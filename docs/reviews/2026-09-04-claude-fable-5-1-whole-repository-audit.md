# Claude Fable 5.1 Whole-Repository Audit

Date: 2026-09-04 UTC
Mode: read-only, source-only review
Model: `claude-fable-5-1`
Provider: first-party
Effort: `max`
Session: `98bd77e3-c841-4ca2-86ee-91a1001b5382`
Snapshot: `/dev/shm/garmin-ai-caddie-fable51-audit-20260904T110214Z`
Snapshot expiry: 2026-09-05T11:02:14Z
Snapshot contents: 984 files, approximately 22 MiB; no `.git`, dependencies, build products, private data, or credentials
CLI tools: `Read,Grep,Glob`; permission mode `dontAsk`; fallback disabled
Raw JSON archive: `/home/jason/garmin-ai-caddie-data/archives/20260904T110214Z-fable51-whole-repository.json`
Raw JSON SHA-256: `50b56130e2b9c29920bf9061b461a539b0cad08902d47d13aad460c416553440`
Fable result SHA-256: `1a6b22dddf1259cef36e9ed6f080fab6acc1b19f6f823549606a019da48eab18`

The repository report below is a Codex-curated rendering of that raw result;
its final source-copy hash is recorded in `docs/operations/PROJECT_STATE.md`.

The first launcher attempt was invalid and was terminated before producing output because its cwd was `/home/jason`; it is excluded from this report. The corrected session was verified in the dedicated snapshot above. Fable did not run tests, builds, browsers, services, or network requests.

---

审计完成。以下是基于源码快照的独立审计报告（未运行任何测试、构建或网络请求；无 `.git`，分支事实仅依据随附文档核对）。

## 一、Findings（按严重性排序）

未发现 P0。没有发现会直接丢失用户成绩或伪造击球坐标的路径：Watch 与 iPhone 在无定位时都不会生成 location 事件（`WatchRoundContainerView.swift:984,1047`；`CurrentHoleView.swift:2592,2684-2686`）。

**F1 · P2 · 文档/证据 finding（置信度高）：MAP1 的精确放置与 Touch Target 只有静态字符串测试和纯函数单测，PROJECT_STATE 把它写成"covered by the current code and tests"，且"no-GPS 开局到地图"没有端到端 CI 断言。**

| 证据 | 位置 |
|---|---|
| 声明措辞 | `docs/operations/PROJECT_STATE.md:37`、`:1038-1043`、`:129-134` |
| loupe/Touch Target 的"测试"是 `assertIn` 源码字符串 | `tests/test_mobile_contracts.py:3314-3332`、`:3635-3653` |
| iOS UITests 不引用任何手机 Touch Target、View Green、精确编辑器标识符 | `mobile/ios/AICaddieUITests/` 中无 `live-open-map-from-hero`、`live-map-target-*`、`live-map-distance-panel`、`live-green-flag-*`、`round-shot-precision-*` |
| 唯一被真实手势覆盖的 loupe 是复盘长按拖动 | `ReviewEditUITests.swift:212-234` |
| Native Mobile CI 的 Watch 运行时截图只有 11 个模式，不含 touch-target/view-green | `.github/workflows/native-mobile.yml:629-639` |
| touch-target/view-green 截图只在另一条工作流，且用 `measuredPxOverride` 预置点位而非手势 | `.github/workflows/watch-runtime.yml:582-593`；`WatchUITestRoot.swift:316-319` |
| 拒绝定位/无 fix 的 UI 测试止步于"可开局"，不点 Start | `TeeSelectionUITests.swift:256-259`、`:292-295` |
| 唯一的"无 fix 看到地图"是重启恢复一个用注入 fix 开的局 | `RealFlowUITests.swift:1131-1156` |
| 离线开局测试保留注入的 GPS | `TeeSelectionUITests.swift:376-478` |

影响：用户反馈"手机不能选点看距离"在 CI 上无法被证伪，也无法被证实；PROJECT_STATE 对 MAP1 的完成度表述高于证据。修复方向：为 hero 点击、放置目标、距离面板、View Green 拖旗、精确编辑器确认各加一条 XCUITest，分别在有/无注入 fix 下运行；在 PROJECT_STATE 明确写出"loupe 拖动态在 simctl 截图中不可捕获"；watch-runtime 在 MAP1 之后至少跑一次。

**F2 · P2 · confirmed source finding，跨端不一致（置信度高）：无 GPS 时 iPhone 主图显示"发球台到果岭"的静态码数且标签不注明来源，并用它驱动球童；同一状态下 Watch 显示 999 与"等待定位"。**

| 证据 | 位置 |
|---|---|
| iPhone 无 fix 时回落到静态 F/M/B，仅以 `isLive` 区分 | `CurrentHoleView.swift:580-586` |
| 标签只有"到果岭"与"果岭 · 实时"两种 | `LiveHoleComponents.swift:907` |
| 球童距离回落到 `staticMiddleM`，不区分打法 | `CaddieDecisionRequestBuilder.swift:8-26`；`CurrentHoleView.swift:2675-2681` |
| Watch 无 fix 一律 999 并标"等待定位" | `WatchRoundContainerView.swift:260-262,580-590`；`WatchHoleMapView.swift:778-783,895` |
| 手机的两个详情面板反而标注了"发球台 → 目标/旗位" | `LivePlayMapDetailView.swift:299`；`LiveGreenDetailView.swift:259` |

影响：离场开局时手机主图上的"中 385"读起来像当前距离，与 Watch 的 999 语义冲突；不会伪造坐标，但违反用户要求的"诚实状态"。修复方向：`isLive == false` 时把标签改为"发球台→果岭"或采用与 Watch 一致的 999 状态；静态回落只用于 tee 打法。

**F3 · P2 · confirmed contract drift（置信度高）：刚在 reconciliation 中被确认为 active wire contract 的 `live_round_event.schema.json`，其 score payload 禁止 `fairway`，而 Watch、iPhone、服务器都在使用它。**

| 证据 | 位置 |
|---|---|
| schema score payload `additionalProperties:false`，只允许 `strokes`/`source` | `mobile/contracts/live_round_event.schema.json:64-78` |
| Watch 直连后端写入 `fairway` | `WatchBackendClient.swift:229-233` |
| 手机中继与手机记分写入 `fairway` | `WatchEventBridge.swift:471-473`；`LiveScoreConfirmation.swift:109` |
| 服务器自有校验表接受并投影 `fairway` | `server_v2/models.py:53,84,141`；`ai_caddie/caddie/mobile_live.py:3294-3297` |
| readiness 把该文件当作契约来源 | `server_v2/readiness.py:26` |
| 契约测试只校验手写 fixture，未含 `fairway` | `tests/test_mobile_contracts.py` 相关 fixture |

影响：当前无运行时损失，因为服务器不用该 JSON schema 校验；但任何依据 schema 的消费方或未来校验器都会拒绝真实 score 事件，reconciliation 文档中的 authority correction 建立在过时文件上。修复方向：schema 增加 `fairway` 枚举；新增测试把 Python 校验表与 JSON schema 做双向一致性断言。

**F4 · P3 · contract drift（置信度高）：`watch_round_state.schema.json` 与 Swift 编解码器不同步。** 顶层 `additionalProperties:false`（`:5`）却缺 `rootCaddieRecommendation`（`WatchRoundState.swift:424`；`WatchEventBridge.swift:422`）；`availableClubs.items` 缺 `token/distanceSource/confidence`（`WatchRoundState.swift:7-12`）；`hazards.items` 缺 `sideM/frontDistanceM/backDistanceM/frontPx/backPx`（`:44-48`）。lockstep 测试只做 Swift 对 Swift（`tests/test_mobile_contracts.py:3537-3600`），schema 测试用手写样例（`:339-399`）。无运行时校验，故无损失；修复同 F3 思路。

**F5 · P2 · documentation/process finding（置信度高）：Cloud 审计归档处于未提交状态，但账本已记 `done`，临时快照与报告已删除，哈希无法对归档文件核验。**

| 证据 | 位置 |
|---|---|
| 账本行 `CLOUD-AUDIT` 为 `done`，并称"snapshot/report cleaned" | `PROJECT_STATE.md:563`、`:109-118`、`:1025-1031` |
| 归档报告自述"after this archive was committed" | `docs/reviews/2026-09-04-cloud-whole-repository-audit.md:55-57` |
| 记录的 SHA-256 是临时报告的，不是归档文件的 | 同上 `:53-54`；`PROJECT_STATE.md:117-118` |
| `evidence/*` 保留条件是"Cloud report and artifact hash are archived" | `branch-strategy-20260904.md:44,119` |

影响：审计产物只剩工作树单副本；按 AGENTS.md 规则账本状态是权威，此时它是错的；清理门槛可能被误判为已开启。修复方向：先提交归档并记录归档文件自身哈希，再改 `done`；在此之前不得触碰 `evidence/*`。

**F6 · P3 · 文档漂移（置信度高）**：`branch-reconciliation-20260904.md:7` 写 reconciliation 分支"immediately after the PR is merged or closed"到期，与 `PROJECT_STATE.md:958-960`、`branch-strategy-20260904.md:111` 的"保留到审计与 owner 清理"冲突；`branch-strategy-20260904.md:108` 仍把 canonical 固定在 `f0b193a2`；`mobile/ios/README.md:37` 写"Current branch: codex/release-hardening-20260827"；`docs/USER_GUIDE.md:144` 仍把果岭调旗列为 backlog，虽有历史声明横幅。另一个未知：`branch-strategy:27` 说 `6593b95e`"adds this policy record"，Cloud 报告 `:24` 说该记录在 `6593b95e` 被"corrected"，无 git 无法裁定。

**F7 · P3 · confirmed source finding（置信度高）**：安装日志的 Tee 键仍有 `"blue"` 兜底：`server_v2/main.py:1924`、`:1953`、`server_v2/course_install.py:312`。两端客户端都总是发送 `tee_box`（`WatchBackendClient.swift:369,402`；`SyncClient.swift:368`），所以只在省略参数时触发，后果是 status 查错键返回 404 后本地重试，属良性；但与"绝不伪造 Blue"的规则矛盾。修复：兜底改为 `unknown`。

**F8 · P3 · 跨端不一致（置信度高）**：Watch Touch Target 无腕上 fix 时不给任何距离，因为像素标定依赖 GPS 的球员到旗距离（`WatchHoleMapView.swift:79-117`；`WatchRoundContainerView.swift:251-258`）；iPhone 用 overlay 的 `ppm` 给出发球台参考距离（`LivePlayMapDetailView.swift:528-538`）。Watch 本地已有累计米数路线可做标定（`WatchCourseStore.swift:492-511`）。两者都诚实，但离场用户在表上"选点测距"只见准星不见数字。

**F9 · P3 · 工具漂移**：`tools/contracts/check_authority.py:33-36` 仍硬编码 `live_round_event.schema.json` 为 `v1_compatibility_only`，而 manifest 已移除该条目（`contracts/canonical/authority.json:20-27`）。目前惰性，但形成第二真源。

**F10 · P3 · 暴露面说明，非缺陷**：`topo.png`/`green.png` 无鉴权公开（`server_v2/main.py:779,844`；`_requires_admin_token` `:317-355` 未覆盖；Watch 请求不带凭据 `WatchBackendClient.swift:439-441`），在公网 Funnel 上提供 Garmin 派生渲染图，是策略决定，建议 owner 明确记录。

**F11 · P3 · Watch 可达性**：部分缓存的球场在无 GPS 且无手机配置时无法从选择器进入：已下载分组只列精确完整的（`WatchStartView.swift:499-524`；`WatchCourseLibrary.swift:57-59,776-782`），附近需定位，搜索需 config（`WatchCourseLibrary.swift:183-187`）。进行中的局由 `WatchRoundStore` 持久化，所以只影响结束后再开。

## 二、专项核对

**用户提出的 MAP1/S70 行为，代码实际支持什么：**

| 行为 | 结论 | 关键证据 |
|---|---|---|
| Watch 离场无 GPS 开局直接显示地图 | 部分支持。有精确缓存或包内首洞 seed 时直接进地图；无缓存且无手机网络时是"地图准备中"占位加 999，不是球场地图 | `WatchRoundContainerView.swift:15-28,894-947`；`WatchMapPreparingView` `:64-151`；`WatchCourseLibrary.swift:296-363,514-553,578-582` |
| Watch 未知 Tee 不伪造 Blue | 支持 | `WatchCourseDownload.swift:75-85`；`WatchRoundSetupView.swift:500-509`；服务器 `analysis.py:98-147`；测试 `test_server_v2_mobile.py:1104-1174`、`test_course_tees.py:115-151` |
| 手机无 GPS 手动搜索后直接开局并显示地图 | 代码支持，Start 与 GPS 解耦；地图需网络取到 prep，否则"地图准备中…" | `StartRoundView.swift:142-163`；`AICaddieApp.swift:673-716,959-1069`；`CurrentHoleView.swift:407-441,646-664` |
| 无 GPS 距离显示诚实 | Watch 是 999；iPhone 是静态发球台码数且标签不明（见 F2） | 见 F2 |
| 手机地图选点看距离 | 代码存在且可达：hero 透明点击层、页眉按钮、更多调整；两段距离在无定位时用 `ppm` 像素标定 | `CurrentHoleView.swift:278,620-637,775`；`LivePlayMapDetailView.swift:201-334,528-538`。运行时未验证（F1）。一个可能解释：详情页要求 `resolvedMapOverlay` 非空，否则显示"这洞暂时没有可交互地图"（`:82-98`） |
| 果岭拖旗与补杆位置的 S70 loupe | Watch Touch Target 与 Green View、iPhone Touch Target、View Green、复盘拖动与精确编辑器均有 loupe，边界均夹在安全区并避开底部控件，均带 accessibilityLabel/Identifier | `WatchHoleMapView.swift:120-150,599-621,1458-1513`；`WatchGreenPreviewView.swift:503-531,674-694,1145-1202`；`LivePlayMapDetailView.swift:154-170,691-705,721-787`；`LiveGreenDetailView.swift:138-151,691-708,739-808`；`RoundShotEditComponents.swift:113-127,308-314,435-491,667-691,963-977,983-1046` |
| Web 复盘 | 只有指针拖动，无 loupe 与缩放；文档未声称有 | `web_v2/src/components/ReviewHoleCanvas.tsx:103-245` |

**分支与治理：** PROJECT_STATE、branch-strategy、branch-reconciliation、Cloud 报告在 `1775d87a` 父序（旧 integration 第一父、`a331281a` 第二父）、`79ee08cd` 为 MAP1 树的 history-only merge、三个 release tag 上互相一致。没有文档把审计或 `evidence/*` ref 当产品分支，分类表明确写"never merge as product code"。不建议重放 46 个旧提交的决定有依据。未提交状态的自洽问题见 F5、F6。没有文档把 Cloud 审计误称为 Fable：Fable 5.1 只被记为分支评估输入，且 `PROJECT_STATE.md:1035-1037` 明确说明未使用 homeserver Fable。本次 Fable 全仓审计在账本中尚无条目。

在归档提交与 owner 清理决定之前不应清理：`integration/map1-reconcile-20260904`、`codex/p0-p1-p2-checkpoint-20260823`（`d26feaba`）、全部 27 个 `evidence/*`、tag `release/testflight-0.1.0-build-47`、`deploy/backend-2026-09-02`、`source/map1-2026-09-04`、`main`（`0f696b88`）、open PR #176/#218/#219/#291 对应的四个 `superpowers/*`，以及文档仍引用的 `codex/tee-meta-fix-20260829`、`codex/release-hardening-20260827`。`fix/*` 三个 ref 是唯一的清理候选，也应等归档完成。

**认证、隔离、离线与回滚：** 管理员令牌用 `hmac.compare_digest`（`main.py:291`；`players_api.py:119`）；成员 bearer 不能借管理员头提权（`players_api.py:200-208`）；会话令牌散列存储（`identity_repo.py:148`）；玩家分区路由清单与 gate 清单一致（`players_api.py:222-313`；`main.py:317-388`）；Release 构建不向 Watch 下发 admin token（`WatchEventBridge.swift:844-846`）。Web 把 bearer 放 localStorage 是记录在案的取舍（`web_v2/src/sessionStore.ts:4-7`）。Watch 提前把临时模板持久化并在升级中逐批写入，进程被杀可恢复（`WatchCourseLibrary.swift:355-356,387-404`）。回滚风险仍是 PROJECT_STATE 自述的候选容器启动即跑 Alembic 迁移，回滚需恢复数据库快照而非仅换镜像。

## 三、Verdict 与清单

**整体 verdict：NOT READY**，指 MAP1 不能从 `evidence-open` 关闭，也不能进行对外分发或生产提升；维持内部 TestFlight build 47 现状且不再上传，属可接受。

必须立即处理：
1. 修正 PROJECT_STATE 对 MAP1 测试覆盖的措辞，并补 F1 列出的手机 Touch Target、View Green、精确编辑器 XCUITest 与 MAP1 之后的 watch-runtime 运行，或明确记录 loupe 拖动态在 CI 中不可捕获。
2. 提交 Cloud 归档报告，记录归档文件自身哈希，再把 `CLOUD-AUDIT` 置为 `done`；此前不做任何 ref 清理。
3. 让 `live_round_event.schema.json` 接受 `fairway`，并增加 schema 与服务器校验表的一致性测试。
4. 决定 iPhone 无 GPS 主图语义，与 Watch 的 999 状态对齐或加明确来源标签。

可延后：F4、F6、F7、F8、F9、F10、F11。

已检查的主要区域：`AGENTS.md`、`CLAUDE.md`、`README.md`、`docs/operations/*` 四份状态与分支文档、Cloud 归档、`contracts/canonical/authority.json` 与 `tools/contracts/check_authority.py`、`mobile/contracts/*` 四个 schema、Watch 的 App、StartView、SetupView、CourseLibrary、CourseStore、CourseDownload、RoundModel、RoundContainerView、HoleMapView、GreenPreviewView、LocationProvider、BackendClient、RoundState，iOS 的 AICaddieApp、StartRoundView、CurrentHoleView、LivePlayMapDetailView、LiveGreenDetailView、LiveHoleComponents、RoundShotEditComponents、WatchEventBridge、SyncClient、CaddieDecisionRequestBuilder、LiveRoundEventBuilder，三组 UITests，`server_v2` 的 main、mobile、models、players_api、course_install、readiness，`ai_caddie/caddie/mobile_live.py` 与 `analysis.py` 的 Tee 解析，相关 Python 测试，两条原生工作流与 `ci.yml`，Web 的 ReviewHoleCanvas 与存储模块。

未运行或无法核实：任何测试、构建、lint、Docker、模拟器与真机；所有 GitHub run ID、artifact 哈希、App Store Connect 状态、backend 部署 revision；完整 Git 对象与 ref 图、268 个远程 ref 的可达性统计；`04ab1da8` 与 `6593b95e` 的具体内容差异；S70 数码表冠与触控手感、GPS 硬件行为、配对设备行为。
