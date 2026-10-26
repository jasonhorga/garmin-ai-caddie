import AICaddieDomain
import CoreMotion
import SwiftUI
import WatchKit

@main
public struct AICaddieWatchApp: App {
    @Environment(\.scenePhase) private var scenePhase
    private struct NearbyCourseDiscoveryKey: Equatable {
        let config: WatchRoundConfig?
        let latitudeBucket: Int?
        let longitudeBucket: Int?
    }

    private struct RoundInPlayKey: Equatable {
        let roundId: String?
        let setAside: Bool
    }

    private struct ActiveCourseUpgradeKey: Equatable {
        /// Bumped to restart a paused upgrade when the app comes back to the front.
        let retryEpoch: Int
        let roundId: String
        let frontGlobalId: Int
        let loopKey: String?
        let teeBox: String?
        let config: WatchRoundConfig
    }

    @StateObject private var syncClient = WatchSyncClient()
    @StateObject private var roundModel = WatchRoundModel()
    @StateObject private var courseLibrary = WatchCourseLibrary()
    // watch P3: the watch's own GPS — recomputes you/green distances from the wrist (less phone-dependence).
    @StateObject private var watchLocation = WatchLocationProvider()
    @StateObject private var autoShotProvider = WatchAutoShotProvider()
    @AppStorage("watch.gpsPreheatEnabled") private var gpsPreheatEnabled = true
    /// Sets a round left open aside so its workout session and GPS stop (battery report 2026-10-12).
    /// Checked once a minute with the newest wrist fix.
    @State private var roundIdleTracker = WatchRoundIdleTracker()
    /// Restarts a paused precise-map upgrade (`ActiveCourseUpgradeKey.retryEpoch`).
    @State private var courseUpgradeRetryEpoch = 0
    @State private var lastCourseUpgradeRestart = Date.distantPast
    /// B7 step 1 (实验): record swing candidates and their features; never changes a score.
    @AppStorage("watch.collectSwingFeatures") private var collectSwingFeatures = false
    private let swingCandidateStore = WatchSwingCandidateStore()
    /// Which round a candidate belongs to across a closure; a late candidate joins the closed round.
    @State private var swingRouter = WatchSwingCandidateRouter()
    @State private var swingUploadRetry: Task<Void, Never>?

    /// B7 capability/battery gate for the current round, and its battery reports (the baseline).
    @State private var swingGate: WatchSwingCollectionGate?
    @State private var swingCollectionAllowed = false
    /// Persists the gate across relaunches and closes each round's gate exactly once.
    private let swingGateLifecycle = WatchSwingGateLifecycle()

    /// Collection runs only while the player wants it and the round's gate allows it.
    private var collectingSwings: Bool { swingCollectionAllowed }

    private var swingCapability: WatchSwingCapability {
        WatchSwingCapability(
            provider: autoShotProvider.state,
            sensorsSupported: autoShotProvider.isSupported,
            motionPermissionDenied: CMBatchedSensorManager.authorizationStatus == .denied
                || CMBatchedSensorManager.authorizationStatus == .restricted
        )
    }

    /// The settings row's status; nil hides the row on a device that cannot collect at all.
    private var swingCollectionStatus: String? {
        guard autoShotProvider.isSupported else { return nil }
        return WatchSwingCollectionStatus.text(
            preference: collectSwingFeatures,
            roundActive: swingGate != nil,
            blocker: swingGate?.blocker(capability: swingCapability)
        )
    }

    public init() {}

    public var body: some Scene {
        WindowGroup {
            content
                // Keep the standalone round able to sync: adopt the backend config the phone delivers.
                .onChange(of: syncClient.config, initial: true) { _, newConfig in
                    roundModel.config = newConfig
                    if newConfig != nil {
                        Task { await roundModel.retryDeferredFinishes() }
                        Task { await uploadFinishedSwingCandidates() }
                    }
                }
                .onChange(of: syncClient.roundSeed, initial: true) { _, seed in
                    if let seed {
                        roundModel.applyRoundSeed(seed)
                    }
                }
                .onChange(of: syncClient.currentState, initial: true) { _, state in
                    if let state {
                        roundModel.receivePhoneState(state)
                    }
                }
                .onChange(of: syncClient.phoneRoundClosure, initial: true) { _, closure in
                    if let closure {
                        let closesActiveRound = roundModel.round?.roundId == closure.roundId
                        roundModel.applyPhoneRoundClosure(closure)
                        if closesActiveRound {
                            autoShotProvider.stop()
                            reconcileLocationServices()
                        }
                        // A phone Finish/Discard hands the closed round to the candidate uploader.
                        closeSwingRound(closure.roundId)
                        closeSwingGate(roundId: closure.roundId)
                    }
                }
                .onChange(of: roundModel.lastRoundClosure) { _, closure in
                    guard let closure else { return }
                    closeSwingGate(roundId: closure.roundId)
                    try? syncClient.forgetRound(
                        roundId: closure.roundId,
                        // Standalone Finish proves only the standalone event store reached the
                        // backend. A pre-upgrade WCSession relay tail remains durable until it is
                        // uploaded; only explicit Abandon is destructive across both stores.
                        discardQueuedEvents: closure.disposition == .abandoned
                    )
                    syncClient.sendRoundClosureToPhone(closure)
                    if roundModel.round == nil {
                        autoShotProvider.stop()
                        reconcileLocationServices()
                    }
                }
                .onChange(of: roundModel.autoShotEnabled, initial: true) { _, _ in
                    reconcileAutoShot()
                }
                .onChange(of: syncClient.phoneReachable) { _, reachable in
                    if reachable {
                        Task { await roundModel.retryDeferredFinishes() }
                        Task { await uploadFinishedSwingCandidates() }
                    }
                }
                .onChange(of: roundModel.round?.roundId, initial: true) { _, _ in
                    reconcileAutoShot()
                    reconcileLocationServices()
                }
                .onChange(of: roundModel.screen, initial: true) { _, screen in
                    reconcileAutoShot()
                    reconcileLocationServices()
                    watchLocation.setHeadingUpdates(screen == .flagDirection)
                    roundModel.noteInPlay()
                }
                .onChange(of: gpsPreheatEnabled, initial: true) { _, _ in
                    reconcileLocationServices()
                }
                .onChange(of: collectSwingFeatures) { _, _ in
                    refreshSwingGate()
                    reconcileAutoShot()
                }
                .onChange(of: autoShotProvider.state) { _, _ in refreshSwingGate() }
                .environment(\.watchSwingCollectionStatus, swingCollectionStatus)
                .task(id: roundModel.round?.roundId) {
                    // B7 battery budget: one reading a minute while a round is active.
                    guard roundModel.round != nil else { return }
                    let device = WKInterfaceDevice.current()
                    device.isBatteryMonitoringEnabled = true
                    while !Task.isCancelled {
                        if swingGate != nil {
                            swingGate?.record(WatchBatterySample(
                                at: Date(),
                                level: Double(device.batteryLevel),
                                charging: device.batteryState == .charging || device.batteryState == .full
                            ))
                            refreshSwingGate()
                        }
                        try? await Task.sleep(nanoseconds: 60_000_000_000)
                    }
                }
                .onChange(of: roundModel.round?.roundId, initial: true) { _, roundId in
                    rollSwingGate(to: roundId)
                    // A round that ended (or was replaced) uploads its candidates.
                    let closed = swingRouter.roundChanged(to: roundId, at: Date())
                    swingRouter.holeChanged(to: roundModel.activeHole, at: Date())
                    if closed != nil {
                        Task { await uploadFinishedSwingCandidates() }
                    }
                }
                .onChange(of: roundModel.activeHole) { _, hole in
                    swingRouter.holeChanged(to: hole, at: Date())
                }
                .onChange(of: watchLocation.latestFix) { _, fix in
                    autoShotProvider.updateSpeed(fix)
                }
                .task(id: RoundInPlayKey(roundId: roundModel.round?.roundId, setAside: roundModel.screen == .resume)) {
                    // A plain task, not onChange: it keeps running in the background while the
                    // workout keeps the app alive. Each round in play (and each resume) starts fresh.
                    roundIdleTracker.reset()
                    guard roundModel.round != nil, roundModel.screen != .resume else { return }
                    while !Task.isCancelled {
                        roundModel.noteInPlay()
                        pauseRoundIfIdle(watchLocation.latestFix)
                        try? await Task.sleep(nanoseconds: 60_000_000_000)
                    }
                }
                .onChange(of: autoShotProvider.latestSwing) { _, observation in
                    // The round and hole in play when the motion ended, even if it is delivered
                    // after that round closed or the next one started.
                    guard collectingSwings, let observation,
                          let assignment = swingRouter.assignment(forMotionAt: observation.observedAt) else { return }
                    let roundId = assignment.roundId
                    swingCandidateStore.append(
                        WatchSwingCandidateRecord(
                            capturedAt: ISO8601DateFormatter().string(from: observation.observedAt),
                            hole: assignment.hole,
                            features: observation.features,
                            horizontalAccuracyM: watchLocation.latestFix?.horizontalAccuracyM,
                            speedMps: observation.speedMps,
                            proposedShot: observation.proposedShot
                        ),
                        roundId: roundId
                    )
                    if roundId != swingRouter.activeRoundId {
                        // Settled just after its round closed: upload with that round.
                        Task { await uploadFinishedSwingCandidates() }
                    }
                }
                .onChange(of: qualifiedWatchFix?.capturedAt) { _, _ in
                    // B6 洞结束: walking off the green toward the next tee opens 本洞成绩.
                    guard let fix = qualifiedWatchFix else { return }
                    if roundModel.observeLocation(
                        latitude: fix.coordinate.latitude,
                        longitude: fix.coordinate.longitude,
                        horizontalAccuracyM: fix.horizontalAccuracyM
                    ) {
                        WKInterfaceDevice.current().play(.notification)
                    }
                }
                .onChange(of: autoShotProvider.latestSignal) { _, signal in
                    // AutoShot records a durable GPS origin, so it must obey the same live-fix
                    // contract as manual shots and F/M/B instead of accepting a cached coarse sample.
                    guard signal != nil, let fix = qualifiedWatchFix else { return }
                    if roundModel.proposeAutoShotCandidate(
                        latitude: fix.coordinate.latitude,
                        longitude: fix.coordinate.longitude,
                        horizontalAccuracyM: fix.horizontalAccuracyM,
                        capturedAt: fix.capturedAt
                    ) {
                        WKInterfaceDevice.current().play(.notification)
                    }
                }
                .onAppear {
                    // The turn (B4b-2 §7) resolves round holes 10–18 through the course library:
                    // the ordered package online, else the installed whole-course template.
                    roundModel.secondLoopLoader = { [courseLibrary, syncClient] request in
                        await courseLibrary.secondLoop(request, config: syncClient.config)
                    }
                    roundModel.onRoundTableChanged = { [syncClient] start in
                        syncClient.sendRoundStart(start)
                    }
                    // An A / B / C venue's loops for its turn, named by the course's own loop label.
                    roundModel.nineLoopSiblings = { [courseLibrary] globalId in
                        courseLibrary.nineLoopSiblings(of: globalId).map { option in
                            NineLoop(id: "\(option.globalId):all", name: option.resolvedSegmentLabel ?? option.name)
                        }
                    }
                    reconcileLocationServices()
                    syncClient.requestConfigurationFromPhone()
                    Task { await roundModel.retryDeferredFinishes() }
                }
                .onChange(of: scenePhase) { _, phase in
                    reconcileLocationServices()
                    guard phase == .active else { return }
                    // A map upgrade that ran out of retries (a cold course still being drawn on the
                    // server) starts again when the golfer looks at the Watch.
                    // At most every five minutes: a wrist raise is not a reason to start over.
                    if courseLibrary.preciseUpgradePaused, roundModel.round != nil,
                       Date().timeIntervalSince(lastCourseUpgradeRestart) >= 5 * 60 {
                        lastCourseUpgradeRestart = Date()
                        courseUpgradeRetryEpoch += 1
                    }
                    syncClient.requestConfigurationFromPhone()
                    Task { await roundModel.retryDeferredFinishes() }
                    Task { await uploadFinishedSwingCandidates() }
                }
        }
    }

    @ViewBuilder
    private var content: some View {
#if DEBUG
        if let uitestScreen = WatchUITestRoot.requestedScreen() {
            // `simctl launch ... -uitest-screen <name>`: render the real view with demo data so
            // `simctl io screenshot` captures it (watchOS has no XCUITest). DEBUG-only.
            WatchUITestRoot(screen: uitestScreen, model: roundModel)
        } else {
            standardContent
        }
#else
        standardContent
#endif
    }

    @ViewBuilder
    private var standardContent: some View {
        Group {
            if roundModel.round != nil {
                // round-12 P3.3: a standalone round in progress takes over the whole watch.
                // watch P1b: pass the active hole's map geometry (topo image + anchors). Recomputed every
                // render — a @Published change on syncClient (incl. lastHoleImageKey when the image lands)
                // re-renders this body, so the 「球道图」 entry appears as soon as the topo transfer completes.
                WatchRoundContainerView(
                    model: roundModel,
                    holeGeometry: activeHoleGeometry,
                    watchGreenYards: watchGreenYards,
                    shotLocation: qualifiedWatchFix,
                    latestWatchFix: watchLocation.latestFix,
                    watchHeading: watchLocation.latestHeading,
                    autoShotSupported: autoShotProvider.isSupported,
                    autoShotStatus: autoShotProvider.state.menuDetail
                )
            } else {
                WatchStartView(
                    phoneReachable: syncClient.phoneReachable,
                    // The picker decides which rows are nearby. Keep the complete small library here
                    // as well so a precise offline course remains startable when the wrist has no
                    // qualified GPS fix (or the player is still far from the venue).
                    courses: courseLibrary.courses,
                    nearbyCourses: courseLibrary.nearbyCourses,
                    searchMatches: courseLibrary.searchMatches,
                    cachedCourseIds: courseLibrary.cachedCourseIds,
                    isLoadingCourses: courseLibrary.isLoadingNearby,
                    discoveryState: courseLibrary.discoveryState,
                    isSearchingCourses: courseLibrary.isSearchingCourses,
                    preparingCourseId: courseLibrary.preparingCourseId,
                    errorMessage: courseLibrary.errorMessage,
                    // A stale/coarse fix must not be treated as a nearby-course location. The same
                    // quality gate used by the live rangefinder lets the picker fall back to precise
                    // offline courses while satellites are still acquiring.
                    currentLatitude: qualifiedWatchFix?.coordinate.latitude,
                    currentLongitude: qualifiedWatchFix?.coordinate.longitude,
                    onRefresh: {
                        Task {
                            if let fix = qualifiedWatchFix {
                                await courseLibrary.refreshNearby(
                                    latitude: fix.coordinate.latitude,
                                    longitude: fix.coordinate.longitude,
                                    config: syncClient.config
                                )
                            }
                        }
                    },
                    onSearchAllCourses: { name in
                        Task {
                            await courseLibrary.searchAllCourses(
                                name: name,
                                config: syncClient.config
                            )
                        }
                    },
                    onLoadCourseTees: { globalId in
                        await courseLibrary.loadCourseTees(
                            globalId: globalId,
                            config: syncClient.config
                        )
                    },
                    onStartCourse: { selection in
                        // The provisional round is created synchronously. Once the first tap seeds
                        // it, a second tap must not create a different roundId while the setup view
                        // is animating away.
                        guard roundModel.round == nil else { return }
                        // A round is created locally before any package request. This mirrors the
                        // S70 cold-start behavior: no GPS or network spinner can erase the start
                        // fact. `activeCourseUpgradeKey` then upgrades this same round in place.
                        // Fails closed: a malformed selection or an unpersistable provisional
                        // template leaves the setup on screen with the library's error message.
                        guard let prepared = courseLibrary.startCourseImmediately(selection) else {
                            return
                        }
                        roundModel.seedRound(
                            prepared.holeStates,
                            activeHole: prepared.holeStates.first?.hole,
                            courseName: prepared.courseName,
                            courseGlobalId: selection.front.globalId,
                            teeBox: selection.teeBox,
                            loopKey: selection.loopKey
                        )
                        syncClient.sendRoundStart(
                            WatchRoundStart.watchStarted(prepared, selection: selection)
                        )
                    }
                )
            }
        }
        .task(id: nearbyCourseDiscoveryKey) {
            guard nearbyCourseDiscoveryKey != nil,
                  let fix = qualifiedWatchFix else { return }
            await courseLibrary.refreshNearby(
                latitude: fix.coordinate.latitude,
                longitude: fix.coordinate.longitude,
                config: syncClient.config
            )
        }
        .task(id: activeCourseUpgradeKey) {
            guard let key = activeCourseUpgradeKey,
                  let upgraded = await courseLibrary.upgradeCachedCourseWhenReady(
                    globalId: key.frontGlobalId,
                    roundId: key.roundId,
                    config: key.config,
                    loopKey: key.loopKey,
                    teeBox: key.teeBox,
                    priorityHole: roundModel.activeHole,
                    onProgress: { states in
                        guard roundModel.round?.roundId == key.roundId else { return }
                        roundModel.applyCourseMapUpgrade(states)
                    }
                  ),
                  roundModel.round?.roundId == key.roundId else {
                return
            }
            roundModel.applyCourseMapUpgrade(upgraded.holeStates)
        }
        .task(id: activeGreenDetailKey) {
            guard roundModel.screen == .viewGreen,
                  let state = roundModel.activeHoleState else { return }
            await courseLibrary.loadGreenDetailIfNeeded(
                for: state,
                config: syncClient.config
            )
        }
    }

    private var nearbyCourseDiscoveryKey: NearbyCourseDiscoveryKey? {
        // Nearby discovery belongs only to the start surface. Letting the 11-metre location bucket
        // keep firing through an active round wastes Watch battery and backend work.
        guard roundModel.round == nil else { return nil }
        guard let coordinate = qualifiedWatchFix?.coordinate else {
            return NearbyCourseDiscoveryKey(
                config: syncClient.config,
                latitudeBucket: nil,
                longitudeBucket: nil
            )
        }
        return NearbyCourseDiscoveryKey(
            config: syncClient.config,
            latitudeBucket: Int((coordinate.latitude * 10_000).rounded()),
            longitudeBucket: Int((coordinate.longitude * 10_000).rounded())
        )
    }

    private var activeCourseUpgradeKey: ActiveCourseUpgradeKey? {
        guard let round = roundModel.round,
              let frontGlobalId = round.courseGlobalId
                ?? round.holeStates.first(where: { $0.hole == round.activeHole })?.globalId
                ?? round.holeStates.compactMap(\.globalId).first,
              let config = syncClient.config else {
            return nil
        }
        return ActiveCourseUpgradeKey(
            retryEpoch: courseUpgradeRetryEpoch,
            roundId: round.roundId,
            frontGlobalId: frontGlobalId,
            loopKey: round.loopKey,
            teeBox: round.teeBox,
            config: config
        )
    }

    private var activeGreenDetailKey: String? {
        guard roundModel.screen == .viewGreen,
              let state = roundModel.activeHoleState,
              let globalId = state.globalId else { return nil }
        return "\(roundModel.round?.roundId ?? "-"):\(globalId):\(state.hole):\(state.geometryRevision ?? "-")"
    }

    /// A closure the router has not seen yet (phone Finish racing the round-ID change).
    private func closeSwingRound(_ roundId: String) {
        if swingRouter.activeRoundId == roundId {
            swingRouter.roundChanged(to: roundModel.round?.roundId, at: Date())
        }
        Task { await uploadFinishedSwingCandidates() }
    }

    /// B7 step 1: candidates of rounds that are no longer active go up with their features only. A
    /// failed upload stays on the Watch and is retried on config, reachability, closure, launch and
    /// a backoff while the app stays alive.
    private func uploadFinishedSwingCandidates(attempt: Int = 0) async {
        guard let config = syncClient.config else { return }
        let client = WatchBackendClient(
            baseURL: config.baseURL,
            adminToken: config.adminToken,
            sessionToken: config.sessionToken,
            sessionTokenExpiresAt: config.sessionTokenExpiresAt
        )
        let outcome = await WatchSwingCandidateUploader(store: swingCandidateStore).uploadClosedRounds(
            activeRoundId: swingRouter.activeRoundId
        ) { roundId, candidates in
            try await client.uploadSwingCandidates(roundId: roundId, candidates: candidates)
        }
        guard !outcome.failed.isEmpty else { return }
        let delays = WatchSwingCandidateUploader.retryDelaysS
        guard attempt < delays.count else { return }
        swingUploadRetry?.cancel()
        swingUploadRetry = Task {
            try? await Task.sleep(nanoseconds: UInt64(delays[attempt] * 1_000_000_000))
            guard !Task.isCancelled else { return }
            await uploadFinishedSwingCandidates(attempt: attempt + 1)
        }
    }

    /// A round change closes the previous round's gate (its battery report becomes evidence, and the
    /// baseline when it did not collect) and opens or restores one for the new round.
    private func rollSwingGate(to roundId: String?) {
        let now = Date()
        if let gate = swingGate, gate.roundId != roundId {
            swingGateLifecycle.close(roundId: gate.roundId, gate: gate, at: now)
            swingGate = nil
        }
        if let roundId, swingGate == nil {
            swingGate = swingGateLifecycle.open(roundId: roundId, at: now)
        }
        refreshSwingGate()
    }

    /// A logical closure (Watch or phone Finish/Discard) closes the gate even when the round stays
    /// visible for a deferred upload.
    private func closeSwingGate(roundId: String) {
        swingGateLifecycle.close(roundId: roundId, gate: swingGate, at: Date())
        if swingGate?.roundId == roundId { swingGate = nil }
        refreshSwingGate()
    }

    /// Re-evaluates the gate; a change turns the motion collection on or off.
    private func refreshSwingGate() {
        let capability = swingCapability
        let allowed = swingGate?.allowsCollection(preference: collectSwingFeatures, capability: capability) ?? false
        if let swingGate { swingGateLifecycle.save(swingGate) }
        guard allowed != swingCollectionAllowed else { return }
        swingCollectionAllowed = allowed
        reconcileAutoShot()
    }

    private func reconcileAutoShot() {
        let keepWorkoutActive = WatchLocationLaunchPolicy.shouldKeepRoundWorkoutSession(
            hasActiveRound: roundModel.round != nil && roundModel.screen != .resume
        )
        Task {
            await autoShotProvider.reconcile(
                roundActive: keepWorkoutActive,
                autoShotEnabled: keepWorkoutActive && roundModel.autoShotEnabled,
                collectSwingFeatures: keepWorkoutActive && collectingSwings
            )
        }
    }

    private func pauseRoundIfIdle(_ fix: WatchLocationFix?) {
        guard roundModel.round != nil, roundModel.screen != .resume else { return }
        if roundIdleTracker.evaluate(
            latitude: fix?.coordinate.latitude,
            longitude: fix?.coordinate.longitude,
            horizontalAccuracyM: fix?.horizontalAccuracyM ?? .infinity,
            at: Date(),
            holePoints: roundModel.roundHolePoints,
            lastActivityAt: roundModel.lastActivityAt,
            scoredHoles: roundModel.scoredHoles,
            // A nine can go on to the next nine (the turn, often over lunch); only a full round
            // is finished. A nine left open is still set aside by the other two rules.
            allHolesScored: roundModel.allPlannedHolesScored && roundModel.holeCount > 9
        ) != nil, roundModel.pauseForIdle() {
            roundIdleTracker.reset()
            // Directly, not via onChange: this can run while the app is in the background.
            reconcileAutoShot()
            reconcileLocationServices()
        }
    }

    /// `GPS 预热` keeps a fix warm while choosing a course. Once a round begins, location is always
    /// on because the rangefinder and shot positions must not be silently disabled by a setup preference.
    private func reconcileLocationServices() {
        let setAside = roundModel.round != nil && roundModel.screen == .resume
        if WatchLocationLaunchPolicy.shouldStartLocationServices(
            // A set-aside round (resume screen) is not playing. The setup preheat warms GPS there
            // only while the player is looking, not for a round set aside in a pocket.
            hasActiveRound: roundModel.round != nil && !setAside,
            // The live state: the minute task runs on an App copy whose scenePhase can be stale.
            gpsPreheatEnabled: gpsPreheatEnabled
                && !(setAside && WKApplication.shared().applicationState != .active)
        ) {
            watchLocation.requestAuthorization()
            watchLocation.startUpdatingLocation()
        } else {
            watchLocation.stopUpdatingLocation()
        }
    }

    /// The active hole uses a cached precise bitmap when present and otherwise keeps the factual
    /// CourseView vectors visible while the same course/hole upgrades in place.
    private var activeHoleGeometry: WatchHoleMapGeometry? {
        guard let s = roundModel.activeHoleState, let hm = s.holeMap else { return nil }
        let img = s.globalId.flatMap { gid in
            syncClient.holeImageStore.image(
                globalId: gid,
                hole: s.hole,
                geometryRevision: s.geometryRevision
            )
        }
        let greenDetail = s.globalId.flatMap { gid in
            syncClient.holeImageStore.image(
                globalId: gid,
                hole: s.hole,
                geometryRevision: s.geometryRevision,
                detail: true
            )
        }
        guard let geo = WatchHoleMapGeometry.from(
            holeMap: hm,
            image: img,
            hazards: s.hazards,
            greenDetailImage: greenDetail
        ) else { return nil }
        // watch P3: if the watch has its OWN fix + this hole's projection refs, place YOU from the wrist GPS
        // (else keep the phone-pushed you = tee/phone-GPS). Pin/lay-up/route anchors are unchanged.
        if let fix = qualifiedWatchFix, let refs = s.holeImageProjection?.refs,
           let px = WatchGeoMath.projectToTopoPx(lat: fix.coordinate.latitude, lon: fix.coordinate.longitude, refs: refs) {
            return geo.withYou(px)
        }
        return geo
    }

    /// A cold or coarse Core Location sample is not yet a rangefinder fix. Fifteen metres matches the
    /// existing live-caddie accuracy gate; until then the Hole Root stays on the frozen 搜星 state.
    private var qualifiedWatchFix: WatchLocationFix? {
        guard let fix = watchLocation.latestFix,
              WatchLocationProvider.isLiveRangefinderFix(fix) else {
            return nil
        }
        return fix
    }

    /// F/M/B uses the package's selected Tee before the opening shot and the Watch's own
    /// qualified GPS afterwards. The container retains its existing acquiring/score-only gates.
    private var watchGreenYards: (front: Int?, center: Int?, back: Int?)? {
        guard let s = roundModel.activeHoleState else { return nil }
        let fix = qualifiedWatchFix
        let origin = GreenRangeOrigin.resolve(
            recordedShotCount: roundModel.recordedShotCount,
            isPreparing: false,
            hasQualifiedFix: fix != nil
        )
        let c: (latitude: Double, longitude: Double)
        switch origin {
        case .tee:
            // These are the same package coordinates used by the existing Tee distance arc.
            guard let latitude = s.teeLatitude, let longitude = s.teeLongitude,
                  latitude.isFinite, (-90...90).contains(latitude),
                  longitude.isFinite, (-180...180).contains(longitude) else { return nil }
            c = (latitude, longitude)
        case .liveGPS:
            guard let fix else { return nil }
            c = (fix.coordinate.latitude, fix.coordinate.longitude)
        case .fallback:
            return nil
        }
        let front = WatchGeoMath.yards(from: c.latitude, c.longitude, toLat: s.frontGreenLat, s.frontGreenLon)
        let center = WatchGeoMath.yards(from: c.latitude, c.longitude, toLat: s.centerGreenLat, s.centerGreenLon)
        let back = WatchGeoMath.yards(from: c.latitude, c.longitude, toLat: s.backGreenLat, s.backGreenLon)
        guard front != nil || center != nil || back != nil else { return nil }
        return (front, center, back)
    }
}

public enum WatchLocationLaunchPolicy {
    public static func shouldStartLocationServices(
        hasActiveRound: Bool = true,
        gpsPreheatEnabled: Bool = true,
        arguments: [String] = ProcessInfo.processInfo.arguments
    ) -> Bool {
#if DEBUG
        guard let index = arguments.firstIndex(of: "-uitest-screen"), index + 1 < arguments.count else {
            return hasActiveRound || gpsPreheatEnabled
        }
        return false
#else
        return hasActiveRound || gpsPreheatEnabled
#endif
    }

    /// A real active round keeps one golf workout session alive so wrist GPS and AutoShot can
    /// continue after the display sleeps. Deterministic simulator launches inject GPS or render a
    /// named screenshot and must not open Health authorization UI they cannot meaningfully test.
    public static func shouldKeepRoundWorkoutSession(
        hasActiveRound: Bool = true,
        arguments: [String] = ProcessInfo.processInfo.arguments,
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> Bool {
#if DEBUG
        if arguments.contains("-uitest-screen")
            || (environment["UITEST_GPS_LAT"] != nil && environment["UITEST_GPS_LON"] != nil) {
            return false
        }
#endif
        return hasActiveRound
    }
}
