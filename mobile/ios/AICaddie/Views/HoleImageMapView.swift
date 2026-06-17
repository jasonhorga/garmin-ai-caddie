import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

/// 球洞 2D 俯视图:服务端渲染的真实球场图(球道/果岭/沙坑/水)+ 推荐打法叠加(route 线 +
/// 推荐落点 + 推荐球杆 + 旗杆)。备战和实战共用 —— 给它一个 `CoursePrepHole` 即可。
/// (替代早先的矢量 HoleMapView:真实几何端点没有面多边形,只有这张服务端图带表面。)
public struct HoleImageMapView: View {
    public let hole: CoursePrepHole

    public init(hole: CoursePrepHole) {
        self.hole = hole
    }

    public var body: some View {
        #if canImport(UIKit)
        if let image = decodedImage, let overlay = hole.map?.overlay, overlay.w > 0, overlay.h > 0 {
            ZStack {
                Image(uiImage: image).resizable().scaledToFit()
                Canvas { context, size in
                    draw(&context, size: size, overlay: overlay)
                }
            }
            .aspectRatio(CGFloat(overlay.w) / CGFloat(overlay.h), contentMode: .fit)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(LiveHoleStyle.line))
        }
        #endif
    }

    public var hasMap: Bool {
        hole.map?.overlay != nil && (hole.map?.overlay.w ?? 0) > 0
    }

    #if canImport(UIKit)
    private var decodedImage: UIImage? {
        guard let uri = hole.map?.image,
              let comma = uri.firstIndex(of: ","),
              let data = Data(base64Encoded: String(uri[uri.index(after: comma)...]))
        else {
            return nil
        }
        return UIImage(data: data)
    }
    #endif

    private func draw(_ context: inout GraphicsContext, size: CGSize, overlay: CoursePrepOverlay) {
        let sx = size.width / CGFloat(overlay.w)
        let sy = size.height / CGFloat(overlay.h)
        let routePoints: [CGPoint] = overlay.route.compactMap { row in
            row.count >= 2 ? CGPoint(x: row[0] * sx, y: row[1] * sy) : nil
        }
        // Recommended play line (tee → green).
        if routePoints.count >= 2 {
            var path = Path()
            path.move(to: routePoints[0])
            for point in routePoints.dropFirst() { path.addLine(to: point) }
            context.stroke(path, with: .color(.white.opacity(0.95)), style: StrokeStyle(lineWidth: 3, lineCap: .round, dash: [7, 5]))
            let tee = routePoints[0]
            context.fill(Path(ellipseIn: CGRect(x: tee.x - 5, y: tee.y - 5, width: 10, height: 10)), with: .color(.white))
        }
        // Recommended landing point + club label (where the caddie suggests laying the tee shot).
        if let landing = recommendedLandingOverlayPoint(overlay) {
            let center = CGPoint(x: landing[0] * sx, y: landing[1] * sy)
            context.fill(Path(ellipseIn: CGRect(x: center.x - 8, y: center.y - 8, width: 16, height: 16)), with: .color(LiveHoleStyle.green))
            context.fill(Path(ellipseIn: CGRect(x: center.x - 3, y: center.y - 3, width: 6, height: 6)), with: .color(.white))
            if let club = recommendedClub {
                context.draw(
                    Text(club).font(.caption2.weight(.bold)).foregroundColor(.white),
                    at: CGPoint(x: center.x, y: center.y - 18)
                )
            }
        }
        // Pin (green end of the route).
        if let pin = routePoints.last {
            context.fill(Path(ellipseIn: CGRect(x: pin.x - 5, y: pin.y - 5, width: 10, height: 10)), with: .color(.red))
        }
    }

    private var recommendedClub: String? {
        hole.teeClub ?? hole.steps.first?.club
    }

    /// Landing point in overlay px: walk the route polyline to where cumulative metres reach landingM.
    private func recommendedLandingOverlayPoint(_ overlay: CoursePrepOverlay) -> [Double]? {
        guard let landingM = hole.landingM, !overlay.route.isEmpty else {
            return nil
        }
        for row in overlay.route where row.count >= 3 {
            if row[2] >= landingM {
                return row
            }
        }
        return overlay.route.last
    }
}
