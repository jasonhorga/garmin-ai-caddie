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
            let topo = prep == nil || stale ? nil : topoURL(hole, revision)
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

    /// The hole's plans from the same decision authority as live play: the installed caddie seed
    /// and CoursePrep chain through `OfflineCaddieDecisionEvaluator`, merged and de-duplicated by
    /// `LiveCaddieRouteAuthority` exactly as the live hole does before any network response
    /// (for a tee shot, before any GPS). Each plan is a physically different complete route. A
    /// package without a caddie seed or bag still shows its installed CoursePrep chain.
    static func options(template: LiveRoundPackage, hole: Hole, prep: CoursePrepHole?) -> [PrepPlanOption] {
        guard let prep else { return [] }
        let routes = decisionRoutes(template: template, hole: hole, prep: prep)
        let options = routes.enumerated().compactMap { index, route in
            option(route: route, index: index, par: hole.par)
        }
        if !options.isEmpty { return uniquelyTitled(options) }
        return installedOption(prep: prep, par: hole.par).map { [$0] } ?? []
    }

    static func decisionRoutes(
        template: LiveRoundPackage,
        hole: Hole,
        prep: CoursePrepHole
    ) -> [CaddiePlanSequence] {
        guard let seed = LiveCaddieSeedFactory.resolve(package: template, hole: hole, prep: prep) else {
            return []
        }
        let base = CaddieDecisionRequestBuilder().makeDecisionRequest(
            seed: seed,
            input: LiveCaddieInput(shotType: "tee")
        )
        let request = CaddieDecisionRequestBuilder.addingCanonicalPlan(to: base, prep: prep)
        let decision = OfflineCaddieDecisionEvaluator().makeDecision(
            seed: seed,
            request: request,
            strategyMode: nil
        )
        return LiveCaddieRouteAuthority.resolve(
            installed: nil,
            online: nil,
            offline: decision,
            par: hole.par,
            shotType: "tee"
        )
    }

    static func option(route: CaddiePlanSequence, index: Int, par: Int) -> PrepPlanOption? {
        var steps: [Step] = []
        var shots: [MapPlannedShot] = []
        for (stepIndex, step) in route.steps.enumerated() {
            let name = step.clubName.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !name.isEmpty, name != "-" else { continue }
            steps.append(Step(id: stepIndex, club: displayClub(name), yards: yards(step.targetCarryM)))
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
        for (index, step) in prep.steps.enumerated() {
            let name = (step.clubName ?? step.club ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            guard !name.isEmpty, name != "-" else { continue }
            steps.append(Step(id: index, club: displayClub(name), yards: yards(step.targetCarryM)))
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
        switch caddieStrategyMode(forRouteId: route.id) ?? "" {
        case "protect_score": return "稳妥"
        case "stock": return "推荐"
        case "attack": return "进攻"
        default: return "方案 \(index + 1)"
        }
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
