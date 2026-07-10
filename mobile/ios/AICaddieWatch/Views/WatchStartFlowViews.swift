import SwiftUI

/// Watch design-system #19–21: the 开局向导 (linear push, select = advance, swipe-right back).
/// Three presentational lists: 选球场 (nearest-first) → 选 9/18 → 选发球台. Select-on-tap (no confirm
/// button); everything is undoable via 放弃本场. VStacks so they render in ImageRenderer snapshots.

/// #19 选球场 — GPS-nearest courses, tap to pick.
public struct WatchCourseSelectView: View {
    public struct Course: Identifiable, Equatable {
        public let name: String
        public let par: Int
        public let km: Double
        public var id: String { name }
        public init(name: String, par: Int, km: Double) {
            self.name = name
            self.par = par
            self.km = km
        }
    }
    public let courses: [Course]
    public let onPick: (String) -> Void
    public init(courses: [Course], onPick: @escaping (String) -> Void = { _ in }) {
        self.courses = courses
        self.onPick = onPick
    }
    public var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("附近球场").font(.headline.weight(.bold)).padding(.bottom, 2)
            ForEach(Array(courses.enumerated()), id: \.element.id) { i, course in
                Button { onPick(course.name) } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 1) {
                            Text(course.name).font(.system(size: 14, weight: i == 0 ? .bold : .semibold))
                            Text("Par \(course.par) · \(String(format: "%.1f", course.km)) km").font(.system(size: 10)).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.right").font(.system(size: 10)).foregroundStyle(.tertiary)
                    }
                    .padding(.horizontal, 9).padding(.vertical, 8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 10).fill(i == 0 ? AICaddieDesignTokens.par.opacity(0.16) : Color.white.opacity(0.06)))
                }.buttonStyle(.plain)
            }
        }
        .padding(8)
    }
}

/// #20 选 9/18 — starting-nine choice, big rows.
public struct WatchNineSelectView: View {
    public let onPick: (String) -> Void
    public init(onPick: @escaping (String) -> Void = { _ in }) { self.onPick = onPick }
    private let items: [(key: String, title: String, sub: String)] = [
        ("all", "全 18 洞", "前九 + 后九"),
        ("front", "前 9 洞", "1–9"),
        ("back", "后 9 洞", "10–18"),
    ]
    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("打几洞").font(.headline.weight(.bold)).padding(.bottom, 2)
            ForEach(items, id: \.key) { it in
                Button { onPick(it.key) } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 1) {
                            Text(it.title).font(.system(size: 15, weight: .bold))
                            Text(it.sub).font(.system(size: 10)).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.right").font(.system(size: 10)).foregroundStyle(.tertiary)
                    }
                    .padding(.horizontal, 10).padding(.vertical, 9)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 11).fill(Color.white.opacity(0.07)))
                }.buttonStyle(.plain)
            }
        }
        .padding(8)
    }
}

/// #21 选发球台 — tee list with slope/rating (harvested from CourseView), select-on-tap.
public struct WatchTeeSelectView: View {
    public struct Tee: Identifiable, Equatable {
        public let name: String
        public let color: Color
        public let yards: Int
        public let slope: Int?
        public var id: String { name }
        public init(name: String, color: Color, yards: Int, slope: Int?) {
            self.name = name
            self.color = color
            self.yards = yards
            self.slope = slope
        }
    }
    public let tees: [Tee]
    public let selected: String?
    public let onPick: (String) -> Void
    public init(tees: [Tee], selected: String? = nil, onPick: @escaping (String) -> Void = { _ in }) {
        self.tees = tees
        self.selected = selected
        self.onPick = onPick
    }
    public var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("发球台").font(.headline.weight(.bold)).padding(.bottom, 2)
            ForEach(tees) { tee in
                Button { onPick(tee.name) } label: {
                    HStack(spacing: 7) {
                        Circle().fill(tee.color).frame(width: 12, height: 12)
                        Text(tee.name).font(.system(size: 14, weight: .semibold))
                        Spacer()
                        VStack(alignment: .trailing, spacing: 0) {
                            Text("\(tee.yards) 码").font(.system(size: 12, weight: .semibold)).monospacedDigit()
                            if let s = tee.slope {
                                Text("Slope \(s)").font(.system(size: 8.5)).foregroundStyle(.tertiary).monospacedDigit()
                            }
                        }
                        if tee.name == selected {
                            Image(systemName: "checkmark").font(.system(size: 11, weight: .bold)).foregroundStyle(AICaddieDesignTokens.par)
                        }
                    }
                    .padding(.horizontal, 9).padding(.vertical, 7)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 10).fill(Color.white.opacity(0.06)))
                }.buttonStyle(.plain)
            }
        }
        .padding(8)
    }
}
