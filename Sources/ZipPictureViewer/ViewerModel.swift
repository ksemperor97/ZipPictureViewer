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
        return true
    }

    func applyLoad(_ generation: Int, entries: [ImageEntry], issues: [ScanIssue], index: Int) -> Bool {
        guard generation == loadGeneration, let pending = pendingContext else { return false }
        currentContext = pending
        pendingContext = nil
        scanIssues = issues
        state.setEntries(entries, currentIndex: index)
        return true
    }

    @discardableResult
    func rejectLoad(_ generation: Int) -> Bool {
        guard generation == loadGeneration else { return false }
        pendingContext = nil
        return true
    }

    func moveNext() -> Bool { state.moveNext() }
    func movePrevious() -> Bool { state.movePrevious() }
    func moveBundle(by step: Int) -> Bool { state.moveBundle(by: step) }
}
