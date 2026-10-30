import CoreLocation
import SwiftUI
import UIKit
import XCTest
@testable import AICaddie

/// J5.10 page responsiveness and J5.11 request/refresh behavior through real hosted SwiftUI state.
/// Twenty current-hole club events must request zero adjacent bodies.
@MainActor
final class ProductLiveHolePageTests: XCTestCase {
    #if !SWIFT_PACKAGE
    // J5.11: synthetic dogleg inputs, with independently specified 284.3 m straight range and
    // 320.9 m centreline stations. No expected value is derived from the planner under test.
    private func decisionPackage() throws -> LiveRoundPackage {
        let base = try ProductInputs.package().rebasedForOfflineStart(roundId: UUID().uuidString)
        var json = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(base)) as? [String: Any])
        let profiles: [[String: Any]] = [
            ["clubName": "Driver", "sampleSize": 24, "median_m": 197, "p10_m": 189, "p90_m": 205],
            ["clubName": "8I", "sampleSize": 24, "median_m": 121, "p10_m": 115, "p90_m": 127],
        ]
        json["clubProfiles"] = profiles
        // One pixel/metre, affine equatorial anchors (100 m = 0.000899321606 degrees).
        let prep: [String: Any] = [
            "hole": 1, "par": 4, "par_source": "synthetic", "blue_yards": 351, "route_len_m": 320.9,
            "geometryCoverage": "ready", "geometryRevision": "dogleg-r1",
            "route": [[20.0, 350.0], [130.0, 250.0], [304.3, 350.0]],
            "map": ["overlay": ["w": 400, "h": 400, "ppm": 1, "ln": 320.9,
                "route": [[20.0, 350.0, 0.0], [130.0, 250.0, 135.5], [304.3, 350.0, 320.9]]]],
            "holeImageProjection": ["available": true, "widthPx": 400, "heightPx": 400, "refs": [
                ["lat": 0.0, "lon": 0.0, "px": 20.0, "py": 350.0],
                ["lat": 0.0, "lon": 0.000899321606, "px": 120.0, "py": 350.0],
                ["lat": 0.000899321606, "lon": 0.0, "px": 20.0, "py": 250.0],
            ]],
            "greenDistances": ["available": true, "middleM": 284.3,
                               "middleLat": 0.0, "middleLon": 0.002556771326],
            "steps": [
                ["clubName": "Driver", "note": "", "targetCarryM": 197, "routeOffsetM": 197,
                 "role": "tee", "planIndex": 0],
                ["clubName": "8I", "note": "", "targetCarryM": 121, "routeOffsetM": 318,
                 "role": "scoring", "planIndex": 1],
            ],
            "cautions": [], "hazards": ["water_carry": [], "bunkers": [], "details": []],
        ]
        json["coursePrep"] = ["schema": "ai-caddie-course-prep-v1", "globalId": 81001, "holes": [prep]]
        json["caddieContextSeeds"] = [[
            "hole": 1, "sourceRef": "synthetic:dogleg", "shotTypes": ["tee"], "requiredLiveInputs": [],
            "context": ["par": 4, "clubProfiles": profiles], "selectedOfflineOptionId": "stock",
            "offlineOptions": [["id": "stock", "label": "推荐", "clubName": "Driver", "carryM": 197,
                                "sampleSize": 24, "confidence": "high", "riskScore": 0,
                                "source": "synthetic", "sourceRefs": []]],
            "evidence": [], "missingData": [],
        ]]
        return try ProductSharedVectors.decode(json)
    }

    private func pageDecision(empty: Bool = false) throws -> CaddieDecisionResponse {
        let sequence: [String: Any] = ["id": "online-safe", "label": "推荐", "clubs": [
            ["clubName": "8I", "role": "advance", "targetCarry_m": 121, "routeOffset_m": 121],
            ["clubName": "Driver", "role": "scoring", "targetCarry_m": 197, "routeOffset_m": 318],
        ]]
        var json: [String: Any] = [
            "schema": "ai-caddie-decision-v2", "decisionId": "online-result", "shotType": "tee", "phase": "Tee",
            "context": [:], "options": [], "sequences": empty ? [] : [sequence],
            "avoidZones": [], "forbiddenZones": [], "acceptableMiss": [:], "evidence": [],
            "confidence": [:], "missingData": [], "auditCriteria": [],
        ]
        if !empty { json["selectedSequence"] = sequence; json["selectedOptionId"] = "online-safe" }
        return try ProductSharedVectors.decode(json)
    }

    private func withDecisionPage(
        package: LiveRoundPackage? = nil,
        cache: LiveHoleSessionCache = LiveHoleSessionCache(),
        locationProvider: LocationProvider? = nil,
        _ exercise: (LiveHoleDecisionProbe) async throws -> Void
    ) async throws {
        let package = try package ?? decisionPackage()
        let hole = try XCTUnwrap(package.holes.first)
        let session = C33URLProtocol.session()
        let client = CaddieDecisionClient(baseURL: URL(string: "https://decisions.example.test")!, session: session)
        let probe = LiveHoleDecisionProbe()
        let defaultFix = LocationFix(coordinate: .init(latitude: 0, longitude: 0), horizontalAccuracyM: 5,
                                     altitudeM: nil, capturedAt: "2026-10-01T00:00:00Z")
        // A nonselected mounted page retains SwiftUI state but starts no lifecycle/network tasks.
        let view = CurrentHoleView(package: package, hole: hole, caddieClient: client,
                                   sessionCache: cache, isSelected: false)
            .observingDecisionsForTesting(
                probe,
                locationProvider: locationProvider ?? LocationProvider(fixedFix: defaultFix)
            )
        let host = UIHostingController(rootView: view)
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 390, height: 844))
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
            probe.refresh = nil; probe.request = nil; probe.routes = nil; probe.source = nil
            probe.planningDistance = nil; probe.offlineDecision = nil; probe.offlineRequest = nil
            probe.mapTargetDistance = nil; probe.setTarget = nil
            session.invalidateAndCancel()
            C33URLProtocol.setHandlers(onStart: nil)
        }
        let mounted = try await waitForHostedState(host) { probe.refresh != nil }
        XCTAssertTrue(mounted)
        try await exercise(probe)
    }

    func test_j5_11_request_keeps_straight_distance_while_local_dogleg_uses_route() async throws {
        try await withDecisionPage { probe in
            let request = try XCTUnwrap(probe.request)
            let setTarget = try XCTUnwrap(probe.setTarget)
            let initial = try XCTUnwrap(request())
            guard case .number(let initialDistance)? = initial.context["distanceToPin_m"] else {
                return XCTFail("wire distance missing")
            }
            XCTAssertEqual(initialDistance, 284.3, accuracy: 0.1,
                           "on-hole wire value has main's straight-distance semantics")
            setTarget(CGPoint(x: 189, y: 350)) // 169 m Touch Target from tee.
            XCTAssertEqual(try XCTUnwrap(probe.mapTargetDistance)() ?? -1, 169, accuracy: 0.1,
                           "Touch Target state is written before checking its wire isolation")
            let targeted = try XCTUnwrap(request())
            guard case .number(let distance)? = targeted.context["distanceToPin_m"] else {
                return XCTFail("wire distance missing")
            }
            XCTAssertEqual(distance, 284.3, accuracy: 0.1, "Touch Target cannot change the wire distance")
            XCTAssertNil(targeted.context["canonicalPlanRemainingRouteLength_m"], "local context never goes online")
            let offlineRequest = try XCTUnwrap(probe.offlineRequest)
            XCTAssertEqual(try XCTUnwrap(offlineRequest()).context["canonicalPlanRemainingRouteLength_m"], .number(320.9))
            let offline = try XCTUnwrap(probe.offlineDecision)
            let route = try XCTUnwrap(CaddiePlanSequence.selectedSequence(from: try XCTUnwrap(offline())))
            XCTAssertEqual(route.steps.map(\.clubName), ["Driver", "8I"])
            XCTAssertGreaterThanOrEqual(route.steps.last?.routeOffsetM ?? 0, 306.2)
            XCTAssertEqual(try XCTUnwrap(probe.planningDistance)() ?? -1, 320.9, accuracy: 0.1)
        }
    }

    /// J5.11: off-hole and no-GPS tee requests keep the full factual dogleg for local planning;
    /// a static straight fallback must not masquerade as a measured remaining route.
    func test_j5_11_off_hole_or_no_location_keeps_whole_tee_route() async throws {
        let offHoleFix = LocationFix(
            coordinate: .init(latitude: 0.01, longitude: 0.01), horizontalAccuracyM: 5,
            altitudeM: nil, capturedAt: "2026-10-01T00:00:00Z"
        )
        let cases: [(String, LocationProvider)] = [
            ("off-hole", LocationProvider(fixedFix: offHoleFix)),
            ("no-location", LocationProvider()),
        ]
        for (label, provider) in cases {
            try await withDecisionPage(locationProvider: provider) { probe in
                let offlineRequest = try XCTUnwrap(probe.offlineRequest)
                let context = try XCTUnwrap(offlineRequest()?.context)
                XCTAssertNil(
                    context["canonicalPlanRemainingRouteLength_m"],
                    "\(label) has no measured remaining route; a straight fallback must not fill it"
                )
                XCTAssertNotNil(context["canonicalPlanRouteLength_m"], "\(label) keeps the full tee route")
                let offlineDecision = try XCTUnwrap(probe.offlineDecision)
                let decision = try XCTUnwrap(offlineDecision())
                let route = try XCTUnwrap(CaddiePlanSequence.selectedSequence(from: decision))
                XCTAssertEqual(route.steps.map(\.clubName), ["Driver", "8I"], "\(label) route")
                XCTAssertGreaterThanOrEqual(route.steps.last?.routeOffsetM ?? 0, 306.2, "\(label) endpoint")
            }
        }
    }

    /// J5.11: run seed -> online -> each real load fallback, checking the published physical chain
    /// and the actual session flag. Removing any corresponding write-back must fail this test.
    private func assertOnlineRefreshRetained(_ fallback: String) async throws {
        let package = try decisionPackage()
        let cache = LiveHoleSessionCache()
        let hole = try XCTUnwrap(package.holes.first)
        let online = try JSONEncoder().encode(pageDecision())
        let empty = try JSONEncoder().encode(pageDecision(empty: true))
        try await withDecisionPage(package: package, cache: cache) { probe in
            let refresh = try XCTUnwrap(probe.refresh)
            let routes = try XCTUnwrap(probe.routes)
            probe.clientUnavailable = true
            await refresh() // Actual no-client seed, then the online response.
            XCTAssertEqual(routes().first?.steps.map(\.clubName), ["Driver", "8I"])
            probe.clientUnavailable = false
            C33URLProtocol.setHandlers(onStart: { $0.reply(200, online) })
            await refresh()
            XCTAssertEqual(routes().map(\.id), ["online-safe"])
            XCTAssertEqual(routes().first?.steps.map(\.clubName), ["8I", "Driver"])
            if fallback == "no-client" {
                probe.clientUnavailable = true
            } else if fallback == "empty" {
                C33URLProtocol.setHandlers(onStart: { $0.reply(200, empty) })
            } else {
                C33URLProtocol.setHandlers(onStart: { proto in
                    proto.client?.urlProtocol(proto, didFailWithError: URLError(.notConnectedToInternet))
                })
            }
            await refresh()
            let entry = cache.entry(roundId: package.roundId, hole: hole.number,
                                    sourceGlobalId: hole.sourceGlobalId, sourceLocalHole: hole.sourceLocalHole,
                                    teeBox: package.course.teeBox)
            XCTAssertFalse(entry.caddieDecisionIsOnline, "\(fallback) must clear the real page's online flag")
            XCTAssertEqual(routes().map(\.id), ["online-safe"], "\(fallback) must retain the online route")
            XCTAssertEqual(routes().first?.steps.map(\.clubName), ["8I", "Driver"])
        }
    }

    func test_j5_11_online_then_error_retains_route() async throws {
        try await assertOnlineRefreshRetained("error")
    }

    func test_j5_11_online_then_empty_card_retains_route() async throws {
        try await assertOnlineRefreshRetained("empty")
    }

    func test_j5_11_online_then_no_client_retains_route() async throws {
        try await assertOnlineRefreshRetained("no-client")
    }

    func test_j5_11_unsigned_online_response_clears_previous_cache_identity() throws {
        var entry = LiveHoleSessionCache.Entry()
        entry.storeOnlineDecision(try pageDecision(), inputSignature: "previous-input")
        entry.storeOnlineDecision(try pageDecision(), inputSignature: nil)
        XCTAssertNil(entry.caddieDecisionInputSignature)
        XCTAssertTrue(LiveHoleSessionCachePolicy.shouldFetchDecision(
            inputSignature: "previous-input", cachedSignature: entry.caddieDecisionInputSignature,
            hasCachedDecision: entry.caddieDecision != nil
        ))
    }

    /// J5.11: a local route from the current geometry keeps its provenance across page unloads,
    /// so a later installed CoursePrep chain can replace it instead of being blocked as online.
    func test_j5_11_restored_local_route_allows_later_installed_upgrade() async throws {
        let package = try decisionPackage()
        let hole = try XCTUnwrap(package.holes.first)
        let prep = try XCTUnwrap(package.coursePrep?.holes.first { $0.hole == hole.number })
        let revision = try XCTUnwrap(LiveHoleSessionCache.cacheRevision(hole: hole, prep: prep))
        let cache = LiveHoleSessionCache()
        let response = try pageDecision()
        let localRoute = try XCTUnwrap(CaddiePlanSequence.selectedSequence(from: response))
        // Match the page's versioned read. A nil revision would invalidate this route before
        // restoration and exercise the initial installed fallback instead of local provenance.
        cache.update(roundId: package.roundId, hole: hole.number,
                     sourceGlobalId: hole.sourceGlobalId, sourceLocalHole: hole.sourceLocalHole,
                     teeBox: package.course.teeBox, geometryRevision: revision) { entry in
            entry.caddieRoutes = [localRoute]
            entry.caddieDecisionIsOnline = false
        }
        let cached = cache.entry(roundId: package.roundId, hole: hole.number,
                                 sourceGlobalId: hole.sourceGlobalId, sourceLocalHole: hole.sourceLocalHole,
                                 teeBox: package.course.teeBox, geometryRevision: revision)
        XCTAssertEqual(cached.caddieRoutes.map(\.id), ["online-safe"])
        XCTAssertFalse(cached.caddieDecisionIsOnline)
        try await withDecisionPage(package: package, cache: cache) { probe in
            let routes = try XCTUnwrap(probe.routes)
            let source = try XCTUnwrap(probe.source)
            let refresh = try XCTUnwrap(probe.refresh)
            XCTAssertEqual(routes().map(\.id), ["online-safe"], "the cached local route must actually be restored")
            XCTAssertEqual(source(), .offline, "restored local route is not online")
            probe.clientUnavailable = true
            await refresh()
            XCTAssertEqual(routes().map(\.id), [LiveCaddieRouteAuthority.installedRouteId])
            XCTAssertEqual(routes().first?.steps.map(\.clubName), ["Driver", "8I"])
        }
    }

    /// J5.11: a route without matching geometry is no longer an available fact; the page must
    /// use the current installed chain rather than misrepresent an invalidated cache as restored.
    func test_j5_11_unversioned_or_stale_cached_route_uses_current_installed_facts() async throws {
        let package = try decisionPackage()
        let hole = try XCTUnwrap(package.holes.first)
        let prep = try XCTUnwrap(package.coursePrep?.holes.first { $0.hole == hole.number })
        let revision = try XCTUnwrap(LiveHoleSessionCache.cacheRevision(hole: hole, prep: prep))
        let localRoute = try XCTUnwrap(CaddiePlanSequence.selectedSequence(from: pageDecision()))
        let cachedRevisions: [String?] = [nil, "dogleg-r0"]
        for cachedRevision in cachedRevisions {
            let cache = LiveHoleSessionCache()
            cache.update(roundId: package.roundId, hole: hole.number,
                         sourceGlobalId: hole.sourceGlobalId, sourceLocalHole: hole.sourceLocalHole,
                         teeBox: package.course.teeBox, geometryRevision: cachedRevision) { entry in
                entry.caddieRoutes = [localRoute]
                entry.caddieDecisionIsOnline = false
            }
            let stored = cache.entry(roundId: package.roundId, hole: hole.number,
                                     sourceGlobalId: hole.sourceGlobalId, sourceLocalHole: hole.sourceLocalHole,
                                     teeBox: package.course.teeBox)
            XCTAssertEqual(stored.caddieRoutes.map(\.id), ["online-safe"])
            let cached = cache.entry(roundId: package.roundId, hole: hole.number,
                                     sourceGlobalId: hole.sourceGlobalId, sourceLocalHole: hole.sourceLocalHole,
                                     teeBox: package.course.teeBox, geometryRevision: revision)
            XCTAssertTrue(cached.caddieRoutes.isEmpty)
            try await withDecisionPage(package: package, cache: cache) { probe in
                XCTAssertEqual(try XCTUnwrap(probe.source)(), .installed)
                let routes = try XCTUnwrap(probe.routes)
                XCTAssertEqual(routes().map(\.id), [LiveCaddieRouteAuthority.installedRouteId])
                XCTAssertEqual(routes().first?.steps.map(\.clubName), ["Driver", "8I"])
            }
        }
    }

    /// Drive the callbacks used by CurrentHoleView with the real first-stroke model and store.
    /// Deliberately do not refresh the rendered callback Value between starting and dismissal.
    private func withPrepSession(
        _ exercise: (LiveRoundAppModel, LiveRoundPackage, OfflineStore, LiveHolePageNavigationProbe) throws -> Void
    ) async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://page-navigation.example.test")!, session: session)
        let model = LiveRoundAppModel(
            offlineStore: store, apiBaseURL: client.baseURL, watchBridge: nil,
            garminSessionStore: nil, syncClient: client,
            offlineGeometryRetryDelaysNanoseconds: [], networkPathObserver: nil
        )
        await model.stopRoundBackgroundWorkForTesting()
        defer {
            session.invalidateAndCancel()
            try? FileManager.default.removeItem(at: directory)
        }
        let package = try ProductInputs.package().rebasedForOfflineStart(roundId: UUID().uuidString)
        model.enterPrepMode(with: package, hole: 4)
        let probe = LiveHolePageNavigationProbe()
        let view = RoundHomeView(
            package: model.package, offlineStore: store, sessionStore: nil,
            liveRoundState: model.liveRoundState,
            onEvent: model.handleEvent, onSetActiveHole: model.setActiveHole,
            prepPackage: model.prepPackage, onPrepHoleChanged: model.prioritizePrepHole,
            onStartRoundFromFirstStroke: { model.startRoundFromFirstStroke(startHole: $0) }
        ).observingHolePageNavigationForTesting(
            probe, initialPath: [.startCourse(globalId: package.course.globalId, teeBox: nil), .hole(4)]
        )
        let host = UIHostingController(rootView: view)
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 390, height: 844))
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
            probe.starts.removeAll()
            probe.dismissals.removeAll()
            probe.backs.removeAll()
            probe.openPrepCourse = nil
            probe.path = nil
            probe.callbacks = nil
        }
        let mounted = try await waitForHostedState(host) { probe.starts[4] != nil }
        XCTAssertTrue(mounted, "the actual RHV destination must mount before the deadline")
        XCTAssertNotNil(probe.starts[4], "the actual RHV hole destination must mount")
        try exercise(model, package, store, probe)
    }

    func test_j5_2_first_stroke_sheet_dismissal_replaces_prep_base_before_callback_refresh() async throws {
        try await withPrepSession { model, package, store, probe in
            let path = try XCTUnwrap(probe.path)
            let start = try XCTUnwrap(probe.starts[4])
            let dismiss = try XCTUnwrap(probe.dismissals[4])
            let callbacks = try XCTUnwrap(probe.callbacks)
            XCTAssertEqual(path.wrappedValue,
                           [.startCourse(globalId: package.course.globalId, teeBox: nil), .hole(4)])
            XCTAssertNil(model.liveRoundState)
            XCTAssertTrue(start(4))
            XCTAssertEqual(model.liveRoundState?.activeHole, 4)
            XCTAssertEqual(try store.inProgressRoundId(), package.roundId)
            XCTAssertFalse(callbacks.value.hasLiveRound, "no body/callback refresh has occurred")
            dismiss()
            // J5.2: Back dismisses one destination. Only the live hole may remain above home.
            XCTAssertEqual(path.wrappedValue, [.hole(4)])
            path.wrappedValue.removeLast()
            XCTAssertTrue(path.wrappedValue.isEmpty, "Back must reach home, not the same prep hole")
            XCTAssertNotNil(model.liveRoundState, "returning home must retain the active-round hero")
        }
    }

    func test_j5_2_unstarted_sheet_dismissal_keeps_the_prep_base() async throws {
        try await withPrepSession { _, package, _, probe in
            let path = try XCTUnwrap(probe.path)
            let dismiss = try XCTUnwrap(probe.dismissals[4])
            let expected: [HubRoute] = [.startCourse(globalId: package.course.globalId, teeBox: nil), .hole(4)]
            dismiss()
            XCTAssertEqual(path.wrappedValue, expected, "a failed/unstarted round must keep its prep navigation")
        }
    }

    func test_j5_10_started_round_stops_prep_following_and_persists_live_cursor_before_refresh() async throws {
        try await withPrepSession { model, package, _, probe in
            let callbacks = try XCTUnwrap(probe.callbacks)
            let start = try XCTUnwrap(probe.starts[4])
            XCTAssertNotNil(callbacks.prepPackage(displayed: package, wasPrep: true))
            XCTAssertTrue(start(4))
            XCTAssertNil(callbacks.prepPackage(displayed: package, wasPrep: true),
                         "a cached prep flag must not let GPS move a now-live round")
            callbacks.persistActiveHole(5, displayed: package, wasPrep: true)
            XCTAssertEqual(model.liveRoundState?.activeHole, 5,
                           "the same cached prep flag must not swallow a live page advance")
        }
    }

    func test_j5_10_prep_geometry_belongs_to_the_displayed_page_not_cached_package() async throws {
        try await withPrepSession { _, package, _, probe in
            let callbacks = try XCTUnwrap(probe.callbacks)
            // The retained page must not borrow another tee/round's geometry from a later body.
            callbacks.value.package = package.rebasedForOfflineStart(roundId: UUID().uuidString)
            let prep = try XCTUnwrap(callbacks.prepPackage(displayed: package, wasPrep: true))
            XCTAssertEqual(prep, package)
        }
    }

    func test_j5_2_old_page_cannot_promote_or_move_a_different_active_round() async throws {
        try await withPrepSession { model, package, _, probe in
            let callbacks = try XCTUnwrap(probe.callbacks)
            let path = try XCTUnwrap(probe.path)
            let dismiss = try XCTUnwrap(probe.dismissals[4])
            let previousPath = path.wrappedValue
            let other = package.rebasedForOfflineStart(roundId: UUID().uuidString)
            model.enterPrepMode(with: other, hole: 4)
            XCTAssertTrue(model.startRoundFromFirstStroke(startHole: 4))
            dismiss()
            XCTAssertEqual(path.wrappedValue, previousPath)
            XCTAssertNil(callbacks.prepPackage(displayed: package, wasPrep: true))
            callbacks.persistActiveHole(5, displayed: package, wasPrep: true)
            XCTAssertEqual(model.liveRoundState?.roundId, other.roundId)
            XCTAssertEqual(model.liveRoundState?.activeHole, 4,
                           "the outgoing page cannot write the new round's cursor")
        }
    }

    @MainActor
    private struct ObservedHome: View {
        @ObservedObject var model: LiveRoundAppModel
        let preparedPackage: LiveRoundPackage
        let probe: LiveHolePageNavigationProbe

        var body: some View {
            RoundHomeView(
                package: model.package, offlineStore: model.offlineStore, sessionStore: nil,
                liveRoundState: model.liveRoundState,
                courseOptions: [ProductInputs.course(preparedPackage.course.globalId, venue: "Example", holes: 18)],
                onEvent: model.handleEvent, onSetActiveHole: model.setActiveHole,
                pendingLiveHole: model.pendingLiveHole,
                onConsumePendingLiveHole: model.consumePendingLiveHole,
                prepPackage: model.prepPackage,
                onOpenPrepCourse: { course in
                    guard course.globalId == preparedPackage.course.globalId else { return false }
                    // Inject only the already-loaded course package; route changes and first-stroke
                    // activation still run through the real RHV/model, observed as in the app.
                    model.enterPrepMode(with: preparedPackage, hole: 1)
                    return true
                },
                onPrepHoleChanged: model.prioritizePrepHole,
                onClosePrep: model.closePrepMode,
                onStartRoundFromFirstStroke: { model.startRoundFromFirstStroke(startHole: $0) }
            ).observingHolePageNavigationForTesting(probe, initialPath: [.start])
        }
    }

    func test_j5_2_new_round_route_back_action_reaches_home_after_first_stroke() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = OfflineStore(directoryURL: directory)
        let session = C33URLProtocol.session()
        let client = SyncClient(baseURL: URL(string: "https://page-navigation.example.test")!, session: session)
        let model = LiveRoundAppModel(
            offlineStore: store, apiBaseURL: client.baseURL, watchBridge: nil,
            garminSessionStore: nil, syncClient: client,
            offlineGeometryRetryDelaysNanoseconds: [], networkPathObserver: nil
        )
        await model.stopRoundBackgroundWorkForTesting()
        let package = try ProductInputs.package().rebasedForOfflineStart(roundId: UUID().uuidString)
        let probe = LiveHolePageNavigationProbe()
        let host = UIHostingController(rootView: ObservedHome(model: model, preparedPackage: package, probe: probe))
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 390, height: 844))
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
            probe.starts.removeAll()
            probe.dismissals.removeAll()
            probe.backs.removeAll()
            probe.openPrepCourse = nil
            probe.path = nil
            probe.callbacks = nil
            session.invalidateAndCancel()
            try? FileManager.default.removeItem(at: directory)
        }

        let pickerMounted = try await waitForHostedState(host) { probe.openPrepCourse != nil }
        XCTAssertTrue(pickerMounted)
        let path = try XCTUnwrap(probe.path)
        XCTAssertEqual(path.wrappedValue, [.start])
        let open = try XCTUnwrap(probe.openPrepCourse)
        XCTAssertTrue(open(ProductInputs.course(package.course.globalId, venue: "Example", holes: 18)))
        let prepMounted = try await waitForHostedState(host) {
            path.wrappedValue == [.hole(1)] && probe.starts[1] != nil && probe.selected[1] == true
        }
        XCTAssertTrue(prepMounted, "normal new-round entry must replace .start with one selected hole")
        XCTAssertNil(model.liveRoundState)
        let start = try XCTUnwrap(probe.starts[1])
        XCTAssertTrue(start(1))
        let liveRendered = try await waitForHostedState(host) { probe.callbacks?.value.hasLiveRound == true }
        XCTAssertTrue(liveRendered, "unlike the shortcut race fixture, this home observes model publication")
        let sheetDismissed = try XCTUnwrap(probe.dismissals[1])
        sheetDismissed()
        XCTAssertEqual(path.wrappedValue, [.hole(1)], "the shortcut prep-base guard is irrelevant on this route")
        XCTAssertEqual(probe.selected[1], true)
        let back = try XCTUnwrap(probe.backs[1]) // Exact action passed to LivePlayTopInfo's Button.
        back()
        let reachedHome = try await waitForHostedState(host) { path.wrappedValue.isEmpty }
        XCTAssertTrue(reachedHome, "J5.2: the actual Back action must reach home, not just mutate a test array")
        XCTAssertEqual(model.liveRoundState?.roundId, package.roundId)
        XCTAssertEqual(try store.inProgressRoundId(), package.roundId, "the resumable round must remain intact")
    }
    #endif

    private func waitForHostedState(
        _ host: UIViewController, until condition: () -> Bool
    ) async throws -> Bool {
        let deadline = Date().addingTimeInterval(10)
        while !condition(), Date() < deadline {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            await Task.yield()
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        return condition()
    }

    private final class Probe {
        var bodies: [Int: Int] = [:]
        var events: [(Int, LiveRoundEvent)] = []
        var advances: [(Int, Int)] = []
        var callbacks: [Int: (event: (LiveRoundEvent) -> Void, advance: (Int) -> Void)] = [:]
        var inputs: [Int: LiveHolePageInput] = [:]
        var states: [Int: LiveRoundStateSnapshot] = [:]
    }

    private final class Model: ObservableObject {
        let package: LiveRoundPackage
        let probe = Probe()
        let latest = LiveHolePageCallbacks()
        @Published var state: LiveRoundStateSnapshot
        @Published var selected = 1
        @Published var downloadedCourseOptions: [MobileCourseOption] = []
        @Published var interactionRevision = 0
        var generation = 0
        var navigationLock: LiveHoleNavigationLock? = LiveHoleNavigationLock(currentHole: 1)

        init() throws {
            package = try ProductInputs.package()
            state = LiveRoundStateSnapshot(roundId: package.roundId, activeHole: 1, holes: [
                Self.hole(1, roundId: package.roundId), Self.hole(2, roundId: package.roundId)
            ])
        }

        private static func hole(_ number: Int, roundId: String) -> LiveHoleStateSnapshot {
            LiveHoleStateSnapshot(
                roundId: roundId, hole: number, par: 4, score: 4, putts: 2, penaltyCount: 0,
                fairwayResult: nil, selectedClub: "7I", selectedShotType: "tee",
                selectedStrategyMode: "balanced", distanceToPinM: nil, lie: "tee",
                latitude: nil, longitude: nil, horizontalAccuracyM: nil,
                targetLatitude: nil, targetLongitude: nil, targetKind: nil, updatedAt: nil
            )
        }

        func update(hole: Int, score: Int? = nil) {
            generation += 1
            var holes = state.holes
            let index = holes.firstIndex { $0.hole == hole }!
            holes[index].selectedClub = "club-\(generation)"
            holes[index].updatedAt = "event-\(generation)"
            if let score { holes[index].score = score }
            state = LiveRoundStateSnapshot(roundId: state.roundId, activeHole: 1, holes: holes,
                                           scoredHoles: score == nil ? state.scoredHoles : [hole])
        }

        func refreshCallbacks() {
            let revision = generation
            let probe = probe
            latest.value = LiveHolePageCallbacks.Value(
                package: package, hasLiveRound: true,
                onEvent: { probe.events.append((revision, $0)) },
                onSetActiveHole: { probe.advances.append((revision, $0)) }
            )
        }

        func input(_ number: Int) -> LiveHolePageInput {
            LiveHolePageInput(
                isSelected: selected == number, package: package,
                hole: package.holes.first { $0.number == number }!,
                round: LiveHolePageRoundInput(state, hole: number),
                courseOptions: NineLoopTurn.loopCatalogue(network: [], downloaded: downloadedCourseOptions),
                isPreparingRound: false, isFinishingRound: false, finishErrorMessage: nil,
                isPrepMode: false, prepTeeOptions: [], apiBaseURL: nil, adminToken: nil,
                offlineStore: nil, watchBridge: nil, interactionRevision: interactionRevision
            )
        }
    }

    private struct CountedPage: View {
        let number: Int
        let generation: Int
        let input: LiveHolePageInput
        let state: LiveRoundStateSnapshot
        let probe: Probe
        let event: (LiveRoundEvent) -> Void
        let advance: (Int) -> Void

        var body: some View {
            let _ = countBody()
            Text("\(number):\(generation):\(input.round?.ownHole?.score ?? 0)")
        }

        private func countBody() {
            probe.bodies[number, default: 0] += 1
            probe.callbacks[number] = (event, advance)
            probe.inputs[number] = input
            probe.states[number] = state
        }
    }

    private struct HostedPages: View {
        @ObservedObject var model: Model

        var body: some View {
            let _ = model.refreshCallbacks()
            HStack {
                ForEach([1, 2], id: \.self) { number in
                    let input = model.input(number)
                    let latest = model.latest
                    LiveHolePage(input: input) {
                        CountedPage(number: number, generation: model.generation, input: input, state: model.state,
                                    probe: model.probe, event: latest.onEvent,
                                    advance: { next in
                                        latest.advance(
                                            from: number, to: next,
                                            navigationLock: Binding(get: { model.navigationLock },
                                                                    set: { model.navigationLock = $0 })
                                        ) { value, target in value.onSetActiveHole(target) }
                                    })
                    }.equatable()
                }
            }
        }
    }

    private func settle(_ host: UIViewController) {
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.05))
    }

    private func withHost(_ exercise: (Model, UIViewController) throws -> Void) throws {
        let model = try Model()
        let host = UIHostingController(rootView: HostedPages(model: model))
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 390, height: 844))
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer { window.isHidden = true; window.rootViewController = nil }
        settle(host)
        XCTAssertGreaterThan(model.probe.bodies[1, default: 0], 0)
        XCTAssertGreaterThan(model.probe.bodies[2, default: 0], 0)
        try exercise(model, host)
    }

    func test_j5_10_twenty_current_hole_events_skip_adjacent_bodies_but_adjacent_edit_updates_once() throws {
        try withHost { model, host in
            let baseline = model.probe.bodies
            for _ in 0..<20 {
                model.update(hole: 1)
                settle(host)
            }
            // Handwritten contract: selected N=20, adjacent 0; adjacent edit adds exactly 1.
            XCTAssertEqual(model.probe.bodies[1, default: 0] - baseline[1, default: 0], 20)
            XCTAssertEqual(model.probe.bodies[2, default: 0] - baseline[2, default: 0], 0)
            let beforeEdit = model.probe.bodies[2, default: 0]
            model.update(hole: 2, score: 5)
            settle(host)
            XCTAssertEqual(model.probe.bodies[2, default: 0] - beforeEdit, 1)
        }
    }

    func test_j5_10_frozen_page_callbacks_use_latest_event_and_navigation_state() throws {
        try withHost { model, host in
            let callbacks = try XCTUnwrap(model.probe.callbacks[2])
            for _ in 0..<20 { model.update(hole: 1); settle(host) }
            let event = LiveRoundEventBuilder(roundId: model.state.roundId)
                .makeScoreEvent(hole: 2, strokes: 5)
            callbacks.event(event)
            // This was hole 1 when the adjacent callback was created; the live binding now
            // permits hole 2 -> 3. A captured old lock would reject this navigation entirely.
            model.navigationLock = LiveHoleNavigationLock(currentHole: 2)
            callbacks.advance(3)
            XCTAssertEqual(model.probe.events.last?.0, 20)
            XCTAssertEqual(model.probe.events.last?.1, event)
            XCTAssertEqual(model.probe.advances.last?.0, 20)
            XCTAssertEqual(model.probe.advances.last?.1, 3)
            XCTAssertEqual(model.navigationLock?.currentHole, 3)
        }
    }

    func test_j5_10_selecting_an_adjacent_page_rebuilds_it_immediately_with_latest_inputs() throws {
        try withHost { model, host in
            for _ in 0..<20 { model.update(hole: 1); settle(host) }
            let baseline = model.probe.bodies[2, default: 0]
            model.selected = 2
            settle(host)
            XCTAssertEqual(model.probe.bodies[2, default: 0] - baseline, 1)
            XCTAssertEqual(model.probe.inputs[2]?.round?.ownHole?.selectedClub, "7I")
            XCTAssertEqual(model.probe.inputs[2]?.round?.scores, model.input(2).round?.scores)
            XCTAssertEqual(model.probe.inputs[2]?.isSelected, true)
            XCTAssertEqual(model.probe.states[2]?.holeState(for: 1)?.selectedClub, "club-20",
                           "selection must consume the latest full state, including previously ignored fields")
            model.update(hole: 1)
            settle(host)
            XCTAssertEqual(model.probe.bodies[2, default: 0] - baseline, 2,
                           "the selected page consumes even an unrelated event")
        }
    }

    func test_j5_10_round_score_edits_update_the_chip_and_card_on_an_adjacent_page() throws {
        try withHost { model, host in
            let baseline = model.probe.bodies[2, default: 0]
            model.update(hole: 1, score: 5)
            settle(host)
            XCTAssertEqual(model.probe.bodies[2, default: 0] - baseline, 1,
                           "the global score chip/card must not freeze with unrelated club/GPS fields")
            XCTAssertEqual(model.probe.inputs[2]?.round?.scores.first?.score, 5)
        }
    }

    func test_j5_10_installed_loop_catalogue_change_reaches_the_adjacent_page() throws {
        try withHost { model, host in
            let baseline = model.probe.bodies[2, default: 0]
            model.downloadedCourseOptions = [ProductInputs.course(82001, venue: "Example")]
            settle(host)
            XCTAssertEqual(model.probe.bodies[2, default: 0] - baseline, 1)
            XCTAssertEqual(model.probe.inputs[2]?.courseOptions.map(\.globalId), [82001],
                           "an empty network catalogue must still deliver the installed loop")
        }
    }

    func test_j5_10_adjacent_restorable_fields_update_without_a_score_change() throws {
        try withHost { model, host in
            let baseline = model.probe.bodies[2, default: 0]
            model.update(hole: 2)
            settle(host)
            XCTAssertEqual(model.probe.bodies[2, default: 0] - baseline, 1)
            XCTAssertEqual(model.probe.inputs[2]?.round?.ownHole?.selectedClub, "club-1")
        }
    }

    func test_j5_10_drag_begin_refreshes_frozen_adjacent_once_without_event_churn() throws {
        try withHost { model, host in
            let baseline = model.probe.bodies[2, default: 0]
            for _ in 0..<20 { model.update(hole: 1); settle(host) }
            XCTAssertEqual(model.probe.bodies[2, default: 0] - baseline, 0)

            // J5.10: decoding a prefetched image does not publish to a nonselected page.
            // Each new drag must request one body so it can read the now-ready image cache.
            model.interactionRevision += 1
            settle(host)
            XCTAssertEqual(model.probe.bodies[2, default: 0] - baseline, 1)

            for _ in 0..<20 { model.update(hole: 1); settle(host) }
            XCTAssertEqual(model.probe.bodies[2, default: 0] - baseline, 1,
                           "an unchanged interaction signal must still skip unrelated events")
            model.interactionRevision += 1
            settle(host)
            XCTAssertEqual(model.probe.bodies[2, default: 0] - baseline, 2,
                           "a later drag also refreshes the adjacent page before selection")
        }
    }
}
