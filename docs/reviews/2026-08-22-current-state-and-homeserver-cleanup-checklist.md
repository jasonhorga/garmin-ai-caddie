# 2026-08-22 当前状态扫描与 Homeserver 清理清单

> 本报告从只读扫描开始，随后按 Owner 授权执行了限定清理。生成时间：2026-08-22 17:07–17:17 UTC。
> 没有删除源码 worktree、容器、镜像或 volume，也没有运行构建/测试。

## 1. 结论

本报告记录的是当时的容量快照和已执行的最小清理，不代表 79 份源码快照
需要永久保留。后续保留/删除口径见
[资源保留与清理决定](../ops/2026-08-22-resource-retention-decision.md)
以及 [Homeserver Resource Policy](../ops/HOMESERVER_RESOURCE_POLICY.md)。
源码快照必须先做唯一 delta 清点；测试容器、镜像、volume 和证据必须
分开处理。

Homeserver 的根分区仍然是 98 GiB、可用空间为 0、使用率 100%。inode 只使用约 26%，所以问题是容量而不是文件数量。

最大的可回收项仍然是：

- 79 个 Claude worktree 目录中的 50 个重复 `.venv`；
- Docker BuildKit 缓存；
- 已停止的审查/候选 API 容器及其仅被这些容器引用的镜像；
- 一批无引用的匿名 Docker volume。

源码 worktree、生产数据、当前运行的服务和持久 volume 不能按“看起来旧”直接删除。

## 2. 资源快照

| 项目 | 当前事实 | 处理结论 |
|---|---|---|
| 根盘 | 98 GiB，总已用约 94 GiB，可用 0 | 必须先释放空间，才能做远端构建/截图/测试 |
| inode | 6.3M 中约 26% 已用 | 不需要做小文件清扫 |
| 内存 | 7.8 GiB；可用约 4.4 GiB | 当前不是主要阻塞，但不能并发重型任务 |
| Docker 镜像 | 59 个；约 20.87 GiB；可回收约 4.703 GiB | 逐项核对后再删 |
| Docker 容器 | 48 个，10 个运行中、38 个已停止；可回收约 266 MiB | 停止容器先做回滚核对 |
| Docker volume | 87 个；约 15.96 GiB；Docker 标记可回收约 5.408 GiB | 任何 named volume 都先保留 |
| BuildKit | 约 11.16 GiB；可回收约 8.351 GiB | 第一候选，仍需一次明确授权 |
| Claude worktree | 79 个；50 个 `.venv` | 源码全部先保留，只考虑旧依赖副本 |

## 3. 必须保留的资源

### 3.1 运行服务

以下 10 个容器当前在运行，不能用 prune 或批量 stop 处理：

- `aicaddie-web`
- `aicaddie-release-6a6080c-candidate`（当前同步/候选 API 线）
- `aicaddie-release-28a9d18-candidate`
- `aicaddie-release-cceeed8-candidate`
- `aicaddie-release-854cbd3-candidate`
- `aicaddie-candidate-91b6e2c-api`
- `aicaddie-e1f8dc9-resource-v4`
- `garmin-ai-caddie-api-1`（`5130f65`，healthy，生产端口 9000）
- `aicaddie-review-real-f463725-api`
- `garmin-ai-caddie-db-1`（Postgres，healthy）

此外，`aicaddie-sync:latest` 是当前 cron 使用的同步镜像，必须保留。最新日志显示同步已成功运行：485 个 scorecard、485 个 shot 文件、110 个 course reference，缺失数为 0；最后两次成功时间约为 15:39 和 16:37 UTC。Half Moon Bay 的两场（`17603881` Ocean、`17601656` Old）已按 round ID 核对，scorecard 与 shot 文件均完整；同步主链路当前没有确认到问题。

### 3.2 持久数据

以下 volume 是硬保护项：

- `garmin-ai-caddie_ai-caddie-private`（约 10.5 GiB，多个运行 API 共用）
- `garmin-ai-caddie_ai-caddie-pgdata`（约 48 MiB，Postgres）

三个 named dangling volume 也暂时全部保留，尤其是可能包含预检数据的：

- `aicaddie-pw-profile`
- `garmin-topov4-preflight-d92272a-20260731_ai-caddie-pgdata`
- `garmin-topov4-preflight-d92272a-20260731_ai-caddie-private`

### 3.3 交互/审查会话

当前发现两个 tmux 会话，均不自动停止：

- `aicaddie-review-f463725-tunnel`：旧的 review tunnel，仍有 cloudflared 子进程
- `sat-coach-review-settings-20260822`：当前 settings review 服务

本次扫描没有发现 Claude/Codex/Fable/Opus 进程的工作目录指向 Garmin worktree；这只能说明“当前没有被进程打开”，不能替代源码保全审计。

## 4. Worktree 清单与建议

### 4.1 事实

- 目标目录：`/home/jason/codex-runs/garmin-ai-caddie-p0-watch-20260822/.claude/worktrees`
- 目录数：79
- 含 `.venv` 的目录数：50
- 今天（2026-08-22）新建的两个目录：`web-redesign-polish`、`web-mobile-fixes`；当前为空，仍先保留，避免误删当前会话产物。
- 50 个 `.venv` 的父目录时间范围：2026-06-14 至 2026-07-09；没有一个 `.venv` 是今天创建的。
- 这些目录里的 `.git` 文件指向编辑机 `/home/ubuntu/claude-web-data/repo/garmin-ai-caddie/.git/worktrees/...`，在 homeserver 上无法直接作为有效 Git worktree 使用。它们更像 Claude 运行留下的源码快照，不能用 Git 分支状态判断“是否已合并”。

### 4.2 现在不能做的事

- 不能删除整个 `.claude/worktrees` 目录。
- 不能按目录名包含 `superpowers`、`agent-`、`review` 就删除。
- 不能把“没有活动进程”当成“内容不需要”。
- 不能使用 `git clean`、`rm -rf`、`docker system prune` 这类无白名单命令。

### 4.3 待授权的最小候选

最小风险顺序如下：

1. **旧依赖副本**：只删除 2026-08-22 之前的 50 个 `.venv` 目录，保留 79 个源码父目录；删除前先生成文件数/manifest，并确认本轮不需要在这些目录中运行 Claude。
2. **两个空目录**：`web-redesign-polish`、`web-mobile-fixes` 只有在确认没有其他 session 持有它们后才删除。
3. **停止容器**：先保留最近候选与有回滚价值的镜像；逐个记录容器名、镜像 tag、创建时间和是否有 volume，再删明确废弃的停止容器。
4. **镜像**：停止容器清理后重新计算“无任何容器引用”的镜像；只删除明确标记为旧 review/旧 candidate 的镜像，不删除 `latest`、生产 tag、数据库、当前 candidate。
5. **BuildKit 缓存**：可回收约 8.351 GiB；在开始远端构建前清一次即可，不触碰 image/container/volume。
6. **匿名 volume**：82 个匿名 dangling volume 需要按创建时间和挂载来源复核后再清；不能用 `docker volume prune` 代替核对。

## 5. 当前仓库与产品任务状态

本地编辑仓库：`codex/results-merged-20260812`，HEAD `7dec4b0a`。工作树有 275 个已修改路径和 93 个未跟踪路径；tracked diff 约 54.5k 行新增、5.6k 行删除。这里混合了产品实现、测试、合同、审查资料和历史计划，不能用“dirty”直接判断某个功能完成或失败。

按当前有效的精简任务索引，仍需闭环的主线是：

- **T00–T05：Topo/地图质量与 Watch 展示**：有修复和批准图，但要在当前 HEAD、更多真实球洞上重新验收外轮廓和设备边界。
- **T10–T14：陌生球场发现**：名称/城市搜索可复用；Garmin GPS nearby 的真实上游来源尚未被证明。
- **T20–T25：三端统一球场包与 readiness**：已有 package、OfflineStore、逐洞 topo 下载能力；备战页仍没有完整持久下载任务状态。
- **T30–T35：S70 全旅程**：需要按一场球逐状态复核地图、球童、障碍、旗位、计分和结束/恢复，不以单张截图宣称完成。
- **T40–T47：Deep Mine**：已发现 DSKIMG auxiliary 二维流等高价值线索；通用 103 项 Research Lab 没有整体实施，研究应保持非阻塞、证据驱动。
- **T50–T53：发布门**：远端资源恢复后跑 GitHub Actions/模拟器和真实数据矩阵；用户批准前不发 TestFlight。

当前同步日志是健康的，Half Moon Bay 两场已经落盘；剩余的是“历史页/round detail/shotmap/iOS Results 是否能完整展示”这一独立端到端验收。2026-08-22 增加的 freshness 观测用于后续诊断，不代表已修复一个已确认的同步故障。详见 [Garmin sync freshness vertical slice](2026-08-22-garmin-sync-freshness-vertical-slice.md)。当前没有可用 Xcode，因此本轮不能声明 native build、模拟器截图或 TestFlight 已验证。

## 6. 已执行结果

- [x] 按持久 manifest 白名单删除 50 个旧 `.venv`，没有删除任何源码父目录。
- [x] manifest 已保存到 `/home/jason/garmin-ai-caddie-data/cleanup-manifests/2026-08-22-venv-cleanup.meta` 和同名 `.paths`。
- [x] `docker builder prune --force` 只清理 BuildKit 缓存；Docker 报告回收 `8.351GB`，没有使用 `docker system prune`。
- [x] 删除后复核：根盘从 `100% / 0 bytes free` 恢复到 `72% / 约 27 GiB free`；Build Cache 可回收项为 `0B`。
- [x] 复核 10 个运行容器、两个生产 volume、`aicaddie-sync:latest`、两个 tmux 会话均仍在。
- [x] 复核旧 `.venv` 剩余数为 `0`。

Docker 的逻辑可回收总量和实际释放空间不完全相等，因为镜像层、BuildKit 层和文件系统 block 可能共享；以后以 `df -h` 的实际结果为准。

## 7. 为什么会产生这么多占用

这不是单个程序泄漏，而是几种工作方式叠加：

1. **每个 Claude 会话复制一份源码和环境。** 79 个 worktree 是连续多轮 review/实现留下的快照；其中 50 个各自执行依赖安装，形成约 21.5 GiB 重复 `.venv`。
2. **每个候选 SHA 都构建独立 Docker tag。** API 镜像约 1.7–1.8 GiB、sync 镜像约 3.5 GiB；虽然层有共享，但不同构建仍会留下大量独有层。停止容器还会继续引用旧镜像，使普通 prune 无法回收。
3. **BuildKit 默认长期保留缓存。** 反复构建、切换分支和运行审查会把中间层积到约 11 GiB。
4. **临时 compose/review 会话创建 volume。** 87 个 volume 中绝大多数是匿名 volume；会话结束后容器消失，volume 不会自动删除。
5. **并行审查留下运行态资产。** 多个候选 API、tunnel、截图和预览服务同时存在，单项不一定大，但会延长容器、镜像和 volume 的生命周期。

## 8. 以后如何避免复发

### 8.1 Worktree 与 Python 依赖

- 每个会话可以有源码目录，但不要在每个目录里永久保留 `.venv`；使用一个共享的 `/home/jason/venvs/garmin-ai-caddie`，或统一在 Docker 中运行。
- 把 `UV_CACHE_DIR` 指向一个共享缓存目录；缓存只保留一份，worktree 删除时不复制缓存。
- 所有同步/复制命令固定排除 `.venv/`、`node_modules/`、`dist/`、`.build/`、`.codex-tmp/` 和凭据文件。
- worktree 建立时登记 `owner/session/createdAt/expiryAt`；会话结束即归档源码，7 天后只删除依赖目录，不删除源码快照。
- 每次启动重型任务前检查 `df -Pk /`；可用空间低于 10 GiB 时只允许清理/诊断，不允许构建。

### 8.2 Docker

- 每个 review 项目使用明确的 session 前缀和 TTL label；结束时只清理自己创建的 stopped container 和 ephemeral volume。
- 保持一个生产镜像、一个当前候选镜像和一个可回滚镜像即可；不要让每个 SHA 的 API 容器长期运行。
- 每周只清理 BuildKit 缓存，例如 `docker builder prune --force --filter until=168h`；不使用全局 `docker system prune`。
- compose 临时环境结束时使用项目限定的 `docker compose down --remove-orphans`；`--volumes` 只对明确的临时项目使用。
- named volume 必须有 owner/用途登记；没有登记的 volume 先报告，不自动删除。

### 8.3 运行流程

- 重型构建、Playwright、截图和数据导入串行执行；禁止多个 agent 同时构建同一远端 Docker daemon。
- 每次任务结束输出三项：创建了什么、可删除什么、实际占用多少；把清理 manifest 放在 `/home/jason/<project>-data/cleanup-manifests`，不放在临时 worktree。
- 每天只保留一个 review tunnel 和一个当前预览服务；旧 tunnel 不因“看起来老”自动杀，需要先确认 URL/用途。
- 每周检查 `docker system df`、`df -h` 和 worktree 年龄；超过阈值先生成白名单，再由 Owner 授权。

## 9. 下一步清单（未执行）

- [x] Owner 已授权并完成“旧 `.venv` + BuildKit cache”清理；源码 worktree、运行容器、named volume 未动。
- [x] 重新检查磁盘，已释放约 26 GiB，恢复到约 27 GiB 可用。
- [ ] 对 38 个停止容器生成 rollback manifest；没有 manifest 不删。
- [ ] 重新计算无引用镜像与 dangling volume，逐项标记保留/候选。
- [x] 核对 Half Moon Bay 两场 Garmin round ID、时间、scorecard 和 shot 文件；两场均完整落盘。
- [ ] 通过 history/round detail/shotmap/iOS Results 对这两场做端到端展示验收。
- [ ] 在 homeserver 或 GitHub Actions 运行轻量后端/Web 回归；native/Playwright 等重任务串行执行。
- [ ] 回到 T00–T53 主线，优先陌生球场 vertical slice 和 S70 全旅程验收；不重启四份超长 Plan 的线性执行。
- [ ] 所有截图/测试通过且用户批准后，才创建发布候选并上传 TestFlight。

## 10. 当前仍需单独授权的范围

本次授权只覆盖旧 `.venv` 和 BuildKit cache，以下项目仍未授权：

- 38 个停止容器；
- 旧 candidate/review 镜像；
- 82 个匿名 dangling volume；
- 3 个 named dangling volume；
- 任意源码 worktree 或 tmux/tunnel。

这些项目要先生成逐项 rollback/数据清单，再单独确认。

## 11. 第二阶段复核（2026-08-22 20:42 UTC）

本节覆盖第 10 节之后实际执行的清理，不改写前面的历史快照：

- [x] 重新扫描 `/home/jason/codex-runs`：102 个顶层目录、约 9.1 GiB；仅
  `sat-coach-*` 进程仍在使用其目录。
- [x] 记录 Codex run 清单：
  `cleanup-manifests/2026-08-22T2032Z-codex-runs-audit`。
- [x] 按 allow-list 删除 14 个旧 `.venv`（`du` 合计约 6.6 GiB；共享层使
  根盘实际释放约 3 GiB）；保留 2 个当前目录入口，源码和证据目录未删除。
  清理后 `/home/jason/codex-runs` 约 6.3 GiB。
- [x] 对 79 个 Claude worktree 做内容级清点并生成恢复档；没有删除
  worktree（此前明确要求保留）。
- [x] 删除无 tag、无容器引用的 dangling image
  `sha256:a36250871de0833b8757561c72f2477ef1ddd1101afa4e617fb552e0de514c6b`
  （约 621 MB），metadata 与结果在
  `cleanup-manifests/2026-08-22T2032Z-docker-cache-cleanup`。
- [x] 用七天过滤器清理 BuildKit（约 285.5 MB）。
- [x] 清理可重建 pnpm/uv/npm 缓存；没有触碰 Playwright、用户 Trash、
  Garmin 数据或共享 journal。
- [x] 最终复核：根盘约 54 GiB 已用、39 GiB 可用（59%）；5 个容器运行中，
  9 个 tagged images，5 个 named volumes。

仍待单独决策：候选/review 镜像的生命周期、共享 system journal 的轮转上限、
以及是否在用户确认后分批删除已归档的 Claude worktree。上述事项不是本轮
P3 清理的必要条件。
