import SwiftUI

enum WatchFinishRoundLayout {
    /// watchOS owns the top-right clock lane even when the app asks for full-screen content.
    /// Reserve the same horizontal space as scoring so a long course name cannot run under it.
    static let systemTimeTrailingClearance: CGFloat = 48

    /// Keep the result and the two non-destructive choices together. Discard stays visible just
    /// below them, but no longer competes with the primary save action in a three-button row.
    static let primaryActionHeight: CGFloat = 48
    static let secondaryActionHeight: CGFloat = 44
    static let abandonActionHeight: CGFloat = 38

    /// The 41 mm face has only 215 pt of vertical content. Keep the typography enlarged, but use a
    /// tighter instrument rhythm so all four lifecycle choices remain visible without scrolling.
    static let compactPrimaryActionHeight: CGFloat = 46
    static let compactSecondaryActionHeight: CGFloat = 42
    static let compactAbandonActionHeight: CGFloat = 34

    static func isCompact(_ size: CGSize) -> Bool {
        size.height <= 220
    }
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
    public let onEditScore: () -> Void
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
        onEditScore: @escaping () -> Void = {},
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
        self.onEditScore = onEditScore
        self.onKeepPlaying = onKeepPlaying
        self.onAbandon = onAbandon
    }

    public var body: some View {
        GeometryReader { proxy in
            let compact = WatchFinishRoundLayout.isCompact(proxy.size)
            let primaryHeight = compact
                ? WatchFinishRoundLayout.compactPrimaryActionHeight
                : WatchFinishRoundLayout.primaryActionHeight
            let secondaryHeight = compact
                ? WatchFinishRoundLayout.compactSecondaryActionHeight
                : WatchFinishRoundLayout.secondaryActionHeight
            let abandonHeight = compact
                ? WatchFinishRoundLayout.compactAbandonActionHeight
                : WatchFinishRoundLayout.abandonActionHeight

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Text("结束本场")
                        .font(.system(size: compact ? 19 : 20, weight: .black))
                        .padding(.trailing, WatchFinishRoundLayout.systemTimeTrailingClearance)
                        .accessibilityLabel("\(courseName)，结束本场")

                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(scoreText)
                            .font(.system(size: compact ? 40 : 42, weight: .black, design: .rounded))
                            .monospacedDigit()
                            .foregroundStyle(AICaddieDesignTokens.scoreColor(toPar: toPar))
                            .lineLimit(1)
                            .minimumScaleFactor(0.72)

                        VStack(alignment: .leading, spacing: 0) {
                            Text(totalStrokesText)
                                .font(.system(size: compact ? 18 : 19, weight: .black, design: .rounded))
                                .monospacedDigit()
                            Text(completionText)
                                .font(.system(size: compact ? 11 : 12, weight: .semibold, design: .rounded))
                                .monospacedDigit()
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                                .minimumScaleFactor(0.78)
                        }
                    }
                    .padding(.top, compact ? 2 : 7)

                    Button(action: onConfirmFinish) {
                        Text(primaryActionLabel)
                            .font(.system(size: 18, weight: .black))
                            .foregroundStyle(.white)
                            .frame(
                                maxWidth: .infinity,
                                minHeight: primaryHeight,
                                maxHeight: primaryHeight
                            )
                            .background(
                                AICaddieDesignTokens.par,
                                in: RoundedRectangle(cornerRadius: 26, style: .continuous)
                            )
                    }
                    .buttonStyle(.plain)
                    .padding(.top, compact ? 5 : 9)

                    HStack(spacing: 6) {
                        secondaryButton(editScoreActionLabel, height: secondaryHeight, action: onEditScore)
                        secondaryButton(secondaryActionLabel, height: secondaryHeight, action: onKeepPlaying)
                    }
                    .padding(.top, compact ? 4 : 6)

                    Button(role: .destructive, action: onAbandon) {
                        Text("放弃本场")
                            .font(.system(size: 16, weight: .black))
                            .foregroundStyle(AICaddieDesignTokens.doubleBogey)
                            .frame(
                                maxWidth: .infinity,
                                minHeight: abandonHeight,
                                maxHeight: abandonHeight
                            )
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .padding(.top, compact ? 0 : 2)
                    .id(Self.secondaryActionAnchor)
                }
                .padding(.horizontal, WatchDisplayGeometry.minimumContentInset)
                .padding(.top, compact ? 2 : 4)
                .padding(.bottom, 2)
            }
            .scrollIndicators(.hidden)
            .defaultScrollAnchor(.top)
        }
        .background(Color.black)
        .ignoresSafeArea(edges: .top)
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
    var completionText: String {
        guard let totalPutts else { return holesText }
        return "\(holesText) · \(totalPutts) 推"
    }
    var primaryActionLabel: String { "保存并结束" }
    var editScoreActionLabel: String { "编辑成绩" }
    var secondaryActionLabel: String { "继续打球" }

    private func secondaryButton(
        _ label: String,
        height: CGFloat,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 16, weight: .black))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.78)
                .frame(
                    maxWidth: .infinity,
                    minHeight: height,
                    maxHeight: height
                )
                .background(Color(red: 70 / 255, green: 70 / 255, blue: 73 / 255), in: Capsule())
        }
        .buttonStyle(.plain)
    }
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
    public let pendingPhoneCourseName: String?
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
        pendingPhoneCourseName: String? = nil,
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
        self.pendingPhoneCourseName = pendingPhoneCourseName
        self.onResume = onResume
        self.onSaveAndEnd = onSaveAndEnd
        self.onAbandon = onAbandon
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 7) {
                Text(isFreshRound ? "球局已准备好" : "未结束的球局")
                    .font(.system(size: 20, weight: .black))
                Text(courseName.isEmpty ? "高尔夫球局" : courseName)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                    .padding(.trailing, WatchFinishRoundLayout.systemTimeTrailingClearance)
                Text(isFreshRound
                    ? "从第 \(activeHole) 洞开始 · 共 \(holeCount) 洞"
                    : "第 \(activeHole) 洞 · 已记 \(scoredHoles)/\(holeCount)")
                    .font(.system(size: 17, weight: .black, design: .rounded))
                    .monospacedDigit()
                if pendingUploads > 0 {
                    Text("\(pendingUploads) 条记录等待同步")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(AICaddieDesignTokens.offline)
                }
                if let pendingPhoneCourseName {
                    Text("手机已开始另一场")
                        .font(.system(size: 13, weight: .heavy))
                        .foregroundStyle(AICaddieDesignTokens.bogey)
                    Text(pendingPhoneCourseName)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                        .minimumScaleFactor(0.72)
                    Text("保存或放弃当前局后自动切换")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(.secondary)
                }
                lifecycleButton(
                    isFreshRound ? "开始本场" : "继续本场",
                    primary: true,
                    action: onResume
                )
                if canSaveAndEnd {
                    lifecycleButton("保存并结束", action: onSaveAndEnd)
                }
                Button(role: .destructive, action: onAbandon) {
                    Text("放弃本场")
                        .font(.system(size: 16, weight: .black))
                        .foregroundStyle(AICaddieDesignTokens.doubleBogey)
                        .frame(maxWidth: .infinity, minHeight: 46)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, WatchDisplayGeometry.minimumContentInset)
            .padding(.vertical, 6)
        }
        .scrollIndicators(.hidden)
        .background(Color.black)
        .ignoresSafeArea(edges: .top)
    }

    private func lifecycleButton(
        _ label: String,
        primary: Bool = false,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 17, weight: .black))
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, minHeight: 48)
                .background(
                    primary
                        ? AICaddieDesignTokens.par
                        : Color(red: 35 / 255, green: 35 / 255, blue: 37 / 255),
                    in: Capsule()
                )
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
                    .font(.system(size: 20, weight: .black))
                Text(message)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(errorMessage == nil ? Color.secondary : AICaddieDesignTokens.doubleBogey)
                    .multilineTextAlignment(.center)
                    .lineLimit(4)
                Spacer(minLength: 4)
                HStack(spacing: 8) {
                    confirmationButton("返回", background: Color(red: 31 / 255, green: 31 / 255, blue: 31 / 255), action: onCancel)
                    confirmationButton("放弃", background: Color(red: 1.0, green: 69 / 255, blue: 59 / 255), action: onConfirm)
                }
            }
            .padding(.horizontal, WatchDisplayGeometry.minimumContentInset)
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
                .font(.system(size: 16, weight: .black))
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, minHeight: 46)
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
                    .font(.system(size: 20, weight: .black))
                    .multilineTextAlignment(.center)
                    .offset(y: 10)

                Text(statusText)
                    .font(.system(size: 13, weight: .semibold))
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
            .padding(.horizontal, WatchDisplayGeometry.minimumContentInset)
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
                .font(.system(size: 16, weight: .black))
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, minHeight: 46)
                .background(
                    background,
                    in: RoundedRectangle(cornerRadius: 12, style: .continuous)
                )
        }
        .buttonStyle(.plain)
        .disabled(isUploading)
    }
}
