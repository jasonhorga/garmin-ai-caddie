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

    public init(model: WatchRoundModel, holeGeometry: WatchHoleMapGeometry? = nil) {
        self.model = model
        self.holeGeometry = holeGeometry
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
                onHoleMap: { model.openHoleMap() },
                onScoreHole: { model.startScoringActiveHole() },
                onPreviousHole: { model.goToPreviousHole() },
                onNextHole: { model.goToNextHole() },
                onFinish: { model.requestFinish() },
                onMenu: { model.openMenu() }
            )
        case .holeMap:
            if let s = model.activeHoleState, hasHoleView(s) {
                ZStack {
                    if holeMapBigText {
                        distanceHero(s, big: true)          // 大字模式: arm's-length center number
                    } else if let geometry = holeGeometry {
                        holeMapView(s, geometry)            // the real hole map
                    } else {
                        distanceHero(s, big: false)         // no-geometry fallback: big F/M/B hero
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color.black)
                .contentShape(Rectangle())
                .onTapGesture { holeMapBigText.toggle() }   // spec D1: tap toggles 大字
                .overlay(alignment: .bottomLeading) { backToHubButton }
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
            frontGreen: WatchUnits.yards(s.frontGreenM ?? 0),
            centerGreen: WatchUnits.yards(s.centerGreenM ?? 0),
            backGreen: WatchUnits.yards(s.backGreenM ?? 0),
            playsLikeDelta: Int((s.elevationDeltaM ?? 0).rounded()),
            lastShot: WatchUnits.yards(s.lastShotDistanceM ?? 0),
            caddieClub: caddieClub(s),
            caddieNote: caddieNote(s),
            // owner 2026-07-08 (Fable audit): KEEP the scoring ring — real per-hole scores, current hole hi.
            ringPips: model.allHoleStates.map {
                WatchRingPip(hole: $0.hole, toPar: $0.score > 0 ? $0.score - $0.par : nil, isCurrent: $0.hole == model.activeHole)
            },
            showTextOverlay: true,
            // owner 2026-07-08: KEEP 实打 — only when the backend has a real mesh-elevation slope
            // (elevationDeltaM non-nil ⇒ playsLike.available), so it stays honest.
            showPlaysLike: s.elevationDeltaM != nil,
            geometry: geometry
        )
    }

    private func distanceHero(_ s: WatchRoundState, big: Bool) -> some View {
        WatchDistanceHero(
            frontYd: s.frontGreenM.map { WatchUnits.yards($0) },
            centerYd: s.centerGreenM.map { WatchUnits.yards($0) },
            backYd: s.backGreenM.map { WatchUnits.yards($0) },
            caddieLine: caddieLine(s),
            bigText: big
        )
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
