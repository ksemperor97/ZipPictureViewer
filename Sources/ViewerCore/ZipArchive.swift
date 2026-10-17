import Foundation

public struct ZipError: Error, CustomStringConvertible, Sendable {
    public enum Kind: String, Sendable {
        case badZip = "bad_zip"
        case resourceLimit = "resource_limit"
        case unsupported = "unsupported_archive"
        case encryptionUnsupported = "unsupported_encryption"
        case passwordRequired = "password_required"
        case wrongPassword = "wrong_password"
        case changed = "source_changed"
    }

    public let kind: Kind
    public let message: String
    public var description: String { message }

    public init(_ kind: Kind, _ message: String) {
        self.kind = kind
        self.message = message
    }
}

public struct ZipLimits: Sendable {
    public var maxMembers = 100_000
    public var maxCentralDirectoryBytes = 64 * 1024 * 1024
    public init() {}
}

/// One central-directory record with its decoded name.
public struct ZipCentralRecord: Sendable {
    public let index: Int
    public let name: String
    public let isDirectory: Bool
    public let crc: UInt32
    public let location: ZipMemberLocation
    public let encryption: Encryption?
}

/// Reads a ZIP central directory without trusting declared sizes.
public enum ZipArchive {
    public static func records(
        at url: URL,
        encoding: NameEncoding,
        limits: ZipLimits = ZipLimits()
    ) throws -> [ZipCentralRecord] {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        let fileSize = try handle.seekToEnd()
        let directory = try locateCentralDirectory(handle, fileSize: fileSize)
        guard directory.count <= limits.maxMembers else {
            throw ZipError(.resourceLimit, "Archive has \(directory.count) members; limit is \(limits.maxMembers).")
        }
        guard directory.size <= UInt64(limits.maxCentralDirectoryBytes),
              directory.offset + directory.size <= fileSize
        else {
            throw ZipError(.resourceLimit, "Central directory is too large or out of bounds.")
        }
        try handle.seek(toOffset: directory.offset)
        let data = try handle.read(upToCount: Int(directory.size)) ?? Data()
        return try parseRecords(ByteReader(data), count: directory.count, encoding: encoding)
    }

    private struct DirectoryInfo {
        let offset: UInt64
        let size: UInt64
        let count: Int
    }

    private static func locateCentralDirectory(_ handle: FileHandle, fileSize: UInt64) throws -> DirectoryInfo {
        let tailLength = min(fileSize, 22 + 65_535)
        try handle.seek(toOffset: fileSize - tailLength)
        let tail = try handle.read(upToCount: Int(tailLength)) ?? Data()
        guard let endIndex = lastSignature(0x0605_4B50, in: tail, minimumRemaining: 22) else {
            throw ZipError(.badZip, "File is not a zip file")
        }
        let end = ByteReader(tail, offset: endIndex)
        end.skip(10)
        var count = UInt64(end.u16())
        var size = UInt64(end.u32())
        var offset = UInt64(end.u32())
        if count == 0xFFFF || size == 0xFFFF_FFFF || offset == 0xFFFF_FFFF {
            (offset, size, count) = try zip64Directory(handle, tail: tail, endIndex: endIndex, fileSize: fileSize)
        }
        return DirectoryInfo(offset: offset, size: size, count: Int(clamping: count))
    }

    private static func zip64Directory(
        _ handle: FileHandle,
        tail: Data,
        endIndex: Int,
        fileSize: UInt64
    ) throws -> (UInt64, UInt64, UInt64) {
        guard endIndex >= 20 else { throw ZipError(.badZip, "Missing ZIP64 locator") }
        let locator = ByteReader(tail, offset: endIndex - 20)
        guard locator.u32() == 0x0706_4B50 else { throw ZipError(.badZip, "Missing ZIP64 locator") }
        locator.skip(4)
        let recordOffset = locator.u64()
        guard recordOffset + 56 <= fileSize else { throw ZipError(.badZip, "Bad ZIP64 record") }
        try handle.seek(toOffset: recordOffset)
        let record = ByteReader(try handle.read(upToCount: 56) ?? Data())
        guard record.u32() == 0x0606_4B50 else { throw ZipError(.badZip, "Bad ZIP64 record") }
        record.skip(28)
        let count = record.u64()
        let size = record.u64()
        let offset = record.u64()
        return (offset, size, count)
    }

    private static func parseRecords(_ reader: ByteReader, count: Int, encoding: NameEncoding) throws -> [ZipCentralRecord] {
        var records: [ZipCentralRecord] = []
        records.reserveCapacity(count)
        for index in 0..<count {
            guard reader.remaining >= 46, reader.u32() == 0x0201_4B50 else {
                throw ZipError(.badZip, "Corrupt central directory at record \(index)")
            }
            reader.skip(4)
            let flags = reader.u16()
            let method = reader.u16()
            let modTime = reader.u16()
            reader.skip(2)
            let crc = reader.u32()
            var compressed = UInt64(reader.u32())
            var uncompressed = UInt64(reader.u32())
            let nameLength = Int(reader.u16())
            let extraLength = Int(reader.u16())
            let commentLength = Int(reader.u16())
            reader.skip(8)
            var offset = UInt64(reader.u32())
            guard reader.remaining >= nameLength + extraLength + commentLength else {
                throw ZipError(.badZip, "Truncated central directory record \(index)")
            }
            let rawName = reader.bytes(nameLength)
            let extra = ExtraFields(reader.bytes(extraLength))
            reader.skip(commentLength)
            extra.applyZip64(uncompressed: &uncompressed, compressed: &compressed, offset: &offset)
            let name = ZipNameDecoding.decode(rawName, flags: flags, encoding: encoding)
            records.append(ZipCentralRecord(
                index: index,
                name: name,
                isDirectory: name.hasSuffix("/"),
                crc: crc,
                location: ZipMemberLocation(
                    localHeaderOffset: offset,
                    compressedSize: compressed,
                    uncompressedSize: uncompressed,
                    method: method,
                    flags: flags,
                    modTime: modTime
                ),
                encryption: flags & 0x1 == 0 ? nil : (method == 99 || extra.has(0x9901) ? .aes : .zipCrypto)
            ))
        }
        return records
    }

    private static func lastSignature(_ signature: UInt32, in data: Data, minimumRemaining: Int) -> Int? {
        guard data.count >= minimumRemaining else { return nil }
        var index = data.count - minimumRemaining
        while index >= 0 {
            if ByteReader(data, offset: index).u32() == signature { return index }
            index -= 1
        }
        return nil
    }
}

/// ZIP extra field blocks (id, size, payload).
private struct ExtraFields {
    private var fields: [UInt16: Data] = [:]

    init(_ data: Data) {
        let reader = ByteReader(data)
        while reader.remaining >= 4 {
            let id = reader.u16()
            let size = Int(reader.u16())
            guard reader.remaining >= size else { break }
            fields[id] = reader.bytes(size)
        }
    }

    func has(_ id: UInt16) -> Bool { fields[id] != nil }

    func applyZip64(uncompressed: inout UInt64, compressed: inout UInt64, offset: inout UInt64) {
        guard let data = fields[0x0001] else { return }
        let reader = ByteReader(data)
        if uncompressed == 0xFFFF_FFFF, reader.remaining >= 8 { uncompressed = reader.u64() }
        if compressed == 0xFFFF_FFFF, reader.remaining >= 8 { compressed = reader.u64() }
        if offset == 0xFFFF_FFFF, reader.remaining >= 8 { offset = reader.u64() }
    }
}

/// Little-endian cursor over bytes. Callers check `remaining` first.
final class ByteReader {
    private let data: Data
    private(set) var position: Int

    init(_ data: Data, offset: Int = 0) {
        self.data = Data(data)
        position = offset
    }

    var remaining: Int { data.count - position }

    func skip(_ count: Int) { position += count }

    func u16() -> UInt16 { UInt16(truncatingIfNeeded: read(2)) }
    func u32() -> UInt32 { UInt32(truncatingIfNeeded: read(4)) }
    func u64() -> UInt64 { read(8) }

    func bytes(_ count: Int) -> Data {
        defer { position += count }
        return data.subdata(in: position..<(position + count))
    }

    private func read(_ count: Int) -> UInt64 {
        var value: UInt64 = 0
        for shift in 0..<count {
            value |= UInt64(data[data.startIndex + position + shift]) << (8 * shift)
        }
        position += count
        return value
    }
}
