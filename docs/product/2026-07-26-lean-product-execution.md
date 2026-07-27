# AI Caddie 精简产品执行总表

**状态：** 当前唯一执行入口  
**目标：** 在保留用户已确认 UI 和现有代码的前提下，尽快交付可在真实球场完整使用的 Watch/iOS/Web 统一产品。  
**恢复起点：** `feature/lean-product-delivery`，基于 `2a8beb1`。旧 `feature/execute-all-frozen-plans` 仅作历史归档。

## 产品完成标准

玩家能选择真实球场，在 Watch 或 iPhone 开始一局；完成手动记杆、成绩确认、换洞、修改、强杀恢复和离线整轮；随后同步到后端并在 iOS/Web 复盘。地图和球童只展示真实可用的数据。

## 已有能力，优先复用

- 用户已确认的 Watch/iOS/Web 页面和 S70 交互决定。
- `LiveRoundPackage`、真实球场选择、球洞地图和 Watch GPS 距离。
- iOS `OfflineStore`、Watch `WatchRoundStore`、WatchConnectivity 和现有后端 event/replay/ACK API。
- Web 历史、统计、复盘和已有 Garmin 数据连接能力。

这些能力先接通和修复；没有真实阻塞证据时，不重写。

## 当前里程碑

| 顺序 | 可见结果 | 状态 |
|---|---|---|
| 1 | 现有 iOS/Watch 使用一个真实球场完成开局，列出唯一真实阻塞点 | `COMPLETE` |
| 2 | 在现有 UI 中完成已确认的成绩确认与手动记杆流程 | `COMPLETE` |
| 3 | 关键操作后强杀可恢复，重发不丢不重，结果进入现有后端并可复盘 | `COMPLETE` |
| 4 | Watch 可独立搜索、下载、缓存新球场并离线开局 | `COMPLETE` |
| 5 | 已确认的 S70 地图与球童页面接入真实距离、危险区和球杆数据 | `COMPLETE` |
| 6 | 完整手动路径稳定后，再做 AutoShot 和按需 Deep Mine | `CURRENT — 软件路径完成，待真机门` |

任一时刻只推进一个里程碑。里程碑完成后回到本表选择下一项，不沿实现细节继续派生计划树。

## 里程碑 1 结果（2026-07-26）

- 实现 SHA：`f56358da2ae2810517527746e676c644d44b8bf7`。
- Native CI：[run 30190900236](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30190900236) 整体成功：iOS `109/109`、真实 App XCUITest `3/3`、Watch `69/69`。
- Codex 已下载并亲自检查运行态产物。iOS 首页没有 `Unknown course` 或虚假进行中局；历史页显示真实黑骑士数据（155 场、103.8 均杆）；开局页选择北京丽宫、蓝 T、6377 码。
- 北京丽宫第 1 洞真实地图、Par 4 和蓝 T 距离正确加载：前/中/后 `342 / 363 / 379` 码。球童“展开”后 accessibility tree 出现完整方案、护分/标准/进攻和备选打法；方案位于当前截图 viewport 下方，不把截图构图当作产品阻塞。
- Watch seed 与强杀恢复截图均为真实 App，而不是表盘；两个进程 PID 为 `45435 → 45691`，恢复前后都保留北京丽宫、第 1 洞、404 码和同一记分状态。
- 里程碑 1 没有剩余数据或链路阻塞。Watch 小屏标题中的球场名与 Par 会被省略号截断，记入里程碑 2 的交互整理，不为此单独扩张或重跑里程碑 1。

## 里程碑 2 结果（2026-07-26）

- 产品流程 SHA：`daf338fed1f4d676ab4f61594dbd1be230f0d100`；最终 Watch 证据 SHA：`41b22a8ef558be2e76568390df9cb83f3ab4c4c4`。
- 完整 Native CI：[run 30195527919](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30195527919) 整体成功：Domain `47/47`、iOS `111/111`、真实 App XCUITest `3/3`、Watch `82/82`。最终 Watch runtime：[run 30210760850](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30210760850) 成功：Watch `83/83`。
- Watch 已完成推荐成绩一键接受；手动确认按总杆 → 推杆 → Par 4/5 上球道/偏左/偏右 → 罚杆推进，Par 3 跳过球道结果。历史洞可随时修改且不改变当前实战洞。
- “记一杆”先固定腕上 GPS 位置，再选择实际球杆或明确跳过；跳过仍保存位置，推荐杆不会被当成实际杆。已有 Watch/phone adapters 继续产生统一 live-round `location` 事件；已记非推杆数驱动“+2 推”的推荐成绩。
- iPhone 从真实 `coursePrep.map.overlay.route[0]` 与投影 refs 反算各洞 Tee 经纬度并下发 Watch。候选下一洞首杆要求 GPS accuracy ≤ 12 米、距下一 Tee ≤ `35 米 + accuracy`，且有当前 Tee 时下一 Tee 必须更近；“走到下一 Tee”本身不会换洞。
- 上一洞未确认时命中的下一洞首杆只暂存、不写事件。确认上一洞后才切洞，并把暂存杆作为下一洞第一杆；取消则不换洞，把该杆归回上一洞并标为 `recovery`，随后仍可选球杆或跳过球杆。
- Codex 已下载并逐张检查最终 artifact。候选成绩页显示“第 8 洞首杆已暂存”，球杆页显示“第 8 洞 · 第 1 杆已定位”；推荐、Fairway、首页与 seed/restore 页面均无权限弹窗，关键操作在首屏完整可见。seed/restore 是独立真实进程 PID `26131 → 26900`，状态一致；7 次截图启动 PID 均不同。
- 截图曾被 Watch unit-test host 遗留的系统定位页覆盖；最终 workflow 在“测试 → 截图”边界擦除并重启模拟器，截图启动本身也不请求定位。里程碑 2 没有剩余产品或验证阻塞。

## 里程碑 3 结果（2026-07-26）

- 功能最终 SHA：`6077111ab7f438ac843a118eb4774ceee3bce77e`。
- `pendingManualShot` 与成绩确认草稿已随现有 `round.json` 持久化；在成绩确认页或球杆页强杀后，重开回到同一页面，同一杆不丢失也不提前重复入账。[Watch runtime run 30212011485](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30212011485) 成功，Watch `86/86`；Codex 已检查两组独立进程 seed/restore 截图。
- Watch 待发送事件保留到收到精确 ACK；后端继续以 `(playerId, clientId, eventId)` 去重并完成 player-scoped 双登记。完成球局后，现有 iOS/Web 历史复盘均能看到总杆、推杆、Fairway 与真实罚杆；缺少罚杆字段的旧 Garmin 球局继续使用原失误代理，不伪造罚杆。
- [Watch runtime run 30214498129](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30214498129) 成功，包含 Watch 单测、构建和强杀恢复；[CI run 30214932147](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30214932147) 整体成功，包含后端、Web 组件、lint、production build、Docker 与 visual smoke。
- [Native Mobile run 30214932897](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30214932897) 的 iOS app tests、SwiftJCS 边界检查、390×844 设计截图采集与 artifact 上传成功后主动取消了后续无关的重复模拟器任务。Codex 已检查 `round-review.png`：逐洞显示 `罚 1 / 罚 0`，合计显示 `罚 1`，推杆、球道和总杆无截断或布局挤压。

## 里程碑 4 结果（2026-07-26）

- 功能最终 SHA：`a7176860c14cc1aafdd3f7cfd6c6b636bfd2010c`。Watch 使用 iPhone 已下发的后端地址与登录 session，直接读取现有 course options/package/prep 接口；选球场后把真实洞、Par、T 台距离、F/M/B、plays-like、球杆、危险区、地图锚点与渲染图写入现有 Watch course/image store。没有新增 installer、CAS、hash 或地图分发协议。
- 已缓存球场不需要手机、网络或 config 即可生成新的 round identity 并开局；在线更新失败保留缓存列表，prep 没有几何时只保留真实记分数据，不伪造地图。后端 `teeBox = unknown` 时会从真实 tees 中优先选择 Blue/White，不把 `unknown` 发回开局接口。
- 最终 Watch runtime：[run 30216738684](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30216738684) 整体成功：Watch `93/93`、独立 App build、runtime seed/restore 与 artifact 上传全部通过。
- Codex 已下载并亲自检查三张 416×496 真实 App 截图。首次进程 PID `26682` 显示北京丽宫、第 4 洞、P5、567 码和球道图入口；未重装、没有网络 config 且不发网络请求的第二进程 PID `27133` 从 production round/image store 恢复真实 gid31669/h4 地图、3 号木与 F/M/B；第三进程 PID `27478` 从同一 course store 显示完整北京丽宫名称、`18 洞 · Blue` 和已下载标记。诊断中无 crash、fatal、unknown screen 或 restore error。

## 里程碑 5 结果（2026-07-26）

- 功能最终 SHA：`459e7c25784311f3c8de3de783c98dc827b4e95a`。独立 Watch 球局的现有菜单按当前洞真实数据开放“球童建议”和“障碍”两个浅层仪表面；球童页消费真实 F/M/B、腕上 GPS 距离覆盖、高差、推荐杆和已有打法 options，障碍页直接消费真实沙坑/水域区间。
- D02 的根页门控已恢复诚实降级：Watch 契约尚无完整推荐新鲜度、模式门和真实横向散布，因此生产根地图只显示真实底图、球员、旗位、F/M/B、测距与成绩环；原固定 `you → layup → green` 路线、固定 `30×26` 椭圆和无条件推荐 chip 均不再显示。
- `elevationDeltaM` 已在显示边界从米换成码；完整球童 options 不再展示未校准 `expectedStrokes`，也删除了“不给成功率”工程备注。离线预备数据没有目标工作流时不再伪造红色“待选旗位”动作。
- 最终 Watch runtime：[run 30218317794](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30218317794) 整体成功：Watch `99/99`、独立 App build、真实缓存球场 seed/restore、球童页与障碍页运行态截图全部通过。
- Codex 已下载并亲自检查最终 416×496 截图：事实地图显示第 4 洞 P5、实打 `+8` 码和 `256 / 270 / 282` F/M/B；球童页显示 `248 / 262 / 274`、坡度 `+8` 码、`3号木`与离线状态；障碍页显示真实沙坑前沿 `197`、越过 `213` 码。四次独立进程 PID 为 `24183 → 24669 → 25108 → 25210`，诊断中无 crash、fatal、unknown screen 或 restore error。

## 当前工作：AutoShot 与按需 Deep Mine

里程碑 1–5 已建立真实开局、手动记杆、确认换洞、恢复同步、Watch 独立球场缓存和事实地图/球童页面。里程碑 6 从现有 AutoShot 代码与真实击球路径开始，只解决阻塞自动记杆的可复现问题；Deep Mine 只在实际新球场缺失已需要的数据时启动，不建设通用未知格式平台。风、空气密度、假成功率和推杆级等高线继续后置。

### AutoShot Beta 软件结果（2026-07-26）

- 当前实现 SHA：`4ffb14663b0042384c92e38d9cf8acda21e6f345`。AutoShot 默认关闭，只在球局中由玩家显式开启；设备不支持高频批量加速度与 Device Motion 时保持禁用，不提供未经真机验证的 100Hz fallback。
- Watch 通过 HealthKit 高尔夫 workout session 启动 `CMBatchedSensorManager`，原始 Motion 只在内存交给纯检测器，不写 round store、Health workout 或后端。候选只有在玩家确认后才复用现有“球杆可选 → GPS location event”链路；拒绝、未确认和重复检测均不产生正式杆事件。
- 候选、球杆确认和下一 Tee 上一洞成绩确认继续使用现有强杀恢复状态。候选从球洞地图出现时，拒绝或完成球杆确认都会回到球洞地图；菜单中的 AutoShot Beta 状态可见且列表可滚动。
- 最终 Watch runtime [run 30220967536](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30220967536) 完整成功：Watch `111/111`、独立 App build、18 次真实进程启动、真实缓存球场 seed/restore、球童/障碍、AutoShot 候选页和菜单截图全部通过。Codex 已检查最终截图；候选说明无截断，菜单标题和 Beta 开关完整，诊断 artifact 无 crash、fatal、unknown screen、restore error 或 AutoShot provider failure。
- 模拟器不能证明真机传感器授权、后台 workout 抢占、误报/漏报、连续一场续航和热量表现，因此里程碑 6 暂不标 COMPLETE。下一步只做 TestFlight 真机球场验证；Deep Mine 仍没有被真实新球场的数据缺口触发。

### Watch 距上一杆结果（2026-07-27）

- 功能 SHA：`df154f8c90a67230cfe383fc415983427023822a`。独立 Watch 球局直接复用当前洞已持久化的最后一条有效 `location` 事件，以最新腕上 GPS 实时计算走离上一杆位置的距离；不新增字段、协议或第二份位置状态。其他洞和损坏位置值不会覆盖当前洞最后一个有效起点。
- 球洞地图和球童详情使用同一个动态值；腕上 fix 或本地事件缺失时才回退到现有 phone/backend 距离字段。AutoShot 菜单同时移除了容器层多余的第二个 `ScrollView`，保留菜单自身唯一滚动层。
- Watch runtime [run 30235314492](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30235314492) 完整成功：Watch `113/113`、独立 App build 和 20 次真实进程截图全部通过。Codex 已检查地图与球童截图，两处都显示同一真实计算结果 `61 码`；菜单首屏正常，artifact 中没有 App crash、未知测试页面或恢复失败。

## 持续端到端验收基线

以下能力已由里程碑 1–4 建立，后续实现不得回退：

1. iOS 能选择真实球场并创建 `LiveRoundPackage`。
2. Watch 收到或读取同一球场的真实洞、Par、距离和地图数据，而不是 18×Par 4 练习占位。
3. Watch 能进入用户已确认的当前洞页面并在进程重启后恢复这一局。
4. 若链路失败，只记录复现步骤和直接原因；修复最先阻塞用户流程的问题，不提前建设后续平台。

## 防止再次过度设计

- 产品要求用用户行为表达，例如“重启不丢成绩”；哈希、canonical JSON、签名或新数据库都只是候选实现，不自动成为任务。
- 不执行原 Plan 1–4 的线性任务树。它们只作为需求、边界案例和历史研究资料。
- 不创建多级任务编号；不出现 `5B2a-S` 一类递归拆分。
- 一个实现任务必须产生可运行、可观察的产品推进；纯基础设施只能由当前用户流程的真实阻塞触发。
- 不为高尔夫领域不可能输入建立通用协议平台；输入优先采用有范围的领域类型。
- 测试覆盖当前用户路径、数据不丢和已复现 bug。理论协议向量、源码字符串审计、逐行为 RED 证据和逐提交 SHA 不是普通功能验收项。
- 修改后先跑最相关测试；完整 Native/全套回归只在里程碑集成点运行。
- 每个里程碑至多一次独立代码审查。普通小改不派发“实现者 + 规格审查 + 质量审查”三段流水线。
- 用户已经确认的渲染和交互不重新论证；只有真机使用暴露问题时才重开。
- 不等待 agent；没有独立且有价值的并行工作时不创建 agent。

## 明确后置

- 通用 RFC 8785 数字平台、任意 JSON 内容寻址和 storage-v2/v3 迁移平台。
- Course CAS、复杂 rights matrix、构建租约、Ed25519 发布控制、channel/GC 平台。
- 全量未知格式研究框架。Deep Mine 只在实际球场缺失某项数据时按证据启动。
- 风、空气密度、假成功率和推杆级果岭等高线。

后置不等于删除。只有当前产品路径出现可复现问题，或相应里程碑真正开始时，才从历史资料中提取所需部分。

## 工作记录规则

本文件只维护里程碑状态、当前阻塞和下一步。实现细节留在代码、短提交说明和必要的 bug 记录中，不再生成程序级实施巨册。
