import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

/// 复盘逐洞落点图:把这一局这一洞**实际打的每一杆**画在真实球场 2D 图上 —— 开球→落点→…→果岭
/// 连成实际打球路线,落点按球位(球道/长草/沙坑/果岭/水)配色,合成补的开球杆用虚线淡色,
/// 已知球杆标在落点旁。坐标用服务端投影好的 overlay 像素(误差 0.04m)。
public struct RoundShotMapView: View {
    public let shotMap: RoundHoleShotMap

    public init(shotMap: RoundHoleShotMap) {
        self.shotMap = shotMap
    }

    public var body: some View {
        #if canImport(UIKit)
        if let image = decodedImage, let overlay = shotMap.map?.overlay, overlay.w > 0, overlay.h > 0 {
            ZStack {
                Image(uiImage: image).resizable().scaledToFit()
                Canvas { context, size in
                    draw(&context, size: size, overlay: overlay)
                }
            }
            .aspectRatio(CGFloat(overlay.w) / CGFloat(overlay.h), contentMode: .fit)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(LiveHoleStyle.line))
        }
        #endif
    }

    public var hasMap: Bool {
        shotMap.map?.overlay != nil && (shotMap.map?.overlay.w ?? 0) > 0
    }

    #if canImport(UIKit)
    private var decodedImage: UIImage? {
        guard let uri = shotMap.map?.image,
              let comma = uri.firstIndex(of: ","),
              let data = Data(base64Encoded: String(uri[uri.index(after: comma)...]))
        else {
            return nil
        }
        return UIImage(data: data)
    }
    #endif

    private func draw(_ context: inout GraphicsContext, size: CGSize, overlay: CoursePrepOverlay) {
        let sx = size.width / CGFloat(overlay.w)
        let sy = size.height / CGFloat(overlay.h)
        func point(_ p: [Int]?) -> CGPoint? {
            guard let p, p.count >= 2 else { return nil }
            return CGPoint(x: CGFloat(p[0]) * sx, y: CGFloat(p[1]) * sy)
        }

        // Connected shot path: each shot start→end, in order.
        for shot in shotMap.shots {
            guard let a = point(shot.start), let b = point(shot.end) else { continue }
            var path = Path()
            path.move(to: a)
            path.addLine(to: b)
            let style = shot.synthetic
                ? StrokeStyle(lineWidth: 2.5, lineCap: .round, dash: [5, 5])
                : StrokeStyle(lineWidth: 3, lineCap: .round)
            context.stroke(path, with: .color(.white.opacity(shot.synthetic ? 0.6 : 0.95)), style: style)
        }

        // Tee dot (first shot's start).
        if let tee = point(shotMap.shots.first?.start) {
            context.fill(Path(ellipseIn: CGRect(x: tee.x - 5, y: tee.y - 5, width: 10, height: 10)), with: .color(.white))
        }

        // Landing dot at each shot's end, colored by the lie it ended on, + club label.
        for shot in shotMap.shots {
            guard let b = point(shot.end) else { continue }
            let color = lieColor(shot.endLie)
            context.fill(Path(ellipseIn: CGRect(x: b.x - 7, y: b.y - 7, width: 14, height: 14)), with: .color(color))
            context.fill(Path(ellipseIn: CGRect(x: b.x - 2.5, y: b.y - 2.5, width: 5, height: 5)), with: .color(.white))
            if let club = shot.club, !club.isEmpty, club.lowercased() != "unknown" {
                context.draw(
                    Text(zhClubName(club)).font(.caption2.weight(.bold)).foregroundColor(.white),
                    at: CGPoint(x: b.x, y: b.y - 16)
                )
            }
        }
    }

    /// 落点球位 → 颜色(球道绿、长草橄榄、沙坑沙黄、果岭浅绿、水蓝)。
    private func lieColor(_ lie: String?) -> Color {
        switch (lie ?? "").lowercased() {
        case "fairway": return LiveHoleStyle.green
        case "green": return Color(red: 90 / 255, green: 200 / 255, blue: 120 / 255)
        case "bunker", "sand": return Color(red: 214 / 255, green: 190 / 255, blue: 138 / 255)
        case "rough": return Color(red: 120 / 255, green: 140 / 255, blue: 70 / 255)
        case "water", "hazard": return Color(red: 60 / 255, green: 130 / 255, blue: 200 / 255)
        case "teebox", "tee": return .white
        default: return Color(red: 185 / 255, green: 50 / 255, blue: 40 / 255)
        }
    }
}

/// 点开复盘某一洞 → 取该洞落点图并展示(图 + 逐杆列表)。无几何/无数据时优雅兜底。
public struct RoundHoleShotMapScreen: View {
    public let roundRef: String
    public let hole: Int
    public let apiBaseURL: URL?
    public let adminToken: String?

    @State private var shotMap: RoundHoleShotMap?
    @State private var isLoading = true
    @State private var errorText: String?

    public init(roundRef: String, hole: Int, apiBaseURL: URL? = nil, adminToken: String? = nil) {
        self.roundRef = roundRef
        self.hole = hole
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
    }

    public var body: some View {
        Group {
            if isLoading {
                AICaddieLoadingView(text: "载入落点…")
            } else {
                ScrollView { content }
            }
        }
        .background(Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255))
        .navigationTitle("第 \(hole) 洞 · 落点")
        .task(id: hole) { await load() }
    }

    @ViewBuilder private var content: some View {
        if let shotMap, shotMap.found, shotMap.map != nil {
            VStack(spacing: 12) {
                RoundShotMapView(shotMap: shotMap)
                shotListCard(shotMap)
            }
            .padding(14)
        } else {
            VStack(spacing: 8) {
                Image(systemName: "scope").font(.title).foregroundStyle(.secondary)
                Text(errorText ?? "这一洞暂无落点数据").font(.subheadline).foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity).padding(.vertical, 40).liveCard()
        }
    }

    private func shotListCard(_ shotMap: RoundHoleShotMap) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("逐杆").font(.caption).foregroundStyle(.secondary)
            ForEach(shotMap.shots) { shot in
                HStack(spacing: 8) {
                    Text("\((shot.order ?? 0))").font(.subheadline.monospacedDigit().weight(.bold)).frame(width: 22, alignment: .leading)
                    if let club = shot.club, !club.isEmpty, club.lowercased() != "unknown" {
                        Text(zhClubName(club)).font(.subheadline)
                    } else if shot.synthetic {
                        Text("开球(自动补)").font(.subheadline).foregroundStyle(.secondary)
                    } else {
                        Text("—").font(.subheadline).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(zhLie(shot.lie) + " → " + zhLie(shot.endLie)).font(.caption).foregroundStyle(.secondary)
                }
                .padding(.vertical, 5)
                .overlay(alignment: .bottom) { Divider() }
            }
        }
        .liveCard()
    }

    private func zhLie(_ lie: String?) -> String {
        switch (lie ?? "").lowercased() {
        case "fairway": return "球道"
        case "green": return "果岭"
        case "bunker", "sand": return "沙坑"
        case "rough": return "长草"
        case "water", "hazard": return "水"
        case "teebox", "tee": return "发球台"
        case "": return "—"
        default: return lie ?? "—"
        }
    }

    @MainActor
    private func load() async {
        guard let apiBaseURL else { isLoading = false; errorText = "未配置后端地址"; return }
        isLoading = true
        errorText = nil
        do {
            shotMap = try await SyncClient(baseURL: apiBaseURL, adminToken: adminToken).fetchRoundShotMap(roundRef: roundRef, hole: hole)
        } catch {
            errorText = "这一洞落点暂时取不到"
        }
        isLoading = false
    }
}
