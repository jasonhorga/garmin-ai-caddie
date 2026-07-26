import SwiftUI

@main
public struct AICaddieWatchApp: App {
    @StateObject private var syncClient = WatchSyncClient()
    @StateObject private var roundModel = WatchRoundModel()
    // watch P3: the watch's own GPS — recomputes you/green distances from the wrist (less phone-dependence).
    @StateObject private var watchLocation = WatchLocationProvider()

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
                .onAppear {
                    if WatchLocationLaunchPolicy.shouldStartLocationServices() {
                        watchLocation.requestAuthorization()
                        watchLocation.startUpdatingLocation()
                    }
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
        if roundModel.round != nil {
            // round-12 P3.3: a standalone round in progress takes over the whole watch.
            // watch P1b: pass the active hole's map geometry (topo image + anchors). Recomputed every
            // render — a @Published change on syncClient (incl. lastHoleImageKey when the image lands)
            // re-renders this body, so the 「球道图」 entry appears as soon as the topo transfer completes.
            WatchRoundContainerView(
                model: roundModel,
                holeGeometry: activeHoleGeometry,
                watchGreenYards: watchGreenYards,
                shotLocation: watchLocation.latestFix
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
                onStartPractice: { roundModel.startPracticeRound() }
            )
        }
    }

    private func sendQuickInputEvent(_ event: WatchInputEvent) {
        try? syncClient.sendQuickInputEvent(event)
    }

    /// watch P1b: the active hole's render geometry — the phone-pushed overlay anchors (`holeMap`) + the
    /// cached /topo.png. nil until both arrive, so the map entry stays hidden and we fall back to the hub.
    private var activeHoleGeometry: WatchHoleMapGeometry? {
        guard let s = roundModel.activeHoleState, let hm = s.holeMap, let gid = s.globalId else { return nil }
        let img = syncClient.holeImageStore.image(globalId: gid, hole: s.hole)
        guard let geo = WatchHoleMapGeometry.from(holeMap: hm, image: img) else { return nil }
        // watch P3: if the watch has its OWN fix + this hole's projection refs, place YOU from the wrist GPS
        // (else keep the phone-pushed you = tee/phone-GPS). Pin/lay-up/route anchors are unchanged.
        if let fix = watchLocation.latestFix, let refs = s.holeImageProjection?.refs,
           let px = WatchGeoMath.projectToTopoPx(lat: fix.coordinate.latitude, lon: fix.coordinate.longitude, refs: refs) {
            return geo.withYou(px)
        }
        return geo
    }

    /// watch P3: front/center/back green distances (码) recomputed from the watch's OWN fix + the hole's
    /// green coordinates. nil when there is no fix / no green coords → the container keeps the phone values.
    private var watchGreenYards: (front: Int?, center: Int?, back: Int?)? {
        guard let s = roundModel.activeHoleState, let fix = watchLocation.latestFix else { return nil }
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
        arguments: [String] = ProcessInfo.processInfo.arguments
    ) -> Bool {
#if DEBUG
        guard let index = arguments.firstIndex(of: "-uitest-screen"), index + 1 < arguments.count else {
            return true
        }
        return false
#else
        return true
#endif
    }
}
