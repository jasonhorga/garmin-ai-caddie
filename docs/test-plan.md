# 测试重建计划（C387）

> 状态：草案，供 Jason / 土土复审。本文是 C387 的第①步交付物；后续子卡按本文第 12 节拆分执行。
> 日期：2026-11-07。范围：服务端（`server_v2/`、`ai_caddie/`、`ops/`）、iOS（`mobile/ios/AICaddie*`）、手表（`mobile/ios/AICaddieWatch*`）。Web（`web_v2/`，规格 J9）**不在本卡范围**，`ci.yml` 的 `frontend` job 原样保留。
> 本文所有「真实入口」都在仓库 `35a402af` 上用 grep 核过（文件:符号；行号随代码变，只作提示）。

---

## 1. 目的和原则

**目的**：删掉现有约 4130 条 Python 测试与约 2050 条 Swift 测试，按产品设计从头重建一套**数量少、走真实入口、每条能对回产品目标**的测试，让服务端快层 ≤3 分钟，并用「注回真实线上 bug」和「变异测试」证明新测试的强度，而不是用条数。

卡原话（C387，Jason 11-07）：「把全量都删掉 从头构建测试」；「全量测试的构造应该也有软件工程的做法」。10-23：「run 一遍 CI 要 5300 个测试，这太夸张了」。

**R-DEV-3**：测试从产品设计顶层出发；修 bug / 新设计 / 上线前全量三者分开；**不为一个 bug 加一条测试、不钉源码原文**。

由此定下的硬规则：

| # | 规则 | 怎么检查 |
|---|---|---|
| P1 | 每条测试的 docstring 第一行写它覆盖的目标 ID（如 `S-11`），一条测试可覆盖多个 ID | 追溯校验测试（第 9 节） |
| P2 | 测试只走真实入口：HTTP 路由（`TestClient`）、CLI `main(argv)`、Swift 的 ViewModel/Store 公开方法、WatchConnectivity 消息处理入口。不 `import` 私有函数（`_xxx`）、不读源码文本、不 grep 仓库文件 | small 测试扫描 `tests/` 禁止 `read_text()` 读 `server_v2/`/`ai_caddie/`/`mobile/` 下的 `.py/.swift` |
| P3 | 修 bug 时**先看现有目标测试为什么没抓到**：等价类/边界值缺了就补到该目标的参数表里，不新开「test_cNNN_xxx」文件 | 文件名禁止 `test_c\d+`（追溯校验里查） |
| P4 | 一个目标有且只有一个「主测试」（走最外层真实入口），可以有若干「深度测试」（同入口的参数化用例），深度由风险决定（第 2 节） | 追溯矩阵 |
| P5 | 尺寸（small/medium/large）由测试所在目录决定，预算写死、超了列进汇总，挂死由总超时拦（第 3 节） | 运行器统计 |
| P6 | 测试封闭：不依赖机器忙闲、真实时钟、外网、执行顺序（第 5 节） | `tests/offline.py` 守卫 + 运行器检查 |

---

## 2. 产品目标清单

### 2.0 字段说明

- **规格**：`docs/product/2026-10-23-product-test-spec.md` 的编号。该规格没有 `J-xx` 形式，实际为 `J1`–`J9` 小节内的 `1.1`–`9.5` 条目和发布门 `G1`–`G8`；本文写作 `J5.9`、`G1`。找不到写「缺规格」。
- **风险**：**高** = 可能导致数据丢失 / 记分或统计错误 / 越权或泄密 / 上线或出包被阻断；**中** = 功能错误但可见、可绕过、不丢数据（如建议不准、页面数字缺失）；**低** = 体验/诊断类，不影响成绩与数据。
- **深度**（按风险）：
  - **D3（高）**：主测试 + 等价类全覆盖 + 边界值 + 状态迁移全部合法/非法边 + 幂等/重试/并发至少各 1 例 + 进变异测试名单 + 进注回 bug 名单；
  - **D2（中）**：主测试 + 主要等价类 + 关键边界；
  - **D1（低）**：只有主测试（happy path + 一个降级路径）。
- **入口**：测试必须调用的最外层真实入口。

### 2.1 服务端（S，31 个）

| ID | 球手视角目标 | 规格 | 风险 | 深度 | 真实入口（文件:符号） |
|---|---|---|---|---|---|
| S-01 | 我用 Apple 登录拿到会话，能刷新、能登出，过期会话被拒 | J7.2 | 高（账号） | D3 | `POST /api/v2/auth/apple` `server_v2/auth_api.py:apple_sign_in`；`/auth/refresh` `refresh`；`/auth/logout` `logout`；`/auth/apple/link` `apple_link` |
| S-02 | 别人改 URL 里的 player id 也读不到/改不了我的数据 | J7.1 | 高（隐私） | D3 | 任意 `/api/v2/players/{player_id}/...` 路由（如 `main.py` `GET/PUT /api/v2/players/{player_id}/clubs/bag`）；`/api/v2/history/*` 带他人 token |
| S-03 | 管理员能建成员、轮换 token、删成员；普通会话碰不到管理接口 | J7.2 | 高（权限） | D2 | `server_v2/players_api.py:admin_create_player`、`admin_list_players`、`/admin/players/{id}/rotate-token`；中间件 `main.py:enforce_admin_token_before_body_validation` |
| S-04 | 搜球场/附近球场列表去重、洞数写清楚 | J4.1 | 中 | D2 | `GET /api/v2/courses/search` `main.py:course_search_endpoint`；`GET /api/v2/courses/nearby` `_course_nearby_http`；`GET /api/v2/mobile/courses/options` `mobile_course_options` |
| S-05 | 选发球台后码数用对应 tee | J4.1, J4.4 | 中 | D2 | `GET /api/v2/courses/{gid}/tees` `main.py:_course_tees_http` |
| S-06 | 开局拿到球场包/球局包，四种半场顺序每洞映射到正确物理洞 | J4.3, J5.1 | 高（记分错洞） | D3 | `GET /api/v2/mobile/courses/{gid}/package` `main.py:_mobile_course_package_http` → `server_v2/mobile.py:build_mobile_course_package_response`；`GET /api/v2/mobile/rounds/{rid}/package` `_mobile_round_package_http` |
| S-07 | 球场下载在后台续传，失败如实告诉我，能取消/重试 | J4.2 | 中 | D2 | `GET /api/v2/courses/{gid}/install/status` `main.py:course_install_status`；`POST .../install/jobs/{id}/cancel`、`/retry` |
| S-08 | 果岭前/中/后、障碍、坡度距离算对 | J4.4 | 高（建议依据错） | D3 | `GET /api/v2/geometry/hole/{gid}/{h}`；`GET /api/v2/courses/{gid}/prep` `main.py:course_prep_nine` |
| S-09 | 球童给的推荐球杆/打法有证据链，不带成功率%，没基准不出 SG/处方 | J5.11, J8.1, J8.2 | 高 | D3 | `POST /api/v2/caddie/decision`；`GET /api/v2/caddie/context`；`POST /api/v2/caddie/decisions/{id}/audit` |
| S-10 | 球包：我手填的距离优先，Garmin 距离按 p10–p90 清洗 | J2.7 | 高（建议依据错） | D3 | `GET/PUT /api/v2/players/{player_id}/clubs/bag`；`GET /api/v2/history/clubs/bag` |
| S-11 | 手机/手表上报的记录事件批量入库，重试不重、断网补传不丢 | J5.9, J6.4 | 高（数据丢失） | D3 | `POST /api/v2/mobile/rounds/{rid}/events` `main.py:mobile_round_events` → `mobile.py:append_mobile_events_response`；`GET .../events/replay`；`POST .../events/ack` |
| S-12 | 结束一场后成绩落库；不可能的记分卡（总杆 < 推+罚+1）被拒 | J5.6, J5.7 | 高（记分错误） | D3 | `POST /api/v2/mobile/rounds/{rid}/finish` `main.py:mobile_round_finish`；`POST /api/v2/players/{pid}/rounds` `main.py:ingest_player_round` |
| S-13 | 开球左/右/命中判定对，手记局同规则 | J5.8 | 中 | D2 | 经 S-12 入库后 `GET /api/v2/history/rounds/{ref}` |
| S-14 | 订正只追加、立即生效、重同步后仍在、留一条准确日志、重试幂等 | J3.1, J3.3, J3.4 | 高（记分错误） | D3 | `POST /api/v2/history/rounds/{ref}/corrections` `main.py:add_round_correction`；`GET .../correction-log` |
| S-15 | 成绩首页差点、近 20/10 场统计、范围×粒度、口径诚实（未知不算 0） | J2.1, J2.2, J2.5 | 高（统计错误） | D3 | `GET /api/v2/history/overview`；`GET /api/v2/history/stats`；`GET /api/v2/history/stats/mobile` |
| S-16 | 任何汇总点进去看到同一组真实球局；全部球局可搜可筛可按月分组 | J2.3, J2.4 | 中 | D2 | `GET /api/v2/history/drilldown/{ref}`；`GET /api/v2/history/rounds` |
| S-17 | 单场复盘、球场页、每洞落点图编号/颜色正确，缺值不填 0 | J2.6, J2.8, J2.9 | 中 | D2 | `GET /api/v2/history/rounds/{ref}`、`.../holes/{h}/shotmap`；`GET /api/v2/history/courses/{gid}/holes/{h}/shots` `main.py:hole_history_shots` |
| S-18 | AI 报告分开事实/推断/缺失；模型挂了成绩页照常 | J2.10, J2.11 | 低 | D1 | `GET/POST /api/v2/reports/...`（用假 LLM provider） |
| S-19 | Garmin 完成局自动同步，不重不漏；会话失效如实提示；同步不并发 | J1.1, J1.2 | 高（数据丢失） | D3 | `POST /api/v2/sync/garmin`、`/players/{pid}/sync/garmin`、`GET /api/v2/sync/status`、`.../sync/garmin/jobs/{id}`；后台 `server_v2/sync_jobs.py:GarminSyncJobStore`；CLI `ai_caddie/pipeline.py:main` |
| S-20 | 手记局与 Garmin 局对账合并，9 洞双卡偏移正确 | J1.3, J6.4 | 高（重复/丢局） | D3 | `GET /api/v2/mobile/rounds/{rid}/reconciliation`；`POST .../reconciliation/apply` → `mobile.py:apply_mobile_round_reconciliation_response` |
| S-21 | 挥杆候选按场上传，可重试，不重复 | J5.15 | 低 | D1 | `POST /api/v2/mobile/rounds/{rid}/swing-candidates` |
| S-22 | 分享链接只读，不能借链接读别的局，撤销后失效 | J9.5 | 中（隐私） | D2 | `server_v2/share_api.py:create_round_share`、`revoke_round_share`；`GET /api/v2/share/{token}` |
| S-23 | 我的 token、Garmin 会话、Apple 身份不出现在响应、日志、存储、模型输入里 | J7.3 | 高（泄密） | D3 | 日志：`server_v2/log_privacy.py:LogPrivacyFilter`、`protect_handler`（经真实 app 启动挂载）；上报：`POST /api/v2/mobile/client-timing`；事件存储：经 S-11 入口 |
| S-24 | 服务上线后 `/health` 的 revision 就是刚发的 SHA；readiness 允许 warming | G1, G7 | 高（上线阻断） | D2 | `GET /api/v2/health` `main.py:health`；`GET /api/v2/readiness` `main.py:readiness` |
| S-25 | 新镜像启动先迁移、可 downgrade、seed 幂等 | G2 | 高（上线阻断/数据） | D2 | `alembic upgrade head`/`downgrade -1`（子进程）；`server_v2/identity_seed.py:main` |
| S-26 | 部署：sync 镜像同 SHA，否则拒跑；失败自动回滚、旧容器持续健康；重启策略/端口只绑本机 | G3, G4, G5, G6 | 高（上线阻断） | D3 | CLI `ops/agenthub_deploy.py:main`（`deploy`/`rollback`/`up`），注入假 docker 执行器 |
| S-27 | 新旧数据共存：缺字段、未知事件版本不崩 | J8.3 | 中 | D2 | 经 S-11、S-06 入口送旧/新版本 payload |
| S-28 | 客户端中途断开记 499 不记 400；客户端耗时诊断节流回传 | J8.4, J8.5 | 低 | D1 | `main.py:request_timing_middleware`；`POST /api/v2/mobile/client-timing` |
| S-29 | 天气拿不到不编造；产品设置可读 | J5.3 | 低 | D1 | `GET /api/v2/weather/snapshot`；`GET /api/v2/settings/product` |
| S-30 | 冒烟：冷启动→Apple 登录→开局→记分→成绩→成员越权被拒→同步可触发 | G8 | 高（上线阻断） | D2 | 真进程 `uvicorn server_v2.main:app` + `ops/smoke_private_trial.sh`（large） |
| S-31 | 服务器在后台忙（建包、出图、统计预热）时，我开局要的轻请求（球包、洞图、附近、tees、开局包首洞）照样返回；我放弃等待后服务端停掉为我做的重活 | J4.2（「开局最多等 30 秒」） | 高（开不了局） | D3 | `GET /api/v2/history/clubs/bag`（`server_v2/club_bag_api.py:run_bag_read`）；`GET .../holes/{h}/garmin-raster`（`server_v2/garmin_raster.py:_dispatch_raster`）；`GET /api/v2/courses/nearby`；`GET /api/v2/mobile/rounds/{rid}/package`。测法：用 `threading.Event` 把重活线程池占满（不计时），断言轻请求完成；模拟客户端断开后断言重活作业状态为 cancelled |

### 2.2 iOS 手机 App（I，22 个）

缩写：`APP` = `mobile/ios/AICaddie/AICaddieApp.swift`（`LiveRoundAppModel`，**不在 SwiftPM 目标里**，只能经 Xcode 工程测，见第 3.4 节）；`S/` = `mobile/ios/AICaddie/Services/`；`V/` = `mobile/ios/AICaddie/Views/`。

| ID | 球手视角目标 | 规格 | 风险 | 深度 | 真实入口（文件:符号） |
|---|---|---|---|---|---|
| I-01 | 用 Apple 登录，会话存钥匙串，重启还在；登出清干净 | J7.2 | 高（账号） | D3 | `APP` `LiveRoundAppModel.activateSession(_:migrateLegacyData:)`；`S/SessionStore.swift` `SessionStore.save/reload/signOut/clear`；`S/AppleAuthClient.swift` `signIn(identityToken:displayName:)` |
| I-02 | 搜球场、看附近、选发球台；不主动弹定位 | J4.1 | 中 | D2 | `APP` `searchCourses(...)`、`nearbyCourses(...)`、`loadCourseTees(globalId:)`；`V/MobileCourseSearchView.swift` |
| I-03 | 开局：下载球场包最多等 30 秒，失败如实提示，可重试/取消/撤销 | J4.2, J5.1 | 高（开不了局） | D3 | `APP` `startCourseRound(roundId:teeBox:loops:)`、`retryRoundStart()`、`cancelRoundStart()`、`undoRoundStart()`；`S/SyncClient.swift` `fetchCoursePackage` |
| I-04 | 选第一环、打完问第二环、第 10 洞后锁定；换洞落到正确物理洞 | J5.1, J4.3 | 高（记分错洞） | D3 | `APP` `setActiveHole(_:)`、`setSecondLoop`、`continueIntoSecondLoop` |
| I-05 | 首页主卡按进行中/附近/无数据切换，天气拿不到不编造 | J5.2, J5.3 | 低 | D1 | `V/RoundHomeView.swift` `RoundHomeView`（经 `APP` 状态驱动） |
| I-06 | 打球屏三距离、坡度、旗位、目标点；地图三档降级、原地升级不回退 | J5.4, J4.5 | 中 | D2 | `V/CurrentHoleView.swift` `CurrentHoleView`（数据经 `APP` 公开状态） |
| I-07 | 球童建议：在线/离线结果一致，只在可信时显示 | J5.11, J4.6 | 高（建议错） | D3 | `S/CaddieDecisionRequestBuilder.swift` `makeDecisionRequest(seed:input:)`；`S/OfflineCaddieDecisionEvaluator.swift` `makeDecision(seed:request:strategyMode:)`；`S/CaddieDecisionClient.swift` `fetchCaddieDecision(_:endpoint:)` |
| I-08 | 本洞记分预选来源正确，总杆 ≥ 推+罚+1 | J5.6 | 高（记分错误） | D3 | `APP` `handleEvent(_ LiveRoundEvent)`；`S/LiveRoundEventBuilder.swift` `makeScoreEvent(hole:strokes:)`、`makePuttEvent`、`makePenaltyEvent` |
| I-09 | 保存的落点等于当时 GPS；没定位也照样存成绩 | J5.5 | 中 | D2 | `S/LiveRoundEventBuilder.swift` `makeLocationEvent`；`APP` `handleEvent` |
| I-10 | 每条记录先落本地；断网排队，回网补传，不重不丢 | J5.9, J6.3, J6.4 | 高（数据丢失） | D3 | `S/OfflineStore.swift` `appendEvent(_:)`、`loadPendingEvents(roundId:)`、`applyReplayEvents`；`APP` `syncPendingEvents()`、`syncOnForeground()`；`SyncClient.postEventBatchWithRetry(_:roundId:idempotencyKey:attempts:)` |
| I-11 | 结束球局；没网时先封存，回网自动补完 | J5.9, J6.4 | 高（数据丢失） | D3 | `APP` `finishActiveRound()`、`discardActiveRound()`；`OfflineStore.sealRoundForDeferredFinish`、`resumeDeferredRoundFinish`、`loadPendingRoundFinishes` |
| I-12 | 计分卡与本场汇总按已记洞求 Par | J5.10 | 中（显示错） | D2 | `V/LiveRoundScorecardView.swift` `LiveRoundScorecardView`（经 `APP` 状态） |
| I-13 | 球包：编辑距离后排队同步，离线可改，重装后能从服务端恢复 | J2.7 | 中 | D2 | `S/ClubBagSyncCoordinator.swift` `enqueue(_:)`、`flush()`、`retryNow()`、`restoreFromServer()` |
| I-14 | 成绩/统计/复盘页数字与服务端一致；模型失败照常显示 | J2.1–J2.9, J2.11 | 中 | D2 | `SyncClient.fetchMobileStats`、`fetchHistoryRounds`、`fetchRoundDetail`、`fetchRoundShotMap`；`V/ResultsView.swift`、`V/StatsView.swift`、`V/RoundReviewView.swift` |
| I-15 | 订正：同屏加杆/调序/删除后编号连续，提交后立即生效 | J3.2, J3.1 | 高（记分错误） | D3 | `SyncClient.postRoundCorrection`；`V/RoundReviewView.swift` |
| I-16 | Garmin 同步可手动/自动触发，状态如实（进行中/需重新认证/失败） | J1.2, J9.3 | 中 | D2 | `APP` `syncGarminData()`、`syncGarminDataOutcome()`、`autoSyncGarminIfNeeded()`；`S/GarminSessionClient.swift` `importSession` |
| I-17 | 手机把配置/会话/本洞数据推给手表；断连时手表不显示过期建议 | J6.2 | 高（建议错/数据） | D3 | `S/WatchEventBridge.swift` `sendStateToWatch(_:)`、`sendConfigToWatch`、`sendRoundSeedToWatch`、`pushPendingApplicationContext` |
| I-18 | 手表上的记分/开局/结束到手机后正确入本地并上传 | J6.1, J6.4 | 高（数据丢失） | D3 | `S/WatchEventBridge.swift` `handleWatchInputMessage(_:replyHandler:)`、`mapWatchInputEvent(_:)`；`APP` `handleWatchRoundStart(_:)`、`handleWatchRoundClosure(_:)` |
| I-19 | 上传的事件、回给手表的摘要和日志里不含会话 token、Apple 身份、Garmin 会话 | J7.3 | 高（泄密） | D2 | 经 `OfflineStore.appendEvent` → `SyncClient.postEventBatch`（假 `URLProtocol` 截取请求体）；`WatchEventBridge.handleWatchInputMessage`（回复摘要脱敏） |
| I-20 | 冷启动恢复进行中的球局，旧版本数据不崩 | J8.3 | 高（数据丢失） | D3 | `APP` `LiveRoundAppModel.bootstrap()` |
| I-21 | 客户端耗时诊断节流回传，不扰业务 | J8.4 | 低 | D1 | `SyncClient` client-timing 上报（经 `APP` 公开动作触发） |
| I-22 | TestFlight 能出包：Release 构建成功、版本号递增、后端 revision 门通过 | G7 | 高（出包阻断） | D2 | `.github/workflows/ios-testflight.yml` job `testflight` → `bundle exec fastlane ios beta`（`fastlane/`） |

### 2.3 手表 App（W，14 个）

缩写：`M` = `mobile/ios/AICaddieWatch/Models/WatchRoundModel.swift`（`WatchRoundModel`）；`WS/` = `mobile/ios/AICaddieWatch/Services/`。

| ID | 球手视角目标 | 规格 | 风险 | 深度 | 真实入口（文件:符号） |
|---|---|---|---|---|---|
| W-01 | 手表收到手机推来的配置/会话/球局种子后可用 | J6.2 | 高 | D3 | `WS/WatchSyncClient.swift` `applyApplicationContext(_:)`；`session(_:didReceiveApplicationContext:)` |
| W-02 | 手表单独开局、杀进程后恢复；四种顺序不串局 | J6.1 | 高（串局/丢局） | D3 | `M` `seedRound(...)`、`resumeRound()`、`startPracticeRound(...)`；`WS/WatchCourseLibrary.swift` `startCourse(...)` |
| W-03 | 选洞、前后翻、转场选第二环 | J5.1, J4.3 | 高（记分错洞） | D3 | `M` `selectHole(_:)`、`goToNextHole()`、`goToPreviousHole()`、`openTurn`、`chooseTurnSecond`、`confirmTurn()` |
| W-04 | 本洞三页与手机同数，只画可信建议 | J5.12, J4.5 | 中 | D2 | `M` `currentCaddieOptions(progressM:)`、`rootCaddieLayerAvailable(at:)` |
| W-05 | 滚轮记分/推杆/罚杆，自动保存，换洞判定 | J5.13, J5.6 | 高（记分错误） | D3 | `M` `setDraftScore`、`setDraftPutts`、`setDraftPenalty`、`adjustDraft*`、`saveActiveHole()`、`acceptRecommendedScore` |
| W-06 | 手动记一杆、选杆、撤销 | J5.13 | 中 | D2 | `M` `beginManualShot(...)`、`completePendingManualShot(clubName:)`、`undoPendingManualShot` |
| W-07 | 看计分卡 | J5.10 | 低 | D1 | `M` `openScorecard()`；`WS/WatchRoundStore.swift` `holeState(hole:)` |
| W-08 | 记录离线排队，经手机或直连服务端送达，收到 ack 才删 | J6.1, J6.3 | 高（数据丢失） | D3 | `WatchSyncClient.queueInputEvent(_:)`、`flushQueue()`、`markEventsAcknowledged(_:)`；`WatchRoundStore.pendingEvents`、`markPosted` |
| W-09 | 结束/放弃球局；没网先延迟，回网重试 | J6.1, J6.4 | 高（数据丢失） | D3 | `M` `confirmFinish()`、`confirmAbandon`、`retryDeferredFinishes()`；`WatchRoundStore.deferFinish`、`loadDeferredFinishes` |
| W-10 | 断连/过期时不显示旧建议 | J6.2 | 高（建议错） | D2 | `WatchSyncClient.session(_:didReceiveMessage:)` / `didReceiveUserInfo`（内部 `receiveStatePayload`） |
| W-11 | 自动记杆实验开关只采候选、不改成绩 | J5.14 | 中 | D2 | `M` `setAutoShotEnabled(_:)`、`acceptAutoShotCandidate`、`rejectAutoShotCandidate` |
| W-12 | 冷启动快、按策略拿定位，有进行中球局直接回到该洞 | J6.1 | 中 | D2 | `mobile/ios/AICaddieWatch/AICaddieWatchApp.swift` `AICaddieWatchApp`、`WatchLocationLaunchPolicy` |
| W-13 | 洞图/球场包离线可用，原地升级不回退 | J4.5 | 中 | D2 | `WatchSyncClient` `session(_:didReceive file:)` → `receiveHoleImage(fileURL:metadata:)`；`WatchCourseLibrary.refresh(config:)` |
| W-14 | 手表日志不打出 token/会话 | J7.3（缺手表条款） | 中 | D1 | `WS/WatchLog.swift` `WatchLog`（经 `WatchBackendClient` 失败路径观察日志输出） |

### 2.4 汇总

| 层 | 目标数 | 高 | 中 | 低 |
|---|---|---|---|---|
| 服务端 S | 31 | 19 | 8 | 4 |
| iOS I | 22 | 13 | 7 | 2 |
| 手表 W | 14 | 7 | 6 | 1 |
| 合计 | 67 | 39 | 21 | 7 |

规格缺口（建议补进产品规格，不在本卡改规格）：手表日志隐私（W-14）；TF 出包本身（I-22 只有 G7 的 revision 门，缺「Release 构建成功」的条款）。

---

## 3. 测试尺寸与分层

### 3.1 尺寸定义（Google test sizes）

| 尺寸 | 允许 | 禁止 | 单条上限 | Python 例子 | Swift 例子 |
|---|---|---|---|---|---|
| **small** | 纯内存计算；注入的假时钟、假网络、内存存储；单进程单线程 | 网络（含 localhost）、磁盘（含临时目录）、子进程、`sleep`、真实时钟、环境变量依赖 | 100 ms（超 1 s 列进超预算清单） | 记分不变式、对账合并、码数计算、状态机迁移、契约 fixture 校验 | AICaddieDomain 纯逻辑；`OfflineCaddieDecisionEvaluator`；`WatchRoundModel` 用内存 store |
| **medium** | 本机：in-process `TestClient`、临时目录 SQLite、`$TMPDIR` 下文件、本机子进程（alembic、CLI `main(argv)`）、多线程 | 外网、其它机器、真实 Garmin/Apple/LLM、真实时钟判定 | 5 s（超 30 s 列进超预算清单） | 走 HTTP 路由的 S-xx 主测试；`agenthub_deploy.main` 配假 docker | iOS/watchOS 模拟器上的 XCTest，用假 `URLProtocol`、假 `WCSession` |
| **large** | 跨进程真端口、Docker、跨机、真机/模拟器 UI、TestFlight 构建 | 真实玩家账号；生产写操作 | 5 min | `uvicorn` 真进程 + `ops/smoke_private_trial.sh`；镜像构建冒烟 | XCUITest（`AICaddieUITests`、`AICaddieWatchUITests`）；`fastlane ios beta` 只构建不上传 |

### 3.2 分层与时间预算（写死）

预算是健康检查，不是门禁，量的是**测试步骤本身**（不含 `uv sync`、checkout、xcodegen、冷编译）：

- **CPU 时间计成本**：预算数字回答「这层测试要花多少算力」。机器忙时墙钟会被拉长（C392、C394 在负载约 20 时 1 s 的 small 测试跑了 2.5–3.4 s，断言全过），这不是测试变贵了。
- **墙钟只防挂死**：卡死由各入口的总超时拦（宿主 CD、CI job 的 timeout），超时照旧失败。
- **数字来源**：在固定环境（下表「预算」列括号里的机器、单进程、空闲）测基线，再留约 30% 余量，即预算 ≈ 基线 × 1.3；基线变了按同一办法重定，不为某次慢跑临时调大。
- **超了怎么办**：单条超过 3.1 的上限、或某层合计超过下表预算，运行器把测试名和耗时列进汇总，退出码不变；有人看到就开卡查原因（测试是否该换层、拆分或修慢代码）。断言失败和 small 层守卫拦下的违规（网络、磁盘、子进程、`sleep`、真实时钟）仍然让运行失败。

下表「门禁」列指这层测试必须通过，不含耗时。

| 层 | 内容 | 预算 | 在哪跑 | 门禁 |
|---|---|---|---|---|
| **快层-服务端** | Python small + medium | small ≤ 45 s；medium ≤ 135 s；**合计 ≤ 180 s**（GitHub `ubuntu-latest` 2 核，单进程） | PR CI `ci.yml` backend；push main；宿主 CD 部署前 | 必过 |
| **快层-原生** | Swift small（`swift test`，macOS 无模拟器）+ 改动相关的 Swift medium | small ≤ 60 s；相关 medium ≤ 5 min（不含冷编译） | PR CI `native-mobile.yml` `native-quick`（自托管 `caddie-mba`），仅 `mobile/**`、`Package.swift`、契约路径改动时 | 必过 |
| **慢层-服务端** | Python large（真端口冒烟、迁移往返、镜像冒烟） | ≤ 6 min | 合并前（PR 加 label `slow` 或 merge queue）+ 每日 1 次 | 合并前必过；每日红开卡 |
| **慢层-原生** | 全部 Swift medium + XCUITest（手机 + 手表）+ TF Release 构建（不上传） | medium ≤ 8 min；UI ≤ 20 min；TF 构建 ≤ 25 min | 合并前（改了 `mobile/**`）+ 每日 1 次，Mac 自托管 | 同上 |
| **变异层** | cosmic-ray（Python）/ Muter（Swift）+ 注回 bug 语料 | Python ≤ 60 min；Swift ≤ 90 min | 每周 1 次（周日夜）+ 手动 | 不挡合并；分数跌破阈值开卡 |

与 C248 定的三档（快速反馈服务端 ≤10、iOS ≤15、合并前全量 ≤30 分钟）的关系：本计划把服务端快层收紧到 3 分钟，其它档维持或收紧，不放宽。

### 3.3 Python 怎么标记尺寸：推荐「目录」

新布局：

```
tests/
  __init__.py
  _bootstrap/            # 保留：最先导入 tests.offline（离线守卫）
  offline.py             # 保留：外网/Garmin/Playwright 守卫
  check_isolation.py     # 保留：日志隔离 + 新增预算统计（见下）
  support/               # 假时钟、假网络、临时根目录、工厂函数（不是测试）
  small/   _bootstrap/ __init__.py test_*.py
  medium/  _bootstrap/ __init__.py test_*.py
  large/   _bootstrap/ __init__.py test_*.py   # __init__.py 里 load_tests 默认返回空套件
  durations.json         # 各测试文件历史耗时（分片用）
```

两种做法比较：

| | 目录（推荐） | unittest 装饰器 `@size("small")` |
|---|---|---|
| 宿主 CD 现命令 `python -m tests.check_isolation discover -s tests -t .` | **原样可用**：跑到 small + medium；large 的 `tests/large/__init__.py` 定义 `load_tests`，未设 `AI_CADDIE_TEST_LAYER=slow` 时返回空套件，所以不会被带进快层 | 也可用，但 large 仍会被 import（导入 uvicorn/docker 依赖），靠 skip，跑完报大量 skipped |
| 按改动路径挑 | 路径即尺寸，`git diff` 后直接选目录 | 要先 import 才知道尺寸 |
| 预算统计 | 按目录汇总耗时，简单 | 要读装饰器元数据 |
| 封闭性检查 | small 目录统一装「禁磁盘/禁网络/禁 sleep」守卫，medium 目录不装 | 每个装饰器各自装，易漏 |
| 现有 `_bootstrap` 机制 | 每个新目录加 `_bootstrap/`，与 `tests/README.md` 现规则一致 | 无变化 |

结论：**用目录**。另加一个可选薄入口 `python -m tests.run --layer fast|slow|all [--changed BASE] [--shard i/n]`（实现于 `tests/run.py`，内部仍调 `check_isolation`），给 CI 和人用；宿主 CD 即使不改命令也只跑快层（见第 12 节方案 A）。

预算强制：在 `tests/check_isolation.py` 的结果对象上记每条测试耗时（`startTest/stopTest`，用 `time.monotonic` —— 这是**运行器**量时间，测试本身不得读真实时钟），结束时：
- 单条超过所在尺寸上限 → 列进汇总的「Tests over their limit」清单（测试名、耗时、上限），不记失败；
- small 目录合计 > 45 s、medium 合计 > 135 s → 该层在「Layer budget report」里标 `OVER BUDGET`，退出码不变（3.2）；
- 运行器量的是墙钟（`time.monotonic`），机器忙时会偏大，所以只作提示；
- 把每个文件耗时写到 `$TMPDIR/test-durations.json`，供 `tools/tests/update_durations.py` 刷新 `tests/durations.json`。

### 3.4 Swift 怎么分尺寸

现状：`Package.swift` 有 3 个测试目标；只有 `AICaddieDomainTests` 是纯逻辑；`AICaddie`、`AICaddieWatch` 无条件 `import WatchConnectivity`，macOS `swift test` 编不过；`LiveRoundAppModel`（9049 行）在 `AICaddieApp.swift`，被 SwiftPM 排除，相关 250 条测试包在 `#if !SWIFT_PACKAGE` 里只能 Xcode 跑。全仓无 Swift Testing（`@Test`），全是 XCTest。

| 尺寸 | 目标 | 跑法 | 要做的结构调整 |
|---|---|---|---|
| small | `AICaddieDomainTests` + 新 `AICaddieCoreTests`（手机/手表共享的纯逻辑：记分不变式、离线队列状态机、环/洞映射、建议可信判定、payload 编解码） | macOS `swift test --filter` ，无模拟器 | 把纯逻辑从 `AICaddie`/`AICaddieWatch` 抽到无 UIKit/WatchConnectivity 依赖的 `AICaddieCore` 目标（单独子卡，见第 12 节 K8）；WatchConnectivity 用协议 `WatchSessioning` 包住 |
| medium | `AICaddieTests`、`AICaddieWatchTests`（ViewModel 级，假 `URLProtocol`、假 `WatchSessioning`、内存/临时目录 `OfflineStore`） | `xcodebuild test -scheme AICaddie`/`AICaddieWatch` 模拟器 | `LiveRoundAppModel` 测试保持只在 Xcode 工程跑；文件开头注明尺寸 |
| large | `AICaddieUITests`、`AICaddieWatchUITests`（XCUITest，fixture 后端）、TF Release 构建、真机冒烟 | 慢层，Mac 自托管 | 每个 UI 测试只对应一个高风险目标的端到端路径，控制在 ≤ 12 条 |

Swift 标记：文件顶部 `// size: small|medium|large` + `// goals: I-10, W-08`（追溯扫描也读 Swift 文件，见第 9 节）。

---

## 4. 用例设计方法

每个 D2/D3 目标的测试用参数表写用例（Python `subTest`，Swift 循环 + `XCTContext.runActivity`），表头即等价类/边界。下面是各类目标的设计样例，子卡照此为每个目标写全。

### 4.1 等价类

| 目标 | 输入维度 | 有效等价类 | 无效等价类 |
|---|---|---|---|
| S-01 登录 | Apple identity token | 有效新用户；有效老用户；带 displayName/不带 | 过期；签名错；aud 不符；空串 |
| S-02 越权 | 请求者 × 资源所有者 | 本人；管理员 | 他人 token；无 token；已登出 token；分享 token 做写操作 |
| S-11 事件 | 事件批 | 新事件；重放同 idempotencyKey；乱序到达 | 未知 kind（应保留不崩，J8.3）；超大 body；他人 roundId |
| S-15 统计 | 球局集合 | 18 洞全记；9 洞；含 Garmin+手记合并局 | 推杆未知（不算 0）；GIR 无法判定；0 场 |
| I-07/W-04 建议 | 数据可信度 | 几何+球包齐全；仅几何；离线 | 无 GPS；球包空；包过期 |
| S-26 部署 | sync 镜像 | 同 SHA 存在 | 不存在；SHA 不同；docker 调用失败 |

### 4.2 边界值

| 目标 | 边界 | 取值 |
|---|---|---|
| S-12/I-08/W-05 记分 | 总杆 vs 推杆+罚杆+1 | 总杆 = 推+罚+1（合法下界）；= 推+罚（非法）；推=0、罚=0、总杆=1（一杆进洞）；总杆上限（规格未定→按 `ai_caddie/rounds/score_invariant.py` 现行上限 ±1） |
| S-08 码数 | 到果岭距离 | 0 m、1 m、站在果岭上、超出地图边界、tee 缺坐标 |
| S-10 球包 | p10–p90 清洗 | 样本数 0/1/9/10/11；全相同值；含极端离群 |
| I-03 开局 | 下载等待 | 29.9 s 成功；30 s 超时；立即失败（注入假时钟，不真等） |
| I-04/W-03 环锁定 | 当前洞 | 第 9 洞（可改第二环）；第 10 洞（锁定）；9 洞场无第二环 |
| S-15 近 N 场 | 场数 | 0、1、9、10、11、19、20、21 |
| S-20 对账 | 时间窗口 | 同日不同时段；跨午夜；9 洞双卡偏移 0/9 |
| S-17 落点图 | 洞号 | 1、9、10、18、19（越界）|

### 4.3 状态迁移

**开局状态机（I-03/I-04/W-02/W-03）**，测试覆盖每条合法边各一次、每个状态下至少一个非法事件被拒：

```
idle --start--> preparing --package ok--> active(loop1) --hole 9 saved--> askSecondLoop
preparing --timeout/fail--> startFailed --retry--> preparing
startFailed --cancel--> idle      active --undoStart(无记录时)--> idle
askSecondLoop --choose--> active(loop2) --hole≥10--> locked
active/locked --finish--> finishing --server ok--> finished
finishing --offline--> sealed(deferred) --network back--> finishing
active --discard--> idle
非法：idle 下 saveHole；locked 下 setSecondLoop；finished 下 handleEvent
```

**离线队列（I-10/W-08/S-11）**：

```
pending --post--> inFlight --2xx ack--> acked(删除)
inFlight --网络错/5xx--> pending(重试计数+1，退避用假时钟)
inFlight --422--> quarantined（不重试，J5.9：不丢——保留可见）
pending --杀进程--> pending（重启后仍在）
acked 的事件再次被服务端 replay --> 去重，不重复入库
```

必测：同一事件两次 post（幂等）；ack 丢失后重放；重试次数上限边界（2/3/4 次）；进程在 inFlight 时被杀。

**Garmin 同步作业（S-19）**：`queued → running → succeeded|failed|needsReauth|cancelled`；`running` 时再触发 → 返回同一 job（不并发）；`failed --retry--> queued`。

**部署（S-26）**：`build → preflight(sync 镜像同 SHA?) → swap → health(revision==SHA?) → done`；任一步失败 → `rollback → 旧容器健康`。

---

## 5. 封闭性规则

| 规则 | 做法 | 违反时 |
|---|---|---|
| 不读真实时钟 | 生产代码的「现在」经注入：Python 用 `tests/support/clock.py:FakeClock` patch 生产侧已有的时间获取点（无注入点的，子卡先给生产代码加 `now: Callable` 参数，默认 `datetime.now`）；Swift 用 `Clock`/`DateProvider` 协议注入 | small 守卫 patch `time.time`/`datetime.now` 为抛错（仅在 small 目录） |
| 不 `sleep` | 重试退避、轮询都经注入的 `sleep` 函数，测试里换成推进假时钟；Swift 用 `Task.sleep` 包装器 | small 守卫 patch `time.sleep` 抛错；`grep -n "time.sleep(" tests/` 由追溯校验测试报错 |
| 不碰外网 | 保留 `tests/offline.py`（拦 Garmin、Playwright）；扩展为拦所有非 127.0.0.1 socket 连接；LLM/Apple/Garmin 一律假 provider | 守卫抛 `NetworkBlocked` |
| 不碰共享磁盘 | medium 只用 `tempfile.TemporaryDirectory()` 创建独立临时目录（标准库优先使用 `TMPDIR`，未设置时使用系统临时目录）；保留现有「默认路径全部指向每进程 `.test-cache-*`」机制；small 禁止 `open()` 写 | small 守卫 patch `builtins.open` 写模式抛错 |
| 不依赖机器忙闲 | 不写「X 秒内完成」的断言（性能预算只由运行器统计，不在单条测试断言）；并发测试用 `threading.Barrier`/事件同步，不用时间窗口 | 复审拒绝 |
| 不依赖顺序 | 每条测试自建数据；`unittest` 默认按名字排序，CI 每周一次用 `--shuffle`（`tests/run.py` 实现随机种子并打印） | 种子可复现 |
| 不读环境变量默认 | 需要的配置在测试内用 `mock.patch.dict(os.environ, ..., clear=False)` 局部设置 | — |

**不稳测试处理流程（不重跑碰运气）**：

1. 发现：任一层出现「同一提交上一次红一次绿」即判为不稳（CI 不配置自动 retry；`gh run rerun` 只允许用于基础设施故障，且需在 PR 评论写原因）。
2. 隔离：当天把该测试移到 `tests/quarantine/`（不在任何门禁里，`load_tests` 返回空），同时开 C 卡，卡名「不稳：<目标 ID> <测试名>」，**隔离期间该目标在追溯矩阵里标红**（目标失去覆盖是可见的）。
3. 修：找根因（时钟、顺序、共享状态、线程竞态），修测试或修产品代码；禁止加 `sleep`、加大超时、加重试来「修」。
4. 回归：修好后用 `python -m tests.run --repeat 50 <测试>` 在本机连跑 50 次全绿，才移回原目录；隔离区存量 >3 条时停新功能卡先修。

---

## 6. 契约测试

### 6.1 现有契约文件

| 契约 | 文件 | 双方 |
|---|---|---|
| 手机→服务端 事件 | `mobile/contracts/live_round_event.schema.json` | iOS `OfflineStore`/`SyncClient` ↔ `POST /mobile/rounds/{rid}/events` |
| 服务端→手机 球局/球场包 | `mobile/contracts/live_round_package.schema.json` | `GET /mobile/*/package` ↔ iOS `SyncClient.fetchCoursePackage` |
| 手表→手机 输入事件 | `mobile/contracts/watch_input_event.schema.json` | `WatchSyncClient.queueInputEvent` ↔ `WatchEventBridge.mapWatchInputEvent` |
| 手机→手表 本洞状态 | `mobile/contracts/watch_round_state.schema.json` | `WatchEventBridge.sendStateToWatch` ↔ `WatchSyncClient` 接收 |
| 球局身份用例 | `mobile/contracts/fixtures/round_identity_cases.json` | Python + iOS + 手表 |
| 规范对象/事件种类/原因码 | `contracts/canonical/*.json`（`authority.json`、`event_kind_registry.json`、`reason_codes.json`、`canonical_fixture_v1.schema.json`），生成器 `tools/contracts/generate_contracts.py` → `AICaddieDomain/GeneratedContracts.swift` | Python + Swift |
| 脱敏金样 | `contracts/canonical/fixtures/mobile_event_sanitizer_golden.json` | Python `mobile_event_store.sanitize_mobile_event` + iOS `OfflineStore` |
| 跨语言产品向量 | `contracts/fixtures/shared/`（`caddie_golden.json`、`loop_map.json`、`tee_result.json`、`c120_avoid_zones.json`），被 `mobile/ios/project.yml` 和 Swift `ProductSharedVectors.swift` 引用 | Python + Swift |

**注意**：跨语言产品向量已由 K7 从 `tests/product/fixtures/shared/` 搬到 `contracts/fixtures/shared/`（`project.yml`、`native-mobile.yml` 路径过滤同步改好），删旧测试时不再牵动原生构建。手机包/事件 fixture 的源文件在 `mobile/contracts/fixtures/`，`AICaddie/Fixtures/*.fixture.json` 是它们的字节副本。

### 6.2 做法：同一份 fixture，两端各测一次

| 契约 | 生产方测试（small） | 消费方测试 | 文件计划 |
|---|---|---|---|
| 事件（手机→服务端） | Swift small：`LiveRoundEventBuilder` 产出的每种事件编码后通过 schema 校验（Swift 侧用 fixture 对比：编码结果与 `mobile/contracts/fixtures/events/*.json` 规范化后相等） | Python medium：把同一批 fixture POST 到 `/mobile/rounds/{rid}/events` 全部 2xx 且 replay 等值 | `tests/medium/test_contract_mobile_events.py`；`AICaddieCoreTests/ContractEventsTests.swift` |
| 球局包（服务端→手机） | Python medium：真实路由响应用 `jsonschema` 校验 `live_round_package.schema.json`，并把响应写成金样（金样变更需在 PR 里显式更新） | Swift small：解码金样，断言关键字段（洞映射、环、tee） | `tests/medium/test_contract_round_package.py`；`ContractPackageTests.swift` |
| 手表↔手机 | 手机 small：`WatchRoundStatePayload` 编码 = `mobile/contracts/fixtures/watch/state_*.json`；手表 small：`WatchInputEvent` 编码 = `fixtures/watch/input_*.json` | 手表 small：解码 `state_*.json`；手机 small：`mapWatchInputEvent` 解码 `input_*.json` | 新增 `mobile/contracts/fixtures/watch/`；两端 `ContractWatchTests.swift` |
| fixture 本身合法 | Python small：所有 `mobile/contracts/fixtures/**` 通过对应 schema；所有 Swift 资源副本（`AICaddie/Fixtures/*.fixture.json`）与源文件字节相同 | — | `tests/small/test_contract_fixtures.py` |
| canonical 生成物 | Python small：`generate_contracts.py --check`（生成结果与仓库内 `GeneratedContracts.swift` 一致） | Swift small：`GeneratedContractsSmokeTests` 保留为契约测试 | `tests/small/test_contract_codegen.py` |

契约测试只比较**数据**（fixture 与 schema），不读对方源码；CI 的 `tools/contracts/check_authority.py` 步骤保留。

---

## 7. 变异测试

### 7.1 工具选型

`pyproject.toml` / `uv.lock` 里**没有** mutmut、cosmic-ray、pytest、hypothesis、coverage；测试运行器是标准库 `unittest`（284/301 个文件 import unittest，0 个 import pytest）。

| 候选 | 与 unittest 兼容 | 结论 |
|---|---|---|
| mutmut 3.x | 只支持 pytest 作为运行器 | 不选（要引入 pytest） |
| mutmut 2.x | `--runner "<任意命令>"` 可用 | 备选（已停止维护） |
| **cosmic-ray** | `test-command` 任意命令；会话存 SQLite，可断点续跑、可分布式 | **推荐** |

需要加的依赖（**需装进共享 venv `<caddie-data>/venvs/garmin-ai-caddie-ci`，由宿主做**；本卡不 pip install）：

```toml
# pyproject.toml
[dependency-groups]
mutation = ["cosmic-ray"]   # 版本由 uv lock 定，K12 核对其 unittest test-command 用法
```

`uv lock` 后由宿主 `uv sync --group mutation` 装进共享 venv；Docker 镜像不装该组。

### 7.2 跑哪些模块、阈值、频率

只变异 D3 目标背后的核心模块（不追求全仓）：

| 模块 | 目标 | 阈值（存活率 ≤） |
|---|---|---|
| `ai_caddie/rounds/score_invariant.py`、`round_corrections.py`、`round_ingest.py` | S-12、S-14 | 20% |
| `ai_caddie/caddie/mobile_event_store.py`、`mobile_reconciliation.py`、`round_loops.py`、`mobile_round_identity.py` | S-11、S-20、S-06 | 25% |
| `ai_caddie/history/history_stats.py`、`mobile_stats.py`、`corrected_history.py` | S-15 | 25% |
| `ai_caddie/caddie/decision.py`、`club_bag.py` | S-09、S-10 | 35% |
| `server_v2/auth_api.py`、`players_api.py`、`session.py`、`share_api.py` | S-01–S-03、S-22 | 20% |
| `server_v2/log_privacy.py` | S-23 | 15% |
| `server_v2/sync_jobs.py` | S-19 | 30% |
| `ops/agenthub_deploy.py`（只 `deploy`/`rollback` 相关函数） | S-26 | 35% |

- 测试命令：`python -m tests.run --layer fast --goals <该模块对应目标>`（只跑相关测试，单个变异体 ≤ 20 s）。
- 频率：每周日夜 1 次全量（≤ 60 min，cosmic-ray 4 worker）；PR 改了上表模块时，慢层里对**改动行**做增量变异（`cosmic-ray` 过滤到 diff 行，≤ 10 min）。
- 阈值第一次跑出基线后锁定，只许变好（ratchet）；跌破阈值不挡合并，自动开 C 卡。
- 存活变异体处理：要么补该目标的等价类/边界用例，要么标「等价变异」写进 `tests/mutation/equivalent.toml` 并说明。

### 7.3 注回 bug 语料（复用现有 faults 机制）

`tests/product/faults/` 现有 177 个卡目录 + `run_faults.py`（在一次性 worktree 里打补丁跑目标测试）。新做法：

- 保留 `run_faults.py` 的「一次性 worktree 打补丁」机制，搬到 `tools/faults/run_faults.py`；
- 新 `tools/faults/manifest.json` 的 `target` 从「旧测试名」改为**目标 ID**（`"goals": ["S-11"]`），运行时由追溯矩阵展开成测试；
- 第 10 节的 ≥20 个真实 bug 各写一个补丁进语料；旧的 177 个卡目录随旧测试删掉（它们的 `target` 全指向旧测试名，删后悬空）。

### 7.4 Swift 侧

- 工具：Muter（macOS，基于 xcodebuild）只跑 `AICaddieDomain` + 新 `AICaddieCore`（small 层，快），每周 1 次在 Mac 自托管上，≤ 90 min；阈值同上思路（核心逻辑存活率 ≤ 30%）。
- ViewModel 层（`LiveRoundAppModel`、`WatchRoundModel`）不跑全量变异，改用第 10 节的 Swift 注回补丁（`kind: swift`），由现有 `.github/workflows/agenthub-native-mutant.yml` 的机制执行，仅合并前对改动涉及的补丁跑（C248 已定：原生 mutant 不每轮跑）。

---

## 8. 选择与分片

### 8.1 按改动路径挑测试（参考 MovieClaw `ci.yml` 的 `changes` job + `dorny/paths-filter`）

两级：

1. **job 级**（GitHub Actions）：`backend`（`server_v2/** ai_caddie/** ops/** migrations/** contracts/** mobile/contracts/** tests/** pyproject.toml uv.lock`）、`native`（`mobile/** Package.swift contracts/**`）、`frontend`（`web_v2/**`）。未命中的 job 记 skipped。
2. **目标级**：`tests/selection.toml` 维护「代码路径 glob → 目标 ID」映射（与第 2 节「真实入口」列一致），再由测试 docstring 的目标 ID 反查测试：

```toml
[[map]]
paths = ["ai_caddie/caddie/mobile_event_store.py", "server_v2/mobile.py"]
goals = ["S-11", "S-20", "S-27"]
[[map]]
paths = ["mobile/contracts/**", "contracts/**"]
goals = ["*contract*"]   # 所有契约测试
```

- 目标级挑选**只用于开发期反馈**（codex 克隆里自检、PR 上的「早报」）；**PR 最终门禁、push main、宿主 CD 都跑完整快层**——快层只有 3 分钟，没必要冒漏跑的险。
- 这替代 `par1025/related-tests.sh`（它按「测试文件里出现了被改文件的文件名」挑测试，本质是钉源码原文，与 R-DEV-3 冲突）。
- 未映射到任何目标的生产文件 → `python -m tests.run --changed` 打印警告并退回跑完整快层。

### 8.2 按历史耗时分片（参考 MovieClaw `tests/conftest.py:pytest_collection_modifyitems` + `scripts/update-shard-durations.py`）

- 快层预算 3 分钟，**默认不分片**；当 medium 合计 > 100 s 时启用 2 片。
- 分片单位 = 测试文件；权重 = `tests/durations.json`（文件 → 秒）；算法 = 最长优先贪心装箱（LPT）；未知文件按中位数计。
- `python -m tests.run --layer fast --shard 1/2` 在 CI matrix 里用；宿主 CD 单机时用 `--jobs 2`（两个子进程各跑一片，结果合并）。
- 刷新：每日慢层任务结束后由 `tools/tests/update_durations.py` 生成新 `durations.json` 并开 PR（记录过时只影响均衡，不会漏跑）。

### 8.3 慢测试打标记出门禁

- 「慢」= 在 `tests/large/`（或 Swift `// size: large`）。快层运行器**拒绝**运行 large（`load_tests` 空套件）。
- medium 单条连续 3 次超过 2 s（看 `durations.json`），每日任务自动开卡：要么拆小/改 small，要么挪到 large（需在 PR 说明理由）。
- large 只在：PR 打 `slow` label、合并前（GitHub merge queue 或 Jason 合并时手动触发 `workflow_dispatch`）、每日 cron 跑。

---

## 9. 需求→测试追溯矩阵

### 9.1 约定

- Python：每条测试方法 docstring 首行 `"""S-11 S-27: 重放同一批事件不重复入库"""`；类 docstring 写的 ID 对类内全部方法生效。
- Swift：方法前一行注释 `// goals: I-10 W-08`。
- 一条测试可列多个 ID；主测试额外标 `[main]`，如 `"""S-11 [main]: ..."""`。

### 9.2 校验脚本

规则本身由 small 测试 `tests/small/test_traceability.py` 用内存里的计划和测试片段自测；对真实仓库跑一遍要读计划和全部分层测试文件（读磁盘，按 3.1 不属 small），放在 medium 测试 `tests/medium/test_traceability_repository.py`（目标 ID 均为 `META`）：

1. 解析本文第 2 节三张表，得到目标集合 G 与每个目标的深度；
2. 用 `ast` 扫 `tests/small|medium|large/**/*.py` 的 docstring、用正则扫 `mobile/ios/**Tests*/**/*.swift` 的 `// goals:` 注释，得到「ID → 测试」映射 T；
3. 断言：G 中每个 ID 在 T 里 ≥1 条且恰有 1 条 `[main]`；D3 目标 ≥ 4 条；T 中不存在 G 之外的 ID（防拼写错）；`tests/quarantine/` 里的测试不计入覆盖；
4. 断言测试文件名不匹配 `test_c\d+`，测试代码不对 `server_v2/`、`ai_caddie/`、`mobile/` 下源码调 `read_text()`/`open()`（P2/P3）；
5. 失败信息列出缺覆盖的目标 ID。

（扫 Swift 文件只读**测试**文件的注释，不读产品源码，不违反 P2。）

### 9.3 矩阵模板（计划路径，子卡完成后替换为实际测试名）

| 目标 | 尺寸 | 计划测试（文件::测试名） | 深度 |
|---|---|---|---|
| S-01 | medium | `tests/medium/test_s_auth.py::AppleSignIn::test_sign_in_refresh_logout [main]` / `::test_rejects_invalid_tokens`（等价类表） | D3 |
| S-02 | medium | `tests/medium/test_s_auth.py::PlayerIsolation::test_cross_player_requests_rejected [main]` | D3 |
| S-03 | medium | `tests/medium/test_s_admin.py::Admin::test_member_lifecycle [main]` | D2 |
| S-04/S-05 | medium | `tests/medium/test_s_courses.py::CourseSearch::test_search_nearby_tees [main]` | D2 |
| S-06 | medium + small | `tests/medium/test_s_round_start.py::Packages::test_four_loop_orders_map_physical_holes [main]`；`tests/small/test_s_loops.py::LoopMap::test_boundaries` | D3 |
| S-07 | medium | `tests/medium/test_s_courses.py::Install::test_status_cancel_retry [main]` | D2 |
| S-08 | small + medium | `tests/small/test_s_geometry.py::Distances::test_boundaries`；`tests/medium/test_s_courses.py::Prep::test_hole_distances [main]` | D3 |
| S-09 | medium | `tests/medium/test_s_caddie.py::Decision::test_evidence_no_percent_no_sg_without_baseline [main]` | D3 |
| S-10 | medium + small | `tests/medium/test_s_bag.py::Bag::test_manual_overrides_garmin [main]`；`tests/small/test_s_bag_filter.py::P10P90::test_boundaries` | D3 |
| S-11 | medium + small | `tests/medium/test_s_events.py::Events::test_batch_idempotent_replay_ack [main]`；`tests/small/test_s_event_queue.py::States::test_transitions` | D3 |
| S-12/S-13 | medium + small | `tests/medium/test_s_finish.py::Finish::test_finish_persists_and_rejects_impossible [main]`；`tests/small/test_s_score_invariant.py::Bounds::test_strokes_vs_putts_penalties` | D3 |
| S-14 | medium | `tests/medium/test_s_corrections.py::Corrections::test_append_only_effective_logged_idempotent [main]` | D3 |
| S-15–S-17 | medium + small | `tests/medium/test_s_history.py::Overview::test_home_stats_drilldown_same_rounds [main]`；`tests/small/test_s_stats.py::Windows::test_recent_n_boundaries` | D3/D2 |
| S-18 | medium | `tests/medium/test_s_reports.py::Reports::test_provider_failure_keeps_results [main]` | D1 |
| S-19 | medium | `tests/medium/test_s_garmin_sync.py::Sync::test_no_dup_no_loss_reauth_single_flight [main]` | D3 |
| S-20 | medium + small | `tests/medium/test_s_reconcile.py::Reconcile::test_manual_vs_garmin_merge [main]`；`tests/small/test_s_reconcile_rules.py` | D3 |
| S-21 | medium | `tests/medium/test_s_events.py::Swing::test_candidates_retry_no_dup [main]` | D1 |
| S-22 | medium | `tests/medium/test_s_share.py::Share::test_read_only_scoped_revocable [main]` | D2 |
| S-23 | medium | `tests/medium/test_s_privacy.py::Secrets::test_no_secret_in_response_log_store [main]` | D3 |
| S-24/S-29 | medium | `tests/medium/test_s_health.py::Health::test_revision_readiness [main]` | D2 |
| S-25 | medium | `tests/medium/test_s_migrations.py::Migrations::test_upgrade_downgrade_seed_idempotent [main]` | D2 |
| S-26 | medium | `tests/medium/test_s_deploy.py::Deploy::test_sync_image_gate_rollback_restart_policy [main]` | D3 |
| S-27 | medium | `tests/medium/test_s_events.py::Compat::test_unknown_versions_survive [main]` | D2 |
| S-28 | medium | `tests/medium/test_s_health.py::Timing::test_disconnect_499 [main]` | D1 |
| S-30 | large | `tests/large/test_s_smoke.py::Smoke::test_cold_start_round_results_isolation_sync [main]` | D2 |
| S-31 | medium | `tests/medium/test_s_responsiveness.py::LightRequests::test_light_routes_return_while_heavy_pool_held [main]` / `::test_client_disconnect_cancels_heavy_work` | D3 |
| I-01 | medium | `AICaddieTests/Goals/SessionGoalTests.swift::testSignInPersistSignOut` [main] | D3 |
| I-02–I-04 | medium + small | `AICaddieTests/Goals/RoundStartGoalTests.swift::testStartRetryCancelUndo` [main]；`AICaddieCoreTests/RoundStateMachineTests.swift` | D3 |
| I-05/I-06/I-12 | medium | `AICaddieTests/Goals/PlayScreenGoalTests.swift` | D1/D2 |
| I-07 | small | `AICaddieCoreTests/CaddieDecisionGoalTests.swift::testOnlineOfflineParity` [main] | D3 |
| I-08/I-09 | small + medium | `AICaddieCoreTests/ScoreInvariantTests.swift`；`AICaddieTests/Goals/ScoringGoalTests.swift` [main] | D3 |
| I-10/I-11 | medium + small | `AICaddieTests/Goals/OfflineQueueGoalTests.swift::testQueueReplayNoDupNoLoss` [main]；`AICaddieCoreTests/QueueStateMachineTests.swift` | D3 |
| I-13 | medium | `AICaddieTests/Goals/ClubBagGoalTests.swift` [main] | D2 |
| I-14/I-15 | medium | `AICaddieTests/Goals/ResultsGoalTests.swift`、`CorrectionGoalTests.swift` [main] | D2/D3 |
| I-16 | medium | `AICaddieTests/Goals/GarminSyncGoalTests.swift` [main] | D2 |
| I-17/I-18 | small + medium | `AICaddieCoreTests/ContractWatchTests.swift`；`AICaddieTests/Goals/WatchBridgeGoalTests.swift` [main] | D3 |
| I-19 | medium | `AICaddieTests/Goals/PrivacyGoalTests.swift` [main] | D2 |
| I-20 | medium | `AICaddieTests/Goals/BootstrapGoalTests.swift` [main] | D3 |
| I-21 | medium | `AICaddieTests/Goals/TimingGoalTests.swift` [main] | D1 |
| I-22 | large | `ios-testflight.yml` 的「只构建」模式（`upload_to_testflight=false`）在慢层每日跑 [main] | D2 |
| W-01–W-03 | medium + small | `AICaddieWatchTests/Goals/WatchRoundGoalTests.swift` [main]；`AICaddieCoreTests/RoundStateMachineTests.swift` | D3 |
| W-04/W-10 | medium | `AICaddieWatchTests/Goals/WatchCaddieGoalTests.swift` [main] | D2 |
| W-05–W-07 | medium | `AICaddieWatchTests/Goals/WatchScoringGoalTests.swift` [main] | D3 |
| W-08/W-09 | medium + small | `AICaddieWatchTests/Goals/WatchQueueGoalTests.swift` [main]；`AICaddieCoreTests/QueueStateMachineTests.swift` | D3 |
| W-11–W-14 | medium | `AICaddieWatchTests/Goals/WatchLifecycleGoalTests.swift` [main] | D2/D1 |
| UI（large） | large | `AICaddieUITests/Goals/GoldenPathUITests.swift`（开局→记分→结束→成绩，覆盖 I-03/I-08/I-11/I-14）；`AICaddieWatchUITests/Goals/WatchGoldenPathUITests.swift`（覆盖 W-02/W-05/W-09） | — |

规模估计：Python 约 35 个测试文件、主测试 30 条 + 深度用例（`subTest`）约 300 个；Swift 约 30 个文件、约 250 条。

---

## 10. 注回 bug 清单

### 10.1 筛选依据

在 `<caddie-data>/BACKLOG.md` 中扫了约 213 张 C 卡（C1xx、C2xx、C3xx），只保留同时满足以下三条的：

1. 卡里写了真实世界证据：Jason/球手真机截图或 build 号（TF 93、build 96–102）、生产日志/耗时、真实 TestFlight run 或线上事故；
2. 有已合并的修复，能用 `git log --grep` 对到提交，修复位置的文件:符号在 `35a402af` 上 grep 得到；
3. 日期在 10-08 之后（实际命中的都在 10-23 – 11-03；BACKLOG 里 10-08 – 10-22 没有带日期的 C 卡）。

剔除约 186 张：复审跟进（约 122）、测试/CI/Mac 设施（约 35）、文档流程（约 4）、产品决定或新功能（C241、C370、C158、C166–C174 等）、只由 CI/复审/变异发现（C200、C201、C265、C375、C82、C118、C120 等）、未修或仍开（C202、C374）、生产副本上量的（C100、C146、C154）、根因卡自己写「线索非结论」的（C243）。

**手表：没有一张手表卡满足「真机/线上碰到」**（C1、C26、C41、C72 都来自 CI 截图或复审），所以本清单没有手表 bug；手表测试强度只能靠第 7 节变异测试衡量，这是已知缺口。

### 10.2 清单（27 条）

缩写：`ml.py` = `ai_caddie/caddie/mobile_live.py`；`APP` = `mobile/ios/AICaddie/AICaddieApp.swift`；`iOS/` = `mobile/ios/AICaddie/`。「预期」：**抓** = 快层或慢层测试按设计必红；**可能** = 取决于注回补丁的写法；**抓不到** = 视觉时序/纯性能，超出封闭测试能力（说明原因）。

| # | 卡 | 日期 | 根因（一句话） | 注回位置（文件:符号） | 预期由谁抓 | 预期 |
|---|---|---|---|---|---|---|
| 1 | C13 | 10-23 | 所有 release 容器都建成 `on-failure:3`，被换下旧容器退出码 143 也算失败，重启后旧版抢端口，`up` 直接沿用在跑的容器 → 线上回退旧版 | `ops/agenthub_deploy.py:up`、`find_current` | S-26（重启策略只给当前容器；`up` 选当前 SHA） | 抓 |
| 2 | C33 | 10-24 | 开局包同步等首洞 prepare（与附近/几何共用 2 个 worker），最长 22 s，客户端挂住 | `server_v2/mobile.py:build_mobile_round_package_response`；`ml.py:first_hole_lightweight_course_prep` | S-31（重活占满时开局包仍返回） | 可能 |
| 3 | C34 | 10-25 | 障碍导出失败后安装被标完成且不重试，包却一直报 pending，客户端无限轮询 | `server_v2/course_install.py:_schedule_retry`、`public_state` | S-07（安装状态迁移：失败→重试/如实失败，状态与包一致） | 抓 |
| 4 | C36 | 10-25 | 没先调 `/tees`、冷 release 直接要球场包返回 422「不能解析成 9 洞」（C33 回归） | `server_v2/mobile.py:_refresh_course_release_authority`、`build_mobile_course_package_response` | S-06（等价类：冷缓存、未调 tees 直接要包 → 200） | 抓 |
| 5 | C85 | 10-26 | 洞屏等完整个人包（4.7–24 s）而不用 0.3 s 的 map_only 包 | `APP` `LiveRoundAppModel.prepareCourseRound` | I-03（假 SyncClient 挂起个人包，map_only 到达即可进洞；用 continuation 控制，不计时） | 抓 |
| 6 | C87 | 10-26 | 附近结果不带 tees；冷缓存时 `/tees` 同步拉 Garmin release（4.4 s） | `server_v2/main.py:course_tees`、`course_nearby_endpoint` | S-04/S-05（附近结果含 tees）；耗时部分归 S-31 | 抓（功能部分） |
| 7 | C88 | 10-26 | 包内 Garmin 图 URL 没带 `?v=`，与图路由缓存键不符，预取从不命中；另 JPG 天空被烧进底色 | `ml.py:_startup_hole_assets`；`ai_caddie/geometry/garmin_raster.py:_main_component` | S-06（契约：包内图 URL 与图路由缓存键一致）；底色问题不抓 | 可能（URL 部分抓，图像部分抓不到） |
| 8 | C89 | 10-26 | 只在外层判 CourseView 是否完整，部分数据被画到精确地形图上；缓存的 topo 阻止升级 | `iOS/Views/CurrentHoleView.swift:LiveTopoAvailability` | I-06（地图三档降级等价类：部分数据 → 不画精确层；原地升级不回退） | 可能 |
| 9 | C96 | 10-27 | 结束流程没共用九洞候选，打完 9 洞结束时不问第二个九洞 | `iOS/Models/NineLoopTurn.swift:candidateLoops`；`iOS/Views/LiveRoundFinishSummaryView.swift` | I-04（状态迁移：hole 9 saved → askSecondLoop） | 抓 |
| 10 | C97 | 10-27 | 翻洞先显示黑底事实页再显示黑色加载图，显示没等图就绪 | `iOS/Models/LiveHolePagerState.swift:LiveHolePagerState` | I-06 | 抓不到（视觉时序；慢层 UI 截图对比可能抓） |
| 11 | C114 | 10-28 | 开局包请求 30 s 超时只试 1 次（服务端用了 32.8 s），失败后静默退回「开始」按钮 | `APP` `RoundStartFailure`；`iOS/Services/SyncClient.swift:fetchRoundPackage` | I-03（边界：超时→必须进入 startFailed 并可重试，不能静默回 idle） | 抓 |
| 12 | C115 | 10-28 | 相邻页选中前不解码本地 topo，每洞先闪 Garmin 底图 | `iOS/Views/CurrentHoleView.swift:LiveHolePrepUpgradePolicy` | I-06 | 抓不到（视觉时序） |
| 13 | C123 | 10-28 | 分享链接路径冷算 `history_correction_revision`（8.6 s），没复用登录路径的几何签名缓存 | `ai_caddie/history/corrected_history.py:corrected_history_data` | S-22 | 抓不到（纯性能，封闭测试不计时；列入性能冒烟另议） |
| 14 | C134 | 10-28 | 离线球场按下载记录（每个 globalId/九洞）各列一行，沙河出现 3 次 | `iOS/Models/StartRoundPresentation.swift:offlineRows`、`deduplicatedVenueRows` | I-02（去重等价类：同球场多九洞下载 → 一行） | 抓 |
| 15 | C135 | 10-28 | 注册新 round_id 时扫描整个 6 MB `events.jsonl`（28–35 s），后台重活饿死轻请求 | `ai_caddie/caddie/mobile_event_store.py:MobileEventStore.ensure_round_event_index` | S-31（饿死部分）；全量扫描本身不计时 | 可能 |
| 16 | C136 | 10-28 | `/prep` 和开局包用了不同 tee（包从历史模板局取 tee），同洞距离互相矛盾 | `ml.py:_package_holes`、`first_hole_lightweight_course_prep` | S-06 + S-08（跨入口一致性：同 tee 下 `/prep` 与包的同洞距离相等） | 抓 |
| 17 | C162 | 10-29 | `/tees` 未返回时 tee 页用离线/附近行的 tee；27 洞场候选漏掉第三个九洞 | `iOS/Views/StartRoundView.swift:resolvedTeeOptions`；`ml.py:build_mobile_course_options` | S-04（27 洞三个九洞都在候选）+ I-02 | 抓 |
| 18 | C164 | 10-29 | 狗腿洞上实时规划没用 prep 路线折线，4 条路线都不落果岭 | `ml.py:hydrate_live_caddie_geometry_context`；`iOS/Services/LiveCaddieRouteAuthority.swift` | S-09 + I-07（狗腿洞 fixture：至少一条路线落果岭；与备战三方案一致 J4.6） | 抓 |
| 19 | C189/C385 | 10-29 | 球包 GET 与无关的开局重活共用 worker，被堵 20.6 s | `server_v2/club_bag_api.py:run_bag_read` | S-31（占满重活池时球包仍返回） | 抓 |
| 20 | C220 | 10-30 | `/readiness` 冷启动同步重建历史统计（262 s），超过 TF 预检 60 s 读超时，TF 出包失败 | `server_v2/readiness.py:build_readiness_response` | S-24（假统计构建器挂起时 readiness 立刻返回 warming） | 抓 |
| 21 | C227/C262 | 10-30 | 附近搜索第一圈限 5 km 且等所有圈都完才显示，只出 1 个球场 | `iOS/Views/StartRoundView.swift:performNearbyDiscovery` | I-02（边界：5 km 外、8 km 内的球场出现；先到的一圈先显示） | 抓 |
| 22 | C244 | 10-31 | CoursePrep 留距逻辑先推 58° 留全挥距离，与实时 `_sequence_tail` 杆序规则矛盾 | `ai_caddie/courses/course_prep.py:_strategy`、`_shared_sequence_tail` | S-08 + S-09（同洞 prep 方案与实时建议杆序一致） | 抓 |
| 23 | C314 | 11-02 | Fastfile `backend_revision!` 健康检查无重试，一次 Funnel 断连就让整轮 TF 失败 | `fastlane/Fastfile:backend_revision!` | I-22（慢层：假 health 端点首个连接断开） | 可能（需慢层故障注入夹具） |
| 24 | C366 | 11-03 | 客户端放弃后服务端仍跑 nearby/tees/包（190–574 s），只有 `/prep` 会取消；附近请求不合并 | `server_v2/prep_work.py:run_prep`；`server_v2/map_startup.py:schedule_nearby` | S-31（客户端断开 → 重活作业 cancelled；同参数附近请求合并为一个作业） | 可能 |
| 25 | C368 | 11-03 | 客户端在 body 中途断开时返回 400，iOS 因此丢弃耗时上报，慢开局时间线丢失 | `server_v2/main.py:http_exception_handler_with_disconnect`；`iOS/Services/ClientTimingStore.swift:ClientTimingStore` | S-28（断开记 499）+ I-21（上报失败保留重传） | 抓 |
| 26 | C369 | 11-03 | Garmin 底图下载只在个人包到达后才开始（个人包用了 574 s），进第 1 洞连底图都没有 | `APP` `beginGarminRasterDownload`（private，经 `prepareCourseRound` 触发） | I-03（个人包挂起时进第 1 洞前已发出底图请求；假 `URLProtocol` 观察请求） | 抓 |
| 27 | C373 | 11-03 | Garmin 图路由是同步的，与建包共用线程池和 GIL（403–420 s） | `server_v2/garmin_raster.py:_dispatch_raster` | S-31 | 抓 |

**预期检出**：抓 18 / 可能 6 / 抓不到 3（C97、C115 视觉时序，C123 纯性能）。验收线：27 条里实际检出 ≥ 18 条（≈ 2/3），每条「没抓到」在检出表里写原因和归属（补测试 / 接受不抓）。

### 10.3 注回方式

- 每条写成一个反向补丁 `tools/faults/c387/<卡>.patch`（把修复「改回去」，不必逐字还原旧代码，只要重现根因），manifest 记录 `{"card": "C134", "goals": ["I-02"], "kind": "python|native-unit"}`；
- Python 补丁在一次性 worktree 里跑 `python -m tests.run --layer fast --goals <goals>`；Swift 补丁经 `agenthub-native-mutant.yml` 的 `patch_b64` 输入跑；
- 检出表（卡、补丁、红的测试名、用时）写进 `docs/test-plan.md` 第 10.4 节（由末卡 K13 填写）。

---

## 11. 现状基线（删前，2026-11-07，`35a402af`）

### 11.1 Python

| 项 | 数值 | 统计方法 |
|---|---|---|
| 测试方法数 | **4133** | `grep -rE "^\s+(async )?def test" tests --include=*.py \| wc -l` |
| `.py` 文件数 / 行数 | 301 / 121,010 | `find tests -name '*.py'` |
| 运行器 | 标准库 `unittest`（经 `tests/check_isolation.py`） | — |
| 故障（变异）语料 | 118 个 manifest、1076 条记录、1069 个补丁（python 725、native-unit 307、native-ui 16、python-script 5、web 5 等） | `tests/product/faults/**/manifest.json` |
| 已知红 | 7 份（`tests/product/known-red/C16a–g.md`） | — |

按目录：

| 目录 | 测试方法数 |
|---|---|
| `tests/`（顶层 `test_*.py`） | 3488 |
| `tests/product/` | 413 |
| `tests/acceptance/` | 230 |
| `tests/perf/` | 2 |

前 15 个文件：

| 文件 | 条数 | 文件 | 条数 |
|---|---|---|---|
| `test_mobile_contracts.py` | 129 | `test_contract_authority.py` | 70 |
| `test_server_v2_mobile.py` | 127 | `product/test_j4_course.py` | 62 |
| `test_mobile_event_store_phase0.py` | 119 | `test_ci_workflow.py` | 60 |
| `test_course_install.py` | 116 | `test_agenthub_deploy.py` | 58 |
| `test_decision_layer.py` | 107 | `test_topo_render.py` | 56 |
| `test_mobile_reconciliation.py` | 95 | `test_fault_runner.py` | 53 |
| `test_course_prep.py` | 74 | `test_render_backfill.py` | 51 |
| — | — | `test_history_stats_core.py` | 48 |

（`test_ci_workflow.py`、`test_fault_runner.py`、`test_contract_authority.py` 合计 183 条是测「测试设施/CI 配置文本」本身，新体系里不对应任何产品目标。）

### 11.2 Swift

| 项 | 数值 |
|---|---|
| `func test` 数 | **2051**（`grep -rE "func test" mobile \| wc -l`） |
| 测试代码行数 | 72,155（`mobile/ios/*Tests*` 下 `.swift`） |
| 按目标 | `AICaddieTests` 1344（其中 250 条在 `#if !SWIFT_PACKAGE`，仅 Xcode）；`AICaddieWatchTests` 575；`AICaddieDomainTests` 89；`AICaddieUITests` 40；`AICaddieWatchUITests` 2；（`AICaddie/` 源码目录误命中 1） |
| 框架 | 全部 XCTest，无 Swift Testing |
| `swift test` 可跑 | 仅 `AICaddieDomainTests`（其余依赖 WatchConnectivity/模拟器） |

### 11.3 用时

| 项 | 数值 | 来源 |
|---|---|---|
| CI `backend` job（main 最近 10 次，全绿） | 383 / 407 / 407 / 418 / 469 / 535 / 565 / 578 / 587 / 609 s，**中位数 502 s（8 分 22 秒）** | `gh run list --workflow ci.yml --branch main --limit 10` + `gh run view <id> --json jobs`（11-05 – 11-07） |
| CI `frontend` / `docker` job 中位数 | 221 s / 85 s | 同上（不在本卡范围） |
| 宿主 CD 全量一次 | 约 19 分 30 秒 | C387 卡面（本文未独立测） |
| PR 原生 `native-quick` 两 job | 约 22 / 31 分钟（其中冷编译约 13 分钟，单元测试 1–2 分钟） | C248 卡面 |

**删后目标对比**（末卡验收用同样方法重测）：Python 测试方法 4133 → ≤ 400（含 `subTest` 不单计）；backend 测试步骤 → ≤ 180 s；宿主 CD 测试段 → ≤ 4 分钟；Swift `func test` 2051 → ≤ 300。

---

## 12. 迁移阶段与拆卡建议

### 12.1 子卡（每卡一事、≤ 4 条验收）

卡号映射：K1=C390、K2=C391、K3=C392、K4=C393、K5=C394、K6=C395、K7=C396、K8=C397、K9=C398、K10=C399、K11=C400、K12=C401、K13=C387。

| 卡 | 标题 | 目的 | 验收（≤4） | 依赖 |
|---|---|---|---|---|
| K0 | test-plan 定稿 | Jason/土土复审本文，定目标清单与预算 | ①目标清单与风险定级经 Jason 认可 ②预算数字认可 ③方案 A/B（12.3）选定 | — |
| K1 | 新测试骨架与运行器 | 建 `tests/small|medium|large|quarantine|support`、`tests/run.py`、预算统计、small 封闭守卫 | ①`discover -s tests -t .` 只跑 small+medium，large/quarantine 为空套件 ②超单条/总预算即非 0 退出（各有一条自测）③small 中读时钟/sleep/写磁盘/联网即报错 ④旧测试原样仍在、CI 照常绿 | K0 |
| K2 | 追溯校验 | `tests/small/test_traceability.py` 解析本文第 2 节并对回 docstring/Swift 注释 | ①缺目标、未知 ID、无 `[main]` 均报错且列出 ID ②禁止 `test_c\d+` 文件名与读源码文本 ③暂以「允许缺失清单」放行未完成目标，清单只减不增 | K1 |
| K3 | 服务端快层：账号·隐私·健康·部署 | S-01–S-03、S-22–S-26、S-28、S-29 | ①每目标有 `[main]` ②D3 目标的等价类/边界表齐 ③本组 medium ≤ 40 s ④C13、C220、C368 补丁在本地注回时变红 | K2 |
| K4 | 服务端快层：球场·开局·响应性 | S-04–S-08、S-31 | ①同上 ②S-31 用 Event 占满线程池、无计时断言 ③本组 ≤ 40 s ④C34、C36、C136、C162、C189、C373 注回变红 | K2 |
| K5 | 服务端快层：记录·同步·对账 | S-11–S-14、S-19–S-21、S-27 | ①同上 ②离线队列/同步作业状态迁移全覆盖 ③本组 ≤ 50 s ④幂等/重放/并发各 ≥1 例 | K2 |
| K6 | 服务端快层：建议·球包·成绩 | S-09、S-10、S-15–S-18 | ①同上 ②统计近 N 场边界表齐 ③本组 ≤ 40 s ④C164、C244 注回变红 | K2 |
| K7 | 契约 fixture 搬家与 Python 侧契约测试 | 把 `tests/product/fixtures/shared/` 搬到 `contracts/fixtures/shared/`，新增 `mobile/contracts/fixtures/watch/`；Python 侧契约测试 | ①`project.yml`、`native-mobile.yml` 路径改好、原生构建绿 ②fixture 全部过 schema、Swift 资源副本字节一致 ③球局包路由响应过 schema | K1 |
| K8 | Swift 纯逻辑抽 `AICaddieCore` | 把记分不变式、队列状态机、环映射、建议可信判定、payload 编解码抽到无 WatchConnectivity 依赖的目标；`WatchSessioning` 协议 | ①`swift test` 在 Mac 无模拟器跑通 ②App 与手表行为不变（现有原生测试绿）③TF 只构建成功 | K0 |
| K9 | iOS 新测试 | I-01–I-21（small 在 Core，medium 在 `AICaddieTests/Goals/`）+ 两端契约 | ①每目标 `[main]` ②small ≤ 60 s、medium ≤ 5 min ③C85、C96、C114、C134、C227、C369 注回变红 ④契约 fixture 两端各测一次 | K7、K8 |
| K10 | 手表新测试 | W-01–W-14 | ①每目标 `[main]` ②队列/开局状态机全覆盖 ③Watch medium ≤ 3 min ④手表↔手机契约两端测 | K7、K8 |
| K11 | 慢层与每日任务 | S-30 large、I-22 TF 只构建、手机/手表 UI 金路径各 1 条；新 `nightly.yml`（cron） | ①慢层服务端 ≤ 6 min、UI ≤ 20 min ②每日红自动开卡 ③PR `slow` label 可触发 | K3–K6、K9、K10 |
| K12 | 变异测试与分片选择 | cosmic-ray 依赖组（宿主装 venv）、`tests/selection.toml`、`--changed`、`--shard`、`durations.json`；Muter 周跑 | ①首次基线跑出并写入阈值 ②`--changed` 对一次真实 diff 选对目标 ③2 片分片耗时差 ≤ 20% ④每周 workflow 建好 | K3–K6 |
| K13 | **注回 bug 检出表 + 删光旧测试 + CI/宿主 CD 切新分层** | 第 10 节 27 条逐条注回出表；删旧；切换 | ①检出表写入 10.4，检出 ≥ 18/27，漏网逐条说明 ②旧 `tests/test_*.py`、`tests/product/`、`tests/acceptance/`、`tests/perf/`、旧 Swift 测试全删，追溯校验「允许缺失清单」为空 ③CI backend 测试步骤 ≤ 180 s、宿主 CD 测试段 ≤ 4 min（同 11.3 方法重测）④删后照常上线一张卡、TF 照常出包 | K1–K12 |

顺序：K0 → K1 → K2 → {K3、K4、K5、K6 可并行，K7、K8 可并行} → {K9、K10} → {K11、K12} → K13。K8 改的是 iOS 大文件（`AICaddieApp.swift` 周边），按 C248 第⑤条与其它改同文件的卡串行。

K3–K10 期间新旧测试**并存**（新测试在 `tests/small|medium`，旧测试原地不动），快层会暂时更慢；这是有意的，删旧集中在 K13 一次完成，不做逐步兼容。

### 12.2 CI 改法（K13 内）

| 文件 | 改动 |
|---|---|
| `.github/workflows/ci.yml` backend | 「Run backend tests」改为 `uv run python -m tests.run --layer fast`（等价于原命令，多出预算报告）；冷启动/冒烟步骤移到 `nightly.yml` 的服务端慢层（S-30）；保留 `check_authority.py`、`py_compile` |
| `.github/workflows/native-mobile.yml` | `native-quick`：先 `swift test`（small），再按改动跑 `-only-testing:AICaddieTests/Goals` 或 `AICaddieWatchTests/Goals`；路径过滤 `tests/product/fixtures/shared/**` → `contracts/fixtures/shared/**` |
| 新 `.github/workflows/nightly.yml` | cron：服务端 large、原生全部 medium + UI、TF 只构建；每周日加变异 |
| `.github/workflows/agenthub-native-mutant.yml` | 不变（继续接收 `patch_b64`） |

### 12.3 宿主 CD 怎么切：两种做法

宿主 CD 的全量命令写在宿主 `projects.json`（job 只读可见、不可改），当前为 `python -m tests.check_isolation discover -s tests -t .`。

| | 方案 A：宿主不改（推荐先用） | 方案 B：宿主改命令 |
|---|---|---|
| 做法 | 新快层放在 `tests/small`、`tests/medium`（各带 `_bootstrap/`）；`tests/large/__init__.py`、`tests/quarantine/__init__.py` 定义 `load_tests`，未设 `AI_CADDIE_TEST_LAYER=slow` 时返回空套件；预算统计做进 `check_isolation.py`。删旧后，原命令自然只跑快层 | 土土把 `projects.json` 的命令改成 `python -m tests.run --layer fast --jobs 2` |
| 宿主改动 | 无 | 改一行命令；必须在 K13 合并**之后**改（否则 `tests.run` 不存在会红） |
| 好处 | 零协调；K13 合并即生效 | 可分片（`--jobs 2`）、报告更清楚、命令自说明 |
| 坏处 | 无法在宿主上分片；「large 不跑」依赖 `load_tests` 约定，有人误设环境变量会把慢层带进 CD | 多一次跨人协调；切换窗口内若顺序错会让 CD 红 |
| 结论 | K13 用 A；快层稳定后若宿主仍 > 4 分钟，再由土土按 B 改 | — |

### 12.4 依赖旧测试设施的外部流程：删后怎么办

| 设施 | 在哪 | 删后影响 | 处理（谁） |
|---|---|---|---|
| `tests/product/faults/<卡>/manifest.json` + `*.patch`（1076 条） | 仓库 | `target` 全指向旧测试名，删后悬空 | 删除；机制搬到 `tools/faults/`，`target` 改为目标 ID；只收第 10 节的 27 条 + 以后按目标补（K12/K13） |
| `tests/product/faults/run_faults.py`（及 `test_fault_runner.py` 53 条） | 仓库 | 同上 | 搬到 `tools/faults/run_faults.py`，加 `--goals`；它自己的测试只留 1 条 small（K13） |
| `<par1025>/related-tests.sh` | 宿主（仓库外） | **会静默失效**：它按「测试文件里出现被改文件名」挑测试，新测试不写源码文件名 → 永远输出「no Python test module references the changed files」并 exit 0 | 土土改为 `python -m tests.run --changed "$base"`，或直接跑快层（3 分钟）；K13 合并前通知 |
| `<par1025>/runtests.sh` | 宿主 | 仍可用（通用 unittest 包装 + heavy-lock） | 不改；用法改为 `runtests.sh <clone> tests.small` 等（更新 COMMON.md/DESK.md 说明，土土） |
| `tests/product/known-red/*.md`（7 份）与规格里「现品必红」（J5.7、J8.2） | 仓库 | 删 | 改为对应目标测试上的 `@unittest.expectedFailure` + docstring `KNOWN-RED Cxx`；产品修好后「意外通过」即红，逼着摘标记；追溯校验单列 known-red 目标 |
| `tests/product/fixtures/shared/`（被 `mobile/ios/project.yml`、`ProductSharedVectors.swift`、`native-mobile.yml` 引用） | 仓库 | 直接删会让原生构建失败 | K7 先搬到 `contracts/fixtures/shared/` |
| `tests/fixtures/*.pb`、`*.json`（168 KB） | 仓库 | 新测试需要的搬到 `tests/support/fixtures/`，其余删 | K3–K6 各自搬 |
| `tests/offline.py`、`tests/check_isolation.py`、`tests/_bootstrap/` | 仓库 | 保留（是设施不是测试）；`test_check_isolation.py` 等旧自测删，换 1–2 条 small | K1/K13 |
| `AGENTS.md`、`CLAUDE.md` 中 `tests/acceptance/` 「Claude 专属、Codex 不得改」规则；宿主项目控制台按路径拒绝 Codex 改 `tests/acceptance/` | 仓库 + 宿主 | 目录消失后规则失效 | 文档改为新约定（谁写目标测试、谁可改）；**宿主控制台的受保护路径需土土同步改**（K13） |
| `tests/README.md` | 仓库 | 过时 | K1 起改写为新分层说明 |
| AgentHub 原生 mutant 派发（C248：只在合并前、≤2 条） | 宿主 | 补丁来源变了 | 派发脚本读 `tools/faults/manifest.json`（土土，K12） |
| 共享 venv 加 cosmic-ray | 宿主 | 新依赖 | 宿主 `uv sync --group mutation`（土土，K12） |

### 12.5 风险与回退

- 新测试不如旧测试密：用第 10 节注回检出率和第 7 节变异分数作硬指标，未达标不进 K13。
- K13 合并后发现漏网：回退 = `git revert` K13 提交（旧测试回来），不在新体系里加兼容层。
- 手表无真实 bug 样本：手表测试强度只靠变异测试和复审，K10 验收中加「手表核心模块 Muter 存活率 ≤ 30%」作为替代证据（若 K12 先完成）。

### 12.6 本文未核实、需复审确认的点

- mutmut 3.x 只支持 pytest 运行器、cosmic-ray 可用任意 `test-command`：凭工具文档印象，K12 动手前核对。
- `tests/large/__init__.py` 的 `load_tests` 返回空套件即可让 `discover` 不进该包：符合 unittest 的包级 `load_tests` 协议，K1 用一条自测确认。（C390 已实测成立：Python 3.12 `discover` 导入包 `__init__` 后见到 `load_tests` 即交由它处理且不再递归，包内模块不被导入；自测 `tests/medium/test_layer_selection.py`。）
- 宿主 CD 19 分 30 秒、原生 PR 22/31 分钟取自卡面，未独立重测；宿主 `projects.json` 已由 C387 job 只读核过（11-07）：caddie 全量命令为 `heavy-lock --wait 5400 env AI_CADDIE_DATA_MODE=fixture <venv>/bin/python -m tests.check_isolation discover -s tests -t .`，`test_timeout` 5400 s，方案 A 前提成立。
- 第 10 节「预期」是按设计推断，实际检出以 K13 注回结果为准；C369 已合并标「待TF」，是否进了 11-07 的 TF 包未确认。
