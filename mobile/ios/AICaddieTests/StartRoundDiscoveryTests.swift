import XCTest
import AICaddieDomain
@testable import AICaddie

final class StartRoundDiscoveryTests: XCTestCase {
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

    func testManualSearchCanStartWhileTeeAuthorityIsStillLoading() {
        let common: (Bool) -> Bool = { manualSearch in
            StartRoundView.isStartAllowed(
                isPreparing: false,
                isLoadingTees: true,
                roundId: "live-31670-test",
                courseGlobalId: 31670,
                teeBox: "unknown",
                selectedCourseRequiresRemoteTees: true,
                teeOptions: [],
                selectedCourseWasManualSearch: manualSearch
            )
        }

        XCTAssertTrue(common(true))
        XCTAssertFalse(common(false))
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
            currentTeeBox: "",
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
            ["第 1 个 9 洞组", "第 2 个 9 洞组", "第 3 个 9 洞组"]
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

    func testProviderCompositeLoopTokensStayOutOfUserFacingTitles() {
        XCTAssertEqual(
            GarminCourseNameAuthority.userFacingSegmentTitle(label: "A", holes: 9),
            "第 1 个 9 洞组"
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
}
