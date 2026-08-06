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
- D02 的 2026-07-26 基线先恢复了诚实降级：当时 Watch 尚未取得完整推荐新鲜度、模式门和真实散布依据，生产根地图只显示真实底图、球员、旗位、F/M/B、测距与成绩环；原固定 `you → layup → green` 路线、固定 `30×26` 椭圆和无条件推荐 chip 均不再显示。该“契约尚不完整”结论已被 2026-07-30 的条件球童层实现取代，见“当前工作”中的待批准候选；真实性门不满足时仍保持这套事实层。
- `elevationDeltaM` 已在显示边界从米换成码；完整球童 options 不再展示未校准 `expectedStrokes`，也删除了“不给成功率”工程备注。离线预备数据没有目标工作流时不再伪造红色“待选旗位”动作。
- 最终 Watch runtime：[run 30218317794](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30218317794) 整体成功：Watch `99/99`、独立 App build、真实缓存球场 seed/restore、球童页与障碍页运行态截图全部通过。
- Codex 已下载并亲自检查当时的 416×496 截图：事实地图显示第 4 洞 P5、实打 `+8` 码和 `256 / 270 / 282` F/M/B；球童页显示 `248 / 262 / 274`、坡度 `+8` 码、`3号木`与离线状态。当时障碍页把沙坑 `[alongRoute, side]` 误报为“前沿 `197` / 越过 `213`”，后续 UI-03 实战审计已取消这项错误证据。四次独立进程 PID 为 `24183 → 24669 → 25108 → 25210`，诊断中无 crash、fatal、unknown screen 或 restore error。

### 新球场 Tee / geometry 索引修正（2026-07-27，已完成）

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

Watch 的事实型 Hole Root、地图比例、障碍前后沿和 Apple 系统覆盖差异已经收口；Hole Root 条件球童层、完整球童打法首屏与顺序成绩确认已有模拟器生产 View 候选，正在等待 Owner 视觉批准，尚不算最终获批。iPhone 与 Watch 都已用同一真实球场、同一 local round 连续走完并结束 18 洞；用户明确批准前不发布 TestFlight。风、空气密度、假成功率和推杆级果岭等高线继续后置。

统一视觉审批工作台 working copy 位于 `/home/ubuntu/claude-web-data/review-artifacts/final-visual-approval-current/index.html`：当前把 Watch Hole Root、GPS 搜星、球童、成绩确认、本洞击球、击球后实际球杆、结束、球场选择、开局设置、iPhone Live Hole 与 IOS-07 首页修改前后共 11 组、27 张批准/production 图放在同一页，并明确把 Web 同一真实球局和透明 topo 留为待替换证据。所有图片引用已由 homeserver Chromium 验证存在，broken image 与 request failure 均为 `0`；整页渲染为 `1440×9880`，回传图 `/home/ubuntu/claude-web-data/review-artifacts/final-visual-approval-current/render-homeserver.png` 的 SHA256 为 `f9d85a4a8f1411cecd71179425cf502405c1861b2cf052886e73125b6e3513e5`。这只是可持续更新的审批入口，不是 Owner 已批准结论；公网 topo-v4 和隔离 CI player 闭环后仍须替换受影响图，再请求最终批准。

### Watch Hole Root 条件球童层候选（2026-07-30，等待 Owner 批准）

- 当前候选 HEAD：`12261af57b6e2cfda8b25e692a3a19a16745c155`。iPhone 将真实 GPS `capturedAt` 写入 live decision；Watch 根页只有在 live decision、允许模式、high/medium confidence、样本不少于 10、evidence、180 秒推荐有效期、15 秒腕上 fix、15 米定位精度、距推荐原点 25 米以内、杆/decision/route 一致以及 aim 位于真实 p10/p90 内同时成立时才显示推荐，否则完整退回事实层。
- 地图只画“玩家 → 当前一杆目标”的虚线；p10/p90 只表达现有数据能证明的纵深范围。没有横向散布数据，因此不画假椭圆；没有下一杆确定决策，因此不画目标到果岭的第二段路线。推荐卡可进入完整 Caddie。
- 当前图是 watchOS Simulator 运行 production `WatchHoleMapView`、使用北京丽宫真实地图样本生成的确定性同状态截图；它不是物理手表截图，也不是一次实时后端球局截图。Actions run `30563717363` 的 iOS target 通过；run `30566921132` 的 Watch 全测试、截图采集和上传步骤通过，随后主动取消无关 build/18 洞回放，因此不得把该 run 表述为整条 workflow 成功。
- 本项状态仅为 `CANDIDATE / OWNER VISUAL GATE OPEN`。批准图与当前候选已生成一对一审批页；在 Owner 明确批准前不标记完成、不进入 TestFlight。

### Watch 球童打法首屏候选（2026-07-30，等待 Owner 批准）

- 实现提交 `c43d09f`，证据 HEAD `59337b4e77459caf53283c90b5ad50276174cbd9`。Hole Root 已经展示当前一杆推荐，点击后直接进入稳妥/标准/进攻三套完整打法，不再先重复距离、坡度与单杆建议；没有完整 plans 的旧 companion payload 才降级到原事实页。
- 保留批准稿的三卡顺序、策略色、暗色层级和标准方案蓝框。后续已确认的产品逻辑优先于旧稿示意：卡片显示完整 club chain 与每杆 carry；未经校准的 expected strokes / 成功率继续不展示，也不把工程说明写给球员。
- Actions RED run `30568220558` 明确因缺少 `WatchCaddieScreen` 失败；GREEN run `30569084237` 的 Watch 全测试、设计截图上传和独立 Watch build 成功，随后主动取消无关整轮回放。截图是在 watchOS Simulator 中渲染 production 三卡内容；它不是物理手表证据。
- 本项状态仅为 `CANDIDATE / OWNER VISUAL GATE OPEN`。一对一审批页已生成；Owner 批准前不标记最终完成。

### Watch 顺序成绩确认候选（2026-07-30，等待 Owner 批准）

- 实现 HEAD `3226b04b657c9abf5b79f1e408fbdc3c85f76f99`。保留后来确认的产品逻辑：推荐成绩可一键接受并直接保存；手动才按 Par 4/5 的总杆 → 推杆 → Fairway（偏左/上球道/偏右）→ 罚杆推进，Par 3 跳过 Fairway。旧批准稿的一页式 stepper 只作为视觉语言，不恢复为交互。
- 下一洞首杆暂存页面仍以“上一洞成绩确认”为当前任务：确认后换洞并把暂存位置作为下一洞第一杆；取消后不换洞，把位置归回上一洞 recovery 并进入实际球杆确认。本切片没有修改模型、持久化、事件或跨端协议。
- 标题、数字、± 控件、绿色主操作和灰色取消现在复用同一紧凑几何；手动页明确显示 `1/4…4/4`，Par 3 显示 `1/3…3/3`。Actions RED run `30570137572` 明确因顺序标签缺失失败；GREEN run `30570474610` 的 Watch 全测试、六张截图上传和独立 Watch build 成功，随后主动取消无关整轮回放。
- 本项状态仅为 `CANDIDATE / OWNER VISUAL GATE OPEN`。旧批准稿没有后来流程对应的同状态画面，因此审批页明确把旧图标为视觉语言，并把六个生产 View 状态作为新的批准候选；Owner 批准前不把它们称为最终基线。

### Watch 本洞击球列表候选（2026-07-31，等待 Owner 批准）

- 实现提交 `6c10f8f`，真实容器证据 HEAD `4027067`。当前列表只显示本洞已持久化的 GPS 击球事实，按顺序展示球杆与相邻位置的距离；推杆仍在洞末成绩确认，不把推杆伪造成有 GPS 起点的逐杆记录。“补记一杆”复用既有定位、球杆提示和 live-round location event，不新增第二套击球协议。
- 旧批准图的第 4/5 行把推杆混进逐杆 GPS 列表，因此只保留其黑底、紧凑分隔线、顺序号和绿色补记动作的视觉语言；production 以三条真实 location event 和明确返回入口重排。真实截图不是直接渲染孤立 View，而是通过 `WatchRoundModel` 写入事件，再由 `WatchRoundContainerView` 从菜单导航进入。
- [Watch run 30602074451](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30602074451) 的 Watch tests、独立 build、真实容器 runtime 与 diagnostics 全部成功。production 截图 `/home/ubuntu/claude-web-data/review-artifacts/watch-shot-list-container-4027067-run-30602074451/runtime/watch-current-hole-shots-runtime.png` 的 SHA256 为 `723faee9e270e146f62f5053c95eae46bff9a6d5bef9b9ec399fc36507e668bf`。
- 本项状态仅为 `CANDIDATE / OWNER VISUAL GATE OPEN`。审批工作台同时展示错误的旧业务示意、正确逻辑下的重排目标和 production 真实容器；Owner 批准前不标记最终视觉完成。

### Watch GPS 搜星真实性门（2026-07-31，运行态已验证）

- 根因是 Hole Root 在 `watchGreenYards == nil` 时回退到球场准备阶段的静态 F/M/B，玩家离开 Tee 后也可能把 Tee 距离看成当前位置距离。实现 `339b57e` 只接受精度 `≤15 m` 的腕上 fix；`.home/.holeMap` 在合格定位到达前进入明确的“搜星中…”状态，完全不显示码数。静态 `distanceM/frontGreenM/centerGreenM/backGreenM` 不再充当 Hole Root 实时距离。
- 搜星页不会遮住更高优先级的未决任务：`.scoring/.clubPrompt/.menu` 与强杀恢复继续优先；底部球局工具入口也保留。真实球场截图 harness 使用 production course 当前 Tee 和真实 Green 坐标重新计算距离，不再以静态字段伪装实时 GPS。
- RED [run 30602272558](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30602272558) 在 `7d3cbac` 精确暴露缺失的 `hasQualifiedWristFix` 与 `.acquiringGPS` 契约；GREEN [run 30602996584](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30602996584) 在 `339b57e` 完整成功：Watch `150/150`、独立 Watch build、真实 `WatchRoundModel + WatchRoundContainerView` 截图和 diagnostics 均通过。日志存在模拟器卸载/WatchConnectivity 系统噪声，但没有 App crash report、unknown-screen、restore-unavailable 或 product failure marker。
- production 图 `/home/ubuntu/claude-web-data/review-artifacts/watch-gps-truth-339b57e-run-30602996584/runtime/watch-gps-acquiring-runtime.png` 的 SHA256 为 `8ed6b5443e952c23786ef14c2760193bbac08e54b996a2eb3155fb618052c0f8`；审批页单项截图 `/home/ubuntu/claude-web-data/review-artifacts/final-visual-approval-current/watch-gps-acquiring-section.png` 为 `1408×738`，SHA256 `8a88bc37a29b65cc09c7af4d17997cfcb35d909a2ad43172d5233a3c9e4db2c3`。本项关闭的是“定位前报假距离”的产品真实性缺陷；最终视觉仍随整页一起等待 Owner 审批。

### Watch 击球后实际球杆首屏密度与真实 carry（2026-07-31，运行态已验证）

- 根因是 `WatchClubPromptView` 同时给球杆行和 Skip 使用 watchOS 默认 `.bordered`；系统把 Skip 扩成约 52pt 高并固定在滚动区外，真实 46mm Watch 安全内容区只剩一支杆。实现 `5f3c67b` 改用项目已有的紧凑 plain 行，推荐杆恢复绿色层级，随后 `d19c43f` 把明确的“跳过球杆 · 位置已存”移入标题次操作行，释放底部整行但不删除 Skip。
- 位置仍在进入页面前由 model 暂存；推荐杆不会自动成为实际杆，点击某杆才写 club event，跳过只保存既有 location。更多球杆继续滚动。DEBUG runtime seed 现在也通过真实 `WatchRoundModel → WatchRoundContainerView` 建立 pending shot，并带四支下载球包数据；不再把孤立 View 当作真实容器证据。
- 第一轮 RED [run 30603920249](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30603920249) 因缺少布局契约失败；第一轮 GREEN [run 30604248922](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30604248922) 虽然 `151/151`、build 和 runtime 成功，但人工看图只露出两行半，因此没有接受。按真实约 160pt 安全高度加强后的 RED [run 30604761266](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30604761266) 精确失败为 `2 < 3`；最终 GREEN [run 30605033686](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30605033686) 完整成功：Watch `151/151`、独立 build、setup-only 真实容器 runtime 与 diagnostics 均通过，不启动 18 洞或写远端成绩。
- 逐图复核又发现 production 容器已经持有完整 `WatchClubOption.medianM`，但 View 边界把它降成了纯名称数组。`0798b1d` 保留推荐杆重排时的完整对象，按统一码制显示有效的实测 carry；缺失、非有限或非正值继续诚实留空，不以 fixture 或推荐距离补造数据。
- 最终 [GREEN run 30645651926](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30645651926) 在同一提交完成 Watch `152/152`、独立 build、production model/container runtime 与 diagnostics；`setup-visual` 明确跳过真实球场、计分写入和 Web job。`416×496` 图 `/home/ubuntu/claude-web-data/review-artifacts/watch-club-carry-0798b1d-run-30645651926/runtime/watch-club-prompt-runtime.png` 显示真实 fixture 换算后的 `220 / 200 / 180` 码，3 行完整且无挤压、重叠或截断，SHA256 `28f70a9ba876c138ee896666a181992c3d6977f32e961caefd7b1915d30e8ca3`；审批页单项图 SHA256 为 `c9d0582029cbbab7d7982e94be8402064cd6ce052994b3195d3b47a039c122dd`。watchOS `ImageRenderer` 一贯不展开 `ScrollView`，因此空白的确定性设计快照不作为本屏证据，最终裁决只使用上述真实 simulator 容器图。

### Watch 结束球局视觉候选（2026-07-30，等待 Owner 批准）

- 实现 HEAD `6bd9116ae123433e9690eb51090e1e791e9ab590`。保留已验证的安全结束事务：待同步事件必须全部获得 identity ACK 且远端 `/finish` 成功后才清除本地球局；`继续打球` 始终非破坏性返回。本切片没有修改模型、持久化、协议或后端。
- 页面恢复原批准稿的两层统计网格与黄/绿/蓝视觉语言：成绩/总杆/推杆为首行，GIR/球道为第二行。百分比由明确 outcome 计算，同时用小字保留 `hits/recorded`；未知与异常旧值继续不进分母。原“稍后同步”改为更准确的“结束前保存”，并只保留一个绿色主动作和一个弱化的继续入口，不恢复旧稿中的暂停、放弃或重复编辑动作。
- RED [run 30571521221](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30571521221) 因旧页面缺少新的展示契约而失败；GREEN [run 30572101827](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30572101827) 的 Watch `141/141`、396×484 截图上传和独立 Watch build 成功，随后主动取消本切片无关的整轮回放。当前截图 SHA256 为 `b17e991b27e9e9ae6d4d7963c76d4d46413d0d10bc0da6524ed973052bf6d3e9`。
- 本项状态仅为 `CANDIDATE / OWNER VISUAL GATE OPEN`。一对一审批页将旧概念稿归一到与 production SwiftUI 截图相同画布，并明确两者的证据边界；Owner 批准前不标记最终完成、不发布 TestFlight。

### Watch 球场选择视觉候选（2026-07-30，等待 Owner 批准）

- 实现 HEAD `dab9b46c5dd0144f1bc279db31bf947b53408c09`。根因不是球场数据或下载链路，而是 production `WatchStartView` 直接使用 watchOS 默认 `List/Section/NavigationTitle`，把每行放大成厚重系统卡片并让 “AI Caddie” 标题占据首屏。当前改用项目已有的紧凑 `ScrollView + 自定义行`模式；Apple 系统时间照常保留。
- 真实 GPS 的附近/已知分组、距离排序、缓存可离线状态、刷新、全库搜索、远端结果、Tee/洞组设置与下载开局均未删除。真实长球场名允许两行完整显示；批准稿中的球场数量、简称与 Par 只作为示意，不用伪造数据填满列表。绿点只表达已缓存，灰点表达需下载，不把“附近”与“缓存”混为同一事实。
- RED [run 30573195316](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30573195316) 因旧 View 缺少附近/已知展示契约而失败；GREEN [run 30573790489 attempt 2](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30573790489/attempts/2) 的 Watch `142/142`、设计截图上传和独立 Watch build 成功。取得普通附近列表、缓存开局设置、全库结果和远端开局设置等 12 个真实进程状态后，主动取消无关后续旅程。附近/全库截图 SHA256 分别为 `dbf6af6cd457fb0901a95cf0301f0068c93dce18676e77944843ea52d249b870` / `e345a85b88ca548fa8cefc71697856442a0b8bc072fc31267f54856deb85abd0`。
- 本项状态仅为 `CANDIDATE / OWNER VISUAL GATE OPEN`。审批页同时展示原批准概念、production 附近页和全库搜索状态；Owner 批准前不标记最终完成。下一可见状态继续审计开局设置，不因球场列表变紧凑就把整个开局流程提前关闭。
- 2026-07-31 逐屏复核发现全库已有真实结果时，页面下方仍显示“选择球场 / 暂无已知球场”。`82b190d` 只在存在可见全库结果且本地分组为空时隐藏该矛盾分组；本地真实行、附近分组、刷新与无结果空态均保留。[Watch run 30649265994](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30649265994) 完整成功：Watch `153/153`、独立 build、production runtime 与 diagnostics 均通过，且 setup-only 范围未运行真实球场计分或 Web job。Codex 已亲看最终 `416×496` 图，两条 Mission Hills 结果完整，当前图 SHA256 为 `2856bc60bd938c2b52e955eff047349aca39e8231eef8779d45d828c8c736e61`。

### Watch 开局设置视觉候选（2026-07-30/31，等待 Owner 批准）

- 原紧凑化实现 `0aec841` 仍把主动作放在内容 `ScrollView` 中，首次下载页的按钮初始只露出上半部分；第一轮固定 footer 又把“离线/下载说明”和主动作一起固定，虽然按钮完整，却把当前洞组/Tee 挤成一条绿色边。最终 production 修正 `003b2bc6506dcf55b254a30385b518e10e5b8bfd` 只固定主动作，把说明留在可滚动内容中；cached 当前洞组和 remote 当前 Tee 均完整可见，下一选项露出一部分作为可滚动提示。
- 首次下载主动作明确写“下载并开始”，已有匹配缓存才写“准备并开始”。9/18 洞、9+9、真实 Tee/码数、缓存匹配、`ensureGeometry`、禁用条件和 `onStart` 均未改；无法取得真实 Tee 时仍不会用猜测值开局。
- 初始视觉 RED [run 30597449279](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30597449279) 测得旧按钮底边有 `322` 个绿色像素；中间 GREEN [run 30597916127](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30597916127) 虽通过第一版按钮门，但人工复核拒绝了只剩 `20px` 的选中项。加强后的 RED [run 30598539958](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30598539958) 只因首次下载仍显示“准备并开始”失败。最终 [run 30599249180](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30599249180) 在证据 HEAD `e5431137647342993bab1562aae797918344d750` 完整成功：Watch `146/146`、独立 build、真实 cached/remote 进程截图和像素门均通过；主动作 `68px`、当前选择 `54px`、视口边缘绿色像素 `0`。
- 本次 workflow 使用 `setup-visual` 安全范围，在截图后明确跳过 `real-course`、计分写入旅程和 Web job；artifact 中没有 `real-course` 或 `journey` 文件。cached/remote 两张 `416×496` 最终图 SHA256 分别为 `ac26882c2451f8a338c321bc9f964c81c0e57a5c2a026863011cfda707b921f0` / `467ade7cfb302692175f3615c04b8369f8063ab91965b5ba94df0ed0cc717f57`。
- 本项现在关闭的是明确的裁切缺陷，状态仍为 `CANDIDATE / OWNER VISUAL GATE OPEN`，不是 Owner 已批准；最终审批前不发布 TestFlight。

### iPhone Live Hole 暗色连续性候选（2026-07-30，地图首屏阻塞仍开放）

- 实现 HEAD `fe3d44a09de060ae07673303a5d147fb28aa8535`。根因是通用 `liveCard()` 固定为白色；7 月暗色 Hole Root 只覆盖地图与主控制台，展开球童、更多调整、拍照取证和球局调整继续复用白卡。当前新增 Hole Root 专用 `#121720` 辅助表面，只替换这四块的颜色系统；球童决策、地图数据、记一杆、球杆确认、推荐成绩一键接受、手动顺序确认和跨端事件均未改，共享浅色卡也未改。
- RED [run 30577872422](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30577872422) 因缺少暗色辅助表面契约而失败。GREEN [run 30578222735](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30578222735) 的 iOS `145/145`、真实 App XCUITest `3/3`、设计图与真实截图/视频步骤成功；取得所需 artifact 后主动取消无关 Watch 重跑，因此 workflow 最终结论为 cancelled，不冒充整条 workflow 成功。根页、球童方案与避开区截图 SHA256 分别为 `7313ff5a27efc7f7af0b59f6f959725a3934dff6bb8159cc2fe1f5ef8037a9b3` / `9e9fe8904e221cf63df731893e4af371a4c61643c8ca8d1b3f3d7112a200220d` / `7a5c77762a70308a5327cabed6d5d3c483cdde8c68c79857b35b535f2923c268`。
- 人工看真实截图又发现独立阻塞：第一张根页截图只出现路线/障碍和暗色 fallback，约 30 秒后的同进程截图才出现完整北京丽宫 topo。直接测同一冷 topo URL 得到首字节 `14.630684s`、总计 `15.996948s`；第二次为 `1.559103s` / `3.008855s`。当前 Compose 只持久化 `/var/lib/ai-caddie`，但 topo 默认缓存位于容器内 `output/topo_render_cache`，容器重建会丢缓存；iPhone 又在 fire-and-forget prewarm 后立刻进第一洞，形成首屏竞速。
- 因此暗色连续性只标 `CANDIDATE`，审批页同时公开修改前/后、同进程稍后完整地图和上述阻塞。下一产品切片先让 topo 缓存跨部署持久化，并让第一洞在可用地图或明确加载态之间有确定门；真正同状态根页证据出现前，iPhone Live Hole 不标最终完成、不发布 TestFlight。

#### 首屏 topo ready 修正（2026-07-30，地图阻塞已关闭）

- 实现 HEAD `310d0bc235f090255b90b5cc8662563f0dd0f959`。Compose 现在把 `AI_CADDIE_TOPO_CACHE_DIR` 固定到现有持久卷下的 `/var/lib/ai-caddie/topo_render_cache`；冷图请求进行中明确显示“球场地图加载中…”，成功与失败不再共用静默 fallback。真实流程在保存第一张 Live Hole 截图前必须看到 `topo-hole-base-ready`，因此以后不能再把未完成地图冒充最终证据。
- [RED run 30582646507](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30582646507) 的真实根页实际已经显示完整 topo，但 success 图片没有进入 accessibility tree，新增证据门按预期失败；只加显式 accessibility element 后，[GREEN run 30584958817](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30584958817) 的 iOS `145/145` 与真实 App XCUITest `3/3` 均通过，截图/视频上传成功。取得 iOS 证据后主动取消无关 Watch 重跑，因此整个 workflow 结论为 cancelled，不冒充全 workflow 成功。
- 当前北京丽宫第 1 洞根页、展开球童、避开区与第 2 洞截图 SHA256 分别为 `8e635150840ad47e62a29c7d632ae5c38a5c8fce4e34d834b2df79e6383880cd` / `40d735d33bb65e2093f606770b90a3aeb374ed1e1fdda3797c9bfd5e9a68c995` / `900e41e50acd0d4d20555251373d78fb192d42db73c43e18ffd8718429eafead` / `5cf6b2962ec6abb7f40843473de2387dc42dc64ab4be69561f084b33b2a9c925`；第 1 洞、记杆后和第 2 洞 tree 都有地图 ready 标识，diagnostics 无 crash/fatal/unknown screen/restore failure。
- 本项只关闭“首屏地图交付”阻塞。整个 Live Hole 仍为 `CANDIDATE / OWNER VISUAL GATE OPEN`；排版、颜色、控件位置与 S70 体感继续按主线逐屏比较，Owner 批准最终审批页前不发布 TestFlight。

#### 跨端透明 topo 候选（2026-07-30，待公网部署闭环）

- `f5b3f87` 将 `topo-v4` 的球场外画布改为透明 RGBA；`ca35661` 移除 iPhone Live Hole 的独立地图卡片底色；`2794117` 让 iOS/Web 请求带不可变 `?v=topo-v4`；`b5d64f2` 让独立 Watch 也优先下载同一 versioned topo，失败才退回旧 prep JPEG。Watch [run 30591346859](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30591346859) 的单测、App build、真实 Cypress 18 洞恢复和运行证据均成功。
- 该 run 仍不能作为透明视觉通过：公网 `?v=topo-v4` 当前实际返回 `ETag: "topo-v3-3881-1"`、RGB `678×1060`，四角均为不透明 `(145,196,253,255)`；54 张真实 `416×496` Watch 截图中的 Cypress Hole Root 因此仍有蓝色矩形，而已有透明素材的独立 Map 状态能正确融入黑色表面。下一步只替换现有 API 容器并保持同一 volume/Funnel/DB，验证 `topo-v4-*`、透明角和持久缓存后重跑 iPhone/Watch；Owner 明确授权部署前不动公网服务。

### 真实 18 洞闭环结果（2026-07-30）

- iPhone 在 SHA `d6f57d96e0c6acb92af345c15276a8d370df357b` 的 [Native run 30507566447](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30507566447) 整体成功。同一北京丽宫真实球局连续完成 1–18 洞；第 10 洞强杀恢复后仍显示已打 9/18 洞，修改第 1 洞不移动当前洞；每洞 F/M/B 为真实整数，球童等待真实结构化结果且不使用离线 fallback；第 18 洞明确保存结束后清除进行中球局并返回首页。最终汇总为 `57 杆 / -15`、`36 推`、球道 `2/3`、`0` 罚杆，结束前安全保存 76 条记录。
- Watch 最终在 SHA `77a6056c1bef05b12b4fa8b4015155cb6e9cf971` 的 [runtime run 30515480491](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30515480491) 整体成功。同一 Cypress Point `globalId=3881` / round `watch-7D610C9D-1D6C-494B-ABF4-FDB91518F56F` 从第 1 洞连续到第 18 洞；18/18 production course/image store 地图可渲染，每个已完成洞恰好一条首杆 GPS；第 10 洞进程重启和第 1 洞历史修改均未改变实战游标。
- Watch 结束汇总先诚实显示 56 条待同步；第二个真实进程通过结束按钮所调用的同一 `confirmFinish()` 路径取得全部 event identity ACK 并完成 `/finish`，证据从 `pending_uploads_before=56` 变为 `pending_uploads=0`、`persisted_round_after=absent`、`screen_after=home`、`remote_finish=success`。后端同时记录 `/events` `200 OK` 与 `/finish` `201 Created`。随后不带 DEBUG 截图参数重启真实 App，磁盘上没有 `watch-round/round.json`；workflow 从 production `Documents/watch-courses/courses.json` 读取 Cypress 缓存坐标 `36.58063641034944, -121.97344543054194` 作为腕上定位，普通 `WatchStartView` 将 Cypress 显示为 `附近球场 · 0.0 km`，并把远处的北京丽宫保留在可点击的 `已知球场`。
- watchOS Simulator 没有可用的 Watch XCUITest 点击驱动，因此结束确认由 DEBUG-only 旅程根直接调用按钮的现有产品方法；网络、持久化、ACK、finish 和无参数重启均为真实运行态。Release/TestFlight 路径、产品协议、UI 与结束语义没有为测试改动。

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
| UI-05 | `FIXED / 真实 GPS 与缓存运行态已验证` | 后端已有球场坐标和 Watch 腕上 GPS，偏差来自 Watch option 解码丢坐标、下载缓存未回填位置以及所有有坐标球场都被统称“附近”。`ecc9c58` 保留 API 坐标，`de1cb62` 接通真实距离排序/文案，`1dbddf1` 只在缺坐标时用 production package 第一洞 Tee 回填缓存；`77a6056` 以 50 km 为明确边界拆分“附近球场/已知球场”，无有效 GPS 时仍显示“选择球场”。[Watch run 30515480491](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30515480491) 完成单测、build、真实 Cypress 下载、离线恢复和同一 round 的 1–18 洞；缓存北京丽宫页面显示真实 `0.4 km`，结束后普通 App 用缓存中的 Cypress 坐标显示 `附近球场 · 0.0 km`，北京丽宫进入“已知球场”，没有伪造距离。该 checkpoint 当时只覆盖后端已知/缓存球场；`88b7695` 已在 2026-08-04 接入 Garmin provider-wide radius 路由，当前状态与证据见本文件“当前剩余产品任务”。 |
| IOS-01 | `FIXED / 跨端回归已验证` | `e4e1c69` 由拥有状态栏的 `RoundHomeView.NavigationStack` 只在 Hole destination 隐藏 system chrome，保留实战页自己的明确返回；球童联网 spinner 复用原状态圆点和原说明行，不再新增高度。完整 [Native run 30406541463](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30406541463) 在同一 SHA `e4e1c698f1e92997b15d18925360dc3c1cd2d1e3` 成功：iOS `115/115`、真实 iPhone XCUITest `3/3`、Watch `130/130`，Watch seed/强杀恢复也成功。Codex 已检查 393×852 真实北京丽宫实战页：没有时间/Wi-Fi/电量或“早上好”返回标题；返回按钮完整；“保存本洞”位于 y=`697…744`，底栏文字最大 y `<817`，均在 Home Indicator 安全边界 `818` 之上；加载态没有改变面板高度。真实图 SHA256 为 `d9e1263e47805a5b88fdaa77afc2563d2da4150d0dcaeb2aea5db6d00422f861`；批准图保持 `5d310e72b11ef133038aea9754688d3edcf841427e0ba90b8e2fe4db30297906`，本切片没有重画已批准构图。 |
| IOS-02 | `FIXED / 运行态已验证` | `443d1d1` 删除五个不可点击的假 Tab，只保留真实“本场计分卡”入口；`8bb8166` 允许随时编辑任意已完成洞且不改变当前实战洞。[Native 30420177192](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30420177192) 的真实北京丽宫流程已显示第 1 洞成绩、编辑后仍以第 2 洞为当前洞。 |
| IOS-03 | `FIXED / 跨端回归已验证` | `1453a75` 接通推荐一键接受、手动总杆→推杆→Par 4/5 球道→罚杆、Par 3 跳过球道与 ordered next-hole 推进。复核同时发现 SwiftUI 复用洞页身份，导致新洞继承旧滚动位置并清掉 GPS；`d301abf` 用 `roundId+hole` 明确每洞视图身份。[Native 30428491722](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30428491722) 的真实流程从第 1 洞进入第 2 洞，洞头/地图/记杆完整，编辑第 1 洞后仍停在第 2 洞。 |
| IOS-04 | `FIXED / 跨端回归已验证` | `cd7220f` 把球童主视图改成稳妥/标准/进攻三套完整 club→club 链；`1023a9b` 明确发送 `includeExplanation=false`，让结构化 options/sequences 与模型 429/503/60 秒延迟解耦。[Native 30428491722](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30428491722) 的真实流程强制三套打法均来自在线结构化结果且无离线 fallback。 |
| IOS-05 | `FIXED / 运行态已验证` | `1c0eb25` 将“记一杆”与洞末成绩确认拆开：先持久化 GPS location，再询问实际球杆；跳过球杆仍保留位置，推荐杆不会冒充实际杆。[Native 30420177192](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30420177192) 已留存独立记杆、球杆提示、跳过后“已记第 1 杆”和一杆后推荐 `3 杆 / 2 推 / 0 罚`的真实截图；`6db5611` 同时把导出的 `shotOrder` 改为每洞从 1 重新开始。 |
| IOS-06 | `FIXED / LIVE FUNNEL 运行态已验证` | `272493e` 让本次明确选择的 Tee 几何 `target_distance_m` 成为名义洞长权威，并同步进入球童上下文；缺少该 Tee 几何时保持 `nil`，不复用别的 Tee 或当前到果岭距离。此前 live funnel 容器未部署该源码，真实截图仍为 `yards: null`；[Native run 30507566447](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30507566447) 的北京丽宫 Blue 第 1 洞现已在真实运行页显示 `Par 4 · 365 码 · 蓝 T`，同时保留实时 F/M/B `342 / 363 / 379`，关闭部署缺口。 |
| IOS-07 | `FIXED / 真实模拟器已验证` | [RED run 30595086698](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30595086698) 在 358pt 实际卡片宽度复现旧布局高达 `158pt > 112pt`，仅新增的长名称契约失败；`3cc8e9b` 将卡片重排为“最多两行球场名 + 右上固定成绩组 / 下一行日期 · 洞数 · Par”。[GREEN run 30595465967](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30595465967) 的 iOS 测试、真实 App XCUITest、截图与视频上传步骤成功；随后主动取消无关 Watch 重跑，因此不把整个 workflow 的 cancelled 结论冒充全套成功。Codex 已逐图对比旧真实首页与新 `1178×2556` 真实首页：`Cypress / Point Club` 正好两行，真实 topo 缩略图、`55 / -20`、`2026-07-30 · 18 洞 · Par 75` 均完整且没有重叠；真实图 SHA256 为 `726b4f37ea66e84b02c90c14f3f5ff5f795346ebfcf57752c6fe987732080e88`，确定性设计图 SHA256 为 `60b12acdb5989623eb3e3ebdcc97e01d18f461e78d7694b816179468032f6546`。 |
| E2E-01 | `RUNTIME COMPLETE / VISUAL PROVISIONALLY APPROVED` | [Native run 30507566447](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30507566447) 已在同一北京丽宫 local round 完成 iPhone 1–18 洞、强杀恢复、历史修正、在线球童、最终 ACK/finish 与回首页；最终 [Watch run 30515480491](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30515480491) 已在同一 Cypress Point round 完成 1–18 洞、18/18 真实地图、每洞唯一首杆 GPS、强杀恢复、历史修正、56 条事件全部 ACK、远端 finish、本地 round 清除、真实缓存坐标附近分组与无参数重启回 `WatchStartView`。实现门已关闭；Owner 已允许视觉暂时不阻塞主线，但发布 TestFlight 仍须针对届时候选单独授权。 |
| E2E-02 | `FIXED / 跨端运行态已验证` | 模型 RED [30425532226](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30425532226) 证明 partial ACK 禁止 `/finish` 且整场保留；真实 UI RED [30426412575](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30426412575) 证明旧入口会破坏性丢弃。`5745835`/`466d1ca`/`bbfdbaf` 让菜单与末洞共用非破坏性暗色汇总，只有全部 event identity ACK 且 `/finish` 成功才清球局。[Native 30428491722](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30428491722) 在 SHA `bbfdbafebe1573d98b644a37f442e2bf1646c04d` 整体成功：iPhone 真实旅程显示 `已完成 1/18 洞`、继续后仍是第 2 洞、明确保存结束后才回到开局；iOS/Watch build 与测试均通过。Codex 已亲检汇总与 Watch seed/restore，汇总截图 SHA256 `a520e687a88ab9ff27a77eafbe4db003fde67169516ce930b155727d333689e4`。 |
| E2E-03 | `RUNTIME COMPLETE / 隔离凭证已验证` | 生产隔离球员 `CI Visual Runner`（`p_0d839389`）已经旋转独立 bearer，并以 GitHub Secret `AI_CADDIE_CI_PLAYER_TOKEN` 注入 workflow；明文 token 未写入仓库、日志或 artifact。[Run 31085653095](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/31085653095) 在 SHA `3bbb3b42820682d8262351b6ad9dc07f9393a28a` 完整成功：Watch 对真实 Cypress Point 完成 1–18 洞、`56` 条事件全部 ACK、远端 `/finish`、本地清场和回首页；后继 Web job 以同一球员打开真实复盘工作台、球局列表和球局详情，`/history/overview`、shotmap 与 Hole 1/2 topo 均为 HTTP 200。生产只读复核确认 round `watch-C79328B1-9183-440F-AD59-5197D53ED5AE` 的 `56` 条事件只在该隔离球员分区，registry 中该 ID 唯一且 `isOwner=false`，Owner 历史仍为 `461` 轮；此前误写入 Owner 的 `5` 轮未删除或修改。Watch/Web artifact SHA256 分别为 `3b308fe134b983c5eec41a662e7e23ce3317272672ebe9b53ee30cbe26f41160` / `07187bb020c21096d108c499e502775bc67e9d8a8ba0741be49cc345b130ad18`，凭证字符串扫描命中 `0`。 |
| OPS-01 | `RUNTIME RECOVERED` | 2026-07-28 的远端 502 来自 homeserver 重启后 Postgres 容器未自动启动；数据库启动后 API healthy，真实 Cypress 下载重跑成功。此项与产品截图分轨，不再阻塞本地/离线 UI 证据。 |

发布门：完成清单后，由 CI 生成真实 App 模拟器截图；Codex 将批准图与最终图按状态并排提交用户审批。用户明确批准前，不创建下一版 TestFlight。

## 当前剩余产品任务（2026-08-05）

| 顺序 | 可见结果 | 当前状态 | 完成门 |
|---|---|---|---|
| 1 | iOS 复盘/备战的 Topo 只显示真实洞形，Watch 长文字不越界 | `VERIFIED / Native + Watch 运行态通过` | 真实 App 截图无外围绿色矩形，45 mm 全部长文字状态留在表盘内 |
| 2 | 新开一场时可按城市、球场关键字或两者组合查找任意 Garmin 球场 | `VERIFIED / 真实新球场旅程通过` | 只查目录；只填城市或关键字均可用；两者都填时分别查询并按 `globalId` 取交集；选中后才下载单座球场 |
| 3 | 不输入名称，直接列出当前坐标 50 km 内的 provider-wide 附近球场 | `VERIFIED / 当前位置旅程通过` | Garmin 独立 radius 路由按 50 条完整分页；默认 50 km、可切 100/200 km；覆盖未缓存球场并按真实距离排序；选中后才下载单座球场 |
| 4 | CourseView Deep Mine 将现有 release/prodgeometry 中未使用的真实数据逐项转成产品判断 | `SOFTWARE CLOSED — 普通地图全部闭合；会员 Green Contours 为外部抓包依赖` | 非会员 APK 请求、字段、mesh、DSKIMG、版本更新、搜索分页和三端缓存均有终态；Green Contours 正反球场抓包在用户方便时补，不阻塞 Overall 主线 |
| 5 | 任意新球场先用轻量真实数据秒开，再原位升级为精确地图 | `VERIFIED / iOS Native + Watch runtime 通过` | `courseData` 先提供路线、计分卡、果岭外形和水/沙粗距离；`prodgeometry` 到达后不换 round/course identity 地升级，断网重开仍可用 |
| 6 | 后端、iOS、Watch、Web 使用同一球场发现、地图权威和缓存升级规则 | `VERIFIED / 完整 CI 与 Native 基线通过` | 同一 `globalId + build/release` 在三端得到一致洞、Tee、障碍、地形与版本；轻量/精确 source precedence 只有一套 |
| 7 | 把 Topo、Watch 越界、附近/搜索/任意新球场串成真实模拟器旅程 | `VERIFIED / 完整真实模拟器旅程通过` | 从当前位置或城市/关键字选一座未缓存球场，下载、开局、离线重开并完成复盘；逐屏留存真实 App 截图，不以单元测试代替旅程 |
| 8 | 最终图逐张对照冻结批准图，由用户视觉批准后再进入 TestFlight | `PROVISIONALLY APPROVED / 不阻塞后续主线` | Owner 已确认当前视觉可暂时接受并继续主线；这不是 TestFlight 分发授权，发布前仍需以届时产品 SHA 做一次短确认 |

当前执行指针：仓库内的软件任务以及 E2E-03 隔离凭证运行门均已关闭，不再从地图或视觉细节派生新开发。下一步只可能由两个彼此独立的外部门触发：获得发布授权后用物理 Apple Watch 验证 AutoShot 误报/漏报、后台、续航与发热；用户方便时提供会员 Green Contours 正反球场抓包。真机门不得用模拟器冒充，会员等高线门不得用普通 DSKIMG 冒充；在任一门具备前，当前候选保持冻结，不发布 TestFlight。

2026-08-06 真机门发布预检发现并关闭一项旧私测遗留：TestFlight workflow 曾把 Owner admin token 作为 Xcode build setting 写入 iOS `Info.plist`。Release 代码虽然已经强制 Sign in with Apple、不会读取该值，但凭证仍可能从 IPA 被提取。当前候选已删除 workflow/Fastlane 注入、plist 键和 project build setting；Release 只内置公开 API origin，iPhone 使用 scoped Apple session 并转发给 Watch。workflow 现在默认 build-only，只有明确设置 `upload_to_testflight=true` 才上传。[Run 31113044025](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/31113044025) 在 SHA `77483dc402f1491d050deae1f5017e4238aaec62` 生成签名 `0.1.0 (36)` IPA 和内嵌 Watch App，未调用 TestFlight upload；产物 SHA256 为 `0aa706c52552305430d64cb0b97e64beab6725eb2749f3cb88f098df5c77ccae`。解包审计确认公开 API origin 正确、`AICaddieAdminToken`/`AI_CADDIE_ADMIN_TOKEN` 字符串均不存在，并用生产 Owner token 实值扫描得到 `0` 命中。尚未上传新 TestFlight，真正分发仍需 Owner 对届时候选明确授权。

完整 [Native run 30992657810](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30992657810) 在 SHA `354297d7f53bc69ed784ff86e66c816cc7de99fd` 成功完成 iOS 测试、北京丽宫真实 1–18 洞、当前位置/名称搜索、未缓存球场下载、轻量→精确 Topo、强杀恢复、Watch 测试与 runtime；Codex 已逐张检查 33 个 iPhone、25 个 Watch 核心状态。最终候选 `dac97c19e240f4d34f12d32a382ab494839d64e0` 相比该完整基线只改动复盘编辑 sheet 与测试/工作流；定向 [run 30999515200](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30999515200) 只执行 `ReviewEditUITests/testCaptureReviewEditFlow` 并成功，真实 tree 中“删除这一杆”为 `y=766…810`，低于安全门 `822`。Watch runtime 复用相同 product tree `1f79e7f257d19c9a462c0757f7033c5f7e26ce87` 的既有运行证据，不把旧 Watch 源码截图冒充当前。公开审批页为 `https://caddie.taile36706.ts.net/demos/garmin-aicaddie-final-dac97c1-30999515200/`：127 个图片引用、0 缺失，入口、iOS 资源和中文 Watch 资源均实测 HTTP 200，homeserver Chromium 已真实加载。2026-08-05 Owner 确认当前视觉“暂时 ok”，因此视觉 Gate 不再阻塞后续 Overall 主线；随后普通地图 Deep Mine 也已闭合，当前执行指针只剩上表列明的外部门。该确认不等于授权分发新的 TestFlight，发布动作仍需在实际候选 SHA 上单独确认。

2026-08-05 Owner 又明确修正 Watch 成绩环：只在主球道图显示，第 1 洞从 3 点开始，顺时针经过 6/9 点，第 18 洞在 12 点结束，为右上系统时间留出完整空区；纯记分 Home、放大、选点测距、拖旗、Hazard、菜单与记分页均不显示。实现 SHA `187d5403f7f8a94ae3f252edc77cb80ec7022a2a` 已由 [Watch runtime run 31020701861](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/31020701861) 在 45 mm 模拟器完成测试、独立 build 和运行截图；Codex 已逐张核对系统时间及无环状态。前后对照页为 `https://caddie.taile36706.ts.net/demos/watch-score-ring-187d540-31020701861/`；旧总审批页中的 Watch Hole Root 证据被本页取代，在 Owner 再次确认前仍不得进入 TestFlight。

球场发现的固定产品规则：开局页同时提供“附近球场”和“搜索球场”两条入口，不二选一。附近球场默认 50 km，无结果时可扩大范围；手动搜索的“城市”和“球场关键字”至少填一项。两项都填时不拼成单个 Garmin query，而是分别查询后按 `globalId` 取交集；真实验证中“深圳”、“观澜”分别有结果，而“深圳 观澜”直接查询返回 0。搜索结果始终是轻量目录，只在用户选中后下载该球场的 Tee、洞和地图。

附近发现已确认使用 Garmin 自己的匿名 CourseView 路由 `Boundaries/{longitude},{latitude},{radiusMetres},32/Courses`，而不是名称搜索路由或本地缓存。2026-08-04 在深圳观澜坐标以 50 km 半径实测分页得到 56 条，最近结果为 Mission Hills 的真实 9 洞环；20/50/100/200 米半径分别返回 1/2/3/5 条。接口异常返回明确错误，不把网络失败或中途分页失败伪装成“附近没有球场”。

Native run `30950302423` 在附近球场 SHA `88b7695` 上完成 build、App 单测和设计截图；唯一失败是旧旅程断言要求同一屏同时看到上一洞“到/过”文字与下一洞标题，而前一 SHA 同一断言刚通过。它不是附近搜索回归，也不另起测试工程；下一个集成 SHA 复验并按真实用户状态改掉脆弱断言。

Deep Mine 当前结论（细节与证据见 `docs/research/IMG_RESEARCH.md`）：

- `HasGreenContour` 已由 Garmin JSON 正式命名并用两组正反球场复现；普通 DSKIMG DEM 在有等高线的 Els 仍约 30 m 网格，因此不是订阅 Green Contours 本体。
- 修复了超过 120 KiB GMP 被旧 FAT 解析器静默截断的问题；默认 DEM sample codec 已由公开已知流、未修改 mkgmap 独立 fixture、四球场全部 26 个 tile 的 header 极值/padding，以及 485,737 个 prodgeometry ground vertices 交叉验证。扩大到 12 区域的 48 个匿名真实包后，96 个 DEM tiles 仍全部为单 level、`shrink=0`、`encodingType=0` 且极值零偏差；加原四场共 52 场、122 tiles。当前产品只接受这个已证明的 CourseView 变体，未来非默认 descriptor 显式触发版本拒绝，不为泛 Garmin 格式猜实现。
- 扩大 corpus 暴露并修复了 RGN 私有 bit-6 trailer；严格模式下 48 场解出 26,106 areas、1,503 lines、312 points，15/3/2 种 TRE 声明类型全部有真实对象且零 subdivision abort。LBL 直接 offset 与 CP1252/CP936/CP932 文本池也已解码；809 条文字主要是 Tee/球场元数据，不是隐藏的沙坑、果岭图例。联合报告 SHA-256 为 `36b729e160dd6b78782bb3903708b5c7c9e41d36a68ea5c579745a1dd9e1550e`。
- Garmin Golf 的 `MEDIUM`、`MEDIUM_PLUS`、`INTERMEDIATE` 三档下载已经分清。`INTERMEDIATE` JSON 中的 `Image` 与现有 DSKIMG 字节完全相同，不是隐藏的更富地图；GMA/UNL 是设备解锁包装。
- 新增匿名轻量 `courseData` 解析入口，按 `BuildId + globalLayoutId` 绑定真实响应。17 洞跨三场对照证明 `3241/18123=水`、`3242/18124=沙坑`，两点顺序为 Tee 侧→果岭侧；旧资料所谓“障碍多边形”已纠正为近/远边界线和锚点。
- `courseData` 已扩大为抓取 manifest 绑定的 114 场、1,701 洞机械审计：`InfoMask` 在 1,701/1,701 洞等于 route flags 高四位，route flags 低 28 位在 1,701/1,701 洞等于 `Flag=1` 路线点的 PointNumber 位图，17,273 个 point 的 `Closure` 全为 0。障碍 flags 低两位在 4,649 个单侧样本中有 4,646 个与 `1=球路右、2=球路左` 一致，3 个 Garmin 原始异常不修饰；高位 subtype 保持 opaque。`3244` 的 105 条全是主路线共线子段，不是球车道或新表面；`3243/18125` 终态保留为第三种 opaque hazard category，不展示猜测标签。权威报告 SHA-256 为 `a519f9772cdd4dba2eebb72c5b128e18dd5856631d1ad44d3b67816438064372`。
- 每洞 30 个 `GreenRadii` 已在 166 个 authority-bound 洞闭合：从正北顺时针每 12° 采样，东向分量需乘 `cos(endpointLatitude)`；4,980 点对选中 VFX 的 P95 误差 `0.355094 m`。它只用于轻量显示轮廓，不冒充 F/M/B 或坡度。真实双果岭 layout `38059` 进一步证明 `hole.json Doglegs` 固定指 A，而 `courseData` 路线末端选择当前 A/B；产品已统一用该选择驱动路线、目标距离、Topo 标记、F/M/B 与坡度 component，18 洞实跑 A=8/B=10，路线/目标最大残差 `0.020981 m`。权威报告 SHA-256 为 `9f5524c80780d6d30357cdefc484a6a766294b18174a46d2178d93544b4675a8`。
- `prodgeometry` 全资产分支已闭合：15 个真实球场、184 洞、2,545 个 Draco mesh 覆盖三个 CourseGen 版本、三个 biome 与海边/内陆场；24 个 mesh 名、`hole.json`、`foliage.json`、每洞独有的 `1024×1024 Terrain.webp` 以及 POSITION/UV/NORMAL/COLOR 通道均有终态产品裁决，未知 mesh、静态资产、attribute semantic 和 data type 都为 0。`Terrain.webp` 经 184 张像素统计确认是 3D 光照用切线空间法线图，不是隐藏彩色地图或 Green Contours；权威报告 SHA-256 为 `cdf931f4c77896ffb1b95d123aa265bfd67dced57fc173c24382f58f965c44cc`。
- DSKIMG 私有矢量语义分支已闭合：13 个 release-bound artifact、11 个唯一 embedded IMG 与 184 洞 prodgeometry 全部入账，166 洞完成跨源绑定；剩余 18 洞严格等于匿名 release 404 的 `31636/31637`，无额外豁免。15 个 area、3 个 line、2 个 point 类型全部得到终态裁决；`0x012e05` 已纠正为 cart path，`0x010b08` 保持 opaque，`0x011409/0x01140e` 是内外嵌套洞域。DSKIMG 只承担粗略/离线显示 fallback，精确距离、lie、障碍和罚杆仍由 prodgeometry/courseData 掌权。冻结报告 SHA-256 为 `ff271c6bddc67de3bebfdee7609e774ac7849527c1db489a9bb7c983c688e8a3`。
- Garmin Golf APK 的普通地图获取/更新链也已闭合：Course 用 `BuildId + GlobalLayoutId + Version`，Image 用 `PartNumber + GlobalLayoutId + Version`，两者不混用；名称、位置+名称和附近目录均完整分页。产品已修正 release 永久旧缓存、仅凭 `gid + hole` 永久复用 prodgeometry、Topo 一年 immutable 和名称搜索只读第一页四个缺口。release 先完整解析再原子替换，离线保留最后有效版本；精确几何以 canonical asset path/version 与 sidecar 绑定，派生 Topo 的磁盘 key/ETag 同时绑定 renderer style 和 geometry authority，Web/iPhone/Watch 统一使用 `topo-v6` 并重新验证。

普通地图的 Deep Mine 与可见产品切片现在均已闭合：新球场可先用轻量包秒开真实路线、计分卡、果岭外形以及水/沙的粗 `到 / 过`，精确 mesh 到达后原位升级；以后 Garmin 更新同一球场也不会继续使用旧 release、旧几何或旧 Topo。订阅 Green Contours 本体只在用户方便时做一次真实 S70/会员正反球场抓包，不阻塞普通球场获取或 Overall 主线。

2026-08-05 已把这组研究结果接入产品候选：后端按 `globalId + BuildId + variant` 缓存并校验 `courseData`，首次 package 立即返回真实路线、Par、Tee 锚点、GreenRadii 绘图轮廓和已证明的水/沙 span，同时在后台准备对应 prodgeometry。iPhone 当前洞低频重查并在同一 round/hole 上切换精确 topo；Watch 在没有位图时先绘制同一事实矢量图，精确图到达后只替换地图事实，保留 round id、当前洞、成绩、推杆、罚杆、选杆和确认草稿。Watch 的部分缓存下次联网也会继续升级，不会永久停在轻量版。homeserver 相关 Python 结果为 CourseView/course-prep `31 passed + 2 skipped`、mobile server `64 passed`；随后 Native run `30992657810` 已关闭 build、真实新球场、18 洞、Watch 与恢复集成门，本项不再阻塞视觉审批。

同日第 6 项已接通 Web：选择任意目录球场先调用与 iOS/Watch 相同的 mobile course package，取得完整真实洞号并触发同一后台精确升级；Web 从 `route + holeImageProjection` 重建同一像素 overlay，在 partial 阶段绘制真实路线、GreenRadii 和水/沙 span，只有单洞变为 ready 后才请求 topo。partial 页面保留当前事实图并每 30 秒低频复读，精确图到达后原位替换；topo 首次渲染竞态也不再把同一 URL 永久钉死在 fallback。备战缓存指纹已纳入该 `globalId` 的 release/courseData 文件，BuildId 或轻量事实变化会自动失效旧缓存。homeserver 结果：相关后端 `112 passed + 2 skipped`，Web 全量 `581 passed + 2 skipped`，production build 与 lint 均通过。iOS Native [run 30969165514](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30969165514) 成功；该 run 的 review scope 明确跳过 Watch，因此另以 [Watch real-course run 30970447204](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/30970447204) 关闭 Watch 门。

Deep Mine 的软件与普通地图完成门已经全部关闭：APK 地图请求/更新链、`courseData` 字段与类型码、DSKIMG FAT/GMP/TRE/RGN/LBL/DEM、prodgeometry 全资产、搜索分页以及 iOS/Watch/Web 同 round identity 的轻量→精确升级均有证据。完整研究账本只剩 Green Contours 一正一反会员抓取和解码这一项外部依赖；详细标准只维护在 `docs/research/IMG_RESEARCH.md`，不再复制庞大计划，也不让它占住当前执行指针。

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
