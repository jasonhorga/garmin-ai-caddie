import XCTest
@testable import AICaddie

/// 设置 → 离线球场 rows: the only surface that shows whole-course download progress.
final class OfflineCourseDownloadProgressTests: XCTestCase {
    private func record(
        _ globalId: Int,
        phase: PrepCourseDownloadPhase,
        downloaded: Int = 0,
        total: Int = 18,
        errorText: String? = nil
    ) -> PrepCourseDownloadRecord {
        PrepCourseDownloadRecord(
            course: MobileCourseOption(globalId: globalId, name: "球场 \(globalId)", holes: total, teeBox: "blue"),
            teeBox: "blue",
            phase: phase,
            downloadedHoles: downloaded,
            totalHoles: total,
            errorText: errorText
        )
    }

    func testProgressClampsToItsTotal() {
        let over = LiveCourseDownloadProgress(roundId: "r", courseName: "丽宫", readyHoles: 20, totalHoles: 18)
        XCTAssertEqual(over.readyHoles, 18)
        XCTAssertTrue(over.isComplete)
        let empty = LiveCourseDownloadProgress(roundId: "r", courseName: "丽宫", readyHoles: -1, totalHoles: 0)
        XCTAssertEqual(empty.totalHoles, 1)
        XCTAssertEqual(empty.readyHoles, 0)
        XCTAssertEqual(empty.fraction, 0)
    }

    func testLiveRowLeadsWhileItsRoundIsCurrentAndShowsABarUntilComplete() {
        let live = LiveCourseDownloadProgress(roundId: "r1", courseName: "丽宫", readyHoles: 5, totalHoles: 18)
        let rows = OfflineCourseDownloadRow.rows(
            live: live,
            liveRoundId: "r1",
            downloads: [record(7, phase: .ready, downloaded: 18)]
        )
        XCTAssertEqual(rows.map(\.id).first, "live:r1")
        XCTAssertEqual(rows[0].title, "丽宫")
        XCTAssertEqual(rows[0].subtitle, "本场")
        XCTAssertEqual(rows[0].status, "已下载 5/18 洞")
        XCTAssertEqual(try XCTUnwrap(rows[0].fraction), 5.0 / 18.0, accuracy: 0.0001)

        let done = OfflineCourseDownloadRow.rows(
            live: LiveCourseDownloadProgress(roundId: "r1", courseName: "丽宫", readyHoles: 18, totalHoles: 18),
            liveRoundId: "r1",
            downloads: []
        )
        XCTAssertEqual(done.map(\.status), ["已下载 18 洞"])
        XCTAssertNil(done[0].fraction, "a finished course has no progress bar")
    }

    func testLiveRowDisappearsOnceItsRoundIsNoLongerCurrent() {
        let live = LiveCourseDownloadProgress(roundId: "old", courseName: "丽宫", readyHoles: 9, totalHoles: 18)
        XCTAssertTrue(OfflineCourseDownloadRow.rows(live: live, liveRoundId: nil, downloads: []).isEmpty)
        XCTAssertTrue(OfflineCourseDownloadRow.rows(live: live, liveRoundId: "new", downloads: []).isEmpty)
    }

    func testPrepRowsMapEachPhaseAndOnlyInFlightRowsCarryABar() {
        let downloads = [
            record(1, phase: .queued),
            record(2, phase: .preparing, downloaded: 3),
            record(3, phase: .downloading, downloaded: 9, total: 9),
            record(4, phase: .ready, downloaded: 18),
            record(5, phase: .failed, errorText: "network"),
            record(6, phase: .failed, errorText: "两段 9 洞组合暂不支持备战下载"),
        ]
        let rows = OfflineCourseDownloadRow.rows(live: nil, liveRoundId: "r", downloads: downloads)
        XCTAssertEqual(rows.map(\.status), [
            "等待下载",
            "已下载 3/18 洞",
            "已下载 9/9 洞",
            "已下载 18 洞",
            "下载失败",
            "暂不支持备战",
        ])
        XCTAssertEqual(rows.map { $0.fraction != nil }, [false, true, true, false, false, false])
        XCTAssertEqual(rows[1].subtitle, MobileCourseSearchView.recentRowSubtitle(downloads[1]))
        XCTAssertEqual(Set(rows.map(\.id)).count, rows.count)
    }
}
