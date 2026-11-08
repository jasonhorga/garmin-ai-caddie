// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "GarminAICaddie",
    platforms: [
        .iOS(.v17),
        .watchOS(.v10),
        .macOS(.v14),
    ],
    products: [
        .library(name: "AICaddieDomain", targets: ["AICaddieDomain"]),
        .library(name: "AICaddieCore", targets: ["AICaddieCore"]),
    ],
    targets: [
        .target(
            name: "SwiftJCS",
            path: "mobile/ios/AICaddieDomain/ThirdParty/SwiftJCS"
        ),
        .target(
            name: "AICaddieDomain",
            dependencies: ["SwiftJCS"],
            path: "mobile/ios/AICaddieDomain",
            exclude: ["ThirdParty/SwiftJCS"]
        ),
        .target(
            name: "AICaddieCore",
            dependencies: ["AICaddieDomain"],
            path: "mobile/ios/AICaddieCore"
        ),
        .testTarget(
            name: "AICaddieDomainTests",
            dependencies: ["AICaddieDomain", "SwiftJCS"],
            path: "mobile/ios/AICaddieDomainTests",
            resources: [.copy("Fixtures")]
        ),
        .testTarget(
            name: "AICaddieCoreTests",
            dependencies: ["AICaddieCore", "AICaddieDomain"],
            path: "mobile/ios/AICaddieCoreTests"
        ),
    ]
)
