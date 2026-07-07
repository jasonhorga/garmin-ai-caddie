# 复盘 v2 设计(经三模型对抗评审收敛,2026-07-05)

> 目标:复盘每杆做到「**什么杆 + 多远 + 落在/打进哪 + 罚没罚**」四要素**完整、可信、可修**。系统会漏记(没检测到挥杆)/错记(暂定球、练习挥) → 用户能增/改/删杆。**铁律:不造假**(拿不准留空、不重复计罚杆、推测绝不进统计)。范围:iOS + 网页;**手表门控**。
>
> **本设计由 3 个模型独立对抗评审后收敛**:Codex(gpt-5.5-xhigh)+ Gemini(3.1-pro)+ Fable。三家一致:草案「方向对(双层模型 + provenance 是正解),但不能直接实现,先修三处硬伤」。下方即修正后的设计。

## 三家一致的三处硬伤(已修)

1. **数据身份**:`roundId:hole:order` 当稳定 ID 会在 Garmin 重同步 / 多源(Garmin + 手表 JSONL + 未来 AutoShot)下错位,修正层挂错杆。→ 改**铸造稳定 ID + op-based 修正层**。
2. **罚杆模型是高尔夫规则错误**:罚杆区(红/黄桩)里**可以不罚直接打**,罚杆只由「救济决定」产生;把 `penalty` 绑在落点 = 把不该罚的洞算多一杆 = **造假**。→ 罚杆从落点剥离,挂到 `relief_event`。
3. **整洞 PUT 覆盖 与「离线优先」自相矛盾**,多端/离线会静默吃掉修正。→ 改 **op-based 事件日志**(本地先落 + 后台同步)。

---

## 1. 数据模型

- **Raw 层(多源、只读)**:Garmin 导入 + 手表 JSONL 事件(+ 未来 AutoShot)。每杆 ingest 时**铸造并持久化稳定 ID**(`source` + 原生 shotId/timestamp/坐标内容哈希)。**`order` 只是读取时派生的展示序号,任何引用一律不用 order。** 多源需 per-source ID + 去重(手表记的杆和 Garmin 导入现在就可能重复)。
- **修正层 = op-based 事件日志**(append-only,本地先落、后台同步):`addShot / editField / deleteShot(带删因) / restoreShot / reorderShot`,每条带 `clientMutationId`(幂等)、`baseRevision`(冲突检测)、时间、作者。**天然送:撤销/重做、离线合并、审计轨迹、冲突极小化、AutoShot 共存**(AutoShot 只生成建议,永不覆盖 manual,冲突进待处理队列)。
- **合并优先级**:`raw → 手动操作 → 推导建议(read-time)`。删除 = tombstone(不物理消失);推测永不覆盖手动;**悬空引用**(raw 因重同步变了)→ 保留修正 + 标「原始数据已变更」,**不静默丢**。合并函数必须有夹具测试(全删 / 原始为空 / 手动-only / 删后恢复 / 推测手动打架)。
- **字段级 provenance**:`club.source / start.source / end.source / lie.source / distance.source ∈ {garmin, watch, manual, inferred, geometry}`,+ `unknown_reason`。杆级 `garmin+edited` 太粗。
- **计分调和(硬伤,MVP 必须想清)**:洞分两源 —— Garmin scorecard vs shots+penalty 派生。规则:该洞**有任何手动修正 → shots 派生为准并标「已修正」**;无修正 → scorecard 为准;矛盾且无修正 → **展示差异,不静默选边**。**罚杆绝不重复计**(scorecard 已含罚杆时不再叠加 outcome penalty)。失杆归因:罚杆归到「导致它的那一杆」;校验 `∑各环节失杆 = 总杆 − 基准`。

## 2. 障碍 / 球位 taxonomy(规则正确)

**球位拆三层**(草案把规则区域/表面/打法混在一个 `lie` 里是错的):
- `course_area`(规则区域):`teeing_area / general_area / bunker / penalty_area / putting_green`
- `surface`(表面):`fairway / rough / fringe / native / trees / cartpath / …`
- `shot_intent`(打法,可选,是 strokes-gained 环节术语不是球位):`normal / recovery / punch / chip / pitch / putt`

**罚杆从落点剥离 → `relief_event`(救济决定):**
| relief_event | 罚杆 | 说明 |
|---|---|---|
| `none_play_as_it_lies` | 0 | 罚杆区内直接打(极常见,草案漏了) |
| `stroke_and_distance` | +1 | 回原杆起点重打(OB/遗失球) |
| `back_on_line` / `lateral_red` / `drop_zone` | +1 | 罚杆区/不可打的抛球选项 |
| `bunker_out_back` | +2 | 沙坑不可打的后方线选项 |
| `e5_local` | +2 | 业余最常用本地规则(OB/遗失侧向抛,目标用户十有八九用它) |
| `free_relief` | 0 | 车道/修理地/临时积水,球合法移动(无此事件,合法移动在图上像数据错误) |

- **`outcome`** 只放特殊结果:`holed / lost_ball / ob / penalty_area / unplayable / pickup / free_relief / unknown`;普通落地只用 `end.course_area/surface`(不再 `outcome=in_bunker` 与 `endLie=bunker` 重复)。
- **坐标断裂 + replay 链接**(OB/遗失球:杆罚**加距离**,下杆回原位):`replay_from_shotId`(下杆起点 = 原杆起点)、`penalty_for_shotId`、`estimated_ob_point?`。**回退线可视化放 v2.1,但这套语义 MVP 必须进**(否则固化错模型、v2.1 要数据迁移)。
- **补齐业余高频**:`lost_ball`(遗失球,常见罚杆源)、`provisional`(暂定球——找到原球后暂定那几杆不计但 Garmin 记了 = 错记大来源,`deleteShot` 删因枚举为它设)、`tap-in/gimme`(推杆系统性少记)、`free_relief`、沙坑 unplayable +2。

## 3. 缺杆:检测 > 推测(重命名 + 三条红线)

- **缺杆检测(有价值、不造假)= 漏记的正解**:前杆落点 ↔ 后杆起点位移超阈值 → 提示「**这里可能漏了一杆**」(纯提示,点进入插入流程)。这才解决「两杆被 Garmin 并成一杆」。
- **缺球杆名(降级)**:`club==null` 时 MVP 直接显示「**未知球杆**」+ 一键手动选杆;推测只作为**选杆器里的默认高亮**,展示层**不写「7号铁?」**(用户会当真;灰字问号的置信语义用户看不见)。
- **三条红线**:① inferred **永不进**球杆档案 / 任何统计聚合(club 数据本就脏 clubId=0,循环污染会毒化 AI 选杆);② **Garmin 几何距离是起点→落点直线位移,不是击球距离**(横偏/dogleg/下坡滚动系统性失真,风坡加重)——别当 carry;③ read-time 计算不入库(可复现),真要存必带推测版本。

## 4. 编辑 / 新增交互(手势定死)

- **iOS 满屏图**:查看态只**平移/缩放**;**切洞用底部洞条/按钮,永不 swipe**(三种单指拖动不可共存);**拖落点用长按拾起再拖**;编辑态显式进出、进入后禁切洞。
- **新增杆 = 从列表「在第 N 杆后插入」**:起点默认 = 前杆落点,触发「**一杆拆两杆**」+ 自动重算相邻杆距离(修复 Garmin 把两杆并一杆)。半吊子增杆(只给终点)会画瞬移连线、比不做更假。或 MVP 只做**无几何杆**(补推杆/补罚杆)。
- **删杆带删因**(暂定球/练习挥/别人的球/误检测)+ **撤销**(错记比漏记更伤信任、成本最低 → 升为 MVP 核心)。
- **网页**:MVP 只读(**必须带 provenance 展示**,家庭多用户要看清「谁改的」);**非几何修正(改球杆/球位/罚杆,纯表单)第二步开放网页**(大屏鼠标批量修 18 洞是重度用户刚需,且无手势冲突)。
- **无几何洞兜底**:满屏图退化为**列表式编辑**。
- **离线**:合并在客户端本地可跑,修正先落本地事件日志(球场上最想改时恰恰没网)。

## 5. 端点(op-based)

- `GET …/holes/{hole}/shotmap`(读取时套修正 + read-time 推导;输出字段级 provenance + 计分调和状态)。
- `POST …/rounds/{ref}/holes/{hole}/corrections`(**append 一条操作事件**,`clientMutationId` 幂等 + `baseRevision` 冲突检测;不再整洞 PUT 覆盖)。
- evidence-isolated per player;tombstone 留删因。

## 6. MVP 边界(重排 —— 三家一致)

**进 MVP(先修模型再上线):**
1. 稳定 ID + **op-based 修正层**(一并解决离线/撤销/审计/AutoShot 共存)。
2. **正确的罚杆/救济模型**(哪怕晚一周;别固化错模型将来做数据迁移)。
3. **删杆 + 删因 + 撤销**(错记 > 漏记,价值/成本比最高)。
4. **计分调和**(否则罚杆一上线洞分自相矛盾)。
5. **缺杆检测提示**(漏记的正解入口)。
6. iOS 满屏查看 + 手势定死;逐杆距离(已 done #238)。

**降级 / 后置:**
- club 推测 → 「未知 + 手动选杆」(最易违铁律、价值最低)。
- 增杆:要么带最简几何链(起点=前杆落点+重算),要么只做无几何杆;不做半吊子。
- **v2.1**:拖动改落点位置、OB 回退线可视化、网页几何编辑、局级修正摘要「本局被修正 3 处」、导出/分享(带 provenance)。

## 7. 三端 + 门控

网页:MVP 只读(带 provenance)→ 第二步表单编辑。iOS:满屏 + 编辑。**Watch:门控**。

---

## 附:评审记录

- 方法:草案 → 3 模型独立对抗评审(狠挑,不夸)→ 收敛。评审档在 homeserver `/home/jason/reviewv2/`。
- 三家一致 top 3:① 数据身份 + op-based 修正层 ② 罚杆模型重做(挂救济不挂落点 + OB stroke&distance + 补 lost/provisional/free-relief + 计分调和)③ MVP 重排(推测降级、删杆+撤销升核心、增杆带几何链)。
- 复用:`ai-review-homeserver` 记了 Codex/Gemini 跑法;Fable 走 Agent。
