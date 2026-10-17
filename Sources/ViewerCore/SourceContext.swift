import Foundation

/// A user-selected source and the path used to access its contents.
///
/// `logicalPath` keeps symbolic-link components and is the identity used by
/// session storage and sibling navigation. `accessPath` is resolved and is
/// what the scanner walks, so scanned entries live under it.
public struct SourceContext: Hashable, Sendable {
    public let logicalPath: URL
    public let accessPath: URL
    public let kind: SourceKind

    public init(path: URL, kind: SourceKind? = nil) {
        let logical = SourceContext.absolute(path)
        let access = logical.resolvingSymlinksInPath()
        logicalPath = logical
        accessPath = access
        self.kind = kind ?? SourceContext.inferKind(logical: logical, access: access)
    }

    public var sessionKey: String { logicalPath.path }

    public var isAccessible: Bool {
        var isDirectory: ObjCBool = false
        let exists = FileManager.default.fileExists(atPath: accessPath.path, isDirectory: &isDirectory)
        return exists && (kind == .archive ? !isDirectory.boolValue : isDirectory.boolValue)
    }

    /// Absolute path with "." and ".." removed but symlinks kept. Unlike
    /// `standardizedFileURL` this never strips a leading "/private".
    public static func absolute(_ url: URL) -> URL {
        let expanded = (url.path as NSString).expandingTildeInPath
        let base = expanded.hasPrefix("/") ? expanded : FileManager.default.currentDirectoryPath + "/" + expanded
        var parts: [String] = []
        for part in base.split(separator: "/") {
            switch part {
            case ".": continue
            case "..": _ = parts.popLast()
            default: parts.append(String(part))
            }
        }
        return URL(fileURLWithPath: "/" + parts.joined(separator: "/"))
    }

    private static func inferKind(logical: URL, access: URL) -> SourceKind {
        var isDirectory: ObjCBool = false
        FileManager.default.fileExists(atPath: access.path, isDirectory: &isDirectory)
        let looksLikeArchive = Formats.isArchive(logical) || Formats.isArchive(access)
        return looksLikeArchive && !isDirectory.boolValue ? .archive : .folder
    }
}

/// Moving between sibling collections and choosing what an archive opens.
public enum FolderNavigation {
    /// The folder to browse when the user opens a single archive, or nil when
    /// the archive should open alone (missing, or in a folder too broad to
    /// scan recursively, such as the home folder or a volume root).
    public static func containingFolder(of archive: SourceContext) -> SourceContext? {
        guard archive.kind == .archive, archive.isAccessible else { return nil }
        let parent = archive.logicalPath.deletingLastPathComponent()
        if isBroadScanRoot(parent) { return nil }
        return SourceContext(path: parent, kind: .folder)
    }

    public static func sibling(of context: SourceContext, step: Int) -> SourceContext? {
        let parent = context.logicalPath.deletingLastPathComponent()
        guard parent.path != context.logicalPath.path else { return nil }
        let candidates = context.kind == .archive ? childArchives(of: parent) : childFolders(of: parent)
        guard candidates.count > 1,
              let index = candidates.firstIndex(where: { $0.path == context.logicalPath.path })
        else { return nil }
        let next = candidates[(index + step + candidates.count) % candidates.count]
        return SourceContext(path: next, kind: context.kind)
    }

    public static func childFolders(of folder: URL) -> [URL] {
        children(of: folder) { url, isDirectory in isDirectory }
    }

    public static func childArchives(of folder: URL) -> [URL] {
        children(of: folder) { url, isDirectory in !isDirectory && Formats.isArchive(url) }
    }

    private static func children(of folder: URL, where include: (URL, Bool) -> Bool) -> [URL] {
        let keys: [URLResourceKey] = [.isDirectoryKey]
        guard let urls = try? FileManager.default.contentsOfDirectory(
            at: folder,
            includingPropertiesForKeys: keys,
            options: [.skipsHiddenFiles]
        ) else { return [] }
        return urls
            .filter { url in
                let isDirectory = (try? url.resourceValues(forKeys: Set(keys)).isDirectory) ?? false
                return include(url, isDirectory == true)
            }
            .map { folder.appendingPathComponent($0.lastPathComponent) }
            .sorted { NaturalSort.less($0.lastPathComponent, $1.lastPathComponent) }
    }

    private static func isBroadScanRoot(_ folder: URL) -> Bool {
        let resolved = folder.resolvingSymlinksInPath().path
        // $HOME defines the home folder on POSIX systems; FileManager ignores it.
        let homeURL = ProcessInfo.processInfo.environment["HOME"].map { URL(fileURLWithPath: $0) }
            ?? FileManager.default.homeDirectoryForCurrentUser
        let home = homeURL.resolvingSymlinksInPath().path
        let isVolumeRoot = folder.pathComponents.count <= 1
            || (folder.pathComponents.count == 3 && folder.pathComponents[1] == "Volumes")
        return resolved == home || isVolumeRoot
    }
}
