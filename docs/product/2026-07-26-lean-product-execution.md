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
| 4 | Watch 可独立搜索、下载、缓存新球场并离线开局 | `COMPLETE — 软件链 + Simulator 真实数据证据` |
| 5 | 已确认的 S70 地图与球童页面接入真实距离、危险区和球杆数据 | `COMPLETE` |
| 6 | 完整手动路径稳定后，再做 AutoShot 和按需 Deep Mine | `SOFTWARE COMPLETE — 待真机门` |

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

### Watch 真实洞组 / Tee 开局补齐（2026-07-27）

- 功能 SHA：`573c8bdc5e1c3faad76a3eca06fb86ad81cff13c`。点击已知真实球场后不再按历史默认 Tee 直接开局，而是进入腕上设置页：9 洞环可明确选择只打 9 洞或同场任意 9+9 组合，并明确选择真实 Tee；选择值直接复用现有 package 的 `tee_box/back_global_id`，不新增后端协议。
- 离线缓存按实际前九、后九和 Tee 匹配；不匹配时明确要求联网更新，不会拿另一个 Tee/洞组的缓存冒充。未获批准的默认 `18×Par 4「仅记分」`入口已从生产开局页移除。
- Watch runtime [run 30250667576](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30250667576) 完整成功：Watch `118/118`、独立 App build 和 24 次真实进程启动全部通过。首次成功构建的截图复核还抓到设置页插值被显示为字面量，最终 SHA 修正后复跑；Codex 已检查球场页无“仅记分”，设置页正确显示 `A · Blue T · 9 洞` 与 `只打 A · 9 洞`，诊断中无 crash、未知测试页面或恢复失败。
- 原里程碑 4 的“独立搜索新球场”完成表述过宽：当前搜索框只过滤 `/mobile/courses/options` 返回的历史/已知球场，并未接入仓库已经存在的 `/api/v2/courses/search` 全库入口。因此“已知真实球场 → 洞组/Tee → 下载 → 离线开局”已完成；任意未打过新球场的远端发现仍是里程碑 4 当前唯一软件缺口。

### Watch 全库新球场发现补齐（2026-07-27）

- 功能最终 SHA：`fe89aec6c6eb910b6eae2feb7b0928ff122e3ce3`。腕上输入名称后必须明确点击“搜索全部球场”，不会因输入文字自动联网；结果显示 Garmin 名称、城市、省份和真实洞数，同场 9 洞结果继续进入既有 9+9 设置页。
- 选择全库结果后读取现有 `/api/v2/courses/{globalId}/tees?ensure_release=true`，设置页立即显示真实 Tee；已有 geometry 时同时显示总码数，首次球场则暂不伪造码数。随后仍走同一 package → prep → image/course store → 离线开局链。只有点击准备并开始、首次下载几何时才传 `ensure_geometry=true`，没有新增 installer、地图协议或第二套缓存。package 只返回 `Course {globalId}` 时保留玩家实际选择的球场名。
- Garmin 搜索记录允许 `holes=null`；Watch 现在保留该结果但显示“洞数未知”并禁止开局，不再让一条不完整记录导致整批搜索解码失败。后端会把远端搜索失败同样降成空结果，因此空结果文案明确要求检查名称或稍后重试，不武断声称球场不存在。Tee 获取失败时也禁用开局，不会拿猜测的 Blue T 继续。
- 运行态复核同时发现并修复两个可见问题：9+9 候选不再出现同一洞组的 `A + A`；远端 wire key `blue` 仍原样发回后端，但摘要统一显示为 `Blue T`。最终 Watch runtime [run 30255505429](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30255505429) 完整成功：Watch `119/119`、独立 App build、26 次真实进程启动和 26 张 416×496 截图全部通过。Codex 已检查全库结果页显示 `Mission Hills · A/B` 与 `深圳 · 广东 · 9 洞`，远端设置页显示 `A · Blue T · 9 洞` 和 `蓝 T · 3210 码`；26 个 launch PID 均不同，诊断中无 crash、unknown screen 或恢复失败。
- 这证明 Watch 软件链和契约边界已经接通，不证明 Garmin 对任意未来球场都有完整 package/prep/地图数据。下一个门是拿一个账号历史中从未出现的真实球场完成“搜索 → Tee → 下载 → 断网重开”；只有该证据暴露具体缺项时才启动 Deep Mine。

## 里程碑 5 结果（2026-07-26）

- 功能最终 SHA：`459e7c25784311f3c8de3de783c98dc827b4e95a`。独立 Watch 球局的现有菜单按当前洞真实数据开放“球童建议”和“障碍”两个浅层仪表面；球童页消费真实 F/M/B、腕上 GPS 距离覆盖、高差、推荐杆和已有打法 options，障碍数据包含水域进/出距离与沙坑沿路线点/横向距离。
- D02 的根页门控已恢复诚实降级：Watch 契约尚无完整推荐新鲜度、模式门和真实横向散布，因此生产根地图只显示真实底图、球员、旗位、F/M/B、测距与成绩环；原固定 `you → layup → green` 路线、固定 `30×26` 椭圆和无条件推荐 chip 均不再显示。
- `elevationDeltaM` 已在显示边界从米换成码；完整球童 options 不再展示未校准 `expectedStrokes`，也删除了“不给成功率”工程备注。离线预备数据没有目标工作流时不再伪造红色“待选旗位”动作。
- 最终 Watch runtime：[run 30218317794](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30218317794) 整体成功：Watch `99/99`、独立 App build、真实缓存球场 seed/restore、球童页与障碍页运行态截图全部通过。
- Codex 已下载并亲自检查当时的 416×496 截图：事实地图显示第 4 洞 P5、实打 `+8` 码和 `256 / 270 / 282` F/M/B；球童页显示 `248 / 262 / 274`、坡度 `+8` 码、`3号木`与离线状态。当时障碍页把沙坑 `[alongRoute, side]` 误报为“前沿 `197` / 越过 `213`”，后续 UI-03 实战审计已取消这项错误证据。四次独立进程 PID 为 `24183 → 24669 → 25108 → 25210`，诊断中无 crash、fatal、unknown screen 或 restore error。

### 新球场 Tee / geometry 索引修正（2026-07-27，进行中）

- Garmin CourseView release 的 MEN Tee `name + index` 现在是 Tee 选择的权威；geometry 的 `sets` 按 release 的真实 index 匹配，不再把 `set 1/2/3/4/5` 固定解释成黑/蓝/白/金/红。这样 Pebble Beach（Blue=1、Gold=2、White=3、Green=4、Red=5）和北京丽宫（Gold=1、Blue=2、White=3、Red=4）都不会错配。
- `GET /api/v2/courses/{globalId}/tees?ensure_release=true` 只获取并缓存真实 CourseView release 的 Tee 名称/index，快速返回；普通 `/tees` 保持只读、不触发下载。iOS 与 Watch 的 Tee 请求都显式使用该参数。点击准备并开始后，现有 package 请求才传 `ensure_geometry=true`；首次 package/prep 下载允许最长 900 秒，几何未完成前码数保持 `null`，不伪造。
- geometry 缺失时继续返回真实 Tee 名称和 `yards: null`，不猜距离；没有 release 的旧缓存继续走 canonical fallback。
- 本切片的本机 Python focused gate 已通过；GitHub Native CI 的 iOS/Watch 单测与 Watch runtime 在父提交 `5a74480` 已通过，后端 cache 修复在 `50e4c26` 另行验证。

### 未打过球场的真实下载门（2026-07-27）

- homeserver 真实验证使用 Garmin `globalId=3881`（Cypress Point Club，搜索结果 18 洞）。冷 release 请求 `ensure_release=true` 用时 `0.219504s`，只返回 Championship/Middle/Forward 三个真实 Tee，geometry 仍为 `0/18 missing`，没有隐藏下载。
- 现有 production package 请求 `ensure_geometry=true` 用时 `241.795319s`，返回 `2,011,453` bytes、18 个洞且 `geometryCoverage=ready` 的 18/18；请求没有超过新的 900 秒客户端预算。下载后重新读取 Tee 得到 Championship `6269`、Middle `6067`、Forward `5358` 码，三组均 `holeCount=18`。
- 真实链路第一次复读曾显示 9 洞/3094 码；根因是首次 Tee 查询缓存了 geometry 缺失结果，package 下载后没有清 `load_geometry` 的负缓存。`50e4c26` 在 `_ensure_geometry_for_course` 与 package-hole helper 统一失效该缓存，并增加先失败后通过的回归测试；重启后同一 Cypress 数据稳定返回 18 洞/6269 码。
- 这项证据证明后端 release → geometry → Tee 重读链路已接通；Watch 端证据见下节。只有新的实际数据缺口才继续 Deep Mine。

### Watch 运行态（真实球场数据）下载与离线恢复（2026-07-27）

- GitHub Actions [run 30306280529](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30306280529) 在 macOS watchOS Simulator 上全部成功：Watch 测试、构建、真实球场 seed、诊断收集和 artifact 上传均通过；这不是物理手表证据。
- `real-course-download-seed` 使用真实搜索结果 `globalId=3881`（Cypress Point Club），取得真实 Championship Tee，执行 package `ensure_geometry=true` 与 18 洞 prep/render，并写入现有 production course/image store；没有新增 installer、缓存协议或 fixture。
- `real-course-download-restore` 是第二个独立进程，未提供 API URL/token，调用 `startCourse(config: nil)` 从本地 production store 开局；因此它验证的是下载后的离线恢复，而不是再次联网成功。
- artifact 中的 `watch-real-course-download.png` 与 `watch-real-course-offline.png`（均 416×496）已由 Codex 逐张检查：两张都显示 `Cypress Point Club`、第 1 洞 `P5`、`407 码` 和真实球道图；两张 artifact SHA256 相同（`4f6727ea97fb6fc463f98fe6badb8d475bf274ee9d2ea18ae86cadf229a7e560`）。
- 两次 launch PID 为 `18929 → 31770`，不同进程；diagnostics 没有 AICaddieWatch crash report、`real-course-*-failed` marker 或 restore error。该证据关闭了软件侧“账号历史中未出现的新球场 → Tee → 几何/图片下载 → 离线重开”门；物理手表的 AutoShot 门仍未关闭。

### TestFlight 签名门修复（2026-07-27）

- 首次当前分支上传 [run 30307710460](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30307710460) 在 archive 前失败：旧 App Store profile 不含 Sign in with Apple，旧 Watch profile 不含 HealthKit。根因是 profiles 在 6 月 6 日生成，而两个 entitlement 在 6 月 29 日加入；原 bootstrap 只确保 Bundle ID，不同步 capability。
- `c7ab42e` 在 `fastlane/Fastfile` 增加幂等 capability 同步：iOS `APPLE_ID_AUTH`、Watch `HEALTHKIT`，随后复用原有 `match(force: true)`。新增 CI contract；`uv run python -m unittest tests.test_ci_workflow` 为 `26/26` 通过。
- Signing bootstrap [run 30308261724](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30308261724) 成功启用 Watch HealthKit，并重建/推送两个 App Store profiles。重跑 TestFlight [run 30308357804](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30308357804) 成功 archive、签名、上传并完成 App Store Connect processing（build `0.1.0 (35)`）。
- IPA artifact 解码验证：iOS embedded profile 含 `com.apple.developer.applesignin = Default`；Watch embedded profile 含 `com.apple.developer.healthkit = true`。这只证明 TestFlight binary 已可安装，不证明物理 Watch 的 Apple 登录、传感器授权、误报/漏报、续航或发热。
- 只读 App Store Connect [run 30308959334](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30308959334) 确认 build 35 为 `VALID / IN_BETA_TESTING`、未过期、出口合规已完成；现有 internal group 为 `allBuilds=true`。本次未分发 external `Private Trial`、未通知 tester。

## 当前工作：真实整轮逐屏复核进行中

Watch 的真实 Hole Root、地图比例、障碍前后沿和 Apple 系统覆盖差异已经收口。iPhone 已接通独立记杆、成绩确认、换洞、计分卡、历史洞修改和可靠结束事务；`bbfdbaf` 的 [Native 30428491722](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30428491722) 已完整验证非破坏性“本场汇总”、继续打球与明确保存结束。当前唯一产品门是用同一真实球场、同一 local round 连续走完 18 洞；第 1→2 洞成功和菜单汇总都不等于完整一轮。最终并排截图由用户批准前不发布 TestFlight。风、空气密度、假成功率和推杆级果岭等高线继续后置。

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

### Watch 首页实时果岭距离结果（2026-07-27）

- 功能 SHA：`2890c5de214cee4b183c77c65e8f90469bfcec95`。首页原先始终显示整洞 Tee 长度，玩家走到球道中段仍可能看到 `567 码`。现在优先显示腕上 GPS 算出的中果岭距离；暂时无腕上结果时回退到已准备的中果岭距离，只有两者都缺失才显示整洞长度。没有改布局、状态或数据协议。
- Watch runtime [run 30236028072](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30236028072) 完整成功：Watch `114/114`、独立 App build 和 21 次真实进程截图全部通过。Codex 已检查同一真实缓存球场的首页：预备距离显示 `262 码`，腕上实时值到达后显示 `211 码`；地图、球童、距上一杆和恢复截图继续正常，artifact 中没有 App crash、未知测试页面或恢复失败。

### Watch 结束页诚实统计结果（2026-07-27）

- 最终功能 SHA：`727e169526252f2ae9359062f1e0bcee0d6b3171`。结束页直接复用已存在的 `greenInRegulation` 与 `fairwayResult`，不新增协议或后端字段。只统计已有成绩的洞；球道只接受大小写不敏感的 `HIT/LEFT/RIGHT`，GIR 只接受明确 Bool，未知或异常旧值不进入分母也不伪装成 miss。
- 结束页以紧凑三列显示推杆、球道命中/已记录和 GIR 命中/已记录；没有明确 outcome 时隐藏对应列。首次运行态截图发现原两个纵排按钮会让标题与次按钮越界，最终改为同一行后，标题、球场、成绩、三列统计、同步提示和两个动作都在 416×496 首屏完整可见。
- Watch runtime [run 30246181671](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30246181671) 完整成功：Watch `115/115`、独立 App build 和 22 次真实进程截图全部通过。Codex 已检查结束页显示 `推杆 16 / 球道 5/7 / GIR 4/9`，artifact 中没有 App crash、未知测试页面、恢复失败或 AutoShot provider failure。

### Watch Map Detail 表冠缩放结果（2026-07-27）

- 功能 SHA：`40e839e880d8d57603873a2944ab14fc9f42ba4e`。历史提交虽然留下 `fullMap/mapScale` 绘制分支和“转表冠缩放”文案，但生产源码从未出现 `.digitalCrownRotation`，属于可渲染而不可操作的死入口。现在只在独立 Map Detail 占用表冠；停在基准位时保留事实左栏和成绩环，转动后进入全屏地图并连续缩放真实位图与全部叠加，回到基准位则恢复外层呈现。
- 设计上没有把早期降权旧稿中的“靠近果岭自动弹 Green View”混进本切片：当前没有完整 pinSet、Green View 边界和恢复规则，整洞图放大不能冒充果岭特写。既有拖旗仍是临时预览；到旗主距离持久化另行按真实数据解决。
- Watch runtime [run 30247952766](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30247952766) 完整成功：Watch `116/116`、独立 App build 和 23 次真实进程截图全部通过。Codex 已对比同一北京丽宫缓存球场的普通/全屏截图：全屏态地图居中，事实左栏与成绩环消失，距离、返回键、动态缩放轨道完整；artifact 中没有 App crash、未知测试页面、恢复失败或 AutoShot provider failure。

## 持续端到端验收基线

以下能力已由里程碑 1–4 建立，后续实现不得回退：

1. iOS 能选择真实球场并创建 `LiveRoundPackage`。
2. Watch 收到或读取同一球场的真实洞、Par、距离和地图数据，而不是 18×Par 4 练习占位。
3. Watch 能进入用户已确认的当前洞页面并在进程重启后恢复这一局。
4. 若链路失败，只记录复现步骤和直接原因；修复最先阻塞用户流程的问题，不提前建设后续平台。

## 2026-07-28 全轮 UI 复核与发布门

Build 35 的可安装性不等于产品视觉获批。当前重新以 2026-07-02/10 Watch 批准图、2026-07-04 iOS 批准图和 2026-07-15 后续 Owner 决定为准，使用真实球场数据按一名球员打一整轮的时间顺序复核。下表是唯一逐屏清单；独立 seed 截图只能辅助定位，不能代替连贯旅程。

| 顺序 | 用户阶段 | 必须走到并留证的状态 |
|---|---|---|
| 1 | 无进行中球局 | Watch/iPhone 启动、登录或连接状态、诚实空态 |
| 2 | 找球场 | 附近/已知球场、全库新球场搜索、无结果与网络失败 |
| 3 | 开局设置 | 9/18 洞或 9+9、真实 Tee、码数未知、首次下载、已缓存离线开局 |
| 4 | 当前洞根页 | 真地图为根；F/M/B、Hole/Par、成绩环、球员/旗位和上一杆事实正确；无几何时降级为大字读距，无距离时才降级为记分 |
| 5 | 地图仪表 | 原图、实打、表冠缩放、选点测距、拖旗、真实障碍；条件不足时不显示假路线、假散布、假概率或风 |
| 6 | 球童 | 根页仅显示通过真实性/新鲜度/模式门的当前杆建议；点击后进入完整建议；否则根页保持事实态 |
| 7 | 记一杆 | GPS 未就绪、位置固定、球杆选择、跳过球杆、距上一杆、手动补杆 |
| 8 | 自动候选 | AutoShot 关闭/不支持、候选接受、拒绝和中断恢复；模拟器只验 UI/状态，不冒充真机传感器证据 |
| 9 | 洞末确认 | 推荐成绩一键接受；手动总杆→推杆→Par 4/5 球道→罚杆；Par 3 跳过球道 |
| 10 | 下一洞候选 | 到下一 Tee 不换洞；候选首杆暂存；确认后归下一洞，Cancel 后作为上一洞 recovery |
| 11 | 赛中修正 | 计分卡、任意洞总分修改、选洞、本洞最近问题修正；历史编辑不改变实战洞 |
| 12 | 中断恢复 | 根页、球杆提示、成绩草稿、候选首杆、离线队列在强杀后回到同一未决任务 |
| 13 | 结束与同步 | 结束确认、诚实统计、离线保留、部分 ACK、成功完成和回到无进行中球局 |
| 14 | iPhone 赛中 | 首页、开局准备、真实地图/读距/球童、记分和跨端当前状态一致 |
| 15 | 赛后复盘 | iPhone 历史/逐洞/逐杆/罚杆与 Web 只读复盘一致，不出现占位或伪造统计 |

当前已复现的第一项偏差：`UI-01`，Watch `.home` 是按钮型记分 Hub，真实 Hole Map 被放到二级“球道图”；这违反单一事实型 Hole Root，也解释了 Build 35 与 S70/批准图体感不一致。修复必须保留现有记分、候选杆、恢复、选洞和结束能力，只改变其进入层级。

### 逐屏问题台账

| 编号 | 状态 | 复现与裁决 |
|---|---|---|
| UI-01 | `FIXED / 运行态已验证` | `d90ddcb` 已把真实地图/事实读距恢复为唯一 Hole Root；[Watch run 30347531477 attempt 2](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30347531477) 在真实 Cypress Point 18 洞下载与离线重开中均进入同一根页。 |
| UI-02 | `FIXED / 运行态已验证` | `7985d49` 根据实际视口与 `you → pin` 像素跨度只缩小静止态地图；242pt 批准图画布仍保持原比例，全屏表冠缩放不受影响。[Watch run 30350643879](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30350643879) 为 `124/124`，真实 Cypress Point 下载与断网重开均完整显示 Tee、果岭和旗位，截图 SHA256 同为 `f2389334c5d0c4de5ba59ed099d4dd0139215d445e2fc7a36dc6243f4a92f102`。 |
| UI-03 | `FIXED / 跨端运行态已验证` | `cf7c6bc` 从真实障碍 mesh 外边界生成近/远点，修正狗腿洞投影先后与直线距离混用造成的 `到 471 / 过 468` 倒序；`172f442`/`577219d` 补齐真实 iOS 安全区截图与共享契约。最终 [Watch run 30392143866](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30392143866) 和 [Native run 30392141564](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30392141564) 均在同一 SHA `577219dc1aed7bab891bbabcb19e46d4d24a8127` 成功。Cypress 沙坑从 Tee 显示 `到 262 / 过 277`，球道中段显示 `到 131 / 过 146`，边界点落在真实沙坑上；iPhone 真实球局同时显示沙坑 `到 10 / 过 165` 与水域 `到 21 / 过 69`，备战障碍行完整位于安全区且不再截到加载态。Watch Tee/中段截图 SHA256 为 `2d5686b13f2995b966527c4208e35b193b5313b2500ac50e33d877913dd1823f` / `f0751c1771cb67b956687a7cf2bc88aa92e4ffc9fa49c6674814e6fa358f9c04`；iOS 备战/实战/避开区截图 SHA256 为 `d7353972f92875f2260accae88ccce55b058afa9e6c7194963e3dae76c29e9fa` / `e188052c5257af0608b67b3ec1971ee0dab4c6c1121b2ff91ddd847c7fa6bafb` / `dcb5f17c36a44800ad062505957b9b168811a90fbf09dc2388be4424693586ea`。固定语义：`到`=当前位置到近沿，`过`=当前位置越过远沿所需总 carry；`sideM` 永不展示。 |
| UI-04 | `FIXED / Apple 平台差异运行态已验证` | `9bb5b4b` 只让赛中 Hole/Hazard 地图忽略安全区并请求隐藏持久系统覆盖，地图恢复全表面，列表、开局和确认页未受影响。真实 Simulator 仍保留右上时钟；这符合 [Apple 公开 API](https://developer.apple.com/documentation/swiftui/view/persistentsystemoverlays(_:)) 的明确约束：它只是 preference，系统可以不采纳，因而不得用私有状态栏 API 冒充 S70。`1cd9568` 将全图放大态距离胶囊移入左上事实区，给时钟留出车道。[Watch run 30399741737](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30399741737) 在同一 SHA `1cd956839e6a0044e986487c3c7d928eaaebf737` 完成 `130/130`、build、真实 Cypress 下载、离线重开、放大和障碍截图；放大/真实根页截图 SHA256 为 `4fa70c90bbc83800294a6377fbc8e3713d53897f2d978b5f9d0e6b1f19add813` / `bd74052162dece39ea35646d9f76a1144d04fd5a56e49fbbea912d8c901edbf0`。 |
| IOS-01 | `FIXED / 跨端回归已验证` | `e4e1c69` 由拥有状态栏的 `RoundHomeView.NavigationStack` 只在 Hole destination 隐藏 system chrome，保留实战页自己的明确返回；球童联网 spinner 复用原状态圆点和原说明行，不再新增高度。完整 [Native run 30406541463](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30406541463) 在同一 SHA `e4e1c698f1e92997b15d18925360dc3c1cd2d1e3` 成功：iOS `115/115`、真实 iPhone XCUITest `3/3`、Watch `130/130`，Watch seed/强杀恢复也成功。Codex 已检查 393×852 真实北京丽宫实战页：没有时间/Wi-Fi/电量或“早上好”返回标题；返回按钮完整；“保存本洞”位于 y=`697…744`，底栏文字最大 y `<817`，均在 Home Indicator 安全边界 `818` 之上；加载态没有改变面板高度。真实图 SHA256 为 `d9e1263e47805a5b88fdaa77afc2563d2da4150d0dcaeb2aea5db6d00422f861`；批准图保持 `5d310e72b11ef133038aea9754688d3edcf841427e0ba90b8e2fe4db30297906`，本切片没有重画已批准构图。 |
| IOS-02 | `FIXED / 运行态已验证` | `443d1d1` 删除五个不可点击的假 Tab，只保留真实“本场计分卡”入口；`8bb8166` 允许随时编辑任意已完成洞且不改变当前实战洞。[Native 30420177192](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30420177192) 的真实北京丽宫流程已显示第 1 洞成绩、编辑后仍以第 2 洞为当前洞。 |
| IOS-03 | `FIXED / 跨端回归已验证` | `1453a75` 接通推荐一键接受、手动总杆→推杆→Par 4/5 球道→罚杆、Par 3 跳过球道与 ordered next-hole 推进。复核同时发现 SwiftUI 复用洞页身份，导致新洞继承旧滚动位置并清掉 GPS；`d301abf` 用 `roundId+hole` 明确每洞视图身份。[Native 30428491722](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30428491722) 的真实流程从第 1 洞进入第 2 洞，洞头/地图/记杆完整，编辑第 1 洞后仍停在第 2 洞。 |
| IOS-04 | `FIXED / 跨端回归已验证` | `cd7220f` 把球童主视图改成稳妥/标准/进攻三套完整 club→club 链；`1023a9b` 明确发送 `includeExplanation=false`，让结构化 options/sequences 与模型 429/503/60 秒延迟解耦。[Native 30428491722](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30428491722) 的真实流程强制三套打法均来自在线结构化结果且无离线 fallback。 |
| IOS-05 | `FIXED / 运行态已验证` | `1c0eb25` 将“记一杆”与洞末成绩确认拆开：先持久化 GPS location，再询问实际球杆；跳过球杆仍保留位置，推荐杆不会冒充实际杆。[Native 30420177192](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30420177192) 已留存独立记杆、球杆提示、跳过后“已记第 1 杆”和一杆后推荐 `3 杆 / 2 推 / 0 罚`的真实截图；`6db5611` 同时把导出的 `shotOrder` 改为每洞从 1 重新开始。 |
| IOS-06 | `SOURCE FIXED / LIVE FUNNEL 待部署` | 根因不是头部 View，而是已有历史球场路径绕过了 geometry-only Tee 洞长补齐。`272493e` 让本次明确选择的 Tee 几何 `target_distance_m` 成为名义洞长权威，并同步进入球童上下文；缺少该 Tee 几何时保持 `nil`，不复用别的 Tee 或当前到果岭距离。失败测试由 `None != 401` 变为相关 5 个球场包场景全绿。最新真实截图仍缺名义洞长的直接原因已查明：live funnel API 容器仍是较早的 `577219d`，北京丽宫 Blue package 第 1–3 洞均返回 `yards: null`，尚未包含 `272493e`。未知所有者的 homeserver service 未被擅自替换；更新明确部署路径后才补最终运行图。 |
| E2E-01 | `OPEN / FINAL GATE` | 当前真实 iPhone XCUITest 只完成第 1 洞并进入第 2 洞；Watch runtime artifact 也由多个独立 seed/restore 进程覆盖状态，不是同一球局连续走完 18 洞。最新 run `30422215123` 中 `watch-round-home`、seed/restore 使用无几何测试状态，因此又显示旧按钮 Hub；它只能证明局部记分和恢复，既不能推翻真实 Cypress 地图根页证据，也不能冒充最终 Hole Root 证据。连续旅程必须从 production course/image store 的地图根页出发，验证每洞杆序重置、换洞、历史修正、强杀恢复、结束与赛后复盘，并逐屏亲检 iPhone/Watch 截图。 |
| E2E-02 | `FIXED / 跨端运行态已验证` | 模型 RED [30425532226](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30425532226) 证明 partial ACK 禁止 `/finish` 且整场保留；真实 UI RED [30426412575](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30426412575) 证明旧入口会破坏性丢弃。`5745835`/`466d1ca`/`bbfdbaf` 让菜单与末洞共用非破坏性暗色汇总，只有全部 event identity ACK 且 `/finish` 成功才清球局。[Native 30428491722](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30428491722) 在 SHA `bbfdbafebe1573d98b644a37f442e2bf1646c04d` 整体成功：iPhone 真实旅程显示 `已完成 1/18 洞`、继续后仍是第 2 洞、明确保存结束后才回到开局；iOS/Watch build 与测试均通过。Codex 已亲检汇总与 Watch seed/restore，汇总截图 SHA256 `a520e687a88ab9ff27a77eafbe4db003fde67169516ce930b155727d333689e4`。 |
| OPS-01 | `RUNTIME RECOVERED` | 2026-07-28 的远端 502 来自 homeserver 重启后 Postgres 容器未自动启动；数据库启动后 API healthy，真实 Cypress 下载重跑成功。此项与产品截图分轨，不再阻塞本地/离线 UI 证据。 |

发布门：完成清单后，由 CI 生成真实 App 模拟器截图；Codex 将批准图与最终图按状态并排提交用户审批。用户明确批准前，不创建下一版 TestFlight。

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
