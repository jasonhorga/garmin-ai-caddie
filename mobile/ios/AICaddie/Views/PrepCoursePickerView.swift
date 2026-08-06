import SwiftUI

/// 备战入口:先选球场(各 9 洞环 / 整场),再进赛前攻略。修复「一进备战就锁死在某个球场」——
/// 备战和开始一场一样,先让你挑球场。
public struct PrepCoursePickerView: View {
    public let courseOptions: [MobileCourseOption]
    public let apiBaseURL: URL?
    public let adminToken: String?

    @StateObject private var locationProvider = LocationProvider()
    @State private var nearbyCourseOptions: [MobileCourseOption] = []
    @State private var remoteCourseOptions: [MobileCourseOption] = []
    @State private var showingCourseSearch = false
    @State private var preferredRemoteCourseId: Int?
    @State private var isLoadingNearby = false
    @State private var nearbyStatusText: String?

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
                    Label("按城市或球场名搜索", systemImage: "magnifyingglass")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(LiveHoleStyle.green)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
                .liveCard()

                if isLoadingNearby {
                    HStack(spacing: 8) {
                        ProgressView()
                        Text("正在定位并查找附近球场…")
                    }
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .liveCard()
                } else if let nearbyStatusText {
                    Label(nearbyStatusText, systemImage: "location")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .liveCard()
                }

                if displayVenueGroups.isEmpty {
                    Text("附近暂时没有可选球场，可以用城市或球场名搜索 Garmin 全部球场。")
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
        .onAppear {
            locationProvider.requestAuthorization()
            locationProvider.startUpdatingLocation()
        }
        .onDisappear {
            locationProvider.stopUpdatingLocation()
        }
        .task(id: locationDiscoveryKey) {
            await discoverNearbyCourses()
        }
        .sheet(isPresented: $showingCourseSearch) {
            NavigationStack {
                MobileCourseSearchView(
                    locationProvider: locationProvider,
                    installedGlobalIds: Set(courseOptions.map(\.globalId)),
                    onSearch: searchCourses,
                    onNearby: nearbyCourses,
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
        // Course selection follows the S70 model: nearby catalogue rows plus the one explicit
        // text-search choice. Historical/previously played courses are lookup metadata only.
        return (nearbyCourseOptions + remoteCourseOptions).filter { seen.insert($0.globalId).inserted }
    }

    private var displayVenueGroups: [(venue: String, segments: [MobileCourseOption])] {
        var groups: [(venue: String, segments: [MobileCourseOption])] = []
        for option in allCourseOptions {
            let venue = option.venueDisplayName
            if let index = groups.firstIndex(where: { $0.venue == venue }) {
                groups[index].segments.append(option)
            } else {
                groups.append((venue: venue, segments: [option]))
            }
        }
        for index in groups.indices {
            groups[index].segments.sort { ($0.segmentLabel ?? "~~") < ($1.segmentLabel ?? "~~") }
        }
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

    private func nearbyCourses(
        latitude: Double,
        longitude: Double,
        radiusKm: Int
    ) async throws -> [MobileCourseSearchMatch] {
        guard let apiBaseURL else { throw URLError(.notConnectedToInternet) }
        return try await SyncClient(baseURL: apiBaseURL, adminToken: adminToken).nearbyCourses(
            latitude: latitude,
            longitude: longitude,
            radiusKm: radiusKm
        )
    }

    private func selectSearchResult(
        _ selected: MobileCourseSearchMatch,
        _ matches: [MobileCourseSearchMatch]
    ) {
        _ = matches
        guard let option = resolvedOption(for: selected) else { return }
        remoteCourseOptions = [option]
        preferredRemoteCourseId = selected.globalId
    }

    private var locationDiscoveryKey: String {
        guard let coordinate = locationProvider.latestFix?.coordinate else {
            return "waiting:\(locationProvider.authorizationStatus.rawValue)"
        }
        // About 10 m of precision is ample for a 50 km course search and avoids re-querying for
        // every tiny Core Location update while the picker is open.
        return "\(Int((coordinate.latitude * 10_000).rounded())):\(Int((coordinate.longitude * 10_000).rounded()))"
    }

    @MainActor
    private func discoverNearbyCourses() async {
        guard let fix = locationProvider.latestFix else {
            nearbyCourseOptions = []
            isLoadingNearby = locationProvider.authorizationStatus == .notDetermined
                || locationProvider.authorizationStatus == .authorizedAlways
                || locationProvider.authorizationStatus == .authorizedWhenInUse
            nearbyStatusText = locationProvider.authorizationStatus == .denied
                || locationProvider.authorizationStatus == .restricted
                ? "定位权限未开启；可以直接按城市或球场名搜索。"
                : nil
            return
        }
        isLoadingNearby = true
        nearbyStatusText = nil
        defer { isLoadingNearby = false }
        do {
            let matches = try await nearbyCourses(
                latitude: fix.coordinate.latitude,
                longitude: fix.coordinate.longitude,
                radiusKm: 50
            )
            var seen = Set<Int>()
            nearbyCourseOptions = matches.compactMap { resolvedOption(for: $0) }.filter {
                seen.insert($0.globalId).inserted
            }
            nearbyStatusText = nearbyCourseOptions.isEmpty
                ? "当前位置 50 km 内没有找到球场；可以扩大范围或按名称搜索。"
                : "当前位置 50 km 内的球场"
        } catch {
            nearbyCourseOptions = []
            nearbyStatusText = "附近球场暂时读取失败；可以先按城市或球场名搜索。"
        }
    }

    private func resolvedOption(for match: MobileCourseSearchMatch) -> MobileCourseOption? {
        guard let provider = match.courseOption else { return nil }
        guard let known = courseOptions.first(where: { $0.globalId == match.globalId }) else {
            return provider
        }
        return MobileCourseOption(
            globalId: provider.globalId,
            courseKey: known.courseKey,
            name: provider.name,
            roundCount: known.roundCount,
            latestRoundId: known.latestRoundId,
            latestRoundDate: known.latestRoundDate,
            templateRoundId: known.templateRoundId,
            suggestedLiveRoundId: known.suggestedLiveRoundId,
            holes: provider.holes,
            teeBox: known.teeBox,
            geometryCoverage: known.geometryCoverage,
            sourceRefs: known.sourceRefs,
            venueName: provider.venueName ?? known.venueName,
            segmentLabel: provider.segmentLabel ?? known.segmentLabel,
            segmentHoles: provider.segmentHoles ?? known.segmentHoles,
            latitude: provider.latitude ?? known.latitude,
            longitude: provider.longitude ?? known.longitude,
            tees: known.tees
        )
    }
}
