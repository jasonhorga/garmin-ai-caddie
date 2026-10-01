import CoreGraphics
import Foundation
@testable import AICaddie

/// Shared 备战 plan fixtures for the design snapshots and the prep layout tests.
enum PrepRouteFixtures {
    /// 备战 fixture plans with the real strategy identities (the installed chain → 推荐, safe → 稳妥,
    /// attack → 进攻) and genuinely different carries and landing stations. Stations are cumulative
    /// fractions of the route; the last leg of each plan is its green-bound scoring leg and ends at
    /// the route's end (1.0), so every plan is a physically complete hole. On a Par 3 the plans are
    /// the same one-stroke route with a different club (推荐 8I, 稳妥 a smoother 7I, 进攻 9I).
    static func routes(par: Int, routeLengthM: Double) -> [CaddiePlanSequence] {
        let plans: [(id: String, clubs: [String], stations: [Double])]
        switch par {
        case 3:
            plans = [
                (LiveCaddieRouteAuthority.installedRouteId, ["8I"], [1]),
                ("safe", ["7I"], [1]),
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
                ("safe", ["3W", "5I", "9I"], [0.28, 0.6, 1]),
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
        let installed = route.first { $0.id == LiveCaddieRouteAuthority.installedRouteId } ?? route[0]
        let steps: [[String: Any]] = installed.steps.map { step in
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
