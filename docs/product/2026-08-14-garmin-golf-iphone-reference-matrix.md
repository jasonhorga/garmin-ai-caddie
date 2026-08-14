# Garmin Golf iPhone 视觉与交互基准

> 状态：iPhone 产品真值。Apple Watch 另以 Approach S70 为基准；GolfLive 只补统计功能广度，不能替代本文件的 iPhone 信息层级和视觉基准。
>
> 官方证据：Garmin International 的美国 App Store `Garmin Golf`（App ID `1192480582`，查询版本 `3.9`，查询日期 2026-08-14）。截图 URL 来自 Apple `lookup` API，不使用私人账号截图。

## 1. 真值优先级

1. 用户实际打球任务与已确认业务规则。
2. 本文件列出的 Garmin Golf iPhone 官方页面及信息层级。
3. 我们的真实数据边界、AI 球童与可解释证据层。
4. 内部 HTML、设计稿和历史批准图只作为实现草稿；与前三项冲突时不能作为验收真值。

“像 Garmin”不是复制商标、素材或像素，而是复用已经被验证的产品结构：先回答当前任务、地图承担主体、数据贴近对象、复杂细节逐步展开。

## 2. 官方逐屏参考

| ID | Garmin 官方页面 | 官方截图 | 我们的对应页面 | 必须借鉴的结构 | 我们保留的差异化 |
|---|---|---|---|---|---|
| G-IOS-01 | Activity | [1.png](https://is1-ssl.mzstatic.com/image/thumb/PurpleSource221/v4/d1/50/14/d1501425-eb40-a5f4-3eff-3cac495e21bc/1.png/392x696bb.png) | `ResultsView` / 全部球局 | 最新球局优先；每场独立紧凑卡；右侧总杆与相对 Par；底部 18 洞颜色条 | 可信度、逐杆覆盖和 AI 复盘入口只能作次级信息 |
| G-IOS-02 | Round scorecard | [2.png](https://is1-ssl.mzstatic.com/image/thumb/PurpleSource221/v4/2c/4f/01/2c4f01ce-3806-314c-262b-d3ff5713c693/2.png/392x696bb.png) | `RoundReviewView` | 球场头部后先显示记分卡；总分与每洞结果是第一事实；FIR/GIR/推杆/罚杆逐层展开 | 点洞进入逐杆地图和可编辑证据 |
| G-IOS-03 | Course Stats | [3.png](https://is1-ssl.mzstatic.com/image/thumb/PurpleSource211/v4/6a/14/d9/6a14d9f7-e701-cecd-0ac3-3d787d377fdf/3.png/392x696bb.png) | 球场统计 | 全场/前九/后九先切范围；用范围线和位置标记表达均值，不堆 KPI 小卡 | 接到该球场反复失误的洞图和备战策略 |
| G-IOS-04 | Shot map | [4.png](https://is1-ssl.mzstatic.com/image/thumb/PurpleSource211/v4/e9/be/74/e9be74cb-5a47-5e6f-849e-c018ec94d090/4.png/392x696bb.png) | `RoundShotMapView` | 地图近乎占满屏幕；杆、距离和推杆事实贴在真实落点；返回、图层、定位、缩放悬浮在边缘 | 编辑落点、顺序、球杆、罚杆及数据来源状态 |
| G-IOS-05 | Leaderboard score rows | [5.png](https://is1-ssl.mzstatic.com/image/thumb/PurpleSource211/v4/bc/eb/e7/bcebe7ed-40cf-2fc3-4339-56f85920c121/5.png/392x696bb.png) | 实战/赛后记分卡 | 表格只承担天然是表格的数据；洞号、Par、成绩对齐；行可展开 | 单人产品不复制社交排名，只复用紧凑记分结构 |
| G-IOS-06 | Shot Overview | [6.png](https://is1-ssl.mzstatic.com/image/thumb/PurpleSource211/v4/56/0f/ca/560fcafc-b0d2-58c4-9227-138bd8db51ab/97aedf07-891f-487a-bcce-0bf76b7a6638_6.png/392x696bb.png) | `StatsView(.analysis)` | Drive / Approach / Chip / Putt 是一级阶段导航；一个页面一次只回答一个阶段问题；空间图是主体 | 数据覆盖、可信度和从弱项回到具体球局/洞/杆 |
| G-IOS-07 | Virtual Range | [7.png](https://is1-ssl.mzstatic.com/image/thumb/PurpleSource211/v4/38/a4/60/38a46093-bf76-8248-4230-33b0937257df/5.5.png/392x696bb.png) | 球杆与散布 | 真击球点、距离网格、球杆筛选在同一空间图里；底部只保留必要摘要 | 用 Garmin 历史杆距和我们的样本质量筛选，不展示假散布点 |

## 3. 七条硬性验收规则

1. 成绩首页首屏必须先看到真实最近球局，不能先看到生涯 KPI 或模块入口。
2. 单场详情必须先看到记分卡，再看到阶段指标和 AI 解释。
3. 有可投影逐杆数据时，复盘地图必须是主体；同一逐杆事实不能再在地图下重复成长列表。
4. 表现分析必须以四阶段切换为主导航；不能恢复成开球、GIR、推杆、季度、球场、球杆连续卡片墙。
5. 有真实空间点才画点；只有方向/计数聚合时，必须明确画成“分区汇总”，不能生成看似真实的随机散布。
6. FIR、GIR、推杆、罚杆等数字都显示实际分子/分母或覆盖说明；缺数据不等于 0。
7. 每次视觉交付必须把本表官方图与同状态模拟器截图并排审查；测试通过和内部稿一致都不能替代这一步。

## 4. 当前修复顺序

本轮只按可见用户路径线性推进：

1. `成绩 → 最近球局` 对齐 G-IOS-01。
2. `最近球局 → 单场` 对齐 G-IOS-02。
3. `单场 → 某洞落点` 对齐 G-IOS-04。
4. `成绩 → 表现分析` 对齐 G-IOS-06，并明确聚合图与真实散布图的边界。
5. 下一批再处理球场统计和球杆真实散布，对齐 G-IOS-03/G-IOS-07。
