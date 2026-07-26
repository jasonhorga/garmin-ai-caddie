import SwiftUI

/// Home-before-a-round. Real courses are the primary path; downloaded rows remain available with no
/// phone or network. 「仅记分」keeps the old blank scorecard as a deliberate secondary fallback.
public struct WatchStartView: View {
    public let phoneReachable: Bool
    public let courses: [WatchCourseOption]
    public let cachedCourseIds: Set<Int>
    public let isLoadingCourses: Bool
    public let preparingCourseId: Int?
    public let errorMessage: String?
    public let onRefresh: () -> Void
    public let onStartCourse: (WatchCourseOption) -> Void
    public let onStartPractice: () -> Void

    @State private var searchText = ""

    public init(
        phoneReachable: Bool,
        courses: [WatchCourseOption] = [],
        cachedCourseIds: Set<Int> = [],
        isLoadingCourses: Bool = false,
        preparingCourseId: Int? = nil,
        errorMessage: String? = nil,
        onRefresh: @escaping () -> Void = {},
        onStartCourse: @escaping (WatchCourseOption) -> Void = { _ in },
        onStartPractice: @escaping () -> Void = {}
    ) {
        self.phoneReachable = phoneReachable
        self.courses = courses
        self.cachedCourseIds = cachedCourseIds
        self.isLoadingCourses = isLoadingCourses
        self.preparingCourseId = preparingCourseId
        self.errorMessage = errorMessage
        self.onRefresh = onRefresh
        self.onStartCourse = onStartCourse
        self.onStartPractice = onStartPractice
    }

    public var body: some View {
        NavigationStack {
            List {
                Section("选择球场") {
                    if filteredCourses.isEmpty {
                        if isLoadingCourses {
                            ProgressView("正在获取球场")
                        } else {
                            Text(searchText.isEmpty ? "暂无已下载球场" : "没有匹配球场")
                                .foregroundStyle(.secondary)
                        }
                    } else {
                        ForEach(filteredCourses) { course in
                            courseButton(course)
                        }
                    }

                    Button(action: onRefresh) {
                        Label(isLoadingCourses ? "正在更新" : "更新球场", systemImage: "arrow.clockwise")
                    }
                    .disabled(isLoadingCourses || preparingCourseId != nil)
                }

                if let errorMessage {
                    Section {
                        Text(errorMessage)
                            .font(.caption2)
                            .foregroundStyle(.orange)
                    }
                }

                Section {
                    Button(action: onStartPractice) {
                        Text("仅记分")
                    }
                    .disabled(preparingCourseId != nil)
                } footer: {
                    Label(
                        phoneReachable ? "iPhone 已连接" : "已下载球场可离线开局",
                        systemImage: phoneReachable ? "iphone.radiowaves.left.and.right" : "applewatch"
                    )
                }
            }
            .navigationTitle("AI Caddie")
            .searchable(text: $searchText, prompt: "搜索球场")
        }
    }

    @ViewBuilder
    private func courseButton(_ course: WatchCourseOption) -> some View {
        Button {
            onStartCourse(course)
        } label: {
            HStack(spacing: 6) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(course.displayName)
                        .font(.body.weight(.semibold))
                        .lineLimit(2)
                    Text("\(course.playableHoleCount) 洞 · \(course.preferredTee)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 2)
                if preparingCourseId == course.globalId {
                    ProgressView()
                        .controlSize(.small)
                } else if cachedCourseIds.contains(course.globalId) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(AICaddieDesignTokens.par)
                        .accessibilityLabel("已下载，可离线")
                } else {
                    Image(systemName: "arrow.down.circle")
                        .foregroundStyle(.secondary)
                        .accessibilityLabel("需要下载")
                }
            }
        }
        .disabled(preparingCourseId != nil)
    }

    private var filteredCourses: [WatchCourseOption] {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return courses }
        return courses.filter { course in
            [course.name, course.venueName, course.segmentLabel]
                .compactMap { $0 }
                .contains { $0.localizedCaseInsensitiveContains(query) }
        }
    }
}
