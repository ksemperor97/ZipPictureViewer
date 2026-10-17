import AppKit
import ViewerCore

/// Handles viewer keys at the end of the responder chain, so they work
/// whichever control last had focus.
final class ViewerWindow: NSWindow {
    var onKeyDown: ((NSEvent) -> Bool)?

    override func keyDown(with event: NSEvent) {
        if onKeyDown?(event) != true {
            super.keyDown(with: event)
        }
    }
}

/// Composes the viewer window and routes commands between its parts.
final class MainWindowController: NSWindowController, NSWindowDelegate {
    let model = ViewerModel()
    let session = SessionStore()
    let canvas = ImageCanvas(frame: .zero)
    let controls = ControlsPanel(frame: .zero)
    let info = InfoPanel(frame: .zero)
    let issuePanel = IssuePanel()
    let helpPanel = HelpPanel()
    private(set) lazy var loader = SourceLoader(model: model, session: session)
    private(set) lazy var display = DisplayController(model: model, canvas: canvas)
    private(set) lazy var opener = SourceOpener(model: model, loader: loader, session: session)
    private var hideWork: DispatchWorkItem?
    private var pendingSave: DispatchWorkItem?
    private(set) var isClosing = false
    /// True once a full-screen transition has finished, not while animating.
    private(set) var isFullScreen = false

    init() {
        let window = ViewerWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1100, height: 800),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "Zip Picture Viewer"
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.minSize = NSSize(width: 480, height: 360)
        window.backgroundColor = NSColor(calibratedWhite: 0.09, alpha: 1)
        window.collectionBehavior = [.fullScreenPrimary]
        window.acceptsMouseMovedEvents = true
        super.init(window: window)
        window.delegate = self
        buildLayout(in: window)
        connect()
        window.center()
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    // MARK: Layout and wiring

    private func buildLayout(in window: NSWindow) {
        let root = ViewerContentView(frame: window.contentRect(forFrameRect: window.frame))
        window.contentView = root
        for view in [canvas, info, controls] as [NSView] {
            view.translatesAutoresizingMaskIntoConstraints = false
            root.addSubview(view)
        }
        NSLayoutConstraint.activate([
            canvas.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            canvas.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            canvas.topAnchor.constraint(equalTo: root.topAnchor),
            canvas.bottomAnchor.constraint(equalTo: root.bottomAnchor),
            controls.centerXAnchor.constraint(equalTo: root.centerXAnchor),
            controls.bottomAnchor.constraint(equalTo: root.bottomAnchor, constant: -16),
            controls.widthAnchor.constraint(lessThanOrEqualTo: root.widthAnchor, constant: -24),
            info.centerXAnchor.constraint(equalTo: root.centerXAnchor),
            info.topAnchor.constraint(equalTo: root.topAnchor, constant: 34),
            info.widthAnchor.constraint(lessThanOrEqualTo: root.widthAnchor, constant: -80),
        ])
        root.onDrop = { [weak self] url in self?.opener.open(url) }
        root.onMouseMoved = { [weak self] in self?.revealPanels() }
        canvas.onMouseMoved = { [weak self] in self?.revealPanels() }
        setPanelsVisible(false)
        window.initialFirstResponder = canvas
    }

    private func connect() {
        loader.delegate = self
        display.delegate = self
        controls.onCommand = { [weak self] command in self?.perform(command) }
        controls.onEncodingChange = { [weak self] encoding in self?.opener.changeEncoding(encoding) }
        (window as? ViewerWindow)?.onKeyDown = { [weak self] event in
            guard let self, let command = KeyBindings.command(for: event) else { return false }
            self.perform(command)
            return true
        }
        opener.onMessage = { [weak self] message in self?.showTransientStatus(message) }
        opener.onLoadStarted = { [weak self] in self?.revealPanels() }
        issuePanel.onRetry = { [weak self] in self?.opener.refresh() }
        updateNavigation()
    }

    // MARK: Commands

    func perform(_ command: ViewerCommand) {
        guard !isClosing, let window else { return }
        switch command {
        case .openFolder: opener.chooseFolder(in: window)
        case .openArchive: opener.chooseArchive(in: window)
        case .previous: if model.movePrevious() { display.showCurrent() }
        case .next: if model.moveNext() { display.showCurrent() }
        case .previousBundle: if model.moveBundle(by: -1) { display.showCurrent() }
        case .nextBundle: if model.moveBundle(by: 1) { display.showCurrent() }
        case .previousFolder: opener.openSibling(step: -1)
        case .nextFolder: opener.openSibling(step: 1)
        case .refresh: opener.refresh()
        case .cancelScan: if loader.cancelCurrent() { controls.button("cancel_scan_button")?.isEnabled = false }
        case .fit: canvas.requestFit()
        case .actualSize: canvas.actualSize()
        case .zoomIn: canvas.zoom(by: 1.25)
        case .zoomOut: canvas.zoom(by: 0.8)
        case .fullscreen: window.toggleFullScreen(nil)
        case .exitFullscreen: if window.styleMask.contains(.fullScreen) { window.toggleFullScreen(nil) }
        case .help: helpPanel.makeKeyAndOrderFront(nil)
        case .issues: showIssues()
        case .minimize: window.miniaturize(nil)
        case .close: window.performClose(nil)
        }
    }

    func issueMessages() -> [String] {
        model.scanIssues.map { "[\($0.kind)] \($0.target.path)\n\($0.message)" } + display.issueMessages()
    }

    private func showIssues() {
        let messages = issueMessages()
        guard !messages.isEmpty else { return }
        issuePanel.setMessages(messages)
        issuePanel.makeKeyAndOrderFront(nil)
    }

    // MARK: Status

    private func updateNavigation() {
        let state = model.state
        let hasEntries = state.hasEntries
        controls.setEnabled(model.currentContext != nil, for: ["previous_folder_button", "next_folder_button", "refresh_button"])
        controls.setEnabled(hasEntries && state.hasMultipleBundles, for: ["previous_archive_button", "next_archive_button"])
        controls.setEnabled(hasEntries && state.currentIndex > 0, for: ["previous_button"])
        controls.setEnabled(hasEntries, for: ["next_button", "fit_button", "actual_size_button", "zoom_in_button", "zoom_out_button"])
    }

    private func updateIssues() {
        controls.setIssueCount(model.scanIssues.count + display.errors.count)
        if issuePanel.isVisible { issuePanel.setMessages(issueMessages()) }
    }

    private func showTransientStatus(_ message: String) {
        controls.statusLabel.stringValue = message
        revealPanels()
    }

    private func revealPanels() {
        guard !isClosing else { return }
        setPanelsVisible(true)
        hideWork?.cancel()
        let work = DispatchWorkItem { [weak self] in self?.hidePanelsUnlessHovered() }
        hideWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.2, execute: work)
    }

    private func hidePanelsUnlessHovered() {
        guard let window else { return }
        let mouse = controls.convert(window.mouseLocationOutsideOfEventStream, from: nil)
        if controls.bounds.contains(mouse) {
            revealPanels()
            return
        }
        setPanelsVisible(false)
    }

    private func setPanelsVisible(_ visible: Bool) {
        controls.isHidden = !visible
        info.isHidden = !visible || info.text.isEmpty
        window?.standardWindowButton(.closeButton)?.superview?.isHidden = !visible
    }

    private func schedulePositionSave() {
        pendingSave?.cancel()
        guard let context = model.currentContext, let entry = model.state.currentEntry else { return }
        let state = model.state
        let work = DispatchWorkItem { [weak self] in
            self?.session.savePosition(context, entry: entry, index: state.currentIndex, indexInBundle: state.indexInBundle)
        }
        pendingSave = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2, execute: work)
    }

    private func flushPositionSave() {
        if let work = pendingSave, !work.isCancelled {
            work.perform()
            work.cancel()
        }
        pendingSave = nil
    }

    // MARK: NSWindowDelegate

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        isClosing = true
        hideWork?.cancel()
        opener.beginShutdown()
        loader.beginShutdown()
        display.beginShutdown()
        flushPositionSave()
        return true
    }

    func windowDidEnterFullScreen(_ notification: Notification) {
        isFullScreen = true
        controls.setFullscreenTitle(true)
    }

    func windowDidExitFullScreen(_ notification: Notification) {
        isFullScreen = false
        controls.setFullscreenTitle(false)
    }
}

extension MainWindowController: SourceLoaderDelegate {
    func sourceLoader(_ loader: SourceLoader, statusChanged message: String) {
        controls.statusLabel.stringValue = message
    }

    func sourceLoader(_ loader: SourceLoader, scanningChanged scanning: Bool) {
        controls.setScanning(scanning)
    }

    func sourceLoaderWillApply(_ loader: SourceLoader) {
        flushPositionSave()
    }

    func sourceLoader(_ loader: SourceLoader, applied context: SourceContext, result: ScanResult) {
        display.reset()
        updateIssues()
        if result.entries.isEmpty {
            let message = !result.issues.isEmpty ? "이미지 컨테이너를 읽지 못했습니다"
                : result.discoveredFiles == 0 ? "빈 폴더입니다"
                : "지원되는 이미지 형식이 없습니다"
            canvas.showMessage(message)
            info.text = context.logicalPath.path
            controls.statusLabel.stringValue = "0 / 0"
            updateNavigation()
            return
        }
        display.showCurrent()
    }

    func sourceLoader(_ loader: SourceLoader, completed context: SourceContext, result: ScanResult) {
        updateIssues()
        updateNavigation()
        controls.statusLabel.stringValue = model.state.positionLabel
    }

    func sourceLoader(_ loader: SourceLoader, rejected message: String) {
        showTransientStatus(message)
        updateNavigation()
    }
}

extension MainWindowController: DisplayControllerDelegate {
    func display(_ display: DisplayController, startedEntry entry: ImageEntry) {
        if let context = model.currentContext {
            controls.selectEncoding(loader.encoding(for: context, entry: entry))
        }
        info.text = "\(entry.container.path)  |  \(entry.memberName)"
        controls.statusLabel.stringValue = model.state.positionLabel
        updateNavigation()
        schedulePositionSave()
    }

    func display(_ display: DisplayController, statusChanged message: String) {
        controls.statusLabel.stringValue = message
    }

    func displayErrorsChanged(_ display: DisplayController) {
        updateNavigation()
        updateIssues()
        if !display.errors.isEmpty { revealPanels() }
    }

    func display(_ display: DisplayController, passwordFor entry: ImageEntry, completion: @escaping (String?) -> Void) {
        guard let window else { return completion(nil) }
        PasswordPrompt.ask(for: entry.container.lastPathComponent, on: window, completion: completion)
    }
}
