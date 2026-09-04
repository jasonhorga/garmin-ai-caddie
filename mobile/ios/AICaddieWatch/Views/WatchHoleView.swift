import SwiftUI

/// Bounded vertical geometry for the standalone hole instrument. Keeping this calculation pure lets
/// the 41/45/49 mm contract be checked without relying on a simulator's SwiftUI measurement timing.
public struct WatchHoleInstrumentLayout: Equatable {
    public static let headerHeight: CGFloat = 26
    public static let sectionSpacing: CGFloat = 4
    public static let actionHeight: CGFloat = WatchDisplayGeometry.instrumentActionHeight

    public let safeRect: CGRect
    public let glanceHeight: CGFloat

    public var usedHeight: CGFloat {
        Self.headerHeight + Self.sectionSpacing + glanceHeight + Self.sectionSpacing + Self.actionHeight
    }

    public var fitsInSafeArea: Bool {
        usedHeight <= safeRect.height + 0.5
    }

    public static func resolve(for size: CGSize) -> Self {
        let safeRect = WatchDisplayGeometry.contentRect(in: size)
        let reservedHeight = headerHeight + actionHeight + sectionSpacing * 2
        let availableHeight = max(0, safeRect.height - reservedHeight)
        return Self(
            safeRect: safeRect,
            glanceHeight: WatchCaddieGlanceView.compactInstrumentHeight(for: availableHeight)
        )
    }
}

public struct WatchHoleView: View {
    public let state: WatchRoundState
    public let clubs: [String]
    public let queuedEventCount: Int
    public let phoneReachable: Bool
    public let lastPhoneAcceptedAt: String?
    public let onEvent: (WatchInputEvent) -> Void

    public init(
        state: WatchRoundState,
        clubs: [String],
        queuedEventCount: Int = 0,
        phoneReachable: Bool = false,
        lastPhoneAcceptedAt: String? = nil,
        onEvent: @escaping (WatchInputEvent) -> Void = { _ in }
    ) {
        self.state = state
        self.clubs = clubs
        self.queuedEventCount = queuedEventCount
        self.phoneReachable = phoneReachable
        self.lastPhoneAcceptedAt = lastPhoneAcceptedAt
        self.onEvent = onEvent
    }

    public var body: some View {
        NavigationStack {
            GeometryReader { proxy in
                let layout = WatchHoleInstrumentLayout.resolve(for: proxy.size)
                ZStack {
                    Color.black
                    VStack(spacing: WatchHoleInstrumentLayout.sectionSpacing) {
                        HStack(spacing: 6) {
                            Text("H\(state.hole) · P\(state.par)")
                                .font(.system(size: WatchDisplayGeometry.instrumentHeaderFontSize, weight: .black))
                                .lineLimit(1)
                                .minimumScaleFactor(0.72)
                            Spacer(minLength: 0)
                            statusText
                        }
                        .frame(width: layout.safeRect.width, height: WatchHoleInstrumentLayout.headerHeight)

                        WatchCaddieGlanceView(
                            state: state,
                            compact: true,
                            compactHeight: layout.glanceHeight
                        )
                        .frame(
                            width: layout.safeRect.width,
                            height: layout.glanceHeight,
                            alignment: .topLeading
                        )

                        HStack(spacing: 6) {
                            if !state.caddieOptions.isEmpty {
                                NavigationLink {
                                    WatchCaddieOptionsView(
                                        hole: state.hole,
                                        par: state.par,
                                        options: state.caddieOptions,
                                        recommendedId: state.offlineOptionId,
                                        route: state.holeMap?.route ?? []
                                    )
                                } label: {
                                    toolChip("球童", systemName: "figure.golf")
                                }
                            }
                            if !state.hazards.isEmpty {
                                NavigationLink {
                                    ScrollView { WatchHazardView(hazards: state.hazards).padding(8) }
                                } label: {
                                    toolChip("障碍", systemName: "exclamationmark.triangle")
                                }
                            }
                            NavigationLink {
                                WatchInputView(state: state, clubs: clubs, onEvent: onEvent)
                            } label: {
                                toolChip("记杆", systemName: "plus")
                            }
                        }
                        .frame(width: layout.safeRect.width, height: WatchHoleInstrumentLayout.actionHeight)
                    }
                    .frame(width: layout.safeRect.width, height: layout.safeRect.height, alignment: .top)
                    .position(x: layout.safeRect.midX, y: layout.safeRect.midY)
                }
            }
            .toolbar(.hidden, for: .navigationBar)
        }
        .background(Color.black)
        .ignoresSafeArea()
        .accessibilityIdentifier("watch-hole-instrument")
    }

    private var statusText: some View {
        HStack(spacing: 3) {
            Image(systemName: phoneReachable ? "iphone.radiowaves.left.and.right" : "iphone.slash")
            if queuedEventCount > 0 {
                Text("待传 \(queuedEventCount)")
                    .lineLimit(1)
            } else {
                Text(phoneReachable ? "手机已连" : "手机未连")
                    .lineLimit(1)
            }
        }
        .font(.system(size: 11, weight: .bold))
        .lineLimit(1)
        .minimumScaleFactor(0.7)
        .foregroundStyle(queuedEventCount > 0 ? AICaddieDesignTokens.confidenceColor("low") : .secondary)
    }

    private func toolChip(_ label: String, systemName: String) -> some View {
        Label(label, systemImage: systemName)
            .font(.system(size: 13, weight: .black))
            .foregroundStyle(.white)
            .lineLimit(1)
            .minimumScaleFactor(0.72)
            .frame(maxWidth: .infinity)
            .frame(height: WatchHoleInstrumentLayout.actionHeight)
            .background(AICaddieDesignTokens.hudPanel, in: Capsule())
            .contentShape(Rectangle())
    }
}
