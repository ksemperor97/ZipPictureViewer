import AppKit

/// Commands the end-to-end tests send to the running app.
///
/// Input is posted to AppKit's event queue as real `NSEvent`s, so key
/// routing, hit testing and button tracking behave as for a user. Posting
/// (rather than delivering synchronously) also lets the reply go out before
/// the event is handled.
final class AutomationCommands {
    private let controller: MainWindowController
    private var window: NSWindow { controller.window! }

    init(controller: MainWindowController) {
        self.controller = controller
    }

    func run(_ request: [String: Any]) throws -> Any {
        let params = request["params"] as? [String: Any] ?? [:]
        switch request["name"] as? String {
        case "state": return state()
        case "pixel": return controller.canvas.renderedColor(atX: number(params["x"], 0.5), y: number(params["y"], 0.5))
        case "key": return try key(params["key"] as? String ?? "", modifiers: params["modifiers"] as? [String] ?? [])
        case "move_mouse": return postMouse(.mouseMoved, at: point(params), clickCount: 0)
        case "click": return try click(params["button"] as? String ?? "")
        case "clickable":
            let button = controller.controls.button(params["button"] as? String ?? "")
            return button.map { !$0.isHiddenOrHasHiddenAncestor && $0.isEnabled } ?? false
        case "double_click": return doubleClick(at: point(params))
        case "drop": return drop((params["paths"] as? [String] ?? []).map(URL.init(fileURLWithPath:)), at: point(params))
        case "file_open":
            let url = URL(fileURLWithPath: params["path"] as? String ?? "")
            DispatchQueue.main.async { NSApp.delegate?.application?(NSApp, open: [url]) }
            return true
        case "choose": return try choose(params["control"] as? String ?? "", index: params["index"] as? Int ?? 0)
        case "choose_menu": return try chooseMenu(params["path"] as? [String] ?? [])
        case "answer_dialog": return try answerDialog(text: params["text"] as? String ?? "", accept: params["accept"] as? Bool ?? true)
        case "activate":
            NSApp.activate(ignoringOtherApps: true)
            window.makeKeyAndOrderFront(nil)
            return window.isKeyWindow
        case "close":
            DispatchQueue.main.async { self.window.performClose(nil) }
            return true
        case let name: throw AutomationError("Unknown automation command: \(name ?? "nil")")
        }
    }

    private func state() -> [String: Any] {
        let model = controller.model
        let entry = model.state.currentEntry
        let canvas = controller.canvas
        let mainWindow = window
        return [
            "visible": mainWindow.isVisible,
            "window_number": mainWindow.windowNumber,
            "first_responder": mainWindow.firstResponder.map { String(describing: type(of: $0)) } ?? NSNull(),
            "active": NSApp.isActive && mainWindow.isKeyWindow,
            "fullscreen": controller.isFullScreen,
            "source": model.currentContext?.logicalPath.path ?? NSNull(),
            "source_kind": model.currentContext?.kind.rawValue ?? NSNull(),
            "scanning": model.isScanning,
            "entry_count": model.state.entries.count,
            "index": entry == nil ? NSNull() : model.state.currentIndex,
            "archive": entry?.container.lastPathComponent ?? NSNull(),
            "member": entry?.memberName ?? NSNull(),
            "status": controller.controls.statusLabel.stringValue,
            "file_label": controller.info.text,
            "issues_button": controller.controls.button("issues_button")?.title ?? "",
            "issue_messages": controller.issueMessages(),
            "message": canvas.message,
            "has_image": canvas.hasImage,
            "movie_running": canvas.isAnimating,
            "fit_mode": canvas.fitMode,
            "zoom": (Double(canvas.magnification) * 10_000).rounded() / 10_000,
            "controls_visible": !controller.controls.isHidden,
            "modal_title": mainWindow.attachedSheet?.title ?? NSNull(),
            "dialog_windows": Dictionary(
                NSApp.windows
                    .filter { $0 !== mainWindow && $0.isVisible && !$0.isSheet && !$0.title.isEmpty }
                    .map { ($0.title, $0.windowNumber) },
                uniquingKeysWith: { first, _ in first }
            ),
            "dialogs": NSApp.windows
                .filter { $0 !== mainWindow && $0.isVisible && !$0.isSheet && !$0.title.isEmpty }
                .map(\.title)
                .sorted(),
        ]
    }

    // MARK: Keyboard

    private static let keys: [String: (UInt16, String)] = [
        "Left": (123, "\u{F702}"), "Right": (124, "\u{F703}"), "Down": (125, "\u{F701}"), "Up": (126, "\u{F700}"),
        "Space": (49, " "), "Return": (36, "\r"), "Escape": (53, "\u{1B}"),
        "F": (3, "f"), "R": (15, "r"), "O": (31, "o"), "Question": (44, "?"),
        "Plus": (24, "+"), "Minus": (27, "-"), "0": (29, "0"), "1": (18, "1"),
    ]

    private func key(_ name: String, modifiers: [String]) throws -> Bool {
        guard let (code, characters) = Self.keys[name] else { throw AutomationError("Unknown key \(name)") }
        var flags: NSEvent.ModifierFlags = code >= 123 ? [.function, .numericPad] : []
        for modifier in modifiers {
            // Same names as the Qt-era tests: "ctrl" is Command on macOS.
            switch modifier {
            case "ctrl": flags.insert(.command)
            case "meta": flags.insert(.control)
            case "shift": flags.insert(.shift)
            case "alt": flags.insert(.option)
            default: throw AutomationError("Unknown modifier \(modifier)")
            }
        }
        for type in [NSEvent.EventType.keyDown, .keyUp] {
            let event = NSEvent.keyEvent(
                with: type, location: .zero, modifierFlags: flags, timestamp: ProcessInfo.processInfo.systemUptime,
                windowNumber: window.windowNumber, context: nil, characters: characters,
                charactersIgnoringModifiers: characters, isARepeat: false, keyCode: code
            )
            if let event { NSApp.postEvent(event, atStart: false) }
        }
        return true
    }

    // MARK: Mouse

    private func click(_ name: String) throws -> Bool {
        guard let button = controller.controls.button(name) else { throw AutomationError("No control \(name)") }
        guard !button.isHiddenOrHasHiddenAncestor, button.isEnabled else {
            throw AutomationError("\(name) is not clickable")
        }
        // Click where the button is drawn after any pending layout pass.
        window.contentView?.layoutSubtreeIfNeeded()
        let center = button.convert(NSPoint(x: button.bounds.midX, y: button.bounds.midY), to: nil)
        _ = postMouse(.leftMouseDown, at: center, clickCount: 1)
        return postMouse(.leftMouseUp, at: center, clickCount: 1)
    }

    private func doubleClick(at location: NSPoint) -> Bool {
        for clickCount in [1, 2] {
            _ = postMouse(.leftMouseDown, at: location, clickCount: clickCount)
            _ = postMouse(.leftMouseUp, at: location, clickCount: clickCount)
        }
        return true
    }

    @discardableResult
    private func postMouse(_ type: NSEvent.EventType, at location: NSPoint, clickCount: Int) -> Bool {
        guard let event = NSEvent.mouseEvent(
            with: type, location: location, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
            windowNumber: window.windowNumber, context: nil, eventNumber: 0, clickCount: clickCount,
            pressure: type == .leftMouseUp ? 0 : 1
        ) else { return false }
        NSApp.postEvent(event, atStart: false)
        return true
    }

    /// Fractional window position (from the top-left) in window coordinates.
    private func point(_ params: [String: Any]) -> NSPoint {
        let size = window.contentView?.bounds.size ?? .zero
        return NSPoint(x: size.width * number(params["x"], 0.5), y: size.height * (1 - number(params["y"], 0.5)))
    }

    private func number(_ value: Any?, _ fallback: CGFloat) -> CGFloat {
        (value as? NSNumber).map { CGFloat($0.doubleValue) } ?? fallback
    }

    // MARK: Drag and drop, menus, sheets

    /// Deliver a drop to the view under the point, as the drag manager does.
    private func drop(_ urls: [URL], at location: NSPoint) -> [String: Any] {
        let pasteboard = NSPasteboard(name: NSPasteboard.Name("zpv-automation-\(UUID().uuidString)"))
        pasteboard.clearContents()
        pasteboard.writeObjects(urls as [NSURL])
        let info = AutomationDraggingInfo(pasteboard: pasteboard, location: location, window: window)
        var target = window.contentView?.hitTest(location)
        while let view = target, !view.registeredDraggedTypes.contains(.fileURL) {
            target = view.superview
        }
        guard let destination = target,
              destination.draggingEntered(info) != [],
              destination.draggingUpdated(info) != []
        else { return ["accepted": false] }
        return ["accepted": destination.performDragOperation(info)]
    }

    private func choose(_ control: String, index: Int) throws -> Bool {
        guard control == "encoding_combo" else { throw AutomationError("No menu \(control)") }
        let popup = controller.controls.encodingPopup
        guard !popup.isHiddenOrHasHiddenAncestor, popup.isEnabled else { throw AutomationError("Menu is not available") }
        popup.selectItem(at: index)
        popup.sendAction(popup.action, to: popup.target)
        return true
    }

    /// Pick a menu bar item by its titles, as clicking through the menus does.
    private func chooseMenu(_ path: [String]) throws -> Bool {
        var menu = NSApp.mainMenu
        for (depth, title) in path.enumerated() {
            guard let current = menu, let index = current.items.firstIndex(where: { $0.title == title }) else {
                throw AutomationError("Menu item not found: \(path[...depth].joined(separator: " > "))")
            }
            if depth == path.count - 1 {
                DispatchQueue.main.async { current.performActionForItem(at: index) }
                return true
            }
            menu = current.items[index].submenu
        }
        throw AutomationError("Empty menu path")
    }

    private func answerDialog(text: String, accept: Bool) throws -> Bool {
        guard let sheet = window.attachedSheet, let content = sheet.contentView else {
            throw AutomationError("No dialog is open")
        }
        let field: NSSecureTextField? = descendants(of: content).first
        field?.stringValue = text
        let buttons: [NSButton] = descendants(of: content)
        let title = (accept ? L("확인", "OK") : L("취소", "Cancel")).string
        guard let button = buttons.first(where: { $0.title == title }) else {
            throw AutomationError("Dialog button not found")
        }
        DispatchQueue.main.async { button.performClick(nil) }
        return true
    }

    private func descendants<T: NSView>(of view: NSView) -> [T] {
        view.subviews.flatMap { ([$0] as? [T] ?? []) + descendants(of: $0) }
    }
}

/// The drag information AppKit would hand a destination view.
private final class AutomationDraggingInfo: NSObject, NSDraggingInfo {
    let draggingPasteboard: NSPasteboard
    let draggingLocation: NSPoint
    let draggingDestinationWindow: NSWindow?

    init(pasteboard: NSPasteboard, location: NSPoint, window: NSWindow) {
        draggingPasteboard = pasteboard
        draggingLocation = location
        draggingDestinationWindow = window
    }

    var draggingSourceOperationMask: NSDragOperation { .copy }
    var draggedImageLocation: NSPoint { draggingLocation }
    var draggedImage: NSImage? { nil }
    var draggingSource: Any? { nil }
    var draggingSequenceNumber: Int { 1 }
    var draggingFormation: NSDraggingFormation = .default
    var animatesToDestination = false
    var numberOfValidItemsForDrop = 1
    var springLoadingHighlight: NSSpringLoadingHighlight { .none }

    func slideDraggedImage(to screenPoint: NSPoint) {}
    func resetSpringLoading() {}

    func enumerateDraggingItems(
        options enumOpts: NSDraggingItemEnumerationOptions = [],
        for view: NSView?,
        classes classArray: [AnyClass],
        searchOptions: [NSPasteboard.ReadingOptionKey: Any] = [:],
        using block: (NSDraggingItem, Int, UnsafeMutablePointer<ObjCBool>) -> Void
    ) {}
}
