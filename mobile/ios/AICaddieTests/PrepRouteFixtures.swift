import CoreGraphics
import Foundation
import XCTest
@testable import AICaddie

/// Shared 备战 plan fixtures for the design snapshots and the prep layout tests.
enum PrepRouteFixtures {
    /// The one player every 备战 fixture plan is played by: each club's stock carry (median) and
    /// half its p10-p90 spread, in metres — a long, wilder driver and steadier fairway clubs.
    static let bag: [(club: String, carryM: Double, halfSpreadM: Double)] = [
        ("1W", 220, 30), ("3W", 210, 18), ("5W", 196, 14), ("3H", 184, 12), ("4H", 172, 11),
        ("5I", 161, 10), ("6I", 150, 9), ("7I", 139, 8), ("8I", 127, 7), ("9I", 115, 7),
        ("PW", 102, 6), ("GW", 88, 5), ("SW", 74, 5), ("LW", 60, 5),
    ]
    /// The tee clubs a Par 4/5 offers the decision authority: the driver (its stock pick) and the
    /// steadier 3W as the 稳妥 candidate; the authority keeps the latter only when it lowers the
    /// whole chain's modelled risk without adding strokes.
    static let alternativeTeeClubs: [(id: String, club: String)] = [("safe", "3W")]
    /// How far a stroke's carry may differ from its club's stock carry in any plan.
    static let carryToleranceM = 8.0
    /// Two plans with the same stroke count are the same route unless some landing differs by this.
    static let distinctLandingM = 15.0
    /// A plan closes on its hole when its carries sum to the route within the scoring window's
    /// overshoot bound: the green-bound stroke is the club whose stock carry is nearest the
    /// remaining distance, never a carry stretched to fit.
    static let closureToleranceM = 10.0

    static func stockCarry(_ club: String) -> Double? {
        bag.first { $0.club.caseInsensitiveCompare(club) == .orderedSame }?.carryM
    }

    /// The course template the bag belongs to: the fixture package with `bag` as its club
    /// profiles and no per-hole server seeds, so every hole's seed is synthesized from the bag and
    /// the hole's prep exactly as on a phone without a cached seed.
    static func package() throws -> LiveRoundPackage {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        var root = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        root["clubProfiles"] = bag.map { row -> [String: Any] in
            [
                "clubName": row.club, "sampleSize": 24, "median_m": row.carryM,
                "p10_m": row.carryM - row.halfSpreadM, "p90_m": row.carryM + row.halfSpreadM,
            ]
        }
        root["caddieContextSeeds"] = [] as [Any]
        return try JSONDecoder().decode(LiveRoundPackage.self, from: JSONSerialization.data(withJSONObject: root))
    }

    /// A prep's 方案, from the production decision authority (`PrepPlanOption.options`) fed `bag`.
    static func plans(for prep: CoursePrepHole) throws -> [PrepPlanOption] {
        let template = try package()
        let hole = Hole(
            number: prep.hole, par: prep.par, yards: prep.playingYards, geometryCoverage: .ready,
            sourceGlobalId: template.course.globalId, sourceLocalHole: prep.hole, courseHoleNumber: prep.hole
        )
        return PrepPlanOption.options(template: template, hole: hole, prep: prep)
    }

    /// One plan from explicit strokes (club, carry in metres), landing at the cumulative carries.
    static func sequence(id: String, legs: [(club: String, carryM: Double)], routeLengthM: Double) -> CaddiePlanSequence {
        var offset = 0.0
        let steps = legs.enumerated().map { index, leg -> CaddiePlanSequenceStep in
            offset += leg.carryM
            let isLast = index == legs.count - 1
            return CaddiePlanSequenceStep(
                id: "\(id)-\(index)",
                role: isLast ? "scoring" : (index == 0 ? "tee" : "position"),
                clubName: leg.club,
                targetCarryM: leg.carryM,
                expectedRemainingM: isLast ? 0 : routeLengthM - offset,
                sampleSize: 12,
                confidence: "medium",
                sourceRefs: [],
                routeOffsetM: offset,
                planIndex: index
            )
        }
        return CaddiePlanSequence(
            id: id,
            label: legs.map(\.club).joined(separator: "-"),
            expectedRemainingM: 0,
            riskScore: nil,
            confidence: "medium",
            coverageText: nil,
            sourceRefs: [],
            steps: steps
        )
    }

    /// One physically coherent 备战 hole (Codex 5921831209): the displayed Blue yardage, `route_len_m`,
    /// the overlay's `ln` and stations, its pixel geometry through one isotropic `ppm`, the green's
    /// distances and the obstacle spans (which the decision authority plans around) all describe
    /// one hole. The route metres are the ones whose production yard
    /// rounding is `yards`; every station is its pixel distance along the route over `ppm`.
    struct Hazard {
        let kind: String
        /// Front / back as fractions of the route; `side` metres left of it (nil on the route).
        let front: Double
        let back: Double
        let side: Double?
    }

    static func routeMetres(yards: Int) -> Double { Double(yards) / 1.09361 }

    static func hole(
        number: Int,
        par: Int,
        yards: Int,
        pixels: [CGPoint],
        width: Int,
        height: Int,
        imageDataURI: String?,
        coverage: String,
        revision: String,
        greenOutlineRadius: CGSize? = nil,
        hazards: [Hazard] = [],
        cautions: [String] = [],
        playsLike: [String: Any]? = nil
    ) throws -> CoursePrepHole {
        precondition(pixels.count >= 2)
        let length = routeMetres(yards: yards)
        var cumulative: [Double] = [0]
        for index in 1..<pixels.count {
            let a = pixels[index - 1], b = pixels[index]
            cumulative.append(cumulative[index - 1] + Double(hypot(b.x - a.x, b.y - a.y)))
        }
        let ppm = cumulative.last! / length
        let stations = cumulative.map { $0 / ppm }
        let tee = pixels[0]
        // The pixel at `station` metres along the route, `side` metres to its left.
        func pixel(station: Double, side: Double) -> CGPoint {
            let target = min(max(station, 0), length) * ppm
            var index = 1
            while index < pixels.count - 1 && cumulative[index] < target { index += 1 }
            let a = pixels[index - 1], b = pixels[index]
            let segment = cumulative[index] - cumulative[index - 1]
            let t = segment > 0 ? (target - cumulative[index - 1]) / segment : 0
            let dx = Double(b.x - a.x) / max(segment, 1e-9), dy = Double(b.y - a.y) / max(segment, 1e-9)
            // In the image y grows downward, so "left" of travel is (dy, -dx).
            return CGPoint(
                x: Double(a.x) + t * Double(b.x - a.x) + side * ppm * dy,
                y: Double(a.y) + t * Double(b.y - a.y) - side * ppm * dx
            )
        }
        func straightMetres(_ point: CGPoint) -> Double {
            (Double(hypot(point.x - tee.x, point.y - tee.y)) / ppm * 10).rounded() / 10
        }
        // No installed chain: every plan, the default included, comes from the decision authority.
        let candidateRoutes: [[String: Any]] = par >= 4
            ? alternativeTeeClubs.compactMap { option in
                stockCarry(option.club).map { ["id": option.id, "club": option.club, "carryM": $0, "riskScore": 1.0] as [String: Any] }
            }
            : []
        var details: [[String: Any]] = []
        var water: [[Double]] = []
        var bunkers: [[Double]] = []
        for hazard in hazards {
            let frontRoute = (hazard.front * length).rounded()
            let backRoute = (hazard.back * length).rounded()
            let frontPx = pixel(station: frontRoute, side: hazard.side ?? 0)
            let backPx = pixel(station: backRoute, side: hazard.side ?? 0)
            var detail: [String: Any] = [
                "kind": hazard.kind,
                "frontM": straightMetres(frontPx), "backM": straightMetres(backPx),
                "frontRouteM": frontRoute, "backRouteM": backRoute,
                "frontPx": [Double(frontPx.x), Double(frontPx.y)],
                "backPx": [Double(backPx.x), Double(backPx.y)],
            ]
            if let side = hazard.side { detail["sideM"] = side } else { detail["sideM"] = NSNull() }
            details.append(detail)
            if hazard.kind == "water" { water.append([frontRoute, backRoute]) } else { bunkers.append([frontRoute, hazard.side ?? 0]) }
        }
        let overlay: [String: Any] = [
            "w": width, "h": height, "ppm": ppm, "ln": length,
            "route": zip(pixels, stations).map { [Double($0.x), Double($0.y), $1] },
        ]
        var map: [String: Any] = ["overlay": overlay]
        if let imageDataURI { map["image"] = imageDataURI }
        var body: [String: Any] = [
            "hole": number, "par": par, "par_source": "courseview",
            "blue_yards": yards, "route_len_m": length,
            // Production's top-level route: hole-local metres (x east, y north) from the tee.
            "route": zip(pixels, stations).map {
                [Double($0.x - tee.x) / ppm, -Double($0.y - tee.y) / ppm, $1]
            },
            "geometryCoverage": coverage, "geometryRevision": revision,
            "steps": [] as [Any], "candidateRoutes": candidateRoutes, "cautions": cautions,
            "hazards": ["water_carry": water, "bunkers": bunkers, "details": details] as [String: Any],
            "map": map,
            "greenDistances": [
                "available": true, "frontM": length - 7, "middleM": length, "backM": length + 7,
            ] as [String: Any],
        ]
        if let playsLike { body["playsLike"] = playsLike }
        if let radius = greenOutlineRadius, let end = pixels.last {
            body["greenOutline"] = [
                "available": true, "source": "fixture",
                "pointsPx": (0..<24).map { index -> [Double] in
                    let angle = Double(index) / 24 * 2 * Double.pi
                    return [Double(end.x) + Double(radius.width) * cos(angle), Double(end.y) + Double(radius.height) * sin(angle)]
                },
            ] as [String: Any]
        }
        let data = try JSONSerialization.data(withJSONObject: body)
        return try JSONDecoder().decode(CoursePrepHole.self, from: data)
    }

    /// The 备战 row a hole's prep produces, as `PrepHoleRows.build` does: the displayed yardage is
    /// the prep's playing yardage and the plans are the decision authority's for that prep.
    static func row(number: Int, prep: CoursePrepHole, topoURL: URL?, state: LiveMapDisplayState) throws -> PrepHoleRow {
        PrepHoleRow(
            number: number,
            displayNumber: number,
            par: prep.par,
            yards: prep.playingYards,
            prep: prep,
            topoURL: topoURL,
            state: state,
            plans: try plans(for: prep)
        )
    }
}
