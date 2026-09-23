# 交接给 Codex：PR #332（性能与球童修正）

**来源**：Claude Code 云端会话。Owner 直接委派，要求实现并提 PR。
**分支**：`claude/code-audit-performance-17wqcv`，合并目标 `integration/v2`。
**PR**：https://github.com/jasonhorga/garmin-ai-caddie/pull/332
**审计报告**：`docs/reviews/2026-09-23-claude-performance-caddie-audit.md`

本文档只说明 Codex 接下来要做什么。执行状态仍以 `PROJECT_STATE.md` 为准。本 PR 没有改动 ledger，是否以及如何登记由 Codex 决定。

---

## 1. PR 内容（按 commit）

| Commit | 内容 | 生效位置 |
|---|---|---|
| `e02df645` | 历史加载：冷加载时成绩卡每局只解析一次；球场名解析从 O(N²) 改为按 `HistoryData` 建索引；round detail / shotmap 只处理本局的杆；同步没有新增比赛文件时不清空统计缓存；`data/snapshots` 只把 `*_hole.json` 计入指纹 | 后端 |
| `39d539dd` | Garmin release 刷新失败后 5 分钟内直接用缓存（原来每个 topo/green/prep 请求都串行重试一次 30s 超时）；`/prep-tips` 改走 prep 缓存 | 后端 |
| `66acb4f2` | 球童：GIR 不再使用被截断的落点；attack 必须比保留下来的 stock 更远；开球时不再声称"已考虑风和坡度" | 后端 |
| `84b4bccd` | iOS 离线评估器 `trimAtGreenWindow` 做同样的 GIR 修正，并加了 XCTest | iOS app |
| `1dee71dd` | `render=False` 的 prep 按单洞缓存，iPhone/Watch/Web 的 `/prep` 请求和 prep-tips 共用；prepare-recent 在启动、同步、录入后预热最近打过的球场的单洞 prep（后续 commit 改为默认 1 个，可配置） | 后端 |
| 后续 commit | 回应 PR 评审：缓存签名加入 `st_ctime_ns`；同一时间只允许一个预热线程，规模可配置，并记录耗时日志；release 刷新失败打告警日志；修复预热测试与残留后台线程之间的竞态 | 后端/测试 |
| `e0b097eb` | 审计报告（仅文档） | — |

每个行为修复都有回归测试，这些测试在旧代码上失败、在新代码上通过。12 个 caddie golden 回放全部通过。

## 2. 交接时的验证状态

- 本地（云端容器，Python 3.12，`uv sync --frozen`）：以 root 运行时，只有 `test_contract_authority` 里 2 个"文件不可读"类用例失败（root 不受 chmod 000 限制）。在同一容器里用非 root 用户 `nobody` 重跑，**全部通过**（2182 个 OK，跳过 13 个；复核方法见 PR 评论）。
- `test_server_v2_cache_warmup` 偶发失败的根因已经查明：前面测试启动的 `prepare-recent-*` 后台线程还在运行，它们构建的 stats 被 spy 计入。这个问题在 base 上就存在，本 PR 在 setUp 里先 join 这些线程来修复。修复后连续 3 次全量运行都通过。
- `check_authority.py`（`origin/integration/v2...HEAD`）和 `py_compile` 都通过。
- GitHub CI：`e0b097eb` 上的 backend、frontend、docker 三项全绿。**`1dee71dd` 上的 CI 和 Native Mobile CI 在交接时还在运行**，Swift 修改只在 Native CI 里编译验证过，Codex 合并前请确认两者都是绿色。
- 容器里无法运行 Web e2e 和真机测试；本 PR 也没有修改 Web 代码。

## 3. Codex 待办（按顺序）

1. **合并前**：确认 PR #332 在最新 head 上 CI 全绿，包括 Native Mobile CI。如果是红的，在 PR 分支上修复，或者退回给 Claude 会话。
2. **合并** PR 到 `integration/v2`（由 owner 决定，或按既有授权执行）。
3. **部署后端**。第 1、2、3、5 个 commit 都要在 homeserver 部署后才会生效：
   - 按既有流程从合并后的 SHA 构建 API 候选镜像，替换 API 容器，数据卷和端口保持不变；
   - `bash ops/build_sync_image.sh`，生成与新 API 同一 SHA 的 sync 镜像（cron 只接受这个 tag）；
   - 确认 `/api/v2/health` 返回的 revision 等于合并后的 SHA。
4. **部署后的验证**（同一台 homeserver，建议记录耗时）：
   - `/api/v2/history/rounds?limit=2000` 在冷缓存和热缓存下的耗时，与之前的基线对比；
   - 启动后等日志出现 `prep_warm gid=... duration_ms=...`，再对最近打过的球场请求 `/api/v2/courses/{gid}/prep?render=false&holes=1` 以及 3 洞一批的请求，应命中单洞缓存，日志中 `course_install stage=prep` 的耗时应明显下降。注意：移动端 course package 本身不跑全洞 prep（`server_v2/mobile.py` 里 `include_course_prep=False`，只做首洞轻量 prep），所以 package 的冷启动耗时**不在本 PR 的改善范围内**；
   - 预热规模由 `AI_CADDIE_PREP_WARM_COURSES` 控制（0 表示关闭，默认 1，最大 3）。建议先设为 0 采集基线，再设为 1 做对比；
   - 连续触发两次没有新比赛的 Garmin 同步，第二次之后 `/history/stats` 仍然命中缓存，不会重建约 10s；
   - A1 这类 Par 4 的路线：飞过果岭后沿的一杆不再显示为 GIR，attack 不会比 stock 更短。
5. **TestFlight**：只有 `84b4bccd` 影响 app。按现有 release rule 在 Native CI 通过后打 internal build（`external_distribution=false`），然后做 Apple 处理检查。真机验证仍由 owner 完成。
6. **ledger**：在 `PROJECT_STATE.md` 里登记这一 slice、证据和剩余阻塞（由 Codex 决定形式）。

## 4. 需要 Codex 在 homeserver 上确认的两个问题（Claude 看不到服务器）

- **cron 是否在正常运行**：app 首页"启动时拉最新记录"依赖两条路径，一是 `ops/auto_sync.sh` 每小时的 cron，二是 app 冷启动或回到前台时超过 15 分钟自动同步。代码路径已经在，如果 owner 看到首页不是最新，请检查 `~/garmin-auto-sync.log` 中的 cron 执行记录，以及 Garmin 自动登录（xvfb Playwright）是否失败。
- **同步是否会改写未变化的成绩卡文件**：如果增量同步会重写已有的成绩卡或击球文件（导致 mtime 变化），`e02df645` 中"同步没有新数据时保留缓存"的优化就不会生效，但也不会出错。可以对比同步前后 `data/scorecards` 的 mtime 确认。

## 5. 后续建议（未在本 PR 中实现，优先级从高到低）

1. **拆分 prep**：与球员无关的几何事实在安装球场时按 `geometryRevision` 预先算好并落盘，请求时只计算球员策略。这是 36s 冷批次的主要来源。拆之前先在 homeserver 用真实 mesh profile `prep_hole`；审计报告里关于 `_point_in_mesh` 的判断有误，它在生产代码里没有调用方。
2. **CPU 重活移出 API 进程**（stats 重建、prep、topo 渲染），避免单进程下被 GIL 拖慢首屏。
3. **CoursePrep 写死蓝 tee**（`course_prep._blue_tee`），与所选 tee 的几何混用，危险区 carry 可能差 20–40m。
4. **Par 5 够不到果岭的第二杆没有建议**（`MIN_SEQUENCE_DISTANCE_M` 与 carry 容差共同导致），也没有"layup 到擅长挖起杆距离"的逻辑。
5. **Watch**：green 图从 1280px 降到 640–800px；`WatchCourseLibrary` 改为增量持久化。
6. **清理部署配置**：`fly.toml`、`backend-fly-deploy.yml`、`render.yaml`、`web_v2/vercel.json` 目前没有使用，Fly workflow 可能把 app 指向一个空后端。readiness 和相关测试引用了这些文件，建议单独开 PR 清理。
7. **长期方向**：见审计报告 §3（期望杆数引擎）和 §4（SQLite/Postgres 读模型、默认拒绝的鉴权、多用户统一处理）。

## 6. AGENTS.md §6 交接信息

- **类型**：修改型，owner 直接委派实现并提 PR。
- **工作位置**：Claude Code 云端临时容器中的仓库 checkout（非 homeserver）。只读审计阶段的快照 `/dev/shm/garmin-review-*` 已经删除。
- **创建的资源**：
  - 容器内的 `.venv`（`uv sync --frozen`），随容器回收；
  - 把浅克隆 unshallow 了，否则 authority 检查找不到 pin；
  - GitHub 分支 `claude/code-audit-performance-17wqcv` 和 PR #332。
  - 没有创建任何容器、端口、隧道或卷，也没有登录 homeserver。
- **到期与清理**：云端容器闲置后自动回收，分支在合并后可以删除。
- **交付物**：PR #332，含上面列出的 6 个 commit，以及本文档。
