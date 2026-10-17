import AppKit
import ViewerCore

protocol DisplayControllerDelegate: AnyObject {
    func display(_ display: DisplayController, startedEntry entry: ImageEntry)
    func display(_ display: DisplayController, statusChanged message: String)
    func displayErrorsChanged(_ display: DisplayController)
    /// Ask for a ZipCrypto password; `nil` means the user cancelled.
    func display(_ display: DisplayController, passwordFor entry: ImageEntry, completion: @escaping (String?) -> Void)
}

/// Shows the current entry and keeps decoding results in order.
///
/// Each display request gets a token; any result that arrives for an older
/// token is dropped, so rapid navigation never shows a stale image.
final class DisplayController {
    weak var delegate: DisplayControllerDelegate?
    private let model: ViewerModel
    private let canvas: ImageCanvas
    private let decoder = ImageDecoder()
    private(set) var errors: [ImageEntry: String] = [:]
    private var passwords: [URL: Data] = [:]
    private var token = 0
    private var presentedToken = 0
    private var originalSize: CGSize = .zero
    private var isClosing = false
    private var upgradeWork: DispatchWorkItem?

    init(model: ViewerModel, canvas: ImageCanvas) {
        self.model = model
        self.canvas = canvas
        canvas.onViewChanged = { [weak self] in self?.scheduleUpgrade() }
        canvas.onAnimationFailed = { [weak self] message in
            guard let self, let entry = model.state.currentEntry else { return }
            self.showError(message, for: entry)
        }
    }

    func reset() {
        errors.removeAll()
        decoder.cancelPending()
        delegate?.displayErrorsChanged(self)
    }

    func beginShutdown() {
        isClosing = true
        token += 1
        decoder.cancelPending()
    }

    func issueMessages() -> [String] {
        errors.map { entry, message in "[display] \(entry.container.path) | \(entry.memberName)\n\(message)" }
            .sorted()
    }

    func showCurrent() {
        guard !isClosing, let entry = model.state.currentEntry else { return }
        token += 1
        let current = token
        upgradeWork?.cancel()
        decoder.cancelPending()
        delegate?.display(self, startedEntry: entry)

        if !entry.isAnimated, let cached = decoder.cached(entry, maxPixel: canvas.fitPixelSize) {
            present(.image(cached), for: entry)
            return
        }
        // Only show a loading message when decoding is noticeably slow.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) { [weak self] in
            guard let self, self.token == current, self.presentedToken != current else { return }
            self.canvas.showMessage("불러오는 중…")
        }
        withPassword(for: entry, token: current) { [weak self] password in
            guard let self else { return }
            self.decoder.decode(entry, maxPixel: self.canvas.fitPixelSize, password: password) { outcome in
                guard self.token == current, !self.isClosing else { return }
                self.present(outcome, for: entry)
            }
        }
    }

    // MARK: Presenting

    private func present(_ outcome: DecodeOutcome, for entry: ImageEntry) {
        presentedToken = token
        switch outcome {
        case .image(let decoded):
            originalSize = decoded.originalSize
            canvas.showImage(decoded.image, originalSize: decoded.originalSize, resetView: true)
            clearError(for: entry)
            schedulePreload()
            scheduleUpgrade()
        case .animation(let data, let size):
            originalSize = size
            canvas.playAnimation(data, originalSize: size)
            clearError(for: entry)
            schedulePreload()
        case .failure(let error):
            if error.kind == .wrongPassword {
                passwords.removeValue(forKey: entry.container)
            }
            showError(error.message, for: entry, kind: error.kind == .resourceLimit ? "자원 한도" : "오류")
        }
    }

    private func showError(_ message: String, for entry: ImageEntry, kind: String = "오류") {
        presentedToken = token
        originalSize = .zero
        errors[entry] = message
        canvas.showMessage("이미지를 열 수 없습니다\n\(entry.imageLabel)\n\(message)")
        delegate?.display(self, statusChanged: "\(model.state.positionLabel)  ·  \(kind)")
        delegate?.displayErrorsChanged(self)
    }

    private func clearError(for entry: ImageEntry) {
        delegate?.display(self, statusChanged: model.state.positionLabel)
        if errors.removeValue(forKey: entry) != nil {
            delegate?.displayErrorsChanged(self)
        }
    }

    // MARK: Passwords

    private func withPassword(for entry: ImageEntry, token current: Int, _ continuation: @escaping (Data?) -> Void) {
        guard entry.encryption == .zipCrypto else {
            continuation(nil)
            return
        }
        if let known = passwords[entry.container] {
            continuation(known)
            return
        }
        delegate?.display(self, passwordFor: entry) { [weak self] answer in
            guard let self, self.token == current else { return }
            guard let answer else {
                self.showError("ZIP 암호 입력을 취소했습니다.", for: entry)
                return
            }
            let password = Data(answer.utf8)
            self.passwords[entry.container] = password
            continuation(password)
        }
    }

    // MARK: Sharper renditions and preloading

    /// Load full resolution once the zoom needs more pixels than are shown.
    private func scheduleUpgrade() {
        upgradeWork?.cancel()
        guard canvas.hasImage, let entry = model.state.currentEntry, !entry.isAnimated else { return }
        let needed = canvas.requiredPixelScale * canvas.imagePointWidth
        let shown = CGFloat(canvas.displayedPixelWidth)
        guard shown < needed * 0.95, shown < originalSize.width else { return }
        let current = token
        let password = passwords[entry.container]
        let work = DispatchWorkItem { [weak self] in
            guard let self, self.token == current else { return }
            self.decoder.decode(entry, maxPixel: nil, password: password) { outcome in
                guard self.token == current, case .image(let decoded) = outcome else { return }
                self.canvas.replaceImage(decoded.image, originalSize: decoded.originalSize)
            }
        }
        upgradeWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2, execute: work)
    }

    private func schedulePreload() {
        let state = model.state
        guard state.entries.count > 1 else { return }
        for offset in [1, 2, -1] {
            let index = (state.currentIndex + offset + state.entries.count) % state.entries.count
            let entry = state.entries[index]
            if entry.isAnimated || entry == state.currentEntry { continue }
            if entry.encryption == .aes { continue }
            let password = passwords[entry.container]
            if entry.encryption == .zipCrypto && password == nil { continue }
            if decoder.cached(entry, maxPixel: canvas.fitPixelSize) != nil { continue }
            decoder.decode(entry, maxPixel: canvas.fitPixelSize, password: password) { _ in }
        }
    }
}
