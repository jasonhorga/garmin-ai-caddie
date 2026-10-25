import CoreGraphics
import CoreLocation
import Foundation

/// The Garmin fallback image contract returned by
/// `/api/v2/courses/{gid}/holes/{hole}/garmin-raster`.
///
/// Garmin's raster has its own pixel frame. Keeping its projection beside the URL means every
/// live overlay can use the same geo facts while the precise CourseView image is still pending.
public struct GarminRasterResponse: Codable, Equatable {
    public let available: Bool
    public let imageUrl: String?
    public let projection: GarminRasterProjection?
    public let mode: String
    public let reason: String?

    public init(
        available: Bool,
        imageUrl: String? = nil,
        projection: GarminRasterProjection? = nil,
        mode: String = "none",
        reason: String? = nil
    ) {
        self.available = available
        self.imageUrl = imageUrl
        self.projection = projection
        self.mode = mode
        self.reason = reason
    }

    public var isUsable: Bool {
        available && projection?.isUsable == true
    }

    /// An image can still be useful as a background when Garmin could not provide registration
    /// anchors. Callers must keep all geo overlays disabled in that case.
    public var hasDisplayableImage: Bool {
        imageUrl?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
    }

    /// Whether the live hole's descriptor recovery may stop. A package raster is only a visual
    /// first frame: keep retrying metadata until the image and its geographic projection are both
    /// usable, otherwise target placement and route overlays would remain disabled forever on a
    /// cold course. An open image-version conflict keeps recovery running as well.
    static func descriptorRecoveryIsSettled(
        _ raster: GarminRasterResponse?, versionConflictURL: URL?
    ) -> Bool {
        raster?.isUsable == true && versionConflictURL == nil
    }
}

/// Projection shape intentionally mirrors `holeImageProjection` so the same affine math can be
/// used for GPS, Touch Target, flag and route points on either displayed image.
public struct GarminRasterProjection: Codable, Equatable {
    /// Kept for compatibility with the earlier 452 payload, which encoded an explicit
    /// `{"available": false}` projection instead of using `null`.
    public let available: Bool
    public let widthPx: Int
    public let heightPx: Int
    public let refs: [CoursePrepProjectionRef]

    public init(
        available: Bool = true,
        widthPx: Int,
        heightPx: Int,
        refs: [CoursePrepProjectionRef]
    ) {
        self.available = available
        self.widthPx = widthPx
        self.heightPx = heightPx
        self.refs = refs
    }

    private enum CodingKeys: String, CodingKey { case widthPx, heightPx, refs, available }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        available = try container.decodeIfPresent(Bool.self, forKey: .available) ?? true
        widthPx = try container.decodeIfPresent(Int.self, forKey: .widthPx) ?? 0
        heightPx = try container.decodeIfPresent(Int.self, forKey: .heightPx) ?? 0
        refs = try container.decodeIfPresent([CoursePrepProjectionRef].self, forKey: .refs) ?? []
    }

    public var isUsable: Bool {
        available && widthPx > 0 && heightPx > 0 && refs.count >= 3 && refs.allSatisfy {
            $0.lat.isFinite && $0.lon.isFinite && $0.px.isFinite && $0.py.isFinite
        }
    }

    public var coursePrepProjection: CoursePrepHoleImageProjection {
        CoursePrepHoleImageProjection(
            available: isUsable,
            widthPx: widthPx,
            heightPx: heightPx,
            refs: refs
        )
    }
}

/// `CoursePrepHoleImageProjection` is defined in the shared model with optional dimensions and
/// refs. Keep the validation explicit in one place; there is no native `isUsable` member on that
/// type in the shared model.
public extension CoursePrepHoleImageProjection {
    var isUsable: Bool {
        guard available,
              let widthPx,
              let heightPx,
              widthPx > 0,
              heightPx > 0,
              let refs,
              refs.count >= 3 else { return false }
        return refs.allSatisfy {
            $0.lat.isFinite && $0.lon.isFinite && $0.px.isFinite && $0.py.isFinite
        }
    }
}

/// Pure projection helpers shared by the live map and the native acceptance tests. Reference
/// points describe an affine geo → pixel transform in a small hole-local frame; solving relative
/// to ref[0] avoids the conditioning problems of absolute WGS84 values.
public enum GarminRasterProjectionMath {
    public static func projectToPixel(
        latitude: Double,
        longitude: Double,
        projection: CoursePrepHoleImageProjection
    ) -> CGPoint? {
        guard projection.available,
              let refs = projection.refs,
              refs.count >= 3 else { return nil }
        return projectToPixel(
            latitude: latitude,
            longitude: longitude,
            refs: refs
        )
    }

    public static func projectToPixel(
        latitude: Double,
        longitude: Double,
        refs: [CoursePrepProjectionRef]
    ) -> CGPoint? {
        guard refs.count >= 3,
              latitude.isFinite,
              longitude.isFinite else { return nil }
        let origin = refs[0]
        let x = refs[1]
        let y = refs[2]
        let a = x.lon - origin.lon
        let b = y.lon - origin.lon
        let c = x.lat - origin.lat
        let d = y.lat - origin.lat
        let determinant = a * d - b * c
        guard determinant.isFinite, abs(determinant) > 1e-12 else { return nil }
        let deltaLon = longitude - origin.lon
        let deltaLat = latitude - origin.lat
        let s = (deltaLon * d - b * deltaLat) / determinant
        let t = (a * deltaLat - deltaLon * c) / determinant
        let px = origin.px + s * (x.px - origin.px) + t * (y.px - origin.px)
        let py = origin.py + s * (x.py - origin.py) + t * (y.py - origin.py)
        guard px.isFinite, py.isFinite else { return nil }
        return CGPoint(x: px, y: py)
    }

    public static func projectFromPixel(
        _ pixel: CGPoint,
        projection: CoursePrepHoleImageProjection
    ) -> CLLocationCoordinate2D? {
        guard projection.available,
              let refs = projection.refs,
              refs.count >= 3 else { return nil }
        return projectFromPixel(pixel, refs: refs)
    }

    public static func projectFromPixel(
        _ pixel: CGPoint,
        refs: [CoursePrepProjectionRef]
    ) -> CLLocationCoordinate2D? {
        guard refs.count >= 3,
              pixel.x.isFinite,
              pixel.y.isFinite else { return nil }
        let origin = refs[0]
        let x = refs[1]
        let y = refs[2]
        let pxA = x.px - origin.px
        let pxB = y.px - origin.px
        let pyA = x.py - origin.py
        let pyB = y.py - origin.py
        let determinant = pxA * pyB - pxB * pyA
        guard determinant.isFinite, abs(determinant) > 1e-12 else { return nil }
        let deltaPx = pixel.x - origin.px
        let deltaPy = pixel.y - origin.py
        let s = (deltaPx * pyB - pxB * deltaPy) / determinant
        let t = (pxA * deltaPy - deltaPx * pyA) / determinant
        let latitude = origin.lat + s * (x.lat - origin.lat) + t * (y.lat - origin.lat)
        let longitude = origin.lon + s * (x.lon - origin.lon) + t * (y.lon - origin.lon)
        guard latitude.isFinite, longitude.isFinite else { return nil }
        return CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }

    /// Move one point from the precise/topo pixel frame into Garmin's frame through geographic
    /// coordinates. Returning nil keeps callers from drawing an unregistered overlay.
    public static func remap(
        pixel: CGPoint,
        from source: CoursePrepHoleImageProjection,
        to destination: CoursePrepHoleImageProjection
    ) -> CGPoint? {
        guard let coordinate = projectFromPixel(pixel, projection: source) else { return nil }
        return projectToPixel(
            latitude: coordinate.latitude,
            longitude: coordinate.longitude,
            projection: destination
        )
    }

    public static func remapOverlay(
        _ overlay: CoursePrepOverlay,
        from source: CoursePrepHoleImageProjection?,
        to destination: CoursePrepHoleImageProjection
    ) -> CoursePrepOverlay? {
        guard let source,
              source.isUsable,
              destination.isUsable,
              let destinationWidth = destination.widthPx,
              let destinationHeight = destination.heightPx else { return nil }
        var route: [[Double]] = []
        route.reserveCapacity(overlay.route.count)
        for row in overlay.route {
            guard row.count >= 2,
                  row[0].isFinite,
                  row[1].isFinite,
                  let point = remap(
                      pixel: CGPoint(x: row[0], y: row[1]),
                      from: source,
                      to: destination
                  ) else { return nil }
            var result = row
            result[0] = point.x
            result[1] = point.y
            route.append(result)
        }
        let sourcePPM = overlay.ppm
        let destinationPPM = averagePixelsPerMetre(for: destination, source: source)
        return CoursePrepOverlay(
            w: destinationWidth,
            h: destinationHeight,
            ppm: destinationPPM.map { sourcePPM * $0 } ?? sourcePPM,
            ln: overlay.ln,
            route: route
        )
    }

    /// Estimate the ground scale change between two projections from their first two reference
    /// points. This preserves pixel-distance yardage while switching image frames.
    private static func averagePixelsPerMetre(
        for destination: CoursePrepHoleImageProjection,
        source: CoursePrepHoleImageProjection
    ) -> Double? {
        guard let sourceRefs = source.refs,
              let destinationRefs = destination.refs,
              sourceRefs.count >= 3,
              destinationRefs.count >= 3 else { return nil }
        func pixelsPerMetre(_ refs: [CoursePrepProjectionRef]) -> Double? {
            let earthRadius = 6_371_008.8
            let origin = refs[0]
            let latitudeScale = earthRadius * .pi / 180
            let longitudeScale = latitudeScale * cos(origin.lat * .pi / 180)
            // Fit the two pixel-axis vectors against local east/north metres. This uses each
            // projection's own references, so the two payloads may sample different WGS84 points.
            let east1 = (refs[1].lon - origin.lon) * longitudeScale
            let north1 = (refs[1].lat - origin.lat) * latitudeScale
            let east2 = (refs[2].lon - origin.lon) * longitudeScale
            let north2 = (refs[2].lat - origin.lat) * latitudeScale
            let determinant = east1 * north2 - east2 * north1
            guard determinant.isFinite, abs(determinant) > 1e-9 else { return nil }
            let pixel1 = CGPoint(x: refs[1].px - origin.px, y: refs[1].py - origin.py)
            let pixel2 = CGPoint(x: refs[2].px - origin.px, y: refs[2].py - origin.py)
            // Invert the metre-reference matrix to obtain pixels per metre for east and north.
            let eastPixel = CGPoint(
                x: (pixel1.x * north2 - pixel2.x * north1) / determinant,
                y: (pixel1.y * north2 - pixel2.y * north1) / determinant
            )
            let northPixel = CGPoint(
                x: (east1 * pixel2.x - east2 * pixel1.x) / determinant,
                y: (east1 * pixel2.y - east2 * pixel1.y) / determinant
            )
            let average = (hypot(eastPixel.x, eastPixel.y) + hypot(northPixel.x, northPixel.y)) / 2
            return average.isFinite && average > 0 ? average : nil
        }
        guard let sourceScale = pixelsPerMetre(sourceRefs),
              let destinationScale = pixelsPerMetre(destinationRefs) else { return nil }
        guard sourceScale.isFinite, sourceScale > 0,
              destinationScale.isFinite, destinationScale > 0 else { return nil }
        // `overlay.ppm` is the source frame's pixels-per-metre. Apply the ratio of the two
        // independently fitted geo→pixel transforms; the three refs need not be the same
        // geographic samples in the 452 response.
        return (destinationScale / sourceScale)
    }
}

/// Pure viewport transfer used when the Garmin bitmap is replaced by the downloaded precise topo.
/// It preserves the geographic point at the hero's centre and keeps the same on-screen ground
/// scale, then callers remap target/flag pixels with `remap`.
public enum GarminRasterViewportTransfer {
    public static func transfer(
        viewportSize: CGSize,
        sourceFrame: CGRect,
        destinationFrame: CGRect,
        sourceOverlay: CoursePrepOverlay,
        destinationOverlay: CoursePrepOverlay,
        sourceProjection: CoursePrepHoleImageProjection,
        destinationProjection: CoursePrepHoleImageProjection,
        scale: CGFloat,
        offset: CGSize
    ) -> (scale: CGFloat, offset: CGSize)? {
        guard viewportSize.width > 0, viewportSize.height > 0,
              sourceFrame.width > 0, sourceFrame.height > 0,
              destinationFrame.width > 0, destinationFrame.height > 0,
              sourceOverlay.w > 0, sourceOverlay.h > 0,
              destinationOverlay.w > 0, destinationOverlay.h > 0,
              scale.isFinite, scale > 0 else { return nil }
        let center = CGPoint(x: viewportSize.width / 2, y: viewportSize.height / 2)
        let sourceBase = CGPoint(
            x: center.x + (center.x - center.x - offset.width) / scale,
            y: center.y + (center.y - center.y - offset.height) / scale
        )
        let sourcePixel = CGPoint(
            x: (sourceBase.x - sourceFrame.minX) / sourceFrame.width * CGFloat(sourceOverlay.w),
            y: (sourceBase.y - sourceFrame.minY) / sourceFrame.height * CGFloat(sourceOverlay.h)
        )
        guard let coordinate = GarminRasterProjectionMath.projectFromPixel(
            sourcePixel, projection: sourceProjection
        ), let destinationPixel = GarminRasterProjectionMath.projectToPixel(
            latitude: coordinate.latitude,
            longitude: coordinate.longitude,
            projection: destinationProjection
        ) else { return nil }
        let sourceGroundScale = CGFloat(sourceOverlay.ppm) * sourceFrame.width / CGFloat(sourceOverlay.w) * scale
        let destinationBaseScale = CGFloat(destinationOverlay.ppm) * destinationFrame.width / CGFloat(destinationOverlay.w)
        guard sourceGroundScale.isFinite, sourceGroundScale > 0,
              destinationBaseScale.isFinite, destinationBaseScale > 0 else { return nil }
        let nextScale = min(max(sourceGroundScale / destinationBaseScale, 1), 4)
        let destinationBase = CGPoint(
            x: destinationFrame.minX + destinationPixel.x / CGFloat(destinationOverlay.w) * destinationFrame.width,
            y: destinationFrame.minY + destinationPixel.y / CGFloat(destinationOverlay.h) * destinationFrame.height
        )
        let nextOffset = CGSize(
            width: center.x - (center.x + (destinationBase.x - center.x) * nextScale),
            height: center.y - (center.y + (destinationBase.y - center.y) * nextScale)
        )
        return (nextScale, nextOffset)
    }
}

extension GarminRasterResponse {
    public func resolvedImageURL(relativeTo baseURL: URL) -> URL? {
        guard let imageUrl,
              let components = URLComponents(string: imageUrl),
              !components.path.isEmpty else { return nil }
        if let scheme = components.scheme, scheme != baseURL.scheme {
            return nil
        }
        if let host = components.host, host != baseURL.host {
            return nil
        }
        if components.host != nil || components.scheme != nil {
            guard components.scheme == baseURL.scheme,
                  components.host == baseURL.host else { return nil }
            return components.url
        }
        let path = components.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard !path.isEmpty else { return nil }
        guard var baseComponents = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else {
            return nil
        }
        let prefix = baseComponents.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        baseComponents.path = prefix.isEmpty ? "/\(path)" : "/\(prefix)/\(path)"
        baseComponents.query = components.percentEncodedQuery
        baseComponents.fragment = components.fragment
        return baseComponents.url
    }
}
