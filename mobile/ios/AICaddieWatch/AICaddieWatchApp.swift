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

    private struct ActiveCourseUpgradeKey: Equatable {
        let roundId: String
        let globalId: Int
        let config: WatchRoundConfig
    }

    @StateObject private var syncClient = WatchSyncClient()
    @StateObject private var roundModel = WatchRoundModel()
    @StateObject private var courseLibrary = WatchCourseLibrary()
    // watch P3: the watch's own GPS — recomputes you/green distances from the wrist (less phone-dependence).
    @StateObject private var watchLocation = WatchLocationProvider()
    @StateObject private var autoShotProvider = WatchAutoShotProvider()
    @AppStorage("watch.gpsPreheatEnabled") private var gpsPreheatEnabled = true

    public init() {}

    public var body: some Scene {
        WindowGroup {
            content
                // Keep the standalone round able to sync: adopt the backend config the phone delivers.
                .onChange(of: syncClient.config, initial: true) { _, newConfig in
                    roundModel.config = newConfig
                    if newConfig != nil {
                        Task { await roundModel.retryDeferredFinishes() }
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
                    }
                }
                .onChange(of: roundModel.lastRoundClosure) { _, closure in
                    guard let closure else { return }
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
                    }
                }
                .onChange(of: roundModel.round?.roundId, initial: true) { _, _ in
                    reconcileAutoShot()
                    reconcileLocationServices()
                }
                .onChange(of: roundModel.screen, initial: true) { _, _ in
                    reconcileAutoShot()
                }
                .onChange(of: gpsPreheatEnabled, initial: true) { _, _ in
                    reconcileLocationServices()
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
                    reconcileLocationServices()
                    syncClient.requestConfigurationFromPhone()
                    Task { await roundModel.retryDeferredFinishes() }
                }
                .onChange(of: scenePhase) { _, phase in
                    guard phase == .active else { return }
                    syncClient.requestConfigurationFromPhone()
                    reconcileLocationServices()
                    Task { await roundModel.retryDeferredFinishes() }
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
                        let prepared = courseLibrary.startCourseImmediately(selection)
                        roundModel.seedRound(
                            prepared.holeStates,
                            activeHole: prepared.holeStates.first?.hole,
                            courseName: prepared.courseName
                        )
                        syncClient.sendRoundStart(
                            WatchRoundStart(
                                roundId: prepared.roundId,
                                courseName: prepared.courseName,
                                teeBox: selection.teeBox,
                                nine: "all",
                                globalId: selection.front.globalId,
                                backGlobalId: selection.back?.globalId,
                                activeHole: prepared.holeStates.first?.hole ?? 1,
                                holes: prepared.holeStates.map { state in
                                    WatchRoundSeedHole(
                                        hole: state.hole,
                                        par: state.par,
                                        distanceM: state.distanceM,
                                        teeLatitude: state.teeLatitude,
                                        teeLongitude: state.teeLongitude,
                                        globalId: state.globalId
                                    )
                                }
                            )
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
                    globalId: key.globalId,
                    roundId: key.roundId,
                    config: key.config,
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
              let globalId = round.holeStates.first(where: { $0.hole == round.activeHole })?.globalId
                ?? round.holeStates.compactMap(\.globalId).first,
              let config = syncClient.config else {
            return nil
        }
        return ActiveCourseUpgradeKey(
            roundId: round.roundId,
            globalId: globalId,
            config: config
        )
    }

    private func reconcileAutoShot() {
        let keepWorkoutActive = WatchLocationLaunchPolicy.shouldKeepRoundWorkoutSession(
            hasActiveRound: roundModel.round != nil && roundModel.screen != .resume
        )
        Task {
            await autoShotProvider.reconcile(
                roundActive: keepWorkoutActive,
                autoShotEnabled: keepWorkoutActive && roundModel.autoShotEnabled
            )
        }
    }

    /// `GPS 预热` keeps a fix warm while choosing a course. Once a round begins, location is always
    /// on because the rangefinder and shot positions must not be silently disabled by a setup preference.
    private func reconcileLocationServices() {
        if WatchLocationLaunchPolicy.shouldStartLocationServices(
            hasActiveRound: roundModel.round != nil,
            gpsPreheatEnabled: gpsPreheatEnabled
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

    /// watch P3: front/center/back green distances (码) recomputed from the watch's OWN qualified fix +
    /// the hole's green coordinates. nil keeps the current-hole root in acquiring/score-only truth states.
    private var watchGreenYards: (front: Int?, center: Int?, back: Int?)? {
        guard let s = roundModel.activeHoleState, let fix = qualifiedWatchFix else { return nil }
        let c = fix.coordinate
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
