import Foundation

/// Persists the last source and per-source reading positions.
///
/// The file format (version 2) is the one the Python version wrote, so
/// saved positions survive the switch. The file is untrusted input: every
/// field is type-checked and a corrupt file is treated as empty.
public final class SessionStore {
    public static let configDirectoryEnvironment = "ZIP_PICTURE_VIEWER_CONFIG_DIR"

    public let fileURL: URL

    public init(fileURL: URL = SessionStore.defaultFileURL()) {
        self.fileURL = fileURL
    }

    public static func defaultFileURL() -> URL {
        if let override = ProcessInfo.processInfo.environment[configDirectoryEnvironment], !override.isEmpty {
            return URL(fileURLWithPath: override).appendingPathComponent("session.json")
        }
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return support.appendingPathComponent("ZipPictureViewer/session.json")
    }

    public func lastContext() -> SourceContext? {
        guard let root = read()["last_root"] as? [String: Any],
              let path = root["logical_path"] as? String,
              let kindName = root["source_kind"] as? String,
              let kind = SourceKind(rawValue: kindName)
        else { return nil }
        let context = SourceContext(path: URL(fileURLWithPath: path), kind: kind)
        return context.isAccessible ? context : nil
    }

    public func saveRoot(_ context: SourceContext) {
        var data = read()
        data["last_root"] = rootDictionary(context)
        write(data)
    }

    public func savePosition(_ context: SourceContext, entry: ImageEntry, index: Int, indexInBundle: Int) {
        var data = read()
        var positions = data["positions"] as? [String: Any] ?? [:]
        positions[context.sessionKey] = [
            "container_id": containerID(context, entry.container),
            "member_id": serializedMemberID(entry),
            "container_index": max(indexInBundle, 0),
            "global_index": max(index, 0),
        ] as [String: Any]
        data["positions"] = positions
        data["last_root"] = rootDictionary(context)
        write(data)
    }

    /// Index of the saved image, the nearest survivor in its container, or 0.
    public func restoreIndex(_ context: SourceContext, entries: [ImageEntry]) -> Int {
        guard let position = savedPosition(context),
              let container = position["container_id"] as? String
        else { return 0 }
        let memberID = position["member_id"]
        var sameContainer: [Int] = []
        for (index, entry) in entries.enumerated() where containerID(context, entry.container) == container {
            if memberMatches(entry, memberID) { return index }
            sameContainer.append(index)
        }
        guard !sameContainer.isEmpty else { return 0 }
        let saved = (position["container_index"] as? Int) ?? 0
        return sameContainer[max(0, min(saved, sameContainer.count - 1))]
    }

    /// The container of the saved position, spelled as the scanner names it.
    public func savedContainer(_ context: SourceContext) -> URL? {
        guard let container = savedPosition(context)?["container_id"] as? String else { return nil }
        if container == "." { return context.accessPath }
        if container.hasPrefix("/") { return URL(fileURLWithPath: container) }
        return container.split(separator: "/").reduce(context.accessPath) { $0.appendingPathComponent(String($1)) }
    }

    // MARK: Encoding

    private func savedPosition(_ context: SourceContext) -> [String: Any]? {
        (read()["positions"] as? [String: Any])?[context.sessionKey] as? [String: Any]
    }

    private func rootDictionary(_ context: SourceContext) -> [String: String] {
        [
            "logical_path": context.logicalPath.path,
            "access_path": context.accessPath.path,
            "source_kind": context.kind.rawValue,
        ]
    }

    private func containerID(_ context: SourceContext, _ container: URL) -> String {
        let root = context.accessPath.resolvingSymlinksInPath().pathComponents
        let target = container.resolvingSymlinksInPath().pathComponents
        if context.kind == .archive && root == target { return "." }
        guard target.starts(with: root) else { return container.path }
        let relative = target.dropFirst(root.count)
        return relative.isEmpty ? "." : relative.joined(separator: "/")
    }

    private func serializedMemberID(_ entry: ImageEntry) -> Any {
        guard let id = entry.memberID else { return entry.memberName }
        return ["record_index": id.recordIndex, "header_offset": id.headerOffset, "crc": id.crc] as [String: Any]
    }

    private func memberMatches(_ entry: ImageEntry, _ saved: Any?) -> Bool {
        if let name = saved as? String { return entry.memberName == name }
        guard let saved = saved as? [String: Any],
              let record = saved["record_index"] as? Int,
              let offset = (saved["header_offset"] as? NSNumber)?.uint64Value,
              let crc = (saved["crc"] as? NSNumber)?.uint32Value
        else { return false }
        return entry.memberID == ArchiveMemberID(recordIndex: record, headerOffset: offset, crc: crc)
    }

    // MARK: File access

    private func read() -> [String: Any] {
        guard let data = try? Data(contentsOf: fileURL),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              object["version"] as? Int == 2
        else { return ["version": 2, "positions": [String: Any]()] }
        return object
    }

    private func write(_ object: [String: Any]) {
        var object = object
        object["version"] = 2
        do {
            try FileManager.default.createDirectory(at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            let data = try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
            try data.write(to: fileURL, options: .atomic)
        } catch {
            // Losing a saved position must not interrupt viewing.
            NSLog("Cannot save session to %@: %@", fileURL.path, error.localizedDescription)
        }
    }
}
