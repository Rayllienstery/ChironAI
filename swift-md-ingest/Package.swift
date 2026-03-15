// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "SwiftMdIngest",
    platforms: [
        .macOS(.v13),
        .iOS(.v16),
        .windows(.v10)
    ],
    products: [
        .executable(name: "swift-md-ingest", targets: ["SwiftMdIngest"])
    ],
    targets: [
        .executableTarget(
            name: "SwiftMdIngest",
            path: "Sources",
            swiftSettings: [
                .define("SWIFT_MD_INGEST")
            ]
        ),
        .testTarget(
            name: "SwiftMdIngestTests",
            dependencies: ["SwiftMdIngest"],
            path: "Tests"
        )
    ]
)

