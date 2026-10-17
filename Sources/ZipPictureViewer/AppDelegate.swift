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
        NSApp.mainMenu = MainMenu.build()
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
                // AppKit options such as -NSDocumentRevisionsDebugMode take a value.
                if argument.hasPrefix("-NS"), !remaining.isEmpty { remaining.removeFirst() }
            } else if startupPath == nil {
                startupPath = URL(fileURLWithPath: argument)
            }
        }
    }
}

enum MainMenu {
    static func build() -> NSMenu {
        let main = NSMenu()
        let appName = "Zip Picture Viewer"
        main.addItem(submenu("ZipPictureViewer", [
            item("\(appName) 정보", #selector(NSApplication.orderFrontStandardAboutPanel(_:)), ""),
            .separator(),
            item("\(appName) 가리기", #selector(NSApplication.hide(_:)), "h"),
            item("\(appName) 종료", #selector(NSApplication.terminate(_:)), "q"),
        ]))
        main.addItem(submenu("파일", [
            item("폴더 열기…", #selector(AppDelegate.openFolder(_:)), "o"),
            item("ZIP/CBZ 열기…", #selector(AppDelegate.openArchive(_:)), "O"),
            item("새로고침", #selector(AppDelegate.refreshSource(_:)), "r"),
            .separator(),
            item("창 닫기", #selector(NSWindow.performClose(_:)), "w"),
        ]))
        main.addItem(submenu("보기", [
            item("화면 맞춤", #selector(AppDelegate.fitImage(_:)), "0"),
            item("실제 크기", #selector(AppDelegate.actualSize(_:)), "1"),
            item("확대", #selector(AppDelegate.zoomIn(_:)), "+"),
            item("축소", #selector(AppDelegate.zoomOut(_:)), "-"),
            .separator(),
            item("읽지 못한 항목", #selector(AppDelegate.showIssues(_:)), ""),
            fullScreenItem(),
        ]))
        main.addItem(submenu("도움말", [item("단축키 도움말", #selector(AppDelegate.showHelp(_:)), "?")]))
        return main
    }

    private static func submenu(_ title: String, _ items: [NSMenuItem]) -> NSMenuItem {
        let container = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        let menu = NSMenu(title: title)
        items.forEach(menu.addItem)
        container.submenu = menu
        return container
    }

    private static func item(_ title: String, _ action: Selector, _ key: String) -> NSMenuItem {
        NSMenuItem(title: title, action: action, keyEquivalent: key)
    }

    private static func fullScreenItem() -> NSMenuItem {
        let item = NSMenuItem(title: "전체 화면", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f")
        item.keyEquivalentModifierMask = [.command, .control]
        return item
    }
}
