import Foundation

public enum SourceKind: String, Sendable {
    case folder
    case archive
}

public enum Encryption: Sendable {
    case zipCrypto
    case aes
}

/// Detects a file replaced or modified after it was scanned.
public struct ContainerRevision: Hashable, Sendable {
    public let size: UInt64
    public let modified: TimeInterval
    public let inode: UInt64

    public init(url: URL) throws {
        let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        size = (attributes[.size] as? NSNumber)?.uint64Value ?? 0
        modified = (attributes[.modificationDate] as? Date)?.timeIntervalSince1970 ?? 0
        inode = (attributes[.systemFileNumber] as? NSNumber)?.uint64Value ?? 0
    }
}

/// Identifies one central-directory record, even among duplicate names.
public struct ArchiveMemberID: Hashable, Sendable {
    public let recordIndex: Int
    public let headerOffset: UInt64
    public let crc: UInt32
}

/// Where a ZIP member's data lives, taken from the central directory.
public struct ZipMemberLocation: Hashable, Sendable {
    public let localHeaderOffset: UInt64
    public let compressedSize: UInt64
    public let uncompressedSize: UInt64
    public let method: UInt16
    public let flags: UInt16
    public let modTime: UInt16
}

public struct ImageEntry: Hashable, Sendable {
    /// The archive file, or the folder holding the image file.
    public let container: URL
    public let memberName: String
    public let kind: SourceKind
    public let revision: ContainerRevision?
    public let memberID: ArchiveMemberID?
    public let location: ZipMemberLocation?
    public let encryption: Encryption?

    public init(
        container: URL,
        memberName: String,
        kind: SourceKind,
        revision: ContainerRevision?,
        memberID: ArchiveMemberID? = nil,
        location: ZipMemberLocation? = nil,
        encryption: Encryption? = nil
    ) {
        self.container = container
        self.memberName = memberName
        self.kind = kind
        self.revision = revision
        self.memberID = memberID
        self.location = location
        self.encryption = encryption
    }

    public var isArchiveMember: Bool { kind == .archive }
    public var isAnimated: Bool { Formats.isAnimated(memberName) }
    public var imageLabel: String { (memberName as NSString).lastPathComponent }

    /// The file whose revision controls this entry's contents.
    public var sourceURL: URL {
        isArchiveMember ? container : container.appendingPathComponent(memberName)
    }
}

public struct ScanIssue: Sendable {
    public let target: URL
    public let stage: String
    public let kind: String
    public let message: String
}

public struct ScanResult: Sendable {
    public var entries: [ImageEntry] = []
    public var issues: [ScanIssue] = []
    public var cancelled = false
    public var discoveredFiles = 0

    public init() {}
}
