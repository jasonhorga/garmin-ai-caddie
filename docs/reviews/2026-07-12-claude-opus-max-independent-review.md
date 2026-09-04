# AI Caddie 全仓库独立工程评审(Claude Opus 4.8,最高推理强度)

> **状态:COMPLETE(10 个领域全部实际审查过;各领域的实际深度见文末覆盖清单)**
>
> 这是一次**全新的、独立的 Opus-only 重跑**。报告在评审开始时创建并逐领域增量更新。

---

## 一、运行元信息

| 项 | 值 |
|---|---|
| 评审日期 | 2026-07-12 |
| 模型身份 | `claude-opus-4-8`(Claude Opus 4.8) |
| 推理强度 | max |
| 会话性质 | **全新独立重跑(fresh Opus-only rerun)**,单会话、可审计 |
| 子代理 / 多模型 | **未使用**。全程无 Task / subagent / team / 其他模型;所有文件由本会话直接读取 |
| 分支 / HEAD | `integration/v2` @ `a0c0fca` |
| 代码规模 | Python ~85,900 行 · TS/TSX ~35,400 行 · Swift ~21,800 行 · 155 个后端测试文件 · 47 个前端测试文件 · 111 个 `.md` |
| 写入 | **只写本文件**。未改任何源码 / 测试 / 配置 / 文档 / 依赖 / git 状态 / 生成物;未 commit、未 push |

### 独立性排除项

刻意**未打开**:`docs/CODE_REVIEW_FINDINGS.md`、`docs/reviews/**`(本文件除外)、`docs/superpowers/reviews/**`,以及任何主要用途是"既往评审结论"的文件。

**一处必须披露的意外接触**:用 `grep -rn "pg_dump\|identity.db"` 做全仓库验证时,grep 结果里顺带打印出了 `docs/reviews/2026-07-11-full-repository-review.md` 的**一行**文本。我没有打开该文件,也没有读它的任何其他内容。相关结论(备份不含身份库)在跑这条 grep **之前**已经从 `docker-compose.yml` / `ops/backup_data.sh` / `ops/export_snapshot.py` 的源码独立得出,grep 只用于确认"仓库里确实没有 pg_dump"。此后所有检索均加了排除。

### 证据方法与限制

**方法**:只读生产源码的 source→sink 路径,不从注释或测试倒推行为。对影响面大的结论跑了**只读动态验证**(在进程内直接调用被审代码,不启服务、不装包、不写仓库、不产出构建物)。三次动态验证的脚本都放在 `/tmp`,未进仓库。

**明确的限制**:
- **没有跑测试套件**,没有测覆盖率,没有做依赖漏洞扫描(会需要装包)。
- **没有编译 Swift**(需要 macOS + Xcode)。iOS / Watch 的结论全部来自源码阅读,标注为 CONFIRMED 的都是逻辑上可判定的,涉及 WatchConnectivity 回调线程语义的一处标为 HIGH-CONFIDENCE。
- **没有访问生产环境**,没有看运行时日志 / 指标。
- 有一条最初的怀疑经动态验证后被**否决**(见 §9.2),另一条被**收窄**(见 §9.3)。

### 置信度与严重度

| 置信度 | 含义 |
|---|---|
| **CONFIRMED** | 源码逻辑可判定,或已用只读动态验证复现 |
| **HIGH-CONFIDENCE** | 逻辑清晰,但依赖一个未在本环境实测的平台语义(如 WCSession 回调线程) |
| **NEEDS-DYNAMIC-VERIFICATION** | 缺陷存在,但影响幅度取决于生产数据/负载,需实测 |

| 级别 | 定义 |
|---|---|
| **P0** | 正在发生的数据泄露/损坏,或产品不可用。下一次部署前必须修 |
| **P1** | 会造成用户数据永久丢失、凭据外泄、不可控成本,或核心流程直接失败。**面向公众发布前必须修** |
| **P2** | 特定条件下的正确性/完整性缺陷、可被滥用的资源消耗、明确的债 |
| **P3** | 加固、一致性、清理 |

---

## 二、执行判断(Executive verdict)

**结论:不适合面向公众发布。适合继续作为 owner 自用 + 少量家人试用。没有 P0。有 5 个 P1。**

这是一个**工程完成度远超同类个人项目**的仓库:三端(Web / iOS / Apple Watch)+ Python 后端 + 真实 Garmin 数据管道 + 几何解码与渲染 + LLM 球童,几乎每个模块都有测试,跨端契约用 JSON Schema 固化,权限模型分层清晰,而且**代码注释把"每条路由为什么这样授权"写清楚了**——这个注释质量在同规模仓库里是罕见的,它让本次评审能高效地比对"设计意图 vs 实际行为"。

问题几乎全部集中在同一条线上——**从"单人自用"走向"多人产品"的过渡没有做完**:

> 产品已经打开了「任何 Apple 用户登录即自动注册成成员」这道门(`server_v2/auth_api.py:137`),但**备份、限流、部分路由的授权表、以及 AI 报告的事实校验**都还停留在"只有 owner 一个人、只有英文、只有我自己会用"的假设上。

五个 P1 都是这条线的直接后果,而且**四个不需要攻击者**——在正常使用和正常运维中就会发生。

### 强项(应当保留的工程资产)

- **授权模型有单一事实来源,而且是"先门后体"**。`_requires_admin_token`(中间件,在 Pydantic 校验**之前**)+ `is_player_scoped_route`(成员放行表)+ `admin_request_disposition`(admin / owner / member 三态)。未授权请求根本走不到 handler(`server_v2/main.py:331-346`)。其中「合法 admin header + member bearer → 403 而不是静默提权」(`server_v2/players_api.py:200-208`)是很到位的细节。
- **数据隔离靠路径构造,不靠检查**。`evidence_root(player_id)`(`ai_caddie/core/data.py:33-41`)让成员的证据 / 媒体 / 事件日志物理上落在不同目录——隔离是构造出来的,不是"每个 handler 记得加 if"。这比检查式隔离稳健一个量级。
- **服务端实时事件日志的临界区是对的**。`fcntl.flock` 把"读序号 + 追加"包成一个真正的原子段(`ai_caddie/caddie/mobile_live.py:2376-2382`),并且注释解释了为什么必须原子。
- **启动即 fail-closed**。`ops/start_api.sh:20-41` 拒绝在 0.0.0.0 上以无鉴权姿态启动;`assert_admin_security_config()` 在 boot 时把同一个配置错误喊出来。
- **Apple 身份校验是标准的**。只验 JWKS 签名 + `aud`/`iss`/`exp` + 强制 `require` 关键 claim(`server_v2/apple_auth.py:37-57`);session token 存 SHA-256 hash 而非明文(`server_v2/identity_repo.py:147-163`);iOS 用 Keychain 存 session,admin token 只在 `#if DEBUG` 编译进去(`mobile/ios/AICaddie/Services/SessionStore.swift:107-122`)。
- **备份的导入侧路径校验写得比多数实现完整**。`ops/import_snapshot.py:20-46` 做了绝对路径 / `..` / 白名单 / resolve-后仍在-root 四重检查(经典 tar-slip 防御)。
- **跨端契约有真 JSON Schema 校验**,含 25 处真实 `Draft202012Validator` 断言,而且有**否定用例**(`_assert_json_schema_rejects`)。这在个人项目里几乎见不到。
- **手表单位一致**。`WatchUnits`(`AICaddieWatch/Design/WatchUnits.swift`)统一"内部米、显示码",与 iPhone 端一致。

---

## 三、优先级发现总表

| ID | 级别 | 置信度 | 领域 | 一句话 |
|---|---|---|---|---|
| **F-01** | **P1** | CONFIRMED | 备份 / 密钥 | 成员的 Garmin 登录 cookie 被打进备份包,而清单**硬编码** `secretFree: true` |
| **F-02** | **P1** | CONFIRMED | 备份 / 恢复 | 身份库(Postgres)完全不在备份内;从备份恢复 = 每个成员**永久**失去自己的数据 |
| **F-03** | **P1** | CONFIRMED | 安全 / 成本 | 任何 Apple 用户自动注册 + **全站零限流** + 成员可直达 LLM 端点 |
| **F-04** | **P1** | CONFIRMED(动态验证) | 授权表 | 成员在「备战」搜球场**必然 403**——一个主导航区块对成员是坏的 |
| **F-05** | **P1** | CONFIRMED(动态验证) | AI / 测试 | AI 报告的防幻觉校验在**中文(生产语言)下完全失效**,却仍盖章 `factBinding: bound` |
| **F-06** | **P2** | CONFIRMED | 数据完整性(iOS + 后端) | JSONL 追加不检查换行终止符 → 崩溃后**已成功记录的那一杆会被销毁** |
| **F-07** | **P2** | HIGH-CONFIDENCE | 手表 | 手表离线队列是**无锁的 read-modify-write** → ack 在途时记的杆可能静默丢失 |
| **F-08** | **P2** | CONFIRMED | 手表 | 手表→手机**只用 `sendMessage`**(要求可达),没有 `transferUserInfo` 兜底(手机→手表**有**) |
| **F-09** | **P2** | CONFIRMED | 数据完整性 | 手动记分 ingest 的幂等是 check-then-act,无锁 + 非原子写 → 并发重试产生**重复球局** |
| **F-10** | **P2** | CONFIRMED | 统计正确性 | 差点估算把**两种不同量纲**(rated differential / score-par)混在一起取分位数 |
| **F-11** | **P2** | CONFIRMED | 部署陷阱 | owner 首次 Apple 登录若 email 未命中白名单,会被**永久且不可逆**地注册成 member |
| **F-12** | **P2** | CONFIRMED | CI | `ci.yml` **只在 `pull_request` 触发**,合并后 / 主干上从不跑 → 部署源分支从未被整体验证 |
| **F-13** | **P2** | CONFIRMED | 资源耗尽 | `POST /courses/{gid}/topo/prewarm` **完全无鉴权**,可扇出后台重渲染 |
| **F-14** | **P2** | CONFIRMED | 性能 / 伸缩 | 实时事件日志每次追加都**全文件重读重解析**,且永不轮转 → O(n²) |
| **F-15** | **P2** | CONFIRMED | 契约演进 | 后端与 iOS/Watch 之间**没有 schema 版本协商**;旧 app + 新后端 = 硬解码失败 |
| **F-16** | **P2** | CONFIRMED | 会话 | `/auth/refresh` 两端都实现了但**从未被调用**;iOS 也没有 401 处理 |
| **F-17** | **P2** | CONFIRMED | 测试质量 | 「完全就绪」的 live-round package 只被一个**手写的、残缺的** schema 检查器验证 |
| **F-18** | **P2** | CONFIRMED | 部署 | `docker-compose.yml` 的 `web` 服务是 Vite **dev server**,且监听 `0.0.0.0:5173` |
| **F-19** | **P2** | HIGH-CONFIDENCE | 安全加固 | `player_id` 路径参数未做格式校验就进文件系统路径 |
| **F-20** | **P3** | CONFIRMED | 供应链 | `superfly/flyctl-actions/setup-flyctl@master` 未固定版本;无 dependabot / 漏洞扫描 |
| **F-21** | **P3** | CONFIRMED | 会话 | refresh 无绝对寿命上限;`token_revocations` 表单调增长无清理 |
| **F-22** | **P3** | CONFIRMED | 性能 | 每个受门控请求做 **2 次**完整鉴权(各含一次磁盘读 + 一次 DB 查询) |
| **F-23** | **P3** | CONFIRMED | 数据完整性 | 玩家注册表 / ack 存储:无锁 read-modify-write + 非原子 `write_text` |
| **F-24** | **P3** | CONFIRMED | iOS 加固 | Keychain 条目未设 `ThisDeviceOnly`(会进 iCloud 备份);`SecItemAdd` 返回值被忽略 |

---

## 四、P1 详细证据

### F-01(P1 · CONFIRMED)成员 Garmin 登录 cookie 被打进"声称无密钥"的备份包

**触发**:任何一次 `ops/backup_data.sh`(README.md:92 把它列为常用运维入口),只要有任何成员绑定过 Garmin。

**source → sink**

1. 成员经 `POST /api/v2/players/{player_id}/sync/garmin/session` 绑定(`server_v2/main.py:1338-1350`)。
2. `server_v2/session.py:29` → `garmin_token_dir(player_id, SESSION_ROOT)`;`ai_caddie/connectors/garmin_cn.py:71-79`:
   ```python
   def garmin_token_dir(player_id, root=ROOT) -> Path:
       if player_id is None or player_id == OWNER_ID:
           return root / ".garmin_tokens"                              # owner:data/ 之外
       return root / "data" / "players" / player_id / ".garmin_tokens"  # 成员:data/ 之内 ←
   ```
3. `ai_caddie/connectors/session_material.py:65-74` 把**原始 cookie 头 + CSRF 明文落盘**:
   ```python
   web_session_path.write_text(web_session + "\n", encoding="utf-8")
   anti_forgery_path.write_text(anti_forgery + "\n", encoding="utf-8")
   ```
4. `ops/export_snapshot.py:11-25` 的备份清单**整个收 `data/players`**;`ops/export_snapshot.py:57-67` 的 `_iter_regular_files` 用 `os.walk` 递归收所有普通文件,**没有任何排除规则**(只跳过符号链接)→ `data/players/<pid>/.garmin_tokens/web_session` **进 tar**。
5. `ops/export_snapshot.py:95` 与 `ops/backup_data.sh:35` 都**硬编码** `"secretFree": True`——这个字段不是算出来的,是写死的。

**为什么 owner 没事、成员有事**:owner 的 cookie 在 `ROOT/.garmin_tokens`(`data/` 之外),不在 `DATA_PATHS` 里。**多人分区重构把成员的 cookie 移进了 `data/` 之内,备份清单没跟着改。** 典型的"隔离机制上线、周边系统没跟上"。

**影响**:Garmin Connect CN 的 web session cookie 是该成员 **Garmin 账号的完整凭据**(不止高尔夫数据)。备份包按设计要拷出机器;清单上的 `secretFree: true` 会让运维/自动化误判为可放低信任存储。

**现有缓解**:落盘时 0600/0700(进 tar 后失效)。

**缺失的测试**:没有任何测试断言快照**不含** `.garmin_tokens`。现有快照测试只验证"包含了什么",没有验证"排除了什么"。

**修法**:`_iter_regular_files` 显式排除 `.garmin_tokens` / 所有 dotdir;把 `secretFree` 改成**扫描后计算**(扫到敏感文件就置 false 或直接非零退出)。

---

### F-02(P1 · CONFIRMED)身份库不在备份内 → 恢复即永久失去所有成员的数据归属

**触发**:任何一次真实灾难恢复(换机 / 卷损坏 / 误删)。

**证据**

1. 生产用 Postgres,数据在**独立的卷** `ai-caddie-pgdata`(`docker-compose.yml:36,49,74`),和 API 的 `ai-caddie-private` 卷是两个卷。
2. `ops/backup_data.sh` 只做一件事:调 `ops/export_snapshot.py` 打包**文件树**。
3. `ops/export_snapshot.py:11-30` 的 `DATA_PATHS` / `GEOMETRY_OUTPUT_PATHS` **不含任何数据库**。
4. 全仓库检索:**没有任何 `pg_dump`**。

**为什么是永久性数据丢失,而不只是"要重新登录"**

成员数据全在 `data/players/p_<16位hex>/`(`ai_caddie/rounds/round_ingest.py:54`、`ai_caddie/caddie/mobile_live.py:2211`、`ai_caddie/core/data.py:41`)。而 `p_<hex>` ↔ Apple `sub` 的绑定**只存在于 Postgres**:

- `server_v2/identity_models.py:44-52` `UserIdentity(provider, subject)` — Apple sub → user
- `server_v2/identity_models.py:55-59` `LegacyPlayerMap(legacy_player_id → user_id)` — user → `p_*`

恢复流程:文件树回来了 → `data/players/p_abc…/` 里躺着该成员全部球局/球杆/事件/报告 → 但 Postgres 是空的 → 成员 Apple 登录 → `get_user_by_apple_subject` 返回 None(`server_v2/auth_api.py:114`)→ 走到 `server_v2/auth_api.py:139-153` 的自动注册 → `pid = "p_" + secrets.token_hex(8)` **生成一个全新的随机 pid** → 成员进入一个**完全空的账号**;他原来的数据成为**无主孤儿目录,没有任何途径能重新关联**(Apple sub → pid 的映射不存在于任何其他地方)。

**影响**:每一个成员,100% 数据不可达。owner 不受影响(`OWNER_ID = "me"` 是常量,数据在扁平根)。

**缺失的测试**:`tests/test_deployment_manifests.py` 存在,但不断言备份覆盖身份库;**没有任何恢复演练测试**。

**修法**:`backup_data.sh` 加 `pg_dump`(SQLite 部署则加 `data/identity.db`),纳入同一 manifest 的 sha256;加一条端到端演练——"备份 → 全新环境恢复 → 成员用同一个 Apple sub 登录 → 拿回原 pid"。

---

### F-03(P1 · CONFIRMED)自动注册 + 零限流 + 成员可直达 LLM = 无上限的第三方成本

**触发**:任何拥有 Apple ID 的人拿到 app,登录一次。

1. **门是开的**(有意的产品决策,不是 bug)。`server_v2/auth_api.py:137-165`:首次见到的 Apple `sub` → `provision_member(...)` → 直接发 session。唯一边界是 identity token 的 `aud` 等于配置的 bundle id——也就是"**任何装了这个 app 的人**"。
2. **成员能打到 LLM**。`server_v2/players_api.py:285-309` 明确把这些 POST 列为成员可用:
   ```python
   or path == "/api/v2/caddie/decision"
   or (path.startswith("/api/v2/media/") and (path.endswith("/analyze") or path.endswith("/redact")))
   or (path.startswith("/api/v2/reports/") and path.endswith("/generate"))
   ```
   最终落到 `ai_caddie/llm/llm_providers.py:151 / 265 / 311` 的出站调用,用的是 **owner 环境变量里的 API key**(`docker-compose.yml:29-33`),单次最多 1800 output tokens、60s 超时。
3. **没有任何限流**。全仓库检索 `ratelimit|rate_limit|slowapi|limiter|throttl` 在 `server_v2/` 与 `ai_caddie/` 生产代码里**零命中**。中间件只有三个:admin 门、`Referrer-Policy`、`Content-Length` 上限(`server_v2/main.py:331-377`)。
4. **body 上限 160MB**(`server_v2/main.py:361`),媒体有按类型的单文件上限(`ai_caddie/core/media.py:19-23`),但**没有任何按人/按时间窗的配额**。

**影响**:不可控的第三方 LLM 花费(计在 owner 账上)+ 成员分区的磁盘无限增长 + `/reports/*/generate` 触发完整统计构建的 CPU。

**现有缓解(重要)**:`AI_CADDIE_LLM_PROVIDER` 默认 `static`(`docker-compose.yml:26`)。**如果 owner 没配 LLM key,今天就没有真实成本**——这把"当前实际风险"从 P0 压到 P1。但 AI 球童就是产品的核心卖点,一旦开真 provider,风险立即实体化。

**修法**:按 `player_id` 的令牌桶 + 每日预算熔断;把自动注册改成邀请制,或给新成员一个低配额档。

---

### F-04(P1 · CONFIRMED,动态验证)成员在「备战」搜球场必然 403

**动态验证**(进程内直接调用后端的两个路由分类函数,只读、不启服务):

```
METHOD PATH                                 admin-gated  member-allowed => 成员结果
GET    /api/v2/courses/search               True         False          => 403 (forbid)
GET    /api/v2/courses/41825/prep           True         True           => OK
POST   /api/v2/courses/41825/topo/prewarm   False        False          => 公开(无鉴权)
```

**根因:两张表不一致。**

- `server_v2/main.py:288` 把 `/api/v2/courses/search` 放进**需要 admin token** 的 GET 列表。
- `server_v2/players_api.py:255-284` 的成员放行表里,`/api/v2/courses/` 只放行了 `/prep` 和 `/prep-tips`,**没有 `search`**。
- 于是 `server_v2/main.py:338-343` → `player_token_allows = False` → `enforce_admin_or_owner` → `admin_request_disposition` 认出这是 member bearer → `"forbid"` → **403**。

**为什么用户一定会撞上**:`web_v2/src/components/PrepPage.tsx:215-226`——没选球场时,备战页的**整个空状态就是** `CourseFinder`("选择球场开始备战"),而「备战」是 5 个主导航区块之一(`web_v2/src/navigation.ts:24,50`),对成员没有任何屏蔽。`web_v2/src/api.ts:405-408` 的 `searchCourses` 会带成员 session bearer;`adminTokenHeader`(`web_v2/src/api.ts:117-130`)对成员**刻意不发** admin token(这个客户端防护本身是对的)。同一个搜索也被 `LiveSandbox`(球童沙盘)使用。

**为什么这个 bug 能活下来**:iOS **不调** `/courses/search`(检索确认),它走 `/api/v2/mobile/courses/options`(该路由**在**成员放行表里)。主力真机流程绕开了它。

**缺失的测试**:现有的路由策略测试(`test_aggregator_route_isolation.py` / `test_analysis_route_guards.py`)只从**"不该访问的要挡住"**这一侧写。**缺对称的另一侧**——"成员对每个应当可用的路由都能 200"。这正是本 bug 的测试盲区,也是最该补的一条。

---

### F-05(P1 · CONFIRMED,动态验证)AI 报告的防幻觉校验在中文下完全失效,却仍盖章"已绑定事实"

这是本次评审**最值得注意**的一条:一个**主动给出虚假安全信号**的机制。

**机制**

`generate_report`(`ai_caddie/reports/reports.py:2600-2606`)的提示词明确要求中文输出:
```python
prompt = (
    "用简体中文撰写基于证据的高尔夫复盘。仅使用 factsUsed 中的事实。"
    "不得编造天气、谎言、意图、球杆、罚杆或私人数据。..."
)
```

而防幻觉校验器 `_UNSUPPORTED_CLAIM_RULES` / `_CATEGORY_MENTION_PATTERNS`(`ai_caddie/reports/reports.py:157-201`)**全部是英文关键词 + `\b` 词边界**:
```python
"weather": re.compile(r"\b(weather|wind|rain|temperature|precipitation|gusts?)\b", re.IGNORECASE),
"club":    re.compile(r"\b(club|driver|wood|iron|wedge|putter|hybrid)\b", re.IGNORECASE),
...
```

中文叙述里没有 `wind` / `club` 这些词 → 没有任何 category 被"提及" → `unsupported_claims` 恒为 `[]` → `_report_payload`(`ai_caddie/reports/reports.py:2295-2298`) 输出 **`"factBinding": {"state": "bound", "unsupportedClaimCount": 0}`**。

**动态验证**(同一条"编造逆风"的断言,只换语言):

```
EN            unsupportedClaims=[{'category': 'causal_claim', ...}]
              factBinding={'state': 'needs_review', 'unsupportedClaimCount': 1}

ZH(生产语言)   unsupportedClaims=[]
              factBinding={'state': 'bound', 'unsupportedClaimCount': 0}
```

**为什么测试是绿的(根因)**:`tests/test_fact_bound_reports.py` 用 `StaticProvider("<英文文本>")` 驱动 `generate_report`——套件里每一条 narrative 都是**英文**("trend narrative"、"identity review"、"stored review"…)。测试在一个**生产系统从不产出的语言**上验证这条代码路径。这是一个结构性盲点,不是漏写一个用例。

**影响**
- 产品的核心差异化(README.md:136「fact-bound AI review」)在**唯一可能产生幻觉的路径上没有生效**。
- 更糟的是它**不是"没检查",而是"检查了并声明通过"**——`factBinding: bound` 是一个会被 UI 渲染成信任标识的字段。**虚假的安全信号比没有信号更危险。**
- 生效范围:`server_v2/reports.py:170, 206, 222` 的 round / course / hole 报告生成端点(`_generate_provider_report_or_fallback` → `generate_report(facts, build_text_provider())`)。

**现有缓解**:`AI_CADDIE_LLM_PROVIDER` 默认 `static`,narrative 是固定串 "AI Caddie fixture response"——今天要么 AI 复盘等于关着,要么(一开真 provider)校验就是死的。两种状态都不可接受,但**当前没有正在发生的幻觉**,所以是 P1 而非 P0。

**注**:球童决策解释(`ai_caddie/caddie/decision.py:424-429`)的提示词是**英文**,其校验器(`_decision_unsupported_claims`,`ai_caddie/caddie/decision.py:411-421`)也是英文——那一条是**自洽的**,校验确实会触发。问题只出在报告的中文路径上。

**修法**:(a) 校验器换成中英双语词表(或改用"事实覆盖率"式的结构化校验而非关键词匹配);(b) 在 `tests/test_fact_bound_reports.py` 里**加一条中文 narrative 的否定用例**——这一条测试就能永久钉死这个回归。

---

## 五、P2 详细证据(重点项)

### F-06(P2 · CONFIRMED)JSONL 追加不检查换行终止符 → 崩溃销毁"已经记好的那一杆"

**同一个根因,同时存在于服务端和 iOS 端**,而且都在记杆路径上。

**iOS**(`mobile/ios/AICaddie/Services/OfflineStore.swift:225-240`):
```swift
let handle = try FileHandle(forWritingTo: logURL)
try handle.seekToEnd()
try handle.write(contentsOf: encoded)      // ← 写 JSON
try handle.write(contentsOf: Data([0x0A])) // ← 再写换行(两次独立 write)
```

代码在 `loadEvents`(`mobile/ios/AICaddie/Services/OfflineStore.swift:256-260`) 里承认了非原子性,并给出一个**保证**:
> "Losing at most that one half-written event keeps every prior recorded score intact."(最多丢那一条半写的事件,之前记录的每一杆都完好)

**这个保证是错的。** 如果 iOS 在写完 JSON、还没写换行时杀掉 app(jetsam;记一杆之后正好开相机/地图时极可能),文件末尾就是**一条完整但没有换行的 JSON**。下一次 `appendEvent` 直接 `seekToEnd()` 往这一行**后面接着写**:

```
{完整的事件1}{完整的事件2}\n     ← 一个物理行,无效 JSON
```

`loadEvents` 跳过坏行 → **事件 1(一条已经成功落盘、之前能读出来的杆)和事件 2 一起消失。**

**服务端**(`ai_caddie/caddie/mobile_live.py:2416-2439`)是同一个形状:`with path.open("a")` 逐行 `handle.write(json + "\n")`,同样不检查末尾终止符。进程被杀(OOM / `docker compose down` / 部署重启)后,手表/手机 POST 的**第一条**事件会被接到残行上,整行变成无效 JSON 被所有 reader 丢弃——而 API 已经返回了 `accepted: 1` 和一个 `serverSequence`(`ai_caddie/caddie/mobile_live.py:2440-2446`),客户端据此 ack 并**删掉本地队列里的那条,不会重传**。

**影响**:对一个"记录每一杆"的产品,这是最不该有的失败模式——**不报错、不重试、不可见**,而且销毁的是**已经成功记录**的数据。

**触发窗口**:两次 `write` 之间。窄,但 iOS jetsam 是异步的,长期一定会撞上。损害有界(2 条事件),但其中一条是用户已经记好的成绩。

**缺失的测试**:两端都没有"日志尾部无换行 → 再追加 → 旧记录仍可读"的用例。

**修法(两端各一行)**:追加前检查最后一个字节是不是 `\n`,不是就先补一个。

---

### F-07 / F-08(P2)手表离线队列:无锁竞态 + 缺少可靠传输兜底

**F-08(CONFIRMED)传输不对称。**

- **手机 → 手表**(`mobile/ios/AICaddie/Services/WatchEventBridge.swift:439-444`)做对了:
  ```swift
  if WCSession.default.isReachable {
      WCSession.default.sendMessage(["state": object], replyHandler: nil)
  } else {
      WCSession.default.transferUserInfo(["state": object])   // ← 排队、有序、保证送达
  }
  ```
- **手表 → 手机**(`mobile/ios/AICaddieWatch/Services/WatchSyncClient.swift:270`)**只用 `sendMessage`**,没有 `transferUserInfo` 兜底。而 `sendMessage` 要求对端**当前可达**——球场上手机通常在包里/车上、屏幕锁着,`isReachable` 大部分时间是 false。

于是手表用**自己手写的文件队列**去重新实现 `transferUserInfo` 本来免费提供的保证……并且实现里有竞态。

**F-07(HIGH-CONFIDENCE)队列是无锁的 read-modify-write。**

`mobile/ios/AICaddieWatch/Services/WatchSyncClient.swift` 里**没有任何 lock / serial queue / actor / `@MainActor`**(全文只有两处 `DispatchQueue.main.async` 用于 UI 发布)。而两条路径都对同一个 JSON 文件做"读→改→写":

```swift
public func queueInputEvent(_ event: WatchInputEvent) throws {   // mobile/ios/AICaddieWatch/Services/WatchSyncClient.swift:180-189,UI 线程(用户点击)
    var events = try loadQueuedEvents()
    guard !events.contains(where: { $0.eventId == event.eventId }) else { return }
    events.append(event)
    try writeQueuedEvents(events)
}

private func removeAcknowledgedEventIds(_ eventIds: Set<String>) throws {  // mobile/ios/AICaddieWatch/Services/WatchSyncClient.swift:229-238,WCSession 回调线程
    let remaining = try loadQueuedEvents().filter { !eventIds.contains($0.eventId) }
    try writeQueuedEvents(remaining)
}
```

`sendMessage` 的 `replyHandler` / `errorHandler` 由 WatchConnectivity 在**后台队列**回调(这是我标 HIGH-CONFIDENCE 而非 CONFIRMED 的唯一原因——平台语义未在本环境实测)。因此:

- ack 回调线程:`load [e1,e2,e3]` → 过滤掉 e1 → 准备写 `[e2,e3]`
- 同时 UI 线程:用户点"记一杆" → `load [e1,e2,e3]` → append e4 → 写 `[e1,e2,e3,e4]`
- 若 ack 的写**后落地** → 队列变成 `[e2,e3]` → **e4 永久丢失**

`.atomic` 写只保证文件不撕裂,**不消除丢失更新**。而 `flushQueue`(`mobile/ios/AICaddieWatch/Services/WatchSyncClient.swift:251-259`)会在一个紧循环里对每条事件发 `sendMessage`,让多个 ack 几乎同时回调——把竞态窗口开到最大。

队列也**没有上限**(`queueInputEvent` 无限 append)。

**修法**:(a) 手表→手机改用 `transferUserInfo`(排队、有序、保证送达),本地队列只作为二级兜底;(b) 把 `WatchSyncClient` 的队列操作放进一个串行队列或标成 actor。

---

### F-09(P2 · CONFIRMED)手动记分 ingest 的幂等在并发下失效,且四处非原子写

`ai_caddie/rounds/round_ingest.py:606-659` 是一个教科书式的 check-then-act,**全程无锁**(对比:同仓库的 `append_event_batch` 用了 `fcntl.flock`,说明作者知道该怎么做):

```python
index = _load_index(player_id, root)                    # 606 读
if index["entries"].get(idempotency_key) is not None:   # 607-609 判
    return {...}
round_id = _allocate_round_id(idempotency_key, scorecards_dir)   # 622
(scorecards_dir / f"{round_id}.json").write_text(...)   # 638 写
...
_save_index(index, player_id, root)                     # 659 写
```

两个带**同一个 Idempotency-Key** 的并发请求:A、B 都在 606 读到"没有这个 key"。A 在 638 写下 `<base>.json`。B 此时才跑到 622(`ai_caddie/rounds/round_ingest.py:97-103`):

```python
def _allocate_round_id(idempotency_key, scorecards_dir):   # ai_caddie/rounds/round_ingest.py:97-103
    base = int(hashlib.sha256(...).hexdigest()[:12], 16)
    rid = base
    while (scorecards_dir / f"{rid}.json").exists():   # ← 看到 A 刚写的文件
        rid += 1                                        # ← 换一个 id
    return rid
```

B 换成 `base+1` → **写出第二份球局**。同一个幂等键,两条球局 → 统计(杆数 / 差点 / GIR)全部**双算**,而用户看不出是重复。

**次生:仓库里明明有 `atomic_write_json`(`ai_caddie/core/data.py:66-77`,temp + `os.replace`),ingest 路径却全用裸 `write_text`**——`_save_index`(`ai_caddie/rounds/round_ingest.py:93-94`)、`_update_summary`(`ai_caddie/rounds/round_ingest.py:571-572`)、以及 638/641 的 scorecard/shots。写 `_save_index` 时被杀 → 台账截断 → `_load_index`(`ai_caddie/rounds/round_ingest.py:88-90`) 的 `except Exception: pass` **静默降级成空台账** → 之后所有重试都被当成新球局 → **重复球局批量产生**。

**缺失的测试**:`tests/` 里的幂等测试全是**串行**的(先 POST 再 POST);没有并发用例,也没有"台账被截断后仍幂等"的用例。

---

### F-10(P2 · CONFIRMED)差点估算把两种量纲混在一起取分位数

`ai_caddie/history/history_stats.py:544-564`:

```python
def _handicap_estimate(rounds):
    rated = [(date, d) for row in rounds if (d := _round_differential_or_par(row)) is not None]
    ...
    recent = [d for _day, d in rated[:20]]
    take = math.ceil(0.4 * len(recent))
    lowest = sorted(recent)[:take]              # ← 取最低的 40%
    return round(sum(lowest) / len(lowest) * 0.96, 1)
```

`_round_differential_or_par`(`ai_caddie/history/history_stats.py:514-541`)返回的是**两种不同量纲之一**:

- 有 rating/slope → WHS differential:`(score - rating) * 113 / slope`(`_round_differential`(`ai_caddie/history/history_stats.py:248-254`))
- 没有 → 回退到 `score - par`

**这两个数在难球场上差很多。** 例:rating 74.5 / slope 135 / par 72,打了 90 杆:
- rated differential = `(90 - 74.5) * 113 / 135` = **12.98**
- score − par = `90 - 72` = **18.0**

`sorted(recent)[:take]` 取**最低的 40%** —— 这个顺序统计量会**系统性地优先选中 rated 的那批**(在难球场上它们数值更低),把差点**低估**。上例中,20 场全 unrated 得 17.3,混入 rated 后可以掉到 12.5——**接近 5 杆的偏差,纯粹由"哪些球局碰巧带了 rating 元数据"决定。**

**最有说服力的证据是代码自己的注释**。`_round_differential_or_par` 的 docstring(`ai_caddie/history/history_stats.py:520-521`)写着:

> "byMonth `averageDifferential`(图表曲线)**保持只用 rated**,因为把两种量纲混进一条曲线会误导。"

作者**识别出了这个危险,并在图表上规避了它,却没有把同样的推理应用到差点本身**——而差点恰恰是量纲混合破坏力最大的地方(因为它取的是顺序统计量,不是平均值)。

**影响**:「差点(估算)」是产品的门面数字之一,而"Garmin 的统计太弱"正是这个产品存在的理由。

**幅度需实测(NEEDS-DYNAMIC-VERIFICATION)**:取决于 owner 数据里 rated / unrated 的实际比例。逻辑缺陷本身是 CONFIRMED。

---

### F-11(P2 · CONFIRMED)owner 首次 Apple 登录可能被**永久且不可逆**地注册成 member

`server_v2/auth_api.py:122-136`:owner 身份的**唯一获取途径**是首次登录时 Apple identity token 里的 `email` claim 命中 `AI_CADDIE_ADMIN_APPLE_EMAILS` 白名单。

两条都会让它失手:

1. **`.env.example` 里根本没有 `AI_CADDIE_ADMIN_APPLE_EMAILS`**(`docker-compose.yml:15` 传了它,但模板没列)。照着 `.env.example` 部署的人,这个变量是空的。
2. 就算配了,如果 owner 在 Apple 登录时选了 **"隐藏我的邮件"**,`email` claim 会是 `…@privaterelay.appleid.com` 的中继地址,**匹配不上白名单**。

任一情况下,owner 的 sub 走到 `server_v2/auth_api.py:137-153` 的自动注册 → 被建成 **member**。

**而且不可逆**:`link_apple_identity`(`server_v2/identity_repo.py:99-108`)在 sub 已绑到别的 user 时**拒绝改绑**(`IdentityConflictError`),`/auth/apple/link` 也会因此 409。**恢复只能靠手工改数据库。**

**修法**:`.env.example` 补上该变量;更根本地,把 owner 引导改成一次性的 bootstrap token 或"第一个登录的人是 owner",不要依赖一个**用户可以选择不提供**的 claim。

---

### F-12(P2 · CONFIRMED)合并后 / 主干上没有 CI

`.github/workflows/ci.yml:3-5`:
```yaml
on:
  workflow_dispatch:
  pull_request:
```

**没有 `push:`。** 所以 `integration/v2`(部署源分支)在合并之后**从来没有被整体跑过一次**。PR 各自绿灯不等于合并结果绿灯(base 漂移、语义冲突、跨 PR 的契约不一致都逃得掉),而 `gh pr merge` 并不强制检查。

`.github/workflows/native-mobile.yml:5-10` 还有 `paths:` 过滤,只在 `mobile/ios/**` 变更时触发——**改 `mobile/contracts/*.schema.json`(跨端共享契约!)或 `server_v2/models.py` 都不会触发 iOS/Watch 的编译与测试**。契约漂移对 CI 是隐形的。

**修法**:给 `ci.yml` 加 `push: branches: [integration/v2]`;把 `native-mobile.yml` 的 `paths` 扩到 `mobile/contracts/**` 和 `server_v2/models.py`。

---

### F-15(P2 · CONFIRMED)后端与 iOS/Watch 之间没有 schema 版本协商

每个 payload 都带 `"schema": "ai-caddie-live-round-package-v1"`,但**没有任何客户端检查它**——检索确认 iOS/Watch 里 `schema` 只作为 `Codable` 的一个默认值出现(`mobile/ios/AICaddie/Models/LiveRoundPackage.swift:41`),从不比对。

后端在 homeserver 上独立部署,iOS 走 TestFlight / App Store,**必然有一条长期不更新的旧版本尾巴**。一旦后端改了必填字段的形状:旧 app 的 Swift `Codable` 解码直接失败 → 用户看到一个无法理解的错误,没有"请更新 app"的路径,也没有降级路径。

**修法**:客户端校验 `schema` 前缀并在不匹配时给出明确的"请更新"提示;或后端按 `Accept-Version` / query 做版本分发。

---

### F-16(P2 · CONFIRMED)会话刷新两端都写好了,但从来没接上

- 后端有 `POST /api/v2/auth/refresh`(`server_v2/auth_api.py:182-198`),而且实现得很讲究(在一个事务里 mint + revoke,保留原 scope 防止把 `watch` session 洗成 `user`)。
- iOS 有 `AppleAuthClient.refresh(token:)`(`mobile/ios/AICaddie/Services/AppleAuthClient.swift:44`)。
- **但检索确认:除定义外没有任何调用点。**

后果:session TTL 默认 720 小时(30 天,`server_v2/auth_api.py:60`),到期后 `SessionStore.liveToken` 返回 nil(`mobile/ios/AICaddie/Services/SessionStore.swift:69`)→ Release 构建下 `applyAICaddieAuth` **不加任何 auth 头**(`mobile/ios/AICaddie/Services/SessionStore.swift:107-122`)→ 所有请求 401。而 **iOS 里没有任何 401 处理**(检索确认,只有 `mobile/ios/AICaddie/Services/SyncClient.swift:85` 一句提到 401 的注释)——不会触发重新登录,只会一路报错。

顺带:`.env.example:19` 写的是 `AI_CADDIE_SESSION_TTL_HOURS=24`(**24 小时**),与 `server_v2/auth_api.py:57-60` 注释里"长 TTL 免得天天重登"的意图矛盾;而 `docker-compose.yml` 的 environment 块**根本没有转发这个变量**,所以在 compose 下它是无效配置。

---

### F-17(P2 · CONFIRMED)「完全就绪」的 live-round package 只被一个残缺的手写校验器检查

`tests/test_mobile_contracts.py` 里有**两个**校验助手:

- `_assert_json_schema_accepts` / `_assert_json_schema_rejects`(`tests/test_mobile_contracts.py:74-81`)——**真的**,用 `Draft202012Validator`。
- `_assert_schema_accepts`(`tests/test_mobile_contracts.py:33-71`)——**手写的、残缺的** JSON Schema 子集实现。

**必须澄清(我最初的怀疑被收窄了)**:真校验器**确实在用**,25 处调用,而且带否定用例(`_assert_json_schema_rejects`,如 `tests/test_mobile_contracts.py:954-962`、`tests/test_mobile_contracts.py:999-1000`)。**契约测试整体是强的。**

但有一处例外:**`tests/test_mobile_contracts.py:483`**——`test_..._ready_package`,即 `offlinePackageStatus.state == "ready"` 的**完全就绪**包(字段最全、正是 iOS 在一切正常时解码的**主力形状**)——**只**被 `_assert_schema_accepts` 校验,后面没有跟真校验器。

而手写校验器忽略了四个 schema **实际都在用**的特性:`$ref` / `$defs`(`live_round_package` 用了)、`additionalProperties`(四个都用了)、`allOf`、`pattern`、`minimum`、`format`、可空联合类型。它还有一条 `if key not in properties: continue`——**payload 里出现 schema 未定义的字段会被直接跳过**。

**影响**:恰恰是生产主力形状上,契约没有被真正校验。**修法是一行**(把 `tests/test_mobile_contracts.py:483` 换成 `_assert_json_schema_accepts`),并删掉那个手写助手——它现在是个陷阱。

---

### F-13 / F-14 / F-18 / F-19(P2,简述)

- **F-13 `POST /api/v2/courses/{gid}/topo/prewarm` 完全无鉴权**(动态验证)。`server_v2/main.py:724-743` 定义,`_requires_admin_token` 的 POST 分支既不在 `exact_paths` 也不匹配任何 `protected_prefix_suffix`,handler 也没有 `Depends(current_player_id)`。它会给该球场每个有几何的洞排一次后台渲染(注释称首渲 **~6–10 秒/洞**),而 `ops/start_api.sh:46` 是**单进程 uvicorn**。`web_v2/src/api.ts:105-109` 注释明说"no auth needed",所以是**有意为之**——但意图和风险不匹配。缓解:`server_v2/main.py:735` 过滤掉没有 mesh 的洞,所以乱填 gid 排 0 个任务。
- **F-14 实时事件日志 O(n²) 且永不轮转**。`append_event_batch`(`ai_caddie/caddie/mobile_live.py:2386-2401`)在 flock 临界区里**把整个 `events.jsonl` 读进内存逐行 `json.loads`**,只为重算序号和两个去重集合。同样的全文件扫描也发生在 `_event_log_rows`(`ai_caddie/caddie/mobile_live.py:2226-2251`),它被 `/state`、`/replay`、`/reconciliation`、round package 各调一次(有的一次请求调多次)。日志**从不按球局切分、不轮转、不压实**。
- **F-18 `docker-compose.yml:56-70` 的 `web` 服务是 Vite dev server**(`npm run dev -- --host 0.0.0.0`),端口映射 `5173:5173` **不带 `127.0.0.1` 前缀**(而 `api` 服务是带的)。README.md:99 把 `docker compose up --build` 作为容器化入口。
- **F-19 `player_id` 路径参数未校验就进文件系统路径**。四个路由(`server_v2/main.py:471/589/601/1338`)把 URL 里的 `player_id` 原样传进 `evidence_root` / `manual_club_bag_file` / `garmin_token_dir` / `round_ingest._player_dir`。每个 handler 都有 `if acting != OWNER_ID and acting != player_id: 403`,所以**成员只能传自己的 id**;owner 可以传任意字符串。我没有做穿越 PoC(会需要写文件,超出只读范围),所以标 HIGH-CONFIDENCE。**真正的问题不是"能不能穿越",是防线站错了地方**:整个隔离模型建立在 `evidence_root(player_id)` 的**路径构造**上,那就应该在 `evidence_root` 入口做一次集中的 `^(me|p_[0-9a-f]{16})$` 校验。低成本、高价值的收口。

---

## 六、跨端契约分析(领域 7)

**做得好的**:`mobile/contracts/` 下 4 个 JSON Schema 是三端共享的单一事实来源,后端在 `tests/test_mobile_contracts.py` 里用真 `Draft202012Validator` 对**真实构建出来的 payload**(不是手写的假数据)做校验,并且有否定用例。`tests/test_mobile_contracts.py` 还会 grep iOS 源码断言控件/wiring 存在——一种务实的"跨语言契约锁"。

**四个缺口**:

| 缺口 | 证据 | 后果 |
|---|---|---|
| 没有版本协商 | 客户端从不检查 `schema` 字段(F-15) | 旧 app + 新后端 = 硬解码失败,无降级路径 |
| 主力形状未被真校验 | `tests/test_mobile_contracts.py:483`(F-17) | ready package 的契约实际上没锁住 |
| CI 不覆盖契约变更 | `.github/workflows/native-mobile.yml:5-10` 的 `paths` 不含 `mobile/contracts/**`(F-12) | 改 schema 不触发 iOS/Watch 编译测试 |
| 授权表在两处手写、会漂移 | `server_v2/main.py:265-328` vs `server_v2/players_api.py:222-310`(F-04 的根因) | 两张表不一致 → 成员被 403 |

最后一条值得单独说:`_requires_admin_token` 和 `is_player_scoped_route` 是**两张手写的、必须保持一致的路径表**。F-04 就是它们漂移的产物。**这是一个结构性风险,不是一次疏忽**——应该合并成一张声明式的路由策略表(每条路由一行:`{path, method, who}`),再由两个函数从同一张表推导。

---

## 七、测试缺口矩阵(领域 9)

| 领域 | 现状 | 关键缺口 |
|---|---|---|
| 后端单测 | 155 个文件,unittest,CI 跑 `unittest discover` | — |
| 路由授权 | 有(`test_aggregator_route_isolation` / `test_analysis_route_guards` / `test_evidence_isolation` …) | **只测"该挡的挡住了",不测"该放的放行了"** → F-04 逃逸 |
| 幂等 | 有,但**全是串行的** | 无并发用例;无"台账被截断后仍幂等"用例 → F-09 逃逸 |
| 崩溃一致性 | 无 | 无"日志尾部无换行 → 再追加"用例(两端)→ F-06 逃逸 |
| 备份 | 有(验证"包含了什么") | **不验证"排除了什么"**(→ F-01);**无恢复演练**(→ F-02) |
| 防幻觉 | 有,但**只喂英文 narrative** | **无中文 narrative 用例** → F-05 逃逸(这是最典型的"测试在验证一个生产从不产出的形状") |
| 跨端契约 | 强(25 处真校验 + 否定用例) | ready package 只被弱校验器覆盖 → F-17 |
| 限流 / 配额 | **无**(因为没有限流) | → F-03 |
| Web | 47 个测试文件 + 3 个 Playwright e2e(含 `multiplayer-isolation.spec.ts`) | 无成员视角的**正向**流程 e2e(备战搜球场就在这个盲区里) |
| iOS / Watch | 有单测 + CI 真 `xcodebuild test` + ImageRenderer 设计快照 | 无并发/竞态用例(→ F-07);无崩溃一致性用例(→ F-06) |

**贯穿性的观察**:这个套件的失败模式**不是"覆盖率低"**——覆盖率其实相当高。失败模式是 **"测试验证的是一个生产系统不会进入的状态"**:英文的 narrative、串行的幂等、只测拒绝不测放行、验证包含不验证排除。这类盲点靠加覆盖率是找不出来的,只能靠**对每条断言反问一句"生产真的会长成这样吗"**。

---

## 八、其余领域小结

### 领域 1:架构 / 需求 / 文档一致性

分层清楚且与文档相符:`ai_caddie/`(领域层,无 FastAPI)→ `server_v2/`(FastAPI 适配层)→ `web_v2/` / `mobile/`。`README.md:83-85` 声明 `tools/legacy/` 不再是主入口,与实际一致(生产代码不 import `tools/`)。

问题:**111 个 `.md` 里绝大多数是 `docs/superpowers/plans/` 和 `specs/` 的历史计划快照,没有一份"当前架构是什么样"的文档**。README 主体(1-80 行)还停留在"Garmin 抓取脚本"的叙事,v2 产品只是第 81 行开始的一节。新人(或半年后的自己)只能读代码。

### 领域 3:Garmin / 几何 / 统计 / 球童 / provider 边界

- **Provider 边界是对的**:`generate_report` 先 `_redact_value(facts)` 再进提示词(`ai_caddie/reports/reports.py:2601`),送出去的是**结构化事实 JSON**,不是原始 Garmin 文件或 token——与 README.md:168 的声明一致。`redact_secret_text`(`ai_caddie/llm/llm_providers.py:65-83`)在错误路径上也做了脱敏。
- **但事实校验在中文下失效**(F-05)——这是 provider 边界上最严重的问题。
- **单位换算全仓库一致**(1 m = 1.09361 yd;`ai_caddie/geometry/elevation.py:18`、`ai_caddie/courses/course_prep.py:25`、`WatchUnits.swift`、`reviewShotMapLogic.ts`)。仅有的瑕疵是 `ai_caddie/caddie/analysis.py:1074` 用 `int()` 截断而 `ai_caddie/caddie/analysis.py:202` 用 `int(round())`——四舍五入不一致,±1 码,P3。
- **几何数学正确**:semicircle 转换 `180/2^31`、局部平面近似、`green_slope` 的最小二乘平面拟合(`ai_caddie/geometry/elevation.py:114-135`)都没问题。
- **差点估算有量纲混合缺陷**(F-10)。

### 领域 4:Web 前端

- **认证客户端写得很谨慎**:`adminTokenHeader`(`web_v2/src/api.ts:117-130`)在检测到 member session 时**拒绝发送 admin token**——客户端与服务端(`server_v2/players_api.py:200-208`)双向设防,这是对的。
- **诊断模式(内部 ID / source refs / 证据面板)是组件级自隐的**(`web_v2/src/components/SourceRefs.tsx:16-22` 的 `if (!diagnostics) return null`),而不是靠调用方记得不渲染——同样是"构造式"而非"检查式"的做法,值得肯定。
- **无障碍**:46 个组件全部出现 `aria-label` 或 `role`。不算深度审计,但基本卫生在。
- 主要缺陷是 F-04(成员备战搜球场 403)。

### 领域 5 / 6:iOS 与 Apple Watch

- **认证与凭据存储是稳的**(见 §二强项)。手表**不持久化** session token(`WatchSyncClient.applyApplicationContext`(`mobile/ios/AICaddieWatch/Services/WatchSyncClient.swift:350-372`) 只写内存里的 `client.config`),token 经 WatchConnectivity application context 从手机推送——设计正确。
- 主要缺陷:F-06(崩溃销毁已记录的杆)、F-07(队列竞态)、F-08(传输不对称)、F-15(无版本协商)、F-16(无刷新/无 401 处理)。
- **一个值得注意的耦合**:iOS 媒体上传把内容作为 **base64 String 持在内存里**(`mobile/ios/AICaddie/Services/MediaUploadClient.swift:8` `contentBase64: String?`)。一个 80MB 视频 ≈ 107MB 的 base64 字符串 → 内存压力 → **jetsam 杀 app** → 而这正是 F-06 的触发条件。两个缺陷在同一个场景里会互相放大。(此耦合为合理推断,未实测,标 NEEDS-DYNAMIC-VERIFICATION。)

### 领域 8:安全 / 隐私 / 密钥 / 供应链 / CI / 部署 / 可观测性

- **无硬编码密钥**(全仓库正则扫描,零命中)。密钥全走环境变量。
- **锁文件是强制的**:`uv sync --frozen`(CI + Docker 一致)、`npm ci`。✓
- **`superfly/flyctl-actions/setup-flyctl@master` 未固定版本**(`.github/workflows/backend-fly-deploy.yml:76`)——第三方 action 用 `@master`,等于给部署工作流(持有 Fly 凭据)一张空白支票。**无 dependabot,无漏洞扫描。**(F-20)
- **CORS 经检查是安全的**(`allow_credentials=False` + Starlette 的 `fullmatch` 正则)——见 §9.1 的否决记录。
- **可观测性**:Python 用标准 `logging`,Swift 用 `os.Logger`(`AICaddieLog` / `WatchLog`),有结构化的 privacy 标注。**但没有指标、没有追踪、没有告警**——生产里发生 F-06 这类静默丢数据,没有任何东西会响。
- **并发姿态**:

| 资源 | 保护 | 评价 |
|---|---|---|
| Garmin 同步(改 `fetch` 模块全局变量) | `threading.Lock` + 非阻塞 acquire → 409(`server_v2/main.py:1266,1287`) | **正确**——但依赖 `ops/start_api.sh:46` 是**单进程**。任何人加 `--workers 2` 都会静默破坏它,而代码里**没有断言** |
| 实时事件日志追加 | `fcntl.flock`(跨进程安全) | **正确** |
| 身份库 | Postgres 事务 + UNIQUE + `IntegrityError → IdentityConflictError` 语义化 | **正确**,并发首次登录的竞态处理得很干净 |
| 手动记分 ingest | **无** | F-09 |
| 手表离线队列 | **无** | F-07 |
| 玩家注册表 / ack 存储 | **无** | F-23 |

---

## 九、经过验证后被否决 / 收窄的判断(诚实记录)

评审要求"检查反证并否决站不住的结论"。有三条:

### 9.1 【否决】"成员点开球洞几何证据会 403"

动态验证确认路由层面**确实** 403(`GET /api/v2/geometry/hole/{gid}/{hole}?source_ref=…` 对成员 forbid)。但**成员根本走不到这条路径**:

- `web_v2/src/App.tsx:781-786` 的 `renderDiagnosticsDrilldownPanels()` 用 `if (!(diagnostics && isOwnerMode)) return null` 挡住整个几何证据面板;
- `web_v2/src/components/SourceRefs.tsx:16-22` 组件级自隐,成员**没有任何可点的 source ref**;
- iOS **完全不调** `/geometry/hole`(检索确认)。

→ 这是一个**潜伏的**授权表不对称,不是用户可见缺陷。不计入发现表。

**它同时验证了 F-04 的判断方式**:同样是 403,`/courses/search` 之所以是 P1,恰恰因为它**在成员可见的主流程正中间**。

### 9.2 【否决】"PlaysLike 的海拔取点会落在球道网格之外,导致实打距离算错"

`elevation.nearest_elevation`(`ai_caddie/geometry/elevation.py:47-64`)**确实没有距离上限**——它无论多远都会返回"最近的顶点",从不返回 `None`。理论上,如果发球台不在任何 mesh 的覆盖范围内,它会拿一个几十米外的顶点的高程当作发球台高程,`deltaM` 就错了,而且照样报 `available: true`。

**我在真实几何上实测否决了这条。** 从 1519 个已解码的 mesh 文件里随机抽 30 个洞,测量 `derive_route()` 得到的发球点到**任意** mesh 顶点的最近距离:

```
n=30   tee→最近网格顶点:  min=0.2m  median=0.8m  p90=1.1m  max=1.3m
   发球台距离任何顶点 >10m 的洞: 0/30
```

网格**密集覆盖了发球台**(中位数 0.8 米)。缺少距离上限是一个**潜在**的健壮性缺口,但在这份数据上**没有任何证据表明它正在出错**。降级为 P3 加固建议,不计入发现表。

### 9.3 【收窄】"契约测试是假绿的"

初始怀疑:`tests/test_mobile_contracts.py` 用一个手写的残缺 schema 检查器代替了已经 import 的 `Draft202012Validator`。

**收窄后的事实**:真校验器**在用,25 处**,而且带否定用例。契约测试**整体是强的**。只有 `tests/test_mobile_contracts.py:483`(ready package)是弱校验器单独覆盖。→ 从 P2 "假绿套件" 收窄为 F-17 "一处主力形状未被真校验 + 一个应当删掉的陷阱助手"。

---

## 十、发布门禁与 30 / 60 / 90 天路线图

### 发布门禁(面向公众发布的硬性前置条件)

| # | 门禁 | 对应发现 | 验收标准 |
|---|---|---|---|
| G1 | 备份不含任何凭据,且 `secretFree` 是**算出来的** | F-01 | 一条测试:构造带 `.garmin_tokens` 的树 → 导出 → 断言 tar 里**没有**它 |
| G2 | 备份包含身份库,且**恢复演练通过** | F-02 | 一条端到端:备份 → 全新环境恢复 → 同一 Apple sub 登录 → 拿回原 pid |
| G3 | LLM / 渲染类端点有**按人限流 + 每日预算熔断** | F-03 | 超配额返回 429;预算耗尽自动降级到 deterministic |
| G4 | 成员能走完每一个主导航区块 | F-04 | 一条路由策略**正向**测试:成员对每个应可用路由 200 |
| G5 | 防幻觉校验在**中文**下生效 | F-05 | 一条中文 narrative 的否定用例 |
| G6 | 记杆路径的崩溃一致性 | F-06 | 两端各一条:日志尾部无换行 → 再追加 → 旧记录仍可读 |
| G7 | owner 引导不依赖可被隐藏的 email claim | F-11 | 用一次性 bootstrap token 或"首个登录者即 owner" |
| G8 | 主干上有 CI | F-12 | `ci.yml` 加 `push: branches: [integration/v2]` |

### 30 天(P1 清零 + 止血)

1. **F-01 / F-02(备份)**——这两条一起做,是唯一会造成**永久性、不可恢复损失**的一组。`pg_dump` + 排除 dotdir + 计算式 `secretFree` + 一次真实的恢复演练。
2. **F-05(中文防幻觉)**——双语词表 + 中文否定用例。改动小、风险低、直接消除一个虚假安全信号。
3. **F-04(成员 403)**——把两张手写路径表合成**一张声明式路由策略表**,两个函数从同一张表推导。这不只是修 bug,是**消除这一类 bug**。
4. **F-03(限流)**——先上最简单的按 `player_id` 令牌桶 + LLM 预算熔断。
5. **F-11(owner 引导)** + `.env.example` 补全。

### 60 天(数据完整性 + 手表可靠性)

6. **F-06(两端换行终止符)**——两行代码,但要配崩溃一致性测试。
7. **F-07 / F-08(手表)**——手表→手机改用 `transferUserInfo`;`WatchSyncClient` 的队列操作串行化。这一组直接决定"球场上记的杆会不会丢",是**手表产品的可信度底线**。
8. **F-09(ingest 幂等)**——`fcntl.flock` + 统一改用 `atomic_write_json`(仓库里已经有了)。
9. **F-12(CI)** + **F-17(契约主力形状)** + **F-16(会话刷新 / 401)**。

### 90 天(可伸缩性 + 演进能力)

10. **F-14(事件日志 O(n²))**——按 `roundId` 分片 + 结束球局后压实。这是唯一一个会随时间**变得更糟**的问题。
11. **F-15(schema 版本协商)**——在还只有少量 TestFlight 用户时做,成本最低;等 App Store 上有长尾旧版本就晚了。
12. **F-10(差点量纲)**——要么统一到 rated-only(样本变少但诚实),要么给 score-par 做一次尺度归一。这是产品可信度问题,不是 bug。
13. **F-13 / F-18 / F-19 / F-20** + 一份真正的"当前架构"文档。

### 一条元建议

这份仓库最值得投资的不是任何一个单独的修复,而是**把"构造式安全"的做法贯彻到剩下的地方**。它已经在两个地方做对了——`evidence_root(player_id)` 用**路径构造**实现隔离,`SourceRefs` 用**组件自隐**实现诊断门控。两者都不依赖"每个调用方记得检查"。

而所有五个 P1,根子都在**还没有这样做的地方**:
- 备份靠一份**手写的**路径清单(F-01/F-02)→ 应该改成"默认排除,显式包含"。
- 授权靠**两张手写的**路径表(F-04)→ 应该改成一张声明式表。
- 防幻觉靠一份**手写的**关键词表(F-05)→ 应该改成结构化的事实覆盖校验。
- 成本控制靠**没人写**的限流(F-03)。

**手写的、必须靠人记得同步的清单,就是这份仓库的系统性风险来源。** 每把一张这样的清单换成一个"构造上不可能出错"的机制,就消掉一整类未来的 bug。

---

## 十一、覆盖清单(Coverage Ledger)

| # | 领域 | 状态 | 实际读过的文件 / 实际做过的验证 |
|---|---|---|---|
| 1 | 架构 / 产品需求 / 文档一致性 | ✅ 已审(中等深度) | `README.md` 全文、`docs/` 目录树 + `docs/superpowers/specs/` 清单、`.env.example`、顶层结构、`git ls-files` 全量分类。**未逐篇读 111 份文档**(读了 README + 抽样),已在 §八说明 |
| 2 | 后端 / API / 认证授权 / 存储 / 并发 / 数据完整性 / 备份恢复 | ✅ 已审(深度) | `server_v2/`:`main.py`(全 1400 行)、`players_api.py`(全)、`auth_api.py`(全)、`apple_auth.py`(全)、`identity_repo.py`(全)、`identity_models.py`(全)、`db.py`(全)、`session.py`(全)、`media.py`(头部)、`reports.py`(provider 选择)。`ai_caddie/`:`core/data.py`(全)、`rounds/players.py`(全)、`rounds/round_ingest.py`(关键段)、`rounds/round_corrections.py`(关键段)、`caddie/mobile_live.py`(事件日志全段)、`connectors/garmin_cn.py`(分区段)、`connectors/session_material.py`。`ops/`:`start_api.sh`、`backup_data.sh`、`export_snapshot.py`、`import_snapshot.py`。`Dockerfile`、`docker-compose.yml`。**动态验证**:路由授权分类表 |
| 3 | Garmin / 几何 / 统计 / 差点 / 球童事实 / prompts / provider 边界 | ✅ 已审(中高深度) | `ai_caddie/history/history_stats.py`(差点 / differential 段)、`ai_caddie/geometry/elevation.py`(全)、`ai_caddie/courses/course_prep.py`(route / playslike 段)、`ai_caddie/reports/reports.py`(prompt + 事实校验 + payload)、`ai_caddie/caddie/decision.py`(LLM 边界段)、`ai_caddie/llm/llm_providers.py`(全部 provider + 脱敏)、单位换算全仓库检索。**动态验证 ×2**:中文事实校验失效(复现);真实几何上的 tee→mesh 距离(30 洞采样,**否决**了一条怀疑)。**未深审**:`garmin/fetch.py` 的 Garmin 协议细节、CourseView protobuf 解析器 |
| 4 | Web 前端 | ✅ 已审(中等深度) | `api.ts`(auth / 请求层)、`navigation.ts`(全)、`App.tsx`(auth / drilldown / 诊断门控段)、`PrepPage.tsx`、`CourseFinder` 调用链、`SourceRefs.tsx`、`diagnosticsStore.ts`、`sessionStore` 引用、e2e 清单、a11y 检索(46/46 组件)。**未逐个审 46 个组件**;**未做性能剖析** |
| 5 | iOS | ✅ 已审(中等深度) | `SessionStore.swift`(全)、`OfflineStore.swift`(持久化 / 追加 / 加载段)、`MediaUploadClient.swift`(接口 + 内存形状)、`AICaddieApp.swift`(生命周期检索)、`SyncClient.swift`(错误类型)、`AppleAuthClient.swift`、401/refresh 全量检索。**未编译**(需 macOS);**未审** `CurrentHoleView` 等大型 view |
| 6 | Apple Watch / WatchConnectivity | ✅ 已审(中高深度) | `WatchSyncClient.swift`(队列 / 传输 / 配置全段)、`WatchRoundStore.swift`、`WatchEventBridge.swift`(传输段)、`WatchUnits.swift`(全)、WatchConnectivity 传输方式全量检索、手表测试清单。**未审** `WatchHoleMapView` / `WatchGeoMath` 的几何细节 |
| 7 | 跨端契约与 schema 演进 | ✅ 已审(深度) | `mobile/contracts/` 4 个 schema 的特性分析、`tests/test_mobile_contracts.py`(校验助手 + 全部 25 处真校验调用点 + `tests/test_mobile_contracts.py:483` 例外)、客户端 `schema` 字段处理全量检索 |
| 8 | 安全 / 隐私 / 密钥 / 供应链 / CI-CD / 部署 / 可观测性 / 限流 | ✅ 已审(中高深度) | 7 个 workflow(`ci.yml` / `native-mobile.yml` 逐行;其余读触发与关键步骤)、硬编码密钥全量正则扫描、限流全量检索、出站 HTTP 全量检索、action 固定版本检索、`.github/` 目录(确认无 dependabot)、CORS 分析、并发保护逐项列举。**未做**:依赖漏洞扫描 / SBOM(需装包,超出只读范围) |
| 9 | 测试质量 / 假绿 / 覆盖缺口 / 死代码 | ✅ 已审(中高深度) | `tests/` 全量清单(155)、`test_mobile_contracts.py`(深度)、`test_fact_bound_reports.py`(narrative 语言分析)、`test_decision_layer.py`(factBinding 断言)、幂等/备份/授权测试的**缺口方向**分析、web 测试清单(47 + 3 e2e)。**未跑测试套件、未测覆盖率** |
| 10 | 发布就绪 + 优先级路线图 | ✅ 已审 | 8 条发布门禁 + 30/60/90 天路线图 + 一条元建议 |

**未完成 / 明确不在范围内的**:
- 未运行任何测试套件、未测覆盖率、未编译 Swift、未做依赖漏洞扫描(均需安装包或 macOS,超出"只读 + 不装包 + 不产构建物"的约束)。
- 未访问生产环境、未看运行时日志/指标。
- 未逐篇阅读 111 份文档、未逐个审查 46 个 Web 组件与全部 Swift view。

**10 个领域全部实际审查过,故标记 COMPLETE**;各领域的实际深度与未覆盖部分已如实列在上表,请按此判断结论的可信范围。
