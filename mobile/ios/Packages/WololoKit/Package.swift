// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "WololoKit",
    defaultLocalization: "en",
    platforms: [.iOS(.v17), .macOS(.v13)],
    products: [.library(name: "WololoKit", targets: ["WololoKit"])],
    targets: [
        .target(name: "WololoKit", resources: [.process("Resources")]),
        .testTarget(name: "WololoKitTests", dependencies: ["WololoKit"])
    ]
)
