import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

/// 球洞 2D 俯视图:服务端渲染的真实球场图(球道/果岭/沙坑/水)+ 推荐打法叠加(route 平滑弧线 +
/// 落点 + 球杆 + 旗杆)。备战和实战共用 —— 给它一个 `CoursePrepHole` 即可。
/// 实战时可传 `selectedClub` + 该杆距离:切球杆/换策略时落点标记与球杆标签**实时联动**。
/// 不传则回退到 prep 的推荐落点 / 推荐球杆(备战屏即如此)。
public struct HoleImageMapView: View {
    public let hole: CoursePrepHole
    /// 实战:当前选中的球杆(已是中文名)。传入则地图标签随之变。
    public let selectedClub: String?
    /// 实战:当前选中球杆的典型距离(米)。传入则落点标记移到该距离处。
    public let selectedClubMetres: Double?

    public init(hole: CoursePrepHole, selectedClub: String? = nil, selectedClubMetres: Double? = nil) {
        self.hole = hole
        self.selectedClub = selectedClub
        self.selectedClubMetres = selectedClubMetres
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
        // Recommended play line (tee → green) as a smooth SOLID curve, not a hard polyline.
        if routePoints.count >= 2 {
            context.stroke(
                Self.smoothPath(through: routePoints),
                with: .color(.white.opacity(0.95)),
                style: StrokeStyle(lineWidth: 3, lineCap: .round, lineJoin: .round)
            )
            let tee = routePoints[0]
            context.fill(Path(ellipseIn: CGRect(x: tee.x - 5, y: tee.y - 5, width: 10, height: 10)), with: .color(.white))
        }
        // Landing point + club label: live (selected club's distance) when playing, else the prep's
        // recommended landing. Switching clubs mid-shot moves the marker here.
        if let landing = landingOverlayPoint(overlay) {
            let center = CGPoint(x: landing[0] * sx, y: landing[1] * sy)
            context.fill(Path(ellipseIn: CGRect(x: center.x - 8, y: center.y - 8, width: 16, height: 16)), with: .color(LiveHoleStyle.green))
            context.fill(Path(ellipseIn: CGRect(x: center.x - 3, y: center.y - 3, width: 6, height: 6)), with: .color(.white))
            if let club = clubLabel {
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

    /// 标签:实战传入的当前球杆(已中文)优先,否则 prep 推荐球杆(转中文)。
    private var clubLabel: String? {
        if let selectedClub, !selectedClub.isEmpty {
            return selectedClub
        }
        guard let raw = hole.teeClub ?? hole.steps.first?.club else {
            return nil
        }
        return zhClubName(raw)
    }

    /// Landing point in overlay px: walk the route polyline to where cumulative metres reach the
    /// target (selected club's distance when playing, else the prep's recommended landingM).
    private func landingOverlayPoint(_ overlay: CoursePrepOverlay) -> [Double]? {
        guard let targetM = selectedClubMetres ?? hole.landingM, !overlay.route.isEmpty else {
            return nil
        }
        for row in overlay.route where row.count >= 3 {
            if row[2] >= targetM {
                return row
            }
        }
        return overlay.route.last
    }

    /// Smooth play line through the route centreline points. Quadratic-through-midpoints: each
    /// interior route point is a control point and the curve passes through the midpoints between
    /// consecutive points. Unlike a Catmull-Rom spline this stays INSIDE the control polygon, so it
    /// never overshoots/bulges outside the fairway at a dogleg (the earlier curve's problem) while
    /// still rounding the corners (a hard polyline looked wrong).
    static func smoothPath(through points: [CGPoint]) -> Path {
        var path = Path()
        guard points.count >= 2 else { return path }
        path.move(to: points[0])
        if points.count == 2 {
            path.addLine(to: points[1])
            return path
        }
        for index in 1 ..< points.count - 1 {
            let midpoint = CGPoint(
                x: (points[index].x + points[index + 1].x) / 2,
                y: (points[index].y + points[index + 1].y) / 2
            )
            path.addQuadCurve(to: midpoint, control: points[index])
        }
        path.addLine(to: points[points.count - 1])
        return path
    }
}
