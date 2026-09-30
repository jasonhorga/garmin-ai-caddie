import Foundation
@testable import AICaddie

/// Shared 备战 plan fixtures for the design snapshots and the prep layout tests.
enum PrepRouteFixtures {
    /// 备战 fixture plans with the real strategy identities (the installed chain → 推荐, safe → 稳妥,
    /// attack → 进攻) and genuinely different carries and landing stations. Stations are cumulative
    /// fractions of the route; the last leg of each plan is its green-bound scoring leg.
    static func routes(par: Int, routeLengthM: Double) -> [CaddiePlanSequence] {
        let plans: [(id: String, clubs: [String], stations: [Double])]
        switch par {
        case 3:
            plans = [
                (LiveCaddieRouteAuthority.installedRouteId, ["8I"], [1]),
                ("safe", ["7I"], [0.9]),
                ("attack", ["9I"], [1]),
            ]
        case 4:
            plans = [
                (LiveCaddieRouteAuthority.installedRouteId, ["1W", "8I"], [0.55, 1]),
                ("safe", ["3H", "7I"], [0.4, 1]),
                ("attack", ["1W", "PW"], [0.68, 1]),
            ]
        default:
            plans = [
                (LiveCaddieRouteAuthority.installedRouteId, ["1W", "3W", "SW"], [0.41, 0.79, 1]),
                ("safe", ["3W", "5I", "9I"], [0.3, 0.62, 1]),
                ("attack", ["1W", "3W"], [0.52, 1]),
            ]
        }
        return plans.map { plan -> CaddiePlanSequence in
            var previous = 0.0
            let steps = plan.stations.enumerated().map { index, station -> CaddiePlanSequenceStep in
                let offset = (routeLengthM * station).rounded()
                let carry = offset - previous
                previous = offset
                let isLast = index == plan.stations.count - 1
                return CaddiePlanSequenceStep(
                    id: "\(plan.id)-\(index)",
                    role: isLast ? "scoring" : (index == 0 ? "tee" : "position"),
                    clubName: plan.clubs[min(index, plan.clubs.count - 1)],
                    targetCarryM: carry,
                    expectedRemainingM: isLast ? 0 : routeLengthM - offset,
                    sampleSize: 12,
                    confidence: "medium",
                    sourceRefs: [],
                    routeOffsetM: offset,
                    planIndex: index
                )
            }
            return CaddiePlanSequence(
                id: plan.id,
                label: plan.clubs.joined(separator: "-"),
                expectedRemainingM: 0,
                riskScore: nil,
                confidence: "medium",
                coverageText: nil,
                sourceRefs: [],
                steps: steps
            )
        }
    }

}
