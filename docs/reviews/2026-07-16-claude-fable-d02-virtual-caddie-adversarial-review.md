# Claude Fable 5：D02 Virtual Caddie 独立对抗审查

> 日期：2026-07-16 UTC  
> 性质：只读产品设计与工程复用审查，不授权实现  
> 模型：`claude-fable-5`  
> Effort：`max`  
> Fallback：未配置，未发生  
> Claude Code 会话：`2ad07a39-5b32-4079-9078-6021ccc06ee7`  
> 会话日志：`/home/ubuntu/.claude/projects/-home-ubuntu-claude-web-data-repo-garmin-ai-caddie/2ad07a39-5b32-4079-9078-6021ccc06ee7.jsonl`  
> 工具约束：只开放 `Read`、`Grep`、`Glob`；实际调用 `Read ×10`、`Grep ×13`；无 Task/Agent、无 Web、无写文件工具  
> 纯度审计：JSONL 中 47 条 assistant 记录全部为 `claude-fable-5`，非 Fable assistant 记录为 0；CLI `modelUsage` 仅含 `claude-fable-5`；终止原因为 `completed / end_turn`
>
> **2026-07-16 队列更正：**§2.3 的三项不再作为独立 Owner 问题：① C′ 方向本身定义为“当前一杆建议在真实、可信、新鲜时出现”，先只覆盖 Tee 属实施分批与数据降级；② 40/41mm 降级由 E04 原型证据决定；③ companion-only 只是当前契约缺口，独立局目标受 D04 与 D02 共同约束。当前唯一 Owner 问题仍是 D02 的 A/B/C′ 方向选择，见[决策账本](2026-07-15-watch-decision-and-task-tracker.md)。正文保留用于追溯。
>
> **2026-07-17 DECISION：**Owner 已确认“直接对标 S70”，D02 正式落为 `S70 BEHAVIORAL PARITY / C′`；当前唯一 `CURRENT` 是 D04。本文的 A/B/C′ 提问保留为决策历史。

## 1. 最终裁决

**C（修正后采纳），准确命名：「条件单杆球童层——根页只在建议有效、可信、新鲜且模式允许时叠加当前一杆的推荐杆＋瞄准线＋真实纵深散布带，B 是它的法定零状态，A 式多杆确定性路线永久禁止出现在根页」。**

但必须向 Owner 声明：这不是账本里原来的 C。旧 C 写的是“条件显示简化路线”，Codex 新 C 是“条件显示单杆建议层且禁止路线”——主语已换。程序上应作为 C′ 重新呈交，并在账本变更记录里写明“联合建议由 B 改为 C′，依据是新核验的 Garmin 官方产品图与连续实拍”，不得静默改写旧 C 定义。

## 2. 设计合理性

### 2.1 成立点

1. 新证据直接命中：Garmin 官方产品图在标准 Hole View 显示 7I＋瞄准线＋散布框并冠名 `IMPROVED VIRTUAL CADDIE`；实拍根页直接推荐 3W/Driver。这证明 S70 的真实根页形态就是“事实层＋条件建议层”，B（根页零建议）反而偏离了要还原的对象。
2. C′ 的失败模式是优雅的：任何门槛不满足时它逐字退化为 B，根页稳定性论证被完整继承。
3. A 被两路证伪：S70 根页画的是当前一杆，而非 `you → layup → green` 两段整洞路线；仓库现状中 `WatchEventBridge.makeHoleMap` 在没有推荐时把 layup 回退到路线总长 60%，用户看到的“路线”可能与任何真实建议无关。

### 2.2 最强反例

本仓库的散布与期望杆数还没有准备好：

- dispersion 只有 carry 纵深一维：`decision.py:2511-2528` 只有 `carryP10_m/carryP90_m`，没有横向散布统计；
- expectedStrokes 在两条链上是两个不同语义；
- Watch 侧连 p10/p90 都没有收到：`WatchCaddieOption` 只有 clubName、carryM、expectedStrokes、confidence。

如果按当前数据强上 C′，屏上的“真实历史散布区”会变成第二个装饰椭圆。因此 C′ 必须绑定“数据契约先行”；在契约落地前，产品行为恒等于 B。

### 2.3 仍需 Owner 决定的边界

1. 建议层每一杆都可出现，还是 v1 先只做开球杆；实拍显示 Par 5 第二杆也有根页推荐，但“每杆通用”仍属推导。
2. 最小表径（40/41 mm）降级时，先丢散布带，还是整层移入 Map Detail。
3. v1 是否接受“建议层仅 companion 模式可用、Watch 独立局无建议层”；当前独立局的离线建议数据没有进入 Watch 包。

## 3. S70 事实与推导分层

### CONFIRMED

- Virtual Caddie 推荐单杆或组合、可左右切换、显示 `AVG. STROKES` 与该杆历史散布区；散布覆盖果岭时显示上果岭概率；需至少五轮带传感器或 Club Prompt 的数据。
- Golf Settings 有 Automatic / Manual recommendations。
- 官方产品图的标准 Hole View 直接显示 7I、瞄准线与散布框。
- 连续实拍根页推荐 3W/Driver；完整页显示 3W 4.3、Driver 4.5、3H 4.3；方框同时是 landing zone 与个人散布，Driver 散布可能入水，因此推荐 3W。
- 横跨球道的白弧是用户 Driver Distance 设置弧；它与直线瞄准线、散布方框是三种不同对象。
- Big Numbers 是持久模式。
- Tournament Mode 至少禁用 PlaysLike。

### DERIVED

- 红白蓝点对应剩余 100/150/200 码标杆。
- 根页建议按每一杆滚动更新。
- Manual 模式下根页不主动推送推荐。
- 弧线、瞄准线、散布框的精确 z-order 与样式规则。
- 数据不足时建议层整体消失的具体门槛。

### UNKNOWN

- `AVG. STROKES` 的精确公式。
- S70 随 GPS 移动重算建议的频率、TTL 与失效阈值。
- S70 离线或数据陈旧时的根页行为。
- Big Numbers 与 AOD 是否保留球童建议。
- 上果岭概率的计算口径。

## 4. 工程复用矩阵

### 4.1 直接复用

| 资产 | 证据 |
|---|---|
| Canvas 锚点变换与绘图原语（anchors/safe/pill） | `WatchHoleMapView.swift:165-175, 376-382, 422-424` |
| 18 洞成绩环 perimeter 算法（D01 已 KEEP） | `WatchHoleMapView.swift:386-419, 426-454` |
| WGS84 → topo px 仿射投影 | `WatchEventBridge.swift:399-412` |
| 路线插值 `interpRoute` | `WatchEventBridge.swift:416-430` |
| 后端 per-club p10/p90 纵深散布与 sampleSize 管线 | `decision.py:2511-2528`；`live_round_package.schema.json:561-575` |
| high/medium/low 置信度产出链 | `analysis.py:633-636`；`decision.py:1332-1355` |
| topo 图传输与 state 推送通道 | `WatchEventBridge.swift:432-445, 498-513` |
| iPhone 侧 option 提取（已有 p10/p90/sampleSize/confidence） | `CaddiePlanView.swift:60-161` |

### 4.2 修改后复用

| 资产 | 需要的修改 | 证据 |
|---|---|---|
| `WatchCaddieOptionsView` | 作为完整 Caddie 页骨架；补散布带、样本数、校准后杆数 | `WatchCaddieOptionsView.swift:7-84` |
| `WatchCaddieOption` / `WatchRoundStatePayload` | 增补 p10/p90/sampleSize、决策新鲜度与门控字段 | `WatchEventBridge.swift:53-78, 156-209` |
| `CurrentHoleView` 决策与推送链 | GPS 移动触发重算；到旗距离改为 GPS 自动输入 | `CurrentHoleView.swift:168-197, 924-960, 1194-1199` |
| `WatchHoleMapView` | 保留左栏与地图底座；两段路线改为条件单杆线；chip 变成可点 Button | `WatchHoleMapView.swift:145-213, 296-301` |
| `makeHoleMap` | 曲线控制点留给 Map Detail；没有真实决策时推荐 layup 必须为 nil | `WatchEventBridge.swift:376-394` |

### 4.3 必须淘汰

| 行为 | 理由 | 证据 |
|---|---|---|
| 固定 30×26 px 装饰散布椭圆 | 与真实历史散布冲突 | `WatchHoleMapView.swift:304-308` |
| 无条件常驻的 `you → layup → green` 两段路线 | layup 可为 60% 纯猜测 | `WatchHoleMapView.swift:296-301`；`WatchEventBridge.swift:382` |
| `suggestedClub ?? options.first ?? selectedClub ?? "—"` 的 chip 回退链 | 会把用户自选杆冒充球童推荐 | `WatchRoundContainerView.swift:146-153` |
| 没有绑定行为的表冠缩放指示 | 假 affordance | `WatchHoleMapView.swift:229-244` |
| `yardsPerPx` 像素比例测距 | 不是真正的地理反投影 | `WatchHoleMapView.swift:95-108` |
| `showPlaysLike: s.elevationDeltaM != nil` 默认开启 | S70 默认显示实际距离 | `WatchRoundContainerView.swift:179-181` |
| 长按临时“大字” | Big Numbers 是持久模式 | `WatchHoleMapView.swift:159`；`WatchRoundContainerView.swift:62-79` |
| 面向用户显示未校准“期望 x.x” | 双语义且未校准 | `WatchCaddieOptionsView.swift:53-55` |

## 5. 必须修改的数据契约、状态机、UI 与算法

### 5.1 数据契约

1. `WatchCaddieOption` 增补 `p10M`、`p90M`、`sampleSize`。当前没有横向散布，v1 只能画“沿瞄准线的纵深散布带”，不得命名为完整“散布框”。
2. `targetWindow` 是写死的 4–16 m 启发式宽度，只能作为内部瞄准容差，永远不得渲染成用户历史散布。
3. 拆开 expectedStrokes 的双语义：
   - sequence 链改名 `plannedShots`；
   - scoreImpact 启发式改名 `strokesEstimateUncalibrated`；
   - 新增 `avgStrokesCalibrated?`，只有真实历史 strokes-to-holeout 回验过线后才允许显示 Garmin 式“平均 4.3”。
4. payload 增加 `decisionComputedAt`、`decisionComputedForDistanceM` 或起算坐标、`recommendationMode`、`tournamentMode`、`caddieEnabled`。
5. 新增显式 `currentShotTargetPx/Geo`，与 `holeMap.layup` 解耦；后端已有 `targetLocal`，缺少的是投影与下发。
6. Watch 独立局若要显示建议层，Watch 包必须携带 per-hole 离线 options；否则 v1 明文限定为 companion 模式。

### 5.2 状态机

建议层采用：

- `visible(fresh)`；
- `hidden(reason)`，其中 reason 包括 `insufficientData`、`stale`、`manualMode`、`tournament`、`caddieOff`、`offlineNoSeed`、`computing`。

失效事件包括：GPS 位移超阈值、记杆、换洞、策略切换、TTL 到期、companion 断连。必须加滞回，避免 GPS 抖动导致建议层闪烁。建议出现或消失不发触觉，因为它是意见层，不应占用中断预算。

建议可见门槛：`confidence == high`（medium 是否放行交给原型验证）、`dispersion.state == modeled`、`sampleSize ≥ MIN_STRONG_CLUB_SAMPLE` 且数据新鲜。当前 Watch 虽收到 `caddieConfidence`，但没有任何门控读取。

### 5.3 UI 交互

- 推荐 chip 改为真实 Button，点击进入完整 Caddie。
- 根页地图 tap 改为进入 Map Detail；选点测距与拖旗迁入 Map Detail / Green View。
- Driver Arc 与 AI 线视觉隔离：弧为细白事实层，仅 Par 4/5 首杆前显示；AI 线为绿色、更粗，随建议层出现和消失。
- Big Numbers 改为持久模式且不显示建议层；AOD 只显示事实。
- 40/41 mm 降级顺序：先去掉散布带、保留 chip＋线；再降为仅 chip。

### 5.4 算法

1. companion 模式下，球员位移超过工程阈值后重新计算建议。当前 GPS 更新只重推旧决策，导致 F/M/B 已按 Watch GPS 更新，而推荐杆仍来自旧位置。
2. Watch 侧用自身 GPS 与 `decisionComputedForDistanceM` 比较；偏差超限时主动隐藏建议层。
3. v1 纵深散布带由 p10/p90 沿瞄准方向投影。
4. 上果岭概率需要散布覆盖果岭 mesh 与校准模型，v1 不做。

## 6. 对 Codex 提案逐条裁决

1. 根页常驻洞号、Par、F/M/B、地图、成绩环、球员位置，以及有真实数据时的 Driver Arc：**ACCEPT**。Driver Arc 使用本产品实测 medianM 是平台翻译，不是 Garmin 的同一数据源，必须有样本门槛。
2. 有效且足够可信时显示推荐杆、瞄准线与真实散布区：**MODIFY**。门槛必须可执行；v1 只能如实显示纵深散布带；必须加滞回。
3. 点击推荐杆进入完整 Caddie：**MODIFY**。方案结构可接受；校准过线前不得显示绝对预期杆数。
4. 数据不足、过期、球童关闭或 Tournament Mode 时整层消失：**ACCEPT**，但还必须覆盖 Manual recommendations、companion 断连、Big Numbers 与 AOD。
5. 根页不画确定性多杆路线：**ACCEPT**，并升级为硬不变量。整洞计划只进入 Caddie 详情或 Map Detail，并明确标为计划。
6. 直接把新方案继续叫旧 C：**REJECT**。必须作为 C′ 重新提交，并保留旧建议 B 被新证据推翻的变更记录。

## 7. 给 Owner 的唯一 D02 问题

> 根页洞图上的球童呈现采用哪种形态？
>
> - A：常驻 `you → layup → green` 整洞路线（现状延续）。
> - B：根页零建议，全部进入详情。
> - C′：条件单杆球童层——门槛满足时显示推荐杆、当前一杆瞄准线、真实纵深散布带；任一门槛不满足时整层消失，根页自动退化为 B。

**Fable 推荐 C′。** 它同时满足 S70 官方图与实拍确认的根页形态、B 方案的稳定零状态，以及“不展示未校准数字、不伪造散布”的数据诚实约束。
