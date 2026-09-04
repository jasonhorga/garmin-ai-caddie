# Approach S70 Watch 体验重构：已核证证据包

> 日期：2026-07-15 UTC  
> 用途：供 Codex 与 Claude Fable 5 在不重新猜测 S70 事实的前提下，独立推导 Apple Watch 产品设计。  
> 状态：RESEARCH INPUT，不是设计定稿，不授权实现。  
> 证据口径：`OFFICIAL` = Garmin 当前手册/Support；`MULTI-SOURCE` = 多个独立评测或长期用户交叉；`REPO` = 当前仓库源码可直接验证；`UNKNOWN` = 公开资料无法确认，需 S70/Apple Watch 真机测试。

## 0. 用户当前判断

- 用户对当前 Watch 的视觉层级、响应/操控节奏、自动记杆与洞末流程、可靠性/异常恢复四类问题都不满意。
- 用户还没有亲自试完全部能力；不可把尚未实测的功能当成已验证体验。
- 目标是清楚理解并最大程度还原 Garmin Approach S70 的腕上高尔夫产品体感，同时适配 Apple Watch，不复制 Garmin 商标，也不照抄 Garmin 已知缺陷。
- 本轮先判断设计，再判断现有工程复用，最后才提出修改与实现路径。

## 1. 官方基线

### 1.1 当前手册与硬件

- `OFFICIAL`：Approach S70 Owner's Manual v5，2026-04，覆盖 42/47 mm：
  - https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-A07C88F2-5C72-45B7-B96D-A4203A9F90DA-homepage.html
  - PDF：https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/Approach_S70_OM_EN-US.pdf
- `OFFICIAL`：S70 是触屏 + 三个实体键，不是两个键：
  - Action：表盘下按即开始 golf；球局中按下打开 Golf Menu。
  - Menu：系统 controls/settings；长按开关机。
  - Back：返回上一屏。
  - Device Overview：https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-C4EE9EF3-5007-41D9-B84F-4582440483AE.html

### 1.2 开局

- `OFFICIAL`：`Action → Play Golf → GPS → 附近仅一场则自动选场，否则选场 → 是否记分 → tee → 洞主屏`。
- `OFFICIAL`：开局时若距某洞最远后发球台不超过 30 m，可从该洞开始；否则默认第 1 洞。
- `MULTI-SOURCE`：正常环境下 GPS 常在数秒内锁定；基础距离/计分首轮即可使用，高级能力需一两轮熟悉。
- Playing Golf：https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-2E8EE4BB-67F6-4B99-9E6C-83CB12DB33C3.html
- Starting on Any Hole：https://support.garmin.com/en-US/?faq=rRbecOVS7z9TxsObte8PY5

### 1.3 抬腕第一眼 / 洞主屏

- `OFFICIAL`：默认洞主屏不是全屏地图。它明确采用：
  - 顶部：洞号与 Par。
  - 左侧：果岭后/中/前距离，中距最大且以黄色强调。
  - 右侧：彩色洞图。
  - 地图上的白色弧线：用户在 Golf Settings 中设置的平均 Driver Distance；它是事实标尺，不是 AI 路线或散布。
  - 上一杆距离：显示在洞主屏顶部。
- `OFFICIAL + CONTINUOUS VIDEO`：Virtual Caddie 有效时，标准 Hole View 不是“零球童”。Garmin 官方产品图直接显示推荐杆 `7I`、当前一杆瞄准线和散布图；连续实机 `2:15–2:23` 显示 F/M/B、洞图、Driver Arc 与底部 `3W` 推荐入口同时存在。点击后约 `2:25` 才进入完整球童页。
- `OFFICIAL`：S70 **存在逐洞成绩环**。实体表圈刻有 1–18 洞指示；打球并显示成绩时，屏幕在各洞号旁绘制彩色短弧，表示该洞相对 Par 的成绩。颜色为：紫 `+5 或更差`、粉 `+4`、红 `+3`、橙 `+2`、黄 `+1`、绿 `Par`、浅蓝 `-1`、深蓝 `-2 或更好`。
- `OFFICIAL`：这是一套“物理洞号刻度 + 屏内动态成绩色段”的混合设计，不是单一当前成绩图标。第 9 洞官方示意图显示 1–8 洞已有色段，当前洞 9 另有白色轮廓指示。
- 官方主屏图片：
  - https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/Shared/GUID-C45078E4-2C84-4548-8202-0E48F759EFF5-high.jpg
- 官方成绩环证据：
  - https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-D5D74362-3004-4930-BC95-24CFF5988B98.html
  - https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/Shared/GUID-CEEEEA02-C713-40F8-BC5F-6BC55A8077C0-high.jpg
  - https://www8.garmin.com/manuals-apac/webhelp/approachs70/ZH-CN/GUID-557982D6-3E5A-4D5D-B12A-C82ADBC83742-5968.html
  - 本仓库纠错审计：[S70 成绩环证据更正](2026-07-15-s70-score-history-ring-evidence-correction.md)
- Virtual Caddie / Driver Arc 专项证据：[2026-07-16-s70-virtual-caddie-driver-arc-evidence.md](2026-07-16-s70-virtual-caddie-driver-arc-evidence.md)
- `MULTI-SOURCE`：亮屏 AMOLED 在强日光下清楚；S70 的快速价值是抬腕完成下一杆决策，不必掏手机。
- `UNKNOWN`：暗态 AOD 的精确内容、亮度、抬腕延迟与页面恢复粒度没有官方高尔夫专属说明；长期用户对抬腕可靠性和暗态阳光可读性有负面反馈。
- `UNKNOWN`：Touch Target、全图缩放、Big Numbers、AOD、Green View、PinPointer 各面是否保留或隐藏成绩色段，仍需真机逐面核验；不能从洞 1、尚无历史成绩的示意图反推“不存在成绩环”。

### 1.4 PlaysLike

- `OFFICIAL`：默认显示实际 F/M/B；点任一距离切换为 PlaysLike，不是实际与 PlaysLike 永久并列常显。
- `OFFICIAL`：继续上滑可查看高差、风、空气密度分别造成的距离变化。
- `OFFICIAL`：Wind/Weather 可分别关闭；Tournament Mode 禁用 PlaysLike。
- `OFFICIAL`：风和空气密度依赖与 Garmin Golf/Connect 的手机连接。
- 手册：https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-4D16CAF9-F14F-44D0-8860-B5BEF6DB9F72.html
- Support：https://support.garmin.com/en-US/?faq=ouNixcnGq94RQ20k6yEV18
- `MULTI-SOURCE`：用户有时需重新打开手机 App 才恢复风数据；动态数据的手机依赖会暴露为静默缺失或陈旧。

### 1.5 地图、目标、障碍、果岭

- `OFFICIAL`：点洞图进入更详细地图；再点地图放置 target circle。
- `OFFICIAL`：同时显示“当前位置→目标”和“目标→旗位”的两段距离。
- `OFFICIAL`：右侧 slider 缩放；官方没有说明自由拖拽平移。
- `OFFICIAL`：Hazard/Layup 是独立地图状态，显示障碍类型、前后沿距离，用左右箭头循环。
- `S70 VISUAL + CROSS-DEVICE OFFICIAL`：红/白/蓝/黄单点是距旗保留 100/150/200/250 码或米的 layup 点；S70 画面已确认这些色点，逐色文字语义由 Garmin J1/G80 当前官方手册交叉确认。成对障碍标记与两个距离是 hazard 前后沿，不能当成两个 layup 点。
- `OFFICIAL`：Green View 从 `Action → View Green` 进入；在放大果岭上点/拖旗，右侧 slider 缩放；旗位只保存当前轮，返回后主屏距离更新。
- Touch Target：https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-2AC0AEAF-190C-43BB-9E5B-DE33A77B88A8.html
- Hazards：https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-622EE307-DA4A-4809-8C83-7E7B6BBF9826.html
- Green View：https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-66DDB1DE-89C4-46F3-A6FF-577C29792FCC.html
- `MULTI-SOURCE`：评测认为触摸响应良好但略逊 Apple Watch；部分 S62→S70 长期用户认为每洞进入/等待/缩放流程 clunky。地图操作体验存在真实分歧。

### 1.6 Golf Menu / 仪表面

- `OFFICIAL`：球局中 Action 打开 Golf Menu。当前 v5 项目包括：View Green、Virtual Caddie、Change Hole、Change Green、Scorecard、PinPointer、Wind、Round Info、Measure Shot、Club Stats、Custom Targets、Sunrise & Sunset、Settings、End Round。
- Golf Menu：https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-07681BF1-996F-4151-963B-B6D7CA7CF910.html
- 产品心智：这些能力围绕同一个当前洞切换“仪表面”，Back 返回当前洞；不是五个常驻兄弟页。

### 1.7 Virtual Caddie

- `OFFICIAL`：需至少五轮带 Approach sensors 或 Club Prompt 的杆数据并上传；每轮需连接配对手机/Garmin Golf。
- `OFFICIAL`：Golf Settings 可启用 automatic 或 manual virtual caddie club recommendations；完整页也可从 Action → Virtual Caddie 进入，并用左右箭头切其它球杆/组合。
- `OFFICIAL`：显示推荐球杆/组合、平均预计杆数、历史散布区；若散布区覆盖果岭，会显示上果岭概率。
- `OFFICIAL IMAGE + CONTINUOUS VIDEO`：Virtual Caddie 是两层结构：根页条件显示当前一杆的轻量推荐；点击后才进入包含组合、替代方案、`AVG. STROKES` 与详细散布的完整页。S70 根页没有无条件 `you → layup → green` 的确定性整洞路线。
- `OFFICIAL`：产品页将 `57145-3.jpg` 标为 `IMPROVED VIRTUAL CADDIE`，并说明 shot dispersion chart 用于快速显示不同选杆可能涉及的障碍。
- `CONTINUOUS VIDEO`：约 `2:25–3:05` 依次显示 `3W → 8I = 4.3`、Driver → PW = `4.5`、3 Hybrid → 3 Hybrid = `4.3`、4 Hybrid → 3 Hybrid = `4.5`。这能否定“expected strokes = 组合球杆数量”或 `len(steps)`。
- 官方图：https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/Shared/GUID-77145969-CC31-4EDF-BE22-D211174B14D0-high.jpg
- 官方产品图：https://res.garmin.com/it-production/image/upload/v1679492352/Product_Images/en/products/010-02746-02/g/57145-3.jpg
- 手册：https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-5A77A7DF-49E0-4E35-A23A-2402E7043FA7.html
- Golf Settings：https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-CBFA7E15-FBF2-4C92-A5A7-C9026972D21B.html
- 连续实拍：https://www.youtube.com/watch?v=O7jZz_4Ki70
- `DESIGN CAUTION`：S70 显示这些数字不代表本产品当前的 expectedStrokes/概率已经校准。未校准数字不能因为“Garmin 有”就直接复用。
- `UNKNOWN`：Garmin 未公开 `AVG. STROKES` 的推杆、短杆、罚杆或固定 `+2` 公式，也未公开 Automatic recommendation 的重算频率、TTL、滞回或离线缓存。

### 1.8 AutoShot、Club Prompt 与补杆

- `OFFICIAL`：AutoShot 需要开启记分、戴在前导腕、手表处于正确洞；正常完整挥杆最可靠，推杆不检测，轻切/短 wedge 常漏。
- `OFFICIAL`：检测后顶部显示上一杆距离；Measure Shot 可查看上一杆/全部杆。
- `OFFICIAL`：开启 Club Tracking 后，每次检测到击球会提示选择球杆；CT10 全套可替代 prompt。
- `OFFICIAL`：漏检必须在漏杆发生位置 `Action → Measure Shot → Action → Add Shot` 补录，然后走到下一球位。
- AutoShot Support：https://support.garmin.com/en-US/?faq=PMDFD4p5N74JYxSamVvGg6
- Measured Shots：https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-36C094EA-AFF5-4A82-BBEC-E91C445DCF86.html
- Manual Shot：https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-F265290C-F32C-48DF-B0E0-5F5147D930F0.html
- `MULTI-SOURCE`：Club Prompt 同时是一次点击的球杆输入和隐性的“已识别本杆”反馈。
- `MULTI-SOURCE`：失败反馈不对称；用户可能到第二杆或走出 5–10 码才发现漏记。
- `MULTI-SOURCE`：CT10 可补漏，但放下/多拿 wedge/修 pitch mark/敲地/倚 putter 可误记，部分用户拆掉 putter CT10。
- 设计含义：应复制低摩擦确认，不应复制“必须事前补杆、事后难修”的死角。

### 1.9 计分与统计

- `OFFICIAL`：开启记分后，洞末提示录分；默认总杆为 Par，可调整。
- `OFFICIAL`：统计链为总杆（已含推杆）→ 推杆 → Par 4/5 的球道命中/左/右 → 罚杆。
- `OFFICIAL`：推杆只做统计，不再次增加总杆。
- `OFFICIAL`：Par 3 或使用 Approach sensors 时不显示 fairway 项。
- `OFFICIAL`：记分可随时从 Action → Scorecard → 洞修改。
- `MULTI-SOURCE`：关闭 Stat Tracking 后只问总分，系统对提示为何消失解释不足。
- Recording Stats：https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-DDEFEB56-BE04-417D-834F-1CBA63FE67C0.html
- Support（Scoring 段）：https://support.garmin.com/en-US/?faq=PMDFD4p5N74JYxSamVvGg6

### 1.10 自动换洞

- `OFFICIAL`：走近下一洞最远后发球台时自动换洞；Garmin 建议先完成上一洞记分。
- `OFFICIAL`：若自动换洞失败，可 `Action → Change Hole → 上下滑 → 选洞` 手动恢复。
- `OFFICIAL`：手表必须处于正确洞，否则下一洞开球可能不被 AutoShot 记录。
- Automatic Transition：https://support.garmin.com/en-US/?faq=leUAomDugD7UxMH9iQheTA
- `UNKNOWN`：自动换洞精确 geofence 半径、驻留时间、触觉与动画未公开；30 m 仅由起始洞判定 FAQ 明确给出，不能挪作自动换洞阈值。

### 1.11 Big Numbers、AOD 与锁定

- `OFFICIAL`：Big Numbers 是明确的持久球局模式，不是长按临时页。
- `OFFICIAL`：Big Numbers 隐藏完整洞图和 AutoShot banner；上下滑看 PlaysLike 中距、风、handicap；Action → View Map 可临时看地图。
- `OFFICIAL`：Garmin Support 明确写明 Virtual Caddie 不能与 Big Numbers 或 Tournament Mode 同时使用；Tournament Mode 不只是禁用 PlaysLike，也必须禁用 Virtual Caddie。
- 官方图：https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/Shared/GUID-6EFF581A-025C-4B2B-BB9A-EB480505B57F-high.jpg
- 手册：https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-82EAB5FB-1BCD-4D0B-95F0-DE4CC5D7BEE9.html
- View Map：https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-CE27ADA2-5644-4106-BDF8-04E7D7B8DB5A.html
- Virtual Caddie Support：https://support.garmin.com/en-US/?faq=sjA1cXNnKf0nLANJY3T627
- `OFFICIAL`：S70 支持 During Activity AOD、Wrist Gesture、Timeout、Lock Device/Auto Lock。
- `MULTI-SOURCE`：亮屏阳光可读；暗态 AOD 和抬腕可靠性存在负面长期反馈。手套误按实体键有单一直接报告；雨水湿屏影响尚未形成 S70 专属强证据。

### 1.12 结束、暂停、保存、同步

- `OFFICIAL`：标准收口是 `Action → End Round`，然后可看统计并选 Save / Edit Score / Discard / Pause Round。
- `OFFICIAL`：Save 回表盘；Pause 可稍后继续；结束并保存后才 ready to sync。
- `OFFICIAL`：Scorecard 可在 Garmin Golf app/Web 赛后修改（官方只保证 stroke play）。
- Ending：https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-5B933B1F-97C2-43FA-A10F-7959DAD4FE64.html
- `MULTI-SOURCE`：没有可靠的 9/18 洞自动结束；用户忘记结束后，回家路线可能被计入球局（公开评测实例为 27 miles）。
- `UNKNOWN`：第 18 洞是否在特定固件自动提示结束、Pause 的恢复入口/持久化、强制重启后的精确恢复粒度。

## 2. 长期体验共识与 Garmin 缺陷

### 2.1 强/中强共识

- 抬腕看距比掏手机快，是核心价值。
- 亮屏 AMOLED、洞图、障碍/layup、盲打方向与续航是主要优点。
- AutoShot 对正常全挥总体有用，短切/推杆弱。
- 越追求高精度统计，旗位、漏杆、误杆、CT10、洞后修正的摩擦越明显。
- 手机不是每杆必需，但风、CPE/球场同步、My Bag、统计同步与故障恢复存在隐性依赖。
- Garmin Golf 的赛后分析被多位长期用户认为弱于 ShotScope/Arccos，尤其 strokes gained、趋势和时间筛选。

### 2.2 不应照抄的缺陷

- AutoShot 漏检反馈不明确，补上一杆路径要求用户仍在原击球位置。
- CT10 会把非击球动作误计，尤其推杆与果岭周边。
- 动态风/天气可能静默陈旧或消失。
- 自动换洞依赖地图/CPE/GPS，失败原因不透明。
- 9/18 洞未可靠提醒结束，忘记结束会污染活动距离。
- 暗态 AOD、抬腕可靠性、默认地图缩放体验存在用户分歧。
- 推杆位置受 GPS 精度限制，不应制造伪精确。

## 3. 当前仓库的已证事实

### 3.1 当前不是一套 Watch 产品

- `REPO`：`AICaddieWatchApp.swift:43-64` 有三条互斥入口：
  1. WatchRoundStore 有 round → standalone 多洞 Hub。
  2. 否则 iPhone 推 currentState → legacy 单洞 List。
  3. 都没有 → 本地固定 18 洞、统一 Par 4 的“练习记分”。
- `REPO`：生产代码没有从 iPhone 球局调用 `WatchRoundModel.seedRound()`；地图、腕上 GPS、计分卡主要只接在 standalone 分支。
- 设计含义：必须先统一 round coordinator，不能只给某条分支换皮。

### 3.2 根页与推进因果错误

- `REPO`：standalone 根页是摘要 Hub，地图是“球道图”二级按钮：`WatchRoundHomeView.swift:69-120`。
- `REPO`：`WatchRoundModel.saveActiveHole():187-204` 保存 score/putt/penalty 后强制 `goToNextHole()`。
- `REPO`：当前没有 GPS→候选洞→确认/自动切洞的状态通路。
- `REPO`：最后一洞保存后只是 `goToNextHole()` 无动作，不会进入结束流程。

### 3.3 地图资产可复用，当前交互不可直接复用

- 可直接或修改复用：`WatchGeoMath`、`WatchHoleImageStore`、`WatchHoleMapGeometry`、topo 图片传输、route/anchor 计算、Canvas 绘图原语。
- `REPO`：`WatchHoleMapView` 只有 tap、drag、long press；全 Watch target 没有 `digitalCrownRotation`，但 UI 画了“转表冠缩放”。
- `REPO`：自由测距用当前点→pin 的像素跨度推统一 yards-per-pixel，不是经纬度反投影地理距离。
- `REPO`：拖旗直接发生在全洞小图；`liveMeasuredPx`/`livePinDrag` 无 callback、事件或持久化。
- 设计含义：保留渲染底座，重做状态、输入、坐标与持久化。

### 3.4 当前没有逐杆真相模型

- `REPO`：`WatchInputKind` 只有 score/putt/penalty/club/distance，没有 shot、location、accuracy、shotId、target。
- `REPO`：distance 被手机桥和直连后端映射为 club event；两条映射校验规则还不一致。
- `REPO`：同洞多个击球无法由 `WatchRoundState.applying()` 表达；club 只是覆盖 selectedClub。
- `REPO`：score/putt/penalty 是三个独立事件，完成本洞不是原子语义。
- 设计含义：AutoShot、补杆、上一杆、对账、逐杆地图不能先靠 UI 假装存在。

### 3.5 定位与后台生命周期不足

- `REPO`：WatchLocationProvider 保留 accuracy/timestamp，但消费端只判断 fix 是否存在便覆盖距离/位置。
- `REPO`：没有精度、新鲜度、滞回、候选洞可信度的 UI/状态门控。
- `REPO`：GPS 在 app appear 时启动，尚无 HKWorkout/background 球局生命周期。

### 3.6 数据安全与同步问题

- `REPO`：standalone 与 legacy 各有独立 outbox。
- `REPO`：直连后端与手机中继的事件校验/映射不一致；直连收到任意成功 2xx 后会把整批 eventIds 视为成功。
- `REPO`：`confirmFinish()` 在无后端配置时仍 `finishLocally()` 清空 round/outbox；开始页却承诺“联网后自动同步”。
- `REPO`：成功结束后本地已完成轮次也立即清空，无 Watch 端历史。
- 设计含义：结束、暂停、完成待同步、重试、历史留存必须进入正式状态机。

### 3.7 当前规范互相冲突

- 2026-06-22 spec：地图为 Home、表冠缩放、长按菜单、位置触发。
- 2026-07-10 control spec：五个顶层横滑页、表冠沿洞轴、长按大字、屏幕不自动跳洞。
- 当前代码：Hub 根页、地图二级、自绘返回、长按大字、假的表冠缩放提示。
- 设计含义：旧“定稿/宪法”只能作历史输入，不能作为新设计约束。

## 4. 对此前纯 Fable 报告的事实修正

此前报告：`docs/reviews/2026-07-14-claude-fable-s70-experience-research.md`。该会话全程纯 `claude-fable-5`、max effort、无 fallback，但 WebSearch/WebFetch 权限全部被拒，因此 S70 侧是 MODEL-RECALL。

必须纠正：

1. S70 是三实体键 + 触屏，不是双键。
2. 默认洞主屏就是左 F/M/B + 右洞图，不是全屏地图叠数字；当前地图的左右分栏方向接近官方。
3. PlaysLike 由点距离切换查看，不是实际/等效永久并列常显。
4. 开启 Club Tracking 后，AutoShot 检测成功会触发 Club Prompt；不是场中永远零输入。
5. Virtual Caddie 明确显示平均预计杆数，散布覆盖果岭时还显示上果岭概率。
6. 官方未确认第 18 洞自动弹结束；标准流程仍是 Action → End Round。
7. 自动换洞的官方目标是下一洞最远后 tee，不可简写成“离开果岭即换洞”。
8. Virtual Caddie 有“根页条件单杆建议 + 点击后完整球童”两层；“根页完全零球童”和“根页常驻整洞两段路线”都不符合新核验的一手证据。
9. Driver Distance Arc、当前一杆瞄准线和历史散布是三个不同对象；Big Numbers/Tournament Mode 与 Virtual Caddie 互斥。

仍成立且重要：

- 当前 save score → next hole 的因果错误。
- 五页横滑不是 S70 的原生结构。
- 单一当前洞根屏 + 浅仪表面比 Hub/多页更接近专用仪器心智。
- Green View 应是放大果岭专用面。
- 当前菜单、结束留存、表冠绑定和事件账本均不完整。

## 5. 设计必须同时解决的四个维度

### A. 视觉层级

- 默认首帧同时保留 F/M/B、洞图、洞号/Par、上一杆。
- 当前主屏不要堆满确定性整洞多杆路线、未校准数字、同步状态等所有信息。
- AI 差异应是“条件出现的当前一杆推荐杆、瞄准线和真实散布 + 按需展开完整 Caddie”，不是让主洞屏变成整洞沙盘；数据门槛不满足时应完整退化为纯事实根页。
- 42/47 mm S70 与 Apple Watch 41/42/44/45/46/49 mm 不能只等比缩放。

### B. 响应与操控节奏

- 需要 Apple Watch 上稳定的 Action 等价入口与返回语义。
- 表冠控制当前屏的连续/离散轴；不得出现没有绑定的假 affordance。
- 抬腕后优先恢复当前洞核心读数；AOD 与亮屏必须分别设计。
- 触觉、动画与自动提示必须有明确矩阵，不能靠各屏临时决定。

### C. 自动记杆与洞末流程

- 在 AutoShot 真机数据未过线前，必须有可靠的一键记杆/补上一杆。
- 自动检测成功需要明确而不打断挥杆的确认；Club Prompt 不能是唯一成功信号。
- 计分与换洞必须解耦；score/putts/fairway/penalty 的出现时机和对账语义需正式定义。
- GPS 候选洞需要精度、新鲜度、滞回、低置信恢复与手动换洞。

### D. 可靠性与异常恢复

- 统一 coordinator、ledger/outbox 与事件契约。
- finishedPendingSync、paused、resume、discard、retry、history 都必须有状态。
- 上传失败、无配置、杀进程、低电、手机离线时零数据丢失。
- 漏杆、误杆、错洞、忘记结束、动态数据陈旧均需腕上可理解和可恢复。

## 6. 待真机裁决，不得冒充事实

- S70 42/47 mm 的直接逐屏与触摸目标对照。
- 高尔夫 AOD 暗态内容、抬腕延迟、恢复页面与缩放/target 持久。
- 自动换洞精确 geofence、驻留、触觉和计分 prompt 的相对时序。
- Club Prompt 精确延迟、跳过/撤销和补杆后行为。
- Virtual Caddie Auto 模式何时出现、断网是否缓存。
- 雨水/湿屏、厚手套、Auto Lock 的真实 S70 场上表现。
- Apple Watch AOD、Digital Crown、后台定位/Workout、Ultra Action Button 的真机限制与续航。

## 7. 给设计评审者的任务

1. 先从本证据包独立判断最优 Watch 产品模型，不接受“五页/三页/单根页”任何旧答案作为前提。
2. 同时处理视觉、操控节奏、自动流程、可靠性四维；不能只优化其中一维。
3. 给出 2–3 个真正不同的概念方向、取舍、推荐和淘汰理由。
4. 明确哪些 S70 行为应忠实复制、哪些应做 Apple 翻译、哪些 Garmin 缺陷应主动修正。
5. 对当前工程给出直接复用/修改复用/淘汰矩阵，设计不得假设不存在的 AutoShot 或逐杆事件已完成。
6. 所有未知项进入真机验证计划；不可用模型记忆补洞。
7. 当前只交付概念设计与对抗意见，不写实现代码，不把输出冒充用户已批准的正式 spec。
