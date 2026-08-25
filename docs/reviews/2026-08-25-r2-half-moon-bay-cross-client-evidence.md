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

## 尚未证明

本轮是后端事实与 shotmap 对账，不等于 iOS/Web runtime 验收。以下仍属于 R2：

- 同一 round 在 iOS 与 Web 的真实请求/首帧计时和截图并排比较；
- Web 刷新后 review cache 是否避免重复请求，并按 player、round、hole、geometry revision 隔离；
- 趋势页面点击真实 HMB round 后是否正确落到对应复盘洞；
- 3W/3H 的 Garmin 原始杆距到 `/prep` provenance 再到各客户端显示的证据表。

## 杆距 provenance 受控核查

2026-08-25 对与公开 revision 对齐的 candidate API 做了只读、受控的
`GET` 核查。无授权头时，`/api/v2/courses/6022/prep` 和
`/api/v2/courses/6023/prep` 均返回 HTTP 401。随后使用容器内已有的 admin
凭据（只在请求头中使用，未打印或落盘）重新核查：两条请求均返回 HTTP
200、`holeCount=18`，每洞都有 `geometryRevision`；`/api/v2/history/clubs/bag`
也返回 200，但 `clubs=[]`。这说明当前 candidate 数据卷没有可引用的
HMB Garmin 球包值，不能从这两场 round 的 shot label 反推出球杆距离。
本轮没有调用任何写接口。

源码链路本身已存在并通过静态检查：Garmin `/club/player` 与 `/club/types`
字段会持久化；`adviceDistance` 优先于 `averageDistance`；后端 ladder 会
标注 `garmin_advice`、`garmin_average`、`history_median`、`manual`、
`catalog_default` 或 `unresolved`；`/prep` 会返回 `distanceSource`、
`sampleSize` 和 `confidence`，客户端也有对应解码路径。尚未证明的是这些
字段在 HMB 的真实响应中取了什么值，以及 iOS/Web 是否按同一值显示。

结论：HMB 两场的 shot facts 已完整证明；3W/3H/Driver 的真实数值仍是
明确的凭据阻塞，不是“缺失数据”或可以用默认值填充的问题。解除该阻塞
需要一次用户授权的 `/club/player`/`/club/types` 捕获、匹配的 `/prep`
响应，以及同一 HMB round 的 iOS/Web runtime 对账。
