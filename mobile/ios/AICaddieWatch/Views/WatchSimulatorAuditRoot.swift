#if DEBUG
import CoreLocation
import Foundation
import SwiftUI

/// Findings-only simulator harness. All navigation, gesture handling and score callbacks belong to
/// the production views/model. Only input facts and unavailable hardware states are injected here.
struct WatchSimulatorAuditRoot: View {
    static let screens: Set<String> = [
        "audit-empty", "audit-start", "audit-start-nine", "audit-phone-9", "audit-phone-18",
        "audit-restore", "audit-score-current", "audit-map-pending", "audit-late-map",
        "audit-out-of-order", "audit-next-tee", "audit-auto-candidate", "audit-heading",
        "audit-manual-candidate",
    ]
    let screen: String
    @ObservedObject var model: WatchRoundModel
    @State private var initialized = false
    @State private var ready = false
    @State private var error: String?
    @State private var fix: WatchLocationFix?
    @State private var mapArrived = false

    private let env = ProcessInfo.processInfo.environment
    private static let venueId = 31669
    private static let nineId = 32001
    private static let originLatitude = 40.0454995
    private static let longitude = 116.5461531
    static var headingUpdatesWanted = false
    private var zoom: CGFloat { CGFloat(Double(env["UITEST_AUDIT_ZOOM"] ?? "1") ?? 1) }
    private var page: Int { Int(env["UITEST_AUDIT_PAGE"] ?? "0") ?? 0 }
    private var trace: String {
        "hole=\(model.activeHole);scored=\(model.scoredHoles);strokes=\(model.totalStrokes);"
            + "shots=\(model.recordedShotCount);screen=\(model.screen);"
            + "pending=\(model.pendingManualShot != nil);auto=\(model.autoShotEnabled);"
            + "round=\(model.round != nil);map=\(geometry != nil);"
            + "ready=\(ready);headingWanted=\(Self.headingUpdatesWanted);"
    }

    var body: some View {
        Group {
            if let error {
                Text("Audit fixture failed: \(error)")
            } else if model.round != nil {
                WatchRoundContainerView(
                    model: model,
                    holeGeometry: geometry,
                    watchGreenYards: greenRanges,
                    shotLocation: fix,
                    watchHeading: screen == "audit-heading" ? WatchHeadingFix(
                        trueDegrees: 110, accuracyDegrees: 6, capturedAt: Date()
                    ) : nil,
                    autoShotSupported: env["UITEST_AUDIT_AUTOSHOT_SUPPORTED"] == "1",
                    initialGreenZoomScaleOverride: Double(zoom),
                    initialHolePage: page,
                    initialPlanViewport: WatchHoleViewport(zoom: zoom),
                    initialHazardViewport: WatchHoleViewport(zoom: zoom)
                )
                .environment(\.isLuminanceReduced, env["UITEST_AUDIT_AOD"] == "1")
            } else {
                WatchStartView(
                    phoneReachable: false,
                    courses: screen.hasPrefix("audit-start") ? startOptions : [],
                    nearbyCourses: screen.hasPrefix("audit-start") ? startOptions : [],
                    cachedCourseIds: screen.hasPrefix("audit-start") ? Set(Self.options.map(\.globalId)) : [],
                    discoveryState: .waitingForGPS,
                    onStartCourse: { selection in
                        Task { await startCachedCourse(selection) }
                    }
                )
            }
        }
        .overlay(alignment: .topLeading) {
            // Same proven clear-Text mechanism as watch-hole-page-current; no visible test controls.
            Text(trace).font(.system(size: 1)).foregroundStyle(.clear)
                .frame(width: 2, height: 2).allowsHitTesting(false)
                .accessibilityIdentifier("watch-audit-state")
        }
        .task {
            guard !initialized else { return }
            initialized = true
            do { try initialize(); ready = true } catch { self.error = String(describing: error) }
            // A deterministic stationary GPS feed, not a real receiver measurement. Unlike a single
            // startup coordinate this remains qualified during a long UI session. Stale/acquiring
            // cases intentionally receive no refresh.
            while !Task.isCancelled {
                if env["UITEST_AUDIT_RANGE"] != "stale" && env["UITEST_AUDIT_RANGE"] != "none" {
                    refreshFix()
                }
                writeState()
                try? await Task.sleep(nanoseconds: 3_000_000_000)
            }
        }
        .onChange(of: model.screen) { _, _ in writeState() }
        .onChange(of: model.activeHole) { _, _ in refreshFix(); writeState() }
        .onChange(of: model.pendingUploads) { _, _ in writeState() }
    }

    private var geometry: WatchHoleMapGeometry? {
        guard let state = model.activeHoleState, let globalId = state.globalId,
              screen != "audit-map-pending",
              screen != "audit-late-map" || mapArrived,
              let image = WatchHoleImageStore().image(
                globalId: globalId, hole: state.sourceLocalHole ?? state.hole,
                geometryRevision: state.geometryRevision
              ) else { return nil }
        guard let geometry = WatchHoleMapGeometry.from(
            holeMap: state.holeMap, image: image, hazards: state.hazards,
            greenDetailImage: WatchHoleMapSample.greenDetailImage
        ) else { return nil }
        if progressM > 0, let player = WatchHazardMapLayout.imagePoint(on: state.holeMap?.route ?? [], atMetres: progressM) {
            return geometry.withYou(player)
        }
        return geometry
    }

    private var progressM: Double {
        guard let fix, let tee = model.activeHoleState?.teeLatitude else { return 0 }
        return max(0, (fix.coordinate.latitude - tee) * 111_195)
    }

    private var greenRanges: (front: Int?, center: Int?, back: Int?)? {
        guard fix != nil else { return nil }
        return (WatchUnits.yards(max(0, 505 - progressM)), WatchUnits.yards(max(0, 518.8 - progressM)),
                WatchUnits.yards(max(0, 531 - progressM)))
    }

    private static var options: [WatchCourseOption] {
        [
            WatchCourseOption(globalId: venueId, name: "模拟审查球场", holes: 18,
                              teeBox: "Blue", venueName: "模拟审查球场",
                              segmentHoles: 18, tees: ["Blue", "White"]),
            WatchCourseOption(globalId: nineId, name: "模拟审查球场 ~ A", holes: 9,
                              teeBox: "Blue", venueName: "模拟审查球场",
                              segmentLabel: "A", segmentHoles: 9, tees: ["Blue", "White"]),
            WatchCourseOption(globalId: 32002, name: "模拟审查球场 ~ B", holes: 9,
                              teeBox: "Blue", venueName: "模拟审查球场",
                              segmentLabel: "B", segmentHoles: 9, tees: ["Blue", "White"]),
        ]
    }

    private var startOptions: [WatchCourseOption] {
        screen == "audit-start-nine" ? [Self.options[1], Self.options[2], Self.options[0]] : Self.options
    }

    /// Repeating an existing review hole is a UI fixture, never a claim about an actual 18-hole map.
    private static func states(count: Int, globalId: Int, roundId: String) throws -> [WatchRoundState] {
        let source = try JSONSerialization.jsonObject(
            with: JSONEncoder().encode(WatchUITestRoot.auditMappedHole)
        ) as! [String: Any]
        return try (1...count).map { hole in
            var row = source
            row["roundId"] = roundId
            row["hole"] = hole
            row["globalId"] = globalId
            row["sourceLocalHole"] = hole
            row["courseHoleNumber"] = hole
            let latitude = originLatitude + Double(hole - 1) * 0.008
            row["teeLatitude"] = latitude
            row["teeLongitude"] = longitude
            row["frontGreenLat"] = latitude + 505 / 111_195
            row["centerGreenLat"] = latitude + 518.8 / 111_195
            row["backGreenLat"] = latitude + 531 / 111_195
            row["frontGreenLon"] = longitude
            row["centerGreenLon"] = longitude
            row["backGreenLon"] = longitude
            return try JSONDecoder().decode(WatchRoundState.self, from: JSONSerialization.data(withJSONObject: row))
        }
    }

    private static func storeImages(_ states: [WatchRoundState]) throws {
        let data = Data(base64Encoded: WatchHoleMapSample.jpegBase64)!
        for state in states {
            try WatchHoleImageStore().store(data: data, globalId: state.globalId!,
                                            hole: state.sourceLocalHole!, geometryRevision: state.geometryRevision)
        }
    }

    @MainActor
    private func initialize() throws {
        model.config = nil
        model.secondLoopLoader = { request in await WatchCourseLibrary().secondLoop(request, config: nil) }
        if screen == "audit-restore" { return }
        if screen == "audit-score-current" {
            model.resumeRound()
            model.startScoringActiveHole()
            return
        }
        model.setAutoShotEnabled(false)
        // These are newly named test authorities. They replace only simulator fixture data.
        WatchRoundStore().clear()
        model.refreshFromStore()
        if screen == "audit-empty" { return }
        if screen.hasPrefix("audit-start") {
            for option in Self.options {
                let states = try Self.states(count: option.holes, globalId: option.globalId,
                                             roundId: "audit-template")
                try Self.storeImages(states)
                try WatchCourseStore().save(WatchCourseTemplate(
                    option: option, courseName: option.displayName, teeBox: "Blue",
                    holeStates: states, cachedAt: ISO8601DateFormatter().string(from: Date())
                ))
            }
            return
        }
        let count = screen == "audit-phone-9" ? 9 : 18
        let globalId = count == 9 ? Self.nineId : Self.venueId
        let key = count == 9 ? "\(globalId):all" : "\(globalId):front+\(globalId):back"
        let roundId = "audit-\(UUID().uuidString)"
        let states = try Self.states(count: count, globalId: globalId, roundId: roundId)
        let seed = WatchRoundSeed(
            roundId: roundId, courseName: "模拟审查球场", activeHole: 1,
            holes: states.map {
                WatchRoundSeedHole(hole: $0.hole, par: $0.par, distanceM: $0.distanceM,
                                   teeLatitude: $0.teeLatitude, teeLongitude: $0.teeLongitude,
                                   globalId: globalId, localHole: $0.sourceLocalHole,
                                   courseHoleNumber: $0.courseHoleNumber)
            }, globalId: globalId, teeBox: "Blue", loopKey: key
        )
        model.applyRoundSeed(seed)
        if screen != "audit-map-pending" {
            model.applyCourseMapUpgrade(states)
            if screen != "audit-late-map" { try Self.storeImages(states) }
        }
        model.resumeRound()
        refreshFix()
        model.secondLoopLoader = { request in
            guard let key = request.loopKey else { return .unavailable("Audit fixture has no loop key") }
            do {
                let states = try Self.states(count: 18, globalId: Self.venueId, roundId: request.roundId)
                return .ready(loopKey: key, holeStates: Array(states.suffix(9)))
            } catch { return .unavailable("Audit second-loop fixture failed") }
        }
        if screen == "audit-late-map" {
            Task { @MainActor in
                try? await Task.sleep(nanoseconds: 6_000_000_000)
                do { try Self.storeImages(states); mapArrived = true }
                catch { self.error = String(describing: error) }
            }
        }
        if screen == "audit-out-of-order" {
            model.selectHole(2)
            var newer = try JSONSerialization.jsonObject(with: JSONEncoder().encode(states[0])) as! [String: Any]
            newer["snapshotRevision"] = 20
            newer["score"] = 6
            newer["phoneShotEventIds"] = []
            model.receivePhoneState(try JSONDecoder().decode(WatchRoundState.self, from: JSONSerialization.data(withJSONObject: newer)))
            newer["snapshotRevision"] = 19
            newer["score"] = 3
            model.receivePhoneState(try JSONDecoder().decode(WatchRoundState.self, from: JSONSerialization.data(withJSONObject: newer)))
        }
        if screen == "audit-next-tee" {
            model.beginManualShot(latitude: Self.originLatitude + 0.008, longitude: Self.longitude,
                                  horizontalAccuracyM: 5, capturedAt: ISO8601DateFormatter().string(from: Date()))
        }
        if screen == "audit-manual-candidate" {
            model.beginManualShot(latitude: Self.originLatitude, longitude: Self.longitude,
                                  horizontalAccuracyM: 5, capturedAt: ISO8601DateFormatter().string(from: Date()))
        }
        if screen == "audit-auto-candidate" {
            model.setAutoShotEnabled(true)
            _ = model.proposeAutoShotCandidate(latitude: Self.originLatitude, longitude: Self.longitude,
                                               horizontalAccuracyM: 5, capturedAt: ISO8601DateFormatter().string(from: Date()))
        }
        if screen == "audit-heading" { model.openFlagDirection() }
    }

    @MainActor
    private func startCachedCourse(_ selection: WatchCourseSelection) async {
        let library = WatchCourseLibrary()
        guard let prepared = await library.startCourse(selection, config: nil) else {
            error = library.errorMessage ?? "Audit cached course did not start"
            return
        }
        model.seedRound(prepared.holeStates, activeHole: prepared.holeStates.first?.hole,
                        courseName: prepared.courseName, courseGlobalId: selection.front.globalId,
                        teeBox: selection.teeBox, loopKey: selection.loopKey)
        model.secondLoopLoader = { request in await library.secondLoop(request, config: nil) }
        refreshFix()
    }

    private func refreshFix() {
        guard env["UITEST_AUDIT_RANGE"] != "none" else { fix = nil; return }
        let movement = env["UITEST_AUDIT_RANGE"] == "far" ? 1.0
            : (env["UITEST_AUDIT_MOVE_AFTER_SHOT"] == "1" && model.recordedShotCount > 0 ? 201.2 / 111_195 : 0)
        let latitude = (model.activeHoleState?.teeLatitude ?? Self.originLatitude) + movement
        let date = env["UITEST_AUDIT_RANGE"] == "stale" ? Date().addingTimeInterval(-120) : Date()
        fix = WatchLocationFix(coordinate: CLLocationCoordinate2D(latitude: latitude, longitude: Self.longitude),
                               horizontalAccuracyM: 5, capturedAt: ISO8601DateFormatter().string(from: date))
    }

    private func writeState() {
        let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let row: [String: Any] = ["trace": trace, "screen": screen, "input": "synthetic-review-fixture",
                                  "holeCount": model.holeCount, "totalStrokes": model.totalStrokes,
                                  "totalPutts": model.totalPutts, "scoredHoles": model.scoredHoles]
        if let data = try? JSONSerialization.data(withJSONObject: row, options: .sortedKeys) {
            try? data.write(to: directory.appendingPathComponent("watch-audit-state.json"), options: .atomic)
        }
    }
}
#endif
