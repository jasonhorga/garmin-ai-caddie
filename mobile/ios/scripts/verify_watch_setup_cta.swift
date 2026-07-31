#!/usr/bin/env swift

import AppKit
import Foundation

guard CommandLine.arguments.count == 2 else {
    fputs("usage: verify_watch_setup_cta.swift <watch-screenshot.png>\n", stderr)
    exit(2)
}

let url = URL(fileURLWithPath: CommandLine.arguments[1])
guard let data = try? Data(contentsOf: url),
      let bitmap = NSBitmapImageRep(data: data) else {
    fputs("could not decode Watch screenshot: \(url.path)\n", stderr)
    exit(2)
}

let width = bitmap.pixelsWide
let height = bitmap.pixelsHigh
guard width > 0, height > 0 else {
    fputs("empty Watch screenshot: \(url.path)\n", stderr)
    exit(2)
}

// Both the selected setup row and the primary CTA are green. Their exact RGB values vary with
// simulator colour management, so distinguish them by separate full-width horizontal bands rather
// than a brittle colour bucket: the CTA is the tallest band and the selected row is above it.
func isPrimaryActionGreen(_ x: Int, _ y: Int) -> Bool {
    guard let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else { return false }
    let red = Int((color.redComponent * 255).rounded())
    let green = Int((color.greenComponent * 255).rounded())
    let blue = Int((color.blueComponent * 255).rounded())
    return green >= 85 && green >= red + 35 && green >= blue + 20
}

struct GreenBand {
    let startY: Int
    let endY: Int

    var height: Int { endY - startY + 1 }
}

var matchingPixels = 0
var firstEdgePixels = 0
var lastEdgePixels = 0
var greenBands: [GreenBand] = []
var bandStartY: Int?

for y in 0..<height {
    var greenPixels = 0
    for x in 0..<width where isPrimaryActionGreen(x, y) {
        matchingPixels += 1
        greenPixels += 1
        if y == 0 { firstEdgePixels += 1 }
        if y == height - 1 { lastEdgePixels += 1 }
    }
    if greenPixels >= width * 55 / 100 {
        bandStartY = bandStartY ?? y
    } else if let startY = bandStartY {
        greenBands.append(GreenBand(startY: startY, endY: y - 1))
        bandStartY = nil
    }
}
if let startY = bandStartY {
    greenBands.append(GreenBand(startY: startY, endY: height - 1))
}

let actionBand = greenBands.max { $0.height < $1.height }
let actionHeight = actionBand?.height ?? 0
let selectedChoiceHeight = greenBands
    .filter { band in
        guard let actionBand else { return false }
        return band.endY < actionBand.startY
    }
    .map(\.height)
    .max() ?? 0
let edgePixels = max(firstEdgePixels, lastEdgePixels)
print(
    "WATCH_SETUP_CTA width=\(width) height=\(height) pixels=\(matchingPixels) "
        + "actionHeight=\(actionHeight) edgePixels=\(edgePixels) "
        + "selectedChoiceHeight=\(selectedChoiceHeight) "
        + "bands=\(greenBands.map(\.height))"
)

guard matchingPixels >= width * 20 else {
    fputs("primary setup action is missing from the initial Watch viewport\n", stderr)
    exit(1)
}
guard actionHeight >= 60 else {
    fputs("primary setup action is not fully visible: green band is only \(actionHeight)px high\n", stderr)
    exit(1)
}
guard edgePixels <= 4 else {
    fputs("primary setup action is clipped by the Watch viewport edge (\(edgePixels) green edge pixels)\n", stderr)
    exit(1)
}
guard selectedChoiceHeight >= 48 else {
    fputs(
        "selected setup choice is clipped by the fixed action area "
            + "(only \(selectedChoiceHeight)px visible)\n",
        stderr
    )
    exit(1)
}
