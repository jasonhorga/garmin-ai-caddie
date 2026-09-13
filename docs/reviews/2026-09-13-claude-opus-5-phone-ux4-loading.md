# Garmin AI Caddie · PHONE-UX4 启动加载独立对抗式审查（Opus 5 / max）

**审查模式**：只读；快照 `/dev/shm/garmin-ai-caddie-opus5-phone-ux4-20260913`（导出自 `5c8461bd`）；仅用 Read/Grep/Glob；未创建任何容器/端口/隧道/缓存/文件。
**证据分级**：〔实测〕= PROJECT_STATE 记录的探针数据；〔源码〕= 从快照代码推断；〔未知〕= 快照内无法确定、需补测。

---

## 1. 结论先行

### 1.1 首屏真正的关键路径〔源码 + 实测拼接〕

新球局（课程非本地完整模板）时，手机端严格串行：

```
点"开始" → GET /mobile/courses/{gid}/package (background_geometry=true, ensure_geometry=false)
   服务端: release 刷新(≤1h 一次 Garmin 外呼) → history 加载(冷 4.6s) → stats 构建(冷 6.7s)
          → 18 洞 holes/模板(≈0.2s) → 天气(Open‑Meteo 同步, 0–10s) → 18 洞 caddie seeds(≈12s, 恒定)
          → readiness → 首洞轻量 prep(每次重读全部 shots 文件) → 入队 install job(毫秒)
   → 645KB JSON 传输 → 客户端 save/activate → 进入首洞页(轻量路线立即可画)
   → GET /prep(热 28ms / 冷≈2s/洞) → topo.png(热 15ms) → POST /caddie/decision(1.6s 环回 / 2.5s 公网)
```

- 客户端在拿到完整 package 前不发任何首洞请求：`mobile/ios/AICaddie/AICaddieApp.swift:1183-1219`（await package → activate → `signalFreshRoundEntry`），随后 `CurrentHoleView.swift:1907-1938`（prep → decision 串行）。
- package 路由是同步 `def`（`server_v2/main.py:1861-1876`），在 FastAPI 线程池里跑，单 uvicorn 进程（`ops/start_api.sh:135`，无 `--workers`），所有 CPU 密集工作共享一个 GIL。

### 1.2 最可信的 3 个瓶颈

| # | 瓶颈 | 量级 | 证据 |
|---|---|---|---|
| 1 | **18 洞 seed 里的策略排序 CPU**：每洞把整袋球杆各跑一次全洞组合枚举，且每洞跑两遍（`_tee_candidate_routes` 与 `_offline_caddie_options` 用完全相同参数调用 `_shot_option_clubs`），枚举内部对同一球杆的 `_club_stability_cost` 重算 24 万次 | warm package 12.9s 中 ≈12s；这是**冷热都在**的恒定成本 | 〔实测〕seeds 11.986s、tail 10.47s、239,642 次 stability cost；〔源码〕`ai_caddie/caddie/mobile_live.py:1515-1520` 与 `:1608-1613`；`ai_caddie/caddie/decision.py:1150,1119-1126,974-996` |
| 2 | **冷 history+stats（≈11.3s）比"warm"测量更常见**：完成一局 → `ingest_round` 直接 `stats_cache.clear()`（连 `_load_cache` 一起清），且**没有**像 sync 那样触发后台预热 | 冷 24.4s vs 热 12.9s | 〔源码〕`ai_caddie/rounds/round_ingest.py:747-753,890`；`server_v2/mobile.py:255-276`；对比 sync 后预热 `server_v2/main.py:2298-2303` |
| 3 | **串行耦合 + 零复用**：package 等 18 洞全部算完才返回；同一课程的 package 没有 single‑flight/memo（手机 + 手表 + 本地模板启动的后台 revalidation + 超时重试各算一遍）；decision 端点再次为该洞重算同一枚举 | 每个重复请求 ≈ 全价 | 〔源码〕`mobile_live.py:2529-2541`；`AICaddieApp.swift:1611-1636`（revalidation 再拉完整 package）；`WatchBackendClient.swift:362-384`；`mobile_live.py:1868-1875`（decision 端点重算 `_tee_candidate_routes`）；`SyncClient.swift:505-511`（120s 超时后重试 1 次，服务端不可取消） |

### 1.3 测量/归因可能有误的地方

1. **"warm 12.858s" 不是常态**：真实使用中最常见的触发序列"结束球局 → 下次开局"会先经过 `stats_cache.clear()`（1.2 #2），无预热；另外 package 自身在有经纬度的已打球场上会同步拉 Open‑Meteo 并 **append 到 `weather_snapshots.jsonl`**，而该文件在 stats 指纹里（`ai_caddie/history/stats_cache.py:106-111,214-221`；写入 `mobile_live.py:273-278` → `weather_context.py:234-239`）。因此**同一次请求不受影响，但下一次 stats 消费者（手表 package、统计页、下一局）会重建 6.7s**。测量时是否触发〔未知〕：容器出站是否能到 Open‑Meteo、探针 round_id 是否复用都会改变结果。
2. **公网只加 0.6–1.3s/请求的结论对 package 不成立**：package 公网 20.5s vs 环回 13.5s，多出 ≈7s。服务端无 gzip 中间件（`server_v2/` 无 `GZipMiddleware`），645KB 走 cloudflared 上行；探针没有拆 TTFB 与传输时间，也是不同运行、服务端负载可能不同〔未知〕。
3. **"首洞 prep 28ms/topo 15ms 不是瓶颈"只在热缓存成立**：prep 缓存是进程内存（`ai_caddie/courses/prep_cache.py:41-49`），2/3/4 洞冷 prep 环回 6.5s 说明冷 prep ≈2s/洞；`/prep` 与 `topo.png` 每小时会同步刷新 Garmin release（`server_v2/main.py:1043-1047`、`:804-809`，`course_reference.py:24,264-289`，抓取超时 30s：`geometry/inspect_courseview_release.py:80-86`）。首个 tees 探针的 2.766s 就是这次刷新〔实测〕。
4. **`_sequence_tail` 238 次不能唯一分解**：调用次数 = Σ(每个 Par4/5 洞 × 2 次 × 过水安全过滤后的杆数)，且 `distance_m<=0` 的洞不会调用（`decision.py:1185-1192`）。所以 73,552/239,642 是**该球包 + 该球场**的工作量，不是常数；杆数 N 增加时组合数按 C(N+s−1, s) 增长（s 最大 4：`decision.py:35,1146-1150`）。
5. **cold 24.4s 仍不是"最冷"**：它没有包含 Garmin release/courseData 冷抓取（package 内 `_refresh_course_release_authority`、模板路径 `ensure_course_data`，均 30s 超时），也没包含 18 洞冷 prep（≈36s 服务端 CPU，由手机后台管线触发）。
6. **31921 带后台 geometry 29.2s 与 31917 13.4s 不可比**：不同课程、可能不同冷热态；"后台安装不降低同步成本"的结论需要同课程同状态对照〔未知〕。
7. **decision 1.619s 是孤立测量**：真实流程里它与 install job（Node/Draco 子进程 + 进程内 topo 渲染）和本地模板启动的后台 package 重算并发，GIL 争用下的延迟未测〔未知〕。
8. **"package 返回 → ready 1.10s"是缓存命中的时间线**，不代表新球场；31917 历史 job 在 geometry 16/18 失败意味着该球场模板永远不会"完整"，于是**每次新球局都走远程 package**（本地快速路径条件见 `LiveRoundPackage.swift:104-126`、`AICaddieApp.swift:1158-1181`）。这可能是实体机上"每次都慢"的直接原因之一。

---

## 2. 源码证据：调用图与同步/异步边界

### 2.1 服务端完整 package 调用图（同步部分全部在请求线程内）

```
main.py:1861 mobile_course_package()                       [sync def → 线程池，持 GIL 做 CPU]
└ server_v2/mobile.py:150 build_mobile_course_package_response()
  ├ :166 _refresh_course_release_authority(allow_fetch=True)   ← Garmin 外呼(≤1h/课程, 30s 超时) 【同步 I/O】
  ├ :170 load_history_data_for_mode()  → stats_cache.cached_load_history_data (进程内存, 冷 4.6s)
  ├ :171 mobile_live.build_live_round_package_for_course(include_course_prep=False, ensure_lightweight=True)
  │  ├ :2838 _geometry_only_course_template()  [仅未打过的课程] → courseData 抓取(30s 超时) + 18× geometry_coverage_for_hole
  │  ├ :2860 build_live_round_package()
  │  │  ├ :2399 cached_build_history_stats()   (进程内存, 指纹 single-flight, 冷 6.7s)   【CPU】
  │  │  ├ :2437 _package_holes()  18× hazards/ coverage(每次解码 release pb)             【小】
  │  │  ├ :2470 _weather_snapshot_for_package()  Open-Meteo 同步(10s 超时) + append jsonl 【同步 I/O + 指纹污染】
  │  │  ├ :2480 _weather_coverage_for_package()  18× 重读 weather 文件                     【小 N×M】
  │  │  ├ :2529 _caddie_context_seeds()  18×:                                             【CPU 主体】
  │  │  │     _geometry_seed / _route_evidence_seed(点-多边形)  ≈0.2s/18 洞
  │  │  │     :2096 _tee_candidate_routes  → _shot_option_clubs → sorted(N× _whole_hole_sequence_key → _sequence_tail)
  │  │  │     :2121 _offline_caddie_options → _shot_option_clubs(同参数, 再算一遍)
  │  │  │     :2068 _manual_notes_for_seed 2× 重读 annotations 文件
  │  │  └ :2542 readiness / :2585 course_prep(移动端已关闭)
  │  ├ :2916 _filter_package_to_nine()   ← 9 洞环/前后九: 算 18 洞后丢一半
  │  └ :2934 back_global_id 递归再建一个完整 package 后 _merge_nines   ← 组合 18 = 2 倍成本
  ├ :198 first_hole_lightweight_course_prep() → course_prep.lightweight_prep_hole → effective_club_ladder
  │      → club_ladder → data.py:670 build_club_profiles() 【每次重读全部 shots 文件, 无缓存】
  └ main.py:1923 course_install.enqueue()  【异步：单 worker 日志式 job + 2 线程 geometry 池 + 子进程】
```

### 2.2 客户端顺序〔源码〕

- `prepareCourseRound`（`AICaddieApp.swift:1126`）：先查本地模板是否"完整"（prep 全部精确 + topo 全部在盘 + 每洞有 seed，`:1158-1166`）→ 是则 0 网络进入并后台 revalidate；否则 await 远程 package（`:1183`，`SyncClient.swift:501-511` 超时 120s、重试 1 次）。
- 进入首洞：`holePrep` 初值取 package 里的首洞轻量 prep（`CurrentHoleView.swift:249-251`）→ `loadHoleMap` `/prep`（`:1958`）→ `retainThenPublishHolePrep` 发布地图（topo 在 `liveTopoURL` 就绪后由图层加载，`:1334-1360`）→ `loadCaddieDecision`（`:1916`）→ `onLiveHoleInitialLoadDidFinish`（`:1928`）→ 才启动全场后台管线 `beginOfflineCourseDownload`（`AICaddieApp.swift:1414-1424`，prep 批 2 并发、topo 2 并发 `:1751-1810`）。
- 球童请求**必须有该洞 seed**（`CurrentHoleView.swift:2731-2734`），离线兜底必须有 `offlineOptions`（`OfflineCaddieDecisionEvaluator.swift:38-44`）。这是 A/B 的硬依赖。

### 2.3 可并行 / 不可并行

| 可并行（今天串行） | 不可并行（真依赖） |
|---|---|
| Garmin release 刷新（I/O）∥ history/stats（CPU）：`mobile.py:166` 先于 `:170` | seeds 依赖 `stats["clubs"]`（球杆分布）与每洞 stats 行 |
| Open‑Meteo（I/O）∥ seeds（CPU）：`mobile_live.py:2470` 先于 `:2529` | `_sequence_tail` 依赖 first club 与剩余距离；同洞两次调用是纯重复 |
| 客户端：首洞 `/prep`+`topo.png` 只需 gid/hole/tee（公开课程知识），可与 package 并发预取 | 精确 prep 依赖 geometry 安装完成 |
| 18 洞 seed 彼此独立（可跨进程并行，线程并行无效——GIL） | decision 依赖 seed 存在（客户端契约） |

### 2.4 重复计算 / N×M 放大清单

1. 每洞 `_shot_option_clubs` 2 次同参调用（`mobile_live.py:1515,1608`）→ 50% 纯浪费。
2. `_club_stability_cost` 对 ≤2N 个不同值重算 239,642 次（`decision.py:1122-1125` 每候选链每杆一次；无任何 memo，`decision.py` 无 `lru_cache`）。这是 tail 10.47s 的主体（估算每次 30–45µs）。
3. `_sequence_tail` 与球洞无关（只依赖 first club、剩余距离、球袋；不看 avoid_zones）→ 同洞两次 100% 可复用，跨洞可按 0.1m 取整复用。
4. decision 端点对同洞再算一次 `_tee_candidate_routes`（`:1868`）+ 3 条 `_sequence_option`（`decision.py:1257-1268`）。
5. 9 洞环 / `nine=front|back` 先算 18 洞 seed 再过滤（`:2907-2916,3218-3252`）；组合 18（`back_global_id`）递归再建一个完整 package（`:2934-2953`）→ 36 洞 seed 换 18 洞。
6. 同课程 package 无 memo/single‑flight：手机 + 手表 + revalidation + 重试各全价。
7. `build_club_profiles` 每次 package 重读全部 shots 文件（`course_prep.py:1803→785`，`data.py:670-698`）；stats 已读过一次。
8. 19× 重读 weather jsonl、36× 重读 annotations jsonl、≥40× release pb 解码（`geometry_evidence.py:105-122`）——今天毫秒级，随文件增长线性变差。
9. 响应体：每洞 seed 内嵌整份 `clubProfiles/playerProfile/weatherSnapshot`（`:2094-2095`）→ 645KB 里大部分是 18× 重复。

---

## 3. A–F 逐项评估

先给一个关键前提〔源码推断〕：**seed 的 12s 里 ≈11.8s 是策略排序，其余 18 洞几何/路线/历史上下文只有 ≈0.2s**（实测 seeds 11.986 − route/options 11.797）。所以"轻量 seed"（保留 context，仅去掉 candidateRoutes/offlineOptions）几乎免费；而 decision 端点在有精确几何时会自己重算 candidateRoutes（`:1868-1875`），且没有 candidateRoutes 也能出决策（`tests/test_server_v2_mobile.py:2162-2178`）。

| 方案 | 预期首屏收益 | 复杂度 | 一致性/回退风险 | 对手机/S70 架构 | 优先级 |
|---|---|---|---|---|---|
| **D. 单次评估 + memo（D+）** | warm package 12.9s → 估 1.5–2.5s（环回）；decision 1.6s → 估 <0.5s；手表/重试/组合同受益 | 低：`_shot_option_clubs` 结果在洞内复用；`_club_stability_cost` 按 (杆身份, scoring) 在一次 build 内 memo；`_sequence_tail` 按 (excluded, round(remaining,1)) memo。纯函数，可做**字节级金样回归** | 极低（结果精确相同）。契约不变 | 不改任何协议；是 A/B/C 的前置（否则后台仍烧 12s GIL） | **P0** |
| **冷 stats 修复（C 的最小形态）** | 冷 24.4s → ≈13s（D+ 后 ≈2–3s）；消除"结束一局后下一局必冷" | 低：ingest 后调用 `warm_stats_cache_in_background()`；package 天气改为异步/不参与首屏；build_club_profiles 加指纹缓存 | 预热线程与前台争 GIL（单进程）；需限制并发 1 | 手机无感 | **P0** |
| **A. 轻量 18 洞 package + 后台 seed（建议形态"A‑lite"：首打洞全 seed，其余 seed‑lite）** | D+ 之后再省 ≈1s；主要价值是**上限保护**（球包/洞数增长、未来更贵的策略模型）与解耦 | 中高：seed 状态字段（`strategyState`）、可恢复 job（复用 course_install 日志模式，键含 player/gid/tee/nine/stats 指纹/球包指纹/geometryRevision）、交付通道（`install/status` + 再拉 package 或新 `/seeds`）、客户端逐洞合并且不降级、`hasCaddieContextForEveryHole` 语义、手表同步 | 首屏后到 seed 落地前：在线球童可用，**离线兜底不可用**；旧 job 覆盖新 round（sourceRef 含 round_id，需 rebase，`LiveRoundPackage.swift:196-257` 已有客户端先例）；后台 12s CPU 若无 D+ 会拖慢前台 decision | 最接近 S70 的"首屏与后台安装解耦" | **P1**（D+ 实测后若首屏仍 >目标才做） |
| **B. 只同步首洞（=已实现的 fast_start）** | package ≈ 1/18 seed + 0.9s；冷 stats 不变 | 已实现且经 Fable 审阅修补（`17ad4e66`）；开关 `AICaddieApp.swift:533,554`、服务端 `mobile.py:161-203` | 一洞记分卡/补齐重试（5 次退避）/partial 覆盖 full 等 UX 复杂度是产品刚否掉的；补齐请求仍是全价且重算首洞 | 与 S70"完整球场立即可翻页"的体感相反 | **P2**（保留为实验开关，不重开） |
| **C. 持久化 stats 与逐洞 seed** | 仅在"指纹不变的重访"命中：进程重启后、同一会话内的重复请求。**打完一局即失效**（新 scorecard 改变 stats 指纹 → 所有 seed 失效）；首次到访不受益 | 中：seed 缓存键必须含 stats 指纹 + 球包文件指纹 + release/geometryRevision + hazards 指纹 + annotations；round_id/天气是动态字段须剥离后回填；磁盘版还要原子写/版本号/保留期 | 键漏一项即"旧建议"；进程内 package memo 可先拿走 80% 收益 | 与手机本地模板重复投入 | 进程内 memo **P1**；磁盘持久化 **P2** |
| **E. 有界候选 / beam / DP** | D+ 后枚举本身估 <1s，E 的边际收益小；仅当 N 大（多别名/满 14 杆）或 MAX_SEQUENCE_STEPS 提高时才显著 | 中：需保留 water 硬约束、"不重复开球杆"、并列打破规则（`decision.py:1158-1165` 以杆名做 tie‑break） | 可能漏全局最优；需要用真实历史做逐洞 safe/stock/attack 离线回归 | 无 | **P2** |
| **F. 手机预装/下载完整 CourseView，网络只更新** | 对**已完整下载**的课程，今天已经是 0 网络进入（`:1158-1181`）；F 的增量在于：让模板可靠地变"完整"（31917 卡在 16/18）、让后台 revalidation 不再全价重算、进入时允许"部分完整"模板 | 完整版 = 端上跑 Draco 解码/mesh 点-多边形/topo 渲染/策略模型 —— 现在全是服务端 Python/Node，等于重写；CourseView 匿名端点批量镜像的授权边界〔未知〕（`courseview_core.py:305-311`） | 版本迁移、存储、授权、双端一致 | 是 S70 的形态，但 S70 的具体实现不可复制 | 现有本地路径可靠化 **P1**；端上计算 **不做** |

**推荐组合**：D+ → 冷 stats 修复 → package 进程内 single‑flight/memo + nine/组合裁剪 → 客户端首洞 prep/topo 预取与分层推荐 →（实测后）A‑lite。C‑磁盘、E、F‑端上计算不进本轮。

---

## 4. S70 对照（只写可支持的）

**公开可查的 S70 行为**（产品页/用户手册层面，不含时序数字）：预装全球球场 CourseView 地图，开局不依赖手机网络下载球场；Virtual Caddie 依据同步的个人击球距离在表端给出推荐；球场更新通过 Garmin Golf App/Wi‑Fi 在后台完成。**未知**：表端数据格式是否与本仓库解码的 `courseData/{build},{layout}` + prodgeometry 同源（本仓库命名暗示同源，属推断）、首屏渲染时序、推荐计算是否完全在表端、更新粒度。

**可由当前证据支持的架构差异**：
1. S70 首屏读本地已安装资源；当前手机在模板不完整时首屏被服务端 12–24s 计算阻塞（§1）。
2. S70 更新与展示解耦；当前手机的"解耦"只对完整模板成立，且后台 revalidation 仍触发全价 package（`AICaddieApp.swift:1611-1636`）。
3. S70 根页是轻量推荐杆，详细方案是二级页；当前手机根页条带在 decision 返回前只用距离排序的球袋兜底（`LiveClubStripPolicy.swift:3-4`），没有把 package 里已有的 `offlineOptions.stock` 作为首帧推荐（`CurrentHoleView.swift:2470-2476` 仅看 `caddieDecision`）。手表端反而已把 offlineOption 一起下发（`:2793,2817`）。

**手机端可借鉴而不必复制 Garmin 私有实现**：
- "本地资源"：模板 + geometryRevision 键的 topo 缓存已具备；补上"部分完整也可进入"（有几洞进几洞，其余走 `waitForPreciseHoleMap` 轮询）和"seed 版本键"，即可让绝大多数重访 0 网络进入。
- "后台更新"：复用 course_install 的可恢复日志模式承载 seed/prep 补齐，键含版本，状态可查询。
- "分层推荐"：首帧用 seed 的 stock 选项（明确标"缓存方案"），decision 到达后替换；不引入新的确定性多杆路线常驻根页。

---

## 5. 具体落地顺序、SLA/埋点、验证

### 5.1 若只能做一轮（推荐本轮范围）

1. **D+**（`mobile_live.py:_caddie_context_seeds` 内对每洞只调一次 `_shot_option_clubs`，两份输出由同一 (safe,stock,attack) 派生；`decision.py` 为 `_club_stability_cost`/`_sequence_tail` 增加显式 memo 参数，默认 None 保持旧行为）。验收：fixture 与真实历史快照下 seeds/decision **字节级一致**；`_sequence_tail` 调用减半、stability 调用 ≤ 2N/次 build。
2. **冷 stats 护栏**：`round_ingest._invalidate_cache` 之后触发后台预热；package 天气拉取改为不阻塞（先返回 `missing`，由后台补）或至少不在 seeds 前；`build_club_profiles` 加 SHOT_DIR 指纹缓存。
3. **裁剪与去重**：`nine`/9 洞环在 build 前就把 `hole_numbers_override` 传下去；组合 18 只为后九算后九；package 按 (player,gid,tee,nine,back,指纹) single‑flight。
4. **客户端小改**：点开始时并发预取首洞 `/prep` + `topo.png`（只需 gid/hole/tee）；根页首帧显示 seed stock 选项并标注状态。
5. 重新跑同一套探针，再决定是否需要 A‑lite。

### 5.2 三个 SLA 与埋点

| SLA | 定义（T0 = 点"开始"） | 埋点 | 门槛（建议，需实测校准） |
|---|---|---|---|
| **首屏可用** | 首洞页出现轻量路线 + 洞信息 + 距离（不要求 topo） | 客户端 `course-start.begin/fetch.end/activate.end/pending-published`（已有 DEBUG trace，`AICaddieApp.swift:1132-1220`，需提升为 release 可采集）；服务端 package 内部事件已有，补 `stats_state=hit/leader/waiter`、`seed_ms`、`tail_calls`、`weather_ms`、`release_refresh_ms`、`body_bytes` | 环回热 ≤3s；公网热 ≤5s；公网冷（stats 冷）≤12s |
| **球童 ready** | 首帧推荐可见（seed stock 或 decision）→ 在线 decision 替换 | `live-hole.initial-load-finished`（`CurrentHoleView.swift:1924-1926`）+ decision 请求耗时 | 首帧推荐 ≤ 首屏 +0.5s；在线 decision ≤ 首屏 +2.5s（公网） |
| **完整球场 ready** | 18 洞 prep 精确 + topo 在盘 + 每洞 seed 含 offlineOptions（= 本地模板完整） | `offline-cache.task.begin/end`（`:1468-1478`）、服务端 `install/status` phase、`course_install stage=prep/topo duration_ms` 日志 | 热几何 ≤2min；冷几何 ≤10min；失败洞数 = 0（否则模板永不完整） |

### 5.3 同一套冷/热/公网探针

- 复用 `ops/benchmark_course_install.py` 与 `phone-ux4-loading-20260913` 的 JSONL 探针；每次用**新 round_id**；记录 `time_starttransfer` 与 `time_total`、body 字节、`Content-Encoding`。
- 三种状态各跑：①容器重启后不等预热；②同进程第二次；③公网隧道；再加 ④"结束一局后立刻开局"（触发 ingest clear）与 ⑤"install job 运行中发 decision"（争用）。
- 门槛判定用服务端事件与客户端埋点各自的 p50/p95，不用单次。

---

## 6. 反例与风险 + guardrail

| 风险 | 现状证据 | Guardrail |
|---|---|---|
| 后台任务重复（手机 + 手表 + revalidation + 超时重试） | package 无 single‑flight；服务端同步路由不可取消（`SyncClient.swift:1224-1247` 重试） | 按 (player,gid,tee,nine,back,指纹) single‑flight；seed job 复用 `course_install.job_id` 式键去重 |
| 旧 round/版本覆盖新数据 | seed 的 `sourceRef=round_id:hole`；fast‑start 已有 generation 守卫（`AICaddieApp.swift:1293-1320`） | 后台 seed 以课程事实为键，交付时 rebase round_id；客户端合并检查 roundId + geometryRevision + 不降级（沿用 `preservingForegroundPrecisePrep`） |
| 缓存爆炸 | 若以 round_id 为键则每局一份 | 键不含 round_id/天气；每 player LRU 上限；磁盘版带保留期 |
| 组合搜索质量下降（E） | tie‑break 依赖杆名 | 先做精确 memo；E 仅在实测仍超标时做，且用真实历史逐洞回归 |
| 天气/审计写入自我失效 | `stats_cache.py:106-111`；`mobile_live.py:273-278` | 天气拉取移出首屏路径并在写后预热；或按 stats 真正读取的子集做指纹 |
| CourseView 授权/版本 | 匿名端点（`courseview_core.py:305-311`）；每小时 release 刷新；409 revision 契约 | 请求内刷新加短超时（如 3s），完整刷新交后台；不做批量镜像 |
| 网络长尾 | Open‑Meteo 10s、Garmin release/courseData 30s、Cloudflare 源站超时（公开文档 100s）、iOS package 120s×2；524 不在 iOS 的 transient 列表（`SyncClient.swift:403`）→ 直接回退本地 | 首屏路径全部 I/O 有界；冷 + 争用场景必须实测保证 <100s |
| 后台 seed 拖慢前台（单进程 GIL） | 单 uvicorn 进程；seeds 纯 Python | 先 D+ 把 CPU 降一个量级；必要时 seed job 走子进程 |
| 模板永不完整 → 每局远程 | 31917 geometry 16/18 失败 | 允许"部分完整"进入 + 失败洞可重试；完整性作为"完整球场 ready"SLA 的失败计数 |

**需要补测的最小实验**（当前快照无法回答）：① 同课程两次 package（不同 round_id）之间 stats 是否重建（看 `stats_state`）；② package 公网 TTFB vs 传输；③ 结束一局后立即开局的耗时；④ install job 运行中的 decision p95；⑤ D+ 后 seeds 实际耗时与球包 N。

---

## 7. 给产品负责人的选择建议（≤8 行）

1. 本轮只做 **D+ + 冷 stats 护栏 + 裁剪/去重 + 客户端预取与分层首帧**：零协议变更、可字节级验证、预期把热 package 从 ≈13s 压到 ≈2s、冷从 ≈24s 压到 ≈13s 且让"打完一局后下一局必冷"消失。
2. **A 先不做**：在 D+ 之前它只是把 12s 的 GIL 计算挪到后台，仍会拖慢首洞 prep/decision，且要新增可恢复 job、seed 版本、双端合并。D+ 落地并实测后，若公网首屏仍 >5s，再做 A‑lite（首打洞全 seed，其余轻量）。
3. **B（一洞 fast‑start）不重开**：已被产品否掉的 UX 复杂度，收益被 A‑lite 覆盖。
4. **C 只做进程内 memo/single‑flight，磁盘持久化不做**：打完一局就失效，命中率低于投入。
5. **E 不做**：真正的开销在重复计算不在枚举；做了还要承担推荐变化的回归风险。
6. **F 的端上计算不做**：等于重写几何/渲染/策略栈，授权边界未知；但要把"本地模板可靠变完整 + 部分完整可进入"作为 P1 产品目标，这才是 S70 体感的来源。
7. 验收以 §5.2 三个 SLA 的 p95 为准，用同一套冷/热/公网/结束后开局/争用五态探针。
8. 在 §6 的五个补测实验出结果前，不要对外承诺具体秒数。

---

**Handoff（AGENTS.md §6）**：只读；快照 `/dev/shm/garmin-ai-caddie-opus5-phone-ux4-20260913`；未创建容器/卷/端口/隧道/缓存；快照按策略 24h 过期，由 Codex 清理；交付物为本报告。
