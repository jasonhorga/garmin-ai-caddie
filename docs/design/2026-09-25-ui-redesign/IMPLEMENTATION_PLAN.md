# 实现计划：打球中 / 复盘 / 开球前 / 统计 重设计 + 手表自动记杆

对应设计：本目录 `README.md` 与各原型 HTML。本文件给实现方（Codex）排期用：按数据依赖分 8 批，
每批写明要改什么、依赖什么、怎么验收。批次编号即建议顺序；同一行标“可并行”的可以同时做。

总约束（沿用仓库规则）：

- 每批一个 PR，只做本批范围；UI 批次不顺手改后端，后端缺的数据归 B0。
- 新增或改动的后端字段先写契约和测试，再给客户端用；客户端对缺字段必须能降级（不显示那一项，不报错）。
- 上线仍走现有门槛：homeserver 部署证据齐全后才发 TestFlight；API 和 sync 镜像同 revision 一起构建。
- 屏幕上不写过程提示（同步、下载、检测来源等）；这些状态只进日志和设置页。

## 依赖总览

```
B0 数据底座 ──┬─> B1 手机打球屏 + 旗位 ─┐
              ├─> B4 开球前            │
              ├─> B2 手机记分三屏 <────┘
              │     └─> B3 复盘（含改杆纠错上报）
              ├─> B5 成绩 / 统计 / 球包
              └─> B6 手表界面 ──> B7 手表自动记杆 v2（需 B3 的纠错数据）
```

B1 与 B4 只依赖已有数据，可和 B0 并行起步；B2 的 GPS 开球预选、B5 的新统计、B7 必须等 B0。

## B0 数据底座（后端为主，无界面变化）

| 项 | 现状 | 要做 | 验收 |
|---|---|---|---|
| 球道轮廓（唯一几何来源） | `HolePrep` 有 `greenOutline`、hazards，没有球道；Garmin 几何里有 `Fairway.drc` | `HolePrep.fairwayOutline`：与 `greenOutline` 同一显示坐标系（topo 像素）的多边形数组，另附 WGS84 经纬度环；可能多段；**缺失为 `null`**（不是空数组）。手机包和手表下载包都带同一字段 | course_prep 单测：有 / 无 / 多段；手机与手表解码器对新旧包的兼容测试（缺字段 = null） |
| 开球结果判定（唯一算法） | 手动选 | 一个判定算法，Python 与 Swift 各实现一份、共用同一组测试向量：输入第二杆（或首推）经纬度 + `fairwayOutline` + 路线中线，输出 `hit / left / right / null`；Par 3 或 `fairwayOutline = null` 返回 `null`（= 不预选）。客户端离线算用于预选，服务端用同一算法算统计，以用户保存的值为准 | 共享测试向量：球道内、左、右、贴边、多段、无轮廓 |
| 每洞成绩来源 | score 事件 payload 有 `source`（现为 `ios_score_confirmation`） | 统一取值：`watch_detected`、`phone_shots`、`default`、`manual_edit`；持久化到每洞 | 事件回放后每洞能读到来源 |
| 统计跳过默认洞 | 统计不区分 | 推杆、GIR 统计跳过“来源 = default 且未改过”的洞 | stats 单测：默认洞不计入推杆 / GIR |
| 新统计字段 | 只有时间窗汇总；无罚杆 | `mobile stats` 增加：每场推杆 / GIR / 球道序列；罚杆合计；救球成功率（长草、沙坑起杆后一推进洞或两杆内完成）；一推 / 两推 / 三推+ 比例；按 9 洞环的每洞平均；前九 × 后九组合矩阵与只打 9 洞场数；最难的洞（按平均多杆排序） | 契约测试 + 用夹具球局核对数值 |
| 纠错记录 | `/history/rounds/{ref}/corrections` 只存整洞替换 | 同时写一条结构化纠错日志：操作类型（加 / 删 / 挪 / 换杆 / 改推杆 / 改总杆 / 改开球）、前后值、时间位置；供 B7 使用 | 纠错接口单测：每种操作都产生日志 |

### B0 成绩来源实现说明（B0c）

- 定义在 `ai_caddie/rounds/score_source.py`：`watch_detected` / `phone_shots` / `default` / `manual_edit`。
- 旧值一律算人填的：`ios_score_confirmation`、`apple_watch`、没有 source → `manual_edit`。只有显式 `default` 才算“默认未改”，所以历史统计不变。
- 每洞来源 = 该洞 score / putt / penalty 事件依次合并：全是 `default` 才是 `default`；出现过别的来源就取最近一个非 default 的，之后再来 `default` 也不降级（改过就是改过）。
- 落点：`build_round_state` 每洞 `scoreSource`；`round_ingest` 写进成绩卡每洞 `scoreSource`，且整场推杆总数不计默认洞（全是默认洞时为空，不写 0）。
- 统计：`history_stats` 里推杆 / GIR 的读取都经 `_stat_putts` / `_stat_gir`，默认洞返回空；用户对该洞的推杆更正（annotation）仍然生效。球道不受影响。复盘明细仍显示原始值，默认洞怎么显示由 B3 定。
- “跳过”指不参与：默认洞同时退出推杆 / GIR 的分母（覆盖率、Approach、approachMiss）、推杆数据质量和 `missing_putt_data` 诊断，不算“缺数据”；对该洞做过推杆更正则重新计入。持久化快照（`snapshot._played_holes`）保留 `scoreSource`，没有该字段的旧 / Garmin 洞形状不变。
- 客户端发送新来源放在 B2（记分三屏重做时一起做“是否改过”的判断），B7 发 `watch_detected`。在那之前客户端仍发旧值，统计与现在一致。

### B0 新统计字段实现说明（B0d-1）

都在 `history_stats._scoring` 里（`_round_breakdowns`），移动端 `mobile_stats._SCORING_KEYS` 同步放行：

- `putting` 增加 `zeroPutts / onePutts / twoPutts / threePlusPutts` 和对应百分比（只算 B0c 意义上合格的洞，推杆更正生效）。0 推（切杆进洞）单独一档，不算一推；四档合计 100%。
- `penalties`：`total / holesRecorded / roundsRecorded / averagePerRound`；只统计带 `penalties` 字段、且不是未编辑默认洞的洞（手动记分有，Garmin 成绩卡没有，缺失不当 0；默认洞入库时的 `penalties: 0` 不是记录）。
- `scrambling`：**标准救球率** = 未标准杆上果岭的洞里，最终 Par 或更好的比例。原计划写的“长草 / 沙坑起杆后一推进洞或两杆内完成”需要逐杆起点和完整杆序，现有球位数据不保证包含每一杆和推杆，会系统性少算，所以改用标准定义。以后（B7 有完整杆序后）按球位的 up-and-down 用新字段名，不改这个字段的含义。
- `roundSequences`：每场（新的在前）`holes`（显示洞号 1–18，缺洞时不补位，其余数组与它逐项对应）+ 逐洞 `putts / gir / fairway`。默认洞的 `putts / gir` 为 `null`；`fairway` 不属于 B0c 跳过的字段，照常给出。
- `loops`：按物理 9 洞环的逐洞平均杆差和样本数。环的身份 = Garmin 球场 id + 物理洞段，key 形如 `gid:1001:1-9` / `gid:7:10-18`（没有 id 时 `course:<courseKey>:…`）：27 洞球场每个环有自己的 id（都是 1–9 洞），18 洞单球场前后九共用一个 id、靠洞段区分；成绩卡带了后九 id（包括前后 id 相同的“A/A”）时，后九就是那个 id 的 1–9 洞，只有没有后九 id 的才是单球场的 10–18。同一天合并的两张成绩卡按“末尾连续 10、11…”切分前后半，前半即使被 Garmin 编成 10–18 也不会和后半撞号。名字在全部场次统计完后按 key 一次决定：取“球场 ~ A/C”两段后缀、或单环场次的单字母后缀（“~ A”）里出现最多的环名；“C/B+A” 这类组合名不作证据；没有证据时写“1–9 洞 / 10–18 洞”，不合成“前九 / 后九”。每个环洞的 par 取各场来源 par 的众数（并列取较小者）；所有列表都有完整排序键（组合在显示名之后再比 `frontKey / backKey`）。结果与历史顺序无关。合并场次的洞 ref 用显示洞号，前半被 Garmin 编成 10–18 的合并场次也能唯一指到每个洞。
- `nineCombos`：只算 `holesCompleted == 18` 的场次，按“前环 key → 后环 key”分组（A/B ≠ B/A），行里带 `frontKey / backKey` 和显示名、场数、平均杆；`nineOnlyRounds`：`holesCompleted == 9` 的场数。
- `hardestHoles`：各环逐洞平均杆差最高的 5 个，至少 2 个样本。
- 体积：用真实历史跑一遍，`/stats` 的 scoring 多出约 298,568 字节（gzip 后约 28,412 字节），主要是 `roundSequences`。B5（统计页）上线前定一个移动端载荷预算（比如按最近 N 场截断 `roundSequences`，或拆成按需请求），不在 B0d-1 里改。

### B0 契约细节（Python 与 Swift 各自实现时以此为准）

现有字段（`ai_caddie/courses/course_prep.py` 的 `HolePrep`）先写清楚，新字段照它们的坐标系：

- `route`：事实路线，发球台→果岭中心的折线，点为 `[x_m, y_m, 累计_m]`，本洞局部米制坐标（与 hazards 同一 frame）。
- `map.overlay.route`：同一条路线在显示坐标系里的像素点，`map.overlay.w / h` 为显示尺寸；只有路线、没有 topo 图时也会下发（“route-only bootstrap”）。
- `holeImageProjection`：`{available, widthPx, heightPx, refs:[{lat, lon, px, py} ×3]}`，三个不共线锚点，客户端拟合仿射把 GPS 放到图上。
- `greenOutline.pointsPx`：显示坐标系像素。
- **显示坐标系**：原点左上，x 向右，y 向下，单位是 topo 图的显示像素（渲染图 ÷ SS），与 `widthPx / heightPx` 相同。

新增 `fairwayOutline`（HolePrep 与手表下载包同名同结构，附加字段，不改旧字段）：

```json
"fairwayOutline": {
  "version": 1,
  "source": "courseData.Fairway",
  "polygons": [
    {"outerPx": [[x, y], ...], "holesPx": [[[x, y], ...]],
     "outerLatLon": [[lat, lon], ...], "holesLatLon": [[[lat, lon], ...]]}
  ]
}
```

- 缺失语义：没有球道几何，或本洞没有 RefLat/RefLon 锚点（无法换算经纬度）= `null`；旧包没有这个键 = 解码为 `null`；`version` 不认识 = 当作 `null`（不报错）。`null` 只影响开球预选和球道统计，不影响地图。
- 环：不闭合（首点不重复），每环 ≥ 3 点；生产端按 RFC 7946 规范化（`outerLatLon` 逆时针、`holesLatLon` 顺时针，以 lon 为横轴）；消费端**不得依赖绕行方向**。
- 多段球道 = 多个 `polygons`；球道里的沙坑等挖空 = 该 polygon 的 `holes*`。点在球道内 = 落在某个 outer 内且不在它的任何 hole 内。
- 经纬度数组顺序固定为 `[lat, lon]`（字段名里写明 LatLon），WGS84 度，7 位小数；像素 1 位小数。`outerPx` 与 `outerLatLon` 一一对应。

开球判定（唯一算法，共享向量 `tests/fixtures/tee_result_vectors.json`，Python 单测和 Swift 单测都读它）：

1. 输入：第二杆位置（没有第二杆用首推位置）的经纬度、`fairwayOutline`、`route`、本洞 Par。Par 3、`fairwayOutline = null`、没有位置 → `null`。
2. 以球道 `outerLatLon` 全部点的平均经纬度为原点，等距矩形投影到米（x 东、y 北，地球半径 6378137 m，与 `shot_projection` 相同）。
3. 在任一球道 polygon 内，或到最近球道边界 ≤ 0.5 m → `hit`。
4. 否则取 `route` 上离该点最近的一段（先把 `route` 用 `holeImageProjection` 或 hazards 的 refLat/refLon 转到同一米制坐标；两者都没有、或路线少于 2 点 → `null`；路线只用来分左右，第 3 步的 `hit` 不依赖路线），
   按“沿路线前进方向”的叉积符号：左侧 `left`，右侧 `right`。
实现：Python `ai_caddie/courses/tee_result.py`（服务端 / 统计）；取轮廓 `course_prep._fairway_outline`（本洞路线 15 m 内的 `Fairway.drc` 连通块）。
5. 向量至少覆盖：球道中、左、右、贴边 0.4 m / 0.6 m、多段之间、在挖空里、Par 3、无轮廓、无路线。

地图显示（B1 / B4 / B6 都按这张表，和 README 的地图降级契约一致）：

| topo 图 | 可画路线（`map.overlay.route`，或 `route` + `holeImageProjection`） | `fairwayOutline` | 显示 |
|---|---|---|---|
| 有 | 有 | 任意 | 正常：topo + 路线 + 落点 |
| 没有 | 有 | 任意 | 立即画事实路线 + `greenOutline` + 已有障碍（深色底）；topo 到了原地替换，不重置缩放 / 平移 / 障碍选择 / 目标点 / 旗位 |
| 没有 | 没有 | 任意 | 统一整屏等待页（洞号 · Par · 码数），不进空白洞 |
| 任意 | 任意 | `null` | 地图不变；开球不预选；球道统计只用用户填的 |

## B1 手机打球主屏 + 旗位（可与 B0 并行）

- 文件：`CurrentHoleView.swift`、`HoleImageMapView.swift`、`LiveGreenDetailView.swift`、`LiveHoleComponents.swift`。
- 内容：全屏 topo、两侧按钮布局；障碍按 README 第 1 节唯一规范：主图默认不选中，只有“障碍”选择器画一个，细红线真实轮廓 + 小红点，无白圈粗框；果岭只一面旗、点果岭进旗位；
  目标点放大镜（沿用现有 Touch Target 参数）。
- 旗位界面：去虚线；1–4 倍缩放；旗到前 / 后 / 左 / 右四边距离（图上细线 + 卡片四格，用 `greenOutline` 算射线交点）；
  拖旗不弹放大镜、旗子与手指保持相对位置；拖出果岭贴边。
- 验收：`-uitest-screen` 新增截图用例（开球、目标拖动、旗位缩放、主图无障碍默认态、选中一个障碍）；四边距离单测（多边形射线交点）；
  地图降级契约（README 第 8 节）的 UI 测试：topo 未就绪先出事实路线；后台补图不重置缩放 / 障碍选择 / 目标点。

## B2 手机记分三屏（依赖 B0 的开球判定、成绩来源）

- 文件：`LiveScoreConfirmationView.swift`、`LiveRoundScorecardView.swift`、`LiveRoundFinishSummaryView.swift`、`Models/LiveScoreConfirmation.swift`。
- 本洞记分改为一屏：总杆记分符号条（从 1 杆排起、不自动居中）、推杆分段、开球三块小图、罚杆 −/+；不写任何来源提示。
- 预选优先级：手表挥杆 → 手机“记一杆”次数 + 2 推 → 默认标准杆；开球用 B0 判定预选。保存时写 `source`。
- 计分卡：大号成绩 + 累计走势 + 前 / 后九符号卡；“结束本场”入口移到这里。
- 本场汇总：复盘同版式（成绩、记分卡、四格含 GIR“按推杆推算”）；去掉同步状态；放弃前确认。
- 验收：草稿模型单测（预选优先级、推杆超总杆时总杆自动加）；三屏 UI 截图。

## B3 复盘（依赖 B2 的汇总版式、B0 的纠错日志）

- 文件：`RoundReviewView.swift`、`RoundShotMapView.swift`、`RoundShotEditComponents.swift`、`Models/RoundEditModel.swift`。
- 单场复盘 = 汇总版式 + 累计走势 + 分享；缺数据不单独提示。
- 每洞落点：全屏 topo、编号点按球位着色、“一号木 221”标签、“推 ×2”；底部 18 洞符号条换洞；去掉缓存状态和简洁图切换。
- 同屏改杆：编号点拖动（放大镜）、点空白加杆（按距离预猜球杆）、底栏球杆横滑 / 球位 / 顺序 ‹ › / 删除；未选中时推杆、罚杆 −/+；
  去掉排序列表、图例、单独的精确定位全屏页。保存仍整洞提交，同时带上逐项改动（给 B0 纠错日志）。
- 顺带：`RecentRoundReviewView` 无入口，确认后删除或接回。
- 验收：编辑模型单测（插入位置、顺序调整、删除后编号）；纠错日志端到端测试。

## B4 开球前（可与 B0 并行）

- 文件：`RoundHomeView.swift`、`StartRoundView.swift`、`PrepCoursePickerView.swift`、`MobileCourseSearchView.swift`、`CourseReviewView.swift`。
- 首页主卡按情况切换：附近球场 + 上次组合与发球台 + “开始”；进行中 = “继续第 N 洞”；附近没有 = 搜索。上一场卡片加 18 洞符号条。
- 开始一场：合并附近 / 最近 / 已下载为一个列表；只选第一个 9 洞环（A / B / C），发球台颜色圆点；按钮写“从 B 场开始 · 蓝 T”。
  第二个环在打完第一个环时选（默认上次搭配，可同一环，可结束只打 9 洞），开打第二环前可改；不合成“9 洞组”，不固定“全场”。
  不显示定位 / 下载状态文字；未下载也可开打，按 README 第 8 节地图降级契约。
- 备战：全屏 topo + 球童路线；方案切换、球杆顺序、18 洞条；可换发球台；未就绪的洞按地图降级契约显示，不弹“地图尚未准备完成”。
- 验收：9 洞环状态机单测（选第一环 → 中途选第二环 → 改选 → 只打 9 洞；含同一环两次）；手机与手表同一状态机；
  备战 / 打球在部分洞未就绪时的降级 UI 测试（事实路线、整屏等待页、补图不重置状态）。

## B5 成绩 / 统计 / 球包（依赖 B0 新统计字段）

- 文件：`ResultsView.swift`、`StatsView.swift`、`PerformancePhaseGraphics.swift`、`ClubGappingLadder.swift`、`ClubSettingsView.swift`、`ClubBag.swift`。
- 成绩首页：差点最大 + 近 20 场走势（每场点 + 近 10 场均线）+ 三数字 + 最近三场符号条 + 四个入口。
- 表现分析：“最该练”一句 + 四阶段同一写法（大数字、和之前比、分段条）；删除现有分段切换和四种阶段小图。
- 时间与频率：粒度切换图 + 季度 / 历年卡片 + 打球日历（现有“时间趋势”内容全部保留）。
- 成绩分布：每 5 杆柱状、全部洞成绩构成、按 Par。
- 球场：topo 打底、均杆 + 最佳、每场细线、最难三洞地图卡片、常打三种组合 + 全部组合。
- 球包：距离阶梯（p10–p90 条 + 中位线 + 相邻差距 < 8 / > 20 标黄）；点杆改距离或拿掉；合并“成绩 → 球杆”和“球杆设置”。
- 验收：各屏在缺字段时降级；数值与 B0 夹具一致。

## B6 手表界面（依赖 B2 的记分模型）

- 文件：`WatchRoundContainerView.swift`、`WatchHoleMapView.swift`、`WatchHazardMapView.swift`、`WatchGreenPreviewView.swift`、
  `WatchScoreHoleView.swift`、`WatchClubPromptView.swift`、`WatchFinishRoundView.swift`、`Models/WatchRoundModel.swift`。
- 本洞改为上下三页（方案 / 障碍 / 果岭），表冠只缩放，放大后拖动平移；点球杆签换方案、点“1 / N”换障碍（放大后换障碍**保持当前缩放和平移**，不自动 fit，owner 要求，防 IMG-8050 回归；UI 测试断言 z / pan 不变）；
  障碍只在障碍页（显式选择器）画一个，方案页和果岭页默认不画，样式同 README 第 1 节唯一规范；
  点地图（放大时长按 0.5 秒）测距，未开球从发球台量。
- 本洞成绩一屏：总杆左右数字带（表冠 / 滑动）、推 / 罚原地循环滚轮、开球三格；不点确认则下一洞开球时自动保存。
- 去掉每杆“刚才用哪支杆？”（球杆改由 B7 按距离推断，推断前留空）。
- 洞结束触发：离开果岭 25 m 以上朝下一洞发球台走，或下一洞首杆。
- 验收：`WatchUITestRoot` 增加对应屏；洞结束触发的单测（GPS 轨迹夹具）。

## B7 手表自动记杆 v2（实验开关后面，依赖 B6 + B3 纠错）

原型里的 800 Hz / 200 Hz 采样、Series 8+、1.4 秒缓存、各门槛、8 m 合并距离都是**假设**，不是现有 `WatchAutoShotDetector`
已证明的能力；实现前先补下面的门槛和测试，不能把原型数字当成承诺。

- **能力 / 电量门槛**：运行时检测 `CMBatchedSensorManager` 与设备能力，不满足（机型、系统、权限、锻炼会话起不来）就整体关闭，
  回到手动记杆；记录一场的耗电，超过预算（先定为比现有锻炼会话多 ≤ 5% / 小时）自动关闭。
- **采样失败降级**：传感器报错或批次中断时停止检测、保留已记录的杆，不丢数据、不弹提示，本场剩余按手动记。
- **候选不改成绩**：第 1、2 步里候选只写特征，不进成绩；端到端测试证明开启采集后成绩、事件流与关闭时完全一致。
- **GPS / 洞结束门槛**（同样是假设，第 1 步数据定值）：
  - 位置精度：原型写的 ≤ 12 m 只是起点。第 1 步记录每次候选的水平精度分布，定出门槛后才用于判球位 / 合并。
  - 精度不够：取挥杆前 10 秒内最好的一个点；仍不够就标“位置未知”——照样计杆，但不判球位、不按距离合并（只按 60 秒时间合并）、不推断球杆。
  - 漂移：5 秒内跳 > 30 m 且步数没有对应移动的点丢弃。
  - 整洞没有 GPS：不自动分洞，回到现有的手动换洞；本洞挥杆照样计入当前洞。
  - 洞结束（离开果岭 25 m 且朝下一洞发球台走，或下一洞首杆）是**可撤销**的：误触发后 60 秒内在原果岭附近又测到挥杆，自动退回上一洞；
    用户也可以在成绩页把杆挪回上一洞，这类改动写进纠错日志当标签。
  - 能力门槛的评估报告里必须包含：GPS 精度分布、洞结束误触发率 / 漏触发率；达不到就只开采集、不开启用。

分三步，前一步有数据再做后一步：

1. **采集**：扩展 `WatchAutoShotDetector`（往回找挥动起点、累计转角、撞击时长、推杆 / 切杆分类、车速过滤），
   只记录候选及特征值，不改成绩；每场结束随纠错一起上传（开关控制，原始传感器数据不出表）。
2. **标注与调参**：用户实打若干场，在复盘逐杆核对（B3 的改动即标签）；离线评估各门槛的精确率 / 召回率，定起步门槛。
3. **启用**：候选按“同位置 60 秒只留最像击球的一次”合并，免确认直接进本场；推杆没测到按首推距离估；球杆按距离推断；
   个人门槛按纠错慢慢调（每场一小步、同类纠错 ≥ 5 条才动）。罚杆不猜。
- 验收：检测器单测（空挥、试挥打地、打完比划、坐车、推杆 / 试推夹具）；启用前的实打评估报告。

## 风险和待定

- 推杆能否稳定检测未知，按距离估是常规路径；B7 第 1 步的数据决定是否开放推杆检测。
- 撞击时长、车速、合并距离、采样率等都是假设，没有公开数据可依；以 B7 的能力门槛和第 2 步实测为准。
- 统计模型新增字段较多，B0 需要先确认现有历史数据能否回算（缺逐杆球位的旧球局，救球率只算有数据的场次）。
