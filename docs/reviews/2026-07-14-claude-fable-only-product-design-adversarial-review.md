# AI Caddie 产品设计对抗性独立评审(Claude Fable 5 单模型)

> 日期:2026-07-14 UTC
> 模型:`claude-fable-5`(Claude Fable 5),effort:max
> 会话:单会话、无 Task/subagent/team/其它模型;session ID:`b4262e63-efab-46f9-9840-e56d1839c741`(初稿时运行环境未向模型暴露该 ID,验收补读时由验收方提供后补录)
> 验收补读:2026-07-14 同日,按验收要求对 8 个此前仅做消费面/Grep/Glob 核对的文件完成完整 Read(明细见文末覆盖清单);补读未改变任何 verdict,四处证据引用已按实读加固
> 一致性验收:2026-07-14 同日第二轮,修正计数/等级/状态模型/裸路径等内部一致性问题(明细见修订记录,不改变任何方向性结论)
> Fallback:**本次运行禁止 fallback,且未发生 fallback**;全文由 Fable 5 直接读取源码与文档后撰写
> 基线:本地 `integration/v2` @ `a0c0fca`
> 写入:仅本文件;未修改任何源码/测试/配置/旧报告/旧 spec/mockup;未 commit/push/fetch;未读取 data/、.garmin_tokens 或任何真实凭据
> 主审查对象:[2026-07-13 产品设计合理性、工程复用与改版评估](2026-07-13-product-design-reuse-redesign-review.md)(下称「新报告」)
>
> **2026-07-16 AUTHORITY CORRECTION — HISTORICAL REVIEW INPUT：**本文 I6/V10 把家庭可见性写成未设计三档，但 2026-06-13 Owner 已明确锁定“每人只看自己、owner 管理页不看成员分析”；该访谈不再是当前 Owner 门。本文提出的 8 秒 pending 推荐杆也必须服从 L07，推荐杆不得未经确认写成实际杆。当前队列与更正见[Watch 决策账本](2026-07-15-watch-decision-and-task-tracker.md)和[全仓 Owner-gate 审计](2026-07-16-repository-wide-owner-gate-authority-and-drift-audit.md)。

## 状态:COMPLETE

所有指定文档(14 份)与指定关键实现(Web 10 个、iOS 9 个、Watch 11 个、后端/AI/契约 15 项)均实际读取;大文件按关键段落读取,深度在文末覆盖清单逐项如实标注。结论标签:**CONFIRMED**(源码/文档可判定)、**PRODUCT-HYPOTHESIS**(合理产品假设、无用户数据)、**NEEDS-VALIDATION**(需真机/用户/数据验证)。

---

## 1. Executive verdict

**新报告是一份合格且大体正确的产品设计重审,方向性结论应当采纳;但它有一处内部自相矛盾、两处对旧 spec 的过度否决、三处重要设计缺口,以及若干「直接复用」评级过于乐观的条目。**

具体裁决:

1. **三步顺序(先设计→再复用→后修改)形式与实质上都成立**(CONFIRMED)。第 1–12 节的设计论证大多独立于工程现状;但有两处结论是从现有资产反推的:9.3 的页面投影目标列表与 `server_v2/history_overview.py`、`server_v2/history_round_detail.py`、`server_v2/history_drilldown.py` 三个现存文件几乎一一对应,9.4 的 CoursePack 是投资建议(新报告自己承认)。方向都对,但读者应知道这不是纯白纸推导。
2. **生命周期组织(方案 B)、Web 复盘/统计合并、iPhone 记录语义拆分、AI 解释化、状态机正交化——这五个核心结论我独立复核后同意**,证据见下文。
3. **最大的问题不在新报告说了什么,而在它没说什么(三处重要设计缺口)**:①「记这一杆」产生的逐杆流与「完成本洞」确认的总杆之间的**对账语义**完全未定义——而这恰是旧 Watch 宪法已解决、新报告连带丢弃的条款;②生命周期各阶段之间的**数据契约**(备战产出物是什么、场中如何消费它)缺失,导致「闭环」只是一张箭头图;③**多球局并存/中途弃局保留数据**的状态在状态机里没有位置。
4. **Watch 三方案:我独立分析后同意「单一打球主页 + sheet/push」为首选候选**,且比新报告多一条它漏掉的最强工程论据:现有生产代码 `WatchRoundContainerView.swift:39-137` 已经是 `switch model.screen` 的单根 hub-and-spoke 结构,**五页横滑宪法从未被实现**——单根页候选与现有代码同构,迁移成本三方案中最低(CONFIRMED)。但「抬腕回到当前洞上下文」与旧宪法「抬腕回来必须是离开时的样子」是两个互斥原则,新报告未意识到这一冲突,必须列为真机验证项(NEEDS-VALIDATION)。
5. **不建议重写整个项目、strangler 式迁移**:同意(CONFIRMED)。三份工程评审报告与我的抽查一致表明高价值资产(几何、映射、统计公式、契约测试、隔离模型)真实存在,而缺陷集中在状态机、存储事务与授权表这几条可收口的线上。

---

## 2. 对新报告:最强同意、最强反对、必须修正

### 2.1 最强同意(三条)

1. **「保存本洞」的复合语义是产品错误,不只是代码组织问题。** 实证:`CurrentHoleView.swift:1092-1119` 的 `submitEvents()` 一次性发出 location/score/putt/penalty/club/note 六种事件;同文件 624-638 行「选完即记」又在选杆瞬间单发一个轻量 club 事件;而「结束本场」(699-718 行)确认文案是「未保存的记录会被丢弃」并直通 `onDiscard()` → `AICaddieApp.swift:588-600` `discardActiveRound()` → `OfflineStore.swift:208-223` 物理删除该局全部事件。三个动作(选杆、记录、结束)的语义在同一屏内互相污染,且「结束=删除」直接违反用户直觉。契约层同构证据(验收补读):`live_round_event.schema.json:80-102` 让单个 club 事件的 payload 同时携带选杆字段、完整 `decision` 审计对象与 `actualShot`——语义混合已经固化进跨端契约,不止 UI 层。拆分为「记这一杆/完成本洞/完成并同步本场/放弃并删除」四个动作是正确的(CONFIRMED)。
2. **Web「一个不删」原则确实把重设计降级成了重新分组。** 实证链:[Web 重设计 spec](../superpowers/specs/2026-06-09-web-product-redesign-design.md) 第 44-45 行「现有每个页面都有去处——一个不删」→ `navigation.ts:69-82` 至今保留「球童沙盘/手机记分」工具组;`PrepPage.tsx:246-266`「发到手表/手机」按钮实际执行 `window.print()`;`CorrectionsPage.tsx:396-407` 要求用户手选 targetType、手填「目标编号」;`ReportsPage.tsx:119-206` 是五类报告的「载入/生成」控制台;`RecordRoundPage.tsx:89-101` 整场记录只在 React state。撤销该原则、控制台功能上下文化,是本轮最有杠杆的 Web 结论(CONFIRMED)。
3. **「定稿/宪法」措辞需要免疫处理。** [Watch 操控规范](../superpowers/specs/2026-07-10-watch-control-spec.md) 第 3 行自称「操控宪法」、[Watch 设计系统](../superpowers/specs/2026-07-10-watch-design-system.md) 第 1 行自称「定稿」,但两者所定的五页横滑从未在生产代码中存在(`WatchRoundModel.swift:12-20` 的 screen 枚举与 `WatchRoundContainerView` 是按钮驱动的 hub,不是分页壳)——「定稿」既未验证也未实现,却在文本上排他。新报告「定稿只表示当时选择已记录」的新原则正确(CONFIRMED)。

### 2.2 最强反对(三条)

1. **新报告自相矛盾:频率表判球包为低频「设置或『我的』」,推荐 IA 却给球包 Web 一级入口。** 新报告 §2.1 频率表明确写「球包、账户、连接器 | 低频 | 设置或『我的』」;§6.3 推荐主侧栏却是「复盘/备战/球包/────/设置」;§7.4 iPhone 又说「球包/账户进入设置或『我的』」。同一份报告内,球包在 Web 是一级、在 iPhone 是设置项、在自家频率表里是低频——三者互斥,且违反其引用的 Master Spec 规则 8「三端共享语义」。球包(个人球杆距离模型)确实是差异化资产,可以为它辩护一级地位,但必须给出「为什么违反频率原则」的显式理由并三端一致,而不是无声打破自己刚立的规则(CONFIRMED 矛盾存在;球包最终层级为 PRODUCT-HYPOTHESIS,两个方向都可辩护)。
2. **对旧 Watch 宪法采取了「连坐否决」,丢掉了至少三条比新报告更好的条款(最强的三条如下,完整清单见 §6)**:计分页预填已侦测杆数+来源行(对账语义)、「记上一洞?」小签(温和跨洞提醒)、「四问门」设计治理机制。新报告 §17「继续有效」清单没有任何一条来自两份 2026-07-10 Watch 文档,这不是审慎,是误伤(CONFIRMED)。
3. **8 秒自动记杆的否决过于粗糙(对旧 spec 的第二处过度否决)。** 新报告 §8.4.6 把宪法条款概括为「8 秒后把推荐杆静默写成事实」加以否决。但原文([watch-control-spec](../superpowers/specs/2026-07-10-watch-control-spec.md) 第 50 行)是:浮层已弹出(记杆意图已确立)、8 秒无操作、按推荐记入**并标「自动」、事后可改**——有标记、可审计,且它解决的是新报告自己也承认的手套/雨天场景(宪法第 20 行:「湿手/手套时点按会失效,读数不能失效」)。新报告的替代方案(§8.4.5「未确认球杆保持 unknown」)在手套天意味着整场球杆全是 unknown,个人球杆模型这一核心资产在雨天颗粒无收。正确的裁决不是二选一,而是第三条路:超时按推荐**预填并标 pending**,不进统计,洞末计分对账时一并确认——既保零触屏流程,又不污染统计(PRODUCT-HYPOTHESIS,需手套真机测试)。

### 2.3 必须修正的结论(摘要,详表见 §7)

| 新报告结论 | 修正 |
|---|---|
| `history_overview/round_detail/drilldown`「直接复用」 | 改为「**接口形状直接复用,数据源必须随 ledger 迁移**」:三者底层仍走 `load_history_data_for_mode` 全量文件读取(`server_v2/history_overview.py:255-257`;验收补读加固:`server_v2/history_round_detail.py:20,27`、`server_v2/history_drilldown.py:21` 同样如此),把它们标成「直接」会让实施者误以为存储迁移与它们无关 |
| 状态机四态 + explicitDiscard 完备 | **缺「中途终止但保留数据」路径**:打 7 洞下雨回家,既非 finished 也不该 discard;且未回答「一个玩家能否有多个 active round」——若唯一 active,开新局将强迫用户对旧局做 finish/discard 二选一,正是最易丢数据的时刻(CONFIRMED 缺口) |
| Watch「一份 outbox + 两个 transport(手机中继/直连云端)」 | 双活 transport 引入跨通道去重与选路复杂度;现状直连云端仅在 `confirmFinish` 使用(`WatchRoundModel.swift:284-298`)。应明确 v1 主通道 = `transferUserInfo` 手机中继,直连云端仅为结束时兜底(MODIFY) |
| 冻结五页/3+2 直接实施 | 冻结无时限、无退出条件。若三方案原型验证迟迟不排期,冻结=无限期停滞,而现有单根 container 是可用的。应加「N 周内未完成原型验证则按现有 container 结构演进」的退出条款(MODIFY) |
| 五类 AI 报告「退出主流程,合并为页面级解释」 | 同意退出主导航,但需补:解释结果仍要**持久化且可回溯**(「去年 AI 怎么说」是复盘记忆的一部分,与 append-only 哲学一致);新报告只说了入口消失,没说产物去哪(MODIFY) |

---

## 3. 第一部分:设计合理性与备选方案比较(对新报告 12 个关键问题的独立裁决)

### 3.1 「备战→打球→复盘」生命周期是不是最佳组织?

**裁决:是主组织的最佳候选,但新报告的论证有两个缺口(ACCEPT with modifications)。**

- 同意的理由(独立复核):方案 A(竞品对标)的恶果有实证——产品手册 §3 就是一张 Garmin 功能对照表,B1–B9 全部以「Garmin 有」为立项理由;方案 C(AI 中心)与 F-05(中文事实绑定完全失效,`ai_caddie/reports/reports.py:157-201` 全英文关键词表,CONFIRMED 仍在 HEAD)同时存在时是危险的:把不可验证的层放到中心。
- 缺口一:**「不打球的日子」的任务没有位置。** 用户天天看的可能是统计趋势与球包,而非某个生命周期阶段;新报告 §5.3「所有主产品功能必须明确服务三条主流程,无法归入的默认进入实验/诊断/删除候选」是一刀切——球包正是反例(横切三个阶段),这也是它 IA 自相矛盾的根源(见 §2.2.1)。修正:承认存在少数「横切资产」类目(球包、账户),它们服务全部三条主流程,归属由频率而非流程决定。
- 缺口二:**阶段间数据契约未定义。** §3 的闭环图有「备战→场中」箭头,但备战的产出物(哪几洞的打法结论?用户改过的目标线?)如何成为场中 decision 的输入,全文没有回答。Master Spec 的 decision inputs 列了 `historical hole/course patterns` 与 `manual notes`,唯独没有「备战时用户自己定的计划」。没有这个契约,「备战」退化为「阅读」,生命周期组织的核心卖点(闭环)不成立(CONFIRMED 缺口;修补方案见 §5)。

### 3.2 Web 复盘与统计应否合并?球包一级是否成立?

**合并:ACCEPT(CONFIRMED)。** 现状证据:`navigation.ts:26-49` 把 rounds/holes/issues 分到 review、把 history(趋势)/courses 分到 stats——「强弱分析」在复盘而「趋势总览」在统计,两者都是「我打得怎么样」,分界线是任意的;iPhone 首页同构地出现「历史复盘/数据统计/上一场」三个相邻入口(`RoundHomeView.swift:228-239,245-267`)。但要诚实:合并的收益是**心智归一**,不是选择变少——合并后复盘二级有五项(总览/球局/趋势/强弱/球场),总目的地数不变。另外 `App.tsx:162` 确认整个 Web 仍由 `activePage` React state 驱动、无 URL 路由,合并 IA 若不同时上真路由,深链/回退/分享仍是残的——新报告 §6.2 已指出,应与 IA 合并同 PR 处理。

**球包一级:见 §2.2.1,新报告需自我修正后才能裁决。** 我的倾向:Web 一级保留「球包」可辩护(它是唯一承载「个人球杆模型可信度」的页面,是产品论文的一半),但必须同步说明 iPhone 为何下沉到设置(平台差异理由:手机场景球包主要在选杆时被动消费),并把这个差异写进跨端语义文档(PRODUCT-HYPOTHESIS)。

### 3.3 iPhone Hub 应否保留?记录语义是否足够?

**Hub 保留:ACCEPT(CONFIRMED)。** `RoundHomeView.swift` 的结构(进行中卡置顶 196-207、打球主磁贴 209-213、三磁贴 217-240、上一场 245-267、工程项收进设置 sheet 282-329)已接近新报告 §7.4 的目标,收敛「三入口合一」即可,无需重做。

**记录语义:拆分方向 ACCEPT,但「不足够」——缺对账规则(本评审最重要的新发现之一)。** 新报告定义「记这一杆」(逐杆)与「完成本洞」(确认总杆/推杆/罚杆)两个动作,却没有回答:**逐杆流数到 5 杆、用户洞末确认 6 杆时,谁赢?差异如何呈现?未记录的那一杆要不要补?** 这不是边缘情况——只要用户漏记一杆(每轮必然发生),两个数就分叉。旧宪法恰好有答案:计分页「自动预填已侦测杆数」+「已记 N 杆」来源行([watch-control-spec](../superpowers/specs/2026-07-10-watch-control-spec.md) 第 37 行;[watch-design-system](../superpowers/specs/2026-07-10-watch-design-system.md) §2.4「你这洞我数到 X 杆就长这样,不弹窗」)。新报告的 ScoreHole sheet(§8.3)没有预填对账语义。**修正:总杆确认值为权威(A 级事实),逐杆流为证据(B 级);确认值≠逐杆数时不阻塞保存,但写入 `strokesUnaccounted` 差额,复盘时提示补杆——预填规则从旧宪法原样继承**(CONFIRMED 缺口 + 具体修补)。

另外确认:假底栏必须删(`LiveHoleComponents.swift:570-591`,注释自认「Visual language only」的五标签假 tab bar,CONFIRMED);`CurrentHoleView.swift` 超 1200 行承担九种职责,拆分正确(CONFIRMED)。

### 3.4 Watch 三方案(独立对比,不迎合新报告)

按用户要求逐维独立判断。前提事实:**五页横滑从未实现**;现有生产 Watch 是 `WatchRoundContainerView.swift:39-137` 的 `switch model.screen` 单根 hub(home 根 + holeMap/menu/scorecard/holeSelect/scoring/finishing 六个态),加一条 legacy 单洞 companion 路径(`AICaddieWatchApp.swift:42-65`)。

| 维度 | ①五页横滑(宪法) | ②3+2 | ③单根 Play + sheet/push(新报告首选) | 判定依据 |
|---|---|---|---|---|
| 看距离(30–60 次/轮) | 抬腕即家页 | 同 | 同 | 三者同分;真正决定读距速度的是 §8.5.1 的 3 秒验收,与导航无关(CONFIRMED) |
| 记杆(30–60 次/轮) | 角标按钮→选杆浮层 | 同 | 大按钮→ShotCapture sheet | **三方案在此维度同构**(都是按钮+浮层),记杆体验的差异由浮层设计决定,不由顶层导航决定(CONFIRMED) |
| 计分(9–18 次/轮) | 右滑一页 | 右滑一页 | 点「计分本洞」→sheet | 一次横滑 vs 一次点按成本相当;①②的真实代价是**计分页作为常驻兄弟页参与抬腕恢复**,可能抬腕落在计分页(NEEDS-VALIDATION,见下「抬腕」行) |
| 地图手势(拖旗/点测距/点障碍) | 顶层横滑与地图点按/拖动共存,旗靠近屏缘时拖旗起手与翻页手势竞争 | 同①(地图仍是分页之一) | **地图所在根页无横滑,手势独占** | ③有结构性优势(CONFIRMED);但幅度未知——宪法已用「拖只从旗柄开始」缩小冲突面,冲突残余量必须真机量化(NEEDS-VALIDATION) |
| 表冠 | 每屏一轴;根页=沿洞轴 | 同 | 同(旗/障碍/layup 停点) | ③的表冠设计实质就是宪法球道图页的轴换名;三者无差(CONFIRMED)。注意现状反面教材:`WatchHoleMapView` 画着「转表冠缩放」指示(229-243 行)而全 target **零** `digitalCrownRotation` 绑定(grep 证实)——无论选哪个方案,表冠必须真接 |
| 手套/雨天 | 表冠+一个大按钮走全程;8 秒自动兜底 | 同① | 表冠+大按钮;球杆保持 unknown | ①在雨天球杆数据保全上**优于**③现文;③需按 §2.2.3 的 pending 预填方案补齐(NEEDS-VALIDATION 手套实测) |
| AOD/抬腕 | 宪法:「抬腕回来必须是离开时的样子」(反模式 2) | 同 | 新报告:「抬腕应稳定回到当前球洞上下文」(§8.2) | **两个互斥原则,双方都没给证据**。watchOS 系统预期是前者,Garmin 用户预期是后者。这是三方案对比里唯一真正的哲学分歧,必须列为真机 A/B 项(NEEDS-VALIDATION) |
| 发现性 | 靠记忆左右页序;菜单在最左要滑两次 | 略好 | 显式按钮+系统 sheet,首日可发现性最好 | ③优(CONFIRMED 对新用户);老用户横滑肌肉记忆可能更快(NEEDS-VALIDATION) |
| 工程成本 | 需新建 TabView 分页壳 | 需新建 | **与现有 `WatchRoundContainerView` 同构,增量=把 screen switch 改为 sheet/NavigationStack + 补 ShotCapture** | ③最低(CONFIRMED)——这是新报告漏掉的、支持自己首选项的最强论据 |

**推荐:③作为首选候选进入原型对比,与新报告一致;但附加三条新报告没有的约束:**
1. 原型对比的核心变量收窄为两个真问题——**抬腕恢复策略**(当前洞 vs 离开时)与**地图手势冲突残余量**;其余维度纸面已可判定,不必陪跑全量测试。
2. 视觉规则书(黑药丸/ScoreChip 形状冗余/topo 色板/文字优先,[watch-design-system](../superpowers/specs/2026-07-10-watch-design-system.md) §1)与导航正交、已真渲验证,**显式列入「继续有效」**,不随五页连坐。
3. 冻结带退出条件(§2.3)。

### 3.5 Garmin owner 是否应为 v1 主 persona?

**ACCEPT,但必须加一条硬约束,否则会错误牺牲家庭成员(CONFIRMED 风险)。** 支持:本产品的差异化(长期记忆+个人球杆模型)只对有历史数据的人立即成立,把首个深度体验对准 Garmin owner 是对的。风险:工程现实是成员路径已经断裂——成员备战搜球场必 403(Opus F-04,`server_v2/main.py:288` vs 成员放行表漂移)、成员 Garmin 绑定不存在(产品手册 A1「highest-leverage fix」)、Web 成员自绑前后端契约断开(Codex P1-WEB-02)。「主 persona」的措辞在这种现实下极易被读成「成员可以再等等」。约束:**成员完成搜索/开局/备战/记分/同步的一级任务完整性是 v1 出货条件**(新报告 §14.2.4 已有此意,应升格为 persona 定义的一部分,而非第一优先级里的一项)。「家庭成员是否真的需要个性化球童」无任何用户数据(PRODUCT-HYPOTHESIS)。

### 3.6 「确定性 decision + LLM 只解释」是否合理?五类报告退出是否过度收缩?

**前者 ACCEPT(CONFIRMED)且有新证据加固:LLM 连「解释」层都还锁不住。** `ai_caddie/reports/reports.py:157-201` 的防幻觉校验全英文而生产语言是中文(F-05,HEAD 仍在);`ai_caddie/caddie/decision.py:411-421` 的决策解释校验是英文+英文 prompt(自洽,但覆盖类目远少于 prompt 声称的限制)。在这种校验成熟度下,给 LLM 任何事实权都是错的。
**后者 MODIFY:退出主导航正确,但「收缩」要止于入口,不能及于产物。** 见 §2.3 第五行:解释必须可持久化、可回溯、可引用 fact IDs——否则丢掉了报告系统唯一真实的用户价值(时间维度的记忆)。

### 3.7 CoursePack / PostgreSQL ledger / object storage / 页面级投影

**四者方向全部 ACCEPT(与两份工程报告独立收敛)。** 补三点:
1. CoursePack 的**静态/动态边界未划**:旗位(每日变化)、拖旗预览、天气都不属于版本化静态事实;「一轮球固定 CoursePack 版本」(§11)需限定为几何/route/高程,并定义动态层的旁路(CONFIRMED 缺口,小)。
2. 页面级投影方向正确的直接证据:`server_v2/history_overview.py:218-257` 已是干净的 `HistoryOverviewResponse` 投影,而全量 `build_history_stats`(`ai_caddie/history/history_stats.py:3819-3858`)一次构造 13 个维度、`App.tsx:137-140,173-175` 自述 11–20MB——现状本身就是「先有巨石、后打补丁投影」的教训。
3. 投影列表(§9.3 六个端点)与现存三文件高度重合——这是「从现状反推」,不影响正确性,但正式 spec 应从**页面需求**正推一遍,验证六个端点是否恰好、有无缺(如 `/bag` 投影就不在列表里,而球包被推荐为一级入口)。

### 3.8 Watch standalone / AutoShot / Vision / WebGL 3D / 风力与 expected-strokes 后置

**全部 ACCEPT(CONFIRMED),各有独立证据:**
- AutoShot:[auto-swing spec](../superpowers/specs/2026-07-05-auto-swing-detection.md) 已被 Codex+Gemini 双评审降格为「受控验证假设」,阶段-1 一键记杆先行——新报告与之一致,无需再辩。
- Vision:XR-04(EXIF GPS 原样落盘并可能外发)未修,后置正确。
- WebGL 3D:design-system §八本就只允许「Web 备战大屏」用 3D,新报告进一步收紧为暂缓——2D topo(0.45s 渲染实测)已完成「看清打法」任务,3D 无已证增益(CONFIRMED)。
- expected-strokes:**现状比新报告描述的更失控**——未校准的期望杆数已经在三端消费者界面上:Watch `WatchCaddieOptionsView.swift:53-55`(「期望 %.1f」)、iOS `CaddiePlanView.swift:71-72`(expectedStrokes/expectedStrokesDelta 字段)。撤下是对的;注意设计系统只封印了百分比与 ±误差带([watch-design-system](../superpowers/specs/2026-07-10-watch-design-system.md) §1「64%、±18 判死」),没封期望杆数——契约测试禁词表应同步扩充。
- Watch standalone:新报告 §8.3 区分「场中离线可用」与「完全独立产品」是关键洞察;现状 `startPracticeRound`(`WatchRoundModel.swift:158-167`)+ watch-auth 转发已是半独立,冻结扩张、保留现有,合理。

### 3.9 roundSyncStatus × reviewStatus 正交是否足够?

**不足够:缺一个状态、缺一个正交维度;其余答对(部分 REJECT)。**
- **缺「suspended/abandoned-with-data」状态**(CONFIRMED,见 §2.3 第二行):必须回答多局并存规则。建议:允许多个非 active 局存在,`active` 全局唯一;新开局时旧 active 自动转 `suspended`(数据完整保留、可恢复可结束),而不是强迫用户当场 finish/discard。
- **缺正交的对账维度**:Garmin 表与手动记录同场并存是产品既定场景(Web spec §5.4「若 Garmin 表同时记了同一场,自动合并,不重复计数」;产品手册也载明)。自动合并失败/歧义时需要可见状态与人工裁决入口——但它**不应挤进 reviewStatus 的档位**:对账需求是数据事实,不是复盘进度,已 reviewed 的球局在 Garmin 数据晚到时同样会再次需要对账。正确做法是增加第三个正交维度 `reconciliationStatus: none / needed / resolved`,与 roundSyncStatus、reviewStatus 互不阻塞(CONFIRMED 缺口)。
- **不需要「recovered」「conflict」独立状态**:崩溃恢复回 active 即可;跨端字段冲突由 server sequence + append-only correction 定序解决,状态机不必显式化(同意新报告的隐含立场)。
- **reviewStatus 两档(pending/reviewed)够用**:correction 逐条 append 生效,不存在「半确认」原子性问题;对账不占用 review 档位(见上一条的正交维度)(ACCEPT)。

### 3.10 新报告是否只是重述工程 bug?

**不是。** 它的主体(IA、语义、状态机、AI 边界)是真设计层内容,与工程报告互补而非重复。但它遗漏的设计层问题见 §5(缺失关键问题清单)——其中对账语义与阶段数据契约两条,分量不低于它已写出的任何一节。

### 3.11 多套决策规则的「可能不同」应升级为「确认不同」

新报告 §10.2 说各套规则的风险常数「可能不同」。实测:`ai_caddie/courses/course_prep.py:542-552` `_candidate_routes` 风险分 = 0/1/3(有水或沙时 attack=3);`ai_caddie/caddie/mobile_live.py:1083-1133` `_offline_caddie_options` base_risk = 0.8/1.5/3.0 再加 near_risks×1.5 + line_risks×1.0;`ai_caddie/caddie/decision.py` 的选择规则又是「stock 与最安全选项风险差 ≤1 则选 stock」。**三套常数体系互不兼容,同一洞在备战页、离线包、在线决策三处可能给出不同排序**(CONFIRMED)。合并为单一带 `policyVersion` 策略的优先级应从「第三优先级」提前评估——它直接伤害「同一事实三端一致」的验收标准(§16 备战 2)。

### 3.12 频率表与「3 秒」验收

频率表方法论正确;数字自我声明为验收目标而非研究结论,诚实(ACCEPT)。补一条:频率表缺「找球/走路间隙看上一杆距离」这一高频微任务(宪法「上一杆药丸」条款覆盖了它,`WatchHoleMapView` 的 lastShot 参数也已实现)——收敛 IA 时别把它当装饰删掉。

---

## 4. 第二部分:工程复用矩阵复核

对新报告 §13.2 矩阵逐类抽查后的修订意见(未列出的行 = 抽查未发现问题,ACCEPT):

| 资产 | 新报告评级 | 我的裁决 | 依据 |
|---|---|---|---|
| Garmin connector / 快照 / 映射 | 修后复用 | **ACCEPT** | 与 P1-BE-02/03(部分失败吞掉、negative cache 永不重试)一致,修复清单已在工程报告 |
| `history_overview/round_detail/drilldown` | 直接复用 | **MODIFY**:形状直接复用、数据源随 ledger 迁移 | `server_v2/history_overview.py:255-257`、`server_v2/history_round_detail.py:20,27`、`server_v2/history_drilldown.py:21`(验收补读)三处均走 `load_history_data_for_mode` 全量文件加载;见 §2.3 |
| 历史统计公式 | 修后复用 | **ACCEPT**,但把 F-10(差点混量纲)与 XR-02(9+9 rating 污染)列为「修后」的显式前置——两者都直接改门面数字 | `ai_caddie/history/history_stats.py:544-564`(Opus 引用,本次未复读该段,采信两份报告交叉确认) |
| append-only correction 语义 | 语义复用、实现重构 | **ACCEPT**,补充:`RoundCorrectionRequest`(`server_v2/models.py:474-486`)至今无 `club/lie` 字段,XR-01 的 addShot 丢字段未修——「修后」的第一刀应是它 | CONFIRMED(本次复核 HEAD) |
| geometry sync / `hole_render` topo | 直接复用 | **ACCEPT** | `ai_caddie/geometry/hole_render.py:25-45` 帧/投影统一,三端 overlay 靠构造对齐,是全库质量最高的资产之一 |
| `geometry_evidence` | 淘汰重构 | **ACCEPT** | XR-03 证明其 polygon 读侧与真实写侧(centroid/bbox、positions/faces)schema 断裂;`ai_caddie/geometry/geometry_evidence.py:165-180` 的 surface 行读取兼容层也印证了「平行世界」判断 |
| 多套 caddie 规则合并 | 重构复用 | **ACCEPT 并加急**(§3.11:常数已确认互斥) | course_prep vs mobile_live vs decision 三套常数 |
| LLM provider / fact bundle | 修后复用 | **ACCEPT** | F-05/XR-06 前置;provider 抽象本身质量可用(验收补读整读 `ai_caddie/llm/llm_providers.py` 全 709 行:五 provider、配置 fail-fast、`redact_secret_text` 脱敏 65-82 行、OAuth 过期 skew 处理 391-405 行,与 Master Spec 要求的 provider 集合一一对应) |
| JSON Schema / contract tests | 修后复用 | **ACCEPT** | `tests/test_mobile_contracts.py:34-81` 双校验器并存,F-17(ready package 只被弱校验器盖)与残缺助手须删;4 个 schema(`mobile/contracts/`,验收补读全部整读)是三端唯一共同事实,保。补一条整读后的直接印证:`live_round_package.schema.json` 实际使用 `$ref/$defs`(720-794 行)、`additionalProperties:false`、`pattern`(634 行)——恰是弱校验器忽略的特性,F-17 的风险面属实;`watch_round_state.schema.json:251-254` 要求 `score ≥ 1`,而 Swift 侧以 `score: 0` 作「未记分」哨兵(`WatchRoundModel.swift:117-119,163`),是 P2-CON-02 类契约漂移的又一实例,也从契约层佐证「记分语义不干净」 |
| LiveRoundPackage / Watch state / event schema | 修后复用(收敛条件字段、unknown 兼容、版本) | **ACCEPT** | 验收补读整读四 schema 后确认:`watch_input_event.schema.json:32-35` 与 `live_round_event.schema.json:41-54` 的 kind 枚举均封闭、无 unknown 通道(XR-05 的契约层根源);`live_round_package.schema.json` 条件字段众多(preparationMode/geometryEnsure 等),「收敛」判断成立 |
| `LiveRoundEventBuilder` 与离线包准备链 | 修后复用 | **ACCEPT** | 接统一 RoundEvent 与 CoursePack 的方向正确 |
| event ID / sequence / cursor / revision 原语 | 修后复用 | **ACCEPT** | 协议概念保留、迁入事务 ledger,与 Codex §8.2 六不变量一致 |
| Apple auth / identity / player-scoped 隔离 | 修后复用 | **ACCEPT** | 隔离靠路径构造(`evidence_root`)是全库最好的安全设计;「修后」= F-01/02/03/11 + F-19 的入口正则收口 |
| iOS `OfflineStore` 架构 | 修后复用 | **ACCEPT** | 文件形态可保;F-06(换行终止符,`OfflineStore.swift:225-240` 复核仍在)、P0-IOS-01(sync marker 定义 pending 边界,272-289 行复核仍在)是修复清单 |
| iOS Hub / StartRoundView / 地图组件 | 直接或修改复用 | **ACCEPT** | `StartRoundView.swift:35-85` 的默认选场/选台逻辑成熟 |
| Web AppShell / Sidebar | 直接或修改复用 | **ACCEPT**:壳与门控(`AppShell.tsx:35-72`)干净;「修改」= 接真 URL router + IA 重组 | |
| Web 诊断门控 | 直接复用 | **ACCEPT** | 组件级自隐(SourceRefs)+ `AppShell` owner 开关,构造式,好 |
| 设计快照与契约测试 | 直接复用(增 baseline) | **ACCEPT**,注意「增 baseline」实质是修(P3-IOS-01:现在只产图不比对),别按字面理解为零工作 | |
| 文件型权威数据 → PG ledger + 对象存储 | 逐步替换 | **ACCEPT** | 与 Codex §8、Opus 元建议三方收敛 |
| Watch store/sync | 重构复用(一份 WAL/outbox + 两 transport) | **MODIFY**:主通道明确为 transferUserInfo 中继,直连仅结束兜底(§2.3) | `WatchSyncClient.swift:172-178`(非 write-ahead)、180-189/229-238(无锁 RMW)、261-303(仅 sendMessage);`WatchRoundStore` 本体(75-101 行)简洁可保 |
| Watch 五页/3+2 分页壳 | 冻结 | **ACCEPT + 补充**:所谓「分页壳」在生产中不存在,真正要冻结的是**按五页 spec 新开工**;现有 container 是单根结构,应作为候选③的迁移基座而非冻结对象 | `WatchRoundContainerView.swift:39-137` |
| Watch legacy 单洞 + 独立局双产品线 | 淘汰合并 | **ACCEPT** | `AICaddieWatchApp.swift:42-65` 双路径互斥,P1-MOB-01 确认手机全洞状态从未 seed 进 roundModel |

**矩阵未覆盖、应补入的一行:** `WatchLocationProvider.swift`(83-89 行无 age/accuracy 过滤直接发布 fix;19-22 行自认无 workout 会话)——评级应为「修后复用」,它是「GPS 差冻结最后可信点」降级规则(§11)的实现载体,现状做不到。

---

## 5. 新报告缺失的关键问题(按分量排序)

1. **逐杆流 × 洞分确认的对账语义**(Critical,§3.3):谁是权威、差额怎么呈现、预填规则——旧宪法有解,新报告丢了。
2. **生命周期阶段间的数据契约**(Critical,§3.1):备战产出物的 schema 及其进入场中 decision 的通路;没有它,「闭环」不闭。
3. **多球局并存 / suspended 语义**(Critical,§3.9)。
4. **Garmin 对账维度(reconciliationStatus)在状态模型中的位置**(Important,§3.9)。
5. **家庭数据可见性模型**(Important,PRODUCT-HYPOTHESIS):owner 可否看成员球局、成员间是否互见、未成年成员的代管边界——新报告用「家庭管理属于账户能力」一句带过,但这是权限**设计**问题,不是权限**实现**问题;工程报告只保证了默认隔离。
6. **推杆/总杆包含关系的跨端书面定义**(Important):strokes 含 putts 是 Garmin 语义,三端事件(`submitEvents` 的 score/putt 分事件、Watch `saveActiveHole` 同构)都隐式依赖它,但没有任何 spec 写死;理解错会使手动记分系统性错杆,是数据正确性风险而不止文案问题(PRODUCT-HYPOTHESIS 其发生率,CONFIRMED 其无定义)。
7. **解释产物的持久化去向**(Important,§3.6)。
8. **备战不绑「下一场」的 D6 洞察未显式继承**(Minor):[Web spec](../superpowers/specs/2026-06-09-web-product-redesign-design.md) D6 的场景理由(常备的不是下一场)应写进新 North Star,防止未来又有人做「下一场」绑定。
9. **「同日」9+9 合并的时区定义**(Minor):按本地日还是 UTC 日合并,影响统计正确性,设计层从未定义。
10. **CoursePack 静态/动态边界**(Minor,§3.7)。

---

## 6. 旧 spec 中优于新报告、不应连坐否决的条款

| 旧条款 | 出处 | 保留理由 |
|---|---|---|
| 计分页预填已侦测杆数 + 「已记 N 杆」来源行 | watch-control-spec 第 37 行;watch-design-system §2.4 | 新报告对账语义的现成答案(§3.3) |
| 「记上一洞?」小签(GPS 不跳洞但温和提醒) | watch-control-spec 第 52 行 | 新报告只留了禁令(不自动跳洞),丢了补救通路;漏记洞分是高频真实错误 |
| 「四问门」(新屏先答:轴?点按?进出?大字?) | watch-control-spec 第 85 行;design-system §5.3 | 可操作的设计治理闸门,与五页无关;新报告 §18 的约束都是原则性的,缺这种硬门 |
| 唯一视觉系统(黑药丸/ScoreChip 形状冗余/topo 色板/文字优先/禁词进契约测试) | watch-design-system §1、§5 | 已真渲验证、与导航正交;新报告 §17「继续有效」未列,造成实施者不确定性 |
| 上一杆药丸(实时距上一杆,找球用) | watch-design-system §2.3 | 高频微任务(§3.12),IA 收敛时易被误删 |
| 备战不绑定「下一场」(D6) | web-redesign spec §3 D6 | 真实使用洞察,应进 North Star(§5.8) |
| 「洞分由所记录的杆自动累计,收洞确认推杆」的计分哲学 | web-redesign spec §5.4 | 与新报告「完成本洞确认总杆」不是同一模型;两者的取舍(自动累计 vs 显式确认)应在对账语义(§3.3)里一并裁决,而不是被无声替换 |

---

## 7. 对新报告的逐项 verdict 总表

| 新报告条目 | verdict | 备注 |
|---|---|---|
| §1 核心方向成立、不推倒重来、strangler 迁移 | **ACCEPT** | CONFIRMED |
| §2 频率驱动层级 + 2.1 频率表 | **ACCEPT** | 补横切类目与「上一杆」微任务;数字 NEEDS-VALIDATION(已自我声明) |
| §3 方案 B 生命周期 | **ACCEPT(修)** | 补阶段数据契约(§3.1) |
| §4 撤销「required 不可删」「一个不删」「定稿=最优」 | **ACCEPT** | 三处原文行号复核成立 |
| §5.2 Garmin owner 主 persona | **ACCEPT(加硬约束)** | 成员一级任务完整性 = 出货条件(§3.5) |
| §5.3 三主流程 + 「无法归入即删除候选」 | **MODIFY** | 承认横切资产类目(§3.1) |
| §6.2 Web 四项批评(拆分/实战残留/控制台/无 URL/虚假承诺) | **ACCEPT** | 全部有代码实证(§2.1.2) |
| §6.3 推荐 Web IA(球包一级) | **MODIFY** | 内部矛盾须先解决(§2.2.1) |
| §7 iPhone(Hub 保留/语义拆分/删假底栏/拆 CurrentHoleView) | **ACCEPT(补对账)** | §3.3 |
| §7.3 校对不阻塞上传、correction 追加 | **ACCEPT** | CONFIRMED 正确 |
| §8.1 冻结五页与 3+2 | **ACCEPT(加退出条件)** | §2.3 |
| §8.2 3+2 非最优的五条理由 | **ACCEPT 其四,MODIFY 其一** | 「计分不应与距离同级」成立;「抬腕稳定回当前洞」与旧宪法原则冲突未被识别,NEEDS-VALIDATION(§3.4) |
| §8.3 单根页候选 IA | **ACCEPT 为首选候选** | 补同构性论据 + 视觉系统显式保留(§3.4) |
| §8.4 操控规则 10 条 | **ACCEPT 其九;第 6 条(8 秒)MODIFY** | 第三条路:pending 预填不进统计(§2.2.3);第 5 条与第 6 条须与对账语义合并设计 |
| §8.5 验证场景 | **ACCEPT(收窄)** | 核心变量收窄为抬腕策略+手势冲突(§3.4) |
| §9.1–9.2 架构与 Garmin 边界 | **ACCEPT** | 与工程报告收敛 |
| §9.3 stats 投影 | **ACCEPT(补正推验证 + /bag)** | §3.7 |
| §9.4 CoursePack | **ACCEPT(补动态边界)** | §3.7 |
| §9.5 缓投 WebGL 3D | **ACCEPT** | CONFIRMED |
| §10 AI 职责边界 | **ACCEPT** | LLM 解释层校验现状(F-05)加固此结论 |
| §10.5 报告退出主流程 | **MODIFY** | 产物须持久可溯(§3.6) |
| §11 四级可信度 + 降级 | **ACCEPT** | 良好;WatchLocationProvider 是其未列的实现缺口(§4 末) |
| §12 状态机 + 正交 reviewStatus | **MODIFY** | 缺 suspended 状态与正交 reconciliationStatus 维度(§3.9) |
| §13 复用矩阵 | 逐行见 §4 | 两行 MODIFY,余 ACCEPT |
| §14–15 修改建议与分期 | **ACCEPT(两处调序)** | caddie 规则合并提前评估(§3.11);对账语义并入 Stage 0 状态机设计 |
| §16 验收标准 | **ACCEPT(增补)** | 增:对账差额可见、成员正向 200 全覆盖(Opus G4)、解释持久化 |
| §17 覆盖关系 | **MODIFY** | 「继续有效」补 watch 视觉系统、四问门、D6、预填对账(§6) |
| §18 实施者约束 | **ACCEPT** | 建议吸收「四问门」式硬闸 |
| §19 最终结论(核心定义 + 「先设计收口、再接强资产」) | **ACCEPT(修)** | 方向与「不补页面、不推倒、先收口」三段式全盘同意;North Star 一句话按 §10 增补「阶段产出互为输入、对账先于解释、诚实降级」三处措辞 |

---

## 8. 产品设计发现分级(本评审新增,非工程 bug 重述)

**Critical**
- C1 逐杆×洞分对账语义缺失(§3.3;修补方案已给)。
- C2 生命周期阶段间数据契约缺失,备战→场中断链(§3.1)。
- C3 状态机缺 suspended/多局并存规则,新开局时刻是丢数据高危点(§3.9)。
- C4 三套决策常数互斥,同一洞三处建议可能矛盾,直接违背「同一事实三端一致」(§3.11)。

**Important**
- I1 新报告球包层级三处自相矛盾(§2.2.1)。
- I2 未校准 expectedStrokes 已在三端消费者界面展示(`WatchCaddieOptionsView.swift:53-55`、`CaddiePlanView.swift:71-72`),且已是跨端契约一等字段(验收补读:`watch_round_state.schema.json:106-108,216-218`、`WatchRoundState.swift:150`、`WatchCaddieOption.expectedStrokes` 52 行);契约禁词表未覆盖(§3.8)。
- I3 Watch「转表冠缩放」指示无任何表冠绑定(grep 零命中)——虚假 affordance 与 iPhone 假底栏同性质,应并入同一条「虚假 affordance 清零」验收。
- I4 复盘图例在无真实当时决策的情况下把 prep route 标注为「球童建议线」(`ReviewHoleCanvas.tsx:57-60,114-125`):画的是事后几何推荐路线,不是该轮当时的 decision——图例应改为「推荐路线(非当时建议)」或接真 decision audit(诚实性,与 §6.2「虚假承诺」同类但新报告未点名此处)。
- I5 正交对账维度(reconciliationStatus)缺位(§3.9)。
- I6 家庭可见性模型未设计(§5.5)。
- I7 解释产物持久化去向未定义(§3.6)。
- I8 推杆/总杆包含关系无跨端书面定义(§5.6):三端事件隐式依赖「strokes 含 putts」的 Garmin 语义而无 spec 写死,理解错会使手动记分系统性错杆——数据正确性风险,故列 Important。

**Minor**
- M1 「同日」合并的时区定义缺失(§5.9)。
- M2 CoursePack 静态/动态边界(§3.7)。
- M3 频率表漏「看上一杆距离」微任务(§3.12)。
- M4 D6(不绑下一场)未显式继承(§6)。

---

## 9. 第三部分:具体修改建议与分阶段顺序(对新报告 §14–15 的修订版)

**Stage 0(设计收口——在新报告基础上增补三件)**
1. North Star Spec 按新报告 §14.1 写,**并入**:对账语义(C1)、阶段数据契约(C2)、suspended 与多局并存规则(C3)、正交对账维度 reconciliationStatus(I5)、横切类目(球包/账户)与其三端层级的统一裁决(I1)、「继续有效」清单补旧 spec 条款(§6)。
2. 统一 `RoundEvent/RoundState/CoursePack/DecisionEvidence/FactRef` 定义时,同步定义 `PrepPlan`(备战产出物)与 `strokesUnaccounted`(对账差额)。
3. Watch 冻结令附退出条件与原型验证的两个核心变量(§3.4)。

**Stage 1(数据可靠性——与新报告一致,微调)**
- 按新报告 §14.2 全部执行;把「caddie 三套常数合并为单 policy」的**评估**(不一定是实现)提前到本阶段末,因为它决定 CoursePack/离线包的 schema。

**Stage 2(三端主流程)**
- Watch:两变量真机对比(抬腕策略、手势冲突)→ 胜出后按候选③在现有 container 上演进(不重建);ShotCapture sheet 实现时带 pending 预填方案进手套实测。
- iPhone:四动作语义 + 对账 UI + 删假底栏 + 拆 CurrentHoleView。
- Web:IA 合并与 URL 路由同 PR;沙盘进备战、记分改赛后补录(带持久草稿);I4 图例修正。

**Stage 3(引擎统一)**
- CoursePack(含动态边界)、policy 合并落地、页面投影(含 /bag)、manual/Garmin 统一学习闭环 + reconciliationStatus 裁决流程。

**Stage 4(实验)**
- 同新报告 §14.5,无修订。

**验收标准增补(在新报告 §16 之上):**
- 场中:洞末确认值≠逐杆数时,保存不被阻塞且差额可见、复盘可补。
- 赛后:同场 Garmin/手动双记录将 `reconciliationStatus` 置为 needed,并可一键裁决为 resolved。
- 工程:成员对每个应可用路由的**正向 200 测试**(Opus G4);未校准量(expectedStrokes/成功率)进入契约禁词测试。
- 备战:PrepPlan 能被场中 decision 引用并在赛后复盘中对照。

---

## 10. 最终 North Star 建议

新报告 §19 的表述基本可用,我建议的最终版(改动加粗):

> 用可信数据形成个人模型,赛前给出**可被场中引用的**计划、场中给出可执行建议**并可靠记下每一杆**、赛后**先对账再解释**结果,并把纠错反馈回下一次决策——**任何一步的产出都是下一步的输入,任何一步的缺失都有诚实的降级**。

三条不变量作为 North Star 的宪法级条款:①记录一经确认永不静默消失;②界面上没有一个不可用的控件、没有一个未校准的数字;③同一事实三端同值同源。

---

## 11. 正式 spec 前必须验证的任务/指标

| # | 验证项 | 方法 | 判定(通过线或决策门) | 标签 |
|---|---|---|---|---|
| V1 | 抬腕恢复策略:当前洞 vs 离开时页面 | 候选③原型两版本(抬腕恢复到当前洞主页 vs 恢复到离开时视图),同批用户各打真实 9 洞 A/B | **决策门**:「抬腕后 2 秒内读到本洞主距离」成功率两版本相差 ≥15 个百分点 → 采用高者;相差 <15 个百分点视为无实质差异 → 采用 watchOS 系统默认(恢复离开时视图)并终止该争议 | NEEDS-VALIDATION |
| V2 | 单根页地图手势 vs 分页横滑的冲突残余 | 原型对照,量化每 9 洞误触/误翻页次数 | **决策门**:单根页误触次数 < 分页方案的 50% → 记为③的已证结构优势;未达 → 该维度记为无差,方案取舍回落到发现性与工程成本两维(纸面均已判定利于③) | NEEDS-VALIDATION |
| V3 | 手套/雨天记杆:unknown 方案 vs pending 预填方案 | 真机手套实测,两方案各完整 9 洞 | **通过线**(pending 预填方案需同时满足):记杆动作完成率 = 100%;洞末确认后球杆归因率(非 unknown 比例)≥80%;误归因率(确认时需要改杆的比例)≤5%。任一不满足 → 采用 unknown 方案 | NEEDS-VALIDATION |
| V4 | 对账 UI:洞末差额提示的理解度 | 5 人可用性走查 | **通过线**:≥4/5 人在无提示下正确说出「差 N 杆」的含义并完成一次补杆操作;未达 → 改文案后重测;连续两轮未达 → 重做该交互 | NEEDS-VALIDATION |
| V5 | 抬腕 3 秒读距(直射阳光) | 真机 AOD/亮屏计时 | **通过线**:≤3s(新报告自设目标) | NEEDS-VALIDATION |
| V6 | 18 洞离线全程:杀进程/断网/低电,`finishedPendingSync` 数据零丢失 | 状态机测试 + 真机 | **通过线**:全场景零丢失 | CONFIRMED 需回归 |
| V7 | 三套 caddie 常数在同一洞的分歧幅度 | 离线对历史已打球场的全部洞并行跑三套规则 | **discovery 输出 + 升级门**:无 pass/fail;产出「推荐杆不一致洞占比」与「风险排序翻转占比」两个分布,作为 policy 合并 spec 的输入;若推荐杆不一致洞占比 >10% → policy 合并从 Stage 3 提前为 Stage 1 阻塞项 | CONFIRMED 可立即做 |
| V8 | 成员正向路由 200 全覆盖 | 声明式路由表 + 正向测试 | **通过线**:全绿 | CONFIRMED 可立即做 |
| V9 | 中文事实绑定否定用例 | 中文 narrative 注入测试 | **通过线**:fail-closed | CONFIRMED 可立即做 |
| V10 | 家庭成员对「owner 可见我的球局」的真实态度 | 与每位真实家庭成员一对一访谈 | **discovery 输出 + 决策规则**:无 pass/fail;记录每人在「owner 全可见 / 仅汇总可见 / 默认不可见」三档中的选择,直接决定产品默认值;任一成员不选「全可见」→ 默认改为成员自主开关 | PRODUCT-HYPOTHESIS |

---

## 12. 覆盖清单(实际读取/未读取,如实申报;含 2026-07-14 验收补读修正)

**文档(14/14 全读)**:主对象 2026-07-13 新报告(全文);2026-07-12 Opus 独立评审(全文,分两段);2026-07-11 交叉审查(全文);2026-07-11 全库审查(全文,分两段);Master Product Spec(全文);Web 重设计 spec(全文);Watch 操控规范(全文);Watch 设计系统(全文);AutoShot(全文);Decision Layer(全文);Course Prep On Device(全文);2026-07-03 设计系统(全文);产品手册(全文);USER_GUIDE(全文)。

**Web(10/10 实读)**:navigation.ts(全)、AppSidebar.tsx(全)、AppShell.tsx(全)、App.tsx(1-320 行:状态模型/boot/payload 注释;其余未读)、PrepPage.tsx(1-120 + 243-271 导出段)、ReviewWorkbench.tsx(1-100)、StatsDashboard.tsx(150-280:趋势图/散布椭圆/成绩构成)、RecordRoundPage.tsx(80-220)、CaddiePage.tsx(1-60 结构)、LiveSandbox.tsx(1-70 含单位契约注释)。另核对 ReviewHoleCanvas.tsx(全)、CorrectionsPage/ReportsPage(定向 grep)。

**iPhone(9/9 实读)**:AICaddieApp.swift(1-130 + 560-709:discard/handleEvent/sync/replay)、RoundHomeView.swift(全)、StartRoundView.swift(1-90)、CurrentHoleView.swift(590-740 选杆/结束段 + 1060-1200 submitEvents 段;全文 1200+ 行未逐行)、LiveHoleComponents.swift(540-619)、CaddiePlanView.swift(1-80)、OfflineStore.swift(190-330)、SyncClient.swift(300-420)、WatchEventBridge.swift(380-470)。

**Watch(11/11 实读)**:AICaddieWatchApp.swift(全)、WatchRoundModel.swift(全)、**WatchRoundState.swift(全 459 行,验收补读整读)**、WatchRoundContainerView.swift(全)、WatchRoundHomeView.swift(全)、WatchHoleMapView.swift(1-140 + 190-250)、WatchScoreHoleView.swift(全)、WatchCaddieOptionsView.swift(全)、WatchRoundStore.swift(全)、WatchSyncClient.swift(150-310)、WatchLocationProvider.swift(全)。另:全 target `digitalCrownRotation` grep(零命中,否定性存在检查)。

**后端/AI/契约(15/15 实读)**:ai_caddie/caddie/decision.py(380-490:解释/校验/审计)、ai_caddie/caddie/mobile_live.py(1083-1172 离线选项段;事件日志段采信两份工程报告的一致引用)、ai_caddie/courses/course_prep.py(495-575 策略/路线段)、ai_caddie/geometry/geometry_evidence.py(150-210)、ai_caddie/geometry/hole_render.py(1-70)、ai_caddie/history/history_stats.py(3800-3858 build 全量段;差点段采信 Opus+Codex 交叉确认,未复读)、ai_caddie/reports/reports.py(150-210 校验词表)、**ai_caddie/llm/llm_providers.py(全 709 行,验收补读整读)**、server_v2/main.py(265-354 授权表与中间件)、server_v2/history_overview.py(全)、**server_v2/history_round_detail.py(全 29 行,验收补读整读)**、**server_v2/history_drilldown.py(全 32 行,验收补读整读)**、server_v2/models.py(460-516:RoundCorrectionRequest 复核)、**mobile/contracts/ 四个 schema 全部整读(验收补读):watch_input_event.schema.json(全 140 行)、live_round_event.schema.json(全 235 行)、live_round_package.schema.json(全 795 行)、watch_round_state.schema.json(全 268 行)**、tests/test_mobile_contracts.py(30-100 双校验器)。

**验收补读小结(2026-07-14)**:8 个文件(WatchRoundState.swift、server_v2/history_round_detail.py、server_v2/history_drilldown.py、ai_caddie/llm/llm_providers.py、四个 contracts schema)全部完整 Read。补读**未推翻任何 verdict**;带来四处证据加固,均已并入正文:①§2.3/§4 history 投影「数据源须迁移」新增 `server_v2/history_round_detail.py:20,27` 与 `server_v2/history_drilldown.py:21` 直接证据;②§2.1.1 记录语义混合新增契约层证据(`live_round_event.schema.json:80-102` club 事件承载 decision/actualShot);③§8 I2 expectedStrokes 新增契约一等字段证据(`watch_round_state.schema.json:106-108,216-218`);④§4 契约行新增 kind 枚举封闭(XR-05 契约层根源)、F-17 风险面($ref/$defs/pattern 实际在用)与 `score≥1` vs Swift `score:0` 哨兵漂移(P2-CON-02 同类)的整读印证。

**一致性验收修订记录(2026-07-14 第二轮,不改变任何方向性结论)**:①Executive verdict 缺口计数「两处」改「三处」,并把 8 秒条款归入「对旧 spec 的过度否决」使总括句(1 矛盾 + 2 过度否决 + 3 缺口)与 §2.2 三条一一对应;②统一状态模型:needsReconciliation 不再作为 reviewStatus 第三档,改为正交维度 `reconciliationStatus: none/needed/resolved`(§3.9、§5.4、§7 表 §12 行、§8 I5、§9 Stage 0/Stage 3/验收标准同步);③「推杆/总杆包含关系」等级统一为 Important(§5.6 与 §8 新 I8 一致,理由:数据正确性风险),§5 顺序按分量重排、§8 Minor 重编号并同步 §5.8/§5.9 交叉引用;④§7 verdict 表补新报告 §19 行(ACCEPT(修));⑤V1/V2/V3/V4/V7/V10 判定改为可执行阈值或显式 discovery 输出+决策门,表头改「判定(通过线或决策门)」;⑥消除有歧义裸路径:`reports.py`→`ai_caddie/reports/reports.py`、`decision.py`→`ai_caddie/caddie/decision.py`、`history_stats.py`→`ai_caddie/history/history_stats.py` 等,§1/§2.3/§3.6/§3.11/§4/§12 全部补全目录前缀;⑦元数据补读加固计数「三处」改「四处」;⑧Stage 0 计数「增补四件」改「增补三件」;⑨自查追加:后端/AI/契约项数「14」改「15」(状态段与 §12 组标题)、Exec verdict 第 5 点「四份工程报告」改「三份工程评审报告」、§2.2.2「三条」改「至少三条(最强的三条)」以与 §6 的七条完整清单自洽。

**明确未做**:未运行任何测试/构建;未编译 Swift;未访问生产环境或真机;未读取 data/、.garmin_tokens 或任何凭据;未逐行读 App.tsx/CurrentHoleView.swift/ai_caddie/caddie/mobile_live.py/ai_caddie/history/history_stats.py 全文(采信段落 + 两份工程报告对同一行号的交叉确认,均已标注);Watch 真机交互结论一律标 NEEDS-VALIDATION。

所有要求领域均实际审查,8 个验收补读文件全部成功完整读取,一致性修订全部完成,故状态保持 **COMPLETE**;各结论可信范围以上表深度为准。
