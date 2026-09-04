# Watch Owner 决策队列重分类（Codex 审计稿）

> 日期：2026-07-16 UTC  
> 性质：只读产品治理审计；不授权产品代码实施  
> 当前唯一 Owner 问题：D02  
> 目的：只把真正改变产品承诺、且无法由既有决定、证据或工程约束推出的问题交给 Owner；删除假三选一、重复项和技术阈值问题
>
> **2026-07-16 后续全仓审计更正：**常设队列结论不变。D09b“腕上多人卡不在当前范围”不再以手机/Web admin 代录作为支撑；2026-06-13 Owner 已锁定每人只看自己、owner 管理页不看成员分析。完整更正与全仓实现漂移见[全仓 Owner-gate 审计](2026-07-16-repository-wide-owner-gate-authority-and-drift-audit.md)。
>
> **2026-07-17 QUEUE PROGRESSION：**D02 已由 Owner 确认为直接对标 S70 的双层行为模型；当前唯一 Owner 问题为 D04。

## 1. 审计原则

1. 先判断产品设计是否合理，再看已有工程能否复用，不能因当前实现省事而偷偷降低产品目标。
2. 既有 Owner 决定优先；review 只能申请显式重开，不能把既有决定重新包装成绿地三选一。
3. 若一个选项违反已锁定 invariant、隐私底线或单一权威原则，它不是有效 Owner 选项。
4. 技术阈值、设备门槛、GPS/Motion 参数、表径降级和交互入口先由证据决定。
5. 任意时刻只向用户提出一个问题；用户回答后先写回账本，再进入下一题。

## 2. D03–D13 重分类总表

| ID | Codex 分类 | 是否继续问 Owner | 裁决摘要 |
|---|---|---:|---|
| D03 | `ENGINEERING_DECIDABLE` | 否 | 旧矛盾文档保留为历史输入并显式 supersede；并列生效与删除都不成立 |
| D04 | `OWNER_REQUIRED / REOPEN` | 是 | 不是新三选一，而是是否批准收窄此前已批准的 Watch 独立开局范围 |
| D05 | `ALREADY DECIDED` | 否 | AutoShot 分批 Beta，手动补杆永久保留 |
| D06 | `ALREADY DECIDED` | 否 | 确认式换洞、provisional 下一洞首杆、Cancel 回上一洞 |
| D07 | `ALREADY DECIDED` | 否 | 已确认规格明确 v1 默认比杆；Stableford/净杆为后续制式 |
| D08 | `DUPLICATE / DERIVED` | 否 | 记分链与逐杆链独立；关闭记分不能静默改变逐杆开关 |
| D09 | `DERIVED` | 否 | Watch 传感器与逐杆事件只归已认证佩戴者；代记同组总分若未来要做，应另立功能决定 |
| D10 | `ALREADY DECIDED / DERIVED` | 否 | Watch 保留继续打球所需纠错；全量逐杆地图深编辑归 iOS，Web 维持只读 |
| D11 | `ALREADY DECIDED` | 否 | 现有产品边界是个人休闲/训练产品，本 build 明确排除 tournament product surface；不得宣称正式比赛合规 |
| D12 | `ALREADY DECIDED + EVIDENCE FIRST` | 否 | 隐私底线已锁定为默认不上传、仅独立 opt-in 最小窗口；是否运营研究数据捐赠计划须先证明必要性 |
| D13a | `EVIDENCE FIRST` | 否 | 后台 Workout 是否必需、功耗和抢占恢复由真机验证决定 |
| D13b | `EVIDENCE FIRST` | 否（当前） | 先证明 Workout 与 Health 保存的真实平台组合；证据后若仍存在产品范围分叉，再申请 Owner 决策 |

## 3. 不再询问的事项

### D03 — 文档权威治理

裁决：`DECIDED / ENGINEERING GOVERNANCE / A`。

- 06-22 文档自称设计阶段产物；Round 1/2 自称 research/concept，本来就不是现行规范。
- 07-10 两份文档虽自称“定稿/操控宪法”，但其五页结构已与 L01–L03 冲突，无法继续并列生效。
- 保留全部历史文件，在页头标 `Historical Input / Superseded`；写 supersession ADR；把仍有效的 Owner 语义抽入新的 canonical 文档。
- 执行降级前必须先保存 D04 等旧文档中的 Owner 决定，不能借治理动作静默删范围。

关键证据：

- `docs/superpowers/specs/2026-06-22-apple-watch-golf-design.md:3-5`
- `docs/superpowers/specs/2026-07-10-watch-control-spec.md:3-4,30`
- `docs/superpowers/specs/2026-07-10-watch-design-system.md:1-5,24`
- `docs/reviews/2026-07-15-s70-verified-evidence-pack.md:227-232`

### D07 — Handicap / 净杆

裁决：`DECIDED / V1 GROSS ONLY / NET LATER`，而不是新的 Owner 问题。

- 2026-06-09 的 Web 产品重设计明确标为“已与用户逐屏确认”。其计分规格写明：默认比杆；Stableford/净杆按差点作为后续制式。
- 纯 Fable 终审的要求是“把 v1 不做写成明确 decision，不能无声缺席”，并未证明需要重开 Owner 决定。
- 当前 `handicapEstimate` 只能作为明确标注的统计估算，不能直接冒充官方 Handicap Index 或据此生成规则正确的净杆。
- 后续真实净杆需要发球台 rating/slope、逐洞 stroke index、Handicap Index、Course/Playing Handicap 与规则口径；现有解析器、统计估算和 UI 可部分复用，但不构成完整流程。

关键证据：

- `docs/superpowers/specs/2026-06-09-web-product-redesign-design.md:3-5,89`
- `docs/reviews/2026-07-15-claude-fable-watch-full-experience-final-adversarial-review.md:104`
- `ai_caddie/history/history_stats.py:544-583`
- `ai_caddie/courses/course_reference.py:35,297-302`

### D08 — 不记分模式与逐杆

裁决：`DECIDED / C / DERIVED`。

- L04 已锁定击球、成绩、当前洞三条独立事实链。
- 记分与逐杆追踪必须是独立设置；关闭记分只让成绩链保持空，不改变 AutoShot、Club Prompt、手动补杆和逐杆开关。
- 当前开关状态必须明确显示并记住；用户仍可单独关闭逐杆追踪。

### D09 — 佩戴者与多人

裁决：`DECIDED / WEARER ONLY / DERIVED`。

- v1 Watch 只为当前已认证佩戴者产生成绩、逐杆和传感器事件，不出现球员选择器。
- 现有后端是按身份/球员分区的数据模型，适合复用；事件仍必须显式绑定 wearer/player，不能靠隐含默认值。
- “替同组球员手填总分”不是传感器归属问题。若未来要在腕上提供，应另立功能范围决定；逐杆仍不得归给非佩戴者。
- 当前不把“同组手动总分”升级成 Owner 问题：Master Product Spec 明确排除本 build 的 friend/group/team/social surface；S70 v5 官方 `Keeping Score` 子树只有记分方法、统计、Score History 和 Handicap，没有多人计分主题。若未来重开多人赛中卡，再独立评估。

关键证据：

- `docs/superpowers/specs/2026-05-25-ai-caddie-master-product-spec.md:62-66`
- Garmin S70 v5 官方 `Keeping Score`：`GUID-36D33AC5-47C1-4644-B0EC-9ACCD89FEDFF.html`

### D10 — Watch 编辑深度

裁决：`DECIDED / A′ / DERIVED`。

- Watch 可随时修改任意洞总成绩，并完成继续打球所必需的当前洞、未决杆及最近问题修正。
- “最近”覆盖几洞、入口和小表径交互属于原型/田测问题，不让 Owner 凭文字定阈值。
- 全量跨洞逐杆位置、球杆、顺序和球位的深编辑归 iOS；2026-07-07 Owner 定稿明确 Web 只读、iOS 才是编辑器。旧 D10 写成“iPhone/Web 深编辑”不准确。
- 所有修改使用 append-only correction；历史编辑不得改变 `activePlayHole`。

关键证据：

- `docs/superpowers/specs/2026-07-07-review-edit-ui-design.md:1-5`
- `docs/reviews/2026-07-15-watch-decision-and-task-tracker.md:59-64`
- `docs/reviews/2026-07-15-s70-verified-evidence-pack.md:124`

### D11 — 休闲/训练定位与比赛合规

裁决：`DECIDED / PERSONAL LEISURE-TRAINING / NO COMPLIANCE CLAIM`。

- Master Product Spec 把产品定义为个人高尔夫智能产品，并明确本 build 不包含 friend/group/team/tournament/PK/social product surfaces。
- 当前也没有规则、地区、赛事与法律矩阵；因此“不宣称正式比赛合规”是事实边界，不是新的 Owner 偏好。
- Tournament Mode 仍可作为限制 AI、风、PlaysLike 等能力的产品模式，但它不能被文案包装成合规认证。
- 只有 Owner 未来明确要进入正式赛事产品轨道时，才在规则专家/法务证据完成后申请重开。

关键证据：

- `docs/superpowers/specs/2026-05-25-ai-caddie-master-product-spec.md:7-9,31-35,62-66`
- `docs/reviews/2026-07-15-codex-fable-watch-full-experience-reassessment.md:1693`

### D12 — AutoShot 训练数据隐私

裁决：`DECIDED PRIVACY BASELINE + EVIDENCE FIRST RESIDUAL`。

- 传感器训练数据必须单独 opt-in、默认不上传；不得整轮持久化原始 800Hz 流；未确认推断不得进入正式统计。
- 因此旧选项“参加 Beta 即默认上传原始高频窗口”不是合法的对等产品选项。
- 当前也不需要让 Owner 在“可选上传”和“完全本地”之间凭空选择。先由模型/数据团队证明最小窗口上传对检测质量确有必要，并给出字段、时长、用途、保留期、撤回和删除方案。
- 证据成立后，才申请是否运营独立“研究数据捐赠计划”；无证据时保持完全本地。

关键证据：

- `docs/superpowers/specs/2026-07-05-auto-swing-detection.md:107-111`
- `docs/reviews/2026-07-15-codex-fable-watch-full-experience-reassessment.md:811-818`
- `docs/reviews/2026-07-15-claude-fable-watch-full-experience-final-adversarial-review.md:84`

### D13 — Workout 与 Apple Health

裁决：整体移入 `EVIDENCE FIRST`。

- `HKWorkoutSession`、后台 GPS/Motion 生命周期和“是否保存一条 Apple Health Workout”是不同问题。
- 当前尚未真机证明：是否必须使用 Workout、能否可靠运行但不保存、其它后台路径是否成立、AOD/五小时功耗、权限拒绝、被其它 Workout 抢占及恢复。
- 未证明这些平台组合前，不让 Owner 对一个可能不存在的自由组合做产品选择。
- 隐私底线先成立：不得因为后台技术需要而静默写入 Health；若证据后决定提供 Health 集成，也必须显式授权，且拒绝写权限不应破坏核心地图、计分和逐杆。
- Spike 后若仍存在“v1 提供可选保存”与“v1 完全不提供”的真实范围分叉，再申请一个准确的 Owner 二选一。

## 4. 当前真正保留的 Owner 问题

### D04 — 是否批准收窄 Watch 独立开局范围

此前已批准的范围包括 Watch 端“附近球场 → 洞组 → 发球台”、下载并独立开局，以及离开手机完成整轮。当前 review 建议只保留“iPhone 预装后场中独立”，因此必须作为范围重开询问。

准确问题：

> 是否批准把 v1 从“Watch 可独立搜索、选场、选洞组/Tee、下载并开局”收窄为“iPhone 预装真实整轮包；Watch 可从已安装包开始/恢复，并在开球后完全脱离手机打完整轮”？

- A — 批准收窄：v1 不在 Watch 搜索或下载新球场。
- B — 保持既有范围：Watch 可独立搜索、选择、下载和开局，iPhone 只是可选准备/同步面。

Codex 推荐：**B，保持既有范围**。理由是产品目标首先是还原并改进 S70 Watch 体验；完整腕上冷启动是更好的产品设计。A 具有明显的工程复用与交付风险优势，但那是范围/时间取舍，不能冒充产品最优。若 Owner 明确把最短 v1 上线置于 S70 独立性之上，再选择 A。

工程事实：当前 iPhone 真实选场、Tee、`LiveRoundPackage` 与缓存可复用；Watch 端生产冷启动、认证、搜索、下载、包安装和半包恢复尚未完成，因此 B 工程量显著更大。

## 5. 暂定 Owner 队列顺序

1. D02 — Hole Root 条件单杆球童层（当前唯一 `CURRENT`）。
2. D04 — 是否重开并收窄 Watch 独立冷启动范围。

D03、D07–D12 不再占用用户逐题队列。D13 与原 E01–E10 保持证据优先；证据完成后仍须再次审计它们是否真的需要 Owner，而不是自动升级成用户问题。

## 6. 交给纯 Fable 的攻击点

纯 Fable 必须重点挑战：

1. D07 是否确实已由 06-09 的用户确认规格决定，还是 S70 差距足以申请重开。
2. D04 的推荐应按产品最优选 B，还是按 v1 风险选 A；不得混淆两套价值函数。
3. D10 必须尊重“iOS 深编辑、Web 只读”的 Owner 定稿。
4. D11 是否已被 Master Product Spec 的个人产品边界决定，还是仍应作为 Owner 问题。
5. D12 是否应保持“隐私底线已决定、数据捐赠证据先行”，而不是现在就让 Owner 选择。
6. D13 是否必须完整证据先行；何种证据才足以形成真实 Owner 分叉。
7. D09 的同组手动总分是否属于当前产品范围；S70 v5 官方 Keeping Score 子树没有多人计分主题，而 Master Product Spec 又明确排除 group/team/social surface，是否足以不提问。
8. L01–L17、D01–D13、E01–E10 中是否仍藏有遗漏、重复或假 Owner 决策。

## 7. 纯 Fable 终审后的合并修正

纯 `claude-fable-5 / max / 无 fallback` 终审接受本稿所有核心分类，常设 Owner 队列仍为 D02 → D04，但要求补入四项防漂移规则：

1. E07 若证据显著过线，改变确认式换洞默认会重开 D06，必须回 Owner；不能只写“再次审计”。
2. E08 与 D04 合并：D04 选完整独立范围时转为实施工作；选收窄范围时才保留为未来 Owner 重开入口。
3. D13b 必须现在预登记为“平台证据后若范围分叉仍真实存在，则回 Owner”，避免届时被工程默认吞掉。
4. 2026-07-15 重审曾把风/空气密度静默带回 PlaysLike 与动态数据 Track，但 2026-07-02 Owner 已明确“成功率、风：不做；推杆级果岭等高线不做”。因此新增 L18/L19，E09 改为未来 Owner 重开而非普通证据优先项。

最终终审与完整纯度审计见：[纯 Fable Owner 决策队列终审](2026-07-16-claude-fable-watch-owner-decision-queue-final-adversarial-review.md)。
