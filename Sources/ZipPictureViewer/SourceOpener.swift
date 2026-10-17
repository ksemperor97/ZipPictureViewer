import AppKit
import ViewerCore

/// Turns user requests (dialogs, drops, Finder, restore) into source loads.
final class SourceOpener {
    var onMessage: ((String) -> Void)?
    var onLoadStarted: (() -> Void)?
    private let model: ViewerModel
    private let loader: SourceLoader
    private let session: SessionStore
    private var restorePending = false
    private var isShuttingDown = false

    init(model: ViewerModel, loader: SourceLoader, session: SessionStore) {
        self.model = model
        self.loader = loader
        self.session = session
    }

    /// Reopen the previous session on the next run-loop turn unless an
    /// explicit open request (command line, Finder) arrives first.
    func scheduleRestore() {
        restorePending = true
        DispatchQueue.main.async { [weak self] in self?.restoreLastSource() }
    }

    func beginShutdown() {
        isShuttingDown = true
        restorePending = false
    }

    func chooseFolder(in window: NSWindow) {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.message = "이미지 컬렉션 폴더 선택"
        panel.beginSheetModal(for: window) { [weak self] response in
            if response == .OK, let url = panel.url { self?.open(url) }
        }
    }

    func chooseArchive(in window: NSWindow) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowedContentTypes = [.zip] + [.init(filenameExtension: "cbz")].compactMap { $0 }
        panel.message = "ZIP/CBZ 선택"
        panel.beginSheetModal(for: window) { [weak self] response in
            if response == .OK, let url = panel.url { self?.open(url) }
        }
    }

    /// Open a folder or archive. An archive opens its containing folder so
    /// sibling archives stay reachable, starting at the chosen archive.
    func open(_ url: URL) {
        restorePending = false
        let context = SourceContext(path: url)
        if let folder = FolderNavigation.containingFolder(of: context) {
            load(folder, focusArchive: context.logicalPath)
        } else {
            load(context)
        }
    }

    func load(_ context: SourceContext, focusArchive: URL? = nil) {
        guard !isShuttingDown else { return }
        if loader.load(context, focusArchive: focusArchive) {
            onLoadStarted?()
        }
    }

    func refresh() {
        if let context = model.currentContext { load(context) }
    }

    func openSibling(step: Int) {
        guard let context = model.currentContext else { return }
        guard let sibling = FolderNavigation.sibling(of: context, step: step) else {
            onMessage?("형제 항목을 찾지 못했습니다")
            return
        }
        load(sibling)
    }

    func changeEncoding(_ encoding: NameEncoding) {
        guard !isShuttingDown, loader.changeEncoding(encoding) else { return }
        onLoadStarted?()
    }

    private func restoreLastSource() {
        guard restorePending, model.currentContext == nil, !model.isScanning else { return }
        restorePending = false
        if let context = session.lastContext() { load(context) }
    }
}
