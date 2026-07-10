import SwiftUI

/// Watch design-system #22: AOD 息屏大字 — Always-On dimmed face. Pure black, one huge dimmed hero number
/// (中 to-pin), minimal chrome. watchOS renders AOD at reduced luminance; here we approximate with a
/// dimmed white so the snapshot reads like the wrist-down state. Presentational.
public struct WatchAODView: View {
    public let centerYd: Int
    public let hole: Int
    public let par: Int
    public init(centerYd: Int = 262, hole: Int = 4, par: Int = 5) {
        self.centerYd = centerYd
        self.hole = hole
        self.par = par
    }
    public var body: some View {
        VStack(spacing: 2) {
            Spacer()
            Text("第\(hole)洞 · P\(par)").font(.system(size: 12, weight: .semibold)).foregroundStyle(.white.opacity(0.45))
            Text("\(centerYd)").font(.system(size: 76, weight: .bold, design: .rounded)).monospacedDigit()
                .foregroundStyle(.white.opacity(0.62))
            Text("码 · 到果岭").font(.system(size: 11)).foregroundStyle(.white.opacity(0.38))
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.black)
    }
}

/// Watch design-system #25: GPS 异常 / 低电 — an honest status screen (搜星中 / 低电量). No fabricated
/// distances while the fix is bad. Presentational; single Canvas-free layout.
public struct WatchStatusView: View {
    public enum Kind { case searching, lowBattery }
    public let kind: Kind
    public init(kind: Kind = .searching) { self.kind = kind }

    public var body: some View {
        VStack(spacing: 9) {
            Spacer()
            Image(systemName: icon).font(.system(size: 34, weight: .semibold)).foregroundStyle(tint)
            Text(title).font(.system(size: 16, weight: .bold))
            Text(detail).font(.system(size: 11)).foregroundStyle(.secondary).multilineTextAlignment(.center)
            Spacer()
        }
        .padding(12)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var icon: String {
        switch kind {
        case .searching: return "location.magnifyingglass"
        case .lowBattery: return "battery.25"
        }
    }
    private var tint: Color {
        switch kind {
        case .searching: return Color(red: 0.35, green: 0.72, blue: 1.0)
        case .lowBattery: return Color(red: 1.0, green: 0.83, blue: 0.28)
        }
    }
    private var title: String {
        switch kind {
        case .searching: return "搜星中…"
        case .lowBattery: return "电量偏低"
        }
    }
    private var detail: String {
        switch kind {
        case .searching: return "定位就绪前不显示距离,\n免得报假数"
        case .lowBattery: return "屏幕降频省电,\nGPS 记杆继续"
        }
    }
}
