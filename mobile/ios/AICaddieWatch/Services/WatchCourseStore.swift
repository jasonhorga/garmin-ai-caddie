import Foundation
import AICaddieDomain

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

    /// A composite 18-hole cache is stored under its front option, while active holes 10–18 carry
    /// the back option's Garmin globalId. Map recovery must resolve either authority without changing
    /// the stricter front-selection lookup used when a player starts a course.
    public func compositeCourse(containingGlobalId globalId: Int) -> WatchCourseTemplate? {
        loadCourses().first {
            $0.option.globalId == globalId || $0.backOption?.globalId == globalId
        }
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
        backOption: WatchCourseOption? = nil,
        package: WatchCoursePackage,
        prepsByGlobalId: [Int: WatchCoursePrepResponse],
        topoImagesByGlobalId: [Int: [Int: Data]] = [:],
        cachedAt: String
    ) throws -> WatchCourseDownload {
        guard !package.holes.isEmpty else { throw WatchCourseTemplateBuilderError.emptyPackage }

        var images: [WatchCourseImage] = []
        let states = package.holes.sorted { $0.number < $1.number }.map { hole -> WatchRoundState in
            let globalId = hole.sourceGlobalId ?? package.course.globalId
            let localHole = hole.sourceLocalHole ?? hole.number
            let prepResponse = prepsByGlobalId[globalId]
            let prep = prepResponse?.holes.first { $0.hole == localHole }
            let geometryRevision = prep?.geometryRevision ?? hole.geometryRevision
            let distanceM = hole.yards.map { Double($0) * 0.9144 }
            let projection = watchProjection(prep?.holeImageProjection)
            let overlay = prep.flatMap { prepOverlay($0, projection: projection) }
            let holeMap = overlay.flatMap {
                makeHoleMap(
                    $0,
                    landingM: prep?.landingM,
                    greenOutline: prep?.greenOutline
                )
            }
            let routeDistanceM = overlay?.route.last.flatMap { $0.count >= 3 ? $0[2] : nil }
            let tee = packageTeeCoordinate(hole) ?? teeCoordinate(holeMap: holeMap, projection: projection)
            let green = prep?.greenDistances?.available == true ? prep?.greenDistances : nil
            let deltaM = prep?.playsLike?.available == true ? prep?.playsLike?.deltaM : nil
            let clubs = (prepResponse?.clubs ?? []).map {
                WatchClubOption(clubName: $0.name, medianM: $0.m, source: "course-prep")
            }
            let preparedOptions = routeDistanceM.map {
                preparedCaddieOptions(
                    clubs: clubs,
                    suggestedClub: prep?.teeClub,
                    routeDistanceM: $0,
                    landingM: prep?.landingM
                )
            } ?? []
            let preparedNote = preparedTargetNote(
                routeDistanceM: routeDistanceM,
                landingM: prep?.landingM
            )

            let resolvedImageData: Data?
            if let data = topoImagesByGlobalId[globalId]?[localHole],
               WatchHoleImageStore.isValidImageData(data) {
                resolvedImageData = data
            } else if let image = prep?.map?.image,
                      let data = imageData(from: image),
                      WatchHoleImageStore.isValidImageData(data) {
                resolvedImageData = data
            } else {
                resolvedImageData = nil
            }
            if let resolvedImageData {
                images.append(WatchCourseImage(
                    globalId: globalId,
                    hole: hole.number,
                    data: resolvedImageData,
                    geometryRevision: geometryRevision
                ))
            }

            let reportedCoverage = prep?.geometryCoverage ?? hole.geometryCoverage
            // A server "ready" flag is not sufficient offline authority. Without both a decodable
            // raster and projected route/map facts the Watch cannot construct the production hole
            // geometry, so retain the honest fallback but keep recovery active.
            let effectiveCoverage = reportedCoverage?.caseInsensitiveCompare("ready") == .orderedSame
                && (resolvedImageData == nil || holeMap == nil)
                ? "partial"
                : reportedCoverage

            return WatchRoundState(
                roundId: package.roundId,
                hole: hole.number,
                par: hole.par,
                distanceM: distanceM,
                teeLatitude: tee?.latitude,
                teeLongitude: tee?.longitude,
                targetNote: preparedNote,
                suggestedClub: prep?.teeClub,
                selectedClub: nil,
                availableClubs: clubs,
                strategyMode: preparedOptions.isEmpty ? nil : "stock",
                offlineOptionId: preparedOptions.isEmpty ? nil : "stock",
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
                playsLikeDistanceM: WatchUnits.playsLikeMetres(
                    distanceMetres: distanceM,
                    elevationDeltaMetres: deltaM
                ),
                elevationDeltaM: deltaM,
                geometryCoverage: effectiveCoverage,
                geometryRevision: effectiveCoverage?.caseInsensitiveCompare("ready") == .orderedSame
                    ? geometryRevision
                    : nil,
                caddieOptions: preparedOptions,
                // CourseView's fast package can omit hazards that precise prodgeometry later
                // reveals.  Do not turn that provisional subset into a Watch hazard list.
                hazards: effectiveCoverage?.caseInsensitiveCompare("ready") == .orderedSame
                    ? watchHazards(prep?.hazards, route: overlay?.route)
                    : [],
                score: 0,
                putts: 0,
                penaltyCount: 0,
                caddieConfidence: "offline"
            )
        }

        let locatedOption = locatedCourseOption(option, from: states)
        let locatedBackOption = backOption.map { locatedCourseOption($0, from: states) }
        let template = WatchCourseTemplate(
            option: locatedOption,
            backOption: locatedBackOption,
            courseName: resolvedCourseName(package: package, option: option),
            teeBox: package.course.teeBox,
            holeStates: states,
            cachedAt: cachedAt
        )
        return WatchCourseDownload(template: template, images: images)
    }

    /// Build the three on-watch route choices from facts already downloaded for offline play: the
    /// player's measured bag, the prepared Tee club and this hole's real route length. These are
    /// deterministic planning choices, not success probabilities or fabricated shot dispersion.
    static func preparedCaddieOptions(
        clubs: [WatchClubOption],
        suggestedClub: String?,
        routeDistanceM: Double,
        landingM: Double?
    ) -> [WatchCaddieOption] {
        let usable = clubs
            .filter { option in
                guard let carry = option.medianM else { return false }
                return carry.isFinite && carry > 0
            }
            .sorted { ($0.medianM ?? 0) > ($1.medianM ?? 0) }
        guard routeDistanceM.isFinite, routeDistanceM > 0, !usable.isEmpty else { return [] }

        let normalizedSuggestion = suggestedClub?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        let preparedCarry = landingM.flatMap { value in
            value.isFinite && value > 0 ? min(value, routeDistanceM) : nil
        }
        let suggestedIndex: Int?
        if let normalizedSuggestion, !normalizedSuggestion.isEmpty {
            suggestedIndex = usable.firstIndex { option in
                option.clubName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
                    == normalizedSuggestion
            }
        } else {
            suggestedIndex = nil
        }
        let targetCarry = preparedCarry ?? routeDistanceM * 0.55
        let nearestIndex = usable.indices.min { lhs, rhs in
            let lhsDelta = abs((usable[lhs].medianM ?? 0) - targetCarry)
            let rhsDelta = abs((usable[rhs].medianM ?? 0) - targetCarry)
            return lhsDelta < rhsDelta
        }
        let stockIndex = suggestedIndex ?? nearestIndex ?? usable.startIndex

        let safeIndex = min(stockIndex + 1, usable.index(before: usable.endIndex))
        let attackIndex = max(stockIndex - 1, usable.startIndex)
        let variants: [(id: String, label: String, first: WatchClubOption, bias: Double)] = [
            // Match iPhone: lead with the selected recommendation, then compare the lower-risk
            // alternative before the aggressive route.
            ("stock", "推荐", usable[stockIndex], 0.92),
            ("safe", "保守", usable[safeIndex], 0.84),
            ("attack", "进攻", usable[attackIndex], 1.05),
        ]

        return variants.map { variant in
            let plan = preparedPlan(
                first: variant.first,
                clubs: usable,
                routeDistanceM: routeDistanceM,
                completionBias: variant.bias
            )
            return WatchCaddieOption(
                optionId: variant.id,
                label: variant.label,
                clubName: variant.first.clubName,
                carryM: variant.first.medianM,
                plan: plan,
                confidence: "offline"
            )
        }
    }

    private static func preparedPlan(
        first: WatchClubOption,
        clubs: [WatchClubOption],
        routeDistanceM: Double,
        completionBias: Double
    ) -> [WatchCaddiePlanStep] {
        var remaining = routeDistanceM
        var selected = first
        var plan: [WatchCaddiePlanStep] = []
        // Driver is a Tee-shot choice, never a follow-up recommendation. Without this separate
        // tail bag a long Par 5 could independently reconstruct 1W → 1W on Watch even though the
        // server and iPhone had already excluded that impossible route.
        let followUpClubs = clubs.filter { !isDriver($0.clubName) }

        while remaining > 25, plan.count < 3, let carry = selected.medianM {
            plan.append(WatchCaddiePlanStep(clubName: selected.clubName, carryM: carry))
            remaining -= carry
            guard remaining > 25, !followUpClubs.isEmpty else { break }
            let target = remaining * completionBias
            selected = followUpClubs.min {
                abs(($0.medianM ?? 0) - target) < abs(($1.medianM ?? 0) - target)
            } ?? selected
        }
        return plan
    }

    private static func isDriver(_ raw: String) -> Bool {
        let key = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: " ", with: "")
        return ["driver", "d", "dr", "1d", "1w", "一号木", "一号木杆"].contains(key)
    }

    private static func preparedTargetNote(
        routeDistanceM: Double?,
        landingM: Double?
    ) -> String? {
        guard let routeDistanceM, routeDistanceM.isFinite, routeDistanceM > 0,
              let landingM, landingM.isFinite, landingM > 0 else { return nil }
        let remainingM = max(routeDistanceM - min(landingM, routeDistanceM), 0)
        guard remainingM > 25 else { return "攻果岭" }
        return "推进 · 留\(WatchUnits.yards(remainingM))"
    }

    private static func locatedCourseOption(
        _ option: WatchCourseOption,
        from states: [WatchRoundState]
    ) -> WatchCourseOption {
        let tee = states.first {
            $0.globalId == option.globalId && $0.teeLatitude != nil && $0.teeLongitude != nil
        }
        return option.withFallbackLocation(
            latitude: tee?.teeLatitude,
            longitude: tee?.teeLongitude
        )
    }

    private static func resolvedCourseName(
        package: WatchCoursePackage,
        option: WatchCourseOption
    ) -> String {
        let packageName = package.course.name.trimmingCharacters(in: .whitespacesAndNewlines)
        let genericName = "Course \(package.course.globalId)"
        if packageName.caseInsensitiveCompare(genericName) == .orderedSame {
            return option.name
        }
        return package.course.name
    }

    private static func watchProjection(_ value: WatchCoursePrepProjection?) -> WatchHoleImageProjection? {
        guard let value, value.available, let refs = value.refs, refs.count >= 3 else { return nil }
        return WatchHoleImageProjection(widthPx: value.widthPx, heightPx: value.heightPx, refs: refs)
    }

    private static func packageTeeCoordinate(
        _ hole: WatchCoursePackageHole
    ) -> (latitude: Double, longitude: Double)? {
        guard let latitude = hole.teeLatitude,
              let longitude = hole.teeLongitude,
              latitude.isFinite, (-90...90).contains(latitude),
              longitude.isFinite, (-180...180).contains(longitude) else { return nil }
        return (latitude, longitude)
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
        landingM: Double?,
        greenOutline: WatchCoursePrepGreenOutline?
    ) -> WatchHoleMap? {
        let route = overlay.route
        guard route.count >= 2,
              let first = route.first, first.count >= 3,
              let last = route.last, last.count >= 3,
              last[2] > 0 else { return nil }
        let total = last[2]
        // Keep the legacy non-optional anchor decodable, but never treat the 60% fallback as advice.
        // WatchRoundContainerView rebuilds every visible prepared target from an explicit option carry.
        let landing = min(max(landingM ?? total * 0.6, 0), total)
        return WatchHoleMap(
            w: overlay.w,
            h: overlay.h,
            you: [first[0], first[1]],
            pin: [last[0], last[1]],
            layup: interpolate(route, atM: landing),
            apex: interpolate(route, atM: landing * 0.5),
            greenCtrl: interpolate(route, atM: landing + (total - landing) * 0.5),
            route: route,
            greenOutline: greenOutline?.available == true ? greenOutline?.pointsPx : nil
        )
    }

    private static func prepOverlay(
        _ prep: WatchCoursePrepHole,
        projection: WatchHoleImageProjection?
    ) -> WatchCoursePrepOverlay? {
        if let overlay = prep.map?.overlay { return overlay }
        guard let width = projection?.widthPx, width > 0,
              let height = projection?.heightPx, height > 0,
              let refs = projection?.refs, refs.count >= 3,
              prep.route.count >= 2 else { return nil }

        // The lightweight prep contract defines refs[0...2] as local (0,0), (120,0), and
        // (0,120) metres in the exact affine frame shared by /topo.png. Reconstruct only the
        // route pixels here; the expensive legacy JPEG is neither rendered nor downloaded.
        let origin = refs[0]
        let xRef = refs[1]
        let yRef = refs[2]
        var pixelRoute: [[Double]] = []
        for row in prep.route {
            guard row.count >= 3 else { return nil }
            let localX = row[0]
            let localY = row[1]
            let cumulative = row[2]
            let x = origin.px
                + (localX / 120) * (xRef.px - origin.px)
                + (localY / 120) * (yRef.px - origin.px)
            let y = origin.py
                + (localX / 120) * (xRef.py - origin.py)
                + (localY / 120) * (yRef.py - origin.py)
            guard x.isFinite, y.isFinite, cumulative.isFinite else { return nil }
            pixelRoute.append([
                (x * 10).rounded() / 10,
                (y * 10).rounded() / 10,
                cumulative,
            ])
        }
        return WatchCoursePrepOverlay(w: width, h: height, route: pixelRoute)
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

    private static func watchHazards(
        _ value: WatchCoursePrepHazards?,
        route: [[Double]]?
    ) -> [WatchHazard] {
        guard let value else { return [] }
        var result: [WatchHazard] = []
        let bunkerDetails = value.details
            .filter { $0.kind == "bunker" }
            .sorted { $0.frontRouteM < $1.frontRouteM }
        if !bunkerDetails.isEmpty {
            for detail in bunkerDetails {
                result.append(WatchHazard(
                    kind: "bunker",
                    label: HazardDisplayNaming.label(
                        kind: "bunker",
                        frontRouteM: detail.frontRouteM,
                        frontPx: detail.frontPx,
                        sideM: detail.sideM,
                        route: route
                    ),
                    startM: detail.frontRouteM,
                    endM: detail.backRouteM,
                    frontDistanceM: detail.frontM,
                    backDistanceM: detail.backM,
                    frontPx: detail.frontPx,
                    backPx: detail.backPx
                ))
            }
        } else {
            let bunkers = value.bunkers.sorted { ($0.first ?? 0) < ($1.first ?? 0) }
            for interval in bunkers {
                result.append(WatchHazard(
                    kind: "bunker",
                    label: HazardDisplayNaming.legacyLabel(
                        kind: "bunker", interval: interval, route: route
                    ),
                    startM: interval.first,
                    sideM: interval.count >= 2 ? interval[1] : nil
                ))
            }
        }
        let waterDetails = value.details
            .filter { $0.kind == "water" }
            .sorted { $0.frontRouteM < $1.frontRouteM }
        if !waterDetails.isEmpty {
            for detail in waterDetails {
                result.append(WatchHazard(
                    kind: "water",
                    label: HazardDisplayNaming.label(
                        kind: "water",
                        frontRouteM: detail.frontRouteM,
                        frontPx: detail.frontPx,
                        sideM: detail.sideM,
                        route: route
                    ),
                    startM: detail.frontRouteM,
                    endM: detail.backRouteM,
                    frontDistanceM: detail.frontM,
                    backDistanceM: detail.backM,
                    frontPx: detail.frontPx,
                    backPx: detail.backPx
                ))
            }
        } else {
            let water = value.waterCarry.sorted { ($0.first ?? 0) < ($1.first ?? 0) }
            for interval in water {
                result.append(WatchHazard(
                    kind: "water",
                    label: HazardDisplayNaming.legacyLabel(
                        kind: "water", interval: interval, route: route
                    ),
                    startM: interval.first,
                    endM: interval.count >= 2 ? interval[1] : nil
                ))
            }
        }
        return result
    }

    private static func imageData(from dataURI: String) -> Data? {
        let parts = dataURI.split(separator: ",", maxSplits: 1, omittingEmptySubsequences: false)
        guard parts.count == 2, parts[0].contains(";base64") else { return nil }
        return Data(base64Encoded: String(parts[1]), options: .ignoreUnknownCharacters)
    }
}
