import Foundation
import SwiftUI

public enum WatchFlagDirectionBlockReason: Equatable {
    case missingFlag
    case waitingForGPS
    case waitingForCompass
    case needsCalibration
    case staleHeading
    case alreadyAtFlag
    case tooFarFromHole

    var message: String {
        switch self {
        case .missingFlag: return "当前洞缺少旗位"
        case .waitingForGPS: return "等待 GPS 定位"
        case .waitingForCompass: return "等待指南针"
        case .needsCalibration: return "转动手腕校准"
        case .staleHeading: return "指南针数据已过期"
        case .alreadyAtFlag: return "已到旗杆"
        case .tooFarFromHole: return "离本洞较远"
        }
    }
}

public enum WatchFlagDirectionState: Equatable {
    case ready(relativeDegrees: Double, distanceYards: Int)
    case blocked(WatchFlagDirectionBlockReason)
}

/// Fail-closed PinPointer math. Only a recent, accurate true-north heading can produce an arrow.
public enum WatchFlagDirectionResolver {
    public static let maximumHeadingAgeSeconds = 10.0
    public static let maximumHeadingAccuracyDegrees = 25.0

    public static func resolve(
        playerLatitude: Double?,
        playerLongitude: Double?,
        flagLatitude: Double?,
        flagLongitude: Double?,
        heading: WatchHeadingFix?,
        now: Date = Date()
    ) -> WatchFlagDirectionState {
        guard let flagLatitude, let flagLongitude,
              valid(latitude: flagLatitude, longitude: flagLongitude) else {
            return .blocked(.missingFlag)
        }
        guard let playerLatitude, let playerLongitude,
              valid(latitude: playerLatitude, longitude: playerLongitude) else {
            return .blocked(.waitingForGPS)
        }
        let distanceM = WatchGeoMath.metres(
            playerLatitude,
            playerLongitude,
            flagLatitude,
            flagLongitude
        )
        guard distanceM >= 0.5 else { return .blocked(.alreadyAtFlag) }
        guard WatchGeoMath.usefulGolfYards(WatchGeoMath.yards(distanceM)) != nil else {
            return .blocked(.tooFarFromHole)
        }
        guard let heading else { return .blocked(.waitingForCompass) }
        guard heading.trueDegrees.isFinite,
              (0..<360).contains(heading.trueDegrees),
              heading.accuracyDegrees.isFinite,
              heading.accuracyDegrees >= 0 else {
            return .blocked(.waitingForCompass)
        }
        guard heading.accuracyDegrees <= maximumHeadingAccuracyDegrees else {
            return .blocked(.needsCalibration)
        }
        let age = now.timeIntervalSince(heading.capturedAt)
        guard age >= -1, age <= maximumHeadingAgeSeconds else {
            return .blocked(.staleHeading)
        }
        guard let bearing = WatchGeoMath.initialBearingDegrees(
            from: playerLatitude,
            playerLongitude,
            to: flagLatitude,
            flagLongitude
        ) else {
            return .blocked(.alreadyAtFlag)
        }
        return .ready(
            relativeDegrees: shortestTurnDegrees(from: heading.trueDegrees, to: bearing),
            distanceYards: WatchGeoMath.yards(distanceM)
        )
    }

    public static func shortestTurnDegrees(from heading: Double, to bearing: Double) -> Double {
        var delta = (bearing - heading).truncatingRemainder(dividingBy: 360)
        if delta > 180 { delta -= 360 }
        if delta <= -180 { delta += 360 }
        return delta
    }

    private static func valid(latitude: Double, longitude: Double) -> Bool {
        latitude.isFinite && longitude.isFinite
            && (-90...90).contains(latitude)
            && (-180...180).contains(longitude)
    }
}

public struct WatchFlagDirectionView: View {
    public let state: WatchFlagDirectionState
    public let onBack: () -> Void

    public init(
        state: WatchFlagDirectionState,
        onBack: @escaping () -> Void = {}
    ) {
        self.state = state
        self.onBack = onBack
    }

    public var body: some View {
        Group {
            switch state {
            case let .ready(relativeDegrees, distanceYards):
                VStack(spacing: 6) {
                    Text("旗向指引")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(.secondary)
                    WatchFlagCompassDial(relativeDegrees: relativeDegrees)
                        .frame(width: 104, height: 104)
                    HStack(alignment: .firstTextBaseline, spacing: 4) {
                        Text("\(distanceYards)")
                            .font(.system(size: 38, weight: .bold, design: .rounded))
                            .monospacedDigit()
                        Text("码 · 到旗杆")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.top, 4)
                .frame(maxHeight: .infinity, alignment: .top)
                .accessibilityElement(children: .combine)
                .accessibilityLabel("旗向指引，\(distanceYards) 码")
            case let .blocked(reason):
                VStack(spacing: 12) {
                    Text("旗向指引")
                        .font(.headline.weight(.bold))
                    Image(systemName: "location.north.circle")
                        .font(.system(size: 54, weight: .regular))
                        .foregroundStyle(.secondary)
                    Text(reason.message)
                        .font(.caption.weight(.medium))
                        .foregroundStyle(.secondary)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.black)
        .persistentSystemOverlays(.hidden)
        .simultaneousGesture(
            DragGesture(minimumDistance: 24)
                .onEnded { value in
                    guard value.startLocation.x <= 28,
                          value.translation.width >= 60,
                          abs(value.translation.height) < 50 else { return }
                    onBack()
                }
        )
        .accessibilityAction(named: Text("返回球洞"), onBack)
    }
}

private struct WatchFlagCompassDial: View {
    let relativeDegrees: Double

    var body: some View {
        Canvas { context, size in
            let center = CGPoint(x: size.width / 2, y: size.height / 2)
            let radius = min(size.width, size.height) / 2 - 3
            context.stroke(
                Path(ellipseIn: CGRect(
                    x: center.x - radius,
                    y: center.y - radius,
                    width: radius * 2,
                    height: radius * 2
                )),
                with: .color(Color.white.opacity(0.22)),
                style: StrokeStyle(lineWidth: 2)
            )

            for index in 0..<12 {
                let angle = Double(index) * 30 * .pi / 180
                let outer = CGPoint(
                    x: center.x + CGFloat(sin(angle)) * radius,
                    y: center.y - CGFloat(cos(angle)) * radius
                )
                let tickLength: CGFloat = index.isMultiple(of: 3) ? 8 : 6
                let inner = CGPoint(
                    x: center.x + CGFloat(sin(angle)) * (radius - tickLength),
                    y: center.y - CGFloat(cos(angle)) * (radius - tickLength)
                )
                var tick = Path()
                tick.move(to: inner)
                tick.addLine(to: outer)
                context.stroke(
                    tick,
                    with: .color(Color.white.opacity(0.25)),
                    style: StrokeStyle(lineWidth: 1.5, lineCap: .square)
                )
            }

            let angle = relativeDegrees * .pi / 180
            let direction = CGVector(dx: CGFloat(sin(angle)), dy: CGFloat(-cos(angle)))
            let perpendicular = CGVector(dx: -direction.dy, dy: direction.dx)
            let tip = CGPoint(
                x: center.x + direction.dx * 44,
                y: center.y + direction.dy * 44
            )
            let tail = CGPoint(
                x: center.x - direction.dx * 18,
                y: center.y - direction.dy * 18
            )
            var shaft = Path()
            shaft.move(to: tail)
            shaft.addLine(to: tip)
            context.stroke(
                shaft,
                with: .color(.red),
                style: StrokeStyle(lineWidth: 5, lineCap: .round)
            )

            var arrow = Path()
            arrow.move(to: tip)
            arrow.addLine(to: CGPoint(
                x: tip.x - direction.dx * 13 + perpendicular.dx * 6,
                y: tip.y - direction.dy * 13 + perpendicular.dy * 6
            ))
            arrow.addLine(to: CGPoint(
                x: tip.x - direction.dx * 13 - perpendicular.dx * 6,
                y: tip.y - direction.dy * 13 - perpendicular.dy * 6
            ))
            arrow.closeSubpath()
            context.fill(arrow, with: .color(.red))
            context.fill(
                Path(ellipseIn: CGRect(x: center.x - 5, y: center.y - 5, width: 10, height: 10)),
                with: .color(.white)
            )
        }
    }
}
