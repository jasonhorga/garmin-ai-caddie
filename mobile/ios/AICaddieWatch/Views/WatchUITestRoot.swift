#if DEBUG
import CoreLocation
import SwiftUI

/// Real-runtime watch screenshots: launched with `-uitest-screen <name>` (via `simctl launch`), the watch
/// app renders the REAL target view with demo data at its root so `simctl io screenshot` captures it in
/// the actual watchOS simulator runtime — including List/ScrollView content that ImageRenderer design
/// snapshots cannot render. DEBUG-only: never compiled into the Release/TestFlight binary. watchOS has no
/// XCUITest, so this direct-render-by-arg harness is how the watch surfaces get genuine running-app shots.
public struct WatchUITestRoot: View {
    public let screen: String
    @ObservedObject private var model: WatchRoundModel

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
             "standalone-course-caddie", "standalone-course-hazards",
             "standalone-course-last-shot", "standalone-course-caddie-last-shot",
             "standalone-course-live-home":
            standaloneCourseRound
        case "course-picker":
            cachedCoursePicker
        case "interaction-club-seed", "interaction-club-restore",
             "interaction-score-seed", "interaction-score-restore":
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
        case "menu":
            WatchMenuView(
                hasCaddie: true,
                hasHazards: true,
                autoShotSupported: true,
                autoShotStatus: "关闭"
            )
        case "score", "score-recommendation":
            WatchScoreHoleView(hole: 7, par: 4, score: 5, putts: 2, penalty: 0)
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
        case "club-prompt":
            WatchClubPromptView(
                hole: 8,
                shotNumber: 1,
                recommendedClub: "一号木",
                clubs: ["一号木", "三号木", "5号铁", "7号铁"]
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
        return WatchStartView(
            phoneReachable: false,
            courses: cached.map(\.option),
            cachedCourseIds: Set(cached.map { $0.option.globalId })
        )
    }

    private var standaloneCourseRound: some View {
        Group {
            if model.round != nil {
                WatchRoundContainerView(
                    model: model,
                    holeGeometry: standaloneCourseGeometry,
                    watchGreenYards: standaloneHomeGreenYards,
                    shotLocation: standaloneLastShotFix
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

    private var standaloneHomeGreenYards: (front: Int?, center: Int?, back: Int?)? {
        guard screen == "standalone-course-live-home" else { return nil }
        return (front: 199, center: 211, back: 223)
    }

    private var standaloneLastShotFix: WatchLocationFix? {
        guard screen == "standalone-course-last-shot"
                || screen == "standalone-course-caddie-last-shot" else {
            return nil
        }
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
                WatchRoundContainerView(model: model)
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
                WatchRoundContainerView(model: model)
            } else {
                Text("interaction restore unavailable")
            }
        }
        .onAppear {
            switch screen {
            case "interaction-club-seed":
                model.applyRoundSeed(Self.interactionClubSeed)
                model.beginManualShot(
                    latitude: 40.0,
                    longitude: 116.0,
                    horizontalAccuracyM: 5,
                    capturedAt: "2026-07-26T12:00:00Z"
                )
            case "interaction-score-seed":
                model.applyRoundSeed(Self.interactionScoreSeed)
                model.beginManualShot(
                    latitude: 40.001,
                    longitude: 116.0,
                    horizontalAccuracyM: 5,
                    capturedAt: "2026-07-26T12:10:00Z"
                )
            default:
                break
            }
        }
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
        tees: ["Blue", "White"]
    )

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
                    greenCtrl: [498, 375]
                ),
                playsLikeDistanceM: 525.8,
                elevationDeltaM: 7,
                geometryCoverage: "ready",
                hazards: [
                    WatchHazard(kind: "bunker", label: "沙坑", startM: 180, endM: 195),
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

    // MARK: - demo data (mirrors the design-snapshot fixtures)

    private static let demoToPars: [Int: Int] = [1: 0, 2: 1, 3: -1, 4: 2, 5: 0, 6: 1]

    static let demoOptions: [WatchCaddieOption] = [
        WatchCaddieOption(optionId: "safe", label: "稳妥", clubName: "9号铁", carryM: 128, expectedStrokes: 3.1, confidence: "high"),
        WatchCaddieOption(optionId: "stock", label: "标准", clubName: "8号铁", carryM: 142, expectedStrokes: 3.0, confidence: "high"),
        WatchCaddieOption(optionId: "attack", label: "进攻", clubName: "7号铁", carryM: 156, expectedStrokes: 3.2, confidence: "medium"),
    ]

    static let demoHazards: [WatchHazard] = [
        WatchHazard(kind: "bunker", label: "沙坑 1", startM: 120, endM: 140),
        WatchHazard(kind: "bunker", label: "沙坑 2", startM: 165, endM: 178),
        WatchHazard(kind: "water", label: "水域", startM: 210, endM: 235),
    ]

    static let demoScorecard: [WatchScorecardRow] = [
        WatchScorecardRow(hole: 1, par: 4, score: 4),
        WatchScorecardRow(hole: 2, par: 5, score: 6),
        WatchScorecardRow(hole: 3, par: 3, score: 2),
        WatchScorecardRow(hole: 4, par: 4, score: 5),
        WatchScorecardRow(hole: 5, par: 4, score: 0),
    ]

    static let demoState = WatchRoundState(
        roundId: "r1", hole: 7, par: 4, distanceM: 139,
        targetNote: "右沙坑 138–150 码,避开",
        targetLatitude: 22.28, targetLongitude: 114.16, targetKind: "pin",
        suggestedClub: "7号铁", selectedClub: "7号铁",
        availableClubs: [WatchClubOption(clubName: "7号铁", medianM: 139), WatchClubOption(clubName: "6号铁", medianM: 150)],
        shotType: "approach", strategyMode: "stock", lie: "fairway",
        nextShotPrompt: "上果岭中心偏左", holePlanSummary: "开球 → 攻果岭",
        expectedStrokes: 4.1, expectedRemainingM: 8,
        frontGreenM: 128, centerGreenM: 135, backGreenM: 142,
        playsLikeDistanceM: 138, elevationDeltaM: 3,
        caddieOptions: demoOptions, hazards: demoHazards,
        score: 4, putts: 2, penaltyCount: 0, caddieConfidence: "high"
    )
}
#endif
