import Compression
import Foundation

public struct ReadLimits: Sendable {
    public var maxUncompressedBytes: UInt64 = 256 * 1024 * 1024
    /// Members larger than this must not exceed `maxCompressionRatio`.
    public var ratioCheckThreshold: UInt64 = 64 * 1024 * 1024
    public var maxCompressionRatio: UInt64 = 500
    public init() {}
}

/// Reads one image's bytes from a folder file or an exact ZIP member.
public enum ZipMemberReader {
    public static func read(
        _ entry: ImageEntry,
        password: Data? = nil,
        limits: ReadLimits = ReadLimits()
    ) throws -> Data {
        try checkRevision(entry)
        guard entry.isArchiveMember, let location = entry.location else {
            return try readFile(entry.sourceURL, limits: limits)
        }
        return try readMember(entry, location: location, password: password, limits: limits)
    }

    public static func checkRevision(_ entry: ImageEntry) throws {
        guard let expected = entry.revision else { return }
        guard (try? ContainerRevision(url: entry.sourceURL)) == expected else {
            throw ZipError(.changed, "File changed since it was scanned: \(entry.sourceURL.path)")
        }
    }

    private static func readFile(_ url: URL, limits: ReadLimits) throws -> Data {
        let size = try ContainerRevision(url: url).size
        guard size <= limits.maxUncompressedBytes else {
            throw ZipError(.resourceLimit, "Image is \(size) bytes; limit is \(limits.maxUncompressedBytes).")
        }
        return try Data(contentsOf: url, options: .mappedIfSafe)
    }

    private static func readMember(
        _ entry: ImageEntry,
        location: ZipMemberLocation,
        password: Data?,
        limits: ReadLimits
    ) throws -> Data {
        try checkLimits(location, limits: limits)
        if entry.encryption == .aes {
            throw ZipError(.encryptionUnsupported, "AES-encrypted ZIP members are not supported.")
        }
        let handle = try FileHandle(forReadingFrom: entry.container)
        defer { try? handle.close() }
        try handle.seek(toOffset: location.localHeaderOffset)
        let header = ByteReader(try handle.read(upToCount: 30) ?? Data())
        guard header.remaining == 30, header.u32() == 0x0403_4B50 else {
            throw ZipError(.badZip, "Bad local header for \(entry.memberName)")
        }
        header.skip(22)
        let skip = UInt64(header.u16()) + UInt64(header.u16())
        try handle.seek(toOffset: location.localHeaderOffset + 30 + skip)
        var payload = try handle.read(upToCount: Int(location.compressedSize)) ?? Data()
        guard payload.count == Int(location.compressedSize) else {
            throw ZipError(.badZip, "Truncated data for \(entry.memberName)")
        }
        if entry.encryption == .zipCrypto {
            payload = try decrypt(payload, entry: entry, location: location, password: password)
        }
        let plain = try inflate(payload, location: location, name: entry.memberName)
        // The scanner records a member id (with its CRC) for every archive entry.
        guard let expected = entry.memberID?.crc, CRC32.checksum(plain) == expected else {
            throw ZipError(.badZip, "CRC mismatch for \(entry.memberName)")
        }
        return plain
    }

    private static func checkLimits(_ location: ZipMemberLocation, limits: ReadLimits) throws {
        if location.uncompressedSize > limits.maxUncompressedBytes {
            throw ZipError(.resourceLimit, "Image expands to \(location.uncompressedSize) bytes; limit is \(limits.maxUncompressedBytes).")
        }
        if location.uncompressedSize > limits.ratioCheckThreshold,
           location.uncompressedSize > max(location.compressedSize, 1) * limits.maxCompressionRatio {
            throw ZipError(.resourceLimit, "Compression ratio exceeds \(limits.maxCompressionRatio)x.")
        }
    }

    private static func decrypt(
        _ payload: Data,
        entry: ImageEntry,
        location: ZipMemberLocation,
        password: Data?
    ) throws -> Data {
        guard let password else {
            throw ZipError(.passwordRequired, "A ZIP password is required.")
        }
        guard payload.count >= 12 else { throw ZipError(.badZip, "Encrypted data is truncated") }
        var cipher = ZipCrypto(password: password)
        let plain = cipher.decrypt(payload)
        // The last header byte checks the password: CRC high byte, or the
        // modification time high byte when a data descriptor follows.
        let check = location.flags & 0x8 != 0
            ? UInt8(location.modTime >> 8)
            : UInt8((entry.memberID?.crc ?? 0) >> 24)
        guard plain[plain.startIndex + 11] == check else {
            throw ZipError(.wrongPassword, "The ZIP password is incorrect.")
        }
        return plain.subdata(in: (plain.startIndex + 12)..<plain.endIndex)
    }

    private static func inflate(_ payload: Data, location: ZipMemberLocation, name: String) throws -> Data {
        switch location.method {
        case 0:
            return payload
        case 8:
            let capacity = Int(location.uncompressedSize)
            guard capacity > 0 else { return Data() }
            var output = Data(count: capacity)
            let written = output.withUnsafeMutableBytes { destination in
                payload.withUnsafeBytes { source in
                    compression_decode_buffer(
                        destination.bindMemory(to: UInt8.self).baseAddress!, capacity,
                        source.bindMemory(to: UInt8.self).baseAddress!, payload.count,
                        nil, COMPRESSION_ZLIB
                    )
                }
            }
            guard written == capacity else { throw ZipError(.badZip, "Cannot inflate \(name)") }
            return output
        default:
            throw ZipError(.unsupported, "Compression method \(location.method) is not supported (\(name)).")
        }
    }
}

/// Traditional PKWARE encryption.
struct ZipCrypto {
    private var keys: (UInt32, UInt32, UInt32) = (0x1234_5678, 0x2345_6789, 0x3456_7890)

    init(password: Data) {
        for byte in password { update(byte) }
    }

    mutating func decrypt(_ data: Data) -> Data {
        var output = [UInt8](repeating: 0, count: data.count)
        for (index, byte) in data.enumerated() {
            let temp = (keys.2 | 2) & 0xFFFF
            let plain = byte ^ UInt8(truncatingIfNeeded: (temp &* (temp ^ 1)) >> 8)
            update(plain)
            output[index] = plain
        }
        return Data(output)
    }

    private mutating func update(_ byte: UInt8) {
        keys.0 = CRC32.update(keys.0, byte)
        keys.1 = (keys.1 &+ (keys.0 & 0xFF)) &* 134_775_813 &+ 1
        keys.2 = CRC32.update(keys.2, UInt8(truncatingIfNeeded: keys.1 >> 24))
    }
}

enum CRC32 {
    private static let table: [UInt32] = (0..<256).map { index in
        var value = UInt32(index)
        for _ in 0..<8 {
            value = value & 1 == 1 ? (value >> 1) ^ 0xEDB8_8320 : value >> 1
        }
        return value
    }

    static func update(_ crc: UInt32, _ byte: UInt8) -> UInt32 {
        (crc >> 8) ^ table[Int((crc ^ UInt32(byte)) & 0xFF)]
    }

    static func checksum(_ data: Data) -> UInt32 {
        var crc: UInt32 = 0xFFFF_FFFF
        for byte in data { crc = update(crc, byte) }
        return crc ^ 0xFFFF_FFFF
    }
}
