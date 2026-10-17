// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "ZipPictureViewer",
    platforms: [.macOS(.v13)],
    targets: [
        // Scanning, ZIP reading and session persistence; no UI dependencies.
        .target(name: "ViewerCore"),
        .executableTarget(
            name: "ZipPictureViewer",
            dependencies: ["ViewerCore"],
            linkerSettings: [.linkedFramework("AppKit")]
        ),
    ],
    swiftLanguageModes: [.v5]
)
