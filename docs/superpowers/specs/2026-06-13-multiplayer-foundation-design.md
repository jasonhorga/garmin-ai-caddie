# 多球员地基 + 手机局落库后端(阶段一设计)

> **中文摘要:** 把现在"私有单人(你的 Garmin 数据)"的产品,扩成"个人+好友"的**按人隔离**本地库:每个球员一套数据根 + 一条**专属网址(capability token)**,每条网址只通该球员自己——**没有全局切换器、谁也看不到别人**。owner 另有一个**管理入口**(admin token)建/删球员、生成并分发他们的专属网址。新增"手机录的一局"落库后端(逐杆采集事件 → Garmin 同构 scorecard+shots,引擎统一分析)。**本地库 = 唯一真源;Garmin 只是 owner 的只读输入源之一;不写回 Garmin。** 访问用 per-player bearer token,**为将来"登录"预留**——以后把"owner 发链接"换成"登录签发同类 token",后端访问模型不变。这是三子系统中的第一块(地基),后端+网页本期做完;原生 iOS/手表是阶段二、独立 spec。

**Branch:** `superpowers/multiplayer-foundation` off integration/v2 (faea7c9)。

---

## 1. 背景与决策来源

用户验收反馈后的方向(2026-06-13 对话):
- 手机最终也要能**自己记录一局**——不一定每次戴 Garmin 手表,或借给没 Garmin 的球友用。
- 记录粒度:**逐杆标落点(GPS)**——产出和 Garmin 一样的杆级数据,强弱分析/球杆距离/落点散布不降级。
- 多球员:**先"个人+好友"私有**;数据模型 + 访问模型都**预留升级**到真账号/登录(player_id 主键、per-player bearer token)。
- **按人隔离,不要全局切换器**(用户明确否决"一个页面能翻所有人数据"):**每人一条专属网址,只看得到自己**。owner 的"管理"只列球员与其链接,不混着看数据。
- 数据来源优先级:**有 Garmin 数据就从 Garmin 取**(用手表时不在手机重复记);忘带设备 / 没 Garmin 的人 → 手动记录。**最终本地一套统一数据库。**
- **不写回 Garmin 备份**(理由见 §8)。
- **后面可能需要登录**——本期访问用 owner 签发的 per-player token,设计成将来能平滑换成登录签发。

三子系统拆分与顺序(已确认):**① 本期 = 多球员地基(后端+网页)+ 手机局落库后端** ←本文档;② 原生 iOS+手表 重做 + 逐杆 GPS 记录 + 设备端选球员(独立 spec)。分阶段理由:后端/网页 Claude 能自起服务、截图、跑测试**全程验收**;iOS/手表无法本机验收,集中到阶段二由用户在 TestFlight 验。

---

## 2. 范围

**本期做:** 按球员的数据存储与加载;球员注册表 + 专属 token 签发;**按 token 的访问隔离**(每人只见自己);owner 管理入口(建/删/发链接);全部历史/统计接口按当前 token 的球员作用域 + 每球员独立缓存;手机局落库后端(`POST .../rounds`);本地备份覆盖全部球员。

**本期不做(明确排除):** 原生 iOS / 手表任何改动(阶段二);**正式登录/注册**(本期用 owner 签发 token,但为登录预留,见 §11);多租户/陌生人自助注册;写回 Garmin(§8);手机端采集 UI(阶段二;本期只交付被它调用的后端接口 + 用 curl/测试验证)。

---

## 3. 数据模型与存储

### 3.1 每球员一套数据根

现状:`ai_caddie.history.load_history_data()` 无参,读模块级单根(owner 的 Garmin 数据)。改为按球员分根:

```
data/
  scorecards/        # 既有扁平布局 = owner(player_id="me")—— 原地不动,零迁移
  shots/
  summary.json
  players/
    <player_id>/
      scorecards/    # 该球员的局(手动录的;owner 也可有)
      shots/
      summary.json
      profile.json   # 名字、创建时间、可选头像、source 统计
```

**owner 兼容(零破坏):** `player_id == "me"` **优先读既有扁平 `data/`**(homeserver 卷里已有的 467 局),不搬文件;若 `data/players/me/` 也存在(owner 手机补录的局)则**合并**(§4 去重)。其它球员只读 `data/players/<id>/`。否决备选:给每条记录加 player_id 字段全量过滤——文件无此字段、要全改、慢。

### 3.2 球员注册表(含 token 映射)

`data/players/registry.json`(**仅 owner 管理入口可读全表;球员侧 API 永不返回此表**):

```json
{
  "schema": "ai-caddie-players-v1",
  "players": [
    {"id": "me", "name": "我", "isOwner": true, "createdAt": "...", "avatar": null,
     "tokenHash": "sha256:...", "tokenLast4": "9f3a"},
    {"id": "p_a1b2", "name": "老王", "isOwner": false, "createdAt": "...", "avatar": null,
     "tokenHash": "sha256:...", "tokenLast4": "77c1"}
  ]
}
```

- `id`:slug 主键(owner 固定 `me`;其余 `p_<随机>`)。**预留升级位**——将来转真账号时 player_id ↔ account_id,数据根不变。
- `tokenHash`:每球员一条**不可猜 bearer token**(≥32 字节随机),**只存哈希**;明文仅在生成时返回一次给 owner 去分发(类似 API key)。`tokenLast4` 仅供管理页识别。
- owner(`me`)不可删;Garmin 同步永远只写 `me`。
- **没有 activePlayerId**——当前球员由请求携带的 token 决定(§5),不存全局"当前选中"。

---

## 4. 数据来源与统一(本地库为唯一真源)

每个球员的局落进**同一套 per-player 存储、同一套 Garmin 同构 schema**,只用 `source` 区分:

| source | 来源 | 适用球员 |
|---|---|---|
| `garmin` | Garmin CN 同步(只读输入) | 仅 owner(`me`) |
| `manual` | 手机逐杆记录落库 | owner(忘带设备)+ 所有球友 |

引擎(history/stats/strengths/prep/reports)对两种 source **一视同仁**(schema 相同);`source` 仅用于展示标注与去重。

**去重 / 优先级:** 同一球员、同天、同球场若同时有 `garmin` 与 `manual`(owner 用表就不会重复记,极少):**Garmin 优先**(更全),`manual` 标 `supersededBy` 不计入统计。规则在 owner 合并扁平 `data/` 与 `data/players/me/` 时执行。

---

## 5. 访问模型与 API(核心修订:按 token 隔离,无切换器)

### 5.1 两种凭证

- **per-player bearer token**(球员侧):随请求携带(`Authorization: Bearer <token>` 或网址 `?key=`)。后端按 token → 反查 player_id → **所有数据严格限定该球员**。一条 token 只通一个球员;**不存在"看所有人"的球员侧接口**。
- **admin token**(owner 管理侧):仅用于管理端点(建/删球员、签发/吊销链接、看注册表)。admin **不是**一个"能浏览所有人分析"的视图——它只管理球员与链接。

### 5.2 球员侧接口(按 token 作用域,不再有 `?player=` 切换器)

现有历史类接口改为**从 token 解析球员**,不接受调用方任意指定球员:
- `GET /api/v2/history/overview|rounds|stats|drilldown|...`
- `GET /api/v2/courses/{gid}/prep|prep-tips`、`/api/v2/reports` 等
- 返回的永远是"持此 token 的球员"的数据;无效/缺失 token → 401。

### 5.3 owner 管理接口(admin token)

- `GET    /api/v2/admin/players` → 注册表(球员 + tokenLast4,**不含明文 token、不含各球员数据**)。
- `POST   /api/v2/admin/players` `{name, avatar?}` → 建档;**返回一次性明文 token + 专属网址**供 owner 分发。
- `PATCH  /api/v2/admin/players/{id}` `{name?, avatar?}`。
- `POST   /api/v2/admin/players/{id}/rotate-token` → 重签 token(旧链接失效)。
- `DELETE /api/v2/admin/players/{id}` → 删(owner 不可删;移除其数据根)。

### 5.4 手机局落库(阶段二 iOS 调用,本期交付 + 测试)

- `POST /api/v2/players/{id}/rounds`(owner 操作时用 admin token 指定 `{id}` 给某球友记;球员自己记则用其 bearer token,`{id}` 须与 token 球员一致,否则 403)。
- 入参:一局采集事件序列(沿用现有 live event 形状 / `watch_input_event` 契约:逐杆 `location`(lat/lon)+`club`(+shotType)、`score`、`putt`、`penalty`、`note`;附 `courseGlobalId`/前后九、开球时间、tee)。
- 处理:校验 → 落成该球员的 **Garmin 同构** `scorecards/<round_id>.json` + `shots/<round_id>.json`,`source="manual"`;增量更新该球员 `summary.json`;失效该球员 stats 缓存。
- **幂等**:`Idempotency-Key`(或事件里的客户端 round id),重复提交不产生重复局。
- 返回:落库后的 round 摘要(id、洞数、杆数),供 app 跳转复盘。

---

## 6. 引擎按球员作用域

- `load_history_data(player_id="me")`:据此选数据根(§3.1 兼容逻辑);所有调用点透传 player(由 token 解析得来,非调用方指定)。
- `stats_cache`:key 从单指纹改为 `(player_id, 指纹)`——各球员独立缓存/失效;启动只预热 `me`,其它按需冷算。
- 其余 builder 签名已接受 `HistoryData`,**内部算法零改**——只是上层传入"该球员的 HistoryData"。改动集中在加载层 + 缓存层 + 鉴权/作用域层。

---

## 7. 网页 UI(本期可见交付)

### 7.1 球员侧:由网址锁定,无切换器

- 网址形如 `https://<host>/p/<token>`(或带 `?key=`);前端从网址取 token,所有 API 调用带上 → **整个 app 只显示该球员自己**。
- 顶部只显示"当前是谁"(名字/头像,只读),**没有下拉、没有别人**。
- 现有所有页面(概览/历史/强弱/球场/报告/备战)**布局不改**,数据即该球员;手动局带"手动"标(`source=manual`)。
- 无 token / token 失效 → 一个干净的"需要有效链接"提示页(不暴露任何球员存在与否)。

### 7.2 owner 管理页(admin token)

- 独立入口(设置区);列球员 + 各自 tokenLast4 + 局数/来源占比 + "复制专属网址 / 重发 / 删除"。
- **管理页本身不展示任何人的成绩分析**——只管理球员与链接。要看某球员分析,owner 用该球员的专属网址(和别人一样)。
- 复用 W4a 设计语言;Claude 自起服务 + Playwright 截图验收(遵低内存守则)。

---

## 8. 非目标与理由

- **不写回 Garmin 做备份。** ① 没 Garmin 账号的球友写不回 → 残缺;② 仅验证过 Garmin CN 读路径,无可靠写接口,逆向写脆弱且有账号/ToS 风险;③ 本地库是唯一真源,备份在本地解决(§9)即覆盖全部球员。owner 想把自己的局镜像回 Garmin 可作 owner-only 可选小功能另议,非备份策略。
- **本期不做正式登录/注册/多租户**——但访问模型(per-player bearer token)**专为将来登录预留**(§11),不是推倒重来。
- **不动原生**(阶段二)。

---

## 9. 备份策略(覆盖全部球员)

本地库为真源,备份在本地做,所有球员一视同仁:扩展 `ops/export_snapshot.py` 纳入 `data/players/**` → 定期导出 tar;`ops/backup_data.sh` + cron 做本机/异地副本(落地放实现期);homeserver 卷 `ai-caddie-private` 已持久化,快照可异地存。**注意:registry.json 含 tokenHash,属敏感,备份须随私有库一起、不外泄。**

---

## 10. 兼容性 / 安全 / 测试

- **兼容**:owner 现有 467 局零迁移(`me` 读既有扁平 `data/`);Garmin 同步路径不变(只写 `me`)。`?player=` 切换器**不引入**(本就没上线);球员侧接口一律按 token 作用域。
- **安全**:
  - per-player token ≥32 字节随机,**只存哈希**;明文仅签发时返回一次。token 验证防时序攻击(`secrets.compare_digest`/比哈希)。
  - **隔离硬保证**:球员侧任何接口都不接受调用方指定 player,只认 token → 不可能越权看别人。落库 `{id}` 须与 token 球员一致(admin 例外)。
  - 诚实的取舍:token 在网址里,链接泄露(截图/浏览器同步)即被访问——对"私有+好友打球数据"可接受,且 `rotate-token` 可吊销;将来换登录消除此风险(§11)。
  - admin token 仍是管理闸门;绝不打印/提交 token/cookie。
- **测试**(后端 unittest,CI=discover):
  - 加载器:`me` 读扁平、新球员读 players/<id>、合并去重(Garmin 优先)。
  - **隔离**:持球员 A 的 token 取不到球员 B 的任何数据;无效 token→401;落库 `{id}`≠token 球员→403。
  - admin:建球员返回一次性 token、列表不含明文、rotate 使旧 token 失效、删除移除数据根。
  - 落库:事件 → Garmin 同构 scorecard+shots 正确 + 幂等 + 缓存失效 + 落库后该球员 overview/stats 正确。
  - 缓存:`(player_id,指纹)` key 隔离。
  - 前端 vitest:网址 token 解析锁定球员、无切换器、管理页、手动局标注、无效链接提示页。
  - e2e:owner 建球员→拿到专属网址→用该网址只见该球员→(mock 落库一局)→历史可见;用 A 的网址看不到 B。

---

## 11. 预留升级(owner 发链接 → 正式登录)

- 球员侧访问已是**标准 bearer token**模型。将来加登录,只是**换 token 的签发方式**:从"owner 在管理页生成"改为"用户登录后服务端签发同类 token",**后端校验、作用域、数据根、引擎全部不变**。
- player_id 稳定 slug 主键,所有数据/接口以它为锚;registry.json 可平滑迁成账号表(tokenHash→密码哈希/会话);`isOwner`→账号角色。
- 接口形状(`Bearer` / `/players/{id}/...` / `/admin/...`)在登录后维持不变。

---

## Self-review 检查项

- 无 TBD/占位;§3 兼容与 §4 去重一致;§5 访问模型(token 隔离、无 `?player` 切换器)与 §7 UI(网址锁定、owner 管理页不看数据)一致;§11 登录演进与 §5 token 模型一致;落库接口入/出契约明确(沿用 watch_input_event)。范围聚焦地基,不含原生。
