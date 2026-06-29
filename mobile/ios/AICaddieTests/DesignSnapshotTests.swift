import SwiftUI
import UIKit
import XCTest
@testable import AICaddie

/// Renders the redesigned SwiftUI surfaces to PNGs in the simulator so the design
/// can be reviewed from CI without a physical device / TestFlight. The workflow
/// collects `Documents/design-snapshots/*.png` from the simulator container and
/// uploads them as the `design-snapshots` artifact.
final class DesignSnapshotTests: XCTestCase {
    @MainActor
    func testRenderLiveHoleRedesign() throws {
        let view = VStack(spacing: 12) {
            HoleDistanceHeader(
                course: "北京丽宫 · 前九", holeNumber: 7, holeCount: 9, par: 4,
                toPinYards: 152, carryFrontYards: nil, toParText: "+1",
                greenFrontYards: 140, greenCenterYards: 148, greenBackYards: 155, slopeYards: 3
            )
            CaddieRecCard(
                modeTitle: "球童建议 · 保守(护分)",
                recommendation: "7 号铁 · 上果岭中心偏左",
                rationale: "右侧沙坑 138–150 码,落点避开;球道偏窄,优先保帕。",
                chips: [(text: "期望失分最低", warn: false), (text: "命中 64%", warn: false), (text: "右沙坑", warn: true)]
            )
            VStack(alignment: .leading, spacing: 10) {
                Text("选球杆").font(.caption).foregroundStyle(.secondary)
                ClubStripView(clubs: ["5i", "6i", "7i", "8i", "9i", "PW"], selected: "7i")
                RecordShotButton(title: "📍 保存本洞 · 含定位", lastShotText: "已定位 · 精度 ±4m · 球杆 7i")
            }
            .liveCard()
            VStack(alignment: .leading, spacing: 10) {
                Text("本洞成绩").font(.caption).foregroundStyle(.secondary)
                HoleScoreSteppers(score: .constant(4), putts: .constant(2))
            }
            .liveCard()
        }
        .padding(14)
        .frame(width: 390)
        .background(Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255))

        try render(view, named: "live-hole")
    }

    @MainActor
    func testRenderRecentReview() throws {
        let fixtureURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let package = try JSONDecoder().decode(LiveRoundPackage.self, from: Data(contentsOf: fixtureURL))
        let view = RecentReviewContent(package: package)
            .frame(width: 390)
            .background(Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255))
        try render(view, named: "recent-review")
    }

    @MainActor
    func testRenderRoundHome() throws {
        let view = VStack(spacing: 12) {
            HubInProgressCard(courseName: "北京丽宫 · 前九", activeHole: 7, recorded: 6, total: 9)
            HStack(spacing: 10) {
                HubTile(icon: "map", title: "赛前攻略", subtitle: "逐洞攻略 · 试算一杆")
                HubTile(icon: "chart.line.uptrend.xyaxis", title: "历史复盘", subtitle: "441 场近况")
            }
            HubLastRoundCard(courseName: "北京天竺黑骑士 C/A", date: "06-11", score: 89, toPar: 17)
        }
        .padding(14)
        .frame(width: 390)
        .background(Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255))
        try render(view, named: "round-home")
    }

    @MainActor
    func testRenderCaddiePlan() throws {
        func option(_ id: String, _ label: String, _ club: String, _ carry: Double, _ risk: Double) -> CaddiePlanOption {
            CaddiePlanOption(
                id: id, label: label, carryM: carry, riskScore: risk, clubName: club,
                p10M: nil, p90M: nil, sampleSize: 42, confidence: "high", coverageText: "8/10",
                expectedStrokes: 4.0, expectedStrokesDelta: -0.2, scoreImpactModel: nil,
                sourceRefs: ["geometry:31795:7"], missingDataLabels: []
            )
        }
        func step(_ role: String, _ club: String, _ carry: Double, _ remaining: Double) -> CaddiePlanSequenceStep {
            CaddiePlanSequenceStep(id: "\(role)-\(club)", role: role, clubName: club, targetCarryM: carry,
                                   expectedRemainingM: remaining, sampleSize: 42, confidence: "high", sourceRefs: [])
        }
        func sequence(_ id: String, _ strokes: Int, _ confidence: String, _ steps: [CaddiePlanSequenceStep]) -> CaddiePlanSequence {
            CaddiePlanSequence(id: id, label: steps.map(\.clubName).joined(separator: "-"), expectedStrokes: strokes,
                               expectedRemainingM: steps.last?.expectedRemainingM, riskScore: nil, confidence: confidence,
                               coverageText: nil, sourceRefs: [], steps: steps)
        }
        // round-11: 整洞序列为主 — three 打法 each a 开球→攻果岭 chain (user-approved direction).
        let view = CaddiePlanView(
            options: [
                option("stock", "稳妥", "7i", 150, 1),
                option("attack", "进攻搏鸟", "6i", 165, 3),
                option("layup", "放置短切", "9i", 120, 1),
            ],
            selectedOptionId: "stock",
            sequences: [
                sequence("safe", 2, "high", [step("advance", "3W", 160, 155), step("scoring", "6I", 150, 5)]),
                sequence("stock", 2, "medium", [step("advance", "Driver", 180, 133), step("scoring", "PW", 130, 3)]),
                sequence("attack", 2, "low", [step("advance", "Driver", 180, 133), step("scoring", "SW", 125, 8)]),
            ],
            selectedSequenceId: "stock",
            // round-10: multiple bunkers are numbered + sorted near→far (CaddiePlanHazard.from), so
            // three avoid zones aren't all just "沙坑". Build via .from to exercise that real logic.
            hazards: CaddiePlanHazard.from(
                CoursePrepHazards(waterCarry: [[175, 195]], bunkers: [[210, 225], [138, 150]])
            )
        )
        .padding(14)
        .frame(width: 390)
        .background(Color.white)
        try render(view, named: "caddie-plan")
    }

    /// Full-screen capture of a REAL screen (NavigationStack + ScrollView render fully here,
    /// unlike SwiftUI ImageRenderer). Hosts the view in an on-screen UIWindow and snapshots
    /// the rendered hierarchy — what the running app actually draws (top viewport).
    @MainActor
    func testCaptureLiveScreens() throws {
        let fixtureURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("AICaddie/Fixtures/live_round_package.fixture.json")
        let package = try JSONDecoder().decode(LiveRoundPackage.self, from: Data(contentsOf: fixtureURL))

        // 黑骑士 = A/B/C 三个 9 洞环 + 北湖 = 单一 18 洞,验证按球场列环的选场 UI。
        let blackKnightTees = ["Gold", "Blue", "White", "Red"]
        let courses = [
            MobileCourseOption(globalId: 31794, name: "北京天竺黑骑士球员俱乐部 ~ A", roundCount: 40, suggestedLiveRoundId: "live-31794", holes: 9, teeBox: "blue", geometryCoverage: "ready", venueName: "北京天竺黑骑士球员俱乐部", segmentLabel: "A", segmentHoles: 9, tees: blackKnightTees),
            MobileCourseOption(globalId: 31795, name: "北京天竺黑骑士球员俱乐部 ~ B", roundCount: 30, suggestedLiveRoundId: "live-31795", holes: 9, teeBox: "blue", geometryCoverage: "ready", venueName: "北京天竺黑骑士球员俱乐部", segmentLabel: "B", segmentHoles: 9, tees: blackKnightTees),
            MobileCourseOption(globalId: 31796, name: "北京天竺黑骑士球员俱乐部 ~ C", roundCount: 58, suggestedLiveRoundId: "live-31796", holes: 9, teeBox: "blue", geometryCoverage: "ready", venueName: "北京天竺黑骑士球员俱乐部", segmentLabel: "C", segmentHoles: 9, tees: blackKnightTees),
            MobileCourseOption(globalId: 41825, name: "北京北湖九号国际高尔夫俱乐部", roundCount: 40, suggestedLiveRoundId: "live-41825", holes: 18, teeBox: "blue", geometryCoverage: "ready", venueName: "北京北湖九号国际高尔夫俱乐部", segmentLabel: nil, segmentHoles: 18, tees: ["Black", "Blue", "White", "Red"]),
        ]

        // Pass a non-nil apiBaseURL so the 备战 tile (gated on apiBaseURL) renders — without it
        // the snapshot hides 备战 and misrepresents the real app.
        let apiBaseURL = URL(string: "https://caddie.example")
        try captureScreen(RoundHomeView(package: package, apiBaseURL: apiBaseURL, courseOptions: courses), named: "full-home")
        // Hub WITH an in-progress round → shows the 进行中 card + 「结束本场」(cancel) button.
        let activeState = LiveRoundStateSnapshot(roundId: package.roundId, activeHole: package.holes.first?.number ?? 1, holes: [])
        try captureScreen(
            RoundHomeView(package: package, apiBaseURL: apiBaseURL, liveRoundState: activeState, courseOptions: courses, startingNine: "front"),
            named: "full-home-active"
        )
        try captureScreen(NavigationStack { StartRoundView(courseOptions: courses) }, named: "full-start")
        try captureScreen(NavigationStack { PrepCoursePickerView(courseOptions: courses, apiBaseURL: apiBaseURL, adminToken: nil) }, named: "full-prep-picker")
        if let hole = package.holes.first {
            try captureScreen(NavigationStack { CurrentHoleView(package: package, hole: hole) }, named: "full-hole")
        }
        try captureScreen(RecentRoundReviewView(package: package), named: "full-review")

        // Dark Mode regression guard. WITHOUT the app's fix, the light-themed screens render
        // white-on-white in Dark Mode (cards Color.white, text semantic .primary → white).
        // WITH the app-root fix (.preferredColorScheme(.light)) the hierarchy renders light even
        // in a Dark window — these two captures document the bug and prove the fix.
        try captureScreen(RoundHomeView(package: package, apiBaseURL: apiBaseURL, courseOptions: courses), named: "dark-broken", dark: true)
        try captureScreen(RoundHomeView(package: package, apiBaseURL: apiBaseURL, courseOptions: courses).preferredColorScheme(.light), named: "dark-fixed", dark: true)

        // 2D hole map = server-rendered hole image + recommended route/landing/club overlay.
        // Synthesise a green hole image + overlay route so the overlay rendering is verifiable.
        let mapW = 240, mapH = 360
        let holeImage = UIGraphicsImageRenderer(size: CGSize(width: mapW, height: mapH)).image { ctx in
            UIColor(red: 0.46, green: 0.66, blue: 0.40, alpha: 1).setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: mapW, height: mapH))
            UIColor(red: 0.60, green: 0.78, blue: 0.45, alpha: 1).setFill()
            ctx.fill(CGRect(x: 92, y: 40, width: 56, height: 280))
            UIColor(red: 0.50, green: 0.80, blue: 0.43, alpha: 1).setFill()
            ctx.cgContext.fillEllipse(in: CGRect(x: 96, y: 28, width: 48, height: 42))
        }
        let b64 = "data:image/jpeg;base64," + (holeImage.jpegData(compressionQuality: 0.85)?.base64EncodedString() ?? "")
        let prepJSON = """
        {"hole":7,"par":4,"par_source":"courseview","blue_yards":410,"route_len_m":375,\
        "route":[[120,330],[118,180],[120,55]],"steps":[{"club":"D","note":"开球"}],\
        "cautions":[],"hazards":{"water_carry":[],"bunkers":[]},"landing_m":150,"tee_club":"D",\
        "map":{"image":"\(b64)","overlay":{"w":\(mapW),"h":\(mapH),"ppm":1.0,"ln":375,\
        "route":[[120,330,0],[118,180,150],[120,55,375]]}}}
        """
        let prepHole = try JSONDecoder().decode(CoursePrepHole.self, from: Data(prepJSON.utf8))
        try captureScreen(VStack { HoleImageMapView(hole: prepHole).frame(height: 460) }.padding(24), named: "hole-map")

        // 单场复盘: hole-by-hole scorecard + score strip + phase summary + graceful missing-data,
        // rendered from a round-detail fixture (mirrors /api/v2/history/rounds/{ref}).
        let roundJSON = """
        {"roundRef":"r1","found":true,"title":"Fixture Links",\
        "round":{"courseName":"Fixture Links","date":"2026-05-20","score":81,"par":72,"toPar":9,"holesCompleted":9,"confidence":"high"},\
        "scorecard":[\
        {"hole":1,"par":4,"score":5,"toPar":1,"className":"bogey","putts":2,"status":"complete"},\
        {"hole":2,"par":3,"score":3,"toPar":0,"className":"par","putts":2,"gir":true,"status":"complete"},\
        {"hole":3,"par":5,"score":4,"toPar":-1,"className":"birdie","putts":1,"status":"complete"},\
        {"hole":4,"par":4,"score":6,"toPar":2,"className":"double","putts":3,"fairway":"left","status":"complete"},\
        {"hole":5,"par":4,"score":4,"toPar":0,"className":"par","putts":2,"status":"complete"}],\
        "phaseSummary":[\
        {"phase":"Tee","state":"ready","primary":"5/9 球道命中"},\
        {"phase":"Approach","state":"ready","primary":"3/9 标准杆上果岭(GIR)"},\
        {"phase":"Short Game","state":"ready","primary":"2 次短杆"},\
        {"phase":"Putting","state":"ready","primary":"31 推"},\
        {"phase":"Penalty / Damage","state":"partial","primary":"1 个双柏忌及以上"}],\
        "missingData":[{"label":"shot rows","state":"missing","reason":"no normalized Garmin shot rows for this round"}]}
        """
        let roundDetail = try JSONDecoder().decode(RoundDetail.self, from: Data(roundJSON.utf8))
        try captureScreen(
            RoundReviewContent(detail: roundDetail, isLoading: false, errorText: nil, fallbackCourseName: "Fixture Links"),
            named: "round-review"
        )

        // 数据统计: overview KPIs + 近场折线图 + 成绩分布 + by-par(3/4/5) + putting + trends + quarter +
        // courses(按球场聚合,可钻取各九洞) + clubs (距离按码), from a compact mobile-stats fixture.
        let statsJSON = """
        {"summary":{"totalRounds":423,"average18":92.4,"median18":92,"recent10Average":94.6,"bestScore":82,"worstScore":106,"handicapEstimate":18.2},\
        "trend":{"points":[\
        {"date":"2026-05-01","score":95,"toPar":23,"birdies":1,"pars":6,"bogeys":7,"doublesPlus":4},\
        {"date":"2026-05-10","score":91,"toPar":19,"birdies":2,"pars":7,"bogeys":7,"doublesPlus":2},\
        {"date":"2026-05-20","score":89,"toPar":17,"birdies":1,"pars":9,"bogeys":6,"doublesPlus":2},\
        {"date":"2026-06-01","score":86,"toPar":14,"birdies":3,"pars":9,"bogeys":5,"doublesPlus":1}]},\
        "scoring":{"outcomes":{"eagleOrBetter":1,"birdie":40,"par":300,"bogey":250,"doubleOrWorse":120},\
        "outcomeDistribution":[{"key":"eagleOrBetter","label":"Eagle+","count":1,"pct":0.5},{"key":"birdie","label":"Birdie","count":40,"pct":6.5},{"key":"par","label":"Par","count":300,"pct":43.5},{"key":"bogey","label":"Bogey","count":250,"pct":35.2},{"key":"double","label":"Double","count":70,"pct":10.2},{"key":"triple","label":"Triple","count":20,"pct":2.8},{"key":"quadPlus","label":"+4 or worse","count":10,"pct":1.4}],\
        "scoreBands":[{"label":"80s","count":42},{"label":"90s","count":171},{"label":"100+","count":93}],\
        "byPar":[{"par":3,"averageToPar":0.62,"parOrBetterPct":38},{"par":4,"averageToPar":0.44,"parOrBetterPct":42},{"par":5,"averageToPar":0.21,"parOrBetterPct":55},{"par":6,"averageToPar":1.1,"parOrBetterPct":10}],\
        "phaseStats":[{"phase":"Tee","fairwaysRecorded":180,"fairwaysHit":102,"fairwayMissLeft":46,"fairwayMissRight":32},{"phase":"Approach","girRecorded":300,"gir":99,"girPct":33},{"phase":"Putting","averagePutts":1.9,"threePutts":40}],\
        "teeDirection":{"recorded":180,"hit":102,"left":46,"right":32,"hitPct":57,"dominantMiss":"left"},\
        "putting":{"averagePutts":1.9,"averagePuttsPerRound":32.5,"roundsWithPutts":120,"threePutts":240}},\
        "time":{"byQuarter":[{"key":"2026-Q2","roundCount":12,"average18":92.4,"bestScore":84,"outcomes":{"birdie":14,"doubleOrWorse":31}}]},\
        "courses":[{"courseKey":"bk","courseName":"北京天竺黑骑士","roundCount":128,"average18":91.0,"bestScore":82,"worstScore":99,\
        "rounds":[{"roundId":"r-901","date":"2026-06-11","score":89,"toPar":17,"holesCompleted":18,"nine":"北京天竺黑骑士 ~ C/A"},\
        {"roundId":"r-880","date":"2026-05-28","score":86,"toPar":14,"holesCompleted":18,"nine":"北京天竺黑骑士 ~ B/C"},\
        {"roundId":"r-855","date":"2026-05-12","score":94,"toPar":22,"holesCompleted":18,"nine":"北京天竺黑骑士 ~ A/B"}],\
        "nineBreakdown":[{"label":"北京天竺黑骑士 ~ C/A","roundCount":58,"average":89.0,"bestScore":82},{"label":"北京天竺黑骑士 ~ B/C","roundCount":40,"average":92.0,"bestScore":85},{"label":"北京天竺黑骑士 ~ A/B","roundCount":30,"average":93.0,"bestScore":88}]}],\
        "clubs":[{"club":"Driver","sampleCount":120,"median":210,"p10":195,"p90":225,"consistency":"high","distanceTrend":"stable"},\
        {"club":"7I","sampleCount":90,"median":138,"p10":130,"p90":146,"consistency":"high","distanceTrend":"up"}],\
        "diagnosis":{"topIssue":"double_or_worse","issueTrends":[{"issue":"tee_miss","direction":"worsening","estimatedStrokesLost":1.2},{"issue":"three_putt","direction":"improving","estimatedStrokesLost":-0.6}]}}
        """
        let mobileStats = try JSONDecoder().decode(MobileStats.self, from: Data(statsJSON.utf8))
        try captureScreen(StatsContent(stats: mobileStats, isLoading: false, errorText: nil), named: "stats")
        // 球场钻取(round-10):各九洞组合 + 所有比赛(时间·成绩,点单场看复盘)。
        if let course = mobileStats.courses.first {
            try captureScreen(NavigationStack { CourseStatsDetailView(course: course) }, named: "course-detail")
        }

        // 球杆设置: defaults to the player's REAL Garmin bag (real names, incl 自定义 50/54/58 挖起杆)
        // resolved from /club/player + /club/types, with history distances (码).
        let bagProfiles = [
            ClubProfile(clubName: "Driver", sampleSize: 120, medianM: 210, p10M: 195, p90M: 225),
            ClubProfile(clubName: "5I", sampleSize: 60, medianM: 165, p10M: 158, p90M: 172),
            ClubProfile(clubName: "7I", sampleSize: 90, medianM: 140, p10M: 132, p90M: 148),
            ClubProfile(clubName: "PW", sampleSize: 70, medianM: 110, p10M: 102, p90M: 118),
        ]
        // The owner's actual 14-club bag resolved from Garmin (clubTypeId map + custom 50/54/58 wedges).
        let bag: Set<String> = [
            "一号木", "三号木", "三号小鸡腿", "五号铁", "六号铁", "七号铁", "八号铁", "九号铁",
            "P 杆", "A 杆", "50° 挖起杆", "54° 挖起杆", "58° 挖起杆", "推杆",
        ]
        try captureScreen(
            ClubSettingsContent(selected: bag, clubProfiles: bagProfiles, distancesYd: .constant(["七号铁": 140, "P 杆": 110])),
            named: "club-settings"
        )

        // 复盘逐洞落点图: this round's actual shots (tee→landing→green) on the hole, dots by lie.
        let shotMapJSON = """
        {"found":true,"hole":1,"par":4,\
        "map":{"image":"\(b64)","overlay":{"w":\(mapW),"h":\(mapH),"ppm":1.0,"ln":360,\
        "route":[[120,330,0],[118,180,180],[120,55,360]]}},\
        "shots":[\
        {"start":[120,330],"end":[122,200],"club":"Driver","lie":"TeeBox","endLie":"Fairway","shotType":"TEE","order":1,"synthetic":false},\
        {"start":[122,200],"end":[110,120],"club":"7I","lie":"Fairway","endLie":"Bunker","shotType":"APPROACH","order":2,"synthetic":false},\
        {"start":[110,120],"end":[119,60],"club":"SW","lie":"Bunker","endLie":"Green","shotType":"APPROACH","order":3,"synthetic":false}]}
        """
        let shotMap = try JSONDecoder().decode(RoundHoleShotMap.self, from: Data(shotMapJSON.utf8))
        try captureScreen(
            VStack(spacing: 12) { RoundShotMapView(shotMap: shotMap).frame(height: 420); RoundShotMapLegend() }
                .padding(24)
                .background(Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255)),
            named: "round-shot-map"
        )
    }

    @MainActor
    private func captureScreen(_ view: some View, named name: String, dark: Bool = false) throws {
        let size = CGSize(width: 390, height: 844)
        let style: UIUserInterfaceStyle = dark ? .dark : .light
        let host = UIHostingController(rootView: view)
        host.overrideUserInterfaceStyle = style
        host.view.frame = CGRect(origin: .zero, size: size)
        let window = UIWindow(frame: host.view.frame)
        window.overrideUserInterfaceStyle = style
        window.rootViewController = host
        window.makeKeyAndVisible()
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        // Pump the runloop so SwiftUI commits its first render, then capture the layer tree
        // (synchronous; works headless, unlike drawHierarchy(afterScreenUpdates:) which needs
        // a live display and renders blank in CI).
        RunLoop.main.run(until: Date(timeIntervalSinceNow: 1.0))
        host.view.layoutIfNeeded()
        let renderer = UIGraphicsImageRenderer(size: size)
        let image = renderer.image { ctx in
            window.layer.render(in: ctx.cgContext)
        }
        guard let data = image.pngData() else {
            XCTFail("no png for \(name)")
            return
        }
        let dir = try FileManager.default
            .url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
            .appendingPathComponent("design-snapshots", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try data.write(to: dir.appendingPathComponent("\(name).png"))
        print("WROTE_SCREEN \(name)")
    }

    @MainActor
    private func render(_ view: some View, named name: String) throws {
        let renderer = ImageRenderer(content: view)
        renderer.scale = 2
        guard let image = renderer.uiImage, let data = image.pngData() else {
            XCTFail("ImageRenderer produced no image for \(name)")
            return
        }
        let dir = try FileManager.default
            .url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
            .appendingPathComponent("design-snapshots", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try data.write(to: dir.appendingPathComponent("\(name).png"))

        let attachment = XCTAttachment(image: image)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
        print("WROTE_SNAPSHOT \(name)")
    }
}
