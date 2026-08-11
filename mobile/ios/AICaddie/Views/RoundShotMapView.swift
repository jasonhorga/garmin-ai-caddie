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
        if let overlay = shotMap.map?.overlay, overlay.w > 0, overlay.h > 0 {
            let ratio = CGFloat(overlay.w) / CGFloat(overlay.h)
            if let editModel {
                ZStack {
                    TopoHoleBaseImage(topoURL: topoURL, fallback: decodedImage)
                    Canvas { context, size in
                        draw(&context, size: size, overlay: overlay)
                    }
                }
                .aspectRatio(ratio, contentMode: .fit)
                .overlay {
                    if let image = decodedImage {
                        RoundShotEditLayer(editModel: editModel, overlay: overlay, clubs: editClubs,
                                           baseImage: image, topoURL: topoURL)
                    }
                }
                .overlay(alignment: .topLeading) { holeTag }
                .mapSurface()
            } else {
                ZoomableRoundMapViewport(aspectRatio: ratio) {
                    ZStack {
                        TopoHoleBaseImage(topoURL: topoURL, fallback: decodedImage)
                        Canvas { context, size in
                            draw(&context, size: size, overlay: overlay)
                        }
                    }
                }
                .overlay(alignment: .topLeading) { holeTag }
                .overlay(alignment: .bottomTrailing) {
                    Label("双指缩放", systemImage: "plus.magnifyingglass")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.white)
                        .padding(.vertical, 5)
                        .padding(.horizontal, 8)
                        .background(.black.opacity(0.55), in: Capsule())
                        .padding(9)
                        .allowsHitTesting(false)
                }
                .mapSurface()
            }
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
        drawRoundShotPath(&context, size: size, overlay: overlay, shots: shotMap.shots)
    }
}

#if canImport(UIKit)
/// Pinch/pan/double-tap viewport used only by the read-only history map. Edit mode keeps the
/// unscaled coordinate plane so its landing-point drag gestures remain pixel-authoritative.
private struct ZoomableRoundMapViewport<Content: View>: View {
    let aspectRatio: CGFloat
    let content: Content

    @State private var scale: CGFloat = 1
    @State private var offset: CGSize = .zero
    @GestureState private var pinchScale: CGFloat = 1
    @GestureState private var dragOffset: CGSize = .zero

    private var displayedScale: CGFloat {
        min(max(scale * pinchScale, 1), 4)
    }

    init(aspectRatio: CGFloat, @ViewBuilder content: () -> Content) {
        self.aspectRatio = aspectRatio
        self.content = content()
    }

    var body: some View {
        GeometryReader { proxy in
            let size = proxy.size
            let proposedOffset = CGSize(
                width: offset.width + dragOffset.width,
                height: offset.height + dragOffset.height
            )
            content
                .frame(width: size.width, height: size.height)
                .scaleEffect(displayedScale)
                .offset(clamped(proposedOffset, in: size, scale: displayedScale))
                .contentShape(Rectangle())
                .gesture(magnifyGesture(in: size))
                // At 1× the pager owns horizontal drags (change hole). Once zoomed, the map owns
                // them with higher priority so panning never accidentally jumps to another hole.
                .highPriorityGesture(
                    panGesture(in: size),
                    including: displayedScale > 1.01 ? .all : .none
                )
                .onTapGesture(count: 2) {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        if scale > 1.05 {
                            scale = 1
                            offset = .zero
                        } else {
                            scale = 2.5
                            offset = .zero
                        }
                    }
                }
                .accessibilityHint("双指缩放，放大后拖动；双击可快速放大或还原")
        }
        .aspectRatio(aspectRatio, contentMode: .fit)
        .clipped()
    }

    private func magnifyGesture(in size: CGSize) -> some Gesture {
        MagnificationGesture()
            .updating($pinchScale) { value, state, _ in state = value }
            .onEnded { value in
                scale = min(max(scale * value, 1), 4)
                if scale <= 1.01 {
                    scale = 1
                    offset = .zero
                } else {
                    offset = clamped(offset, in: size, scale: scale)
                }
            }
    }

    private func panGesture(in size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 8)
            .updating($dragOffset) { value, state, _ in
                if displayedScale > 1.01 { state = value.translation }
            }
            .onEnded { value in
                guard scale > 1.01 else { return }
                let proposed = CGSize(
                    width: offset.width + value.translation.width,
                    height: offset.height + value.translation.height
                )
                offset = clamped(proposed, in: size, scale: scale)
            }
    }

    private func clamped(_ value: CGSize, in size: CGSize, scale: CGFloat) -> CGSize {
        guard scale > 1 else { return .zero }
        let maxX = size.width * (scale - 1) / 2
        let maxY = size.height * (scale - 1) / 2
        return CGSize(
            width: min(max(value.width, -maxX), maxX),
            height: min(max(value.height, -maxY), maxY)
        )
    }
}
#endif

/// Shared shot-path rendering (amber actual path + tee ring + landing dots + club
/// labels), factored out of ``RoundShotMapView`` so the drag magnifier (``MagnifierLoupe``) draws the
/// exact same picture — magnified — over the exact same projection.
func drawRoundShotPath(_ context: inout GraphicsContext, size: CGSize, overlay: CoursePrepOverlay, shots: [RoundShot]) {
    let sx = size.width / CGFloat(max(overlay.w, 1))
    let sy = size.height / CGFloat(max(overlay.h, 1))
    func point(_ p: [Int]?) -> CGPoint? {
        guard let p, p.count >= 2 else { return nil }
        return CGPoint(x: CGFloat(p[0]) * sx, y: CGFloat(p[1]) * sy)
    }
    // Actual shot path: each shot start→end, in order, in AMBER (#ffb300). A dark halo keeps it
    // legible over green/sand/water; synthetic (auto-filled) shots are dashed + faded.
    let amber = Color(red: 1.0, green: 0.70, blue: 0.0)
    for shot in shots {
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
    if let tee = point(shots.first?.start) {
        context.stroke(Path(ellipseIn: CGRect(x: tee.x - 6, y: tee.y - 6, width: 12, height: 12)),
                       with: .color(.white), style: StrokeStyle(lineWidth: 2.5))
    }

    // Landing dot at each shot's end, colored by the lie it ended on (white outline) + club label.
    for shot in shots {
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
    case "fringe": return "果岭边"
    case "trees", "tree_area": return "树下"
    case "water", "hazard": return "水"
    case "teebox", "tee": return "发球台"
    default: return "—"
    }
}

/// 一杆的直线距离(码),由起终点像素 + overlay 的每米像素数(ppm)换算。推杆或缺端点 → nil(不显示)。
/// 共享给只读逐杆行 + 编辑态可重排行,拖动后距离随之刷新(米→码)。
public func roundShotYards(_ shot: RoundShot, ppm: Double?) -> Int? {
    if (shot.shotType ?? "").uppercased() == "PUTT" || (shot.club ?? "").contains("推") { return nil }
    guard let s = shot.start, s.count >= 2, let e = shot.end, e.count >= 2, let ppm, ppm > 0 else { return nil }
    let dx = Double(e[0] - s[0]), dy = Double(e[1] - s[1])
    let metres = (dx * dx + dy * dy).squareRoot() / ppm
    return Int((metres * 1.09361).rounded())
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

/// Screen-level cache for one historical round. A `TabView` is free to unload off-screen pages;
/// keeping maps and in-flight work here makes that an implementation detail instead of another
/// server request. The pager fetches the current hole first, then the remaining holes four at a
/// time, and warms each corresponding topo bitmap through `TopoHoleImageStore`.
@MainActor
final class RoundShotMapRepository: ObservableObject {
    private enum LoadResult {
        case success(RoundHoleShotMap)
        case failure
    }

    @Published private var maps: [Int: RoundHoleShotMap] = [:]
    @Published private var loadingHoles: Set<Int> = []
    @Published private var errors: [Int: String] = [:]

    private let roundRef: String
    private let client: SyncClient?
    private var inFlight: [Int: Task<LoadResult, Never>] = [:]

    init(roundRef: String, apiBaseURL: URL?, adminToken: String?) {
        self.roundRef = roundRef
        self.client = apiBaseURL.map { SyncClient(baseURL: $0, adminToken: adminToken) }
    }

    func map(for hole: Int) -> RoundHoleShotMap? { maps[hole] }

    func isLoading(_ hole: Int) -> Bool {
        maps[hole] == nil && errors[hole] == nil
    }

    func error(for hole: Int) -> String? { errors[hole] }

    func store(_ map: RoundHoleShotMap, for hole: Int) {
        maps[hole] = map
        errors[hole] = nil
        prefetchTopo(for: map)
    }

    func load(_ hole: Int) async {
        guard maps[hole] == nil else { return }
        guard let client else {
            errors[hole] = "未配置后端地址"
            return
        }

        let task: Task<LoadResult, Never>
        if let existing = inFlight[hole] {
            task = existing
        } else {
            errors[hole] = nil
            loadingHoles.insert(hole)
            task = Task { [roundRef] in
                do {
                    return .success(try await client.fetchRoundShotMap(roundRef: roundRef, hole: hole))
                } catch {
                    return .failure
                }
            }
            inFlight[hole] = task
        }

        let result = await task.value
        inFlight[hole] = nil
        loadingHoles.remove(hole)
        switch result {
        case .success(let map):
            maps[hole] = map
            errors[hole] = nil
            prefetchTopo(for: map)
        case .failure:
            if maps[hole] == nil { errors[hole] = "这一洞落点暂时取不到" }
        }
    }

    /// Current/start hole first, then neighbours, then the rest. Four concurrent API calls keep the
    /// 18-hole warm-up fast without creating the request storm that previously slowed every page.
    func prefetch(_ holes: [Int], startingAt startHole: Int? = nil) async {
        var seen: Set<Int> = []
        let valid = holes.filter { $0 > 0 && seen.insert($0).inserted }
        let ordered: [Int]
        if let startHole, let startIndex = valid.firstIndex(of: startHole) {
            let neighbours = [startHole, valid[safe: startIndex - 1], valid[safe: startIndex + 1]].compactMap { $0 }
            let priority = neighbours.filter { seenValue in valid.contains(seenValue) }
            ordered = priority + valid.filter { !priority.contains($0) }
        } else {
            ordered = valid
        }

        for index in stride(from: 0, to: ordered.count, by: 4) {
            guard !Task.isCancelled else { return }
            let batch = Array(ordered[index..<min(index + 4, ordered.count)])
            await withTaskGroup(of: Void.self) { group in
                for hole in batch {
                    group.addTask { await self.load(hole) }
                }
            }
        }
    }

    private func prefetchTopo(for map: RoundHoleShotMap) {
        #if canImport(UIKit)
        guard let client,
              let globalId = map.globalId,
              let localHole = map.localHole,
              map.geometryRevision != nil,
              !map.usesCourseDataFrame else { return }
        TopoHoleImageStore.prefetch(
            SyncClient.topoImageURL(
                baseURL: client.baseURL,
                globalId: globalId,
                localHole: localHole,
                geometryRevision: map.geometryRevision
            )
        )
        #endif
    }
}

private extension Array {
    subscript(safe index: Index) -> Element? {
        indices.contains(index) ? self[index] : nil
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
    /// Called when this hole enters/leaves edit mode, so the pager can lock horizontal 翻洞 while editing
    /// (设计 §1:改的模式锁切洞,免误触换洞)。nil for a standalone screen.
    public let onEditingChange: ((Bool) -> Void)?

    @StateObject private var mapRepository: RoundShotMapRepository
    @State private var editModel: RoundEditModel?
    @State private var isEditing = false
    @State private var isSaving = false

    public init(roundRef: String, hole: Int, apiBaseURL: URL? = nil, adminToken: String? = nil,
                showsNavigationTitle: Bool = true, onEditingChange: ((Bool) -> Void)? = nil) {
        self.roundRef = roundRef
        self.hole = hole
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        self.showsNavigationTitle = showsNavigationTitle
        self.onEditingChange = onEditingChange
        _mapRepository = StateObject(
            wrappedValue: RoundShotMapRepository(
                roundRef: roundRef,
                apiBaseURL: apiBaseURL,
                adminToken: adminToken
            )
        )
    }

    init(roundRef: String, hole: Int, apiBaseURL: URL?, adminToken: String?,
         showsNavigationTitle: Bool, onEditingChange: ((Bool) -> Void)?,
         mapRepository: RoundShotMapRepository) {
        self.roundRef = roundRef
        self.hole = hole
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        self.showsNavigationTitle = showsNavigationTitle
        self.onEditingChange = onEditingChange
        _mapRepository = StateObject(wrappedValue: mapRepository)
    }

    private var shotMap: RoundHoleShotMap? { mapRepository.map(for: hole) }
    private var isLoading: Bool { mapRepository.isLoading(hole) }
    private var errorText: String? { mapRepository.error(for: hole) }

    public var body: some View {
        Group {
            if isLoading {
                AICaddieLoadingView(text: "载入落点…")
            } else {
                ScrollView { content }
                    // The editable topo deliberately owns long-press/drag gestures. Give the outer
                    // vertical scroller a stable accessibility target so assistive technology and
                    // the real UI journey can start a scroll from the controls below the map rather
                    // than accidentally moving a numbered landing.
                    .accessibilityIdentifier(isEditing ? "round-shot-edit-scroll" : "round-shot-read-scroll")
            }
        }
        .background(HubStyle.grouped)
        .navigationTitle(showsNavigationTitle ? "第 \(hole) 洞 · 落点" : "")
        .toolbar {
            if let sm = shotMap, sm.found, editModel != nil {
                if isEditing {
                    ToolbarItem(placement: .navigationBarLeading) {
                        Button("取消") { cancelEditing() }
                            .disabled(isSaving)
                            .accessibilityIdentifier("round-edit-cancel")
                    }
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Button {
                            Task { await saveEditing() }
                        } label: {
                            if isSaving {
                                ProgressView()
                                    .controlSize(.small)
                                    .accessibilityLabel("保存中")
                            } else {
                                Text("保存")
                            }
                        }
                        .disabled(isSaving)
                        .accessibilityIdentifier("round-edit-save")
                    }
                } else {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Button("编辑") { beginEditing() }
                    }
                }
            }
        }
        .task(id: hole) { await load() }
        .onDisappear {
            guard isEditing else { return }
            editModel?.cancelEdit()
            isEditing = false
            isSaving = false
            onEditingChange?(false)
        }
    }

    @ViewBuilder private var content: some View {
        if isEditing, let editModel {
            Group {
                if editModel.canEditPositions {
                    RoundShotEditContent(editModel: editModel, topoURL: topoURL(for: editModel.map))
                } else {
                    RoundShotFactEditContent(editModel: editModel)
                }
            }
            .allowsHitTesting(!isSaving)
            .padding(14)
        } else if let shotMap, shotMap.found, shotMap.map != nil {
            VStack(spacing: 12) {
                RoundShotMapView(shotMap: shotMap, topoURL: topoURL(for: shotMap))
                if let reason = shotMap.missingData.first?.reason {
                    Label(reason, systemImage: "arrow.clockwise.circle")
                        .font(.subheadline)
                        .foregroundStyle(.orange)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .hubCard()
                }
                RoundShotMapLegend()
                shotListCard(shotMap)
            }
            .padding(14)
        } else if let shotMap, shotMap.found, !shotMap.shots.isEmpty {
            VStack(spacing: 12) {
                Label(
                    shotMap.missingData.first?.reason
                        ?? "已找到逐杆 GPS，球场地图素材正在准备",
                    systemImage: "location.fill"
                )
                .font(.subheadline)
                .foregroundStyle(.orange)
                .frame(maxWidth: .infinity, alignment: .leading)
                .hubCard()
                shotListCard(shotMap)
            }
            .padding(14)
        } else {
            VStack(spacing: 8) {
                Image(systemName: "scope").font(.title).foregroundStyle(.secondary)
                Text(
                    errorText
                        ?? shotMap?.missingData.first?.reason
                        ?? "这一洞暂无落点数据"
                )
                .font(.subheadline)
                .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity).padding(.vertical, 40).hubCard()
        }
    }

    private func shotListCard(_ shotMap: RoundHoleShotMap) -> some View {
        let ppm = shotMap.map?.overlay.ppm
        return VStack(alignment: .leading, spacing: 8) {
            Text("逐杆").font(.caption).foregroundStyle(.secondary)
            ForEach(shotMap.shots) { shot in
                RoundShotRow(shot: shot, ppm: ppm)
                    .padding(.vertical, 5)
                    .overlay(alignment: .bottom) { Divider() }
            }
        }
        .hubCard()
    }

    /// Topo base-image URL for this hole's render — the physical (gid, localHole) the shot map was
    /// projected onto. nil (→ flat fallback) when the round has no course geometry or no base URL.
    private func topoURL(for shotMap: RoundHoleShotMap) -> URL? {
        guard let apiBaseURL,
              let gid = shotMap.globalId,
              let local = shotMap.localHole,
              shotMap.geometryRevision != nil,
              !shotMap.usesCourseDataFrame else { return nil }
        return SyncClient.topoImageURL(
            baseURL: apiBaseURL,
            globalId: gid,
            localHole: local,
            geometryRevision: shotMap.geometryRevision
        )
    }

    @MainActor
    private func load() async {
        if isEditing { onEditingChange?(false) }
        isEditing = false
        isSaving = false
        await mapRepository.load(hole)
        guard let apiBaseURL, let map = mapRepository.map(for: hole) else {
            editModel = nil
            return
        }
        editModel = map.found
            ? RoundEditModel(
                map: map,
                sync: SyncClient(baseURL: apiBaseURL, adminToken: adminToken),
                roundRef: roundRef
            )
            : nil
    }

    @MainActor
    private func beginEditing() {
        guard !isSaving, let editModel else { return }
        editModel.enterEdit()
        isEditing = true
        onEditingChange?(true)
    }

    @MainActor
    private func cancelEditing() {
        guard !isSaving, let editModel else { return }
        editModel.cancelEdit()
        mapRepository.store(editModel.map, for: hole)
        isEditing = false
        onEditingChange?(false)
    }

    @MainActor
    private func saveEditing() async {
        guard !isSaving, let editModel else { return }
        isSaving = true
        let saved = await editModel.save()
        isSaving = false
        guard saved else { return }
        mapRepository.store(editModel.map, for: hole)
        isEditing = false
        onEditingChange?(false)
    }
}

/// 横滑翻洞:整页左右滑过这一局每一洞的落点图(从复盘点某洞进入,停在该洞,可左右滑到相邻洞)。
public struct RoundShotMapPagerScreen: View {
    public let roundRef: String
    public let holes: [Int]
    public let apiBaseURL: URL?
    public let adminToken: String?
    public let onClose: (() -> Void)?
    @StateObject private var mapRepository: RoundShotMapRepository
    @State private var current: Int
    /// Holes currently in edit mode. Non-empty ⇒ 翻洞 is locked (设计 §1:改的模式锁切洞)。
    @State private var editingHoles: Set<Int> = []

    public init(
        roundRef: String,
        holes: [Int],
        startHole: Int,
        apiBaseURL: URL? = nil,
        adminToken: String? = nil,
        onClose: (() -> Void)? = nil
    ) {
        self.roundRef = roundRef
        self.holes = holes
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        self.onClose = onClose
        _mapRepository = StateObject(
            wrappedValue: RoundShotMapRepository(
                roundRef: roundRef,
                apiBaseURL: apiBaseURL,
                adminToken: adminToken
            )
        )
        _current = State(initialValue: holes.contains(startHole) ? startHole : (holes.first ?? startHole))
    }

    init(
        roundRef: String,
        holes: [Int],
        startHole: Int,
        apiBaseURL: URL?,
        adminToken: String?,
        onClose: (() -> Void)?,
        mapRepository: RoundShotMapRepository
    ) {
        self.roundRef = roundRef
        self.holes = holes
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        self.onClose = onClose
        _mapRepository = StateObject(wrappedValue: mapRepository)
        _current = State(initialValue: holes.contains(startHole) ? startHole : (holes.first ?? startHole))
    }

    private var isLocked: Bool { !editingHoles.isEmpty }

    public var body: some View {
        // A pinned selection binding: while editing, reject page changes so a stray horizontal swipe
        // rubber-bands back to the current hole instead of switching away mid-edit. This never touches
        // the child's own drag/tap gestures (no ancestor gesture is added), so drag-to-move still works.
        let selection = Binding(get: { current }, set: { if !isLocked { current = $0 } })
        return TabView(selection: selection) {
            ForEach(holes, id: \.self) { hole in
                RoundHoleShotMapScreen(
                    roundRef: roundRef, hole: hole,
                    apiBaseURL: apiBaseURL, adminToken: adminToken, showsNavigationTitle: false,
                    onEditingChange: { editing in
                        if editing { editingHoles.insert(hole) } else { editingHoles.remove(hole) }
                    },
                    mapRepository: mapRepository
                )
                .tag(hole)
            }
        }
        .tabViewStyle(.page(indexDisplayMode: .never))
        .background(HubStyle.grouped)
        // Editing has exactly two exits: the explicit Cancel and Save actions.  A sheet pull-down
        // must not become a third, silent way to discard the whole local draft.
        .interactiveDismissDisabled(isLocked)
        .navigationTitle(isLocked ? "第 \(current) 洞 · 编辑中" : "第 \(current) 洞 · 落点 · 左右滑")
        .task(id: roundRef) {
            await mapRepository.prefetch(holes, startingAt: current)
        }
        .onChange(of: current) { _, newHole in
            Task {
                let index = holes.firstIndex(of: newHole)
                let nearby = [
                    newHole,
                    index.flatMap { holes[safe: $0 - 1] },
                    index.flatMap { holes[safe: $0 + 1] },
                ].compactMap { $0 }
                await mapRepository.prefetch(nearby, startingAt: newHole)
            }
        }
        .toolbar {
            if !isLocked, let onClose {
                ToolbarItem(placement: .topBarLeading) {
                    Button("关闭", action: onClose)
                }
            }
        }
    }
}
