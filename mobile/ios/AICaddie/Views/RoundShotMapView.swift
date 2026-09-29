import CryptoKit
import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

/// 复盘逐洞落点图 (B3, `review.html` screen 2): the hole's real topo with every shot this round drew
/// on it — a white line per shot, a numbered dot at each landing coloured by the landing lie, a
/// "一号木 221" label beside it and "推 ×2" on the green. Coordinates are the server-projected overlay
/// pixels. Read-only it pinches / double-taps to zoom and keeps one control: show / hide labels.
public struct RoundShotMapView: View {
    public let shotMap: RoundHoleShotMap
    /// 服务端真实地形底图 URL(`…/holes/{hole}/topo.png`)。有则底图用它,否则/加载失败回退到
    /// payload 里的 flat 渲染图。两者共用同一投影,实际打球路线叠加层像素级对齐。
    public let topoURL: URL?
    /// 非 nil = 编辑态:在同一投影帧上叠一层拖柄 + 点空白加杆(见 RoundShotEditLayer)。
    public let editModel: RoundEditModel?
    /// The scorecard putt count ("推 ×N"); falls back to the putt rows on the map.
    public let putts: Int?

    @State private var showsShotFacts = true

    public init(shotMap: RoundHoleShotMap, topoURL: URL? = nil,
                editModel: RoundEditModel? = nil, putts: Int? = nil) {
        self.shotMap = shotMap
        self.topoURL = topoURL
        self.editModel = editModel
        self.putts = putts
    }

    public var body: some View {
        #if canImport(UIKit)
        if let overlay = shotMap.map?.overlay, overlay.w > 0, overlay.h > 0 {
            let ratio = CGFloat(overlay.w) / CGFloat(overlay.h)
            if let editModel {
                ZStack {
                    TopoHoleBaseImage(topoURL: topoURL, fallback: decodedImage)
                    Canvas { context, size in
                        drawRoundShotPath(&context, size: size, overlay: overlay, shots: shotMap.shots, numbered: false)
                    }
                }
                .aspectRatio(ratio, contentMode: .fit)
                .overlay {
                    RoundShotEditLayer(
                        editModel: editModel,
                        overlay: overlay,
                        baseImage: decodedImage,
                        topoURL: topoURL
                    )
                }
            } else {
                ZoomableRoundMapViewport(
                    aspectRatio: ratio,
                    showsShotFacts: $showsShotFacts
                ) {
                    ZStack {
                        TopoHoleBaseImage(topoURL: topoURL, fallback: decodedImage)
                        Canvas { context, size in
                            drawRoundShotPath(&context, size: size, overlay: overlay, shots: shotMap.shots)
                        }
                        if showsShotFacts {
                            reviewFactOverlays(overlay: overlay)
                        }
                    }
                }
            }
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

    /// Club + yards beside each real landing and the putt count on the green.
    private func reviewFactOverlays(overlay: CoursePrepOverlay) -> some View {
        GeometryReader { proxy in
            let placements = reviewFactPlacements(in: proxy.size, overlay: overlay)
            ZStack {
                ForEach(placements) { placement in
                    Text(placement.text)
                        .font(.system(size: 11, weight: .semibold))
                        .monospacedDigit()
                        .foregroundStyle(.white)
                        .lineLimit(1)
                        .fixedSize()
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color(red: 16 / 255, green: 20 / 255, blue: 18 / 255).opacity(0.82), in: Capsule())
                        .overlay(Capsule().stroke(Color.white.opacity(0.16), lineWidth: 0.5))
                        .position(placement.point)
                        .accessibilityLabel(placement.accessibilityText)
                        .accessibilityIdentifier(
                            placement.isPutt ? "round-map-putts" : "round-map-shot-\(placement.id)"
                        )
                }
                if shotMap.manualPenalty > 0 {
                    Text("罚杆 +\(shotMap.manualPenalty)")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(Color(red: 0.043, green: 0.059, blue: 0.047))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(LivePlayStyle.hazard, in: Capsule())
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)
                        .padding(10)
                        .accessibilityIdentifier("round-map-penalty")
                }
            }
            .allowsHitTesting(false)
        }
    }

    private struct ReviewFactPlacement: Identifiable {
        let id: String
        let text: String
        let accessibilityText: String
        let lane: Int
        let isPutt: Bool
        var point: CGPoint
    }

    /// Keep labels close to their real landing while preventing two nearby shots (most often the
    /// final approach and a short miss around the green) from drawing capsules on top of each other.
    /// Resolve collisions independently on the left/right label lanes, then clamp inside the map.
    private func reviewFactPlacements(in size: CGSize, overlay: CoursePrepOverlay) -> [ReviewFactPlacement] {
        var placements: [ReviewFactPlacement] = []
        for (index, shot) in nonPuttShots.enumerated() {
            guard let anchor = mapPoint(shot.end, in: size, overlay: overlay),
                  let text = roundShotLabelText(shot, ppm: overlay.ppm) else { continue }
            placements.append(
                ReviewFactPlacement(
                    id: shot.id,
                    text: text,
                    accessibilityText: "第 \(index + 1) 杆 \(text)",
                    lane: anchor.x < size.width * 0.58 ? 0 : 1,
                    isPutt: false,
                    point: reviewLabelPoint(anchor, index: index, in: size)
                )
            )
        }
        if let puttCount, puttCount > 0, let anchor = greenAnchor(in: size, overlay: overlay) {
            placements.append(
                ReviewFactPlacement(
                    id: "putts",
                    text: "推 ×\(puttCount)",
                    accessibilityText: "推杆 \(puttCount) 次",
                    lane: anchor.x < size.width * 0.58 ? 0 : 1,
                    isPutt: true,
                    point: reviewLabelPoint(anchor, index: nonPuttShots.count, in: size)
                )
            )
        }

        let minimumY: CGFloat = 24
        let maximumY = max(minimumY, size.height - 24)
        let spacing: CGFloat = 26
        for lane in 0...1 {
            let indices = placements.indices
                .filter { placements[$0].lane == lane }
                .sorted { placements[$0].point.y < placements[$1].point.y }
            var previousY = minimumY - spacing
            for index in indices {
                let resolved = min(max(placements[index].point.y, previousY + spacing), maximumY)
                placements[index].point.y = resolved
                previousY = resolved
            }
            guard let last = indices.last, placements[last].point.y >= maximumY else { continue }
            var nextY = maximumY + spacing
            for index in indices.reversed() {
                let resolved = max(min(placements[index].point.y, nextY - spacing), minimumY)
                placements[index].point.y = resolved
                nextY = resolved
            }
        }
        return placements
    }

    private var nonPuttShots: [RoundShot] {
        shotMap.shots.filter { !roundShotIsPutt($0) && !$0.synthetic && $0.end != nil }
    }

    private var puttCount: Int? {
        if let putts { return putts }
        let rows = shotMap.shots.filter(roundShotIsPutt).count
        return rows > 0 ? rows : nil
    }

    private func greenAnchor(in size: CGSize, overlay: CoursePrepOverlay) -> CGPoint? {
        let puttEnd = shotMap.shots.reversed().first(where: { roundShotIsPutt($0) && $0.end != nil })?.end
        return mapPoint(puttEnd ?? overlay.route.last.map { [Int($0[0]), Int($0[1])] }, in: size, overlay: overlay)
    }

    private func mapPoint(_ row: [Int]?, in size: CGSize, overlay: CoursePrepOverlay) -> CGPoint? {
        guard let row, row.count >= 2, overlay.w > 0, overlay.h > 0 else { return nil }
        return CGPoint(
            x: CGFloat(row[0]) / CGFloat(overlay.w) * size.width,
            y: CGFloat(row[1]) / CGFloat(overlay.h) * size.height
        )
    }

    private func reviewLabelPoint(_ anchor: CGPoint, index: Int, in size: CGSize) -> CGPoint {
        let xShift: CGFloat = anchor.x < size.width * 0.58 ? 52 : -52
        let yShift: CGFloat = index.isMultiple(of: 2) ? -12 : 14
        return CGPoint(
            x: min(max(anchor.x + xShift, 50), size.width - 50),
            y: min(max(anchor.y + yShift, 24), size.height - 24)
        )
    }
}

#if canImport(UIKit)
/// Pinch / pan / double-tap viewport used only by the read-only map. Edit mode keeps the unscaled
/// coordinate plane so its landing drags stay pixel-authoritative. The one control left on the map is
/// 显示 / 隐藏标签 (README §7: no simple-map layer switch).
private struct ZoomableRoundMapViewport<Content: View>: View {
    let aspectRatio: CGFloat
    @Binding var showsShotFacts: Bool
    let content: Content

    @State private var scale: CGFloat = 1
    @State private var offset: CGSize = .zero
    @GestureState private var pinchScale: CGFloat = 1
    @GestureState private var dragOffset: CGSize = .zero

    private var displayedScale: CGFloat {
        min(max(scale * pinchScale, 1), 4)
    }

    init(
        aspectRatio: CGFloat,
        showsShotFacts: Binding<Bool>,
        @ViewBuilder content: () -> Content
    ) {
        self.aspectRatio = aspectRatio
        _showsShotFacts = showsShotFacts
        self.content = content()
    }

    var body: some View {
        GeometryReader { proxy in
            let size = proxy.size
            let proposedOffset = CGSize(
                width: offset.width + dragOffset.width,
                height: offset.height + dragOffset.height
            )
            ZStack(alignment: .bottomTrailing) {
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
                    .onTapGesture(count: 2) { toggleZoom() }
                    .accessibilityHint("双指缩放，放大后拖动；双击放大或还原")

                // Zoom state for assistive tech and UI tests (the accessibility frame ignores
                // `scaleEffect`).
                Color.clear
                    .frame(width: 1, height: 1)
                    .accessibilityElement()
                    .accessibilityLabel("地图缩放")
                    .accessibilityValue(displayedScale > 1.01 ? "已放大" : "全洞")
                    .accessibilityIdentifier("round-map-zoom-state")
                    .allowsHitTesting(false)
                Button {
                    showsShotFacts.toggle()
                } label: {
                    Image(systemName: showsShotFacts ? "text.bubble.fill" : "text.bubble")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(.white)
                        .frame(width: 40, height: 40)
                        .background(.ultraThinMaterial, in: Circle())
                        .environment(\.colorScheme, .dark)
                }
                .buttonStyle(.plain)
                .padding(10)
                .accessibilityLabel(showsShotFacts ? "隐藏标签" : "显示标签")
                .accessibilityIdentifier("round-map-labels")
            }
        }
        .aspectRatio(aspectRatio, contentMode: .fit)
        .clipped()
    }

    private func toggleZoom() {
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

func roundShotIsPutt(_ shot: RoundShot) -> Bool {
    (shot.shotType ?? "").uppercased() == "PUTT"
        || (shot.club ?? "").localizedCaseInsensitiveContains("putt")
        || (shot.club ?? "").contains("推")
}

/// "一号木 221" / "221码" / "一号木" — nil when neither the club nor the distance is known.
func roundShotLabelText(_ shot: RoundShot, ppm: Double?) -> String? {
    let raw = shot.club?.trimmingCharacters(in: .whitespacesAndNewlines)
    let club = raw.flatMap { $0.isEmpty || $0.lowercased() == "unknown" ? nil : zhClubName($0) }
    let yards = roundShotYards(shot, ppm: ppm)
    switch (club, yards) {
    case let (club?, yards?): return "\(club) \(yards)"
    case let (club?, nil): return club
    case let (nil, yards?): return "\(yards)码"
    default: return nil
    }
}

/// Shared shot-path rendering (white path + tee ring + numbered landing dots), factored out of
/// ``RoundShotMapView`` so the drag magnifier (``MagnifierLoupe``) draws the exact same picture —
/// magnified — over the exact same projection. Edit mode draws its own draggable handles instead
/// of the numbers.
func drawRoundShotPath(
    _ context: inout GraphicsContext,
    size: CGSize,
    overlay: CoursePrepOverlay,
    shots: [RoundShot],
    numbered: Bool = true
) {
    let sx = size.width / CGFloat(max(overlay.w, 1))
    let sy = size.height / CGFloat(max(overlay.h, 1))
    func point(_ p: [Int]?) -> CGPoint? {
        guard let p, p.count >= 2 else { return nil }
        return CGPoint(x: CGFloat(p[0]) * sx, y: CGFloat(p[1]) * sy)
    }
    // One bright route over the course art. A dark halo keeps the white path legible over sand and
    // pale greens; synthetic (auto-filled) shots stay dashed + faded.
    for shot in shots where !roundShotIsPutt(shot) {
        guard let a = point(shot.start), let b = point(shot.end) else { continue }
        var path = Path()
        path.move(to: a)
        path.addLine(to: b)
        let width: CGFloat = shot.synthetic ? 2.5 : 3.0
        context.stroke(path, with: .color(.black.opacity(0.30)),
                       style: StrokeStyle(lineWidth: width + 1.6, lineCap: .round, lineJoin: .round))
        let line = StrokeStyle(lineWidth: width, lineCap: .round, lineJoin: .round, dash: shot.synthetic ? [5, 5] : [])
        context.stroke(path, with: .color(.white.opacity(shot.synthetic ? 0.68 : 0.96)), style: line)
    }

    // Tee marker: a hollow ring in the tee colour (the start of the hole).
    if let tee = point(shots.first?.start) {
        context.stroke(Path(ellipseIn: CGRect(x: tee.x - 6, y: tee.y - 6, width: 12, height: 12)),
                       with: .color(reviewLieColor("teebox")), style: StrokeStyle(lineWidth: 2.5))
    }

    // Numbered dot at each full shot's landing: dark fill, landing-lie ring, white number.
    let fullShots = shots.filter { !roundShotIsPutt($0) }
    for (index, shot) in fullShots.enumerated() {
        guard let b = point(shot.end) else { continue }
        let radius: CGFloat = 9
        let rect = CGRect(x: b.x - radius, y: b.y - radius, width: radius * 2, height: radius * 2)
        let next = fullShots.indices.contains(index + 1) ? fullShots[index + 1] : nil
        context.fill(Path(ellipseIn: rect), with: .color(Color(red: 16 / 255, green: 20 / 255, blue: 18 / 255)))
        context.stroke(Path(ellipseIn: rect), with: .color(reviewLieColor(roundShotLandingLie(shot, next: next))),
                       style: StrokeStyle(lineWidth: 2))
        if numbered {
            context.draw(
                Text("\(index + 1)")
                    .font(.system(size: 10, weight: .bold))
                    .monospacedDigit()
                    .foregroundColor(.white),
                at: b
            )
        }
    }
}

/// Where a shot came to rest: its observed landing lie, else where the next shot was played from.
func roundShotLandingLie(_ shot: RoundShot, next: RoundShot?) -> String? {
    if let lie = shot.endLie, !lie.isEmpty, lie.lowercased() != "unknown" { return lie }
    return next?.lie
}

/// Landing-lie colours of `review.html` (tee lilac, fairway light green, rough deep green, bunker
/// sand, green pale green); water blue; anything unknown a neutral grey.
public func reviewLieColor(_ lie: String?) -> Color {
    switch (lie ?? "").lowercased() {
    case "teebox", "tee": return Color(red: 201 / 255, green: 194 / 255, blue: 242 / 255)
    case "fairway": return Color(red: 139 / 255, green: 224 / 255, blue: 143 / 255)
    case "rough", "trees", "tree_area": return Color(red: 47 / 255, green: 138 / 255, blue: 69 / 255)
    case "bunker", "sand": return Color(red: 233 / 255, green: 214 / 255, blue: 160 / 255)
    case "green", "fringe": return Color(red: 216 / 255, green: 247 / 255, blue: 184 / 255)
    case "water", "hazard": return Color(red: 92 / 255, green: 176 / 255, blue: 255 / 255)
    default: return Color.white.opacity(0.55)
    }
}

/// 球位中文(未知/缺失 → 「—」,不编造)。共享给地图标签与编辑底栏。
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
public func roundShotYards(_ shot: RoundShot, ppm: Double?) -> Int? {
    if (shot.shotType ?? "").uppercased() == "PUTT" || (shot.club ?? "").contains("推") { return nil }
    return RoundEditModel.yards(from: shot.start, to: shot.end, ppm: ppm)
}

/// One round-level memory + disk cache. The visible pager renders exactly one hole; this repository
/// prefetches data without creating hidden SwiftUI pages or competing toolbars.
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
    private let globalId: Int?
    private let backGlobalId: Int?
    private let nine: String?
    private let teeBox: String?
    private let client: SyncClient?
    private var inFlight: [Int: Task<LoadResult, Never>] = [:]

    init(roundRef: String, apiBaseURL: URL?, adminToken: String?, globalId: Int? = nil, backGlobalId: Int? = nil, nine: String? = nil, teeBox: String? = nil) {
        self.roundRef = roundRef
        self.client = apiBaseURL.map { SyncClient(baseURL: $0, adminToken: adminToken) }
        self.globalId = globalId
        self.backGlobalId = backGlobalId
        self.nine = nine
        self.teeBox = teeBox
    }

    func map(for hole: Int) -> RoundHoleShotMap? { maps[hole] }

    func isLoading(_ hole: Int) -> Bool {
        maps[hole] == nil && errors[hole] == nil
    }

    func error(for hole: Int) -> String? { errors[hole] }

    func store(_ map: RoundHoleShotMap, for hole: Int) {
        maps[hole] = map
        errors[hole] = nil
        RoundReviewDiskCache.saveShotMap(map, roundRef: roundRef, hole: hole)
        prefetchTopo(for: map)
    }

    func load(_ hole: Int, revalidate: Bool = false) async {
        if maps[hole] == nil,
           let cached = RoundReviewDiskCache.loadShotMap(roundRef: roundRef, hole: hole) {
            maps[hole] = cached
            errors[hole] = nil
            prefetchTopo(for: cached)
            if !revalidate { return }
        }
        guard maps[hole] == nil || revalidate else { return }
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
            task = Task { [roundRef, globalId, backGlobalId, nine, teeBox] in
                do {
                    return .success(try await client.fetchRoundShotMap(roundRef: roundRef, hole: hole, globalId: globalId, backGlobalId: backGlobalId, nine: nine, teeBox: teeBox))
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
            RoundReviewDiskCache.saveShotMap(map, roundRef: roundRef, hole: hole)
            prefetchTopo(for: map)
        case .failure:
            if maps[hole] == nil { errors[hole] = "这一洞落点暂时取不到" }
        }
    }

    /// Current/start hole first, then neighbours, then the rest. Two concurrent calls are enough to
    /// warm a round without recreating the request storm that made the old 18-page TabView flash.
    func prefetch(
        _ holes: [Int],
        startingAt startHole: Int? = nil,
        revalidate: Bool = false
    ) async {
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

        for index in stride(from: 0, to: ordered.count, by: 2) {
            guard !Task.isCancelled else { return }
            let batch = Array(ordered[index..<min(index + 2, ordered.count)])
            await withTaskGroup(of: Void.self) { group in
                for hole in batch {
                    group.addTask { await self.load(hole, revalidate: revalidate) }
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

/// One hole of the review, full screen (`review.html` screen 2): the topo with this round's shots,
/// a glass score box on top (第 N 洞 · Par, the score symbol, 推 / 罚) with 编辑, and the 18-hole
/// score strip at the bottom. 编辑 turns the same screen into the editor (README §7): numbered dots
/// become drag handles, a tap on empty ground adds a shot, and the bottom strip becomes the edit bar.
/// No cache status, no legend, no separate precision page.
public struct RoundHoleShotMapScreen: View {
    public let roundRef: String
    public let hole: Int
    public let apiBaseURL: URL?
    public let adminToken: String?
    public let globalId: Int?
    public let backGlobalId: Int?
    public let nine: String?
    public let teeBox: String?
    /// The round's scorecard (score box, putts, strip). Empty for a standalone screen.
    public let scorecard: [RoundDetailHole]
    /// Holes the strip offers (played holes); empty hides the strip.
    public let stripHoles: [Int]
    public let onSelectHole: ((Int) -> Void)?
    public let onClose: (() -> Void)?
    /// Called when this hole enters/leaves edit mode, so the pager can lock horizontal 翻洞 while
    /// editing (改的模式锁切洞，免误触换洞).
    public let onEditingChange: ((Bool) -> Void)?
    public let onSaved: (() -> Void)?
    /// The round detail's canonical id (putt corrections target `{canonical}:{hole}`).
    let canonicalRoundRef: String?

    @StateObject private var mapRepository: RoundShotMapRepository
    @State private var editModel: RoundEditModel?
    @State private var isEditing = false
    @State private var isSaving = false

    public init(roundRef: String, hole: Int, apiBaseURL: URL? = nil, adminToken: String? = nil, globalId: Int? = nil, backGlobalId: Int? = nil, nine: String? = nil, teeBox: String? = nil,
                scorecard: [RoundDetailHole] = [], onClose: (() -> Void)? = nil, onEditingChange: ((Bool) -> Void)? = nil) {
        self.init(
            roundRef: roundRef, hole: hole, apiBaseURL: apiBaseURL, adminToken: adminToken,
            scorecard: scorecard, stripHoles: [], onSelectHole: nil, onClose: onClose,
            onEditingChange: onEditingChange, onSaved: nil,
            mapRepository: RoundShotMapRepository(
                roundRef: roundRef,
                apiBaseURL: apiBaseURL,
                adminToken: adminToken,
                globalId: globalId,
                backGlobalId: backGlobalId,
                nine: nine,
                teeBox: teeBox
            ),
            globalId: globalId, backGlobalId: backGlobalId, nine: nine, teeBox: teeBox
        )
    }

    init(roundRef: String, hole: Int, apiBaseURL: URL?, adminToken: String?,
         scorecard: [RoundDetailHole], stripHoles: [Int], onSelectHole: ((Int) -> Void)?,
         onClose: (() -> Void)?, onEditingChange: ((Bool) -> Void)?, onSaved: (() -> Void)?,
         mapRepository: RoundShotMapRepository, globalId: Int? = nil, backGlobalId: Int? = nil, nine: String? = nil, teeBox: String? = nil,
         canonicalRoundRef: String? = nil) {
        self.roundRef = roundRef
        self.hole = hole
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        self.globalId = globalId
        self.backGlobalId = backGlobalId
        self.nine = nine
        self.teeBox = teeBox
        self.scorecard = scorecard
        self.stripHoles = stripHoles
        self.onSelectHole = onSelectHole
        self.onClose = onClose
        self.onEditingChange = onEditingChange
        self.onSaved = onSaved
        self.canonicalRoundRef = canonicalRoundRef
        _mapRepository = StateObject(wrappedValue: mapRepository)
    }

    private var shotMap: RoundHoleShotMap? { mapRepository.map(for: hole) }
    private var isLoading: Bool { mapRepository.isLoading(hole) }
    private var errorText: String? { mapRepository.error(for: hole) }
    private var scoreRow: RoundDetailHole? { scorecard.first { $0.hole == hole } }

    public var body: some View {
        ZStack {
            RoundHoleMapStyle.base.ignoresSafeArea()
            if isLoading {
                ProgressView("载入落点…")
                    .tint(.white)
                    .foregroundStyle(LivePlayStyle.ink60)
            } else {
                content
            }
        }
        .safeAreaInset(edge: .top, spacing: 0) { topBar }
        .safeAreaInset(edge: .bottom, spacing: 0) { bottomBar }
        .preferredColorScheme(.dark)
        .toolbar(.hidden, for: .navigationBar)
        .task(id: hole) { await load() }
        .onChange(of: scoreRow?.putts) { _, putts in
            editModel?.adoptRecordedPutts(putts)
        }
        .onDisappear {
            guard isEditing else { return }
            editModel?.cancelEdit()
            isEditing = false
            isSaving = false
            onEditingChange?(false)
        }
    }

    // MARK: map / fallbacks

    @ViewBuilder private var content: some View {
        if isEditing, let editModel {
            if editModel.canEditPositions {
                RoundShotEditMap(editModel: editModel, topoURL: topoURL(for: editModel.map))
                    .allowsHitTesting(!isSaving)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                RoundShotFactEditList(editModel: editModel)
                    .allowsHitTesting(!isSaving)
            }
        } else if let shotMap, shotMap.found, shotMap.map != nil {
            RoundShotMapView(shotMap: shotMap, topoURL: topoURL(for: shotMap), putts: scoreRow?.putts)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let shotMap, shotMap.found, !shotMap.shots.isEmpty {
            ScrollView {
                RoundShotFactList(shots: shotMap.shots, ppm: shotMap.map?.overlay.ppm)
                    .padding(16)
            }
        } else {
            VStack(spacing: 10) {
                Image(systemName: "scope").font(.title).foregroundStyle(LivePlayStyle.ink45)
                Text(errorText ?? "这一洞没有落点")
                    .font(.subheadline)
                    .foregroundStyle(LivePlayStyle.ink60)
                if errorText != nil {
                    Button {
                        Task { await load() }
                    } label: {
                        Label("重新载入这一洞", systemImage: "arrow.clockwise")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(LivePlayStyle.ink)
                            .padding(.horizontal, 16)
                            .frame(height: 40)
                            .background(LivePlayStyle.fill12, in: Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("round-shot-map-retry")
                }
            }
            .padding(24)
        }
    }

    // MARK: top score box

    private var topBar: some View {
        HStack(alignment: .top, spacing: 10) {
            if !isEditing, let onClose {
                glassButton(system: "xmark", label: "关闭", identifier: "round-shot-map-close", action: onClose)
            }
            if isEditing, let editModel {
                RoundHoleDraftScoreBox(hole: hole, par: scoreRow?.par ?? shotMap?.par, row: scoreRow, editModel: editModel)
            } else {
                RoundHoleScoreBox(hole: hole, par: scoreRow?.par ?? shotMap?.par, row: scoreRow,
                                  putts: scoreRow?.putts, penalties: scoreRow?.penalties)
            }
            Spacer(minLength: 0)
            if isEditing {
                HStack(spacing: 8) {
                    pill("取消", filled: false, identifier: "round-edit-cancel") { cancelEditing() }
                        .disabled(isSaving)
                    pill(isSaving ? "保存中…" : "保存", filled: true, identifier: "round-edit-save") {
                        Task { await saveEditing() }
                    }
                    .disabled(isSaving)
                }
            } else if let shotMap, shotMap.found, editModel != nil {
                pill("编辑", filled: false, identifier: "round-edit-begin") { beginEditing() }
            }
        }
        .padding(.horizontal, 14)
        .padding(.top, 6)
        .padding(.bottom, 8)
    }

    private func pill(_ title: String, filled: Bool, identifier: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 15, weight: .bold))
                .foregroundStyle(filled ? LiveScoreStyle.primaryInk : LivePlayStyle.ink)
                .padding(.horizontal, 16)
                .frame(height: 38)
                .background {
                    if filled {
                        Capsule().fill(LiveScoreStyle.primaryFill)
                    } else {
                        Capsule().fill(.ultraThinMaterial)
                    }
                }
                .overlay(Capsule().stroke(LivePlayStyle.stroke14, lineWidth: filled ? 0 : 0.5))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(identifier)
    }

    private func glassButton(system: String, label: String, identifier: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: system)
                .font(.system(size: 14, weight: .bold))
                .foregroundStyle(LivePlayStyle.ink)
                .frame(width: 38, height: 38)
                .background(.ultraThinMaterial, in: Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
        .accessibilityIdentifier(identifier)
    }

    // MARK: bottom strip / edit bar

    @ViewBuilder private var bottomBar: some View {
        if isEditing, let editModel {
            RoundShotEditBar(editModel: editModel)
                .disabled(isSaving)
        } else if !stripHoles.isEmpty, let onSelectHole {
            RoundHoleScoreStrip(holes: stripHoles, current: hole, scorecard: scorecard, onSelect: onSelectHole)
        }
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
                roundRef: roundRef,
                globalId: globalId,
                backGlobalId: backGlobalId,
                nine: nine,
                teeBox: teeBox,
                putts: scoreRow?.putts,
                puttTargetRoundRef: canonicalRoundRef
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
        onSaved?()
    }
}

enum RoundHoleMapStyle {
    static let base = Color(red: 11 / 255, green: 15 / 255, blue: 12 / 255)
}

/// The edit-mode map: observes the draft so every drag, add and delete redraws the path underneath
/// the handles.
struct RoundShotEditMap: View {
    @ObservedObject var editModel: RoundEditModel
    let topoURL: URL?

    var body: some View {
        RoundShotMapView(shotMap: editModel.map, topoURL: topoURL, editModel: editModel)
    }
}

/// While editing, the score box follows the draft's putts and penalty.
struct RoundHoleDraftScoreBox: View {
    let hole: Int
    let par: Int?
    let row: RoundDetailHole?
    @ObservedObject var editModel: RoundEditModel

    var body: some View {
        RoundHoleScoreBox(hole: hole, par: par, row: row, putts: editModel.putts, penalties: editModel.map.manualPenalty)
    }
}

/// The glass box on top of a hole: 第 N 洞 · Par P, the score symbol and its name, 推 / 罚.
struct RoundHoleScoreBox: View {
    let hole: Int
    let par: Int?
    let row: RoundDetailHole?
    let putts: Int?
    let penalties: Int?

    var body: some View {
        HStack(spacing: 10) {
            if let score = row?.score {
                ScoreChip(score: score, toPar: par.map { score - $0 }, size: 34, dark: true)
            }
            VStack(alignment: .leading, spacing: 1) {
                Text(par.map { "第 \(hole) 洞 · Par \($0)" } ?? "第 \(hole) 洞")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundStyle(LivePlayStyle.ink)
                    .lineLimit(1)
                Text(detail)
                    .font(.system(size: 12))
                    .monospacedDigit()
                    .foregroundStyle(LivePlayStyle.ink60)
                    .lineLimit(1)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(LivePlayStyle.stroke14, lineWidth: 0.5))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("round-shot-score-box")
    }

    private var detail: String {
        var parts: [String] = []
        if let score = row?.score, let par {
            parts.append(ScoreChip.name(toPar: score - par))
        }
        if let putts { parts.append("推 \(putts)") }
        if let penalties, penalties > 0 { parts.append("罚 \(penalties)") }
        return parts.isEmpty ? "没有成绩" : parts.joined(separator: " · ")
    }
}

/// Bottom 18-hole strip: each hole's number over its score symbol; tap to change hole.
struct RoundHoleScoreStrip: View {
    let holes: [Int]
    let current: Int
    let scorecard: [RoundDetailHole]
    let onSelect: (Int) -> Void

    var body: some View {
        ScrollViewReader { reader in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 4) {
                    ForEach(holes, id: \.self) { hole in
                        cell(hole).id(hole)
                    }
                }
                .padding(.horizontal, 12)
            }
            .onAppear { reader.scrollTo(current, anchor: .center) }
        }
        .frame(height: 60)
        .padding(.vertical, 6)
        .background(.ultraThinMaterial)
        .environment(\.colorScheme, .dark)
    }

    private func cell(_ hole: Int) -> some View {
        let row = scorecard.first { $0.hole == hole }
        let selected = hole == current
        return Button { onSelect(hole) } label: {
            VStack(spacing: 3) {
                Text("\(hole)")
                    .font(.system(size: 11, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(selected ? LiveScoreStyle.primaryInk.opacity(0.7) : LivePlayStyle.ink45)
                if let score = row?.score {
                    ScoreChip(
                        score: score,
                        toPar: row?.par.map { score - $0 },
                        size: 24,
                        dark: true,
                        ink: selected ? LiveScoreStyle.primaryInk : nil
                    )
                } else {
                    Text("–")
                        .font(.system(size: 13, weight: .bold))
                        .foregroundStyle(LivePlayStyle.ink45)
                        .frame(height: 24)
                }
            }
            .frame(width: 40, height: 52)
            .background(
                selected ? LiveScoreStyle.primaryFill : LivePlayStyle.fill08,
                in: RoundedRectangle(cornerRadius: 11, style: .continuous)
            )
        }
        .buttonStyle(.plain)
        .accessibilityLabel(row?.score.map { "第 \(hole) 洞，\($0) 杆" } ?? "第 \(hole) 洞")
        .accessibilityAddTraits(selected ? [.isSelected] : [])
        .accessibilityIdentifier("round-hole-strip-\(hole)")
    }
}

/// One visible hole at a time; swipe or the bottom strip changes hole. Editing locks both, and the
/// sheet cannot be pulled away while a draft is open.
public struct RoundShotMapPagerScreen: View {
    public let roundRef: String
    public let holes: [Int]
    public let apiBaseURL: URL?
    public let adminToken: String?
    public let globalId: Int?
    public let backGlobalId: Int?
    public let nine: String?
    public let teeBox: String?
    public let scorecard: [RoundDetailHole]
    public let onClose: (() -> Void)?
    public let onSaved: (() -> Void)?
    let canonicalRoundRef: String?
    @StateObject private var mapRepository: RoundShotMapRepository
    @State private var current: Int
    /// Holes currently in edit mode. Non-empty ⇒ 翻洞 is locked.
    @State private var editingHoles: Set<Int> = []

    public init(
        roundRef: String,
        holes: [Int],
        startHole: Int,
        apiBaseURL: URL? = nil,
        adminToken: String? = nil,
        globalId: Int? = nil,
        backGlobalId: Int? = nil,
        nine: String? = nil,
        teeBox: String? = nil,
        scorecard: [RoundDetailHole] = [],
        onClose: (() -> Void)? = nil,
        onSaved: (() -> Void)? = nil
    ) {
        self.init(
            roundRef: roundRef, holes: holes, startHole: startHole,
            apiBaseURL: apiBaseURL, adminToken: adminToken, onClose: onClose,
            mapRepository: RoundShotMapRepository(
                roundRef: roundRef,
                apiBaseURL: apiBaseURL,
                adminToken: adminToken,
                globalId: globalId,
                backGlobalId: backGlobalId,
                nine: nine,
                teeBox: teeBox
            ),
            globalId: globalId, backGlobalId: backGlobalId, nine: nine, teeBox: teeBox,
            scorecard: scorecard, onSaved: onSaved
        )
    }

    init(
        roundRef: String,
        holes: [Int],
        startHole: Int,
        apiBaseURL: URL?,
        adminToken: String?,
        onClose: (() -> Void)?,
        mapRepository: RoundShotMapRepository,
        globalId: Int? = nil,
        backGlobalId: Int? = nil,
        nine: String? = nil,
        teeBox: String? = nil,
        scorecard: [RoundDetailHole] = [],
        onSaved: (() -> Void)? = nil,
        canonicalRoundRef: String? = nil
    ) {
        self.roundRef = roundRef
        self.holes = holes
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
        self.globalId = globalId
        self.backGlobalId = backGlobalId
        self.nine = nine
        self.teeBox = teeBox
        self.scorecard = scorecard
        self.onClose = onClose
        self.onSaved = onSaved
        self.canonicalRoundRef = canonicalRoundRef
        _mapRepository = StateObject(wrappedValue: mapRepository)
        _current = State(initialValue: holes.contains(startHole) ? startHole : (holes.first ?? startHole))
    }

    private var isLocked: Bool { !editingHoles.isEmpty }

    public var body: some View {
        RoundHoleShotMapScreen(
            roundRef: roundRef,
            hole: current,
            apiBaseURL: apiBaseURL,
            adminToken: adminToken,
            scorecard: scorecard,
            stripHoles: holes,
            onSelectHole: { hole in
                guard !isLocked else { return }
                current = hole
            },
            onClose: onClose,
            onEditingChange: { editing in
                if editing { editingHoles.insert(current) } else { editingHoles.remove(current) }
            },
            onSaved: onSaved,
            mapRepository: mapRepository,
            globalId: globalId,
            backGlobalId: backGlobalId,
            nine: nine,
            teeBox: teeBox,
            canonicalRoundRef: canonicalRoundRef
        )
        .id("\(roundRef):\(current)")
        .gesture(
            DragGesture(minimumDistance: 24)
                .onEnded { value in
                    guard let target = HoleSwipeNavigation.target(
                        current: current,
                        holes: holes,
                        translation: value.translation,
                        enabled: !isLocked
                    ) else { return }
                    withAnimation(.easeInOut(duration: 0.18)) {
                        current = target
                    }
                },
            including: isLocked ? .none : .all
        )
        // Editing has exactly two exits: the explicit Cancel and Save actions. A pull-down must not
        // become a third, silent way to discard the whole local draft.
        .interactiveDismissDisabled(isLocked)
        .task(id: roundRef) {
            await mapRepository.load(current)
            await mapRepository.load(current, revalidate: true)
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
    }
}

enum RoundReviewDiskCache {
    private static let decoder = JSONDecoder()
    private static let encoder = JSONEncoder()

    static func loadDetail(roundRef: String) -> RoundDetail? {
        load(RoundDetail.self, from: url(roundRef: roundRef, fileName: "detail.json"))
    }

    static func saveDetail(_ detail: RoundDetail, roundRef: String) {
        save(detail, to: url(roundRef: roundRef, fileName: "detail.json"))
    }

    static func loadShotMap(roundRef: String, hole: Int) -> RoundHoleShotMap? {
        load(RoundHoleShotMap.self, from: url(roundRef: roundRef, fileName: "hole-\(hole).json"))
    }

    static func saveShotMap(_ map: RoundHoleShotMap, roundRef: String, hole: Int) {
        save(map, to: url(roundRef: roundRef, fileName: "hole-\(hole).json"))
    }

    private static func load<T: Decodable>(_ type: T.Type, from url: URL) -> T? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? decoder.decode(type, from: data)
    }

    private static func save<T: Encodable>(_ value: T, to url: URL) {
        guard let data = try? encoder.encode(value) else { return }
        try? FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try? data.write(to: url, options: [.atomic])
    }

    private static func url(roundRef: String, fileName: String) -> URL {
        let root = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("AICaddieRoundReview-v3", isDirectory: true)
        // A round reference is not globally unique across backend members. Bind every review byte
        // to the currently signed-in player so signing out/in can never show another account's
        // cached scorecard or shot positions. DEBUG without Apple auth receives its own scope.
        let playerScope = SessionStore.shared.currentSession?.playerId ?? "debug-no-session"
        let safePlayer = digest(playerScope)
        let safeRef = digest(roundRef)
        return root.appendingPathComponent(safePlayer, isDirectory: true)
            .appendingPathComponent(safeRef, isDirectory: true)
            .appendingPathComponent(fileName)
    }

    private static func digest(_ value: String) -> String {
        SHA256.hash(data: Data(value.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
    }
}
