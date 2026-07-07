import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

/// 复盘逐洞落点图:把这一局这一洞**实际打的每一杆**画在真实球场 2D 图上 —— 开球→落点→…→果岭
/// 连成实际打球路线,落点按球位(球道/长草/沙坑/果岭/水)配色,合成补的开球杆用虚线淡色,
/// 已知球杆标在落点旁。坐标用服务端投影好的 overlay 像素(误差 0.04m)。
public struct RoundShotMapView: View {
    public let shotMap: RoundHoleShotMap
    /// 服务端真实地形底图 URL(`…/holes/{hole}/topo.png`)。有则底图用它,否则/加载失败回退到
    /// payload 里的 flat 渲染图。两者共用同一投影,实际打球路线叠加层像素级对齐。
    public let topoURL: URL?
    /// 非 nil = 编辑态:在同一投影帧上叠一层拖动手柄 + 点击加/改(见 RoundShotEditLayer)。
    public let editModel: RoundEditModel?
    public let editClubs: [String]

    public init(shotMap: RoundHoleShotMap, topoURL: URL? = nil,
                editModel: RoundEditModel? = nil, editClubs: [String] = []) {
        self.shotMap = shotMap
        self.topoURL = topoURL
        self.editModel = editModel
        self.editClubs = editClubs
    }

    public var body: some View {
        #if canImport(UIKit)
        if let image = decodedImage, let overlay = shotMap.map?.overlay, overlay.w > 0, overlay.h > 0 {
            ZStack {
                TopoHoleBaseImage(topoURL: topoURL, fallback: image)
                Canvas { context, size in
                    draw(&context, size: size, overlay: overlay)
                }
            }
            .aspectRatio(CGFloat(overlay.w) / CGFloat(overlay.h), contentMode: .fit)
            .overlay {
                if let editModel {
                    RoundShotEditLayer(editModel: editModel, overlay: overlay, clubs: editClubs)
                }
            }
            .overlay(alignment: .topLeading) { holeTag }
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        }
        #endif
    }

    /// 第 N 洞 · Par X pill over the top-left of the render (score/relative isn't in this payload → omitted).
    @ViewBuilder private var holeTag: some View {
        if shotMap.hole > 0 {
            Text(shotMap.par.map { "第 \(shotMap.hole) 洞 · Par \($0)" } ?? "第 \(shotMap.hole) 洞")
                .font(.caption.weight(.bold))
                .foregroundStyle(.primary)
                .padding(.vertical, 5)
                .padding(.horizontal, 10)
                .background(Color.white.opacity(0.92))
                .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
                .shadow(color: .black.opacity(0.12), radius: 3, y: 1)
                .padding(10)
        }
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
        func routePoint(_ p: [Double]) -> CGPoint { CGPoint(x: CGFloat(p[0]) * sx, y: CGFloat(p[1]) * sy) }

        // Caddie-recommended route — a white dashed line, drawn FIRST so the actual (yellow) shot path
        // sits over it. Lets the player compare "what the caddie suggested" vs "what I actually did".
        let route = overlay.route.filter { $0.count >= 2 }
        if route.count >= 2 {
            var rp = Path()
            rp.move(to: routePoint(route[0]))
            for pt in route.dropFirst() { rp.addLine(to: routePoint(pt)) }
            context.stroke(rp, with: .color(.black.opacity(0.22)),
                           style: StrokeStyle(lineWidth: 3.4, lineCap: .round, lineJoin: .round))
            context.stroke(rp, with: .color(.white.opacity(0.75)),
                           style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round, dash: [5, 5]))
        }

        // Actual shot path: each shot start→end, in order, in AMBER (#ffb300). A dark halo keeps it
        // legible over green/sand/water; synthetic (auto-filled) shots are dashed + faded.
        let amber = Color(red: 1.0, green: 0.70, blue: 0.0)
        for shot in shotMap.shots {
            guard let a = point(shot.start), let b = point(shot.end) else { continue }
            var path = Path()
            path.move(to: a)
            path.addLine(to: b)
            let width: CGFloat = shot.synthetic ? 3.0 : 4.0
            context.stroke(path, with: .color(.black.opacity(0.30)),
                           style: StrokeStyle(lineWidth: width + 1.6, lineCap: .round, lineJoin: .round))
            let line = StrokeStyle(lineWidth: width, lineCap: .round, lineJoin: .round, dash: shot.synthetic ? [5, 5] : [])
            context.stroke(path, with: .color(amber.opacity(shot.synthetic ? 0.7 : 1.0)), style: line)
        }

        // Tee marker: a hollow white ring (the start of the hole).
        if let tee = point(shotMap.shots.first?.start) {
            context.stroke(Path(ellipseIn: CGRect(x: tee.x - 6, y: tee.y - 6, width: 12, height: 12)),
                           with: .color(.white), style: StrokeStyle(lineWidth: 2.5))
        }

        // Landing dot at each shot's end, colored by the lie it ended on (white outline) + club label.
        for shot in shotMap.shots {
            guard let b = point(shot.end) else { continue }
            let rect = CGRect(x: b.x - 6, y: b.y - 6, width: 12, height: 12)
            context.fill(Path(ellipseIn: rect), with: .color(shotLieColor(shot.endLie)))
            context.stroke(Path(ellipseIn: rect), with: .color(.white), style: StrokeStyle(lineWidth: 1.5))
            if let club = shot.club, !club.isEmpty, club.lowercased() != "unknown" {
                // Dark shadow behind the white club label so it stays legible over light lies
                // (fairway/green/sand). GraphicsContext is a value type — copy + addFilter so the
                // shadow applies only to this label draw, not the dots/lines.
                var labelCtx = context
                labelCtx.addFilter(.shadow(color: .black.opacity(0.85), radius: 1.4, x: 0, y: 0.5))
                labelCtx.draw(
                    Text(zhClubName(club)).font(.caption2.weight(.bold)).foregroundColor(.white),
                    at: CGPoint(x: b.x, y: b.y - 15)
                )
            }
        }
    }
}

/// 落点球位 → 颜色(球道绿、长草橄榄、沙坑沙黄、果岭浅绿、水蓝、其它/未知 红)。共享给图例。
public func shotLieColor(_ lie: String?) -> Color {
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

/// 球位中文(未知/缺失 → 「—」,不编造)。共享给逐杆列表 + 图例。
public func shotLieLabel(_ lie: String?) -> String {
    switch (lie ?? "").lowercased() {
    case "fairway": return "球道"
    case "green": return "果岭"
    case "bunker", "sand": return "沙坑"
    case "rough": return "长草"
    case "water", "hazard": return "水"
    case "teebox", "tee": return "发球台"
    default: return "—"
    }
}

/// 颜色图例:每个球位一个色点 + 中文,解决「这些点的颜色到底什么意思」。
public struct RoundShotMapLegend: View {
    public init() {}
    private let items: [(String, String)] = [
        ("fairway", "球道"), ("green", "果岭"), ("rough", "长草"),
        ("bunker", "沙坑"), ("water", "水"), ("other", "其它/未知"),
    ]
    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("落点颜色").font(.caption).foregroundStyle(.secondary)
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), alignment: .leading), count: 3), spacing: 6) {
                ForEach(items, id: \.0) { item in
                    HStack(spacing: 5) {
                        Circle().fill(shotLieColor(item.0))
                            .frame(width: 11, height: 11)
                            .overlay(Circle().stroke(Color.black.opacity(0.12)))
                        Text(item.1).font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }
        }
        .hubCard()
    }
}

/// 点开复盘某一洞 → 取该洞落点图并展示(图 + 逐杆列表)。无几何/无数据时优雅兜底。
public struct RoundHoleShotMapScreen: View {
    public let roundRef: String
    public let hole: Int
    public let apiBaseURL: URL?
    public let adminToken: String?
    /// The pager owns the title (current hole); a standalone screen sets its own.
    public let showsNavigationTitle: Bool

    @State private var shotMap: RoundHoleShotMap?
    @State private var isLoading = true
    @State private var errorText: String?
    @State private var editModel: RoundEditModel?
    @State private var isEditing = false

    public init(roundRef: String, hole: Int, apiBaseURL: URL? = nil, adminToken: String? = nil,
                showsNavigationTitle: Bool = true) {
        self.roundRef = roundRef
        self.hole = hole
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        self.showsNavigationTitle = showsNavigationTitle
    }

    public var body: some View {
        Group {
            if isLoading {
                AICaddieLoadingView(text: "载入落点…")
            } else {
                ScrollView { content }
            }
        }
        .background(HubStyle.grouped)
        .navigationTitle(showsNavigationTitle ? "第 \(hole) 洞 · 落点" : "")
        .toolbar {
            if let shotMap, shotMap.found, shotMap.map != nil, editModel != nil {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(isEditing ? "完成" : "编辑") {
                        if isEditing {
                            isEditing = false
                            Task { await editModel?.refetch(); shotMap = editModel?.map }
                        } else {
                            editModel?.enterEdit()
                            isEditing = true
                        }
                    }
                }
            }
        }
        .task(id: hole) { await load() }
    }

    @ViewBuilder private var content: some View {
        if let shotMap, shotMap.found, shotMap.map != nil {
            Group {
                if isEditing, let editModel {
                    RoundShotEditContent(editModel: editModel, topoURL: topoURL(for: shotMap))
                } else {
                    VStack(spacing: 12) {
                        RoundShotMapView(shotMap: shotMap, topoURL: topoURL(for: shotMap))
                        RoundShotMapLegend()
                        shotListCard(shotMap)
                    }
                }
            }
            .padding(14)
        } else {
            VStack(spacing: 8) {
                Image(systemName: "scope").font(.title).foregroundStyle(.secondary)
                Text(errorText ?? "这一洞暂无落点数据").font(.subheadline).foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity).padding(.vertical, 40).hubCard()
        }
    }

    private func shotListCard(_ shotMap: RoundHoleShotMap) -> some View {
        let ppm = shotMap.map?.overlay.ppm
        return VStack(alignment: .leading, spacing: 8) {
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
                    // 距离(码)—— 复盘的另一半:什么杆 + 打多远。推杆略(距离无意义)。
                    if let yards = shotYards(shot, ppm: ppm) {
                        Text("\(yards) 码").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(shotLieLabel(shot.lie) + " → " + shotLieLabel(shot.endLie)).font(.caption).foregroundStyle(.secondary)
                }
                .padding(.vertical, 5)
                .overlay(alignment: .bottom) { Divider() }
            }
        }
        .hubCard()
    }

    /// 一杆的直线距离(码),由起终点像素 + overlay 的每米像素数(ppm)换算。推杆或缺端点 → nil(不显示)。
    private func shotYards(_ shot: RoundShot, ppm: Double?) -> Int? {
        if (shot.shotType ?? "").uppercased() == "PUTT" || (shot.club ?? "").contains("推") { return nil }
        guard let s = shot.start, s.count >= 2, let e = shot.end, e.count >= 2, let ppm, ppm > 0 else { return nil }
        let dx = Double(e[0] - s[0]), dy = Double(e[1] - s[1])
        let metres = (dx * dx + dy * dy).squareRoot() / ppm
        return Int((metres * 1.09361).rounded())
    }

    /// Topo base-image URL for this hole's render — the physical (gid, localHole) the shot map was
    /// projected onto. nil (→ flat fallback) when the round has no course geometry or no base URL.
    private func topoURL(for shotMap: RoundHoleShotMap) -> URL? {
        guard let apiBaseURL, let gid = shotMap.globalId, let local = shotMap.localHole else { return nil }
        return SyncClient.topoImageURL(baseURL: apiBaseURL, globalId: gid, localHole: local)
    }

    @MainActor
    private func load() async {
        guard let apiBaseURL else { isLoading = false; errorText = "未配置后端地址"; return }
        isLoading = true
        errorText = nil
        do {
            let sync = SyncClient(baseURL: apiBaseURL, adminToken: adminToken)
            let m = try await sync.fetchRoundShotMap(roundRef: roundRef, hole: hole)
            shotMap = m
            editModel = RoundEditModel(map: m, sync: sync, roundRef: roundRef)
        } catch {
            errorText = "这一洞落点暂时取不到"
        }
        isLoading = false
    }
}

/// 横滑翻洞:整页左右滑过这一局每一洞的落点图(从复盘点某洞进入,停在该洞,可左右滑到相邻洞)。
public struct RoundShotMapPagerScreen: View {
    public let roundRef: String
    public let holes: [Int]
    public let apiBaseURL: URL?
    public let adminToken: String?
    @State private var current: Int

    public init(roundRef: String, holes: [Int], startHole: Int, apiBaseURL: URL? = nil, adminToken: String? = nil) {
        self.roundRef = roundRef
        self.holes = holes
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        _current = State(initialValue: holes.contains(startHole) ? startHole : (holes.first ?? startHole))
    }

    public var body: some View {
        TabView(selection: $current) {
            ForEach(holes, id: \.self) { hole in
                RoundHoleShotMapScreen(
                    roundRef: roundRef, hole: hole,
                    apiBaseURL: apiBaseURL, adminToken: adminToken, showsNavigationTitle: false
                )
                .tag(hole)
            }
        }
        .tabViewStyle(.page(indexDisplayMode: .never))
        .background(HubStyle.grouped)
        .navigationTitle("第 \(current) 洞 · 落点 · 左右滑")
    }
}
