# Codex 对 Claude Fable S70 设计 Round 1 的强对抗审查

> 日期：2026-07-15 UTC  
> 对象：`2026-07-15-claude-fable-s70-design-synthesis-round1.md`  
> 性质：RESEARCH / ADVERSARIAL INPUT，不是正式设计 spec，不授权实现  
> 方法：Codex 主审 + 独立产品攻击 + 独立 rubric 评分 + 仓库源码抽查

## 0. 裁决

Round 1 的原始评分为 **62/100**。由于把多项 Apple Watch 未核证能力写成既定设计，触发红线，裁决分封顶为 **59/100**。

它不是低质量报告。最强部分是：

- 正确撤回了上一轮七项错误 S70 事实；
- 把计分、换洞、逐杆记录拆成不同因果链；
- 明确 `saveActiveHole() → goToNextHole()` 是错误因果；
- 把 `finishedPendingSync`、逐事件 ACK、未同步不清空、统一 coordinator/ledger/outbox 放在 UI 之前；
- 保留手动记杆作为 AutoShot 永久兜底；
- 正确主张 Green View 是独立果岭表面；
- 主动列出十项脆弱假设。

但它尚未证明方向 A 是最优，更不能称为“唯一产品架构”。目前更严谨的结论是：

> 方向 A 是一个值得首先原型验证的候选；其中可靠性骨架可保留，场上交互仍需重做。

## 1. 运行完整性修正

Round 1 的正文、工具调用和设计推理均由 `claude-fable-5` 完成，未发生正文 fallback；但 Claude Code 最终 `modelUsage` 还记录了 `claude-haiku-4-5` 的 2075 input / 24 output。该用量与会话 `ai-title` 自动命名吻合，没有进入正文推理，但这意味着 Round 1 元数据中“未使用其它模型”的绝对表述不严谨。

已做最小复现实验：增加

```text
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
```

后，探针的最终 `modelUsage` 只剩 `claude-fable-5`。Round 2 必须使用该开关，并在元数据中区分：

- substantive design model；
- Claude Code 非实质辅助调用；
- fallback 是否发生。

不得用“正文是 Fable”掩盖运行审计事实，也不得把标题辅助调用误称为正文 fallback。

## 2. 对 Fable 的三项明确让步

### 2.1 Codex 旧规则“保存本洞才推进洞”应撤回

Fable 对这一点的反驳成立。计分保存不能成为换洞的因果门。纯测距用户、不计分用户、漏记分用户都不应因此被困在旧洞。

修正后的原则应是：

- 数据上：计分、换洞、逐杆记录完全解耦；
- 体验上：它们可在自然转场时协同提示；
- 未完成计分形成可恢复的“待确认债务”，不阻塞下一洞；
- GPS/场地只提出或执行换洞候选，不能静默改写成绩。

### 2.2 先立事件契约，再画 Shot/Score 界面

Fable 对旧 ShotCapture/ScoreHole 草图的攻击成立。当前没有 shotId、位置、accuracy、来源、置信度、纠正关系，直接画“删除误报/补记”只是 UI 假象。

### 2.3 五页不值得再占用昂贵真球场验证预算

官方 S70 事实、任务频率和现有工程均已足以淘汰五个顶层兄弟页。真机轮次应优先验证仍未知的根交互，而不是复活明显不合理的五页方案。

## 3. 红线一：方向 A 的记分数学没有闭合

Round 1 同时写了：

- 有账本时用“已记杆数”预填总杆；
- 总杆包含推杆；
- 推杆只是统计，不再次加到总杆；
- 记杆依从率按“非推杆”计算；
- 方向 B 又显示“已记 5 杆 + 2 推 = 7”；
- 罚杆不是物理击球，却也进入总分。

这些定义互不兼容。Round 2 必须先定义至少六个量：

```text
physicalStrikeCount
trackedNonPuttShots
putts
penaltyStrokes
scorecardTotal
unaccountedStrokes
```

并用至少三个具体球洞例子写出关系，包括：

1. 4 次非推杆 + 2 推 + 1 罚，总分 7；
2. 漏记 1 次非推杆，但洞末总分正确；
3. 自动多记 1 杆，但总分和推杆正确。

在该模型闭合前：

- 不能用 shot count 预填总分；
- 不能声称方向 B 可由账本推导成绩；
- 不能把 60%/80% 依从率当 P2 发布门。

## 4. 红线二：三个候选并非三个公平方案

Round 1 的比较是偏置的：

- A 得到完整可靠性骨架、S70 版式、自动换洞、AOD 和全部主动超越项；
- B 基本是 A 加强制逐杆税，更像模式而非架构；
- C 被主动拿掉自动换洞、地图表冠和稳定 AOD，再因这些缺陷被淘汰。

A/B 比的是“数据真相”，C 比的是 IA，比较轴不一致。Round 2 必须先拆开正交决策：

- 默认首帧事实层；
- 表冠语义；
- 逐杆记录策略；
- 换洞自动化程度；
- AI 球童显著性；
- 标准表与 Ultra 的基线关系。

然后重新组成 2–3 个“都值得赢”的候选。至少应包含可信对照：

- 单洞根屏 + 表冠用于显式地图缩放；
- 单洞根屏 + 默认确认式换洞，高置信自动作为后期能力；
- 真正 Apple-native 的单根 NavigationStack/仪表面，而不是故意削弱的常驻页阵。

Fable 可以继续推荐 A，也可以撤回；不得用陪跑方案证明 A。

## 5. 方向 A 不是“被动测距仪”，而是过载主动编排器

默认主屏同时包含：

- 洞号/Par；
- 上一杆；
- F/M/B；
- 洞图；
- 常驻 AI 建议；
- 菜单角标；
- 记杆角标。

一轮中又可能出现：

- 自动换洞全屏宣告；
- 上洞计分小签；
- Club Prompt 半层；
- GPS 错洞常驻标；
- 结束建议；
- 自动暂停守卫。

这与“被动”定位不一致，尤其在 41/42 mm 和非 Ultra 上。Round 2 必须给出最好/典型/最坏三种一洞中断预算：

```text
小签次数 / 半层次数 / 全屏覆盖次数 / 触觉次数 / 必须响应次数
```

并把主屏明确拆为：

- 抬腕一眼的事实层；
- 用户主动进入的操作层；
- 只有高置信数据才出现的意见层。

## 6. 表冠沿洞轴尚未证明合理

Round 1 把一根轴混合成：

```text
全洞 → 障碍 1..n → layup → 果岭特写
```

这里混合了视口、对象选择、战术目标和进入另一表面。进入全图后表冠又变成缩放，计分时变杆数，列表时变滚动。隐含模式过多。

还存在未回答的问题：

- 左右并列障碍如何线性排序；
- 多策略路线如何排序；
- 衣袖/手腕误转如何恢复；
- 焦点丢失时表冠归谁；
- 用户如何知道当前控制的是 target、zoom 还是 scroll；
- 6× 缩放但不允许平移时，偏离缩放中心的目标如何查看。

“4/5 人前三洞发现”不能证明它优于缩放。必须比较至少两种真实原型，并测：指定目标到达时间、选错率、误转率、湿手/手套成功率、回到主距离的时间。

## 7. 自动换洞的默认策略和门槛不合格

“误换 ≤1 次/18 洞”不是可信仪器的通过线。一次误换就可能展示错误码数、错误建议，并把下一杆归到错误洞。

必须覆盖：

- 球车路径经过下一洞后 tee；
- 前 tee 用户经过后 tee；
- 相邻/交叉 tee；
- shotgun start、跳洞、补洞；
- 双果岭、共享果岭；
- 9→10 经过会所；
- 下一洞 tee 紧邻本洞果岭；
- 用户先到下一 tee、上洞仍未完成。

“全屏宣告 + 墙钟 10 秒撤销”也不成立：用户垂腕 30 秒后才看表时，撤销已失效。撤销至少要绑定“用户看见后”或“下一杆确认前”，而不是纯计时。

Round 2 必须分别比较：

1. 默认建议、用户确认；
2. 高置信自动切换、可见候选期；
3. 用户选择开启的 S70 式自动。

数据上计分不能驱动换洞，但成绩状态可以作为置信证据；体验上换洞应触发上洞计分债务提示。

## 8. 记杆按钮保存的是“点击位置”，不一定是“击球位置”

用户可能：

- 挥杆后看球、走出数米才点；
- 挥杆前点，随后换杆或取消；
- 在球车或球伴球位旁点；
- 在 GPS 陈旧或无 fix 时点。

因此手动/自动检测首先只能产生候选击球：

```text
candidateShot(source, capturedAt, observedPosition?, accuracy?, confidence?)
```

成功触觉只能代表“候选已可靠保存”，不能代表洞、位置和击球事实均正确。Round 2 必须说明手动按钮的前/后时序、无 fix 降级、走开后补录，以及如何把错误位置标为 unknown 而不是伪精确。

## 9. Club Prompt 与 AutoShot 反馈存在直接矛盾

Round 1 同时写了：

- “击球时间窗永不主动触觉”；
- AutoShot 成功产生轻 tick；
- “不弹窗”；
- Club Prompt 半层自动升起；
- 半层下滑 = 保持 unknown；
- 裁决表又写半层下滑 = 误报。

最后一条甚至可能删除真击球。Round 2 必须给出唯一语义，并说明：何时出现、覆盖什么、多久保留、用户忽略后如何继续、漏检时如何补、误报时如何撤销。

## 10. 计分与换洞应数据解耦、体验协同

Fable 正确拆开了数据因果，却把提示时机也拆散了。走向下一 tee 是自然的计分提醒时刻。合理原则是：

- 换洞独立发生；
- 洞转场可生成上洞 `scoreDebt`；
- scoreDebt 不阻塞下一洞；
- 默认 Par 只能是编辑器初始值，不能冒充已确认成绩；
- 未确认成绩必须在计分卡和结束流程中持续可见。

“新洞上无触觉小签”很可能完全漏掉。Round 2 必须说明计分债务如何再次出现、何时升级提醒、用户如何在数洞后修复。

## 11. AI 球童常驻行既太抢又太弱

主屏“7 铁 · 打前沿”会被理解为权威建议，但 v1 明确没有可靠风数据，lie、真实旗位和个人球杆样本也可能不足。

必须区分：

- 距离是事实；
- AI 建议是带条件的意见；
- 推荐球杆绝不能自动成为实际使用球杆。

Round 2 必须定义建议的有效条件、TTL、输入缺失、target/pin/GPS 更新后的失效与重算，以及陈旧/低置信时主屏如何消失或降级。

## 12. Apple Watch 平台能力被写得过于确定

以下均应先列为 PLATFORM UNKNOWN，除非提供 Apple 官方依据或真机证据：

- HKWorkoutSession 自动带来所需的后台 GPS 与 AOD 行为；
- AOD 能按需要频率更新实时中距；
- 左缘右滑可承担所有 push Back；
- 表冠、列表、页面和浮层可按文中方式稳定仲裁；
- Ultra Action Button 可在该上下文可靠作为一键记杆；
- 垂腕后系统必然恢复到期望的深层表面。

核心产品必须在标准 Apple Watch、无 AOD、无 Ultra Action Button、湿屏/手套下仍成立。AOD 和 Ultra 只能增强，不能是架构支柱。

还必须补充这些工程前置条件：

- AOD 只覆盖部分机型，用户可全局或按 app 关闭；
- workout/background session 不保证任意 GPS/UI 更新 cadence；
- 同一时间只能维持一个 workout session，被其它 workout 抢占时必须降级；
- 当前工程尚没有 HealthKit entitlement、权限文案和后台配置；
- 必须明确是否写入 Health workout/活动圆环，以及权限拒绝后的基础模式。

Digital Crown binding 本身可做，但依赖 `.focusable()` 和焦点仲裁；“过 Par 加重哒声”不应冒充系统标准 detent。watchOS 的竖页能力存在，也不等于嵌套 ScrollView/Crown 与 AOD 恢复行为已被证明。

## 13. 自动暂停守卫存在生命周期矛盾

“自动 paused，但不产生数据变更”是自相矛盾。`active → paused` 会影响 GPS、Workout、IMU、AutoShot 和事件归属。误暂停可能直接制造漏杆。

在证明自动暂停无害前，结束守卫只能：

- 提醒；
- 标记疑似离场；
- 保持数据采集或使用明确降级策略；
- 绝不静默改变 active round 的记录语义。

## 14. 工程复用矩阵有两项过度乐观

### 14.1 WatchGeoMath 不是反投影直接复用

当前 `WatchGeoMath` 只有 geo→pixel 和 haversine，没有 pixel→geo。逆变换可以基于现有 refs 新增，但应归为“修改复用”，并增加退化矩阵、范围外点击和数值稳定性测试。

此外，`holeMap.you` 不能稳定视为 tee：手机有实时 GPS 时会把它覆盖为玩家位置。当前全轮状态也没有明确的所选 tee / 最远后 tee 经纬度。因此自动换洞需要新增完整洞序、每洞 tee anchors、所选发球台和几何置信信息，不能靠现有 `holeMap.you` 反推成立。

### 14.2 WatchRoundStore 不是 WAL

当前 store 是 JSON snapshot 原子覆盖，不是高频 append-only ledger。Round 2 必须定义：

- append 与 checkpoint；
- replay 与去重；
- 崩溃中断；
- phone/watch 并发纠正；
- 双通道路由租约；
- server idempotency；
- 逐事件 ACK；
- snapshot/cursor 合并。

“单 WAL + 手机主通道/直连备通道”目前只是愿望。网络可达性变化期间如何防重复和乱序必须明确。

### 14.3 手机 ACK 与服务器 ACK 不是同一层

当前手机中继的成功只表示事件已持久化进 iPhone `OfflineStore`，不等于服务器已经接受；Watch 直连的响应才接近服务器 ACK。至少需要区分：

```text
watchPersisted → handedOffToPhone → serverAccepted / serverRejected
```

并处理 rejected dead-letter、phone/server 两级重放和最终 reconciliation。`finishedPendingSync → synced` 不能由任一通道的单次成功直接触发。

### 14.4 新事件是全栈契约变化

`shot / holeScore / holeAdvance / pinSet` 不只是 Watch 枚举扩容。当前 Swift、后端 Pydantic、JSON Schema、reducer/replay、统计、Web/iOS 消费者均依赖封闭事件集合。Round 2 不得在未核全栈的情况下把它估成局部中等改动。

### 14.5 自动 fairway L/C/R 没有数据地基

当前只有 `fairwayResult` 结果字段，没有 fairway polygon/边界。route anchors 或 topo 位图不足以可靠判断落点左/中/右。v1 应保持人工输入，或把自动预填降为独立数据设计假设。

### 14.6 生产通路不只是“补一根 seed 线”

当前手机只推当前洞单状态。真正统一 standalone/companion 还需要全轮状态包、洞序、tee/green/projection、地图 manifest、版本与完整性、缓存淘汰、增量更新和失败恢复。可以复用 builder 与传输原语，不能把产品接线写成一个 `seedRound()` 调用。

### 14.7 尺寸矩阵必须按 point bounds，不按表壳毫米猜

Round 1 的 `198pt≈46mm` 不准确：198pt 更接近旧 45mm，Series 10 46mm 约 208pt；Ultra 49mm 的可用 point 宽度也不必然比 46mm 更宽。因此“Ultra 最舒展”不能仅凭 49mm 得出。

S70 尺寸事实也补错了：454×454 对应 47mm，42mm 为 390×390。Round 2 必须撤回该断言，并按真实 point bounds、safe area、圆角和 Dynamic Type 建原型矩阵。

## 15. 可靠性不能只等于“不丢数据”

以下错误数据也可能被完美持久化和同步：

- 归错洞的 shot；
- 点击位置冒充击球位置；
- 不准确 pin；
- 默认 Par 冒充已确认成绩；
- AI 推荐冒充实际球杆。

新不变量必须同时包含：

- 不丢；
- 不重复；
- 不把低置信推断冒充事实；
- 手动确认优先；
- 来源与纠正链可审计；
- 旧自动结果不能覆盖新人工结果。

## 16. 当前量化数字只能是 pilot 观察值

以下门槛没有足够来源或样本：3 人 p90、5 人 4/5、54 次换洞、两轮标定、每轮一次误换、60%/80% 依从率、S9 75% 耗电、触觉 80%、拖旗 4m、罗盘 10°。

Round 2 必须把数字分成：

- hard invariant / release gate；
- pilot observation target；
- 需要 S70 或当前 App 基线后才能设定。

低频高损害错误（误换洞、丢事件、错归属）不能用小样本“未发生”证明安全。

## 17. Round 2 必须逐项交付

Fable 不应写一篇防御性扩写，而应对本审查逐条标记：

```text
保留 / 修改 / 撤回 / 仍待真机
```

并交付：

1. 修正后的运行元数据；
2. 封闭的计分/逐杆真相模型与三个例子；
3. 2–3 个同等强度候选，不得陪跑；
4. 围绕四个真实瞬间的完整一洞时序：球前抬腕、击球后、走下果岭、到下一 tee；
5. 每个瞬间的屏幕、用户动作、内部事件、失败恢复；
6. 最好/典型/最坏的提示和触觉预算；
7. 默认自动换洞、确认式换洞、用户开启自动三者的公平比较；
8. 唯一的表冠/触摸/返回/半层语义；
9. 平台 CONFIRMED / PROTOTYPE-ONLY / UNKNOWN 表；
10. 41/42、45/46、49 mm 的内容取舍，不得只给百分比；
11. AI 建议的新鲜度、置信度和失效规则；
12. 单 ledger/双传输的排序、幂等和冲突语义；
13. 重新评分并说明推荐是否改变；
14. 若仍推荐 A，只能称“优先原型候选”，除非核心未知已被证据消除。

## 18. 必须保留的收敛结论

Round 2 不应为了反驳而推翻以下已收敛内容：

- 五个顶层兄弟页淘汰；
- 单一当前洞心智；
- F/M/B 和洞图是首帧核心候选；
- 计分不驱动换洞；
- Green View 独立；
- shot/score/holeAdvance 是不同事件；
- `finishedPendingSync` 和未同步不清空；
- 统一 coordinator、ledger、事件契约与 outbox；
- AutoShot 只是可替换 producer；
- 手动补杆与 append correction 永远存在；
- 未校准 AI 数字不进入主屏；
- 现有 topo、Canvas、route/anchor 等渲染资产优先复用；
- 所有用户尚未体验的功能保持“待验证”，不得写成用户已认可。
