import AppKit
import ImageIO

/// Scrollable, zoomable image surface. 100% means one image pixel per point.
final class ImageCanvas: NSScrollView {
    var onFitRequested: (() -> Void)?
    var onActualSizeRequested: (() -> Void)?
    /// Called when zoom or viewport changes so a sharper image can be loaded.
    var onViewChanged: (() -> Void)?
    /// Called with the ImageIO status code when GIF playback cannot start.
    var onAnimationFailed: ((Int) -> Void)?

    private let imageView = NSImageView()
    private let messageLabel = NSTextField(labelWithString: "")
    private(set) var fitMode = true
    private(set) var hasImage = false
    private var messageText: LocalizedText?
    private var animation: AnimationToken?

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        contentView = CenteringClipView()
        drawsBackground = true
        backgroundColor = NSColor(calibratedWhite: 0.09, alpha: 1)
        hasVerticalScroller = false
        hasHorizontalScroller = false
        allowsMagnification = true
        minMagnification = 0.02
        maxMagnification = 32
        imageView.imageScaling = .scaleAxesIndependently
        imageView.animates = false
        documentView = imageView
        messageLabel.textColor = NSColor(calibratedWhite: 0.96, alpha: 1)
        messageLabel.alignment = .center
        messageLabel.font = .systemFont(ofSize: 15)
        messageLabel.maximumNumberOfLines = 0
        addSubview(messageLabel)
        showMessage(L("폴더 열기 또는 드래그", "Open a folder or drop one here"))
        Localization.shared.observe { [weak self] in
            guard let self, let text = self.messageText else { return }
            self.messageLabel.stringValue = text.string
            self.layoutMessage()
        }
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    override var acceptsFirstResponder: Bool { true }

    var message: String { messageLabel.isHidden ? "" : messageLabel.stringValue }

    /// Longest side, in pixels, needed to fill the viewport in fit mode.
    var fitPixelSize: Int {
        let scale = window?.backingScaleFactor ?? 2
        return Int(max(bounds.width, bounds.height) * scale)
    }

    /// Pixels per image point currently needed to stay sharp.
    var requiredPixelScale: CGFloat { magnification * (window?.backingScaleFactor ?? 2) }

    var displayedPixelWidth: Int { (imageView.image?.representations.first?.pixelsWide) ?? 0 }
    var imagePointWidth: CGFloat { imageView.frame.width }

    // MARK: Content

    func showImage(_ image: CGImage, originalSize: CGSize, resetView: Bool) {
        stopAnimation()
        imageView.image = NSImage(cgImage: image, size: originalSize)
        imageView.frame = NSRect(origin: .zero, size: originalSize)
        hasImage = true
        messageLabel.isHidden = true
        imageView.isHidden = false
        if resetView || fitMode { fit() }
    }

    /// Swap in a sharper rendition without moving the view.
    func replaceImage(_ image: CGImage, originalSize: CGSize) {
        guard hasImage, imageView.frame.size == originalSize else { return }
        imageView.image = NSImage(cgImage: image, size: originalSize)
    }

    func playAnimation(_ data: Data, originalSize: CGSize) {
        stopAnimation()
        imageView.frame = NSRect(origin: .zero, size: originalSize)
        hasImage = true
        messageLabel.isHidden = true
        imageView.isHidden = false
        fit()
        let token = AnimationToken()
        animation = token
        let status = CGAnimateImageDataWithBlock(data as CFData, nil) { [weak self] _, frame, shouldStop in
            if token.stopped {
                shouldStop.pointee = true
                return
            }
            self?.imageView.image = NSImage(cgImage: frame, size: originalSize)
        }
        if status != noErr {
            onAnimationFailed?(Int(status))
        }
    }

    var isAnimating: Bool { animation.map { !$0.stopped } ?? false }

    /// NSScrollView lays out its own subviews, so the message is placed here
    /// (Auto Layout constraints on it never produced a visible frame).
    override func tile() {
        super.tile()
        layoutMessage()
    }

    private func layoutMessage() {
        let available = NSSize(width: max(bounds.width - 40, 1), height: bounds.height)
        let size = messageLabel.sizeThatFits(available)
        messageLabel.frame = NSRect(
            x: (bounds.width - size.width) / 2,
            y: (bounds.height - size.height) / 2,
            width: size.width,
            height: size.height
        ).integral
    }

    func showMessage(_ text: LocalizedText) {
        messageText = text
        stopAnimation()
        imageView.image = nil
        imageView.isHidden = true
        hasImage = false
        messageLabel.stringValue = text.string
        messageLabel.isHidden = false
        layoutMessage()
        fitMode = true
        magnification = 1
    }

    private func stopAnimation() {
        animation?.stopped = true
        animation = nil
    }

    // MARK: Zoom

    func fit() {
        fitMode = true
        guard hasImage else { return }
        let size = imageView.frame.size
        guard size.width > 0, size.height > 0, bounds.width > 0, bounds.height > 0 else { return }
        let scale = min(bounds.width / size.width, bounds.height / size.height)
        magnification = min(max(scale, minMagnification), maxMagnification)
        onViewChanged?()
    }

    func requestFit() {
        fit()
        onFitRequested?()
    }

    func actualSize() {
        guard hasImage else { return }
        fitMode = false
        setMagnification(1, centeredAt: NSPoint(x: imageView.frame.midX, y: imageView.frame.midY))
        onActualSizeRequested?()
        onViewChanged?()
    }

    func zoom(by factor: CGFloat) {
        guard hasImage else { return }
        fitMode = false
        let center = NSPoint(x: contentView.bounds.midX, y: contentView.bounds.midY)
        setMagnification(min(max(magnification * factor, minMagnification), maxMagnification), centeredAt: center)
        onViewChanged?()
    }

    override func magnify(with event: NSEvent) {
        fitMode = false
        super.magnify(with: event)
        onViewChanged?()
    }

    override func setFrameSize(_ newSize: NSSize) {
        super.setFrameSize(newSize)
        if fitMode { fit() }
    }

    // MARK: Mouse and keys

    override func mouseDown(with event: NSEvent) {
        window?.makeFirstResponder(self)
        if event.clickCount == 2 {
            fitMode ? actualSize() : requestFit()
            return
        }
        // In fit mode the image area moves the window, like a title bar.
        if fitMode, let window, !window.styleMask.contains(.fullScreen) {
            window.performDrag(with: event)
            return
        }
        super.mouseDown(with: event)
    }

    /// Rendered colour at a fractional position, as "#rrggbb" in sRGB.
    ///
    /// The view is drawn into an sRGB bitmap so the answer does not depend
    /// on the attached display's colour profile.
    func renderedColor(atX x: CGFloat, y: CGFloat) -> String {
        let scale = window?.backingScaleFactor ?? 2
        guard let rep = NSBitmapImageRep(
            bitmapDataPlanes: nil,
            pixelsWide: max(Int(bounds.width * scale), 1),
            pixelsHigh: max(Int(bounds.height * scale), 1),
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0
        )?.retagging(with: .sRGB) else { return "" }
        rep.size = bounds.size
        cacheDisplay(in: bounds, to: rep)
        let px = Int(CGFloat(rep.pixelsWide - 1) * x)
        let py = Int(CGFloat(rep.pixelsHigh - 1) * y)
        guard let color = rep.colorAt(x: px, y: py) else { return "" }
        return String(
            format: "#%02x%02x%02x",
            Int((color.redComponent * 255).rounded()),
            Int((color.greenComponent * 255).rounded()),
            Int((color.blueComponent * 255).rounded())
        )
    }
}

/// Lets the ImageIO animation block notice that playback was replaced.
private final class AnimationToken {
    var stopped = false
}

/// Keeps a document smaller than the viewport centred.
private final class CenteringClipView: NSClipView {
    override func constrainBoundsRect(_ proposedBounds: NSRect) -> NSRect {
        var rect = super.constrainBoundsRect(proposedBounds)
        guard let document = documentView else { return rect }
        if rect.width > document.frame.width {
            rect.origin.x = (document.frame.width - rect.width) / 2
        }
        if rect.height > document.frame.height {
            rect.origin.y = (document.frame.height - rect.height) / 2
        }
        return rect
    }
}
