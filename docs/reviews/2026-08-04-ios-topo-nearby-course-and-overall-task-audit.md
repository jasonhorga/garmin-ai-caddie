# iOS Topo、附近球场与后续总体任务审计

日期：2026-08-04  
审查基线：产品冻结提交 `b65128c7a1e190d344944b09c2fbe27d604b7f06`  
本轮性质：先完成事实审计，再按下方线性 Task Board 实施；截至当前仍未发布 TestFlight。

实施状态更新（2026-08-04）：`T01–T05` 已完成。产品提交为 `3bf9a37`（Topo）和 `4c123b2`（iOS Map Surface）；最终审阅页已发布至 <https://caddie.taile36706.ts.net/demos/garmin-topo-surface-4c123b2-20260804/>。当前仍等待 Owner 逐图批准，尚未发布 TestFlight。

## 一、结论先行

用户指出的两个产品问题都真实存在，但需要拆成三件事处理：

1. **iOS topo 球洞轮廓异常是真 bug。** `04b-shot-map`、`07-prep-card`、`08-prep-hazards` 可见孤立三角碎片、狭长尖刺和不自然的多边形外沿；`10-live-hole` 相对正常，说明问题随真实球场/球洞 geometry 变化，并非所有图片都会出现。
2. **这不只是缺少 `cornerRadius`。** 冻结提交中的 iOS 备战/复盘地图已经对外层容器使用 12/14pt 圆角；异常来自服务端根据 Garmin 三角网格生成的内部 alpha mask。只给外框继续加圆角，内部尖刺仍然存在。
3. **审批页的 Watch 外形也有展示错误。** 当前 HTML 对 396×484 Watch 画布只用通用 `8px` 圆角，因此看起来像方屏而不像 Apple Watch。原始 runtime 截图应保持不改；审批页展示层应套真实 41/46mm 屏幕圆角或表框。真机由 watchOS/硬件屏幕裁切，不应在 app 根视图再做一次浪费显示面积的全局圆角。
4. **Watch 球洞图会继承同一个 topo 轮廓 bug。** Watch 的 Canvas 直接绘制手机下发的 topo PNG；服务端 mask 修好后 iOS、Watch、Web 应同时受益。
5. **iOS 的“附近球场”目前只是对历史已有球场排序。** GPS 不会触发 Garmin 附近球场发现；备战页也只遍历已有 `courseOptions`。
6. **选中一个已知 `globalId` 之后的链路已有较多可复用能力。** 后端已有 Garmin 名称搜索、CourseView release/tee 解析、按洞补 geometry、球场 package 和 topo 预热。缺失的是“GPS 发现陌生球场 → 选中 → 后台获取/解析/质检 → 安装完整球场包 → 三端可用”的一条可靠产品链。
7. **Garmin 的 GPS 附近发现上游尚未被当前仓库证明。** 现有代码只证明匿名 `CourseName` 搜索；旧大计划假设了 provider-wide catalog/centroid mirror，但它仍是计划，不是已验证的 Garmin 接口。实现前必须先从现有 protobuf 未解析字段或 Garmin Golf/S70 开局抓包中确认真实来源，不能把计划里的接口当成已经存在。

## 二、Topo 图形问题的证据与原因

### 2.1 可见证据

- `current-ios/04b-shot-map.png`：右侧和底部存在尖角/楔形突出。
- `current-ios/07-prep-card.png`：主体外存在脱离或近乎脱离的三角碎片，边界锯齿明显。
- `current-ios/08-prep-hazards.png`：多洞出现不自然的多边形外沿。
- `current-ios/10-live-hole.png`：轮廓相对完整，证明不是固定 UI 圆角参数造成的统一错误。
- Watch `W03/W07/W08/W09/W10` 使用同源 topo，能看到短宽、不自然裁切和局部尖角。

审批证据目录：

`/home/ubuntu/claude-web-data/review-artifacts/garmin-visual-final-b65128c-20260803/`

### 2.2 冻结提交中的实现事实

- `HoleImageMapView` 的卡片模式已经使用 12pt `RoundedRectangle`。
- `RoundShotMapView` 已使用 14pt `RoundedRectangle`。
- `topo_render.py` 把 Rough、TreeArea、Fairway、Fringe、Bunker、Teebox、Green 的三角面直接合并为 `land_L`。
- 最终洞形只是 `land_L ∪ water_keep` 与约 110m route corridor 相乘。
- 水域有 route-end seed 的 flood fill，但陆地没有 route/tee/green seeded connected-component 筛选。
- 没有孤岛删除、狭长尖刺检测、窄颈修复、边界平滑或按实际米制阈值的形态清理。
- 冻结版本输出透明画布，因此上述不良 mask 会作为可见球洞外轮廓直接暴露在三端。

### 2.3 实施结论

实查真实 mesh 后找到比形态学清理更可靠、也更小的修法：

1. **地图表面层**：iOS 备战、复盘统一使用同一个 `MapSurfaceStyle`；实战 hero 继续直接融入暗色场上界面。
2. **洞形数据层**：Garmin 包内的 `PhysicsMesh` 才是连续地形权威；原来的尖刺来自 `TreeArea` 等材质碎片被错误并入 alpha。Topo 现在优先用 `PhysicsMesh` 作为外轮廓，没有该层的旧包才保留历史材质并集降级。
3. **画框层**：远离实际 route 走廊、最终不可能显示的邻洞材质碎片，不再参与公共 frame 的宽度计算；Topo、overlay、复盘落点仍共享同一个投影。
4. **没有做统一磨圆**：初版 opening/closing 已主动删除，避免把真实 dogleg、海岸、水域和沙坑轮廓削成相同胶囊。
5. **缓存层**：`STYLE_VERSION` 已升到 `topo-v5`，iOS、Watch、Web URL 缓存键同步。
6. **真实样本验收**：`31794/1`、`31669/1`、`31669/2` 三个异常洞和 `31793/1` 正常对照均为 `678×1060`；Web/iOS overlay 误差 `0 px`，iOS/Watch 仿射最大误差 `0.396147 px`，球路 alpha 最小值 `255`。

### 2.4 Watch 预览外形的单独修法

- 原始 PNG 继续作为不可变证据保留。
- HTML 的 `.watch .device-frame` 使用与 396×484 比例匹配的明显圆角，并可选加 41/46mm 表框和 Digital Crown 装饰。
- 审批页同时提供“设备框预览”和“展开原始像素证据”。
- 不在 Watch app 根界面添加第二层全局圆角；实际产品内容仍由系统安全区和真机屏幕裁切。

## 三、球场选择与 Garmin 地图获取现状

### 3.1 iOS 当前行为

`StartRoundView`：

- 请求当前位置；
- 只在传入的 `courseOptions` 内计算 Haversine 距离；
- 把已有球场按近到远排序；
- 不调用 Garmin 搜索或 nearby API。

`PrepCoursePickerView`：

- 只遍历同一份 `courseOptions`；
- 空列表仍提示先同步 Garmin；
- 没有 GPS、文本搜索或新球场安装入口。

`courseOptions` 的服务端来源：

- `build_mobile_course_options()` 只遍历当前用户历史 `source.rounds`；
- 球场经纬度也来自历史球局；
- 因此“最近在前”真实含义是“我以前打过的球场里，最近的在前”，不是“Garmin 数据库中附近的球场”。

### 3.2 已有可复用能力

- `GET /api/v2/courses/search?name=...`：按名称从 Garmin CourseView 查 `globalId`。
- CourseView release 解析：球场名、洞组、tee、每洞 geometry/raster URL 等已有基础解析。
- `ensure_prodgeometry(globalId, hole)`：可下载、解密、解码某洞 geometry 并导出 hazards/mesh。
- `GET /api/v2/mobile/courses/{globalId}/package?ensure_geometry=true`：可为选定球场构建 live package。
- `POST /api/v2/courses/{globalId}/topo/prewarm`：可预渲染已有 geometry 的 topo。
- iOS 已有环组合、tee 选择、整轮本地 package 和 Watch 文件传输的部分基础。

### 3.3 不能原样沿用的部分

- 新球场第一次准备目前可在一个请求中顺序尝试 18 洞，并把 iOS timeout 拉到 900 秒；这不是可交付的下载/安装体验，应改为可恢复后台任务和明确进度。
- `ensure_prodgeometry` 会从本地历史 scorecard 查 `playerProfileId`；没有历史的新用户/家庭成员可能直接失败。凭证与 profile 必须来自当前账户的 Garmin 绑定，而不是偶然依赖旧球局文件。
- 当前请求多处 best-effort 吞错，适合旧的“有图更好”降级，不适合向用户声明“地图已准备好”。需要逐洞 readiness 与失败原因。
- 当前名称搜索不等于 nearby，且当前仓库没有证明 Garmin provider-wide catalog 或经纬度 nearby endpoint。

### 3.4 推荐的产品流程

统一成一条开局/备战入口：

`定位 → 附近球场 / 搜索球场 / 已安装与最近 → 选洞组 → 选 Tee → 准备地图 → 可离线开局`

其中：

- 附近球场优先从服务端已验证的 Garmin course metadata/centroid catalog 查询，避免把用户精确位置转发给 Garmin。
- 如果 Garmin 只有实时 nearby 接口，则由账户绑定的后端代理调用，并最小化位置精度与保留时间。
- 选中陌生球场后，服务端获取 release、tee、洞序、geometry、hazards 和允许使用的地图资产，完成逐洞质检后生成 iOS/Watch/Web 共用语义的安装包。
- 最小可用条件应是正确洞序、tee、par 和 F/M/B；富 topo/hazard/guidance 可显示准备中或明确不可用，不能伪造 ready。
- 429/503 必须自动按 `Retry-After`/退避重试同一个任务；用户可以离开页面，回来继续看到进度。

## 四、总体 Task 清单

旧四份超长 Plan 全部保留为约束、证据和边界资料，不逐行照抄执行：

- `2026-07-18-phase0-canonical-round-runtime.md`
- `2026-07-18-course-acquisition-snapshot-installer.md`
- `2026-07-18-deep-mine-research-lab.md`
- `2026-07-18-s70-experience-capability-promotion.md`

下面这张表才是接下来用于线性推进的产品 Task Board。一个 Task 只交付一个用户可见或可验证结果，不再把内部哈希、序列化或数据库细节拆成用户看不懂的主任务。

### Phase 0：保持基线并修眼前地图问题

- [x] **T00 保留验收基线**：冻结 `b65128c…`、旧审批页和全部原始截图；在用户批准前不发 TestFlight。
- [x] **T01 建立坏洞回归样本**：锁定 `31794/1`、`31669/1`、`31669/2` 三个异常洞和 `31793/1` 正常对照。
- [x] **T02 修正 topo hole mask 权威**：以连续 `PhysicsMesh` 取代材质碎片并集，并保持 overlay 像素对齐；提交 `3bf9a37`。
- [x] **T03 统一地图表面圆角**：iOS 卡片地图共用 Map Surface；不把真实地形强行胶囊化；提交 `4c123b2`。
- [x] **T04 修审批页 Watch 外形**：新证据页采用真实 Watch 圆角、表框和侧键，原始截图单独可展开；未修改 Watch runtime。
- [x] **T05 全洞重渲染与视觉 QC**：四洞 renderer/contact sheet、跨端投影和同 SHA iOS/Watch 真模拟器证据均已完成；公开审阅页的桌面/手机浏览器检查为 29 张图片全部加载、0 broken image、0 横向溢出。等待 Owner 在审阅页逐图批准，不等同于已发布 TestFlight。

Phase 0 验收：用户指出的异常洞不再有碎片/尖刺；正常洞没有被过度削平；三端 overlay 仍对齐；审批页 Watch 一眼看起来像真实手表。

### Phase 1：先打通“一个从未打过的新球场”

- [ ] **T10 证明 Garmin nearby 数据源**：无损枚举现有 CourseView search protobuf 未使用字段；核实 course centroid；检查已有抓包；必要时只请求一次 Garmin Golf/S70 “Play Golf → 附近球场”抓包。输出真实 endpoint、参数、认证、区域和返回 fixture，不凭猜测编码。
- [ ] **T11 后端 nearby API**：输入当前坐标和半径，返回距离排序的 Garmin 球场 metadata；明确 CN/global 范围与无结果状态。
- [ ] **T12 新球场后台准备任务**：选择陌生 `globalId` 后，异步获取 release/洞组/tee/geometry/hazards，逐洞生成 topo 和 package；支持断点、状态查询及 429/503 自动重试。
- [ ] **T13 iOS 单一选场界面**：开始一场和备战共用“附近 / 搜索 / 已安装与最近”数据源，不再各维护一份列表逻辑。
- [ ] **T14 一场真实新球场验收**：以一个历史中不存在的真实球场完成“发现 → 选择 → 下载 → 18 洞地图准备 → 飞行模式重新打开并可开局”。

Phase 1 验收：用户到一个从未打过的球场，无需先在 Garmin 形成历史球局，也能在 iPhone 上找到并准备好该球场。

### Phase 2：三端统一与离线

- [ ] **T20 统一球场 identity**：venue、9/18 洞组、洞序、tee 和版本在 iOS/Watch/Web 指向同一事实，不再靠历史球场名字拼接。
- [ ] **T21 统一地图资产契约**：每洞明确 image、geometry、transform、hazards、F/M/B、版本与缺席原因；三端不得各自猜投影或 readiness。
- [ ] **T22 统一安装状态**：未安装、准备中、可基础记分、富地图可用、损坏、需更新在三端语义一致。
- [ ] **T23 Watch 获取完整整轮包**：iPhone relay 是加速/降级，不是唯一来源；Watch 已安装后可脱离手机和网络完成整轮。
- [ ] **T24 Web 复用同一球场目录**：支持同一 search/nearby metadata、备战和包状态展示；Web 不另造球场结构。
- [ ] **T25 更新与缓存失效**：Garmin 球场版本变化、topo style 变化或某洞修复时只更新必要资产，正在进行的球局保持可恢复。

### Phase 3：重新做一次 S70 全体验差距验收

- [ ] **T30 重建 S70 状态证据矩阵**：不只比较旧批准图；逐项覆盖开局、Hole Root、大字距离、地图、目标测距、障碍、球童、Club Prompt、计分确认、选洞、结束、恢复和 AOD。
- [ ] **T31 Watch 地图视觉校正**：修正真实洞图裁切、比例、轮廓、地图占比、F/M/B 层级、成绩环、推荐杆和 marker 语义；41/46mm 各有真机/模拟器证据。
- [ ] **T32 S70 开局流**：附近球场 → 洞组 → Tee → 准备/安装 → 开球；位置拒绝、无网、无富地图都有诚实降级。
- [ ] **T33 成绩确认与换洞**：保留已确认的逻辑——检测到下一洞候选先确认上一洞；接受后承接已记录的下一洞开球，取消则继续上一洞；任何洞随时可改。
- [ ] **T34 场上可靠性**：GPS、抬腕恢复、震动、Club Prompt、后台/息屏、低电和离线恢复逐项验证；不把模拟器能截图等同于真机成立。
- [ ] **T35 18 洞用户旅程**：按 S70 用户手册式路径模拟完整一场，逐状态与 S70 证据及批准视觉并排；发现的问题一次汇总后成批修复。

### Phase 4：Garmin Deep Mine，挖到底但不阻塞主线

- [ ] **T40 冻结授权原始 corpus**：整理历史抓包、CourseView search/release/date、prodgeometry ZIP、Hazards、coursedata/IMG、raster、更新响应；原始字节只读保存并记录来源/版本。
- [ ] **T41 无损 protobuf 清点**：保留所有字段 occurrence，不只解析当前已知字段；跨球场、跨版本统计未知字段的类型、取值和共现关系，优先研究坐标、国家/区域、tee、targets 和更新信息。
- [ ] **T42 prodgeometry 全量清点**：23 类 mesh、所有 Draco attributes、`hole.json`、foliage、Terrain.webp、route、elevation 与 hazard 类型全部枚举；禁止研究层过早舍入或只保留 POSITION。
- [ ] **T43 DSKIMG/IMG 递归解析**：把 TRE/RGN/LBL/DEM/contour 的 section、object、坐标系和覆盖率一次清楚；与 prodgeometry 高程交叉验证，严格区分“宏观地形等高”与“可支持推杆的果岭微等高”。
- [ ] **T44 未知 Garmin 端点研究**：专用 Hazards、HasTargets 对应目标、course update/check、官方 raster、附近/目录发现逐项留真实 fixture；没有证据就保持 unknown。
- [ ] **T45 数据覆盖与新球场策略**：统计当前拥有的洞、Garmin 可发现但未下载的球场、缺 geometry/contour/raster 的原因；形成“到新球场后自动获取”的稳定路径，而不是手工加 gid。
- [ ] **T46 能力晋升门**：只有身份、坐标、单位、覆盖率和跨样本验证通过的数据才能进入产品。研究发现先进入报告/可视化，不直接改变球童建议。
- [ ] **T47 Owner 抓包请求**：只有现有 corpus 无法回答真实 endpoint/认证/字段语义时才请求用户抓包；请求应一次说明手机上点哪几步、抓什么、如何去敏，并通过独立提醒渠道通知，避免主任务无声停住。

明确不纳入当前主线：实时风。现有来源不可靠，且用户已明确它不是当前优先项；任何重新加入必须有新证据和单独决定。

### Phase 5：回归、审批与发布门

- [ ] **T50 自动检查**：轻量静态检查本地完成；构建、测试、全洞渲染、模拟器和浏览器自动化全部在 homeserver/GitHub Actions 执行。
- [ ] **T51 真实数据矩阵**：至少覆盖已有常打场、从未打过的新场、9洞环组合、18洞单 gid、缺 geometry、破损 geometry、海边和水障碍场。
- [ ] **T52 同状态视觉证据**：每个改动状态给出批准/S70 目标、真实 runtime 截图和必要的原始数据证据；不再只让模型看缩小 contact sheet。
- [ ] **T53 用户批准 Gate**：先给用户看修正后的 iOS topo、Watch 真设备框预览和新球场端到端结果；明确批准后才触发 TestFlight。

## 五、推荐的实际执行顺序

不要先重写四份超长 Plan，也不要从完整平台底座重新开工。下一步按以下线性顺序推进：

1. `T01–T05`：先把用户眼前已经看到的 topo 与 Watch 审批框修正确。
2. `T10`：用真实证据确定 Garmin nearby 数据源；这是新球场能力唯一必须先证明的外部依赖。
3. `T11–T14`：只打通一个真实陌生球场的 iPhone vertical slice。
4. `T20–T25`：把已经跑通的同一链路扩到 Watch/Web 和离线，不另起炉灶。
5. `T30–T35`：以真实数据和完整一场重新做 S70 全体验校正。
6. `T40–T47`：Deep Mine 持续推进；发现可以晋升，但不能把主线重新拖回数万行计划阶段。
7. `T50–T53`：统一证据、用户批准、再发 TestFlight。

## 六、为什么上一轮“P0/P1 = 0”仍会漏掉这些问题

上一轮证明的是：冻结 SHA 在当时列出的 61 个状态中，没有剩余被最终裁决为阻断的批准图差异。它没有证明：

- 所有真实球场/所有洞的 geometry 都经过外轮廓质量检查；
- 缩小 contact sheet 足以暴露每个透明 mask 的孤岛和尖刺；
- 审批页的设备框本身忠实模拟 Apple Watch；
- 产品已经实现 Garmin GPS nearby discovery；
- 当前 Watch 整体体验已经与 S70 全链路等价。

因此本轮不是推翻冻结证据，而是补上了上一轮验收范围之外的**真实数据质量、验收呈现和产品能力**三类检查。以后视觉验收必须同时包含“同状态 UI”与“跨真实数据 corpus 的地图质量”两条轴。
