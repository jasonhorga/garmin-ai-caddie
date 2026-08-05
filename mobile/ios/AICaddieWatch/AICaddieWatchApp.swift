import SwiftUI
import WatchKit

@main
public struct AICaddieWatchApp: App {
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
                .onChange(of: roundModel.autoShotEnabled, initial: true) { _, _ in
                    reconcileAutoShot()
                }
                .onChange(of: roundModel.round?.roundId, initial: true) { _, _ in
                    reconcileAutoShot()
                    reconcileLocationServices()
                }
                .onChange(of: gpsPreheatEnabled, initial: true) { _, _ in
                    reconcileLocationServices()
                }
                .onChange(of: autoShotProvider.latestSignal) { _, signal in
                    guard signal != nil, let fix = watchLocation.latestFix else { return }
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
            } else if let state = syncClient.currentState {
                // phone-coordinated companion glance (legacy single-hole push).
                WatchHoleView(
                    state: state,
                    clubs: state.availableClubNames,
                    queuedEventCount: syncClient.queuedEventCount,
                    phoneReachable: syncClient.phoneReachable,
                    lastPhoneAcceptedAt: syncClient.lastPhoneAcceptedAt,
                    onEvent: sendQuickInputEvent
                )
            } else {
                WatchStartView(
                    phoneReachable: syncClient.phoneReachable,
                    courses: courseLibrary.courses,
                    searchMatches: courseLibrary.searchMatches,
                    cachedCourseIds: courseLibrary.cachedCourseIds,
                    isLoadingCourses: courseLibrary.isLoadingCourses,
                    isSearchingCourses: courseLibrary.isSearchingCourses,
                    preparingCourseId: courseLibrary.preparingCourseId,
                    errorMessage: courseLibrary.errorMessage,
                    currentLatitude: watchLocation.latestFix?.coordinate.latitude,
                    currentLongitude: watchLocation.latestFix?.coordinate.longitude,
                    onRefresh: {
                        Task { await courseLibrary.refresh(config: syncClient.config) }
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
                        Task {
                            guard let prepared = await courseLibrary.startCourse(
                                selection,
                                config: syncClient.config
                            ) else { return }
                            roundModel.seedRound(
                                prepared.holeStates,
                                activeHole: prepared.holeStates.first?.hole,
                                courseName: prepared.courseName
                            )
                            if prepared.holeStates.contains(where: {
                                $0.geometryCoverage?.caseInsensitiveCompare("ready") != .orderedSame
                            }), let upgraded = await courseLibrary.upgradeCourseWhenReady(
                                selection,
                                roundId: prepared.roundId,
                                config: syncClient.config
                            ) {
                                roundModel.applyCourseMapUpgrade(upgraded.holeStates)
                            }
                        }
                    }
                )
            }
        }
        .task(id: syncClient.config) {
            await courseLibrary.refresh(config: syncClient.config)
        }
    }

    private func sendQuickInputEvent(_ event: WatchInputEvent) {
        try? syncClient.sendQuickInputEvent(event)
    }

    private func reconcileAutoShot() {
        if roundModel.round != nil, roundModel.autoShotEnabled {
            Task { await autoShotProvider.start() }
        } else {
            autoShotProvider.stop()
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
        guard let s = roundModel.activeHoleState, let hm = s.holeMap, let gid = s.globalId else { return nil }
        let img = syncClient.holeImageStore.image(globalId: gid, hole: s.hole)
        guard let geo = WatchHoleMapGeometry.from(
            holeMap: hm,
            image: img,
            hazards: s.hazards
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
              fix.coordinate.latitude.isFinite,
              (-90...90).contains(fix.coordinate.latitude),
              fix.coordinate.longitude.isFinite,
              (-180...180).contains(fix.coordinate.longitude),
              fix.horizontalAccuracyM.isFinite,
              (0...15).contains(fix.horizontalAccuracyM) else {
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
}
