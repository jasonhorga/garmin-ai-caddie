# caddie RUNBOOK（job 用）

caddie 卡由土土起的 job 做（11-07 起，项目台已撤）。job 开工只读 `<tutu>/jobs/JOB.md`
（跨项目做法：开工三问、开卡五项、复审八条、报告和交接）和本文件（caddie 自己的流程和不做，
见 §0、§10）；项目台交接文件 DESK.md、par1025 的 COMMON.md / CODEX-NOTE.md 已并入这两处（C402）。
推送、合并、部署、回滚由宿主 CD 做（`<tutu>/docs/same-job-cd.md`）；下文 §2–§5
里「项目台」手工做的合并、上线、回滚步骤只作排障参考；其余各节的「项目台」读作做本卡的 job。
`docs/operations/runbook.md` 仍是部署脚本的契约参考（退出码、环境变量、开机恢复）。

本仓库是公开的：这里只用占位符，真实值都在本机文件里。

| 占位符 | 含义 |
|---|---|
| `<caddie-data>` | 本机 caddie 数据目录（项目台交接文件里有绝对路径） |
| `<deploy-env>` | `<caddie-data>/secrets/deploy.env`，0600，部署脚本的非秘密环境变量（见 §3.0） |
| `<sync-log>` | 生产 sync cron 写的日志（路径见 cron 包装脚本） |
| `<api-host>` | 生产 API 的公网源（`native-mobile.yml` 的默认 `api_base_url`） |
| `<codex-runs>` | 本机一次性 checkout 根目录（HOMESERVER-POLICY 规定的位置） |
| `<checkout>` | 一次性 checkout：`<codex-runs>/caddie-<任务>-<日期>/` |
| `<par1025>` | `<codex-runs>/caddie-codex/par1025`，共享测试脚本（runtests.sh、related-tests.sh、mac-test.sh）和证据目录 |
| `<tutu>` | 土土的工作目录（JOB.md、same-job-cd.md、backlog_edit.py 所在） |

## 0. 流程（job 开工到收尾；11-09 C402 从 DESK.md、COMMON.md、CODEX-NOTE.md 收拢）

跨项目的做法（开工三问、开卡五项、复审八条、报告、交接宿主 CD、等待、BACKLOG 带锁改）只看
JOB.md，这里不抄；本节只写 caddie 自己的。

### 0.1 卡、BACKLOG 和定案
- 卡状态在 `<caddie-data>/BACKLOG.md`，按 JOB.md 用宿主 `backlog_edit.py` 带锁替换单行，不整份写。
  状态词：【未派】【未派·等 <卡号>】【在做】【待TF】【等你定·截止 MM-DD】【已关·日期·证据】；
  【待验收·等真机】已取消（H201）。改完对账：`python3 <caddie-data>/operations/backlog-check.py <caddie-data>/BACKLOG.md`。
- 推荐底图、洞屏画法、等待页样子之前，先对 C241 定案：永不出线条/矢量图；精细图 → 没有就用
  Garmin 底图 → 好了原地换（11-03 C369 推荐「先画矢量图」违反 C241 被 Jason 否）。写【等你定】前先
  grep BACKLOG 里的「定案」「拍板」，已定的不再问。
- 测试从规格来：规格是 `docs/product/2026-10-23-product-test-spec.md`（J/G 编号），按 JOB.md 开卡第 ② 项挂编号；
  找不到对应承诺就在报告写「缺规格」，先改规格。期望值按规格/文档里的数字手写进测试并附一行怎么得出，
  不拿被测函数生成。

### 0.2 clone 和本地测试
- 只从 GitHub clone 到 `<checkout>`，`git remote get-url origin` 必须是 github 地址，报告写基线 origin/main sha
  （10-28 C118：从本地目录 clone 的 origin 指向本地、main 过期，rebase 把已合并提交重放一遍）。
- 后端：`bash <par1025>/runtests.sh <checkout> <模块或测试名>`，单条命令、一次一个模块（它设 fixture 模式、
  用共享运行时；给多个模块或目录才排 heavy-lock，退出码 75 = 等锁超时，重跑同一条）。交回前跑
  `bash <par1025>/related-tests.sh <checkout>` 必须 rc 0：它跑 tests/ 里按文件名引用改动文件的全部模块
  （含 tests/acceptance 的源码钉子测试；10-29 #586/#587 漏跑这类模块，推上去 backend 才红）。全量见 §1.0。
- known-red：`tests/product/known-red/C16x.md` 里每条是产品与手写 golden 不一致、标了 `expectedFailure`
  （Swift 用 XCTExpectFailure）的断言。修卡 = 改产品让它真过，再去掉标记、把 md 那行标已修并写修复 commit；
  期望值不改，认为 golden 错了就写进报告、按 JOB.md 走决策。
- 先红要是行为红：只靠新类型/新函数不存在而编译失败不算红。先放新接口、函数体照抄旧行为，让新测试按
  断言失败，下一个提交再换成新行为（10-26 C30）。iOS 的先红在 Mac 上跑一次留原文。
- 改 SwiftUI 修饰符、函数名、identifier，或改/删/改名 Swift 函数前，先 `grep -rn "<旧写法或函数名>" tests/`
  找按源码钉它的测试一起改（保留原意图），并列进已跑测试（10-30 C162、11-02 C308）。断言源码文本的旧测试
  按 C58⑩ 换成行为测试或删掉，不新增。
- 改进程级全局状态（猴补丁 logging/类方法、全局 filter、环境变量、单例）：CI backend 是一个进程跑全部
  模块，逐模块全绿看不出污染（11-02 C317 PR CI 红 7 条）。要在同一进程里把触发它的模块和受影响模块
  一起跑，可用 `python -m tests.check_isolation`。
- 前端改动在本机只跑相关的 npm 测试；Swift 本机编译不了，见下一条和 §1 CI。
- iOS/手表卡交出前在 Mac 上实跑本卡相关 Swift 测试类到通过（11-02 C298④，C289 盲写两条像素测试在 Mac 上红）：
  `~/homeserver-data/bin/mac-swift-test <checkout> <ios|watch|both> [Target/Class[/test]]`（打包工作树、
  未提交改动也算，增量约 30 s）；在沙盒里调不到时用 `bash <par1025>/mac-test.sh <ios|watch|both> [...]`。
  连不上 Mac 先 `ssh mba-admin-lan` 查（Mac 的 DHCP 地址会变），改本机 ssh 配置里的地址。
- 新 mutant 只进 `tests/product/faults/<卡>/manifest.json`（格式同中央 `{"schema": 1, "records": [...]}`，
  patch 路径相对仓库根，id 全局唯一），中央 manifest 一行不动（10-30 C184 重复 id）；交出前跑
  `tests.test_fault_runner` 必须 OK。补丁用 `git diff` 从真实改动生成，逐个 `git apply --check`；
  报告里说 killed 要附 `run_faults.py --run --id <完整 id> --out <文件>` 输出里 `results[0].status` 原文（10-31 C219）。
- 给 WatchEventBridge.swift 的 payload 结构（WatchRoundStatePayload、WatchHoleMap、WatchHazard 等）加字段，
  同时登记 `mobile/contracts/watch_round_state.schema.json`（`tests.test_mobile_contracts` 逐字段比，11-02 C304）。
- 需要线上数据做副本实测：`docker exec <release> tar cf - -T <清单>` 只读拷到 `$TMPDIR`，只用副本；
  C372 全负载复现用 `<par1025>/C372-evidence/c372-load.sh`。

### 0.3 CI、Mac runner 和排障
- PR 上 iOS 的必需检查是 `native-quick`（C251，只编译 + 本卡相关测试）；带真模拟器截图的 fixture 只在合并前跑一次（§1.0、§9.1）。
- fixture 红：`gh run view <id> --log-failed` 找 ` error:`；超时类下载 `real-screenshots` 产物看 ios-app.log。
  已知偶发 C186、C213；其余先对 §9.4 假红表。
- Mac 自托管 runner caddie-mba、caddie-mba-2、caddie-mba-3（Jason 11-02「runner 不要沙盒 可以多开」）：
  都不套 sandbox-exec，每个 `.env` 有 `CADDIE_SIM_PREFIX=<名>`、用自己的模拟器。加 runner：gh 拿
  registration-token → 复制 runner 目录（去掉 .runner、.credentials*、_work、_diag、.env）→
  `config.sh --unattended --no-default-labels`。
- 线上整体变慢先看宿主 CPU steal（`vmstat 1 3` 的 st 列；11-03 全接口卡几分钟、steal 30–35%，不是 caddie 代码）。
- TestFlight 与部署互斥（§9.2）：部署归宿主 CD 后，CD 是否已接这条互斥未核，派 TF 前先核。

### 0.4 提交和交出
- 按逻辑分提交，英文 conventional 提交信息；作者、署名行、不推送、报告写法和交接宿主 CD 按 JOB.md。
- 推送前宿主跑 `ah scan` 逐个提交查改动行：`/home/<用户>/` 路径、`*.ts.net`/`.lan`/`.local` 主机名、私网 IP、
  回环主机加端口（`127.0.0.1:<端口>`、`localhost:<端口>`、`0.0.0.0:…`、`[::1]:…`）都会拦，哪怕 main 上同一行原来就有；
  后面提交改掉也没用。测试只要主机名就写不带端口的 `http://localhost/...`；改 workflow 里带
  `|| 'https://<tailnet 主机>'` 兜底的行时去掉兜底（repo 变量 `vars.AI_CADDIE_API_BASE_URL` 已设）。
  能调到 ah 就自查：`ah scan --repo-dir . --project caddie origin/main..HEAD`。已被历史中间提交拦住时，核 HEAD
  干净后 `git reset --soft <红测试提交>` 压成一个（核 tree 不变）再交。
- 报告、证据放 job 的 run 目录，不写进 clone、不提交进仓库（11-02 C304 r2）。

## 1. 测试

**本地**（项目台、Codex、复审子代理在 `<checkout>` 里跑；用共享只读运行时，不建 `.venv`、不 `uv sync`）：
只跑本卡相关的模块——卡的验收测试加改动直接影响的测试模块。**本地不跑全量 `discover`**：全量由 CI
`backend` 在每次推送和合并后的 main 上跑（约 4 分钟），本地全量要 30 分钟以上、要排整机锁，Codex 沙盒里还常卡住。

```bash
cd <checkout>
AI_CADDIE_DATA_MODE=fixture <caddie-data>/venvs/garmin-ai-caddie-ci/bin/python -m unittest \
  tests.acceptance.test_card_<N>_<name> <受影响的模块…> -v
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

### 1.0 测试与上线流程（C248，Jason 10-31 定；11-09 C402 起本节是唯一真身，DESK.md、COMMON.md 已并入本文件）

- 时长目标：①每次推送的快速反馈——服务端 ≤10 分钟；iOS「只编译 + 本卡相关测试」≤15 分钟（估值，实测有依据可调，调前报土土）；②合并前全量只跑 1 次，≤30 分钟，不在每轮返工里重复；③排队 ≤10 分钟，超了就减并发或减触发。
- 本地不跑后端全量（项目台、Codex、复审都不跑）：本地只跑本卡相关模块 + `<par1025>/related-tests.sh`（按文件名找引用改动文件的测试模块，见 §0.2）；全量交 PR 上的 CI `backend`，合并前必须绿；合并前全量由宿主 CD 跑一次。
- iOS：Codex 交回后先跑「只编译 + 本卡相关测试」原生 job，编译过了才送复审；带真模拟器截图的 fixture 只在合并前跑一次。
- 原生 mutant 不每轮实跑：复审只做静态判断，列出「可能假杀」的几条（被编译失败、崩溃或无关测试杀死，不是被断言杀死）；合并前只对这几条实跑一次。Python mutant 是秒级的，复审照常实跑。
- 复审限轮：B（挡）只限产品行为真错/回归、或本卡验收测试不咬旧代码；其它都是 N：本卡下一轮一起修或直接放弃，不另开卡（除非是独立的用户可见问题，Jason 11-03），不许把 N 升级成 B。同一张卡到第 3 轮还在返工，就停下来重拆卡或重定方案，不再一轮轮磨。
- 改同一个大文件的卡串行派（CurrentHoleView.swift、AICaddieApp.swift、StartRoundView.swift、LiveHoleComponents.swift、server_v2/main.py、ai_caddie/courses/course_prep.py 等）：开卡写清改哪些文件，和在途卡重叠就排队。

`topo_render` 的 forkserver 常驻约 46 MiB RSS（约 18–30 MiB PSS）是有意为之：按生产参数（`AI_CADDIE_TOPO_RENDER_PROCESSES=3`）停止后首个任务重启 forkserver、预导入 `topo_render` 的冷启动实测中位 3325 ms、最大 4828 ms，超过 1 秒阈值；因此空闲回收仍只回收 worker 池，避免把开销落到下一次预热渲染。

### 1.1 事件库 payload 迁移（C159）

新镜像里的入口是 `ops/migrate_mobile_event_payloads.py`。部署新代码并确认健康后，先对所有有日志的分区 dry-run：

```bash
C=aicaddie-release-<新rev>
docker exec "$C" sh -c '
  for R in /var/lib/ai-caddie/data/mobile_events /var/lib/ai-caddie/data/players/*/mobile_events; do
    [ -f "$R/events.jsonl" ] || continue
    echo "partition=$R"
    python /app/ops/migrate_mobile_event_payloads.py "$R"
  done
'
```

只对上面容器内 dry-run 输出中 `changed` 大于 0 的具体分区 apply；报告必须包含 `backup`。把这些输出中的 `root` 路径逐个填入下面命令，最后对同一批分区再 apply 一次，确认 `changed` 为 0：

```bash
docker exec "$C" python /app/ops/migrate_mobile_event_payloads.py /var/lib/ai-caddie/data/players/<player-dir>/mobile_events --apply
docker exec "$C" python /app/ops/migrate_mobile_event_payloads.py /var/lib/ai-caddie/data/players/<player-dir>/mobile_events --apply
```

apply 持有该分区的事件锁；同一分区的追加、读和 ACK 会等待锁完成。备份只留在原目录，权限为 0600。
若出现 `mobile_event_migration_intent_unrecoverable`，先停止该分区的写入。用下面命令找出仍在盘上的 intent，再保留对应 `events.jsonl.migration.json` 和 `.bak-*`，核对 intent 中的旧日志 sha、长度和 `backupPath`，由人工用备份恢复原日志权限与内容；无法核对时保留现场交项目台处理，不要删除日志。

```bash
docker exec "$C" find /var/lib/ai-caddie/data -name events.jsonl.migration.json -print
```

服务和 cron 的日志出口统一脱敏（含 root 传播及 lastResort）；`partition=player:<12 位 hex>` 保留供映射，玩家 id 和 Bearer 凭据仍脱敏。CI 的 `tests.check_isolation` 在每个测试模块清理后检查 `Logger.addHandler/callHandlers` 是否还原，无需登记模块。

告警的 `main:<hash>` 对应主分区，`player:<hash>` 对应 `players/<id>/mobile_events` 或 revision scanner 的 `players/<id>/scorecards`、`shots`、`snapshots`、`manual_rounds`、`corrections` 等目录；hash 是容器内分区**解析后的绝对目录路径**按 UTF-8 编码计算 SHA256 的前 12 位。下面命令在同一容器内列出标识与目录的对应关系（包括 intent 已消失的目录），按告警中的完整标识匹配；不要在宿主机路径上计算：

```bash
docker exec -i "$C" python - <<'PY'
import hashlib
from pathlib import Path
base = Path("/var/lib/ai-caddie/data")
for candidate in sorted({
    base / "mobile_events",
    *(base / "players").glob("*/mobile_events"),
    *(path for path in base.iterdir() if path.is_dir()),
    *(path for player in (base / "players").glob("*") if player.is_dir()
      for path in player.iterdir() if path.is_dir()),
}):
    if not candidate.is_dir():
        continue
    root = candidate.resolve()
    scope = "player" if root.parent.parent.name == "players" else "main"
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:12]
    print(f"{scope}:{digest} {root}")
PY
```

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

项目台实际跑 `bash <caddie-data>/tmp/deploy-sha.sh $SHA`（等 main CI 绿 → 下面 (a)(b) → §4 即时核对）。退出码：0=部署且 §4 即时核对全过（脚本已写 `deploy-verified` 行）；9=main CI 不绿；10=冻结；11=部署锁被占；12=日志末行不是 `result=ok` 或含 `: skipped (`（deploy.env 缺配置）；13=§4 核对不过；其他=部署脚本自己的失败码。**非 0 一律按失败处理**；BACKLOG 只在 `releases.tsv` 出现该 SHA 的 `deploy-verified` 行之后才标【已上线】。

```bash
set -euo pipefail
D=<caddie-data>
if [ -e "$D/release-freeze" ]; then                                      # §5：冻结时只放行修复 PR
  FIX=$(cut -f4 "$D/release-freeze")
  PR=$(gh api "repos/jasonhorga/garmin-ai-caddie/commits/$SHA/pulls" --jq '.[0].number')
  [ -n "$FIX" ] && [ "$FIX" = "$PR" ] || { cat "$D/release-freeze"; exit 1; }
fi
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
(umask 022; gh api "repos/jasonhorga/garmin-ai-caddie/tarball/$SHA" | tar -xz --strip-components=1 -C "$T")
mkdir -p "$D/deploy-logs"; L="$D/deploy-logs/$(date -u +%Y%m%dT%H%M%SZ)-${SHA:0:12}.log"
cd "$T"
set +e
env -i PATH="$PATH" HOME="$HOME" LANG=C.UTF-8 bash -c \
  'set -a; . "$0"; set +a; exec timeout 2280 ./ops/agenthub_deploy.py deploy "$1"' \
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

`exit=0` 且日志末行 `result=ok action=deploy revision=$SHA`，日志里**没有** `: skipped (`（`build skipped` 是镜像复用，正常）。再核对（`deploy-sha.sh` 已自动做下面四条并写 `deploy-verified`，手工跑时照做）：

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

合并后首次上线会连续构建 API 和 sync 两张依赖镜像，可能撞上 2280 秒
时限；超时直接重跑 `deploy $SHA`（依赖镜像已经按哈希打标签，会复用），或首次上线前先单独构建：
```bash
cd "$T"  # the SHA's tarball tree from §3.1
API_DEPS_HASH="$(python3 -c 'from ops.agenthub_deploy import api_dependency_hash; print(api_dependency_hash())')"
SYNC_DEPS_HASH="$(python3 -c 'from ops.agenthub_deploy import sync_dependency_hash, api_dependency_hash; print(sync_dependency_hash(api_dependency_hash()))')"
docker build -f Dockerfile.deps --label "ai.caddie.dependencies-hash=$API_DEPS_HASH" \
  -t "garmin-ai-caddie-deps:$API_DEPS_HASH" .
docker build -f Dockerfile.sync-deps --build-arg "API_IMAGE=garmin-ai-caddie-deps:$API_DEPS_HASH" \
  --label "ai.caddie.dependencies-hash=$SYNC_DEPS_HASH" \
  --label "ai.caddie.api-dependencies-hash=$API_DEPS_HASH" \
  -t "aicaddie-sync-deps:$SYNC_DEPS_HASH" .
```

| 情况 | 线上状态 | 项目台做什么 |
|---|---|---|
| `exit=2` | 没动 | 配置/参数错（多半是 `<deploy-env>`）；修好重跑，不冻结 |
| `exit=1` | 旧版本仍在服务 | 冻结；读日志 `reason=`，开卡修，修好走正常流程上线 |
| `exit=1` 且 `reason=not enough time left before AICADDIE_DEPLOY_DEADLINE_SECONDS` | 旧版本仍在服务 | 构建太慢（10-22 实例：构建缓存没了，`uv sync` 两次各 ~14 分钟，共 37 分钟）。镜像多半已建好进了缓存：查 `docker image inspect garmin-ai-caddie-api:$SHA`，在就直接重跑 `deploy $SHA`，不冻结；先查缓存为什么没了 |
| `exit=3` | 旧版本**没能确认恢复**，线上可能挂了 | 立刻回滚到上一个版本（下面命令）；仍不行跑 `./ops/agenthub_deploy.py up`；冻结；给 Jason 一句"线上挂了，正在恢复/已恢复" |
| 超时被杀 | 不确定 | 先 `curl` 本地 health：新容器在跑就重跑 `deploy $SHA`（只做核对）；没容器在服务就 `rollback <上一个 sha>` |
| `exit=0` 但 §4 有一项不对，或上线后发现回归 | 新版本在服务 | 回滚到上一个版本；冻结 |
| 回滚 `exit=1`，目标旧容器自己坏了（例：没了网络挂接、起不来） | 当前版本仍在服务 | 不手工修容器（`docker network connect` 等不在项目台授权里）。脚本会在启动已有容器前自己接回配置的网络；仍不行就对目标 revision 跑 `deploy $SHA`（镜像在就不构建，会删掉同名停止的旧容器、按配置重建） |

上一个版本的 sha（停掉的旧容器带 revision 标签）：

```bash
docker ps -a --filter name=aicaddie-release- \
  --format '{{.Names}}\t{{.Label "ai.caddie.source-revision"}}\t{{.Status}}'
```

回滚（在 `$T` 或任一同版本导出树里跑，环境同 §3.1；只启停已有容器，不构建、不删东西）：

```bash
cd "$T"
env -i PATH="$PATH" HOME="$HOME" LANG=C.UTF-8 bash -c \
  'set -a; . "$0"; set +a; exec timeout 2280 ./ops/agenthub_deploy.py rollback "$1"' \
  <caddie-data>/secrets/deploy.env "$PREV"
```

回滚后按 §4 用 `$PREV` 核对。注意：`git diff --name-only $PREV $SHA -- migrations/` 非空时，
回滚只换代码、不回退库结构；新库结构和旧代码不兼容就改为向前修。用快照
`pg_restore --clean` 恢复数据库会丢掉快照之后写入的数据，**要 Jason 点头**。
回滚到旧镜像时，新版 `topo-vN` 缓存可能被 retention 当作过期删除；缓存可再生，不影响服务数据。

### C62 会话存储回滚注意

C62 已删除旧的 flat 会话文件（owner 和每个家庭成员各一份）。回滚到 C62 之前的镜像前，先停同步，再把 owner 和**所有成员**当前代的两个文件拷回旧路径（漏了成员 = 成员会话全丢、要重新绑定）：

```bash
ROOT="<private-root>"
for TOKEN_DIR in "$ROOT/.garmin_tokens" "$ROOT"/data/players/*/.garmin_tokens; do
  [ -f "$TOKEN_DIR/current" ] || continue
  GENERATION="$(cat "$TOKEN_DIR/current")"
  install -m 600 "$TOKEN_DIR/generations/$GENERATION/web_cookie.txt" "$TOKEN_DIR/web_cookie.txt"
  install -m 600 "$TOKEN_DIR/generations/$GENERATION/csrf.txt" "$TOKEN_DIR/csrf.txt"
done
```

旧镜像恢复后、再次部署 C62 或更新版本前，删除指针文件，让新代码按旧布局读取并在首次写入时重新迁移：

```bash
ROOT="<private-root>"
for TOKEN_DIR in "$ROOT/.garmin_tokens" "$ROOT"/data/players/*/.garmin_tokens; do
  rm -f "$TOKEN_DIR/current"
done
```

**冻结**：

```bash
printf '%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$SHA" "<一句原因>" > <caddie-data>/release-freeze
```

冻结期间不合并、不上线、不出包（修复本身那一张 PR 除外）。修复 PR 上线：合并后按 §3.1 正常上线它的
main 提交，只是开头的冻结检查改为"冻结原因写明的修复 PR 就是这一张"——项目台先把修复 PR 号写进
`release-freeze` 第 4 列，再上线。修复上线并按 §4 确认后，项目台
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
- 增删 Funnel/公网路由，改生产端口、卷、网络的定义（部署脚本在启动已有容器前把它接回本来配置的网络不算"改网络"，
  这是脚本内的恢复；项目台不手工敲 `docker network`/`docker update` 修容器——缺什么恢复能力就开卡加进脚本）。
- 合并被自动模式分类器拦下时：请他回一句"合并 caddie#<PR>"，然后项目台自己合。

不用问他：审查、合并、上线、确认、按 §5 回滚、冻结与解冻、重跑 CI、拉 CI 产物、内部 TestFlight 上传（§6，Jason 10-22 定）。
上线后只告诉他"线上变了什么"；需要他做事时只说"要你做什么"，各一句。

## 8. 等待和卡住

不再有 AgentHub 的"卡住提醒"。项目台每次等东西（CI、Codex、上线脚本、TestFlight）都用
后台任务或有上限的 until 循环，超时设该活正常耗时的约 2 倍（CI 10 分钟、native 45 分钟、
上线 40 分钟、TestFlight 60 分钟）；超时 = 卡住，先查为什么，不直接重试。

## 9. 排队规矩（给派卡脚本强制执行；11-03 从项目台 DESK.md 收拢，DESK.md 已于 C402 撤掉）

每张卡派出前、推送前、合并前都按下面判断。机器可读的判据写在每条末尾【判据】里，脚本照它拦。

### 9.1 并发上限
- **Mac（mba-admin-lan，10 核）上同时跑的 Codex 线 ≤3 条**（`operations/mac-codex.sh`，含服务端卡；Jason 11-02 定「尽量都在 Mac 跑」）。iOS/手表卡在途（已派到合并）也 ≤3 条。【判据】`ps` 里 `codex-mac/run.sh <lane>` 进程数 <3 才派。
- **Mac 上托管 fixture 在跑时，不同时重跑别的 iOS 检查、不再派 iOS Codex**（负载会把时序测试打红，见 9.4 C337）。【判据】native-mobile.yml `fixture_mode=true` 的 run 在 in_progress 时，不派 iOS 卡、不 rerun iOS job。
- **原生 mutant 实跑全仓同时 ≤2**，且只给已开 PR 的分支派（backend CI 只在 PR 上跑，没 PR 会白等超时，10-30 C236）。
- **fixture 只在合并前跑 1 次**（C248）：每轮返工只跑 native-quick/backend；iOS 复审过了才派 fixture。
- **排队 ≤10 分钟**：超了先减并发或减触发，不加 runner。

### 9.2 同文件串行
- 改同一个大文件的卡串行派，开卡时写清改哪些文件，和在途卡重叠就排队：
  `mobile/ios/AICaddie/Views/CurrentHoleView.swift`、`mobile/ios/AICaddie/AICaddieApp.swift`、`StartRoundView.swift`、`LiveHoleComponents.swift`、`server_v2/main.py`、`ai_caddie/courses/course_prep.py`、`.github/workflows/native-mobile.yml`、`tests/test_mobile_contracts.py`、`.github/scripts/check_native_fixture_dns.py`。
  【判据】新卡「改动文件」与任一【在做】卡的「改动文件」交集非空 → 状态写【未派·等 <卡号>】。
- **两个 PR 改同一 workflow/契约测试**：后合的先 rebase 到新 main，让 backend 再绿一次再合（10-31 C252×C236 各自绿、合起来 main 红，挡了部署）。
- **TestFlight 与部署互斥**：TF dispatch 时钉住当前生产 revision，TF 跑完前不部署；用后台「等 TF 完 → deploy-sha.sh」串起来。
- 新 mutant 只进 `tests/product/faults/<卡>/manifest.json`，中央 manifest 不动；`run_faults.py --check` 查 HEAD，合并/改补丁后先提交再查。

### 9.3 返工轮数
- 复审 B（挡）只限产品行为真错/回归、或本卡验收测试不咬旧代码；其它都是 N，不升级成 B。
- **复审 N 项要么在本卡下一轮一起修、要么直接放弃；不另开卡，除非是独立的用户可见问题**（Jason 11-03 经土土）。只补测试/mutant、CI 与工具小项、代码整洁一律放弃；放弃的在复审底稿里写一句理由即可。【判据】新开卡的来源若是 `review-<卡>-rN.md` 的 N 项，描述里必须写出用户可见的现象（不是「无测试守」「mutant 存活」），否则不开。
- 同一张卡到第 3 轮还在返工 → 停下重拆卡或重定方案。

### 9.4 已知假红（先对号，再决定重跑还是查代码）
| 现象 | 判断 | 处理 |
|---|---|---|
| iOS PR 检查红、失败用例每次不同、Mac 负载高（C337，11-02 负载 362/10 核） | Mac 超载时序假红 | `ssh mba-admin-lan uptime`；用例不重叠 → 重跑失败 job；同一用例反复红才查代码 |
| `C33PackageTests.testPendingGeometryFailureReschedulesWithBackoff` 红（C347 #713，负载约 100） | 负载时序 | 重跑 |
| `LiveRoundAppModelTests.testReenteringStartKeepsTheExistingProgressTimer`（数 yield 等计时器） | 调度时序（C287） | 重跑；C287 改成等确定信号 |
| 托管 UI 测试打字后等按钮 5 s 超时（PrepDegradation/RealFlow） | 托管机查询慢（C245/C347） | 重跑；C347 放宽到 15 s |
| `tests.product.test_c154b` J42 计时测试负载下红，main 同样红 | 墙钟阈值吃负载（C360） | 本机负载低时重跑；CI backend 为准 |
| fixture 某分片贴着/超过时限，日志里多次 `App animations complete notification not received`（每次 60 s） | **不是假红**：app 不空闲（C332 根因：LiveGreenEntryButton 重写 exclusion 成更新环） | 查产品，不放宽时限 |
| TF 预检 `OpenTimeout` | Funnel 公网入口断 | `python3 ~/homeserver-data/funnel-watch/funnel_watch.py --dry-run`，恢复后重出 |
| TF 预检失败、刚部署过 | 部署改了 revision + 冷缓存（TF 钉旧 revision） | 等 TF 完再部署，见 9.2 |
| 本地推送脚本真实地形探针 60 s 超时（负载 19 下 main 47 s） | 本机负载（C344） | 以 PR CI backend 为准；本地不跑后端全量 |
| main backend 红、两个刚合的 PR 改了同一 workflow/契约测试 | 合并冲突（C252×C236） | 开修复 PR，部署用修好后的 main sha |
| DNS 门把测试桩的 -1200/-1001 报成泄漏 | 门改错（C354）：桩错误不带 URL，不算泄漏 | 改门，8 份 CI 日志条数须与 main 一致 |
| Mac Codex 「Reconnecting… waiting for network」 | mac-codex.sh 过 2 小时被后台上限杀、ssh -R 断（Mac 上 codex 仍在跑） | 不重派，`caddie-console-mac-reattach.sh <lane> <原端口> <clone>` 重接 |
| 推送脚本报 No such file（/tmp/caddie-console-*.sh） | 容器重启清空 /tmp | `bash console-scripts/install.sh`（真身在 garmin-ai-caddie-data/console-scripts） |

## 10. 不做（11-09 C402 从 DESK.md、CODEX-NOTE.md 收拢；跨项目的不做见 JOB.md）

- 不把子代理、复审员或别的会话说的「已杀/已过/main 也红」当事实：自己在 main 和本卡基线上各跑一次再下结论。
- 取长行尾部不用 `rev` 管道（11-02：util-linux 2.39.3 的 rev 在 C locale 下遇非 ASCII 字节死循环、100% CPU，
  超时被杀后变孤儿空转 4 小时）；用 awk substr 或 python。
- rebase 解冲突不对整份文件用 `git checkout --theirs/--ours`：会连带丢掉对面不冲突的改动（10-30 C204 丢了
  main 的 J5.9 取舍记录）。只改冲突块，解完 `git diff origin/main -- <文件>` 核只剩本卡改动。
- 查容器环境变量不 grep：会把令牌打进上下文。线上数据只读拷副本用（§0.2），子代理不直接读生产。
- workflow 不用 YAML 合并键 `<<: *anchor`（11-04 C372）：GitHub Actions 认锚点/别名、不认合并键，整份
  native-mobile.yml 解析失败、PR 上 native-quick 不出现（本地 PyYAML 认）；`tests.test_ci_workflow` 有守卫。
- runner、模拟器、进程归属不按前缀匹配，按确切名字：caddie-mba 是 caddie-mba-2/-3 的前缀，按 `<前缀>-`
  匹配会误关别的 runner 正在用的模拟器（C372 fixture 踩过）。
- 不远程重启 Mac（caddie-mba）：开着 FileVault、无自动登录，远程重启停在开机密码界面回不来，只能请 Jason
  在机器前做（11-03 C333）。Mac 卡时 ssh 会断几分钟，诊断用 Mac 本地 nohup 采样写文件。
- Mac 上 Tailscale 保持关着，不拉起（11-02 拉起后 DNS 排在代理前面，Mac 连不上 GitHub，3 台 runner 全 offline）。
- 两条不同视图/不同合成路径渲出的同一画面，不用 `XCTAssertEqual` 逐字节比像素（Mac 上单通道差 1 就红，11-02 C289）；
  用 WatchDesignSnapshotTests 的 `assertPixelsMatch(actual, expected, maxChannelDelta: 2, msg)`，同一路径前后两次渲染才完全相等。
- mutant 补丁不手写 hunk 头、不混进 apply_patch 指令（`*** Add File:` 行）和本机绝对路径：文件以 `diff --git` 开头
  （10-30 C187、10-31 C219）。
- Swift 不凭记忆写，交出前逐条自查（CI 上踩过）：
  - `XCTAssert*(await …)` 不能编译，先 `let x = await …` 再断言；`@ViewBuilder` 函数体里不写「声明后接 if/else 赋值」，挪进普通辅助函数。
  - 用到的类型名、初始化器参数名先 grep 现有定义；改访问级别或新调用方法/属性时，签名里每个类型（参数、返回值、
    泛型、关联值）的访问级别 ≥ 方法本身（10-26 C30）。
  - 被调函数带 `throws` 写 `try`；断言里引用的局部变量在当前测试函数里有声明；存储闭包 `@escaping`（10-29 C134）。
  - 隐式返回的函数/计算属性/闭包前面加了语句，就把表达式写成 `return …`；测试函数里新写 `try` 要给签名加
    `throws`（10-30 #604/#605）。

<!-- agenthub:collab -->
## AgentHub 协作

- 派活：`ah codex say caddie "<话>"`（或 `--file 卡.md`），打出 `TURN <id> 预计 HH:MM`。
- 等：后台跑 `ah codex wait caddie`（最多 110 分钟）；`ah codex wait caddie --turn <id>` 等指定轮，`ah codex status caddie --turn <id>` 查指定轮；不传 `--turn` 取该 lane 最新轮。

| wait 退出码 | 含义与处理 |
|---|---|
| 0 | 回话已打出；按卡复审 diff 和回话。 |
| 1 | 本轮异常（失败或失联）；看输出和指定轮 status，查明原因再续派。 |
| 2 | 项目未登记、参数或记录读取错误；修正登记、参数或记录后重跑。 |
| 3 | 等待超时，仍在跑；对同一轮再起一次 wait。 |
| 4 | 没有本轮记录；核对项目、lane、TURN，确认 say 成功。 |
| 5 | 已完成但回话文件缺失或为空（或无法读取）；查登记 data_dir 下的 codex-turns/<id>.md 和 runner 日志，补齐回话再复审。 |

- 兜底：say 之后 `send_later` 2 小时，醒来先查指定轮 status（防 wait 被 /clear 或重启带走）；wait 退出不影响 runner，可重新等同一轮。
- 同一项目/lane 上一轮没完不能再 say；独立卡并行用 `ah codex say caddie --lane <卡> --file 卡.md`，wait/status 也带同一 `--lane <卡>`。
- CI 等待设上限（正常耗时约 2 倍），超时先查原因，不盲目重试。
- 推送之前在待推送仓库运行 `ah scan --project caddie <base>..<head>`；异地加 `--repo-dir <仓库>`，正文加 `--body-file <文件>`；仅退出 0 才推（1 = 命中，2 = 扫描无法完成）。
- Codex 回话控制在一页以内。
<!-- agenthub:collab:end -->
