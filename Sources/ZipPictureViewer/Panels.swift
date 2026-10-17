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
        isReleasedWhenClosed = false
        textView.isEditable = false
        textView.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        let scroll = NSScrollView()
        scroll.documentView = textView
        scroll.hasVerticalScroller = true
        textView.autoresizingMask = [.width]
        let copy = NSButton(title: "", target: self, action: #selector(copyAll))
        let retry = NSButton(title: "", target: self, action: #selector(retry))
        let buttons = NSStackView(views: [copy, retry])
        let column = NSStackView(views: [scroll, buttons])
        column.orientation = .vertical
        column.edgeInsets = NSEdgeInsets(top: 10, left: 10, bottom: 10, right: 10)
        contentView = column
        center()
        Localization.shared.observe { [weak self] in
            self?.title = Self.windowTitle.string
            copy.title = L("전체 복사", "Copy All").string
            retry.title = L("다시 스캔", "Rescan").string
        }
    }

    static let windowTitle = L("읽지 못한 항목", "Unreadable Items")

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
    static let windowTitle = L("단축키 도움말", "Keyboard Shortcuts")

    private static let shortcuts: [(LocalizedText, LocalizedText)] = [
        (LocalizedText(verbatim: "← / →, Space"), L("이전 / 다음 이미지", "Previous / next image")),
        (LocalizedText(verbatim: "↑ / ↓"), L("이전 / 다음 묶음", "Previous / next set")),
        (LocalizedText(verbatim: "⌘↑ / ⌘↓"), L("이전 / 다음 형제 폴더 또는 아카이브", "Previous / next sibling folder or archive")),
        (LocalizedText(verbatim: "O / ⌘O"), L("폴더 열기", "Open folder")),
        (LocalizedText(verbatim: "⇧⌘O"), L("ZIP/CBZ 열기", "Open ZIP/CBZ")),
        (LocalizedText(verbatim: "R"), L("새로고침", "Refresh")),
        (LocalizedText(verbatim: "0 / 1"), L("화면 맞춤 / 100%", "Fit / 100%")),
        (L("+ / −, 핀치", "+ / −, pinch"), L("확대 / 축소", "Zoom in / out")),
        (L("더블클릭", "Double-click"), L("화면 맞춤 / 100% 전환", "Toggle fit / 100%")),
        (LocalizedText(verbatim: "F, ⌃⌘F"), L("전체화면", "Full screen")),
        (LocalizedText(verbatim: "Esc"), L("전체화면 종료", "Leave full screen")),
        (LocalizedText(verbatim: "?"), L("이 도움말", "This help")),
    ]

    init() {
        super.init(
            contentRect: NSRect(x: 0, y: 0, width: 360, height: 320),
            styleMask: [.titled, .closable, .utilityWindow],
            backing: .buffered,
            defer: true
        )
        isReleasedWhenClosed = false
        let labels = Self.shortcuts.map { _ in [NSTextField(labelWithString: ""), NSTextField(labelWithString: "")] }
        let grid = NSGridView(views: labels)
        grid.rowSpacing = 6
        grid.columnSpacing = 16
        let container = NSStackView(views: [grid])
        container.edgeInsets = NSEdgeInsets(top: 14, left: 16, bottom: 14, right: 16)
        contentView = container
        center()
        Localization.shared.observe { [weak self] in
            self?.title = Self.windowTitle.string
            for (row, (key, action)) in zip(labels, Self.shortcuts) {
                row[0].stringValue = key.string
                row[1].stringValue = action.string
            }
            // Fit the window to the rows; a taller window leaves gaps between them.
            self?.setContentSize(container.fittingSize)
        }
    }
}

/// Asks for a ZipCrypto password in a sheet so the window stays responsive.
enum PasswordPrompt {
    static let title = L("ZIP 암호", "ZIP Password")

    static func ask(for archiveName: String, on window: NSWindow, completion: @escaping (String?) -> Void) {
        let alert = NSAlert()
        alert.messageText = title.string
        alert.informativeText = L("\(archiveName)의 암호를 입력하세요.", "Enter the password for \(archiveName).").string
        alert.addButton(withTitle: L("확인", "OK").string)
        alert.addButton(withTitle: L("취소", "Cancel").string)
        let field = NSSecureTextField(frame: NSRect(x: 0, y: 0, width: 240, height: 24))
        alert.accessoryView = field
        alert.window.title = title.string
        alert.window.initialFirstResponder = field
        alert.beginSheetModal(for: window) { response in
            completion(response == .alertFirstButtonReturn ? field.stringValue : nil)
        }
    }
}
