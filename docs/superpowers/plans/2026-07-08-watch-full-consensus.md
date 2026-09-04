# Apple Watch 全套共识实现计划

> **2026-07-16 AUTHORITY CORRECTION — HISTORICAL PLAN / SUPERSEDED：**本文件记录 07-08 当时的实现共识，**不再是当前已批准设计，也不得直接授权实施**。其固定根页路线、表冠/拖动语义、默认 `HKWorkoutSession`、轨迹确认版 AutoShot 等内容已分别进入 D02、E02/E03、D13、D05 的新决策/证据路由；腕上独立整轮与开局流仍是 D04 的既有范围证据。当前唯一权威队列与 no-code gate 见[Watch 决策账本](../../reviews/2026-07-15-watch-decision-and-task-tracker.md)，全仓冲突索引见[Owner-gate 审计](../../reviews/2026-07-16-repository-wide-owner-gate-authority-and-drift-audit.md)。正文保留用于追溯。

> **执行者须知:** 这是执行**已批准的设计**(spec `docs/superpowers/specs/2026-07-02-unified-tri-surface-spec.md` §四 + 共识渲染图 `scratchpad/wall/watch-*.png` + `flow-*.png`)。设计已定,不要重新设计;每屏的验收标准 = 出模拟器快照对齐对应的共识图。用 superpowers:subagent-driven-development 或 executing-plans 逐任务实现。

**目标:** 把 Apple Watch app 做到与共识渲染图 + spec §四 完全一致——一块能不带手机独立打完 18 洞、对标 Garmin S70 的主打球面。

**架构:** 手表**永不渲 3D/不解网格**;主打球屏 = 后端自绘 topo 位图底 + 手表端极薄 native 矢量叠加(你/旗/落点/打球线);数据靠「离线日志 + 重放」,默认 手表→手机→云。所有距离/叠加靠**手表自身 GPS** 实时算。

**技术栈:** SwiftUI(iOS 17 target,ObservableObject/@Published,非 @Observable 宏);CoreLocation + HealthKit(HKWorkoutSession)/CLBackgroundActivitySession;WatchConnectivity(transferFile/transferUserInfo);后端 FastAPI(server_v2)+ `ai_caddie/geometry/topo_render.py`;仅在 GitHub `native-mobile.yml`(macOS 真 xcodebuild)编译验 + ImageRenderer/simctl 快照;GPS/session 最终须 TestFlight 真机验。

## 全局约束(每个任务都隐含遵守)
- **不造假**:拿不准留空,推测值永不进统计/球杆档案。
- **删干净**(spec 明令,共识老图里有、别照抄):球童「上果岭 64%」成功率、球杆「±18」误差带、英文「PinPointer」(→旗向指引)、繁体「旗桿」(→旗杆)。
- **保留**(spec 负责人推翻评审的"砍"):成绩环(只最外层洞图、放大消失)、实打/plays-like(真高程数据,已在 iOS 用;单位是**码**不是 m)。
- **底图 = 我们自绘 topo**(`GET /api/v2/courses/{gid}/holes/{hole}/topo.png`),不是 Garmin 官方 raster(授权红线)。
- **离线优先**:排定/选场那刻起后台预取整场;打球中**绝不在线拉图**。
- **手势统一**:转表冠=缩放/微调,拖=平移,点=确认。
- iOS PR **必看两套 CI**:native-mobile(编译+快照)+ backend(`tests/test_mobile_contracts.py` grep 手表源码断言控件——改控件要同步它)。
- 每屏验收 = ImageRenderer 快照(`WatchDesignSnapshotTests`)或 simctl(`WatchUITestRoot`)对齐共识图,`gh run download` 下来肉眼看。

---

## 阶段 0 — 数据/契约地基(gates 一切;先做)

Fable 审计确认:主打球屏 + 走动刷新 + 叠加层所需的数据**今天不在手表上**。这阶段补齐。

### Task 0.1 后端:果岭前/中/后**坐标** + 叠加锚点
- **文件:** `ai_caddie/courses/course_prep.py`(`_green_distances` 附近,加坐标)、`server_v2/main.py`(prep DTO)、`tests/test_*course_prep*.py`。
- 现状:`greenDistances` 只给算好的距离(front/middle/backM)。**加**:果岭前/中/后三点的 lat/lon(手表 GPS 要自己重算距离);以及 topo 图的**地理→像素投影参数**(reuse `hole_render._frame` 的 project;导出 ref_lat/ref_lon + ppm + 图尺寸 + 洞口/tee 像素),让手表把「你(GPS)/旗/落点」摆到 topo 图对的像素上。
- 验收:prep 响应含 `greenPoints{front,center,back:{lat,lon}}` + `holeImageProjection{refLat,refLon,ppm,widthPx,heightPx,...}`;单测断言字段 + 一个已知洞的数值合理。

### Task 0.2 契约 + 手表模型:新字段
- **文件:** `mobile/ios/AICaddieWatch/Models/WatchRoundState.swift`、`mobile/ios/AICaddie/Services/WatchEventBridge.swift`(手机桥打包)、`mobile/ios/AICaddie/Views/CurrentHoleView.swift`(sendWatchState)、`tests/test_mobile_contracts.py`、watch schema JSON。
- 加:`greenPoints`、`holeImageProjection`、`hazards[]`(含**海水** kind、几何点/多边形)、`ringPips`(独立局有、伴机局可空)。
- 验收:契约测试断言新字段 schema;`WatchRoundState` decode 可选字段(无则降级)。

### Task 0.3 后端:海水障碍进 route_hazards
- **文件:** `ai_caddie/geometry/`(route_hazards,现只认 Lake+Bunker)+ course_prep hazards DTO。spec 附录A:59 个海边洞漏了 Ocean/Beach 水障碍。
- 验收:一个海边洞(已知 gid)的 hazards 含 water(海);单测。

### Task 0.4 离线交付:开局预取当前+下一洞 topo 图到手表
- **文件:** `mobile/ios/AICaddie/Services/WatchEventBridge.swift`(WatchConnectivity `transferFile`)、`mobile/ios/AICaddieWatch/Services/WatchRoundStore.swift`(缓存 + 读)。
- 手机在开局/切洞时把当前+下一洞的 topo.png(手表尺寸)transferFile 给手表;手表缓存,打球中读本地(**不在线拉**)。没手机时手表才直连 `topo.png` 降级。
- 验收:`WatchRoundStore` 有 `holeImage(hole:)->UIImage?` 读缓存;单测(注入假文件)。

---

## 阶段 1 — 主打球屏:真实球道图洞视图(共识 `watch-holeview.png`)

### Task 1.1 接 `WatchHoleMapView` 进 app + 改造成吃真数据
- **文件:** 从 `origin/superpowers/watch-holeview-redesign` 取 `Views/WatchHoleMapView.swift` + `Views/WatchMapDraw.swift` 进 `mobile/ios/AICaddieWatch/`;改造:图从烤死样图 → 参数传入(`UIImage` + `holeImageProjection`);F/M/B/球童/上一杆/环从 `WatchRoundState` 传;叠加层(你/旗/落点/打球线)用 projection 把 GPS/几何点投到图像素。
- **文件:** `Views/WatchRoundContainerView.swift`(`.home` **有几何** → `WatchHoleMapView`;**无几何** → 纯记分兜底屏)。**兜底 = 只记分**:洞号 + Par + 计分器(−N＋)+ 一句「本洞无地图 / 距离数据」,**不显任何距离**——无网格 = 无果岭坐标 = 无距离,老实留空不编(前/中/后本身就是从几何算的,所以 #291 那个文字屏也没数据,不是兜底)。**#291(`WatchDistanceHero`)退休**:它 = 有几何时的大数字,已被洞视图的**大字模式**取代,不并入。
- **几何覆盖现状(2026-07-08 实测)**:玩家打过 96 场,取几何后 **94 有几何**;剩 2 场(gid 31636/31637)Garmin CourseView **直接 404**(根本没有),= 唯二真·纯记分洞。新开的场靠按需取([[garmin-round-lifecycle]] 的 ensure_prodgeometry)自动补,取不到(404)才落纯记分。
- **大字模式开关放这屏上**(spec D1:洞视图上,不是单独滑一页)。
- 验收:快照 `watch-holemap` 对齐 `watch-holeview.png`(左列 洞号·Par + 球童 chip + 后/中/前[中最大] + 实打切换 + 上一杆 pill + 边缘成绩环);`watch-holemap-zoom` 对齐 `watch-holeview-zoom.png`(放大、环消失、「转表冠缩放」);`watch-holemap-pl` 对齐 `watch-holeview-pl.png`(实打 ↑8 金色)。

### Task 1.2 表冠缩放 / 拖平移 / 点确认手势
- **文件:** `WatchHoleMapView.swift`(`.digitalCrownRotation` → mapScale + fullMap;`DragGesture` → 平移;tap → 确认)。#218 是静态参数,这里真交互化。
- 验收:编译过(手势逻辑无法快照,靠代码 + 契约断言存在 `.digitalCrownRotation`)。

---

## 阶段 2 — 第二层交互屏(共识 `flow-*.png`,~7 组)

每屏:新 SwiftUI view + 接进 `WatchHoleMapView` 的动作/导航 + 快照对齐对应 `flow-*.png`。都复用 `WatchMapDraw` 在真 topo 图上叠加。

- **Task 2.1 选点测距**(`flow-measure.png`):十字准星、拖地图选点 → 你→点 / 点→果岭 距离;表冠沿打球线微调。
- **Task 2.2 拖旗 / 果岭特写**(`flow-green.png`):果岭放大、十字对旗、拖旗 → **主数字「中」跟着变到旗**(spec L84)。
- **Task 2.3 障碍**(`flow-target.png` + `WatchHazardView` 重做):射线**绑当前打球目标线**(非死指果岭中心)、进/过距离、**多障碍转表冠翻(标 1/3)**、**海水标蓝**。
- **Task 2.4 球道命中问法**(`flow-score-fw.png`):记分时**只在四/五杆洞**问 左偏/中/右偏(+罚杆),接进记分流。
- **Task 2.5 本洞击球列表**(`flow-shots.png`)+ **旗向指引**(`flow-pin.png`,英文 PinPointer→旗向指引)。
- **Task 2.6 开局流**(`flow-course/nine/tee.png`):附近球场 → 打几洞 → 发球台(现在开局只有一颗「开始记分」)。发球台用 spec 挖出的 per-tee slope/rating。
- 验收:每屏快照对齐对应 `flow-*.png`;`WatchUITestRoot` 加 `-uitest-screen` 分支;契约测试断言新 view 存在。

---

## 阶段 3 — 自动行为 + GPS(spec「及格线」;最大、须真机)

### Task 3.1 手表自身 GPS + 保活 session + 预热
- **文件:** 新 `Services/WatchLocationProvider.swift`(CoreLocation,1Hz,`desiredAccuracy` best,**不占空**);`Info.plist` 加定位/健康用途键;保活 = `HKWorkoutSession`(默认,给活动环但强制心率)可选 `CLBackgroundActivitySession`(无心率,watchOS 10.1+,真机验);**赛前设置屏预热 GPS**;满电提示。
- 省电:`isLuminanceReduced` 落腕把 UI 刷新降到 10–20s;垂手熄屏。
- 验收:编译过 + 单测(注入假 location);**真机/TestFlight 验冷锁定/续航**(标注为设备验)。

### Task 3.2 走动距离自动刷新
- 用 Task 0.1 的果岭三点坐标 + GPS → 实时重算 前/中/后 + 到旗;洞视图主数字随走动更新。
- 验收:单测(喂 GPS 序列 → 距离变);洞图快照不变。

### Task 3.3 确认式切洞 + 震动
- 到下一台弹「第5洞?[记分]/[还在第4洞]」+ `WKInterfaceDevice.current().play(.notification)`;一点即走、误判取消;每一击归**当前活动洞**(非 GPS)。
- 验收:单测(切洞逻辑);快照确认弹窗屏。

### Task 3.4 上一杆:实时距离(找球)+ 位置滤波
- 用 `distanceFromLastShotM`(实时,非上一杆长度 `lastShotDistanceM`);上一杆位置 Kalman/多点滤波存(原始 GPS 一杆 ±5–14m)。常挂 pill。
- 验收:单测(滤波器 + 找球距离)。

### Task 3.5 息屏大字(AOD)+ 洞末轨迹确认记杆(AutoShot v1 中间方案)
- AOD 常显前/中/后大字;洞末从 GPS 轨迹分段「你跳了 210/150/30 码,是这几杆吗?」让确认(凑复盘落点数据,无挥杆误报)。
- 验收:快照 AOD 屏 + 轨迹确认屏。

### Task 3.6 异常状态屏
- GPS 没定好/漂移、离线球童、电量保护 —— 各一个明确状态。
- 验收:快照。

---

## 阶段 4 — 同步中继 + 收尾

### Task 4.1 独立局同步走 手表→手机→云(spec D9 默认)
- **文件:** `WatchSyncClient.swift` / `WatchRoundModel.swift`(现在独立局收官**直连云**)。改默认:事件用 WatchConnectivity `transferUserInfo` 中继给手机、手机上云(最省电、保证最终送达);没手机才直连云降级。
- 验收:单测(有手机走中继、无手机走直连)。

### Task 4.2 全局清「被 spec 否掉的老图残留」
- grep 全手表源码:无「64%/成功率」、无「±18」、无「PinPointer」、无繁体「旗桿」。
- 验收:契约测试加断言(这些串**不得**出现)。

---

## 验收总览
- 每屏快照对齐共识图(hole-map/zoom/pl + 7 组 flow + AOD/异常/确认切洞)。
- `tests/test_mobile_contracts.py` 全绿(含新字段 schema + 禁词断言)。
- native-mobile CI 编译 + 快照绿;`gh run download` 肉眼验。
- GPS/session/续航 = TestFlight 真机验(唯一非 CI 项)。
- 完成度:阶段 0 数据地基 → 1 主屏 → 2 交互屏 → 3 GPS/自动 → 4 同步;每阶段独立可合并的 PR。
