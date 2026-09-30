import Foundation

/// One hole of the full-screen 备战 (README §8, `pre-round.html` 第三台). It is resolved once per
/// install change from the local course template, never per render: which facts exist, which local
/// topo is installed, and therefore which state of the map degradation contract the hole shows.
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
            return PrepHoleRow(
                number: hole.number,
                displayNumber: hole.courseHoleNumber,
                par: prep?.par ?? hole.par,
                yards: prep?.playingYards ?? hole.yards,
                prep: prep,
                topoURL: topo,
                state: LiveMapDisplayState.resolvePrep(
                    prep: prep,
                    hasLocalTopo: topo != nil,
                    isStale: stale,
                    downloadActive: downloadActive
                )
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

/// One caddie plan for the hole and its club order ("一号木 224 → 三号木 205 → 挖起杆 110").
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

    let id: Int
    let title: String
    let steps: [Step]

    /// The installed prep row carries one canonical caddie plan (its structured steps). Each step's
    /// club is its own carry, the same facts the map projects as landings.
    static func options(for prep: CoursePrepHole?) -> [PrepPlanOption] {
        guard let prep else { return [] }
        let steps = prep.steps.enumerated().compactMap { index, step -> Step? in
            guard let raw = step.clubName ?? step.club,
                  !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
            let yards = step.targetCarryM.flatMap { carry -> Int? in
                guard carry.isFinite, carry > 0 else { return nil }
                return CoursePrepRoute.yards(fromMetres: carry)
            }
            return Step(id: index, club: zhClubDisplayName(raw), yards: yards)
        }
        guard !steps.isEmpty else { return [] }
        return [PrepPlanOption(id: 0, title: "球童建议", steps: steps)]
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
}
