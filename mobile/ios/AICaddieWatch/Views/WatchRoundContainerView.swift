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
        guard hasQualifiedWristFix else { return .acquiringGPS }
        if hasGeometry, hasLiveCenterDistance { return .map }
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
    /// A hazard row opens a focused map instrument. nil keeps the first-level S70-style hazard list.
    @State private var selectedHazardID: String?

    /// watch P3: F/M/B green distances (码) from the watch's OWN GPS; when present they override the
    /// phone-pushed static distances so the hole view is a live rangefinder even without the phone.
    private let watchGreenYards: (front: Int?, center: Int?, back: Int?)?
    /// Latest fix from the Watch itself. Manual shot capture is disabled until this exists; no
    /// placeholder coordinate is ever manufactured.
    private let shotLocation: WatchLocationFix?
    private let watchHeading: WatchHeadingFix?
    private let autoShotSupported: Bool
    private let autoShotStatus: String
    /// DEBUG runtime evidence may start the real map in a deterministic interaction state. Production
    /// callers leave both nil, so live tap/drag state remains owned by WatchHoleMapView.
    private let measuredPxOverride: CGPoint?
    private let pinDragOverride: CGSize?

    public init(model: WatchRoundModel, holeGeometry: WatchHoleMapGeometry? = nil,
                watchGreenYards: (front: Int?, center: Int?, back: Int?)? = nil,
                shotLocation: WatchLocationFix? = nil,
                watchHeading: WatchHeadingFix? = nil,
                autoShotSupported: Bool = false,
                autoShotStatus: String = "本机不支持",
                initialHoleMapCrownScale: Double = WatchHoleMapView.restingCrownScale,
                initialSelectedHazardID: String? = nil,
                measuredPxOverride: CGPoint? = nil,
                pinDragOverride: CGSize? = nil) {
        self.model = model
        self.holeGeometry = holeGeometry
        self.watchGreenYards = watchGreenYards
        self.shotLocation = shotLocation
        self.watchHeading = watchHeading
        self.autoShotSupported = autoShotSupported
        self.autoShotStatus = autoShotStatus
        self.measuredPxOverride = measuredPxOverride
        self.pinDragOverride = pinDragOverride
        self._holeMapCrownScale = State(initialValue: initialHoleMapCrownScale)
        self._selectedHazardID = State(initialValue: initialSelectedHazardID)
    }

    // watch P3: effective F/M/B — the watch-GPS value when available, else the phone-pushed distance.
    private func frontYd(_ s: WatchRoundState) -> Int { watchGreenYards?.front ?? WatchUnits.yards(s.frontGreenM ?? 0) }
    private func centerYd(_ s: WatchRoundState) -> Int { watchGreenYards?.center ?? WatchUnits.yards(s.centerGreenM ?? 0) }
    private func backYd(_ s: WatchRoundState) -> Int { watchGreenYards?.back ?? WatchUnits.yards(s.backGreenM ?? 0) }

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
                centerYd: watchGreenYards?.center
            )
        } else {
            activeScreen
        }
    }

    @ViewBuilder
    private var activeScreen: some View {
        switch model.screen {
        case .home:
            if let state = model.activeHoleState {
                currentHoleRoot(state)
            } else {
                Color.black
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
            if let state = model.activeHoleState {
                // Backward-compatible navigation alias for pending interactions written by older builds.
                // It renders the same single root; there is no user-visible sibling map page.
                currentHoleRoot(state)
            } else {
                Color.black.onAppear { model.backToHome() }
            }
        case .menu:
            WatchMenuView(
                hasCaddie: model.caddieDetailAvailable,
                hasHazards: model.hazardDetailAvailable,
                canRecordShot: shotLocation != nil,
                autoShotSupported: autoShotSupported,
                autoShotEnabled: model.autoShotEnabled,
                autoShotStatus: autoShotStatus,
                hasClubStats: model.clubStatsAvailable,
                hasFlagDirection: activeFlagCoordinate != nil,
                onRecordShot: { recordManualShot() },
                onScoreHole: { model.startScoringActiveHole() },
                onCaddie: { model.openCaddie() },
                onHazards: { model.openHazards() },
                onToggleAutoShot: {
                    guard autoShotSupported else { return }
                    model.setAutoShotEnabled(!model.autoShotEnabled)
                },
                onScorecard: { model.openScorecard() },
                onCurrentHoleShots: { model.openCurrentHoleShots() },
                onHoleSelect: { model.openHoleSelect() },
                onClubStats: { model.openClubStats() },
                onSettings: { model.openSettings() },
                onFlagDirection: { model.openFlagDirection() },
                onFinish: { model.requestFinish() },
                onClose: { model.backToHome() }
            )
        case .caddie:
            if let state = model.activeHoleState, model.caddieDetailAvailable {
                WatchCaddieScreen(
                    state: state,
                    frontYd: watchGreenYards?.front,
                    centerYd: watchGreenYards?.center,
                    backYd: watchGreenYards?.back,
                    lastShotDistanceM: latestShotDistanceM(state),
                    onBack: { model.backToHome() }
                )
            } else {
                Color.black.onAppear { model.backToHome() }
            }
        case .hazards:
            if let state = model.activeHoleState, model.hazardDetailAvailable {
                if let selectedHazardID,
                   let geometry = holeGeometry,
                   let route = state.holeMap?.route,
                   !route.isEmpty {
                    WatchHazardMapView(
                        geometry: geometry,
                        route: route,
                        hazards: state.hazards,
                        centerGreenYards: centerYd(state),
                        initialHazardID: selectedHazardID,
                        onBack: { self.selectedHazardID = nil }
                    )
                } else {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 8) {
                            instrumentBackButton
                            if let geometry = holeGeometry,
                               let route = state.holeMap?.route,
                               !route.isEmpty {
                                let progress = WatchHazardMapLayout.playerProgressMetres(
                                    on: route,
                                    playerImagePoint: geometry.youPx
                                ) ?? 0
                                WatchHazardView(
                                    hazards: state.hazards,
                                    playerProgressM: progress,
                                    playerImagePoint: geometry.youPx,
                                    route: route,
                                    onSelect: { selectedHazardID = $0.id }
                                )
                            } else {
                                WatchHazardView(hazards: state.hazards)
                            }
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
                    onBack: { model.openMenu() }
                )
            }
        case .currentHoleShots:
            if let state = model.activeHoleState {
                ScrollView {
                    WatchCurrentHoleShotsView(
                        hole: state.hole,
                        par: state.par,
                        shots: model.currentHoleShots,
                        latestShotDistanceM: latestShotDistanceM(state),
                        canAddShot: shotLocation != nil,
                        onAddShot: { recordManualShot() },
                        onBack: { model.backToMenu() }
                    )
                }
                .ignoresSafeArea(edges: [.top, .leading, .trailing])
            } else {
                Color.black.onAppear { model.backToMenu() }
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
                    distanceToPinYards: watchGreenYards?.center,
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
                onKeepPlaying: { model.keepPlaying() }
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
        }
    }

    var distanceText: String? {
        watchGreenYards?.center.map { "\($0) 码" }
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
        if let suggested = s.suggestedClub?.trimmingCharacters(in: .whitespacesAndNewlines),
           !suggested.isEmpty,
           let matching = s.caddieOptions.first(where: {
               guard let clubName = $0.clubName?.trimmingCharacters(in: .whitespacesAndNewlines),
                     !clubName.isEmpty else {
                   return false
               }
               return clubName.caseInsensitiveCompare(suggested) == .orderedSame
           }) {
            return matching
        }
        return s.caddieOptions.first
    }

    private func caddieClub(_ s: WatchRoundState) -> String {
        WatchClubDisplay.name(caddieOption(s)?.clubName ?? s.suggestedClub ?? "—")
    }

    private func caddieNote(_ s: WatchRoundState) -> String {
        if let note = s.targetNote?.trimmingCharacters(in: .whitespacesAndNewlines), !note.isEmpty {
            return note
        }
        let option = caddieOption(s)
        if let remaining = s.expectedRemainingM, remaining.isFinite, remaining >= 0 {
            if remaining <= 10 { return "攻果岭" }
            return "留 \(WatchUnits.yards(remaining)) 码"
        }

        // A downloaded/offline plan has no calibrated dispersion, but its carry and following club
        // are real package facts. Use those to explain what this recommendation is trying to do
        // instead of showing only the vague strategy word ("稳妥").
        var parts: [String] = []
        if let carry = option?.carryM, carry.isFinite, carry > 0 {
            parts.append("打 \(WatchUnits.yards(carry))")
        }
        if let plan = option?.plan, let next = plan.dropFirst().first {
            parts.append("后接\(WatchClubDisplay.name(next.clubName))")
        }
        if !parts.isEmpty { return parts.joined(separator: " · ") }
        return option?.label ?? ""
    }

    private func caddieLine(_ s: WatchRoundState) -> String? {
        let club = caddieClub(s)
        let note = caddieNote(s)
        if club == "—" && note.isEmpty { return nil }
        return note.isEmpty ? club : "\(club) · \(note)"
    }

    @ViewBuilder
    private func holeMapView(_ s: WatchRoundState, _ geometry: WatchHoleMapGeometry) -> some View {
        let currentShot = currentShotLayout(for: s, geometry: geometry)
        let preparedRootCaddieLayerAvailable = currentShot == nil
            && model.preparedRootCaddieLayerAvailable(at: shotLocation)
        WatchHoleMapView(
            holeNumber: s.hole,
            par: s.par,
            frontGreen: frontYd(s),
            centerGreen: centerYd(s),
            backGreen: backYd(s),
            playsLikeDelta: model.activePlaysLikeDeltaYards,
            lastShot: latestShotDistanceM(s).map(WatchUnits.yards) ?? 0,
            caddieClub: caddieClub(s),
            caddieNote: caddieNote(s),
            showCaddieRecommendation: currentShot != nil || preparedRootCaddieLayerAvailable,
            currentShotLayout: currentShot,
            showPreparedPlan: preparedRootCaddieLayerAvailable,
            // owner 2026-07-08 (Fable audit): KEEP the scoring ring — real per-hole scores, current hole hi.
            ringPips: model.allHoleStates.map {
                WatchRingPip(hole: $0.hole, toPar: $0.score > 0 ? $0.score - $0.par : nil, isCurrent: $0.hole == model.activeHole)
            },
            showTextOverlay: true,
            // owner 2026-07-08: KEEP 实打 — only when the backend has a real mesh-elevation slope
            // (elevationDeltaM non-nil ⇒ playsLike.available), so it stays honest.
            showPlaysLike: s.elevationDeltaM != nil,
            fullMap: WatchHoleMapView.isFullMap(crownScale: holeMapCrownScale),
            mapScale: CGFloat(holeMapCrownScale),
            geometry: geometry,
            measuredPxOverride: measuredPxOverride,
            pinDragOverride: pinDragOverride,
            onOpenCaddie: { model.openCaddie() }
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
            frontYd: watchGreenYards?.front,
            centerYd: watchGreenYards?.center,
            backYd: watchGreenYards?.back,
            caddieLine: showCaddie ? caddieLine(s) : nil,
            bigText: big
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
            currentHoleInstrument {
                WatchGPSAcquiringView()
            }
        case .map:
            currentHoleInstrument {
                if holeMapBigText {
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
        ZStack { content() }
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
            ringPips: model.allHoleStates.map {
                WatchRingPip(
                    hole: $0.hole,
                    toPar: $0.score > 0 ? $0.score - $0.par : nil,
                    isCurrent: $0.hole == model.activeHole
                )
            },
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
        Button(action: { model.backToMenu() }) {
            Label("菜单", systemImage: "chevron.backward")
                .font(.caption.weight(.semibold))
        }
        .buttonStyle(.plain)
    }

}
