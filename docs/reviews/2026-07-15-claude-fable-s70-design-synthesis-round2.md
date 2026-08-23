# S70 → Apple Watch 概念设计综合 · 第二轮（接受 Codex 强对抗后的修订版）

> 日期：2026-07-15 UTC ｜ 模型：`claude-fable-5`，effort **max** ｜ session ID：`a10212b2-906e-4327-addd-50cfda4f10d0`
> 运行元数据（如实）：Round 1 全部 substantive design/tool turns 为 Fable；Claude Code 自动 ai-title 产生过极少量 `claude-haiku-4-5` 辅助用量（2075 in / 24 out），不是正文 fallback，也不隐瞒。Round 2 启动方已设 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`；本轮纯度最终以启动方审计 `result.modelUsage` 为准。**本轮第一次尝试在生成 Write 时因 API `Response stalled mid-stream` 未落盘，本文件为同会话重试产物**，无模型切换、无 fallback。
> 输入：Round 1 报告、`2026-07-15-codex-adversarial-attack-on-fable-s70-round1.md`、`2026-07-15-s70-verified-evidence-pack.md`（三者全文在册）；工程事实沿用 Round 1 实读的 27 个 Watch 源文件与 WatchEventBridge。
> 性质：RESEARCH / CONCEPT，非用户批准 spec，不授权实现。Apple 平台能力无仓库/输入证据者一律标 PLATFORM UNKNOWN。

## 状态：COMPLETE

**核心裁决变化（先说结论）**：撤回「方向 A 是唯一产品架构」。改为：**可靠性骨架（P0）无条件保留为第一步；场上交互以两个同等强度候选 K1/K2 进入原型对照，K1 为优先原型候选**。理由：Codex §12 列出的平台未知（表冠焦点仲裁、AOD、Back 全覆盖、Ultra 按钮）在本轮无法用仓库证据消除，按纪律不得以 UNKNOWN 为支柱宣称唯一架构。

---

## 1. 对 Codex 攻击 §0–§18 的逐项裁决

| § | 攻击要点 | 裁决 | 一句话理由与报告落点 |
|---|---|---|---|
| 0 | 62/100 封顶 59，A 只能是「优先原型候选」 | **保留** | 接受评分与降格逻辑；本轮自评见 §14，推荐措辞已降格 |
| 1 | 元数据须区分 substantive/辅助/fallback | **保留** | 已按其口径写入本文件头；ai-title Haiku 用量如实列出 |
| 2 | 三项让步（计分门撤回/契约先行/五页不再耗真机） | **保留** | 双方收敛，进 §15 收敛清单 |
| 3 | 记分数学未闭合，六量未定义 | **保留（红线成立）** | Round 1 确实混用「已记杆数」与「总杆含推杆」；§2 给闭合模型+3 算例；账本预填改为闭合后的受限形式 |
| 4 | 三候选不公平，B 是税、C 被削弱 | **保留** | 承认偏置：B 与 A 比数据真相、C 比 IA，比较轴不一致；§3 按正交决策重组 K1/K2/K3，K3 不再被拿掉自动换洞以外的正当能力 |
| 5 | A 是过载编排器非被动仪器 | **修改** | 首帧过载指控部分成立：主屏拆三层（事实/操作/意见），AI 行改门控；但洞号Par/F/M/B/洞图/上一杆四件是 S70 官方首帧（证据包 §1.3），不撤；§5 给三档中断预算 |
| 6 | 沿洞轴混合视口/对象/表面，模式过多 | **修改** | 攻击成立：Round 1 的轴混了三种语义。拆解后「目标停点轴」降级为 K2 被测项，K1 默认表冠=显式缩放（S70 slider 直译）；遗留问题逐一作答见 §7 |
| 7 | 自动换洞默认档与墙钟撤销不合格 | **修改** | 接受：撤销改绑「用户交互/下一杆确认」非墙钟；默认档改确认式（K1），高置信自动降为 K2 原型对照；八类困难场景进入标定集；「≤1/18」撤回为 pilot 观察值 |
| 8 | 点击位置≠击球位置 | **保留** | 全盘采纳 candidateShot 语义；§8 给唯一事件模型，观测位置带 posQuality，永不冒充击球位置 |
| 9 | Club Prompt 反馈矛盾（下滑=unknown 又=误报） | **保留（矛盾属实）** | Round 1 §4.1 与裁决表 #12 确实互相矛盾；§8 给唯一语义：下滑=忽略（unknown），误报=显式按钮 |
| 10 | 计分换洞应数据解耦、体验协同 | **保留** | 采纳 scoreDebt：转场时刻是自然提醒点；债务持续可见、结束流程强制清点；§4/§6 落地 |
| 11 | AI 常驻行既抢又弱 | **修改** | 采纳门控/TTL/失效（§9）；但「距离是事实、建议是意见」分层后，满足门槛时仍允许一行常驻（K2）或点开（K1），由原型裁决 |
| 12 | 平台能力写得过确定 | **保留（红线成立）** | §10 给 CONFIRMED/PROTOTYPE-ONLY/UNKNOWN 矩阵；标准表、无 AOD、无 Ultra、湿屏成立为硬底线；AOD/Ultra 降为增强件 |
| 13 | 自动暂停守卫生命周期矛盾 | **撤回（原设计）** | 「自动 paused 但不产生数据变更」确实自相矛盾；守卫降为：提醒+标记疑似离场+保持采集或显式降级，绝不自动改 active 语义 |
| 14 | 工程矩阵两项过乐观+五项补充 | **保留** | GeoMath 改「修改复用」；WatchRoundStore 非 WAL；holeMap.you≠tee（`WatchEventBridge.swift:382-384` youPxOverride 即证据）；新事件=全栈契约变化；fairway 自动预填撤回；seed≠一根线；尺寸按 point bounds 重裁（§11/§12） |
| 15 | 可靠性≠只是不丢数据 | **保留** | 六条新不变量（不丢/不重/低置信不冒充/人工优先/来源可审计/旧自动不覆盖新人工）纳入 hard invariant（§13） |
| 16 | 量化数字只能是 pilot 观察值 | **保留** | §13 三级分级；撤回全部小样本发布门 |
| 17 | 逐项交付清单 | **保留** | 本文结构即按其 14 项交付 |
| 18 | 必须保留的收敛结论 | **保留** | §15 全文列出，一条未推翻 |

**对 Codex 的两处有据反驳**（非辩护，附可证伪依据）：①§5 称首帧「常驻 AI 建议」违背被动性——但 S70 官方 Virtual Caddie 开启后同样叠加在洞屏（证据包 §1.7 输入为 Action 进入；其推荐展示形态官方图为独立面）——此处 Codex 对：常驻行无 S70 首帧先例，我撤；但「洞号/Par+F/M/B+洞图+上一杆」是官方首帧全集，若 Codex 主张再删减，须给出 S70 之外的证据，这四件保留。②§7 称「一次误换就可能把下一杆归错洞」——成立于 AutoShot 期，但 v1 手动记杆的 candidateShot 带 `holeAtCapture` 且可 correction 重归属（§8），误换的破坏半径在 v1 有界；这不推翻其结论（默认确认式我已接受），只修正其损害模型。

---

## 2. 记分真相模型（闭合）

**定义（唯一口径，跨端写死）**：

- `physicalStrike`：规则意义上的真实击球（含推杆）。罚杆不是击球。
- `trackedNonPuttShot`：账本中的非推杆击球记录（candidateShot 家族，见 §8），状态 ∈ {candidate, confirmed, rejected, superseded}。**推杆不逐杆记录**（GPS 果岭尺度不可靠，证据包 §2.2），只记洞末计数。
- `putts`：洞末人工输入的推杆计数（≥0）。
- `penaltyStrokes`：洞末人工输入的罚杆计数（≥0），非物理击球，按规则计入总分。
- `scorecardTotal`：A 级事实 = 用户确认的本洞总杆 = 非推杆物理击球数 + putts + penaltyStrokes。默认 Par 只是**编辑器初始值**，确认前该洞处于 `scoreDebt`，绝不冒充已确认成绩。
- `unaccountedStrokes` = scorecardTotal − (confirmed(trackedNonPuttShot) 数 + putts + penaltyStrokes)。>0=漏记非推杆；<0=账本多记（提示清理误报）；仅诊断，永不阻塞、永不自动改分。
- 预填规则（闭合后受限恢复）：编辑器初始 totalDraft = confirmed 非推杆数 + puttsDraft + penaltyDraft；当 confirmed 数=0 时回退 Par。putts/penalty 由用户输入，不从账本推。

**算例（Par 4 洞，均不重复不漏算）**：

| 例 | 账本(confirmed非推杆) | putts | 罚 | 预填 | 用户确认 | unaccounted | 说明 |
|---|---|---|---|---|---|---|---|
| 1 全记录 | 4 | 2 | 1 | 4+2+1=7 | 7 | 0 | 物理击球6（4挥+2推）+1罚=7；推杆不产生 shot 事件、罚杆不产生 shot 事件，无重复计入 |
| 2 漏记1杆 | 3（实际挥4） | 2 | 0 | 3+2=5 | 用户改为 6 | 6−5=+1 | 总分正确；差额提示「可补记1杆」，补记为无位置 shot 或不补，均不改分 |
| 3 误报多记 | 5（4真+1练习挥误记） | 2 | 0 | 5+2=7 | 用户改为 6 | 6−7=−1 | 总分与推杆正确；负差额提示清理，用户在击球列表 reject 误报后账本归 4，差额归 0 |

**推论**：①「已记 N 杆」来源行显示的是 confirmed 非推杆数与推杆分开的「N挥+M推+K罚」，不再显示歧义的单一 N；②方向 B 式「账本推导成绩」只在 putts/penalty 已输入后才是恒等式，因此它不是独立架构，是预填公式——Codex §4「B 是模式非架构」由此被数学证实，B 不再作为候选；③依从率定义修正为 confirmed 非推杆 / 用户确认总杆−putts−penalty，仅作 pilot 观察。

---

## 3. 正交决策与同等强度候选

**六个正交决策轴**：D1 首帧事实层（已收敛：洞号Par+F/M/B+洞图+上一杆）；D2 表冠语义（显式缩放 vs 目标停点轴）；D3 记杆入口显著性（安静角标 vs 显著入口）；D4 换洞自动化（确认式 / 高置信候选期自动 / 用户开启全自动）；D5 AI 显著性（门控点开 vs 门控常驻行）；D6 硬件基线（标准表、无 AOD、无 Ultra、湿屏必须独立成立；AOD/Ultra/AutoShot 只是增强）。

**三候选（各自都值得赢；共享 P0 可靠性骨架、§2 记分模型、§8 事件语义、Green View 独立面、菜单仪表面）**：

| | K1「测距仪·缩放冠」 | K2「仪表·目标冠」 | K3「Apple 原生仪表栈」 |
|---|---|---|---|
| 表冠(根屏) | **显式地图缩放**（S70 slider 直译；锚定取景：以「你」为锚朝旗向取景，无自由平移=与 S70 官方一致） | **目标停点轴**（纯对象选择：障碍1..n→layup→旗；不含视口、不含进入其它面；缩放只在全图态/果岭面内，进入借焦点、退出归还，屏上轴标签常显） | 系统语义优先：List 滚动/系统缩放控件；不自绘轴条 |
| 换洞(D4) | 默认**确认式小签**（tee 邻近触发，常驻至交互或离开 geofence） | **高置信自动+可见候选期**（宣告持续到用户交互；撤销至下一杆确认前有效；中低置信降小签/手动） | 确认式小签（其正当选择，非削弱） |
| 记杆(D3) | 安静角标（P2 门后可升级） | 同 K1 | 同 K1（Toolbar 位） |
| AI(D5) | 门控**点开**（洞面一个「球童」入口，门槛满足才可点亮） | 门控**常驻一行**（门槛不满足即缺席） | 门控点开 |
| 导航 | 洞面+仪表面推入；自绘层最少 | 同左 | 单洞根 NavigationStack + 系统 sheet/toolbar/返回，零自定义手势层 |
| 标准表成立性 | 成立（无 AOD/Ultra/AutoShot 依赖） | 成立（同左；焦点仲裁是其最大平台风险） | 成立（平台风险最低） |
| 最大失败模式 | 每洞一次必须响应的换洞小签被无视→错洞停留成默认态 | 表冠模式混乱复发/误转选错目标→仪器感反噬 | 系统组件密度在场上不够「一眼」→回到腕上小 App |

三者不再有陪跑：K1 押「最少模式+最低平台风险」，K2 押「最接近仪器的手感」，K3 押「零平台赌注」。B 已被 §2 证明是预填公式而非架构，撤销候选资格；Round 1 方向 C 的「取消自动换洞+砍地图表冠」削弱不再存在——K3 的确认式换洞与系统缩放是其正当立场。

---

## 4. 一洞时序（四个真实瞬间；主线 K1，⟦K2 差异⟧标注）

**T1 球前抬腕**
- 屏幕：洞面事实层=洞号/Par、F/M/B（中大）、洞图、上一杆药丸；GPS 质量标（仅劣化时出现）；意见层：⟦K2：门槛满足时一行「7铁·打前沿」⟧ K1：「球童」入口点亮与否。
- 用户动作：看；可转冠缩放（K1）/选目标（K2）；点障碍问前/越；点距离切实打。
- 内部事件：无（纯读）。建议按 §9 门控计算，不落事件。
- 失败恢复：无 fix→距离灰+时效标→超龄划线（绝不显示错数字）；无图→数字 hero；建议门槛不满足→入口不点亮/行缺席。

**T2 击球后（拎包瞬间）**
- 屏幕：洞面；用户点「记杆」角标（或不点——完全可选）。
- 内部事件：`candidateShot(shotId, source:manualPostShot, capturedAt, observedPosition?, posQuality, holeAtCapture)` **先落盘**→轻 tick（唯一含义：候选已保存，不担保洞/位置正确）。球杆半层升起：点杆=confirm+club；「误报」显式按钮=rejected；下滑或 8s 无操作=收起，club 保持 unknown（**下滑≠误报**）。
- 失败恢复：无 fix→候选照存 posQuality:none；先点后换杆→半层内改；忘点走远→洞面/列表「补记」，位置三选（当前位/图上指/无位置），无位置者不进距离统计；点错→列表 reject（append，不物理删）。

**T3 走下果岭**
- 屏幕：洞面（不弹任何东西——推杆/罚杆洞末一次输入，果岭上不打扰）。
- 内部事件：无。⟦K2：换洞引擎开始积累下一 tee 置信证据（fix 精度、驻留、方向、上洞 scoreState 仅作证据非门）⟧。
- 失败恢复：此刻点记杆会把推杆误记为非推杆——半层内「这是推杆?」不做（伪精确），靠洞末 putts 输入与 unaccounted 提示纠偏。

**T4 到下一 tee**
- K1：小签「到第 8 洞?」+一次触觉；点=holeAdvance(origin:userConfirm)；若上洞未确认成绩→同帧生成 `scoreDebt(hole7)`，小签旁出「记第7洞」直达计分面；不点=小签常驻（非 10s 消失），离开 geofence 才撤。
- ⟦K2：高置信→自动 holeAdvance(origin:auto, evidence)+全屏宣告，**宣告持续至用户任意交互**；撤销钮驻宣告内，且至「下一 candidateShot confirmed 前」菜单可撤（撤销=holeAdvance correction+受影响 shot 重归属）⟧。
- 计分面（若点入）：预填按 §2；确认→holeScore 事件（原子），债务清除。
- 失败恢复：误换→撤销/选洞，事件链可审计；漏换→小签仍在+手动选洞；数洞未记分→计分卡角标「欠 N 洞」，结束流程强制清点债务列表（可批量 Par 确认，但须逐洞点头——默认值不自动转正）。

---

## 5. 一洞 UI 中断预算（小签/半层/全屏/触觉/必须响应）

| 场景 | K1 | K2 | K3 |
|---|---|---|---|
| 最好（GPS 好、记分勤、无误报） | 1 小签(换洞)/0–1 半层(记杆自选)/0 全屏/2 触觉(换洞+记杆)/**1 必须响应**(换洞确认) | 0 小签/0–1 半层/1 全屏宣告(看见即散)/2 触觉/**0 必须响应** | 同 K1 |
| 典型（每洞记 2–3 杆、洞末计分） | 2 小签(换洞+记分债)/2–3 半层/0 全屏/4–5 触觉/1 必须响应 | 1 小签(记分债)/2–3 半层/1 全屏/4–5 触觉/0 必须响应 | 同 K1 |
| 最坏（GPS 差+误报+忘计分 3 洞） | 3–4 小签(+GPS 标+债务)/3–4 半层(含清误报)/0 全屏/6 触觉/2–3 必须响应 | 同左+1 误换撤销交互（其最坏比 K1 多一次全屏+一次纠正） | 同 K1 |

诚实结论：K1 的结构性成本=每洞 1 次必须响应（18 次/轮）；K2 把它换成 0 次必须响应+误换尾部风险。这正是原型要测的核心交换，纸面不裁。

---

## 6. 换洞三策略公平比较（数据上计分永不驱动换洞；scoreState 仅可作置信证据）

| 维度 | ①默认确认式(K1/K3) | ②高置信自动+候选期(K2) | ③用户开启 S70 式全自动 |
|---|---|---|---|
| 每轮必须响应 | ~18 次 | 0（宣告可忽视） | 0（静默） |
| 错洞停留 | 用户漏点则**持续**（最大风险） | 瞬时（自动纠） | 瞬时 |
| 误换风险 | ≈0 | 有；撤销绑交互/下一杆确认，破坏半径=可 correction | 最高；且用户自选风险 |
| 八类困难场景(球车经过后tee/前tee用户/相邻tee/shotgun/跳洞/双果岭/9→10会所/先到tee未记分) | 天然免疫（人点头） | 全部进标定集；不达标场景降级为① | 同② |
| scoreDebt 协同 | 小签同帧带「记上洞」 | 宣告后洞面挂债务角标 | 同② |
| v1 地基 | 需 tee anchors 契约（现无，§12） | 同左+置信引擎 | 同② |
| 裁决 | **v1 默认** | 原型对照；数据达标后可升默认 | 仅设置开关，pilot 数据后开放 |

撤销语义统一：候选期=「宣告出现→用户任意交互」；纠错期=「至下一 candidateShot confirmed 或手动结束候选」；两期内撤销均为一等操作，全部走 holeAdvance correction。

---

## 7. 表冠与操控唯一语义

**每屏一轴+屏上文字轴标签（常显，杜绝隐含模式）**：洞面=缩放(K1)/目标(K2)；全图态=缩放；果岭面=缩放；计分面=总杆；列表=滚动；半层升起借走表冠、收起归还（焦点仲裁 PROTOTYPE-ONLY，§10）。
**Codex §6 六问逐答（K2 若存活须满足）**：①左右并列障碍：按沿洞距离排序，同距按左→右，标签带方位字（「沙坑·左」）；②多策略路线不进轴（路线属球童面）；③误转：停点切换设角度阈值+回中惯性，轴标签闪显当前对象；④焦点丢失：默认归根屏轴，浮层收起必归还；⑤当前控制何物：右缘轴条+文字标签双通道；⑥缩放无平移：锚定取景（你→旗框架）保证目标恒在框内；偏轴对象靠点按而非平移。
**其余唯一语义**：点按=问它/选它；拖=仅果岭面拖旗；长按=不绑定；横滑=仅推入面返回（Back 全覆盖性 PLATFORM UNKNOWN，K3 用系统返回钮兜底）；下滑=收起浮层；「过 Par 加重哒声」撤回为自定义触觉候选，不冒充系统 detent。

---

## 8. 记杆唯一事件语义（手动与未来 AutoShot 共用）

```
candidateShot(shotId, source{manualPostShot|manualBackfill|auto}, capturedAt,
  observedPosition?, posQuality{fresh|stale|none}, confidence?, holeAtCapture,
  club?, state{candidate|confirmed|rejected|superseded}, correctionOf?)
```
- 观测位置=「记录时位置」，**永不自动冒充击球位置**；fix 超龄→stale；无 fix→none；补记→用户三选。
- 反馈时机：落盘成功→轻 tick（唯一含义：候选已保存）；半层是**可选**球杆确认（manualPostShot 默认升起；auto 低置信不升起只入队列）；8s 无操作/下滑=收起（club unknown）；误报=半层内显式按钮或列表 rejected；改杆/改位置=append correction（supersedes 链）。
- AutoShot=同 schema 第二 producer（source:auto+confidence），手动按钮永不撤；推荐杆永不自动写入 club。

---

## 9. AI 球童建议：门槛、置信、TTL、失效

- 输入门槛（全部满足才出现）：几何 ready 或 F/M/B 有效；到目标距离有效（fix fresh）；该距离段球杆样本≥门槛（数值=baseline 后定）；decision confidence ≥ medium。
- TTL/失效：位置位移>阈值、pin/target 变更、换洞、fix 转 stale → 立即失效并重算；重算失败→**缺席**（意见层规则：低置信即消失，不灰显不占位）。
- 分层铁律：距离=事实层；建议=意见层（K1 点开/K2 一行）；`suggestedClub` 与用户 `club` 字段物理分离，任何路径不得自动转写；expectedStrokes/概率不进主屏（收敛结论）。

---

## 10. Apple 平台能力矩阵

| 能力 | 状态 | 依据 |
|---|---|---|
| WCSession sendMessage/applicationContext/transferFile | **PLATFORM CONFIRMED** | 生产代码+测试（WatchSyncClient 及其测试） |
| CoreLocation 前台 fix（含 accuracy/timestamp） | **CONFIRMED** | WatchLocationProvider 实测在用 |
| ImageRenderer 快照流水线 | **CONFIRMED** | WatchDesignSnapshotTests 在 CI 产图 |
| HKWorkoutSession→后台 GPS/常亮行为 | **UNKNOWN** | 仓库零实现（provider 自认 foreground-only）；entitlement/权限文案/写入 Health 与被其它 workout 抢占策略均未定 |
| AOD 内容/更新频率可控性 | **UNKNOWN** | 无任何仓库证据；AOD 只能是增强件 |
| 左缘右滑承担全部 Back | **UNKNOWN** | 现代码自绘返回钮，无 NavigationStack 证据 |
| digitalCrownRotation 基础绑定 | **PROTOTYPE-ONLY** | 仓库多文档共识可做，但全 target 零绑定；焦点/嵌套 ScrollView 仲裁未证 |
| 浮层借走/归还表冠焦点 | **UNKNOWN** | 无实现证据；K2 最大平台风险 |
| Ultra Action Button 第三方绑定为记杆 | **UNKNOWN** | 仅 06-22 spec 一句提及，无证据 |
| 垂腕/熄屏后恢复到指定表面 | **UNKNOWN** | 无证据；恢复策略须原型裁决 |
| 触觉播放 API 与样式集 | **UNKNOWN** | 仓库零使用 |

**架构底线**：K1/K2/K3 均已按「标准表+无 AOD+无 Ultra+湿屏」独立成立设计；上表 UNKNOWN 任何一项落空只影响增强件与 K2 的轴体验，不影响 P0 与 K1 成立性。

---

## 11. 尺寸重裁（按 point bounds，撤回毫米推断）

撤回 Round 1 两断言：「198pt≈46mm」与「Ultra 最舒展」（Codex §14.7 成立；S70 侧同样撤回，42mm=390×390、47mm=454×454 归证据包口径外的错配）。本轮不再给百分比/字号猜测，改为**信息取舍序**：
- 任何尺寸首帧的不可删集：洞号/Par、中距（最大）、前/后距。
- 第一降级位：洞图（最小屏上「洞图 vs 数字 hero」**必须视觉原型后决定**，不纸面裁）。
- 第二降级位：上一杆药丸（可折进点击）。
- 永不进首帧（所有尺寸）：同步状态、未校准期望杆数、固定散布。
- **2026-07-15 证据更正**：原文在本条中包含“18 洞环”，现已撤销。S70 官方手册与图片明确存在“实体 1–18 洞刻度 + 屏内逐洞成绩色段”；成绩环默认应保留在 Hole Root，具体尺寸与交互态隐藏规则进入原型。见 [S70 成绩环证据更正](2026-07-15-s70-score-history-ring-evidence-correction.md)。
- 必须原型后才能决定的清单：最小屏左列比例与叠放/分栏取舍、AI 行是否有资格上任何尺寸首帧、角标最小可点尺寸、Ultra 边距策略。快照矩阵按真实 point bounds×Dynamic Type 建档，不按表壳毫米。

---

## 12. 工程矩阵修正与 ledger/ACK 边界（不写实现代码）

- **WatchGeoMath 反投影：修改复用**（现仅 geo→px+haversine；px→geo 为新增，含退化/范围外/数值稳定测试）。
- **tee anchors：新建契约**。`holeMap.you` 不可当 tee（手机以 youPxOverride 覆盖为玩家实时位置，`WatchEventBridge.swift:382-384`）；换洞引擎需要每洞 tee 经纬（含所选/最远后 tee）+洞序+几何置信字段，现契约不存在。
- **单 ledger 定义**（WatchRoundStore 现为 snapshot 原子覆盖，非 WAL）：append-only 事件文件（逐条 fsync）+ 周期 checkpoint（现 snapshot 降格为 checkpoint 角色）+ 启动 replay（eventId 去重、correction 按 supersedes 链后写胜）+ 崩溃恢复=最后 checkpoint+尾部 replay。
- **双传输仲裁**：同一事件同一时刻仅一通道在飞（路由租约，超时回收换道）；手机中继成功仅= `handedOffToPhone`，直连 2xx 才接近 `serverAccepted`；三层 ACK：`watchPersisted → handedOffToPhone → serverAccepted/serverRejected`；rejected 进 dead-letter 供人工裁决；`finishedPendingSync → synced` 仅当**全集 serverAccepted**（任一通道单次成功不得触发）；server 幂等键=eventId（重发安全）。
- **新事件=全栈契约变化**：shot/holeScore/holeAdvance/pinSet 触及 Swift 模型、后端 Pydantic、JSON Schema（封闭枚举需 unknown 通道）、reducer/replay、统计与 Web/iOS 消费者——工作量级重估为「大」，非局部中改。
- **fairway 自动预填：撤回**（无 fairway polygon 数据地基）；v1 人工 L/C/R，自动化降为独立数据设计假设。
- **seed 通路：新建（成体系）**：全轮状态包+洞序/tee/green/projection+地图 manifest+版本完整性+缓存淘汰+增量更新+失败恢复；复用 builder 与传输原语，但不是「一根 seedRound 线」。
- 维持 Round 1 有效项：backendClient 双映射分叉必修、任意 2xx 全量 ACK 必修、confirmFinish 清空路径关闭、假表冠指示清零、渲染资产优先复用。

---

## 13. 指标三级分级（撤回小样本发布门）

- **Hard invariant（发布门，自动化可证）**：事件零丢失、零重复计入（幂等/去重）、correction 全链可审计、低置信推断永不冒充事实（默认 Par 不自动转正、推荐杆不自动写入、posQuality 不伪精确）、finishedPendingSync 永不清空、旧自动结果不覆盖新人工结果。
- **Pilot observation（只记分布，不设通过线）**：记杆依从率、误换/漏换次数、抬腕读距时长、小签察觉率、触觉察觉率、拖旗误差、罗盘误差、AOD 可读性、耗电曲线。原 Round 1 的 60%/80% 依从门、≤1/18 误换线、3 人 p90、S9≤75% 等**全部撤回**至此级。
- **Baseline-dependent release gate（先取基线再定门）**：换洞②升默认门、记杆表面化（P2）门、续航门、42mm 版式门——基线来源=S70 对照录制（07-14 §9 清单）+ 现 App 田测分布；低频高损害错误（误换、丢事件、错归属）不得用小样本「未发生」判安全，须用注入测试+长周期遥测。

---

## 14. 同 rubric 自评与推荐变化

按 Codex 口径自评 Round 2：记分模型闭合+3 算例（§2）、候选去偏置（§3）、平台未知全部显式化（§10）、数字降级（§13）、事件语义唯一化（§8）修复了 Round 1 的两条红线与主要偏置；仍存的弱点：候选对照未经原型、tee anchors/全轮包契约仅有边界定义、K2 焦点仲裁未证。自评 **78/100**（不设封顶项：未再把 UNKNOWN 写成设计支柱）。
**推荐变化**：撤回「方向 A 唯一架构」。新推荐=**P0 可靠性骨架无条件先行；K1 为优先原型候选，K2 同场对照，K3 作为实现策略基线与第三对照**；升级为「架构」须以 §10 UNKNOWN 消除+§13 基线门为前提。

---

## 15. 保留的收敛结论与三项最大未决

**保留（一条未推翻）**：五页淘汰；单一当前洞心智；F/M/B+洞图为首帧核心候选；计分不驱动换洞；Green View 独立面；shot/score/holeAdvance 分事件；finishedPendingSync+未同步不清空；统一 coordinator/ledger/事件契约/outbox；AutoShot 只是可替换 producer；手动补杆与 append correction 永存；未校准 AI 数字不进主屏；topo/Canvas/route-anchor 渲染资产优先复用；用户未试功能一律保持待验证。

**三项最大未决**：①换洞默认档的真实交换（K1 的 18 次必须响应 vs K2 的误换尾部风险）只能由双原型同场田测裁决；②表冠焦点仲裁与目标轴可用性（K2 存亡；PLATFORM UNKNOWN 集中地）；③tee anchors/全轮状态包契约设计（换洞引擎与 standalone 统一的共同前置，现契约完全缺位）。

*本报告为第二轮修订，连同 §1 裁决表交用户与 Codex 复核；模型纯度以启动方 `result.modelUsage` 审计为准。*
