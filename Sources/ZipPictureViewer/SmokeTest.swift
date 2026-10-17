import Foundation
import ImageIO
import UniformTypeIdentifiers
import ViewerCore

/// `--smoke-test`: exercise decoding, ZIP scanning and session storage of a
/// built app without opening a window. Returns the process exit code.
enum SmokeTest {
    static func run() -> Int32 {
        do {
            try checkImageFormats()
            let folder = FileManager.default.temporaryDirectory
                .appendingPathComponent("zpv-smoke-\(UUID().uuidString)")
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            defer { try? FileManager.default.removeItem(at: folder) }

            let archive = folder.appendingPathComponent("smoke.zip")
            try storedZip(name: "page.png", data: try pngData(width: 8, height: 6)).write(to: archive)
            let result = CollectionScanner.scan(root: archive)
            guard result.issues.isEmpty, result.entries.count == 1 else {
                throw AutomationError("Archive scan failed: \(result.issues.map(\.message))")
            }
            let bytes = try ZipMemberReader.read(result.entries[0])
            guard let source = CGImageSourceCreateWithData(bytes as CFData, nil),
                  let image = CGImageSourceCreateImageAtIndex(source, 0, nil),
                  image.width == 8, image.height == 6
            else { throw AutomationError("Decoded image is invalid") }

            let store = SessionStore(fileURL: folder.appendingPathComponent("session.json"))
            let context = SourceContext(path: archive)
            store.savePosition(context, entry: result.entries[0], index: 0, indexInBundle: 0)
            guard store.lastContext() == context, store.restoreIndex(context, entries: result.entries) == 0 else {
                throw AutomationError("Session round trip failed")
            }
            print("ZipPictureViewer smoke test passed")
            return 0
        } catch {
            FileHandle.standardError.write(Data("Smoke test failed: \(error)\n".utf8))
            return 1
        }
    }

    private static func checkImageFormats() throws {
        let supported = Set((CGImageSourceCopyTypeIdentifiers() as? [String]) ?? [])
        let required: [UTType] = [.png, .jpeg, .gif, .webP, .heic]
        let missing = required.filter { !supported.contains($0.identifier) }
        guard missing.isEmpty else {
            throw AutomationError("Missing image decoders: \(missing.map(\.identifier))")
        }
    }

    private static func pngData(width: Int, height: Int) throws -> Data {
        guard let context = CGContext(
            data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
            space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else { throw AutomationError("Cannot create bitmap") }
        context.setFillColor(red: 0, green: 0.5, blue: 1, alpha: 1)
        context.fill(CGRect(x: 0, y: 0, width: width, height: height))
        let output = NSMutableData()
        guard let image = context.makeImage(),
              let destination = CGImageDestinationCreateWithData(output, UTType.png.identifier as CFString, 1, nil)
        else { throw AutomationError("Cannot encode PNG") }
        CGImageDestinationAddImage(destination, image, nil)
        guard CGImageDestinationFinalize(destination) else { throw AutomationError("Cannot encode PNG") }
        return output as Data
    }

    /// A one-member ZIP using the "stored" method.
    private static func storedZip(name: String, data: Data) -> Data {
        let nameBytes = Data(name.utf8)
        let crc = checksum(data)
        var local = Data()
        local.append(le32(0x0403_4B50)); local.append(le16(20)); local.append(le16(0x0800)); local.append(le16(0))
        local.append(le32(0)); local.append(le32(crc)); local.append(le32(UInt32(data.count))); local.append(le32(UInt32(data.count)))
        local.append(le16(UInt16(nameBytes.count))); local.append(le16(0)); local.append(nameBytes); local.append(data)
        var central = Data()
        central.append(le32(0x0201_4B50)); central.append(le16(20)); central.append(le16(20)); central.append(le16(0x0800))
        central.append(le16(0)); central.append(le32(0)); central.append(le32(crc))
        central.append(le32(UInt32(data.count))); central.append(le32(UInt32(data.count)))
        central.append(le16(UInt16(nameBytes.count))); central.append(Data(count: 12)); central.append(le32(0))
        central.append(nameBytes)
        var end = Data()
        end.append(le32(0x0605_4B50)); end.append(Data(count: 4)); end.append(le16(1)); end.append(le16(1))
        end.append(le32(UInt32(central.count))); end.append(le32(UInt32(local.count))); end.append(le16(0))
        return local + central + end
    }

    private static func checksum(_ data: Data) -> UInt32 {
        var crc: UInt32 = 0xFFFF_FFFF
        for byte in data {
            crc ^= UInt32(byte)
            for _ in 0..<8 { crc = crc & 1 == 1 ? (crc >> 1) ^ 0xEDB8_8320 : crc >> 1 }
        }
        return crc ^ 0xFFFF_FFFF
    }

    private static func le16(_ value: UInt16) -> Data { withUnsafeBytes(of: value.littleEndian) { Data($0) } }
    private static func le32(_ value: UInt32) -> Data { withUnsafeBytes(of: value.littleEndian) { Data($0) } }
}
