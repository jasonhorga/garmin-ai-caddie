# Garmin 新球局同步与备战下载方案

日期：2026-08-20 UTC
状态：`IMPLEMENTED IN WORKTREE / REMOTE PYTHON + SWIFT-SOURCE TESTS ADDED / IOS XCODE PENDING / NOT DEPLOYED`。本稿不改变已批准的 Watch View Green（`779b31c`），也不执行生产发布。

本轮实际落地范围：

- package 的后台几何/topo 准备改为原子 JSON journal + 单 worker；API 重启会恢复 queued/running 任务。
- 新增 `GET /api/v2/courses/{global_id}/install/status`，响应只含公共课程/洞级进度，不返回 player identity、GPS、球杆距离或 Garmin 凭据。
- journal 每个洞保存 `geometryRevision`，topo 只有在同一 revision 下才算 ready；Garmin release 更新不会复用旧 ready 状态。
- topo future 完成后立即写回洞级状态；worker 收尾期间新增的洞会在 active worker 释放后自动接力，不会遗留在 queued 状态。
- iOS `SyncClient` 可以读取安装状态；备战下载器优先使用该状态减少盲目 coverage 轮询。
- 备战入口只在本机 `OfflineStore` 完整 facts + 全部 topo PNG 校验通过后进入；`CourseReviewView` 不再发起页面级 `/prep`/coverage 下载，也不显示简化 CourseView 地图。
- 服务端仍保留旧 `_upgrade_course_geometry` 作为兼容内部调用，但 package 新路径不再把它挂到 FastAPI `BackgroundTasks`。
- `/prep`、coverage、topo 的 iOS GET 采用短超时和 transient-only 有限重试；备战整包使用受限两路吞吐，不再为不可见的“首洞优先”额外串行等待。

远程定向验证（homeserver Docker）：Python/backend 回归以最后一次实际运行结果为准；iOS Swift 测试已补齐关键状态门控但尚未经过 Xcode 编译。未做真实冷 18 洞 benchmark；未部署、未上传 TestFlight。

## 结论先行

这次反馈包含两个互相独立的问题：

1. **新球局没有同步**：已找到确定的生产故障。homeserver 的小时 cron 依赖
   `aicaddie-sync:latest`，但该镜像不存在；8 月 18–19 日每次运行都以 Docker exit 125 失败。
   生产 owner scorecard 最新文件仍是 2026-07-24，因此新球局根本没有进入服务端数据卷。
2. **备战下载慢/后台停/简化地图难看**：代码有可复用的断点队列，但不是系统级后台下载；冷球场的主要耗时在 Garmin geometry 获取、mesh 计算和逐洞 topo 渲染，不是单纯网络带宽。

因此不能只调一个超时或把客户端并发盲目调大；先恢复同步，再把“选择球场”和“查看攻略”拆成清晰的下载状态机。

## 联合复核结论（Cloud + 纯 Fable xhigh）

两路审查没有发现需要推翻上述根因的证据，但补上了三个重要边界：

1. **Garmin 同步故障与地图下载故障完全分开。** Cloud 的生产证据是同步镜像缺失、cron 每小时 exit 125；Fable 也将“球局未入库”排在下载/缓存之前。不能用重新打开成绩页或清 iOS 缓存替代修复同步链路。
2. **当前“下载”有两条不同的实现，不能混称。** 备战详情页启动的是页面生命周期内的 package/prep/coverage 请求；真正可持久、逐洞落盘的 `OfflineStore` 队列主要在实战离线安装路径。离开备战页后，前者会被 SwiftUI 取消，后端进程内 `BackgroundTasks` 也不是持久队列。这正是用户看到“退回去就中断、再进又像重新下载”的工程原因。
3. **“下载完成前不进入备战界面”可以作为明确产品规则。** 选择后只留在搜索/下载库，不进入地图攻略页；下载库显示每洞进度、暂停/继续、取消和错误。备战界面只接受完整球场包，完全不显示简化地图。这样可以删除一整条“半成品地图”产品路径，但必须把下载任务做成持久、可恢复的队列，诚实面对首次下载可能需要几分钟的代价。

Fable 另外指出：S70 的洞图固定任务朝向并没有可靠证据支持服务端自由旋转；若用户需要旋转，应只做客户端视口变换（先缩放/平移，旋转作为备战二级操作），底图与 overlay 使用同一仿射变换，绝不按角度生成服务端新图。

本轮联合审查还确认了一个与本次“复盘没有落点”直接相关、但不属于下载的独立问题：历史 shot 数据本身大多完整，当前 geometry-authority 硬门会把已有 GPS 清成空数组；9+9 合并局还存在后九杆未重映射的问题。该项必须列入 P0/P1，不能等下载系统改完才处理。

## 证据

| 结论 | 证据 |
|---|---|
| cron 实际每小时运行 | homeserver `crontab -l`: `37 * * * * /home/jason/aicaddie-sync.sh` |
| 同步失败 | `~/aicaddie-sync.log`: `Unable to find image 'aicaddie-sync:latest' locally`、`pull access denied`、`SYNC FAILED (exit 125)`，连续每小时出现 |
| 数据未更新 | 私有卷 owner `data/scorecards` 最新 mtime 为 2026-07-24；当前日期为 2026-08-19 |
| 缺失镜像 | `docker images` 没有 `aicaddie-sync:*`；只有 API 镜像 |
| 生产代码漂移 | API 仍运行约两周前的旧镜像；`/api/v2/health` 返回 `revision: unknown`，不是当前批准分支的 SHA |
| 设置“同步”语义错误 | `RoundHomeView.swift:466-470` 的按钮调用 `onSync`；App 注入的是 `syncPendingEvents()`，只上传本机事件，不调用 Garmin sync |
| 连接 Garmin 不会拉取 | `GarminSessionView.swift:78-104` 只 POST session import 并保存 cookie，没有随后执行 sync |
| iOS 读取链路可刷新 | Results 页面每次打开/下拉刷新请求 history/stats；服务端 stats fingerprint 会随 scorecard/shot 文件变化失效 |
| 可复用的离线队列已存在 | `AICaddieApp.swift:2544-2760` + `OfflineStore.swift:952-976`：实战离线安装可选择后入队、逐洞保存、active 重启转 queued；备战详情目前没有复用同一协调器 |
| 不是系统级后台 | `AICaddieApp.swift:2700-2725` 只用 `beginBackgroundTask`；普通 `URLSession.data(for:)` 被系统挂起/杀掉后只能前台恢复。当前文案已改为“服务器继续准备，回前台从已保存洞继续”，没有把它描述成 background URLSession |
| 备战地图状态不一致 | `CourseReviewView.swift:111-258,333-460` 同时存在 partial CourseView、精确 coverage 门禁和 placeholder 分支；不同状态下观感不一致，不能把任何一条分支都当作最终地图 |
| 手机地图不能旋转 | `HoleImageMapView.swift:45-66` 无 `RotationGesture`；复盘地图已有缩放/拖动，但不是备战旋转 |

## 产品决定（建议）

### 1. 备战的语义

“选择球场”只表示把一个目标加入下载库，不等于已经可以进入备战。选择后留在搜索页或独立的下载库/进度页，显示：

`排队 → 准备球场数据 → 保存地图 n/18 → 已完成`

只有 `已完成` 才显示“进入备战”，并导航到完整攻略地图。下载中不允许进入备战界面，也不渲染 CourseView 简化轮廓；用户只能看到进度、错误和控制按钮。完成条件是选定球场的 geometry、hazard/prep facts、策略数据和全部 18 洞 topo 资产通过 manifest/完整性校验并写入本地。完成后不自动跳转，显示明确的“进入备战”按钮，避免打断用户当前操作。

这意味着“简化地图”不再是一个降级 UI，而是应从备战产品路径中移除。可以暂时保留底层解析器或旧组件，直到所有引用迁移并通过回归；但不应继续维护或调用第二套简化渲染逻辑。

### 2. 地图旋转边界

只在 iPhone 备战/攻略地图增加旋转手势（整张地图和 overlay 一起变换），加“重置方向”按钮；不改变实战地图的 Garmin 式默认方向，也不改 Watch View Green 已批准的旋转、边界和旗位持久化协议。旋转是本地显示状态，不写入球场事实。

### 3. 设置菜单语义

右上角菜单改成三个清楚的区域：

- Garmin 数据：上次拉取时间、状态、`立即同步 Garmin`；
- 本机记分：待上传数量（自动上传，不再把它叫 Garmin 同步）；
- 球包/账号：进入现有设置页。

视觉上使用一个状态头卡 + 简洁行项目，去掉技术 footer 和含糊的“同步”按钮。

## 分阶段执行

### P0：先恢复可用（最小改动）

1. 在**明确的目标部署 SHA**上重建 API 与 sync 镜像，生成 `aicaddie-sync:<same-sha>`，再给 cron 使用；先手动跑一轮，确认新 scorecard、shot、sync status 落盘。不要只把当前分支代码塞进旧 API 镜像。
2. cron wrapper 启动前 `docker image inspect`，缺镜像立即写清楚的告警并退出；日志记录 API/sync SHA。CI/deploy 必须把 API 和 sync image 作为一个不可分离的 release。
3. iOS 增加真正的 Garmin sync client/action；连接成功后可立即执行一次，设置页按钮同时上传本机待发事件并拉取 Garmin，分别显示结果。成功后刷新 course options、home、history。
4. 备战选择结果先留在下载库；当前复用 `LiveRoundAppModel` 的 app-scoped 持久队列，任务未完成时只显示下载进度，不进入备战界面。已删除/停用备战页面的简化地图与页面级 loader；完整 facts + topo 安装并校验后，才显示“进入备战”。
5. 修复历史 shotmap 的 geometry-authority 硬门：已有 GPS 但 geometry authority stale 时仍返回 shot count/可用投影，并明确标记地图陈旧；没有几何时也不能把 GPS 静默伪装成“没有落点”。同时修复 9+9 合并局后九杆的 hole/globalId 重映射。

### P1：稳定下载与可观察性

6. 给 `/prep`、coverage、`/topo.png` 增加 transient-only retry、ETag/尺寸日志和每洞状态；保持服务端 singleflight、最多两路冷渲染，不盲目提高并发。实战仍可首洞优先，备战整包走受限吞吐。
7. 已把服务端 geometry/topo 升级从 FastAPI `BackgroundTasks` 移到小型持久幂等 journal（`server_v2/course_install.py`），状态为 `queued/running/ready/failed`；客户端可按状态读取，API 重启后恢复任务。player-specific prep facts 仍由 iOS `OfflineStore` 原子保存，避免把私人球杆数据写进公共 journal。
8. 继续复用 `OfflineStore` 的 revision-keyed PNG、原子写和逐洞进度；把 facts 完成和 topo 完成分开展示，避免“整座球场 ready 前什么都不可用”。
9. 手机加入 `RotationGesture` 与 reset（先缩放/平移，再按需开启旋转）；重做设置 sheet，并补充同步/下载失败的可见错误和重试入口。

### P2：速度和规模

10. 服务端生成不可变 course bundle manifest（facts + topo URL/revision/size/checksum），静态资产放对象存储/CDN。
11. iOS 用 background `URLSession` 下载 bundle 文件，按文件校验后原子安装；BGProcessing 只作补偿，不把它当实时保证。
12. 只预取用户明确选择的球场；附近/搜索只取 metadata。对最近使用球场做服务端预热，不下载全世界球场。

## 不做的事

- 不修改已批准 `779b31c` 的 Watch View Green；不新增 Watch installer、CAS 或第二套地图协议。
- 不因为“慢”把 geometry/topo 并发无限调大；homeserver 只有 4 核，当前后端已经有冷渲染并发闸门。
- 不把 CourseView 简化 overlay 当作最终 topo；也不在未有事实时显示假障碍/假距离。
- 不用“历史列表缓存”掩盖 Garmin cron 未运行；先修入库，再验证 history/stats/iOS 刷新。
- 不把一次手动 Garmin sync 放进每次前台启动；自动 cron + 明确的手动刷新即可，避免耗尽 Garmin 会话和服务器资源。

## 当前验收顺序

1. `aicaddie-sync:<sha>` 存在，手动 cron exit 0；新 scorecard/shot mtime 更新。
2. 认证请求能在 `/history/rounds`、round detail、shotmap 看到新球局；iOS 成绩页下拉刷新显示同一场。
3. 设置中的“立即同步 Garmin”不会只显示“本机事件已同步”。
4. 选择备战球场后始终停留在下载库；下载中没有备战地图或简化地图；返回/重启 App 后进度仍在；完整 bundle 校验通过后才出现“进入备战”。Python contract tests 覆盖状态机；iOS 真机/模拟器仍需 GitHub Actions 编译与 UI 验证。
5. 历史复盘：一个 geometry authority stale 但有 GPS 的洞仍显示杆数/落点数量并标注“地图数据待更新”；一个 9+9 合并局的后九洞能显示第二段球场的杆。
6. App 被挂起/重启后下载任务恢复；备战地图（完成后）旋转时底图和所有 overlay 同步旋转，重置后恢复默认方向。

纯 Fable xhigh 已于 2026-08-19 完成（无 fallback；远程运行目录 `/home/jason/codex-runs/aicaddie-fable-sync-download-20260819`）。本工作树改动仍未部署；生产同步镜像缺失问题仍需单独确定目标 release SHA 后处理，不能用本地 journal 改动替代部署修复。

## Opus 5 独立代码审查（2026-08-20）

本轮按用户要求在 homeserver 以 `claude-opus-5`、`high`、无 fallback、只读方式完成。Opus 没有读取 token/cookie/`.env` 或生产球局，也没有修改文件、运行服务或构建。审查 session 为
`6c627beb-f089-4c71-a1ce-d41c47013994`，原始结果保存在
`/home/jason/codex-runs/aicaddie-opus-final-code-review-20260820/final-review.json`，本地副本为
`.codex-tmp/opus-final-code-review-20260820.json`，SHA256 为
`70b6480422085925dfd3b9889f68d7bc27443eb87c8d5b3755da5d606564168`。

Opus 总结为 `READY WITH FOLLOW-UPS`，没有发现 Critical；但指出 H1/H2/H3 三个高优先级问题和 M4-M9 六个中优先级问题。以下是审查后对当前工作树的逐项裁决：

| 项目 | 当前裁决 | 说明 |
|---|---|---|
| H1 authority 观测失败与 stale 混淆 | **已修复** | `geometry_evidence` 输出 `current/stale/unknown`；`unknown` 不重绑 ready 行，worker 保持 queued/running 并使用有上限的单 timer 指数退避，不再立即自旋或伪装成用户可见失败。 |
| H2 lifespan 扫描与 journal 无界增长 | **已修复主要风险** | resume 已移到 daemon 线程；加入 restart backlog、逐个恢复和 terminal retention。`course_install` 回归覆盖恢复、清理和交接。仍建议后续增加跨进程锁/磁盘 fsync。 |
| H3 iOS journal 行为测试缺失 | **部分修复** | `SyncClientTests` 已覆盖 install/status 解码及 composite `back_global_id`；`LiveRoundAppModelTests` 已覆盖 `running + topo=queued` 不取 PNG、随后 `topo=ready` 才取图。仍需在 GitHub Actions/macOS 上执行 Xcode，补齐探针异常、revision mismatch 和 composite 多源的运行时断言。 |
| M4 composite status 的 back GID 不一致 | **已修复** | iOS 抽出 `courseInstallBackGlobalId(for:)`，刷新和收尾查询共用，并传递 `back_global_id`。 |
| M5 status 探针异常误报失败 | **已修复** | 收尾查询改为 `do/catch`；网络/5xx 探针异常保持 preparing/downloading 并低频重试，只有明确非进行中状态才标失败。 |
| M6 ready 包不复核 Garmin 新 release | **已实现，待 Xcode 验证** | `validateReadyPrepCourse` 在进入备战前复核 install/status 的 per-hole revision；本地包不完整会重新排队，status 404/暂时不可达保持离线可用，明确 revision mismatch 才重新下载。 |
| M7 完成徽标只按 globalId | **已修复** | iOS 改用 `(globalId, teeBox, nine)` 精确 key；不完整的 ready 行重新显示继续下载。 |
| M8 真实 Pydantic `model_copy` 路径无测试 | **已修复** | 新增真实 `LiveRoundPackageResponse` 分支测试，验证 alias 序列化。 |
| M9 install/status 无 response model | **已修复** | 新增严格 `CourseInstallStatusResponse` / `CourseInstallHoleStatus` 并挂到路由；本次还把 `geometryAuthorityObservation` 加入严格 live-package schema。 |

### 审查后验证中发现并修复的回归

- release rebind 时旧的 `topoRevision` 未清除，会使新版本看起来像旧 topo 已完成；现在确证 stale/revision change 会同时清掉两种 revision。
- authority `unknown` 在不确定时会保留既有 ready topo revision，不再因一次无法观测而把已完成行降级；相应测试覆盖 transient unknown 与新 release 两条路径。

### 本轮新增收口

- `MobileCourseSearchView` 不再按 `globalId` 粗匹配 retained download；备战父层通过 `globalId + teeBox + nine` 提供精确 key，避免同一 Garmin 球场多个发球台互相覆盖状态。
- `SyncClientTests` 新增 install/status typed response、洞级 revision、composite `back_global_id` 的请求/解码覆盖。
- `LiveRoundAppModelTests` 新增服务器 journal 门控：第一次 status 为 `running/topo=queued` 时不请求 topo PNG，下一次 status 为 `ready/topo=ready` 后才下载并落盘全部图。
- `tests/test_mobile_contracts.py` 的备战断言改为精确 key 语义，不再要求已经废弃的 global-id-only 参数。

### 远端验证结果

在 homeserver 独立目录 `/home/jason/codex-runs/aicaddie-opus-close-20260820-r2`，使用镜像
`aicaddie-system-adjust-test-20260820:latest` 的预置 `/app/.venv` 执行：

```text
AI_CADDIE_DATA_MODE=fixture \
uv run python -m unittest \
  tests.test_course_install \
  tests.test_mobile_contracts \
  tests.test_server_v2_mobile \
  tests.test_topo_render -v
```

结果：`Ran 221 tests in 9.568s ... OK (skipped=3)`。另行执行
`tests.test_geometry_evidence`：`Ran 15 tests ... OK`。跳过的 3 项都明确要求 CI 中不存在的真实解码 prodgeometry；没有失败。一次只读挂载导致的 8 个文件锁错误不计入结果，随后已用可写 scratch 目录重跑通过。

### 仍然不能宣称完成的事项

1. 尚未在 macOS/GitHub Actions 执行真实 `xcodebuild`、iOS UI 测试或 Watch 编译；Swift 目前有源码契约和新增 XCTest 源码，但未取得编译/运行结果。
2. 尚未部署 API/sync 镜像，也没有上传 TestFlight；homeserver 生产 cron 的 `aicaddie-sync:latest` 缺失仍是独立 P0 运维问题。
3. 尚未做冷球场 18 洞实际下载 benchmark，也没有证明 `M6` 的 release revalidation 和 H1 unknown 终态在真机上完整闭环。

因此当前准确结论仍是：Python/backend 状态机和跨端契约回归已通过，代码可以进入下一轮修复与 CI 验证；不能把这次 Opus 审查结果写成“已发布”或“TestFlight ready”。
