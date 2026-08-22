import SwiftUI

/// The permanent current-hole surface. Geometry and distance availability select an honest visual
/// projection; they never change the scoring or shot state machine behind it.
public enum WatchHoleRootPresentation: Equatable {
    case acquiringGPS
    case map
    case distances
    case scoreOnly

    public static func resolve(
        hasQualifiedWristFix: Bool,
        hasGeometry: Bool,
        hasLiveCenterDistance: Bool
    ) -> Self {
        // GPS is a rangefinder input, not a round-entry gate. Keep the course map/score controls
        // usable during a cold fix (S70 shows 999 until location is ready); the caller supplies that
        // sentinel only for presentation and never fabricates a coordinate or shot fact.
        if hasGeometry { return .map }
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
            let approvedHeight = min(proxy.size.height, 198)
            VStack(spacing: 16) {
                Image(systemName: "location.magnifyingglass")
                    .font(.system(size: 34, weight: .semibold))
                    .foregroundStyle(Color(red: 0.28, green: 0.68, blue: 1.0))
                    .offset(y: 7)
                Text("搜星中...")
                    .font(.system(size: 16, weight: .bold))
                Text("定位就绪前不显示距离，\n免得报假数")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
            .frame(width: proxy.size.width, height: approvedHeight)
            .position(x: proxy.size.width / 2, y: approvedHeight / 2)
        }
        .background(Color.black)
        .ignoresSafeArea()
        .accessibilityElement(children: .combine)
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
                initialGreenRotationOverride: Double? = nil) {
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
        self.initialHazardID = initialSelectedHazardID
        self._holeMapCrownScale = State(initialValue: initialHoleMapCrownScale)
    }

    // watch P3: effective F/M/B — the watch-GPS value when available, else the phone-pushed distance.
    static func effectiveGreenYards(live: Int?, fallbackMetres: Double?) -> Int? {
        live ?? fallbackMetres.map(WatchUnits.yards)
    }

    private func frontYd(_ s: WatchRoundState) -> Int? {
        if let live = watchGreenYards?.front { return live }
        guard hasQualifiedRangeFix else { return 999 }
        return Self.effectiveGreenYards(live: watchGreenYards?.front, fallbackMetres: s.frontGreenM)
    }

    private func canonicalCenterYd(_ s: WatchRoundState) -> Int? {
        Self.effectiveGreenYards(live: watchGreenYards?.center, fallbackMetres: s.centerGreenM)
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
            return canonicalCenterYd(s)
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
        if let live = watchGreenYards?.back { return live }
        guard hasQualifiedRangeFix else { return 999 }
        return Self.effectiveGreenYards(live: watchGreenYards?.back, fallbackMetres: s.backGreenM)
    }

    /// Prefer the Watch's live walk-off distance; retain older server/phone facts as an offline fallback.
    private func latestShotDistanceM(_ s: WatchRoundState) -> Double? {
        if let fix = shotLocation,
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
                hole: state.hole,
                par: state.par,
                centerYd: centerYd(state)
            )
        } else {
            activeScreen
        }
    }

    @ViewBuilder
    private var activeScreen: some View {
        switch model.screen {
        case .resume:
            WatchResumeRoundView(
                courseName: model.courseName,
                activeHole: model.activeHole,
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
            if model.pendingAutoShotCandidate != nil {
                WatchAutoShotCandidateView(
                    onAccept: { model.acceptAutoShotCandidate() },
                    onReject: { model.rejectAutoShotCandidate() }
                )
            } else {
                Color.black.onAppear { model.backToHome() }
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
                let savedPin = selectedGreenPin(for: state, geometry: geometry)
                WatchGreenPreviewView(
                    geometry: geometry,
                    centerGreenYards: canonicalCenterYd(state),
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
                    onBack: { model.backToMenu() }
                )
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
                    WatchHazardMapView(
                        geometry: geometry,
                        route: route,
                        hazards: state.hazards,
                        centerGreenYards: canonicalCenterYd(state),
                        initialHazardID: initialHazardID,
                        onBack: { model.backToMenu() }
                    )
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
                    holes: model.allHoleStates.map { WatchScorecardRow(hole: $0.hole, par: $0.par, score: $0.score) },
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
                    onSelect: { model.selectHole($0) },
                    onBack: { model.openMenu() }
                )
            }
        case .clubPrompt:
            if let pending = model.pendingManualShot {
                WatchClubPromptView(
                    hole: pending.hole,
                    shotNumber: pending.shotNumber,
                    distanceToPinYards: model.activeHoleState.flatMap { centerYd($0) } ?? 999,
                    recommendedClub: model.allHoleStates.first(where: { $0.hole == pending.hole })?.suggestedClub,
                    clubs: model.allHoleStates.first(where: { $0.hole == pending.hole })?.availableClubs ?? [],
                    onSelectClub: { model.completePendingManualShot(clubName: $0) },
                    onSkipClub: { model.completePendingManualShot(clubName: nil) }
                )
            } else {
                Color.black.onAppear { model.backToHome() }
            }
        case .scoring:
            WatchScoreHoleView(
                hole: model.scoringHole ?? model.activeHole,
                par: model.scoringHoleState?.par ?? 0,
                score: model.draftScore,
                putts: model.draftPutts,
                penalty: model.draftPenalty,
                step: model.scoreFlowStep,
                fairway: model.draftFairway,
                candidateNextHole: model.pendingManualShot?.candidateFromHole == model.scoringHole
                    ? model.pendingManualShot?.hole
                    : nil,
                onScoreDelta: { model.adjustDraftScore($0) },
                onPuttsDelta: { model.adjustDraftPutts($0) },
                onPenaltyDelta: { model.adjustDraftPenalty($0) },
                onAcceptRecommended: { model.acceptRecommendedScore() },
                onManualEntry: { model.startManualScoreEntry() },
                onAdvance: { model.advanceScoreEntry() },
                onFairway: { model.selectDraftFairway($0) },
                onSave: { model.saveManualScore() },
                onCancel: { model.cancelScoring() }
            )
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
        guard let center = watchGreenYards?.center else {
            return shotLocation == nil ? "999 码 · 等待定位" : nil
        }
        if WatchGeoMath.isBeyondUsefulGreenRange(center) { return "离本洞较远" }
        return "\(WatchGeoMath.greenRangeText(center)) 码"
    }

    /// A delivered Watch green range is itself proof that a qualified wrist fix was available for
    /// that calculation. Keep it visible if the independently published location object arrives a
    /// frame later; only the complete absence of both facts should fall back to Garmin-style 999.
    private var hasQualifiedRangeFix: Bool {
        shotLocation != nil || watchGreenYards?.center != nil
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
            playerLatitude: shotLocation?.coordinate.latitude,
            playerLongitude: shotLocation?.coordinate.longitude,
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
            holeNumber: s.hole,
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
            // owner 2026-07-08: KEEP 实打 — only when the backend has a real mesh-elevation slope
            // (elevationDeltaM non-nil ⇒ playsLike.available), so it stays honest.
            showPlaysLike: s.elevationDeltaM != nil,
            fullMap: false,
            mapScale: CGFloat(WatchHoleMapView.restingCrownScale),
            geometry: renderedGeometry,
            pinImagePoint: selectedPin,
            measuredPxOverride: measuredPxOverride,
            interactionMode: .root,
            onOpenCaddie: { model.openCaddie() },
            onOpenMapDetail: {
                holeMapCrownScale = WatchHoleMapView.restingCrownScale
                model.openHoleMap()
            }
        )
    }

    private func holeMapDetailView(
        _ s: WatchRoundState,
        _ geometry: WatchHoleMapGeometry
    ) -> some View {
        let selectedPin = selectedGreenPin(for: s, geometry: geometry)
        return WatchHoleMapView(
            holeNumber: s.hole,
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
            showHoleIdentity: false,
            fullMap: true,
            mapScale: CGFloat(holeMapCrownScale),
            geometry: geometry,
            pinImagePoint: selectedPin,
            measuredPxOverride: measuredPxOverride,
            interactionMode: .touchTarget,
            onBack: { model.backToHome() }
        )
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
        switch WatchHoleRootPresentation.resolve(
            hasQualifiedWristFix: shotLocation != nil,
            hasGeometry: holeGeometry != nil,
            hasLiveCenterDistance: watchGreenYards?.center != nil
        ) {
        case .acquiringGPS:
            // Kept for old deep links/tests; production resolution above deliberately never blocks
            // a seeded round on GPS.
            currentHoleInstrument { WatchGPSAcquiringView() }
        case .map:
            currentHoleInstrument {
                if holeMapBigText, watchGreenYards?.center != nil {
                    distanceHero(s, big: true)
                        .contentShape(Rectangle())
                        .onTapGesture { holeMapBigText = false }
                } else if let geometry = holeGeometry {
                    holeMapView(s, geometry)
                }
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
            .onLongPressGesture(minimumDuration: 0.6) { model.openMenu() }
            .accessibilityAction(named: Text("球局工具")) { model.openMenu() }
            .onChange(of: model.activeHole) { _ in
                holeMapCrownScale = WatchHoleMapView.restingCrownScale
            }
    }

    private var rootControls: some View {
        GeometryReader { proxy in
            let safeRect = WatchDisplayGeometry.contentRect(in: proxy.size)
            let controlHalf = WatchDisplayGeometry.instrumentControlSize / 2
            HStack {
                rootControl(
                    systemName: "line.3.horizontal",
                    label: "球局菜单",
                    identifier: "watch-hole-menu",
                    action: { model.openMenu() }
                )
                Spacer()
                if !model.autoShotEnabled {
                    rootControl(
                        systemName: "plus",
                        label: "手动记杆",
                        identifier: "watch-hole-record-shot",
                        isEnabled: shotLocation != nil,
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
            hole: s.hole,
            par: s.par,
            holeCount: model.holeCount,
            scoredHoles: model.scoredHoles,
            toPar: model.toPar,
            distanceText: distanceText,
            pendingUploads: model.pendingUploads,
            hasHoleMap: false,
            canRecordShot: shotLocation != nil,
            onRecordShot: { recordManualShot() },
            onScoreHole: { model.startScoringActiveHole() },
            onPreviousHole: { model.goToPreviousHole() },
            onNextHole: { model.goToNextHole() },
            onFinish: { model.requestFinish() },
            onMenu: { model.openMenu() }
        )
    }

    private func recordManualShot() {
        guard let fix = shotLocation else { return }
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
