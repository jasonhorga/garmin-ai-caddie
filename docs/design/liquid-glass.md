# Caddie 液态玻璃（Liquid Glass）界面重新设计：iPhone + Apple Watch

> 卡：C388（Jason 11-08 经土土「趁没事用 claude 把 caddie 的液态玻璃 UI/UE 认真再设计一下 包括 ios 和手表」）。
> 本文是设计定稿和实现拆分的唯一依据；旧评估 `par1025/investigate-C166-r2.md` 与旧 C167–C173 只作参考，已按本文改写（见第 6 节）。
> 截图：`docs/design/shots/before/`（现状，来自 CI 模拟器）；`docs/design/shots/after/`（实现后，由每批实现补齐，见第 6 节各批验收）。
> 基线：main 35a402af（2026-11-07）。截图来源：native-mobile fixture run 42031847103（c142 分支，11-05，与 main 界面一致）的 `design-snapshots`（iPhone 390×844pt）、`real-screenshots`（iPhone 393×852pt 真 App UI 测试）、`watch-snapshots`（41mm、46mm）。全部为 fixture 数据，无真实用户数据。

## 0. 已定的事（不重议）

| 定案 | 出处 | 本设计怎么落 |
|---|---|---|
| 菜单和屏幕上所有可按的东西按液态玻璃设计框架做，全部统一、不留例外 | Jason 10-29 17:0x / 10-29「再评估评估 能不能都统一」 | 每个可点控件只用系统控件与系统样式（第 1.3 节表）；确需自定尺寸的写明理由（第 5 节） |
| 最低 iOS 26 / watchOS 26，不做旧外观兼容 | Jason 10-29 18:2x「1，只支持 26」 | 批 0 先提版本；全文不写 `#available` 兜底 |
| 跟随系统深色先不做 | 同上「2，先不做」→C174 | 保留现状：普通页浅色、打球页深色（系统 API 强制），不改 231 处写死颜色 |
| 洞屏底图永不出线条图 | C241 定案 | 本设计只动浮在地图上的控件层，不碰底图选择：精细图→Garmin 底图→原地换；都没有时中性底+「地图准备中」 |
| iPad、横屏 | C170/C171 11-05 土土收卡 | 不在本卡范围（本卡只做 iPhone 竖屏 + 手表）；布局按系统安全区和实测尺寸写，不按机型，以后做 iPad 时不返工 |

## 1. 设计原则（球场上的真实使用）

### 1.1 使用场景决定的硬约束

| 场景 | 约束 | 设计对策 |
|---|---|---|
| 单手、拇指操作（另一手拿杆） | 高频操作必须在屏幕下 1/3 的拇指区 | 打球页「记一杆」「记分」放底部；开局「开始」、首页「继续/打一场球」放底部浮动玻璃按钮；搜索框在底部（iOS 26 系统搜索 tab） |
| 戴手套 | 触控精度差 | 主操作 ≥ 60pt（记一杆 76pt），其余 ≥ 44pt（HIG 最小值）；相邻可点控件间距 ≥ 8pt；手表主按钮用系统 toolbar 尺寸，不自画小点击区 |
| 强光 | 低对比度看不清 | 关键数字（中距离、杆数）用系统粗体大字 + `monospacedDigit`；玻璃上的文字靠系统 vibrancy；打球页保持深色外观；「记一杆」用 `.glassProminent` 实色 tint，对比度实测 ≥ 4.5:1（文字）/ ≥ 3:1（按钮边缘对地图） |
| 走路中看一眼 | 一眼 ≤ 1 秒读到 | 每屏只有一个最大信息：打球页=到果岭中距离；手表=距离大字；成绩=差点；其余降级 |
| 不想误触 | 口袋/走路误碰 | 破坏性操作（放弃本场、删除一杆）一律系统 `confirmationDialog` + `role: .destructive`；记分保存有撤销（现有行为不变） |

### 1.2 液态玻璃怎么用（Apple HIG，iOS 26 / watchOS 26）

1. **玻璃只给「控件层」，不给「内容层」**。导航栏、toolbar、tab bar、浮在地图上的按钮和信息牌是玻璃；列表行、成绩卡片、计分卡表格是内容，不加玻璃（HIG：Liquid Glass 用于浮在内容之上的导航与控件）。
2. **系统给的玻璃优先**：NavigationStack 的导航栏/toolbar、TabView 的 tab bar、sheet（部分高度时）、Menu、confirmationDialog 在 iOS 26 自动是玻璃，**不手工加** `.glassEffect`。
3. **浮在地图上的自定控件**：按钮用 `.buttonStyle(.glass)`，主操作用 `.buttonStyle(.glassProminent)` + `.tint`；非按钮的信息牌（距离牌）用 `.glassEffect(.regular, in: .rect(cornerRadius: 22))`。相邻的玻璃元素放进同一个 `GlassEffectContainer`（共享采样、可以互相融合变形）。
4. **tint 只给每屏一个主操作**（HIG：tint 少用）。打球页=记一杆；开局=开始；首页=继续/打一场球；手表=记一杆。
5. **形状同心**：浮层按钮用胶囊/圆，卡片圆角跟随系统（`ConcentricRectangle` / `.rect(cornerRadius: .containerConcentric)`），不写死 12/16/20 混用。
6. **动效**：系统转场（push、sheet、zoom navigation transition）；玻璃控件之间展开/收起用 `glassEffectID` + `withAnimation`（例：底部「记分」点开计分弹层）；尊重「减弱动态效果」「降低透明度」（系统玻璃自动处理，我们不另写）。记一杆、保存记分用 `.sensoryFeedback`。
7. **字号**：普通页一律 Dynamic Type 文字样式（`.largeTitle`…`.caption2`）；地图上的标签、距离大字、手表距离大字是「和图/表盘尺寸绑定的读数」，用固定 pt + `minimumScaleFactor`，写入第 5 节理由表。

### 1.3 控件选型总表（iPhone）

| 用途 | 选用 | 不再用 |
|---|---|---|
| 页面返回、标题、页内操作 | `NavigationStack` + 系统返回 + `.toolbar`（`.topBarTrailing` 等） | 自画圆形返回钮、自画顶栏 |
| 关闭/完成 sheet | toolbar 里 `Button(role: .close)` / `Button(role: .confirm)`（iOS 26） | 自画 ✕、自画「保存」胶囊 |
| 一组 2–4 个互斥选项 | `Picker` + `.pickerStyle(.segmented)` | 自画分段胶囊 |
| 更多操作（≥2 个次要操作） | `Menu`（toolbar 里 `ellipsis`） | 并排小胶囊按钮 |
| 列表、设置 | `List` / `Form`（`.insetGrouped`），`NavigationLink`，`swipeActions` | 自画行卡片 + `.plain` 按钮 |
| 页内主按钮 | `.buttonStyle(.borderedProminent)` + `.controlSize(.large)` | 自画填充圆角矩形 |
| 页内次按钮 | `.buttonStyle(.bordered)` | 自画描边 |
| 浮在地图/底部的按钮 | `.buttonStyle(.glass)` / `.glassProminent`，放进 `GlassEffectContainer` | 实心白圆 + 手写阴影 |
| 破坏性确认 | `confirmationDialog` + `role: .destructive` | 自画红字按钮、自画确认页 |
| 进度 | `ProgressView`（线性/圆形） | 自画进度条 |
| 搜索 | `.searchable` + `Tab(role: .search)`（底部搜索） | 自画搜索框 |
| 数字增减（记分） | 系统 `.glass` 按钮组成的增减控件（理由见第 5 节） | 自画 ± 方块 |

### 1.4 控件选型总表（Apple Watch）

| 用途 | 选用 | 不再用 |
|---|---|---|
| 列表、菜单、设置类页面 | 每页包 `NavigationStack` + `List` + toolbar 系统样式返回（路由状态机不变） | 自画 40pt 黑圆返回（WatchInstrumentBackButton）；左边缘右滑是手势，保留 |
| 打球仪表页的角落按钮（菜单 ☰、记一杆 +） | `.toolbar { ToolbarItem(placement: .topBarLeading/.bottomBar…) }`，系统玻璃按钮，记一杆 `.glassProminent` 绿 tint | 自画角落圆钮、手写安全区偏移 |
| 页面切换 | `TabView` + `.tabViewStyle(.verticalPage)`，表冠翻页 | — |
| 数字调整（杆数/推杆/罚杆） | 表冠 `digitalCrownRotation` + 系统 `.glass` ± 按钮 | 自画 ± 方块 |
| 确认（结束本场、放弃） | 保留为状态机里的一屏，按钮换系统 `.borderedProminent`（`role: .destructive`）/ `.bordered` | 自画胶囊 |

## 2. iPhone 逐屏设计

每屏格式：前（现状截图）｜后（实现后截图，批号见第 6 节）；目的；信息层级（1 最重要）；控件选型；交互与动效；现状 → 改法。

### 2.0 导航结构（前后对比）

**前**（代码盘点，main 35a402af）：根是 `RoundHomeView` 的单一 `NavigationStack(path:)`（RoundHomeView.swift:1043，路由 `HubRoute`）。首页是一张长页（问候语、打一场球大卡、快捷球场、上一场、最近走势、成绩入口），右上 toolbar 齿轮开设置 sheet（:1093；球包在设置里 push，ClubSettingsView）。成绩各页 push。打球页是同一个栈里的洞 pager（`TabView(.page)`，:1461），每洞一页 `CurrentHoleView`，它把导航栏藏掉（CurrentHoleView.swift:1295）自己在地图上画顶栏和按钮。全 App 95 个 `.buttonStyle(.plain)` 自画按钮、0 个 `.glass`、11 处 `.ultraThinMaterial` 手工玻璃；只有 10 个 `.bordered`、6 个 `.borderedProminent`。

**后**：

```
TabView（iOS 26 浮动玻璃 tab bar，滚动时 .tabBarMinimizeBehavior(.onScrollDown) 收起）
├─ 打球（首页）    NavigationStack：首页 → 开局 → 球场详情；右上 toolbar：设置
├─ 成绩            NavigationStack：成绩 → 表现分析 / 时间与频率 / 成绩分布 / 球场 / 全部球局 → 复盘 → 落点图
├─ 球包            NavigationStack：球包 → 球杆编辑
└─ 搜索（Tab(role: .search)，在 tab bar 最右、拇指区）  搜索球场 → 开局
打球页：仍是「打球」tab 栈里的洞 pager（路由不变），进入后 `.toolbar(.hidden, for: .tabBar)` 藏 tab bar；顶栏用系统 toolbar；果岭详情 fullScreenCover；sheet：记分、选杆、计分卡、转场、结束本场
```

- 理由：tab bar 和底部搜索都在拇指区，是 HIG 在 iOS 26 推荐的顶层结构；三个顶层目的地（打球、看成绩、管球包）各自保留自己的返回栈，切 tab 不丢位置。打球中不显示 tab bar，避免误触切走。球包从「设置里的一项」升为 tab：打球前看/改球杆距离是高频事，球童建议也依赖它。
- 进行中的球局：tab bar 上方用 `.tabViewBottomAccessory` 放「进行中 · 第 7 洞 · +2 ›」一条（系统玻璃附件栏），任何 tab 一点就回到打球页——替代现在只在首页才有的「继续」卡。
- 功能不变：所有页面、入口、数据都在，只是位置从「首页上的入口卡」变成 tab；首页仍保留成绩/球包摘要卡，点了切到对应 tab。

### 2.1 登录

| 前 | 后 |
|---|---|
| ![](shots/before/ip-signin-390.png) | 批 1 补 `after/ip-signin-390.png` |

- 目的：第一次打开时用 Apple 登录。
- 层级：1 App 名和一句说明；2 Apple 登录按钮。
- 控件：系统 `SignInWithAppleButton`（`.signInWithAppleButtonStyle(.black)`，高 50pt，放底部安全区内 `safeAreaInset(edge: .bottom)`）；标题用 `.largeTitle.bold()`，说明 `.body` 次要色。
- 前 → 后：现在按钮在屏幕中部（模拟器截图里是系统占位黄块）；改到底部拇指区，上方留品牌区。行为不变。

### 2.2 首页（打球 tab）

| 前 | 后 |
|---|---|
| ![](shots/before/ip-home-390.png) ![](shots/before/ip-home-393.png) ![](shots/before/ip-home-active-390.png) | 批 1 补 `after/ip-home-390.png`、`after/ip-home-active-390.png`、`after/ip-home-430.png`（大屏） |

- 目的：一眼知道「现在该干什么」：有进行中的球局就继续，没有就开一场。
- 层级：1 主操作（继续第 N 洞 / 打一场球）；2 附近或常去球场（快捷开局）；3 上一场成绩；4 最近走势。
- 控件：
  - 导航栏：`.navigationTitle("晚上好")` + `.navigationBarTitleDisplayMode(.large)`；右上 `ToolbarItem(.topBarTrailing)` 设置（`Button("设置", systemImage: "gearshape")`，系统玻璃）。去掉自画齿轮圆钮。
  - 主操作：页面底部 `safeAreaInset(edge: .bottom)` 一个 `.buttonStyle(.glassProminent)` + `.controlSize(.extraLarge)` 全宽按钮：无球局「打一场球」、有球局「继续 · 第 7 洞」（tint 球场绿）。现在的深绿大卡改成内容卡（球场名、已打 N 洞、对标准杆、洞色点条），不再自己当按钮——点卡片进打球页仍可用（`NavigationLink`/`.contentShape` + 系统按下效果），但主按钮只有底部那一个。
  - 快捷球场：横向 `ScrollView` 里 `.buttonStyle(.bordered)` + `.buttonBorderShape(.capsule)`，前面系统图标 `location.fill`（附近）/`clock`（常去）。
  - 上一场、最近走势：内容卡（不加玻璃），整卡 `NavigationLink`，右侧系统 chevron 由 List/NavigationLink 自带，不手画。
- 交互与动效：进打球页用 `.navigationTransition(.zoom(sourceID:in:))` 从主按钮放大展开（iOS 26 系统转场）；下拉刷新 `.refreshable`。
- 前 → 后：主操作从首页中上部的自画大卡移到底部拇指区；顶部齿轮换系统 toolbar；成绩/球包入口卡改为 tab（首页只留摘要）。

### 2.3 首页·快捷球场与搜索入口

| 前 | 后 |
|---|---|
| ![](shots/before/ip-home-quick-390.png) | 批 1 补 `after/ip-home-quick-390.png` |

- 目的：常去球场一点即开局；找新球场从底部搜索 tab 进。
- 控件：同 2.2 的快捷胶囊；搜索 tab（`Tab(role: .search)`）点开后搜索框在底部（iOS 26 iPhone 默认位置），结果页同 2.4。
- 前 → 后：现在首页上半部只有问候+大卡，快捷球场是一排小文字胶囊；改为系统 bordered 胶囊、≥44pt 高。

### 2.4 开局·选球场（搜索/附近）

| 前 | 后 |
|---|---|
| ![](shots/before/ip-start-search-390.png) ![](shots/before/ip-start-search-393.png) ![](shots/before/ip-start-nearby-390.png) | 批 2 补 `after/ip-start-search-390.png`、`after/ip-start-nearby-390.png` |

- 目的：到了球场，最快找到「我脚下这个球场」。
- 层级：1 附近（按距离，带「已下载」状态）；2 最近打过；3 搜索结果。
- 控件：`List` 分 Section（附近 / 最近 / 搜索结果）；`.searchable(text:, placement: .automatic)`（在搜索 tab 里时系统放底部）；行用 `LabeledContent` 风格：球场名 `.headline`、距离·洞数 `.subheadline` 次要色、已下载用系统 `checkmark.circle.fill` 或进度 `ProgressView(value:)`；定位中用 `ProgressView` + 「正在等待定位…」系统样式行；失败行用 `ContentUnavailableView` + 「重试」`.bordered`。
- 交互：点行 push 开局设置（2.5）；滑动行 `swipeActions` 无（不增功能）。
- 前 → 后：自画搜索框、自画返回圆钮、自画选中行（绿底+勾）→ 系统 searchable、系统返回、系统 List 选中态。

### 2.5 开局·设置（前后九/起始半场、发球台）与球场详情

| 前 | 后 |
|---|---|
| ![](shots/before/ip-start-setup-390.png) ![](shots/before/ip-start-setup-393.png) ![](shots/before/ip-course-detail-390.png) | 批 2 补 `after/ip-start-setup-390.png`、`after/ip-course-detail-390.png` |

- 目的：确认从哪个 9 洞开始、打哪个发球台，然后开打。
- 层级：1 球场名；2 从哪个 9 洞开始；3 发球台（颜色+码数）；4 开始。
- 控件：
  - 起始 9 洞：选项 ≤4 个时 `Picker(.segmented)`（A 场 / B 场 / C 场），每段下方的「9 洞 · 3393 码」放在 Picker 下面一行 `.footnote`；>4 个时用 `List` + 勾选。
  - 发球台：`List` 行（色点 `Circle().fill(teeColor)` + 名称 + 码数），选中用系统 `checkmark`；不再用自画大色圆。
  - 开始：`safeAreaInset(edge: .bottom)` 里 `.glassProminent` + `.controlSize(.extraLarge)` 全宽，tint 球场绿。
  - 顶部：系统返回（去掉文字「返回」自画按钮）；球场名做 `.navigationTitle`。
  - 球场详情：`ScrollView` 内容卡；「最难的三个洞」横向卡片；「常打的组合」`DisclosureGroup`（替代自画「全部 4 种组合 ⌄」）。
- 前 → 后：底部「开始」现在是自画绿色矩形，改系统玻璃突出按钮；半场三块自画卡改 segmented。

### 2.6 打球页（含开局前预览；核心页）

| 前 | 后 |
|---|---|
| ![](shots/before/ip-live-390.png) ![](shots/before/ip-live-393.png) ![](shots/before/ip-prep-393.png) | 批 3 补 `after/ip-live-390.png`、`after/ip-live-430.png`、`after/ip-live-satellite-390.png`（亮卫星 Garmin 底图）、`after/ip-live-topo-390.png`（深色精细图）、`after/ip-prep-390.png` |
| ![](shots/before/ip-live-garmin-390.png) ![](shots/before/ip-live-garmin-nofix-390.png) ![](shots/before/ip-live-offcourse-390.png) ![](shots/before/ip-score-cancelled-393.png) | 同上（Garmin 底图有/无定位、离场、已开打带顶部小胶囊四种状态各补一张） |

- 目的：走路中看一眼就知道「到果岭还有多远、这杆怎么打」，单手点「记一杆」。
- 层级：1 到果岭中距离（大字）；2 当前洞号/Par/码数；3 前/后距离、球童建议路线与落点；4 障碍翻页、图层；5 计分卡、结束本场、洞位图等次要操作。
- 布局（竖屏，地图铺满全屏 `ignoresSafeArea()`，控件全部在系统安全区内）：

```
┌───────────────────────────────┐
│ ‹  1 · Par 4 · 410 码      ⋯ │ ← 系统 toolbar（玻璃）：返回 / 标题+副标题 / 更多 Menu
│    第 1 杆 · T 台 ⌄            │   副标题是发球台 Menu（换 T 台）
│                     ┌──────┐ │
│                     │前 373│ │ ← 距离牌：.glassEffect(.regular, .rect(cornerRadius: 22))
│                     │ 364  │ │   中距离 64pt 粗体 monospacedDigit，强光下最醒目
│                     │后 355│ │
│ (◎)                 └──────┘ │ ← 左侧竖排 .glass 圆钮 44pt：图层（路线/障碍）、洞位图
│ (≡)        [地图]             │
│                               │
│  ╭ 球道沙坑 2/2  ‹ › ╮        │ ← 障碍翻页条：.glass 胶囊（同一 GlassEffectContainer）
│ ( 记分 )          (＋ 记一杆) │ ← 底部 safeAreaInset：记分 .glass 60pt；记一杆 .glassProminent 76pt
└───────────────────────────────┘
```

- 控件：
  - 顶栏：去掉 `.toolbar(.hidden)`，用所在 NavigationStack 的系统 `.toolbar`（批 3 第一步先在洞 pager 里实测 toolbar 能否随当前页正确切换；不能就退一步：同样位置用 `.buttonStyle(.glass)` 按钮 + `GlassEffectContainer` 叠在地图上，仍是系统样式，不再自画圆）：`.topBarLeading` 返回（系统 chevron）；`.principal` 标题「1 · Par 4 · 410 码」+ `.navigationSubtitle`「第 1 杆 · T 台」（副标题点开是发球台 `Menu`，替代现在的自画「第 1 洞 · 记第一杆即开打 ⌄ T 台」小胶囊）；`.topBarTrailing` 一个 `Menu`（`ellipsis`）：计分卡、洞位图、球洞调整（加打/移除）、结束本场（`role: .destructive`，进确认）。现在并排的「计分卡」「结束本场」两个小胶囊（`ip-score-cancelled-393`）收进 Menu。
  - 距离牌：不是按钮，是信息牌，用 `.glassEffect`；点它切「到旗杆/到果岭中」保持现有行为（如有）。
  - 记一杆：`.buttonStyle(.glassProminent)`、`.tint(近白)`、`.foregroundStyle(深色)`、直径 76pt、系统 `plus` 图标+「记一杆」两行字；tint 候选（A 近白 / B 系统黄）由批 3 在亮卫星球道、沙坑、深色精细图 × 「降低透明度」开/关 6 张截图上量对比度后定：文字对按钮 ≥ 4.5:1、按钮边缘对周围地图 ≥ 3:1，都达标选 A（最接近现在）。
  - 记分：`.glass` 圆 60pt + 下方「记分」`.caption`。点开是记分弹层（2.8），按钮和弹层用 `glassEffectID` 做展开变形。
  - 左侧图层/洞位图：`.glass` 圆 44pt，`Label` 只显图标（`.labelStyle(.iconOnly)`），带 `accessibilityLabel`。
  - 障碍翻页条：`.glass` 胶囊，‹ › 是系统 `Button(systemImage:)`，44pt 点击区。
  - 所有浮层放进一个 `GlassEffectContainer(spacing: 12)`，玻璃互相融合、采样一致。
- 取景：地图按「系统安全区 + 实测浮层框」算四边留白，替换写死顶部 80、底部 34（现在 32 处引用）；浮层尺寸变了取景跟着变，不被按钮盖住。点击坐标换算用同一份留白。
- 底图：完全不动（C241：精细图→Garmin 底图→原地换；都没有时中性底+「地图准备中」；没投影时图上写「路线等精细地图出来后显示」）。
- 交互与动效：左右滑切洞（现有）；记一杆成功 `.sensoryFeedback(.success)`；记分展开用玻璃变形；减弱动态效果时只淡入淡出（系统自动）。
- 开局前预览（prep）：同一页面，底部「记一杆」换成「开始第 1 洞」（同位置、同样式），顶栏标题同上。
- 前 → 后：实心白圆+手写阴影 → 系统 glassProminent；自画顶栏 → 系统 toolbar（自带玻璃和返回）；两个顶部小胶囊 → Menu；写死 80/34 → 实测。

### 2.7 打球页·球童打法、障碍、果岭详情

| 前 | 后 |
|---|---|
| ![](shots/before/ip-live-plan-393.png) ![](shots/before/ip-live-hazard-393.png) ![](shots/before/ip-green-390.png) | 批 3 补 `after/ip-live-plan-390.png`、`after/ip-live-hazard-390.png`、`after/ip-green-390.png` |

- 目的：看这洞的打法路线（球童建议）、某个障碍的前后距离、果岭前后左右与旗位。
- 控件：打法路线、障碍是地图上的叠加（内容层，不是玻璃）；路线标签「一号木 230」保留现有画法（和图绑定，第 5 节）；障碍翻页条见 2.6。果岭详情（现为 fullScreenCover，CurrentHoleView.swift:1667，左上自画黑圆 chevron LiveGreenDetailView.swift:246）：包一层 `NavigationStack`，toolbar `.topBarLeading` `Button(role: .close)`；下方读数卡（发球台到旗 315 码、前/后/左/右）是内容卡，`Grid` 排版，数字 `.title.monospacedDigit()`。
- 盘点发现 `LiveHazardDetailView`、`CaddiePlanView`、`LivePlayHeader`、`LiveCaddiePlanPanel`、`LiveHazardBrowserPanel`、旧 `RecordShotButton`/`HoleScoreSteppers` 已不在 App 里出现，只剩快照测试引用 → 批 3 删除（连同只测它们的快照）。
- 前 → 后：果岭页自画返回 → 系统关闭；读数卡字号改 Dynamic Type（上限 `.accessibility2`，地图区不缩）。

### 2.8 打球弹层：记分、选杆提示、计分卡、转场、结束本场

| 前 | 后 |
|---|---|
| ![](shots/before/ip-score-390.png) ![](shots/before/ip-shot-club-393.png) ![](shots/before/ip-scorecard-390.png) ![](shots/before/ip-scorecard-393.png) ![](shots/before/ip-turn-390.png) ![](shots/before/ip-summary-390.png) ![](shots/before/ip-summary-393.png) | 批 4 补 `after/ip-score-390.png`、`after/ip-shot-club-390.png`、`after/ip-scorecard-390.png`、`after/ip-turn-390.png`、`after/ip-summary-390.png` |

- **记分**（目的：洞打完 3 秒内记好杆数、推杆、开球方向、罚杆）：
  - 系统 `.sheet`，`.presentationDetents([.medium, .large])`，`.presentationBackground` 不设（iOS 26 部分高度 sheet 自动玻璃）。
  - toolbar：`.cancellationAction` `Button(role: .cancel)`（替代右上自画「取消」）；`.confirmationAction` 无——保存放底部。
  - 杆数：一排 `.glass` 圆钮（信天翁…+3，6 个，≥ 52pt），当前选中用 `.glassProminent` tint；推杆 0/1/2/3/4+：`Picker(.segmented)`；开球偏左/球道/偏右：`Picker(.segmented)` 带图标；罚杆：系统 `Stepper`（理由：0–3 小范围，系统 Stepper 足够，且有 VoiceOver 调整）。
  - 保存：底部 `.glassProminent` 全宽「保存 5 杆 · 去第 2 洞」，`.sensoryFeedback(.success)`。
- **选杆提示**（这一杆用了什么球杆？；代码在 LiveHoleComponents.swift:1125，归批 3）：`.sheet` `.presentationDetents([.medium])`；`List` 行「一号木 230 码」+ 右侧「球童建议」`.badge`；「跳过球杆（位置已记录）」放 toolbar `.cancellationAction`。
- 记分弹层现在写死 `.height(400/500)` 且禁止下滑关闭（LiveScoreConfirmationView.swift:33-35）→ 改 `.medium/.large`，保留「禁止下滑关闭」（防误触丢记分，现有行为）。
- **计分卡**：`.sheet` `.large`；toolbar 左 `Button(role: .close)`（替代自画 ✕ 圆，LiveRoundScorecardView.swift:106-125）；内嵌的「球洞调整」区代码在 CurrentHoleView.swift:6094，已经是系统 Menu，批 4 不动；表格 `Grid`（内容层），当前洞用系统 tint 圈；「改成绩」「球洞调整」放底部 `.bordered` / 列表行。
- **转场（B 场打完了）**：`.sheet` `.medium`；三个半场选项 `Picker(.segmented)` 或 List（>3 时）；「接着打 C 场」`.glassProminent`；「不打了 · 只打 9 洞」`.bordered`；「稍后」toolbar `.cancellationAction`。
- **结束本场/汇总**：`.sheet` `.large`；「保存并结束」`.glassProminent`；「继续打球」`.bordered`；「放弃本场」`.bordered` + `role: .destructive`，点后 `confirmationDialog`（现有确认语不变）。
- 前 → 后：自画白胶囊/红字按钮、自画顶部 grabber 和 ✕ → 系统 sheet、系统 close/cancel、系统按钮样式。保存、撤销、记分写入逻辑不动。

### 2.9 复盘：全部球局、单场复盘、落点图、编辑

| 前 | 后 |
|---|---|
| ![](shots/before/ip-history-393.png) ![](shots/before/ip-review-390.png) ![](shots/before/ip-review-393.png) ![](shots/before/ip-shotmap-390.png) ![](shots/before/ip-shotmap-393.png) ![](shots/before/ip-edit-390.png) ![](shots/before/ip-edit-393.png) | 批 4 补 `after/ip-history-390.png`、`after/ip-review-390.png`、`after/ip-shotmap-390.png`、`after/ip-edit-390.png` |

- 全部球局：`List`（按月 Section）+ `.searchable`（球场或日期）；筛选「所有年份 / 所有球场 / 9 洞」改 toolbar `Menu`（`line.3.horizontal.decrease`），去掉自画筛选胶囊行。
- 单场复盘：系统返回；toolbar 右 `ShareLink`（替代底部自画「分享」大按钮）；计分卡 `Grid`（内容层）。
- 落点图：push 页，地图铺满；toolbar 左 `Button(role: .close)`、标题「第 1 洞 · Par 4」、右「编辑」（系统 `EditButton` 语义）；底部洞条：横向 `ScrollView` 里 `.glass` 胶囊（每洞一个，选中 `.glassProminent`）放 `safeAreaInset(edge: .bottom)`，一个 `GlassEffectContainer`。
- 盘点发现的缺陷：从「球场 → 洞历史」push 进落点图时 `onClose` 为空、导航栏又被藏（RoundShotMapView.swift:741；StatsView.swift:512），页面上没有返回钮，只能边缘右滑。改成系统 toolbar 后两条入口都有系统返回/关闭（批 4 验收）。
- 编辑：toolbar 左「取消」`role: .cancel`、右「保存」`role: .confirm`；推杆/罚杆 系统 `Stepper` 放底部玻璃条；删除一杆 `confirmationDialog`。
- 前 → 后：自画 ✕/编辑/保存胶囊、自画洞条 → 系统 toolbar 与玻璃胶囊。

### 2.10 成绩（tab）及子页

| 前 | 后 |
|---|---|
| ![](shots/before/ip-results-390.png) ![](shots/before/ip-results-393.png) ![](shots/before/ip-analysis-390.png) ![](shots/before/ip-time-390.png) ![](shots/before/ip-time-393.png) ![](shots/before/ip-distribution-390.png) | 批 1 补 `after/ip-results-390.png`、`after/ip-analysis-390.png`、`after/ip-time-390.png`、`after/ip-distribution-390.png` |

- 目的：回家后看「我差点多少、哪里丢杆」。
- 层级：1 差点估算（大字）；2 走势图；3 近 10 场均杆/最佳/场数；4 最近球局；5 分析入口。
- 控件：tab 根 `.navigationTitle("成绩")` 大标题；范围「近 10 场 / 近 20 场 / 近一年 / 全部」与粒度「逐场 / 月 / 季 / 年」都改 `Picker(.segmented)`（现在是自画分段胶囊）；分析入口是 `NavigationLink` 内容卡；空/加载/部分失败用 `ContentUnavailableView` / `ProgressView` / 系统 `.bordered`「重试」。
- 前 → 后：自画返回圆钮去掉（tab 根无返回）；自画分段 → 系统 segmented；数字 `.largeTitle.monospacedDigit()`。

### 2.11 球包（tab）

| 前 | 后 |
|---|---|
| ![](shots/before/ip-bag-390.png) ![](shots/before/ip-bag-edit-390.png) ![](shots/before/ip-bag-add-390.png) | 批 1 补 `after/ip-bag-390.png`、`after/ip-bag-edit-390.png` |

- 现状：在设置 sheet 里 push（ClubSettingsView.swift:108），编辑是写死 `.medium` 的 sheet 加自画「完成」（:344）。
- 控件：tab 根 `.navigationTitle("球包")`；`List`，每行球杆名 + 距离条（内容，保留现有画法）+ 中位数；toolbar 右 `Button("添加球杆", systemImage: "plus")`（替代自画「+ 球杆」文字）；编辑用 push 页 `Form`（名称、显示距离），删除 `swipeActions(role: .destructive)`；恢复中/失败用系统 `ProgressView` / 带「重试」的 `ContentUnavailableView`。

### 2.12 设置（打球 tab 右上进入）

| 前 | 后 |
|---|---|
| ![](shots/before/ip-settings-390.png) ![](shots/before/ip-settings-offline-390.png) ![](shots/before/ip-settings-prefetch-390.png) | 批 1 补 `after/ip-settings-390.png`、`after/ip-settings-offline-390.png` |

- 控件：`Form`（`.insetGrouped`）分 Section：账号与球包（同步状态 `LabeledContent` + 系统 `ProgressView`）、离线球场（每行 `ProgressView(value:)` + 「已下载 7/18 洞」）、数据与网络（`Toggle` 蜂窝下载）、服务器与 Garmin 会话、退出登录（`role: .destructive` + `confirmationDialog`）；以 sheet 呈现，toolbar `Button(role: .close)`。
- 现状：已经是 NavigationStack + List + toolbar「完成」（RoundHomeView.swift:2224、:2326），改动最小：「完成」换 `Button(role: .close)`，离线球场自画进度条 → `ProgressView(value:)`，球包入口移走（成为 tab）。

## 3. Apple Watch 逐屏设计

手表的使用方式：抬腕 ≤ 2 秒看距离，偶尔点一下记一杆，洞打完转表冠记分。原则：仪表页画面（距离大字、球洞图、果岭图）不动，只把**按钮**换成系统 toolbar 按钮——它们由系统放在每种表盘的安全角落，点击区由系统给，这是解决 #418/#422 四次「底部点不中」（49mm 记一杆首点无效、41mm 计分卡第 4 行、46/49mm 转场按钮出屏、45mm 首点无效）的根本办法，而不是继续手量偏移。

### 3.0 导航结构（前后对比）

**前**（代码盘点）：手表 App 里没有一个 NavigationStack、toolbar、sheet、Menu。所有页面是一个状态机：`WatchRoundModel.screen`（WatchRoundModel.swift:13）在 `WatchRoundContainerView` 里 `switch` 换页（WatchRoundContainerView.swift:471-676）。返回钮是自画 40pt 黑圆（`WatchInstrumentBackButton`，WatchEdgeBackGesture.swift:18）加左边缘右滑手势；仪表页角落 ☰/＋ 是自画 40pt 圆（50pt 点击区，`rootControl` :1305-1332，位置靠手算 `rootRailBottom`）。按钮样式只有 `.plain`（34 处），没有任何系统材质。代码注释记着 #417 在 49mm 上 W01 记一杆 / W02 菜单首点 0/5（:1299-1300），但**没有任何 UI 测试点过 ☰ 或 ＋**。

**后**：

```
路由不变：仍是 WatchRoundModel.screen 状态机（不改状态机 = 不改功能行为）
每个页面自己包一层 NavigationStack，只为拿到系统 toolbar 和系统标题：
├─ 开始 / 开局设置（半场 → 发球台）/ 菜单 / 计分卡 / 选洞 / 转场 / 设置 / 球杆统计：
│     NavigationStack { List … }.navigationTitle(…)
│     .toolbar { ToolbarItem(.cancellationAction) { 系统样式返回 → model 回上一屏 } }
└─ 打球仪表（TabView(.verticalPage)，表冠翻页，页面顺序不变）
     页 1 距离大字（前/中/后 + 建议杆）　页 2 球洞图（当前一杆、瞄准线）　页 3 果岭 / 障碍
     toolbar：.topBarLeading 洞号「H7 · P4 +3」（只读）；
              .bottomBar 左 ☰ 菜单（.glass）、中 撤销「第 2 杆 ↺」（有时才出现，.glass）、右 ＋ 记一杆（.glassProminent 绿）
     图层 .ignoresSafeArea() 满屏画，按钮在系统 toolbar 位置
```

- 返回：自画 40pt 黑圆 → 系统 toolbar 按钮（玻璃、系统点击区）。左边缘右滑是手势不是控件，保留（现有行为）。批 5 把 `WatchInstrumentBackButton/Header` 的实现换成系统 toolbar 写法，各页调用点不变，所以批 6 的页面自动跟着换。
- 仪表页保持满屏：`WatchFullWindowCanvas` 的手量表盘边距表只在快照里用（真机读系统安全区），按钮进 toolbar 后不再需要它给按钮定位；快照改按 5 种真实表盘尺寸渲染。
- 长按开菜单（:1230）保留。

### 3.1 开始、开局设置（半场、发球台）

| 前 | 后 |
|---|---|
| ![](shots/before/w-start-46.png) ![](shots/before/w-setup-halves-46.png) ![](shots/before/w-setup-tees-46.png) | 批 5 补 `after/w-start-41.png`、`after/w-start-46.png`、`after/w-setup-halves-46.png`、`after/w-setup-tees-41.png` |

- 控件：`List`；行用系统按钮行（`.listItemTint`）；发球台行：色点 + 名称 + 码数（码数未知写「码数未知」`.footnote`），当前选中系统 `checkmark`；底部提示「可立即开局 · 球场数据后台补齐」用 `Section` footer。标题用 `.navigationTitle`（系统在左上、和返回同排）。
- 前 → 后：自画圆形返回 + 自画标题 → 系统返回与标题；行背景自画圆角 → 系统 List 行。

### 3.2 打球·距离大字（页 1）与常亮

| 前 | 后 |
|---|---|
| ![](shots/before/w-round-home-46.png) ![](shots/before/w-distance-41.png) ![](shots/before/w-distance-46.png) ![](shots/before/w-caddie-46.png) ![](shots/before/w-always-on-46.png) ![](shots/before/w-waiting-41.png) ![](shots/before/w-waiting-46.png) | 批 6 补 41/42/45/46/49 五种表盘各一张 `after/w-distance-<mm>.png`，常亮一张 |

- 目的：抬腕一眼看到中距离。
- 层级：1 中距离（最大，现有字号不缩）；2 前/后；3 建议杆与「稳妥」；4 洞号与比分（toolbar 标题）。
- 控件：画面不动；角落按钮改 toolbar：`ToolbarItemGroup(placement: .bottomBar)` 左 ☰（`Button("菜单", systemImage: "line.3.horizontal").buttonStyle(.glass)`）、右 ＋（`.buttonStyle(.glassProminent).tint(.green)`，`accessibilityLabel("记一杆")`）。洞号「H7 · P4 +3」放 `.topBarLeading`（只读）。
- 常亮（降低亮度）：只显示距离，toolbar 按钮系统自动淡化（`isLuminanceReduced` 时现有行为不变）。
- 等待定位：中距离位置显示「等待定位」（现有），＋ 按钮保持可点（现有行为）。
- 前 → 后：自画角落圆钮 → 系统 toolbar 玻璃按钮；首击命中由系统点击区保证，并用五表盘 UI 测试证明。

### 3.3 打球·球洞图（页 2）与当前一杆

| 前 | 后 |
|---|---|
| ![](shots/before/w-holemap-41.png) ![](shots/before/w-holemap-46.png) ![](shots/before/w-shot-undo-46.png) | 批 6 补 `after/w-holemap-41.png`、`after/w-holemap-46.png`、`after/w-holemap-49.png`、`after/w-shot-undo-46.png` |

- 控件：图不动（D02「根页只画当前一杆」不变）；左侧 300/287/273 读数不动；toolbar 同 3.2；撤销条「第 2 杆 ↺」改 `.glass` 胶囊按钮放 `.bottomBar` 中间（系统三槽 bottomBar：左菜单、中撤销、右记一杆）。
- 前 → 后：撤销条从自画文字+图标 → 系统玻璃胶囊，点击区 ≥ 44pt。

### 3.4 打球·果岭预览、障碍、旗向（页 3）

| 前 | 后 |
|---|---|
| ![](shots/before/w-green-46.png) ![](shots/before/w-hazards-46.png) ![](shots/before/w-flag-41.png) ![](shots/before/w-flag-46.png) | 批 6 补 `after/w-green-46.png`、`after/w-hazards-46.png`、`after/w-flag-41.png` |

- 控件：果岭预览的返回/旋转两个自画圆钮（`WatchGreenRotationButton`，WatchGreenPreviewView.swift:609）→ toolbar 系统返回 + `.bottomBar` 右 `.glass` 旋转钮；障碍文字版是 `List`（只读行）；障碍图、旗向页的自画返回 → 系统 toolbar 返回。

### 3.5 记分（洞打完）

| 前 | 后 |
|---|---|
| ![](shots/before/w-score-41.png) ![](shots/before/w-score-46.png) | 批 6 补 `after/w-score-41.png`、`after/w-score-46.png`、`after/w-score-49.png` |

- 目的：转表冠或点 ± 在 3 秒内记完杆数、推杆、罚杆。
- 控件：三行「总杆 / 推杆 / 罚杆」，当前行用 `.focusable` + `.digitalCrownRotation` 调（现在已用表冠的保持）；± 是 `.buttonStyle(.glass)` 圆钮（≥ 44pt，见第 5 节）；当前行数字用系统 tint 描边（`.glassEffect(.regular.tint(.green))`）；底部「开球」（球道命中选择）`.glass`、「保存」`.glassProminent` 绿，放 `.bottomBar`。
- 前 → 后：自画灰方块 ± 和自画绿胶囊 → 系统玻璃按钮；按钮位置交给 toolbar，41mm 不再挤出屏。

### 3.6 菜单、计分卡、选洞

| 前 | 后 |
|---|---|
| ![](shots/before/w-scorecard-41.png) ![](shots/before/w-scorecard-46.png) ![](shots/before/w-hole-select-46.png) | 批 5 补 `after/w-scorecard-41.png`、`after/w-scorecard-46.png`、`after/w-hole-select-41.png`、`after/w-menu-46.png` |

- 菜单：`List`，系统图标 + 文字行；「结束本场」行 `role: .destructive` 放最后。
- 计分卡：`List`（每洞一行：洞号、标准杆、成绩，成绩着色保留）；标题 `.navigationTitle("计分卡")` + 比分放 `.topBarTrailing` 只读。41mm 第 4 行点不到的问题由系统 List 滚动与点击区解决（批 5 用 UI 测试证明）。
- 选洞：`LazyVGrid` 里 `.buttonStyle(.bordered)` 圆钮，当前洞 `.borderedProminent`；系统返回。

- 设置页的 4 个开关现在用自画 `WatchApprovedToggleStyle`（WatchSettingsView.swift:130）→ 系统 `Toggle` 默认样式。

### 3.7 球童选项、球杆统计

| 前 | 后 |
|---|---|
| ![](shots/before/w-caddie-options-46.png) | 批 5 补 `after/w-caddie-options-46.png` |

- 球童选项：上半是图（内容，不动），下面选项 `List`；页码「2/3」用 `TabView(.page)` 系统页点；「标准」等选项是 `Picker`（`.navigationLink` 样式）。

### 3.8 转场、结束本场、放弃

| 前 | 后 |
|---|---|
| ![](shots/before/w-turn-46.png) ![](shots/before/w-finish-46.png) | 批 5 补 `after/w-turn-41.png`、`after/w-turn-49.png`、`after/w-finish-46.png` |

- 转场（后九打完了）：`List` 三行（前九 / 后九再打一次 / 只打 9 洞结束本场），主操作「接着打 前九」放 `.bottomBar` `.glassProminent`。46/49mm 按钮出屏问题由 toolbar 放置解决。
- 结束本场：`WatchFinishConfirmationView`（WatchFinishRoundView.swift:406）、放弃确认（:339）本身是状态机里的一屏，保留为一屏（不改成弹窗，免得改变状态机），只把自画胶囊换成系统按钮：「确认」`.borderedProminent` + `role: .destructive`、「返回」`.bordered`；说明文字不变。

## 4. 怎么证明做对了（各批共用）

| 要证明的 | 测法 | 层 |
|---|---|---|
| 每屏有前后截图 | 批 0 扩截图矩阵后，每批合并前的 fixture run 产出 `design-snapshots`/`watch-snapshots`，把本文列出的 after 文件名拷进 `docs/design/shots/after/`（缩到 390pt 宽、256 色，单张 ≤ 60 KB） | CI 产物 |
| 所有可点控件是系统样式 | 每批新增一条 Python 源码守卫只做「白名单计数」：本批文件里 `.buttonStyle(.plain)`、`PlainButtonStyle`、自定义 `ButtonStyle` 的数量必须降到第 5 节列出的例外数（守卫钉的是数量和例外表，不钉具体写法；例外表改了守卫跟着改并写理由） | 单元 |
| 关键按钮首击命中（iPhone） | `RealFlowUITests` 增加：打球页「记一杆」「记分」、开局「开始」在小屏和大屏两种模拟器上**第一次 tap** 就进入下一状态（等待真实界面事件，不按秒等）；亮卫星底图下同测一次 | UI |
| 关键按钮首击命中（手表） | `AICaddieWatchUITests` 增加：41/42/45/46/49 五种表盘，仪表页 ＋ 记一杆、☰ 菜单、记分「保存」、转场主按钮各「第一下就点中」5/5 | UI |
| 不改计分、建议、同步行为 | 现有单测、产品测试（`tests/product`、`AICaddieTests/Product`）、UI 测试原样通过，期望值不改；任何期望值要改的，停下在回话里说明（多半是动到了行为） | 全量（合并前一次） |
| 强光对比度 | 批 3/批 6：在亮卫星、沙坑、深色精细图 × 「降低透明度」开/关 6 张截图上取像素算：记一杆文字对按钮底色 ≥ 4.5:1，按钮边缘对周围地图 ≥ 3:1 | 截图测量 |

故意改坏（每批写一条进 `tests/product/faults/<卡>/manifest.json`）：例：把记一杆的点击区缩到 30pt / 把 toolbar 按钮挪回自画角落偏移，首击测试必须变红。

## 5. 自定尺寸与例外（书面理由）

样式全部是系统的；下表只是「系统样式 + 自定尺寸/画法」的地方，以及不是控件、因此不用系统控件的东西。

| 位置 | 做法 | 理由 |
|---|---|---|
| iPhone 记一杆 76pt 圆 | `.glassProminent` + `.frame(width: 76, height: 76)` + `.buttonBorderShape(.circle)` | 戴手套单手主操作；系统 bottom toolbar 按钮约 44pt 放不下；HIG 允许主操作放大 |
| iPhone 记分 60pt 圆、记分弹层杆数圆钮 ≥ 52pt | `.glass` + 自定 frame | 同上，戴手套 |
| 距离牌（iPhone 右上、手表页 1 大字） | `.glassEffect` 信息牌 / 纯文字；固定 pt + `minimumScaleFactor(0.6)` | 不是控件；字号和牌子/表盘尺寸绑定，Dynamic Type 放大会挤掉地图或截断数字 |
| 地图上的路线、落点标签、码数刻度、旗 | 现有画法（Canvas/Path） | 是地图内容，和地图缩放绑定，不是控件；底图规则按 C241 |
| 记分弹层杆数一排 | 自定布局的 `.glass` 按钮组 | 系统没有「带名称的 6 选 1 大按钮」控件；`Picker(.segmented)` 6 段在 390pt 宽每段 < 52pt，戴手套点不准 |
| 手表记分 ± | `.glass` 圆钮 ≥ 44pt | watchOS 没有系统 Stepper；表冠是主输入，± 是辅助 |
| 手表仪表页满屏画布 | `.ignoresSafeArea()` 画图层，按钮仍在系统 toolbar | 距离和球洞图要用满整块屏（WatchRoundContainerView 现有设计依据） |
| 打球页、复盘、打球弹层强制深色 | `.preferredColorScheme(.dark)`（系统 API；现有 10 处） | 跟随系统深色另做（C174，Jason 10-29「先不做」）；地图在深色外观下对比度最好。手表本来就是黑底，不设外观 |
| 普通页强制浅色 | `.preferredColorScheme(.light)` | 同上 |

## 6. 实现拆分（改写 C167–C173）

原则：每批只改自己列出的文件，批与批之间文件不重叠，可以并行；共享的只有批 0 加的尺寸常量文件（之后各批只读）。每批都是「只换控件层和导航结构」，计分、建议、同步、底图选择的行为一律不变——由现有单测/产品测试/UI 测试原样通过来证明，不改这些测试的期望值。每批的验收都包含「把本文对应屏的 after 截图补进 `docs/design/shots/after/` 并在本文该屏的『后』格引用」。

| 批（卡） | 范围（本文章节） | 只改这些文件 | 依赖 | 并行 |
|---|---|---|---|---|
| 0（C167） | 提最低 iOS 26 / watchOS 26；所有 CI 用同一个 Xcode（≥26，现在 runner 上是 27）；截图矩阵：iPhone 小屏（iPhone 16e/17 一类 6.1"）+ 大屏（Pro Max 6.9"）两种尺寸、亮卫星 Garmin 底图 fixture、手表 41/42/45/46/49 五种表盘；加两份尺寸常量文件 | `mobile/ios/project.yml`、`Package.swift`、`.github/workflows/native-mobile.yml`、`watch-runtime.yml`、`mobile/ios/AICaddieTests/DesignSnapshotTests.swift`、`mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift`、`mobile/ios/AICaddieUITests/UITestViewport.swift`、新增 `AICaddie/Views/GlassMetrics.swift`、`AICaddieWatch/Views/WatchGlassMetrics.swift` | 无 | 先做，其余都等它 |
| 1（C168） | iPhone 外壳与普通页：TabView（打球/成绩/球包/搜索）、首页、成绩各页、球包、设置、登录（§2.1–2.3、§2.10–2.12） | `AICaddieApp.swift`（只动根视图）、`RoundHomeView.swift`（含设置 sheet、洞 pager 容器；不动 pager 里的 CurrentHoleView）、`HubBento.swift`、`HubReviewStyle.swift`、`ResultsView.swift`、`StatsView.swift`、`ScoreDistributionView.swift`、`ClubBag.swift`、`ClubSettingsView.swift`、`BackendSettingsView.swift`、`GarminSessionView.swift`、`SignInView.swift` | 0 | 与 3、6 并行 |
| 2（C170） | 开局：搜索/附近/选场/选半场/发球台/球场详情（§2.4–2.5） | `StartRoundView.swift`、`MobileCourseSearchView.swift`、`CourseReviewView.swift` | 0、1（搜索 tab 入口在 1） | 与 4、6 并行 |
| 3（C169） | 打球页（含开局前预览）浮层：系统 toolbar 顶栏、底部 GlassEffectContainer（记分/记一杆）、距离牌玻璃、侧边图层钮、障碍翻页条、果岭/障碍详情、球童打法页；去掉写死顶部 80/底部 34；删没人用的旧组件（§2.7 列出）；选杆提示（在 LiveHoleComponents）（§2.6–2.8） | `CurrentHoleView.swift`、`LivePlayChrome.swift`、`LiveHoleComponents.swift`、`LiveGreenDetailView.swift`、`LiveGreenEntryButton.swift`、`LiveHazardDetailView.swift`、`CaddiePlanView.swift`、`LiveHolePagerDisplayProbe.swift`；测试 `LivePlannedRouteLayoutTests`、`GarminRasterTests`、`RealFlowUITests`（只改位置断言） | 0 | 与 1、5 并行 |
| 4（C171） | 打球弹层与复盘：记分弹层、计分卡、转场、结束本场/汇总、全部球局、复盘、落点图（含补洞历史入口缺的返回）、编辑（§2.8–2.9） | `LiveScoreConfirmationView.swift`、`LiveRoundScorecardView.swift`、`LiveScorecardComponents.swift`、`LiveRoundTurnSheet.swift`、`LiveRoundFinishSummaryView.swift`、`RoundReviewView.swift`、`RoundShotMapView.swift`、`RoundShotEditComponents.swift` | 0 | 与 2、6 并行 |
| 5（C172） | 手表列表类页面：开始、开局设置（半场/发球台）、选洞、菜单、设置、球杆统计、计分卡、转场、结束本场、球童选项（§3.1、§3.6–3.8） | `WatchStartView.swift`、`WatchRoundSetupView.swift`、`WatchHoleSelectView.swift`、`WatchMenuView.swift`、`WatchSettingsView.swift`、`WatchClubStatsView.swift`、`WatchScorecardView.swift`、`WatchTurnView.swift`、`WatchFinishRoundView.swift`、`WatchCaddieOptionsView.swift`、`WatchEdgeBackGesture.swift`（换成系统 toolbar 返回写法，调用点不变，手势保留） | 0 | 与 3、1 并行 |
| 6（C173） | 手表打球仪表页：角落按钮进系统 toolbar（记一杆 glassProminent）、记分页 ± 换系统玻璃按钮+表冠、撤销条、果岭/障碍/旗向页的返回；5 种表盘首击 5/5 UI 测试（§3.2–3.5） | `WatchRoundContainerView.swift`、`WatchRoundHomeView.swift`、`WatchDistanceHero.swift`、`WatchHoleMapView.swift`、`WatchHoleRingView.swift`、`WatchScoreHoleView.swift`、`WatchShotUndoStrip.swift`、`WatchGreenPreviewView.swift`、`WatchHazardView.swift`、`WatchHazardMapView.swift`、`WatchFlagDirectionView.swift`、`WatchCaddieGlanceView.swift`、`WatchFullWindowCanvas.swift`；`AICaddieWatchUITests` | 0、5（返回写法在 5） | 与 2、4 并行 |

派活顺序（iOS 在途 ≤3 条线）：0 → {3, 1, 5} → {2, 4, 6}。每批合并走同 job CD，进 main 后等 TF。

旧 C170（iPad 分栏）、旧 C171（打球页横屏）不在本卡范围（11-05 土土已收卡，「要做时再开新卡」），这两行改写成上表的批 2、批 4；原文存在本文附录。

## 附录：旧 C167–C173 原文（本卡改写这 7 行前的 BACKLOG 原样）

旧 C170（iPad 分栏）、旧 C171（打球页横屏）不在本卡范围；本设计的取景改成「系统安全区 + 实测四边留白」（批 3），以后做横屏/iPad 时直接复用，不返工。

```text
| C167 | **液态玻璃批 0：CI Xcode 26 + 最低 iOS 26/watchOS 26 + 截图矩阵**（C166 拆）：①PR 的 native CI 用 Xcode 16.4（iOS 18.5 SDK），TestFlight 用最新 Xcode 26.3（ios-testflight.yml:44 选最新、native-mobile.yml 没选）→ 所有 CI 同一个 Xcode 26；②两份工程配置最低版本 iOS 17→26、watchOS→26，native-mobile.yml 4 处写死 ios17.0、product-UI 的 iOS 18.5 模拟器一并改；③截图矩阵扩到多机型/iPad/横屏/最大字号/亮卫星图/手表 5 种表盘；④删约 12 个没人用的旧组件（LiveHoleComponents.swift、CaddiePlanView 视图部分，只剩快照测试引用）。首轮全量看哪些快照/UI 测试变，按新 SDK 实测重录，不改数字凑过  验收：①用户在“CI按指定Xcode/系统矩阵构建并产出可审截图”场景中操作，可直接看到目标结果；②每个指定系统组合都能产出可比较的产品截图，失败时明确标出组合；档位：审一次| C166 评估 par1025/investigate-C166-r2.md | 【搁置·11-07 13:4x Jason「液态玻璃先搁置 把其他做完」】 【未派·11-05 土土统一清理：所等的 C134 都已上线或已关，不再等，进派活队列】 【未派·等 C134】11-03 08:5x 对账排队：Mac 上在途 Codex 4 条（C354 r2/C347/C292/C293）+ C332 fixture，再多 Mac 超载会假红（C337），空一条派一条；iOS 线现 C332、C347。11-02 10:1x 对账排队：iOS 在途已满 3 条（C264 #661、C265 #660、C262 #666），这三条合了再按文件不重叠派；10-31 08:4x 对账排队：iOS 在途 C241/C162 合并前 fixture+原生 mutant 占 macOS runner（全仓 mutant ≤2），这两张合了再按文件不重叠派；今晚 TestFlight（C134+C143）出完再派，不在出 TF 前改编译器；并入：C75 让 fixture 定期跑（native-mobile.yml 的 fixture 仍只能 workflow_dispatch；合并前手动跑已在做）（C75 行；10-30 清扫） |
| C168 | **液态玻璃批 1：弹层与普通页换系统控件+玻璃**：记分确认、计分卡、选杆、转场、结束本场、开局页、首页卡片按钮、成绩筛选、球包；去掉写死 sheet 高度/自画关闭保存按钮/写死字号（改动态字体），顶栏进系统 toolbar，按钮用系统 .glass/.glassProminent；99/136 个 plain 自画 Button 收敛到系统样式  验收：①用户在“弹层和普通页使用系统控件，交互和内容保持一致”场景中操作，可直接看到目标结果；②记分、选杆、结束和开局的系统控件在不同屏幕尺寸上可操作且内容不丢；档位：审一次| C166 评估 par1025/investigate-C166-r2.md | 【搁置·11-07 13:4x Jason「液态玻璃先搁置 把其他做完」】 【未派·等 C167】 |
| C169 | **液态玻璃批 2：打球页地图浮层换系统控件**：顶栏进系统 toolbar，记分/记一杆放底部 safeAreaInset，地图铺满按系统安全区+实测浮层框取景；去掉写死顶部 80（32 处含点击坐标换算和测试）与底部 34 下限；记一杆用 .glassProminent+tint，候选色在亮卫星球道/沙坑/深色地图×降低透明度各截图量对比度（文字 ≥4.5:1、边缘对地图 ≥3:1）选达标的；复盘落点图、果岭/障碍全屏页顶栏同批；像素对齐测试按新实测重算  验收：①用户在“打球页地图铺满安全区，底部记分和记杆可点”场景中操作，可直接看到目标结果；②地图浮层和底部记分/记杆按钮在安全区内可见、可点击；档位：审一次| C166 评估 par1025/investigate-C166-r2.md | 【搁置·11-07 13:4x Jason「液态玻璃先搁置 把其他做完」】 【未派·等 C167】与 C136/C164b（CurrentHoleView）若仍在飞，后合者 rebase |
| C170 | **液态玻璃批 3：iPad 分栏**：首页等改 NavigationSplitView（iPhone 自动收起不变），sheet 按 size class 自适应  验收：①用户在“iPad显示分栏，iPhone保持原有单列”场景中操作，可直接看到目标结果；②iPad 分栏切换不丢当前球局，iPhone 仍可完成同一流程；档位：审一次| C166 评估 par1025/investigate-C166-r2.md | 【已关·11-05 土土收卡：界面功能想法（iPad/横屏/手表/深色），要做时再开新卡】 【未派·等 C168】 |
| C171 | **液态玻璃批 4：打球页横屏**：地图不旋转，浮层按钮挪左右两栏，取景从上下两组改四边按实测；iPhone 横屏约 390pt 高、球洞约竖屏一半（如实告诉 Jason）  验收：①用户在“横屏洞图不旋转，四边控件可操作”场景中操作，可直接看到目标结果；②横屏时地图方向保持一致，左右两侧按钮都能完成记分和切洞；档位：审一次| C166 评估 par1025/investigate-C166-r2.md | 【已关·11-05 土土收卡：界面功能想法（iPad/横屏/手表/深色），要做时再开新卡】 【未派·等 C169】；并入：C46④ 打球页横屏洞图很小（约 67×103pt）（PR #492 审查，C46 行；10-30 清扫） |
| C172 | **液态玻璃批 5a：手表列表/菜单类页面换系统导航与 toolbar（watchOS 26）**  验收：①用户在“手表列表、菜单导航和toolbar符合系统样式”场景中操作，可直接看到目标结果；②手表列表和菜单返回路径清楚，系统 toolbar 不遮挡内容；档位：审一次| C166 评估 par1025/investigate-C166-r2.md | 【已关·11-05 土土收卡：界面功能想法（iPad/横屏/手表/深色），要做时再开新卡】 【未派·等 C167】；并入：C78 开局排序不一致（手表按进入的环优先、手机 A/B/C 固定；C78 没找到位置跳过）（C78 行；10-30 清扫） |
| C173 | **液态玻璃批 5b：手表打球仪表页换系统按钮样式**：画面不动；#418/#422 复查出过 4 次底部点不中 → CI 扩到 5 种表盘跑「第一下就点中 5/5」  验收：①用户在“手表打球按钮在多表盘首击可点中”场景中操作，可直接看到目标结果；②五种表盘首次点击都能进入记分/记一杆，不需重复点按；档位：审一次| C166 评估 par1025/investigate-C166-r2.md | 【已关·11-05 土土收卡：界面功能想法（iPad/横屏/手表/深色），要做时再开新卡】 【未派·等 C172】 |
```
