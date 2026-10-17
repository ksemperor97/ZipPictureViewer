import Foundation
import ImageIO
import ViewerCore

struct DecodedImage {
    let image: CGImage
    /// Size after EXIF orientation, in image pixels.
    let originalSize: CGSize
    let isFullResolution: Bool
}

enum DecodeOutcome {
    case image(DecodedImage)
    case animation(Data, originalSize: CGSize)
    case failure(ZipError)
}

struct DecodeLimits {
    var maxPixels = 100_000_000
    var maxDecodedBytes = 256 * 1024 * 1024
    var read = ReadLimits()
}

/// Decodes images off the main thread with ImageIO and caches still images.
final class ImageDecoder {
    private let queue: OperationQueue = {
        let queue = OperationQueue()
        queue.maxConcurrentOperationCount = 2
        queue.qualityOfService = .userInitiated
        return queue
    }()
    private let cache = NSCache<CacheKey, CachedImage>()
    private let limits: DecodeLimits

    init(limits: DecodeLimits = DecodeLimits()) {
        self.limits = limits
        cache.totalCostLimit = 256 * 1024 * 1024
    }

    /// The best cached image of `entry` that is at least `maxPixel` wide, if any.
    func cached(_ entry: ImageEntry, maxPixel: Int?) -> DecodedImage? {
        guard let item = cache.object(forKey: CacheKey(entry)) else { return nil }
        guard (try? ZipMemberReader.checkRevision(entry)) != nil else {
            cache.removeObject(forKey: CacheKey(entry))
            return nil
        }
        let decoded = item.decoded
        if decoded.isFullResolution { return decoded }
        let longest = Int(max(decoded.image.width, decoded.image.height))
        return longest >= (maxPixel ?? Int.max) ? decoded : nil
    }

    func cancelPending() {
        queue.cancelAllOperations()
    }

    /// Decode `entry`; `maxPixel` nil means full resolution.
    func decode(
        _ entry: ImageEntry,
        maxPixel: Int?,
        password: Data?,
        completion: @escaping (DecodeOutcome) -> Void
    ) {
        let limits = self.limits
        let cache = self.cache
        queue.addOperation {
            let outcome = Self.run(entry, maxPixel: maxPixel, password: password, limits: limits)
            if case .image(let decoded) = outcome {
                let key = CacheKey(entry)
                let existing = cache.object(forKey: key)?.decoded
                if existing.map({ !$0.isFullResolution && $0.image.width <= decoded.image.width }) ?? true {
                    cache.setObject(CachedImage(decoded), forKey: key, cost: decoded.image.bytesPerRow * decoded.image.height)
                }
            }
            DispatchQueue.main.async { completion(outcome) }
        }
    }

    private static func run(_ entry: ImageEntry, maxPixel: Int?, password: Data?, limits: DecodeLimits) -> DecodeOutcome {
        do {
            let data = try ZipMemberReader.read(entry, password: password, limits: limits.read)
            guard let source = CGImageSourceCreateWithData(data as CFData, nil),
                  CGImageSourceGetCount(source) > 0
            else { throw ZipError(.badZip, "Cannot read image data") }
            let size = try checkedSize(source, limits: limits)
            if entry.isAnimated && CGImageSourceGetCount(source) > 1 {
                return .animation(data, originalSize: size)
            }
            let longest = Int(max(size.width, size.height))
            let target = min(maxPixel ?? longest, longest)
            let options: [CFString: Any] = [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceThumbnailMaxPixelSize: max(target, 1),
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceShouldCacheImmediately: true,
            ]
            guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else {
                throw ZipError(.badZip, "Cannot decode image")
            }
            return .image(DecodedImage(image: image, originalSize: size, isFullResolution: target >= longest))
        } catch let error as ZipError {
            return .failure(error)
        } catch {
            return .failure(ZipError(.badZip, error.localizedDescription))
        }
    }

    private static func checkedSize(_ source: CGImageSource, limits: DecodeLimits) throws -> CGSize {
        guard let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let width = properties[kCGImagePropertyPixelWidth] as? Int,
              let height = properties[kCGImagePropertyPixelHeight] as? Int,
              width > 0, height > 0
        else { throw ZipError(.badZip, "Cannot read image size") }
        guard width * height <= limits.maxPixels, width * height * 4 <= limits.maxDecodedBytes else {
            throw ZipError(.resourceLimit, "Image is \(width)×\(height); limit is \(limits.maxPixels / 1_000_000) MP.")
        }
        // Orientations 5–8 rotate by 90°, swapping width and height.
        let orientation = properties[kCGImagePropertyOrientation] as? Int ?? 1
        return orientation >= 5 ? CGSize(width: height, height: width) : CGSize(width: width, height: height)
    }
}

private final class CacheKey: NSObject {
    let entry: ImageEntry
    init(_ entry: ImageEntry) { self.entry = entry }
    override var hash: Int { entry.hashValue }
    override func isEqual(_ object: Any?) -> Bool { (object as? CacheKey)?.entry == entry }
}

private final class CachedImage {
    let decoded: DecodedImage
    init(_ decoded: DecodedImage) { self.decoded = decoded }
}
