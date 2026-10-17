import Foundation

/// The ordered image list and the current position within it.
public struct ViewerState {
    public private(set) var entries: [ImageEntry] = []
    public private(set) var currentIndex = 0
    /// Index of the first entry of each container ("bundle").
    private var bundleStarts: [Int] = []

    public init() {}

    public var hasEntries: Bool { !entries.isEmpty }
    public var currentEntry: ImageEntry? { entries.isEmpty ? nil : entries[currentIndex] }
    public var positionLabel: String { entries.isEmpty ? "0 / 0" : "\(currentIndex + 1) / \(entries.count)" }
    public var hasMultipleBundles: Bool { bundleStarts.count > 1 }
    public var isAtFirstEntry: Bool { currentIndex == 0 }
    public var isAtLastEntry: Bool { !entries.isEmpty && currentIndex == entries.count - 1 }
    public var isInFirstBundle: Bool { currentBundle == 0 }
    public var isInLastBundle: Bool { currentBundle == bundleStarts.count - 1 }

    public mutating func setEntries(_ newEntries: [ImageEntry], currentIndex index: Int) {
        entries = newEntries
        currentIndex = newEntries.isEmpty ? 0 : max(0, min(index, newEntries.count - 1))
        bundleStarts = newEntries.indices.filter { index in
            index == 0 || newEntries[index].container != newEntries[index - 1].container
        }
    }

    /// Next image, wrapping from the last to the first.
    public mutating func moveNext() -> Bool {
        guard hasEntries else { return false }
        currentIndex = (currentIndex + 1) % entries.count
        return true
    }

    public mutating func movePrevious() -> Bool {
        guard currentIndex > 0 else { return false }
        currentIndex -= 1
        return true
    }

    public mutating func moveBundle(by step: Int) -> Bool {
        guard hasMultipleBundles else { return false }
        let bundle = currentBundle
        currentIndex = bundleStarts[(bundle + step + bundleStarts.count) % bundleStarts.count]
        return true
    }

    /// Position of the current entry among entries of the same container.
    public var indexInBundle: Int { currentIndex - bundleStarts[currentBundle] }

    private var currentBundle: Int {
        bundleStarts.lastIndex(where: { $0 <= currentIndex }) ?? 0
    }
}
