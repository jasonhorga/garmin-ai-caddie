// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "GarminAICaddie",
    platforms: [
        .iOS(.v17),
        .watchOS(.v10),
    ],
    products: [
        .library(name: "AICaddieDomain", targets: ["AICaddieDomain"]),
        .library(name: "AICaddie", targets: ["AICaddie"]),
        .library(name: "AICaddieWatch", targets: ["AICaddieWatch"]),
    ],
    targets: [
        .target(
            name: "AICaddieDomain",
            path: "mobile/ios/AICaddieDomain"
        ),
        .target(
            name: "AICaddie",
            dependencies: ["AICaddieDomain"],
            path: "mobile/ios/AICaddie",
            exclude: ["AICaddieApp.swift"],
            resources: [.process("Fixtures")]
        ),
        .target(
            name: "AICaddieWatch",
            dependencies: ["AICaddieDomain"],
            path: "mobile/ios/AICaddieWatch",
            exclude: ["AICaddieWatchApp.swift"]
        ),
        .testTarget(
            name: "AICaddieDomainTests",
            dependencies: ["AICaddieDomain"],
            path: "mobile/ios/AICaddieDomainTests",
            resources: [.process("Fixtures")]
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
