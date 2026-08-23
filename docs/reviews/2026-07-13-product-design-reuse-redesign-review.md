# AI Caddie 产品设计合理性、工程复用与改版评估

> 日期：2026-07-13 UTC  
> 基线：本地 `integration/v2` @ `a0c0fca`  
> 范围：产品定位、Web、iPhone、Apple Watch、统一后端、Garmin 数据、地图几何、统计、AI 球童、报告、跨端同步与相关设计文档  
> 方法：先挑战设计前提，再判断工程复用，最后提出修改方案  
> 性质：产品与架构设计重审，不覆盖既有安全/正确性缺陷报告  
> 写入：仅新增本文件；旧 review、旧 spec、mockup 和源码全部保留  
>
> **2026-07-16 AUTHORITY CORRECTION — HISTORICAL REVIEW INPUT：**本文 §14 把“Watch 无 iPhone 完成搜索、开局准备和直连同步”列为暂缓，是一次 review 建议，**不能预先裁决 D04**。当前唯一 Owner 队列、既有独立范围与 no-code gate 见[Watch 决策账本](2026-07-15-watch-decision-and-task-tracker.md)；全仓冲突见[Owner-gate 审计](2026-07-16-repository-wide-owner-gate-authority-and-drift-audit.md)。正文保留用于追溯。

---

## 0. 为什么需要重新评估

前几轮评审主要回答的是：

1. 代码会不会丢数据、泄露凭据或算错统计；
2. 实现是否符合已有文档；
3. 当前版本能不能扩大 TestFlight 或公开试用。

这些问题很重要，但仍缺少更靠前的一层：

> 这个功能、页面、导航和跨端分工本身是否合理，是否值得按当前设计实现？

本报告不再把“定稿”“宪法”“已批准设计”视为不可质疑的事实。任何设计都必须先通过用户任务、使用频率、数据可信度、平台约束和工程成本评估。

本报告与以下工程报告配套使用：

- [Claude Opus 4.8 独立工程评审](2026-07-12-claude-opus-max-independent-review.md)
- [Codex × Claude 交叉审查](2026-07-11-codex-claude-cross-review.md)
- [全仓库代码、架构、发布与文档审查](2026-07-11-full-repository-review.md)

其中 `2026-07-12-claude-fable-only-rerun.md` 明确标记为 INCOMPLETE，不作为独立完成的权威结论。

全文严格按用户要求分成三部分：

1. **第 1–12 节：设计合理性**——先判断产品定位、三端 IA、Watch 操控、后端/AI 边界和状态机是否合理；
2. **第 13 节：工程复用**——再判断现有实现哪些可直接复用、修后复用或退出；
3. **第 14 节以后：具体修改**——最后给出修改优先级、实施顺序、验收标准和旧文档覆盖关系。

---

## 1. 总体裁决

### 1.1 核心产品方向成立

最初 Master Product Spec 提出的两个问题是正确的：

1. 我的高尔夫长期发生了什么变化，哪些问题持续丢杆？
2. 在当前球位、球场几何、障碍和个人球杆能力下，下一杆应该怎么打？

见 [Master Product Spec](../superpowers/specs/2026-05-25-ai-caddie-master-product-spec.md)，第 15–29 行。

这两个问题构成本报告认为最有潜力的产品差异化假设：

- 长期、可追溯的个人高尔夫记忆；
- 真实球洞几何与个人球杆模型；
- 建议、实际结果、赛后纠错和下次建议之间的闭环。

这部分不应推倒重来。

### 1.2 当前完整设计不是最优方案

当前产品逐步演变成了：

- Garmin 功能替代；
- GolfLive 统计替代；
- Web 管理台；
- iPhone 记分器；
- Apple Watch 独立球局；
- AI 报告平台；
- Vision/媒体证据系统；
- 家庭多用户系统；
- AutoShot 研究项目。

这些能力单独看都有价值，但整体缺少清晰的取舍规则。底层能力很强，用户体验却被功能数量、重复入口和不一致语义稀释。

最主要的设计问题不是“页面不够漂亮”，而是：

1. 产品范围由功能清单驱动，而不是由用户任务驱动；
2. Web、iPhone、Watch 的职责边界不断重叠；
3. “记录一杆”“保存本洞”“结束球局”的语义不统一；
4. AI 被做成页面和报告，而不是嵌入具体任务的解释能力；
5. 手表把低频菜单、旗向和高频距离、记杆放在同一导航层级；
6. 消费者产品与 owner 诊断/后台控制台仍然混在一起；
7. 手动球员和 Garmin 球员没有完全进入同一个学习闭环。

### 1.3 不建议重写整个项目

推荐策略是：

> 保留高价值数据与几何引擎，重新定义产品边界和球局状态机，再逐步替换错误的页面与存储路径。

也就是采用 strangler 式迁移，而不是全仓推倒重来。

---

## 2. “最优设计”的判断标准

本报告所说的“最优”，不是抽象审美，也不是页面最少，而是在当前个人/家庭使用范围内同时满足：

1. **任务匹配**：用户能快速完成真正要做的事情。
2. **频率匹配**：高频动作处于最短路径，低频工具不得占据主导航。
3. **数据可信**：界面不能把估算、推断或 AI 文案伪装成事实。
4. **可逆可靠**：记分、纠错、结束和同步都有明确状态，不能静默删除。
5. **平台适配**：共享语义，不强求三端共享相同布局。
6. **优雅降级**：无网络、无几何、GPS 差、AI 失败时仍可记分。
7. **工程杠杆**：优先复用真正形成差异化的资产，停止维护重复实现。
8. **范围克制**：没有证明用户价值的功能可以删除、后置或仅保留实验状态。

### 2.1 使用频率决定界面层级

| 用户任务 | 每轮频率 | 合理主设备 | 交互预算 |
|---|---:|---|---|
| 看距离与主建议 | 30–60 次 | Watch | 抬腕 3 秒内 |
| 记录一杆 | 30–60 次 | Watch / iPhone | 一次明确动作 |
| 确认本洞成绩 | 9/18 次 | Watch / iPhone | 5–10 秒 |
| 查看完整球童方案 | 少量 | iPhone / Watch detail | 一次进入 |
| 旗向指引 | 0–数次 | Watch | 条件满足时进入 |
| 计分卡、选洞、结束 | 少量 | Watch / iPhone | 明确工具入口 |
| 备战 | 每轮一次 | Web / iPhone | 可阅读、可比较 |
| 深度复盘与趋势 | 每轮后或每周 | Web / iPhone | 可钻取、可纠错 |
| 球包、账户、连接器 | 低频 | Web / iPhone | 设置或“我的” |

这个频率表对 Watch 五个对等顶层页面形成了强烈反对信号，也暴露了 iPhone 与 Web 中多个重复入口。表中的“3 秒”等数字是本报告提出的验收目标，不是已经完成的用户研究结论。

---

## 3. 三种产品组织方式

| 方案 | 描述 | 优点 | 问题 | 裁决 |
|---|---|---|---|---|
| A. 功能/竞品对标型 | Garmin 有什么、GolfLive 有什么，就分别建立页面 | 覆盖广、看起来完整 | 功能膨胀、页面找位置、跨端重复 | 否决为主导原则 |
| B. 球员生命周期型 | 备战 → 打球 → 复盘 → 更新个人模型 | 与真实任务一致，易分配平台职责 | 需要删除或重定位已有功能 | **推荐** |
| C. AI 助手/聊天型 | 以 AI 对话或报告为中心串联全部能力 | 表面统一、演示感强 | 不利于数据核验，容易泛化和幻觉 | 否决为主界面 |

推荐方案 B。

目标闭环：

```text
                 ┌────── 个人球杆 / 倾向 / 球场记忆 ──────┐
                 │                                        │
选场与备战 → 场中建议与记录 → 收洞与同步 → 赛后校对与复盘
  Web/iPhone      Watch+iPhone       后端账本        Web/iPhone
                 └──────────── 更新个人模型 ────────────┘
```

AI 是这个闭环中的解释层，不是权威事实层。

---

## 4. 必须撤销的旧设计前提

### 4.1 “所有要求能力都不能删”

Master Product Spec 第 74–75 行规定：

> No required capability is optional.

这条规则会把早期想法永久转化成开发义务，是造成范围膨胀的根因之一。

应改为：

> 只有被核心任务、真实数据或用户验证证明有价值的能力，才进入主产品；其余能力可以删除、后置或保留实验。

### 4.2 “现有每个页面一个不删”

[Web 产品重设计](../superpowers/specs/2026-06-09-web-product-redesign-design.md)第 43–59 行明确写着：

> 现有每个页面都有去处——一个不删。

这会把“重新设计”降级成“给旧页面重新分组”。当前 Web 仍保留球童沙盘、手机记分、订正控制台和报告控制台，就是这个原则的结果。

### 4.3 “写成定稿就等于最优”

两份 2026-07-10 Watch 文档把五页称为“操控宪法”“定案”和“统一设计定稿”：

- [Watch 操控规范](../superpowers/specs/2026-07-10-watch-control-spec.md)，第 3、30、54–75 行；
- [Watch 设计系统](../superpowers/specs/2026-07-10-watch-design-system.md)，第 1–3、22–64 行。

新原则应是：

> 定稿只表示当时选择已记录，不表示免于后续产品红队。

---

## 5. 目标产品定义

### 5.1 一句话定义

AI Caddie 应是：

> 一个用真实球局、个人球杆模型和球场几何，帮助球员赛前制定计划、场中做决定、赛后理解失分的个人高尔夫决策系统。

它不应被定义为：

- Garmin 全功能克隆；
- GolfLive 全模块克隆；
- 家庭管理超级 App；
- AI 报告生成器；
- 通用高尔夫聊天机器人；
- 以 3D、Vision 或 AutoShot 为卖点的技术展示。

### 5.2 主 persona

建议 v1 的主 persona 是：

> 有 Garmin 历史数据、愿意在 iPhone/Apple Watch 上使用个性化球童和复盘的核心球手。

家庭成员与纯手动球员必须能完整记分并逐步获得个性化，但不应为了同时满足四类用户而让 v1 主流程变得复杂。

家庭管理属于账户和权限能力，不应主导消费者信息架构。

### 5.3 三条主流程

1. **备战**：选择球场/T 台/洞组，找到关键洞和可信打法，确认离线就绪。
2. **打球**：快速看距离与主建议，可靠记录每杆/每洞，断网可继续。
3. **复盘**：先确认球局与缺杆，再看少量可行动洞察，并更新个人模型。

所有主产品功能必须明确服务其中一条；无法归入的功能默认进入实验、诊断或删除候选。

---

## 6. Web 设计评估

### 6.1 当前合理的部分

- Web 被定义为深度复盘与备战工作台，而不是场中主设备，这个方向正确。
- 侧栏、二级导航、钻取、真实洞图、球局时间线、统计组件和球包组件都有复用价值。
- owner diagnostics 已开始门控，消费者与内部信息正在分离。

当前导航定义见 [navigation.ts](../../web_v2/src/navigation.ts)，第 20–82 行。

### 6.2 当前不合理的部分

#### 复盘与统计被人为拆开

当前一级区块同时存在“复盘”和“统计”，而“复盘”下已经有概览、球局和强弱分析，“统计”又有趋势和球场。

它们本质上都在回答“我打得怎么样、为什么”。这种拆分增加选择成本，也造成 iPhone 首页同样出现“历史复盘”“数据统计”“上一场”三个相邻入口。

#### Web 声称不做实战，却保留实战工具

`navigation.ts:69-82` 仍把“球童沙盘”和“手机记分”放在侧栏工具组。

- 球童沙盘应成为备战页的高级试算器或 owner diagnostics。
- 手机记分不应作为 Web 场中功能；若保留，应定位为赛后补录，并具备持久草稿。

#### 控制台页面仍冒充消费者功能

- `CorrectionsPage` 让用户面对 target type/ID；
- `ReportsPage` 以“加载/生成各种报告”为主要交互；
- 数据质量、readiness、后端配置仍存在管理台心智。

订正、报告和来源证据应嵌入具体球局、球洞、球杆或统计上下文。

#### 当前页面状态没有成为 URL

核心页面主要由 `activePage` React state 驱动，导致刷新、后退、收藏和分享深链能力不足。

深度复盘工具必须有 URL 路由：球局、球洞、球场、统计范围和筛选都应可恢复。

#### “发到设备”和分析图形存在虚假承诺

当前备战页的“导出”和“发到手机/手表”实际都落到打印行为；在真正完成离线包同步、状态回执和设备可见性之前，“发到设备”不应出现在消费者界面。

部分统计还把四个互斥方向百分比合成为二维散布椭圆，或在没有真实 decision 的复盘图上仍使用“球童建议线”图例。这类表达看起来高级，却没有足够数据维度支撑，必须改成诚实的条形/方向图或真实决策对比。

### 6.3 推荐 Web IA

主侧栏：

```text
复盘
备战
球包
────────
设置
```

“统计”合并进“复盘”：

- 总览；
- 球局；
- 趋势；
- 强弱；
- 球场。

AI 报告不再是一级或固定二级页，而是：

- 单局内“解释这场”；
- 趋势内“解释这段变化”；
- 球场内“给我下次建议”。

球童沙盘：

- 普通用户：嵌入备战工作台；
- owner：可保留完整 diagnostics 模式。

手机记分：

- 从消费者侧栏移除；
- 需要时改成“补录球局”，进入赛后流程。

---

## 7. iPhone 设计评估

### 7.1 当前合理的部分

当前 [RoundHomeView.swift](../../mobile/ios/AICaddie/Views/RoundHomeView.swift) 已形成一个相对清晰的 Hub：

- 继续/开始球局是主任务；
- 备战、复盘、统计是次级入口；
- 设置与 Garmin/同步被下沉；
- 上一场可快速进入。

地图、实时距离、球童摘要、球杆选择、离线包、位置服务和 Watch 桥接也都有明显复用价值。

### 7.2 当前不合理的部分

#### “选球杆、记录一杆、保存本洞”语义混合

[CurrentHoleView.swift](../../mobile/ios/AICaddie/Views/CurrentHoleView.swift)第 1092–1119 行的 `submitEvents()` 一次提交：

- 当前位置；
- 总杆；
- 推杆；
- 罚杆；
- 球杆；
- 备注。

同一文件第 624–637 行又在“选完球杆”时立即写一个轻量 club event。

用户无法清楚判断：

- 这是选择下一杆球杆；
- 这是已经记录了一杆；
- 还是完成了本洞。

这是产品语义错误，不只是代码组织问题。

#### 主按钮与实际动作不一致

`LiveSaveButton` 显示“保存本洞”，但当前流程既没有可靠的逐杆模型，也没有自然推进下一洞。

目标必须拆成两个不同动作：

1. **记这一杆**：保存当前洞、GPS、时间、球杆；不改变洞。
2. **完成本洞**：确认总杆/推杆/罚杆；原子保存并推进下一洞。

#### 假底栏必须删除

[LiveHoleComponents.swift](../../mobile/ios/AICaddie/Views/LiveHoleComponents.swift)第 570–590 行定义了“洞图/记分/球童/球场/更多”五个视觉标签，但注释明确说明它们不具备导航行为。

不可点击却看起来可点击的底栏是虚假 affordance，应立即删除或真正接通；不应继续作为视觉装饰。

#### 场中页面承担过多职责

`CurrentHoleView.swift` 已超过 1200 行，同时承担：

- GPS 与地图；
- 球童请求与离线降级；
- 球杆与打法；
- 计分；
- 媒体/Vision；
- 加打/减九洞；
- 结束本场；
- Watch 同步；
- 恢复状态。

这既是工程问题，也是界面边界问题。场中主页应该只保留：

- 当前洞/距离/地图；
- 一条主建议；
- 记杆；
- 完成本洞；
- 进入详细球童与低频工具的入口。

### 7.3 推荐 iPhone 状态结构

```text
无球局
  ├─ 开始一场
  ├─ 上一场待复盘
  ├─ 备战
  └─ 复盘

准备中
  球场 → 洞组 → T 台 → 球包确认 → 离线/Watch 就绪

进行中
  当前洞主页
    ├─ 记这一杆
    ├─ 完成本洞
    ├─ 球童详情
    ├─ 洞图/选点
    └─ 球局工具

结束后
  finishedPendingSync → finishedSynced
          └─ reviewStatus: pending → reviewed
```

校对不是同步前门槛。球局结束后应尽快上传权威记录；用户可以在同步前或同步后进入校对，后续修改以 append-only correction 继续同步，不能因为用户尚未复盘而阻塞原始球局保存。

### 7.4 首页建议

保留当前 Hub 组件，但做以下收敛：

- “历史复盘”“数据统计”“上一场”合并成一个“复盘”入口；
- 上一场仍可作为复盘入口的内容卡；
- 备战保持独立；
- 球包/账户进入设置或“我的”；
- 进行中球局永远置顶；
- 无球局时“开始一场”是唯一主按钮。

---

## 8. Apple Watch 设计评估

### 8.1 当前设计裁决

五页横滑应立即冻结，不再直接进入实现。

此前非正式提出的 `3+2`：

```text
[球童] — [球道图] — [计分]
                 ├─ 菜单
                 └─ 旗向
```

比五页明显更好，但基于当前任务频率和手势分析，它仍不是首选候选。

当前首选候选：

> 单一“打球主页”常驻；记杆和计分使用上下文浮层；球童详情、计分卡、选洞、旗向、设置和结束使用系统 push。

这仍是一项设计假设，不是新的“宪法”。正式定稿前必须用原生可交互原型比较：

1. 五页；
2. 3+2；
3. 单一打球主页 + sheet/push。

至少完成三轮真实 9/18 洞任务测试，记录读距离耗时、误触/误翻页、记杆遗漏、计分完成时间、返回当前上下文的成功率，以及手套/雨天可用性。没有这些证据，不应把任何一个候选写成永久定案。

### 8.2 为什么 3+2 仍不是最优

- 主球童建议本来就应常显在打球主页，不需要对等页面；
- 计分只发生每洞一次，不应与每杆查看的距离同级；
- 地图已经拥有点按测距、拖旗和表冠目标轴，再叠加顶层横滑仍有冲突；
- 抬腕应该稳定回到当前球洞上下文，而不是回到离开时的任意分页；
- 显式按钮和系统 sheet/push 比记忆左右页位置更可发现。

### 8.3 当前首选 Watch IA 候选

```text
打球主页（唯一根页；有图时地图就是背景与空间主体，无图时保持同一信息布局）
  ├─ 球道图 / 果岭图 / 无图数字降级
  ├─ 主距离 / F-M-B / GPS 新鲜度
  ├─ 推荐杆 + 一句策略
  ├─ 表冠：旗 / 障碍 / layup 目标停点
  ├─ 大按钮：记杆
  ├─ 上下文入口：计分本洞
  └─ 工具入口：球局

ShotCapture sheet
  ├─ 选杆
  ├─ 未知球杆
  ├─ 删除误报
  └─ 补记

ScoreHole sheet
  ├─ 总杆
  ├─ 推杆
  ├─ 罚杆
  └─ 保存并推进

球局 NavigationStack
  ├─ 球童详情
  ├─ 计分卡
  ├─ 选洞
  ├─ 旗向指引
  ├─ 球杆数据
  ├─ 设置
  └─ 结束本场
```

这里所说的 v1 Watch：

- 必须能把已经准备好的球局离线打完并可靠保留；
- 不要求 v1 同时完成无 iPhone 的球场搜索、整场准备、账户管理和直接云端全流程；
- “场中离线可用”与“Watch 完全独立成为另一套产品”必须区分。

### 8.4 Watch 操控规则

1. 表冠只控制当前页面唯一聚焦维度，该维度可以是连续值或离散停点索引。
2. 根页表冠切换“当前要看的目标”（旗、障碍、layup），不翻页、不缩放。
3. 地图不平移；拖动只允许拖旗，并且只从旗柄开始。
4. 记杆必须先持久化 GPS/时间/当前洞，再显示成功。
5. 未确认球杆保持 unknown，不进入球杆统计。
6. 不得 8 秒后把推荐杆静默写成事实。
7. 保存本洞才推进洞；GPS 永远不自动跳洞。
8. 结束本场只进入 `finishedPendingSync`，不得清空 round/outbox。
9. 无图但有果岭坐标时显示纯数字；无坐标时明确“距离不可用”，绝不显示 0 码。
10. 长按大字只能是增强能力，不能成为查看关键数字的必经手势。

### 8.5 Watch 候选方案的验证场景

1. 抬腕 3 秒内读到主距离与推荐。
2. 雨天/手套只用一个大按钮和表冠即可记杆。
3. 记杆后立即杀进程，GPS 点、当前洞和 pending 仍存在。
4. 未选杆保持未知，不自动写推荐杆。
5. 保存本洞重复点击、断网、重启都只推进一次。
6. 无图但有坐标仍有 F/M/B；无坐标不显示假数字。
7. GPS 过期或精度差时取消“实时”标识。
8. 旗向只有坐标和 heading 质量合格时可进入。
9. 离线打完 18 洞保持 `finishedPendingSync`，任何错误都不清数据。
10. 在单根页候选中，地图拖旗和测距不再与顶层分页手势竞争；对照原型必须量化这一收益。

---

## 9. 后端、Garmin、统计与地图设计评估

### 9.1 推荐总体架构

继续采用模块化单体，不建议拆成微服务。

```text
Garmin / 手动球局 / Watch 事件
                ↓
      可追溯 Round/Hole/Shot Ledger
                ↓
个人球杆模型 + 版本化 CoursePack
                ↓
备战事实 / 场中决策 / 赛后复盘
                ↓
       可选 LLM 解释与问答
```

目标内部边界：

- PostgreSQL：玩家、连接、标准化 round/hole/shot、事件、订正、cursor、idempotency、决策结果；
- Object storage：Garmin 原始快照、CoursePack、地图、媒体；
- Worker：Garmin 导入、几何解码、地图渲染、统计投影、可选 AI；
- FastAPI：鉴权、命令和页面级轻量查询。

### 9.2 Garmin 数据

Garmin connector 是重要入口，不应成为内部领域模型。

保留：

- connector adapter；
- 原始不可变快照；
- Garmin → 标准 Round/Hole/Shot 映射；
- source refs 与导入批次。

逐步退出：

- 每次请求重新读取大量原始文件再拼统计；
- 手动局反向伪装成 Garmin JSON 作为长期权威写路径。

### 9.3 统计

`ai_caddie/history/history_stats.py:3819-3858` 已接近 4000 行，并一次构造 summary、time、scoring、courses、holes、clubs、issues、diagnosis、profile、quality 和 drillDown。

算法资产值得保留，但产品不应继续依赖一个约 11–20MB 的巨型统计响应。现有源码自己在 `server_v2/history_stats.py:38-59`、`web_v2/src/App.tsx:137-180,260-275` 将完整响应描述为约 11MB/20MB，并已用 summary/mobile stats 做局部瘦身。

目标查询投影：

- `/overview`
- `/rounds/{id}/review`
- `/trends`
- `/courses/{id}`
- `/clubs`
- `/data-quality`

主流程只展示可行动指标：

- 近期成绩变化；
- 阶段弱项；
- 重复球场/球洞模式；
- 球杆距离与样本可信度；
- 下一次可采取的动作。

记录榜单、覆盖率和内部诊断进入次级页面或 owner diagnostics。

### 9.4 地图与 CoursePack

本报告建议优先继续投资地图与几何资产，因为它同时服务备战、场中和复盘，并且已有真实实现与跨端消费者；这是一项产品投资建议，不是已由市场数据证明的结论。

直接保留：

- prodgeometry 获取与日期回退；
- 坐标投影；
- 自有 topo 渲染；
- 路线、障碍、绿区和高程事实；
- 服务器位图 + 客户端轻 overlay 的跨端策略。

目标是一个版本化 CoursePack：

```text
course / hole / tee / version
base-map object key + hash
projection
route
green anchors
hazard polygons
elevation facts
coverage + provenance
```

Web、iPhone、Watch 使用同一事实包，但各自绘制适合平台的 overlay。

Garmin 官方 raster 只用于内部对齐与质检；产品使用自绘图可以降低未授权分发风险，但最终许可边界仍需正式法律/授权确认。

`geometry_evidence` 不应继续维护一个与 canonical mesh 不一致的平行 polygon 世界，应改为 CoursePack 查询投影。

### 9.5 暂不建议投入 WebGL 3D

当前 2D topo + 路线/障碍/高程 overlay 已能完成“看清打法”的任务。

WebGL 3D 只有在真实用户测试证明它比 2D 更快帮助决策时才值得进入主路线；不能仅因为技术上可做或视觉更炫就实施。

---

## 10. AI 球童与报告设计评估

### 10.1 正确方向

[Decision Layer Design](../superpowers/specs/2026-05-23-ai-caddie-decision-layer-design.md)提出：

> 核心产品对象是一个可验证的 decision，而不是 dashboard、round 或 report。

并坚持确定性决策、LLM 只负责解释，这个方向是正确的。

### 10.2 当前问题

当前存在多套在线/离线决策规则：

- `course_prep.py`
- `mobile_live.py`
- `decision.py`
- iOS `OfflineCaddieDecisionEvaluator.swift`

它们的风险常数、球杆选择和 attack 语义可能不同。

此外：

- 中文事实绑定检查存在已确认漏洞；
- expected-strokes 由大量手工权重组合，尚未校准；
- 风力修正同样依赖经验系数；
- 五类持久化 AI 报告把 AI 变成了内容中心；
- Vision 的自由文本和照片元数据存在隐私与 prompt 风险。

### 10.3 AI 应承担的职责

- 将结构化事实压缩成清晰简体中文；
- 解释为什么当前确定性建议成立；
- 比较时段并指出重复模式；
- 根据已确认弱项建议练习重点；
- 对结构化事实进行问答；
- 明确缺失数据。

### 10.4 AI 不应承担的职责

- 计算距离、障碍、高程、rating/slope；
- 独立选择球杆或目标；
- 输出未经校准的成功率或预计杆数；
- 根据自由文本/Vision 自动修改 lie、处罚、天气或球局事实；
- 决定同步、cursor 或球局生命周期；
- 将无合法 fact ID 的内容标记为“已事实绑定”。

### 10.5 推荐 AI 产品形态

用户主流程只保留：

1. “解释当前建议”；
2. “解释这场球”；
3. “解释这段趋势”；
4. 基于当前事实的追问。

course/hole/club/trend 多套独立 AI 报告退出主导航，统一为页面内的解释能力。

expected-strokes 和风力 carry 在真实校准前不进入消费者主界面，只显示：

- 精确距离；
- 过障碍距离；
- 坡度实打修正；
- 球杆样本数；
- safe/stock/attack 序数风险；
- 目标与可接受失误方向；
- 缺失信息与置信度。

Vision 在 v1 仅作为照片附件和人工确认的实验能力。

---

## 11. 数据可信度与降级模型

建议固定四级：

| 级别 | 内容 | 展示规则 |
|---|---|---|
| A 权威观察 | 用户确认记分、Garmin scorecard、带精度 GPS、选定 T 台 | 可直接展示和纠错 |
| B 确定性派生 | 距离、障碍、高程、rating/slope、足样本球杆中位数 | 显示来源、版本、新鲜度 |
| C 经验模型 | miss pattern、策略排序、校准后的 scoring impact | 必须显示样本数与模型版本 |
| D AI 推断 | 文案、练习建议、Vision | 不得改写 A/B，必须引用事实 |

降级规则：

- Garmin 失效：缓存历史仍可读，手动记分继续；
- 几何缺失：关闭障碍/实打/路线推荐，保留记分；
- 球杆样本不足：使用手动或 catalog 距离，标记“非个性化”；
- GPS 差：冻结最后可信点，不写假落点；
- AI 失败：使用 deterministic explanation；
- CoursePack 更新：一轮球固定版本，赛后更新；
- 不同量纲与可信等级不得静默混入同一统计。

---

## 12. 统一球局与同步状态机

三端必须共享同一语义：

```text
draft
  → active
  → finishedPendingSync
  → finishedSynced

active / finishedPendingSync
  → explicitDiscard（明确二次确认）
```

同步生命周期与复盘生命周期正交：

```text
roundSyncStatus: active / finishedPendingSync / finishedSynced
reviewStatus: pending / reviewed
```

`reviewStatus` 不阻塞上传。用户在任一同步状态下都可以校对；校对结果以 correction event 追加，而不是重写或延迟原始结束事件。

关键不变量：

1. 保存本洞是一个原子 mutation。
2. 记杆与完成本洞是不同事件。
3. 结束球局不等于删除球局。
4. 无配置、断网、500、malformed 2xx、partial ACK 都不能清本地记录。
5. Watch 与 iPhone 使用一份 outbox 语义；transport 可以有手机中继和直连云端两种。
6. cursor、revision、idempotency 和 schema version 必须由服务端账本保证。
7. Web 若保留补录，必须使用相同事件和持久草稿，不能只存在 React 内存。

---

## 13. 工程复用总矩阵

这一节才开始回答“已经实现的工程部分怎么处理”。前面第 1–12 节的目标是判断产品与架构设计是否合理；本节将现有实现分成直接复用、修后复用和退出/重构三类。

### 13.1 当前实现边界

Web 已有可用的 shell、复盘、备战、地图、球包和诊断门控组件，但页面组织仍受“一个不删”影响。

iPhone 已有开局选择、地图、离线存储、逐杆编辑和 Watch 桥接基础，但 `CurrentHoleView` 将位置、球杆、杆数、推杆、罚杆、媒体和球局管理混在一个协调器与滚动页面中。

Watch 当前生产入口存在两条互斥路径：

- `mobile/ios/AICaddieWatch/AICaddieWatchApp.swift:43-63` 中，`roundModel.round != nil` 时进入多洞 `WatchRoundContainerView`；
- 同一分支只有手机推送单洞 state 时进入 legacy `WatchHoleView`。

`mobile/ios/AICaddieWatch/Models/WatchRoundModel.swift:12-20` 的 `WatchRoundScreen` 只有 home/scoring/finishing/scorecard/holeSelect/menu/holeMap，没有完整 shot capture、球童策略、旗向或 `finishedPendingSync`。因此可以复用组件和存储原语，但不能把现有页面开关继续当作目标产品架构。

后端已经存在轻量历史 overview、round detail 和 drilldown 路由，也已有 event ID、server sequence、cursor、revision、JSON Schema 与 player-scoped 隔离原语。目标迁移应优先扩展这些已有边界，避免重建第二套接口。

### 13.2 复用矩阵

| 工程资产 | 裁决 | 处理方式 |
|---|---|---|
| Garmin CN connector / raw snapshots | 修后复用 | 变成可替换 adapter；原始快照不可变；修复凭据与备份 |
| Garmin → Round/Hole/Shot 映射 | 修后复用 | 写入标准化 ledger，保留 provenance |
| Club bag canonicalization / manual precedence | 直接复用 | 名称与枚举移入共享契约 |
| 历史统计公式与 sourceRefs | 修后复用 | 修正确性问题，拆成页面投影 |
| `server_v2/history_overview.py`、`history_round_detail.py`、`history_drilldown.py` | 直接复用 | 作为轻量页面投影的迁移种子 |
| append-only correction / annotation 语义 | 语义复用、实现重构 | 保留 append-only 模型；修复 addShot 契约并迁入事务 DB 与客户端 outbox |
| geometry sync / date fallback | 直接复用 | 输出 immutable CoursePack |
| `hole_render` / topo 投影 | 直接复用 | 对象存储 + manifest，三端共用 |
| `course_prep` 距离/障碍/高程事实 | 修后复用 | 与推荐策略解耦 |
| `geometry_evidence` 平行 schema | 淘汰重构 | 改成 CoursePack 查询投影 |
| 多套在线/离线 caddie 规则 | 重构复用 | 合并为一个带 `policyVersion` 的策略 |
| expected-strokes / 手工 wind 权重 | 暂停消费者展示 | 有校准数据后再进入产品 |
| LLM provider / fact bundle / fallback | 修后复用 | 先修中文/数值事实审计、prompt 隔离和 claim→fact ID 验证，再作为解释 sidecar |
| 五类独立 AI 报告 | 退出主流程 | 合并为页面级“解释” |
| 媒体附件与 Vision 管道 | 修后复用 | 先做 EXIF 清除、provider 披露、上传幂等、内存/流式处理和配额；Vision 仅实验与人工确认 |
| JSON Schema / contract tests | 修后复用 | 先消除真实 payload 漂移和残缺校验，再生成三端模型并增加版本协商 |
| LiveRoundPackage / Watch state / event schema | 修后复用 | 收敛条件字段、unknown 兼容、schema/policy version |
| `LiveRoundEventBuilder` 与离线包准备链 | 修后复用 | 接统一 RoundEvent 与 CoursePack，不重复定义语义 |
| event ID / server sequence / cursor / revision 原语 | 修后复用 | 保留协议概念，迁入事务 ledger 并修 partial ACK |
| Apple auth / identity repo / session / player-scoped 隔离 | 修后复用 | 保留隔离模型；补备份恢复、限流、注册策略和会话生命周期 |
| iOS `OfflineStore` 架构 | 修后复用 | 修复 ACK、生命周期和事务边界 |
| iOS Hub 卡片 / `StartRoundView` / `HoleImageMapView` / `RoundShotMapView` | 直接或修改复用 | 重新接入统一状态机与共享选场模型 |
| iOS `RoundEditModel.swift` / `RoundShotEditComponents.swift` | 修后复用 | 提升为赛后校对核心，并修 addShot 字段契约 |
| iOS `CurrentHoleView` | 拆分复用 | 保留组件，重做记录语义和协调器 |
| Watch GeoMath / Units / map geometry / image cache | 直接复用 | 作为各导航候选共享的地图/距离基础 |
| Watch map / distance / scorecard / hole select / caddie views | 修改后复用 | 接真实表冠、状态、降级、系统导航和无障碍 |
| WatchRoundStore / WatchSyncClient / WatchBackendClient | 重构复用 | 合成一份 WAL/outbox 与两个 transport，保留有用字段和传输原语 |
| Watch 五页 / 3+2 分页壳 | 冻结，不作为目标架构复用 | 先用原生任务原型与单根页候选对照验证 |
| Watch legacy 单洞与独立局双产品线 | 淘汰合并 | 统一 coordinator |
| Web AppShell / Sidebar / URL 无关视觉基础 | 直接或修改复用 | 接真实 URL router，重组 IA |
| Web review / prep / map / round / score components | 直接或修改复用 | 合并复盘与统计，保留真实几何与钻取 |
| Web `BagPage` / `ClubBagPage` | 修改后复用 | 合并单一球包工作台；owner 代管另行门控 |
| Web diagnostics / source refs 门控 | 直接复用 | 继续将内部证据与 owner 工具从消费者视图隔离 |
| Web Live/Sandbox/实时 scorer | 退出消费者入口 | 沙盘进备战/诊断；记分改赛后补录 |
| 设计快照与契约测试 | 直接复用 | 增加 baseline、状态流、真机任务测试 |
| 文件型权威 round/event/ACK 数据 | 逐步替换 | PostgreSQL ledger + object storage |

---

## 14. 具体修改建议

### 14.1 设计层立即动作

1. 新建一份产品 North Star Spec，只保留备战、打球、复盘三条主流程。
2. 撤销 Master Spec 的“所有 required capability 都必须做”规则。
3. 撤销 Web Spec 的“一个页面不删”规则。
4. 明确本报告立即冻结 Watch 五页与此前非正式 3+2 的直接实施，但单根页仍只是首选候选；只有新正式 spec 才能授权实现。
5. 定义统一 `RoundEvent`、`RoundState`、`CoursePack`、`DecisionEvidence`、`FactRef`。
6. 在任何新 UI 实现前先画完整任务流和错误/降级状态。

### 14.2 第一优先级：可靠核心

1. iPhone/Watch/Web 使用统一 round ledger、outbox 和结束状态。
2. 明确“记这一杆”“完成本洞”“完成并同步本场”“放弃并删除”四个动作。
3. 修复既有工程报告中的记分丢失、ACK、备份、身份恢复、限流与事实绑定 P1。
4. 让成员能够完成球场搜索、开始球局、备战和同步的所有一级任务。
5. 将关键权威数据迁入 PostgreSQL 事务路径。
6. 建立跨版本契约生成和兼容策略。

### 14.3 第二优先级：界面收敛

1. 为 Watch 制作五页、3+2、Play root 三个原生任务原型；首选候选通过真机任务测试后，再实施 ShotCapture/ScoreHole sheets + 工具栈。
2. iPhone 删除假底栏，拆分 CurrentHoleView，接统一状态机。
3. iPhone 首页合并“上一场/历史复盘/数据统计”。
4. Web 合并复盘与统计的顶层心智。
5. Web 移除消费者侧球童沙盘和手机记分 utility。
6. 订正、报告、来源证据全部上下文化。
7. 统一 Web/iPhone 的球场、T 台和 9+9 选择模型。

### 14.4 第三优先级：复用差异化资产

1. 建立单一版本化 CoursePack。
2. 统一 server-rendered topo + client overlay。
3. 合并在线/离线 caddie 策略并加 `policyVersion`。
4. 让手动记杆真实产生逐杆数据并反哺个人球杆模型。
5. 将单局建议与实际结果放在同一个赛后复盘页面。
6. 用轻量 API 投影替换巨型 stats payload。

### 14.5 暂缓或实验

- AutoShot 产品化；
- Watch 无 iPhone 完成搜索、开局准备和直接云端同步的完整独立主路线；
- Vision 自动判断；
- WebGL 3D；
- 风力 carry 精算；
- 未校准 expected-strokes；
- 推杆级果岭阅读；
- 新的 AI 报告种类；
- 面向公众的家庭/SaaS 扩张。

[AutoShot 评估](../superpowers/specs/2026-07-05-auto-swing-detection.md)已经正确将它降为“受控验证假设”；近期只做一键记杆、影子数据和真机续航验证。

---

## 15. 建议实施顺序

### Stage 0：设计冻结与文档治理

- 写 North Star Spec；
- 写统一球局状态机；
- 标记旧 spec 被覆盖的段落；
- 输出 Web/iPhone/Watch 任务流；
- 不改视觉代码。

### Stage 1：数据可靠性

- round ledger/outbox；
- 结束与恢复；
- schema version；
- 备份/身份/限流；
- 成员一级任务打通。

### Stage 2：三端主流程改造

- Watch 三方案原生原型与任务验证；胜出方案再进入生产；
- iPhone 场中记录语义；
- Web IA 收敛；
- 赛后校对优先。

### Stage 3：引擎统一

- CoursePack；
- caddie policy；
- stats projections；
- manual/Garmin 统一学习闭环。

### Stage 4：实验能力

- AutoShot shadow mode；
- Vision 人工确认；
- 旗向与 AOD 真机验证；
- 任何 3D/风力/预计杆数实验。

---

## 16. 产品验收标准

### 备战

1. Garmin owner、Garmin member、纯手动 member 都能搜索并选择球场。
2. Web 与 iPhone 对同一球场/T 台/洞组显示一致事实。
3. 用户能在 2 分钟内看完关键 3–5 洞。
4. 离线准备状态对用户透明，但可确认成功。
5. 无几何时仍能提供 par、长度与非几何建议，不伪造地图事实。

### 场中

1. 开始球局后直接进入当前洞。
2. 记一杆、完成本洞和结束本场语义完全不同。
3. 断网、锁屏、杀进程、手机不在身边都不丢记录。
4. Watch 抬腕 3 秒内看到距离与主建议。
5. 保存本洞后只推进一次。
6. 未同步结束不会清本地数据。
7. GPS 差、几何缺失、AI 失败均有明确降级。

### 赛后

1. 第一屏先确认“已保存/待同步/缺几杆”，再显示洞察。
2. 订正发生在具体球洞和击球上下文。
3. AI 解释引用真实 fact IDs。
4. 更正后的数据能进入下一次备战和球童模型。
5. 用户能从任何统计钻取到构成它的球局/球洞/击球。

### 工程

1. 同一事件定义不再手写四份不同模型。
2. 一轮球固定 CoursePack 与 policy version。
3. 任何 partial ACK 都保留未确认事件。
4. Watch 与 iPhone 至少有完整 1→18 洞状态机测试。
5. 快照测试比较 baseline，而不只是生成图片。
6. 真机验证覆盖 18 洞续航、AOD、后台、GPS 和 WatchConnectivity。

---

## 17. 对旧文档的覆盖关系

本报告是评估结论，不直接修改旧文件。它的即时效力是：冻结与本报告冲突的新增实现，防止继续按旧五页或非正式 3+2 开工；它本身不是可执行 UI spec。后续正式 spec 必须明确：

### 继续有效

- Master Product Spec 的两个核心产品问题；
- offline-first；
- source/coverage/confidence；
- 三端共享语义、各自拥有 ergonomics；
- 确定性 decision + 可选 LLM explanation；
- 自有 topo + client overlay；
- AutoShot 先实验、后产品化。

### 被本报告否决或要求修订

- “所有 required capability 都必须完成”；
- Web“现有页面一个不删”；
- Web 消费者侧球童沙盘和手机实时记分；
- iPhone“保存本洞”混合记录语义；
- iPhone 假底栏；
- Watch 五页顶层横滑作为默认实施方案；
- 此前非正式 3+2 作为最终 IA；
- 8 秒推荐杆自动写入正式统计；
- AI 报告作为独立产品中心；
- 未校准 expected-strokes/风力模型进入主界面；
- Vision 自动改变权威事实；
- 以功能数量或竞品 parity 作为 roadmap。

---

## 18. 给后续 Claude/Codex 实施者的约束

1. 先读本报告，再读旧 Watch/Web/iOS spec。
2. 旧文档与本报告冲突时，不得盲目服从“定稿/宪法”措辞。
3. 未经原生任务测试和新的正式 spec 批准，不得直接实现五页、3+2、单根页或其它 Watch 导航。
4. 每个改动先说明：
   - 它服务哪条用户任务；
   - 为什么该平台负责；
   - 复用了什么；
   - 淘汰了什么；
   - 无网络/无几何/无 AI 时怎样工作。
5. 不得用“代码已经存在”作为保留功能的理由。
6. 不得用“竞品有”作为新增功能的充分理由。
7. 所有结束、删除、同步和订正动作必须先通过状态机与数据完整性评审。

---

## 19. 最终结论

AI Caddie 的核心不是页面数量、AI 报告数量或 Garmin 功能覆盖率，而是：

> 用可信数据形成个人模型，在赛前给出计划、场中给出可执行建议、赛后解释结果，并把纠错反馈回下一次决策。

当前项目已经拥有实现这个目标的大部分高价值工程资产：

- Garmin 历史与来源证据；
- 球洞几何和自有地图；
- 球杆模型；
- 确定性决策引擎；
- 逐杆复盘与订正；
- 离线包和跨端基础设施；
- 大量测试与快照工具。

真正需要重做的是：

- 功能取舍规则；
- 跨端职责；
- 球局与记录语义；
- Watch 导航；
- Web 消费者/诊断边界；
- AI 的职责边界；
- 权威数据存储和同步状态机。

因此最终建议不是“继续照旧 spec 把页面补齐”，也不是“推倒重写”，而是：

> 先完成设计收口，再把现有强资产接入一个更小、更可信、更符合真实球场使用频率的产品。
