import SwiftUI

/// 备战入口:先选球场(各 9 洞环 / 整场),再进赛前攻略。修复「一进备战就锁死在某个球场」——
/// 备战和开始一场一样,先让你挑球场。
public struct PrepCoursePickerView: View {
    public let courseOptions: [MobileCourseOption]
    public let apiBaseURL: URL?
    public let adminToken: String?

    public init(courseOptions: [MobileCourseOption], apiBaseURL: URL?, adminToken: String?) {
        self.courseOptions = courseOptions
        self.apiBaseURL = apiBaseURL
        self.adminToken = adminToken
    }

    public var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                if courseVenueGroups(courseOptions).isEmpty {
                    Text("暂无球场,先在设置里同步 Garmin 球局。").font(.subheadline).foregroundStyle(.secondary)
                }
                ForEach(courseVenueGroups(courseOptions), id: \.venue) { group in
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
    }

    @ViewBuilder private func segmentRow(_ segment: MobileCourseOption) -> some View {
        if let apiBaseURL {
            NavigationLink {
                CourseReviewView(client: SyncClient(baseURL: apiBaseURL, adminToken: adminToken), globalId: segment.globalId)
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
            }
            .buttonStyle(.plain)
        }
    }
}
