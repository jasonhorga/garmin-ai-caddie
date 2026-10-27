import XCTest
import AICaddieDomain
@testable import AICaddie

final class StartRoundDiscoveryTests: XCTestCase {
    func testOpeningPageIsCourseUnlessACourseIsPassed() {
        XCTAssertEqual(StartRoundView.openingPage(initialPage: nil, defaultCourseGlobalId: nil), .course)
        XCTAssertEqual(StartRoundView.openingPage(initialPage: nil, defaultCourseGlobalId: 31795), .setup)
        XCTAssertEqual(StartRoundView.openingPage(initialPage: .course, defaultCourseGlobalId: 31795), .course)
        XCTAssertEqual(StartRoundView.openingPage(initialPage: .setup, defaultCourseGlobalId: nil), .setup)
    }

    func testPreselectedLoopPrefersCurrentThenRecentThenFirst() {
        let loops = [blackKnight(31794, "A"), blackKnight(31795, "B"), blackKnight(31796, "C")]
        XCTAssertEqual(StartRoundPresentation.preselectedLoop(in: loops, current: loops[2], recent: loops[1])?.globalId, 31796)
        XCTAssertEqual(StartRoundPresentation.preselectedLoop(in: loops, current: nil, recent: loops[1])?.globalId, 31795)
        let otherVenue = MobileCourseOption(globalId: 400, name: "另一球场 ~ A", holes: 9, venueName: "另一球场", segmentLabel: "A", segmentHoles: 9)
        XCTAssertEqual(StartRoundPresentation.preselectedLoop(in: loops, current: otherVenue, recent: loops[1])?.globalId, 31795)
        XCTAssertEqual(StartRoundPresentation.preselectedLoop(in: loops, current: otherVenue, recent: nil)?.globalId, 31794)
        XCTAssertNil(StartRoundPresentation.preselectedLoop(in: [], current: nil, recent: otherVenue))
    }

    func testThreeNineHoleVenueStartsOnlyTheSelectedLoop() {
        let loops = [blackKnight(31794, "A"), blackKnight(31795, "B"), blackKnight(31796, "C")]
        let entries = StartRoundPresentation.combinedLoopEntries(selected: loops[1])
        XCTAssertEqual(entries, [RoundLoopEntry(globalId: 31795, half: "all")])
    }

    func testPreselectedTeePrefersLastUsedThenCourseDefault() {
        XCTAssertEqual(StartRoundPresentation.preselectedTee(lastUsed: "white", offered: ["Gold", "Blue", "White"], defaultTee: "blue"), "White")
        XCTAssertEqual(StartRoundPresentation.preselectedTee(lastUsed: "red", offered: ["Gold", "Blue", "White"], defaultTee: "blue"), "Blue")
        XCTAssertEqual(StartRoundPresentation.preselectedTee(lastUsed: nil, offered: ["Gold", "Blue", "White"], defaultTee: "gold"), "Gold")
        XCTAssertEqual(StartRoundPresentation.preselectedTee(lastUsed: "unknown", offered: ["Gold", "Blue", "White"], defaultTee: "gold"), "Gold")
        XCTAssertEqual(StartRoundPresentation.preselectedTee(lastUsed: nil, offered: ["Gold", "Blue", "White"], defaultTee: "silver"), "Blue")
        XCTAssertEqual(StartRoundPresentation.preselectedTee(lastUsed: "  ", offered: ["Gold", "Blue", "White"], defaultTee: nil), "Blue")
        XCTAssertEqual(StartRoundPresentation.preselectedTee(lastUsed: nil, offered: ["Gold", "Red"], defaultTee: nil), "Gold")
        XCTAssertEqual(StartRoundPresentation.preselectedTee(lastUsed: "white", offered: [], defaultTee: "blue"), "white")
        XCTAssertEqual(StartRoundPresentation.preselectedTee(lastUsed: nil, offered: [], defaultTee: "blue"), "blue")
        XCTAssertEqual(StartRoundPresentation.preselectedTee(lastUsed: nil, offered: [], defaultTee: nil), "")
        XCTAssertEqual(StartRoundPresentation.preselectedTee(lastUsed: " white ", offered: ["Gold", " White "], defaultTee: "gold"), " White ")
        XCTAssertEqual(StartRoundPresentation.preselectedTee(lastUsed: nil, offered: ["Gold", " Blue "], defaultTee: nil), " Blue ")
    }

    func testReturningToSameCourseKeepsWhiteTeeAuthorityAndRoundIdentity() {
        let course = MobileCourseOption(globalId: 401, name: "测试球场", teeBox: "Blue", tees: ["Blue", "White"])
        let rows = [CourseTee(teeBox: "Blue", name: "Blue", isDefault: true), CourseTee(teeBox: "White", name: "White")]
        // An explicit White pick survives 返回 → the same venue row.
        let before = courseRowState(globalId: 401, tee: "White", rows: rows)
        let after = StartRoundPresentation.selectingCourseRow(course, current: course, state: before, lastUsedTee: nil)

        XCTAssertEqual(after.selection.teeBox, "White")
        XCTAssertTrue(after.userPickedTee)
        XCTAssertEqual(after.selection.roundId, "live-existing")
        XCTAssertEqual(after.fetchedTees, rows)
        XCTAssertEqual(courseRowTeeOptions(after, course: course), ["Blue", "White"])
        XCTAssertEqual(after, before)
    }

    func testReturningToSearchedCourseKeepsFetchedTeesAndCanStart() {
        // A name-search result carries no bundled tee names; /tees is its only colour authority.
        let searched = MobileCourseOption(globalId: 90_001, name: "搜索球场")
        let rows = [CourseTee(teeBox: "Blue", name: "Blue", isDefault: true), CourseTee(teeBox: "White", name: "White")]
        let before = courseRowState(globalId: 90_001, tee: "White", rows: rows)
        let after = StartRoundPresentation.selectingCourseRow(searched, current: searched, state: before, lastUsedTee: nil)
        let options = courseRowTeeOptions(after, course: searched, requiresRemoteTees: true, wasManualSearch: true)

        XCTAssertEqual(after.selection.teeBox, "White")
        XCTAssertEqual(after.fetchedTees, rows)
        XCTAssertEqual(options, ["Blue", "White"])
        XCTAssertTrue(StartRoundView.isStartAllowed(
            isPreparing: false, isLoadingTees: false,
            roundId: after.selection.roundId, courseGlobalId: Int(after.selection.globalIdText),
            teeBox: after.selection.teeBox, selectedCourseRequiresRemoteTees: true,
            teeOptions: options, selectedCourseWasManualSearch: true
        ))
    }

    func testReturningToVenueKeepsChosenLoopEvenWhenRowComesFromAnotherSource() {
        let first = blackKnight(31794, "A")
        let chosen = blackKnight(31795, "B")
        let before = courseRowState(globalId: 31795, tee: "White", rows: [CourseTee(teeBox: "White", name: "White")])
        // A refreshed course-row authority may offer only A; reopening the venue must keep B.
        let after = StartRoundPresentation.selectingCourseRow(first, current: chosen, state: before, lastUsedTee: "Blue")
        XCTAssertEqual(after.selection.globalIdText, "31795")
        XCTAssertEqual(after, before)
    }

    func testReturningToSameGlobalIdKeepsStateDespiteChangedVenueMetadata() {
        let previous = MobileCourseOption(globalId: 401, name: "旧名称")
        let refreshed = MobileCourseOption(globalId: 401, name: "新名称")
        let before = courseRowState(globalId: 401, tee: "White", rows: [])
        XCTAssertEqual(StartRoundPresentation.selectingCourseRow(refreshed, current: previous, state: before, lastUsedTee: nil), before)
        XCTAssertEqual(StartRoundPresentation.selectingCourseRow(refreshed, current: nil, state: before, lastUsedTee: nil), before)
    }

    func testReturningToSameCoursePreservesFailedTeeRetry() {
        let course = MobileCourseOption(globalId: 90_001, name: "搜索球场")
        let before = courseRowState(globalId: 90_001, tee: "unknown", rows: [], teeLoadFailed: true)
        let after = StartRoundPresentation.selectingCourseRow(course, current: course, state: before, lastUsedTee: nil)
        XCTAssertTrue(after.teeLoadFailed, "the existing retry must remain reachable when no new Tee task is triggered")
        XCTAssertEqual(after, before)
    }

    func testDifferentVenueResetsSetupUsingItsOwnLastUsedTeeOrDefault() {
        let previous = blackKnight(31795, "B")
        let next = MobileCourseOption(globalId: 501, name: "另一球场", teeBox: "Gold", tees: ["Gold", "Blue"])
        let before = courseRowState(globalId: 31795, tee: "White", rows: [CourseTee(teeBox: "White", name: "White")], teeLoadFailed: true)
        let uuid = UUID(uuidString: "00000000-0000-0000-0000-000000000001")!
        let after = StartRoundPresentation.selectingCourseRow(next, current: previous, state: before, lastUsedTee: nil, uuid: uuid)
        XCTAssertEqual(after.selection.globalIdText, "501")
        XCTAssertEqual(after.selection.roundId, "live-501-00000000-0000-0000-0000-000000000001")
        XCTAssertEqual(after.selection.teeBox, "Gold")
        XCTAssertFalse(after.userPickedTee)
        XCTAssertTrue(after.fetchedTees.isEmpty)
        XCTAssertFalse(after.teeLoadFailed)
        XCTAssertEqual(StartRoundPresentation.selectingCourseRow(next, current: previous, state: before, lastUsedTee: "Blue").selection.teeBox, "Blue")
    }

    private func courseRowState(
        globalId: Int, tee: String, rows: [CourseTee], teeLoadFailed: Bool = false
    ) -> StartRoundPresentation.CourseRowState {
        .init(
            selection: .init(globalIdText: String(globalId), roundId: "live-existing", teeBox: tee),
            userPickedTee: true, fetchedTees: rows, teeLoadFailed: teeLoadFailed
        )
    }

    private func courseRowTeeOptions(
        _ state: StartRoundPresentation.CourseRowState, course: MobileCourseOption,
        requiresRemoteTees: Bool = false, wasManualSearch: Bool = false
    ) -> [String] {
        StartRoundView.resolvedTeeOptions(
            fetchedTees: state.fetchedTees, courseTees: course.tees ?? [], teeBox: state.selection.teeBox,
            requiresRemoteTees: requiresRemoteTees, wasManualSearch: wasManualSearch
        )
    }

    func testLastUsedTeeIsTheRecentThenTheCallerTeeAtThisVenue() {
        XCTAssertEqual(StartRoundPresentation.lastUsedTee(selectedVenue: "黑骑士", recentVenue: "黑骑士", recentTee: "white", callerVenue: "黑骑士", callerTee: "blue"), "white")
        XCTAssertEqual(StartRoundPresentation.lastUsedTee(selectedVenue: "黑骑士", recentVenue: "北湖", recentTee: "white", callerVenue: "黑骑士", callerTee: "blue"), "blue")
        XCTAssertEqual(StartRoundPresentation.lastUsedTee(selectedVenue: "黑骑士", recentVenue: "黑骑士", recentTee: "unknown", callerVenue: "黑骑士", callerTee: "blue"), "blue")
        XCTAssertNil(StartRoundPresentation.lastUsedTee(selectedVenue: "黑骑士", recentVenue: "北湖", recentTee: "white", callerVenue: nil, callerTee: nil))
        XCTAssertEqual(StartRoundPresentation.lastUsedTee(selectedVenue: "黑骑士", recentVenue: " 黑骑士 ", recentTee: " Red ", callerVenue: nil, callerTee: nil), "Red")
        XCTAssertNil(StartRoundPresentation.lastUsedTee(selectedVenue: "黑骑士", recentVenue: nil, recentTee: nil, callerVenue: "黑骑士", callerTee: "unknown"))
        XCTAssertNil(StartRoundPresentation.lastUsedTee(selectedVenue: "", recentVenue: "", recentTee: "white", callerVenue: nil, callerTee: nil))
        XCTAssertEqual(StartRoundPresentation.lastUsedTee(selectedVenue: " Test Course ", recentVenue: "test course", recentTee: "White", callerVenue: nil, callerTee: nil), "White")
    }

    func testTeeAfterRefreshPrefersTheDefaultRowOverTheGuess() {
        let goldDefault = [
            CourseTee(teeBox: "gold", name: "Gold", isDefault: true),
            CourseTee(teeBox: "blue", name: "Blue"),
            CourseTee(teeBox: "white", name: "White"),
        ]
        let noDefault = [
            CourseTee(teeBox: "gold", name: "Gold"),
            CourseTee(teeBox: "blue", name: "Blue"),
            CourseTee(teeBox: "white", name: "White"),
        ]
        XCTAssertEqual(StartRoundView.teeAfterRefresh(current: "blue", userPicked: false, lastUsed: nil, rows: goldDefault), "gold")
        XCTAssertEqual(StartRoundView.teeAfterRefresh(current: "white", userPicked: true, lastUsed: nil, rows: goldDefault), "white")
        XCTAssertEqual(StartRoundView.teeAfterRefresh(current: "red", userPicked: true, lastUsed: nil, rows: goldDefault), "gold")
        XCTAssertEqual(StartRoundView.teeAfterRefresh(current: "blue", userPicked: false, lastUsed: "White", rows: goldDefault), "white")
        XCTAssertEqual(StartRoundView.teeAfterRefresh(current: "", userPicked: false, lastUsed: "red", rows: goldDefault), "gold")
        XCTAssertEqual(StartRoundView.teeAfterRefresh(current: "gold", userPicked: false, lastUsed: nil, rows: noDefault), "blue")
        XCTAssertEqual(StartRoundView.teeAfterRefresh(current: " WHITE ", userPicked: true, lastUsed: nil, rows: goldDefault), "white")
    }

    func testEveryExplicitCourseStartUsesANewRoundIdentity() {
        let first = StartRoundView.freshLiveRoundId(
            globalId: 31793,
            uuid: UUID(uuidString: "00000000-0000-0000-0000-000000000001")!
        )
        let second = StartRoundView.freshLiveRoundId(
            globalId: 31793,
            uuid: UUID(uuidString: "00000000-0000-0000-0000-000000000002")!
        )

        XCTAssertEqual(first, "live-31793-00000000-0000-0000-0000-000000000001")
        XCTAssertNotEqual(first, second)
        XCTAssertNotEqual(first, "live-31793")
    }

    func testStartRoundSurfacesOnlyActionablePreparationFailures() {
        XCTAssertEqual(
            StartRoundView.roundPreparationFailureMessage(from: "暂时无法开始,稍后重试"),
            "暂时无法开始,稍后重试"
        )
        XCTAssertEqual(
            StartRoundView.roundPreparationFailureMessage(from: "离线中,使用已保存数据"),
            "离线中,使用已保存数据"
        )
        XCTAssertNil(StartRoundView.roundPreparationFailureMessage(from: "主页就绪"))
        XCTAssertNil(StartRoundView.roundPreparationFailureMessage(from: "离线地图已准备"))
    }

    func testOfflineNearbyFallbackIncludesOnlyCoordinateProvenDownloadedCourses() {
        let near = option(
            globalId: 1,
            name: "Near course",
            latitude: 40.0456,
            longitude: 116.5462,
            roundCount: 1
        )
        let farHistory = option(
            globalId: 2,
            name: "Far historical course",
            latitude: 22.7401,
            longitude: 114.0714,
            roundCount: 99
        )
        let unknownHistory = option(
            globalId: 3,
            name: "History without coordinates",
            latitude: nil,
            longitude: nil,
            roundCount: 120
        )

        let nearby = StartRoundView.locallyAvailableNearbyCourses(
            [farHistory, unknownHistory, near],
            latitude: 40.0454995,
            longitude: 116.5461531,
            radiusKm: 50
        )

        XCTAssertEqual(nearby.map(\.globalId), [1])
        XCTAssertEqual(nearby.first?.name, "Near course")
    }

    func testOfflineNearbyFallbackDeduplicatesGlobalIdsAndRejectsInvalidPlayerFix() {
        let first = option(
            globalId: 7,
            name: "A loop",
            latitude: 40.0456,
            longitude: 116.5462,
            roundCount: 3
        )
        let duplicate = option(
            globalId: 7,
            name: "Duplicate stale row",
            latitude: 40.0457,
            longitude: 116.5463,
            roundCount: 30
        )

        XCTAssertEqual(
            StartRoundView.locallyAvailableNearbyCourses(
                [first, duplicate],
                latitude: 40.0454995,
                longitude: 116.5461531,
                radiusKm: 50
            ).map(\.name),
            ["A loop"]
        )
        XCTAssertTrue(
            StartRoundView.locallyAvailableNearbyCourses(
                [first],
                latitude: 91,
                longitude: 116.5461531,
                radiusKm: 50
            ).isEmpty
        )
    }

    func testOfflineServiceFailureCanRetainVerifiedPackageWithoutTeeCoordinates() {
        let downloaded = option(
            globalId: 31793,
            name: "北京丽宫体育公园高尔夫俱乐部",
            latitude: nil,
            longitude: nil,
            roundCount: 0
        )
        let far = option(
            globalId: 3881,
            name: "Cypress Point Club",
            latitude: 36.58,
            longitude: -121.97,
            roundCount: 0
        )

        let fallback = StartRoundView.locallyAvailableNearbyCourses(
            [far, downloaded],
            latitude: 40.0454995,
            longitude: 116.5461531,
            radiusKm: 50,
            includeUnknownCoordinates: true
        )

        XCTAssertEqual(fallback.map(\.globalId), [31793])
    }

    func testSuccessfulNearbyResponseCanExposeTheExplicitRecentCourseWhenItOmitsIt() {
        let recent = option(
            globalId: 31793,
            name: "北京丽宫体育公园高尔夫俱乐部",
            latitude: 40.0456,
            longitude: 116.5462,
            roundCount: 1
        )
        let nearby = option(
            globalId: 31870,
            name: "附近另一个球场",
            latitude: 40.06,
            longitude: 116.55,
            roundCount: 0
        )

        let fallback = StartRoundView.recentCourseFallback(
            recent: recent,
            provider: [nearby]
        )

        XCTAssertEqual(fallback?.globalId, 31793)
        XCTAssertEqual(fallback?.name, "北京丽宫体育公园高尔夫俱乐部")
    }

    func testRecentCourseIsNotDuplicatedWhenNearbyContainsTheSameGarminGlobalId() {
        let recent = option(
            globalId: 31793,
            name: "北京丽宫体育公园高尔夫俱乐部",
            latitude: 40.0456,
            longitude: 116.5462,
            roundCount: 1
        )

        XCTAssertNil(
            StartRoundView.recentCourseFallback(
                recent: recent,
                provider: [recent]
            )
        )
    }

    func testNearbyDiscoveryDoesNotRestartForNormalWalkingGPSUpdates() {
        let initial = StartRoundView.nearbyDiscoveryBucket(
            latitude: 40.0454995,
            longitude: 116.5461531
        )
        let afterWalking = StartRoundView.nearbyDiscoveryBucket(
            latitude: 40.0458995,
            longitude: 116.5465531
        )
        let afterMeaningfulTravel = StartRoundView.nearbyDiscoveryBucket(
            latitude: 40.0654995,
            longitude: 116.5661531
        )

        XCTAssertEqual(initial, afterWalking)
        XCTAssertNotEqual(initial, afterMeaningfulTravel)
    }

    func testNearbyDiscoveryAppliesOnlyTheCurrentUncancelledGeneration() {
        let current = UUID()
        let superseded = UUID()

        XCTAssertTrue(
            StartRoundView.shouldApplyNearbyDiscoveryResult(
                isCancelled: false,
                requestToken: current,
                activeRequestToken: current,
                requestKey: "4004:11654",
                currentRequestKey: "4004:11654"
            )
        )
        XCTAssertFalse(
            StartRoundView.shouldApplyNearbyDiscoveryResult(
                isCancelled: true,
                requestToken: current,
                activeRequestToken: current,
                requestKey: "4004:11654",
                currentRequestKey: "4004:11654"
            )
        )
        XCTAssertFalse(
            StartRoundView.shouldApplyNearbyDiscoveryResult(
                isCancelled: false,
                requestToken: superseded,
                activeRequestToken: current,
                requestKey: "4004:11654",
                currentRequestKey: "4004:11654"
            )
        )
        XCTAssertFalse(
            StartRoundView.shouldApplyNearbyDiscoveryResult(
                isCancelled: false,
                requestToken: current,
                activeRequestToken: current,
                requestKey: "4004:11654",
                currentRequestKey: "4006:11656"
            )
        )
    }

    func testSelectingASearchResultRetainsOnlyItsSiblingLoops() {
        let selected = MobileCourseOption(
            globalId: 31670,
            name: "Shenzhen Mission Hills Golf Club ~ Faldo",
            holes: 9,
            venueName: "Shenzhen Mission Hills Golf Club",
            segmentLabel: "Faldo",
            segmentHoles: 9
        )
        let sibling = MobileCourseOption(
            globalId: 31671,
            name: "Shenzhen Mission Hills Golf Club ~ Ozaki",
            holes: 9,
            venueName: "Shenzhen Mission Hills Golf Club",
            segmentLabel: "Ozaki",
            segmentHoles: 9
        )
        let unrelated = MobileCourseOption(
            globalId: 31874,
            name: "Haikou Mission Hills Golf Club ~ Blackstone",
            holes: 18,
            venueName: "Haikou Mission Hills Golf Club"
        )

        XCTAssertEqual(
            StartRoundView.sameVenueSearchOptions(
                selected: selected,
                candidates: [unrelated, sibling, selected]
            ).map(\.globalId),
            [31670, 31671]
        )
    }

    func testStableCourseDisplayNameRebuildsSingleLoopWithoutStaleCombination() {
        let selected = MobileCourseOption(
            globalId: 31_794,
            name: "北京天竺黑骑士球员俱乐部 ~ C/A",
            holes: 9,
            venueName: "北京天竺黑骑士球员俱乐部",
            segmentLabel: "C",
            segmentHoles: 9
        )

        XCTAssertEqual(
            StartRoundView.roundDisplayName(front: selected, back: nil),
            "北京天竺黑骑士球员俱乐部"
        )
        XCTAssertEqual(
            StartRoundView.courseVenueName(selected),
            "北京天竺黑骑士球员俱乐部"
        )
    }

    func testManualSearchProvenanceSurvivesSiblingLoopButNotAnotherVenue() {
        let searchedLoop = MobileCourseOption(
            globalId: 31670,
            name: "Shenzhen Mission Hills Golf Club ~ Faldo",
            holes: 9,
            venueName: "Shenzhen Mission Hills Golf Club",
            segmentLabel: "Faldo",
            segmentHoles: 9
        )
        let siblingLoop = MobileCourseOption(
            globalId: 31671,
            name: "Shenzhen Mission Hills Golf Club ~ Ozaki",
            holes: 9,
            venueName: "Shenzhen Mission Hills Golf Club",
            segmentLabel: "Ozaki",
            segmentHoles: 9
        )
        let otherVenue = MobileCourseOption(
            globalId: 31874,
            name: "Haikou Mission Hills Golf Club ~ Blackstone",
            holes: 18,
            venueName: "Haikou Mission Hills Golf Club"
        )

        XCTAssertTrue(
            StartRoundView.preservesManualSearchProvenance(
                wasManualSearch: true,
                previous: searchedLoop,
                next: siblingLoop
            )
        )
        XCTAssertFalse(
            StartRoundView.preservesManualSearchProvenance(
                wasManualSearch: true,
                previous: searchedLoop,
                next: otherVenue
            )
        )
        XCTAssertFalse(
            StartRoundView.preservesManualSearchProvenance(
                wasManualSearch: false,
                previous: searchedLoop,
                next: siblingLoop
            )
        )
    }

    /// Formerly `testManualSearchCanStartWhileTeeAuthorityIsStillLoading`; since C87 the course
    /// default starts any course while `/tees` loads, not only a manually searched one.
    func testCourseDefaultOrManualSearchCanStartWhileTeeAuthorityIsStillLoading() {
        let common: (String, Bool) -> Bool = { teeBox, manualSearch in
            StartRoundView.isStartAllowed(
                isPreparing: false,
                isLoadingTees: true,
                roundId: "live-31670-test",
                courseGlobalId: 31670,
                teeBox: teeBox,
                selectedCourseRequiresRemoteTees: true,
                teeOptions: [],
                selectedCourseWasManualSearch: manualSearch
            )
        }

        XCTAssertTrue(common("unknown", true))
        XCTAssertTrue(common("blue", true))
        // C87: the course default needs no Tee list, so a nearby course starts on it as well.
        XCTAssertTrue(common("unknown", false))
        // A concrete colour on a nearby course still waits for the Tee list that names it.
        XCTAssertFalse(common("blue", false))
    }

    func testNearbyRowCarryingTeesShowsThemAtOnceWithoutATeesRequest() throws {
        // C87 (build 96, 沙河): a nearby row whose CourseView release the server already caches
        // carries the GET /tees answer. Selecting it lists those Tee rows and enables Start at once;
        // no /tees request is sent or awaited.
        let payload = Data("""
        {"schema":"ai-caddie-course-nearby-v1","radiusKm":50,"matches":[
          {"globalId":31794,"name":"测试球场 ~ A","holes":9,"ratio":0,"distanceKm":0.4,
           "teeOptions":{"schema":"ai-caddie-course-tees-v1","globalId":31794,"defaultTeeBox":"blue","tees":[
             {"teeBox":"black","name":"Black","set":1,"yards":3400,"holeCount":9,"default":false},
             {"teeBox":"blue","name":"Blue","set":2,"yards":3200,"holeCount":9,"default":true}]}},
          {"globalId":31795,"name":"测试球场 ~ B","holes":9,"ratio":0,"distanceKm":0.5}]}
        """.utf8)
        let response = try JSONDecoder().decode(MobileNearbyCoursesResponse.self, from: payload)
        let option = try XCTUnwrap(response.matches.first?.courseOption)
        let selection = StartRoundView.selectionState(for: option, lastUsedTee: nil)
        XCTAssertEqual(selection.teeBox, "blue", "the carried course default is preselected")
        let options = StartRoundView.resolvedTeeOptions(
            fetchedTees: [], courseTees: option.tees ?? [], teeBox: selection.teeBox,
            requiresRemoteTees: true, wasManualSearch: false
        )
        XCTAssertEqual(options, ["black", "blue"])
        XCTAssertTrue(StartRoundView.isStartAllowed(
            isPreparing: false, isLoadingTees: false,
            roundId: selection.roundId, courseGlobalId: 31794, teeBox: selection.teeBox,
            selectedCourseRequiresRemoteTees: true, teeOptions: options, selectedCourseWasManualSearch: false
        ))

        let carried = StartRoundPresentation.carriedTees(in: response.matches)
        let rows = try XCTUnwrap(carried[31794])
        XCTAssertEqual(rows.map(\.yards), [3400, 3200], "the yard row comes with the carried Tee rows")
        XCTAssertNil(carried[31795])
    }

    private final class RequestPaths: @unchecked Sendable {
        private let lock = NSLock()
        private var paths: [String] = []
        func append(_ path: String) { lock.withLock { paths.append(path) } }
        var tees: [String] { lock.withLock { paths.filter { $0.hasSuffix("/tees") } } }
    }

    @MainActor
    func testSelectingANearbyRowThatCarriesTeesSendsNoTeesRequest() async throws {
        // C87 rework: nearby → select → StartRoundView's Tee-load step over a stubbed server,
        // counting GET /tees on the wire.
        let nearbyPayload = Data("""
        {"schema":"ai-caddie-course-nearby-v1","radiusKm":50,"matches":[
          {"globalId":31794,"name":"测试球场 ~ A","holes":9,"ratio":0,"distanceKm":0.4,
           "teeOptions":{"schema":"ai-caddie-course-tees-v1","globalId":31794,"defaultTeeBox":"blue","tees":[
             {"teeBox":"black","name":"Black","set":1,"yards":3400,"holeCount":9,"default":false},
             {"teeBox":"blue","name":"Blue","set":2,"yards":3200,"holeCount":9,"default":true}]}},
          {"globalId":31795,"name":"测试球场 ~ B","holes":9,"ratio":0,"distanceKm":0.5}]}
        """.utf8)
        let teesPayload = Data("""
        {"schema":"ai-caddie-course-tees-v1","globalId":31795,"defaultTeeBox":"white","tees":[
          {"teeBox":"white","name":"White","set":1,"yards":3000,"holeCount":9,"default":true}]}
        """.utf8)
        let paths = RequestPaths()
        CapturingURLProtocol.requestHandler = { request in
            let url = try XCTUnwrap(request.url)
            paths.append(url.path)
            let body: Data
            switch url.path {
            case "/api/v2/courses/nearby": body = nearbyPayload
            case "/api/v2/courses/31795/tees": body = teesPayload
            default:
                return (HTTPURLResponse(url: url, statusCode: 404, httpVersion: nil, headerFields: nil)!, Data())
            }
            return (
                HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!,
                body
            )
        }
        defer { CapturingURLProtocol.requestHandler = nil }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingURLProtocol.self]
        // The SyncClient calls behind LiveRoundAppModel.nearbyCourses / loadCourseTees. The model
        // itself is not used: its new-area pass may ask /tees in the background on its own.
        let client = SyncClient(
            baseURL: URL(string: "https://start-round-tees.example.test")!,
            session: URLSession(configuration: configuration),
            retrySleep: { _ in }
        )

        let matches = try await client.nearbyCourses(latitude: 40.0, longitude: 116.5, radiusKm: 50)
        let carried = StartRoundPresentation.carriedTees(in: matches)
        let request: (Int) async -> [CourseTee]? = { globalId in
            let tees = (try? await client.fetchCourseTees(globalId: globalId))?.tees ?? []
            return tees.isEmpty ? nil : tees
        }

        let carriedRows = await StartRoundView.courseTeeRows(globalId: 31794, carried: carried, request: request)
        XCTAssertEqual(carriedRows?.map(\.teeBox), ["black", "blue"])
        XCTAssertEqual(carriedRows?.map(\.yards), [3400, 3200])
        XCTAssertEqual(paths.tees, [], "a row carrying Tee rows must not ask /tees")

        let fetchedRows = await StartRoundView.courseTeeRows(globalId: 31795, carried: carried, request: request)
        XCTAssertEqual(fetchedRows?.map(\.teeBox), ["white"])
        XCTAssertEqual(paths.tees, ["/api/v2/courses/31795/tees"], "a row without them asks /tees once")
    }

    @MainActor
    func testRemoteTeeLookupKeepsConcreteColourStartGatedAcrossItsAwait() async {
        var loading = true
        let rows = await StartRoundView.courseTeeRows(
            globalId: 31795, carried: [:], setLoading: { loading = $0 },
            request: { _ in
                XCTAssertTrue(loading, "no frame may release the gate before the remote request")
                await Task.yield()
                XCTAssertTrue(loading, "the gate remains raised while the request is suspended")
                XCTAssertFalse(StartRoundView.isStartAllowed(
                    isPreparing: false, isLoadingTees: loading, roundId: "fixture-round",
                    courseGlobalId: 31795, teeBox: "blue", selectedCourseRequiresRemoteTees: false,
                    teeOptions: ["blue"], selectedCourseWasManualSearch: false
                ))
                return [CourseTee(teeBox: "blue", name: "Blue")]
            }
        )
        XCTAssertEqual(rows?.map(\.teeBox), ["blue"])
        XCTAssertFalse(loading)

        loading = true
        let failed = await StartRoundView.courseTeeRows(
            globalId: 31795, carried: [31795: []], setLoading: { loading = $0 },
            request: { _ in XCTAssertTrue(loading); return nil }
        )
        XCTAssertNil(failed)
        XCTAssertFalse(loading, "a finished failed request releases the gate too")

        loading = true
        let carried = await StartRoundView.courseTeeRows(
            globalId: 31795, carried: [31795: [CourseTee(teeBox: "white", name: "White")]],
            setLoading: { loading = $0 }, request: { _ in XCTFail("carried rows need no request"); return nil }
        )
        XCTAssertEqual(carried?.map(\.teeBox), ["white"])
        XCTAssertFalse(loading, "carried rows release the gate without a network await")
    }

    func testFailedTeeRequestStillOffersRetryNextToTheCourseDefault() throws {
        // C87 rework: a nearby course now starts on `unknown`, so its Tee list is ["unknown"], never
        // empty. A failed /tees must still show 重试获取发球台 while 球场默认 T remains startable.
        let match = MobileCourseSearchMatch(
            globalId: 31795, name: "测试球场 ~ B", holes: 9, city: nil, province: nil, ratio: 0
        )
        let option = try XCTUnwrap(match.courseOption)
        let selection = StartRoundView.selectionState(for: option, lastUsedTee: nil)
        let courseTees = option.tees ?? []
        let options = StartRoundView.resolvedTeeOptions(
            fetchedTees: [], courseTees: courseTees, teeBox: selection.teeBox,
            requiresRemoteTees: true, wasManualSearch: false
        )
        XCTAssertEqual(options, ["unknown"])
        XCTAssertTrue(StartRoundView.showsTeeRetry(
            requiresRemoteTees: true, teeLoadFailed: true, fetchedTees: [], courseTees: courseTees
        ))
        XCTAssertTrue(StartRoundView.isStartAllowed(
            isPreparing: false, isLoadingTees: false,
            roundId: selection.roundId, courseGlobalId: 31795, teeBox: selection.teeBox,
            selectedCourseRequiresRemoteTees: true, teeOptions: options, selectedCourseWasManualSearch: false
        ))

        // No retry before a failure, or once real Tee rows exist (fetched, or carried by the row).
        XCTAssertFalse(StartRoundView.showsTeeRetry(
            requiresRemoteTees: true, teeLoadFailed: false, fetchedTees: [], courseTees: courseTees
        ))
        let rows = [CourseTee(teeBox: "blue", name: "Blue", isDefault: true)]
        XCTAssertFalse(StartRoundView.showsTeeRetry(
            requiresRemoteTees: true, teeLoadFailed: true, fetchedTees: rows, courseTees: courseTees
        ))
        XCTAssertFalse(StartRoundView.showsTeeRetry(
            requiresRemoteTees: true, teeLoadFailed: true, fetchedTees: [], courseTees: ["blue"]
        ))
    }

    func testNearbyCourseWithoutTeesYetStartsOnTheCourseDefault() throws {
        // C87: with no carried Tee rows the picker shows 球场默认 T at once and Start is usable while
        // /tees is still loading; such a round starts on the server's course default (`unknown`).
        // The real list replaces it when it arrives, so the player can still change Tee first.
        let match = MobileCourseSearchMatch(
            globalId: 31795, name: "测试球场 ~ B", holes: 9, city: nil, province: nil, ratio: 0
        )
        let option = try XCTUnwrap(match.courseOption)
        let selection = StartRoundView.selectionState(for: option, lastUsedTee: nil)
        XCTAssertEqual(selection.teeBox, "unknown")
        XCTAssertEqual(StartRoundPresentation.teeShortLabel(selection.teeBox), "球场默认 T")
        let options = StartRoundView.resolvedTeeOptions(
            fetchedTees: [], courseTees: option.tees ?? [], teeBox: selection.teeBox,
            requiresRemoteTees: true, wasManualSearch: false
        )
        XCTAssertEqual(options, ["unknown"])
        XCTAssertTrue(StartRoundView.isStartAllowed(
            isPreparing: false, isLoadingTees: true,
            roundId: selection.roundId, courseGlobalId: 31795, teeBox: selection.teeBox,
            selectedCourseRequiresRemoteTees: true, teeOptions: options, selectedCourseWasManualSearch: false
        ))
        let rows = [CourseTee(teeBox: "white", name: "White"), CourseTee(teeBox: "blue", name: "Blue", isDefault: true)]
        XCTAssertEqual(
            StartRoundView.teeAfterRefresh(current: selection.teeBox, userPicked: false, lastUsed: nil, rows: rows),
            "blue"
        )
    }

    func testTailSearchSelectionCarriesCourseIntoStartRoundState() {
        let tail = MobileCourseOption(
            globalId: 31793,
            name: "Shadow Creek Golf Club ~ 18 洞",
            holes: 18,
            teeBox: "unknown",
            tees: ["white", "blue"]
        )
        let candidates = (1...199).map { id in
            MobileCourseOption(globalId: id, name: "北京球场 \(id)", holes: 18)
        } + [tail]

        let state = StartRoundView.selectionState(
            for: candidates.last!,
            lastUsedTee: nil,
            uuid: UUID(uuidString: "00000000-0000-0000-0000-000000000317")!
        )

        XCTAssertEqual(state.globalIdText, "31793")
        XCTAssertEqual(state.roundId, "live-31793-00000000-0000-0000-0000-000000000317")
        XCTAssertEqual(state.teeBox, "white")
    }

    func testCourseSearchPresentationPreservesUnknownProviderNamesAndLocalizesAddressesOnly() {
        let match = MobileCourseSearchMatch(
            globalId: 40_001,
            name: "Nicklaus Club Beijing",
            holes: 18,
            city: "Chaoyang District",
            province: "beijing",
            ratio: 1,
            distanceKm: 8.25
        )

        XCTAssertEqual(match.name, "Nicklaus Club Beijing")
        XCTAssertEqual(match.city, "Chaoyang District")
        XCTAssertEqual(match.displayName, "Nicklaus Club Beijing")
        XCTAssertEqual(match.subtitle, "8.2 公里 · 朝阳区 · 北京市 · 18 洞")
        XCTAssertEqual(match.courseOption?.name, "Nicklaus Club Beijing")
    }

    func testProviderNameIsPreservedWhenNoGarminChineseSourceIsPresent() {
        let match = MobileCourseSearchMatch(
            globalId: 31_793,
            name: "Shadow Creek Golf Club",
            holes: 18,
            city: "Shunyi District",
            province: "Beijing",
            ratio: 1
        )

        XCTAssertEqual(match.name, "Shadow Creek Golf Club")
        XCTAssertEqual(match.displayName, "Shadow Creek Golf Club")
        XCTAssertEqual(match.subtitle, "顺义区 · 北京市 · 18 洞")
    }

    func testGarminChineseSourceWinsOverEnglishDuplicateWithoutTranslation() {
        XCTAssertEqual(
            MobileCourseDisplayLocalization.courseName("Red Flag Valley Golf Club"),
            "Red Flag Valley Golf Club"
        )
        XCTAssertEqual(
            MobileCourseDisplayLocalization.courseName("West Park Golf & Country Club"),
            "West Park Golf & Country Club"
        )
        XCTAssertEqual(
            MobileCourseDisplayLocalization.courseName("Bangchuidao Golf Club"),
            "Bangchuidao Golf Club"
        )
        XCTAssertEqual(
            MobileCourseDisplayLocalization.preferredCourseName(
                ["Red Flag Valley Golf Club", "红旗谷高尔夫球场"],
                globalId: 42_001,
                trustedNameSources: [MobileCourseDisplayLocalization.garminSnapshotNameSource, MobileCourseDisplayLocalization.garminSnapshotNameSource]
            ),
            "红旗谷高尔夫球场"
        )
        XCTAssertEqual(
            MobileCourseDisplayLocalization.preferredCourseName(
                ["Red Flag Valley Golf Club"],
                globalId: 42_001
            ),
            "Red Flag Valley Golf Club"
        )
        XCTAssertTrue(MobileCourseDisplayLocalization.isCompositeSegment("A/C"))
        XCTAssertTrue(MobileCourseDisplayLocalization.isCompositeSegment("ABC"))
        XCTAssertTrue(MobileCourseDisplayLocalization.isCompositeSegment("AC"))
        XCTAssertFalse(MobileCourseDisplayLocalization.isCompositeSegment("Ocean"))
    }

    func testCompositeLoopNamesAreNotExposedAsSelectableSegments() {
        let match = MobileCourseSearchMatch(
            globalId: 42_002,
            name: "Example Golf Club ~ A/C",
            holes: 9,
            city: nil,
            province: nil,
            ratio: 1
        )

        XCTAssertEqual(match.displayName, "Example Golf Club")
        XCTAssertEqual(match.courseOption?.name, "Example Golf Club")
        XCTAssertNil(match.courseOption?.segmentLabel)
    }

    func testPreferredVenueUsesOnlyAnAlreadyProvidedChineseName() {
        XCTAssertEqual(
            MobileCourseDisplayLocalization.preferredVenueName(
                ["West Park Golf & Country Club", "西郊高尔夫俱乐部"],
                trustedNameSources: [MobileCourseDisplayLocalization.garminSnapshotNameSource, MobileCourseDisplayLocalization.garminSnapshotNameSource]
            ),
            "西郊高尔夫俱乐部"
        )
        XCTAssertEqual(
            MobileCourseDisplayLocalization.preferredVenueName(["West Park Golf & Country Club"]),
            "West Park Golf & Country Club"
        )
    }

    func testUnmarkedChineseNameCannotOverrideProviderSpelling() {
        XCTAssertEqual(
            MobileCourseDisplayLocalization.preferredCourseName(
                ["West Park Golf & Country Club", "手填中文球场"]
            ),
            "West Park Golf & Country Club"
        )
        XCTAssertEqual(
            MobileCourseDisplayLocalization.preferredVenueName(
                ["West Park Golf & Country Club", "手填中文球场"]
            ),
            "West Park Golf & Country Club"
        )
    }

    func testUnmarkedVenueNameDoesNotLocalizeSearchResult() {
        let match = MobileCourseSearchMatch(
            globalId: 42_003,
            name: "West Park Golf & Country Club",
            holes: 18,
            city: nil,
            province: nil,
            ratio: 1,
            venueName: "手填中文球场"
        )
        XCTAssertEqual(match.displayName, "West Park Golf & Country Club")
        XCTAssertEqual(match.courseOption?.name, "West Park Golf & Country Club")
    }

    func testBackendGarminVenueKeepsTheSameNameAcrossSearchAndSelection() {
        let match = MobileCourseSearchMatch(
            globalId: 42_004,
            name: "West Park Golf & Country Club ~ West",
            holes: 9,
            city: nil,
            province: nil,
            ratio: 1,
            venueName: "西郊高尔夫俱乐部",
            venueNameSource: MobileCourseDisplayLocalization.garminSnapshotNameSource,
            segmentLabel: "West"
        )

        XCTAssertEqual(match.displayName, "西郊高尔夫俱乐部")
        XCTAssertEqual(match.courseOption?.name, "西郊高尔夫俱乐部")
        XCTAssertEqual(match.courseOption?.segmentLabel, "West")
        XCTAssertEqual(match.courseOption?.venueDisplayName, "西郊高尔夫俱乐部")
    }

    func testManualVenueCannotReplaceProviderNameButGarminSnapshotCan() {
        let manual = MobileCourseOption(
            globalId: 42_005,
            name: "Red Flag Valley Golf Club",
            holes: 18,
            venueName: "手填中文球场",
            venueNameSource: "manual"
        )
        XCTAssertEqual(manual.venueDisplayName, "Red Flag Valley Golf Club")

        let garmin = MobileCourseOption(
            globalId: 42_005,
            name: "Red Flag Valley Golf Club",
            holes: 18,
            venueName: "红旗谷高尔夫球场",
            venueNameSource: MobileCourseDisplayLocalization.garminSnapshotNameSource
        )
        XCTAssertEqual(garmin.venueDisplayName, "红旗谷高尔夫球场")
    }

    func testRoundDisplayNameUsesPhysicalVenueForSingleAndCompositeLoops() {
        let loopA = MobileCourseOption(
            globalId: 31783,
            name: "Tian An Holiday Sports Club ~ A",
            holes: 9,
            venueName: "Tian An Holiday Sports Club",
            segmentLabel: "A",
            segmentHoles: 9
        )
        let loopB = MobileCourseOption(
            globalId: 31784,
            name: "Tian An Holiday Sports Club ~ B",
            holes: 9,
            venueName: "Tian An Holiday Sports Club",
            segmentLabel: "B",
            segmentHoles: 9
        )

        XCTAssertEqual(
            StartRoundView.roundDisplayName(front: loopA, back: nil),
            "Tian An Holiday Sports Club"
        )
        XCTAssertEqual(
            StartRoundView.roundDisplayName(front: loopA, back: loopB),
            "Tian An Holiday Sports Club"
        )
        XCTAssertEqual(
            StartRoundView.roundDisplayName(front: loopA, back: loopA),
            "Tian An Holiday Sports Club"
        )
    }

    func testReconciliationRepairsStaleBlackKnightLoopLabelsWithPartialCatalogue() {
        let venue = "北京天竺黑骑士球员俱乐部"
        let providerRows = [
            MobileCourseOption(
                globalId: 31796, name: "\(venue) ~ C/A", holes: 9,
                venueName: venue, segmentLabel: "C/A", segmentHoles: 9
            ),
            MobileCourseOption(
                globalId: 31794, name: "\(venue) ~ A/B", holes: 9,
                venueName: venue, segmentLabel: "", segmentHoles: 9
            ),
            MobileCourseOption(
                globalId: 31795, name: "\(venue) ~ B/C", holes: 9,
                venueName: venue, segmentLabel: "", segmentHoles: 9
            ),
        ]
        // Only C is present in the current player catalogue. A and B must still recover from the
        // provider's old played-combination names rather than falling back to two "全场" rows.
        let catalogue = [
            MobileCourseOption(
                globalId: 31796, name: "\(venue) ~ C/A", holes: 18,
                venueName: venue, segmentLabel: "C", segmentHoles: 9
            ),
        ]
        let downloaded = providerRows.map {
            MobileCourseOption(
                globalId: $0.globalId,
                name: $0.name,
                holes: 9,
                geometryCoverage: "ready",
                venueName: venue,
                segmentLabel: "",
                segmentHoles: 9
            )
        }

        let reconciled = StartRoundView.reconciledCourseOptions(
            primary: providerRows,
            catalogue: catalogue,
            downloaded: downloaded
        )
        let group = courseVenueGroups(reconciled).first

        XCTAssertEqual(group?.venue, venue)
        XCTAssertEqual(group?.segments.map(\.globalId), [31794, 31795, 31796])
        XCTAssertEqual(
            group?.segments.map(\.segmentDisplayTitle),
            ["A 场", "B 场", "C 场"]
        )
        XCTAssertEqual(
            group?.segments.map(\.name),
            [venue, venue, venue]
        )
        XCTAssertEqual(group?.segments.map(\.resolvedHoles), [9, 9, 9])
    }

    func testNineHoleWithoutLoopLabelIsNeverPresentedAsWholeCourse() {
        let unlabeledNine = MobileCourseOption(
            globalId: 9001,
            name: "示例球场",
            holes: 9,
            segmentLabel: nil,
            segmentHoles: nil
        )
        let wholeEighteen = MobileCourseOption(
            globalId: 9002,
            name: "示例球场",
            holes: 18,
            segmentLabel: nil,
            segmentHoles: 18
        )

        XCTAssertEqual(unlabeledNine.segmentDisplayTitle, "9 洞组")
        XCTAssertEqual(wholeEighteen.segmentDisplayTitle, "全场")
    }

    func testSegmentTitlesPreserveNamesAndAppendFieldSuffixOnlyOnce() {
        XCTAssertEqual(
            GarminCourseNameAuthority.userFacingSegmentTitle(label: "A", holes: 9),
            "A 场"
        )
        XCTAssertEqual(
            GarminCourseNameAuthority.userFacingSegmentTitle(label: "B", holes: 9),
            "B 场"
        )
        XCTAssertEqual(
            GarminCourseNameAuthority.userFacingSegmentTitle(label: "C", holes: 9),
            "C 场"
        )
        XCTAssertEqual(
            GarminCourseNameAuthority.userFacingSegmentTitle(label: "老球场", holes: 9),
            "老球场"
        )
        XCTAssertEqual(
            GarminCourseNameAuthority.userFacingSegmentTitle(label: "新球场", holes: 9),
            "新球场"
        )
        XCTAssertEqual(
            GarminCourseNameAuthority.userFacingSegmentTitle(label: "A 场", holes: 9),
            "A 场"
        )
        XCTAssertEqual(
            GarminCourseNameAuthority.userFacingSegmentTitle(label: "AC", holes: 9),
            "9 洞组"
        )
        XCTAssertEqual(
            GarminCourseNameAuthority.userFacingSegmentTitle(label: nil, holes: 18),
            "全场"
        )
    }

    func testSecondNineCandidatesKeepOnlySameVenueNineHoleRows() {
        let selected = MobileCourseOption(
            globalId: 9101,
            name: "黑骑士 ~ A",
            holes: 9,
            venueName: "黑骑士",
            segmentLabel: "A",
            segmentHoles: 9
        )
        let sibling = MobileCourseOption(
            globalId: 9102,
            name: "黑骑士 ~ B",
            holes: 9,
            venueName: "黑骑士",
            segmentLabel: "B",
            segmentHoles: 9
        )
        let staleWholeVenueRow = MobileCourseOption(
            globalId: 9103,
            name: "黑骑士",
            holes: 18,
            venueName: "黑骑士",
            segmentLabel: nil,
            segmentHoles: 18
        )
        let otherVenue = MobileCourseOption(
            globalId: 9104,
            name: "另一球场 ~ C",
            holes: 9,
            venueName: "另一球场",
            segmentLabel: "C",
            segmentHoles: 9
        )

        XCTAssertEqual(
            StartRoundView.sameVenueNineHoleCandidates(
                selected: selected,
                candidates: [staleWholeVenueRow, otherVenue, sibling, selected]
            ).map(\.globalId),
            [9101, 9102]
        )
    }

    func testNearby401ExplainsThatTheAppLoginExpired() {
        XCTAssertEqual(
            StartRoundView.nearbyDiscoveryErrorMessage(
                SyncClientError.http(status: 401, body: nil)
            ),
            "登录已失效；请重新登录后再查找附近球场。"
        )
    }

    func testNearbyTimeoutHasAnHonestRecoverableTerminalState() {
        XCTAssertEqual(
            StartRoundView.nearbyDiscoveryErrorMessage(URLError(.timedOut)),
            "附近球场暂时无法读取；可重试，或按城市或球场名搜索。"
        )
    }

    // MARK: - B4b: one course list, first-loop tiles, start title

    func testCourseListMergesSourcesNearbyFirstWithoutDuplicateVenues() {
        let bkA = loop(9101, venue: "黑骑士", label: "A")
        let bkB = loop(9102, venue: "黑骑士", label: "B")
        let bkC = loop(9103, venue: "黑骑士", label: "C")
        let northLake = MobileCourseOption(globalId: 9201, name: "北湖", holes: 18, venueName: "北湖", segmentHoles: 18)
        let searched = loop(9301, venue: "天马", label: "东")
        let recentStale = loop(9102, venue: "黑骑士", label: "B")
        let downloaded = MobileCourseOption(globalId: 9401, name: "丽宫", holes: 18, venueName: "丽宫", segmentHoles: 18)

        let rows = StartRoundPresentation.mergedCourseRows(
            nearby: [bkC, northLake, bkA, bkB],
            search: [searched],
            recent: [recentStale],
            downloaded: [downloaded, northLake]
        )

        XCTAssertEqual(rows.map(\.venue), ["黑骑士", "北湖", "天马", "丽宫"])
        XCTAssertEqual(rows.map(\.source), [.nearby, .nearby, .search, .downloaded])
        XCTAssertEqual(rows[0].segments.map(\.globalId), [9101, 9102, 9103], "loops keep the course's A/B/C order")
        XCTAssertEqual(rows[0].holes, 27)
        XCTAssertEqual(rows[1].holes, 18)
        XCTAssertEqual(rows[0].id, 9101)
    }

    func testCourseListKeepsTheRecentCourseWhenNearbyOmitsIt() {
        let nearby = MobileCourseOption(globalId: 1, name: "附近球场", holes: 18, venueName: "附近球场", segmentHoles: 18)
        let recent = loop(2, venue: "黑骑士", label: "B")
        let rows = StartRoundPresentation.mergedCourseRows(nearby: [nearby], recent: [recent])
        XCTAssertEqual(rows.map(\.venue), ["附近球场", "黑骑士"])
        XCTAssertEqual(rows.last?.source, .recent)
    }

    func testNearbyRowsSortByDistanceAndKeepUnlocatedRowsInProviderOrder() {
        let far = MobileCourseOption(globalId: 1, name: "far", latitude: 40.30, longitude: 116.55)
        let unknownFirst = MobileCourseOption(globalId: 2, name: "unknown-1")
        let near = MobileCourseOption(globalId: 3, name: "near", latitude: 40.046, longitude: 116.546)
        let unknownSecond = MobileCourseOption(globalId: 4, name: "unknown-2")
        XCTAssertEqual(
            StartRoundPresentation.sortedByDistance(
                [far, unknownFirst, near, unknownSecond],
                latitude: 40.0455,
                longitude: 116.5462
            ).map(\.globalId),
            [3, 1, 2, 4]
        )
    }

    func testDistanceCopyMatchesThePrototype() {
        XCTAssertEqual(StartRoundPresentation.distanceText(metres: 1_200), "1.2 公里")
        XCTAssertEqual(StartRoundPresentation.distanceText(metres: 8_640), "8.6 公里")
        XCTAssertEqual(StartRoundPresentation.distanceText(metres: 23_400), "23 公里")
        XCTAssertEqual(StartRoundPresentation.distanceText(metres: 9_990), "10 公里")
        XCTAssertEqual(StartRoundPresentation.distanceText(metres: 350), "0.4 公里")
        XCTAssertNil(StartRoundPresentation.distanceText(metres: .infinity))
    }

    func testLoopTilesUseTheCourseOwnLoopNames() {
        XCTAssertEqual(StartRoundPresentation.loopTileTitle(loop(1, venue: "黑骑士", label: "A")), "A 场")
        XCTAssertEqual(StartRoundPresentation.loopTileTitle(loop(2, venue: "天马", label: "东")), "东")
        XCTAssertEqual(
            StartRoundPresentation.loopTileTitle(
                MobileCourseOption(globalId: 3, name: "北湖", holes: 18, venueName: "北湖", segmentHoles: 18)
            ),
            "18 洞"
        )
    }

    /// Arzaga (2026-10-10): an 18-hole Jack Nicklaus II beside a 9-hole Gary Player. Whichever is
    /// selected, both are offered; the whole course comes first.
    func testA18HoleCourseBesideANineIsOfferedWithIt() {
        let nicklaus = MobileCourseOption(
            globalId: 26807, name: "Arzaga Golf Club", holes: 18,
            venueName: "Arzaga Golf Club", segmentLabel: "Jack Nicklaus II", segmentHoles: 18
        )
        let player = MobileCourseOption(
            globalId: 26808, name: "Arzaga Golf Club", holes: 9,
            venueName: "Arzaga Golf Club", segmentLabel: "Gary Player", segmentHoles: 9
        )
        let elsewhere = loop(26790, venue: "Gardagolf Country Club", label: "Bianco")
        let candidates = [player, elsewhere, nicklaus]

        for selected in [player, nicklaus] {
            XCTAssertEqual(
                StartRoundView.sameVenueStartableCourses(selected: selected, candidates: candidates).map(\.globalId),
                [26807, 26808],
                "selected \(selected.globalId)"
            )
        }
        XCTAssertEqual(StartRoundPresentation.loopTileTitle(nicklaus), "Jack Nicklaus II")
        XCTAssertEqual(
            StartRoundPresentation.startActionTitle(selected: player, loops: [nicklaus, player], teeBox: "white"),
            StartRoundPresentation.startActionTitle(selected: player, loops: [player], teeBox: "white"),
            "the nine's start title ignores the 18-hole course beside it"
        )
    }

    func testVenuesWithOnlyNinesOrOnlyOneCourseAreUnchanged() {
        let a = loop(1, venue: "黑骑士", label: "A")
        let b = loop(2, venue: "黑骑士", label: "B")
        let c = loop(3, venue: "黑骑士", label: "C")
        XCTAssertEqual(
            StartRoundView.sameVenueStartableCourses(selected: b, candidates: [c, a, b]).map(\.globalId),
            StartRoundView.sameVenueNineHoleCandidates(selected: b, candidates: [c, a, b]).map(\.globalId)
        )
        let single = MobileCourseOption(globalId: 9, name: "北湖", holes: 18, venueName: "北湖", segmentHoles: 18)
        XCTAssertEqual(StartRoundView.sameVenueStartableCourses(selected: single, candidates: [single, a]).map(\.globalId), [9])
    }

    func testTeeYardsAreShownOnlyWhenTheyCoverTheHolesBeingStarted() {
        XCTAssertEqual(StartRoundPresentation.teeYards(total: 3201, teeHoleCount: 9, playedHoles: 9), 3201)
        XCTAssertEqual(StartRoundPresentation.teeYards(total: 6412, teeHoleCount: 18, playedHoles: 18), 6412)
        XCTAssertNil(
            StartRoundPresentation.teeYards(total: 6412, teeHoleCount: 18, playedHoles: 9),
            "a nine-hole start never shows an 18-hole total"
        )
        XCTAssertEqual(StartRoundPresentation.teeYards(total: 3201, teeHoleCount: nil, playedHoles: 9), 3201)
        XCTAssertNil(StartRoundPresentation.teeYards(total: nil, teeHoleCount: 9, playedHoles: 9))
        XCTAssertNil(StartRoundPresentation.teeYards(total: 3201, teeHoleCount: 9, playedHoles: nil))
    }

    func testChangeCourseKeepsANeverPlayedVenueSelectedWhenTheRequeryFails() {
        // The home's course-here rows for a venue that is in no catalogue, download or recent
        // record (never played, not downloaded).
        let labels: [String] = ["A", "B", "C"]
        let matches: [MobileCourseSearchMatch] = labels.enumerated().map { index, label in
            MobileCourseSearchMatch(
                globalId: 90_001 + index, name: "新球场 ~ \(label)", holes: 9, city: "北京",
                province: nil, ratio: 1, latitude: 40.0, longitude: 116.0 + Double(index) * 0.001,
                distanceKm: 0.2, venueName: "新球场", segmentLabel: label
            )
        }
        let homeRows = HubNearby.options(from: matches, catalogue: [], downloaded: [])
        let carried = HubNearby.venueLoops(containing: 90_002, in: homeRows)
        XCTAssertEqual(carried.map(\.globalId), [90_001, 90_002, 90_003])

        // 开始一场's own nearby query failed (no current rows); nothing else lists the venue.
        let selected = StartRoundView.selectedSegment(
            globalId: 90_002,
            current: [],
            preselectedVenue: carried,
            offline: [],
            explicit: [],
            recent: nil
        )
        XCTAssertEqual(selected?.globalId, 90_002, "the known loop stays selected without a second request")
        let loops = StartRoundView.sameVenueNineHoleCandidates(
            selected: selected!,
            candidates: [selected!] + carried
        )
        XCTAssertEqual(loops.map(\.globalId), [90_001, 90_002, 90_003], "the complete provider sibling set")
        let rows = StartRoundPresentation.mergedCourseRows(nearby: [], recent: loops)
        XCTAssertEqual(rows.count, 1)
        XCTAssertEqual(rows.first?.holes, 27)

        // A current nearby row for the same id still wins over the carried one.
        let fresh = MobileCourseOption(
            globalId: 90_002, name: "新球场", holes: 9, venueName: "新球场", segmentLabel: "B", segmentHoles: 9
        )
        XCTAssertEqual(
            StartRoundView.selectedSegment(
                globalId: 90_002, current: [fresh], preselectedVenue: carried, offline: [], explicit: [], recent: nil
            ),
            fresh
        )
        XCTAssertTrue(HubNearby.venueLoops(containing: 12_345, in: homeRows).isEmpty)
    }

    func testTheCarriedVenueOwnsItsRowOverAPartialDownloadOfTheSameVenue() {
        let labels: [String] = ["A", "B", "C"]
        let carried: [MobileCourseOption] = labels.enumerated().map { index, label in
            MobileCourseOption(
                globalId: 90_001 + index, name: "新球场", holes: 9,
                venueName: "新球场", segmentLabel: label, segmentHoles: 9
            )
        }
        let downloadedA = MobileCourseOption(
            globalId: 90_001, name: "新球场", holes: 9, venueName: "新球场", segmentLabel: "A", segmentHoles: 9
        )
        let selected = carried[1]
        let loops = StartRoundView.sameVenueNineHoleCandidates(selected: selected, candidates: [selected] + carried)
        // The destination's nearby requery failed (no nearby / search rows); only A is downloaded.
        let rows = StartRoundView.courseRows(
            nearby: [], search: [], recent: [], downloaded: [downloadedA],
            selected: selected, selectedLoops: loops, preselectedVenue: carried
        )
        XCTAssertEqual(rows.count, 1, "the partial download dedupes behind the carried venue")
        XCTAssertEqual(rows.first?.segments.map(\.globalId), [90_001, 90_002, 90_003])
        XCTAssertEqual(rows.first?.holes, 27)

        // Without a carried venue, a downloaded selection keeps its own row (selecting never moves it).
        let own = StartRoundView.courseRows(
            nearby: [], search: [], recent: [], downloaded: [downloadedA],
            selected: downloadedA, selectedLoops: [downloadedA], preselectedVenue: []
        )
        XCTAssertEqual(own.map(\.source), [.downloaded])
        // A current nearby row for the selected loop owns the venue; the carried rows add nothing.
        let nearbyB = carried[1]
        let current = StartRoundView.courseRows(
            nearby: [nearbyB], search: [], recent: [], downloaded: [downloadedA],
            selected: nearbyB, selectedLoops: loops, preselectedVenue: carried
        )
        XCTAssertEqual(current.first?.source, .nearby)
        XCTAssertEqual(current.first?.segments.map(\.globalId), [90_002])

        // A current nearby / search row with only a sibling (A, not the selected B): the carried
        // A/B/C own that venue row in place, keeping its source and position.
        let other = MobileCourseOption(
            globalId: 70_001, name: "别的球场", holes: 18, venueName: "别的球场", segmentHoles: 18
        )
        let siblingNearby = StartRoundView.courseRows(
            nearby: [other, downloadedA], search: [], recent: [], downloaded: [],
            selected: selected, selectedLoops: loops, preselectedVenue: carried
        )
        XCTAssertEqual(siblingNearby.map(\.source), [.nearby, .nearby])
        XCTAssertEqual(siblingNearby.map(\.venue), ["别的球场", "新球场"])
        XCTAssertEqual(siblingNearby.last?.segments.map(\.globalId), [90_001, 90_002, 90_003])
        XCTAssertEqual(siblingNearby.last?.holes, 27)
        let siblingSearch = StartRoundView.courseRows(
            nearby: [], search: [downloadedA], recent: [], downloaded: [downloadedA],
            selected: selected, selectedLoops: loops, preselectedVenue: carried
        )
        XCTAssertEqual(siblingSearch.count, 1)
        XCTAssertEqual(siblingSearch.first?.source, .search)
        XCTAssertEqual(siblingSearch.first?.segments.map(\.globalId), [90_001, 90_002, 90_003])
        XCTAssertEqual(siblingSearch.first?.holes, 27)
    }

    func testChangeCourseKeepsTheCardsLastTeeWhenTheCourseOffersIt() {
        let offered = ["Gold", "Blue", "White"]
        let tee = StartRoundView.initialTee(callerTee: "white", offered: offered, courseTee: "blue")
        XCTAssertEqual(tee, "White", "the card's last tee wins over the Blue/White default")
        // The /tees refresh offers White too, so it stays White (not the default Blue row).
        let rows = [
            CourseTee(teeBox: "gold", name: "Gold", yards: 3585, holeCount: 9),
            CourseTee(teeBox: "blue", name: "Blue", yards: 3393, holeCount: 9, isDefault: true),
            CourseTee(teeBox: "white", name: "White", yards: 3019, holeCount: 9),
        ]
        let refreshed = StartRoundView.teeAfterRefresh(current: tee, userPicked: false, lastUsed: "white", rows: rows)
        XCTAssertEqual(refreshed.lowercased(), "white")
        let loopB = MobileCourseOption(
            globalId: 31795, name: "北京天竺黑骑士球员俱乐部", holes: 9,
            venueName: "北京天竺黑骑士球员俱乐部", segmentLabel: "B", segmentHoles: 9, tees: offered
        )
        XCTAssertEqual(
            StartRoundPresentation.startActionTitle(selected: loopB, loops: [loopB], teeBox: refreshed),
            "从 B 场 开始 · 白 T"
        )

        // Unknown / blank / not offered → the course default choice.
        XCTAssertEqual(StartRoundView.initialTee(callerTee: "unknown", offered: offered, courseTee: nil), "Blue")
        XCTAssertEqual(StartRoundView.initialTee(callerTee: "  ", offered: offered, courseTee: nil), "Blue")
        XCTAssertEqual(StartRoundView.initialTee(callerTee: "red", offered: offered, courseTee: nil), "Blue")
        // No tee list to check against → the caller's tee (the /tees refresh corrects an invalid one).
        XCTAssertEqual(StartRoundView.initialTee(callerTee: "white", offered: [], courseTee: "blue"), "white")
        XCTAssertEqual(StartRoundView.initialTee(callerTee: "unknown", offered: [], courseTee: "blue"), "blue")
        XCTAssertEqual(StartRoundView.teeAfterRefresh(current: "red", userPicked: false, lastUsed: "red", rows: rows), "blue")
    }

    func testFetchedTeeDefaultReplacesAutomaticGuess() {
        let course = MobileCourseOption(globalId: 401, name: "测试球场", holes: 9, tees: ["Blue", "Gold"])
        let lastUsed = StartRoundView.lastUsedTeeForCourse(for: course, recent: nil, caller: nil, callerTee: "unknown")
        XCTAssertNil(lastUsed)
        let selection = StartRoundView.selectionState(for: course, lastUsedTee: lastUsed)
        XCTAssertEqual(selection.teeBox, "Blue", "a catalogue without a default initially guesses Blue")
        let rows = [
            CourseTee(teeBox: "Blue", name: "Blue"),
            CourseTee(teeBox: "Gold", name: "Gold", isDefault: true),
        ]
        XCTAssertEqual(StartRoundView.teeAfterRefresh(current: selection.teeBox, userPicked: false, lastUsed: lastUsed, rows: rows), "Gold")
        XCTAssertEqual(StartRoundView.teeAfterRefresh(current: selection.teeBox, userPicked: false, lastUsed: "blue", rows: rows), "Blue", "a real last-used tee still wins")
    }

    func testPendingTeeRefreshValidatesManualPick() {
        // The player taps the bundled Blue chip while /tees is pending. Its response removes Blue.
        let rows = [
            CourseTee(teeBox: "White", name: "White"),
            CourseTee(teeBox: "Red", name: "Red", isDefault: true),
        ]
        XCTAssertEqual(
            StartRoundView.teeAfterRefresh(current: "Blue", userPicked: true, lastUsed: nil, rows: rows),
            "Red", "an unoffered pick falls back to the course default"
        )
        XCTAssertEqual(
            StartRoundView.teeAfterRefresh(current: "Blue", userPicked: true, lastUsed: "white", rows: rows),
            "White", "an unoffered pick falls back through the historical preference rule"
        )
        XCTAssertEqual(
            StartRoundView.teeAfterRefresh(current: "white", userPicked: true, lastUsed: nil, rows: rows),
            "White", "an offered manual pick wins and uses the response's spelling"
        )
    }

    func testLastUsedTeeIsScopedToTheRecentOrCallerVenue() {
        let caller = MobileCourseOption(globalId: 401, name: "测试球场 ~ A", holes: 9, venueName: "测试球场")
        let sibling = MobileCourseOption(globalId: 402, name: "测试球场 ~ B", holes: 9, venueName: "测试球场")
        let recent = MobileCourseOption(globalId: 403, name: "测试球场 ~ C", holes: 9, teeBox: "White", venueName: "测试球场")
        let other = MobileCourseOption(globalId: 501, name: "另一球场", holes: 9, tees: ["Blue", "Gold"])
        XCTAssertEqual(
            StartRoundView.lastUsedTeeForCourse(for: sibling, recent: recent, caller: caller, callerTee: "Gold"), "White"
        )
        XCTAssertEqual(
            StartRoundView.lastUsedTeeForCourse(for: sibling, recent: other, caller: caller, callerTee: "Gold"), "Gold"
        )
        let otherLastUsed = StartRoundView.lastUsedTeeForCourse(for: other, recent: recent, caller: caller, callerTee: "White")
        XCTAssertNil(otherLastUsed, "switching venues must not carry the previous venue's tee")
        XCTAssertEqual(StartRoundView.selectionState(for: other, lastUsedTee: otherLastUsed).teeBox, "Blue")
    }

    func testADownloadedCourseFarFromHereStaysInTheListTail() {
        let near = loop(1, venue: "黑骑士", label: "A")
        let recent = loop(2, venue: "北湖", label: "A")
        let travel = loop(3, venue: "海南神州", label: "A")
        let rows = StartRoundPresentation.mergedCourseRows(
            nearby: [near],
            recent: [recent],
            downloaded: [near, travel]
        )
        XCTAssertEqual(rows.map(\.venue), ["黑骑士", "北湖", "海南神州"])
        XCTAssertEqual(rows.map(\.source), [.nearby, .recent, .downloaded])
    }

    func testStartTitleNamesTheFirstLoopAndTee() {
        let bkA = loop(9101, venue: "黑骑士", label: "A")
        let bkB = loop(9102, venue: "黑骑士", label: "B")
        XCTAssertEqual(
            StartRoundPresentation.startActionTitle(selected: bkB, loops: [bkA, bkB], teeBox: "blue"),
            "从 B 场 开始 · 蓝 T"
        )
        XCTAssertEqual(
            StartRoundPresentation.startActionTitle(selected: bkB, loops: [], teeBox: ""),
            "从 B 场 开始"
        )
        XCTAssertEqual(
            StartRoundPresentation.startActionTitle(selected: loop(1, venue: "天马", label: "东"), loops: [], teeBox: "Black"),
            "从 东 开始 · 黑 T"
        )
        let wholeCourse = MobileCourseOption(globalId: 9201, name: "北湖", holes: 18, venueName: "北湖", segmentHoles: 18)
        XCTAssertEqual(
            StartRoundPresentation.startActionTitle(selected: wholeCourse, loops: [wholeCourse], teeBox: "white"),
            "从 前九 开始 · 白 T",
            "an 18-hole course starts on one half, 前九 by default"
        )
        XCTAssertEqual(
            StartRoundPresentation.startActionTitle(selected: wholeCourse, loops: [wholeCourse], teeBox: "blue", half: "back"),
            "从 后九 开始 · 蓝 T"
        )
        XCTAssertEqual(
            StartRoundPresentation.startActionTitle(selected: wholeCourse, loops: [], teeBox: "blue", half: "front"),
            "从 前九 开始 · 蓝 T"
        )
        for title in [
            StartRoundPresentation.startActionTitle(selected: wholeCourse, loops: [wholeCourse], teeBox: "blue"),
            StartRoundPresentation.startActionTitle(selected: wholeCourse, loops: [wholeCourse], teeBox: "blue", half: "back"),
        ] {
            XCTAssertFalse(title.contains("18 洞"), title)
        }
        XCTAssertEqual(StartRoundPresentation.startActionTitle(selected: nil, loops: [], teeBox: "blue"), "开始")
    }

    func testStartLoopsRequestOneHalfOfAnEighteenHoleCourseAndTheWholeNineHoleLoop() {
        let wholeCourse = MobileCourseOption(globalId: 9201, name: "北湖", holes: 18, venueName: "北湖", segmentHoles: 18)
        XCTAssertEqual(
            StartRoundPresentation.startLoops(selected: wholeCourse),
            [RoundLoopEntry(globalId: 9201, half: "front")]
        )
        XCTAssertEqual(
            StartRoundPresentation.startLoops(selected: wholeCourse, half: "front"),
            [RoundLoopEntry(globalId: 9201, half: "front")]
        )
        XCTAssertEqual(
            StartRoundPresentation.startLoops(selected: wholeCourse, half: "back"),
            [RoundLoopEntry(globalId: 9201, half: "back")]
        )
        let bkB = loop(9102, venue: "黑骑士", label: "B")
        XCTAssertEqual(StartRoundPresentation.startLoops(selected: bkB), [RoundLoopEntry(globalId: 9102, half: "all")])
        XCTAssertEqual(
            StartRoundPresentation.startLoops(selected: bkB, half: "back"),
            [RoundLoopEntry(globalId: 9102, half: "all")],
            "a nine-hole loop has no halves"
        )
    }

    func testTeeLabelsAreShortAndKeepUnknownNames() {
        XCTAssertEqual(StartRoundPresentation.teeShortLabel("Blue"), "蓝 T")
        XCTAssertEqual(StartRoundPresentation.teeShortLabel("championship"), "黑 T")
        XCTAssertEqual(StartRoundPresentation.teeShortLabel("unknown"), "球场默认 T")
        XCTAssertEqual(StartRoundPresentation.teeShortLabel("Combo"), "Combo")
        XCTAssertNil(StartRoundPresentation.teeShortLabel("  "))
    }

    private func loop(_ globalId: Int, venue: String, label: String) -> MobileCourseOption {
        MobileCourseOption(
            globalId: globalId,
            name: "\(venue) ~ \(label)",
            holes: 9,
            venueName: venue,
            segmentLabel: label,
            segmentHoles: 9
        )
    }

    private func option(
        globalId: Int,
        name: String,
        latitude: Double?,
        longitude: Double?,
        roundCount: Int
    ) -> MobileCourseOption {
        MobileCourseOption(
            globalId: globalId,
            name: name,
            roundCount: roundCount,
            holes: 18,
            latitude: latitude,
            longitude: longitude
        )
    }

    /// While nearby is still coming the list says so above the usable rows (the watch shows the
    /// same two states). A failure, an explicit search pick, or arrived nearby rows end the line.
    func testNearbyPendingLineShowsOnlyWhileNearbyIsActuallyBeingLookedFor() {
        func text(
            loading: Bool = true, failed: Bool = false, manual: Bool = false,
            nearby: Bool = false, fix: Bool
        ) -> String? {
            StartRoundView.nearbyPendingText(
                isLoading: loading, failed: failed, manualSearchSelected: manual,
                hasNearbyRows: nearby, hasFix: fix
            )
        }
        XCTAssertEqual(text(fix: false), "正在等待定位…")
        XCTAssertEqual(text(fix: true), "正在找附近球场…")
        XCTAssertNil(text(nearby: true, fix: true), "nearby arrived")
        XCTAssertNil(text(failed: true, fix: true), "the retry icon replaces it")
        XCTAssertNil(text(manual: true, fix: true), "an explicit search pick ends the wait")
        XCTAssertNil(text(loading: false, fix: false), "denied GPS: nothing is being looked for")
    }

    private func blackKnight(_ id: Int, _ loop: String) -> MobileCourseOption {
        let venue = "北京天竺黑骑士球员俱乐部"
        return MobileCourseOption(
            globalId: id, name: "\(venue) ~ \(loop)", holes: 9,
            venueName: venue, segmentLabel: loop, segmentHoles: 9
        )
    }

    /// The captions the list draws, through the subtitle's own chain (`holeCaption(for:...)`).
    private func captions(
        nearby: [MobileCourseOption] = [],
        recentRows: [MobileCourseOption] = [],
        downloaded: [MobileCourseOption] = [],
        catalogue: [MobileCourseOption] = [],
        recentRecord: MobileCourseOption? = nil
    ) -> [String?] {
        StartRoundPresentation.mergedCourseRows(nearby: nearby, recent: recentRows, downloaded: downloaded).map {
            StartRoundView.holeCaption(for: $0, downloaded: downloaded, catalogue: catalogue, recent: recentRecord)
        }
    }

    /// Codex review of #392: recent 黑骑士 A wins the venue's de-duplication over downloaded A/B,
    /// so a caption keyed on the row source showed a bare "9 洞" (neither the venue nor what is on
    /// the phone), then nearby A/B/C showed "27 洞". The caption now says what it covers.
    func testHoleCaptionSaysWhatTheCountCoversWhicheverSourceOwnsTheRow() {
        let loopA = blackKnight(31794, "A"), loopB = blackKnight(31795, "B"), loopC = blackKnight(31796, "C")
        // Before nearby: one row (recent owns it), captioned with the download coverage A+B.
        let waiting = StartRoundPresentation.mergedCourseRows(nearby: [], recent: [loopA], downloaded: [loopA, loopB])
        XCTAssertEqual(waiting.count, 1)
        XCTAssertEqual(waiting.first?.source, .recent)
        XCTAssertEqual(waiting.first?.segments.map(\.globalId), [31794], "sources' loops never mix")
        XCTAssertEqual(
            captions(recentRows: [loopA], downloaded: [loopA, loopB], recentRecord: loopA),
            ["已下载 18 洞"]
        )
        // Nearby arrives with the whole venue.
        XCTAssertEqual(
            captions(nearby: [loopA, loopB, loopC], recentRows: [loopA], downloaded: [loopA, loopB], recentRecord: loopA),
            ["27 洞"]
        )
        // The actual recent record with nothing downloaded: only the loops last played.
        XCTAssertEqual(captions(recentRows: [loopA], recentRecord: loopA), ["最近打过 9 洞"])
        // A downloaded-only row: its own loops.
        XCTAssertEqual(captions(downloaded: [loopA]), ["已下载 9 洞"])
    }

    /// Codex review 6044451139 (1): the catalogue names and groups a downloaded package, but its
    /// whole-course count must not replace the installed template's. Same id: downloaded 9, catalogue 18.
    func testDownloadedCoverageCountsTheInstalledTemplateNotTheCatalogueCourse() {
        let installed = MobileCourseOption(globalId: 40001, name: "丽宫 ~ 前九", holes: 9, segmentHoles: 9)
        let catalogue = MobileCourseOption(
            globalId: 40001, name: "北京丽宫体育公园高尔夫俱乐部", holes: 18,
            venueName: "北京丽宫体育公园高尔夫俱乐部", segmentHoles: 18
        )
        let reconciled = StartRoundView.reconciledCourseOptions(
            primary: [installed], catalogue: [catalogue], downloaded: [installed]
        )
        // The list row is built from the reconciled package, exactly as the screen does.
        let rows = StartRoundPresentation.mergedCourseRows(nearby: [], downloaded: reconciled)
        XCTAssertEqual(rows.count, 1)
        XCTAssertEqual(
            rows.map { StartRoundView.holeCaption(for: $0, downloaded: [installed], catalogue: [catalogue], recent: nil) },
            ["已下载 9 洞"]
        )
    }

    /// Codex review 6044451139 (2): the carried selection (home GPS card) is sorted with the recent
    /// rows, but with no recent record and nothing downloaded it was never played: its loops come
    /// from the catalogue/provider authority and read as the venue.
    func testCarriedVenueWithoutRecentRecordNeverClaimsItWasPlayed() {
        let loops = [blackKnight(31794, "A"), blackKnight(31795, "B"), blackKnight(31796, "C")]
        let rows = StartRoundView.courseRows(
            nearby: [], search: [], recent: [], downloaded: [],
            selected: loops[1], selectedLoops: loops, preselectedVenue: loops
        )
        XCTAssertEqual(rows.count, 1)
        XCTAssertEqual(rows.first?.source, .recent, "the order is unchanged")
        XCTAssertEqual(
            rows.map { StartRoundView.holeCaption(for: $0, downloaded: [], catalogue: loops, recent: nil) },
            ["27 洞"]
        )
        // Having last played loop A here does not make the carried A/B/C row a played 27 holes.
        XCTAssertEqual(
            rows.map { StartRoundView.holeCaption(for: $0, downloaded: [], catalogue: loops, recent: loops[0]) },
            ["27 洞"]
        )
    }
}
