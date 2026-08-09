import SwiftUI

enum WatchFinishRoundLayout {
    /// watchOS owns the top-right clock lane even when the app asks for full-screen content.
    /// Reserve the same horizontal space as scoring so a long course name cannot run under it.
    static let systemTimeTrailingClearance: CGFloat = 48
}

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
    public let initiallyShowSecondaryAction: Bool
    public let onConfirmFinish: () -> Void
    public let onKeepPlaying: () -> Void
    public let onAbandon: () -> Void

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
        initiallyShowSecondaryAction: Bool = false,
        onConfirmFinish: @escaping () -> Void = {},
        onKeepPlaying: @escaping () -> Void = {},
        onAbandon: @escaping () -> Void = {}
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
        self.initiallyShowSecondaryAction = initiallyShowSecondaryAction
        self.onConfirmFinish = onConfirmFinish
        self.onKeepPlaying = onKeepPlaying
        self.onAbandon = onAbandon
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                Text("结束本场")
                    .font(.system(size: 14, weight: .bold))

                Text(courseName)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
                    .padding(.trailing, WatchFinishRoundLayout.systemTimeTrailingClearance)
                    .padding(.top, 2)

                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(scoreText)
                        .font(.system(size: 34, weight: .bold, design: .rounded))
                        .monospacedDigit()
                        .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: toPar))
                        .lineLimit(1)
                        .minimumScaleFactor(0.72)

                    VStack(alignment: .leading, spacing: 0) {
                        Text(totalStrokesText)
                            .font(.system(size: 15, weight: .bold, design: .rounded))
                            .monospacedDigit()
                        Text(holesText)
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .monospacedDigit()
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.top, 6)

                if totalPutts != nil {
                    Text(puttsText)
                        .font(.system(size: 13, weight: .medium, design: .rounded))
                        .monospacedDigit()
                        .foregroundStyle(.secondary)
                        .padding(.top, 5)
                }

                if let pendingUploadText {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.up.circle")
                        Text(pendingUploadText)
                    }
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(AICaddieDesignTokens.offline)
                    .padding(.top, 5)
                }

                Button(action: onConfirmFinish) {
                    Text(primaryActionLabel)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(AICaddieDesignTokens.par)
                        .frame(maxWidth: .infinity, minHeight: 42, maxHeight: 42)
                        .background(
                            AICaddieDesignTokens.par.opacity(0.25),
                            in: RoundedRectangle(cornerRadius: 26, style: .continuous)
                        )
                }
                .buttonStyle(.plain)
                .padding(.top, 6)

                Button(action: onKeepPlaying) {
                    Text(secondaryActionLabel)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity, minHeight: 42, maxHeight: 42)
                        .background(
                            Color(red: 70 / 255, green: 70 / 255, blue: 73 / 255),
                            in: RoundedRectangle(cornerRadius: 26, style: .continuous)
                        )
                }
                .buttonStyle(.plain)
                .padding(.top, 5)
                .id(Self.secondaryActionAnchor)

                Button(role: .destructive, action: onAbandon) {
                    Text("放弃本场")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(AICaddieDesignTokens.doubleBogey)
                        .frame(maxWidth: .infinity, minHeight: 38, maxHeight: 38)
                }
                .buttonStyle(.plain)
                .padding(.top, 3)
            }
            .padding(.horizontal, 10)
            .padding(.top, 4)
            .padding(.bottom, 4)
        }
        .scrollIndicators(.hidden)
        .defaultScrollAnchor(initiallyShowSecondaryAction ? .bottom : .top)
        .background(Color.black)
        .ignoresSafeArea(edges: [.top, .leading, .trailing])
    }

    private static let secondaryActionAnchor = "watch-finish-secondary-action"

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

/// Restored rounds pause here instead of reopening a stale score draft. Nothing is discarded until
/// the golfer explicitly chooses one of the three lifecycle verbs.
public struct WatchResumeRoundView: View {
    public let courseName: String
    public let activeHole: Int
    public let scoredHoles: Int
    public let holeCount: Int
    public let pendingUploads: Int
    public let isFreshRound: Bool
    public let canSaveAndEnd: Bool
    public let onResume: () -> Void
    public let onSaveAndEnd: () -> Void
    public let onAbandon: () -> Void

    public init(
        courseName: String,
        activeHole: Int,
        scoredHoles: Int,
        holeCount: Int,
        pendingUploads: Int,
        isFreshRound: Bool = false,
        canSaveAndEnd: Bool = true,
        onResume: @escaping () -> Void = {},
        onSaveAndEnd: @escaping () -> Void = {},
        onAbandon: @escaping () -> Void = {}
    ) {
        self.courseName = courseName
        self.activeHole = activeHole
        self.scoredHoles = scoredHoles
        self.holeCount = holeCount
        self.pendingUploads = pendingUploads
        self.isFreshRound = isFreshRound
        self.canSaveAndEnd = canSaveAndEnd
        self.onResume = onResume
        self.onSaveAndEnd = onSaveAndEnd
        self.onAbandon = onAbandon
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 7) {
                Text(isFreshRound ? "球局已准备好" : "未结束的球局")
                    .font(.system(size: 16, weight: .bold))
                Text(courseName.isEmpty ? "高尔夫球局" : courseName)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                    .padding(.trailing, WatchFinishRoundLayout.systemTimeTrailingClearance)
                Text(isFreshRound
                    ? "从第 \(activeHole) 洞开始 · 共 \(holeCount) 洞"
                    : "第 \(activeHole) 洞 · 已记 \(scoredHoles)/\(holeCount)")
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                if pendingUploads > 0 {
                    Text("\(pendingUploads) 条记录等待同步")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(AICaddieDesignTokens.offline)
                }
                lifecycleButton(
                    isFreshRound ? "开始本场" : "继续本场",
                    tint: AICaddieDesignTokens.par,
                    action: onResume
                )
                if canSaveAndEnd {
                    lifecycleButton("保存并结束", tint: Color.white, action: onSaveAndEnd)
                }
                Button(role: .destructive, action: onAbandon) {
                    Text("放弃本场")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(AICaddieDesignTokens.doubleBogey)
                        .frame(maxWidth: .infinity, minHeight: 34)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
        }
        .scrollIndicators(.hidden)
        .background(Color.black)
        .ignoresSafeArea(edges: [.top, .leading, .trailing])
    }

    private func lifecycleButton(
        _ label: String,
        tint: Color,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(tint)
                .frame(maxWidth: .infinity, minHeight: 36)
                .background(Color(red: 35 / 255, green: 35 / 255, blue: 37 / 255), in: Capsule())
        }
        .buttonStyle(.plain)
    }
}

public struct WatchAbandonConfirmationView: View {
    public let pendingUploads: Int
    public let errorMessage: String?
    public let onConfirm: () -> Void
    public let onCancel: () -> Void

    public init(
        pendingUploads: Int,
        errorMessage: String? = nil,
        onConfirm: @escaping () -> Void = {},
        onCancel: @escaping () -> Void = {}
    ) {
        self.pendingUploads = pendingUploads
        self.errorMessage = errorMessage
        self.onConfirm = onConfirm
        self.onCancel = onCancel
    }

    public var body: some View {
        GeometryReader { proxy in
            VStack(spacing: 9) {
                Spacer(minLength: 8)
                Text("放弃本场？")
                    .font(.system(size: 16, weight: .bold))
                Text(message)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(errorMessage == nil ? Color.secondary : AICaddieDesignTokens.doubleBogey)
                    .multilineTextAlignment(.center)
                    .lineLimit(4)
                Spacer(minLength: 4)
                HStack(spacing: 8) {
                    confirmationButton("返回", background: Color(red: 31 / 255, green: 31 / 255, blue: 31 / 255), action: onCancel)
                    confirmationButton("放弃", background: Color(red: 1.0, green: 69 / 255, blue: 59 / 255), action: onConfirm)
                }
            }
            .padding(.horizontal, 10)
            .padding(.bottom, 10)
            .frame(width: proxy.size.width, height: min(proxy.size.height, 198))
        }
        .background(Color.black)
        .ignoresSafeArea()
    }

    private var message: String {
        if let errorMessage { return errorMessage }
        let pending = pendingUploads > 0 ? "，包含 \(pendingUploads) 条未上传记录" : ""
        return "将删除手表上的本场\(pending)。\n手机上的记录不受影响。"
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
                .frame(maxWidth: .infinity, minHeight: 34)
                .background(background, in: Capsule())
        }
        .buttonStyle(.plain)
    }
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
        GeometryReader { proxy in
            let approvedHeight = min(proxy.size.height, 198)
            VStack(spacing: 10) {
                Spacer(minLength: 4)

                Text(titleText)
                    .font(.system(size: 16, weight: .bold))
                    .multilineTextAlignment(.center)
                    .offset(y: 10)

                Text(statusText)
                    .font(.system(size: 11))
                    .foregroundStyle(
                        uploadError == nil ? Color.secondary : AICaddieDesignTokens.doubleBogey
                    )
                    .multilineTextAlignment(.center)
                    .lineLimit(2)
                    .offset(y: 10)

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
            .padding(.bottom, 10)
            .frame(width: proxy.size.width, height: approvedHeight)
            .position(x: proxy.size.width / 2, y: approvedHeight / 2)
        }
        .background(Color.black)
        .ignoresSafeArea()
    }

    var titleText: String { "结束本场?" }
    var summaryText: String { "\(holesPlayed) 洞 · \(scoreText) · 保存并结束" }
    var cancelLabel: String { "返回" }
    var confirmLabel: String { isUploading ? "保存中" : "确认" }

    private var statusText: String {
        if let uploadError { return uploadError }
        if isUploading { return "正在保存…" }
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
