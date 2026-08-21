# Garmin 新球局同步与备战下载方案

日期：2026-08-20 UTC
状态：`BACKEND/SYNC DEPLOYED / PYTHON + IOS + WATCH CI VERIFIED / TESTFLIGHT NOT UPLOADED`。本稿不改变已批准的 Watch View Green（`779b31c`）。

本轮实际落地范围：

- package 的后台几何/topo 准备改为原子 JSON journal + 单 worker；API 重启会恢复 queued/running 任务。
- 新增 `GET /api/v2/courses/{global_id}/install/status`，响应只含公共课程/洞级进度，不返回 player identity、GPS、球杆距离或 Garmin 凭据。
- journal 每个洞保存 `geometryRevision`，topo 只有在同一 revision 下才算 ready；Garmin release 更新不会复用旧 ready 状态。
- topo future 完成后立即写回洞级状态；worker 收尾期间新增的洞会在 active worker 释放后自动接力，不会遗留在 queued 状态。
- iOS `SyncClient` 可以读取安装状态；备战下载器优先使用该状态减少盲目 coverage 轮询。
- 备战入口只在本机 `OfflineStore` 完整 facts + 全部 topo PNG 校验通过后进入；`CourseReviewView` 不再发起页面级 `/prep`/coverage 下载，也不显示简化 CourseView 地图。
- 服务端仍保留旧 `_upgrade_course_geometry` 作为兼容内部调用，但 package 新路径不再把它挂到 FastAPI `BackgroundTasks`。
- `/prep`、coverage、topo 的 iOS GET 采用短超时和 transient-only 有限重试；备战整包使用受限两路吞吐，不再为不可见的“首洞优先”额外串行等待。

远程定向验证（homeserver Docker + GitHub Actions）：Python/backend 回归、iOS Xcode/UI flow 和 Watch runtime 均已取得通过结果；后端/sync 已于 2026-08-20 部署；修复后的隔离 candidate 已完成真实冷 18 洞 benchmark；未上传 TestFlight。

## 结论先行

这次反馈包含两个互相独立的问题：

1. **新球局没有同步（部署前故障，已修复）**：homeserver 的小时 cron 依赖
   `aicaddie-sync:latest`，该镜像缺失导致 8 月 18–19 日每次运行都以 Docker exit 125 失败。
   现已安装并验证同 revision sync 镜像，生产同步恢复。
2. **备战下载慢/后台停/简化地图难看**：代码有可复用的断点队列，但不是系统级后台下载；冷球场的主要耗时在 Garmin geometry 获取、mesh 计算和逐洞 topo 渲染，不是单纯网络带宽。

因此不能只调一个超时或把客户端并发盲目调大；先恢复同步，再把“选择球场”和“查看攻略”拆成清晰的下载状态机。

## 联合复核结论（Cloud + 纯 Fable xhigh）

两路审查没有发现需要推翻上述根因的证据，但补上了三个重要边界：

1. **Garmin 同步故障与地图下载故障完全分开。** Cloud 的生产证据是同步镜像缺失、cron 每小时 exit 125；Fable 也将“球局未入库”排在下载/缓存之前。不能用重新打开成绩页或清 iOS 缓存替代修复同步链路。
2. **当前“下载”有两条不同的实现，不能混称。** 备战详情页启动的是页面生命周期内的 package/prep/coverage 请求；真正可持久、逐洞落盘的 `OfflineStore` 队列主要在实战离线安装路径。离开备战页后，前者会被 SwiftUI 取消，后端进程内 `BackgroundTasks` 也不是持久队列。这正是用户看到“退回去就中断、再进又像重新下载”的工程原因。
3. **“下载完成前不进入备战界面”可以作为明确产品规则。** 选择后只留在搜索/下载库，不进入地图攻略页；下载库显示每洞进度、暂停/继续、取消和错误。备战界面只接受完整球场包，完全不显示简化地图。这样可以删除一整条“半成品地图”产品路径，但必须把下载任务做成持久、可恢复的队列，诚实面对首次下载可能需要几分钟的代价。

Fable 另外指出：S70 的洞图固定任务朝向并没有可靠证据支持服务端自由旋转；若用户需要旋转，应只做客户端视口变换（先缩放/平移，旋转作为备战二级操作），底图与 overlay 使用同一仿射变换，绝不按角度生成服务端新图。

本轮联合审查还确认了一个与本次“复盘没有落点”直接相关、但不属于下载的独立问题：历史 shot 数据本身大多完整，当前 geometry-authority 硬门会把已有 GPS 清成空数组；9+9 合并局还存在后九杆未重映射的问题。该项必须列入 P0/P1，不能等下载系统改完才处理。

## 部署前证据

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

1. **已完成**：`aicaddie-sync:<sha>` 存在，手动 sync exit 0；485 份 scorecard 与 485 份 shot 文件刷新。
2. **已完成**：认证请求能在 `/history/rounds`、round detail、shotmap 读取新数据；生产公开健康和 sync status 返回目标 revision。
3. 设置中的“立即同步 Garmin”不会只显示“本机事件已同步”。
4. 选择备战球场后始终停留在下载库；下载中没有备战地图或简化地图；返回/重启 App 后进度仍在；完整 bundle 校验通过后才出现“进入备战”。Python contract tests 与 iOS simulator CI 已覆盖；实体设备闭环仍待验证。
5. 历史复盘：一个 geometry authority stale 但有 GPS 的洞仍显示杆数/落点数量并标注“地图数据待更新”；一个 9+9 合并局的后九洞能显示第二段球场的杆。
6. App 被挂起/重启后下载任务恢复；备战地图（完成后）旋转时底图和所有 overlay 同步旋转，重置后恢复默认方向。

纯 Fable xhigh 已于 2026-08-19 完成（无 fallback；远程运行目录 `/home/jason/codex-runs/aicaddie-fable-sync-download-20260819`）。本轮后端/sync 已按下列 revision 部署；iOS 设置页的 Garmin 主动同步动作仍是后续任务。

## 2026-08-20 生产部署记录

- API 与 sync 源 revision：`28a9d1899ccce8293cb79011c98de68f7b0f05eb`。
- API 运行端口：`39051`；旧 `39049`、`39047` 保留作回滚，未删除数据。
- 公网 `/api/v2/health` 返回目标 revision；`/api/v2/sync/status` 返回 `ready`、485/485 和本轮同步时间。
- 历史 smoke：458 个合并后球局、18 洞详情、shotmap `prodgeometry`；备战 smoke：18 洞、13 支球杆、18 洞击球散点。
- cron `/home/jason/aicaddie-sync.sh` 已加入缺失镜像保护、`--pull=never` 和 image revision 日志；`aicaddie-sync:latest` 已固定到同 revision。
- 发布前焦点备份：`/home/jason/aicaddie-production-backups/pre-cceeed8-20260820T215139Z`。

本记录只覆盖后端/sync；没有上传 TestFlight，也不替代实体 iPhone/Apple Watch 闭环验证。

## 2026-08-21 验证收口补充

- Native Mobile CI run `32433707710` 已完成且为 `success`。该 run 的 head 是
  `abec1ee`（当前分支 `93528ce` 只追加了证据文档），已通过 iOS
  `xcodebuild test`、SwiftJCS 边界、设计快照、真实 iOS simulator flow、截图/视频
  采集和 secret scan。
- 同一 run 的 Watch target/runtime 步骤因 `require_live_preflight=false` 被跳过；因此
  不能把这次结果写成 Watch CI 全绿，也不能替代之前独立的 Watch runtime 证据或实体
  Apple Watch 验证。
- 在 homeserver 的冷测 checkout（关键历史复盘文件与当前 `93528ce` 的 SHA 一致）运行
  `tests.test_round_shot_map`、`tests.test_round_shot_map_corrections`、
  `tests.test_server_v2_history_round_detail`、`tests.test_garmin_fetch_completed_only`：
  `Ran 57 tests ... OK`。这覆盖 stale geometry authority 保留 GPS、9+9 后九映射、
  无几何时保留 GPS 摘要以及 pin-only shot cache 重拉。
- 曾尝试在 homeserver 跑完整 `unittest discover`（1,936 项）。业务测试没有出现新的
  断言失败；剩余 3 个失败/错误均来自临时 checkout 的 Git authority 元数据（先是无效
  worktree 指针，后是缺少历史 pinned commit），不是产品代码。历史 bundle 传输在
  homeserver SSH listener 暂时超时后已停止，避免继续占用共享资源；该 suite 不标记为
  全绿，待 SSH 恢复后在带完整 Git 历史的 checkout 重跑。
- 当前仍未上传 TestFlight、未把 `93528ce` 部署到生产，也未修改生产容器或生产卷。

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
| H3 iOS journal 行为测试缺失 | **已验证（仍有后续覆盖空间）** | `SyncClientTests` 已覆盖 install/status 解码及 composite `back_global_id`；`LiveRoundAppModelTests` 已覆盖 `running + topo=queued` 不取 PNG、随后 `topo=ready` 才取图。GitHub Actions/macOS 已执行真实 `xcodebuild test` 和 review-scope iOS simulator flow；探针异常、revision mismatch 和 composite 多源仍可继续补更细的运行时断言。 |
| M4 composite status 的 back GID 不一致 | **已修复** | iOS 抽出 `courseInstallBackGlobalId(for:)`，刷新和收尾查询共用，并传递 `back_global_id`。 |
| M5 status 探针异常误报失败 | **已修复** | 收尾查询改为 `do/catch`；网络/5xx 探针异常保持 preparing/downloading 并低频重试，只有明确非进行中状态才标失败。 |
| M6 ready 包不复核 Garmin 新 release | **已实现并经 CI 验证** | `validateReadyPrepCourse` 在进入备战前复核 install/status 的 per-hole revision；本地包不完整会重新排队，status 404/暂时不可达保持离线可用，明确 revision mismatch 才重新下载。 |
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

GitHub Actions 验证（均为 workflow dispatch，未使用生产部署）：

- iOS Native CI：run `32352452546`，head `9de72b619a0389a47cc8f62974755cbd4b090d0d`。`xcodebuild test`、SwiftJCS consumer boundary、review-scope 的真实 iOS simulator flow、截图/视频 artifact secret scan 均为 success。
- Watch Runtime Visual Check：run `32351441093`，head `5b245cb1dbac16b53a267368f62294dc92b8a065`。Watch XCTest、41mm/49mm runtime boundary capture、round seed/restore、diagnostic artifact secret scan 均为 success。随后提交的 `9de72b6` 只调整 iOS 测试中的并发完成顺序断言，未改变 Watch target。
- 本轮为 CI simulator/runtime 证据，不等同于用户的实体 iPhone/Apple Watch 真机闭环，也不等同于生产 API 已更新。

### 2026-08-21 冷球场基准修正记录

本轮首次运行 `ops/benchmark_course_install.py` 时，使用了一个匿名、此前未
安装的 18 洞目标。结果**不能作为修复后的性能基准**：服务端在 geometry
ensure 阶段进入 `failed`，随后 coverage 报告为 18/18 `missing`，因此没有
合法的冷/热 prep 或 topo 耗时。该运行的持久证据保存在 homeserver 的
`/home/jason/codex-runs/aicaddie-course-benchmark-20260821`，其退出码为 1。

只读检查确认失败发生在 `d9e27b2` 之前的 authority 规则：真实 Garmin ZIP
使用了新的外部 asset namespace，旧代码把 `CourseGenVersion + Version`
硬拼成文件名，导致已经下载、解密、Draco 解码并生成衍生物的洞被误判为
missing。提交 `d9e27b2` 已改为绑定 release 的精确 URL stem、真实 ZIP
SHA-256、提取目录以及 `GlobalId/HoleNumber/内部版本 pair`；没有把校验
放宽成“文件存在即可”。

在修复后的 candidate 冷测前，验收状态曾是：authority 修复有回归测试和
真实生产卷只读验证，但冷 18 洞 benchmark 尚无合法结果。旧失败运行不能
被改写成性能成功，也不能直接复用已经产生中间产物的匿名目标作为“冷”
测试。

随后在独立 candidate（镜像 source revision `abec1ee`、独立可写数据根、
生产 Garmin 会话材料只读挂载）用另一个未缓存目标完成了修复后的冷测。证据
持久证据文件为 homeserver `/home/jason/aicaddie-data/evidence/course-install-benchmark-20260821.json`（candidate 原始副本在
`/home/jason/codex-runs/aicaddie-cold-candidate-20260821-01/benchmark-22708.json`），
SHA-256 为
`b2fdb573ae3b133ff8a69fda303adcde04d3dfbea9ef1436ab17cc39bd382790`；文件只
包含匿名目标摘要和耗时，不包含球场名、坐标、账号或 Garmin 原始数据。

结果：package 首响 58 ms；服务端从 package 开始到 18 洞 geometry + topo
全部 ready 为 108,987 ms（约 109 秒）；客户端断开 15 秒期间服务端由 0/0
推进到 2/2，证明断开后仍继续工作；冷 prep 6 请求窗口 6,337 ms，18 张冷
topo 186 ms；同一 candidate 的热 prep 2,354 ms、热 topo 179 ms。18 洞
mesh、hazard 和 authority sidecar 均完整生成。该结果证明持久安装和
断线续作链路可用，但不等于生产部署后的实体设备体验或 Garmin 服务器在
所有地区的固定 SLA。

### 仍然不能宣称完成的事项

1. 已在 GitHub Actions/macOS 执行并通过 `xcodebuild test`、iOS review-scope simulator flow、Watch XCTest/runtime capture；尚未完成用户实体设备上的真机闭环验证。
2. API/sync 已部署，iOS 设置页主动 Garmin sync 动作已在 `df291d1` 收口，但尚未上传 TestFlight，也未完成实体设备闭环。
3. 修复后的冷球场 18 洞 benchmark 已在隔离 candidate 完成；仍没有证明 `M6` 的 release revalidation 和 H1 unknown 终态在实体真机上完整闭环，也没有在生产 API 上重复冷下载。

因此当前准确结论是：`d9e27b2` 的 authority 修复、Python/backend 状态机、
隔离 candidate 冷 18 洞安装和跨端契约回归已通过；测试契约陈旧断言已在
`14907de` 修正，后端 CI 已通过。后端/sync 已发布；不能把这次结果写成
“TestFlight ready”，剩余工作是实体设备闭环、生产发布后的验证，以及在
确认发布门禁后清理 candidate 临时资源。
