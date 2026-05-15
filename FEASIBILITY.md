# Feasibility Analysis — 2026-05-08 prototype round

四个方向各做了一个最小验证。下面是每个的结论 + 暴露出来的真实约束。

## 1. 18 洞 hole overlay 全图 + HTML 索引

**做了**：`build_hole_overlay.py` 跑全 18 洞，每洞 BirdsEye 底图 + 历史击球点叠加，输出 `output/hole_overlays/hole_NN.jpg` 加 `index.html` 索引。

**数据**：snapshot 400065 (黑骑士 B/C) 18 洞共 1015 杆历史击球，每洞 28-76 杆。focus round 17344568 用大点+白圈突出，其他轮 r=4 半透明散点。

**结论：可行，已上线**。
- ✅ Garmin 的 shot JSON 自带 x/y 像素坐标，根本不需要算 bbox（之前错误判断）
- ✅ 4x supersampling + LANCZOS 抗锯齿够用
- ⚠️ 局限：当前只覆盖 1 个 snapshot。要扩展到所有 91 个球场需要循环每个 snapshotId 调一次 `/shot/course-snapshot/{sid}/hole`，cookie 刷新后批量跑就行，工作量低

## 2. 全量 shot 数据拉取（fetch.py --shots）

**未跑**。Cookie 过期（curl 返回 401），需要用户从浏览器重新导出 cookie + csrf。

**结论：可行但有运维负担**。
- ✅ fetch.py 早就支持 `--shots`，逻辑完整（每场调 `/shot/scorecard/{sid}/hole`，缓存到 `data/shots/`）
- ⚠️ 单场约 0.25s，443 场约 2 分钟；带 sleep 不会触发限流
- ⚠️ 真实障碍：cookie 寿命 9-19 小时，每次跑批前都要手动刷一次。长期方案要么走 OAuth refresh（之前没跑通），要么写个浏览器扩展自动同步 cookie。先用手动够了

## 3. 单场 AI 复盘 prototype

**做了**：`ai_review.py` 把一场 scorecard JSON 抽成 1693 字符结构化 brief（球场/差点/round stats/每洞详情），喂给 Claude Sonnet 4.5 出复盘。

**数据**：17344568（黑骑士 B/C，101 杆）的复盘见 `output/ai_reviews/17344568.md`。

**结论：可行，但今天没跑成 API**。
- ✅ Brief 抽取逻辑通了：FH/GIR/putts、各 rating、每洞 par+strokes+putts+FH+net、最长杆——信息密度足够 LLM 写出有针对性的复盘
- ✅ Prompt 设计成功：4 段固定结构（定性/亮点/根因/下次试一件事）让输出可比可累积
- ❌ ANTHROPIC_API_KEY 在 shell 里是空值，没真打 API。我用同款模型按 prompt 生成了一段示意输出存到 .md 文件验证格式
- 🎯 看那段示意输出，它给出的几个观察都是从 brief 数据里推出来的（GIR=2 是核心问题、博忌+ 占 17/18、右偏比左偏多 2 倍、par 3 整体崩、approach 是根因）——说明数据足够支撑有内容的复盘
- 🎯 限制：单场看不出 trend，复盘里只能写「这是基于单场的猜测」。真正有用的是跑全 443 场再让 LLM 做横比

**下一步**：用户配 ANTHROPIC_API_KEY，跑 `uv run ai_review.py 17344568` 验证真实 API 输出 vs 我的模拟输出差异。

## 4. 两个 dashboard 视图（趋势线 + 球场地图）

**做了**：`build_dashboard.py` 输出两个独立 HTML：
- `output/dashboard/trend.html` — Chart.js 时间序列总杆波动图（仅 18 洞场次，335 场）
- `output/dashboard/courses.html` — Leaflet + Esri 卫星瓦片，91 个球场聚类标点，圆大小反映出场次数，弹窗显示 N 场/均杆/最好杆

**结论：可行，质量出乎意料地好**。
- ✅ 91 个球场全有经纬度（0 个缺失）。courseSnapshot 里的 lat/lon 是十进制度数（不是 semicircle，跟 hole 数据不同），跳过转换直接画地图
- ✅ Chart.js + Leaflet via CDN，零 Python 依赖增加
- ✅ 335 场 18 洞数据排开来一眼能看到趋势：早期场次到现在差不多十年，最近 269 场聚集
- 🎯 这个观感跟视频里那个微信小程序一致甚至更好（卫星底图 + 聚类）。剩下 6 个视图（成绩分析/分布金字塔/打球频率热力日历/打球记录时间线/年度汇总/打过的球场列表）都是同样套路，每个 1-2 小时能出
- ⚠️ 球友信息 Garmin 没有，时间线视图里那栏要么留空要么靠未来语音/手动补

## 整体可行性判断

| 方向 | 技术可行性 | 数据足够 | 主要约束 |
|---|---|---|---|
| Hole overlay 全场 | ✅ | ✅ | 需要刷 cookie 跑批 |
| 全量 shot 数据 | ✅ | ✅ | cookie 寿命短，手动刷烦 |
| 单场 AI 复盘 | ✅ | ✅ | 需要 API key 配置 |
| 多场横比 AI 复盘 | ✅ | 需要先跑 #2 | 上下文长度，需要先聚合再喂 |
| 8 个 dashboard 视图 | ✅ | 7/8 完整数据 | 球友字段需要补充输入 |
| Tier 2 每洞先验 | ✅ | 需要先跑 #2 | 数据齐了就能做 |
| Tier 3 能力模型 | ⚠️ | 需要语音补 putts/FH 之外的击球类型 | 数据缺口在击球意图标注 |
| Tier 4 实时建议 | ❌ | 需要球场几何（fairway/hazard 多边形） | Garmin API 暂未找到这层数据 |

## 现在就能做的（不依赖 cookie/API key）

1. 把另外 6 个 dashboard 视图补齐：成绩分析、分布金字塔、打球频率热力日历、打球记录时间线、年度汇总、打过的球场列表
2. AI 复盘 prompt 多版本 A/B（结构改一改让输出更直接还是更结构化）
3. Hole overlay 加：分球场切换、focus round 切换、按 club 分色版本

## 等用户解锁的（要 cookie 或 API key）

1. fetch.py --shots 跑全量 → 解锁 tier 2、所有球场的 hole overlay
2. ANTHROPIC_API_KEY 配置 → 真 API 跑 AI 复盘，再做 prompt 调优
3. 等 #1 完成后再跑 91 个球场每个的 hole overlay 批量

## 没解决的根本问题

**球场几何（fairway / hazard / green polygon）**还没找到 API。这是 tier 4 实时建议的前置——没有几何就没法说「这一杆该瞄左边 5 米避开右边水池」。之前 probe_map.py 试过 30 多个路径都 404。下一步要么再抓一次 SPA 网络看有没有漏掉的 endpoint，要么承认 Garmin CN 不暴露这层，从 OSM/GeoJSON 自己标注关键球场。

**球友字段** Garmin 没有，目前唯一来源是录手表时同组球友标记（3451876373 之类的 unitId）但这只是设备序列号，没法关联到人名。视频里那个小程序有「球友统计 104」，他们可能让用户手动建球友档案。我们要么也走手动，要么语音输入时顺便登记。
