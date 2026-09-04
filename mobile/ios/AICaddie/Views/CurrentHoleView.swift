import CoreLocation
import Foundation
import SwiftUI
import AICaddieDomain
#if canImport(UIKit)
import UIKit
#endif

private struct PendingPhoneShot: Identifiable {
    let locationEvent: LiveRoundEvent
    let shotOrder: Int

    var id: String { locationEvent.eventId }
}

/// One obstacle annotation in the shared topo-pixel frame. Distances and placement always come from
/// the same boundary facts, so the map never points at one bunker while describing another one.
private struct LiveMapHazardAnnotation: Identifiable {
    let id: String
    let kind: String
    let label: String
    let toYards: Int
    let overYards: Int
    let frontPx: [Double]
    let backPx: [Double]
}

public struct CurrentHoleView: View {
    @Environment(\.dismiss) private var dismiss

    public let package: LiveRoundPackage
    public let hole: Hole
    public let onEvent: (LiveRoundEvent) -> Void
    private let onRetainReadyHolePrep: (String, Int, CoursePrepHole) -> Void
    private let requestBuilder = CaddieDecisionRequestBuilder()
    private let offlineDecisionEvaluator = OfflineCaddieDecisionEvaluator()
    private let caddieClient: CaddieDecisionClient?
    private let mediaUploadClient: MediaUploadClient?
    private let caddieBaseURL: URL?
    private let adminToken: String?
    private let offlineStore: OfflineStore?
    private let watchBridge: WatchEventBridge?
    private let liveRoundState: LiveRoundStateSnapshot?
    // 球局调整(加打 / 减九洞 / 结束本场)— round-11: 从首页 Hub 移进开球后的实战屏(用户反馈:
    // 这些该在球局里、不放首页)。控件与闭包原样保留,仅换了容身的屏。
    private let courseOptions: [MobileCourseOption]
    private let startingNine: String?
    private let isPreparingRound: Bool
    private let pendingEventCount: Int
    private let isFinishingRound: Bool
    private let finishErrorMessage: String?
    private let onChangeNine: (String) -> Void
    private let onPrepareCourseRound: (Int, String, String, String) -> Void
    private let onPrepareCompositeRound: (Int, Int, String, String) -> Void
    private let onFinishRound: () async -> Bool
    private let onDiscardRound: () -> Void
    private let onAdvanceHole: (Int) -> Void
    private let onLiveHoleInitialLoadDidFinish: () -> Void

    @StateObject private var locationProvider = LocationProvider()
    @State private var score: Int
    @State private var puttCount: Int = 2
    @State private var penaltyCount: Int = 0
    @State private var selectedClub: String
    @State private var hasUserSelectedClub = false
    @State private var selectedShotType: String
    @State private var selectedStrategyMode: String = "stock"
    @State private var holePrep: CoursePrepHole?
    @State private var distanceToPinText: String = ""
    @State private var selectedLie: String = "fairway"
    @State private var currentCoordinate: CLLocationCoordinate2D?
    /// A manually chosen Touch Target point.  This is intentionally separate from the movable
    /// green flag below: S70's Touch Target and View Green are two different instruments.
    @State private var targetCoordinate: CLLocationCoordinate2D?
    /// Overlay pixel for a Touch Target.  Unlike the optional coordinate, this remains usable when
    /// a searched course has a map but no geo projection anchors or GPS fix yet.
    @State private var targetPixel: CGPoint?
    /// The per-round flag position edited on the View Green surface.  `nil` means use the factual
    /// provider/geometry pin carried by `mapPinCoordinate`.
    @State private var greenPinCoordinate: CLLocationCoordinate2D?
    /// Full-hole topo pixel for a manually moved flag. This remains usable when the map has no
    /// affine geo anchors; it is session-local and never becomes a GPS/event coordinate by itself.
    @State private var greenPinPixel: CGPoint?
    @State private var targetKind: String?
    /// The legacy wire contract has one target tuple.  Keep track of which instrument was edited
    /// last so a Watch/old server receives the tuple the golfer is looking at, without making the
    /// two on-screen coordinates share storage again.
    @State private var lastTargetEditKind: String?
    @State private var currentHorizontalAccuracyM: Double?
    @State private var note: String = ""
    @State private var caddieDecision: CaddieDecisionResponse?
    @State private var isLoadingCaddieDecision = false
    @State private var caddieErrorMessage: String?
    @State private var visionFindings: [[String: JSONValue]] = []
    @State private var lastAppliedRestoredHoleState: LiveHoleStateSnapshot?
    @State private var showManage = false
    @State private var showRoundSummary = false
    @State private var showDiscardConfirmation = false
    @State private var showCaddieDetail = false
    @State private var showMapDetail = false
    @State private var showGreenDetail = false
    @State private var scoreDraft: LiveScoreDraft?
    @State private var showScorecard = false
    @State private var gpsHoleCandidate: LiveHoleGPSCandidate?
    @State private var pendingHistoricalScoreHole: Int?
    @State private var pendingPhoneShot: PendingPhoneShot?
    @State private var holeRootScrollRequest = 0

    private static let holeRootScrollAnchor = "live-hole-root"

    private var liveHeroHeight: CGFloat {
        // The previous fixed 360pt card made the factual hole map a thumbnail. Keep the first screen
        // map-led on every phone while leaving enough of the distance instrument visible below it.
        #if canImport(UIKit)
        min(max(UIScreen.main.bounds.height * 0.60, 480), 590)
        #else
        520
        #endif
    }

    public init(
        package: LiveRoundPackage,
        hole: Hole,
        caddieBaseURL: URL? = nil,
        adminToken: String? = nil,
        caddieClient: CaddieDecisionClient? = nil,
        offlineStore: OfflineStore? = nil,
        watchBridge: WatchEventBridge? = nil,
        liveRoundState: LiveRoundStateSnapshot? = nil,
        courseOptions: [MobileCourseOption] = [],
        startingNine: String? = nil,
        isPreparingRound: Bool = false,
        pendingEventCount: Int = 0,
        isFinishingRound: Bool = false,
        finishErrorMessage: String? = nil,
        onChangeNine: @escaping (String) -> Void = { _ in },
        onPrepareCourseRound: @escaping (Int, String, String, String) -> Void = { _, _, _, _ in },
        onPrepareCompositeRound: @escaping (Int, Int, String, String) -> Void = { _, _, _, _ in },
        onFinishRound: @escaping () async -> Bool = { false },
        onDiscardRound: @escaping () -> Void = {},
        onAdvanceHole: @escaping (Int) -> Void = { _ in },
        onLiveHoleInitialLoadDidFinish: @escaping () -> Void = {},
        onRetainReadyHolePrep: @escaping (String, Int, CoursePrepHole) -> Void = { _, _, _ in },
        onEvent: @escaping (LiveRoundEvent) -> Void = { _ in }
    ) {
        self.package = package
        self.hole = hole
        self.onEvent = onEvent
        self.caddieClient = caddieClient ?? caddieBaseURL.map { CaddieDecisionClient(baseURL: $0, adminToken: adminToken) }
        self.mediaUploadClient = caddieBaseURL.map { MediaUploadClient(baseURL: $0, adminToken: adminToken) }
        self.caddieBaseURL = caddieBaseURL
        self.adminToken = adminToken
        self.offlineStore = offlineStore
        self.watchBridge = watchBridge
        self.liveRoundState = liveRoundState
        self.courseOptions = courseOptions
        self.startingNine = startingNine
        self.isPreparingRound = isPreparingRound
        self.pendingEventCount = pendingEventCount
        self.isFinishingRound = isFinishingRound
        self.finishErrorMessage = finishErrorMessage
        self.onChangeNine = onChangeNine
        self.onPrepareCourseRound = onPrepareCourseRound
        self.onPrepareCompositeRound = onPrepareCompositeRound
        self.onFinishRound = onFinishRound
        self.onDiscardRound = onDiscardRound
        self.onAdvanceHole = onAdvanceHole
        self.onLiveHoleInitialLoadDidFinish = onLiveHoleInitialLoadDidFinish
        self.onRetainReadyHolePrep = onRetainReadyHolePrep
        let seed = package.caddieContextSeeds.first { $0.hole == hole.number }
        let restoredHoleState = liveRoundState?.holeState(for: hole.number)
        let restoredTarget = Self.restoredTarget(from: restoredHoleState)
        let restoredManualTarget = restoredTarget?.kind == "pin" ? nil : restoredTarget
        let restoredGreenPin = restoredTarget?.kind == "pin" ? restoredTarget?.coordinate : nil
        self._score = State(initialValue: restoredHoleState?.score ?? hole.par)
        self._puttCount = State(initialValue: restoredHoleState?.putts ?? 2)
        self._penaltyCount = State(initialValue: restoredHoleState?.penaltyCount ?? 0)
        self._selectedClub = State(initialValue: restoredHoleState.map { zhClubName($0.selectedClub) }
            ?? Self.defaultClub(par: hole.par, holeYards: hole.yards, profiles: package.clubProfiles))
        self._selectedShotType = State(initialValue: restoredHoleState?.selectedShotType ?? seed?.shotTypes.first ?? "approach")
        self._selectedStrategyMode = State(initialValue: restoredHoleState?.selectedStrategyMode ?? "stock")
        self._distanceToPinText = State(initialValue: Self.validDistanceText(restoredHoleState?.distanceToPinM))
        self._selectedLie = State(initialValue: restoredHoleState?.lie ?? "fairway")
        self._holePrep = State(
            initialValue: package.coursePrep?.holes.first { $0.hole == hole.number }
        )
        self._currentHorizontalAccuracyM = State(initialValue: restoredHoleState?.horizontalAccuracyM)
        self._lastAppliedRestoredHoleState = State(initialValue: restoredHoleState)
        self._gpsHoleCandidate = State(initialValue: nil)
        self._scoreDraft = State(
            initialValue: offlineStore.flatMap { try? $0.loadLiveScoreDraft(roundId: package.roundId) }
        )
        if let latitude = restoredHoleState?.latitude, let longitude = restoredHoleState?.longitude {
            self._currentCoordinate = State(initialValue: CLLocationCoordinate2D(latitude: latitude, longitude: longitude))
        } else {
            self._currentCoordinate = State(initialValue: nil)
        }
        if let restoredManualTarget {
            self._targetCoordinate = State(initialValue: restoredManualTarget.coordinate)
        } else {
            self._targetCoordinate = State(initialValue: nil)
        }
        self._targetPixel = State(initialValue: nil)
        self._greenPinCoordinate = State(initialValue: restoredGreenPin)
        self._greenPinPixel = State(initialValue: nil)
        self._targetKind = State(initialValue: restoredManualTarget?.kind)
        self._lastTargetEditKind = State(initialValue: restoredTarget?.kind)
    }

    public var body: some View {
        liveHoleContent
        // The app shell is intentionally light, but this approved live-play surface is dark.
        // Request dark system chrome here so the status-bar time, network, and battery stay visible.
        .preferredColorScheme(.dark)
        // The map owns the live surface and supplies a stable navigation-style return row. The
        // inherited NavigationStack label is intentionally hidden because it can expose a stale
        // greeting from the round home rather than the approved live-play hierarchy.
        .toolbar(.hidden, for: .navigationBar)
        .navigationBarBackButtonHidden(true)
        .onAppear {
            #if DEBUG
            UITestEventLatencyTrace.record(
                "live-hole.appear hole=\(hole.number) course=\(package.course.globalId)"
            )
            #endif
            locationProvider.requestAuthorization()
            locationProvider.startUpdatingLocation()
        }
        .onReceive(locationProvider.$latestFix) { latestFix in
            guard let latestFix else {
                return
            }
            currentCoordinate = latestFix.coordinate
            currentHorizontalAccuracyM = latestFix.horizontalAccuracyM
            gpsHoleCandidate = LiveHoleGPSResolver.candidate(
                holes: package.holes,
                coordinate: latestFix.coordinate,
                horizontalAccuracyM: latestFix.horizontalAccuracyM
            )
            // watch P1c: push the live position to the watch so its hole-map 「你」 pans as you walk. Only
            // when the hole map is up (holePrep loaded) — avoids chatter before the round view is ready.
            if holePrep != nil {
                sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
            }
        }
        .task(id: hole.number) {
            #if DEBUG
            // The package already carries factual Tee coordinates for every ready hole. Move the
            // deterministic multi-hole simulator journey before waiting on the per-hole prep GET;
            // otherwise the new hole can appear with shot capture disabled for the whole request.
            moveSimulatedLocationToHoleTeeIfRequested(hole)
            UITestEventLatencyTrace.record(
                "live-hole.load.begin hole=\(hole.number) course=\(package.course.globalId)"
            )
            #endif
            // One ordered bootstrap per hole: first establish the real map/F/M/B context, then make
            // exactly one initial online caddie request from that context. The prior pair of sibling
            // tasks issued a distance-free request and a replacement request concurrently, allowing
            // a cancelled stale request to flash a false "联网不可用" state over the good response.
            await loadCurrentHole()
            #if DEBUG
            UITestEventLatencyTrace.record(
                "live-hole.load.end hole=\(hole.number) course=\(package.course.globalId)"
            )
            #endif
        }
        .onChange(of: liveRoundState) { _, newState in
            applyRestoredStateIfNeeded(newState)
        }
        .onChange(of: selectedStrategyMode) { _, _ in
            // Changing strategy re-plans the shot → adopt the new strategy's recommended club so the
            // club strip + landing marker move with it (保守/激进 选不同杆,图上的落点要跟着变).
            Task { await loadCaddieDecision(syncClub: true) }
        }
        .fullScreenCover(isPresented: $showCaddieDetail) {
            caddieDetailSurface
        }
        .fullScreenCover(isPresented: $showMapDetail) {
            mapDetailSurface
        }
        .fullScreenCover(isPresented: $showGreenDetail) {
            greenDetailSurface
        }
        .sheet(item: $scoreDraft) { presentedDraft in
            scoreConfirmationSurface(for: presentedDraft)
        }
        .sheet(item: $pendingPhoneShot, onDismiss: {
            // Recording starts from the lower action panel. After selecting or skipping the optional
            // club, restore the S70-style Hole Root instead of leaving the player below the map.
            holeRootScrollRequest += 1
        }) { pendingShot in
            actualClubPromptSurface(for: pendingShot)
        }
        .sheet(isPresented: $showScorecard, onDismiss: presentPendingHistoricalScoreEdit) {
            scorecardSurface
        }
        .sheet(isPresented: $showRoundSummary) {
            roundSummarySurface
        }
        .confirmationDialog(
            "放弃这场球局？",
            isPresented: $showDiscardConfirmation,
            titleVisibility: .visible
        ) {
            Button("放弃并删除本场记录", role: .destructive) {
                onDiscardRound()
                dismiss()
            }
            Button("继续打球", role: .cancel) {}
        } message: {
            Text("未保存到历史的本场成绩、落点和待上传媒体将被删除。")
        }
    }

    // Keep the large live-play layout in its own opaque view boundary. Besides making the
    // hierarchy easier to read, this prevents SwiftUI's modifier chain in `body` from forcing the
    // compiler to infer every map, panel, and sheet expression as one type-checking problem.
    private var liveHoleContent: some View {
        ZStack {
            LivePlayStyle.base.ignoresSafeArea()
            liveHoleScrollView
            #if DEBUG
            offlineReadyMarker
            #endif
        }
    }

    private var liveHoleScrollView: some View {
        ScrollViewReader { scrollProxy in
            ScrollView(showsIndicators: false) {
                liveHoleStack
                    .padding(.bottom, 24)
            }
            .onChange(of: holeRootScrollRequest) { _, _ in
                withAnimation(.easeOut(duration: 0.22)) {
                    scrollProxy.scrollTo(Self.holeRootScrollAnchor, anchor: .top)
                }
            }
        }
    }

    private var liveHoleStack: some View {
        VStack(spacing: 0) {
            heroSection
                .id(Self.holeRootScrollAnchor)
            livePrimaryPanel
            liveSecondaryCards
        }
    }

    private var livePrimaryPanel: some View {
        // Dark-glass data panel: distance hero → caddie strip → shot/score actions → tab bar.
        LivePlayPanel {
            LiveCaddieStrip(
                clubs: caddieClubChips,
                playsText: caddiePlaysText,
                isLoading: isLoadingCaddieDecision || isPreciseHoleMapPending,
                isReady: caddieDecision != nil
                    && !isPreciseHoleMapPending
                    && !isLoadingCaddieDecision,
                errorText: isPreciseHoleMapPending
                    ? "精确地图准备中 · 球童建议稍后更新"
                    : caddieErrorMessage,
                onExpand: { showCaddieDetail = true },
                onSelect: { selectClub($0) }
            )
            LiveHolePrimaryActions(
                canRecordShot: liveCoordinateForCurrentHole != nil,
                recordedShotCount: recordedNonPuttShotCount,
                onRecordShot: recordShotLocation,
                onConfirmScore: beginScoreConfirmation
            )
            LiveScorecardButton(onTap: { showScorecard = true })
        }
        .padding(.horizontal, 10)
        .padding(.top, -22)
        .zIndex(2)
    }

    private var liveSecondaryCards: some View {
        // Secondary live controls remain part of the dark playing instrument.
        VStack(spacing: 12) {
            moreAdjustCard
            mediaCard
            manageSection
        }
        .padding(.horizontal, 14)
        .padding(.top, 16)
    }

    #if DEBUG
    @ViewBuilder
    private var offlineReadyMarker: some View {
        if package.hasCompleteOfflineCoursePrep,
           offlineStore?.hasCourseTopoImages(for: package) == true {
            Text("离线地图已准备")
                .font(.system(size: 1))
                .foregroundStyle(Color.white.opacity(0.02))
                .frame(width: 1, height: 1)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("离线地图已准备")
                .accessibilityIdentifier("live-hole-offline-course-ready")
        }
    }
    #endif

    @ViewBuilder
    private var mapDetailSurface: some View {
        if let holePrep {
            LivePlayMapDetailView(
                hole: holePrep,
                topoURL: liveTopoURL,
                selectedClub: selectedClub,
                selectedClubMetres: selectedClubMetres,
                targetCoordinate: $targetCoordinate,
                referenceCoordinate: mapReferenceCoordinate,
                referenceIsLive: mapReferenceIsLive,
                pinCoordinate: effectiveMapPinCoordinate,
                onTargetChanged: { coordinate in
                    handleMapTargetChanged(coordinate, kind: "target")
                },
                onTargetCommitted: { coordinate in
                    handleMapTargetCommitted(coordinate, kind: "target")
                },
                targetPixel: $targetPixel,
                onTargetPixelChanged: { pixel in
                    handleMapTargetPixelChanged(pixel, kind: "target")
                },
                onTargetPixelCommitted: { pixel in
                    handleMapTargetPixelCommitted(pixel, kind: "target")
                }
            )
        } else {
            ZStack {
                LivePlayStyle.base.ignoresSafeArea()
                ProgressView("地图准备中…")
                    .tint(.white)
                    .foregroundStyle(.white)
            }
        }
    }

    @ViewBuilder
    private var greenDetailSurface: some View {
        if let holePrep {
            LiveGreenDetailView(
                hole: holePrep,
                detailURL: greenDetailURL,
                topoURL: liveTopoURL,
                targetCoordinate: $greenPinCoordinate,
                targetPixel: $greenPinPixel,
                referenceCoordinate: mapReferenceCoordinate,
                referenceIsLive: mapReferenceIsLive,
                pinCoordinate: mapPinCoordinate,
                onTargetChanged: { coordinate in
                    handleMapTargetChanged(coordinate, kind: "pin")
                },
                onTargetCommitted: { coordinate in
                    handleMapTargetCommitted(coordinate, kind: "pin")
                },
                onTargetPixelChanged: { pixel in
                    handleMapTargetPixelChanged(pixel, kind: "pin")
                },
                onTargetPixelCommitted: { pixel in
                    handleMapTargetPixelCommitted(pixel, kind: "pin")
                }
            )
        } else {
            ZStack {
                LivePlayStyle.base.ignoresSafeArea()
                ProgressView("果岭地图准备中…")
                    .tint(.white)
                    .foregroundStyle(.white)
            }
        }
    }

    private func scoreConfirmationSurface(for presentedDraft: LiveScoreDraft) -> some View {
        LiveScoreConfirmationView(
            draft: Binding(
                get: { scoreDraft ?? presentedDraft },
                set: { next in
                    scoreDraft = next
                    if let offlineStore {
                        try? offlineStore.saveLiveScoreDraft(roundId: package.roundId, draft: next)
                    }
                }
            ),
            nextHole: presentedDraft.advanceAfterSave ? nextHole(after: presentedDraft.hole) : nil,
            onAccept: acceptScoreConfirmation,
            onCancel: cancelScoreConfirmation
        )
    }

    private func actualClubPromptSurface(for pendingShot: PendingPhoneShot) -> some View {
        LiveActualClubPromptView(
            shotNumber: pendingShot.shotOrder,
            choices: actualClubChoices,
            onSelect: { club in recordActualClub(club, for: pendingShot) },
            onSkip: { pendingPhoneShot = nil }
        )
    }

    private var scorecardSurface: some View {
        LiveRoundScorecardView(
            courseName: package.course.name,
            holes: package.holes,
            liveRoundState: liveRoundState,
            recordedScoreHoles: recordedScoreHoles,
            gpsCandidate: gpsHoleCandidate,
            onGoToHole: { selectedHole in
                showScorecard = false
                onAdvanceHole(selectedHole)
            },
            onEdit: { selectedHole in
                pendingHistoricalScoreHole = selectedHole
                showScorecard = false
            }
        )
    }

    private var roundSummarySurface: some View {
        LiveRoundFinishSummaryView(
            courseName: package.course.name,
            holesCompleted: completedHoleStates.count,
            holeCount: package.holes.count,
            totalStrokes: completedHoleStates.reduce(0) { $0 + $1.state.score },
            toPar: completedHoleStates.isEmpty
                ? nil
                : completedHoleStates.reduce(0) { $0 + $1.state.score - $1.hole.par },
            totalPutts: completedHoleStates.reduce(0) { $0 + $1.state.putts },
            fairwaysHit: completedHoleStates.filter { $0.state.fairwayResult == LiveFairwayResult.hit.rawValue }.count,
            fairwaysRecorded: completedHoleStates.filter { $0.hole.par != 3 && $0.state.fairwayResult != nil }.count,
            totalPenalties: completedHoleStates.reduce(0) { $0 + $1.state.penaltyCount },
            pendingEventCount: pendingEventCount,
            isFinishingRound: isFinishingRound,
            finishErrorMessage: finishErrorMessage,
            onFinish: {
                Task {
                    if await onFinishRound() {
                        showRoundSummary = false
                    }
                }
            },
            onContinue: { showRoundSummary = false },
            onDiscard: {
                showRoundSummary = false
                showDiscardConfirmation = true
            }
        )
    }

    private var caddieContextSeed: CaddieContextSeed? {
        package.caddieContextSeeds.first { $0.hole == hole.number }
    }

    // MARK: - 打球屏 v2 hero (map backdrop + header + overlays)

    /// Map-as-backdrop hero: the server-rendered hole image (推荐打法叠加) fills the top, with the
    /// header, a green crosshair reticle on the green, and one amber hazard carry pill over it.
    private var heroSection: some View {
        ZStack(alignment: .top) {
            liveMapBackdrop
                .padding(.top, LivePlayMapOverlayLayout.liveMapTopInset)
                .frame(height: liveHeroHeight)
                .frame(maxWidth: .infinity)
                .clipped()
            LivePlayStyle.topScrim
                .frame(height: 176)
                .frame(maxWidth: .infinity, alignment: .top)
                .allowsHitTesting(false)
            GeometryReader { geo in
                let greenTarget = liveGreenTarget(in: geo.size)
                ZStack {
                    LivePlayReticle()
                        .position(
                            greenTarget ?? LivePlayMapOverlayLayout.fallbackGreenTarget(in: geo.size)
                        )

                    LiveMapGreenDistanceOverlay(
                        frontYards: liveGreenYards?.front ?? greenYards(liveGreenDistances?.frontM),
                        middleYards: liveGreenYards?.middle ?? greenYards(liveGreenDistances?.middleM),
                        backYards: liveGreenYards?.back ?? greenYards(liveGreenDistances?.backM),
                        toPinYards: displayedTargetYards,
                        isLive: isGreenRangeLive
                    )
                    .position(x: min(118, geo.size.width * 0.31), y: 137)

                    ForEach(Array(liveMapHazardAnnotations.prefix(2).enumerated()), id: \.element.id) { index, annotation in
                        if let front = liveMapTarget(annotation.frontPx, in: geo.size),
                           let back = liveMapTarget(annotation.backPx, in: geo.size) {
                            LiveMapHazardRangeOverlay(
                                kind: annotation.kind,
                                label: annotation.label,
                                toYards: annotation.toYards,
                                overYards: annotation.overYards,
                                front: front,
                                back: back,
                                index: index,
                                viewportSize: geo.size
                            )
                        }
                    }
                    if isPreciseHoleMapPending {
                        LiveMapPreparingPill()
                            .position(x: geo.size.width * 0.5, y: geo.size.height * 0.88)
                    }
                    if let player = livePlayerTarget(in: geo.size) {
                        LivePlayerPositionMarker()
                            .position(player)
                    }
                }
            }
            .frame(height: liveHeroHeight)
            .allowsHitTesting(false)
            // The hero is the first map instrument, so a player should not have to find the
            // secondary "更多调整" disclosure before opening Touch Target. Keep this transparent
            // layer below the header (which is declared next) and above the decorative overlays;
            // the panel below the hero has its own higher z-index and keeps its buttons tappable.
            Rectangle()
                .fill(.clear)
                .frame(maxWidth: .infinity)
                .frame(height: max(liveHeroHeight - LivePlayMapOverlayLayout.liveMapTopInset, 1))
                .offset(y: LivePlayMapOverlayLayout.liveMapTopInset / 2)
                .contentShape(Rectangle())
                .onTapGesture { showMapDetail = true }
                .accessibilityLabel("打开地图并选目标")
                .accessibilityIdentifier("live-open-map-from-hero")
            LivePlayHeader(
                holeNumber: hole.number,
                par: hole.par,
                yards: hole.yards,
                teeLabel: teeLabelZh,
                roundToParText: roundToParText,
                onBack: { dismiss() },
                onFinishRound: { showRoundSummary = true },
                onOpenMap: { showMapDetail = true }
            )
            .padding(.horizontal, 20)
            .padding(.top, 4)
        }
        .frame(height: liveHeroHeight)
    }

    /// 球洞俯视图(2D):服务端渲染的真实球场图 + 推荐打法叠加。无图时回退暗色渐变占位。
    @ViewBuilder private var liveMapBackdrop: some View {
        if let holePrep, holePrep.resolvedMapOverlay != nil {
            HoleImageMapView(hole: holePrep, selectedClub: selectedClub, selectedClubMetres: selectedClubMetres,
                             topoURL: liveTopoURL, showsCardChrome: false,
                             showsRecommendedRoute: true,
                             showsHazards: true)
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(
                    holePrep.geometryCoverage.caseInsensitiveCompare("partial") == .orderedSame
                        ? "live-hole-map-partial"
                        : "live-hole-map-\(holePrep.geometryCoverage.lowercased())"
                )
        } else {
            LinearGradient(
                colors: [Color(red: 26 / 255, green: 46 / 255, blue: 30 / 255), LivePlayStyle.base],
                startPoint: .top, endPoint: .bottom
            )
        }
    }

    // MARK: - Focused caddie plan + secondary dark cards

    /// Approved full-hole plan hierarchy: one light, focused surface containing exactly the three
    /// complete route cards. It deliberately does not repeat the live distance/actions panel.
    private var caddieDetailSurface: some View {
        ZStack {
            Color.white.ignoresSafeArea()
            ScrollView(showsIndicators: false) {
                VStack(alignment: .leading, spacing: 12) {
                    if let caddieDecision {
                        CaddiePlanView(
                            response: caddieDecision,
                            hazards: caddiePlanHazards,
                            onSelectStrategyMode: { selectedStrategyMode = $0 }
                        )
                    } else {
                        CaddiePlanView(
                            seed: caddieContextSeed,
                            hazards: caddiePlanHazards,
                            onSelectStrategyMode: { selectedStrategyMode = $0 }
                        )
                    }
                    if isLoadingCaddieDecision {
                        ProgressView("更新球童建议…")
                    }
                    if let caddieErrorMessage {
                        Text(caddieErrorMessage)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Button {
                        Task { await loadCaddieDecision() }
                    } label: {
                        Label("刷新球童", systemImage: "arrow.clockwise")
                            .font(.subheadline)
                    }
                    .disabled(isLoadingCaddieDecision)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .safeAreaPadding(.bottom, 12)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .safeAreaInset(edge: .top, spacing: 0) {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("球童完整方案")
                        .font(.title2.weight(.bold))
                    Text("第 \(hole.number) 洞 · Par \(hole.par)")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
                Button {
                    showCaddieDetail = false
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.title2)
                        .foregroundStyle(.secondary)
                        .frame(width: 44, height: 44)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("关闭球童方案")
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 4)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.white)
            .overlay(alignment: .bottom) { Divider() }
        }
        .tint(LiveHoleStyle.green)
        .preferredColorScheme(.light)
    }

    /// All the original secondary inputs are preserved, tucked into 更多调整.
    private var moreAdjustCard: some View {
        DisclosureGroup {
            VStack(spacing: 10) {
                HStack(alignment: .firstTextBaseline) {
                    Text("选球杆").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    clubPickerMenu  // round-12: 全杆下拉,默认推荐杆,选完即记
                }
                Picker("打法", selection: $selectedShotType) {
                    ForEach(shotTypeOptions, id: \.self) { Text(zhShotType($0)).tag($0) }
                }
                Picker("球位", selection: $selectedLie) {
                    ForEach(lieOptions, id: \.self) { Text(zhLie($0)).tag($0) }
                }
                TextField("到旗杆距离(码)", text: $distanceToPinText)
                    .keyboardType(.decimalPad)
                Button {
                    targetCoordinate = currentCoordinate
                    targetPixel = nil
                    targetKind = currentCoordinate == nil ? nil : "target"
                    lastTargetEditKind = currentCoordinate == nil ? nil : "target"
                    if currentCoordinate != nil {
                        distanceToPinText = ""
                        persistMapTarget(coordinate: targetCoordinate, kind: "target")
                        Task { await loadCaddieDecision(syncClub: !hasUserSelectedClub) }
                    }
                } label: {
                    Label("设为目标点", systemImage: "mappin.and.ellipse")
                }
                .disabled(currentCoordinate == nil)
                Button {
                    showMapDetail = true
                } label: {
                    Label("打开地图选目标", systemImage: "map")
                }
                Button {
                    showGreenDetail = true
                } label: {
                    Label("放大果岭 / 拖动旗位", systemImage: "flag.fill")
                }
                Stepper("罚杆 \(penaltyCount)", value: $penaltyCount, in: 0...4)
                TextField("备注", text: $note)
            }
            .padding(.top, 6)
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                Label("更多调整", systemImage: "slider.horizontal.3")
                    .font(.headline)
                Text("球杆 · 打法 · 球位 · 距离 · 目标 · 备注")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.85)
            }
        }
        .livePlayAuxiliaryCard()
    }

    /// Media capture (unchanged behavior).
    private var mediaCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("拍照取证").font(.caption).foregroundStyle(.secondary)
            MediaCaptureView(
                roundId: package.roundId,
                hole: hole.number,
                targetId: caddieContextSeed?.sourceRef ?? "\(package.roundId):\(hole.number)",
                offlineStore: offlineStore,
                uploadClient: mediaUploadClient,
                onEvent: onEvent,
                onVisionFindings: { findings in
                    visionFindings = findings
                    Task { await loadCaddieDecision() }
                }
            )
        }
        .livePlayAuxiliaryCard()
    }

    // MARK: - 打球屏 v2 display values (derived, read-only)

    /// 本场 to-par chip: sum of (score − par) over recorded holes; falls back to this hole's delta.
    private var roundToParText: String {
        let delta: Int
        if let holes = liveRoundState?.holes, !holes.isEmpty {
            delta = holes.reduce(0) { $0 + ($1.score - $1.par) }
        } else {
            delta = score - hole.par
        }
        if delta == 0 { return "本场 E" }
        return "本场 \(delta > 0 ? "+\(delta)" : "\(delta)")"
    }

    /// Tee colour label (蓝T/白T/…) from the round's teeBox; nil when unknown.
    private var teeLabelZh: String? {
        let map = [
            "blue": "蓝T", "white": "白T", "red": "红T", "gold": "金T",
            "black": "黑T", "green": "绿T", "yellow": "黄T", "silver": "银T",
        ]
        let tee = package.course.teeBox.lowercased()
        if let label = map[tee] { return label }
        return (tee.isEmpty || tee == "unknown") ? nil : package.course.teeBox
    }

    /// The caddie strip's club chips: the 3 most-relevant clubs + their distance, selected = filled.
    private var caddieClubChips: [LiveCaddieStrip.Club] {
        let bag = bagBest(filterTeeOnly: true)
        return clubNames.map { name in
            let sub = bag[name].map { "\(CoursePrepRoute.yards(fromMetres: $0.medianM)) 码" } ?? ""
            return LiveCaddieStrip.Club(name: name, sub: sub, on: name == selectedClub)
        }
    }

    /// One 实打 plays-like line for the caddie strip — only when the per-hole prep carries a real
    /// slope (never fabricated); nil otherwise.
    private var caddiePlaysText: String? {
        guard let playsLike = holePrep?.playsLike, playsLike.available, let deltaYd = playsLike.deltaYd, deltaYd != 0 else {
            return nil
        }
        return "坡度修正 \(deltaYd > 0 ? "+" : "")\(deltaYd) 码 · \(deltaYd > 0 ? "上坡" : "下坡")"
    }

    /// At most two upcoming, position-bound obstacles are shown on the large phone map. Live GPS
    /// ranges win; before the first qualified fix, the same measured edges retain their tee ranges.
    /// Legacy one-number hazards cannot be placed on an edge and therefore stay out of the overlay.
    private var liveMapHazardAnnotations: [LiveMapHazardAnnotation] {
        guard !isPreciseHoleMapPending, let holePrep else { return [] }
        if let live = liveHazardReadouts {
            return live.map {
                LiveMapHazardAnnotation(
                    id: $0.id,
                    kind: $0.kind,
                    label: $0.label,
                    toYards: $0.toYards,
                    overYards: $0.overYards,
                    frontPx: $0.frontPx,
                    backPx: $0.backPx
                )
            }
        }
        let route = holePrep.resolvedMapOverlay?.route
        return holePrep.hazards.details
            .filter { ($0.kind == "bunker" || $0.kind == "water")
                && $0.frontPx.count >= 2 && $0.backPx.count >= 2 }
            .sorted { $0.frontRouteM < $1.frontRouteM }
            .enumerated()
            .map { index, detail in
                LiveMapHazardAnnotation(
                    id: "\(detail.kind)-\(index)",
                    kind: detail.kind,
                    label: CoursePrepHazardNaming.label(kind: detail.kind, detail: detail, route: route),
                    toYards: CoursePrepRoute.yards(fromMetres: detail.frontM),
                    overYards: CoursePrepRoute.yards(fromMetres: detail.backM),
                    frontPx: detail.frontPx,
                    backPx: detail.backPx
                )
            }
    }

    /// CourseView's small package is a factual drawing source, but its hazard spans are not a
    /// completeness guarantee.  Keep map/distance play available while prodgeometry downloads,
    /// without presenting that provisional subset as the nearest-hazard or final caddie answer.
    private var isPreciseHoleMapPending: Bool {
        holePrep?.geometryCoverage.caseInsensitiveCompare("partial") == .orderedSame
    }

    /// 本洞真实地形底图 URL(与 `loadHoleMap` 用同一 source 球场 + 本地洞号:组合局后九在第二个环的
    /// gid)。给 `HoleImageMapView` 当底图;无后端地址/占位球场时为 nil → 回退到 payload flat 渲染图。
    private var liveTopoURL: URL? {
        guard holePrep?.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame else {
            return nil
        }
        let mapGlobalId = hole.sourceGlobalId ?? package.course.globalId
        let mapLocalHole = hole.sourceLocalHole ?? hole.number
        let geometryRevision = holePrep?.geometryRevision ?? hole.geometryRevision
        if let local = offlineStore?.loadCourseTopoImageURL(
            globalId: mapGlobalId,
            localHole: mapLocalHole,
            geometryRevision: geometryRevision
        ) {
            return local
        }
        #if DEBUG
        if ProcessInfo.processInfo.environment["UITEST_FORCE_LIVE_NETWORK_FAILURE"] == "1" {
            return nil
        }
        #endif
        guard let caddieBaseURL else { return nil }
        return SyncClient.topoImageURL(
            baseURL: caddieBaseURL,
            globalId: mapGlobalId,
            localHole: mapLocalHole,
            geometryRevision: geometryRevision
        )
    }

    private var greenDetailURL: URL? {
        guard let caddieBaseURL,
              let prep = holePrep,
              let outline = prep.greenOutline,
              outline.available,
              let projection = prep.holeImageProjection,
              let width = projection.widthPx,
              let height = projection.heightPx,
              let crop = GreenDetailCrop.around(
                  points: outline.pointsPx,
                  imageWidth: Double(width),
                  imageHeight: Double(height)
              ) else { return nil }
        let mapGlobalId = hole.sourceGlobalId ?? package.course.globalId
        let mapLocalHole = hole.sourceLocalHole ?? hole.number
        return SyncClient.greenDetailImageURL(
            baseURL: caddieBaseURL,
            globalId: mapGlobalId,
            localHole: mapLocalHole,
            crop: crop,
            geometryRevision: prep.geometryRevision
        )
    }

    /// The route endpoint is the selected green target used by the shared map render. Projecting it
    /// here keeps the live target ring on that real green instead of at one fixed screen coordinate.
    private func liveGreenTarget(in heroSize: CGSize) -> CGPoint? {
        guard let overlay = holePrep?.resolvedMapOverlay else { return nil }
        if let movedPin = greenPinPixel,
           movedPin.x.isFinite,
           movedPin.y.isFinite,
           let point = LivePlayMapOverlayLayout.project(
               overlayPoint: [Double(movedPin.x), Double(movedPin.y)],
               overlayWidth: overlay.w,
               overlayHeight: overlay.h,
               into: heroSize,
               topInset: LivePlayMapOverlayLayout.liveMapTopInset
           ) {
            return point
        }
        if let movedPin = greenPinCoordinate,
           let refs = holePrep?.holeImageProjection?.refs,
           let projected = WatchEventBridge.projectToTopoPx(
               lat: movedPin.latitude,
               lon: movedPin.longitude,
               refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
           ),
           let point = LivePlayMapOverlayLayout.project(
               overlayPoint: projected,
               overlayWidth: overlay.w,
               overlayHeight: overlay.h,
               into: heroSize,
               topInset: LivePlayMapOverlayLayout.liveMapTopInset
           ) {
            return point
        }
        guard let greenTarget = overlay.route.last else { return nil }
        return LivePlayMapOverlayLayout.project(
            overlayPoint: greenTarget,
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            into: heroSize,
            topInset: LivePlayMapOverlayLayout.liveMapTopInset
        )
    }

    /// Project any topo-pixel fact through exactly the same aspect-fit transform as the bitmap.
    private func liveMapTarget(_ overlayPoint: [Double], in heroSize: CGSize) -> CGPoint? {
        guard let overlay = holePrep?.resolvedMapOverlay else { return nil }
        return LivePlayMapOverlayLayout.project(
            overlayPoint: overlayPoint,
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            into: heroSize,
            topInset: LivePlayMapOverlayLayout.liveMapTopInset
        )
    }

    private func livePlayerTarget(in heroSize: CGSize) -> CGPoint? {
        guard let currentCoordinate = liveCoordinateForCurrentHole,
              let overlay = holePrep?.resolvedMapOverlay,
              let refs = holePrep?.holeImageProjection?.refs,
              refs.count >= 3,
              let point = WatchEventBridge.projectToTopoPx(
                  lat: currentCoordinate.latitude,
                  lon: currentCoordinate.longitude,
                  refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
              ) else { return nil }
        return LivePlayMapOverlayLayout.project(
            overlayPoint: point,
            overlayWidth: overlay.w,
            overlayHeight: overlay.h,
            into: heroSize,
            topInset: LivePlayMapOverlayLayout.liveMapTopInset
        )
    }

    /// Touch Target uses the live fix when it is plausibly on this hole. Without GPS it falls back
    /// to the factual Tee anchor carried by the package or reconstructed from the map projection;
    /// this is a display/reference coordinate only and is never sent as `currentLocation`.
    private var mapReferenceCoordinate: CLLocationCoordinate2D? {
        if mapReferenceIsLive, let currentCoordinate {
            return currentCoordinate
        }
        if let latitude = hole.teeLatitude, let longitude = hole.teeLongitude,
           latitude.isFinite, longitude.isFinite,
           (-90...90).contains(latitude), (-180...180).contains(longitude) {
            return CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
        }
        guard let prep = holePrep,
              let first = prep.resolvedMapOverlay?.route.first,
              first.count >= 2,
              let refs = prep.holeImageProjection?.refs else {
            return nil
        }
        let projected = WatchEventBridge.projectFromTopoPx(
            px: first[0],
            py: first[1],
            refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
        )
        return projected.map { CLLocationCoordinate2D(latitude: $0.latitude, longitude: $0.longitude) }
    }

    private var mapReferenceIsLive: Bool {
        hasPlausibleLiveFix
    }

    private var hasPlausibleLiveFix: Bool {
        guard let fix = locationProvider.latestFix else { return false }
        if gpsHoleCandidate?.hole == hole.number { return true }
        guard let green = liveGreenDistances,
              let latitude = green.middleLat,
              let longitude = green.middleLon else { return false }
        let metres = GeoDistance.haversineMetres(
            fix.coordinate.latitude,
            fix.coordinate.longitude,
            latitude,
            longitude
        )
        return metres.isFinite && metres <= GeoDistance.maximumUsefulGreenMetres
    }

    private var mapPinCoordinate: CLLocationCoordinate2D? {
        if let prep = holePrep,
           let last = prep.resolvedMapOverlay?.route.last,
           last.count >= 2,
           let refs = prep.holeImageProjection?.refs,
           let projected = WatchEventBridge.projectFromTopoPx(
               px: last[0],
               py: last[1],
               refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
           ) {
            return CLLocationCoordinate2D(latitude: projected.latitude, longitude: projected.longitude)
        }
        if let green = liveGreenDistances,
           let latitude = green.middleLat,
           let longitude = green.middleLon {
            return CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
        }
        return nil
    }

    /// The pin shown by the map surfaces. A manually moved flag wins over the provider's factual
    /// route endpoint, while the latter remains the fallback for untouched holes.
    private var effectiveMapPinCoordinate: CLLocationCoordinate2D? {
        greenPinCoordinate ?? mapPinCoordinate
    }

    /// The legacy Watch/event payload has one coordinate tuple. Until that contract grows a second
    /// tuple, publish the instrument edited most recently. If that instrument is pixel-only (or was
    /// just cleared), fall back to the other coordinate-bearing instrument instead of clearing a
    /// still-visible flag/target. Pixel-only state remains local and is never promoted to WGS84.
    private var wireTargetSelection: (coordinate: CLLocationCoordinate2D, kind: String)? {
        let preferred = Self.normalizedTargetKind(lastTargetEditKind)

        func targetSelection() -> (coordinate: CLLocationCoordinate2D, kind: String)? {
            guard let coordinate = validTargetCoordinate(targetCoordinate) else { return nil }
            let kind = Self.normalizedTargetKind(targetKind)
            return (coordinate, kind == "pin" ? "target" : (kind ?? "target"))
        }

        func pinSelection() -> (coordinate: CLLocationCoordinate2D, kind: String)? {
            guard let coordinate = validTargetCoordinate(greenPinCoordinate) else { return nil }
            return (coordinate, "pin")
        }

        if preferred == "pin", let selection = pinSelection() { return selection }
        if preferred != "pin", let selection = targetSelection() { return selection }
        if let selection = targetSelection() { return selection }
        if let selection = pinSelection() { return selection }
        return nil
    }

    private var wireTargetCoordinate: CLLocationCoordinate2D? {
        wireTargetSelection?.coordinate
    }

    private var wireTargetKind: String? {
        wireTargetSelection?.kind
    }

    private func validTargetCoordinate(
        _ coordinate: CLLocationCoordinate2D?
    ) -> CLLocationCoordinate2D? {
        guard let coordinate,
              coordinate.latitude.isFinite,
              coordinate.longitude.isFinite,
              (-90...90).contains(coordinate.latitude),
              (-180...180).contains(coordinate.longitude) else {
            return nil
        }
        return coordinate
    }

    private func hasTargetState(for kind: String) -> Bool {
        if Self.normalizedTargetKind(kind) == "pin" {
            return greenPinCoordinate != nil || greenPinPixel != nil
        }
        return targetCoordinate != nil || targetPixel != nil
    }

    /// Keep the legacy preference aligned with the remaining local instruments after a clear. The
    /// pixel checks deliberately count as state so a no-projection edit remains the most-recent
    /// instrument locally, while `wireTargetSelection` still falls back to another real coordinate.
    private func refreshLastTargetEditKind(preferred: String?) {
        let preferred = Self.normalizedTargetKind(preferred)
        if preferred == "pin", hasTargetState(for: "pin") {
            lastTargetEditKind = "pin"
            return
        }
        if preferred != "pin", hasTargetState(for: "target") {
            lastTargetEditKind = "target"
            return
        }
        if hasTargetState(for: "target") {
            lastTargetEditKind = "target"
        } else if hasTargetState(for: "pin") {
            lastTargetEditKind = "pin"
        } else {
            lastTargetEditKind = nil
        }
    }

    /// Distance from the current map reference to a manually moved flag. This is deliberately not
    /// the same as `mapTargetDistanceMetres`: a Touch Target is an aim point, while a moved flag is
    /// the hole's endpoint.
    private var greenPinDistanceMetres: Double? {
        if let coordinateDistance = distanceFromMapReference(to: greenPinCoordinate) {
            return coordinateDistance
        }
        return pixelDistanceMetres(from: mapReferencePixel, to: validMapPixel(greenPinPixel))
    }

    private func distanceFromMapReference(to endpoint: CLLocationCoordinate2D?) -> Double? {
        guard let start = mapReferenceCoordinate, let endpoint else { return nil }
        let metres = GeoDistance.haversineMetres(
            start.latitude,
            start.longitude,
            endpoint.latitude,
            endpoint.longitude
        )
        guard metres.isFinite, metres > 0, metres <= GeoDistance.maximumUsefulGreenMetres else {
            return nil
        }
        return metres
    }

    private var mapTargetDistanceMetres: Double? {
        if let coordinateDistance = distanceFromMapReference(to: targetCoordinate) {
            return coordinateDistance
        }
        return pixelDistanceMetres(from: mapReferencePixel, to: validMapPixel(targetPixel))
    }

    /// The shared topo pixel frame is still measurable when a searched/off-course course has no
    /// affine geo anchors. Prefer a projected coordinate when available, then use the factual route
    /// endpoints as the tee/pin references.
    private var mapReferencePixel: CGPoint? {
        guard let overlay = holePrep?.resolvedMapOverlay else { return nil }
        if let reference = mapReferenceCoordinate,
           let refs = holePrep?.holeImageProjection?.refs,
           let projected = WatchEventBridge.projectToTopoPx(
               lat: reference.latitude,
               lon: reference.longitude,
               refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
           ),
           projected.count >= 2,
           projected[0].isFinite,
           projected[1].isFinite {
            return CGPoint(x: projected[0], y: projected[1])
        }
        guard let first = overlay.route.first,
              first.count >= 2,
              first[0].isFinite,
              first[1].isFinite else { return nil }
        return CGPoint(x: first[0], y: first[1])
    }

    private func pixelDistanceMetres(from start: CGPoint?, to end: CGPoint?) -> Double? {
        guard let start,
              let end,
              let ppm = holePrep?.resolvedMapOverlay?.ppm,
              ppm.isFinite,
              ppm > 0,
              start.x.isFinite,
              start.y.isFinite,
              end.x.isFinite,
              end.y.isFinite else { return nil }
        let metres = hypot(Double(end.x - start.x), Double(end.y - start.y)) / ppm
        guard metres.isFinite,
              metres >= 0,
              metres <= GeoDistance.maximumUsefulGreenMetres else { return nil }
        return metres
    }

    private func validMapPixel(_ pixel: CGPoint?) -> CGPoint? {
        guard let pixel,
              pixel.x.isFinite,
              pixel.y.isFinite,
              let overlay = holePrep?.resolvedMapOverlay,
              pixel.x >= 0,
              pixel.y >= 0,
              pixel.x <= CGFloat(overlay.w),
              pixel.y <= CGFloat(overlay.h) else { return nil }
        return pixel
    }

    private var displayedTargetYards: Int? {
        guard targetCoordinate != nil
                || targetPixel != nil
                || greenPinCoordinate != nil
                || greenPinPixel != nil
                || distanceToPinMetres != nil else {
            return nil
        }
        return effectiveDistanceToPinMetres.flatMap { greenYards($0) }
    }

    private func handleMapTargetChanged(_ coordinate: CLLocationCoordinate2D?, kind: String = "target") {
        let normalizedKind = Self.normalizedTargetKind(kind) ?? "target"
        if normalizedKind == "pin" {
            // View Green owns the flag binding. Never let a flag drag replace a Touch Target.
            greenPinCoordinate = coordinate
        } else {
            // Touch Target owns the manual aim point. Keep its kind separate from the flag state.
            targetCoordinate = coordinate
            targetKind = coordinate == nil ? nil : normalizedKind
        }
        if coordinate == nil {
            refreshLastTargetEditKind(preferred: normalizedKind)
        } else {
            lastTargetEditKind = normalizedKind
        }
        // A selected map point is the authoritative target for this request. Clear a previous text
        // override so the map and the caddie never describe different distances.
        if coordinate != nil || normalizedKind == "pin" {
            distanceToPinText = ""
        }
        // This callback runs for every drag frame. Keep the phone map/distance surface live locally;
        // the committed callback sends one complete Watch payload after the finger is released.
    }

    /// Pixel callbacks are deliberately separate from coordinate callbacks. A pixel is enough to
    /// keep the map and local distance instrument live, but it is never promoted to a fake WGS84/GPS
    /// event when projection refs are unavailable.
    private func handleMapTargetPixelChanged(_ pixel: CGPoint?, kind: String = "target") {
        let normalizedKind = Self.normalizedTargetKind(kind) ?? "target"
        if normalizedKind == "pin" {
            greenPinPixel = pixel
        } else {
            targetPixel = pixel
        }
        if let pixel {
            lastTargetEditKind = normalizedKind
            distanceToPinText = ""
        } else if normalizedKind == "pin" {
            greenPinCoordinate = nil
            refreshLastTargetEditKind(preferred: normalizedKind)
        } else {
            targetCoordinate = nil
            targetKind = nil
            refreshLastTargetEditKind(preferred: normalizedKind)
        }
        // Pixel updates also run once per drag frame, so defer cross-device delivery until commit.
    }

    private func handleMapTargetPixelCommitted(_ pixel: CGPoint?, kind: String = "target") {
        if pixel == nil {
            // Explicit clears are persisted by the coordinate commit. There is no second refresh
            // here: both detail surfaces emit coordinate + pixel callbacks for one gesture.
            return
        }

        // If the same gesture also produced a coordinate callback, that callback owns persistence.
        // Pixel-only edits stay session-local; the caddie still gets the new pixel-derived distance.
        let normalizedKind = Self.normalizedTargetKind(kind) ?? "target"
        let coordinate = normalizedKind == "pin" ? greenPinCoordinate : targetCoordinate
        guard coordinate == nil else { return }
        sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
        Task { await loadCaddieDecision(syncClub: !hasUserSelectedClub) }
    }

    private func handleMapTargetCommitted(_ coordinate: CLLocationCoordinate2D?, kind: String = "target") {
        let normalizedKind = Self.normalizedTargetKind(kind) ?? "target"
        // `applyTarget/applyFlag` emits a nil coordinate before its pixel callback when projection
        // anchors are unavailable. That is a pixel-only placement, not an explicit clear; wait for
        // the pixel commit and keep any other coordinate on the legacy wire tuple.
        let pixelOnlyPlacement = coordinate == nil && hasTargetState(for: normalizedKind)
        if !pixelOnlyPlacement {
            if let coordinate = validTargetCoordinate(coordinate) {
                let kind = normalizedKind == "pin"
                    ? "pin"
                    : (Self.normalizedTargetKind(targetKind) ?? normalizedKind)
                persistMapTarget(coordinate: coordinate, kind: kind)
            } else if let fallback = wireTargetSelection {
                // Clearing the most-recent instrument must not clear the other one from the
                // legacy single-tuple Watch/backend contract.
                persistMapTarget(coordinate: fallback.coordinate, kind: fallback.kind)
            } else {
                persistMapTarget(coordinate: nil, kind: "target")
            }
        }
        sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
        if !pixelOnlyPlacement {
            Task { await loadCaddieDecision(syncClub: !hasUserSelectedClub) }
        }
    }

    /// Persist target edits as a lightweight club/state event. It carries no latitude/longitude for
    /// the player, so offline map selection never masquerades as a GPS location event.
    private func persistMapTarget() {
        persistMapTarget(
            coordinate: targetCoordinate,
            kind: targetCoordinate == nil ? "target" : (targetKind ?? "target")
        )
    }

    private func persistMapTarget(coordinate: CLLocationCoordinate2D?, kind: String) {
        let timestamp = ISO8601DateFormatter().string(from: Date())
        let trimmedClub = selectedClub.trimmingCharacters(in: .whitespacesAndNewlines)
        // The club event contract requires a non-empty clubName. A target edit is still meaningful
        // before a club is chosen, so use an explicit compatibility placeholder; restore logic never
        // surfaces this placeholder as the selected club.
        let persistedClub = trimmedClub.isEmpty ? "unknown" : trimmedClub
        let targetDistance: Double? = {
            guard coordinate != nil else { return nil }
            if Self.normalizedTargetKind(kind) == "pin" {
                return distanceFromMapReference(to: coordinate)
            }
            return distanceFromMapReference(to: coordinate)
        }()
        var payload: [String: JSONValue] = [
            "clubName": .string(persistedClub),
            "targetLatitude": coordinate.map { .number($0.latitude) } ?? .null,
            "targetLongitude": coordinate.map { .number($0.longitude) } ?? .null,
            "targetKind": coordinate == nil ? .null : .string(Self.normalizedTargetKind(kind) ?? "target"),
            "distanceToPinM": targetDistance.map(JSONValue.number) ?? .null,
        ]
        payload["shotType"] = .string(selectedShotType)
        payload["strategyMode"] = .string(selectedStrategyMode)
        payload["lie"] = .string(selectedLie)
        emit(kind: .club, timestamp: timestamp, payload: payload)
    }

    @MainActor
    private func loadCurrentHole() async {
        isLoadingCaddieDecision = true
        let canPollForPreciseMap = await loadHoleMap()
        guard !Task.isCancelled else {
            isLoadingCaddieDecision = false
            return
        }
        // Sync the selected club to the recommendation on a fresh hole; a hole the player already
        // recorded keeps their actual choice.
        let alreadyRecorded = liveRoundState?.holeState(for: hole.number)?.selectedClub.isEmpty == false
        await loadCaddieDecision(
            syncClub: !alreadyRecorded && !isPreciseHoleMapPending && !hasUserSelectedClub
        )
        isLoadingCaddieDecision = false
        #if DEBUG
        UITestEventLatencyTrace.record(
            "live-hole.initial-load-finished hole=\(hole.number) course=\(package.course.globalId)"
        )
        #endif
        onLiveHoleInitialLoadDidFinish()

        // The package request has already queued prodgeometry in the backend. Keep the CourseView
        // vectors usable now, then replace only this hole's map facts when the precise mesh arrives.
        // The structured `.task(id: hole.number)` owns this loop, so changing holes or leaving the
        // screen cancels it without leaving a detached poller behind.
        if canPollForPreciseMap,
           holePrep?.geometryCoverage.caseInsensitiveCompare("partial") == .orderedSame {
            await waitForPreciseHoleMap(syncClub: !alreadyRecorded)
        }
    }

    private func loadHoleMap() async -> Bool {
        #if DEBUG
        if ProcessInfo.processInfo.environment["UITEST_FORCE_LIVE_NETWORK_FAILURE"] == "1" {
            return false
        }
        #endif
        guard let caddieBaseURL else {
            return false
        }
        // 每洞用自己的 source 球场 + 本地洞号(组合局后九在第二个环的 gid)。
        let mapGlobalId = hole.sourceGlobalId ?? package.course.globalId
        let mapLocalHole = hole.sourceLocalHole ?? hole.number
        guard mapGlobalId != 0 else {
            return false
        }
        let client = SyncClient(baseURL: caddieBaseURL, adminToken: adminToken)
        let lightweight: CoursePrepHole
        do {
            guard let fetched = try await client.fetchHolePrep(
                globalId: mapGlobalId,
                localHole: mapLocalHole
            ) else { return false }
            lightweight = fetched
        } catch {
            // Keep the package's retained prep facts. Returning false prevents the partial-map
            // upgrade loop from polling forever while the player is offline.
            return false
        }
        // Old cached/server payloads may lack the three topo anchors. Keep that compatibility path,
        // but never make current geometry pay the cold server-render cost that lost hole 4's facts.
        var resolved = lightweight
        if lightweight.resolvedMapOverlay == nil,
           !lightweight.route.isEmpty,
           let rendered = try? await client.fetchHolePrep(
               globalId: mapGlobalId,
               localHole: mapLocalHole,
               render: true
           ) {
            resolved = rendered
        }
        #if DEBUG
        // A freshly fetched hole can be visible before SwiftUI publishes the `@State` assignment
        // performed by retainThenPublishHolePrep. Move the deterministic simulator fix from the
        // already-resolved value so a hole transition cannot temporarily disable shot capture.
        moveSimulatedLocationToHoleTeeIfRequested(resolved)
        #endif
        await retainThenPublishHolePrep(
            resolved,
            globalId: mapGlobalId,
            sourceLocalHole: mapLocalHole,
            watchHole: hole.number
        )
        // Re-push to the watch now that F/M/B + plays-like are available. The ordered bootstrap will
        // fetch and push the matching caddie decision immediately after this map step.
        if let holePrep {
            sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
        }
        return true
    }

    @MainActor
    private func waitForPreciseHoleMap(syncClub: Bool) async {
        guard let caddieBaseURL else { return }
        let mapGlobalId = hole.sourceGlobalId ?? package.course.globalId
        let mapLocalHole = hole.sourceLocalHole ?? hole.number
        guard mapGlobalId != 0 else { return }
        let client = SyncClient(baseURL: caddieBaseURL, adminToken: adminToken)
        var delaySeconds: UInt64 = 5

        while !Task.isCancelled {
            do {
                try await Task.sleep(nanoseconds: delaySeconds * 1_000_000_000)
            } catch {
                return
            }
            guard !Task.isCancelled else { return }
            guard let refreshed = try? await client.fetchHolePrep(
                globalId: mapGlobalId,
                localHole: mapLocalHole
            ) else {
                delaySeconds = min(delaySeconds * 2, 60)
                continue
            }
            guard refreshed.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame else {
                delaySeconds = min(delaySeconds * 2, 60)
                continue
            }

            // Cache the matching bitmap and retain the precise prep before SwiftUI can publish the
            // ready map. A force-quit immediately after the map appears must therefore reopen the
            // same factual map instead of the partial package captured when the round started.
            await retainThenPublishHolePrep(
                refreshed,
                globalId: mapGlobalId,
                sourceLocalHole: mapLocalHole,
                watchHole: hole.number
            )
            // Rehydrate the decision from precise geometry after the durable map state is visible.
            await loadCaddieDecision(syncClub: syncClub && !hasUserSelectedClub)
            guard !Task.isCancelled else { return }
            return
        }
    }

    /// A ready prep and its bitmap are one user-visible fact. Make both durable before assigning
    /// `holePrep`; otherwise the player can see the precise map, kill the app, and resume from the
    /// older partial round package. Partial CourseView facts remain intentionally immediate.
    @MainActor
    private func retainThenPublishHolePrep(
        _ prep: CoursePrepHole,
        globalId: Int,
        sourceLocalHole: Int,
        watchHole: Int
    ) async {
        if prep.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame,
           prep.resolvedMapOverlay != nil {
            await pushTopoToWatch(
                globalId: globalId,
                sourceLocalHole: sourceLocalHole,
                watchHole: watchHole,
                geometryRevision: prep.geometryRevision
            )
            await pushGreenDetailToWatch(
                globalId: globalId,
                sourceLocalHole: sourceLocalHole,
                watchHole: watchHole,
                prep: prep
            )
            onRetainReadyHolePrep(package.roundId, hole.number, prep)
        }
        holePrep = prep
    }

    #if DEBUG
    /// A simulator cannot physically walk between holes. For the continuous real-course UI journey,
    /// recover this prep route's Tee GPS from the same calibrated topo projection used by the product.
    /// The explicit launch flag plus DEBUG compile gate prevent test movement from entering TestFlight.
    private func moveSimulatedLocationToHoleTeeIfRequested(_ packageHole: Hole) {
        guard let latitude = packageHole.teeLatitude,
              let longitude = packageHole.teeLongitude else { return }
        applySimulatedLocationIfRequested(latitude: latitude, longitude: longitude)
    }

    private func moveSimulatedLocationToHoleTeeIfRequested(_ prep: CoursePrepHole) {
        guard let first = prep.resolvedMapOverlay?.route.first, first.count >= 2,
              let refs = prep.holeImageProjection?.refs,
              let tee = WatchEventBridge.projectFromTopoPx(
                  px: first[0],
                  py: first[1],
                  refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) }
              ) else { return }
        applySimulatedLocationIfRequested(latitude: tee.latitude, longitude: tee.longitude)
    }

    private func applySimulatedLocationIfRequested(latitude: Double, longitude: Double) {
        guard ProcessInfo.processInfo.environment["UITEST_FOLLOW_HOLE_TEE"] == "1",
              let fix = locationProvider.moveSimulatedFixForUITest(
                  latitude: latitude,
                  longitude: longitude
              ) else { return }
        // Keep the view's derived state in the same transaction. Waiting for the @Published delivery
        // leaves `gpsHoleCandidate` on the previous hole for a frame and disables the shot button.
        currentCoordinate = fix.coordinate
        currentHorizontalAccuracyM = fix.horizontalAccuracyM
        gpsHoleCandidate = LiveHoleGPSResolver.candidate(
            holes: package.holes,
            coordinate: fix.coordinate,
            horizontalAccuracyM: fix.horizontalAccuracyM
        )
    }
    #endif

    /// Cache the clean topo independently of Watch availability, then relay the same bytes when a
    /// bridge exists. Phone durability must not depend on whether WatchConnectivity was created.
    private func pushTopoToWatch(
        globalId: Int,
        sourceLocalHole: Int,
        watchHole: Int,
        geometryRevision: String?
    ) async {
        guard globalId != 0, offlineStore != nil || watchBridge != nil else { return }
        if let cached = offlineStore?.loadCourseTopoImage(
            globalId: globalId,
            localHole: sourceLocalHole,
            geometryRevision: geometryRevision
        ) {
            if let watchBridge {
                watchBridge.pushHoleImage(
                    globalId: globalId,
                    hole: watchHole,
                    imageData: cached,
                    geometryRevision: geometryRevision
                )
            }
            return
        }
        #if DEBUG
        if ProcessInfo.processInfo.environment["UITEST_FORCE_LIVE_NETWORK_FAILURE"] == "1" {
            return
        }
        #endif
        guard let caddieBaseURL,
              let data = try? await SyncClient(
                  baseURL: caddieBaseURL,
                  adminToken: adminToken
              ).fetchTopoImage(
                  globalId: globalId,
                  localHole: sourceLocalHole,
                  geometryRevision: geometryRevision
              ) else { return }
        do {
            try offlineStore?.saveCourseTopoImage(
                data,
                globalId: globalId,
                localHole: sourceLocalHole,
                geometryRevision: geometryRevision
            )
        } catch {
            AICaddieLog.storage.error(
                "Live topo cache save failed for \(globalId, privacy: .public)/\(sourceLocalHole, privacy: .public): \(String(describing: error), privacy: .public)"
            )
        }
        if let watchBridge {
            watchBridge.pushHoleImage(
                globalId: globalId,
                hole: watchHole,
                imageData: data,
                geometryRevision: geometryRevision
            )
        }
    }

    /// Relay the focused View Green bitmap after the normal topo. The crop is derived from the same
    /// prep outline that becomes `WatchHoleMap.greenOutline`, so the Watch can place it without a
    /// second server manifest. A missing detail asset never blocks the round or the whole-hole map.
    private func pushGreenDetailToWatch(
        globalId: Int,
        sourceLocalHole: Int,
        watchHole: Int,
        prep: CoursePrepHole
    ) async {
        guard globalId != 0, let watchBridge, let caddieBaseURL,
              let projection = prep.holeImageProjection,
              let width = projection.widthPx,
              let height = projection.heightPx,
              let outline = prep.greenOutline,
              let crop = GreenDetailCrop.around(
                  points: outline.pointsPx,
                  imageWidth: Double(width),
                  imageHeight: Double(height)
              ) else { return }
        #if DEBUG
        if ProcessInfo.processInfo.environment["UITEST_FORCE_LIVE_NETWORK_FAILURE"] == "1" {
            return
        }
        #endif
        guard let data = try? await SyncClient(
            baseURL: caddieBaseURL,
            adminToken: adminToken
        ).fetchGreenDetailImage(
            globalId: globalId,
            localHole: sourceLocalHole,
            crop: crop,
            geometryRevision: prep.geometryRevision
        ), OfflineStore.isValidCourseTopoImageData(data) else { return }
        watchBridge.pushHoleImage(
            globalId: globalId,
            hole: watchHole,
            imageData: data,
            geometryRevision: prep.geometryRevision,
            assetKind: "green-detail"
        )
    }

    /// round-13 LIVE: 本洞前/中/后果岭(F/M/B)prep 数据,仅在 prep 几何可用时。distances 是 tee→green
    /// 静态值;B1 起它还带 F/M/B 的经纬度,供下面的 `liveGreenYards` 做实时测距。
    private var liveGreenDistances: CoursePrepGreenDistances? {
        guard let gd = holePrep?.greenDistances, gd.available else { return nil }
        return gd
    }

    /// 米 → 码(F/M/B 显示按码,与 R13 设计一致)。
    private func greenYards(_ metres: Double?) -> Int? {
        metres.map { Int(($0 * 1.09361).rounded()) }
    }

    /// round-13 B1 LIVE 测距:当前 GPS 定位 → 前/中/后果岭实时码距(haversine,客户端计算,离线可用)。
    /// 仅当有实时定位且该洞 prep 带果岭 F/M/B 经纬度时返回;否则 nil → 调用方回退到静态 tee→green 距离。
    /// 读取 @Published 的 `locationProvider.latestFix`,所以定位每次更新(球员走动)都会驱动重算与刷新。
    private var liveGreenYards: (front: Int?, middle: Int?, back: Int?)? {
        guard hasPlausibleLiveFix,
              let fix = locationProvider.latestFix,
              let gd = liveGreenDistances else { return nil }
        let here = fix.coordinate
        let front = GeoDistance.yards(from: here.latitude, here.longitude, to: gd.frontLat, gd.frontLon)
        let middle = GeoDistance.yards(from: here.latitude, here.longitude, to: gd.middleLat, gd.middleLon)
        let back = GeoDistance.yards(from: here.latitude, here.longitude, to: gd.backLat, gd.backLon)
        guard front != nil || middle != nil || back != nil else { return nil }
        return (front, middle, back)
    }

    /// watch P1d LIVE 果岭测距(米):当前 GPS → 前/中/后果岭 haversine 米距,发给手表当 F/M/B,让手表
    /// 成为真正的测距仪(距离随走动更新)。与 `liveGreenYards` 同源,但保留米制以复用手表侧 m→码 转换。
    private var liveGreenMetres: (front: Double?, middle: Double?, back: Double?)? {
        guard hasPlausibleLiveFix,
              let fix = locationProvider.latestFix,
              let gd = liveGreenDistances else { return nil }
        let here = fix.coordinate
        func metres(_ lat: Double?, _ lon: Double?) -> Double? {
            guard let lat, let lon else { return nil }
            return GeoDistance.haversineMetres(here.latitude, here.longitude, lat, lon)
        }
        let front = metres(gd.frontLat, gd.frontLon)
        let middle = metres(gd.middleLat, gd.middleLon)
        let back = metres(gd.backLat, gd.backLon)
        guard front != nil || middle != nil || back != nil else { return nil }
        return (front, middle, back)
    }

    /// 实时果岭测距当前是否生效(有 GPS 定位 + 该洞带果岭经纬度)→ 头部显示「实时」标记区分实时/静态。
    private var isGreenRangeLive: Bool { liveGreenYards != nil }

    /// 本洞避开区:取按洞拉取的 prep 水域区间与沙坑路线点/横距供球童方案展示。
    /// (live 包为提速不再内置全洞 coursePrep;按洞 prep 随 2D 图一起加载。)
    private var caddiePlanHazards: [CaddiePlanHazard] {
        guard let holePrep,
              holePrep.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame else {
            return []
        }
        if let liveHazards = liveHazardReadouts {
            return liveHazards.map {
                CaddiePlanHazard(
                    id: $0.id,
                    icon: $0.kind == "water" ? "water" : "bunker",
                    label: $0.label,
                    detail: $0.detail
                )
            }
        }
        return CaddiePlanHazard.from(
            holePrep.hazards,
            route: holePrep.resolvedMapOverlay?.route
        )
    }

    /// Live-round hazard ranges use the player's current GPS fix and the measured front/back boundary
    /// pixels. A non-nil empty array means every measured hazard is already behind the player; nil
    /// means this older prep lacks the projection needed for live ranging and should use static facts.
    private var liveHazardReadouts: [CoursePrepLiveHazardReadout]? {
        guard let holePrep,
              holePrep.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame,
              let fix = locationProvider.latestFix,
              let route = holePrep.resolvedMapOverlay?.route,
              let projection = holePrep.holeImageProjection,
              projection.available,
              let refs = projection.refs else {
            return nil
        }
        return CoursePrepLiveHazardReadout.upcoming(
            hazards: holePrep.hazards,
            route: route,
            projectionRefs: refs,
            playerLatitude: fix.coordinate.latitude,
            playerLongitude: fix.coordinate.longitude
        )
    }

    /// Measured hazard facts mirrored to the Watch. New prep carries true front/back boundary facts;
    /// old caches fall back to water intervals and a single reliable bunker route point.
    private func watchHazards() -> [WatchHazard] {
        guard let holePrep,
              holePrep.geometryCoverage.caseInsensitiveCompare("ready") == .orderedSame else {
            return []
        }
        let route = holePrep.resolvedMapOverlay?.route
        var out: [WatchHazard] = []
        let bunkerDetails = holePrep.hazards.details
            .filter { $0.kind == "bunker" }
            .sorted { $0.frontRouteM < $1.frontRouteM }
        if !bunkerDetails.isEmpty {
            for detail in bunkerDetails {
                out.append(WatchHazard(
                    kind: "bunker",
                    label: CoursePrepHazardNaming.label(
                        kind: "bunker", detail: detail, route: route
                    ),
                    startM: detail.frontRouteM,
                    endM: detail.backRouteM,
                    frontDistanceM: detail.frontM,
                    backDistanceM: detail.backM,
                    frontPx: detail.frontPx,
                    backPx: detail.backPx
                ))
            }
        } else {
            let bunkers = holePrep.hazards.bunkers.sorted { ($0.first ?? 0) < ($1.first ?? 0) }
            for interval in bunkers {
                out.append(WatchHazard(
                    kind: "bunker",
                    label: CoursePrepHazardNaming.legacyLabel(
                        kind: "bunker", interval: interval, route: route
                    ),
                    startM: interval.first,
                    sideM: interval.count >= 2 ? interval[1] : nil
                ))
            }
        }
        let waterDetails = holePrep.hazards.details
            .filter { $0.kind == "water" }
            .sorted { $0.frontRouteM < $1.frontRouteM }
        if !waterDetails.isEmpty {
            for detail in waterDetails {
                out.append(WatchHazard(
                    kind: "water",
                    label: CoursePrepHazardNaming.label(
                        kind: "water", detail: detail, route: route
                    ),
                    startM: detail.frontRouteM,
                    endM: detail.backRouteM,
                    frontDistanceM: detail.frontM,
                    backDistanceM: detail.backM,
                    frontPx: detail.frontPx,
                    backPx: detail.backPx
                ))
            }
        } else {
            let water = holePrep.hazards.waterCarry.sorted { ($0.first ?? 0) < ($1.first ?? 0) }
            for interval in water {
                out.append(WatchHazard(
                    kind: "water",
                    label: CoursePrepHazardNaming.legacyLabel(
                        kind: "water", interval: interval, route: route
                    ),
                    startM: interval.first,
                    endM: interval.count >= 2 ? interval[1] : nil
                ))
            }
        }
        return out
    }

    /// Club picker options: the player's clubs, minus empty/"Unknown" placeholders and
    /// case-insensitive duplicates (Garmin club names are user-entered and messy).
    /// Player's clubs from the backend real bag: zhClubName-normalized, deduped (keep most-sampled),
    /// restricted to the player's bag. `filterTeeOnly` drops 一号木 off the tee — applied to the
    /// quick chips, but NOT to the full dropdown (which lets the player pick ANY club).
    private func bagBest(filterTeeOnly: Bool) -> [String: ClubProfile] {
        var best: [String: ClubProfile] = [:]
        for profile in package.clubProfiles {
            let raw = profile.clubName.trimmingCharacters(in: .whitespaces)
            guard !raw.isEmpty, raw.lowercased() != "unknown" else { continue }
            let name = zhClubName(raw)
            if filterTeeOnly, clubIsTeeOnly(name), selectedLie != "tee" { continue }
            if let existing = best[name], existing.sampleSize >= profile.sampleSize { continue }
            best[name] = profile
        }
        // Restrict to the player's bag — manual override (球杆设置) if set, else the real Garmin bag —
        // so clubs they don't carry (a stray mis-tagged "二号小鸡腿") never appear. Neither known → all.
        if let bag = ClubBagStore.effectiveBag() {
            best = best.filter { bag.contains($0.key) }
        }
        return best
    }

    /// The 3 clubs most relevant to THIS shot (quick chips): nearest to the to-pin distance when
    /// known, else the 3 longest. Always keeps the selected club visible.
    private var clubNames: [String] {
        let best = bagBest(filterTeeOnly: true)
        let ordered: [String]
        if let target = effectiveDistanceToPinMetres {
            ordered = best.sorted { abs($0.value.medianM - target) < abs($1.value.medianM - target) }.map(\.key)
        } else {
            ordered = best.sorted { $0.value.medianM > $1.value.medianM }.map(\.key)
        }
        var top = Array(ordered.prefix(3))
        if best[selectedClub] != nil, !top.contains(selectedClub) {
            top = [selectedClub] + top.prefix(2)
        }
        return top
    }

    /// round-12: the FULL bag for the dropdown picker — every club + its distance, longest→shortest,
    /// so the player can choose ANY club (not just the 3 quick chips). No tee-only filter here.
    private var allBagClubs: [(name: String, metres: Double)] {
        bagBest(filterTeeOnly: false)
            .sorted { $0.value.medianM > $1.value.medianM }
            .map { (name: $0.key, metres: $0.value.medianM) }
    }

    /// The caddie's currently-recommended club (zh), used to mark it in the dropdown.
    private var recommendedClub: String? {
        guard let decision = caddieDecision, let raw = recommendedClubName(from: decision) else {
            return nil
        }
        return zhClubName(raw)
    }

    /// round-12: full-bag dropdown — pick ANY club + its distance; recommended club marked; defaults
    /// to the recommendation (selectedClub is synced to it). Selecting records the pick (选完即记).
    @ViewBuilder private var clubPickerMenu: some View {
        Menu {
            ForEach(allBagClubs, id: \.name) { club in
                Button {
                    selectClub(club.name)
                } label: {
                    let label = "\(club.name) · \(CoursePrepRoute.yards(fromMetres: club.metres)) 码"
                        + (club.name == recommendedClub ? " · 推荐" : "")
                    if club.name == selectedClub {
                        Label(label, systemImage: "checkmark")
                    } else {
                        Text(label)
                    }
                }
            }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "bag").font(.caption)
                Text(selectedClub.isEmpty ? "选择球杆" : selectedClub).font(.subheadline.weight(.semibold))
                Image(systemName: "chevron.down").font(.caption2)
            }
            .foregroundStyle(LiveHoleStyle.green)
        }
    }

    /// Set the selected club (chips + dropdown). round-12「选完即记」: persist the pick immediately as
    /// a lightweight club-selection event (clubName/打法/球位/距离 — NOT a shot/GPS record) so the
    /// choice survives a quit/restart and drives the map landing marker.
    private func selectClub(_ club: String) {
        let changed = club != selectedClub
        selectedClub = club
        guard changed, !club.isEmpty else { return }
        hasUserSelectedClub = true
        emit(kind: .club, timestamp: ISO8601DateFormatter().string(from: Date()), payload: [
            "clubName": .string(selectedClub),
            "shotType": .string(selectedShotType),
            "strategyMode": .string(selectedStrategyMode),
            "lie": .string(selectedLie),
            "distanceToPinM": distanceToPinPayload(),
        ])
    }

    /// The selected club's typical distance (metres) from the bag model — drives the live map marker.
    private var selectedClubMetres: Double? {
        guard let profile = package.clubProfiles.first(where: { zhClubName($0.clubName) == selectedClub }) else {
            return nil
        }
        return profile.medianM
    }

    /// A sensible pre-decision default club: the tee club (longest trustworthy non-tee-only club) for
    /// par 4/5, or the club whose median matches the green distance for a par 3. Avoids defaulting to
    /// an arbitrary clubProfiles.first (which could be a noisy short iron — owner's "9I" reads 159m
    /// off 13 stray shots). The live caddie decision refines this to its recommendation once loaded.
    private static func defaultClub(par: Int, holeYards: Int?, profiles: [ClubProfile]) -> String {
        let usable = profiles.filter { profile in
            let raw = profile.clubName.trimmingCharacters(in: .whitespaces)
            return !raw.isEmpty && raw.lowercased() != "unknown" && profile.medianM > 0
        }
        // ≥20 samples mirrors the backend caddie trust filter (MIN_CADDIE_SAMPLE); fall back to all
        // data-backed clubs for low-data players so we still pick something reasonable.
        let trusted = usable.filter { $0.sampleSize >= 20 }
        let pool = trusted.isEmpty ? usable : trusted
        guard !pool.isEmpty else { return "" }
        let pick: ClubProfile
        if par == 3, let yards = holeYards, yards > 0 {
            let targetM = Double(yards) * 0.9144
            pick = pool.min { abs($0.medianM - targetM) < abs($1.medianM - targetM) } ?? pool[0]
        } else {
            let nonTee = pool.filter { !clubIsTeeOnly(zhClubName($0.clubName)) }
            let candidates = nonTee.isEmpty ? pool : nonTee
            pick = candidates.max { $0.medianM < $1.medianM } ?? candidates[0]
        }
        return zhClubName(pick.clubName)
    }

    /// The club the player will hit NOW under the caddie's decision: the first step of the selected
    /// sequence (the tee/advance shot) when sequences exist, else the selected single-club option.
    private func recommendedClubName(from decision: CaddieDecisionResponse) -> String? {
        let sequences = CaddiePlanSequence.sequences(from: decision)
        let selectedId = CaddiePlanSequence.selectedSequenceId(from: decision) ?? decision.selectedOptionId
        if let sequence = sequences.first(where: { $0.id == selectedId }) ?? sequences.first,
           let firstClub = sequence.steps.first?.clubName, firstClub != "-" {
            return firstClub
        }
        let options = CaddiePlanOption.options(from: decision)
        let club = (options.first { $0.id == decision.selectedOptionId } ?? options.first)?.clubName
        return (club == nil || club == "-") ? nil : club
    }

    /// Adopt the caddie's recommended club as the selected club so the club strip highlight and the
    /// hole-map landing marker follow the recommendation (and change with strategy). No-op if the
    /// decision carries no usable club.
    @MainActor
    private func syncSelectedClubToRecommendation() {
        guard let decision = caddieDecision, let club = recommendedClubName(from: decision) else {
            return
        }
        selectedClub = zhClubName(club)
    }

    // MARK: - 球局调整(加打 / 减九洞 / 结束本场)— round-11 从首页移入实战屏

    /// 收在实战屏底部的折叠区:加打/减九洞 + 结束本场。控件与闭包与原首页一致。
    @ViewBuilder private var manageSection: some View {
        DisclosureGroup(isExpanded: $showManage) {
            VStack(spacing: 8) {
                nineControl
                loopAddControl
                if let live = liveRoundState, package.holes.contains(where: { $0.number == live.activeHole }) {
                    Button {
                        showRoundSummary = true
                    } label: {
                        Text("结束本场").font(.subheadline).frame(maxWidth: .infinity).padding(.vertical, 6)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(Color(red: 185 / 255, green: 50 / 255, blue: 40 / 255))
                }
            }
            .padding(.top, 8)
        } label: {
            Label("球局调整 · 加打 / 结束本场", systemImage: "slider.horizontal.3")
                .font(.subheadline).foregroundStyle(.secondary)
        }
        .livePlayAuxiliaryCard()
    }

    /// 起始九洞的加打 / 撤销:nine 是对一局 18 洞的视图过滤,已记杆按 roundId 保留。
    @ViewBuilder private var nineControl: some View {
        if package.course.globalId != 0 {
            let currentNine = package.nine ?? "all"
            if currentNine != "all" {
                Button {
                    onChangeNine("all")
                } label: {
                    Label("＋加打另外 9 洞(凑 18)", systemImage: "plus.circle")
                        .font(.subheadline.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .foregroundStyle(LiveHoleStyle.green)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(LiveHoleStyle.green))
                }
                .buttonStyle(.plain)
                .disabled(isPreparingRound)
            } else if let startingNine, startingNine != "all" {
                Button {
                    onChangeNine(startingNine)
                } label: {
                    Label("移除另外 9 洞 · 只打\(nineText(startingNine))", systemImage: "minus.circle")
                        .font(.subheadline)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .foregroundStyle(.secondary)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(LiveHoleStyle.line))
                }
                .buttonStyle(.plain)
                .disabled(isPreparingRound)
            }
        }
    }

    private func nineText(_ nine: String) -> String {
        switch nine {
        case "front":
            return "前九"
        case "back":
            return "后九"
        default:
            return "全 18 洞"
        }
    }

    /// 当前局对应的 CourseView 选项(用 course.globalId 反查;组合局的 globalId = 前环)。
    private var activeCourseOption: MobileCourseOption? {
        courseOptions.first { $0.globalId == package.course.globalId }
    }

    /// 同球场可作为「另一个 9 洞」的环(9 洞、同球场),含当前环本身。按 A/B/C 排序。
    private var siblingLoops: [MobileCourseOption] {
        guard let venue = activeCourseOption?.venueName else { return [] }
        return courseOptions
            .filter { ($0.venueName ?? "") == venue
                && ($0.segmentHoles ?? $0.holes) == 9 }
            .sorted { ($0.segmentLabel ?? "~~") < ($1.segmentLabel ?? "~~") }
    }

    private func loopLabel(_ option: MobileCourseOption) -> String {
        if let label = option.segmentLabel, !label.isEmpty {
            return "\(label) 场"
        }
        return "另一个 9 洞"
    }

    @ViewBuilder private var loopAddControl: some View {
        // 仅进行中、且当前局是某球场的一个 9 洞环时显示。
        if liveRoundState != nil, let active = activeCourseOption, (active.segmentHoles ?? active.holes) == 9 {
            if package.holes.count <= 9 {
                if !siblingLoops.isEmpty {
                    // 单 9 洞环进行中 → 选另一个环加打凑 18(同一局,已记杆保留)。
                    Menu {
                        ForEach(siblingLoops) { loop in
                            Button("＋ \(loopLabel(loop)) · 凑 18 洞") {
                                onPrepareCompositeRound(package.course.globalId, loop.globalId, package.course.teeBox, package.roundId)
                            }
                        }
                    } label: {
                        Label("＋加打另一个 9 洞(凑 18)", systemImage: "plus.circle")
                            .font(.subheadline.weight(.semibold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 12)
                            .foregroundStyle(LiveHoleStyle.green)
                            .overlay(RoundedRectangle(cornerRadius: 12).stroke(LiveHoleStyle.green))
                    }
                    .disabled(isPreparingRound)
                }
            } else {
                // 已是组合 18(两个 9 洞环)→ 移除加打的后 9,只打起始 9 洞(前 9 已记杆保留)。
                Button {
                    onPrepareCourseRound(package.course.globalId, package.roundId, package.course.teeBox, "all")
                } label: {
                    Label("移除加打的 9 洞 · 只打前 9", systemImage: "minus.circle")
                        .font(.subheadline)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .foregroundStyle(.secondary)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(LiveHoleStyle.line))
                }
                .disabled(isPreparingRound)
            }
        }
    }

    private var shotTypeOptions: [String] {
        let options = caddieContextSeed?.shotTypes ?? []
        return options.isEmpty ? ["tee", "approach", "recovery"] : options
    }

    private var lieOptions: [String] {
        ["fairway", "rough", "bunker", "green", "tee", "recovery"]
    }

    /// 击球类型 / 球位的封闭英文枚举 → 中文(更多调整里的选择器)。未知值原样回退。
    private func zhShotType(_ value: String) -> String {
        switch value.lowercased() {
        case "tee":
            return "开球"
        case "approach":
            return "攻果岭"
        case "recovery":
            return "解围"
        case "layup":
            return "铺垫"
        case "putt":
            return "推杆"
        default:
            return value.capitalized
        }
    }

    private func zhLie(_ value: String) -> String {
        switch value.lowercased() {
        case "fairway":
            return "球道"
        case "rough":
            return "长草"
        case "bunker":
            return "沙坑"
        case "green":
            return "果岭"
        case "tee":
            return "发球台"
        case "recovery":
            return "解围"
        default:
            return value.capitalized
        }
    }

    private func makeCaddieDecisionRequest() -> CaddieDecisionRequest? {
        guard let caddieContextSeed else {
            return nil
        }
        return requestBuilder.makeDecisionRequest(
            seed: caddieContextSeed,
            input: LiveCaddieInput(
                shotType: selectedShotType,
                distanceToPinM: effectiveDistanceToPinMetres,
                lie: selectedLie,
                coordinate: liveCoordinateForCurrentHole,
                targetCoordinate: wireTargetCoordinate,
                targetKind: wireTargetKind,
                horizontalAccuracyM: liveCoordinateForCurrentHole == nil ? nil : currentHorizontalAccuracyM,
                capturedAt: liveCoordinateForCurrentHole == nil ? nil : locationProvider.latestFix?.capturedAt,
                strategyMode: selectedStrategyMode,
                visionFindings: visionFindings
            )
        )
    }

    @MainActor
    private func loadCaddieDecision(syncClub: Bool = false) async {
        #if DEBUG
        let effectiveClient = ProcessInfo.processInfo.environment["UITEST_FORCE_LIVE_NETWORK_FAILURE"] == "1"
            ? nil
            : caddieClient
        #else
        let effectiveClient = caddieClient
        #endif
        guard let effectiveClient else {
            caddieDecision = makeOfflineCaddieDecision()
            caddieErrorMessage = caddieDecision == nil
                ? "这一洞暂时无法给建议。"
                : "离线模式 · 使用已保存的方案。"
            if syncClub { syncSelectedClubToRecommendation() }
            sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
            return
        }
        guard let request = makeCaddieDecisionRequest() else {
            caddieErrorMessage = "这一洞暂时无法给建议。"
            sendWatchState(decision: nil, offlineOption: selectedOfflineOption)
            return
        }

        let requestedBeforePrep = holePrep == nil
        isLoadingCaddieDecision = true
        defer {
            isLoadingCaddieDecision = false
        }

        do {
            let response = try await effectiveClient.fetchCaddieDecision(request, endpoint: package.caddieDecisionEndpoint)
            guard !Task.isCancelled else { return }
            // If prep arrived while a manual distance-free request was in flight, the ordered hole
            // bootstrap will launch the context-complete request next. Never let the stale answer
            // overwrite it.
            guard !(requestedBeforePrep && holePrep != nil) else { return }
            caddieDecision = response
            caddieErrorMessage = nil
            if syncClub { syncSelectedClubToRecommendation() }
            sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
        } catch let error where LiveCaddieLoadFailure.isCancellation(error) {
            return
        } catch {
            if let offlineDecision = makeOfflineCaddieDecision() {
                caddieDecision = offlineDecision
                caddieErrorMessage = "联网球童暂不可用 · 已切换到离线缓存建议。"
            } else {
                caddieErrorMessage = "球童建议暂取不到 · 仍显示已缓存的方案。"
            }
            if syncClub { syncSelectedClubToRecommendation() }
            sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
        }
    }

    private func makeOfflineCaddieDecision() -> CaddieDecisionResponse? {
        guard let caddieContextSeed,
              let request = makeCaddieDecisionRequest()
        else {
            return nil
        }
        return offlineDecisionEvaluator.makeDecision(
            seed: caddieContextSeed,
            request: request,
            strategyMode: selectedStrategyMode
        )
    }

    private var selectedOfflineOption: OfflineCaddieOption? {
        guard let seed = caddieContextSeed else {
            return nil
        }
        return offlineDecisionEvaluator.selectedOption(in: seed, strategyMode: selectedStrategyMode)
    }

    private func sendWatchState(decision: CaddieDecisionResponse?, offlineOption: OfflineCaddieOption?) {
        // round-13 LIVE: forward the per-hole 前/中/后果岭 (F/M/B) + plays-like slope the backend
        // already ships on /prep (holePrep), plus the geometry-coverage gate. Static tee→green
        // distances (not live-GPS recomputed); nil on holes without usable geometry.
        let green = holePrep?.greenDistances
        let greenOK = green?.available == true
        // watch P1d: prefer LIVE-GPS green distances (from where the player stands) over static tee→green.
        let liveGreens = liveGreenMetres
        let playsLike = holePrep?.playsLike
        let slopeM = playsLike?.available == true ? playsLike?.deltaM : nil
        // watch P0.2: forward the topo geo→px projection so the watch overlays its own GPS/pin/landings.
        let hip = holePrep?.holeImageProjection
        let watchProj: WatchHoleImageProjection? = (hip?.available == true)
            ? WatchHoleImageProjection(
                widthPx: hip?.widthPx, heightPx: hip?.heightPx,
                refs: hip?.refs?.map { WatchProjectionRef(lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) })
            : nil
        // watch P1b/P1c: pre-compute the hole-map overlay anchors (you / pin=green / lay-up) from the
        // centreline route so the watch draws the map on the cached /topo.png with no projection math.
        // `you` follows the player's LIVE GPS (projected onto the topo via the same affine refs) when a
        // fix is available, else falls back to the tee — so the map pans as you walk (companion mode).
        let mapGlobalId = hole.sourceGlobalId ?? package.course.globalId
        let youPxOverride: [Double]? = {
            guard let coord = liveCoordinateForCurrentHole, let refs = hip?.refs, refs.count >= 3 else { return nil }
            return WatchEventBridge.projectToTopoPx(
                lat: coord.latitude, lon: coord.longitude,
                refs: refs.map { (lat: $0.lat, lon: $0.lon, px: $0.px, py: $0.py) })
        }()
        let holeMap: WatchHoleMap? = (holePrep?.resolvedMapOverlay).flatMap {
            WatchEventBridge.makeHoleMap(
                overlay: $0,
                landingM: holePrep?.landingM,
                youPxOverride: youPxOverride,
                greenOutline: holePrep?.greenOutline?.available == true
                    ? holePrep?.greenOutline?.pointsPx
                    : nil
            )
        }
        let state = watchBridge?.makeWatchRoundStatePayload(
            package: package,
            hole: hole,
            score: score,
            putts: puttCount,
            penaltyCount: penaltyCount,
            selectedClub: selectedClub,
            decision: decision,
            offlineOption: offlineOption,
            distanceToPinM: effectiveDistanceToPinMetres,
            targetLatitude: wireTargetCoordinate?.latitude,
            targetLongitude: wireTargetCoordinate?.longitude,
            targetKind: wireTargetKind,
            frontGreenM: liveGreens?.front ?? (greenOK ? green?.frontM : nil),
            centerGreenM: liveGreens?.middle ?? (greenOK ? green?.middleM : nil),
            backGreenM: liveGreens?.back ?? (greenOK ? green?.backM : nil),
            frontGreenLat: greenOK ? green?.frontLat : nil,
            frontGreenLon: greenOK ? green?.frontLon : nil,
            centerGreenLat: greenOK ? green?.middleLat : nil,
            centerGreenLon: greenOK ? green?.middleLon : nil,
            backGreenLat: greenOK ? green?.backLat : nil,
            backGreenLon: greenOK ? green?.backLon : nil,
            holeImageProjection: watchProj,
            globalId: mapGlobalId,
            holeMap: holeMap,
            playsLikeDistanceM: playsLikeMetres(
                distanceMetres: effectiveDistanceToPinMetres,
                elevationDeltaMetres: slopeM
            ),
            elevationDeltaM: slopeM,
            geometryCoverage: holePrep?.geometryCoverage ?? hole.geometryCoverage.rawValue,
            geometryRevision: holePrep?.geometryRevision ?? hole.geometryRevision,
            hazards: watchHazards()
        )
        if let state {
            try? watchBridge?.sendStateToWatch(state)
        }
    }

    private func playsLikeMetres(distanceMetres: Double?, elevationDeltaMetres: Double?) -> Double? {
        guard let distanceMetres, distanceMetres.isFinite,
              let elevationDeltaMetres, elevationDeltaMetres.isFinite else { return nil }
        return distanceMetres + elevationDeltaMetres
    }

    private func applyRestoredStateIfNeeded(_ snapshot: LiveRoundStateSnapshot?) {
        guard let restoredHoleState = snapshot?.holeState(for: hole.number) else {
            return
        }
        guard lastAppliedRestoredHoleState?.hasSameRestorableFields(as: restoredHoleState) != true else {
            return
        }
        applyRestoredState(restoredHoleState)
    }

    private func applyRestoredState(_ restoredHoleState: LiveHoleStateSnapshot) {
        // Save-only fields are persisted only on explicit Save; preserve any the user
        // has edited-but-not-saved instead of reverting them to the snapshot (P0-5).
        let reconciled = restoredHoleState.reconciledSaveOnlyFields(
            currentScore: score,
            currentPutts: puttCount,
            currentPenaltyCount: penaltyCount,
            lastApplied: lastAppliedRestoredHoleState
        )
        score = reconciled.score
        puttCount = reconciled.putts
        penaltyCount = reconciled.penaltyCount
        // Normalise to the same zhClubName the picker uses (init does this) so the ClubStrip highlight matches.
        selectedClub = zhClubName(restoredHoleState.selectedClub)
        selectedShotType = restoredHoleState.selectedShotType
        selectedStrategyMode = restoredHoleState.selectedStrategyMode
        selectedLie = restoredHoleState.lie
        distanceToPinText = Self.validDistanceText(restoredHoleState.distanceToPinM)
        if let latitude = restoredHoleState.latitude, let longitude = restoredHoleState.longitude {
            currentCoordinate = CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
        } else {
            currentCoordinate = nil
        }
        if let restoredTarget = Self.restoredTarget(from: restoredHoleState) {
            if restoredTarget.kind == "pin" {
                targetCoordinate = nil
                targetKind = nil
                greenPinCoordinate = restoredTarget.coordinate
            } else {
                targetCoordinate = restoredTarget.coordinate
                targetKind = restoredTarget.kind
                greenPinCoordinate = nil
            }
            lastTargetEditKind = restoredTarget.kind
        } else {
            targetCoordinate = nil
            greenPinCoordinate = nil
            targetKind = nil
            lastTargetEditKind = nil
        }
        // Pixel targets are session-local unless the server has a geo coordinate to reproject. A
        // restored hole starts without a stale point from the previously visible hole.
        targetPixel = nil
        greenPinPixel = nil
        currentHorizontalAccuracyM = restoredHoleState.horizontalAccuracyM
        lastAppliedRestoredHoleState = restoredHoleState
        sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
    }

    private func beginScoreConfirmation() {
        if scoreDraft == nil {
            let restoredFairway = liveRoundState?.holeState(for: hole.number)?.fairwayResult
                .flatMap(LiveFairwayResult.init(rawValue:))
            scoreDraft = LiveScoreDraft(
                hole: hole.number,
                par: hole.par,
                recordedShotCount: recordedNonPuttShotCount,
                currentScore: score,
                currentPutts: puttCount,
                currentPenalty: penaltyCount,
                currentFairway: restoredFairway
            )
        }
        if let scoreDraft {
            if let offlineStore {
                try? offlineStore.saveLiveScoreDraft(roundId: package.roundId, draft: scoreDraft)
            }
        }
    }

    private func acceptScoreConfirmation(_ accepted: LiveScoreDraft) {
        let events = LiveScoreSubmission.events(
            roundId: package.roundId,
            draft: accepted,
            note: note,
            timestamp: ISO8601DateFormatter().string(from: Date())
        )
        events.forEach(onEvent)
        if let offlineStore {
            try? offlineStore.clearLiveScoreDraft(roundId: package.roundId)
        }
        scoreDraft = nil
        if accepted.hole == hole.number {
            score = accepted.score
            puttCount = accepted.putts
            penaltyCount = accepted.penalty
        }
        if accepted.advanceAfterSave {
            if let next = nextHole(after: accepted.hole) {
                onAdvanceHole(next)
            } else {
                showRoundSummary = true
            }
        }
        sendWatchState(decision: caddieDecision, offlineOption: selectedOfflineOption)
    }

    private func cancelScoreConfirmation() {
        let draftHole = scoreDraft?.hole
        let shouldReturnToDraftHole = scoreDraft?.advanceAfterSave == true && draftHole != hole.number
        if let offlineStore {
            try? offlineStore.clearLiveScoreDraft(roundId: package.roundId)
        }
        scoreDraft = nil
        if shouldReturnToDraftHole, let draftHole {
            onAdvanceHole(draftHole)
        }
    }

    private var recordedScoreHoles: Set<Int> {
        guard let offlineStore, let events = try? offlineStore.loadEvents() else { return [] }
        let displayedHoles = Set(package.holes.map(\.number))
        return Set(events.compactMap { event in
            guard event.roundId == package.roundId,
                  displayedHoles.contains(event.hole),
                  event.kind == .score else {
                return nil
            }
            return event.hole
        })
    }

    private var completedHoleStates: [(hole: Hole, state: LiveHoleStateSnapshot)] {
        let recorded = recordedScoreHoles
        return package.holes.compactMap { hole in
            guard recorded.contains(hole.number),
                  let state = liveRoundState?.holeState(for: hole.number) else {
                return nil
            }
            return (hole, state)
        }
    }

    private func presentPendingHistoricalScoreEdit() {
        guard let selectedHoleNumber = pendingHistoricalScoreHole else { return }
        pendingHistoricalScoreHole = nil
        guard let selectedHole = package.holes.first(where: { $0.number == selectedHoleNumber }) else {
            return
        }

        let restored = liveRoundState?.holeState(for: selectedHoleNumber)
        let draft = LiveScoreDraft(
            hole: selectedHoleNumber,
            par: selectedHole.par,
            recordedShotCount: 0,
            currentScore: restored?.score ?? selectedHole.par,
            currentPutts: restored?.putts ?? 2,
            currentPenalty: restored?.penaltyCount ?? 0,
            currentFairway: restored?.fairwayResult.flatMap(LiveFairwayResult.init(rawValue:)),
            offerRecommendation: false,
            advanceAfterSave: false
        )
        scoreDraft = draft
        if let offlineStore {
            try? offlineStore.saveLiveScoreDraft(roundId: package.roundId, draft: draft)
        }
    }

    private func nextHole(after number: Int) -> Int? {
        let ordered = package.holes.map(\.number)
        guard let index = ordered.firstIndex(of: number), ordered.indices.contains(index + 1) else {
            return nil
        }
        return ordered[index + 1]
    }

    private var recordedNonPuttShotCount: Int {
        guard let offlineStore, let events = try? offlineStore.loadEvents() else { return 0 }
        return events.filter { event in
            event.roundId == package.roundId && event.hole == hole.number && event.kind == .location
        }.count
    }

    private var actualClubChoices: [LiveActualClubChoice] {
        var choices = allBagClubs.map { club in
            LiveActualClubChoice(
                name: club.name,
                yards: CoursePrepRoute.yards(fromMetres: club.metres),
                isRecommended: club.name == recommendedClub
            )
        }
        if let recommendedClub, !choices.contains(where: { $0.name == recommendedClub }) {
            choices.insert(
                LiveActualClubChoice(name: recommendedClub, yards: nil, isRecommended: true),
                at: 0
            )
        }
        return choices
    }

    private func recordShotLocation() {
        guard let currentCoordinate = liveCoordinateForCurrentHole else { return }
        let shotOrder = recordedNonPuttShotCount + 1
        let builder = LiveRoundEventBuilder(roundId: package.roundId)
        let locationEvent = builder.makeLocationEvent(
            hole: hole.number,
            coordinate: currentCoordinate,
            horizontalAccuracyM: currentHorizontalAccuracyM,
            altitudeM: locationProvider.latestFix?.altitudeM,
            targetCoordinate: wireTargetCoordinate,
            targetKind: wireTargetKind
        )
        onEvent(locationEvent)
        pendingPhoneShot = PendingPhoneShot(locationEvent: locationEvent, shotOrder: shotOrder)
    }

    private func recordActualClub(_ club: String, for pendingShot: PendingPhoneShot) {
        let trimmedClub = club.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedClub.isEmpty else {
            pendingPhoneShot = nil
            return
        }
        #if DEBUG
        UITestEventLatencyTrace.record("actual-club.build.begin hole=\(hole.number)")
        #endif
        let event = LiveRoundEventBuilder(roundId: package.roundId).makeActualClubEvent(
            hole: hole.number,
            clubName: trimmedClub,
            sourceLocationEventId: pendingShot.locationEvent.eventId,
            shotOrder: pendingShot.shotOrder,
            shotType: selectedShotType,
            strategyMode: selectedStrategyMode,
            lie: selectedLie,
            distanceToPinM: effectiveDistanceToPinMetres,
            offlineOptionId: selectedOfflineOption?.optionId,
            decision: caddieDecision
        )
        #if DEBUG
        UITestEventLatencyTrace.record("actual-club.build.end hole=\(hole.number)")
        UITestEventLatencyTrace.record("actual-club.encode.begin hole=\(hole.number)")
        let encodedByteCount = (try? JSONEncoder().encode(event).count) ?? -1
        UITestEventLatencyTrace.record("actual-club.encode.end hole=\(hole.number) bytes=\(encodedByteCount)")
        UITestEventLatencyTrace.record("actual-club.handle.begin hole=\(hole.number)")
        #endif
        onEvent(event)
        #if DEBUG
        UITestEventLatencyTrace.record("actual-club.handle.end hole=\(hole.number)")
        #endif
        pendingPhoneShot = nil
    }

    private func distanceToPinPayload() -> JSONValue {
        guard let metres = distanceToPinMetres else {
            return .null
        }
        return .number(metres)
    }

    private func emit(kind: LiveRoundEventKind, timestamp: String, payload: [String: JSONValue]) {
        onEvent(
            LiveRoundEvent(
                eventId: UUID().uuidString,
                roundId: package.roundId,
                timestamp: timestamp,
                hole: hole.number,
                kind: kind,
                payload: payload
            )
        )
    }

    /// 到旗杆距离在 UI 里以「码」输入/显示;后端事件/球童请求用米,这里在边界换算回米。
    private var distanceToPinMetres: Double? {
        guard let yards = Double(distanceToPinText.trimmingCharacters(in: .whitespacesAndNewlines)),
              yards.isFinite,
              yards > 0 else {
            return nil
        }
        let metres = CoursePrepRoute.metres(fromYards: yards)
        return metres <= GeoDistance.maximumUsefulGreenMetres ? metres : nil
    }

    /// One distance source for club relevance, backend planning, and Watch state. A player's manual
    /// target wins; otherwise use live GPS→green-middle, then the downloaded tee→middle fallback.
    private var effectiveDistanceToPinMetres: Double? {
        LiveCaddieDistance.resolve(
            manualM: distanceToPinMetres ?? mapTargetDistanceMetres ?? greenPinDistanceMetres,
            liveMiddleM: liveGreenMetres?.middle,
            staticMiddleM: liveGreenDistances?.middleM,
            holeYards: hole.yards
        )
    }

    private var liveCoordinateForCurrentHole: CLLocationCoordinate2D? {
        mapReferenceIsLive ? currentCoordinate : nil
    }

    /// 后端存的米 → 前端显示的整码(恢复已记距离时用)。
    private static func yardsText(fromMetres metres: Double) -> String {
        String(CoursePrepRoute.yards(fromMetres: metres))
    }

    private static func validDistanceText(_ metres: Double?) -> String {
        guard let metres,
              metres.isFinite,
              metres > 0,
              metres <= GeoDistance.maximumUsefulGreenMetres else { return "" }
        return yardsText(fromMetres: metres)
    }

    /// Target semantics are shared by iPhone, Watch and the server event contract. `map_target` was
    /// emitted by an intermediate build; read it as a normal manual target so an upgrade does not
    /// strand the saved point, but never emit that legacy token again.
    private static func normalizedTargetKind(_ raw: String?) -> String? {
        switch raw?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "pin": return "pin"
        case "target", "map_target": return "target"
        case "green_center": return "green_center"
        default: return nil
        }
    }

    private static func restoredTarget(
        from state: LiveHoleStateSnapshot?
    ) -> (coordinate: CLLocationCoordinate2D, kind: String)? {
        guard let state,
              let latitude = state.targetLatitude,
              let longitude = state.targetLongitude,
              latitude.isFinite,
              longitude.isFinite,
              (-90...90).contains(latitude),
              (-180...180).contains(longitude),
              let kind = normalizedTargetKind(state.targetKind) else {
            return nil
        }
        return (
            CLLocationCoordinate2D(latitude: latitude, longitude: longitude),
            kind
        )
    }
}
