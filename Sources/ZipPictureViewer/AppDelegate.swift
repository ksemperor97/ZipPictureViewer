import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    private let launch: LaunchOptions
    private var windowController: MainWindowController?
    private var automation: AutomationServer?
    /// Files Finder asked us to open before the window existed.
    private var pendingOpen: URL?

    init(launch: LaunchOptions) {
        self.launch = launch
    }

    func applicationWillFinishLaunching(_ notification: Notification) {
        Localization.shared.observe { NSApp.mainMenu = MainMenu.build() }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let controller = MainWindowController()
        windowController = controller
        controller.showWindow(nil)
        controller.window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        if let handshake = launch.automationHandshake {
            do {
                automation = try AutomationServer(controller: controller, handshake: handshake)
            } catch {
                NSLog("Automation failed to start: %@", String(describing: error))
                exit(2)
            }
        }
        if let url = pendingOpen ?? launch.startupPath {
            controller.opener.open(url)
        } else {
            controller.opener.scheduleRestore()
        }
        pendingOpen = nil
    }

    /// Finder "Open With", Dock drops and `open -a` deliver files here.
    func application(_ application: NSApplication, open urls: [URL]) {
        guard let url = urls.first else { return }
        guard let controller = windowController else {
            pendingOpen = url
            return
        }
        controller.opener.open(url)
        controller.window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    // MARK: Menu actions

    @objc func openFolder(_ sender: Any?) { windowController?.perform(.openFolder) }
    @objc func openArchive(_ sender: Any?) { windowController?.perform(.openArchive) }
    @objc func refreshSource(_ sender: Any?) { windowController?.perform(.refresh) }
    @objc func fitImage(_ sender: Any?) { windowController?.perform(.fit) }
    @objc func actualSize(_ sender: Any?) { windowController?.perform(.actualSize) }
    @objc func zoomIn(_ sender: Any?) { windowController?.perform(.zoomIn) }
    @objc func zoomOut(_ sender: Any?) { windowController?.perform(.zoomOut) }
    @objc func showIssues(_ sender: Any?) { windowController?.perform(.issues) }
    @objc func showHelp(_ sender: Any?) { windowController?.perform(.help) }

    @objc func chooseLanguage(_ sender: NSMenuItem) {
        guard let raw = sender.representedObject as? String, let language = AppLanguage(rawValue: raw) else { return }
        Localization.shared.setPreference(language)
    }
}

/// Command-line options. AppKit's own `-NS…`/`-psn_…` arguments are ignored.
struct LaunchOptions {
    var automationHandshake: URL?
    var startupPath: URL?
    var smokeTest = false

    init(arguments: [String]) {
        var remaining = arguments.dropFirst()[...]
        while let argument = remaining.popFirst() {
            if argument == "--smoke-test" {
                smokeTest = true
            } else if argument == "--automation-handshake", let value = remaining.popFirst() {
                automationHandshake = URL(fileURLWithPath: value)
            } else if argument.hasPrefix("-") {
                // "-Key value" sets a user default for this run (e.g.
                // -AppLanguage en); macOS's own "-psn_…" has no value.
                if !argument.hasPrefix("--"), !argument.hasPrefix("-psn_"), !remaining.isEmpty {
                    remaining.removeFirst()
                }
            } else if startupPath == nil {
                startupPath = URL(fileURLWithPath: argument)
            }
        }
    }
}

enum MainMenu {
    /// Rebuilt whenever the language changes.
    static func build() -> NSMenu {
        let main = NSMenu()
        let appName = "ZipPictureViewer"
        main.addItem(submenu(LocalizedText(verbatim: appName), [
            item(L("\(appName) 정보", "About \(appName)"), #selector(NSApplication.orderFrontStandardAboutPanel(_:)), ""),
            .separator(),
            languageMenu(),
            .separator(),
            item(L("\(appName) 가리기", "Hide \(appName)"), #selector(NSApplication.hide(_:)), "h"),
            item(L("\(appName) 종료", "Quit \(appName)"), #selector(NSApplication.terminate(_:)), "q"),
        ]))
        main.addItem(submenu(L("파일", "File"), [
            item(L("폴더 열기…", "Open Folder…"), #selector(AppDelegate.openFolder(_:)), "o"),
            item(L("ZIP/CBZ 열기…", "Open ZIP/CBZ…"), #selector(AppDelegate.openArchive(_:)), "O"),
            item(L("새로고침", "Refresh"), #selector(AppDelegate.refreshSource(_:)), "r"),
            .separator(),
            item(L("창 닫기", "Close Window"), #selector(NSWindow.performClose(_:)), "w"),
        ]))
        main.addItem(submenu(L("보기", "View"), [
            item(L("화면 맞춤", "Fit to Window"), #selector(AppDelegate.fitImage(_:)), "0"),
            item(L("실제 크기", "Actual Size"), #selector(AppDelegate.actualSize(_:)), "1"),
            item(L("확대", "Zoom In"), #selector(AppDelegate.zoomIn(_:)), "+"),
            item(L("축소", "Zoom Out"), #selector(AppDelegate.zoomOut(_:)), "-"),
            .separator(),
            item(IssuePanel.windowTitle, #selector(AppDelegate.showIssues(_:)), ""),
            fullScreenItem(),
        ]))
        main.addItem(submenu(L("도움말", "Help"), [item(HelpPanel.windowTitle, #selector(AppDelegate.showHelp(_:)), "?")]))
        return main
    }

    /// Named in both languages so it can be found whichever is active.
    static let languageTitle = "언어 (Language)"

    private static func languageMenu() -> NSMenuItem {
        let choices: [(AppLanguage, String)] = [
            (.system, L("시스템 설정 따름", "System Default").string),
            (.korean, "한국어"),
            (.english, "English"),
        ]
        let items = choices.map { language, title -> NSMenuItem in
            let item = NSMenuItem(title: title, action: #selector(AppDelegate.chooseLanguage(_:)), keyEquivalent: "")
            item.representedObject = language.rawValue
            item.state = Localization.shared.preference == language ? .on : .off
            return item
        }
        return submenu(LocalizedText(verbatim: languageTitle), items)
    }

    private static func submenu(_ title: LocalizedText, _ items: [NSMenuItem]) -> NSMenuItem {
        let container = NSMenuItem(title: title.string, action: nil, keyEquivalent: "")
        let menu = NSMenu(title: title.string)
        items.forEach(menu.addItem)
        container.submenu = menu
        return container
    }

    private static func item(_ title: LocalizedText, _ action: Selector, _ key: String) -> NSMenuItem {
        NSMenuItem(title: title.string, action: action, keyEquivalent: key)
    }

    private static func fullScreenItem() -> NSMenuItem {
        let item = NSMenuItem(title: L("전체 화면", "Enter Full Screen").string, action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f")
        item.keyEquivalentModifierMask = [.command, .control]
        return item
    }
}
