import XCTest

/// Real running-app screenshots of the 发球台 (tee) picker on 开始一场 (XCUITest, not ImageRenderer).
/// Launches the ACTUAL app pointed at the live backend (funnel) with the owner admin token + a
/// simulated on-course GPS fix (all via launchEnvironment), navigates 首页主卡 → 开始一场, selects a
/// tee dot and captures it. The tee options come from `GET /api/v2/courses/{id}/tees` (colour + total
/// yards + default), so the tee row shows real tee choices with yardage. PNGs + per-screen
/// accessibility-tree dumps are written to the test process Documents dir; native-mobile.yml collects
/// `*Documents/real-screenshots/*`.
final class TeeSelectionUITests: XCTestCase {
    private let app = XCUIApplication()
    /// The suite intentionally reuses one simulator installation. Reset only the first launch of
    /// each test method; later relaunches are part of the same journey and must retain its round.
    private var shouldResetActiveRoundOnNextLaunch = true

    /// Read a config value the test runner may receive either plain or TEST_RUNNER_-prefixed.
    private func cfg(_ key: String) -> String? {
        let env = ProcessInfo.processInfo.environment
        return env[key] ?? env["TEST_RUNNER_\(key)"]
    }

    override func setUpWithError() throws {
        continueAfterFailure = false
        shouldResetActiveRoundOnNextLaunch = true
        app.launchEnvironment["AI_CADDIE_API_BASE_URL"] = cfg("AI_CADDIE_API_BASE_URL") ?? ""
        app.launchEnvironment["AI_CADDIE_ADMIN_TOKEN"] = cfg("AI_CADDIE_ADMIN_TOKEN") ?? ""
        for key in UITestBackendLaunchConfiguration.markerKeys {
            app.launchEnvironment.removeValue(forKey: key)
        }
        app.launchEnvironment.merge(
            UITestBackendLaunchConfiguration.markers(
                fixtureMode: cfg("AI_CADDIE_FIXTURE_MODE"),
                dataMode: cfg("AI_CADDIE_DATA_MODE")
            )
        ) { _, new in new }
        // XCUIApplication keeps launchEnvironment mutations between test methods. Clear every
        // test-only fault/permission switch here so the empty-nearby and transport-failure
        // journeys cannot change one another's production branch or depend on execution order.
        for key in [
            "UITEST_FORCE_NEARBY_FAILURE",
            "UITEST_FORCE_COURSE_PACKAGE_FAILURE",
            "UITEST_FORCE_LIVE_NETWORK_FAILURE",
            "UITEST_COURSE_TEES_DELAY_MS",
            "UITEST_LOCATION_AUTHORIZATION",
            "UITEST_RESET_ACTIVE_ROUND",
            "UITEST_DISABLE_EVENT_SYNC",
        ] {
            app.launchEnvironment.removeValue(forKey: key)
        }
        // 北京丽宫第 1 洞蓝 T: a real CourseView tee on the same course this flow verifies.
        app.launchEnvironment["UITEST_GPS_LAT"] = cfg("UITEST_GPS_LAT") ?? "40.0454995"
        app.launchEnvironment["UITEST_GPS_LON"] = cfg("UITEST_GPS_LON") ?? "116.5461531"
        app.launchEnvironment["UITEST_MODE"] = "1"
    }

    func testCaptureTeeSelector() throws {
        app.launchEnvironment["UITEST_COURSE_TEES_DELAY_MS"] = "1500"
        writeDiagnostics()
        launchFresh()
        save("01-home"); dump("01-home")

        // 首页主卡 → 开始一场 (StartRoundView), opened without a preselected course.
        guard openStartRound() else {
            save("02-start-missing"); dump("02-start-missing")
            XCTFail("the real home must expose and open 开始一场")
            return
        }
        settle(9)
        save("02-start-round"); dump("02-start-round")  // 一个球场列表 + 第一个环 + 发球台圆点

        // This injected coordinate can legitimately return several nearby venues. Reaching the Tee
        // row therefore requires an explicit venue choice; history must never silently select one
        // for the player. Use the real Beijing Palace catalogue row verified by the same GPS.
        let palaceRow = app.buttons["start-round-venue-31793"]
        guard palaceRow.waitForExistence(timeout: 15), palaceRow.isHittable else {
            XCTFail("the production nearby response must list Beijing Palace (31793)")
            return
        }
        XCTAssertTrue(
            nearbyDistanceRows().firstMatch.waitForExistence(timeout: 60),
            "the complete provider nearby result must list nearby venues with their distance"
        )
        XCTAssertEqual(
            palaceRow.value as? String,
            "未选择",
            "multiple nearby venues must wait for the player's explicit choice"
        )
        XCTAssertFalse(
            app.buttons["start-round-primary-action"].isEnabled,
            "a course from history must not become the implicit nearby selection"
        )
        palaceRow.tap()
        let palace = app.buttons["start-round-course-segment-31793"]
        XCTAssertTrue(palace.waitForExistence(timeout: 8), "the selected venue must show its loop tile")
        let startAction = app.buttons["start-round-primary-action"]
        XCTAssertTrue(
            waitUntilEnabled(startAction, timeout: 90),
            "the selected course must load its Tee authority and become startable"
        )
        let becameSelected = waitForValue("已选择", on: palace, timeout: 8)
        save("02b-start-round-selected"); dump("02b-start-round-selected")
        XCTAssertTrue(
            becameSelected,
            "the explicit nearby-course choice must become the active segment"
        )
        XCTAssertTrue(
            waitUntilEnabled(app.buttons["start-round-primary-action"], timeout: 90),
            "the selected nearby course must load its Tee authority and become startable"
        )
        // README §8: an 18-hole course is two loops, 前九 / 后九; only the first is chosen here.
        XCTAssertTrue(palace.label.contains("前九"), "the 18-hole course's first tile is its 前九")
        XCTAssertTrue(
            app.buttons["start-round-course-half-back-31793"].exists,
            "the 18-hole course must offer 后九 as the other first loop"
        )
        XCTAssertTrue(
            startAction.label.hasPrefix("从 前九 开始"),
            "the primary action must name the chosen first loop and its tee"
        )

        // The 发球台 row: colour dots with this course's yardages from GET /courses/{id}/tees.
        let teeRow = app.descendants(matching: .any)["start-round-tee-selector"]
        XCTAssertTrue(teeRow.waitForExistence(timeout: 10), "the selected course must show its tee dots")
        settle(2)
        save("03-tee-row"); dump("03-tee-row")
        // Change from the real default to the real white Tee and prove the selection is reflected in
        // the primary action while the course remains startable.
        let whiteTee = app.buttons.matching(
            NSPredicate(format: "identifier ==[c] %@", "start-round-tee-white")
        ).firstMatch
        XCTAssertTrue(
            whiteTee.waitForExistence(timeout: 5) && whiteTee.isHittable,
            "the real Beijing Palace Tee authority must expose its white Tee"
        )
        XCTAssertTrue(whiteTee.label.hasPrefix("白 T"), "a tee dot is labelled with its colour and yards")
        whiteTee.tap()
        XCTAssertTrue(waitForValue("已选择", on: whiteTee, timeout: 5), "the tapped tee must become selected")
        XCTAssertTrue(
            startAction.label.hasSuffix("· 白 T"),
            "the primary action must name the newly selected white Tee"
        )
        XCTAssertTrue(app.buttons["start-round-primary-action"].isEnabled)
        save("04-white-tee-selected"); dump("04-white-tee-selected")
    }

    /// Unlike the deterministic journeys below, this path must use the simulator's real
    /// CLLocationManager delivery. The workflow resets TCC and sets the simulator coordinate before
    /// xcodebuild starts; this test accepts the system sheet and proves that the authorization
    /// callback restarts location updates and reaches the provider-backed nearby catalogue.
    func testRealCoreLocationAuthorizationFindsNearbyCourse() throws {
        app.launchEnvironment.removeValue(forKey: "UITEST_GPS_LAT")
        app.launchEnvironment.removeValue(forKey: "UITEST_GPS_LON")
        app.launchEnvironment.removeValue(forKey: "UITEST_LOCATION_AUTHORIZATION")
        launchFresh()

        guard openStartRound() else {
            XCTFail("the home must expose 开始一场 before the real Core Location request")
            return
        }

        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let locationAlert = springboard.alerts.firstMatch
        XCTAssertTrue(
            locationAlert.waitForExistence(timeout: 12),
            "the clean simulator must show the real iOS location authorization sheet"
        )
        let allowedLabels = [
            "Allow While Using App",
            "使用 App 时允许",
            "使用App时允许",
        ]
        let allow = allowedLabels.lazy
            .map { locationAlert.buttons[$0] }
            .first { $0.exists && $0.isHittable }
        XCTAssertNotNil(allow, "the real location sheet must expose its while-in-use approval")
        allow?.tap()

        XCTAssertTrue(app.navigationBars["开始一场"].waitForExistence(timeout: 8))
        let palace = app.buttons["start-round-venue-31793"]
        XCTAssertTrue(
            palace.waitForExistence(timeout: 60),
            "a real Core Location fix at Beijing Palace must reach the Garmin nearby result"
        )
        XCTAssertTrue(
            palace.label.contains("公里"),
            "real Core Location must reach the provider result (nearby rows carry their distance)"
        )
        XCTAssertGreaterThan(
            nearbyDistanceRows().count,
            1,
            "the live Beijing coordinate is known to return several physical venues"
        )
        XCTAssertEqual(
            palace.value as? String,
            "未选择",
            "real GPS with several nearby venues must not silently select a historical course"
        )
        save("real-core-location-01-nearby")
        dump("real-core-location-01-nearby")
    }

    func testDeniedGPSStillOffersCatalogueSearchInsteadOfHistory() throws {
        app.launchEnvironment.removeValue(forKey: "UITEST_GPS_LAT")
        app.launchEnvironment.removeValue(forKey: "UITEST_GPS_LON")
        app.launchEnvironment["UITEST_LOCATION_AUTHORIZATION"] = "denied"
        launchFresh()

        guard openStartRound() else {
            XCTFail("the home must keep the new-round entry available when GPS is denied")
            return
        }
        XCTAssertTrue(app.navigationBars["开始一场"].waitForExistence(timeout: 8))
        save("denied-01-start-round"); dump("denied-01-start-round")
        settle(4)
        XCTAssertFalse(
            nearbyDistanceRows().firstMatch.exists,
            "denied GPS must not list any course as nearby"
        )
        let search = app.buttons["start-round-search-all-courses"]
        XCTAssertTrue(
            search.waitForExistence(timeout: 5) && search.isHittable,
            "denied GPS must never strand the player without city/name search"
        )
        let start = app.buttons["start-round-primary-action"]
        XCTAssertTrue(start.exists)
        XCTAssertFalse(start.isEnabled, "no historical course may be silently selected as nearby")

        search.tap()
        XCTAssertTrue(app.navigationBars["找球场"].waitForExistence(timeout: 8))
        let nearby = app.buttons["course-catalog-nearby-action"]
        XCTAssertTrue(nearby.exists, "the start-round catalogue must retain the nearby affordance")
        XCTAssertFalse(nearby.isEnabled, "denied GPS must not issue a nearby query with invented coordinates")

        // Do not stop at proving that a text field exists. Exercise the complete fallback against the
        // live Garmin catalogue: city-only search -> factual provider row -> selection -> real Tee load.
        let city = app.textFields["course-catalog-city-field"]
        XCTAssertTrue(city.waitForExistence(timeout: 5))
        city.tap()
        city.typeText("北京")
        let submit = app.buttons["course-catalog-search-action"]
        XCTAssertTrue(waitUntilEnabled(submit, timeout: 5))
        submit.tap()
        XCTAssertTrue(waitUntilGone(app.keyboards.firstMatch, timeout: 8))

        let palaceResult = app.buttons["course-catalog-result-31793"]
        XCTAssertTrue(
            bringIntoView(palaceResult, maxSwipes: 30),
            "city-only search must return the real Beijing Palace catalogue row while GPS is denied"
        )
        palaceResult.tap()

        let selectedPalace = app.buttons["start-round-course-segment-31793"]
        XCTAssertTrue(selectedPalace.waitForExistence(timeout: 12))
        XCTAssertTrue(
            waitForValue("已选择", on: selectedPalace, timeout: 8),
            "the manual fallback result must become the explicit start-round selection"
        )
        XCTAssertTrue(
            waitUntilEnabled(app.buttons["start-round-primary-action"], timeout: 90),
            "the denied-GPS fallback must load real Tee authority and leave the round startable"
        )
    }

    func testAuthorizedGPSWithoutFixStillOffersCompleteCatalogueFallback() throws {
        app.launchEnvironment.removeValue(forKey: "UITEST_GPS_LAT")
        app.launchEnvironment.removeValue(forKey: "UITEST_GPS_LON")
        app.launchEnvironment["UITEST_LOCATION_AUTHORIZATION"] = "authorized"
        // Keep this evidence round local to the simulator. The explicit cleanup below still exercises
        // the real end-menu path, while no score/shot event can reach the owner's backend.
        app.launchEnvironment["UITEST_DISABLE_EVENT_SYNC"] = "1"
        launchFresh()

        guard openStartRound() else {
            XCTFail("the home must keep the new-round entry available while an authorized GPS waits for a fix")
            return
        }
        XCTAssertTrue(app.navigationBars["开始一场"].waitForExistence(timeout: 8))
        XCTAssertFalse(
            nearbyDistanceRows().firstMatch.exists,
            "authorized Core Location without a fix must not claim any nearby course"
        )
        let search = app.buttons["start-round-search-all-courses"]
        XCTAssertTrue(
            search.waitForExistence(timeout: 5) && search.isHittable,
            "waiting for a GPS fix must never block city/name search"
        )
        XCTAssertFalse(app.buttons["start-round-primary-action"].isEnabled)
        save("no-fix-01-start-round"); dump("no-fix-01-start-round")

        search.tap()
        XCTAssertTrue(app.navigationBars["找球场"].waitForExistence(timeout: 8))
        XCTAssertFalse(
            app.buttons["course-catalog-nearby-action"].isEnabled,
            "the app must not invent coordinates merely because permission is granted"
        )
        try searchAndSelectBeijingPalace(field: "course-catalog-keyword-field", text: "北京丽宫")
        XCTAssertTrue(
            waitUntilEnabled(app.buttons["start-round-primary-action"], timeout: 90),
            "an authorized-but-fixless player must still reach a startable real course"
        )

        let start = app.buttons["start-round-primary-action"]
        XCTAssertTrue(bringIntoView(start, maxSwipes: 20))
        start.tap()
        defer { discardActiveRoundForEvidence() }

        let firstHole = app.staticTexts["第 1 洞"]
        XCTAssertTrue(
            firstHole.waitForExistence(timeout: 90),
            "manual search without a GPS fix must enter the first hole immediately"
        )
        let factualMap = app.descendants(matching: .any).matching(
            NSPredicate(format: "identifier BEGINSWITH %@", "live-hole-map-")
        ).firstMatch
        XCTAssertTrue(
            factualMap.waitForExistence(timeout: 90),
            "the searched course must render its factual map without waiting for GPS"
        )
        let caddiePlan = openCaddiePlan(timeout: 90)
        XCTAssertTrue(
            caddiePlan.exists,
            "the no-GPS start must still expose the static-map caddie recommendation"
        )
        let teeReference = app.descendants(matching: .any).matching(
            // B1 distance ladder: the static tee reference reads "发球台 · 码" (live: "到果岭 · 码").
            NSPredicate(format: "label CONTAINS %@", "发球台 · 码")
        ).firstMatch
        XCTAssertTrue(
            teeReference.waitForExistence(timeout: 5),
            "the no-GPS hero must label its F/M/B values as Tee-referenced static distances"
        )

        // B1c: the Touch Target lives on the main map itself. A tap places it, a tap on it clears it.
        let openMap = app.descendants(matching: .any)
            .matching(identifier: "live-open-map-from-hero")
            .firstMatch
        XCTAssertTrue(
            openMap.waitForExistence(timeout: 8) && openMap.isHittable,
            "the full-screen hole map must be the Touch Target surface"
        )
        let targetMarker = app.descendants(matching: .any)
            .matching(identifier: "live-map-target-marker")
            .firstMatch
        XCTAssertFalse(targetMarker.exists)
        // The interaction layer is one gesture surface; a normalized coordinate is the closest
        // representation of the player's tap on the real map.
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.50, dy: 0.45)).tap()
        XCTAssertTrue(
            targetMarker.waitForExistence(timeout: 8),
            "a map tap without GPS must place a local Touch Target on the main map"
        )
        XCTAssertTrue(
            targetMarker.label.contains("发球台 → 目标"),
            "no-GPS Touch Target distances must be labelled from the Tee, not from the phone"
        )
        XCTAssertFalse(
            targetMarker.label.contains("当前位置 → 目标"),
            "a no-GPS map target must never claim to start at the current phone location"
        )
        XCTAssertFalse(
            app.descendants(matching: .any).matching(identifier: "live-map-distance-panel").firstMatch.exists,
            "the retired Touch Target page must not reappear"
        )
        targetMarker.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        let cleared = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == false"),
            object: targetMarker
        )
        XCTAssertEqual(
            XCTWaiter().wait(for: [cleared], timeout: 5),
            .completed,
            "a tap on the target clears it"
        )

        // The green itself is the entry point from the same no-GPS round. Verify its real zoom surface; the
        // active drag loupe remains a video/device-evidence concern because XCTest cannot snapshot a
        // transient, held gesture without mislabelling a post-release frame.
        let greenEditor = app.buttons["live-open-green-from-hero"]
        if greenEditor.waitForExistence(timeout: 8), !greenEditor.isHittable {
            // Diagnostics for the real-simulator log: what covers the green entry's hit point.
            let point = CGPoint(x: greenEditor.frame.midX, y: greenEditor.frame.midY)
            print("DIAG live-open-green-from-hero frame=\(greenEditor.frame) window=\(app.windows.firstMatch.frame)")
            for element in app.descendants(matching: .any).allElementsBoundByIndex
            where !element.identifier.isEmpty && element.frame.contains(point) {
                print("DIAG covering id=\(element.identifier) type=\(element.elementType.rawValue) frame=\(element.frame)")
            }
        }
        XCTAssertTrue(greenEditor.waitForExistence(timeout: 8) && greenEditor.isHittable)
        greenEditor.tap()
        // View Green opens on the focused, centered putting surface. There is no redundant
        // plus-button: pinch/drag is reserved for deliberate precision interaction.
        let greenPanel = app.descendants(matching: .any)["live-green-distance-panel"]
        XCTAssertTrue(greenPanel.waitForExistence(timeout: 8))
        XCTAssertFalse(app.buttons["live-green-zoom-in"].exists)
        let closeGreen = app.buttons["关闭果岭地图"]
        XCTAssertTrue(closeGreen.waitForExistence(timeout: 5) && closeGreen.isHittable)
        closeGreen.tap()

        // The live hole image itself pages between adjacent holes. This exercises the actual SwiftUI
        // drag route, while map editing remains isolated inside its full-screen precision surfaces.
        let firstHero = app.descendants(matching: .any)
            .matching(identifier: "live-open-map-from-hero")
            .firstMatch
        XCTAssertTrue(firstHero.waitForExistence(timeout: 8) && firstHero.isHittable)
        firstHero.swipeLeft()
        XCTAssertTrue(app.staticTexts["第 2 洞"].waitForExistence(timeout: 30))
        let secondHero = app.descendants(matching: .any)
            .matching(identifier: "live-open-map-from-hero")
            .firstMatch
        XCTAssertTrue(secondHero.waitForExistence(timeout: 30) && secondHero.isHittable)
        secondHero.swipeRight()
        XCTAssertTrue(app.staticTexts["第 1 洞"].waitForExistence(timeout: 30))
    }

    func testNoCourseWithinFiftyKilometresStillOffersCompleteCatalogueFallback() throws {
        // 0,0 is open ocean. This drives the production nearby endpoint to an honest empty result
        // without a fake response or a test-only app route.
        app.launchEnvironment["UITEST_GPS_LAT"] = "0"
        app.launchEnvironment["UITEST_GPS_LON"] = "0"
        app.launchEnvironment.removeValue(forKey: "UITEST_LOCATION_AUTHORIZATION")
        launchFresh()

        guard openStartRound() else {
            XCTFail("the home must open a new round even when the current area has no course")
            return
        }
        XCTAssertTrue(app.navigationBars["开始一场"].waitForExistence(timeout: 8))
        // No status prose any more: an empty result simply lists no nearby row (a transport
        // failure adds only the retry icon).
        settle(20)
        XCTAssertFalse(
            nearbyDistanceRows().firstMatch.exists,
            "an ocean coordinate must not list any nearby course"
        )
        XCTAssertFalse(
            app.buttons["start-round-venue-31793"].exists,
            "the empty nearby result must not be repopulated from play history"
        )
        XCTAssertFalse(app.buttons["start-round-primary-action"].isEnabled)
        save("empty-nearby-01-start-round"); dump("empty-nearby-01-start-round")

        let search = app.buttons["start-round-search-all-courses"]
        XCTAssertTrue(search.exists && search.isHittable)
        search.tap()
        XCTAssertTrue(app.navigationBars["找球场"].waitForExistence(timeout: 8))
        try searchAndSelectBeijingPalace(field: "course-catalog-city-field", text: "北京")
        XCTAssertTrue(
            waitUntilEnabled(app.buttons["start-round-primary-action"], timeout: 90),
            "an empty nearby result must still reach a startable real course through city search"
        )
    }

    func testNearbyServiceFailureWithoutLocalCacheStillOffersCompleteCatalogueFallback() throws {
        // A remote failure is different from an honest empty result. Use an ocean coordinate so
        // any course cached by another test is factually outside the local 50 km fallback.
        app.launchEnvironment["UITEST_GPS_LAT"] = "0"
        app.launchEnvironment["UITEST_GPS_LON"] = "0"
        app.launchEnvironment["UITEST_FORCE_NEARBY_FAILURE"] = "1"
        app.launchEnvironment.removeValue(forKey: "UITEST_LOCATION_AUTHORIZATION")
        launchFresh()

        guard openStartRound() else {
            XCTFail("the home must keep the new-round entry available when nearby discovery fails")
            return
        }
        XCTAssertTrue(app.navigationBars["开始一场"].waitForExistence(timeout: 8))
        XCTAssertTrue(
            app.buttons["start-round-retry-nearby"].waitForExistence(timeout: 20),
            "a transport failure without a factual local candidate must settle to the retry icon + search"
        )
        XCTAssertFalse(
            app.buttons.matching(
                NSPredicate(format: "identifier BEGINSWITH %@", "start-round-venue-")
            ).firstMatch.exists,
            "a failed request at an ocean coordinate must not repopulate the list from history"
        )
        XCTAssertFalse(app.buttons["start-round-primary-action"].isEnabled)

        let search = app.buttons["start-round-search-all-courses"]
        XCTAssertTrue(search.exists && search.isHittable)
        search.tap()
        XCTAssertTrue(app.navigationBars["找球场"].waitForExistence(timeout: 8))
        try searchAndSelectBeijingPalace(field: "course-catalog-keyword-field", text: "北京丽宫")
        XCTAssertTrue(
            waitUntilEnabled(app.buttons["start-round-primary-action"], timeout: 90),
            "nearby transport failure must still reach a startable real course through name search"
        )
    }

    func testDownloadedNearbyCourseStartsACompletelyNewRoundWithAllLiveServicesOffline() throws {
        // Phase 1: use the production path once to retain the selected course's all-hole lightweight
        // facts and topo bitmaps. Start remains immediate; this marker arrives from its background
        // download and proves that the later offline launch is not relying on another test's cache.
        launchFresh()
        guard openStartRound() else {
            XCTFail("the real home must open a course for the offline-cache setup")
            return
        }
        XCTAssertTrue(app.navigationBars["开始一场"].waitForExistence(timeout: 8))
        let palace = selectCourse(31793, timeout: 20)
        XCTAssertTrue(
            palace.exists,
            "the production nearby result must expose the real Beijing Palace course"
        )
        XCTAssertTrue(waitForValue("已选择", on: palace, timeout: 8))
        let onlineStart = app.buttons["start-round-primary-action"]
        XCTAssertTrue(
            waitUntilEnabled(onlineStart, timeout: 90),
            "the selected real course must load Tee authority"
        )
        XCTAssertTrue(bringIntoView(onlineStart, maxSwipes: 20))
        onlineStart.tap()
        XCTAssertTrue(app.staticTexts["第 1 洞"].waitForExistence(timeout: 90))
        let cacheReady = app.descendants(matching: .any)["live-hole-offline-course-ready"]
        let becameReady = cacheReady.waitForExistence(timeout: 240)
        if !becameReady {
            // Preserve the actual screen and accessibility state before XCTest aborts this method.
            // A failed cache gate must be diagnosable without guessing or merely extending timeouts.
            save("offline-cache-01-timeout")
            dump("offline-cache-01-timeout")
        }
        XCTAssertTrue(
            becameReady,
            "the selected course must retain every drawable hole and available topo before offline acceptance"
        )
        save("offline-cache-01-online-ready"); dump("offline-cache-01-online-ready")
        // B1: 返回 opens the scorecard; 回到首页 there keeps the round.
        let back = app.buttons["计分卡"]
        XCTAssertTrue(back.waitForExistence(timeout: 5))
        back.tap()
        let leaveHome = app.buttons["live-scorecard-leave-home"]
        XCTAssertTrue(leaveHome.waitForExistence(timeout: 5))
        leaveHome.tap()
        XCTAssertTrue(
            app.buttons["home-in-progress-round"].waitForExistence(timeout: 8),
            "returning from the cache warm-up must preserve the active round card"
        )
        app.terminate()

        // Phase 2: disable bootstrap refresh, nearby discovery, Tee lookup, course package, per-hole
        // prep, online caddie, topo fetch, and map-upgrade polling. The only valid source now is the
        // local template and local bitmaps produced above.
        app.launchEnvironment["UITEST_FORCE_NEARBY_FAILURE"] = "1"
        app.launchEnvironment["UITEST_FORCE_COURSE_PACKAGE_FAILURE"] = "1"
        app.launchEnvironment["UITEST_FORCE_LIVE_NETWORK_FAILURE"] = "1"
        launchFresh(resetActiveRound: true)

        guard openStartRound() else {
            XCTFail("the home must open a new round with all live services offline")
            return
        }
        XCTAssertTrue(app.navigationBars["开始一场"].waitForExistence(timeout: 8))
        XCTAssertTrue(app.buttons["start-round-retry-nearby"].waitForExistence(timeout: 20))
        XCTAssertFalse(
            nearbyDistanceRows().firstMatch.exists,
            "a failed nearby request must not list any course as nearby"
        )

        let downloaded = firstDownloadedCourseSegment()
        XCTAssertTrue(
            downloaded.waitForExistence(timeout: 8),
            "only a genuinely downloaded nearby course may survive the service failure"
        )
        XCTAssertEqual(
            downloaded.value as? String,
            "未选择",
            "an offline package must require an explicit tap after nearby discovery fails"
        )
        if downloaded.value as? String != "已选择" {
            downloaded.tap()
        }
        XCTAssertTrue(waitForValue("已选择", on: downloaded, timeout: 8))
        XCTAssertTrue(
            app.buttons.matching(
                NSPredicate(format: "identifier BEGINSWITH %@", "start-round-course-segment-")
            ).firstMatch.waitForExistence(timeout: 5),
            "the selected downloaded venue must show its loop tile"
        )

        let start = app.buttons["start-round-primary-action"]
        XCTAssertTrue(
            waitUntilEnabled(start, timeout: 20),
            "a downloaded course must remain startable without any live metadata request"
        )
        if !start.isHittable { app.swipeUp() }
        XCTAssertTrue(start.isHittable)
        start.tap()

        XCTAssertTrue(
            app.staticTexts["第 1 洞"].waitForExistence(timeout: 30),
            "the fully offline action must enter the factual first hole"
        )
        XCTAssertTrue(
            app.descendants(matching: .any)["topo-hole-base-ready"].waitForExistence(timeout: 10),
            "the offline first hole must render the retained topo bitmap, not a network loading state"
        )
        XCTAssertTrue(
            app.descendants(matching: .any)["live-caddie-complete-route"].firstMatch.waitForExistence(timeout: 10),
            "the offline decision must retain its complete club chain on the map"
        )
        XCTAssertFalse(
            app.buttons["改第 1 洞成绩"].exists,
            "rebasing a downloaded course must not inherit a previous round's score events"
        )
        save("offline-start-01-new-first-hole"); dump("offline-start-01-new-first-hole")
    }

    // MARK: - navigation helpers

    private func launchFresh(resetActiveRound: Bool = false) {
        if resetActiveRound || shouldResetActiveRoundOnNextLaunch {
            app.launchEnvironment["UITEST_RESET_ACTIVE_ROUND"] = "1"
            app.launchEnvironment["UITEST_DISABLE_EVENT_SYNC"] = "1"
            shouldResetActiveRoundOnNextLaunch = false
        } else {
            app.launchEnvironment.removeValue(forKey: "UITEST_RESET_ACTIVE_ROUND")
            app.launchEnvironment.removeValue(forKey: "UITEST_DISABLE_EVENT_SYNC")
        }
        if app.state == .runningForeground { app.terminate() }
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 30), "app did not foreground")
        // Home renders cached/fixture instantly, then the funnel fetch swaps in real data.
        settle(20)
    }

    private func settle(_ seconds: TimeInterval) { Thread.sleep(forTimeInterval: seconds) }

    private func waitForValue(_ expected: String, on element: XCUIElement, timeout: TimeInterval) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        repeat {
            if (element.value as? String) == expected { return true }
            Thread.sleep(forTimeInterval: 0.2)
        } while Date() < deadline
        return (element.value as? String) == expected
    }

    private func waitUntilEnabled(_ element: XCUIElement, timeout: TimeInterval) -> Bool {
        if element.exists, element.isEnabled { return true }
        let expectation = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == true AND enabled == true"),
            object: element
        )
        return XCTWaiter.wait(for: [expectation], timeout: timeout) == .completed
    }

    private func waitUntilGone(_ element: XCUIElement, timeout: TimeInterval) -> Bool {
        if !element.exists { return true }
        let expectation = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == false"),
            object: element
        )
        return XCTWaiter.wait(for: [expectation], timeout: timeout) == .completed
    }

    /// The live root exposes the complete route directly without a second presentation layer.
    @discardableResult
    private func openCaddiePlan(timeout: TimeInterval) -> XCUIElement {
        // B1: the selected route is drawn on the full-screen map; its accessible summary is the
        // evidence that the structured recommendation arrived.
        let route = app.descendants(matching: .any)["live-caddie-complete-route"].firstMatch
        XCTAssertTrue(
            route.waitForExistence(timeout: timeout),
            "the live map must carry the complete caddie route"
        )
        return route
    }

    private func searchAndSelectBeijingPalace(field identifier: String, text: String) throws {
        let field = app.textFields[identifier]
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        field.tap()
        field.typeText(text)
        let submit = app.buttons["course-catalog-search-action"]
        XCTAssertTrue(waitUntilEnabled(submit, timeout: 5))
        submit.tap()
        XCTAssertTrue(waitUntilGone(app.keyboards.firstMatch, timeout: 8))

        let result = app.buttons["course-catalog-result-31793"]
        let foundResult = bringIntoView(result, maxSwipes: 30)
        if !foundResult {
            save("catalogue-\(identifier)-result-missing")
            dump("catalogue-\(identifier)-result-missing")
        }
        XCTAssertTrue(
            foundResult,
            "manual catalogue fallback must return the real Beijing Palace row"
        )
        result.tap()
        let selected = app.buttons["start-round-course-segment-31793"]
        XCTAssertTrue(selected.waitForExistence(timeout: 12))
        XCTAssertTrue(
            waitForValue("已选择", on: selected, timeout: 8),
            "the manually found course must become the explicit start-round selection"
        )
    }

    private func bringIntoView(_ element: XCUIElement, maxSwipes: Int) -> Bool {
        for _ in 0..<maxSwipes {
            if element.exists, element.isHittable, fullyVisible(element) { return true }
            if element.exists, element.frame.minY < visibleSafeRect().minY {
                app.swipeDown()
            } else {
                app.swipeUp()
            }
            settle(0.6)
        }
        return element.exists && element.isHittable && fullyVisible(element)
    }

    /// SwiftUI can report a row at the bottom edge as hittable even when its tap point is under the
    /// iPhone home-indicator lane. Require the full row to be inside the usable viewport before
    /// tapping so a catalogue selection exercises the real button action.
    private func visibleSafeRect() -> CGRect {
        let windowFrame = app.windows.firstMatch.frame
        var top = windowFrame.minY + 8
        // A sheet leaves the underlying start-round navigation bar in the accessibility tree. Use
        // the active catalogue bar first; otherwise its frame falsely marks every top result as
        // covered and the helper oscillates between the list's two scroll bounds.
        let catalogueNavigationBar = app.navigationBars["找球场"]
        let navigationBar = catalogueNavigationBar.exists
            ? catalogueNavigationBar
            : app.navigationBars.firstMatch
        if navigationBar.exists {
            top = max(top, navigationBar.frame.maxY + 8)
        }
        let bottom = windowFrame.maxY - 34
        return CGRect(
            x: windowFrame.minX + 8,
            y: top,
            width: max(0, windowFrame.width - 16),
            height: max(0, bottom - top)
        )
    }

    private func fullyVisible(_ element: XCUIElement) -> Bool {
        let frame = element.frame
        return !frame.isNull && !frame.isEmpty && visibleSafeRect().contains(frame)
    }

    /// B4b: 开始一场 is one course list. After a failed nearby request the only rows left are
    /// local ones (downloaded / recent); the first venue row is the downloaded course.
    private func firstDownloadedCourseSegment() -> XCUIElement {
        app.buttons.matching(
            NSPredicate(format: "identifier BEGINSWITH %@", "start-round-venue-")
        ).firstMatch
    }

    /// Provider-nearby rows are the only rows that carry a distance ("1.2 公里").
    private func nearbyDistanceRows() -> XCUIElementQuery {
        app.buttons.matching(
            NSPredicate(format: "identifier BEGINSWITH %@ AND label CONTAINS %@", "start-round-venue-", "公里")
        )
    }

    /// Select a course in the one list (its venue row), then return its loop tile.
    @discardableResult
    private func selectCourse(_ globalId: Int, timeout: TimeInterval) -> XCUIElement {
        let tile = app.buttons["start-round-course-segment-\(globalId)"]
        if tile.exists, tile.value as? String == "已选择" { return tile }
        let row = app.buttons["start-round-venue-\(globalId)"]
        if row.waitForExistence(timeout: timeout), row.isHittable {
            row.tap()
        }
        if tile.waitForExistence(timeout: 8), tile.value as? String != "已选择", tile.isHittable {
            tile.tap()
        }
        return tile
    }

    /// B4b home main card: "换球场或组合" (a known course) or the search card both open 开始一场
    /// without a preselected course; the main card's "开始" would preselect it.
    @discardableResult
    private func openStartRound() -> Bool {
        let change = app.buttons["home-change-course"]
        if change.waitForExistence(timeout: 4), change.isHittable {
            change.tap()
            return true
        }
        let entry = app.buttons["home-new-round"]
        if entry.waitForExistence(timeout: 4), entry.isHittable {
            entry.tap()
            return true
        }
        return tapContaining(["换球场或组合", "今天去哪打"])
    }

    /// Keep the no-GPS interaction journey isolated from the next UI test. This follows the same
    /// user-visible end-menu path as production; `UITEST_DISABLE_EVENT_SYNC` makes the final discard
    /// local-only and therefore cannot write a synthetic round to the owner's backend.
    private func discardActiveRoundForEvidence() {
        guard app.state == .runningForeground else { return }
        let greenClose = app.buttons["关闭果岭地图"]
        if greenClose.exists, greenClose.isHittable { greenClose.tap() }
        let mapClose = app.buttons["关闭详细地图"]
        if mapClose.exists, mapClose.isHittable { mapClose.tap() }
        // B1: 结束本场 lives on the scorecard, opened by the live screen's top-left 返回.
        let scorecard = app.buttons["计分卡"]
        if scorecard.waitForExistence(timeout: 5), scorecard.isHittable { scorecard.tap() }
        let endMenu = app.buttons["live-round-end-menu"]
        guard endMenu.waitForExistence(timeout: 8), endMenu.isHittable else { return }
        endMenu.tap()
        let discard = app.buttons["live-finish-discard"]
        guard discard.waitForExistence(timeout: 8), discard.isHittable else { return }
        discard.tap()
        let confirm = app.buttons["放弃并删除本场记录"]
        if confirm.waitForExistence(timeout: 5), confirm.isHittable { confirm.tap() }
        _ = app.buttons["home-new-round"].waitForExistence(timeout: 10)
    }

    /// Tap the first button/cell/text whose label CONTAINS any of the given fragments.
    @discardableResult
    private func tapContaining(_ fragments: [String]) -> Bool {
        for fragment in fragments {
            let predicate = NSPredicate(format: "label CONTAINS %@", fragment)
            for query in [app.buttons, app.cells, app.staticTexts, app.otherElements] {
                let match = query.matching(predicate).firstMatch
                if match.waitForExistence(timeout: 4), match.isHittable { match.tap(); return true }
            }
        }
        return false
    }

    // MARK: - diagnostics

    /// Probe GET /courses/{gid}/tees so a "no tee options" result is diagnosable as
    /// funnel-unreachable / bad-token / geometry-absent (token length only — never the token itself).
    private func writeDiagnostics() {
        let url = cfg("AI_CADDIE_API_BASE_URL") ?? ""
        let token = cfg("AI_CADDIE_ADMIN_TOKEN") ?? ""
        var lines = ["resolvedURL=\(url)", "tokenLen=\(token.count)"]
        // 北京丽宫 (gid 31793) — the real course selected by the injected blue-tee fix.
        if let probeURL = URL(string: url + "/api/v2/courses/31793/tees") {
            var request = URLRequest(url: probeURL)
            request.timeoutInterval = 40
            request.setValue(token, forHTTPHeaderField: "x-ai-caddie-admin-token")
            let semaphore = DispatchSemaphore(value: 0)
            URLSession.shared.dataTask(with: request) { data, response, error in
                let code = (response as? HTTPURLResponse)?.statusCode ?? -1
                lines.append("tees.status=\(code)")
                if let error { lines.append("tees.error=\(error.localizedDescription)") }
                if let data, let body = String(data: data, encoding: .utf8) {
                    lines.append("tees.body=\(String(body.prefix(400)))")
                }
                semaphore.signal()
            }.resume()
            _ = semaphore.wait(timeout: .now() + 45)
        } else {
            lines.append("tees.skipped=invalid-url")
        }
        try? lines.joined(separator: "\n").data(using: .utf8)?
            .write(to: realShotsDir().appendingPathComponent("tees-diagnostics.txt"))
    }

    // MARK: - capture helpers

    private func realShotsDir() -> URL {
        let base = (try? FileManager.default.url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true))
            ?? FileManager.default.temporaryDirectory
        let dir = base.appendingPathComponent("real-screenshots", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func save(_ name: String) {
        let shot = XCUIScreen.main.screenshot()
        try? shot.pngRepresentation.write(to: realShotsDir().appendingPathComponent("\(name).png"))
        let attachment = XCTAttachment(screenshot: shot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
        print("WROTE_REAL_SCREENSHOT \(name)")
    }

    private func dump(_ name: String) {
        try? app.debugDescription.data(using: .utf8)?
            .write(to: realShotsDir().appendingPathComponent("tree-\(name).txt"))
    }
}
