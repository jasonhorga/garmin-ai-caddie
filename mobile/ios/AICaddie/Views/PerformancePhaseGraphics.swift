import Foundation
import SwiftUI

/// Garmin's Shot Overview makes spatial evidence the body of the page. These first-pass graphics
/// remain honest about the smaller mobile aggregate contract: regions and fills encode recorded
/// counts, while individual dots are reserved for a later contract that actually supplies shots.
struct DirectionRangeGraphic: View {
    let left: Int?
    let center: Int?
    let right: Int?

    var body: some View {
        GeometryReader { proxy in
            let values = [left ?? 0, center ?? 0, right ?? 0]
            let peak = max(values.max() ?? 0, 1)
            ZStack(alignment: .bottom) {
                FairwayShape()
                    .fill(
                        LinearGradient(
                            colors: [Color(red: 0.12, green: 0.33, blue: 0.16),
                                     Color(red: 0.27, green: 0.58, blue: 0.31)],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )

                HStack(spacing: 0) {
                    ForEach(0..<7, id: \.self) { index in
                        Rectangle().fill(Color.white.opacity(index.isMultiple(of: 2) ? 0.07 : 0.015))
                    }
                }
                .clipShape(FairwayShape())

                HStack(alignment: .bottom, spacing: 1) {
                    ForEach(0..<3, id: \.self) { index in
                        Rectangle()
                            .fill(index == 1 ? Color.white.opacity(0.32) : Color.orange.opacity(0.38))
                            .frame(height: max(8, CGFloat(values[index]) / CGFloat(peak) * proxy.size.height * 0.76))
                            .overlay(alignment: .top) {
                                Text("\(values[index])")
                                    .font(.caption2.monospacedDigit().weight(.bold))
                                    .foregroundStyle(.white)
                                    .padding(.top, 5)
                            }
                    }
                }
                .padding(.horizontal, proxy.size.width * 0.12)
                .clipShape(FairwayShape())

                Rectangle()
                    .fill(Color.white.opacity(0.7))
                    .frame(width: 1, height: proxy.size.height)
            }
        }
        .frame(height: 260)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("开球方向分区汇总，偏左 \(left ?? 0)，球道 \(center ?? 0)，偏右 \(right ?? 0)")
    }
}

private struct FairwayShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.width * 0.32, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.width * 0.68, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
        path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
        path.closeSubpath()
        return path
    }
}

struct ApproachTargetGraphic: View {
    let short: Int?
    let long: Int?
    let left: Int?
    let right: Int?
    let green: Int?

    var body: some View {
        GeometryReader { proxy in
            let center = CGPoint(x: proxy.size.width / 2, y: proxy.size.height / 2)
            ZStack {
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(Color(red: 0.12, green: 0.30, blue: 0.16))
                Ellipse()
                    .fill(Color(red: 0.34, green: 0.67, blue: 0.37))
                    .frame(width: proxy.size.width * 0.58, height: proxy.size.height * 0.52)
                Ellipse()
                    .stroke(Color.white.opacity(0.45), lineWidth: 1)
                    .frame(width: proxy.size.width * 0.58, height: proxy.size.height * 0.52)
                missLabel("偏长 \(long ?? 0)", x: center.x, y: 24)
                missLabel("偏短 \(short ?? 0)", x: center.x, y: proxy.size.height - 24)
                missLabel("偏左 \(left ?? 0)", x: 47, y: center.y)
                missLabel("偏右 \(right ?? 0)", x: proxy.size.width - 47, y: center.y)
                VStack(spacing: 1) {
                    Text("\(green ?? 0)").font(.title2.monospacedDigit().weight(.semibold))
                    Text("GIR").font(.caption2.weight(.bold))
                }
                .foregroundStyle(.white)
                .position(center)
            }
        }
        .frame(height: 240)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("攻果岭分区汇总，GIR \(green ?? 0)，偏短 \(short ?? 0)，偏长 \(long ?? 0)，偏左 \(left ?? 0)，偏右 \(right ?? 0)")
    }

    private func missLabel(_ text: String, x: CGFloat, y: CGFloat) -> some View {
        Text(text)
            .font(.caption2.monospacedDigit().weight(.semibold))
            .foregroundStyle(.white.opacity(0.9))
            .position(x: x, y: y)
    }
}

struct ShortGameGraphic: View {
    let shotCount: Int?

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color(red: 0.13, green: 0.31, blue: 0.16))
            Ellipse()
                .fill(Color(red: 0.36, green: 0.69, blue: 0.38))
                .frame(width: 210, height: 126)
            Capsule()
                .fill(Color(red: 0.70, green: 0.64, blue: 0.43).opacity(0.72))
                .frame(width: 82, height: 34)
                .offset(x: 102, y: 52)
            VStack(spacing: 2) {
                Text(shotCount.map(String.init) ?? "—")
                    .font(.system(size: 42, weight: .semibold))
                    .monospacedDigit()
                Text("次长草 / 沙坑起杆")
                    .font(.caption.weight(.semibold))
            }
            .foregroundStyle(.white)
        }
        .frame(height: 220)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(shotCount.map { "已记录 \($0) 次长草或沙坑击球" } ?? "暂无已记录短杆")
    }
}

struct PuttingGreenGraphic: View {
    let average: Double?

    var body: some View {
        let progress = min(max((average ?? 0) / 3.0, 0), 1)
        ZStack {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color(red: 0.13, green: 0.31, blue: 0.16))
            Circle()
                .stroke(Color.white.opacity(0.16), lineWidth: 18)
                .frame(width: 142, height: 142)
            Circle()
                .trim(from: 0, to: progress)
                .stroke(Color.white, style: StrokeStyle(lineWidth: 18, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .frame(width: 142, height: 142)
            VStack(spacing: 1) {
                Text(average.map { String(format: "%.1f", $0) } ?? "—")
                    .font(.system(size: 38, weight: .semibold))
                    .monospacedDigit()
                Text("推 / 洞").font(.caption.weight(.semibold))
            }
            .foregroundStyle(.white)
        }
        .frame(height: 220)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(average.map { String(format: "平均每洞 %.1f 推", $0) } ?? "暂无已记录推杆")
    }
}
