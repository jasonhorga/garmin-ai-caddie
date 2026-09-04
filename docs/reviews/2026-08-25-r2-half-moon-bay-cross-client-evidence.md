# R2 Half Moon Bay 事实对账

**日期：** 2026-08-25 UTC  
**用途：** R2 复盘跨端验证的只读基线，不是发布批准。  
**API revision：** `6a6080c6f6867513ed461d20e98a29113bd65433`  
**原始证据目录（私有 homeserver）：**
`/home/jason/garmin-ai-caddie-data/operations/r2-hmb-evidence-20260825`

## 采集边界

通过 homeserver 上与公开 revision 对应的 candidate API 只执行 `GET`：

- 两场 round detail：`17603881`、`17601656`
- 每场 18 个逐洞 shotmap，参数 `includeImage=false`
- 没有调用 correction、sync、ingest 或任何写接口
- 原始响应没有复制到公开 `/home/jason/demos`，也没有写入生产数据卷

杆距复核另使用当前 HEAD `b2688f3c` 的只读源码快照和一个无网络、无端口、
只读根文件系统的临时容器。生产数据卷只以 `:ro` 挂载；容器没有启动服务，
只执行 `effective_club_ladder("me")`、`club_ladder_with_provenance("me")`
和与 `/prep` 相同的 club-row 投影。没有重新请求生产全洞 `/prep`。

## 结果

| Round | 球场 | 成绩 | 逐洞 | 球杆事实 | shotmap | 地图 authority | 缺失数据 |
|---|---|---:|---:|---:|---:|---|---:|
| `17603881` | Half Moon Bay Golf Links ~ Ocean | 102 | 18/18 | 58 | 18/18 | `prodgeometry` 18/18 | 0 |
| `17601656` | Half Moon Bay Golf Links ~ Old | 96 | 18/18 | 53 | 18/18 | `prodgeometry` 18/18 | 0 |

两场的逐洞检查均通过：

- detail 的 `shotCount` 与 shotmap 的 shot 数一致；`shotRefs` 数量一致。
- shot order 都是从 1 开始的连续序列，没有乱序洞。
- `globalId/localHole` 与显示洞号一致：Ocean 为 `6022`，Old 为 `6023`。
- 所有返回的 shot 都有完整 GPS 投影事实；没有 synthetic shot。
- 每洞都有 `geometryRevision`，18 洞没有缺失 `map` 或 `missingData`。

### 统计事实

这些是响应中已有的事实，不是重新推算的建议：

| Round | GIR（记录/命中） | 球道（记录/命中/左/右） | 推杆总数 | 罚杆总数 |
|---|---:|---:|---:|---:|
| Ocean `17603881` | 18/1 | 13/6/2/5 | 36 | 2 |
| Old `17601656` | 18/3 | 14/5/4/5 | 38 | 0 |

## 对 R2 的含义

这份证据排除了“Garmin 两场没有落点数据”这一解释。若 iOS 或 Web 仍显示“没有每一个球的落点位置”，问题在客户端请求、缓存、坐标映射或首帧状态，而不是这两场源数据为空。

它还给出了跨端对账应使用的固定断言：

1. iOS 与 Web 对同一个 `roundRef + hole` 必须显示相同的 shot 数、顺序、club、`globalId/localHole` 和 `geometryRevision`。
2. 地图应声明 `mapKind=prodgeometry`，不得静默回退为示意图；若回退，必须显示缺失状态。
3. GIR/FIR 必须沿用 `recorded` 分母（Ocean 18/13，Old 18/14），不能把缺失伪造为 0。
4. 复盘编辑前后应保留原始 round/shot facts，并只在 correction 层产生变化。

## 完整性校验

以下摘要文件在 homeserver 原始目录中保存，文件非空：

| 文件 | SHA-256 |
|---|---|
| `round-summary.json` | `36e2016085a33669b30c17124df01a66ee896f7eb6941e145f65773b4a1954ac` |
| `shotmap-summary.json` | `b6d86862867a6e44128769455c18ce5806bbff4aeb62c173cd7c6f1baa5ec443` |
| `manifest.txt` | `7ed7d00c8dc2e98d7cfc73f8f1709547cb0885cca47cdfbf40c4af2e7655c0e1` |
| `file-manifest.txt` | `c7e55c68b5dffdaf76ab2320aceb78255dd2f3c878786b17f474a4ca24f2861a` |
| `club-provenance-current-head.json` | `04ef01cca74b075882abe43cff25a4791f58857c8017086bc0d99e9f7ea44e2e` |

## 杆距 provenance 真实对账

先前记录的“candidate `clubs=[]`”结论不正确。受控授权 GET 实际返回了
非空 Garmin 球包；旧 `/prep` 也返回了 club rows，只是没有 `token`、
`distanceSource`、`sampleSize` 或 `confidence`。本次直接对生产数据卷做
只读纯函数复核，确认 Driver、3W、3H 的 Garmin `adviceDistance` 和
`averageDistance` 都是 `0`。当前代码只接受 `5...350m` 的 Garmin 值，
所以这些 `0` 是“Garmin 未提供距离”，不会被标成 `garmin_advice` 或
`garmin_average`。owner 也没有 manual bag，最终来源是 AutoShot 历史中位数。

| 杆 | Garmin type | advice / average (m) | AutoShot 候选 | 当前 HEAD 选择 | `/prep` club projection |
|---|---:|---:|---|---|---|
| Driver | 1 | 0 / 0 | `Driver` 197.0m, n=3155 | `Driver` 197m | 215yd, `history_median`, n=3155, high |
| 3W | 2 | 0 / 0 | `3W` 170.9m, n=535; `3号木杆` 167.9m, n=358 | `3W` 171m | 187yd, `history_median`, n=535, high |
| 3H | 6 | 0 / 0 | `3H` 158.6m, n=236; `3号小鸡腿` 153.5m, n=96 | `3H` 159m | 174yd, `history_median`, n=236, high |

当前 HEAD 先按 canonical token 合并 aliases，再以 `(sampleSize, median)` 选
最强记录，因此每支实体杆只剩一行，Putter 也被排除。上表中的 `/prep`
列是使用 endpoint 同一映射生成的 `name`、`token`、`m`、`yd`、
`distanceSource`、`sampleSize` 和 `confidence`，不是再次调用全洞 endpoint。

作为对照，同一只读容器还执行了正在运行的生产镜像
`garmin-ai-caddie-api:5130f65` 内置 ladder。旧输出为：

| 旧 production ladder row | m / yd | 问题 |
|---|---:|---|
| `Driver` | 197 / 215 | 无 provenance |
| `3W` | 171 / 187 | 与下一行是同一 `wood3` |
| `3号木杆` | 168 / 184 | 3W alias 重复 |
| `3号小鸡腿` | 154 / 168 | 以 alias 出现且无来源/样本 |
| `Putter` | 109 / 119 | 不应进入 full-shot recommendation ladder |

这解释了旧生产显示不一致的最小原因：Garmin 原值并非错误的非零距离；
旧 ladder 没有合并所有 aliases、混入 Putter，而且 wire payload 缺 provenance。
当前 HEAD 的后端数值和来源现已由真实数据证明，不需要 catalog default 填充。

客户端边界仍须分开陈述：iOS `CoursePrepClub` 可以解码上述全部字段，但
当前持久 `CoursePrepPackage` 只保留 holes；Web 会按 `yd` 选最近杆并显示本地化
来源标签；在真实运行证据补齐前，这里只能证明客户端代码投影，不能宣称两个
客户端已显示同一行。真实运行证据见下文。

## Web HMB runtime 证据（2026-08-26 UTC）

在 homeserver 容量门通过后，使用隔离目录和生产 Funnel 当前 revision 对应的
candidate 容器环境中的 admin token，以裸 URL owner 路径运行一次只读 Playwright：

```bash
AI_CADDIE_ADMIN_TOKEN=<candidate-container-env> \
REVIEW_ROUND_REF=17603881 \
VITE_AI_CADDIE_API_BASE_URL=https://caddie.taile36706.ts.net \
VITE_AI_CADDIE_REQUIRE_LINK=true \
npx playwright test e2e/live-ci-player-evidence.spec.ts \
  --config=playwright.live.config.ts --project=desktop-chromium --reporter=line
```

`AI_CADDIE_CI_PLAYER_TOKEN` 在这次 owner-only 路径中未设置。测试将 admin token
只放入 Playwright 隔离 context 的 localStorage；URL、控制台结构化状态、截图和
artifact 均不携带 token。结果为 `1 passed (25.6s)`：

- `/api/v2/history/overview` 200；round detail 200；round `17603881` hole 1 的
  shotmap 200，`found=true`、`globalId=6022`；hole 1 和 2 的 topo PNG 均为 200。
- 生成六张 1440x980 PNG：`results-overview`、`time-trends`、
  `performance-analysis`、`rounds-list`、`review-workbench`、`round-review`；
  单文件大小范围为 116,548--177,241 bytes，均非空。
- `scan_artifacts_for_secrets.py --secret-env AI_CADDIE_ADMIN_TOKEN` 扫描六个
  artifact 文件通过。测试没有调用 correction、sync、ingest 或其他写接口；没有
  部署、重启、Funnel 变更或生产写入。

首次尝试从 `garmin-ai-caddie-api-1` 读取 token，浏览器的 overview 请求为
`net::ERR_FAILED`，而同一 token 对公网 protected endpoints 只读 GET 返回 401。
随后核对发现该健康容器并非 Funnel 当前 `6a6080c6...` revision 的 candidate；使用
`aicaddie-release-6a6080c-candidate` 的环境 token 后，公网 overview 与 rounds
读取均为 200，且上述浏览器运行通过。该诊断没有回显 token 或响应正文。

本次远端 session 目录、`node_modules`、Playwright test output 和本次下载的
`chromium-1223` / `chromium_headless_shell-1223` 均已删除；端口 5173 没有残留
服务。原有共享 Playwright cache 未删除。

## iOS HMB runtime 证据（GitHub Actions run `32919313329`）

运行固定在 head `e484ac3765eef6be353edf11b8e6eb186335a8c3`，参数为
`capture_scope=review`、`review_round_ref=17603881`、
`require_live_preflight=false`、`api_base_url=https://caddie.taile36706.ts.net`。
结果如下：

- iOS XCTest：`257` tests，`0` failures；SwiftJCS consumer boundaries 成功。
- 真实 iOS simulator selected suite：`9/9`，共 `1007.692s`；其中
  `RealFlowUITests` `1/1`（`324.514s`）、`ReviewEditUITests` `1/1`
  （`208.151s`）、`TeeSelectionUITests` `7/7`（`475.026s`）。
- design snapshots 30 files、real Native evidence 75 files 均通过 secret-byte
  scan；`real-screenshots` artifact 中 32 张 PNG 均非空。Watch 阶段因 review
  scope 正确跳过。
- resolver 诊断确认 `roundRef=17603881`、`courseName=Half Moon Bay Golf Links ~ Ocean`、
  hole 1、`globalId=6022`、`localHole=1`、`shotCount=3`、clubs `Driver,5I`。
  health probe 为 200，revision 为 `6a6080c6...`。
- `ReviewEdit` 流程默认进入编辑后点击 `round-edit-cancel`（label `取消`），生成
  `04d-edit-cancelled.png`；此次证据没有 correction、sync 或其他写入。
  `RealFlow` 通过 `UITEST_DISABLE_EVENT_SYNC=1` 运行，事件同步写入关闭。
- preflight 是按 dispatch 参数有意跳过，不应解释为失败或 live-course 缺口。

五个 event-latency 文件只记录 `round-home.appear pending=-1 course=31796`，
数值约 `1381.6`、`1420.4`、`1462.9`、`1564.4`、`1647.1ms`（约 1.38--1.65s）。
它们是 home/round appearance 的延迟代理，**不是**完整 review topo 首帧计时；
首帧 topo 与逐图视觉状态仍需 owner 逐图审核。

## GitHub Web-only runtime 证据（2026-08-26 UTC）

当前 HEAD `8419840b` 的 GitHub Actions run `32944143003` 中，job
`98101156667` 的 Web-only 证据为 `1/1 passed (39.8s)`。artifact
`9597641080` 共 6 个文件、821,477 bytes，zip SHA-256 为
`d321b5816904214abcc37c1f231e02fb844ed7dc2a47e667d83d0b04f454f375`；secret
scan 通过。

- overview、detail、shotmap、topo 请求均为 HTTP 200。
- hole 1 shotmap 为 `found=true`、`globalId=6022`、`localHole=1`。
- topo hole 1 和 hole 2 均为 `image/png`。

前两次 GitHub 尝试 `32942764978`、`32943661246` 都在 overview 的 60 秒
transport wait 处失败；服务诊断没有发现 5xx。它们应记录为传输/证据采集失败，
不能冒充产品错误。第三次 `32944143003` 成功，现作为 Web 主证据；此前
homeserver owner-only run 保留为补充历史。截图仍需 owner 视觉审批，不能据此
声称视觉审批已经完成。

## iOS/Web 对齐边界

Web HMB owner-only run 的 round detail、hole-1 shotmap（`found=true`、
`globalId=6022`）和 topo 请求均为 200，生成六张非空 1440x980 PNG（
`116,548--177,241` bytes），并通过 admin-token secret scan。iOS resolver
与 Web 使用相同 `roundRef=17603881`、hole 1、`globalId/localHole=6022/1`、
shotCount 3 的事实。截图本身不自动构成视觉一致性结论；owner 仍须逐图确认
地图、首帧、球杆距离/来源及取消编辑后的状态。

## 尚未证明

Web 与 iOS HMB 请求和真实截图现已有 runtime 证据，但这不等于视觉 parity
已获批准。以下仍属于 R2：

- owner 对同一 HMB round 的 30 张 iOS 与 6 张 Web 截图逐图审核并批准。
- owner 确认两端实际显示 Driver 215yd、3W 187yd、3H 174yd 及对应来源；上述
  event-latency 代理指标不得替代 topo 首帧判断。
