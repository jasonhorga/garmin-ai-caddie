# Watch Owner 决策队列终审（纯 Fable 独立对抗稿）

> 日期：2026-07-16 UTC
> 模型：`claude-fable-5`；effort：`max`；首次尝试成功，无重试、无 fallback
> 会话：`0f900a45-cf8a-41c4-8d3c-8874d6b60d74`
> 日志：`/home/ubuntu/.claude/projects/-home-ubuntu-claude-web-data-repo-garmin-ai-caddie/0f900a45-cf8a-41c4-8d3c-8874d6b60d74.jsonl`
> 运行约束：`CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK=1`、`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`、仅开放 `Read` / `Grep`
> 纯度审计：46 条 assistant 记录全部为 `claude-fable-5`；工具内容块仅 `Read ×20`、`Grep ×3`；无 Task/Agent/Web/Write/Edit/Bash；CLI `modelUsage` 仅含 `claude-fable-5`；`stop_reason=end_turn`、`terminal_reason=completed`
> 性质：只读产品治理终审；未修改任何文件；对 Codex 重分类稿逐项独立复核
> 输入：任务指定 15 份文件全部完整读毕（第 13 份实际路径为 `docs/superpowers/plans/2026-07-08-watch-full-consensus.md`，任务清单中的 specs 路径不存在）；另抽验 `ai_caddie/history/history_stats.py`、`ai_caddie/courses/course_reference.py`、`docs/superpowers/specs/2026-06-22-apple-watch-golf-design.md` 页头，Codex 引用属实
> 审查基准：先产品设计是否最优（对标 S70 腕上体验），再工程复用，最后修改建议；既有 Owner 决定优先，模型可决的不转嫁
>
> **2026-07-16 后续全仓审计更正：**本文对 Watch 常设队列 `D02 → D04` 的结论不变，但有两处摘要遗漏/论据需要以[决策账本](2026-07-15-watch-decision-and-task-tracker.md)和[全仓 Owner-gate 审计](2026-07-16-repository-wide-owner-gate-authority-and-drift-audit.md)为准：① 条件回流除 E07、D13b、E08/E09 外还包括 **D12b**（证据成立后才问是否运营研究数据捐赠计划）；② D09b 不再以“已有手机/Web admin 代录通道”为理由，避免误读为 owner 可浏览成员数据。正文保留用于追溯。
>
> **2026-07-17 QUEUE PROGRESSION：**Owner 已确认直接对标 S70，D02 落为 `DECIDED / S70 BEHAVIORAL PARITY / C′`；当前唯一 `CURRENT` 为 D04。正文中的 D02-current 表述是当时快照。

---

## 1. 执行结论

**常设 Owner 队列只剩 2 项，顺序为：**

1. **D02**（`CURRENT`，不变）— Hole Root 球童呈现形态：A 常驻整洞路线 / B 纯事实层 / C′ 条件单杆球童层。
2. **D04**（`QUEUED`，改写为 `OWNER_REOPEN`）— 是否授权把此前已批准的 Watch 冷启动独立范围收窄为"iPhone 预装、Watch 场中独立"。

**另有 3 个"证据完成后可能回到 Owner"的预登记项，现在不问、届时不得静默转为模型决定：**

- **E07**：高置信自动换洞若证据过线，升级默认 = 重开 D06，必须回 Owner。
- **D13b**：真机证明 Workout/Health 平台组合后，若"v1 提供可选保存"与"v1 不提供保存"两个范围都真实存在，才形成一个准确的 Owner 二选一。
- **E08 / E09（重开型）**：E08 是 D04 选 A 之后的延期分支；E09 现文案藏着对 Owner 已否决范围（风、推杆级果岭等高线）的重开，必须改写（见 §3、§7）。

D03、D05–D13 全部退出逐题队列：D03/D08/D09 模型与工程可决，D05/D06/D07/D10/D11 已被既有 Owner 决定覆盖，D12 底线已定、余下证据先行，D13 整体证据先行。

**本轮新发现（Codex 稿未覆盖）：** 2026-07-15 重审把"风/空气密度"作为 S70 对齐项写回了 PlaysLike 设计（`docs/reviews/2026-07-15-codex-fable-watch-full-experience-reassessment.md:436`、`:1094`、Track E `:1305`），而 Owner 在 2026-07-02 spec 已明确"风：不做"（`docs/superpowers/specs/2026-07-02-unified-tri-surface-spec.md:29,146`）。这是一次未申报的静默重开，E09 现文案会把它当开放证据题合法化，必须纠正。

---

## 2. 逐项裁决表（D03–D13）

| 项 | 分类 | 是否改写 | 理由与关键证据 |
|---|---|---|---|
| D03 旧文档权威降级 | `ENGINEERING_OR_MODEL_DECIDABLE` | 是（撤出 Owner 队列） | 见下 D03 详注。三个旧文档没有一份有 Owner 亲自批准记录；07-10 宪法与已锁定 L01–L03 及 L07 直接冲突，"并列生效"不成立，"删除"违反保留原则——只剩一个有效选项，单选项不是 Owner 问题 |
| D04 Watch 独立边界 | `OWNER_REOPEN` | 是（重写问题与选项） | 已批准范围含腕上开局向导与独立整场：`plans/2026-07-08-watch-full-consensus.md:5,72`、`specs/2026-07-10-watch-control-spec.md:47`、`specs/2026-07-02-unified-tri-surface-spec.md:38,161`。账本现三选一（`2026-07-15-watch-decision-and-task-tracker.md:131-133`）把重开伪装成绿地题；选项 C（全程依赖 iPhone 在线）违反已锁定的"不带手机独立打完整场"，删除 |
| D05 AutoShot 首发 | `ALREADY_DECIDED` | 补一条变更记录 | 账本已记用户决定 A（`:140-153`）。需补记：它取代了 07-02 spec D4"实时挥杆识别先不做、轨迹确认过渡"（`2026-07-02-unified-tri-surface-spec.md:126`）——用户后来的"不得无限后置"指令覆盖在先决定，合法，但按账本规则 4（`:20`）应留痕；轨迹确认路径仍可作旧设备/影子期的兜底，无矛盾 |
| D06 确认式换洞 | `ALREADY_DECIDED` | 否 | 用户逐条定义的流程（`:155-168`），与 07-02 D4"确认式切洞"（`:126`）一致 |
| D07 Handicap/净杆 | `ALREADY_DECIDED` | 是（从队列移入已决定检查点） | 2026-06-09 重设计"已与用户逐屏确认"（`2026-06-09-web-product-redesign-design.md:3`），计分制式写明"默认比杆；Stableford/净杆按差点做后续制式选项"（`:89`）。纯 Fable 终审只要求"把 v1 不做写成明确 decision"（`2026-07-15-claude-fable-watch-full-experience-final-adversarial-review.md:104`），从未要求重开。`handicapEstimate` 只是标注"估算"的统计值（`ai_caddie/history/history_stats.py:544-552`），逐洞 stroke index 数据在（`ai_caddie/courses/course_reference.py:35`）但不构成合规净杆流程 |
| D08 不记分×逐杆 | `ENGINEERING_OR_MODEL_DECIDABLE` | 是（写回 DECIDED/DERIVED=C） | 由 L04 三链独立（tracker `:54`）+ 产品立身是深统计（master spec `:7-9`）+ 自动化必须显式可控推出：A 让"不记分"名不副实地继续采集、B 把两链耦合，都无效；C 是唯一站得住的选项。重审 §20 早已把它列入"联合可直接定"（`:1727`） |
| D09 只记佩戴者 | 9a `ENGINEERING_OR_MODEL_DECIDABLE`；9b `DUPLICATE_OR_INVALID` | 是（拆开） | 见下 D09 详注 |
| D10 Watch 编辑深度 | `ALREADY_DECIDED`（合成 A′） | 是（改写选项 A，删 B/C） | 见下 D10 详注 |
| D11 休闲/训练定位 | `ALREADY_DECIDED` | 是（移入已决定） | master spec 定义个人产品并排除 tournament surface（`2026-05-25-ai-caddie-master-product-spec.md:7-9,62-65,738`）；不存在规则/法务矩阵，"不宣称合规"是事实边界不是偏好。B（按正式比赛产品设计）等于重开 master 边界，无人提出，删除；"v1 是否上架 Tournament 隐藏开关"是规格优先级（T062），非 Owner。正式赛事轨道 = 未来 Owner 主动重开 + 规则/法务证据先行 |
| D12 训练数据隐私 | 12a `ALREADY_DECIDED`；12b `EVIDENCE_FIRST` | 是（拆开，删选项 B） | 底线已锁：单独 opt-in、默认不上传、不整轮持久化原始高频、未确认推断不进统计（`2026-07-05-auto-swing-detection.md:108`；重审 `:813-818`；Fable 终审 `:84`）。选项 B（参加 Beta 即默认上传）违反底线，是无效选项。A vs C 现在不成熟：先由数据侧证明最小窗口上传对检测质量确有必要（字段/时长/用途/保留/撤回/删除方案），证据成立才问"是否运营独立研究数据捐赠计划"；无证据时行为等同 C（完全本地） |
| D13 Workout×Health | `EVIDENCE_FIRST`（13a/13b 都是） | 是（整体移入证据队列 + 预登记条件 Owner 项） | "后台是否必须 Workout""能否运行不保存""CLBackgroundActivitySession 是否成立"全是未验平台事实（tri-surface 附录 B `:90` 已指出 HKWorkoutSession 强制心率、替代路径需真机验证）。平台组合未证明前，让 Owner 对可能不存在的自由组合三选一是假问题。隐私地板现在就锁：不因技术需要静默写 Health；写权限被拒不得破坏地图/计分/逐杆核心。Spike 后若"可选保存"与"完全不提供"都真实存在，按预登记回 Owner 二选一 |

### D03 详注

三份旧文档的性质核验：

- `2026-06-22-apple-watch-golf-design.md:4` 自称"设计阶段产物，尚未落地代码"；
- `2026-07-10-watch-control-spec.md:3` 与 `2026-07-10-watch-design-system.md:3` 的"定稿"署名都是"Fable 交互评审 / Fable 整体设计综合"——**是模型定稿，无任何"与用户确认/负责人拍板"记录**（对照：06-09 web 重设计`:3`明写"已与用户逐屏确认"，07-02 spec `:12`明写"负责人拍板"）。

冲突是实锤的双重冲突：07-10 的五页结构与已锁定 L01–L03 冲突（tracker `:51-53`）；更硬的一条是控制宪法的"选杆浮层放 8 秒 = 按推荐杆自动记入"（`2026-07-10-watch-control-spec.md:50`）直接违反用户锁定的 L07"推荐杆不会自动写成实际杆"（tracker `:57`），重审 §11.3 也已废除该行为（`:1004-1011`）。**与用户锁定语义冲突的模型定稿不能继续现行有效**——这不是取舍，是一致性要求。因此：保留全部历史、页头标 `Historical Input / Superseded`、写 supersession ADR、先把其中仍有效的 Owner 语义（如 D04 的开局向导范围）抽入 canonical 再降级（Codex 的安全垫，采纳）。我明确知道 07-15 纯 Fable 终审曾把此项放进用户门（重审 `:1745-1748`）；本轮推翻该立场的理由是当时未做"这些文档是否有 Owner 批准记录"的前提核验——核验结果是没有。执行后在变更记录里向 Owner 通报（可见、可逆），不占逐题队列。

### D09 详注

账本 D09（`:200-213`）捆绑了两个问题，必须拆开：

- **9a 传感器与逐杆归属**：腕上运动/GPS 证据物理上只属于佩戴者；多用户体系的按人隔离是硬不变量（`2026-06-13-multiplayer-foundation-design.md:13-15`：按人隔离、无切换器、谁也看不到别人）。事件显式绑定 wearer/player 即可。推导结论，无需 Owner。
- **9b 替同组球员手填总分**：不属于本 build 产品边界——master spec 明确排除 friend/group/team/tournament/PK/social surface（`:62-65,738`）；S70 证据包 §1.9 的官方计分链（`2026-07-15-s70-verified-evidence-pack.md:118-127`）没有多人主题，Codex 另查官方 Keeping Score 子树同样无多人计分，未见反证——即它也不是 S70 腕上核心体验的一部分。且"给球友记一局"在本产品已有归宿：owner 可经 admin 通道替球友落一局（`2026-06-13-multiplayer-foundation-design.md:115`），承接面是手机/网页而非手表。把它现在升级成 Owner 三选一是无效问题；未来真要做腕上多人卡，属新功能范围，另立重开。

### D10 详注

账本选项 A 写"完整跨洞逐杆地图和深度编辑放在 **iPhone/Web**"（`:222`），直接违反 Owner 2026-07-07 定稿"**网页保持只读，iOS 才是编辑器**（两端有别，负责人定的）"（`2026-07-07-review-edit-ui-design.md:5`）。这是账本内一次未申报的静默推翻，必须改写为 A′。同时：

- 删 B（腕上整轮深编辑）：重开 Owner 已定的两端分工且无新证据，41mm 上复制 iOS 满屏编辑器也与 S70 证据相悖（S70 计分卡只改洞成绩，`2026-07-15-s70-verified-evidence-pack.md:124`）；
- 删 C（腕上只改总分）：违反用户锁定 L11——"打厚了"的入口包含腕上"本洞击球列表"（tracker `:61`），C 会把用户锁定的场中恢复能力砍掉。
- A′ 语义：Watch 可随时改任意洞总成绩（L15，`:65`）+ 完成继续打球所需的当前洞/最近问题修正；全量跨洞逐杆深编辑归 iOS；Web 只读。"最近"覆盖几洞、入口形态 = 原型/田测问题（账本规则 6，`:22`），不问 Owner。

---

## 3. E01–E10 审计表

| 项 | 裁决 | 说明 |
|---|---|---|
| E01 工具入口位置 | 证据直接决定 | 原型/田测出结果即落规格；Owner 在 T092 逐节审批时整体过目。仅当田测失败触发 L02 写死的三页重开条件、且评估结论要求改 L03 级 IA 时，才升级为 Owner 重开 |
| E02 根页表冠空置与否 | 证据直接决定 | 纯交互测量（误转、焦点借还、湿手）。无价值取舍残留 |
| E03 缩放轴 vs 目标停点轴 | 证据直接决定 | K1/K2 同场对照数据定；平手时默认 K1（S70 忠实）已是既定裁决规则 |
| E04 C′ 门槛与小表径降级 | 证据直接决定（条件项） | D02≠C′ 则自动关闭；阈值、降级阶梯、视觉隔离全属账本规则 6 的工程范畴。补一条守卫：完整 Caddie 规格（T062）不得把 S70 的"上果岭概率"抄回来——Owner 铁律"零百分比"（`2026-07-02-unified-tri-surface-spec.md:22`、`2026-07-10-watch-design-system.md:14`）；未自校准前不显示小数平均杆数（`2026-07-16-s70-virtual-caddie-driver-arc-evidence.md:104-112`） |
| E05 AOD 内容与恢复 | 证据直接决定 | "AOD 只投事实层"已是联合不变量（重审 §12.2）；余下是平台测量与默认值工程 |
| E06 AutoShot 设备表 | 证据直接决定 | D05-A 已授权按能力分批；具体机型线随测量走 |
| E07 自动换洞升默认 | **证据后 Owner（重开 D06）** | 队列里唯一预登记的"证据后必回 Owner"项：改的是 Owner 已定的出厂默认行为。证据不过线则永不问 |
| E08 完全冷启动时机 | 与 D04 合并（条件 Owner） | 不是独立问题：D04 选 B 即溶解为实施排序；选 A 则它成为未来范围扩张的重开入口。账本应标注"依赖 D04" |
| E09 Green Contours/动态风进首版 | **改写：一半 ALREADY_DECIDED（排除），一半 OWNER_REOPEN（证据先行）** | 现文案是本轮发现的最大反向漏洞：风与推杆级果岭等高线是 Owner 已否决项（`2026-07-02-unified-tri-surface-spec.md:29,146`），果岭宏观坡向已上线（PR #308）。把它们写成中立的"证据过线后再排优先级"等于允许证据流程绕过 Owner 把已否决范围加回来。改写为："v1 承诺不含风/微观等高线（已决定）；未来加回 = 先备齐来源/精度/TTL/离线/续航证据，再作为 Owner 重开申请" |
| E10 wet lock/手套 | 证据直接决定 | 真机矩阵证明需要才进规格（T092 过目）；不凭偏好加全局模式，维持原判 |

**总注**：除 E07（及 E08/E09 的重开形态）外，没有一项"证据完成后必然要问 Owner"。账本 G7/T080"按 E01–E10 顺序逐项讨论"的表述应改为"逐项审计，仅把满足重开条件的项交 Owner"——与 Codex §5 的方向一致，但要把 E07/E09 的例外写死，防止两个方向的错误：既不把工程题上交，也不让证据流程静默吞掉 Owner 权。

---

## 4. 对 Codex 的异议

| Codex 裁决 | 我的裁决 | 说明 |
|---|---|---|
| D03 = ENGINEERING_DECIDABLE | **ACCEPT** | 补强论据：07-10 宪法的 8 秒自动写杆（`:50`）违反用户锁定 L07——降级不仅是治理整洁，是锁定语义的一致性义务。补一条执行要求：降级写入变更记录并向 Owner 通报（通报制，非审批制） |
| D04 = OWNER_REQUIRED/REOPEN，推荐 B | **ACCEPT 分类与推荐；MODIFY 选项文本** | 重开表述诚实，采纳。修改：①问题里必须点名被收窄的具体已批产物（腕上开局向导 Task 2.6、控制宪法开局三步、离线预取与无手机直连降级 `plans/…:16,43,72`），不能只说"范围"；②Codex 的 A 已含"Watch 可从已安装包开始/恢复"，比账本原 A（只说"开球后"独立）更好，采用 Codex 版；③账本原选项 C 删除（违反锁定承诺）；④"常打球场自动预装"是 A 之下的工程默认值，不得膨胀成第三选项 |
| D05/D06 = ALREADY DECIDED | **ACCEPT** | 补：D05 对 07-02 D4 的取代要落一条变更记录（见 §2） |
| D07 = ALREADY DECIDED | **ACCEPT** | 攻击后站得住：S70 差距论不足以重开——净杆依赖产品没有的官方差点与制式流程，且 06-09 决定本身已含"后续做"的路线位，重开无新价值证据。引用行号全部核实无误 |
| D08 = DUPLICATE/DERIVED | **ACCEPT**（分类词归一为 ENGINEERING_OR_MODEL_DECIDABLE） | 结论相同：C 是唯一有效选项，写回即可 |
| D09 = DERIVED，不问同组总分 | **ACCEPT** | 补强：产品内已有"替球友记一局"的手机/网页承接面（multiplayer-foundation `:115`），家人球局场景不因腕上单人而失去归宿——这让"不问"更站得住 |
| D10 = A′/DERIVED | **ACCEPT** | 补：账本 C 也要删（违反 L11），Codex 稿未点名 |
| D11 = ALREADY DECIDED | **ACCEPT** | 补一句：v1 是否上架 Tournament 开关 = 规格优先级，非 Owner |
| D12 = 底线已定 + 证据先行 | **ACCEPT** | 无修改 |
| D13 = 整体证据先行，13b 证据后再看 | **ACCEPT** | 补一条防漂移要求：13b 的"证据后若分叉成立则回 Owner"必须现在就预登记进账本，防止届时被当工程默认吃掉 |
| "D02 后只剩 D04" | **MODIFY** | 常设队列判断正确、无过度删除；但 Codex §5 漏了三件事：①E07 是唯一预登记的证据后 Owner 重开（D06 默认值），应点名而非笼统"再次审计"；②E08 与 D04 的依赖关系要写进账本；③E09 现文案本身是静默重开载体（风/等高线），Codex 的"E01–E10 保持证据优先"没有发现这一点，必须改写 E09 并把 07-15 重审里的风对齐内容（`:436,1094,1305`）标注为"超出 Owner 已批范围，待重开" |

**REJECT 项：无。** Codex 本稿没有需要整体否决的裁决；全部问题出在遗漏与选项文本精度，均以 MODIFY 收口。

---

## 5. 准确的 Owner 问题

### 当前唯一问题：D02（维持账本原文，不改）

> Hole Root 采用哪种球童呈现形态？

- **A** — 根页无条件常驻 `you → layup → green` 确定性整洞两段路线（延续当前实现，即保留你此前看过的常驻路线视觉）。
- **B** — 根页永远只有事实层（洞号/Par、F/M/B、地图、成绩环、球员位置、适用时的 Driver Arc），一切球童建议进 Caddie/Map Detail。
- **C′** — 条件单杆球童层：事实层永久保留；仅当当前一杆建议真实、可信、新鲜且模式允许时显示推荐杆、当前一杆瞄准线与真实历史散布，点击进完整 Caddie；任一门槛不满足整层消失退化为 B；根页永不画整洞多杆路线（tracker `:101`）。

推荐 **C′**（Codex 与纯 Fable 独立复核一致，我本轮维持）：它是 S70 两层结构的忠实翻译（`2026-07-16-s70-virtual-caddie-driver-arc-evidence.md:31-70`）。工程代价诚实声明：当前只有纵深 p10/p90、无横向散布、契约缺口未补，散布/新鲜度契约（T042/T078）完成前运行行为必须退化为 B（tracker `:102`）——选 C′ 买的是方向，不是立刻可见的层。

### 下一个问题：D04（改写后版本，D02 落盘后才问）

> 此前已批准的 v1 范围包括：Watch 端开局向导（附近球场 → 洞组 → 发球台，`plans/2026-07-08-watch-full-consensus.md:72`、`specs/2026-07-10-watch-control-spec.md:47`）、离线预取 + 无手机时 Watch 直连下载降级（`plans/…:16,43`）、不带手机独立打完整场（`specs/2026-07-02-unified-tri-surface-spec.md:38`）。**是否授权把它收窄为：iPhone 预装真实整轮包；Watch 只能从已安装包开始/恢复，开球后完全脱离手机打完整轮？**

- **A（批准收窄）** — v1 的 Watch 不做球场搜索与新球场下载；开局向导仍在腕上，但只对已预装的球场生效。工程上大量复用 iPhone StartRound、`LiveRoundPackage` 与缓存，交付最快；代价是"临场换未准备过的球场 / 手机没电没带"时腕上开不了局，且"真离线 + 表上开局"这一被你的 spec 认定的最大差异化空档（`2026-07-02-unified-tri-surface-spec.md:161`）v1 不兑现。
- **B（保持既有范围）** — Watch 可独立搜索、选择、下载、开局，iPhone 只是可选准备/同步面。产品上最接近 S70（S70 开局即在腕上完成，`2026-07-15-s70-verified-evidence-pack.md:30-33`）；工程上需要新建 Watch 端生产级认证、搜索、包下载/安装/半包恢复（当前源码三套互斥入口、无生产冷启动路径，重审 `:183-187,1059-1067`），交付显著更慢。

推荐 **B** 为产品最优（与 Codex 一致）；若你把最短 v1 上线置于 S70 独立性之上则选 A。两套价值函数由你定，不由模型混算。选 A 时 E08 保留为未来重开入口；选 B 时 E08 关闭、只剩实施排序。分步交付（先做 A 的里程碑、承诺 B 的范围）属实施计划自由度，不是第三个选项。

### 预登记（届时才问，现在不问）

- **E07**：换洞证据显著过线后——"是否把出厂默认从确认式改为高置信自动推进（重开 D06）？"
- **D13b**：平台组合证明后、且分叉真实存在时——"v1 提供 Apple Health 可选保存，还是完全不提供？"

---

## 6. 可直接写回账本的决定（无需 Owner）

以下每行给出精确状态与一句话语义，可原样落入账本第 4/5 节及变更记录（账本维护者执行；本审查未改文件）：

1. **D03** → `DECIDED / ENGINEERING GOVERNANCE / A`：旧 Watch 文档（06-22、07-10 两份、Round 1/2）标 `Historical Input / Superseded`，写 supersession ADR，先抽取其中仍有效的 Owner 语义再降级，不删除；执行后在变更记录通报 Owner。依据：无 Owner 批准记录 + 与 L01–L03、L07 冲突（`2026-07-10-watch-control-spec.md:50` vs tracker `:57`）。
2. **D05** → 状态不变（`DECIDED / A`），追加变更记录一条："D05-A 取代 2026-07-02 spec D4 的'实时挥杆识别先不做、轨迹确认过渡'（`:126`）；依据为用户其后'不得无限后置'指令；轨迹确认保留为旧设备/影子期兜底。"
3. **D07** → `DECIDED / V1 GROSS ONLY / NET-STABLEFORD 后续制式`：来源 2026-06-09 用户逐屏确认（`:3,89`）；`handicapEstimate` 永远标"估算"，schema 保留净杆扩展位；重开需 Owner 主动发起。
4. **D08** → `DECIDED / C / DERIVED`：记分与逐杆追踪独立设置；关闭记分只让成绩链为空，不静默改变 AutoShot/Club Prompt/逐杆开关；开关状态明确显示并记住。
5. **D09** → 拆写：`D09a DECIDED / WEARER ONLY / DERIVED`（腕上成绩、逐杆、传感器事件只归已认证佩戴者，事件显式绑定 player）；`D09b CLOSED / OUT OF BUILD SCOPE`（同组手填总分不在本 build 边界，master spec `:62-65,738`；替球友记一局已由手机/网页 admin 通道承接，`2026-06-13-multiplayer-foundation-design.md:115`；未来要做属新功能重开）。
6. **D10** → `DECIDED / A′ / DERIVED`：Watch 改任意洞总成绩 + 继续打球所需的当前洞/最近修正；全量跨洞逐杆深编辑归 iOS；**Web 只读**（`2026-07-07-review-edit-ui-design.md:5`）；"最近"的覆盖与入口交给原型；append-only correction、历史编辑不动 `activePlayHole`。
7. **D11** → `DECIDED / PERSONAL LEISURE-TRAINING / NO COMPLIANCE CLAIM`：Tournament Mode 只能作为能力隐藏模式（v1 是否上架 = 规格优先级）；正式赛事轨道 = Owner 主动重开 + 规则/法务证据先行。
8. **D12** → 拆写：`D12a DECIDED / PRIVACY BASELINE`（单独 opt-in、默认不上传、不整轮持久化原始高频、未确认推断不进统计）；`D12b EVIDENCE NEEDED`（先证明最小窗口上传必要性及字段/时长/保留/撤回/删除方案，成立后才问是否运营研究数据捐赠计划；无证据保持完全本地）。
9. **D13** → `EVIDENCE NEEDED`（整体）：13a 平台组合真机验证（Workout 必要性、运行不保存可行性、CLBackgroundActivitySession、抢占恢复、五小时功耗）；13b 预登记条件 Owner 二选一（见 §5）；即刻生效的隐私地板：不静默写 Health、写权限被拒不破坏核心。
10. **E08** → 行内加注"依赖 D04：选 B 即关闭本项，选 A 时保留为未来重开入口"。
11. **E09** → 改写为："v1 承诺不含风与推杆级果岭等高线（Owner 2026-07-02 已决定，`:29,146`；果岭宏观坡向已上线）；未来加回属 Owner 重开，先备齐来源/精度/TTL/离线包/续航证据再申请。"同时把重审 `:436,1094,1305` 的风/空气密度内容标注"超出 Owner 已批范围，待重开后才可入规格"。
12. **E07** → 行内加注"证据过线后 = 重开 D06，必回 Owner，不得工程自决默认值"。
13. **指针修正**：账本头部 `Next decision: D03` → `D04`；§2"当前问题回答后：先更新 D02 和变更记录,再进入 D03" → `D04`；D02 的"下一项 D03" → `D04`；D04 的"下一项 D07…" → "E 阶段（Owner 常设队列到此完结）"。
14. **建议新增两条锁定基线**（防再次走私）：`L18`：v1 无成功率/百分比、无风、无推杆级等高线；PlaysLike 仅高差（来源：Owner 2026-07-02 铁律与 D2/D3，`:22,29,146`）。`L19`：完整 Caddie 不复制 S70 上果岭概率；平均杆数须自校准后才可显示（`2026-07-16-s70-virtual-caddie-driver-arc-evidence.md:104-112`）。

---

## 7. 遗漏检查

**已锁定语义静默推翻扫描（B 项任务）结果：**

| 发现 | 处置 |
|---|---|
| D10 账本选项 A 把 Web 写成深编辑面，推翻 07-07 Owner 定稿 | 已改写为 A′（§2/§6） |
| D04 账本三选一把已批范围包装成绿地题；选项 C 违反锁定承诺 | 已重写（§5），C 删除 |
| D12 选项 B 违反已锁定隐私底线 | 删除（§6） |
| 07-10 控制宪法 8 秒自动写推荐杆违反 L07 | 作为 D03 降级依据记录 |
| **风/空气密度被 07-15 重审静默带回 PlaysLike 设计**，违反 Owner 07-02"风：不做" | 新发现；E09 改写 + 重审相应段落标注待重开（§6 第 11 条） |
| D05 与 07-02 D4 的先后取代关系无变更记录 | 补记（§6 第 2 条），非新问题 |
| D02 选项集本身：核对无违反 D01（成绩环 KEEP）与铁律；C′ 的数据诚实前置已写入（tracker `:102`） | 无需处理 |
| 地图球童路线的既有已过目视觉：未被绕过——D02 的选项 A 就是"保留该路线"，Owner 答 D02 即亲自裁决此事 | 无需另立问题 |

**账本外真实 Owner 决策扫描：** 逐一排查了开局天气卡（无数据源，早已 DEFERRED）、成员 Garmin 自绑定（独立主线，非 Watch 队列）、订阅/发布/商标命名（个人产品边界内已定或不适用）、Green View 拖旗归属、AOD 内容、佩戴手设置、多用户手表归属（由 D09a + 现有隔离不变量覆盖）——**没有发现新的、未登记的 Owner 级决策**。大量中小设计选择的正确聚合点是 G8/T092 的用户逐节规格审批（tracker `:429-435`），不应逐条进 D 队列。

---

## 8. 最终下一步

1. **D02 维持唯一 `CURRENT`，原文不动**；不预先向 Owner 提出 D04 或任何其它问题。
2. Owner 回答 D02 后：先把答案、理由、影响写回账本并落变更记录，同时应用 §6 的全部写回（D03 降级、D05 补记、D07–D13 状态、E07/E08/E09 改写、指针修正、L18/L19 入册），再把 **D04（改写后版本）设为 `CURRENT`**。
3. D04 落盘后，Owner 常设队列完结；进入 G1–G6（canonical 文档、契约、Spike、原型），E 阶段按 §3 的审计结论执行——证据能定的证据定，只有 E07、D13b 和 E08/E09 的重开形态在触发条件成立时回到 Owner，每次仍只问一题、先写回再前进。
