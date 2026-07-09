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

    public init(model: WatchRoundModel, holeGeometry: WatchHoleMapGeometry? = nil) {
        self.model = model
        self.holeGeometry = holeGeometry
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
                hasHoleMap: holeGeometry != nil,
                onHoleMap: { model.openHoleMap() },
                onScoreHole: { model.startScoringActiveHole() },
                onPreviousHole: { model.goToPreviousHole() },
                onNextHole: { model.goToNextHole() },
                onFinish: { model.requestFinish() },
                onMenu: { model.openMenu() }
            )
        case .holeMap:
            if let geometry = holeGeometry, let s = model.activeHoleState {
                WatchHoleMapView(
                    holeNumber: s.hole,
                    par: s.par,
                    frontGreen: WatchUnits.yards(s.frontGreenM ?? 0),
                    centerGreen: WatchUnits.yards(s.centerGreenM ?? 0),
                    backGreen: WatchUnits.yards(s.backGreenM ?? 0),
                    playsLikeDelta: Int((s.elevationDeltaM ?? 0).rounded()),
                    lastShot: WatchUnits.yards(s.lastShotDistanceM ?? 0),
                    caddieClub: caddieClub(s),
                    caddieNote: caddieNote(s),
                    // owner 2026-07-08 (Fable audit): KEEP the scoring ring — 18-hole edge ring of the
                    // round's real per-hole scores, current hole highlighted.
                    ringPips: model.allHoleStates.map {
                        WatchRingPip(hole: $0.hole, toPar: $0.score > 0 ? $0.score - $0.par : nil, isCurrent: $0.hole == model.activeHole)
                    },
                    showTextOverlay: true,
                    // owner 2026-07-08: KEEP 实打/plays-like — shown ONLY when the backend has a real
                    // mesh-elevation slope (elevationDeltaM non-nil ⇒ playsLike.available), so it stays
                    // honest: raw yardage on holes whose geometry carries no elevation.
                    showPlaysLike: s.elevationDeltaM != nil,
                    geometry: geometry
                )
                .overlay(alignment: .bottomLeading) {
                    // Back to the home hub (score/next/menu live there). Bottom-leading keeps clear of the
                    // watchOS clock (top-trailing) and the map's top-leading data column.
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
            } else {
                // Geometry not ready (topo image still transferring) — return to the hub.
                Color.black.onAppear { model.backToHome() }
            }
        case .menu:
            WatchMenuView(
                onScorecard: { model.openScorecard() },
                onHoleSelect: { model.openHoleSelect() },
                onFinish: { model.requestFinish() },
                onClose: { model.backToHome() }
            )
        case .scorecard:
            ScrollView {
                WatchScorecardView(
                    holes: model.allHoleStates.map { WatchScorecardRow(hole: $0.hole, par: $0.par, score: $0.score) },
                    totalToPar: model.toPar,
                    onSelectHole: { model.selectHole($0) },
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
        case .scoring:
            WatchScoreHoleView(
                hole: model.activeHole,
                par: model.activeHoleState?.par ?? 0,
                score: model.draftScore,
                putts: model.draftPutts,
                penalty: model.draftPenalty,
                onScoreDelta: { model.adjustDraftScore($0) },
                onPuttsDelta: { model.adjustDraftPutts($0) },
                onPenaltyDelta: { model.adjustDraftPenalty($0) },
                onSave: { model.saveActiveHole() },
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

    private var distanceText: String? {
        guard let distanceM = model.activeHoleState?.distanceM else { return nil }
        return "\(WatchUnits.yards(distanceM)) 码"
    }

    // watch P1b: the caddie recommendation shown on the hole map's data column.
    private func caddieClub(_ s: WatchRoundState) -> String {
        s.suggestedClub ?? s.caddieOptions.first?.clubName ?? s.selectedClub ?? "—"
    }

    private func caddieNote(_ s: WatchRoundState) -> String {
        if let note = s.targetNote, !note.isEmpty { return note }
        return s.caddieOptions.first?.label ?? ""
    }
}
