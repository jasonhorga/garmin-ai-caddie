import SwiftUI
import AICaddieDomain

/// The permanent current-hole surface. Geometry and distance availability select an honest visual
/// projection; they never change the scoring or shot state machine behind it.
public enum WatchHoleRootPresentation: Equatable {
    case acquiringGPS
    /// A round has a selected course, but its first factual map payload has not arrived yet. This is
    /// intentionally distinct from `scoreOnly`: starting a round should land on the map instrument,
    /// even when the map is still being transferred in the background.
    case mapPreparing
    case map
    case distances
    case scoreOnly

    public static func resolve(
        hasQualifiedWristFix: Bool,
        hasGeometry: Bool,
        hasLiveCenterDistance: Bool,
        courseDataPending: Bool = false
    ) -> Self {
        // GPS is a rangefinder input, not a round-entry gate. Keep the course map/score controls
        // usable during a cold fix (S70 shows 999 until location is ready); the caller supplies that
        // sentinel only for presentation and never fabricates a coordinate or shot fact.
        if hasGeometry { return .map }
        if courseDataPending { return .mapPreparing }
        if hasLiveCenterDistance { return .distances }
        return .scoreOnly
    }
}

/// Honest cold-GPS state for the current-hole root. Prepared Tee distances remain useful course facts,
/// but they are never presented as the player's current range while the Watch is still acquiring.
public struct WatchGPSAcquiringView: View {
    public init() {}

    public var body: some View {
        GeometryReader { proxy in
            let safeRect = WatchDisplayGeometry.contentRect(in: proxy.size)
            VStack(spacing: 3) {
                Text("999")
                    .font(.system(size: 68, weight: .black, design: .rounded))
                    .monospacedDigit()
                    .minimumScaleFactor(0.62)
                    .lineLimit(1)
                Text("等待定位")
                    .font(.system(size: 15, weight: .black))
                    .foregroundStyle(AICaddieDesignTokens.hudYellow)
                Text("定位完成后显示到果岭距离")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
            }
            .frame(width: safeRect.width, height: safeRect.height)
            .position(x: safeRect.midX, y: safeRect.midY)
        }
        .background(Color.black)
        .ignoresSafeArea()
        .accessibilityElement(children: .combine)
        .accessibilityLabel("999 码，等待定位")
    }
}

/// First-frame map instrument for a newly started round whose CourseView/topo facts are still being
/// downloaded. It deliberately avoids drawing a synthetic fairway: the only spatial content shown
/// before `WatchHoleMapGeometry` exists is the honest loading affordance. The course identity and
/// explicit 999 values make the transition from setup to play visible without blocking on GPS/network.
public struct WatchMapPreparingView: View {
    public let courseName: String
    public let hole: Int
    public let par: Int

    public init(courseName: String, hole: Int, par: Int) {
        self.courseName = courseName
        self.hole = hole
        self.par = par
    }

    public var body: some View {
        GeometryReader { proxy in
            let safeRect = WatchDisplayGeometry.contentRect(in: proxy.size)
            VStack(spacing: 8) {
                HStack(spacing: 6) {
                    Text("H\(hole) · P\(par)")
                        .font(.system(size: 17, weight: .black))
                        .lineLimit(1)
                        .minimumScaleFactor(0.65)
                    Spacer(minLength: 0)
                }
                .frame(width: safeRect.width, alignment: .leading)

                ZStack {
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .fill(Color(red: 0.08, green: 0.20, blue: 0.12))
                        .overlay {
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .stroke(Color.white.opacity(0.14), lineWidth: 1)
                        }
                    VStack(spacing: 7) {
                        Image(systemName: "map.fill")
                            .font(.system(size: 30, weight: .semibold))
                            .foregroundStyle(AICaddieDesignTokens.hudGreen)
                        ProgressView()
                            .tint(.white)
                        Text("地图准备中")
                            .font(.system(size: 13, weight: .black))
                            .foregroundStyle(.white)
                        Text(courseName)
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundStyle(.white.opacity(0.65))
                            .lineLimit(1)
                            .minimumScaleFactor(0.6)
                    }
                    .padding(.horizontal, 14)
                }
                .frame(width: safeRect.width, height: max(92, safeRect.height * 0.48))

                HStack(spacing: 9) {
                    range("前")
                    range("中")
                    range("后")
                }
                Text("可先记分，地图到达后自动显示")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.68)
            }
            .frame(width: safeRect.width, height: safeRect.height)
            .position(x: safeRect.midX, y: safeRect.midY)
        }
        .background(Color.black)
        .ignoresSafeArea()
        .accessibilityElement(children: .combine)
        .accessibilityLabel("第 \(hole) 洞，球场地图准备中，前中后距离 999 码")
        .accessibilityIdentifier("watch-map-preparing-root")
    }

    private func range(_ label: String) -> some View {
        VStack(spacing: 0) {
            Text("999")
                .font(.system(size: 22, weight: .black, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(.white)
            Text(label)
                .font(.system(size: 11, weight: .black))
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }
}

/// round-12 P3.3 (Watch standalone): the navigation shell that wires `WatchRoundModel` to the three
/// presentational screens. It maps the model's derived state into each view's props and routes the
/// views' callbacks back to the model — the model owns all state, this view owns none. Switching on
/// `model.screen` (rather than a NavigationStack) keeps each screen full-bleed on the small watch face.
public struct WatchRoundContainerView: View {
    @Environment(\.isLuminanceReduced) private var isLuminanceReduced
    @ObservedObject private var model: WatchRoundModel
    /// watch P1b: the active hole's render geometry (topo image + overlay anchors), built by the app from
    /// the pushed WatchHoleMap + cached /topo.png. nil ⇒ no map yet ⇒ the home 「球道图」 entry stays hidden.
    private let holeGeometry: WatchHoleMapGeometry?
    /// watch P1f (spec D1 大字模式): tap the hole view to blow the center distance up for arm's-length /
    /// bright-sun reading. Toggled on the .holeMap screen; the map + the no-geometry hero both honor it.
    @AppStorage("watch.bigTextMode") private var holeMapBigText = false
    @AppStorage("watch.gpsPreheatEnabled") private var gpsPreheatEnabled = true
    /// Map Detail owns the Crown. The resting position keeps the facts column and score ring; turning it
    /// enters the existing full-map presentation and continuously changes the real image transform.
    @State private var holeMapCrownScale: Double
    /// B6 本洞: 方案 / 障碍 / 果岭 pages, the 方案 page's Crown zoom + pan, and the plan the player
    /// picked by tapping the club tag (nil = the caddie's).
    @State private var holePage = 0
    @State private var planViewport = WatchHoleViewport()
    @State private var selectedPlanId: String?
    /// DEBUG compatibility and deep-linking only; production opens the nearest upcoming obstacle.
    private let initialHazardID: String?

    /// watch P3: F/M/B green distances (码) from the watch's OWN GPS; when present they override the
    /// phone-pushed static distances so the hole view is a live rangefinder even without the phone.
    private let watchGreenYards: (front: Int?, center: Int?, back: Int?)?
    /// Latest fix from the Watch itself. Manual shot capture is disabled until this exists; no
    /// placeholder coordinate is ever manufactured.
    private let shotLocation: WatchLocationFix?
    private let watchHeading: WatchHeadingFix?
    private let autoShotSupported: Bool
    private let autoShotStatus: String
    /// DEBUG runtime evidence may start Touch Target at a deterministic measured point. Production
    /// callers leave it nil, so live target state remains owned by WatchHoleMapView.
    private let measuredPxOverride: CGPoint?
    /// DEBUG runtime evidence for a user-moved View Green flag. Production starts at the canonical
    /// centre and lets the user's tap/drag update the same WatchGreenPreviewView state.
    private let initialGreenPinOverride: CGPoint?
    /// DEBUG runtime evidence may start View Green at the maximum Crown detent. Production callers
    /// leave this at 1 and the user owns every subsequent Crown change.
    private let initialGreenZoomScaleOverride: Double
    /// DEBUG-only paper-alignment evidence. Production restores the round-scoped saved rotation.
    private let initialGreenRotationOverride: Double?
    /// How long a detected shot can be undone (DEBUG runtime evidence holds it on screen).
    private let shotUndoSeconds: UInt64
    /// Review evidence of the production 本洞 pages: the hazard page's starting zoom / pan.
    private let initialHazardViewport: WatchHoleViewport

    public init(model: WatchRoundModel, holeGeometry: WatchHoleMapGeometry? = nil,
                watchGreenYards: (front: Int?, center: Int?, back: Int?)? = nil,
                shotLocation: WatchLocationFix? = nil,
                watchHeading: WatchHeadingFix? = nil,
                autoShotSupported: Bool = false,
                autoShotStatus: String = "本机不支持",
                initialHoleMapCrownScale: Double = WatchHoleMapView.restingCrownScale,
                initialSelectedHazardID: String? = nil,
                measuredPxOverride: CGPoint? = nil,
                initialGreenPinOverride: CGPoint? = nil,
                initialGreenZoomScaleOverride: Double = 1,
                initialGreenRotationOverride: Double? = nil,
                shotUndoSeconds: UInt64 = WatchRoundModel.shotUndoSeconds,
                initialHolePage: Int = 0,
                initialPlanViewport: WatchHoleViewport = WatchHoleViewport(),
                initialHazardViewport: WatchHoleViewport = WatchHoleViewport()) {
        self.model = model
        self.holeGeometry = holeGeometry
        self.watchGreenYards = watchGreenYards
        self.shotLocation = shotLocation
        self.watchHeading = watchHeading
        self.autoShotSupported = autoShotSupported
        self.autoShotStatus = autoShotStatus
        self.measuredPxOverride = measuredPxOverride
        self.initialGreenPinOverride = initialGreenPinOverride
        self.initialGreenZoomScaleOverride = initialGreenZoomScaleOverride
        self.initialGreenRotationOverride = initialGreenRotationOverride
        self.shotUndoSeconds = shotUndoSeconds
        self.initialHazardID = initialSelectedHazardID
        self._holeMapCrownScale = State(initialValue: initialHoleMapCrownScale)
        self._holePage = State(initialValue: min(max(initialHolePage, 0), 2))
        self._planViewport = State(initialValue: initialPlanViewport)
        self.initialHazardViewport = initialHazardViewport
    }

    // watch P3: effective F/M/B — the watch-GPS value when available, else the phone-pushed distance.
    static func effectiveGreenYards(live: Int?, fallbackMetres: Double?) -> Int? {
        live ?? fallbackMetres.map(WatchUnits.yards)
    }

    /// A complete F/M/B tuple can be supplied by the phone bridge or a deterministic UI fixture.
    /// Treat it as one coherent range fact; a partial tuple must never make one edge look live while
    /// the remaining edges are still unavailable.
    static func hasCompleteGreenRange(
        _ range: (front: Int?, center: Int?, back: Int?)?
    ) -> Bool {
        guard let range else { return false }
        return range.front != nil && range.center != nil && range.back != nil
    }

    static func rangeFixIsQualified(
        shotLocation: WatchLocationFix?,
        watchGreenYards: (front: Int?, center: Int?, back: Int?)?,
        now: Date = Date()
    ) -> Bool {
        // Bridged F/M/B values describe course/range facts, but cannot prove that the Watch has a
        // current position. S70-style cold start must keep the map interactive and show 999 until
        // a fresh, accurate wrist fix arrives.
        guard let shotLocation else { return false }
        return WatchLocationProvider.isLiveRangefinderFix(shotLocation, now: now)
    }

    /// Static phone-pushed green ranges are course facts, not a live rangefinder reading. They may
    /// calibrate the map only after a qualified wrist fix exists; otherwise callers must keep the
    /// distance unavailable and render the explicit acquiring state.
    static func canonicalCenterYards(
        live: Int?,
        fallbackMetres: Double?,
        hasQualifiedRangeFix: Bool
    ) -> Int? {
        guard hasQualifiedRangeFix else { return nil }
        return effectiveGreenYards(live: live, fallbackMetres: fallbackMetres)
    }

    private func frontYd(_ s: WatchRoundState) -> Int? {
        guard hasQualifiedRangeFix else { return 999 }
        return Self.effectiveGreenYards(live: watchGreenYards?.front, fallbackMetres: s.frontGreenM) ?? 999
    }

    private func canonicalCenterYd(_ s: WatchRoundState) -> Int? {
        Self.canonicalCenterYards(
            live: watchGreenYards?.center,
            fallbackMetres: s.centerGreenM,
            hasQualifiedRangeFix: hasQualifiedRangeFix
        )
    }

    private func selectedGreenPin(
        for state: WatchRoundState,
        geometry: WatchHoleMapGeometry
    ) -> CGPoint? {
        guard let placement = model.greenPlacement(forHole: state.hole, globalId: state.globalId),
              geometry.imageSize.width > 0,
              geometry.imageSize.height > 0 else { return nil }
        let candidate = CGPoint(
            x: placement.normalizedPinX * geometry.imageSize.width,
            y: placement.normalizedPinY * geometry.imageSize.height
        )
        let boundary = WatchGreenPreviewLayout.boundaryPolygon(geometry.greenOutlinePx)
        return WatchGreenPreviewLayout.contains(candidate, polygon: boundary) ? candidate : nil
    }

    private func greenRotation(for state: WatchRoundState) -> Double {
        model.greenPlacement(forHole: state.hole, globalId: state.globalId)?.rotationDegrees ?? 0
    }

    /// Hole Root's middle value follows the moved flag. The canonical centre range remains the sole
    /// pixel calibration authority, so repeatedly entering View Green cannot compound rounding error.
    private func centerYd(_ s: WatchRoundState) -> Int? {
        guard hasQualifiedRangeFix else { return 999 }
        guard let canonical = canonicalCenterYd(s),
              let geometry = holeGeometry,
              let selectedPin = selectedGreenPin(for: s, geometry: geometry) else {
            return canonicalCenterYd(s) ?? 999
        }
        return WatchGreenPreviewLayout.pinMetrics(
            playerImagePoint: geometry.youPx,
            canonicalPinImagePoint: geometry.pinPx,
            selectedPinImagePoint: selectedPin,
            greenOutline: geometry.greenOutlinePx,
            centerGreenYards: canonical
        )?.playerToPinYards ?? canonical
    }

    private func backYd(_ s: WatchRoundState) -> Int? {
        guard hasQualifiedRangeFix else { return 999 }
        return Self.effectiveGreenYards(live: watchGreenYards?.back, fallbackMetres: s.backGreenM) ?? 999
    }

    /// Prefer the Watch's live walk-off distance; retain older server/phone facts as an offline fallback.
    private func latestShotDistanceM(_ s: WatchRoundState) -> Double? {
        if let fix = qualifiedShotLocation,
           let live = model.distanceFromLatestShotM(
                latitude: fix.coordinate.latitude,
                longitude: fix.coordinate.longitude
           ) {
            return live
        }
        return s.distanceFromLastShotM ?? s.lastShotDistanceM
    }

    public var body: some View {
        if isLuminanceReduced, let state = model.activeHoleState {
            WatchAlwaysOnDistanceView(
                hole: state.displayHoleNumber,
                par: state.par,
                centerYd: centerYd(state)
            )
        } else {
            activeScreen
                .overlay(alignment: .bottom) { undoableShotStrip }
                .task(id: model.pendingManualShot?.capturedAt) {
                    // B6: a detected shot is recorded once its undo window passes.
                    guard model.undoableShotText != nil else { return }
                    try? await Task.sleep(nanoseconds: shotUndoSeconds * 1_000_000_000)
                    guard !Task.isCancelled else { return }
                    model.completePendingManualShot(clubName: nil)
                }
        }
    }

    @ViewBuilder
    private var undoableShotStrip: some View {
        if let text = model.undoableShotText {
            WatchShotUndoStrip(text: text) { model.undoPendingManualShot() }
        }
    }

    @ViewBuilder
    private var activeScreen: some View {
        switch model.screen {
        case .resume:
            WatchResumeRoundView(
                courseName: model.courseName,
                activeHole: model.activeDisplayHoleNumber,
                scoredHoles: model.scoredHoles,
                holeCount: model.holeCount,
                pendingUploads: model.pendingUploads,
                isFreshRound: !model.hasRecordedProgress,
                canSaveAndEnd: model.canSaveAndEndFromResume,
                pendingPhoneCourseName: model.pendingPhoneRoundCourseName,
                onResume: { model.resumeRound() },
                onSaveAndEnd: { model.requestSaveAndEndFromResume() },
                onAbandon: { model.requestAbandon() }
            )
        case .home:
            if let state = model.activeHoleState {
                currentHoleRoot(state)
            } else {
                Color.black.onAppear { model.openMenu() }
            }
        case .autoShotCandidate:
            // No per-shot confirmation page (README §3): a legacy candidate becomes the undoable shot.
            Color.black.onAppear {
                model.acceptAutoShotCandidate()
                if model.screen == .autoShotCandidate { model.backToHome() }
            }
        case .holeMap:
            if let state = model.activeHoleState, let geometry = holeGeometry {
                holeMapDetailView(state, geometry)
            } else {
                Color.black.onAppear { model.backToHome() }
            }
        case .menu:
            WatchMenuView(
                hasCaddie: model.caddieDetailAvailable,
                hasViewGreen: holeGeometry != nil,
                hasHazards: model.hazardDetailAvailable,
                hasClubStats: model.clubStatsAvailable,
                hasFlagDirection: activeFlagCoordinate != nil,
                onViewGreen: { model.openViewGreen() },
                onCaddie: { model.openCaddie() },
                onHazards: { model.openHazards() },
                onScorecard: { model.openScorecard() },
                onHoleSelect: { model.openHoleSelect() },
                onClubStats: { model.openClubStats() },
                onSettings: { model.openSettings() },
                onFlagDirection: { model.openFlagDirection() },
                onFinish: { model.requestFinish() },
                onBack: { model.backToHome() }
            )
        case .viewGreen:
            if let state = model.activeHoleState, let geometry = holeGeometry {
                greenPage(state, geometry: geometry, onBack: { model.backToMenu() })
            } else {
                Color.black.onAppear { model.backToMenu() }
            }
        case .caddie:
            if let state = model.activeHoleState, model.caddieDetailAvailable {
                WatchCaddieScreen(
                    state: state,
                    geometry: holeGeometry,
                    frontYd: frontYd(state),
                    centerYd: centerYd(state),
                    backYd: backYd(state),
                    lastShotDistanceM: latestShotDistanceM(state),
                    onBack: { model.backToHome() }
                )
            } else {
                Color.black.onAppear { model.backToHome() }
            }
        case .hazards:
            if let state = model.activeHoleState, model.hazardDetailAvailable {
                if let geometry = holeGeometry,
                   let route = state.holeMap?.route,
                   !route.isEmpty {
                    hazardPage(state, geometry: geometry, route: route, onBack: { model.backToMenu() })
                } else {
                    // Legacy cache without a shared topo frame cannot place obstacle facts honestly.
                    // Keep its text-only degradation; geometry-capable rounds never pass through it.
                    ScrollView {
                        VStack(alignment: .leading, spacing: 8) {
                            instrumentBackButton
                            WatchHazardView(hazards: state.hazards)
                        }
                        .padding(8)
                    }
                }
            } else {
                Color.black.onAppear { model.backToMenu() }
            }
        case .clubStats:
            WatchClubStatsView(
                clubs: model.allHoleStates.flatMap(\.availableClubs),
                onBack: { model.backToMenu() }
            )
        case .settings:
            WatchSettingsView(
                gpsPreheatEnabled: $gpsPreheatEnabled,
                bigTextMode: $holeMapBigText,
                autoShotSupported: autoShotSupported,
                autoShotEnabled: model.autoShotEnabled,
                autoShotStatus: autoShotStatus,
                onToggleAutoShot: {
                    guard autoShotSupported else { return }
                    model.setAutoShotEnabled(!model.autoShotEnabled)
                },
                onBack: { model.backToMenu() }
            )
        case .flagDirection:
            WatchFlagDirectionView(
                state: flagDirectionState,
                onBack: { model.backToMenu() }
            )
        case .scorecard:
            ScrollView {
                WatchScorecardView(
                    holes: model.allHoleStates.map { WatchScorecardRow(hole: $0.hole, par: $0.par, score: $0.score, displayHole: $0.displayHoleNumber) },
                    totalToPar: model.toPar,
                    onSelectHole: { model.startEditingHole($0) },
                    onBack: { model.closeScorecard() }
                )
            }
        case .holeSelect:
            ScrollView {
                WatchHoleSelectView(
                    holes: model.allHoleStates.map(\.hole),
                    activeHole: model.activeHole,
                    displayHoles: Dictionary(
                        model.allHoleStates.map { ($0.hole, $0.displayHoleNumber) },
                        uniquingKeysWith: { first, _ in first }
                    ),
                    onSelect: { model.selectHole($0) },
                    onBack: { model.openMenu() }
                )
            }
        case .scoring:
            WatchScoreHoleView(
                hole: model.displayHoleNumber(model.scoringHole ?? model.activeHole),
                par: model.scoringHoleState?.par ?? 0,
                score: model.draftScore,
                putts: model.draftPutts,
                penalty: model.draftPenalty,
                courseDataPending: model.scoringHoleState?.geometryCoverage == "pending",
                fairway: model.draftFairway,
                candidateNextHole: model.pendingManualShot?.candidateFromHole == model.scoringHole
                    ? model.pendingManualShot.map { model.displayHoleNumber($0.hole) }
                    : nil,
                onScore: { model.setDraftScore($0) },
                onPutts: { model.setDraftPutts($0) },
                onPenalty: { model.setDraftPenalty($0) },
                onFairway: { model.setDraftFairway($0) },
                onSave: { model.saveManualScore() },
                onCancel: { model.cancelScoring() }
            )
        case .turn:
            if let plan = model.turnPlan {
                WatchTurnView(
                    plan: plan,
                    isLoading: model.isLoadingSecondLoop,
                    message: model.turnMessage,
                    onChoose: { model.chooseTurnSecond($0) },
                    onConfirm: { Task { await model.confirmTurn() } },
                    onBack: { model.leaveTurn() }
                )
            } else {
                Color.black.onAppear { model.backToHome() }
            }
        case .finishing:
            WatchFinishRoundView(
                courseName: model.courseName,
                holesPlayed: model.scoredHoles,
                holeCount: model.holeCount,
                totalStrokes: model.totalStrokes,
                toPar: model.toPar,
                totalPutts: model.totalPutts,
                fairwaySummary: model.fairwaySummary,
                girSummary: model.girSummary,
                pendingUploads: model.pendingUploads,
                onConfirmFinish: { model.requestFinishConfirmation() },
                onEditScore: { model.openScorecardFromFinish() },
                onKeepPlaying: { model.keepPlaying() },
                onAbandon: { model.requestAbandon() }
            )
        case .finishConfirmation:
            WatchFinishConfirmationView(
                holesPlayed: model.scoredHoles,
                toPar: model.toPar,
                pendingUploads: model.pendingUploads,
                isUploading: model.isUploading,
                uploadError: model.uploadError,
                onConfirm: { Task { await model.confirmFinish() } },
                onCancel: { model.cancelFinishConfirmation() }
            )
        case .abandonConfirmation:
            WatchAbandonConfirmationView(
                pendingUploads: model.pendingUploads,
                errorMessage: model.uploadError,
                onConfirm: { model.confirmAbandon() },
                onCancel: { model.cancelAbandon() }
            )
        }
    }

    var distanceText: String? {
        guard hasQualifiedRangeFix else { return "999 码 · 等待定位" }
        guard let state = model.activeHoleState,
              let center = Self.canonicalCenterYards(
                live: watchGreenYards?.center,
                fallbackMetres: state.centerGreenM,
                hasQualifiedRangeFix: true
              ) else { return "999 码 · 等待球场数据" }
        if WatchGeoMath.isBeyondUsefulGreenRange(center) { return "离本洞较远" }
        return "\(WatchGeoMath.greenRangeText(center)) 码"
    }

    /// A delivered Watch green range remains unusable as a live distance until the Watch publishes
    /// a fresh, accurate coordinate. This prevents stale bridge values from masking the Garmin-style
    /// 999 cold-start state.
    private var hasQualifiedRangeFix: Bool {
        Self.rangeFixIsQualified(
            shotLocation: shotLocation,
            watchGreenYards: watchGreenYards
        )
    }

    /// Only a fresh, accurate wrist coordinate can support direction, shot capture, or a live
    /// walk-off calculation. A complete bridged F/M/B tuple can keep distance presentation alive,
    /// but it cannot manufacture a coordinate for those actions.
    private var qualifiedShotLocation: WatchLocationFix? {
        guard let shotLocation,
              WatchLocationProvider.isLiveRangefinderFix(shotLocation) else {
            return nil
        }
        return shotLocation
    }

    private var activeFlagCoordinate: (latitude: Double, longitude: Double)? {
        guard let state = model.activeHoleState else { return nil }
        if let latitude = state.targetLatitude,
           let longitude = state.targetLongitude,
           validCoordinate(latitude: latitude, longitude: longitude) {
            return (latitude, longitude)
        }
        if let latitude = state.centerGreenLat,
           let longitude = state.centerGreenLon,
           validCoordinate(latitude: latitude, longitude: longitude) {
            return (latitude, longitude)
        }
        return nil
    }

    private var flagDirectionState: WatchFlagDirectionState {
        WatchFlagDirectionResolver.resolve(
            playerLatitude: qualifiedShotLocation?.coordinate.latitude,
            playerLongitude: qualifiedShotLocation?.coordinate.longitude,
            flagLatitude: activeFlagCoordinate?.latitude,
            flagLongitude: activeFlagCoordinate?.longitude,
            heading: watchHeading
        )
    }

    private func validCoordinate(latitude: Double, longitude: Double) -> Bool {
        latitude.isFinite && longitude.isFinite
            && (-90...90).contains(latitude)
            && (-180...180).contains(longitude)
    }

    // A prepared Tee plan may appear on Hole Root only while a qualified Watch fix still places the
    // player at that Tee. Away from the Tee, Root requires the stricter fresh live-decision contract.
    private func caddieOption(_ s: WatchRoundState) -> WatchCaddieOption? {
        if let selectedPlanId, let picked = s.caddieOptions.first(where: { $0.optionId == selectedPlanId }) {
            return picked
        }
        if let optionId = s.offlineOptionId ?? s.strategyMode,
           let selected = s.caddieOptions.first(where: { $0.optionId == optionId }) {
            return selected
        }
        if let suggested = normalizedCaddieClub(s.suggestedClub) {
            return s.caddieOptions.first(where: {
                normalizedCaddieClub($0.plan?.first?.clubName ?? $0.clubName) == suggested
            })
        }
        return s.caddieOptions.first
    }

    private func caddieClub(_ s: WatchRoundState) -> String {
        let option = caddieOption(s)
        return WatchClubDisplay.name(
            option?.plan?.first?.clubName ?? option?.clubName ?? s.suggestedClub ?? "—"
        )
    }

    private func caddieNote(_ s: WatchRoundState) -> String {
        let option = caddieOption(s)
        if let remaining = s.expectedRemainingM, remaining.isFinite, remaining >= 0 {
            if remaining <= 10 { return "攻果岭" }
            return "留\(WatchUnits.yards(remaining))码"
        }

        // Hole Root gets one short current-shot fact. Arbitrary target prose belongs in Caddie detail;
        // allowing it here was the source of 0.55–0.62 text scaling on the compact display.
        if let carry = option?.plan?.first?.carryM ?? option?.carryM,
           carry.isFinite,
           carry > 0 {
            return "\(WatchUnits.yards(carry))码"
        }
        return option?.label ?? ""
    }

    private func normalizedCaddieClub(_ value: String?) -> String? {
        guard let value else { return nil }
        let display = WatchClubDisplay.name(value)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !display.isEmpty, display != "—" else { return nil }
        return display.lowercased()
    }

    private func caddieLine(_ s: WatchRoundState) -> String? {
        let club = caddieClub(s)
        let note = caddieNote(s)
        if club == "—" && note.isEmpty { return nil }
        return note.isEmpty ? club : "\(club) · \(note)"
    }

    @ViewBuilder
    private func holeMapView(_ s: WatchRoundState, _ geometry: WatchHoleMapGeometry) -> some View {
        let selectedPin = selectedGreenPin(for: s, geometry: geometry)
        let currentShot = currentShotLayout(for: s, geometry: geometry)
        let preparedGeometry = currentShot == nil
            && model.preparedRootCaddieLayerAvailable(at: shotLocation)
            ? preparedRootGeometry(for: s, base: geometry)
            : nil
        let preparedRootCaddieLayerAvailable = preparedGeometry != nil
        let renderedGeometry = preparedGeometry ?? geometry
        WatchHoleMapView(
            holeNumber: s.displayHoleNumber,
            par: s.par,
            frontGreen: frontYd(s),
            centerGreen: centerYd(s),
            backGreen: backYd(s),
            canonicalCenterGreen: canonicalCenterYd(s),
            playsLikeDelta: model.activePlaysLikeDeltaYards,
            lastShot: latestShotDistanceM(s).map(WatchUnits.yards) ?? 0,
            caddieClub: caddieClub(s),
            caddieNote: caddieNote(s),
            showCaddieRecommendation: currentShot != nil || preparedRootCaddieLayerAvailable,
            currentShotLayout: currentShot,
            showPreparedPlan: preparedRootCaddieLayerAvailable,
            driverDistanceM: model.playerAtActiveTee(at: shotLocation) ? driverDistanceM(s) : nil,
            showReferenceMarkers: true,
            hazardRoute: s.holeMap?.route ?? [],
            // owner 2026-07-08 (Fable audit): KEEP the scoring ring — real per-hole scores, current hole hi.
            ringPips: model.allHoleStates.map {
                WatchRingPip(hole: $0.hole, toPar: $0.score > 0 ? $0.score - $0.par : nil, isCurrent: $0.hole == model.activeHole)
            },
            showTextOverlay: centerYd(s) != nil,
            rangeUnavailable: !hasQualifiedRangeFix,
            // owner 2026-07-08: KEEP 实打 — only when the backend has a real mesh-elevation slope
            // (elevationDeltaM non-nil ⇒ playsLike.available), so it stays honest.
            showPlaysLike: s.elevationDeltaM != nil && hasQualifiedRangeFix,
            fullMap: false,
            mapScale: CGFloat(WatchHoleMapView.restingCrownScale),
            geometry: renderedGeometry,
            pinImagePoint: selectedPin,
            measuredPxOverride: measuredPxOverride,
            interactionMode: .measure,
            userZoom: planViewport.zoom,
            userPan: planViewport.pan,
            measureOriginImagePx: teeImagePoint(s),
            planLegs: planLegs(s, geometry: geometry),
            onOpenCaddie: { cyclePlan(s) },
            onOpenMapDetail: {
                holeMapCrownScale = WatchHoleMapView.restingCrownScale
                model.openHoleMap()
            }
        )
        .id(instrumentIdentity("root-map", state: s, geometry: renderedGeometry))
    }

    // MARK: B6 本洞 pages (README §3)

    /// 方案 / 障碍 / 果岭 as vertical pages (dots on the right). Unzoomed a vertical swipe pages; the
    /// Crown only zooms the page in view and a drag pans it once zoomed.
    private func holePages(_ s: WatchRoundState, _ geometry: WatchHoleMapGeometry) -> some View {
        TabView(selection: $holePage) {
            GeometryReader { proxy in
                holeMapView(s, geometry)
                    .watchZoomPan($planViewport, size: proxy.size)
            }
            .tag(0)
            // Always three pages (README §3): with nothing ahead the hazard page says 前方无障碍
            // instead of disappearing.
            hazardPage(s, geometry: geometry, route: s.holeMap?.route ?? [], onBack: { holePage = 0 })
                .tag(1)
            greenPage(s, geometry: geometry, onBack: { holePage = 0 })
                .tag(2)
        }
        .tabViewStyle(.verticalPage)
        .accessibilityIdentifier("watch-hole-pages")
        // The page in view, for the paging UI test: TabView keeps its neighbours in the hierarchy,
        // so their own elements cannot say which page is showing.
        .overlay(alignment: .topLeading) {
            Color.clear
                .frame(width: 1, height: 1)
                .allowsHitTesting(false)
                .accessibilityElement()
                .accessibilityLabel("本洞页")
                .accessibilityValue(Self.holePageName(holePage))
                .accessibilityIdentifier("watch-hole-page-current")
        }
    }

    /// 方案 / 障碍 / 果岭 by page tag.
    static func holePageName(_ page: Int) -> String {
        switch page {
        case 1: return "障碍"
        case 2: return "果岭"
        default: return "方案"
        }
    }

    /// Tap the green club tag: the next caddie plan (wrapping).
    private func cyclePlan(_ s: WatchRoundState) {
        if let next = Self.nextPlanId(after: caddieOption(s)?.optionId, in: s.caddieOptions.map(\.optionId)) {
            selectedPlanId = next
        }
    }

    /// The plan after `current` (wrapping); nil with fewer than two plans.
    static func nextPlanId(after current: String?, in ids: [String]) -> String? {
        guard ids.count > 1 else { return nil }
        let index = current.flatMap { ids.firstIndex(of: $0) } ?? -1
        return ids[(index + 1) % ids.count]
    }

    /// The selected plan as map legs: every remaining shot with its landing and label (README §3).
    /// Before the tee shot the plan starts at the tee.
    private func planLegs(_ s: WatchRoundState, geometry: WatchHoleMapGeometry) -> [WatchPlanLeg] {
        guard let option = caddieOption(s), let route = s.holeMap?.route else { return [] }
        let plan = option.plan ?? option.carryM.map { [WatchCaddiePlanStep(clubName: option.clubName ?? "", carryM: $0)] } ?? []
        return WatchPlanLegs.resolve(plan: plan, route: route, origin: teeImagePoint(s) ?? geometry.youPx)
    }

    /// Before the tee shot every range is measured from the tee (README §3).
    private func teeImagePoint(_ s: WatchRoundState) -> CGPoint? {
        guard model.recordedShotCount == 0,
              let lat = s.teeLatitude, let lon = s.teeLongitude,
              let refs = s.holeImageProjection?.refs else { return nil }
        return WatchGeoMath.projectToTopoPx(lat: lat, lon: lon, refs: refs)
    }

    private func hazardPage(
        _ state: WatchRoundState,
        geometry: WatchHoleMapGeometry,
        route: [[Double]],
        onBack: @escaping () -> Void
    ) -> some View {
        WatchHazardMapView(
            geometry: geometry,
            route: route,
            hazards: state.hazards,
            centerGreenYards: canonicalCenterYd(state),
            rangeUnavailable: !hasQualifiedRangeFix,
            initialHazardID: initialHazardID,
            initialViewport: initialHazardViewport,
            onBack: onBack
        )
        .id(instrumentIdentity("hazards", state: state, geometry: geometry))
    }

    private func greenPage(
        _ state: WatchRoundState,
        geometry: WatchHoleMapGeometry,
        onBack: @escaping () -> Void
    ) -> some View {
        let savedPin = selectedGreenPin(for: state, geometry: geometry)
        return WatchGreenPreviewView(
            geometry: geometry,
            centerGreenYards: canonicalCenterYd(state),
            rangeUnavailable: !hasQualifiedRangeFix,
            initialPin: initialGreenPinOverride ?? savedPin,
            initialZoomScale: initialGreenZoomScaleOverride,
            initialRotationDegrees: initialGreenRotationOverride ?? greenRotation(for: state),
            onPlacementChange: { pin, rotation in
                guard geometry.imageSize.width > 0, geometry.imageSize.height > 0 else { return }
                model.saveGreenPlacement(
                    hole: state.hole,
                    globalId: state.globalId,
                    normalizedPinX: pin.x / geometry.imageSize.width,
                    normalizedPinY: pin.y / geometry.imageSize.height,
                    rotationDegrees: rotation
                )
            },
            onBack: onBack
        )
        // SwiftUI may otherwise reuse Green View's local pin/zoom state for the next hole.
        .id(instrumentIdentity("green", state: state, geometry: geometry))
    }

    private func holeMapDetailView(
        _ s: WatchRoundState,
        _ geometry: WatchHoleMapGeometry
    ) -> some View {
        let selectedPin = selectedGreenPin(for: s, geometry: geometry)
        return WatchHoleMapView(
            holeNumber: s.displayHoleNumber,
            par: s.par,
            frontGreen: frontYd(s),
            centerGreen: centerYd(s),
            backGreen: backYd(s),
            canonicalCenterGreen: canonicalCenterYd(s),
            lastShot: 0,
            showCaddieRecommendation: false,
            showPreparedPlan: false,
            showReferenceMarkers: false,
            hazardRoute: s.holeMap?.route ?? [],
            ringPips: [],
            showTextOverlay: false,
            rangeUnavailable: !hasQualifiedRangeFix,
            showHoleIdentity: false,
            fullMap: true,
            mapScale: CGFloat(holeMapCrownScale),
            geometry: geometry,
            pinImagePoint: selectedPin,
            measuredPxOverride: measuredPxOverride,
            interactionMode: .touchTarget,
            onBack: { model.backToHome() }
        )
        .id(instrumentIdentity("touch-target", state: s, geometry: geometry))
        .focusable(true)
        .digitalCrownRotation(
            $holeMapCrownScale,
            from: WatchHoleMapView.restingCrownScale,
            through: WatchHoleMapView.maximumCrownScale,
            by: 0.02,
            sensitivity: .medium,
            isContinuous: false,
            isHapticFeedbackEnabled: true
        )
        .onChange(of: s.hole) { _ in
            holeMapCrownScale = WatchHoleMapView.restingCrownScale
        }
    }

    /// Stable identity for views that own transient drag/zoom state. Dynamic player coordinates are
    /// deliberately excluded: they update the map facts in place instead of cancelling a gesture.
    private func instrumentIdentity(
        _ mode: String,
        state: WatchRoundState,
        geometry: WatchHoleMapGeometry
    ) -> String {
        let width = Int(geometry.imageSize.width.rounded())
        let height = Int(geometry.imageSize.height.rounded())
        let crop = geometry.greenDetailRectPx.map {
            "\(Int($0.minX.rounded())):\(Int($0.minY.rounded())):\(Int($0.width.rounded())):\(Int($0.height.rounded()))"
        } ?? "none"
        return "\(mode)|\(state.globalId ?? 0)|\(state.hole)|\(state.geometryRevision ?? "none")|\(width)x\(height)|\(crop)"
    }

    /// Driver Distance is drawn only from a real bag median. Missing/unknown values remove the arc;
    /// the recommended club or a prepared carry is never substituted as if it were the user's Driver.
    private func driverDistanceM(_ state: WatchRoundState) -> Double? {
        state.availableClubs.first(where: {
            WatchClubDisplay.shortCode($0.clubName) == "D"
                && ($0.medianM?.isFinite ?? false)
                && ($0.medianM ?? 0) > 0
        })?.medianM
    }

    /// Legacy map payloads retain a 60%-of-hole compatibility anchor when no landing was supplied.
    /// Never render that anchor as advice: a prepared first shot must be rebuilt from the selected
    /// Caddie option's explicit carry and the measured cumulative-metre route.
    private func preparedRootGeometry(
        for state: WatchRoundState,
        base: WatchHoleMapGeometry
    ) -> WatchHoleMapGeometry? {
        let option = caddieOption(state)
        guard let carry = option?.plan?.first?.carryM ?? option?.carryM,
              carry.isFinite,
              carry > 0,
              let route = state.holeMap?.route,
              let progress = WatchHazardMapLayout.playerProgressMetres(
                on: route,
                playerImagePoint: base.youPx
              ),
              let target = WatchHazardMapLayout.imagePoint(
                on: route,
                atMetres: progress + carry
              ),
              hypot(target.x - base.youPx.x, target.y - base.youPx.y) > 1 else {
            return nil
        }
        let apex = WatchHazardMapLayout.imagePoint(
            on: route,
            atMetres: progress + carry * 0.5
        ) ?? CGPoint(
            x: (base.youPx.x + target.x) * 0.5,
            y: (base.youPx.y + target.y) * 0.5
        )
        return WatchHoleMapGeometry(
            image: base.image,
            imageSize: base.imageSize,
            youPx: base.youPx,
            pinPx: base.pinPx,
            layupPx: target,
            apexPx: apex,
            greenCtrlPx: base.greenCtrlPx,
            routePx: base.routePx,
            greenOutlinePx: base.greenOutlinePx,
            hazardSpans: base.hazardSpans
        )
    }

    private func currentShotLayout(
        for state: WatchRoundState,
        geometry: WatchHoleMapGeometry
    ) -> WatchCurrentShotLayout? {
        guard model.rootCaddieLayerAvailable(at: shotLocation),
              let recommendation = state.rootCaddieRecommendation,
              let route = state.holeMap?.route else {
            return nil
        }
        return WatchCurrentShotLayout.resolve(
            route: route,
            playerImagePoint: geometry.youPx,
            aimCarryM: recommendation.aimCarryM,
            carryP10M: recommendation.carryP10M,
            carryP90M: recommendation.carryP90M
        )
    }

    private func distanceHero(_ s: WatchRoundState, big: Bool) -> some View {
        let showCaddie = model.rootCaddieLayerAvailable(at: shotLocation)
            || model.preparedRootCaddieLayerAvailable(at: shotLocation)
        return WatchDistanceHero(
            frontYd: frontYd(s),
            centerYd: centerYd(s),
            backYd: backYd(s),
            caddieLine: showCaddie ? caddieLine(s) : nil,
            bigText: big,
            gpsUnavailable: !hasQualifiedRangeFix
        )
    }

    @ViewBuilder
    private func currentHoleRoot(_ s: WatchRoundState) -> some View {
        let mapPending = holeGeometry == nil && (
            s.globalId != nil
                || s.geometryCoverage?.caseInsensitiveCompare("pending") == .orderedSame
                || s.geometryCoverage?.caseInsensitiveCompare("partial") == .orderedSame
        )
        switch WatchHoleRootPresentation.resolve(
            hasQualifiedWristFix: hasQualifiedRangeFix,
            hasGeometry: holeGeometry != nil,
            hasLiveCenterDistance: Self.canonicalCenterYards(
                live: watchGreenYards?.center,
                fallbackMetres: s.centerGreenM,
                hasQualifiedRangeFix: hasQualifiedRangeFix
            ) != nil,
            courseDataPending: mapPending
        ) {
        case .acquiringGPS:
            // Kept for old deep links/tests; production resolution above deliberately never blocks
            // a seeded round on GPS.
            currentHoleInstrument { WatchGPSAcquiringView() }
        case .map:
            currentHoleInstrument {
                if holeMapBigText,
                   Self.canonicalCenterYards(
                    live: watchGreenYards?.center,
                    fallbackMetres: s.centerGreenM,
                    hasQualifiedRangeFix: hasQualifiedRangeFix
                   ) != nil {
                    distanceHero(s, big: true)
                        .contentShape(Rectangle())
                        .onTapGesture { holeMapBigText = false }
                } else if let geometry = holeGeometry {
                    holePages(s, geometry)
                }
            }
        case .mapPreparing:
            currentHoleInstrument {
                WatchMapPreparingView(
                    courseName: model.courseName,
                    hole: s.displayHoleNumber,
                    par: s.par
                )
            }
        case .distances:
            currentHoleInstrument {
                distanceHero(s, big: holeMapBigText)
                    .contentShape(Rectangle())
                    .onTapGesture { holeMapBigText.toggle() }
            }
        case .scoreOnly:
            scoreOnlyRoot(s)
        }
    }

    private func currentHoleInstrument<Content: View>(
        @ViewBuilder content: () -> Content
    ) -> some View {
        ZStack {
            content()
            rootControls
        }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.black)
            .ignoresSafeArea()
            .contentShape(Rectangle())
            // Zoomed, a 0.5 s press measures on the map, so the menu press waits for the 1× page.
            .onLongPressGesture(minimumDuration: 0.6) { if !planViewport.isZoomed { model.openMenu() } }
            .accessibilityAction(named: Text("球局工具")) { model.openMenu() }
            .onChange(of: model.activeHole) { _ in
                holeMapCrownScale = WatchHoleMapView.restingCrownScale
                holePage = 0
                planViewport = WatchHoleViewport()
                selectedPlanId = nil
            }
    }

    @ViewBuilder
    private var rootControls: some View {
        if holePage == 0 {
            rootControlRail
        }
    }

    private var rootControlRail: some View {
        GeometryReader { proxy in
            let safeRect = WatchDisplayGeometry.contentRect(in: proxy.size)
            let controlHalf = WatchDisplayGeometry.instrumentControlSize / 2
            HStack {
                rootControl(
                    systemName: "line.3.horizontal",
                    label: "高尔夫菜单",
                    identifier: "watch-hole-menu",
                    action: { model.openMenu() }
                )
                Spacer()
                if !model.autoShotEnabled {
                    rootControl(
                        systemName: "plus",
                        label: "手动记杆",
                        identifier: "watch-hole-record-shot",
                        isEnabled: qualifiedShotLocation != nil,
                        action: { recordManualShot() }
                    )
                }
            }
            .frame(width: safeRect.width)
            .position(x: safeRect.midX, y: safeRect.maxY - controlHalf)
        }
    }

    private func rootControl(
        systemName: String,
        label: String,
        identifier: String,
        isEnabled: Bool = true,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 22, weight: .black))
                .foregroundStyle(systemName == "plus" ? Color.black : Color.white)
                .frame(
                    width: WatchDisplayGeometry.instrumentVisualControlSize,
                    height: WatchDisplayGeometry.instrumentVisualControlSize
                )
                .background(systemName == "plus" ? AICaddieDesignTokens.hudGreen : Color.black.opacity(0.72), in: Circle())
                .overlay(Circle().stroke(systemName == "plus" ? AICaddieDesignTokens.hudGreen.opacity(0.92) : Color.white.opacity(0.34), lineWidth: 1.4))
                .frame(
                    width: WatchDisplayGeometry.instrumentControlSize,
                    height: WatchDisplayGeometry.instrumentControlSize
                )
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(!isEnabled)
        .opacity(isEnabled ? 1 : 0.45)
        .accessibilityLabel(label)
        .accessibilityIdentifier(identifier)
    }

    private func scoreOnlyRoot(_ s: WatchRoundState) -> some View {
        WatchRoundHomeView(
            courseName: model.courseName,
            hole: s.displayHoleNumber,
            par: s.par,
            holeCount: model.holeCount,
            scoredHoles: model.scoredHoles,
            toPar: model.toPar,
            distanceText: distanceText,
            courseDataPending: s.geometryCoverage == "pending",
            pendingUploads: model.pendingUploads,
            hasHoleMap: false,
            canRecordShot: qualifiedShotLocation != nil,
            onRecordShot: { recordManualShot() },
            onScoreHole: { model.startScoringActiveHole() },
            onPreviousHole: { model.goToPreviousHole() },
            onNextHole: { model.goToNextHole() },
            onFinish: { model.requestFinish() },
            onMenu: { model.openMenu() }
        )
    }

    private func recordManualShot() {
        guard let fix = qualifiedShotLocation else { return }
        model.beginManualShot(
            latitude: fix.coordinate.latitude,
            longitude: fix.coordinate.longitude,
            horizontalAccuracyM: fix.horizontalAccuracyM,
            capturedAt: fix.capturedAt
        )
    }

    private var instrumentBackButton: some View {
        WatchInstrumentBackButton(accessibilityLabel: "返回菜单") {
            model.backToMenu()
        }
    }

}
