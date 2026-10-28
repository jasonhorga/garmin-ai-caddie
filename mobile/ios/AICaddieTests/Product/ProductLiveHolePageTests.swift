import SwiftUI
import UIKit
import XCTest
@testable import AICaddie

/// J5.10 (page responsiveness and historical score edits): count real hosted SwiftUI bodies,
/// not calls to ==. Twenty current-hole club events must request zero adjacent bodies.
@MainActor
final class ProductLiveHolePageTests: XCTestCase {
    #if !SWIFT_PACKAGE
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
                prepPackage: model.prepPackage, onPrepHoleChanged: model.prioritizePrepHole,
                onClosePrep: model.closePrepMode,
                onOpenPrepCourse: { course in
                    guard course.globalId == preparedPackage.course.globalId else { return false }
                    // Inject only the already-loaded course package; route changes and first-stroke
                    // activation still run through the real RHV/model, observed as in the app.
                    model.enterPrepMode(with: preparedPackage, hole: 1)
                    return true
                },
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
