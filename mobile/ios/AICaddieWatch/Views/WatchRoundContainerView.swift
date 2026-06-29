import SwiftUI

/// round-12 P3.3 (Watch standalone): the navigation shell that wires `WatchRoundModel` to the three
/// presentational screens. It maps the model's derived state into each view's props and routes the
/// views' callbacks back to the model — the model owns all state, this view owns none. Switching on
/// `model.screen` (rather than a NavigationStack) keeps each screen full-bleed on the small watch face.
public struct WatchRoundContainerView: View {
    @ObservedObject private var model: WatchRoundModel

    public init(model: WatchRoundModel) {
        self.model = model
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
                onScoreHole: { model.startScoringActiveHole() },
                onPreviousHole: { model.goToPreviousHole() },
                onNextHole: { model.goToNextHole() },
                onFinish: { model.requestFinish() },
                onMenu: { model.openMenu() }
            )
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
}
