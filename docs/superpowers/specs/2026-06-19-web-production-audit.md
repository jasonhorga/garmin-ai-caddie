# Web 前端「production 化」审计(2026-06-19)

> 触发:owner 反馈「网页问题很多……整体工程化味道很浓,不是一个真的 production 产品」+ 4 张截图(单场复盘、历史球局、备战、球局回顾)。要求:对齐手机端 round-10 修正 + 全站审计「工程味」。

## 根因(一句话)

同一份 web 构建既给 **owner**(烤入 admin token、全运维/调试权限)用,也可能给 **分享链接的访客**(`/p/<token>`)用;但它把**所有内部 ref/ID、数据质量/覆盖/置信度、来源追踪面板、英文工程调试面板、运维控制台**默认渲染给所有人。owner 的产品体验被埋在工程信息底下,访客更会看到不该看的东西。

## 修复策略(两套机制 + 本地化)

1. **`isOwner` 门控** = `!playerToken && Boolean(adminToken)`(App.tsx 已有此表达式,但只用在 1 处)。把**纯运维界面**对访客彻底隐藏:整个「设置」段(同步与数据健康 / 订正 / 后端配置 / 球员管理)、报告生成、各 ops 面板。
2. **`诊断模式` 开关**(owner-only,**默认关**,localStorage 持久化)。让 **owner 默认也看到干净产品**;需要排数据时一键打开,调出 raw ref / 来源面板 / 数据质量 / 证据链 / 置信度。这保住 owner 的「添加订正」等依赖 ref 的工作流,同时默认呈现产品。
3. **本地化 + 格式化**剩余面向用户的部分:英文球童/决策/天气面板→中文、ISO 时间戳→友好日期、英文/`~`/`+`/`-` 球场 nine 标注归一、raw subjectId/roundId→友好标签、raw courseKey 隐藏、单位(m/s→km/h、°、码)。

---

## 发现清单(按簇)

### A. 历史 / 单场复盘簇 —— 工程味重灾区(`HistoryRoundDetailPanel` / `HistoryDrilldownPanel` / `HoleEvidencePanel` / `RoundCard` / `SourceRefs`)

P0(内部管道泄漏给用户):
- 标题区 raw round ID chip(`16745851`)+ `已找到`/`未找到` 状态 chip。
- 成绩区混入数据质量/覆盖卡:`记分卡 齐全`、`击球数据 齐全`、`推杆数 齐全`、`置信度 高`(ETL 完整度 + 管道评估,非高尔夫指标)。
- `相关来源` 面板(球局/球洞/击球/原始 + `16745851:1:15147` `等45处`)恒显示。
- 逐洞 `击球 16745851:18:15164` raw shotRef chips。
- AI review meta 暴露 LLM provider + 原始 model id(`claude-3-opus-…` / `high confidence` 英文)。
- 整个 `HistoryDrilldownPanel`(raw ref / EvidenceCoverage / 原始 JSON dump / 源字段)对**所有用户**可达(点任意来源 ref 即开)。
- 整个 `HoleEvidencePanel`(几何证据,**全英文**:Shot Routes / Surface Classifications / Map Features / Fetch Geometry…)对所有用户可达。
- `RoundCard` 每张卡 `来源 [16745851]` chip + `DataQualityChips`(击球 齐全/缺失)。
- `SourceRefs` 把 raw ref 当主可见文本渲染(无 display-name 层)。

P1:`data.title` 直接渲染 raw ISO 时间戳(`2025-09-02T08:47:59+09:00`)+ 英文球场名 + `~`/`-` 混用;8 卡竖排成绩区冗长;`缺失数据` section 直接给用户;`有路径图的洞数` 几何黑话。
干净:`ScoreStrip` / `HistoryTimeline` 无问题。

### B. 统计簇(`StrengthsPage` / `TrendsOverview` / `CourseStats` / `CourseDistributionMap` / `StatsQualityChips`)

已达标(web 本来就对):**近期趋势 issue 中文标签**(完整 `issueLabels.ts`,处处 `issueLabel()`);**保帕率百分比**(本地按计数算,无双缩放)。
P1:
- `StrengthsPage` 推杆用 per-hole `averagePutts`(~1.9)非 per-round `averagePuttsPerRound`(~33);三推显示累计非场均(÷`roundsWithPutts`)。
- nine 组合 key 未归一(`~C+A` 与 `C/A` 分裂成两行)——`CourseStats` + `CourseDistributionMap`。
- raw `courseKey`(`golf_course_cn_12345`)无门控直接显示给所有用户。
P2:季度/成绩构成显示洞占比非场均;球场钻取无「逐场 日期·成绩」可点列表;英文标签(`N rounds`、`StatsQualityChips` aria);`引擎自检(高级)` 整段英文(已折叠)。

### C. 导航 / IA / 首页 / 杂项页

P0(整段运维暴露):
- 「设置」段 4 子页(同步与数据健康 / 订正 / 后端配置 / 球员管理)只有 `players` 被 gate;其余对所有用户可见。
- 点「设置」默认落到 ops 工作台(`SyncStatusPanel` 含 **管理令牌输入框** + **Garmin 会话/防伪令牌导入表单**、`MobilePackagePrepPanel`、`MobileReconciliationPanel`、`ReadinessPanel`、`DataQualityPage`)。
P1:
- 「报告」在历史子导航,但带 owner 生成按钮 + AI provider/model 元数据 + ML 证据链黑话(`无依据断言`/`推断`/factLabels);report header `<h2>` 居然是 provider 名。
- raw `subjectId`(`recent_10`/`2024-03:900001`)、roundId 当下拉/标签。
- `SettingsPage`(后端配置)= 纯 owner 控制面(OAuth 矩阵、AI provider 列表、`prodgeometry`、英文 `Static`)。
- `DataQualityPage` / `ReadinessPanel` / Mobile* 面板对所有用户渲染。
- `SyncStatusPanel` 暴露 `snapshotId`/`errorCode`。
- 错误文案对访客也说「前往 设置 → 同步与数据健康 填管理令牌」。
P2:`selectedCaddieSourceRef` 默认硬编码 `'900001:7'`;报告正文备注 `(暂英文)` 像 TODO;`手机记分(GPS)` 技术括号;访客无「关于」类落地的 设置。

### D. 备战 / 球童簇(`PrepPage` / `PrepHoleCard` / `CourseFinder` / `CaddiePage`)

P0:
- **备战只选球场名,9 洞变体(`~ C/A`、`~ A`)当独立条目平铺,无「起始9洞」选择步骤**(手机 #45/#46 已做:选球场→前九/后九/全场 分段)。
- `PrepHoleCard` 每洞 `Par 来源:CourseView` provenance chip + raw `sourceRefs`(`900001:7`)chips。
- `CaddiePage` 的 `CaddieContextPanel`(14 个英文输入:Source ref / 经纬度 / Route X/Y / Landing radius…,Source ref 预填 `900001:7`)+ `MediaContextPanel` 全英文、无门控、对所有用户渲染。
P1(球童本地化 + parity):
- 策略标签 `safe/stock/attack` raw 无中文无配色(手机:稳妥绿/标准蓝/进攻橙);`selectedOptionId` 当 `<h2>`;`selected` 英文 pill。
- 避开区是**全局一个平铺列表**非按选项归属;沙坑不编号(`PrepHoleCard` 全 `沙`)。
- `formatOptionMeta`/sequence/weather/scoreImpact/explanation/acceptableMiss/auditPanel/media 面板大量英文(risk/exp/clear/shots/remaining/carry/left、Weather Context、Score Impact…);天气单位 m/s + 原始度数 + `X C`。
- `phaseZh()`/`confidenceZh()`/`missDirectionZh()` 已存在但 CaddiePage 没调用。
P2:`球场 ${globalId}` 回退暴露数字 ID;`CourseView` 英文 brand chip。
干净:码显示、par3 不显示球杆条、`coursePrepPanelLogic` 码换算、`PrepTipsTab` 未知 basis 守卫 —— 均正确。

---

## 执行计划(分批 PR → integration/v2 → 部署 → 实景 Playwright 复核)

1. **基建**:`isOwner` 计算并下发到 AppShell;新增 `诊断模式` 开关(owner-only,默认关,localStorage)+ 一个 `useDiagnostics()` 读取;`OWNER_ONLY_PAGES` 过滤设置段对访客隐藏;owner-only 页加路由守卫。
2. **历史/复盘**:门控 raw ref/状态/数据质量卡/相关来源/逐洞 shotRef/AI infra 到 诊断模式;ISO→友好日期;球场名 + nine 归一;成绩区压缩成紧凑 chip bar。`Drilldown`/`HoleEvidence` 仅诊断模式可达。
3. **统计**:推杆 per-round 字段修正;nine key 归一(抽 `canonicalNineLabel`);raw courseKey 隐藏;球场钻取加逐场列表;英文标签中文化。
4. **备战/球童**:备战按基础球场名分组 + 起始9洞分段;移除 par-source/sourceRefs chips;球童本地化(策略中文+配色、避开区按选项 + 沙坑编号、调用已有 zh 助手、天气单位、决策/序列/证据中文);英文调试面板(CaddieContext/Media)收进诊断模式。
5. **导航/杂项**:设置段对访客隐藏 + 默认页改 overview;报告页拆「只读叙述(用户)」vs「生成+证据(owner)」;subjectId/roundId 友好化;错误文案分 owner/访客;清理硬编码 ref、`(暂英文)`、`(GPS)`。
6. **部署 + 实景复核**:homeserver build + 每页 desktop/mobile Playwright 截图肉眼过(owner 默认视图 + 诊断模式 + 模拟 player-link 三态)。

每批一个 PR、CI 绿再合并;web 改前端需 homeserver `npm run build`(root)。
