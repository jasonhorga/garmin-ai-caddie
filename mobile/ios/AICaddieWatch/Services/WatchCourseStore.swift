import Foundation

public final class WatchCourseStore {
    private let fileURL: URL
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    public init(directoryURL: URL? = nil) {
        let directory = directoryURL
            ?? FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("watch-courses", isDirectory: true)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        fileURL = directory.appendingPathComponent("courses.json")
    }

    public func loadCourses() -> [WatchCourseTemplate] {
        guard let data = try? Data(contentsOf: fileURL) else { return [] }
        return (try? decoder.decode([WatchCourseTemplate].self, from: data)) ?? []
    }

    public func course(globalId: Int) -> WatchCourseTemplate? {
        loadCourses().first { $0.option.globalId == globalId }
    }

    public func save(_ course: WatchCourseTemplate) throws {
        var courses = loadCourses()
        if let index = courses.firstIndex(where: { $0.option.globalId == course.option.globalId }) {
            courses[index] = course
        } else {
            courses.append(course)
        }
        try encoder.encode(courses).write(to: fileURL, options: .atomic)
    }
}

public enum WatchCourseTemplateBuilderError: Error {
    case emptyPackage
}

public enum WatchCourseTemplateBuilder {
    public static func build(
        option: WatchCourseOption,
        package: WatchCoursePackage,
        prepsByGlobalId: [Int: WatchCoursePrepResponse],
        cachedAt: String
    ) throws -> WatchCourseDownload {
        guard !package.holes.isEmpty else { throw WatchCourseTemplateBuilderError.emptyPackage }

        var images: [WatchCourseImage] = []
        let states = package.holes.sorted { $0.number < $1.number }.map { hole -> WatchRoundState in
            let globalId = hole.sourceGlobalId ?? package.course.globalId
            let localHole = hole.sourceLocalHole ?? hole.number
            let prepResponse = prepsByGlobalId[globalId]
            let prep = prepResponse?.holes.first { $0.hole == localHole }
            let distanceM = hole.yards.map { Double($0) * 0.9144 }
            let projection = watchProjection(prep?.holeImageProjection)
            let holeMap = prep?.map.flatMap { makeHoleMap($0.overlay, landingM: prep?.landingM) }
            let tee = teeCoordinate(holeMap: holeMap, projection: projection)
            let green = prep?.greenDistances?.available == true ? prep?.greenDistances : nil
            let deltaM = prep?.playsLike?.available == true ? prep?.playsLike?.deltaM : nil
            let clubs = (prepResponse?.clubs ?? []).map {
                WatchClubOption(clubName: $0.name, medianM: $0.m, source: "course-prep")
            }

            if let image = prep?.map?.image, let data = imageData(from: image) {
                images.append(WatchCourseImage(globalId: globalId, hole: hole.number, data: data))
            }

            return WatchRoundState(
                roundId: package.roundId,
                hole: hole.number,
                par: hole.par,
                distanceM: distanceM,
                teeLatitude: tee?.latitude,
                teeLongitude: tee?.longitude,
                suggestedClub: prep?.teeClub,
                selectedClub: nil,
                availableClubs: clubs,
                frontGreenM: green?.frontM,
                centerGreenM: green?.middleM,
                backGreenM: green?.backM,
                frontGreenLat: green?.frontLat,
                frontGreenLon: green?.frontLon,
                centerGreenLat: green?.middleLat,
                centerGreenLon: green?.middleLon,
                backGreenLat: green?.backLat,
                backGreenLon: green?.backLon,
                holeImageProjection: projection,
                globalId: globalId,
                holeMap: holeMap,
                playsLikeDistanceM: deltaM.flatMap { delta in distanceM.map { $0 + delta } },
                elevationDeltaM: deltaM,
                geometryCoverage: prep?.geometryCoverage ?? hole.geometryCoverage,
                hazards: watchHazards(prep?.hazards),
                score: 0,
                putts: 0,
                penaltyCount: 0,
                caddieConfidence: "offline"
            )
        }

        let template = WatchCourseTemplate(
            option: option,
            courseName: package.course.name,
            teeBox: package.course.teeBox,
            holeStates: states,
            cachedAt: cachedAt
        )
        return WatchCourseDownload(template: template, images: images)
    }

    private static func watchProjection(_ value: WatchCoursePrepProjection?) -> WatchHoleImageProjection? {
        guard let value, value.available, let refs = value.refs, refs.count >= 3 else { return nil }
        return WatchHoleImageProjection(widthPx: value.widthPx, heightPx: value.heightPx, refs: refs)
    }

    private static func teeCoordinate(
        holeMap: WatchHoleMap?,
        projection: WatchHoleImageProjection?
    ) -> (latitude: Double, longitude: Double)? {
        guard let you = holeMap?.you, you.count >= 2,
              let refs = projection?.refs, refs.count >= 3 else { return nil }
        let o = refs[0], r1 = refs[1], r2 = refs[2]
        let a = r1.px - o.px
        let b = r2.px - o.px
        let c = r1.py - o.py
        let d = r2.py - o.py
        let det = a * d - b * c
        guard abs(det) > 1e-12 else { return nil }
        let dx = you[0] - o.px
        let dy = you[1] - o.py
        let s = (dx * d - b * dy) / det
        let t = (a * dy - dx * c) / det
        let latitude = o.lat + s * (r1.lat - o.lat) + t * (r2.lat - o.lat)
        let longitude = o.lon + s * (r1.lon - o.lon) + t * (r2.lon - o.lon)
        guard latitude.isFinite, (-90...90).contains(latitude),
              longitude.isFinite, (-180...180).contains(longitude) else { return nil }
        return (latitude, longitude)
    }

    private static func makeHoleMap(
        _ overlay: WatchCoursePrepOverlay,
        landingM: Double?
    ) -> WatchHoleMap? {
        let route = overlay.route
        guard route.count >= 2,
              let first = route.first, first.count >= 3,
              let last = route.last, last.count >= 3,
              last[2] > 0 else { return nil }
        let total = last[2]
        let landing = min(max(landingM ?? total * 0.6, 0), total)
        return WatchHoleMap(
            w: overlay.w,
            h: overlay.h,
            you: [first[0], first[1]],
            pin: [last[0], last[1]],
            layup: interpolate(route, atM: landing),
            apex: interpolate(route, atM: landing * 0.5),
            greenCtrl: interpolate(route, atM: landing + (total - landing) * 0.5)
        )
    }

    private static func interpolate(_ route: [[Double]], atM: Double) -> [Double] {
        guard let first = route.first, first.count >= 3 else { return [0, 0] }
        if atM <= first[2] { return [first[0], first[1]] }
        for index in 0..<(route.count - 1) {
            let start = route[index]
            let end = route[index + 1]
            guard start.count >= 3, end.count >= 3 else { continue }
            if atM <= end[2] {
                let span = end[2] - start[2]
                let fraction = span > 0 ? (atM - start[2]) / span : 0
                return [
                    start[0] + (end[0] - start[0]) * fraction,
                    start[1] + (end[1] - start[1]) * fraction,
                ]
            }
        }
        guard let last = route.last, last.count >= 2 else { return [0, 0] }
        return [last[0], last[1]]
    }

    private static func watchHazards(_ value: WatchCoursePrepHazards?) -> [WatchHazard] {
        guard let value else { return [] }
        var result: [WatchHazard] = []
        let bunkers = value.bunkers.sorted { ($0.first ?? 0) < ($1.first ?? 0) }
        for (index, interval) in bunkers.enumerated() {
            result.append(WatchHazard(
                kind: "bunker",
                label: bunkers.count > 1 ? "沙坑 \(index + 1)" : "沙坑",
                startM: interval.first,
                endM: interval.count >= 2 ? interval[1] : nil
            ))
        }
        let water = value.waterCarry.sorted { ($0.first ?? 0) < ($1.first ?? 0) }
        for (index, interval) in water.enumerated() {
            result.append(WatchHazard(
                kind: "water",
                label: water.count > 1 ? "水域 \(index + 1)" : "水域",
                startM: interval.first,
                endM: interval.count >= 2 ? interval[1] : nil
            ))
        }
        return result
    }

    private static func imageData(from dataURI: String) -> Data? {
        let parts = dataURI.split(separator: ",", maxSplits: 1, omittingEmptySubsequences: false)
        guard parts.count == 2, parts[0].contains(";base64") else { return nil }
        return Data(base64Encoded: String(parts[1]), options: .ignoreUnknownCharacters)
    }
}
