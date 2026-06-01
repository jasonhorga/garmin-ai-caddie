import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

/// Pre-round course review: browse every hole of a course with its styled map, par
/// (labelled source), and the club-based strategy — fed by `/api/v2/courses/{gid}/prep`.
public struct CourseReviewView: View {
    private let client: SyncClient
    private let globalId: Int
    @State private var holes: [CoursePrepHole] = []
    @State private var isLoading = false
    @State private var errorText: String?

    public init(client: SyncClient, globalId: Int) {
        self.client = client
        self.globalId = globalId
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if isLoading {
                    ProgressView("加载中…")
                }
                if let errorText {
                    Text("加载失败：\(errorText)").foregroundColor(.red).font(.callout)
                }
                ForEach(holes, id: \.hole) { hole in
                    HolePrepCard(hole: hole)
                }
            }
            .padding()
        }
        .navigationTitle("赛前球场")
        .task { await load() }
    }

    private func load() async {
        isLoading = true
        errorText = nil
        do {
            let response = try await client.fetchCoursePrep(globalId: globalId)
            holes = response.holes
        } catch {
            errorText = error.localizedDescription
        }
        isLoading = false
    }
}

struct HolePrepCard: View {
    let hole: CoursePrepHole

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Text("\(hole.hole) 洞").font(.headline)
                Text("Par \(hole.par)")
                    .font(.caption).bold()
                    .padding(.horizontal, 8).padding(.vertical, 2)
                    .background(parColor).foregroundColor(.white).clipShape(Capsule())
                Text("\(hole.blueYards)y").font(.caption).foregroundColor(.secondary)
                Spacer()
                Text(sourceLabel).font(.caption2).foregroundColor(.secondary)
            }
            #if canImport(UIKit)
            if let image = holeImage {
                Image(uiImage: image).resizable().scaledToFit()
                    .clipShape(RoundedRectangle(cornerRadius: 8))
            }
            #endif
            ForEach(Array(hole.steps.enumerated()), id: \.offset) { _, step in
                Text("• \(step.club ?? "?")  \(step.note)").font(.subheadline)
            }
            ForEach(Array(hole.cautions.enumerated()), id: \.offset) { _, caution in
                Text("⚠︎ \(caution)").font(.caption).foregroundColor(.orange)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var parColor: Color {
        switch hole.par {
        case 3: return .blue
        case 5: return .orange
        default: return .green
        }
    }

    private var sourceLabel: String {
        switch hole.parSource {
        case "played": return "记分卡"
        case "official": return "官方"
        default: return "推算"
        }
    }

    private var cardBackground: Color {
        #if canImport(UIKit)
        return Color(uiColor: .secondarySystemBackground)
        #else
        return Color.gray.opacity(0.12)
        #endif
    }

    #if canImport(UIKit)
    private var holeImage: UIImage? {
        guard let dataUri = hole.map?.image,
              let comma = dataUri.firstIndex(of: ","),
              let data = Data(base64Encoded: String(dataUri[dataUri.index(after: comma)...]))
        else { return nil }
        return UIImage(data: data)
    }
    #endif
}
