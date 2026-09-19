# 网络与球场数据系统第一性原理复审

日期：2026-09-18 UTC  
模型：Claude Fable 5.1，`xhigh`，只读  
审计提交：`23aec471c46791c6d29595936e4a04e864a6ad66`  
会话：`52b87e1b-1ba4-41a5-b60f-0512bd702cc4`  
远端完整报告：`/home/jason/garmin-ai-caddie-data/operations/fable-net-first-principles-20260918/fable-report.md`  
报告 SHA-256：`3297f5d6127f0dc3b7b7517f176814d38bac3692cec2ade10a888b7650a32b25`  
Raw SHA-256：`2c5a7637b9c12f6618d45133f63e0c3f0fa813b26780db2f04b6f368c75c4ae5`

本轮只读使用 APK、源码、已有历史测量和公开文档；没有运行构建、测试、服务、
反编译或新的 HTTP 探测。临时 snapshot 在交接后按精确路径清理。

## 结论

当前问题的根因不是“某个请求慢”，而是把四种不同生命周期的数据焊接成一次
同步 package：球场事实、玩家统计、18 洞策略 seed、每局天气/事件游标。开局时
服务器重新生成玩家投影，导致缓存无法共享、后台任务争用前台、失败也没有清晰
的可用状态。

推荐采用 **C 型混合架构**：

```text
版本化 L1 球场事实
    + 事件驱动的服务端玩家层
    + iPhone/Watch/Web 统一键的本地缓存
    + 客户端矢量首屏
    + 服务端精确 PNG 作为 L2 增强
```

保留服务端的精确几何、距离和球童算法，改变它们进入开局路径的方式。不要把
所有球场地图离线塞进客户端，也不要在端上重写 Draco/地形/策略全栈。

## “开一场球”的最小闭包

T0 定义为球场和 tee 已选定后的最后一次确认点按；GPS 搜星另行测量。

### R0：本地球局壳

本地立刻建立 round、洞号、par 和记分能力。不能依赖网络。

### R1：首洞可打

需要路线、tee 坐标、果岭轮廓、障碍点、tee 对应码数和 F/M/B。它们来自同一份
版本化 L1 数据，不需要先生成精确 PNG。

### R2：首洞可交互

客户端用 L1 矢量显示地图、缩放和点选；球童推荐先用缓存 seed 或稳定的球包距离
兜底，在线策略异步替换。

### R3：18 洞事实

与 R1 使用同一份 18 洞 L1 数据，同时可用。不建立“先返回一洞 package，再换成
另一个 18 洞 package”的第二套协议。

### R4：精确资源

topo、green detail、精确 prep 和完整 18 洞策略在后台按洞准备，必须有进度、心跳、
失败洞和取消语义。

courseData 历史请求约 5.7–19.7 KB、93–153 ms；含路线、GreenRadii、par、tee、
障碍和洞号事实。它是 R1/R3 的合理数据基础，不应等精确 PNG 才存在。

## 必须同步与必须异步

| 数据 | T0 后是否阻塞 | 规则 |
| --- | --- | --- |
| L1 release/courseData/Hazards/GreenRadii | 只有本地和服务端都没有该 build 时阻塞一次 | 选择球场或 tee 时预取；旧 build 可先用并后台校验 |
| 当前洞矢量、F/M/B | 不阻塞 | 与 L1 同源；没有精确 PNG 也可用 |
| 18 洞事实 | 不单独阻塞 | 与首洞同一 payload/版本 |
| 缓存球童 seed | 不阻塞 | 先展示缓存；在线结果异步替换 |
| 天气 | 不阻塞 | 后台补，不写入 stats 缓存身份 |
| Garmin 历史同步 | 永不阻塞 | 只影响统计新鲜度，作为 durable job |
| 精确 topo/green | 后台或按需 | 首洞优先，其余按 2–4 并发；Watch 的 green 按需 |
| Garmin 认证 | token 已缓存时不阻塞 | 资源权限和玩家权限分离；认证失效要明确显示 |

## Garmin 事实边界

APK 可确认 Garmin Golf Android 3.9 具有：

- Course DAO、OMT data DAO、layout version、逐洞 3D 下载跟踪和本地缓存任务；
- CourseView 目录、版本检查、release、courseData、Hazards、等高线和地图密钥端点模板；
- WorkManager/DownloadManager、离线登录和设备重连 worker；
- 通用球道、果岭、沙坑、水面图集、符号和主题资源；
- GCS 成绩、击球和球包的本地 DAO/缓存任务。

公开 S70 手册只确认预装球场、常打球场自动更新，以及手动更新可排队到接外部
电源；没有公开可复现的开局秒数。APK 不能证明 Garmin 的实际 HTTP 顺序、TTL、
并发数，也不能证明通用图集就是打球主图。

因此目前不能声称：S70 是多少秒、Garmin 一定直连哪个服务器、Garmin 与 S70
一定共享格式，或 Garmin 的速度差全部来自网络。

## 现有架构的可证实问题

1. package single-flight key 含 `round_id` 和分钟桶，首页、开局、Watch、Web、
   revalidate 无法共享一次构建。
2. 首页只需要摘要，却请求完整 18 洞 package；启动和 Garmin 同步后会重复付费。
3. package、prep、topo、green 使用了不同的 release 刷新策略，首洞链路可能再次
   外呼 Garmin。
4. 单 uvicorn 进程、几何池、topo 信号量和安装 worker 与 prepare-recent、cron、
   匿名 prewarm 争用前台。
5. 结束一局的 ingest 清理 stats 范围过宽；下一局常被迫冷重建。
6. 天气可在 package 内同步访问 Open-Meteo，并参与缓存指纹，造成长尾和自失效。
7. 手机有两套 topo 磁盘缓存，手机还可能把 green 推给 Watch，而 Watch 又按需取。
8. iOS 退避可累计约 245 秒，服务端已有逐洞进度却没有统一取消契约。
9. 复合 9+9 后九递归没有透传 `allow_lightweight_fetch=False`。普通 package 顶层
   是 cache-only，但未打过的后九可能在请求线程同步抓 release/courseData，最多触发
   两个 30 秒外呼。该问题必须单独修复和测试。

## 唯一目标模型

| 层 | 内容 | 稳定键 | 责任 |
| --- | --- | --- | --- |
| L0 | nearby/search、Garmin `zh_CHS` 名称 | GPS 桶或查询 | 短缓存、后台刷新 |
| L1 | release、tee/par/长度、路线、GreenRadii、障碍、洞号映射 | `(gid, build)` | homeserver 物化不可变 JSON；客户端长期缓存 |
| L2 | topo、green、精确 prep | `(gid, hole, geometryRevision, style)` | journal 逐洞生成；PNG 是增强而非首屏前提 |
| L3a | stats、club profiles | `(player, historyFingerprint, bagFingerprint)` | sync/结束/球包变更后后台重建 |
| L3b | 玩家×球场 18 洞 seed | `(player, gid, build, geometryRevision, L3aFingerprint)` | 异步重建；缓存缺失时使用可靠兜底 |
| L4 | round id、事件游标、天气 | `round_id` | 请求时毫秒级绑定 |
| L5 | history、shotmap、stats view | 玩家指纹/ETag | 增量刷新，不阻塞开局 |
| L6 | Garmin 会话和同步任务 | 玩家 | durable、可见进度、可取消 |

`package` 只能是这些层的快速引用和绑定，不再承担全量计算。

## 不可妥协的不变量

1. T0 后关键路径不包含 Garmin 出站、Open-Meteo 或 18 洞策略计算。
2. R1 与 R3 使用同一份 L1；不存在第二套 `first_hole_fast` 协议。
3. 已缓存 L1 的球场不能对用户显示 `geometryCoverage=missing`。
4. 同一 `(player, gid, build, tee, nine, fingerprint)` 同时只构建一次，round 身份在
   返回前绑定。
5. 结束一局、同步、改球包只失效当前玩家，并立即后台预热。
6. 后台任务 60 秒内必须有进度或心跳，并能在 provider/worker 层取消。
7. 样式版本发布前完成预渲染，不能由用户首访触发全场冷渲染。
8. 三端共享缓存键、任务字段和埋点事件名。

## 架构选择

| 方案 | 结论 | 原因 |
| --- | --- | --- |
| A：现状，homeserver 每次现算 + PNG | 不再作为目标 | 精确图质量好，但首屏、缓存、任务边界都被 package 锁死 |
| B：完全端上球场数据/渲染 | 不做 | 要在 iOS/Watch/Web 重写解密、Draco、地形和策略；授权边界也未确认 |
| C：L1 版本化事实 + 服务端玩家层 + 客户端矢量首屏 + PNG L2 | 推荐 | 保留现有精确算法和地图质量，可分阶段迁移、回滚 |
| D：C 再把 L1/L2 发布成静态对象 | P2 演进 | 已安装球场可绕过 API 进程，但运维和发布复杂度更高 |

不要让 iOS/Watch/Web 直连 Garmin OMT：虽然 L0/L1 技术上是匿名小端点，但
名称语言、CORS、批量授权、缓存一致性和 provider 变更都需要一个权威边界。正确
做法是 homeserver 作为 L1 物化者，再把不可变文件高效分发；Garmin 账户历史和
球场公共数据也必须分开鉴权。

## 建议迁移顺序

### P0

1. 显式透传复合后九 `allow_lightweight_fetch`，取消模板函数的隐式默认推导，并
   加冷复合场景测试。
2. 安装 journal 增加 L1 stage 0，物化 release/courseData/Hazards；tee 选择时预取。
3. single-flight 去掉 `round_id`/分钟桶，返回前绑定 round/event；天气移出关键路径。
4. Hub 改用 options + summary；同步后不再拉完整 package。
5. 删除同步 `ensure_geometry`、匿名 prewarm、死的 upgrade 协调器和手机 green 推送；
   prepare-recent 统一进入低优先级 journal。
6. stats 按玩家清理；成员 sync status 返回本人状态；补 install/sync 进度和取消端点。

### P1/P2

- L3a/L3b 事件驱动物化，prep 按洞缓存，客户端统一 URLSession/ETag/metrics；
- 合并两套 topo 缓存，Watch green 按需，cron 复用同一 job；
- 样式发布前全量预渲染，之后再考虑 SSE/background URLSession 和静态对象化。

## 必须实测的事项

现有数字全部是候选服务器探针或模拟器单次值，不是实体 SLA。应使用实体 S70、
实体 iPhone/Watch、Garmin Golf Android，在 GPS 已锁定、同球场同 tee、同网络条件
下，以最后确认点按为 T0；分别记录：

```text
R1 首洞 F/M/B 可见
R2 地图可交互
R3 18 洞事实可见
R4 精确资源全部可用
```

分桶包括冷/热、部分安装、新球场、已安装重访、Garmin 重连、Wi-Fi/蜂窝、Watch
中继/直连；每桶至少 20 次报 p50，50 次报 p95。Android 只做不解密的主机/时序/
字节量采集，不绕过证书固定。我们的端同时记录 `X-AI-Caddie-Request-ID`、
`Server-Timing`、`URLSessionTaskMetrics`、解码、落盘、首帧和地图交互事件。

建议目标（不是实测承诺）：已安装球场公网热路径首洞事实 `0.5/1.0s`，新球场
L1 已物化 `1.5/3s`，首次物化 `3/6s`；任务最长无进度 `<=60s`。

## 本轮边界

本轮只完成第一性原理复审和证据整理，没有修改产品代码、构建、部署、生产数据或
TestFlight。`NET-TASKS-P0` 仍是 queued，需按本报告的目标模型开始实现。
