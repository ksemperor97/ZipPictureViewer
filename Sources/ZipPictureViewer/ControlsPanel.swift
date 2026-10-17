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
/// Compact mode shows the everyday buttons; "More" reveals the rest.
final class ControlsPanel: NSVisualEffectView {
    var onCommand: ((ViewerCommand) -> Void)?
    var onEncodingChange: ((NameEncoding) -> Void)?

    /// Buttons by the automation name used in tests (e.g. "next_button").
    private(set) var buttons: [String: NSButton] = [:]
    let statusLabel = NSTextField(labelWithString: "")
    let encodingPopup = NSPopUpButton()
    private let secondaryRow = NSStackView()
    private(set) var isExpanded = false
    private var status = L("폴더 또는 ZIP 열기", "Open a folder or ZIP")
    private var issueCount = 0
    private var isFullscreen = false

    private static let compact: [(String, LocalizedText, ViewerCommand?)] = [
        ("open_button", L("폴더 열기", "Open Folder"), .openFolder),
        ("previous_button", L("← 이전", "← Previous"), .previous),
        ("next_button", L("다음 →", "Next →"), .next),
        ("close_button", L("닫기", "Close"), .close),
        ("expand_button", L("펼치기", "More"), nil),
    ]
    private static let secondary: [(String, LocalizedText, ViewerCommand)] = [
        ("open_archive_button", L("ZIP 열기", "Open ZIP"), .openArchive),
        ("previous_folder_button", L("이전 폴더", "Previous Folder"), .previousFolder),
        ("next_folder_button", L("다음 폴더", "Next Folder"), .nextFolder),
        ("previous_archive_button", L("↑ 이전 묶음", "↑ Previous Set"), .previousBundle),
        ("next_archive_button", L("↓ 다음 묶음", "↓ Next Set"), .nextBundle),
        ("refresh_button", L("새로고침", "Refresh"), .refresh),
        ("fit_button", L("화면 맞춤", "Fit"), .fit),
        ("actual_size_button", LocalizedText(verbatim: "100%"), .actualSize),
        ("zoom_out_button", L("축소 −", "Zoom Out −"), .zoomOut),
        ("zoom_in_button", L("확대 +", "Zoom In +"), .zoomIn),
        ("fullscreen_button", L("전체화면", "Full Screen"), .fullscreen),
        ("issues_button", L("오류", "Issues"), .issues),
        ("help_button", L("도움말", "Help"), .help),
        ("cancel_scan_button", L("스캔 취소", "Cancel Scan"), .cancelScan),
        ("minimize_button", L("최소화", "Minimize"), .minimize),
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
            encodingPopup.addItem(withTitle: encoding.rawValue)
            encodingPopup.lastItem?.representedObject = encoding.rawValue
        }
        encodingPopup.target = self
        encodingPopup.action = #selector(encodingChosen)
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
        Localization.shared.observe { [weak self] in self?.relabel() }
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    func button(_ name: String) -> NSButton? { buttons[name] }

    func setScanning(_ scanning: Bool) {
        buttons["cancel_scan_button"]?.isEnabled = scanning
        buttons["open_button"]?.isEnabled = !scanning
        buttons["open_archive_button"]?.isEnabled = !scanning
        encodingPopup.isEnabled = !scanning
    }

    func setStatus(_ text: LocalizedText) {
        status = text
        statusLabel.stringValue = text.string
    }

    func setIssueCount(_ count: Int) {
        issueCount = count
        buttons["issues_button"]?.isEnabled = count > 0
        relabel()
    }

    func setEnabled(_ enabled: Bool, for names: [String]) {
        names.forEach { buttons[$0]?.isEnabled = enabled }
    }

    func selectEncoding(_ encoding: NameEncoding) {
        encodingPopup.selectItem(at: NameEncoding.allCases.firstIndex(of: encoding) ?? 0)
    }

    func setFullscreenTitle(_ fullscreen: Bool) {
        isFullscreen = fullscreen
        relabel()
    }

    func toggleExpanded() {
        isExpanded.toggle()
        secondaryRow.isHidden = !isExpanded
        relabel()
    }

    /// Apply the current language to every title, including state-dependent ones.
    private func relabel() {
        for (name, title, _) in Self.compact { buttons[name]?.title = title.string }
        for (name, title, _) in Self.secondary { buttons[name]?.title = title.string }
        buttons["issues_button"]?.title = "\(L("오류", "Issues").string) \(issueCount)"
        if isFullscreen { buttons["fullscreen_button"]?.title = L("창모드", "Window").string }
        if isExpanded { buttons["expand_button"]?.title = L("접기", "Less").string }
        for (index, encoding) in NameEncoding.allCases.enumerated() {
            encodingPopup.item(at: index)?.title = "\(L("ZIP 이름", "ZIP names").string): \(Self.title(for: encoding).string)"
        }
        encodingPopup.toolTip = L("현재 ZIP의 파일명 인코딩", "File name encoding of the current ZIP").string
        statusLabel.stringValue = status.string
    }

    private func makeButton(_ name: String, _ title: LocalizedText, _ command: ViewerCommand?) -> NSButton {
        let button = NSButton(title: title.string, target: self, action: #selector(buttonPressed(_:)))
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

    private static func title(for encoding: NameEncoding) -> LocalizedText {
        switch encoding {
        case .auto: return L("자동", "Automatic")
        case .cp949: return LocalizedText(verbatim: "CP949")
        case .cp437: return LocalizedText(verbatim: "CP437")
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
