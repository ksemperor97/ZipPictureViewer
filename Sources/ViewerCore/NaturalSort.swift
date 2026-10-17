import Foundation

/// Finder-like ordering: "vol2" before "vol10", case-insensitive.
public enum NaturalSort {
    public static func less(_ left: String, _ right: String) -> Bool {
        let order = left.compare(right, options: [.numeric, .caseInsensitive, .widthInsensitive])
        if order != .orderedSame {
            return order == .orderedAscending
        }
        return left < right
    }

    /// Compare relative paths component by component so folders group together.
    public static func lessPath(_ left: [String], _ right: [String]) -> Bool {
        for (leftPart, rightPart) in zip(left, right) where leftPart != rightPart {
            return less(leftPart, rightPart)
        }
        return left.count < right.count
    }
}
