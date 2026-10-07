import CoreGraphics
import Foundation

/// One hole of the full-screen 备战 (README §8, `pre-round.html` 第三台). It is resolved once per
/// install change from the local course template, never per render: which facts exist, which local
/// topo is installed, therefore which state of the map degradation contract the hole shows, and the
/// caddie plans for the hole.
struct PrepHoleRow: Equatable, Identifiable {
    /// The template hole number (on a whole-course template also the physical hole).
    let number: Int
    /// B4b-2 presentation number (`Hole.courseHoleNumber`), the only number the player sees.
    let displayNumber: Int
    let par: Int?
    let yards: Int?
    let prep: CoursePrepHole?
    /// Revision-bound installed topo; used only in the `.precise` state.
    let topoURL: URL?
    let state: LiveMapDisplayState
    /// The hole's caddie plans (方案), in the decision authority's order.
    var plans: [PrepPlanOption] = []

    var id: Int { number }
}

enum PrepHoleRows {
    /// Rows for every hole of the installed (possibly still downloading) whole-course template.
    /// Before the template exists the course's hole count gives waiting rows, so a selected course
    /// opens at once (选了就进) and fills in hole by hole.
    static func build(
        template: LiveRoundPackage?,
        fallbackHoleCount: Int,
        downloadActive: Bool,
        requiredRevisions: [String: String]?,
        topoURL: (Hole, String?) -> URL?
    ) -> [PrepHoleRow] {
        guard let template, !template.holes.isEmpty else {
            return (1...max(1, fallbackHoleCount)).map { number in
                PrepHoleRow(
                    number: number,
                    displayNumber: number,
                    par: nil,
                    yards: nil,
                    prep: nil,
                    topoURL: nil,
                    state: .waiting
                )
            }
        }
        return template.holes.sorted { $0.number < $1.number }.map { hole -> PrepHoleRow in
            let prep = template.coursePrep?.holes.first { $0.hole == hole.number }
            let revision = prep?.geometryRevision ?? hole.geometryRevision
            let stale = isStale(hole: hole, installedRevision: revision, required: requiredRevisions)
            // The topo bitmap is keyed by the hole's geometry revision, not the Tee, so a Tee whose
            // prep is still lightweight shows the same downloaded map (device review, build 77:
            // switching 蓝 T → 白 T dropped the map).
            let topo = prep == nil || stale
                ? nil
                : (topoURL(hole, revision) ?? holeRevisionTopo(hole, revision: revision, topoURL: topoURL))
            let state = LiveMapDisplayState.resolvePrep(
                prep: prep,
                hasLocalTopo: topo != nil,
                isStale: stale,
                downloadActive: downloadActive
            )
            return PrepHoleRow(
                number: hole.number,
                displayNumber: hole.courseHoleNumber,
                par: prep?.par ?? hole.par,
                yards: prep?.playingYards ?? hole.yards,
                prep: prep,
                topoURL: topo,
                state: state,
                plans: state == .waiting ? [] : PrepPlanOption.options(template: template, hole: hole, prep: prep)
            )
        }
    }

    /// The hole's own revision, when it names a different bitmap than the prep row's token.
    private static func holeRevisionTopo(
        _ hole: Hole,
        revision: String?,
        topoURL: (Hole, String?) -> URL?
    ) -> URL? {
        guard let holeRevision = hole.geometryRevision, holeRevision != revision else { return nil }
        return topoURL(hole, holeRevision)
    }

    /// A revision the server positively replaced (`PrepCourseDownloadRecord.requiredGeometryRevisions`,
    /// keyed `globalId:localHole`) is not presented as the current precise map.
    static func isStale(hole: Hole, installedRevision: String?, required: [String: String]?) -> Bool {
        guard let raw = required?["\(hole.sourceGlobalId):\(hole.sourceLocalHole)"] else { return false }
        let wanted = normalized(raw)
        guard !wanted.isEmpty else { return false }
        guard let installedRevision else { return true }
        return normalized(installedRevision) != wanted
    }

    private static func normalized(_ revision: String) -> String {
        revision.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }
}

/// One caddie plan (方案) for the hole: its own route legs for the map (each landing labelled
/// "球杆 码数") and the same strokes as the bottom club order.
struct PrepPlanOption: Equatable, Identifiable {
    struct Step: Equatable, Identifiable {
        let id: Int
        let club: String
        let yards: Int?

        var label: String {
            guard let yards, yards > 0 else { return club }
            return "\(club) \(yards)"
        }
    }

    let id: String
    let title: String
    let steps: [Step]
    /// The map legs, in the shared `HoleImageMapView` / `LivePlannedRouteRenderer` contract.
    let shots: [MapPlannedShot]

    /// The hole's plans from the same decision authority as live play: the installed CoursePrep
    /// chain first, then the caddie seed's routes through `OfflineCaddieDecisionEvaluator`, merged
    /// and de-duplicated by `LiveCaddieRouteAuthority` exactly as the live hole does before any
    /// network response
    /// (for a tee shot, before any GPS). Each plan is a physically different complete route. A
    /// package without a caddie seed or bag still shows its installed CoursePrep chain.
    static func options(template: LiveRoundPackage, hole: Hole, prep: CoursePrepHole?) -> [PrepPlanOption] {
        guard let prep else { return [] }
        let routes = decisionRoutes(template: template, hole: hole, prep: prep)
        let options = routes.enumerated().compactMap { index, route in
            option(route: route, index: index, par: hole.par)
        }
        if !options.isEmpty { return uniquelyTitled(options) }
        // The installed chain alone only when no evaluator rejected it: after a local no-route
        // decision (water / OB) 备战 shows no plan rather than the rejected route.
        if offlineDecision(template: template, hole: hole, prep: prep)?.isLocalNoRoute == true { return [] }
        return installedOption(prep: prep, par: hole.par).map { [$0] } ?? []
    }

    static func decisionRoutes(
        template: LiveRoundPackage,
        hole: Hole,
        prep: CoursePrepHole
    ) -> [CaddiePlanSequence] {
        guard let decision = offlineDecision(template: template, hole: hole, prep: prep) else {
            return []
        }
        let input = LiveCaddieInput.firstFrameTee(greenDistances: prep.greenDistances, holeYards: hole.yards)
        // Exactly as live play: the installed CoursePrep chain leads.
        let installed = LiveCaddieRouteAuthority.installedRoute(
            prep: prep,
            par: hole.par,
            shotType: "tee",
            fallbackRouteEndM: input.distanceToPinM
        )
        return LiveCaddieRouteAuthority.resolve(
            installed: installed,
            online: nil,
            offline: decision,
            par: hole.par,
            shotType: "tee"
        )
    }

    /// The live hole's first-frame tee decision before any GPS fix or player choice.
    static func offlineDecision(template: LiveRoundPackage, hole: Hole, prep: CoursePrepHole) -> CaddieDecisionResponse? {
        guard let seed = LiveCaddieSeedFactory.resolve(package: template, hole: hole, prep: prep) else { return nil }
        let input = LiveCaddieInput.firstFrameTee(greenDistances: prep.greenDistances, holeYards: hole.yards)
        let base = CaddieDecisionRequestBuilder().makeDecisionRequest(seed: seed, input: input)
        let request = CaddieDecisionRequestBuilder.addingCanonicalPlan(to: base, prep: prep)
        return OfflineCaddieDecisionEvaluator().makeDecision(seed: seed, request: request, strategyMode: nil)
    }

    static func option(route: CaddiePlanSequence, index: Int, par: Int) -> PrepPlanOption? {
        var steps: [Step] = []
        var shots: [MapPlannedShot] = []
        var previousOffsetM = 0.0
        let lastIndex = route.steps.lastIndex { !$0.clubName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        for (stepIndex, step) in route.steps.enumerated() {
            let name = step.clubName.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !name.isEmpty, name != "-" else { continue }
            let offset = step.routeOffsetM ?? step.landingM
            steps.append(chip(
                id: stepIndex, name: name, carryM: step.targetCarryM,
                offsetM: stepIndex == lastIndex ? offset : nil, previousOffsetM: previousOffsetM
            ))
            if let offset { previousOffsetM = offset }
            shots.append(MapPlannedShot(
                id: "prep-\(route.id)-\(step.id)",
                clubName: name,
                carryM: step.targetCarryM,
                routeOffsetM: step.routeOffsetM ?? step.landingM,
                role: step.role,
                expectedRemainingM: step.expectedRemainingM,
                // A GIR landing short of the flag stays at its landing; a Par 3 tee shot is the
                // scoring leg. Otherwise the map's own route-end rule decides (as in live play).
                targetsPin: step.greenInRegulation == true ? false : (par == 3 ? true : nil),
                planIndex: step.planIndex ?? stepIndex
            ))
        }
        guard !steps.isEmpty else { return nil }
        return PrepPlanOption(id: route.id, title: title(for: route, index: index), steps: steps, shots: shots)
    }

    /// The installed CoursePrep chain alone, when there is no caddie decision for the hole.
    static func installedOption(prep: CoursePrepHole, par: Int) -> PrepPlanOption? {
        var steps: [Step] = []
        var shots: [MapPlannedShot] = []
        var previousOffsetM = 0.0
        let lastIndex = prep.steps.lastIndex { !(($0.clubName ?? $0.club ?? "").trimmingCharacters(in: .whitespacesAndNewlines)).isEmpty }
        for (index, step) in prep.steps.enumerated() {
            let name = (step.clubName ?? step.club ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            guard !name.isEmpty, name != "-" else { continue }
            let offset = step.routeOffsetM ?? step.landingM
            steps.append(chip(
                id: index, name: name, carryM: step.targetCarryM,
                offsetM: index == lastIndex ? offset : nil, previousOffsetM: previousOffsetM
            ))
            if let offset { previousOffsetM = offset }
            shots.append(MapPlannedShot(
                id: "prep-installed-\(index)-\(name)",
                clubName: name,
                carryM: step.targetCarryM,
                routeOffsetM: step.routeOffsetM ?? step.landingM,
                role: step.role,
                expectedRemainingM: step.expectedRemainingM,
                targetsPin: par == 3 ? true : nil,
                planIndex: step.planIndex ?? index
            ))
        }
        guard !steps.isEmpty else { return nil }
        return PrepPlanOption(id: "installed", title: "推荐", steps: steps, shots: shots)
    }

    /// The strategy the decision engine labelled the route with; an unlabelled route is numbered.
    static func title(for route: CaddiePlanSequence, index: Int) -> String {
        if route.id == LiveCaddieRouteAuthority.installedRouteId { return "推荐" }
        switch caddieStrategyMode(forRouteId: route.id) ?? "" {
        case "protect_score": return "稳妥"
        case "stock": return "推荐"
        case "attack": return "进攻"
        default: return "方案 \(index + 1)"
        }
    }

    /// The chip names the shot as the map label does (`PlannedShotLabel`): the last shot onto the
    /// green is the leg actually played along the route, not the club's full carry.
    private static func chip(id: Int, name: String, carryM: Double?, offsetM: Double?, previousOffsetM: Double) -> Step {
        let played = offsetM.map { $0 - previousOffsetM }
        let label = PlannedShotLabel.resolve(clubName: name, carryM: carryM, playedM: played)
        return Step(id: id, club: label.club, yards: label.yards)
    }

    /// The same club name the map labels draw (`LivePlannedRouteRenderer.labelText`).
    static func displayClub(_ raw: String) -> String {
        zhClubDisplayName(zhClubName(raw))
    }

    private static func yards(_ metres: Double?) -> Int? {
        guard let metres, metres.isFinite, metres > 0 else { return nil }
        return Int((metres * LivePlannedRouteRenderer.yardsPerMetre).rounded())
    }

    private static func uniquelyTitled(_ options: [PrepPlanOption]) -> [PrepPlanOption] {
        var seen: [String: Int] = [:]
        return options.enumerated().map { index, option in
            let count = seen[option.title, default: 0]
            seen[option.title] = count + 1
            guard count > 0 else { return option }
            return PrepPlanOption(
                id: option.id,
                title: "方案 \(index + 1)",
                steps: option.steps,
                shots: option.shots
            )
        }
    }
}

/// 地图降级契约 (README §8): the zoom and pan the player set on the prep map. The screen owns it, so
/// a map replacement of the same hole (the factual route giving way to the precise topo, a
/// refreshed facts row) never resets it; the pan is re-clamped against the new map when drawn.
struct HoleMapViewportState: Equatable {
    var zoomScale: CGFloat = 1
    var offset: CGSize = .zero

    /// The fitted view (no reset control).
    var isFitted: Bool {
        let unzoomed: Bool = zoomScale <= 1.01
        let centred: Bool = abs(offset.width) <= 0.5 && abs(offset.height) <= 0.5
        return unzoomed && centred
    }
}

/// 备战 one-screen state. The displayed hole, its plan and the map viewport live here, owned by the
/// screen rather than by the map view, so a background map replacement (factual route → precise
/// topo, a refreshed facts row, a finished download, a Tee's new facts) never resets them
/// (README 地图降级契约). Only an explicit hole change starts that hole fitted on its first plan.
struct PrepHoleMapSession: Equatable {
    private(set) var holeNumber: Int?
    var viewport = HoleMapViewportState()
    private(set) var selectedPlanIndex = 0

    /// Explicit navigation (a strip tap).
    mutating func select(hole: Int) {
        guard hole != holeNumber else { return }
        holeNumber = hole
        viewport = HoleMapViewportState()
        selectedPlanIndex = 0
    }

    mutating func selectPlan(_ index: Int, planCount: Int) {
        guard index >= 0, index < planCount else { return }
        selectedPlanIndex = index
    }

    /// New facts for the course. The hole, viewport and plan are kept; the hole moves only when it
    /// no longer exists (or nothing was shown yet), and a plan index is clamped only when the hole
    /// now has fewer plans (a hole with none keeps it for when they arrive).
    mutating func adopt(holeNumbers: [Int], planCount: Int) {
        guard let current = holeNumber, holeNumbers.contains(current) else {
            if let first = holeNumbers.first {
                holeNumber = nil
                select(hole: first)
            }
            return
        }
        if planCount > 0, selectedPlanIndex >= planCount {
            selectedPlanIndex = planCount - 1
        }
    }

    /// The plan shown for a hole with `plans`, clamped for display.
    func plan(in plans: [PrepPlanOption]) -> PrepPlanOption? {
        guard !plans.isEmpty else { return nil }
        return plans[min(max(selectedPlanIndex, 0), plans.count - 1)]
    }
}

/// 备战's full-screen map geometry.
///
/// The fitted (rest) frame shows the whole plan: the tee, every landing with room for its
/// "球杆 码数" label, and the green all sit inside the content rect between the chrome (the badge
/// row on top, the glass panel at the bottom). Among such frames it prefers one whose bitmap covers
/// the viewport; when the hole's shape makes that impossible (a diagonal hole on a square topo in
/// a portrait screen), the plan wins: the map is drawn once and fades into one calm fill of its own
/// dominant edge colour reaching the screen edges (`TopoEdgeExtension`), so there is no rectangle, seam,
/// black band or stretched edge texture.
enum PrepMapLayout {
    /// An overlay point the fitted map keeps inside the content rect with `clearance` points of
    /// room on each side (a landing's label, or a small margin for the tee and the route).
    struct Anchor: Equatable {
        let point: CGPoint
        let clearance: CGSize
    }

    /// Room around the factual route's points (the tee, the green) when they carry no label.
    static let routeMargin: CGFloat = 14

    static func restFrame(
        overlayWidth: Int,
        overlayHeight: Int,
        route: [[Double]],
        anchors: [Anchor] = [],
        viewport: CGSize,
        topInset: CGFloat,
        bottomInset: CGFloat,
        shrink: CGFloat = 1,
        prefersCover: Bool = true
    ) -> CGRect? {
        guard overlayWidth > 0, overlayHeight > 0,
              viewport.width.isFinite, viewport.height.isFinite,
              viewport.width > 0, viewport.height > 0 else { return nil }
        let mapWidth = CGFloat(overlayWidth)
        let mapHeight = CGFloat(overlayHeight)
        let coverScale = max(viewport.width / mapWidth, viewport.height / mapHeight)
        guard coverScale.isFinite, coverScale > 0 else { return nil }
        let top = min(max(topInset.isFinite ? topInset : 0, 0), viewport.height)
        let bottom = max(top, viewport.height - max(bottomInset.isFinite ? bottomInset : 0, 0))
        let routeAnchors: [Anchor] = route.compactMap { row -> Anchor? in
            guard row.count >= 2, row[0].isFinite, row[1].isFinite else { return nil }
            return Anchor(point: CGPoint(x: row[0], y: row[1]), clearance: CGSize(width: routeMargin, height: routeMargin))
        }
        let all = (routeAnchors + anchors).filter {
            $0.point.x.isFinite && $0.point.y.isFinite
                && $0.clearance.width.isFinite && $0.clearance.height.isFinite
        }
        guard !all.isEmpty else {
            return coverFrame(overlayWidth: overlayWidth, overlayHeight: overlayHeight, route: route, viewport: viewport,
                              topInset: topInset, bottomInset: bottomInset)
        }
        let xs = all.map { Axis(point: $0.point.x, clearance: max($0.clearance.width, 0)) }
        let ys = all.map { Axis(point: $0.point.y, clearance: max($0.clearance.height, 0)) }
        func feasible(_ scale: CGFloat) -> Bool {
            placement(xs, scale: scale, low: 0, high: viewport.width) != nil
                && placement(ys, scale: scale, low: top, high: bottom) != nil
        }
        // The largest scale (up to the cover scale) at which every anchor fits between the chrome.
        var fitScale: CGFloat
        if feasible(coverScale) {
            fitScale = coverScale
        } else {
            var low: CGFloat = 0
            var high: CGFloat = coverScale
            for _ in 0..<40 {
                let mid = (low + high) / 2
                if feasible(mid) { low = mid } else { high = mid }
            }
            fitScale = low
        }
        guard fitScale > 0 else {
            return coverFrame(overlayWidth: overlayWidth, overlayHeight: overlayHeight, route: route, viewport: viewport,
                              topInset: topInset, bottomInset: bottomInset)
        }
        let scale = fitScale * min(max(shrink.isFinite ? shrink : 1, 0.05), 1)
        func origin(_ axis: [Axis], length: CGFloat, low: CGFloat, high: CGFloat, viewportLength: CGFloat) -> CGFloat {
            guard let fit = placement(axis, scale: scale, low: low, high: high) else { return 0 }
            let points = axis.map(\.point)
            let middle = ((points.min() ?? 0) + (points.max() ?? 0)) / 2
            let centred = (low + high) / 2 - middle * scale
            // A map whose surroundings continue seamlessly (the lightweight map's flat ground)
            // simply centres the plan.
            guard prefersCover else { return min(max(centred, fit.lower), fit.upper) }
            // Prefer a position that also keeps this edge of the viewport covered.
            let coverLow = viewportLength - length * scale
            let lower = max(fit.lower, coverLow)
            let upper = min(fit.upper, 0)
            if lower <= upper { return min(max(centred, lower), upper) }
            return min(max(centred, fit.lower), fit.upper)
        }
        let x = origin(xs, length: mapWidth, low: 0, high: viewport.width, viewportLength: viewport.width)
        let y = origin(ys, length: mapHeight, low: top, high: bottom, viewportLength: viewport.height)
        return CGRect(x: x, y: y, width: mapWidth * scale, height: mapHeight * scale)
    }

    private struct Axis {
        let point: CGFloat
        let clearance: CGFloat
    }

    /// The origins along one axis that keep every anchor (with its clearance) inside [low, high].
    private static func placement(
        _ axis: [Axis],
        scale: CGFloat,
        low: CGFloat,
        high: CGFloat
    ) -> (lower: CGFloat, upper: CGFloat)? {
        var lower = -CGFloat.greatestFiniteMagnitude
        var upper = CGFloat.greatestFiniteMagnitude
        for item in axis {
            lower = max(lower, low + item.clearance - item.point * scale)
            upper = min(upper, high - item.clearance - item.point * scale)
        }
        return lower <= upper ? (lower, upper) : nil
    }

    /// The bitmap's aspect fill of the whole viewport, the route's centre as near the middle of the
    /// content rect as keeping every edge covered allows: the fitted frame of a hole with nothing
    /// to fit.
    static func coverFrame(
        overlayWidth: Int,
        overlayHeight: Int,
        route: [[Double]],
        viewport: CGSize,
        topInset: CGFloat,
        bottomInset: CGFloat
    ) -> CGRect? {
        guard overlayWidth > 0, overlayHeight > 0,
              viewport.width.isFinite, viewport.height.isFinite,
              viewport.width > 0, viewport.height > 0 else { return nil }
        let scale = max(viewport.width / CGFloat(overlayWidth), viewport.height / CGFloat(overlayHeight))
        guard scale.isFinite, scale > 0 else { return nil }
        let width = CGFloat(overlayWidth) * scale
        let height = CGFloat(overlayHeight) * scale
        let points: [CGPoint] = route.compactMap { row -> CGPoint? in
            guard row.count >= 2, row[0].isFinite, row[1].isFinite else { return nil }
            return CGPoint(x: row[0], y: row[1])
        }
        let xs = points.map(\.x)
        let ys = points.map(\.y)
        let focus: CGPoint
        if let minX = xs.min(), let maxX = xs.max(), let minY = ys.min(), let maxY = ys.max() {
            focus = CGPoint(x: (minX + maxX) / 2, y: (minY + maxY) / 2)
        } else {
            focus = CGPoint(x: CGFloat(overlayWidth) / 2, y: CGFloat(overlayHeight) / 2)
        }
        let top = min(max(topInset.isFinite ? topInset : 0, 0), viewport.height)
        let bottom = max(top, viewport.height - max(bottomInset.isFinite ? bottomInset : 0, 0))
        let targetX: CGFloat = viewport.width / 2
        let targetY: CGFloat = (top + bottom) / 2
        // Keep every edge of the viewport covered by the bitmap.
        let x = min(max(targetX - focus.x * scale, viewport.width - width), 0)
        let y = min(max(targetY - focus.y * scale, viewport.height - height), 0)
        return CGRect(x: x, y: y, width: width, height: height)
    }

    /// True when `frame` leaves no part of the viewport uncovered.
    static func covers(_ frame: CGRect, viewport: CGSize) -> Bool {
        frame.minX <= 0.5 && frame.minY <= 0.5
            && frame.maxX >= viewport.width - 0.5 && frame.maxY >= viewport.height - 0.5
    }
}
