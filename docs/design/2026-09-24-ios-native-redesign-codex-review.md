# 请 Codex 评审：iPhone 界面新版方案

- **来源**：Claude Code 云端会话，owner 要求出一版“更原生 iOS、图形化而不是控件化”的界面方案，并请 Codex 评审。
- **设计稿**：[`2026-09-24-ios-native-redesign-proposal.html`](2026-09-24-ios-native-redesign-proposal.html)，用浏览器打开即可，无外部依赖。
- **范围**：本次只有设计稿，没有改任何代码。执行状态仍以 `PROJECT_STATE.md` 为准。
- **基线**：`integration/v2` @ `602fd01c` 的 iOS 界面与数据字段。

## 1. 方案概要

设计稿共 7 个屏幕，每个都写了“现在 / 新版 / 用到的原生组件 / 数据字段”：

| # | 屏幕 | 主要变化 | 主要涉及文件 |
|---|---|---|---|
| 01 | 首页 | 根视图改为 `TabView`（打球 / 备战 / 成绩 / 球包）；进行中卡片带当前洞小地图；上一场画成 18 洞逐洞柱 | `AICaddieApp.swift`、`RoundHomeView.swift` |
| 02 | 开一场 | 九洞组合画成“9 个点一圈”，点选拼 18 洞；Tee 用真实颜色标志加码数、评分/坡度；显示 18 洞长度柱状图。去掉 `Picker(.menu)`、单选行和 `confirmationDialog` | `StartRoundView.swift` |
| 03 | 打球 | 全屏地图；顶部毛玻璃胶囊；果岭旁竖向前/中/后刻度；推荐落点画 p10–p90 散布椭圆；障碍直接标“到/越”码数；底部为可拖动的 sheet（`presentationDetents`） | `CurrentHoleView.swift`、`LiveHoleComponents.swift`、`HoleImageMapView.swift` |
| 04 | 记分 | 一屏记完：点成绩形状选杆数，点果岭上的球选推杆，点球道左/中/右选开球，罚杆为 0/+1/+2，默认选中手表记到的杆数 | `LiveScoreConfirmationView.swift` |
| 05 | 成绩 | 四个阶段各一张图放在同一屏（开球扇形、攻果岭方向弧、推杆分布、杆型相对标准杆）；顶部近 20 场面积折线 | `ResultsView.swift`、`StatsView.swift`、`PerformancePhaseGraphics.swift` |
| 06 | 单场复盘 | 九洞小地图墙代替计分表，每洞画出实际击球线和成绩形状，点开即现有的逐杆地图 | `RoundReviewView.swift`、`RoundShotMapView.swift` |
| 07 | 球包 | 每支杆一条 p10–p90 距离带加中位数；与上一支杆中位数差超过 15 码时标出“断档”；拖动中位数改码数 | `ClubSettingsView.swift`、`ClubGappingLadder.swift` |

原则：只改界面层，不改后端接口和数据模型。设计稿中的数字都是示意。

## 2. 请 Codex 重点确认

1. **数据是否真的在客户端可用**
   - 打球屏的散布椭圆用 `CaddiePlanOption.p10M / p90M`，“预计 4.1 杆”用 `expectedStrokes`（`CaddiePlanView.swift:142-148`）。
   - 这些字段在实时球童响应里是否稳定有值？还是只在部分路径下有？
2. **TabView 迁移风险**
   - 现在的根是 `RoundHomeView` 的 `NavigationStack(path:)`；打球屏靠它隐藏导航栏并切到深色。
   - 改成 `TabView` 后，打球全屏态、Watch 事件桥和深链是否会受影响？
3. **打球屏全屏地图**
   - 现有 `LivePlayPanel` 叠在地图下方；改成浮层 sheet 后，地图的缩放/拖动手势和 sheet 拖动是否冲突？
   - 叠加层坐标是否仍然可靠（overlay 像素坐标和 topo 帧）？
4. **截图测试**
   - `DesignSnapshotTests` 和 `test_mobile_contracts.py` 里有大量源码字符串断言，改版会批量失效。
   - 请给出更新这些测试的建议方式。
5. **分期是否合理**，是否有需要提前的依赖。
6. **旧组件清理**：`LiveDistanceReadout`、`LiveCaddieStrip`、`LivePlayScoreSteppers`、`moreAdjustCard` 目前无调用方；`StatsView` 的 `.all` 模式和 `CaddiePlanView` 只在测试里用。能否在第 4 期删除？

## 3. 分期（设计稿“落地顺序”一节）

1. **打球屏**：全屏地图 + 半屏面板 + 一屏记分。
2. **骨架**：`TabView` + 首页 + 开一场。
3. **成绩与复盘**：四阶段图 + 九洞小地图墙。
4. **球包与收尾**：距离带球包；可选 Live Activity / 灵动岛；清理旧组件。

每期都可以单独上线，并走现有 Native CI 截图测试和 TestFlight 内测。

## 4. 待 owner 决定

1. 打球屏是否改为全屏地图、面板浮在上面。
2. 是否增加独立的“球包”标签。
3. 是否做 Live Activity / 灵动岛（需要新增 Widget 扩展和对应的签名/TestFlight 配置）。

## 5. 交接信息（AGENTS.md §6）

- **类型**：设计与评审请求，不含代码改动。
- **工作位置**：Claude Code 云端临时容器。
- **创建的资源**：
  - 本文件与设计稿 HTML（仓库内）；
  - 一个私有的 claude.ai artifact 预览页，仅 owner 可见。
  - 没有创建容器、端口、隧道或卷，也没有登录 homeserver。
- **到期与清理**：云端容器闲置后自动回收。
