# Claude Code Fable Max 独立全仓审查

> 审查日期：2026-07-11
> Claude Code：2.1.207
> 请求配置：`--model fable --effort max`
> 会话 ID：`3b5153c3-c15e-40a1-8c6d-2648ea2ad53d`
> 执行方式：严格只读；禁止 Edit/Write、Git mutation 与外部写操作
> 独立性：明确禁止读取 Codex 主审查 `docs/reviews/2026-07-11-full-repository-review.md` 与历史 `docs/CODE_REVIEW_FINDINGS.md`
> 模型记录：CLI 以 `fable` 启动，但运行并非纯 Fable。主会话日志中有 94 条 `claude-fable-5` assistant 记录、177 条 `claude-opus-4-8` 记录；下文两段最终综合输出均由自动 fallback 的 `claude-opus-4-8` 生成，部分调用还使用了 `claude-opus-4-8[1m]` 变体
> 动态验证限制：在 `dontAsk` 权限模式中，Python/npm 测试命令被拒绝；下文没有声称测试套件全绿
> 来源：以下正文与附录从 Claude 主会话 JSONL 中提取，保留 Claude 原始输出，仅增加本说明头。

---

Seven of eight subagents have completed and I've independently verified the geometry/AI scope first-hand (projection correctness, green-slope math, plays-like, subprocess safety, fact-binding, LLM hygiene, and now that media upload does **not** strip EXIF GPS — a privacy gap). I have comprehensive, cross-corroborated coverage. I'll synthesize the full report now.

Note: one thing I confirmed just now — `ai_caddie/core/media.py` has no EXIF/GPS stripping, so uploaded photos retain location metadata on disk and would carry it to any vision LLM provider.

Let me deliver the consolidated review.

---

# garmin-ai-caddie 全仓独立代码评审报告

**评审对象**：工作树 HEAD `a0c0fca`（分支 `integration/v2`）
**基线对比**：本地远程跟踪 ref `origin/integration/v2 = b5e17d3`，领先 HEAD 约 46 个提交（HEAD 无独有提交，即 HEAD 严格落后于远程）。未执行任何 fetch/pull。
**方法**：8 个并行子代理（后端鉴权、后端数据层、AI/几何、Web、iOS/watch、契约漂移、CI/CD、远程 diff）+ 我本人对每个层的第一手源码核验。禁读文件（`docs/CODE_REVIEW_FINDINGS.md`、`docs/reviews/**`）全程未打开。

> **关键限制**：本会话处于 `don't-ask` 权限模式，**所有 Python / npm / 测试执行均被沙箱拒绝**（我与 7 个子代理独立各自撞到同一限制）。因此**没有任何结论带 `deterministic-repro`（动态复现）证据**；全部为 `static-inference`（逐跳 file:line 核验）或 `test-evidence`（读测试/CI 源码）。凡涉及"套件是否全绿"的判断我一律不下"绿"的结论——**未能完整运行任何测试套件**。

---

## 一、发布就绪结论（Release-Readiness Verdict）

**不可发布（NOT READY）。** 存在 **1 个 P0（公网可下载的全权限凭据泄漏）** 与 **约 9 个 P1**，其中多数集中在两类要害：**记分数据在多个平台上会静默丢失**（产品核心用户数据），以及**凭据/隐私暴露**。工程"应用层"防护（fail-closed 启动、只读快照导入校验、密文脱敏、成员数据分区隔离）质量相当高，但**围绕它的发布管线与客户端记分生命周期是薄弱环节**。在 P0 与记分类 P1 修复并回归前，不应对外发 TestFlight / 公网部署。

远程分支（b5e17d3）已修掉若干 HEAD 可见缺陷（见 §六），但**未触及**本报告的任何 P0/P1 根因。

---

## 二、值得肯定之处（Strengths，均附证据）

- **成员数据隔离"由构造保证"**：`evidence_root(player_id)`（`ai_caddie/core/data.py:33`）、`_media_root`（`server_v2/media.py:44`）、`mobile_event_log(player_id)`（`ai_caddie/caddie/mobile_live.py:2203`）、成员 Garmin cookie 目录（`garmin_cn.py:78`）全部按 player_id 分路径；成员猜到 owner 的 round_id 只会拿到 200 + 空证据。由 `tests/test_aggregator_route_isolation.py`、`test_players_api_auth.py` 端到端锁定。
- **移动事件日志并发正确**：`append_event_batch`（`mobile_live.py:2380`）用 `fcntl.flock` 把"读-去重-追加"包成跨进程/跨线程的临界区，双去重键 `(round, idempotencyKey)` 与 `(round, clientId, eventId)`，容忍撕裂末行。
- **快照导入是真硬化**（对比默认危险的 `extractall`）：`ops/import_snapshot.py:20-52` 拒绝绝对路径/`..`、`resolve()` 后二次校验落点在 root 内、用 `extractfile`+`copyfileobj`（软链成员被跳过、不传播权限）。
- **Apple JWT 校验正确**：`apple_auth.py:46-49` 锁定 `algorithms=["RS256"]`（防 alg-confusion/none）、校验 aud（列表，兼容 iOS bundle + web Services ID）、iss、`require=[exp,iss,aud,sub]`。
- **会话机制稳健**：256-bit `secrets.token_urlsafe(32)`、只存 sha256 哈希、每次解析都查过期+吊销、refresh 单次化（同事务撤旧）且**保留 scope**（防 watch 会话洗成 user）。凭据比较全程 `hmac.compare_digest`/`secrets.compare_digest`。
- **指纹缓存严谨且分玩家**：`stats_cache` 以 `(name,size,mtime_ns)` 清单摘要 + player_id 为键，`clear(player_id)` 精准逐出，锁保护、build 在锁外（可接受的偶发双算）。无跨玩家缓存污染。
- **iOS 离线记分是事件日志驱动**：`OfflineStore`（`OfflineStore.swift`）append-only JSONL + 从日志重放恢复（`restoreLiveRoundState`）+ 容忍撕裂末行 + `lastApplied` 三方合并保未保存的本地编辑。
- **统计引擎避开经典坑**：除法一律有 `if total else` 守卫；推杆/GIR/开球只统计"该字段存在"的洞，2024 前无推杆时代用 `dataQuality` 标注而非拉低均值；GIR 是"regulation 触面分类"真算而非 score≤par 代理。
- **AI 是真"事实绑定"设计**：球童**建议本身是确定性规则算的**（`analysis.py`/`decision.py`），LLM 只生成解释文本；报告叙述经 `audit_report_narrative` 事后审计并在有未支撑主张时强制 confidence=low + 走确定性兜底。密文脱敏 `redact_secret_text`（`llm_providers.py:65`）覆盖 bearer/cookie/csrf/token/api_key/本地路径，API key 走 header 不进 prompt。
- **投影几何正确且被测试锁定**：等距圆柱投影带 `cos(ref_lat)`（`core/data.py:96`），`test_shot_projection.py` 锁定 semicircle 标度、ENU 轴向、往返恒等；`plays_like` 用诚实的 1:1 规则并正确做 m→yd（`elevation.py:85` `deltaYd`）。
- **CI 每个 PR 构建并冒烟两个 Docker 镜像**（`ci.yml:83-115`），`uv sync --frozen` 保证 CI 与镜像一致，直接堵住历史上"sync 镜像漂移 10 天"的复发。

---

## 三、P0 / P1 详单

> 每条含：唯一 ID · 置信度/证据类型 · 精确 file:line · 触发 · 影响 · 修复 · 验收标准 · 远程状态。

### 【P0-1】管理员令牌被烘焙进 Release IPA，并作为产物上传到**公开**仓库
- **置信度**：高 · **证据**：static-inference（全链路第一手核验）
- **位置**：`mobile/ios/AICaddie/Info.plist:24`（`AICaddieAdminToken = $(AI_CADDIE_ADMIN_TOKEN)`）→ `fastlane/Fastfile:86-88`（把 `AI_CADDIE_ADMIN_TOKEN` 注入 Release archive 的 xcargs）→ `.github/workflows/ios-testflight.yml:69`（传入 `secrets.AI_CADDIE_ADMIN_TOKEN`）+ `:74-78`（`if: always()` 上传 `build/ios/*.ipa` 为产物 `AICaddie-ipa`）。仓库为公开：`docs/ios-testflight-setup.md:60` 明写"this repo is public"。
- **触发**：任意一次 `iOS TestFlight (CD)` 运行。公开仓库的 Actions 产物任何登录用户可下载（默认保留 90 天）。
- **影响**：解压 IPA → `Info.plist` 内含**明文管理员令牌**（+ 后端 origin）。该令牌是后端全权限 owner 凭据（`X-AI-Caddie-Admin-Token`），可读写全部受保护路由（history/media/decisions/Garmin session 导入）。**这条凭据泄漏使本仓库其余所有加固形同虚设**。
- **要点澄清**：Release **代码**不读它（读取路径 `AICaddieApp.swift:798-810` 被 `#if DEBUG` 编译掉），但 Xcode 的 `$(...)` 变量替换与构建配置无关，令牌照样被写进 shipped 包——是**"随包分发但代码不用"的静默凭据**，仍可被提取。`SessionStore`/`Fastfile` 注释称 Release"never load or hold one"是**误导**（不 load 但 hold）。
- **修复**：从 `Info.plist` 彻底删除 `AICaddieAdminToken` 键（Release 本就不读；DEBUG 可从 env/Keychain 拿）；停止上传 `*.ipa` 产物（TestFlight 已有构建，产物无增益）；**并立即轮换 `AI_CADDIE_ADMIN_TOKEN`**（历史产物可能已泄漏）。
- **验收**：新 Release IPA 的 `Info.plist` 无任何令牌/密钥键；CI 不再上传 IPA 产物或产物经密钥扫描；旧令牌已轮换且旧值失效。
- **远程状态**：远程 b5e17d3 **未修**（`Info.plist`/`Fastfile`/workflow 该链在远程 diff 中无变更）。
- **备注**：子代理将其评为 P1；我上调为 P0，因"公开仓库 + 可下载产物 + 全权限令牌"构成**当下可被外部访问的凭据泄漏**。

### 【P1-1】iOS：同步进行中记录的事件被误判"已同步"而永久不上传
- **置信度**：高 · **证据**：static-inference（竞态窗口即"慢同步中记分"这一常见场景）
- **位置**：`AICaddieApp.swift:640-653`（`syncPendingEvents`）、`OfflineStore.swift:272-289`（`loadPendingEvents` 以"最后一个 sync_marker 之后"定义待同步）、`:291-312`（`appendSyncMarker` 追加在日志尾部）。
- **触发**：`syncPendingEvents` 载入待同步 → `await` 上传（数秒~30s 窗口）→ 在**尾部**追加 marker。窗口内 `handleEvent`/`acceptWatchEvent` 追加的新事件落在 marker **之前**，遂被重新归类为"已同步"。marker 的 `acceptedEventIds` 虽持久化但**从不被消费**。
- **影响**：手机→后端**静默且永久**分叉：该洞本地可见、永不到 web/watch/history；`pendingEventCount` 显示 0、状态显示"已同步"。
- **修复**：待同步用**按 eventId 的集合差**计算（所有 marker 的 `acceptedEventIds`∪`duplicateEventIds` 之外者），或对同步加 `isSyncing` 串行 + 完成后重跑。
- **验收**：新增单测——在 `loadPendingEvents` 与 `appendSyncMarker` 之间插入一条事件，断言其仍出现在下一次待同步集合并最终上传。
- **远程状态**：远程未修（`AICaddieApp`/`OfflineStore` 该逻辑在远程 diff 中未变）。

### 【P1-2】手表"保存并结束"在无后端配置时静默清空待同步事件（UI 却承诺"稍后同步"）
- **置信度**：高 · **证据**：static-inference
- **位置**：`WatchRoundModel.swift:257-274`（`confirmFinish`：`guard !pending.isEmpty, canUpload else { finishLocally() }`）、`:278-282`（`finishLocally → store.clear()`）vs `WatchFinishRoundView.swift:61-65`（`pendingUploads>0` 时显示"稍后同步 N"）。
- **触发**：独立手表局在 `config == nil`（配对后从未开过手机 app / applicationContext 未送达 / 已登出）时结束 → `canUpload=false` → `finishLocally()` 抹掉 `round.json`（含 `pendingEvents`）。
- **影响**：整局腕上记分在 UI 明说"稍后同步"的瞬间被销毁。（上传失败路径是对的——保留事件；只有 no-config 路径丢数据。）
- **修复**：`pending` 非空且 `canUpload=false` 时保持"已结束待同步"状态或把 pending 归档到幸存文件，待 config 到达后排空。
- **验收**：单测覆盖 no-config + 非空 pending 的 finish，断言 pending 被保留而非清空（现有 `WatchRoundModelTests` 反而把该丢数据行为编码为"intended"——见 §七）。
- **远程状态**：远程未修。

### 【P1-3】手机端唯一的结束方式="结束本场=丢弃",丢弃本地已存但未同步的事件，并泄漏待传媒体
- **置信度**：行为高 / 严重度中（取决于离线结束频率）· **证据**：static-inference
- **位置**：`CurrentHoleView.swift:707-719`（唯一结束入口，弹窗"未保存的记录会被丢弃"）、`AICaddieApp.swift:590-600`（`discardActiveRound` 不做最终同步）、`OfflineStore.swift:208-223`（`discardRound` 删该局事件，但**不动** `pending_media.jsonl` 与媒体文件）。
- **触发**：玩家用唯一入口结束一局。每次保存都显示"已保存"，故"未保存的记录"读作"不会丢"，但所有**未同步**事件（如离线后九洞）被删且永不到后端；`discardRound` 还把该局待传媒体文件永久遗留（磁盘泄漏，无其他 GC）。
- **修复**：新增真正的"完成"动作——先 `syncPendingEvents()`（带可见失败态）再清本地；丢弃文案改为明确的未同步计数；删除被丢弃局的 `pending_media` 条目与文件。
- **验收**：完成动作在清本地前完成一次成功同步；丢弃路径清理对应媒体；文案区分"已同步/未同步"。
- **远程状态**：远程未修。

### 【P1-4】Web：进行中的一局仅存在 React state，刷新/切后台/误点即整局丢失
- **置信度**：高 · **证据**：static-inference
- **位置**：`web_v2/src/components/RecordRoundPage.tsx:89-101`（全用 `useState`，全文件无任何存储读写）、`:299-301`（退出按钮无二次确认）。
- **触发**：手机浏览器约 4 小时一局中，后台标签被回收（击球间极常见）/ 刷新 / 点"退出(不保存)"。`clientRoundId` 幂等与 `submitting` 防抖只护"最终提交"，不护会话。
- **影响**：产品核心用户数据在其最高风险平台上全损。**与 iOS 形成鲜明对比**：iOS 记分是事件日志持久化 + 重启恢复；Web 记分器没拿到同等耐久工程——Web 是这条链的薄弱点。
- **修复**：每次变更把 `{clientRoundId,course,holes,currentHole}` 写 localStorage、挂载时恢复（"恢复上次未提交的球局"）；给退出加确认；失败提交入队重试。
- **验收**：模拟刷新/重挂载后能恢复进行中的一局；退出有确认。
- **远程状态**：远程未修（`RecordRoundPage` 在远程 diff 中未变）。

### 【P1-5】addShot 订正的 `club`/`lie` 被 Pydantic 请求模型静默丢弃（永久数据丢失）
- **置信度**：高 · **证据**：static-inference（两侧 + Pydantic v2 `extra='ignore'` 定义性行为）
- **位置**：iOS 发送 `club`/`lie`——`RoundCorrection.swift:31-32,68-69`；服务端 `RoundCorrectionRequest`（`server_v2/models.py:474-486`）**无 club/lie 字段**、无 `extra` 配置（默认 ignore），路由存 `body.model_dump()`（`main.py:544`）只含声明字段；读侧却期望它们——`round_shot_map.py:147-148` 用 `e.get("lie")/e.get("club")` → 恒为 `None`。
- **触发**：任意当前 iOS 版本经复盘编辑器补/改一杆。Web 不发 addShot。
- **影响**：用户填的球杆/球位在服务端往返后消失（落点渲染成红色"未知"）；订正日志永久缺字段。
- **修复**：给 `RoundCorrectionRequest` 加 `club: str|None=None` 与 `lie: str|None=None`，并加断言 `stored["club"]` 的测试。
- **验收**：POST 带 club/lie 的 addShot 后，落库记录与 shotmap 读回均含二者。
- **远程状态**：远程未修（`models.py` 该模型在远程 diff 中未加这两字段）。
- **测试反证**：`tests/test_corrections_api_ops.py` 文档自称"落库不被丢字段",却恰恰不断言 club/lie——见 §七。

### 【P1-6】Swift 事件类型枚举全面封闭 → 新事件种类破坏三条前向兼容路径
- **置信度**：高 · **证据**：static-inference + 远程 `.fairway` 提交佐证
- **位置**：`LiveRoundEventKind`（`LiveRoundEvent.swift:3-13`，9 例无 unknown）、`WatchInputKind`（`WatchEventBridge.swift:4-10`、`WatchSyncClient.swift:6-12`）、三处 exhaustive switch（`WatchRoundState.swift:397`、`WatchBackendClient.swift:48`、`OfflineStore.swift:348`）。
- **三种版本组合破坏**：① 新手表+旧手机：`decode(WatchInputEvent)` 遇未知 kind → 回 `["accepted": false]` 无 eventId → 手表 `resolvedEventIds` 空 → 事件在每次可达性变化时**无限重试**、队列永不排空；② 新客户端+旧服务端：`LiveRoundEventBatchRequest` 逐事件按 Literal 校验 → 一个未知 kind **422 整批**（`mobile.py:126`）→ 手表 `confirmFinish` 全量保留 `uploadError`；③ 旧手机+新服务端 replay：`decode(LiveRoundEvent)` 遇新 kind 抛错 → **整个 replay 响应失败**，未更新的 TestFlight 手机无法多端追赶。
- **影响**：一旦上线任一新事件种类（远程已在做 `.fairway`），HEAD 期的 TestFlight 旧包会命中路径③；缺乏协商机制（`schema` 常量只是文档不校验）。
- **修复**：给两个枚举加 `unknown` 兜底 case（`init(rawValue:)` fallback）；replay 解码跳过未知；手机 bridge 对解码失败回 `rejectedEventIds+reason`；服务端改逐事件 accept/reject 而非整批 422。**上线纪律**：服务端先于客户端部署。
- **验收**：向 Swift 解码器投喂未知 kind 不崩、被 drop 并上报；旧客户端 replay 含新 kind 事件时能跳过继续。
- **远程状态**：远程用 `7016a46` 加 `.fairway`、`b98b347` 补三处 switch——**只解决了那一个新种类的编译**，未引入通用 unknown 兜底，故此根因**远程仍在**。

### 【P1-7】同日合并的 18 洞局用"9 洞 rating/slope"计算差点，污染所有差值统计
- **置信度**：高 · **证据**：static-inference + 仓内 docstring/窗口测试佐证该数据形态
- **位置**：`ai_caddie/history/history.py:365`（`merge_same_day_halves` 用 `{**front, ...}` 且从不覆写 `rating`/`slope`，二者在 `:282-283` 取自 9 洞 `teeBoxRating/teeBoxSlope`）；`history_stats.py:248-254`（`_round_differential = (score18 - rating)*113/slope` **无合理性守卫**，`rating>=50` 守卫**只在** `_round_differential_or_par`）。**我已第一手核验** `_round_differential` 确无 rating 守卫。
- **触发**：任意同日 9+9 合并且 tee rating 为 9 洞值的局（代码 docstring 与 `test_history_stats_window.py:361-377` 自述该形态真实存在）。
- **影响**：`summary.averageDifferential/bestDifferential/recent10AverageDifferential`、`difficultyAdjusted`、各 `time.by*` 时段差值全部注入约 +55 杆的**幻象差点**——用户可见的错误数学（且进入 mobile payload）。
- **修复**：在 `_round_differential` 内加同样的 `rating>=50`（或 `merged` 标记）守卫，或在 `merge_same_day_halves` 里把 rating/slope 置空。
- **验收**：金标测试固定一个合并 18 洞局的差点为诚实值（≈43 而非≈94）。
- **远程状态**：远程未修。

### 【P1-8】`superfly/flyctl-actions/setup-flyctl@master` 可变分支引用 + job 级暴露部署密钥，且被测试"钉死"为不安全
- **置信度**：高 · **证据**：static-inference
- **位置**：`.github/workflows/backend-fly-deploy.yml:76`；job 级 `env`（:58-68）把 `FLY_API_TOKEN` 与 `AI_CADDIE_ADMIN_TOKEN` 注入**每个** step（含该第三方 action 与 setup-uv）；`tests/test_ci_workflow.py:194` 断言 `assertIn("...@master", text)` ——测试**强制**了这个可变引用。
- **触发**：superfly `master` 被恶意/被入侵推送后，任意一次 `Backend Fly Deploy`。
- **影响**：以 Fly org token（整套基础设施控制权）+ 管理员令牌执行任意代码。
- **修复**：钉到 commit SHA；把两个密钥从 job 级 `env` 下放到真正使用它们的 step；同步改测试为钉 SHA。
- **验收**：workflow 引用为 `@<sha>`；密钥不在 job 级 env；测试断言 SHA。
- **远程状态**：远程未修。

> **P1 汇总**：P0-1（凭据泄漏）+ P1-1/2/3/4（四平台记分丢数据：iOS 同步竞态 / watch 无配置清空 / 手机丢弃式结束 / Web 无持久化）+ P1-5（订正丢字段）+ P1-6（枚举前向兼容）+ P1-7（差点数学）+ P1-8（供应链）。**根因去重**：P1-1/2/3 同属"客户端记分生命周期缺'先同步再落地'的原子收尾"；与 §四多条"非原子写"同族但分属不同存储，单列。

---

## 四、P2 / P3 完整清单（精简）

### P2（去重后）
- **[P2-a] 部署漂移：`render.yaml` 直起 uvicorn，跳过 `alembic upgrade head` 且 `uv sync` 不带 `--frozen`**。`render.yaml:6-7`；迁移只在 `ops/start_api.sh:44` 跑，应用从不 `create_all`（我已 grep 确认）。Render（`docs/deployment/private-trial.md:11` 列为 API 起点）与文档的"本地私有冒烟"裸 uvicorn 命令（`private-trial.md:46-51`）都不迁移 → 身份表缺失 → **Apple 登录/成员会话全坏**（owner 用管理员令牌仍可用）。Fly/Docker/compose 路径经 `start_api.sh` 正确。**我与 CI/CD 代理独立同证**。
- **[P2-b] 成员 Garmin 会话 cookie 被扫进"secretFree:true"的备份/快照**。`export_snapshot.py:11-15` 递归收全部 `data/players/`，无 `.garmin_tokens` 排除；成员 cookie 存于 `data/players/<id>/.garmin_tokens/`（`garmin_cn.py:78`、`session.py:24`）。导出/备份 manifest 却硬写 `secretFree:True`（`export_snapshot.py:95`、`backup_data.sh:35`），与 readiness 的"secret_handling ready"自相矛盾。**我第一手两侧核验**。
- **[P2-c] 开放式成员自助注册 + 无限流/无配额**。`auth_api.py:107-165` 任意首见 Apple sub（aud 匹配 bundle）自动在 owner 家庭建成员；无邀请/白名单/上限；无速率限制/存储配额 → 可无界增长租户 + 认证态算力/LLM 成本滥用（`/reports/*/generate` 触发付费 provider，80MB 媒体上传）。
- **[P2-d] 默认 fail-open**：无 admin token 且无 profile 时匿名请求解析为 OWNER（`players_api.py:122-126`），启动仅 WARNING 不拒。Docker/Fly 由 `start_api.sh` fail-closed 兜底；裸 uvicorn 无兜底。`test_players_api_auth.py:93` 把该 fail-open 编码为期望——见 §七。
- **[P2-e] 差点/统计的金标 + 性能回归测试在 CI 从不运行**。`tests/test_history_stats_perf.py` 为 pytest 风格（0 个 `TestCase`），CI 用 `unittest discover`（`ci.yml:31`），且 pytest 不在依赖里 → 收集 0 个用例。仓内**唯一**统计金标 `fixtures/history_stats_perf_golden.json` 与 O(n²) 性能界成为 CI 死代码。
- **[P2-f] 圆桌一堆非原子/无锁的读改写 JSON 存储**（撕裂/丢更新/幂等丢失）：`round_ingest._save_index`/`_update_summary`（`round_ingest.py:91,538`，未用现成 `atomic_write_json`）→ 崩溃即丢全部幂等历史、并发即重复入库重复计分；`fetch.py:76,128,168` 抓取写、`vision_context.py:283` 整体重写、mobile ack `mobile_live.py:2289`、corrections/players 注册等。两进程同步（API `_SYNC_LOCK` 仅进程内 vs cron `flock`）无共享卷锁。
- **[P2-g] 无界后台线程**：`main.py:496`（每次 ingest）、`:1308`（每次 sync）各 spawn 一个重活 daemon 线程（几何 ensure 网络拉取 + topo 渲染 + 三窗口 stats warm），无池/去抖/join；配合 P2-c 可被成员放大。**我已 grep 确认**四处 spawn。
- **[P2-h] O(n) / O(n²) 热路径**：owner 事件日志单文件永久增长、每批全量重解析（`mobile_live.py:2386`）；`/sync/status` 每次解析 `data/snapshots/` 全部（含多 MB 洞快照，`snapshot.py:770`）；`load_shot_history` 每洞重解析记分卡（`history.py:475`）；每次 API 同步写 manifest 触发全量 stats 重算。
- **[P2-i] Web：ClubBagPage 切玩家无 seq 守卫的竞态** → owner 可把 A 的球包保存到 B（跨成员写污染，`ClubBagPage.tsx:42-118`）；**无错误边界**任意渲染异常整站白屏（`main.tsx`）；**boot 后无全局 401 处理**，会员会话过期后翻转成 owner-mode UI。
- **[P2-j] Web/Vercel 无安全响应头**（CSP/X-Frame-Options/X-Content-Type-Options/HSTS 缺失，`vercel.json`），叠加会话 token 存 localStorage → XSS 爆炸半径最大化；`VITE_AI_CADDIE_REQUIRE_LINK` 未在 vercel.json 设置 → 消费部署门禁 fail-open。
- **[P2-k] 契约漂移**：发布的 JSON Schema 拒绝真实包（`clubProfiles[].sampleRefs` 未在 schema 且 `additionalProperties:false`）；手表直传 vs 手机中转产出不同 wire 事件（source 戳/strokes 强转 0/club 优先级）；auth `expiresAt` 服务端带微秒、iOS `ISO8601DateFormatter` 默认不解析小数秒 → 客户端过期逻辑全失效（token 到 401 才失效，手表更把过期 token 当永活）。
- **[P2-l] iOS/watch 一批**：无 token 刷新接线（`AppleAuthClient.refresh` 零调用），过期即静默掉认证；手机→手表状态推送**每 3m GPS 定位**都 `transferUserInfo` → 泛滥 WC 队列且无 errorHandler；`WatchSyncClient` 队列无同步的读改写竞态；`WatchRoundModel.record` 失败使整局从 UI 消失；实打把**米**的高程差直接加到**码**距离（应用现成的 `deltaYd`，`WatchRoundContainerView.swift:170`）；`WatchInputView` 过期 `@State` 可把一洞数值写到另一洞、club 事件带虚假 `distanceToPinM:0`；**无 `PrivacyInfo.xcprivacy`**（App Store 拒审风险）；"断开 Garmin"只删本地、后端仍持有并使用 Garmin cookie。
- **[P2-m] CI/发布治理**：5/7 workflow 无 `permissions:` 块（默认宽授）；**默认分支 push 不跑 CI**（`ci.yml:3-5` 仅 dispatch+PR，被 `test_ci_workflow.py` 钉死）→ 直推 `integration/v2` 无信号；fastlane **完全不钉版本、无 `Gemfile.lock`**（处理 ASC 私钥/match 密码的管线每次装最新全树）；私有家庭后端 origin 硬编码进公开 workflow（`native-mobile.yml:56`）。
- **[P2-n] readiness 在部署容器内永远 degraded**：`readiness.py:1161-1170` 要求 `docs/`、`mobile/contracts/`、`render.yaml`、`web_v2/vercel.json` 存在于盘，但 `Dockerfile:27-31` 只 COPY `ai_caddie/server_v2/ops/migrations`——运行时永报 `missing_ops_files`，唯一聚合健康信号恒红，无告警价值（且无其他监控/告警）。
- **[P2-o] 备份系统无调度、无轮转、恢复从未演练**：无 cron 触发 `backup_data.sh`、无按数/龄裁剪、备份与被保护数据同卷、无异机副本、无自动 restore-verify。
- **[P2-p] cron self-heal 明文存 Garmin 凭据**（`auto_sync.sh:13` `.garmin_tokens/garmin_login.json`），与 README:41-43"不保存密码"矛盾且不强制 chmod。

### P3（清单）
- `atomic_write_json` 无 fsync + 仅按 PID 命名临时文件（断电可留零长度文件；同进程双线程写同路径会 `os.replace` FileNotFoundError → 500）**（我与数据层代理同证）**；`round_shot_map.py:169` 循环变量遮蔽 → `roundRef` 返回一个 shot id；只做位置编辑的杆会**就地修改共享缓存的 HistoryData**（`round_shot_map.py:160`）；`merge_same_day_halves` 把 None 当 0；`_merge_owner_sources` 同日同场会吞掉第二局；`_reconcile_abandoned` 可能删掉"本地撕裂但其实已完成"的局；每次 API 同步都无条件失效缓存（写新 manifest 进指纹目录）而 cron pipeline 反而不写 status（`/sync/status` 陈旧）；durable snapshot 每次全量复制无保留上限；`AnnotationCreateRequest.payload` 无大小上限；身份层无 `sessions.user_id`/`user_identities.user_id` 索引、过期会话/吊销从不清理、`get_engine` 首调竞态、`load_registry` 在鉴权读路径里**写**默认注册表（只读 FS 会 500）；`server_v2/geometry.py` 零异常处理（畸形 mesh JSON 可 500）；`create_manual_round` id 用秒级时间戳（同秒覆盖）。
- 后端：`course_topo_prewarm` POST + `course_tees` GET 无鉴权（轻度 DoS 放大，后台渲染）；`weather` open_meteo 固定 host + 数值经纬度（无 SSRF，已核）；`geometry` 子进程用 list 形 `subprocess.run` + 超时无 shell 注入（已核）；**上传媒体不剥离 EXIF GPS**（`core/media.py` 无 exif 处理）→ 照片位置元数据留盘并会随 vision LLM 外发（我第一手核验）。
- Web：无 URL 路由（后退即退出、刷新丢上下文）；`refreshRoundsState` 忽略 seq 守卫捕获陈旧过滤器；球包页被 ~11MB 全量 stats 阻塞；e2e `screenshots.spec.ts` 用 sleep + 把失败降级为 `console.warn`（结构上不可能失败）；`InvalidLinkPage` 死代码却由自身测试养活；平/标准杆渲染不一致（"E" vs "0"）；`CaddiePage` 媒体上传把整文件 base64 进内存无大小上限。
- iOS/watch：UITest GPS 注入钩子（`UITEST_GPS_LAT/LON`）**未 `#if DEBUG` 门禁**编进 Release（`LocationProvider.swift:26-47`、`WatchLocationProvider.swift:36-47`；对比 `WatchUITestRoot` 正确门禁）；本地 `sync_marker` 违反事件契约（`hole:0` vs schema `minimum:1`）；手表 replay/ack 客户端是死代码（从不反向对账）；`pushHoleImage` 复用单临时路径可致传输前被覆盖；O(n²) 事件日志访问；中英文案混用（手表出现英文 targetNote）；无障碍缺失（Canvas 无 a11y、手表定尺字、26pt < 44pt 命中区、纯色编码）；`Package.swift` 与 `project.yml` 漂移；幂等键=全 eventId 拼接（超大批可撑爆 header）；媒体上传无幂等（成功后崩溃会重复上传）；手表 GPS 启动即开永不停（耗电）。
- 契约：Schema 比服务端更严（时间戳时区、`targetKind` 枚举）造成静默契约洞；TS 类型滞后 Pydantic（多字段缺失、`name`/`dataMode` 可空性谎报）；绿坡 `greenSlope` payload HEAD 仅后端有（客户端无消费，属有意滞后）；球位词表在采集/编辑/渲染面漂移（`tee` vs `teebox`）；`phoneSequence` 死协议字段。
- CI/容器：镜像以 **root** 运行（Dockerfile 无 `USER`）**（我同证）**、基础镜像按 tag 而非 digest 钉；`fly.toml` 无 HTTP 健康检查；compose `web` 开发服务 0.0.0.0 发布 + 整仓 rw 挂载；`import_snapshot.py` 不校验 manifest sha256；`build_sync_image.sh` 依赖检出目录名；录屏/录制 lane 吞失败 + sleep；OAuth 探针密钥走 argv；native build "evidence" 是声明戳而非派生数据；`eval`-based 密钥存在性检查。

---

## 五、验证命令与结果 / 限制

- **HEAD/远程基线**（成功）：`git rev-parse HEAD`→`a0c0fca`；`git rev-parse origin/integration/v2`→`b5e17d3`；`git log --oneline HEAD..origin/integration/v2`→46 提交，HEAD 无独有提交。`git diff --stat`（排除禁读文件）：远程主要动 server_v2、watch、tests、web copy、CI。
- **路由面枚举**（成功）：仅 `admin_router`+`auth_router` 两个 router 均已挂载 + main.py 内 `@app` 路由，鉴权矩阵完整覆盖，无未挂载/隐藏 router。
- **迁移完整性**（成功，读源码）：`migrations/versions/0001+0002` 建齐 9 张身份表，线性单 head，均可逆；应用无 `create_all`（仅注释引用）。
- **构建产物追踪**（成功）：`git ls-files web_v2/dist`→0（未跟踪）；`.dockerignore` 正确排除 `.garmin_tokens/data/clubs.json/.env*/backups`。
- **公开仓库事实**（成功）：`docs/ios-testflight-setup.md:60` 明写"this repo is public"（P0 定级依据）。
- **测试执行**（**全部被拒**）：`.venv/bin/python -m unittest ...`、`python3 -c ...`、`npm ...` 在 `don't-ask` 模式下一律被沙箱拒绝（我与 7 个子代理独立各自撞到）。仅 `--version` 类探针可过。**故未运行任何测试套件，不对任何套件下"绿"结论**；所有测试相关判断均为读源码的 `test-evidence`。`node v24.4.1` 存在但 `npm`/`npx` 被拒。
- **fixture 模式**：无论如何均以 `AI_CADDIE_DATA_MODE=fixture` 为前提；私有挂载数据（`data/`、`.garmin_tokens`）全程未读取/未打印。
- **子代理**：8 个中 7 个完成（后端鉴权/数据层、Web、iOS/watch、契约、CI/CD、远程 diff）；AI/几何专项代理在本报告合成时仍在运行——但其全部范围（投影正确性+测试、绿坡平面拟合、plays-like、子进程注入、事实绑定、LLM 密文卫生、EXIF）已由我第一手核验覆盖，报告无缺口。

---

## 六、HEAD vs 远程（origin/integration/v2）状态标注

- **已在远程修复的 HEAD 缺陷**（远程 diff 佐证，均非本报告 P0/P1 根因）：手表测距气泡压住球童卡（`318bd6d`）、复盘编辑两个"完成"并排（`37ce670`）、实战洞图加载态像黑屏（`37ce670`，仍有"失败误报为无几何"残留）、首开 prep 冷启动 2–19s（`6ae51f3`，成员/冷容器首开仍慢）、cache-warmup flaky "4!=3"（`2de5ef7`，**未 drain `prepare-recent-ingest/-sync` 线程,仍不全**）、Web 黑话文案（`86cada7`）、手表 uitest 定位框（`a09223d`）。
- **远程新增且可疑**（远程独有）：上球道问法**未按 par-4/5 门禁** → par-3 fairway 污染开球统计（远程 `WatchInputView.swift`/`round_ingest.py:282`，**P2**）；fairway 答案把左/中/右全归"hit"丢方向；`greenSlope.directionDeg` 在投影失败时残留地面帧（画错破孔箭头）；`green_read` 平面拟合跨整块 Green.drc（多果岭串扰）——**HEAD 无 `green_read`,属远程独有**；测试钩子未全编译门禁（`WatchHoleMapView.swift:140` pin 半径按 uitest 运行参数、`UITEST_GPS_ROUTE` 未 `#if DEBUG`）。
- **本报告 P0/P1 的远程状态**：P0-1、P1-1~P1-8 的**根因在远程 b5e17d3 均未修**（远程 diff 未触及对应文件/逻辑；P1-6 远程仅补了 `.fairway` 单例编译，未加通用 unknown 兜底）。
- **规范落地**（两份 2026-07-10 未跟踪手表规范 vs 远程实现）：远程落地了 Phase-2 能力（测距/拖旗/大字/fairway/坡度），但**表冠轴"操控宪法"基本未开工**——手表目标内零 `digitalCrownRotation`，五页横滑/浮层选杆/开局向导/合并 hub 等均缺；`fullMap` 甚至画了个不工作且与规范相悖的"转表冠缩放"提示。属规范晚于分支的预期缺口，非 bug。

---

## 七、编码了不安全/错误行为的测试（勿盲信）

- `tests/test_players_api_auth.py:93`（`test_dev_profile_no_token_defaults_to_owner`）把 P2-d 的 fail-open 默认编码为期望行为。
- `tests/test_corrections_api_ops.py` docstring 自称"落库不被丢字段",却不断言 club/lie——正是 P1-5 漏掉的断言。
- `WatchRoundModelTests` 把 P1-2 的"无配置结束即清空 pending"编码为 `intended`（"no backend configured → local practice round"），锁死了丢数据契约。
- `tests/test_history_stats_perf.py` pytest 风格在 unittest-discover CI 下收集 0 用例（P2-e），唯一统计金标成死代码。
- `tests/test_round_ingest_api.py` 不 patch `_prepare_recent_bg` → 每个 POST 泄漏真线程（flaky 根源，HEAD 未修）；`test_server_v2_cache_warmup.py` 只 patch 一个 warmer 线程，boot 的 prepare-recent 线程真跑（可触网络）。
- `e2e/screenshots.spec.ts:1006-1009` 把 `failedResponses`/`browserErrors` 降级为 `console.warn` + `waitForTimeout(800/1200)` → 结构上不可能失败、对半渲染截图当"稳定"。
- 大量 `test_ci_workflow.py`/`test_deployment_manifests.py` 是对 YAML/文档的 `assertIn` 字符串断言（防删有价值，但对注释掉的行也通过、且把不安全选择——`@master` 引用、模拟器名——钉死为"期望状态"）。

---

## 八、架构建议与分阶段修复路线图

**架构层面（根因收敛）**
1. **记分收尾统一为"先同步再落地"的原子事务**：iOS/watch/Web 三端共用同一语义——完成动作必须先成功同步、失败态可见、按 eventId 集合差判定待同步（消除 P1-1/2/3/4 全族），Web 补 localStorage 持久化对齐 iOS 的事件日志耐久。
2. **文件存储写入统一走 `atomic_write_json` + 跨进程 flock**：把已在事件日志证明的 `flock` 模式推广到 ingest 索引/summary、抓取写、vision findings、ack、注册表（消除 P2-f/P3 非原子族 + 两进程同步竞态）。
3. **契约版本协商机制化**：所有 Swift 事件/覆盖枚举加 `unknown` 兜底、replay 跳过未知、服务端逐事件 accept/reject；建立 Swift-encode↔JSON-Schema 往返测试与手机/手表 mapper 奇偶测试（消除 P1-6、P2-k）。
4. **发布管线去凭据化**：令牌不进任何 shipped 包/产物，改运行时后端屏输入；workflow 全加最小 `permissions`、第三方 action 钉 SHA、密钥下放到 step（消除 P0-1、P1-8、P2-m）。
5. **认证态资源治理**：成员注册加邀请/白名单/家庭上限 + 全局限流 + 每玩家配额 + 背景任务改单飞线程池（消除 P2-c/g）。

**分阶段路线图**
- **P0/发布前阻断（0–3 天）**：修 P0-1（删 Info.plist 令牌键 + 停传 IPA 产物 + **轮换令牌**）；修 P1-8（钉 SHA + 密钥下放）；四端记分丢数据 P1-1/2/3/4 至少上"先同步再落地 + 二次确认 + Web 持久化"；P1-5 加 club/lie 字段；P1-7 加 rating 守卫。
- **P1 收尾（1–2 周）**：P1-6 枚举 unknown 兜底 + 契约往返/奇偶测试；P2-a 让 render.yaml 走 `start_api.sh`（或标注"仅 fixture"）；P2-b 备份排除 `.garmin_tokens` 并让 `secretFree` 由扫描而非硬写决定；P2-e 把 perf/金标测试改 `unittest.TestCase`。
- **加固（2–4 周）**：P2-c/d/j 鉴权与门禁 fail-closed + 限流 + 安全头 + CSP；P2-f/g/h 原子写/共享锁/线程池/热路径分文件;P2-n readiness 拆"仓库卫生（仅 CI）"与"运行时"；P2-l iOS token 刷新 + 单位修正 + PrivacyInfo.xcprivacy；备份调度/轮转/异机/恢复演练（P2-o）。
- **持续**：默认分支 push 跑 CI；`Gemfile.lock` 钉版本；容器非 root + digest 钉；文档/runbook 修断（见远程代理列出的 STATUS.md 陈旧、REMOTE_DEV.md 死路径、secrets.md 导出清单滞后、`.env.example` 缺 `AI_CADDIE_ADMIN_APPLE_EMAILS` 等）。

---

## 九、新增或容易被其他审查遗漏的发现

1. **"secretFree:true"的备份实际含成员 Garmin 会话 cookie（P2-b）**：allowlist 递归收 `data/players/` 却无 `.garmin_tokens` 例外——一个自称无密文的产物携带可冒充成员 Garmin CN 账号的活 cookie，且直接推翻 readiness 的"secret_handling ready"自证。两侧 file:line 已核。
2. **"事实绑定"只绑类别不绑数值**：`audit_report_narrative`（`reports.py:2304`）按关键词判断叙述是否*提及*某统计类别且该类别*有*结构化事实支撑——但**不校验数值**。故 LLM 在"有支撑的类别"里编一个错数字（如把 GIR 40% 说成 80%）会通过审计、被标为 `factBinding:bound`。这是产品招牌"fact-bound"的实质盲区（我第一手读透审计逻辑）。
3. **一处"投影正确、但客户端用错单位"的隐形错配**：后端 `plays_like` 正确产出 `deltaYd`（m→yd），但手表实打**忽略 deltaYd、把原始米高程差加到码距离**（`WatchRoundContainerView.swift:170`）——修复只需改用现成的 `deltaYd`。这类"服务端对、客户端misuse"最易被单侧审查漏掉。
4. **同一个"记分耐久"能力,iOS 做对了、Web 没做**：iOS 是事件日志 + 重启恢复 + 撕裂容忍（工程扎实），Web 记分器却零持久化（P1-4）——跨平台一致性缺口使 Web 成为唯一会按设计丢整局的面。
5. **`render.yaml` 与"本地私有冒烟"文档命令都绕过迁移**：不仅是一个陈旧 manifest——文档 `private-trial.md:46-51` 教操作者用的裸 `uvicorn` 命令同样跳过 `alembic upgrade head`，直接与 lifespan 注释"schema 由 Alembic 独占、start_api.sh 迁移"的前提矛盾，静默地让 Apple 登录在这两条路径上坏掉。
6. **上传媒体不剥离 EXIF GPS（P3）**：`core/media.py` 无任何 exif 处理，照片位置元数据留盘并会随 `analyze_media` 外发给 vision LLM——"私有试用"隐私姿态下的加固缺口。
7. **测试把不安全行为钉成"期望"**（§七）：fail-open 默认、watch 无配置清空、订正丢字段、`@master` 引用、模拟器名——多条"绿测试"其实在锁死缺陷；`test_history_stats_perf.py` 更是唯一统计金标却在 CI 里收集 0 用例。
8. **无界 daemon 线程 × 开放注册 × 无限流的复合放大**：单看每条是中低危,组合起来一个自助注册的成员可经 `/players/{id}/rounds` 反复触发重活背景线程 + 付费 LLM + 80MB 媒体,无任何配额/限流兜底。
The final AI/geometry subagent completed and it materially strengthens two areas of the report — I'm integrating it now as an addendum (new/changed items only; the rest of the report above stands).

---

# 附录 · 集成 AI/几何专项代理（第 8 个,报告合成后返回）

该代理证据类型同为 `static-inference`（Python/测试执行同样被沙箱拒绝,数学用手算对照金标验证）。它带来 **1 条应上调为 P1 的发现** 与 **1 条我此前未覆盖的 P2 正确性缺陷**,并佐证了投影/子进程/密文卫生等既有结论。**发布结论不变:仍为不可发布**;P1 数量由 9 升至 10。

## 新增 / 升级发现

### 【P1-9】"事实绑定"审计只认英文关键词,而模型被要求输出中文 → 招牌安全属性在生产语言下失效
- **置信度**:高 · **证据**:static-inference（正则集全英文 + prompt 命令简体中文,两侧 file:line）
- **位置**:`ai_caddie/reports/reports.py:183-201`(`_CATEGORY_MENTION_PATTERNS` 全为英文 `\b` 正则)vs prompt `reports.py:2604-2609`(命令"简体中文")。审计入口 `reports.py:2319-2323`。
- **触发**:配置任意非 static provider(anthropic/gemini/nvidia)时,模型返回的**中文**叙述里编造天气/球位/罚杆/策略/因果("当天阵风很大""下水是因为糟糕球位""建议每洞强攻果岭")——**匹配不到任何英文 detector** → `unsupportedClaims=[]` → `factBinding.state="bound"`、`confidence` 维持 medium/high。仅语言无关的球杆代码正则(`8i|pw…`)幸存。
- **影响**:产品招牌"fact-bound AI review"的核心安全性质**在它实际生成的语言里根本不成立**;编造的球童建议以"已绑定/中高可信"出厂。这是我此前"只绑类别不绑数值"这一 §九-2 观察的**更严重形态**——审计根本不在生产语言上运作,故上调为 **P1**。
- **修复**:给每个 `_CATEGORY_MENTION_PATTERNS`/`_*_VALUE_TOKENS` 补中文词表(风/雨/阵风;球位/坡/沙坑/长草;罚杆/下水/OB;一号木/铁杆/挖起杆;应该/建议/进攻/保守;因为/导致);或改让模型产出结构化 JSON、按字段校验而非审计散文。
- **验收**:金标测试喂**中文**含编造主张的叙述,断言其被标 `needs_review` 且 confidence 降为 low(现 `test_fact_bound_reports.py` 所有 flag 断言只喂英文——见下)。
- **远程状态**:远程未修。

### 【P2-q】`geometry_evidence` 多边形读取器与管线实际写出的形状不兼容 → 真实球场静默丢危险区/地表
- **置信度**:中高 · **证据**:static-inference(写侧 vs 读侧形状不符;所有多边形形输入均为测试合成)
- **位置**:读侧要求 `hazard.get("polygon")`/points/path(`geometry_evidence.py:279,489,544,613`)、`_mesh_surface_rows` 需多边形环(`:165-171`);但写侧**不产多边形**:`export_prodgeometry_hazards.py:96-127` 写 `centroid/bbox/tee_distances`、`decode_courseview_geometry.js:207-213` 写 `meshes:[{name,positions,faces}]`。
- **触发**:任意真实解码球场经 `classify_shot_surface`/`build_route_geometry_evidence`/`build_hole_map_dto`。
- **影响**:生产几何上 `classify_shot_surface` 恒返回 `surface:"unknown"` → 手动局的**几何 GIR/fairway 恒 None**(`round_ingest.py:434-447`);`/geometry/hole/{}/map` 不出危险区/地表多边形;caddie route 的 `avoidZones`/`hazardClearances` 为空。**主线复盘洞分析不受影响**(走单独的三角形路径 `analysis.py:266-298`),prep/watch 危险区也走三角形路径——故此坑只在 `geometry_evidence` 这条线,且被测试掩盖。
- **修复**:把真实 `positions/faces`(或 hazard `centroid/bbox`)适配成环,或像 `analysis.py` 那样走 `mesh_components`;加真实形状回归测试。
- **远程状态**:远程未见修复此形状适配。

## 佐证 / 归并（并入已有条目）
- **EXIF/GPS 不剥离**(我在 §四-P3 已列):代理补充了**传输面**——`vision_context.py:144-164` 把原始字节连同 EXIF 转发给第三方多模态 LLM(Anthropic/Gemini/NVIDIA),独立于"高尔夫位置隐私模型"之外。定级由 P3 维持但影响面更广(留盘 + 外发)。
- **`green_slope.directionDeg` 是"数学角冒充方位角"且在错误坐标帧**(并入 §九 subtle + §六远程 directionDeg 关切):`elevation.py:140` 的 `atan2(-b,-a)` 是在**未旋转**的 east/north 度量帧、从东逆时针的数学角,却被 docstring/字段命名为"topo 帧的 bearing"(`elevation.py:117`、`course_prep.py:359`);而 topo 图是**旋转**到 tee→green 轴的(`hole_render._setup:65-98`)。当前潜伏(手机只画幅值、方向箭头 deferred),但对下一个消费它的客户端是活陷阱;`test_elevation.py:64` 把 `directionDeg==180` 钉为"正确",数值对但**把错误语义锁死**。
- **P2-B 提示注入**(并入 §二/§九):用户自由文本(手记 `strategy_note`/`hole_note`、vision `evidenceText`、球场名)以 `evidence[].text` 进入 caddie/report prompt(`decision.py:430`、`reports.py:1088`),仅经 `redact_secret_text`(只去密文/路径)、**未做指令中和**;与 P1-9 叠加,注入的中文指令可产出未被审计标记的编造建议。有界(手记截断 180 字、认证路由)。
- **P3 补充**:决策解释的幻觉检查漏掉球杆/球位/距离/危险区类别(`decision.py:411-421`,仅查天气/计分/私账);LLM 调用无重试/退避、无跨批 token/成本预算(超时是有的:HTTP 60s、weather 10s、几何子进程 180s;但 **Anthropic 客户端无显式超时**,依赖 SDK 默认)。

## 该代理进一步佐证的强项
- **投影数学经校准且自洽**:`world_to_local/local_to_world` 是基于 `cos(ref_lat)` + WGS84 赤道半径的等距圆柱线性化,往返精确、两半球均成立(cos 偶函数、经度符号处理 E/W),与 `test_projection_roundtrip.py`/`test_shot_projection.py:88-107` 手算期望一致。
- **子进程注入安全**:`subprocess.run(cmd_list,…)` 列表参数、从不 `shell=True`、每子进程 180s 超时、每洞锁避免单个挂死拖垮其他;`/ensure` admin 门禁。
- **provider 兜底全部 fail-safe**:report/decision/vision 三条路径异常均降级为确定性/uncertainty,从不 500;vision **绝不信任 provider 返回的 `confirmationState`**(强制 `unconfirmed`)、畸形 LLM JSON → uncertainty;媒体做按类大小上限 + 魔数嗅探防伪造 content-type + 路径穿越拦截。
- **密文卫生分层**:`redact_secret_text` 应用于喂 prompt 前的 facts、叙述、决策文本/refs、以及入库前的 provider 错误信息;API key 仅 env、绝不进 prompt。

## 该代理列出的"编码错误数学/误导"的测试
- **`geometry_evidence` 测试钉死了管线从不产出的形状**(`test_geometry_evidence.py:114-124`、`test_server_v2_geometry.py:192-197`、`test_gir_fairway_derivation.py:66-72` 全合成 `{"hazards":[{"polygon":…}]}`)——掩盖了 P2-q 的"生产恒空"路径,是最要害的"测试 vs 现实"缺口。
- **`test_fact_bound_reports.py` 只在英文上证明审计器**(所有 flag 断言 `:178,230,258,281,322` 喂英文;唯一中文叙述 `:35` 是良性且从不检查 `unsupportedClaims`)——因此该套件"认证"了一个在生产语言下不成立的保证(P1-9)。
- **`test_elevation.py:64` 把 `directionDeg==180` 钉为正确**——算术对,但把"未旋转 east/north 帧里的数学角"当"bearing"的语义陷阱锁死。

---

## 更新后的总览

**发布就绪:仍为不可发布(NOT READY)。** 现为 **1 个 P0 + 10 个 P1**(新增 P1-9 事实绑定语言失效)+ 约 17 个 P2 + 大量 P3。三条最应先动的:**P0-1**(公网 IPA 泄漏全权限令牌,并轮换)、**四端记分丢数据族 P1-1~4**、**P1-9**(招牌"fact-bound"在中文下失效)。八个子代理 + 我的第一手核验全部完成,彼此高度交叉印证;八方独立确认**测试套件在本沙箱内无法执行**,故全程无动态复现证据、不对任何套件下"绿"结论。其余 P0/P1/P2/P3 明细、远程状态标注、验收标准、路线图与"易被遗漏"清单见上文正报告,除本附录新增/升级的 P1-9、P2-q 外均保持不变。
