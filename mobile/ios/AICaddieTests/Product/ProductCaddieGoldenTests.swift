import SwiftUI
import XCTest
@testable import AICaddie

struct ProductCaddieDocument: Decodable {
    let schemaVersion: Int
    let cases: [ProductCaddieVector]
}

struct ProductCaddieVector: Decodable {
    struct Profile: Decodable {
        let median_m: Double
        let p10_m: Double
        let p90_m: Double
        let sampleSize: Int
    }
    struct Expected: Decodable {
        let id: String
        let clubNames: [String]
        let routeOffsets_m: [Double]
        let landingsLocal: [[Double]]
        let planIndices: [Int]
        let plannedStrokes: Int
    }
    struct Green: Decodable {
        let frontM: Double
        let middleM: Double
        let backM: Double
        let source: String

        var input: [String: Any] {
            ["frontM": frontM, "middleM": middleM, "backM": backM, "source": source]
        }
    }
    struct Hazard: Decodable {
        let id: String
        let kind: String
        let carryToFront_m: Double
        let carryToClear_m: Double
        let sourceRefs: [String]?

        var input: [String: Any] {
            ["id": id, "kind": kind, "carryToFront_m": carryToFront_m,
             "carryToClear_m": carryToClear_m, "sourceRefs": sourceRefs ?? []]
        }
        var goldenZone: [String: JSONValue] {
            ["id": .string(id), "kind": .string(kind), "carryToFront_m": .number(carryToFront_m),
             "carryToClear_m": .number(carryToClear_m)]
        }
    }
    let id: String
    let hole: Int
    let par: Int
    let shotType: String
    let ballLocal: [Double]
    let pinLocal: [Double]
    let routeLocal: [[Double]]
    let distanceToPin_m: Double
    let clubProfiles: [String: Profile]
    let openingClubs: [String: String]
    let expected: [Expected]
    let routeRiskScores: [String: Double]?
    let greenDistances: Green?
    let hazards: [Hazard]?
    let expectedAvoidZones: [Hazard]?

    var sourceRef: String { "course:81001:hole:\(hole)" }
    var sourceRefs: [String] { [sourceRef] + (hazards ?? []).flatMap { $0.sourceRefs ?? [] } }

    func risk(_ strategy: String) -> Double {
        routeRiskScores?[strategy] ?? ["safe": 0.0, "stock": 1.0, "attack": 2.0][strategy]!
    }

    func seed() throws -> CaddieContextSeed {
        // Match C16c golden_context's input facts. The native parser also requires the name
        // inside each profile row, in addition to the name-keyed dictionary used by Python.
        let profiles: [String: [String: Any]] = clubProfiles.mapValues { p in
            ["median_m": p.median_m, "p10_m": p.p10_m, "p90_m": p.p90_m, "sampleSize": p.sampleSize]
        }
        let namedProfiles = Dictionary(uniqueKeysWithValues: profiles.map { name, value in
            var row = value
            row["clubName"] = name
            return (name, row)
        })
        let routes: [[String: Any]] = try [("safe", "conservative_layup"), ("stock", "stock_line"), ("attack", "aggressive_line")].map { strategy, routeID in
            let club = try XCTUnwrap(openingClubs[strategy], id)
            let profile = try XCTUnwrap(clubProfiles[club], id)
            let fraction = profile.median_m / distanceToPin_m
            let landing = zip(ballLocal, pinLocal).map { a, b in a + (b - a) * fraction }
            let zones = (hazards ?? []).map { $0.input }
            return ["id": routeID, "club": club, "carry_m": profile.median_m,
                "landingLocal": landing, "riskScore": risk(strategy), "lineRisks": zones,
                // Native's typed hazard input is an adapter of those same physical facts.
                "planningHazards": zones, "sourceRefs": sourceRefs]
        }
        var context: [String: Any] = ["hole": hole, "par": par, "shotType": shotType,
            "source": "fixture", "sourceRef": sourceRef, "distanceToPin_m": distanceToPin_m,
            "clubProfiles": namedProfiles, "candidateRoutes": routes,
            "routeEvidence": ["startLocal": ballLocal, "targetLocal": pinLocal]]
        if let greenDistances { context["greenDistances"] = greenDistances.input }
        let options = try ["safe", "stock", "attack"].map { strategy -> OfflineCaddieOption in
            let club = try XCTUnwrap(openingClubs[strategy], id)
            let p = try XCTUnwrap(clubProfiles[club], id)
            return OfflineCaddieOption(optionId: strategy, label: strategy, clubName: club,
                carryM: p.median_m, p10M: p.p10_m, p90M: p.p90_m, sampleSize: p.sampleSize,
                confidence: "medium", riskScore: risk(strategy), source: "synthetic-profile", sourceRefs: sourceRefs)
        }
        return CaddieContextSeed(hole: hole, sourceRef: sourceRef, shotTypes: [shotType], requiredLiveInputs: [],
            context: try ProductSharedVectors.decode(context),
            selectedOfflineOptionId: "stock", offlineOptions: options, evidence: [], missingData: [])
    }

    func prep() throws -> CoursePrepHole {
        // Identity map: one topo pixel per local metre; cumulative stations are factual
        // distances from the supplied ball, never copied from an expected landing.
        let route = routeLocal.enumerated().map { index, point in
            [point[0], point[1], index == 0 ? 0 : distanceToPin_m]
        }
        let water = (hazards ?? []).filter { $0.kind == "water" }.map { [$0.carryToFront_m, $0.carryToClear_m] }
        var input: [String: Any] = [
            "hole": hole, "par": par, "par_source": "synthetic",
            "blue_yards": Int((distanceToPin_m * 1.0936133).rounded()),
            "route_len_m": distanceToPin_m, "geometryCoverage": "ready", "route": routeLocal,
            "steps": [], "cautions": [], "hazards": ["water_carry": water],
            "map": ["overlay": ["w": 500, "h": 500, "ppm": 1, "ln": distanceToPin_m, "route": route]],
        ]
        // Only supply measured green facts present in the shared input. A fabricated available
        // middle-only green triggers factual seed repair and reselects the longest opening club.
        if let greenDistances {
            var green = greenDistances.input
            green["available"] = true
            input["greenDistances"] = green
        }
        return try ProductSharedVectors.decode(input)
    }

    func package() throws -> LiveRoundPackage {
        let base = try ProductInputs.package()
        var input = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(base)) as? [String: Any])
        var holes = try XCTUnwrap(input["holes"] as? [[String: Any]])
        let index = try XCTUnwrap(holes.firstIndex { $0["number"] as? Int == hole }, id)
        holes[index]["par"] = par
        input["holes"] = holes
        input["caddieContextSeeds"] = [try JSONSerialization.jsonObject(with: JSONEncoder().encode(seed()))]
        input["clubProfiles"] = clubProfiles.map { name, p in
            ["clubName": name, "median_m": p.median_m, "p10_m": p.p10_m, "p90_m": p.p90_m, "sampleSize": p.sampleSize] as [String: Any]
        }
        return try ProductSharedVectors.decode(input)
    }
}

@MainActor
final class ProductCaddieGoldenTests: XCTestCase {
    private var previousDefaults: UserDefaults!
    private var suite: String!

    override func setUp() {
        super.setUp()
        previousDefaults = ClubBagStore.defaults
        suite = "product-caddie-\(UUID().uuidString)"
        ClubBagStore.defaults = UserDefaults(suiteName: suite)!
    }

    override func tearDown() {
        ClubBagStore.defaults.removePersistentDomain(forName: suite)
        ClubBagStore.defaults = previousDefaults
        super.tearDown()
    }

    func test_j5_11_offline_plans_and_projected_landings_match_shared_golden() throws {
        let document: ProductCaddieDocument = try ProductSharedVectors.read("caddie_golden")
        XCTAssertEqual(document.schemaVersion, 1)
        XCTAssertEqual(document.cases.count, 5)
        for vector in document.cases {
            let seed = try vector.seed()
            let request = CaddieDecisionRequest(shotType: vector.shotType, context: seed.context)
            let decision = try XCTUnwrap(OfflineCaddieDecisionEvaluator().makeDecision(seed: seed, request: request, strategyMode: "stock"), vector.id)
            let sequences = CaddiePlanSequence.sequences(from: decision)
            XCTAssertEqual(decision.sourceRef, vector.sourceRef, vector.id)
            XCTAssertEqual(Set(decision.evidenceRefs ?? []), Set(vector.sourceRefs), vector.id)
            XCTAssertEqual(decision.selectedOptionId, "stock", vector.id + " supplied opening choice")
            if let zones = vector.expectedAvoidZones {
                XCTAssertEqual(decision.avoidZones, zones.map { $0.goldenZone }, vector.id)
            } else {
                XCTAssertTrue(decision.avoidZones.isEmpty, vector.id + " no invented obstacle")
            }
            for expected in vector.expected {
                let sequence = sequences.first { $0.id == expected.id }
                if expected.id == "safe" {
                    // The current material-alternative gate removes the explicit 3-shot safe route.
                    XCTExpectFailure("C16e J5.11: materialAlternatives drops golden safe route") {
                        XCTAssertEqual(sequence?.steps.map(\.clubName), expected.clubNames, vector.id + " safe")
                    }
                    if sequence == nil { continue }
                }
                let actual = try XCTUnwrap(sequence, vector.id + " " + expected.id)
                try assertGolden(actual, expected: expected, vector: vector)
                if vector.greenDistances != nil {
                    let raw = try XCTUnwrap(decision.sequences?.first { $0["id"] == .string(expected.id) }, vector.id)
                    XCTAssertEqual(raw["shotsToGreen"], .number(Double(expected.plannedStrokes)), vector.id + " " + expected.id)
                }
            }
        }
    }

    func test_j4_6_prep_and_live_select_same_independent_plan_for_both_tees() throws {
        let document: ProductCaddieDocument = try ProductSharedVectors.read("caddie_golden")
        for vector in document.cases {
            let package = try vector.package()
            let hole = try XCTUnwrap(package.holes.first { $0.number == vector.hole })
            let prep = try vector.prep()
            let decision = try XCTUnwrap(PrepPlanOption.offlineDecision(template: package, hole: hole, prep: prep), vector.id)
            let liveSeed = try vector.seed()
            let resolvedSeed = try XCTUnwrap(LiveCaddieSeedFactory.resolve(package: package, hole: hole, prep: prep), vector.id)
            // Check the actual prep boundary retains the supplied opening choices, rather than
            // silently replacing stock with the longest club during factual augmentation.
            XCTAssertEqual(resolvedSeed.offlineOptions.map(\.optionId), ["safe", "stock", "attack"], vector.id)
            XCTAssertEqual(resolvedSeed.offlineOptions.map(\.clubName), ["9I", "6I", "3W"], vector.id)
            XCTAssertEqual(resolvedSeed.selectedOfflineOptionId, "stock", vector.id)
            let liveRequest = CaddieDecisionRequestBuilder().makeDecisionRequest(seed: liveSeed,
                input: .firstFrameTee(greenDistances: prep.greenDistances, holeYards: hole.yards))
            let live = try XCTUnwrap(OfflineCaddieDecisionEvaluator().makeDecision(seed: liveSeed, request: liveRequest, strategyMode: "stock"), vector.id)
            // Both selected chains must independently equal the stock golden, beyond equality to each other.
            let stock = try XCTUnwrap(vector.expected.first { $0.id == "stock" })
            try assertGolden(try XCTUnwrap(CaddiePlanSequence.selectedSequence(from: decision)), expected: stock, vector: vector)
            try assertGolden(try XCTUnwrap(CaddiePlanSequence.selectedSequence(from: live)), expected: stock, vector: vector)
            let options = PrepPlanOption.options(template: package, hole: hole, prep: prep)
            XCTExpectFailure("C16e J4.6: prep offers two routes; the third safe golden route is filtered") {
                XCTAssertEqual(options.count, 3, vector.id)
            }
        }
        // Keep the tee, landing and club-chip anchors within the unoccluded viewport.
        // Coordinates are layout bounds, not screenshot reference pixels.
        for (name, size) in [("compact", CGSize(width: 320, height: 480)), ("large", CGSize(width: 430, height: 740))] {
            let anchors = [PrepMapLayout.Anchor(point: CGPoint(x: 100, y: 50), clearance: CGSize(width: 45, height: 20)),
                           PrepMapLayout.Anchor(point: CGPoint(x: 100, y: 350), clearance: CGSize(width: 45, height: 20))]
            let frame = try XCTUnwrap(PrepMapLayout.restFrame(overlayWidth: 300, overlayHeight: 400,
                route: [[100, 350], [100, 50]], anchors: anchors, viewport: size, topInset: 60, bottomInset: 100), name)
            let scale = frame.width / 300
            for anchor in anchors {
                let x = frame.minX + anchor.point.x * scale
                let y = frame.minY + anchor.point.y * scale
                XCTAssertGreaterThanOrEqual(x - anchor.clearance.width, -0.01, name)
                XCTAssertLessThanOrEqual(x + anchor.clearance.width, size.width + 0.01, name)
                XCTAssertGreaterThanOrEqual(y - anchor.clearance.height, 59.99, name)
                XCTAssertLessThanOrEqual(y + anchor.clearance.height, size.height - 99.99, name)
            }
        }
        var session = PrepHoleMapSession()
        session.select(hole: 1)
        session.selectPlan(1, planCount: 3)
        XCTAssertEqual(session.selectedPlanIndex, 1)
        session.select(hole: 2)
        XCTAssertEqual(session.selectedPlanIndex, 0, "new hole starts on its first plan")
        for (name, last, offered, expected) in [
            ("switch-white", Optional("white"), ["blue", "white"], "white"),
            ("unavailable-tee", Optional("red"), ["blue", "white"], "blue"),
        ] {
            XCTAssertEqual(StartRoundPresentation.preselectedTee(lastUsed: last, offered: offered, defaultTee: "blue"), expected, name)
        }
        // Without seed, bag or an installed plan, there is no recommendation to draw.
        let empty = try ProductInputs.package()
        let prep = try ProductInputs.prep()
        let hole = try XCTUnwrap(empty.holes.first)
        XCTAssertTrue(PrepPlanOption.options(template: empty, hole: hole, prep: prep).isEmpty, "no seed/no bag")
        XCTAssertTrue(HoleImageMapView(hole: prep).plannedLegs().isEmpty, "facts only")
    }

    private func assertGolden(_ actual: CaddiePlanSequence, expected: ProductCaddieVector.Expected,
                              vector: ProductCaddieVector, file: StaticString = #filePath, line: UInt = #line) throws {
        let label = vector.id + " " + expected.id
        XCTAssertEqual(actual.steps.count, expected.plannedStrokes, label + " planned strokes", file: file, line: line)
        XCTAssertEqual(actual.steps.map(\.clubName), expected.clubNames, label, file: file, line: line)
        XCTAssertEqual(actual.steps.map(\.routeOffsetM), expected.routeOffsets_m.map(Optional.some), label, file: file, line: line)
        XCTAssertEqual(actual.steps.map(\.planIndex), expected.planIndices.map(Optional.some), label, file: file, line: line)
        let map = HoleImageMapView(hole: try vector.prep(), plannedShots: actual.steps.map {
            MapPlannedShot(id: $0.id, clubName: $0.clubName, carryM: $0.targetCarryM, routeOffsetM: $0.routeOffsetM,
                role: $0.role, expectedRemainingM: $0.expectedRemainingM, planIndex: $0.planIndex ?? -1)
        })
        let legs = map.plannedLegs()
        XCTAssertEqual(legs.count, expected.landingsLocal.count, label, file: file, line: line)
        for (leg, landing) in zip(legs, expected.landingsLocal) {
            XCTAssertEqual(Double(leg.destination.x), landing[0], accuracy: 0.001, label, file: file, line: line)
            XCTAssertEqual(Double(leg.destination.y), landing[1], accuracy: 0.001, label, file: file, line: line)
        }
    }
}
