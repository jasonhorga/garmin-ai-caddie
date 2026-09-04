# Apple Watch 产品决策账本与后续任务总表

> Status: STANDING OWNER DECISION QUEUE COMPLETE  
> Product owner: 用户  
> Review partners: Codex + 纯 Fable 最终对抗审查  
> Last updated: 2026-07-17  
> Current decision: none  
> Next decision: none in the standing queue; enter canonical spec/evidence work  
> Implementation state: 未授权；本阶段只做决策、规格、原型与验证，不改产品代码

## 1. 这份文件解决什么问题

这是一份持久的单一账本，用来防止讨论在某个分支越挖越深后遗失主线。

执行规则：

1. 任意时刻只能有一个 `CURRENT` 决策。
2. 每次只向用户提出一个决策问题，不在同一轮夹带下一题。
3. 用户回答后，先把答案、理由、影响和变更历史写回本文件，再把下一项改为 `CURRENT`。
4. 已决定事项不靠覆盖旧文字来修改；任何重开都追加一条变更记录。
5. 标为 `EVIDENCE NEEDED` 的事项，在原型或真机证据完成前不得让用户凭感觉拍板。
6. 技术阈值、事件 schema、幂等、续航数字、GPS 几何参数等由工程证据决定，不无必要地转嫁给用户。
7. 在当前必须确认的 Owner 决策、canonical 规格和用户书面审批完成前，不进入产品代码实施。
8. Codex、Fable 或其调用链若遇到 `429`、`503`（包括上游根因实际为 `429`）、`capacity`、`cooldown` 或 `stalled` 等瞬时容量错误，必须保持原模型、原 effort、原会话输入与无 fallback 约束，自动定时重试直到成功；不得把一次瞬时失败当成审查结论。优先遵守服务端 `Retry-After`；未提供时按 `30s → 60s → 120s → 300s → 900s` 递增，达到 `900s` 后每 `900s` 持续重试。只有鉴权、配置、无效参数等确定性错误才暂停以修正或报告。
9. `EVIDENCE NEEDED` 不等于“证据完成后必问 Owner”；证据若唯一推出答案，由工程直接落规格。只有证据后仍存在真实价值取舍，或要重开既有 Owner 决定时，才重新进入单题队列。

状态定义：

| 状态 | 含义 |
|---|---|
| `CURRENT` | 当前唯一正在讨论的事项 |
| `QUEUED` | 已登记，按编号等待讨论 |
| `EVIDENCE NEEDED` | 必须先完成指定原型、真机或数据验证，再讨论 |
| `DECIDED` | 已有明确结论；若重开必须追加变更记录 |

## 2. 当前检查点

| 字段 | 当前值 |
|---|---|
| 当前问题 | 无；常设 Owner 决策队列已完成 |
| 用户上一次已落盘答案 | D04：采用 B，Watch 可独立搜索球场、选择洞组/Tee、下载真实球场包并开局；iPhone 只是可选准备/同步端 |
| 下一步 | 进入 canonical 文档、Spike 与证据路由；只有登记条件真正触发时，才一次一个地把条件重开项交回 Owner |
| 当前常设 Owner 队列 | 空；D 项均已决定、工程可决或证据先行 |
| 当前阶段出口 | **已达到**：D02、D04 均 `DECIDED`，直接决定项已落盘，条件重开项已登记 |
| 产品代码 | 保持不动 |

## 3. 不再重复讨论的已锁定基线

以下不是当前提问队列。它们已经由用户明确锁定，或已在 Codex × Fable 对抗审查中站住；如需改变，必须明确发起重开，不能在后续文档中静默推翻。

| ID | 状态 | 已锁定结论 | 决策来源 |
|---|---|---|---|
| L01 | `DECIDED` | 五页横滑淘汰 | S70 证据、任务频率、Codex × Fable 一致结论 |
| L02 | `DECIDED` | 三页不作为产品方向；只有单根页入口田测失败时才重启评估 | Codex × Fable 终审 |
| L03 | `DECIDED` | 推荐架构为“单一当前洞根页 + 浅层仪表面 + 单一交互仲裁器” | Codex × Fable 终审 |
| L04 | `DECIDED` | 击球、成绩、当前洞是三条独立事实链 | 用户流程 + 对抗审查 |
| L05 | `DECIDED` | `fairwayResult` 可见值只允许 `HIT / LEFT / RIGHT` | 用户锁定 |
| L06 | `DECIDED` | `startLie` 是本杆起始球位；`endLie` 独立 | 用户锁定 |
| L07 | `DECIDED` | Club Prompt 只补球杆；跳过不会删除击球；推荐杆不会自动写成实际杆 | 用户锁定 + 对抗审查 |
| L08 | `DECIDED` | Tee 同点多杆只暴露最后一杆；原始观测仍可审计 | 用户锁定 + S70 证据边界 |
| L09 | `DECIDED` | 非 Tee 约 10 码分组是数据实证，不冒充 Garmin 官方规格 | 证据包 + 对抗审查 |
| L10 | `DECIDED` | 唯一新增拆分语义是“打厚了”；不增加 OB、Mulligan、暂定球恢复 UI | 用户锁定 |
| L11 | `DECIDED` | “打厚了”入口为上一杆、洞末差额、本洞击球列表；不弹近距二选一 | 用户锁定 + Codex × Fable 结论 |
| L12 | `DECIDED` | 快速接受默认成绩后不再逐项追问 | 用户锁定 |
| L13 | `DECIDED` | 手动确认顺序为总杆、推杆、Par 4/5 Fairway、罚杆 | 用户锁定 |
| L14 | `DECIDED` | 下一洞首杆可 provisional；上一洞成绩确认优先；取消推进则候选杆归回上一洞 | 用户锁定 |
| L15 | `DECIDED` | 任意洞成绩可随时修改，且编辑历史洞不得改变 `activePlayHole` | 用户锁定 |
| L16 | `DECIDED` | 除明确 Discard 外，未同步数据不得清空 | 用户锁定 + hard invariant |
| L17 | `DECIDED` | 任意时刻至多一个未决 `ResolutionEpisode` | Fable 对抗审查修正 |
| L18 | `DECIDED` | v1 不显示成功率/概率，不接入风或空气密度，不做推杆级果岭等高线；PlaysLike 只使用已核实的高差 | 2026-07-02 Owner 铁律；后续重审不得静默带回 |
| L19 | `DECIDED` | 完整 Caddie 不复制 S70 的上果岭概率；`AVG. STROKES` 只有在本产品完成真实自校准后才能显示 | Owner 零假精确铁律 + S70 机制证据边界 |
| L20 | `DECIDED / DERIVED` | 任意玩家至多一个前台 `active` 球局；开始新局不得清空或覆盖旧局，旧局必须进入明确、可恢复的非前台状态（如 `suspended`，或经明确结束后成为 `finishedPendingSync`）；允许多个被保留的非前台球局，只有显式 Discard 才删除。自动挂起还是先询问属于 T092 规格审批细节 | L16 + D09a/L04 的事件归属唯一性 + 07-14 C3 生命周期缺口；不是仅由 L16 单独推出 |
| L21 | `DECIDED` | 面向用户的距离统一显示“码”；内部契约和计算可继续用米，但必须在展示/输入边界明确换算，不能混用 | 2026-06-11 用户原话“所有的 m 都换算成码给我显示” |

## 4. Owner 级产品决策队列

本节同时保留“尚待用户逐项确认”和“已经由用户语义/联合结论确认”的 Owner 级决策。已是 `DECIDED` 的项目只作为检查点，不会重复询问。

### D01 — 18 洞成绩环是否常驻 Hole Root

| 字段 | 内容 |
|---|---|
| 状态 | `DECIDED` |
| 为什么必须用户定 | 用户此前明确要求保留；任何移除都属于重开 Owner 决定，Codex/Fable 无权静默覆盖 |
| 调查状态 | **VERIFIED CORRECTION**：此前“没有成绩环”的结论已被 Garmin 官方手册、官方标注图、42/47mm 产品图和多份球场实拍证伪 |
| S70 已核事实 | S70 的实体内圈印有 1–18 洞编号；开启记分并完成各洞后，屏幕边缘会出现与洞号对齐的逐洞彩色分段弧。官方产品图、球场实拍和多个视频封面均明确可见 |
| 证据单 | [S70 成绩环证据更正](2026-07-15-s70-score-history-ring-evidence-correction.md)：含 Garmin 官方原文、官方标注图、颜色表、实拍交叉证据和错误根因 |
| 方案 A | 保留在 Hole Root，并把 Apple Watch 的屏内环明确设计成 S70“实体洞号刻度 + 屏内逐洞彩色弧”的平台翻译 |
| 方案 B | 尽管 S70 有环，仍因 Apple Watch 首帧密度而移到 Scorecard；这会降低 S70 还原度 |
| 方案 C | 根页默认显示，但进入地图缩放、拖旗或其它交互轴时条件隐藏；是否符合 S70 的隐藏时机仍需继续核验 |
| 当前建议 | **A**：既有 Owner 决定是保留，而且新的一手图片证据证明它确属 S70 体验；只有 Apple Watch 真机布局证明确实挤压核心读距时才讨论条件隐藏，不再讨论整体移除 |
| 用户决定 | **A / KEEP**。沿用既有 Owner 决定；本轮错误申请重开已撤销，不再重复询问 |
| 决定理由 | 用户此前明确保留；新的一手证据证明成绩环确属 S70 核心 Score History 体验 |
| 影响 | Hole Root IA、Watch 视觉系统、Scorecard、Big Numbers、42/46mm 布局原型 |
| 下一项 | D02 |

### D02 — Hole Root 的球童呈现形态

| 字段 | 内容 |
|---|---|
| 状态 | `DECIDED / S70 BEHAVIORAL PARITY / C′` |
| 为什么必须用户定 | 现有根页路线是用户已经看过的产品视觉；新证据同时否定“无条件常驻整洞路线”和“根页永远零球童”，需要 Owner 明确选择新的产品方向 |
| 调查状态 | **VERIFIED CORRECTION**：Garmin 官方产品图、当前手册、Support 与连续实拍确认 S70 采用“根页条件当前杆建议 + 点击后完整 Virtual Caddie”的两层结构 |
| 证据单 | [S70 Virtual Caddie / Driver Arc 专项证据](2026-07-16-s70-virtual-caddie-driver-arc-evidence.md)；[纯 Fable D02 独立对抗审查](2026-07-16-claude-fable-d02-virtual-caddie-adversarial-review.md)；[Codex 当前实现复用审计](2026-07-16-codex-d02-current-implementation-reuse-audit.md) |
| 方案 A | 根页无条件常驻 `you → layup → green` 的确定性整洞两段路线；延续当前实现 |
| 方案 B | 根页只显示洞号/Par、F/M/B、地图、成绩环、球员位置和适用时的 Driver Arc；所有球童建议都进入 Caddie / Map Detail |
| 方案 C′ | **条件单杆球童层**：根页永久保留事实层；只有当前一杆建议真实、可信、新鲜且模式允许时，才显示推荐杆、当前一杆瞄准线和真实历史散布；点击推荐杆进入完整 Caddie。任何门槛不满足时整层消失、根页自动退化为 B；根页永远不画确定性的整洞多杆路线 |
| 数据诚实前置 | 当前只有纵深 p10/p90，没有横向历史散布；Watch 契约也没有完整传递 p10/p90、样本量、新鲜度和门控字段。在这些契约完成前，C′ 的运行行为必须退化为 B，不得继续画固定装饰椭圆或未校准 `expectedStrokes` |
| 联合建议 | **C′**：Codex 与纯 `claude-fable-5 / max / 无 fallback` 独立复核一致；它最接近 S70，同时把 B 作为低置信、陈旧、Big Numbers、Tournament、关闭或数据不足时的法定零状态 |
| 用户决定 | **直接对标 S70。**采用 S70 的可观察双层行为：根页永久事实层；建议真实、可信、新鲜且模式允许时显示当前一杆推荐、瞄准线与真实个人散布；点击进入完整 Virtual Caddie；条件不足时整层消失并退化为 B |
| 对标边界 | 对标任务流、信息层级、状态切换和恢复行为，不逐像素复制，也不使用 Garmin 专有地图资产或假装知道其内部阈值；继续遵守 L18/L19：无上果岭概率，未真实自校准前无 `AVG. STROKES`，Apple Watch 的 Crown/触摸/haptic 做平台翻译 |
| 决定理由 | Owner 认为既然 S70 证据已经研究透彻，就应直接以 S70 为产品基准，而不是继续在抽象 A/B/C 中折中；C′ 正是 S70 根页轻量当前杆建议 + 完整球童详情的准确工程表达 |
| 影响 | Hole Root、Map Detail、完整 Caddie、Driver Arc、散布数据契约、推荐新鲜度状态机、GPS 触发重算与小表径降级 |
| 下一项 | D04 |

### D03 — 是否正式降低旧 Watch 文档的权威级别

| 字段 | 内容 |
|---|---|
| 状态 | `DECIDED / ENGINEERING GOVERNANCE / A` |
| 重分类结论 | 不再是 Owner 三选一。06-22 与 Round 1/2 本来就是研究输入；07-10 两份模型“定稿”既无 Owner 批准记录，又与 L01–L03、L07 冲突。并列生效会制造双重真源，删除又破坏历史证据，只有 A 合法 |
| 执行动作 | 标为 `Historical Input / Superseded`；写 supersession ADR；先把仍有效的 Owner 语义抽入 canonical 文档；保留原文件，不删除 |
| Owner 处理 | 执行后通报并保留变更记录，不占逐题审批队列；任何具体 Owner 语义若要改变，必须另行申请重开 |
| 决定理由 | 单一权威治理 + 既有锁定语义优先；07-10 的“8 秒后按推荐杆自动记入”还直接违反 L07 |
| 影响 | 文档权威图、ADR、旧规格页头、后续实现依据 |
| 下一项 | 不重复询问；D02 后直接进入 D04 |

### D04 — 首版 Watch 独立边界

| 字段 | 内容 |
|---|---|
| 状态 | `DECIDED / B / WATCH-INDEPENDENT COLD START` |
| 为什么必须用户定 | 用户已明确要求学习 Garmin“启动新一局的流程，尤其是手表”；此前范围也已批准 Watch 端“附近球场 → 洞组 → 发球台”、下载并独立开局，以及不带手机完成整轮。现在若改为 iPhone 预装，是对既有 v1 产品承诺的显式收窄，不能由实现难度自动决定 |
| 准确问题 | 是否授权把已批准的 Watch 冷启动独立范围收窄为：iPhone 预装真实整轮包；Watch 只能从已安装包开始/恢复，但开球后可完全脱离手机打完整轮？ |
| 方案 A | **批准收窄**：v1 Watch 不搜索或下载新球场；腕上开局向导只列已安装包。大量复用 iPhone 选场、`LiveRoundPackage` 与缓存，交付更快，但临场未预装球场无法开局。当前默认 18 个 Par 4 的空白“练习记分”只保留为测试脚手架，不作为生产兜底 |
| 方案 B | **保持既有范围**：Watch 独立搜索、选场、选洞组/Tee、下载并开局；iPhone 只是可选准备/同步面。最接近 S70，工程上需新增 Watch 认证、搜索、包下载、原子安装与半包恢复 |
| 删除的旧方案 | 原 C“Watch 全程依赖 iPhone 在线”违反已锁定的独立整场承诺，不再作为有效选项 |
| 通用记分占位 | 无论 A/B，当前无球场包的默认 18×Par 4 “练习记分”均不是已批准产品模式；生产路径退役。未来若要做独立通用记分卡，作为新功能范围另立重开，不藏进 D04 |
| 联合建议 | **B，保持既有范围**：先按产品最优和 S70 独立体验判断；若 Owner 明确把最短 v1 上线置于完整独立性之上，再选 A |
| 用户决定 | **B，保持既有范围。**Watch 自己完成球场搜索、洞组/Tee 选择、真实球场包下载与开局；完成开局后也可不依赖 iPhone 打完整轮。iPhone 是可选的准备、缓存协助与同步面，不是腕上冷启动的必需前置 |
| 决定理由 | 直接对标 S70 的完整独立体验；不能因为现有 iPhone 代码更容易复用，就把产品设计收窄成 companion。A 可以作为内部交付里程碑，但不改变最终产品范围，也不得把 18×Par 4 测试脚手架包装成生产兜底 |
| 分期边界 | 工程可以先完成 A 所需的真实包安装、缓存与离线整轮能力，再补齐腕上搜索/下载；但在 B 的链路完整前，只能标为中间里程碑，不能宣称 D04 已实现 |
| 影响 | 开局旅程、full-round package、缓存、同步生命周期、错误降级 |
| 下一项 | 常设 Owner 队列完成；进入 canonical 文档、Spike 与证据路由 |

### D05 — AutoShot 首发策略

| 字段 | 内容 |
|---|---|
| 状态 | `DECIDED` |
| 为什么属于产品策略 | 这是产品承诺和设备覆盖策略；具体机型仍由证据决定 |
| 方案 A | 首批高频能力设备直接 Beta；旧设备 100Hz 影子验证后第二批；所有设备永久保留手动补杆 |
| 方案 B | 等所有目标设备都达到同一门槛后一次性发布 |
| 方案 C | 首版只做手动记杆，AutoShot 全部后置 |
| 联合建议 | **A**：不无限后置 AutoShot，同时不拿旧设备和续航风险赌全量体验 |
| 用户决定 | 采用方案 A |
| 决定理由 | 用户已明确要求 AutoShot 不得因困难无限后置；Codex × Fable 终审据此收敛为分批 Beta |
| 变更关系 | 本决定取代 2026-07-02 D4“实时挥杆识别 v1 先不做”的旧范围；轨迹确认仍可作为旧设备/影子期兜底，不是主产品承诺 |
| 影响 | Beta 标签、支持矩阵、Motion/续航 spike、遥测和发布门 |
| 下一项 | 不重复询问 |

### D06 — v1 默认换洞策略

| 字段 | 内容 |
|---|---|
| 状态 | `DECIDED` |
| 为什么属于产品策略 | 它决定腕上打球时系统主动程度和误换洞风险 |
| 方案 A | 确认式默认：位置只形成候选；上一洞成绩确认后才推进；下一洞候选首杆先 provisional |
| 方案 B | 高置信时自动推进，低置信才确认 |
| 方案 C | 完全手动换洞，不使用位置候选 |
| 联合建议 | **A**：与用户描述流程一致；B 只做原型/遥测对照，未来是否升级另立证据门 |
| 用户决定 | 采用方案 A |
| 决定理由 | 用户已经逐条定义“上一洞确认优先、下一洞首杆 provisional、Cancel 继续上一洞”的确认式流程 |
| 条件重开 | E07 只有在 tee-anchor、误换/漏换和长期遥测显著过线时，才能申请把默认改为高置信自动推进；这会重开 D06，必须回 Owner，工程不得自行升级默认 |
| 影响 | Location/Hole Engine、ResolutionEpisode、成绩确认、触觉与中断优先级 |
| 下一项 | 不重复询问 |

### D07 — 首版是否有意不做 Handicap / 净杆

| 字段 | 内容 |
|---|---|
| 状态 | `DECIDED / V1 GROSS ONLY / NET-STABLEFORD LATER` |
| 既有 Owner 决定 | 2026-06-09/10 已与用户逐屏确认：默认比杆；Stableford / 净杆按差点作为后续制式选项 |
| 当前语义 | v1 先完成可靠 gross score、逐杆、修改和复盘；schema 保留扩展位；`handicapEstimate` 永远明确标“估算”，不得冒充官方 Index 或规则正确净杆 |
| 工程复用 | 已有差点估算与逐洞 stroke index 可在后续部分复用；完整净杆仍需 rating/slope、Handicap Index、Course/Playing Handicap 和规则口径 |
| 决定理由 | 纯 Fable 终审要求的是把既有范围显式记入 decision，而不是重新让 Owner 选择 |
| 影响 | 计分规格、Scorecard、统计口径、后端 contract |
| 下一项 | 不重复询问 |

### D08 — “不记分模式”是否仍记录逐杆

| 字段 | 内容 |
|---|---|
| 状态 | `DECIDED / C / DERIVED` |
| 分类 | 不是 Owner 取舍；L04 三条事实链独立已经排除耦合方案，C 是唯一有效 contract |
| 决定语义 | `scoringEnabled` 与 `shotTrackingEnabled` 独立；关闭记分只让成绩链为空，不静默改变 AutoShot、Club Prompt、手动补杆和逐杆开关；状态明确显示并记住 |
| 决定理由 | A 把采集写成不可控“始终运行”，B 违反 L04；独立设置同时满足语义诚实与用户控制 |
| 影响 | 开局设置、shot ledger、统计、球局完成条件 |
| 下一项 | 不重复询问 |

### D09 — Watch 是否只记录佩戴者本人

| 字段 | 内容 |
|---|---|
| 状态 | `DECIDED / SPLIT` |
| D09a | `DECIDED / WEARER ONLY / DERIVED`：腕上成绩、逐杆、Motion/GPS 事件只归已认证佩戴者；事件显式绑定 player/wearer，不出现球员选择器 |
| D09b | `CLOSED / OUT OF BUILD SCOPE`：同组手填总分不在当前 friend/group/team/social 产品边界；S70 现有 Watch 证据也未证明腕上多人卡是核心体验。未来若要腕上多人卡，作为新功能重开 |
| S70 对照 | S70 v5 官方 Keeping Score 子树无多人计分主题，未发现它是 S70 腕上核心体验；因此不因“对齐 S70”增加该 Owner 门 |
| 决定理由 | 传感器归属是物理与数据隔离不变量；多人卡是另一产品项目，旧 A/B/C 把两者错误捆绑 |
| 影响 | Watch 计分 IA、多人 contract、统计归属、同步 |
| 下一项 | 不重复询问 |

### D10 — Watch 端允许多深的赛中/赛后编辑

| 字段 | 内容 |
|---|---|
| 状态 | `DECIDED / A′ / DERIVED` |
| 决定语义 | Watch 可随时改任意洞总成绩，并完成继续打球所需的当前洞、未决杆和最近问题修正；“最近”覆盖几洞与入口由原型决定 |
| 平台分工 | 全量跨洞逐杆位置、球杆、顺序、归属和球位深编辑归 iOS；Web 按 2026-07-07 Owner 定稿保持只读，不得写成 iPhone/Web 都是深编辑器 |
| 删除的旧方案 | B 重开既定平台分工且不适合腕上；C 违反 L11 的“打厚了”与本洞击球列表恢复入口 |
| 数据规则 | 所有修改使用 append-only correction；历史编辑不得改变 `activePlayHole` |
| 影响 | 本洞击球列表、历史洞入口、correction contract、iOS/Web 复盘分工 |
| 下一项 | 不重复询问 |

### D11 — v1 是否定位为休闲/训练产品，而不宣称正式比赛合规

| 字段 | 内容 |
|---|---|
| 状态 | `DECIDED / PERSONAL LEISURE-TRAINING / NO COMPLIANCE CLAIM` |
| 既有产品边界 | Master Product Spec 定义为个人高尔夫智能产品，并明确当前 build 排除 tournament / team / PK / social product surface |
| 决定语义 | v1 不宣称正式比赛合规；Tournament Mode 只能作为明确隐藏受限能力的模式，不能包装成赛事合规认证。是否在 v1 上架该开关属于规格优先级，不是新的 Owner 战略题 |
| 条件重开 | 只有 Owner 未来主动进入正式赛事产品轨道，并完成规则、地区、赛事与法务证据后，才申请重开 |
| 决定理由 | 当前没有合规矩阵；旧 B 是未经提出的产品边界扩张，旧 C 也不能以“用户负责”替代产品门控 |
| 影响 | Caddie、天气、PlaysLike、Tournament Mode、营销与 QA 矩阵 |
| 下一项 | 不重复询问 |

### D12 — AutoShot Beta 的训练数据与上传隐私政策

| 字段 | 内容 |
|---|---|
| 状态 | `D12a DECIDED / D12b EVIDENCE NEEDED` |
| D12a 隐私底线 | 单独 opt-in、默认不上传；不整轮持久化原始高频流；未确认推断不进入正式统计；同意可撤回、用途受限、支持删除 |
| 删除的旧方案 | “参加 Beta 即默认上传原始/高频窗口”违反既有隐私底线，不是有效 Owner 选项 |
| D12b 证据任务 | 先证明最小压缩窗口上传对模型质量确有必要，并给出字段、时长、用途、保留期、撤回和删除方案；无证据时保持完全本地 |
| 条件 Owner 问题 | 只有 D12b 证据成立时，才询问是否运营独立的研究数据捐赠计划；不会把默认上传重新列为选项 |
| 决定理由 | 隐私底线已由敏感数据最小化原则和此前 AutoShot 规格锁定；余下是数据必要性证据，不应凭偏好先拍 |
| 影响 | Beta onboarding、隐私文案、遥测 contract、保留期、删除请求和后台管线 |
| 下一项 | D12b 先做证据，不占常设 Owner 队列 |

### D13 — Golf Workout 是否写入 Apple Health

| 字段 | 内容 |
|---|---|
| 状态 | `EVIDENCE NEEDED` |
| 重分类结论 | 当前三选一过早假定 Workout 后台生命周期与 Health 保存能自由组合；平台事实未验证前不是有效 Owner 问题 |
| D13a 真机证据 | 验证 Workout 是否必需、能否运行但不保存、`CLBackgroundActivitySession` 替代路径、AOD/五小时功耗、权限拒绝、被其它 Workout 抢占与恢复 |
| 即刻隐私地板 | 不得因后台技术需要静默写入 Apple Health；拒绝写权限不得破坏地图、计分和逐杆核心能力 |
| D13b 预登记 | 真机证明平台组合后，若“v1 提供显式可选保存”与“v1 完全不提供保存”仍都真实可行，必须回 Owner 二选一，不得被工程默认吃掉 |
| 决定理由 | 先证实平台约束，再决定产品范围；自动保存不是合法的技术必然 |
| 影响 | HealthKit 授权、开局设置、结束流程、隐私说明和恢复行为 |
| 下一项 | T031 真机 Spike；当前不提问 |

## 5. 证据路由与条件重开队列

这些事项不会自动升级为 Owner 问题。证据能唯一推出答案的由工程落规格；只有明确标为“条件 Owner 重开”的项在触发条件成立时回到单题队列。

| ID | 状态 | 证据/原型任务 | 证据后的路由 | 当前约束 |
|---|---|---|---|---|
| E01 | `EVIDENCE NEEDED / ENGINEERING ROUTE` | 42/46mm 工具入口原型；新用户三洞内找到 Green View、计分和球局工具 | 数据直接决定；只有失败触发 L02/L03 级 IA 重开时才回 Owner | 单一明确入口 + 浅推入，不复活兄弟页 |
| E02 | `EVIDENCE NEEDED / ENGINEERING ROUTE` | 表冠焦点借还、误转、湿手/手套真机测试 | 数据直接决定 | 当前倾向根页不占表冠 |
| E03 | `EVIDENCE NEEDED / ENGINEERING ROUTE` | Map Detail K1 缩放轴 / K2 目标停点轴同场对照 | 数据直接决定；平手按 S70 忠实度和低误转裁决 | 两臂都保留，不预先删 K2 |
| E04 | `ENABLED BY D02 / EVIDENCE NEEDED` | 41/46mm S70 双层根页、Driver Arc/AI 线隔离、低置信/陈旧/模式降级原型 | 数据直接决定；不再回 Owner 选择产品方向 | 无真实横向散布/新鲜度契约前完整退化为 B；禁止成功率和未校准平均杆数；不得把平台翻译做成像素临摹 |
| E05 | `EVIDENCE NEEDED / ENGINEERING ROUTE` | AOD 更新、烧屏/功耗、抬腕恢复和中断矩阵 | 数据直接决定 | AOD 只投影事实层；Big Numbers 为用户选择后持久模式 |
| E06 | `EVIDENCE NEEDED / ENGINEERING ROUTE` | 高频 API 机型线、批量延迟、按设备误报/漏报、五小时续航 | 数据直接决定 D05 的设备分批名单 | 高频能力设备首批，旧设备独立过门后加入 |
| E07 | `EVIDENCE NEEDED / CONDITIONAL OWNER REOPEN` | tee anchors、误换/漏换、恢复成本和长期遥测 | 证据不过线不提问；显著过线后必须重开 D06，由 Owner 决定是否改出厂默认 | v1 默认保持确认式，工程不得自行升级 |
| E08 | `CLOSED BY D04-B / IMPLEMENTATION ROUTE` | Watch 搜索、选场、Tee、包下载/安装、缓存与无网恢复 | D04-B 已锁定产品范围；直接进入 T033、T042、T056、T076 的证据、契约、规格与原型工作，不再作为 Owner 问题 | iPhone 可协助准备/同步，但不得成为腕上冷启动前置；A 只可作为内部中间里程碑 |
| E09 | `ALREADY DECIDED / FUTURE OWNER REOPEN` | 仅为未来重开准备来源、精度、TTL、离线包和续航证据 | v1 不做风/空气密度和推杆级等高线；未来加回必须先有证据，再申请 Owner 重开 | 果岭宏观坡向可保留；07-15 重审中带回的动态风属于超出已批范围 |
| E10 | `EVIDENCE NEEDED / ENGINEERING ROUTE` | 雨水、湿屏、Water Lock、厚手套与大触点矩阵 | 数据直接决定；只有结果要求新增全局产品模式且存在真实取舍时才升级 | 不凭偏好增加 app-level wet lock |

## 6. 不需要用户逐项拍板的技术与验证事项

以下由 Codex/Fable、工程约束和实测证据决定；只有当结果会改变产品承诺时，才升级为新的 Owner 决策。

| 类别 | 事项 |
|---|---|
| 数据模型 | shot ledger、candidate/confirmed/rejected/superseded、append-only correction、eventId 幂等 |
| 交互仲裁 | 单一交易浮层槽位、用户任务租约、持久待处理队列、AOD 事实投影 |
| 位置引擎 | tee anchors 误差、GPS freshness、洞候选几何阈值、heading 质量门 |
| Motion | 采样率、时间窗、冲击/随挥规则、批量延迟；原始/压缩窗口必须服从 D12a 隐私底线，不能由算法便利决定 |
| 续航 | 五小时曲线、最低剩余电量、降级触发点 |
| 同步 | WatchConnectivity + 直连双通道、outbox、serverAccepted、死信和重试 |
| 动态数据 | v1 PlaysLike 只用高差；风/空气密度属于 E09 Owner 重开前的研究证据，不进入现行产品 contract |
| 场地数据 | full-round package 体积、surface 多边形体积、startLie 分类归属 |
| 可靠性 | 来电、通知、AOD、强杀、重启、暂停、Workout 被抢占、长期离线恢复 |
| 发布门 | 先量基线再定数字；低频高损害错误使用注入测试和长期遥测 |

## 7. 决策完成后的任务 Backlog

### 阶段 G0 — 决策与权威锁定

| Task | 任务 | 依赖 | 可并行 | 完成门 |
|---|---|---|---|---|
| T000 | 建立并维护本决策账本 | 无 | 否 | 本文件存在，唯一 `CURRENT` 和 `NEXT` 明确 |
| T001 | 完成常设 Owner 队列 D02、D04，并维护条件重开注册表 | T000 | 否 | 每次只问一项；直接决定项和证据路由不再冒充 Owner 题 |
| T002 | 审计总重审中的用户门、静默重开与范围走私，并与本账本保持一致 | T000 | 可与 T001 并行 | 数量、编号、权威来源、L18/L19、E07–E09 与当前 `NEXT` 不互相矛盾 |
| T003 | 冻结 `owner-locked-semantics` | T001 | 否 | 用户锁定语义逐条可追溯，模型不可静默推翻 |
| T004 | 建立 UNKNOWN 注册表并给每项分配 evidence / prototype / implementation owner | T001 | 可与 T003 并行 | 正文中不再藏无归属的“以后再看” |

### 阶段 G1 — Canonical 文档与验证基线

| Task | 任务 | 依赖 | 可并行 | 完成门 |
|---|---|---|---|---|
| T010 | 建立 `docs/watch/` 骨架和 README 权威地图 | T001 | 否 | research/product/interaction/architecture/contracts/decisions/validation/plans/archive 边界明确 |
| T011 | 第一份 decision 写 `owner-locked-semantics.md` | T003, T010 | 否 | Owner 语义成为首要权威 |
| T012 | 写旧 Watch 规范 supersession ADR；按 D03 更新旧文档页头 | D03, T010 | 与 T013–T016 并行 | 历史证据保留，但不再与 canonical 并列 |
| T013 | 写 S70 facts、watchOS capabilities、field evidence | T004, T010 | 可并行 | 每条标 `CONFIRMED / DERIVED / UNKNOWN` 和来源 |
| T014 | 写 north star、capability tree、task frequency、full-round journey、IA | D01, D02, D04, T011 | 可并行 | 全体验分支都有入口、状态、降级和责任面 |
| T015 | 先建立 validation 基线：hard invariants、pilot metrics、baseline-dependent gates | T004, T010 | 可并行 | 验证不是最后补写；每项能力从一开始有证据出口 |
| T016 | 建 `evidence-manifest.md` | T010 | 可并行 | 视频、设备、OS、固件、课程、日志和脚本可追溯；`.mockups/watch-shot-tracking.html` 明确入册为历史未核原型或归档，不再游离 |
| T017 | 建 `traceability-matrix.md` | T011, T014, T015 | 否 | 锁定语义 → 产品行为 → contract → validation → plan 全链可追踪 |
| T018 | 将联合重审标为 review input，避免继续膨胀成巨型现行规格 | T012, T017 | 否 | 每项现行行为都有唯一 canonical owner |

### 阶段 G2 — Spike 基础设施与核心契约草案

本阶段可以准备实验代码，但仍不接入正式产品路径。

| Task | 任务 | 依赖 | 可并行 | 完成门 |
|---|---|---|---|---|
| T020 | 核对并准备 HealthKit/Motion entitlements、Info.plist 权限文案、签名与 TestFlight profile | D12a, D13, T013 | 可并行 | 真机 Spike 有合法、可复现的权限与签名基础；不暗示自动写入 Health |
| T021 | 冻结真机设备/佩戴腕/左右手/OS 测试矩阵 | T013, T015 | 可并行 | 不用单一机型结果外推全部 Watch |
| T022 | 建 Spike 日志、功耗、视频、结果模板 | T015, T016 | 可并行 | 原始证据与结论同时留存 |
| T023 | 建 Motion/Location 统一时间基准与传感器标注工具 | T021, T022 | 可并行 | 准确率、延迟和击球时 GPS 可被正确对齐 |
| T024 | 写 Spike 阶段运动窗口的同意、保留、脱敏和删除规则 | D12a, T016 | 可并行 | 研究数据不先于隐私政策偷跑；默认完全本地 |
| T025 | 起草 canonical event envelope 与核心 domain 事件 | T011, T017 | 可并行 | 至少覆盖 shot/score/hole/correction、scoreDebt、ResolutionEpisode、provisional assignment、active/editing hole、resolution transaction |

### 阶段 G3 — 并行平台与数据 Spike

以下四组并行；结果必须回写 research、evidence manifest 和 validation，不能只留在聊天或实验分支。

| Task | Spike 组 | 主要输出 | 影响决策 |
|---|---|---|---|
| T030 | Sensor：高频 Motion、100Hz、时间轴、候选延迟、标注窗口 | 按设备/腕位/杆型的可用性和延迟分布；D12b 最小窗口必要性证据 | D05, D12b, E06 |
| T031 | Lifecycle：Workout、后台 GPS、抢占恢复、AOD、真实五小时续航/热量 | 生命周期状态、耗电曲线、明确降级 | D13, E05, E06 |
| T032 | Interaction：表冠焦点、浮层借还、haptic、湿屏/手套、抬腕恢复 | 误转、成功率、焦点恢复和触觉预算 | E01–E05, E10 |
| T033 | Course data：整轮包、tee anchors、surfaces、Green mesh、heading；风/空气仅作 E09 重开证据研究 | 包体、传输、精度、缓存和数据质量；不得把动态风写入 v1 contract | D04, E07–E09 |
| T034 | S70 真机侧拍与同场任务对照 | 抬腕读距、导航、计分、Club Prompt、Finish 的真实基线 | E01–E05, E09 |

阶段内依赖：

- 五小时续航必须使用真实 Motion + GPS + Workout 管线；
- AutoShot 准确率必须使用统一时间基准和标注工具；
- Map 表冠原型依赖焦点 Spike；
- PinPointer 规格依赖 heading 结果；
- startLie/fairway 推断依赖 surface 体积与质量；
- 自动换洞依赖 tee anchor 覆盖报告。

### 阶段 G4 — 机器契约与迁移冻结

| Task | 任务 | 依赖 | 可并行 | 完成门 |
|---|---|---|---|---|
| T040 | 冻结单一 canonical domain event；若保留 `watch-input-event-v2`，只作为 transport adapter | T025, T030–T033 | 否 | WatchInputEvent / LiveRoundEvent 不再形成双重事实模型 |
| T041 | 定义 ledger、reducer、checkpoint、resolutionTransactionId 与原子/部分失败语义 | T040 | 可并行 | 任意中断可重放，三合一确认不会写一半 |
| T042 | 冻结 full-round package、tee anchors、surface dependency、pinSet、target、current-shot caddie target/dispersion/freshness/mode gating；环境字段仅留未来扩展位 | T033, T040 | 可并行 | v1 不消费风/空气；真实球局、地图、换洞、Green View、startLie 与球童层使用同一包契约；`targetWindow` 不得冒充历史散布，未校准杆数不得进入用户 UI |
| T043 | 定义三层 ACK、路由租约、outbox、serverAccepted、dead-letter 和用户可见恢复 | T040 | 可并行 | 离线与双通道同步不丢不重 |
| T044 | 设计 v1→v2 持久球局迁移与混合客户端降级 | T041–T043 | 可并行 | 旧球局和旧客户端不会被静默破坏 |
| T045 | 定义 client/server clock、serverSequence、多端 correction 排序和冲突规则 | T041, T043 | 可并行 | 多端修改结果确定、可审计 |
| T046 | 生成 JSON Schema、Swift Codable、Pydantic、golden fixtures 和正反 contract tests | T040–T045 | 否 | Watch/iPhone/server/reducer 重放结果一致 |
| T047 | 审计全部消费者 | T046 | 可并行 | 统计、球杆档案、AI 样本、shot map、Web/iOS 均有迁移责任人 |
| T048 | 从契约阶段建设故障注入、事件 fixtures、遥测和隐私删除测试 | T041–T047 | 可并行 | validation 资产与实现同步生长 |

### 阶段 G5 — 共享架构与交互规格

共享架构先于具体页面；交互规格不得绕开 contract 自创状态。

| Task | 任务 | 依赖 | 可并行 | 完成门 |
|---|---|---|---|---|
| T050 | 写 event ledger/reducer/checkpoint、RoundCoordinator、PresentationCoordinator | T041, T046 | 否 | 事实状态、工作流状态和呈现状态边界明确 |
| T051 | 写 Workout/Sensor coordinator、location-hole engine、package cache、sync lifecycle、statistics projection | T042–T047, T050 | 部分并行 | 每个组件职责、接口、降级和测试归属明确 |
| T052 | `navigation-focus-resume.md` | T032, T050 | 否 | 焦点、恢复、单浮层和待处理队列统一 |
| T053 | `scoring-and-hole-transition.md` | D06, T041, T050, T052 | 与 T054 起草并行 | 快速/手动确认、provisional、Cancel、历史编辑、单 episode 上限无歧义 |
| T054 | `shot-capture-and-recovery.md` | D05, T030, T041, T050 | 与 T053 起草并行 | AutoShot/手动杆、Tee last-wins、10 码、“打厚了”、误检恢复完整 |
| T055 | `club-prompt.md` | T052, T054 | 否 | 只补杆号、点按完备、表冠仅增强、超时/中断不提交 |
| T056 | pre-round setup 与 full-round package install/cache 规格 | D04, T042, T051 | 可并行 | 每一步标明 Watch/iPhone/网络归属与降级 |
| T057 | Hole Root / Big Numbers / Scorecard 规格 | D01, D02, D07–D10, T052, T053 | 可并行 | 根页事实层、条件建议层和编辑边界明确；成绩环覆盖 S70 八档颜色、已打/当前/未来洞、9/18 洞与 shotgun 语义；Big Numbers 与 Caddie 互斥 |
| T058 | Map / hazards / PlaysLike 规格 | D02, L18, T032–T034, T042, T052 | 可并行 | 根页地图、Map Detail 明确；v1 PlaysLike 仅高差，风/空气和推杆级等高线明确缺席 |
| T059 | Green View / pinSet / PinPointer 规格 | T033, T042, T058 | 可并行 | 拖旗、heading 门和 Green 数据降级明确 |
| T060 | Pause / Finish / post-round / correction 规格 | D10, T041, T043, T053 | 可并行 | Finish preflight、finishedPendingSync、忘记结束和统计重算完整 |
| T061 | AOD / wet / glove / accessibility 规格 | T031, T032, T052 | 可并行 | AOD 事实投影、低电、湿手、VoiceOver、颜色非唯一编码完整 |
| T062 | Caddie / AI / Tournament Mode 规格 | D02, D11, L18, L19, T042, T058–T061 | 可并行 | 根页仅当前一杆、完整页才有组合；无成功率/假平均杆数；推荐与 actual club 分离；Big Numbers/Tournament/Manual/离线/陈旧/低置信缺席明确；若首批仅 Tee 或 companion 可用，必须在 T092 显式审批，不得成为隐含默认 |
| T063 | Privacy / Health / telemetry 产品政策规格 | D12a, D12b, D13, T024, T043 | 可并行 | 默认本地、可撤回同意、Health 不静默写入、保留和删除均无歧义 |
| T064 | 将 26 个中断冲突场景映射到 contract、reducer 和规格 | T052–T063 | 否 | 每个场景只有一个结果，无覆盖和隐式提交 |

### 阶段 G6 — 风险原型与验证

只做会改变设计的原型，不用原型代替 contract。

| Task | 任务 | 依赖 | 可并行 | 完成门 |
|---|---|---|---|---|
| T070 | 42/46mm 单根页工具入口发现性原型 | T032, T052, T057 | 与 T071–T075 并行 | 可测 E01；失败条件可触发三页重开 |
| T071 | 根页表冠与 Map K1/K2 双臂原型 | T032, T052, T058 | 可并行 | 可测 E02/E03，不预设结论 |
| T072 | score/hole/provisional 杆三合一原子确认原型 | T041, T053 | 可并行 | 正常、中断、强杀和部分失败结果一致 |
| T073 | Club Prompt 点按/表冠/排队原型 | T032, T052, T055 | 可并行 | 不覆盖成绩确认，跳过不删杆 |
| T074 | AOD / Big Numbers / 抬腕 / 来电恢复原型 | T031, T061, T064 | 可并行 | 可测 E05，任何草稿不被隐式提交 |
| T075 | 最小表径、湿手、手套和 app-level wet lock 对照 | T032, T061 | 可并行 | 可测 E10 |
| T076 | 真实整轮包进入统一 Watch 产品路径 | T042, T056–T060 | 可并行 | 不再只有假练习局；离线开局到结束成立 |
| T077 | 全轮场景矩阵、崩溃恢复、故障注入和 hard invariant 自动测试设计 | T048, T064, T070–T076 | 否 | 用户锁定流程和低频高损害场景全覆盖 |
| T078 | C′ 条件单杆球童层 41/46mm 双表径原型 | D02, T032, T042, T057, T058, T062 | 可并行 | 可测 E04；同时覆盖事实零状态、推荐 chip、当前一杆线、真实纵深散布带、Driver Arc、低置信/陈旧/Big Numbers/Tournament 降级；不得使用固定椭圆或假 60% 落点；Tee-only/companion-only 若作为首批限制必须形成可见 decision record |
| T079 | 汇总每个原型的 decision record 与证据包 | T070–T078 | 否 | 失败假设回写规格，证据可复查 |

### 阶段 G7 — 证据路由与条件 Owner 重开

| Task | 任务 | 依赖 | 可并行 | 完成门 |
|---|---|---|---|---|
| T080 | 按 D12b、D13b 与 E01–E10 逐项审计状态和证据路由；只把满足条件的重开项交 Owner | T079 | 否 | 工程题由证据定；D12b、E07、D13b、E09 仅在登记条件成立时一次问一项，回答先写回；E08 已由 D04-B 关闭为实施路由，不再回 Owner |
| T081 | 根据证据结果与实际触发的条件重开修改 canonical 规格并重跑 traceability 审计 | T080 | 否 | 决策、contract、验证和 UI 无漂移；未触发项不制造用户门 |

### 阶段 G8 — 实施就绪与用户规格审批

| Task | 任务 | 依赖 | 可并行 | 完成门 |
|---|---|---|---|---|
| T090 | Canonical 规格自审 | T081 | 否 | 无 TBD、矛盾、双重权威、未分配责任或失效链接 |
| T091 | 实施就绪审查 | T090 | 可并行准备 | 隐私/Health/App Store/比赛规则、auth/token、feature flag、设备 allowlist、远程 kill switch、诊断导出、支持 runbook、包校验和/原子安装/磁盘淘汰、日志脱敏全部有负责人 |
| T092 | 用户逐节审阅并批准书面规格 | T090, T091 | 否 | 用户明确批准 canonical spec |

### 阶段 G9 — 写实施计划，不直接开工

| Task | 任务 | 依赖 | 可并行 | 完成门 |
|---|---|---|---|---|
| T100 | 调用 `writing-plans`，拆成 P0–P11 计划树 | T092 | 否 | 不再有一份巨型 Watch 计划；每个 Track 有文件级步骤、测试、依赖、回滚和验收门 |
| T101 | 实施前重做代码复用/修改后复用/淘汰映射 | T100 | 可并行 | 每一能力对应真实源码和迁移路径 |
| T102 | 获得用户实施授权后才进入产品代码 | T100, T101 | 否 | 设计阶段不偷跑正式实现 |

## 8. 主路径与并行关系

```text
D02 ✓ → D04 ✓（常设 Owner 队列完成；其余事项已决定/工程可决/证据先行）
   ↓
权威锁定 + docs/watch + validation/evidence 基线
   ↓
Spike 基础设施 + 核心 event contract 草案
   ↓                         ↘
并行平台/数据 Spike           AutoShot 算法研究
   ↓                         （不接生产 UI）
机器契约 + migration 冻结  ←─┘
   ↓
共享架构 → 交互规格
   ↓
风险原型 + 全轮/崩溃/故障注入验证
   ↓
D12b、D13b 与 E01–E10 状态/证据路由（E08 已转实施）；仅触发条件重开时回 Owner
   ↓
实施就绪审查 + canonical spec 用户批准
   ↓
writing-plans → 复用/淘汰映射
   ↓
获得授权后才实施代码
```

实施计划必须拆为以下依赖树：

```text
P0 Contracts + migration
 ├─ P1 Ledger / reducer / checkpoint
 ├─ P2 Server ingest / ACK / dead-letter / consumers
 └─ P3 Full-round package / production round entry

P1 + P3
 └─ P4 RoundCoordinator / single-root / PresentationCoordinator
      ├─ P5 Scoring + hole transition
      ├─ P6 Manual shot + Club Prompt + recovery
      └─ P7 Map + Green + PinPointer + environment

P1
 └─ P8 Workout / background / AOD / interruption
      └─ P9 AutoShot Beta

P1 + P2 + P5 + P6
 └─ P10 Finish / post-round / correction / statistics

全部计划
 └─ P11 Telemetry / TestFlight rollout / field validation
```

第一个生产里程碑不是 AutoShot，而是最小可靠闭环：

```text
真实球场整轮包
→ Watch 开局
→ 手动成绩与手动一杆
→ 强杀恢复
→ 离线结束
→ 手机/服务器同步
→ iOS 深度修改（Web 维持只读复盘）
→ 统计重算
```

AutoShot 的 Spike 和算法研究从 G3 并行开始；只有在 contract、ledger、手动恢复和 PresentationCoordinator 成立后，才作为新的 producer 接入正式产品。

最容易遗漏、必须在计划里点名的横切任务：

- Watch entitlement、签名 profile 和权限文案；
- Motion/Location 统一时间基准；
- 原始运动窗口 opt-in、保留、脱敏和删除；
- WatchInputEvent / LiveRoundEvent 双映射收敛；
- v1 持久球局迁移与混合客户端；
- 多事件原子提交和部分失败恢复；
- 多端 correction 的确定性冲突规则；
- dead-letter 的用户可见恢复入口；
- 统计、球杆档案、AI 样本、shot map 消费者审计；
- 整轮包 checksum、版本、原子安装、磁盘预算和半包恢复；
- 设备、佩戴腕、左右手与 capability gating；
- Beta feature flags、远程停用、诊断遥测和支持 runbook；
- 位置、HealthKit 和传感器日志脱敏；
- VoiceOver、颜色非唯一编码、单位/时区和左右冠方向；
- 真机证据的设备、OS、固件、课程和测试脚本可追溯性。

## 9. 决策变更记录

只追加，不覆盖历史。

| 时间 | ID | 变更 | 理由/证据 | 下一项 |
|---|---|---|---|---|
| 2026-07-15 | TRACKER | 建立决策账本；设 D01 为唯一 `CURRENT` | 用户要求逐项讨论、先写回再进入下一项 | D01 |
| 2026-07-15 | D05 | 将既有“AutoShot 分批 Beta、手动补杆永久保留”迁入账本，状态为 `DECIDED` | 用户要求不得无限后置 + Codex × Fable 终审 | 不重复询问 |
| 2026-07-15 | D06 | 将用户已定义的确认式换洞流程迁入账本，状态为 `DECIDED` | 用户逐条锁定 provisional 首杆、成绩确认与 Cancel 语义 | 不重复询问 |
| 2026-07-15 | D01-EVIDENCE-ERROR | 曾错误写入“S70 没有 18 段边缘成绩环”，并据此推荐移除 | 过度依赖洞 1/未记分的手册示意图与二手文字，未逐张检查官方产品图库和球场实拍 | 已撤销 |
| 2026-07-15 | D01-EVIDENCE-CORRECTION | 官方产品图与多源实拍明确显示 1–18 洞刻度及逐洞彩色分段弧；D01 推荐暂改为保留 | Garmin 官方 CDN、Plugged In Golf 实拍、PlayBetter 实拍、多个独立视频封面 | D01 继续 `CURRENT`，待证据审计收口 |
| 2026-07-15 | D01 | `DECIDED / A / KEEP`；D02 成为唯一 `CURRENT` | 用户明确质疑“不存在”的错误结论；Garmin 官方 `Score History` 原文、42/47 mm 官方产品图、球场实拍与连续视频一致确证 | D02 |
| 2026-07-16 | D02-EVIDENCE-CORRECTION | 保留旧联合建议 B 的历史；新增 C′“条件单杆球童层”，联合建议由 B 改为 C′，D02 仍为 `CURRENT`、未替用户决定 | Garmin 官方产品图在 Hole View 直接显示推荐杆/瞄准线/散布；连续实拍证明根页轻量推荐与完整 Caddie 两层；纯 Fable 独立复核同意 C′，并要求数据契约完成前退化为 B | D02 待 Owner 决定 |
| 2026-07-16 | QUEUE-AUDIT | Codex 三路审计 + 纯 `claude-fable-5 / max / 无 fallback` 终审重分类完整 D/E 队列；常设 Owner 队列收敛为 D02 → D04 | 旧队列混入假三选一、既有决定、工程阈值和证据题；Fable 会话 `0f900a45-cf8a-41c4-8d3c-8874d6b60d74` 纯度与完成度通过 | D02 仍唯一 `CURRENT` |
| 2026-07-16 | D03 | `DECIDED / ENGINEERING GOVERNANCE / A`；旧稿保留并 supersede，不再让 Owner 三选一 | 旧模型稿无 Owner 批准记录，且与 L01–L03、L07 冲突；只有单一权威方案合法 | 不重复询问 |
| 2026-07-16 | D03-EXEC-PARTIAL | 给 06-22、07-10 两份旧 Watch 规格、旧总 Spec 和 07-15 review input 加权威更正页头；历史正文完整保留 | 防止旧“唯一真源/两项用户门/操控宪法”继续覆盖当前账本；supersession ADR 与 canonical `docs/watch/` 仍按 T010–T012 完成 | D02 仍唯一 `CURRENT` |
| 2026-07-16 | D04-REFRAME | 改为 `OWNER_REOPEN`；删除“全程依赖 iPhone”旧 C；联合产品建议改为保持完整腕上冷启动独立范围 | 07-02/07-08 已批准 Watch 搜索/选场/Tee/下载/开局；收窄必须透明授权，不能以工程复用冒充产品最优 | D02 决定后进入 D04 |
| 2026-07-16 | D05-HISTORY | 补记 D05-A 取代 07-02 D4“实时识别 v1 先不做”；轨迹确认保留为兜底 | 用户后续明确要求 AutoShot 不得因困难无限后置 | 不重复询问 |
| 2026-07-16 | D07 | `DECIDED / V1 GROSS ONLY / NET-STABLEFORD LATER` | 06-09/10 用户逐屏确认规格已明确该范围；Fable 终审只要求显式记入 decision | 不重复询问 |
| 2026-07-16 | D08–D10 | D08 独立设置、D09 wearer-only/多人腕上卡出当前范围、D10 A′（iOS 深编辑、Web 只读）直接落盘 | L04/L11/L15、多人隔离 contract 与 07-07 Owner 定稿已经唯一推出答案 | 不重复询问 |
| 2026-07-16 | D11 | `DECIDED / PERSONAL LEISURE-TRAINING / NO COMPLIANCE CLAIM` | Master Product Spec 排除 tournament product surface；当前无规则/法务矩阵 | 未来正式赛事轨道须主动重开 |
| 2026-07-16 | D12 | 拆为隐私底线 `DECIDED` + 数据捐赠必要性 `EVIDENCE NEEDED`；删除默认上传方案 | 敏感运动数据默认不上传、独立 opt-in 和不持久化整轮原始流已是硬边界 | 证据成立才可能回 Owner |
| 2026-07-16 | D13 | 整体改为 `EVIDENCE NEEDED`；预登记平台证据后可能出现的 Health 保存二选一 | Workout 后台与 Health 保存并非同一问题，当前组合未真机证明 | T031；不当前提问 |
| 2026-07-16 | E07/E08/E09 | E07 过线必须重开 D06；E08 与 D04 合并；E09 纠正为 v1 已明确无风/空气密度和推杆级等高线 | 防止证据流程把工程题上交，也防止用“以后验证”静默带回 Owner 已否决范围 | 条件触发时一次只问一项 |
| 2026-07-16 | OWNER-SCOPE-CORRECTION | 新增 L18/L19；标记 07-15 重审中动态风/空气密度内容超出 07-02 Owner 已批范围 | 07-02 明确“成功率、风、不做推杆级等高线”；后续重审曾无变更记录地带回 | 未经 Owner 重开不得实施 |
| 2026-07-16 | REVIEW-RETRY-POLICY | 将 Fable/GPT 调用链的瞬时故障统一为自动持续重试：`503` 若根因是上游 `429` 同样处理；保留模型、effort、输入和无 fallback 约束 | Owner 明确要求遇到 cooldown/429/503 时自动定时恢复，直到成功 | 常设执行规则，不占 Owner 决策队列 |
| 2026-07-16 | D09b-RATIONALE-CORRECTION | 保留“腕上多人卡不在当前范围”的结论，但删除“已有手机/Web admin 代录通道”论据；后端 admin 可写不等于已有用户产品，也不授权 owner 浏览成员数据 | 2026-06-13 Owner 已锁定每人只看自己、owner 管理页不看成员分析；D09b 应只由当前产品边界与 S70 Watch 证据支撑 | 不重复询问 |
| 2026-07-16 | CONDITIONAL-ROUTE-CORRECTION | 将 D12b 补回 T080 与主路径的条件 Owner 回流注册表 | D12 正文已写“证据成立后才问研究数据捐赠”，但 G7 摘要此前漏列，存在未来被静默吞掉风险 | 当前不提问 |
| 2026-07-16 | REPOSITORY-WIDE-OWNER-GATE-AUDIT | 扩展审计到 Watch 外的家庭身份、Web/iOS、后端、旧规格与当前实现；未新增常设 Owner 问题，登记确定性实现漂移和 authority guard 工作 | 81 份 Markdown 三路扫描 + Watch/Web/backend 代码核验；详见全仓 Owner-gate 审计 | D02 仍唯一 `CURRENT` |
| 2026-07-16 | L20/L21 | 补记可恢复多球局生命周期与全产品用户可见单位规则；L20 来源经 Fable 修正为 L16 + 事件归属唯一性 + 07-14 C3，自动挂起/询问留给 T092；L21 由用户原话直接锁定 | L16、D09a/L04；2026-06-11 W4 用户确认的“全部显示码” | 不重复询问 |
| 2026-07-16 | D04-EVIDENCE-AND-PLACEHOLDER | 补入 W4“尤其是手表”的用户级开局来源；明确当前 18×Par4 空白练习局是测试脚手架，不作为 A/B 的生产兜底 | 纯 Fable 全仓终审指出 D04 选项若不点名占位模式，未来会制造第三题回流 | D02 决定后才问 D04 |
| 2026-07-16 | PURE-FABLE-REPOSITORY-AUDIT | 纯 `claude-fable-5 / max / 无 fallback` 完成全仓 Owner-gate 终审；裁决 `MODIFY`，但接受“无新增常设 Owner 门”，新增两项实现漂移并修正文档 guard/L20/D04 文本 | 会话 `75bd1b53-3fee-4696-8dba-5cd7ff5ff4c6`；`Read ×62 / Grep ×6`；133 条 assistant 记录全部为 Fable | D02 仍唯一 `CURRENT` |
| 2026-07-17 | D02 | `DECIDED / S70 BEHAVIORAL PARITY / C′`；不再让 Owner 在抽象 A/B/C′ 中反复选择，直接锁定 S70“永久事实层 + 条件当前杆建议层 + 点击完整球童”的可观察行为模型；E04 正式启用 | Owner 提出“不能直接对标 S70 么”，在明确行为对标而非像素/资产/未知算法复制的边界后回答“好” | D04 成为唯一 `CURRENT` |
| 2026-07-17 | D04 | `DECIDED / B / WATCH-INDEPENDENT COLD START`；保持 Watch 搜索球场、选择洞组/Tee、下载真实球场包、独立开局与脱离 iPhone 完整打轮的既有范围。A 仅可作为内部中间里程碑，18×Par 4 空白练习局仅为测试脚手架；E08 同步关闭为工程实施路由 | Owner 接受“直接对标 S70”原则，并在被单独询问是否按 B 落账后确认“好” | 常设 Owner 队列完成；进入 canonical 文档、Spike 与证据路由 |

## 10. 核心证据入口

- [Codex × Fable Watch 全体验重审](2026-07-15-codex-fable-watch-full-experience-reassessment.md)
- [纯 Fable 无 fallback 最终对抗审查](2026-07-15-claude-fable-watch-full-experience-final-adversarial-review.md)
- [S70 已核验证据包](2026-07-15-s70-verified-evidence-pack.md)
- [S70 Virtual Caddie / Driver Arc 专项证据](2026-07-16-s70-virtual-caddie-driver-arc-evidence.md)
- [纯 Fable D02 独立对抗审查](2026-07-16-claude-fable-d02-virtual-caddie-adversarial-review.md)
- [Codex D02 当前实现复用审计](2026-07-16-codex-d02-current-implementation-reuse-audit.md)
- [Codex Owner 决策队列重分类](2026-07-16-codex-watch-owner-decision-queue-reclassification.md)
- [纯 Fable Owner 决策队列终审](2026-07-16-claude-fable-watch-owner-decision-queue-final-adversarial-review.md)
- [全仓 Owner 决策门、权威与实现漂移审计](2026-07-16-repository-wide-owner-gate-authority-and-drift-audit.md)
- [纯 Fable 全仓 Owner-gate 最终对抗审查](2026-07-16-claude-fable-repository-wide-owner-gate-final-adversarial-review.md)
- [Fable S70 Round 1](2026-07-15-claude-fable-s70-design-synthesis-round1.md)
- [Codex 对 Round 1 的对抗审查](2026-07-15-codex-adversarial-attack-on-fable-s70-round1.md)
- [Fable S70 Round 2](2026-07-15-claude-fable-s70-design-synthesis-round2.md)
