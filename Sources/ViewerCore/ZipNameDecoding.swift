import Foundation

/// How ZIP member names without the UTF-8 flag are decoded.
public enum NameEncoding: String, CaseIterable, Sendable {
    case auto
    case cp949
    case cp437
}

enum ZipNameDecoding {
    private static let cp437 = String.Encoding(
        rawValue: CFStringConvertEncodingToNSStringEncoding(
            CFStringEncoding(CFStringEncodings.dosLatinUS.rawValue)
        )
    )
    private static let cp949 = String.Encoding(
        rawValue: CFStringConvertEncodingToNSStringEncoding(
            CFStringEncoding(CFStringEncodings.dosKorean.rawValue)
        )
    )

    /// The UTF-8 flag always wins. `auto` then prefers valid UTF-8 (common
    /// for macOS-made archives that omit the flag), then a plausible Korean
    /// CP949 name, then CP437 as the ZIP specification prescribes.
    static func decode(_ raw: Data, flags: UInt16, encoding: NameEncoding) -> String {
        if flags & 0x0800 != 0, let name = String(data: raw, encoding: .utf8) {
            return name
        }
        switch encoding {
        case .cp949:
            return String(data: raw, encoding: cp949) ?? latin(raw)
        case .cp437:
            return latin(raw)
        case .auto:
            if !raw.allSatisfy({ $0 < 0x80 }) {
                if let name = String(data: raw, encoding: .utf8) {
                    return name
                }
                if let name = String(data: raw, encoding: cp949), isPlausibleHangul(name) {
                    return name
                }
            }
            return latin(raw)
        }
    }

    private static func latin(_ raw: Data) -> String {
        String(data: raw, encoding: cp437) ?? String(decoding: raw, as: UTF8.self)
    }

    private static func isPlausibleHangul(_ name: String) -> Bool {
        let scalars = name.unicodeScalars
        let hasHangul = scalars.contains { (0xAC00...0xD7A3).contains($0.value) }
        let hasControl = scalars.contains { $0.value < 0x20 }
        return hasHangul && !hasControl
    }
}
