import SwiftUI

/// The approved compact end-of-round summary. The richer GIR/fairway facts remain in the model for
/// history and phone review, but this glance deliberately shows only the facts present in render #16.
public struct WatchFinishRoundView: View {
    public let courseName: String
    public let holesPlayed: Int
    public let holeCount: Int
    public let totalStrokes: Int
    public let toPar: Int?
    public let totalPutts: Int?
    public let fairwaySummary: WatchOutcomeSummary?
    public let girSummary: WatchOutcomeSummary?
    public let pendingUploads: Int
    public let onConfirmFinish: () -> Void
    public let onKeepPlaying: () -> Void

    public init(
        courseName: String,
        holesPlayed: Int,
        holeCount: Int,
        totalStrokes: Int,
        toPar: Int?,
        totalPutts: Int? = nil,
        fairwaySummary: WatchOutcomeSummary? = nil,
        girSummary: WatchOutcomeSummary? = nil,
        pendingUploads: Int = 0,
        onConfirmFinish: @escaping () -> Void = {},
        onKeepPlaying: @escaping () -> Void = {}
    ) {
        self.courseName = courseName
        self.holesPlayed = holesPlayed
        self.holeCount = holeCount
        self.totalStrokes = totalStrokes
        self.toPar = toPar
        self.totalPutts = totalPutts
        self.fairwaySummary = fairwaySummary
        self.girSummary = girSummary
        self.pendingUploads = pendingUploads
        self.onConfirmFinish = onConfirmFinish
        self.onKeepPlaying = onKeepPlaying
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("结束本场")
                .font(.system(size: 15, weight: .bold))

            Text(courseName)
                .font(.system(size: 9, weight: .medium))
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .padding(.top, 1)

            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(scoreText)
                    .font(.system(size: 32, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: toPar))

                VStack(alignment: .leading, spacing: 0) {
                    Text(totalStrokesText)
                        .font(.system(size: 13, weight: .bold, design: .rounded))
                        .monospacedDigit()
                    Text(holesText)
                        .font(.system(size: 9, weight: .medium, design: .rounded))
                        .monospacedDigit()
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.top, 6)

            if totalPutts != nil {
                Text(puttsText)
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
                    .padding(.top, 5)
            }

            if let pendingUploadText {
                HStack(spacing: 4) {
                    Image(systemName: "arrow.up.circle")
                    Text(pendingUploadText)
                }
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(AICaddieDesignTokens.offline)
                .padding(.top, 5)
            }

            Spacer(minLength: 3)

            Button(action: onConfirmFinish) {
                Text(primaryActionLabel)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(AICaddieDesignTokens.par)
                    .frame(maxWidth: .infinity, minHeight: 42)
                    .background(
                        AICaddieDesignTokens.par.opacity(0.25),
                        in: RoundedRectangle(cornerRadius: 21, style: .continuous)
                    )
            }
            .buttonStyle(.plain)

            Button(action: onKeepPlaying) {
                Text(secondaryActionLabel)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity, minHeight: 43)
                    .background(
                        Color(red: 70 / 255, green: 70 / 255, blue: 73 / 255),
                        in: RoundedRectangle(cornerRadius: 22, style: .continuous)
                    )
            }
            .buttonStyle(.plain)
            .padding(.top, 8)
        }
        .padding(.horizontal, 25)
        .padding(.top, 8)
        .padding(.bottom, 6)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Color.black)
        .ignoresSafeArea()
    }

    var scoreText: String {
        guard let toPar else { return "—" }
        if toPar == 0 { return "E" }
        return toPar > 0 ? "+\(toPar)" : "\(toPar)"
    }

    var totalStrokesText: String { "\(totalStrokes) 杆" }
    var holesText: String { "\(holesPlayed)/\(holeCount) 洞" }
    var puttsText: String { totalPutts.map { "推杆 \($0)" } ?? "推杆 —" }
    var pendingUploadText: String? { pendingUploads > 0 ? "稍后同步 \(pendingUploads)" : nil }
    var primaryActionLabel: String { "保存并结束" }
    var secondaryActionLabel: String { "继续打球" }
}

/// Render #18: a separate destructive-action guard. Upload/finalize cannot begin from the summary;
/// the player must reach this surface and explicitly press the opposite-side red button.
public struct WatchFinishConfirmationView: View {
    public let holesPlayed: Int
    public let toPar: Int?
    public let pendingUploads: Int
    public let isUploading: Bool
    public let uploadError: String?
    public let onConfirm: () -> Void
    public let onCancel: () -> Void

    public init(
        holesPlayed: Int,
        toPar: Int?,
        pendingUploads: Int,
        isUploading: Bool = false,
        uploadError: String? = nil,
        onConfirm: @escaping () -> Void = {},
        onCancel: @escaping () -> Void = {}
    ) {
        self.holesPlayed = holesPlayed
        self.toPar = toPar
        self.pendingUploads = pendingUploads
        self.isUploading = isUploading
        self.uploadError = uploadError
        self.onConfirm = onConfirm
        self.onCancel = onCancel
    }

    public var body: some View {
        VStack(spacing: 10) {
            Spacer(minLength: 4)

            Text(titleText)
                .font(.system(size: 16, weight: .bold))
                .multilineTextAlignment(.center)

            Text(statusText)
                .font(.system(size: 11))
                .foregroundStyle(
                    uploadError == nil ? Color.secondary : AICaddieDesignTokens.doubleBogey
                )
                .multilineTextAlignment(.center)
                .lineLimit(2)

            Spacer(minLength: 4)

            HStack(spacing: 8) {
                confirmationButton(
                    cancelLabel,
                    background: Color(red: 31 / 255, green: 31 / 255, blue: 31 / 255),
                    action: onCancel
                )
                confirmationButton(
                    confirmLabel,
                    background: Color(red: 1.0, green: 69 / 255, blue: 59 / 255),
                    action: onConfirm
                )
            }
        }
        .padding(.horizontal, 10)
        .padding(.top, 10)
        .padding(.bottom, 32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.black)
        .ignoresSafeArea()
    }

    var titleText: String { "结束本场?" }
    var summaryText: String { "\(holesPlayed) 洞 · \(scoreText) · 保存并上传" }
    var cancelLabel: String { "返回" }
    var confirmLabel: String { isUploading ? "保存中" : "确认" }

    private var statusText: String {
        if let uploadError { return uploadError }
        if isUploading { return "正在保存并上传…" }
        return summaryText
    }

    private var scoreText: String {
        guard let toPar else { return "—" }
        if toPar == 0 { return "E" }
        return toPar > 0 ? "+\(toPar)" : "\(toPar)"
    }

    private func confirmationButton(
        _ label: String,
        background: Color,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, minHeight: 32)
                .background(
                    background,
                    in: RoundedRectangle(cornerRadius: 12, style: .continuous)
                )
        }
        .buttonStyle(.plain)
        .disabled(isUploading)
    }
}
