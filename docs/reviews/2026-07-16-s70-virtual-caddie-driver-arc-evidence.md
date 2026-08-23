# Approach S70 Virtual Caddie、Driver Arc 与地图标记专项证据

> 日期：2026-07-16 UTC  
> 状态：VERIFIED RESEARCH INPUT，不是设计批准，不授权实现  
> 目的：纠正此前对 S70 Hole View、Virtual Caddie、Driver Distance Arc、layup 点和障碍标记的混淆，为 D02 提供可追溯证据  
> 证据标签：`OFFICIAL` = Garmin 当前手册、产品页或 Support；`CONTINUOUS VIDEO` = 未剪断的实机交互片段；`CROSS-DEVICE OFFICIAL` = Garmin 其它当前设备的官方同类图例；`DERIVED` = 基于多项证据的设计推导；`UNKNOWN` = 公开资料无法证明

## 1. 结论先行

1. S70 的标准 Hole View 不是“纯事实、完全没有球童”。当 Virtual Caddie 可用时，根页会保留 F/M/B、洞图、Driver Distance Arc，并显示轻量推荐杆；Garmin 官方产品图还直接显示当前一杆瞄准线与散布图。
2. 点击根页推荐后，才进入完整 Virtual Caddie：球杆或球杆组合、替代方案、`AVG. STROKES`、当前一杆散布与左右切换。
3. Driver Distance Arc 是用户 Golf Settings 中平均 Driver Distance 的事实标尺，不是 AI 路线，也不是历史散布。
4. S70 根页没有 `you → layup → green` 的确定性整洞两段路线。完整 Virtual Caddie 可以展示当前方案，但不能据此把整洞路线无条件常驻根页。
5. Big Numbers 是独立持久模式；Garmin Support 明确写明 Virtual Caddie 不能与 Big Numbers 或 Tournament Mode 同时使用。
6. `AVG. STROKES` 是采用该推荐时预计完成/得分的平均杆数，不是屏上球杆图标数量；Garmin 没有公开精确公式，不能写成“上果岭杆数 + 固定两推”。
7. 红/白/蓝/黄单点与成对障碍标记是两套对象。跨 Garmin 官方图例中，单点分别代表距旗保留 100/150/200/250 码或米；障碍画面则显示前后沿距离。

## 2. 一手来源

| 来源 | 类型 | 能证明什么 | 不能证明什么 |
|---|---|---|---|
| [S70 Playing Golf](https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-2E8EE4BB-67F6-4B99-9E6C-83CB12DB33C3.html) | OFFICIAL | 默认 Hole View 的 F/M/B、洞图与 `Driver distance from the tee box` | 自动推荐何时刷新、推荐层 TTL |
| [S70 Golf Settings](https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-CBFA7E15-FBF2-4C92-A5A7-C9026972D21B.html) | OFFICIAL | Driver Distance 会“appears as an arc on the map”；Virtual Caddie 支持 automatic 或 manual recommendations | Automatic 的速度、静止时间、位置阈值 |
| [S70 Virtual Caddie](https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-5A77A7DF-49E0-4E35-A23A-2402E7043FA7.html) | OFFICIAL | 推荐球杆或组合、替代选项、平均预计杆数、基于该杆历史的下一杆散布、覆盖果岭时的上果岭概率 | `AVG. STROKES` 精确公式、刷新策略、离线缓存 |
| [S70 产品页官方图](https://res.garmin.com/it-production/image/upload/v1679492352/Product_Images/en/products/010-02746-02/g/57145-3.jpg) | OFFICIAL | 标准 Hole View 上直接显示 `7I`、当前杆瞄准线、落点/散布方框；产品页标题为 `IMPROVED VIRTUAL CADDIE` | 每种状态下是否都显示相同叠层 |
| [Garmin 产品页](https://www.garmin.com/en-US/p/847706/) | OFFICIAL | “shot dispersion chart” 用于快速显示选杆后可能进入的障碍 | 散布框统计分位数与几何算法 |
| [Virtual Caddie on a Garmin Golf Watch](https://support.garmin.com/en-US/?faq=sjA1cXNnKf0nLANJY3T627) | OFFICIAL | Virtual Caddie 不能与 Big Numbers 或 Tournament Mode 同时使用 | S70 的具体动画和消失过渡 |
| [Using Big Numbers Mode](https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-82EAB5FB-1BCD-4D0B-95F0-DE4CC5D7BEE9.html) 与 [Viewing the Map](https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-CE27ADA2-5644-4106-BDF8-04E7D7B8DB5A.html) | OFFICIAL | Big Numbers 通过 Settings 开启，是持久模式；地图另从 View Map 进入 | AOD 中具体保留内容 |
| [S70 Virtual Caddie 实机视频](https://www.youtube.com/watch?v=O7jZz_4Ki70) | CONTINUOUS VIDEO | 根页轻量推荐与完整球童的连续层级、方案切换、实际数字与地图对象 | Garmin 内部算法与不可见输入 |

## 3. 根页与完整 Virtual Caddie 是两层

### 3.1 根页轻量层

连续实机视频约 `2:15–2:23`：

- 标准 Hole View 显示洞号与 Par；
- 左侧显示 F/M/B；
- 右侧显示洞图；
- 地图保留白色 Driver Distance Arc；
- 底部显示 `3W` 推荐入口。

这段能够证明根页不是方案 B 所描述的“永远零球童”。它不能证明 Automatic recommendation 的静止秒数、速度阈值、GPS 位移阈值或 TTL。

Garmin 官方产品图进一步证明，在有有效推荐的 Hole View 上，可以同时存在：

- 推荐杆 `7I`；
- 从球员到当前目标的瞄准/预测线；
- 目标处的历史散布图。

### 3.2 完整球童层

同一连续视频约 `2:25–3:05`：

- 点击根页 `3W` 后进入完整 Virtual Caddie；
- `3W → 8I` 显示 `AVG. STROKES 4.3`；
- Driver → PW 显示 `4.5`；
- 3 Hybrid → 3 Hybrid 显示 `4.3`；
- 4 Hybrid → 3 Hybrid 显示 `4.5`；
- 左右箭头用于切换替代方案；
- 地图显示当前方案的一杆落点/散布与路线信息。

产品层级因此应描述为：

```text
Hole View
├── 永久事实层：洞号/Par、F/M/B、洞图、球员位置、成绩环、Driver Arc（适用时）
└── 条件球童层：当前一杆推荐杆、瞄准线、真实散布（建议有效时）
    └── 点击进入完整 Virtual Caddie：组合、替代方案、AVG. STROKES、详细散布
```

## 4. 地图对象必须分开

| 对象 | S70 语义 | 证据强度 | 本项目禁止的误用 |
|---|---|---|---|
| Driver Distance Arc | 用户设置的平均 Driver Distance 在地图上的弧 | OFFICIAL | 当成 AI 规划线、散布边界或 layup 路线 |
| 推荐杆 chip | 当前推荐杆的轻量入口 | OFFICIAL IMAGE + CONTINUOUS VIDEO | 回退到用户刚选的杆并冒充 AI 推荐 |
| 当前一杆瞄准线 | 从当前球位到预测目标的线 | OFFICIAL IMAGE | 画成确定性球路，或延伸成整洞多杆路线 |
| Shot dispersion | 基于该杆历史的下一杆散布 | OFFICIAL | 用固定像素椭圆或 `targetWindow` 启发式冒充历史散布 |
| Layup 单点 | 距旗保留固定距离的目标点 | S70 VISUAL + CROSS-DEVICE OFFICIAL | 与障碍前/后沿标记混为一谈 |
| Hazard 前后沿 | 同一障碍的 front/back 距离 | OFFICIAL + CONTINUOUS VIDEO | 误读为两个 layup 点 |

### 4.1 Layup 色点语义

S70 当前官方页面和实机画面能确认红/白/蓝/黄单点存在，但没有在 S70 文字页逐色解释。Garmin 当前其它设备的官方手册使用同一约定：

- [Approach J1](https://www8.garmin.com/manuals/webhelp/GUID-A699B5E3-A65C-4F44-B23C-C376C2891F3F/EN-US/GUID-A4263205-E2FE-4EC2-A08C-26A63A59D593.html)
- [Approach G80](https://www8.garmin.com/manuals/webhelp/approachg80/EN-US/GUID-C7C3B92F-7012-4279-82EE-26215CAC2468.html)

官方文字为：red = 100、white = 150、blue = 200、yellow = 250，单位随设备设置为 yards 或 meters。

因此 S70 应标记为：`S70 visual verified + cross-device official semantic / high confidence`，而不是写成 S70 官方文字已逐色证实。

## 5. AVG. STROKES 的正确边界

S70 手册原文：`Displays the average number of strokes expected to score with the club recommendation.`

实机中，两支球杆组合会显示 4.3 或 4.5，而不是 2.0。这能否定以下错误解释：

- 它不是组合中球杆图标的数量；
- 它不是简单的“从当前位置到果岭需要几杆”；
- 它不能被当前仓库的 `len(steps)` 代替。

合理的产品语义是“按该推荐打法完成本洞的预计平均杆数”。但公开资料没有披露：

- 推杆如何建模；
- 罚杆如何进入期望值；
- 短杆、切杆与果岭周边如何建模；
- 是否使用固定两推；
- 散布与障碍概率的精确分布。

因此本项目必须建立并校准自己的 strokes-to-holeout 概率模型；未校准前不得显示 Garmin 式小数 `AVG. STROKES`。

## 6. Big Numbers、Tournament 与模式门控

- Big Numbers 从 `Settings > Big Numbers` 开启，是持久显示模式；地图另从 `View Map` 打开。
- Garmin Support 明确写明 Virtual Caddie `Cannot be used with Big Numbers or Tournament Mode enabled`。
- Golf Settings 明确允许 automatic 或 manual virtual caddie club recommendations。

因此，Apple Watch 方案至少要建模：

- `caddieEnabled`；
- `recommendationMode = automatic | manual`；
- `bigNumbersEnabled`；
- `tournamentMode`；
- `decisionFreshness`；
- `dataSufficiency`。

Big Numbers 不是“尚未进入球童前的状态”，Tournament Mode 也不是只隐藏 PlaysLike；两者都必须让 Virtual Caddie 建议层不可用。

## 7. D02 的证据后果

旧三案中：

- A“根页无条件常驻整洞两段路线”被证据否定；
- B“根页永远零球童”也被官方产品图与连续实拍否定；
- 旧 C“条件显示简化路线”定义不准确，因为根页应显示的是当前一杆建议层，而不是简化后的整洞路线。

应把新选项单独命名为 C′：

> **条件单杆球童层：** 根页永久保留事实层；只有当前一杆建议真实、可信、新鲜且模式允许时，才显示推荐杆、当前一杆瞄准线与真实历史散布。点击推荐杆进入完整 Caddie。任何门槛不满足时，建议层整体消失，根页退化为 B。根页永远不画确定性的 `you → layup → green` 多杆路线。

工程落地仍受数据诚实约束：当前只有纵深 p10/p90，没有横向历史散布；Watch 契约也没有完整传递这些字段。因此 C′ 可以作为产品方向，但在真实数据契约完成前，运行行为必须退化为 B，不能继续画固定装饰椭圆。

## 8. 仍未知

- S70 Automatic recommendation 的静止时间、速度、距离和 GPS 新鲜度阈值。
- S70 建议随球员移动的重算频率、TTL 与滞回规则。
- S70 断网或手机断连后是否缓存推荐，以及缓存多久。
- S70 AOD 中是否保留推荐 chip、瞄准线或散布。
- S70 不同表径下建议层的精确降级。
- S70 shot dispersion 的统计分位数、二维拟合和旋转方式。
- `AVG. STROKES` 与上果岭概率的精确算法。

## 9. 交叉审查

- [纯 Fable D02 独立对抗审查](2026-07-16-claude-fable-d02-virtual-caddie-adversarial-review.md)
- [S70 已核证综合证据包](2026-07-15-s70-verified-evidence-pack.md)
- [Watch 决策与任务账本](2026-07-15-watch-decision-and-task-tracker.md)
