# D02 当前实现复用与淘汰审计

> 日期：2026-07-16 UTC  
> 审查者：Codex 只读源码审计  
> 状态：REVIEW INPUT，不是实施批准  
> 范围：Hole Root 地图、Virtual Caddie、Driver Arc、推荐数据契约、GPS 更新与 expected strokes

## 1. 结论

当前工程不是全部推倒重来。地图底图、Canvas、坐标投影、F/M/B、成绩环、球杆历史和 iPhone→Watch 传输管线有明显复用价值。

不能复用的是当前产品语义：

- 无条件整洞两段路线；
- 固定像素假散布；
- 缺数据时的全洞 60% 假落点；
- 用赛前 landing 冒充当前 AI target；
- 把实际选杆回退成 AI 推荐；
- 两套未校准 expected strokes 冒充 Garmin `AVG. STROKES`。

设计方向如果选择 C′，必须先完成真实 target、散布、样本量、新鲜度与模式门控契约；在此之前根页应退化为纯事实层。

## 2. 可直接复用

| 资产 | 文件与行附近 | 复用理由 |
|---|---|---|
| topo 地图底图、Canvas 与坐标变换 | `mobile/ios/AICaddieWatch/Views/WatchHoleMapView.swift:145-175,257-293` | 已具备图片、渐变和地图坐标到画布的渲染底座 |
| 玩家与旗杆绘制原语 | `WatchHoleMapView.swift:314-338` | 图元本身与新球童语义无冲突 |
| F/M/B 左栏结构 | `WatchHoleMapView.swift:187-213` | 接近 S70 默认 Hole View 的事实层 |
| 18 洞成绩环绘制 | `WatchHoleMapView.swift:386-454` | D01 已确认保留，可继续使用现有 perimeter 算法 |
| Watch GPS → topo 像素投影、腕上 F/M/B 重算入口 | `mobile/ios/AICaddieWatch/AICaddieWatchApp.swift:71-95` | 数学与位置入口可复用；当前更新范围不足，见 §3 |
| 推荐基础数据骨架 | `mobile/ios/AICaddieWatch/Models/WatchRoundState.swift:3-21,45-69` | 已有 clubName、sampleSize、medianM、carryM、confidence 等门控基础 |
| iPhone → Watch target、option、hazard 传输入口 | `mobile/ios/AICaddie/Views/CurrentHoleView.swift:1013-1042` | 可作为新 contract 的迁移起点 |
| WGS84 → topo px 投影与路线插值 | `mobile/ios/AICaddie/Services/WatchEventBridge.swift:396-430` | 可用于真实 current-shot target、Driver Arc 与纵深散布投影 |
| 后端球杆 p10/p90 与 sampleSize | `ai_caddie/caddie/decision.py:2511-2528` | 可支持 v1 纵深散布带，但不等于二维散布框 |

## 3. 修改后复用

### 3.1 根页推荐 chip

位置：`WatchHoleMapView.swift:193-200`

当前只是静态文字。需要改为：

- 只有真实建议存在且门槛通过时显示；
- 成为真实 Button，点击进入正式 Virtual Caddie screen；
- 不用默认文案填空；
- 不把实际使用杆当成推荐杆。

### 3.2 推荐回退逻辑

位置：`mobile/ios/AICaddieWatch/Views/WatchRoundContainerView.swift:145-159`

当前为 `suggestedClub → caddieOptions.first → selectedClub`。`selectedClub` 是实际杆，不能兜底冒充 AI 推荐。应拆成：

- `recommendedClub`：意见层；
- `actualClub`：事实层；
- `selectedAlternative`：用户在 Caddie 中查看或选择的方案。

### 3.3 路线、目标点与散布绘制

位置：`WatchHoleMapView.swift:295-312`

线、点、框的图元可以复用，但语义必须改成：

- 当前一杆瞄准线；
- 当前一杆真实目标中心；
- 由本人该杆历史数据驱动的散布。

当前全栈只有一维 carry P10/P90，因此 v1 最多如实绘制沿瞄准线的纵深散布带。没有横向数据时，不得画完整二维椭圆或矩形。

### 3.4 Watch 地图契约

位置：`WatchRoundState.swift:100-122`

当前只有 `you/pin/layup/apex/greenCtrl` 五个中心线锚点。至少要增加：

- current recommendation ID；
- recommended club；
- target 经纬度与像素坐标；
- p10/p90 纵深散布；
- 将来的横向范围或 polygon；
- sampleSize、confidence、source；
- computedAt、computedForLocation/distance、TTL；
- automatic/manual、Big Numbers、Tournament、caddieEnabled 等资格字段。

### 3.5 地图生成桥

位置：`WatchEventBridge.swift:371-393`

路线插值、仿射投影可以保留，但必须改为消费当前一杆决策。没有有效 target 时，返回“没有球童层”，不能再生成替代落点。

### 3.6 当前洞发送链

位置：`CurrentHoleView.swift:999-1042`

当前已经发送真实 `targetLatitude/Longitude`，但地图仍使用 `holePrep.landingM`。需要让 current decision 的 target、club、dispersion 与 freshness 真正驱动 Watch 地图。

### 3.7 GPS 更新与建议失效

位置：

- `AICaddieWatchApp.swift:71-83`
- `CurrentHoleView.swift:168-197`

当前 Watch GPS 更新只移动 `you`，源码注释明确写着 pin、layup 和 route anchors 不变；iPhone 端也会在 GPS 更新后重新推送旧决定，而不是重算建议。

需要：

- 位置、lie、pin、风、策略或实际击球变化后触发重算；
- Watch 使用自身 GPS 判断决策是否已偏离起算位置；
- 超过阈值时先隐藏陈旧建议，而不是继续展示；
- 用滞回防止 GPS 抖动造成闪烁。

### 3.8 完整 Virtual Caddie

当前正式 Watch screen/state 中没有完整 Caddie 页面。现有 `caddieOptions` 与旧 `WatchCaddieOptionsView` 可作为数据和视觉骨架，但必须进入统一状态机，支持：

- 推荐方案；
- 替代球杆/组合；
- 当前杆真实散布；
- 未校准数字缺席；
- Back 返回同一 Hole Root；
- automatic/manual、离线、Tournament 与 Big Numbers 的明确降级。

## 4. 必须淘汰

| 行为 | 文件与行附近 | 淘汰原因 |
|---|---|---|
| 无条件常驻整洞两段路线 | `WatchHoleMapView.swift:295-301` | 与 S70 根页当前一杆语义冲突 |
| 固定 `30 × 26 px` 假散布 | `WatchHoleMapView.swift:303-308` | 与真实历史散布冲突；只保留数据驱动绘图原语 |
| 缺数据时取全洞 60% 假落点 | `WatchEventBridge.swift:381` | 与任何真实建议无关 |
| 用赛前 `holePrep.landingM` 冒充当前 AI target | `CurrentHoleView.swift:999-1012` | 推荐不会随当前位置与当前决策变化 |
| 赛前 Driver 启发式生成 landing | `ai_caddie/course_prep.py:505-528` | 可用于预处理候选，不得直接成为用户可见 AI 目标 |
| 默认 `"3号木"`、`"推进 · 留100"` | `WatchHoleMapView.swift:59-60` | 假推荐污染事实层 |
| 没有 Crown 绑定却画缩放轨道和“转表冠缩放” | `WatchHoleMapView.swift:218-244` | 假 affordance |
| `yardsPerPx` 像素比例估算距离 | `WatchHoleMapView.swift:93-108` | 不是真实地理距离；Map Detail 应使用反投影/经纬度 |
| 在全洞小图直接拖旗 | `WatchHoleMapView.swift:124-133` | 应迁移到独立 Green View |
| `expectedStrokes = len(steps)` | `decision.py:759-793` | 只是计划步骤数，不是平均完洞杆数 |
| `1.0 + 风险增量` 的启发式 expected strokes | `decision.py:2656-2697` | 未用真实 strokes-to-holeout 校准，不能显示为 `AVG. STROKES` |

## 5. 实施前硬门槛

1. 根页球童层的可见判据写成机器可执行状态，而不是 UI 临时判断。
2. `targetWindow` 明确标为内部瞄准容差，不得冒充历史散布。
3. expected strokes 拆成 `plannedShots`、`strokesEstimateUncalibrated` 与未来的 `avgStrokesCalibrated`。
4. GPS 位移后的重算、TTL、Watch 自灭与滞回进入同一状态机。
5. Big Numbers、Tournament、manual recommendations、关闭、离线无 seed、低置信和陈旧状态均有明确结果。
6. 41/46 mm 原型验证 Driver Arc、AI 线、散布带、chip 和成绩环不会造成不可读或误触。
7. 在以上门槛完成前，C′ 必须退化为方案 B；不允许先用假数据把 UI 画出来。

## 6. 关联文档

- [S70 Virtual Caddie / Driver Arc 专项证据](2026-07-16-s70-virtual-caddie-driver-arc-evidence.md)
- [纯 Fable D02 独立对抗审查](2026-07-16-claude-fable-d02-virtual-caddie-adversarial-review.md)
- [Watch 决策与任务账本](2026-07-15-watch-decision-and-task-tracker.md)
