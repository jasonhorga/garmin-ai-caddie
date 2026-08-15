# Garmin-first 三端产品顺序与 UI 审计

> 日期：2026-08-14 UTC  
> 候选：`c3cd83df7cbe79b1f9f8a020403f26162d82a4bc`  
> 状态：`BLOCK`；仅审查，不改产品代码，不上传 Build 42  
> 基准：Approach S70 官方手册与产品图、Garmin Golf iOS 官方 App Store 图、用户已经确认的业务规则

## 1. 总结论

当前候选不是“再调几个字号就能发布”。地图、数据、状态机和缓存里有大量可复用工程，但多个首要页面采用了错误的产品顺序：内部批准稿被当成最高真值，Garmin 官方行为只被当成灵感。因此测试成功地保护了内部稿，也同时保护了隐藏 iPhone 状态栏、Watch 菜单破坏性动作前置、Hole Root 无可发现入口、iPhone 常驻大控制台、Watch 三方案列表等偏差。

正确方向不是重新天马行空设计，而是：

1. S70 已有答案的实战顺序直接沿用。
2. Garmin Golf iOS 已有答案的成绩、单场、落点图和阶段统计顺序直接沿用。
3. 只有实体输入、屏幕形状和本产品真实能力不同的地方，才做最小等价适配。
4. 本产品已经超过 Garmin 的洞间错误恢复、可审计数据和跨端编辑能力继续保留，但不上 Watch 根页制造噪声。

## 2. 为什么以前反复要求“学 Garmin”，结果仍然偏离

这不是用户指令不明确，而是执行链的真值优先级错了。

### 2.1 内部批准稿替代了竞品事实

- `CurrentHoleView` 明确按内部批准的 `map + glass panel` 组合实现，并把所有原有次要输入继续保留在页面下方。
- `WatchMenuView` 注释声称保留“approved S70-like quartet”，但批准稿的菜单顺序没有用 S70 官方 Golf Menu 核验。
- 当前 Watch 三方案页和 iPhone 双主按钮都与批准稿高度一致；“实现是否忠实”做到了，“批准稿是否合理”没有先判断。

### 2.2 测试在主动保护错误设计

`RealFlowUITests.swift` 不只检查页面能用，还明确断言：

- 底部面板必须在屏幕高度 60%–68% 开始；
- iPhone 实战页不得显示系统时间、Wi-Fi 和电量。

所以隐藏状态栏并不是漏测，而是错误产品决定被写成了回归标准。只修实现而不先改产品真值，后续测试会继续把页面拉回旧稿。

### 2.3 局部修补没有重新设置信息预算

每次新增能力都以“原有能力继续保留”为前提：球童三杆、PlaysLike、记一杆、确认成绩、计分卡、更多调整、媒体、管理入口逐层叠加。单项都有理由，合起来就不再是抬腕或一眼可读的产品。

### 2.4 过去的对抗审查也继承了错误基线

旧 Fable 报告正确发现了不可发现手势、菜单顺序、41 mm 过密和 iPhone 大面板；但它也因为未拿到完整官方证据，错误建议把 S70 的分步统计改成单屏，并把洞间推进简化成进入下一 Tee 即自动换洞。说明模型审查只能作为对抗输入，最终仍必须落到可复查的 Garmin 证据和用户规则。

## 3. 证据边界

### 3.1 已证实的 S70 行为

- `OFFICIAL-TEXT`：S70 有 Touchscreen、Action、Menu、Back 四种输入；球局中按 Action 打开 Golf Menu。
- `OFFICIAL-TEXT`：开球流程是 Play Golf → GPS/附近球场 → 选择球场 → 是否记分 → Tee。
- `OFFICIAL-TEXT`：走到下一洞，Hole Information 自动转到下一洞。
- `OFFICIAL-TEXT`：Golf Menu 的顺序从 View Green、Virtual Caddie、Change Hole、Scorecard 等开始，End Round 在最后。
- `OFFICIAL-TEXT`：统计顺序是总杆 → 推杆 → 球道命中/偏左/偏右（Par 3 或 Approach sensors 隐藏）→ 罚杆。
- `OFFICIAL-TEXT`：End Round 后提供查看统计、Save、Edit Score、Discard、Pause Round。
- `OFFICIAL-TEXT`：AutoShot 自动检测普通击球，不检测推杆；检测后可通过 Club Prompt 记录球杆。
- `OFFICIAL-VISUAL`：Hole Root 只保留 Hole/Par、F/M/B、地图、位置、Driver Distance/洞环和条件成立的当前一杆推荐。
- `OFFICIAL-VISUAL`：Hazards/Layups 一次聚焦一个障碍，障碍轮廓与前后距离直接贴在地图对象上，底部箭头换障碍。
- `OFFICIAL-VISUAL`：完整 Virtual Caddie 一次显示一个组合、AVG. STROKES、地图目标与真实散布，用左右切换替代纵向三卡列表。
- `OFFICIAL-VISUAL`：42 mm（1.2 英寸、390×390）与 47 mm（1.4 英寸、454×454）保持同一信息拓扑；小表没有增加折行说明，也没有把 Dashboard 硬塞进根页。

### 3.2 Garmin Golf iOS 能证明什么

官方 App Store 图可直接证明：

- Activity：最近球局优先；
- Round：记分卡优先；
- Shot Map：地图近乎铺满屏幕，返回、图层、定位、缩放浮在边缘，逐杆事实贴在真实点上；
- Shot Overview：Drive / Approach / Chip / Putt 是一级阶段导航；
- Course Stats 与 Virtual Range：空间或范围图承担主体，表格只用于天然表格数据。

官方图不能证明 Garmin Golf iOS 有一套与 S70 相同的实时打球页。因此 iPhone 实战应采用 S70 的任务顺序、Garmin iOS 的 map-first 移动布局，不能把赛后 Shot Map 冒充 Garmin 的实时产品事实。

## 4. 问题 → Garmin 处理 → 当前偏差 → 应修改方式

| # | 问题 | S70 / Garmin 的处理 | 当前偏差 | 平台必要差异 | 建议 |
|---:|---|---|---|---|---|
| 1 | Watch Hole Root 入口不可发现 | S70 按 Action 打开 Golf Menu | 地图根页唯一入口是无提示 0.6 秒长按 | Apple Watch 没有可供 App 独占的 Action 键 | 给一个固定、克制的 Golf Menu 图标；手动记杆模式再加一个紧凑记杆图标。根页最多两个小图标，不加三按钮快捷条 |
| 2 | 根页信息过载 | S70 始终先显示 Hole/Par、F/M/B、地图；球童有效时只加当前一杆短杆名、线、目标、散布 | 当前同时显示长杆名、长说明、PlaysLike 文案、障碍胶囊、上一杆、成绩环和时间 | Apple Watch 必须给系统时间留右上角 | 根页删长说明与障碍文字；Watch 用 `D/3W/3H/5i/PW/50°`；一次最多一个瞬时提示 |
| 3 | 41 mm 靠缩字硬塞 | S70 42/47 mm 保持同一内容拓扑，文字均为单行任务词 | 多处依赖 `minimumScaleFactor`，长球场名、杆链、脚注和按钮仍显拥挤 | Apple Watch 是圆角长方形，不是圆屏 | 先删信息、再用短词，最后才缩字；正文不低于可读规格，根页所有关键文本禁止折行 |
| 4 | Score-only fallback 像按钮 Dashboard | S70 Big Numbers 是独立的大字距离模式；地图通过 Golf Menu 再进入 | 当前无图页同时放球场名、比分、记一杆、本洞成绩、左右洞、菜单、结束 | 无图时仍需人工记杆 | 改为 Big Numbers/事实兜底 + 两个小动作；结束、选洞、计分卡统一进菜单 |
| 5 | Golf Menu 顺序相反 | S70 View Green、Caddie、Change Hole、Scorecard 等在前，End Round 最后 | 当前先出现计分卡、选洞、结束、继续、放弃，再到本洞动作；AutoShot Beta 也在主菜单 | 手动记杆是本产品必要补偿 | 依 Garmin 顺序重排；手动记杆在手动模式下置顶；AutoShot 状态进设置；End Round 只保留一项并沉底 |
| 6 | 结束、继续、放弃散落 | S70 点最后一项 End Round 后，再见 Save/Edit/Discard/Pause | 当前菜单同时有结束、继续、放弃，结束页又有另一组动作 | 本产品可保留“继续打球” | 主菜单只留末尾“结束本场”；进入统一结束页，再列保存、编辑、继续/暂停、放弃并二次确认 |
| 7 | 手动记分体感笨重 | S70 确实分步：总杆→推杆→球道→罚杆 | 逻辑正确，但每页重复大标题、大数字、整宽下一步和整宽取消，形成重翻页感 | 本产品前置一键推荐成绩，优于 S70 | 保留推荐门与四步；缩短标题为 `H7 · P4`，Cancel 用统一返回动作，不在每页占一整行；Par 3 自动跳球道 |
| 8 | 洞间推进容易被误简化 | S70 正常路径会自动转下一洞 | 旧建议想把“到下一 Tee”直接当换洞 | 本产品必须处理打到隔壁球道、下一 Tee 附近 recovery | 保留候选状态机：暂存下一洞首杆→提示上一洞→确认后归下一洞；Cancel 留上一洞。正常路径视觉上应像 S70 自动，无异常时不多问 |
| 9 | Hazard 页重复且遮挡 | S70 一次突出一个障碍，前后距离贴对象，底部切换 | 当前顶部还有“中 N 码·到果岭”，地图两枚到/过胶囊，底部又写“沙坑 1/1·障碍前后沿”，洞号被压住 | Digital Crown 可替代 S70 的上下箭头 | 顶部只留障碍类型；地图只留两个边界数值；底部只留序号/切换提示。删除 F/M/B 重复摘要 |
| 10 | Touch Target 与快捷操作冲突 | S70 点地图进入目标测距，显示人→目标、目标→旗两段距离 | 旧 Fable 建议单击地图弹快捷条，会占用官方触控语义 | Crown 可以承担地图缩放 | 保留点图测距；Action 等价入口必须是独立图标，不能抢占地图单击 |
| 11 | Watch 完整球童不像 S70 | S70 一次一个组合，地图+AVG. STROKES+散布，左右换方案 | 当前是推荐/保守/进攻三张纵向文字卡，没有地图、平均杆数或散布主体 | 本产品有三种策略，可继续存在 | Watch 改为单方案仪表面，左右/表冠切三策略；iPhone/Web 才做三方案并列比较 |
| 12 | Club Prompt 文案和按钮过大 | S70 AutoShot 后询问球杆，可跳过；短码优先 | 当前 41 mm 显示四个大卡和长中文杆名，底部跳过条贴边 | Apple Watch 需承担无传感器的手动 GPS 记杆 | 推荐杆第一、短码一行、3–4 行可见、跳过固定安全区；选完立即回 Hole Root |
| 13 | 成绩环跨页面干扰 | S70 只在 Hole View 的 bezel 用洞色记录成绩 | 用户已经要求只在球道图显示，3 点起、顺时针经下/左到 12 点结束 | Apple Watch 需避开右上系统时间 | 保留现有环几何；确保其它菜单、记分、球童、障碍、结束页全部不显示 |
| 14 | iPhone 实战不是渐进披露 | S70 根页只给当前一杆建议；详情再给完整 Caddie。Garmin iOS Shot Map 是 map-first | 当前根页常驻三杆 chip、PlaysLike 行、两个同级大按钮和计分卡，再向下堆更多调整/媒体/管理 | 手机需要在没有 Watch 时成为完整替代 | 地图近乎全屏；根页只留当前建议摘要和情境主动作；完整球童、计分卡、调整进入可拉起底板 |
| 15 | iPhone 把“确认成绩”常驻为主按钮 | S70 在计分/洞间时才进入成绩；AutoShot 日常不需要每时每刻确认本洞 | 绿色“确认本洞成绩”从开球起一直与高频“记一杆”竞争 | 手机手动记录需要显式按钮 | 未接近洞末时主动作是记杆；形成下一洞候选/主动计分时才上浮成绩确认 |
| 16 | iPhone 隐藏状态栏 | Garmin Golf 官方 Shot Map 保留系统状态栏 | 代码和 UI 测试主动隐藏时间、电量、网络 | 没有必要差异 | 恢复状态栏，并重新给顶部 Hole Header 留空间 |
| 17 | iPhone 复盘/成绩顺序 | Garmin：Activity → Round Scorecard → Shot Map | 当前这三层总体已经接近；逐杆编辑也已经在地图上 | 本产品多了拖动、增删、排序和审计来源 | 保留数据与直接编辑；提高地图缓存/首帧，避免把同一逐杆事实再列成长列表 |
| 18 | 统计页面卡片化过度 | Garmin Shot Overview 以四阶段切换和空间图为主体 | 部分页面已有四阶段，但 Web/旧页面仍容易回到 KPI 卡墙 | Web 可利用大屏 | 统一 Drive/Approach/Chip/Putt；结论先行，图形第二，表格只用于记分卡/明细 |
| 19 | Web 复盘浪费大屏 | Garmin 没有可直接复制的 Web 真值；iOS Shot Map 提供地图优先语义 | 1440 px 中竖版地图居中，两侧大黑边，编辑信息在下方 | 桌面宽屏本来就应不同 | 左侧地图、右侧逐杆/编辑/记分卡双栏；能力与 iPhone 同义，不照搬手机单列 |
| 20 | 三端产品语言不一致 | Garmin Watch 使用短杆码，手机在详情中展开；任务词稳定 | `3H`、三号小鸡腿、三号混合杆等并存；球童卡顺序也不一致 | Watch 需要更短 | 建立同一语义表：Watch 短码、iPhone/Web 标准中文+短码；方案顺序恒为推荐→保守→进攻，已选只加状态不改顺序 |

## 5. Watch 页面序列与信息预算

### 5.1 Hole Root

始终显示：

- 一行 `H15 · P4`；
- F/M/B，Middle 最突出；
- 洞图和当前位置；
- 仅在本页出现的 18 洞成绩环；
- 右上系统时间保留区。

条件显示：

- 有效球童建议时，一个短杆码、当前一杆瞄准线、目标、真实散布；
- 手动记杆模式：一个紧凑记杆图标；
- 一个固定 Golf Menu 图标，作为 S70 Action 的等价入口。

根页禁止：

- 球场全名；
- 长杆链和“推进·后接…”；
- 障碍到/过胶囊；
- “实打加减码”句子；
- 结束按钮、计分卡按钮、左右选洞按钮；
- 两行按钮标题和依赖极端缩放的正文。

### 5.2 地图详情 / Touch Target

- 地图全屏；
- 点地图放目标；
- 只显示当前位置→目标、目标→旗两段距离；
- Digital Crown 缩放；
- 一个清楚的返回动作。

### 5.3 Hazard

- 一次一个障碍；
- 顶部一个类型词；
- 前后边界和两个数字贴在障碍上；
- Crown 换障碍；
- 不再重复果岭中距、洞号说明和“障碍前后沿”句子。

### 5.4 Virtual Caddie

- 一屏只显示一个策略；
- 顶部短杆组合；
- 地图、目标、散布为主体；
- AVG. STROKES 有校准数据时才显示；
- 左右或 Crown 切推荐/保守/进攻；
- 不使用三张纵向文字卡。

### 5.5 洞末记分

- 先显示本产品的一键推荐成绩；直接接受后完成，不追问统计；
- 进入手动后严格沿用 S70 四步；
- 每屏只保留一个问题、一个主动作、一个统一返回方式；
- Par 3 无球道页；球道只有命中、偏左、偏右。

### 5.6 Golf Menu 与 End Round

- 菜单采用普通单行列表，不用大卡；
- 高频查看/本洞动作在上，设置靠后，End Round 最后；
- End Round 再进入 Save/Edit/Continue or Pause/Discard；
- 放弃必须二次确认，但不在根菜单长期占一行。

### 5.7 41 / 45 / 49 mm 规则

- 三尺寸共享页面顺序，不共享同一批长文案；
- 41 mm 只做减法：短杆码、去说明句、一次一个 overlay；
- 45/49 mm 可以增加地图面积或留白，不借机增加更多常驻控制；
- 可点击面积可以满足 watchOS 可用性，视觉形状不必因此画成巨大整宽卡；
- 所有可读内容必须位于真实 rounded-rectangle content rect，而不只是背景和 Canvas marker；
- `minimumScaleFactor` 只能处理语言微差，不能用来挽救错误信息量。

## 6. 三端统一的产品顺序

| 阶段 | Watch | iPhone | Web |
|---|---|---|---|
| 开局 | 独立 GPS → 附近球场 → Tee → 开球 | “开始一场”看附近；“备战”按城市/球场搜索 | 搜索、备战、下载管理，不承担现场首选入口 |
| 实战 | Hole Root → 地图/障碍/球童按需展开 | 同一 Hole Root 语义，地图近乎全屏，底板承接细节 | 不做实时主端 |
| 击球 | AutoShot 或紧凑手动记杆 → Club Prompt → 回根页 | 没有 Watch 时同构手动记杆；位置先保存，球杆可跳过 | 不做现场击球 |
| 洞间 | 下一洞首杆候选 → 上一洞一键确认或 S70 四步 → 确认/Cancel 分流 | 同一状态机，可编辑任意洞 | 可查看同步状态，不改变现场主流程 |
| 结束 | Menu 最后一项 End Round → 保存/编辑/继续/放弃 | 同一语义，信息更完整 | 已结束球局不提供现场结束动作 |
| 复盘 | 仅计分卡/本洞击球轻查看 | 最近球局 → 记分卡 → 点洞看落点图 → 地图直接编辑 | 同一事实，地图+编辑+记分卡桌面双栏 |
| 统计 | 不做长期分析 | Drive/Approach/Chip/Putt + 时间/球场/球杆 | 与 iPhone 同指标，利用大屏做比较和深入筛选 |

## 7. 工程复用边界

### 7.1 可以直接保留

- topo/球场图下载、缓存和 authority binding；
- GPS、F/M/B、地图投影、触点和障碍几何；
- 当前一杆 target/散布 contract 的方向；
- 用户确认的洞间候选与恢复状态机；
- 成绩推荐门及 S70 顺序字段；
- 逐杆位置先保存、球杆可跳过、复盘拖动/增删/排序；
- `WatchDisplayGeometry` 与 3→12 点成绩环几何；
- Garmin Golf 式 Activity、Scorecard、Shot Map 和四阶段数据结构。

### 7.2 修改后复用

- `WatchHoleMapView`：保留 Canvas/GPS/地图，重排文字预算和根页动作；
- `WatchScoreHoleView`：保留状态机，重做标题、Cancel 和按钮密度；
- `WatchHazardMapView`：保留障碍选择与距离，删除重复摘要和胶囊；
- `WatchCaddieOption` 数据：保留三策略，UI 改成 S70 单方案仪表面；
- iPhone `CurrentHoleView`：保留所有事件与服务 wiring，重组为全屏地图+可拉起底板；
- Web review 数据和编辑器：改成真正的桌面双栏。

### 7.3 应淘汰

- Watch 地图根页仅靠 0.6 秒隐藏长按；
- `WatchRoundHomeView` 的多按钮 Dashboard；
- 当前 Golf Menu 的结束/继续/放弃前置顺序；
- Watch 三张纵向打法卡作为完整球童；
- Hazard 页顶部 F/M/B 摘要和重复说明；
- iPhone 常驻三杆 chip + 双主按钮 + 计分卡的大控制台；
- iPhone 实战隐藏状态栏的产品决定及对应测试；
- 把内部批准稿本身作为 Garmin 对标证明的验收方式。

## 8. 线性实施批次

不再建立大计划，只按用户可见路径做三个小批次：

1. **Watch 一洞闭环**：Hole Root、Action 等价入口、菜单顺序、Hazard、球童仪表面、推荐成绩与手动四步、End Round。用同一真实洞出 41/45/49 mm 对照图。
2. **iPhone 一洞闭环**：恢复状态栏、全屏地图、单推荐渐进披露、情境主动作和可拉起底板；保持现有事件/缓存/状态机不动。
3. **复盘与统计闭环**：iPhone Activity→Scorecard→Shot Map；Web 同事实双栏；四阶段分析和三端术语统一。

每批只做一次 Garmin 官方图并排审查、一次完整旅程检查和必要的现有测试调整；不再增加与产品无关的基础设施或截图矩阵。

## 9. 还需要用户决定什么

目前没有需要用户重新决定的业务规则。Garmin 官方顺序和用户已经确认的规则足以回答大部分问题。

Apple Watch 缺少 S70 Action 键属于平台适配，不应变成开放式选择题。默认建议是：Hole Root 固定一个 Golf Menu 小图标；手动记杆模式再出现一个紧凑记杆图标；地图单击继续保留 Touch Target。先用 41/45/49 mm 三张真实模拟器图验证位置，再让用户做视觉批准即可。

## 10. 官方来源

- [Approach S70 Owner's Manual PDF](https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/Approach_S70_OM_EN-US.pdf)，重点第 5、7–13、49–50 页。
- [S70 Device Overview](https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-C4EE9EF3-5007-41D9-B84F-4582440483AE.html)
- [S70 Golf Menu](https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-07681BF1-996F-4151-963B-B6D7CA7CF910.html)
- [S70 Keeping Score](https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-36D33AC5-47C1-4644-B0EC-9ACCD89FEDFF.html)
- [S70 Recording Statistics](https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-DDEFEB56-BE04-417D-834F-1CBA63FE67C0.html)
- [S70 Ending a Round](https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-5B933B1F-97C2-43FA-A10F-7959DAD4FE64.html)
- [S70 47 mm 官方产品页](https://www.garmin.com/en-US/p/847706)
- [S70 42 mm 官方产品页](https://www.garmin.com/en-US/p/847697)
- [Garmin Golf iOS App Store](https://apps.apple.com/us/app/garmin-golf/id1192480582)
- 本仓库既有证据：[S70 Virtual Caddie 与地图机制](./2026-07-16-s70-virtual-caddie-and-map-mechanisms-evidence.md)
- 本仓库既有证据：[Garmin Golf iPhone 视觉与交互基准](../product/2026-08-14-garmin-golf-iphone-reference-matrix.md)

## 11. Fable xhigh 独立复核

### 11.1 运行证明

- 任务：从 Garmin 官方事实重新审查候选，不把内部批准稿当作正确答案；覆盖 Watch、iPhone、Web 和既有用户规则。
- 结果：`terminal_reason=completed`，共 118 turns。
- 模型：`modelUsage` 只有 `claude-fable-5`；无 Opus、Sonnet 或其它 fallback。
- 原始结果：homeserver `/home/jason/codex-runs/aicaddie-fable-garmin-first-20260814/garmin-first.json`。
- SHA256：`70708b38c3bbf8855e3c7b31b21ced7c3be0ccc819ad1fe6195a03cee4d1e8a3`。

### 11.2 双方独立得到的交集

Fable 与本审查独立确认了以下问题：

1. Watch Golf Menu 把结束/继续/放弃放在本洞工具前，违反 S70 的任务顺序；放弃只应在 End Round 二级流程出现。
2. iPhone `showsRecommendedRoute: true` 仍常驻整洞规划线；它既不是已击球事实，也不是只有当前一杆有效时才出现的球童建议，必须改为条件门控。
3. iPhone 实战地图占比不足，下方常驻控制台堆叠球童、三杆、PlaysLike、双主按钮、计分卡和更多管理；应恢复 map-first 与渐进披露。
4. Watch 完整球童是三张纵向文字卡，缺少 S70 的地图目标、真实散布和 AVG. STROKES 主体。
5. Watch 41 mm 已出现洞号折行，多个页面用 `minimumScaleFactor` 0.55–0.72 掩盖信息超载；应先删文案和缩短杆名，而不是继续缩字。
6. Hazard 页面重复显示果岭距离、到/过胶囊、障碍名称和说明；应恢复 S70“一次一个障碍、两个边界数字贴对象”的结构。
7. 三端推荐/保守/进攻顺序、杆名和期望杆数不一致；选中方案不应改变排序，AVG. STROKES 不能被模糊“风险值”替代。
8. score-only Dashboard 只能作为无几何/无有效距离的兜底，不是 Watch 主路径；有地图时必须保持 Hole Root。
9. Web 不应把天然的 18 洞记分卡做成 18 张大卡；Drive / Approach / Chip / Putt 四阶段也应与 iPhone 保持同义。

### 11.3 对 Fable 建议的纠正与拒绝

| Fable 建议 | 最终处理 | 理由 |
|---|---|---|
| 候选可 `CONDITIONAL SHIP` | **拒绝，继续 `BLOCK`** | 菜单入口、iPhone 实战层级和 Watch Caddie 都是首要路径，不是发布后可慢慢修的装饰问题 |
| 保留 0.6 秒隐藏长按作为唯一地图菜单入口 | **纠正** | S70 的 Action 可发现且有实体反馈；Apple Watch 无可独占等价键，隐藏长按不能承担唯一入口。保留长按作为快捷方式，同时放一个克制的 Golf Menu 图标 |
| Watch Hole Root 为 0 个可见按钮 | **纠正** | 手动记杆与 Action 等价入口是本平台必要补偿；最多两个小图标，但不能恢复按钮墙 |
| 每步删除 Cancel，并把记分主数字再放大 | **拒绝** | 用户已经明确投诉字过大、折页和控件局促；四步顺序保留，Cancel 改为统一紧凑返回语义，不以更大数字换取所谓 Garmin 感 |
| iPhone 状态栏作为用户选择题 | **拒绝** | Garmin Golf 官方 iOS 图保留状态栏，而当前测试明确在保护隐藏状态栏的内部稿；没有证据支持继续把错误实现包装成开放选择 |
| Hole Root 可保留最近障碍文字胶囊 | **拒绝** | S70 根页是距离与地图事实层；障碍名称和前后沿属于 Hazard 聚焦页，根页不再叠文字 |
| Hazard 当前顶部没有真正压住洞号，可小修 | **纠正** | 是否像素重叠不是唯一标准；它仍重复事实、抢占安全区并破坏视线顺序，应按官方极简结构重排 |
| Watch 球童仍可保留三张紧凑方案卡 | **拒绝** | S70 的核心不是卡片数量，而是“一次一个方案 + 地图目标 + 散布 + AVG. STROKES”；仅缩卡片无法恢复产品体感 |
| 仓库不存在既有 S70 研究文档 | **纠正事实** | 候选中存在 `docs/reviews/2026-07-16-s70-virtual-caddie-and-map-mechanisms-evidence.md`；本审查已把它作为辅助证据，最终判断仍以官方材料为准 |

### 11.4 代码事实锚点

- `mobile/ios/AICaddieWatch/Views/WatchRoundContainerView.swift:588`：地图主路径用 0.6 秒隐藏长按打开菜单。
- `mobile/ios/AICaddieWatch/Views/WatchMenuView.swift:80`：注释把内部稿称为 approved S70-like，实际先列计分卡、选洞、结束、继续和放弃。
- `mobile/ios/AICaddieWatch/Views/WatchCaddieOptionsView.swift:21`：完整球童把所有方案纵向列出，并把推荐项浮到第一位。
- `mobile/ios/AICaddieWatch/Views/WatchHazardMapView.swift:433`：果岭中距、障碍摘要和切换说明同时占据障碍页。
- `mobile/ios/AICaddie/Views/CurrentHoleView.swift:184`：实现明确以 approved mockup 的大玻璃面板为布局真值。
- `mobile/ios/AICaddie/Views/CurrentHoleView.swift:489`：iPhone 实战无条件启用整洞推荐路线。
- `mobile/ios/AICaddie/Views/RoundHomeView.swift:230`：实战路由主动隐藏系统状态栏。
- `mobile/ios/AICaddieUITests/RealFlowUITests.swift:522`：UI 测试固定大面板起点并主动断言系统时间、Wi-Fi、电量不可见。

### 11.5 合并后的最终判断

Fable 的价值是从另一条推理路径再次证明：偏差不是一两个 SwiftUI spacing，而是产品顺序错误。双方意见相交后，实施基线仍是本文第 4–8 节；Fable 与官方证据冲突或会加剧用户已指出问题的建议不采纳。

因此本轮没有新增业务选择题，也不进入 TestFlight。下一步只按三个小批次分别做 Watch 一洞闭环、iPhone 一洞闭环、复盘/统计闭环；每批先给出真实 41/45/49 mm 或 iPhone 模拟器图，与对应 Garmin 官方图并排，通过后才进入下一批。
