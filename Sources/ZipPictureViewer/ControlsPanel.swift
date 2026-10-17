import AppKit
import ViewerCore

/// Every viewer command a control or shortcut can trigger.
enum ViewerCommand {
    case openFolder, openArchive, previous, next, previousBundle, nextBundle
    case previousFolder, nextFolder, refresh, cancelScan
    case fit, actualSize, zoomIn, zoomOut, fullscreen, exitFullscreen, help, issues, minimize, close
}

/// Floating HUD with the viewer's buttons and status.
///
/// Compact mode shows the everyday buttons; "펼치기" reveals the rest.
final class ControlsPanel: NSVisualEffectView {
    var onCommand: ((ViewerCommand) -> Void)?
    var onEncodingChange: ((NameEncoding) -> Void)?

    /// Buttons by the automation name used in tests (e.g. "next_button").
    private(set) var buttons: [String: NSButton] = [:]
    let statusLabel = NSTextField(labelWithString: "폴더 또는 ZIP 열기")
    let encodingPopup = NSPopUpButton()
    private let secondaryRow = NSStackView()
    private(set) var isExpanded = false

    private static let compact: [(String, String, ViewerCommand?)] = [
        ("open_button", "폴더 열기", .openFolder),
        ("previous_button", "← 이전", .previous),
        ("next_button", "다음 →", .next),
        ("close_button", "닫기", .close),
        ("expand_button", "펼치기", nil),
    ]
    private static let secondary: [(String, String, ViewerCommand)] = [
        ("open_archive_button", "ZIP 열기", .openArchive),
        ("previous_folder_button", "이전 폴더", .previousFolder),
        ("next_folder_button", "다음 폴더", .nextFolder),
        ("previous_archive_button", "↑ 이전 묶음", .previousBundle),
        ("next_archive_button", "↓ 다음 묶음", .nextBundle),
        ("refresh_button", "새로고침", .refresh),
        ("fit_button", "화면 맞춤", .fit),
        ("actual_size_button", "100%", .actualSize),
        ("zoom_out_button", "축소 −", .zoomOut),
        ("zoom_in_button", "확대 +", .zoomIn),
        ("fullscreen_button", "전체화면", .fullscreen),
        ("issues_button", "오류 0", .issues),
        ("help_button", "도움말", .help),
        ("cancel_scan_button", "스캔 취소", .cancelScan),
        ("minimize_button", "최소화", .minimize),
    ]

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        material = .hudWindow
        blendingMode = .withinWindow
        state = .active
        wantsLayer = true
        layer?.cornerRadius = 10
        translatesAutoresizingMaskIntoConstraints = false

        let primaryRow = NSStackView(views: [statusLabel] + Self.compact.map { makeButton($0.0, $0.1, $0.2) })
        statusLabel.textColor = .white
        statusLabel.font = .monospacedDigitSystemFont(ofSize: 12, weight: .regular)
        statusLabel.lineBreakMode = .byTruncatingTail
        statusLabel.widthAnchor.constraint(greaterThanOrEqualToConstant: 90).isActive = true
        for encoding in NameEncoding.allCases {
            encodingPopup.addItem(withTitle: "ZIP 이름: \(Self.title(for: encoding))")
            encodingPopup.lastItem?.representedObject = encoding.rawValue
        }
        encodingPopup.target = self
        encodingPopup.action = #selector(encodingChosen)
        encodingPopup.toolTip = "현재 ZIP의 파일명 인코딩"
        secondaryRow.setViews(Self.secondary.map { makeButton($0.0, $0.1, $0.2) } + [encodingPopup], in: .leading)
        secondaryRow.isHidden = true
        for row in [primaryRow, secondaryRow] {
            row.spacing = 6
            row.orientation = .horizontal
        }
        let column = NSStackView(views: [primaryRow, secondaryRow])
        column.orientation = .vertical
        column.alignment = .leading
        column.spacing = 6
        column.edgeInsets = NSEdgeInsets(top: 8, left: 10, bottom: 8, right: 10)
        column.translatesAutoresizingMaskIntoConstraints = false
        addSubview(column)
        NSLayoutConstraint.activate([
            column.leadingAnchor.constraint(equalTo: leadingAnchor),
            column.trailingAnchor.constraint(equalTo: trailingAnchor),
            column.topAnchor.constraint(equalTo: topAnchor),
            column.bottomAnchor.constraint(equalTo: bottomAnchor),
        ])
        setScanning(false)
        setIssueCount(0)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    func button(_ name: String) -> NSButton? { buttons[name] }

    func setScanning(_ scanning: Bool) {
        buttons["cancel_scan_button"]?.isEnabled = scanning
        buttons["open_button"]?.isEnabled = !scanning
        buttons["open_archive_button"]?.isEnabled = !scanning
        encodingPopup.isEnabled = !scanning
    }

    func setIssueCount(_ count: Int) {
        buttons["issues_button"]?.title = "오류 \(count)"
        buttons["issues_button"]?.isEnabled = count > 0
    }

    func setEnabled(_ enabled: Bool, for names: [String]) {
        names.forEach { buttons[$0]?.isEnabled = enabled }
    }

    func selectEncoding(_ encoding: NameEncoding) {
        encodingPopup.selectItem(at: NameEncoding.allCases.firstIndex(of: encoding) ?? 0)
    }

    func setFullscreenTitle(_ fullscreen: Bool) {
        buttons["fullscreen_button"]?.title = fullscreen ? "창모드" : "전체화면"
    }

    func toggleExpanded() {
        isExpanded.toggle()
        secondaryRow.isHidden = !isExpanded
        buttons["expand_button"]?.title = isExpanded ? "접기" : "펼치기"
    }

    private func makeButton(_ name: String, _ title: String, _ command: ViewerCommand?) -> NSButton {
        let button = NSButton(title: title, target: self, action: #selector(buttonPressed(_:)))
        button.bezelStyle = .rounded
        button.controlSize = .small
        button.identifier = NSUserInterfaceItemIdentifier(name)
        buttons[name] = button
        if let command { commands[name] = command }
        return button
    }

    private var commands: [String: ViewerCommand] = [:]

    @objc private func buttonPressed(_ sender: NSButton) {
        guard let name = sender.identifier?.rawValue else { return }
        if name == "expand_button" {
            toggleExpanded()
        } else if let command = commands[name] {
            onCommand?(command)
        }
    }

    @objc private func encodingChosen() {
        guard let raw = encodingPopup.selectedItem?.representedObject as? String,
              let encoding = NameEncoding(rawValue: raw)
        else { return }
        onEncodingChange?(encoding)
    }

    private static func title(for encoding: NameEncoding) -> String {
        switch encoding {
        case .auto: return "자동"
        case .cp949: return "CP949"
        case .cp437: return "CP437"
        }
    }
}

/// The file path label shown above the image.
final class InfoPanel: NSVisualEffectView {
    let label = NSTextField(labelWithString: "")

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        material = .hudWindow
        blendingMode = .withinWindow
        state = .active
        wantsLayer = true
        layer?.cornerRadius = 8
        translatesAutoresizingMaskIntoConstraints = false
        label.textColor = .white
        label.font = .systemFont(ofSize: 12)
        label.lineBreakMode = .byTruncatingMiddle
        label.translatesAutoresizingMaskIntoConstraints = false
        addSubview(label)
        NSLayoutConstraint.activate([
            label.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 10),
            label.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -10),
            label.topAnchor.constraint(equalTo: topAnchor, constant: 6),
            label.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -6),
        ])
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    var text: String {
        get { label.stringValue }
        set {
            label.stringValue = newValue
            label.toolTip = newValue
        }
    }
}
