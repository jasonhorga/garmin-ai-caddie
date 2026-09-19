# Direct Garmin Path and Caddie Algorithm Audit

日期: 2026-09-18 UTC  
审计模型: Claude Fable 5.1, `xhigh`  
审计提交: `23aec471c46791c6d29595936e4a04e864a6ad66`  
模式: source-only, read-only

完整报告、原始 JSON 和交接记录保存在 homeserver：

- Report: `/home/jason/garmin-ai-caddie-data/operations/fable-direct-caddie-20260918/fable-report.md`
- Report SHA-256: `c875c2d853d456ad8804bb8d70ac6d337f884994bfaf2e6d94a5ca5f4d53bb64`
- Raw SHA-256: `77d8b0fb6b9ac4cc57c48fb513cacd5cff85e3b37c8825cf5a2b8c8330ddb5fb`
- Session: `50e3a671-5a99-42fa-abfc-9dc07260be0e`, 178 turns, success

本地这份文档是可审阅摘要；它不把 Garmin 私有运行时顺序、TTL、Virtual
Caddie 权重或 S70 秒数当成已知事实。

## Verdict

### 网络: 不把直连作为主路径

L0/L1 的匿名 OMT 目录和球场事实在技术上可以由 iPhone、Watch 或 Web 访问，
但不应把三端直连 Garmin 作为主架构。当前已缓存球场的 L1 在服务端是本地文件
读取，直连反而增加一次 Garmin RTT，并把中文名、BuildId/release 一致性、缓存
和撤回回退逻辑复制到三端。L2 精确几何的密钥交换和解密需要 Garmin 应用凭据、
`3D-Account-Id` 与玩家 profile，必须留在服务端。L5 历史/账户接口匿名返回 403，
也必须经 homeserver。

推荐唯一目标是：homeserver 物化版本化 L1 -> CDN/对象存储；服务端保留 L2 和
玩家层 L3/L5；三端缓存同一 `(globalId, BuildId, zh_CHS)` 对象并用矢量事实先画
首屏，PNG/精确资源异步按需到达。直连只能作为同一版本契约下的离线/降级备用路径。

### 球童: 当前实现 NO-GO

“5 号铁 -> 1 号木”不是展示层偶发错误，而是当前生成链允许的结构性结果。历史
package 已实际出现 `3H -> Driver`、`9I -> Driver`、挖起杆后接木杆，以及把
Driver 标成 par 3 的 safe 方案。需要先做硬可行性筛选，再做风险调整的期望杆数
优化，不能继续只调 safe/stock/attack 权重。

## A. 直连与中转

### 证据边界

- 〔历史实测〕完整 package 曾为公网 `20.515s`、loopback `13.532s`；冷路径
  `24.4s` 中 history 约 `4.57s`、stats `6.67s`、18 洞 seed `11.99s`；温路径
  `12.9s` 中 seed 仍约 `11.9s`。
- 〔历史实测〕同一候选的公网额外开销大致为每请求 `0.6-1.3s`，不是 12 秒主体。
  去掉 caddie seed 后完整 package 约 `0.925-1.095s`。
- 〔APK/反编译证据·旧报告记录〕APK 中存在 CourseView、OMT/GCS、风、球杆统计、
  3D/contour 等客户端能力线索；本轮压缩 APK 无法重新 grep，不能据此推断运行时
  顺序、TTL、并发或算法。
- 〔未知/需实机测〕实体 S70、实体 Watch、蜂窝/蓝牙中继的启动秒数；Web 对 Garmin
  OMT 的 CORS 响应头；正常 server 的真实队列时间。

### 分层结论

| 层 | 内容 | 直连判断 | 结论 |
|---|---|---|---|
| L0 | nearby/search、`zh_CHS` 名称 | iPhone/Watch 技术可行，Web CORS 未知 | 不做主路径；可作降级 |
| L1 | release、courseData、Hazards、Tee、Par、洞号、名称 | 匿名可取，历史 probe 全部 200 | homeserver 按 BuildId 物化一次，再 CDN 分发 |
| L2 | prodgeometry、Draco、topo/green | 密钥交换需 Garmin app/profile 凭据 | 永远服务端解密；产物可版本化分发 |
| L3 | stats、club profile、seed/decision | 本项目玩家数据和计算 | 事件驱动预计算，不存在 Garmin 直连替代 |
| L5 | 历史 round、shotmap、账户同步 | 匿名 GCS 403，需 CN cookie/CSRF | 只能走 homeserver |

### 链路方程和优化优先级

`T_ready = DNS/TLS + serial(RTT + queue + compute + bytes/BW + decode) + render`

当前单 uvicorn/共享 2 CPU/2 GiB 上，`queue` 还会和安装、prepare-recent、几何
任务争用；换成正常 server 可以降低队列和隧道开销，但不会自动消除 seed 计算。
最大收益顺序应是：

1. 从开局请求移出 18 洞 seed 和重复 sequence 枚举，保留当前洞两阶段决策。
2. L1 按 `(gid, BuildId)` 物化、ETag/CDN 缓存；所有读路径 cache-only，版本刷新另做任务。
3. L3 在 Garmin sync、球包变更、geometry 变更后后台预热；同球场去掉 `round_id`
   对 single-flight key 的重复。
4. 首屏用 L1 矢量事实，精确 PNG/green 延迟到进入对应洞或页面时。
5. 直连 OMT 只作为同一版本契约的备用，不建立第二套中文名/权限权威。

## B. 球童调用链

### 三条当前生成路径

1. **Package seed**: `server_v2/mobile.py:302-323` ->
   `ai_caddie/caddie/mobile_live.py:_caddie_context_seeds` ->
   `_geometry_seed` -> `_route_evidence_seed` -> `build_route_geometry_evidence` ->
   `_shot_option_clubs` -> `_tee_candidate_routes`/`_offline_caddie_options`。
2. **Live decision**: iOS seed context + GPS/lie -> `POST /api/v2/caddie/decision`
   (`server_v2/main.py:1472`) -> `server_v2/caddie.py` ->
   `build_decision_plan` (`ai_caddie/caddie/decision.py:3838`) ->
   `_option_from_route` -> `_select_option` -> `_club_sequences` ->
   `_sequence_first_club` -> `_sequence_tail`。
3. **Lightweight prep**: `course_prep.py:_lightweight_prep_hole` -> `_strategy` ->
   `_strategy_tee_row` -> approach loop -> `steps/tee_club`。Watch 根页消费
   `WatchCourseStore.swift:242`；Watch 还存在另一套离线路线算法。

三端展示没有把序列截断：iOS `CaddiePlanView.swift:840-888`、Watch
`WatchCaddieOptionsView.swift:327-335`、Web `CaddiePage.tsx:849-948` 都会显示
序列。问题在生成端没有说明第二杆的起点、障碍和理由。

### 允许 5I -> 1W 的具体断点

| 编号 | 代码 | 断点 |
|---|---|---|
| M1 | `mobile_live.py:1473-1477`、`decision.py:1070-1097` | 水筛选若所有杆均为 `risk`，静默回退到全球球包 |
| M2 | `geometry_evidence.py:691` | 同一障碍的多个路线交点被 `min(start)..max(end)` 合并成一段假连续区间 |
| M3 | `decision.py:1152-1225,1265-1270` | 障碍成本只给第一杆；`_sequence_tail` 没有障碍参数 |
| M4 | `decision.py:1362` vs `mobile_live.py:1477` | 选杆使用过滤后的集合，展示序列却从全局 `clubProfiles` 重算 |
| M5 | `decision.py:40-42,1269` | 首杆稳定性权重低、推进 credit 不足以约束风险，短杆可能先赢排序 |
| M6 | `course_prep.py:1380-1389` | 开球杆不是 Driver 时，较长剩余距离分支把 Driver 放回 approach ladder |
| M7 | `decision.py:3055-3065`、`mobile_live.py:1975-1998` | 第二杆沿用 Tee 原点的障碍区间，帧不对 |
| M8 | `decision.py:810-819` | 静态全洞距离/最近 carry 可能把 Driver 当成球道中下一杆 |
| M9 | `mobile_live.py:1494-1511,1533-1548` | 用任意剩余球杆填 safe/attack 槽，标签与风险不单调 |
| M10 | `mobile_live.py:920-925` | 历史 par 优先且缺省为 4，可能把错误 par 带进分支选择 |

最短因果链是：M2 形成错误水区间 -> M1 删除所有可行首杆或静默回退 ->
M3/M4 在未过滤全球球包中挑 Driver 作后续杆 -> 三端原样显示 `5I -> 1W`。
这已经由历史 package 的同类输出证实；本快照提交是否复现相同数字仍需回放验证。

## 推荐算法契约

### 阶段 1: 硬可行性

以当前球位/lie 为原点，对每支球杆计算 p10/p50/p90 落点带、风坡修正、横向
离散和逐段 hazard 区间。水、OB、沙坑、树区有交集时直接淘汰，除非用户明确选择
并看到“进攻/冒险”。第二杆起点必须是第一杆落点和 lie，重新投影障碍，不能复用 Tee
距离。没有可行方案时返回 `infeasible` 及原因，禁止静默恢复全球球包。

### 阶段 2: 风险调整的期望杆数

在可行集合上最小化：

`E[strokes] + penalty + bunkerRisk + nextShotUnavailable + dispersion - confidence`

首杆通常会自然选最长可行 Driver；只有水/OB、狭窄球道、短洞、无 1W 或 1W
数据不稳定时才换杆。球道中不得无理由换更长球杆，至少要求当前 lie 允许且输出
layup/位置理由。

### 输出不变量

- 当前杆、预计落点和 p10/p90、下一杆和剩余距离必须同时存在。
- 理由必须指向实际约束或障碍；置信度必须反映样本量和 geometry authority。
- safe/stock/attack 必须是物理上不同且风险单调的方案；不能用任意剩余球杆填坑。
- 冷启动缺少历史时使用保守离散、置信度不得为 high、序列最多两杆。
- 任何非 Tee 的 Driver 都要有明确 lie/样本/用户授权；否则硬拒绝。

### 最小 golden 矩阵

至少落 CI 的 12 例：正常 par4/5 首杆 1W；5I->1W 反例；水前 layup；短四杆；
三杆洞；狭窄球道；OB/沙坑；无历史冷启动；复合 9+9；无 1W/1W 不稳定；风坡
和 lie 变化重规划；多段水区间不得合并。核心指标是硬约束违例 0、非显式进攻
危险区穿越 0、序列连续性 100%、理由/置信度完整、替代方案有真实差异。

## P0/P1/P2 顺序

- **P0**: 修 M1-M7 和多段 hazard 保留；补全 lightweight Driver 排除；approach
  原点重投影；复合后九显式传 `allow_lightweight_fetch=False`；把 18 洞 seed
  移出开局请求。
- **P1**: L1 物化/CDN、single-flight 去 `round_id`、courseData 作为 par 权威、
  持久化 profile id、`/prep`/topo cache-only。
- **P2**: 矢量首屏、Watch PNG 按需、统一任务进度/取消契约、校准期望杆数表。

任何实现前先加入 golden 回放和回滚指标：`Driver 非 Tee`、静默回退、第二杆
更长次数必须为 0；`caddie_seed` p95 回升到 2 秒以上则回滚。

## 审计资源清理

Fable 快照 `/dev/shm/garmin-ai-caddie-fable-direct-caddie-20260918` 已核验无
进程/句柄后按 handoff 精确删除；持久化 report/raw/prompt/manifest/session summary/
handoff 保留。审计没有创建容器、端口、隧道、依赖环境或构建产物。
