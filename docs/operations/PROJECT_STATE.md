# Garmin AI Caddie Project State

> This is the short, durable execution state for the current product push.
> Long reviews and historical plans remain reference material; they are not the
> live task queue.

**Updated:** 2026-09-09 UTC
**Branch:** `integration/v2` (GitHub default; current product source tip
`b9ff8b9d`; deployed backend tip
`6d130528c366df62a6050f6c23b5d885fbe56e55`; MAP1 product-code tip
`5628cc6db31dde310ee5691c3683f750e51b27d8`; reconciliation merge
`1775d87a7a3eb2ac3c879bb81f07406ef28dd760`)
**Source baseline:** `a44f1c9f9f5b92b280e85e93e15e1094c7ff85a6` (the Build 53
feedback changes are now included in the canonical source and Build 54; the
backend runtime is the newer descendant `6d130528` of the earlier
`325cc2f3` candidate; historical TestFlight build 47/48/49/50/51/52/53
sources remain recorded below)
**Release rule:** the gates are ordered, not circular:
`canonical source -> source/Native CI and backend preflight -> automatic fresh
internal TestFlight build/upload (the workflow performs signing) -> Apple
processing/status check -> stop and hand off for physical iPhone/Watch evidence
-> Phase 6 readiness -> owner approval -> external distribution or production
promotion`. Once the required test gates are green, this internal-only upload
does not require another per-upload chat confirmation. It keeps
`external_distribution=false` and does not authorize production. An
owner-approved `test_environment_upload=true` is the permitted internal-only
fallback when the authenticated readiness shape, health schema, and exact
backend revision pass but non-production readiness checks are degraded; it
never closes the physical-device gate or promotes the app. A standalone
artifact-only IPA is an optional historical diagnostic, not a release gate or a
prerequisite for the upload workflow.

## Current Work Summary

- **Backend candidate:** Public revision
  `6d130528c366df62a6050f6c23b5d885fbe56e55` is running in healthy container
  `aicaddie-release-6d130528-candidate-20260909`, image
  `garmin-ai-caddie-api:6d130528-candidate-20260909` with image digest
  `sha256:fcc5ee95dd6c89c837d326d435c7646ed39a9b6b1607c20e59957c961cf60647`.
  Public `/api/v2/health` reports `status=ok` and that
  exact revision. This revision is a descendant of the earlier `325cc2f3`
  candidate, so the runtime is not a rollback; it includes the earlier backend
  fixes plus the later topo rendering and snapshot-scope changes. The deployment
  record is under
  `/home/jason/garmin-ai-caddie-data/operations/backend-deploy-20260909-snapshot-exclusion`.
- **Snapshot geometry remediation (2026-09-09):** Commits `ca3f505c` and
  `6d130528` make durable manifests/writes and portable exports omit the
  reproducible shared `output/prodgeometry*` trees while retaining
  `geometryDependencies` metadata; imports still accept legacy archives. The
  exact allow-list and verification records are under
  `/home/jason/garmin-ai-caddie-data/cleanup-manifests/20260909-snapshot-geometry-exclusion`.
  Sixteen legacy geometry directories were removed from nine retained snapshots,
  releasing `34,241,567,932` bytes; raw Garmin data, manifests, normalized
  history, and top-level shared geometry remain. Post-cleanup checks found zero
  snapshot geometry directories, `snapshotId=null`, and no cross-snapshot or
  external references. The 10:37 UTC scheduled sync then completed with 491
  scorecards/shots, 112/112 course references, and no new snapshot geometry.
- **Sync image incident and recovery (2026-09-07):** The hourly cron is a
  one-shot `docker run --rm`, so a persistent `aicaddie-sync` container is not
  expected in `docker ps` between runs. At 23:37, 00:37, and 01:37 UTC it
  correctly refused the missing exact-revision image instead of using stale
  `latest` (which still points to the 2026-08-21 `6a6080c` image). The rebuilt
  image `aicaddie-sync:caf3afad55e31c3b98a378e0d1cf4c2c5fb5a737` was created at
  01:41 UTC, has image ID
  `sha256:81799662dda5c81fe17cfb52e1ccba8edb7bbcd7856c969d31ad39d1954c3615`,
  and its source label matches the API image while its key code hashes match
  the API image and canonical checkout. A
  controlled run at 02:06 UTC exited 0: Garmin auth succeeded, 490 rounds,
  490 scorecards, 490 shot sets, 112/112 course references, and 4 new rounds
  were saved; the shared API health endpoint remained `ok` at the same
  revision. The repository helper fix is committed as `0fd1ffc2` and Source CI
  run `34079053241` passed backend, frontend, and Docker smoke jobs. The next
  unattended cron run at 02:37 UTC also used the exact image and completed
  successfully with the same 490 rounds and 112/112 course references (0 new
  rounds), confirming the automatic schedule is recovered.
- **Garmin login verification fix:** Garmin CN's gateway now requires the
  browser same-origin fetch metadata on authenticated API calls. Commit
  `caf3afad` sends `Sec-Fetch-Site: same-origin`, `Sec-Fetch-Mode: cors`, and
  `Sec-Fetch-Dest: empty`; the controlled comparison changed the same valid
  Cookie/CSRF request from HTTP 403 to 200, and summary/bag reads succeeded.
  Source CI run `34043175968` passed backend, frontend, and Docker jobs.
- **Source CI:** GitHub run `33680857200` at `d189b3b4` passed backend (2,047
  tests, 13 skips), frontend component/lint/build/visual smoke, and Docker
  API/sync smoke jobs.
- **Current-head source CI:** GitHub run `33978122703` at `d06c97c2` passed the
  backend, frontend visual smoke, and Docker jobs. The commits after the P2
  product tip are documentation-only, so this confirms the canonical checkout
  remains green without changing the app binary.
- **MAP1 source CI:** GitHub run `34021727402` at `c11ddf33` passed backend,
  frontend component/lint/build/visual smoke, and Docker API/sync smoke jobs.
- **Release-handoff documentation CI:** GitHub run `34013149549` at
  `6519065d` passed backend, frontend (component tests, lint, build, and visual
  smoke), and Docker API/sync smoke jobs. This was a documentation-only push;
  no product binary or release side effect changed.
- **Native live evidence:** Native Mobile CI run `33680501425` at mobile
  source `c5902a96` passed all 38 evidence steps. iOS and Watch manifests are
  `passed`; the live iOS journey covered no-GPS manual search/start, map and
  caddie restore, review editing, and the 7 TeeSelection UI tests. Watch tests
  (329) and 22 runtime screenshots also passed. The mobile tree is identical
  between `c5902a96` and the current `d189b3b4` (the latter adds only Python
  contract coverage). Native artifact `9868217071` has digest
  `sha256:70183f3155e434c617b5d53590be8857e6aab791b17dc518c99af04f46aa0415`.
- **MAP1 Native live evidence:** Native Mobile CI run `34021862658` at
  `c11ddf33` passed all 38 evidence steps, including the live iOS no-GPS
  start/map/caddie journey, Touch Target and review precision flows, Watch
  tests, runtime screenshots, and secret/artifact scans.
- **Latest Native live evidence:** Native Mobile CI run `34159418409` at
  `8c378997694d5183e440d85518963131ff704c56` passed all 38 evidence steps.
  The real iOS journey passed the downloaded-course/offline new-round test,
  no-GPS manual search/start, live course preflight, screenshot/video capture,
  and secret scans; Watch build, runtime screenshots, and evidence scans also
  passed. It used backend revision
  `caf3afad55e31c3b98a378e0d1cf4c2c5fb5a737`.
- **Current Native live evidence:** Native Mobile CI run `34316964148` at
  source `a44f1c9f9f5b92b280e85e93e15e1094c7ff85a6` passed every required
  step: iOS tests, SwiftJCS boundaries, design snapshots, live course
  preflight, real iOS XCUITest/screenshots/video, Watch tests and runtime
  screenshots, and all secret/evidence scans. Its evidence manifest records
  `dataMode=live` and `ios.status=watch.status=passed`; the live API was pinned
  to backend revision `325cc2f33aa39ac18bbcac9bc2e87c6f15a89384`.
- **Current source CI:** GitHub CI run `34316491467` at `a44f1c9f` passed
  backend, frontend, and Docker jobs.
- **TestFlight build 47:** iOS TestFlight CD run `33686521143` built and
  uploaded `0.1.0 (47)` from `d189b3b4`. Apple finished processing it;
  provenance records `uploadRequested=true`, `uploadCompleted=true`, and
  `uploadToTestflight=true`. IPA SHA-256 is
  `19936b224428aa2e740fc7b277f26b80f91c52b44c567b75cbe310349db4f3ad`;
  artifact `AICaddie-ipa` ID `9868598629` has ZIP digest
  `sha256:19865fc1d6190c5e58e882f63062b39b1cebd00d730c3b656c8e54ed7fdbe82b`.
- **Historical artifact-only build 48 (diagnostic only):** iOS TestFlight CD run
  `33977405908` built and signed `0.1.0 (48)` from canonical tip `8e13623d`.
  The IPA SHA-256 is
  `479dc3e3298e3f8527458752f7a33e2ef22d11d79176047be075d556d24ceafc`;
  GitHub artifact `AICaddie-ipa` ID `9972807230` has ZIP digest
  `sha256:5422bcf511eb3933264dbd7d31c0ff2a865eddc8a2feb114cbb49cb1bcf50829`.
  Its provenance records `uploadRequested=false`, `uploadCompleted=false`,
  and `uploadToTestflight=false`; build 48 is not in App Store Connect. It was
  useful only for package/signing diagnostics; do not repeat a standalone IPA
  build when no upload is authorized.
- **TestFlight build 48 (historical internal candidate):** iOS TestFlight CD run
  `34012329292` built from canonical tip `b4aa9a71832e03b5620e13178ba299902a8ebd08`
  with `test_environment_upload=true`, `upload_to_testflight=true`, and
  `external_distribution=false`. Apple processed `0.1.0 (48)` successfully.
  The IPA SHA-256 is
  `1b1febfdb3919694c1dbf92e818f97f29f65d931cccd0eb7672e31b97276abef`;
  GitHub artifact `AICaddie-ipa` ID `9982919017` has ZIP digest
  `sha256:baf955c01a7aacd55a4499945a625e83ecdb929a15c5050c2274ff5089b90528`.
  Provenance records `uploadRequested=true`, `uploadCompleted=true`, and
  `uploadToTestflight=true`, with API origin
  `https://caddie.taile36706.ts.net` and backend revision
  `c16488911038d7e5b47ec310d1aaf05ca29950df`.
- **TestFlight build 50 (historical auth-state candidate):** iOS TestFlight CD
  run `34040432333` built and uploaded `0.1.0 (50)` from
  `4bca0f2ed13d3db93474a32137694d04b734c066`; Apple processed it successfully.
  Its provenance used API origin `https://caddie.taile36706.ts.net` but the
  pre-fix backend revision `ce4d41f055a3923ce44ee48bdab9131bb4d1fb74`.
- **TestFlight build 51 (current internal candidate):** iOS TestFlight CD run
  `34048458619` built and uploaded `0.1.0 (51)` from
  `caf3afad55e31c3b98a378e0d1cf4c2c5fb5a737`, with
  `test_environment_upload=true`, `upload_to_testflight=true`, and
  `external_distribution=false`. Fastlane waited for and reported Apple
  processing complete. IPA SHA-256 is
  `28296cd7c146f344939e910d87ffc16a04c7803dbf95d773a405f8010ff3dcf5`;
  GitHub artifact `AICaddie-ipa` ID `9993936191` has ZIP digest
  `sha256:e53c7d8eac7de0d116d9076b3733658eb00e019bc7748ed9cd62f28f857b5c62`.
  Provenance binds API origin `https://caddie.taile36706.ts.net` and backend
  revision `caf3afad55e31c3b98a378e0d1cf4c2c5fb5a737`.
- **TestFlight build 52 (superseded internal candidate):** The first CD attempt
  `34162509901` signed an IPA but stopped before Apple upload because the hosted
  macOS runner could not resolve the Tailscale split-DNS origin. The retry
  `34162939105` passed backend preflight, uploaded, and waited for Apple
  processing from source `8c378997694d5183e440d85518963131ff704c56`. Provenance
  binds the public quick-tunnel origin
  `https://suggests-kilometers-normal-insertion.trycloudflare.com` to backend
  revision `caf3afad55e31c3b98a378e0d1cf4c2c5fb5a737`; IPA SHA-256 is
  `4ad8c13aac3d2fb3c86ee87dc28804d4cc73ca2eaa0a824feb934f25c491b249`.
  Read-only App Store Connect run `34163600353` reports `0.1.0 (52)`, id
  `2f0aa6f1-033f-4917-917c-9697c46ce9ca`, `VALID`, `expired=false`,
  `internalState=IN_BETA_TESTING`, `externalState=READY_FOR_BETA_SUBMISSION`,
  `usesNonExemptEncryption=false`, arm64 processed bundle, and inclusion in
  the existing internal `Jason's friends` all-builds group. No external group,
  Beta Review submission, or production promotion was performed. The quick
  tunnel remains running for physical validation and must stay alive while
  the current internal build is being tested.
- **TestFlight build 53 (historical internal candidate):** iOS TestFlight CD run
  `34231106418` built and uploaded from source
  `f24a22ddcdf41b3abc1f7907a71f9201110f94ce` with
  `test_environment_upload=true`, `upload_to_testflight=true`, and
  `external_distribution=false`. Apple processed `0.1.0 (53)` successfully.
  The provenance binds API origin
  `https://suggests-kilometers-normal-insertion.trycloudflare.com` to backend
  revision `f363872f3af631edf0bcae5f9ab3e2c9fe28e0bb`. IPA SHA-256 is
  `fe4f6078dd7b0560b5f755c14d2133af13ca1a272562a064995c3d6ec2c8e23f5`;
  GitHub artifact `AICaddie-ipa` ID `10058141615` has ZIP digest
  `sha256:19188deaf5e25097b0b5bd8bd6afb3bcf15bdd5536430ccf4add49320512e0ed`.
  Read-only App Store Connect run `34232120285` reports build ID
  `318e7835-7c6c-42d9-a7d7-5c26bd90c628`, `VALID`, `expired=false`,
  `internalState=IN_BETA_TESTING`, `externalState=READY_FOR_BETA_SUBMISSION`,
  processed arm64 bundle `com.ai-caddie.mobile`, and inclusion in the existing
  internal `Jason's friends` all-builds group. The external `Private Trial`
  group was not changed; no Beta Review submission, external distribution, or
  production promotion was performed.
- **TestFlight build 54 (current internal candidate):** iOS TestFlight CD run
  `34323088795` built and uploaded `0.1.0 (54)` from source
  `a44f1c9f9f5b92b280e85e93e15e1094c7ff85a6` with
  `test_environment_upload=true`, `upload_to_testflight=true`, and
  `external_distribution=false`. Provenance binds the public quick-tunnel
  origin to backend revision
  `325cc2f33aa39ac18bbcac9bc2e87c6f15a89384`, records
  `uploadRequested=true`, `uploadCompleted=true`, and
  `uploadToTestflight=true`, and gives IPA SHA-256
  `5243bd6ceb18128603b69156bb5c858ee5cc5aa92da1a7a51bf20975cea68ceb`.
  Read-only App Store Connect run `34324271971` reports build ID
  `6f6bfd9a-617a-4dbc-878e-ebbf21cb38f1`, `VALID`, `expired=false`,
  `internalState=IN_BETA_TESTING`, `externalState=READY_FOR_BETA_SUBMISSION`,
  processed arm64 bundle `com.ai-caddie.mobile`, and inclusion in the existing
  internal `Jason's friends` all-builds group. `Private Trial` remains
  unchanged and does not contain build 54; no external distribution, Beta
  Review submission, or production promotion was performed.
- **TestFlight build 49 (historical internal candidate):** iOS TestFlight CD run
  `34025628804` built from canonical tip
  `c11ddf33704dffbe99c4978e54bb269c7be4002b` with
  `test_environment_upload=true`, `upload_to_testflight=true`, and
  `external_distribution=false`. Apple processed `0.1.0 (49)` successfully.
  The IPA SHA-256 is
  `e6a4feb75aa97c3b845451a9539aa6bbfdfcb0e221dd03f0ef45138a51890746`;
  GitHub artifact `AICaddie-ipa` ID `9987051978` has ZIP digest
  `sha256:561057cdf94da9f0b1434dba4dfad34ccb8c21e98403cf9174331ea8883d33fd`.
  Provenance records `uploadRequested=true`, `uploadCompleted=true`, and
  `uploadToTestflight=true`, with API origin
  `https://caddie.taile36706.ts.net` and backend revision
  `c16488911038d7e5b47ec310d1aaf05ca29950df`.
- **Apple status for build 48:** Read-only App Store Connect run
  `34012813699` reports build `0.1.0 (48)`, id
  `a4dc0005-bfda-4b52-a208-391267dc2a31`, `VALID`, `expired=false`,
  `internalState=IN_BETA_TESTING`, `externalState=READY_FOR_BETA_SUBMISSION`,
  and `usesNonExemptEncryption=false`. The existing internal group
  `Jason's friends` is `internal=true`, `allBuilds=true`, and includes build
  48. The external `Private Trial` group does not include build 48. The same
  read-only run returned processed app bundle `com.ai-caddie.mobile` with
  arm64 architecture. No external distribution, Beta Review submission, or
  group mutation was performed.
- **Apple status for build 49:** Read-only App Store Connect run
  `34026097416` reports build `0.1.0 (49)`, id
  `628b9237-402e-4ad2-81d6-a91cd9e00564`, `VALID`, `expired=false`,
  `internalState=IN_BETA_TESTING`, `externalState=READY_FOR_BETA_SUBMISSION`,
  and `usesNonExemptEncryption=false`. The existing internal group
  `Jason's friends` is `internal=true`, `allBuilds=true`, and includes build
  49. The external `Private Trial` group does not include build 49. No
  external distribution, Beta Review submission, or group mutation was
  performed.
- **Apple status for build 51:** Read-only TestFlight workflow run
  `34048981151` reports build `0.1.0 (51)`, id
  `065aa316-6be1-4db7-9ae6-2ccf764b3166`, `VALID`, `expired=false`,
  `internalState=IN_BETA_TESTING`, `externalState=READY_FOR_BETA_SUBMISSION`,
  and `usesNonExemptEncryption=false`. The existing internal group
  `Jason's friends` is `internal=true`, `allBuilds=true`, and includes build
  51. The external `Private Trial` group was not changed and does not include
  build 51. The processed app bundle is `com.ai-caddie.mobile`/`arm64`.
- **Artifact diagnostics:** Exact IPA run `33687517758` passed iOS/Watch
  codesign, bundle/profile/team/version/build binding, profile expiry, and arm
  architecture checks. These checks do not substitute for a physical install.
- **Phase 6 release audit:** Run `33687800258` passed provenance, backend,
  signing, and API checks, while the overall result correctly remains
  `incomplete`: external Beta Review, target tester coverage, and physical
  iPhone/Watch installation are unconfirmed. `install_verified` remains
  `false` by design.
- **Internal upload attempt `34011709040`:** archive/export/sign completed on
  the macOS runner, but the strict Fastlane backend preflight rejected the
  authenticated `degraded` readiness state before calling Apple upload. No
  TestFlight build was created by this run; its IPA artifact was retained for
  diagnostics. The internal hardware-validation retry uses the explicit
  `test_environment_upload=true` path and still enforces health schema,
  authenticated readiness shape, and exact backend revision.
- **Remaining release gate:** Current TestFlight build 54 is processed and
  visible through the existing internal all-builds group. Physical
  iPhone/paired Watch installation, fresh Garmin reconnect/sync behavior,
  first-launch behavior, held-loupe interaction, exact tester evidence, and
  S70 touch/Digital Crown comparison remain open. External Beta Review and
  production promotion remain blocked until the hardware evidence and owner
  approval are complete.
- **Post-release cleanup (2026-08-31):** The exact allow-list and protected
  resources are recorded in
  `docs/operations/cleanup-20260831-build46.md`. No source worktree,
  rollback artifact, persistent data, shared cache, or other project/session
  resource is in the deletion scope.
- **Local workspace cleanup (2026-08-31):** The four generated geometry/
  CourseView directories were checksum-verified and moved to the additive
  homeserver import at
  `/home/jason/garmin-ai-caddie-data/imports/local-cache-20260831/`; the local
  copies were then removed. Completed Garmin physical worktrees were removed
  while their Git branch refs were retained. Closed Garmin-only Codex/Claude
  transcripts and generated review artifacts were removed from the editing box
  after their allow-list checks; review evidence is preserved under
  `/home/jason/garmin-ai-caddie-data/archives/local-generated-20260831/`, and
  durable memory remains in the canonical Claude `memory/` directory and this
  repository. No active process, credential, user-round data, or production
  Docker volume was touched. Full records are in
  `docs/operations/cleanup-20260831-local-garmin.md`.
- **Branch reconciliation (2026-09-04):** Fable 5.1's read-only review found
  that MAP1 and the old `integration/v2` line were genuine product branches,
  not a reason to replay every historical commit. PR [#331](https://github.com/jasonhorga/garmin-ai-caddie/pull/331)
  preserved the old line as the first parent and the reconciliation/MAP1 line
  as the second parent of a normal merge, while keeping the MAP1 tree
  canonical. The merged commit is `1775d87a`; the reconciliation branch and
  old refs remain available for the later whole-repository audit. The branch
  policy and current ref inventory are recorded in
  `docs/operations/branch-strategy-20260904.md`.
- **Contract boundary correction:** The active
  `mobile/contracts/live_round_event.schema.json` is no longer incorrectly
  listed as a frozen legacy adapter. The Watch input schema remains the only
  declared legacy adapter; the focused regression test and the historical
  `sync_marker`/`serverSequence` migration debt are recorded in
  `docs/operations/branch-reconciliation-20260904.md`.
- **Reconciliation CI:** Source CI run `33832029115` and Native Mobile CI run
  `33832029223` both passed at head `a331281acb78aec7def0e68d111f6d9cc941b249`
  (backend, frontend, Docker, iOS and Watch steps). The earlier fixture-test
  failure was corrected by `a331281a`; no product code changed in that fix.
- **Release side effects:** TestFlight tag `release/testflight-0.1.0-build-47`,
  backend tag `deploy/backend-2026-09-02`, and source tag
  `source/map1-2026-09-04` are unchanged. This reconciliation performed no
  upload, external distribution, deployment, synchronization, or production
  data write.
- **Prior Codex-only audit (complete; not Claude/Fable):** A read-only snapshot at
  `/dev/shm/garmin-ai-caddie-cloud-audit-20260904` was created by Codex at
  `2026-09-04T03:29:05Z` from `04ab1da8b77950d0cdf3dde09174f2c76460f0ec`.
  It is 32 MiB, contains no `.venv`, `node_modules`, build products, or
  credentials, and expired at `2026-09-05T03:29:05Z` (cleaned early after
  handoff). The inspection confirmed one P2 documentation fact error, corrected in
  `6593b95e`; the archived report is
  `docs/reviews/2026-09-04-cloud-whole-repository-audit.md` with archive
  SHA-256
  `1380b1659502377eb3f6f755ff1b987f14efdf5dddf4bc484640363e3fb12819`.
- **Claude Fable 5.1 whole-repository audit (complete; P2 follow-up applied):** A
  homeserver source-only snapshot was reviewed with the explicit first-party
  model `claude-fable-5-1`, `max` effort, and read-only `Read/Grep/Glob` tools.
  The report is
  `docs/reviews/2026-09-04-claude-fable-5-1-whole-repository-audit.md`;
  session `98bd77e3-c841-4ca2-86ee-91a1001b5382`; raw JSON SHA-256
  `50b56130e2b9c29920bf9061b461a539b0cad08902d47d13aad460c416553440`;
  report source-copy SHA-256
  `4ee5814afad50fbb085803da3c8cfcef50c343255b9cc52397b8035aed98e603`.
  Fable's verdict was `NOT READY`. The no-GPS distance labels, active score
  schema parity, and focused no-GPS/precision UI journeys are now implemented
  in the follow-up below; held-finger loupe capture and physical-device proof
  remain evidence-open. No release or deployment state was changed by the
  review or its follow-up.

## Objective

Close the smallest set of product and engineering gaps needed for a Garmin/S70
first round flow across Watch, iOS and Web: reliable start, live scoring,
course preparation, review, and synchronized history. Preserve existing working
code; do not restart the old multi-week plan tree.

## Current Slice

**`PHONE-UX2` — 7813–7819 真机交互与信息架构修正** (`in-progress`)

本轮处理 TestFlight Build 53 的真机截图反馈：简化 Touch Target/旗位拖动放大镜，
移除地图上的大外圆、双圆与十字准心，并把放大视图与手指保持可见间距；缩小并错开
沙坑/水障碍前后沿数字；地图支持缩放。已有进行中球局时首页只提供“继续”，不再
暴露新开球局入口。球童建议收进二级入口，统一杆名与推荐排序，并明确
`3H` 为“三号混合杆”；梳理记杆、确认本洞成绩和本场计分卡的层级，明确果岭
前/中/后与旗位距离是两组不同事实。Garmin 登录、会话保存、数据验证、同步和
网络失败改用单一权威状态；球场名称与行政地址优先显示中文；成绩页先显示持久化
缓存，再在后台刷新。

基线源码与自动验证已完成：Source CI `34316491467` 和 Native Mobile CI
`34316964148` 均在源码 `a44f1c9f` 上全绿；TestFlight CD `34323088795`
已上传 Build 54，Apple read-only 检查 `34324271971` 确认其已处理并在内部
`Jason's friends` 组可见。后续 UX2 边界修正已在远端通过 373 个聚焦测试（5 个
跳过），仍需
完成新源码的原生编译/设备证据后才能交接；Build 53 保留为上一轮历史候选，不能作为
本轮效果证据。

**Durable resume checkpoint (2026-09-09 UTC):** 当前唯一工作切片为
`PHONE-UX2`。已完成同杆授权分组、稀疏球包 Driver 线路和即时选中摘要代码及回归测试；
远端 scratch 为 `/home/jason/codex-runs/garmin-ai-caddie-phone-ux2-20260909-b`
（只读挂载测试，未创建持久服务）。聚焦套件已更新为 `374 passed, 5 skipped`；
全量 discovery 的失败/错误来自验证容器缺少 `git` 且排除了 `.env`、`data`、`output`
等 authority/鉴权/持久化资源，不能当作产品回归。恢复时唯一继续路径是先完成新源码
的原生编译/测试，再检查地图、障碍页、旗位真实设备表现；在这些证据完成前保持
`PHONE-UX2` 为 `in-progress`，不要上传或发布新的候选包。

**Durable execution plan (persisted 2026-09-09 UTC):**
1. 已完成：修正测试方法边界，并保留当前工作区全部产品改动；`git diff --check` 通过。
2. 已完成：homeserver 容量检查通过（约 117 GiB 可用、5.1 GiB 可用内存）；复用上述 scratch 在只读挂载并提供临时目录/数据层的容器中运行聚焦套件，`374 passed, 5 skipped`，exit 0。首轮只读容器错误是缺少 `/tmp` 和可写事件根，已修正验证条件，不是产品回归。
3. 进行中：针对 `b9ff8b9d` 重新通过 GitHub Native Mobile CI 完成 Swift 编译、单测、截图和真实 iPhone/Watch 证据，重点核对地图纵向拖动、独立障碍页、单一旗杆底部落点和三种打法选择。
4. 约束：原生/设备证据完成前不生成或上传新候选包、不做 Beta Review/外部发布/生产发布；验证结束后只清理本会话 allow-list 资源并回写本账本。

此前 `PHONE-REGRESSION` 保持 `evidence-open`：

**`PHONE-REGRESSION` — 球童推荐、障碍物标注与 Garmin 状态修正** (`evidence-open`)

本轮继续处理 TestFlight 截图 7770–7772、7802–7803 暴露的问题：Garmin 网页已登录时，
App 不能再把导入/验证/同步/网络失败统称为“连接失败”；附近服务失败时，也不能把
本机历史球场冒充附近结果，更不能丢失 A/B/C 场区标签。新增修复要求球童条、地图杆名、
带球距离和落点使用同一份后端推荐；障碍物前后点只显示紧邻边界的小数字，并拒绝
8,000+ 码等失真值；Garmin 已保存但未验证的会话必须能不重新登录直接重试同步。
`course` 在用户界面统一称为“球场”，A/B/C 称为“场区”。此前的
本轮修改已通过 Source CI 和 Native Mobile CI，并已按既定规则自动上传内部
TestFlight Build 53、完成 Apple processing/status 检查。Native Mobile CI run
`34223836622` 在 source `f24a22dd`、backend `f363872f` 上全绿。此前的
`34124638966`/`34121007416` 仅是旧候选的网络失败记录，不能作为当前产品
失败证据。

当前 live 验证和 Build 54 的 API 入口为
`https://suggests-kilometers-normal-insertion.trycloudflare.com`，由 homeserver
上的临时 tmux 会话 `codex-aicaddie-quicktunnel-http2-20260907` 代理到候选
API `127.0.0.1:39055`。健康检查持续返回 revision
`325cc2f33aa39ac18bbcac9bc2e87c6f15a89384`。该入口只在 Native/内部
TestFlight/真机验证期间保留，未修改共享 Tailscale Funnel 或 Lightsail 防火墙。

`GARMIN-AUTH` remains `evidence-open` for the one fresh physical reconnect;
`MAP1` remains `evidence-open` for held-loupe and paired-device evidence.

现场证据（2026-09-07 08:49–08:54 UTC）：在用户实际点击多次“重新连接
Garmin”期间，对运行中的 candidate API 做了 10 分钟只读监听；除健康检查外，
没有收到 `/api/v2/sync/garmin/session`、`/api/v2/sync/garmin` 或成员同步路由的
任何请求。监听进程已清理。当前失败点位于手机发请求之前，或设备使用了不同的
API origin；尚未取得真实 HTTP 状态码，不能宣称同步已修复。

**`GARMIN-AUTH` — reconnect validation and release binding** (`evidence-open`)

The Garmin web login succeeds, but build 50 can still report verification
failure because it was released before the same-origin gateway fix. The fix is
source-CI green, Native-CI green, and deployed at exact revision `caf3afad`;
build 54 is uploaded and visible in the internal group, with the later phone
UX source at `a44f1c9f` and backend `325cc2f3`. The diagnostic refresh
endpoint must not be called again: it rotated the captured session, so the
user must create a fresh session with one reconnect after this handoff.

The preceding `MAP1` slice remains `evidence-open` for physical-device proof:

The current product slice is applying physical iPhone feedback from TestFlight
build 48: preserve authoritative A/B/C course-loop metadata over stale local
records; make Touch Target and each caddie club render distance-accurate aim
points with two direct airborne arcs (Tee to landing and landing to flag);
remove redundant live-play media/adjustment chrome while retaining the
underlying features; and make horizontal hole-map swipes change holes without
stealing map-edit gestures. Release evidence remains open under `REL` and is
not changed by this slice.

The current product tip has a verified backend deployment, passing live
iOS/Watch Native evidence from run `34045077006`, and current TestFlight build
51 from run `34048458619`. The remaining release evidence is physical-device
installation, fresh Garmin reconnect/sync, first-launch/start verification,
exact tester qualification, and (if desired) external Beta Review/distribution.
Apple status has been verified, so work stops at the hardware handoff.

MAP1 implementation evidence (2026-09-02): the Watch/iPhone map-first start,
pixel-safe Touch Target and Green View editors, S70-style drag loupes, and
review landing precision editor are wired in the current workspace. The Watch
now keeps an unresolved Tee as `unknown` instead of displaying or submitting a
fabricated Blue Tee; the production package route accepts that token, retains
its provenance in the response, and resolves an internal distance only from a
factual CourseView Tee list. Without that authority it stays unresolved rather
than selecting the longest geometry row. Fable's follow-up review found that
the current evidence was mostly source-string, pure-function, screenshot, and
simulator coverage; the P2 follow-up adds a real no-GPS hero-to-map journey and
the review precision-editor route, while a held loupe remains video/device
evidence rather than a post-release accessibility assertion.

A network-disabled, read-only homeserver run in the existing API image passed
`147/147` focused tests: `tests.test_mobile_contracts` `94/94`,
`tests.test_ci_fixture_contract` `35/35`, `tests.test_course_tees` `17/17`, and
the production manual-search `tee_box=unknown` package test `1/1`. Python
`compileall` and `git diff --check` also pass. Source CI run `33680857200`
then passed the full backend/frontend/Docker contract jobs. Native Mobile CI
run `33680501425` passed all 38 steps at mobile source `c5902a96`, including
the no-GPS manual catalogue fallback, map/caddie restore, review precision
editing, 7 TeeSelection UI tests, 329 Watch tests, and 22 Watch runtime
screenshots. Swift compilation and simulator runtime evidence are therefore
green in CI; physical iPhone/Watch interaction and S70 Digital Crown/touch
comparison remain open because no paired hardware is available here. With no
course geometry/cache at all, a client can only show a map-preparation
placeholder; it cannot invent a real course map. With no GPS it can start,
show cached/downloaded geometry, and use local map targets, but it must not
record a fabricated shot coordinate. The reusable remote source snapshot is
`/home/jason/codex-runs/garmin-ai-caddie-map1-20260902` (29 MiB), expires
2026-09-09; all focused test/compile containers were `--rm` and are gone.
Homeserver free space is approximately 5.9 GiB, below the repository's 10 GiB
heavy-work gate, so no new Native build or full test session was started for
the follow-up.

P2 follow-up (2026-09-05): the phone now labels no-GPS F/M/B values as
`发球台 → 果岭` / `码 · 静态参考` and explains that they are not the current
position; the active live-round JSON Schema accepts the server/Watch
`fairway` enum with lockstep regression checks; and the no-GPS UI journey now
starts a manually searched course, verifies map/caddie/tee-reference labels,
opens Touch Target, places a target, checks Tee-based distance, and exercises
Touch Target/View Green zoom controls. Review editing also exercises the
newly added landing's precision editor, zoom, and explicit confirmation. A
read-only Pydantic smoke in the existing API container accepted all three
fairway values and rejected an invalid value; local AST/JSON/diff checks pass.
GitHub Native Mobile CI run `33970471549` at canonical tip `12fb5030` then
completed successfully: iOS/Watch compilation, XCUITest journeys, runtime
screenshots, artifact scans, and Watch tests all passed. The native evidence
artifact is `9971529102` with digest
`sha256:672a50e02f69811a26d6c836aee49090937d030339507eb7d2f7c0b3a81c6090`.
This closes the macOS/simulator portion; held-loupe video on real touch input,
paired iPhone/Watch installation, and S70 hardware comparison remain
evidence-open. Commit `caceb88e` was fast-forward pushed to
`origin/integration/v2`, followed by documentation tips `12fb5030` and
`b4aa9a71`; the later internal TestFlight upload and its read-only Apple status
check are recorded below. No external distribution, synchronization, or
production data write was performed.

The earlier current-head TestFlight CD artifact-only run `33977405908` then completed
successfully from `8e13623d`: Release signing, archive/export, provenance, and
artifact upload passed. It produced build 48 with IPA SHA-256
`479dc3e3298e3f8527458752f7a33e2ef22d11d79176047be075d556d24ceafc` and
artifact `9972807230` (ZIP digest
`5422bcf511eb3933264dbd7d31c0ff2a865eddc8a2feb114cbb49cb1bcf50829`). The
workflow explicitly used `upload_to_testflight=false`; no Apple upload or
deployment side effect occurred. This verifies that the P2 tree is packageable
as a signed release artifact, but it is not the current TestFlight candidate and
does not close the physical-device gate.

The subsequent internal upload run `34012329292` completed successfully from
`b4aa9a71`, uploaded and processed build 48, and retained external distribution
off. Read-only App Store Connect verification run `34012813699` confirmed that
build 48 is `VALID`, unexpired, in internal beta testing, and included by the
existing `Jason's friends` all-builds group. This closes the CI/Apple processing
portion only; it does not claim a physical install.

### Historical context (retained; earlier snapshots)

The following paragraphs are retained historical snapshots. Statements that
describe pre-deployment or pre-upload state are superseded by the current
summary above; the historical evidence itself is not removed.

`W1` and `S1` are closed with isolated current-head evidence. The public
service still runs revision `6a6080c6...`; no production deployment or data
synchronization was performed. R2 Web HMB and same-round iOS simulator runtime
evidence are complete, and the owner's `go` instruction on 2026-08-26 is
recorded as approval to advance the evidence gate. REL now checks the external
release prerequisites; no TestFlight upload is performed by this transition.
Candidate artifacts and production uploads are separate gates. Release provenance
binds commit, workflow/build, API origin host, backend revision, IPA hash, and upload
flag; tester/install assertions are manual and build-number-bound.
The artifact-only build is green. A fresh homeserver probe found the existing
candidate and production upstreams, Caddy, and the public Funnel all returning
200; the earlier ingress timeout was transient. The candidate remains the
public upstream, but its revision is not yet proven identical to the IPA and
the first GitHub-runner readiness probe timed out once; a strict rerun passed.

The latest source candidate `affb58df` includes the bounded course-identity
repair for Garmin global ID `31793`, where the provider currently says
`Shadow Creek Golf Club` while this player's history says
`北京丽宫体育公园高尔夫俱乐部`. The API keeps provider facts authoritative,
applies a player-scoped historical display alias only after a strict 2 km
physical match, and never mutates the shared provider cache. Empty provider
searches can recover an explicitly matching historical alias; nearby overlays
use a tighter radius; unknown, placeholder, unplayed, and coordinate-conflicting
rows fail closed. Geometry cache reads are bounded to history IDs missing
coordinates that are present in the current provider result. Homeserver
verification of the final candidate passed 60/60 focused/regression tests,
Python compilation, and diff-check; a read-only production snapshot check found
six real `31793` rounds with the required ID/name/coordinate fields and matching
cached geometry (0.173 km). No production deployment or data write has occurred.

On 2026-08-30, the backend candidate was deployed from the clean detached
checkout at `/home/jason/codex-runs/garmin-ai-caddie-backend-deploy-20260830`,
exact revision `1af378b811cd25edae12285c5745aef1b57d7faf`. The verified private
volume backup is
`/home/jason/garmin-ai-caddie-data/operations/backend-deploy-20260830/private-volume-20260830.tar.gz`
(3,349,748,487 bytes, 33,504 members, SHA-256
`9c632173043f3ac7010ef5883124ee1c57387ca3656aa387e873b102b819b162`; `gzip -t`
and checksum verification passed). Image
`garmin-ai-caddie-api:1af378b-candidate-20260830` (image digest
`sha256:237de4151516dcb6117fc2aaf514c7e177d9115fe55346337c4254517f666aaa`)
is healthy in container `aicaddie-release-1af378b-candidate-20260830` on the
existing `127.0.0.1:39055 -> 9000` mapping and shared private volume; health
reports the exact revision. The prior container/image remain stopped and
preserved for rollback. PostgreSQL, Caddy, Funnel, and persistent volumes were
not otherwise modified, and no data synchronization/write was performed.

Release-hardening commit `1d0f352b` is integrated on the canonical checkout.
Using the existing homeserver image
`garmin-ai-caddie-api:6a6080c-candidate` (`sha256:b035a77c...`), the focused
provenance/readiness/evidence suite passed 50/50; remote Python compilation and
`git diff --check` passed. A broader 89-test invocation had 86 passes and three
environment-only failures because the image has no `git`; a host-runtime run
had one unrelated missing-`pathspec` environment failure. No TestFlight,
signing, deployment, production, container, volume, or persistent-data write
was performed.

Canonical now includes the full release candidate chain through `cc2ad861`.
Opus supplied a final GO verdict in the handoff; no repository report path or
report hash was supplied, so none is claimed here. The release-specific
homeserver suite passed 100 tests, with remote Python compilation and
`git diff --check` also passing. External GitHub API, macOS native/TestFlight
execution, IPA signing/upload, and App Store Connect facts remain unverified.
Release-preflight verification on canonical HEAD `cc2ad861200f4c4aee74a8063aff4f57948a8b09`
used a short-lived homeserver scratch checkout with Git metadata: the focused
release suite passed 100/100, and full Python test discovery passed 1,974 tests
with 13 skips. Full-tree Python compilation passed. The real fixture-based
artifact-only provenance dry run produced a hashed IPA and exercised both
pre-upload and post-upload evidence contracts without network or production
writes. Source CI, Native Mobile CI, Phase 6 GitHub-runner validation, and
macOS/TestFlight artifact signing/upload remain to be run externally.
The same Linux scratch ran full Python discovery successfully; `web_v2` Vitest
reported 608 passed, 7 skipped, and one timeout in the existing stale-trends
refresh test (`src/App.test.tsx:1622`). Web lint passed with two existing
Fast Refresh warnings, and the production Vite build passed. The repository
root `npm test` remains a historical placeholder that exits with
`Error: no test specified`; the actual `web_v2` checks were run separately.
An external Actions orchestration attempt on 2026-08-27 listed available
workflows, but GitHub returned `No commit found for SHA` for canonical
`cc2ad861200f4c4aee74a8063aff4f57948a8b09`. Pushing this local-only candidate
was not authorized, so no source CI, Native Mobile CI, or Phase 6 run was
dispatched and no run ID or artifact is claimed. TestFlight, release, deploy,
and signing workflows were not dispatched.
The Phase 6 workflow path bug was fixed in `a46f83a7b6ba26d82f0309a1fcfc8cb93c541cef`
by initializing release evidence paths in a step via `$GITHUB_ENV` instead of
using the invalid job-level `runner.temp` context. Runs `33073844326` and
`33073934450` both completed successfully at that SHA; each produced the
readiness and roadmap artifacts. The downloaded reports were 4,522 and 7,380
bytes respectively; SHA256s for the first run were
`f9f8cced6bb6779e87f04dad46f8974cf2277e9a65c328f652a9f628f9b0a844` and
`3fa7ca2b7a158e9684e5f0b932aeed57ee1b850386cdc96742d994fe1c316636`.
Both correctly remained `incomplete` because the dispatch supplied no backend,
ASC, TestFlight build, or provenance inputs. Native run `33071953908` was
diagnosed as macOS UI-test infrastructure failure:
`XCTDaemonErrorDomain Code=19` (`AXDisableAccessibilityOnTermination`) with
`AppleM2ScalerParavirtDriver`; no native source change was made.
After the owner-authorized push of `91d91694ea1bd3d2318bd93f62fe851e19204ffc`
to `codex/p0-p1-p2-checkpoint-20260823`, source CI run `33071951190` completed
successfully (backend, frontend, Docker, and visual smoke). Native Mobile CI
run `33071953908` completed failure at `Real-simulator screenshots (iOS,
XCUITest against live backend)`; its small artifacts were retained only long
enough to verify: `real-flow.mp4` 760,395 bytes,
SHA256 `96f345d980c7c81194d0a8089f8dc4764112ba74b4ff997c45117e4097eecc6c`,
and `ios-app.log` 88 bytes,
SHA256 `d0b53e2a719d60b6dbcd54eba0b8286a2b494eb7b3f8de8de5b6cdc8b8ecba38`.
Phase 6 dispatch run `33071919393` failed before execution because GitHub
rejected the workflow expression `runner.temp`; no Phase 6 evidence was
produced. TestFlight/release/deploy/signing workflows remain unrun.
Native rerun `33074266179` at pushed HEAD
`d2cacff788bc842e4b8488dd3cce4469df9ba964` passed XcodeGen, iOS target tests,
SwiftJCS boundaries, and design snapshot secret scans, but failed the live iOS
XCUITest step. `RealFlowUITests` and `ReviewEditUITests` timed out fetching
`/api/v2/history/rounds?hasShots=true&limit=120` from the public API, while
`TeeSelectionUITests.testAuthorizedGPSWithoutFixStillOffersCompleteCatalogueFallback`
failed its home new-round availability assertion. The same run's real screenshot,
design snapshot, and video artifacts were uploaded; Watch stages were skipped
after the iOS failure. This does not establish a source regression: the two
transport failures are live-ingress/runtime evidence, and the remaining
TeeSelection assertion requires a focused reproduction before any code change.
Native runtime evidence therefore remains open and TestFlight workflows remain
unrun. The fix was verified by Native rerun `33077525178`: the authorized-GPS
fallback and all seven `TeeSelectionUITests` passed, but both review resolver
tests returned `noEligibleRound` because the current public history did not
contain a qualifying scored hole with two club-labelled spatially separated
shots and usable geometry.
The GPS fallback failure is a confirmed startup sequencing bug: when no cached
package exists, `bootstrap()` kept the root loading gate active while awaiting
the best-effort course-options refresh. The minimal fix in the current working
tree releases `isBootstrapping` immediately after Phase 1, preserving the
background refresh and leaving all live API assertions unchanged. A fresh
Native rerun is required to verify the fix; no release flags are enabled.

Only one task may become `in-progress` at a time. Update this file before
starting the next slice.

The current release-hardening candidate requires a fresh remote verification
of the focused readiness/provenance/workflow suites. No production service,
TestFlight upload, or signing resource is created by this source transition.
Native Mobile CI rerun `33229825184` at `27f37e184988203a28ac720e15d87ca72737901a`
reached the live iOS simulator flow and failed in `RealFlowUITests.testCaptureRealAppFlow()`
at `RealFlowUITests.swift:614` because the tee decision only exposed
`stock`-style output instead of the three complete route cards (`推荐打法`,
`保守打法`, `进攻打法`). The fixture decision endpoint was then fixed in
commit `cbed0a0e` to delegate tee/approach/recovery payload generation to the
app’s own deterministic decision builder with explanations forced off. A new
remote rerun is still required to verify that pushed fix.

Native Mobile CI run `33130426502` at head `75b34810590e8b622b27e69e53f16bd16c416cfb`
failed in the real iOS simulator screenshot step while compiling
`RealEvidenceRoundResolver.swift:73`: escaped quotes inside the optional-hole
string interpolation produced an unterminated string literal. The source-only
fix computes `holeText` before interpolation and preserves the exact diagnostic
output; the focused mobile contract and remote Python compilation pass. No
Native workflow rerun was dispatched; Opus/owner review is the next gate.

Per Opus GO, ran exactly one fixture-mode Native Mobile CI validation
`33132251561` at exact head `23423c406f10a6be55db71e90dd69f302cee84cd`, with
`capture_scope=full`, `fixture_mode=true`, `review_round_ref=900001`, an
ephemeral runner token, blank production inputs, and live preflight disabled.
Fixture uv install/start/health and stop passed; XcodeGen, iOS app target,
SwiftJCS boundaries, design snapshots/secret scan, Watch target,
Watch snapshots/secret scan, Watch runtime seed/restore (22 PNGs), runtime
secret scan, evidence writer, artifact uploads, and cleanup passed. The iOS
UI-test step failed only in behavior: `RealFlowUITests` and `ReviewEditUITests`
returned `noEligibleRound`, while three TeeSelection tests could not find the
Beijing Palace/segment `31793` fixture rows. This run therefore proves the
source compile fix and independent Watch stages, but not iOS fixtureRevision,
18-hole package/map/topo/green/caddie/identity consumption or iOS behavior.
Artifacts were retained remotely only: design snapshots 3,702,496 bytes
(`sha256:4d229a297217ede1eda957ead04f92414ce8370153e2ff94b07aac1cdf34e6e5`),
real screenshots 2,237,032 bytes (`sha256:2a8465f33c931b60ae8cf18e37faa17fccf3db9228d5d94683a3cdf277a8306d`),
real video 92,894,131 bytes (`sha256:572ee63e6380cf38b5445b22d8e1754739805777d1a24fad055310694b3dc87e`),
Watch snapshots 2,151,345 bytes (`sha256:9fe2ad8aba1cf017f7557fbcfb650d367fc5c1fc9d70170ecdd9295cab730896`),
Watch runtime 286,672 bytes (`sha256:9cf6ea7d57f7fcd847e37bbbc36b0703179da88fd770203bd73583926afa3379`),
and native evidence 510 bytes (`sha256:c3847fca4ad78c8485ee0b1998bdfee965d02a8b98b075fd557a6862f212be18`).
No further rerun, TestFlight, release, deploy, signing, or production action
was performed; the remaining blocker is the fixture route/data consumption
needed by iOS review and tee-selection behavior.

Diagnosis of run `33132251561` found two independent fixture contract gaps;
no source or test change was made and no rerun was dispatched. The resolver
does receive `UITEST_REVIEW_ROUND_REF=900001` from the workflow, and fixture
history advertises round `900001` with scored holes and two non-synthetic
club-labelled shots. However, the fixture's deterministic 64x64 PNG is only
358 decoded bytes (480 base64 bytes), while
`RealEvidenceRoundResolver.usableMapImage` requires decoded data larger than
1,024 bytes; every shotmap therefore rejects with `shotmap mismatch or missing
geometry/image` before landing separation can pass. Separately,
`server_v2/ci_fixture.py` course search and nearby return `31795` / “Black
Knight B/C” and `3881` / “Cypress Point Club”, while `options()` filters to
`3881`; the three failing TeeSelection assertions require provider course
`31793` / “Beijing Palace” and accessibility IDs ending in `31793`. The logs
show the expected catalog IDs were absent, not an action/scroll race. Minimal
next fix is fixture-only: provide a >1,024-byte valid raster while preserving
the resolver threshold, and add the exact `31793` Beijing Palace fixture
catalog/nearby/search identity (with its tee/package bindings) without
changing assertions or production data. Fixture route/API consumption remains
unproven until that correction and one owner-authorized rerun.

Implemented the bounded fixture-data repair after the `33132251561` diagnosis,
without changing resolver thresholds, UI assertions, live mode, or production
data. `server_v2/ci_fixture.py` now emits deterministic valid 64x64 RGBA PNGs
using a seeded pixel stream; decoded payloads are 14,183 bytes and are reused
consistently by shotmap, prep, topo, and green resources, satisfying the
existing `>1,024` byte and raster-dimension gate. Course identity `31793`
(`Beijing Palace`) is now accepted and preserved through search, nearby,
options, tees, package, prep, geometry, and round-context routes while
existing `31795`, `3881`, `31670`, and `31871` aliases remain supported and
unknown IDs still fail closed. The focused fixture contract suite passes
26/26 on the homeserver temporary uv/FastAPI environment; loopback HTTP smoke
with `AI_CADDIE_FIXTURE_MODE=1` returns fixture revision
`ci-fixture-20260827-v1` and 31793 in both search and nearby; remote
`compileall -q server_v2 ai_caddie tests` passes. No Native rerun was
dispatched; Opus read-only re-review is the next gate.

The single fixture-mode validation `33134913933` at `ac1e7291` confirmed the
image repair and 31793 catalogue identity were present, but exposed a separate
`NewCourseEvidenceResolver` precondition: every nearby row was also listed in
`options()`, and all coverage responses were `ready`, leaving no uninstalled
course with a partial first-hole upgrade. The minimal fixture-only correction
adds supported course `31797` (`Fixture Open Course`) to search/nearby and
course aliases, deliberately leaves it out of installed options, and returns
partial/zero-ready coverage only for that course. Existing 31793 Beijing
Palace and round 900001 data remain unchanged. Homeserver fixture contracts
remain green at 26/26 with full Python compilation; no Native rerun has been
dispatched and Opus review is required before any further workflow action.

Fixture-contract P1 hardening after `95d3c1e7` is implemented in commit
`7ed11cb0` plus the current follow-up: decision requests require an exact
caller `sourceRef`; course aliases return their canonical resolver id;
package/prep composite holes preserve `sourceGlobalId` and `sourceLocalHole`;
prep serves a non-null three-anchor `holeImageProjection`; and the fixture
mirrors the parameterized `/api/v2/players/{playerId}/clubs/bag` GET route and
allowlist. The caller-to-route matrix is now explicit: Watch
`WatchCourseLibrary` generates `watch-<UUID>` round IDs, iOS home fallback
generates `home-<gid>`, and iOS live fallback generates
`live-<gid>-<UUID>`; these are accepted only with UUID syntax and a
`COURSE_ALIASES` course ID. Course `3881` is present in search/nearby/options.
The fixture generates independent package/prep/coverage/install/geometry/
shotmap/history rows for holes 1-18 with distinct overlays/images and correct
front/back/all filtering. Local compilation and the focused fixture suite ran
17 tests (5 passed, 12 skipped without FastAPI). An exact-SHA remote scratch
with a temporary uv venv containing FastAPI ran the same 17 tests (17 passed)
and remote Python compilation/diff-check passed. macOS Codable decode and
Watch runtime evidence remain open; this is fixture evidence only.
Follow-up P1/P2 closure is implemented through commits `c7d5e9fc` and
`1d15c229`: caddie
decision accepts and validates holes 1-18 with caller round/course/local-hole
identity and per-hole source refs; package metadata reports segment-sized
source/geometry/caddie readiness counts and one seed per requested hole;
history detail, shotmap, geometry, prep, coverage, and install are generated
per hole with distinct refs/overlays, including back-course local-hole mapping;
`includeImage=false` is honored by shotmap. Remote FastAPI-backed fixture
contract verification ran 17/17 tests, plus remote py_compile and diff-check;
the local dependency-gated run remains 17 tests with 12 FastAPI skips. The
latest exact-SHA remote run after the geometry/round identity correction also
remains 17/17 passed.
The latest correction keeps composite back-nine metadata, decision, history,
and shotmap rows on back-course local holes 1-9 while preserving display holes
10-18 and caller round refs. Dynamic `watch-<UUID>` package and shotmap
requests fail closed without explicit course context; with explicit 31795/3881
context they retain the selected course identity. Remote FastAPI verification
after this correction remained 17/17 passed.
Opus final review `opus-fixture-contract-review-f88b58dc-20260827.md` identified
two remaining P1s. They are addressed in the current follow-up: back-nine
caddie options/dispersion now expose physical `localHole` 1-9 plus
`displayHole` 10-18, and `SyncClient.fetchRoundDetail`/
`fetchRoundShotMap` now accept and send optional `global_id`,
`back_global_id`, `nine`, and `tee_box` context while retaining old call
signatures through defaults. The fixture rejects dynamic Watch round
requests without explicit course context. Local fixture tests ran 18 tests
(6 passed, 12 skipped without FastAPI); the correctly synchronized remote uv
venv with FastAPI ran 18/18 passed, plus py_compile and diff-check. Swift
compile/Codable and macOS Watch runtime remain unverified and require the
Native workflow.
The final native caller follow-up threads this identity through `RoundReviewView`,
the shot-map pager/repository, edit refreshes, and recent-round review; recent
composite packages derive the back-course id from per-hole source identity.
Local Python compilation and `git diff --check` pass; a remote FastAPI-backed
rerun passed 18/18 and remote Python compilation passed. The remote scratch was
removed after verification. Swift compile/Codable and macOS Watch runtime remain
unverified and require the Native workflow.
The subsequent full-entry identity pass is implemented in the current follow-up:
fixture round aliases are structurally parsed and encoded course/query conflicts
fail closed; package, history-detail, and shot-map routes bind front/back course,
segment, and tee context; Home previous-round, Results recent/archive/trend, and
Stats drill-in entries carry round identity into the review pager/repository/edit
refresh chain; and `RoundDetailHole` retains physical course/local-hole,
back-course, and source-reference fields. Local checks ran 20 tests (6 passed,
14 skipped without FastAPI); the homeserver FastAPI-backed suite passed 20/20,
with remote Python compilation and diff-check passing. Native Swift compile and
Codable/runtime evidence remain open; no workflow, deployment, signing, upload,
or TestFlight action was performed.
expected Opus fixture-contract review report at
`/home/jason/garmin-ai-caddie-data/operations/opus-fixture-contract-review-20260827.md`
was checked and does not exist; no report hash is claimed. This remains source
and fixture evidence only; no workflow, deployment, signing, upload, or
TestFlight action was performed.
The follow-up identity-boundary pass unifies segment/display/local-hole
resolution across fixture package, prep, coverage, history, shotmap, and caddie
routes. It rejects front/back segment conflicts, requires back-course identity
for back segments, preserves physical identity in `RoundDetailHole` and
`RoundHoleShotMap`, and adds a nine/holes/back-course matrix contract. Local
checks ran 21 tests (6 passed, 15 skipped without FastAPI); the homeserver
FastAPI-backed suite passed 21/21 with remote Python compilation and
`git diff --check` passing. Native Swift compile/Codable/runtime evidence
remains open; no workflow, deployment, signing, upload, or TestFlight action
was performed.
The final Opus boundary follow-up applies the shared hole resolver to package,
install/status, prep, coverage, history, shotmap, and caddie generation. Caddie
course identity is checked after segment normalization, and editable shot-map
copies preserve top-level source provenance. Segment matrix tests cover front
1-9, back local 1-9/display 10-18, missing back identity, and invalid ranges.
Local checks ran 22 tests (6 passed, 16 skipped without FastAPI); homeserver
FastAPI-backed tests passed 22/22 with remote Python compilation and
`git diff --check` passing. Native Swift compile/Codable/runtime evidence
remains open; no workflow, deployment, signing, upload, or TestFlight action
was performed.
The final caddie identity follow-up propagates segment, front/back course,
tee, display/local hole, round, and source reference fields through fixture
`CaddieContextSeed` generation and the Native request builder. Caddie now
normalizes local/display holes before validating `courseGlobalId`; executable
tests cover both back-hole forms and reject front/back mismatches. Local checks
ran 23 tests (6 passed, 17 skipped without FastAPI); homeserver FastAPI-backed
tests passed 23/23 with remote Python compilation and `git diff --check`
passing. Native Swift compile/Codable/runtime evidence remains open; no
workflow, deployment, signing, upload, or TestFlight action was performed.

The denied-GPS city-only catalogue failure has a minimal source fix on the
current branch: `StartRoundView` now applies the resolved search option
directly when a result is tapped, instead of writing `remoteCourseOptions` and
immediately looking the option up again through coalesced `@State`. This keeps
the existing city-search/long-result behavior while making the selected course
ID, fresh live round ID, and tee state explicit before dismissing the sheet. A
deterministic `StartRoundDiscoveryTests` case covers selecting the final item
from a 200-row catalogue and retaining the resulting start-round state. The
 homeserver is Linux and cannot run `xcodebuild`; macOS Native Mobile CI is
 required for runtime confirmation. The first verification dispatch
 `33089327124` was pinned to `87780b3e2083cbaee4162663048d9b95872f467c` but
 failed during Swift compilation because two existing segment/venue callers
 still used the removed `globalIdText:` argument; iOS tests and all Watch
 stages were skipped, so it provides no behavioral evidence. Those callers
 were corrected in `8521f862`. The single rerun `33089934893` was pinned to
 `8521f8621e70a14115ed40f008eafe23e6ed5c77`: XcodeGen, simulator inventory,
 the complete iOS app target, SwiftJCS boundaries, design snapshots, and
 secret scans passed. Its live preflight then failed before all RealFlow,
 ReviewEdit, TeeSelection, and Watch runtime stages because the expected
 backend revision was `8521f862...` while the public backend reported
 `6a6080c6f6867513ed461d20e98a29113bd65433`. This is an external provenance
 gate, not source/fixture behavior evidence; no additional rerun is justified
 until the public backend revision is aligned. No release, deploy, signing, or
 upload workflow is dispatched.

Bounded provenance diagnosis confirms this is a workflow/environment contract
issue, not a safe reason to weaken the gate. `native-mobile.yml` and
`watch-runtime.yml` pass the app checkout SHA separately as
`AI_CADDIE_PREFLIGHT_APP_REVISION`; `AI_CADDIE_PREFLIGHT_EXPECTED_REVISION`
comes from the explicit backend revision dispatch input or protected backend
variable. The API health endpoint reports the independently deployed
`AI_CADDIE_BUILD_REVISION`. The backend deploy workflow sets that value from
its own `$GITHUB_SHA`; it is therefore correct for the public service to
report a different revision until that backend commit is deployed. Direct
read-only health probing on 2026-08-27
returned schema `ai-caddie-health-v2`, status `ok`, service `server_v2`, and
revision `6a6080c6...`, matching Native preflight run `33089934893`. The
preflight validators and workflow contract tests pass in an exact-SHA remote
scratch through Python compilation; `pytest` was unavailable there, so no
Python test result is claimed. The minimal safe resolution is an owner-
authorized backend deployment of the compatible backend revision, or an
explicit separately supplied backend revision input/variable for Native CI;
do not substitute the observed revision or remove the check. No production
data, service, or deployment was modified.

## Task Ledger

These IDs persist across sessions and context compactions. They are the only
project-level task list; historical plans are reference material.

| ID | State | Scope | Exit evidence |
|---|---|---|---|
| `W1` | `done` | Watch lifecycle, independent discovery, offline/restart, and 41/45/49 mm behavior. | Run `32806892801` watch-runtime job succeeded at head `8a3ee8ba`: 41/45/49 mm captures, real Cypress 18-hole install/restore, same-round 1–18 journey, hole-1 history edit while live on hole 10, finish confirmation, 57 queued records acknowledged, remote finish success, plus Cancel recovery and abandon/tombstone markers. |
| `S1` | `done` | Sync provenance, resumable background course download, real club-distance data, and Garmin-to-client consistency. | Focused backend/Web gates plus Native Mobile CI `32837705596` at `bf84ea8a`: iOS 257 tests, Watch 315 tests, iOS/Watch design snapshots, real iOS flow/video, 11 Watch runtime screenshots, secret scans, and non-empty runtime/build artifacts. |
| `R1` | `done` | Web map-first review editor/cache slice described above. | Focused tests plus remote add/drag/delete/reorder/save/reload evidence. |
| `R2` | `done` | iOS/Web review parity, first-frame/cache, overlay-first layout, and unified trend entry after `R1`. | Half Moon Bay round-by-round facts, same-round iOS/Web request/first-frame evidence, public comparison page, and owner `go` approval. |
| `REL` | `evidence-open` | Release and TestFlight gate; current internal build 54 is processed and group-visible. | Source CI `34316491467`, Native CI `34316964148`, and CD run `34323088795` passed at source `a44f1c9f`; read-only run `34324271971` confirmed build `0.1.0 (54)` `VALID`, unexpired, `IN_BETA_TESTING`, arm64, and included in `Jason's friends` (`allBuilds=true`) with backend `325cc2f3`. Physical installation, fresh Garmin reconnect, and optional external Beta Review remain open. |
| `MAP1` | `evidence-open` | Physical iPhone feedback for course-loop authority, Touch Target/caddie map arcs and landing interpolation, simplified live controls, and horizontal hole navigation. | Product/test commit `5628cc6d` plus Source CI `34021727402` and Native Mobile CI `34021862658` are green; TestFlight build 50 contains the MAP1 product tree. Held-loupe/device evidence remains open. |
| `GARMIN-AUTH` | `evidence-open` | Make a successful Garmin web login validate and synchronize against the current CN gateway, then bind the internal app candidate to that backend. | Commit `caf3afad`, source sync follow-up `f24a22dd`, Source CI `34043175968`/`34223501012`, controlled 403-to-200 gateway comparison, healthy public deployment, Native Mobile CI `34223836622`, TestFlight CD `34231106418`, and Apple/group check `34232120285` are complete. One new real-device reconnect/sync remains. |
| `PHONE-REGRESSION` | `evidence-open` | Unify backend caddie recommendation with the live club strip/map landing, constrain hazard labels/distances to small factual edge numbers, and provide a direct retry for saved-but-unverified Garmin sessions while preserving provider-nearby, manual-search, downloaded-course provenance and A/B/C labels. | Source CI `34223501012`, Native Mobile CI `34223836622`, backend revision `f363872f`, TestFlight Build 53, and Apple processing/group visibility are complete; physical screenshots and device behavior remain evidence-open. |
| `PHONE-UX2` | `in-progress` | Apply Build 53 screenshot feedback for offset/simplified map loupes, compact factual hazard labels, resume-only active-round behavior, one Garmin auth/sync state, localized course/address display, stale-while-refresh score history, nested caddie advice, clearer scoring hierarchy and F/M/B versus pin presentation, plus zoomable maps with a single flag marker. Follow-up fixes cover strategy selection, tee-club semantics, a dedicated hazard surface, fitted-map panning, and one pole-foot flag geometry. | Source CI `34316491467`, Native Mobile CI `34316964148`, TestFlight CD `34323088795`, and Apple/internal-group check `34324271971` passed at source `a44f1c9f`; focused remote suite now passes `373` tests (`5` skips), while fresh native/device evidence remains open. |
| `CLOUD-AUDIT` | `done` | Historical Codex-only read-only inspection after branch reconciliation; not a model audit. | Archived report `docs/reviews/2026-09-04-cloud-whole-repository-audit.md`; archive SHA-256 `1380b1659502377eb3f6f755ff1b987f14efdf5dddf4bc484640363e3fb12819`; snapshot/report cleaned. |
| `FABLE-AUDIT` | `done` | Homeserver Claude Fable 5.1 whole-repository read-only audit; findings feed MAP1/REL gates. | `docs/reviews/2026-09-04-claude-fable-5-1-whole-repository-audit.md`; session `98bd77e3-c841-4ca2-86ee-91a1001b5382`; raw JSON SHA-256 `50b56130e2b9c29920bf9061b461a539b0cad08902d47d13aad460c416553440`; report source-copy SHA-256 `4ee5814afad50fbb085803da3c8cfcef50c343255b9cc52397b8035aed98e603`; model usage only `claude-fable-5-1`; temporary resources cleaned. |
| `SNAPSHOT-BLOAT` | `done` | Remove reproducible `output/prodgeometry*` from durable Garmin snapshots and portable exports while preserving dependency metadata and legacy import compatibility. | Commits `ca3f505c`/`6d130528`; Source CI `34330414405`; focused remote tests `31/31`; cleanup manifest `/home/jason/garmin-ai-caddie-data/cleanup-manifests/20260909-snapshot-geometry-exclusion`; 16 directories and `34,241,567,932` bytes removed, nine snapshots retained, post-sync geometry count zero. |

### Status vocabulary

`queued` means defined but not started; `in-progress` means the current slice;
`evidence-open` means code exists but runtime proof is missing;
`ci-green-runtime-open` means CI is green but production/runtime proof is
missing; `implementation-partial` means more code is required; `blocked`
means a named external decision or prerequisite is missing; `done` and
`cancelled` are terminal.

## Completed Evidence

- `caf3afad`: Source CI run `34043175968` passed backend, frontend, and Docker
  jobs after adding Garmin CN same-origin fetch metadata. Controlled gateway
  comparison with the same Cookie/CSRF pair changed HTTP 403 to 200.
- `caf3afad`: Public backend deployment
  `aicaddie-release-caf3afad-candidate-20260906` is healthy and
  `/api/v2/health` reports the exact revision. Native Mobile CI run
  `34045077006` passed all live iOS/Watch steps (`dataMode=live`), including
  no-GPS/manual-search/map/caddie flow, real screenshots/video, Watch tests and
  runtime screenshots, evidence writing, and secret scans. Native evidence
  artifact `9993775235` has ZIP digest
  `sha256:03de0e455a28fd6ddabc0a218d0e0bc5d5c7536db6fd797eef4d0f77a09601e7`.
- `caf3afad`: TestFlight CD run `34048458619` uploaded and Apple processed
  build 51; provenance records API origin and backend revision exactly, with
  IPA SHA-256 `28296cd7c146f344939e910d87ffc16a04c7803dbf95d773a405f8010ff3dcf5`.
  Read-only TestFlight run `34048981151` confirmed build 51 `VALID`, unexpired,
  `IN_BETA_TESTING`, arm64, and included in internal `Jason's friends`; no
  external group or distribution was changed.
- `f24a22dd`: Source CI `34223501012` and Native Mobile CI `34223836622` passed;
  the latter completed all 300 iOS tests, live course/map/caddie evidence,
  Watch tests/runtime screenshots, and artifact/secret scans. TestFlight CD
  `34231106418` uploaded and Apple processed build 53 against backend
  `f363872f`. IPA SHA-256 is
  `fe4f6078dd7b0560b5f755c14d2133af13ca1a272562a064995c3d6ec2c8e23f5`;
  artifact `10058141615` ZIP digest is
  `sha256:19188deaf5e25097b0b5bd8bd6afb3bcf15bdd5536430ccf4add49320512e0ed`.
  Read-only App Store Connect run `34232120285` confirmed build 53 `VALID`,
  unexpired, `IN_BETA_TESTING`, arm64, and included in internal `Jason's
  friends`; no external group, Beta Review submission, or production
  promotion was performed.
- `a44f1c9f`: Source CI `34316491467` and Native Mobile CI `34316964148`
  passed; the latter covered live iOS XCUITest/screenshots/video, Watch tests
  and runtime screenshots, and all evidence/secret scans against backend
  `325cc2f3`. TestFlight CD `34323088795` uploaded build 54 with exact
  source/API/backend provenance and IPA SHA-256
  `5243bd6ceb18128603b69156bb5c858ee5cc5aa92da1a7a51bf20975cea68ceb`.
  Read-only Apple check `34324271971` confirmed `VALID`, unexpired,
  `IN_BETA_TESTING`, arm64, and membership in internal `Jason's friends`;
  external distribution and production remained unchanged.
- `ca3f505c`/`6d130528`: Source CI `34330414405` and focused remote snapshot
  tests (`31/31`) passed. New manifests and portable exports contain no
  `output/prodgeometry*` members while retaining dependency metadata; the
  import path accepts pre-change archives. Homeserver cleanup manifest
  `20260909-snapshot-geometry-exclusion` records 16 exact deletions,
  `34,241,567,932` bytes released, nine retained snapshots, zero remaining
  per-snapshot geometry directories, and no external references. The next
  scheduled sync completed successfully against API revision `6d130528`.
- `d189b3b4`: Source CI run `33680857200` passed backend (2,047 tests, 13
  skips), frontend component/lint/build/visual smoke, and Docker API/sync
  smoke. The MAP1 mobile source is unchanged from `c5902a96`.
- `6519065d`: Documentation-only source CI run `34013149549` passed backend,
  frontend component/lint/build/visual smoke, and Docker API/sync smoke.
- Backend candidate revision `c1648891` is deployed from
  `/home/jason/codex-runs/garmin-ai-caddie-map1-deploy-20260902` in
  `aicaddie-release-c1648891-candidate-20260902`; public health and the
  authenticated course `31793` package probe passed with 18/18 geometries and
  factual `teeBox=unknown` provenance.
- `c5902a96`: Native Mobile CI run `33680501425` passed all 38 steps; iOS and
  Watch manifests passed, Watch 329 tests passed, and 22 runtime screenshots
  were uploaded. Native artifact `9868217071` has digest
  `sha256:70183f3155e434c617b5d53590be8857e6aab791b17dc518c99af04f46aa0415`.
- `12fb5030`: Native Mobile CI run `33970471549` completed with `success`.
  The iOS/Watch compile and XCUITest lanes, no-GPS manual-search/map/caddie
  journey, Touch Target/View Green zoom, review precision-editor route, Watch
  tests, runtime screenshots, and secret/artifact scans passed. Artifact
  `native-build-evidence-ci-fixture` (`9971529102`) digest is
  `sha256:672a50e02f69811a26d6c836aee49090937d030339507eb7d2f7c0b3a81c6090`;
  the run was fixture-mode and does not replace physical-device evidence.
- `d189b3b4`: TestFlight CD run `33686521143` uploaded and Apple processed
  build `0.1.0 (47)`. IPA SHA-256 is
  `19936b224428aa2e740fc7b277f26b80f91c52b44c567b75cbe310349db4f3ad`;
  artifact `9868598629` ZIP digest is
  `sha256:19865fc1d6190c5e58e882f63062b39b1cebd00d730c3b656c8e54ed7fdbe82b`.
- Exact artifact diagnostics run `33687517758` passed signing/profile/team/
  version/build/architecture checks. ASC status run `33687613975` confirmed
  build 47 `VALID`, unexpired, in internal beta testing and included by the
  internal all-builds group; it is not assigned to `Private Trial`.
- TestFlight CD run `34012329292` built and uploaded current build `0.1.0 (48)`
  from `b4aa9a71` with external distribution disabled. Apple processing,
  provenance, and artifact upload passed; IPA SHA-256 is
  `1b1febfdb3919694c1dbf92e818f97f29f65d931cccd0eb7672e31b97276abef`, and
  artifact `9982919017` has ZIP digest
  `sha256:baf955c01a7aacd55a4499945a625e83ecdb929a15c5050c2274ff5089b90528`.
- Read-only ASC listing run `34012813699` confirmed current build 48 is
  `VALID`, unexpired, in `IN_BETA_TESTING`, and included in the existing
  internal all-builds group `Jason's friends`; `Private Trial` excludes it.
  This run performed no tester, group, review, or distribution mutation.
- Phase 6 audit run `33687800258` passed provenance/backend/signing/API checks
  and intentionally remained `incomplete` because external review, tester
  coverage, and physical installation are unconfirmed; `install_verified` is
  `false`.
- `7dbb29be`: Native Mobile CI run `33624244255` passed all 38 steps. Real iOS
  XCUITest coverage passed `RealFlowUITests` (including no-GPS map/caddie
  restore), `ReviewEditUITests`, and 7/7 `TeeSelectionUITests`; Watch target
  passed 329 tests and Watch runtime produced 22 screenshots with secret scans.
- `10d56855`: Watch provisional shot acceptance/completion is idempotent; Native
  Mobile CI run `32684985178` passed.
- `ca3fa89`: caddie tiers are distinct (`稳妥`, `标准`, `进攻`); focused remote
  tests reported 106 passed, 2 skipped.
- `bbc865af`: FIR denominator excludes unknown/empty tokens while preserving
  real `0` as a miss; XCTest coverage added (GitHub verification pending).
- CI run `32689037776` was run against `a1b88a2e`: Docker passed; frontend failed
  because an older `App.test.tsx` mock omits install status; backend failed two
  assertions that still encode pre-`ca3fa89` strategy/readiness expectations.
- The three CI fixes are now integrated at `2ca27720`; rerun `ci.yml` before
  starting the next product slice.
- CI run `32690177548` then passed backend, Docker, component tests, lint and
  build, but failed only visual smoke because two E2E fixtures still used the
  old `phase:'complete', holes:[]` shape. That fixture correction is `edf41054`.
- CI run `32690671928` at head `b6ecee8f` is green across backend, frontend
  visual smoke and Docker.
- R1 is complete across `3eed2c56`, `82538984`, `bfc6bb57`, `de11b5db`, and
  `b1b86af7`: focused Web 38 passed; full Vitest 600 passed/7 skipped; build
  passed; lint 0 errors/2 existing warnings; history visual smoke 1 passed;
  final remote review-editor interaction passed in 11.8s on homeserver after
  temporary browser install, which was removed with no persistent service or
  tunnel left behind.
- Watch runtime run `32707001002` succeeded at head `ca2b2d7a` (artifact
  `9513235658`), covering 41/45/49 mm runtime boundaries and all five stateful
  recovery markers.
- Watch recovery-only run `32791049667` succeeded at head `84a53752` in 20m12s;
  artifact `watch-runtime-evidence` ID `9543591961`, digest
  `sha256:395ecdfdbadba578257737c0f90b667eef9f38c324da257fc02d4bd8e216e381`.
  Its markers prove the Cancel recovery location event is persisted and the
  abandoned round's stale seed is rejected after relaunch. Web evidence was
  correctly skipped.
- CI run `32796906679` at head `8a3ee8ba` passed frontend, backend, and Docker;
  this advances the verified code baseline but does not close W1's production
  18-hole/current-head journey evidence.
- 2026-08-25 public Funnel verification passed: `/`, `/api/v2/health`,
  `/sat/`, `/yoyo/`, `/demos/`, and `/yoyo-api/health` each returned HTTP 200
  after the root route was restored from `127.0.0.1:443` to `:8080`. The
  before/after route backups are under
  `/home/jason/garmin-ai-caddie-data/operations/funnel-backups` (before SHA
  `6f1bc4...`, after SHA `3ea52c...`).
- Watch runtime run `32801079395` at head `8a3ee8ba` passed the 41/49 mm
  coverage, but Preflight live course discovery failed because the public API
  is on backend revision `6a6080c6...` while the expected current-head
  candidate is `8a3ee8ba`; at that point this did not close W1.
- Watch runtime run `32806892801` at head `8a3ee8ba` succeeded for the complete
  W1 journey. Artifact `watch-runtime-evidence` ID `9549422683`, digest
  `sha256:554bbace81931ba65ec47a08a91249fc9ee95d1e8a6d3ae3bc3b55c472b676fc`.
  The Watch job's evidence was scanned for secrets before upload.
- The same run's optional `web-live-evidence` job failed before receiving
  `/api/v2/history/overview` (`net::ERR_FAILED`) through the temporary Quick
  Tunnel; this is a separate Web transport/evidence gap, not a Watch W1
  failure, and produced no Web artifact.
- S1 read-only audit (snapshot `e8JaMj`, cleaned after handoff) found that the
  backend install journal, iOS prep queue, and Watch course store each track a
  different readiness model; there is no shared `precise/offline-installed`
  contract. The iOS queue has finite background grace rather than a durable OS
  transfer, while the backend journal itself is resumable.
- The same audit traced club distances to Garmin advice/average, AutoShot
  history medians, manual bag, and catalog fallback. `/prep` currently drops
  the distance source, and iOS/Web do not normalize spaced Garmin names such as
  `3 Wood`/`3 Iron`; this is the confirmed minimum explanation for the 3-wood/
  3-iron inconsistency. No production runtime mutation was used.
- S1 implementation commits `85acb022`, `bc9ab55e`, and `fb1c1287` now add spaced Garmin
  name normalization, `/prep` distance provenance (`history_median`, Garmin,
  manual, catalog, or explicit `unresolved`), propagation to iOS/Watch/Web,
  and cache invalidation when a manual bag changes. Focused remote verification
  reports 78 backend tests passed with 2 geometry skips; Web focused tests and
  build passed on the delegated worktree. iOS/Watch XCTest has not yet run.
- S1 Watch install-status commit `11c28972` (delegated source `b4688e8a`) adds
  the Watch-side journal contract, 404-as-missing behavior, and focused
  request/decode tests; it has not yet received macOS XCTest evidence.
- Native Mobile CI run `32817814200` at source head `5462f59f` passed XcodeGen,
  iOS XCTest, SwiftJCS boundaries, and design snapshots, but failed the real
  iOS flow at `RealFlowUITests.swift:292`: the search keyboard remained present
  after tapping the manual search button. Watch XCTest and Watch runtime
  screenshots were skipped by that failure.
- Keyboard-focus fix `bf944100` synchronously clears `focusedField` before
  launching manual, nearby, or submit-triggered searches. Review-scope Native
  run `32821984671` completed: `RealFlowUITests.testCaptureRealAppFlow` passed,
  but `ReviewEditUITests.testCaptureReviewEditFlow` failed at line 289 when the
  last reorder handle did not change the preceding visible shot. Full Native
  verification remains blocked on that bounded reorder gate.
- Test-only reorder commit `5fdb9fff` moves the XCUITest drag destination to
  the preceding row's content center. Edit-scope run `32826478232` passed the
  real reorder flow; no production reorder code changed.
- Full Native Mobile CI run `32827910559` was dispatched at `e43a00bf` with
  `capture_scope=full` and the live-revision preflight disabled. XcodeGen,
  iOS XCTest (257 tests), SwiftJCS boundaries, design snapshots, and the real
  iOS flow passed. The Watch test target failed to compile in
  `WatchBackendClientTests.swift` because a multiline raw JSON fixture used
  single-line raw-string delimiters; Watch XCTest and runtime screenshots were
  skipped. Test-only correction `c5f871b6` changes the fixture to a valid
  multiline raw string. No production Watch code changed.
- Full Native Mobile CI run `32832956274` was dispatched at `aa9f9616` with
  `capture_scope=full` and `require_live_preflight=false`. iOS XCTest (257
  tests), SwiftJCS boundaries, iOS snapshots, real iOS flow/video, and Watch
  simulator boot all passed. Watch target compilation then failed because the
  multiline fixture's opening/closing delimiters were on the same lines as
  JSON content (`WatchBackendClientTests.swift:334,351`); Watch XCTest and
  runtime screenshots were skipped. Correction `9bd4ce64` places both
  delimiters on their own lines. No production code changed.
- Full Native Mobile CI run `32837705596` at `bf84ea8a` passed. iOS XCTest
  executed 257 tests and Watch XCTest executed 315 tests, all with zero
  failures. XcodeGen, SwiftJCS boundary checks, iOS/Watch design snapshots,
  real iOS flow/video, and 11 Watch runtime seed/restore/interaction
  screenshots all passed secret-byte scans and uploaded successfully. The
  `watch-real-screenshots` artifact (ID `9561062102`, 289,202 bytes) and
  `native-build-evidence` artifact (ID `9561063172`, 452 bytes) are present
  and non-empty; runtime artifact zip digest is
  `4aa5db2479484c95d120b3cd0def14260c35d616387c4fc07472a909653d7f4d`.
- Read-only Half Moon Bay evidence was collected against revision
  `6a6080c6...` for rounds `17603881` (Ocean, 102, 58 shots) and `17601656`
  (Old, 96, 53 shots). Both have 18/18 hole details and shotmaps, matching
  shot counts/refs and sequential order; all maps are `prodgeometry`, GPS is
  complete, and no hole reports missing data or synthetic shots. The detailed
  checksums and remaining cross-client limits are in
  `docs/reviews/2026-08-25-r2-half-moon-bay-cross-client-evidence.md`; raw
  responses remain private under the homeserver project data directory.
- Current-head source CI run `32843227361` at `a4f80eb9` exposed two bounded
  integration regressions: one backend source-contract assertion still expects
  the pre-reorder XCUITest string, and Web build rejects a test fixture whose
  optional `map.image` no longer satisfies `CoursePrepHole`. Docker passed;
  Web component tests (601 passed, 7 skipped) and lint passed. No release or
  production state changed.
- Source CI run `32844906468` at `1f0bc607` passed all jobs: backend tests and
  private trial smoke, Web component tests (601 passed, 7 skipped), lint,
  TypeScript/Vite build, Playwright visual smoke, and both Docker image/health/
  geometry checks. The two fixes are test/fixture-only in `cf06d587`; production
  code and production revision were unchanged.
- Web-only runtime run `32845282260` at `1f0bc607` passed the real CI-player
  journey through the stable Funnel endpoint. Overview, time trends,
  performance, rounds list, review workbench, and round review all rendered;
  protected overview/detail/shotmap/topo requests returned 200, and the first
  live topo was course `3881` hole 1. The six PNGs are 1440x980 and non-empty;
  artifact `9562076813` is 828,730 bytes with zip SHA256
  `c7993aa100be4c4fbb12be135ed90c473fb5e76d6e5b744dc6a9f09871b8efe7`.
  Secret-byte scanning passed. This proves the stable Web transport and real
  player journey, not an iOS runtime or an HMB-specific cross-client match.
- Web ReviewWorkbench cache slice `6a865217` now persists only successful
  `found=true` maps for a short bounded window (player + round + hole key,
  geometry revision, 5-minute TTL, 24-entry/1.5 MB cap). Storage failures and
  malformed entries are ignored; failed/no-geometry responses are never stored;
  a successful correction evicts both persistent and in-memory entries. Focused
  Vitest was 24/24, lint had 0 errors with 2 pre-existing warnings, and build
  passed on homeserver.
- Source CI run `32847741048` at `769e3609` passed all jobs after that slice:
  backend/private trial, Web component tests (601 passed, 7 skipped), lint,
  TypeScript/Vite build, Playwright visual smoke, and Docker image/health/
  geometry checks.
- Current-head Web-only runtime run `32847990023` passed through the stable
  Funnel endpoint: overview/detail/shotmap/topo all returned 200, Playwright
  1/1 passed, and six 1440x980 PNGs passed secret-byte scanning. Artifact
  `9563119622` is 828,730 bytes with zip SHA256
  `81954f0a9065668fb6bbaac7885d709f9f33e3bdfa15f5d2c2a81b39abc850ec`.
- HMB Web runtime evidence completed on 2026-08-26 against the public Funnel
  revision `6a6080c6...`: owner-admin Playwright with `REVIEW_ROUND_REF=17603881`
  passed 1/1 in 25.6s. Overview, round detail, hole-1 shotmap (`found=true`,
  `globalId=6022`) and topo responses were all 200; six non-empty 1440x980 PNGs
  were 116,548--177,241 bytes and the admin-token secret-byte scan passed. The
  first browser attempt used the non-Funnel container token and got a protected
  endpoint 401/`net::ERR_FAILED`; the Funnel revision's candidate-container
  token resolved that revision mismatch. No token was logged or placed in URLs/
  screenshots, and no production write, deploy, restart, sync, or Funnel change
  occurred. The isolated remote directory, dependencies, outputs, and newly
  downloaded browser cache were removed; pre-existing shared cache remains.

- HMB iOS runtime run `32919313329` at head `e484ac37` passed: iOS XCTest
  257/257, RealFlow 1/1 (324.514s), ReviewEdit 1/1 (208.151s), TeeSelection
  7/7 (475.026s), selected 9/9 (1007.692s). Resolver evidence is round
  `17603881`, Half Moon Bay Ocean hole 1, `globalId/localHole=6022/1`,
  `shotCount=3`, clubs Driver/5I. The real-screenshots artifact contains 32
  non-empty PNGs; the separate design-snapshots artifact contains 30 files,
  and all native secret scans passed. Event-latency files are only
  `round-home.appear` proxies
  (pending=-1, course=31796, about 1.38--1.65s), not topo first-frame proof.
  ReviewEdit used default Cancel and RealFlow disabled event sync; no correction,
  sync, or other write occurred. Preflight was intentionally skipped by input.
- HMB club provenance is now proved read-only against the production data volume.
  Garmin Driver/3W/3H each have `adviceDistance=0` and `averageDistance=0`, and
  no manual bag is present. Current HEAD canonicalizes aliases and selects
  AutoShot history medians: Driver 197m/215yd (n=3155), 3W 171m/187yd (n=535),
  and 3H 159m/174yd (n=236), all `history_median` with high confidence. The
  production image's old ladder retains duplicate `3W`/`3号木杆` rows, uses
  `3号小鸡腿` for hybrid3, includes Putter, and has no provenance fields. The
  private evidence SHA is `04ef01cca74b075882abe43cff25a4791f58857c8017086bc0d99e9f7ea44e2e`.
- The production API recovered without intervention: on 2026-08-25 the
  `garmin-ai-caddie-api-1` container was `healthy`, local and public health GETs
  returned 200, and its `StartedAt` remained `2026-08-04T18:59:17Z`. No restart,
  deployment, synchronization, Funnel change, or production write occurred.
  R2 remains open only for owner screenshot approval, not backend club provenance
  or runtime technical evidence.
- GitHub Web-only HMB runtime run `32944143003` at head `8419840b` passed: job
  `98101156667` completed `1/1` in 39.8s and artifact `9597641080` contains
  six files (821,477 bytes). Overview/detail/shotmap/topo returned 200;
  shotmap found `true` with `globalId=6022`, `localHole=1`; topo holes 1/2
  were `image/png`. Secret scanning passed and the artifact zip SHA-256 is
  `d321b5816904214abcc37c1f231e02fb844ed7dc2a47e667d83d0b04f454f375`.
  Earlier runs `32942764978` and `32943661246` failed at the overview 60s
  transport wait; service diagnosis found no 5xx. Those failures are transport
  evidence gaps, not product errors. The successful GitHub run supersedes the
  homeserver owner-only run as the Web evidence source; that run remains
  supplementary history. R2 remains `evidence-open`, with only owner visual
  approval remaining; `REL` remains `blocked`.
- The R2 owner review page is publicly published at
  `https://caddie.taile36706.ts.net/demos/garmin-r2-owner-review-20260826/`.
  It contains exactly 39 public files (the index plus 38 PNGs); external
  verification returned HTTP 200 for the index and all image URLs, and the
  image SHA-256 values match the private staging copy. No production app route,
  data, or Funnel configuration was changed; this is a static evidence
  publication only. Watch evidence remains separate and is not implied by this
  page.
- Artifact-only release workflow `33024982596` at `ec73527f` passed on the
  GitHub macOS runner. XcodeGen, signing-secret presence, fastlane archive and
  IPA export all passed; the signed IPA artifact is `9628147722` (9,915,969
  bytes; zip digest `1eb0a823692db8bd72fc322fa3ca4437f844fb7764633e272b7970079798fc6d`).
  The log explicitly says `TestFlight upload was not requested`; no binary was
  uploaded to TestFlight.
- Phase 6 read-only audit `33024993745` passed as a workflow but reported an
  incomplete readiness state: all six signing secrets, the public HTTPS URL,
  App Store Connect metadata/review observations were ready, while the backend
  probe timed out and tester coverage/device installation remain manual. Direct
  read-only probes showed the production API at `127.0.0.1:9000` healthy, but
  the public Caddy `:8080` route and candidate host port `:39055` timed out.
  Caddy's current `/api/*` upstream is `127.0.0.1:39055` (candidate image
  `6a6080c0-candidate`, started 2026-08-21); no restart, route switch, or
  production write was performed. At that point REL remained blocked on ingress
  stability and the two manual gates; the later re-audit below supersedes the
  ingress portion of that observation.
- Homeserver ingress re-audit on 2026-08-27 was read-only: candidate `:39055`
  (20/20 HTTP 200, p50 19 ms, p95 37.5 ms), production `:9000` (20/20,
  p50 12 ms, p95 33.5 ms), Caddy `:8080` (20/20, p50 26.4 ms, p95 69.5 ms),
  and public Funnel (10/10, p50 219 ms, p95 579 ms). Candidate authenticated
  overview/round/shotmap requests returned 200. Caddy validation was `Valid`,
  no upstream errors appeared in the last 30 minutes, and no route/container/
  database mutation occurred. Candidate has no Docker healthcheck and uses a
  restart entrypoint that runs Alembic/identity seed against a writable shared
  database, so it was intentionally not restarted or replaced.
- Strict Phase 6 rerun `33029186839` at `10e1a7be` preserved the honest result:
  signing, URL, App Store metadata, and review gates were ready, but the
  GitHub-runner backend probe again returned `TimeoutError`; target tester
  assignment and physical iPhone/Watch installation remain manual-required.
  The run did not upload TestFlight. This runner-only timeout is now a separate
  evidence gap from the healthy homeserver/public probes and must be resolved
  or explicitly bounded before release; the successful rerun below supplies
  that additional evidence.
- Strict Phase 6 rerun `33029475105` at `30ab509f` passed the backend probe:
  the GitHub runner received HTTP 200 and the expected health/readiness schemas
  from `caddie.taile36706.ts.net`. Signing, URL, metadata, and review gates
  were ready; only target tester assignment and physical iPhone/Watch
  installation remained `manual_required`. The workflow failed solely because
  `fail_when_incomplete=true`; it did not upload TestFlight.
- Native Mobile CI run `33264517479` at exact HEAD
  `affb58df7ab875bc8f26ab0c87c609d9b7d254aa` completed successfully (job
  `99132103748`, status `success`); all 38 executed steps passed.
  The six retained artifacts and GitHub digests are: `design-snapshots`
  `sha256:75ad20a4668e24b2833fc43d3db85fefd1199a6c04734d02120a1e84460537c6`,
  `real-screenshots`
  `sha256:7953d14a46d6402a258f5c01388104758b377684e07fb7b45addca62822456b0`,
  `real-video`
  `sha256:fa2770f4dbcff756c86c8d36f663c2d76bc05a69045b76634e988d03f9bfe3b3`,
  `watch-snapshots`
  `sha256:6f1a5c04e54fed7f8acf6325e986889505173a45e0337f789e7c9b5d4e54a686`,
  `watch-real-screenshots`
  `sha256:05ae55ebadd9804082d331929989b8a09dd737d868ee06af3cc8954d9415b4c5`,
  and `native-build-evidence-ci-fixture`
  `sha256:e942ffd91c5578d0090a701785925fb44f468499ff014083a4d964b470010a76`.
  Fixture/preflight skips were expected; no production, signing, deployment,
  or TestFlight action occurred.
- Artifact-only iOS workflow `33266986490` at the same exact HEAD terminated
  in job `99138677684` before build: `fastlane/Fastfile:267` (and the paired
  line 268) used an invalid `unless` modifier inside an array literal. All
  setup/signing-secret checks passed; no IPA or provenance artifact was
  published and `upload_to_testflight=false` prevented any TestFlight action.
- Artifact-only iOS workflow `33268601901` at exact HEAD
  `1af378b811cd25edae12285c5745aef1b57d7faf` completed successfully (job
  `99142945097`, status `success`); `AICaddie-ipa` artifact ID `9719443927`
  is 9,940,801 bytes with GitHub/ZIP SHA-256
  `d42469f4a038fa13e69b28dc19cb135888ee3c2be3a49eccfc794914490a02f6`, and
  the independent IPA SHA-256 is
  `3948cb9ec2bd25ae001a96576916d631953adcf0b347cc968c1273019bf3a67b`.
  Provenance binds version `0.1.0`, build `44`, and API host
  `caddie.taile36706.ts.net`; `uploadRequested`, `uploadCompleted`, and
  `uploadToTestflight` are all false, with `backendRevision=null` by the
  artifact-only contract. No TestFlight upload occurred.
- Phase 6 readiness run `33268954572` at exact HEAD
  `1af378b811cd25edae12285c5745aef1b57d7faf` completed successfully (job
  `99143871021`, status `success`, `fail_when_incomplete=false`). Artifact
  `phase6-readiness-evidence` ID `9719506171` is 2,885 bytes with GitHub
  digest `sha256:a21f5b8eb52da41118098da43841e2d4cf60816b03163db6182fe22ea76efc0e`;
  downloaded readiness and roadmap JSON hashes are
  `6e2b91fd8591ba2f1f73f5376e40b12914907648802724d10dedcc0b9468f98f` and
  `1b0ebf63797678cb9982e92987ab5ba1096b4ec949c1121b778217d18763b2bd`.
  Health was HTTP 200 at backend revision `6a6080c6f6867513ed461d20e98a29113bd65433`;
  readiness was HTTP 200 with 15 valid checks and `degraded` status, but the
  deployed handler did not emit the explicit authenticated marker (the
  no/invalid-header response has zero checks). The overall state is
  `incomplete`: Beta Review readiness/submission, tester
  coverage, and iPhone/Watch installation remain `manual_required`, while
  release provenance is degraded for `upload_flag_false` as designed.

These are code/test facts, not proof of a physical Apple Watch Ultra session.

## Historical Deployment Decision Summary (2026-08-29; superseded 2026-09-02)

The following deployment decision records are retained for provenance. The
current candidate, deployment, and TestFlight state are in the summary above.

- **Revision boundary:** local canonical `HEAD` is `affb58df7ab875bc8f26ab0c87c609d9b7d254aa`; the protected origin branch is `1af378b811cd25edae12285c5745aef1b57d7faf`. The artifact-only IPA and Phase 6 evidence are already recorded above at `1af378b8` (IPA ZIP digest `d42469f4...`, independent IPA digest `3948cb9e...`; readiness artifact digest `a21f5b8e...`). The homeserver scratch `garmin-ai-caddie-rel-20260829` has no Git metadata and is a mixed snapshot, so it is not source provenance.
- **Running image is older:** `garmin-ai-caddie-api:6a6080c-candidate`, image `sha256:b035a77c4d70771ce5529f7898ce0a4a8a133965748f9607c729b37361bd3a03`, is labeled/deployed as backend revision `6a6080c6f6867513ed461d20e98a29113bd65433`. Its `/app/server_v2/main.py` matches that older revision and it has no course-reconciliation module; it is not the current candidate.
- **Preserve before replacement:** capture the current container/Caddy metadata and back up the writable volumes `garmin-ai-caddie_ai-caddie-private` (about 10.51 GB) and `garmin-ai-caddie_ai-caddie-pgdata` (about 48 MB). Preserve container `aicaddie-release-6a6080c-candidate`, port `127.0.0.1:39055 -> 9000`, and the recovery manifest. `ops/backup_data.sh` exports the selected private data plus a SQLite/`pg_dump` identity backup and writes a hashed manifest; it is not a raw volume clone.
- **Homeserver option:** after owner approval, build/tag the compatible candidate, stop/recreate only the API on the same volumes and port, and probe local, Caddy, and Funnel health. Boot runs bounded PostgreSQL readiness, `alembic upgrade head`, and identity seeding under a lock, so expect brief API downtime and migration risk. Rollback means recreating the preserved prior image/container with the same volumes/port; if a migration is not backward-compatible, restore the verified database snapshot rather than assuming image rollback is sufficient.
- **Fly option:** the manual `Backend Fly Deploy` workflow creates/uses a separate Fly app and `ai_caddie_private` volume, sets runtime secrets and `AI_CADDIE_BUILD_REVISION`, deploys with `flyctl deploy --remote-only`, and may mutate `AI_CADDIE_API_BASE_URL`; it has no backup or rollback step. It does not contain homeserver data and therefore must not be treated as a data-preserving replacement without an explicit import/owner decision.
- **Upload constraint:** the signed IPA is artifact-only (`backendRevision=null`, upload flags false). A connected upload requires an explicit backend revision/API-origin match and backend-health equality. Uploading this current app against the old public `6a6080c6...` backend would either fail the provenance gate or leave the course-reconciliation/client contract unproven; do not weaken the check or upload until a compatible backend is deployed or the app is rebuilt from the old revision.

## Historical Deployment/Native Blocker (2026-08-30; resolved 2026-09-02)

The credential/revision blocker below was resolved by the current backend and
Native runs recorded above; it is retained only as historical diagnosis.

- The deployed candidate is healthy at exact backend revision
  `1af378b811cd25edae12285c5745aef1b57d7faf`; the old `6a6080c6...` container
  and image are stopped and retained for rollback. The verified backup,
  container, image, and resource details are recorded above.
- A redacted homeserver comparison found the candidate container, preserved old
  container, and `/home/jason/watchreview/.env` all have length `64` and the
  same SHA-256 digest
  `61b3728ba1e2808aea5ce7328300efe334fda8fe00aa5e5a220bce545a8374319`.
  The `.env` token authenticated successfully to candidate, Caddy, and public
  Funnel `nearby` endpoints (HTTP 200, global ID `31793` present), so this is
  not a candidate-versus-old-container token difference.
- Native Mobile CI run `33293254635` used the public URL, exact app/backend
  revision, `fixture_mode=false`, and `require_live_preflight=true`. Health
  reached the expected revision, but live `/api/v2/courses/nearby` returned
  HTTP 401 from the preflight; the run stopped there and performed no release
  or TestFlight action. The GitHub log shows the admin token was injected and
  masked, but GitHub does not expose its bytes for comparison. The GitHub
  secret metadata says `AI_CADDIE_ADMIN_TOKEN` was last updated
  `2026-08-10T02:19:38Z`; therefore a stale/mismatched GitHub secret is the
  leading diagnosis, not a proven byte-level fact. Secret rotation requires a
  separate explicit side-effect record.

## Exact Next Actions

1. Run the broader remote Python regression suite from the current source
   scratch, including mobile, course-prep, decision, schema and topo tests.
2. Attempt the supported Swift/iOS/Watch native compile/test path; record a
   concrete pass or the environment limitation instead of inferring it from
   Python contracts.
3. If native gates pass, install the resulting internal candidate on the
   physical iPhone and paired Watch; verify map panning, the dedicated hazard
   list, one pole-foot flag, and selectable Driver/safe/stock/attack lines.
4. In the app, create a fresh Garmin session and tap reconnect once; confirm
   the state reads “已连接 · 同步完成” and that no-GPS/manual-search map and
   caddie flows remain usable. Do not call the diagnostic refresh endpoint.
5. Do not run external Beta Review, external tester distribution, production
   deployment, or synchronization as part of this handoff. Keep historical
   refs and any cleanup manifests until an explicit allow-listed cleanup
   decision is complete.

## Open Blockers / Facts

- Local machine is an editing/control plane; builds, Xcode, Playwright and
  other heavy work run on homeserver or GitHub Actions.
- Production promotion and synchronization remain gated on owner approval and
  physical-device evidence; do not trigger synchronization as a test.
- The focused green baked fixture is still 1024 px; do not stretch it and call
  it a 1280 px evidence asset.
- The public Funnel root route was restored on 2026-08-25 from
  `127.0.0.1:443` to `:8080` under user authorization; the route backup
  directory and before/after SHAs are recorded above. Public endpoint checks
  returned 200. The current public candidate is revision `caf3afad...`; the
  prior `ce4d41f0...` image/container is retained as the named rollback target. The
  current candidate deployment and its health evidence are recorded above.
- Physical iPhone/Watch installation, first-launch/start behavior, exact tester
  qualification, and external Beta Review remain unverified. CI and simulator
  evidence cannot close those hardware/account gates.
- One runtime evidence boundary remains open: deferred-finish network retry is
  still unit-test-only. Cancel completion and old-seed tombstone rejection are
  covered by run `32791049667`.
- Existing user files `.codex-tmp/` and
  `.mockups/watch-shot-tracking.html` are untracked and must be preserved.
- Keep historical Claude/superpowers worktrees unless a separate allow-list
  cleanup is explicitly authorized.
- The temporary current-head candidate, proxy, Quick Tunnel, overlay mount,
  and scratch directory from run `32806892801` were removed after evidence
  collection; public `39055`/Caddy/Funnel health remained unchanged.

## Operating Rules

- At most one modifying implementation agent and one read-only review snapshot.
- Every delegated task returns its worktree, commit, tests, resources and
  cleanup result. Temporary resources are removed by their creator.
- Update this file only when a task changes state, evidence, blocker, or the
  current slice changes. Add a dated one-line entry below; do not paste full
  command logs here.
- After context compression, read this file first, then run lightweight
  `git status`, `git log -8`, and agent-status checks. Do not recreate a new
  master checklist from memory.

## State Changes

- 2026-09-09: Fresh Native Mobile CI `34407853548` was dispatched from
  `integration/v2` head `158c1db5` (product-code tip `b9ff8b9d`) with
  `capture_scope=full`, live API
  `https://suggests-kilometers-normal-insertion.trycloudflare.com`, and
  backend revision `6d130528`. The run is still in progress; no TestFlight,
  signing, or distribution side effect was started.

- 2026-09-09: Native Mobile CI `34406253005` reached all Watch build/runtime evidence
  and failed only at the iOS app target with Swift access-control errors in
  `CoursePrep.swift:158`: a public default argument referenced internal
  `GeoDistance` symbols. The minimal fix is `b9ff8b9d`, which exposes the
  route-distance default through `CoursePrepLiveHazardReadout` without making
  the math helper public. A fresh Native run against `b9ff8b9d` is required;
  no release side effect was performed.

- 2026-09-09: Context recovery confirmed the sole active slice remains
  `PHONE-UX2`; the durable source tip is `b9ff8b9d` (the previous
  `a44f1c9f` entry was stale). The next action is a fresh Native Mobile CI
  run against `b9ff8b9d`; no TestFlight or other release side effect is
  authorized before its native/device evidence is complete.

- 2026-09-09: `PHONE-UX2` focused verification was rerun in the documented
  homeserver-only environment using scratch
  `/home/jason/codex-runs/garmin-ai-caddie-phone-ux2-20260909-b`, a read-only
  source mount, and ephemeral `/tmp`, `data`, and `output` tmpfs layers. The
  suite ran `374` tests with `5` skips and exited `0`. The earlier failed
  attempt had `122` environment errors because a fully read-only container
  lacked a temporary directory and event-store write layer; no source or
  persistent homeserver data was changed. Native/device evidence remains the
  next gate.

- 2026-09-09: `SNAPSHOT-BLOAT` completed. Derived shared geometry is now
  excluded from new durable snapshots and portable exports, with dependency
  metadata retained and legacy archive import preserved. The exact allow-list
  removed 16 per-snapshot geometry directories (`34,241,567,932` bytes) while
  retaining nine raw-data snapshots and the top-level geometry store. Candidate
  API revision `6d130528` is healthy; the scheduled sync completed afterward
  and produced no snapshot geometry. Homeserver README and cleanup evidence were
  updated; no mobile/TestFlight release side effect was performed.

- 2026-09-09: `PHONE-UX2` moved from `in-progress` to `evidence-open` after
  Source CI `34316491467`, Native Mobile CI `34316964148`, TestFlight CD
  `34323088795`, and read-only Apple check `34324271971` all passed at source
  `a44f1c9f`. Build 54 is the current internal handoff against backend
  `325cc2f3`; the remaining gate is physical iPhone/Watch validation. The
  quick tunnel remains available for that evidence. No external distribution,
  Beta Review submission, or production promotion occurred.

- 2026-09-09: `PHONE-UX2` follow-up implementation passed the focused remote
  contract suite (`373` tests, `5` skips, exit 0), including course prep,
  decision selection, mobile package/server paths, topo rendering, mobile
  contracts, and CI fixtures. The broader discovery run found `4` failures,
  `18` errors, and `13` skips only because its validation container lacks
  `git` and excludes `.env`, `data`, and `output`; those authority, auth, and
  persistence checks are environment-limited rather than product evidence.
  Same-club authorization is now scoped per canonical club group; sparse Par
  4/5 Driver bags expose three line modes with one measured carry. The fresh
  native build/device run remains open; no release or deployment side effect
  was performed. Test scratch
  `/home/jason/codex-runs/garmin-ai-caddie-phone-ux2-20260909-b` is a temporary
  read-only mount with no persistent service and is retained until final
  verification/allow-listed cleanup.

- 2026-09-08: `PHONE-REGRESSION` moved from `in-progress` to `evidence-open`
  after Source CI `34223501012`, Native Mobile CI `34223836622`, backend
  revision `f363872f`, TestFlight CD `34231106418`, and read-only Apple check
  `34232120285` all passed. Build 53 is the current internal handoff; the
  remaining work is fresh physical Garmin reconnect/sync, iPhone/Watch install,
  and held-loupe/S70 evidence. External distribution and production remain
  unchanged.

- 2026-09-06: Garmin login verification failure was isolated to Garmin CN's
  same-origin gateway check: the old authenticated request returned 403 and
  the same Cookie/CSRF request with browser fetch metadata returned 200.
  Commit `caf3afad` added the headers and regression test; Source CI
  `34043175968` passed and the healthy public backend now reports that exact
  revision. `GARMIN-AUTH` remained the sole active slice while Native,
  TestFlight, and read-only Apple verification ran in order; those gates are
  now complete and the slice is `evidence-open` only for real-device proof.
- 2026-09-06: TestFlight build 50 from `4bca0f2e` was uploaded by CD run
  `34040432333`; read-only ASC run `34040896324` reported `VALID`, unexpired,
  `IN_BETA_TESTING`, and included in the internal `Jason's friends` group.
  It predates backend revision `caf3afad`, so it is not the final auth-fix
  handoff candidate.
- 2026-09-06: Native Mobile CI `34045077006` passed all live iOS/Watch steps
  at `caf3afad`; TestFlight CD `34048458619` uploaded/processed build 51 with
  exact API/backend provenance; read-only Apple/group check `34048981151`
  confirmed `VALID`, unexpired, internal-beta visibility. External distribution
  and production state were unchanged; the remaining gate is one fresh Garmin
  reconnect plus physical iPhone/Watch evidence.
- 2026-09-06: Physical TestFlight build-48 screenshots reproduced stale
  course-loop labels, incorrect Touch Target/caddie path geometry, duplicate
  5i/6i landing placement, redundant live-play controls, and missing
  horizontal hole navigation. `MAP1` returned to `in-progress`; fresh source,
  Native, and internal TestFlight evidence is required before hardware handoff.
- 2026-09-06: MAP1 product/test commit `5628cc6d` reconciles stale A/B/C loop
  metadata, interpolates club landing pixels, draws explicit Tee-to-landing and
  landing-to-flag arcs, restores the missing Touch Target first leg, keeps
  moved pixel-only flags authoritative, hides the live media card and redundant
  map rows, and adds live/review horizontal hole navigation. The source and
  Native gates are recorded below; build 49 was the then-current
  hardware-handoff candidate and has since been superseded by build 51.
- 2026-09-06: User-provided screenshots `IMG_7757.png` through `IMG_7762.png`
  were located at `/home/ubuntu/` and verified as the original build-48
  feedback set: stale A/B/C labels, missing Touch Target first leg, duplicate
  5i/6i placement, single caddie path, and redundant live controls.
- 2026-09-06: MAP1 Source CI `34021727402` and Native Mobile CI `34021862658`
  passed at `c11ddf33`; no new product-code changes were required after the
  screenshot review.
- 2026-09-06: Internal upload attempt `34024843660` timed out during the
  authenticated backend preflight before Apple upload; ASC listing
  `34025526071` confirmed build 49 did not exist. A retry `34025628804` then
  uploaded and processed build 49, and ASC listing `34026097416` confirmed it
  is valid and visible in `Jason's friends`; external `Private Trial` was not
  changed. `MAP1` and `REL` remain evidence-open for physical iPhone/Watch
  installation and interaction proof.
- 2026-09-04: Fable 5.1 re-evaluated the branch topology. The old
  `integration/v2` line has 46 unique historical commits while MAP1 has 287;
  the safe decision was a history-preserving normal merge with MAP1's tested
  tree canonical, not a replay or force-reset. PR #331 merged as
  `1775d87a7a3eb2ac3c879bb81f07406ef28dd760` (old integration first parent,
  reconciliation/MAP1 second parent); both branch tips are ancestors, and the
  default branch remains `integration/v2`. Fable's follow-up inventory
  classified the 268 remote refs and deferred all deletion or rename work until
  the Cloud audit and owner gates are complete; details are in
  `docs/operations/branch-strategy-20260904.md`.
- 2026-09-04: The first reconciliation CI scan exposed a test-fixture setup
  error (a temporary authority fixture omitted its manifest), not a product
  regression. `a331281a` initialized that manifest; Source CI `33832029115`
  and Native Mobile CI `33832029223` then passed all required jobs. The active
  live-round contract authority correction and focused regression test are now
  part of the merged tree.
- 2026-09-04: Reconciliation changed no release or runtime state. TestFlight,
  backend, and source tags remain pinned; no upload, deployment, external
  distribution, synchronization, or production data write occurred. Started
  the prior Codex-only whole-repository inspection from the recorded temporary
  snapshot; `REL` and `MAP1` hardware evidence remain open.
- 2026-09-04: Prior Codex-only audit snapshot lifecycle recorded before delegation:
  `/dev/shm/garmin-ai-caddie-cloud-audit-20260904`, owner Codex,
  created `03:29:05Z`, expiry `2026-09-05T03:29:05Z`, no containers/services/
  ports/dependencies. The initial temporary report hash was
  `484791a4d00b1ac5ba1bf6fddd2d7de428e6913941f9607472e3d0bc19817889`; the
  corrected repository archive hash is
  `1380b1659502377eb3f6f755ff1b987f14efdf5dddf4bc484640363e3fb12819`.
  The report is archived in `docs/reviews/2026-09-04-cloud-whole-repository-audit.md`,
  and the temporary snapshot/report were removed by allow-list cleanup.
- 2026-09-04: The prior Codex-only inspection's only finding was the P2
  parent-order wording error in the pre-audit state snapshot. The live state
  and branch strategy records now state that `1775d87a` has old integration as
  first parent and MAP1 as second; no runtime or product-code finding was
  reported. At that earlier point homeserver Fable 5.1 was not used because
  its capacity check showed about 6.5 GiB free, below the project's 10 GiB
  start threshold.
- 2026-09-04: Homeserver Claude Fable 5.1 completed a separate corrected
  source-only whole-repository audit (session
  `98bd77e3-c841-4ca2-86ee-91a1001b5382`; model usage only
  `claude-fable-5-1`). The report is archived at
  `docs/reviews/2026-09-04-claude-fable-5-1-whole-repository-audit.md`; raw
  JSON is retained under the homeserver project archive with SHA-256
  `50b56130e2b9c29920bf9061b461a539b0cad08902d47d13aad460c416553440`;
  the report source copy has SHA-256
  `4ee5814afad50fbb085803da3c8cfcef50c343255b9cc52397b8035aed98e603`.
  The temporary snapshot, launchers, and report copy were removed after
  handoff; no containers, services, ports, dependencies, release actions, or
  source edits were created by Fable.
- 2026-09-05: Applied the bounded P2 follow-up from the Fable report on the
  canonical `integration/v2` working tree. No-GPS phone distances now state
  their Tee/static-reference semantics; `live_round_event.schema.json` and
  the server fairway validator are covered by parity/accept-reject checks; and
  XCUITest journeys cover manual no-GPS start → map/caddie/Touch Target/View
  Green zoom plus added-shot precision zoom/confirm. The Cloud archive report
  hash was corrected to
  `1380b1659502377eb3f6f755ff1b987f14efdf5dddf4bc484640363e3fb12819`.
  Local AST/JSON/diff checks and a read-only Pydantic smoke in the existing API
  container passed. Homeserver capacity was about 5.9 GiB, so no new heavy
  test/build/native session ran; no push, deployment, synchronization, or
  TestFlight action occurred.
- 2026-09-05: Ran the earlier current-head iOS TestFlight CD workflow
  `33977405908` from `8e13623d` in artifact-only mode. The signed build 48 and
  provenance passed; IPA SHA-256 is
  `479dc3e3298e3f8527458752f7a33e2ef22d11d79176047be075d556d24ceafc`, and
  GitHub artifact `9972807230` has ZIP digest
  `5422bcf511eb3933264dbd7d31c0ff2a865eddc8a2feb114cbb49cb1bcf50829`.
  Provenance confirms all TestFlight upload flags are false; no Apple upload,
  deployment, synchronization, or production data write occurred.
- 2026-09-06: Ran the standing internal hardware-validation upload from
  canonical `integration/v2` tip `b4aa9a71` as TestFlight CD run
  `34012329292`. The authenticated health/schema/revision checks passed under
  `test_environment_upload=true`; Apple processed build `0.1.0 (48)` and the
  workflow recorded `uploadToTestflight=true`. IPA SHA-256 is
  `1b1febfdb3919694c1dbf92e818f97f29f65d931cccd0eb7672e31b97276abef`.
  The follow-up read-only ASC listing run `34012813699` confirmed build 48 in
  the existing internal group and absent from `Private Trial`. No external
  distribution, Beta Review submission, production deployment, synchronization,
  or production data write occurred.
- 2026-09-02: MAP1 implementation and its focused contract coverage are integrated at
  source baseline `d189b3b4`; focused homeserver contracts pass 147/147 and
  source CI `33680857200` is green. The map-first no-GPS start, factual
  `teeBox=unknown` handling, phone map/caddie flow, manual map distance
  placement, and S70-style drag loupes for Touch Target, Green View, and
  review edits are present in source and focused tests. Full end-to-end
  no-GPS gesture coverage remains open per the 2026-09-04 Fable audit.
- 2026-09-02: Deployed the compatible backend candidate from
  `/home/jason/codex-runs/garmin-ai-caddie-map1-deploy-20260902` at revision
  `c16488911038d7e5b47ec310d1aaf05ca29950df`; health and authenticated course
  `31793` package probes passed. Native Mobile CI `33680501425` passed all 38
  steps, including iOS/Watch runtime evidence and Watch screenshots.
- 2026-09-02: TestFlight CD `33686521143` uploaded and Apple processed build
  `0.1.0 (47)` from `d189b3b4`; IPA SHA-256 is
  `19936b224428aa2e740fc7b277f26b80f91c52b44c567b75cbe310349db4f3ad`.
  Exact artifact diagnostics `33687517758` passed. ASC status `33687613975`
  confirms build 47 is valid and included in the internal all-builds group;
  it is not assigned to the external `Private Trial` group.
- 2026-09-02: Phase 6 audit `33687800258` passed provenance/backend/signing/API
  checks but remains `incomplete` by design. External Beta Review, tester
  coverage, and physical iPhone/Watch installation and first launch are still
  open; `install_verified=false`. No new build or external distribution was
  triggered.
- 2026-08-30: Completed a scoped capacity cleanup with immutable manifests.
  Removed 54 old Garmin artifact-only `codex-runs` entries (2.89 GiB total,
  including one root-owned entry removed through a separately recorded exact
  path) and 214 old Garmin/Phase 6/TestFlight `/tmp` entries (0.879 GiB).
  The historical S70/review material was archived at
  `/home/jason/garmin-ai-caddie-data/archives/garmin-legacy-review-20260830T0958Z.tar.zst`
  (SHA-256 `e47200277282ebf9d4fac088a41a68e9b60f2f498daa1eaaa44f5e4ae1b389c5`).
  All 35 Git-backed Garmin snapshots, including dirty snapshots, were kept;
  other-project directories/processes, `/home/ubuntu/.codex/sessions` and
  Codex databases, persistent volumes, images, and shared BuildKit cache were
  not changed. Manifests are under
  `/home/jason/garmin-ai-caddie-data/cleanup-manifests/20260830T0958Z-*` and
  the local `/home/ubuntu/claude-web-data/repo/garmin-ai-caddie/.codex-tmp/local-cleanup-20260830`.
  The hard protection rules were also added to `/home/ubuntu/HOMESERVER.md`
  and copied to `/home/jason/HOMESERVER.md`.

- 2026-08-28: Adopted the shared-runtime rule: remote verification uses the
  immutable project API image's read-only `/app/.venv`; the only host fallback
  is the lock-protected `/home/jason/garmin-ai-caddie-data/venvs/garmin-ai-caddie-ci`.
  No dependency installation is allowed inside a worktree. After the release
  candidate was integrated as `1d0f352b`, removed the clean local release
  worktree and its unused remote `.venv`. A timestamped allow-list manifest
  with SHA-256 `cb05bd62b828656f8392b643c2d7055e668488b4c5e4f6620496454ff1ed0b77`
  records eight stale duplicated remote `.claude/worktrees` trees (about 7.2
  GiB) removed after an open-file scan found no references. The unused remote
  candidate venv was separately removed under manifest SHA-256
  `8763a358a31e6a24f98e1cb4b657560b83865fca7afce6a0b9fdfc09775b7de3`.
  Remote free space rose to about 29 GiB. The remaining local worktrees contain uncommitted
  user/history artifacts and are retained; other projects' remote directories
  and services were not touched.

- 2026-08-24: Replaced the chat-sized plan with stable task IDs and set `R1`
  as the only queued next slice. Echo-style shell output is intentionally not
  tracked as project state.
- 2026-08-24: Started bounded `R1`; no other modifying task is active.
- 2026-08-24: Integrated `a1b88a2e`; CI `32689037776` passed Docker but exposed
  one Web fixture failure and two backend assertion failures. Fixes are queued
  one modifying agent at a time.
- 2026-08-25: Integrated bounded CI contract fix `cf06d587` as `1f0bc607`,
  pushed the canonical branch, and passed source CI `32844906468`; R2 now has
  a green source baseline and remains open only for real Web/iOS evidence and
  the documented parity/cache gaps.
- 2026-08-25: Stable Funnel Web runtime evidence passed in run `32845282260`;
  the prior Quick Tunnel transport failure is closed for Web. R2 remains open
  for HMB cross-client parity, iOS runtime evidence, and the explicitly scoped
  cache/provenance gaps.
- 2026-08-25: Integrated Web review cache `6a865217` as `769e3609`; source CI
  `32847741048` and current-head stable Web runtime `32847990023` both passed.
  R2 remains open only for the documented HMB/iOS cross-client and provenance
  evidence, plus owner visual approval.
- 2026-08-26: GitHub Web-only HMB run `32944143003` passed at head `8419840b`
  (job `98101156667`, artifact `9597641080`, `1/1` in 39.8s). The first two
  runs failed at the overview 60s transport wait, with no service 5xx found;
  the third run is successful Web evidence, while owner visual approval stays
  open and `REL` stays blocked.
- 2026-08-24: Integrated backend test-contract fix `46aad448` and Web fixture
  fix `2ca27720`; awaiting a matching green CI run.
- 2026-08-24: Integrated visual fixture correction `edf41054`; CI
  `32690671928` at `b6ecee8f` is green across all three jobs. The code batch is
  closed; runtime/product evidence remains open.
- 2026-08-24: Closed `R1` as done with commits `3eed2c56`, `82538984`,
  `bfc6bb57`, `de11b5db`, and `b1b86af7`; focused/full Web tests, build/lint,
  history visual smoke, and final remote review-editor interaction passed;
  temporary browser resources were cleaned up. Started `W1` as the sole
  in-progress slice.
- 2026-08-24: W1 runtime code reached `evidence-open`: run `32707001002` at
  head `ca2b2d7a` succeeded for 41/45/49 mm and five recovery markers, while
  the production journey remained open after an external API 502 and the
  three evidence boundaries listed above.
- 2026-08-24: Read-only homeserver diagnosis confirmed the 502 is caused by
  Funnel root -> `127.0.0.1:443` while project Caddy listens on `:8080`; no
  routing change was made.
- 2026-08-25: Integrated `84a53752` and verified its bounded recovery harness
  in GitHub run `32791049667`; W1 remains evidence-open because production
  18-hole/current-head evidence and deferred-finish network retry runtime
  evidence are still open.
- 2026-08-25: CI run `32796906679` passed frontend, backend, and Docker at
  `8a3ee8ba`; W1 remains evidence-open with the external API 502 blocker and
  current-head production journey still required.
- 2026-08-25: Under user authorization, restored the public Funnel root from
  `127.0.0.1:443` to `:8080`; backups are in
  `/home/jason/garmin-ai-caddie-data/operations/funnel-backups` (before
  `6f1bc4...`, after `3ea52c...`). Public `/`, `/api/v2/health`, `/sat/`,
  `/yoyo/`, `/demos/`, and `/yoyo-api/health` checks returned 200; W1 can
  continue its production 18-hole journey, with deferred-finish retry still
  unit-test-only.
- 2026-08-25: Watch runtime run `32801079395` at `8a3ee8ba` passed 41/49 mm,
  but Preflight live course discovery failed on backend revision mismatch
  (`6a6080c6...` public vs `8a3ee8ba` expected). W1 remains evidence-open and
  requires user authorization to deploy/switch the current-head candidate;
  deferred-finish retry remains unit-test-only.
- 2026-08-25: Run `32806892801` closed the W1 Watch runtime journey at
  `8a3ee8ba`; 18-hole/install/restore/history-edit/finish evidence and Cancel
  plus abandon recovery markers passed. The optional Web job failed through
  the temporary Quick Tunnel with `net::ERR_FAILED`; W1 is nevertheless done,
  and S1 is now the queued next slice. All run-created remote resources were
  cleaned up and public revision/route checks remained unchanged.
- 2026-08-25: Closed W1 and started S1 as the sole in-progress slice; the first
  S1 action is a read-only data-flow audit, with no implementation or
  production synchronization authorized yet.
- 2026-08-25: S1 audit completed without code changes. It confirmed the
  cross-client readiness-contract gap and the spaced Garmin club-name/source
  gap; the next work is two bounded implementation slices with focused tests.
- 2026-08-25: S1 provenance slice merged as `85acb022`; manual-bag cache,
  unresolved-source correction, and history-alias tie-break merged as
  `bc9ab55e`/`fb1c1287`. Delegated homeserver gates passed (78 backend focused
  tests, 2 geometry skips; Web focused tests/build);
  native iOS/Watch evidence is still pending.
- 2026-08-25: Integrated Watch install-status slice `11c28972` from delegated
  commit `b4688e8a`. Native run `32817814200` passed the iOS unit/design gates
  but failed the real search flow at line 292 because the keyboard remained
  visible; Watch stages were skipped. A bounded focus-dismissal fix is now the
  sole active implementation task before the next native run.
- 2026-08-25: Integrated keyboard-focus fix `bf944100` from delegated commit
  `44ba73fb`; it synchronously clears the search field before all three search
  entry paths. Review-scope run `32821984671` passed the complete RealFlow
  search/review journey but failed the ReviewEdit reorder assertion at line
  289; a second bounded delegated worktree is investigating that behavior.
- 2026-08-25: Test-only reorder fix `5fdb9fff` (delegated `ef5261d2`) changed
  the XCUITest drag destination from a second reorder handle to the preceding
  row content. Edit-scope run `32826478232` passed; the full native Watch gate
  is next.
- 2026-08-25: Pushed integrated head `e43a00bf` and dispatched full Native run
  `32827910559` with `capture_scope=full` and `require_live_preflight=false`;
  production revision remains unchanged. The run passed all iOS stages but
  failed Watch compilation on the malformed multiline raw JSON fixture, so no
  Watch XCTest/runtime claim was made.
- 2026-08-25: Integrated test-only Watch fixture correction `c5f871b6` from a
  delegated worktree. The fixture now uses valid multiline raw-string
  delimiters; the next action is a fresh full Native run.
- 2026-08-25: Full Native run `32832956274` at `aa9f9616` passed all iOS
  stages and Watch simulator boot, but Watch compilation still rejected the
  fixture because Swift requires multiline content and closing delimiters to
  start on their own lines. Integrated the bounded test-only correction
  `9bd4ce64`; no Watch runtime evidence is claimed until the next run.
- 2026-08-25: Full Native run `32837705596` at `bf84ea8a` passed all iOS and
  Watch tests, design/runtime screenshot gates, secret scans, and artifact
  uploads. Closed S1 and started R2 as the sole in-progress slice; production
  revision and TestFlight state remain unchanged.
- 2026-08-25: Collected read-only HMB round/shotmap evidence for `17603881`
  and `17601656`; both are complete and `prodgeometry`-backed. Added the
  durable summary in `docs/reviews/2026-08-25-r2-half-moon-bay-cross-client-evidence.md`.
  Current-head CI `32843227361` then found one stale backend contract assertion
  and one Web fixture type error; a single bounded fix agent is handling those
  before R2 runtime evidence continues.
- 2026-08-25: Corrected the bounded HMB provenance probe with a current-HEAD,
  network-disabled container over the production volume mounted read-only. The
  Garmin bag is non-empty but its Driver/3W/3H advice/average values are zero;
  current HEAD selects the real AutoShot medians with provenance, while the
  production image's old ladder has alias duplication, Putter contamination,
  and no provenance. The production API also returned to healthy without a
  restart (`StartedAt` unchanged). R2 stays `evidence-open` only for real HMB
  iOS/Web parity and owner approval; no production/Funnel/sync mutation occurred.
- 2026-08-26: Owner said `go` after the public R2 comparison page was verified;
  interpreted as approval of the R2 evidence gate. Closed R2 and started REL
  as the sole active slice. The next action is an artifact-only release audit;
  no TestFlight upload, production deployment, synchronization, or Funnel
  change is authorized by this state transition.
- 2026-08-27: Artifact-only release run `33024982596` passed and produced a
  signed IPA without uploading. The initial Phase 6 run `33024993745` reported
  an ingress timeout; the subsequent read-only homeserver audit showed the
  route healthy. Strict rerun `33029186839` reproduced a runner timeout once,
  while `33029475105` passed the backend probe. No route/container/data
  mutation was made; REL remains open only for revision consistency and the
  manual tester/device gates.
- 2026-08-27: Native rerun `33074266179` at `d2cacff7` passed deterministic iOS
  gates but failed live XCUITest execution: two public history-request timeouts
  and one authorized-GPS tee-selector availability assertion. Screenshot,
  design-snapshot, and video artifacts uploaded; Watch runtime stages were
  skipped. No product code change was made pending focused reproduction.
- 2026-08-27: Diagnosed the authorized-GPS failure as a real no-cache startup
  sequencing bug: Phase 2 network refresh held the root loading gate, hiding
  the new-round fallback for up to the request timeout. Added the minimal
  post-Phase-1 `isBootstrapping = false` fix in `AICaddieApp.swift`; remote
  homeserver Python compileall passed, while Swift/Xcode verification remains
  pending on Native CI.
- 2026-08-27: Native rerun `33077525178` at `7002c5f5` verified the startup fix:
  the no-fix fallback and all seven TeeSelection tests passed. Review and
  review-edit flows failed immediately with `noEligibleRound` at the resolver,
  indicating missing qualifying live history evidence rather than transport,
  simulator, or UI failures. Artifacts uploaded were real-video (77,004,282
  bytes), real-screenshots (3,948,540 bytes), and design-snapshots (3,699,371
  bytes); Watch runtime stages were skipped. No production data or release
  workflow was changed.
- 2026-08-27: Native rerun `33082852454` at `65b47180` passed deterministic iOS
  gates and the live `RealFlow` and `ReviewEdit` journeys. Six of seven
  TeeSelection tests passed; `testDeniedGPSStillOffersCatalogueSearchInsteadOfHistory`
  failed at `TeeSelectionUITests.swift:242` with an `XCTAssertTrue` failure.
  The run uploaded real-video (228,180,095 bytes), real-screenshots
  (49,535,922 bytes), and design-snapshots (3,699,371 bytes). Watch setup and
  runtime stages were skipped after the live iOS step failed, so Watch remains
  unverified. No product, production-data, or release-workflow change was made.
- 2026-08-27: Audited the denied-GPS failure at `dc308361`. The catalogue row
  `course-catalog-result-31793` was found and tapped, while the following
  `start-round-course-segment-31793` row never appeared within 12 seconds.
  `MobileCourseSearchMatch.courseOption`, `selectSearchResult`, and
  `segmentRow` all preserve the same global ID, so no fixture-ID or
  accessibility-label mismatch is established. The failure is currently an
  isolated live SwiftUI state/navigation timing issue; no timeout relaxation,
  assertion weakening, or product change is justified without a focused
  reproduction. Remote exact-SHA Python compileall and `git diff --check`
  passed; the temporary scratch was removed.
- 2026-08-27: Bounded artifact trace of run `33082852454` refined the failure
  classification. In the denied-GPS process, city-only search returned a long
  virtualized SwiftUI List; the 31793 row was visible near 93% scroll position
  and the XCTest log confirmed a tap on `course-catalog-result-31793`. No API,
  permission, Task cancellation, or package/Tee error followed, but the
  post-dismissal StartRound tree contained no segment row. Keyword-search
  cases with shorter result sets passed. This is consistent with a
  scroll/virtualization locator-action race in the test path, not a proven
  product semantic failure. The 50 MB screenshot artifact and 155 MB app log
  were inspected only for this trace and then deleted; no source change or
  rerun was made.
- 2026-08-27: Implemented the independent backend revision contract in Native
  and Watch workflows. Both now accept an auditable `backend_revision`
  dispatch input, falling back only to protected `AI_CADDIE_BACKEND_REVISION`,
  while passing app SHA separately as `AI_CADDIE_PREFLIGHT_APP_REVISION`.
  Preflight rejects missing/non-40-hex revisions, retains the
  `ai-caddie-health-v2` schema gate, and records independent app/backend IDs.
  Remote exact-SHA compilation and the focused preflight suite passed 7/7.
  The broader CI workflow suite passed 37/38; its sole failure was the remote
  environment missing the pre-existing `pathspec` dependency in a canonical
  authority test. A read-only public health probe still reports backend
  `6a6080c6...`; no Native rerun, production deployment, restart, release,
  signing, or upload was performed.
- 2026-08-27: Native Mobile CI run `33092239960` was dispatched with explicit
  `api_base_url=https://caddie.taile36706.ts.net` and backend revision
  `6a6080c6...`; its head was app/workflow SHA
  `27ab374275c822f4274b062017219ab7c9bf55d9`. XcodeGen, all deterministic
  iOS tests, SwiftJCS boundaries, design snapshots, preflight, and all seven
  `TeeSelectionUITests` passed, including
  `testDeniedGPSStillOffersCatalogueSearchInsteadOfHistory`. RealFlow and
  ReviewEdit each failed with `noEligibleRound` in
  `RealEvidenceRoundResolver.swift:208`, so Watch runtime stages were skipped.
  This is missing qualifying live history evidence, not a source or endpoint
  contract failure. The run uploaded a real video of 77,030,383 bytes; no
  large artifact was retained locally. No release, deploy, signing, or upload
  workflow was dispatched.
- 2026-08-27: Evaluated the remaining `noEligibleRound` fixture gap. The
  resolver contract requires one non-manual history round with a scored hole,
  at least two non-`Unknown` club-labelled shots in that hole's detail, and a
  matching shotmap with usable image/overlay geometry plus two non-synthetic
  spatially separated landings. Existing repository fixtures such as
  `shots_scatter_round.json` are synthetic Garmin-shaped data and are not an
  HTTP history/detail/shotmap service; the existing DEBUG round-ref seed still
  depends on a backend round and does not inject fixture state into iOS.
  A CI-only mock would need to implement the full history, geometry, package,
  caddie, and media surface used by RealFlow/ReviewEdit, so it is not a
  bounded safe change for this slice. No fixture implementation or Native
  rerun was made. The next defensible option is an owner-authorized,
  isolated CI backend/fixture endpoint (with explicit URL and token) that
  serves this contract without writing production history; otherwise the
  live review gate remains blocked on qualifying backend history evidence.
- 2026-08-27: Added fail-closed resolver diagnostics without changing the
  evidence contract or the 24 shot-map request budget. Each inspected round
  now records an auditable rejection reason (missing scored/labelled shots,
  shot-map or geometry/image mismatch, insufficient or non-separated recorded
  landings, and budget exhaustion); RealFlow and ReviewEdit persist these
  diagnostics when resolution fails. Native Watch validation and runtime
  capture now use `always()` conditions so an iOS live-review failure does not
  short-circuit independent Watch validation, while native evidence reports
  Watch test failure rather than falsely marking it passed. App and backend
  revisions remain independent. Live validation still uses the explicit
  backend URL/token; fixture validation remains an isolated, opt-in path and
  no Native workflow was dispatched by this change.
- 2026-08-27: Added the opt-in CI fixture HTTP seam. `AI_CADDIE_FIXTURE_MODE=1`
  registers only the non-production fixture router, which serves deterministic
  health, readiness, history/detail/shotmap, course search/nearby/prep,
  geometry, mobile package, caddie context, media, and review-read endpoints.
  Responses carry `dataMode=ci_fixture`, `source=non_production`, and a fixed
  fixture revision; Native fixture evidence uses a distinct schema and artifact
  name. The launcher is CI/debug-only, private-token-only, loopback-only, and
  the workflow waits for health and verifies shutdown. Live mode and its
  explicit backend revision gate remain unchanged. This is a bounded skeleton
  pending Opus review; no Native dispatch or production action was performed.
- 2026-08-27: Closed the four Opus P1 fixture findings in the bounded fixture
  implementation: the options/nearby/search producers now leave course `31795`
  eligible for `NewCourseEvidenceResolver`; iOS/Watch tee payloads include the
  complete Codable row shape; mobile stats plus overview/sync/install bootstrap
  reads are fixture-backed; and fixture route isolation uses exact or
  parameterized full-path matching with unknown nested paths failing closed.
  Package normalization recursively binds round/course references to `900001` /
  `31795` while retaining `ci_fixture`/`non_production` markers. Producer,
  strict tee, package, compile, and diff-check evidence passed locally and on
  the homeserver; the workflow contract run remains environment-limited by a
  missing `pathspec` dependency. Current status: awaiting Opus re-review; no
  Native dispatch, deployment, release, signing, or upload was performed.
- 2026-08-27: Closed the remaining fixture P1 entity-binding finding. Package,
  course-prep/tees/install, geometry, and shot-map fixture routes now validate
  requested course `31795`, round `900001`, and supported hole/segment IDs;
  mismatches and unknown IDs return 404 instead of silently substituting the
  fixture entities. Happy-path and wrong-ID contract tests cover package
  navigation and nested reference consistency. Commit `99baf324` is pushed;
  current status remains awaiting Opus re-review, with no Native dispatch or
  production/release action.
- 2026-08-27: Closed the follow-up fixture contract P1s from Opus review.
  Course and round package queries now bind `round_id`, `tee_box`, `nine`, and
  `back_global_id`; prep/coverage validate requested holes and expose the full
  iOS/Watch Codable shape; isolated deterministic `topo.png`/`green.png`
  resources validate course/hole identity; and install counts cover all 18
  fixture holes. Happy and fail-closed route tests cover these contracts.
  Current HEAD is awaiting Opus re-review; no Native dispatch, deployment,
  release, signing, or upload was performed.
- 2026-08-27: Closed the latest fixture P1 contract set: explicit dynamic
  aliases map to the canonical fixture entities; package/prep front/back/all
  segments return matching 9/18 hole rows; caddie decision POST and complete
  shotmap overlay fields are fixture-backed; deterministic topo/green assets
  are isolated and identity-checked; and install/coverage counts align with
  the 18-hole course. Unknown IDs, holes, segments, and back-course IDs fail
  closed. Runtime route/decode verification remains dependency-gated on the
  homeserver (`fastapi` unavailable); current status awaits Opus re-review.
- 2026-08-27: Recorded the fixture route-to-model matrix for the latest
  bounded review. `mobile/courses/{gid}/package` and
  `mobile/rounds/{rid}/package` feed `LiveRoundPackage`/Watch package models;
  `courses/{gid}/prep` feeds `CoursePrepResponse` and
  `WatchCoursePrepResponse`; geometry coverage feeds
  `CourseGeometryCoverageResponse`; history shotmap plus
  `courses/{gid}/holes/{hole}/{topo,green}.png` feed `RoundHoleShotMap`,
  `CoursePrepMap`, and Watch map models; caddie decision POST feeds
  `CaddieDecisionResponse` and its Watch live gate. Actual callers pass course
  `3881/31670/31871`, round aliases including `live-round-1`, tee `blue/white`,
  and segments `front/back/all`; fixture aliases and filters cover these forms
  while unknown cross-entity values fail closed. Runtime Codable tests remain
  pending the missing homeserver FastAPI dependency; current status awaits Opus
  re-review.
- 2026-08-27: Completed the full caller/model pass for the fixture route
  matrix. Actual Watch/iOS callers use front course `3881`, composite back
  courses `31670`/`31871`, round aliases including `live-round-1`, tee
  `blue/white`, and `front/back/all`; fixture mappings preserve those caller
  identities independently while retaining canonical `31795/900001` as the
  resolver seed. Package/prep/coverage/install rows filter to the requested
  segment; prep and shotmap provide non-optional map images, projections,
  green F/M/B distances, and overlay `ppm`/`ln`; decision POST preserves
  caller identity and supplies the Watch live dispersion/location gate; and
  club-bag bootstrap is explicitly fixture-backed. Runtime route/Codable
  execution remains blocked only by missing homeserver `fastapi`; current
  status awaits Opus re-review.
- 2026-08-27: After the owner-authorized Opus GO, ran the single fixture-mode
  Native Mobile CI validation `33123361136` from branch
  `codex/p0-p1-p2-checkpoint-20260823`; run metadata confirms exact app
  `headSha=4f69666ae3d4ee539d0b55f675f00017e88c6bcd`. Inputs were
  `capture_scope=full`, `fixture_mode=true`, `review_round_ref=home-31795`,
  blank API/backend inputs, and `require_live_preflight=false`; no production
  URL or token was supplied. XcodeGen, project generation, simulator
  inventory, Watch target compilation, Watch design snapshots, Watch runtime
  seed/restore capture, secret scans, native evidence generation, and cleanup
  passed. Watch conclusions are therefore positive for the deterministic
  Native/Watch stages, but do not prove fixture-backed Watch behavior because
  the fixture never started.
- 2026-08-27: Run `33123361136` concluded `failure` for orchestration reasons.
  `Start isolated CI fixture` exited immediately at `test -n
  "$AI_CADDIE_ADMIN_TOKEN"`; the runner log shows the secret empty, so the
  loopback fixture health check was never reached and no fixture revision or
  round evidence was produced. iOS app target and live preflight/runtime were
  skipped. `Verify SwiftJCS consumer boundaries` also failed secondarily:
  its positive SwiftPM consumer built, but the expected Xcode DerivedData
  `AICaddieDomain.framework` was absent because the iOS target was skipped
  (`find .../DerivedData: No such file or directory`). This is classified as
  workflow secret/step-dependency infrastructure evidence, not a proven source
  regression; no source fix or rerun is justified by this run.
- 2026-08-27: Available run artifacts were `native-build-evidence-ci-fixture`
  (514 bytes), `watch-real-screenshots` (295,697 bytes),
  `watch-snapshots` (2,151,345 bytes), and `real-screenshots` (366 bytes), all
  unexpired. The run annotations also note that optional `real-videos/` and
  `design-snapshots/` paths were empty. No artifact was retained locally.
  TestFlight, release, deploy, signing, production mutation, and production
  data synchronization were not performed.
- 2026-08-27: Audited the fixture-token blocker for Native run `33123361136`
  using GitHub metadata only; no secret values were read or printed. Repository
  Actions secrets include `AI_CADDIE_ADMIN_TOKEN` and
  `AI_CADDIE_CI_PLAYER_TOKEN`, but the required
  `AI_CADDIE_CI_FIXTURE_ADMIN_TOKEN` is absent. Repository variables expose
  only `AI_CADDIE_API_BASE_URL`; no environment-scoped secret or variable
  supplies the fixture token. The workflow references the correct exact name
  in its fixture start, simulator, scan, and evidence paths, and the run log
  confirms the expression resolved to empty. Default workflow permissions are
  read-only; no environment protection or permissions issue explains the
  missing value. The fixture launcher and private API intentionally require a
  non-empty admin bearer and loopback/private profile; a generic read-only
  token cannot replace it without changing the authentication contract or
  opening anonymous write-capable routes.
- 2026-08-27: Hardened `.github/workflows/native-mobile.yml` fail-closed
  behavior. The fixture start step now has `id: start_fixture`; SwiftJCS
  boundary verification requires a successful iOS target; and all fixture-mode
  Watch boot/build/snapshot/runtime stages require
  `steps.start_fixture.outcome == 'success'`. Thus a missing token produces
  explicit skipped iOS/Watch dependent stages and skipped native evidence,
  rather than a secondary SwiftJCS failure or passed Watch fixture evidence.
  The existing non-empty token guard, loopback restriction, private security
  profile, and no-anonymous-write behavior are unchanged. Remote focused
  workflow contract test passed 1/1. No Native rerun was dispatched.
- 2026-08-27: Owner action remains required before fixture validation can run:
  configure protected repository secret `AI_CADDIE_CI_FIXTURE_ADMIN_TOKEN`
  (exact name, Actions-readable, unavailable to pull requests/forks) with a
  high-entropy random CI-only token shared only by the fixture process and the
  Native workflow. Verification should inspect only metadata, dispatch one
  fixture-mode run on the intended branch, and confirm fixture health plus
  iOS and Watch evidence markers; never print the token or reuse the production
  `AI_CADDIE_ADMIN_TOKEN`. No release, TestFlight, deploy, signing, or
  production mutation occurred.
- 2026-08-28: Per the owner-authorized exact-SHA fixture rerun, Native Mobile
  CI run `33137626371` completed at head
  `7a648e94f1dd671a591281225e7545d1d52a23a4` on the protected branch. Workflow
  inputs were `capture_scope=full`, `fixture_mode=true`,
  `review_round_ref=900001`, `require_live_preflight=false`, blank production
  endpoint/backend/revision/token inputs, and an ephemeral runner-generated
  fixture token. Fixture revision was `ci-fixture-20260827-v1`; fixture
  install/start/health and stop passed. XcodeGen, iOS app target,
  SwiftJCS boundary verification, design snapshots/secret scan/upload, and
  all Watch build/snapshot/runtime/evidence stages passed. The iOS real
  simulator step failed behaviorally with 9/9 tests failing: RealFlow failed
  its start assertion, ReviewEdit could not open a resolver-verified real hole,
  and all seven TeeSelection tests could not observe the expected Beijing
  Palace `31793` identity/nearby/catalogue rows. Thus iOS fixture revision,
  round `900001`/course `31795` evidence, 18-hole package/map/topo/green/
  caddie consumption, and the `31797` uninstalled partial-coverage candidate
  remain unproven by Native UI behavior despite the fixture contract tests.
  The Watch runtime seed/restore produced its expected screenshots; Watch
  target, snapshots, runtime, secret scans, native evidence writer/scan/upload,
  and cleanup all passed. Artifact metadata (unexpired, not downloaded) was:
  `native-build-evidence-ci-fixture` 509 bytes,
  `sha256:6db21fb7d40d0b9688c600c586dd9c5328395e2782f0bdc536997c834bcb540f`;
  `watch-real-screenshots` 287,738 bytes,
  `sha256:ff3403ffb43431210279d3aecd4d3d62c04688ec4c9c12e70fa1d2c9422de09d`;
  `watch-snapshots` 2,151,345 bytes,
  `sha256:9c65c53f93987f59fca3b2fb9628a5b3f664c474e37f72cb543779920909d5c7`;
  `real-video` 86,349,632 bytes,
  `sha256:b3dbf2a802ef68d22a88cb5fba84ca25f31adf2f053f1fae69dec5228d747633`;
  `real-screenshots` 2,756,276 bytes,
  `sha256:a7722f9fe5a4495e8fc67913b0a37dd33399bfe9448ddb13d3c8ab33fddd4983`;
  and `design-snapshots` 3,702,496 bytes,
  `sha256:7102625de7b0dd23fb5e2114f87a6dba51137954fae287127e8b38315865872f`.
  No further Native run, release, TestFlight, deploy, signing, production
  mutation, or production data synchronization was performed; the remaining
  blocker is why the corrected fixture catalogue/history payloads are not
  consumed by the iOS UI-test process.
- 2026-08-28: Read-only diagnosis of run `33137626371` identified the common
  cause of all 9 iOS UI failures. The UI-test runner's own diagnostics proved
  `resolvedURL=http://127.0.0.1:9000`, `tokenLen=64`, GPS
  `40.0454995,116.5461531`, and fixture health HTTP 200 with revision
  `ci-fixture-20260827-v1`; the resolver also successfully selected round
  `900001`, course `31795`, hole 1, two labelled shots (`1D`,`8I`), proving
  that the runner could reach and decode `/history/rounds`, round detail, and
  shotmap. The app process did not share that configuration: its captured
  home/start/review trees repeatedly showed `未配置后端地址`, `附近球场暂时读取失败`,
  and a disabled `开始记分`; the collected app log contains no fixture API
  request/response evidence. Consequently the app never requested the
  corrected `31793` search/nearby/options/tees or `31797` partial coverage,
  nor the `900001` package/prep/geometry/topo/green/caddie routes. This is a
  launch-environment propagation/configuration failure, not a fixture route,
  Codable/map decode, course identity, resolver selection, or navigation race.
  Failure matrix: RealFlow waited for the home `成绩` button, then failed its
  first loaded-home/start prerequisite against the offline fixture package;
  ReviewEdit reached `单场复盘` via its DEBUG fallback but the page showed
  `未配置后端地址`, so `round-review-hole-1` never appeared and it failed
  `review-edit evidence must open its resolver-verified real hole`; all seven
  TeeSelection journeys reached `开始一场`, where the actual IDs were
  `start-round-search-all-courses`, `start-round-primary-action`, and expected
  `start-round-course-segment-31793`, but nearby/search rows were absent or
  disabled, yielding the seven Beijing Palace/segment-31793 assertions.
  Workflow inputs and runner env are correctly set in
  `.github/workflows/native-mobile.yml`: fixture mode uses the loopback base,
  `review_round_ref=900001`, GPS values, and the masked ephemeral token in
  both plain and `TEST_RUNNER_` variables. The test resolver sees them, while
  `XCUIApplication.launchEnvironment` does not result in those values inside
  `AICaddieApp` on this target. Minimal repair scope is the iOS UI-test/app
  launch configuration boundary: make the fixture base URL and token
  explicitly reach the application process (with fail-closed fixture-only
  guards and no production fallback), then re-run the existing unchanged
  tests once after Opus review. Do not alter resolver thresholds, assertions,
  fixture data, or mark failures skipped. No new run, deployment, release,
  signing, TestFlight, or production action was performed during this
  diagnosis.
- 2026-08-28: Implemented the bounded iOS fixture launch-environment repair
  after run `33137626371` and diagnosis commit `98a36a53`. Fixture startup now
  writes the masked ephemeral token, loopback URL, `AI_CADDIE_FIXTURE_MODE=1`,
  and `AI_CADDIE_DATA_MODE=fixture` to both runner/job variables and
  `SIMCTL_CHILD_*` variables, so the XCTest runner and the app launched inside
  the simulator receive the same configuration. RealFlow, ReviewEdit, and
  TeeSelection harnesses explicitly pass the fixture/data markers alongside
  their existing URL/token launch environment. Added a fail-fast
  `Validate native launch environment` workflow step that reports only
  presence/length booleans, verifies fixture loopback/markers/child-token
  equality, and gates fixture iOS capture on success; live mode remains on its
  separate public endpoint/protected token path without fixture fallback.
  Added workflow contract assertions for the child environment and all three
  UI-test launch helpers. Homeserver shared `ci-venv` verification passed
  `tests.test_ci_workflow` + `tests.test_ci_fixture_contract` 64/64, Python
  `compileall -q server_v2 ai_caddie tests`, YAML parsing, bash syntax, and
  `git diff --check`. No Native rerun, release, TestFlight, deploy, signing,
  or production action was performed; Opus read-only review is required before
  any rerun.
- 2026-08-28: Closed the Opus launch blocker in commit `a0688549` follow-up.
  `BackendConfigurationStore.normalizedAPIBaseURL` still correctly rejects
  HTTP by default; an explicit `allowFixtureLoopback` opt-in now permits only
  DEBUG `http://127.0.0.1:9000` (also `localhost`/`[::1]`) and only when
  `AI_CADDIE_FIXTURE_MODE=1`, `AI_CADDIE_DATA_MODE=fixture`, and a non-empty
  admin token are present. HTTPS behavior and all non-fixture/live/release
  paths remain unchanged. Added Swift configuration tests for fixture accept,
  live loopback reject, bad port/host/query reject, and public HTTPS accept.
  Opus also required launch validation to gate both surfaces: all fixture Watch
  build/snapshot/runtime/scan/upload behavior steps now require successful
  app-resolved launch validation, and native evidence forces both iOS and Watch
  statuses to `skipped` when validation fails/cancels/skips. Workflow contract
  tests assert these gates and evidence inputs. Homeserver shared-environment
  checks before this follow-up had workflow/fixture contracts 64/64 and
  compile/YAML/bash/diff checks green; the combined mobile contract command
  was dependency-blocked because shared `ci-venv` lacks `jsonschema`, so Swift
  compilation remains an Actions gate. No new run, release, deploy, signing,
  TestFlight, or production action was performed; Opus read-only review is
  required before rerun.
- 2026-08-28: Auditable handoff for the guarded fixture URL and common-gate
  slice: branch `codex/p0-p1-p2-checkpoint-20260823`, exact HEAD
  `06164061b7644ac2c1f03304472a857d8af7a5ad`, pushed to origin. Commit
  `c549c8de7a6e0ebee32bff21e81bd9001ba22d8f` (`Allow guarded iOS fixture
  loopback configuration`) changed `.github/workflows/native-mobile.yml`,
  `mobile/ios/AICaddie/AICaddieApp.swift`,
  `mobile/ios/AICaddie/Services/BackendConfigurationStore.swift`,
  `mobile/ios/AICaddieTests/BackendConfigurationStoreTests.swift`,
  `tests/test_ci_workflow.py`, and this ledger; commit
  `06164061b7644ac2c1f03304472a857d8af7a5ad` (`Cover guarded fixture URL
  contract`) changed `tests/test_mobile_contracts.py`.
  Swift URL tests cover fixture `http://127.0.0.1:9000` acceptance only with
  explicit opt-in, HTTP loopback rejection without opt-in (the live case), bad
  fixture port/host/query rejection, and public HTTPS acceptance. App source
  separately requires fixture marker `AI_CADDIE_FIXTURE_MODE=1`, data marker
  `AI_CADDIE_DATA_MODE=fixture`, and a non-empty token before enabling that
  opt-in; release builds hard-disable it. Watch common gating covers Resolve
  and boot simulator, Watch target test, Watch snapshot collection/scan/upload,
  Watch runtime seed/restore, runtime scan/upload, and native evidence status
  generation; failed/cancelled/skipped launch validation maps both surfaces to
  `skipped`.
  Homeserver results: workflow + fixture contracts 64/64; Python
  `compileall -q server_v2 ai_caddie tests` passed; YAML parse, `bash -n
  ops/run_ci_fixture.sh`, and `git diff --check` passed. The broader
  `tests.test_mobile_contracts` could not import because shared `ci-venv`
  lacks `jsonschema`; the repository `uv.lock` includes `jsonschema 4.26.0`,
  but homeserver has no `uv` executable and no lock-backed scratch environment
  was created or installed in this constrained handoff. All pre-existing
  untracked reports, `.codex-tmp/`, and mockup files remain preserved. No
  Native dispatch, deployment, upload, signing, release, or TestFlight action
  was performed.
- 2026-08-28: Opus follow-up isolation hardening is complete in the same
  repair slice. The explicit fixture-only resolver now refuses to inspect
  persisted or Info.plist public HTTPS values whenever either fixture marker
  is present; marker mismatch, missing token, missing URL, non-loopback host,
  wrong port, and HTTP path/query variants all fail closed. The pre-capture
  launch prerequisite and app-resolved launch validation outcomes now gate all
  fixture iOS and Watch build/runtime/snapshot/scan/upload steps, including
  native evidence scanning/upload; evidence writer receives both outcomes and
  forces both surfaces to `skipped` when either is not successful. Swift config
  tests cover explicit fixture acceptance, fallback suppression, marker/token
  mismatch rejection, live HTTPS acceptance, and live HTTP loopback rejection.
  Homeserver shared `ci-venv` ran workflow/fixture contracts 64/64, Python
  compileall, YAML parse, bash syntax, and diff-check successfully. Swift
  compilation remains an Actions-only gate; no Native rerun, release, deploy,
  signing, TestFlight, or production action was performed. The follow-up is
  pushed at the exact HEAD recorded in the handoff below and awaits Opus review.
- 2026-08-27: Diagnosed Native fixture run `33126223345` startup failure with
  a homeserver reproduction: `uv` was unavailable (`command -v uv` empty), and
  the launcher stderr was `nohup: failed to run command 'uv': No such file or
  directory`. The same missing precondition existed on the macOS workflow,
  which invoked `uv run` without installing uv. Added fixture-only
  `Install uv for isolated CI fixture` (`brew install uv`) before startup;
  launcher remains `uv run --frozen python -m uvicorn` and is invoked through
  `bash` because the tracked launcher is not executable, while the startup
  gate still requires loopback health. Added a small redacted startup
  diagnostics artifact on failure. No Native rerun was dispatched.
- 2026-08-28: Per Opus GO, dispatched exactly one fixture-mode Native Mobile
  run `33127924236` at exact head
  `0545c4aa15bc201a168570c5b622f274e5631736`, with `review_round_ref=900001`,
  no production endpoint/revision/token, and live preflight/release flags
  disabled. Fixture install/start/health and stop passed; `uv`/uvicorn startup
  was therefore verified. XcodeGen, design snapshots, Watch target build,
  Watch snapshots, Watch runtime seed/restore screenshots, secret scans,
  native evidence writer, and cleanup passed. iOS app target failed at Swift
  compile with the source call-site mismatch in
  `mobile/ios/AICaddie/Views/RoundShotMapView.swift:1087`: argument labels/order
  for `RoundHoleShotMapScreen` do not match its declaration. SwiftJCS,
  deterministic iOS, RealFlow, ReviewEdit, and TeeSelection were skipped
  because the iOS target failed; no behavior pass is claimed. Artifacts were
  limited to `native-build-evidence-ci-fixture` (514 bytes),
  `watch-real-screenshots` (294,644 bytes), `watch-snapshots` (2,151,345
  bytes), and tiny iOS placeholder artifacts; no large artifact was retained.
  No second Native run, TestFlight, release, deploy, signing, or production
  action was performed.
- 2026-08-28: Fixed the Native compile blocker found by run `33127924236`.
  `RoundShotMapPagerScreen` now calls the dependency-injected
  `RoundHoleShotMapScreen` initializer in its declared label order, preserving
  `roundRef` plus `globalId`, `backGlobalId`, `nine`, and `teeBox` identity.
  Added a focused source contract covering the sole caller and identity fields.
  Remote focused contract and Python compilation passed. This is a source-only
  correction; no Native rerun has been dispatched pending Opus/owner approval.
- 2026-08-28: Fixture Native rerun `33129416236` at exact head
  `c0982e47688bfd733d992d40bfc45d01186f68fa` passed fixture startup/health and
  stop, XcodeGen, design snapshots, Watch build/snapshots/runtime seed-restore,
  secret scans, evidence writer, and cleanup. It then exposed a second Swift
  compile call-site mismatch in
  `mobile/ios/AICaddieTests/LiveRoundAppModelTests.swift:2073`: the
  `RecentRoundSummary` test fixture omitted new optional `backGlobalId`, `nine`,
  and `teeBox` arguments. No iOS behavior stages ran; no fixture/schema or
  runner failure was found. Artifacts were limited to 512-byte evidence,
  292,337-byte Watch runtime screenshots, 2,151,345-byte Watch snapshots, and
  a 366-byte screenshot placeholder. The test fixture is corrected locally;
  no new Native run has been dispatched pending review.
- 2026-08-28: Per Opus GO, ran exactly one fixture-mode Native workflow
  `33130426502` at exact head
  `75b34810590e8b622b27e69e53f16bd16c416cfb`, with `review_round_ref=900001`,
  ephemeral runner token, blank production inputs, and live preflight disabled.
  Fixture uv install/start/health and stop passed; the private fixture was
  reachable, but the real iOS UI-test target did not consume its API payloads
  because it failed to compile `AICaddieUITests/RealEvidenceRoundResolver.swift:73`
  (`hole.map(String.init) ?? \"-\"` caused an unterminated interpolation/string).
  The iOS app target, including `LiveRoundAppModelTests`, SwiftJCS boundaries,
  and design snapshot secret scan passed. The only failed step was
  `Real-simulator screenshots (iOS, XCUITest against live backend)`; RealFlow,
  ReviewEdit, and TeeSelection behavior therefore remain unverified, as do
  iOS fixtureRevision/dataMode and 18-hole/map/topo/green/caddie API-consumption
  assertions. Watch target build, snapshots, runtime seed/restore (22 PNGs),
  Watch secret scan, native evidence writer, and cleanup passed. Artifact zip
  sizes/hashes: design snapshots 3,702,496 bytes / `a1dd349f82f91a100b3a22472845a2c71c895f88c631b496c28ea2bbae09d769`;
  real screenshots 213 bytes / `1ece06f79ec64ea508851a96e09e7bf69f49d1459401df76b31c926f7dc2306e`;
  real video 70,297 bytes / `387f26b1a1dfa012e983236d6750aa5503211633ea4b8b6748159d63647d5a8d`;
  Watch snapshots 2,151,345 bytes / `1953a5d4ded17654740c429c1b3b99564ba27a9e29c343144a0b0f331b5e0cd0`;
  Watch runtime 290,324 bytes / `e075b5cf2cb51809615f016160a49e2bf8ec97aee9a4af19ea4f849d7a5b280e`;
  evidence 515 bytes / `228c301e2fc15fd4f4d0e89a10b72352fab1d2b8b11c0545bb6395261abc983a`.
  No further rerun, TestFlight, release, deploy, signing, or production action
  was performed.
- 2026-08-28: Audited commit `d566eed87c397fea2cb9d17ba09bd0e0e3788251` and
  run `33129416236`. The run was `Native Mobile CI`, workflow_dispatch, exact
  head `c0982e47688bfd733d992d40bfc45d01186f68fa`, and failed only at
  `Test iOS app target` with Swift test compilation error at
  `LiveRoundAppModelTests.swift:2073`; the omitted fields were
  `RecentRoundSummary.backGlobalId`, `.nine`, and `.teeBox`. The fix is pushed
  in `d566eed8`; it changes only that test fixture plus this ledger. Static
  source checks find one `RecentRoundSummary` initialization and one
  `RoundHoleShotMapScreen` caller, with required identity fields present and
  ordered. Homeserver focused contract and Python compilation passed. No
  further omission was found; exact `d566eed8` is ready for one fixture-mode
  Native rerun after Opus/owner confirmation. No rerun was dispatched here.
- 2026-08-27: Replaced the missing-secret dependency with self-contained
  fixture-mode token wiring. Native workflow fixture startup now generates one
  64-hex-byte token from runner `openssl rand -hex 32`, fail-closes when
  `openssl` is unavailable or output format is invalid, masks it immediately,
  exports it for the launcher, and writes only masked job environment names to
  `GITHUB_ENV`. The same job-scoped token is inherited by iOS, Watch, and
  artifact secret scans; Watch launches explicitly forward it through
  `SIMCTL_CHILD_AI_CADDIE_ADMIN_TOKEN`. Live mode uses a separate
  `Configure live native auth` step and the protected `AI_CADDIE_ADMIN_TOKEN`
  secret, so fixture generation cannot affect live endpoint/token selection.
  `ops/run_ci_fixture.sh` retains CI/debug, non-empty token, private profile,
  and loopback guards; no default, CLI token, anonymous route, or production
  fallback was added. Missing token/start failure leaves dependent iOS/Watch
  stages skipped and evidence non-passed. Remote focused workflow/fixture
  behavior tests passed 3/3, remote Python compilation passed, and no Native
  rerun was dispatched. The owner no longer needs to configure
  `AI_CADDIE_CI_FIXTURE_ADMIN_TOKEN`; an external fixture endpoint would still
  require its own explicitly protected credential.
- 2026-08-27: Opus token review P1 follow-up is implemented. Every iOS,
  real-capture, screenshot collection/scan/upload, and native evidence scan
  step now explicitly requires `steps.start_fixture.outcome == 'success'` in
  fixture mode; the evidence writer remains `always()` but receives fixture
  mode and start outcome and forces both iOS and Watch statuses to `skipped`
  for failure/cancel/skipped startup, preventing default `passed` evidence.
  Watch gates remain aligned. Watch runtime token delivery now exports
  `SIMCTL_CHILD_AI_CADDIE_ADMIN_TOKEN` once in the shell before `xcrun`; no
  token assignment appears in the utility command invocation. iOS receives
  the same masked job environment without token command-line arguments.
  Remote focused workflow/fixture tests passed 3/3, remote `compileall`
  passed, and local YAML/bash syntax plus `git diff --check` passed. No Native
  rerun, release, TestFlight, deploy, signing, or production action occurred;
  the temporary homeserver snapshot was removed.
- 2026-08-27: After Opus GO, dispatched the single authorized fixture-mode
  Native Mobile CI run `33126223345` from the protected branch; run metadata
  confirms exact `headSha=a255f347fe5f967b1831831a34a9c247394240bc`. Inputs were
  `capture_scope=full`, `fixture_mode=true`, `review_round_ref=900001`, blank
  API/backend inputs, and `require_live_preflight=false`; no production
  endpoint/token or release flags were used. Runner-side `openssl rand -hex
  32` generation, validation, masking, and environment setup executed, but
  fixture health never became available: all 30 loopback probes returned
  connection refused and the step ended `fixture health check failed`.
- 2026-08-27: Run `33126223345` concluded `failure`, classified as fixture
  startup/runner environment infrastructure, not an app or fixture schema
  regression. Because startup failed, iOS target, SwiftJCS/Codable boundary,
  iOS RealFlow/ReviewEdit/TeeSelection, Watch build/snapshot/runtime, and all
  secret scans were explicitly skipped by the new gates. Native evidence
  writer ran and mapped both surfaces to `skipped`; no fixture revision,
  round/course identity, 18-hole/map/caddie consumption, or behavioral pass is
  claimed. Cleanup and post-checkout passed; the run exposed no artifacts.
  No blind rerun was made. The likely next diagnostic is to expose the
  already-redacted `$RUNNER_TEMP/ai-caddie-fixture.log` on startup failure or
  add an explicit macOS `uv` availability/install gate, but that requires a
  separate reviewed change. No release, TestFlight, deploy, signing, or
  production mutation occurred.
- 2026-08-28: Closed the remaining Native fixture workflow gate isolation gap.
  The app-target launch environment validation now runs before all iOS target
  and design-snapshot stages; real iOS capture, screenshot collection/scan/
  upload, and video upload conditions require both launch validations plus the
  fixture startup and prerequisite outcomes. This keeps fixture mode fail
  closed while leaving live-mode branches unchanged. Remote workflow/fixture
  contract tests passed 64/64, YAML parsing and remote Python compilation
  passed, and the local working-tree `git diff --check` passed. No Native
  rerun, release, TestFlight, deploy, signing, or production action occurred.
- 2026-08-28: Opus identified a P1 ordering defect in the preceding gate
  closure: the authoritative launch-environment step was still declared after
  iOS and design dependents. The validation is now declared before every iOS,
  Watch, capture, snapshot, and native-evidence dependent step, and all those
  fixture conditions require startup, prerequisite, app-target environment,
  and authoritative environment success. Workflow tests parse step order and
  exercise success plus failure/cancelled/skipped rejection for each gate.
  Homeserver verification passed 65/65 focused workflow/fixture tests, remote
  Python compilation, YAML parsing, and bash syntax; no Native rerun or
  release/TestFlight/deploy/signing/production action occurred.
- 2026-08-28: After Opus GO, ran exactly one authorized fixture-mode Native
  Mobile CI workflow `33142832348` at exact head
  `b244968b93dd4cb5837b673d1d466fceac98a383`, with `capture_scope=full`,
  `fixture_mode=true`, `review_round_ref=900001`, blank live URL/revision, and
  `require_live_preflight=false`; no release, deploy, signing, or TestFlight
  flags/actions were used. All four launch gates passed in runtime order:
  fixture startup, launch prerequisites, app-target environment, and
  authoritative environment. The fixture used app URL
  `http://127.0.0.1:9000` and revision `ci-fixture-20260827-v1`; logs contain no
  `未配置后端`/unconfigured-backend output. iOS target actually ran but failed
  to compile because `BackendConfigurationStoreTests` references a missing
  `AICaddieApp.resolveAPIBaseURL` member; therefore SwiftJCS/Codable and iOS
  RealFlow/ReviewEdit/TeeSelection behavior were skipped by dependency gates.
  Design snapshots and scans passed. Watch target, design snapshots, runtime
  seed/restore (22 snapshots), runtime scan, evidence writer, and cleanup all
  passed. Native evidence artifact: 512 bytes,
  `sha256:f69f12709d3ff050f85226cb3a4a4d43d700cb540ed7b69c27ec8db3af1d7c3b`;
  Watch runtime artifact: 292,443 bytes,
  `sha256:e35811a1dabdea38cff2bb52f40f41fd8820abcf4a641ac3c7ef59e416c6a04e`;
  Watch design artifact: 2,151,345 bytes,
  `sha256:3921ab9bc99277ae2522701cc72d2934168f1eb96683087c9953c8db0e8ee8fc`;
  real-screenshots diagnostic artifact: 366 bytes,
  `sha256:4f654a0421902181b23d3b859aff9a0589b73182cb1fe5e3a80ec9458c91bf7f`.
  The diagnostic says the iOS simulator was not booted during post-capture;
  no iOS behavior/API request evidence is claimed. No rerun was dispatched;
  remaining blocker is the compile failure and resulting unverified iOS
  fixtureRevision/round/course/back identity and 18-hole map/topo/green/
  caddie consumption.
- 2026-08-28: Diagnosed the iOS compile failure from run `33142832348`: the
  implementation defines `resolveAPIBaseURL` as the internal static helper on
  `LiveRoundAppModel` in `AICaddieApp.swift`; the new
  `BackendConfigurationStoreTests` incorrectly called nonexistent
  `AICaddieApp.resolveAPIBaseURL`. The minimal correction changes only those
  test calls to `LiveRoundAppModel.resolveAPIBaseURL`, preserving the existing
  fixture explicit-loopback, fallback suppression, marker/token, and live
  HTTPS-only assertions. Repository search found no other stale callsites.
  Homeserver workflow/fixture tests passed 65/65; remote Python compilation,
  YAML parsing, bash syntax, and local diff-check passed. The broader
  `tests.test_mobile_contracts` suite remains unavailable in the shared
  environment because `jsonschema` is not installed. No Native rerun or
  release/TestFlight/deploy/signing/production action occurred.
- 2026-08-28: Ran exactly one authorized fixture-mode Native Mobile CI
  workflow `33144074168` at exact head
  `819d53791b5491a09994ff42859baa0a8e5b847c`, with full capture, fixture mode,
  review round `900001`, blank live URL/revision, and live preflight disabled.
  All four launch gates passed in order, iOS app target compiled and ran, and
  the Watch target/snapshots/runtime seed-restore/evidence/cleanup all passed.
  The run still concluded failure because the iOS test target reported six
  main-actor isolation errors: `LiveRoundAppModel.resolveAPIBaseURL` was called
  from synchronous `BackendConfigurationStoreTests` methods. Real iOS UI
  capture was consequently skipped by the failed target dependency; no iOS
  API request/18-hole fixture consumption evidence is claimed. The fixture
  URL was `http://127.0.0.1:9000`, revision `ci-fixture-20260827-v1`, and no
  unconfigured-backend message appeared. Artifacts: native evidence 512 bytes,
  `sha256:96a74416b6c8f2b2d2023163f815a2218f915e522efb05347013046d43eda6cd`;
  Watch runtime 292,279 bytes,
  `sha256:325f5842a3173b5525e36c6cb1b14412ce4f84e6884594bd96f6b423d664e26f`;
  Watch snapshots 2,151,345 bytes,
  `sha256:4528de23a1a137948ef7287e1cf7e774df26781bf71fd2d726cd5c2cffe9904b`;
  real-screenshot diagnostic 366 bytes,
  `sha256:1dbe97340dbb51c690d31faf15f8f2ecd5812ea3207f14f2b3056d6a1c91be13`.
  No further Native rerun or release/TestFlight/deploy/signing/production
  action occurred.
- 2026-08-28: Fixed the second-level compile issue by annotating
  `BackendConfigurationStoreTests` with `@MainActor`, matching its production
  owner isolation. No duplicate API or production URL behavior changed.
  Homeserver workflow/fixture tests passed 65/65; remote compileall, YAML
  parsing, bash syntax, and local diff-check passed. The macOS Xcode target
  remains unrerun pending Opus review.
- 2026-08-28: Ran exactly one authorized fixture-mode Native Mobile CI
  workflow `33144812162` at exact head
  `27bb9de69245c57ef2a3cf99402402581e74b50e`, with full capture, fixture mode,
  review round `900001`, blank live URL/revision, and live preflight disabled.
  All four launch gates passed, iOS app target compiled and executed, and
  Watch target/snapshots/runtime/evidence/cleanup passed. The only iOS failure
  was the intended fixture-isolation test: fixture markers with an explicit
  `https://production.example.test` URL were accepted by the resolver, so
  `testFixtureResolutionNeverFallsBackToPersistedOrBundleValues` failed at
  line 70. This was a production-logic gap, not a runner or compile issue;
  iOS UI capture remained skipped by the failed target dependency. Fixture URL
  was `http://127.0.0.1:9000`, revision `ci-fixture-20260827-v1`, and no
  unconfigured-backend message appeared. Artifacts: native evidence 511 bytes,
  `sha256:15f5713b36a8613f94562e81f18f177b2400ca6273cb9f751ac3efda6de22470`;
  Watch runtime 288,519 bytes,
  `sha256:ca9e85061738d6faf09a6c2b0acced9a01f171db459c09b1ca36931a9139adf2`;
  Watch snapshots 2,151,345 bytes,
  `sha256:92ab389f7186bf7dce484ecaf75a4f407ed0c7e88669902a5406839877d29457`;
  real-screenshot diagnostic 366 bytes,
  `sha256:77f3dcf8a1a310494771fd24fd4e6fada609eb429ace25ed4ec90e42cd8ac595`;
  design snapshots 3,694,424 bytes,
  `sha256:b6138d8b68c02a59e9c6fcbfd2e9dd919b72f952254011883c25e53930f59820`.
  No rerun or release/TestFlight/deploy/signing/production action occurred.
- 2026-08-28: Closed the fixture resolver gap by requiring the explicit
  fixture URL to remain `http` after the existing guarded loopback normalizer;
  live/non-fixture HTTPS-only candidate resolution is unchanged. Homeserver
  workflow/fixture tests passed 65/65, remote Python compilation, YAML parsing,
  bash syntax, and local diff-check passed. No Native rerun was dispatched;
  Opus read-only review is required before the next workflow action.
- 2026-08-28: After Opus GO, ran exactly one authorized full fixture-mode
  Native Mobile CI workflow `33146296505` at exact HEAD
  `ea1199c9cd1809ad3b75af664df3a22b44e02657` on
  `codex/p0-p1-p2-checkpoint-20260823`, with `fixture_mode=true`,
  `capture_scope=full`, `review_round_ref=900001`, blank live URL/revision,
  `require_live_preflight=false`, and ephemeral masked token. Fixture startup
  and health passed; all four launch gates passed with the fixed URL
  `http://127.0.0.1:9000`; iOS app target (263 tests) and SwiftJCS boundaries
  passed; design snapshots and secret scan passed. iOS XCUITest compiled and
  executed 9 tests but failed four existing behavior assertions: RealFlow
  topo evidence did not settle, ReviewEdit verified evidence-hole topo did not
  settle, offline downloaded-nearby round did not start, and no-course remote
  coordinate did not settle to the expected empty/recoverable state. The
  successful cases included tee selector, denied GPS/catalogue fallback, and
  authorized GPS nearby course; no production fallback or unconfigured-backend
  evidence was observed. iOS screenshots/video were collected and secret
  scanned; UI-test app data and fixture were stopped and cleaned successfully.
  Watch target passed 315 tests; Watch snapshots, runtime seed/restore,
  runtime secret scan, evidence writer/scan, and uploads passed. Artifacts
  finalized: `native-build-evidence-ci-fixture` 511 bytes (ID `9676675058`,
  `sha256:c8bcdf3617d952ecb8094d270ae542c787126157d02524636ff44ea91f73e87c`),
  `watch-real-screenshots` 293,868 bytes (ID `9676674329`,
  `sha256:2227621b9ed06a8e2b238e16d960e99b37df792fb385c3bb714859e3fd7c8446`),
  `watch-snapshots` 2,151,345 bytes (ID `9676511561`,
  `sha256:b510810ca0023614eed02ef33d6ca19e6be516893a04f7e236115ff6204fd26d`),
  `real-screenshots` 8,055,277 bytes (ID `9676396165`,
  `sha256:a813174d33b00c3d5d1a64d85caebb4dfd63f562c1d8c65ba7416f165a0214c1`),
  `real-video` 45,364,290 bytes (ID `9676397268`,
  `sha256:5929aad7188c01429b16d4df09ca683e6b53fd768039acae2508efd06eb7c9c5`),
  and `design-snapshots` 3,694,424 bytes (ID `9676034508`,
  `sha256:41524776c7b91767b068f52647f8768d363d676a47170839b445b6eab51dacbc`). No release/TestFlight/deploy/signing
  action occurred and no further rerun was dispatched. Remaining P2 is the
  four iOS UI behavior assertions and their topo/offline/GPS evidence; this
  run does not claim complete iOS RealFlow/ReviewEdit/TeeSelection evidence.
- 2026-08-28: Read-only diagnosis of Native fixture run `33146296505` found
  two confirmed fixture/behavior contract gaps and one unresolved app-side
  async path. The `(0,0)` no-course case received HTTP 200 with four nearby
  matches because `server_v2/ci_fixture.py:nearby` returns a fixed list,
  independent of coordinates; this is fixture data mismatch, not a timeout.
  The offline case reached the online `live-hole-offline-course-ready` marker,
  but the first-hole `31793` topo request was then cancelled after HTTP 200;
  the offline relaunch showed the generic nearby-service-failure state and no
  retained-download row, so durable prep-library persistence remains
  unproven. RealFlow and ReviewEdit likewise repeatedly received HTTP 200 topo
  bytes before app-side cancellation; the evidence distinguishes cancellation
  from a missing route but does not establish whether SwiftUI task lifecycle
  or image decode is causal. No source/test change or Native rerun was made;
  next action is a bounded fixture correction for coordinate-aware nearby
  emptiness plus focused instrumentation/reproduction of topo persistence.
- 2026-08-28: Implemented the bounded fixture nearby correction in the current
  working tree. `server_v2/ci_fixture.py` now validates latitude/longitude and
  radius, computes haversine distance against the four preset fixture course
  coordinates, returns actual course coordinates, filters by radius, and sorts
  by distance; `(0,0)` therefore returns an honest empty result while the
  Beijing and Monterey fixture ranges retain their supported identities.
  Added direct contract coverage for Beijing ordering, zero-result ocean
  coordinates, Monterey identity, radius filtering, and invalid coordinates or
  radius in `tests/test_ci_fixture_contract.py`. Homeserver verification passed:
  the fixture contract suite ran 27/27, the HTTP nearby matrix passed 4 valid
  plus 4 fail-closed cases, and remote `compileall -q server_v2 ai_caddie tests`
  passed; no local heavy test was run.
  Swift source review found no explicit cancellation path beyond SwiftUI task
  lifecycle, and no independent offline cache-key defect; no Swift change or
  Native rerun was made.
- 2026-08-28: Bounded read-only diagnosis of Native run `33150308680` found
  deterministic fixture semantics behind all three iOS failures; no source
  change, rerun, or workflow dispatch was made. `RealFlowUITests` and
  `ReviewEditUITests` wait for `topo-hole-base-ready` after the shot-map
  response. The fixture shotmap route returns a valid 14,183-byte 64x64 PNG
  and HTTP 200 is available from `/courses/{gid}/holes/{hole}/topo.png`, but
  it labels the shotmap `mapKind=courseData`. iOS
  `RoundHoleShotMap.usesCourseDataFrame` therefore makes
  `RoundShotMapScreen.topoURL(for:)` return nil, so `TopoHoleBaseImage` can
  only expose `topo-hole-base-fallback`; no image decode or URLSession
  cancellation is involved in these two review failures. Watch passes because
  its map/image path does not use this iOS `mapKind` gate. Minimal correction is
  fixture-only: mark ready shotmap rows `mapKind=prodgeometry` (or omit the
  field) while retaining the valid raster and existing assertions.
  The offline test did pass the online `live-hole-offline-course-ready` gate,
  proving the 18-hole prep/topo bytes were durably written. On relaunch it
  failed at the expected fallback banner (`附近服务不可用；已显示下载到本机的附近球场。`),
  before the offline course-row assertion. `refreshDownloadedCourseOptions`
  derives local-nearby eligibility from the persisted package's first hole
  `teeLatitude`/`teeLongitude`; the fixture package template has neither, so
  `locallyAvailableNearbyCourses` drops the downloaded course and the UI
  correctly renders the no-local-cache failure copy. This is independent of
  topo task cancellation and persistence keys. Minimal fixture-only correction
  is to populate package hole tee coordinates from the selected fixture
  course's canonical coordinates (including 31793) before asserting offline
  fallback. The run otherwise had 6/7 TeeSelection passes, including `(0,0)`
  empty/recoverable fallback and real Core Location nearby flow; Watch 315
  tests/runtime/evidence passed. No production or release action occurred.
- 2026-08-28: After the bounded nearby fixture correction, ran exactly one
  authorized full fixture-mode Native Mobile CI workflow `33150308680` at
  exact SHA `961e41de4eeca0821f9aa3cca13f6dfe3b7a107f`, with
  `capture_scope=full`, `fixture_mode=true`, `review_round_ref=900001`, blank
  live URL/revision, `require_live_preflight=false`, and an ephemeral masked
  token. Fixture startup/health, all four launch gates, iOS app target,
  SwiftJCS boundaries, design snapshots/scan, Watch target, Watch snapshots,
  Watch runtime seed/restore, secret scans, evidence writer, uploads, and
  cleanup all passed. The iOS UI target executed 9 tests with 3 failures:
  `RealFlowUITests.testCaptureRealAppFlow` failed because shot-map topo
  evidence did not finish loading, `ReviewEditUITests.testCaptureReviewEditFlow`
  failed because the verified evidence-hole topo did not load, and
  `TeeSelectionUITests.testDownloadedNearbyCourseStartsACompletelyNewRoundWithAllLiveServicesOffline`
  failed its assertion. The other six TeeSelection cases passed, including
  the `(0,0)` no-course empty/recoverable catalogue fallback and real Core
  Location nearby flow; the fixture coordinate/radius repair is therefore
  confirmed. Logs show HTTP 200 topo responses followed by app-side evidence
  failure/cancellation, so topo lifecycle/decode remains unresolved. Offline
  prep persistence remains unproven: the run logged failed course-options and
  offline course-facts requests before the offline assertion. Watch runtime
  evidence passed independently. Artifacts were retained remotely only:
  native evidence 509 bytes (ID `9678285206`,
  `sha256:e37c5f66b341d9a5cbcc7e0ce69e1d8d5acf5ee83480381bd280fd48ece6a71e`),
  Watch runtime 288,686 bytes (ID `9678284448`,
  `sha256:14bc526f9accb7826e3bf5f18d0501b73bd97047dd4e569ecf252f610be404fe`),
  Watch snapshots 2,151,345 bytes (ID `9678081245`,
  `sha256:533ebe5161cf058cafc6cf97e69c7814a2ca785d9acb7c8e3666d5333ba8588f`),
  real screenshots 8,207,849 bytes (ID `9677970020`,
  `sha256:648514f555bb1f6bf263d1f4e00e2f711b9522df3f53b38bd4bf455c190946f1`),
  real video 55,334,926 bytes (ID `9677971653`,
  `sha256:de459de2f7df00bd8d370867206254e52b5d8b5a7768e2b3c325911f86bc97f3`),
  and design snapshots 3,694,424 bytes (ID `9677592993`,
  `sha256:d685349fa9b8ffcab119e767aea6bc7243ef417e0eccfb7441af9dcf08ea1528`).
  No further workflow dispatch, source change, release/TestFlight/deploy,
  signing, or production action was performed. Native verification remains
  open for topo completion and offline downloaded-nearby behavior.
- 2026-08-28: After Opus GO, dispatched exactly one full fixture-mode Native
  Mobile CI workflow at exact HEAD
  `91f4bab58259e5781d6c8739d1ef2f5ec4a1e90c`: run `33155576631`, with
  `capture_scope=full`, `fixture_mode=true`, `review_round_ref=900001`,
  blank live URL/revision, `require_live_preflight=false`, and an ephemeral
  masked runner token. Fixture startup/health, all launch gates, iOS app
  target (263 tests), SwiftJCS boundaries, design snapshots/secret scan,
  Watch target, Watch snapshots/runtime/evidence/secret scan/uploads, and
  cleanup passed. Fixture revision was `ci-fixture-20260827-v1` and the
  launch URL was `http://127.0.0.1:9000`; no release, deploy, signing,
  TestFlight, or production action occurred.
  The iOS UI capture step failed only
  `RealFlowUITests.testCaptureRealAppFlow` at
  `RealFlowUITests.swift:341`: `the prep map must remain locked until all
  local facts and topo assets are installed`. `ReviewEditUITests` passed,
  all 7 `TeeSelectionUITests` passed (including downloaded-nearby offline,
  31793 catalogue, 31795/3881 identity, and 31797/NewCourse paths), and
  logs show `topo-hole-base-ready` plus `offline-cache-01-online-ready` and
  `offline-start-01-new-first-hole` milestones. This isolates the remaining
  issue to iOS prep readiness sequencing/behavior (P2), not the repaired
  shotmap map kind or package coordinates; compile, fixture, Codable, and
  Watch evidence are green. Artifacts were retained only as summaries:
  `native-build-evidence-ci-fixture` ID `9680712659`, 511 bytes,
  SHA256 `efa5da988cd7472f2d1b9040c17500fd2931b6c9792d0afb2abd0302c7fb8936`;
  `real-screenshots` ID `9680299225`, 33,132,122 bytes, SHA256
  `782cb0afc9ac60c16fb496c2d1ffe13a9da810f6f7ae10e31021742dfa7d8f21`;
  `real-video` ID `9680301241`, 80,988,016 bytes, SHA256
  `72460783f0b4622b45b9899a0ad45bf7af99c3b824cf7290041c4c6e8796795b`;
  `watch-real-screenshots` ID `9680711906`, 291,090 bytes, SHA256
  `700fd5e3e583beb98c07ad503ae72d316f09b2635ebb1fd3197f46404825041b`;
  `watch-snapshots` ID `9680447622`, 2,151,345 bytes, SHA256
  `520b70a4e8ed07ed24cee34c0c9b035a61e9faeaa9e98349089ff28e8aefefb7`;
  `design-snapshots` ID `9679663462`, 3,694,424 bytes, SHA256
  `c8c237be68a41601c8b279bb6dae09e7718190d513e6bc08ccb7505f1a44698f`.
  The full textual run log was used for diagnosis and removed; no large
  artifact was retained locally. Native verification remains open for the
  prep readiness assertion and requires a new owner-authorized source change
  and review before any further workflow action.
- 2026-08-28: Implemented the minimal fixture-data repair in source commit
  `f0ffa6f11a975041fae85b3952c88dad5374f21d`. Ready shotmap rows now use
  `mapKind=prodgeometry`, preserving the deterministic PNG, overlay,
  geometry revision, and hole identity. Package holes now include
  `teeLatitude`/`teeLongitude` from the resolved source course, including
  composite back-nine rows and supported aliases. Added focused assertions
  for all 18 shotmaps, canonical coordinates for 31793/31795/3881/31797, and
  front/back composite coordinate provenance. On the homeserver scratch
  `garmin-ai-caddie-fixture-20260828-a7c4`, the full fixture contract module
  passed 29/29 tests and `python -m compileall -q server_v2 ai_caddie tests`
  passed. The scratch was cleaned after verification; no containers, ports,
  tunnels, or persistent data were created. Native run `33150308680` was not
  rerun; Opus read-only re-review and owner-authorized Native validation are
  next, with no release/TestFlight/deploy/signing/production action taken.
- 2026-08-28: Diagnosed the remaining `33155576631` RealFlow failure as a
  fixture contract gap. The app's prep-library downloader requests
  `round_id=prep-library-31793`, but the fixture round identity parser rejected
  that ID with 404 before prep/topo downloads began. Commit `f44e291f`
  adds a strictly parsed, course-bound `prep-library-<courseId>` identity,
  preserving caller refs and rejecting unknown/cross-course IDs. The focused
  fixture contract suite passed 30/30 on the homeserver, with remote
  `compileall` passing and local `git diff --check` clean. No Native rerun or
  release/TestFlight/deploy/signing/production action was performed; Opus
  read-only re-review is required next.
- 2026-08-28: After Opus GO, dispatched the single authorized full fixture-mode
  Native Mobile CI run `33160582466` at exact HEAD
  `5fe14b0ecaad74ca1532ae4c9fea7f1f17dc3b91`, with `capture_scope=full`,
  `review_round_ref=900001`, blank live inputs, `require_live_preflight=false`,
  and runner-generated ephemeral masked token. Fixture startup/health, all
  four launch gates, iOS app target, SwiftJCS, design scans, Watch target,
  Watch runtime/evidence/scans/uploads, and cleanup passed. `ReviewEdit` and
  all 7 `TeeSelection` tests passed. `RealFlow` reached the prep-library
  downloaded course and opened the prep map, proving the `prep-library-31793`
  alias repair; it then failed only at `RealFlowUITests.swift:407` because the
  prep map did not expose the expected hazard overlay. No source, assertion,
  release, TestFlight, deploy, signing, or production action followed.
  Artifact metadata: native evidence ID `9682431333`, 510 bytes,
  `sha256:4ec7b21064c4cb5a198084d80cf965146a939b4166ed18839bf1f31cbe44c1d0`;
  Watch runtime ID `9682430464`, 290,183 bytes,
  `sha256:de5995e91cde997d87a06b625604fc1e91bd23c7cd63f9a48d772fbe5f2c38ff`;
  Watch snapshots ID `9682219417`, 2,151,345 bytes,
  `sha256:205feb4bb8b36faa59a7ccdbeed7de27db55aa3e44553a9a66c47c68c0327c0d`;
  real screenshots ID `9682082871`, 30,988,063 bytes,
  `sha256:d758952cedba11ff72e20f3f6e94471ccbf0e29403a2429dd5a035a064306673`;
  real video ID `9682084718`, 98,093,772 bytes,
  `sha256:08bb11559c7aff90139473e2ca2f0206e20174af12f03143ba3bbee3be50d8f0`;
  design snapshots ID `9681605118`, 3,694,424 bytes,
  `sha256:ddd97c95a5a1a316bab533a556dd98e3bb7eac3411039552e2e1f2dcc51ab768`.
  Homeserver SSH banner exchange timed out during post-run diagnostics, so no
  remote resource cleanup was attempted; ambiguous `/tmp` and `/dev/shm`
  resources remain untouched pending owner-authorized access recovery.
- 2026-08-28: The single delegated REL follow-up reverified the focused
  release-readiness/provenance/evidence suites on the homeserver image
  `garmin-ai-caddie-api:6a6080c-candidate` using its read-only `/app/.venv`:
  `tests.test_phase6_external_readiness`, `tests.test_release_provenance`,
  and `tests.test_release_evidence_pipeline` passed 48/48. The workflow
  contract module remained 36/39, with the three failures limited to the
  image lacking `git` (the documented shared host fallback venv is absent),
  not product failures. The temporary source snapshot and container were
  removed; no source change, release, signing, deploy, TestFlight upload, or
  production mutation occurred. The shared-runtime rule remains mandatory:
  no per-worktree `.venv` or dependency installation.
- 2026-08-28: Installed the cross-project homeserver baseline at
  `/home/jason/HOMESERVER-POLICY.md` (SHA-256
  `08dd2719c67edb462168c1c3f292d7dee5828769c7734a8b273bc01618018c6e`) and
  added missing root discovery pointers `/home/jason/AGENTS.md`,
  `/home/jason/CLAUDE.md`, and `/home/jason/GEMINI.md` (each SHA-256
  `48bf1cb2b65ebf5ae9277f4ecda853b39a80efd0c26216df629231852bac3cb8`).
  Existing files were absent, so nothing was overwritten; the bootstrap
  staging directory was removed. The policy is advisory until launcher/SSH
  enforcement is installed, but it now gives every project a canonical shared
  runtime, path, and cleanup contract.
- 2026-08-28: The single delegated current-head REL audit re-ran the focused
  release-readiness/provenance/evidence suite on
  `garmin-ai-caddie-api:6a6080c-candidate` (`/app/.venv`): 48/48 passed;
  targeted `compileall` and `git diff --check` also passed. The source-only
  scratch and container were removed. `origin/codex/p0-p1-p2-checkpoint-20260823`
  is still at `3baf632b`, while canonical HEAD is `1d0f352b`; consequently
  current-head GitHub source/Native/Phase 6 evidence is blocked on explicit
  authorization to push or dispatch. No code, production, signing, or
  TestFlight action was taken.
- 2026-08-28: Diagnosed and implemented the bounded fixture-only prep hazard
  repair in commit `9bff8293` (original delegated commit
  `d2313ba2`). `server_v2/ci_fixture.py` now supplies deterministic water and
  bunker spans with ordered route distances and valid front/back pixel
  boundaries; `tests.test_ci_fixture_contract` passed 31/31 in the fixed
  homeserver image. Remote `compileall` passed and the implementation worktree,
  scratch, and named container were removed under cleanup manifest
  `4faab6f4d74b2e66ebaa87d30758121614af789add681783f124dbf4c15f1ce6`.
  Native rerun is intentionally waiting for Opus read-only review; no
  production data, deploy, signing, or TestFlight action occurred.
- 2026-08-28: Opus completed a read-only review of `9bff8293` and returned GO:
  the water/bunker details satisfy the Swift Codable contract, route and pixel
  coordinates are coherent, and the fixture router remains isolated behind
  `AI_CADDIE_FIXTURE_MODE=1`. Both temporary Opus snapshots were removed.
  Current-head Native/macOS evidence is still blocked because canonical HEAD
  `1d0f352b` plus `9bff8293` is not present on the protected remote branch;
  pushing or dispatching that external workflow requires explicit owner
  authorization. No source, production, signing, or TestFlight action was
  taken in this review.
- 2026-08-29: Read-only GitHub metadata check confirms the required signing
  secret names are present and `AI_CADDIE_API_BASE_URL` is configured as
  `https://caddie.taile36706.ts.net`; no backend-revision repository variable
  is configured, so the upload/native workflows must receive the known public
  backend revision explicitly (`6a6080c6...`) or have that variable added.
  Remote branch `codex/p0-p1-p2-checkpoint-20260823` remains at `3baf632b`,
  while local candidate HEAD is `9bff8293`. No push or workflow dispatch was
  performed. The June `logs/phase6_external_readiness_latest.json` remains
  historical evidence and cannot satisfy the current candidate's gate.
- 2026-08-29: Read-only source/deployment comparison shows the public API
  reports backend revision `6a6080c6...`, while the candidate contains later
  backend-domain changes across 15 `server_v2`/`ai_caddie` files (the latest
  `9bff8293` itself only adds fixture hazard data). This is not yet a proven
  incompatibility, but current-head Native live evidence must either prove the
  candidate against that deployed revision or follow an explicitly authorized
  compatible backend deployment. GitHub has the signing-secret names and
  `AI_CADDIE_API_BASE_URL`, but no `AI_CADDIE_BACKEND_REVISION` repository
  variable; the known revision must therefore be supplied as an explicit
  workflow input or configured before the release gate. The old local Phase 6
  JSON (created 2026-06-07) is not valid evidence for this candidate.
- 2026-08-29: Fixed the fixture tee-decision metadata regression surfaced by
  source CI `33232927555`. Commit `787c69f5` on branch
  `codex/tee-meta-fix-20260829` restores `sourceRef`, `courseGlobalId`,
  `globalId`, `localHole`, `displayHole`, and `roundId` on the fixture
  decision's selected metadata while preserving the real decision builder's
  tee route selection. The focused local syntax check passed and the branch
  was pushed; the broader remote rerun is still pending.
- 2026-08-29: Source CI `33233365006` then exposed nested `dispersion.localHole`
  loss for composite back-nine contexts. Commit `d41a818e` on the same branch
  extends the fixture annotation to nested `dispersion` objects on
  `selected`, `selectedOption`, and `selectedSequence`. A stubbed local import
  check for the failing back-nine case now passes; the branch was pushed.
- 2026-08-29: Owner-authorized full fixture Native validation `33245546335`
  is running at exact HEAD `3f82a742f795f1f1b335eba623ebab7e559166be` with
  `capture_scope=full`, `fixture_mode=true`, `review_round_ref=900001`, and
  live preflight disabled. Fixture startup, launch prerequisites, iOS target
  tests, SwiftJCS boundaries, design snapshots, and secret scan have passed;
  the real iOS UI journey is in progress. No production, signing, deploy, or
  TestFlight action has been performed by this run.
- 2026-08-29: Fixture Native run `33245546335` completed with one product
  failure in `RealFlowUITests.testCaptureRealAppFlow` at line 589: after
  opening the full caddie plan, its heading could not be brought into the
  visible simulator viewport. iOS target/SwiftJCS/design scans, ReviewEdit,
  all seven TeeSelection tests, Watch target, and Watch runtime screenshots
  passed; real screenshot artifact upload separately hit an Actions service
  timeout. The failure is assigned to a bounded caddie-surface layout fix;
  no release or TestFlight action has been performed.
- 2026-08-29: The single delegated course-reconciliation implementation was
  completed in `a9e3f9e49d684cb84c65fe3fae1c0d77117ff5c4`, then bounded geometry
  lookup was added in `8955b851eae6de01093d961c2353e533dc17c1a7` and integrated
  as `affb58df`. The final homeserver run used the shared API image
  `garmin-ai-caddie-api:6a6080c-candidate`: reconciliation/course-search/auth
  focused and regression suites passed 60/60, `compileall` passed, and
  `git diff --check` passed. A read-only production snapshot inspection found
  six owner rounds for `31793`, all with `courseId` or
  `frontNineGlobalCourseId`, course names, coordinates, city, and hole counts;
  cached CourseView geometry corroborated the same venue at 0.173 km. The
  geometry-candidate optimization is included in canonical commit `affb58df`.
  Temporary containers and scratch data were removed; no ports, volumes,
  services, deployment, signing, or TestFlight action occurred. Native live
  rerun is still required after this source is available to the backend; the
  public service remains revision `6a6080c6...`.
- 2026-08-29: Native Mobile CI run `33264517479` completed successfully at
  exact HEAD `affb58df`; job `99132103748` executed 38 passing steps. The
  six artifact digests are recorded under Completed Evidence above. No
  production or TestFlight mutation was performed; the artifact-only iOS
  provenance workflow is the next external gate.
- 2026-08-29: REL external evidence advanced without any production mutation:
  artifact-only iOS run `33268601901` and Phase 6 readiness run `33268954572`
  both passed their workflows at exact HEAD `1af378b8`. The signed candidate
  is intentionally not a release-ready upload: its manifest has
  `backendRevision=null`, all upload flags false, and Phase 6 reports
  `upload_flag_false`; backend health is 200 on deployed revision
  `6a6080c6...`, while its legacy readiness response lacks the explicit auth
  marker (15 checks with the runner credential versus 0 for no/invalid
  header). Beta Review, tester coverage, and physical install evidence remain
  open. The writer/Fastlane contract was audited and requires origin/backend
  revision plus health equality only on the `upload_to_testflight=true` path,
  so no script change is warranted.
- 2026-08-30: After the redacted equality check (candidate and preserved old
  container plus `/home/jason/watchreview/.env`: length 64, identical digest
  `61b3728ba1e2808aea5ce7328300efe334fda8fe00aa5e5a220bce545a8374319`), the
  owner-authorized GitHub secret remediation was applied once via stdin:
  `AI_CADDIE_ADMIN_TOKEN` updated at `2026-08-30T05:13:15Z`. The secret value
  was not printed or persisted; GitHub does not expose it for a direct digest
  comparison. Native rerun is the next and only validation action.
- 2026-08-30: After the one-time authorized secret synchronization, dispatched
  exactly one live Native Mobile CI rerun `33294247633` at branch HEAD
  `1af378b811cd25edae12285c5745aef1b57d7faf` with `capture_scope=full`,
  `fixture_mode=false`, public API origin
  `https://caddie.taile36706.ts.net`, exact `backend_revision`, blank review
  reference, and `require_live_preflight=true`. The run passed launch
  prerequisites and live course discovery; iOS live-simulator and independent
  Watch/evidence stages were still running at this update. No TestFlight,
  signing, or additional deployment action was performed.
- 2026-08-30: Added the explicit owner-approved test-environment upload path in
  commit `8f141b9d9ea1697cda46c2c7c1fd10e32e468f74` (message:
  `ci: allow explicitly approved test-environment upload`). The Fastlane
  bypass only relaxes degraded operational readiness when both
  `test_environment_upload=true` and `upload_to_testflight=true`; public HTTPS
  origin, authenticated readiness shape, health schema, and exact backend
  revision checks remain mandatory. Homeserver verification passed the two
  focused workflow contract tests (`2/2`), remote Ruby `ruby -c` (`Syntax OK`),
  and `git diff --check`. The temporary Ruby container and scratch `.venv`
  were removed; the downloaded release artifact remains at
  `/home/jason/codex-runs/ios-testflight-33300858579-artifact`.
- 2026-08-30: With owner approval, dispatched exactly one iOS TestFlight CD
  run `33300858579` at commit
  `8f141b9d9ea1697cda46c2c7c1fd10e32e468f74`, using
  `api_base_url=https://caddie.taile36706.ts.net`, expected backend revision
  `1af378b811cd25edae12285c5745aef1b57d7faf`,
  `upload_to_testflight=true`, and `test_environment_upload=true`. Run/job
  `33300858579`/`99228619111` completed successfully. App Store Connect
  accepted and finished processing marketing version `0.1.0`, TestFlight build
  `44`, and set the requested changelog; no tester-device installation or
  launch has been independently verified. Release provenance reports
  `uploadRequested=true`, `uploadCompleted=true`, `uploadToTestflight=true`,
  and `backendRevisionVerified=true`. IPA SHA-256 is
  `1063aa602d2265aa94707178c6c152f0ecbc87c53982b8661738463084c4a584`;
  provenance JSON SHA-256 is
  `eeebce7c26cca567c9fb291c7ccd36b2756b0d95260b22de2b424b97f8fb8b3e`;
  GitHub artifact `AICaddie-ipa` ID `9728952402` has ZIP digest
  `93ed970bfe703d0a200f08413060af70a96b1f0ee02812626dea06cda9540213`.
  No production data, deployment, or persistent service state was modified by
  this release action.
- 2026-08-30: After the owner reproduced Apple's generic “Unable to Install”
  dialog for build 44, read-only status run `33308645751` confirmed the build
  remained valid, unexpired, and externally approved. The original build-44
  artifact then passed macOS strict/deep code-sign, iOS/Watch bundle/profile,
  Team ID, version, expiry, and architecture checks in run `33308974390`.
  With Apple reporting no TestFlight incident, replacement CD run
  `33309073713` built and uploaded `0.1.0 (45)` from commit
  `464d8d35880bc0a5fc728800aef196c7c74841c5`; IPA SHA-256 is
  `db1b135b3386d4a55ff104312a541fccdafbec1107980bf40d4ff1e107af8cc4`,
  artifact ID is `9731483890`, and artifact ZIP digest is
  `20143435fe4cd3399a316147558d940be4cfefe39bd22374f8de4934860b6a5d`.
  Distribution run `33309432780` submitted the build and assigned it to
  `Private Trial`; status run `33309492585` observed
  `externalState=IN_BETA_TESTING`, and exact-artifact diagnostic run
  `33309532213` passed. Physical installation remains the only open evidence.
