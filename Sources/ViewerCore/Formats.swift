import Foundation

/// File types the viewer recognises.
public enum Formats {
    public static let archiveExtensions: Set<String> = ["zip", "cbz"]
    // ImageIO decodes all of these natively on macOS 13+.
    public static let imageExtensions: Set<String> = [
        "avif", "bmp", "gif", "heic", "heif", "jpeg", "jpg", "png", "tif", "tiff", "webp",
    ]

    public static func isArchive(_ url: URL) -> Bool {
        archiveExtensions.contains(url.pathExtension.lowercased())
    }

    /// Whether a file or ZIP member name is an image worth showing.
    public static func isImageName(_ name: String) -> Bool {
        let components = name.split(separator: "/")
        if components.contains(where: { $0.hasPrefix("__MACOSX") }) {
            return false
        }
        guard let last = components.last, !last.hasPrefix(".") else {
            return false
        }
        return imageExtensions.contains((String(last) as NSString).pathExtension.lowercased())
    }

    public static func isAnimated(_ name: String) -> Bool {
        (name as NSString).pathExtension.lowercased() == "gif"
    }
}
