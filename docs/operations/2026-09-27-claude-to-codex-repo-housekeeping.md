# Claude → Codex：开工前的仓库收尾（请在本 PR 里回复）

来源：owner 与 Claude 的会话（2026-09-27）。Claude 在云端，git 只能推送自己的工作分支
`claude/code-audit-performance-17wqcv`，不能删分支、打标签或改默认分支（均返回 403）。
以下事项需要有完整权限的 Codex 在 homeserver 上执行。**请在本 PR 的评论里逐项回复结果或疑问**，
Claude 订阅了本 PR，会在评论里跟进。

owner 的决定：

- 重设计（`docs/design/2026-09-25-ui-redesign/`）开工前，先把旧的东西收拾干净。
- 不开长期大分支，直接在主干上按批次做（每批一个短 PR）；只有手表自动记杆 v2 用实验开关。
- `main` 已无意义，把 `integration/v2` 改名为 `main`。
- 远程旧分支清理干净。

## 1. 清理远程分支

脚本：`ops/oneoff/2026-09-27-cleanup-remote-branches.sh`（按 `integration/v2 = cef291a3` 时的 `git branch -r` 生成，运行前请复核）。

验证记录（Claude，2026-09-27，脚本在 `329e03ba` 之后的提交）：

- `bash -n ops/oneoff/2026-09-27-cleanup-remote-branches.sh`：通过。
- 远端引用改为每阶段一次 `git ls-remote origin 'refs/heads/*' 'refs/tags/*'` 后本地比对（原先每个 archive 分支一次网络往返）；打完所有标签后一次性复核，任一标签不对就中止、不删任何分支。
- 真实远端 dry-run：`PATH=<gh 桩>:$PATH ops/oneoff/2026-09-27-cleanup-remote-branches.sh --log /tmp/dry.log`，
  gh 桩返回 default=`integration/v2` 和当时 5 个开放 PR 的 head；退出 0，耗时 7.3 秒，计划 64 个标签、266 个删除（含旧 `main`），无“不在快照”的分支。
  Codex 执行前请用真实 `gh` 再跑一次 dry-run，把耗时和退出码贴到 PR。
- 离线测试 `tests/test_cleanup_remote_branches_script.py`（进 CI 的 `unittest discover`，不联网）：本地 bare origin + gh 桩，覆盖
  dry-run 不改动、执行后归档/删除且重跑幂等、按日志续跑、基线漂移、默认分支不对、开放 PR、分支漂移、标签冲突；
  去掉开放 PR 检查的变异会让测试失败。
- Codex review 5 之后：执行前先确认日志可写（父目录不存在或不可写直接中止，不推任何东西），本地 `archive/*` 标签冲突也并入 preflight；
  harness 增加这两个用例（共 10 个），去掉任一检查都会让对应用例失败。

- 201 个已并入 `integration/v2` 的分支：直接删除。
- 67 个未并入的旧分支（原 64 个旧实验，加上已关闭的 #218/#219/#291）：先打 `archive/<分支名>` 标签再删除，可随时恢复。
  如果其中有你仍在用或 `PROJECT_STATE.md` 仍引用的，请从列表里移除并在评论里说明。
- 旧 `main`：已存档为 `archive/main-before-v2-integration-2026-05-28`（同一提交），直接删除。
- 当前执行预期：67 个 archive tag、201 个已合并分支和旧 `main`，共 269 个 branch 删除；#176、#334 分支不在删除集合。
- 保留：`integration/v2`、`claude/code-audit-performance-17wqcv`、以及仍开放的 #176 分支。

**改名前 4 个开放 PR**（按 Codex review 4 更新；#218/#219/#291 已按下表决议关闭）：

| PR | 标题 | 结论 |
|---|---|---|
| #176 | docs(spec): 多用户 AI Caddie 架构设计 | 未被完全取代。Claude 在 PR334 评论里给出逐章映射后再由 owner 决定；在此之前不关、不删分支 |
| #218 | [设计预览] 手表球道图重做 | 已被本 PR 的 `watch.html` / B6 取代：关闭，分支打 archive 标签 |
| #219 | fix(caddie): 离线球童一杆一距离 | 问题已在 `integration/v2` 的 `ca3fa89a` 修复（同一球杆取 median）：附测试证据关闭，分支打 archive 标签 |
| #291 | feat(watch): 前/中/后大数字 + 大字模式 | 与 B6 / B7 重叠：关闭，分支打 archive 标签；需要的部分在 B6 做 |

## 2. `integration/v2` 改名为 `main`

（按 Codex review 2 补全：完整清单、改名前后状态记录、分层扫描验收。）

### 2.1 改名前记录（写进本 PR 评论或 `PROJECT_STATE.md`）

- `gh api repos/jasonhorga/garmin-ai-caddie --jq .default_branch` 的结果和 `integration/v2` 的 SHA。
- 所有开放 PR 的 `number / base.ref / head.ref`（改名后逐个核对 base 已迁到 `main`）。
- homeserver 上每个 clone / worktree 的路径、当前分支、`git rev-parse --abbrev-ref @{u}`、
  `git symbolic-ref refs/remotes/origin/HEAD`。
- 用到分支名的部署 / 定时任务（`auto_sync.sh`、deploy gate、cron / systemd 单元）清单。

### 2.1a 仓库外引用分类（Codex review 10，homeserver 只读核对，2026-09-27）

活动调用链（`/etc/cron*`、`/etc/systemd/system`、
`/home/jason/garmin-ai-caddie-data/operations/deploy-tools`、运行中的
`aicaddie-tunnel.service`）：**没有** `integration/v2`。这条结论比“只列出三个文件”更严格：改名后的全量 `*.sh` 扫描一共命中 **120** 个文件，但没有一个落在活动调用链里。

| 路径/根目录 | 命中数 | 调用证据 | 结论 |
|---|---:|---|---|
| `/home/jason/codex-runs/**` | 109 | 候选、评审、部署和验证快照；不在 cron / systemd / deploy-tools 调用链 | 历史/临时快照，**不机械替换、不批量删除**。包括当前 PR 的只读评审快照；快照若误跑会因旧分支 ref 已不存在而 fail-closed |
| `/home/jason/garmin-ai-caddie-data/archives/**` | 2 | broken-worktree rescue 归档；无活动调用 | 归档历史快照，保留、不改 |
| `/home/jason/.local/share/Trash/files/**` | 7 | Trash 中的旧工作树；无活动调用 | Trash 历史快照，保留、不改；不把 Trash 当作生产输入 |
| `/home/jason/watchreview/ops/bootstrap_nas_vm_api.sh` | 1 | 旧评审工作树副本；无活动调用 | 历史快照，保留、不改 |
| `/home/jason/r12review/ops/bootstrap_nas_vm_api.sh` | 1 | 旧评审工作树副本；无活动调用 | 历史快照，保留、不改 |
| `/home/jason/reserve-specs.sh` | 1 | 不在自动任务里，但仍可被人工执行 | **唯一需要改的仓库外入口**：已把 `fetch/checkout` 从 `integration/v2` 改为 `main`，并做了正确的无写入 dry-run（见 2.1b） |

扫描证据：
`/home/jason/garmin-ai-caddie-data/operations/pr334-housekeeping-20260927/external-shell-refs-post-rename.txt`。
今后的验收以“活动调用链必须为零、上述五类历史根目录允许命中、`reserve-specs.sh` 只允许 `main`”为准；不能再把 120 个历史文件误报成 3 个活动漏项。

### 2.1b `reserve-specs.sh` 更新与 dry-run 记录（2026-09-27）

`/home/jason/reserve-specs.sh` 已改为抓取 `origin main`。改名前 checksum 为
`b2bb7c556e01a63ceca1d356572be3c54e5acbc345326143faf8d5b912f0f500`，改后为
`a9ed9d0bd6a6863eaf03b8c99f6c84c1424cdcc53c8558f1e8783fc6f452a8f9`；原文件保留在
`/home/jason/garmin-ai-caddie-data/operations/pr334-housekeeping-20260927/reserve-specs.sh.before-main-rename`。

需要透明记录一个执行失误：第一次所谓 dry-run 使用了错误命名的 stub，脚本实际运行了一次。它对已有的
`/home/codex/garmin-ai-caddie` 外部 checkout 执行了 specs checkout，并重新生成了
`web_v2/dist/*.html`；该 checkout 原本已有的 17 个 staged spec 改动没有被 reset 或覆盖，服务仍保持
`index.html`、`todo.html`、`spec.html`、`rv2.html` HTTP 200。生成的 `/tmp/specsrc`、`/tmp/specout` 已按 checksum 记录后删除，未删除持久源数据。

随后使用正确的命令替身执行了真正的 no-write dry-run，退出码 0；输出、日志和临时清理记录分别保存在：

- `reserve-specs-true-dry-run.out`
- `reserve-specs-true-dry-run.log`
- `reserve-specs-temp-cleanup.txt`

均位于上述 housekeeping 证据目录。由于外部 checkout 的既有 dirty 状态在执行前就不明，Codex 没有盲目 reset；后续若要清理它，必须先由 owner 对那 17 个 staged 文件逐项确认。

### 2.2 顺序

1. 关闭 #218/#219/#291（已完成），确认它们的 head SHA 已进入 `ARCHIVE_SNAPSHOT`；#176 和 #334 保持开放。
2. 跑完第 1 步（旧 `main` 已删，否则改名会冲突）。
3. 改名（需要仓库 admin）：`gh api -X POST repos/jasonhorga/garmin-ai-caddie/branches/integration%2Fv2/rename -f new_name=main`，
   保存响应；确认 `default_branch == main`，开放 PR 的 base 已自动迁移，分支保护（如有）已跟过去。
4. homeserver 每个 clone / worktree：
   `git fetch origin && git branch -m integration/v2 main && git branch -u origin/main main && git remote set-head origin -a`，
   再按 2.1 的记录逐个核对当前分支、上游和 `origin/HEAD`。
5. 改名**之后**再改写死的分支名（改名前改会让部署脚本去拉不存在的 `main` 内容）。

### 2.3 必须改的活动引用（按 `cef291a3` 时的 `git grep -n integration/v2`）

| 文件 | 行 | 改法 |
|---|---|---|
| `ops/bootstrap_nas_vm_api.sh` | 5, 17 | 默认分支与帮助文字 → `main` |
| `.github/workflows/ci.yml` | 9 | push 触发只保留 `main` |
| `tests/test_ci_workflow.py` | 60 | 断言改为 `main` |
| `tests/test_deployment_manifests.py` | 369 | 同上 |
| `tests/test_server_v2_readiness.py` | 97 | 同上 |
| `tests/test_phase6_external_readiness.py` | 35, 436, 504, 570, 642, 693, 730, 766, 819 | 同上 |
| `.claude/skills/recording-demo-videos/SKILL.md` | 18, 37 | `--ref main` |
| `docs/ios-testflight-setup.md` | 39, 43 | canonical branch → `main` |
| `docs/deployment/nas-vm-tunnel.md` | 34 | raw URL 路径 → `main` |
| `docs/superpowers/specs/work-board.md` | 47 | 当前分支描述 |
| `docs/superpowers/specs/ai-caddie-spec.md` | 3, 7, 115 | “唯一的、活的产品说明书”：主线改为 `main`；第 115 行“把 `integration/v2` 合进 `main`”改成已完成（改名即完成，写日期），不删这一项 |
| `AGENTS.md`、`PROJECT_STATE.md` 顶部 | — | “当前分支”描述；历史条目不改 |
| homeserver 部署 / 定时任务 | — | 按 2.1 清单 |

历史文档（`docs/reviews/`、`docs/operations/branch-*`、`PROJECT_STATE.md` 的历史条目、旧交接文档）记录的是当时事实，**不改**。

### 2.4 验收：分层扫描

改完后跑一次，结果贴到本 PR：

```sh
# 活动代码、workflow、测试、运维脚本、agent/skill 说明：必须为空
git grep -n "integration/v2" -- \
  '*.py' '*.sh' '*.swift' '*.kt' '*.ts' '*.tsx' '*.js' '*.yml' '*.yaml' '*.toml' '*.json' \
  '.github/' 'ops/' 'tests/' 'tools/' '.claude/' 'AGENTS.md' 'CLAUDE.md' \
  ':!ops/oneoff/' ':!tests/test_cleanup_remote_branches_script.py'
# 活的文档（文件名不带日期 = 当前规范 / 手册 / 看板）：除 PROJECT_STATE.md 的历史条目外必须为空
git ls-files 'docs/*.md' 'docs/**/*.md' | grep -Ev '/[^/]*20[0-9]{2}-?[0-9]{2}-?[0-9]{2}[^/]*$' \
  | grep -v '^docs/operations/PROJECT_STATE.md$' | xargs git grep -n "integration/v2" --
git grep -n "integration/v2" -- docs/operations/PROJECT_STATE.md | head -20   # 只允许历史条目，顶部“Branch”行必须已改
# 带日期的文档（历史设计、计划、评审、交接）：记录当时事实，允许保留，不改
# homeserver 上仓库外：调用链必须为空；home 目录的 120 个命中必须按 2.1a 分类
grep -rn "integration/v2" /etc/cron* /etc/systemd/system /home/jason/garmin-ai-caddie-data/operations/deploy-tools 2>/dev/null
grep -rln "integration/v2" /home/jason --include='*.sh' 2>/dev/null
```

再跑 `uv run pytest tests/test_ci_workflow.py tests/test_deployment_manifests.py tests/test_server_v2_readiness.py tests/test_phase6_external_readiness.py`，
并确认改名后第一次 push 到 `main` 触发了 CI。
`ops/oneoff/2026-09-27-cleanup-remote-branches.sh` 和它的离线测试 `tests/test_cleanup_remote_branches_script.py` 验证的是改名**前**的一次性清理，
必须保留 `integration/v2` 字样，改名后不改、不机械替换；上面第一层扫描已把这两个路径排除。其余任何命中都算漏项。

这一步可以由 Codex 做，也可以回复“请 Claude 做”，Claude 在本分支提交后由你合并。

## 3. 其他收尾（请确认状态）

- Garmin 同步：Codex 已确认恢复（production revision 有同 revision 的 `aicaddie-sync` 镜像，cron 跑通，部署 gate 已绑定同步镜像）。
- 本 PR 的设计文档（`docs/design/2026-09-25-ui-redesign/`，含 `IMPLEMENTATION_PLAN.md`）：已随 PR #334 审阅并合并。
- 已创建基线标签 `v2-baseline-2026-09`，指向合并提交；`PROJECT_STATE.md` 记录了当前最新内部 TestFlight Build 76（本次文档收尾没有重新上传）。
- 已按 `IMPLEMENTATION_PLAN.md` 把 B0 设为 `PROJECT_STATE.md` 的当前任务。

### 3.1 Codex 执行记录（2026-09-27）

- 已按 allow-list 完成远程旧分支归档/删除：67 个 archive tag、269 个 branch 删除；清理执行的中间状态只剩 `main`、#334 head、#176 head；PR #334 合并并删除其 head 后，最终只剩 `main` 和 #176。
- 已把 `integration/v2` 重命名为 `main`，默认分支和 #334/#176 base 已核对，旧 ref 已不存在。
- 活动引用修正已在本 PR 分支提交（见后续 PR comment）；一次性清理脚本和 dated 历史文档保留原名。
- 外部 shell 全量扫描、`reserve-specs.sh` 迁移和上述误运行影响均已记录；PR #334 已合并为 `57ee8431`，基线 tag 已创建，B0 已接棒。临时评审快照已按 allow-list 清理，记录在 `/home/jason/garmin-ai-caddie-data/cleanup-manifests/20260927T1355Z-pr334-review-snapshot/`。

## 回复格式建议

每项一条评论，写：做了 / 没做（原因）/ 需要 owner 决定。Claude 会在评论里回复疑问或补提交。
