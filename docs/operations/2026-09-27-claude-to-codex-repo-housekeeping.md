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
  gh 桩返回 default=`integration/v2` 和当前 5 个开放 PR 的 head；退出 0，耗时 7.3 秒，计划 64 个标签、266 个删除（含旧 `main`），无“不在快照”的分支。
  Codex 执行前请用真实 `gh` 再跑一次 dry-run，把耗时和退出码贴到 PR。
- 离线测试 `tests/test_cleanup_remote_branches_script.py`（进 CI 的 `unittest discover`，不联网）：本地 bare origin + gh 桩，覆盖
  dry-run 不改动、执行后归档/删除且重跑幂等、按日志续跑、基线漂移、默认分支不对、开放 PR、分支漂移、标签冲突；
  去掉开放 PR 检查的变异会让测试失败。
- Codex review 5 之后：执行前先确认日志可写（父目录不存在或不可写直接中止，不推任何东西），本地 `archive/*` 标签冲突也并入 preflight；
  harness 增加这两个用例（共 10 个），去掉任一检查都会让对应用例失败。

- 201 个已并入 `integration/v2` 的分支：直接删除。
- 64 个未并入的旧分支（主要是 7 月的 `codex/*` 实验、`evidence/plan1-*` 红绿证据、若干 `superpowers/*`）：先打 `archive/<分支名>` 标签再删除，可随时恢复。
  如果其中有你仍在用或 `PROJECT_STATE.md` 仍引用的，请从列表里移除并在评论里说明。
- 旧 `main`：已存档为 `archive/main-before-v2-integration-2026-05-28`（同一提交），直接删除。
- 保留：`integration/v2`、`claude/code-audit-performance-17wqcv`、以及 4 个挂着开放 PR 的分支。

**4 个开放 PR**（按 Codex review 4 更新）：

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

### 2.2 顺序

1. 跑完第 1 步（旧 `main` 已删，否则改名会冲突）。
2. 改名（需要仓库 admin）：`gh api -X POST repos/jasonhorga/garmin-ai-caddie/branches/integration%2Fv2/rename -f new_name=main`，
   保存响应；确认 `default_branch == main`，开放 PR 的 base 已自动迁移，分支保护（如有）已跟过去。
3. homeserver 每个 clone / worktree：
   `git fetch origin && git branch -m integration/v2 main && git branch -u origin/main main && git remote set-head origin -a`，
   再按 2.1 的记录逐个核对当前分支、上游和 `origin/HEAD`。
4. 改名**之后**再改写死的分支名（改名前改会让部署脚本去拉不存在的 `main` 内容）。

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
  ':!ops/oneoff/'
# 操作手册：只允许历史叙述，逐行确认
git grep -n "integration/v2" -- 'docs/' ':!docs/reviews/' ':!docs/history/'
# homeserver 上仓库外的部署文件
grep -rn "integration/v2" <部署目录> /etc/cron* /etc/systemd/system 2>/dev/null
```

再跑 `uv run pytest tests/test_ci_workflow.py tests/test_deployment_manifests.py tests/test_server_v2_readiness.py tests/test_phase6_external_readiness.py`，
并确认改名后第一次 push 到 `main` 触发了 CI。
`ops/oneoff/2026-09-27-cleanup-remote-branches.sh` 是一次性脚本，按改名前状态写死，改名后不再运行，不改。

这一步可以由 Codex 做，也可以回复“请 Claude 做”，Claude 在本分支提交后由你合并。

## 3. 其他收尾（请确认状态）

- Garmin 同步：Codex 已确认恢复（production revision 有同 revision 的 `aicaddie-sync` 镜像，cron 跑通，部署 gate 已绑定同步镜像）。
- 本 PR 的设计文档（`docs/design/2026-09-25-ui-redesign/`，含 `IMPLEMENTATION_PLAN.md`）：请审阅后合并。
- 以上完成后打基线标签，例如 `v2-baseline-2026-09`，并在 `PROJECT_STATE.md` 记下对应 TestFlight 版本号。
- 然后按 `IMPLEMENTATION_PLAN.md` 把 B0 设为 `PROJECT_STATE.md` 的当前任务。

## 回复格式建议

每项一条评论，写：做了 / 没做（原因）/ 需要 owner 决定。Claude 会在评论里回复疑问或补提交。
