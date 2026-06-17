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
                toPinYards: 152, carryFrontYards: nil, toParText: "+1"
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
        let view = CaddiePlanView(
            options: [
                option("stock", "稳妥", "7i", 150, 1),
                option("attack", "进攻搏鸟", "6i", 165, 3),
                option("layup", "放置短切", "9i", 120, 1),
            ],
            selectedOptionId: "stock",
            hazards: [
                CaddiePlanHazard(id: "b0", icon: "🏖", label: "沙坑", detail: "138–150m"),
                CaddiePlanHazard(id: "w0", icon: "💧", label: "水域", detail: "越线 175m"),
            ]
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

        let courses = [
            MobileCourseOption(globalId: 31796, courseKey: "bk", name: "北京天竺黑骑士球员俱乐部 ~ C/A", roundCount: 58, latestRoundId: "r1", latestRoundDate: "2026-06-11", templateRoundId: "r1", suggestedLiveRoundId: "live-31796", holes: 18, teeBox: "blue", geometryCoverage: "missing", sourceRefs: []),
            MobileCourseOption(globalId: 31793, courseKey: "lg", name: "北京丽宫体育公园高尔夫俱乐部", roundCount: 6, latestRoundId: "r2", latestRoundDate: "2026-06-12", templateRoundId: "r2", suggestedLiveRoundId: "live-31793", holes: 18, teeBox: "blue", geometryCoverage: "missing", sourceRefs: []),
        ]

        try captureScreen(RoundHomeView(package: package, courseOptions: courses), named: "full-home")
        try captureScreen(NavigationStack { StartRoundView(courseOptions: courses) }, named: "full-start")
        if let hole = package.holes.first {
            try captureScreen(NavigationStack { CurrentHoleView(package: package, hole: hole) }, named: "full-hole")
        }
        try captureScreen(RecentRoundReviewView(package: package), named: "full-review")
    }

    @MainActor
    private func captureScreen(_ view: some View, named name: String) throws {
        let size = CGSize(width: 390, height: 844)
        let host = UIHostingController(rootView: view)
        host.overrideUserInterfaceStyle = .light
        host.view.frame = CGRect(origin: .zero, size: size)
        let window = UIWindow(frame: host.view.frame)
        window.rootViewController = host
        window.makeKeyAndVisible()
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.7))
        let renderer = UIGraphicsImageRenderer(size: size)
        let image = renderer.image { _ in
            _ = window.drawHierarchy(in: window.bounds, afterScreenUpdates: true)
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
