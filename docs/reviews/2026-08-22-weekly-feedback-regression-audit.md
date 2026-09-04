# 2026-08-22 过去一周产品反馈综合回归审计

本文件补正 `2026-08-22-prep-feedback-audit.md` 的范围错误。上一份文档只审了备战的六组反馈，没有覆盖用户在同一阶段反复提出的 Apple Watch、iOS 实战、同步、复盘、Garmin/S70 体感和地图问题。本文件以这些反馈为主，重新做一次跨端对账。

## 1. 先看结论

当前不能把产品称为“Watch 已完成”或“已达到 S70 体感”。代码里有很多针对历史问题的修复，但证据层次不一致：有些只有单元测试，有些有模拟器/审批图，有些有真实 Garmin 数据，有些还没有在真实 iPhone + Ultra 链路上验证。

最重要的结论有四个：

1. **Watch 的结束/放弃、离线暂存、事件 ACK、旗位几何和圆角安全区已经有可复用实现。** 用户之前遇到的“只能保存、不能放弃、卡在 Yes”在代码层面有明显修复，但还没有真机复验，因此不能写成用户体验已通过。
2. **Watch 真正独立开局仍未成立。** 已缓存球场可以离线开始，但新球场的附近发现、全量搜索、下载和包升级仍需要 iPhone 下发 `WatchRoundConfig`。`config == nil` 时仍显示“请先在 iPhone 登录并同步一次”。
3. **View Green 的几何正确性已经改善，但“放大后模糊”仍是明确未闭环问题。** 当前实现主要是对已有 bitmap 做变换，没有证据证明它在 Ultra 真机上达到 S70 的清晰度。
4. **生产同步与代码状态存在证据漂移。** Half Moon Bay 的两场历史数据目前已在本地核实完整；但远端 cron/镜像状态和当前工作树不一致，不能仅凭 iOS 的“数据已更新”文案断言未来同步可靠。

## 2. 状态定义和证据纪律

| 标记 | 含义 |
|---|---|
| **已修复** | 代码、针对性测试和可重复的真实数据/端到端证据都支持；不只是存在一个函数。 |
| **部分修复** | 主要路径存在，但仍有明确缺口、旧数据降级、另一端未跟上或用户可见问题未闭环。 |
| **代码支持，未真实验收** | 静态代码和测试支持该行为，但当前没有 Xcode 模拟器截图、真实 iPhone/Watch 链路或真实球场逐洞证据。 |
| **仍未修复** | 代码直接违反已确定的产品约束，或用户反馈的现象仍可由当前实现复现。 |
| **证据冲突/未知** | 不同审计或环境的状态互相矛盾，必须先确认部署/数据来源，不能用乐观假设收口。 |

本轮不把以下内容当成真实验收：

- Swift/Python/TypeScript 单元测试通过；
- ImageRenderer 生成了 PNG；
- 审批 HTML 里看起来正确的 mock；
- 注释写着“对齐 S70”；
- 本地工作树的代码与 TestFlight/生产包默认相同。

本轮只新增本审计文档，没有修改产品代码，也没有声称完成 iOS/Watch 编译或 TestFlight 验收。当前环境没有 Xcode；重型构建和模拟器任务若要执行，必须在 homeserver 运行并单独记录 SHA、设备尺寸和产物。

## 3. 总览矩阵

| 范围 | 当前判断 | 关键未闭环 |
|---|---|---|
| Watch 独立新场/附近球场 | **部分修复** | 新场搜索和 nearby 需要手机配置；Watch 无配置时仍被挡住。 |
| Watch 远离球场开局、999 | **代码支持，未真实验收** | 无 GPS 时可建 provisional round，但 Ultra 真机显示、升级和耗电未测。 |
| Watch → iPhone 开局同步 | **代码支持，未真实验收** | 有 message/userInfo/retry，但没有真实断连、锁屏、重启后的可见性证据。 |
| Watch 结束、保存、稍后同步、放弃 | **代码基本修复，未真实验收** | 需要真机确认按钮布局、离线语义和最终状态不会误报上传成功。 |
| Watch 41/45/49 mm 安全区、字体、按钮 | **部分修复** | 几何测试存在；用户反馈的“字大、挤、不像 S70”仍没有跨尺寸真实截图闭环。 |
| Watch Hole Root / 成绩环 / Tee 标记 | **部分修复** | 环和 Tee 弧线有代码，但整体排版和标记语义未按完整球局重验。 |
| Watch Touch Target | **代码支持，未真实验收** | 数值改为路线投影，但真实球位/旗位仍未核对。 |
| Watch View Green / 旗位 | **部分修复** | 实际边界、旋转、四边距离和传播存在；bitmap 放大模糊仍未解决。 |
| Watch Virtual Caddie | **部分修复** | 已禁止直接 `1W → 1W`，但稳妥优先和期望杆数模型未完整实现。 |
| Watch Hazard | **部分修复** | 新数据有前/后沿；旧缓存仍可能显示“沙坑 1/2”，真实洞截图缺失。 |
| Watch AutoShot/杆提示/补记 | **代码支持，未真实验收** | 检测器和跳过路径存在；用户实际看到的“只有记杆、没有真实动图”尚未证明已改变。 |
| iOS 实战开始/结束/选洞/GPS | **代码支持，未真实验收** | UI 和状态机有入口，缺原生运行证据。 |
| iOS 复盘/落点编辑/统计 | **部分修复** | 缓存和统计路径存在，但闪烁、慢加载、地图缺失和“少列表多 overlay”未验收。 |
| 备战下载与后台 | **部分修复** | 队列可恢复；没有系统级后台 URLSession/BGProcessing，离开页面或被杀后不能保证继续。 |
| 备战球杆距离 | **代码支持，未真实验收** | 分层来源已接入，3W/3H 的生产原值到最终 UI 没有证据表。 |
| 备战策略 | **仍未修复** | 仍不是明确的“稳妥 → 标准 → 进攻”风险排序模型。 |
| 备战地图/障碍/搜索 | **部分修复** | iOS gate 和 nearby/search 有；Web、Watch 和真实冷场速度不统一。 |
| Garmin 同步状态 | **代码支持，未真实验收 / 证据冲突** | 文案去重有 generation/watermark；远端 cron/镜像部署仍需核实。 |
| S70 整体体感 | **仍未通过** | 没有按完整一场球逐状态在 Ultra 和 iPhone 上对照验收。 |

## 4. Watch：过去一周反馈逐项审计

### W01：Watch 不能独立开始，必须手机登录/同步

**用户反馈：** Watch 启动时提示必须在手机登录并同步；不能查看附近陌生球场。用户最终要求：Watch 的 iPhone 应是可选协助，不应是新一场的冷启动前置。

**当前状态：部分修复。**

**代码证据：**

- `mobile/ios/AICaddieWatch/Services/WatchCourseLibrary.swift:51-87`：`refresh(config:)` 没有配置时仍显示“请先在 iPhone 登录并同步一次”。
- `:93-155`：`refreshNearby` 在没有配置时只能从本地附近缓存回退；没有缓存就报同一提示。
- `:157-193`：`searchAllCourses` 没有配置直接失败。
- `:280-328`：`startCourseImmediately` 可以不等 GPS/下载建立 provisional round，这只解决“开始动作不能丢”，没有解决“新场数据来源独立”。
- `mobile/ios/AICaddieWatch/Services/WatchSyncClient.swift:233-243,692-719`：配置由手机通过 application context 下发并保存到 Keychain。

**可以复用：** `WatchCourseStore` 的完整包缓存、`WatchCourseLibrary.startCourseImmediately`、同一 round id 的 upgrade 流程。

**不能宣称已解决的原因：** “缓存球场离线可开始”和“Watch 首次独立发现新球场”是两个产品能力。当前后者仍被 `config` gate 卡住。

**下一步：** 先定义不带手机 bearer 的 Watch discovery/auth 方案（短期可由手机一次性 provisioning，长期需可刷新 member session），再用陌生球场做真实 `nearby → 选择 → 包准备 → 开局` 验收。

### W02：离球场很远时一直搜星，S70 仍可开始并显示 999

**用户反馈：** Watch 选“开始一场”后一直搜星；离球场很远时 S70 可以先开始，距离显示 999；iOS 看不到已开始的球局。

**当前状态：代码支持，未真实验收。**

**代码证据：**

- `mobile/ios/AICaddieWatch/AICaddieWatchApp.swift:195-230`：点击开始立即调用 `startCourseImmediately`、seed round，并调用 `sendRoundStart`，不以 GPS 为门槛。
- `WatchCourseLibrary.swift:275-328`：provisional hole state 的距离为 `nil`，并写入 `geometryCoverage = "pending"`。
- `mobile/ios/AICaddieWatchTests/WatchRoundModelTests.swift:840-856`：无位置时距离文本为 `999 码 · 等待定位`。

**风险：** 没有 production package 时，用户可能看到可记分但没有地图/球童的 provisional 页面；这要在 UI 上明确，而不能让用户以为地图和建议已准备好。

**必须验收：** Ultra 真机在无 GPS、粗糙 GPS、离场 10km 以上三种状态下，开局时间、999 显示、后续 fix 替换、耗电和锁屏恢复。

### W03：Watch 开局后 iOS 看不到球局

**用户反馈：** 手表开始后，iOS 没有“有一场球开始了”的状态。

**当前状态：代码支持，未真实验收。**

**代码证据：**

- `WatchSyncClient.swift:391-439`：round start 通过 `sendMessage`，失败后 `transferUserInfo`，并持久化 pending start。
- `AICaddieApp.swift:2227-2453`：iPhone 有 pending round start、重试和同 round id 去重/关闭逻辑。
- `mobile/ios/AICaddieWatchTests/WatchSyncClientTests.swift` 和 `WatchRoundModelTests.swift` 覆盖延迟 seed、旧 closure、新 round 冲突和 ACK。

**为什么不能写成已解决：** 这些是协议/模型测试，不是 WCSession 真机链路。必须测试手机锁屏、Watch app 被挂起、phoneReachable=false、重复启动、手机先收到后 UI 刷新等情况，并确认 iOS 首页立即显示正在进行的球局。

### W04：结束本场没有放弃，保存并退出又无法完成

**用户反馈：** Ultra 自动装上后只看到积分和“保存并退出”，没有放弃比赛；保存又不能完成，只能点 Yes；体验卡死。

**当前状态：代码基本修复，未真实验收。**

**代码证据：**

- `mobile/ios/AICaddieWatch/Views/WatchFinishRoundView.swift:25-163`：现在有“保存并结束”“编辑成绩”“继续打球”“放弃本场”。
- `:392-490`：放弃有独立二次确认页。
- `mobile/ios/AICaddieWatch/Services/WatchRoundStore.swift:3-7,67-81,180-230`：区分 `finished`、`savedLocally`、`abandoned`，并有 deferred finish/archive。
- `WatchSyncClient.swift:350-379`：结束 closure 和 tombstone 会保留本地关闭事实，避免旧 seed 复活。

**容易误读的地方：** 离线点击“保存并结束”时，代码可以先进入 `savedLocally`，把当前 UI 清掉，等待下次同步；这不是“服务器已上传”。UI 必须明确显示“已保存到本机，待同步”，不能写成“保存成功”。

**必须验收：** 41/45/49mm 上四个动作的可见性、二次确认、离线结束后重启、恢复上传失败、显式放弃后旧 Watch seed 不复活。

### W05：Watch 字体过大、控件太小、不像游戏仪表面

**用户反馈：** 字超边界、布局拥挤；按钮和字体应该更大、更像游戏界面而不是普通应用；同时又要适配 Ultra 的圆角长方形可见区域。

**当前状态：部分修复。**

**代码证据：**

- `mobile/ios/AICaddieWatch/Design/AICaddieDesignTokens.swift:80-138`：有 41/45/49mm 的圆角和 `contentRect` 安全区、控制尺寸和行高。
- `WatchRoundContainerView.swift:32-46,778-822`、`WatchHoleMapView.swift:479-531,1187-1213`：内容和控制点使用安全矩形。
- 多处使用 `minimumScaleFactor`，例如 `WatchRoundContainerView.swift:37,46` 和 `WatchHoleMapView.swift:643,679,698,752`。

**仍然不足：** `contentRect` 是保守矩形内缩，不等价于对真实圆角可见区域逐点裁切；`minimumScaleFactor` 也不证明版式好看。用户指出的 Hole Root 乱、数字过大、按钮语义不清，仍需要真实 41/45/49 截图逐页验收。

**验收门：** 所有重要文本和 marker 在圆角屏幕内；系统右上角时间不遮挡；主球道页只保留一个核心动作层；操作按钮达到 watchOS 触摸目标，但不挤压地图和距离 hero。

### W06：Hole Root、成绩环和 Tee 标记

**用户反馈和已确定约束：**

- 成绩环保留在 Hole Root；只在主要球道图显示，不在其他页面重复。
- 环从右侧 3 点开始，向下、向左、向上，顺时针到 12 点结束，为右上角系统时间留空。
- 白色弧线只在 Tee 台显示；弧线距离可由默认开球距离设定。
- 蓝/红/白点表示明确的 200/150/100 码参考位置，不是“到果岭的三个随意点”。
- `D` 是当前球童建议的第一杆，不应和未知距离或装饰混淆。

**当前状态：部分修复。**

`WatchRoundContainerView` 已保留 `ringPips` 和 Tee/driver 条件，测试也覆盖了 marker/根页可用性；但当前没有一张按真实球洞、真实 Tee 位置和新环方向生成的 41/45/49mm runtime 证据。此前“审批图通过”不能替代这一轮，因为用户后来又指出根页整体太乱。

**下一步：** 用同一真实球洞固定 `tee → fairway → green` 投影，输出环起止角、弧线距离来源、蓝/红/白点距离和 `D` 文案的事实表，再做三尺寸截图。

### W07：Touch Target 的距离不对

**用户反馈：** 先看到 416 和 163 这种不合理码数，后来要求确认点到哪里、球位到旗杆的语义。

**当前状态：代码支持，未真实验收。**

`WatchHoleMapView` 的 `WatchTouchTargetDistanceLayout` 已从屏幕坐标改为路线/图像几何投影；`WatchHoleMapViewportTests.swift` 覆盖连续缩放和可见性。剩余问题是没有用真实球位、真实旗位和真实单位逐洞核对最终显示。必须证明：

- 点一下地图的目标点后显示的是“当前球位到该目标/旗位”的距离；
- 不会把图像像素、球道累计距离和直线距离混为一谈；
- 旗位编辑后 Hole Root 的到旗距离立即更新。

### W08：View Green 两层模式、旋转和旗位距离

**用户反馈：**

- 球道图接近果岭时，应该是带周围球道/沙坑的局部放大；单独点击“查看果岭”才是第二层更大的果岭编辑。
- 不能用黑色背景包住一个孤立椭圆；周围上下文要保留。
- 用户旋转果岭，使其与纸质旗位图方向一致；旋转后仍按屏幕上下左右测量到真实果岭四边。
- 旗位移动后，到新旗位的距离和上下左右四边距离必须同步。
- 用户最后明确指出放大图仍然模糊，且“到果岭边缘”不能误算成到椭圆边缘。

**当前状态：部分修复，清晰度仍未修复。**

**代码证据：**

- `WatchGreenPreviewView.swift:54-181,209-370`：用 `greenOutlinePx` 多边形、旋转中心和真实边界交点计算距离。
- `:481-499,550-650`：有 Digital Crown 旋转/缩放、上下文图、拖旗和距离标注。
- `WatchRoundStore.swift:30-65,94-107`：持久化 normalized flag point 和 rotation degree。
- 真实边界问题的历史复审 SHA `779b31c` 已通过，但那只证明几何/标签逻辑，不证明 bitmap 质量。

**明确未修：** 视图仍依赖 `UIImage`/位图变换；没有高分辨率/矢量边界渲染或超采样证据。用户说“图非常模糊”是当前仍有效的产品问题。

**建议：** 保留当前多边形几何作为事实层，重新设计渲染层：优先矢量化果岭边界和测量线，底图按目标尺寸请求高分辨率并使用高质量插值；对低分辨率资产显示“地图清晰度有限”，不要放大后假装清晰。

### W09：Virtual Caddie 路线和“一号木接一号木”

**用户反馈：** S70 会展示从当前点到果岭的完整路线；此前出现五杆洞/四杆洞“一号木接一号木”；推荐应先稳妥，再激进/保守；Driver 弧线只能从 Tee 台开始。

**当前状态：部分修复。**

- `WatchCaddieOptionsView.swift:225-310` 已有 continuation target，并过滤 Driver 作为 follow-up 的直接 bug。
- `WatchCourseStore.swift` 有 `preparedCaddieOptions` 和多步 plan。
- `WatchRoundContainerView` 只有满足 Tee 条件才画 Driver 弧线。

**仍未达到目标：** Watch offline fallback 仍是启发式；没有把每根杆的稳定性、障碍风险、落点窗口和“期望杆数 + 推杆”作为可解释排序的统一模型。`stock/safe/attack` 不能只是同一最长杆的不同标题。

**验收：** 用 Par 3/4/5 各一个真实洞，记录当前点、候选路线、预计杆数、风险原因和最终显示顺序；先证明“稳妥”，再允许用户展开进攻方案。

### W10：Hazard 只显示两个边界点，不要序号和多余线

**用户反馈：** 障碍应显示到前沿/过后沿两个数，不要画一条线，不要列一堆“沙坑 1、沙坑 2”；没有真实障碍时不应显示空框。

**当前状态：部分修复。**

- `WatchHazardMapView.swift` 使用 front/back boundary，并主要呈现两个点/距离。
- `WatchCourseStore.swift:450-513` 仍保留 `HazardDisplayNaming.legacyLabel`，旧缓存可能重新出现序号命名。
- `WatchHazardMapLayoutTests.swift` 覆盖前后沿距离和无障碍隐藏，但没有真实球洞视觉证据。

**下一步：** 旧缓存迁移时把序号降级为无标签或类型标签；用至少一个有沙坑、一个有水、一个无障碍的真实洞截图验收“前/后、无额外线条、无假障碍”。

### W11：Golf Menu、杆提示和 AutoShot 体感

**用户反馈：** S70 每杆后可以提示使用哪支杆；可以取消，不记录球杆但保留位置；当前体验像“只让我记杆”，没有真实动图；“补记一杆”不应占主菜单。

**当前状态：代码支持，未真实验收。**

- `WatchMenuView.visibleItems` 测试确保第一层不放“本洞击球”“补记一杆”等内部动作。
- `WatchAutoShotDetector.swift` 有 CoreMotion 检测器和 cooldown；`WatchAutoShotCandidateView.swift`、`WatchClubPromptView.swift` 有确认/跳过路径。
- 位置事件和球杆事件在 `WatchSyncClient.swift:134-183` 中分开，允许跳过球杆但保留位置。

**仍需核对：** 当前 TestFlight/生产构建是否真的走新 candidate UI；检测器是工程起点，不是 Garmin 级检测准确率；没有真机运动数据、误报率和“Cancel 后位置仍保留”的用户旅程证据。

### W12：成绩确认、换洞和任意洞修改

**用户反馈：** 走向下一洞/下一洞开球时先确认上一洞；接受默认总成绩后不必逐项确认；取消确认时继续留在上一洞；任何时候可改洞成绩。

**当前状态：部分修复/未真实验收。**

`WatchRoundState`/`WatchRoundModel` 已有 score draft、pending manual shot、putt/penalty/fairway 字段和任意洞状态更新，测试覆盖多种 closure/round state。可是这套复杂的“上一洞确认 + 下一洞第一杆 provisional + Cancel 回上一洞”仍没有一条真实 Watch 交互证据，尤其没有证明：

- 下一洞开球位置先被记录，但未确认前不会错误结束上一洞；
- 接受后同一 GPS 事件只归到下一洞第一杆一次；
- Cancel 后可继续在上一洞记分，不生成重复杆；
- 手动修改历史洞不改变当前 active hole。

这项不能以模型单测替代用户验收，应列为 Watch P0 场上流程。

### W13：杆事实、Mulligan、OB 与“青蛙跳”的区分

**用户反馈和已确定语义：**

- Tee 台连续打多杆只保留最后一杆的 GPS 位置；不要把 Mulligan 当成一个需要用户额外操作的产品概念。
- 离开 Tee 后在很近的位置打多杆，先记录，最后允许修改；不能凭一个过于激进的固定距离自动宣判。
- 隔壁球道、下一个 Tee 或相邻位置都不等于换洞；打偏后仍属于当前洞。
- Fairway 只有“上球道、偏左、偏右”；偏左/偏右表示没有上球道，不是 Fairway 内的中左/中右。
- Landing Surface 记录击球时球所在的 lie；当前模型不应虚构“从水里打出”或“从果岭推杆”这类不存在的杆事实。

**当前状态：部分修复/仍需产品规则。**

`WatchInputEvent` 已有 `fairwayResult`、`lie`、`shotType` 和位置事件字段，说明数据模型可以承载这些语义；但当前没有证据证明生产路径实现了“TEE last-wins”、近距离多杆暂存，以及 OB 罚杆重打和短距离击球的明确区分。更没有一个经 S70 证据或真实球局验证过的距离阈值。

**不能直接自动化的部分：** GPS 只能看到位置和时间，无法可靠判断球是 OB 后按规则重打、厚击后只走了几码，还是在相邻位置练习。v1 应记录事实（位置、时间、当前洞、可选 lie/罚杆），把规则解释和“最后采用哪一杆”交给用户确认；不能用一个隐藏阈值覆盖三种情况。

**验收：** 至少覆盖 Tee 多杆、当前洞隔壁球道、相邻短击、明确罚杆、跨洞 Tee 附近五种轨迹，并检查分数、shot map、FIR 和复盘是否一致。

### W14：Watch 设置入口与主菜单是否重复

**用户反馈：** 右上角设置菜单不好看；主菜单不应塞入“本洞击球”“补记一杆”等低频动作，页面应保持 Garmin/S70 的仪表面优先。

**当前状态：代码支持，未真实验收。**

`WatchMenuView.visibleItems` 已通过测试过滤低频内部动作，`WatchSettingsView` 也有独立入口。但菜单的视觉层级、返回手势、系统时间 clearance 和主球道页之间的重复入口没有真机验证。最终应只保留一个可发现的设置/Action 入口，低频编辑放在二级页面，不要把每个内部状态都变成按钮。

## 5. iOS 实战反馈

### I01：无法结束或放弃本场

**状态：代码支持，未真实验收。**

`CurrentHoleView.swift` 已有“结束本场”入口；`LiveRoundFinishSummaryView.swift` 有保存、继续和 discard confirmation；`LiveRoundScorecardView.swift` 可以从结束摘要回到任意洞。早期审计发现的“结束等于删除”路径已被新的 `LiveRoundFinishSummaryView` 和事件保存逻辑替换，但没有当前 HEAD 的 Xcode UI 证据。必须测试断网结束、保存后重启、显式放弃和待同步事件保留。

### I02：不能选洞、GPS 不能识别当前洞

**状态：代码支持，未真实验收。**

- `LiveRoundScorecardView.swift` 有可选洞和跳转入口。
- `LiveHoleGPSResolver.swift` 有候选洞解析。
- `CurrentHoleView.swift` 的 live map hero 有 GPS 位置、目标、障碍、F/M/B overlay。

需要在两个相邻洞、隔壁球道和离开球场时测试误判；“到达下一个 Tee 不等于换洞”仍是产品规则，不能只依据最近洞中心自动切换。

### I03：球童剩余码数离谱、地图太小、缺图层

**状态：代码支持，未真实验收。**

当前 iOS live map 高度已经扩大，F/M/B 可按 live GPS 重算，目标/球位/障碍 overlay 也有代码。但没有真实生产 course package 的数值逐洞核对；任何出现两万多码的现象，都必须沿着 `course identity → coordinate projection → unit conversion → selected hole` 打印事实链，而不是只调字号。

### I04：手机端像列表，不像 Garmin 地图仪表面

**状态：仍未完全修复。**

用户明确要求几个端都尽量少用列表，在地图上用 overlay 展示；当前 iOS 实战已经朝 live hero 方向调整，但复盘/统计和部分选场仍是 card/grid/list 结构。列表可以用于选洞和历史筛选，但不能成为主体验。需要由同一套地图语义层驱动 iOS、Watch 和 Web，而不是三个端各自绘制一套 label。

## 6. iOS 复盘、历史和统计反馈

### R01：复盘加载慢、闪烁、重复编辑按钮、地图下载后不显示

**状态：部分修复，未真实验收。**

**代码证据：**

- `RoundReviewView.swift:66-93` 有按已打洞预取和 `RoundReviewDiskCache` 读取。
- `RoundShotMapView.swift`/`SyncClient.fetchRoundShotMap` 有按洞拉取和 corrections API。
- `web_v2/src/components/ReviewWorkbench.tsx:96-162` 有 request sequence guard，避免旧洞响应覆盖新洞。

**未闭环：** 缓存存在不等于页面不会闪烁；需要真实模拟器/设备测量首帧、骨架、地图替换、切洞回退、失败重试和编辑按钮是否重复。用户看见“几根线、后台不停闪烁”时，必须把加载状态作为产品状态机验收，而不是只看 API 返回 200。

### R02：每一杆落点数据被提示为缺失

**状态：数据修复候选已存在，展示链未真实验收。**

`RoundShotMapView`、`RoundEditModel`、`SyncClient` 已支持 add/edit/delete/reorder/drag landing；历史审计也确认 stale geometry authority、9+9 remap 和 pin-only refresh 有候选修复。但必须用用户已确认的 Half Moon Bay 两场逐洞检查：scorecard shot refs、globalId/localHole、shot map response、iOS display 是否一致。不能因为 backend 有 shot 文件就让 UI 显示“没有每一个球的落点位置”。

### R03：复盘编辑应点一下记录、拖完可放、可继续加、排序和删除

**状态：代码支持，未真实验收。**

后端 corrections contract 和 iOS/Web 的 shot map editor 已有对应操作；但用户要求的交互顺序是“点一下记录 → 直接拖动 → 放开即保留草稿 → 加下一杆 → 改顺序/删除 → 最后统一保存”，必须在一条真实 UI 流里验证，而不是把长按、拖动和保存分散在不同页面。

### R04：GIR/FIR/趋势数据看不到或不合理

**状态：部分修复。**

`RoundReviewView.swift:227-257` 已优先使用逐洞事实并回退 phase summary；`StatsView.swift` 有 GIR/FIR、季度平均和趋势结构；Web 历史 panel 也显示 scorecard/GIR/shot refs。剩余风险是缺失数据时 UI 仍可能让用户以为是 0，或只显示列表没有地图上下文。必须分别显示“0 次事实”和“未记录”，并用 Half Moon Bay 两场核对分母。

### R05：历史复盘与统计整合、年度/季度/最近 10/20 场

**状态：代码有基础，产品体验未最终验收。**

统计维度已经比早期版本丰富，但首页 IA、历史球局、趋势和地图复盘仍未经过一次完整 Garmin/Golf Live 对照。用户希望历史复盘和数据合在一起，主入口优先看趋势和地图，不要把“历史复盘”作为重复列表。此项不是当前 Watch 开局的阻塞，但属于整体交付前的 UI 回归门。

## 7. 备战、下载、球场发现和策略反馈

这一节保留上一份六项审计的结论，并补上跨端影响。

### P01：下载慢，退出页面后中断，后台不会持续

**状态：部分修复。**

`AICaddieApp.swift` 已有 `PrepCourseDownloadRecord`、持久队列、进度和按洞恢复；但 `beginBackgroundTask`（约 `:3372-3387`）只是短时 grace period，不是 `URLSessionConfiguration.background` 或 `BGProcessingTask`。App 被挂起/杀死后不能保证继续，服务端 course install 仍依赖进程内 worker。

**产品含义：** 当前可说“不会轻易丢下载意图”，不能说“后台会继续下载”或“和 Garmin 一样快”。

### P02：下载时间过长、地图迟迟不出来

**状态：部分修复，性能未达标。**

当前冷路径包含 Garmin release/geometry 解码、逐洞 prep、topo render 和轮询；服务端有 fingerprint cache、single-flight 和有限并发。iOS 备战页对精确地图采用 gate，未 ready 时显示“完整地图准备中，当前不会显示简化轮廓”（`CourseReviewView.swift:374-421`）。这避免了丑陋假地图，却把等待完全暴露给用户。

**更合理的策略：** 选择球场后进入持久下载条目；后台准备期间允许离开；地图页面显示可信的 lightweight CourseView 并明确标注“危险区准备中”，精确 topo 到达后原位替换。若产品决定“不下载完不进入”，则必须在外层提供明确进度、取消、重试和预计阶段，不能只显示一个长时间 spinner。

### P03：3W、3H 等球杆距离明显错误

**状态：代码支持，未真实验收。**

后端 `club_ladder` 当前来源顺序是 `adviceDistance → averageDistance → AutoShot 中位数 → 默认值`，并按真实球包过滤；已有 `test_manual_club_bag.py` 等测试。没有拿用户的生产 Garmin club bag 与 Half Moon Bay 备战响应做“原始值 → 分层选择 → 单位转换 → UI”证据表，因此不能确认用户看到的 3W/3H 已修复。

### P04：四杆/五杆洞出现 1W 接 1W，建议应稳妥优先

**状态：仍未修复。**

`decision.py` 已排除 Driver 作为 follow-up 的直接重复，但 `stock/safe/attack` 仍不等于真正的风险排序；离线 Watch fallback 仍是启发式。要达到用户要求，输出必须包含：候选球杆、预计 carry/散布、危险区代价、剩余码、预计杆数和置信度，并按 `稳妥 → 标准 → 进攻` 排序。不能用“换一个标签”冒充三种策略。

### P05：沙坑/障碍显示成沙坑 1、沙坑 2

**状态：部分修复。**

iOS/Web/Watch 新路径已有真实前沿/后沿和障碍合并；旧缓存仍可能走 legacy 序号标签。必须清除或迁移旧缓存，并用有多个沙坑、有水、无障碍三种洞验证空状态和标签。

### P06：附近球场和搜索交互

**状态：iOS 部分完成，三端未统一。**

- iOS 有附近、半径、城市/关键字字段和下载条目。
- Watch 有 nearby/search UI，但新请求仍依赖 `WatchRoundConfig`。
- Web `PrepPage` 仍主要是单关键字/已有选项，缺少同一附近/城市契约。
- 用户已经明确：“开始一场”默认附近；“备战”默认搜索城市 + 球场关键字；不要把所有历史球场平铺。

### P07：备战不应先显示难看的简化地图

**状态：iOS 已按 gate 收紧，Web 仍未修复。**

iOS `CourseReviewView` 在精确 coverage ready 前不画简化轮廓；但 `web_v2/src/components/PrepPage.tsx` 收到 partial CourseView 后仍可能直接进入 `PrepWorkbench`，并保留 fallback/示意图路径。三端状态机必须统一为 `metadata → preparing → precise ready → offline installed`，不要让“进入页面”“后台安装”“地图可用”混成一个状态。

### P08：地图加载后不能旋转、回洞还要重新加载、没有缓存感

**状态：部分修复。**

Watch View Green 有 Digital Crown 旋转；Phone 普通地图仍主要支持缩放/平移，没有同等旋转交互。iOS 真实 topo 有 revision-keyed cache，Watch 有 `WatchHoleImageStore` 和 decoded `NSCache`，但没有真机切回上一洞的首帧耗时证据。缓存命中、版本失效和下载进度必须在 UI 上可见。

### P09：Topo 轮廓、圆角和 Garmin 渲染图资产

**状态：样本修复存在，数据资产策略仍未最终闭环。**

早期异常洞的尖刺/多边形碎片已经通过 renderer/mask 修复并升了 topo style revision；iOS、Watch、Web 可以复用同一 PNG 和投影。但这只覆盖已抽样的洞，不证明所有 Garmin CourseView/DSKIMG/富图资源都已解析。

DeepMine 的正确边界是：

- 备战可优先使用已经验证 authority、revision 和尺寸的 Garmin 渲染图，减少冷渲染等待；
- 实战必须保留 geometry/障碍/投影作为事实层，渲染图不能替代距离计算；
- 复盘需要同一 geometry authority 和落点坐标，不能拿另一版本的漂亮图覆盖事实；
- 未确认来源、版本、洞号或许可的 DSKIMG 资产不能直接进入生产缓存。

当前仓库有 `courseview_core`、`topo_render`、`WatchHoleImageStore` 和 revision-keyed cache，但没有一份对全部可用 DSKIMG/富图资产的 authority inventory 和真实球场覆盖报告。因此 DeepMine 仍是可并行的资料任务，不应被误写为“地图已经一次性解析到底”。

## 8. Garmin 同步与“正在同步/已更新/拉取失败”

### S01：状态文案重复或竞态

**状态：代码支持，未真实验收。**

`AICaddieApp.swift:750-785,2596-2687` 已加入 `isGarminSyncing`、generation、水印和 `newRoundCount`，理论上只允许一个 owner 更新“Garmin 数据已更新”，并把“暂无新球局”和“拉取失败”分开。Web `SyncStatusPanel.tsx` 也显示本次新增数量。

用户曾看到“还在转圈却显示数据已更新，然后又说拉取失败”，所以必须做真实 UI 时序测试：开始同步 → 延迟 response → 旧 status 到达 → 新 status 到达 → 失败/重试。静态 generation 逻辑不能替代这个验证。

### S02：Half Moon Bay 两场

**状态：已核实的历史数据切片。**

`docs/reviews/2026-08-22-garmin-sync-freshness-vertical-slice.md` 记录：

- `17603881`，Half Moon Bay Ocean，2026-08-14，18 洞 scorecard 与击球完整；
- `17601656`，Half Moon Bay Old，2026-08-13，18 洞 scorecard 与击球完整。

这证明这两场已落盘的事实，不证明所有新球局会自动同步，也不证明 iOS 历史页面一定正确展示。

### S03：生产 cron/镜像证据冲突

最近的远端只读检查发现：`~/aicaddie-sync.sh` 所依赖的 `aicaddie-sync:latest` 镜像在检查时不存在，cron 日志出现 pull denied/exit 125；运行中的 API 仍是较旧 revision。该结果与早期 freshness 文档“cron 成功”的记录冲突。

**当前状态：证据冲突/未知。**

在确认以下三件事前，不应把同步写成已完成：

1. homeserver 当前运行容器、cron 脚本和目标 Git SHA；
2. 手动触发一次 sync 后新 round 是否写入 owner scorecard/shot 文件；
3. `/history/rounds`、round detail、shot map、iOS Results 是否都能看到同一 round。

这不是要求现在清理或重建 homeserver，而是防止把“本地有两场历史数据”误报成“生产同步健康”。

## 9A. 验证环境与 homeserver 反馈的影响

过去一周还出现了磁盘满、后台终端长期运行、旧 worktree/容器占用以及本地与 homeserver 资源混用的问题。这些不是用户界面功能，但会直接影响本审计的可信度。

**当前判断：发布阻塞的运行治理问题。**

- 当前工作树非常脏，包含大量未提交的产品和测试修改；不能用工作树状态冒充一个可发布 SHA。
- homeserver 必须遵守项目 `AGENTS.md` 和 `/home/ubuntu/HOMESERVER.md`：重型测试、构建、浏览器和模拟器只在远端运行；review snapshot、worktree、Docker 和临时日志必须有 owner/expiry/清理记录。
- 磁盘低于容量门槛时不能并发启动新的构建或全量 review；否则“测试失败/下载很慢/机器卡死”可能是资源问题而不是产品问题。
- 本轮没有清理 homeserver、没有杀进程、没有重建容器；后续做真实验证前先记录 `df -h`、运行容器、目标 SHA 和资源清单。

这也解释了为什么本报告把“代码支持”和“真实验收”严格分开：没有固定部署 SHA 和资源快照，任何截图或同步结论都可能来自旧包。

## 10. Garmin/S70 视觉与行为差距：仍需逐状态验收

用户过去几轮已经明确了以下不可静默推翻的约束：

| S70 参考状态 | 当前判断 |
|---|---|
| Hole Root 先显示大字距离/球道图，再按需进入球童 | 有组件，但当前根页信息密度和层级未最终通过。 |
| 站定后显示当前杆建议和到果岭路线 | 有 route/caddie 数据，但策略真实性和视觉层级未完成。 |
| View Green 是周围球道上下文中的果岭放大，而不是孤立黑底图 | 几何上下文代码存在，图片清晰度仍不达标。 |
| Hazard 显示到前沿/越过后沿的两个数字 | 新路径基本符合，旧缓存序号和真实截图需清理。 |
| 开球 Tee 才显示弧线和可设定落点范围 | 有条件判断，未用真实 Tee 逐洞验。 |
| 18 洞成绩环保留且不遮系统时间 | 有 ring pips，但环方向和不同表径未最终验收。 |
| 选择/取消杆提示不阻塞位置事实 | 协议支持，真实 AutoShot UI 未验。 |
| 结束球局有保存、继续、放弃三种清晰动作 | 代码有，真机布局和离线语义未验。 |
| 主球道图优先，列表只作为次级选择 | iOS/复盘/Web 仍有较多列表和卡片，不是完全一致。 |

因此“有几个截图通过”不能推出“Watch 与 S70 一致”。S70 的目标是完整时序和触感：开局、站定、看距离、看障碍、看球童、记杆、确认、换洞、结束、断网恢复。下一次视觉审计必须沿这条时序走，不再只挑 7 张静态图。

## 11. 可以复用什么，哪些不能直接复用

### 可以复用

- WatchConnectivity 的 `sendMessage + transferUserInfo + applicationContext` 多路径，以及事件 ACK/duplicate/rejected 语义。
- `WatchRoundStore` 的 deferred finish、closure、tombstone 和按 round id 恢复。
- `WatchCourseStore`/`OfflineStore` 的 course identity、revision、逐洞 PNG 原子写和完整度判断。
- `WatchGreenPreviewLayout` 的真实多边形边界、四边距离和 normalized flag placement。
- iOS `LiveHoleGPSResolver`、`LiveRoundScorecardView` 和 `LiveRoundFinishSummaryView` 的选洞/结束骨架。
- `RoundShotMap` correction API 的添加、拖动、排序、删除和审计记录。
- 后端 prep fingerprint cache、geometry coverage probe、topo ETag/single-flight。
- 统计层对 GIR/FIR 的“事实优先、缺失不伪造 0”规则。

### 不能直接当成完成品

- 单元测试里的 fake course、sample image 和 mock WCSession。
- ImageRenderer 生成的审批 PNG；它不能证明系统时钟、安全区、字体和真实图片分辨率。
- `beginBackgroundTask`；它不是持续后台下载。
- `startCourseImmediately`；它解决“保留开局动作”，不等于 Watch 可独立发现和安装陌生球场。
- `preparedCaddieOptions` 的离线默认策略；它不是完整的 S70 稳妥排序模型。
- 本地已有 Half Moon Bay 两场；它不能证明 cron、生产容器和未来增量同步正常。

## 12. 修复优先级（回到主线，不重新启动巨型 Plan）

### P0：先让 Watch 场上主流程可信

1. 用真实 Ultra/模拟器三尺寸证据复核 Hole Root、成绩环起止角、Tee 弧线、系统时间、999、F/M/B、障碍和当前杆。
2. 完成上一洞确认/下一洞 provisional 第一杆/Cancel/任意洞修改的一条真实交互测试。
3. 修复 View Green bitmap 模糊；保持真实边界几何不变，替换渲染层。
4. 真实验证 Watch 开局事件在 iOS 立即可见，以及离线结束/放弃不会丢事件或误报上传完成。
5. 把 Watch 无配置时的产品策略定下来：是一次性手机 provisioning，还是 Watch 自己能完成认证/nearby；在决定前不要声称“完全独立”。

### P1：修同步和球场准备的事实链

1. 核对 homeserver cron、镜像、API revision 和当前 checkout；手动跑一条新 round 的端到端同步证据。
2. 为 3W/3H/Driver 生成真实球包距离证据表。
3. 把备战下载状态拆成 metadata、geometry、topo、offline installed 四个可见阶段；保存任务并在前后台恢复。
4. 统一 iOS/Watch/Web 的 nearby/search 契约；开始一场看附近，备战看城市 + 球场关键字，不平铺历史列表。
5. 改策略排序为可解释的稳妥优先，禁止重复 Driver 路线。

### P2：完成复盘和统计体验

1. 用 Half Moon Bay 两场逐洞核对 shot refs、落点、地图 authority、GIR/FIR 分母和 corrections。
2. 修复复盘首帧/切洞缓存/地图替换/编辑按钮闪烁；再做模拟器截图。
3. 将地图 overlay 作为主复盘视图，列表和 scorecard 作为导航，不让列表取代地图。
4. 把年度、季度、最近 10/20 场、球场/球洞/球杆趋势整合到同一个历史数据入口。

### P3：发布门

只有下面四项同时满足，才重新生成 TestFlight：

- Watch 41/45/49mm 真实截图和完整一场交互通过；
- iOS 实战、复盘和备战的真实端到端路径通过；
- 同步 round 在 Garmin → backend → iOS/Watch/Web 的事实链一致；
- 用户看到批准图、目标 S70 证据和当前 runtime 并明确批准。

## 13. 本轮审计边界和后续证据格式

本文件没有运行 Xcode、iOS/Watch 模拟器或 TestFlight，也没有更改 homeserver。下一轮每个问题都应附以下最小证据，不再只报“测试通过”：

| 证据字段 | 要求 |
|---|---|
| 产品状态 | 入口、前置状态、用户动作、预期结果、实际结果。 |
| 数据事实 | course/globalId、hole、tee、geometry revision、round id、单位。 |
| 设备 | iPhone 型号/iOS、Watch 表径/watchOS、是否锁屏/断网。 |
| 代码 | 文件和符号/行号。 |
| 测试 | 测试名称、运行环境、通过数量。 |
| 截图 | 原始 runtime 截图，不是只看 HTML mock；与批准图同尺寸并排。 |
| 未验证项 | 明确写“没有测”，不能用推断填空。 |

## 14. 最终判断

这次遗漏不是因为 Watch 没有实现，而是因为上一份审计把“最近用户反馈”错误切成了一个备战子集，且把工程支持误当成产品验收。现在的真实位置是：

> **核心数据和状态机有大量可复用基础；Watch 的生命周期和同步代码已经比早期版本可靠；但 Watch 首次独立发现、View Green 清晰度、完整 S70 时序、真实跨设备同步和三端地图体验仍未达到发布门。**

因此本轮不应直接上传新的 TestFlight，也不应重新启动几万行旧 Plan。应按 P0 → P1 → P2 的小批量顺序收口，每一批都用真实设备/真实球场证据关闭，而不是继续扩展计划文本。
