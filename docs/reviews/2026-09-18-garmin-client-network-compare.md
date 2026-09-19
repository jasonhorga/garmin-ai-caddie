# Garmin Golf 客户端与 AI Caddie 网络/缓存对照审计

日期：2026-09-18 UTC
审计模型：Claude Fable 5.1，`xhigh`；只读快照；未运行构建、测试、服务或
反编译命令。
审计提交：`23aec471c46791c6d29595936e4a04e864a6ad66`
成功会话：`bdff89c3-223e-423e-82f1-c3670ca2bb3a`
Fable 原始报告：`/home/jason/garmin-ai-caddie-data/operations/fable-net-compare-20260918/fable-report.md`
报告 SHA-256：`0dde9c0bbe8a5e542011823ac2a947d17e74baff9c6b80049c914dc6cb338717`
Raw JSON SHA-256：`09dbfe143e872168172363c7c8eda9b08d67e5d42c17de2346e66bad7a8ddd40`

只读快照 `/dev/shm/garmin-ai-caddie-fable-net-compare-20260918` 已在交接后按
精确 allow-list 清理；没有容器、卷、端口、隧道、worktree、依赖环境或服务
遗留。原始报告保留在 homeserver 的 operations 目录，便于复核完整证据链。

## 结论

用户感受到 Garmin Golf 比本项目快，这个判断成立；当前主要差距不是公网传输
本身，而是资源所有权和等待顺序不同：

| 方面 | Garmin Golf 可证实的形态 | 本项目当前形态 |
| --- | --- | --- |
| 球场事实 | Android 客户端有 Room/SQLite 球场 DAO、版本表、缓存任务和 OMT 版本检查端点 | package 每次按请求重新拼装历史、统计、18 洞 seed、天气和当前投影 |
| 地图资产 | APK 带有球道/果岭/沙坑/水面图集、主题和地图索引；有 Course3d/DownloadManager 组件 | homeserver 下载、解密、Draco 解码、距离/障碍计算，再按洞渲染 PNG |
| 首屏 | 真实顺序、TTL、并发未知；但本地版本化球场资料是明确能力 | 首屏仍依赖 homeserver package，精确几何和 topo 还会与前台竞争资源 |
| 联网角色 | 更像版本检查和差量下载；重资源有后台/设备更新组件 | 目录、release、history、stats、package、prep、topo、green、sync 多条链路互相触发 |

这不等于已经证明 Garmin 的 iOS/Android 首屏一定使用某一条具体 HTTP 顺序，
也不等于证明 S70 与 Golf App 使用同一数据格式。APK 只能证明组件、端点模板和
资产存在；Garmin 的实际 TTL、HTTP/2/3、并发数、预取触发条件和首屏时序仍需
实机抓取或同场景录像测量。

## 时间证据

下面所有“历史实测”都不是当前实体 iPhone/Watch 的 SLA，只用于定位成本。

| 流程/链路 | 历史结果 | 解释 |
| --- | --- | --- |
| package，公网 | total `20.515s`，TTFB `19.684s`，TLS `0.083s`，剩余传输约 `0.83s` | 等待主要发生在服务端响应前，不是下载带宽 |
| package，loopback | total `13.532s`，TTFB `13.529s` | 与公网差约 7 秒，和当时后台安装/单进程争用一致 |
| 旧版冷/warm package | 冷 `21.8–24.4s`，热 `10–12.9s` | D+ 候选后曾测冷 `7.412s`、热 `2.389s`；候选数据不能当实体设备 SLA |
| package 内 18 洞 caddie seed | 一次历史 trace 中 `caddie_context_seeds` 约 `11.986s`，并记录约 `239,642` 次 stability cost | 12 秒主要是服务端重复策略/稳定性计算，不是网络；应先做单次评估复用和 memo，再重新测量 |
| package 冷 history/stats | 同一类 trace 中 history load 约 `4.574s`、stats build 约 `6.670s` | 结束同步或缓存失效后会叠加，不能靠 GZip 或换公网入口解决 |
| tees release | loopback `2.766s`，公网 `4.410s` | 冷路径同步刷新 release |
| 公网首洞阶段 | prep light `0.667s`、render `0.758s`、topo `0.784s`、green `1.179s`、caddie decision `2.541s` | package 完成后仍有多次请求和渲染 |
| Watch 历史模拟器单次 | 本地 shell `63ms`，首洞事实 `1.369s`，首洞可画 `1.375s`，全 18 洞精确资源 `85.245s` | Apple Watch Series 9 45mm 模拟器、CI 轮询口径；不是实体 Watch/S70 |
| S70 | 没有公开可复现的开局秒数 | 官方手册只描述常用球场自动更新、手动更新可排队到接外部电源 |

公开手册依据：

- [Automatic Course Updates](https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-C83CEE8E-B928-4050-B937-341A0BF2A444.html)
- [Manually Updating Golf Courses](https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-6B19B972-BD7B-489E-8CE0-D5CA173645B1.html)

因此，不能把“S70 是 X 秒”或“我们手表是 Y 秒”写成事实。要公平比较，必须
在 GPS 已锁定、同一球场、同一 tee、同一网络条件下，以最后一次点按为 T0，以
“洞 1 的路线、F/M/B 距离、地图均可交互”为 ready，实体 S70、实体 iPhone 和
实体 Watch 各至少 20 次，报告 p50/p95。

## Garmin 侧证据

Fable 从 Garmin Golf Android 3.9 APK 直接核验到以下能力：

- `CourseDAO`、`CourseDetailsDAO`、`CourseLayoutVersionDAO`、
  `CourseOmtDataDAO`、`PremiumMapDAO`、`Hole3dDownloadTrackingDAO` 等本地表；
- `*FromCacheTask`、`Cache*Task`、`WorkManager`/`CoroutineWorker`、
  `DownloadManager`、设备重连/离线登录 worker；
- OMT 目录、`checkForCourseUpdates`、layout release、courseData、图片密钥、
  green contour、premium map、卫星图等 URL/任务模板；
- `AtlasPages`、`MapIcons/GolfAreas`、主题和 `map.assetindex` 等地图资产；
- GCS 成绩/击球/球包的 DAO 和缓存任务，以及 `api.gcs.garmin.cn`、
  `connect.garmin.cn` 主机字符串。

这支持一个保守结论：Garmin 把球场公共资料和玩家历史分成可缓存的数据层，
并有后台更新机制。它不支持以下未经测量的说法：Garmin 一定直连某个服务器、
一定使用某个并发数、一定把 3D 资产用于主打球图、或一定比本项目快多少秒。

## 本项目的关键等待链

当前 iPhone 冷启动大致是：本地 Phase 1 显示 → Garmin 自动同步检查 →
`refreshCourseOptions` → 最常打球场 `fetchHomePackage`。后者仍是完整 package，
即使 Hub 只需要名称和最近状态，也会触发服务器级计算。

新开局通常还会经历：

1. `/tees?ensure_release=true` 冷路径刷新 release；
2. `/mobile/courses/{gid}/package` 读取历史、构建 stats、18 洞 seed，并可能同步天气；
3. 首洞 `/prep`/decision/topo；
4. 后台安装剩余几何和 topo；
5. 手机与 Watch 各自继续读/写自己的缓存。

服务器是单 uvicorn 进程，前台 package/prep/decision 与启动、同步、结束球局后
触发的 `prepare-recent`、Web prewarm、cron 可能争用同一 CPU/GIL 和几何/topo
信号量。公网每次请求增加约 0.5–1.3 秒；当每洞拆成多请求时会被放大，但历史
数据表明服务端计算和争用仍是最大项。

### 必须修正的 courseData 结论

普通 `/mobile/courses/{gid}/package` 顶层在
`server_v2/mobile.py:321-322` 明确传 `ensure_lightweight=True,
allow_lightweight_fetch=False`，因此该路径对缓存缺失的 courseData 不会同步外呼。
但复合 9+9 的后九递归在
`ai_caddie/caddie/mobile_live.py:3251-3267` 没有透传
`allow_lightweight_fetch`；`mobile_live.py:2852` 会从 `ensure_lightweight` 推导
默认值，后九因此可能恢复同步抓取 courseData/release。

准确表述应是：**普通路径是 cache-only；复合后九存在参数漏传，可能同步外呼。**
不能写成“所有运行期路径都不抓 courseData”，也不能在没有冷场地 trace 前断言
每个新球场都必然缺少 F/M/B。

## 重复工作与协议冲突

以下冲突在当前代码中有直接证据，建议每项只保留一个语义：

| 冲突 | 当前表现 | 建议 |
| --- | --- | --- |
| package single-flight key 含 `round_id` 和分钟桶 | home/live/prep/Web/Watch/revalidate 不能共享一次构建 | 去掉 round 运行身份；按球场、tee、nine、历史/球包指纹共享，返回前再绑定 round/event |
| Hub 拉完整 package | 冷启动和同步后都付 18 洞 seed 的代价 | Hub 改用 options + summary，不请求完整 package |
| courseData 承诺轻量首屏但不统一物化 | 新 release/未缓存时首洞可能只能等精确安装 | 安装 journal 增加 L1 stage 0，先物化 release + courseData，再进入几何 stage |
| release 刷新入口分散 | package、prep、topo、green 各自可能刷新 | 统一由后台版本任务和安装 journal 刷新；用户请求 cache-only |
| `ensure_geometry` 同步路径与 durable journal 并存 | iOS/Web/Watch 旗标语义不一致，超时会占住前台 | 唯一安装路径用 journal；保留单洞诊断接口 |
| 两套手机 topo 磁盘缓存 | 同一 PNG 可能重复下载/解码 | 合并为一个按 `(gid,hole,revision,style)` 的缓存 |
| 手机推 green 与 Watch 按需取 green | 同一资源两次传输 | Watch 统一按需；只推当前洞且需显式选择时才例外 |
| prepare-recent、匿名 topo prewarm、cron 多个写入者 | 与用户前台争几何池，且可能重复渲染 | 合并为低优先级 journal 队列，删除匿名 prewarm |
| stats 清理范围不一致 | 结束/同步可能把不相关玩家缓存一起打冷 | 按 player 清理并事件驱动重建 |
| 安装进度与客户端本地计数分裂 | 服务端已经完成的洞在 UI 看不到 | 以服务端 journal 为权威，客户端显示本地/服务端完成数的最大值 |
| sync status 对成员只返回 `ok` | 成员无法显示自己的 lastRun/progress | 返回本人分区的脱敏状态，不泄露 owner 数据 |

`fast_start`/`first_hole_fast`/`fullCoursePending` 在 active code 中已不存在；相关
旧文档只应保留为历史注记和负向回归断言，不能再恢复成第二套 package 协议。

## 统一目标架构

把资源按层拆开，package 只做快速拼装：

- **L0 目录**：附近/搜索和 Garmin `zh_CHS` 名称，短缓存；
- **L1 球场事实**：release、courseData 路线、果岭/障碍事实和洞号映射，按
  `(gid, build)` 物化并用 ETag/immutable；
- **L2 精确资源**：topo、green、precise prep，安装 journal 按洞准备；
- **L3 玩家层**：stats、club profile、18 洞 caddie seed，按玩家/统计指纹/球包
  指纹后台物化；
- **L4 每局动态**：round id、事件游标、天气，响应时轻量绑定；
- **L5 历史**：rounds、shotmap、stats 视图，按版本/ETag 增量取；
- **L6 账户同步**：独立 durable job，和球场资料权限分离。

服务端至少需要 foreground、user-install、background 三条车道；L3 重计算放
子进程或独立 worker，不能阻塞前台 package。手机、Watch、Web 使用同一任务/缓存
契约；Watch 只在需要时取 green，Wi-Fi/充电时做大资源后台下载。

## 实施顺序（本轮没有实施）

### P0

1. journal stage 0 物化 release + courseData，并修复复合后九参数透传；
2. package single-flight 去掉 `round_id`/分钟桶，返回前重新绑定 round 字段；
3. Hub 删除完整 home package；天气移出 package 同步路径；
4. 删除 package 的同步 `ensure_geometry`、匿名 prewarm 和重复 prepare-recent 写入；
5. 统一任务状态 `{stage, done, total, lastProgressAt, cancellable}`，补 install/sync
   cancel 检查点和端点；
6. stats 按 player 清理，成员 sync status 返回本人状态。

### P1

1. L3 玩家层事件驱动物化，package 变成读缓存+轻量拼装；
2. prep 改为逐洞可复用键，club profile 按 shots 指纹缓存；
3. iOS/Watch 专用 URLSession、超时和瞬态重试，JSON 端点加 ETag/If-None-Match；
4. 三端任务中心读同一进度，Web 备战不再隐式安装整场；
5. cron 改调用同一 API job，消除双写者。

### P2

1. 样式版本发布前离线全量预渲染；
2. SSE/长轮询任务流和 background URLSession；
3. 用 L1 路线/障碍线在端上绘制首屏，进一步减少等待 PNG 的依赖。

## 测量门禁

在改动前先把以下事件写入三端和服务端：

`tap_start → shell_committed → catalogue_visible → tee_options_visible →
first_hole_facts → first_hole_map_interactive → first_reco_visible →
all18_facts_available → all18_precise_cached`。

每次请求带 `X-AI-Caddie-Request-ID`，客户端记录 `URLSessionTaskMetrics`、TTFB、
JSON 解码、磁盘写入、图片解码和首帧；服务端记录 history/release/stats/seed/
courseData/geometry/topo/serialization 各阶段。分桶至少包括新球场、已安装、部分
安装、重访、同步并发、结束后立即开局、loopback/Caddy/蜂窝、Watch 直连/手机中继。
每桶至少 20 次报 p50，50 次报 p95；模拟器单次和旧 CI marker 只能作趋势。

建议目标是产品目标，不是当前测量结果：已安装球场公网热路径首洞事实 p50/p95
`0.5/1.0s`；新球场（L1 已物化）`1.5/3s`；L1 首次抓取 `3/6s`。目标必须在
实体设备和真实网络复测后才能承诺。

## 本轮边界

本轮只完成审计和证据整理，没有修改产品代码、没有构建、没有部署、没有上传
TestFlight，也没有改变生产服务或 Garmin 数据。下一步实现范围仍应由产品负责人
从 P0 清单中确认；“加取消按钮”不是速度修复本身，而应作为统一任务契约的一部分
随进度和优先级一起设计。
