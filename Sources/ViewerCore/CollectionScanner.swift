import Foundation

public struct ScanOptions: Sendable {
    public var encoding: NameEncoding = .auto
    /// Per-archive name encoding chosen by the user.
    public var encodingOverrides: [URL: NameEncoding] = [:]
    /// Container to scan and preview first (as discovered under the root).
    public var priorityContainer: URL?
    public var zipLimits = ZipLimits()
    public var maxIndexEntries = 100_000

    public init() {}

    func encoding(for archive: URL) -> NameEncoding {
        encodingOverrides[archive] ?? encoding
    }
}

/// Builds the image index of a folder tree or a single archive.
///
/// Every container is isolated: a corrupt archive becomes a `ScanIssue` and
/// the rest of the collection still loads.
public enum CollectionScanner {
    public static func scan(
        root: URL,
        options: ScanOptions = ScanOptions(),
        isCancelled: () -> Bool = { false },
        progress: (URL, Int) -> Void = { _, _ in },
        preview: ([ImageEntry]) -> Void = { _ in }
    ) -> ScanResult {
        var result = ScanResult()
        let containers = discover(root: root, result: &result, isCancelled: isCancelled)
        guard !result.cancelled, !containers.isEmpty else { return result }

        let priority = options.priorityContainer.flatMap { containers.contains($0) ? $0 : nil }
            ?? containers[0]
        let early = scanContainer(priority, options: options, budget: options.maxIndexEntries)
        if case .success(let entries) = early, !entries.isEmpty {
            preview(entries)
        }

        for (index, container) in containers.enumerated() {
            if isCancelled() {
                result.cancelled = true
                break
            }
            let outcome: Result<[ImageEntry], ScanFailure>
            if container == priority {
                outcome = early
            } else {
                let reserved = (try? early.get().count) ?? 0
                let budget = options.maxIndexEntries - result.entries.count - reserved
                outcome = scanContainer(container, options: options, budget: budget)
            }
            switch outcome {
            case .success(let entries): result.entries += entries
            case .failure(let failure): result.issues.append(failure.issue)
            }
            progress(container, index + 1)
        }
        return result
    }

    struct ScanFailure: Error {
        let issue: ScanIssue
    }

    // MARK: Discovery

    private static func discover(root: URL, result: inout ScanResult, isCancelled: () -> Bool) -> [URL] {
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: root.path, isDirectory: &isDirectory) else {
            result.issues.append(ScanIssue(target: root, stage: "discover", kind: "not_found", message: "Root does not exist: \(root.path)"))
            return []
        }
        guard isDirectory.boolValue else {
            result.discoveredFiles = 1
            return Formats.isArchive(root) ? [root] : []
        }

        var archives: [URL] = []
        var imageFolders = Set<URL>()
        let keys: [URLResourceKey] = [.isRegularFileKey]
        var walkIssues: [ScanIssue] = []
        defer { result.issues += walkIssues }
        let enumerator = FileManager.default.enumerator(
            at: root,
            includingPropertiesForKeys: keys,
            errorHandler: { url, error in
                walkIssues.append(ScanIssue(target: url, stage: "discover", kind: "os_error", message: error.localizedDescription))
                return true
            }
        )
        while let url = enumerator?.nextObject() as? URL {
            if isCancelled() {
                result.cancelled = true
                return []
            }
            guard (try? url.resourceValues(forKeys: Set(keys)).isRegularFile) == true else { continue }
            result.discoveredFiles += 1
            let parent = url.deletingLastPathComponent()
            if Formats.isArchive(url) {
                archives.append(rebase(url, onto: root))
            } else if Formats.isImageName(url.lastPathComponent) {
                imageFolders.insert(rebase(parent, onto: root))
            }
        }
        return (archives + imageFolders).sorted {
            NaturalSort.lessPath(relativeComponents($0, root), relativeComponents($1, root))
        }
    }

    /// Keep discovered paths spelled under `root` so they match the root the
    /// caller passed (the enumerator may resolve /var to /private/var).
    private static func rebase(_ url: URL, onto root: URL) -> URL {
        let components = relativeComponents(url, root)
        return components.reduce(root) { $0.appendingPathComponent($1) }
    }

    private static func relativeComponents(_ url: URL, _ root: URL) -> [String] {
        let rootPath = root.path.hasSuffix("/") ? root.path : root.path + "/"
        if url.path.hasPrefix(rootPath) {
            return url.path.dropFirst(rootPath.count).split(separator: "/").map(String.init)
        }
        if url.path == root.path {
            return []
        }
        let resolvedRoot = root.resolvingSymlinksInPath().pathComponents
        let resolved = url.resolvingSymlinksInPath().pathComponents
        if resolved.starts(with: resolvedRoot) {
            return Array(resolved.dropFirst(resolvedRoot.count))
        }
        let plainRoot = root.pathComponents
        let plain = url.pathComponents
        return plain.starts(with: plainRoot) ? Array(plain.dropFirst(plainRoot.count)) : plain
    }

    // MARK: Containers

    private static func scanContainer(_ container: URL, options: ScanOptions, budget: Int) -> Result<[ImageEntry], ScanFailure> {
        let isArchive = Formats.isArchive(container) && !isDirectory(container)
        do {
            let entries = isArchive
                ? try scanArchive(container, options: options)
                : try scanFolder(container)
            guard entries.count <= budget else {
                throw ZipError(.resourceLimit, "Image index exceeds the \(options.maxIndexEntries)-entry limit.")
            }
            return .success(entries)
        } catch {
            return .failure(ScanFailure(issue: issue(for: container, stage: isArchive ? "scan_archive" : "scan_folder", error: error)))
        }
    }

    private static func scanArchive(_ archive: URL, options: ScanOptions) throws -> [ImageEntry] {
        let revision = try ContainerRevision(url: archive)
        let records = try ZipArchive.records(at: archive, encoding: options.encoding(for: archive), limits: options.zipLimits)
        return records
            .filter { !$0.isDirectory && Formats.isImageName($0.name) }
            .map { record in
                ImageEntry(
                    container: archive,
                    memberName: record.name,
                    kind: .archive,
                    revision: revision,
                    memberID: ArchiveMemberID(recordIndex: record.index, headerOffset: record.location.localHeaderOffset, crc: record.crc),
                    location: record.location,
                    encryption: record.encryption
                )
            }
            .sorted { NaturalSort.less($0.memberName, $1.memberName) }
    }

    private static func scanFolder(_ folder: URL) throws -> [ImageEntry] {
        let names = try FileManager.default.contentsOfDirectory(atPath: folder.path)
            .filter { Formats.isImageName($0) }
            .sorted(by: NaturalSort.less)
        return names.compactMap { name in
            let url = folder.appendingPathComponent(name)
            guard !isDirectory(url) else { return nil }
            // A file that cannot be stat'ed stays navigable; loading reports why.
            return ImageEntry(container: folder, memberName: name, kind: .folder, revision: try? ContainerRevision(url: url))
        }
    }

    private static func isDirectory(_ url: URL) -> Bool {
        var isDirectory: ObjCBool = false
        return FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory) && isDirectory.boolValue
    }

    private static func issue(for target: URL, stage: String, error: Error) -> ScanIssue {
        if let zipError = error as? ZipError {
            return ScanIssue(target: target, stage: stage, kind: zipError.kind.rawValue, message: zipError.message)
        }
        let nsError = error as NSError
        let kind = nsError.code == NSFileReadNoPermissionError ? "permission_denied" : "os_error"
        return ScanIssue(target: target, stage: stage, kind: kind, message: nsError.localizedDescription)
    }
}
