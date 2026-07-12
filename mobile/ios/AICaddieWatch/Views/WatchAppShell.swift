import SwiftUI

/// Watch 顶层五页骨架 (control-spec 2026-07-10 §2 「球局顶层五页」 + design-system §2 「五页」).
///
/// One `TabView` with `PageTabViewStyle` — **横滑 = 翻页,永远只是翻页** (the control constitution's ONLY
/// job for a horizontal swipe). The Digital Crown is each page's single axis (not paging); there is NO
/// self-drawn 返回 / × / ∧∨ chrome (banned by the spec). Pages left → right:
///
///   ① 球局菜单 (最左, 吞并 hub) · ② 球童建议 · ③ **球道图 = 家, 居中(默认)** · ④ 计分 · ⑤ 旗向指引
///
/// The middle page (球道图) is HOME: `selection` defaults to `2` so "抬腕即在家", and from home it is one
/// swipe left to 球童 / one right to 计分 (spec §3 「家 = 球道图,居中:左一下球童、右一下计分」).
///
/// RENDERING: every page is a Canvas/VStack view (never a lazy container), so `ImageRenderer` snapshots
/// them for CI. The page-position indicator is a self-drawn on-brand `WatchPageDots` (Canvas) rather than
/// the platform dots — controllable, high-contrast, and guaranteed to render in the snapshot.
public struct WatchAppShell: View {
    /// 0 球局 · 1 球童 · 2 球道图(家)· 3 计分 · 4 旗向指引. Defaults to HOME (2).
    @State private var selection: Int
    /// Demo-only (WatchUITestRoot `app-shell-demo`): auto-cycle the 5 pages with an animated page
    /// transition so `simctl recordVideo` captures a real 横滑 walk-through. Never true in the real app.
    private let autoAdvance: Bool

    public init(selection: Int = 2, autoAdvance: Bool = false) {
        _selection = State(initialValue: selection)
        self.autoAdvance = autoAdvance
    }

    public var body: some View {
        ZStack(alignment: .bottom) {
            TabView(selection: $selection) {
                menuPage.tag(0)
                caddiePage.tag(1)
                holeMapPage.tag(2)   // 家 · 居中
                scorePage.tag(3)
                pinPointerPage.tag(4)
            }
            // Custom dots below carry the page position; hide the platform indicator to avoid double dots.
            .tabViewStyle(.page(indexDisplayMode: .never))

            WatchPageDots(count: 5, current: selection, tint: AICaddieDesignTokens.accent)
                .padding(.bottom, 3)
        }
        .background(Color.black)
        .onAppear { if autoAdvance { scheduleDemoAdvance() } }
    }

    private func scheduleDemoAdvance() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.4) {
            withAnimation(.easeInOut(duration: 0.55)) {
                selection = (selection + 1) % 5
            }
            scheduleDemoAdvance()
        }
    }

    // MARK: - Pages (sample data mirrors the per-screen snapshot tests, so the shell is self-consistent:
    // hole 4 · par 5 across 球道图 / 计分 / 旗向).

    private var menuPage: some View {
        WatchMenuView()
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    private var caddiePage: some View {
        WatchCaddieOptionsView(options: Self.sampleOptions, recommendedId: "stock")
            .padding(.horizontal, 8)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    private var holeMapPage: some View {
        WatchHoleMapView(
            holeNumber: 4, par: 5,
            frontGreen: 273, centerGreen: 287, backGreen: 300,
            playsLikeDelta: 8, lastShot: 200,
            caddieClub: "3号木", caddieNote: "推进 · 留100"
        )
    }

    private var scorePage: some View {
        WatchScoreHoleView(hole: 4, par: 5, score: 5, putts: 2, penalty: 0)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    private var pinPointerPage: some View {
        WatchPinPointerView(bearingDeg: -22, distanceYd: 287)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private static let sampleOptions: [WatchCaddieOption] = [
        WatchCaddieOption(optionId: "safe", label: "稳妥", clubName: "9号铁", carryM: 128, expectedStrokes: 3.1, confidence: "high"),
        WatchCaddieOption(optionId: "stock", label: "标准", clubName: "8号铁", carryM: 142, expectedStrokes: 3.0, confidence: "high"),
        WatchCaddieOption(optionId: "attack", label: "进攻", clubName: "7号铁", carryM: 156, expectedStrokes: 3.2, confidence: "medium"),
    ]
}

/// The 5-page position indicator — the current page lit in the accent green, the rest dim. Canvas-drawn so
/// it renders reliably in `ImageRenderer` (the platform page dots don't). This is a position readout, not a
/// control (no gesture) — so it stays within the spec's "no self-drawn nav chrome".
public struct WatchPageDots: View {
    public let count: Int
    public let current: Int
    public let tint: Color

    public init(count: Int, current: Int, tint: Color = .white) {
        self.count = count
        self.current = current
        self.tint = tint
    }

    public var body: some View {
        Canvas { ctx, size in
            let dot: CGFloat = 5
            let gap: CGFloat = 7
            guard count > 0 else { return }
            let total = CGFloat(count) * dot + CGFloat(count - 1) * gap
            var x = (size.width - total) / 2 + dot / 2
            let y = size.height / 2
            for i in 0..<count {
                let isCurrent = i == current
                let r: CGFloat = isCurrent ? dot / 2 + 0.6 : dot / 2 - 0.6
                let rect = CGRect(x: x - r, y: y - r, width: r * 2, height: r * 2)
                ctx.fill(Path(ellipseIn: rect),
                         with: .color(isCurrent ? tint : .white.opacity(0.32)))
                x += dot + gap
            }
        }
        .frame(height: 10)
        .allowsHitTesting(false)
    }
}
