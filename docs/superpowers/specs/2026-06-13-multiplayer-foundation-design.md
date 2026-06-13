# 多球员地基 + 手机局落库后端(阶段一设计)

> **中文摘要:** 把现在"私有单人(你的 Garmin 数据)"的产品,扩成"个人+好友"的**按球员隔离**本地库:每个球员一套数据根,历史/统计/强弱/备战/报告全部按球员作用域;新增"手机录的一局"落库后端(把逐杆采集事件落成 Garmin 同构的 scorecard+shots,引擎统一分析)。**本地库 = 唯一真源;Garmin 只是 owner 的只读输入源之一;不写回 Garmin。** 这是三子系统中的第一块(地基),后端+网页本期做完;原生 iOS/手表(重做 + 逐杆 GPS 记录 + 设备端球员切换)是阶段二、独立 spec。

**Branch:** `superpowers/multiplayer-foundation` off integration/v2 (faea7c9)。

---

## 1. 背景与决策来源

用户验收反馈后的方向(2026-06-13 对话):
- 手机最终也要能**自己记录一局**——因为不一定每次都戴 Garmin 手表,或借给没有 Garmin 的球友用。
- 记录粒度:**逐杆标落点(GPS)**——产出和 Garmin 一样的杆级数据,强弱分析/球杆距离/落点散布不降级。
- 多球员:**先"个人+好友"私有**(不做注册/登录鉴权),但数据模型**预留升级**到真账号(player_id 做主键)。
- 数据来源优先级:**有 Garmin 数据就从 Garmin 取**(用手表时不在手机重复记);忘带设备 / 没 Garmin 的人 → 用手动记录。**最终本地有一套统一数据库。**
- **不写回 Garmin 备份**(见 §8 非目标的理由)。

三子系统拆分与顺序(已与用户确认):
1. **本期 = 多球员地基(后端+网页)+ 手机局落库后端** ← 本文档
2. 阶段二:原生 iOS + 手表 UI 重做 + 逐杆 GPS 记录流程 + 设备端球员切换(独立 spec)

分阶段理由:后端/网页 Claude 能自己起服务、截图、跑测试**全程验收**;iOS/手表无法在本机模拟器验收,需用户在 TestFlight/模拟器配合,故集中到阶段二。

---

## 2. 范围

**本期做:**
- 按球员的数据存储与加载(地基)。
- 球员注册表 + CRUD + 当前球员切换(网页)。
- 全部历史/统计接口按球员作用域 + 每球员独立缓存。
- 手机局落库后端接口(`POST .../rounds`):采集事件 → 该球员的 Garmin 同构 scorecard+shots。
- 本地备份策略覆盖全部球员。

**本期不做(明确排除):**
- 原生 iOS / 手表的任何改动(阶段二)。
- 真账号/注册/登录鉴权/多租户(预留,不实现)。
- 写回 Garmin(见 §8)。
- 手机端 UI(采集界面属阶段二;本期只交付被它调用的后端接口 + 用 curl/测试验证)。

---

## 3. 数据模型与存储

### 3.1 每球员一套数据根

现状:`ai_caddie.history.load_history_data()` 无参,读模块级单根(owner 的 Garmin 数据:`data/scorecards`、`data/shots`、`data/summary.json`)。

改为按球员分根:

```
data/
  scorecards/        # 既有扁平布局 = owner(player_id="me")—— 原地不动,零迁移
  shots/
  summary.json
  players/
    <player_id>/
      scorecards/    # 该球员的局(手动录的;owner 也可有)
      shots/
      summary.json   # 该球员的汇总(由落库时增量维护)
      profile.json   # 名字、创建时间、可选头像、source 统计
```

**owner 兼容(关键、零破坏):** 加载器对 `player_id == "me"` **优先读既有扁平 `data/`**(就是现在 Garmin 同步写入、homeserver 卷里已有的 467 局),不搬动任何文件。若 `data/players/me/` 也存在(owner 用手机补录的局),则**合并**两处(见 §4 去重)。其它球员只读 `data/players/<id>/`。

否决的备选:给每条记录加 `player_id` 字段后全量加载再过滤——现有文件无此字段、要全改、且每次都加载全量再筛,慢。每球员分根是最小改动且天然隔离。

### 3.2 球员注册表

`data/players/registry.json`:

```json
{
  "schema": "ai-caddie-players-v1",
  "activePlayerId": "me",
  "players": [
    {"id": "me", "name": "我", "isOwner": true, "createdAt": "...", "avatar": null},
    {"id": "p_a1b2", "name": "老王", "isOwner": false, "createdAt": "...", "avatar": null}
  ]
}
```

- `id`:slug 主键(owner 固定 `me`;其余 `p_<随机>`)。**这是预留升级位**——将来转真账号时,player_id 映射到 account_id,数据根不变。
- owner(`me`)不可删;Garmin 同步永远只写 `me`。
- `activePlayerId`:服务端记住的"当前查看球员",仅作默认值;每个请求可用 `?player=` 覆盖(见 §5)。

---

## 4. 数据来源与统一(本地库为唯一真源)

每个球员的局都落进**同一套 per-player 存储、同一套 Garmin 同构 schema**,只用 `source` 字段区分来源:

| source | 来源 | 适用球员 |
|---|---|---|
| `garmin` | Garmin CN 同步(只读输入) | 仅 owner(`me`) |
| `manual` | 手机逐杆记录落库 | owner(忘带设备时)+ 所有球友 |

引擎(history/stats/strengths/prep/reports)对两种 source **一视同仁**——只要 schema 相同即可。`source` 仅用于展示标注与去重决策。

**去重 / 优先级规则:** 同一球员、同一天、同一球场若同时存在 `garmin` 和 `manual` 局(理论上 owner 用手表就不会在手机重复记,极少发生):**Garmin 优先**(数据更全),`manual` 那条标记为被取代(`supersededBy`)不计入统计。规则在加载合并阶段执行(owner 合并扁平 `data/` 与 `data/players/me/` 时)。

---

## 5. API

所有现有历史类接口新增可选 `?player=<id>`(缺省 = registry 的 `activePlayerId`,即 `me`):
- `GET /api/v2/history/overview|rounds|stats|drilldown|...`
- `GET /api/v2/courses/{gid}/prep|prep-tips`、`/api/v2/reports` 等

新增球员管理接口(private 鉴权,admin token):
- `GET  /api/v2/players` → 注册表(球员列表 + activePlayerId)。
- `POST /api/v2/players` `{name, avatar?}` → 建档,返回新 player_id。
- `PATCH /api/v2/players/{id}` `{name?, avatar?}` → 改。
- `DELETE /api/v2/players/{id}` → 删(owner 不可删;删除移除该球员数据根)。
- `PUT  /api/v2/players/active` `{playerId}` → 设当前球员(写 registry.activePlayerId)。

新增**手机局落库**接口(阶段二 iOS 调用,本期交付 + 测试):
- `POST /api/v2/players/{id}/rounds`
  - 入参:一局的采集事件序列(沿用现有 live event 形状 / `watch_input_event` 契约:逐杆 `location`(lat/lon)+`club`(+shotType)、`score`、`putt`、`penalty`、`note`;附 `courseGlobalId`/前后九、开球时间、tee)。
  - 处理:校验 → 落成该球员的 **Garmin 同构** `scorecards/<round_id>.json`(holePars、holes[].strokes 等)+ `shots/<round_id>.json`(逐杆坐标/杆/距离),`source="manual"`;增量更新该球员 `summary.json`;失效该球员的 stats 缓存。
  - **幂等**:带 `Idempotency-Key`(或事件里的 round 客户端 id),重复提交不产生重复局。
  - 返回:落库后的 round 摘要(id、洞数、杆数),供 app 跳转复盘。

---

## 6. 引擎按球员作用域

- `load_history_data()` 增加 `player_id: str = "me"` 参数,据此选数据根(§3.1 的兼容逻辑)。所有调用点透传 player。
- `stats_cache`:缓存 key 从"单指纹"改为"`(player_id, 指纹)`"——各球员独立缓存、独立失效;启动预热只热 `me`(其它球员按需冷算)。
- 其余 builder(overview/rounds/stats/strengths/prep/reports)签名已接受 `HistoryData`,**内部逻辑不变**——只是上层传入"该球员的 HistoryData"。改动集中在加载层 + 缓存层 + 接口透传,引擎算法零改。

---

## 7. 网页 UI(本期可见交付)

- **顶部球员切换器**:下拉显示所有球员 + 头像/名字,切换即把全站数据切到该球员(改 `?player=` + 持久化 active)。owner 标记"我"。
- **球员管理**(设置区新增一页 / 或切换器内"管理"):建/改/删球员、看每球员局数与来源占比(Garmin/手动)。
- 现有所有页面(概览/历史/强弱/球场/报告/备战)**不改布局**,只是数据按当前球员。
- 手机手动局在历史里带"手动"标(对应 `source=manual`),和 Garmin 局视觉区分但同等分析。
- 复用 W4a 设计语言;Claude 自行起服务 + Playwright 截图验收(低内存守则,见现有记忆)。

---

## 8. 非目标与理由

- **不写回 Garmin 做备份。** 理由:① 没 Garmin 账号的球友根本写不回 → 功能残缺;② 只验证过 Garmin CN 的读路径,无可靠写接口,逆向写既脆弱又有账号/ToS 风险;③ 本地库是唯一真源,备份在本地解决(§9)即覆盖全部球员,更简单完整。若将来 owner 想把自己的局镜像回 Garmin,可作为 owner-only 的可选小功能另议——但它不是备份策略。
- **不做真账号/鉴权/多租户**(预留 player_id 升级位)。
- **不动原生**(阶段二)。

---

## 9. 备份策略(覆盖全部球员)

本地库为真源,备份在本地做,所有球员一视同仁:
- 复用 `ops/export_snapshot.py`(已含 data/scorecards、shots、reports 等;需扩展纳入 `data/players/**`)→ 定期导出 tar。
- 复用 `ops/backup_data.sh` + cron 做本机/异地副本(具体落地放实现期)。
- homeserver Docker 卷 `ai-caddie-private` 已持久化;快照可异地存。

---

## 10. 兼容性 / 安全 / 测试

- **兼容**:owner 现有 467 局零迁移(`me` 读既有扁平 `data/`);所有接口 `?player` 缺省即旧行为;Garmin 同步路径不变(只写 `me`)。
- **安全**:private 鉴权不变,球员是数据分区**不是登录主体**;admin token 仍是唯一闸门;落库接口校验输入、不接受任意路径(player_id 白名单于注册表)。沿用绝不打印 token/cookie 的规矩。
- **测试**(后端 unittest,CI = discover):
  - 加载器:`me` 读扁平、新球员读 players/<id>、两者合并去重(Garmin 优先)。
  - 接口:`?player` 作用域(球员 A 看不到球员 B 的局);players CRUD;active 切换。
  - 落库接口:事件 → Garmin 同构 scorecard+shots 的正确性 + 幂等 + 缓存失效 + 落库后该球员 overview/stats 正确。
  - 缓存:`(player_id, 指纹)` key 隔离。
  - 前端 vitest:球员切换器、管理页、手动局标注。
  - e2e:建球员 → 切换 → (mock 落库一局)→ 历史可见。

---

## 11. 预留升级(个人+好友 → 真账号)

- player_id 用稳定 slug 主键,所有数据/接口以它为锚——将来引入 account/auth 时,player_id ↔ account_id 映射,数据根与引擎零改。
- registry.json 可平滑迁成账号表;`isOwner` → 账号角色。
- private 鉴权将来可换成 per-account 鉴权,接口形状(`?player` / `/players/{id}/...`)不变。

---

## Self-review 检查项(写完自查)

- 无 TBD/占位;§3 兼容逻辑与 §4 去重一致;范围聚焦单一实现计划(地基,不含原生);player 选择方式(`?player` + registry active)全篇一致;落库接口入/出契约明确(沿用 watch_input_event)。
