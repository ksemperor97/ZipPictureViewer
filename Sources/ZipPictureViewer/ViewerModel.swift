import Foundation
import ViewerCore

/// Shared viewer state with transactional source loading.
///
/// Every load gets a generation; results for an older generation are
/// ignored, so the latest user request always wins.
final class ViewerModel {
    private(set) var state = ViewerState()
    private(set) var currentContext: SourceContext?
    private(set) var pendingContext: SourceContext?
    private(set) var scanIssues: [ScanIssue] = []
    private(set) var loadGeneration = 0

    var isScanning: Bool { pendingContext != nil }
    /// The shown list is a snapshot of a scan that is still reading.
    private(set) var isPartialList = false

    func beginLoad(_ context: SourceContext) -> Int {
        loadGeneration += 1
        pendingContext = context
        return loadGeneration
    }

    /// Show a first container while the load stays pending.
    func applyPreview(_ generation: Int, entries: [ImageEntry], index: Int) -> Bool {
        guard generation == loadGeneration, let pending = pendingContext else { return false }
        currentContext = pending
        scanIssues = []
        state.setEntries(entries, currentIndex: index)
        isPartialList = true
        return true
    }

    func applyLoad(_ generation: Int, entries: [ImageEntry], issues: [ScanIssue], index: Int) -> Bool {
        guard generation == loadGeneration, let pending = pendingContext else { return false }
        currentContext = pending
        pendingContext = nil
        scanIssues = issues
        state.setEntries(entries, currentIndex: index)
        isPartialList = false
        return true
    }

    @discardableResult
    func rejectLoad(_ generation: Int) -> Bool {
        guard generation == loadGeneration else { return false }
        pendingContext = nil
        isPartialList = false
        pendingMove = nil
        return true
    }

    // MARK: Navigation

    enum MoveResult {
        case moved, waiting, unchanged
    }

    /// A move past the part of the folder read so far, waiting for the scan.
    private var pendingMove: ViewerCommand?

    /// While a scan is still reading the folder, a move past the part read
    /// so far waits for it instead of wrapping around or being dropped.
    func move(_ command: ViewerCommand) -> MoveResult {
        let pastLoadedEdge: Bool
        switch command {
        case .previous: pastLoadedEdge = state.isAtFirstEntry
        case .next: pastLoadedEdge = state.isAtLastEntry
        case .previousBundle: pastLoadedEdge = state.isInFirstBundle
        case .nextBundle: pastLoadedEdge = state.isInLastBundle
        default: return .unchanged
        }
        if isPartialList && pastLoadedEdge {
            pendingMove = command
            return .waiting
        }
        pendingMove = nil
        let moved: Bool
        switch command {
        case .previous: moved = state.movePrevious()
        case .next: moved = state.moveNext()
        case .previousBundle: moved = state.moveBundle(by: -1)
        default: moved = state.moveBundle(by: 1)
        }
        return moved ? .moved : .unchanged
    }

    /// Forget a waiting move when a different list is shown.
    func cancelPendingMove() {
        pendingMove = nil
    }

    /// Retry a waiting move after the list grew.
    func retryPendingMove() -> MoveResult {
        guard let command = pendingMove else { return .unchanged }
        pendingMove = nil
        return move(command)
    }
}
