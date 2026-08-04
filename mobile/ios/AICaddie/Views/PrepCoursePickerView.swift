import SwiftUI

/// 备战入口:先选球场(各 9 洞环 / 整场),再进赛前攻略。修复「一进备战就锁死在某个球场」——
/// 备战和开始一场一样,先让你挑球场。
public struct PrepCoursePickerView: View {
    public let courseOptions: [MobileCourseOption]
    public let apiBaseURL: URL?
    public let adminToken: String?

    @State private var remoteCourseOptions: [MobileCourseOption] = []
    @State private var showingCourseSearch = false
    @State private var preferredRemoteCourseId: Int?

    public init(courseOptions: [MobileCourseOption], apiBaseURL: URL?, adminToken: String?) {
        self.courseOptions = courseOptions
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
    }

    public var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                Button {
                    showingCourseSearch = true
                } label: {
                    Label("搜索其他球场", systemImage: "magnifyingglass")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(LiveHoleStyle.green)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
                .liveCard()

                if displayVenueGroups.isEmpty {
                    Text("暂无已知球场，可以直接搜索 Garmin 全部球场。")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                ForEach(displayVenueGroups, id: \.venue) { group in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(group.venue).font(.subheadline.weight(.bold))
                        ForEach(group.segments) { segment in
                            segmentRow(segment)
                        }
                    }
                    .liveCard()
                }
            }
            .padding(14)
        }
        .background(Color(red: 246 / 255, green: 247 / 255, blue: 248 / 255))
        .navigationTitle("选球场备战")
        .sheet(isPresented: $showingCourseSearch) {
            NavigationStack {
                MobileCourseSearchView(
                    onSearch: searchCourses,
                    onSelect: selectSearchResult
                )
            }
        }
    }

    @ViewBuilder private func segmentRow(_ segment: MobileCourseOption) -> some View {
        if let apiBaseURL {
            NavigationLink {
                CourseReviewView(
                    client: SyncClient(baseURL: apiBaseURL, adminToken: adminToken),
                    globalId: segment.globalId,
                    holeCount: segment.resolvedHoles
                )
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: "map").foregroundStyle(LiveHoleStyle.green)
                    Text(segment.segmentDisplayTitle).font(.subheadline).foregroundStyle(.primary)
                    Spacer()
                    Text("\(segment.resolvedHoles) 洞").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                    Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary)
                }
                .padding(.vertical, 8)
                .padding(.horizontal, 10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(LiveHoleStyle.line))
                // Make the WHOLE row (incl. the Spacer gap) the tap target — without this a tap on the
                // empty middle of the row doesn't trigger the NavigationLink (real users tapping the gap
                // + XCUITest, whose synthetic tap lands on the row centre, both missed it).
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("prep-course-row-\(segment.globalId)")
        }
    }

    private var allCourseOptions: [MobileCourseOption] {
        var seen = Set<Int>()
        return (courseOptions + remoteCourseOptions).filter { seen.insert($0.globalId).inserted }
    }

    private var displayVenueGroups: [(venue: String, segments: [MobileCourseOption])] {
        var groups = courseVenueGroups(allCourseOptions)
        guard let preferredRemoteCourseId else { return groups }
        if let index = groups.firstIndex(where: {
            $0.segments.contains { $0.globalId == preferredRemoteCourseId }
        }) {
            let preferred = groups.remove(at: index)
            groups.insert(preferred, at: 0)
        }
        return groups
    }

    private func searchCourses(_ name: String) async throws -> [MobileCourseSearchMatch] {
        guard let apiBaseURL else { throw URLError(.notConnectedToInternet) }
        return try await SyncClient(baseURL: apiBaseURL, adminToken: adminToken).searchCourses(name: name)
    }

    private func selectSearchResult(
        _ selected: MobileCourseSearchMatch,
        _ matches: [MobileCourseSearchMatch]
    ) {
        var seen = Set(remoteCourseOptions.map(\.globalId))
        for option in matches.compactMap(\.courseOption) where seen.insert(option.globalId).inserted {
            remoteCourseOptions.append(option)
        }
        preferredRemoteCourseId = selected.globalId
    }
}
