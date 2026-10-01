# 实现计划：打球中 / 复盘 / 开球前 / 统计 重设计 + 手表自动记杆

对应设计：本目录 `README.md` 与各原型 HTML。本文件给实现方（Codex）排期用：按数据依赖分 8 批，
每批写明要改什么、依赖什么、怎么验收。批次编号即建议顺序；同一行标“可并行”的可以同时做。

总约束（沿用仓库规则）：

- 每批一个 PR，只做本批范围；UI 批次不顺手改后端，后端缺的数据归 B0。
- 新增或改动的后端字段先写契约和测试，再给客户端用；客户端对缺字段必须能降级（不显示那一项，不报错）。
- 上线仍走现有门槛：homeserver 部署证据齐全后才发 TestFlight；API 和 sync 镜像同 revision 一起构建。
- 屏幕上不写过程提示（同步、下载、检测来源等）；这些状态只进日志和设置页。

## 依赖总览

```
B0 数据底座 ──┬─> B1 手机打球屏 + 旗位 ─┐
              ├─> B4 开球前            │
              ├─> B2 手机记分三屏 <────┘
              │     └─> B3 复盘（含改杆纠错上报）
              ├─> B5 成绩 / 统计 / 球包
              └─> B6 手表界面 ──> B7 手表自动记杆 v2（需 B3 的纠错数据）
```

B1 与 B4 只依赖已有数据，可和 B0 并行起步；B2 的 GPS 开球预选、B5 的新统计、B7 必须等 B0。

## B0 数据底座（后端为主，无界面变化）

| 项 | 现状 | 要做 | 验收 |
|---|---|---|---|
| 球道轮廓（唯一几何来源） | `HolePrep` 有 `greenOutline`、hazards，没有球道；Garmin 几何里有 `Fairway.drc` | `HolePrep.fairwayOutline`：与 `greenOutline` 同一显示坐标系（topo 像素）的多边形数组，另附 WGS84 经纬度环；可能多段；**缺失为 `null`**（不是空数组）。手机包和手表下载包都带同一字段 | course_prep 单测：有 / 无 / 多段；手机与手表解码器对新旧包的兼容测试（缺字段 = null） |
| 开球结果判定（唯一算法） | 手动选 | 一个判定算法，Python 与 Swift 各实现一份、共用同一组测试向量：输入第二杆（或首推）经纬度 + `fairwayOutline` + 路线中线，输出 `hit / left / right / null`；Par 3 或 `fairwayOutline = null` 返回 `null`（= 不预选）。客户端离线算用于预选，服务端用同一算法算统计，以用户保存的值为准 | 共享测试向量：球道内、左、右、贴边、多段、无轮廓 |
| 每洞成绩来源 | score 事件 payload 有 `source`（现为 `ios_score_confirmation`） | 统一取值：`watch_detected`、`phone_shots`、`default`、`manual_edit`；持久化到每洞 | 事件回放后每洞能读到来源 |
| 统计跳过默认洞 | 统计不区分 | 推杆、GIR 统计跳过“来源 = default 且未改过”的洞 | stats 单测：默认洞不计入推杆 / GIR |
| 新统计字段 | 只有时间窗汇总；无罚杆 | `mobile stats` 增加：每场推杆 / GIR / 球道序列；罚杆合计；救球成功率（长草、沙坑起杆后一推进洞或两杆内完成）；一推 / 两推 / 三推+ 比例；按 9 洞环的每洞平均；前九 × 后九组合矩阵与只打 9 洞场数；最难的洞（按平均多杆排序） | 契约测试 + 用夹具球局核对数值 |
| 纠错记录 | `/history/rounds/{ref}/corrections` 只存整洞替换 | 同时写一条结构化纠错日志：操作类型（加 / 删 / 挪 / 换杆 / 改推杆 / 改总杆 / 改开球）、前后值、时间位置；供 B7 使用 | 纠错接口单测：每种操作都产生日志 |

### B0 成绩来源实现说明（B0c）

- 定义在 `ai_caddie/rounds/score_source.py`：`watch_detected` / `phone_shots` / `default` / `manual_edit`。
- 旧值一律算人填的：`ios_score_confirmation`、`apple_watch`、没有 source → `manual_edit`。只有显式 `default` 才算“默认未改”，所以历史统计不变。
- 每洞来源 = 该洞 score / putt / penalty 事件依次合并：全是 `default` 才是 `default`；出现过别的来源就取最近一个非 default 的，之后再来 `default` 也不降级（改过就是改过）。
- 落点：`build_round_state` 每洞 `scoreSource`；`round_ingest` 写进成绩卡每洞 `scoreSource`，且整场推杆总数不计默认洞（全是默认洞时为空，不写 0）。
- 统计：`history_stats` 里推杆 / GIR 的读取都经 `_stat_putts` / `_stat_gir`，默认洞返回空；用户对该洞的推杆更正（annotation）仍然生效。球道不受影响。复盘明细仍显示原始值，默认洞怎么显示由 B3 定。
- “跳过”指不参与：默认洞同时退出推杆 / GIR 的分母（覆盖率、Approach、approachMiss）、推杆数据质量和 `missing_putt_data` 诊断，不算“缺数据”；对该洞做过推杆更正则重新计入。持久化快照（`snapshot._played_holes`）保留 `scoreSource`，没有该字段的旧 / Garmin 洞形状不变。
- 客户端发送新来源放在 B2（记分三屏重做时一起做“是否改过”的判断），B7 发 `watch_detected`。在那之前客户端仍发旧值，统计与现在一致。

### B0 新统计字段实现说明（B0d-1）

都在 `history_stats._scoring` 里（`_round_breakdowns`），移动端 `mobile_stats._SCORING_KEYS` 同步放行：

- `putting` 增加 `zeroPutts / onePutts / twoPutts / threePlusPutts` 和对应百分比（只算 B0c 意义上合格的洞，推杆更正生效）。0 推（切杆进洞）单独一档，不算一推；四档合计 100%。
- `penalties`：`total / holesRecorded / roundsRecorded / averagePerRound`；只统计带 `penalties` 字段、且不是未编辑默认洞的洞（手动记分有，Garmin 成绩卡没有，缺失不当 0；默认洞入库时的 `penalties: 0` 不是记录）。
- `scrambling`：**标准救球率** = 未标准杆上果岭的洞里，最终 Par 或更好的比例。原计划写的“长草 / 沙坑起杆后一推进洞或两杆内完成”需要逐杆起点和完整杆序，现有球位数据不保证包含每一杆和推杆，会系统性少算，所以改用标准定义。以后（B7 有完整杆序后）按球位的 up-and-down 用新字段名，不改这个字段的含义。
- `roundSequences`：每场（新的在前）`holes`（显示洞号 1–18，缺洞时不补位，其余数组与它逐项对应）+ 逐洞 `putts / gir / fairway`。默认洞的 `putts / gir` 为 `null`；`fairway` 不属于 B0c 跳过的字段，照常给出。
- `loops`：按物理 9 洞环的逐洞平均杆差和样本数。环的身份 = Garmin 球场 id + 物理洞段，key 形如 `gid:1001:1-9` / `gid:7:10-18`（没有 id 时 `course:<courseKey>:…`）：27 洞球场每个环有自己的 id（都是 1–9 洞），18 洞单球场前后九共用一个 id、靠洞段区分；成绩卡带了后九 id（包括前后 id 相同的“A/A”）时，后九就是那个 id 的 1–9 洞，只有没有后九 id 的才是单球场的 10–18。同一天合并的两张成绩卡按“末尾连续 10、11…”切分前后半，前半即使被 Garmin 编成 10–18 也不会和后半撞号。名字在全部场次统计完后按 key 一次决定：取“球场 ~ A/C”两段后缀、或单环场次的单字母后缀（“~ A”）里出现最多的环名；“C/B+A” 这类组合名不作证据；没有证据时写“1–9 洞 / 10–18 洞”，不合成“前九 / 后九”。每个环洞的 par 取各场来源 par 的众数（并列取较小者）；所有列表都有完整排序键（组合在显示名之后再比 `frontKey / backKey`）。结果与历史顺序无关。合并场次在 `merge_same_day_halves` 里就统一成 1–18：前半若被 Garmin 编成 10–18，显示为 1–9，物理洞号放在 `localHole`，球位按 `frontHoleOffset` 跟着改；所以 `_scoring` 所有段落的洞 ref 都能唯一指到每个洞。
- `nineCombos`：只算 `holesCompleted == 18` 的场次，按“前环 key → 后环 key”分组（A/B ≠ B/A），行里带 `frontKey / backKey` 和显示名、场数、平均杆；`nineOnlyRounds`：`holesCompleted == 9` 的场数。
- `hardestHoles`：各环逐洞平均杆差最高的 5 个，至少 2 个样本。
- 体积：用真实历史跑一遍，`/stats` 的 scoring 多出约 298,568 字节（gzip 后约 28,412 字节），主要是 `roundSequences`。B5（统计页）上线前定一个移动端载荷预算（比如按最近 N 场截断 `roundSequences`，或拆成按需请求），不在 B0d-1 里改。

### B0 纠错日志设计（B0d-2，已确认）

现状：`/history/rounds/{ref}/corrections` 只存事件本身（iOS 只发 `replaceHoleShots` / `replaceHoleFacts` 两种整洞快照），没有前值、没有计划里的操作类型、没有客户端时间；`seq = len(existing)+1` 不加锁，并发会重号。推杆 / 总杆 / 罚杆的更正走 annotation（`putt_correction / score_correction` 用 `to`，`penalty_correction` 用 `strokes`；`from` 不保证有），annotation id 由服务器生成，没有客户端幂等键。B7 要的是“系统当时给出什么、人改成了什么”。

已确认的方向：写入时记录前值（不在读取时推导）；不回填历史；本人范围的只读接口。

**1. 唯一的持久写入边界：审计跟着事件写在同一行**

- 不另开日志文件。每条更正事件、每条更正类 annotation 在**同一行 JSONL** 里带 `audit` 字段：`{"status": "ok" | "pending", "entries": [...], "reason"?}`。事件和审计一次追加、一次 fsync，不存在“事件落库、日志没写”的缺口。纠错日志是这两个存储里 `audit.entries` 的只读视图。
- **只有一把锁**：每个 player 一把审计锁 `data/players/<pid>/audit.lock`（`fcntl.flock` 独占，做法同 `round_ingest._player_ingest_lock`）。更正事件和更正类 annotation 的写入都拿这一把，不再有按局的锁，所以不存在锁的嵌套和两把锁之间的竞争（例如同一洞的 `replaceHoleShots.manualPenalty` 和 `penalty_correction`）。锁层级：审计锁之内不再获取任何其他文件锁；`round_ingest` 的锁不与它嵌套。
- **全局顺序号 `auditSeq`**：每个 player 一个单调递增的计数，两个存储共用。锁内先把计数文件 `audit_seq` 写成新值（临时文件 + `os.replace` + fsync），再追加记录；中途崩溃只会留下空号，不会重号。所有带审计的记录都带 `auditSeq`，它就是两个存储之间的因果顺序。
- **源数据视图必须一致**：审计锁不与 Garmin 导入 / 同步锁嵌套，所以读历史时可能正好在重新同步。每次审计读取都夹在两次“源数据修订号”之间（历史加载器读取的所有目录的逐文件清单摘要，`stats_cache.history_source_revision`）：前后相同才用这份数据做差，并把修订号记进 `audit.sourceRevision`；变了就重读，连续 3 次都在变则事件照常写入、审计记 `pending`。修复同样只在一致的视图上判断。调用方必须传真正去加载的 loader，不能把更早读好的数据塞进来。
- **没有绕过锁的写入口**：锁在存储函数内部获取，不在路由里——`round_corrections.append_correction` 和 `annotations.add_annotation` 是仅有的两个写入口（路由 `POST …/corrections`、`POST /annotations`，以及 `mobile_reconciliation` 都经过它们），测试和后台任务直接调用这两个函数也一样加锁。测试会断言这两个函数之外没有别的代码直接追加这两类文件。
- 更正事件锁内顺序：读已有事件 → 幂等检查 → 用已有事件算改前状态 → 分配单局内 `seq`（`max(seq)+1`）和 `auditSeq` → 用已有事件 + 新事件算改后状态 → 做差 → 追加一行（`O_APPEND`，写整行含换行，`flush` + `os.fsync`）→ 释放。
- annotation 锁内顺序相同：幂等检查 → 算前值 → 分配 `auditSeq` → 追加 → fsync。
- 做差失败（例如改前 / 改后状态构建抛错）：事件照样写入，`audit.status = "pending"` 带 `reason`，接口返回 `201` 且响应里 `auditPending: true`。
- **pending 必须带上当时的源数据指纹**：`audit.sourceFingerprint` = 改前状态所依赖的全部输入的规范 JSON 的 sha256——该洞的源杆（稳定 id 和原始字段）、成绩卡该洞一行、该局此前所有更正事件的 `eventId`、以及当时的 `geometryRevision`；annotation 则是成绩卡该洞一行加此前所有同洞记录的 `eventId`。连指纹都算不出来时记 `null`。
- 修复路径 `repair_pending_audits(player, round)`：在审计锁内重算指纹。与存下的相同，才按事件前缀重算前后状态，写一条 `auditRepair` 记录（`status: "ok"`，带 `repairsEventId`）；不同（例如中间 Garmin 重新同步过）或原指纹为 `null`，写一条 `auditRepair` 记录，`status: "unrecoverable"`，**不推导新的前值**。原行不改。读取日志接口报告仍未修复的 pending 数和 unrecoverable 数。
- 追加前检查文件末尾：最后一行没有换行时先尝试解析——是完整合法的 JSON 就只补一个换行、保留这条记录；解析失败（写到一半）才截掉这段残缺尾巴。读取时跳过无法解析的行，并在响应里报告 `skippedLines`。两种情况都要测。
- **记录类型**：新写入的每一行都带 `recordType`：`"correction"`（更正事件）、`"annotation"`（annotation）、`"auditRepair"`（修复记录）。修复记录写在原事件所在的文件里，但**所有读取方都要过滤掉它**：`round_corrections.load_correction_events`（进而 `apply_corrections`、shot map、局详情）只认 `correction` 和没有 `recordType` 的旧行；`annotations.list_annotations` / `annotations_for_target`（进而统计、下钻、`AnnotationRecord`）只认 `annotation` 和旧行。只有纠错日志读取认 `auditRepair`。

**2. 稳定身份与幂等**

- 两个存储的每条记录都加服务器生成的 `eventId`（UUID4）；`seq` 只在单局更正文件内排序用。
- `clientMutationId` 两边都持久化；annotation 请求模型新增可选 `clientMutationId`。
- 去重键：更正事件 = `(player, 规范 roundRef, clientMutationId)`；annotation = `(player, clientMutationId)`。
- 同一 `clientMutationId` + 相同请求体（去掉 `clientTime` 后的规范 JSON）→ 返回已存记录，不再写、不再做差；请求体不同 → `409`。没有 `clientMutationId` 的旧客户端不去重（与现状一致）。
- 日志条目 id：`logId = "{eventId}:{序号}"`。

**3. 做差的范围（不拿渲染后的响应做差）**

- 改前 / 改后状态都从“编辑状态”构建，而不是 `build_round_hole_shot_map` 的响应：每杆 `{id, displayIndex, club, lie, end, teeStart}`。
  - `id`：稳定 shot id；`id` 为空的行（合成发球台行）不参与。
  - `club / lie`：存储里的原值（原始 `clubName` / `start.lie`，或快照里的 `club / lie`），只做首尾空白处理，不用显示用的规范化球杆名。
  - `end`：落点像素，来自最新的 `replaceHoleShots` 快照；没有像素快照时，用改前那一刻的投影（同 shot map 的投影函数，不含图片）得到，并记下 `geometryRevision`。
  - `teeStart`：只有显示第 1 杆的起点参与比较（发球位置）。其余各杆的起点是由上一杆落点连起来的派生值，**不比较**，所以挪一个落点不会在下一杆起点上再记一条 `move`。
- 缺字段一律当 `None`；`None` 对 `None` 不算变化，`None` 对有值算变化。
- `teeStart` 只在同一个 shot id 前后都是第 1 杆时比较；调序让另一杆变成第 1 杆时不比较起点，只记 `reorder`，不会冒出假的 `move`。
- `move` 只在前后 `geometryRevision` 相同、且落点（或上面条件下的第 1 杆起点）像素变化超过 1 px 时产生。
- **坐标系不可比时，不写任何位置条目**。服务器的改前视图总是当前的 `geometryRevision`（修订号对不上的旧像素快照在读取时本来就不算数，会回落到当前投影）。事件的修订号与之不同或缺失时，没有共同坐标系，无法证明位置是否变了：不产生 `move`，也不产生任何“几何变化”条目；只在这一批审计上记 `positionComparison: {"status": "unavailable", "beforeRevision", "afterRevision"}`（可比时为 `"compared"`）。
- 因此 iOS 用 `replaceHoleShots` 提交的“只改了球杆 / 球位 / 罚杆”的整洞快照，即使中间地图刷新过，也只会记 `club / lie / penalty`，不会冒出假的位置事件。原草案里的 `geometryChanged` 条目取消。`replaceHoleFacts` 和当时拿不到几何的旧逐杆编辑同样不做位置比较。

**4. 操作词表与映射**

计划里的 `add / delete / move / club / putts / total / drive`，加上现有编辑能产生的 `lie / penalty / reorder`。

- 整洞快照：只在后 → `add`；只在前 → `delete`；`move` 见上；球杆不同 → `club`；球位不同 → `lie`；前后都在的杆相对顺序变了 → 一条 `reorder`（前后值是 id 列表）；`manualPenalty` 变了 → `penalty`。
- 旧逐杆 op 的后状态是服务器按“已有事件 + 这条事件”重建的 shot map，与改前视图做同样的差。拿不到几何时 shot map 本来就不显示 `addShot` 加的杆，所以这种情况下不记 `add`。
- 旧逐杆 op：`deleteShot → delete`，`restoreShot → add`（`restored: true`），`addShot → add`，`editField club → club`，`editField lie → lie`，`editField position → move`（同样要求修订号相同），`reorderShot → reorder`，`setHolePenalty → penalty`。
- `drive` 保留词表，生产方是 B3 的开球编辑，本批不测。
- 加杆 / 删杆引起的总杆变化不再单独记 `total`。

**5. annotation 的前后值**

- 规范目标：`targetType = "hole"`，`targetId = "{roundRef}:{显示洞号}"`；匹配时认合并局的 id 和成员 id（1–18 显示洞号），存储时保持客户端给的 `targetId` 不改写。
- 不认识的 ref：**不返回 `404`**（实现时的调整）。现有公开契约允许在成绩卡进入历史之前就写 annotation（测试和实时对局都这样用），所以照常写入，审计记 `pending`、`reason: "target round not found"`、指纹为 `null`，修复时记 `unrecoverable`。更正事件接口和日志读取接口仍然对不认识的 ref 返回 `404`。
- 规范化后的日志一律是 `before / after`：`putt_correction` / `score_correction` 的 `after = payload.to`，`penalty_correction` 的 `after = payload.strokes`。
- `before` 在审计锁内、追加之前计算，取**该洞当时的生效值**，与局详情显示的是同一个值（同一个函数算出），包括更正存储里的状态：
  - 推杆：成绩卡原值，被同目标最后一条 `putt_correction` 覆盖；
  - 总杆：成绩卡原值，被最后一条 `score_correction` 覆盖（实现时核对过：局详情和统计的洞分都只认成绩卡 + `score_correction`，更正存储里的加 / 删杆不改变它，所以前值也不含它们）；
  - 罚杆：成绩卡原值、更正存储的 `setHolePenalty` / 快照 `manualPenalty`、`penalty_correction` 三者里 `auditSeq` 最新的一个（旧记录没有 `auditSeq`，排在所有新记录之前，按文件顺序）。
- `payload.from` 不作为前值，只原样保留为 `clientFrom`。
- 反方向：更正事件（逐杆编辑）的罚杆前值是编辑页看到的 shot map `manualPenalty`，它本来就不显示 annotation 路径的 `penalty_correction`，所以不包含后者。两个存储的先后仍由 `auditSeq` 唯一确定。
- 测试覆盖“已有一条更正后再改”和“两个并发请求”（后者的 `before` 必须是前者的 `after`）。

**6. 路径与读取接口**

- 更正文件名改为 `{可读前缀}--{sha256(规范 ref) 前 16 位}.jsonl`，不再因替换字符而把两个 ref 撞成一个文件。已有的旧文件名只读合并，新写入只进新文件。
- 旧记录（没有 `eventId` / `recordType` / `auditSeq` / `audit`）：
  - 合成确定的 id：`legacy:{sha256(源文件名 + "\n" + 行号 + "\n" + 该行原始字节) 前 16 位}`，和新记录的 UUID4 不可能相同。
  - 更正回放顺序：旧文件的事件按文件行序在前，新文件按行序在后；新文件的单局 `seq` 从旧、新两个文件里的最大 `seq` 往后接。
  - 旧记录没有审计，不进纠错日志，所以日志游标只涉及新记录，不会和旧记录交错。
- 写入和读取都先确认该 ref 能在本人历史里找到，找不到返回 `404`。
- **合并局的身份**：写入前按历史把 ref 解析成规范 id（`row.id`），事件只写进规范 id 的文件；去重、`seq`、回放和前值都跨这一局的所有 ref（规范 id 加成员 id 的旧 / 新文件）合并计算，所以经成员 id 重试是同一次修改（相同请求体返回原记录，不同请求体 `409`）。shot map 读取走同一套解析（`correction_audit.round_identity` + `round_corrections.load_round_events`）。**历史读不出来（离线、连续变化）时拒绝写入更正事件**（`IdentityUnavailable`，接口返回可重试的 `503`，什么都不写）：此时无法确定规范 id 和去重范围，按请求里的 ref 落盘可能把成员 id 当成新局、把重试变成第二条事件。后台调用方必须稍后重试，不能退回用请求 ref。历史可读但做差失败时，事件仍照常写入、审计记 `pending`。合并顺序：没有 `auditSeq` 的旧记录在前（按 `ts`、再按文件顺序），之后按 `auditSeq`。
- `GET /api/v2/history/rounds/{ref}/correction-log?after=<cursor>&limit=<n>`：只读本人（player 取自 token，路径里没有 player）；`limit` 默认 200、上限 1000。
  - 最终顺序：两个存储合并后按 `(auditSeq, 条目序号)` 排序，这是全局的因果顺序。
  - 修复记录用它自己写入时分配的新 `auditSeq`（带 `repairsEventId` 指回原事件），所以已经翻过去的游标不会漏掉后来补上的条目。
  - `after` / `nextCursor` 是不透明游标：`(auditSeq, 条目序号)` 编码成 base64url，客户端只原样回传；服务器拒绝解码失败的游标（`400`）。
  - 响应另带 `pendingAudits`、`skippedLines`。
- 路由策略测试：成员 token 可以读自己的日志，读不到别人的；fixture 模式的路由白名单同步。

**7. 客户端时间与“位置”**

- 两个请求模型各加可选 `clientTime`（ISO 8601），只存不信，排序按服务器顺序；iOS 在 B3 开始发送。
- “位置”指洞号 + 稳定 shot id + 改前 / 改后显示序号，不记录人的 GPS。

**测试矩阵**

- 组合快照（同一次提交里加、删、挪、换杆、改球位、调序、改罚杆）；
- 每个旧逐杆 op 各一条，包括 `restoreShot`、`setHolePenalty`；
- 相同 / 不同 `clientMutationId` 重放（同体不重复、异体 `409`，两个存储都测）；
- 两个并发写同一局（`seq`、`auditSeq` 不重复，第二条的前值是第一条的后值）；
- 同一洞的 `replaceHoleShots.manualPenalty` 和 `penalty_correction` 并发（按 `auditSeq` 串行，后者的前值包含前者）；
- annotation 的前值包含更正存储的状态（先加一杆，再改总杆，前值是加杆后的洞分）；
- 调序换了第 1 杆不产生 `move`；
- 写入和修复之间发生 Garmin 重新同步 → 修复记 `unrecoverable`，不推导新前值；指纹未变 → 修复成功；
- 直接调用存储函数（不经路由）同样拿审计锁，没有其他代码直接写这两类文件；
- 修复记录不会被 `apply_corrections`、`list_annotations` 读到；
- 末行缺换行：合法 JSON 保留并补换行，残缺 JSON 截掉；
- 旧文件名 + 新文件名合并：合成 id 稳定、回放顺序确定、`seq` 接续；
- 游标跨页不重不漏，修复条目出现在后面的页里；
- 做差失败 → `auditPending`，然后修复；
- 残缺尾行的截断和跳过；
- 修订号不同 → 不产生 `move`，审计记 `positionComparison: unavailable`；地图刷新前后提交只改球杆的 `replaceHoleShots` → 只有 `club`；
- 挪一个落点只记一条 `move`（相邻杆的派生起点不记）；
- annotation 的 `putts / total / penalty`（含已有更正、并发）；
- 文件名不撞、旧文件名只读合并；
- 成员路由策略；
- 所有输出的 `eventId / logId / sourceRef` 唯一且能指回源记录。

### B0 契约细节（Python 与 Swift 各自实现时以此为准）

现有字段（`ai_caddie/courses/course_prep.py` 的 `HolePrep`）先写清楚，新字段照它们的坐标系：

- `route`：事实路线，发球台→果岭中心的折线，点为 `[x_m, y_m, 累计_m]`，本洞局部米制坐标（与 hazards 同一 frame）。
- `map.overlay.route`：同一条路线在显示坐标系里的像素点，`map.overlay.w / h` 为显示尺寸；只有路线、没有 topo 图时也会下发（“route-only bootstrap”）。
- `holeImageProjection`：`{available, widthPx, heightPx, refs:[{lat, lon, px, py} ×3]}`，三个不共线锚点，客户端拟合仿射把 GPS 放到图上。
- `greenOutline.pointsPx`：显示坐标系像素。
- **显示坐标系**：原点左上，x 向右，y 向下，单位是 topo 图的显示像素（渲染图 ÷ SS），与 `widthPx / heightPx` 相同。

新增 `fairwayOutline`（HolePrep 与手表下载包同名同结构，附加字段，不改旧字段）：

```json
"fairwayOutline": {
  "version": 1,
  "source": "courseData.Fairway",
  "polygons": [
    {"outerPx": [[x, y], ...], "holesPx": [[[x, y], ...]],
     "outerLatLon": [[lat, lon], ...], "holesLatLon": [[[lat, lon], ...]]}
  ]
}
```

- 缺失语义：没有球道几何，或本洞没有 RefLat/RefLon 锚点（无法换算经纬度）= `null`；旧包没有这个键 = 解码为 `null`；`version` 不认识 = 当作 `null`（不报错）。`null` 只影响开球预选和球道统计，不影响地图。
- 环：不闭合（首点不重复），每环 ≥ 3 点；生产端按 RFC 7946 规范化（`outerLatLon` 逆时针、`holesLatLon` 顺时针，以 lon 为横轴）；消费端**不得依赖绕行方向**。
- 多段球道 = 多个 `polygons`；球道里的沙坑等挖空 = 该 polygon 的 `holes*`。点在球道内 = 落在某个 outer 内且不在它的任何 hole 内。
- 经纬度数组顺序固定为 `[lat, lon]`（字段名里写明 LatLon），WGS84 度，7 位小数；像素 1 位小数。`outerPx` 与 `outerLatLon` 一一对应。

开球判定（唯一算法，共享向量 `tests/fixtures/tee_result_vectors.json`，Python 单测和 Swift 单测都读它）：

1. 输入：第二杆位置（没有第二杆用首推位置）的经纬度、`fairwayOutline`、`route`、本洞 Par。Par 3、`fairwayOutline = null`、没有位置 → `null`。
2. 以球道 `outerLatLon` 全部点的平均经纬度为原点，等距矩形投影到米（x 东、y 北，地球半径 6378137 m，与 `shot_projection` 相同）。
3. 在任一球道 polygon 内，或到最近球道边界 ≤ 0.5 m → `hit`。
4. 否则取 `route` 上离该点最近的一段（先把 `route` 用 `holeImageProjection` 或 hazards 的 refLat/refLon 转到同一米制坐标；两者都没有、或路线少于 2 点 → `null`；路线只用来分左右，第 3 步的 `hit` 不依赖路线），
   按“沿路线前进方向”的叉积符号：左侧 `left`，右侧 `right`。
实现：Python `ai_caddie/courses/tee_result.py`（服务端 / 统计）；取轮廓 `course_prep._fairway_outline`（本洞路线 15 m 内的 `Fairway.drc` 连通块）。
5. 向量至少覆盖：球道中、左、右、贴边 0.4 m / 0.6 m、多段之间、在挖空里、Par 3、无轮廓、无路线。

地图显示（B1 / B4 / B6 都按这张表，和 README 的地图降级契约一致）：

| topo 图 | 可画路线（`map.overlay.route`，或 `route` + `holeImageProjection`） | `fairwayOutline` | 显示 |
|---|---|---|---|
| 有 | 有 | 任意 | 正常：topo + 路线 + 落点 |
| 没有 | 有 | 任意 | 立即画事实路线 + `greenOutline` + 已有障碍（深色底）；topo 到了原地替换，不重置缩放 / 平移 / 障碍选择 / 目标点 / 旗位 |
| 没有 | 没有 | 任意 | 统一整屏等待页（洞号 · Par · 码数），不进空白洞 |
| 任意 | 任意 | `null` | 地图不变；开球不预选；球道统计只用用户填的 |

## B1 手机打球主屏 + 旗位（可与 B0 并行）

- 文件：`CurrentHoleView.swift`、`HoleImageMapView.swift`、`LiveGreenDetailView.swift`、`LiveHoleComponents.swift`。
- 内容：全屏 topo、两侧按钮布局；障碍按 README 第 1 节唯一规范：主图默认不选中，只有“障碍”选择器画一个，细红线真实轮廓 + 小红点，无白圈粗框；果岭只一面旗、点果岭进旗位；
  目标点放大镜（沿用现有 Touch Target 参数）。
- 旗位界面：去虚线；1–4 倍缩放；旗到前 / 后 / 左 / 右四边距离（图上细线 + 卡片四格，用 `greenOutline` 算射线交点）；
  拖旗不弹放大镜、旗子与手指保持相对位置；拖出果岭贴边。
- 验收：`-uitest-screen` 新增截图用例（开球、目标拖动、旗位缩放、主图无障碍默认态、选中一个障碍）；四边距离单测（多边形射线交点）；
  地图降级契约（README 第 8 节）的 UI 测试：topo 未就绪先出事实路线；后台补图不重置缩放 / 障碍选择 / 目标点。

## B2 手机记分三屏（依赖 B0 的开球判定、成绩来源）

- 文件：`LiveScoreConfirmationView.swift`、`LiveRoundScorecardView.swift`、`LiveRoundFinishSummaryView.swift`、`Models/LiveScoreConfirmation.swift`。
- 本洞记分改为一屏：总杆记分符号条（从 1 杆排起、不自动居中）、推杆分段、开球三块小图、罚杆 −/+；不写任何来源提示。
- 预选优先级：手表挥杆 → 手机“记一杆”次数 + 2 推 → 默认标准杆；开球用 B0 判定预选。保存时写 `source`。
  - “记一杆”次数 = 本洞所有手动标的落点（`.location` 事件），手机标的和手表上标的（经手机转存，clientId `apple-watch`）同样计入，来源记 `phone_shots`；
    开球预选用第二个标点，不分设备。`watch_detected` 只留给 B7 的手表自动挥杆检测，不从手动标点推断。
  - 总杆不变量：总杆 ≥ 推杆 + 罚杆 + 1（模型保证，不靠界面）。加推杆 / 罚杆时总杆跟着加；选更小的总杆时先减推杆、再减罚杆；减推杆 / 罚杆不会减总杆。
  - 推杆分段 `0 / 1 / 2 / 3 / 4+`；选中 `4+` 时旁边出现 −/+ 记实际推数（4–9），上报和统计用实际值。
- 计分卡：大号成绩 + 累计走势 + 前 / 后九符号卡；“结束本场”入口移到这里。
- 本场汇总：复盘同版式（成绩、记分卡、四格含 GIR“按推杆推算”）；去掉同步状态；放弃前确认。
  - 副标题的 Par 按已记的洞求和（只打 9 洞显示前九 Par，如“Par 36 · 9/18 洞”）。
  - “点成绩看落点”放在 B3：落点图读服务器上的逐洞 shot map，本场保存上传后才有；B3 的单场复盘（同一版式）里点记分卡成绩打开该洞落点。保存前的汇总页记分卡只展示、不跳转。
- 验收：草稿模型单测（预选优先级、推杆超总杆时总杆自动加）；三屏 UI 截图。

## B3 复盘（依赖 B2 的汇总版式、B0 的纠错日志）

- 文件：`RoundReviewView.swift`、`RoundShotMapView.swift`、`RoundShotEditComponents.swift`、`Models/RoundEditModel.swift`。
- 单场复盘 = 汇总版式 + 累计走势 + 分享；缺数据不单独提示。
- 每洞落点：全屏 topo、编号点按球位着色、“一号木 221”标签、“推 ×2”；底部 18 洞符号条换洞；去掉缓存状态和简洁图切换。
- 同屏改杆：编号点拖动（放大镜）、点空白加杆（按距离预猜球杆）、底栏球杆横滑 / 球位 / 顺序 ‹ › / 删除；未选中时推杆、罚杆 −/+；
  去掉排序列表、图例、单独的精确定位全屏页。保存仍整洞提交，同时带上逐项改动（给 B0 纠错日志）。
- 顺带：`RecentRoundReviewView` 无入口，确认后删除或接回。
- 验收：编辑模型单测（插入位置、顺序调整、删除后编号）；纠错日志端到端测试。

## B4 开球前（可与 B0 并行）

- 文件：`RoundHomeView.swift`、`StartRoundView.swift`、`PrepCoursePickerView.swift`、`MobileCourseSearchView.swift`、`CourseReviewView.swift`。
- 首页主卡按情况切换：附近球场 + 上次组合与发球台 + “开始”；进行中 = “继续第 N 洞”；附近没有 = 搜索。上一场卡片加 18 洞符号条。
- 开始一场：合并附近 / 最近 / 已下载为一个列表；只选第一个 9 洞环（A / B / C），发球台颜色圆点；按钮写“从 B 场开始 · 蓝 T”。
  第二个环在打完第一个环时选（默认上次搭配，可同一环，可结束只打 9 洞），开打第二环前可改；不合成“9 洞组”，不固定“全场”。
  不显示定位 / 下载状态文字；未下载也可开打，按 README 第 8 节地图降级契约。
- 备战：全屏 topo + 球童路线；方案切换、球杆顺序、18 洞条；可换发球台；未就绪的洞按地图降级契约显示，不弹“地图尚未准备完成”。
- 分批：B4a 状态机 + 打完第一环的“接着打哪个 9 洞”；B4b 首页主卡 + 开始一场（只选第一环、发球台圆点）；B4c 备战与地图降级。
  - 状态机 `NineLoopPlan` 在共享框架 `AICaddieDomain`（手机、手表同一份）；手表设置页在 B6 改用它。
  - “上次搭配”：本机最近一次在这个第一环后选的第二环优先，其次历史里最近一场同一第一环的后九；都没有就按球场顺序的下一个环。
  - 打完第一环（单个 9 洞环的最后一洞保存后）弹出选择：选环 = 同一局加上后九并进入第 10 洞；只打 9 洞 = 进本场汇总；稍后 = 关掉，计分卡里的球洞调整仍可加打。
    后九一旦有任何记录（第 10 洞起的事件）就锁定，“改打别的 9 洞 / 移除加打”不再出现。
- B4b 实现说明（首页主卡 + 开始一场）：
  - 开始一场：附近（有定位时按距离，行内“1.2 公里”）→ 搜索选中 → 最近开始过的球场 → 本机已下载（全部已下载的球场，不只附近的），合成一个列表，按球场去重；每个来源自己的环不混合。去掉“附近球场 / 最近使用 / 本机已下载”分区和定位、发球台加载、离线说明等文字；附近失败只多一个重试图标。
  - 选中球场后只选第一个环：环名走 `NineLoop.displayName`（A → “A 场”，东 照用）+“9 洞”（发球台接口给的码数正好是这些洞的总码数时才显示）。开始时的“加打另一个 9 洞”卡删除，开始永远只准备一个环（`onPrepareCourseRound`），第二环由 B4a 的打完第一环提示决定。
  - 发球台：颜色圆点 + 台名 + 这个环的码数，横排可选；颜色表只有一份，放在共享框架 `AICaddieDomain.TeeColor`（手表设置页同用）。按钮文案来自 `NineLoopPlan.startTitle`：“从 B 场 开始 · 蓝 T”。
  - 首页主卡：进行中（球场、已知时大号累计成绩、“已打 N 洞”、“继续第 N 洞”）；在球场附近（和开始一场同一个附近来源 `model.nearbyCourses`，最近的球场在 3 公里内，`HubNearby.currentVenue`）= 该球场 + 这个球场上次的第一个环和发球台（本机成绩存档里最近一场在这个球场的，其次最近开始的球场正好在这里，都没有就是第一个环、球场默认发球台，`HubCourseSuggestion.forVenue`）+ “开始”一键开打 +“换球场或组合”；附近没有球场 =“今天去哪打？”+ 搜索，另有一块“再打上次那个”（一键开打上次的球场、第一个环和发球台）。首页只在已有定位权限时取位置，不弹权限。上一场卡在本机成绩存档最新一场就是这一场时显示 18 洞记分符号条，否则不显示。同步状态只在设置里。
- 分批补充：B4b 之后、B4c 之前是 **B4b-2**：只有两个环的单个 18 洞球场按同一规则走（先选前九或后九，到中途再定第二环，可选同一个环，开打第二环前可改）。
  它需要服务端 package 同时给出“物理洞身份”和“本局顺序洞号”，本地拼包、事件键和在线 revalidation 用同一映射；验收含 前→前、前→后、后→前、后→后 四种组合和锁定前 / 后测试。B4 在 B4b-2 合并前不算完成。
  契约：`B4b-2-CONTRACT.md`（round 洞号 `number` + 物理身份 + `roundLoops` / `loopKey`，删除 `nine` / `back_global_id`）。
  B4c：备战与地图降级。
- B4c 实现说明（备战 + 地图降级契约）：
  - 选了就进：备战搜索结果 / 最近选择（含下载中的行）点了立即进入“赛前球场攻略”；下载仍归 App 下载库，后台继续、重启后续传。选场页只列球场，不写下载 / 准备状态、不显示进度条；只有真正失败的行给“重试”，永远不支持备战的行写“暂不支持备战”。去掉进入前的“地图尚未准备完成”弹窗和 `validateReadyPrepCourse` 对未完成行写的提示文字。UI 测试读 DEBUG + `UITEST_MODE` 才有的安装状态标记，界面和读屏都没有下载文字。
  - 已完整下载的球场照旧与服务端核对地图版本，但改在进入后后台做：服务端确认某洞版本已变时，该行重新排队并带上 `requiredGeometryRevisions`，攻略页把这些洞的旧 topo 当作未就绪（显示事实路线），新图装好后原地替换；服务端不可达时照旧使用本机完整包。
  - 每洞状态只看本机已写入的模板：精确 facts + 本机 revision 对应的 topo = 精确图；有可画路线 = 事实路线 + 果岭轮廓；都没有 = 统一整屏等待页（`HoleMapWaitingPage`：第 N 洞 · Par · 码数，“图到了自动出来”，打球屏同用）。障碍按第 1 节默认不选中：备战地图不画障碍。
  - 洞条“变淡”= 精确图还没到的洞（事实路线和等待页都算），点进去仍按契约显示。
  - 地图全屏：适配视图先保证整条方案可见——发球台、每个落点连同它的“球杆 码数”标签、果岭都在洞号牌和底部面板之间，标签不压任何浮层（`PrepMapLayout.fittedRestFrame`，用渲染器自己的标签布局校验）；在此前提下底图尽量按比例铺满整屏。洞形状做不到铺满时（如方形底图上的斜向球洞），方案优先：地图只画一次，四周是底图自身边缘主色（中位数）的一片平静底色铺到屏幕边（不拉伸边缘像素，不出条纹或色块；旗、果岭、发球台、路线、障碍都只画一次），清晰底图边缘渐隐进这片底色，看不出矩形、接缝、边框或黑边；边缘透明的地形图不加底色；缩放 / 平移沿用打球屏的变换。缩放 / 平移、当前洞和方案由攻略页持有（`PrepHoleMapSession`），补图、下载进度、换发球台都不重置；只有换洞才回到适配视图。备战没有目标点、旗位和障碍选择；打球屏的这三项沿用 B1d 的 `LiveMapCarryOver`。
  - 方案：和打球屏同一个决策来源——本机球童种子 + 安装的 CoursePrep 链经 `OfflineCaddieDecisionEvaluator`，再由 `LiveCaddieRouteAuthority` 合并去重（开球、无 GPS 时打球屏的同一结果）。每个方案是一条完整、实际不同的路线（推荐 / 稳妥 / 进攻）；选中的方案决定地图路线、每个落点（用打球屏的 `LivePlannedRouteRenderer` 标“球杆 码数”）和底部完整球杆顺序。没有球童种子或球杆数据的包只显示安装的 CoursePrep 链。
  - CI 夹具 `DEGRADED_ID`（仅搜索可见，带完整球包以产生多个方案）：第 1 洞精确、第 2 洞先事实路线约 25 秒后补图、第 3–12 洞只有事实路线、第 13–18 洞没有可画路线；`PrepDegradationUITests` 只在夹具模式运行。
- 验收：9 洞环状态机单测（选第一环 → 中途选第二环 → 改选 → 只打 9 洞；含同一环两次）；手机与手表同一状态机；
  备战 / 打球在部分洞未就绪时的降级 UI 测试（事实路线、整屏等待页、补图不重置状态）。

## B5 成绩 / 统计 / 球包（依赖 B0 新统计字段）

- 文件：`ResultsView.swift`、`StatsView.swift`、`PerformancePhaseGraphics.swift`、`ClubGappingLadder.swift`、`ClubSettingsView.swift`、`ClubBag.swift`。
- 成绩首页：差点最大 + 近 20 场走势（每场点 + 近 10 场均线）+ 三数字 + 最近三场符号条 + 四个入口。
- 表现分析：“最该练”一句 + 四阶段同一写法（大数字、和之前比、分段条）；删除现有分段切换和四种阶段小图。
- 时间与频率：粒度切换图 + 季度 / 历年卡片 + 打球日历（现有“时间趋势”内容全部保留）。
- 成绩分布：每 5 杆柱状、全部洞成绩构成、按 Par。
- 球场：topo 打底、均杆 + 最佳、每场细线、最难三洞地图卡片、常打三种组合 + 全部组合。
- 球包：距离阶梯（p10–p90 条 + 中位线 + 相邻差距 < 8 / > 20 标黄）；点杆改距离或拿掉；合并“成绩 → 球杆”和“球杆设置”。
- 验收：各屏在缺字段时降级；数值与 B0 夹具一致。

### B5a 已定口径（PR #364）

- 移动端载荷预算：`/stats/mobile` 的 `scoring.roundSequences` 只保留最近 20 场（`MOBILE_ROUND_SEQUENCE_LIMIT`），完整序列仍在 `/api/v2/history/stats`。
- 表现分析“和之前比”：和前一个可比周期比，不和全部历史比。近 10 场对前 10 场（第 11–20 场），近 20 场对前 20 场（第 21–40 场），近一年对前一年；“全部”不比较。前一周期随同一个 `/stats/mobile` 响应的 `previous` 返回，不多一次请求；按场数的窗口要求前一周期场数凑满，不满时写“前 10 场只有 N 场，暂不比较”。三个前一周期窗口随缓存预热一起构建。
- 差点变化“近 20 场”：现在的估算减去最近 20 场实际球局之前的估算（`handicapChangeRecent20`）；不可定价的球局也算在这 20 场里，估算两侧各自忽略不可用记录。原来的 90 天 `handicapTrend` 保留，首页不再显示。

## B6 手表界面（依赖 B2 的记分模型）

- 文件：`WatchRoundContainerView.swift`、`WatchHoleMapView.swift`、`WatchHazardMapView.swift`、`WatchGreenPreviewView.swift`、
  `WatchScoreHoleView.swift`、`WatchClubPromptView.swift`、`WatchFinishRoundView.swift`、`Models/WatchRoundModel.swift`。
- 本洞改为上下三页（方案 / 障碍 / 果岭），表冠只缩放，放大后拖动平移；点球杆签换方案、点“1 / N”换障碍（放大后换障碍**保持当前缩放和平移**，不自动 fit，owner 要求，防 IMG-8050 回归；UI 测试断言 z / pan 不变）；
  障碍只在障碍页（显式选择器）画一个，方案页和果岭页默认不画，样式同 README 第 1 节唯一规范；
  点地图（放大时长按 0.5 秒）测距，未开球从发球台量。
- 本洞成绩一屏：总杆左右数字带（表冠 / 滑动）、推 / 罚原地循环滚轮、开球三格；不点确认则下一洞开球时自动保存。
- 去掉每杆“刚才用哪支杆？”（球杆改由 B7 按距离推断，推断前留空）。
- 洞结束触发：离开果岭 25 m 以上朝下一洞发球台走，或下一洞首杆。
- 验收：`WatchUITestRoot` 增加对应屏；洞结束触发的单测（GPS 轨迹夹具）。

## B7 手表自动记杆 v2（实验开关后面，依赖 B6 + B3 纠错）

原型里的 800 Hz / 200 Hz 采样、Series 8+、1.4 秒缓存、各门槛、8 m 合并距离都是**假设**，不是现有 `WatchAutoShotDetector`
已证明的能力；实现前先补下面的门槛和测试，不能把原型数字当成承诺。

- **能力 / 电量门槛**：运行时检测 `CMBatchedSensorManager` 与设备能力，不满足（机型、系统、权限、锻炼会话起不来）就整体关闭，
  回到手动记杆；记录一场的耗电，超过预算（先定为比现有锻炼会话多 ≤ 5% / 小时）自动关闭。
- **采样失败降级**：传感器报错或批次中断时停止检测、保留已记录的杆，不丢数据、不弹提示，本场剩余按手动记。
- **候选不改成绩**：第 1、2 步里候选只写特征，不进成绩；端到端测试证明开启采集后成绩、事件流与关闭时完全一致。
- **GPS / 洞结束门槛**（同样是假设，第 1 步数据定值）：
  - 位置精度：原型写的 ≤ 12 m 只是起点。第 1 步记录每次候选的水平精度分布，定出门槛后才用于判球位 / 合并。
  - 精度不够：取挥杆前 10 秒内最好的一个点；仍不够就标“位置未知”——照样计杆，但不判球位、不按距离合并（只按 60 秒时间合并）、不推断球杆。
  - 漂移：5 秒内跳 > 30 m 且步数没有对应移动的点丢弃。
  - 整洞没有 GPS：不自动分洞，回到现有的手动换洞；本洞挥杆照样计入当前洞。
  - 洞结束（离开果岭 25 m 且朝下一洞发球台走，或下一洞首杆）是**可撤销**的：误触发后 60 秒内在原果岭附近又测到挥杆，自动退回上一洞；
    用户也可以在成绩页把杆挪回上一洞，这类改动写进纠错日志当标签。
  - 能力门槛的评估报告里必须包含：GPS 精度分布、洞结束误触发率 / 漏触发率；达不到就只开采集、不开启用。

分三步，前一步有数据再做后一步：

1. **采集**：扩展 `WatchAutoShotDetector`（往回找挥动起点、累计转角、撞击时长、推杆 / 切杆分类、车速过滤），
   只记录候选及特征值，不改成绩；每场结束随纠错一起上传（开关控制，原始传感器数据不出表）。
2. **标注与调参**：用户实打若干场，在复盘逐杆核对（B3 的改动即标签）；离线评估各门槛的精确率 / 召回率，定起步门槛。
3. **启用**：候选按“同位置 60 秒只留最像击球的一次”合并，免确认直接进本场；推杆没测到按首推距离估；球杆按距离推断；
   个人门槛按纠错慢慢调（每场一小步、同类纠错 ≥ 5 条才动）。罚杆不猜。
- 验收：检测器单测（空挥、试挥打地、打完比划、坐车、推杆 / 试推夹具）；启用前的实打评估报告。

## 风险和待定

- 推杆能否稳定检测未知，按距离估是常规路径；B7 第 1 步的数据决定是否开放推杆检测。
- 撞击时长、车速、合并距离、采样率等都是假设，没有公开数据可依；以 B7 的能力门槛和第 2 步实测为准。
- 统计模型新增字段较多，B0 需要先确认现有历史数据能否回算（缺逐杆球位的旧球局，救球率只算有数据的场次）。
