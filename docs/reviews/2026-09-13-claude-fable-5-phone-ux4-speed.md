所有证据已核验完毕（实测 JSONL、A/B 计时、sequence profile、双端源码、CI 工作流、Garmin 公开资料）。以下是完整审查报告。

---

# Garmin AI Caddie · PHONE-UX4 启动性能对抗式审查（Claude Fable 5 / max）

**审查模式**：只读快照 `/dev/shm/garmin-ai-caddie-fable5-phone-ux4-speed-20260913`（提交 `021a912b`）；仅 Read/Grep/Glob + WebSearch；未执行 shell/测试/构建，未创建任何资源。
**证据分级**：〔实测〕= `.review-evidence/` 原始 JSONL/JSON/curl 与 PROJECT_STATE 记录；〔源码推断〕= 本快照代码可直接验证；〔公开证据〕= 带 URL 与访问日期的 Garmin 官方/评测资料；〔未知/需实机测〕= 当前无法宣称。

## 0. 三个问题的直接回答

1. **5s/12s 怎么继续压？** 这两个数只是"上一轮候选服务的测量值"，不是体验目标。〔实测〕已证明：warm package 12.9s 里约 11.9s 是 18 洞策略枚举 CPU，而同一课程**带 18 洞 stock 推荐、不做序列枚举**的 package 只需 1.095s（`.review-evidence/ab-strategy-timing-31921-20260913.json`）。所以正确目标是把"用户可感知等待"压到 1–3s（warm/公网）、重访亚秒，路径见 §B/§C——不改"完整 18 洞"语义。
2. **S70 多快？我们能测吗？** 公开资料**没有**任何可复现的 S70 逐阶段启动秒数（§E）；评测共识只有定性的"GPS 数秒锁定、几乎立即进首洞"。我们自己的 Watch 目前**不能**精确测：CI 用 5 秒轮询 marker + 固定 sleep（`.github/workflows/watch-runtime.yml:459-475`），且全在模拟器上。§D 给出 release 可用的埋点方案；今天已有 artifact 只能给"上界"。
3. **非网络优化有哪些？** 网络已被证伪为主因：Quick Tunnel package 20.5s 中 TTFB 占 19.68s，645KB 传输只花 ~0.83s〔实测，`.review-evidence/http-stage-measurements-20260913.jsonl` 第 19 行〕。剩下的全部是服务端 CPU 重复计算、串行耦合、缓存自我失效、客户端串行管线——见 §B。

## 1. 我核对过的证据底座

### 1.1 服务端分段〔实测〕

| 项目 | 31917 | 31921 | 出处 |
|---|---:|---:|---|
| package 总耗时 cold / warm | 24.393 / 12.858s | 21.848 / 9.998s | `server-internal-timings-31917…jsonl` 第 1-2 行；`…31921…jsonl` 第 1-2 行 |
| history.load（冷） | 4.574s | ~4.6s | 31917 文件第 6 行 |
| stats.build（冷）/ warm 命中 | 6.670s / 0.165s | 7.004s | 第 1510、2019 行；31921 第 1518 行 |
| 18 洞 caddie seeds（冷/热几乎不变） | 11.986 / 11.907s | 8.996 / 9.029s | 第 1897、2405 行 |
| 天气快照（本次命中缓存） | 0.45ms | 0.5ms | 第 1613 行 |
| 首洞 geometry-only 模板 | 174ms | — | 第 116 行 |

**seeds 是冷热都在的恒定成本**；且每洞 `package.tee_candidate_routes` 与 `package.offline_caddie_options` 耗时逐洞成对相等（如 942.5ms/982.8ms、1044.6ms/976.1ms，第 1633-1634、1697-1698 行）——两次调用做的是同一份工作。

### 1.2 A/B 策略计时（31921，18 洞）〔实测〕

`full` 21.182s；`no_caddie_seeds` 0.925s；`empty_strategy_calculators` 1.138s；**`single_stock_no_sequence` 1.095s（18 洞、每洞含 stock 推荐）**。即：package 的"课程事实 + 18 洞 seed 骨架 + 单杆推荐"只值约 1.1s，其余 ~20s 全是序列枚举。这是本报告所有激进目标的实测锚点。

### 1.3 枚举内部〔实测〕

`sequence-profile-31921…jsonl`：`_sequence_tail` 238 次共 10.473s；`_planned_chain_cost` 73,552 次共 9.024s；`_club_stability_cost` 239,642 次共 8.014s（均值 33µs）；hazard cost 仅 8ms。枚举源头：`ai_caddie/caddie/decision.py:1150`（`combinations_with_replacement`）、`decision.py:1196-1200`（每支首杆各跑一次 tail）、`ai_caddie/caddie/mobile_live.py:1515-1520` 与 `:1608-1613`（同参数调 `_shot_option_clubs` 两遍）。

### 1.4 网络与争用〔实测 + 源码推断〕

- loopback package 13.532s（TTFB 13.529s）；Quick Tunnel 20.515s（**TTFB 19.684s，645,599B 传输仅 ~0.83s**）——公网多出的 ~7s 不在传输层（http JSONL 第 4、19 行）。
- 时间线显示：02:39:23 本地 bg package 入队 install job `course-bd82921c…`（第 5 行），随后两个 tunnel package 探针期间该 job 处于 `running`（第 20 行 payload）。单 uvicorn 进程无 `--workers`（`ops/start_api.sh:135`）+ 单 install worker（`server_v2/course_install.py:40`）共享 GIL——**+7s 的主嫌疑是与后台安装 job 的 CPU 争用，不是链路**〔源码推断，需干净状态复测〕。
- 31921 "带后台 geometry 29.2s"（第 32 行）是 geometry 0/18 的另一课程，与 31917 不可比。
- 独立 curl 冷探针 17.29s、604,675B（`package-cold-31917.curl`）——同名"cold"的三个数字（24.4/21.8/17.3）互相差 7s，说明"冷"本身就有多种状态，单次数字不能当 p50。

### 1.5 关键源码事实〔源码推断〕

- 手机开局串行：本地模板不完整 → `await` 完整 package（`mobile/ios/AICaddie/AICaddieApp.swift:1183-1191`，超时 120s：`Services/SyncClient.swift:391,501-503`）→ 激活 → 首洞页串行 `/prep` → decision（`Views/CurrentHoleView.swift:1908-1928`）→ 之后才启动全场缓存管线（`AICaddieApp.swift:1414-1424`）。课程选择页只取 tees，无任何 package/prep 预取（`AICaddieApp.swift:4353`；全仓 `fetchCoursePackage` 调用点均在开局/刷新路径）。
- 本地模板"完整"三门槛：全洞精确 prep + 全洞 topo 在盘 + 全洞 seed（`AICaddieApp.swift:1158-1166`；`Models/LiveRoundPackage.swift:104-126`）。31917 geometry 永远 16/18、readiness `blocked`〔实测，http JSONL 第 4 行〕→ 模板永不完整 → **该球场每次开局都走远程全价 package**。
- 即使 0 网络进入，后台 revalidation 仍拉一次全价 package（`AICaddieApp.swift:1611-1636`），服务端无 package 级 memo/single-flight（`server_v2/main.py:1861-1938` 为同步 def，直接调 build）。
- 结束一局 → `stats_cache.clear()`（`ai_caddie/rounds/round_ingest.py:747-753`）且无预热（预热只在启动 `server_v2/main.py:179` 和 sync 后 `:2302-2303`）；新 shots 文件同时使 prep 缓存失效（`ai_caddie/courses/prep_cache.py:14,32`）。**"打完一局→下一局必冷"是结构性的**。
- 天气自失效环：package 拉到新天气会 append 进 `weather_snapshots.jsonl`（`mobile_live.py:273-278`），而该文件在 stats 指纹里（`ai_caddie/history/stats_cache.py:106-111`）→ 下一个 stats 消费者重建 6.7-7.0s。
- 645KB 里每洞 seed 内嵌整份 `clubProfiles/playerProfile/weatherSnapshot`（`mobile_live.py:2093-2095`）→ 18 倍重复；无 gzip（`server_v2/main.py` 仅 CORS 中间件，`:251-258`）。
- 组合 18 洞递归再建完整 package（`mobile_live.py:2934-2953`）；9 洞环先算后丢（`:2916`）。
- Watch 升级管线**完全串行**：prep 批（每批≤3 洞，`Services/WatchBackendClient.swift:169`）→ 逐洞 topo → 逐洞 green detail，一条 await 链（`Services/WatchCourseLibrary.swift:584-682`），无 active-hole 优先、无并发；green.png 实测单张 838KB〔实测〕，18 洞 ≈15MB，是 topo 总量（~4.6MB）的 3 倍。
- decision 端点对同洞再算一次 `_tee_candidate_routes`（`mobile_live.py:1868-1877`）；seed 没有 candidateRoutes 时 decision 仍可用（`tests/test_server_v2_mobile.py:2162-2178`）。
- 手机端已有诚实的离线球童评估器与 seed stock 选项（`Views/CurrentHoleView.swift:2834-2845`；`Services/OfflineCaddieDecisionEvaluator.swift`），Watch 端已有"本地 shell 先行 + 后台原位升级"的完整先例（`AICaddieWatchApp.swift:198-237,250-267`；`WatchCourseLibrary.swift:296-363`）。

---

## A. 为什么 5s/12s 只是门槛，激进目标是什么

5s/12s 是"当前架构下测出来的数"，其成分已被拆穿：warm 12.9s = 11.9s 可消除的重复枚举 + ~1.0s 真实工作〔实测 §1.1/1.2〕；cold 24.4s 再加 11.3s 本可预热/持久化的 history+stats。**把可消除成本当门槛，等于把 bug 当 SLA。** S70 的公开行为（§E）证明"开局不等网络与重计算"是量产可达的产品形态。

约束：不改"一次给完整 18 洞"的产品语义；所有提前显示的状态必须诚实标注。四阶段目标（tap = 点"开始"；p50/p95 为建议目标，**全部未实测**，依据与假设注明）：

| 阶段 | revisit（本机模板完整） | warm（服务端热+公网） | cold（进程冷/数据变更+公网) | 依据与假设 |
|---|---|---|---|---|
| ① tap→本地 round shell（球局壳+记分可用） | p50 0.3s / p95 0.8s | 同左 | 同左 | 纯本地写盘+导航；Watch 已实现同构路径（`AICaddieWatchApp.swift:203-215`）〔源码推断，需实机埋点确认〕 |
| ② tap→首洞地图可交互（真实矢量路线+F/M/B；topo 原位替换） | p50 0.5s / p95 1.0s | p50 1.5s / p95 3.0s；配合课程详情页预取可到 p50 ≤0.8s | p50 3.5s / p95 6s | warm：facts 层 ~1.0s〔实测 ab〕+ 公网单请求 0.6–1.3s〔实测〕+ 端上解码渲染 0.2–0.4s〔未知/需实测〕；cold 前提=ingest 后预热已落地，剩余冷仅进程重启（启动预热 `main.py:179` 已存在） |
| ③ tap→首杆推荐 | 缓存推荐（标注"缓存方案"）= ②+0.2s；在线 decision p95 ②+2.5s | 同左 | 同左 | 缓存推荐用 seed stock/离线评估器（已存在）；在线 decision 实测 1.6/2.5s，decision 端点 memo 后应 <1s〔源码推断〕 |
| ④ tap→完整 18 洞可翻页（18 洞事实+记分卡） | 即时（本地） | p50 ≤2s / p95 ≤4s | p50 ≤4.5s / p95 ≤8s | 18 洞事实与 ② 同一响应到达——这正是"拆包"的意义：完整语义不必等策略枚举 |

补充第五条（不算首屏但必须有 SLA）：**18 洞精确 topo 全部在盘**——服务端 geometry 热时 package→ready 实测 1.10s；全新课程历史 job 7 分 45 秒〔实测，PROJECT_STATE.md:588-592〕。建议 p95:热几何 ≤2min、冷几何 ≤10min、失败洞数必须为 0（31917 卡 16/18 就是"每次都慢"的直接原因）。

**"真正首个用户 + 全新服务器"的极冷场景**（stats 从未建过、courseData 未缓存、Garmin 外呼 30s 超时在路径上）不在上表承诺内，单独作为有界性验收（<100s 且全程诚实进度），不许拿它平均进 p95。

## B. 关键路径重建模（Opus 方案之外的架构增量)

### B1. 拆包：course-immutable 与 player-specific 分成两种资源〔核心建议〕

现在的 `/package` 把三种寿命完全不同的东西焊在一个响应里：
- **课程不变层**（holes/par/yards/hazards/路线投影/topo 引用）：只随 `geometryRevision` 变，跨玩家共享。〔实测〕它的构建成本 ≈0.9–1.1s（ab `no_caddie_seeds`），而且 install 完成后完全可以**物化到磁盘**，按 `(gid, tee, geometryRevision)` 键做 ETag/immutable 静态服务——重访课程的服务端成本从"重建"变成"读文件"，毫秒级。
- **玩家层 seeds**（stats 摘要、clubProfiles、offlineOptions、candidateRoutes）：只随 (stats 指纹, 球包指纹, geometryRevision, annotations) 变。这些指纹**已经存在**（`stats_cache.py:214-221` 的成熟指纹学科），seed 缓存直接复用同一套键。`sourceRef=round_id:hole`（`mobile_live.py:2036`）是唯一把 seed 绑死在 round 上的字段——交付时 rebase 即可，客户端已有 `rebasedForOfflineStart` 先例。
- **每局动态层**（roundId、天气、event cursor）：小、便宜，开局时实时拼。

拆包后："完整 18 洞可翻页"= 课程层到达（1–2s 公网），球童精确层按指纹命中则同包带上、未命中则先给 stock（诚实标注）后台补——**语义仍是完整 18 洞，没有"先一洞"**。这不是 Opus A-lite 的"seed 后台化"，而是把 seed 从"每局计算"改成"按指纹缓存的物化视图"，多数开局连算都不用算。

### B2. 课程选择/详情页预取，不等点"开始"

`/prep` 与 `topo.png` 只需要 gid/hole/tee，**不需要 round_id**〔源码推断，路由签名 `server_v2/main.py:1015-1021`〕；课程层资源（B1）同样与 round 无关。用户在详情页选 tee 的几秒钟足够把课程层 + 首洞 prep/topo 拉完（warm 首洞 prep 28ms、topo 15ms〔实测〕）。点"开始"只做本地 shell + seeds 绑定。当前详情页只拉 tees（`AICaddieApp.swift:4353`），预取挂点现成。风险：用户浏览不开局的浪费——限流为"仅最近定位球场/明确进入详情页"即可。

### B3. 离线立即打开 + 本地确定性球童先显（诚实状态）

对已完整模板：现状已 0 网络进入，但根页在 decision 返回前只用距离排序兜底而不用 seed stock。把首帧改为"seed stock 选项 + 明确'缓存方案·刷新中'标签，decision 到达后原位替换"——评估器、seed、标签语义全部已存在（`CurrentHoleView.swift:2834-2862`），这是产品语义澄清而非造假：状态机里"缓存推荐"和"在线推荐"本来就是两个诚实状态。对部分完整模板（31917 这种 16/18）：允许进入 + 缺洞走既有 `waitForPreciseHoleMap` 轮询（`CurrentHoleView.swift:2001-2045`），缺洞在 UI 上保持 partial 标注——Watch 端已经这么做了（`WatchCourseLibrary.swift:306-316`）。

### B4. 服务端事件驱动预计算，而不是开局重算

失效源只有四个，全部已有钩子：结束一局（ingest）、球包修改、geometry install 完成、Garmin sync。在这四个事件处触发"重建 stats + 重物化该玩家已装课程的 seeds"（单飞保护、低优先级线程），开局路径就变成纯读。特别要拆掉两个自失效环：① ingest 后 clear 不预热（`round_ingest.py:747-753`）；② 天气 append 污染 stats 指纹（`stats_cache.py:106-111` × `mobile_live.py:273-278`）——天气写入后立即触发后台重建，或把 stats 指纹改为其真正消费的天气子集（`stats._weather_quality` 只占 14.9ms〔实测〕，两种修法都便宜；改指纹子集有陈旧语义风险，优先选"写后预热"）。

### B5. 网络微优化的真实边际（不要夸大）

| 手段 | 实测/推断边际 | 结论 |
|---|---|---|
| gzip（一行中间件） | 645KB 高冗余 JSON 预计压 5–10×；公网省 ~0.6–0.7s，loopback 省 0 | 做，但它只是 20.5s 里的 3% |
| schema 去重（clubProfiles 等提升到包级） | 645KB → 估 200–300KB〔源码推断〕 | 随 B1 拆包顺手做；对 Watch/蜂窝价值最大 |
| HTTP/2 / 连接复用 | tunnel 端已是 h2；逐请求 TLS 0.08–0.23s〔实测〕 | 客户端复用 URLSession 即可，边际 <0.3s |
| Brotli / 二进制格式 | 相对 gzip 的增量在 0.1s 量级 | 不做 |

### B6. Watch 管线重排（不把"一洞先出"冒充完整）

现串行链（`WatchCourseLibrary.swift:584-682`）在公网的理论下限：6 个 prep 批 ×0.67s + 18×topo 0.78s + 18×green 1.18s ≈ **40s+**，真表经 BT/Wi-Fi 更差〔未知/需实机测〕。重排原则：① active hole 的 prep+topo 最先、其余洞有界并发 2–3（手机端并发骨架可平移，`AICaddieApp.swift:1751-1859`）；② green detail（15MB 总量）降级为"View Green 打开时按需 + 全部 topo 完成后再补"；③ 完整性判定不变（`preciseTemplateReady` 三门槛），UI 的"后台补齐中：第 N 洞"文案已存在——18 洞语义与诚实状态都不动，只动顺序与并发。

### B7. D+ 之后的新瓶颈：测，不猜

D+ 后服务端 warm ~2–3s（推导：tail 10.47s 中 stability 8.0s memo 后 ≈0.1s，去重再砍半剩 ~1.3s，加 ~1s 基础〔源码推断，锚定 §1.3〕），此时以下端上成本进入同一量级，全部需要 signpost 实测而不是估：645KB（或拆包后 200KB）的 JSONDecoder 解码、`offlineStore.saveRoundPackage` 落盘、SwiftUI 激活重渲染、256KB topo/838KB green 的图片解码、页面转场动画本身（~0.35s 就吃掉预算 20%）。watchOS 上同样解码在更弱 CPU 上可能是秒级〔未知/需实机测〕。测法见 §D 的埋点集——同一套埋点既测网络也测这些本地段。

## C. 路线排序（收益/风险/工程量/是否改产品语义）

**切片 1 —— 结果完全等价，一个实现切片可完成，不改协议不改语义：**
1. D+（洞内 `_shot_option_clubs` 单次评估 + `_club_stability_cost`/`_sequence_tail` memo）——字节级金样回归可验证；warm package 13s→~2.5-3s。
2. ingest 后预热 + 天气写后预热（消灭"打完必冷"）。
3. package 进程级 single-flight（键含 player/gid/tee/nine/back/指纹）+ 组合 18/9 洞环裁剪——手机+手表+revalidation 不再各付全价。
4. gzip 中间件。
5. 手机：点"开始"即并发预取首洞 prep/topo（与 package 并行）；Watch：B6 的重排。
预期：warm 公网首洞交互进 3s 内，重访接近即时。**先做完就复测同一套探针。**

**切片 2 —— 需要协议/缓存迁移（B1/B2/B3/B4 全量）：** 拆包两资源 + ETag/immutable + seed 指纹缓存与 rebase + 详情页预取 + 首帧缓存推荐状态。这是 <2s 首洞交互、<3s 推荐在 cold/p95 上稳定成立的路径；其中"首帧显示缓存推荐"是唯一需要产品确认的语义点（诚实标注前提下建议接受）。stats 结果磁盘化（按指纹快照）也放这里，解决进程重启冷。

**不做：** E（beam/DP，重复消除后枚举本身 <1.5s，回归风险不值）；F 端上重写几何/策略栈；一洞 fast-start 重开（产品已否）；磁盘化逐 round 缓存（seed 按指纹缓存已覆盖）；Brotli/二进制。

**最短路径结论：** <2s 首洞交互（warm/revisit）= 切片 1 + B2 预取；<3s 推荐 = 同上 + decision 端点 memo；完整 18 洞可翻页应与首洞地图**同时**可用（拆包后本来就是同一响应）；全部 18 洞精确 topo 按 §A 第五条单独 SLA（热 ≤2min）。5/12s 不作为任何阶段验收。

## D. Watch 实测方案

**现状缺陷（具体边界）：** ① CI 以 `for _ in $(seq 1 180)…sleep 5` 轮询 marker 文件（`watch-runtime.yml:459-470`），量化误差 0–5s；② marker 到手后再固定 `sleep 2`（`:475`）、非 marker 模式 `sleep 3/5`（`:211-212,550`）；③ marker 由 `WatchUITestRoot` 在**状态就绪**时写（`Views/WatchUITestRoot.swift:861-864,919`），不含首帧提交；④ 全部在 macOS runner 的模拟器上；⑤ 手机端 trace `UITestEventLatencyTrace` 是 `#if DEBUG` + 环境变量门控（`AICaddieApp.swift:4396-4400`；`Services/UITestEventLatencyTrace.swift:3-8`），且用 `systemUptime`（设备睡眠时暂停，跨睡眠区间不可用）。**结论：现有 CI 数字只能证明"完成了"，不能证明"多快"。**

**Release 可用埋点（双端同一套）：** 用 `ContinuousClock`/`clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW)` 打点 + `os_signpost`（Instruments 可视化）+ 本地 JSONL 环形缓冲（每事件 <200B，仅事件名/毫秒/roundId 前缀，无隐私负担），Release 构建常开。八个必测事件：
1. `tap_start`（按钮 action 第一行）
2. `shell_committed`（provisional round 持久化完成）与 `first_frame`（shell 视图首帧，SwiftUI `onAppear`+`CADisplayLink`/watchOS 用首个 body 提交近似，注明近似口径）
3. `package_request_start` / `ttfb`（URLSession didReceive response）/ `body_done` / `decode_done`
4. `first_hole_map_interactive`（首洞矢量路线可命中手势 = holeMap 非空且视图就绪）
5. `first_reco_visible`（缓存推荐或 decision 二者先到者，各自独立打点）
6. `all18_facts_available`（18 洞 par/yardage 全就位）
7. `all18_precise_cached`（`preciseTemplateReady` 翻真的时刻）
8. 另加 `green_detail_done`（因为它是 Watch 管线最重的尾巴）

**对齐：** package/prep 请求已带 `round_id`+`client_id`（`SyncClient.swift:474,478`；`WatchBackendClient.swift:368-371`），服务端内部事件也带 round_id（timings JSONL `api.package_response`）——以 `roundId` 为 correlation ID 即可三方对表（真机 JSONL、服务端 JSONL、CI 日志）；再加一个客户端生成的 `X-Request-Id` 头可区分同 round 的重试。服务端把本次实测用的内部计时固化为常开结构化日志，并补 `stats_state=hit/leader/waiter`、`seed_source=cache/computed`。

**分桶与样本：** 必须分开统计 installed-revisit / new-course / partial(16/18)；warm/cold 以服务端 `stats_state` 与进程启动时间客观判定，不靠"感觉"；网络分 loopback/局域网/Quick Tunnel 三档并记录探针时刻的 install job 状态（§1.4 的争用教训）。每桶 ≥20 次算 p50，≥50 次才报 p95；真机（iPhone + 实体 Watch 各自直连）为准，模拟器只做回归趋势。

**今天已有 artifact 能给什么：** 服务端侧的全部分段（§1.1-1.3）是可信的；客户端侧只能给"上界"——例如 CI `real-course-download-seed` 从 launch 到 marker 的墙钟（±5s、模拟器、含整场 18 洞精确下载）。**不能宣称**：真机 tap→首帧、首洞地图可交互、任何 p95、以及"我们与 S70 相差 X 秒"。

## E. S70 对照

**公开可复现的启动秒数：不存在。** Garmin 官方手册/产品页没有任何逐阶段时序；独立评测只有定性描述："GPS locks on within a few seconds"、"almost immediately it'll take you to the first hole"（[breakingeighty.com S70 评测](https://breakingeighty.com/garmin-approach-s70-review)，访问 2026-09-13）、"incredibly fast to load courses"（[nationalclubgolfer.com](https://www.nationalclubgolfer.com/us/reviews/distance-measuring-devices/garmin-approach-s70-gps-watch-review/)，访问 2026-09-13）。〔公开证据〕仅此而已——任何"S70 首屏 X 秒"的数字都是编造。

**可确认的架构事实〔公开证据〕：** S70 预装 43,000+ 全彩 CourseView 地图（[Garmin 新闻稿](https://www.garmin.com/en-US/newsroom/press-release/outdoor/dial-in-all-parts-of-your-game-with-new-approach-s70-premium-golf-smartwatches-from-garmin/)、[产品页](https://www.garmin.com/en-US/p/847706/)，访问 2026-09-13）；常打球场经 Garmin Golf app 自动更新；Wi-Fi 课程更新会**排队等接上外部电源才下载**（[Owner's Manual: Automatic Course Updates](https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-C83CEE8E-B928-4050-B937-341A0BF2A444.html)、[Wi-Fi Connectivity Features](https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-7089BCD7-BBA9-4AB1-BE0C-3FA4A2FAE861.html)，访问 2026-09-13）。开局流程为 Action→Play Golf→GPS→选场→记分→tee→洞屏（仓库已核证：`docs/reviews/2026-07-15-s70-verified-evidence-pack.md:28-34`）。

**能借鉴/不能推断：** 能借鉴的是产品契约——地图资源先于开局存在于设备、更新与展示解耦（甚至耦合到充电时机）、开局关键路径不含网络下载、根页轻量推荐与完整 Virtual Caddie 分层（证据包 `:93`）。**不能推断**：表内数据格式、渲染管线、推荐计算位置/时机、缓存策略、任何毫秒数——本仓库解码 courseData 的同名端点暗示同源，但那是推断不是事实。

**公平实拍协议：** ① 场景分离：S70"已装球场"只能对我们"模板完整重访"比；我们"新球场首下"在 S70 上没有对等物（其覆盖球场无首下），只能与"S70 触发 Map Manager 区域更新"比且注明不对等。② 统一 ready 事件："洞 1 屏显示 F/M/B 距离 + 洞图已渲染"。③ 统一计时起点：GPS 已锁定后的"最后一次确认点按"（把 GPS 搜星从两边都剔除；S70 GPS 锁定本身另计一列）。④ 控制变量：同球场同站位、两设备电量 >50%、我方分别测直连 Wi-Fi/蜂窝与经手机中继两条路、记录服务器 warm/cold 状态。⑤ 240fps 慢动作同框拍摄两块屏，用一次拍手/LED 做同步标记；每场景 ≥5 次，报中位数与全距——**n=5 不足以报 p95，明说局限**；要 p95 需 ≥20 次/场景。

## F. 反驳看似快速但误导的方案

1. **"骨架屏当 ready"**：把 spinner 换成灰块不改变任何一个 §D 事件的时间戳；用户要的是可交互地图与真实距离。骨架只允许存在于 <1s 的过渡，且不得计入任何 SLA 达成。
2. **"还是先给一洞吧"**：产品已否，且 §1.2 证明它在技术上也不必要——18 洞事实层只值 1.1s，昂贵的是策略枚举，而枚举可以 memo/缓存掉。用砍语义换 1.1s 是坏交易。
3. **"把后台未完成藏起来"**：31917 永远 16/18 就是活证据——如果 UI 把 partial 冒充完整，用户会在第 17 洞掉进无地图，且模板永不完整导致每局都慢。缺洞必须可见（Watch 已有"后台补齐中：第 N 洞"的正确先例），失败洞数必须是 SLA 指标。
4. **"CI/模拟器时间当真机"**：5s 轮询 + sleep + macOS runner 的模拟器（§D）连量化粒度都不够，更别说 A 系列/S 系列芯片差异；只能当趋势回归用。
5. **"先把 645KB 压小"**：传输实测只占公网 20.5s 的 ~0.8s（§1.4）。gzip 值得做但省的是零头；把它当主攻方向会烧掉一个切片换 3% 收益。
6. **"跟 S70 比：拿它已装球场比我们新球场首下"**：S70 预装 43k 球场，根本没有"首下"这条路径〔公开证据〕；这种对比必然输且结论无效。反过来拿我们"模板完整重访"贴 S70 也必须注明我们的模板会因 revalidation/失败洞而失效，S70 不会。
7. **"warm 12.9s 代表热体验" / 单次 curl 当 p50**：结束一局即 clear（§1.5），最常见的"下一局"其实是冷；且三个"cold"实测互差 7s（§1.4）。任何对外数字必须来自 §D 的分桶多样本。

---

## 给产品负责人（≤10 行）

1. 本切片先做四件事：**D+ 去重/memo**、**ingest/天气写后预热**、**package single-flight + 组合裁剪**、**手机首洞预取 + Watch 管线重排（active-hole 优先、green 降级按需）**——全部结果等价、零协议变更。
2. 预期：warm 公网 tap→首洞地图可交互进 **≤3s**、推荐 **≤3.5s**，重访 **≤1s**；"打完一局下一局必冷"消失；Watch 全 18 精确图墙钟约砍半。
3. 同一切片内补**第一项实测**：双端 release 常开单调钟埋点（§D 八事件，roundId 对齐），跑 loopback/公网 × warm/cold × 20 次，拿到真实 p50/p95 基线。
4. 证据到手后决策第二阶段：若 cold/p95 仍 >6s，启动**拆包两资源 + seed 指纹缓存 + 详情页预取**（§B1/B2，协议迁移，语义不变）；"首帧缓存推荐（诚实标注）"届时一并拍板。
5. S70 对照等我们有真机数字后再拍（§E 协议）；在那之前不对外说任何"对标秒数"。5s/12s 从此不再出现在验收标准里。