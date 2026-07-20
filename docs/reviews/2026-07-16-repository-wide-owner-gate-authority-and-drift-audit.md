# 全仓 Owner 决策门、文档权威与实现漂移审计

> 日期：2026-07-16 UTC  
> 范围：Apple Watch、iOS、Web、后端、家庭成员/身份、历史规格与 review 文档  
> 性质：产品治理与只读工程审计；不授权产品代码实施  
> 当前结论（2026-07-17 progression）：D02 已由 Owner 锁定为 `S70 BEHAVIORAL PARITY / C′`；唯一 `CURRENT` 是 D04  
> 状态：Codex 三路全仓审计 + 纯 `claude-fable-5 / max / 无 fallback` 最终对抗复核已完成并合并  
> Fable 裁决：`MODIFY`，但接受“无新增常设 Owner 门”；会话 `75bd1b53-3fee-4696-8dba-5cd7ff5ff4c6`，`Read ×62 / Grep ×6`，133 条 assistant 记录全部为 `claude-fable-5`

## 1. 最终问题队列

本轮不是继续增加问题，而是把仓库中所有看起来像“需要用户决定”的文字逐一核成以下五类：

1. 既有 Owner 决定；
2. 已登记的 Owner 重开；
3. 工程或数据证据可以直接决定；
4. 旧文档或当前实现违反既有决定；
5. 只有未来范围真正扩张时才成立的新功能申请。

合并后的常设 Owner 队列仍只有两项：

| 顺序 | ID | 状态 | 准确问题 |
|---|---|---|---|
| 1 | D02 | `DECIDED / S70 BEHAVIORAL PARITY / C′` | 直接对标 S70 的可观察双层行为；数据契约完成前退化为纯事实层 |
| 2 | D04 | `CURRENT / OWNER_REOPEN` | 是否授权把已批准的 Watch 独立搜索、选场、选 Tee、下载和开局范围收窄为 iPhone 预装、Watch 场中独立 |

没有证据支持现在再加入第三个常设 Owner 问题。

## 2. 条件回流注册表

以下事项现在不问。表 2.1 是证据/既有决定触发的条件回流；表 2.2 是未来主动扩张产品范围时才成立的新功能重开。两类都必须先满足条件，再回到单题队列。

### 2.1 证据或既有决定触发

| ID | 当前状态 | 何时才回 Owner |
|---|---|---|
| D12b | `EVIDENCE NEEDED` | 数据团队证明上传最小压缩 Motion 窗口确有必要，并给出字段、时长、用途、保留、撤回和删除方案后，才问是否运营独立研究数据捐赠计划 |
| E07 / D06 | `CONDITIONAL OWNER REOPEN` | tee-anchor 与长期遥测显著证明高置信自动推进优于确认式默认时，重开 D06 |
| D13b | `EVIDENCE NEEDED` | 真机证明 Workout/Health 组合后，“显式可选保存”与“完全不提供保存”仍都真实可行时 |
| E08 / D04 | `DEPENDS ON D04` | D04 选收窄后，未来再恢复腕上独立搜索/下载属于范围重开；D04 选保持既有范围则直接变成实施工作 |
| E09 | `FUTURE OWNER REOPEN` | 风、空气密度或推杆级等高线要重新进入产品前，先备齐来源、精度、TTL、离线和续航证据，再申请重开 L18 |
| E01 / L02–L03 | `CONDITIONAL IA REOPEN` | 单根页入口田测失败并达到 L02 写定的重开条件，才可重新评估三页/IA；普通入口细节由证据直接决定 |
| E10 | `CONDITIONAL PRODUCT-MODE REOPEN` | 湿屏/手套证据证明必须增加全局 app-level wet-lock，且仍存在真实产品取舍时才升级 |

此前 T080 的摘要漏列 D12b；这是路由遗漏，不是新的产品问题。

### 2.2 未来主动扩张功能范围

| ID | 当前状态 | 重开条件 |
|---|---|---|
| D09b | `CLOSED / FUTURE FEATURE REOPEN` | 未来主动提出腕上多人计分卡时，作为新功能单独评估；当前 wearer-only 与 self-only 数据边界不变 |
| D11 | `CLOSED / FUTURE STRATEGY REOPEN` | Owner 主动进入正式赛事产品轨道，并先完成规则、地区、赛事和法务证据 |

## 3. 三个非 Watch 候选的裁决

### 3.1 家庭数据可见性

裁决：`ALREADY DECIDED`，不新增问题。

2026-06-13 用户已明确否决“一个页面翻所有人数据”，锁定：

- 每位球员只看自己的数据；
- owner 管理入口只管理球员、凭证和链接，不浏览成员成绩分析；
- 不存在全局球员切换器。

证据：[多球员地基设计](../superpowers/specs/2026-06-13-multiplayer-foundation-design.md) §1、§5、§7。

因此，旧 review 提出的“owner 全可见 / 仅汇总 / 默认不可见”不是当前绿地三选一。未成年代管若未来真的进入产品，是一项新的家庭监护功能，届时另立范围申请；现在不借它重开已锁定的 self-only 默认。

### 3.2 成员 Garmin 自绑定

裁决：`ALREADY OWNER-GOAL-DIRECTED / ENGINEERING COMPLETION`，不新增问题。

- Apple onboarding 明确把它列为后续 Phase B；
- 随后的 Phase B backend design 已明确目标、隔离模型、路由和测试；
- 当前 Web/iOS 接线不完整属于实现缺口，不是产品方向未决定。

证据：[Apple onboarding 设计](../superpowers/specs/2026-06-28-member-onboarding-apple-design.md)第 3 行、[Garmin self-bind Phase B 设计](../superpowers/specs/2026-06-28-garmin-self-bind-phaseB-design.md)第 3 行、[全仓工程审查 P1-WEB-02](2026-07-11-full-repository-review.md)第 614 行起。

工程 review 把“成员 Garmin bind/sync”写成扩大 TestFlight 的硬发布门，是风险建议，不得反向改写 Owner 已分阶段的范围。是否改变具体发布批次应在发布计划中基于目标测试者能力处理；不制造新的产品三选一。

### 3.3 Apple 首次登录自动注册

裁决：`ALREADY DECIDED, BOUNDED BY CONTROLLED DISTRIBUTION`，当前不新增问题。

2026-06-28 的 Owner-approved 设计明确批准首次 Apple 登录自动创建隔离成员，成立前提是 app 只通过 owner 控制的 TestFlight/App Store 分发。当前代码确实对任意 audience 正确的新 Apple subject 自动建成员（`server_v2/auth_api.py:107-165`）。

由此得到两个不同结论：

- 当前私有、受控分发内：沿用已批准自动注册；
- 若未来面向公众开放下载或自助 SaaS：必须先加 invite/allowlist/approval、人数与资源配额。这是公共扩张的安全前置，不是现在让 Owner 在“安全/不安全”之间偏好选择。

公开家庭/SaaS 扩张本来就不在当前 private MVP 范围内，见[竞品研究结论](../research/COMPETITOR_RESEARCH.md)第 839 行和[产品重审](2026-07-13-product-design-reuse-redesign-review.md)第 870 行。

## 4. 当前实现里的确定性漂移

下列问题不需要再问 Owner；它们要么等待 D02/D04 选择，要么已经违反锁定语义。当前阶段只登记，不修改产品代码。

| 漂移 | 证据 | 分类与处理 |
|---|---|---|
| Watch 根页固定制造 60% layup，常驻 `you → layup → green` 两段路线 | `WatchEventBridge.swift:371`；`WatchHoleMapView.swift:193,295`；`WatchRoundContainerView.swift:146` | D02 方案 A 的现实现；D02 决定前不得当成 canonical |
| 固定 `30×26` 装饰散布；零样本时伪造 `8I/140m/p10/p90` | `WatchHoleMapView.swift:304-308`；`mobile_live.py:1788-1789` | 违反 D02 数据诚实前置、E04、L19；无真实数据时必须完整退化 |
| Watch 冷启动只有默认 18 个 Par 4 的空白“练习记分” | `WatchStartView.swift:22`；`WatchRoundModel.swift:156`；`WatchRoundModelTests.swift:198` | 当前视为 D04 前的 placeholder，不是已批准正式模式；若未来要保留成独立通用记分产品，再单独申请新功能范围 |
| 无后端配置结束会清 pending；新 roundId 会丢旧 pending queue | `WatchRoundModel.swift:254,278`；`WatchRoundStore.swift:59`；相关 tests | 直接违反 L16；数据丢失 bug，不得重问 Owner |
| 旧生命周期文档把开始新局压成 finish/discard 二选一 | 旧 Fable 产品 review 的 active-round 缺口；当前 Watch store 的新 round 清队列行为 | L20 由 L16 + D09a/L04 的事件归属唯一性 + 07-14 C3 推出；自动挂起还是先询问由 T092 审批，不是 Owner 新题 |
| 编辑历史洞会改变 `activeHole`，保存后还自动推进 | `WatchScorecardView.swift:49`；`WatchRoundModel.swift:112,189`；`WatchRoundStore.swift:84` | 违反 L15/D10；编辑洞与实战洞必须分离 |
| 手动确认没有 Par 4/5 Fairway；schema 无 fairway 事件且测试使用 `center` | `WatchScoreHoleView.swift:43`；`watch_input_event.schema.json:32`；`watch_round_state.schema.json:187`；`test_mobile_contracts.py:363` | 违反 L05/L13；只允许 `HIT/LEFT/RIGHT` |
| Web 仍可 POST 球杆、球位、罚杆、推杆和成绩深订正 | `CorrectionsPage.tsx:252,424`；`App.tsx:628`；`api.ts:681`；`server_v2/main.py:976` | 违反 D10 的 iOS 深编辑 / Web 只读分工 |
| 整轮包强制 weather，自动请求 Open-Meteo，决策引擎实际按风修正，Web 可手填逆风 | `live_round_package.schema.json:6`；`mobile_live.py:204,1797`；`decision.py:1557`；`LiveSandbox.tsx:465,538` | 违反 L18；这是生产路径漂移，不是 E09 的研究占位 |
| 固定人工系数输出并展示 `expectedStrokes`，还命名为 `calibrated_history_club_v2` | `decision.py:2553-2561,2664-2669,2686`；`CaddiePage.tsx:696-707`；`CaddiePlanView.swift:88-99`；`WatchCaddieOptionsView.swift:53-55` | 违反 L19；真实自校准前不得展示 |
| 后端是 score-over-par fallback，Web/iOS 却写“差点指数/差点” | `history_stats.py:514`；`StatsDashboard.tsx:286,294`；`StatsView.swift:94` | 违反 D07 的“必须标估算”；文案与契约修正，不是新产品决定 |
| 仍有面向用户的 `m` / 米制拼接与“码”并存 | `WatchEventBridge.swift:878,898` 等展示字符串；旧产品手册也记录 Watch `m` 与全局码冲突 | 违反 L21；内部米制可以保留，展示和输入边界统一换算为码 |
| Watch 把 `elevationDeltaM` 直接加到 F/M/B 码数 | `WatchRoundContainerView.swift:28-30,170`；`WatchHoleMapView.swift:206-208` | 违反 L21 且造成约 9% 数字误差；不仅是单位标签问题，是 P1 正确性 bug |
| Web “补记一局”仍调用浏览器高精度 GPS 做逐杆实时记分 | `web_v2/src/components/RecordRoundPage.tsx:30-47` | 违反 2026-07-02 Owner 决定“去掉浏览器 GPS 实时打球，改为赛后手动录入/订正”；不重问 Owner |

## 5. 旧文档权威漂移

三路审计共检查 81 份 Markdown。以下高风险文件仍可能误导后续实现者：

| 文件 | 仍残留的旧语义 | 当前裁决 |
|---|---|---|
| `plans/2026-07-08-watch-full-consensus.md` | 自称设计已批准、不得重设计；固定根页路线、表冠手势、默认 HKWorkout、轨迹确认 AutoShot | 历史实施计划；D02/D05/D13/E02/E03 与当前账本优先 |
| `specs/work-board.md` | 自称当前唯一工作表；旧 A/B/C 排期门、完整读推杆、AutoShot 先搁着 | 历史进度快照；不得继续生成 Owner 问题 |
| `specs/2026-07-02-unified-tri-surface-spec.md` | 固定表冠、平均杆数、默认 HKWorkout、实时 AutoShot v1 不做 | 保留 Owner 来源证据；被后续 D05/L19/D13/E02/E03 局部取代 |
| `specs/2026-07-03-garmin-data-to-features.md` | 高原空气密度“待拍板” | L18 已关闭；未来加入走 E09 重开 |
| `specs/2026-06-09-web-product-redesign-design.md` | 风、上果岭概率、逐杆自动决定洞分、Web 风沙盘 | L04/D08/L18 后来决定优先；Web v1 gross/net-later 等未冲突部分仍是证据 |
| `specs/2026-07-05-auto-swing-detection.md` | AutoShot 无限后置/待拍板、默认推荐杆、一部分平台推断写成结论 | D05/L07/D13/E06 优先 |
| `specs/2026-07-05-review-v2-design.md` | 暂定球/OB 删因、Web 后续编辑、旧 AutoShot 可行论 | L10/L11/D10/D05 优先 |
| `plans/2026-07-07-review-edit-backend.md` | `addShot` 同一个 lie 同时写 start/end | 违反 L06；仅作历史实现记录 |
| `specs/2026-06-20-r12-garmin-gap-analysis.md` | 自称当前完整设计；推荐杆可能写实际杆；Web 实时编辑 | 历史差距分析；L07/D10/no-code gate 优先 |
| `specs/2026-05-25-ai-caddie-master-product-spec.md` 及早期 Watch companion 稿 | Watch 依赖 iPhone、天气/风是必备输入 | D04 与 L18 优先；仅保留历史产品来源 |
| `specs/2026-05-24-history-review-v2-ui-design.md` | 品牌、PWA/native、score strip、叙述密度 Open Questions | 品牌与 native 已决定；其余由原型/规格审批处理，不单独问 Owner |
| `reviews/2026-07-13-product-design-reuse-redesign-review.md` | 把 Watch 完整独立搜索/开局列入暂缓，可能绕过 D04 | 历史 review input；不得预决 D04 |
| `reviews/2026-07-14-claude-fable-only-product-design-adversarial-review.md` | 把家庭可见性写成未设计三档；提出 8 秒 pending 推荐杆 | 家庭 self-only 已由 06-13 锁定；任何推荐杆预填受 L07 约束 |
| `security/secrets.md` | 声称备份已排除 `.garmin_tokens` | 当前被 P0-BKP-01 证伪；修复与实测前不得声称 `secretFree` |
| `USER_GUIDE.md` | 把 iPhone/Watch 能力、部署和 CI 写成已完整可用 | 历史/目标说明；以真实运行和当前审计为准 |

处理原则：保留历史正文，给高风险文件加 `Authority Correction / Historical Input` 页头；不得删除历史，也不得让页头以下的“待拍板”自动重开现行决定。

## 6. D09b 论据更正

D09b“腕上多人计分卡不在当前范围”的结论成立，但旧论据“已有手机/Web admin 通道替球友记一局”不够准确，也容易被误读成 owner 可浏览成员数据。

正确理由只有两条：

1. 当前 private MVP 明确排除 friend/group/team/social 赛中产品面；
2. S70 的 Watch Keeping Score 证据没有把腕上多人卡证明为核心体验。

后端允许 admin 代某球员写入一局，不等于已有面向用户的手机/Web 代录产品，也不改变“每人只看自己的数据”锁定语义。

## 7. 对当前队列的影响

- D02 已按 Owner 确认落为 `S70 BEHAVIORAL PARITY / C′`；
- D04 已成为唯一 `CURRENT`；
- “空白练习记分”按 placeholder 处理，不制造第三题；
- 家庭可见性、成员 Garmin 自绑定和受控分发自动注册均已有方向，不新增问题；
- D12b 必须补回条件回流总表；
- 当前代码漂移全部进入后续复用/修改/淘汰映射，不得反向要求 Owner 为错误实现背书。
- 纯 Fable 终审新增的两项同等级漂移（Watch 米加码、Web 浏览器 GPS 实时记分）已登记。

## 8. 证据入口

- [Watch 决策账本](2026-07-15-watch-decision-and-task-tracker.md)
- [Codex Watch 队列重分类](2026-07-16-codex-watch-owner-decision-queue-reclassification.md)
- [纯 Fable Watch 队列终审](2026-07-16-claude-fable-watch-owner-decision-queue-final-adversarial-review.md)
- [纯 Fable 全仓 Owner-gate 最终对抗审查](2026-07-16-claude-fable-repository-wide-owner-gate-final-adversarial-review.md)
- [全仓工程审查](2026-07-11-full-repository-review.md)
- [Codex × Claude 工程交叉审查](2026-07-11-codex-claude-cross-review.md)
- [多球员地基设计](../superpowers/specs/2026-06-13-multiplayer-foundation-design.md)
- [Apple onboarding 设计](../superpowers/specs/2026-06-28-member-onboarding-apple-design.md)
- [成员 Garmin self-bind Phase B 设计](../superpowers/specs/2026-06-28-garmin-self-bind-phaseB-design.md)
