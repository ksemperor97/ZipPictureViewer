// Draws the app icon and writes assets/ZipPictureViewer.icns.
//   swift Scripts/make_icon.swift
// (Swift port of the original PySide6 drawing.)
import AppKit

let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
let assets = root.appendingPathComponent("assets")
let iconset = assets.appendingPathComponent("ZipPictureViewer.iconset")
let icns = assets.appendingPathComponent("ZipPictureViewer.icns")

func color(_ hex: UInt32, _ alpha: CGFloat = 1) -> NSColor {
    NSColor(
        srgbRed: CGFloat((hex >> 16) & 0xFF) / 255,
        green: CGFloat((hex >> 8) & 0xFF) / 255,
        blue: CGFloat(hex & 0xFF) / 255,
        alpha: alpha
    )
}

func rounded(_ rect: NSRect, _ radius: CGFloat) -> NSBezierPath {
    NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius)
}

/// Draws in a top-left origin, like the original drawing code.
func drawIcon(_ s: CGFloat) -> NSBitmapImageRep {
    let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: Int(s), pixelsHigh: Int(s), bitsPerSample: 8,
        samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
        bytesPerRow: 0, bitsPerPixel: 0
    )!.retagging(with: .sRGB)!
    let context = NSGraphicsContext(bitmapImageRep: rep)!
    let flipped = NSGraphicsContext(cgContext: context.cgContext, flipped: true)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = flipped
    let cg = flipped.cgContext
    cg.translateBy(x: 0, y: s)
    cg.scaleBy(x: 1, y: -1)

    drawBackground(s)
    drawPhotoStack(s, cg)
    drawZipper(s)

    NSGraphicsContext.restoreGraphicsState()
    return rep
}

func drawBackground(_ s: CGFloat) {
    let rect = NSRect(x: s * 0.09, y: s * 0.08, width: s * 0.82, height: s * 0.82)
    let radius = s * 0.18
    color(0x000000, 55 / 255).setFill()
    rounded(rect.offsetBy(dx: 0, dy: s * 0.035), radius).fill()
    let path = rounded(rect, radius)
    NSGradient(colors: [color(0x2DD4BF), color(0x2563EB), color(0x1E293B)], atLocations: [0, 0.48, 1], colorSpace: .sRGB)!
        .draw(in: path, angle: 45)
    color(0xFFFFFF, 80 / 255).setStroke()
    path.lineWidth = s * 0.012
    path.stroke()
}

func drawPhotoStack(_ s: CGFloat, _ cg: CGContext) {
    let back = NSRect(x: s * 0.25, y: s * 0.22, width: s * 0.48, height: s * 0.57)
    let front = NSRect(x: s * 0.19, y: s * 0.28, width: s * 0.54, height: s * 0.54)
    cg.saveGState()
    cg.translateBy(x: s * 0.03, y: -s * 0.005)
    cg.rotate(by: 7 * .pi / 180)
    drawPhotoCard(back, s, faded: true)
    cg.restoreGState()
    cg.saveGState()
    cg.rotate(by: -5 * .pi / 180)
    cg.translateBy(x: -s * 0.055, y: s * 0.035)
    drawPhotoCard(front, s, faded: false)
    cg.restoreGState()
}

func drawPhotoCard(_ rect: NSRect, _ s: CGFloat, faded: Bool) {
    let path = rounded(rect, s * 0.045)
    color(0x000000, 45 / 255).setFill()
    rounded(rect.offsetBy(dx: 0, dy: s * 0.018), s * 0.045).fill()
    color(0xF8FAFC, faded ? 225 / 255 : 1).setFill()
    path.fill()

    let inner = NSRect(x: rect.minX + s * 0.045, y: rect.minY + s * 0.045,
                       width: rect.width - s * 0.09, height: rect.height - s * 0.165)
    NSGradient(colors: [color(0x7DD3FC), color(0x22C55E), color(0x166534)], atLocations: [0, 0.55, 1], colorSpace: .sRGB)!
        .draw(in: rounded(inner, s * 0.03), angle: 90)

    let mountain = NSBezierPath()
    mountain.move(to: NSPoint(x: inner.minX, y: inner.maxY))
    mountain.line(to: NSPoint(x: inner.minX + inner.width * 0.35, y: inner.minY + inner.height * 0.45))
    mountain.line(to: NSPoint(x: inner.minX + inner.width * 0.62, y: inner.maxY))
    mountain.close()
    color(0x14532D).setFill()
    mountain.fill()

    let mountain2 = NSBezierPath()
    mountain2.move(to: NSPoint(x: inner.minX + inner.width * 0.3, y: inner.maxY))
    mountain2.line(to: NSPoint(x: inner.minX + inner.width * 0.75, y: inner.minY + inner.height * 0.35))
    mountain2.line(to: NSPoint(x: inner.maxX, y: inner.maxY))
    mountain2.close()
    color(0x15803D).setFill()
    mountain2.fill()

    color(0xE2E8F0).setStroke()
    path.lineWidth = s * 0.012
    path.stroke()
}

func drawZipper(_ s: CGFloat) {
    let x = s * 0.69, top = s * 0.20, bottom = s * 0.77, width = s * 0.075
    let railRect = NSRect(x: x, y: top, width: width, height: bottom - top)
    color(0x000000, 55 / 255).setFill()
    rounded(railRect.offsetBy(dx: s * 0.012, dy: s * 0.018), s * 0.035).fill()
    let rail = rounded(railRect, s * 0.035)
    color(0xF8FAFC).setFill()
    rail.fill()
    color(0x0F172A).setStroke()
    rail.lineWidth = s * 0.01
    rail.stroke()

    let toothHeight = s * 0.033, gap = s * 0.012
    var y = top + s * 0.045
    var toggle = false
    color(0x334155).setFill()
    while y < bottom - s * 0.09 {
        NSRect(x: x + (toggle ? width * 0.12 : width * 0.48), y: y, width: width * 0.40, height: toothHeight).fill()
        y += toothHeight + gap
        toggle.toggle()
    }

    let pull = rounded(NSRect(x: x - width * 0.2, y: bottom - s * 0.085, width: width * 1.4, height: s * 0.09), s * 0.025)
    color(0xF59E0B).setFill()
    pull.fill()
    color(0x78350F).setStroke()
    pull.lineWidth = s * 0.012
    pull.stroke()

    let paragraph = NSMutableParagraphStyle()
    paragraph.alignment = .center
    let font = NSFont(name: "HelveticaNeue-Bold", size: s * 0.052) ?? .boldSystemFont(ofSize: s * 0.052)
    let label = NSAttributedString(string: "ZIP", attributes: [
        .font: font, .foregroundColor: color(0x0F172A), .paragraphStyle: paragraph,
    ])
    let box = NSRect(x: x - width * 0.18, y: bottom - s * 0.082, width: width * 1.36, height: s * 0.08)
    let height = label.boundingRect(with: box.size).height
    label.draw(in: NSRect(x: box.minX, y: box.midY - height / 2, width: box.width, height: height))
}

let sizes: [(String, CGFloat)] = [
    ("icon_16x16.png", 16), ("icon_16x16@2x.png", 32), ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256), ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512), ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024),
]

try FileManager.default.createDirectory(at: iconset, withIntermediateDirectories: true)
for (name, size) in sizes {
    let png = drawIcon(size).representation(using: .png, properties: [:])!
    try png.write(to: iconset.appendingPathComponent(name))
}
let iconutil = Process()
iconutil.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
iconutil.arguments = ["-c", "icns", iconset.path, "-o", icns.path]
try iconutil.run()
iconutil.waitUntilExit()
guard iconutil.terminationStatus == 0 else { fatalError("iconutil failed") }
print(icns.path)
