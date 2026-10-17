import Foundation
import ViewerCore

protocol SourceLoaderDelegate: AnyObject {
    func sourceLoader(_ loader: SourceLoader, statusChanged message: String)
    func sourceLoader(_ loader: SourceLoader, scanningChanged scanning: Bool)
    func sourceLoaderWillApply(_ loader: SourceLoader)
    /// A source is shown, from a preview or a complete scan.
    func sourceLoader(_ loader: SourceLoader, applied context: SourceContext, result: ScanResult)
    /// The shown source's list grew (more of a scan, or its final result)
    /// while the shown image stays the same.
    func sourceLoader(_ loader: SourceLoader, extended context: SourceContext, result: ScanResult)
    func sourceLoader(_ loader: SourceLoader, rejected message: String)
}

/// Runs scans in the background and applies their results to the model.
final class SourceLoader {
    weak var delegate: SourceLoaderDelegate?
    private let model: ViewerModel
    private let session: SessionStore
    private let queue = DispatchQueue(label: "scan", qos: .userInitiated)
    private var cancelFlag = CancelFlag()
    private var focusArchive: URL?
    private var previewedGeneration: Int?
    private var rootEncodings: [String: NameEncoding] = [:]
    private var encodingOverrides: [URL: NameEncoding] = [:]
    private(set) var isShuttingDown = false
    private(set) var activeScans = 0

    init(model: ViewerModel, session: SessionStore) {
        self.model = model
        self.session = session
    }

    /// Start scanning. `focusArchive` names an archive inside a folder source
    /// whose first image is shown, unless the saved position is inside it.
    @discardableResult
    func load(_ context: SourceContext, focusArchive focus: URL? = nil) -> Bool {
        cancelFlag.cancel()
        let generation = model.beginLoad(context)
        previewedGeneration = nil
        focusArchive = focus.map { rebase($0, from: context.logicalPath, to: context.accessPath) }
        guard context.isAccessible else {
            model.rejectLoad(generation)
            delegate?.sourceLoader(self, scanningChanged: false)
            delegate?.sourceLoader(self, rejected: "열 수 없는 경로: \(context.logicalPath.path)")
            return false
        }

        var options = ScanOptions()
        options.encoding = rootEncoding(context)
        options.encodingOverrides = encodingOverrides
        options.priorityContainer = focusArchive ?? session.savedContainer(context)
        let flag = CancelFlag()
        cancelFlag = flag
        delegate?.sourceLoader(self, scanningChanged: true)
        delegate?.sourceLoader(self, statusChanged: "스캔 중…")
        activeScans += 1
        queue.async { [weak self] in
            let result = CollectionScanner.scan(
                root: context.accessPath,
                options: options,
                isCancelled: { flag.isCancelled },
                progress: { url, count in
                    guard count % 25 == 0 else { return }
                    DispatchQueue.main.async { self?.scanProgress(generation, url: url, count: count) }
                },
                preview: { entries in
                    DispatchQueue.main.async { self?.scanPreview(generation, entries: entries) }
                }
            )
            DispatchQueue.main.async { self?.scanFinished(generation, result: result) }
        }
        return true
    }

    func cancelCurrent() -> Bool {
        guard model.isScanning else { return false }
        cancelFlag.cancel()
        delegate?.sourceLoader(self, statusChanged: "스캔 취소 요청됨…")
        return true
    }

    func beginShutdown() {
        isShuttingDown = true
        cancelFlag.cancel()
    }

    func encoding(for context: SourceContext, entry: ImageEntry?) -> NameEncoding {
        if let entry, entry.isArchiveMember, let override = encodingOverrides[entry.container] {
            return override
        }
        return rootEncoding(context)
    }

    /// Re-read names of the current archive (or the whole root) with `encoding`.
    func changeEncoding(_ encoding: NameEncoding) -> Bool {
        guard let context = model.currentContext else { return false }
        if let entry = model.state.currentEntry, entry.isArchiveMember {
            encodingOverrides[entry.container] = encoding
        } else {
            rootEncodings[context.sessionKey] = encoding
        }
        return load(context)
    }

    // MARK: Scan callbacks (main thread)

    private func scanProgress(_ generation: Int, url: URL, count: Int) {
        guard generation == model.loadGeneration, model.isScanning else { return }
        let browsing = previewedGeneration == generation ? "\(model.state.positionLabel)  ·  " : ""
        delegate?.sourceLoader(self, statusChanged: "\(browsing)스캔 중… \(count)  \(url.lastPathComponent)")
    }

    private func scanPreview(_ generation: Int, entries: [ImageEntry]) {
        guard !isShuttingDown, generation == model.loadGeneration, let context = model.pendingContext else { return }
        var snapshot = ScanResult()
        snapshot.entries = entries
        if previewedGeneration == generation {
            // A larger snapshot: keep showing the same image.
            let shown = model.state.currentEntry.flatMap { entries.firstIndex(of: $0) }
            guard model.applyPreview(generation, entries: entries, index: shown ?? model.state.currentIndex) else { return }
            delegate?.sourceLoader(self, extended: context, result: snapshot)
            return
        }
        let index = initialIndex(context, entries: entries)
        guard model.applyPreview(generation, entries: entries, index: index) else { return }
        previewedGeneration = generation
        delegate?.sourceLoader(self, applied: context, result: snapshot)
    }

    private func scanFinished(_ generation: Int, result: ScanResult) {
        activeScans -= 1
        guard !isShuttingDown else { return }
        guard generation == model.loadGeneration, let context = model.pendingContext else { return }
        delegate?.sourceLoader(self, scanningChanged: false)
        if !context.isAccessible || result.issues.contains(where: { $0.stage == "discover" && $0.target == context.accessPath }) {
            model.rejectLoad(generation)
            delegate?.sourceLoader(self, rejected: "원본을 더 이상 열 수 없습니다: \(context.logicalPath.path)")
            return
        }
        if result.cancelled {
            model.rejectLoad(generation)
            delegate?.sourceLoader(self, rejected: "스캔 취소됨")
            return
        }

        delegate?.sourceLoaderWillApply(self)
        let shown = previewedGeneration == generation ? model.state.currentEntry : nil
        previewedGeneration = nil
        let keptIndex = shown.flatMap { result.entries.firstIndex(of: $0) }
        let index = keptIndex ?? initialIndex(context, entries: result.entries)
        guard model.applyLoad(generation, entries: result.entries, issues: result.issues, index: index) else { return }
        session.saveRoot(context)
        if keptIndex != nil {
            delegate?.sourceLoader(self, extended: context, result: result)
        } else {
            delegate?.sourceLoader(self, applied: context, result: result)
        }
    }

    // MARK: Helpers

    private func initialIndex(_ context: SourceContext, entries: [ImageEntry]) -> Int {
        let restored = session.restoreIndex(context, entries: entries)
        guard let focus = focusArchive else { return restored }
        focusArchive = nil
        if entries.indices.contains(restored), entries[restored].container == focus {
            return restored
        }
        // A chosen archive without images keeps the restored position; its
        // scan issue is reported separately.
        return entries.firstIndex(where: { $0.container == focus }) ?? restored
    }

    private func rootEncoding(_ context: SourceContext) -> NameEncoding {
        rootEncodings[context.sessionKey] ?? .auto
    }

    /// The scanner walks `accessPath`, so spell the focus under it as well.
    private func rebase(_ url: URL, from logical: URL, to access: URL) -> URL {
        let base = logical.pathComponents
        let parts = SourceContext.absolute(url).pathComponents
        guard parts.starts(with: base) else { return url }
        return parts.dropFirst(base.count).reduce(access) { $0.appendingPathComponent($1) }
    }
}

/// Cancellation shared with a background scan.
final class CancelFlag: @unchecked Sendable {
    private let lock = NSLock()
    private var cancelled = false

    var isCancelled: Bool {
        lock.lock()
        defer { lock.unlock() }
        return cancelled
    }

    func cancel() {
        lock.lock()
        cancelled = true
        lock.unlock()
    }
}
