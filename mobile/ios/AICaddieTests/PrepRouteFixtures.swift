import CoreGraphics
import Foundation
@testable import AICaddie

/// Shared 备战 plan fixtures for the design snapshots and the prep layout tests.
enum PrepRouteFixtures {
    /// The one player bag every 备战 fixture plan is played with: each club's stock carry in metres
    /// (Codex 5922420253). Adjacent carries are at most 14 m apart, so a remaining distance in the
    /// bag's range always has a club within `carryToleranceM`.
    static let bag: [(club: String, carryM: Double)] = [
        ("1W", 220), ("3W", 210), ("5W", 196), ("3H", 184), ("4H", 172), ("5I", 161), ("6I", 150),
        ("7I", 139), ("8I", 127), ("9I", 115), ("PW", 102), ("GW", 88), ("SW", 74), ("LW", 60),
    ]
    /// How far a stroke's carry may differ from its club's stock carry: only the green-bound
    /// stroke uses it, to finish the route exactly.
    static let carryToleranceM = 8.0
    /// Two plans with the same stroke count are the same route unless some landing differs by this.
    static let distinctLandingM = 15.0

    static func stockCarry(_ club: String) -> Double? {
        bag.first { $0.club.caseInsensitiveCompare(club) == .orderedSame }?.carryM
    }

    /// 备战 fixture plans with the real strategy identities (the installed chain → 推荐, safe → 稳妥,
    /// attack → 进攻), played with `bag`: every stroke before the last carries its club's stock
    /// distance; the last, green-bound stroke reaches the route's end with the club whose stock
    /// carry is nearest the remaining distance (never the tee-only driver). A strategy whose
    /// remaining distance no club covers within tolerance is not offered, and a plan that lands
    /// where an earlier one does is the same physical route and is dropped.
    static func routes(par: Int, routeLengthM: Double) -> [CaddiePlanSequence] {
        let strategies: [(id: String, clubs: [String])]
        switch par {
        case 3:
            // One stroke to the green: every club choice is the same physical route.
            strategies = [(LiveCaddieRouteAuthority.installedRouteId, [])]
        case 4:
            strategies = [
                (LiveCaddieRouteAuthority.installedRouteId, ["1W"]),
                // An iron off the tee and a lay-up: a short wedge in, short of the trouble.
                ("safe", ["5I", "7I"]),
            ]
        default:
            strategies = [
                (LiveCaddieRouteAuthority.installedRouteId, ["1W", "5I"]),
                ("safe", ["7I", "5I"]),
                ("attack", ["1W", "5W"]),
            ]
        }
        let end = routeLengthM.rounded()
        var kept: [CaddiePlanSequence] = []
        for strategy in strategies {
            var legs: [(club: String, carryM: Double)] = strategy.clubs.compactMap { club in
                stockCarry(club).map { (club, $0) }
            }
            let laidUp = legs.reduce(0) { $0 + $1.carryM }
            let remaining = end - laidUp
            guard let scoring = bag.filter({ $0.club != "1W" })
                .min(by: { abs($0.carryM - remaining) < abs($1.carryM - remaining) }),
                  abs(scoring.carryM - remaining) <= carryToleranceM else { continue }
            legs.append((scoring.club, remaining))
            let route = sequence(id: strategy.id, legs: legs, routeLengthM: routeLengthM)
            let landings = route.steps.compactMap(\.routeOffsetM)
            let duplicate = kept.contains { other in
                let otherLandings = other.steps.compactMap(\.routeOffsetM)
                return otherLandings.count == landings.count
                    && zip(otherLandings, landings).allSatisfy { abs($0 - $1) < distinctLandingM }
            }
            if !duplicate { kept.append(route) }
        }
        return kept
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
    /// distances, the obstacle spans and the installed chain (the same `routes(par:routeLengthM:)`
    /// the plans use) all describe one hole. The route metres are the ones whose production yard
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
        let route = routes(par: par, routeLengthM: length)
        let installed = route.first { $0.id == LiveCaddieRouteAuthority.installedRouteId } ?? route.first
        let steps: [[String: Any]] = (installed?.steps ?? []).map { step in
            var row: [String: Any] = [
                "club": step.clubName,
                "clubName": step.clubName,
                "role": step.role,
                "expectedRemaining_m": step.expectedRemainingM ?? 0,
            ]
            if let carry = step.targetCarryM { row["targetCarry_m"] = carry }
            if let offset = step.routeOffsetM { row["routeOffset_m"] = offset; row["landing_m"] = offset }
            return row
        }
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
            "steps": steps, "cautions": cautions,
            "hazards": ["water_carry": water, "bunkers": bunkers, "details": details] as [String: Any],
            "map": map,
            "greenDistances": [
                "available": true, "frontM": length - 7, "middleM": length, "backM": length + 7,
            ] as [String: Any],
        ]
        if let first = steps.first {
            body["tee_club"] = first["clubName"]
            body["landing_m"] = first["routeOffset_m"]
        }
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
    /// the prep's playing yardage and every plan is built on the prep's own route length.
    static func row(number: Int, prep: CoursePrepHole, topoURL: URL?, state: LiveMapDisplayState) -> PrepHoleRow {
        PrepHoleRow(
            number: number,
            displayNumber: number,
            par: prep.par,
            yards: prep.playingYards,
            prep: prep,
            topoURL: topoURL,
            state: state,
            plans: routes(par: prep.par, routeLengthM: prep.routeLenM)
                .enumerated()
                .compactMap { index, route in PrepPlanOption.option(route: route, index: index, par: prep.par) }
        )
    }
}
