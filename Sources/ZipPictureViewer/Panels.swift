import AppKit

/// Non-blocking list of everything that could not be read.
final class IssuePanel: NSPanel {
    var onRetry: (() -> Void)?
    private let textView = NSTextView()

    init() {
        super.init(
            contentRect: NSRect(x: 0, y: 0, width: 620, height: 380),
            styleMask: [.titled, .closable, .resizable, .utilityWindow],
            backing: .buffered,
            defer: true
        )
        title = "읽지 못한 항목"
        isReleasedWhenClosed = false
        textView.isEditable = false
        textView.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        let scroll = NSScrollView()
        scroll.documentView = textView
        scroll.hasVerticalScroller = true
        textView.autoresizingMask = [.width]
        let copy = NSButton(title: "전체 복사", target: self, action: #selector(copyAll))
        let retry = NSButton(title: "다시 스캔", target: self, action: #selector(retry))
        let buttons = NSStackView(views: [copy, retry])
        let column = NSStackView(views: [scroll, buttons])
        column.orientation = .vertical
        column.edgeInsets = NSEdgeInsets(top: 10, left: 10, bottom: 10, right: 10)
        contentView = column
        center()
    }

    func setMessages(_ messages: [String]) {
        textView.string = messages.joined(separator: "\n\n")
    }

    @objc private func copyAll() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(textView.string, forType: .string)
    }

    @objc private func retry() { onRetry?() }
}

final class HelpPanel: NSPanel {
    private static let shortcuts = [
        ("← / →, Space", "이전 / 다음 이미지"),
        ("↑ / ↓", "이전 / 다음 묶음"),
        ("⌘↑ / ⌘↓", "이전 / 다음 형제 폴더 또는 아카이브"),
        ("O / ⌘O", "폴더 열기"),
        ("⇧⌘O", "ZIP/CBZ 열기"),
        ("R", "새로고침"),
        ("0 / 1", "화면 맞춤 / 100%"),
        ("+ / −, 핀치", "확대 / 축소"),
        ("더블클릭", "화면 맞춤 / 100% 전환"),
        ("F, ⌃⌘F", "전체화면"),
        ("Esc", "전체화면 종료"),
        ("?", "이 도움말"),
    ]

    init() {
        super.init(
            contentRect: NSRect(x: 0, y: 0, width: 360, height: 320),
            styleMask: [.titled, .closable, .utilityWindow],
            backing: .buffered,
            defer: true
        )
        title = "단축키 도움말"
        isReleasedWhenClosed = false
        let grid = NSGridView(views: Self.shortcuts.map { key, action in
            [NSTextField(labelWithString: key), NSTextField(labelWithString: action)]
        })
        grid.rowSpacing = 6
        grid.columnSpacing = 16
        let container = NSStackView(views: [grid])
        container.edgeInsets = NSEdgeInsets(top: 14, left: 16, bottom: 14, right: 16)
        contentView = container
        center()
    }
}

/// Asks for a ZipCrypto password in a sheet so the window stays responsive.
enum PasswordPrompt {
    static func ask(for archiveName: String, on window: NSWindow, completion: @escaping (String?) -> Void) {
        let alert = NSAlert()
        alert.messageText = "ZIP 암호"
        alert.informativeText = "\(archiveName)의 암호를 입력하세요."
        alert.addButton(withTitle: "확인")
        alert.addButton(withTitle: "취소")
        let field = NSSecureTextField(frame: NSRect(x: 0, y: 0, width: 240, height: 24))
        alert.accessoryView = field
        alert.window.title = "ZIP 암호"
        alert.window.initialFirstResponder = field
        alert.beginSheetModal(for: window) { response in
            completion(response == .alertFirstButtonReturn ? field.stringValue : nil)
        }
    }
}
