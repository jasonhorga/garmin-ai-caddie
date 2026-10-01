import CoreLocation
import Foundation
import SwiftUI
import AICaddieDomain
#if canImport(UIKit)
import UIKit
#endif

/// Round actions chosen on the scorecard sheet (the live screen's 返回 destination) run after the
/// sheet has closed.
enum LiveScorecardFollowUp: Equatable {
    case finishRound
    case leaveToHome
}

private struct PendingPhoneShot: Identifiable {
    let locationEvent: LiveRoundEvent
    let shotOrder: Int

    var id: String { locationEvent.eventId }
}

/// Shared horizontal-navigation decision for live and review hole maps. Vertical scrolls and short
/// map adjustments are ignored; edit/precision surfaces can disable the transition explicitly.
enum HoleSwipeNavigation {
    static func target(
        current: Int,
        holes: [Int],
        translation: CGSize,
        enabled: Bool = true,
        minimumHorizontalDistance: CGFloat = 64
    ) -> Int? {
        guard enabled,
              let index = holes.firstIndex(of: current),
              abs(translation.width) >= minimumHorizontalDistance,
              abs(translation.width) > abs(translation.height) * 1.25 else { return nil }
        let nextIndex = translation.width < 0 ? index + 1 : index - 1
        guard holes.indices.contains(nextIndex) else { return nil }
        return holes[nextIndex]
    }
}

/// Selection state for the optional live obstacle instrument. A nil current value is meaningful:
/// it is the initial, uncluttered map state rather than an instruction to fall back to row zero.
enum LiveHazardSelectionPolicy {
    static func retainedSelection(current: String?, availableIDs: [String]) -> String? {
        guard let current, availableIDs.contains(current) else { return nil }
        return current
    }
}

/// The live hero has two mutually exclusive drag contracts. Keeping the routing decision pure makes
/// it possible to test the boundary without relying on simulator touch timing: a fitted map pages
/// holes, while a zoomed map always pans in place.
enum HeroMapGesturePolicy {
    static func isZoomed(scale: CGFloat, pinchScale: CGFloat = 1) -> Bool {
        scale * pinchScale > 1.01
    }

    static func acceptsHoleSwipe(scale: CGFloat, pinchScale: CGFloat = 1) -> Bool {
        !isZoomed(scale: scale, pinchScale: pinchScale)
    }
}

enum LiveHoleAdvanceResolution: Equatable {
    case advance(to: Int)
    case finish

    static func resolve(after acceptedHole: Int, package: LiveRoundPackage) -> Self {
        let ordered = package.holes.map(\.number)
        if let index = ordered.firstIndex(of: acceptedHole), ordered.indices.contains(index + 1) {
            return .advance(to: ordered[index + 1])
        }
        return .finish
    }
}

public struct CurrentHoleView: View {
    @Environment(\.dismiss) private var dismiss

    public let package: LiveRoundPackage
    public let hole: Hole
    public let onEvent: (LiveRoundEvent) -> Void
    private let onRetainReadyHolePrep: (String, Int, CoursePrepHole) -> Void
    private let requestBuilder = CaddieDecisionRequestBuilder()
    private let offlineDecisionEvaluator = OfflineCaddieDecisionEvaluator()
    private let caddieClient: CaddieDecisionClient?
    private let mediaUploadClient: MediaUploadClient?
    private let caddieBaseURL: URL?
    private let adminToken: String?
    private let offlineStore: OfflineStore?
    private let watchBridge: WatchEventBridge?
    private let liveRoundState: LiveRoundStateSnapshot?
    // 球局调整(加打 / 减九洞 / 结束本场)— round-11: 从首页 Hub 移进开球后的实战屏(用户反馈:
    // 这些该在球局里、不放首页)。控件与闭包原样保留,仅换了容身的屏。
    private let courseOptions: [MobileCourseOption]
    private let isPreparingRound: Bool
    private let pendingEventCount: Int
    private let isFinishingRound: Bool
    private let finishErrorMessage: String?
    /// B4b-2 second loop: set / change (entry) or drop (nil) it before its first hole is played.
    private let onSetSecondLoop: (RoundLoopEntry?, String) -> Void
    /// The turn: add the second loop and open its first hole (the model navigates).
    private let onContinueIntoSecondLoop: (RoundLoopEntry, String) -> Void
    private let onFinishRound: () async -> Bool
    private let onDiscardRound: () -> Void
    private let onAdvanceHole: (Int) -> Void
    private let onLiveHoleInitialLoadDidFinish: () -> Void

    @StateObject private var locationProvider = LocationProvider()
    @State private var score: Int
    @State private var puttCount: Int = 2
    @State private var penaltyCount: Int = 0
    @State private var selectedClub: String
    @State private var hasUserSelectedClub = false
    @State private var selectedShotType: String
    /// Persisted round state still carries the legacy strategy field for event compatibility. Keep
    /// the player's one-shot override separate so the default value can never force the backend to
    /// return a stock option when its own per-club model selected another route.
    @State private var selectedStrategyMode: String = "stock"
    /// Non-nil only after the player explicitly taps an alternative in the caddie detail. Automatic
    /// requests leave this nil and therefore consume the backend/seed selectedOptionId.
    @State private var requestedStrategyMode: String? = nil
    @State private var holePrep: CoursePrepHole?
    @State private var distanceToPinText: String = ""
    @State private var selectedLie: String = "fairway"
    @State private var currentCoordinate: CLLocationCoordinate2D?
    /// A manually chosen Touch Target point.  This is intentionally separate from the movable
    /// green flag below: S70's Touch Target and View Green are two different instruments.
    @State private var targetCoordinate: CLLocationCoordinate2D?
    /// Overlay pixel for a Touch Target.  Unlike the optional coordinate, this remains usable when
    /// a searched course has a map but no geo projection anchors or GPS fix yet.
    @State private var targetPixel: CGPoint?
    /// The per-round flag position edited on the View Green surface.  `nil` means use the factual
    /// provider/geometry pin carried by `mapPinCoordinate`.
    @State private var greenPinCoordinate: CLLocationCoordinate2D?
    /// Full-hole topo pixel for a manually moved flag. This remains usable when the map has no
    /// affine geo anchors; it is session-local and never becomes a GPS/event coordinate by itself.
    @State private var greenPinPixel: CGPoint?
    @State private var targetKind: String?
    /// The legacy wire contract has one target tuple.  Keep track of which instrument was edited
    /// last so a Watch/old server receives the tuple the golfer is looking at, without making the
    /// two on-screen coordinates share storage again.
    @State private var lastTargetEditKind: String?
    @State private var currentHorizontalAccuracyM: Double?
    @State private var note: String = ""
    @State private var caddieDecision: CaddieDecisionResponse?
    /// Per-hole route authority. The live response, installed CoursePrep row, and offline seed can
    /// arrive in different orders; retaining the resolved chain here makes refresh idempotent and
    /// keeps the map, card, and Watch on one route.
    @State private var caddieRoutesByHole: [Int: [CaddiePlanSequence]] = [:]
    @State private var selectedCaddieRouteByHole: [Int: String] = [:]
    /// The first deterministic route is retained by physical facts, not by a server id/label. A
    /// deferred network response may arrive several times with different labels or role metadata;
    /// it must not make the visible route jump between unrelated chains. A later installed
    /// CoursePrep route may upgrade a sparse fallback once.
    @State private var retainedCaddieRouteByHole: [Int: CaddiePlanSequence] = [:]
    @State private var explicitlySelectedCaddieRouteHoles: Set<Int> = []
    @State private var isLoadingCaddieDecision = false
    @State private var caddieRequestGeneration = 0
    @State private var caddieErrorMessage: String?
    @State private var visionFindings: [[String: JSONValue]] = []
    @State private var lastAppliedRestoredHoleState: LiveHoleStateSnapshot?
    @State private var showManage = false
    @State private var showRoundSummary = false
    /// B4 turn: after the last hole of a single first loop, ask which nine comes next.
    @State private var turnPlan: NineLoopPlan?
    /// A turn continuation is in flight. The sheet stays up (spinner, disabled) until the model
    /// replaces the package — which rebuilds this destination for the new hole set — so a failed
    /// or offline preparation leaves the choice on screen with a retry message.
    @State private var turnContinuationPending = false
    @State private var turnContinuationFailed = false
    @State private var showDiscardConfirmation = false
    /// B1c Touch Target on the main map: screen point of the finger while the target is dragged
    /// (drives the loupe), whether that drag owns the gesture, and a one-runloop tap suppressor.
    @State private var heroTargetDragLocation: CGPoint?
    @State private var heroTargetDragging = false
    @State private var heroTargetDidDrag = false
    @State private var showGreenDetail = false
    @State private var selectedHazardID: String?
    @State private var scoreDraft: LiveScoreDraft?
    @State private var showScorecard = false
    @State private var gpsHoleCandidate: LiveHoleGPSCandidate?
    @State private var pendingHistoricalScoreHole: Int?
    /// What to do after the scorecard sheet (the 返回 destination) closes: its round actions need the
    /// sheet gone before presenting the summary or leaving the live round.
    @State private var pendingScorecardAction: LiveScorecardFollowUp?
    @State private var pendingPhoneShot: PendingPhoneShot?
    @State private var heroMapScale: CGFloat = 1
    @State private var heroMapOffset: CGSize = .zero
    /// Direct-manipulation offset is ordinary state, matching the Touch Target detail surface.
    /// GestureState can be coalesced behind the ancestor ScrollView and make the bitmap catch up
    /// only on finger-up on some iOS releases.
    @State private var heroMapTransientDragOffset: CGSize = .zero
    @GestureState private var heroMapPinchScale: CGFloat = 1
    @State private var preciseMapTimedOut = false
    /// Highlighted leg from the complete caddie sequence.  The map keeps all legs visible; this
    /// only changes the emphasized landing after a player taps a step in the detail sheet.
    @State private var selectedPlanIndex: Int?
    @AppStorage("liveTeeDistanceArcYards") private var teeDistanceArcYards: Int = 220
    /// Design snapshots only (see `init(package:hole:snapshotState:)`); nil in the app.
    private var snapshotState: SnapshotState?

    private static let holeRootScrollAnchor = "live-hole-root"
    /// The capture implementation remains available, but this evidence card is intentionally absent
    /// from live play until it has a product-worthy entry point.
    static let showsMediaCaptureCard = false

    public init(
        package: LiveRoundPackage,
        hole: Hole,
        caddieBaseURL: URL? = nil,
        adminToken: String? = nil,
        caddieClient: CaddieDecisionClient? = nil,
        offlineStore: OfflineStore? = nil,
        watchBridge: WatchEventBridge? = nil,
        liveRoundState: LiveRoundStateSnapshot? = nil,
        courseOptions: [MobileCourseOption] = [],
        isPreparingRound: Bool = false,
        pendingEventCount: Int = 0,
        isFinishingRound: Bool = false,
        finishErrorMessage: String? = nil,
        onSetSecondLoop: @escaping (RoundLoopEntry?, String) -> Void = { _, _ in },
        onContinueIntoSecondLoop: @escaping (RoundLoopEntry, String) -> Void = { _, _ in },
        onFinishRound: @escaping () async -> Bool = { false },
        onDiscardRound: @escaping () -> Void = {},
        onAdvanceHole: @escaping (Int) -> Void = { _ in },
        onLiveHoleInitialLoadDidFinish: @escaping () -> Void = {},
        onRetainReadyHolePrep: @escaping (String, Int, CoursePrepHole) -> Void = { _, _, _ in },
        onEvent: @escaping (LiveRoundEvent) -> Void = { _ in }
    ) {
        self.package = package
        self.hole = hole
        self.onEvent = onEvent
        self.caddieClient = caddieClient ?? caddieBaseURL.map { CaddieDecisionClient(baseURL: $0, adminToken: adminToken) }
        self.mediaUploadClient = caddieBaseURL.map { MediaUploadClient(baseURL: $0, adminToken: adminToken) }
        self.caddieBaseURL = caddieBaseURL
        self.adminToken = adminToken
        self.offlineStore = offlineStore
        self.watchBridge = watchBridge
        self.liveRoundState = liveRoundState
        self.courseOptions = courseOptions
        self.isPreparingRound = isPreparingRound
        self.pendingEventCount = pendingEventCount
        self.isFinishingRound = isFinishingRound
        self.finishErrorMessage = finishErrorMessage
        self.onSetSecondLoop = onSetSecondLoop
        self.onContinueIntoSecondLoop = onContinueIntoSecondLoop
        self.onFinishRound = onFinishRound
        self.onDiscardRound = onDiscardRound
        self.onAdvanceHole = onAdvanceHole
        self.onLiveHoleInitialLoadDidFinish = onLiveHoleInitialLoadDidFinish
        self.onRetainReadyHolePrep = onRetainReadyHolePrep
        let seed = package.caddieContextSeeds.first { $0.hole == hole.number }
        let restoredHoleState = liveRoundState?.holeState(for: hole.number)
        let restoredTarget = Self.restoredTarget(from: restoredHoleState)
        let restoredManualTarget = restoredTarget?.kind == "pin" ? nil : restoredTarget
        let restoredGreenPin = restoredTarget?.kind == "pin" ? restoredTarget?.coordinate : nil
        self._score = State(initialValue: restoredHoleState?.score ?? hole.par)
        self._puttCount = State(initialValue: restoredHoleState?.putts ?? 2)
        self._penaltyCount = State(initialValue: restoredHoleState?.penaltyCount ?? 0)
        let restoredClub = restoredHoleState.map { Self.normalizedSelectedClub($0.selectedClub) } ?? ""
        self._selectedClub = State(initialValue: restoredClub)
        self._hasUserSelectedClub = State(initialValue: !restoredClub.isEmpty)
        // A fresh hole starts from the tee even when an older seed happens to list approach first.
        // The recorded event log remains authoritative for resumed holes.
        let initialShotType = restoredHoleState?.selectedShotType
            ?? seed?.shotTypes.first(where: { $0.caseInsensitiveCompare("tee") == .orderedSame })
            ?? "tee"
        self._selectedShotType = State(initialValue: initialShotType)
        self._selectedStrategyMode = State(initialValue: restoredHoleState?.selectedStrategyMode ?? "stock")
        self._distanceToPinText = State(initialValue: Self.validDistanceText(restoredHoleState?.distanceToPinM))
        self._selectedLie = State(initialValue: restoredHoleState?.lie ?? "fairway")
        self._holePrep = State(
            initialValue: package.coursePrep?.holes.first { $0.hole == hole.number }
        )
        self._currentHorizontalAccuracyM = State(initialValue: restoredHoleState?.horizontalAccuracyM)
        self._lastAppliedRestoredHoleState = State(initialValue: restoredHoleState)
        self._gpsHoleCandidate = State(initialValue: nil)
        self._scoreDraft = State(
            initialValue: offlineStore.flatMap { try? $0.loadLiveScoreDraft(roundId: package.roundId) }
        )
        if let latitude = restoredHoleState?.latitude, let longitude = restoredHoleState?.longitude {
            self._currentCoordinate = State(initialValue: CLLocationCoordinate2D(latitude: latitude, longitude: longitude))
        } else {
            self._currentCoordinate = State(initialValue: nil)
        }
        if let restoredManualTarget {
            self._targetCoordinate = State(initialValue: restoredManualTarget.coordinate)
        } else {
            self._targetCoordinate = State(initialValue: nil)
        }
        self._targetPixel = State(initialValue: nil)
        self._greenPinCoordinate = State(initialValue: restoredGreenPin)
        self._greenPinPixel = State(initialValue: nil)
        self._targetKind = State(initialValue: restoredManualTarget?.kind)
        self._lastTargetEditKind = State(initialValue: restoredTarget?.kind)
    }

    /// Deterministic starting state for design snapshots: one selected obstacle, pre-resolved
    /// caddie routes and a zoomed map. Applied after the per-hole reset so the capture is stable.
    struct SnapshotState {
        var selectsFirstHazard = false
        var caddieRoutes: [CaddiePlanSequence] = []
        var selectedRouteIndex = 0
        var mapScale: CGFloat = 1
        /// A placed Touch Target (topo pixels) and, optionally, a held finger showing the loupe.
        var targetPixel: CGPoint?
        var targetDragFocus: CGPoint?
    }

    init(package: LiveRoundPackage, hole: Hole, snapshotState: SnapshotState, caddieBaseURL: URL? = nil) {
        self.init(package: package, hole: hole, caddieBaseURL: caddieBaseURL)
        self.snapshotState = snapshotState
        // Seed the state directly: a headless capture can render before `.task(id:)` runs, so the
        // snapshot must not depend on that task. `applySnapshotState()` re-applies it after the
        // per-hole reset if the task does run first.
        let prep = package.coursePrep?.holes.first { $0.hole == hole.number }
        if snapshotState.selectsFirstHazard, let prep,
           let first = LiveHazardDisplayItem.rows(for: prep, liveReadouts: nil).first {
            _selectedHazardID = State(initialValue: first.id)
        }
        let routes = snapshotState.caddieRoutes
        if let first = routes.first {
            let selected = routes.indices.contains(snapshotState.selectedRouteIndex)
                ? routes[snapshotState.selectedRouteIndex]
                : first
            _caddieRoutesByHole = State(initialValue: [hole.number: routes])
            _retainedCaddieRouteByHole = State(initialValue: [hole.number: first])
            _selectedCaddieRouteByHole = State(
                initialValue: [hole.number: LiveCaddieRouteAuthority.routeSignature(selected)]
            )
            _explicitlySelectedCaddieRouteHoles = State(initialValue: [hole.number])
        }
        _heroMapScale = State(initialValue: min(max(snapshotState.mapScale, 1), 4))
        if let targetPixel = snapshotState.targetPixel {
            _targetPixel = State(initialValue: targetPixel)
            _heroTargetDragLocation = State(initialValue: snapshotState.targetDragFocus)
        }
    }

    @MainActor
    private func applySnapshotState() {
        guard let snapshotState else { return }
        if snapshotState.selectsFirstHazard, let first = liveHazardDisplayRows.first {
            selectedHazardID = first.id
        }
        let routes = snapshotState.caddieRoutes
        if let first = routes.first {
            let selected = routes.indices.contains(snapshotState.selectedRouteIndex)
                ? routes[snapshotState.selectedRouteIndex]
                : first
            caddieRoutesByHole[hole.number] = routes
            retainedCaddieRouteByHole[hole.number] = first
            selectedCaddieRouteByHole[hole.number] = routeKey(selected)
            explicitlySelectedCaddieRouteHoles.insert(hole.number)
        }
        heroMapScale = min(max(snapshotState.mapScale, 1), 4)
        if let targetPixel = snapshotState.targetPixel {
            self.targetPixel = targetPixel
            heroTargetDragLocation = snapshotState.targetDragFocus
        }
    }

    public var body: some View {
        liveHoleContent
        // The app shell is intentionally light, but this approved live-play surface is dark.
        // Request dark system chrome here so the status-bar time, network, and battery stay visible.
        .preferredColorScheme(.dark)
        // The map owns the live surface and supplies a stable navigation-style return row. The
        // inherited NavigationStack label is intentionally hidden because it can expose a stale
        // greeting from the round home rather than the approved live-play hierarchy.
        .toolbar(.hidden, for: .navigationBar)
        .navigationBarBackButtonHidden(true)
        .onAppear {
            #if DEBUG
            UITestEventLatencyTrace.record(
                "live-hole.appear hole=\(hole.number) course=\(package.course.globalId)"
            )
            #endif
            locationProvider.requestAuthorization()
            locationProvider.startUpdatingLocation()
        }
        .onReceive(locationProvider.$latestFix) { latestFix in
            guard let latestFix else {
                return
            }
            currentCoordinate = latestFix.coordinate
            currentHorizontalAccuracyM = latestFix.horizontalAccuracyM
            gpsHoleCandidate = LiveHoleGPSResolver.candidate(
                holes: package.holes,
                coordinate: latestFix.coordinate,
                horizontalAccuracyM: latestFix.horizontalAccuracyM
            )
            // watch P1c: push the live position to the watch so its hole-map 「你」 pans as you walk. Only
            // when the hole map is up (holePrep loaded) — avoids chatter before the round view is ready.
            if holePrep != nil {
                sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
            }
        }
        .task(id: hole.number) {
            // A navigation destination can be retained while the package publishes more prep
            // rows. Rebind the factual row for this display hole before reconciling routes; without
            // this explicit step a reused view can keep the previous hole's route and briefly show
            // no line (or the wrong line) until its on-demand request completes.
            // The adoption policy compares geometry quality, so never feed it the previous
            // hole's row: a ready row for hole 1 must not block a partial-but-correct row for hole 2.
            let currentPrepForHole = holePrep?.hole == hole.number ? holePrep : nil
            if let packagePrep = package.coursePrep?.holes.first(where: { $0.hole == hole.number }) {
                if CoursePrepHoleAdoptionPolicy.shouldAdopt(
                    current: currentPrepForHole,
                    incoming: packagePrep,
                    authoritativeRevision: hole.geometryRevision
                ) {
                    holePrep = packagePrep
                }
            } else if currentPrepForHole == nil {
                holePrep = nil
            }
            // A reused CurrentHoleView must not carry a manual choice into the next hole. The
            // persisted `selectedStrategyMode` remains available for legacy event replay, while
            // this transient override always starts in automatic mode for a new hole.
            requestedStrategyMode = nil
            selectedPlanIndex = nil
            selectedHazardID = nil
            preciseMapTimedOut = false
            heroMapScale = 1
            heroMapOffset = .zero
            heroMapTransientDragOffset = .zero
            // Publish the deterministic package/offline route before the first network frame. A
            // deferred hole therefore never renders a lone club while the map request is pending.
            reconcileCaddieRoutes()
            applySnapshotState()
            #if DEBUG
            // The package already carries factual Tee coordinates for every ready hole. Move the
            // deterministic multi-hole simulator journey before waiting on the per-hole prep GET;
            // otherwise the new hole can appear with shot capture disabled for the whole request.
            moveSimulatedLocationToHoleTeeIfRequested(hole)
            UITestEventLatencyTrace.record(
                "live-hole.load.begin hole=\(hole.number) course=\(package.course.globalId)"
            )
            #endif
            // One ordered bootstrap per hole: first establish the real map/F/M/B context, then make
            // exactly one initial online caddie request from that context. The prior pair of sibling
            // tasks issued a distance-free request and a replacement request concurrently, allowing
            // a cancelled stale request to flash a false "联网不可用" state over the good response.
            await loadCurrentHole()
            #if DEBUG
            UITestEventLatencyTrace.record(
                "live-hole.load.end hole=\(hole.number) course=\(package.course.globalId)"
            )
            #endif
        }
        .onChange(of: liveRoundState) { _, newState in
            applyRestoredStateIfNeeded(newState)
        }
        .onChange(of: package.coursePrep?.holes.first(where: { $0.hole == hole.number })) { _, incoming in
            // Preserve a precise map already retained by the live view when a background refresh
            // still carries lightweight prep; otherwise adopt the new factual prep without
            // restarting the hole task or discarding zoom/flag interaction state.
            guard let incoming else { return }
            let currentPrepForHole = holePrep?.hole == hole.number ? holePrep : nil
            if CoursePrepHoleAdoptionPolicy.shouldAdopt(
                current: currentPrepForHole,
                incoming: incoming,
                authoritativeRevision: hole.geometryRevision
            ) {
                holePrep = incoming
                reconcileCaddieRoutes()
            }
        }
        .onChange(of: liveHazardDisplayRows) { previous, next in
            // A new hole starts with no highlighted obstacle.  Preserve an explicit choice while
            // the package refreshes (a legacy row that became a precise one keeps the selection),
            // but never auto-select the first row just because data arrived.
            selectedHazardID = LiveMapCarryOver.hazardSelection(
                current: selectedHazardID,
                previous: previous,
                next: next
            )
        }
        .onChange(of: holePrep) { previous, next in
            carryOverMapInteraction(from: previous, to: next)
        }
        .fullScreenCover(isPresented: $showGreenDetail) {
            greenDetailSurface
        }
        .sheet(item: $scoreDraft) { presentedDraft in
            scoreConfirmationSurface(for: presentedDraft)
        }
        .sheet(item: $pendingPhoneShot) { pendingShot in
            actualClubPromptSurface(for: pendingShot)
        }
        .sheet(isPresented: $showScorecard, onDismiss: handleScorecardDismissed) {
            scorecardSurface
        }
        .sheet(isPresented: $showRoundSummary) {
            roundSummarySurface
        }
        .sheet(isPresented: Binding(
            get: { turnPlan != nil },
            set: { if !$0 { turnPlan = nil } }
        )) {
            if let turnPlan {
                LiveRoundTurnSheet(
                    plan: turnPlan,
                    isPreparing: isPreparingRound || turnContinuationPending,
                    failureText: turnContinuationFailed ? "没能接上这个 9 洞，请重试" : nil,
                    onContinue: continueIntoSecondLoop,
                    onStop: {
                        self.turnPlan = nil
                        showRoundSummary = true
                    },
                    onLater: { self.turnPlan = nil }
                )
            }
        }
        .onChange(of: isPreparingRound) { wasPreparing, preparing in
            // Still here after the preparation ended: the package did not grow (offline, no
            // installed template, request failed). Keep the sheet and offer a retry.
            guard wasPreparing, !preparing, turnContinuationPending else { return }
            turnContinuationPending = false
            turnContinuationFailed = true
        }
        .confirmationDialog(
            "放弃这场球局？",
            isPresented: $showDiscardConfirmation,
            titleVisibility: .visible
        ) {
            Button("放弃并删除本场记录", role: .destructive) {
                onDiscardRound()
                dismiss()
            }
            Button("继续打球", role: .cancel) {}
        } message: {
            Text("放弃后这一场不会保存，已记的 \(completedHoleStates.count) 洞成绩、落点和待上传媒体会删除。")
        }
    }

    // Keep the large live-play layout in its own opaque view boundary. Besides making the
    // hierarchy easier to read, this prevents SwiftUI's modifier chain in `body` from forcing the
    // compiler to infer every map, panel, and sheet expression as one type-checking problem.
    //
    // B1 (live-play.html): the hole map owns the whole screen. There is no bottom panel and no plan
    // card; the route and landing labels are drawn on the map and every control floats on its edges.
    private var liveHoleContent: some View {
        ZStack {
            LivePlayStyle.base.ignoresSafeArea()
            heroSection
                .ignoresSafeArea()
                .id(Self.holeRootScrollAnchor)
            liveMapChrome
            #if DEBUG
            offlineReadyMarker
            #endif
        }
    }

    private var liveMapChrome: some View {
        ZStack {
            VStack(spacing: 0) {
                HStack(alignment: .top, spacing: 8) {
                    LivePlayTopInfo(
                        holeNumber: hole.courseHoleNumber,
                        par: hole.par,
                        yards: hole.yards,
                        roundLine: liveRoundLine,
                        onBack: { showScorecard = true }
                    )
                    Spacer(minLength: 8)
                    LivePlayGreenLadder(
                        frontYards: liveGreenYards?.front ?? greenYards(liveGreenDistances?.frontM),
                        middleYards: liveGreenYards?.middle ?? greenYards(liveGreenDistances?.middleM),
                        backYards: liveGreenYards?.back ?? greenYards(liveGreenDistances?.backM),
                        flagYards: placedFlagYards,
                        isLive: isGreenRangeLive
                    )
                }
                .padding(.horizontal, 14)
                .padding(.top, 6)
                Spacer(minLength: 0)
            }

            HStack {
                LivePlaySideControls(
                    // 地图降级契约: the obstacle facts the partial map already has are browsable
                    // while the precise topo is pending (outline when known, else the factual
                    // edge points); a selection survives the upgrade (LiveMapCarryOver).
                    hasHazards: !liveHazardDisplayRows.isEmpty,
                    hazardShown: selectedLiveHazard != nil,
                    planPosition: livePlanPosition,
                    showsRecenter: heroMapScale > 1.01,
                    onToggleHazards: toggleHazardDisplay,
                    onNextPlan: selectNextPlan,
                    onRecenter: recenterHeroMap
                )
                Spacer(minLength: 0)
            }
            .padding(.leading, 14)

            VStack(spacing: 0) {
                Spacer(minLength: 0)
                HStack(alignment: .bottom, spacing: 10) {
                    LivePlayScoreButton(action: beginScoreConfirmation)
                    Spacer(minLength: 0)
                    if let selectedLiveHazard,
                       let selectedLiveHazardIndex {
                        LivePlayHazardBar(
                            row: selectedLiveHazard,
                            index: selectedLiveHazardIndex,
                            count: liveHazardDisplayRows.count,
                            onPrevious: { selectHazard(at: selectedLiveHazardIndex - 1) },
                            onNext: { selectHazard(at: selectedLiveHazardIndex + 1) }
                        )
                        .frame(maxWidth: 230)
                        .padding(.bottom, 10)
                        Spacer(minLength: 0)
                    }
                    LivePlayRecordShotButton(
                        enabled: liveCoordinateForCurrentHole != nil,
                        recordedShotCount: recordedNonPuttShotCount,
                        action: recordShotLocation
                    )
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 8)
            }
        }
        .overlay(alignment: .topLeading) { liveCaddieRouteSummary }
        // No accessibility container here: the chrome floats over the whole map, and a `.contain`
        // element with an identifier becomes the front-most accessibility hit target for every
        // point inside its frame. That made the green entry (`live-open-green-from-hero`) and the
        // map itself unreachable for VoiceOver and XCTest even though touches passed through the
        // transparent spacers. The controls stay individual elements.
    }

    /// The selected caddie route is drawn on the map; this invisible element reads it out for
    /// VoiceOver (and lets UI tests prove the structured recommendation arrived).
    @ViewBuilder
    private var liveCaddieRouteSummary: some View {
        if let route = selectedLiveCaddieRoute, !route.steps.isEmpty {
            Color.clear
                .frame(width: 1, height: 1)
                .padding(.top, 120)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(
                    "球童路线：" + route.steps.enumerated()
                        .map { "第 \($0.offset + 1) 杆，\($0.element.summaryText)" }
                        .joined(separator: "；")
                )
                .accessibilityIdentifier("live-caddie-complete-route")
        }
    }

    /// "本场 +2 · 第 3 杆": the round to par and the stroke about to be played on this hole.
    private var liveRoundLine: String {
        "\(roundToParText) · 第 \(recordedNonPuttShotCount + 1) 杆"
    }

    /// "旗 N" appears in the ladder only once the player has placed today's flag.
    private var placedFlagYards: Int? {
        guard greenPinCoordinate != nil || greenPinPixel != nil else { return nil }
        return effectiveDistanceToPinMetres.flatMap { greenYards($0) }
    }

    private var livePlanPosition: (index: Int, count: Int)? {
        let routes = liveCaddieRoutes
        guard !routes.isEmpty else { return nil }
        let selectedKey = selectedLiveCaddieRoute.map { routeKey($0) }
        let index = routes.firstIndex { routeKey($0) == selectedKey } ?? 0
        return (index, routes.count)
    }

    /// 打法 steps through the caddie's routes; the map redraws the selected one.
    private func selectNextPlan() {
        let routes = liveCaddieRoutes
        guard routes.count > 1, let position = livePlanPosition else { return }
        let next = routes[(position.index + 1) % routes.count]
        selectStrategyMode(CaddiePlanPresentation.selectionToken(for: next))
    }

    /// 障碍 shows one obstacle (the first) or hides it again; ‹ › in the bar then steps through them.
    private func toggleHazardDisplay() {
        if selectedLiveHazard != nil {
            selectedHazardID = nil
        } else if !liveHazardDisplayRows.isEmpty {
            selectHazard(at: 0)
        }
    }

    private func recenterHeroMap() {
        withAnimation(.easeOut(duration: 0.18)) {
            heroMapScale = 1
            heroMapOffset = .zero
            heroMapTransientDragOffset = .zero
        }
    }

    private func handleScorecardDismissed() {
        presentPendingHistoricalScoreEdit()
        let followUp = pendingScorecardAction
        pendingScorecardAction = nil
        switch followUp {
        case .finishRound:
            showRoundSummary = true
        case .leaveToHome:
            dismiss()
        case nil:
            break
        }
    }

    #if DEBUG
    @ViewBuilder
    private var offlineReadyMarker: some View {
        if package.hasCompleteOfflineCoursePrep,
           offlineStore?.hasCourseTopoImages(for: package) == true {
            Text("离线地图已准备")
                .font(.system(size: 1))
                .foregroundStyle(Color.white.opacity(0.02))
                .frame(width: 1, height: 1)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("离线地图已准备")
                .accessibilityIdentifier("live-hole-offline-course-ready")
        }
    }
    #endif

    @ViewBuilder
    private var greenDetailSurface: some View {
        if let holePrep, !isPreciseHoleMapPending {
            LiveGreenDetailView(
                hole: holePrep,
                detailURL: greenDetailURL,
                topoURL: liveTopoURL,
                targetCoordinate: $greenPinCoordinate,
                targetPixel: $greenPinPixel,
                referenceCoordinate: mapReferenceCoordinate,
                referenceIsLive: mapReferenceIsLive,
                pinCoordinate: mapPinCoordinate,
                onTargetChanged: { coordinate in
                    handleMapTargetChanged(coordinate, kind: "pin")
                },
                onTargetCommitted: { coordinate in
                    handleMapTargetCommitted(coordinate, kind: "pin")
                },
                onTargetPixelChanged: { pixel in
                    handleMapTargetPixelChanged(pixel, kind: "pin")
                },
                onTargetPixelCommitted: { pixel in
                    handleMapTargetPixelCommitted(pixel, kind: "pin")
                }
            )
        } else {
            ZStack {
                LivePlayStyle.base.ignoresSafeArea()
                ProgressView("精确果岭图准备中…")
                    .tint(.white)
                    .foregroundStyle(.white)
            }
        }
    }

    private func scoreConfirmationSurface(for presentedDraft: LiveScoreDraft) -> some View {
        LiveScoreConfirmationView(
            draft: Binding(
                get: { scoreDraft ?? presentedDraft },
                set: { next in
                    scoreDraft = next
                    if let offlineStore {
                        try? offlineStore.saveLiveScoreDraft(roundId: package.roundId, draft: next)
                    }
                }
            ),
            nextHole: presentedDraft.advanceAfterSave ? nextHole(after: presentedDraft.hole) : nil,
            onAccept: acceptScoreConfirmation,
            onCancel: cancelScoreConfirmation,
            courseHoleNumber: package.courseHoleNumber(forRoundHole:)
        )
    }

    private func actualClubPromptSurface(for pendingShot: PendingPhoneShot) -> some View {
        LiveActualClubPromptView(
            shotNumber: pendingShot.shotOrder,
            choices: actualClubChoices,
            onSelect: { club in recordActualClub(club, for: pendingShot) },
            onSkip: { pendingPhoneShot = nil }
        )
    }

    private var scorecardSurface: some View {
        LiveRoundScorecardView(
            courseName: package.course.venueDisplayName,
            holes: package.holes,
            liveRoundState: liveRoundState,
            recordedScoreHoles: recordedScoreHoles,
            gpsCandidate: gpsHoleCandidate,
            onGoToHole: { selectedHole in
                showScorecard = false
                onAdvanceHole(selectedHole)
            },
            onEdit: { selectedHole in
                pendingHistoricalScoreHole = selectedHole
                showScorecard = false
            },
            onFinishRound: {
                pendingScorecardAction = .finishRound
                showScorecard = false
            },
            onLeaveToHome: {
                pendingScorecardAction = .leaveToHome
                showScorecard = false
            },
            roundAdjustments: AnyView(
                VStack(spacing: 12) {
                    if Self.showsMediaCaptureCard {
                        mediaCard
                    }
                    manageSection
                }
            ),
            loopTitles: LiveScorecardLoops.titles(package: package, catalogue: courseOptions)
        )
    }

    private var roundSummarySurface: some View {
        LiveRoundFinishSummaryView(
            courseName: package.course.venueDisplayName,
            holes: package.holes,
            loopTitles: LiveScorecardLoops.titles(package: package, catalogue: courseOptions),
            scores: completedHoleScores,
            isFinishingRound: isFinishingRound,
            finishErrorMessage: finishErrorMessage,
            onFinish: {
                Task {
                    if await onFinishRound() {
                        showRoundSummary = false
                    }
                }
            },
            onContinue: { showRoundSummary = false },
            onDiscard: {
                showRoundSummary = false
                showDiscardConfirmation = true
            }
        )
    }

    private var caddieContextSeed: CaddieContextSeed? {
        LiveCaddieSeedFactory.resolve(package: package, hole: hole, prep: holePrep)
    }

    /// Apply a strategy tap immediately. The network request that follows refreshes the authoritative
    /// decision, but the first frame already switches both the selected card and the next-club answer.
    private func selectStrategyMode(_ mode: String) {
        let normalized = caddieSelectionToken(forRouteId: mode) ?? mode.lowercased()
        guard !normalized.isEmpty else { return }
        requestedStrategyMode = normalized
        selectedStrategyMode = normalized
        selectedPlanIndex = nil
        hasUserSelectedClub = false
        caddieErrorMessage = nil
        if let route = LiveCaddieRouteAuthority.selected(
            routes: liveCaddieRoutes,
            preferredToken: normalized,
            fallbackToken: nil
        ) {
            selectedCaddieRouteByHole[hole.number] = routeKey(route)
            explicitlySelectedCaddieRouteHoles.insert(hole.number)
        }
        if let decision = caddieDecision,
           let recommendation = LiveClubStripPolicy.recommendation(
               from: decision,
               strategyMode: normalized
           ) {
            selectedClub = recommendation.name
        }
        // Strategy changes are explicit user actions. Trigger the request here instead of observing
        // the persisted field: applying the server's authoritative selection must never launch a
        // second request (and tapping the already-selected route still needs one request).
        Task { await loadCaddieDecision(syncClub: true) }
    }

    // MARK: - 打球屏 v2 hero (map backdrop + header + overlays)

    /// Map-as-backdrop hero: the server-rendered hole image fills the top, with one compact flag,
    /// factual green ranges and small obstacle-edge numbers.
    private var heroSection: some View {
        ZStack(alignment: .top) {
            heroMapVisual
            LivePlayStyle.topScrim
                .frame(height: 176)
                .frame(maxWidth: .infinity, alignment: .top)
                .allowsHitTesting(false)
            heroInteractionLayer
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    /// The course bitmap and GPS marker share one transform. Fixed-size instruments stay in the
    /// viewport plane so zooming cannot turn the distance panel into a giant opaque map blocker.
    private var heroMapVisual: some View {
        GeometryReader { geo in
            ZStack(alignment: .top) {
                ZStack {
                    liveMapBackdrop
                        .padding(.top, LivePlayMapOverlayLayout.liveMapTopInset)
                        .frame(width: geo.size.width, height: geo.size.height)
                        .clipped()
                    if let player = livePlayerTarget(in: geo.size) {
                        LivePlayerPositionMarker()
                            .position(player)
                    }
                }
                .frame(width: geo.size.width, height: geo.size.height)
                .allowsHitTesting(false)
                .scaleEffect(heroDisplayedMapScale)
                .offset(heroDisplayedMapOffset(in: geo.size))

                if let holePrep, let overlay = holePrep.resolvedMapOverlay {
                    let liveMap = liveHoleImageMap(holePrep)
                    let legs = liveMap.plannedLegs()
                    let teeArc = liveMap.teeDistanceArcPixels()
                    let teeArcYards = liveMap.teeDistanceArcYards
                    Canvas { context, size in
                        LivePlannedRouteRenderer.draw(
                            &context,
                            size: size,
                            legs: legs,
                            teeArc: teeArc,
                            teeArcYards: teeArcYards,
                            overlay: overlay,
                            scale: heroDisplayedMapScale,
                            offset: heroDisplayedMapOffset(in: size),
                            topInset: LivePlayMapOverlayLayout.liveMapTopInset,
                            // The selected obstacle is drawn in the same pass so its 前 / 后
                            // labels share one collision layout with the route and tee labels.
                            hazard: selectedLiveHazard.map { (hole: holePrep, row: $0) },
                            target: liveTargetGeometry
                        )
                    }
                    .frame(width: geo.size.width, height: geo.size.height)
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
                }

                // The target itself is drawn by the canvas; this invisible element reads it out
                // (and lets UI tests find it) at its on-screen position.
                if let point = liveTargetScreenPoint(in: geo.size) {
                    Color.clear
                        .frame(width: 30, height: 30)
                        .position(point)
                        .allowsHitTesting(false)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(liveTargetAccessibilityLabel)
                        .accessibilityIdentifier("live-map-target-marker")
                }

                // Holding the target shows the same map magnified around the finger (100 pt,
                // 2.35x, crosshair), exactly as the former Touch Target page did.
                if let focus = heroTargetDragLocation {
                    LiveMapTargetMagnifierLoupe(
                        mapSize: geo.size,
                        focus: focus,
                        displayedScale: heroDisplayedMapScale,
                        displayedOffset: heroDisplayedMapOffset(in: geo.size)
                    ) {
                        liveMapBackdrop
                            .padding(.top, LivePlayMapOverlayLayout.liveMapTopInset)
                            .frame(width: geo.size.width, height: geo.size.height)
                    }
                    .position(LiveMapTargetMagnifierLoupe<EmptyView>.position(for: focus, in: geo.size))
                    .allowsHitTesting(false)
                }

                // A cached topo image is already a usable map.  Do not cover it with the old
                // "hazards later" pill while a background metadata refresh catches up.
                if holePrep == nil {
                    LiveMapPreparingPill()
                        .position(x: geo.size.width * 0.5, y: geo.size.height * 0.88)
                        .allowsHitTesting(false)
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
            .animation(nil, value: heroMapTransientDragOffset)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .clipped()
    }

    private var heroDisplayedMapScale: CGFloat {
        max(1, heroMapScale * heroMapPinchScale)
    }

    private func heroDisplayedMapOffset(in viewport: CGSize) -> CGSize {
        let proposed = CGSize(
            width: heroMapOffset.width + heroMapTransientDragOffset.width,
            height: heroMapOffset.height + heroMapTransientDragOffset.height
        )
        guard let overlay = holePrep?.resolvedMapOverlay,
              let frame = LivePlayMapOverlayLayout.mapFrame(
                  overlayWidth: overlay.w,
                  overlayHeight: overlay.h,
                  in: viewport,
                  topInset: LivePlayMapOverlayLayout.liveMapTopInset
              ) else {
            return proposed
        }
        return LivePlayMapOverlayLayout.clampedOffset(
            proposed,
            mapFrame: frame,
            viewportSize: viewport,
            scale: heroDisplayedMapScale
        )
    }

    /// The map itself owns its interactions: tap the green target for flag placement, tap elsewhere
    /// for Touch Target, and swipe horizontally for the adjacent hole. No explanatory action rows are
    /// needed below the map.
    private var heroInteractionLayer: some View {
        GeometryReader { geometry in
            let greenPath = liveGreenHitPath(in: geometry.size)
            ZStack {
                Color.clear
                    .contentShape(Rectangle())

                if let greenPath {
                    let greenBounds = greenPath.boundingRect
                    let localGreenPath = greenPath.applying(
                        CGAffineTransform(
                            translationX: -greenBounds.minX,
                            y: -greenBounds.minY
                        )
                    )
                    Button {
                        guard !isPreciseHoleMapPending else { return }
                        showGreenDetail = true
                    } label: {
                        Color.white.opacity(0.001)
                            .frame(
                                width: max(greenBounds.width, 1),
                                height: max(greenBounds.height, 1)
                            )
                            .contentShape(localGreenPath)
                    }
                    .buttonStyle(.plain)
                    .frame(
                        width: max(greenBounds.width, 1),
                        height: max(greenBounds.height, 1)
                    )
                    .position(x: greenBounds.midX, y: greenBounds.midY)
                    .accessibilityLabel("调整旗位")
                    .accessibilityIdentifier("live-open-green-from-hero")
                    // Keep the accessibility activation point on the actual green contour.  The
                    // button is already reduced to the contour's local bounding box, so this point
                    // remains deterministic for XCTest and VoiceOver without reopening the whole
                    // map as a green hit target.
                    .accessibilityActivationPoint(
                        CGPoint(
                            x: greenPath.boundingRect.midX,
                            y: greenPath.boundingRect.midY
                        )
                    )
                    .zIndex(1)
                } else if let greenTarget = liveGreenTarget(in: geometry.size) {
                    Button {
                        guard !isPreciseHoleMapPending else { return }
                        showGreenDetail = true
                    } label: {
                        Circle()
                            .fill(Color.white.opacity(0.001))
                            .frame(width: 76, height: 76)
                            .contentShape(Circle())
                    }
                    .buttonStyle(.plain)
                    .position(transformedHeroPoint(greenTarget, in: geometry.size))
                    .accessibilityLabel("调整旗位")
                    .accessibilityIdentifier("live-open-green-from-hero")
                    .zIndex(1)
                }
            }
            // Keep all map gestures in the full hero coordinate space. The old gesture lived on a
            // translated rectangle below the header, which made green-path exclusion depend on
            // SwiftUI's local-coordinate interpretation and allowed an accessibility tap to be lost.
            // B1c: a tap on the map places the Touch Target (a tap on the target clears it); the
            // green keeps its own button above. Holding the target drags it with the loupe.
            .simultaneousGesture(
                SpatialTapGesture().onEnded { value in
                    guard !isPreciseHoleMapPending,
                          !heroTargetDidDrag,
                          value.location.y >= LivePlayMapOverlayLayout.liveMapTopInset,
                          greenPath?.contains(value.location) != true else { return }
                    handleHeroMapTap(at: value.location, in: geometry.size)
                }
            )
            .simultaneousGesture(heroTargetDragGesture(in: geometry.size))
            .simultaneousGesture(heroMapPinchGesture(in: geometry.size))
            // Keep the two drag contracts separate. The paging gesture is active only at the fitted
            // scale, while the map pan is active only after zoom; this prevents a vertical pan from
            // accidentally changing holes and prevents the parent ScrollView from stealing zoomed
            // map movement. Both are simultaneous so ordinary vertical page scrolling remains
            // available when the fitted map is not being paged.
            .simultaneousGesture(heroMapHoleSwipeGesture())
            .simultaneousGesture(heroMapPanGesture(in: geometry.size))
            // Keep the map gesture container and the contour-sized green button as separate
            // accessibility elements. Without an explicit containment boundary SwiftUI promotes
            // this gesture-bearing ZStack to one full-hero button and hides the green entry from
            // VoiceOver/XCTest hit testing.
            .accessibilityElement(children: .contain)
            .accessibilityLabel("球洞地图，点地图设目标点")
            .accessibilityHint("按住目标点拖动微调，左右滑动切换球洞")
            .accessibilityIdentifier("live-open-map-from-hero")
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func heroMapHoleSwipeGesture() -> some Gesture {
        // Once zoomed, make this recognizer inert so it cannot compete with the pan recognizer.
        DragGesture(
            minimumDistance: HeroMapGesturePolicy.isZoomed(scale: heroMapScale)
                ? 10_000
                : 24
        )
            .onEnded { value in
                // A drag that grabbed the Touch Target never pages the hole.
                guard !heroTargetDragging else { return }
                guard HeroMapGesturePolicy.acceptsHoleSwipe(
                    scale: heroMapScale,
                    pinchScale: heroMapPinchScale
                ) else { return }
                guard let target = HoleSwipeNavigation.target(
                    current: hole.number,
                    holes: package.holes.map(\.number),
                    translation: value.translation
                ) else { return }
                #if canImport(UIKit)
                UIImpactFeedbackGenerator(style: .light).impactOccurred()
                #endif
                onAdvanceHole(target)
            }
    }

    private func heroMapPinchGesture(in viewport: CGSize) -> some Gesture {
        MagnificationGesture()
            .updating($heroMapPinchScale) { value, state, _ in
                state = value
            }
            .onEnded { value in
                heroMapScale = min(max(heroMapScale * value, 1), 4)
                heroMapOffset = heroMapClampedOffset(
                    heroMapOffset,
                    scale: heroMapScale,
                    viewport: viewport
                )
            }
    }

    private func heroMapPanGesture(in viewport: CGSize) -> some Gesture {
        DragGesture(
            minimumDistance: HeroMapGesturePolicy.isZoomed(scale: heroMapScale)
                ? 4
                : 10_000
        )
            .onChanged { value in
                guard HeroMapGesturePolicy.isZoomed(
                    scale: heroMapScale,
                    pinchScale: heroMapPinchScale
                ),
                      !heroTargetDragging,
                      !heroTargetHit(at: value.startLocation, in: viewport) else { return }
                heroMapTransientDragOffset = value.translation
            }
            .onEnded { value in
                guard HeroMapGesturePolicy.isZoomed(
                    scale: heroMapScale,
                    pinchScale: heroMapPinchScale
                ),
                      !heroTargetDragging,
                      !heroTargetHit(at: value.startLocation, in: viewport) else {
                    heroMapTransientDragOffset = .zero
                    return
                }
                heroMapOffset = heroMapClampedOffset(
                    CGSize(
                        width: heroMapOffset.width + value.translation.width,
                        height: heroMapOffset.height + value.translation.height
                    ),
                    scale: heroMapScale,
                    viewport: viewport
                )
                heroMapTransientDragOffset = .zero
            }
    }

    // MARK: - Map degradation contract

    /// A background precise map replacing the lightweight one (same hole) keeps the player's
    /// target and flag on the same spot of the hole. A point with a geo coordinate is reprojected
    /// through the new map's anchors; a pixel-only point is moved by route station + lateral offset.
    /// Zoom, pan and the obstacle selection are kept by their own state.
    private func carryOverMapInteraction(from previous: CoursePrepHole?, to next: CoursePrepHole?) {
        guard let previous, let next, previous.hole == next.hole,
              let oldOverlay = previous.resolvedMapOverlay,
              let newOverlay = next.resolvedMapOverlay,
              oldOverlay != newOverlay else { return }
        func carried(pixel: CGPoint?, coordinate: CLLocationCoordinate2D?) -> CGPoint? {
            guard let pixel else { return nil }
            if let reprojected = liveOverlayPixel(for: coordinate) { return reprojected }
            return LiveMapCarryOver.transfer(pixel, from: oldOverlay, to: newOverlay)
        }
        if targetPixel != nil {
            targetPixel = carried(pixel: targetPixel, coordinate: targetCoordinate)
        }
        if greenPinPixel != nil {
            greenPinPixel = carried(pixel: greenPinPixel, coordinate: greenPinCoordinate)
        }
    }

    // MARK: - B1c Touch Target on the main map

    /// Grabbing the target (a press within `LiveTargetRenderer.grabRadius` of its ring) drags it;
    /// the loupe follows the finger. Any other drag keeps its pan / hole-swipe meaning.
    private func heroTargetDragGesture(in viewport: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 4)
            .onChanged { value in
                guard !isPreciseHoleMapPending else { return }
                if !heroTargetDragging {
                    guard heroTargetHit(at: value.startLocation, in: viewport) else { return }
                    heroTargetDragging = true
                }
                heroTargetDidDrag = true
                heroTargetDragLocation = value.location
                if let pixel = heroOverlayPixel(at: value.location, in: viewport, clampToMap: true) {
                    applyHeroTarget(pixel: pixel, committed: false)
                }
            }
            .onEnded { value in
                guard heroTargetDragging else { return }
                if let pixel = heroOverlayPixel(at: value.location, in: viewport, clampToMap: true) {
                    applyHeroTarget(pixel: pixel, committed: true)
                }
                heroTargetDragLocation = nil
                // The tap and hole-swipe recognizers may deliver in this same run loop; keep them
                // suppressed for that delivery so the drag neither re-places the target nor pages.
                DispatchQueue.main.async {
                    heroTargetDragging = false
                    heroTargetDidDrag = false
                }
            }
    }

    private func handleHeroMapTap(at location: CGPoint, in viewport: CGSize) {
        if heroTargetHit(at: location, in: viewport, radius: 24) {
            clearHeroTarget()
        } else if let pixel = heroOverlayPixel(at: location, in: viewport, clampToMap: false) {
            applyHeroTarget(pixel: pixel, committed: true)
        } else {
            return
        }
        #if canImport(UIKit)
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        #endif
    }

    /// Same publication order as the former Touch Target page: resolve the coordinate from the
    /// projection refs first (nil for a pixel-only course), then publish coordinate and pixel, and
    /// commit once when the finger lifts.
    private func applyHeroTarget(pixel: CGPoint, committed: Bool) {
        guard validMapPixel(pixel) != nil else { return }
        let coordinate = liveCoordinate(forOverlayPixel: pixel)
        handleMapTargetChanged(coordinate, kind: "target")
        handleMapTargetPixelChanged(pixel, kind: "target")
        guard committed else { return }
        if let coordinate {
            handleMapTargetCommitted(coordinate, kind: "target")
        }
        handleMapTargetPixelCommitted(pixel, kind: "target")
    }

    private func clearHeroTarget() {
        handleMapTargetChanged(nil, kind: "target")
        handleMapTargetPixelChanged(nil, kind: "target")
        // The coordinate commit owns an explicit clear (one event, one caddie refresh).
        handleMapTargetCommitted(nil, kind: "target")
    }

    private func heroTargetHit(
        at location: CGPoint,
        in viewport: CGSize,
        radius: CGFloat = LiveTargetRenderer.grabRadius
    ) -> Bool {
        guard let point = liveTargetScreenPoint(in: viewport) else { return false }
        return hypot(point.x - location.x, point.y - location.y) <= radius
    }

    /// Screen point -> topo pixel through the inverse pan/zoom and the aspect-fit frame.
    private func heroOverlayPixel(at location: CGPoint, in viewport: CGSize, clampToMap: Bool) -> CGPoint? {
        guard let overlay = holePrep?.resolvedMapOverlay else { return nil }
        let scale = max(heroDisplayedMapScale, 0.001)
        let offset = heroDisplayedMapOffset(in: viewport)
        let base = CGPoint(
            x: (location.x - viewport.width / 2 - offset.width) / scale + viewport.width / 2,
            y: (location.y - viewport.height / 2 - offset.height) / scale + viewport.height / 2
        )
        guard let px = LivePlayMapOverlayLayout.unproject(
            screenPoint: base,
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            from: viewport,
            topInset: LivePlayMapOverlayLayout.liveMapTopInset,
            clampToMap: clampToMap
        ) else { return nil }
        return CGPoint(x: px[0], y: px[1])
    }

    private func liveCoordinate(forOverlayPixel pixel: CGPoint) -> CLLocationCoordinate2D? {
        guard let refs = holePrep?.holeImageProjection?.refs,
              let projected = WatchEventBridge.projectFromTopoPx(
                  px: pixel.x,
                  py: pixel.y,
                  refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
              ) else { return nil }
        return CLLocationCoordinate2D(latitude: projected.latitude, longitude: projected.longitude)
    }

    private func liveOverlayPixel(for coordinate: CLLocationCoordinate2D?) -> CGPoint? {
        guard let coordinate,
              let refs = holePrep?.holeImageProjection?.refs,
              let projected = WatchEventBridge.projectToTopoPx(
                  lat: coordinate.latitude,
                  lon: coordinate.longitude,
                  refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
              ),
              projected.count >= 2 else { return nil }
        return validMapPixel(CGPoint(x: projected[0], y: projected[1]))
    }

    /// The target in topo pixels: the explicit pixel wins; a coordinate is projected only when the
    /// course supplied anchors.
    private var liveTargetOverlayPixel: CGPoint? {
        validMapPixel(targetPixel) ?? liveOverlayPixel(for: targetCoordinate)
    }

    /// Distances start at the Tee anchor (route[0]) until there is a plausible live fix.
    private var liveTargetReferencePixel: CGPoint? {
        let routeStart = holePrep?.resolvedMapOverlay?.route.first.flatMap { row -> CGPoint? in
            row.count >= 2 ? validMapPixel(CGPoint(x: row[0], y: row[1])) : nil
        }
        if !mapReferenceIsLive { return routeStart }
        return liveOverlayPixel(for: mapReferenceCoordinate) ?? routeStart
    }

    private var liveTargetGeometry: LiveTargetGeometry? {
        guard let overlay = holePrep?.resolvedMapOverlay,
              let target = liveTargetOverlayPixel else { return nil }
        let reference = liveTargetReferencePixel
        let pin = effectiveMapPinPixel
        func yards(_ from: CGPoint?, _ to: CGPoint?) -> Int? {
            guard let from, let to, overlay.ppm.isFinite, overlay.ppm > 0 else { return nil }
            let metres = Double(hypot(to.x - from.x, to.y - from.y)) / overlay.ppm
            return CoursePrepRoute.yards(fromMetres: metres)
        }
        return LiveTargetGeometry(
            reference: reference,
            target: target,
            pin: pin,
            toTargetYards: yards(reference, target),
            toPinYards: yards(target, pin)
        )
    }

    private func liveTargetScreenPoint(in viewport: CGSize) -> CGPoint? {
        guard let target = liveTargetOverlayPixel,
              let base = liveMapTarget([Double(target.x), Double(target.y)], in: viewport) else { return nil }
        return transformedHeroPoint(base, in: viewport)
    }

    private var liveTargetAccessibilityLabel: String {
        let geometry = liveTargetGeometry
        let from = mapReferenceIsLive ? "当前位置 → 目标" : "发球台 → 目标"
        var parts = ["目标点"]
        if let yards = geometry?.toTargetYards { parts.append("\(from) \(yards) 码") }
        if let yards = geometry?.toPinYards { parts.append("再 \(yards) 码到旗") }
        return parts.joined(separator: "，")
    }

    private func transformedHeroPoint(_ point: CGPoint, in viewport: CGSize) -> CGPoint {
        let scale = heroDisplayedMapScale
        let center = CGPoint(x: viewport.width / 2, y: viewport.height / 2)
        let offset = heroDisplayedMapOffset(in: viewport)
        return CGPoint(
            x: center.x + (point.x - center.x) * scale + offset.width,
            y: center.y + (point.y - center.y) * scale + offset.height
        )
    }

    private func heroMapClampedOffset(_ proposed: CGSize, scale: CGFloat, viewport: CGSize) -> CGSize {
        guard let overlay = holePrep?.resolvedMapOverlay,
              let frame = LivePlayMapOverlayLayout.mapFrame(
                  overlayWidth: overlay.w,
                  overlayHeight: overlay.h,
                  in: viewport,
                  topInset: LivePlayMapOverlayLayout.liveMapTopInset
              ) else {
            return proposed
        }
        return LivePlayMapOverlayLayout.clampedOffset(
            proposed,
            mapFrame: frame,
            viewportSize: viewport,
            scale: scale
        )
    }

    /// 球洞俯视图(2D):服务端渲染的真实球场图 + 推荐打法叠加。无图时回退暗色渐变占位。
    @ViewBuilder private var liveMapBackdrop: some View {
        if let holePrep,
           LiveMapDisplayState.resolve(prep: holePrep, pending: isPreciseHoleMapPending) != .waiting {
            liveHoleImageMap(holePrep)
                .accessibilityElement(children: .contain)
                    .accessibilityIdentifier(
                        holePrep.geometryCoverage.caseInsensitiveCompare("partial") == .orderedSame
                            ? "live-hole-map-partial"
                            : "live-hole-map-\(holePrep.geometryCoverage.lowercased())"
                    )
        } else {
            // A loading surface is warranted only when there is no route projection to draw yet.
            // `isPreciseHoleMapPending` must never hide an already usable lightweight map. It is the
            // same full-screen waiting page as 备战 (地图降级契约): hole · Par · yards.
            LiveMapPreparingSurface(holeNumber: hole.courseHoleNumber, par: hole.par, yards: hole.yards)
        }
    }

    /// One configured map for both the bitmap layer and the viewport-plane route layer, so the
    /// labelled legs are exactly the ones the bitmap would have drawn.
    private func liveHoleImageMap(_ holePrep: CoursePrepHole) -> HoleImageMapView {
            HoleImageMapView(hole: holePrep, selectedClub: selectedClub, selectedClubMetres: selectedClubMetres,
                             pinOverlayPixel: effectiveMapPinPixel,
                             topoURL: liveTopoURL, showsCardChrome: false,
                             // CourseView already supplies a factual route and pixel projection.
                             // Draw that lightweight map immediately while precise topo/hazard
                             // assets continue in the background; the selected caddie sequence
                             // replaces the restrained centreline as soon as it is available.
                             showsRecommendedRoute: true,
                             // The selected obstacle is rendered once by the viewport-plane
                             // `LiveHazardOverlayRenderer` below. Keep HoleImageMapView's legacy
                             // partial spans off so an unselected obstacle can never leak through.
                             showsHazards: false,
                             showsPrepClubLabel: false,
                             showsClubLabel: false,
                             teeDistanceArcYards: showsTeeDistanceArc ? teeDistanceArcYards : nil,
                             plannedShots: livePlannedShots,
                             selectedPlanIndex: selectedPlanIndex,
                             // `LivePlannedRouteRenderer` draws the route with its "杆名 码数"
                             // labels in the viewport plane (screen-size type at every zoom).
                             drawsPlannedRouteInMap: false)
    }

    /// The distance reference is useful only before the first full shot of a hole. With no GPS
    /// fix we still treat the opening state as the tee so an offline/new-course start gets the same
    /// S70 cue; once a shot is recorded it disappears even if the player walks back toward the tee.
    private var showsTeeDistanceArc: Bool {
        guard recordedNonPuttShotCount == 0 else { return false }
        guard let current = currentCoordinate else { return true }
        guard let tee = teeAnchorCoordinate else { return false }
        let distance = GeoDistance.haversineMetres(
            current.latitude,
            current.longitude,
            tee.latitude,
            tee.longitude
        )
        return distance.isFinite && distance <= 45
    }

    /// Less-frequent scoring inputs remain here. Map target and flag placement live directly on the
    /// map above, matching the interaction instead of duplicating it as explanatory rows.
    private var moreAdjustCard: some View {
        DisclosureGroup {
            VStack(spacing: 10) {
                HStack(alignment: .firstTextBaseline) {
                    Text("选球杆").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    clubPickerMenu  // round-12: 全杆下拉,默认推荐杆,选完即记
                }
                Picker("打法", selection: $selectedShotType) {
                    ForEach(shotTypeOptions, id: \.self) { Text(zhShotType($0)).tag($0) }
                }
                Picker("球位", selection: $selectedLie) {
                    ForEach(lieOptions, id: \.self) { Text(zhLie($0)).tag($0) }
                }
                TextField("到旗杆距离(码)", text: $distanceToPinText)
                    .keyboardType(.decimalPad)
                Stepper("罚杆 \(penaltyCount)", value: $penaltyCount, in: 0...4)
                TextField("备注", text: $note)
            }
            .padding(.top, 6)
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                Label("更多调整", systemImage: "slider.horizontal.3")
                    .font(.headline)
                Text("球杆 · 打法 · 球位 · 距离 · 罚杆 · 备注")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.85)
            }
        }
        .livePlayAuxiliaryCard()
    }

    /// Media capture (unchanged behavior).
    private var mediaCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("拍照取证").font(.caption).foregroundStyle(.secondary)
            MediaCaptureView(
                roundId: package.roundId,
                hole: hole.number,
                targetId: caddieContextSeed?.sourceRef ?? "\(package.roundId):\(hole.number)",
                offlineStore: offlineStore,
                uploadClient: mediaUploadClient,
                onEvent: onEvent,
                onVisionFindings: { findings in
                    visionFindings = findings
                    Task { await loadCaddieDecision() }
                }
            )
        }
        .livePlayAuxiliaryCard()
    }

    // MARK: - 打球屏 v2 display values (derived, read-only)

    /// 本场 to-par chip: sum of (score − par) over recorded holes; falls back to this hole's delta.
    private var roundToParText: String {
        let delta: Int
        if let holes = liveRoundState?.holes, !holes.isEmpty {
            delta = holes.reduce(0) { $0 + ($1.score - $1.par) }
        } else {
            delta = score - hole.par
        }
        if delta == 0 { return "本场 E" }
        return "本场 \(delta > 0 ? "+\(delta)" : "\(delta)")"
    }

    /// Tee colour label (蓝T/白T/…) from the round's teeBox; nil when unknown.
    private var teeLabelZh: String? {
        let map = [
            "blue": "蓝T", "white": "白T", "red": "红T", "gold": "金T",
            "black": "黑T", "green": "绿T", "yellow": "黄T", "silver": "银T",
        ]
        let tee = package.course.teeBox.lowercased()
        if let label = map[tee] { return label }
        return (tee.isEmpty || tee == "unknown") ? nil : package.course.teeBox
    }

    /// The caddie strip's club chips: the 3 most-relevant clubs + their distance, selected = filled.
    private var caddieClubChips: [LiveCaddieStrip.Club] {
        let bag = caddieClubProfiles
        return clubNames.map { name in
            let sub = LiveClubStripPolicy.distanceMetres(
                for: name,
                profiles: bag,
                recommendation: recommendedClubChoice
            ).map { "\(CoursePrepRoute.yards(fromMetres: $0)) 码" } ?? ""
            return LiveCaddieStrip.Club(name: name, sub: sub, on: name == selectedClub)
        }
    }

    /// One 实打 plays-like line for the caddie strip — only when the per-hole prep carries a real
    /// slope (never fabricated); nil otherwise.
    private var caddiePlaysText: String? {
        guard let playsLike = holePrep?.playsLike, playsLike.available, let deltaYd = playsLike.deltaYd, deltaYd != 0 else {
            return nil
        }
        return "坡度修正 \(deltaYd > 0 ? "+" : "")\(deltaYd) 码 · \(deltaYd > 0 ? "上坡" : "下坡")"
    }

    /// The live panel and map consume one retained, per-hole route closure. A sparse response is
    /// never allowed to replace an already displayed CoursePrep/offline chain during refresh.
    private var liveCaddieRoutes: [CaddiePlanSequence] {
        if let cached = caddieRoutesByHole[hole.number], !cached.isEmpty {
            return cached
        }
        return resolvedCaddieRoutes()
    }

    /// Compute the current raw route candidates without consulting the published per-hole cache.
    /// Reconciliation must always see a newly arrived CoursePrep/online chain; using the display
    /// cache here would make the first sparse response permanently authoritative for this view.
    private func resolvedCaddieRoutes() -> [CaddiePlanSequence] {
        let resolved = LiveCaddieRouteAuthority.resolve(
            installed: installedCaddieRoute,
            online: caddieDecision,
            offline: makeOfflineCaddieDecision(),
            par: hole.par,
            shotType: selectedShotType
        )
        if !resolved.isEmpty || hole.par != 3 || selectedShotType.caseInsensitiveCompare("tee") != .orderedSame {
            return resolved
        }
        // A legacy Par 3 response can carry a valid option card but no `sequences` array. Make the
        // one scoring leg explicit locally so the map cannot degrade to a bare 7I label with no
        // tee-to-pin arc. This is a transport repair only; club choice still comes from the option.
        let response = caddieDecision ?? makeOfflineCaddieDecision()
        let targetM = effectiveDistanceToPinMetres
            ?? holePrep?.resolvedMapOverlay?.ln
            ?? holePrep?.routeLenM
            ?? hole.yards.map { CoursePrepRoute.metres(fromYards: Double($0)) }
            ?? 0
        guard targetM > 0, let response else { return resolved }
        let options = CaddiePlanOption.options(from: response)
            .filter { !$0.clubName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && $0.clubName != "-" }
        return options.prefix(3).enumerated().map { index, option in
            let step = CaddiePlanSequenceStep(
                id: "par3-fallback-\(index)-\(option.clubName)",
                role: "scoring",
                clubName: option.clubName,
                targetCarryM: option.carryM > 0 ? option.carryM : nil,
                expectedRemainingM: 0,
                sampleSize: option.sampleSize,
                confidence: option.confidence,
                sourceRefs: option.sourceRefs,
                routeOffsetM: targetM,
                landingM: targetM,
                planIndex: 0
            )
            return CaddiePlanSequence(
                id: option.id,
                label: option.label,
                expectedRemainingM: 0,
                riskScore: option.riskScore,
                confidence: option.confidence,
                coverageText: option.coverageText,
                sourceRefs: option.sourceRefs,
                steps: [step]
            )
        }
    }

    /// Merge a new response into the per-hole closure. The installed CoursePrep chain may upgrade
    /// a deferred fallback once, but ordinary network refreshes preserve the first selected route.
    @MainActor
    private func reconcileCaddieRoutes() {
        let incoming = resolvedCaddieRoutes()
        // The local evaluator rejected the installed chain (water / OB): it is vetoed from the
        // published, retained and selected routes; a server-validated online route still shows.
        let vetoInstalled = makeOfflineCaddieDecision()?.isLocalNoRoute == true
        guard !incoming.isEmpty || vetoInstalled else { return }
        let existing = (caddieRoutesByHole[hole.number] ?? []).filter {
            LiveCaddieRouteAuthority.isDisplayable($0, par: hole.par, shotType: selectedShotType)
        }

        // Choose the visible first route once (shared pure rule, `LiveCaddieRouteAuthority`).
        guard let reconciled = LiveCaddieRouteAuthority.reconciled(
            incoming: incoming,
            existing: existing,
            installed: installedCaddieRoute,
            retained: retainedCaddieRouteByHole[hole.number],
            explicitSelectionKey: explicitlySelectedCaddieRouteHoles.contains(hole.number)
                ? selectedCaddieRouteByHole[hole.number]
                : nil,
            vetoInstalled: vetoInstalled
        ) else {
            // No safe route remains: drop the retained club, map legs, summary and selection,
            // and a caddie-owned (not manually chosen) selected club with them.
            caddieRoutesByHole[hole.number] = nil
            retainedCaddieRouteByHole[hole.number] = nil
            selectedCaddieRouteByHole[hole.number] = nil
            explicitlySelectedCaddieRouteHoles.remove(hole.number)
            selectedClub = LiveClubStripPolicy.caddieOwnedSelection(
                current: selectedClub, recommendation: nil, userSelected: hasUserSelectedClub, noRoute: true
            )
            return
        }
        let (first, merged) = reconciled
        retainedCaddieRouteByHole[hole.number] = first

        // Keep the retained route at index zero and append only physically distinct alternatives.
        caddieRoutesByHole[hole.number] = merged

        let currentToken = selectedCaddieRouteByHole[hole.number]
        let fallbackToken = caddieDecision?.selectedSequence.flatMap {
            jsonString($0["id"]) ?? jsonString($0["label"])
        } ?? caddieDecision?.selectedOptionId
        let selected = LiveCaddieRouteAuthority.selected(
            routes: merged,
            preferredToken: currentToken,
            fallbackToken: currentToken == nil ? fallbackToken : nil
        ) ?? merged.first
        if let selected {
            selectedCaddieRouteByHole[hole.number] = routeKey(selected)
        }
    }

    private func routeKey(_ route: CaddiePlanSequence) -> String {
        LiveCaddieRouteAuthority.routeSignature(route)
    }

    private func jsonString(_ value: JSONValue?) -> String? {
        guard case .string(let raw) = value else { return nil }
        return raw
    }

    /// A tapped route is transient; after the server resolves it, `requestedStrategyMode` is
    /// cleared. Keep the resolved mode for subsequent refreshes, but do not force the persisted
    /// default (`stock`) onto the very first request before the server has selected anything.
    private var activeStrategyMode: String? {
        requestedStrategyMode ?? (caddieDecision == nil ? nil : selectedStrategyMode)
    }

    private var requestStrategyMode: String? {
        requestedStrategyMode ?? (caddieDecision == nil ? nil : selectedStrategyMode)
    }

    /// A factual front/back green window is a valid GIR destination, never a flag-targeted arc
    /// (the shared rule lives on `LiveCaddieRouteAuthority`).
    private func shouldTargetPin(
        offsetM: Double?,
        role: String,
        shotIndex: Int,
        routeEndM: Double
    ) -> Bool {
        LiveCaddieRouteAuthority.shouldTargetPin(
            offsetM: offsetM,
            role: role,
            shotIndex: shotIndex,
            routeEndM: routeEndM,
            par: hole.par,
            greenDistances: holePrep?.greenDistances
        )
    }

    /// The installed CoursePrep chain as a route (shared with 备战, `LiveCaddieRouteAuthority`).
    private var installedCaddieRoute: CaddiePlanSequence? {
        LiveCaddieRouteAuthority.installedRoute(
            prep: holePrep,
            par: hole.par,
            shotType: selectedShotType,
            fallbackRouteEndM: effectiveDistanceToPinMetres
        )
    }

    private var selectedLiveCaddieRoute: CaddiePlanSequence? {
        let routes = liveCaddieRoutes
        if let token = selectedCaddieRouteByHole[hole.number],
           let selected = routes.first(where: { routeKey($0) == token })
                ?? routes.first(where: { LiveCaddieRouteAuthority.physicalSignature($0) == token }) {
            return selected
        }
        return LiveCaddieRouteAuthority.selected(
            routes: routes,
            preferredToken: activeStrategyMode,
            fallbackToken: caddieDecision?.selectedOptionId
        ) ?? routes.first
    }

    /// All relevant mapped hazards belong to the dedicated obstacle instrument. Keeping this count
    /// derived from the same factory as the detail page prevents a button that opens an empty list.
    private var liveHazardDisplayRows: [LiveHazardDisplayItem] {
        guard let holePrep else { return [] }
        return LiveHazardDisplayItem.rows(for: holePrep, liveReadouts: liveHazardReadouts)
    }

    private var selectedLiveHazardIndex: Int? {
        guard let selectedHazardID else { return nil }
        return liveHazardDisplayRows.firstIndex(where: { $0.id == selectedHazardID })
    }

    private var selectedLiveHazard: LiveHazardDisplayItem? {
        guard let selectedLiveHazardIndex else { return nil }
        return liveHazardDisplayRows[selectedLiveHazardIndex]
    }

    private func selectHazard(at index: Int) {
        guard liveHazardDisplayRows.indices.contains(index) else { return }
        selectedHazardID = liveHazardDisplayRows[index].id
        #if canImport(UIKit)
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        #endif
    }

    /// CourseView's small package is a factual drawing source, but its hazard spans are not a
    /// completeness guarantee.  Keep map/distance play available while prodgeometry downloads,
    /// without presenting that provisional subset as the nearest-hazard or final caddie answer.
    private var isPreciseHoleMapPending: Bool {
        LiveMapDisplayState.isPrecisePending(
            geometryCoverage: holePrep?.geometryCoverage,
            timedOut: preciseMapTimedOut,
            hasBaseURL: caddieBaseURL != nil,
            hasCachedTopo: hasCachedTopoForCurrentHole
        )
    }

    private var hasCachedTopoForCurrentHole: Bool {
        guard let holePrep,
              let offlineStore else { return false }
        let mapGlobalId = hole.sourceGlobalId
        let mapLocalHole = hole.sourceLocalHole
        return offlineStore.loadCourseTopoImageURL(
            globalId: mapGlobalId,
            localHole: mapLocalHole,
            geometryRevision: holePrep.geometryRevision ?? hole.geometryRevision
        ) != nil
    }

    /// 本洞真实地形底图 URL(与 `loadHoleMap` 用同一 source 球场 + 本地洞号:组合局后九在第二个环的
    /// gid)。给 `HoleImageMapView` 当底图;无后端地址/占位球场时为 nil → 回退到 payload flat 渲染图。
    private var liveTopoURL: URL? {
        let mapGlobalId = hole.sourceGlobalId
        let mapLocalHole = hole.sourceLocalHole
        let geometryRevision = holePrep?.geometryRevision ?? hole.geometryRevision
        if let local = offlineStore?.loadCourseTopoImageURL(
            globalId: mapGlobalId,
            localHole: mapLocalHole,
            geometryRevision: geometryRevision
        ) {
            return local
        }
        guard holePrep?.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame else {
            return nil
        }
        #if DEBUG
        if ProcessInfo.processInfo.environment["UITEST_FORCE_LIVE_NETWORK_FAILURE"] == "1" {
            return nil
        }
        #endif
        guard let caddieBaseURL else { return nil }
        return SyncClient.topoImageURL(
            baseURL: caddieBaseURL,
            globalId: mapGlobalId,
            localHole: mapLocalHole,
            geometryRevision: geometryRevision
        )
    }

    private var greenDetailURL: URL? {
        guard let caddieBaseURL,
              let prep = holePrep,
              let outline = prep.greenOutline,
              outline.available,
              let projection = prep.holeImageProjection,
              let width = projection.widthPx,
              let height = projection.heightPx,
              let crop = GreenDetailCrop.around(
                  points: outline.pointsPx,
                  imageWidth: Double(width),
                  imageHeight: Double(height)
              ) else { return nil }
        let mapGlobalId = hole.sourceGlobalId
        let mapLocalHole = hole.sourceLocalHole
        return SyncClient.greenDetailImageURL(
            baseURL: caddieBaseURL,
            globalId: mapGlobalId,
            localHole: mapLocalHole,
            crop: crop,
            geometryRevision: prep.geometryRevision
        )
    }

    /// The route endpoint is the selected green target used by the shared map render. Projecting it
    /// here keeps the live target ring on that real green instead of at one fixed screen coordinate.
    private func liveGreenTarget(in heroSize: CGSize) -> CGPoint? {
        guard let overlay = holePrep?.resolvedMapOverlay else { return nil }
        if let movedPin = greenPinPixel,
           movedPin.x.isFinite,
           movedPin.y.isFinite,
           let point = LivePlayMapOverlayLayout.project(
               overlayPoint: [Double(movedPin.x), Double(movedPin.y)],
               overlayWidth: overlay.w,
               overlayHeight: overlay.h,
               into: heroSize,
               topInset: LivePlayMapOverlayLayout.liveMapTopInset
           ) {
            return point
        }
        if let movedPin = greenPinCoordinate,
           let refs = holePrep?.holeImageProjection?.refs,
           let projected = WatchEventBridge.projectToTopoPx(
               lat: movedPin.latitude,
               lon: movedPin.longitude,
               refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
           ),
           let point = LivePlayMapOverlayLayout.project(
               overlayPoint: projected,
               overlayWidth: overlay.w,
               overlayHeight: overlay.h,
               into: heroSize,
               topInset: LivePlayMapOverlayLayout.liveMapTopInset
           ) {
            return point
        }
        guard let greenTarget = overlay.route.last else { return nil }
        return LivePlayMapOverlayLayout.project(
            overlayPoint: greenTarget,
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            into: heroSize,
            topInset: LivePlayMapOverlayLayout.liveMapTopInset
        )
    }

    /// The green entry follows the factual putting-surface boundary instead of a fixed hit circle
    /// around the pin. The path is projected and transformed with the hero map, so it remains
    /// correct while the player is inspecting a zoomed/panned hole.
    private func liveGreenHitPath(in heroSize: CGSize) -> Path? {
        guard let overlay = holePrep?.resolvedMapOverlay,
              let outline = holePrep?.greenOutline,
              outline.available else { return nil }
        let points = outline.pointsPx.compactMap { row -> CGPoint? in
            guard row.count >= 2,
                  row[0].isFinite,
                  row[1].isFinite,
                  let projected = LivePlayMapOverlayLayout.project(
                      overlayPoint: row,
                      overlayWidth: overlay.w,
                      overlayHeight: overlay.h,
                      into: heroSize,
                      topInset: LivePlayMapOverlayLayout.liveMapTopInset
                  ) else { return nil }
            return transformedHeroPoint(projected, in: heroSize)
        }
        guard points.count >= 3 else { return nil }
        var path = Path()
        path.move(to: points[0])
        for point in points.dropFirst() { path.addLine(to: point) }
        path.closeSubpath()
        return path
    }

    /// Project any topo-pixel fact through exactly the same aspect-fit transform as the bitmap.
    private func liveMapTarget(_ overlayPoint: [Double], in heroSize: CGSize) -> CGPoint? {
        guard let overlay = holePrep?.resolvedMapOverlay else { return nil }
        return LivePlayMapOverlayLayout.project(
            overlayPoint: overlayPoint,
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            into: heroSize,
            topInset: LivePlayMapOverlayLayout.liveMapTopInset
        )
    }

    private func livePlayerTarget(in heroSize: CGSize) -> CGPoint? {
        let displayCoordinate: CLLocationCoordinate2D? = {
            if recordedNonPuttShotCount == 0, showsTeeDistanceArc {
                return teeAnchorCoordinate ?? liveCoordinateForCurrentHole
            }
            return liveCoordinateForCurrentHole
        }()
        guard let currentCoordinate = displayCoordinate,
              let overlay = holePrep?.resolvedMapOverlay,
              let refs = holePrep?.holeImageProjection?.refs,
              refs.count >= 3,
              let point = WatchEventBridge.projectToTopoPx(
                  lat: currentCoordinate.latitude,
                  lon: currentCoordinate.longitude,
                  refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
              ) else { return nil }
        return LivePlayMapOverlayLayout.project(
            overlayPoint: point,
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            into: heroSize,
            topInset: LivePlayMapOverlayLayout.liveMapTopInset
        )
    }

    /// Touch Target uses the live fix when it is plausibly on this hole. Without GPS it falls back
    /// to the factual Tee anchor carried by the package or reconstructed from the map projection;
    /// this is a display/reference coordinate only and is never sent as `currentLocation`.
    private var mapReferenceCoordinate: CLLocationCoordinate2D? {
        // The first-shot map, Touch Target reference and tee-distance arc must share one physical
        // anchor. Snap the opening state to the projected route[0] while the player is at the tee;
        // after a shot, live GPS regains authority and the map follows the player normally.
        if recordedNonPuttShotCount == 0,
           let teeAnchor = teeAnchorCoordinate,
           (currentCoordinate == nil || isWithinTeeAnchor(currentCoordinate, teeAnchor)) {
            return teeAnchor
        }
        if mapReferenceIsLive, let currentCoordinate {
            return currentCoordinate
        }
        return teeAnchorCoordinate
    }

    /// One tee authority for the route, map reference, GPS snap and initial detail marker.
    private var teeAnchorCoordinate: CLLocationCoordinate2D? {
        if let prep = holePrep,
           let first = prep.resolvedMapOverlay?.route.first,
           first.count >= 2,
           let refs = prep.holeImageProjection?.refs,
           let projected = WatchEventBridge.projectFromTopoPx(
               px: first[0],
               py: first[1],
               refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
           ) {
            return CLLocationCoordinate2D(latitude: projected.latitude, longitude: projected.longitude)
        }
        guard let latitude = hole.teeLatitude,
              let longitude = hole.teeLongitude,
              latitude.isFinite,
              longitude.isFinite,
              (-90...90).contains(latitude),
              (-180...180).contains(longitude) else { return nil }
        return CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }

    private func isWithinTeeAnchor(
        _ coordinate: CLLocationCoordinate2D?,
        _ tee: CLLocationCoordinate2D
    ) -> Bool {
        guard let coordinate else { return true }
        let distance = GeoDistance.haversineMetres(
            coordinate.latitude,
            coordinate.longitude,
            tee.latitude,
            tee.longitude
        )
        return distance.isFinite && distance <= 45
    }

    private var mapReferenceIsLive: Bool {
        hasPlausibleLiveFix
    }

    private var hasPlausibleLiveFix: Bool {
        guard let fix = locationProvider.latestFix else { return false }
        if gpsHoleCandidate?.hole == hole.number { return true }
        guard let green = liveGreenDistances,
              let latitude = green.middleLat,
              let longitude = green.middleLon else { return false }
        let metres = GeoDistance.haversineMetres(
            fix.coordinate.latitude,
            fix.coordinate.longitude,
            latitude,
            longitude
        )
        return metres.isFinite && metres <= GeoDistance.maximumUsefulGreenMetres
    }

    private var mapPinCoordinate: CLLocationCoordinate2D? {
        if let prep = holePrep,
           let last = prep.resolvedMapOverlay?.route.last,
           last.count >= 2,
           let refs = prep.holeImageProjection?.refs,
           let projected = WatchEventBridge.projectFromTopoPx(
               px: last[0],
               py: last[1],
               refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
           ) {
            return CLLocationCoordinate2D(latitude: projected.latitude, longitude: projected.longitude)
        }
        if let green = liveGreenDistances,
           let latitude = green.middleLat,
           let longitude = green.middleLon {
            return CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
        }
        return nil
    }

    /// The pin shown by the map surfaces. A manually moved flag wins over the provider's factual
    /// route endpoint, while the latter remains the fallback for untouched holes.
    private var effectiveMapPinCoordinate: CLLocationCoordinate2D? {
        greenPinCoordinate ?? mapPinCoordinate
    }

    private var effectiveMapPinPixel: CGPoint? {
        if let moved = validMapPixel(greenPinPixel) {
            return moved
        }
        if let moved = greenPinCoordinate,
           let refs = holePrep?.holeImageProjection?.refs,
           let projected = WatchEventBridge.projectToTopoPx(
               lat: moved.latitude,
               lon: moved.longitude,
               refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
           ), projected.count >= 2,
           let valid = validMapPixel(CGPoint(x: projected[0], y: projected[1])) {
            return valid
        }
        guard let last = holePrep?.resolvedMapOverlay?.route.last,
              last.count >= 2 else { return nil }
        return validMapPixel(CGPoint(x: last[0], y: last[1]))
    }

    /// The legacy Watch/event payload has one coordinate tuple. Until that contract grows a second
    /// tuple, publish the instrument edited most recently. If that instrument is pixel-only (or was
    /// just cleared), fall back to the other coordinate-bearing instrument instead of clearing a
    /// still-visible flag/target. Pixel-only state remains local and is never promoted to WGS84.
    private var wireTargetSelection: (coordinate: CLLocationCoordinate2D, kind: String)? {
        let preferred = Self.normalizedTargetKind(lastTargetEditKind)

        func targetSelection() -> (coordinate: CLLocationCoordinate2D, kind: String)? {
            guard let coordinate = validTargetCoordinate(targetCoordinate) else { return nil }
            let kind = Self.normalizedTargetKind(targetKind)
            return (coordinate, kind == "pin" ? "target" : (kind ?? "target"))
        }

        func pinSelection() -> (coordinate: CLLocationCoordinate2D, kind: String)? {
            guard let coordinate = validTargetCoordinate(greenPinCoordinate) else { return nil }
            return (coordinate, "pin")
        }

        if preferred == "pin", let selection = pinSelection() { return selection }
        if preferred != "pin", let selection = targetSelection() { return selection }
        if let selection = targetSelection() { return selection }
        if let selection = pinSelection() { return selection }
        return nil
    }

    private var wireTargetCoordinate: CLLocationCoordinate2D? {
        wireTargetSelection?.coordinate
    }

    private var wireTargetKind: String? {
        wireTargetSelection?.kind
    }

    private func validTargetCoordinate(
        _ coordinate: CLLocationCoordinate2D?
    ) -> CLLocationCoordinate2D? {
        guard let coordinate,
              coordinate.latitude.isFinite,
              coordinate.longitude.isFinite,
              (-90...90).contains(coordinate.latitude),
              (-180...180).contains(coordinate.longitude) else {
            return nil
        }
        return coordinate
    }

    private func hasTargetState(for kind: String) -> Bool {
        if Self.normalizedTargetKind(kind) == "pin" {
            return greenPinCoordinate != nil || greenPinPixel != nil
        }
        return targetCoordinate != nil || targetPixel != nil
    }

    /// Keep the legacy preference aligned with the remaining local instruments after a clear. The
    /// pixel checks deliberately count as state so a no-projection edit remains the most-recent
    /// instrument locally, while `wireTargetSelection` still falls back to another real coordinate.
    private func refreshLastTargetEditKind(preferred: String?) {
        let preferred = Self.normalizedTargetKind(preferred)
        if preferred == "pin", hasTargetState(for: "pin") {
            lastTargetEditKind = "pin"
            return
        }
        if preferred != "pin", hasTargetState(for: "target") {
            lastTargetEditKind = "target"
            return
        }
        if hasTargetState(for: "target") {
            lastTargetEditKind = "target"
        } else if hasTargetState(for: "pin") {
            lastTargetEditKind = "pin"
        } else {
            lastTargetEditKind = nil
        }
    }

    /// Distance from the current map reference to a manually moved flag. This is deliberately not
    /// the same as `mapTargetDistanceMetres`: a Touch Target is an aim point, while a moved flag is
    /// the hole's endpoint.
    private var greenPinDistanceMetres: Double? {
        if let coordinateDistance = distanceFromMapReference(to: greenPinCoordinate) {
            return coordinateDistance
        }
        return pixelDistanceMetres(from: mapReferencePixel, to: validMapPixel(greenPinPixel))
    }

    private func distanceFromMapReference(to endpoint: CLLocationCoordinate2D?) -> Double? {
        guard let start = mapReferenceCoordinate, let endpoint else { return nil }
        let metres = GeoDistance.haversineMetres(
            start.latitude,
            start.longitude,
            endpoint.latitude,
            endpoint.longitude
        )
        guard metres.isFinite, metres > 0, metres <= GeoDistance.maximumUsefulGreenMetres else {
            return nil
        }
        return metres
    }

    private var mapTargetDistanceMetres: Double? {
        if let coordinateDistance = distanceFromMapReference(to: targetCoordinate) {
            return coordinateDistance
        }
        return pixelDistanceMetres(from: mapReferencePixel, to: validMapPixel(targetPixel))
    }

    /// The shared topo pixel frame is still measurable when a searched/off-course course has no
    /// affine geo anchors. Prefer a projected coordinate when available, then use the factual route
    /// endpoints as the tee/pin references.
    private var mapReferencePixel: CGPoint? {
        guard let overlay = holePrep?.resolvedMapOverlay else { return nil }
        if let reference = mapReferenceCoordinate,
           let refs = holePrep?.holeImageProjection?.refs,
           let projected = WatchEventBridge.projectToTopoPx(
               lat: reference.latitude,
               lon: reference.longitude,
               refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
           ),
           projected.count >= 2,
           projected[0].isFinite,
           projected[1].isFinite {
            return CGPoint(x: projected[0], y: projected[1])
        }
        guard let first = overlay.route.first,
              first.count >= 2,
              first[0].isFinite,
              first[1].isFinite else { return nil }
        return CGPoint(x: first[0], y: first[1])
    }

    private func pixelDistanceMetres(from start: CGPoint?, to end: CGPoint?) -> Double? {
        guard let start,
              let end,
              let ppm = holePrep?.resolvedMapOverlay?.ppm,
              ppm.isFinite,
              ppm > 0,
              start.x.isFinite,
              start.y.isFinite,
              end.x.isFinite,
              end.y.isFinite else { return nil }
        let metres = hypot(Double(end.x - start.x), Double(end.y - start.y)) / ppm
        guard metres.isFinite,
              metres >= 0,
              metres <= GeoDistance.maximumUsefulGreenMetres else { return nil }
        return metres
    }

    private func validMapPixel(_ pixel: CGPoint?) -> CGPoint? {
        guard let pixel,
              pixel.x.isFinite,
              pixel.y.isFinite,
              let overlay = holePrep?.resolvedMapOverlay,
              pixel.x >= 0,
              pixel.y >= 0,
              pixel.x <= CGFloat(overlay.w),
              pixel.y <= CGFloat(overlay.h) else { return nil }
        return pixel
    }

    private var displayedTargetYards: Int? {
        guard targetCoordinate != nil
                || targetPixel != nil
                || greenPinCoordinate != nil
                || greenPinPixel != nil
                || distanceToPinMetres != nil else {
            return nil
        }
        return effectiveDistanceToPinMetres.flatMap { greenYards($0) }
    }

    private func handleMapTargetChanged(_ coordinate: CLLocationCoordinate2D?, kind: String = "target") {
        let normalizedKind = Self.normalizedTargetKind(kind) ?? "target"
        if normalizedKind == "pin" {
            // View Green owns the flag binding. Never let a flag drag replace a Touch Target.
            greenPinCoordinate = coordinate
        } else {
            // Touch Target owns the manual aim point. Keep its kind separate from the flag state.
            targetCoordinate = coordinate
            targetKind = coordinate == nil ? nil : normalizedKind
        }
        if coordinate == nil {
            refreshLastTargetEditKind(preferred: normalizedKind)
        } else {
            lastTargetEditKind = normalizedKind
        }
        // A selected map point is the authoritative target for this request. Clear a previous text
        // override so the map and the caddie never describe different distances.
        if coordinate != nil || normalizedKind == "pin" {
            distanceToPinText = ""
        }
        // This callback runs for every drag frame. Keep the phone map/distance surface live locally;
        // the committed callback sends one complete Watch payload after the finger is released.
    }

    /// Pixel callbacks are deliberately separate from coordinate callbacks. A pixel is enough to
    /// keep the map and local distance instrument live, but it is never promoted to a fake WGS84/GPS
    /// event when projection refs are unavailable.
    private func handleMapTargetPixelChanged(_ pixel: CGPoint?, kind: String = "target") {
        let normalizedKind = Self.normalizedTargetKind(kind) ?? "target"
        if normalizedKind == "pin" {
            greenPinPixel = pixel
        } else {
            targetPixel = pixel
        }
        if let pixel {
            lastTargetEditKind = normalizedKind
            distanceToPinText = ""
        } else if normalizedKind == "pin" {
            greenPinCoordinate = nil
            refreshLastTargetEditKind(preferred: normalizedKind)
        } else {
            targetCoordinate = nil
            targetKind = nil
            refreshLastTargetEditKind(preferred: normalizedKind)
        }
        // Pixel updates also run once per drag frame, so defer cross-device delivery until commit.
    }

    private func handleMapTargetPixelCommitted(_ pixel: CGPoint?, kind: String = "target") {
        if pixel == nil {
            // Explicit clears are persisted by the coordinate commit. There is no second refresh
            // here: both detail surfaces emit coordinate + pixel callbacks for one gesture.
            return
        }

        // If the same gesture also produced a coordinate callback, that callback owns persistence.
        // Pixel-only edits stay session-local; the caddie still gets the new pixel-derived distance.
        let normalizedKind = Self.normalizedTargetKind(kind) ?? "target"
        let coordinate = normalizedKind == "pin" ? greenPinCoordinate : targetCoordinate
        guard coordinate == nil else { return }
        sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
        Task { await loadCaddieDecision(syncClub: !hasUserSelectedClub) }
    }

    private func handleMapTargetCommitted(_ coordinate: CLLocationCoordinate2D?, kind: String = "target") {
        let normalizedKind = Self.normalizedTargetKind(kind) ?? "target"
        // `applyTarget/applyFlag` emits a nil coordinate before its pixel callback when projection
        // anchors are unavailable. That is a pixel-only placement, not an explicit clear; wait for
        // the pixel commit and keep any other coordinate on the legacy wire tuple.
        let pixelOnlyPlacement = coordinate == nil && hasTargetState(for: normalizedKind)
        if !pixelOnlyPlacement {
            if let coordinate = validTargetCoordinate(coordinate) {
                let kind = normalizedKind == "pin"
                    ? "pin"
                    : (Self.normalizedTargetKind(targetKind) ?? normalizedKind)
                persistMapTarget(coordinate: coordinate, kind: kind)
            } else if let fallback = wireTargetSelection {
                // Clearing the most-recent instrument must not clear the other one from the
                // legacy single-tuple Watch/backend contract.
                persistMapTarget(coordinate: fallback.coordinate, kind: fallback.kind)
            } else {
                persistMapTarget(coordinate: nil, kind: "target")
            }
        }
        sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
        if !pixelOnlyPlacement {
            Task { await loadCaddieDecision(syncClub: !hasUserSelectedClub) }
        }
    }

    /// Persist target edits as a lightweight club/state event. It carries no latitude/longitude for
    /// the player, so offline map selection never masquerades as a GPS location event.
    private func persistMapTarget() {
        persistMapTarget(
            coordinate: targetCoordinate,
            kind: targetCoordinate == nil ? "target" : (targetKind ?? "target")
        )
    }

    private func persistMapTarget(coordinate: CLLocationCoordinate2D?, kind: String) {
        let timestamp = ISO8601DateFormatter().string(from: Date())
        let trimmedClub = selectedClub.trimmingCharacters(in: .whitespacesAndNewlines)
        // The club event contract requires a non-empty clubName. A target edit is still meaningful
        // before a club is chosen, so use an explicit compatibility placeholder; restore logic never
        // surfaces this placeholder as the selected club.
        let persistedClub = trimmedClub.isEmpty ? "unknown" : trimmedClub
        let targetDistance: Double? = {
            guard coordinate != nil else { return nil }
            if Self.normalizedTargetKind(kind) == "pin" {
                return distanceFromMapReference(to: coordinate)
            }
            return distanceFromMapReference(to: coordinate)
        }()
        var payload: [String: JSONValue] = [
            "clubName": .string(persistedClub),
            "targetLatitude": coordinate.map { .number($0.latitude) } ?? .null,
            "targetLongitude": coordinate.map { .number($0.longitude) } ?? .null,
            "targetKind": coordinate == nil ? .null : .string(Self.normalizedTargetKind(kind) ?? "target"),
            "distanceToPinM": targetDistance.map(JSONValue.number) ?? .null,
        ]
        payload["shotType"] = .string(selectedShotType)
        payload["strategyMode"] = .string(selectedStrategyMode)
        payload["lie"] = .string(selectedLie)
        emit(kind: .club, timestamp: timestamp, payload: payload)
    }

    @MainActor
    private func loadCurrentHole() async {
        // Sync the selected club to the recommendation on a fresh hole; a hole the player already
        // recorded keeps their actual choice.
        let alreadyRecorded = liveRoundState?.holeState(for: hole.number)?.selectedClub.isEmpty == false
        let syncClub = !alreadyRecorded && !hasUserSelectedClub
        if holePrep != nil {
            // The package already contains the factual route/F-M-B context. Start the refresh in
            // parallel, but let the first caddie response use that context immediately instead of
            // making the player wait for a second prep GET/render request.
            let mapTask = Task { await loadHoleMap() }
            await loadCaddieDecision(syncClub: syncClub)
            _ = await mapTask.value
        } else {
            _ = await loadHoleMap()
            guard !Task.isCancelled else { return }
            await loadCaddieDecision(syncClub: syncClub)
        }
        guard !Task.isCancelled else { return }
        #if DEBUG
        UITestEventLatencyTrace.record(
            "live-hole.initial-load-finished hole=\(hole.number) course=\(package.course.globalId)"
        )
        #endif
        onLiveHoleInitialLoadDidFinish()

        // The package request has already queued prodgeometry in the backend. Keep the CourseView
        // vectors usable now, then replace only this hole's map facts when the precise mesh arrives.
        // The structured `.task(id: hole.number)` owns this loop, so changing holes or leaving the
        // screen cancels it without leaving a detached poller behind.
        if holePrep?.geometryCoverage.caseInsensitiveCompare("partial") == .orderedSame,
           !hasCachedTopoForCurrentHole {
            await waitForPreciseHoleMap(syncClub: !alreadyRecorded)
        }
    }

    private func loadHoleMap() async -> Bool {
        #if DEBUG
        if ProcessInfo.processInfo.environment["UITEST_FORCE_LIVE_NETWORK_FAILURE"] == "1" {
            return false
        }
        #endif
        guard let caddieBaseURL else {
            return false
        }
        // A ready retained package is authoritative only when its hazard records also carry the
        // precise polygons used by the dedicated obstacle page. Older ready packages can have the
        // map/overlay but no `outlinePx`; refresh those once so the UI can obtain the real boundary.
        if let existing = holePrep,
           CoursePrepHoleAdoptionPolicy.isReadyMap(existing),
           existing.hasRenderableHazardOutlines,
           CoursePrepHoleAdoptionPolicy.revisionMatches(
               existing.geometryRevision,
               hole.geometryRevision
           ) {
            return false
        }
        // 每洞用自己的 source 球场 + 本地洞号(组合局后九在第二个环的 gid)。
        let mapGlobalId = hole.sourceGlobalId
        let mapLocalHole = hole.sourceLocalHole
        guard mapGlobalId != 0 else {
            return false
        }
        let client = SyncClient(baseURL: caddieBaseURL, adminToken: adminToken)
        let lightweight: CoursePrepHole
        do {
            guard let fetched = try await client.fetchHolePrep(
                globalId: mapGlobalId,
                localHole: mapLocalHole,
                teeBox: package.course.teeBox
            ) else { return false }
            lightweight = fetched
        } catch {
            // Keep the package's retained prep facts. Returning false prevents the partial-map
            // upgrade loop from polling forever while the player is offline.
            return false
        }
        // Old cached/server payloads may lack the three topo anchors. Keep that compatibility path,
        // but never make current geometry pay the cold server-render cost that lost hole 4's facts.
        var resolved = lightweight
        if lightweight.resolvedMapOverlay == nil,
           !lightweight.route.isEmpty,
           let rendered = try? await client.fetchHolePrep(
               globalId: mapGlobalId,
               localHole: mapLocalHole,
               render: true,
               teeBox: package.course.teeBox
           ) {
            resolved = rendered
        }
        #if DEBUG
        // A freshly fetched hole can be visible before SwiftUI publishes the `@State` assignment
        // performed by retainThenPublishHolePrep. Move the deterministic simulator fix from the
        // already-resolved value so a hole transition cannot temporarily disable shot capture.
        moveSimulatedLocationToHoleTeeIfRequested(resolved)
        #endif
        let didPublish = await retainThenPublishHolePrep(
            resolved,
            globalId: mapGlobalId,
            sourceLocalHole: mapLocalHole,
            watchHole: hole.number
        )
        guard didPublish else { return false }
        // Re-push to the watch now that F/M/B + plays-like are available. The ordered bootstrap will
        // fetch and push the matching caddie decision immediately after this map step.
        if let holePrep {
            sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
        }
        return true
    }

    @MainActor
    private func waitForPreciseHoleMap(syncClub: Bool) async {
        guard let caddieBaseURL else {
            preciseMapTimedOut = true
            return
        }
        let mapGlobalId = hole.sourceGlobalId
        let mapLocalHole = hole.sourceLocalHole
        guard mapGlobalId != 0 else {
            preciseMapTimedOut = true
            return
        }
        let client = SyncClient(baseURL: caddieBaseURL, adminToken: adminToken)
        // The server-side install journal is already doing the expensive work. Keep the active
        // hole responsive with a short bounded probe instead of making a player wait through a
        // 60-second exponential slot after geometry has become ready.
        var delaySeconds: UInt64 = 2
        let deadline = Date().addingTimeInterval(30)

        while !Task.isCancelled {
            guard Date() < deadline else {
                // Keep the lightweight route usable after a bounded wait. A later foreground or
                // hole refresh may retry; the player is never trapped behind an unbounded spinner.
                preciseMapTimedOut = true
                return
            }
            do {
                try await Task.sleep(nanoseconds: delaySeconds * 1_000_000_000)
            } catch {
                return
            }
            guard !Task.isCancelled else { return }
            guard let refreshed = try? await client.fetchHolePrep(
                globalId: mapGlobalId,
                localHole: mapLocalHole,
                teeBox: package.course.teeBox
            ) else {
                delaySeconds = min(delaySeconds * 2, 15)
                continue
            }
            guard refreshed.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame else {
                delaySeconds = min(delaySeconds * 2, 15)
                continue
            }

            // Cache the matching bitmap and retain the precise prep before SwiftUI can publish the
            // ready map. A force-quit immediately after the map appears must therefore reopen the
            // same factual map instead of the partial package captured when the round started.
            let didPublish = await retainThenPublishHolePrep(
                refreshed,
                globalId: mapGlobalId,
                sourceLocalHole: mapLocalHole,
                watchHole: hole.number
            )
            guard didPublish else { return }
            // Rehydrate the decision from precise geometry after the durable map state is visible.
            await loadCaddieDecision(syncClub: syncClub && !hasUserSelectedClub)
            guard !Task.isCancelled else { return }
            return
        }
    }

    /// A ready prep and its bitmap are one user-visible fact. Make both durable before assigning
    /// `holePrep`; otherwise the player can see the precise map, kill the app, and resume from the
    /// older partial round package. Partial CourseView facts remain intentionally immediate.
    @MainActor
    private func retainThenPublishHolePrep(
        _ prep: CoursePrepHole,
        globalId: Int,
        sourceLocalHole: Int,
        watchHole: Int
    ) async -> Bool {
        guard CoursePrepHoleAdoptionPolicy.shouldAdopt(
            current: holePrep,
            incoming: prep,
            authoritativeRevision: hole.geometryRevision
        ) else {
            return false
        }
        holePrep = prep
        // The prep response is factual even while the caddie request is in flight or returns a
        // sparse card. Publish its route immediately so response ordering cannot hide the chain.
        reconcileCaddieRoutes()
        guard CoursePrepHoleAdoptionPolicy.isReadyMap(prep) else { return true }

        // Publish the factual map immediately. Watch/cache asset delivery is auxiliary and must not
        // keep the caddie strip in a loading state or make the player stare at the previous club.
        Task { @MainActor in
            await pushTopoToWatch(
                globalId: globalId,
                sourceLocalHole: sourceLocalHole,
                watchHole: watchHole,
                geometryRevision: prep.geometryRevision
            )
            await pushGreenDetailToWatch(
                globalId: globalId,
                sourceLocalHole: sourceLocalHole,
                watchHole: watchHole,
                prep: prep
            )
            onRetainReadyHolePrep(package.roundId, hole.number, prep)
        }
        return true
    }

    #if DEBUG
    /// A simulator cannot physically walk between holes. For the continuous real-course UI journey,
    /// recover this prep route's Tee GPS from the same calibrated topo projection used by the product.
    /// The explicit launch flag plus DEBUG compile gate prevent test movement from entering TestFlight.
    private func moveSimulatedLocationToHoleTeeIfRequested(_ packageHole: Hole) {
        guard let latitude = packageHole.teeLatitude,
              let longitude = packageHole.teeLongitude else { return }
        applySimulatedLocationIfRequested(latitude: latitude, longitude: longitude)
    }

    private func moveSimulatedLocationToHoleTeeIfRequested(_ prep: CoursePrepHole) {
        guard let first = prep.resolvedMapOverlay?.route.first, first.count >= 2,
              let refs = prep.holeImageProjection?.refs,
              let tee = WatchEventBridge.projectFromTopoPx(
                  px: first[0],
                  py: first[1],
                  refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
              ) else { return }
        applySimulatedLocationIfRequested(latitude: tee.latitude, longitude: tee.longitude)
    }

    private func applySimulatedLocationIfRequested(latitude: Double, longitude: Double) {
        guard ProcessInfo.processInfo.environment["UITEST_FOLLOW_HOLE_TEE"] == "1",
              let fix = locationProvider.moveSimulatedFixForUITest(
                  latitude: latitude,
                  longitude: longitude
              ) else { return }
        // Keep the view's derived state in the same transaction. Waiting for the @Published delivery
        // leaves `gpsHoleCandidate` on the previous hole for a frame and disables the shot button.
        currentCoordinate = fix.coordinate
        currentHorizontalAccuracyM = fix.horizontalAccuracyM
        gpsHoleCandidate = LiveHoleGPSResolver.candidate(
            holes: package.holes,
            coordinate: fix.coordinate,
            horizontalAccuracyM: fix.horizontalAccuracyM
        )
    }
    #endif

    /// Cache the clean topo independently of Watch availability, then relay the same bytes when a
    /// bridge exists. Phone durability must not depend on whether WatchConnectivity was created.
    private func pushTopoToWatch(
        globalId: Int,
        sourceLocalHole: Int,
        watchHole: Int,
        geometryRevision: String?
    ) async {
        guard globalId != 0, offlineStore != nil || watchBridge != nil else { return }
        if let cached = offlineStore?.loadCourseTopoImage(
            globalId: globalId,
            localHole: sourceLocalHole,
            geometryRevision: geometryRevision
        ) {
            if let watchBridge {
                watchBridge.pushHoleImage(
                    globalId: globalId,
                    hole: watchHole,
                    imageData: cached,
                    geometryRevision: geometryRevision
                )
            }
            return
        }
        #if DEBUG
        if ProcessInfo.processInfo.environment["UITEST_FORCE_LIVE_NETWORK_FAILURE"] == "1" {
            return
        }
        #endif
        guard let caddieBaseURL,
              let data = try? await SyncClient(
                  baseURL: caddieBaseURL,
                  adminToken: adminToken
              ).fetchTopoImage(
                  globalId: globalId,
                  localHole: sourceLocalHole,
                  geometryRevision: geometryRevision
              ) else { return }
        do {
            try offlineStore?.saveCourseTopoImage(
                data,
                globalId: globalId,
                localHole: sourceLocalHole,
                geometryRevision: geometryRevision
            )
        } catch {
            AICaddieLog.storage.error(
                "Live topo cache save failed for \(globalId, privacy: .public)/\(sourceLocalHole, privacy: .public): \(String(describing: error), privacy: .public)"
            )
        }
        if let watchBridge {
            watchBridge.pushHoleImage(
                globalId: globalId,
                hole: watchHole,
                imageData: data,
                geometryRevision: geometryRevision
            )
        }
    }

    /// Relay the focused View Green bitmap after the normal topo. The crop is derived from the same
    /// prep outline that becomes `WatchHoleMap.greenOutline`, so the Watch can place it without a
    /// second server manifest. A missing detail asset never blocks the round or the whole-hole map.
    private func pushGreenDetailToWatch(
        globalId: Int,
        sourceLocalHole: Int,
        watchHole: Int,
        prep: CoursePrepHole
    ) async {
        guard globalId != 0, let watchBridge, let caddieBaseURL,
              let projection = prep.holeImageProjection,
              let width = projection.widthPx,
              let height = projection.heightPx,
              let outline = prep.greenOutline,
              let crop = GreenDetailCrop.around(
                  points: outline.pointsPx,
                  imageWidth: Double(width),
                  imageHeight: Double(height)
              ) else { return }
        #if DEBUG
        if ProcessInfo.processInfo.environment["UITEST_FORCE_LIVE_NETWORK_FAILURE"] == "1" {
            return
        }
        #endif
        guard let data = try? await SyncClient(
            baseURL: caddieBaseURL,
            adminToken: adminToken
        ).fetchGreenDetailImage(
            globalId: globalId,
            localHole: sourceLocalHole,
            crop: crop,
            geometryRevision: prep.geometryRevision
        ), OfflineStore.isValidCourseTopoImageData(data) else { return }
        watchBridge.pushHoleImage(
            globalId: globalId,
            hole: watchHole,
            imageData: data,
            geometryRevision: prep.geometryRevision,
            assetKind: "green-detail"
        )
    }

    /// round-13 LIVE: 本洞前/中/后果岭(F/M/B)prep 数据,仅在 prep 几何可用时。distances 是 tee→green
    /// 静态值;B1 起它还带 F/M/B 的经纬度,供下面的 `liveGreenYards` 做实时测距。
    private var liveGreenDistances: CoursePrepGreenDistances? {
        guard let gd = holePrep?.greenDistances, gd.available else { return nil }
        return gd
    }

    /// 米 → 码(F/M/B 显示按码,与 R13 设计一致)。
    private func greenYards(_ metres: Double?) -> Int? {
        metres.map { Int(($0 * 1.09361).rounded()) }
    }

    /// round-13 B1 LIVE 测距:当前 GPS 定位 → 前/中/后果岭实时码距(haversine,客户端计算,离线可用)。
    /// 仅当有实时定位且该洞 prep 带果岭 F/M/B 经纬度时返回;否则 nil → 调用方回退到静态 tee→green 距离。
    /// 读取 @Published 的 `locationProvider.latestFix`,所以定位每次更新(球员走动)都会驱动重算与刷新。
    private var liveGreenYards: (front: Int?, middle: Int?, back: Int?)? {
        guard hasPlausibleLiveFix,
              let fix = locationProvider.latestFix,
              let gd = liveGreenDistances else { return nil }
        let here = fix.coordinate
        let front = GeoDistance.yards(from: here.latitude, here.longitude, to: gd.frontLat, gd.frontLon)
        let middle = GeoDistance.yards(from: here.latitude, here.longitude, to: gd.middleLat, gd.middleLon)
        let back = GeoDistance.yards(from: here.latitude, here.longitude, to: gd.backLat, gd.backLon)
        guard front != nil || middle != nil || back != nil else { return nil }
        return (front, middle, back)
    }

    /// watch P1d LIVE 果岭测距(米):当前 GPS → 前/中/后果岭 haversine 米距,发给手表当 F/M/B,让手表
    /// 成为真正的测距仪(距离随走动更新)。与 `liveGreenYards` 同源,但保留米制以复用手表侧 m→码 转换。
    private var liveGreenMetres: (front: Double?, middle: Double?, back: Double?)? {
        guard hasPlausibleLiveFix,
              let fix = locationProvider.latestFix,
              let gd = liveGreenDistances else { return nil }
        let here = fix.coordinate
        func metres(_ lat: Double?, _ lon: Double?) -> Double? {
            guard let lat, let lon else { return nil }
            return GeoDistance.haversineMetres(here.latitude, here.longitude, lat, lon)
        }
        let front = metres(gd.frontLat, gd.frontLon)
        let middle = metres(gd.middleLat, gd.middleLon)
        let back = metres(gd.backLat, gd.backLon)
        guard front != nil || middle != nil || back != nil else { return nil }
        return (front, middle, back)
    }

    /// 实时果岭测距当前是否生效(有 GPS 定位 + 该洞带果岭经纬度)→ 头部显示「实时」标记区分实时/静态。
    private var isGreenRangeLive: Bool { liveGreenYards != nil }

    /// Live-round hazard ranges use the player's current GPS fix and the measured front/back boundary
    /// pixels. A non-nil empty array means every measured hazard is already behind the player; nil
    /// means this older prep lacks the projection needed for live ranging and should use static facts.
    private var liveHazardReadouts: [CoursePrepLiveHazardReadout]? {
        guard let holePrep,
              holePrep.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame,
              hasPlausibleLiveFix,
              let fix = locationProvider.latestFix,
              let route = holePrep.resolvedMapOverlay?.route,
              let projection = holePrep.holeImageProjection,
              projection.available,
              let refs = projection.refs else {
            return nil
        }
        return CoursePrepLiveHazardReadout.upcoming(
            hazards: holePrep.hazards,
            route: route,
            projectionRefs: refs,
            playerLatitude: fix.coordinate.latitude,
            playerLongitude: fix.coordinate.longitude
        )
    }

    /// Measured hazard facts mirrored to the Watch. New prep carries true front/back boundary facts;
    /// old caches fall back to water intervals and a single reliable bunker route point.
    private func watchHazards() -> [WatchHazard] {
        guard let holePrep,
              holePrep.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame else {
            return []
        }
        let route = holePrep.resolvedMapOverlay?.route
        let routeLengthM = holePrep.resolvedMapOverlay?.ln ?? holePrep.routeLenM
        var out: [WatchHazard] = []
        let bunkerDetails = holePrep.hazards.details
            .filter {
                $0.kind == "bunker"
                    && CoursePrepHazardRelevance.isRelevant(
                        kind: $0.kind,
                        frontRouteM: $0.frontRouteM,
                        backRouteM: $0.backRouteM,
                        routeLengthM: routeLengthM,
                        hasPreciseOutline: $0.outlinePx.count >= 3
                    )
            }
            .sorted { $0.frontRouteM < $1.frontRouteM }
        if !bunkerDetails.isEmpty {
            for detail in bunkerDetails {
                out.append(WatchHazard(
                    kind: "bunker",
                    label: CoursePrepHazardNaming.label(
                        kind: "bunker", detail: detail, route: route
                    ),
                    startM: detail.frontRouteM,
                    endM: detail.backRouteM,
                    frontDistanceM: detail.frontM,
                    backDistanceM: detail.backM,
                    frontPx: detail.frontPx,
                    backPx: detail.backPx
                ))
            }
        } else {
            let bunkers = holePrep.hazards.bunkers
                .filter {
                    guard let front = $0.first else { return false }
                    return CoursePrepHazardRelevance.isRelevant(
                        kind: "bunker",
                        frontRouteM: front,
                        backRouteM: front,
                        routeLengthM: routeLengthM
                    )
                }
                .sorted { ($0.first ?? 0) < ($1.first ?? 0) }
            for interval in bunkers {
                out.append(WatchHazard(
                    kind: "bunker",
                    label: CoursePrepHazardNaming.intervalLabel(
                        kind: "bunker", interval: interval, route: route
                    ),
                    startM: interval.first,
                    sideM: interval.count >= 2 ? interval[1] : nil
                ))
            }
        }
        let waterDetails = holePrep.hazards.details
            .filter {
                $0.kind == "water"
                    && CoursePrepHazardRelevance.isRelevant(
                        kind: $0.kind,
                        frontRouteM: $0.frontRouteM,
                        backRouteM: $0.backRouteM,
                        routeLengthM: routeLengthM,
                        hasPreciseOutline: $0.outlinePx.count >= 3
                    )
            }
            .sorted { $0.frontRouteM < $1.frontRouteM }
        if !waterDetails.isEmpty {
            for detail in waterDetails {
                out.append(WatchHazard(
                    kind: "water",
                    label: CoursePrepHazardNaming.label(
                        kind: "water", detail: detail, route: route
                    ),
                    startM: detail.frontRouteM,
                    endM: detail.backRouteM,
                    frontDistanceM: detail.frontM,
                    backDistanceM: detail.backM,
                    frontPx: detail.frontPx,
                    backPx: detail.backPx
                ))
            }
        } else {
            let water = holePrep.hazards.waterCarry
                .filter {
                    guard let front = $0.first else { return false }
                    let back = $0.dropFirst().first ?? front
                    return CoursePrepHazardRelevance.isRelevant(
                        kind: "water",
                        frontRouteM: front,
                        backRouteM: back,
                        routeLengthM: routeLengthM
                    )
                }
                .sorted { ($0.first ?? 0) < ($1.first ?? 0) }
            for interval in water {
                out.append(WatchHazard(
                    kind: "water",
                    label: CoursePrepHazardNaming.intervalLabel(
                        kind: "water", interval: interval, route: route
                    ),
                    startM: interval.first,
                    endM: interval.count >= 2 ? interval[1] : nil
                ))
            }
        }
        return out
    }

    /// Club picker options: the player's clubs, minus empty/"Unknown" placeholders and
    /// case-insensitive duplicates (Garmin club names are user-entered and messy).
    /// Player's clubs from the backend real bag: zhClubName-normalized, deduped (keep most-sampled),
    /// restricted to the player's bag. Tee-only clubs are filtered only after the opening shot and
    /// only when the current shot is not a tee shot; the old `selectedLie` gate hid driver before the
    /// player had hit anything.
    private func bagBest(filterTeeOnly: Bool) -> [String: ClubProfile] {
        var best: [String: ClubProfile] = [:]
        for profile in package.clubProfiles {
            let raw = profile.clubName.trimmingCharacters(in: .whitespaces)
            guard !raw.isEmpty, raw.lowercased() != "unknown" else { continue }
            let name = zhClubName(raw)
            if filterTeeOnly, shouldFilterTeeOnlyClubs, clubIsTeeOnly(name) { continue }
            if let existing = best[name], existing.sampleSize >= profile.sampleSize { continue }
            best[name] = profile
        }
        // Restrict to the player's bag — manual override (球杆设置) if set, else the real Garmin bag —
        // so clubs they don't carry (a stray mis-tagged "二号小鸡腿") never appear. Neither known → all.
        if let bag = ClubBagStore.effectiveBag() {
            best = best.filter { bag.contains($0.key) }
        }
        return best
    }

    private var shouldFilterTeeOnlyClubs: Bool {
        selectedShotType.lowercased() != "tee" && recordedNonPuttShotCount > 0
    }

    /// Profiles used by the quick strip. The backend recommendation is re-added from the complete
    /// bag even when a tee-only fallback filter would otherwise remove it.
    private var caddieClubProfiles: [String: ClubProfile] {
        var profiles = bagBest(filterTeeOnly: true)
        if let recommendedClub,
           profiles[recommendedClub] == nil,
           let fallback = bagBest(filterTeeOnly: false)[recommendedClub] {
            profiles[recommendedClub] = fallback
        }
        return profiles
    }

    /// The three quick chips always put the actual caddie recommendation first. Distance-ranked bag
    /// clubs fill the remaining slots and the selected club remains visible for manual choices.
    private var clubNames: [String] {
        LiveClubStripPolicy.orderedNames(
            profiles: caddieClubProfiles,
            recommended: recommendedClub,
            selected: selectedClub,
            targetMetres: effectiveDistanceToPinMetres
        )
    }

    /// round-12: the FULL bag for the dropdown picker — every club + its distance, longest→shortest,
    /// so the player can choose ANY club (not just the 3 quick chips). No tee-only filter here.
    private var allBagClubs: [(name: String, metres: Double)] {
        bagBest(filterTeeOnly: false)
            .sorted { $0.value.medianM > $1.value.medianM }
            .map { (name: $0.key, metres: $0.value.medianM) }
    }

    /// The caddie's currently-recommended club (zh), used to mark it in the dropdown.
    private var recommendedClub: String? {
        recommendedClubChoice?.name
    }

    /// The same normalized club/carry pair drives the strip and the map. Do not derive the map
    /// distance from a possibly stale local median when the backend supplied a strategy carry.
    private var recommendedClubChoice: LiveClubStripPolicy.Recommendation? {
        if let first = selectedLiveCaddieRoute?.steps.first {
            let name = zhClubName(first.clubName)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if !name.isEmpty, name != "-" {
                return LiveClubStripPolicy.Recommendation(
                    name: name,
                    carryMetres: first.targetCarryM
                )
            }
        }
        guard let decision = caddieDecision else { return nil }
        return LiveClubStripPolicy.recommendation(
            from: decision,
            strategyMode: activeStrategyMode
        )
    }

    /// The map and the caddie sheet consume one selected sequence. A legacy Par-3 card without a
    /// structured sequence still gets a direct tee-to-pin scoring leg below.
    private var livePlannedShots: [MapPlannedShot] {
        if let sequence = selectedLiveCaddieRoute {
            let shots = sequence.steps.enumerated().compactMap { index, step -> MapPlannedShot? in
                let name = step.clubName.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !name.isEmpty, name != "-" else { return nil }
                let routeEnd = holePrep?.resolvedMapOverlay?.ln
                    ?? holePrep?.routeLenM
                    ?? effectiveDistanceToPinMetres
                    ?? 0
                let targetsPin: Bool = {
                    if step.greenInRegulation == true { return false }
                    if hole.par == 3 && selectedShotType.caseInsensitiveCompare("tee") == .orderedSame {
                        return true
                    }
                    return index == sequence.steps.count - 1
                        && shouldTargetPin(
                            offsetM: step.routeOffsetM ?? step.landingM,
                            role: step.role,
                            shotIndex: index,
                            routeEndM: routeEnd
                        )
                }()
                return MapPlannedShot(
                    id: "live-\(sequence.id)-\(step.id)",
                    clubName: name,
                    carryM: step.targetCarryM,
                    routeOffsetM: step.routeOffsetM ?? step.landingM,
                    role: step.role,
                    expectedRemainingM: step.expectedRemainingM,
                    targetsPin: targetsPin,
                    planIndex: step.planIndex ?? index
                )
            }
            if !shots.isEmpty { return shots }
        }

        // Legacy Par-3 responses can contain only a selected option card and no structured
        // `sequences` payload. Keep the map and card coherent by materialising that one factual
        // club as a direct tee-to-pin scoring leg. The carry remains the player's measured club
        // fact; the route endpoint is the green, because this is a scoring recommendation.
        guard hole.par == 3,
              selectedShotType.caseInsensitiveCompare("tee") == .orderedSame,
              let response = caddieDecision ?? makeOfflineCaddieDecision(),
              let targetM = effectiveDistanceToPinMetres
                ?? holePrep?.resolvedMapOverlay?.ln
                ?? holePrep?.routeLenM
                ?? hole.yards.map { CoursePrepRoute.metres(fromYards: Double($0)) },
              targetM > 0 else {
            return []
        }
        let option = CaddiePlanOption.options(from: response).first {
            let name = $0.clubName.trimmingCharacters(in: .whitespacesAndNewlines)
            return !name.isEmpty && name != "-"
        }
        guard let option else { return [] }
        return [
            MapPlannedShot(
                id: "par3-fallback-\(option.id)-\(option.clubName)",
                clubName: option.clubName,
                carryM: option.carryM > 0 ? option.carryM : nil,
                routeOffsetM: targetM,
                role: "scoring",
                expectedRemainingM: 0,
                targetsPin: true,
                planIndex: 0
            )
        ]
    }

    private func selectPlanStep(_ index: Int) {
        guard livePlannedShots.contains(where: { $0.planIndex == index }) else { return }
        selectedPlanIndex = selectedPlanIndex == index ? nil : index
    }

    /// round-12: full-bag dropdown — pick ANY club + its distance; recommended club marked; defaults
    /// to the recommendation (selectedClub is synced to it). Selecting records the pick (选完即记).
    @ViewBuilder private var clubPickerMenu: some View {
        Menu {
            ForEach(allBagClubs, id: \.name) { club in
                Button {
                    selectClub(club.name)
                } label: {
                    let label = "\(club.name) · \(CoursePrepRoute.yards(fromMetres: club.metres)) 码"
                        + (club.name == recommendedClub ? " · 推荐" : "")
                    if club.name == selectedClub {
                        Label(label, systemImage: "checkmark")
                    } else {
                        Text(label)
                    }
                }
            }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "bag").font(.caption)
                Text(selectedClub.isEmpty ? "选择球杆" : selectedClub).font(.subheadline.weight(.semibold))
                Image(systemName: "chevron.down").font(.caption2)
            }
            .foregroundStyle(LiveHoleStyle.green)
        }
    }

    /// Set the selected club (chips + dropdown). round-12「选完即记」: persist the pick immediately as
    /// a lightweight club-selection event (clubName/打法/球位/距离 — NOT a shot/GPS record) so the
    /// choice survives a quit/restart and drives the map landing marker.
    private func selectClub(_ club: String) {
        let changed = club != selectedClub
        selectedClub = club
        guard changed, !club.isEmpty else { return }
        hasUserSelectedClub = true
        emit(kind: .club, timestamp: ISO8601DateFormatter().string(from: Date()), payload: [
            "clubName": .string(selectedClub),
            "shotType": .string(selectedShotType),
            "strategyMode": .string(selectedStrategyMode),
            "lie": .string(selectedLie),
            "distanceToPinM": distanceToPinPayload(),
        ])
    }

    /// The selected club's typical distance (metres) from the bag model — drives the live map marker.
    private var selectedClubMetres: Double? {
        guard !selectedClub.isEmpty else { return nil }
        if let recommendation = recommendedClubChoice,
           recommendation.name == selectedClub,
           let carry = recommendation.carryMetres {
            return carry
        }
        return package.clubProfiles.first(where: { zhClubName($0.clubName) == selectedClub })?.medianM
    }

    /// The club the player will hit NOW under the caddie's decision: the first step of the selected
    /// sequence (the tee/advance shot) when sequences exist, else the selected single-club option.
    private func recommendedClubName(from decision: CaddieDecisionResponse) -> String? {
        LiveClubStripPolicy.recommendation(
            from: decision,
            strategyMode: activeStrategyMode
        )?.name
    }

    /// Adopt the caddie's recommended club as the selected club so the club strip highlight and the
    /// hole-map landing marker follow the recommendation (and change with strategy). No-op if the
    /// decision carries no usable club.
    @MainActor
    private func syncSelectedClubToRecommendation() {
        selectedClub = LiveClubStripPolicy.caddieOwnedSelection(
            current: selectedClub,
            recommendation: recommendedClubChoice?.name,
            userSelected: hasUserSelectedClub,
            noRoute: caddieDecision?.isLocalNoRoute == true
        )
    }

    // MARK: - B4 turn (接着打哪个 9 洞)

    /// The turn plan when this round is exactly one loop: a half of an 18-hole course, or a
    /// nine-hole loop of a known venue.
    private var turnPlanAtEndOfFirstLoop: NineLoopPlan? {
        guard liveRoundState != nil else { return nil }
        var remembered: [String: String] = [:]
        var history: [HistoryRoundCard] = []
        if let offlineStore {
            remembered = (try? offlineStore.loadNineLoopPairings()) ?? [:]
            if let archive = try? offlineStore.loadHistoryRoundsArchive() {
                history = archive.groups.flatMap(\.rounds)
            }
        }
        return NineLoopTurn.planAtEndOfFirstLoop(
            package: package, catalogue: courseOptions, remembered: remembered, history: history
        )
    }

    private func continueIntoSecondLoop(_ loop: NineLoop) {
        guard let entry = NineLoopTurn.entry(loop.id),
              let first = package.roundLoops.first else { return }
        try? offlineStore?.rememberNineLoopPairing(first: NineLoopTurn.loopId(first.entry), second: loop.id)
        // The model adds the loop and opens its first hole: this view is rebuilt for the new hole
        // set, so it cannot own that navigation. The sheet stays until then.
        turnContinuationFailed = false
        turnContinuationPending = true
        onContinueIntoSecondLoop(entry, package.roundId)
    }

    /// The second loop can still be changed until its first hole has anything recorded: the lock
    /// is any event on a round hole at or after the second loop's start (B4b-2 — round holes, so
    /// 后→前 locks on round hole 10 exactly like 前→后).
    private var secondLoopStarted: Bool {
        guard package.secondLoop != nil,
              let offlineStore,
              let events = try? offlineStore.loadEvents() else { return false }
        return package.isSecondLoopLocked(by: events)
    }

    // MARK: - 球局洞数调整

    /// The header menu is the single finish entry. This section only mutates the playable hole set.
    @ViewBuilder private var manageSection: some View {
        DisclosureGroup(isExpanded: $showManage) {
            VStack(spacing: 8) {
                loopAddControl
            }
            .padding(.top, 8)
        } label: {
            Label("球洞调整 · 加打 / 移除", systemImage: "slider.horizontal.3")
                .font(.subheadline).foregroundStyle(.secondary)
        }
        .livePlayAuxiliaryCard()
    }

    /// The loops this round may add or switch to as its second loop: the other half and the same
    /// half of an 18-hole course (前九 / 后九), or the venue's labelled nine-hole loops (the
    /// current loop included). README §8: never a synthesized "9 洞组" in a selectable B4 control.
    private var selectableSecondLoops: [NineLoop] {
        guard let first = package.roundLoops.first else { return [] }
        if first.isCourseHalf {
            return NineLoopTurn.halves(globalId: first.globalId)
        }
        guard let active = courseOptions.first(where: { $0.globalId == first.globalId }),
              active.resolvedHoles == 9 else { return [] }
        return NineLoopTurn.siblings(of: active, in: courseOptions).compactMap(NineLoopTurn.loop)
    }

    @ViewBuilder private var loopAddControl: some View {
        // 仅进行中:单环 → 加打第二环;已有第二环且未开打 → 改打或移除(第二环第一洞一有记录就锁定)。
        if liveRoundState != nil, let first = package.roundLoops.first {
            let firstId = NineLoopTurn.loopId(first.entry)
            if package.roundLoops.count == 1 {
                if !selectableSecondLoops.isEmpty {
                    Menu {
                        ForEach(selectableSecondLoops, id: \.id) { loop in
                            Button("＋ \(loop.displayName) · 凑 18 洞") {
                                guard let entry = NineLoopTurn.entry(loop.id) else { return }
                                try? offlineStore?.rememberNineLoopPairing(first: firstId, second: loop.id)
                                onSetSecondLoop(entry, package.roundId)
                            }
                        }
                    } label: {
                        Label("＋加打另一个 9 洞(凑 18)", systemImage: "plus.circle")
                            .font(.subheadline.weight(.semibold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 12)
                            .foregroundStyle(LiveHoleStyle.green)
                            .overlay(RoundedRectangle(cornerRadius: 12).stroke(LiveHoleStyle.green))
                    }
                    .disabled(isPreparingRound)
                    .accessibilityIdentifier("live-add-second-loop")
                }
            } else if !secondLoopStarted {
                let currentSecond = package.secondLoop.map { NineLoopTurn.loopId($0.entry) }
                let alternatives = selectableSecondLoops.filter { $0.id != currentSecond }
                if !alternatives.isEmpty {
                    Menu {
                        ForEach(alternatives, id: \.id) { loop in
                            Button("改打 \(loop.displayName)") {
                                guard let entry = NineLoopTurn.entry(loop.id) else { return }
                                try? offlineStore?.rememberNineLoopPairing(first: firstId, second: loop.id)
                                onSetSecondLoop(entry, package.roundId)
                            }
                        }
                    } label: {
                        Label("改打别的 9 洞", systemImage: "arrow.triangle.2.circlepath")
                            .font(.subheadline.weight(.semibold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 12)
                            .foregroundStyle(LiveHoleStyle.green)
                            .overlay(RoundedRectangle(cornerRadius: 12).stroke(LiveHoleStyle.green))
                    }
                    .disabled(isPreparingRound)
                    .accessibilityIdentifier("live-change-second-loop")
                }
                Button {
                    onSetSecondLoop(nil, package.roundId)
                } label: {
                    Label("移除第二环 · 只打 9 洞", systemImage: "minus.circle")
                        .font(.subheadline)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .foregroundStyle(.secondary)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(LiveHoleStyle.line))
                }
                .disabled(isPreparingRound)
                .accessibilityIdentifier("live-remove-second-loop")
            }
        }
    }

    private var shotTypeOptions: [String] {
        let options = caddieContextSeed?.shotTypes ?? []
        return options.isEmpty ? ["tee", "approach", "recovery"] : options
    }

    private var lieOptions: [String] {
        ["fairway", "rough", "bunker", "green", "tee", "recovery"]
    }

    /// 击球类型 / 球位的封闭英文枚举 → 中文(更多调整里的选择器)。未知值原样回退。
    private func zhShotType(_ value: String) -> String {
        switch value.lowercased() {
        case "tee":
            return "开球"
        case "approach":
            return "攻果岭"
        case "recovery":
            return "解围"
        case "layup":
            return "铺垫"
        case "putt":
            return "推杆"
        default:
            return value.capitalized
        }
    }

    private func zhLie(_ value: String) -> String {
        switch value.lowercased() {
        case "fairway":
            return "球道"
        case "rough":
            return "长草"
        case "bunker":
            return "沙坑"
        case "green":
            return "果岭"
        case "tee":
            return "发球台"
        case "recovery":
            return "解围"
        default:
            return value.capitalized
        }
    }

    private func makeCaddieDecisionRequest() -> CaddieDecisionRequest? {
        guard let caddieContextSeed else {
            return nil
        }
        let baseRequest = requestBuilder.makeDecisionRequest(
            seed: caddieContextSeed,
            input: LiveCaddieInput(
                shotType: selectedShotType,
                distanceToPinM: effectiveDistanceToPinMetres,
                lie: selectedLie,
                coordinate: liveCoordinateForCurrentHole,
                targetCoordinate: wireTargetCoordinate,
                targetKind: wireTargetKind,
                horizontalAccuracyM: liveCoordinateForCurrentHole == nil ? nil : currentHorizontalAccuracyM,
                capturedAt: liveCoordinateForCurrentHole == nil ? nil : locationProvider.latestFix?.capturedAt,
                strategyMode: requestStrategyMode,
                requestedOptionId: caddieOptionId(forStrategyMode: requestStrategyMode),
                visionFindings: visionFindings
            )
        )
        // A package created before PHONE-UX6 may have the prep chain in the course payload but not
        // in its caddie seed. Fill that one missing transport fact locally so an offline/older
        // package cannot resurrect the independent ``3H -> 3H`` planner on the first tee request.
        return CaddieDecisionRequestBuilder.addingCanonicalPlan(to: baseRequest, prep: holePrep)
    }

    /// Adopt the route the decision engine actually selected. The request's strategy/option is a
    /// preference, not a guarantee: hazards, dispersion, sparse samples, or a whole-hole leave
    /// can make the engine choose another route. Keeping this field aligned is important for the
    /// next-club strip, Watch state, and persisted club events.
    @MainActor
    private func syncStrategyModeToDecision(_ response: CaddieDecisionResponse?) {
        requestedStrategyMode = nil
        _ = response
        reconcileCaddieRoutes()
        guard let selected = selectedLiveCaddieRoute else {
            return
        }
        let authoritative = caddieSelectionToken(forRouteId: selected.id)
            ?? caddieSelectionToken(forRouteId: selected.label)
            ?? "stock"
        if selectedStrategyMode != authoritative {
            selectedStrategyMode = authoritative
        }
    }

    @MainActor
    private func loadCaddieDecision(syncClub: Bool = false) async {
        caddieRequestGeneration &+= 1
        let requestGeneration = caddieRequestGeneration
        isLoadingCaddieDecision = true
        defer {
            if requestGeneration == caddieRequestGeneration {
                isLoadingCaddieDecision = false
            }
        }
#if DEBUG
        let effectiveClient = ProcessInfo.processInfo.environment["UITEST_FORCE_LIVE_NETWORK_FAILURE"] == "1"
            ? nil
            : caddieClient
        #else
        let effectiveClient = caddieClient
        #endif
        guard let effectiveClient else {
            caddieDecision = makeOfflineCaddieDecision()
            syncStrategyModeToDecision(caddieDecision)
            caddieErrorMessage = caddieDecision == nil
                ? "这一洞暂时无法给建议。"
                : (caddieDecision?.isLocalNoRoute == true
                    ? Self.localNoRouteMessage
                    : "离线模式 · 使用已保存的方案。")
            if syncClub { syncSelectedClubToRecommendation() }
            sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
            return
        }
        guard let request = makeCaddieDecisionRequest() else {
            caddieErrorMessage = "这一洞暂时无法给建议。"
            sendWatchState(decision: nil, offlineOption: selectedOfflineOption)
            return
        }

        let requestedBeforePrep = holePrep == nil
        do {
            let response = try await effectiveClient.fetchCaddieDecision(request, endpoint: package.caddieDecisionEndpoint)
            guard !Task.isCancelled, requestGeneration == caddieRequestGeneration else { return }
            // If prep arrived while a manual distance-free request was in flight, the ordered hole
            // bootstrap will launch the context-complete request next. Never let the stale answer
            // overwrite it.
            guard !(requestedBeforePrep && holePrep != nil) else { return }
            let offlineDecision = makeOfflineCaddieDecision()
            if LiveCaddieDecisionUsability.hasRecommendation(response) {
                // Route authority is reconciled below. Keep the response itself so its measured
                // alternatives/evidence remain available, but never let a sparse selectedSequence
                // replace the retained CoursePrep route.
                caddieDecision = response
                caddieErrorMessage = nil
            } else if let offlineDecision {
                caddieDecision = offlineDecision
                // A complete local route is a usable recommendation. Transport provenance is an
                // implementation detail and should not displace live playing information.
                caddieErrorMessage = offlineDecision.isLocalNoRoute ? Self.localNoRouteMessage : nil
            } else {
                caddieDecision = nil
                caddieErrorMessage = "球场资料准备中，请稍后刷新。"
            }
            // The server has now resolved the requested route (including any safety constraints).
            // Reconcile once, then make every surface consume the same retained route.
            syncStrategyModeToDecision(caddieDecision)
            if syncClub { syncSelectedClubToRecommendation() }
            sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
        } catch let error where LiveCaddieLoadFailure.isCancellation(error) {
            return
        } catch {
            guard requestGeneration == caddieRequestGeneration else { return }
            if let offlineDecision = makeOfflineCaddieDecision() {
                caddieDecision = offlineDecision
                syncStrategyModeToDecision(offlineDecision)
                caddieErrorMessage = offlineDecision.isLocalNoRoute
                    ? Self.localNoRouteMessage
                    : "联网球童暂不可用 · 已切换到离线缓存建议。"
            } else {
                caddieErrorMessage = "球童建议暂取不到 · 仍显示已缓存的方案。"
            }
            if syncClub { syncSelectedClubToRecommendation() }
            sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
        }
    }

    private func intValue(_ value: JSONValue?) -> Int? {
        guard case .number(let raw) = value, raw.isFinite else { return nil }
        return Int(raw.rounded())
    }

    /// An offline decision that recommends nothing must not claim a saved plan.
    static let localNoRouteMessage = "离线没有安全完整的路线 · 联网后再给建议。"

    private func makeOfflineCaddieDecision() -> CaddieDecisionResponse? {
        guard let caddieContextSeed,
              let request = makeCaddieDecisionRequest()
        else {
            return nil
        }
        return offlineDecisionEvaluator.makeDecision(
            seed: caddieContextSeed,
            request: request,
            strategyMode: requestStrategyMode
        )
    }

    private var selectedOfflineOption: OfflineCaddieOption? {
        guard let seed = caddieContextSeed else {
            return nil
        }
        if let decision = caddieDecision, decision.isOfflineFallback {
            // An offline decision with no selected option found no safe, complete route: there is
            // no club to recommend, so the seed's own pick must not resurface on the Watch.
            guard let selectedID = decision.selectedOptionId else { return nil }
            if let selected = seed.offlineOptions.first(where: { $0.optionId == selectedID }) {
                return selected
            }
        }
        return offlineDecisionEvaluator.selectedOption(
            in: seed,
            strategyMode: requestStrategyMode,
            requestedOptionId: caddieOptionId(forStrategyMode: requestStrategyMode)
        )
    }

    private func sendWatchState(decision: CaddieDecisionResponse?, offlineOption: OfflineCaddieOption?) {
        // round-13 LIVE: forward the per-hole 前/中/后果岭 (F/M/B) + plays-like slope the backend
        // already ships on /prep (holePrep), plus the geometry-coverage gate. Static tee→green
        // distances (not live-GPS recomputed); nil on holes without usable geometry.
        let green = holePrep?.greenDistances
        let greenOK = green?.available == true
        // watch P1d: prefer LIVE-GPS green distances (from where the player stands) over static tee→green.
        let liveGreens = liveGreenMetres
        let playsLike = holePrep?.playsLike
        let slopeM = playsLike?.available == true ? playsLike?.deltaM : nil
        // watch P0.2: forward the topo geo→px projection so the watch overlays its own GPS/pin/landings.
        let hip = holePrep?.holeImageProjection
        let watchProj: WatchHoleImageProjection? = (hip?.available == true)
            ? WatchHoleImageProjection(
                widthPx: hip?.widthPx, heightPx: hip?.heightPx,
                refs: hip?.refs?.map { WatchProjectionRef(lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) })
            : nil
        // watch P1b/P1c: pre-compute the hole-map overlay anchors (you / pin=green / lay-up) from the
        // centreline route so the watch draws the map on the cached /topo.png with no projection math.
        // `you` follows the player's LIVE GPS (projected onto the topo via the same affine refs) when a
        // fix is available, else falls back to the tee — so the map pans as you walk (companion mode).
        let mapGlobalId = hole.sourceGlobalId
        let youPxOverride: [Double]? = {
            guard let coord = liveCoordinateForCurrentHole, let refs = hip?.refs, refs.count >= 3 else { return nil }
            return WatchEventBridge.projectToTopoPx(
                lat: coord.latitude, lon: coord.longitude,
                refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) })
        }()
        let holeMap: WatchHoleMap? = (holePrep?.resolvedMapOverlay).flatMap {
            WatchEventBridge.makeHoleMap(
                overlay: $0,
                landingM: holePrep?.landingM,
                youPxOverride: youPxOverride,
                greenOutline: holePrep?.greenOutline?.available == true
                    ? holePrep?.greenOutline?.pointsPx
                    : nil
            )
        }
        let state = watchBridge?.makeWatchRoundStatePayload(
            package: package,
            hole: hole,
            score: score,
            putts: puttCount,
            penaltyCount: penaltyCount,
            selectedClub: selectedClub.isEmpty ? nil : selectedClub,
            decision: decision,
            offlineOption: offlineOption,
            distanceToPinM: effectiveDistanceToPinMetres,
            targetLatitude: wireTargetCoordinate?.latitude,
            targetLongitude: wireTargetCoordinate?.longitude,
            targetKind: wireTargetKind,
            frontGreenM: liveGreens?.front ?? (greenOK ? green?.frontM : nil),
            centerGreenM: liveGreens?.middle ?? (greenOK ? green?.middleM : nil),
            backGreenM: liveGreens?.back ?? (greenOK ? green?.backM : nil),
            frontGreenLat: greenOK ? green?.frontLat : nil,
            frontGreenLon: greenOK ? green?.frontLon : nil,
            centerGreenLat: greenOK ? green?.middleLat : nil,
            centerGreenLon: greenOK ? green?.middleLon : nil,
            backGreenLat: greenOK ? green?.backLat : nil,
            backGreenLon: greenOK ? green?.backLon : nil,
            holeImageProjection: watchProj,
            globalId: mapGlobalId,
            holeMap: holeMap,
            playsLikeDistanceM: playsLikeMetres(
                distanceMetres: effectiveDistanceToPinMetres,
                elevationDeltaMetres: slopeM
            ),
            elevationDeltaM: slopeM,
            geometryCoverage: holePrep?.geometryCoverage ?? hole.geometryCoverage.rawValue,
            geometryRevision: holePrep?.geometryRevision ?? hole.geometryRevision,
            hazards: watchHazards()
        )
        if let state {
            try? watchBridge?.sendStateToWatch(state)
        }
    }

    private func playsLikeMetres(distanceMetres: Double?, elevationDeltaMetres: Double?) -> Double? {
        guard let distanceMetres, distanceMetres.isFinite,
              let elevationDeltaMetres, elevationDeltaMetres.isFinite else { return nil }
        return distanceMetres + elevationDeltaMetres
    }

    private func applyRestoredStateIfNeeded(_ snapshot: LiveRoundStateSnapshot?) {
        guard let restoredHoleState = snapshot?.holeState(for: hole.number) else {
            return
        }
        guard lastAppliedRestoredHoleState?.hasSameRestorableFields(as: restoredHoleState) != true else {
            return
        }
        applyRestoredState(restoredHoleState)
    }

    private func applyRestoredState(_ restoredHoleState: LiveHoleStateSnapshot) {
        // Save-only fields are persisted only on explicit Save; preserve any the user
        // has edited-but-not-saved instead of reverting them to the snapshot (P0-5).
        let reconciled = restoredHoleState.reconciledSaveOnlyFields(
            currentScore: score,
            currentPutts: puttCount,
            currentPenaltyCount: penaltyCount,
            lastApplied: lastAppliedRestoredHoleState
        )
        score = reconciled.score
        puttCount = reconciled.putts
        penaltyCount = reconciled.penaltyCount
        // Normalise to the same zhClubName the picker uses (init does this) so the ClubStrip highlight matches.
        // An empty selection is intentional while a fresh decision is loading; never turn it into a
        // stale default club just because the event log was replayed.
        selectedClub = Self.normalizedSelectedClub(restoredHoleState.selectedClub)
        hasUserSelectedClub = !selectedClub.isEmpty
        selectedShotType = restoredHoleState.selectedShotType
        // A restored event is authoritative for the persisted legacy field, but it is never a
        // pending tap. Do not replay a stale one-shot override when a saved round is rehydrated.
        requestedStrategyMode = nil
        selectedStrategyMode = restoredHoleState.selectedStrategyMode
        selectedLie = restoredHoleState.lie
        distanceToPinText = Self.validDistanceText(restoredHoleState.distanceToPinM)
        if let latitude = restoredHoleState.latitude, let longitude = restoredHoleState.longitude {
            currentCoordinate = CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
        }
        if let restoredTarget = Self.restoredTarget(from: restoredHoleState) {
            if restoredTarget.kind == "pin" {
                targetCoordinate = nil
                targetKind = nil
                greenPinCoordinate = restoredTarget.coordinate
            } else {
                targetCoordinate = restoredTarget.coordinate
                targetKind = restoredTarget.kind
                greenPinCoordinate = nil
            }
            lastTargetEditKind = restoredTarget.kind
        } else {
            targetCoordinate = nil
            greenPinCoordinate = nil
            targetKind = nil
            lastTargetEditKind = nil
        }
        // Pixel targets are session-local unless the server has a geo coordinate to reproject. A
        // restored hole starts without a stale point from the previously visible hole.
        targetPixel = nil
        greenPinPixel = nil
        currentHorizontalAccuracyM = restoredHoleState.horizontalAccuracyM
        lastAppliedRestoredHoleState = restoredHoleState
        sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
    }

    private func beginScoreConfirmation() {
        if scoreDraft == nil {
            // Preselect from the best evidence (README §2): Watch swings → the phone's 记一杆
            // count + 2 putts → par. The phone does not receive Watch swing counts yet (B7).
            scoreDraft = LiveScoreDraft(
                hole: hole.number,
                par: hole.par,
                watchSwingCount: nil,
                phoneShotCount: recordedNonPuttShotCount,
                teeResult: liveTeeResultPreselection
            )
        }
        if let scoreDraft {
            if let offlineStore {
                try? offlineStore.saveLiveScoreDraft(roundId: package.roundId, draft: scoreDraft)
            }
        }
    }

    private func acceptScoreConfirmation(_ accepted: LiveScoreDraft) {
        let events = LiveScoreSubmission.events(
            roundId: package.roundId,
            draft: accepted,
            note: note,
            timestamp: ISO8601DateFormatter().string(from: Date())
        )
        events.forEach(onEvent)
        if let offlineStore {
            try? offlineStore.clearLiveScoreDraft(roundId: package.roundId)
        }
        scoreDraft = nil
        if accepted.hole == hole.number {
            score = accepted.score
            puttCount = accepted.putts
            penaltyCount = accepted.penalty
        }
        if accepted.advanceAfterSave {
            switch LiveHoleAdvanceResolution.resolve(after: accepted.hole, package: package) {
            case .advance(let next):
                onAdvanceHole(next)
            case .finish:
                if let plan = turnPlanAtEndOfFirstLoop {
                    turnPlan = plan
                } else {
                    showRoundSummary = true
                }
            }
        }
        sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
    }

    private func cancelScoreConfirmation() {
        let draftHole = scoreDraft?.hole
        let shouldReturnToDraftHole = scoreDraft?.advanceAfterSave == true && draftHole != hole.number
        if let offlineStore {
            try? offlineStore.clearLiveScoreDraft(roundId: package.roundId)
        }
        scoreDraft = nil
        if shouldReturnToDraftHole, let draftHole {
            onAdvanceHole(draftHole)
        }
    }

    private var recordedScoreHoles: Set<Int> {
        guard let offlineStore, let events = try? offlineStore.loadEvents() else { return [] }
        let displayedHoles = Set(package.holes.map(\.number))
        return Set(events.compactMap { event in
            guard event.roundId == package.roundId,
                  displayedHoles.contains(event.hole),
                  event.kind == .score else {
                return nil
            }
            return event.hole
        })
    }

    private var completedHoleStates: [(hole: Hole, state: LiveHoleStateSnapshot)] {
        let recorded = recordedScoreHoles
        return package.holes.compactMap { hole in
            guard recorded.contains(hole.number),
                  let state = liveRoundState?.holeState(for: hole.number) else {
                return nil
            }
            return (hole, state)
        }
    }

    private var completedHoleScores: [Int: LiveHoleScore] {
        Dictionary(uniqueKeysWithValues: completedHoleStates.map { entry in
            (entry.hole.number, LiveHoleScore(
                hole: entry.hole.number,
                par: entry.hole.par,
                score: entry.state.score,
                putts: entry.state.putts,
                penalties: entry.state.penaltyCount,
                fairway: entry.state.fairwayResult,
                source: entry.state.scoreSource
            ))
        })
    }

    private func presentPendingHistoricalScoreEdit() {
        guard let selectedHoleNumber = pendingHistoricalScoreHole else { return }
        pendingHistoricalScoreHole = nil
        guard let selectedHole = package.holes.first(where: { $0.number == selectedHoleNumber }) else {
            return
        }

        let restored = liveRoundState?.holeState(for: selectedHoleNumber)
        let draft = LiveScoreDraft(
            hole: selectedHoleNumber,
            par: selectedHole.par,
            savedScore: restored?.score ?? selectedHole.par,
            savedPutts: restored?.putts ?? 2,
            savedPenalty: restored?.penaltyCount ?? 0,
            savedFairway: restored?.fairwayResult.flatMap(LiveFairwayResult.init(rawValue:)),
            savedSource: restored?.scoreSource.flatMap(LiveScoreSource.init(rawValue:))
        )
        scoreDraft = draft
        if let offlineStore {
            try? offlineStore.saveLiveScoreDraft(roundId: package.roundId, draft: draft)
        }
    }

    private func nextHole(after number: Int) -> Int? {
        let ordered = package.holes.map(\.number)
        guard let index = ordered.firstIndex(of: number), ordered.indices.contains(index + 1) else {
            return nil
        }
        return ordered[index + 1]
    }

    /// B0 tee result: the second shot's position against the fairway outline (nil = no preselect:
    /// Par 3, no outline, no second shot, or a point that cannot be sided).
    private var liveTeeResultPreselection: LiveFairwayResult? {
        guard hole.par != 3,
              let prep = holePrep,
              let outline = prep.fairwayOutline,
              let offlineStore,
              let events = try? offlineStore.loadEvents() else { return nil }
        let shots = LiveMarkedShots.locations(in: events, roundId: package.roundId, hole: hole.number)
        guard shots.count >= 2,
              case .number(let latitude)? = shots[1].payload["latitude"],
              case .number(let longitude)? = shots[1].payload["longitude"] else { return nil }
        let route: [[Double]] = {
            guard let refs = prep.holeImageProjection?.refs,
                  let overlayRoute = prep.resolvedMapOverlay?.route else { return [] }
            return overlayRoute.compactMap { row -> [Double]? in
                guard row.count >= 2,
                      let point = WatchEventBridge.projectFromTopoPx(
                          px: row[0],
                          py: row[1],
                          refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
                      ) else { return nil }
                return [point.latitude, point.longitude]
            }
        }()
        return TeeResultClassifier.classify(
            point: [latitude, longitude],
            outline: outline,
            route: route,
            par: hole.par
        ).flatMap { LiveFairwayResult(rawValue: $0.rawValue) }
    }

    private var recordedNonPuttShotCount: Int {
        guard let offlineStore, let events = try? offlineStore.loadEvents() else { return 0 }
        return LiveMarkedShots.locations(in: events, roundId: package.roundId, hole: hole.number).count
    }

    private var actualClubChoices: [LiveActualClubChoice] {
        var choices = allBagClubs.map { club in
            LiveActualClubChoice(
                name: club.name,
                yards: CoursePrepRoute.yards(fromMetres: club.metres),
                isRecommended: club.name == recommendedClub
            )
        }
        if let recommendedClub, !choices.contains(where: { $0.name == recommendedClub }) {
            choices.insert(
                LiveActualClubChoice(name: recommendedClub, yards: nil, isRecommended: true),
                at: 0
            )
        }
        return choices
    }

    private func recordShotLocation() {
        guard let currentCoordinate = liveCoordinateForCurrentHole else { return }
        let shotOrder = recordedNonPuttShotCount + 1
        let builder = LiveRoundEventBuilder(roundId: package.roundId)
        let locationEvent = builder.makeLocationEvent(
            hole: hole.number,
            coordinate: currentCoordinate,
            horizontalAccuracyM: currentHorizontalAccuracyM,
            altitudeM: locationProvider.latestFix?.altitudeM,
            targetCoordinate: wireTargetCoordinate,
            targetKind: wireTargetKind
        )
        onEvent(locationEvent)
        pendingPhoneShot = PendingPhoneShot(locationEvent: locationEvent, shotOrder: shotOrder)
    }

    private func recordActualClub(_ club: String, for pendingShot: PendingPhoneShot) {
        let trimmedClub = club.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedClub.isEmpty else {
            pendingPhoneShot = nil
            return
        }
        #if DEBUG
        UITestEventLatencyTrace.record("actual-club.build.begin hole=\(hole.number)")
        #endif
        let event = LiveRoundEventBuilder(roundId: package.roundId).makeActualClubEvent(
            hole: hole.number,
            clubName: trimmedClub,
            sourceLocationEventId: pendingShot.locationEvent.eventId,
            shotOrder: pendingShot.shotOrder,
            shotType: selectedShotType,
            strategyMode: selectedStrategyMode,
            lie: selectedLie,
            distanceToPinM: effectiveDistanceToPinMetres,
            offlineOptionId: selectedOfflineOption?.optionId,
            decision: caddieDecision
        )
        #if DEBUG
        UITestEventLatencyTrace.record("actual-club.build.end hole=\(hole.number)")
        UITestEventLatencyTrace.record("actual-club.encode.begin hole=\(hole.number)")
        let encodedByteCount = (try? JSONEncoder().encode(event).count) ?? -1
        UITestEventLatencyTrace.record("actual-club.encode.end hole=\(hole.number) bytes=\(encodedByteCount)")
        UITestEventLatencyTrace.record("actual-club.handle.begin hole=\(hole.number)")
        #endif
        onEvent(event)
        #if DEBUG
        UITestEventLatencyTrace.record("actual-club.handle.end hole=\(hole.number)")
        #endif
        pendingPhoneShot = nil
        // The first recorded location is the opening tee shot. Subsequent advice must be based on
        // the new lie/remaining distance instead of re-running the tee plan with the same driver.
        if pendingShot.shotOrder == 1 {
            selectedShotType = "approach"
            selectedLie = "fairway"
            Task { await loadCaddieDecision(syncClub: !hasUserSelectedClub) }
        }
    }

    private func distanceToPinPayload() -> JSONValue {
        guard let metres = distanceToPinMetres else {
            return .null
        }
        return .number(metres)
    }

    private func emit(kind: LiveRoundEventKind, timestamp: String, payload: [String: JSONValue]) {
        onEvent(
            LiveRoundEvent(
                eventId: UUID().uuidString,
                roundId: package.roundId,
                timestamp: timestamp,
                hole: hole.number,
                kind: kind,
                payload: payload
            )
        )
    }

    /// 到旗杆距离在 UI 里以「码」输入/显示;后端事件/球童请求用米,这里在边界换算回米。
    private var distanceToPinMetres: Double? {
        guard let yards = Double(distanceToPinText.trimmingCharacters(in: .whitespacesAndNewlines)),
              yards.isFinite,
              yards > 0 else {
            return nil
        }
        let metres = CoursePrepRoute.metres(fromYards: yards)
        return metres <= GeoDistance.maximumUsefulGreenMetres ? metres : nil
    }

    /// One distance source for club relevance, backend planning, and Watch state. A player's manual
    /// target wins; otherwise use live GPS→green-middle, then the downloaded tee→middle fallback.
    private var effectiveDistanceToPinMetres: Double? {
        LiveCaddieDistance.resolve(
            manualM: distanceToPinMetres ?? mapTargetDistanceMetres ?? greenPinDistanceMetres,
            liveMiddleM: liveGreenMetres?.middle,
            staticMiddleM: liveGreenDistances?.middleM,
            holeYards: hole.yards
        )
    }

    private var liveCoordinateForCurrentHole: CLLocationCoordinate2D? {
        mapReferenceIsLive ? currentCoordinate : nil
    }

    /// 后端存的米 → 前端显示的整码(恢复已记距离时用)。
    private static func yardsText(fromMetres metres: Double) -> String {
        String(CoursePrepRoute.yards(fromMetres: metres))
    }

    private static func validDistanceText(_ metres: Double?) -> String {
        guard let metres,
              metres.isFinite,
              metres > 0,
              metres <= GeoDistance.maximumUsefulGreenMetres else { return "" }
        return yardsText(fromMetres: metres)
    }

    private static func normalizedSelectedClub(_ raw: String) -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, trimmed.lowercased() != "unknown" else { return "" }
        return zhClubName(trimmed)
    }

    /// Target semantics are shared by iPhone, Watch and the server event contract. `map_target` was
    /// emitted by an intermediate build; read it as a normal manual target so an upgrade does not
    /// strand the saved point, but never emit that legacy token again.
    private static func normalizedTargetKind(_ raw: String?) -> String? {
        switch raw?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "pin": return "pin"
        case "target", "map_target": return "target"
        case "green_center": return "green_center"
        default: return nil
        }
    }

    private static func restoredTarget(
        from state: LiveHoleStateSnapshot?
    ) -> (coordinate: CLLocationCoordinate2D, kind: String)? {
        guard let state,
              let latitude = state.targetLatitude,
              let longitude = state.targetLongitude,
              latitude.isFinite,
              longitude.isFinite,
              (-90...90).contains(latitude),
              (-180...180).contains(longitude),
              let kind = normalizedTargetKind(state.targetKind) else {
            return nil
        }
        return (
            CLLocationCoordinate2D(latitude: latitude, longitude: longitude),
            kind
        )
    }
}
