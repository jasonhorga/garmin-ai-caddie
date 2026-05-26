// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "GarminAICaddie",
    platforms: [
        .iOS(.v17),
        .watchOS(.v10),
    ],
    products: [
        .library(name: "AICaddie", targets: ["AICaddie"]),
        .library(name: "AICaddieWatch", targets: ["AICaddieWatch"]),
    ],
    targets: [
        .target(
            name: "AICaddie",
            path: "mobile/ios/AICaddie",
            exclude: ["AICaddieApp.swift"],
            resources: [.process("Fixtures")]
        ),
        .target(
            name: "AICaddieWatch",
            path: "mobile/ios/AICaddieWatch",
            exclude: ["AICaddieWatchApp.swift"]
        ),
        .testTarget(
            name: "AICaddieTests",
            dependencies: ["AICaddie"],
            path: "mobile/ios/AICaddieTests"
        ),
        .testTarget(
            name: "AICaddieWatchTests",
            dependencies: ["AICaddieWatch"],
            path: "mobile/ios/AICaddieWatchTests"
        ),
    ]
)
