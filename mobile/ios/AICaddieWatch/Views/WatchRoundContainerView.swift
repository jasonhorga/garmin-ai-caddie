import SwiftUI

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

    /// watch P3: F/M/B green distances (码) from the watch's OWN GPS; when present they override the
    /// phone-pushed static distances so the hole view is a live rangefinder even without the phone.
    private let watchGreenYards: (front: Int?, center: Int?, back: Int?)?
    /// Latest fix from the Watch itself. Manual shot capture is disabled until this exists; no
    /// placeholder coordinate is ever manufactured.
    private let shotLocation: WatchLocationFix?
    private let autoShotSupported: Bool
    private let autoShotStatus: String

    public init(model: WatchRoundModel, holeGeometry: WatchHoleMapGeometry? = nil,
                watchGreenYards: (front: Int?, center: Int?, back: Int?)? = nil,
                shotLocation: WatchLocationFix? = nil,
                autoShotSupported: Bool = false,
                autoShotStatus: String = "本机不支持") {
        self.model = model
        self.holeGeometry = holeGeometry
        self.watchGreenYards = watchGreenYards
        self.shotLocation = shotLocation
        self.autoShotSupported = autoShotSupported
        self.autoShotStatus = autoShotStatus
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

    /// watch P1f: the hole view has a map (geometry holes) or a big F/M/B hero (no-geometry fallback), and
    /// a 大字 toggle that swaps either for the arm's-length center number. Shown when the hole has geometry
    /// OR at least a center-green distance; the home 「本洞」 entry is gated on the same.
    private func hasHoleView(_ s: WatchRoundState?) -> Bool {
        holeGeometry != nil || (s?.centerGreenM != nil)
    }

    public var body: some View {
        switch model.screen {
        case .home:
            WatchRoundHomeView(
                courseName: model.courseName,
                hole: model.activeHole,
                par: model.activeHoleState?.par ?? 0,
                holeCount: model.holeCount,
                scoredHoles: model.scoredHoles,
                toPar: model.toPar,
                distanceText: distanceText,
                pendingUploads: model.pendingUploads,
                ringPips: model.allHoleStates.map {
                    WatchRingPip(hole: $0.hole, toPar: $0.score > 0 ? $0.score - $0.par : nil, isCurrent: $0.hole == model.activeHole)
                },
                hasHoleMap: hasHoleView(model.activeHoleState),
                canRecordShot: shotLocation != nil,
                onHoleMap: { model.openHoleMap() },
                onRecordShot: {
                    guard let fix = shotLocation else { return }
                    model.beginManualShot(
                        latitude: fix.coordinate.latitude,
                        longitude: fix.coordinate.longitude,
                        horizontalAccuracyM: fix.horizontalAccuracyM,
                        capturedAt: fix.capturedAt
                    )
                },
                onScoreHole: { model.startScoringActiveHole() },
                onPreviousHole: { model.goToPreviousHole() },
                onNextHole: { model.goToNextHole() },
                onFinish: { model.requestFinish() },
                onMenu: { model.openMenu() }
            )
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
            if let s = model.activeHoleState, hasHoleView(s) {
                ZStack {
                    if holeMapBigText {
                        // 大字: tap anywhere to return to the map. (Map long-press turns it on.)
                        distanceHero(s, big: true)
                            .contentShape(Rectangle())
                            .onTapGesture { holeMapBigText = false }
                    } else if let geometry = holeGeometry {
                        // Map owns its gestures: tap=选点测距, drag flag=拖旗, long-press=大字.
                        holeMapView(s, geometry)
                    } else {
                        // No-geometry hero: tap → 大字 (there is no map to long-press).
                        distanceHero(s, big: false)
                            .contentShape(Rectangle())
                            .onTapGesture { holeMapBigText = true }
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color.black)
                .overlay(alignment: .bottomLeading) { backToHubButton }
            } else {
                // Geometry not ready (topo image still transferring) — return to the hub.
                Color.black.onAppear { model.backToHome() }
            }
        case .menu:
            WatchMenuView(
                hasCaddie: model.caddieDetailAvailable,
                hasHazards: model.hazardDetailAvailable,
                autoShotSupported: autoShotSupported,
                autoShotEnabled: model.autoShotEnabled,
                autoShotStatus: autoShotStatus,
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
                ScrollView {
                    VStack(alignment: .leading, spacing: 8) {
                        instrumentBackButton
                        Text("球童建议").font(.headline)
                        WatchCaddieGlanceView(
                            state: state,
                            frontYd: watchGreenYards?.front,
                            centerYd: watchGreenYards?.center,
                            backYd: watchGreenYards?.back,
                            lastShotDistanceM: latestShotDistanceM(state)
                        )
                        if !state.caddieOptions.isEmpty {
                            Divider()
                            WatchCaddieOptionsView(
                                options: state.caddieOptions,
                                recommendedId: state.offlineOptionId
                            )
                        }
                    }
                    .padding(8)
                }
            } else {
                Color.black.onAppear { model.backToMenu() }
            }
        case .hazards:
            if let state = model.activeHoleState, model.hazardDetailAvailable {
                ScrollView {
                    VStack(alignment: .leading, spacing: 8) {
                        instrumentBackButton
                        WatchHazardView(hazards: state.hazards)
                    }
                    .padding(8)
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
            showCaddieRecommendation: model.rootCaddieLayerAvailable,
            // owner 2026-07-08 (Fable audit): KEEP the scoring ring — real per-hole scores, current hole hi.
            ringPips: model.allHoleStates.map {
                WatchRingPip(hole: $0.hole, toPar: $0.score > 0 ? $0.score - $0.par : nil, isCurrent: $0.hole == model.activeHole)
            },
            showTextOverlay: true,
            // owner 2026-07-08: KEEP 实打 — only when the backend has a real mesh-elevation slope
            // (elevationDeltaM non-nil ⇒ playsLike.available), so it stays honest.
            showPlaysLike: s.elevationDeltaM != nil,
            geometry: geometry,
            onToggleBigText: { holeMapBigText = true }
        )
    }

    private func distanceHero(_ s: WatchRoundState, big: Bool) -> some View {
        WatchDistanceHero(
            frontYd: watchGreenYards?.front ?? s.frontGreenM.map { WatchUnits.yards($0) },
            centerYd: watchGreenYards?.center ?? s.centerGreenM.map { WatchUnits.yards($0) },
            backYd: watchGreenYards?.back ?? s.backGreenM.map { WatchUnits.yards($0) },
            caddieLine: model.rootCaddieLayerAvailable ? caddieLine(s) : nil,
            bigText: big
        )
    }

    private var instrumentBackButton: some View {
        Button(action: { model.backToMenu() }) {
            Label("菜单", systemImage: "chevron.backward")
                .font(.caption.weight(.semibold))
        }
        .buttonStyle(.plain)
    }

    private var backToHubButton: some View {
        // Back to the home hub (score/next/menu live there). Bottom-leading keeps clear of the watchOS
        // clock (top-trailing) and the map's top-leading data column.
        Button(action: { model.backToHome() }) {
            Image(systemName: "chevron.backward")
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(.white)
                .padding(7)
                .background(Circle().fill(.black.opacity(0.55)))
        }
        .buttonStyle(.plain)
        .padding(.leading, 5)
        .padding(.bottom, 5)
    }
}
