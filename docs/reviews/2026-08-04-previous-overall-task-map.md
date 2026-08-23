# AI Caddie 之前的总体任务全景图（保留版）

日期：2026-08-04  
当前产品冻结基线：`b65128c7a1e190d344944b09c2fbe27d604b7f06`  
性质：旧总体任务的导航、状态与继承关系；**不是一份新的巨型实施计划**。

## 先看这一页

最初目标没有变：做一套以 Garmin 数据为事实来源、以 S70 场上体验为产品基准的个人 AI 高尔夫系统；Web、iPhone 和 Apple Watch 共用后端、球场事实、球局事实与球童语义，同时各自按平台特点呈现。

此前工作实际经历了四层：

1. **最初产品树**：12 条完整产品线，覆盖数据、历史、地图、球童、三端、修正、媒体和私测。
2. **Watch 产品决策**：确定单根页、S70 双层球童、独立腕上开局、记分与换洞、AutoShot 等不可静默推翻的行为。
3. **四份超长工程 Plan**：Round Runtime、Course Platform、Deep Mine、S70 Experience，共 6 万多行；它们保留为约束、失败案例和实现资料，但不再逐行执行。
4. **精简产品里程碑**：后来跳出过度工程，按真实用户旅程完成了开局、记杆、确认、恢复、同步、Watch 新球场下载、地图/球童和 18 洞闭环。

当前不是“从零开始”，也不是“旧计划全部完成”。准确状态是：

- 历史、统计、复盘、基础 Garmin 连接和大量三端代码可以直接复用。
- iOS/Watch 的真实整轮主路径已经跑通过，但新发现的 topo 外轮廓、Watch 展示体感、Garmin GPS 附近球场发现仍未闭环。
- 通用 CAS、签名发布平台、完整 v2 ledger 和通用 Deep Mine 框架没有必要为了计划完整度继续补齐；只有产品路径出现真实需要时才取用其中设计。
- TestFlight 尚未发布；当前视觉冻结也不等于用户最终批准。

## 一、最初的 12 条产品主线

状态词：

- `可复用`：已有真实实现，是后续工作的基础。
- `部分闭环`：主能力存在，但仍有明确产品缺口或质量问题。
- `后置保留`：目标仍有效，但不是当前发布主路径。
- `需重新验收`：曾被声明完成，但按现在的 S70/真实数据标准不能继续直接视为完成。

| # | 原总体任务 | 原始目标 | 2026-08-04 的真实状态 | 是否仍有效 | 当前承接位置 |
|---|---|---|---|---|---|
| 1 | Foundation / Fixtures | 没有 Garmin 密钥也能运行的配置、fixture、状态和测试基础 | `可复用`；已长期支撑后端、Web 和 Native 流程 | 是，作为底座，不再单独做产品里程碑 | T50–T52 验证与证据 |
| 2 | Connector / Snapshot | 获取 Garmin 记分卡、逐杆与球场数据，形成可离线、可追溯快照 | `部分闭环`；历史同步和已知球场链路存在，但 GPS 附近陌生球场发现仍缺 | 是 | T10–T14、T20–T25、T40–T45 |
| 3 | History Statistics | 时间、球局、球场、洞、球杆、问题和数据质量统计 | `可复用`；Web/iOS 已有大量统计与复盘消费者 | 是；当前不是首要阻塞 | T35、T52，以及后续统计校正 |
| 4 | Web History | 深度复盘、趋势、球场/洞/球杆下钻和数据质量 | `可复用 / 需回归`；主要产品存在，仍需与统一球场包和真实整轮事实复核 | 是 | T24、T35、T52 |
| 5 | AI Review | 多 Provider、事实约束的球局/趋势 AI 复盘 | `可复用 / 后置保留`；实现存在，但当前地图和场上闭环优先 | 是；不得让 LLM 改写事实 | 完成 S70 全旅程后重新做质量验收 |
| 6 | Geometry / Course Evidence | 球场 geometry、障碍、落点分类、地图与证据覆盖 | `部分闭环 / 当前有 bug`；prodgeometry、hazard、topo 已使用，但 mask 尖刺/孤岛和未知 Garmin 数据仍未挖完 | 是，当前核心 | T01–T05、T12、T21、T40–T46 |
| 7 | Caddie Decision | 根据个人球杆、当前位置、路线与障碍给出可审计的当前杆和整洞方案 | `部分闭环 / 需重新验收`；真实结构化球童和打法链已接入，但仍要按 S70 双层行为、数据诚实和视觉体感复核 | 是，核心产品价值 | T21、T30–T35、T46、T52 |
| 8 | Manual Correction | 注释、总分/推杆/Fairway/罚杆/逐杆修正且保留审计 | `可复用 / 主路径已跑通`；Watch 任意洞成绩修改、iOS 深编辑和复盘已存在 | 是 | T33、T35、T52 |
| 9 | iOS Live | 选场、离线包、GPS、地图、球童、记杆、计分、结束和同步 | `部分闭环`；真实 18 洞已跑通，但当前选场仅基于已知球场，topo 视觉和 S70 体验仍有缺口 | 是，当前核心 | T02–T03、T10–T14、T20–T22、T30–T35 |
| 10 | Apple Watch | 腕上独立开局、地图/读距/球童、记杆计分、离线整轮和同步 | `部分闭环 / 需重新验收`；软件链和模拟器真实数据整轮已完成，独立 nearby 范围、真机 AutoShot/Workout 和 S70 体感仍未最终过门 | 是，场上第一表面 | T04、T20–T23、T30–T35、T52–T53 |
| 11 | Photo / Video | 将球位、障碍、视线等图像证据附着到球局，不把视觉推断冒充事实 | `后置保留`；早期 source/contracts 存在，不是当前首发闭环 | 是，但不阻塞当前版本 | 后续独立产品切片 |
| 12 | Private Trial Hardening | 身份、隔离、部署、备份、导入导出、可观察性、TestFlight 和有限私测 | `部分闭环`；基础设施和 CI 很多，但用户视觉批准、真实新球场和 TestFlight 发布门未过 | 是 | T50–T53 |

原始总树：[2026-05-25-ai-caddie-master-plan-tree.md](../superpowers/plans/2026-05-25-ai-caddie-master-plan-tree.md)。它是历史产品范围，不再单独授权旧的动态风、iPhone-only Watch 或旧 UI。

## 二、后来锁定的 Watch / S70 产品约束

这些不是待办项，而是所有后续任务必须遵守的产品答案：

1. 淘汰五页横滑，也不把三页作为默认方向；采用“单一当前洞根页 + 浅层仪表面 + 单一交互仲裁器”。
2. 保留 S70 式 18 洞成绩环。
3. Hole Root 永久显示真实事实；当前一杆建议只有在真实、可信、新鲜且模式允许时出现，点击进入完整 Caddie；不足时诚实消失。
4. Watch 必须能独立搜索球场、选洞组/Tee、下载真实球场包并开局；iPhone 是可选协助，不是腕上冷启动前置。
5. 击球、成绩和当前洞是三条独立事实链；推荐杆不得自动变成实际球杆。
6. Fairway 只有 `上球道 / 偏左 / 偏右`；landing lie 表示本杆起始位置。
7. Tee 同点多杆产品层只保留最后一杆；非 Tee 近距观测先记录，唯一额外恢复语义是“打厚了”。
8. 默认成绩可以一键接受；手动顺序是总杆 → 推杆 → Par 4/5 Fairway → 罚杆。
9. 到下一 Tee 不等于换洞；下一洞首杆可以 provisional。确认上一洞后归入下一洞，Cancel 后归回上一洞。
10. 任意洞成绩随时可改；编辑历史洞不改变当前实战洞；除明确 Discard 外不得清未同步数据。
11. AutoShot 分设备做 Beta，手动记杆永久保留；AutoShot 必须最后接入已经可靠的手动事实链。
12. v1 只做 gross score；Watch 只记录佩戴者本人；深度逐杆编辑归 iOS，Web 保持只读复盘。
13. v1 不显示假成功率，不接风/空气密度，不做推杆级果岭等高线；PlaysLike 仅使用已核实高差。
14. 用户距离统一显示码；内部可用米，但边界必须明确换算。
15. AutoShot 高频数据默认不上传；任何研究上传必须独立 opt-in。不得因为后台运行需要静默写 Apple Health。

完整决策与证据：[2026-07-15-watch-decision-and-task-tracker.md](2026-07-15-watch-decision-and-task-tracker.md)。其中旧 G0–G9 的文档治理流程已经完成历史使命，不再要求重新走一遍“先写完所有规格再编码”。

## 三、四份超长 Plan 到底是什么状态

### Plan 1 — Canonical Round Runtime

原任务层级：

1. authority manifest / 防契约漂移；
2. CanonicalJSON 与 typed IDs；
3. event/reason registry 和三端 declarations；
4. 修复 v1 retry / ACK 数据丢失；
5. 客户端 pending queue 与 Swift canonical/storage 边界；
6. 去风、固定 round ID、单位漂移和 greenSlope quarantine；
7. SQL v2 ledger；
8. v2 ingest / receipt；
9. deterministic reducer；
10. replay / ACK / merge / compaction；
11. Shared Swift Domain；
12. iOS 迁移；
13. Watch 双状态/双队列收敛与跨设备 ResolutionCommit；
14. production shadow / cutover。

执行事实：Task 1–4 曾被正式标记 `VERIFIED`；Task 5A、5B1 做到一部分后出现递归拆分和过度验证，随后明确停止线性执行。后来的精简里程碑直接用现有 event、ACK、WatchRoundStore、OfflineStore 和同步 API 完成了真实产品恢复/同步，但**没有按 Plan 1 Exit Gate 证明整份 Plan 完成**。

保留方式：数据不丢、事件身份、恢复、跨端一致性等不变量继续有效；通用 RFC8785 平台、storage-v2/v3、完整 v2 ledger 等只在真实产品 bug 需要时取用，不作为独立产品目标。

原文：[2026-07-18-phase0-canonical-round-runtime.md](../superpowers/plans/2026-07-18-phase0-canonical-round-runtime.md)。

### Plan 2 — Course Acquisition / Snapshot / Installer

原任务层级：

1. provider / venue / layout / Tee identity；
2. identity 持久化和 merge/unmerge；
3. occurrence-preserving Garmin adapter / discovery；
4. encrypted Raw CAS / provenance；
5. source observation / revision / head；
6. rights / security domain；
7. acquisition build queue 与陌生球场 production 链；
8. 逐洞 capability quality gate；
9. immutable snapshot；
10. signed install manifest；
11. Course Service；
12. update / rollback / purge / GC / static authority；
13. Swift/TypeScript verifier 与共享安装状态机；
14. iOS installer；
15. Watch direct/relay、独立搜索/下载/开局；
16. Web installer；
17. 跨端 offline/race/crash 验收。

执行事实：该 Plan 没有线性实施。精简路径复用了已有 course options/package/prep 接口，完成了 Watch 按名称搜索远端球场、下载、缓存和离线开局；没有为了交付先建 CAS、rights matrix、Ed25519 channel/GC 平台。

当前缺口正落在这条线上：provider-wide GPS nearby 尚未证明；iOS 只会对历史已知球场排序；陌生新球场的后台准备、逐洞 readiness、三端统一安装状态仍未闭环。

保留方式：identity、真实 Garmin discovery、可恢复后台准备、逐洞质检、统一 package/readiness 和跨端离线仍然有效；复杂 CAS/签名/rights 只有出现明确安全、发布或多账户需求时才恢复。

原文：[2026-07-18-course-acquisition-snapshot-installer.md](../superpowers/plans/2026-07-18-course-acquisition-snapshot-installer.md)。

### Plan 3 — Garmin Deep Mine Research Lab

原任务层级：

1. 授权原始 corpus；
2. ByteDomain / node ledger / byte closure；
3. lossless IR / provenance；
4. parser registry / budgets；
5. unknown registry；
6. protobuf 全字段 inventory；
7. duplicate-aware JSON inventory；
8. ZIP record / gap inventory；
9. texture/image metadata；
10. 全部 Draco attributes；
11. DSKIMG/GMP 的 TRE/RGN/LBL/DEM/contour；
12. fingerprint / diff；
13. coverage / finite-corpus stop rule；
14. 只针对证据缺口生成用户抓包请求；
15. evidence-bound capability promotion；
16. deterministic replay / CLI / CI。

执行事实：仓库历史上已经做过 prodgeometry、Draco、CourseView IMG/DSKIMG、高程和 hazard 的多轮解析，但通用 C1–C16 研究平台没有作为整体实施；这不等于 Garmin 数据已经挖尽。

保留方式：研究目标全部保留，但改成非阻塞轨。优先回答真实产品问题：附近球场来源、未知 protobuf 字段、所有 Draco attributes、DSKIMG 中还有什么、各数据源覆盖率。只有经过身份/坐标/单位/跨样本验证的数据才能进入产品。

原文：[2026-07-18-deep-mine-research-lab.md](../superpowers/plans/2026-07-18-deep-mine-research-lab.md)。

### Plan 4 — S70 Experience / Capability Promotion

原任务层级：

1. 清除误导输出和建立三端诚实零状态；
2. Guidance contract、生成代码边界和静态资产 authority；
3. verified-elevation-only PlaysLike；
4. hazard guidance；
5. macro green；
6. confirmed-shot club calibration 与二维 dispersion；
7. deterministic current-shot / full-Caddie planning；
8. offline-first Apple Guidance state；
9. iOS Hole Root / Map / Caddie；
10. Watch 单根页与 Map/Caddie/Hazard/Green 仪表；
11. flag placement / PinPointer / 41–46mm parity；
12. Web 治理与复盘；
13. 手动记杆、Club Prompt、shot-station reconciliation；
14. S70 成绩确认与换洞；
15. AutoShot 最后接入。

执行事实：后来的精简里程碑实现了其中大量可见路径，包括真实地图/障碍/球童、手动杆、Club Prompt、顺序计分、provisional 下一洞杆、强杀恢复、18 洞结束和 AutoShot 软件候选。但最新用户检查证明“运行过”和“达到 S70 体感”不是同一件事；topo 轮廓、Watch 比例/排版和完整体验仍要重新验收。

保留方式：Plan 4 是最有直接产品价值的资料，但按页面/旅程取用，不再从 D00 到 D15 机械执行。

原文：[2026-07-18-s70-experience-capability-promotion.md](../superpowers/plans/2026-07-18-s70-experience-capability-promotion.md)。

## 四、真正跑过的精简产品里程碑

2026-07-26 起，执行方式从“补完平台”改成“交付完整用户结果”。冻结产品分支记录的六个里程碑为：

| 里程碑 | 用户可见结果 | 冻结分支记录 | 今天如何看 |
|---|---|---|---|
| M1 | iOS/Watch 用一个真实球场完成开局 | `COMPLETE` | 可复用基础成立 |
| M2 | 已确认的成绩确认、手动记杆、下一洞候选归属 | `COMPLETE` | 核心交互仍有效 |
| M3 | 强杀恢复、重发不丢不重、进入后端并可复盘 | `COMPLETE` | 继续作为 hard invariant |
| M4 | Watch 搜索、下载、缓存新球场并离线开局 | `COMPLETE — 软件/模拟器证据` | 不是 provider-wide GPS nearby；真机独立体验仍要验 |
| M5 | S70 地图/球童接真实距离、危险区和球杆数据 | `COMPLETE` | 数据接入完成不等于视觉和体感完成；需 T30–T35 重验 |
| M6 | AutoShot 软件路径和按需 Deep Mine | `SOFTWARE COMPLETE — 待真机门` | AutoShot 不能宣称真实识别已完成 |

随后还跑通了 iPhone 和 Watch 各自真实 18 洞、历史修正、ACK/finish 和回到无进行中球局。冻结分支的 61 状态视觉审计也关闭了当时列出的差异，但它没有覆盖所有真实球场 geometry、审批页设备框和 Garmin 全球 nearby，因此不能外推为“整个产品已经最终完成”。

精简执行原文位于冻结产品提交：`docs/product/2026-07-26-lean-product-execution.md`。当前工作树的控制分支早于该提交，核对时应使用：

```bash
git show b65128c7a1e190d344944b09c2fbe27d604b7f06:docs/product/2026-07-26-lean-product-execution.md
```

## 五、旧总体任务如何落到当前执行表

当前精简表不是替代旧任务，而是它们的执行索引：

| 当前阶段 | 继承的旧任务 | 当前要交付的结果 |
|---|---|---|
| T00–T05 topo 与 Watch 展示 | Master 6/9/10；Plan 2 quality/snapshot；Plan 4 iOS/Watch map | 清掉真实洞 mask 尖刺/孤岛，统一地图表面，修正 Watch 审批框并全洞验收 |
| T10–T14 陌生新球场 | Master 2/6/9；Plan 2 discovery/acquisition/iOS installer；Plan 3 protobuf/endpoint | 证明真实 Garmin nearby 来源，让 iPhone 找到并离线准备一个历史中没有的球场 |
| T20–T25 三端统一 | Master 2/6/9/10/12；Plan 1 事实一致性；Plan 2 identity/package/installer | 三端共用 course identity、地图资产和 readiness；Watch/iOS/Web 不再各猜一套 |
| T30–T35 S70 全体验 | Master 7/9/10；Watch 决策账本；Plan 4 | 按完整一场逐状态比较 S70、批准图与真实 runtime，而不是只看几个截图 |
| T40–T47 Deep Mine | Master 2/6；Plan 3 全部研究目标 | 无损挖 protobuf、prodgeometry、DSKIMG、raster、更新与覆盖；证据不足才请求抓包 |
| T50–T53 发布门 | Master 12；四 Plan 的必要可靠性约束 | homeserver/GitHub Actions 验证、真实数据矩阵、并排证据、用户批准后再发 TestFlight |

当前执行表：[2026-08-04-ios-topo-nearby-course-and-overall-task-audit.md](2026-08-04-ios-topo-nearby-course-and-overall-task-audit.md)。

没有被当前 T00–T53 重复列出的历史统计、AI 复盘、Photo/Video、家庭成员和运营能力并未删除；它们要么已有可复用实现，要么属于当前真实场上闭环之后的产品切片。若当前改动触碰这些消费者，必须回归；但不为“总体计划看起来完整”而重新开一条基础设施长线。

## 六、现在整体做到哪里

```text
长期产品目标与 S70 行为决策             已明确
历史 / 统计 / Web 复盘基础               大量可复用
真实 iOS / Watch 手动 18 洞闭环          已跑通
成绩确认 / provisional / 修改 / 恢复      已跑通
真实地图 / 障碍 / 球童数据接入            已接通，但视觉与数据质量需重验
Watch 按名称找新场、下载、缓存、离线开局   软件链已跑通
Garmin GPS 周边全库发现                   未证明 / 未实现
Topo 全球场轮廓质量                       未通过
S70 完整体感与真机门                      未最终通过
AutoShot 真机识别与 Workout/Health 证据    未最终通过
用户最终视觉批准 / TestFlight             未完成
```

因此主线回到一个很清楚的位置：先修眼前真实 topo/Watch 展示问题；再证明 Garmin nearby 并打通一个陌生球场；随后统一三端并按完整 18 洞重新验 S70 体验；Deep Mine 并行但不阻塞；最后把证据交用户批准后才发 TestFlight。

## 七、保留规则

- 四份超长 Plan、早期 Master Plan、Watch 决策账本和全部对抗 review 均原样保留，不删除，不声称“之前白做了”。
- 旧 Plan 中的哈希、CanonicalJSON、CAS、签名、序列化、租约和 GC 是候选实现机制，不是面向用户的总体目标。
- 新 Task Board 只负责告诉我们下一步交付什么，不取代旧资料中的不变量、失败案例和证据。
- 深入某个问题后必须回到本文的 12 条产品线和当前 T00–T53，防止局部研究再次吞掉整体推进。
- 任何“完成”必须区分：代码存在、软件/模拟器跑通、真机证据、用户视觉批准、已发布；不能把其中一层冒充下一层。
