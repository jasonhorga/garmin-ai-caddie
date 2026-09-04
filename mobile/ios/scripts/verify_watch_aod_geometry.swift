#!/usr/bin/env swift

import AppKit
import Foundation

guard CommandLine.arguments.count == 2 else {
    fputs("usage: verify_watch_aod_geometry.swift <watch-screenshot.png>\n", stderr)
    exit(2)
}

let url = URL(fileURLWithPath: CommandLine.arguments[1])
guard let data = try? Data(contentsOf: url),
      let bitmap = NSBitmapImageRep(data: data),
      bitmap.pixelsWide == 396,
      bitmap.pixelsHigh == 484 else {
    fputs("expected a decoded 396x484 Watch screenshot: \(url.path)\n", stderr)
    exit(2)
}

func isVisibleText(_ x: Int, _ y: Int) -> Bool {
    guard let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else { return false }
    return max(color.redComponent, color.greenComponent, color.blueComponent) >= 0.19
}

struct TextBand {
    var minX: Int
    var maxX: Int
    var minY: Int
    var maxY: Int

    var width: Int { maxX - minX + 1 }
    var height: Int { maxY - minY + 1 }
}

var bands: [TextBand] = []
for y in 80..<bitmap.pixelsHigh {
    var minX = bitmap.pixelsWide
    var maxX = -1
    for x in 0..<bitmap.pixelsWide where isVisibleText(x, y) {
        minX = min(minX, x)
        maxX = max(maxX, x)
    }
    guard maxX >= minX else { continue }
    if let last = bands.indices.last, y == bands[last].maxY + 1 {
        bands[last].minX = min(bands[last].minX, minX)
        bands[last].maxX = max(bands[last].maxX, maxX)
        bands[last].maxY = y
    } else {
        bands.append(TextBand(minX: minX, maxX: maxX, minY: y, maxY: y))
    }
}

guard bands.count >= 3 else {
    fputs("AOD must expose header, distance, and caption text bands; found \(bands.count)\n", stderr)
    exit(1)
}

let header = bands[0]
let distance = bands[1]
let caption = bands[2]
print(
    "WATCH_AOD header=\(header.minY)...\(header.maxY),\(header.width)x\(header.height) "
        + "distance=\(distance.minY)...\(distance.maxY),\(distance.width)x\(distance.height) "
        + "caption=\(caption.minY)...\(caption.maxY),\(caption.width)x\(caption.height)"
)

// The bounded 68 pt production render has bands at 80...99, 144...238 and 280...297.
// It intentionally leaves more rounded-glass margin than the earlier 76 pt concept render. Runtime
// includes the watchOS clock above it; verify both minimum legibility and maximum horizontal spread
// so a later change can neither shrink the hero nor reintroduce the real-device edge collision.
guard (77...85).contains(header.minY), header.width >= 100, header.height >= 18 else {
    fputs("AOD content is vertically displaced: header begins at \(header.minY)px\n", stderr)
    exit(1)
}
guard (140...150).contains(distance.minY),
      distance.width >= 220,
      distance.height >= 92,
      distance.minX >= 78,
      distance.maxX <= 317 else {
    fputs(
        "AOD distance is outside bounded geometry: x=\(distance.minX)...\(distance.maxX), "
            + "\(distance.width)x\(distance.height)px\n",
        stderr
    )
    exit(1)
}
guard (276...286).contains(caption.minY), caption.width >= 90, caption.height >= 17 else {
    fputs("AOD caption is outside the approved lane: begins at \(caption.minY)px\n", stderr)
    exit(1)
}
