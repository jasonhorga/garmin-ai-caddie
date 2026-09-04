# 资源保留与清理决定（2026-08-22）

## 结论先说

你的方向对了一半：

- **不需要永久保留 79 份 Claude 源码目录。** 它们大多是审查/尝试留下的工作副本，应该改成短 TTL 的临时快照。
- **测试用的无状态 Docker 容器通常可以删。** 但不能把容器、镜像、volume、数据库和测试证据当成同一种东西一起删。
- **“GitHub 有最新源码”目前还不能作为删除依据。** 当前 canonical checkout 是 `codex/results-merged-20260812`、HEAD `7dec4b0a`，本地与 `origin` 的提交指针相同，但工作树仍有 275 个 tracked 修改、208 个 untracked 文件和 40 个 ignored 路径。此时删除旧快照可能丢掉尚未提交的唯一修复、fixture 或证据。

所以正确的目标不是“全留”或“全删”，而是：**唯一来源集中保存，临时工作自动过期，不能重建的数据永不随缓存清理。** 规则已写入 [HOMESERVER_RESOURCE_POLICY.md](HOMESERVER_RESOURCE_POLICY.md)。

## 对两个假设的反驳

### 1. “源码都在 GitHub，旧快照全部删掉”

只有在一次保全检查通过后才成立。GitHub 不包含未提交文件、未跟踪文件、ignored 文件、私有 Garmin 原始包、用户 round 数据、数据库、凭据、临时截图和某些只存在于快照里的生成物。即使文件名相同，也可能对应不同的本地修改。

旧快照的合理保留方式是：

1. 记录目录、大小、创建时间和可识别的 source SHA。
2. 与 canonical checkout 和已推送 tag 做差异清点。
3. 对唯一 delta 生成 patch 或合并到正式分支；对唯一 fixture/原始数据/审批图移到持久数据目录。
4. 只保留一个可恢复的已批准基线（Git tag/压缩归档即可），而不是保留完整 `.git`、`.venv` 和所有构建物。
5. 清点结果写入 manifest 后，才删除已经证明冗余的目录。

换句话说，**保留的是可追溯性，不是 79 份副本**。如果一个快照只是某个已打 tag 的干净 checkout，删除它是正确的；如果它含有未归档修改，删除就是数据丢失。

### 2. “测试 Docker 测完全部删掉”

无状态的 stopped test container 可以删，甚至应该按 session TTL 自动删。但以下对象不能按“测试”一概删除：

- **named volume** 可能挂着 PostgreSQL、Garmin raw 数据或 `ai-caddie-private`；容器停了，数据仍然需要。
- **镜像** 是回滚和复现的依据。至少保留 production、current candidate、rollback 三个明确 digest；其余镜像要先确认没有容器引用且能从 SHA/lockfile/构建参数重建。
- **日志、退出码、测试报告、截图和 SHA manifest** 是发布/事故证据，应该先归档再删运行态对象。
- **BuildKit cache** 才是真正的可重建缓存，适合定期按年龄清理；清 cache 不等于可以删 volume。

删除容器也不一定释放很多空间，因为层可能被其他镜像共享；实际效果必须用 `df -h` 复核，不能只看 Docker 的“可回收”估算。

## 现在采用的保留等级

| 等级 | 内容 | 生命周期 | 自动清理 |
|---|---|---|---|
| P0 保护 | canonical source、已推送 commit/tag、用户/原始 Garmin 数据、数据库、凭据、迁移与恢复脚本 | 长期；需可恢复备份 | 禁止 |
| P1 发布证据 | approved 图、测试报告、IPA/dSYM、镜像 digest、回滚 manifest、事故日志 | 当前版本及上一个版本；release gate 关闭后再归档 | 禁止自动删 |
| P2 临时工作 | Fable/Opus review snapshot、单个委派 worktree、stopped test container、preview/tunnel | review 24h；implementation 7d；container/session 24h | 到期由 owner 按 allow-list 删除 |
| P3 缓存 | `.venv`、`node_modules`、Swift `DerivedData`、BuildKit、uv/npm/pip/Playwright cache | 按年龄和磁盘压力 | 每周或低于容量阈值清理 |

工具不是等级。Claude 产生的唯一 Garmin fixture 是 P0；Docker 的数据库 volume 也是 P0；反过来，Claude review 快照和 Docker build layer 都是 P2/P3。

## Claude/Fable/Opus 的新规矩

根因已经明确：过去把“咨询/审查”误当成“长期实现分支”，导致每次会话复制源码并安装一份环境。以后：

- Codex 是唯一 canonical checkout 的集成负责人。
- Fable/Opus 默认只读，只接收 source-only snapshot，路径放 `/dev/shm/aicaddie-review-<id>`，TTL 24 小时。
- Review 不创建持久 Git worktree，不安装依赖，不创建 `.venv`，不构建镜像，不启动服务。
- 只有 Codex 明确委派的一个有 owner、用途、创建时间和过期时间的实现任务，才允许一个临时 implementation worktree，最长 7 天。
- 同时最多一个 implementation worktree 和一个 review snapshot；意见并行复用同一个 snapshot。
- 每次会话结束必须报告创建了什么、保护了什么、可删什么、何时清理以及清理结果。

这意味着“Claude 不是主要负责人”会落实为资源边界，而不是口头约定：它帮忙发现问题和给建议，但不会再留下第二套长期源码树。

## 本次状态与下一步

本轮已经完成的安全清理只有旧 `.venv` 和 BuildKit cache；没有删除源码父目录、运行容器、镜像或 named volume。根盘已从满盘恢复到约 27 GiB 可用。

截至本轮远端只读复核，旧快照目录仍有 79 份、合计约 884 MiB，`.venv`
为 0；Docker 仍有 59 个镜像、48 个容器（10 个运行中）和 87 个 volume，
BuildKit 约 2.8 GiB 且当前无可回收项。这些数字说明依赖副本已经清掉，
剩余源码快照和 Docker 数据必须逐项判定，不能用一次全局 prune 代替。

下一次清理按这个顺序进行：

1. 为 38 个 stopped container 生成逐项 manifest，记录日志、退出码、挂载和镜像引用。
2. 只删除明确标记为临时且无数据挂载的容器。
3. 重新计算无引用镜像，再保留 production/candidate/rollback 后删除冗余镜像。
4. 对 anonymous volume 做挂载来源核对；named volume 必须单独批准，禁止顺手 prune。
5. 对 79 个源码快照做 SHA/唯一文件/diff 清点；证明冗余后再分批删除，先保留 manifest 和可恢复 patch。

在这些清单生成前，不执行批量 `rm -rf`、`git clean`、`docker system prune` 或 `docker volume prune`。

## 2026-08-22 后续清理记录

上面的容量数字是本轮开始时的历史快照。之后按同一规则完成了第二阶段
清理，当前事实以远端复核为准：

- 根盘从满盘恢复到 `98G` 总容量、约 `54G` 已用、`39G` 可用（约 59%）。
- `/home/jason/codex-runs` 从约 `9.1G` 降到约 `6.3G`。
- 14 个旧运行目录的 `.venv` 已逐项记录并删除（`du` 合计约 6.6 GiB，因共享
  层实际释放约 3 GiB）；保留当前 watch 同步目录和
  主 watch 目录的 `.venv` 入口（后者仅为空壳），源码目录没有删除。
- 79 个 Claude worktree 没有删除。完整内容级清单在
  `/home/jason/garmin-ai-caddie-data/cleanup-manifests/2026-08-22T2016Z-worktree-audit`；
  已生成可恢复压缩档
  `/home/jason/garmin-ai-caddie-data/archives/garmin-ai-caddie-worktrees-2026-08-22.tar.zst`，
  SHA256 为
  `6d209af197da90cb51e972347d1a4ddaae112f6325a219c228e3870a14bfe235`，并验证可还原 79 个根目录、54117 个文件。
- 删除了一个无 tag、无容器引用的 dangling API 镜像（约 621MB）。
- 按 `until=168h` 清理 BuildKit，回收约 285.5MB；没有执行全局
  `docker system prune`。
- pnpm store prune 回收约 669MB；npm cache 已清空；uv cache（主机没有
  `uv` 命令）按 P3 规则删除。它们都是可重建缓存，不含用户数据。
- 当前 Docker 只保留 5 个运行容器、9 个有 tag 的镜像和 5 个 named volume。
  `ai-caddie-private`（约 10.5G）是持久数据，`aicaddie-pw-profile`
  是浏览器登录 profile，均不能按测试缓存删除。

### 尚未自动删除的空间

`docker system df` 仍会把约 5.8G 标为可回收，主要是明确保留的 sync/API
候选与 rollback 镜像层，不是悬空测试对象：

- 生产 API：`garmin-ai-caddie-api:5130f65`
- 当前候选 API：`garmin-ai-caddie-api:6a6080c-candidate`
- 当前 review API：`garmin-ai-caddie-api:f463725`（用户仍可能在看 review）
- API rollback：`garmin-ai-caddie-api:rollback-a6d5ec5`
- sync 当前/rollback：`aicaddie-sync:6a6080c-candidate`、
  `aicaddie-sync:28a9d18-candidate`

只有在候选发布或 review 明确关闭后，才从这组中删除旧对象。系统 journal
约 2G，属于全机共享诊断日志，本轮没有擅自 vacuum；应另设日志轮转上限后
再处理。`/home/jason/.local/share/pnpm/store` 仍约 1G、Playwright 约
267MB，分别是其他项目可复用的共享缓存，暂不删除。

本轮新增审计清单：

- `2026-08-22T2032Z-codex-runs-audit`
- `2026-08-22T2032Z-codex-venv-cleanup`
- `2026-08-22T2032Z-docker-cache-cleanup`
- `2026-08-22T2032Z-cache-cleanup`

以后所有 Claude/Fable/Opus 会话必须使用 source-only `/dev/shm` snapshot；
不得在 `/home/jason/codex-runs` 复制 `.venv`，不得为 review 建立长期
worktree 或 Docker image。每次会话结束时，按 session 前缀清理自己的
容器、缓存和 tunnel，并把 TTL/allow-list 写入上述持久 manifest。

本轮还确认了一个容易被忽略的根因：部分 bind-mounted 构建目录由容器内
`root` 写入，导致宿主用户无法直接删除旧 `.venv`。以后构建容器必须使用
匹配宿主的 UID/GID，或把构建产物写到临时 Docker volume；确需提权清理时，
只能对已生成的精确 allow-list 使用 `sudo`，并把失败/成功路径记录下来。
