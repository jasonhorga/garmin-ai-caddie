# caddie RUNBOOK（项目台用）

自 2026-10-22 起，AgentHub 只是 Claude × Codex 的协作基础设施，不再合并、发布、
确认、回滚或出包。这些事由 **caddie 项目台**（一个 Claude 会话）按本文件手动做。
`docs/operations/runbook.md` 仍是部署脚本的契约参考（退出码、环境变量、开机恢复），
本文件只写"项目台按什么顺序、跑什么命令"。

本仓库是公开的：这里只用占位符，真实值都在本机文件里。

| 占位符 | 含义 |
|---|---|
| `<caddie-data>` | 本机 caddie 数据目录（项目台交接文件里有绝对路径） |
| `<deploy-env>` | `<caddie-data>/secrets/deploy.env`，0600，部署脚本的非秘密环境变量（见 §3.0） |
| `<sync-log>` | 生产 sync cron 写的日志（路径见 cron 包装脚本） |
| `<api-host>` | 生产 API 的公网源（`native-mobile.yml` 的默认 `api_base_url`） |
| `<codex-runs>` | 本机一次性 checkout 根目录（HOMESERVER-POLICY 规定的位置） |
| `<checkout>` | 一次性 checkout：`<codex-runs>/caddie-<任务>-<日期>/` |

## 1. 测试

**本地**（项目台或 Codex 在 `<checkout>` 里跑；用共享只读运行时，不建 `.venv`、不 `uv sync`）：

```bash
cd <checkout>
AI_CADDIE_DATA_MODE=fixture <caddie-data>/venvs/garmin-ai-caddie-ci/bin/python -m unittest discover -s tests
# 只跑本卡相关：
AI_CADDIE_DATA_MODE=fixture <caddie-data>/venvs/garmin-ai-caddie-ci/bin/python -m unittest tests.acceptance.test_card_<N>_<name> -v
```

`uv.lock` 变了，共享运行时要按 HOMESERVER-POLICY 重建，不能临时装包。前端、Docker、
iOS 不在本机跑，交给 CI。

**CI（合并前必须全绿，看 PR head 那一次 run）：**

| 检查 | workflow | 何时必需 | 时长 |
|---|---|---|---|
| `backend` | `ci.yml` | 所有 PR | 1–2 分钟 |
| `frontend` | `ci.yml` | 所有 PR | 1–2 分钟 |
| `docker` | `ci.yml` | 所有 PR | 2–4 分钟 |
| `native-mobile` | `native-mobile.yml` | PR 改到它的 `pull_request.paths`（`mobile/ios/**`、`Package.swift` 等） | 17–21 分钟 |

```bash
gh pr checks <PR> --repo jasonhorga/garmin-ai-caddie
gh pr view <PR> --repo jasonhorga/garmin-ai-caddie --json headRefOid,mergeable,statusCheckRollup
```

`agenthub-native-mutant.yml`（AgentHub 的对抗变异门）不再是必需检查。

**native PR 要看截图**：拉同一次 `native-mobile` run 的两份产物，交子代理逐张看，
在 PR 里写每份产物看到了什么、和卡的验收对不对得上；看完删目录。

```bash
RUN=$(gh run list --repo jasonhorga/garmin-ai-caddie --workflow native-mobile.yml \
  --commit <PR-head-sha> --json databaseId,conclusion --jq '.[0].databaseId')
gh run download "$RUN" --repo jasonhorga/garmin-ai-caddie -n design-snapshots -n watch-snapshots \
  -D <caddie-data>/tmp/pr<PR>-<head8>
```

## 2. 合并

前置：没有冻结（§5）；PR head 上 §1 的检查全绿；`mergeable=MERGEABLE`；项目台已审过 diff
和 Codex 的 `REPORT.md`。改到以下文件时项目台要逐行审（它们在主机上以 Docker 权限运行或决定数据）：
`ops/agenthub_deploy.py`、`ops/build_sync_image.sh`、`ops/complete_homeserver_api_deploy.sh`、
`Dockerfile*`、`migrations/**`、`ops/start_api.sh`、`server_v2/{auth_api,session,apple_auth,identity_repo}.py`、
`ai_caddie/garmin/**`、`.github/**`。

```bash
gh pr merge <PR> --repo jasonhorga/garmin-ai-caddie --merge --match-head-commit <PR-head-sha>
SHA=$(gh api repos/jasonhorga/garmin-ai-caddie/commits/main --jq .sha)
# 等 main 上这次 push 的 ci.yml 绿（后台跑，跑完叫醒）：
RUN=$(gh run list --repo jasonhorga/garmin-ai-caddie --workflow ci.yml --branch main --commit "$SHA" \
  --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN" --repo jasonhorga/garmin-ai-caddie --exit-status
```

合并就是上线：没有候选、预发或手动切换。合并后立刻按 §3 上线。

## 3. 上线

### 3.0 一次性准备

`<deploy-env>`（0600）写这几行，值抄自本机 AgentHub 时代 caddie `project.toml` 的
`[release.deploy].env`（只含端口、容器前缀、网络、卷、锁、sync 脚本路径、公网 health URL，无秘密）：

```
AICADDIE_API_PORT=…
AICADDIE_CONTAINER_PREFIX=aicaddie-release-
AICADDIE_DEPLOY_NETWORK=…
AICADDIE_PRIVATE_VOLUME=…
AICADDIE_SYNC_LOCK=…          # 必须和 sync cron 包装脚本 export 的锁是同一个文件
AICADDIE_SYNC_SCRIPT=…        # cron 实际跑的 sync 脚本；配了才会做 sync 合约检查
AICADDIE_DEPLOY_PUBLIC_HEALTH_URL=https://<api-host>/api/v2/health
```

缺 `AICADDIE_SYNC_SCRIPT` 或 `AICADDIE_DEPLOY_PUBLIC_HEALTH_URL` 时脚本会打印 `skipped`
而不是失败——上线日志里看到 `skipped` 就是 `<deploy-env>` 坏了，按失败处理。

### 3.1 每次上线（`$SHA` = 刚合并、main CI 绿的 main 提交）

```bash
set -euo pipefail
D=<caddie-data>
test ! -e "$D/release-freeze" || { cat "$D/release-freeze"; exit 1; }   # §5
df -h "$D"                                                               # 留 ≥ 1 GiB
exec 8>"$D/locks/deploy.lock"; flock -n 8                                # 同一时间只一个上线

# (a) 发布前数据库快照（每次都做，几秒钟；保留最近 3 份）
mkdir -p -m 700 "$D/release-snapshots"; umask 077
F="$D/release-snapshots/caddie-$(date -u +%Y%m%dT%H%M%SZ)-${SHA:0:12}.dump"
docker exec garmin-ai-caddie-db-1 pg_dump -U aicaddie -d aicaddie -Fc > "$F.partial"
test -s "$F.partial"
docker exec -i garmin-ai-caddie-db-1 pg_restore --list < "$F.partial" | grep -q .
mv "$F.partial" "$F"
ls -1t "$D"/release-snapshots/*caddie-*.dump | tail -n +4 | xargs -r rm --

# (b) 导出这一提交的干净树（无 .git），在树根跑部署脚本
T=<codex-runs>/caddie-deploy-${SHA:0:12}
rm -rf -- "$T"; mkdir -m 700 "$T"
gh api "repos/jasonhorga/garmin-ai-caddie/tarball/$SHA" | tar -xz --strip-components=1 -C "$T"
mkdir -p "$D/deploy-logs"; L="$D/deploy-logs/$(date -u +%Y%m%dT%H%M%SZ)-${SHA:0:12}.log"
cd "$T"
set +e
env -i PATH="$PATH" HOME="$HOME" LANG=C.UTF-8 bash -c \
  'set -a; . "$0"; set +a; exec timeout 2400 ./ops/agenthub_deploy.py deploy "$1"' \
  "$D/secrets/deploy.env" "$SHA" > "$L" 2>&1
RC=$?
set -e
tail -n 30 "$L"; echo "exit=$RC"
printf '%s\t%s\tdeploy\texit=%s\t%s\n' "$(date -u +%FT%TZ)" "$SHA" "$RC" "$(basename "$F")" >> "$D/releases.tsv"
```

用 Bash `run_in_background` 跑（镜像要构建时 5–15 分钟，上限 40 分钟），跑完叫醒。
完成后删 `$T`；`deploy-logs` 留最近 20 份。

脚本自己会做：库健康检查、构建 `garmin-ai-caddie-api:$SHA` **和同 revision 的
`aicaddie-sync:$SHA`**（sync cron 只认和当前 API 同 revision 的 sync 镜像，缺了每小时同步
会静默失败）、拿 sync 锁、停旧容器起新容器、等本地 health、跑部署闸门（check-only）、
跑 sync 合约（check-only）、等公网 health、保留最近 2 个停掉的旧容器供回滚。
失败时自动恢复旧容器。

### 3.2 `ops/agenthub_deploy.py` 或开机单元变了

部署的提交改到 `ops/agenthub_deploy.py` 或 `ops/systemd/aicaddie-stack-up.service` 时，
上线成功后在 `$T` 里按 `docs/operations/runbook.md`「Boot recovery」重新安装开机恢复副本
（`install … ~/.local/lib/aicaddie/agenthub_deploy.py` 等），并用
`sha256sum ops/agenthub_deploy.py ~/.local/lib/aicaddie/agenthub_deploy.py` 确认一致。

## 4. 确认上线成功

`exit=0` 且日志末行 `result=ok action=deploy revision=$SHA`，日志里**没有** `skipped`。再核对：

```bash
set -a; . <caddie-data>/secrets/deploy.env; set +a
curl -fsS "http://127.0.0.1:${AICADDIE_API_PORT}/api/v2/health"     # {"status":"ok","revision":"$SHA"}
curl -fsS "$AICADDIE_DEPLOY_PUBLIC_HEALTH_URL"                          # 同上
docker ps --filter name=aicaddie-release- --format '{{.Names}} {{.Status}}'   # 只有 aicaddie-release-${SHA:0:8} 在跑
docker image inspect "aicaddie-sync:$SHA" --format '{{index .Config.Labels "ai.caddie.source-revision"}}'  # = $SHA
```

下一个整点 37 分的 sync 跑完后看一眼 `<sync-log>` 末尾：没有新的 `SYNC FAILED`。
卡里写了"线上可见的验收"时，项目台用 `curl https://<api-host>/…` 照做一遍（不再有单独的
"release 档生产验证"会话）。

都对上 → 给 Jason 一句"线上变了什么"。

## 5. 失败、回滚、冻结

| 情况 | 线上状态 | 项目台做什么 |
|---|---|---|
| `exit=2` | 没动 | 配置/参数错（多半是 `<deploy-env>`）；修好重跑，不冻结 |
| `exit=1` | 旧版本仍在服务 | 冻结；读日志 `reason=`，开卡修，修好走正常流程上线 |
| `exit=1` 且 `reason=not enough time left before AICADDIE_DEPLOY_DEADLINE_SECONDS` | 旧版本仍在服务 | 构建太慢（10-22 实例：构建缓存没了，`uv sync` 两次各 ~14 分钟，共 37 分钟）。镜像多半已建好进了缓存：查 `docker image inspect garmin-ai-caddie-api:$SHA`，在就直接重跑 `deploy $SHA`，不冻结；先查缓存为什么没了 |
| `exit=3` | 旧版本**没能确认恢复**，线上可能挂了 | 立刻回滚到上一个版本（下面命令）；仍不行跑 `./ops/agenthub_deploy.py up`；冻结；给 Jason 一句"线上挂了，正在恢复/已恢复" |
| 超时被杀 | 不确定 | 先 `curl` 本地 health：新容器在跑就重跑 `deploy $SHA`（只做核对）；没容器在服务就 `rollback <上一个 sha>` |
| `exit=0` 但 §4 有一项不对，或上线后发现回归 | 新版本在服务 | 回滚到上一个版本；冻结 |

上一个版本的 sha（停掉的旧容器带 revision 标签）：

```bash
docker ps -a --filter name=aicaddie-release- \
  --format '{{.Names}}\t{{.Label "ai.caddie.source-revision"}}\t{{.Status}}'
```

回滚（在 `$T` 或任一同版本导出树里跑，环境同 §3.1；只启停已有容器，不构建、不删东西）：

```bash
cd "$T"
env -i PATH="$PATH" HOME="$HOME" LANG=C.UTF-8 bash -c \
  'set -a; . "$0"; set +a; exec timeout 2400 ./ops/agenthub_deploy.py rollback "$1"' \
  <caddie-data>/secrets/deploy.env "$PREV"
```

回滚后按 §4 用 `$PREV` 核对。注意：`git diff --name-only $PREV $SHA -- migrations/` 非空时，
回滚只换代码、不回退库结构；新库结构和旧代码不兼容就改为向前修。用快照
`pg_restore --clean` 恢复数据库会丢掉快照之后写入的数据，**要 Jason 点头**。

**冻结**：

```bash
printf '%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$SHA" "<一句原因>" > <caddie-data>/release-freeze
```

冻结期间不合并、不上线、不出包（修复本身那一张 PR 除外）。修复上线并按 §4 确认后，项目台
自己 `rm <caddie-data>/release-freeze`，在 `releases.tsv` 记一行 `unfreeze`。同一原因第二次冻结
→ 先查根因，再动手。

## 6. TestFlight（只在 iOS/Watch 改动需要到手机/手表上时）

前置：没有冻结；main HEAD 就是线上 revision（§4 已确认）；当天出包少于 3 次。

```bash
gh workflow run ios-testflight.yml --repo jasonhorga/garmin-ai-caddie --ref main \
  -f expected_backend_revision="$SHA" -f upload_to_testflight=true \
  -f test_environment_upload=false -f api_base_url="https://<api-host>" \
  -f release_notes="<≤500 字，写这一包改了什么>"
RUN=$(gh run list --repo jasonhorga/garmin-ai-caddie --workflow ios-testflight.yml --limit 1 \
  --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN" --repo jasonhorga/garmin-ai-caddie --exit-status      # 约 10–15 分钟，上限 60

# 成功后只读核对 TestFlight 上的 build：
gh workflow run ios-testflight-testers.yml --repo jasonhorga/garmin-ai-caddie --ref main \
  -f operation=list -f external_distribution=false -f diagnose_bundles=true
```

外部测试/提交审核（`external_distribution=true` 的任何操作）不在这里做。

## 7. 哪些事要 Jason 点头

要他一句原话（在聊天里，不让他去 GitHub 点按钮）：

- 任何外部 TestFlight 分发、App Store 提交。
- 用快照恢复/覆盖生产数据库，或任何删除生产数据的操作。
- 增删 Funnel/公网路由，改生产端口、卷、网络。
- 合并被自动模式分类器拦下时：请他回一句"合并 caddie#<PR>"，然后项目台自己合。

不用问他：审查、合并、上线、确认、按 §5 回滚、冻结与解冻、重跑 CI、拉 CI 产物、内部 TestFlight 上传（§6，Jason 10-22 定）。
上线后只告诉他"线上变了什么"；需要他做事时只说"要你做什么"，各一句。

## 8. 等待和卡住

不再有 AgentHub 的"卡住提醒"。项目台每次等东西（CI、Codex、上线脚本、TestFlight）都用
后台任务或有上限的 until 循环，超时设该活正常耗时的约 2 倍（CI 10 分钟、native 45 分钟、
上线 40 分钟、TestFlight 60 分钟）；超时 = 卡住，先查为什么，不直接重试。
