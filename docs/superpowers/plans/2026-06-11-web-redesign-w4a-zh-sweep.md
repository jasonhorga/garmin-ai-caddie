# Web Redesign W4a — 全站中文化 + 样式统一 + 全局码显示 + 强弱分析重做

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps for tracking. Requirements source: `docs/superpowers/specs/2026-06-11-w4-requirements.md` (user acceptance feedback items 1–2; item 3 选九洞/Tee = W4b, NOT here).

> **中文摘要:** 用户真实使用后的三连击:旧页面全英文裸样式(球局/球场/报告/设置)、强弱分析看不懂、距离要用码。本期:legacy 页面全部套 W1 设计语言并中文化;强弱分析按"结论先行"重做(用上 phaseStats/teeDirection 等现成数据);所有展示距离米→码(后端不动);**收尾前 Playwright 逐页截图人眼验收(桌面+412px)— 新的硬性门禁**。

**Branch:** `superpowers/web-redesign-w4a` off integration/v2 (65ba118) via EnterWorktree (verify base; reset if stale). Node 24 PATH. Baselines: frontend vitest 337/33 files (post PR#21), backend 779 (post PR#22), e2e 2/2. Frontend-only phase (zero backend changes; report BODY text stays English — it comes from the report provider, translating it is a later backend phase; only page CHROME is in scope for 报告).

**Hard rules (from memory/feedback):**
- 显示层全部用码:`1 m = 1.09361 yd`,整数,后缀「码」。后端/接口/测试 fixture 维持米制。输入框(沙盘到果岭)改为码输入、提交前转回米(保留 1 位小数米值)。
- 中文化 = 页面 chrome(标题/eyebrow/标签/按钮/表头/空态/错误态/aria)。数据值里的英文枚举走映射(已有 issueLabels.ts / CONFIDENCE_ZH / MISS_DIRECTION_ZH 先例)。
- 样式统一 = 复用现有 token/类(.panel、.section-head、chips、subnav 等),原生裸控件(select/checkbox)套既有表单样式或新增 `.w4-*` 类;不引库。
- **完工门禁:真实数据起服务 → Playwright 截全部页面(桌面 1440 + 412px)→ 多模态人眼检查 → 范围外的丑也要上报。**

---

### Task A: 共享件 — units.ts(码)+ 公共 zh 词典

**Files:** Create `web_v2/src/units.ts` + `units.test.ts`;Create/extend `web_v2/src/zhLabels.ts`(吸收 issueLabels.ts?不动它,新文件放通用词:phase Tee/Approach/Putting/Scoring→开球/攻果岭/推杆/得分,confidence,geometry coverage ready/partial/missing→齐全/部分/缺失,state ready/error 等)。

units 契约(TDD):
```ts
export function yards(m: number | null | undefined): number | null   // m→整数码
export function fmtYd(m: number | null | undefined, dash = '—'): string  // '393码' / '—'
export function metersFromYards(yd: number): number                  // 输入反转换, 1位小数
```
Commit: `feat(web): units(码) + shared zh label maps`

### Task B: 球局页(HistoryTimeline + RoundCard)中文化+restyle

用户截图实锤页。'ROUND ARCHIVE/Rounds/Month-grouped…' → 「球局存档/球局/按月分组…」;筛选条(Year/Course/Has shots/Has report)→ 「年份/球场/有击球/有报告」+ 套 `.w4-filter` 样式(参照 trends 的 range 行风格);RoundCard 内 chrome zh(badges 文案、aria);月组头 zh(May 2026→2026年5月)。HistoryTimeline.test/App.test/e2e 锚点迁移(e2e 断言 heading 'Rounds' → 「球局」,注意 subnav 球局按钮与页 h2 同名 — 用 role+level 区分)。
Commit: `feat(web): 球局页中文化 + 设计语言统一`

### Task C: 球场页(CourseStats)中文化+restyle + 去备战

'Course Stats' → 「球场表现」;行内字段 zh(rounds/avg/best/worst/geometry→场次/平均/最好/最差/几何);每行加「去备战 →」(需要 globalId:CourseStats 只有 courseKey —— 通过 App 传入 courseOptions 做 courseKey→globalId 映射,无映射的行不显示按钮;点击走既有 handlePrepCourse)。CourseDistributionMap 的 chrome zh。测试迁移。
Commit: `feat(web): 球场页中文化 + 去备战直达`

### Task D: 报告页(ReportsPage)chrome 中文化+restyle

标题/页签/按钮/字段标签 zh('Reports/Generate/Load/period…'→「报告/生成/载入/周期…」);报告正文(narrative/facts)保持后端原文,正文区加说明「报告正文由引擎生成(暂英文)」。样式套 panel/chips。测试迁移(App.test 报告流断言 'Reports' heading 等)。
Commit: `feat(web): 报告页 chrome 中文化`

### Task E: 设置区(SyncStatusPanel/工作区/Corrections/SettingsPage)中文化+restyle

同步面板:'Garmin CN/ready/scorecards/shot files/Last data update/Sync now/Admin token/Web session header…' → zh(就绪/记分卡/击球文件/最近数据更新/立即同步/管理令牌/会话头…);连接器卡、能力矩阵、OAuth probe 标签 zh。MobilePackagePrep/Reconciliation/Readiness/DataQuality chrome zh + restyle。CorrectionsPage、SettingsPage chrome zh。这是体量最大的翻译任务 — 允许拆两个提交(同步面板一个、其余一个)。测试迁移量大(App.test 同步/订正流 + 各组件 test):**台账纪律 — 只改文案断言,不许丢行为断言**。e2e:'Sync & Data Quality'/'Corrections'/'Settings'/'Garmin CN'/'Review history' 锚点全部换 zh(对应 subnav 标签已是 zh,页内 h1 改后用 zh)。
Commit(s): `feat(web): 设置区中文化 + 样式统一(同步面板/数据健康/订正/配置)`

### Task F: 强弱分析重做(结论先行)

用户原话"没看懂"。新组件 `StrengthsPage.tsx` 替换三块堆叠:
1. **头部结论区**:「你最该练」前 3 条 — 来源 stats.playerProfile.weaknesses(label zh 映射 + reason 白话)+ issues[0];每条带出处 chips。
2. **总体数字行**(来自 stats.scoring.phaseStats,全局已有!):球道命中率(Tee.fairwaysHit/sampleCount)、GIR(Approach.girPct)、平均推杆(Putting.averagePutts,标「估算」)。
3. **三个折叠/锚点区**(原数据重组,全 zh):
   - 按洞:沿用 HoleStats 数据,行式「第N洞 · 球场 · 平均+x · 最差+y」+ 分布条;表头白话。
   - 按杆:ClubStats 数据,**距离全部码**(median/p10/p90→常用距离/波动区间),confidence zh。
   - 问题:IssueStats 的 issue 行(issueLabel zh)+ 次数;decision-audit 区块移除出本页(挪到设置·数据健康?NO — 简单:折叠在页尾「引擎自检(高级)」details 元素里,不删功能)。
原 HoleStats/ClubStats/IssueStats 组件:被 StrengthsPage 吸收后若无其它消费者则删除并迁移测试台账(grep 先行)。App renderStatsContent holes|clubs|issues → StrengthsPage。e2e 强弱分析断言换新锚点(「你最该练」)。
Commit: `feat(web): 强弱分析重做 — 结论先行 + 总体命中率/GIR/推杆 + 全码距离`

### Task G: 全局码清扫

grep 所有渲染 `m`/`米`/`carry_m`/`route_len` 显示点:LiveSandbox(距T/到果岭读数、降级输入框改码输入)、建议卡 carry、PrepHoleCard 已是码(验证)、prep 头部「总码数」(已码)、TrendsOverview(无距离)、其余出现点逐一换 fmtYd。LiveSandbox e2e/unit 断言更新(距T 0码 · 到果岭 430码 — 393m→430 码,精确换算断言)。
Commit: `feat(web): 全部展示距离统一为码`

### Task H: 全量测试/e2e 迁移收口

跑 FULL vitest + e2e,清掉 B–G 漏网的断言;e2e 走查文案全 zh 后逐段核对(防 substring 冲突,沿用 exact:true 经验)。
Commit: `test(web): zh/码 迁移收口`

### Task I: 视觉验收(新硬性门禁)

脚本 `web_v2/e2e/visual-capture.mjs`(或扩展 smoke):真实数据起 backend(9000)+ vite,Playwright 走全部页面/页签(概览/历史×5/备战入口+课程页×3/实战×3/设置×3),桌面 1440 + 412px 全页截图到 `/tmp/w4a-shots/`。**控制器(主会话)逐张多模态查看**:残留英文、裸样式、布局崩、对比度可疑点 → 列清单 → 修复 → 重截。本任务由控制器亲自执行,不下放。
(产物不入库;截图目录路径写进 PR 描述供用户抽查。)

### Task J: Ship

FULL gates(前端全量 + 后端 779 不回归)→ push → PR → 瘦身对抗复查(2 维度:zh/样式回归扫描 + 测试台账诚实性;**视觉证据 = Task I 截图**)→ 修复 → CI 绿合并(用户已建立的小步合并模式;大阶段照例报告)。

## Self-review
- 需求 1(中文+样式)→ B/C/D/E/F;需求 2(码)→ A/G;强弱分析重做 → F;视觉门禁 → I(记忆 visual-review-mandatory 落实)。
- 风险:E 的测试迁移量(App.test 同步流密集)— 台账纪律;F 删组件 grep 先行;e2e zh 锚点 substring 冲突 — exact 匹配。
- 不做:报告正文翻译(后端)、选九洞/Tee(W4b)、iOS。
