# Approach S70 成绩环证据更正

> Status: VERIFIED CORRECTION  
> Date: 2026-07-15  
> Scope: S70 打球界面的逐洞成绩环  
> Supersedes: 所有声称“S70 没有 18 洞边缘成绩环”的本仓库结论

## 1. 更正结论

此前结论“S70 没有沿边缘显示 18 洞成绩的环”是错误的。

正确事实是：

- S70 的实体表圈刻有 1–18 洞指示；
- 打球并记分时，屏幕会在对应洞号旁显示彩色短弧；
- 每段颜色表示该洞相对 Par 的成绩；
- 因此它是“物理洞号刻度 + 屏幕动态成绩色段”的混合成绩环；
- Apple Watch 没有这种实体表圈，所以本项目用屏内 18 段环进行平台翻译，方向上确实来自 Garmin，而非凭空自创。

## 2. Garmin 官方文字与图片证据

### 2.1 Owner's Manual：Score History

Garmin 官方英文手册原文：

> While playing a round, your watch displays a color next to each of the hole indicators along the bezel to indicate your score on that hole.

来源：

- [Garmin S70 Owner's Manual — Score History](https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-D5D74362-3004-4930-BC95-24CFF5988B98.html)
- [Garmin 官方带标注图片](https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/Shared/GUID-CEEEEA02-C713-40F8-BC5F-6BC55A8077C0-high.jpg)
- [Garmin 中文官方手册](https://www8.garmin.com/manuals-apac/webhelp/approachs70/ZH-CN/GUID-557982D6-3E5A-4D5D-B12A-C82ADBC83742-5968.html)
- [Garmin 日文官方手册](https://www8.garmin.com/manuals-apac/webhelp/approachs70/JA-JP/GUID-645A5714-C13D-46CC-9DDF-BFFF698AA852-4779.html)

日文页明确使用“ベゼルに刻印されたホールインジケーター”，即洞号指示刻在实体表圈上。

当前英文手册页同时标明 42 mm `010-02746-00` 与 47 mm `010-02746-02`，版本为 v5、发布日期为 2026-04；因此这不是把其它型号手册误套到 S70。

### 2.2 官方颜色表

| 颜色 | 相对 Par |
|---|---|
| 紫色 | +5 或更差 |
| 粉色 | +4 |
| 红色 | +3 |
| 橙色 | +2 |
| 黄色 | +1 |
| 绿色 | Par |
| 浅蓝色 | -1 |
| 深蓝色 | -2 或更好 |

这与本项目现有 ScoreChip / `scoreColor(toPar:)` 的基本方向高度一致；具体色值和色盲冗余仍是本产品自己的实现问题。

### 2.3 Garmin 官方产品图库

- [Approach S70 官方产品页](https://www.garmin.com/en-US/p/847706)
- [官方 47 mm 主产品图](https://res.garmin.com/en/products/010-02746-02/g/cf-xl.jpg)：第 15 洞画面可见 1–14 洞成绩色段、第 15 洞白色当前洞轮廓和 16–18 洞空白状态。
- [官方 42 mm 主产品图](https://res.garmin.com/en/products/010-02746-00/v/cf-xl.jpg)：同一套逐洞成绩环，排除“只在 47 mm 上存在”的误判。
- [官方 #8 洞画面](https://res.garmin.com/it-production/image/upload/v1679492352/Product_Images/en/products/010-02746-02/g/57145-2.jpg)：洞号 1–7 旁已有不同颜色的成绩段，当前为第 8 洞。
- [官方 #15 洞画面](https://res.garmin.com/it-production/image/upload/v1679492352/Product_Images/en/products/010-02746-02/g/57145-3.jpg)：洞号 1–14 旁已有成绩段，当前为第 15 洞。
- [官方 Wind 画面](https://res.garmin.com/en/products/010-02746-02/g/pd-05-lg.jpg)：Wind 仪表面仍可见已完成洞的成绩段。
- [官方 42 mm 画面](https://res.garmin.com/en/products/010-02746-00/v/pd-05-lg.jpg)：小表径同样存在这套表圈成绩历史。

官方图片和手册共同排除了以下误判：

- 不是普通表盘装饰环；
- 不是地图缩放轨；
- 不是第三方 App；
- 不是只显示当前洞的一枚小图标；
- 不是 S62 或其它 Garmin 型号被错认成 S70。

## 3. 独立实拍与视频交叉证据

### 3.1 Plugged In Golf 球场实拍

- [评测页面](https://pluggedingolf.com/garmin-approach-s70-golf-smartwatch-review/)
- [第 11 洞基础距离画面](https://pluggedingolf.com/wp-content/uploads/2023/06/Garmin-Approach-S70-Golf-Smartwatch-1560.jpg)
- [第 11 洞 PlaysLike 画面](https://pluggedingolf.com/wp-content/uploads/2023/06/Garmin-Approach-S70-Golf-Smartwatch-1562.jpg)

两张真机照片都清楚显示已完成洞的逐洞彩色弧。

### 3.2 PlayBetter 球场实拍

- [评测页面](https://www.playbetter.com/blogs/golf-gps-rangefinders/garmin-approach-s70-review)
- [基础 Yardage 画面](https://cdn.shopify.com/s/files/1/0245/2363/6832/files/S70-yardage_480x480.jpg)
- [Strokes 输入画面](https://cdn.shopify.com/s/files/1/0245/2363/6832/files/S70-strokes-hole_480x480.jpg)

真机表圈上的 1–18 洞刻度和屏幕内侧成绩色段均可辨认。

### 3.3 多个独立视频封面

- [Garmin Approach S70: The Complete Guide](https://www.youtube.com/watch?v=DqQMLMCX-OA)
- [Garmin Approach S70 Review](https://www.youtube.com/watch?v=DEcG0dakEz0)
- [S70 On Course Review](https://www.youtube.com/watch?v=_2SX7Zxada0)
- [S70 Virtual Caddie](https://www.youtube.com/watch?v=O7jZz_4Ki70)

这些来源不是证明颜色语义的主要依据，但可以证明该视觉在真实产品展示中稳定存在。

### 3.4 连续操作视频与其它实拍页面

- [The Golf Shop Online — S70 On Course Review](https://www.youtube.com/watch?v=_2SX7Zxada0&t=364s)：`6:04` 输入 Strokes，`6:12–6:16` 回到 Hole View 后外圈仍在；`0:50–1:15` 地图缩放过程中也可见。连续画面排除了把不同页面、不同机器或营销合成图拼在一起的误判。
- [TechRadar S70 评测](https://www.techradar.com/health-fitness/garmin-s70-approach-review-the-best-gets-better)：第 1 洞画面只有当前洞状态，第 9 洞画面在 1–8 洞位置出现多色弧、10–18 仍为空，清楚展示成绩段随已完成洞逐步填入。
- [Breaking Eighty S70 评测](https://breakingeighty.com/garmin-approach-s70-review)：标准 Hole View 实拍可见红、黄、绿等逐洞色段。
- [National Club Golfer S70 实拍](https://www.nationalclubgolfer.com/wp-content/uploads/2024/09/garmin-approach-s70-gps-golf-watch-screen-2.jpg)：表圈可直接辨认 `S70`，真实腕上画面仍显示同一结构。

## 4. 已确认的显示语义

| 观察 | 结论 | 证据级别 |
|---|---|---|
| 1–18 数字在普通表盘和非高尔夫页面也存在 | 洞号刻度属于实体表圈 | `OFFICIAL + MULTI-SOURCE` |
| 第 8 洞画面只在此前洞位出现颜色 | 色段随已完成洞逐步形成 | `OFFICIAL` |
| 第 15 洞画面已覆盖此前大部分洞位 | 这是整轮逐洞历史，不是当前洞装饰 | `OFFICIAL` |
| 手册给出颜色到相对 Par 的完整表 | 色段编码逐洞成绩 | `OFFICIAL` |
| 基础距离、PlaysLike、Wind 画面都可看到 | 它属于当前洞相关的高层球局视觉 | `OFFICIAL + MULTI-SOURCE` |
| 当前洞附近有白色/空心指示，未来洞无成绩颜色 | 当前洞与已完成洞使用不同视觉语义 | `OFFICIAL IMAGE` |
| 连续视频中输入成绩后返回 Hole View，成绩环仍存在 | 不是静态营销图偶然叠加 | `INDEPENDENT CONTINUOUS VIDEO` |
| 官方 Big Numbers 画面没有 1–18 洞环 | 纯大字距离面是已确认的隐藏例外 | `OFFICIAL` |

## 5. 仍然未知，不能继续猜

- Touch Target 的各个细分状态是否始终保留，还是会在拖动/选点时短暂隐藏；
- AOD、PinPointer 的精确保留/隐藏行为；
- 未开启记分、不同 scoring method、9 洞轮次和 shotgun 起洞时的精确排列；
- 固件版本是否改变线宽、当前洞指示或隐藏规则。

已经可以从官方或连续视频确认：标准 Hole View 保留；地图缩放与若干 Green View 实拍仍保留；Big Numbers 的纯大字距离页隐藏。剩余问题应通过 S70 真机视频逐项验证，不能再从单张营销图外推。

## 6. 错误根因

1. 过度依赖手册“第 1 洞、尚无已完成成绩”的主屏示意图；该场景本来就不会出现历史色段。
2. 阅读了 Keeping Score，却漏读其子页 Score History；子页恰好包含直接答案和颜色表。
3. 旧研究以文字抓取为主，没有把 Garmin 产品图库和球场实拍逐张纳入证据矩阵。
4. 后续 Round 1/2 和联合重审继承了这一错误前提，形成多文档一致但事实错误的假共识。
5. 多模型对抗审查主要审逻辑一致性，没有回到一手图片重新验证基础事实。

## 7. 对产品判断的修正

此前“为了更接近 S70，应把成绩环移出 Hole Root”的建议失去事实基础。

当前正确默认是：

- 保留成绩环；
- 将其视为 S70 核心整轮上下文的 Apple Watch 平台翻译；
- 已完成洞按相对 Par 着色；
- 当前洞与未来洞必须有不同状态；
- 完整 Scorecard 仍是独立仪表面，但不能以此为理由从根页删除环；
- 只有真机布局证明它妨碍 F/M/B 首读时，才讨论在地图缩放或交互态条件隐藏。

这也意味着现有源码注释“score indicator lives on the hole-info view”的方向基本正确；需要复核的是几何、洞号表达、未打洞状态、色值和隐藏时机，不是功能是否存在。

### 7.1 当前实现的准确复用与缺口

已经做对、可以修改复用：

- `WatchRoundContainerView.swift` 已明确保留成绩环，并使用每洞真实 `score - par` 生成 `ringPips`；
- `WatchHoleMapView.swift` 已把当前洞与已完成洞分开绘制；
- 环只在外层 Hole Map 绘制、进入 `fullMap` 隐藏，这个产品方向合理，但隐藏时机仍需 S70 真机逐面验证；
- 计分卡和其它成绩面已经共享 `scoreColor(toPar:)` 的色彩入口。

仍需修改，不能冒充已经还原：

- `AICaddieDesignTokens.scoreColor(toPar:)` 目前只区分 `≤-2 / -1 / Par / +1 / ≥+2` 五档；S70 官方是八档，缺少 `+2 橙 / +3 红 / +4 粉 / ≥+5 紫` 的独立表达；
- 当前未打洞会绘制半透明白段，而 S70 官方图中未来洞没有成绩色段；需确认 Apple Watch 上是保持空白还是用极弱刻度补偿没有实体洞号圈的问题；
- S70 的 1–18 数字来自实体表圈，本项目没有实体刻度；是否绘制完整洞号、只绘制短段，或只标 1/9/18，需要小表径原型，不能声称像素级复制；
- 9 洞、shotgun 起洞和环组合的排列尚未定义；
- 当前矩形环只覆盖部分圆角矩形周长，这是平台翻译选择，不是 Garmin 原样行为。

本轮只更正文档和决策依据，不修改产品代码。

## 8. 受影响文档

必须显式更正：

- `2026-07-14-claude-fable-s70-experience-research.md`；
- `2026-07-15-s70-verified-evidence-pack.md`；
- `2026-07-15-claude-fable-s70-design-synthesis-round1.md`；
- `2026-07-15-claude-fable-s70-design-synthesis-round2.md`；
- `2026-07-15-codex-fable-watch-full-experience-reassessment.md`；
- `2026-07-15-claude-fable-watch-full-experience-final-adversarial-review.md`；
- `2026-07-15-watch-decision-and-task-tracker.md`。

旧错误应保留在变更记录中，不能无痕覆盖。
