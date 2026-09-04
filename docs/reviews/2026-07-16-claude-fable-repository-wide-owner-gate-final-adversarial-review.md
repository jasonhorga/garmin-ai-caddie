# 纯 Fable 全仓 Owner-gate 最终对抗审查

> 日期：2026-07-16 UTC  
> 模型：`claude-fable-5`；effort：`max`  
> 会话：`75bd1b53-3fee-4696-8dba-5cd7ff5ff4c6`  
> 日志：`/home/ubuntu/.claude/projects/-home-ubuntu-claude-web-data-repo-garmin-ai-caddie/75bd1b53-3fee-4696-8dba-5cd7ff5ff4c6.jsonl`  
> 运行约束：`CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK=1`、`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`、safe mode、只开放 Read/Grep  
> 纯度审计：133 条 assistant 记录全部为 `claude-fable-5`；`Read ×62 / Grep ×6`；无 Web、Agent、Bash、Write、Edit；`modelUsage` 仅含 `claude-fable-5`；`stop_reason=end_turn`、`terminal_reason=completed`  
> 运行结果：首次尝试成功，无 429/503、无重试、无 fallback；耗时 964.8 秒  
> 性质：独立只读对抗审查；Fable 未修改任何文件
>
> **2026-07-17 QUEUE PROGRESSION：**本报告正文记录终审完成时的队列快照。Owner 此后已确认直接对标 S70，D02 落为 `DECIDED / S70 BEHAVIORAL PARITY / C′`；当前唯一 `CURRENT` 为 D04。现状以[决策账本](2026-07-15-watch-decision-and-task-tracker.md)为准。

## 1. 最终裁决

Fable 对 Codex 全仓合并稿的裁决是 **MODIFY**，但接受核心结论：

- 常设 Owner 队列确实只剩 `D02 CURRENT → D04 QUEUED / OWNER_REOPEN`；
- 没有第三个需要现在向 Owner 提出的问题；
- 家庭可见性、成员 Garmin self-bind、受控分发下 Apple 自动注册均已有 Owner 方向；
- 当前代码漂移都应修回既有决定或等待 D02/D04，不能要求 Owner 为错误实现背书。

Fable 要求修改四类内容：

1. L20 的来源不能只写“由 L16 唯一推出”；
2. 漂移表漏了 Watch 米直接加码、Web 浏览器 GPS 实时记分；
3. 条件重开注册表要区分证据回流和未来功能扩张；
4. 07-13/07-14 review、secrets 文档、USER_GUIDE 仍需 authority/security guard。

这些修正均已合并进[全仓 Owner-gate 审计](2026-07-16-repository-wide-owner-gate-authority-and-drift-audit.md)和[Watch 决策账本](2026-07-15-watch-decision-and-task-tracker.md)。

## 2. Owner 队列

### 2.1 常设队列

| 顺序 | ID | 状态 | Fable 裁决 |
|---|---|---|---|
| 1 | D02 | `CURRENT` | A/B/C′ 定义准确；C′ 契约未完成前必须退化为 B |
| 2 | D04 | `QUEUED / OWNER_REOPEN` | 确认是对既有腕上独立开局范围的重开；应补入 W4 用户原话“尤其是手表” |

### 2.2 条件回流

Fable 确认以下路由必须保留：

- D12b：证明确需上传最小 Motion 窗口后，才问是否运营独立研究数据捐赠计划；
- E07：若证据足以改变确认式换洞默认，重开 D06；
- D13b：平台证据后若 Health 可选保存与完全不提供仍都可行，回 Owner；
- E08：依赖 D04；
- E09：风、空气密度、推杆级等高线未来加回必须 Owner 重开；
- E01：只有田测失败达到 L02/L03 条件时才重开 IA；
- E10：只有证据要求新增全局 wet-lock 模式且存在真实取舍时才升级。

未来主动扩张功能的重开另列：

- D09b：腕上多人计分卡；
- D11：正式赛事产品轨道。

## 3. 非 Watch 三项裁决

### 3.1 家庭数据可见性

`ACCEPT / ALREADY DECIDED`。

2026-06-13 用户已明确决定：

- 按人隔离；
- 每人只看自己；
- 不做全局球员切换器；
- owner 管理页只管理成员与凭证，不浏览成员成绩分析。

因此旧 Fable review 的“owner 全可见 / 仅汇总 / 默认不可见”三档建立在错误前提上，不应成为新 Owner 问题。未成年代管是未来新功能。

### 3.2 成员 Garmin self-bind

`ACCEPT / OWNER-GOAL-DIRECTED / ENGINEERING COMPLETION`。

Apple onboarding 已把 self-bind 指向 Phase B；Phase B 后端设计又定义了隔离目录、成员路由、cookie 策略和测试。当前 Web/iOS 接线不完整是工程缺口。工程 review 可以把真实账户验证设为发布门，但不能把它重新包装为产品方向三选一。

### 3.3 Apple 自动注册

`ACCEPT / DECIDED, BOUNDED BY CONTROLLED DISTRIBUTION`。

Owner-approved 设计允许首次 Apple 登录自动创建隔离成员，前提是分发由 owner 控制。若未来公开下载或做 SaaS，invite/allowlist、人数和资源配额是公开扩张前的安全前置；只有把已批 UX 改成“首登待审批”时，才构成 Owner 重开。

## 4. L20、L21 与 D02 旧子题

### L20

`MODIFY`，实质结论保留。

- 不清旧局 pending：由 L16 推出；
- 旧局必须可恢复：由 L16 + 07-14 C3 缺口推出；
- 至多一个前台 active：来自 D09a/L04 的单一佩戴者与事件归属唯一性，不是 L16 单独推出；
- 自动挂起还是先询问：属于 T092 规格审批细节，不是 Owner 战略题。

### L21

`CONFIRMED`。

2026-06-11 用户原话是“所有的 m 都换算成码给我显示”；同一规格明确后端/接口可保留米制，展示与输入边界换算为码。

### D02 旧 Fable §2.3

三项全部重分类正确：

- 每杆通用 vs Tee-first：C′ 门控下的诚实实施分批；
- 40/41mm 降级：E04 原型证据；
- companion-only：当前契约缺口与 D04 依赖，不是新 Owner 问题。

如果首批真的只支持 Tee 或 companion，必须在 T092 书面规格中显式审批，不能成为隐含默认。

## 5. 代码漂移抽核

| # | 漂移 | Fable 裁决 | 关键证据 |
|---|---|---|---|
| 1 | 固定 60% layup、根页常驻两段路线 | `CONFIRMED` | `WatchEventBridge.swift:381`；`WatchHoleMapView.swift:295-301` |
| 2 | 固定 30×26 散布；零样本伪造 8I/p10/p90 | `CONFIRMED` | `WatchHoleMapView.swift:304-308`；`mobile_live.py:1788-1789` |
| 3 | 默认 18×Par4 空白练习记分 | `CONFIRMED PLACEHOLDER` | `WatchStartView.swift:22-24`；`WatchRoundModel.swift:158-167` |
| 4 | 无配置结束清 pending；新 roundId 丢旧队列 | `CONFIRMED BUG` | `WatchRoundModel.swift:262-282`；`WatchRoundStore.swift:60-78` |
| 5 | 生命周期只写 finish/discard | `MODIFY SOURCE` | L20 来源须补 D09a/L04 与 07-14 C3 |
| 6 | 编辑历史洞改变 activeHole 并自动推进 | `CONFIRMED` | `WatchScorecardView.swift:49-50`；`WatchRoundModel.swift:112-115,189-204` |
| 7 | 无 Fairway 确认；schema 无 fairway；测试用 `center` | `CONFIRMED` | `WatchScoreHoleView.swift:43-75`；两个 schema；`test_mobile_contracts.py:363` |
| 8 | Web 可 POST 深订正 | `CONFIRMED` | `CorrectionsPage.tsx:252-268,424-448`；`server_v2/main.py:976-982` |
| 9 | Weather/Open-Meteo/风修正已进入生产路径 | `CONFIRMED` | package schema；`mobile_live.py:204-229,1797-1805`；`decision.py:1557-1584` |
| 10 | 人工 expectedStrokes 冒充 calibrated | `CONFIRMED` | `decision.py:2553-2561,2664-2669,2686`；三端 UI |
| 11 | 差点 fallback 冒充“差点指数” | `CONFIRMED` | `history_stats.py:514-541`；Web/iOS 文案 |
| 12 | 用户可见 `m` 与英文 `leave` | `CONFIRMED` | `WatchEventBridge.swift:878,898` |
| 13 | `elevationDeltaM` 直接加 F/M/B 码数 | `NEW CONFIRMED` | `WatchRoundContainerView.swift:28-30,170`；`WatchHoleMapView.swift:206-208` |
| 14 | Web 补记页仍用浏览器 GPS 实时逐杆记分 | `NEW CONFIRMED` | `RecordRoundPage.tsx:30-47` |

没有一项需要 Owner 为现实现状背书。

Fable 额外要求：Web 深订正退役前，iOS 必须先具备等价订正覆盖，避免修正平台分工时反而丢能力；这是工程迁移顺序。

## 6. 文档权威审计

Fable 逐一核实新增 guard，没有发现错误覆盖仍有效 Owner 决定。

它指出四个遗漏：

1. 07-13 产品重审会把 D04 的收窄建议冒充已定；
2. 07-14 Fable review 的家庭可见性三档与 8 秒推荐杆提案会违反后续锁定；
3. `docs/security/secrets.md` 虚假声称备份已排除所有 `.garmin_tokens`；
4. `docs/USER_GUIDE.md` 把尚未成立的三端能力写成已完整可用。

这些文件现均已加 guard。

另有两项卫生修正：

- 06-28 两份 family 设计的不存在链接已改指向 06-13 多球员设计；
- `.mockups/watch-shot-tracking.html` 已登记到 T016，后续入 evidence manifest 或归档。

## 7. D04 文本修正

Fable 认为空白练习局是没有 Owner 批准的测试脚手架，不应成为第三题。但 D04 必须说明其命运，避免答案落盘后再次回流。

合并后的规则是：

- 无论 D04 选 A 或 B，默认 18×Par4 空白练习记分都不作为生产兜底；
- A 表示未预装真实包时不能开产品球局；
- 若未来确实要做通用无球场记分卡，作为独立新功能范围重开。

## 8. 唯一下一题

Fable 最终确认：现在只应问 D02，不夹带 D04 或任何条件问题。

- A：根页常驻确定性整洞两段路线；
- B：根页只保留事实层，全部球童进入详情；
- C′：仅在当前一杆建议真实、可信、新鲜且模式允许时显示推荐杆、瞄准线和真实散布；否则完整退化为 B；根页永不画确定性整洞路线。

Fable 维持推荐 **C′**。散布与新鲜度契约完成前，C′ 的实际运行必须等同 B。
