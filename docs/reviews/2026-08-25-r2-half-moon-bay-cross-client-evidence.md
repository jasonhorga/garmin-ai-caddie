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
来源标签。这里没有 HMB iOS/Web runtime 截图，因此只能证明客户端代码投影，
不能宣称两个客户端已显示同一行。

## 尚未证明

本轮是后端事实与 shotmap 对账，不等于 iOS/Web runtime 验收。以下仍属于 R2：

- 同一 round 在 iOS 与 Web 的真实请求/首帧计时和截图并排比较；
- Web 刷新后 review cache 是否避免重复请求，并按 player、round、hole、geometry revision 隔离；
- 趋势页面点击真实 HMB round 后是否正确落到对应复盘洞；
- 同一 HMB round 的 iOS/Web runtime 是否实际显示 Driver 215yd、3W 187yd、
  3H 174yd 及对应来源。
