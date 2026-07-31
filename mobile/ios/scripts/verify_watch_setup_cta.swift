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

// The setup fixture has one darker selected-Tee row and one brighter primary CTA. Match only the
// latter, allowing normal antialiasing and colour-management variation in the simulator screenshot.
func isPrimaryActionGreen(_ x: Int, _ y: Int) -> Bool {
    guard let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else { return false }
    let red = Int((color.redComponent * 255).rounded())
    let green = Int((color.greenComponent * 255).rounded())
    let blue = Int((color.blueComponent * 255).rounded())
    return green >= 85 && green >= red + 35 && green >= blue + 20
}

func isSelectedChoiceGreen(_ x: Int, _ y: Int) -> Bool {
    guard let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else { return false }
    let red = Int((color.redComponent * 255).rounded())
    let green = Int((color.greenComponent * 255).rounded())
    let blue = Int((color.blueComponent * 255).rounded())
    return (55...82).contains(green) && green >= red + 30 && green >= blue + 20
}

var minY = height
var maxY = -1
var matchingPixels = 0
var firstEdgePixels = 0
var lastEdgePixels = 0
var selectedChoiceRun = 0
var longestSelectedChoiceRun = 0

for y in 0..<height {
    var selectedChoicePixels = 0
    for x in 0..<width where isPrimaryActionGreen(x, y) {
        matchingPixels += 1
        minY = min(minY, y)
        maxY = max(maxY, y)
        if y == 0 { firstEdgePixels += 1 }
        if y == height - 1 { lastEdgePixels += 1 }
    }
    for x in 0..<width where isSelectedChoiceGreen(x, y) {
        selectedChoicePixels += 1
    }
    if selectedChoicePixels >= width * 55 / 100 {
        selectedChoiceRun += 1
        longestSelectedChoiceRun = max(longestSelectedChoiceRun, selectedChoiceRun)
    } else {
        selectedChoiceRun = 0
    }
}

let actionHeight = maxY >= minY ? maxY - minY + 1 : 0
let edgePixels = max(firstEdgePixels, lastEdgePixels)
print(
    "WATCH_SETUP_CTA width=\(width) height=\(height) pixels=\(matchingPixels) "
        + "actionHeight=\(actionHeight) edgePixels=\(edgePixels) "
        + "selectedChoiceHeight=\(longestSelectedChoiceRun)"
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
guard longestSelectedChoiceRun >= 48 else {
    fputs(
        "selected setup choice is clipped by the fixed action area "
            + "(only \(longestSelectedChoiceRun)px visible)\n",
        stderr
    )
    exit(1)
}
