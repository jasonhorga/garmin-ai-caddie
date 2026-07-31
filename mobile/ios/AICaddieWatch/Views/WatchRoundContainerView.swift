import SwiftUI

/// The permanent current-hole surface. Geometry and distance availability select an honest visual
/// projection; they never change the scoring or shot state machine behind it.
public enum WatchHoleRootPresentation: Equatable {
    case map
    case distances
    case scoreOnly

    public static func resolve(hasGeometry: Bool, hasCenterDistance: Bool) -> Self {
        if hasGeometry { return .map }
        if hasCenterDistance { return .distances }
        return .scoreOnly
    }
}

/// round-12 P3.3 (Watch standalone): the navigation shell that wires `WatchRoundModel` to the three
/// presentational screens. It maps the model's derived state into each view's props and routes the
/// views' callbacks back to the model — the model owns all state, this view owns none. Switching on
/// `model.screen` (rather than a NavigationStack) keeps each screen full-bleed on the small watch face.
public struct WatchRoundContainerView: View {
    @ObservedObject private var model: WatchRoundModel
    /// watch P1b: the active hole's render geometry (topo image + overlay anchors), built by the app from
    /// the pushed WatchHoleMap + cached /topo.png. nil ⇒ no map yet ⇒ the home 「球道图」 entry stays hidden.
    private let holeGeometry: WatchHoleMapGeometry?
    /// watch P1f (spec D1 大字模式): tap the hole view to blow the center distance up for arm's-length /
    /// bright-sun reading. Toggled on the .holeMap screen; the map + the no-geometry hero both honor it.
    @State private var holeMapBigText = false
    /// Map Detail owns the Crown. The resting position keeps the facts column and score ring; turning it
    /// enters the existing full-map presentation and continuously changes the real image transform.
    @State private var holeMapCrownScale: Double
    /// A hazard row opens a focused map instrument. nil keeps the first-level S70-style hazard list.
    @State private var selectedHazardID: String? = nil

    /// watch P3: F/M/B green distances (码) from the watch's OWN GPS; when present they override the
    /// phone-pushed static distances so the hole view is a live rangefinder even without the phone.
    private let watchGreenYards: (front: Int?, center: Int?, back: Int?)?
    /// Latest fix from the Watch itself. Manual shot capture is disabled until this exists; no
    /// placeholder coordinate is ever manufactured.
    private let shotLocation: WatchLocationFix?
    private let autoShotSupported: Bool
    private let autoShotStatus: String
    /// DEBUG runtime evidence may start the real map in a deterministic interaction state. Production
    /// callers leave both nil, so live tap/drag state remains owned by WatchHoleMapView.
    private let measuredPxOverride: CGPoint?
    private let pinDragOverride: CGSize?

    public init(model: WatchRoundModel, holeGeometry: WatchHoleMapGeometry? = nil,
                watchGreenYards: (front: Int?, center: Int?, back: Int?)? = nil,
                shotLocation: WatchLocationFix? = nil,
                autoShotSupported: Bool = false,
                autoShotStatus: String = "本机不支持",
                initialHoleMapCrownScale: Double = WatchHoleMapView.restingCrownScale,
                measuredPxOverride: CGPoint? = nil,
                pinDragOverride: CGSize? = nil) {
        self.model = model
        self.holeGeometry = holeGeometry
        self.watchGreenYards = watchGreenYards
        self.shotLocation = shotLocation
        self.autoShotSupported = autoShotSupported
        self.autoShotStatus = autoShotStatus
        self.measuredPxOverride = measuredPxOverride
        self.pinDragOverride = pinDragOverride
        self._holeMapCrownScale = State(initialValue: initialHoleMapCrownScale)
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
                onRecordShot: { recordManualShot() },
                onScoreHole: { model.startScoringActiveHole() },
                onCaddie: { model.openCaddie() },
                onHazards: { model.openHazards() },
                onToggleAutoShot: {
                    guard autoShotSupported else { return }
                    model.setAutoShotEnabled(!model.autoShotEnabled)
                },
                onScorecard: { model.openScorecard() },
                onHoleSelect: { model.openHoleSelect() },
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
        case .scorecard:
            ScrollView {
                WatchScorecardView(
                    holes: model.allHoleStates.map { WatchScorecardRow(hole: $0.hole, par: $0.par, score: $0.score) },
                    totalToPar: model.toPar,
                    onSelectHole: { model.startEditingHole($0) },
                    onBack: { model.openMenu() }
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
                    recommendedClub: model.allHoleStates.first(where: { $0.hole == pending.hole })?.suggestedClub,
                    clubs: model.allHoleStates.first(where: { $0.hole == pending.hole })?.availableClubNames ?? [],
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
                onConfirmFinish: { Task { await model.confirmFinish() } },
                onKeepPlaying: { model.keepPlaying() }
            )
        }
    }

    var distanceText: String? {
        if let liveCenterYd = watchGreenYards?.center {
            return "\(liveCenterYd) 码"
        }
        guard let state = model.activeHoleState else { return nil }
        if let centerGreenM = state.centerGreenM {
            return "\(WatchUnits.yards(centerGreenM)) 码"
        }
        guard let distanceM = state.distanceM else { return nil }
        return "\(WatchUnits.yards(distanceM)) 码"
    }

    // A prepared/offline recommendation is useful inside the caddie detail surface, but D02 forbids it
    // from appearing on the root until freshness/mode/dispersion are all explicitly gated.
    private func caddieClub(_ s: WatchRoundState) -> String {
        s.suggestedClub ?? s.caddieOptions.first?.clubName ?? s.selectedClub ?? "—"
    }

    private func caddieNote(_ s: WatchRoundState) -> String {
        if let note = s.targetNote, !note.isEmpty { return note }
        return s.caddieOptions.first?.label ?? ""
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
            showCaddieRecommendation: currentShot != nil,
            currentShotLayout: currentShot,
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
            onOpenCaddie: { model.openCaddie() },
            onToggleBigText: { holeMapBigText = true }
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
        WatchDistanceHero(
            frontYd: watchGreenYards?.front ?? s.frontGreenM.map { WatchUnits.yards($0) },
            centerYd: watchGreenYards?.center ?? s.centerGreenM.map { WatchUnits.yards($0) },
            backYd: watchGreenYards?.back ?? s.backGreenM.map { WatchUnits.yards($0) },
            caddieLine: model.rootCaddieLayerAvailable(at: shotLocation) ? caddieLine(s) : nil,
            bigText: big
        )
    }

    @ViewBuilder
    private func currentHoleRoot(_ s: WatchRoundState) -> some View {
        switch WatchHoleRootPresentation.resolve(
            hasGeometry: holeGeometry != nil,
            hasCenterDistance: watchGreenYards?.center != nil || s.centerGreenM != nil
        ) {
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
            .overlay(alignment: .bottomLeading) { roundToolsButton }
            .onChange(of: model.activeHole) { _ in
                holeMapBigText = false
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

    private var roundToolsButton: some View {
        Button(action: { model.openMenu() }) {
            Image(systemName: "ellipsis")
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(.white)
                .padding(7)
                .background(Circle().fill(.black.opacity(0.55)))
        }
        .buttonStyle(.plain)
        .accessibilityLabel("球局工具")
        .padding(.leading, 5)
        .padding(.bottom, 5)
    }
}
