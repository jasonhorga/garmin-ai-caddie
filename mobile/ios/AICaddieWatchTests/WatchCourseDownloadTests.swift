import XCTest
@testable import AICaddieWatch

final class WatchCourseDownloadTests: XCTestCase {
    private let client = WatchBackendClient(baseURL: URL(string: "https://caddie.example")!)

    func testNearbyRankingPlacesNearestKnownCourseFirstAndUnknownLast() {
        let farther = WatchCourseOption(
            globalId: 2,
            name: "Farther",
            holes: 18,
            latitude: 40.0755,
            longitude: 116.5462
        )
        let unknown = WatchCourseOption(globalId: 3, name: "Unknown", holes: 18)
        let nearest = WatchCourseOption(
            globalId: 1,
            name: "Nearest",
            holes: 18,
            latitude: 40.0491,
            longitude: 116.5462
        )

        let ranked = WatchCourseProximity.ranked(
            [farther, unknown, nearest],
            fromLatitude: 40.0455,
            longitude: 116.5462
        )

        XCTAssertEqual(ranked.map(\.globalId), [1, 2, 3])
    }

    func testNearbyDistanceLabelMatchesApprovedPicker() {
        XCTAssertEqual(WatchCourseProximity.distanceLabel(400), "0.4 km")
        XCTAssertEqual(WatchCourseProximity.distanceLabel(3_140), "3.1 km")
        XCTAssertNil(WatchCourseProximity.distanceLabel(.infinity))
        XCTAssertNil(WatchCourseProximity.distanceLabel(-1))
    }

    func testNearbyRadiusDoesNotMislabelADistantKnownCourse() {
        XCTAssertTrue(WatchCourseProximity.isNearby(distanceM: 49_999))
        XCTAssertTrue(WatchCourseProximity.isNearby(distanceM: 50_000))
        XCTAssertFalse(WatchCourseProximity.isNearby(distanceM: 50_001))
        XCTAssertFalse(WatchCourseProximity.isNearby(distanceM: .infinity))
    }

    func testPreferredTeeDoesNotTreatUnknownAsARealTee() {
        let option = WatchCourseOption(
            globalId: 31669,
            name: "北京丽宫",
            holes: 18,
            teeBox: "unknown",
            tees: ["Blue", "White"]
        )

        XCTAssertEqual(option.preferredTee, "Blue")
    }

    func testBuildsOfflineRoundTemplateFromRealPackageAndRenderedPrep() throws {
        let option = WatchCourseOption(
            globalId: 31669,
            name: "北京丽宫",
            holes: 18,
            teeBox: "Blue",
            tees: ["Blue", "White"]
        )
        let package = try client.decodeCoursePackage(Data(
            #"{"roundId":"watch-download-1","course":{"globalId":31669,"name":"北京丽宫","teeBox":"Blue"},"holes":[{"number":1,"par":4,"yards":404,"geometryCoverage":"ready","sourceGlobalId":31669,"sourceLocalHole":1}]}"#.utf8
        ))
        let prep = try client.decodeCoursePrep(Data(
            #"{"schema":"ai-caddie-course-prep-v1","globalId":31669,"holeCount":1,"clubs":[{"name":"1W","m":220.0,"yd":241},{"name":"7I","m":140.0,"yd":153}],"holes":[{"hole":1,"par":4,"geometryCoverage":"ready","landing_m":220.0,"tee_club":"1W","hazards":{"water_carry":[[100.0,130.0]],"bunkers":[[180.0,15.0]],"details":[{"kind":"water","frontM":100.0,"backM":130.0,"frontRouteM":100.0,"backRouteM":130.0,"frontPx":[300.0,550.0],"backPx":[360.0,505.0],"sideM":null},{"kind":"bunker","frontM":168.0,"backM":184.0,"frontRouteM":170.0,"backRouteM":190.0,"frontPx":[440.0,445.0],"backPx":[470.0,420.0],"sideM":15.0}]},"map":{"image":"data:image/jpeg;base64,AQID","overlay":{"w":1000,"h":800,"ppm":1.0,"ln":400.0,"route":[[100.0,700.0,0.0],[500.0,400.0,200.0],[600.0,100.0,400.0]]}},"greenDistances":{"available":true,"frontM":350.0,"middleM":360.0,"backM":370.0,"frontLat":40.0035,"frontLon":116.005,"middleLat":40.0036,"middleLon":116.0051,"backLat":40.0037,"backLon":116.0052},"playsLike":{"available":true,"deltaM":5.0,"deltaYd":5},"holeImageProjection":{"available":true,"widthPx":1000,"heightPx":800,"refs":[{"lat":40.0,"lon":116.0,"px":100.0,"py":700.0},{"lat":40.0,"lon":116.001,"px":200.0,"py":700.0},{"lat":40.001,"lon":116.0,"px":100.0,"py":600.0}]}}]}"#.utf8
        ))

        let download = try WatchCourseTemplateBuilder.build(
            option: option,
            package: package,
            prepsByGlobalId: [31669: prep],
            cachedAt: "2026-07-26T00:00:00Z"
        )

        XCTAssertEqual(download.template.courseName, "北京丽宫")
        XCTAssertEqual(download.template.teeBox, "Blue")
        XCTAssertEqual(download.template.holeStates.count, 1)
        XCTAssertEqual(download.images, [
            WatchCourseImage(globalId: 31669, hole: 1, data: Data([1, 2, 3]))
        ])

        let round = download.template.makeRound(roundId: "watch-live-1")
        let hole = try XCTUnwrap(round.holeStates.first)
        XCTAssertEqual(round.courseName, "北京丽宫")
        XCTAssertEqual(hole.roundId, "watch-live-1")
        XCTAssertEqual(hole.hole, 1)
        XCTAssertEqual(hole.par, 4)
        XCTAssertEqual(hole.distanceM ?? 0, 369.4176, accuracy: 0.0001)
        XCTAssertEqual(hole.teeLatitude ?? 0, 40.0, accuracy: 0.000_001)
        XCTAssertEqual(hole.teeLongitude ?? 0, 116.0, accuracy: 0.000_001)
        XCTAssertEqual(hole.suggestedClub, "1W")
        XCTAssertEqual(hole.availableClubNames, ["1W", "7I"])
        XCTAssertEqual(hole.frontGreenM, 350)
        XCTAssertEqual(hole.centerGreenM, 360)
        XCTAssertEqual(hole.backGreenM, 370)
        XCTAssertEqual(hole.elevationDeltaM, 5)
        XCTAssertEqual(hole.playsLikeDistanceM ?? 0, 374.4176, accuracy: 0.0001)
        XCTAssertEqual(hole.globalId, 31669)
        XCTAssertEqual(hole.holeMap?.you, [100, 700])
        XCTAssertEqual(hole.holeMap?.pin, [600, 100])
        XCTAssertEqual(hole.holeMap?.route, [
            [100, 700, 0],
            [500, 400, 200],
            [600, 100, 400],
        ])
        XCTAssertEqual(hole.hazards.map(\.label), ["沙坑", "水域"])
        let bunker = try XCTUnwrap(hole.hazards.first)
        XCTAssertEqual(bunker.startM, 170)
        XCTAssertEqual(bunker.endM, 190)
        XCTAssertEqual(bunker.frontDistanceM, 168)
        XCTAssertEqual(bunker.backDistanceM, 184)
        XCTAssertEqual(bunker.frontPx, [440, 445])
        XCTAssertEqual(bunker.backPx, [470, 420])
        XCTAssertNil(bunker.sideM)
        XCTAssertEqual(hole.score, 0)
        XCTAssertEqual(hole.putts, 0)
        XCTAssertEqual(hole.penaltyCount, 0)
    }

    func testBuildPrefersSharedTopoBitmapOverLegacyPrepJPEG() throws {
        let option = WatchCourseOption(
            globalId: 31669,
            name: "北京丽宫",
            holes: 18,
            teeBox: "Blue"
        )
        let package = try client.decodeCoursePackage(Data(
            #"{"roundId":"watch-topo-v4","course":{"globalId":31669,"name":"北京丽宫","teeBox":"Blue"},"holes":[{"number":1,"par":4,"yards":404,"geometryCoverage":"ready","sourceGlobalId":31669,"sourceLocalHole":1}]}"#.utf8
        ))
        let prep = try client.decodeCoursePrep(Data(
            #"{"globalId":31669,"clubs":[],"holes":[{"hole":1,"hazards":{},"map":{"image":"data:image/jpeg;base64,AQID","overlay":{"w":678,"h":1060,"route":[]}}}]}"#.utf8
        ))
        let sharedTopo = Data([9, 8, 7])

        let download = try WatchCourseTemplateBuilder.build(
            option: option,
            package: package,
            prepsByGlobalId: [31669: prep],
            topoImagesByGlobalId: [31669: [1: sharedTopo]],
            cachedAt: "2026-07-30T00:00:00Z"
        )

        XCTAssertEqual(download.images, [
            WatchCourseImage(globalId: 31669, hole: 1, data: sharedTopo)
        ])
    }

    func testBuildProjectsLightweightPrepRouteOntoSharedTopoWithoutLegacyMap() throws {
        let option = WatchCourseOption(
            globalId: 3881,
            name: "Cypress Point Club",
            holes: 18,
            teeBox: "championship"
        )
        let package = try client.decodeCoursePackage(Data(
            #"{"roundId":"watch-light-prep","course":{"globalId":3881,"name":"Cypress Point Club","teeBox":"championship"},"holes":[{"number":1,"par":5,"yards":407,"geometryCoverage":"ready","sourceGlobalId":3881,"sourceLocalHole":1}]}"#.utf8
        ))
        let prep = try client.decodeCoursePrep(Data(
            #"{"globalId":3881,"clubs":[],"holes":[{"hole":1,"par":5,"geometryCoverage":"ready","landing_m":220.0,"tee_club":"1W","route":[[0.0,0.0,0.0],[0.0,200.0,200.0],[30.0,320.0,323.7]],"hazards":{},"holeImageProjection":{"available":true,"widthPx":678,"heightPx":1060,"refs":[{"lat":36.58,"lon":-121.97,"px":100.0,"py":700.0},{"lat":36.58,"lon":-121.9686,"px":220.0,"py":700.0},{"lat":36.5811,"lon":-121.97,"px":100.0,"py":580.0}]}}]}"#.utf8
        ))
        let sharedTopo = Data([9, 8, 7])

        let download = try WatchCourseTemplateBuilder.build(
            option: option,
            package: package,
            prepsByGlobalId: [3881: prep],
            topoImagesByGlobalId: [3881: [1: sharedTopo]],
            cachedAt: "2026-08-01T00:00:00Z"
        )

        let hole = try XCTUnwrap(download.template.holeStates.first)
        let map = try XCTUnwrap(hole.holeMap)
        XCTAssertEqual(map.w, 678)
        XCTAssertEqual(map.h, 1060)
        XCTAssertEqual(map.you, [100, 700])
        XCTAssertEqual(map.pin, [130, 380])
        XCTAssertEqual(map.route ?? [], [
            [100, 700, 0],
            [100, 500, 200],
            [130, 380, 323.7],
        ])
        XCTAssertEqual(download.images, [
            WatchCourseImage(globalId: 3881, hole: 1, data: sharedTopo)
        ])
    }

    func testBuildUsesSelectedPackageTeeWhenRenderedPrepIsAbsent() throws {
        let option = WatchCourseOption(
            globalId: 31669,
            name: "北京丽宫",
            holes: 18,
            teeBox: "Blue",
            tees: ["Blue", "White"]
        )
        let package = try client.decodeCoursePackage(Data(
            #"{"roundId":"watch-fast-tee","course":{"globalId":31669,"name":"北京丽宫","teeBox":"Blue"},"holes":[{"number":1,"par":4,"yards":404,"geometryCoverage":"ready","sourceGlobalId":31669,"sourceLocalHole":1,"teeLatitude":40.0454995,"teeLongitude":116.5461531}]}"#.utf8
        ))

        let download = try WatchCourseTemplateBuilder.build(
            option: option,
            package: package,
            prepsByGlobalId: [:],
            cachedAt: "2026-07-29T00:00:00Z"
        )
        let hole = try XCTUnwrap(download.template.holeStates.first)

        XCTAssertEqual(try XCTUnwrap(hole.teeLatitude), 40.0454995, accuracy: 0.000_001)
        XCTAssertEqual(try XCTUnwrap(hole.teeLongitude), 116.5461531, accuracy: 0.000_001)
        XCTAssertEqual(
            try XCTUnwrap(download.template.option.latitude),
            40.0454995,
            accuracy: 0.000_001
        )
        XCTAssertEqual(
            try XCTUnwrap(download.template.option.longitude),
            116.5461531,
            accuracy: 0.000_001
        )
    }

    func testNewCourseTemplateKeepsSearchResultNameWhenPackageOnlyHasGenericIdName() throws {
        let option = WatchCourseOption(
            globalId: 31870,
            name: "Mission Hills ~ A",
            holes: 9,
            venueName: "Mission Hills",
            segmentLabel: "A",
            segmentHoles: 9,
            tees: ["blue", "white"]
        )
        let package = try client.decodeCoursePackage(Data(
            #"{"roundId":"watch-new-1","course":{"globalId":31870,"name":"Course 31870","teeBox":"blue"},"holes":[{"number":1,"par":4,"yards":null,"geometryCoverage":"missing","sourceGlobalId":31870,"sourceLocalHole":1}]}"#.utf8
        ))

        let download = try WatchCourseTemplateBuilder.build(
            option: option,
            package: package,
            prepsByGlobalId: [:],
            cachedAt: "2026-07-27T00:00:00Z"
        )

        XCTAssertEqual(download.template.courseName, "Mission Hills ~ A")
    }

    func testCachedTemplatePersistsAndCreatesANewRoundIdentityEachTime() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("watch-course-store-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = WatchCourseStore(directoryURL: directory)
        let option = WatchCourseOption(globalId: 31669, name: "北京丽宫", holes: 18, teeBox: "Blue")
        let template = WatchCourseTemplate(
            option: option,
            courseName: "北京丽宫",
            teeBox: "Blue",
            holeStates: [
                WatchRoundState(
                    roundId: "download-only", hole: 1, par: 4, distanceM: 369.4,
                    selectedClub: nil, score: 0, putts: 0, penaltyCount: 0,
                    caddieConfidence: "offline"
                )
            ],
            cachedAt: "2026-07-26T00:00:00Z"
        )

        try store.save(template)
        XCTAssertEqual(store.loadCourses(), [template])

        let first = try XCTUnwrap(store.course(globalId: 31669)).makeRound(roundId: "watch-round-a")
        let second = try XCTUnwrap(store.course(globalId: 31669)).makeRound(roundId: "watch-round-b")
        XCTAssertEqual(first.holeStates.first?.roundId, "watch-round-a")
        XCTAssertEqual(second.holeStates.first?.roundId, "watch-round-b")
        XCTAssertNotEqual(first.roundId, second.roundId)
    }

    func testRoundSetupSelectionKeepsExplicitTeeAndBackLoop() {
        let front = WatchCourseOption(
            globalId: 31669,
            name: "北京黑骑士 ~ A",
            holes: 9,
            teeBox: "Blue",
            venueName: "北京黑骑士",
            segmentLabel: "A",
            segmentHoles: 9,
            tees: ["Blue", "White"]
        )
        let back = WatchCourseOption(
            globalId: 31670,
            name: "北京黑骑士 ~ B",
            holes: 9,
            teeBox: "Blue",
            venueName: "北京黑骑士",
            segmentLabel: "B",
            segmentHoles: 9,
            tees: ["Blue", "White"]
        )

        let selection = WatchCourseSelection(front: front, back: back, teeBox: "White")

        XCTAssertEqual(selection.front.globalId, 31669)
        XCTAssertEqual(selection.back?.globalId, 31670)
        XCTAssertEqual(selection.teeBox, "White")
        XCTAssertEqual(selection.holeCount, 18)
    }

    @MainActor
    func testOfflineStartRejectsADifferentTeeOrHoleGroupInsteadOfUsingWrongCache() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("watch-course-selection-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = WatchCourseStore(directoryURL: directory)
        let front = WatchCourseOption(
            globalId: 31669,
            name: "北京黑骑士 ~ A",
            holes: 9,
            teeBox: "Blue",
            venueName: "北京黑骑士",
            segmentLabel: "A",
            segmentHoles: 9,
            tees: ["Blue", "White"]
        )
        let back = WatchCourseOption(
            globalId: 31670,
            name: "北京黑骑士 ~ B",
            holes: 9,
            teeBox: "Blue",
            venueName: "北京黑骑士",
            segmentLabel: "B",
            segmentHoles: 9,
            tees: ["Blue", "White"]
        )
        try store.save(WatchCourseTemplate(
            option: front,
            courseName: "北京黑骑士 ~ A",
            teeBox: "Blue",
            holeStates: [
                WatchRoundState(
                    roundId: "download-only", hole: 1, par: 4, distanceM: 369.4,
                    selectedClub: nil, score: 0, putts: 0, penaltyCount: 0,
                    caddieConfidence: "offline"
                )
            ],
            cachedAt: "2026-07-26T00:00:00Z"
        ))
        let library = WatchCourseLibrary(
            store: store,
            imageStore: WatchHoleImageStore(directoryURL: directory),
            makeRoundId: { "watch-offline-round" }
        )

        let prepared = await library.startCourse(
            WatchCourseSelection(front: front, back: back, teeBox: "White"),
            config: nil
        )

        XCTAssertNil(prepared)
        XCTAssertEqual(library.errorMessage, "这个洞组和发球台尚未下载，请联网后重试")
    }

    @MainActor
    func testCourseLibraryStartsACachedCourseWithoutPhoneOrNetworkConfig() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("watch-course-library-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = WatchCourseStore(directoryURL: directory)
        let option = WatchCourseOption(globalId: 31669, name: "北京丽宫", holes: 18, teeBox: "Blue")
        try store.save(WatchCourseTemplate(
            option: option,
            courseName: "北京丽宫",
            teeBox: "Blue",
            holeStates: [
                WatchRoundState(
                    roundId: "download-only", hole: 1, par: 4, distanceM: 369.4,
                    selectedClub: nil, score: 0, putts: 0, penaltyCount: 0,
                    caddieConfidence: "offline"
                )
            ],
            cachedAt: "2026-07-26T00:00:00Z"
        ))
        let library = WatchCourseLibrary(
            store: store,
            imageStore: WatchHoleImageStore(directoryURL: directory),
            makeRoundId: { "watch-offline-round" }
        )

        XCTAssertEqual(library.courses, [option])
        XCTAssertEqual(library.cachedCourseIds, [31669])
        let prepared = await library.startCourse(option, config: nil)
        XCTAssertEqual(prepared?.roundId, "watch-offline-round")
        XCTAssertEqual(prepared?.holeStates.first?.roundId, "watch-offline-round")
        XCTAssertNil(library.errorMessage)
    }
}
