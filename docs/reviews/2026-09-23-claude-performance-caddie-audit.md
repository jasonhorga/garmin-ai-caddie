# Garmin AI Caddie 代码审计（2026-09-23，基于 HEAD c2c5146）

范围：球场数据加载、历史比赛加载、球童方案合理性、整体架构。

> 本报告随分支 `claude/code-audit-performance-17wqcv` 提交。该分支已处理的条目：
> - §1.2 冷加载重复解析；§1.3 `/history/rounds` O(N²)；§1.4 按局取杆；§1.1 无新比赛的同步不再清空历史缓存；
> - §2.2 release 刷新失败退避；§2.1 `/prep-tips` 走 prep 缓存；
> - §3.7 GIR 截断误判；§3.9 attack 比 stock 短；§3.5 开球不再虚假声明"已考虑风和坡度"。
>
> 需要注意的一处更正：§2.1 提到的 `_point_in_mesh` 在生产代码里其实没有调用方，prep 的真实热点还需要用真实 mesh 数据 profile。
> 其余条目都未处理，是后续工作。
方式：只读。在 `/dev/shm` 的 git archive 快照上审查，没有改仓库，没有安装依赖，没有起服务。
标记含义：
- **[已核实]** 我亲自对照源码确认过；
- **[实测]** 数字来自仓库文档里已有的测量；
- **[估]** 推断或估算，需要 profiling 确认。

---

## 0. 一句话结论

性能问题和球童方案的问题，根源是同一个架构选择：**所有派生数据都在读取时从上千个原始 JSON 文件现算，而不是在写入（同步、安装、结束一局）时物化好。** 于是：

- 历史接口靠文件指纹缓存兜底。任何写入都会让缓存整体失效，冷重建一次约 11s。
- 球场 prep 在请求时做纯 Python 的几何计算，冷批次要 36s。
- 球童有 5 套以上规划器互相覆盖，每修一个 bug 就多一条特例。

快的办法是先修下面的热点。治本的办法是把"读时计算"改成"写时物化"，再把球童改成单一目标函数（期望杆数）。

---

## 1. 历史比赛加载

### 现状 [实测，约 435 局]
| 步骤 | 冷 | 热 |
|---|---|---|
| history load | 4.57s | — |
| stats build | 6.7–7.0s | 0.165s |
| `/history/stats` 响应体 | 11–20MB | — |

### 主要瓶颈（按影响排序）

1. **缓存失效太频繁，而且冷重建约 11s 时一直占着 GIL。**
   - 缓存有效性靠扫描并 stat 6 个目录（`stats_cache.py:275`）。
   - 其中包括 `data/snapshots`，而加载器并不读这个目录。每次同步都会往里写一个新 manifest，所以即使同步了 0 局新比赛，缓存也会失效。
   - 以下写入都会让 stats 失效：天气、批注、报告、决策审计。
   - 全站只有一个 uvicorn 进程，重建期间其他请求都会变慢。

2. **冷加载重复解析文件。** [已核实]
   - `history.py:783`：`load_shot_history` 在每个洞的循环里都 `read_json` 一遍整张 scorecard。所需的 id 在 `round_row` 里本来就有。
   - `history.py:378-384`：`_scorecard_to_round` 为了判断 `hasShots` 先解析一遍 shot 文件，`load_shot_history` 又解析一遍。
   - 500 局时大约是 10k 次 JSON 解析，而实际只需要约 1k 次。

3. **`/history/rounds` 的复杂度是 O(N²)。** [已核实]
   - 每张卡片都调用 `history_course_venue_name`（`history_overview.py:199`）。
   - 它内部的 `_related_course_name_rows`（`history.py:129`）会扫描全部 raw_rounds + rounds。
   - 合成基准测试中，480 局仅扫描一项就要约 1s。常去的主场越多，情况越糟。
   - iOS 每次进入"成绩"页都会请求 `limit=2000`。

4. **打开一局会触发 18 次 shotmap 请求，每次都复制全部约 45k 杆。**
   - 位置：`history_round_detail.py:151`、`round_shot_map.py:99`（`remap_shots_to_merged_rounds`）。
   - mesh 被解析两次，而且没有缓存。

5. **大响应体每次都重新校验、序列化、用 gzip 9 压缩，没有 ETag。**
   - `/history/summary` 只需要其中几个数字，却为此构造了完整的 20MB pydantic 模型。

6. **Web 端的问题**
   - "分页"其实是先取 120 条，再重拉 2000 条。
   - shotmap 请求没有带 `includeImage=false`，PNG 被下载了两遍，还把 1.5MB 的 localStorage 缓存挤爆。

### 建议
- **小时级改动**
  - 修第 2 条的重复解析。
  - 在 `HistoryData` 上预建两个索引：venue 映射、按局的杆索引。这样第 3、4 条会从 O(N²)/O(全量) 降到 O(N)/O(本局)。
  - summary 改为直接从原始 dict 切片。
  - 所有历史 GET 加弱 ETag，并返回 304。
  - 从指纹里去掉 `snapshots`。
  - 同步 0 局新数据时不清缓存。
  - gzip 压缩级别调到 5–6。
- **天级改动**
  - HistoryData 持久化到磁盘，避免重启后重新冷加载。
  - 按文件的 (mtime, size) 做增量解析。
  - stats 重建放到 ProcessPool 里执行，重建期间先返回旧数据。
- **治本**
  - 同步或录入时，把每局写成一条规范化记录存进 SQLite。
  - 聚合指标增量更新。
  - 用一个单调递增的 `data_version` 替代目录指纹，它同时充当 ETag 和缓存键。
  - 客户端通过 `?since=version` 做增量同步。

---

## 2. 球场数据加载

### 现状 [实测，PERF-STARTUP 课程 31921]
| 操作 | 耗时 |
|---|---|
| package，重启后首次 | 7.4s |
| package，warm | 2.4s |
| prep 冷批次 | 36.5s |
| prep 热批次 | 148ms |
| 新球场安装 job | 7m45s |
| Watch：18 个 topo | 24.8s |
| Watch：18 个 green | 54.9s |

- package JSON 约 650KB，gzip 后约 107KB。
- 单张 green.png 838KB。

### 主要瓶颈

1. **prep 的几何计算是纯 Python 暴力遍历，缓存粒度也不对。** [已核实]
   - `course_prep.py:134-149`：`_point_in_mesh` 对每个点遍历全部三角形。
   - 缓存键是 `(gid, 洞号组合 tuple, …)`（`prep_cache.py:232`）。Web、iPhone、Watch、单洞视图请求的洞号组合各不相同，所以同一组数据被重复计算。
   - owner 的指纹里包含 `_dir_sig(SHOT_DIR)` 和 `_dir_sig(SCORECARD_DIR)`（`prep_cache.py:190`）。结果是每次同步都会让所有球场的几何 prep 失效，尽管几何本身和球员无关。
   - Web 每 5s 轮询一次全部 18 洞；安装过程中每落地一个洞，都会触发整场重建。
   - `/prep-tips` 完全没有缓存，每次都跑一遍全洞 prep。
2. **Garmin release 刷新挡在请求路径上。** [已核实]
   - topo.png 和 green.png 都用 `refresh_release=True`，而且发生在 ETag/304 判断之前（`main.py:848`）。
   - release 文件超过 1 小时，就会在持锁状态下同步拉取 Garmin，超时 30s。
   - 拉取失败没有退避，每个请求都会重试一次，而且串行排队。[估] 这很可能是 Watch 上 5–15s 长尾的来源。
3. **package 每次都从头重建。**
   - singleflight 的键带分钟时间桶，没有持久缓存。
   - `_rebind` 对 650KB 的结构做 deepcopy。
   - 每洞全量读取 annotations/weather JSONL，18 洞合计约 36 次以上。这两个文件只追加，读取量会随历史线性增长。
   - 18 个 seed 各带一份完整的 clubProfiles、playerProfile 和天气。
4. **天气抓取会让 stats 自己失效，形成一个环。**
   - package 路径同步请求 Open-Meteo，结果写进 weather jsonl。
   - 这改变了 stats 的指纹，下一次 stats 请求就要冷重建（约 6–7s）。
5. **Watch 端**
   - green 请求 1280px，而且安装时从不预渲染。
   - topo 下载全尺寸，与手机 `pushHoleImage` 推送的图片重复。
   - `WatchCourseLibrary` 每次进度回调都重写全部图片和全部模板，写入量是 O(n²)，[估] 约 40MB 闪存写入。
6. **安装流水线**
   - 每洞依次跑 2 个 node 进程和 2–3 个 `python -m` 进程，一个球场约 90 次进程启动。
   - mesh 用 JSON 存储，每个消费者各解析一遍。
   - 全局只有 1 个 install worker，两个用户同时安装新球场时要排队。
7. **iOS**
   - [估，置信度中] `prefetchFirstHoleTopo` 要求 `geometryCoverage=="ready"`，但 lightweight prep 始终是 `partial`，所以首洞 topo 预取可能从不触发。
   - `loadCourseTemplates()` 在 MainActor 上同步解码全部模板。

### 建议
- **小时到一两天**
  - release 改为后台 stale-while-revalidate，失败加负缓存和退避，先判断 ETag。
  - prep 按单洞缓存，指纹拆成几何部分和球员部分；prep-tips 共用这份缓存。
  - Web 只拉新就绪的洞。
  - Watch 的 green 降到 640–800px，topo 提供小尺寸变体，持久化改为增量写入。
  - package 路径不同步抓天气，并在单次构建内 memo coverage。
  - gzip 排除 `image/*`。
- **数天**
  - 把 prep 拆成两层：
    - 与球员无关的几何事实（route、hazards、F/M/B、playsLike、outline）在安装 job 里按 `geometryRevision` 算好并存盘；
    - 与球员相关的策略在请求时计算，毫秒级。
  - 这一项基本就能消掉 36s 的冷批次。
  - 几何计算用 numpy/shapely 向量化。
  - 安装流水线改为进程内调用；mesh 存成二进制数组。
  - CPU 密集任务放到独立进程池。
- **治本：不可变 CourseBundle**
  - 按 `(gid, release, geometrySha, rendererVersion)` 做内容寻址，一个 bundle 包含：
    - 每个 tee 的球场事实；
    - 多尺寸 topo 和 green；
    - 预压缩好的 JSON。
  - 设置 `immutable` 缓存头，放到 CDN 或 Cloudflare 缓存后面。
  - `/package` 缩成只有球员层，引用 bundle hash。
  - 手机把一个紧凑的 watch-bundle 一次性 `transferFile` 给手表，手表直连只作回退。
  - 仓库里 `unified-tri-surface-spec` 已经设计过 CoursePack，但还没有落地。

---

## 3. 球童方案合理性

### 优点
- 决策是确定性的、可复现的，LLM 只负责写解释。
- 用 p10/p90 而不是单一均值。
- 水障碍是硬约束，要求整个散布区间都避开，思路接近 DECADE。
- 样本少时向先验收缩。
- 果岭按前后窗口而不是单点处理。

### 问题

**数据与模型**
1. **所谓"carry"其实是各种 lie、全部历史混在一起的总距离。**
   - 位置：`data.py:670`、`history_stats.py:3229`。
   - 切杆和部分挥杆会把挖起杆的中位数拉低。
   - MAD 过滤的下限是 50m，基本不起作用。
   - 没有按时间加权，也没有区分 lie。
2. **横向散布在生产中不存在。** [已核实]
   - `lateralP10P90_m` 只有读取方和白名单，没有任何生产代码产出它。
   - 因此 OB 两侧的走廊检查永远返回 unknown。
3. **危险区是一维的**：只看沿路线的距离，不看左右和偏离中线多远，瞄点也不是决策变量。
   - 例：线路右侧 25m 的球道沙坑，和横穿球道的沙坑惩罚相同。
   - safe、stock、attack 三种模式只能靠换杆来区分。
4. **tee 和几何混用。** [已核实]
   - CoursePrep 写死蓝 tee 和狗腿路线（`course_prep.py:50`）。
   - 危险区用的是所选 tee 到目标的直线。
   - 在 tee 上优先用 prep 的长度。
   - 结果：打白 tee 或红 tee 的人会拿到蓝 tee 的距离，危险区 carry 可能差 20–40m。
5. **风、坡度、高差**
   - 风只作用于攻果岭和救球，不作用于开球；调整量是固定 m/s 系数，不随击球距离缩放。
   - 高差 playsLike 只显示给用户，不参与决策。
   - 开球时 UI 显示"已考虑风和坡度"，这是**虚假陈述**（`decision.py:2577`）。
6. **编造的兜底数据**：`8I 140m`、`DEFAULT_LADDER`、Watch 端的 `total*0.6`。这违反了项目自己"不编造事实"的契约。

**逻辑 bug**

7. **GIR 用的是被截断后的落点。** [已核实截断代码：`decision.py:2175`；子 agent 已用片段复现]
   - 一杆越过果岭后沿 25m 的球也会被判为 GIR。
   - Swift 端的 `trimAtGreenWindow` 有同样的问题。
8. **GIR 只看中位数，前沿容差为 0。**
   - 中位数刚好落在前沿时，约 50% 的概率会短。
   - 这与 PROJECT_STATE 里"按分布判断"的说法不一致。
9. **Attack 可能比 stock 用更短的杆。**（`_profile_tee_routes:3159`）
   - 实际输出：safe 3W / stock Driver / attack 3W。
10. **攻果岭的模式与其描述自相矛盾。**
    - "safe/果岭中心"实际是 pin−10m，忽略了果岭几何。前旗位加前水时，这会把目标推向水。
    - 救球是固定的 −46/−34/−22m。
11. **Par 5 够不到果岭的第二杆没有建议。**
    - 由 `MIN_SEQUENCE_DISTANCE_M=260` 与 carry 容差共同导致。
    - 整个系统没有"layup 到最喜欢的挖起杆距离"这个概念。
12. **短 Par 4 上，CoursePrep 会给出"Driver 打 55%"这类方案。**
13. **`scoreImpact.model="calibrated_history_club_v2"` 名不副实**：所有系数都是手调的，没有做过校准。

**架构层面**
14. GIR 窗口逻辑至少实现了 5 份，分布在 Python 和 Swift，用了 route 距离和直线距离两套坐标。在狗腿洞上，手机和服务端会给出不一致的结果。
15. 规划器至少 5 套：
    - CoursePrep 贪心；
    - live 枚举；
    - mobile_live 候选；
    - 2 个遗留生成器；
    - Swift `fallbackSteps`。

    最后往往是**最简单的那套胜出**：Swift 把已安装的 prep 路线放第一，并在整洞期间锁定。PROJECT_STATE 里反复出现的缺陷（3H→3H、stale seed、穿果岭、重复 tab）都是这种结构的症状，不是偶发 bug。`decision.py` 里约有 450 个浮点字面量，`20.0` 出现了 26 次。

### Out-of-the-box 重设计：单一期望杆数引擎
- **目标函数**：选择 (球杆, 瞄点)，使 E[打完该洞的杆数] 最小。罚杆按规则计入。
  - 各种路线、各模式、GIR 都是这一个计算的输出，而不是一条条规则。
- **数据**
  - 建一张击球表，用已有的 mesh 判定每杆的 lie。
  - 只用全挥杆，按 球杆 × lie 分组，拟合纵向和横向的分布以及偏差。
  - 近期数据加权（例如半衰期 90 天）；样本少时向相邻球杆和同差点人群收缩。
- **基线**：用 Broadie 式的"距离 × lie → 平均剩余杆数"表，再用用户自己的数据做个性化。副产品是一个 strokes-gained 功能。
- **求解**
  - 每洞、每个 tee 栅格化成约 2m 网格，做 value iteration。
  - 每个格点用约 256 个固定的准蒙特卡洛样本评估各球杆和瞄点。
  - layup、攻旗还是攻果岭中心、Par 5 策略都会自然从优化结果里出来。
- **三种模式由同一个分布导出**
  - stock = E 最小；
  - safe = E+0.05 范围内尾部风险（CVaR）最小；
  - attack = E+0.15 范围内 birdie 概率最大。
  - 按构造就保证有序，不会再出现"attack 更短"。
- **端侧**
  - 服务端把 value grid 和 policy 预计算进离线包，约 10–20KB/洞。
  - 手机和手表只保留一个约 300 行的确定性评估器，用共享的 golden 向量保证与 Python 一致。
  - 这一个评估器替代掉 Swift 里的全部规划器和 GIR 裁剪逻辑。
- **迁移路径**
  1. 击球表 + strokes-gained 报告（单独就有价值）。
  2. 按 tee 栅格化，同时立即修第 4 条的 tee 混用。
  3. 新引擎影子运行，与现有 `decision.py` 对比并记录分歧。
  4. 离线包加入 value grid，Swift 评估器通过一致性测试。
  5. 切换默认，删除旧规划器。
- **用用户自己的历史验证**
  - 预测的上果岭、罚杆、沙坑概率 vs 实际比例；
  - 预测的剩余杆数 vs 实际；
  - 每杆"比最优多花的杆数"；
  - 用最近若干局做 hold-out；
  - 把 A1 等已知截图固化成回归测试。
- **短期止血**（不必等重设计）：修 7、8、9、11；删掉虚假的"已考虑风和坡度"文案；修 tee 混用；把 GIR 窗口统一成一份 route 坐标实现。

---

## 4. 整体架构（accidental complexity）

1. **实际数据没有数据库。**
   - Postgres 只存 9 张身份表。
   - 服务端事件存储是手写的事务日志：commit marker、fcntl 锁，还有约 240 行逐字节解析 JSON 前缀来识别半截写入。测试 3.5k 行。
   - iOS 又实现了一遍（`OfflineStore.swift`，2.7k 行）。
   - 建议：一个 SQLite（WAL）做单一存储，事件用 `UNIQUE(round_id, client_id, event_id)` 保证幂等。
2. **Garmin 同步靠改写 fetch 模块的全局路径变量来切换球员**（`garmin_cn.py:~120`），所以需要全局文件锁和单 worker 队列。给 fetch 传一个 paths 参数就能去掉这个全局约束。
3. **两套身份系统 + 5 种以上认证方式。**
   - 鉴权靠中间件里的路径白名单（`main.py:350-434`），新路由默认是公开的；代码注释里记录过一次真实的漏网。
   - 建议改成 router 级依赖，默认拒绝。
   - 视频以 base64 塞进 JSON 上传，因此有 160MB 的请求上限；应改为 multipart。
4. **契约 codegen 管线什么有用的东西都没生成。**
   - 生成物只有 fixture 和一个空的 `EVENT_KINDS`。
   - 真正的 API 类型是手抄三份：pydantic 85 个、TS 151 个、Swift 约 227 个。
   - 建议：以 FastAPI 的 OpenAPI 为唯一源，生成 TS 和 Swift 类型；删除休眠的 canonical 契约栈，连同对设计文档 hash 的 authority 校验。
5. **测试断言的是源码文本而不是行为。**
   - 约 1.8k 条 `assertIn('title: "成绩"', swift_source)` 这样的断言。
   - `test_ci_workflow.py` 在断言 CI YAML 的内容。
   - 这类测试改名就挂，真出回归反而照样通过，还拖慢每一轮 agent 迭代。
6. **God 文件，全靠 `dict[str, Any]` 传递**（1,407 处 vs 26 个 dataclass）。
   - `decision.py` 6.1k 行、232 个函数，把持久化、LLM、规划、审计混在一起。
   - `mobile_live.py` 横跨 4 个领域。
   - `LiveRoundAppModel` 约 4.2k 行，`CurrentHoleView` 有 49 个 `@State`。
7. **流程负担。**
   - 自称"short"的 `PROJECT_STATE.md` 有 5,273 行。
   - `docs/superpowers/plans` 有 81k 行。
   - 每个 agent 会话都要背这些上下文，这本身就是一个性能问题。
8. **死代码和依赖**
   - 未使用的依赖：matplotlib、garminconnect、garth、keyring。
   - `tools/legacy` 只靠一个测试的 import 存活。
   - fly、render、vercel 部署配置可能都已不用 [待确认]。

---

## 5. 建议的执行顺序

1. **1–2 天，纯收益**：
   - 历史：去掉重复解析、修 O(N²)、预建索引、ETag；
   - release 刷新移出请求路径；
   - prep 按单洞缓存，指纹拆分；
   - Watch 图片尺寸降下来，持久化改增量；
   - 修 GIR 截断、attack<stock、虚假的"风/坡度"文案、tee 混用。
2. **1–2 周**：
   - prep 拆成几何层和策略层，几何层在安装时物化；
   - CPU 任务进独立进程池；
   - 所有 GET 带 ETag；
   - fetch 参数化，去掉全局锁；
   - 鉴权改为默认拒绝。
3. **数周，治本**：
   - SQLite 读模型 + `data_version`；
   - CourseBundle 内容寻址；
   - OpenAPI codegen，删掉源码文本测试；
   - 期望杆数引擎：影子运行后再切换。
4. **持续**：把 PROJECT_STATE 压到 150 行以内，归档历史计划。

## 6. 需要实测确认的点
- Garmin 抖动时，topo/green 的 Server-Timing 是否集中在 `release_lookup` 这一段。
- 修掉第 1.2 条的重复解析后，冷加载的实际降幅（需要真实文件大小）。
- member 的 package 是否每次都请求 Open-Meteo。
- starlette 的 GZip 是否会压缩 PNG。
- iOS `prefetchFirstHoleTopo` 是否真的从不触发。
- fly、render、vercel 是否还在用；"家庭多用户"是否仍是真实需求。如果不是，身份和同步部分能大幅简化。

## 7. 资源交接（AGENTS.md §6）
- 性质：只读。
- 快照：`/dev/shm/garmin-review-1790129474`（git archive HEAD c2c5146）。审计结束后已删除。
- 创建的资源：没有容器、端口、隧道或依赖环境。
- 产出：本报告。
