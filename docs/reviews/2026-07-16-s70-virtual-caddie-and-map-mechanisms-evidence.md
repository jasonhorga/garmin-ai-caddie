# Approach S70 根页地图与 Virtual Caddie 机制证据审计

> 日期：2026-07-16 UTC  
> 状态：VERIFIED RESEARCH INPUT；2026-07-17 Owner 已批准 D02 直接对标 S70 的可观察双层行为，当前 `CURRENT` 为 D04  
> 审查：Codex + 纯 `claude-fable-5` max effort、禁 fallback 对抗复核  
> 范围：S70 Hole Root、地图目标、Driver Distance、Layup、Touch Target、Virtual Caddie，以及当前工程复用边界  
> 实施状态：只改评审文档，不改产品代码

## 0. 结论

此前把 D02 问成“整条球童路线留在根页，还是全部移入详情”是错误的二分法。S70 的公开证据显示的是三层渐进披露：

1. **事实根页**：洞号、Par、F/M/B、洞图、位置、Driver Distance 弧、成绩环；
2. **条件单杆球童层**：仅在 Virtual Caddie 有真实、有效建议时，在同一根页增加推荐杆、当前一杆瞄准线、目标中心与按本人该杆历史数据形成的散布框；
3. **完整 Virtual Caddie**：点根页推荐杆后进入，查看杆组、平均预计杆数、左右备选、同一散布区及可能的上果岭概率。

因此新的联合推荐不是保留当前实现，而是：

> **D02-C′：保留 S70 式条件单杆球童机制；淘汰当前无条件常驻的整洞两段路线、固定尺寸假散布和启发式假落点。**

这个结论仍需 Owner 确认。本文只修正事实、方案定义和联合建议，不把 D02 标为 `DECIDED`。

## 1. 为什么旧问题失真

旧 D02 把以下三种不同对象混成了“路线”：

- Driver Distance Arc：用户设置的平均开球距离弧；
- Touch Target / Layup：用户主动进入地图详情后查看或选择的目标；
- Virtual Caddie：根据洞形、风和个人球杆历史生成的当前一杆建议。

当前代码又额外发明了第四种对象：

- `you → layup → green` 的整洞两段确定性路线，并在 layup 上画固定 30×26 px 椭圆。

这第四种对象没有得到 S70 官方手册、官方产品图或连续实拍支持。它也不是当前决策引擎的真实逐杆输出：路线来自赛前中心线和 Driver 启发式，玩家移动时只更新 `you`，目标与后半段路线不随当前一杆重新求解。

## 2. 证据等级

| 等级 | 含义 |
|---|---|
| `OFFICIAL-TEXT` | Garmin 当前官方手册或 Support 明文 |
| `OFFICIAL-VISUAL` | Garmin 官方产品图、新闻稿图或官方教程连续画面 |
| `CONTINUOUS-DEVICE` | 可看到点按前后关系的连续实机视频 |
| `CROSS-DEVICE-OFFICIAL` | Garmin 其它 Approach 设备的官方手册；只用于解释跨产品通用符号，不冒充 S70 v5 原文 |
| `REPO` | 当前仓库源码直接可核 |
| `UNKNOWN` | 公开证据不足，必须由真机、数据或原型解决 |

## 3. 六种地图元素必须分开

| 元素 | 已核行为 | 根页关系 | 证据 |
|---|---|---|---|
| 事实层 | Hole/Par、F/M/B、洞图、当前位置、成绩环 | 始终存在；数据退化时按事实降级 | `OFFICIAL-TEXT` + `OFFICIAL-VISUAL` |
| Driver Distance Arc | 用户在 Golf Settings 设置平均开球距离，地图显示一条弧 | 有设置时可显示；不是 AI | `OFFICIAL-TEXT` |
| 固定 Layup 距离点 | Garmin 通用颜色为红 100、白 150、蓝 200、黄 250 | S70 官方图可见同组彩色点；具体颜色语义采用跨设备官方佐证，不写成 S70 v5 明文 | `OFFICIAL-VISUAL` + `CROSS-DEVICE-OFFICIAL` |
| Touch Target | 点地图进入详情，再放置目标；显示“当前位置→目标”和“目标→旗”两段距离 | 用户主动进入详情，不是自动球童路线 | `OFFICIAL-TEXT` |
| 自动轻量 Virtual Caddie | 推荐杆 + 当前一杆瞄准线 + 目标中心 + 真实历史散布框 | 有有效建议时叠加在根页；无数据、关闭或模式不允许时消失 | `OFFICIAL-VISUAL` + `CONTINUOUS-DEVICE` + S62 `OFFICIAL-TEXT` |
| 完整 Virtual Caddie | 杆组、AVG. STROKES、左右备选、散布、上果岭概率 | 点根页推荐杆进入独立仪表面 | `OFFICIAL-TEXT` + `CONTINUOUS-DEVICE` |

## 4. 根页轻量层的视觉证据

### 4.1 Garmin 官方产品图

官方 S70 产品图：

- https://res.garmin.com/it-production/image/upload/v1679492352/Product_Images/en/products/010-02746-02/g/57145-3.jpg

同一屏明确出现：

- `#15 Par 4`；
- 左侧 F/M/B；
- 右侧洞图；
- 底部 `7I` 推荐杆；
- 从球员位置通往目标的白色瞄准线；
- 果岭附近白色圆角框与框心目标点。

新闻稿同构图：

- https://s34181.pcdn.co/en-US/newsroom/wp-content/uploads/2023/05/MCJT-57229_ApproachS70_Press-Release-Image_v2.png

这不是完整 Caddie 页：屏幕仍保留 Hole Root 的 Hole/Par/F/M/B 布局，没有 AVG. STROKES、左右换杆箭头或确认按钮。

### 4.2 白色圆角框为何应解释为散布

S70 手册 Virtual Caddie 官方标注图：

- https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/Shared/GUID-77145969-CC31-4EDF-BE22-D211174B14D0-high.jpg

手册把编号 3 明确定义为：

> 下一杆使用推荐球杆时，根据该杆击球历史得到的 shot dispersion area。

该编号指向的正是白色圆角框。官方根页产品图和连续实机根页出现同形、同位置语义的框；完整页点入后仍使用同一框。因此最严格、不过度推断的表述是：

> 这是“目标中心 + 散布范围”的复合地图元素；框心承担本杆瞄准目标，框幅表达个人历史散布。

没有证据支持“完整页相同白框是散布，根页白框却只是无散布语义的普通目标框”。

### 4.3 连续实机点按链路

视频：

- https://www.youtube.com/watch?v=O7jZz_4Ki70

关键时序：

| 时间 | 画面 | 证明什么 |
|---:|---|---|
| 2:15 | Hole Root 底部显示 `3W`；地图已有线、目标点和白框 | 轻量球童内容与 F/M/B、Hole Map 同屏 |
| 2:20 | 用户点按根页推荐杆 | 推荐杆是完整 Caddie 入口 |
| 2:23 | 点按后的过渡画面 | 不是横滑到兄弟根页 |
| 2:25 | 完整页显示 `3W + 8I`、`AVG. STROKES 4.3`、左右替代 | 完整推理详情在独立仪表面 |
| 2:27 | 完整页继续显示同一目标/散布复合元素 | 根页和详情共享同一当前一杆建议，而非两套无关路线 |

Garmin Singapore 官方教程也在约 80.87 秒展示 F/M/B + `4h` + 瞄准线/散布框：

- https://www.youtube.com/watch?v=zpaxL30zNqU

### 4.4 S62 前代官方交互文本

S70 当前 v5 Hole View 文字只列基线元素，没有描述 Automatic Virtual Caddie 的条件渲染。S62 官方手册补足了这一交互机制：

- Hole View 把 `Virtual caddie club recommendation` 明列为根页元素；
- 点推荐可查看计算的平均杆数和其它推荐；
- 换杆后地图更新新的击球方向目标；
- 建议会随球场进程自动重算。

来源：

- https://www8.garmin.com/manuals/webhelp/GUID-7681996C-530F-4C69-80C4-3CD20D82746C/EN-US/GUID-0DD95F70-6EC7-49FA-B821-CE790EFDB2E5.html
- https://www8.garmin.com/manuals/webhelp/GUID-7681996C-530F-4C69-80C4-3CD20D82746C/EN-US/GUID-9763BF39-464E-4501-9C4C-8684FDD61576.html

该文本与 S70 官方图、官方教程和连续实拍一致，因此可以用来解释 S70 公开图中的层级关系；不能用它推导 S70 未公开的精确时序阈值。

## 5. 开关与法定零状态

S70 Golf Settings 明确支持 `automatic or manual virtual caddie club recommendations`，且需先积累五轮带球杆归属的数据：

- https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-CBFA7E15-FBF2-4C92-A5A7-C9026972D21B.html

Garmin Support 当前 FAQ 进一步明确：

- Virtual Caddie 不能与 Big Numbers 同用；
- Virtual Caddie 不能与 Tournament Mode 同用。

来源：

- https://support.garmin.com/en-US/?faq=sjA1cXNnKf0nLANJY3T627

因此 Apple Watch 设计需要一个明确的法定零状态：

- 无建议；
- 数据不足；
- 置信不足；
- 用户选择 Manual/Off；
- Big Numbers；
- Tournament Mode；

以上状态都不显示推荐杆、瞄准线或散布框，也不能用假目标填空。

## 6. D02 三个候选

### A — 维持当前整洞路线

根页无条件显示 `you → layup → green` 两段路线和固定散布。

优点：演示信息丰富；用户已看过该视觉。

否决理由：

- 与 S70 当前一杆机制不同；
- 目标来自赛前 Driver 启发式；
- 玩家移动时目标不重算；
- 固定 30×26 px 椭圆是假数据；
- 缺数据时 60% 落点仍制造确定性；
- 一杆打完后整洞路线可能立即失真。

### B — 根页完全没有球童视觉

所有推荐、目标和散布都进入 Map Detail / Caddie。

优点：根页最稳定、最清楚。

问题：新的一手证据已经证明 S70 Automatic 模式的价值正是抬腕在根页直接看到本杆建议；全部下沉会损失 S70 体感和最高频价值。

### C′ — S70 式条件单杆球童层

根页始终先成立事实层。只有当前一杆建议真实、有效、足够可信且模式允许时，才增加：

- 一行推荐杆 Button；
- 当前位置到目标的瞄准线；
- 目标中心；
- 由本人该杆历史数据驱动的散布框。

点推荐杆进入完整 Virtual Caddie：

- 杆组与左右替代；
- 同一目标/散布；
- 经校准的 AVG. STROKES；
- 条件成立时的上果岭概率；
- 明确确认/返回。

无有效建议时，C′ 的表现等于 B；但 B 不是唯一常态，而是 C′ 的零状态。

**联合推荐：C′。**

## 7. 当前工程复用判断

### 7.1 可直接或轻改复用

- topo 底图、缓存与文件传输；
- `Canvas` 底图和绘制原语；
- GPS/WGS84→topo px 投影；
- 腕上 GPS 重算 `you` 与 F/M/B；
- F/M/B 左列与成绩环；
- 推荐杆、候选打法、置信度、球杆样本量的现有数据链。

主要源码：

- `WatchHoleMapView.swift:145-175,257-293,314-338,386-454`
- `AICaddieWatchApp.swift:71-95`
- `WatchRoundState.swift:3-69,125-181`

### 7.2 修改后复用

| 当前能力 | 修改方向 | 证据位置 |
|---|---|---|
| 根页推荐 chip | 改为有门槛的 Button；点击进入正式 Caddie screen；不以 selectedClub 兜底冒充建议 | `WatchHoleMapView.swift:193-200`、`WatchRoundContainerView.swift:145-184` |
| 路线绘制原语 | 只保留线、点、框的绘制能力；数据语义改成当前一杆 target + 真实 dispersion | `WatchHoleMapView.swift:295-312` |
| 地图 contract | 从五个静态中心线锚点改为当前一杆 target、散布尺寸/形状、数据来源、样本量、置信和生成时间 | `WatchRoundState.swift:100-122` |
| 腕上 GPS | 不只移动 `you`；位置、lie、pin、风或换杆变化后触发建议重新求解 | `AICaddieWatchApp.swift:71-83` |
| iPhone→Watch 桥 | 不再用赛前 `landingM` 生成球童路线；转发当前一杆决策和可审计的散布 contract | `CurrentHoleView.swift:999-1042`、`WatchEventBridge.swift:371-393` |
| Caddie 数据 | 可复用球杆样本量、median、p10/p90 和置信骨架；需补 2D 横向散布/投影，不能用一维 carry window 冒充 Garmin 散布框 | `WatchRoundState.swift:3-69`、`decision.py:2511-2528` |
| 完整 Caddie | 新建正式 Watch screen/state；复用 options 数据，但 AVG. STROKES 上屏前必须完成口径校准 | `WatchRoundState.swift:45-69,150-181` |

### 7.3 必须淘汰

- 无条件常驻的 `you → layup → green` 两段整洞路线：`WatchHoleMapView.swift:295-301`；
- 固定 30×26 px 假散布常量：`WatchHoleMapView.swift:303-308`；
- 缺数据时取全洞 60% 的假落点：`WatchEventBridge.swift:371-393`；
- Watch 地图继续消费赛前 `holePrep.landingM`：`CurrentHoleView.swift:999-1012`；
- 用赛前 Driver 启发式生成当前球童目标：`course_prep.py:505-528`；
- 无绑定的表冠缩放轨道和“转表冠缩放”：`WatchHoleMapView.swift:218-244`；
- 把 `expectedStrokes = len(steps)` 当作 Garmin 的平均完洞杆数：`decision.py:759-793`；
- 把 baseline 为 1.0 的单杆风险分值当作预计完洞杆数：`decision.py:2656-2697`。

## 8. 仍然 UNKNOWN，不转嫁给 Owner

以下由工程、真机或数据证据解决，不再另开 Owner 选择题：

1. Automatic 模式在每杆后的精确出现、收起和刷新时机；
2. Manual 模式接受建议后，根页是否保留本杆叠加；
3. S70 根页散布框与位置变化的动画/刷新频率；
4. 数据不足时 Garmin 是否隐藏整套叠加，还是允许只有杆牌；本产品推荐更严格地整套隐藏；
5. Apple Watch 41/42 mm 同时放置 F/M/B、成绩环、推荐杆和散布框的可读性；
6. 本产品真实 2D 散布最少样本、异常值处理、横纵轴计算与朝向；
7. AVG. STROKES 与上果岭概率的校准和发布门；
8. Big Numbers、AOD、Tournament Mode 下的精确恢复页和动画。

## 9. 纯 Fable 复核审计

最终聚焦会话：

- session：`eaff234d-a068-4811-9cb1-9dfa0c7dc262`；
- CLI：Claude Code `2.1.211`；
- model：`claude-fable-5`；
- effort：`max`；
- 未提供 `--fallback-model`；
- 环境：`CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK=1`；
- 环境：`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`；
- terminal_reason：`completed`；
- permission_denials：空；
- 最终 `modelUsage`：只有 `claude-fable-5`。

Fable 第一份最终稿曾错误写出“散布只在完整页，从不在根页”。Codex 用 Garmin 官方标注图中编号 3 的散布框、官方根页产品图和连续实机根页的同形白框反攻；同一纯 Fable 会话逐图复核后明确撤回，最终结论改为：

> 根页与完整页共享“瞄准线 + 目标中心 + 真实散布框”；完整页额外提供换杆、平均杆数和概率。

这次纠错说明 Fable 的作用是独立对抗，不是给 Codex 结论盖章；最终结论以可复查证据和双方纠错后的交集为准。

## 10. 当前唯一 Owner 问题

> D02：是否同意采用 C′——Hole Root 平时只显示事实；当当前一杆存在真实、有效、足够可信且模式允许的球童建议时，显示推荐杆 Button，并在地图上显示本杆瞄准线、目标点和你的真实散布框；点击进入完整 Caddie。与此同时，彻底淘汰当前整洞 `you → layup → green` 静态路线、固定 30×26 假散布和 60% 假落点？

可回答：

- `同意 C′`；
- `仍要 A：整洞路线常驻`；
- `改选 B：根页完全没有球童视觉`。
