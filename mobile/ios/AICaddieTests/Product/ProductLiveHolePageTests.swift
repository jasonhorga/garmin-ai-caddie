import SwiftUI
import UIKit
import XCTest
@testable import AICaddie

/// J5.10 (page responsiveness and historical score edits): count real hosted SwiftUI bodies,
/// not calls to ==. Twenty current-hole club events must request zero adjacent bodies.
@MainActor
final class ProductLiveHolePageTests: XCTestCase {
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
