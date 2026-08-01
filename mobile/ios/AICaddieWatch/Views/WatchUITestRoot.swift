#if DEBUG
import CoreLocation
import Foundation
import SwiftUI

/// Real-runtime watch screenshots: launched with `-uitest-screen <name>` (via `simctl launch`), the watch
/// app renders the REAL target view with demo data at its root so `simctl io screenshot` captures it in
/// the actual watchOS simulator runtime — including List/ScrollView content that ImageRenderer design
/// snapshots cannot render. DEBUG-only: never compiled into the Release/TestFlight binary. watchOS has no
/// XCUITest, so this direct-render-by-arg harness is how the watch surfaces get genuine running-app shots.
public struct WatchUITestRoot: View {
    public let screen: String
    @ObservedObject private var model: WatchRoundModel
    @State private var realCourseTaskStarted = false
    @State private var realCourseStatus: String?

    private static let realCourseGlobalId = 3881

    public init(screen: String, model: WatchRoundModel) {
        self.screen = screen
        self.model = model
    }

    /// Reads `-uitest-screen <name>` from the launch arguments; nil when not a UI-test launch.
    public static func requestedScreen() -> String? {
        let args = ProcessInfo.processInfo.arguments
        guard let index = args.firstIndex(of: "-uitest-screen"), index + 1 < args.count else {
            return nil
        }
        return args[index + 1]
    }

    public var body: some View {
        switch screen {
        case "milestone-seed", "milestone-restore":
            milestoneRound
        case "standalone-course-seed", "standalone-course-restore",
             "standalone-course-map-zoom",
             "standalone-course-caddie", "standalone-course-hazards",
             "standalone-course-last-shot", "standalone-course-caddie-last-shot",
             "standalone-course-live-home":
            standaloneCourseRound
        case "real-course-download-seed", "real-course-download-restore",
             "real-course-download-caddie",
             "real-course-map-measured", "real-course-map-pin-drag",
             "real-course-hazard-map", "real-course-hazard-mid-map",
             "real-course-journey-start", "real-course-journey-advance",
             "real-course-journey-restore", "real-course-journey-history-edit",
             "real-course-journey-finish", "real-course-journey-finish-confirm":
            realCourseRound
        case "course-picker":
            cachedCoursePicker
        case "course-search-results":
            WatchStartView(
                phoneReachable: false,
                searchMatches: Self.remoteCourseMatches
            )
        case "course-setup":
            NavigationStack {
                WatchRoundSetupView(
                    front: Self.setupFront,
                    courses: [Self.setupFront, Self.setupBack],
                    hasCachedVersion: true
                )
            }
        case "course-remote-setup":
            NavigationStack {
                WatchRoundSetupView(
                    front: Self.remoteCourseOptions[0],
                    courses: [Self.remoteCourseOptions[0]],
                    ensureGeometry: true,
                    onLoadTees: { _ in Self.remoteCourseTees }
                )
            }
        case "interaction-club-seed", "interaction-club-restore",
             "interaction-score-seed", "interaction-score-restore",
             "interaction-current-hole-shots", "interaction-gps-acquiring",
             "interaction-club-stats", "interaction-settings",
             "interaction-flag-direction":
            interactionRound
        case "home":
            WatchRoundHomeView(
                courseName: "北京丽宫 · 前九", hole: 7, par: 4, holeCount: 9,
                scoredHoles: 6, toPar: 3, distanceText: "152 码", pendingUploads: 2,
                ringPips: (1...18).map { WatchRingPip(hole: $0, toPar: Self.demoToPars[$0], isCurrent: $0 == 7) },
                canRecordShot: true
            )
        case "caddie-options":
            WatchCaddieOptionsView(options: Self.demoOptions, recommendedId: "stock")
                .padding(8)
        case "hazards":
            WatchHazardView(hazards: Self.demoHazards)
                .padding(8)
        case "glance":
            WatchCaddieGlanceView(state: Self.demoState)
                .padding(8)
        case "scorecard":
            WatchScorecardView(holes: Self.demoScorecard, totalToPar: 2)
        case "hole-select":
            WatchHoleSelectView(holes: Array(1...18), activeHole: 7)
        case "current-hole-shots":
            ScrollView {
                WatchCurrentHoleShotsView(
                    hole: 7,
                    par: 4,
                    shots: Self.demoRecordedShots,
                    latestShotDistanceM: 38,
                    canAddShot: true
                )
            }
        case "menu":
            WatchMenuView(
                hasCaddie: true,
                hasHazards: true,
                autoShotSupported: true,
                autoShotStatus: "关闭"
            )
        case "score", "score-recommendation":
            WatchScoreHoleView(hole: 7, par: 4, score: 5, putts: 2, penalty: 0)
        case "score-total":
            WatchScoreHoleView(
                hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
                step: .score
            )
        case "score-putts":
            WatchScoreHoleView(
                hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
                step: .putts
            )
        case "score-next-tee-candidate":
            WatchScoreHoleView(
                hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
                candidateNextHole: 8
            )
        case "score-fairway":
            WatchScoreHoleView(
                hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
                step: .fairway
            )
        case "score-penalty":
            WatchScoreHoleView(
                hole: 7, par: 4, score: 5, putts: 2, penalty: 0,
                step: .penalty
            )
        case "club-prompt":
            WatchClubPromptView(
                hole: 8,
                shotNumber: 1,
                recommendedClub: "一号木",
                clubs: [
                    WatchClubOption(clubName: "一号木", medianM: 201),
                    WatchClubOption(clubName: "三号木", medianM: 183),
                    WatchClubOption(clubName: "5号铁", medianM: 165),
                    WatchClubOption(clubName: "7号铁", medianM: 139),
                ]
            )
        case "autoshot-candidate":
            WatchAutoShotCandidateView()
        case "finish":
            WatchFinishRoundView(
                courseName: "北京丽宫 · 前九", holesPlayed: 9, holeCount: 9,
                totalStrokes: 41, toPar: 5, totalPutts: 16,
                fairwaySummary: WatchOutcomeSummary(hits: 5, recorded: 7),
                girSummary: WatchOutcomeSummary(hits: 4, recorded: 9),
                pendingUploads: 2
            )
        case "start":
            WatchStartView(phoneReachable: false)
        default:
            Text("unknown uitest screen: \(screen)")
        }
    }

    private var cachedCoursePicker: some View {
        let cached = WatchCourseStore().loadCourses()
        let options = cached.flatMap { [$0.option, $0.backOption].compactMap { $0 } }
        return WatchStartView(
            phoneReachable: false,
            courses: options,
            cachedCourseIds: Set(cached.map { $0.option.globalId }),
            currentLatitude: 40.0454995,
            currentLongitude: 116.5461531
        )
    }

    private var standaloneCourseRound: some View {
        Group {
            if model.round != nil {
                WatchRoundContainerView(
                    model: model,
                    holeGeometry: standaloneCourseGeometry,
                    watchGreenYards: standaloneHomeGreenYards,
                    shotLocation: standaloneLastShotFix,
                    initialHoleMapCrownScale: screen == "standalone-course-map-zoom"
                        ? WatchHoleMapView.restingCrownScale + 0.02
                        : WatchHoleMapView.restingCrownScale
                )
            } else {
                Text("offline course restore unavailable")
            }
        }
        .onAppear {
            if screen == "standalone-course-seed", model.round == nil {
                Task { await seedStandaloneCourse() }
            } else if screen == "standalone-course-restore" {
                model.openHoleMap()
            } else if screen == "standalone-course-map-zoom" {
                model.openHoleMap()
            } else if screen == "standalone-course-caddie" {
                model.openCaddie()
            } else if screen == "standalone-course-hazards" {
                model.openHazards()
            } else if screen == "standalone-course-last-shot" {
                ensureStandaloneLastShot()
                model.openHoleMap()
            } else if screen == "standalone-course-caddie-last-shot" {
                ensureStandaloneLastShot()
                model.openCaddie()
            } else if screen == "standalone-course-live-home" {
                model.backToHome()
            }
        }
    }

    /// DEBUG-only live evidence: exercise the same production Watch course library against a real
    /// backend, then prove a second process can start the exact cached selection without config.
    private var realCourseRound: some View {
        Group {
            if model.round != nil {
                if isRealCourseHazardScreen,
                   let state = model.activeHoleState,
                   let geometry = realCourseHazardGeometry,
                   let route = state.holeMap?.route,
                   !route.isEmpty,
                   !state.hazards.isEmpty {
                    WatchHazardMapView(
                        geometry: geometry,
                        route: route,
                        hazards: state.hazards,
                        centerGreenYards: realCourseHazardCenterYards(state)
                    )
                } else {
                    WatchRoundContainerView(
                        model: model,
                        holeGeometry: realCourseGeometry,
                        watchGreenYards: realCourseGreenYards,
                        shotLocation: realCourseRuntimeFix,
                        measuredPxOverride: screen == "real-course-map-measured"
                            ? realCourseMeasuredPoint
                            : nil,
                        pinDragOverride: screen == "real-course-map-pin-drag"
                            ? CGSize(width: 16, height: 20)
                            : nil
                    )
                }
            } else {
                VStack(spacing: 8) {
                    ProgressView()
                    Text(realCourseStatus ?? "准备真实球场…")
                        .font(.caption2)
                        .multilineTextAlignment(.center)
                }
                .padding(12)
            }
        }
        .onAppear {
            guard !realCourseTaskStarted else { return }
            realCourseTaskStarted = true
            Task { @MainActor in
                if screen == "real-course-download-seed" {
                    await seedRealCourse()
                } else if screen == "real-course-journey-start" {
                    await startRealCourseJourney()
                } else if screen == "real-course-journey-advance" {
                    advanceRealCourseJourney()
                } else if screen == "real-course-journey-restore" {
                    verifyRealCourseJourney(stage: "restored")
                } else if screen == "real-course-journey-history-edit" {
                    editRealCourseJourneyHistory()
                } else if screen == "real-course-journey-finish" {
                    finishRealCourseJourney()
                } else if screen == "real-course-journey-finish-confirm" {
                    await confirmRealCourseJourneyFinish()
                } else {
                    await restoreRealCourseOffline(selectHazardHole: isRealCourseHazardScreen)
                }
            }
        }
    }

    private var isRealCourseHazardScreen: Bool {
        screen == "real-course-hazard-map" || screen == "real-course-hazard-mid-map"
    }

    private var isRealCourseJourneyScreen: Bool {
        screen.hasPrefix("real-course-journey-")
    }

    private var realCourseGeometry: WatchHoleMapGeometry? {
        guard let state = model.activeHoleState,
              let globalId = state.globalId,
              let image = WatchHoleImageStore().image(globalId: globalId, hole: state.hole) else {
            return nil
        }
        return WatchHoleMapGeometry.from(holeMap: state.holeMap, image: image)
    }

    private var realCourseMeasuredPoint: CGPoint? {
        guard let geometry = realCourseGeometry else { return nil }
        return CGPoint(
            x: geometry.youPx.x + (geometry.pinPx.x - geometry.youPx.x) * 0.55,
            y: geometry.youPx.y + (geometry.pinPx.y - geometry.youPx.y) * 0.55
        )
    }

    /// Runtime screenshots place the simulated wrist at the production course's active Tee. Distances
    /// are then recomputed from the retained green coordinates instead of displaying prepared Tee facts
    /// through the live-distance UI.
    private var realCourseRuntimeFix: WatchLocationFix? {
        guard let state = model.activeHoleState,
              let latitude = state.teeLatitude,
              let longitude = state.teeLongitude else {
            return nil
        }
        return WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: latitude, longitude: longitude),
            horizontalAccuracyM: 5,
            capturedAt: "2026-07-31T00:00:00Z"
        )
    }

    private var realCourseGreenYards: (front: Int?, center: Int?, back: Int?)? {
        guard let state = model.activeHoleState, let fix = realCourseRuntimeFix else { return nil }
        let latitude = fix.coordinate.latitude
        let longitude = fix.coordinate.longitude
        let front = WatchGeoMath.yards(
            from: latitude, longitude, toLat: state.frontGreenLat, state.frontGreenLon
        )
        let center = WatchGeoMath.yards(
            from: latitude, longitude, toLat: state.centerGreenLat, state.centerGreenLon
        )
        let back = WatchGeoMath.yards(
            from: latitude, longitude, toLat: state.backGreenLat, state.backGreenLon
        )
        guard center != nil else { return nil }
        return (front: front, center: center, back: back)
    }

    /// Same downloaded Cypress geometry, with a deterministic simulated GPS fix about 120 yards
    /// before the first real hazard. This makes the runtime comparison match the approved mid-hole
    /// state without inventing a hazard, route, or map point.
    private var realCourseHazardGeometry: WatchHoleMapGeometry? {
        guard let geometry = realCourseGeometry,
              let progress = simulatedRealCourseHazardProgressM,
              let route = model.activeHoleState?.holeMap?.route,
              let point = WatchHazardMapLayout.imagePoint(on: route, atMetres: progress) else {
            return realCourseGeometry
        }
        return geometry.withYou(point)
    }

    private var simulatedRealCourseHazardProgressM: Double? {
        guard screen == "real-course-hazard-mid-map",
              let state = model.activeHoleState else { return nil }
        let firstHazardM = state.hazards.compactMap { $0.startM ?? $0.endM }.min()
        return firstHazardM.map { max(0, $0 - 110) }
    }

    private func realCourseHazardCenterYards(_ state: WatchRoundState) -> Int {
        guard let progress = simulatedRealCourseHazardProgressM,
              let routeEnd = state.holeMap?.route?.last,
              routeEnd.count >= 3 else {
            return WatchUnits.yards(state.centerGreenM ?? 0)
        }
        return WatchUnits.yards(max(0, routeEnd[2] - progress))
    }

    private var realCourseRuntimeConfig: WatchRoundConfig? {
        let environment = ProcessInfo.processInfo.environment
        guard let rawBaseURL = environment["AI_CADDIE_API_BASE_URL"],
              let baseURL = URL(string: rawBaseURL),
              let playerToken = environment["AI_CADDIE_PLAYER_TOKEN"],
              !playerToken.isEmpty else {
            return nil
        }
        return WatchRoundConfig(
            baseURL: baseURL,
            adminToken: nil,
            sessionToken: playerToken
        )
    }

    @MainActor
    private func seedRealCourse() async {
        removeRealCourseMarkers()
        guard let config = realCourseRuntimeConfig else {
            failRealCourse("缺少真实 API 配置")
            return
        }

        let library = WatchCourseLibrary()
        await library.searchAllCourses(name: "Cypress Point", config: config)
        guard let match = library.searchMatches.first(where: { $0.globalId == Self.realCourseGlobalId }),
              let option = match.courseOption else {
            failRealCourse("真实球场搜索未返回 Cypress Point")
            return
        }

        let tees = await library.loadCourseTees(globalId: Self.realCourseGlobalId, config: config)
        guard let tee = tees.first(where: { $0.teeBox.caseInsensitiveCompare("championship") == .orderedSame })
                ?? tees.first else {
            failRealCourse("真实球场没有可用 Tee")
            return
        }

        let selectedOption = option.withTees(tees, selectedTee: tee.teeBox)
        let selection = WatchCourseSelection(
            front: selectedOption,
            teeBox: tee.teeBox,
            ensureGeometry: true
        )
        guard let prepared = await library.startCourse(selection, config: config) else {
            failRealCourse(library.errorMessage ?? "真实球场下载失败")
            return
        }

        model.seedRound(
            prepared.holeStates,
            activeHole: prepared.holeStates.first?.hole,
            courseName: prepared.courseName
        )
        writeRealCourseMarker("real-course-download-ready")
    }

    @MainActor
    private func restoreRealCourseOffline(selectHazardHole: Bool = false) async {
        removeRealCourseMarkers()
        let store = WatchCourseStore()
        guard let cached = store.course(globalId: Self.realCourseGlobalId) else {
            failRealCourse("找不到已下载的真实球场缓存")
            return
        }

        let selection = WatchCourseSelection(
            front: cached.option,
            back: cached.backOption,
            teeBox: cached.teeBox
        )
        let library = WatchCourseLibrary()
        guard let prepared = await library.startCourse(selection, config: nil) else {
            failRealCourse(library.errorMessage ?? "离线球场开局失败")
            return
        }

        let activeHole: Int?
        if selectHazardHole {
            guard let hazardHole = prepared.holeStates.first(where: {
                !$0.hazards.isEmpty && !($0.holeMap?.route?.isEmpty ?? true)
            }) else {
                failRealCourse("真实球场没有可定位的障碍")
                return
            }
            activeHole = hazardHole.hole
        } else {
            activeHole = prepared.holeStates.first?.hole
        }

        model.seedRound(
            prepared.holeStates,
            activeHole: activeHole,
            courseName: prepared.courseName
        )
        if screen == "real-course-download-caddie" {
            model.openCaddie()
        }
        if selectHazardHole {
            writeRealCourseMarker(screen == "real-course-hazard-mid-map"
                ? "real-course-hazard-mid-ready"
                : "real-course-hazard-ready")
        } else {
            writeRealCourseMarker("real-course-offline-ready")
        }
    }

    /// Begin exactly one production-store Cypress round. All later journey launches restore this
    /// `round.json`; they must never call `startCourse` or seed a replacement round.
    @MainActor
    private func startRealCourseJourney() async {
        removeJourneyCoverageMarkers()
        let previousRoundId = model.round?.roundId
        await restoreRealCourseOffline()
        guard let startedRoundId = model.round?.roundId,
              startedRoundId != previousRoundId else {
            if !FileManager.default.fileExists(
                atPath: realCourseMarkerURL("real-course-journey-failed").path
            ) {
                failRealCourseJourney("真实缓存没有建立新的连续旅程 round")
            }
            return
        }
        model.backToHome()
        verifyRealCourseJourney(stage: "started")
    }

    /// Record one real-GPS-origin shot and finish only the currently active hole. The first occurrence
    /// of each real Par uses the locked manual order; remaining holes exercise one-tap recommendation.
    @MainActor
    private func advanceRealCourseJourney() {
        removeJourneyResultMarkers()
        guard let round = model.round,
              let state = model.activeHoleState,
              round.holeStates.sorted(by: { $0.hole < $1.hole }).firstIndex(where: {
                  $0.hole == state.hole
              }) == model.scoredHoles,
              state.score == 0,
              journeyLocationCount(hole: state.hole, round: round) == 0,
              let teeLatitude = state.teeLatitude,
              let teeLongitude = state.teeLongitude else {
            failRealCourseJourney("当前洞不是按顺序等待首杆，或缺少真实 Tee GPS")
            return
        }

        model.backToHome()
        model.beginManualShot(
            latitude: teeLatitude,
            longitude: teeLongitude,
            horizontalAccuracyM: 5,
            capturedAt: String(format: "2026-07-29T12:%02d:00Z", state.hole)
        )
        guard let pending = model.pendingManualShot,
              pending.hole == state.hole,
              pending.candidateFromHole == nil,
              pending.shotNumber == 1 else {
            failRealCourseJourney("第 \(state.hole) 洞没有把真实 Tee 定位暂存为第 1 杆")
            return
        }
        model.completePendingManualShot(clubName: state.hole == 1 ? state.suggestedClub : nil)
        guard let afterShot = model.round,
              journeyLocationCount(hole: state.hole, round: afterShot) == 1 else {
            failRealCourseJourney("第 \(state.hole) 洞首杆没有唯一持久化")
            return
        }

        model.startScoringActiveHole()
        let manualMarker = journeyManualParMarker(state.par)
        if FileManager.default.fileExists(atPath: manualMarker.path) {
            model.acceptRecommendedScore()
        } else {
            model.startManualScoreEntry()
            guard model.scoreFlowStep == .score else {
                failRealCourseJourney("第 \(state.hole) 洞未进入手动总杆")
                return
            }
            model.advanceScoreEntry()
            guard model.scoreFlowStep == .putts else {
                failRealCourseJourney("第 \(state.hole) 洞未按总杆进入推杆")
                return
            }
            model.advanceScoreEntry()
            if state.par == 3 {
                guard model.scoreFlowStep == .penalty else {
                    failRealCourseJourney("Par 3 不应要求球道结果")
                    return
                }
            } else {
                guard model.scoreFlowStep == .fairway else {
                    failRealCourseJourney("Par 4/5 必须在推杆后确认球道结果")
                    return
                }
                model.selectDraftFairway(state.par == 5 ? .left : .hit)
            }
            guard model.scoreFlowStep == .penalty else {
                failRealCourseJourney("第 \(state.hole) 洞没有以罚杆步骤收口")
                return
            }
            model.saveManualScore()
            try? Data("covered".utf8).write(to: manualMarker, options: .atomic)
        }

        guard model.scoredHoles == afterShot.holeStates.filter({ $0.score > 0 }).count + 1 else {
            failRealCourseJourney("第 \(state.hole) 洞成绩没有写入同一 round")
            return
        }
        model.backToHome()
        verifyRealCourseJourney(stage: "completed-hole-\(state.hole)")
    }

    /// Mid-round edit deliberately changes hole 1 but must leave hole 10 as the live cursor.
    @MainActor
    private func editRealCourseJourneyHistory() {
        removeJourneyResultMarkers()
        guard let first = model.allHoleStates.first,
              first.score > 0,
              model.activeHole == 10,
              model.scoredHoles == 9 else {
            failRealCourseJourney("历史修改必须发生在同一 round 的第 10 洞")
            return
        }
        let activeHole = model.activeHole
        let scoreBefore = first.score
        model.startEditingHole(first.hole)
        model.adjustDraftScore(1)
        model.advanceScoreEntry()
        model.advanceScoreEntry()
        if first.par != 3 {
            model.selectDraftFairway(.right)
        }
        guard model.scoreFlowStep == .penalty else {
            failRealCourseJourney("历史洞修改没有走到罚杆确认")
            return
        }
        model.saveManualScore()
        guard model.activeHole == activeHole,
              model.allHoleStates.first?.score == scoreBefore + 1,
              model.scoredHoles == 9 else {
            failRealCourseJourney("修改历史洞错误地移动了实战洞")
            return
        }
        model.backToHome()
        verifyRealCourseJourney(stage: "edited-hole-1")
    }

    @MainActor
    private func finishRealCourseJourney() {
        removeJourneyResultMarkers()
        let realPars = Set(model.allHoleStates.map(\.par))
        guard model.scoredHoles == 18,
              model.holeCount == 18,
              realPars.allSatisfy({
                  FileManager.default.fileExists(atPath: journeyManualParMarker($0).path)
              }) else {
            failRealCourseJourney("结束汇总前并未完成同一 round 的 18 洞")
            return
        }
        model.requestFinish()
        guard model.screen == .finishing else {
            failRealCourseJourney("完整一轮没有进入真实结束汇总")
            return
        }
        verifyRealCourseJourney(stage: "finish-summary")
    }

    /// Close the exact persisted 18-hole journey through the production Watch sync path. This is a
    /// second launch after the summary screenshot, so it proves queued offline facts survive a process
    /// boundary before all acknowledgements and `/finish` permit the local round to be cleared.
    @MainActor
    private func confirmRealCourseJourneyFinish() async {
        removeJourneyResultMarkers()
        guard let config = realCourseRuntimeConfig else {
            failRealCourseJourney("结束确认缺少真实 API 配置")
            return
        }
        guard let before = model.round,
              before.holeStates.count == 18,
              Set(before.holeStates.map(\.hole)) == Set(1...18),
              before.holeStates.allSatisfy({
                  $0.roundId == before.roundId
                      && $0.globalId == Self.realCourseGlobalId
                      && $0.score > 0
                      && journeyLocationCount(hole: $0.hole, round: before) == 1
              }),
              before.pendingEvents.count == 56 else {
            failRealCourseJourney("结束确认前不是同一轮完整的 18 洞/56 条待同步记录")
            return
        }

        let imageStore = WatchHoleImageStore()
        let mappedHoles = before.holeStates.filter { state in
            guard state.holeMap != nil,
                  let image = imageStore.image(
                      globalId: Self.realCourseGlobalId,
                      hole: state.hole
                  ) else {
                return false
            }
            return WatchHoleMapGeometry.from(holeMap: state.holeMap, image: image) != nil
        }.count
        guard mappedHoles == 18 else {
            failRealCourseJourney("结束确认前只有 \(mappedHoles) 洞真实地图可恢复")
            return
        }

        let roundId = before.roundId
        let activeHole = before.activeHole
        model.config = config
        model.requestFinish()
        await model.confirmFinish()

        guard model.round == nil,
              WatchRoundStore().load() == nil,
              model.pendingUploads == 0,
              model.screen == .home,
              model.uploadError == nil,
              !model.isUploading else {
            failRealCourseJourney(
                "真实 ACK/finish 未闭环：\(model.uploadError ?? "本地 round 未清除")"
            )
            return
        }

        realCourseStatus = "18 洞已保存并结束"
        let evidence = [
            "stage=finish-confirmed",
            "round_id=\(roundId)",
            "global_id=\(Self.realCourseGlobalId)",
            "active_hole=\(activeHole)",
            "scored_holes=18",
            "hole_count=18",
            "current_hole_shots=1",
            "mapped_holes=\(mappedHoles)",
            "pending_uploads_before=56",
            "pending_uploads=0",
            "persisted_round_after=absent",
            "screen_after=home",
            "remote_finish=success",
        ].joined(separator: "\n")
        writeRealCourseMarker("real-course-journey-ready", contents: evidence)
    }

    @MainActor
    private func verifyRealCourseJourney(stage: String) {
        removeJourneyResultMarkers()
        guard let round = model.round,
              round.holeStates.count == 18,
              Set(round.holeStates.map(\.hole)) == Set(1...18),
              round.holeStates.allSatisfy({
                  $0.roundId == round.roundId && $0.globalId == Self.realCourseGlobalId
              }),
              let active = model.activeHoleState else {
            failRealCourseJourney("旅程不是 Cypress Point 的同一 18 洞 round")
            return
        }

        let expectedHole = ProcessInfo.processInfo.environment["UITEST_JOURNEY_EXPECTED_HOLE"]
            .flatMap(Int.init)
        let expectedScored = ProcessInfo.processInfo.environment["UITEST_JOURNEY_EXPECTED_SCORED"]
            .flatMap(Int.init)
        guard expectedHole == nil || expectedHole == model.activeHole,
              expectedScored == nil || expectedScored == model.scoredHoles else {
            failRealCourseJourney(
                "期望第 \(expectedHole ?? -1) 洞/完成 \(expectedScored ?? -1)，实际第 \(model.activeHole) 洞/完成 \(model.scoredHoles)"
            )
            return
        }

        let imageStore = WatchHoleImageStore()
        let mappedHoles = round.holeStates.filter { state in
            guard state.holeMap != nil,
                  let image = imageStore.image(globalId: Self.realCourseGlobalId, hole: state.hole) else {
                return false
            }
            return WatchHoleMapGeometry.from(holeMap: state.holeMap, image: image) != nil
        }.count
        guard mappedHoles == 18 else {
            failRealCourseJourney("18 洞 production image store 只有 \(mappedHoles) 洞可渲染")
            return
        }

        for state in round.holeStates {
            let shotCount = journeyLocationCount(hole: state.hole, round: round)
            if state.score > 0, shotCount != 1 {
                failRealCourseJourney("已完成第 \(state.hole) 洞不是唯一一条第 1 杆 GPS")
                return
            }
            if state.score == 0, shotCount != 0 {
                failRealCourseJourney("未完成第 \(state.hole) 洞提前收到杆事件")
                return
            }
        }

        let currentShots = journeyLocationCount(hole: active.hole, round: round)
        let evidence = [
            "stage=\(stage)",
            "round_id=\(round.roundId)",
            "global_id=\(Self.realCourseGlobalId)",
            "active_hole=\(model.activeHole)",
            "scored_holes=\(model.scoredHoles)",
            "hole_count=\(model.holeCount)",
            "current_hole_shots=\(currentShots)",
            "mapped_holes=\(mappedHoles)",
            "pending_uploads=\(model.pendingUploads)",
        ].joined(separator: "\n")
        writeRealCourseMarker("real-course-journey-ready", contents: evidence)
    }

    private func journeyLocationCount(
        hole: Int,
        round: WatchRoundStore.PersistedRound
    ) -> Int {
        round.pendingEvents.filter { $0.hole == hole && $0.kind == .location }.count
    }

    private func journeyManualParMarker(_ par: Int) -> URL {
        realCourseMarkerURL("real-course-journey-manual-par-\(par)")
    }

    private func removeJourneyCoverageMarkers() {
        for par in 3...5 {
            try? FileManager.default.removeItem(at: journeyManualParMarker(par))
        }
    }

    private func removeJourneyResultMarkers() {
        for name in ["real-course-journey-ready", "real-course-journey-failed"] {
            try? FileManager.default.removeItem(at: realCourseMarkerURL(name))
        }
    }

    private func failRealCourseJourney(_ message: String) {
        realCourseStatus = message
        writeRealCourseMarker("real-course-journey-failed", contents: message)
    }

    @MainActor
    private func failRealCourse(_ message: String) {
        realCourseStatus = message
        switch screen {
        case "real-course-download-seed":
            writeRealCourseMarker("real-course-download-failed")
        case "real-course-hazard-map", "real-course-hazard-mid-map":
            writeRealCourseMarker(screen == "real-course-hazard-mid-map"
                ? "real-course-hazard-mid-failed"
                : "real-course-hazard-failed")
        case _ where isRealCourseJourneyScreen:
            failRealCourseJourney(message)
        default:
            writeRealCourseMarker("real-course-offline-failed")
        }
    }

    private func realCourseMarkerURL(_ name: String) -> URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent(name)
    }

    private func writeRealCourseMarker(_ name: String, contents: String? = nil) {
        try? Data((contents ?? name).utf8).write(to: realCourseMarkerURL(name), options: .atomic)
    }

    private func removeRealCourseMarkers() {
        for name in [
            "real-course-download-ready", "real-course-download-failed",
            "real-course-offline-ready", "real-course-offline-failed",
            "real-course-hazard-ready", "real-course-hazard-failed",
            "real-course-hazard-mid-ready", "real-course-hazard-mid-failed",
            "real-course-journey-ready", "real-course-journey-failed",
        ] {
            try? FileManager.default.removeItem(at: realCourseMarkerURL(name))
        }
    }

    private var standaloneHomeGreenYards: (front: Int?, center: Int?, back: Int?)? {
        screen == "standalone-course-live-home"
            ? (front: 199, center: 211, back: 223)
            : (front: 248, center: 262, back: 274)
    }

    private var standaloneLastShotFix: WatchLocationFix? {
        return WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40.0454995, longitude: 116.5461531),
            horizontalAccuracyM: 5,
            capturedAt: "2026-07-27T00:01:00Z"
        )
    }

    private func ensureStandaloneLastShot() {
        guard model.recordedShotCount == 0 else { return }
        model.beginManualShot(
            latitude: 40.045,
            longitude: 116.5461531,
            horizontalAccuracyM: 5,
            capturedAt: "2026-07-27T00:00:00Z"
        )
        model.completePendingManualShot(clubName: nil)
    }

    private var standaloneCourseGeometry: WatchHoleMapGeometry? {
        guard let state = model.activeHoleState,
              let globalId = state.globalId,
              let image = WatchHoleImageStore().image(globalId: globalId, hole: state.hole) else {
            return nil
        }
        return WatchHoleMapGeometry.from(holeMap: state.holeMap, image: image)
    }

    @MainActor
    private func seedStandaloneCourse() async {
        let courseStore = WatchCourseStore()
        let imageStore = WatchHoleImageStore()
        guard let imageData = Data(base64Encoded: WatchHoleMapSample.jpegBase64) else { return }
        do {
            try courseStore.save(Self.standaloneCourseTemplate)
            try imageStore.store(data: imageData, globalId: 31669, hole: 4)
        } catch {
            return
        }
        let library = WatchCourseLibrary(
            store: courseStore,
            imageStore: imageStore,
            makeRoundId: { "ci-watch-offline-course-round" }
        )
        guard let prepared = await library.startCourse(Self.standaloneCourseOption, config: nil) else {
            return
        }
        model.seedRound(
            prepared.holeStates,
            activeHole: prepared.holeStates.first?.hole,
            courseName: prepared.courseName
        )
    }

    private var milestoneRound: some View {
        Group {
            if model.round != nil {
                WatchRoundContainerView(model: model, shotLocation: Self.milestoneWatchFix)
            } else {
                Text("round restore unavailable")
            }
        }
        .onAppear {
            if screen == "milestone-seed" {
                model.applyRoundSeed(Self.milestoneSeed)
            }
        }
    }

    private var interactionRound: some View {
        Group {
            if model.round != nil {
                WatchRoundContainerView(
                    model: model,
                    shotLocation: interactionShotLocation,
                    watchHeading: interactionHeading
                )
            } else {
                Text("interaction restore unavailable")
            }
        }
        .onAppear {
            switch screen {
            case "interaction-club-seed":
                seedInteractionClubPrompt()
            case "interaction-score-seed":
                model.applyRoundSeed(Self.interactionScoreSeed)
                model.beginManualShot(
                    latitude: 40.001,
                    longitude: 116.0,
                    horizontalAccuracyM: 5,
                    capturedAt: "2026-07-26T12:10:00Z"
                )
            case "interaction-current-hole-shots":
                seedInteractionCurrentHoleShots()
            case "interaction-gps-acquiring":
                model.applyRoundSeed(Self.interactionGPSAcquiringSeed)
                model.backToHome()
            case "interaction-club-stats":
                seedInteractionClubStats()
            case "interaction-settings":
                model.applyRoundSeed(Self.interactionGPSAcquiringSeed)
                model.openSettings()
            case "interaction-flag-direction":
                seedInteractionFlagDirection()
            default:
                break
            }
        }
    }

    /// Runtime visual evidence for the production model/container path. The pending location is real
    /// model state; the four clubs mirror a downloaded bag so the first-screen density is reviewable.
    private func seedInteractionClubPrompt() {
        let roundId = "ci-interaction-club-round"
        model.seedRound(
            [
                WatchRoundState(
                    roundId: roundId, hole: 7, par: 4, distanceM: 139,
                    teeLatitude: 40.0, teeLongitude: 116.0,
                    suggestedClub: "一号木", selectedClub: nil,
                    availableClubs: [
                        WatchClubOption(clubName: "一号木", medianM: 201),
                        WatchClubOption(clubName: "三号木", medianM: 183),
                        WatchClubOption(clubName: "5号铁", medianM: 165),
                        WatchClubOption(clubName: "7号铁", medianM: 139),
                    ],
                    score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
                ),
                WatchRoundState(
                    roundId: roundId, hole: 8, par: 5, distanceM: 472,
                    teeLatitude: 40.001, teeLongitude: 116.0,
                    selectedClub: nil,
                    score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
                ),
            ],
            activeHole: 7,
            courseName: "北京丽宫 · 前九"
        )
        model.beginManualShot(
            latitude: 40.0,
            longitude: 116.0,
            horizontalAccuracyM: 5,
            capturedAt: "2026-07-26T12:00:00Z"
        )
    }

    private func seedInteractionClubStats() {
        let roundId = "ci-interaction-club-stats-round"
        model.seedRound(
            [
                WatchRoundState(
                    roundId: roundId, hole: 1, par: 4, distanceM: 365,
                    selectedClub: nil,
                    availableClubs: [
                        WatchClubOption(clubName: "一号木", medianM: 224),
                        WatchClubOption(clubName: "三号木", medianM: 199),
                        WatchClubOption(clubName: "五号铁", medianM: 163),
                        WatchClubOption(clubName: "七号铁", medianM: 139),
                        WatchClubOption(clubName: "挖起杆", medianM: 87),
                    ],
                    score: 0, putts: 0, penaltyCount: 0, caddieConfidence: "offline"
                ),
            ],
            activeHole: 1,
            courseName: "北京丽宫"
        )
        model.openClubStats()
    }

    private func seedInteractionFlagDirection() {
        let roundId = "ci-interaction-flag-direction-round"
        model.seedRound(
            [
                WatchRoundState(
                    roundId: roundId,
                    hole: 7,
                    par: 4,
                    distanceM: 139,
                    teeLatitude: 40.0,
                    teeLongitude: 116.0,
                    selectedClub: nil,
                    centerGreenM: 139,
                    centerGreenLat: 40.0,
                    centerGreenLon: 116.00163,
                    score: 0,
                    putts: 0,
                    penaltyCount: 0,
                    caddieConfidence: "offline"
                ),
            ],
            activeHole: 7,
            courseName: "北京丽宫"
        )
        model.openFlagDirection()
    }

    private var interactionShotLocation: WatchLocationFix? {
        switch screen {
        case "interaction-current-hole-shots": return Self.interactionCurrentHoleFix
        case "interaction-flag-direction": return Self.interactionFlagFix
        default: return nil
        }
    }

    private var interactionHeading: WatchHeadingFix? {
        guard screen == "interaction-flag-direction" else { return nil }
        return WatchHeadingFix(
            trueDegrees: 110,
            accuracyDegrees: 6,
            capturedAt: Date()
        )
    }

    /// Runtime approval evidence must exercise the production model/container path, not mount the
    /// list view directly. The eastward points are spaced at roughly 245 yd, 152 yd and 42 yd so the
    /// rendered facts remain easy to compare with the approved design while still being calculated.
    private func seedInteractionCurrentHoleShots() {
        model.applyRoundSeed(Self.interactionCurrentHoleShotsSeed)
        if model.recordedShotCount == 0 {
            let shots: [(longitude: Double, club: String?, capturedAt: String)] = [
                (116.00000, "一号木", "2026-07-26T08:00:00Z"),
                (116.00263, "七号铁", "2026-07-26T08:05:00Z"),
                (116.00426, nil, "2026-07-26T08:10:00Z"),
            ]
            for shot in shots {
                model.beginManualShot(
                    latitude: 40.0,
                    longitude: shot.longitude,
                    horizontalAccuracyM: 4,
                    capturedAt: shot.capturedAt
                )
                model.completePendingManualShot(clubName: shot.club)
            }
        }
        model.openCurrentHoleShots()
    }

    private static let milestoneSeed = WatchRoundSeed(
        roundId: "ci-beijing-ligong-round-1",
        courseName: "北京丽宫体育公园高尔夫俱乐部",
        activeHole: 1,
        holes: [
            WatchRoundSeedHole(hole: 1, par: 4, distanceM: 369.4176), // 404 yards
        ]
    )

    private static let standaloneCourseOption = WatchCourseOption(
        globalId: 31669,
        name: "北京丽宫体育公园高尔夫俱乐部",
        holes: 18,
        teeBox: "Blue",
        venueName: "北京丽宫体育公园高尔夫俱乐部",
        latitude: 40.0491,
        longitude: 116.5461531,
        tees: ["Blue", "White"]
    )

    private static let setupFront = WatchCourseOption(
        globalId: 32001,
        name: "北京黑骑士 ~ A",
        holes: 9,
        teeBox: "Blue",
        venueName: "北京黑骑士",
        segmentLabel: "A",
        segmentHoles: 9,
        tees: ["Blue", "White"]
    )

    private static let setupBack = WatchCourseOption(
        globalId: 32002,
        name: "北京黑骑士 ~ B",
        holes: 9,
        teeBox: "Blue",
        venueName: "北京黑骑士",
        segmentLabel: "B",
        segmentHoles: 9,
        tees: ["Blue", "White"]
    )

    private static let remoteCourseMatches = [
        WatchCourseSearchMatch(
            globalId: 31870,
            name: "Mission Hills ~ A",
            holes: 9,
            city: "深圳",
            province: "广东",
            ratio: 0.96
        ),
        WatchCourseSearchMatch(
            globalId: 31871,
            name: "Mission Hills ~ B",
            holes: 9,
            city: "深圳",
            province: "广东",
            ratio: 0.94
        ),
    ]

    private static var remoteCourseOptions: [WatchCourseOption] {
        remoteCourseMatches.compactMap(\.courseOption)
    }

    private static let remoteCourseTees = [
        WatchCourseTee(
            teeBox: "blue",
            name: "Blue",
            geometrySet: 2,
            yards: 3210,
            holeCount: 9,
            isDefault: true
        ),
        WatchCourseTee(
            teeBox: "white",
            name: "White",
            geometrySet: 3,
            yards: 3010,
            holeCount: 9,
            isDefault: false
        ),
    ]

    /// The same real gid31669/hole-4 render already baked for design review, persisted through the
    /// production course/image stores so the second process proves an offline course start and map load.
    private static let standaloneCourseTemplate = WatchCourseTemplate(
        option: standaloneCourseOption,
        courseName: "北京丽宫体育公园高尔夫俱乐部",
        teeBox: "Blue",
        holeStates: [
            WatchRoundState(
                roundId: "download-template-only",
                hole: 4,
                par: 5,
                distanceM: 518.8,
                teeLatitude: 40.0454995,
                teeLongitude: 116.5461531,
                suggestedClub: "3号木",
                selectedClub: nil,
                availableClubs: [
                    WatchClubOption(clubName: "3号木", medianM: 205, source: "course-prep"),
                    WatchClubOption(clubName: "5号铁", medianM: 170, source: "course-prep"),
                ],
                frontGreenM: 227,
                centerGreenM: 240,
                backGreenM: 251,
                globalId: 31669,
                holeMap: WatchHoleMap(
                    w: Int(WatchHoleMapSample.imageSize.width),
                    h: Int(WatchHoleMapSample.imageSize.height),
                    you: [504, 702],
                    pin: [435, 279],
                    layup: [506, 403],
                    apex: [556, 562],
                    greenCtrl: [498, 375],
                    route: [
                        [504, 702, 0],
                        [506, 403, 210],
                        [435, 279, 400],
                    ]
                ),
                playsLikeDistanceM: 525.8,
                elevationDeltaM: 7,
                geometryCoverage: "ready",
                caddieOptions: demoOptions,
                hazards: [
                    WatchHazard(
                        kind: "bunker", label: "沙坑", startM: 170, endM: 190,
                        frontDistanceM: 168, backDistanceM: 184
                    ),
                ],
                score: 0,
                putts: 0,
                penaltyCount: 0,
                caddieConfidence: "offline"
            ),
        ],
        cachedAt: "2026-07-26T00:00:00Z"
    )

    private static let interactionClubSeed = WatchRoundSeed(
        roundId: "ci-interaction-club-round",
        courseName: "北京丽宫 · 前九",
        activeHole: 7,
        holes: [
            WatchRoundSeedHole(
                hole: 7, par: 4, distanceM: 139,
                teeLatitude: 40.0, teeLongitude: 116.0
            ),
            WatchRoundSeedHole(
                hole: 8, par: 5, distanceM: 472,
                teeLatitude: 40.001, teeLongitude: 116.0
            ),
        ]
    )

    private static let interactionScoreSeed = WatchRoundSeed(
        roundId: "ci-interaction-score-round",
        courseName: "北京丽宫 · 前九",
        activeHole: 7,
        holes: interactionClubSeed.holes
    )

    private static let interactionCurrentHoleShotsSeed = WatchRoundSeed(
        roundId: "ci-interaction-current-hole-shots-round",
        courseName: "北京丽宫 · 前九",
        activeHole: 7,
        holes: interactionClubSeed.holes
    )

    private static let interactionGPSAcquiringSeed = WatchRoundSeed(
        roundId: "ci-interaction-gps-acquiring-round",
        courseName: "北京丽宫 · 前九",
        activeHole: 7,
        holes: interactionClubSeed.holes
    )

    private static let interactionCurrentHoleFix = WatchLocationFix(
        coordinate: CLLocationCoordinate2D(latitude: 40.0, longitude: 116.00471),
        horizontalAccuracyM: 4,
        capturedAt: "2026-07-26T08:11:00Z"
    )

    private static let interactionFlagFix = WatchLocationFix(
        coordinate: CLLocationCoordinate2D(latitude: 40.0, longitude: 116.0),
        horizontalAccuracyM: 4,
        capturedAt: "2026-07-26T08:11:00Z"
    )

    private static let milestoneWatchFix = WatchLocationFix(
        coordinate: CLLocationCoordinate2D(latitude: 40.0, longitude: 116.0),
        horizontalAccuracyM: 5,
        capturedAt: "2026-07-31T00:00:00Z"
    )

    // MARK: - demo data (mirrors the design-snapshot fixtures)

    private static let demoToPars: [Int: Int] = [1: 0, 2: 1, 3: -1, 4: 2, 5: 0, 6: 1]

    static let demoOptions: [WatchCaddieOption] = [
        WatchCaddieOption(optionId: "safe", label: "稳妥", clubName: "9号铁", carryM: 128, plan: [WatchCaddiePlanStep(clubName: "3W", carryM: 172), WatchCaddiePlanStep(clubName: "9I", carryM: 128)], confidence: "high"),
        WatchCaddieOption(optionId: "stock", label: "标准", clubName: "8号铁", carryM: 142, plan: [WatchCaddiePlanStep(clubName: "1W", carryM: 192), WatchCaddiePlanStep(clubName: "8I", carryM: 142)], confidence: "high"),
        WatchCaddieOption(optionId: "attack", label: "进攻", clubName: "7号铁", carryM: 156, plan: [WatchCaddiePlanStep(clubName: "1W", carryM: 192), WatchCaddiePlanStep(clubName: "PW", carryM: 118)], confidence: "medium"),
    ]

    static let demoHazards: [WatchHazard] = [
        WatchHazard(
            kind: "bunker", label: "沙坑 1", startM: 116, endM: 132,
            frontDistanceM: 120, backDistanceM: 136
        ),
        WatchHazard(
            kind: "bunker", label: "沙坑 2", startM: 160, endM: 178,
            frontDistanceM: 165, backDistanceM: 183
        ),
        WatchHazard(
            kind: "water", label: "水域", startM: 210, endM: 235,
            frontDistanceM: 210, backDistanceM: 235
        ),
    ]

    static let demoScorecard: [WatchScorecardRow] = [
        WatchScorecardRow(hole: 1, par: 4, score: 4),
        WatchScorecardRow(hole: 2, par: 5, score: 6),
        WatchScorecardRow(hole: 3, par: 3, score: 2),
        WatchScorecardRow(hole: 4, par: 4, score: 5),
        WatchScorecardRow(hole: 5, par: 4, score: 0),
    ]

    static let demoRecordedShots: [WatchRecordedShot] = [
        WatchRecordedShot(
            eventId: "shot-1", hole: 7, number: 1, clubName: "一号木", shotType: "tee",
            location: WatchShotLocationValue(latitude: 40.0, longitude: 116.0, horizontalAccuracyM: 4)!,
            capturedAt: "2026-07-26T08:00:00Z", distanceToNextM: 224
        ),
        WatchRecordedShot(
            eventId: "shot-2", hole: 7, number: 2, clubName: "七号铁", shotType: "approach",
            location: WatchShotLocationValue(latitude: 40.001, longitude: 116.0, horizontalAccuracyM: 4)!,
            capturedAt: "2026-07-26T08:05:00Z", distanceToNextM: 139
        ),
        WatchRecordedShot(
            eventId: "shot-3", hole: 7, number: 3, clubName: nil, shotType: "recovery",
            location: WatchShotLocationValue(latitude: 40.002, longitude: 116.0, horizontalAccuracyM: 4)!,
            capturedAt: "2026-07-26T08:10:00Z", distanceToNextM: nil
        ),
    ]

    static let demoState = WatchRoundState(
        roundId: "r1", hole: 7, par: 4, distanceM: 139,
        targetNote: "右沙坑 138–150 码,避开",
        targetLatitude: 22.28, targetLongitude: 114.16, targetKind: "pin",
        suggestedClub: "7号铁", selectedClub: "7号铁",
        availableClubs: [WatchClubOption(clubName: "7号铁", medianM: 139), WatchClubOption(clubName: "6号铁", medianM: 150)],
        shotType: "approach", strategyMode: "stock", lie: "fairway",
        nextShotPrompt: "上果岭中心偏左", holePlanSummary: "3W → 8I · 上果岭",
        expectedRemainingM: 8,
        frontGreenM: 128, centerGreenM: 135, backGreenM: 142,
        playsLikeDistanceM: 138, elevationDeltaM: 3,
        caddieOptions: demoOptions, hazards: demoHazards,
        score: 4, putts: 2, penaltyCount: 0, caddieConfidence: "high"
    )
}
#endif
