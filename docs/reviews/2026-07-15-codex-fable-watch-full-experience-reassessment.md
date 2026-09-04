# Apple Watch 全体验重审：S70 体感、AutoShot、计分、可靠性与工程复用

> 日期：2026-07-15 UTC
> 状态：JOINT DESIGN REVIEW，尚未成为实施规格
> 共同审查：Codex、Claude Fable 5、并行只读代码审查
> 范围：Apple Watch 完整高尔夫旅程，以及与 iPhone、Web、统一后端的必要接口
> 顺序：先判断设计合理性，再判断工程复用，最后提出修改与验证路线
> 保留原则：既有代码、旧评审、旧规格和 mockup 全部保留；本文件提出权威级别调整建议，用户确认前旧文档权威级别不变
>
> **2026-07-16 AUTHORITY CORRECTION：**本文件仍是重要 review input，但不再定义当前 Owner 队列。其“还有两个用户门 / 旧文档降级需 Owner 确认”等表述已被[决策账本](2026-07-15-watch-decision-and-task-tracker.md)和[纯 Fable 队列终审](2026-07-16-claude-fable-watch-owner-decision-queue-final-adversarial-review.md)取代：当前唯一 `CURRENT` 是 D02，下一项是 D04；D03 已重分类为工程治理。正文保留用于追溯，不得据此重新制造 D03 用户门。
>
> **2026-07-17 QUEUE PROGRESSION：**D02 已确认直接对标 S70 并落为 `DECIDED / S70 BEHAVIORAL PARITY / C′`；当前唯一 `CURRENT` 是 D04。上段 D02-current 描述是 07-16 快照。

---

## 0. 这次重审的结论

### 0.1 不能再把问题定义成“AutoShot 做不做”

AutoShot 很重要，而且这次判断比旧文档更进取：

- 可以现在直接建设 AutoShot 产品 Beta；
- 第一版应明确支持前导腕、非推杆、完整挥杆；
- 高置信候选直接持久化并进入 Club Prompt；
- 中置信候选等待移动、同点后续击球和 GPS 证据；
- 手动补杆、误检删除、改杆和“打厚了”永久存在；
- 短切、沙坑、旧设备和 trailing wrist 不能被虚假宣传成已解决。

但 AutoShot 只是逐杆事实的一个 producer。完整 Watch 产品还必须同时解决：

- 真实球局如何进入 Watch；
- 抬腕第一眼是什么；
- 地图、障碍、PlaysLike、Green View、PinPointer 如何工作；
- 记分、逐杆和当前洞如何保持独立；
- Club Prompt、成绩确认、换洞、AOD、来电和低电如何仲裁；
- Pause、Finish、离线、崩溃和同步如何不丢数据；
- 用户如何随时修改任意洞而不破坏正在打的洞。

### 0.2 当前 Watch 不能评价为“S70 已做大半，只差几个功能”

源码核验得到一个更上游的事实：

- 生产存在 standalone Hub、手机推送 legacy List、固定全 Par 4 练习局三套互斥路径；
- 真实手机球局没有调用 WatchRoundModel.seedRound 或 WatchRoundStore.upsertHoleState；
- 富地图、腕上 GPS、完整计分卡所在的 standalone 分支拿不到真实球场；
- legacy 分支能收到手机当前洞状态，但不渲染已经传输的 topo 地图；
- 因而当前最漂亮的一批 Watch 快照更接近“可复用原型资产”，不是完整生产旅程。

正确表述是：

> 当前仓库已经拥有地图、几何、距离、同步和若干 UI 零件，但真实球场 Watch 产品闭环还没有接通。

### 0.3 三页和五页都不是推荐答案

本轮重新比较后：

- 五页横滑淘汰；
- 三页横滑不作为产品方向，也不预先投入可交互原型预算；
- 推荐“单一当前洞根页 + 浅推入仪表面 + 单一决策浮层”。

只有当单根页田测证明工具入口不可发现时，才重启三页评估。

这不是把功能砍成一页。它表示：

- 只有当前洞是根；
- Map Detail、Green View、Caddie、Score、PinPointer、Big Numbers、Scorecard 等都是围绕当前洞切换的仪表面；
- 自动提示不能把用户随机带到另一个兄弟页；
- 抬腕、AOD 和恢复都只有一个稳定基底。

### 0.4 推荐采用“产品模型忠实 S70、导航实现尊重 Apple”的混合路线

复制 S70 的内容优先级与仪表心智：

- 洞号和 Par；
- 后/中/前距离，中距最大且醒目；
- 右侧洞图；
- 顶部上一杆；
- Golf Menu 围绕同一当前洞；
- Green View 独立；
- PlaysLike 由实际距离切换；
- Club Prompt 只补球杆；
- 洞末成绩手动确认；
- 自动换洞有人工恢复。

翻译成 Apple Watch：

- 无法复制 S70 的 Action/Back/三物理键；
- 使用一个稳定、可见的“球局工具”入口；
- 使用系统返回和浅层 NavigationStack 或等价原生导航；
- 表冠只控制当前仪表面的唯一轴；
- Ultra Action Button、AOD 和高频运动 API 都只能是增强，标准表仍须完整成立。

主动修正 Garmin 缺陷：

- 漏杆不要求用户仍站在原地才能补；
- 风和动态数据必须显示来源与时效；
- 错洞、误杆、未选杆和忘记结束都有可恢复状态；
- 结束不能清空未同步数据；
- 赛后修改走追加修正，不覆盖历史事实。

---

## 1. 为什么之前讨论很久仍然漏掉三页/五页和其它设计问题

### 1.1 把既有规格当成约束，而不是待评估假设

2026-07-10 的 Watch 文档把五页写成“操控宪法”“定案”。后续工程评审自然更容易问：

- 实现是否符合五页；
- 哪些页面没做；
- 表冠有没有接上。

而没有先问：

- 五页本身是否符合真实打球频率；
- 低频计分和高频读距为什么要同级；
- S70 实际是不是五个兄弟页。

### 1.2 分析单位过窄

Round 1/2 的主要分析单位是“一洞四个时刻”：

1. 球前抬腕；
2. 击球后；
3. 走下果岭；
4. 到下一 Tee。

这个模型适合讨论 AutoShot、记分和换洞，却天然压缩了：

- 选场、GPS、发球台、起始洞；
- 离线包与独立模式；
- Big Numbers、PinPointer、Green View；
- Pause、9→10 会所休息、雷雨；
- 雨天、湿屏、手套、AOD；
- 跳洞、shotgun、双果岭；
- Finish、同步、赛后编辑。

### 1.3 AutoShot 的技术难度吸走了横向评估预算

挥杆识别、10 码、practice swing、OB、换洞归属都很有技术深度。分析容易在一个分支上继续向下挖，却没有回到能力树检查其它分支是否同样完整。

### 1.4 快照可渲染被误认为生产可达

WatchDesignSnapshotTests 能渲染富地图，并不等于真实用户能进入该路径。此前没有单独做“生产可达性审计”，所以：

- 测试中的 seedRound；
- 生产中的 legacy currentState；
- 练习局的固定洞；
- 手机传来的 topo 文件

被混在一起理解成了一套已经贯通的产品。

### 1.5 没有建立逐项 S70 能力追踪表

旧讨论中“菜单里提过”常被视为“已经设计”，但以下能力实际上没有完整入口、状态、恢复和验证：

- Big Numbers；
- Green View；
- PinPointer；
- Change Green；
- Pause/Resume；
- Tournament Mode；
- Wind/Air Density；
- Round Info；
- Club Stats；
- Lock/Auto Lock；
- 结束前数据清点。

---

## 2. 判断最优 Watch 设计的标准

### 2.1 高频任务必须成为根

| 任务 | 每轮频率 | 推荐层级 |
|---|---:|---|
| 抬腕看后/中/前与当前洞 | 30–60 次 | 唯一根页 |
| 看上一杆、GPS 状态 | 10–40 次 | 根页事实层 |
| 查看地图目标或障碍 | 若干次 | 从根页一次进入 |
| AutoShot 后补球杆 | 每个被识别的非推杆 | 单一决策浮层 |
| 确认本洞成绩 | 9/18 次 | 自动债务或明确入口 |
| 修改历史洞 | 少量 | Scorecard 推入 |
| Green View、PinPointer | 条件性 | Golf Menu 仪表面 |
| Pause、结束、设置 | 低频 | Golf Menu |

### 2.2 事实、推断和意见必须分层

- 事实：洞号、Par、GPS、F/M/B、用户确认成绩、已持久化击球。
- 推断：当前洞候选、AutoShot 置信、默认成绩、startLie、fairway 默认。
- 意见：推荐球杆、打法、目标、平均预计杆数。

低置信推断不能伪装成事实；意见不能自动写成用户实际使用的球杆。

### 2.3 所有自动化必须可逆

- AutoShot 候选可 reject 或 correction；
- 换洞可撤销或重新分配；
- “打厚了”恢复隐藏观察，不物理删除；
- 赛后修改追加 revision；
- 结束前后都不清除未同步 ledger。

### 2.4 标准表必须独立成立

不能把以下能力当成产品成立前提：

- Ultra Action Button；
- AOD；
- Series 8+ 高频传感器；
- 手机实时在线；
- 动态风；
- 完整球场几何。

这些能力可增强体验，但最小产品必须在标准表、无 AOD、无 Ultra、离线和 GPS 降级时仍可完成球局。

---

## 3. 三种总体 IA 方案

### 3.1 方案 A：S70 仪器模型

结构：

    当前洞根页
      ├─ Map Detail
      ├─ Green View
      ├─ Caddie
      ├─ Score
      ├─ PinPointer
      ├─ Big Numbers
      └─ Golf Menu → Scorecard / Change Hole / Pause / Finish / Settings

优点：

- 与 S70 的当前洞心智同构；
- 抬腕恢复稳定；
- 自动提示只有一个基底；
- 高频读距不与低频功能争夺顶层导航。

风险：

- Apple Watch 没有 S70 Action 键；
- 必须验证“球局工具”入口的发现性；
- 自定义仪表面需要更严格的焦点、AOD 和可访问性设计。

### 3.2 方案 B：Apple 原生仪表栈

结构仍是单一当前洞，但最大化使用：

- NavigationStack；
- 系统 Toolbar；
- 系统 Sheet；
- 系统 List/Picker；
- 系统返回。

优点：

- 平台风险最低；
- VoiceOver、Dynamic Type、返回和焦点更可靠；
- 更容易处理系统通知与恢复。

风险：

- 容易变成普通 Watch 小 App；
- 默认系统密度未必满足烈日下三秒读数；
- S70 的专用仪器感较弱。

### 3.3 方案 C：三页横滑

示例：

    球童 — 当前洞 — 计分

优点：

- 比五页简单；
- 两个高关注入口离当前洞近；
- 容易做演示。

问题：

- 球童和计分仍被抬到与每杆读距同级；
- 横滑与湿手、手套、地图触摸冲突；
- 抬腕可能恢复在计分页而不是当前洞；
- Club Prompt 与成绩确认仍需独立浮层，三页并没有解决中断模型；
- 表冠在页面、地图和计分之间容易发生语义争夺。

### 3.4 联合推荐

推荐采用：

> 方案 A 的产品模型 + 方案 B 的原生导航纪律。

五页直接淘汰；三页只保留纸面对照，不进入正式信息架构。Track A 若证明新用户无法在三洞内自行找到 Green View、计分和球局工具，才触发三页方案重开。

Map Detail 的表冠语义仍保留一项 Round 2 未决：

- 默认假设：表冠显式缩放，点按选择目标；
- 对照臂：表冠沿障碍/layup/旗位的目标停点轴。

两者应在同一个原型构建中切换配置同场测试。不能因为合稿时偏好 S70 忠实就静默抹掉目标轴候选。

---

## 4. 推荐的当前洞根页

### 4.1 首帧不可删事实

- 洞号；
- Par；
- 后/中/前距离；
- 中距最大、黄色或同等级高对比强调；
- 右侧洞图；
- 上一杆距离；
- GPS 质量仅在劣化时出现。

### 4.2 有条件出现

- 一行 AI 建议：仅在输入有效、样本与置信门槛满足时；
- Driver Distance 弧线：仅在真实球杆距离存在时；
- scoreDebt、未选杆、换洞候选等状态标；
- 手动记杆入口：AutoShot 不可用时升格，正常时保留在上一杆/球局工具中。

### 4.3 不应常驻

- 固定散布椭圆；
- 同步成功状态；
- 未校准 expected strokes；
- 多个小按钮；
- 假 Digital Crown 轨道。

### 4.4 既有 Owner 决定与证据更正

以下两项曾经被用户看过或明确要求保留，本轮不能由 Codex 与 Fable 静默删除：

- 18 洞成绩环；
- 地图上的球童路线。

**2026-07-15 成绩环证据更正**：此前联合稿建议将成绩环移出 Hole Root，部分依据是旧研究错误声称“S70 没有 18 段边缘成绩环”。Garmin 官方 `Score History` 明确证明：S70 的实体表圈刻有 1–18 洞指示，屏幕在各洞号旁绘制逐洞成绩色段。因此该建议撤回，恢复用户此前的 KEEP 决定；完整证据见 [S70 成绩环证据更正](2026-07-15-s70-score-history-ring-evidence-correction.md)。

更正后的联合建议是：

- 成绩环保留在 Hole Root，作为 S70“物理洞号刻度 + 屏内动态成绩色段”的 Apple Watch 平台翻译；只对矩形几何、当前/未打状态和交互态隐藏时机做原型；
- 球童路线从 Hole Root 移到 Map Detail/Caddie，根页只保留一行建议。

成绩环不再申请重开；球童路线在用户确认前仍维持既有决定。

### 4.5 根页表冠

推荐根页本身不占用表冠：

- 根页是抬腕即读的事实面；
- 点洞图进入 Map Detail 后，表冠才成为缩放；
- Score、Caddie、列表各自在自己的表面拥有唯一轴。

这一点仍需真机原型比较“根页无轴”和“根页直接缩放”两种方案。进入 Map Detail 后，还要比较“缩放轴”和“目标停点轴”；任何候选都不得再画出没有绑定的表冠提示。

---

## 5. 完整球局旅程

### 5.1 赛前与开局

目标流程与首版归属面：

| 步骤 | 首版归属 |
|---|---|
| 恢复未结束球局，或从已准备/缓存的真实球场包开始新球局 | Watch 可完成 |
| GPS 搜索附近球场 | iPhone 准备为基线；Watch 冷启动缓存场为后续能力 |
| 附近仅一场自动选定，多场时选择 | iPhone 基线；Watch 缓存模式后续 |
| 选择 9/18 洞、环组合、发球台 | iPhone 准备，结果写入整轮包 |
| 选择记分、统计、Club Prompt、AutoShot Beta、Tournament Mode | iPhone 设置；Watch 可快速覆盖本轮设置 |
| 显示 Watch/离线准备状态 | iPhone 与 Watch 均显示 |
| 根据 tee 位置建议起始洞，允许 shotgun | Watch |
| 启动 Golf Workout、GPS、Motion 与 round ledger | Watch |
| 进入当前洞根页 | Watch |

首版独立边界：

> iPhone 负责准备真实球场整轮包；开球后 Watch 可以在手机不在线的情况下完整打完、暂停、结束并保留待同步数据。

降级：

- 无网：使用已缓存球场；
- 无 GPS：最近/常打球场，但标明依据；
- 无几何：纯距离或纯记分；
- HealthKit/Motion 被拒绝：AutoShot 不运行，测距、记分和手动补杆仍可用；
- 手机不在：已准备整轮包后继续。

### 5.2 球前抬腕

用户首先看：

- 当前洞；
- 后/中/前；
- 洞图；
- 上一杆；
- 必要时一行建议。

用户可：

- 点地图进入 Map Detail；
- 点距离切 actual/PlaysLike；
- 点建议进入 Caddie；
- 打开 Golf Menu；
- 打开 Big Numbers。

### 5.3 击球与 Club Prompt

正确顺序：

1. AutoShot 或手动 producer 产生 candidateShot；
2. 本地 append-only ledger 成功；
3. 才播放一次“已保存候选”触觉；
4. PresentationCoordinator 判断是否可以显示 Club Prompt；
5. 用户选杆或“跳过球杆”；
6. 跳过只留下 club unknown；
7. 只有明确“误检”才 reject 击球。

Club Prompt 不负责证明这是不是一杆，也不能自动把推荐杆写成实际杆。

### 5.4 地图、障碍、PlaysLike 与果岭

Map Detail：

- 表冠缩放；
- 点选目标；
- 同时显示当前位置→目标、目标→旗；
- 无自由平移，保持你→旗框架；
- 障碍显示前后沿；
- target、pin 和视图状态按产品规则持久。

PlaysLike：

- 默认 actual；
- 点距离切换；
- v1 详情只显示已核实的高差；
- **2026-07-16 OWNER-SCOPE CORRECTION**：风与空气密度这里只能作为 S70 事实和未来重开研究输入，不能进入现行 v1 规格。Owner 在 `2026-07-02-unified-tri-surface-spec.md:29,146` 已明确“风：不做”；任何加回都必须先备齐来源/精度/TTL/离线/续航证据，再由 Owner 显式重开；
- Tournament Mode 禁用相应能力。

Green View：

- 独立放大果岭面；
- 表冠缩放；
- 只在这里拖旗；
- pinSet 是本轮事件；
- 返回后 F/M/B 与建议重算。

PinPointer：

- 独立仪表面；
- 需要 heading 质量门；
- 罗盘受干扰时明确降级。

### 5.5 离开上一洞与到下一 Tee

位置引擎可以产生 transitionCandidate，但：

- 到下一 Tee 不等于换洞；
- 当前洞、成绩、击球是三条独立事实链；
- 尚未开球时，根页只显示一次小签并震动一次；
- 已产生下一洞候选杆时，建立 ResolutionEpisode。

换洞自动化三档：

1. v1 默认：确认式小签；
2. 原型对照：高置信自动推进，但有持续可见宣告和可撤销期；
3. S70 式全自动：仅作为用户主动开启的设置，必须等 tee anchors 与田测基线通过。

成绩永远不驱动换洞；scoreState 只能作为位置引擎的辅助证据。

### 5.6 上一洞未确认，但已经打了下一洞第一杆

必须先持久化候选杆，不改变当前洞，不弹 Club Prompt。

抬腕后仍显示上一洞成绩确认：

- 快速接受默认成绩；
- 手动检查；
- 继续上一洞。

快速接受原子完成：

- 确认上一洞成绩；
- 接受洞推进；
- 将候选杆分配为下一洞第一杆。

继续上一洞：

- reject 本次洞推进；
- 将候选杆归到上一洞；
- 继续上一洞记录；
- 不自动确认成绩。

完成归属后，仍新鲜的 Club Prompt 才可显示。

### 5.7 Pause、Finish 与赛后

Pause：

- 保存生命周期、草稿、未决候选和 resume token；
- 传感器停止或降级；
- 恢复时回到未完成的用户任务，而不是随机根页。

Finish Preflight：

- 未确认洞；
- 未决换洞；
- 未选杆；
- 用户已经提出的误检/打厚问题；
- 账本正负差额已经暴露的问题；
- 同步状态；
- 低电或 GPS 降级说明。

Finish Preflight 不得为了“清点完整”而把全部隐藏近距 observation 强制翻出来；没有用户动作或账本差额证据时，仍保持隐藏。

出口：

- Save；
- Edit Score；
- Pause；
- Discard。

除明确 Discard 外，只能进入 finishedPendingSync，不能清空 ledger。

---

## 6. 六组必须正交的状态

### 6.1 RoundLifecycle

- idle；
- preparing；
- active；
- paused；
- finishPreflight；
- finishedPendingSync；
- synced；
- discarded。

### 6.2 ShotLedger

- motionObservation；
- shotCandidate；
- shotStation；
- confirmed；
- rejected；
- superseded；
- correction。

### 6.3 ScoreState

- none；
- scoreDebt；
- draft；
- confirmed；
- corrected。

### 6.4 HoleState

- stable；
- transitionCandidate；
- advanced；
- rejected；
- corrected。

### 6.5 ResolutionEpisode

专门连接：

- 上一洞未确认；
- 下一洞候选；
- 暂存的开球杆。

它是工作流，不是新的事实源。

复杂度上限：

- 任意时刻至多一个未决 ResolutionEpisode；
- 如果第二次换洞候选出现，旧 episode 降级为纯 scoreDebt；
- 旧 episode 解绑权威逐杆归属；原始 shot 只保留 displayedHoleAtCapture 与位置证据；
- 另追加 provisionalAssignment(holeAtCapture, reason: episodeOverflow)，它不是最终事实，允许后续 correction；
- 不允许形成多洞嵌套 episode 链。

### 6.6 PresentationCoordinator

- 一个交易浮层槽；
- 一个状态警告层；
- 一个持久待处理队列；
- 一个 AOD 事实投影。

不能继续用单一 screen 枚举表示全部产品状态。

---

## 7. 计分设计

### 7.1 快速接受

成绩确认首屏显示：

- 第 N 洞；
- 推荐总杆；
- 推荐推杆；
- Par 4/5 的推荐 HIT/LEFT/RIGHT；
- 推荐罚杆；
- 一行以内的推荐依据与置信摘要；详细证据点开查看。

主操作：

- 确认推荐；
- 详细修改；
- 在换洞冲突中显示“继续上一洞”。

点击确认后：

- 一次原子写入本洞成绩；
- 不再追问推杆、球道和罚杆；
- 不自动修改逐杆账本。

如果 fairway 无可靠位置证据，允许该统计保持缺失；不能为了快速确认伪造 HIT。

### 7.2 手动完整确认

依次引导：

1. 总杆；
2. 推杆；
3. Par 4/5 的 HIT、LEFT、RIGHT；
4. 罚杆；
5. 复核与保存。

Par 3 不问 fairway。推杆是统计项，不再次增加总杆。

### 7.3 默认成绩

scoreRecommendation 必须是明确的推断对象，至少包含：

- total；
- putts；
- fairwayResult 或缺失；
- penalty；
- confidence；
- evidence；
- generatedAt；
- invalidation reason。

它可以使用：

- 已确认非推杆击球；
- 球位进展；
- 是否到达/离开果岭；
- 个人推杆先验；
- 历史洞型；
- 用户手动信息。

它永远不能在未点击时变成已确认成绩。

### 7.4 任意洞修改

必须分开：

- activePlayHole：实际正在打的洞；
- editingHole：当前打开修改的洞。

硬门：

> 在第 8 洞修改第 3 洞，保存后仍处于第 8 洞。

当前代码 selectHole 与 record 都会污染 activeHole，必须重设计。

---

## 8. Fairway 与每杆球位语义

### 8.1 fairwayResult

用户可见值只有：

- HIT：上球道；
- LEFT：没上球道，偏左；
- RIGHT：没上球道，偏右。

不是球道内部左/中/右。

### 8.2 startLie

每杆记录的是击球发生时球所在区域：

- TeeBox；
- Fairway；
- Rough；
- Bunker；
- Unknown。

普通无 CT10 的非推杆主流程不需要 Water 或 Green 作为可选项；schema 可保留兼容字段。

endLie 独立保留，用于落点与赛后分析；不能用下一杆 startLie 静默覆盖用户已经修正的 endLie。

### 8.3 fairway 默认推断

Par 4/5 可根据第二个 shotStation 的 startLie 与球洞中轴推断：

- Fairway → HIT；
- Rough/Bunker 且位于中轴左侧 → LEFT；
- Rough/Bunker 且位于中轴右侧 → RIGHT；
- GPS、几何或 startLie 不可靠 → 缺失。

该推断只是默认选项，用户随时可改。

这不是免费推断。startLie 分类依赖：

- fairway、rough、bunker 等地表面几何；
- shotStation 的可靠位置；
- 球洞中轴或 route；
- 明确的计算归属。

当前后端几何存在 surface 数据，但 Watch 整轮包尚未携带该契约。实现前必须在两种路线中裁决：

1. 将压缩后的 surface 多边形加入整轮包，在 Watch 本地推断；
2. 由 iPhone/服务端计算默认值，Watch 只消费带来源与时效的结果。

先量化每洞 surface 包体积；不能把这条能力写成无成本 UI 默认。

---

## 9. AutoShot：三条路线与联合推荐

### 9.1 路线一：纯规则实时检测

使用：

- 挥杆时序；
- 旋转序列；
- 高频加速度；
- 冲击与回震；
- 减速与随挥；
- GPS 静止/移动；
- 球场上下文；
- 同位置后续击球。

优点：

- 可立即开发；
- 可解释；
- 不等待训练集。

风险：

- 阈值跨球员、设备和杆型不稳定；
- 轻切、沙坑和擦地练习挥困难。

### 9.2 路线二：只做影子采集，等待模型

先采样，再通过补杆、删除误检、“打厚了”和视频标注训练 Core ML。

优点：

- 长期可能有更好泛化。

问题：

- 容易再次把 AutoShot 无限后置；
- 只有洞末总杆只能提供弱监督；
- 用户不会因为未来模型而立刻获得价值。

### 9.3 路线三：规则状态机 + 置信分级 + 后续模型

推荐路线：

- 高置信：正式 candidateShot，显示 Club Prompt；
- 中置信：静默候选，等待移动和下一站证据；
- 低置信：不打扰，仅按隐私策略抽样训练；
- 后续模型替换 confidence evaluator，不改 ledger、UI、10 码分组和计分语义。

### 9.4 Apple Watch 技术判断

分级结论：

- PLATFORM-CONFIRMED：Apple WWDC23 说明 CMBatchedSensorManager 提供高频批量运动数据，且明确以 golf 为用例；
- PLATFORM-CONFIRMED：高频采集需要活动 Workout；
- PLATFORM-CONFIRMED：Series 8/Ultra 一代存在该高频能力；产品仍必须运行时检查，不能只硬编码机型；
- VENDOR-CLAIM/SINGLE-SOURCE：Golfshot 官网与其支持中心声称较老 Apple Watch 可运行 Auto Shot Tracking；
- DERIVED：这使低频路径“值得验证”，但同一厂商资料不能独立证明本产品的 100Hz 路线可达到量产质量；
- DERIVED：不能等 100Hz 先检测再临时打开高频，因为击球冲击已经过去；
- UNKNOWN：从击球到 Club Prompt 的产品延迟分布。真机验证前只采用“目标不超过 3 秒”的设计假设，不再写 0–1 秒承诺。

参考：

- Apple WWDC23 What’s new in Core Motion：https://developer.apple.com/videos/play/wwdc2023/10179/
- Apple Running workout sessions：https://developer.apple.com/documentation/healthkit/running-workout-sessions
- Golfshot Auto Shot Tracking：https://golfshot.com/auto-shot-tracking-golf-app
- Golfshot practice swing handling：https://shotzoom.zendesk.com/hc/en-us/articles/360063096553-What-if-Auto-Shot-Tracking-records-practice-swings

推荐：

- 首批：运行时确认高频能力的设备；
- 第二批：旧设备 100Hz，先影子采集，达到独立设备门后再开放 Beta；
- 所有设备：手动补杆永久存在；
- trailing wrist 和推杆不进入首版承诺。

旧设备升级条件必须写死为同样的硬不变量、独立续航曲线和按设备分组的误报/漏报门，不能用“以后再看”无限后置。

### 9.5 推荐状态机

    Active Golf Workout
      → IMU/GPS 时间环缓冲
      → 高尔夫式旋转候选
      → 冲击/减速/随挥验证
      → motionObservation
      → shotCandidate
      → shotStation
      → 高置信 Club Prompt
      → 移动后固化 station

关键约束：

- GPS 使用击球时附近的历史 fix，不使用批量数据到达时的位置；
- Motion 与 Location 时间轴必须统一；
- 先落盘，后触觉，后 UI；
- 不整轮持久化原始 800Hz 数据；
- Beta opt-in 才保存少量压缩窗口；
- 传感器不可用时明确降级。

### 9.6 直接产品化与影子边界

可直接做产品 Beta：

- Workout/Motion/GPS 生命周期；
- 首批高频设备上的前导腕完整挥杆；
- 高置信候选；
- Club Prompt 选择/跳过；
- 手动补杆、误检删除、改杆；
- 同点 last-wins；
- 约 10 码 shotStation；
- “打厚了”拆分；
- 崩溃恢复与离线 ledger。

先影子或低置信：

- 旧设备 100Hz，直到独立设备门通过；
- 极轻 chip；
- 半挥 wedge；
- 沙坑特殊动作；
- trailing wrist；
- GPS 严重漂移；
- 擦地练习挥与真实打厚的自动语义区分；
- 推杆。

Beta 对外开放前，必须先完成“五小时高频 + GPS + Workout”续航 spike。若续航不成立，先设计明确降级，不得在球场上临时静默停用 AutoShot。

### 9.7 发布门

不可只写一个全局准确率。必须按：

- 设备；
- 佩戴腕；
- 左右手；
- 杆型；
- 球位；
- 步行/球车；
- GPS 质量

分别报告。

硬不变量：

- 中低置信不改成绩；
- 不自动换洞；
- 不自动写实际球杆；
- 已持久化候选零丢失；
- 强杀、重启、断网可 replay；
- 手动修正永远胜过旧自动结果。

性能门槛应先取得 S70、Golfshot 和本产品基线后再冻结；旧报告里的任意小样本百分比不能直接成为 GA 标准。

---

## 10. 同位置、Tee last-wins 与“打厚了”

### 10.1 shotStation

原始观察不删除：

    observation A
    observation B
        → 同一 shotStation
        → primaryObservation = B

普通用户默认只看到最后一杆。

### 10.2 Tee

- 同一 Tee 多次击球，默认只显示最后一杆；
- 中途离开再回来也不改变 last-wins；
- 不为 OB、Mulligan、暂定球建立独立恢复 UI；
- 总杆与罚杆仍由成绩系统负责；
- Tee cluster 不主动推荐“打厚了”。

### 10.3 非 Tee 的约 10 码分组

- 约 10 码来自 Garmin 原始数据实证，不是官方规格；
- GPS 精度跨阈值时保持 pending；
- 阈值应结合 accuracy、时间、移动路径和下一站证据；
- 原始候选保留，避免失去恢复能力。

### 10.4 “打厚了”的最终语义

唯一拆分原因：

> 前一杆确实只打了很短距离，下一次击球发生在附近位置。

恢复后：

- 前一杆起点 = 被覆盖 observation 的位置；
- 前一杆终点 = 下一次击球位置；
- 后一杆继续从下一次击球位置出发；
- 不自动修改已确认总成绩；
- correction reason = fat_or_very_short；
- append correction，不物理删除。

### 10.5 三个 UI 入口

推荐主入口一：上一杆热区

    上一杆 N 码
      → 打厚了，补回 1 杆
      → 改球杆
      → 误检/撤销
      → 查看本洞击球

推荐主入口二：洞末差额

出现时机限定为：

- 用户完成成绩确认后的对账区；
- 计分卡/本洞击球详情；
- 不在击球间隙主动弹窗。

仅当：

- 总成绩比逐杆账本多 1 杆；
- 非 Tee station 存在被覆盖的近距 observation。

显示：

    这里可能漏了一杆
      → 打厚了，补回
      → 只记总分

差额大于 1 时只显示“有 N 杆未记录”，不能把全部差额归为打厚。

负差额镜像入口：

当逐杆账本比用户确认的非推杆数更多时显示：

    已记录的击球比成绩多
      → 查看并清理误检
      → 暂时保留

负差额永远不能自动删除击球；入口进入本洞击球列表，由用户明确 reject。

永久入口三：

    Golf Menu → 本洞击球 → 选择 station → 打厚了，恢复上一杆

### 10.6 不采用自动近距二选一弹窗

不推荐每次近距第二次冲击都弹：

    是新一杆 / 是练习挥

原因：

- 用户已经明确只需要“打厚了”这一条拆分语义；
- 高频弹窗会把普通 practice swing 和 GPS 漂移变成场中负担；
- Club Prompt、scoreDebt 和换洞已经占用中断预算；
- 近距 observation 应先隐藏保留，只在用户主动恢复或账本差额有证据时出现。

---

## 11. Club Prompt

### 11.1 语义

- 击球已经独立持久化；
- Club Prompt 只补 club；
- 跳过 = club unknown；
- 误检 = 独立 reject 动作；
- 推荐杆永不自动变成实际杆。

### 11.2 推荐 UI

单一底部决策层：

- 标题：已记录第 N 杆；
- 上部保留当前洞和剩余距离；
- 点按可以完成选杆、跳过和误检的全部操作；
- 表冠滚动球杆只是增强，不能成为完成任务的唯一方法；
- 推荐杆仅作默认焦点；
- 点行确认；
- 明确“跳过球杆”；
- “不是一杆”放在独立次级动作或击球详情。

球杆列表来自用户真实 ClubProfile/球包；袋里没有的杆不应被临时编入实际记录，用户可跳过并保留 club unknown。

### 11.3 超时

旧文档“8 秒后自动写推荐杆”应废除。

如果设置超时：

- 只从浮层真正显示且屏幕 active 时开始；
- 被 AOD、来电或高优先级任务挡住时不计时；
- 超时仅收起并留下 club unknown；
- 不自动提交推荐杆。

---

## 12. 中断与浮层仲裁

### 12.1 App 内优先级

1. 用户主动任务：计分编辑、补杆、打厚、Pause、Finish；
2. 上一洞成绩与下一洞候选杆归属；
3. 无下一洞击球时的普通换洞/scoreDebt 小签；
4. Club Prompt；
5. 打厚建议、未选杆等低优先任务。

GPS 与低电默认都走并行状态警告层，不抢浮层。只有低电确实要求用户选择降级方案时，才进入交易槽；此时低于成绩归属、高于 Club Prompt。

### 12.2 关键规则

- 所有业务事件先持久化，UI 可以排队；
- Club Prompt 不能覆盖成绩确认；
- 自动提示不能抢用户正在编辑的页面；
- AOD 只显示事实投影，不显示交互浮层；
- 来电/通知回来后重新仲裁，不恢复过时倒计时；
- 每个 ResolutionEpisode 只震一次；
- 每次抬腕不重复震 scoreDebt；
- 所有成功触觉发生在本地持久化之后。

### 12.3 必测冲突

- 旧 Club Prompt 未处理又出现新杆；
- 下一 Tee 未开球但有 scoreDebt；
- 下一洞第一杆已记录但上一洞未确认；
- 成绩编辑时又出现 AutoShot；
- Club Prompt 时低电；
- 成绩确认时来电；
- AOD 期间出现下一洞候选；
- AutoShot 与手动记杆同一时间窗；
- score 差额 +1 时选择打厚；
- 进程在击球落盘后、Prompt 前被杀；
- 人工选洞后 GPS 提出不同洞；
- Finish 时仍有欠分和未决杆。

---

## 13. S70 全景差距矩阵

### 13.1 开局与整轮准备

| 能力 | 当前 | 裁决 |
|---|---|---|
| 统一球局入口 | 三套互斥路径 | 重建单一 RoundCoordinator |
| 附近球场 | Watch 无；iPhone 有排序 | 抽离复用 |
| 9/18、环组合、Tee | iPhone 有部分，Watch 无 | 修改复用 |
| 起始洞/shotgun | activeHole 无 playOrder | 新建 |
| 整轮离线包 | 当前洞临时推送 | 新建 manifest，复用几何/缓存 |
| Watch 独立 | 只有假练习局 | 定义“手机准备、Watch 独立打完”基线 |
| Pause/Resume | 无 | 新建生命周期 |

### 13.2 洞首与视觉

| 能力 | 当前 | 裁决 |
|---|---|---|
| S70 洞主屏 | 真实球局进 List；富图需 Hub 再点 | 重做统一 Hole Root |
| 中距黄色 | legacy 有近似，富图 actual 为白 | 修正 |
| 上一杆顶部 | 不一致 | 修正 |
| Driver Distance 弧线 | 无 | 有真实数据才加 |
| AI chip | 常驻且不可点 | 改为门控 Button |
| 固定散布 | 假 ellipse | 删除 |
| 18 洞环 | 常驻；此前用户明确保留 | **证据更正：保留。**S70 官方存在逐洞成绩环；修改复用当前实现，真机验证矩形几何、未打/当前状态与隐藏时机 |
| 地图球童路线 | 根页常驻，属于既有已过目视觉 | 联合建议移到 Map Detail/Caddie，但必须由用户亲自确认重开 |
| Big Numbers | 长按临时态 | 改为持久模式 |
| 多尺寸 | 单一快照为主 | 建真机矩阵 |

### 13.3 地图与果岭

| 能力 | 当前 | 裁决 |
|---|---|---|
| Map Detail | fullMap 生产不可达 | 新建可达状态 |
| Digital Crown | 只有文字/轨道，没有绑定 | 原型后实现 |
| 选点双距离 | 只有一段近似像素距离 | 新增反投影和两段大地距离 |
| Hazard | legacy 文字，缺坐标 | 扩契约并接地图 |
| PlaysLike toggle | 有 elevation 即默认开启 | 修正为 actual 默认 |
| PlaysLike 单位 | metre delta 直接加 yard | correctness blocker |
| 动态风/空气 | 无数值/TTL；且 Owner 已决定 v1 不做 | 仅保留未来重开研究，不建立现行 v1 产品契约 |
| Green View | 全洞小图拖旗且不持久 | 独立面 + pinSet |
| Change Green | 静默自动选 component | 双果岭专项 |
| PinPointer | 无 heading/页面 | 新建并验证 |
| Green Contours | 有部分坡度算法资产 | 独立验证，不冒充已完成 |

### 13.4 AI 与低频仪表

| 能力 | 当前 | 裁决 |
|---|---|---|
| Virtual Caddie | options 有，生产入口分裂 | 修改复用 |
| expected strokes | 模型有字段，校准不足 | 详情门控 |
| Club Stats | 数据字段有，页面无 | P2 修改复用 |
| Round Info | Hub 少量字段 | 重新定义 |
| Custom Targets | 只在临时 State | 先统一 target 事件 |
| Sunrise/Sunset | 无 | 明确 P3 或手机承担 |
| Tournament Mode | 无 | 至少禁 PlaysLike，规则另审 |

### 13.5 计分、换洞与结束

| 能力 | 当前 | 裁决 |
|---|---|---|
| 原子洞成绩 | score/putt/penalty 三事件 | 新建 confirmed 语义 |
| Fairway | state 有，UI 无 | Par 4/5 增加 HIT/LEFT/RIGHT |
| 保存后动作 | 强制下一洞 | 删除错误因果 |
| 历史洞编辑 | 会改变 activeHole | 分离 editingHole |
| 自动换洞 | 无 tee anchor/episode | 新建位置引擎与 correction |
| Finish | Save/Keep Playing | 增加 Edit/Pause/Discard |
| 无配置结束 | pending 仍 clear | P0 数据丢失修复 |
| 完成历史 | 成功即清空 | 保留最近轮次/revision |
| 忘记结束 | 无守卫 | 提醒但不自动丢弃 |

### 13.6 AOD、雨天与后台

| 能力 | 当前 | 裁决 |
|---|---|---|
| Workout | 无 | AutoShot/GPS 地基 |
| 后台 GPS | foreground-only | 新建并真机验 |
| AOD | 无 | 平台 spike |
| 抬腕恢复 | 无正式策略 | 回事实层或未完成用户任务 |
| Lock/Auto Lock | 无 | Apple 能力原型 |
| 湿屏/手套 | 无测试 | 喷水、湿袖、厚手套矩阵 |
| 低电 | 无 | 状态与降级策略 |

### 13.7 明确记录的产品边界

| 能力 | 裁决 |
|---|---|
| Handicap / 净杆 | S70 有；本产品首版不做，记录为有意范围决定，不再无声缺席 |
| 不记分模式 | 即使不确认洞成绩，AutoShot、Club Prompt 和逐杆位置仍可运行；成绩链保持空 |
| 多人记分 | Watch 只记录佩戴者本人；多人卡留 iPhone/Web |
| 整轮跨洞击球列表 | Watch 只提供当前洞/最近洞修正；整轮深度列表与地图留 iPhone/Web |
| 袋里没有的球杆 | 不临时伪造；用户跳过，club 保持 unknown |

---

## 14. 工程复用矩阵

### 14.1 直接或轻改复用

- topo 服务器渲染和 Canvas 绘制原语；
- WatchHoleImageStore；
- WatchGeoMath 的 WGS84→px 和 haversine；
- F/M/B 经纬度；
- CoursePrep geometry、green mesh、hazard 提取；
- WCSession 文件传输、ACK decoder；
- iPhone StartRound 的附近球场、环组合和 Tee 逻辑；
- LiveRoundPackage 与 offline readiness；
- ClubProfile、caddie options；
- ImageRenderer 和 UITestRoot；
- iPhone/Web 逐杆 correction 的操作语义。

### 14.2 修改后复用

- WatchRoundContainerView：可保留壳，删除 Hub 根心智；
- WatchHoleMapView：只保留渲染，重做状态、输入、坐标和持久化；
- WatchDistanceHero：改为持久 Big Numbers；
- WatchScoreHoleView：改成快速接受 + 完整确认；
- WatchScorecardView：分离 editingHole；
- WatchLocationProvider：并入 Workout/Location coordinator；
- WatchSyncClient：变成统一 outbox、多层 ACK；
- WatchRoundStore：变成 ledger + checkpoint；
- iPhone 整轮 package：生成 Watch 子集和 manifest；
- RoundEditModel：扩展成绩、推杆和 fairway correction。

### 14.3 必须淘汰的行为

- 三套互斥产品入口；
- WatchRoundHomeView Hub 作为打球根页；
- saveActiveHole → goToNextHole；
- 修改历史洞改变当前打球洞；
- 无配置或未同步时结束清空数据；
- 假 Digital Crown affordance；
- 固定 AI 散布椭圆；
- metre delta 直接加 yard；
- static tee→green 高差冒充当前位置 PlaysLike；
- 全洞小图拖旗且不持久；
- 当前洞到了才临时等待下载；
- Club Prompt 超时自动写推荐杆；
- 用下滑/Cancel 同时表示“跳过球杆”和“误检”。

### 14.4 必须新建

- RoundCoordinator；
- PresentationCoordinator / Arbiter；
- RoundWorkoutCoordinator；
- append-only shot/score/hole ledger；
- shotCandidate、shotStation、correction 契约；
- hole transition engine 和 tee anchors；
- playOrder、activePlayHole、editingHole；
- full-round Watch package manifest；
- Green View、PinPointer、Big Numbers；
- scoreDebt 与 ResolutionEpisode；
- finishedPendingSync 与本地完成历史；
- AOD、wet lock、low battery 状态设计。

---

## 15. 能力工作流与路线

不能再按“先 AutoShot 或先 UI”单线排序。推荐九条工作流并行设计、分批集成。

### Track A：产品与 IA

交付：

- current-hole root；
- Golf Menu；
- Map/Green/Caddie/Score/Big Numbers 表面；
- 单根页工具入口可发现性原型；
- Map Detail 的缩放轴/目标停点轴同构建对照；
- 尺寸与户外可读。

退出门：

- 三秒读数；
- 返回与抬腕恢复；
- 表冠一屏一轴；
- 湿屏/手套基本成立。

### Track B：Round 与数据安全

交付：

- RoundCoordinator；
- ledger/checkpoint/replay；
- activePlayHole/editingHole；
- finishedPendingSync；
- 多层 ACK；
- 双传输路由租约与 dead-letter。

同步底线：

- 同一事件同一时刻只允许一个通道在飞；
- watchPersisted 与 handedOffToPhone 不是 serverAccepted；
- serverRejected 必须进入可见 dead-letter；
- 只有全集 serverAccepted，球局才从 finishedPendingSync 转为 synced；
- server 以 eventId 幂等，重发安全。

退出门：

- 除 Discard 外零丢失；
- 崩溃恢复；
- 修改历史洞不污染当前洞；
- 双通道不重复计入。

### Track C：AutoShot Beta

交付：

- Workout/Motion/GPS；
- 首批高频路线；
- 第二批 100Hz 影子与升级门；
- candidate/station；
- Club Prompt；
- manual fallback；
- 打厚恢复。

退出门：

- 按设备/佩戴方式的田测；
- 电量；
- 前导腕完整挥杆；
- 中低置信不污染事实。

### Track D：计分与换洞

交付：

- scoreRecommendation；
- 快速/手动确认；
- scoreDebt；
- transition candidate；
- provisional shot assignment；
- correction。

退出门：

- 用户定义的下一洞首杆场景完整通过；
- 相邻 Tee、隔壁球道、球车经过、shotgun 全覆盖。

### Track E：地图与环境

交付：

- full-round package；
- Map Detail；
- hazard；
- target；
- PlaysLike；
- Green View；
- PinPointer；
- dynamic weather（仅作未来 Owner 重开证据研究；v1 不接入风/空气密度）。

退出门：

- 单位正确；
- stale 明确；
- 离线整轮；
- 双果岭专项。

### Track F：Ambient 与可靠性

交付：

- AOD；
- 抬腕恢复；
- Pause/Resume；
- low battery；
- GPS 降级；
- wet lock；
- system interruption。

退出门：

- 五小时/十八洞真机；
- 系统通知、来电、杀进程；
- 标准表仍完整。

### Track G：结束与赛后

交付：

- Finish Preflight；
- Save/Edit/Pause/Discard；
- Watch 最近轮次；
- iPhone/Web correction；
- 统计重算。

退出门：

- 未同步不清空；
- 任意洞随时可改；
- correction 可审计。

### Track H：证据与验证

交付：

- S70 真机侧拍；
- Apple Watch 设备矩阵；
- AutoShot 标注；
- 续航曲线；
- 场景回归；
- 发布门基线。

### Track I：全栈契约与消费者

交付：

- watch-input-event-v2；
- shot-ledger 契约；
- holeScoreConfirmed、holeAdvance、pinSet、weather TTL；
- full-round-package 与 tee-anchors；
- Swift、后端 Pydantic、JSON Schema、reducer/replay；
- iPhone/Web 消费与 correction 后统计重算；
- 幂等、死信、旧 schema 迁移。

退出门：

- 每个字段只有一个权威定义；
- 旧客户端可明确降级；
- 自动结果不覆盖新人工 correction；
- 多端重放结果一致；
- 新事件进入统计和 AI 样本的规则有测试。

---

## 16. 真机验证矩阵

### 16.1 球局与洞序

- 正常步行 18 洞；
- 球车 18 洞；
- 前九、后九、组合 18；
- 第 10 洞开球；
- shotgun；
- 跳洞后补打；
- 共享 Tee；
- 相邻 Tee；
- 双果岭；
- 9→10 会所休息。

### 16.2 击球

- Driver、wood、iron；
- full wedge；
- half wedge；
- chip；
- bunker；
- practice swing；
- 擦地；
- 打厚 1–10 码；
- 同 Tee 多次；
- OB/retee；
- 手动记杆与 AutoShot 同窗；
- left-handed/right-handed；
- leading/trailing wrist。

### 16.3 位置

- 打到隔壁球道；
- 球车经过下一 Tee；
- GPS 漂移；
- 无权限；
- stale fix；
- 无几何；
- 双通道位置；
- 手机关闭；
- 飞行模式。

### 16.4 设备与环境

- 最小支持表径；
- 主流标准表；
- Ultra；
- Series 8+ 高频；
- 旧设备 100Hz；
- AOD on/off；
- 低电；
- 烈日；
- 阴影；
- 雨；
- 湿袖；
- 手套；
- 罗盘干扰。

### 16.5 生命周期与同步

- 来电；
- 通知；
- 垂腕/AOD；
- app 强杀；
- Watch 重启；
- Workout 被其它 app 抢占；
- 手机中继切直连；
- server reject；
- finish 后长期离线；
- 忘记结束；
- 第 8 洞改第 3 洞。

### 16.6 验证指标的三级治理

本节是当前唯一的指标治理来源；docs/watch 建成后整体迁移到 validation/release-gates.md，其它文档只引用，不重复维护。

#### Hard invariant

无需田测基线即可成为发布硬门：

- 除明确 Discard 外零数据丢失；
- eventId 幂等，零重复计入；
- correction 全链可审计；
- 自动结果不覆盖更新的人工结果；
- 未确认成绩不冒充事实；
- 推荐杆不自动写成实际杆；
- stale/none 位置不伪装精确；
- 记分不触发换洞；
- 编辑历史洞不改变 activePlayHole；
- finishedPendingSync 在全集 serverAccepted 前不转 synced；
- Tournament Mode 不显示被禁能力。

#### Pilot observation

先记录分布，不在小样本前写死发布线：

- 抬腕读距时间；
- 工具入口发现时间；
- Club Prompt 察觉/跳过/误报；
- scoreDebt 察觉；
- 换洞小签察觉；
- 误换/漏换；
- 拖旗误差；
- PinPointer 罗盘误差；
- AOD 可读性；
- 打厚入口接受/撤销率；
- 逐杆依从率；
- 耗电曲线。

#### Baseline-dependent release gate

必须先取得 S70 对照、现 App 田测和本产品 pilot 基线后再冻结：

- AutoShot 按设备/佩戴腕/杆型的召回与误报；
- 旧设备 100Hz 开放条件；
- 五小时续航与最低剩余电量；
- 高置信自动换洞是否可以升为默认；
- 42/小表径布局；
- AI 是否有资格占根页；
- 动态天气 TTL；
- 工具入口发现性是否触发三页重开。

低频高损害错误不能靠“小样本未发生”证明安全，必须使用注入测试、长周期遥测和崩溃恢复测试。

---

## 17. 正式文档体系

本文件是重审入口，不应继续膨胀成同时拥有事实、UI、契约和实施步骤的巨型“总定稿”。

推荐未来建立：

    docs/watch/
    ├── README.md
    ├── research/
    │   ├── s70-facts.md
    │   ├── watchos-capabilities.md
    │   └── field-evidence.md
    ├── product/
    │   ├── north-star.md
    │   ├── capability-tree.md
    │   ├── full-round-journey.md
    │   └── information-architecture.md
    ├── interaction/
    │   ├── navigation-focus-resume.md
    │   ├── pre-round-setup.md
    │   ├── hole-root-and-big-numbers.md
    │   ├── map-hazards-playslike.md
    │   ├── green-view-and-pinpointer.md
    │   ├── scoring-and-hole-transition.md
    │   ├── shot-capture-and-recovery.md
    │   ├── club-prompt.md
    │   ├── caddie.md
    │   ├── pause-finish-postround.md
    │   └── aod-wet-glove-accessibility.md
    ├── architecture/
    │   ├── round-coordinator.md
    │   ├── event-ledger.md
    │   ├── location-hole-engine.md
    │   ├── offline-round-package.md
    │   └── sync-lifecycle.md
    ├── contracts/
    ├── decisions/
    ├── validation/
    ├── plans/
    └── archive/

第一批必须实际创建的权威文件：

- decisions/owner-locked-semantics.md；
- decisions/retire-five-page-watch-constitution.md；
- contracts/shot-ledger.md；
- contracts/watch-input-event-v2.md；
- contracts/full-round-package-and-tee-anchors.md；
- contracts/pin-set.md；
- contracts/weather-ttl.md；
- contracts/start-lie-surface-dependency.md。

owner-locked-semantics 必须原文记录用户本轮锁定语义，并注明：

> 不可由模型联合评审自行推翻；重开必须由用户本人确认。

### 17.1 权威边界

- research 只放外部事实和现场证据；
- product 只放用户任务与产品决策；
- interaction 只放屏幕、入口、状态、焦点和恢复；
- architecture 只放内部边界；
- contracts 是字段与枚举的唯一来源；
- decisions 记录选择理由与替代方案；
- validation 拥有测试矩阵和阈值；
- plans 只写实施顺序；
- archive 保留旧规格，不再与现行文档并列为权威。

docs/watch 建成后，本文件也必须在头部标记 superseded-by 对应的 product/interaction/architecture 文档，避免它自己变成下一份无法挑战的巨型“总定稿”。

### 17.2 每份文档头

必须包含：

- Status；
- Owner；
- Last verified；
- Supersedes；
- Evidence tags；
- Related contracts；
- Open unknowns。

### 17.3 当前旧文档处理

暂不移动或删除。

在本轮经用户确认后，应给以下文档加历史/被替代状态：

- 2026-06-22-apple-watch-golf-design.md；
- 2026-07-10-watch-control-spec.md；
- 2026-07-10-watch-design-system.md；
- Fable S70 Round 1/2；
- Codex Round 1 adversarial review。

它们仍是重要研究输入，但不再单独定义现行 Watch 产品。

“把 2026-07-10 操控宪法降级为历史输入”本身必须写入 decisions，不得通过移动文件悄悄发生。

---

## 18. 下一步，不进入代码

### 18.1 先解决剩余两项用户门

联合评审无权静默决定：

1. 地图球童路线是否仍常驻 Hole Root；
2. 2026-06-22、2026-07-10 与 Round 1/2 文档是否正式降级为历史输入。

成绩环不再是用户门：官方证据已推翻旧研究的否定结论，恢复用户此前“保留在 Hole Root”的决定。对剩余两项，联合建议分别为“路线移到 Map Detail/Caddie”和“旧文档降级但不删除”；在用户确认前维持既有状态。

### 18.2 建 docs/watch 骨架并先锁用户语义

第一份 canonical 文件必须是：

- decisions/owner-locked-semantics.md。

随后创建：

- README；
- research/product/interaction/architecture/contracts/decisions/validation/plans/archive 目录；
- retire-five-page-watch-constitution decision；
- 首批 contracts 清单。

### 18.3 拆出 canonical 产品文档

先从本文件拆出并互相引用：

1. product/capability-tree.md；
2. product/full-round-journey.md；
3. product/information-architecture.md；
4. interaction/navigation-focus-resume.md 的状态仲裁部分；
5. validation/release-gates.md。

本文件随后标记 superseded-by，不继续充当巨型总规格。

### 18.4 写前三份交互规格，同时跑平台 spike

交互规格顺序：

1. scoring-and-hole-transition；
2. shot-capture-and-recovery；
3. club-prompt；
4. hole-root-and-big-numbers；
5. map-hazards-playslike；
6. green-view-and-pinpointer；
7. pause-finish-postround；
8. aod-wet-glove-accessibility；
9. caddie。

并行 spike：

- CMBatchedSensorManager 与旧表 100Hz；
- 五小时高频 + GPS + Workout 续航；
- HKWorkout background 与被抢占恢复；
- Digital Crown focus 和浮层借还；
- AOD/isLuminanceReduced；
- Water Lock/app lock；
- heading；
- haptic；
- full-round package 与 surface 几何体积/传输。

这些 spike 只消除会改变设计的 UNKNOWN，不授权完整产品实现。

### 18.5 最后才写实施计划

实施计划必须按九条能力 Track 拆分，不能再写一份把 UI、AutoShot、同步、地图和后端全部串成单线的巨型计划。

---

## 19. 自我对抗：本方案仍可能错的地方

1. 单根页没有 S70 Action 键，工具入口可能仍不够可发现。
2. 根页不占表冠可能浪费 Apple Watch 最稳定的输入，也可能是正确克制，必须原型。
3. S70 公开手册不能证明最新固件所有时序和触觉。
4. 约 10 码是数据实证，不是官方阈值，可能受 Garmin ingest 过滤影响。
5. Tee last-wins 会主动失去 OB 第一球的逐杆地图，需确认统计影响可接受。
6. 快速成绩推荐可能在没有可靠 putt/fairway 证据时诱导错误确认。
7. AutoShot 高置信规则可能对不同球员、杆型和设备严重漂移。
8. Golfshot 的量产可行不等于本产品可以复用其私有训练数据或达到同等质量。
9. Workout、AOD 和高频 Motion 的组合续航可能无法支撑慢速五小时轮次。
10. Apple 第三方 Water Lock 与应用内锁的可用性仍未核验。
11. 相邻 Tee、共享 Tee 和双果岭可能使自动洞候选长期停留 unresolved。
12. “至多一个未决 ResolutionEpisode、旧 episode 降级 scoreDebt”的简化规则可能把候选杆留在错误洞，需要场景注入验证。
13. 动态风和空气密度的规则与比赛合规边界尚未正式审核。
14. AI 一行建议仍可能挤压事实层，需有/无对照。
15. 全轮地图包可能在 Watch 存储、传输和更新上过重。
16. 多端 append correction 可能产生冲突，server reducer 规则尚未设计。
17. 当前 iPhone correction 并非完整离线可靠账本，复用成本可能被低估。
18. Green mesh 可以算坡度不等于 Green Contours 已达到可用精度。
19. PinPointer 的磁罗盘在球车、手机和金属物附近可能体验很差。
20. 用户尚未亲自试完当前所有功能，不能把未试功能的缺失感当成已证实负反馈。

每一项都应进入 decisions 或 validation，而不是被正文悄悄遗忘。

---

## 20. 联合裁决队列

已可由 Codex 与 Fable直接定：

1. 五页淘汰；
2. 三页不作为正式 IA；
3. 单一当前洞根页；
4. AutoShot 第一版就是 Beta，而不是无限后置；
5. 击球、成绩、当前洞三条事实链独立；
6. Club Prompt 只补球杆；
7. 跳过球杆不删除击球；
8. 记分不驱动换洞；
9. 历史洞编辑不改变当前洞；
10. Tee last-wins；
11. 非 Tee 约 10 码分组保留原始观察；
12. 唯一拆分语义是“打厚了”；
13. 结束不清空未同步数据；
14. Green View 独立；
15. Big Numbers 是持久模式；
16. 动态数据必须带时效；
17. 真实球局必须接入统一 Watch 产品路径；
18. 不记分模式仍可运行 AutoShot、Club Prompt 和逐杆记录；
19. Watch 只记录佩戴者本人；
20. Handicap/净杆首版有意不做；
21. 任意时刻至多一个未决 ResolutionEpisode。

必须通过原型/真机再定：

1. 工具入口的具体位置；
2. 根页表冠是否完全空；
3. Map Detail 的缩放轴 vs 目标停点轴及缩放范围；
4. AOD 内容与恢复粒度；
5. AutoShot 设备支持表；
6. 规则阈值与发布门；
7. app-level wet lock；
8. PinPointer heading 门；
9. 自动洞推进默认策略；
10. AI 是否有资格占根页一行。

必须由用户亲自确认，Codex 与 Fable 无权代决：

1. 是否重开此前地图球童路线的既有视觉决定。联合建议：移到 Map Detail/Caddie；
2. 是否同意将 2026-06-22、2026-07-10 与 Round 1/2 文档正式降级为历史输入。

不再作为用户门：成绩环保留。旧研究中“S70 没有成绩环”的前提已被官方手册和图片证伪，默认恢复此前 Owner KEEP 决定。

---

## 21. 核心证据入口

- [S70 已核验证据包](2026-07-15-s70-verified-evidence-pack.md)
- [Fable S70 Round 1](2026-07-15-claude-fable-s70-design-synthesis-round1.md)
- [Codex 对 Round 1 的对抗审查](2026-07-15-codex-adversarial-attack-on-fable-s70-round1.md)
- [Fable S70 Round 2](2026-07-15-claude-fable-s70-design-synthesis-round2.md)
- [纯 Fable 全体验收口对抗审查](2026-07-15-claude-fable-watch-full-experience-final-adversarial-review.md)
- [产品设计、复用与重建设计审查](2026-07-13-product-design-reuse-redesign-review.md)
- [旧 Watch 操控规范](../superpowers/specs/2026-07-10-watch-control-spec.md)
- [旧 Watch 设计系统](../superpowers/specs/2026-07-10-watch-design-system.md)
- [旧 AutoShot 可行性文档](../superpowers/specs/2026-07-05-auto-swing-detection.md)

关键源码：

- ../../mobile/ios/AICaddieWatch/AICaddieWatchApp.swift
- ../../mobile/ios/AICaddieWatch/Models/WatchRoundModel.swift
- ../../mobile/ios/AICaddieWatch/Services/WatchRoundStore.swift
- ../../mobile/ios/AICaddieWatch/Services/WatchSyncClient.swift
- ../../mobile/ios/AICaddieWatch/Services/WatchLocationProvider.swift
- ../../mobile/ios/AICaddieWatch/Views/WatchRoundContainerView.swift
- ../../mobile/ios/AICaddieWatch/Views/WatchHoleMapView.swift
- ../../mobile/ios/AICaddieWatch/Views/WatchScoreHoleView.swift
- ../../mobile/ios/AICaddie/Views/StartRoundView.swift
- ../../mobile/ios/AICaddie/Models/RoundEditModel.swift

---

## 22. Fable 纯度审计

### 22.1 主全景任务

- session：adfedb95-cdac-493e-8c48-8c49d5412458；
- model：claude-fable-5；
- effort：max；
- fallback：CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK=1；
- duration：约 102 分钟；
- terminal_reason：api_error；
- result：Request timed out；
- modelUsage：仅 claude-fable-5；
- outputTokens：41210；
- WebSearch：2；
- 纯度：通过；
- 完成度：失败，没有可用最终正文。

该任务未被冒充为完成。

### 22.2 聚焦收口任务

- session：ffe8b3db-ed5e-4619-99f9-af6ff7ba75e2；
- model：claude-fable-5；
- effort：max；
- fallback：CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK=1；
- terminal_reason：completed；
- modelUsage：仅 claude-fable-5；
- outputTokens：46672；
- cacheReadInputTokens：1273209；
- cacheCreationInputTokens：117599；
- WebSearch：0；
- permission_denials：空；
- fast_mode_state：off；
- 纯度：通过；
- 完成度：通过。

完整原文保存在：

- [2026-07-15-claude-fable-watch-full-experience-final-adversarial-review.md](2026-07-15-claude-fable-watch-full-experience-final-adversarial-review.md)

### 22.3 Fable 独立攻击后的主要修正

Fable 没有照单全收，指出：

1. 成绩环是用户曾明确保留的决定，联合评审无权静默删除；
2. 地图球童路线同样应进入用户重开队列；
3. Round 2 的目标停点表冠轴不能在合稿时无声消失；
4. AutoShot 0–1 秒提示缺证，应改为真机前“不超过 3 秒”的假设；
5. 旧设备 100Hz 应是第二批，首批先做高频设备；
6. fairway 默认推断依赖 surface 几何和新契约，不是免费能力；
7. 低电默认应走并行状态层；

**2026-07-15 后续证据更正**：Fable 关于“不得静默推翻 Owner KEEP”的治理判断仍然正确；新的 Garmin 官方证据进一步证明成绩环本身也是 S70 的真实能力，因此不再申请重开，直接恢复 KEEP。
8. 洞末还缺负差额“清理误报”入口；
9. 全栈契约、幂等、死信和消费者改造必须成为独立 Track；
10. 未决 ResolutionEpisode 应限制为一个；
11. Club Prompt 点按必须完备，表冠只能增强；
12. 还需明确 Handicap、不记分模式、多人记分和整轮击球列表边界。

### 22.4 Codex 对 Fable 的裁决

全部接受并已回写正文：

- 用户锁定决定新增第三决策队列；
- 三页不再预先投入原型；
- Map Detail 恢复缩放轴/目标轴对照；
- AutoShot 证据重新分级；
- 100Hz 降第二批；
- 续航加入 Beta 发布门；
- startLie surface 依赖显式化；
- 低电移回并行警告层；
- 增加负差额入口；
- 增加 Track I 全栈契约；
- 增加单 episode 上限；
- Club Prompt 点按完备；
- 增加四项范围 decision。

没有接受任何会推翻用户本轮锁定语义的建议。特别是：

- 不恢复每次近距冲击二选一弹窗；
- 不引入 OB/Mulligan/暂定球恢复 UI；
- 不让 Club Prompt 决定击球是否存在；
- 不把 AutoShot 再次无限后置。

### 22.5 联合状态

纯 Fable 已完成联合对抗；本文件仍保持 JOINT DESIGN REVIEW，而不是实施规格，原因只剩：

- 两项用户门尚未确认：地图球童路线、旧文档正式降级；
- 平台与真机 UNKNOWN 尚未验证；
- canonical docs/watch 文档尚未拆分。
