# Garmin Deep Mining 与三场景地图策略复审

日期：2026-08-10

审查对象：`lean-product-delivery` 快照 `ad149a63fcb8fe523840f53ced978d8ddb4f89bf`

审查方式：Codex 机械取证 + homeserver Claude **Fable** `xhigh` 发散/对抗审查 + Claude **Opus 5** `high` 有界终审；CLI 均未配置 fallback，但不把这一点冒充 Claude Code 内部的“纯模型”保证

性质：设计与证据复审，不是实施 Plan；本轮不修改产品代码

## 一、最终结论

这次复审改变了一个重要判断：Garmin 数据不是“找出最好的一种图，然后三端都用它”，而是四种能力必须分开：

1. `courseData MEDIUM_PLUS` 负责最快到达的球场事实和轻量语义；
2. Garmin 官方 raster 负责精绘视觉，但在完成通用配准前不能负责点击、测距或落点 overlay；
3. `prodgeometry` 负责精确几何、坐标和动态交互，是当前产品 authority；
4. DSKIMG 负责研究中的球会级粗矢量、标签、DEM，以及尚未命名的第二套逐顶点二维数据。

因此产品不应再把“事实可用”“图已经好看”“精确交互已就绪”压成一个下载状态。正确状态是：

```text
factsReady   -> 已可看球洞事实、距离和障碍信息，也允许开始一场
visualReady  -> 已有获准使用的官方精绘图或自有视觉缩略图，但未必可以点图
preciseReady -> 已有 revision-bound topo/projection，可以点选、测距和编辑
```

最重要的产品裁决：

- 备战应逐级增强，不能继续空白等待完整 topo。
- iPhone 和 Watch 实战都不得因为 `preciseReady=false` 阻止开局；数字和轻量语义必须能独立工作。
- Watch 使用专门为腕上可读性渲染的高对比语义图，不能把 1242×1920 官方 raster 直接缩小。
- 复盘落点的持久 authority 是 WGS84 + geometry revision，不是屏幕像素；没有地图时仍应允许列表重排、删除和罚杆编辑。
- DSKIMG 暂不进入产品关键路径，但也不能再写成“已经挖完、只有粗多边形、肯定没有惊喜”。新发现的 auxiliary 二维流可能正是粗糙边界缺少的精度层。
- 不恢复 103 个 checkbox 的通用 Research Lab 大工程；只做至多六个有成功/失败收口条件的实验。

## 二、数据结构与 authority

### 2.1 从 Garmin 原始数据到产品地图

```text
Garmin discovery / release
├─ release identity、build、courseGenVersion、逐洞资产 URL
├─ courseData MEDIUM_PLUS JSON
│  └─ 记分卡、tee、route、障碍 span、果岭轮廓等轻量事实
├─ CourseData protobuf wrapper
│  └─ field 3: DSKIMG
│     └─ IMG container
│        └─ GMP
│           ├─ TRE: subdivision、类型表、主几何 + auxiliary area/line/point offsets
│           ├─ RGN: 主粗矢量 + private auxiliary section
│           ├─ LBL: 球场、九洞组、tee 等文本
│           └─ DEM: 球会级连续高程
├─ 官方 raster JPEG
│  └─ Garmin 已经渲染好的逐洞精绘视觉
└─ prodgeometry ZIP
   ├─ hole.json: RefLat/RefLon、洞级事实与版本
   ├─ *.drc: Fairway/Green/Bunker/Lake/Rough 等表面 mesh
   ├─ foliage.json
   └─ Terrain.webp: 3D 光照用 normal map，不是航拍底图
        │
        └─ 服务端派生
           ├─ topo.png / watch topo
           ├─ holeImageProjection
           ├─ hazard geometry
           └─ AI route / overlay frame
```

这里有两个很容易混淆的 `courseData`：

- `MEDIUM_PLUS JSON` 是很小、很快、直接可用于产品事实卡的 API 结果；
- 历史 corpus 里的 `*_coursedata.pb` 是一个 protobuf wrapper，里面的 field 3 才是 DSKIMG。

两者不能在文档和代码命名中继续混成同一个“course data 包”。

### 2.2 每一层到底负责什么

| 能力 | authority | 不能承担的责任 |
|---|---|---|
| 球场/洞身份、release 与资产版本 | release | 不直接作为几何或像素坐标 |
| 记分卡、route、障碍 span、果岭粗轮廓 | MEDIUM_PLUS courseData | 不冒充精细 hazard/边界 mesh |
| 精确球洞表面、坐标换算、动态 overlay | prodgeometry + revision-bound projection | 不把旧 revision 的像素直接复用到新 revision |
| 已渲染视觉 | 官方 raster | 无配准时不能点击测距、编辑落点或承载距离 overlay |
| 产品高对比地图 | prodgeometry 派生 topo | pixels 只是 view state，不是历史事实 |
| 逐杆/落点编辑 | WGS84 + geometry revision | 不以某张 PNG 的 pixel 坐标作为永久记录 |
| 球会级连续地形 | DSKIMG DEM（实验性） | 不作果岭微等高线；当前 3 个样本仍解码失败 |
| DSKIMG auxiliary 二维流 | 未知 | 在验证前不命名、不进入产品计算 |

### 2.3 最小统一包

三端需要共享同一个逻辑包，但不需要再造通用 CAS/签名/序列化平台。最小结构足够：

```text
HoleMapPackage v1
├─ identity: gid, hole, release/build, assetVersion, geometryRevision, styleVersion
├─ facts: par, tees, route, hazard spans, green outline, F/M/B 与各字段来源
├─ frame: WGS84 anchors, width/height/ppm, projection residual（仅 preciseReady）
├─ assets: topoRef, watchTopoRef, rasterRef?（视觉可选）
└─ state: factsReady, visualReady, preciseReady, failureReason
```

客户端不需要下载原始 prodgeometry 或 DSKIMG。它们应留在服务端的获取/研究/派生层；手机和手表只消费事实、派生图、projection 和版本信息。

## 三、Deep Mining 这次真正发现了什么

### 3.1 当前 parser 的真实能力

第一轮 Fable 报告误读了历史 `research-main/parse_courseview.py`。当前 parser 是：

`tools/courseview/parse_courseview.py`

当前版本已经：

- 遍历完整 FAT，并按 part number 拼接多段 GMP；
- 解析 LBL header/text，并能把对象 label offset 回连到字符串；
- 在 70 个唯一 IMG 上完成 70/70 矢量解析，无 subdivision abort；
- 当前 corpus 没有出现声明集合以外的新 area/line/point 类型。

所以“当前 parser 只读一个 FAT part”和“当前完全没读 LBL”均是已修复的历史问题，不得再列为当前 bug。

但是 70/70 只能证明当前有限 corpus 中的已声明类型稳定，不能证明 Garmin 未来格式永远 closed。

### 3.2 DEM 并未 closed

70 个唯一 IMG 中：

- 67 个完整解码；
- 3 个失败：gid `31687`、`38642`、`39643`；
- 三个失败都落在 `plateau-zero / hybrid predictor` 未覆盖分支。

因此以下旧表述必须撤回：

- “当前 DSKIMG DEM 已 CLOSED”；
- “DEM 可以无条件放进产品关键路径”。

同时保留另一条结论：这个 DEM 是球会级连续地形，可能适合跨洞坡势或背景上下文，但分辨率不足以提供果岭微等高线。

### 3.3 TRE7 后 12 字节不是 padding

70/70 唯一 IMG 的 TRE7 都是：

- `recordSize=24`；
- `magic=0x2007`；
- 当前 parser 只消费前 12 字节的 area/line/point offsets；
- 后 12 字节在 70/70 中都不是全零，也不是随机 padding。

104/104 gid IMG 又呈现同一个更深结构：

1. `RGN base + 0x7d` 开始一个 248-byte private header；
2. 248 字节精确填满到 LBL header 之间的空隙；
3. private header 的 `+2/+6` 是 auxiliary section 的绝对 offset/length；
4. auxiliary section 104/104 都紧跟 extended point section；
5. TRE7 的后三列是指向这套 extension 数据的三个累计边界，并能按 subdivision 切分；第一段已经能与主 area 对象逐项对应。

gid 2625 的例子：

```text
主 geometry 最终长度: area=16738, line=473, point=193
后三列最终 offsets: 11428, 11690, 11717
auxiliary section: offset=20367, length=11717
```

又对 70 个唯一 IMG、973 个 subdivision interval 做了 presence correlation：主 area/line/point 的该段是否非空，与后三列对应段是否非空，在三个类别中均为 **0 mismatch**。line/point 分别有 420/480 个双零区间，判别力较强；area 只有 27 个双零区间，所以它的分区结论还依赖 104/104 的总长度闭合与 44,034 个对象的逐项走查，而不能只靠 presence。综合证据已经证明后三列在 CourseView 中按 area/line/point 对应切分真实 extension 流，不是 padding 或抽象统计。第三方通用 IMG 格式文档只把 TRE7 第四列正式称为 RGN Section 5 offset、第五和第六列仍标未知，所以“官方 section 名称”仍未知；但不能因为名字未知而否认已经证明的三类对应行为。

### 3.4 最大的新发现：它是逐对象、逐顶点的二维数据

进一步机械拆分至少对 auxiliary 的 area 段发现：

- area 数据可以按照主 polygon 对象逐项切开；
- 每项都严格符合 Garmin RGN 风格的 `长度码 + bitstream info + 位流`；
- 用普通二维 delta 规则可以解出 `(x, y)` pair，而不是单个高度 scalar；
- pair 数与主 polygon 坐标数完全相同或少一个的对象共有 31,325/44,034（71.1%）；其余 28.9% 分布在 `-45…-2` 与 `+1/+2`，所以不能把它简化成统一的闭合点规则。

随后对 70 个唯一 IMG 的全部 area 数据做了交叉样本扫描：

- 44,034 个主 polygon 与 44,034 个 auxiliary object record 可以逐项走完；
- 70/70 文件没有 object/group cursor mismatch，也没有解析错误；
- `info` 只出现 `0x00…0x22` 的 9 种组合，每轴 base 均不超过 2；按当前 RGN delta decoder 解出的 x/y component 落在 `[-8, 7]`，0 个超出 signed nibble；
- 这个 4-bit 范围部分由当前位宽解释构造出来，不是 residual 语义的独立证据；真正非平凡的结构证据是全部对象与分组游标都精确消费到段尾。

“逐主 area 对象的二维 bitstream 数据”因此已经是全 corpus 强证据；“主坐标低位 residual/refinement”是当前最值得先证伪的解释，但在 E1 的跨球场 scale/alignment/holdout 实验通过前，语义仍标为 **UNKNOWN**，不能写成 LIKELY 或 PROVEN。曲线控制点或其他二维逐顶点属性仍未完全排除。因为它是二维 pair，“纯高度流”不足以单独解释。

line/point 继续验证给出了清楚的边界：3,091 个主 line 与 3,091 个 auxiliary record 也能逐项走完，0 cursor mismatch，2,716 项 pair 数严格相等；但当前 plain 解码仍有 6 个分量超出 signed nibble，说明 line-specific bit 规则尚差一个小分支。point 段则不能简单解释为“每点一个 packed byte”：2,544 个主 point 对应 3,109 auxiliary bytes，并有 299 个 subdivision count mismatch。也就是说 area 的证据已经很强，line 接近闭合，point 仍明显未知，不能把 area 结论机械外推到三类对象。

仍未闭合的边界包括：line/point auxiliary 的逐对象解码、248-byte private header 除 offset/length 外的其余字段、当前 corpus 未出现的 `shrink != 0` / 其他 DEM encoding，以及未来 CourseGenVersion 的新声明类型。这些是明确命名的格式未知，不等于都有产品价值。

在 residual scale sweep 与 prodgeometry/raster 残差比较完成前，正确标签是：

> **PROVEN structure / UNKNOWN semantics / potentially high product value**

它也解释了为什么“当前 DSKIMG 主多边形显得粗、有毛刺”不能直接推出“原始 IMG 就只有这么粗”。

### 3.5 官方 raster 与 MEDIUM_PLUS 现场样本

官方 raster 的分层抽样：

- 12 座跨地区/版本球场；
- 207 洞，207/207 成功；
- 全部为 1242×1920 JPEG；
- 单洞 88,232–211,614 bytes，平均约 133,772.5 bytes。

这证明该样本里 raster 覆盖很强，也推翻旧文档中的 730×730；它不是 Garmin 全球覆盖证明。

MEDIUM_PLUS courseData 的同组抽样：

- 12/12 成功；
- 整场 15,496–38,214 bytes，平均约 30,450.6 bytes；
- 顺序请求平均约 109.8 ms；
- 必须精确使用 `Accept: application/json`，宽泛 Accept 会返回 protobuf。

109.8 ms 是该现场样本的接口耗时，不是“用户一定在两秒内看到页面”的产品 SLA；完整首屏还包括 discovery、release、缓存、服务端和客户端渲染。

### 3.6 完整 Research Lab 没有实施

`docs/superpowers/plans/2026-07-18-deep-mine-research-lab.md` 的状态是：

- checked: 0；
- unchecked: 103；
- 计划中的 `ai_caddie/research/deep_mine` 模块不存在。

历史 parser、corpus、Draco/prodgeometry、raster、DEM 和多个机械实验都是有效资产；但不能把这些针对性 workstream 描述成“Lossless IR / Unknown Registry 平台已完成”或“所有字节 CLOSED”。

## 四、旧结论的保留、撤回与收窄

| 旧结论 | 本轮裁决 | 新表述 |
|---|---|---|
| 当前 parser 只读一个 FAT part | 撤回 | 历史问题，当前已完整拼接 GMP |
| 当前 parser 没解析 LBL | 撤回 | 历史问题，当前已有 LBL 解码与回连 |
| 当前主矢量 corpus 已稳定 | 有边界保留 | 70/70 完整解析且无新声明类型；不外推未来格式 |
| DSKIMG 只有已见粗多边形，没有其他产品能力 | 撤回 | 主层粗，但 auxiliary 是真实逐顶点二维流，语义待证 |
| DEM 当前分布已 CLOSED | 撤回 | 67/70；3 个 hybrid predictor 分支未闭合 |
| DSKIMG 有果岭微等高线 | 否证 | 当前 DEM 过粗；auxiliary 又是二维 pair，不是已证高度 |
| 官方 raster 是 730×730 | 撤回 | 当前 207 洞样本均为 1242×1920 JPEG |
| 官方 raster 可直接承载动态 overlay | 撤回 | 没有通用逐洞 georeference；单洞控制点结果不可泛化 |
| prodgeometry 是交互 geometry authority | 保留 | 继续作为 topo、projection、测距与编辑基础 |
| Deep Mine 大计划已完成 | 撤回 | 有多个强证据 workstream，但 103 项平台计划未实施 |

## 五、备战、实战、复盘的最终地图策略

### 5.1 入口与球场发现

球场发现与地图安装必须分开，不能为了让搜索结果出现就先下载全场资产：

- **备战**：用户已经知道准备去哪，默认按球场名、城市或关键字查 Garmin catalogue；下面只保留最近选过、正在下载和已下载的条目，不请求 GPS。
- **开始一场**：默认用 GPS 查询附近球场，按真实距离排序；不要先列历史上打过的所有球场。定位失败或用户不在球场时再提供名称搜索。
- catalogue 结果只下载几十 KB 级 metadata/release/courseData；用户明确选中某场后才创建 CourseInstallJob。
- 选中后先解析 venue/loop、真实洞数和 tee authority，再把事实、视觉和精确图分阶段准备；不能猜 9/18 洞或 tee。
- “没下载”不等于“不能搜到”；“精确图没完成”也不等于“不能开始”。

### 5.2 场景矩阵

| 场景 | 默认体验 | 数据/坐标 authority | fallback | 禁止行为 |
|---|---|---|---|---|
| 备战 | facts 卡立即出现；合规开关通过后 raster 提供精绘概览，否则用自有缩略图；topo 到达后开放点选/AI 路线 | 数字先 courseData，精确交互用 prodgeometry | topo → 获准 raster/自有缩略图 → courseData 示意 → 纯事实卡 | 为等完整 topo 显示空白或让页面退出后中断任务 |
| iPhone 实战 | F/M/B、障碍到/过、推荐杆优先；topo 是交互上下文 | GPS + prodgeometry projection | topo → courseData 语义图/数字 | `preciseReady=false` 阻止开局；在未配准 raster 上算距离 |
| Watch 实战 | 腕上高对比 topo/语义图，保留 S70 式数字优先 | 手机下发的 revision-bound 包 + Watch GPS | watch topo → courseData 事实矢量 → 纯数字 | 直接缩小官方 raster；洞中等待网络 |
| 复盘浏览 | 该局 revision 的 topo + shot path | 服务端世界坐标与 revision | topo → courseData 只读帧 → 列表 | 把另一 revision 的 pixels 原样混画 |
| 复盘编辑 | 地图可用时拖动；无图仍能重排/删除/罚杆 | WGS84 + geometry revision | 无图列表编辑 | 把 pixels 永久落库；离开页面静默丢草稿 |

Fable 的地图报告矩阵写成“iPhone 开局前须 preciseReady；否则 courseData 数字模式”，前后存在门槛语义歧义。本次综合审查接受“无精确图时进入数字模式”，但不接受把 `preciseReady` 解释为能否开局的前置条件：精确图决定能不能点地图，不决定能不能打一场。

### 5.3 为什么 Garmin 成品图不能直接替代 topo

官方 raster 和自绘 topo 不是“哪个更好看”的单选题：

| 对比项 | 官方 raster | prodgeometry 自绘 topo |
|---|---|---|
| 视觉 | Garmin 已精绘，层次和纹理更成熟 | 视觉取决于 renderer，可为品牌和平台定制 |
| 坐标 | 当前没有可再生的通用逐洞配准 | 有 revision-bound projection |
| 点击/测距 | 配准前不安全 | 原生支持 |
| 动态路线/落点 | 只能当背景看 | 可以稳定叠加 |
| Watch | 缩小后低对比、细节糊、内存浪费 | 可生成 Watch 专用高对比 profile |
| 下载 | 约 2.4 MB/18 洞的当前均值量级 | 服务端冷生成可能慢，但派生图可缓存 |
| 版本 | 必须和 release/geometry token 绑定 | 已有 geometry revision 机制 |
| 合规 | 缓存/转发边界需单独确认 | 自己派生的产品资产更可控 |

所以：在缓存/转发 Garmin raster 的授权与合规边界明确通过后，备战可以先用 raster 解决“好看和快速浏览”；未通过前，`visualReady` 只能由自有缩略图或 topo 承担。实战和复盘编辑继续用 topo 解决“坐标正确和可交互”。若将来 raster 自动配准实验通过，它才可能升级为可叠加的视觉底图，但配准通过仍不替代合规决策。

### 5.4 下载与存储策略

下载必须属于 app 级持久任务，而不是某个 SwiftUI 页面的一次 `Task`：

```text
用户选中球场
├─ P0 facts: release + courseData，先持久化
├─ P1 visual: 获准 raster 或自有 thumbnail，后台、可续传、按洞落盘
└─ P2 precise: 服务端 prewarm prodgeometry/topo，逐洞完成逐洞可用
```

具体规则：

1. 退回备战首页、重新搜索、切到开始一场，都不取消同一个球场的安装 job。
2. 备战首页保留“最近搜索/正在下载/已下载”条目，并可直接暂停、继续或删除。
3. 优先级是“当前球场当前洞 > 当前球场其他洞 > 其他下载”，不是开局就暂停下载。
4. iOS 文件传输使用 background URLSession/resumeData；服务端预热也必须有持久 job id 和逐洞状态。
5. 失败要有 `failureReason`，不能吞错后显示“已准备”。
6. 不把 Garmin 全库全部下到本地。只持久化已选择、近期或附近球场的轻量 metadata；完整 assets 采用 LRU，进行中的 job 不逐出。
7. release/revision 更新时先下载新版本，验证后原子切换；旧版本在切换前保持可用。
8. 合规开关通过后，`rasterRef` 保存 canonical path + asset version，不把临时 `garmindlm` 签名 URL 写入长期 manifest 或日志；签名过期时由服务端重新取 release。
9. 同一 HoleMapPackage 的 raster、prodgeometry 派生 topo 与 projection 必须绑定同一 release/asset version，禁止半新半旧。

用户刚测试的 build 中“下载几分钟”“退出后重来”，直接原因更接近：备战把精确图设为唯一门槛、详情页曾经拥有普通 `Task`、服务端 prodgeometry/Draco/topo 冷管线串行或并发很低。审查快照 `ad149a6` 已把明确选中的球场变成 app-owned 持久记录，所以单纯退回备战首页理论上已不再取消；但它仍没有 background URLSession/HTTP resume，且部分开局流程还会 pause/requeue worker。这个修复必须在下一版真机验证。继续深挖 IMG 本身不会自动修好产品/调度问题。

### 5.5 当前工程哪些复用，哪些必须改

不是从零重写。当前源码已经有这些正确基础：

- `PrepCourseDownloadRecord`、磁盘持久化、重复选择同一球场时 reattach、逐洞进度和 ready 球场缓存；
- courseData 的轻量 route/事实 fallback；
- prodgeometry revision、topo 文件命名、409 防止错误 revision 混用；
- Watch 的 topo 位图 + courseData 事实矢量双轨；
- 当前 FAT/LBL/主矢量 parser 与大量真实 corpus；
- 服务端已有 topo prewarm 能力，只是 iOS 路径还没有充分利用。

这三笔当前快照中的提交正是用户上轮反馈后的可复用修复，不应被旧审计覆盖：

- `9f55f50`：恢复 prep 下载并保留复盘 shot map；
- `1b20ddd`：加固 prep 下载 task handoff；
- `ad149a6`：未完成的 prep job 不被 recent LRU 丢掉。

其中 `9f55f50` 已针对“GPS 明明存在却显示没有落点”做了关键调整：先选择并保留 source shots，再准备地图；合并的第二个九洞按显示洞 10–18 重映射；精确 geometry 不可用时提供轻量 frame 或明确的 unprojected shot rows。它是正确方向，但还需要用生产聚合和最终 TestFlight build 验证，不能因为代码已合入就说用户现场问题已经消失。

必须在这些基础上改，而不是另起平台：

1. `CourseReviewView.swift` 的卡片固定传入 `requiresPreciseMap: true`，并明确写着“地图完成前不显示简化轮廓”。改为 facts/获准视觉层/topo 逐级增强。
2. 官方 raster 当前只有 acquisition metadata：`rasterAssetPath` 有写入但没有生产消费者，服务端没有 raster 路由，iOS 也没有加载路径；合规通过后仍需补完整通道，不能把设计矩阵误写成现状。
3. `AICaddieApp.swift` 虽然把下载记录持久化，但实际传输仍是普通 Swift `Task`；重启是重新排队，不是真正的 byte-range/background resume。
4. `beginRoundPreparation()` 会调用 `pausePrepCourseDownload()`。应改成提高当前球场/当前洞优先级，而不是取消整个 prep worker。
5. 备战/附近发现目前只取消另一条 best-effort `offlineCourseDownloadTask`，这可以保留“前台意图优先”的目标，但不能误伤同一个 app-owned course install job。
6. `RoundShotMapView.swift` 的地图编辑入口仍绑定 `map.image != nil`，并在 `onDisappear` 直接 `cancelEdit()`；列表编辑和草稿保留需要从地图存在性解耦。
7. shot 保存链已机械确认仍把 `replaceHoleShots` 存成完整 pixel snapshot + `geometryRevision`；服务端只在读取时把 pixels unproject 回 WGS84。它只能算过渡格式：下一版 correction event 应直接持久化 WGS84，pixels 仅在返回当前视图时派生。
8. courseData 请求给正确 `Accept` 的现有实现保留，同时增加 response content-type/JSON shape 断言，避免未来静默收到 protobuf。
9. Ocean/Beach 等海滨 hazard 要进入事实与实战 fallback；不能只处理 Lake/Bunker。

不做的事情同样明确：

- 不把原始 prodgeometry、DSKIMG 或全球 Garmin 地图库整体下载到 iPhone/Watch；
- 不为了这次修复恢复通用 CAS、全套 signed manifest、CanonicalJSON 或 Lossless IR 平台；
- 不等待 E1–E4 全部研究结束才修备战下载和复盘编辑。

## 六、下一步：六个有限实验与执行顺序

每个实验都有失败后的收口，不再发展成无限研究平台。

### E1 — auxiliary residual scale sweep（最高优先级）

- 输入：同时拥有 DSKIMG、同版本 prodgeometry 和 raster 的 5–12 个不同球场/洞。
- 方法：第一轮只使用已闭合 object framing 的 area 段，穷举 pair 对齐、轴向、符号和有限 scale；将其作为主 polygon delta 的 residual 合并，和 prodgeometry 边界、raster edge 做 Hausdorff/Chamfer/edge-overlap 比较。area 成功后才扩展 line；point 暂不纳入。
- 成功：训练样本和 holdout 都出现稳定的同一规则，边界残差显著且一致下降；不能只在一洞肉眼变好。
- 失败收口：否定“坐标 refinement”候选，保留为未知逐顶点属性，不进入 renderer。
- 产品价值：决定 DSKIMG 能否从粗 fallback 升级为轻量精细几何来源。

### E2 — 三个 DEM hybrid predictor 失败样本

- 输入：31687、38642、39643 和当前 67 个成功样本。
- 方法：对照独立 Garmin decoder/格式实现，记录 bit consumption 与 predictor state，补最小分支。
- 成功：70/70 解码且每 tile 精确消费合法 bit/padding，旧 67 样本无回归。
- 失败收口：明确 quarantine 该编码分支，DEM 继续 research-only。
- 产品价值：只影响球会级坡势增强，不阻塞任何场景。

### E3 — 官方 raster 通用自动配准

- 输入：至少 10 座球场、30 个方向/形状不同的洞，同版本 raster + prodgeometry。
- 方法：从 mesh 栅格化材质轮廓，与 raster 分割边缘自动求 affine/projective transform；必须 holdout 验证。
- 成功：跨球场保持稳定，median residual <2 px、P95 <5 px，并能绑定 release/asset version。
- 失败收口：raster 永久限定为非交互视觉卡。
- 产品价值：决定它将来能否用于复盘/实战的漂亮底图。

### E4 — 扩大 raster/courseData 覆盖与版本审计

- 输入：按洲、CourseGenVersion、9/18/27 洞、海滨/山地分层的 100+ 球场。
- 方法：记录 availability、HTTP/content type、尺寸/字节、release token、geometry/raster 版本绑定和延迟；不保存签名 token 到报告。
- 成功：得到可重复的覆盖率和缺失分类，不再以 12 场外推全球。
- 失败收口：缺失类别直接进入 fallback matrix，不继续猜。
- 产品价值：决定缓存容量、预热优先级和陌生新场可靠性。

### E5 — 三态 readiness 的一个真实冷球场切片

- 输入：用户历史中没有的一座 18 洞球场。
- 方法：只实现/模拟最小 `factsReady / visualReady / preciseReady` 状态和持久 job，记录退出、杀 app、重进、开局时每洞状态。
- 成功：事实先显示；页面退出不终止；未有精确图仍能开局；各洞到达后原位增强。
- 失败收口：以 telemetry 定位 acquisition、server cold pipeline 或 client scheduling，不扩大架构。
- 产品价值：直接解决当前备战下载问题。

### E6 — 有触发条件的新抓包

- 输入：只有 E1–E4 证明现有 corpus 缺少关键版本/字段时才请求用户抓包。
- 方法：提前写清所需页面、请求类型、时间窗口和去敏字段；一次只回答一个已命名未知。
- 成功：新增样本能区分两个候选解释或覆盖一个缺失分支。
- 失败收口：标注为 provider-internal unknown，不反复让用户盲抓。
- 产品价值：保证未来新球场获取和格式演进，不占用用户日常时间。

执行顺序不是先把六项全做完再写产品：

```text
现在：E5 三态下载切片 + 修复现有下载/复盘真实问题
并行有限研究：E1 auxiliary residual
随后：E3 raster 配准、E4 覆盖
非阻塞：E2 DEM
仅证据触发：E6 抓包
```

这份复审的核心不是“再深挖一次就能把一种地图用遍三端”，而是把每种 Garmin 数据放回它真正擅长的位置，同时不给未知数据过早下结论。

## 七、终审与证据清单

Opus 5 `high` 终审结论为 **READY**，阻断性问题为“无”。终审 debug 中 19 次模型 dispatch 均为 `claude-opus-5`；它独立重算了报告中的数量、覆盖率和关键源码断言。Fable 的地图策略报告作为发散/对抗输入保留；第一轮 Deep Mining 报告因读取历史 parser 而被明确降级为 superseded input，不作为当前事实 authority。

原始产物保存在 homeserver：

`/home/jason/codex-runs/garmin-deepmine-fable-review-20260810-root/results/`

| 产物 | SHA256 | 用途/状态 |
|---|---|---|
| `map-strategy-fable-review.md` | `12acc9fb7f929acd4023478204a8e56b5a08b667d39e4525ce86a9d8e84cf52e` | Fable 地图与三场景对抗输入 |
| `deepmine-fable-review.md` | `84a611653afd4c6036ed80bfdd1d654219278c423391766522aaa41b863406aa` | 第一轮、误读历史 parser；已 superseded |
| `opus-deepmine-final-audit.md` | `12f755ceb90c10641b6174e5ef1780789407225d08717b378cad71c2f5bfcd22` | Opus 5 有界终审；READY、无阻断项 |
| `current-parser-vector-70-unique-audit.json` | `cc958ba81a5efb867a492806164c65691de46eb515d62f6289b5853a5b1cd7de` | 当前 parser 的 70 唯一 IMG 矢量审计 |
| `current-parser-dem-70-unique-audit.json` | `be32f0cf953d57f7008ff9dd816f28bb5501f5c2a66b63284764feb7197e356c` | DEM 67/70 与三个失败样本 |
| `tre7-extra-columns-70-unique-audit.json` | `a57a8d7af5038939854a192b8a5ec38257d5a1bb71adce16536c0b074f81a857` | TRE7 后三列非 padding |
| `tre7-category-correlation-70-unique.json` | `d7dbd11c05428153b54da50d572edfe88226e370b3d0114dd7e8675c4961181d` | 973 interval 的 area/line/point presence |
| `rgn-aux-area-70-unique-summary.json` | `f98eb4e3b23b888a1508d945a34db066de534ce88662bbac17768da7c32cb2b8` | 44,034 个 area object 的全 corpus 走查 |
| `rgn-aux-line-point-70-unique-summary.json` | `02eef682e9951b2721f4640b02174f7e3013e34564592acff6c9c7c17d9c731b` | line/point 边界与未闭合分支 |
| `raster-12-course-live-audit.json` | `d928fb459d9b0fdbd5c35a136936c972bbd145225add05705254eddeb4fccfd2` | 12 场、207 洞官方 raster 样本 |
| `course-data-12-live-audit.json` | `82121dbb49768c267e95859a581bd7d635e8643d19c2837c9a5f2c9942e91985` | 12 场 MEDIUM_PLUS courseData 样本 |

三个产品提交 `9f55f50`、`1b20ddd`、`ad149a6` 已在本机干净 worktree `lean-product-delivery` 中重新用 Git 核验；远端审查快照缺少 `.git` 不影响这三条本机 provenance 结论。
