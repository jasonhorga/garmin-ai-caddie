# S70 Experience 与 Capability Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 canonical round runtime、不可变 CourseSnapshot/安装和逐能力 promotion 成立后，交付 S70 行为对标的 Hole Root、Map Detail、离线本地 Caddie、verified-elevation PlaysLike、hazard guidance、宏观 green preview、玩家球杆校准、真实二维 dispersion、上一洞成绩确认/下一洞暂存归属，以及最后接入 canonical ledger 的 AutoShot producer。

**Architecture:** Track D 只消费 Track A generated contracts，以及 Track B/Plan 2 已签名、已安装、已通过 capability quality gate 的静态 authority、当前设备 round pin 和动态 control；Plan 3 只提供仍为 research-only 的候选与证据，不能被 Track D 直接消费或自行解释成“已晋升”。iOS 与 Watch 从同一份本地已验证资产、LiveRoundPackage、玩家模型和 ephemeral GPS 运行同一确定性 Guidance engine；服务端只做同算法审计/在线增强，不能成为离线地图或球童前置条件。Web 只做治理、备战和只读复盘。AutoShot 永远通过与手动记杆相同的 producer/event factory 写 canonical ledger，且排在第一生产里程碑之后。

**Tech Stack:** Python 3.12、Pydantic v2/generated JSON Schema、unittest、FastAPI、Swift 5.9、SwiftUI、watchOS 10、XCTest、TypeScript 6、React 19、Vitest、Testing Library、XcodeGen。

---

## Authority、范围与依赖门

实施时按以下顺序判定权威：

1. `docs/superpowers/specs/2026-07-18-course-data-platform-and-unified-surfaces-design.md`
2. `docs/reviews/2026-07-15-watch-decision-and-task-tracker.md`，尤其 Tracker D02-C′、L07、L18、L19、D05、D12a、D12b、D13a/D13b、E05、E06、T030、T031
3. `docs/reviews/2026-07-16-s70-virtual-caddie-and-map-mechanisms-evidence.md` 的可观察行为证据；其文末尚未决定的 D02 问题已被 2026-07-17 tracker 决定覆盖
4. Track A/B/C 已完成计划与 generated machine contracts

硬门：

- **Track A gate:** Task D02 之前，`contracts/canonical/canonical_object_registry.json`、`contracts/canonical/reason_codes.json`、`tools/contracts/generate_contracts.py`、`ai_caddie/contracts/generated.py`、`mobile/ios/AICaddieDomain/GeneratedContracts.swift`、`mobile/ios/AICaddieDomain/DomainRoundEvent.swift`、`mobile/ios/AICaddieDomain/DomainLedgerStore.swift` 和 `web_v2/src/contracts/generated.ts` 必须存在并通过 Track A golden tests。Track D 不建立第二套 wire model、event、outbox 或 reducer。
- **Track B gate:** Task D05、D08b、D10、D12、D14b 需要已验证的 `CourseSnapshot`、服务端 `CourseRoundDevicePinRepo.require_active_runtime_pin(...)` 返回的当前认证设备 `VerifiedActiveCourseRoundPin`、本地 `CourseInstallFileAuthorityStore.loadVerifiedActiveRound(...)` 返回的 `VerifiedActiveRoundCourseAuthority`、immutable role-aware asset hash/manifest 和最新 verified effective control。UI 不得把 snapshot accepted 自行解释为 runtime available；联网 audit token 也不得反过来成为本地静态资产可用性的前置条件。
- **Plan 2/3 promotion gate:** Task D03/D04/D05 分别只接受 Plan 2 quality gate 已写入 signed snapshot/manifest/static authority 的 `playsLike`、`hazardGuidance`、`greenSurface` promoted product；当前 grant/safety/purge/rights/runtime control 由 D02c 独立投影，不写回静态身份。Plan 3 的 `DeepMinePromotionCandidate` 必须仍是 `research_only_candidate`、`targetGate=plan-2-capability-quality-gate`，只能由 Plan 2 消费；Track D 不直接 import 它。Research artifact、`geometry_evidence.py` 产物、当前 `Green.drc` 平面拟合和文件存在性只能作为 candidate/evidence，不能直接进入 Guidance。若 Plan 2 尚未为某能力发出带 `capabilityId/qualityReportId/evidenceRefs` 的 accepted static binding，停止对应任务，不用本地 `accepted=true` 绕过 gate。
- **Canonical owner gate:** Plan 4 只能在 Plan 1 已建立的串行 contract-owner lane 中扩展 registry/schema/generator。始终只有一个名为 `canonical-contracts` 的 generated group、一个 `tools/contracts/generate_contracts.py` 和三份 generated declarations；不得新建第二 group、第二 codegen、手写 generated DTO，或让同一 output 被两个 group 拥有。既有 `contracts/canonical/**/*.json` source pattern 自动覆盖本计划新增 JSON；每个 contract checkpoint 都必须重生成并 byte-check `generate_all()` 的完整 output set。
- **S70/AutoShot epistemic gate:** 本计划中的 “S70-like/S70-style” 只表示已引用证据文件覆盖的可观察导航、文案和交互目标，不表示 Garmin 公开或授权了其私有算法、阈值、传感器分类器、颜色 hex 或内部数据模型。所有 transition、shot-station、dispersion 和 AutoShot 阈值都是带本项目 policy/evidence identity 的 app-owned rollout policy；未完成真机证据时只能停在 unavailable/shadow/candidate，不得用 `s70-*` 标识或测试文案冒充 Garmin authority。
- **Native integration ownership gate:** Plan 2 B14/B15 继续唯一拥有 production installer-backed iOS fixture loader、`ios-v1` signed nine-hole fixture、real final-hole UI E2E 和 Watch cold-start installer E2E；Plan 4 不复制 loader、安装 fixture 或绕过真实 LRP/static authority。Plan 4 拥有安装完成后的 iOS/Watch Guidance、地图、记杆、确认和 AutoShot composition wiring，并在改动 app roots 后复跑 Plan 2 的既有 installer E2E 以及本计划两端 native schemes。
- **E04 gate:** Watch 41/46 mm 条件建议层必须通过 snapshot 与真机证据后才能默认开启。
- **Tracker-qualified AutoShot gate:** Task D15 Step 0 必须以 signed closure artifact 闭合 Tracker D12a、D12b、D13a、E05、E06/T030/T031：独立 opt-in、默认不上传、不持久化整轮原始高频流、设备采样/误报漏报/五小时续航、Workout/background/AOD/权限拒绝/抢占恢复均有 exact artifact。D12b 若未证明上传必要性，合法结论就是 `closed_local_only`，保持完全本地且不阻塞 Beta；只有证明确需研究数据捐赠时才触发 Tracker D12b/D13b 的条件 Owner 重开，本计划不得自行上传或写入 Apple Health。

第一生产里程碑止于 Task D14b：必须同时完成手动一杆、回杆/极短杆 canonical reconciliation、Club Prompt、上一洞成绩确认、未决下一洞击球归属、最后一洞结束、任意洞深改、离线结束和同步。Task D15 AutoShot 是最后一项，不得阻塞或替代该手动可靠闭环。

最终锁定接口：所有 round/shot fixture 使用合法 lowercase UUID；Map Touch Target 只通过 Track A `ShotCaptureSession` + `PlayerLiveFactProducer.setShotTarget()` 写 `shot_target_set/shot_target_retracted`，手动杆与 confirmed AutoShot 复用 session 预分配 `shotId`；玩家旗位只通过 `flag_position_set`。Plan 2 capability consumer 必须从 signed static bundle、exact verified ACK、当前认证设备 active pin 和最新 control 重新验证，不接受 caller-provided `accepted`/`available` Boolean。Logical promoted-asset binding 与 physical CAS blob 是两层身份：snapshot exact `assetBindings[{capability,subjectRef,role,assetHash}] → assetBlobs[]`，manifest logical group exact `{capability,subjectRef,role,assetRefs[]} → assets[]`；多个洞或能力可以合法共享同一 content hash，但 logical key 永远是 `(capability,subjectRef,role,assetHash)`。`map` 必须同时拥有 `map.geometry|map.transform|map.image` 三角色；geometry body frozen 为 immutable `ai-caddie-map-body-v1`，每个 `routePoints[]` 只含 exact `{targetRef,latitude,longitude,distanceFromTeeM,remainingDistanceToGreenM}`。当前球位距离只由 ephemeral GPS 计算，海拔只来自 `playsLike.elevation`，二者不得写入静态 map blob。D02c、D07a、D08b、D08c、D10a、D12a、D14a、D14b 是各自领域的最终规范化任务；与它们冲突的前序临时代码必须删除，不能保留为 fallback。

## File Structure

### Canonical contract extension（Track A codegen owner）

- Create: `contracts/canonical/guidance_v1.schema.json` — final current-shot envelope with distinct aim/landing、dispersion、freshness and absence reasons。
- Create: `contracts/canonical/caddie_plan_v1.schema.json`、`guidance_api_response_v1.schema.json` — full-plan detail and optional online audit envelope。
- Create: `contracts/canonical/guidance_engine_bundle_v1.schema.json`、`live_current_position_v1.schema.json` — pinned local engine/mode policy and ephemeral GPS input。
- Create: `contracts/canonical/player_bag_snapshot_v1.schema.json`、`contracts/canonical/player_guidance_model_v1.schema.json` — 完整球包/设定距离与证据学习模型分层；两者共同由 LRP 冻结。
- Create: `contracts/canonical/shot_recovery_policy_v1.schema.json` — pinned app-owned near-station/return-path policy used by manual and later AutoShot reconciliation。
- Create: `contracts/canonical/fixtures/shot_recovery_policy_golden.json` — exact cross-language policy/body/ID and boundary fixture。
- Create: `contracts/canonical/hole_transition_policy_v1.schema.json` — exact versioned Green/departure/next-Tee detector thresholds and conservative uncertainty semantics。
- Create: `contracts/canonical/fixtures/hole_transition_policy_golden.json` — exact policy body/hash plus below/at/above-threshold vectors。
- Modify: `contracts/canonical/live_round_package_v2.schema.json` — require exact `PlayerBagSnapshot/v1`、canonical Guidance engine bundle、exact `ShotRecoveryPolicy/v1` and `HoleTransitionPolicy/v1` bindings；仍不含风。
- Create: `contracts/canonical/fixtures/guidance/current_shot_available.json` — available golden payload。
- Create: `contracts/canonical/fixtures/guidance/current_shot_unavailable.json` — unavailable golden payload。
- Modify: `contracts/canonical/canonical_object_registry.json` — 保留 Track A 的 `RoundFactsVersion/v1`，并以权威名称注册/细化 `GuidanceInput/v1` 与 `GuidanceCandidate/v1` canonical domains。
- Modify: `contracts/canonical/reason_codes.json` — 只追加本计划使用的稳定 reason codes。
- Regenerate: `ai_caddie/contracts/generated.py`、`mobile/ios/AICaddieDomain/GeneratedContracts.swift`、`web_v2/src/contracts/generated.ts` — 禁止手改生成文件。

### Python guidance 与 calibration

- Create: `ai_caddie/guidance/__init__.py` — package boundary。
- Create: `ai_caddie/guidance/models.py` — internal immutable inputs/results 与 wire conversion。
- Create: `ai_caddie/guidance/playslike.py` — verified-elevation-only engine。
- Create: `ai_caddie/guidance/hazards.py` — promoted hazard semantic 与 landing-window consumer。
- Create: `ai_caddie/guidance/map_geometry.py` — strict immutable `map` capability decoder and current-position/route-target resolver。
- Create: `ai_caddie/guidance/caddie_engine.py` — current-shot candidates、deterministic selection 和 absence gates。
- Create: `ai_caddie/guidance/planning_models.py`、`ai_caddie/guidance/multi_shot.py`、`ai_caddie/guidance/guidance_input.py`、`ai_caddie/guidance/stochastic_planner.py`、`ai_caddie/guidance/route_utility_planner.py` — pure planning values、full-plan search、relevant-input identity 和两个门控算法。
- Create: `ai_caddie/players/club_calibration.py` — canonical shot sample admission、2D shot frame、robust covariance/ellipse。
- Create: `ai_caddie/courses/green_surface.py` — promoted macro surface binding 与 base geometry registration consumer。
- Create: `server_v2/guidance.py` — thin guidance and calibration API router。
- Create: `server_v2/guidance_capability_repo.py` — exact current-device pin/control selector over the pure role-aware static verifier。
- Create: `server_v2/guidance_context_repo.py` — authenticated Track A facts、player calibration and verified Track B/C capability composition。
- Create: `server_v2/guidance_manifest_trust.py` — startup-only manifest trust rehydration retaining every historical rotated leaf。
- Create: `server_v2/player_guidance_models.py`、`server_v2/player_guidance_model_repo.py`、`server_v2/guidance_model_provider.py` — immutable learned models、concurrent content-addressed persistence and pinned bag/model provider。
- Modify: `ai_caddie/rounds/resolution_commit.py`、`ai_caddie/rounds/ledger_repo.py`、`tests/resolution_commit_fixtures.py`、`tests/test_resolution_commit_v2.py` — D14b consumes Track A's exact confirmed-loser roster、decision hash、staged disposition and final-shot bijection for explicit same-scope conflict merging。
- Create: `ai_caddie/rounds/active_play_cursor.py`、`contracts/canonical/fixtures/active_play_cursor_timelines.json` — D14b's pure canonical cursor projector and cross-language Confirm/Manual/Cancel/final-hole/restart/conflict timelines；`RoundProjectionV2.viewMappings.currentHole` consumes this result rather than score rows or mutable UI state。
- Modify: `ai_caddie/rounds/reducer_v2.py`、`tests/test_round_reducer_v2.py` — route canonical projection current-hole ownership through the D14b projector and prove historical score edits cannot move live play。
- Modify: `ai_caddie/rounds/ledger_models.py`、`ai_caddie/rounds/ledger_repo.py`、`server_v2/round_ledger_api.py` — D15 narrows Track A's temporary blanket AutoShot provenance guard so only episode-free、unreserved explicit confirmations may use ordinary transport；resolution-owned shots remain commit-only。
- Modify: `server_v2/course_models.py` — add the immutable player-guidance row owned by migration `0012`。
- Create: `migrations/versions/0012_player_guidance_model.py` — Plan 4 唯一 migration，承接 Plan 2 `0011_device_course_authority`。
- Modify: `server_v2/course_dependencies.py` — inject the startup-rehydrated manifest trust history、CAS and repository context provider。
- Modify: `server_v2/main.py` — register the router and install the production provider exactly once。
- Modify: `ai_caddie/courses/course_prep.py` — quarantine legacy `greenSlope` and prevent static strategy from being presented as live guidance。
- Modify: `ai_caddie/caddie/mobile_live.py`、`ai_caddie/caddie/decision.py` — remove fabricated fallback, weather/wind consumption and uncalibrated UI claims from Track D adapters。

### Shared Apple domain 与 iOS

- Create: `mobile/ios/AICaddieDomain/Guidance/GuidanceCoordinator.swift` — shared live-position/freshness/mode/local-static-authority projection。
- Create: `mobile/ios/AICaddieDomain/Guidance/GuidanceRuntimeCapability.swift` — optional online audit-token verifier；不得作为离线 Guidance 前置条件。
- Create: `mobile/ios/AICaddieDomain/Guidance/GuidanceResponseDecoder.swift` — strict current-shot/detail/runtime-capability response split shared by iOS and Watch。
- Create: `mobile/ios/AICaddieDomain/Guidance/GuidanceInputIdentity.swift` — 生成 `GuidanceInput/v1` 的 relevant-input `inputHash`，不建立第二个 version domain。
- Create: `mobile/ios/AICaddieDomain/Guidance/GuidanceMapGeometry.swift` — distinct `aimTarget` line、`predictedLanding` ellipse center and shot-frame rotation。
- Create: `mobile/ios/AICaddieDomain/Guidance/PlayerGuidanceModelStore.swift` — persist and reverify exact LRP/bag/model canonical bytes across restart。
- Create: `mobile/ios/AICaddieDomain/Guidance/GuidanceFreshnessClock.swift` — nondecreasing local freshness clock、trusted-time floor and rollback fail-closed boundary shared by iOS/Watch。
- Create: `mobile/ios/AICaddieDomain/Guidance/GuidanceManualRequestAction.swift` — shared iOS/Watch manual-mode CTA projection and durable request/result recovery over `GuidanceModeStore`。
- Create: `mobile/ios/AICaddieDomain/Map/VerifiedMapAssetSet.swift`、`MapCoordinateTransform.swift`、`MapViewportTransform.swift`、`MapMechanics.swift` — exact map trio、ENU↔pixel、shared viewport and metric overlays。
- Create: `mobile/ios/AICaddieDomain/ClubCalibration/ClubCalibrationSummary.swift` — generated-wire-to-view projection only。
- Create: `mobile/ios/AICaddieDomain/Presentation/PlaysLikePresentation.swift` — immutable raw-versus-adjusted projection with explicit uphill/downhill semantics and no wind。
- Reuse: `mobile/ios/AICaddieDomain/ShotCapture/ManualShotProducer.swift` — Track A canonical manual producer; Track D only wires it into S70 surfaces。
- Create: `mobile/ios/AICaddieDomain/ShotCapture/ShotRecoveryPolicy.swift`、`ShotObservationJournal.swift`、`ShotStationReducer.swift` — T054 durable observation/recovery path。
- Create: `mobile/ios/AICaddieDomain/ShotCapture/ClubPromptProducer.swift`、`ClubPromptVisibleCountdown.swift` — T055 actual-club-only producer and visible eight-second clock。
- Create: `mobile/ios/AICaddieDomain/ShotCapture/ShotStationCanonicalizer.swift` — proposal-to-canonical retraction/replacement saga shared by ledger、stats and calibration。
- Create: `mobile/ios/AICaddieDomain/Scoring/HoleTransitionPolicy.swift`、`HoleTransitionEvidence.swift`、`HoleTransitionDetector.swift`、`HoleTransitionCheckpointStore.swift`、`TransitionShotPreflight.swift`、`TransitionShotPreparationJournal.swift`、`DefaultHoleScoreSuggestion.swift`、`FirstShotLandingClassifier.swift`、`TransitionStageOwnershipClassifier.swift`、`ActivePlayCursorProjector.swift`、`ResolutionEpisode.swift`、`ProvisionalHoleState.swift`、`ResolutionOpenedWireFactory.swift`、`ResolutionShotStagedWireFactory.swift`、`PendingShotOwnershipJournal.swift`、`HoleScoreResolutionRequestFactory.swift`、`HoleScoreTransaction.swift`、`HoleScoreCoordinator.swift` — versioned S70 score confirmation detector、per-stage previous/next ownership、canonical active-play cursor、next-Tee first-shot race closure、scope-local canonical episodes and one actionable flow per round incarnation。
- Modify: `mobile/ios/AICaddieDomain/ResolutionCommit.swift`、`mobile/ios/AICaddieDomainTests/ResolutionCommitTests.swift` — reuse Track A's exact `confirmedLoserStageEventIdentities` contract and verify conflict-merge roster/hash/final-shot bijection across restart and takeover。
- Create: `mobile/ios/AICaddieDomain/ShotCapture/AutoShotCandidate.swift` — candidate lifecycle; no direct statistics writes。
- Create: `mobile/ios/AICaddieDomain/ShotCapture/AutoShotEvidence.swift`、`AutoShotControl.swift`、`AutoShotDecisionOutbox.swift` — signed gates、monotonic control and restart-safe canonical decision journal。
- Modify: `mobile/ios/AICaddieDomain/ShotCapture/ShotCaptureSession.swift`、`mobile/ios/AICaddieDomain/DomainLedgerStore.swift`、`mobile/ios/AICaddieDomain/DomainRoundEvent.swift`、`mobile/ios/AICaddieDomain/RoundPayloadValidator.swift` — durable shot-slot ownership、claim-aware manual append、episode-free AutoShot ordinary classification and atomic claimed-shot reconciliation。
- Modify: `mobile/ios/AICaddieDomainTests/ManualShotProducerTests.swift`、`mobile/ios/AICaddieDomainTests/RoundPayloadValidatorTests.swift` — claimed-slot exclusion and exact stateless-versus-stateful AutoShot boundaries。
- Create: `mobile/ios/AICaddieDomainTests/AutoShotCandidateTests.swift` — exactly-once restart、episode/stage exclusion and terminal-retention regressions。
- Create: `mobile/ios/AICaddieWatchTests/WatchAutoShotLiePickerTests.swift` — known-lie one-tap、unknown-lie explicit picker、restart/mutation and 41/46 mm accessibility regressions。
- Create: `mobile/ios/AICaddieWatchTests/WatchMotionShotProducerTests.swift` — journal-preparation-before-ledger、ledger-before-journal-terminal、ledger/outbox-before-ACK、legacy manual conflict and prior-round crash coverage。
- Create: `mobile/ios/AICaddie/Views/Live/HoleRootView.swift` — permanent facts plus optional one-shot layer。
- Create: `mobile/ios/AICaddie/Views/Live/ShotRecoveryBanner.swift` — non-modal “打厚了，算上一杆” recovery affordance over the durable proposal。
- Create: `mobile/ios/AICaddie/Views/Live/MapDetailView.swift` — driver arc、touch target、hazard、current-shot Guidance separated。
- Create: `mobile/ios/AICaddie/Views/Live/CaddieDetailView.swift` — current-shot alternatives with calibrated-only combination `AVG. STROKES` and no probabilities。
- Create: `mobile/ios/AICaddie/Views/ClubCalibration/ClubCalibrationView.swift` — sample/provenance/2D status。
- Create: `mobile/ios/AICaddie/Views/ReviewEditHoleView.swift` — arbitrary-hole deep score editing over canonical superseding facts。
- Modify: `mobile/ios/AICaddie/Views/CurrentHoleView.swift`、`HoleImageMapView.swift`、`CaddiePlanView.swift` — host new boundaries and delete legacy live semantics。
- Create conditionally after D15 evidence approval: `mobile/ios/AICaddieWatch/AICaddieWatch.entitlements` — minimum Watch capability file only after the evidence gate passes；the file does not exist before this task。
- Modify conditionally after D15 evidence approval: `mobile/ios/AICaddieWatch/Info.plist`、`mobile/ios/project.yml` — truthful Motion/Workout permission and build metadata only after the evidence gate passes。
- Modify: `mobile/ios/AICaddie/AICaddieApp.swift`、`mobile/ios/AICaddieWatch/AICaddieWatchApp.swift` — reverify raw local signed authority and run one offline-first engine；authenticated response tokens are audit-only。

### Watch

- Create: `mobile/ios/AICaddieWatch/Services/WatchGuidanceCoordinator.swift` — single shared-domain guidance state。
- Create: `mobile/ios/AICaddieWatch/Services/WatchShotRecoveryCoordinator.swift` — monotonic Motion/GPS observation journal and pending-candidate recovery。
- Create: `mobile/ios/AICaddieWatch/Services/WatchMotionShotProducer.swift` — shadow/candidate producer behind evidence gate。
- Create: `mobile/ios/AICaddieWatch/Services/WatchHoleScoreCoordinator.swift`、`WatchResolutionPeerTransfer.swift` — canonical episode presentation and exact prepared-commit takeover over Track A peer transport。
- Create: `mobile/ios/AICaddieWatch/Views/HoleRoot/WatchHoleRootView.swift` — facts-first root。
- Create: `mobile/ios/AICaddieWatch/Navigation/WatchInstrumentRoute.swift`、`mobile/ios/AICaddieWatch/Views/HoleRoot/WatchRootInstrumentDock.swift`、`mobile/ios/AICaddieWatch/Views/HoleRoot/WatchGolfToolsSheet.swift`、`mobile/ios/AICaddieWatch/Views/HoleRoot/WatchInstrumentUnavailableView.swift` — exact root→instrument mapping、two-action dock、S70-like shallow Golf Tools entry and honest typed zero states without sibling pages。
- Create: `mobile/ios/AICaddieWatch/Views/MapDetail/WatchMapDetailView.swift` — explicit map interaction surface。
- Create: `mobile/ios/AICaddieWatch/Views/Caddie/WatchCaddieDetailView.swift` — current-shot details。
- Create: `mobile/ios/AICaddieWatch/Views/Hazard/WatchHazardDetailView.swift` — semantic enter/clear guidance。
- Create: `mobile/ios/AICaddieWatch/Views/Green/WatchMacroGreenView.swift` — gated macro surface only。
- Create: `mobile/ios/AICaddieWatch/Views/ShotCapture/WatchClubPromptView.swift` — tap-complete actual-club prompt; Crown is enhancement only。
- Create: `mobile/ios/AICaddieWatch/Views/ShotCapture/WatchShotRecoveryView.swift` — queued near-station explanation/recovery action with persistent later access。
- Create: `mobile/ios/AICaddieWatch/Services/WatchAutoShotCoordinator.swift`、`Views/ShotCapture/WatchAutoShotCandidateView.swift`、`Views/ShotCapture/WatchAutoShotLiePickerView.swift` — Watch-owned D15 Automatic/Candidate decision、explicit unknown-lie resolution、fallback visible-time pause/resume、haptic and arbiter priority；iPhone does not expose a second mutable pending-candidate flow。
- Create: `mobile/ios/AICaddieWatch/Views/Scoring/WatchHoleScoreConfirmView.swift`、`WatchManualHoleScoreFlow.swift`、`WatchScorecardEditView.swift` — highest-priority confirmation and arbitrary-hole editing。
- Modify: `mobile/ios/AICaddieWatch/AICaddieWatchApp.swift`、`Views/WatchRoundContainerView.swift`、`Views/WatchHoleMapView.swift`、`Models/WatchRoundState.swift` — remove second truth and legacy map semantics。
- Modify: `mobile/ios/AICaddieWatch/Services/WatchHoleImageStore.swift` — immutable `(snapshot,subject,map.image hash)` key plus role-aware image/transform/geometry verification。

### Web governance/review only

- Create: `web_v2/src/contracts/guidanceRuntimeCapability.ts` — verifier-only online audit-token decoder bound to authenticated response、round、install and logical asset identity；不决定离线 availability。
- Create: `web_v2/src/contracts/guidanceRuntimeCapability.test.ts` — relabel/tamper/shared-blob/cross-hole rejection regressions。
- Create: `web_v2/src/components/course/CapabilityBadge.tsx` — four-layer/effective reason presentation。
- Create: `web_v2/src/components/prep/HazardGuidancePanel.tsx` — promoted evidence inspection。
- Create: `web_v2/src/components/clubs/ClubCalibrationPanel.tsx` — calibration version/sample/provenance。
- Create: `web_v2/src/components/review/ClubDispersionPlot.tsx` — true covariance ellipse for review。
- Modify: `web_v2/src/components/PrepInspector.tsx`、`CaddiePage.tsx`、`ClubBagPage.tsx`、`StatsDashboard.tsx`、`types.ts` — consume generated contracts; do not add a browser GPS producer or reducer。

## Task D00: Quarantine misleading backend outputs

**Files:**
- Modify: `ai_caddie/courses/course_prep.py:380-390,607-668`
- Modify: `ai_caddie/caddie/mobile_live.py:1571-1655,1706-1930`
- Test: `tests/test_track_d_safety_gates.py`
- Test: `tests/test_course_prep_playslike.py`
- Test: `tests/test_mobile_contracts.py`

- [ ] **Step 1: Write failing safety-gate tests**

```python
# tests/test_track_d_safety_gates.py
from __future__ import annotations

import unittest

from ai_caddie.caddie.mobile_live import _package_club_profiles
from ai_caddie.courses import course_prep


class TrackDSafetyGateTests(unittest.TestCase):
    def test_legacy_green_slope_is_always_quarantined(self) -> None:
        green = {
            "Green.drc": {
                "positions": [[0.0, 0.0, 0.0], [1.0, 0.2, 0.0], [0.0, 0.2, 1.0]],
                "faces": [[0, 1, 2]],
            }
        }
        self.assertEqual(
            course_prep._green_slope(green),
            {
                "available": False,
                "reasonCode": "green_surface_not_promoted",
                "legacySource": "course_prep_green_drc_plane_fit",
            },
        )

    def test_empty_history_never_fabricates_a_club_profile(self) -> None:
        self.assertEqual(_package_club_profiles({"clubs": []}, player_id="player-1"), [])

    def test_zero_sample_rows_are_not_guidance_profiles(self) -> None:
        stats = {
            "clubs": [
                {"club": "8I", "sampleCount": 0, "median": 140.0, "p10": 130.0, "p90": 150.0}
            ]
        }
        self.assertEqual(_package_club_profiles(stats, player_id="player-1"), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and verify the missing helper/current green output fails**

Run: `AI_CADDIE_DATA_MODE=fixture uv run python -m unittest tests.test_track_d_safety_gates -v`

Expected: FAIL importing `_package_club_profiles` or FAIL because `_green_slope` returns a fitted plane.

- [ ] **Step 3: Quarantine `greenSlope` and extract honest club-profile construction**

Replace `_green_slope` in `ai_caddie/courses/course_prep.py` with:

```python
def _green_slope(by: dict) -> dict:
    del by
    return {
        "available": False,
        "reasonCode": "green_surface_not_promoted",
        "legacySource": "course_prep_green_drc_plane_fit",
    }
```

Add next to `_decision_club_profiles` in `ai_caddie/caddie/mobile_live.py`:

```python
def _package_club_profiles(stats: dict[str, Any], *, player_id: str) -> list[dict[str, Any]]:
    from ai_caddie.caddie.club_bag import restrict_to_bag

    profiles = [
        {
            "clubName": row.get("club"),
            "sampleSize": int(row.get("sampleCount") or 0),
            "median_m": float(row["median"]),
            "p10_m": float(row.get("p10") or row["median"]),
            "p90_m": float(row.get("p90") or row["median"]),
            "sampleRefs": _compact_source_refs(
                row.get("validShotRefs") or [], limit=OFFLINE_OPTION_SAMPLE_REF_LIMIT
            ),
        }
        for row in stats.get("clubs") or []
        if row.get("club")
        and row.get("median") is not None
        and int(row.get("sampleCount") or 0) > 0
    ]
    return restrict_to_bag(profiles, lambda row: row.get("clubName"), player_id=player_id)
```

In `build_live_round_package`, replace the inline `club_profiles` list/restrict/fallback block with:

```text
    club_profiles = _package_club_profiles(stats, player_id=player_id)
    if not club_profiles:
        package_missing_data.append(
            {
                "label": "club_calibration",
                "reason": "no confirmed player club samples are available",
            }
        )
```

Do not add a replacement default club. Phase 0/Track A removes weather from the v2 LRP; retain only the v1 neutral compatibility serializer required by the Phase 0 plan.

- [ ] **Step 4: Run focused backend regression**

Run: `AI_CADDIE_DATA_MODE=fixture uv run python -m unittest tests.test_track_d_safety_gates tests.test_course_prep_playslike tests.test_mobile_contracts -v`

Expected: all tests PASS; package fixtures contain no fabricated `8I` profile and `greenSlope.available` is false.

- [ ] **Step 5: Commit the safety quarantine**

```bash
git add ai_caddie/courses/course_prep.py ai_caddie/caddie/mobile_live.py tests/test_track_d_safety_gates.py tests/test_course_prep_playslike.py tests/test_mobile_contracts.py
git commit -m "fix: quarantine unpromoted Track D outputs"
```

## Task D01: Establish honest zero states on iOS, Watch, and Web

**Files:**
- Modify: `mobile/ios/AICaddie/Views/CurrentHoleView.swift:692-705,982-1045`
- Modify: `mobile/ios/AICaddie/Views/CaddiePlanView.swift:88-105,306-345`
- Modify: `mobile/ios/AICaddieWatch/Views/WatchHoleMapView.swift:193-312`
- Modify: `mobile/ios/AICaddieWatch/Views/WatchCaddieOptionsView.swift:45-62`
- Modify: `web_v2/src/components/CaddiePage.tsx:557-905`
- Modify: `web_v2/src/components/StatsDashboard.tsx:184-270`
- Test: `mobile/ios/AICaddieTests/DesignSnapshotTests.swift`
- Test: `mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift`
- Test: `web_v2/src/components/CaddiePage.test.tsx`
- Test: `web_v2/src/components/StatsDashboard.test.tsx`

- [ ] **Step 1: Add failing client assertions for the legal zero state**

Add to `mobile/ios/AICaddieTests/DesignSnapshotTests.swift`:

```swift
func testUncalibratedCaddieDoesNotMutateActualClubOrShowExpectedStrokes() {
    let state = CaddiePlanPresentation(
        recommendedClub: "8I",
        selectedActualClub: nil,
        calibrationAvailable: false
    )
    XCTAssertNil(state.actualClubAfterRecommendation)
    XCTAssertNil(state.legacyMetricText)
}
```

Add to `mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift`:

```swift
func testMissingGuidanceProducesFactsOnlyMapLayers() {
    XCTAssertEqual(
        WatchLegacyMapLayerPolicy.layers(hasVerifiedGuidance: false),
        [.facts]
    )
}
```

Add to `web_v2/src/components/CaddiePage.test.tsx`:

```tsx
it('hides weather, expected strokes, and whole-hole sequences without promoted guidance', () => {
  render(
    <CaddiePage
      decisionState={{ status: 'ready', data: decision }}
      contextState={{ status: 'ready', data: caddieContext }}
      onRequestDecision={vi.fn()}
    />,
  )
  expect(screen.queryByText(/天气|Weather/)).not.toBeInTheDocument()
  expect(screen.queryByText(/AVG\. STROKES|预计杆数/)).not.toBeInTheDocument()
  expect(screen.queryByText(/整洞方案/)).not.toBeInTheDocument()
})
```

Add to `web_v2/src/components/StatsDashboard.test.tsx`:

```tsx
it('does not label directional percentages as calibrated dispersion', () => {
  renderDashboard()
  expect(screen.queryByText(/二维散布|置信椭圆/)).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run each surface test and verify it fails**

Run: `swift test --filter AICaddieTests.DesignSnapshotTests`

Expected: FAIL because `CaddiePlanPresentation` does not exist.

Run: `swift test --filter AICaddieWatchTests.WatchDesignSnapshotTests`

Expected: FAIL because `WatchLegacyMapLayerPolicy` does not exist.

Run: `cd web_v2 && npm test -- --run src/components/CaddiePage.test.tsx src/components/StatsDashboard.test.tsx`

Expected: FAIL because legacy Weather/expected-strokes/dispersion claims are still rendered.

- [ ] **Step 3: Add minimal presentation guards and delete misleading fallback visuals**

Add to `mobile/ios/AICaddie/Views/CaddiePlanView.swift`:

```swift
struct CaddiePlanPresentation: Equatable {
    let recommendedClub: String?
    let selectedActualClub: String?
    let calibrationAvailable: Bool

    var actualClubAfterRecommendation: String? { selectedActualClub }
    var legacyMetricText: String? {
        _ = calibrationAvailable
        return nil
    }
}
```

Delete `syncSelectedClubToRecommendation()` and every call to it from `CurrentHoleView.swift`. Remove `scoreImpactText` and whole-hole `sequenceCards` from `CaddiePlanView`; Task D10 adds only calibrated current-shot details through `CaddieDetailView`.

Add to `mobile/ios/AICaddieWatch/Views/WatchHoleMapView.swift`:

```swift
enum WatchLegacyMapLayer: Equatable {
    case facts
}

enum WatchLegacyMapLayerPolicy {
    static func layers(hasVerifiedGuidance: Bool) -> [WatchLegacyMapLayer] {
        _ = hasVerifiedGuidance
        return [.facts]
    }
}
```

Remove the unconditional caddie chip, `you → layup → green` path and fixed 30×26 ellipse from the legacy `WatchHoleMapView` body. Remove `expectedStrokes` text from `WatchCaddieOptionsView`.

In `CaddiePage.tsx`, remove the Weather panel, `DecisionScoreImpact` and `DecisionSequences` from the rendered live decision surface. In `StatsDashboard.tsx`, relabel the four directional percentages as “方向趋势” and render bars only; do not draw an ellipse.

- [ ] **Step 4: Run client regressions**

Run: `swift test --filter AICaddieTests.DesignSnapshotTests && swift test --filter AICaddieWatchTests.WatchDesignSnapshotTests`

Expected: both filtered suites PASS.

Run: `cd web_v2 && npm test -- --run src/components/CaddiePage.test.tsx src/components/StatsDashboard.test.tsx`

Expected: 2 test files PASS.

- [ ] **Step 5: Commit the cross-surface zero state**

```bash
git add mobile/ios/AICaddie/Views/CurrentHoleView.swift mobile/ios/AICaddie/Views/CaddiePlanView.swift mobile/ios/AICaddieTests/DesignSnapshotTests.swift mobile/ios/AICaddieWatch/Views/WatchHoleMapView.swift mobile/ios/AICaddieWatch/Views/WatchCaddieOptionsView.swift mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift web_v2/src/components/CaddiePage.tsx web_v2/src/components/StatsDashboard.tsx web_v2/src/components/CaddiePage.test.tsx web_v2/src/components/StatsDashboard.test.tsx
git commit -m "fix: enforce honest caddie zero states"
```

## Task D02: Freeze the final current-shot Guidance contract

**Depends on:** Track A canonical registry/codegen. This task defines the final wire shape consumed by D08b–D13. It preserves the authority spec's `RoundFactsVersion/v1` registry object, uses `GuidanceInput/v1` for the relevant-input identity, and carries exact relevant `entityRevisions`; neither a full-round facts hash nor any revision token is capability authority.

**Files:**
- Create: `contracts/canonical/guidance_v1.schema.json`
- Create: `contracts/canonical/fixtures/guidance/current_shot_available.json`
- Create: `contracts/canonical/fixtures/guidance/current_shot_unavailable.json`
- Modify: `contracts/canonical/canonical_object_registry.json`
- Modify: `contracts/canonical/reason_codes.json`
- Modify: `tools/contracts/generate_contracts.py`
- Regenerate: `ai_caddie/contracts/generated.py`
- Regenerate: `mobile/ios/AICaddieDomain/GeneratedContracts.swift`
- Regenerate: `web_v2/src/contracts/generated.ts`
- Test: `tests/test_guidance_contract.py`
- Test: `tests/test_contract_codegen.py`
- Test: `mobile/ios/AICaddieDomainTests/GuidanceContractTests.swift`
- Test: `web_v2/src/contracts/generated.test.ts`

- [ ] **Step 1: Write failing exact-shape and semantic contract tests**

The available golden is exact and uses distinct planning coordinates:

```json
{
  "schema": "ai-caddie-guidance-v1",
  "guidanceId": "11111111-1111-4111-8111-111111111111",
  "candidateHash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "inputHash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "entityRevisions": [{
    "scopeId": "round:11111111-1111-4111-8111-111111111111:active-play-hole",
    "reducerVersion": "round-reducer-v2",
    "canonicalOrdinal": 4,
    "entityProjectionHash": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    "contributingEventSetHash": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    "provisionalFlag": false
  }],
  "snapshotId": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
  "staticAuthorityHashes": [
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
    "9999999999999999999999999999999999999999999999999999999999999999"
  ],
  "plannerMode": "calibrated_route_utility_v1",
  "producer": "local",
  "engineBuild": "local-guidance-engine-v1",
  "executionLocation": "local",
  "selectionPolicyVersion": "guidance-selection-v2",
  "generatedAt": "2026-07-18T10:00:00.000Z",
  "validUntil": "2026-07-18T10:00:12.000Z",
  "availability": "available",
  "mode": "automatic",
  "reasonCodes": [],
  "invalidationReasons": [
    "guidance_input_changed",
    "gps_stale",
    "movement_resumed",
    "mode_changed",
    "control_changed"
  ],
  "recommendedClubRef": "club:3w",
  "aimTarget": {
    "targetRef": "route:station:205",
    "latitude": 22.2801,
    "longitude": 114.1624,
    "routeStationM": 205.0,
    "baseHorizontalDistanceM": 201.4
  },
  "predictedLanding": {
    "latitude": 22.28,
    "longitude": 114.16235,
    "routeStationM": 201.8,
    "alongM": 198.0,
    "crossM": -3.0
  },
  "shotFrameBearingDeg": 31.5,
  "dispersion": {
    "covarianceXXM2": 169.0,
    "covarianceXYM2": 12.0,
    "covarianceYYM2": 81.0,
    "confidence": 0.68,
    "sampleSize": 24,
    "calibrationVersion": "club-model-v7"
  },
  "playsLike": null,
  "hazards": [],
  "rationale": ["three_wood_reduces_right_tail"],
  "evidenceRefs": ["club-model-v7", "map-quality-1"]
}
```

The unavailable golden keeps identity/relevant entity revisions/freshness/mode/reasons but requires `recommendedClubRef/aimTarget/predictedLanding/shotFrameBearingDeg/dispersion/playsLike` to be `null` and `hazards/rationale/evidenceRefs` to be empty unless the schema explicitly permits evidence for the blocked reason. Tests reject extra keys, duplicate arrays, NaN/Infinity, invalid timestamps, invalid covariance, unavailable payloads carrying geometry, available payloads missing any current-shot field, non-UUID `guidanceId`, non-hex typed IDs, an unsorted/duplicate revision scope, or a revision token that differs from Track A's exact six-field generated shape.

The nested exact contracts are:

- `aimTarget`: `targetRef,latitude,longitude,routeStationM,baseHorizontalDistanceM`; `routeStationM` may be null only for a verified explicit off-route Touch Target.
- `predictedLanding`: `latitude,longitude,routeStationM,alongM,crossM`; it is the ellipse center, not the aim point.
- `dispersion`: `covarianceXXM2,covarianceXYM2,covarianceYYM2,confidence,sampleSize,calibrationVersion`; covariance must be positive semidefinite.
- `playsLike`: optional exact `baseHorizontalDistanceM,elevationDeltaM,adjustmentM,distanceM,engineVersion,evidenceRefs`; it exists only for D03/D08c verified elevation/model output, uses finite meters internally and sorted-unique evidence, and contains no wind/weather field. Unavailable is represented by root `playsLike=null`, never a stale or fabricated number.
- `shotFrameBearingDeg`: finite `[0,360)`; the displayed ellipse rotation is this value plus the covariance eigen angle.
- `plannerMode`: `stochastic_expected_strokes_v1|calibrated_route_utility_v1`. Probability values and any numeric `expectedStrokes` field are forbidden in `GuidanceEnvelopeV1`, `CaddiePlanV1`, `GuidanceAPIResponseV1` and every UI projection. `GuidanceEnvelopeV1` never carries AVG. STROKES. D08a may add exactly one nullable, combination-level `averageStrokes` field to `CaddiePlanV1`; it is non-null only for a fully gated `stochastic_expected_strokes_v1` result and is rendered only in full iOS/Watch Caddie detail, never on Hole Root or Web. The pinned internal `PlayerGuidanceModelSnapshot/v1` resource may carry exact recovery-state `expectedStrokes` rows for offline computation, but no generated presentation type may expose or copy those rows directly.
- `mode`: `automatic|manual|off|big_numbers|tournament`.

- [ ] **Step 2: Preserve the authority registry and register only the relevant Guidance identities**

Keep Track A's `RoundFactsVersion/v1` entry exactly because §5.10/§5.11 require it for canonical projection/audit identity. Register the relevant-input object as `GuidanceInput/v1`—not a new `GuidanceInputVersion/v1` domain—and keep `GuidanceCandidate/v1`. `inputHash` is the `GuidanceInput/v1` typed ID over D08b's canonical relevant input. The candidate ID follows the registry's exact included/excluded fields; `generatedAt` and `validUntil` remain identity-bearing unless the registry and all three cross-language goldens explicitly change together. `entityRevisions` is a sorted-unique array by `scopeId` and uses Track A's generated `EntityRevisionToken` shape. Append stable reason codes for static authority, live position, route projection, player model, mode, control and planner-prerequisite failures.

Add a registry regression proving that `RoundFactsVersion`, `GuidanceInput` and `GuidanceCandidate` all resolve their `$ref`s and domain tags exactly. The test mutates each relevant-input field and each entity-revision hash and proves `inputHash`/`candidateHash` changes; mutating transport arrival metadata alone must follow the registry exclusion rule rather than an ad-hoc D02 canonicalizer.

- [ ] **Step 3: Generate Python, Swift, and TypeScript models from the schema**

The generator is the sole owner of wire types. Generated models must use strict unknown-key rejection, finite numeric checks, sorted-unique helpers and exact nullable semantics. No hand-written app DTO may shadow `GuidanceEnvelopeV1`, `GuidanceAimTargetV1`, `GuidancePredictedLandingV1` or `GuidanceDispersionV1`. `GuidanceDispersionV1` is deliberately a **current-shot covariance-only** value; its exact keys remain `covarianceXXM2,covarianceXYM2,covarianceYYM2,confidence,sampleSize,calibrationVersion`, because the current-shot center already lives in `predictedLanding`. D07 adds the separate generated `ClubCalibrationDispersionV1` for calibration/review surfaces that need `centerAlongM/centerCrossM`; the two generated types are never aliases.

- [ ] **Step 4: Run cross-language goldens**

Run:

```bash
uv run python tools/contracts/generate_contracts.py
uv run python -m unittest tests.test_guidance_contract tests.test_contract_codegen -v
swift test --filter GuidanceContractTests
cd web_v2 && npm test -- --run src/contracts/generated.test.ts
```

Expected: PASS; all three languages accept the same current-shot Guidance goldens and reject target/landing swaps, unknown keys, non-finite values, invalid covariance and any `expectedStrokes`、`averageStrokes` or probability field in `GuidanceEnvelopeV1`. This test does not ban the separately generated private player-model resource consumed by D07a/D08b or D08a's exact combination-level `averageStrokes` field in `CaddiePlanV1`.

- [ ] **Step 5: Commit the final Guidance contract**

```bash
git add contracts/canonical/guidance_v1.schema.json contracts/canonical/fixtures/guidance/current_shot_available.json contracts/canonical/fixtures/guidance/current_shot_unavailable.json contracts/canonical/canonical_object_registry.json contracts/canonical/reason_codes.json tools/contracts/generate_contracts.py ai_caddie/contracts/generated.py mobile/ios/AICaddieDomain/GeneratedContracts.swift web_v2/src/contracts/generated.ts tests/test_guidance_contract.py tests/test_contract_codegen.py mobile/ios/AICaddieDomainTests/GuidanceContractTests.swift web_v2/src/contracts/generated.test.ts
git commit -m "feat: freeze final guidance contract"
```

## Task D02a: Enforce generated-code and source-boundary ownership

**Depends on:** D02.

**Files:**
- Create: `tests/test_guidance_source_boundaries.py`
- Modify: `tests/test_contract_codegen.py`
- Modify: `mobile/ios/AICaddieDomainTests/GuidanceContractTests.swift`
- Modify: `web_v2/src/contracts/generated.test.ts`

- [ ] **Step 1: Add failing source-boundary scans**

The scans fail if production source contains a hand-written Guidance wire decoder, uses `roundFactsVersion`/`RoundFactsVersion` as capability authority or as a substitute for the relevant `GuidanceInput/v1` hash, invents a `GuidanceInputVersion/v1` domain, accepts caller-provided `accepted` or `available` authority, exposes a target-only map geometry, serializes probability or any `expectedStrokes` field into Guidance/Caddie/API/UI output, or renders `averageStrokes` outside full iOS/Watch Caddie detail. Track A generated `RoundFactsVersion` types, canonical projection/audit code, D07a's exact internal player-model resource, stochastic planner internals, D08a's generated nullable combination field, `CaddieDetailView.swift`、`WatchCaddieDetailView.swift` and explicitly named negative-test fixtures are allowlisted. Deleting the authority-required type、leaking a recovery-state value directly、showing AVG on Hole Root/Web or populating it in route-utility/uncalibrated mode is a test failure.

- [ ] **Step 2: Add exact canonicalization parity tests**

Python, Swift and TypeScript must produce identical canonical bytes and typed IDs for the available/unavailable goldens. Reordered set-like arrays normalize before identity construction; order-sensitive plan legs do not. Duplicate JSON keys are rejected before decode in all three runtimes.

- [ ] **Step 3: Run the ownership suite**

Run:

```bash
uv run python -m unittest tests.test_guidance_source_boundaries tests.test_contract_codegen -v
swift test --filter GuidanceContractTests
cd web_v2 && npm test -- --run src/contracts/generated.test.ts
```

Expected: PASS and no second Guidance DTO/codegen path exists.

- [ ] **Step 4: Commit the contract ownership gates**

```bash
git add tests/test_guidance_source_boundaries.py tests/test_contract_codegen.py mobile/ios/AICaddieDomainTests/GuidanceContractTests.swift web_v2/src/contracts/generated.test.ts
git commit -m "test: enforce guidance contract ownership"
```

## Task D02b: Verify the role-aware static asset chain without choosing authority

**Depends on:** Plan 2 canonical `CourseStaticAuthorityBundle/v1`, snapshot/manifest schemas, opaque-asset rows and encrypted CAS. D02b is a pure verifier over already selected exact authority; D02c owns round/device/control selection.

**Files:**
- Create: `contracts/canonical/static_guidance_capability_authority_v1.schema.json`
- Create: `contracts/canonical/fixtures/guidance/static_guidance_capability_authority.json`
- Modify: `contracts/canonical/canonical_object_registry.json`
- Modify: `tools/contracts/generate_contracts.py`
- Regenerate: `ai_caddie/contracts/generated.py`
- Regenerate: `mobile/ios/AICaddieDomain/GeneratedContracts.swift`
- Regenerate: `web_v2/src/contracts/generated.ts`
- Create: `ai_caddie/guidance/capability_adapter.py`
- Create: `server_v2/guidance_capability_repo.py`
- Create: `tests/guidance_capability_fixtures.py`
- Create: `tests/test_guidance_capability_adapter.py`
- Create: `tests/test_guidance_map_asset_roles.py`
- Modify: `tests/test_contract_codegen.py`
- Modify: `mobile/ios/AICaddieDomainTests/GuidanceContractTests.swift`
- Modify: `web_v2/src/contracts/generated.test.ts`

- [ ] **Step 1: Write failing two-layer identity and map-role tests**

Cover all of the following:

- snapshot exact logical `assetBindings[{capability,subjectRef,role,assetHash}]` resolves into physical `assetBlobs[]`;
- manifest exact logical groups `{capability,subjectRef,role,assetRefs[]}` resolve into top-level physical `assets[]`;
- each physical ref agrees with opaque row, encrypted CAS bytes, SHA-256, byte domain, size, media type and schema;
- the same physical blob may be shared by two logical bindings without collapsing their capability/subject/role/quality identity;
- role relabel, subject relabel, missing role, duplicated logical key, unreferenced required asset, manifest/snapshot mismatch, CAS tamper and same-SHA/different-quality swaps fail closed;
- Map requires exactly one selected `map.geometry`, `map.transform` and `map.image` for the same subject. Hole 8 geometry/transform/image cannot be substituted into Hole 7 even when every SHA is installed.

The accepted map fixture uses subject `hole:{layoutRevisionId}:{holeGlobalId}`; never `hole + 1` or a mutable local path.

- [ ] **Step 2: Implement a verifier-only role-aware value**

```python
# ai_caddie/guidance/capability_adapter.py
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


class CapabilityVerificationError(ValueError):
    pass


_VERIFIED_MARKER = object()


@dataclass(frozen=True)
class VerifiedGuidanceAsset:
    role: str
    logical_binding_hash: str
    sha256: str
    byte_domain: str
    size: int
    media_type: str
    schema: str
    manifest_requirement: str


@dataclass(frozen=True, init=False)
class VerifiedGuidanceCapability:
    capability_name: str
    capability_id: str
    subject_ref: str
    snapshot_id: str
    quality_report_id: str
    static_course_authority_hash: str
    static_capability_authority_hash: str
    assets: tuple[VerifiedGuidanceAsset, ...]
    product_role: str
    product_body_hash: str
    body: Mapping[str, object]
    evidence_refs: tuple[str, ...]

    def __init__(self, marker: object, *, values: Mapping[str, object]) -> None:
        if marker is not _VERIFIED_MARKER:
            raise TypeError("VerifiedGuidanceCapability is verifier-only")
        for field in self.__dataclass_fields__:
            object.__setattr__(self, field, values[field])
```

The minting function is module-private, recursively freezes decoded bodies and accepts only a `VerifiedCourseStaticAuthority` plus exact `capability_name/subject_ref/product_role`. It performs no database “latest” lookup, reads no round facts and accepts no Boolean availability.

`static_capability_authority_hash = typed_id("StaticGuidanceCapabilityAuthority/v1", static_capability_payload)` binds static-course authority, capability ID/name, subject, quality report, sorted role-aware logical/physical asset identities and selected product role/body hash. D02b creates an exact schema and registry entry before this call exists: `includedFields` is exactly `staticCourseAuthorityHash,capability,capabilityId,subjectRef,qualityReportId,assets,productRole,productBodyHash`, `excludedFields=[]`, and every asset row has the exact fields shown below. The shared golden is hashed in Python/Swift/TypeScript; mutating any logical role/subject/quality/physical descriptor/product hash changes the ID, while an unregistered domain or extra field fails before hashing. It excludes GPS, score, shots, flag, reducer checkpoint, sync cursor and dynamic controls by schema, not by a caller-selected dictionary.

- [ ] **Step 3: Freeze the exact Map product trio**

`map.geometry` canonical body:

```json
{
  "schema": "ai-caddie-map-body-v1",
  "routePoints": [
    {
      "targetRef": "tee",
      "latitude": 22.279,
      "longitude": 114.162,
      "distanceFromTeeM": 0.0,
      "remainingDistanceToGreenM": 380.0
    }
  ]
}
```

Its root keys and every row key are exact. Rows sort by `(distanceFromTeeM,targetRef)`; target refs are unique; Tee is exactly `(0,total)`; Green is exactly `(total,0)`; every row satisfies `abs(distanceFromTeeM + remainingDistanceToGreenM - total) <= 0.5 m`. Static map contains no current-ball distance or elevation.

`map.transform` canonical body has exact keys only:

```json
{
  "schema": "ai-caddie-map-transform-v1",
  "layoutRevisionId": "layout-r1",
  "holeGlobalId": "gid-hole-7",
  "subjectRef": "hole:layout-r1:gid-hole-7",
  "baseImageHash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "geometryHash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "matrix": [1.0, 0.0, 0.0, -1.0, 120.0, 300.0]
}
```

`baseImageHash` and `geometryHash` must resolve to the selected same-subject `map.image` and `map.geometry`. The six finite matrix values are `[a,b,c,d,tx,ty]`. The unique Tee route point is the WGS84 origin for deterministic ECEF→ENU conversion; projection is `pixelX=a*eastM+b*northM+tx`, `pixelY=c*eastM+d*northM+ty`, with top-left image origin and pixel-center coordinates. The 2×2 determinant must be finite/non-zero. Intrinsic width/height come only from decoding the selected image header; `imageWidthPx/imageHeightPx/pixelsPerMeter/routeSamples` are forbidden in transform. Registered geometry samples must lie inside `[0,width) × [0,height)` and meet the signed residual gate.

- [ ] **Step 4: Implement the pure asset-chain API**

```text
verify_static_guidance_capability(
  authority: VerifiedCourseStaticAuthority,
  capability_name: str,
  expected_subject_ref: str,
  product_role: str
) -> VerifiedGuidanceCapability
```

Selection order is logical binding → manifest role group → physical assets → opaque rows/CAS → exact product schema. Never choose “the first SHA” or use a content hash as the logical key. Required role sets are capability policy, not caller input: Map uses the trio above; PlaysLike uses `playsLike.model|playsLike.elevation`; playable regions use `guidance.playable-regions`.

- [ ] **Step 5: Run role, shared-blob and transform suites**

Run:

```bash
uv run python tools/contracts/generate_contracts.py
uv run python -m unittest \
  tests.test_contract_codegen \
  tests.test_guidance_capability_adapter tests.test_guidance_map_asset_roles \
  tests.test_course_snapshot_repo tests.test_course_quality_gate -v
swift test --filter GuidanceContractTests
npm --prefix web_v2 test -- --run src/contracts/generated.test.ts
```

Expected: PASS in Python、Swift and Web; the canonical-contracts source digest and all three generated outputs are byte-current in this checkpoint, and all three languages hash the same static-capability golden. Shared physical bytes remain legal, but role/subject/quality/cross-hole swaps and malformed map geometry/transform fail before any UI decoder.

- [ ] **Step 6: Commit static asset verification**

```bash
git add contracts/canonical/static_guidance_capability_authority_v1.schema.json contracts/canonical/fixtures/guidance/static_guidance_capability_authority.json contracts/canonical/canonical_object_registry.json tools/contracts/generate_contracts.py ai_caddie/contracts/generated.py mobile/ios/AICaddieDomain/GeneratedContracts.swift web_v2/src/contracts/generated.ts ai_caddie/guidance/capability_adapter.py server_v2/guidance_capability_repo.py tests/guidance_capability_fixtures.py tests/test_guidance_capability_adapter.py tests/test_guidance_map_asset_roles.py tests/test_contract_codegen.py mobile/ios/AICaddieDomainTests/GuidanceContractTests.swift web_v2/src/contracts/generated.test.ts
git commit -m "feat: verify role aware guidance assets"
```

## Task D02c: Normalize capability authority to exact device pins, controls, and offline static identity

**Finalizes:** D02b's pure role-aware static verifier by selecting the exact current-device round pin and latest signed control. After this task no production Guidance source may contain `_latest_install`、`initiating_install_binding_json`、`accepted_at.desc()`、facts-bound capability identity or caller-provided availability. D03–D15 consume only the final types below.

**Depends on:** Plan 2 `CourseStaticAuthorityBundle/v1`; `CourseRoundDevicePinRepo.require_active_runtime_pin(...)`; `CourseControlRepo.project_verified_effective_control(...)`; `ActiveRoundSourceMembership`、`VerifiedActiveCourseRoundPin`、`ActiveRuntimePinReason`、`ActiveRuntimePinUnavailable`、`VerifiedEffectiveCourseControl`、`VerifiedCourseStaticAuthority`; local `VerifiedInstalledCourseAuthority`、`DurableActiveRoundPin`、`VerifiedActiveRoundCourseAuthority`、optional `RoundPinAuthorityAttestation` and `LocalVerifiedEffectiveCourseControl`; logical map roles `map.geometry|map.transform|map.image`. `LocalRoundInstallPin` remains an internal durable-store payload and is never a Track D consumer authority.

**Files:**
- Modify: `contracts/canonical/reason_codes.json`
- Regenerate: `ai_caddie/contracts/generated.py`、`mobile/ios/AICaddieDomain/GeneratedContracts.swift`、`web_v2/src/contracts/generated.ts`
- Modify: `ai_caddie/guidance/capability_adapter.py`
- Replace authority selection in: `server_v2/guidance_capability_repo.py`
- Modify: `tests/guidance_capability_fixtures.py`
- Replace/extend: `tests/test_guidance_capability_adapter.py`
- Create: `tests/test_guidance_effective_control.py`
- Create: `tests/test_guidance_authority_source_boundary.py`
- Modify: `tests/test_contract_codegen.py`

- [ ] **Step 1: Write failing current-device, exact-ACK, merged-round, overlay, and source-boundary tests**

```python
# tests/test_guidance_effective_control.py
from __future__ import annotations

from pathlib import Path
import unittest

from ai_caddie.guidance.capability_adapter import CapabilityVerificationError
from server_v2.account_context import AccountContext
from tests.guidance_capability_fixtures import GuidanceCapabilityFixture


class GuidanceEffectiveControlTests(unittest.TestCase):
    def account(self, fixture: GuidanceCapabilityFixture, device: str) -> AccountContext:
        return AccountContext.create(
            account_principal=fixture.verified_account_principal(
                player_id="player-guidance",
                session_id=f"session-{device}",
            ),
            device_principal=fixture.verified_device_principal(
                device_id=device,
                player_id="player-guidance",
            ),
        )

    def test_watch_start_then_ios_join_uses_ios_pin_not_initiating_binding(self) -> None:
        fixture = GuidanceCapabilityFixture.create(initiating_device_id="watch-1")
        self.addCleanup(fixture.close)
        fixture.install_and_pin_device("iphone-1", profile_id="ios-v1")
        value = fixture.verify(account=self.account(fixture, "iphone-1"))
        self.assertEqual(value.device_id, "iphone-1")
        self.assertEqual(value.profile_id, "ios-v1")
        self.assertNotEqual(value.install_ack_id, fixture.initiating_install_ack_id)

    def test_ios_start_then_watch_join_uses_watch_pin(self) -> None:
        fixture = GuidanceCapabilityFixture.create(initiating_device_id="iphone-1")
        self.addCleanup(fixture.close)
        fixture.install_and_pin_device("watch-1", profile_id="watch-v1")
        value = fixture.verify(account=self.account(fixture, "watch-1"))
        self.assertEqual(value.device_id, "watch-1")
        self.assertEqual(value.profile_id, "watch-v1")

    def test_unpinned_prepared_ack_released_pin_and_reinstall_fail_closed(self) -> None:
        fixture = GuidanceCapabilityFixture.create()
        self.addCleanup(fixture.close)
        for device, mutation, reason in (
            ("iphone-unpinned", None, "active_course_round_pin_missing"),
            ("iphone-prepared", "prepared", "active_course_round_pin_unverified"),
            ("iphone-released", "released", "active_course_round_pin_released"),
        ):
            with self.subTest(device=device):
                if mutation is not None:
                    fixture.install_and_pin_device(device, ack_state=mutation)
                with self.assertRaisesRegex(CapabilityVerificationError, reason):
                    fixture.verify(account=self.account(fixture, device))
        original = fixture.verify()
        fixture.reinstall_same_manifest_for_device(
            original.device_id,
            release_original_pin=True,
        )
        with self.assertRaisesRegex(
            CapabilityVerificationError,
            "active_course_round_pin_released",
        ):
            fixture.verify()

    def test_selected_member_pin_must_match_its_source_snapshot_and_semantic_binding(self) -> None:
        for change in ("snapshot", "semantic"):
            fixture = GuidanceCapabilityFixture.create()
            self.addCleanup(fixture.close)
            fixture.add_merged_source("inc-guidance-2")
            fixture.replace_selected_member_binding(field=change)
            with self.subTest(change=change), self.assertRaisesRegex(
                CapabilityVerificationError,
                "active_course_round_pin_binding_mismatch",
            ):
                fixture.verify()

    def test_invalid_authoritative_source_roster_maps_without_parsing_repo_text(self) -> None:
        fixture = GuidanceCapabilityFixture.create()
        self.addCleanup(fixture.close)
        with self.assertRaisesRegex(
            CapabilityVerificationError,
            "active_round_source_binding_mismatch",
        ):
            fixture.verify(source_order=(
                fixture.round_incarnation_id,
                fixture.round_incarnation_id,
            ))

    def test_merged_frozen_order_with_one_member_pin_is_sufficient(self) -> None:
        fixture = GuidanceCapabilityFixture.create()
        self.addCleanup(fixture.close)
        fixture.add_merged_source("inc-guidance-2")
        fixture.add_merged_source("inc-guidance-3")
        value = fixture.verify(source_order=(fixture.round_incarnation_id, "inc-guidance-2", "inc-guidance-3"))
        self.assertEqual(
            value.round_incarnation_ids,
            (fixture.round_incarnation_id, "inc-guidance-2", "inc-guidance-3"),
        )
        fixture.add_second_member_pin_for_same_device("inc-guidance-2")
        with self.assertRaisesRegex(
            CapabilityVerificationError,
            "active_course_round_pin_ambiguous",
        ):
            fixture.verify()

    def test_control_overlay_uses_exact_enable_flags_and_old_policy_cannot_reenable(self) -> None:
        fixture = GuidanceCapabilityFixture.create()
        self.addCleanup(fixture.close)
        cases = (
            ({"grantExpired": True, "activeRoundContinuation": False}, "course_active_round_continuation_blocked", "map"),
            ({"disableMap": True}, "course_map_disabled", "map"),
            ({"disableGuidance": True}, "course_guidance_disabled", "playsLike"),
            ({"purged": True}, "course_active_round_continuation_blocked", "map"),
            ({"rights": "revoked"}, "course_active_round_continuation_blocked", "map"),
            ({"runtimeState": "quarantined"}, "course_active_round_continuation_blocked", "map"),
        )
        for changes, reason, capability in cases:
            with self.subTest(reason=reason):
                fixture.set_latest_control(**changes)
                with self.assertRaisesRegex(CapabilityVerificationError, reason):
                    fixture.verify(capability_name=capability)
                fixture.replay_older_allow_policy()
                with self.assertRaisesRegex(CapabilityVerificationError, reason):
                    fixture.verify(capability_name=capability)
                fixture.restore_allowed_control()

    def test_score_fact_does_not_change_static_capability_authority(self) -> None:
        fixture = GuidanceCapabilityFixture.create()
        self.addCleanup(fixture.close)
        before = fixture.verify()
        fixture.append_score_only_fact()
        after = fixture.verify()
        self.assertEqual(
            before.static_capability_authority_hash,
            after.static_capability_authority_hash,
        )
        self.assertEqual(before.product_body_hash, after.product_body_hash)


class GuidanceAuthoritySourceBoundaryTests(unittest.TestCase):
    def test_guidance_repo_has_no_latest_or_initiating_install_authority(self) -> None:
        source = Path("server_v2/guidance_capability_repo.py").read_text()
        for forbidden in (
            "_latest_install", "initiating_install_binding_json",
            "accepted_at.desc", "factsVersion\": round_facts_version",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the authority tests and verify they fail**

Run:

```bash
uv run python -m unittest \
  tests.test_guidance_capability_adapter \
  tests.test_guidance_effective_control \
  tests.test_guidance_authority_source_boundary -v
```

Expected: FAIL because the pure D02b verifier deliberately does not choose a round/device pin or project latest effective control.

- [ ] **Step 3: Replace the verifier-only value with the final static/effective split**

```python
# ai_caddie/guidance/capability_adapter.py — replace D02b value
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


class CapabilityVerificationError(ValueError):
    pass


_VERIFIED_MARKER = object()


@dataclass(frozen=True)
class VerifiedGuidanceAsset:
    role: str
    logical_binding_hash: str
    sha256: str
    byte_domain: str
    size: int
    media_type: str
    schema: str
    manifest_requirement: str


@dataclass(frozen=True, init=False)
class VerifiedGuidanceCapability:
    owner_account_id: str
    round_id: str
    round_incarnation_ids: tuple[str, ...]
    semantic_binding_hash: str
    active_source_ordinal: int
    active_source_round_id: str
    active_pin_event_identity: str
    active_pin_event_hash: str
    active_pin_generation: int
    device_id: str
    credential_id: str
    profile_id: str
    security_domain_id: str
    install_manifest_id: str
    install_ack_id: str
    install_instance_id: str
    install_ack_generation: int
    capability_name: str
    capability_id: str
    subject_ref: str
    snapshot_id: str
    quality_report_id: str
    static_course_authority_hash: str
    static_capability_authority_hash: str
    effective_control_hash: str
    assets: tuple[VerifiedGuidanceAsset, ...]
    product_role: str
    product_body_hash: str
    body: Mapping[str, object]
    evidence_refs: tuple[str, ...]

    def __init__(self, marker: object, *, values: Mapping[str, object]) -> None:
        if marker is not _VERIFIED_MARKER:
            raise TypeError("VerifiedGuidanceCapability is verifier-only")
        for field in self.__dataclass_fields__:
            object.__setattr__(self, field, values[field])


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    return value


def _mint_verified_guidance_capability(
    values: Mapping[str, object],
) -> VerifiedGuidanceCapability:
    frozen = {key: _freeze(value) for key, value in values.items()}
    if not isinstance(frozen["body"], Mapping):
        raise CapabilityVerificationError("capability body must be an object")
    return VerifiedGuidanceCapability(_VERIFIED_MARKER, values=frozen)
```

`static_course_authority_hash` is Plan 2's signed `CourseStaticAuthorityBundle/v1` identity. `static_capability_authority_hash` is Track D's typed ID over capability/subject/quality plus the canonical sorted role-aware logical/physical asset bindings and product-body hash. Neither contains score, shot, flag, GPS, reducer checkpoint or replication state. `effective_control_hash` is a separate current overlay identity and may change when a later signed grant/safety/purge/trusted-time control arrives.

- [ ] **Step 4: Replace round/install selection with exact current-device authority**

```python
# server_v2/guidance_capability_repo.py — final authority helpers
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from ai_caddie.guidance.capability_adapter import CapabilityVerificationError
from server_v2.course_control_repo import (
    CourseControlProjectionUnavailable,
    CourseControlRepo,
    VerifiedEffectiveCourseControl,
)
from server_v2.course_repo import (
    ActiveRuntimePinReason,
    ActiveRuntimePinUnavailable,
    ActiveRoundSourceMembership,
    CourseRoundDevicePinRepo,
    VerifiedActiveCourseRoundPin,
)
from server_v2.device_credential import VerifiedDevicePrincipal


@dataclass(frozen=True)
class VerifiedGuidanceRoundAuthority:
    active_sources: tuple[ActiveRoundSourceMembership, ...]
    active_pin: VerifiedActiveCourseRoundPin
    effective_control: VerifiedEffectiveCourseControl


def verify_guidance_round_authority(
    session: Session,
    *,
    principal: VerifiedDevicePrincipal,
    canonical_round_id: str,
    active_sources: tuple[ActiveRoundSourceMembership, ...],
    at: datetime,
) -> VerifiedGuidanceRoundAuthority:
    if len({
        (row.snapshot_id, row.semantic_binding_hash) for row in active_sources
    }) != 1:
        raise CapabilityVerificationError("active_round_source_binding_mismatch")
    try:
        active_pin = CourseRoundDevicePinRepo(session).require_active_runtime_pin(
            principal=principal,
            canonical_round_id=canonical_round_id,
            active_sources=active_sources,
        )
        binding = active_pin.binding
        control = CourseControlRepo(session).project_verified_effective_control(
            account_id=principal.account_id,
            security_domain_id=binding.security_domain_id,
            snapshot_id=binding.snapshot_id,
            install_manifest_id=binding.install_manifest_id,
            active_round=True,
            at=at,
        )
    except ActiveRuntimePinUnavailable as error:
        reason_codes = {
            ActiveRuntimePinReason.INVALID_SOURCE_ROSTER:
                "active_round_source_binding_mismatch",
            ActiveRuntimePinReason.MISSING:
                "active_course_round_pin_missing",
            ActiveRuntimePinReason.UNVERIFIED:
                "active_course_round_pin_unverified",
            ActiveRuntimePinReason.RELEASED:
                "active_course_round_pin_released",
            ActiveRuntimePinReason.AMBIGUOUS:
                "active_course_round_pin_ambiguous",
            ActiveRuntimePinReason.BINDING_MISMATCH:
                "active_course_round_pin_binding_mismatch",
        }
        if set(reason_codes) != set(ActiveRuntimePinReason):
            raise RuntimeError("ActiveRuntimePinReason mapping is incomplete")
        raise CapabilityVerificationError(reason_codes[error.reason]) from error
    except CourseControlProjectionUnavailable as error:
        raise CapabilityVerificationError(
            "course_active_round_continuation_blocked"
        ) from error
    if (
        active_pin.canonical_round_id != canonical_round_id
        or binding.account_id != principal.account_id
        or binding.device_id != principal.device_id
        or binding.credential_id != principal.credential_id
        or binding.snapshot_id != active_pin.source.snapshot_id
        or binding.semantic_binding_hash != active_pin.source.semantic_binding_hash
        or control.account_id != principal.account_id
        or control.security_domain_id != binding.security_domain_id
        or control.snapshot_id != binding.snapshot_id
        or control.install_manifest_id != binding.install_manifest_id
    ):
        raise CapabilityVerificationError("active_course_round_pin_binding_mismatch")
    return VerifiedGuidanceRoundAuthority(
        active_sources=active_sources,
        active_pin=active_pin,
        effective_control=control,
    )


def require_capability_allowed(
    control: VerifiedEffectiveCourseControl,
    capability_name: str,
) -> None:
    if not control.can_continue_active_round:
        raise CapabilityVerificationError("course_active_round_continuation_blocked")
    if capability_name == "map" and not control.map_enabled:
        raise CapabilityVerificationError("course_map_disabled")
    if capability_name != "map" and not control.guidance_enabled:
        raise CapabilityVerificationError("course_guidance_disabled")
```

Append exactly these stable Track D absence/error codes to the generated reason-code registry: `active_course_round_pin_missing`、`active_course_round_pin_unverified`、`active_course_round_pin_released`、`active_course_round_pin_ambiguous`、`active_course_round_pin_binding_mismatch`、`active_round_source_binding_mismatch`、`course_active_round_continuation_blocked`、`course_map_disabled`、`course_guidance_disabled`. Plan 2's `ActiveRuntimePinUnavailable.reason` is mapped once by the exhaustive enum switch above；an unmapped future enum member is a source/build failure rather than a generic fallback. UI and audit tokens never expose SQL row names or infer a dominant underlying policy reason that Plan 2's projection does not carry.

The production `verify_guidance_capability(...)` receives the authenticated `VerifiedDevicePrincipal` and the authoritative canonical/merge projection's exact ordered `ActiveRoundSourceMembership` tuple. It calls `verify_guidance_round_authority()` once in the same transaction, calls `require_capability_allowed()`, obtains the exact `VerifiedCourseStaticAuthority` bound to `authority.active_pin.binding`'s manifest/ACK/static-authority hash, then invokes D02b's pure manifest/snapshot/quality/CAS verifier—not any later matching install. A merged round requires one and only one active pin for the current device whose source membership belongs to the active roster；it does **not** require the device to pin every merged source. Profile/manifest are device-local identities, while selected membership snapshot/semantic binding must match exactly. `initiating_install_binding_json` is audit-only and never participates in selection.

Mint `VerifiedGuidanceCapability` from that one verified value only：`round_id=active_pin.canonical_round_id`；`round_incarnation_ids` is the ordered membership tuple；the common `semantic_binding_hash` is proven before selection；`active_source_*` comes from `active_pin.source`；`active_pin_event_identity/event_hash/generation`、device/credential/profile/security-domain/manifest/ACK/install-instance/install-ACK-generation come from `active_pin.binding`；`effective_control_hash` comes from the separately reprojected latest control. No field is read from an initiating branch JSON, recency query or caller Boolean.

The asset block is normalized from one row to a sorted tuple. Snapshot logical bindings are exact `{capability,subjectRef,role,assetHash}`; manifest groups carry the same role and `assetRefs[]`; each referenced `assetBlob`/top-level manifest asset/opaque row/CAS byte tuple must agree. Required map roles are `map.geometry`、`map.transform` and `map.image`; other capability product roles are declared by Plan 2's static-authority binding. Select the JSON product body only by exact role+schema, not “first SHA”. Compute:

```python
product_body_hash = hashlib.sha256(raw_body).hexdigest()
static_capability_authority_hash = typed_id(
    "StaticGuidanceCapabilityAuthority/v1",
    {
        "staticCourseAuthorityHash": static_authority.static_authority_hash,
        "capability": capability_name,
        "capabilityId": capability_id,
        "subjectRef": expected_subject_ref,
        "qualityReportId": report.id,
        "assets": [
            {
                "role": asset.role,
                "logicalBindingHash": asset.logical_binding_hash,
                "sha256": asset.sha256,
                "byteDomain": asset.byte_domain,
                "size": asset.size,
                "mediaType": asset.media_type,
                "schema": asset.schema,
                "manifestRequirement": asset.manifest_requirement,
            }
            for asset in assets
        ],
        "productRole": product_role,
        "productBodyHash": product_body_hash,
    },
)
```

`map.transform` canonical JSON must have exact subject/layout bindings and hashes: `layoutRevisionId`、`holeGlobalId`、`subjectRef`、`baseImageHash`、`geometryHash`; both hashes must resolve to the selected `map.image`/`map.geometry` assets. A Hole 8 transform/image passed to Hole 7 fails before UI decode even if every physical SHA is installed.

- [ ] **Step 5: Update the shared fixture to seed prepared/verified ACKs, per-device pins, roles, and controls**

The fixture uses Plan 2 production repositories and exact install sequencing: client generates `installInstanceId` before the manifest request; server reserves the exact ACK row as `prepared`; the signed bundle binds that `installAckId/installInstanceId/installGeneration`; client atomically commits bytes, then the same row transitions `prepared → verified`; a lost response retries the same identity instead of creating a newer row. It persists the Plan 2 `CourseRoundDevicePinRow` and publishes signed grant/channel/safety/purge/trusted-time controls. `accepted_at` must be at or after `verifiedAt`; no fixture query chooses by recency. Local offline start may use the locally committed signed prepared bundle as D08b specifies, but server round-start/pin authority accepts only the verified ACK and online sync flushes the ACK transition before queued `round_started`. `install_and_pin_device()` creates an independent profile/manifest/ACK authority for the joining device. Merged fixtures freeze the full `ActiveRoundSourceMembership` roster but seed exactly one valid member pin for the authenticated device；zero、two or a non-member pin fail closed, while unpinned peer sources are legal.

For a map fixture, seed three role-aware bindings and make the transform body exact:

```python
{
    "schema": "ai-caddie-map-transform-v1",
    "layoutRevisionId": "layout-r1",
    "holeGlobalId": "gid-hole-7",
    "subjectRef": "hole:layout-r1:gid-hole-7",
    "baseImageHash": image_ref.sha256,
    "geometryHash": geometry_ref.sha256,
    "matrix": [1.0, 0.0, 0.0, -1.0, 120.0, 300.0],
}
```

The fixture decodes intrinsic image dimensions from the `map.image` bytes and uses the unique Tee in `map.geometry` as the ENU origin. Add mutations for non-invertible matrix, duplicated/missing Tee, geometry/image hash swap, cross-hole subject swap, undecodable image header and registered points outside the image bounds.

- [ ] **Step 6: Run the full authority suite**

Run:

```bash
uv run python tools/contracts/generate_contracts.py
uv run python -m unittest \
  tests.test_contract_codegen \
  tests.test_round_start_binding_authority \
  tests.test_guidance_capability_adapter \
  tests.test_guidance_effective_control \
  tests.test_guidance_authority_source_boundary \
  tests.test_course_snapshot_repo \
  tests.test_course_quality_gate -v
```

Expected: PASS; reason-code changes regenerate a byte-current canonical-contracts source digest and all three language outputs in this checkpoint；Watch→iOS and iOS→Watch joining use the authenticated device's exact active member pin; prepared/released/missing、non-member and multiple member pins fail closed；one valid member pin remains sufficient while the complete merged roster stays in its frozen `sourceOrdinal` order；selected membership snapshot/semantic, profile/manifest/security-domain disagreement fails; higher-generation safety/purge/grant state dominates through `can_continue_active_round/map_enabled/guidance_enabled`; score facts do not change static authority; map role or cross-hole swaps fail.

- [ ] **Step 7: Commit the normalized authority boundary**

```bash
git add contracts/canonical/reason_codes.json ai_caddie/contracts/generated.py mobile/ios/AICaddieDomain/GeneratedContracts.swift web_v2/src/contracts/generated.ts ai_caddie/guidance/capability_adapter.py server_v2/guidance_capability_repo.py tests/guidance_capability_fixtures.py tests/test_guidance_capability_adapter.py tests/test_guidance_effective_control.py tests/test_guidance_authority_source_boundary.py tests/test_contract_codegen.py
git commit -m "feat: bind guidance to device pins and static authority"
```

## Task D03: Implement verified-elevation-only PlaysLike

**Depends on:** D02c; Plan 2 has admitted a Plan 3 research candidate through its quality gate and published same-subject roles `playsLike.model` and `playsLike.elevation` into signed static authority. Plan 3 alone never promotes these roles. D03 freezes the pure elevation value/protocol used by the adjustment engine; D08c later implements the production promoted-product query without being a dependency of D03.

**Files:**
- Create: `ai_caddie/guidance/elevation_types.py`
- Create: `ai_caddie/guidance/playslike.py`
- Test: `tests/test_guidance_playslike.py`
- Modify: `tests/test_course_prep_playslike.py`
- Modify: `ai_caddie/courses/course_prep.py`
- Create: `server_v2/guidance.py`

- [ ] **Step 1: Write failing SI/sign/role/coverage tests**

Cover uphill/downhill sign, meter-only internal values, model-version allowlist, model/elevation same subject and map-geometry hash, current/aim interpolation coverage, anchor/residual thresholds, unknown vertical datum/CRS, missing one role and cross-hole role swap. Legacy request-time mesh/nearest-vertex output remains explicitly unavailable.

- [ ] **Step 2: Implement the pure adjustment engine**

```python
@dataclass(frozen=True)
class VerifiedPlaysLikeInput:
    model_capability: VerifiedGuidanceCapability
    elevation_pair: VerifiedElevationPair
    base_horizontal_distance_m: float


@dataclass(frozen=True)
class PlaysLikeResult:
    available: bool
    reason_code: str | None
    base_horizontal_distance_m: float | None
    elevation_delta_m: float | None
    adjustment_m: float | None
    distance_m: float | None
    engine_version: str
    evidence_refs: tuple[str, ...]


```

`elevation_types.py` defines immutable `VerifiedElevationSample`、`VerifiedElevationPair` and a `PlaysLikeElevationProvider` protocol with exact subject/layout/hole/map/product hashes, current/target elevations, anchor distances, interpolation residuals and evidence refs. Constructors are strict value validation only; fixture tests build them from checked values, while D08c's production provider is the sole code that may mint them from installed promoted bytes. The adjustment engine accepts only D02b-minted `playsLike.model` and this `VerifiedElevationPair` from `playsLike.elevation`. It verifies finite SI values, matching subject/map hash/product identities and quality limits, then computes `delta = targetElevationM - currentElevationM` and the approved model adjustment. It exposes no wind, air-density or raw mesh path. Unit conversion happens once at presentation.

- [ ] **Step 3: Quarantine legacy course-prep output**

`course_prep._hole_playslike` returns `{available:false,reasonCode:playslike_elevation_not_promoted}`; file presence or nearest vertex can never enable the live layer. This task creates `server_v2/guidance.py` as the thin router/helper module with the PlaysLike audit projection only; D04/D05/D07 append their generated projections, D08a adds the authenticated current-shot route, and no earlier task may modify a not-yet-created router. Server audit maps only the exact two-role static authority and returns stable absence reasons unchanged.

- [ ] **Step 4: Run and commit**

Run:

```bash
uv run python -m unittest tests.test_guidance_playslike tests.test_elevation tests.test_course_prep_playslike -v
```

Expected: PASS; missing/cross-hole role, hull miss, residual failure and unapproved model all fail closed.

```bash
git add ai_caddie/guidance/elevation_types.py ai_caddie/guidance/playslike.py ai_caddie/courses/course_prep.py server_v2/guidance.py tests/test_guidance_playslike.py tests/test_course_prep_playslike.py
git commit -m "feat: add verified elevation PlaysLike"
```

## Task D04: Build promoted hazard guidance with deterministic semantics

**Depends on:** D02c; Plan 2 has accepted a Plan 3 `hazardGuidance` research candidate for the current hole/route binding and published the promoted product into signed static authority.

**Files:**
- Create: `ai_caddie/guidance/hazards.py`
- Test: `tests/test_hazard_guidance.py`
- Modify: `server_v2/guidance.py`
- Modify: `mobile/ios/AICaddie/Views/CurrentHoleView.swift:383-405`

- [ ] **Step 1: Write failing semantic, overlap, and ordering tests**

```python
# tests/test_hazard_guidance.py
from __future__ import annotations

import unittest

from ai_caddie.guidance.hazards import (
    LandingWindow,
    build_hazard_guidance,
)
from tests.guidance_capability_fixtures import verified_capability


class HazardGuidanceTests(unittest.TestCase):
    def hazards(self) -> list[dict[str, object]]:
        return [
            {"hazardRef": "hazard:water-b", "kind": "water", "enterDistanceM": 138.0, "clearDistanceM": 151.0, "evidenceRefs": ["quality:water-b:v4"]},
            {"hazardRef": "hazard:bunker-a", "kind": "bunker", "enterDistanceM": 132.0, "clearDistanceM": 144.0, "evidenceRefs": ["quality:bunker-a:v4"]},
            {"hazardRef": "hazard:forced-carry-c", "kind": "forced_carry", "enterDistanceM": 140.0, "clearDistanceM": 160.0, "evidenceRefs": ["quality:forced-carry-c:v4"]},
        ]

    def capability(self, hazards: list[dict[str, object]] | None = None):
        return verified_capability(
            "hazardGuidance",
            {
                "schema": "ai-caddie-hazardGuidance-body-v1",
                "routeGeometryHash": "f" * 64,
                "stationingBasis": "tee-origin-route-station-v1",
                "hazards": self.hazards() if hazards is None else hazards,
            },
        )

    def test_clear_distance_is_not_replaced_by_enter_distance(self) -> None:
        result = build_hazard_guidance(
            capability=self.capability(),
            current_route_station_m=0.0,
            landing_window=LandingWindow(start_m=130.0, end_m=155.0),
        )
        water = next(item for item in result.items if item.hazard_ref == "hazard:water-b")
        self.assertEqual(water.enter_distance_m, 138.0)
        self.assertEqual(water.clear_distance_m, 151.0)

    def test_non_overlapping_hazard_is_not_current_shot_guidance(self) -> None:
        result = build_hazard_guidance(
            capability=self.capability(),
            current_route_station_m=0.0,
            landing_window=LandingWindow(start_m=90.0, end_m=110.0),
        )
        self.assertEqual(result.items, ())

    def test_second_shot_converts_absolute_station_to_ball_relative_distance(self) -> None:
        result = build_hazard_guidance(
            capability=self.capability(),
            current_route_station_m=100.0,
            landing_window=LandingWindow(start_m=30.0, end_m=60.0),
        )
        water = next(item for item in result.items if item.hazard_ref == "hazard:water-b")
        self.assertEqual(water.enter_distance_m, 38.0)
        self.assertEqual(water.clear_distance_m, 51.0)

    def test_canonical_body_order_is_preserved(self) -> None:
        expected = ("hazard:bunker-a", "hazard:water-b", "hazard:forced-carry-c")
        result = build_hazard_guidance(
            capability=self.capability(sorted(
                self.hazards(), key=lambda row: str(row["hazardRef"])
            )),
            current_route_station_m=0.0,
            landing_window=LandingWindow(start_m=130.0, end_m=155.0),
        )
        self.assertEqual(tuple(item.hazard_ref for item in result.items), expected)

    def test_unsorted_or_duplicate_hazard_rows_fail_closed(self) -> None:
        for rows in (
            list(reversed(sorted(self.hazards(), key=lambda row: str(row["hazardRef"])))),
            [self.hazards()[0], self.hazards()[0]],
        ):
            with self.subTest(rows=rows):
                result = build_hazard_guidance(
                    capability=self.capability(rows),
                    current_route_station_m=0.0,
                    landing_window=LandingWindow(start_m=130.0, end_m=155.0),
                )
                self.assertFalse(result.available)

    def test_forced_carry_survives_promoted_body_to_guidance_wire(self) -> None:
        result = build_hazard_guidance(
            capability=self.capability(),
            current_route_station_m=0.0,
            landing_window=LandingWindow(start_m=130.0, end_m=165.0),
        )
        forced = next(item for item in result.items if item.kind == "forced_carry")
        self.assertEqual(forced.hazard_ref, "hazard:forced-carry-c")
        self.assertEqual(forced.clear_distance_m, 160.0)

    def test_accepted_empty_hazard_set_is_available_and_evidence_bound(self) -> None:
        capability = self.capability([])
        result = build_hazard_guidance(
            capability=capability,
            current_route_station_m=0.0,
            landing_window=LandingWindow(start_m=130.0, end_m=155.0),
        )
        self.assertTrue(result.available)
        self.assertEqual(result.items, ())
        self.assertEqual(result.evidence_refs, capability.evidence_refs)

    def test_outer_product_shape_and_unknown_kind_fail_closed(self) -> None:
        malformed = verified_capability(
            "hazardGuidance",
            {
                "schema": "ai-caddie-hazardGuidance-body-v1",
                "routeGeometryHash": "f" * 64,
                "stationingBasis": "tee-origin-route-station-v1",
                "hazards": [],
                "subjectRef": "temporary-patch-is-forbidden",
            },
        )
        self.assertFalse(build_hazard_guidance(
            capability=malformed,
            current_route_station_m=0.0,
            landing_window=LandingWindow(start_m=130.0, end_m=155.0),
        ).available)
        unknown = self.capability([{
            "hazardRef": "hazard:lava-1", "kind": "lava",
            "enterDistanceM": 140.0, "clearDistanceM": 151.0,
            "evidenceRefs": ["quality:lava-1:v1"],
        }])
        self.assertFalse(build_hazard_guidance(
            capability=unknown,
            current_route_station_m=0.0,
            landing_window=LandingWindow(start_m=130.0, end_m=155.0),
        ).available)

    def test_missing_or_unpromoted_capability_is_unavailable(self) -> None:
        self.assertFalse(build_hazard_guidance(
            capability=None,
            current_route_station_m=0.0,
            landing_window=LandingWindow(start_m=130.0, end_m=155.0),
        ).available)
        result = build_hazard_guidance(
            capability=verified_capability("playsLike", {"schema": "wrong-capability"}),
            current_route_station_m=0.0,
            landing_window=LandingWindow(start_m=130.0, end_m=155.0),
        )
        self.assertFalse(result.available)
        self.assertEqual(result.reason_code, "hazard_guidance_not_promoted")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `uv run python -m unittest tests.test_hazard_guidance -v`

Expected: FAIL because `ai_caddie.guidance.hazards` does not exist.

- [ ] **Step 3: Implement the promoted semantic consumer**

```python
# ai_caddie/guidance/hazards.py
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import re
from typing import Literal, Mapping

from ai_caddie.guidance.capability_adapter import VerifiedGuidanceCapability


HazardKind = Literal["bunker", "water", "penalty_area", "vegetation", "out_of_bounds", "forced_carry", "layup"]
HAZARD_KINDS = frozenset({
    "bunker", "water", "penalty_area", "vegetation",
    "out_of_bounds", "forced_carry", "layup",
})


@dataclass(frozen=True)
class LandingWindow:
    start_m: float
    end_m: float

    def __post_init__(self) -> None:
        if not isfinite(self.start_m) or not isfinite(self.end_m):
            raise ValueError("landing window must be finite")
        if self.start_m < 0 or self.end_m < self.start_m:
            raise ValueError("landing window must be ordered and non-negative")


@dataclass(frozen=True)
class PromotedHazard:
    hazard_ref: str
    kind: HazardKind
    absolute_enter_station_m: float
    absolute_clear_station_m: float | None
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class HazardGuidanceItem:
    hazard_ref: str
    kind: HazardKind
    enter_distance_m: float
    clear_distance_m: float | None
    evidence_refs: tuple[str, ...]

    def as_wire(self) -> dict[str, object]:
        return {
            "hazardRef": self.hazard_ref,
            "kind": self.kind,
            "enterDistanceM": self.enter_distance_m,
            "clearDistanceM": self.clear_distance_m,
            "evidenceRefs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class HazardGuidanceResult:
    available: bool
    reason_code: str | None
    items: tuple[HazardGuidanceItem, ...]
    evidence_refs: tuple[str, ...]


def _overlaps(
    hazard: PromotedHazard,
    absolute_landing_window: LandingWindow,
) -> bool:
    hazard_end = (
        hazard.absolute_clear_station_m
        if hazard.absolute_clear_station_m is not None
        else hazard.absolute_enter_station_m
    )
    return (
        hazard.absolute_enter_station_m <= absolute_landing_window.end_m
        and hazard_end >= absolute_landing_window.start_m
    )


def build_hazard_guidance(
    *,
    capability: VerifiedGuidanceCapability | None,
    current_route_station_m: float,
    landing_window: LandingWindow,
) -> HazardGuidanceResult:
    if capability is None or capability.capability_name != "hazardGuidance":
        return HazardGuidanceResult(False, "hazard_guidance_not_promoted", (), ())
    if (
        set(capability.body) != {
            "schema", "routeGeometryHash", "stationingBasis", "hazards",
        }
        or capability.body.get("schema") != "ai-caddie-hazardGuidance-body-v1"
        or capability.body.get("stationingBasis") != "tee-origin-route-station-v1"
        or re.fullmatch(
            r"[0-9a-f]{64}", str(capability.body.get("routeGeometryHash") or "")
        ) is None
    ):
        return HazardGuidanceResult(False, "hazard_guidance_not_promoted", (), ())
    raw_hazards = capability.body.get("hazards")
    if (
        not isinstance(raw_hazards, (list, tuple))
        or not isfinite(current_route_station_m)
        or current_route_station_m < 0
    ):
        return HazardGuidanceResult(False, "hazard_guidance_not_promoted", (), ())
    absolute_landing_window = LandingWindow(
        start_m=current_route_station_m + landing_window.start_m,
        end_m=current_route_station_m + landing_window.end_m,
    )
    hazards: list[PromotedHazard] = []
    evidence: set[str] = set(capability.evidence_refs)
    for raw in raw_hazards:
        if not isinstance(raw, Mapping):
            return HazardGuidanceResult(
                False, "hazard_guidance_not_promoted", (), (),
            )
        refs = raw.get("evidenceRefs")
        try:
            hazards.append(PromotedHazard(
                hazard_ref=str(raw.get("hazardRef") or ""),
                kind=str(raw.get("kind") or "other"),  # type: ignore[arg-type]
                absolute_enter_station_m=float(raw["enterDistanceM"]),
                absolute_clear_station_m=None if raw.get("clearDistanceM") is None else float(raw["clearDistanceM"]),
                evidence_refs=tuple(map(str, refs)) if isinstance(refs, (list, tuple)) else (),
            ))
        except (KeyError, TypeError, ValueError):
            return HazardGuidanceResult(
                False, "hazard_guidance_not_promoted", (), (),
            )
        evidence.update(hazards[-1].evidence_refs)
    if [hazard.hazard_ref for hazard in hazards] != sorted({
        hazard.hazard_ref for hazard in hazards
    }):
        return HazardGuidanceResult(
            False, "hazard_guidance_not_promoted", (), (),
        )
    if any(
        not hazard.hazard_ref
        or hazard.kind not in HAZARD_KINDS
        or not hazard.evidence_refs
        or len(hazard.evidence_refs) != len(set(hazard.evidence_refs))
        or not isfinite(hazard.absolute_enter_station_m)
        or hazard.absolute_enter_station_m < 0
        or (
            hazard.absolute_clear_station_m is not None
            and (
                not isfinite(hazard.absolute_clear_station_m)
                or hazard.absolute_clear_station_m < hazard.absolute_enter_station_m
            )
        )
        for hazard in hazards
    ):
        return HazardGuidanceResult(
            False, "hazard_guidance_not_promoted", (), (),
        )
    items = [
        HazardGuidanceItem(
            hazard_ref=hazard.hazard_ref,
            kind=hazard.kind,
            enter_distance_m=max(
                0.0, hazard.absolute_enter_station_m - current_route_station_m,
            ),
            clear_distance_m=(
                None
                if hazard.absolute_clear_station_m is None
                else max(
                    0.0,
                    hazard.absolute_clear_station_m - current_route_station_m,
                )
            ),
            evidence_refs=hazard.evidence_refs,
        )
        for hazard in hazards
        if _overlaps(hazard, absolute_landing_window)
    ]
    items.sort(key=lambda item: (item.enter_distance_m, item.hazard_ref))
    return HazardGuidanceResult(
        True, None, tuple(items), tuple(sorted(evidence)),
    )
```

In `server_v2/guidance.py`, map the canonical `hazards[]` only through the pinned snapshot’s Plan 2 accepted `hazardGuidance` EffectiveCapability. Plan 3 v1 binds the entire sorted, unique multi-row set—including an evidence-backed empty set—to one research-candidate product body；Plan 2 revalidates that body, applies the versioned quality policy and only then publishes it as the promoted runtime product. Its top-level `routeGeometryHash` equals the verified base-map physical blob hash and its `stationingBasis` is exactly `tee-origin-route-station-v1`. Every hazard row's `enterDistanceM`/`clearDistanceM` is therefore an absolute station from the Tee, never a distance from the current ball. Runtime must first project `LiveCurrentPosition` onto that exact route, reject ambiguous or excessive-lateral-offset projections, then add the club-relative landing window to the current absolute station; only the final displayed hazard item converts absolute station back to ball-relative front/clear distance. Never split rows into caller-created capabilities, infer an empty set from capability absence, compare second-shot carry directly to absolute stationing, use request arrival order as rank or reinterpret `enterDistanceM` as `clearDistanceM`.

Replace the legacy water pill projection in `CurrentHoleView.swift` with an explicit formatter:

```swift
func hazardDistanceText(enterYards: Int, clearYards: Int?) -> String {
    guard let clearYards else {
        return "前沿 \(enterYards) 码"
    }
    return "前沿 \(enterYards) 码 · 越过 \(clearYards) 码"
}
```

- [ ] **Step 4: Run hazard and geometry regressions**

Run: `uv run python -m unittest tests.test_hazard_guidance tests.test_course_prep_hazard_geometry tests.test_geometry_evidence -v`

Expected: all tests PASS; canonical multi-row bodies preserve stable order; unsorted/duplicate rows fail closed; “越过” always uses clear distance; an accepted evidence-backed empty body returns an available empty tuple; and capability absence fails closed.

- [ ] **Step 5: Commit promoted hazard guidance**

```bash
git add ai_caddie/guidance/hazards.py server_v2/guidance.py tests/test_hazard_guidance.py mobile/ios/AICaddie/Views/CurrentHoleView.swift
git commit -m "feat: add promoted hazard guidance"
```

## Task D05: Bind an independently promoted macro green surface

**Depends on:** D02c; Track B immutable role-aware asset authority and D02b authoritative `quality_report_id`; Plan 2 has admitted the Plan 3 `greenSurface` research candidate and published a promoted product carrying source hash, component, decoder/calibration, transform, `baseGeometryHash` and registration evidence.

**Files:**
- Create: `ai_caddie/courses/green_surface.py`
- Test: `tests/test_green_surface_binding.py`
- Modify: `server_v2/guidance.py`

- [ ] **Step 1: Write failing binding and mismatch tests**

```python
# tests/test_green_surface_binding.py
from __future__ import annotations

import unittest

from ai_caddie.courses.green_surface import (
    resolve_macro_green_surface,
)
from ai_caddie.contracts.typed_ids import typed_id
from tests.guidance_capability_fixtures import verified_capability


class GreenSurfaceBindingTests(unittest.TestCase):
    def capability(self, **changes: object):
        transform = [1.0, 0.0, 0.0, 1.0, 4.0, -3.0]
        values: dict[str, object] = {
            "schema": "ai-caddie-greenSurface-body-v1",
            "sourceHash": "a" * 64,
            "componentId": "green-component-7",
            "decoderVersion": "green-decoder-v2",
            "calibrationVersion": "green-calibration-v3",
            "orientationTransformId": typed_id(
                "DeepMineGreenOrientationTransform/v1",
                {"matrix": transform},
            ),
            "orientationTransform": transform,
            "baseGeometryHash": "b" * 64,
            "slopeMagnitudePct": 2.4,
            "downhillDirectionDeg": 215.0,
            "registrationResidualM": 2.4,
            "crossSourceResidualM": 5.0,
            "registrationSampleCount": 24,
            "evidenceRefs": ["review:green-7:v3"],
        }
        values.update(changes)
        return verified_capability("greenSurface", values)

    def test_matching_binding_is_available(self) -> None:
        capability = self.capability()
        result = resolve_macro_green_surface(
            capability=capability,
            installed_base_geometry_hash="b" * 64,
        )
        self.assertTrue(result.available)
        self.assertEqual(result.surface.component_id, "green-component-7")
        self.assertEqual(result.surface.quality_report_id, capability.quality_report_id)
        self.assertEqual(result.surface.registration_residual_m, 2.4)
        self.assertEqual(result.surface.cross_source_residual_m, 5.0)
        self.assertEqual(result.surface.registration_sample_count, 24)
        self.assertFalse(hasattr(result.surface, "quality_report_hash"))

    def test_base_geometry_mismatch_fails_closed(self) -> None:
        result = resolve_macro_green_surface(
            capability=self.capability(),
            installed_base_geometry_hash="d" * 64,
        )
        self.assertFalse(result.available)
        self.assertEqual(result.reason_code, "green_surface_geometry_mismatch")

    def test_transform_identity_and_exact_body_shape_fail_closed(self) -> None:
        for changes in (
            {"orientationTransformId": "0" * 64},
            {"metadata": {"slopeMagnitudePct": 2.4}},
        ):
            with self.subTest(changes=changes):
                result = resolve_macro_green_surface(
                    capability=self.capability(**changes),
                    installed_base_geometry_hash="b" * 64,
                )
                self.assertFalse(result.available)
                self.assertEqual(result.reason_code, "green_surface_not_promoted")

    def test_registration_gate_fields_are_not_dropped_or_bypassed(self) -> None:
        for changes in (
            {"registrationResidualM": 3.01},
            {"crossSourceResidualM": 8.01},
            {"registrationSampleCount": 11},
            {"registrationSampleCount": 12.0},
        ):
            with self.subTest(changes=changes):
                result = resolve_macro_green_surface(
                    capability=self.capability(**changes),
                    installed_base_geometry_hash="b" * 64,
                )
                self.assertFalse(result.available)
                self.assertEqual(result.reason_code, "green_surface_not_promoted")

    def test_unpromoted_surface_is_unavailable(self) -> None:
        result = resolve_macro_green_surface(
            capability=verified_capability("playsLike", {"schema": "wrong-capability"}),
            installed_base_geometry_hash="b" * 64,
        )
        self.assertFalse(result.available)
        self.assertEqual(result.reason_code, "green_surface_not_promoted")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `uv run python -m unittest tests.test_green_surface_binding -v`

Expected: FAIL because `ai_caddie.courses.green_surface` does not exist.

- [ ] **Step 3: Implement the immutable registration consumer**

```python
# ai_caddie/courses/green_surface.py
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import re
from typing import Mapping

from ai_caddie.contracts.typed_ids import typed_id
from ai_caddie.guidance.capability_adapter import VerifiedGuidanceCapability


@dataclass(frozen=True)
class MacroGreenSurfaceBinding:
    source_hash: str
    component_id: str
    decoder_version: str
    calibration_version: str
    orientation_transform_id: str
    orientation_transform: tuple[float, float, float, float, float, float]
    base_geometry_hash: str
    quality_report_id: str
    slope_magnitude_pct: float
    downhill_direction_deg: float | None
    registration_residual_m: float
    cross_source_residual_m: float
    registration_sample_count: int
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class MacroGreenSurfaceResult:
    available: bool
    reason_code: str | None
    surface: MacroGreenSurfaceBinding | None


def _binding_is_complete(binding: MacroGreenSurfaceBinding) -> bool:
    direction_valid = (
        binding.downhill_direction_deg is None
        or (
            isfinite(binding.downhill_direction_deg)
            and 0.0 <= binding.downhill_direction_deg < 360.0
        )
    )
    return (
        bool(binding.source_hash)
        and bool(binding.component_id)
        and bool(binding.decoder_version)
        and bool(binding.calibration_version)
        and re.fullmatch(r"[0-9a-f]{64}", binding.orientation_transform_id) is not None
        and len(binding.orientation_transform) == 6
        and all(isfinite(value) for value in binding.orientation_transform)
        and binding.orientation_transform_id == typed_id(
            "DeepMineGreenOrientationTransform/v1",
            {"matrix": list(binding.orientation_transform)},
        )
        and re.fullmatch(r"[0-9a-f]{64}", binding.source_hash) is not None
        and bool(binding.base_geometry_hash)
        and re.fullmatch(r"[0-9a-f]{64}", binding.base_geometry_hash) is not None
        and bool(binding.quality_report_id)
        and isfinite(binding.slope_magnitude_pct)
        and binding.slope_magnitude_pct >= 0
        and direction_valid
        and isfinite(binding.registration_residual_m)
        and 0.0 <= binding.registration_residual_m <= 3.0
        and isfinite(binding.cross_source_residual_m)
        and 0.0 <= binding.cross_source_residual_m <= 8.0
        and type(binding.registration_sample_count) is int
        and binding.registration_sample_count >= 12
        and bool(binding.evidence_refs)
        and binding.evidence_refs == tuple(sorted(set(binding.evidence_refs)))
    )


def resolve_macro_green_surface(
    *,
    capability: VerifiedGuidanceCapability,
    installed_base_geometry_hash: str,
) -> MacroGreenSurfaceResult:
    if capability.capability_name != "greenSurface":
        return MacroGreenSurfaceResult(False, "green_surface_not_promoted", None)
    body = capability.body
    if set(body) != {
        "schema", "sourceHash", "componentId", "decoderVersion",
        "calibrationVersion", "orientationTransformId",
        "orientationTransform", "baseGeometryHash", "slopeMagnitudePct",
        "downhillDirectionDeg", "registrationResidualM",
        "crossSourceResidualM", "registrationSampleCount", "evidenceRefs",
    } or body.get("schema") != "ai-caddie-greenSurface-body-v1":
        return MacroGreenSurfaceResult(False, "green_surface_not_promoted", None)
    transform = body.get("orientationTransform")
    evidence = body.get("evidenceRefs")
    sample_count = body.get("registrationSampleCount")
    if (
        not isinstance(transform, (list, tuple))
        or not isinstance(evidence, (list, tuple))
        or type(sample_count) is not int
    ):
        return MacroGreenSurfaceResult(False, "green_surface_not_promoted", None)
    try:
        binding = MacroGreenSurfaceBinding(
            source_hash=str(body["sourceHash"]),
            component_id=str(body["componentId"]),
            decoder_version=str(body["decoderVersion"]),
            calibration_version=str(body["calibrationVersion"]),
            orientation_transform_id=str(body["orientationTransformId"]),
            orientation_transform=tuple(map(float, transform)),  # type: ignore[arg-type]
            base_geometry_hash=str(body["baseGeometryHash"]),
            quality_report_id=capability.quality_report_id,
            slope_magnitude_pct=float(body["slopeMagnitudePct"]),
            downhill_direction_deg=None if body.get("downhillDirectionDeg") is None else float(body["downhillDirectionDeg"]),
            registration_residual_m=float(body["registrationResidualM"]),
            cross_source_residual_m=float(body["crossSourceResidualM"]),
            registration_sample_count=sample_count,
            evidence_refs=tuple(map(str, evidence)),
        )
    except (KeyError, TypeError, ValueError):
        return MacroGreenSurfaceResult(False, "green_surface_not_promoted", None)
    if not _binding_is_complete(binding):
        return MacroGreenSurfaceResult(False, "green_surface_not_promoted", None)
    if binding.base_geometry_hash != installed_base_geometry_hash:
        return MacroGreenSurfaceResult(False, "green_surface_geometry_mismatch", None)
    return MacroGreenSurfaceResult(True, None, binding)
```

`server_v2/guidance.py` must load the surface asset only through the Track B installed manifest binding and a D02b-minted `greenSurface` capability carrying the exact Plan 2-promoted runtime-product body plus the retained Plan 3 closure/fingerprint/unknown/consumer evidence refs. D05 accepts no metadata wrapper: it checks the exact body keys, recomputes `orientationTransformId` from the six-value matrix, and consumes the evidence-bound `slopeMagnitudePct`/`downhillDirectionDeg` values without recomputing or overriding them. It also preserves Plan 3 candidate evidence values `registrationResidualM`、`crossSourceResidualM` and `registrationSampleCount` as immutable audit fields only after Plan 2 has independently admitted them；values above `3.0 m`、above `8.0 m` or below `12` samples cannot enable the surface. The quality report is bound separately by `VerifiedGuidanceCapability.quality_report_id`; `qualityReportHash` is forbidden in the candidate body because the Plan 2 report is produced after candidate admission and would create an identity cycle. The consumer passes the installed `baseGeometryHash`; it never imports the research candidate, calls `elevation.green_slope` or reads mutable `Green.drc` directly.

The legacy `course_prep.greenSlope` remains unavailable from D00; do not re-enable it.

- [ ] **Step 4: Run binding, green-distance, and promotion consumer tests**

Run: `uv run python -m unittest tests.test_green_surface_binding tests.test_course_prep_green_distances tests.test_track_d_safety_gates -v`

Expected: all tests PASS; a base-geometry mismatch always reports `green_surface_geometry_mismatch`.

- [ ] **Step 5: Commit macro green binding**

```bash
git add ai_caddie/courses/green_surface.py server_v2/guidance.py tests/test_green_surface_binding.py
git commit -m "feat: bind promoted macro green surfaces"
```

## Task D06: Admit only canonical confirmed shots into club calibration

**Depends on:** Track A stable `shot_recorded`, `shot_target_set`, `shot_target_retracted`, `shot_fact_corrected`, `shot_retracted`, `actual_club_set`, entity revision and deterministic `RoundProjectionV2.shot_targets`. Aim is never inferred from Guidance, green center, route centerline or the next-shot position.

**Files:**
- Create: `ai_caddie/players/club_calibration.py`
- Test: `tests/test_club_calibration.py`
- Modify: `ai_caddie/core/data.py:644-720`
- Modify: `ai_caddie/history/history_stats.py:3195-3270`

- [ ] **Step 1: Write failing admission and rejection tests**

```python
# tests/test_club_calibration.py
from __future__ import annotations

import unittest

from ai_caddie.players.club_calibration import (
    ShotFact,
    admit_calibration_sample,
    shot_fact_from_projection,
)
from ai_caddie.rounds.reducer_v2 import RoundProjectionV2, ShotProjection, ShotTargetProjection


class ClubCalibrationAdmissionTests(unittest.TestCase):
    def fact(self, **changes: object) -> ShotFact:
        values: dict[str, object] = {
            "shot_id": "22222222-2222-4222-8222-222222222222",
            "club_ref": "club:iron7",
            "confirmation_state": "confirmed",
            "retracted": False,
            "shot_kind": "full",
            "start_e_m": 0.0,
            "start_n_m": 0.0,
            "target_e_m": 0.0,
            "target_n_m": 150.0,
            "target_provenance": "explicit_touch_target",
            "target_orphaned": False,
            "target_retracted": False,
            "end_e_m": -4.0,
            "end_n_m": 144.0,
            "provenance_ref": "event:22222222-2222-4222-8222-222222222223",
        }
        values.update(changes)
        return ShotFact(**values)

    def test_confirmed_manual_shot_is_admitted(self) -> None:
        result = admit_calibration_sample(self.fact())
        self.assertTrue(result.accepted)
        self.assertEqual(result.sample.club_ref, "club:iron7")

    def test_unconfirmed_autoshot_candidate_is_rejected(self) -> None:
        result = admit_calibration_sample(
            self.fact(confirmation_state="candidate", provenance_ref="autoshot:candidate-1")
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason_code, "shot_not_confirmed")

    def test_retracted_shot_is_rejected(self) -> None:
        result = admit_calibration_sample(self.fact(retracted=True))
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason_code, "shot_retracted")

    def test_recommendation_without_actual_club_is_rejected(self) -> None:
        result = admit_calibration_sample(self.fact(club_ref=None))
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason_code, "actual_club_missing")

    def test_putt_is_not_a_full_swing_calibration_sample(self) -> None:
        result = admit_calibration_sample(self.fact(shot_kind="putt"))
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason_code, "shot_kind_ineligible")

    def test_unconfirmed_guidance_target_is_not_treated_as_player_aim(self) -> None:
        result = admit_calibration_sample(self.fact(target_provenance="guidance_unconfirmed"))
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason_code, "shot_target_unconfirmed")

    def test_orphaned_or_retracted_durable_target_is_rejected(self) -> None:
        self.assertEqual(admit_calibration_sample(self.fact(target_orphaned=True)).reason_code, "shot_target_missing")
        self.assertEqual(admit_calibration_sample(self.fact(target_retracted=True)).reason_code, "shot_target_missing")

    def test_projection_adapter_requires_explicit_canonical_shot_kind(self) -> None:
        shot_id = "22222222-2222-4222-8222-222222222222"
        next_id = "33333333-3333-4333-8333-333333333333"
        projection = RoundProjectionV2(
            shots={
                shot_id: ShotProjection(shot_id, 7, 22.279, 114.162, 4.0, "fairway", "manual", "club:iron7", False),
                next_id: ShotProjection(next_id, 7, 22.280, 114.162, 4.0, "fringe", "manual", None, False),
            },
            shot_targets={
                shot_id: ShotTargetProjection(shot_id, "touch:7:1", 22.280, 114.162, "explicit_touch_target", False, False),
            },
        )
        fact = shot_fact_from_projection(
            projection, shot_id=shot_id, next_shot_id=next_id, shot_kind="putt",
            project_wgs84=lambda latitude, longitude: (longitude, latitude),
        )
        self.assertEqual(fact.shot_kind, "putt")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `uv run python -m unittest tests.test_club_calibration -v`

Expected: FAIL because `ai_caddie.players.club_calibration` does not exist.

- [ ] **Step 3: Implement canonical projection admission**

```python
# ai_caddie/players/club_calibration.py
from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite
from typing import Callable, Literal

from ai_caddie.rounds.reducer_v2 import RoundProjectionV2


ConfirmationState = Literal["candidate", "confirmed", "rejected", "superseded"]


@dataclass(frozen=True)
class ShotFact:
    shot_id: str
    club_ref: str | None
    confirmation_state: ConfirmationState
    retracted: bool
    shot_kind: str
    start_e_m: float
    start_n_m: float
    target_e_m: float
    target_n_m: float
    target_provenance: str
    target_orphaned: bool
    target_retracted: bool
    end_e_m: float
    end_n_m: float
    provenance_ref: str


@dataclass(frozen=True)
class CalibrationSample:
    shot_id: str
    club_ref: str
    start_e_m: float
    start_n_m: float
    target_e_m: float
    target_n_m: float
    target_provenance: str
    end_e_m: float
    end_n_m: float
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class CalibrationAdmission:
    accepted: bool
    reason_code: str | None
    sample: CalibrationSample | None


def admit_calibration_sample(fact: ShotFact) -> CalibrationAdmission:
    if fact.confirmation_state != "confirmed":
        return CalibrationAdmission(False, "shot_not_confirmed", None)
    if fact.retracted:
        return CalibrationAdmission(False, "shot_retracted", None)
    if not fact.club_ref:
        return CalibrationAdmission(False, "actual_club_missing", None)
    if fact.shot_kind == "putt":
        return CalibrationAdmission(False, "shot_kind_ineligible", None)
    if fact.target_orphaned or fact.target_retracted:
        return CalibrationAdmission(False, "shot_target_missing", None)
    if fact.target_provenance not in {"player_confirmed", "explicit_touch_target"}:
        return CalibrationAdmission(False, "shot_target_unconfirmed", None)
    coordinates = (
        fact.start_e_m,
        fact.start_n_m,
        fact.target_e_m,
        fact.target_n_m,
        fact.end_e_m,
        fact.end_n_m,
    )
    if not all(isfinite(value) for value in coordinates):
        return CalibrationAdmission(False, "shot_geometry_invalid", None)
    if hypot(fact.target_e_m - fact.start_e_m, fact.target_n_m - fact.start_n_m) < 1.0:
        return CalibrationAdmission(False, "shot_target_missing", None)
    if not fact.provenance_ref:
        return CalibrationAdmission(False, "shot_provenance_missing", None)
    return CalibrationAdmission(
        True,
        None,
        CalibrationSample(
            shot_id=fact.shot_id,
            club_ref=fact.club_ref,
            start_e_m=fact.start_e_m,
            start_n_m=fact.start_n_m,
            target_e_m=fact.target_e_m,
            target_n_m=fact.target_n_m,
            target_provenance=fact.target_provenance,
            end_e_m=fact.end_e_m,
            end_n_m=fact.end_n_m,
            evidence_refs=(fact.provenance_ref,),
        ),
    )
```

Add the exact Track A projection adapter; `project_wgs84` is the verified local EN transform bound to the installed snapshot:

```python
def shot_fact_from_projection(
    projection: RoundProjectionV2,
    *,
    shot_id: str,
    next_shot_id: str,
    shot_kind: Literal["full", "putt"],
    project_wgs84: Callable[[float, float], tuple[float, float]],
) -> ShotFact:
    shot = projection.shots[shot_id]
    target = projection.shot_targets.get(shot_id)
    end = projection.shots[next_shot_id]
    start_e, start_n = project_wgs84(shot.latitude, shot.longitude)
    end_e, end_n = project_wgs84(end.latitude, end.longitude)
    target_e, target_n = (0.0, 0.0) if target is None else project_wgs84(target.latitude, target.longitude)
    return ShotFact(
        shot_id=shot.shot_id,
        club_ref=shot.actual_club_id,
        confirmation_state="confirmed",
        retracted=shot.retracted,
        shot_kind=shot_kind,
        start_e_m=start_e, start_n_m=start_n,
        target_e_m=target_e, target_n_m=target_n,
        target_provenance="missing" if target is None else target.provenance,
        target_orphaned=True if target is None else target.orphaned,
        target_retracted=False if target is None else target.retracted,
        end_e_m=end_e, end_n_m=end_n,
        provenance_ref=f"shot:{shot.shot_id}:target:{'missing' if target is None else target.target_ref}",
    )
```

Replace direct shot-dictionary aggregation in `build_club_profiles` and `_clubs` with this adapter followed by `admit_calibration_sample`. Keep legacy one-dimensional summaries only as explicitly named review compatibility fields; do not feed them into current-shot Guidance after D07.

- [ ] **Step 4: Run calibration and bag regressions**

Run: `uv run python -m unittest tests.test_club_calibration tests.test_manual_club_bag tests.test_effective_club_ladder tests.test_decision_layer -v`

Expected: all tests PASS; unconfirmed AutoShot candidates, retracted shots and recommendation-only clubs never enter calibration.

- [ ] **Step 5: Commit canonical sample admission**

```bash
git add ai_caddie/players/club_calibration.py ai_caddie/core/data.py ai_caddie/history/history_stats.py tests/test_club_calibration.py
git commit -m "feat: admit canonical club calibration samples"
```

## Task D07: Build a robust two-dimensional club dispersion model

**Depends on:** D06.

**Files:**
- Modify: `ai_caddie/players/club_calibration.py`
- Modify: `server_v2/guidance.py`
- Test: `tests/test_club_dispersion.py`
- Modify: `contracts/canonical/guidance_v1.schema.json`
- Modify: `tools/contracts/generate_contracts.py`
- Regenerate: `ai_caddie/contracts/generated.py`
- Regenerate: `mobile/ios/AICaddieDomain/GeneratedContracts.swift`
- Regenerate: `web_v2/src/contracts/generated.ts`
- Create: `contracts/canonical/fixtures/guidance/club_calibration_dispersion_golden.json`
- Create: `contracts/canonical/fixtures/guidance/club_calibration_available.json`
- Create: `contracts/canonical/fixtures/guidance/club_calibration_unavailable.json`
- Modify: `tests/test_guidance_contract.py`
- Modify: `tests/test_contract_codegen.py`
- Modify: `mobile/ios/AICaddieDomainTests/GuidanceContractTests.swift`
- Modify: `web_v2/src/contracts/generated.test.ts`

- [ ] **Step 1: Write failing shot-frame, outlier, covariance, and ellipse tests**

```python
# tests/test_club_dispersion.py
from __future__ import annotations

import math
import unittest
from uuid import UUID

from ai_caddie.players.club_calibration import (
    CalibrationPolicy,
    CalibrationSample,
    build_club_dispersion,
    ellipse_axes,
    project_sample_to_shot_frame,
)


class ClubDispersionTests(unittest.TestCase):
    @staticmethod
    def shot_id(index: int) -> str:
        value = f"00000000-0000-4000-8000-{index + 1:012x}"
        assert UUID(value).version == 4
        return value

    def sample(self, shot_id: str, along_m: float, cross_m: float) -> CalibrationSample:
        return CalibrationSample(
            shot_id=shot_id,
            club_ref="club:iron7",
            start_e_m=0.0,
            start_n_m=0.0,
            target_e_m=0.0,
            target_n_m=150.0,
            target_provenance="explicit_touch_target",
            end_e_m=-cross_m,
            end_n_m=along_m,
            evidence_refs=(f"event:{shot_id}",),
        )

    def test_projects_world_coordinates_into_along_cross_frame(self) -> None:
        along, cross = project_sample_to_shot_frame(self.sample("22222222-2222-4222-8222-222222222222", 144.0, -4.0))
        self.assertAlmostEqual(along, 144.0)
        self.assertAlmostEqual(cross, -4.0)

    def test_robust_model_excludes_extreme_outlier(self) -> None:
        samples = [
            self.sample(self.shot_id(index), 140.0 + (index % 5), float((index % 3) - 1))
            for index in range(24)
        ]
        outlier_id = self.shot_id(24)
        samples.append(self.sample(outlier_id, 260.0, 90.0))
        model = build_club_dispersion(
            samples,
            CalibrationPolicy(
                version="club-calibration-policy-v1",
                minimum_samples=20,
                outlier_mad_multiplier=4.5,
                confidence=0.68,
            ),
        )
        self.assertTrue(model.available)
        self.assertEqual(model.sample_size, 24)
        self.assertNotIn(f"event:{outlier_id}", model.evidence_refs)
        self.assertLess(model.center_along_m, 150.0)
        self.assertTrue(model.calibration_version.startswith("club-calibration-v1:"))

    def test_insufficient_samples_never_produce_an_ellipse(self) -> None:
        model = build_club_dispersion(
            [self.sample(self.shot_id(index), 140.0, 0.0) for index in range(10)],
            CalibrationPolicy("club-calibration-policy-v1", 20, 4.5, 0.68),
        )
        self.assertFalse(model.available)
        self.assertEqual(model.reason_code, "guidance_calibration_missing")

    def test_ellipse_axes_are_finite_and_ordered(self) -> None:
        major, minor, angle = ellipse_axes(64.0, 3.0, 25.0, confidence=0.68)
        self.assertGreaterEqual(major, minor)
        self.assertGreater(minor, 0.0)
        self.assertTrue(math.isfinite(angle))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `uv run python -m unittest tests.test_club_dispersion -v`

Expected: FAIL because `CalibrationPolicy`, `build_club_dispersion`, and `ellipse_axes` do not exist.

- [ ] **Step 3: Implement the robust frame, covariance, and ellipse math**

Append to `ai_caddie/players/club_calibration.py`:

```python
from hashlib import sha256
from math import atan2, log, sqrt
from statistics import median
from typing import Iterable


@dataclass(frozen=True)
class CalibrationPolicy:
    version: str
    minimum_samples: int
    outlier_mad_multiplier: float
    confidence: float

    def __post_init__(self) -> None:
        if not self.version:
            raise ValueError("calibration policy version is required")
        if self.minimum_samples < 2:
            raise ValueError("minimum_samples must be at least two")
        if self.outlier_mad_multiplier <= 0:
            raise ValueError("outlier multiplier must be positive")
        if not 0 < self.confidence < 1:
            raise ValueError("confidence must be between zero and one")


@dataclass(frozen=True)
class ClubDispersionModel:
    available: bool
    reason_code: str | None
    club_ref: str
    sample_size: int
    center_along_m: float
    center_cross_m: float
    covariance_xx_m2: float
    covariance_xy_m2: float
    covariance_yy_m2: float
    confidence: float
    calibration_version: str
    policy_version: str
    evidence_refs: tuple[str, ...]

    def as_calibration_wire(self) -> dict[str, object] | None:
        if not self.available:
            return None
        return {
            "centerAlongM": self.center_along_m,
            "centerCrossM": self.center_cross_m,
            "covarianceXXM2": self.covariance_xx_m2,
            "covarianceXYM2": self.covariance_xy_m2,
            "covarianceYYM2": self.covariance_yy_m2,
            "confidence": self.confidence,
            "sampleSize": self.sample_size,
            "calibrationVersion": self.calibration_version,
        }


def project_sample_to_shot_frame(sample: CalibrationSample) -> tuple[float, float]:
    target_e = sample.target_e_m - sample.start_e_m
    target_n = sample.target_n_m - sample.start_n_m
    target_length = hypot(target_e, target_n)
    if target_length < 1.0:
        raise ValueError("shot target is too close to define a frame")
    along_e = target_e / target_length
    along_n = target_n / target_length
    right_e = along_n
    right_n = -along_e
    shot_e = sample.end_e_m - sample.start_e_m
    shot_n = sample.end_n_m - sample.start_n_m
    along = shot_e * along_e + shot_n * along_n
    cross = shot_e * right_e + shot_n * right_n
    return along, cross


def _median_absolute_deviation(values: list[float]) -> float:
    center = median(values)
    return median([abs(value - center) for value in values])


def build_club_dispersion(
    samples: Iterable[CalibrationSample],
    policy: CalibrationPolicy,
) -> ClubDispersionModel:
    rows = list(samples)
    if not rows:
        return ClubDispersionModel(
            False, "guidance_calibration_missing", "", 0, 0.0, 0.0,
            0.0, 0.0, 0.0, policy.confidence, "", policy.version, (),
        )
    club_ref = rows[0].club_ref
    rows = [row for row in rows if row.club_ref == club_ref]
    points = [(row, *project_sample_to_shot_frame(row)) for row in rows]
    center_along = median([along for _, along, _ in points])
    center_cross = median([cross for _, _, cross in points])
    radial = [hypot(along - center_along, cross - center_cross) for _, along, cross in points]
    radial_center = median(radial)
    radial_mad = max(_median_absolute_deviation(radial), 0.5)
    cutoff = radial_center + policy.outlier_mad_multiplier * radial_mad
    inliers = [
        (row, along, cross)
        for (row, along, cross), distance in zip(points, radial, strict=True)
        if distance <= cutoff
    ]
    if len(inliers) < policy.minimum_samples:
        return ClubDispersionModel(
            False, "guidance_calibration_missing", club_ref, len(inliers), 0.0, 0.0,
            0.0, 0.0, 0.0, policy.confidence, "", policy.version, (),
        )
    center_along = median([along for _, along, _ in inliers])
    center_cross = median([cross for _, _, cross in inliers])
    denominator = len(inliers) - 1
    covariance_xx = sum((along - center_along) ** 2 for _, along, _ in inliers) / denominator
    covariance_xy = sum(
        (along - center_along) * (cross - center_cross)
        for _, along, cross in inliers
    ) / denominator
    covariance_yy = sum((cross - center_cross) ** 2 for _, _, cross in inliers) / denominator
    evidence_refs = tuple(
        ref
        for row, _, _ in sorted(inliers, key=lambda item: item[0].shot_id)
        for ref in row.evidence_refs
    )
    calibration_digest = sha256(
        "\0".join((policy.version, club_ref, *evidence_refs)).encode("utf-8")
    ).hexdigest()
    return ClubDispersionModel(
        True,
        None,
        club_ref,
        len(inliers),
        center_along,
        center_cross,
        covariance_xx,
        covariance_xy,
        covariance_yy,
        policy.confidence,
        f"club-calibration-v1:{calibration_digest}",
        policy.version,
        evidence_refs,
    )


def ellipse_axes(
    covariance_xx_m2: float,
    covariance_xy_m2: float,
    covariance_yy_m2: float,
    *,
    confidence: float,
) -> tuple[float, float, float]:
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between zero and one")
    trace = covariance_xx_m2 + covariance_yy_m2
    discriminant = sqrt(
        max(0.0, (covariance_xx_m2 - covariance_yy_m2) ** 2 + 4.0 * covariance_xy_m2 ** 2)
    )
    major_variance = max(0.0, (trace + discriminant) / 2.0)
    minor_variance = max(0.0, (trace - discriminant) / 2.0)
    scale = sqrt(-2.0 * log(1.0 - confidence))
    major = scale * sqrt(major_variance)
    minor = scale * sqrt(minor_variance)
    angle = 0.5 * atan2(2.0 * covariance_xy_m2, covariance_xx_m2 - covariance_yy_m2)
    return major, minor, angle
```

Extend `guidance_v1.schema.json` with an exact generated `ClubCalibrationDispersionV1` definition whose keys are `centerAlongM,centerCrossM,covarianceXXM2,covarianceXYM2,covarianceYYM2,confidence,sampleSize,calibrationVersion`. Also freeze generated `GuidanceClubCalibrationV1` with exact keys `clubRef,available,reasonCodes,dispersion,policyVersion,evidenceRefs`: when `available=true`, `dispersion` is a non-null `ClubCalibrationDispersionV1` and `reasonCodes=[]`; when false, `dispersion=null` and `reasonCodes` is the sorted-unique non-empty blocked-reason roster. `clubRef`/`policyVersion` are non-empty bounded strings and `evidenceRefs` is sorted unique. Keep the existing `GuidanceDispersionV1` definition unchanged and covariance-only. Add schema/codegen regressions that reject `centerAlongM/centerCrossM` in a current-shot Guidance envelope, reject their absence from an available club-calibration row, reject an unavailable row with a dispersion, and reject an available row with reason codes.

Create `contracts/canonical/fixtures/guidance/club_calibration_dispersion_golden.json`:

```json
{
  "centerAlongM": 142.0,
  "centerCrossM": 0.0,
  "covarianceXXM2": 2.0,
  "covarianceXYM2": 0.043478260869565216,
  "covarianceYYM2": 0.6956521739130435,
  "confidence": 0.68,
  "sampleSize": 24,
  "calibrationVersion": "club-calibration-v1:a59a32feca4d00dca9e4870cc16166c1da994c478e6af964b7bc4c6bb22f29a8"
}
```

Create the exact generated-row goldens:

`club_calibration_available.json`:

```json
{
  "clubRef": "club:iron7",
  "available": true,
  "reasonCodes": [],
  "dispersion": {
    "centerAlongM": 142.0,
    "centerCrossM": 0.0,
    "covarianceXXM2": 2.0,
    "covarianceXYM2": 0.043478260869565216,
    "covarianceYYM2": 0.6956521739130435,
    "confidence": 0.68,
    "sampleSize": 24,
    "calibrationVersion": "club-calibration-v1:a59a32feca4d00dca9e4870cc16166c1da994c478e6af964b7bc4c6bb22f29a8"
  },
  "policyVersion": "club-calibration-policy-v1",
  "evidenceRefs": ["event:11111111-1111-4111-8111-111111111111"]
}
```

`club_calibration_unavailable.json`:

```json
{
  "clubRef": "club:wood7",
  "available": false,
  "reasonCodes": ["guidance_calibration_missing"],
  "dispersion": null,
  "policyVersion": "club-calibration-policy-v1",
  "evidenceRefs": []
}
```

Add this exact assertion to `tests/test_guidance_contract.py`:

```python
class GuidanceContractTests:
    def test_dispersion_golden_uses_exact_robust_model_values(self) -> None:
        payload = json.loads(
            (ROOT / "fixtures/guidance/club_calibration_dispersion_golden.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["centerAlongM"], 142.0)
        self.assertEqual(payload["centerCrossM"], 0.0)
        self.assertEqual(payload["covarianceXXM2"], 2.0)
        self.assertEqual(payload["covarianceXYM2"], 0.043478260869565216)
        self.assertEqual(payload["covarianceYYM2"], 0.6956521739130435)
        self.assertEqual(payload["sampleSize"], 24)
        self.assertEqual(
            payload["calibrationVersion"],
            "club-calibration-v1:a59a32feca4d00dca9e4870cc16166c1da994c478e6af964b7bc4c6bb22f29a8",
        )
```

Swift and TypeScript fixture tests decode this file and compare the same numeric fields; neither client re-estimates covariance.

Add to `GuidanceContractTests.swift`:

```swift
    func testDecodesExactDispersionGolden() throws {
        let dispersion = try JSONDecoder().decode(
            ClubCalibrationDispersionV1.self,
            from: fixture("club_calibration_dispersion_golden.json")
        )
        XCTAssertEqual(dispersion.centerAlongM, 142.0)
        XCTAssertEqual(dispersion.covarianceXYM2, 0.043478260869565216)
        XCTAssertEqual(dispersion.sampleSize, 24)
        XCTAssertEqual(
            dispersion.calibrationVersion,
            "club-calibration-v1:a59a32feca4d00dca9e4870cc16166c1da994c478e6af964b7bc4c6bb22f29a8"
        )
    }
```

Add to `web_v2/src/contracts/generated.test.ts`:

```tsx
import dispersionGolden from '../../../contracts/canonical/fixtures/guidance/club_calibration_dispersion_golden.json'
import type { ClubCalibrationDispersionV1 } from './generated'

it('uses the exact generated two-dimensional dispersion fixture', () => {
  const dispersion: ClubCalibrationDispersionV1 = dispersionGolden
  expect(dispersion.centerAlongM).toBe(142)
  expect(dispersion.covarianceXYM2).toBe(0.043478260869565216)
  expect(dispersion.sampleSize).toBe(24)
  expect(dispersion.calibrationVersion).toBe(
    'club-calibration-v1:a59a32feca4d00dca9e4870cc16166c1da994c478e6af964b7bc4c6bb22f29a8',
  )
})
```

`server_v2/guidance.py` exposes the player’s rows as generated `GuidanceClubCalibrationV1` objects whose `dispersion` is `ClubCalibrationDispersionV1`, never the current-shot `GuidanceDispersionV1`. An unavailable model returns `dispersion: null`, `reasonCodes: ["guidance_calibration_missing"]`, the policy version and admitted evidence refs; it never substitutes legacy `dispersionRange`.

```python
# server_v2/guidance.py
from ai_caddie.contracts.generated import GuidanceClubCalibrationV1
from ai_caddie.players.club_calibration import ClubDispersionModel


def club_calibration_wire(model: ClubDispersionModel) -> GuidanceClubCalibrationV1:
    return GuidanceClubCalibrationV1(
        clubRef=model.club_ref,
        available=model.available,
        reasonCodes=[] if model.available else [model.reason_code or "guidance_calibration_missing"],
        dispersion=model.as_calibration_wire(),
        policyVersion=model.policy_version,
        evidenceRefs=list(model.evidence_refs),
    )
```

- [ ] **Step 4: Run dispersion and cross-language contract regressions**

Run:

```bash
uv run python tools/contracts/generate_contracts.py
uv run python -m unittest tests.test_contract_codegen tests.test_club_dispersion tests.test_club_calibration tests.test_guidance_contract -v
swift test --filter AICaddieDomainTests
npm --prefix web_v2 test -- --run src/contracts/generated.test.ts
```

Expected: all suites PASS；the canonical-contracts source digest and Python/Swift/TypeScript outputs are byte-current in this checkpoint, the extreme outlier is absent from `evidence_refs`, and Swift/TypeScript decode the same golden covariance object.

- [ ] **Step 5: Commit true two-dimensional dispersion**

```bash
git add ai_caddie/players/club_calibration.py server_v2/guidance.py contracts/canonical/guidance_v1.schema.json tools/contracts/generate_contracts.py ai_caddie/contracts/generated.py mobile/ios/AICaddieDomain/GeneratedContracts.swift web_v2/src/contracts/generated.ts tests/test_club_dispersion.py contracts/canonical/fixtures/guidance/club_calibration_dispersion_golden.json contracts/canonical/fixtures/guidance/club_calibration_available.json contracts/canonical/fixtures/guidance/club_calibration_unavailable.json tests/test_guidance_contract.py tests/test_contract_codegen.py mobile/ios/AICaddieDomainTests/GuidanceContractTests.swift web_v2/src/contracts/generated.test.ts
git commit -m "feat: model calibrated two-dimensional dispersion"
```

## Task D07a: Persist lie-conditioned player models and real production providers

**Supersedes:** fixture-only `ClubModelProvider` lambdas and anonymous in-memory calibration. D08/D08a/D08b must be constructible after a process restart from durable canonical facts and the pinned LiveRoundPackage; no production composition root may inject constant carry/covariance/elevation values.

**Depends on:** D06–D07; Track A authoritative projections and `actual_club_set`; Plan 1 `LiveRoundPackageV2.playerBagSnapshot/guidanceEngineBundle`; D02c static authority.

**Files:**
- Create: `contracts/canonical/player_bag_snapshot_v1.schema.json`
- Create: `contracts/canonical/player_guidance_model_v1.schema.json`
- Create: `contracts/canonical/guidance_engine_bundle_v1.schema.json`
- Modify: `contracts/canonical/live_round_package_v2.schema.json`
- Modify: `contracts/canonical/canonical_object_registry.json`
- Modify: `contracts/canonical/reason_codes.json`
- Modify: `tools/contracts/generate_contracts.py`
- Regenerate: `ai_caddie/contracts/generated.py`
- Regenerate: `mobile/ios/AICaddieDomain/GeneratedContracts.swift`
- Regenerate: `web_v2/src/contracts/generated.ts`
- Create: `server_v2/player_guidance_models.py`
- Create: `server_v2/player_guidance_model_repo.py`
- Create: `server_v2/guidance_model_provider.py`
- Modify: `server_v2/course_models.py`
- Modify: `server_v2/course_dependencies.py`
- Create: `migrations/versions/0012_player_guidance_model.py`
- Create: `tests/test_migration_0012_player_guidance_model.py`
- Create: `tests/test_player_guidance_model_repo.py`
- Create: `tests/test_guidance_model_provider.py`
- Create: `tests/guidance_player_model_fixtures.py`
- Modify: `tests/test_contract_codegen.py`
- Modify: `tests/test_mobile_contracts.py`
- Modify: `web_v2/src/contracts/generated.test.ts`
- Create: `mobile/ios/AICaddieDomain/Guidance/PlayerGuidanceModelStore.swift`
- Create: `mobile/ios/AICaddieDomainTests/PlayerGuidanceModelStoreTests.swift`

- [ ] **Step 1: Write failing durable-model, correction, restart, and lie tests**

```python
# tests/test_player_guidance_model_repo.py
from __future__ import annotations

import unittest

from server_v2.player_guidance_model_repo import PlayerGuidanceModelRepo
from tests.guidance_player_model_fixtures import PlayerGuidanceModelFixture


class PlayerGuidanceModelRepoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = PlayerGuidanceModelFixture.create()

    def tearDown(self) -> None:
        self.fixture.close()

    def test_builds_different_tee_fairway_and_rough_distributions(self) -> None:
        snapshot = self.fixture.repo().build_or_load(
            owner_account_id=self.fixture.account_id,
            player_id=self.fixture.player_id,
            policy=self.fixture.policy,
        )
        driver_tee = snapshot.require_club("club:driver", "tee")
        driver_rough = snapshot.find_club("club:driver", "rough")
        iron_rough = snapshot.require_club("club:iron7", "rough")
        self.assertIsNone(driver_rough)
        self.assertLess(iron_rough.center_along_m, snapshot.require_club("club:iron7", "fairway").center_along_m)
        self.assertGreater(driver_tee.sample_size, 0)

    def test_retraction_or_actual_club_correction_changes_source_and_model_id(self) -> None:
        before = self.fixture.repo().build_or_load(
            owner_account_id=self.fixture.account_id,
            player_id=self.fixture.player_id,
            policy=self.fixture.policy,
        )
        self.fixture.retract_admitted_shot()
        after = self.fixture.repo().build_or_load(
            owner_account_id=self.fixture.account_id,
            player_id=self.fixture.player_id,
            policy=self.fixture.policy,
        )
        self.assertNotEqual(before.source_projection_hash, after.source_projection_hash)
        self.assertNotEqual(before.model_snapshot_id, after.model_snapshot_id)

    def test_restart_loads_and_reverifies_exact_canonical_snapshot(self) -> None:
        first = self.fixture.repo().build_or_load(
            owner_account_id=self.fixture.account_id,
            player_id=self.fixture.player_id,
            policy=self.fixture.policy,
        )
        reopened = self.fixture.reopen_repo().load_verified(first.model_snapshot_id)
        self.assertEqual(reopened, first)
        self.fixture.tamper_canonical_model_bytes(first.model_snapshot_id)
        with self.assertRaisesRegex(ValueError, "player guidance model identity"):
            self.fixture.reopen_repo().load_verified(first.model_snapshot_id)

    def test_recovery_value_requires_consecutive_confirmed_outcomes(self) -> None:
        snapshot = self.fixture.repo().build_or_load(
            owner_account_id=self.fixture.account_id,
            player_id=self.fixture.player_id,
            policy=self.fixture.policy,
        )
        self.assertTrue(snapshot.recovery_model.available)
        self.fixture.break_consecutive_outcome_links()
        rebuilt = self.fixture.repo().build_or_load(
            owner_account_id=self.fixture.account_id,
            player_id=self.fixture.player_id,
            policy=self.fixture.policy,
        )
        self.assertFalse(rebuilt.recovery_model.available)
        self.assertEqual(rebuilt.recovery_model.reason_code, "guidance_recovery_model_missing")

    def test_bag_keeps_uncalibrated_clubs_and_uses_only_player_configured_carry_as_prior(self) -> None:
        bag = self.fixture.build_player_bag_snapshot()
        wood7 = bag.require_club("club:wood7")
        iron7 = bag.require_club("club:iron7")
        self.assertEqual(wood7.configured_carry_source, "catalog_default")
        self.assertEqual(iron7.configured_carry_source, "player_manual")
        self.assertFalse(hasattr(wood7, "guidance_prior"))
        self.assertFalse(hasattr(iron7, "guidance_prior"))
        joined = self.fixture.load_joined_guidance_models(bag_snapshot=bag)
        self.assertIsNone(joined.find_route_utility_model("club:wood7", "tee"))
        iron7_prior = joined.require_route_utility_model("club:iron7", "fairway")
        self.assertEqual(iron7_prior.center_along_m, iron7.configured_carry_m)
        self.assertIn("configured_carry_prior_used", iron7_prior.evidence_refs)
        self.assertFalse(iron7_prior.stochastic_eligible)

    def test_model_and_bag_ids_exclude_only_their_own_id_fields(self) -> None:
        first = self.fixture.build_live_round_config()
        self.fixture.mutate_model_covariance(first.model_snapshot_id)
        changed_model = self.fixture.build_live_round_config()
        self.assertNotEqual(first.model_snapshot_id, changed_model.model_snapshot_id)
        self.assertNotEqual(first.engine_bundle_id, changed_model.engine_bundle_id)
        self.assertNotEqual(first.live_round_package_id, changed_model.live_round_package_id)
        self.assertEqual(first.bag_snapshot_id, changed_model.bag_snapshot_id)
        self.fixture.change_manual_carry("club:iron7", 137.0)
        changed_bag = self.fixture.build_live_round_config()
        self.assertEqual(changed_model.model_snapshot_id, changed_bag.model_snapshot_id)
        self.assertNotEqual(changed_model.bag_snapshot_id, changed_bag.bag_snapshot_id)
        self.assertNotEqual(changed_model.live_round_package_id, changed_bag.live_round_package_id)

    def test_concurrent_identical_builds_converge_on_one_immutable_row(self) -> None:
        first, second = self.fixture.concurrent_builds()
        self.assertEqual(first.model_snapshot_id, second.model_snapshot_id)
        self.assertEqual(self.fixture.model_row_count(first.model_snapshot_id), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and verify the missing durable repository fails**

Run: `uv run python -m unittest tests.test_player_guidance_model_repo tests.test_guidance_model_provider -v`

Expected: FAIL because no strict model contract, durable row, source hash or production provider exists.

- [ ] **Step 3: Freeze distinct player-bag and learned-model contracts inside the pinned LiveRoundPackage**

Do not rename a learned model to `playerBagSnapshot`. The bag is the complete enabled club roster and configured carry source; the model is evidence-derived calibration/recovery data. `player_guidance_model_v1.schema.json` is an exact object with:

```json
{
  "schema": "ai-caddie-player-guidance-model-v1",
  "modelSnapshotId": "1111111111111111111111111111111111111111111111111111111111111111",
  "ownerAccountId": "account-a",
  "playerId": "player-a",
  "sourceProjectionHash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "calibrationPolicyVersion": "club-calibration-policy-v2",
  "recoveryPolicyVersion": "recovery-value-policy-v1",
  "clubModels": [{
    "clubRef": "club:iron7",
    "startLie": "rough",
    "sampleSize": 28,
    "centerAlongM": 132.0,
    "centerCrossM": -1.0,
    "covarianceXXM2": 81.0,
    "covarianceXYM2": 2.0,
    "covarianceYYM2": 36.0,
    "confidence": 0.68,
    "calibrationVersion": "2222222222222222222222222222222222222222222222222222222222222222",
    "evidenceRefs": ["event:11111111-1111-4111-8111-111111111111"]
  }],
  "pooledClubModels": [],
  "recoveryModel": {
    "available": true,
    "reasonCode": null,
    "valueVersion": "3333333333333333333333333333333333333333333333333333333333333333",
    "states": [{"lie":"rough","remainingBucketM":150,"expectedStrokes":2.8,"sampleSize":24}],
    "evidenceRefs": ["round:11111111-1111-4111-8111-111111111111"]
  }
}
```

`player_bag_snapshot_v1.schema.json` is a separate exact object:

```json
{
  "schema": "ai-caddie-player-bag-snapshot-v1",
  "bagSnapshotId": "4444444444444444444444444444444444444444444444444444444444444444",
  "ownerAccountId": "account-a",
  "playerId": "player-a",
  "sourceBagHash": "5555555555555555555555555555555555555555555555555555555555555555",
  "clubs": [{
    "clubRef": "club:iron7",
    "customName": null,
    "configuredCarryM": 132.0,
    "configuredCarrySource": "player_manual",
    "enabled": true
  }, {
    "clubRef": "club:wood7",
    "customName": null,
    "configuredCarryM": 155.0,
    "configuredCarrySource": "catalog_default",
    "enabled": true
  }]
}
```

The real schemas supply exact keys, finite bounds, sorted unique clubs, sorted unique `(clubRef,startLie)` and `(lie,remainingBucketM)` model rows, and forbid direct recovery-model presentation: `expectedStrokes` exists only inside the private planner model. D08a may project only the final selected combination expectation into its separately named nullable `averageStrokes`; it may never serialize an individual recovery row or probability. `configuredCarrySource` is exact `player_manual|provider_player_bag|catalog_default|unavailable`; only the first two may seed a clearly marked low-confidence configured-carry prior under D08b's pinned `configuredCarryPriorPolicy`. A `catalog_default` club remains visible/editable in the bag but cannot silently become personalized Guidance. A learned lie-specific model wins over any configured prior; no model and no eligible configured carry yields unavailable for that club rather than a hard-coded distance.

Freeze `guidance_engine_bundle_v1.schema.json` in this task, before any provider consumes it. Its exact root keys are `schema,engineBundleId,engineBuild,playerCalibrationSnapshot,supportedPlannerModes,maximumVisibleCombinations,maximumVisibleLegs,beamWidth,quadratureVersion,routeProjectionPolicy,positionStabilityPolicy,configuredCarryPriorPolicy,pooledModelCovarianceInflation,hazardSigmaGate,penaltyPolicy,guidanceModePolicy`. `schema` is the constant `ai-caddie-guidance-engine-bundle-v1`; `supportedPlannerModes` is sorted unique over `stochastic_expected_strokes_v1|calibrated_route_utility_v1`; visible combinations/legs are integers `1...3`, beam width is `1...64`, `quadratureVersion` is the exact supported enum, covariance inflation is finite `[1,10]`, and hazard sigma gate is finite `(0,10]`. `playerCalibrationSnapshot` is the exact full `PlayerGuidanceModelSnapshot/v1` `$ref`; no bag field or mutable model path is embedded.

The embedded policy objects are exact and identity-bearing through the enclosing `engineBundleId`; they do **not** mint additional unregistered typed IDs:

- `routeProjectionPolicy`: `policyVersion,maximumLateralOffsetM,minimumAmbiguityGapM,minimumSegmentLengthM,targetStationStepM`; non-empty version, finite `maximumLateralOffsetM ∈ (0,100]`, `minimumAmbiguityGapM ∈ [0,100]`, `minimumSegmentLengthM ∈ (0,100]`, `targetStationStepM ∈ [1,50]`.
- `positionStabilityPolicy`: `policyVersion,maximumHorizontalAccuracyM,maximumFixAgeSeconds,stationarySpeedMps,movingSpeedMps,stationaryDwellSeconds,hysteresisM,identityQuantizationM`; finite positive accuracy/age, `0 <= stationarySpeedMps < movingSpeedMps <= 20`, dwell `[0,60]`, hysteresis `(0,20]`, quantization `(0,hysteresisM]`.
- `configuredCarryPriorPolicy`: `policyVersion,allowedSources,alongSigmaM,crossSigmaM,confidence,stochasticEligible`; exact sorted sources `player_manual|provider_player_bag`, positive sigmas, confidence `(0,0.5]`, constant false eligibility.
- `penaltyPolicy`: `policyVersion,hardSafetyViolationPenalty,hazardTailWeight,crossVarianceWeight,distanceWeight,legCountWeight`; all weights finite non-negative and `hardSafetyViolationPenalty` strictly greater than the maximum sum of the other bounded terms, so unsafe candidates cannot win by tie-break accident.
- `guidanceModePolicy`: `allowedModes,defaultMode,tournamentBehavior,manualRequestBehavior,offBehavior,bigNumbersBehavior`; sorted-unique allowed modes, default contained in them and exact behavior enums `guidance_disabled|durable_one_shot|map_and_distances_only|distances_only`.

Every nested object uses `additionalProperties=false`; cross-field inequalities above are tested in all generated decoders. Unknown keys/versions fail decode.

Register `PlayerGuidanceSource/v1`, `PlayerBagSource/v1`, `PlayerGuidanceModelSnapshot/v1`, `PlayerBagSnapshot/v1` and `GuidanceEngineBundle/v1` with explicit included fields. Only `modelSnapshotId`, `bagSnapshotId` and `engineBundleId`, respectively, are excluded from their own identities; the engine entry includes every exact root field above except `engineBundleId`, with no wildcard. Builders form identity payloads without the self-ID, compute the typed ID, then attach it; hashing a root object that already contains its own ID is forbidden. `LiveRoundPackageV2.playerBagSnapshot` is a required `$ref` to the full `PlayerBagSnapshot/v1`, not an untyped object. The exact learned `PlayerGuidanceModelSnapshot/v1` is instead required as `GuidanceEngineBundleV1.playerCalibrationSnapshot`, matching authority §5.9's bag/config separation and its rule that the engine bundle carries player calibration. Track A's `LiveRoundPackage` wildcard identity binds both independently.

Add cross-language identity-mutation goldens: changing a club's configured carry/source or enabled roster changes `bagSnapshotId` and `liveRoundPackageId` but not the learned model ID; changing any learned mean/covariance/recovery state changes `modelSnapshotId`, `engineBundleId` and `liveRoundPackageId` but not `bagSnapshotId`; changing any other `guidanceEngineBundle` policy or later changing `shotRecoveryPolicy` also changes `liveRoundPackageId`. Changing only an ID field must fail verification rather than create a self-reference. Both iOS and Watch persist the raw LRP and re-decode/reverify the LRP, bag, engine-bundle and model IDs at startup.

Append stable Track D reason/evidence code `configured_carry_prior_used` to the generated registry and localization catalogs. It is diagnostic disclosure for an available low-confidence route-utility recommendation, not an unavailable reason and never appears for a learned model.

- [ ] **Step 4: Implement durable source projection, models, and invalidation**

```python
# server_v2/course_models.py
from sqlalchemy import DateTime, Index, LargeBinary, String, UniqueConstraint


class PlayerGuidanceModelRow(Base):
    __tablename__ = "player_guidance_model_v1"
    __table_args__ = (
        UniqueConstraint(
            "owner_account_id",
            "player_id",
            "source_projection_hash",
            "calibration_policy_version",
            "recovery_policy_version",
            name="uq_player_guidance_model_source_policy",
        ),
        Index(
            "ix_player_guidance_model_owner_player",
            "owner_account_id",
            "player_id",
        ),
    )
    model_snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    player_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_projection_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    calibration_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    recovery_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

```python
# migrations/versions/0012_player_guidance_model.py
from alembic import op
import sqlalchemy as sa

revision = "0012_player_guidance_model"
down_revision = "0011_device_course_authority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_guidance_model_v1",
        sa.Column("model_snapshot_id", sa.String(length=64), primary_key=True),
        sa.Column("owner_account_id", sa.String(length=128), nullable=False),
        sa.Column("player_id", sa.String(length=128), nullable=False),
        sa.Column("source_projection_hash", sa.String(length=64), nullable=False),
        sa.Column("calibration_policy_version", sa.String(length=64), nullable=False),
        sa.Column("recovery_policy_version", sa.String(length=64), nullable=False),
        sa.Column("canonical_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "owner_account_id",
            "player_id",
            "source_projection_hash",
            "calibration_policy_version",
            "recovery_policy_version",
            name="uq_player_guidance_model_source_policy",
        ),
    )
    op.create_index(
        "ix_player_guidance_model_owner_player",
        "player_guidance_model_v1",
        ["owner_account_id", "player_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_player_guidance_model_owner_player",
        table_name="player_guidance_model_v1",
    )
    op.drop_table("player_guidance_model_v1")
```

`tests/test_migration_0012_player_guidance_model.py` upgrades `0011 → 0012`, inspects the exact column lengths/nullability/PK/unique constraint/composite index, downgrades to `0011`, and verifies a second upgrade. It also checks the SQLAlchemy metadata is byte-for-byte equivalent in names, lengths, nullability, PK, unique constraints and indexes, rejects accidental per-column `index=True` indexes, verifies the pre-upgrade single head is exactly `0011_device_course_authority`, and proves no Plan 4 task renumbers Plan 1/2 migrations.

```python
# server_v2/player_guidance_model_repo.py
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert


class PlayerGuidanceModelRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def build_or_load(
        self,
        *,
        owner_account_id: str,
        player_id: str,
        policy: PlayerGuidanceModelPolicy,
    ) -> PlayerGuidanceModelSnapshot:
        source = authoritative_player_shot_projection_in_session(
            self.session,
            owner_account_id=owner_account_id,
            player_id=player_id,
        )
        source_hash = typed_id("PlayerGuidanceSource/v1", {
            "confirmedShots": source.confirmed_shot_facts,
            "actualClubs": source.actual_club_facts,
            "targets": source.explicit_target_facts,
            "corrections": source.correction_facts,
            "retractions": source.retraction_facts,
        })
        admitted = tuple(
            result.sample
            for fact in source.confirmed_shot_facts
            if (result := admit_calibration_sample(fact)).accepted
            and result.sample is not None
        )
        identity_body = build_player_guidance_model_identity_body(
            owner_account_id=owner_account_id,
            player_id=player_id,
            source_projection_hash=source_hash,
            samples=admitted,
            consecutive_outcomes=source.consecutive_outcomes,
            policy=policy,
        )
        identifier = typed_id("PlayerGuidanceModelSnapshot/v1", identity_body)
        payload = {**identity_body, "modelSnapshotId": identifier}
        canonical_bytes = canonical_json_bytes(payload)
        values = dict(
            model_snapshot_id=identifier,
            owner_account_id=owner_account_id,
            player_id=player_id,
            source_projection_hash=source_hash,
            calibration_policy_version=policy.calibration.version,
            recovery_policy_version=policy.recovery.version,
            canonical_bytes=canonical_bytes,
            created_at=datetime.now(timezone.utc),
        )
        dialect = self.session.get_bind().dialect.name
        if dialect == "postgresql":
            statement = postgresql_insert(PlayerGuidanceModelRow).values(
                **values
            ).on_conflict_do_nothing(index_elements=["model_snapshot_id"])
        elif dialect == "sqlite":
            statement = sqlite_insert(PlayerGuidanceModelRow).values(
                **values
            ).on_conflict_do_nothing(index_elements=["model_snapshot_id"])
        else:
            raise RuntimeError(f"unsupported player model CAS dialect: {dialect}")
        self.session.execute(statement)
        self.session.flush()
        row = self.session.get(PlayerGuidanceModelRow, identifier)
        if row is None or bytes(row.canonical_bytes) != canonical_bytes:
            raise ValueError("player guidance model identity collision")
        return self._verified(row)

    def load_verified(self, model_snapshot_id: str) -> PlayerGuidanceModelSnapshot:
        row = self.session.get(PlayerGuidanceModelRow, model_snapshot_id)
        if row is None:
            raise KeyError(model_snapshot_id)
        return self._verified(row)

    def _verified(self, row: PlayerGuidanceModelRow) -> PlayerGuidanceModelSnapshot:
        payload = strict_player_guidance_model_decode(bytes(row.canonical_bytes))
        identity_body = player_guidance_model_identity_body(payload)
        if (
            payload["modelSnapshotId"] != row.model_snapshot_id
            or typed_id("PlayerGuidanceModelSnapshot/v1", identity_body)
                != row.model_snapshot_id
        ):
            raise ValueError("player guidance model identity mismatch")
        return PlayerGuidanceModelSnapshot.from_payload(payload)
```

`authoritative_player_shot_projection_in_session()` reads canonical reducer output only. It joins a shot to its explicit actual-club fact, start lie, explicit/player-confirmed target and next confirmed shot origin; retracted/superseded Tee attempts never enter. The cache key deliberately excludes replication labels but includes every fact/correction/retraction that can change admission or outcome. A model row is immutable; invalidation creates a new row, and GC retains any row pinned by an active LRP/round. Repository tests execute concurrent identical builds on SQLite and on the required disposable PostgreSQL fixture, proving both dialect-native branches converge to one immutable row; unsupported dialects fail before mutation rather than silently falling back to a racy read-then-insert.

Calibration builds exact lie-specific groups first. A pooled club model is allowed only when its own sample gate passes; the route-utility planner may use it with the pinned engine policy's covariance inflation and explicit `pooled_model_used` evidence. The stochastic expected-strokes planner never substitutes pooled data for a missing lie transition. The player-bag snapshot builder reads the existing account-scoped effective bag through a strict adapter, preserves every enabled club even when uncalibrated, computes `sourceBagHash` through registered `PlayerBagSource/v1`, and computes `PlayerBagSnapshot/v1` over the ID-free bag body. Separately, the verified learned model is assigned to `GuidanceEngineBundleV1.playerCalibrationSnapshot` before that bundle ID is computed. No mutable file path, provider raw object or generic catalog ladder enters either LRP component.

- [ ] **Step 5: Implement the real server provider and local raw-byte store**

```python
# server_v2/guidance_model_provider.py
@dataclass(frozen=True)
class RepositoryPlayerGuidanceModelProvider:
    def load(
        self,
        session: Session,
        *,
        owner_account_id: str,
        player_id: str,
        pinned_player_bag: PlayerBagSnapshot,
        pinned_engine_bundle: GuidanceEngineBundleV1,
        current_lie: str,
    ) -> PlayerGuidanceModels:
        if (
            pinned_player_bag.owner_account_id != owner_account_id
            or pinned_player_bag.player_id != player_id
        ):
            raise PermissionError("player bag ownership mismatch")
        learned = PlayerGuidanceModelRepo(session).load_verified(
            pinned_engine_bundle.player_calibration_snapshot.model_snapshot_id
        )
        if learned != pinned_engine_bundle.player_calibration_snapshot:
            raise ValueError("pinned player guidance model mismatch")
        return PlayerGuidanceModels.from_bag(
            bag=pinned_player_bag,
            learned_model=learned,
            current_lie=current_lie,
            configured_prior_policy=pinned_engine_bundle.configured_carry_prior_policy,
        )
```

`PlayerGuidanceModels.from_bag(...)` joins the independently verified bag roster with the independently verified engine-bundle calibration snapshot, then selects a verified lie-specific learned model first. If absent, it may create a low-confidence mean at `configuredCarryM` only for `player_manual|provider_player_bag`, with zero cross bias and covariance/confidence from the exact pinned `configuredCarryPriorPolicy`; it emits `configured_carry_prior_used` evidence and is ineligible for stochastic expected-strokes mode. `catalog_default|unavailable` never creates a recommendation model. The bag remains complete so UI can show/edit an uncalibrated club without pretending it is recommendation-ready.

`course_dependencies()` constructs this concrete provider; D08a and D08b receive it, not a protocol-only lambda. `PlayerGuidanceModelStore.swift` persists the raw canonical `playerBagSnapshot` and `guidanceEngineBundle.playerCalibrationSnapshot` under `(accountId,liveRoundPackageId,bagSnapshotId,engineBundleId,modelSnapshotId)`, atomically writes then re-decodes, and clears on logout/account change. On restart it verifies the LRP/bag/engine/model typed IDs and their independent exact bytes before returning `VerifiedPlayerGuidanceModels`; no public initializer exists.

- [ ] **Step 6: Run repository → provider → restart tests**

Run:

```bash
uv run python tools/contracts/generate_contracts.py
uv run python -m unittest \
  tests.test_club_calibration tests.test_club_dispersion \
  tests.test_manual_club_bag tests.test_effective_club_ladder \
  tests.test_migration_0012_player_guidance_model \
  tests.test_player_guidance_model_repo tests.test_guidance_model_provider \
  tests.test_contract_codegen tests.test_mobile_contracts -v
swift test --filter 'PlayerGuidanceModelStoreTests'
npm --prefix web_v2 test -- --run src/contracts/generated.test.ts
```

Expected: PASS in Python、Swift and Web; this checkpoint regenerates and verifies the canonical-contracts source digest plus all three outputs before repository tests；actual-club correction/retraction changes the immutable model/engine/LRP IDs without changing the bag ID; Tee/fairway/rough distributions differ; all enabled uncalibrated clubs remain in the bag; only player/provider configured carry can create the explicitly low-confidence route-utility prior; catalog defaults never masquerade as personalized Guidance; concurrent identical builds converge; migration round-trips; restart reloads exact canonical bytes.

- [ ] **Step 7: Commit durable production player models**

```bash
git add contracts/canonical/player_bag_snapshot_v1.schema.json contracts/canonical/player_guidance_model_v1.schema.json contracts/canonical/guidance_engine_bundle_v1.schema.json contracts/canonical/live_round_package_v2.schema.json contracts/canonical/canonical_object_registry.json contracts/canonical/reason_codes.json tools/contracts/generate_contracts.py ai_caddie/contracts/generated.py mobile/ios/AICaddieDomain/GeneratedContracts.swift web_v2/src/contracts/generated.ts web_v2/src/contracts/generated.test.ts server_v2/player_guidance_models.py server_v2/player_guidance_model_repo.py server_v2/guidance_model_provider.py server_v2/course_models.py server_v2/course_dependencies.py migrations/versions/0012_player_guidance_model.py tests/guidance_player_model_fixtures.py tests/test_migration_0012_player_guidance_model.py tests/test_player_guidance_model_repo.py tests/test_guidance_model_provider.py tests/test_contract_codegen.py tests/test_mobile_contracts.py mobile/ios/AICaddieDomain/Guidance/PlayerGuidanceModelStore.swift mobile/ios/AICaddieDomainTests/PlayerGuidanceModelStoreTests.swift
git commit -m "feat: persist lie conditioned guidance models"
```

## Task D08: Build deterministic current-shot planning primitives

**Depends on:** D03–D07a. D08 defines pure internal primitives; D08b owns final local/offline composition, live position, route projection and planner selection.

**Files:**
- Create: `ai_caddie/guidance/caddie_engine.py`
- Create: `ai_caddie/guidance/planning_models.py`
- Test: `tests/test_caddie_guidance.py`
- Test: `tests/test_guidance_safety_boundaries.py`

- [ ] **Step 1: Write failing deterministic primitive tests**

Tests prove:

- all input lists are sorted by stable semantic keys before selection;
- no weather/wind field is accepted or read;
- club landing mean and covariance are finite, positive-semidefinite and lie-conditioned;
- `aimTarget`, `predictedLanding` and `shotFrameBearingDeg` are independent fields;
- the ellipse center is the predicted landing and its rotation is shot-frame bearing plus covariance eigen angle;
- hazard inputs use Tee-origin absolute stations and are converted from current route station before comparison;
- unavailable player/map/control input returns a stable reason, never a fabricated default club;
- internal utility/expected-value numbers never appear in a wire projection.

- [ ] **Step 2: Implement immutable planning values and exact tie-breaks**

```python
@dataclass(frozen=True)
class CurrentShotPlan:
    club_ref: str
    aim_target: AimTarget
    predicted_landing: PredictedLanding
    shot_frame_bearing_deg: float
    dispersion: GuidanceDispersion
    hazards: tuple[GuidanceHazard, ...]
    rationale: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class PlanningUnavailable:
    reason_code: str
    evidence_refs: tuple[str, ...]
```

The primitive library accepts only verifier-minted static products and D07a player models. It has no repository, HTTP, clock, GPS recorder or UI dependency. Exact tie-breaks end with `(clubRef,targetRef)`; request/dictionary order cannot change output.

- [ ] **Step 3: Add source-boundary tests**

Scan `ai_caddie/guidance` for wind/weather consumption, hard-coded Driver/3W defaults, target=green shortcuts, ellipse-at-target logic, probability output、any `expectedStrokes` output and Boolean capability availability. The exact D07a player-model decoder、private stochastic utility math and D08a's generated combination `averageStrokes` projection are explicitly allowlisted. No serializer、response mapper or app view model may copy an individual recovery value；only the final gated combination expectation may populate `averageStrokes`, and negative fixtures may contain forbidden strings only in an allowlisted test directory.

- [ ] **Step 4: Run and commit**

Run:

```bash
uv run python -m unittest tests.test_caddie_guidance tests.test_guidance_safety_boundaries -v
```

Expected: PASS with deterministic primitives and no fabricated fallback.

```bash
git add ai_caddie/guidance/caddie_engine.py ai_caddie/guidance/planning_models.py tests/test_caddie_guidance.py tests/test_guidance_safety_boundaries.py
git commit -m "feat: add deterministic guidance primitives"
```

## Task D08a: Freeze full-Caddie detail contracts and audit-only server parity

**Depends on:** D02 final Guidance wire, D08 planning primitives. D08a defines the detail plan and authenticated audit envelope; D08b supplies the production local engine and D08c supplies real providers/trust.

**Files:**
- Create: `contracts/canonical/caddie_plan_v1.schema.json`
- Create: `contracts/canonical/guidance_api_response_v1.schema.json`
- Create: `contracts/canonical/guidance_current_shot_request_v1.schema.json`
- Modify: `contracts/canonical/canonical_object_registry.json`
- Modify: `tools/contracts/generate_contracts.py`
- Regenerate: `ai_caddie/contracts/generated.py`
- Regenerate: `mobile/ios/AICaddieDomain/GeneratedContracts.swift`
- Regenerate: `web_v2/src/contracts/generated.ts`
- Create: `mobile/ios/AICaddieDomain/Guidance/GuidanceResponseDecoder.swift`
- Modify: `server_v2/guidance.py`
- Create: `server_v2/guidance_context_repo.py`
- Modify: `tests/test_contract_codegen.py`
- Test: `tests/test_caddie_plan_contract.py`
- Test: `tests/test_server_v2_guidance.py`
- Create: `tests/test_guidance_repository_provider.py`
- Test: `mobile/ios/AICaddieDomainTests/GuidanceResponseDecoderTests.swift`

- [ ] **Step 1: Write failing exact full-plan tests**

`CaddiePlanV1` exact root keys are `schema,planId,inputHash,entityRevisions,snapshotId,staticAuthorityHashes,plannerMode,generatedAt,validUntil,availability,reasonCodes,combinations,evidenceRefs`. `inputHash` is the same `GuidanceInput/v1` typed ID as D02 and `entityRevisions` is the identical sorted relevant-token roster; there is no parallel `guidanceInputVersion`. It exposes at most three sorted combinations. Each combination has exact `combinationId,rank,averageStrokes,legs,rationale,evidenceRefs`; each leg has exact `legIndex,clubRef,aimTarget,predictedLanding,shotFrameBearingDeg,dispersion,hazards,evidenceRefs` using D02's generated nested types. `averageStrokes` is an explicitly present nullable finite decimal in `[1,20]`: it is non-null for every visible combination only when `plannerMode=stochastic_expected_strokes_v1` and every D08b stochastic calibration/authority gate passed, and is null for every combination in `calibrated_route_utility_v1`. Mixed null/non-null lists, rounded strings and a value on an unavailable/empty plan are invalid.

`averageStrokes` is identity-bearing in both its combination and enclosing `planId`; changing the unrounded value changes both IDs. Python/Swift/TypeScript goldens use the same finite binary64 input and RFC 8785 bytes, while presentation rounds only after decode. The field is never recomputed by a client from legs、rationale or the private recovery table.

Tests reject:

- a whole-round `roundFactsVersion` substituted for the relevant `inputHash/entityRevisions`, any `GuidanceInputVersion/v1`, any `expectedStrokes` field, any probability, `averageStrokes` outside the exact combination slot/gate, fake confidence or a leg carrying only remaining distance;
- current-shot/full-plan disagreement in `inputHash`、`entityRevisions`、`snapshotId`、`staticAuthorityHashes`、`plannerMode`、`generatedAt`、`validUntil`、`availability` or `reasonCodes`; `generatedAt < validUntil` and both outputs have one identical freshness window;
- current-shot fields that differ from `combinations[0].legs[0]`;
- more than three visible legs/combinations, duplicate IDs/evidence, non-contiguous ranks/leg indexes or request-order-dependent output;
- an available current shot with unavailable/empty best plan, or an unavailable current shot with visible combinations.

- [ ] **Step 2: Freeze the response as local result plus optional online audit**

`GuidanceAPIResponseV1` exact root keys are `schema,currentShot,fullCaddie,runtimeCapabilityAudits,audit`. `runtimeCapabilityAudits` is a dictionary of strict D08b tokens used for online comparison/governance only. Empty/missing network audit never disables a locally verified map or Guidance result. `audit` carries server engine build, the server's canonical `roundFactsVersion` for traceability, input-hash match, relevant-entity-revision match, candidate-hash match and mismatch reason; it does not overwrite the local candidate or turn full-round revision into a local availability gate.

The authenticated server route is:

```text
POST /api/v2/guidance/current-shot/{roundId}
body = { hole, liveCurrentPosition, localCandidateHash?, localInputHash? }
```

`guidance_current_shot_request_v1.schema.json` freezes those exact keys: `hole` is the active round `scoreSlot`, `liveCurrentPosition` is the generated ephemeral value, and both local hashes are optional lowercase 64-hex values. When a local hash is absent, the corresponding audit match field is null/unknown rather than false; when present, the server compares it but never replaces the local result. The server authenticates `AccountContext.device_id`, reselects the exact current-device authority through D02c, treats `liveCurrentPosition` as non-persistent request input and runs the same engine bundle. It never uses the last `shot_recorded` as current GPS, never mints caller-consumable availability from a flat dictionary and never makes this endpoint a prerequisite for offline play.

`server_v2/guidance_context_repo.py` and `tests/test_guidance_repository_provider.py` are created in this task with the strict authenticated repository boundary and fixture-backed audit provider required by the route. D08b replaces fixture planning with the offline-first composition, and D08c replaces its elevation/trust fixture ports with production providers; those later tasks modify these already-created files rather than referring to nonexistent paths.

- [ ] **Step 3: Generate strict codecs and one shared decoder**

`GuidanceResponseDecoder` decodes generated types directly, rejects duplicate JSON keys/unknown fields, verifies current-shot/full-plan first-leg identity and preserves audit tokens as raw canonical bytes until D08b's verifier checks them. iOS and Watch share this decoder; neither app declares a parallel response DTO.

- [ ] **Step 4: Add parity and source-boundary tests**

Tests cover authenticated-device mismatch, role/subject token relabel, score-only fact irrelevance, non-persistent GPS, local/server candidate equality under the same canonical inputs, explicit audit mismatch without local candidate replacement, no-network behavior, stochastic combination `averageStrokes` parity, and route-utility all-null behavior. Add a source scan forbidding `runtimeCapabilities["map"]["factsVersion"]`, last-shot-as-GPS, protocol-only production providers, recovery-row leakage and any probability output.

- [ ] **Step 5: Run and commit**

Run:

```bash
uv run python tools/contracts/generate_contracts.py
uv run python -m unittest tests.test_contract_codegen tests.test_caddie_plan_contract tests.test_server_v2_guidance -v
swift test --filter GuidanceResponseDecoderTests
cd web_v2 && npm test -- --run src/contracts/generated.test.ts
```

Expected: PASS; the canonical-contracts source digest and all three generated outputs are byte-current in this checkpoint；detail/current-shot are one decision, server audit is optional, no output contains wind、probability or an `expectedStrokes` field, current-shot never carries AVG, and only a fully gated stochastic detail plan carries combination `averageStrokes`.

```bash
git add contracts/canonical/caddie_plan_v1.schema.json contracts/canonical/guidance_api_response_v1.schema.json contracts/canonical/guidance_current_shot_request_v1.schema.json contracts/canonical/canonical_object_registry.json tools/contracts/generate_contracts.py ai_caddie/contracts/generated.py mobile/ios/AICaddieDomain/GeneratedContracts.swift web_v2/src/contracts/generated.ts mobile/ios/AICaddieDomain/Guidance/GuidanceResponseDecoder.swift server_v2/guidance.py server_v2/guidance_context_repo.py tests/test_contract_codegen.py tests/test_caddie_plan_contract.py tests/test_server_v2_guidance.py tests/test_guidance_repository_provider.py mobile/ios/AICaddieDomainTests/GuidanceResponseDecoderTests.swift
git commit -m "feat: freeze caddie detail and audit contracts"
```

## Task D08b: Normalize to offline-first, route-aware local Guidance with S70 landing semantics

**Final integration law:** implementation must delete any pre-existing path that exposes `roundFactsVersion` as capability authority or relevant-input identity, mints server-only flat `runtimeCapabilities`, uses the last `shot_recorded` origin as current GPS, shares one Green target across clubs, draws covariance at the aim coordinate, hard-codes mode=`automatic`, or scores plans only by remaining distance. Track A's canonical `RoundFactsVersion/v1` projection/audit identity remains. None of the forbidden uses may remain as a fallback after D08b.

**Depends on:** D02c static authority; D07a player model bundle; Plan 2 local raw-byte `CourseStaticAuthorityVerifier`/latest-control projector and Plan 2-promoted route-bound hazard/elevation plus optional `guidance.playable-regions` products admitted from Plan 3 research candidates; Track A local canonical round projection and `LiveRoundPackageV2`.

**Files:**
- Modify: `contracts/canonical/guidance_v1.schema.json`
- Modify: `contracts/canonical/caddie_plan_v1.schema.json`
- Modify: `contracts/canonical/guidance_api_response_v1.schema.json`
- Create: `contracts/canonical/guidance_runtime_capability_token_v1.schema.json`
- Create: `contracts/canonical/fixtures/guidance/runtime_capability_token.json`
- Create: `contracts/canonical/live_current_position_v1.schema.json`
- Modify: `contracts/canonical/live_round_package_v2.schema.json`
- Modify: `contracts/canonical/canonical_object_registry.json`
- Modify: `contracts/canonical/reason_codes.json`
- Modify: `tools/contracts/generate_contracts.py`
- Regenerate: `ai_caddie/contracts/generated.py`
- Regenerate: `mobile/ios/AICaddieDomain/GeneratedContracts.swift`
- Regenerate: `web_v2/src/contracts/generated.ts`
- Create: `ai_caddie/guidance/map_geometry.py`
- Create: `ai_caddie/guidance/position_stability.py`
- Replace: `ai_caddie/guidance/caddie_engine.py`
- Create: `ai_caddie/guidance/multi_shot.py`
- Create: `ai_caddie/guidance/guidance_input.py`
- Create: `ai_caddie/guidance/stochastic_planner.py`
- Create: `ai_caddie/guidance/route_utility_planner.py`
- Create: `mobile/ios/AICaddieDomain/Guidance/LocalGuidanceCapabilityProjector.swift`
- Create: `mobile/ios/AICaddieDomain/Guidance/LiveCurrentPosition.swift`
- Create: `mobile/ios/AICaddieDomain/Guidance/PositionStabilityTracker.swift`
- Create: `mobile/ios/AICaddieDomain/Guidance/GuidanceInputIdentity.swift`
- Create: `mobile/ios/AICaddieDomain/Guidance/LocalGuidanceEngine.swift`
- Create: `mobile/ios/AICaddieDomain/Guidance/RoutePlanner.swift`
- Create: `mobile/ios/AICaddieDomain/Guidance/GuidanceModeStore.swift`
- Create: `mobile/ios/AICaddieDomain/Guidance/GuidanceFreshnessClock.swift`
- Create: `mobile/ios/AICaddieDomain/Guidance/GuidanceManualRequestAction.swift`
- Create: `mobile/ios/AICaddieDomain/Guidance/GuidanceRuntimeCapability.swift`
- Modify: `server_v2/guidance.py`
- Modify: `server_v2/guidance_context_repo.py`
- Modify: `tests/test_contract_codegen.py`
- Create: `tests/test_guidance_offline_authority.py`
- Create: `tests/test_live_current_position.py`
- Create: `tests/test_route_projection.py`
- Create: `tests/test_stochastic_caddie_planner.py`
- Create: `tests/test_route_utility_planner.py`
- Create: `tests/test_guidance_engine_bundle.py`
- Create: `tests/test_guidance_runtime_capability_token.py`
- Create: `tests/test_guidance_playable_regions.py`
- Create: `tests/test_guidance_first_leg_consistency.py`
- Create: `tests/guidance_planner_fixtures.py`
- Create: `mobile/ios/AICaddieDomainTests/OfflineGuidanceEngineTests.swift`
- Create: `mobile/ios/AICaddieDomainTests/PositionStabilityTrackerTests.swift`
- Create: `mobile/ios/AICaddieDomainTests/GuidanceModeStoreTests.swift`
- Create: `mobile/ios/AICaddieDomainTests/GuidanceFreshnessClockTests.swift`
- Create: `mobile/ios/AICaddieDomainTests/GuidanceManualRequestActionTests.swift`
- Create: `mobile/ios/AICaddieWatchTests/WatchOfflineGuidanceTimelineTests.swift`
- Create: `web_v2/src/contracts/guidanceRuntimeCapability.ts`
- Create: `web_v2/src/contracts/guidanceRuntimeCapability.test.ts`
- Modify: `web_v2/src/contracts/generated.test.ts`

- [ ] **Step 1: Write failing live-position, offline, landing-center, algorithm, and mode goldens**

```python
# tests/test_live_current_position.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from ai_caddie.guidance.guidance_input import LiveCurrentPosition
from ai_caddie.guidance.position_stability import PositionStabilityPolicy, PositionStabilityTracker
from tests.guidance_planner_fixtures import PlannerFixture


class LiveCurrentPositionTests(unittest.TestCase):
    def fix(self, second: int, *, speed: float, latitude: float = 22.2790) -> LiveCurrentPosition:
        return LiveCurrentPosition(
            latitude=latitude,
            longitude=114.162,
            horizontal_accuracy_m=4.0,
            observed_at=datetime(2026, 7, 18, 10, 0, second, tzinfo=timezone.utc),
            monotonic_sequence=second + 1,
            speed_mps=speed,
        )

    def tracker(self) -> PositionStabilityTracker:
        return PositionStabilityTracker(
            PositionStabilityPolicy(
                maximum_accuracy_m=20.0,
                stationary_speed_mps=0.7,
                moving_speed_mps=1.4,
                stationary_dwell_seconds=3.0,
                maximum_age_seconds=12.0,
            ),
            position_frame=PlannerFixture.verified_map_position_frame(),
        )

    def settled_identity(self, first_second: int, *, latitude: float):
        tracker = self.tracker()
        first = self.fix(first_second, speed=0.1, latitude=latitude)
        settled = self.fix(first_second + 4, speed=0.1, latitude=latitude)
        tracker.observe(first, now=first.observed_at)
        result = tracker.observe(settled, now=settled.observed_at)
        self.assertEqual(result.state, "stationary")
        self.assertIsNotNone(result.stable_identity)
        return result.stable_identity

    def test_tee_shot_origin_is_not_reused_after_walking_to_the_ball(self) -> None:
        tee_identity = self.settled_identity(0, latitude=22.2790)
        ball_identity = self.settled_identity(8, latitude=22.2808)
        self.assertNotEqual(ball_identity, tee_identity)

    def test_stationary_dwell_and_resume_hysteresis_prevent_jitter(self) -> None:
        tracker = self.tracker()
        for second, speed, expected in (
            (0, 5.0, "moving"),
            (1, 0.2, "settling"),
            (3, 0.1, "settling"),
            (4, 0.1, "stationary"),
            (5, 0.9, "stationary"),
            (6, 1.5, "moving"),
        ):
            value = self.fix(second, speed=speed)
            self.assertEqual(
                tracker.observe(value, now=value.observed_at).state,
                expected,
            )

    def test_stale_inaccurate_or_nonmonotonic_fix_is_not_guidance_input(self) -> None:
        now = datetime(2026, 7, 18, 10, 0, 12, tzinfo=timezone.utc)
        for changes in (
            {"horizontal_accuracy_m": 20.1},
            {"observed_at": now - timedelta(seconds=13)},
            {"monotonic_sequence": 0},
        ):
            with self.subTest(changes=changes):
                value = self.fix(0, speed=0.0)
                value = LiveCurrentPosition(**{**value.__dict__, **changes})
                result = self.tracker().observe(value, now=now)
                self.assertEqual(result.state, "ineligible")
                self.assertEqual(result.reason_code, "guidance_position_stale")
                self.assertIsNone(result.stable_identity)


if __name__ == "__main__":
    unittest.main()
```

```python
# tests/test_stochastic_caddie_planner.py
from __future__ import annotations

import unittest

from ai_caddie.guidance.caddie_engine import evaluate_local_guidance
from tests.guidance_planner_fixtures import PlannerFixture


class StochasticCaddiePlannerTests(unittest.TestCase):
    def test_safe_three_wood_beats_longer_unstable_driver(self) -> None:
        source = PlannerFixture.par5_tee(
            driver_cross_sigma_m=34.0,
            three_wood_cross_sigma_m=13.0,
            right_ob=True,
            promoted_regions=True,
            recovery_model=True,
        )
        result = evaluate_local_guidance(source)
        self.assertEqual(result.planner_mode, "stochastic_expected_strokes_v1")
        self.assertEqual(result.current_shot.recommended_club_ref, "club:3w")
        self.assertNotIn("expectedStrokes", result.current_shot.as_wire())
        self.assertNotIn("averageStrokes", result.current_shot.as_wire())
        self.assertTrue(
            all(
                combination.average_strokes is not None
                for combination in result.full_plan.combinations
            )
        )

    def test_route_utility_never_claims_average_strokes(self) -> None:
        result = evaluate_local_guidance(
            PlannerFixture.par5_tee(recovery_model=False, promoted_regions=False)
        )
        self.assertEqual(result.planner_mode, "calibrated_route_utility_v1")
        self.assertTrue(
            all(
                combination.average_strokes is None
                for combination in result.full_plan.combinations
            )
        )

    def test_rough_carry_loss_changes_the_selected_club(self) -> None:
        fairway = evaluate_local_guidance(PlannerFixture.par4_second_shot(current_lie="fairway"))
        rough = evaluate_local_guidance(PlannerFixture.par4_second_shot(current_lie="rough"))
        self.assertNotEqual(
            fairway.current_shot.recommended_club_ref,
            rough.current_shot.recommended_club_ref,
        )

    def test_par4_driver_aim_and_landing_are_not_the_green(self) -> None:
        result = evaluate_local_guidance(PlannerFixture.par4_tee())
        shot = result.current_shot
        self.assertEqual(shot.recommended_club_ref, "club:driver")
        self.assertNotEqual(shot.aim_target.target_ref, "route:green")
        self.assertLess(shot.aim_target.route_station_m, result.route_total_m)
        self.assertNotEqual(
            (shot.predicted_landing.latitude, shot.predicted_landing.longitude),
            (result.green.latitude, result.green.longitude),
        )

    def test_dogleg_layup_forced_carry_bunker_and_ob_goldens(self) -> None:
        cases = {
            "dogleg": (PlannerFixture.dogleg_par4(), "club:3w"),
            "layup": (PlannerFixture.par5_layup(), "club:iron5"),
            "forced-carry": (PlannerFixture.forced_carry(), "club:driver"),
            "bunker": (PlannerFixture.greenside_bunker(), "club:wedge"),
            "ob": (PlannerFixture.narrow_ob(), "club:3w"),
        }
        for name, (source, club) in cases.items():
            with self.subTest(name=name):
                self.assertEqual(
                    evaluate_local_guidance(source).current_shot.recommended_club_ref,
                    club,
                )

    def test_par3_par4_par5_checked_in_goldens_are_deterministic(self) -> None:
        for fixture in (
            PlannerFixture.par3(), PlannerFixture.par4_tee(), PlannerFixture.par5_tee(),
        ):
            first = evaluate_local_guidance(fixture)
            second = evaluate_local_guidance(fixture.reordered_inputs())
            self.assertEqual(first.as_wire(), second.as_wire())


if __name__ == "__main__":
    unittest.main()
```

```python
# tests/test_guidance_first_leg_consistency.py
class GuidanceFirstLegConsistencyTests(unittest.TestCase):
    def test_current_shot_is_exactly_the_best_full_plan_first_leg(self) -> None:
        value = evaluate_local_guidance(PlannerFixture.par5_tee())
        self.assertTrue(value.full_plan.combinations)
        first = value.full_plan.combinations[0].legs[0]
        shot = value.current_shot
        self.assertEqual(first.club_ref, shot.recommended_club_ref)
        self.assertEqual(first.aim_target, shot.aim_target)
        self.assertEqual(first.predicted_landing, shot.predicted_landing)
        self.assertEqual(first.dispersion, shot.dispersion)
```

```swift
// mobile/ios/AICaddieWatchTests/WatchOfflineGuidanceTimelineTests.swift
func testOfflineRoundKeepsMapAndRecomputesGuidanceAcrossFactsAndRestart() async throws {
    var runtime = try OfflineGuidanceHarness.installedAndPinned()
    try runtime.disableNetwork()
    try await runtime.startRound()
    XCTAssertNotNil(try await runtime.stationaryGuidance(hole: 1))

    try await runtime.appendScoreOnly(hole: 1, strokes: 4)
    XCTAssertEqual(runtime.mapAuthorityState, .available)
    XCTAssertEqual(try await runtime.stationaryGuidance(hole: 1)?.inputHash,
                   runtime.lastInputHash) // score is irrelevant to GuidanceInput/v1

    try await runtime.walkToBall(latitude: 22.2808, longitude: 114.162)
    let moved = try await runtime.stationaryGuidance(hole: 1)
    XCTAssertNotEqual(moved?.inputHash, runtime.initialInputHash)
    XCTAssertNotEqual(moved?.aimTarget, runtime.initialAimTarget)

    runtime = try runtime.restartOffline()
    XCTAssertEqual(runtime.mapAuthorityState, .available)
    XCTAssertNotNil(try await runtime.stationaryGuidance(hole: 2))
}
```

- [ ] **Step 2: Run and verify old server/facts/shared-target paths fail**

Run:

```bash
uv run python -m unittest \
  tests.test_live_current_position tests.test_route_projection \
  tests.test_stochastic_caddie_planner tests.test_route_utility_planner \
  tests.test_guidance_first_leg_consistency tests.test_guidance_offline_authority -v
swift test --filter 'OfflineGuidanceEngineTests|PositionStabilityTrackerTests|GuidanceModeStoreTests|WatchOfflineGuidanceTimelineTests'
```

Expected: FAIL because no local engine/static projector/live-position/stationarity path exists and current D08 draws every club at one injected green target.

- [ ] **Step 3: Bind the final Guidance wire to relevant input and LiveRoundPackage policy**

D02's final `GuidanceEnvelopeV1` and D08a's `CaddiePlanV1` are the only output contracts. Preserve Track A's generated `RoundFactsVersion` canonical/audit type, but delete every use of it as capability authority or local relevant-input key. Do not create `GuidanceInputVersion/v1`. `GuidanceInput/v1` binds only:

```python
# ai_caddie/guidance/guidance_input.py
@dataclass(frozen=True)
class GuidanceRelevantFacts:
    hole_subject_ref: str
    live_position: LiveCurrentPosition
    stable_position: GuidanceStablePositionIdentity
    current_lie: str
    explicit_shot_target: tuple[float, float] | None
    player_flag: tuple[float, float] | None
    guidance_mode: str
    manual_request_id: str | None
    player_bag_snapshot_id: str
    player_model_snapshot_id: str
    engine_bundle_id: str
    static_authority_hashes: tuple[str, ...]
    effective_control_hash: str

    def canonical_payload(self) -> dict[str, object]:
        return {
            "holeSubjectRef": self.hole_subject_ref,
            "livePosition": self.stable_position.canonical_payload(),
            "currentLie": self.current_lie,
            "explicitShotTarget": self.explicit_shot_target,
            "playerFlag": self.player_flag,
            "guidanceMode": self.guidance_mode,
            "manualRequestId": self.manual_request_id,
            "playerBagSnapshotId": self.player_bag_snapshot_id,
            "playerModelSnapshotId": self.player_model_snapshot_id,
            "engineBundleId": self.engine_bundle_id,
            "staticAuthorityHashes": list(self.static_authority_hashes),
            "effectiveControlHash": self.effective_control_hash,
        }


def guidance_input_hash(value: GuidanceRelevantFacts) -> str:
    return typed_id("GuidanceInput/v1", value.canonical_payload())
```

`GuidanceStablePositionIdentity` is emitted by `PositionStabilityTracker` only after freshness/accuracy/dwell gates. Its exact identity fields are `positionFrameHash,quantizedEastIndex,quantizedNorthIndex,accuracyBucket`; indices are safe integers computed with the pinned `identityQuantizationM`, and the local engine plans from the corresponding quantized coordinate. Raw `observedAt`, `monotonicSequence`, instantaneous speed and sub-cell GPS jitter remain eligibility evidence and never enter `GuidanceInput/v1`. Two fresh stationary fixes in the same cell/bucket therefore produce the same input/candidate, while a material cell move or worse accuracy bucket changes `inputHash`.

Score, total strokes, putts, prior-hole edits, sync cursors, outbox state and unrelated holes are absent. Material stable position, classified/confirmed lie, Touch Target, flag, player-bag snapshot, player model, engine bundle, mode or signed control changes `inputHash`. The Guidance/Caddie wire also carries the exact sorted relevant `EntityRevisionToken` roster used to build this payload, so audit can prove which durable facts were read without making unrelated round facts an invalidation dependency. Tests mutate only configured carry/enabled roster and require a new `inputHash` even when the learned model is byte-identical; separate tests advance only timestamp/sequence in one stable cell and require an unchanged hash.

Consume D07a's already-generated, required `LiveRoundPackageV2.guidanceEngineBundle`; D08b implements the frozen `GuidanceEngineBundleV1` keys without redefining its schema or registry identity:

```text
schema
engineBundleId
engineBuild
playerCalibrationSnapshot
supportedPlannerModes
maximumVisibleCombinations
maximumVisibleLegs
beamWidth
quadratureVersion
routeProjectionPolicy
positionStabilityPolicy
configuredCarryPriorPolicy
pooledModelCovarianceInflation
hazardSigmaGate
penaltyPolicy
guidanceModePolicy
```

`playerCalibrationSnapshot` is the exact D07a `PlayerGuidanceModelSnapshot/v1` object and is independent of `LiveRoundPackageV2.playerBagSnapshot`. D08b re-verifies D07a's registry entry has `includedFields` equal to every exact key above except `engineBundleId`, and `excludedFields` equal to the one-element array `['engineBundleId']`; wildcard fields and a missing registry entry fail the registry test. Every embedded policy must match D07a's exact keys, bounds and cross-field rules; no nested typed-ID domain exists. An eligible configured-carry prior can seed only route-utility Guidance for an enabled club whose pinned bag has an eligible configured carry; it never upgrades `catalog_default` or a missing distance. Unknown engine/planner/quadrature/policy versions fail closed. Add negative tests for a missing bundle, a self-referential/manual bundle hash, hard-coded production mode, forbidden weather/wind, mode not allowed by the package, duplicate modes, configured-prior source escalation, bag/model ownership mismatch, bundle ID/body mismatch, a learned-model mutation that fails to change `modelSnapshotId`, `engineBundleId` and `liveRoundPackageId` while leaving `bagSnapshotId` unchanged, and any other engine-bundle mutation that fails to change `liveRoundPackageId`.


- [ ] **Step 4: Implement local static capability projection and complete audit token**

```swift
// mobile/ios/AICaddieDomain/Guidance/LocalGuidanceCapabilityProjector.swift
public struct VerifiedLocalGuidanceCapability: Sendable, Equatable {
    public let capability: String
    public let capabilityId: String
    public let subjectRef: String
    public let qualityReportId: String
    public let staticCourseAuthorityHash: String
    public let staticCapabilityAuthorityHash: String
    public let effectiveControlHash: String
    public let productBodyHash: String
    public let productBody: JSONValue
    public let assets: [VerifiedGuidanceAssetAuthority]
}

public enum LocalGuidanceCapabilityProjector {
    public static func project(
        activeRound: VerifiedActiveRoundCourseAuthority,
        subjectRef: String,
        capability: String
    ) throws -> VerifiedLocalGuidanceCapability {
        let installed = activeRound.authority
        let authority = installed.staticAuthority
        let record = installed.installRecord
        let localPin = activeRound.localPin
        let control = activeRound.effectiveControl
        guard record.pinCount > 0,
              record.installedManifestId == localPin.installManifestId,
              record.snapshotId == localPin.snapshotId,
              record.staticAuthorityHash == authority.staticAuthorityHash,
              authority.payload.installManifestId == record.installedManifestId,
              authority.payload.snapshotId == record.snapshotId,
              control.canContinueActiveRound,
              (capability == "map" ? control.mapEnabled : control.guidanceEnabled)
        else { throw GuidanceRuntimeCapabilityError.authority }
        return try authority.verifyGuidanceCapability(
            capability: capability,
            subjectRef: subjectRef
        )
    }
}
```

The client persists raw signed static bundle/manifest/snapshot/quality/assets/controls and re-verifies after every restart; it never persists the verifier-only value. Every active-round projection must call `CourseInstallFileAuthorityStore.loadVerifiedActiveRound(...)` again, which jointly loads the latest `InstallRecord`、`DurableActiveRoundPin` and release mutations, requires `pinCount > 0`, and validates the optional `RoundPinAuthorityAttestation` when present. Passing a cached `LocalRoundInstallPin` or old attestation directly is forbidden. A locally committed durable pin may keep an offline round usable before the server pin ACK returns；once a server attestation exists it must match exactly, and a released pin always fails closed. Sync order is install ACK prepared→verified, server pin authority, then the unchanged queued `round_started` bytes.

Online responses may include `runtimeCapabilityAudits`, but these are audit/online-enhancement evidence and never a prerequisite for local map or caddie. D08b freezes `guidance_runtime_capability_token_v1.schema.json`, registers `GuidanceRuntimeCapabilityToken/v1`, regenerates all languages and changes `GuidanceAPIResponseV1.runtimeCapabilityAudits` to a strict capability-name dictionary whose value is the generated token—not an untyped object. The exact root keys are `schema,capability,capabilityId,subjectRef,qualityReportId,staticCourseAuthorityHash,staticCapabilityAuthorityHash,effectiveControlHash,snapshotId,round,install,assets,product,availability,reasonCodes,tokenHash`; exact nested keys are:

- `round`: `ownerAccountId,canonicalRoundId,activeSources,semanticBindingHash,selectedSourceOrdinal,selectedSourceRoundId,activePinEventIdentity,activePinEventHash,activePinGeneration`;
- `install`: `deviceId,credentialId,profileId,securityDomainId,installManifestId,installAckId,installInstanceId,installAckGeneration`;
- each sorted-unique `assets[]` row: `role,logicalBindingHash,sha256,byteDomain,size,mediaType,schema,manifestRequirement`;
- `product`: `role,bodyHash,canonicalBody`.

`availability` is `available|unavailable`; available requires empty reasons and an exact product, unavailable requires a sorted-unique non-empty reason roster and null product body according to the schema branch. `tokenHash=typed_id("GuidanceRuntimeCapabilityToken/v1", payloadWithoutTokenHash)`. The registry `includedFields` is every root field except `tokenHash`, with `excludedFields=['tokenHash']`; missing registration, wildcard projection, extra nested keys and a dictionary key unequal to the token's `capability` all fail. Swift and Web strict verifiers recompute every nested identity, require every blob in `InstallRecord.installedAssetRefs`, reject dictionary-key relabel, cross-hole subject swaps, role swaps and same-blob/different-quality swaps. The server token records the one selected active member pin plus the complete frozen source roster；it never invents one pin ID per merged source.

- [ ] **Step 5: Implement live position and stationarity without writing ledger facts**

```swift
// mobile/ios/AICaddieDomain/Guidance/LiveCurrentPosition.swift
public struct LiveCurrentPosition: Codable, Equatable, Sendable {
    public let latitude: Double
    public let longitude: Double
    public let horizontalAccuracyM: Double
    public let observedAt: Date
    public let monotonicSequence: UInt64
    public let speedMps: Double
}
```

Python and Swift expose the same tracker boundary (language naming adjusted only by convention):

```text
PositionStabilityTracker(policy, position_frame)
  .observe(position, now) -> {
    state: moving|settling|stationary|ineligible,
    reasonCode: string?,
    stableIdentity: GuidanceStablePositionIdentity?
  }
```

`LiveCurrentPosition` is a strict ephemeral RuntimeFact value only and exposes no raw-fix identity or eligibility method. Watch/iPhone must pass every raw fix through `PositionStabilityTracker.observe(...)`, whose exact result states are `moving|settling|stationary|ineligible` and whose only identity-bearing output is optional `stable_identity`. The online endpoint consumes D08a's one generated strict body `{hole,liveCurrentPosition,localCandidateHash?,localInputHash?}`; server authenticates device and does not persist the observation. Missing optional hashes produce unknown audit comparisons. `shot_recorded` remains only the position at which a confirmed shot was struck. Walking 200 m after the Tee shot changes distance/recommendation before another shot event exists.

`PositionStabilityTracker` uses pinned engine-bundle values for maximum accuracy/age, stationary and moving speed thresholds, dwell and hysteresis. While walking/cart moving, big-number front/middle/back distance may update from GPS, but Caddie recommendation is absent with `guidance_position_moving`; after stationary dwell it recomputes once. It projects the accepted fix into the verified map ENU frame, creates `GuidanceStablePositionIdentity`, and the planner uses that canonical cell center. GPS jitter inside the same hysteresis cell/accuracy bucket does not churn `inputHash`; raw time/sequence still prove freshness/monotonicity but are excluded from identity. Stale/inaccurate/nonmonotonic fixes yield `guidance_position_stale` and never fall back to shot origin.

- [ ] **Step 6: Implement verified route projection, aim point, and predicted landing**

```python
# ai_caddie/guidance/map_geometry.py — final runtime primitives
@dataclass(frozen=True)
class RouteProjection:
    segment_index: int
    station_m: float
    remaining_to_green_m: float
    lateral_offset_m: float
    projection_latitude: float
    projection_longitude: float
    ambiguity_gap_m: float


@dataclass(frozen=True)
class AimTarget:
    target_ref: str
    latitude: float
    longitude: float
    route_station_m: float
    base_horizontal_distance_m: float


@dataclass(frozen=True)
class PredictedLanding:
    latitude: float
    longitude: float
    route_station_m: float | None
    along_m: float
    cross_m: float


def project_current_ball_to_route(
    geometry: VerifiedMapGeometry,
    position: LiveCurrentPosition,
    policy: RouteProjectionPolicy,
) -> RouteProjection:
    candidates = project_to_every_enu_segment(geometry, position)
    best, second = sorted(candidates, key=lambda row: (
        row.lateral_offset_m, row.segment_index,
    ))[:2]
    if best.lateral_offset_m > policy.maximum_lateral_offset_m:
        raise RouteProjectionError("guidance_route_offset_exceeded")
    if (
        not segments_are_adjacent(best.segment_index, second.segment_index)
        and second.lateral_offset_m - best.lateral_offset_m
        < policy.minimum_ambiguity_gap_m
    ):
        raise RouteProjectionError("guidance_route_projection_ambiguous")
    return best
```

The map body's dual station values are builder-owned route stationing, not request-time geodesics. Tee is `(0,total)`, green `(total,0)`, each sum differs from total by at most `0.5 m`, and order is `(distanceFromTeeM,targetRef)`. Runtime interpolation stays on the verified polyline. Backward shots are legal and may lower station; no “always progressing” clamp exists. An adjacent-fairway/off-route ball keeps the static map visible, but automatic Caddie fails closed until an unambiguous projection or explicit Touch Target exists.

For each club/aim candidate, define the shot frame from live ball to aim. `predictedLanding` is the calibrated `centerAlongM/centerCrossM` projected in that frame; its route station is a separate re-projection when unambiguous. The covariance ellipse is centered at `predictedLanding` and rotated by `shotFrameBearingDeg + covarianceEigenAngle`; it is never centered at the green or raw aim coordinate.

- [ ] **Step 7: Consume exact playable regions and implement the two-level planner**

The optional promoted product role is exactly `guidance.playable-regions`. Its canonical body has exact root keys:

```text
schema = ai-caddie-playable-regions-v1
layoutRevisionId
holeGlobalId
subjectRef
mapGeometryHash
mapGeometryEnvelope
horizontalCrs = local-enu-wgs84-v1
horizontalUnit = meter
registrationResidualM
maximumRegistrationResidualM
sourceInventoryEvidenceHash
topologyEvidenceHash
coverageEvidenceHash
regions
evidenceRefs
```

Each region exact keys are `regionRef,lieKind,rings,evidenceRefs`; `lieKind=fairway|rough|bunker|green|penalty_area|out_of_bounds`. Each ring exact keys are `ringRef,ringRole,points`; `ringRole=outer|hole`, point exact `eastM,northM`. Canonical order is regions/rings/points as defined by Plan 3; rings are explicitly closed, simple and non-degenerate, outer rings CCW, holes CW and strictly inside their outer. Across different regions, point contact and an oppositely oriented shared boundary are legal；proper crossing、strict containment、same-direction shared boundary、identical polygon and differently segmented coincident polygon all prove interior overlap and fail admission. Any point on an outer/hole/shared boundary or matching multiple strict interiors is runtime `unavailable`, never list-order winner. `mapGeometryEnvelope`、`sourceInventoryEvidenceHash`、subject/map hash/topology/registration/coverage evidence must match the current map authority and the independently frozen pre-projection source inventory. Admission uses the stricter of the body's `maximumRegistrationResidualM` and signed quality policy `maximum_playable_region_registration_residual_m`; the Plan 2 production gate is at most `3.0 m`.

Consume only:

```text
VerifiedPlayableRegionProvider.query(
  authority: VerifiedCourseStaticAuthority,
  subject_ref: str,
  expected_map_geometry_hash: str,
  point: WGS84Point
) -> VerifiedLieRegion | unavailable

VerifiedPlayableRegionProvider.covers_landing_window(
  authority: VerifiedCourseStaticAuthority,
  subject_ref: str,
  expected_map_geometry_hash: str,
  landing_window: LandingWindow
) -> bool
```

Boundary ambiguity, topology gap, uncovered landing window, identity mismatch or residual failure is unavailable; Track D never invents a region or recovery probability.

`stochastic_expected_strokes_v1` is enabled only when all are verified for the current device/subject/map hash:

- complete playable-region coverage for every evaluated landing window;
- lie-specific club landing distributions for the current lie;
- lie/remaining-distance recovery value model meeting D07a sample gates;
- `playsLike.elevation` query coverage for current and aim points;
- evidence-backed hazard product, where a verified empty set is valid;
- round penalty policy and deterministic quadrature version from the pinned engine bundle.

Use fixed 3×3 Gauss-Hermite quadrature over each 2D landing covariance. Transform every sample into the shared ENU frame, classify it against promoted playable/hazard/OB regions, apply penalty/replay/drop transitions and evaluate private `1 + penalty + V(nextLie,remainingBucket)`. Search route/explicit-target aim candidates with deterministic beam/DP; sort exact `(expectedValue,riskTail,finalRemaining,clubRefs,targetRefs,combinationId)`. Individual state values、sample probabilities and tail components never leave the engine. Only after the full stochastic gate succeeds, the final expected value of each selected visible combination is copied once into D08a's `averageStrokes`; canonical identity uses the unrounded finite value and UI rounds to one decimal.

If any stochastic prerequisite is absent but route, evidence-backed hazard product, current lie and calibrated/inflated 2D club models remain verified, use `calibrated_route_utility_v1` with exact sort `(hardSafetyViolation,expectedRemainingStation,hazardTailPenalty,crossVariance,totalLegs,clubRefs,targetRefs)`. An eligible configured-carry prior from D07a is allowed only in this mode, carries stable evidence/reason `configured_carry_prior_used`, and can never satisfy stochastic recovery/lie-transition gates. The route-utility mode sets every combination `averageStrokes=null` and does not claim expected strokes or playable-surface outcome probabilities. If those calibrated prerequisites are also incomplete, Caddie is unavailable; verified map, big-number distances and explicit manual Touch Target remain usable.

Both planners produce one sorted combination list. `currentShot` is constructed only by copying `combinations[0].legs[0]`; no separate closest-carry selector exists.


- [ ] **Step 8: Implement pinned modes and durable one-shot manual request**

The generated `LiveRoundPackageV2.guidanceEngineBundle.guidanceModePolicy` is the only production mode policy. Each device's `GuidanceModeStore` persists the player's per-round selected mode plus one device-local manual-request slot per current base context `(runtimeDeviceId,roundId,roundIncarnationId,holeSubjectRef,staticAuthorityHash,inputGeneration)`. The slot has exact keys `{requestId,attemptGeneration,runtimeDeviceId,roundId,roundIncarnationId,holeSubjectRef,staticAuthorityHash,createdAt,inputGeneration,state,resultInputHash,resultEnvelopeB64u,resultPlanB64u,resultHash,lastFailureCode,consumedAt,cancelledAt}`. `attemptGeneration` is a positive safe integer that is monotonic inside that base context；an operational retry reuses it and the exact request ID, while a freshness-expired/cancelled slot may advance it and mint a new request ID only after the current position becomes freshly eligible again. `state` is `prepared|computing|retryable_failed|completed|cancelled`; every result/failure/time field is present as JSON null until its state permits a value. Completed available **or unavailable** output stores the exact canonical generated `GuidanceEnvelopeV1` and `CaddiePlanV1` bytes plus a SHA-256 over their length-delimited bytes. The pair must have identical `inputHash/generatedAt/validUntil`, and restart on that device displays the same bytes only while `generatedAt <= effectiveNow < validUntil`；it never silently recomputes or republishes an expired recommendation. This local settings/result slot is not a round fact、actual-club fact、cross-device message or second Guidance wire contract.

`GuidanceFreshnessClock` is the sole production clock for that comparison and is injected into `GuidanceCoordinator`、`GuidanceModeStore` and `GuidanceManualRequestAction`. The mode store persists one exact device-local high-water row `{runtimeDeviceId,highWaterAt}`. At cold start, the clock compares the injected UTC wall time and the latest locally verified Plan 2 trusted-time floor with that high-water；if both are earlier, it fails closed as `guidance_time_untrusted`, publishes no recommendation and starts no compute until credible time catches up or a newer signed trusted-time floor arrives. Otherwise `effectiveNow` is the maximum of current wall time、trusted-time floor、launch anchor plus monotonic elapsed time and the persisted high-water, and the new high-water is durably stored before any result publication. A forward jump expires results immediately；a backward jump、restart or replay can never move effective time backward or reanimate bytes. HTTP receipt time and server availability are never freshness authority. Add `guidance_time_untrusted` to the generated reason-code registry and localize it without exposing the raw code.

Both iOS and Watch compile and consume the same source-level projection/action **implementation contract**；each process instantiates its own actor/store:

```swift
public enum GuidanceManualRequestPresentation: Equatable, Sendable {
    case hidden
    case ready(label: String)
    case requesting(label: String)
    case retryableFailure(label: String, localizedMessage: String)
    case resultUnavailable(localizedMessage: String)
    case resultAvailable
}

public protocol GuidanceManualRequestAction: Sendable {
    func presentation(
        for context: GuidanceManualRequestContext,
        currentShot: GuidanceEnvelopeV1?
    ) async throws -> GuidanceManualRequestPresentation

    func requestOrRetry(
        for context: GuidanceManualRequestContext
    ) async throws
}
```

`GuidanceManualRequestContext` is a `Sendable` value containing only the verified current runtime device、round/incarnation、hole subject、static authority hash、input generation、decoded mode policy and that process's D09 local-engine closure；the closure is `@Sendable` and captures only immutable verified inputs. The sole production implementation of `GuidanceManualRequestAction` is an actor over the process-local injected `GuidanceModeStore`; iPhone and Watch each own one actor instance because they are separate processes and Watch must work with no phone. No Swift actor、closure or mutable request/result object crosses WatchConnectivity. Both instances run the same generated state machine/golden fixtures, and neither view may instantiate a surface-owned action. The action calls `GuidanceModeStore.requestOrReuseAtomically(...)`; views cannot supply a request ID、result or club. The store serializes concurrent taps on that device and returns the same durable request. The action then marks `computing`, invokes the local engine with that exact `manualRequestId`, verifies the returned `inputHash`/device/authority/round/hole/generation, and atomically stores exact result bytes + `completed/consumedAt`. A process death in `prepared|computing|retryable_failed` resumes the same logical request ID；an operational failure records a stable internal failure code and exposes only localized “重试建议”, whose tap reuses that request. A deterministic unavailable engine result is a completed result, renders its localized reason and cannot spin on repeated taps for the same input generation.

- `automatic`: stationary eligible position automatically computes;
- `manual`: distance/map facts remain. With no current-generation result, both roots show `ready(label:"获取球童建议")`; tap creates/reuses the durable request, `requesting` disables duplicate taps and shows progress, `resultAvailable` replaces the CTA with the normal recommended-club chip, and `resultUnavailable` shows the stable reason until relevant input changes;
- `off`: no caddie layer;
- `big_numbers`: distances only, no recommendation;
- `tournament`: fail closed locally and server-side, never constructs a candidate even if a stale request/token exists.

The selected mode—not a live request/result—may sync through the existing account setting as exact `{roundIncarnationId,mode,modeGeneration,originDeviceId}`. Each device increments `modeGeneration` above its highest observed value；merge chooses maximum `(modeGeneration,originDeviceId)` so offline concurrent mode choices converge deterministically, while absence of phone/network never blocks local selection. An accepted mode-setting change advances the local `inputGeneration` before projection. Manual request/result records survive restart only on their originating device and are never synced、peer-transferred or used as authority by the other device, because their GPS/input/installed-authority context is device-local. WatchConnectivity may relay the exact mode-setting bytes and signed course/engine authority bytes, never an actor or pending/result cache.

Runtime-device、hole、mode、input-generation or authority change atomically cancels any unconsumed local request before accepting a result and clears a completed stale projection；late completion for that cancelled request ID/attempt is rejected without replacing the new root state. Freshness expiry is equally strict: before either root publishes a stored result, the coordinator/action decode both canonical outputs and compare their identical window with `effectiveNow`. At `effectiveNow >= validUntil`, the store atomically changes the slot to `cancelled`, clears its result/failure bytes, persists `cancelledAt`, removes `currentShot/fullCaddie/PlaysLike` from presentation and resets position eligibility to `settling`. No CTA appears from the expired fix. Only a later raw position observation that passes freshness、accuracy、monotonicity and stationary dwell may re-establish eligibility；it may remain in the same quantized cell and keep the same stable-position identity. In `manual`, the root then returns to `.ready`, and the next tap atomically increments `attemptGeneration` and persists a new request ID before compute. In `automatic`, that same fresh eligibility triggers exactly one recompute. Thus a deterministic unavailable result does not spin inside one attempt, but it may be requested again after its own freshness window expires and genuinely fresh live-position evidence arrives.

Replay of the same local request ID/attempt/result bytes is idempotent, while same ID or attempt with different bytes fails closed. `automatic|off|big_numbers|tournament` project `.hidden`; they never expose a manual CTA or consume a stale manual result. Requesting、retry、success、unavailable、dismiss、navigation and Caddie opening write no `actual_club_set`、`shot_recorded` or recommendation-as-actual fallback.

Add exact `GuidanceManualRequestActionTests` and Watch offline timelines:

- `testManualReadyTapDurablyPersistsBeforeComputeAndConcurrentTapsReuseOneRequest`;
- `testRequestingDisablesRepeatTapAndWritesNoActualClubOrRoundFact`;
- `testCrashAtPreparedComputingResultWriteAndConsumedBoundariesRecoversOneLogicalResult`;
- `testRetryableFailureReusesRequestIdButDeterministicUnavailableDoesNotLoop`;
- `testAvailableResultReplacesCTAWithRecommendationAndTapOnlyOpensCaddie`;
- `testRestartLoadsExactCanonicalAvailableOrUnavailableResultBytes`;
- `testValidBytesReuseOnlyBeforeValidUntilAndExpiryCancelsBeforeRender`;
- `testExpiredResultRequiresNewerFreshFixThenAdvancesAttemptAndRequestId`;
- `testRestartAndForwardTimeJumpCannotShowExpiredResult`;
- `testBackwardClockOrHighWaterRollbackCannotReanimateOrStartCompute`;
- `testSameCellFreshFixAfterExpiryRearmsManualAndAutomaticWithoutJitterChurn`;
- `testHoleModeInputGenerationOrAuthorityChangeCancelsStaleRequestAndRejectsLateResult`;
- `testAutomaticOffBigNumbersAndTournamentNeverExposeOrConsumeManualRequest`;
- `testIPhoneAndWatchUseTheSameStateMachineButIndependentDeviceBoundRequests`;
- `testWatchManualRequestWorksWithPhoneAbsentAndNeverPeerTransfersItsResult`;
- `testConcurrentOfflineModeSelectionsConvergeByGenerationAndDeviceId`.

Production must not hard-code `automatic` or `manualRequest=false`.

- [ ] **Step 9: Run Python/Swift/Web parity and offline timelines**

Run:

```bash
uv run python tools/contracts/generate_contracts.py
uv run python -m unittest \
  tests.test_contract_codegen \
  tests.test_live_current_position tests.test_route_projection \
  tests.test_stochastic_caddie_planner tests.test_route_utility_planner \
  tests.test_guidance_engine_bundle tests.test_guidance_playable_regions \
  tests.test_guidance_first_leg_consistency tests.test_guidance_offline_authority \
  tests.test_guidance_contract tests.test_caddie_plan_contract -v
swift test --filter 'OfflineGuidanceEngineTests|PositionStabilityTrackerTests|GuidanceModeStoreTests|GuidanceFreshnessClockTests|GuidanceManualRequestActionTests|WatchOfflineGuidanceTimelineTests|GuidanceContractTests'
npm --prefix web_v2 test -- --run src/contracts/guidanceRuntimeCapability.test.ts src/contracts/generated.test.ts
```

Expected: PASS; this checkpoint's canonical-contracts source digest and all three generated outputs are byte-current；turning off network before round start still permits locally committed installed authority, map and recalculated Guidance; score-only facts do not invalidate; live movement/lie/target changes do; restart re-verifies raw authority; manual ready/requesting/retry/success/unavailable/restart/stale-cancel states are exact and shared by iOS/Watch without an actual-club write；valid bytes survive only until their identical `validUntil`, forward/backward clock jumps cannot expose stale output, and a same-cell fresh fix rearms a new manual attempt without jitter churn; cart stop/go is stable; Par 4/5 Driver lines do not terminate at the green; 3W can beat unstable Driver; stochastic/route-utility gates are honest; root first leg equals detail first leg; no wire contains probability or `expectedStrokes`; current-shot has no AVG, stochastic detail has calibrated combination `averageStrokes`, and route-utility detail carries null only.

- [ ] **Step 10: Commit the offline route-aware Guidance normalization**

```bash
git add contracts/canonical/guidance_v1.schema.json contracts/canonical/caddie_plan_v1.schema.json contracts/canonical/guidance_api_response_v1.schema.json contracts/canonical/guidance_runtime_capability_token_v1.schema.json contracts/canonical/fixtures/guidance/runtime_capability_token.json contracts/canonical/live_current_position_v1.schema.json contracts/canonical/live_round_package_v2.schema.json contracts/canonical/canonical_object_registry.json contracts/canonical/reason_codes.json tools/contracts/generate_contracts.py ai_caddie/contracts/generated.py mobile/ios/AICaddieDomain/GeneratedContracts.swift web_v2/src/contracts/generated.ts ai_caddie/guidance/map_geometry.py ai_caddie/guidance/position_stability.py ai_caddie/guidance/caddie_engine.py ai_caddie/guidance/multi_shot.py ai_caddie/guidance/guidance_input.py ai_caddie/guidance/stochastic_planner.py ai_caddie/guidance/route_utility_planner.py mobile/ios/AICaddieDomain/Guidance/LocalGuidanceCapabilityProjector.swift mobile/ios/AICaddieDomain/Guidance/LiveCurrentPosition.swift mobile/ios/AICaddieDomain/Guidance/PositionStabilityTracker.swift mobile/ios/AICaddieDomain/Guidance/GuidanceInputIdentity.swift mobile/ios/AICaddieDomain/Guidance/LocalGuidanceEngine.swift mobile/ios/AICaddieDomain/Guidance/RoutePlanner.swift mobile/ios/AICaddieDomain/Guidance/GuidanceModeStore.swift mobile/ios/AICaddieDomain/Guidance/GuidanceFreshnessClock.swift mobile/ios/AICaddieDomain/Guidance/GuidanceManualRequestAction.swift mobile/ios/AICaddieDomain/Guidance/GuidanceRuntimeCapability.swift server_v2/guidance.py server_v2/guidance_context_repo.py tests/test_contract_codegen.py tests/guidance_planner_fixtures.py tests/test_guidance_offline_authority.py tests/test_live_current_position.py tests/test_route_projection.py tests/test_stochastic_caddie_planner.py tests/test_route_utility_planner.py tests/test_guidance_first_leg_consistency.py tests/test_guidance_engine_bundle.py tests/test_guidance_runtime_capability_token.py tests/test_guidance_playable_regions.py mobile/ios/AICaddieDomainTests/OfflineGuidanceEngineTests.swift mobile/ios/AICaddieDomainTests/PositionStabilityTrackerTests.swift mobile/ios/AICaddieDomainTests/GuidanceModeStoreTests.swift mobile/ios/AICaddieDomainTests/GuidanceFreshnessClockTests.swift mobile/ios/AICaddieDomainTests/GuidanceManualRequestActionTests.swift mobile/ios/AICaddieWatchTests/WatchOfflineGuidanceTimelineTests.swift web_v2/src/contracts/guidanceRuntimeCapability.ts web_v2/src/contracts/guidanceRuntimeCapability.test.ts web_v2/src/contracts/generated.test.ts
git commit -m "feat: add offline route aware local guidance"
```

## Task D08c: Wire real elevation, trust rehydration, and server audit parity

**Finalizes:** D08a's audit-only server shell with the production `playsLike.elevation` provider and durable manifest trust history. No fixture constant or protocol-only provider enters the composition root.

**Files:**
- Create: `ai_caddie/guidance/elevation_provider.py`
- Create: `server_v2/guidance_manifest_trust.py`
- Modify: `server_v2/guidance_context_repo.py`
- Modify: `server_v2/course_dependencies.py`
- Modify: `server_v2/main.py`
- Create: `tests/test_guidance_elevation_provider.py`
- Create: `tests/test_guidance_manifest_trust.py`
- Modify: `tests/test_guidance_repository_provider.py`

- [ ] **Step 1: Write failing real-product and restart tests**

```python
# tests/test_guidance_elevation_provider.py
class VerifiedPlaysLikeElevationProviderTests(unittest.TestCase):
    def test_queries_current_and_aim_from_installed_promoted_triangulation(self) -> None:
        fixture = ElevationProductFixture.accepted()
        pair = fixture.provider.query_pair(
            authority=fixture.static_authority,
            subject_ref=fixture.subject_ref,
            expected_map_geometry_hash=fixture.map_geometry_hash,
            current=fixture.current,
            aim_target=fixture.aim_target,
        )
        self.assertEqual(pair.product_body_hash, fixture.elevation_product_hash)
        self.assertLessEqual(pair.current.nearest_anchor_distance_m, fixture.maximum_anchor_distance_m)
        self.assertLessEqual(pair.target.interpolation_residual_m, fixture.maximum_interpolation_residual_m)
        self.assertAlmostEqual(pair.delta_elevation_m, pair.target.elevation_m - pair.current.elevation_m)

    def test_cross_hole_map_hash_outside_hull_residual_or_degenerate_triangle_fail(self) -> None:
        for mutation in ("subject", "map_hash", "outside_hull", "residual", "degenerate", "ambiguous"):
            fixture = ElevationProductFixture.accepted(mutation=mutation)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                fixture.query()
```

```python
# tests/test_guidance_manifest_trust.py
class GuidanceManifestTrustTests(unittest.TestCase):
    def test_restart_verifies_old_and_new_leaf_manifests_and_provider_is_idempotent(self) -> None:
        fixture = DurableRotationFixture.two_generations()
        first = rehydrate_guidance_manifest_trust(fixture.bootstrap_roots, fixture.store)
        fixture.verify_old_and_new_manifests(first)
        second = rehydrate_guidance_manifest_trust(fixture.bootstrap_roots, fixture.reopen_store())
        fixture.verify_old_and_new_manifests(second)
        self.assertEqual(second.applied_rotation_payload_ids, first.applied_rotation_payload_ids)
        self.assertIs(get_guidance_manifest_trust(), get_guidance_manifest_trust())
```

- [ ] **Step 2: Implement the exact promoted elevation provider**

`playsLike` has two role-aware installed products: `playsLike.model` and `playsLike.elevation`. The elevation body is exact `ai-caddie-playsLike-elevation-v1` with `layoutRevisionId,holeGlobalId,subjectRef,mapGeometryHash,horizontalCrs=local-enu-wgs84-v1,verticalDatumId,horizontalUnit=meter,verticalUnit=meter,origin,samples,triangles,maximumAnchorDistanceM,maximumInterpolationResidualM,evidenceRefs`. `origin` is the canonical WGS84 ENU origin; sample exact keys are `sampleRef,eastM,northM,elevationM,anchorResidualM`; triangle exact keys are `triangleRef,sampleRefs`. `VerifiedPlaysLikeElevationProvider.query_pair(...)` consumes only `VerifiedCourseStaticAuthority`; verifies exact subject/layout/hole/map hash/CRS/datum/units; decodes canonical sorted samples/triangles; performs deterministic barycentric interpolation; returns `VerifiedElevationPair` carrying both elevations, nearest-anchor distances, interpolation residuals, triangle/sample refs and product-body hash. Convex-hull miss, anchor/residual threshold, degenerate/overlapping triangles, unknown datum/CRS or any identity mismatch returns unavailable. No request-time mutable mesh and no fixture constant enter production.

- [ ] **Step 3: Implement startup-only durable trust rehydration**

`guidance_manifest_trust.py` wraps Plan 2's durable rotation store. At process startup it builds trust from immutable roots, replays every persisted signed rotation envelope once in generation order, retains historical leaves and records exact payload IDs. Same-generation collision/gap fails startup. `get_guidance_manifest_trust()` is `@lru_cache(maxsize=1)`; request/provider resolution never replays rotations. The dependency root injects this one store into server authority/audit verification. Restart tests prove manifests signed by both prior and current leaf remain valid.

- [ ] **Step 4: Run real provider and trust tests**

Run:

```bash
uv run python -m unittest \
  tests.test_guidance_elevation_provider tests.test_guidance_manifest_trust \
  tests.test_guidance_repository_provider tests.test_guidance_playslike -v
```

Expected: PASS; production context construction has concrete player/elevation providers, old/new signing leaves survive restart, provider resolution is idempotent, and no constant elevation path remains.

- [ ] **Step 5: Commit provider and trust completion**

```bash
git add ai_caddie/guidance/elevation_provider.py server_v2/guidance_manifest_trust.py server_v2/guidance_context_repo.py server_v2/course_dependencies.py server_v2/main.py tests/test_guidance_elevation_provider.py tests/test_guidance_manifest_trust.py tests/test_guidance_repository_provider.py
git commit -m "feat: wire verified elevation and durable guidance trust"
```

## Task D09: Coordinate one offline-first Apple Guidance state model per process

**Depends on:** D02/D08a generated contracts and D08b/D08c local engine, static projector, position stability, mode store and optional server audit.

**Files:**
- Reuse: `mobile/ios/AICaddieDomain/Guidance/GuidanceManualRequestAction.swift`
- Reuse: `mobile/ios/AICaddieDomain/Guidance/GuidanceFreshnessClock.swift`
- Create: `mobile/ios/AICaddieDomain/Guidance/GuidanceCoordinator.swift`
- Create: `mobile/ios/AICaddieDomain/Guidance/GuidanceMapGeometry.swift`
- Create: `mobile/ios/AICaddieDomain/Guidance/GuidanceContractMapper.swift`
- Create: `mobile/ios/AICaddieDomain/Guidance/GuidanceAuditState.swift`
- Create: `mobile/ios/AICaddieDomainTests/GuidanceCoordinatorTests.swift`
- Create: `mobile/ios/AICaddieDomainTests/GuidanceMapGeometryTests.swift`
- Create: `mobile/ios/AICaddieDomainTests/GuidanceAppleSourceBoundaryTests.swift`
- Modify: `mobile/ios/AICaddie/AICaddieApp.swift`
- Modify: `mobile/ios/AICaddieWatch/AICaddieWatchApp.swift`
- Create: `mobile/ios/AICaddieWatch/Services/WatchGuidanceCoordinator.swift`

- [ ] **Step 1: Write failing offline/state-separation timelines**

Tests cover:

- a locally committed signed static bundle plus exact round pin starts and recomputes Guidance with network disabled;
- score-only facts and sync-state changes do not invalidate map or current Guidance;
- position/lie/Touch Target/flag/model/bundle/mode/control changes do;
- moving/cart state keeps front/middle/back distances and map visible while hiding the recommendation; stationary dwell recomputes it;
- stale/inaccurate/nonmonotonic GPS never falls back to a prior shot origin;
- `manual` consumes one durable request; `off/big_numbers/tournament` never leak a stale candidate;
- iOS and Watch use the same `GuidanceManualRequestAction` implementation/fixtures but one process-local actor/store each；identical verified inputs yield identical presentation transitions without sharing a request ID or result cache;
- a valid stored current-shot/full-plan pair survives restart only before its identical `validUntil`; expiry clears recommendation/PlaysLike before render, waits for a newer fresh stable fix and rearms the same-cell manual/automatic path without changing stable-position identity;
- forward time jump expires immediately, backward/high-water rollback never reanimates bytes or starts compute, and Phone-absent Watch follows the same clock fixtures locally;
- server audit match/mismatch is visible as audit state but cannot replace or disable a valid local candidate;
- logout/account/profile/pin/static-authority/control-generation changes clear verifier-only state and force raw-byte re-verification.

- [ ] **Step 2: Implement one coordinator with separate facts, recommendation and audit layers**

`GuidanceCoordinator` owns:

```swift
public struct GuidancePresentationState: Equatable, Sendable {
    public let mapAvailable: Bool
    public let distanceFacts: BigNumberDistances?
    public let currentShot: GuidanceEnvelopeV1?
    public let fullCaddie: CaddiePlanV1?
    public let manualRequest: GuidanceManualRequestPresentation
    public let unavailableReason: String?
    public let audit: GuidanceAuditState
}
```

It receives verifier-minted local static capabilities, current `LiveCurrentPosition` stability result, generated LRP mode policy, player model snapshot and effective control. It never accepts a Boolean capability map or caller-minted token. Each process's `GuidanceCoordinator` owns exactly one production `GuidanceManualRequestAction` actor over its device-local store and exposes `requestManualGuidanceOrRetry()` as a thin call；the presentation state is always reloaded locally before publication. iPhone and Watch share generated types、implementation and golden transition fixtures, not memory or actor identity. WatchConnectivity may relay raw signed authority/audit bytes and the convergent player-selected mode-setting bytes, but never a pending manual request、result cache、closure or second reduced truth.

- [ ] **Step 3: Implement exact aim-line and landing-ellipse geometry**

```swift
// mobile/ios/AICaddieDomain/Guidance/GuidanceMapGeometry.swift
import Foundation

public struct GuidanceEllipseAxes: Equatable, Sendable {
    public let majorM: Double
    public let minorM: Double
    public let covarianceEigenAngleRadians: Double
}

public struct GuidanceMapGeometry: Equatable, Sendable {
    public let aimTarget: GeoPoint
    public let predictedLanding: GeoPoint
    public let shotFrameBearingRadians: Double
    public let dispersion: GuidanceDispersionV1

    public init?(guidance: GuidanceEnvelopeV1) {
        guard guidance.availability == "available",
              let aim = guidance.aimTarget,
              let landing = guidance.predictedLanding,
              let bearing = guidance.shotFrameBearingDeg,
              let dispersion = guidance.dispersion else { return nil }
        self.aimTarget = GeoPoint(latitude: aim.latitude, longitude: aim.longitude)
        self.predictedLanding = GeoPoint(latitude: landing.latitude, longitude: landing.longitude)
        self.shotFrameBearingRadians = bearing * .pi / 180
        self.dispersion = dispersion
    }

    public var ellipseAxes: GuidanceEllipseAxes? {
        let xx = dispersion.covarianceXXM2
        let xy = dispersion.covarianceXYM2
        let yy = dispersion.covarianceYYM2
        guard xx.isFinite, xy.isFinite, yy.isFinite,
              xx >= 0, yy >= 0, xx * yy >= xy * xy,
              dispersion.confidence > 0, dispersion.confidence < 1 else { return nil }
        let trace = xx + yy
        let delta = sqrt(max(0, pow(xx - yy, 2) + 4 * pow(xy, 2)))
        let scale = sqrt(-2 * log(1 - dispersion.confidence))
        return GuidanceEllipseAxes(
            majorM: scale * sqrt(max(0, (trace + delta) / 2)),
            minorM: scale * sqrt(max(0, (trace - delta) / 2)),
            covarianceEigenAngleRadians: 0.5 * atan2(2 * xy, xx - yy)
        )
    }

    public var ellipseRotationRadians: Double? {
        ellipseAxes.map { shotFrameBearingRadians + $0.covarianceEigenAngleRadians }
    }
}
```

The renderer draws the line from live ball to `aimTarget`; it centers the ellipse at `predictedLanding`; it rotates only by `ellipseRotationRadians`. Tests use separated aim/landing coordinates and a non-zero covariance cross term so a target-centered or bearing-recomputed implementation fails.

- [ ] **Step 4: Map generated contracts without another DTO**

`GuidanceContractMapper` validates exact schema/timestamps/availability/mode/planner mode, candidate hash, `inputHash`, the sorted relevant `entityRevisions`, sorted static authority hashes and first-leg identity. Current-shot/full-plan must share exact `generatedAt/validUntil` and satisfy `generatedAt < validUntil`. Freshness is that generated window evaluated only through `GuidanceFreshnessClock`, not HTTP receipt time or a raw UI `Date()`. The coordinator stores generated values or immutable view projections only; no `GuidanceSnapshot(roundFactsVersion:target:)` compatibility type survives, while Track A's canonical/audit `RoundFactsVersion` model remains available to the audit adapter.

- [ ] **Step 5: Add Apple source-boundary scans**

Fail if app/domain production source uses `RoundFactsVersion`/`roundFactsVersion` as capability authority or local relevant-input identity, introduces `GuidanceInputVersion`, contains flat `runtimeCapabilities`, directly constructs verifier-only authority, exposes `geometry.target`, centers the ellipse at aim target, treats the last `shot_recorded` as GPS, hard-codes `.automatic`, compares Guidance `validUntil` with raw `Date()` outside `GuidanceFreshnessClock`, or uses server availability as an offline gate. Also fail if an iOS/Watch view constructs `GuidanceModeStore`/`GuidanceManualRequestAction` directly, proxies a manual-request tap to the other device, transports pending/result bytes through WatchConnectivity, or maps a requested/recommended club to `actual_club_set`. Generated/audit-only RoundFactsVersion references are explicitly allowlisted.

- [ ] **Step 6: Run and commit**

Add exact `testRemainingMarkerSemanticMappingAndLabelsAreFrozen`, `testMarkerMeaningSurvivesGrayscaleAndHighContrast`, `testDriverGuidanceAndTouchTargetUseDistinctStyleRoles`, and iPhone light/dark/AOD-style map snapshots before running:

Run:

```bash
swift test --filter 'GuidanceCoordinatorTests|GuidanceMapGeometryTests|GuidanceAppleSourceBoundaryTests|GuidanceFreshnessClockTests|GuidanceManualRequestActionTests|OfflineGuidanceEngineTests|WatchOfflineGuidanceTimelineTests'
```

Expected: PASS; each process has one local coordinator/manual-request action running the same generated state machine, Watch works with Phone absent, distances survive movement/network loss, valid manual CTA/result state survives device-local restart without duplicate compute or peer transfer, expired bytes never render, same-cell fresh fixes rearm, clock rollback never reanimates output, and line/ellipse semantics are exact.

```bash
git add mobile/ios/AICaddieDomain/Guidance/GuidanceCoordinator.swift mobile/ios/AICaddieDomain/Guidance/GuidanceMapGeometry.swift mobile/ios/AICaddieDomain/Guidance/GuidanceContractMapper.swift mobile/ios/AICaddieDomain/Guidance/GuidanceAuditState.swift mobile/ios/AICaddieDomainTests/GuidanceCoordinatorTests.swift mobile/ios/AICaddieDomainTests/GuidanceMapGeometryTests.swift mobile/ios/AICaddieDomainTests/GuidanceAppleSourceBoundaryTests.swift mobile/ios/AICaddie/AICaddieApp.swift mobile/ios/AICaddieWatch/AICaddieWatchApp.swift mobile/ios/AICaddieWatch/Services/WatchGuidanceCoordinator.swift
git commit -m "feat: coordinate offline apple guidance"
```

## Task D10: Build the iOS Hole Root, Map Detail, and Caddie layers

**Depends on:** D09; Track B installed iOS map asset trio for the pinned round binding.

**Files:**
- Reuse: `mobile/ios/AICaddieDomain/Guidance/GuidanceManualRequestAction.swift`
- Create: `mobile/ios/AICaddie/Views/Live/HoleRootView.swift`
- Create: `mobile/ios/AICaddie/Views/Live/MapDetailView.swift`
- Create: `mobile/ios/AICaddie/Views/Live/CaddieDetailView.swift`
- Create: `mobile/ios/AICaddie/Views/ClubCalibration/ClubCalibrationView.swift`
- Create: `mobile/ios/AICaddieDomain/Presentation/ClubDisplayCatalog.swift`
- Create: `mobile/ios/AICaddieDomain/Presentation/GuidanceReasonLocalizer.swift`
- Create: `mobile/ios/AICaddieDomain/Presentation/PlaysLikePresentation.swift`
- Modify: `mobile/ios/AICaddie/Views/CurrentHoleView.swift`
- Modify: `mobile/ios/AICaddie/Views/HoleImageMapView.swift`
- Modify: `mobile/ios/AICaddie/Views/CaddiePlanView.swift`
- Test: `mobile/ios/AICaddieTests/HoleRootPresentationTests.swift`
- Test: `mobile/ios/AICaddieTests/DesignSnapshotTests.swift`

- [ ] **Step 1: Write failing facts/recommendation/detail presentation tests**

Tests require:

- front/middle/back facts remain visible with no Guidance, moving GPS, offline mode or a blocked optional layer;
- raw front/middle/back are always the primary numbers and are never replaced by an adjusted value;
- only a current verified non-null PlaysLike value may add a secondary `调整 N ↑|↓|平` presentation; moving、off、tournament、unavailable or a later null value clears it immediately instead of retaining stale adjusted yards;
- an available current shot adds the recommended club's localized display name directly on screen (for example `3W` or `7号铁`), not a generic “建议” label and not raw `club:iron7`;
- `manual` with no current-generation result shows a primary “获取球童建议” action；ready/requesting/retryable failure/completed unavailable/available states exactly match D09's shared projection and never render CTA + recommendation simultaneously;
- the root shows only the best current-shot recommendation; full combinations stay in Caddie detail;
- Hole Root never displays `AVG. STROKES`; full Caddie detail displays it only from a non-null generated combination `averageStrokes` under `stochastic_expected_strokes_v1`, never by recomputing or reading a recovery row;
- Touch Target, Driver setting overlay and Caddie recommendation remain independent semantic layers;
- blocked/empty Caddie detail has an explicit localized zero state; raw reason codes and raw hazard/lie identifiers never render;
- recommendation navigation never writes `actual_club_set` or mutates selected actual club;
- all map snapshots contain current-ball and pin/green-target markers even when Guidance is absent.

- [ ] **Step 2: Implement facts-first presentation using generated values**

`HoleRootPresentation` receives `GuidancePresentationState` plus `ClubDisplayCatalog`. It exposes `recommendedClubDisplayName`, never a public raw reference for the view, and derives the optional adjustment through this shared immutable projection:

```swift
public enum PlaysLikeDirection: String, Equatable, Sendable {
    case uphill
    case downhill
    case level

    public var symbol: String {
        switch self {
        case .uphill: return "↑"
        case .downhill: return "↓"
        case .level: return "平"
        }
    }
}

public struct PlaysLikePresentation: Equatable, Sendable {
    public let baseYards: Int
    public let adjustedYards: Int
    public let direction: PlaysLikeDirection

    public init?(verified value: GuidancePlaysLikeV1?) {
        guard let value,
              value.baseHorizontalDistanceM.isFinite,
              value.elevationDeltaM.isFinite,
              value.adjustmentM.isFinite,
              value.distanceM.isFinite else { return nil }
        baseYards = Int((value.baseHorizontalDistanceM * 1.0936133).rounded())
        adjustedYards = Int((value.distanceM * 1.0936133).rounded())
        direction = value.elevationDeltaM > 0.25
            ? .uphill
            : value.elevationDeltaM < -0.25 ? .downhill : .level
    }
}
```

`PlaysLikePresentation` is built afresh from the current generated Guidance value; it is never cached independently. The raw front/middle/back projection remains sourced from current GPS and installed Green geometry. `baseYards/adjustedYards` are explicitly labeled shot/target values and may not masquerade as any raw front/middle/back fact. No wind、weather or air-density field enters this projection.

The root layout is:

```text
hole/par + map affordance
front | middle | back
[调整 152 ↑]                              // only for current verified PlaysLike
[获取球童建议 | 正在获取… | 重试建议 | unavailable reason] // manual projection only
[recommended club name + suggestion affordance]  // only when result is available
```

The club name itself is the primary button label. Accessibility adds rationale and opens Caddie detail. In manual mode, `HoleRootView` switches exhaustively over `GuidancePresentationState.manualRequest`: `.ready` is one 44 pt “获取球童建议” button, `.requesting` is disabled with progress, `.retryableFailure` is one “重试建议” button plus localized message, `.resultUnavailable` is non-spinning localized text, `.resultAvailable` defers to the recommended-club chip, and `.hidden` emits no manual control. A malformed state containing both `.ready|requesting|retryableFailure|resultUnavailable` and a current available shot fails the presentation initializer instead of showing two actions. No multi-leg route, probability or AVG/expected-strokes number appears on the root.

`CaddieDetailView` maps generated `CaddiePlanV1` legs to localized club names and target/hazard display metadata. When a leg carries verified PlaysLike, it shows the explicit pair `原始 N 码 / 调整 M 码 ↑|↓|平`; otherwise it shows only the original distance and no placeholder adjusted number. For a generated plan with `plannerMode=stochastic_expected_strokes_v1`, every visible combination must carry a non-null `averageStrokes`; the combination header displays `AVG. STROKES 2.3` rounded to one decimal. For route-utility、uncalibrated、unavailable or any mixed/invalid payload, the AVG label is absent everywhere rather than shown as `--`. A verified accepted-empty hazard product renders “未发现已验证的相关障碍”，not an empty `List`. Unavailable plans render a localized stable reason plus the still-valid distance/map facts.

- [ ] **Step 3: Host one process-local coordinator state without recommendation-to-actual mutation**

`CurrentHoleView` receives its iPhone process's sole D09 coordinator state/action. Tapping “获取球童建议” or “重试建议” calls only that local `GuidanceCoordinator.requestManualGuidanceOrRetry()` and disables itself from the published requesting state；it does not navigate before a result exists. Tapping the displayed club recommendation changes navigation only. `submitEvents()` uses explicit player input for `actual_club_set`; neither a manual request、current-shot nor full-plan value can fill it. Touch Target stays interactive only in Map Detail and writes only D10a's durable target events.

- [ ] **Step 4: Add iPhone snapshots and native tests**

Add exact iPhone tests `testManualReadyTapCallsProcessLocalActionOnceAndWritesNoActualClub`, `testManualRequestingDisablesRepeatTap`, `testManualRetryAndUnavailableUseLocalizedProjection`, `testAvailableManualResultReplacesCTAWithClubChip`, `testRestartOrStaleCancellationNeverShowsCTABesideAStaleRecommendation`, `testExpiredResultDisappearsBeforeRenderAndSameCellFreshFixRearmsReady`, and `testClockRollbackShowsLocalizedUnavailableWithoutStaleClub`. Snapshots cover facts-only, verified uphill/downhill PlaysLike, PlaysLike unavailable, moving/distances-only, every manual ready/requesting/retryable/unavailable/available state, expired/time-untrusted states, off, Big Numbers, tournament, Driver-at-Tee, Touch Target, available recommendation, unavailable recommendation, accepted-empty hazard, stochastic full-Caddie combinations with one-decimal AVG, and route-utility combinations with no AVG. The moving/off/tournament/unavailable/expired/time-untrusted snapshots require raw front/middle/back to remain while no adjusted number、stale arrow or club exists. Every Hole Root snapshot forbids AVG. Include separated aim/landing coordinates so the line and ellipse cannot accidentally overlap.

Run:

```bash
swift test --filter 'HoleRootPresentationTests|DesignSnapshotTests|GuidanceManualRequestActionTests'
xcodegen generate --spec mobile/ios/project.yml --project-root .
xcodebuild test -project mobile/ios/AICaddieNative.xcodeproj -scheme AICaddie -destination "platform=iOS Simulator,name=iPhone 16,OS=latest"
```

Expected: PASS; visible labels are product language, not internal IDs.

- [ ] **Step 5: Commit the iOS three-layer experience**

```bash
git add mobile/ios/AICaddie/Views/Live/HoleRootView.swift mobile/ios/AICaddie/Views/Live/MapDetailView.swift mobile/ios/AICaddie/Views/Live/CaddieDetailView.swift mobile/ios/AICaddie/Views/ClubCalibration/ClubCalibrationView.swift mobile/ios/AICaddieDomain/Presentation/ClubDisplayCatalog.swift mobile/ios/AICaddieDomain/Presentation/GuidanceReasonLocalizer.swift mobile/ios/AICaddieDomain/Presentation/PlaysLikePresentation.swift mobile/ios/AICaddie/Views/CurrentHoleView.swift mobile/ios/AICaddie/Views/HoleImageMapView.swift mobile/ios/AICaddie/Views/CaddiePlanView.swift mobile/ios/AICaddieTests/HoleRootPresentationTests.swift mobile/ios/AICaddieTests/DesignSnapshotTests.swift
git commit -m "feat: add iOS S70 guidance layers"
```

## Task D10a: Implement role-bound S70 map mechanics and durable Touch Target

**Depends on:** D02b/D02c exact map trio, D09/D10, Track A `ShotCaptureSession` + `PlayerLiveFactProducer.setShotTarget()`.

**Files:**
- Create: `mobile/ios/AICaddieDomain/Map/VerifiedMapAssetSet.swift`
- Create: `mobile/ios/AICaddieDomain/Map/MapCoordinateTransform.swift`
- Create: `mobile/ios/AICaddieDomain/Map/MapViewportTransform.swift`
- Create: `mobile/ios/AICaddieDomain/Map/MapMechanics.swift`
- Create: `mobile/ios/AICaddieDomainTests/MapAssetSetTests.swift`
- Create: `mobile/ios/AICaddieDomainTests/MapMechanicsTests.swift`
- Create: `mobile/ios/AICaddie/Services/CurrentShotTargetRecorder.swift`
- Create: `mobile/ios/AICaddieTests/CurrentShotTargetRecorderTests.swift`
- Modify: `mobile/ios/AICaddie/Views/Live/MapDetailView.swift`
- Modify: `mobile/ios/AICaddie/Views/HoleImageMapView.swift`
- Modify: `mobile/ios/AICaddieTests/DesignSnapshotTests.swift`

- [ ] **Step 1: Write failing asset, projection, viewport and target-restart tests**

Cover:

- exact same-subject `map.geometry|map.transform|map.image` binding and cross-hole/role/hash swap rejection;
- intrinsic image width/height decoded from image bytes; transform containing dimensions, scale or route samples is rejected;
- unique Tee WGS84 origin, deterministic ECEF→ENU, exact six-value matrix order, inverse round-trip and non-invertible failure;
- image-decode failure, projected registration point outside bounds and residual-gate failure;
- remaining 100/150/200/250-yard markers interpolated from geometry's `remainingDistanceToGreenM`, not fixed screen percentages;
- remaining-marker presentation is exact `100=red,150=white,200=blue,250=yellow`, always includes the numeric yard label/VoiceOver value and remains distinguishable without color；this is the high-confidence S70 visual + Garmin cross-device official semantic mapping from the evidence file, not a claim that Garmin published S70 palette hex values;
- current ball and selected pin/green target markers always render;
- Driver configured-distance ring appears only in verified Tee-shot context and disappears after the effective first shot/leaving Tee;
- base image, ball, pin, markers, aim line, landing ellipse, Driver ring and Touch Target all use the same zoom/pan viewport transform;
- a non-uniform/rotated/sheared map matrix still renders metric circles/ellipses correctly; no scalar `pixelsPerMeter` approximation exists;
- set/retract Touch Target reuses the current preallocated legal shot UUID across restart and writes only `shot_target_set/shot_target_retracted`.

- [ ] **Step 2: Decode one immutable map asset set**

```swift
public struct VerifiedMapAssetSet: Sendable {
    public let layoutRevisionId: String
    public let holeGlobalId: String
    public let subjectRef: String
    public let geometryHash: String
    public let imageHash: String
    public let imageWidthPx: Int
    public let imageHeightPx: Int
    public let routePoints: [VerifiedMapRoutePoint]
    public let coordinateTransform: MapCoordinateTransform
}

public struct MapCoordinateTransform: Sendable {
    public let teeOrigin: GeoPoint
    private let a: Double
    private let b: Double
    private let c: Double
    private let d: Double
    private let tx: Double
    private let ty: Double

    public func project(_ point: GeoPoint) throws -> MapPixelPoint {
        let enu = try WGS84ENU.project(point, origin: teeOrigin)
        return MapPixelPoint(
            x: a * enu.eastM + b * enu.northM + tx,
            y: c * enu.eastM + d * enu.northM + ty
        )
    }

    public func unproject(_ pixel: MapPixelPoint) throws -> GeoPoint {
        let determinant = a * d - b * c
        guard determinant.isFinite, abs(determinant) > 1e-12 else {
            throw MapTransformError.nonInvertible
        }
        let x = pixel.x - tx
        let y = pixel.y - ty
        let east = (d * x - b * y) / determinant
        let north = (-c * x + a * y) / determinant
        return try WGS84ENU.unproject(eastM: east, northM: north, origin: teeOrigin)
    }
}
```

The verifier receives raw role-aware bytes from D02c's local static authority projector. It exact-decodes D02b's geometry/transform, verifies both hashes and subject, reads only the image header for dimensions and returns no public unchecked initializer. `WatchHoleImageStore` later keys the image by `(snapshotId,subjectRef,imageHash)`; content hash sharing never erases subject/role verification.

- [ ] **Step 3: Implement route/metric mechanics without scalar map scale**

`MapMechanics.remainingMarkerPlacements` interpolates the verified route by Tee-origin station for requested remaining yards. Driver rings and landing ellipses are built as metric ENU paths around their semantic centers, then each sampled point is transformed through the full 2×2 matrix. This preserves rotation, anisotropic scale and shear.

`MapMarkerPresentation` freezes the functional mapping `{100:.red,150:.white,200:.blue,250:.yellow}` and carries exact `remainingYards,colorToken,visibleLabel,accessibilityLabel`. The renderer shows `100/150/200/250` beside or inside every point, adds a contrast halo/shape edge for white and never uses color as the only cue. Product semantic color tokens—not guessed Garmin RGB/hex values—own light/dark/AOD contrast. Unit conversion occurs before presentation and user-facing labels remain yards under L21.

The overlay contract is explicit:

```swift
public struct MapOverlayPresentation: Sendable {
    public let currentBall: GeoPoint
    public let pinOrGreenTarget: GeoPoint
    public let driverOverlay: DriverDistanceOverlay?
    public let touchTarget: GeoPoint?
    public let guidance: GuidanceMapGeometry?
}

public static func driverOverlay(
    teeContext: VerifiedTeeShotContext?,
    configuredDriverDistanceM: Double?,
    calibratedLandingBand: ClosedRange<Double>?
) -> DriverDistanceOverlay? {
    guard teeContext?.isBeforeEffectiveFirstShot == true else { return nil }
    // player-setting fact only; never a Caddie recommendation
}
```

Overlay roles are visually non-interchangeable: Driver Arc is a thin solid white fact-layer arc；Guidance current-ball→`aimTarget` is a thicker solid green recommendation line with a green translucent landing ellipse centered on `predictedLanding`；Touch Target is its own cyan dashed/two-leg current→target→pin line with a target glyph. Remaining-distance points retain red/white/blue/yellow only. Snapshot/source tests reject reusing one style token across Driver、Guidance、Touch Target or layup markers. All layers draw ball and pin markers last so they remain visible.

- [ ] **Step 4: Apply one viewport transform to base image and overlays**

`MapViewportTransform` owns aspect-fit scale, user zoom, pan offset and recenter anchor. The base bitmap and every overlay point pass through the same `imagePixelToScreen` function; no SwiftUI base-image `.aspectRatio(.fit)` may sit outside the zoomed container while Canvas alone zooms. Pinch/Crown changes preserve the current ball or active target as anchor; “recenter” returns to current ball. Snapshot tests compare a known image landmark and overlay point before/after zoom/pan to detect drift.

- [ ] **Step 5: Wire durable iPhone Touch Target interaction**

Map Detail supports tap/drag preview, explicit confirm, clear and cancel. Confirm calls `CurrentShotTargetRecorder.set(session:...)`; clear calls `retract`; cancel changes only local preview. The recorder delegates event creation to Track A `PlayerLiveFactProducer`, appends through the shared ledger/outbox and never creates another target DTO/event path. Restart tests prove the target and the later manual/confirmed AutoShot share the same shot ID.

- [ ] **Step 6: Run and commit**

Run:

```bash
swift test --filter 'MapAssetSetTests|MapMechanicsTests|CurrentShotTargetRecorderTests|DesignSnapshotTests'
```

Expected: PASS; exact role trio, no overlay drift, ball/pin always visible, 100/150/200/250 labels map to red/white/blue/yellow with non-color redundancy, Driver/Guidance/Touch Target styles remain distinct, Driver ring is Tee-only and target capture is durable.

```bash
git add mobile/ios/AICaddieDomain/Map/VerifiedMapAssetSet.swift mobile/ios/AICaddieDomain/Map/MapCoordinateTransform.swift mobile/ios/AICaddieDomain/Map/MapViewportTransform.swift mobile/ios/AICaddieDomain/Map/MapMechanics.swift mobile/ios/AICaddieDomainTests/MapAssetSetTests.swift mobile/ios/AICaddieDomainTests/MapMechanicsTests.swift mobile/ios/AICaddie/Services/CurrentShotTargetRecorder.swift mobile/ios/AICaddieTests/CurrentShotTargetRecorderTests.swift mobile/ios/AICaddie/Views/Live/MapDetailView.swift mobile/ios/AICaddie/Views/HoleImageMapView.swift mobile/ios/AICaddieTests/DesignSnapshotTests.swift
git commit -m "feat: add role bound S70 map mechanics"
```

## Task D11: Build the single-root Watch experience over its process-local Guidance state

**Depends on:** D09; Track A single ledger/reducer/outbox migration; locked decisions L01–L03 (no five-page pager, no three-page default, one current-hole root plus shallow instruments).

**Files:**
- Reuse: `mobile/ios/AICaddieDomain/Guidance/GuidanceManualRequestAction.swift`
- Create: `mobile/ios/AICaddieWatch/Views/HoleRoot/WatchHoleRootView.swift`
- Create: `mobile/ios/AICaddieWatch/Navigation/WatchInstrumentRoute.swift`
- Create: `mobile/ios/AICaddieWatch/Views/HoleRoot/WatchRootInstrumentDock.swift`
- Create: `mobile/ios/AICaddieWatch/Views/HoleRoot/WatchGolfToolsSheet.swift`
- Create: `mobile/ios/AICaddieWatch/Views/HoleRoot/WatchInstrumentUnavailableView.swift`
- Modify: `mobile/ios/AICaddieWatch/AICaddieWatchApp.swift`
- Modify: `mobile/ios/AICaddieWatch/Views/WatchRoundContainerView.swift`
- Modify: `mobile/ios/AICaddieWatch/Views/WatchRoundHomeView.swift`
- Modify: `mobile/ios/AICaddieWatch/Models/WatchRoundState.swift`
- Modify: `mobile/ios/AICaddieWatch/Services/WatchSyncClient.swift`
- Test: `mobile/ios/AICaddieWatchTests/WatchGuidanceCoordinatorTests.swift`
- Test: `mobile/ios/AICaddieWatchTests/WatchRoundModelTests.swift`
- Test: `mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift`

- [ ] **Step 1: Write failing single-root, visible-club and zero-state tests**

Require:

- Watch transport exposes no mutable second round projection;
- facts-only root keeps hole/par, front/middle/back and the 9/18-hole score-history ring;
- verified PlaysLike adds only one secondary adjusted row with an explicit uphill/downhill marker; raw distances remain primary and all zero/moving/off/tournament states clear the row;
- available Guidance displays the localized recommended club name directly on screen, not only in `accessibilityValue`, not a generic “建议” button and never selected actual club;
- Hole Root never renders `AVG. STROKES` even when the pushed full Caddie detail has a calibrated stochastic value;
- moving/manual/off/big-numbers/tournament states have explicit root presentations and never leak stale recommendation;
- manual mode without a current-generation result shows a visible 44 pt “获取球童建议” CTA above the dock；requesting disables duplicate taps, retry reuses the same request, unavailable is stable text, and available result replaces the CTA with the club chip;
- tapping the 9/18-hole score-history ring opens Scorecard; it never changes holes directly and its combined header hit region is at least 44×44 pt;
- the bottom dock has exactly two persistent labeled hit targets, “地图” and “工具”, each at least 44×44 pt on both 41/46 mm；no six-icon strip、hidden long press or horizontal swipe is a required discovery path;
- an available recommendation chip opens Caddie directly, while Golf Tools always retains a Caddie row and opens its honest zero/blocked state when Guidance is absent、off、moving、Big Numbers or tournament-gated;
- Golf Tools exposes the exact ordered route list Map → Caddie → Hazards → Macro Green → PinPointer → Scorecard; unavailable capabilities remain discoverable and open localized zero/blocked states rather than disappearing;
- selecting one Golf Tools row dismisses the sheet and pushes exactly one shallow instrument；one system Back returns directly to Hole Root rather than the tools sheet or a sibling instrument;
- preemption preserves an active instrument only while `(roundIncarnationId,orderedHoleCursor,staticAuthorityHash)` still matches；a hole advance/authority change returns to the new Hole Root, while Club Prompt/AOD resume on the same hole restores the interrupted instrument without committing transient edits;
- score confirmation from D14b preempts every shallow instrument; Club Prompt is next priority;
- five-page and three-page horizontal `TabView`/pager patterns are source-boundary failures unless a future E01 decision record explicitly reopens them.

- [ ] **Step 2: Implement one current-hole root and shallow instrument routes**

```swift
enum WatchInstrumentRoute: String, CaseIterable, Codable, Equatable, Sendable {
    case map
    case caddie
    case hazards
    case macroGreen
    case pinPointer
    case scorecard

    static let golfToolsOrder: [Self] = [
        .map, .caddie, .hazards, .macroGreen, .pinPointer, .scorecard,
    ]

    var localizedTitle: String {
        switch self {
        case .map: return "球道地图"
        case .caddie: return "球童建议"
        case .hazards: return "障碍"
        case .macroGreen: return "宏观坡向"
        case .pinPointer: return "旗位方向"
        case .scorecard: return "记分卡"
        }
    }
}

struct WatchInstrumentContextToken: Codable, Equatable, Sendable {
    let roundIncarnationId: String
    let orderedHoleCursor: Int
    let staticAuthorityHash: String
}

struct WatchHoleRootPresentation: Equatable {
    let hole: Int
    let par: Int?
    let frontYards: Int?
    let middleYards: Int?
    let backYards: Int?
    let playsLikeAdjustedYards: Int?
    let playsLikeDirection: PlaysLikeDirection?
    let recommendedClubDisplayName: String?
    let manualRequest: GuidanceManualRequestPresentation
    let guidanceUnavailableText: String?
    let scoreRing: WatchHoleScoreRingPresentation
}

struct WatchHoleRootView: View {
    let presentation: WatchHoleRootPresentation
    let openInstrument: (WatchInstrumentRoute) -> Void
    let openTools: () -> Void
    let requestManualGuidance: () -> Void

    var body: some View {
        VStack(spacing: 6) {
            Button {
                openInstrument(.scorecard)
            } label: {
                HoleHeaderAndScoreRing(presentation: presentation)
                    .frame(minHeight: 44)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("打开记分卡")
            BigNumberDistances(presentation: presentation)
            if let adjusted = presentation.playsLikeAdjustedYards,
               let direction = presentation.playsLikeDirection {
                Text("调整 \(adjusted) \(direction.symbol)")
                    .font(.caption2)
                    .accessibilityLabel("坡度调整距离 \(adjusted) 码 \(direction.symbol)")
            }
            if let club = presentation.recommendedClubDisplayName {
                Button {
                    openInstrument(.caddie)
                } label: {
                    HStack {
                        Text(club).font(.headline)
                        Text("建议").font(.caption)
                    }
                    .frame(minHeight: 44)
                }
                .buttonStyle(.borderedProminent)
            } else {
                switch presentation.manualRequest {
                case .ready(let label):
                    Button(label, action: requestManualGuidance)
                        .frame(minHeight: 44)
                case .requesting(let label):
                    ProgressView(label)
                        .frame(minHeight: 44)
                case .retryableFailure(let label, let localizedMessage):
                    VStack(spacing: 2) {
                        Text(localizedMessage).font(.caption2)
                        Button(label, action: requestManualGuidance)
                            .frame(minHeight: 44)
                    }
                case .resultUnavailable(let localizedMessage):
                    Text(localizedMessage).font(.caption2)
                case .hidden, .resultAvailable:
                    EmptyView()
                }
            }
        }
        .safeAreaInset(edge: .bottom) {
            WatchRootInstrumentDock(
                openMap: { openInstrument(.map) },
                openTools: openTools
            )
        }
    }
}

struct WatchRootInstrumentDock: View {
    let openMap: () -> Void
    let openTools: () -> Void

    var body: some View {
        HStack(spacing: 6) {
            Button("地图", action: openMap)
                .frame(maxWidth: .infinity, minHeight: 44)
            Button("工具", action: openTools)
                .frame(maxWidth: .infinity, minHeight: 44)
        }
    }
}

struct WatchGolfToolsSheet: View {
    let openInstrument: (WatchInstrumentRoute) -> Void

    var body: some View {
        List(WatchInstrumentRoute.golfToolsOrder, id: \.self) { route in
            Button(route.localizedTitle) {
                openInstrument(route)
            }
        }
        .navigationTitle("球局工具")
    }
}

struct WatchInstrumentUnavailableView: View {
    let title: String
    let localizedReason: String

    var body: some View {
        VStack(spacing: 8) {
            Text(title).font(.headline)
            Text(localizedReason)
                .font(.caption)
                .multilineTextAlignment(.center)
        }
        .navigationTitle(title)
    }
}
```

The root mapping is closed, not an implementation suggestion: score-ring/header tap → `.scorecard`; recommendation chip → `.caddie`; persistent “地图” → `.map`; persistent “工具” → `WatchGolfToolsSheet`. The sheet always lists `.map/.caddie/.hazards/.macroGreen/.pinPointer/.scorecard` in that order, closes before routing, and never becomes a sibling page. `localizedTitle` is product-localized copy (the shown Chinese values are the zh-CN fixture) and its row may show a localized availability subtitle, but the route itself never disappears because Guidance or an optional capability is unavailable. Map, Caddie, Hazard, Green preview, PinPointer and Scorecard are one-level pushed instruments under one interaction arbiter, not permanent swipe pages. The dock contains exactly two labeled controls and remains above the fold through a bottom safe-area inset on both Watch sizes.

D11 must compile and remain truthful before D12/D12a/D14b fill every destination. `WatchRoundContainerView` routes an implementation that is not yet enabled, a missing optional capability, or blocked live evidence to `WatchInstrumentUnavailableView(title:localizedReason:)`; the reason is produced by `GuidanceReasonLocalizer`/the shared product-copy catalog and never exposes a raw reason code. D12 replaces Map/Caddie/Hazard/Macro Green destinations with their real views, D12a replaces PinPointer, and D14b replaces Scorecard；the enum、entry mapping、Back semantics and zero-state fallback do not change between milestones.

`WatchRoundContainerView` owns `activeInstrument: WatchInstrumentRoute?`, `toolsSheetPresented` and the route's `WatchInstrumentContextToken`. It injects `requestManualGuidance` from the Watch process's local `WatchGuidanceCoordinator`, whose `requestManualGuidanceOrRetry()` uses the same domain implementation/API as iOS but a distinct device-bound actor/store；the view cannot call `GuidanceModeStore` directly、construct another action or proxy the tap to iPhone. The presentation initializer rejects a manual CTA state beside a non-null available recommendation. Selecting a tools row atomically clears the sheet and sets the route. System Back clears the active route and returns to Hole Root in one step；it never returns to the tools sheet or cycles to a sibling. A higher-priority score/Club Prompt overlay dismisses the transient tools sheet but retains the active instrument and its local uncommitted interaction state. After the overlay/AOD interruption, resume occurs only when the exact context token still matches；otherwise route state and uncommitted preview are discarded and the new Hole Root appears. Back、context invalidation and preview discard append no target、flag、score or shot fact. Focus/resume therefore restores an interrupted valid instrument, never a pager index or stale previous-hole surface. The root keeps Big Numbers and Caddie mutually exclusive according to LRP mode, while the persistent Tools Caddie row remains reachable and explains that blocked mode without fabricating a recommendation.

`playsLikeAdjustedYards` and `playsLikeDirection` are either both present or both nil and are rebuilt from D10's immutable projection. Raw `middleYards` stays the large primary value. Moving、off、tournament、unavailable and null PlaysLike states set both optional fields to nil; neither root nor resume state may retain the previous adjustment.

- [ ] **Step 3: Delete second truth and raw-display fallbacks**

`AICaddieWatchApp` owns one `WatchRoundModel` and D09 coordinator. `WatchSyncClient` is byte transport only. Delete `suggestedClub → options.first → selectedClub`, direct elevation-to-yards and raw club/reason display fallbacks. `ClubDisplayCatalog` and `GuidanceReasonLocalizer` are shared with iOS.

- [ ] **Step 4: Run 41/46 mm root snapshots**

Add exact navigation/accessibility tests:

- `testScoreRingOpensScorecardWithoutChangingActiveHole`;
- `testRootDockHasExactlyMapAndToolsWithMinimumFortyFourPointTargets`;
- `testRecommendationChipOpensCaddieAndUnavailableCaddieRemainsInTools`;
- `testManualReadyCTAInvokesWatchLocalActionOnceAndNeverWritesActualClub`;
- `testManualRequestingRetryUnavailableAndAvailableStatesAreMutuallyExclusive`;
- `testManualRequestUsesSameFixtureTransitionsAsIPhoneWithoutSharingRequestOrResult`;
- `testExpiredManualResultNeverRendersAndSameCellFreshFixRearmsWatchLocalRequest`;
- `testWatchClockRollbackCannotReanimateClubAndUsesLocalizedUnavailableState`;
- `testGolfToolsOrderAndRouteMappingAreExactOnBothWatchSizes`;
- `testToolSelectionDismissesSheetAndOneBackReturnsDirectlyToRoot`;
- `testScoreOrClubPromptPreemptionResumesOnlyAnExactMatchingInstrumentContext`;
- `testHoleAdvanceOrAuthorityChangeDropsStaleInstrumentAndUncommittedPreview`;
- `testNoHorizontalPagerSixIconDockOrLongPressOnlyInstrumentEntryExists`.

Render facts-only, verified uphill/downhill PlaysLike, PlaysLike unavailable, manual ready/requesting/retryable/unavailable/available, expired/time-untrusted manual states, available club, moving, off, Big Numbers, tournament, every Golf Tools availability/zero-state badge, score-confirmation preemption and Club Prompt queued states at 41/46 mm. Verify raw distances remain primary, no stale adjusted row or club survives a zero/expiry/clock-rollback state, manual CTA/progress/retry remain legible and tappable without colliding with the fixed dock, the recommended club is legible without VoiceOver, the score ring remains present/clickable, and “地图/工具” remain above the fold without clipping or scrolling.

Run:

```bash
swift test --filter 'WatchGuidanceCoordinatorTests|WatchRoundModelTests|WatchDesignSnapshotTests|GuidanceManualRequestActionTests|WatchOfflineGuidanceTimelineTests'
```

Expected: PASS; no horizontal multi-page product shell remains, every instrument has one deterministic discoverable entry/Back path, and preemption never resumes a stale-hole instrument.

- [ ] **Step 5: Commit the single-root Watch experience**

```bash
git add mobile/ios/AICaddieWatch/Views/HoleRoot/WatchHoleRootView.swift mobile/ios/AICaddieWatch/Navigation/WatchInstrumentRoute.swift mobile/ios/AICaddieWatch/Views/HoleRoot/WatchRootInstrumentDock.swift mobile/ios/AICaddieWatch/Views/HoleRoot/WatchGolfToolsSheet.swift mobile/ios/AICaddieWatch/Views/HoleRoot/WatchInstrumentUnavailableView.swift mobile/ios/AICaddieWatch/AICaddieWatchApp.swift mobile/ios/AICaddieWatch/Views/WatchRoundContainerView.swift mobile/ios/AICaddieWatch/Views/WatchRoundHomeView.swift mobile/ios/AICaddieWatch/Models/WatchRoundState.swift mobile/ios/AICaddieWatch/Services/WatchSyncClient.swift mobile/ios/AICaddieWatchTests/WatchGuidanceCoordinatorTests.swift mobile/ios/AICaddieWatchTests/WatchRoundModelTests.swift mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift
git commit -m "feat: add single root Watch experience"
```

## Task D12: Add interactive Watch Map/Caddie/Hazard/Macro-Green instruments

**Depends on:** D10a/D11; Track B Watch install manifest and exact map asset trio; D04/D05 promoted capabilities; E04 layout evidence before default rollout.

**Files:**
- Create: `mobile/ios/AICaddieWatch/Views/MapDetail/WatchMapDetailView.swift`
- Create: `mobile/ios/AICaddieWatch/Views/Caddie/WatchCaddieDetailView.swift`
- Create: `mobile/ios/AICaddieWatch/Views/Hazard/WatchHazardDetailView.swift`
- Create: `mobile/ios/AICaddieWatch/Views/Green/WatchMacroGreenView.swift`
- Create: `mobile/ios/AICaddieWatch/Services/WatchCurrentShotTargetRecorder.swift`
- Modify: `mobile/ios/AICaddieWatch/Services/WatchHoleImageStore.swift`
- Modify: `mobile/ios/AICaddieWatch/Views/WatchRoundContainerView.swift`
- Create: `mobile/ios/AICaddieWatchTests/WatchMapInteractionTests.swift`
- Create: `mobile/ios/AICaddieWatchTests/WatchGuidanceDetailsTests.swift`
- Modify: `mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift`

- [ ] **Step 1: Write failing interactive-map and honest-zero-state tests**

Require:

- Watch image store re-verifies `(snapshotId,subjectRef,map.image hash)` with same-subject transform/geometry before returning bytes;
- ball and pin/green target render in facts-only map;
- base bitmap and overlays remain coincident through Crown zoom, pan and recenter;
- Touch Target has enter-placement, tap/drag preview, confirm, clear and cancel; confirm/retract uses the shared preallocated shot ID and survives restart;
- current-shot line ends at `aimTarget`; ellipse centers at `predictedLanding` with exact rotation;
- 100/150/200/250 remaining markers use the shared red/white/blue/yellow `MapMarkerPresentation`, show numeric yard labels and VoiceOver values, and remain identifiable in grayscale/high-contrast snapshots;
- Driver Arc is thin white, Guidance aim/dispersion is thicker green, and Touch Target is cyan dashed/two-leg；none may borrow a remaining-marker color as its sole identity;
- verified PlaysLike appears in Caddie as an explicit original/adjusted pair with uphill/downhill marker; missing/moving/off/tournament states contain no adjusted numeric fallback and never mention wind;
- Driver ring is absent outside Tee-shot context;
- Caddie/Hazard use localized display metadata, never `club:iron7`, `penalty_area` or raw reason codes;
- verified accepted-empty hazard displays an explicit zero state;
- Green instrument is titled/described as “宏观坡向预览”; no test or copy calls it Garmin Green Contours or putt-level contour parity;
- every D11 `WatchInstrumentRoute` reaches exactly its named detail from both the direct root entry and Golf Tools where applicable；capability/Guidance absence opens the named localized zero/blocked view rather than a blank screen、disabled invisible row or fallback sibling route;
- Hazard and Macro Green never acquire extra permanent root icons：their sole root discovery path is the labeled “工具” sheet, while Hazard may additionally be reached from Map Detail without changing the active root route contract.

- [ ] **Step 2: Render base image and every overlay through one viewport**

```swift
struct WatchMapDetailView: View {
    let presentation: WatchMapDetailPresentation
    let recorder: WatchCurrentShotTargetRecorder
    @State private var zoom = 1.0
    @State private var pan = CGSize.zero
    @State private var interaction: MapInteractionMode = .navigate
    @State private var targetPreview: GeoPoint?

    var body: some View {
        GeometryReader { proxy in
            Canvas { context, size in
                let viewport = MapViewportTransform(
                    imageSize: presentation.imageSize,
                    viewSize: size,
                    zoom: zoom,
                    pan: pan,
                    anchor: presentation.recenterAnchor
                )
                viewport.drawBaseImage(presentation.baseImage, in: &context)
                drawDriver(in: &context, viewport: viewport)
                drawRemainingMarkers(in: &context, viewport: viewport)
                drawGuidance(in: &context, viewport: viewport)
                drawTouchTarget(in: &context, viewport: viewport)
                drawBallAndPinLast(in: &context, viewport: viewport)
            }
            .contentShape(Rectangle())
            .gesture(mapGesture(in: proxy.size))
        }
        .focusable()
        .digitalCrownRotation($zoom, from: 1, through: 4, by: 0.1)
        .toolbar { mapControls }
    }
}
```

`viewport.drawBaseImage` and every `viewport.imagePixelToScreen` call share the same fitted image rect, zoom, pan and anchor. There is no separate `.aspectRatio(.fit)` image behind a zoomed Canvas and no scalar `pixelsPerMeter`. Navigation mode drags pan; placement mode converts tap/drag screen coordinates through viewport inverse + map-transform inverse to a GeoPoint. Recenter anchors on current ball, or active Touch Target when explicitly selected.

`drawRemainingMarkers` consumes D10a's shared presentation unchanged；Watch does not remap colors or omit labels to save space. At 41 mm, collision handling may offset labels along the route normal or hide a lower-priority duplicate only when the same numeric value remains exposed through focus/VoiceOver；it may never swap the red/white/blue/yellow meaning. `drawDriver/drawGuidance/drawTouchTarget` consume distinct semantic style roles and retain a non-color distinction in stroke width、dash/glyph and accessibility label.

- [ ] **Step 3: Wire Watch Touch Target to the canonical recorder**

The toolbar provides “目标”, “确认”, “清除”, “取消” and recenter actions with 41/46 mm hit targets. `WatchCurrentShotTargetRecorder` is a thin wrapper over D10a's `CurrentShotTargetRecorder`/Track A producer. Placement preview is local; confirm appends `shot_target_set`; clear appends `shot_target_retracted`; cancel appends nothing. Phone/Watch simultaneous edits follow Track A entity-revision/conflict rules, not last-arrival UI state.

- [ ] **Step 4: Build localized detail and explicit zero states**

`WatchCaddieDetailView` shows up to three generated combinations using `ClubDisplayCatalog`; first leg exactly matches the root recommendation. A verified leg PlaysLike row displays `原始 N / 调整 M ↑|↓|平`; an absent row displays only the original distance. Only a valid stochastic plan displays each combination's generated `averageStrokes` as `AVG. STROKES 2.3`; route-utility、uncalibrated、unavailable or mixed-null plans display no AVG row. The Hole Root never displays it. `WatchHazardDetailView` maps kind/distance through display metadata and shows “未发现已验证的相关障碍” for an accepted empty set. Capability absence shows a localized unavailable reason and never implies “no hazards”.

`WatchMacroGreenView` may show macro slope magnitude/downhill direction only after D05 authority gates. Its navigation title, accessibility label and screenshots say “宏观坡向预览”. It must not draw synthetic contour lines or claim putt-reading parity.

All instrument detail implementations are selected only by D11's `WatchInstrumentRoute`; none owns a parallel `NavigationStack`, tab index or sibling-page gesture. `WatchRoundContainerView` pushes one route, preserves its local view state behind a higher-priority overlay while the context token remains exact, and applies the one-Back-to-root rule. Map→Hazard is an in-instrument drill-down whose Back first returns to Map；a Hazard opened from Golf Tools has no Map parent and Back returns directly to Hole Root. This parentage is frozen in the route state rather than inferred from the destination type.

- [ ] **Step 5: Run Watch interactions and 41/46 mm snapshots**

Run:

```bash
swift test --filter 'WatchMapInteractionTests|WatchGuidanceDetailsTests|WatchDesignSnapshotTests|CurrentShotTargetRecorderTests'
```

Snapshots cover facts-only ball/pin, zoom/pan alignment, target placement/confirmed/cleared, exact red-100/white-150/blue-200/yellow-250 markers with numeric/grayscale/accessibility redundancy, thin-white Driver versus thick-green Guidance versus cyan-dashed Touch Target, Driver Tee/non-Tee, separated aim/landing, verified uphill/downhill PlaysLike, moving/off/tournament/unavailable PlaysLike zero states, direct-Caddie and Tools-Caddie parity, accepted-empty/unavailable Hazard, macro-green unavailable/available, every exact Tools row and direct/Tools Back parentage at both 41/46 mm. Stochastic Caddie has legible one-decimal AVG and route-utility Caddie has no AVG. Every PlaysLike zero state preserves raw distances and contains no adjusted number、arrow or wind copy；every root snapshot contains no AVG and no extra Hazard/Green permanent icon.

- [ ] **Step 6: Commit Watch instruments**

```bash
git add mobile/ios/AICaddieWatch/Views/MapDetail/WatchMapDetailView.swift mobile/ios/AICaddieWatch/Views/Caddie/WatchCaddieDetailView.swift mobile/ios/AICaddieWatch/Views/Hazard/WatchHazardDetailView.swift mobile/ios/AICaddieWatch/Views/Green/WatchMacroGreenView.swift mobile/ios/AICaddieWatch/Services/WatchCurrentShotTargetRecorder.swift mobile/ios/AICaddieWatch/Services/WatchHoleImageStore.swift mobile/ios/AICaddieWatch/Views/WatchRoundContainerView.swift mobile/ios/AICaddieWatchTests/WatchMapInteractionTests.swift mobile/ios/AICaddieWatchTests/WatchGuidanceDetailsTests.swift mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift
git commit -m "feat: add interactive Watch guidance instruments"
```

## Task D12a: Add durable flag placement, PinPointer, and 41/46 mm parity

**Depends on:** D05/D09/D10a/D12; Track A `flag_position_set`; verified compass/heading inputs.

**Files:**
- Create: `mobile/ios/AICaddieDomain/Green/PinPointerGate.swift`
- Create: `mobile/ios/AICaddieDomainTests/PinPointerGateTests.swift`
- Create: `mobile/ios/AICaddie/Services/FlagPositionRecorder.swift`
- Create: `mobile/ios/AICaddieTests/FlagPositionRecorderTests.swift`
- Create: `mobile/ios/AICaddie/Views/Green/GreenView.swift`
- Create: `mobile/ios/AICaddie/Views/Green/PinPointerView.swift`
- Create: `mobile/ios/AICaddieWatch/Views/Green/WatchPinPointerView.swift`
- Modify: `mobile/ios/AICaddieWatch/Views/Green/WatchMacroGreenView.swift`
- Modify: `mobile/ios/AICaddieWatch/Views/WatchRoundContainerView.swift`
- Modify: `mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift`

- [ ] **Step 1: Write failing flag, heading and relevant-input tests**

Cover:

- explicit drag/tap + confirm appends one canonical `flag_position_set`; preview cancel appends nothing;
- restart/replay restores the flag and changes the `GuidanceInput/v1` `inputHash` because player flag is a relevant input;
- score/sync changes do not alter flag/map authority;
- stale/inaccurate/uncalibrated/interference heading fails PinPointer closed;
- valid heading computes shortest signed turn to the current verified flag;
- PinPointer never substitutes map bearing or a stale cached heading;
- 41/46 mm root, map, target placement, macro-green and PinPointer snapshots retain a tappable score-ring header plus the exact two-control “地图/工具” dock；PinPointer remains discoverable as the fixed fifth Golf Tools row even when heading is blocked.

- [ ] **Step 2: Implement the canonical flag recorder**

`FlagPositionRecorder` delegates to Track A's generated event builder and ledger/outbox. It requires the active round/incarnation/hole semantic subject and finite WGS84 coordinate. Updating a flag appends a superseding event; it never mutates map geometry or Green asset bytes. iOS and Watch use the same recorder. The current pin for distances/guidance is the reducer's effective flag if present, otherwise the installed Green target.

- [ ] **Step 3: Implement fail-closed PinPointer**

```swift
public enum PinPointerResult: Equatable, Sendable {
    case available(deltaDegrees: Double)
    case blocked(reasonCode: String)
}

public enum PinPointerGate {
    public static func evaluate(
        current: GeoPoint,
        flag: GeoPoint?,
        headingDegrees: Double?,
        headingAccuracyDegrees: Double?,
        headingAgeSeconds: Double,
        calibrated: Bool,
        magneticInterference: Bool,
        policy: VerifiedPinPointerPolicy
    ) -> PinPointerResult {
        // exact finite/range/age/accuracy gates, then shortest signed bearing delta
    }
}
```

The policy is versioned and signed through the engine/LRP package. Any missing flag/heading, excessive age/error, uncalibrated compass or interference returns a stable blocked reason.

- [ ] **Step 4: Keep Green claims honest**

`GreenView` and `WatchMacroGreenView` render only D05's independently promoted macro component/slope preview and the draggable flag. All copy says “宏观坡向预览”; no synthetic contour, putt break or full Garmin Green Contours parity is claimed. Full contour support is a future capability requiring a separate promoted data product and decision record.

- [ ] **Step 5: Run native parity and snapshot suites**

Run:

```bash
swift test --filter 'PinPointerGateTests|FlagPositionRecorderTests|MapMechanicsTests|WatchMapInteractionTests|WatchDesignSnapshotTests'
xcodegen generate --spec mobile/ios/project.yml --project-root .
xcodebuild test -project mobile/ios/AICaddieNative.xcodeproj -scheme AICaddie -destination "platform=iOS Simulator,name=iPhone 16,OS=latest"
xcodebuild test -project mobile/ios/AICaddieNative.xcodeproj -scheme AICaddieWatch -destination "platform=watchOS Simulator,name=Apple Watch Series 10 (46mm),OS=latest"
```

Expected: PASS; flag edits invalidate only relevant Guidance input, heading is fail-closed, and both Watch sizes preserve the single root, score ring and aligned interactive map.

- [ ] **Step 6: Commit flag and PinPointer flows**

```bash
git add mobile/ios/AICaddieDomain/Green/PinPointerGate.swift mobile/ios/AICaddieDomainTests/PinPointerGateTests.swift mobile/ios/AICaddie/Services/FlagPositionRecorder.swift mobile/ios/AICaddieTests/FlagPositionRecorderTests.swift mobile/ios/AICaddie/Views/Green/GreenView.swift mobile/ios/AICaddie/Views/Green/PinPointerView.swift mobile/ios/AICaddieWatch/Views/Green/WatchPinPointerView.swift mobile/ios/AICaddieWatch/Views/Green/WatchMacroGreenView.swift mobile/ios/AICaddieWatch/Views/WatchRoundContainerView.swift mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift
git commit -m "feat: add durable flag and pinpointer flows"
```

## Task D13: Add Web capability governance, calibration, and read-only dispersion review

**Depends on:** D02, D04, D06, D07; Plan 2 promotion/quality-report APIs and Plan 3 research-evidence APIs kept visibly distinct. Web remains a non-producing projection surface and never treats research evidence as runtime availability.

**Files:**
- Create: `web_v2/src/components/course/CapabilityBadge.tsx`
- Create: `web_v2/src/components/course/CapabilityBadge.test.tsx`
- Create: `web_v2/src/components/prep/HazardGuidancePanel.tsx`
- Create: `web_v2/src/components/prep/HazardGuidancePanel.test.tsx`
- Create: `web_v2/src/components/clubs/ClubCalibrationPanel.tsx`
- Create: `web_v2/src/components/clubs/ClubCalibrationPanel.test.tsx`
- Create: `web_v2/src/components/review/ClubDispersionPlot.tsx`
- Create: `web_v2/src/components/review/ClubDispersionPlot.test.tsx`
- Modify: `web_v2/src/components/PrepInspector.tsx`
- Modify: `web_v2/src/components/ClubBagPage.tsx`
- Modify: `web_v2/src/components/StatsDashboard.tsx`
- Modify: `web_v2/src/types.ts`

- [ ] **Step 1: Write failing governance and covariance-view tests**

```tsx
// web_v2/src/components/course/CapabilityBadge.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CapabilityBadge } from './CapabilityBadge'

describe('CapabilityBadge', () => {
  it('shows the effective reason instead of treating snapshot acceptance as live availability', () => {
    render(
      <CapabilityBadge
        capability="playsLike"
        snapshotQuality="accepted"
        effectiveAvailability="blocked"
        reasonCodes={['course_guidance_disabled']}
      />,
    )
    expect(screen.getByText('不可用')).toBeInTheDocument()
    expect(screen.getByText('course_guidance_disabled')).toBeInTheDocument()
  })
})
```

```tsx
// web_v2/src/components/review/ClubDispersionPlot.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ClubDispersionPlot, ellipseGeometry } from './ClubDispersionPlot'

describe('ClubDispersionPlot', () => {
  it('derives an ellipse from covariance rather than directional percentages', () => {
    const geometry = ellipseGeometry(64, 3, 25, 0.68)
    expect(geometry.major).toBeGreaterThanOrEqual(geometry.minor)
    render(
      <ClubDispersionPlot
        model={{
          centerAlongM: 141,
          centerCrossM: -1,
          covarianceXXM2: 64,
          covarianceXYM2: 3,
          covarianceYYM2: 25,
          confidence: 0.68,
          sampleSize: 28,
          calibrationVersion: 'calibration-v1',
        }}
      />,
    )
    expect(screen.getByLabelText('68% 置信二维散布，28 个样本')).toBeInTheDocument()
  })

  it('renders an honest absence state without a decorative ellipse', () => {
    render(<ClubDispersionPlot model={null} />)
    expect(screen.getByText('尚无已校准二维散布')).toBeInTheDocument()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })
})
```

```tsx
// web_v2/src/components/prep/HazardGuidancePanel.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HazardGuidancePanel } from './HazardGuidancePanel'

describe('HazardGuidancePanel', () => {
  it('distinguishes the hazard front from the distance required to clear it', () => {
    render(
      <HazardGuidancePanel
        hazards={[{
          hazardRef: 'hazard:water',
          kind: 'water',
          enterDistanceM: 132,
          clearDistanceM: 151,
          evidenceRefs: ['quality:water:v4'],
        }]}
      />,
    )
    expect(screen.getByText(/前沿 144 码/)).toBeInTheDocument()
    expect(screen.getByText(/越过 165 码/)).toBeInTheDocument()
  })

  it('preserves multiple promoted rows and distinguishes accepted empty', () => {
    const { rerender } = render(
      <HazardGuidancePanel hazards={[
        { hazardRef: 'hazard:bunker-1', kind: 'bunker', enterDistanceM: 120, clearDistanceM: 132, evidenceRefs: ['evidence:bunker-1'] },
        { hazardRef: 'hazard:water-2', kind: 'water', enterDistanceM: 140, clearDistanceM: 155, evidenceRefs: ['evidence:water-2'] },
      ]} />,
    )
    expect(screen.getAllByRole('article')).toHaveLength(2)
    rerender(<HazardGuidancePanel hazards={[]} />)
    expect(screen.getByText('已验证：本洞无晋升障碍')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the Web tests and verify they fail**

Run:

```bash
cd web_v2
npm test -- --run \
  src/components/course/CapabilityBadge.test.tsx \
  src/components/prep/HazardGuidancePanel.test.tsx \
  src/components/review/ClubDispersionPlot.test.tsx
```

Expected: FAIL because the new components do not exist.

- [ ] **Step 3: Implement effective-capability and evidence panels**

```tsx
// web_v2/src/components/course/CapabilityBadge.tsx
type CapabilityBadgeProps = {
  capability: string
  snapshotQuality: 'accepted' | 'degraded' | 'blocked'
  effectiveAvailability: 'available' | 'degraded' | 'blocked'
  reasonCodes: string[]
}

export function CapabilityBadge({
  capability,
  snapshotQuality,
  effectiveAvailability,
  reasonCodes,
}: CapabilityBadgeProps): React.ReactElement {
  const label = effectiveAvailability === 'available'
    ? '可用'
    : effectiveAvailability === 'degraded'
      ? '降级'
      : '不可用'
  return (
    <section aria-label={`${capability} capability`}>
      <strong>{capability}</strong>
      <span>{label}</span>
      <small>Snapshot: {snapshotQuality}</small>
      {reasonCodes.map((reason) => <code key={reason}>{reason}</code>)}
    </section>
  )
}
```

`PrepInspector` derives these display props from the generated read-only Snapshot/Install/Runtime/Effective projection returned by the governance API. `CapabilityBadge` never returns a gate token and is not imported by any Guidance producer; only the verifier-only Apple token and D02b server object can enable runtime consumers.

```tsx
// web_v2/src/components/prep/HazardGuidancePanel.tsx
import type { GuidanceHazardV1 } from '../../contracts/generated'

const yards = (meters: number): number => Math.round(meters * 1.0936133)

export function HazardGuidancePanel({ hazards }: { hazards: GuidanceHazardV1[] }): React.ReactElement {
  return (
    <section aria-label="晋升后的障碍指导">
      {hazards.length === 0 ? <p>已验证：本洞无晋升障碍</p> : null}
      {hazards.map((hazard) => (
        <article key={hazard.hazardRef}>
          <strong>{hazard.kind}</strong>
          <span>前沿 {yards(hazard.enterDistanceM)} 码</span>
          {hazard.clearDistanceM == null
            ? null
            : <span>越过 {yards(hazard.clearDistanceM)} 码</span>}
          <small>{hazard.evidenceRefs.join(' · ')}</small>
        </article>
      ))}
    </section>
  )
}
```

```tsx
// web_v2/src/components/clubs/ClubCalibrationPanel.tsx
import type { GuidanceClubCalibrationV1 } from '../../contracts/generated'

export function ClubCalibrationPanel({ rows }: { rows: GuidanceClubCalibrationV1[] }): React.ReactElement {
  return (
    <section aria-label="球杆校准">
      {rows.map((row) => (
        <article key={row.clubRef}>
          <strong>{row.clubRef}</strong>
          <span>{row.available && row.dispersion ? `${row.dispersion.sampleSize} 个确认样本` : '尚未校准'}</span>
          <small>{row.dispersion?.calibrationVersion ?? row.policyVersion}</small>
          <small>{row.evidenceRefs.join(' · ')}</small>
        </article>
      ))}
    </section>
  )
}
```

- [ ] **Step 4: Implement the true covariance review plot**

```tsx
// web_v2/src/components/review/ClubDispersionPlot.tsx
import type { ClubCalibrationDispersionV1 } from '../../contracts/generated'

export type DispersionModel = ClubCalibrationDispersionV1

export function ellipseGeometry(
  covarianceXXM2: number,
  covarianceXYM2: number,
  covarianceYYM2: number,
  confidence: number,
): { major: number; minor: number; angleDegrees: number } {
  if (!(confidence > 0 && confidence < 1)) {
    throw new Error('confidence must be between zero and one')
  }
  const trace = covarianceXXM2 + covarianceYYM2
  const discriminant = Math.sqrt(
    Math.max(0, (covarianceXXM2 - covarianceYYM2) ** 2 + 4 * covarianceXYM2 ** 2),
  )
  const majorVariance = Math.max(0, (trace + discriminant) / 2)
  const minorVariance = Math.max(0, (trace - discriminant) / 2)
  const scale = Math.sqrt(-2 * Math.log(1 - confidence))
  return {
    major: scale * Math.sqrt(majorVariance),
    minor: scale * Math.sqrt(minorVariance),
    angleDegrees: 0.5 * Math.atan2(
      2 * covarianceXYM2,
      covarianceXXM2 - covarianceYYM2,
    ) * 180 / Math.PI,
  }
}

export function ClubDispersionPlot({ model }: { model: DispersionModel | null }): React.ReactElement {
  if (model == null) {
    return <p>尚无已校准二维散布</p>
  }
  const ellipse = ellipseGeometry(
    model.covarianceXXM2,
    model.covarianceXYM2,
    model.covarianceYYM2,
    model.confidence,
  )
  const pixelsPerMeter = 0.5
  return (
    <svg
      role="img"
      aria-label={`${Math.round(model.confidence * 100)}% 置信二维散布，${model.sampleSize} 个样本`}
      viewBox="-100 -100 200 200"
    >
      <line x1="0" y1="90" x2="0" y2="-90" stroke="currentColor" />
      <ellipse
        cx={model.centerCrossM * pixelsPerMeter}
        cy={-model.centerAlongM * pixelsPerMeter}
        rx={ellipse.minor * pixelsPerMeter}
        ry={ellipse.major * pixelsPerMeter}
        transform={`rotate(${ellipse.angleDegrees} ${model.centerCrossM * pixelsPerMeter} ${-model.centerAlongM * pixelsPerMeter})`}
        fill="rgba(59,130,246,0.18)"
        stroke="currentColor"
      />
    </svg>
  )
}
```

`PrepInspector` hosts `CapabilityBadge` and `HazardGuidancePanel`; `ClubBagPage` hosts calibration status; `StatsDashboard` hosts `ClubDispersionPlot` only for generated calibrated models. Remove any path that turns the old four directional percentages into a Caddie input.

- [ ] **Step 5: Add and run the ClubCalibrationPanel test plus full Web checks**

```tsx
// web_v2/src/components/clubs/ClubCalibrationPanel.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ClubCalibrationPanel } from './ClubCalibrationPanel'

describe('ClubCalibrationPanel', () => {
  it('shows versioned confirmed sample provenance', () => {
    render(
      <ClubCalibrationPanel
        rows={[{
          clubRef: 'club:iron7',
          available: true,
          reasonCodes: [],
          dispersion: {
            centerAlongM: 141,
            centerCrossM: -1,
            covarianceXXM2: 64,
            covarianceXYM2: 3,
            covarianceYYM2: 25,
            confidence: 0.68,
            sampleSize: 28,
            calibrationVersion: 'club-calibration-v1:model-1',
          },
          policyVersion: 'club-calibration-policy-v1',
          evidenceRefs: ['event:11111111-1111-4111-8111-111111111111', 'event:22222222-2222-4222-8222-222222222222'],
        }]}
      />,
    )
    expect(screen.getByText('28 个确认样本')).toBeInTheDocument()
    expect(screen.getByText('club-calibration-v1:model-1')).toBeInTheDocument()
  })
})
```

Run:

```bash
cd web_v2
npm test -- --run \
  src/components/course/CapabilityBadge.test.tsx \
  src/components/prep/HazardGuidancePanel.test.tsx \
  src/components/clubs/ClubCalibrationPanel.test.tsx \
  src/components/review/ClubDispersionPlot.test.tsx \
  src/components/PrepPage.test.tsx \
  src/components/ClubBagPage.test.tsx \
  src/components/StatsDashboard.test.tsx
npm run lint
npm run build
```

Expected: all selected tests PASS, ESLint exits 0, TypeScript/Vite build exits 0. No component requests browser geolocation or writes RoundEvent.

- [ ] **Step 6: Commit Web governance and review surfaces**

```bash
git add web_v2/src/components/course/CapabilityBadge.tsx web_v2/src/components/course/CapabilityBadge.test.tsx web_v2/src/components/prep/HazardGuidancePanel.tsx web_v2/src/components/prep/HazardGuidancePanel.test.tsx web_v2/src/components/clubs/ClubCalibrationPanel.tsx web_v2/src/components/clubs/ClubCalibrationPanel.test.tsx web_v2/src/components/review/ClubDispersionPlot.tsx web_v2/src/components/review/ClubDispersionPlot.test.tsx web_v2/src/components/PrepInspector.tsx web_v2/src/components/ClubBagPage.tsx web_v2/src/components/StatsDashboard.tsx web_v2/src/types.ts
git commit -m "feat: add Web capability and calibration review"
```

## Task D14: Wire the Track A manual producer into the S70 current-hole flow

**Depends on:** Track A `ManualShotProducer`, `DomainEventBuilder`, `DomainLedgerStore`, canonical `shot_recorded` schema, outbox/receipt handling and recovery tests complete.

**Files:**
- Reuse: `mobile/ios/AICaddieDomain/ShotCapture/ManualShotProducer.swift`
- Reuse: `mobile/ios/AICaddieDomain/ShotCapture/ShotCaptureSession.swift`
- Reuse: `mobile/ios/AICaddieDomainTests/ManualShotProducerTests.swift`
- Reuse: `mobile/ios/AICaddieDomainTests/PlayerLiveFactProducerTests.swift`
- Create: `mobile/ios/AICaddie/Services/CurrentHoleManualShotRecorder.swift`
- Create: `mobile/ios/AICaddieTests/CurrentHoleManualShotRecorderTests.swift`
- Modify: `mobile/ios/AICaddie/Views/CurrentHoleView.swift:1092-1165`
- Modify: `mobile/ios/AICaddieWatch/Services/WatchDomainCoordinator.swift`
- Modify: `mobile/ios/AICaddieWatch/Models/WatchRoundModel.swift`
- Modify: `mobile/ios/AICaddie/Services/WatchEventBridge.swift`
- Test: `mobile/ios/AICaddieTests/WatchEventBridgeTests.swift`
- Test: `mobile/ios/AICaddieWatchTests/WatchRoundModelTests.swift`

- [ ] **Step 1: Verify the Track A producer gate**

Run:

```bash
test -f mobile/ios/AICaddieDomain/ShotCapture/ManualShotProducer.swift
test -f mobile/ios/AICaddieDomain/ShotCapture/ShotCaptureSession.swift
swift test --filter 'ManualShotProducerTests|PlayerLiveFactProducerTests'
```

Expected: the file check exits 0 and Track A tests PASS. The emitted event must use:

```text
kind = shot_recorded
entityRef = round:{roundId}:shot:{shotId}
payload = shotId/hole/latitude/longitude/horizontalAccuracyM/lie/provenance
provenance = manual
signature = ManualShotProducer.record(_:session:builder:occurredAt:)
commit = ShotCaptureSession.appendShotAndReserveNext(_:)
```

The payload contains no `guidanceId`, `candidateHash`, `recommendedClubRef` or `actualClubRef`. If this gate fails, complete Track A rather than defining another producer in Track D.

`lie` is the start lie where this full shot is struck, not its landing result. Production values are `tee|fairway|rough|bunker|fringe|other`; water/penalty outcome and Green putting are not emitted as full-shot start lies. Putts are recorded only through hole-score facts. The first shot's landing classification may preselect later score/fairway UI, but it does not rewrite this start-lie field.

- [ ] **Step 2: Write failing iOS integration and recommendation-separation tests**

```swift
// mobile/ios/AICaddieTests/CurrentHoleManualShotRecorderTests.swift
import Foundation
import XCTest
import AICaddieDomain
@testable import AICaddie

final class CurrentHoleManualShotRecorderTests: XCTestCase {
    private struct Dependencies {
        let root: URL
        let ledger: DomainLedgerStore
        let builder: DomainEventBuilder
        let session: ShotCaptureSession
    }

    private func dependencies() throws -> Dependencies {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let ledger = try DomainLedgerStore(directoryURL: root.appendingPathComponent("ledger"))
        let builder = try DomainEventBuilder.fixture(
            roundId: "11111111-1111-4111-8111-111111111111",
            originURL: root.appendingPathComponent("origin-sequence.json")
        )
        let session = try ShotCaptureSession(ledger: ledger, context: builder.context)
        return Dependencies(root: root, ledger: ledger, builder: builder, session: session)
    }

    func testTargetRestartAndManualShotReuseThenRotateThePreallocatedUUID() throws {
        let values = try dependencies()
        let preallocated = values.session.shotId
        let emptyProjection = try DomainRoundReducer().reduce(
            [],
            replication: DomainReplicationContext(
                pendingCount: 0,
                syncing: false,
                deadLetterCount: 0
            )
        )
        let target = try PlayerLiveFactProducer().setShotTarget(
            session: values.session, targetRef: "touch:7:1", latitude: 22.2795, longitude: 114.162,
            provenance: .explicitTouchTarget, builder: values.builder, projection: emptyProjection,
            occurredAt: "2026-07-18T09:59:59.000Z"
        )
        try values.session.appendTarget(target)
        let restartedLedger = try DomainLedgerStore(directoryURL: values.root.appendingPathComponent("ledger"))
        let restarted = try ShotCaptureSession(ledger: restartedLedger, context: values.builder.context)
        let event = try CurrentHoleManualShotRecorder().record(
            hole: 7,
            latitude: 22.279,
            longitude: 114.162,
            horizontalAccuracyM: 4.0,
            lie: "fairway",
            session: restarted,
            builder: values.builder,
            occurredAt: "2026-07-18T10:00:00.000Z"
        )
        XCTAssertEqual(target.payload["shotId"], .string(preallocated))
        XCTAssertEqual(event.payload["shotId"], .string(preallocated))
        XCTAssertEqual(event.payload["latitude"], .number(22.279))
        XCTAssertEqual(event.payload["longitude"], .number(114.162))
        XCTAssertEqual(event.payload["horizontalAccuracyM"], .number(4.0))
        XCTAssertEqual(event.payload["provenance"], .string("manual"))
        XCTAssertEqual(try restartedLedger.allEvents(), [target, event])
        XCTAssertNotEqual(restarted.shotId, preallocated)
    }

    func testGuidanceRecommendationIsNotPartOfManualShotRecording() throws {
        let values = try dependencies()
        let event = try CurrentHoleManualShotRecorder().record(
            hole: 7,
            latitude: 22.279,
            longitude: 114.162,
            horizontalAccuracyM: nil,
            lie: "fairway",
            session: values.session,
            builder: values.builder,
            occurredAt: "2026-07-18T10:00:00.000Z"
        )
        XCTAssertNil(event.payload["guidanceId"])
        XCTAssertNil(event.payload["recommendedClubRef"])
        XCTAssertNil(event.payload["actualClubRef"])
    }

    func testAtomicShotCommitIsIdempotentAndNeverReusesCompletedUUID() throws {
        let values = try dependencies()
        let preallocated = values.session.shotId
        let event = try CurrentHoleManualShotRecorder().record(
            hole: 7, latitude: 22.279, longitude: 114.162, horizontalAccuracyM: 4, lie: "fairway",
            session: values.session, builder: values.builder,
            occurredAt: "2026-07-18T10:00:00.000Z"
        )
        let next = values.session.shotId
        XCTAssertNotEqual(next, preallocated)
        try values.session.appendShotAndReserveNext(event)
        XCTAssertEqual(values.session.shotId, next)
        XCTAssertEqual(try values.ledger.allEvents().filter { $0.kind == .shotRecorded }, [event])
    }
}
```

Add to `WatchEventBridgeTests.swift`:

```swift
func testCanonicalManualShotRelayPreservesIdentityAndPayload() throws {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    let sourceLedger = try DomainLedgerStore(directoryURL: root.appendingPathComponent("watch"))
    let phoneLedger = try DomainLedgerStore(directoryURL: root.appendingPathComponent("phone"))
    let builder = try DomainEventBuilder.fixture(
        roundId: "11111111-1111-4111-8111-111111111111",
        originURL: root.appendingPathComponent("origin-sequence.json")
    )
    let session = try ShotCaptureSession(ledger: sourceLedger, context: builder.context)
    let event = try ManualShotProducer().record(
        ManualShotDraft(
            hole: 7,
            latitude: 22.279,
            longitude: 114.162,
            horizontalAccuracyM: 4.0,
            lie: "fairway"
        ),
        session: session,
        builder: builder,
        occurredAt: "2026-07-18T10:00:00.000Z"
    )
    try session.appendShotAndReserveNext(event)
    try WatchEventBridge.relayCanonicalEvent(event, into: phoneLedger)
    XCTAssertEqual(try phoneLedger.allEvents(), [event])
}
```

Add to `WatchRoundModelTests.swift`:

```swift
@MainActor
func testWatchCoordinatorCommitsShotAndReservesNextUUIDAtomically() throws {
    let coordinator = try WatchDomainCoordinator.makeForTest()
    let preallocated = coordinator.shotCaptureSession.shotId
    let event = try coordinator.recordManualShot(
        hole: 7, latitude: 22.279, longitude: 114.162,
        horizontalAccuracyM: 4, lie: "fairway"
    )
    XCTAssertNotEqual(coordinator.shotCaptureSession.shotId, preallocated)
    let next = coordinator.shotCaptureSession.shotId
    try coordinator.shotCaptureSession.appendShotAndReserveNext(event)
    XCTAssertEqual(coordinator.shotCaptureSession.shotId, next)
    XCTAssertEqual(try coordinator.ledger.allEvents().filter { $0.kind == .shotRecorded }, [event])
}
```

- [ ] **Step 3: Run the integration tests and verify they fail**

Run:

```bash
swift test --filter AICaddieTests.CurrentHoleManualShotRecorderTests
swift test --filter AICaddieTests.WatchEventBridgeTests
```

Expected: FAIL because `CurrentHoleManualShotRecorder` and `relayCanonicalEvent` do not exist.

- [ ] **Step 4: Implement the thin iOS recorder over Track A**

Use the authoritative Plan 1 `ShotCaptureSession`. After Track A's deterministic V2→V3 migration, it stores the active slot inside the authoritative current `DomainLedgerStateV3`, which preserves all V2 transport state including `deadLetters` and `acceptedAwaitingCanonicalReplay`. Track D calls only the public ledger/session transaction APIs；it must not decode or mutate a storage-version struct directly and must not add a URL sidecar、rotation method or reconciliation store.

```swift
// mobile/ios/AICaddie/Services/CurrentHoleManualShotRecorder.swift
import AICaddieDomain

struct CurrentHoleManualShotRecorder {
    private let producer = ManualShotProducer()

    func record(
        hole: Int,
        latitude: Double,
        longitude: Double,
        horizontalAccuracyM: Double?,
        lie: String,
        session: ShotCaptureSession,
        builder: DomainEventBuilder,
        occurredAt: String
    ) throws -> DomainRoundEvent {
        let event = try producer.record(
            ManualShotDraft(
                hole: hole,
                latitude: latitude,
                longitude: longitude,
                horizontalAccuracyM: horizontalAccuracyM,
                lie: lie
            ),
            session: session,
            builder: builder,
            occurredAt: occurredAt
        )
        try session.appendShotAndReserveNext(event)
        return event
    }
}
```

`CurrentHoleView` creates or reopens exactly one `ShotCaptureSession(ledger:context:)` for the round incarnation and passes it to Touch Target, manual shot and later confirmed AutoShot paths. `submitEvents()` calls the recorder only from the explicit “记一杆” action and passes current GPS/lie facts. Its `hole` argument is the active round-unique `scoreSlot` from D14b's frozen LRP sequence; physical map subject and displayed hole label are resolved separately from that row, so no producer writes provider/local hole numbers by guessing. The current Guidance candidate is not an argument. `appendShotAndReserveNext` atomically writes event/outbox, completes the old slot and reserves the next legal UUID; restart reads that state from the ledger, so an already durable shot ID cannot be reused. Explicit club input emits the separate Track A `actual_club_set` event for the returned shot ID; a recommendation never fills that field.

- [ ] **Step 5: Relay the canonical event unchanged and connect Watch manual input**

Add to `WatchEventBridge.swift`:

```swift
public static func relayCanonicalEvent(
    _ event: DomainRoundEvent,
    into ledger: DomainLedgerStore
) throws {
    try ledger.appendIfIdentityHashMatches(event)
}
```

In `WatchDomainCoordinator`, keep the same ledger-backed session and replace legacy `WatchInputEvent`/distance→club construction with this atomic method:

```swift
@discardableResult
public func recordManualShot(
    hole: Int,
    latitude: Double,
    longitude: Double,
    horizontalAccuracyM: Double?,
    lie: String
) throws -> DomainRoundEvent {
    let event = try ManualShotProducer().record(
        ManualShotDraft(
            hole: hole,
            latitude: latitude,
            longitude: longitude,
            horizontalAccuracyM: horizontalAccuracyM,
            lie: lie
        ),
        session: shotCaptureSession,
        builder: eventBuilder,
        occurredAt: CanonicalTimestamp.now()
    )
    try shotCaptureSession.appendShotAndReserveNext(event)
    projection = try DomainRoundReducer().reduce(
        ledger.projectionInputs(roundId: event.roundId),
        replication: ledger.replicationContext(roundId: event.roundId)
    )
    return event
}
```

`WatchDomainCoordinator.makeForTest` and production startup construct `ShotCaptureSession(ledger:domainLedger, context:eventBuilder.context)`. The session reloads the active reserved slot from the same ledger state, so there is no separate reconciliation phase. The bridge transports the exact `DomainRoundEvent`; it does not create a phone-origin copy, change the entityRef or rewrite provenance.

- [ ] **Step 6: Run manual-shot, bridge, ledger, and restart regressions**

Run:

```bash
swift test --filter AICaddieDomainTests.ManualShotProducerTests
swift test --filter AICaddieTests.CurrentHoleManualShotRecorderTests
swift test --filter AICaddieTests.WatchEventBridgeTests
swift test --filter AICaddieWatchTests.WatchRoundModelTests
! rg -n 'DomainLedgerStateV2|loadV2\(|validateStorageV2' mobile/ios/AICaddie/Services/CurrentHoleManualShotRecorder.swift mobile/ios/AICaddie/Views/CurrentHoleView.swift mobile/ios/AICaddieWatch/Services/WatchDomainCoordinator.swift mobile/ios/AICaddieWatch/Models/WatchRoundModel.swift mobile/ios/AICaddie/Services/WatchEventBridge.swift
```

Expected: all tests PASS and the source-boundary scan exits 0 with no stale V2 storage API reference；target and manual capture reuse one legal preallocated UUID, one explicit manual action atomically appends one canonical `shot_recorded` plus outbox state and reserves the next UUID, idempotent retry does not duplicate or rotate again, restart reloads the next reserved slot from V3, every pre-migration dead letter/accepted-awaiting receipt remains intact, the event remains pending until its receipt, and recommendation/actual fields remain absent.

- [ ] **Step 7: Commit the S70 manual-shot integration**

```bash
git add mobile/ios/AICaddie/Services/CurrentHoleManualShotRecorder.swift mobile/ios/AICaddieTests/CurrentHoleManualShotRecorderTests.swift mobile/ios/AICaddie/Views/CurrentHoleView.swift mobile/ios/AICaddieWatch/Services/WatchDomainCoordinator.swift mobile/ios/AICaddieWatch/Models/WatchRoundModel.swift mobile/ios/AICaddie/Services/WatchEventBridge.swift mobile/ios/AICaddieTests/WatchEventBridgeTests.swift mobile/ios/AICaddieWatchTests/WatchRoundModelTests.swift
git commit -m "feat: connect manual shots to S70 current-hole flow"
```

## Task D14a: Implement partitioned shot-station reconciliation and Club Prompt semantics

**Depends on:** D14; Track A reducer/event schemas. This task implements locked T054/T055 behavior before AutoShot may emit a confirmed shot.

**Product law:** Tee observations expose only the last effective shot. Non-Tee near-station grouping is an app-owned, LRP-pinned, versioned heuristic requiring field validation; it is not described as Garmin's exact threshold or as a separately signed Garmin policy. `fat_or_very_short` is the only player-visible split/recovery reason. The reducer proposes; only the canonicalizer changes ledger facts through Track A's ordinary append/shot-claim boundary.

**Files:**
- Create: `contracts/canonical/shot_recovery_policy_v1.schema.json`
- Create: `contracts/canonical/fixtures/shot_recovery_policy_golden.json`
- Modify: `contracts/canonical/live_round_package_v2.schema.json`
- Modify: `contracts/canonical/canonical_object_registry.json`
- Modify: `contracts/canonical/reason_codes.json`
- Modify: `tools/contracts/generate_contracts.py`
- Modify: `tests/test_contract_codegen.py`
- Regenerate: `ai_caddie/contracts/generated.py`、`mobile/ios/AICaddieDomain/GeneratedContracts.swift`、`web_v2/src/contracts/generated.ts`
- Create: `mobile/ios/AICaddieDomain/ShotCapture/ShotRecoveryPolicy.swift`
- Create: `mobile/ios/AICaddieDomain/ShotCapture/ShotObservationJournal.swift`
- Create: `mobile/ios/AICaddieDomain/ShotCapture/ShotStationObservationProjector.swift`
- Create: `mobile/ios/AICaddieDomain/ShotCapture/ShotStationReducer.swift`
- Create: `mobile/ios/AICaddieDomain/ShotCapture/ShotStationCanonicalizer.swift`
- Create: `mobile/ios/AICaddieDomain/ShotCapture/ShotRecoveryEventProducer.swift`
- Create: `mobile/ios/AICaddieDomain/ShotCapture/ClubPromptProducer.swift`
- Create: `mobile/ios/AICaddieDomain/ShotCapture/ClubPromptVisibleCountdown.swift`
- Modify: `mobile/ios/AICaddieDomain/Presentation/GuidanceReasonLocalizer.swift`
- Modify: `mobile/ios/AICaddieDomain/ShotCapture/ManualShotProducer.swift`
- Modify: `mobile/ios/AICaddieDomain/DomainLedgerStore.swift`
- Create: `mobile/ios/AICaddieDomainTests/ShotCaptureRecoveryTests.swift`
- Create: `mobile/ios/AICaddieDomainTests/ClubPromptRecoveryTests.swift`
- Create: `mobile/ios/AICaddieDomainTests/GuidanceReasonLocalizerTests.swift`
- Create: `mobile/ios/AICaddieWatch/Services/WatchShotRecoveryCoordinator.swift`
- Create: `mobile/ios/AICaddieWatch/Views/ShotCapture/WatchShotRecoveryView.swift`
- Create: `mobile/ios/AICaddieWatch/Views/ShotCapture/WatchClubPromptView.swift`
- Modify: `mobile/ios/AICaddieWatch/Views/WatchRoundContainerView.swift`
- Create: `mobile/ios/AICaddieWatchTests/WatchShotRecoveryCoordinatorTests.swift`
- Create: `mobile/ios/AICaddie/Views/Live/ShotRecoveryBanner.swift`
- Modify: `mobile/ios/AICaddie/Views/CurrentHoleView.swift`
- Modify: `ai_caddie/history/history_stats.py`
- Modify: `ai_caddie/players/club_calibration.py`
- Create: `tests/test_shot_station_statistics.py`

- [ ] **Step 1: Write failing partition, proposal, canonical and recovery tests**

Add exact tests:

- `testTeeLastWinsAppendsCanonicalRetractionsAndLedgerStatsCalibrationAgree`;
- `testTeeLastWinsNeverOrdersDifferentOriginClockDomainsAndRequiresManualConflictResolution`;
- `testNonTeeGroupingRequiresSignedAppOwnedHeuristicAccuracyAndFollowingPathEvidence`;
- `testNonTeeReturnExcursionAtThresholdKeepsBothShotsAndBelowThresholdCanProposeGrouping`;
- `testMissingOrContradictoryReturnPathEvidenceKeepsBothShots`;
- `testShotRecoveryPolicyIdBindsEveryThresholdAndCannotChangeDuringRound`;
- `testOnlyFatOrVeryShortCreatesOneNewCausallyLinkedRestoredShotId`;
- `testPriorRoundPendingCandidateCannotAppearOrRestoreInCurrentIncarnation`;
- `testStaleRecoveryForUngroupedShotFailsClosedWithoutDuplicateStation`;
- `testCrashBeforeAndAfterCanonicalAppendReusesStableTransactionAndEventBytes`;
- `testRetractionCausesEffectiveShotEventAndPeerReplayPreservesTheCausalChain`;
- `testManualCorrectionReprojectsObservationAndReconcilesDeterministically`;
- `testObservationProjectorUsesShotOriginPlusMonotonicFollowingPathNotBatchArrival`;
- `testNonFiniteOutOfRangeOrInvalidUUIDObservationFailsBeforeJournalMutation`;
- `testInterruptedAtomicWriteAndTruncatedJournalFailClosedWithoutLosingPreparedRecords`;
- `testRetentionBoundsTerminalHistoryPerPartitionButNeverDropsPendingPreparedOrReferencedRecords`;
- `testScoreOverlayPausesClubPromptCountdownAndResumeDoesNotSubmit`;
- `testRecoveryCardForegroundClockPausesBehindScoreAndClubPromptAndExpiryWritesNothing`;
- `testRecoveryRemainsReachableAfterDismissRestartAndFromArbitraryHoleEdit`;
- `testScoreOpenDrainsExistingStationReconciliationBeforeFreezingSuggestion`;
- `testScoreOpenVersusLateRetractionRaceEitherCountsRetractedSetOrDefersWithoutMutatingFrozenSuggestion`;
- `testClubPromptSelectOrSkipWritesOnlyActualClubSetAndRecommendationNeverBecomesActual`.
- `testClubPromptCancelDismissesWithoutActualClubWriteOrShotRetractionAndHistoryCanEditLater`.

The initial policy fixture uses an evidence ref such as `owner-cohort-seed:shot-station-grouping:v1`; no fixture claims completed field validation or names Garmin as the source of the threshold. Promotion beyond the Owner/internal cohort replaces that ref with a checked evidence artifact and a new policy ID.

- [ ] **Step 2: Define every durable partitioned type**

```swift
public struct ShotRecoveryPolicy: Codable, Equatable, Sendable {
    public let schema: String                 // ai-caddie-shot-recovery-policy-v1
    public let policyId: String               // typed ID over every field below
    public let policyVersion: String
    public let baseStationRadiusM: Double
    public let maximumStationRadiusM: Double
    public let accuracyRadiusMultiplier: Double
    public let maximumHorizontalAccuracyM: Double
    public let minimumReturnExcursionM: Double
    public let minimumReturnPathLengthM: Double
    public let recoveryPromptVisibleSeconds: Double
    public let evidenceRefs: [String]

    public func stationRadius(firstAccuracyM: Double, secondAccuracyM: Double) -> Double {
        min(
            maximumStationRadiusM,
            baseStationRadiusM
                + accuracyRadiusMultiplier * (firstAccuracyM + secondAccuracyM)
        )
    }
}

public struct ShotJournalPartition: Codable, Hashable, Sendable {
    public let roundId: String
    public let roundIncarnationId: String
}

public enum ShotStationLie: String, Codable, Sendable {
    case tee
    case fairway
    case rough
    case bunker
    case fringe
    case other
}

public struct ShotStationObservation: Codable, Equatable, Sendable {
    public let partition: ShotJournalPartition
    public let shotId: String
    public let hole: Int
    public let startLie: ShotStationLie
    public let eastM: Double
    public let northM: Double
    public let horizontalAccuracyM: Double
    public let impactMonotonicSeconds: Double
    public let followingPathAdvanceM: Double
    public let precedingObservationId: String?
    public let interImpactPathLengthM: Double
    public let maximumExcursionFromPrecedingStationM: Double
    public let returnedToPrecedingStation: Bool
    public let sourceRevisionOrdinal: UInt64
    public let originDeviceId: String
    public let originEpoch: String
    public let sourceClientSequence: UInt64
    public let sourceEventId: String
    public let evidenceRefs: [String]
}

public enum ShotStationSuppressionReason: String, Codable, Sendable {
    case teeLastWins = "tee_last_wins"
    case appNearStationGrouping = "app_near_station_grouping"
}

public struct ShotStationDecision: Codable, Equatable, Sendable {
    public let decisionId: String
    public let partition: ShotJournalPartition
    public let primaryShotId: String
    public let suppressedShotIds: [String]
    public let reason: ShotStationSuppressionReason
    public let policyId: String
    public let policyVersion: String
    public let evidenceRefs: [String]
}

public enum ShotRecoveryReason: String, Codable, Sendable {
    case fatOrVeryShort = "fat_or_very_short"
}

public enum ShotRecoveryDisposition: String, Codable, Sendable {
    case prepared
    case appended
}

public struct ShotRecoveryRecord: Codable, Equatable, Sendable {
    public let recoveryId: String
    public let partition: ShotJournalPartition
    public let hole: Int
    public let suppressedShotId: String
    public let restoredShotId: String
    public let reason: ShotRecoveryReason
    public let canonicalRetractionEventId: String
    public let transactionId: String
    public let canonicalEventBytes: Data
    public var disposition: ShotRecoveryDisposition
    public let recordedAt: String
}
```

`ShotRecoveryPolicy/v1` is an exact canonical object registered as `ShotRecoveryPolicy/v1` and pinned by `LiveRoundPackageV2.shotRecoveryPolicyId`; the LRP carries the exact canonical policy body/hash, so a round never changes thresholds after start. The verifier requires finite non-negative values, `0 < baseStationRadiusM <= maximumStationRadiusM <= 25`、`0 <= accuracyRadiusMultiplier <= 2`、`0 < maximumHorizontalAccuracyM <= 20`、`maximumStationRadiusM < minimumReturnExcursionM <= 100`、`minimumReturnExcursionM <= minimumReturnPathLengthM <= 500`、`3 <= recoveryPromptVisibleSeconds <= 30` and sorted-unique non-empty evidence. It recomputes `policyId`; callers cannot construct a verified policy from local preferences or a mutable remote flag. The trust comes from the verified LRP/round binding, not a fictional detached signature on this policy object.

Freeze the registry entry and exact root keys rather than using a wildcard identity:

```json
{
  "ShotRecoveryPolicy": {
    "domainTag": "ShotRecoveryPolicy/v1",
    "schemaRef": "contracts/canonical/shot_recovery_policy_v1.schema.json",
    "includedFields": [
      "schema",
      "policyVersion",
      "baseStationRadiusM",
      "maximumStationRadiusM",
      "accuracyRadiusMultiplier",
      "maximumHorizontalAccuracyM",
      "minimumReturnExcursionM",
      "minimumReturnPathLengthM",
      "recoveryPromptVisibleSeconds",
      "evidenceRefs"
    ],
    "excludedFields": ["policyId"]
  }
}
```

`shot_recovery_policy_v1.schema.json` has exactly those ten included keys plus required `policyId`, `additionalProperties=false`, the numeric constraints above and canonical sorted-unique `evidenceRefs`. `live_round_package_v2.schema.json` adds exactly `shotRecoveryPolicyId` and `shotRecoveryPolicy`; the ID must equal the embedded body's recomputed ID. Generated Python/Swift/TypeScript decoders and the shared golden fixture reject a body/ID mismatch, a changed threshold under the same ID, an unknown key and a low/high boundary violation.

The same contract-owner checkpoint appends exactly these stable reason codes used by D14a/D14b: `tee_last_wins`、`tee_cross_device_order_ambiguous`、`app_near_station_grouping`、`fat_or_very_short`、`shot_recovery_source_not_suppressed`、`green_departure_default`、`possible_chip_in`、`unobserved_putts_two_putt_estimate`、`incomplete_shot_evidence_par_floor` and `manual_transition_two_putt_estimate`. The localization catalog must cover all ten before either Watch or iOS can show the associated proposal/suggestion; unknown raw codes remain diagnostic-only.

The initial Owner-cohort seed is exact and versioned: `baseStationRadiusM=2.0`、`maximumStationRadiusM=10.0`、`accuracyRadiusMultiplier=0.5`、`maximumHorizontalAccuracyM=8.0`、`minimumReturnExcursionM=18.0`、`minimumReturnPathLengthM=30.0`、`recoveryPromptVisibleSeconds=12.0`. It is a conservative app policy to validate, not a claim about Garmin's private threshold. Changing any threshold or promoting it to a broader cohort requires a new policy ID and evidence ref; it never silently edits the behavior of an active round.

Every initializer/decoder validates lowercase UUIDs; `hole ∈ 1...18`; finite non-negative impact/following-path/inter-impact/excursion values; finite ENU coordinates with negative zero rejected; `0 < horizontalAccuracyM <= policy.maximumHorizontalAccuracyM`; source revision/client-sequence ordinals in canonical safe-integer range `0...9_007_199_254_740_991`; non-empty bounded `originDeviceId/originEpoch`; allowed lie/reason enums; sorted-unique non-empty evidence; and exact partition equality before mutation. `returnedToPrecedingStation=true` requires a non-null preceding observation in the same partition/hole, `maximumExcursionFromPrecedingStationM >= policy.minimumReturnExcursionM` and `interImpactPathLengthM >= policy.minimumReturnPathLengthM`; a false value must still retain the measured aggregates rather than zeroing them. NaN、±Infinity、negative accuracy/time/path, `-0.0`, unsafe ordinals and out-of-range hole fail before identity/hash/sort. GPS latitude/longitude validation occurs in the observation projector before ENU conversion. Invalid input cannot create a partial journal row.

`ShotObservationJournal` exact-keys every record, partitions every query by `(roundId,roundIncarnationId)`, and persists station observations/decisions/retraction transactions/recovery records atomically through Track A's durable file primitive: write canonical bytes to a same-directory temporary file, fsync file, atomic rename, then fsync parent directory. Startup rejects truncated/noncanonical/hash-mismatched state rather than resetting it. It also retains D15 motion candidates as `CandidateJournalEntry{partition,observation,decision,decidedAt}`; `appendCandidate/pendingCandidate/decideCandidate` all require the partition explicitly. Startup requires the active partition; it never selects “the last pending entry in the file”. Prior-round records remain audit history but cannot be presented or replayed into the current session.

Retention is per partition: keep every pending/prepared entry, every record referenced by an effective retraction/recovery/outbox transaction and the newest 64 unreferenced terminal entries of each kind. Compaction itself is a durable generation-checked transaction; it never removes the only bytes needed for crash replay.

Required production API ownership is explicit:

```text
ShotObservationJournal.prepareRetractionIfAbsent / markCanonicalTransactionAppended
ShotObservationJournal.requireSuppressedObservation / prepareRecoveryIfAbsent / pendingPreparedRecoveries
ShotObservationJournal.appendCandidate / pendingCandidates / decideCandidate
DomainLedgerStore.append(_:)  // exact Track A ordinary/prerequisite boundary
DomainRoundProjection.isEffectiveShot(in partition)
ManualShotProducer.recordRecoveredManualShot(source, restoredShotId, builder, occurredAt)
```

The journal stores exact prepared event bytes, decodes them through Track A's validator, proves re-encoding is byte-identical, and then calls only `DomainLedgerStore.append(_:)`. A recovery `shot_recorded` therefore acquires Track A's permanent ordinary shot claim inside the existing ledger transaction; a retraction uses the same event/outbox/idempotency path. Crash after ledger append but before journal marking retries the same identity/hash and then marks appended. These methods are implemented only in the files listed by D14a; no view/service supplies an alternate append overload, claim API or sidecar ledger.

- [ ] **Step 3: Project production observations and return proposals only**

`ShotStationObservationProjector` joins canonical effective `shot_recorded` origin/revision with the monotonic Motion/GPS path journal and the same verified map ENU origin used by D10a. For each consecutive same-partition observation it persists only derived path evidence—preceding observation ID、inter-impact path length、maximum excursion and returned/not-returned proof—not the raw high-frequency stream. Arrival/request order is irrelevant. Missing accuracy/path evidence yields separate stations rather than optimistic grouping.

`ShotStationReducer.reduce(...) -> [ShotStationDecision]`:

- keeps only the highest source revision per shot;
- groups only within one partition and hole;
- Tee last-wins is automatic only inside one comparable origin clock domain `(originDeviceId,originEpoch)`, ordered by `(sourceClientSequence,impactMonotonicSeconds,shotId)`; the monotonic value is never compared across devices or epochs. If the same Tee station contains effective observations from different origin clock domains with no explicit causal correction, the reducer keeps every shot, emits diagnostic `tee_cross_device_order_ambiguous`, and routes the player to the normal shot-edit conflict UI instead of deleting a guessed loser;
- non-Tee origins are “near” only when both accuracy values pass and their Euclidean separation is at most `policy.stationRadius(firstAccuracyM:secondAccuracyM:)`;
- a near non-Tee pair with verified return evidence (`maximumExcursion >= minimumReturnExcursionM` and `interImpactPathLength >= minimumReturnPathLengthM`) remains two effective shots automatically；this is the required return-path/OB-replay protection and never opens a Mulligan/OB dialog;
- only a near non-Tee pair without verified return evidence may produce `app_near_station_grouping`; missing/contradictory path evidence keeps both shots rather than deleting a possible stroke;
- never appends/retracts/restores facts and never adds a recovered observation a second time;
- ignores a stale recovery whose source is no longer suppressed and reports `shot_recovery_source_not_suppressed`.

Decision IDs are typed IDs over partition, primary/suppressed IDs, reason, exact `policyId` and evidence, so input reordering cannot change them. Tests place origins immediately below/above the derived station radius and path excursion/path-length immediately below/at their thresholds; returning to the same station after a verified excursion always keeps both. Tee remains last-wins for the normal single-authority stream exactly as the Owner selected, while an offline Watch/iPhone ordering ambiguity is preserved for manual resolution.

- [ ] **Step 4: Canonicalize suppression with stable prepared transactions**

```swift
public final class ShotStationCanonicalizer {
    public func reconcile(
        partition: ShotJournalPartition,
        decisions: [ShotStationDecision],
        projection: DomainRoundProjection,
        journal: ShotObservationJournal,
        ledger: DomainLedgerStore,
        builder: DomainEventBuilder,
        occurredAt: String
    ) throws {
        for decision in decisions.sorted(by: { $0.decisionId < $1.decisionId }) {
            for shotId in decision.suppressedShotIds.sorted() {
                guard projection.isEffectiveShot(shotId, in: partition) else { continue }
                let prepared = try journal.prepareRetractionIfAbsent(
                    partition: partition,
                    decision: decision,
                    shotId: shotId,
                    builder: builder,
                    occurredAt: occurredAt
                )
                let event = try prepared.decodeExactDomainRoundEvent()
                do {
                    try ledger.append(event)
                } catch DomainLedgerError.shotSetFrozenByResolution {
                    try journal.markDeferredByResolution(
                        partition: partition,
                        transactionId: prepared.transactionId
                    )
                    continue
                }
                try journal.markCanonicalTransactionAppended(
                    partition: partition,
                    transactionId: prepared.transactionId
                )
            }
        }
    }
}
```

`prepareRetractionIfAbsent` assigns and persists stable `transactionId/eventId/canonicalEventBytes` before ledger append. The event is exact `shot_retracted(reasonCode=tee_last_wins|app_near_station_grouping)` with `causationId` equal to the currently effective source `shot_recorded` event identity and `baseEntityRevision` equal to that shot entity's current revision. `decisionId/policyId/evidenceRefs` remain in the durable journal/diagnostic record; a non-event decision ID is never inserted into the ledger causation graph. Restart reuses exact bytes; payload collision fails closed. `DomainLedgerStore.append(_:)` is extended only inside its existing state transaction to reject an ordinary recovery/retraction affecting a hole whose D14b score episode is unresolved, returning `shotSetFrozenByResolution`; it does not append an event/outbox row or alter a claim. The prepared journal record remains durable and is revalidated after the episode becomes terminal. There are no undefined `appendPreparedCanonicalTransaction`, `rejectSupersededStationShot`, `recordCanonicalRetraction` or `requireRetractedObservation` calls.

Before D14b creates a local score episode, `HoleScoreCoordinator` synchronously drains every already-decidable station reconciliation for that previous-hole occurrence and reprojects the ledger. The subsequent atomic open freezes the suggestion from that projection generation. If a late retraction races the open, the same ledger transaction order yields exactly one of two states: retraction commits first and the frozen suggestion counts the reduced effective set, or open commits first and the retraction remains deferred. A background task can never mutate the shot set underneath an open suggestion. After terminal resolution, a deferred suppression is replayed through `append(_:)`; if it makes score-versus-effective-shot totals suspicious, Hole Root/review shows a durable `成绩可能需要调整` affordance but never silently rewrites the confirmed score.

- [ ] **Step 5: Restore “打厚了” through Track A's one canonical shot producer**

Do not create `CanonicalShotRecordedEventFactory` or any second event-body builder. D14a extends and reuses Track A's existing `ManualShotProducer` with one internal `recordRecoveredManualShot(source:restoredShotId:builder:occurredAt:)` entry point. Its `VerifiedSuppressedShotRecoverySource` argument has no public initializer and is minted only by `ShotObservationJournal.requireSuppressedObservation` after proving the source shot is currently suppressed by an appended canonical retraction in the same partition. An explicit player “打厚了” action durably preallocates one new legal `restoredShotId`, asks that canonical producer to build exact bytes from the verified source, and persists the complete `ShotRecoveryRecord(disposition=.prepared)` before append. The restored event keeps Track A's frozen `shot_recorded.provenance="manual"`, uses the canonical retraction event identity as `causationId`, and never reuses the retracted shot ID. The recovery meaning lives in the durable `ShotRecoveryRecord.reason=fat_or_very_short` plus that causal edge; D14a does not expand Track A's provenance enum through a hidden app-only value.

```swift
public struct ShotRecoveryEventProducer {
    public func prepareFatOrVeryShort(
        partition: ShotJournalPartition,
        suppressedShotId: String,
        projection: DomainRoundProjection,
        journal: ShotObservationJournal,
        builder: DomainEventBuilder,
        occurredAt: String
    ) throws -> ShotRecoveryRecord {
        let source = try journal.requireSuppressedObservation(
            partition: partition,
            shotId: suppressedShotId,
            projection: projection
        )
        return try journal.prepareRecoveryIfAbsent(
            partition: partition,
            source: source,
            reason: .fatOrVeryShort,
            buildCanonicalEvent: { restoredShotId in
                try ManualShotProducer().recordRecoveredManualShot(
                    source: source,
                    restoredShotId: restoredShotId,
                    builder: builder,
                    occurredAt: occurredAt
                )
            }
        )
    }
}
```

The canonicalizer drains prepared recovery records once, verifies exact event bytes/ID/partition/causation, calls Track A `DomainLedgerStore.append(_:)` idempotently and marks appended. This is the sole point that obtains the restored shot's permanent ordinary claim. If the shot is no longer suppressed, no new event is built; if the score episode freezes that hole's shot set, the record remains prepared/deferred with no claim or event until terminal resolution. Ledger, statistics and calibration count the same effective set after replay/restart.

`WatchShotRecoveryView` is the concrete S70-style affordance, not an unspecified future UI. After an `app_near_station_grouping` retraction it emits one subtle haptic and queues a non-modal two-line card on Hole Root: `近点两次击球` / `当前只记后一杆`, with one tap action `打厚了，算上一杆` and a dismiss action. The card is visible for the policy's 12 foreground seconds; background time, wrist-down time and any higher-priority score/Club Prompt overlay do not consume that clock. Expiry/dismiss writes no event and the same recovery remains reachable from the current-hole recent-shot sheet and the arbitrary-hole edit route. Tee last-wins never shows this card.

The recovery action calls only `prepareFatOrVeryShort(...)`; the view cannot mint a shot or mutate score. `ShotRecoveryBanner` exposes the same durable proposal on iOS. If a D14b score episode is already open, the action is temporarily read-only and offers `手动确认成绩`; it cannot append an ordinary recovered shot underneath a frozen suggestion. After that resolution is terminal, current-hole/review editing may restore the shot and, when necessary, supersede the hole score through the normal canonical edit path. Tests cover score-overlay preemption, foreground-clock pause, expiry without mutation, restart persistence, one-tap exactly-once recovery and later-access discoverability.

- [ ] **Step 6: Implement Club Prompt as an actual-club-only queued overlay**

Club Prompt receives a confirmed canonical shot ID only after ownership/reconciliation allows it. Selecting a club or Skip writes exactly one `actual_club_set` (club ID or null). Cancel durably dismisses only that prompt and writes no `actual_club_set`; the canonical shot/location remains, the prompt does not silently reopen, and the player may add/change the club later from shot history. Timeout collapses without a fact, while interruption and score-overlay preemption pause and resume the same prompt. Visible eight-second time accrues only while the prompt is foreground, interactive and highest priority; resume never manufactures a timeout. UI rows use `ClubDisplayCatalog`; recommended club is a visual badge only and never an event argument.

Priority is: D14b score confirmation → Club Prompt → Caddie/Map instruments. The non-modal recovery card queues behind either modal overlay and returns on Hole Root afterward; it never steals the Crown or converts its timeout into a decision. Deferred prompts retain shot order and original IDs.

- [ ] **Step 7: Run replay, statistics and Watch recovery suites**

Run:

```bash
uv run python tools/contracts/generate_contracts.py
uv run python -m unittest tests.test_contract_codegen -v
swift test --filter 'ShotCaptureRecoveryTests|ClubPromptRecoveryTests|GuidanceReasonLocalizerTests|WatchShotRecoveryCoordinatorTests'
uv run python -m unittest tests.test_shot_station_statistics tests.test_club_calibration -v
```

Expected: PASS; generated contracts match the checked-in policy/LRP binding, no cross-round replay or duplicate recovery occurs, verified return-path evidence preserves both non-Tee shots, Tee last-wins is canonical across all consumers, and only an explicit “打厚了” action restores one new shot.

- [ ] **Step 8: Commit canonical station recovery**

```bash
git add contracts/canonical/shot_recovery_policy_v1.schema.json contracts/canonical/fixtures/shot_recovery_policy_golden.json contracts/canonical/live_round_package_v2.schema.json contracts/canonical/canonical_object_registry.json contracts/canonical/reason_codes.json tools/contracts/generate_contracts.py tests/test_contract_codegen.py ai_caddie/contracts/generated.py mobile/ios/AICaddieDomain/GeneratedContracts.swift web_v2/src/contracts/generated.ts mobile/ios/AICaddieDomain/ShotCapture/ShotRecoveryPolicy.swift mobile/ios/AICaddieDomain/ShotCapture/ShotObservationJournal.swift mobile/ios/AICaddieDomain/ShotCapture/ShotStationObservationProjector.swift mobile/ios/AICaddieDomain/ShotCapture/ShotStationReducer.swift mobile/ios/AICaddieDomain/ShotCapture/ShotStationCanonicalizer.swift mobile/ios/AICaddieDomain/ShotCapture/ShotRecoveryEventProducer.swift mobile/ios/AICaddieDomain/ShotCapture/ClubPromptProducer.swift mobile/ios/AICaddieDomain/ShotCapture/ClubPromptVisibleCountdown.swift mobile/ios/AICaddieDomain/ShotCapture/ManualShotProducer.swift mobile/ios/AICaddieDomain/Presentation/GuidanceReasonLocalizer.swift mobile/ios/AICaddieDomain/DomainLedgerStore.swift mobile/ios/AICaddieDomainTests/ShotCaptureRecoveryTests.swift mobile/ios/AICaddieDomainTests/ClubPromptRecoveryTests.swift mobile/ios/AICaddieDomainTests/GuidanceReasonLocalizerTests.swift mobile/ios/AICaddieWatch/Services/WatchShotRecoveryCoordinator.swift mobile/ios/AICaddieWatch/Views/ShotCapture/WatchShotRecoveryView.swift mobile/ios/AICaddieWatch/Views/ShotCapture/WatchClubPromptView.swift mobile/ios/AICaddieWatch/Views/WatchRoundContainerView.swift mobile/ios/AICaddieWatchTests/WatchShotRecoveryCoordinatorTests.swift mobile/ios/AICaddie/Views/Live/ShotRecoveryBanner.swift mobile/ios/AICaddie/Views/CurrentHoleView.swift ai_caddie/history/history_stats.py ai_caddie/players/club_calibration.py tests/test_shot_station_statistics.py
git commit -m "feat: canonicalize shot station recovery"
```

## Task D14b: Implement S70 score confirmation with scope-local evidence and one actionable flow per incarnation

**Depends on:** D14/D14a canonical shot path; Track A Task 13a canonical `resolution_opened/resolution_shot_staged`、atomic `ResolutionCommit`、peer provisional import and score/putt/penalty/fairway events; optional D08b live position/map route for automatic evidence; pinned `LiveRoundPackageV2.roundPolicy.{orderedHoleSequence,holeTransitionPolicy}` for both automatic and manual transition scopes. Geometry/Guidance unavailability disables automatic detection, never manual score/advance. This task completes the first production milestone before D15.

**Product law:** next-Tee proximity is evidence, never an automatic hole switch. Track A retains scope-local canonical heads, but one `roundIncarnationId` may expose at most one **actionable** unresolved confirmation across all scopes. A device with any actionable unresolved episode cannot open another scope；peer/offline episodes from other scopes remain durable conflict/audit evidence and enter a deterministic one-at-a-time reconciliation queue, never parallel mutable flows. Concurrent offline episodes in the same scope are preserved as an explicit conflict rather than arrival-order loss. Hole Root always renders one selected confirmation or one conflict blocker. The authoritative episode and tentative shots are Track A canonical operational events, not a Watch-only journal. Score/shot ownership/close/finish facts are appended locally as one provisional `ResolutionCommit` and accepted by the server only as one CAS transaction after explicit quick accept, manual completion or Cancel. The final hole must resolve the same score flow before the round can finish.

**Files:**
- Create: `contracts/canonical/hole_transition_policy_v1.schema.json`
- Create: `contracts/canonical/fixtures/hole_transition_policy_golden.json`
- Modify: `contracts/canonical/live_round_package_v2.schema.json`
- Modify: `contracts/canonical/canonical_object_registry.json`
- Modify: `tools/contracts/generate_contracts.py`
- Regenerate: `ai_caddie/contracts/generated.py`
- Regenerate: `mobile/ios/AICaddieDomain/GeneratedContracts.swift`
- Regenerate: `web_v2/src/contracts/generated.ts`
- Modify: `tests/test_contract_codegen.py`
- Modify: `mobile/ios/AICaddieDomainTests/GuidanceContractTests.swift`
- Modify: `web_v2/src/contracts/generated.test.ts`
- Modify: `ai_caddie/rounds/resolution_commit.py`
- Modify: `ai_caddie/rounds/ledger_repo.py`
- Create: `ai_caddie/rounds/active_play_cursor.py`
- Modify: `ai_caddie/rounds/reducer_v2.py`
- Create: `contracts/canonical/fixtures/active_play_cursor_timelines.json`
- Modify: `tests/resolution_commit_fixtures.py`
- Modify: `tests/test_resolution_commit_v2.py`
- Create: `tests/test_active_play_cursor.py`
- Create: `tests/test_active_play_cursor_source_boundaries.py`
- Modify: `tests/test_round_reducer_v2.py`
- Modify: `mobile/ios/AICaddieDomain/ResolutionCommit.swift`
- Modify: `mobile/ios/AICaddieDomainTests/ResolutionCommitTests.swift`
- Modify: `mobile/ios/AICaddieDomain/DomainRoundProjection.swift`
- Modify: `mobile/ios/AICaddieDomain/DomainRoundReducer.swift`
- Create: `mobile/ios/AICaddieDomain/Scoring/HoleTransitionPolicy.swift`
- Create: `mobile/ios/AICaddieDomain/Scoring/HoleTransitionEvidence.swift`
- Create: `mobile/ios/AICaddieDomain/Scoring/ResolutionEpisode.swift`
- Create: `mobile/ios/AICaddieDomain/Scoring/ProvisionalHoleState.swift`
- Create: `mobile/ios/AICaddieDomain/Scoring/ActivePlayCursorProjector.swift`
- Create: `mobile/ios/AICaddieDomain/Scoring/ResolutionOpenedWireFactory.swift`
- Create: `mobile/ios/AICaddieDomain/Scoring/ResolutionShotStagedWireFactory.swift`
- Create: `mobile/ios/AICaddieDomain/Scoring/HoleTransitionDetector.swift`
- Create: `mobile/ios/AICaddieDomain/Scoring/HoleTransitionCheckpointStore.swift`
- Create: `mobile/ios/AICaddieDomain/Scoring/TransitionShotPreflight.swift`
- Create: `mobile/ios/AICaddieDomain/Scoring/TransitionShotPreparationJournal.swift`
- Create: `mobile/ios/AICaddieDomain/Scoring/DefaultHoleScoreSuggestion.swift`
- Create: `mobile/ios/AICaddieDomain/Scoring/FirstShotLandingClassifier.swift`
- Create: `mobile/ios/AICaddieDomain/Scoring/TransitionStageOwnershipClassifier.swift`
- Create: `mobile/ios/AICaddieDomain/Scoring/PendingShotOwnershipJournal.swift`
- Create: `mobile/ios/AICaddieDomain/Scoring/HoleScoreTransaction.swift`
- Create: `mobile/ios/AICaddieDomain/Scoring/HoleScoreResolutionRequestFactory.swift`
- Create: `mobile/ios/AICaddieDomain/Scoring/HoleScoreCoordinator.swift`
- Modify: `mobile/ios/AICaddieDomain/ShotCapture/ShotCaptureSession.swift`
- Modify: `mobile/ios/AICaddieDomain/ShotCapture/ManualShotProducer.swift`
- Modify: `mobile/ios/AICaddieDomain/DomainLedgerStore.swift`
- Create: `mobile/ios/AICaddieDomainTests/DomainLedgerStoreTests.swift`
- Create: `mobile/ios/AICaddieDomainTests/HoleTransitionTimelineTests.swift`
- Create: `mobile/ios/AICaddieDomainTests/HoleScoreTransactionTests.swift`
- Create: `mobile/ios/AICaddieDomainTests/FirstShotLandingClassifierTests.swift`
- Create: `mobile/ios/AICaddieDomainTests/ActivePlayCursorProjectorTests.swift`
- Create: `mobile/ios/AICaddieDomainTests/TransitionStageOwnershipClassifierTests.swift`
- Create: `mobile/ios/AICaddieDomainTests/Fixtures/active_play_cursor_timelines.json`
- Modify: `mobile/ios/AICaddieDomainTests/ManualShotProducerTests.swift`
- Create: `mobile/ios/AICaddieWatch/Services/WatchHoleScoreCoordinator.swift`
- Create: `mobile/ios/AICaddieWatch/Services/WatchResolutionPeerTransfer.swift`
- Create: `mobile/ios/AICaddieWatch/Views/Scoring/WatchHoleScoreConfirmView.swift`
- Create: `mobile/ios/AICaddieWatch/Views/Scoring/WatchManualHoleScoreFlow.swift`
- Create: `mobile/ios/AICaddieWatch/Views/Scoring/WatchScorecardEditView.swift`
- Modify: `mobile/ios/AICaddieWatch/Views/WatchRoundContainerView.swift`
- Modify: `mobile/ios/AICaddie/Views/CurrentHoleView.swift`
- Create: `mobile/ios/AICaddie/Views/ReviewEditHoleView.swift`
- Create: `mobile/ios/AICaddieWatchTests/WatchHoleScoreFlowTests.swift`
- Create: `mobile/ios/AICaddieTests/HoleScoreDeepEditTests.swift`

- [ ] **Step 1: Write failing Owner-flow, terminal-hole and crash timelines**

Add exact tests:

- `testArrivalOrCartPassAtNextTeeAloneNeverChangesHoleOrWritesScore`;
- `testHoleTransitionPolicyGoldenHasExactVersionHashAndCrossLanguageParity`;
- `testEveryDistanceSpeedDwellAccuracyAndFreshnessBoundaryIsInclusiveOnlyAtTheFrozenThreshold`;
- `testManualFinishHoleWithoutGeometryOpensTheSameCanonicalEpisodeAndNeverFakesDistance`;
- `testAdjacentFairwayAndBacktrackingRemainCurrentHole`;
- `testChipInAndNeverEnteringGreenCanArmCompletionButStillRequiresOrderedNextTeeEvidence`;
- `testNoGreenEntryStillDefaultsTwoPuttsAndPossibleChipInIsAdvisoryOnly`;
- `testZeroPuttsRequiresExplicitManualChoiceAndQuickNeverInfersHoledOut`;
- `testNoShotEvidenceUsesVerifiedParFloorForPar3Par4AndPar5WithoutFabricatingShots`;
- `testPartialShotEvidenceBelowParUsesLowConfidenceParFloorAndCompleteCountAboveParWins`;
- `testMissingVerifiedParDisablesQuickAndRequiresManualInsteadOfSuggestingTwo`;
- `testDetectorRestartRetainsReducedLatchesButRequiresFreshConsecutiveFixesAndSamePolicyHash`;
- `testCorruptOrPolicyMismatchedCheckpointDisablesAutomaticDetectionWithoutDisablingManualConfirm`;
- `testNextTeeFirstShotRacesDetectorAndNeverOrdinaryAppendsToPreviousHole`;
- `testTransitionShotPreparationRecoversAtEveryOpenStageAndSlotRotationFaultPoint`;
- `testDetectorAndManualShotConcurrentOpenReuseOneCanonicalEpisodeAndOneStage`;
- `testUnconfirmedNextTeeShotsRemainCanonicalOperationalOnlyAndPreserveOrder`;
- `testQuickAcceptAdoptsAllAvailableSuggestedFactsWithoutOpeningManualSteps`;
- `testQuickIsUnavailableWhenAnyTargetStageCannotBeUnambiguouslyAssignedNext`;
- `testCancelAssignsEveryTentativeShotBackToPreviousHoleAndWritesNoScore`;
- `testManualFlowOrderIsScorePuttsFairwayPenaltyAndCommitsOneCausalBatch`;
- `testManualMixedOwnershipRequiresAnExplicitPreviousOrNextChoiceForEveryTargetStage`;
- `testPreviousHoleRecoveryThenTrueNextTeeShotAssignsEachPhysicalShotExactlyOnce`;
- `testSameDeviceOrderedNextTeeMulligansRemainQuickEligibleAndOnlyLastShotIsEffective`;
- `testCrossDeviceOrRecoveryMixedNextTeeRowsRequireManualOwnership`;
- `testChangingOneMixedTargetOwnershipChoiceChangesDecisionHashAndResolutionCommitId`;
- `testRestartBeforeMixedOwnershipSubmitWritesNothingAndPreparedRetryReusesExactChoices`;
- `testPeerSameScopeConflictNeverAppliesTargetStageChoicesToALoserEpisode`;
- `testPar3QuickAcceptWritesFairwayNotApplicable`;
- `testPar4Or5VerifiedFirstLandingWritesHitLeftOrRightAndUnknownStaysUnknownWithoutPrompt`;
- `testFirstShotLandingUsesLastEffectiveTeeShotAndNextConfirmedShotOriginOnly`;
- `testFairwayStrictInteriorIsHitAndSignedRouteTangentClassifiesLeftRight`;
- `testBoundaryAccuracyOverlapAdjacentFairwayAmbiguousOrderAndMissingNextOriginAreUnknown`;
- `testFirstShotClassifierNeverRewritesShotStartLieAndPar3IsNotApplicable`;
- `testCustomNineAndShotgunUseFrozenSequenceAndRepeatedPhysicalHoleIsRejectedInV1`;
- `testResolutionOpenedWireUsesSnakeCaseKindExactEvidenceKeysAndDetectorVersion`;
- `testResolutionShotStagedWireUsesExactFlatPayloadAndReservedShotId`;
- `testCrossingMultipleTeesCannotCreateOrOverwriteSecondEpisodeInSameTransitionScope`;
- `testDifferentScopeOfflineEpisodesRemainAuditOnlyAndHoleRootHasOneActionableConfirmation`;
- `testFinalHoleDepartureOrFinishRequiresScoreConfirmationBeforeFinished`;
- `testFinalHoleCancelReturnsToPlayingAndQuickAcceptThenFinishIsAtomic`;
- `testActivePlayCursorConfirmAndManualAdvanceOnlyToTheVerifiedOrderedNextScoreSlot`;
- `testActivePlayCursorCancelKeepsPreviousHoleAndFinalCancelKeepsFinalHolePlaying`;
- `testActivePlayCursorFinalConfirmRequiresTheSealedCloseFinishRosterBeforeFinished`;
- `testHistoricalScoreShotAndFairwayEditsNeverMoveTheActivePlayCursor`;
- `testActivePlayCursorRestartPeerTakeoverAndAcceptedReplayProduceTheSameResult`;
- `testConcurrentOrOutOfOrderResolutionHeadsFailClosedAtTheLastVerifiedCursor`;
- `testCrashBeforeAndAfterLedgerAppendReusesStableTransactionIdAndNeverDuplicatesFactsOrShots`;
- `testEpisodeAndTentativeShotsAreCanonicalOperationalEventsIgnoredByStatistics`;
- `testWatchPeerBundleMakesUnresolvedEpisodeVisibleOnIPhoneWithoutServerReceipt`;
- `testPhoneUploadsWatchOriginStagesThenSendsOneResolutionCommit`;
- `testLostCommitResponseSubmittedWatchTransfersExactBodyAndPhoneGetsCachedSuccess`;
- `testConcurrentWatchAndPhoneCloseLeavesOneServerWinnerAndVisibleLosingConflict`;
- `testMissingRequiredStageCauseKeepsEveryFinalFactUncommitted`;
- `testServerCrashAtEveryResolutionCommitFaultPointNeverLeavesPartialScoreShotOrFinish`;
- `testRoundFinishedDirectlyCausedByAnythingExceptAcceptedResolutionCloseFailsClosed`;
- `testWatchCanEditAnyCompletedOrCurrentHoleAndReplaySupersedingFactsWithoutChangingActivePlayHole`;
- `testOfflineRestartPreservesOneEpisodeAndAllTentativeShots`.
- `testTwoLocalOpensForSameScopeRaceAndOnlyOneEventOutboxMutationWins`;
- `testTwoLocalOpensForDifferentScopesRaceAndOnlyOneActionableEventOutboxMutationWins`;
- `testExactOpenRetryIsIdempotentButPeerSameScopeOpenRemainsVisibleAsConflict`;
- `testStageClaimAppendSlotCompletionAndNextReservationAreOneFaultAtomicTransaction`;
- `testTwoStagesRacingOneActiveSlotProduceOneStageOnePermanentClaimAndOneRotation`;
- `testExactStageRetryNeverRotatesASecondTimeAndRestartLoadsTheSameNextUUID`.
- `testStagedDraftCannotCarryHoleBeforeResolutionCommit`;
- `testCommitConstructsManualShotDraftOnlyAfterOwnershipDisposition`.
- `testSupersededLoserStagesReceiveTerminalDispositionsOrWholeCommitRollsBack`.
- `testExactEquivalentLoserObservationCoalescesIntoOneAssignedPhysicalShot`;
- `testAcceptedDefaultAndCancelHaveEmptyConfirmedLoserRoster`;
- `testAcceptedDefaultOrCancelCannotAssignOrDiscardAnAmbiguousLoser`;
- `testAmbiguousLoserBlocksCommitUntilEveryStageHasAnExplicitConflictMergeChoice`;
- `testManualConflictMergeRetainsDistinctLoserPhysicalShotExactlyOnce`;
- `testConflictMergeNeverSilentlyDiscardsOrLosesADistinctPhysicalShot`;
- `testConfirmedLoserRosterIsSortedUniqueIncludedInDecisionHashAndBijectiveWithFinalShots`;
- `testExplicitLoserDiscardRequiresARecordedPlayerChoiceAndNonEmptyReasonCode`;
- `testLoserEpisodeCreatesOnlyItsSupersededCloseAndNeverIndependentScoreFacts`;
- `testRetainedLoserFinalShotFeedsNormalStatisticsAndClubCalibrationExactlyOnce`.

- [ ] **Step 2: Define one durable episode with ordered shot ownership**

First tighten `LiveRoundPackageV2.roundPolicy` to the exact v1 object `{orderedHoleSequence,holeTransitionPolicy}`. `holeTransitionPolicy` is a required `$ref` to `HoleTransitionPolicy/v1`; it is frozen into the LRP identity and has no runtime defaults. The checked-in golden body is exactly:

```json
{
  "schema": "ai-caddie-hole-transition-policy-v1",
  "policyHash": "1777644f056f1e324387fd5edbcc1a838ffb4ec242171dece404505bce76a116",
  "policyVersion": "app-conservative-transition-v1",
  "maximumHorizontalAccuracyM": 12.0,
  "maximumFixAgeSeconds": 8.0,
  "maximumInterFixGapSeconds": 6.0,
  "requiredConsecutiveFixes": 3,
  "greenEntryRadiusM": 24.0,
  "greenDepartureRadiusM": 36.0,
  "completionApproachRadiusM": 60.0,
  "candidateTeeArrivalRadiusM": 30.0,
  "candidateTeeShotRadiusM": 35.0,
  "stationarySpeedMps": 0.8,
  "movingSpeedMps": 1.8,
  "candidateTeeDwellSeconds": 8.0,
  "cartPassSpeedMps": 2.8,
  "minimumForwardProgressM": 18.0,
  "minimumTeeDistanceReductionM": 18.0,
  "compactTransitionProgressFraction": 0.6,
  "maximumBacktrackM": 15.0,
  "finalHoleStationaryDwellSeconds": 12.0,
  "finalHoleDepartureTimeoutSeconds": 90.0,
  "transitionEvidenceTtlSeconds": 180.0,
  "conservativeDistanceRule": "full_uncertainty_disk"
}
```

`policyHash` is lowercase SHA-256 over canonical JSON of every exact field above except `policyHash`; the shown value is the golden for the shown body. Register `HoleTransitionPolicy/v1` with that exclusion only. Generated Python/Swift/TypeScript decoders reject extra/missing keys、non-finite values、unknown rule/version、a hash mismatch or violated relationships: `stationarySpeedMps < movingSpeedMps < cartPassSpeedMps`、`greenEntryRadiusM < greenDepartureRadiusM < completionApproachRadiusM`、`candidateTeeArrivalRadiusM <= candidateTeeShotRadiusM` and `compactTransitionProgressFraction ∈ (0,1]`. Every threshold comparison is inclusive at the stated boundary and tests both the next representable value below and above it.

Source-boundary tests reject detector/preflight literals for any frozen threshold and reject loading a process-global/default policy. Production can obtain the policy only by strict decode/reverification of the active raw LRP；manual transition may function without geometry, but it still records that LRP policy hash so replay cannot mix rule generations.

Automatic evidence sets `detectorVersion` exactly to the decoded `policyVersion`. The only non-automatic values are generated enums `manual-transition-v1` and `manual-shot-ownership-v1`; arbitrary non-empty strings are rejected.

For `full_uncertainty_disk`, a fix is definitely inside radius `r` only when `distance + horizontalAccuracyM <= r`, definitely outside only when `distance - horizontalAccuracyM >= r`, and otherwise ambiguous. Certain forward progress/distance reduction subtracts both endpoint uncertainty disks; no center-point-only comparison is legal. A fix participates only when accuracy is `<= 12.0 m`, age is `<= 8.0 s`, timestamps/monotonic sequence increase and the gap from the previous eligible fix is `<= 6.0 s`. A larger gap resets consecutive-fix/dwell accumulation without inventing an interpolated path.

Each sorted-by-`scoreSlot` `orderedHoleSequence` row has exact keys `scoreSlot,manifestOrdinal,holeSubjectRef,displayHole,occurrenceIndex`:

- length is exactly the verified Plan 2 install/snapshot roster length, therefore 9 or 18;
- `scoreSlot` is the unique Track A integer used by every score/putt/penalty/fairway/shot event and is exactly `1...N`;
- `manifestOrdinal` is a 1-based reference to the verified `CourseInstallManifestPayload.orderedHoles` row and each physical manifest row appears exactly once;
- `holeSubjectRef` equals the verified snapshot/static-authority subject for that manifest row;
- `displayHole` equals that row's player-facing provider/local hole number and is presentation only;
- `occurrenceIndex` is the constant `1` in v1.

The sequence array is play order, so a shotgun/custom start is a permutation without using `hole + 1`. Duplicate `scoreSlot`, duplicate physical manifest row, missing roster member, cross-layout subject, length other than 9/18 or `occurrenceIndex != 1` fails LRP verification in Python/Swift/TypeScript. Replaying the same physical nine twice is deliberately not claimed by v1 because it would need 18 distinct score slots over a 9-hole physical roster; that future contract must version the occurrence mapping rather than overwrite one Track A hole entity.

```swift
public struct HoleTransitionEvidence: Codable, Equatable, Sendable {
    public let detectorVersion: String
    public let policyHash: String
    public let roundId: String
    public let roundIncarnationId: String
    public let scopeId: String
    public let previousHole: Int
    public let candidateNextHole: Int?
    public let distanceToCurrentGreenM: Double?
    public let distanceToCandidateTeeM: Double?
    public let greenEntryObserved: Bool
    public let completionApproachObserved: Bool
    public let departedCurrentHole: Bool
    public let candidateTeeArrivalObserved: Bool
    public let candidateTeeShotObserved: Bool
    public let maximumQualifiedHorizontalAccuracyM: Double?
    public let qualifiedFixCount: Int
    public let observationSpanSeconds: Double
    public let stationaryDwellSeconds: Double
    public let forwardProgressM: Double
    public let adjacentFairwayRisk: Bool
    public let backtrackResetObserved: Bool
    public let cartPassRejected: Bool
    public let observedAt: String
    public let evidenceRefs: [String]
}

public struct DefaultHoleScoreSuggestion: Codable, Equatable, Sendable {
    public let suggestionId: String
    public let hole: Int
    public let score: Int
    public let putts: Int
    public let penalties: Int
    public let fairway: HoleFairwayValue?
    public let reasonCode: String
    public let evidenceRefs: [String]
}

public struct UnownedShotDraft: Codable, Equatable, Sendable {
    public let latitude: Double
    public let longitude: Double
    public let horizontalAccuracyM: Double?
    public let lie: String
}

public struct TentativeShotDraft: Codable, Equatable, Sendable {
    public let shotId: String
    public let draft: UnownedShotDraft
    public let capturedAt: String
    public let evidenceRefs: [String]
}

public struct PendingShotOwnership: Codable, Equatable, Sendable {
    public let ownershipId: String
    public let shotId: String
    public let draft: UnownedShotDraft
    public let capturedAt: String
    public let evidenceRefs: [String]
    public let stagedEventIdentity: String
    public let stagedEventHash: String
}

public enum ResolutionEpisodeKind: String, Codable, Sendable {
    case nextHole = "next_hole"
    case finalHole = "final_hole"
}

public enum ResolutionEpisodeDisposition: String, Codable, Sendable {
    case awaitingDecision
    case commitPrepared
    case commitAccepted
    case conflicted
    case cancelled
}

public enum ProvisionalShotOwnershipHint: Codable, Equatable, Sendable {
    case previousHole(Int)
    case verifiedNextHole(Int)
}

public struct ResolutionEpisode: Codable, Equatable, Sendable {
    public let resolutionId: String
    public let scopeId: String
    public let roundId: String
    public let roundIncarnationId: String
    public let previousHole: Int
    public let verifiedNextHole: Int?
    public let orderedHoleCursor: Int
    public let kind: ResolutionEpisodeKind
    public let evidence: HoleTransitionEvidence
    public let openEventIdentity: String
    public let openEventHash: String
    public var tentativeShots: [PendingShotOwnership]
    public var resolutionCommitId: String?
    public var decisionHash: String?
    public var disposition: ResolutionEpisodeDisposition
    public var revision: UInt64
}

public enum ActivePlayCursorPhase: String, Codable, Sendable {
    case playing
    case finished
}

public struct ActivePlayCursorProjection: Codable, Equatable, Sendable {
    public let phase: ActivePlayCursorPhase
    public let orderedHoleCursor: Int?
    public let activePlayHole: Int?
    public let advancingResolutionId: String?
    public let evidenceIdentity: String?
}

public struct ProvisionalHoleState: Equatable, Sendable {
    public let roundId: String
    public let roundIncarnationId: String
    public let activePlayHole: Int?
    public let activePlayPhase: ActivePlayCursorPhase
    public var actionableResolutionId: String?
    public var queuedConflictResolutionIds: [String]
    public var suggestion: DefaultHoleScoreSuggestion?
    public var revision: UInt64
}

public enum ResolutionOpenedWireFactory {
    public static func makeEvent(
        resolutionId: String,
        kind: ResolutionEpisodeKind,
        evidence: HoleTransitionEvidence,
        suggestion: DefaultHoleScoreSuggestion,
        orderedHoleCursor: Int,
        builder: DomainEventBuilder,
        baseRevision: EntityRevisionToken,
        occurredAt: String
    ) throws -> DomainRoundEvent {
        let fairway = suggestion.fairway.map { JSONValue.string($0.rawValue) } ?? .null
        let candidateNextHole = evidence.candidateNextHole.map {
            JSONValue.integer(Int64($0))
        } ?? .null
        let distanceToCurrentGreen = evidence.distanceToCurrentGreenM.map {
            JSONValue.number($0)
        } ?? .null
        let distanceToCandidateTee = evidence.distanceToCandidateTeeM.map {
            JSONValue.number($0)
        } ?? .null
        let maximumQualifiedAccuracy = evidence.maximumQualifiedHorizontalAccuracyM.map {
            JSONValue.number($0)
        } ?? .null
        let payload: [String: JSONValue] = [
            "resolutionId": .string(resolutionId),
            "scopeId": .string(evidence.scopeId),
            "episodeKind": .string(kind.rawValue),
            "previousHole": .integer(Int64(evidence.previousHole)),
            "candidateNextHole": candidateNextHole,
            "orderedHoleCursor": .integer(Int64(orderedHoleCursor)),
            "suggestion": .object([
                "suggestionId": .string(suggestion.suggestionId),
                "score": .integer(Int64(suggestion.score)),
                "putts": .integer(Int64(suggestion.putts)),
                "penalties": .integer(Int64(suggestion.penalties)),
                "fairway": fairway,
                "reasonCode": .string(suggestion.reasonCode),
                "evidenceRefs": .array(suggestion.evidenceRefs.sorted().map(JSONValue.string)),
            ]),
            "evidence": .object([
                "detectorVersion": .string(evidence.detectorVersion),
                "policyHash": .string(evidence.policyHash),
                "observedAt": .string(evidence.observedAt),
                "distanceToCurrentGreenM": distanceToCurrentGreen,
                "distanceToCandidateTeeM": distanceToCandidateTee,
                "greenEntryObserved": .bool(evidence.greenEntryObserved),
                "completionApproachObserved": .bool(evidence.completionApproachObserved),
                "departedCurrentHole": .bool(evidence.departedCurrentHole),
                "candidateTeeArrivalObserved": .bool(evidence.candidateTeeArrivalObserved),
                "candidateTeeShotObserved": .bool(evidence.candidateTeeShotObserved),
                "maximumQualifiedHorizontalAccuracyM": maximumQualifiedAccuracy,
                "qualifiedFixCount": .integer(Int64(evidence.qualifiedFixCount)),
                "observationSpanSeconds": .number(evidence.observationSpanSeconds),
                "stationaryDwellSeconds": .number(evidence.stationaryDwellSeconds),
                "forwardProgressM": .number(evidence.forwardProgressM),
                "adjacentFairwayRisk": .bool(evidence.adjacentFairwayRisk),
                "backtrackResetObserved": .bool(evidence.backtrackResetObserved),
                "cartPassRejected": .bool(evidence.cartPassRejected),
                "evidenceRefs": .array(evidence.evidenceRefs.sorted().map(JSONValue.string)),
            ]),
        ]
        return try builder.make(
            kind: .resolutionOpened,
            entityRef: "round:\(evidence.roundId):resolution:\(resolutionId)",
            payload: payload,
            baseRevision: baseRevision,
            occurredAt: occurredAt
        )
    }
}

public enum ResolutionStageProvenance: String, Codable, Sendable {
    case manual
    case autoshotObserved = "autoshot_observed"
}

public enum ResolutionShotStagedWireFactory {
    public static func makeEvent(
        resolutionId: String,
        captureOrdinal: Int,
        tentative: TentativeShotDraft,
        provenance: ResolutionStageProvenance,
        roundId: String,
        openEventIdentity: String,
        builder: DomainEventBuilder
    ) throws -> DomainRoundEvent {
        let accuracy = tentative.draft.horizontalAccuracyM.map {
            JSONValue.number($0)
        } ?? .null
        return try builder.make(
            kind: .resolutionShotStaged,
            entityRef: "round:\(roundId):resolution:\(resolutionId):shot:\(tentative.shotId)",
            payload: [
                "resolutionId": .string(resolutionId),
                "shotId": .string(tentative.shotId),
                "captureOrdinal": .integer(Int64(captureOrdinal)),
                "capturedAt": .string(tentative.capturedAt),
                "latitude": .number(tentative.draft.latitude),
                "longitude": .number(tentative.draft.longitude),
                "horizontalAccuracyM": accuracy,
                "lie": .string(tentative.draft.lie),
                "provenance": .string(provenance.rawValue),
                "evidenceRefs": .array(tentative.evidenceRefs.sorted().map(JSONValue.string)),
            ],
            baseRevision: nil,
            causationId: openEventIdentity,
            occurredAt: tentative.capturedAt
        )
    }
}
```

`ResolutionOpenedWireFactory` and `ResolutionShotStagedWireFactory` are the only D14b operational-event constructors. Tests assert exact root/nested keys, snake-case `next_hole|final_hole`, non-empty `detectorVersion`, an exact LRP-matching `policyHash`, all frozen detector booleans/metrics, `candidateNextHole/distanceToCandidateTeeM = null` for final hole, flattened stage coordinates and no extra local journal fields. Both still pass through Track A `RoundPayloadValidator` and generated event-kind metadata.

`ActivePlayCursorProjector` is the sole Python/Swift owner of live-hole advancement. Its immutable inputs are the verified `orderedHoleSequence` and Track A's ordered projection inputs, including a complete `local_prepared_resolution_commit` or `accepted_resolution_commit` roster；it never reads `PendingShotOwnershipJournal`、Watch navigation state、the highest score row、GPS proximity or a caller-provided current-hole integer. It starts at cursor `0`/the first `scoreSlot` after a valid `round_started`, then consumes only the deterministic transition scope for that cursor:

- an unresolved/conflicted open, an incomplete/malformed commit roster, `cancelled`, or a loser `superseded` close leaves the cursor on `previousHole`；arrival order can never select a winner;
- a sealed target decision `accepted_default|manually_confirmed` whose open payload matches the current `previousHole` and exact ordered `candidateNextHole` advances once to that next cursor, regardless of how its staged shots were split previous/next;
- at the terminal cursor, `accepted_default|manually_confirmed` becomes `.finished` only when the same sealed roster ends with the required `round_finished` directly caused by the accepted target close；a final-hole Cancel remains `.playing` on the final score slot;
- duplicate exact prepared/accepted representations of the same `resolutionCommitId` are one transition. A different body/hash、a skipped cursor、a future-scope close、two possible target winners or a peer conflict without an accepted winner fails closed at the last verified cursor and exposes the existing conflict blocker;
- ordinary/historical `hole_score_set`、putts、penalties、fairway、shot corrections/retractions and scorecard deep edits are deliberately absent from the advancement allow-list.

The checked-in `active_play_cursor_timelines.json` freezes initial、Quick、Manual、Cancel、mixed-stage Manual、final Quick/Manual/Cancel、strong-kill prepared recovery、Watch→Phone exact-body takeover、accepted replay、same-scope conflict and deep historical edit timelines. Python and Swift must produce byte-equivalent `{phase,orderedHoleCursor,activePlayHole,advancingResolutionId,evidenceIdentity}` rows for every checkpoint. Initially `advancingResolutionId=null` and `evidenceIdentity` is the valid `round_started` event identity. After a non-final advance both fields name the exact winning resolution and its target `resolution_closed` event identity；Cancel/conflict retains the last verified pair. On finish, `advancingResolutionId` names the final winning resolution and `evidenceIdentity` is the directly caused `round_finished` event identity. `RoundProjectionV2.viewMappings.currentHole` and Swift `DomainRoundProjection.viewMappings.currentHole` are assigned only from this projector (`nil` when finished)；source-boundary tests reject deriving them from score presence、maximum hole、UI navigation or mutable stores. `HoleScoreCoordinator` constructs `ProvisionalHoleState` from an `ActivePlayCursorProjection`, so `activePlayHole`/`activePlayPhase` are immutable projector output and `ProvisionalHoleState` is not decoded as an authority-bearing journal record.

`PendingShotOwnershipJournal` is now a rebuildable local index/cache over Track A operational events, never the authority. `UnownedShotDraft` is the only draft allowed before ownership resolution and contains exactly `latitude,longitude,horizontalAccuracyM,lie`; it cannot carry `hole`、score slot、ordered cursor、resolution disposition or provenance. `TentativeShotDraft` exists only before the atomic stage append；`PendingShotOwnership` is constructed only after the persisted stage event supplies its identity/hash, eliminating the former event↔ownership construction cycle. Opening writes one canonical `resolution_opened`; each captured tentative shot writes one canonical `resolution_shot_staged` caused by the open event. The ledger transaction—not the journal—enforces one locally created unresolved episode per `(originDeviceId,roundIncarnationId,scopeId)` and deterministic `captureOrdinal`; D14b additionally prevents the same device from creating a second locally actionable scope anywhere in the incarnation. An epoch rotation/reinstall grants neither exception. Replay may expose same-scope concurrent episodes as `.conflicted` and different-scope peer/offline heads as queued conflict/audit evidence. `ProvisionalHoleState.actionableResolutionId` selects exactly one mutable flow；`queuedConflictResolutionIds` is sorted by `(orderedHoleCursor,scopeId,resolutionId)` and is read-only until the selected flow terminalizes. Walking across another Tee cannot create、activate or overwrite an episode. All IDs are legal lowercase UUIDs or typed IDs, score/putt/penalty/score-slot/cursor values are range-checked, detector accuracy is null or finite `<= policy.maximumHorizontalAccuracyM`, `qualifiedFixCount` is a safe integer `0...128`, span/dwell/progress are finite within the policy evidence TTL, draft coordinates/accuracy are finite, and every array has deterministic order. Cache corruption is rebuilt from the shared ledger; operational events and prepared commit records are exempt from retention GC.

Freeze the two missing Track A local transaction boundaries in `DomainLedgerStore`; local D14b code may not call generic `append(_:)` for either operation:

```swift
public protocol DomainLedgerResolutionEpisodeAPI {
    func appendLocalResolutionOpenIfVacantAtomically(
        _ event: DomainRoundEvent,
        scopeId: String,
        roundId: String,
        roundIncarnationId: String
    ) throws

    func appendResolutionStageAndReserveNextAtomically(
        _ event: DomainRoundEvent,
        resolutionId: String,
        roundId: String,
        roundIncarnationId: String
    ) throws -> DurableShotCaptureState
}
```

`appendLocalResolutionOpenIfVacantAtomically` first treats an existing identical event identity/hash as an idempotent success, then in one `DomainLedgerStore.transaction` validates exact kind/payload/scope/round/incarnation/local origin and rebuilds every unresolved episode head in the incarnation. It rejects a different unresolved local open from the same scope **or any other scope** for that physical device regardless of epoch, appends exactly one `.resolutionPrerequisite` event/outbox row and updates projection inputs. A peer/remote same- or different-scope episode is not discarded or used as an arrival-order winner；it is retained, but the interaction projection admits only one actionable resolution and queues the rest read-only. A fault before atomic replacement leaves no event/outbox/head; a fault after replacement is recovered by the exact retry.

`appendResolutionStageAndReserveNextAtomically` requires an already-persisted nonterminal target open, exact direct causation, the current active capture slot's `shotId`, and the next deterministic capture ordinal. Inside one state transaction it runs Track A ordinary/prerequisite validation, creates or idempotently matches the permanent `.resolutionReserved` shot claim, appends the stage event/outbox/projection input, completes the old capture slot with that stage identity/hash and reserves one new lowercase UUID. It never reserves first and appends later. Exact retry after commit returns the already-advanced state without another rotation; a different stage racing the same active slot loses without a claim, event, outbox row or empty next slot. Peer import continues through Track A's peer batch API and never calls this local-slot method.

`ShotCaptureSession.appendResolutionStageAndReserveNext(_:)` is a thin call to the second API and reloads the returned active UUID. Source-boundary tests require `HoleScoreCoordinator` to use the open-if-vacant API and all local manual/AutoShot episode staging to use the stage+reserve API; journal writes cannot substitute for either ledger transaction.

- [ ] **Step 3: Detect evidence without switching holes**

`HoleTransitionDetector` consumes only the verified LRP policy、the active/ordered-next row's verified Green/Tee geometry、the installed round roster's verified nearby playable/Tee geometry for ambiguity checks、eligible ephemeral fixes and canonical effective shots. If the nearby-hole ambiguity query is unavailable, GPS-only opening fails closed while shot-trigger/manual confirmation remains available. It has these exact GPS-only phases:

1. `completionArmed` latches after `requiredConsecutiveFixes` fixes definitely inside `greenEntryRadiusM`, or—only after at least one effective current-hole full shot—inside `completionApproachRadiusM`. The second arm covers a chip-in、hole-in-one retrieval path or leaving without stepping onto the Green; it is not itself a score/transition decision.
2. `departedCurrentHole` latches only after the arm and both certain forward projection toward the ordered next Tee and certain distance reduction to that Tee reach `min(configuredThreshold, verifiedGreenToNextTeeDistanceM × 0.6)`—normally `18.0 m`, but proportionally smaller on a compact Green→Tee transition. When Green entry was observed, the uncertainty disk must also be definitely outside `greenDepartureRadiusM=36.0 m`; only when the verified Green→Tee anchor distance itself is `<= 36.0 m` may definite ordered-Tee arrival plus the compact progress threshold substitute for that impossible outside-radius condition. Walking through an unrelated Tee、standing in an adjacent fairway or next-Tee proximity without completion and progress evidence cannot open a GPS-only episode.
3. Ordered-next-Tee arrival qualifies only after three eligible fixes definitely inside `30.0 m` and `8.0 s` of accumulated visible stationary dwell at speed `<= 0.8 m/s`. A speed in `(0.8,1.8) m/s` pauses dwell；`>= 1.8 m/s` resets the consecutive arrival run；`>= 2.8 m/s` is a cart pass, records `cartPassRejected=true`, resets arrival/dwell and can never open. Dwell accumulates only between adjacent eligible fixes and never across a `> 6.0 s` gap、background interval or restart.
4. `adjacentFairwayRisk=true` blocks GPS-only opening. Re-entering the completion region after departure or reversing certain transition progress by `>= 15.0 m` records `backtrackResetObserved=true` and resets departure/arrival/dwell. Only a new forward run can qualify again.

```swift
public struct HoleTransitionCheckpoint: Codable, Equatable, Sendable {
    public let partition: ShotJournalPartition
    public let policyHash: String
    public let orderedHoleCursor: Int
    public let checkpointGeneration: UInt64
    public let lastAcceptedObservedAt: String
    public let greenEntryObserved: Bool
    public let completionApproachObserved: Bool
    public let departedCurrentHole: Bool
    public let maximumCertainForwardProgressM: Double
    public let maximumCertainTeeReductionM: Double
    public let adjacentFairwayRisk: Bool
    public let backtrackGeneration: UInt64
}

public enum TransitionShotPreflightDecision: Equatable, Sendable {
    case ordinaryCurrentHole
    case resolutionRequired(HoleTransitionEvidence)
    case manualOwnershipRequired
}

public enum TransitionShotPreparationState: String, Codable, Sendable {
    case prepared
    case openBound = "open_bound"
    case stagePrepared = "stage_prepared"
    case staged
    case terminal
    case blockedByOtherScope = "blocked_by_other_scope"
}

public struct TransitionShotPreparation: Codable, Equatable, Sendable {
    public let partition: ShotJournalPartition
    public let preparationId: String
    public let sourceActionId: String
    public let shotId: String
    public let capturedAt: String
    public let unownedDraft: UnownedShotDraft
    public let policyHash: String
    public let orderedHoleCursor: Int
    public let scopeId: String
    public var resolutionId: String?
    public var canonicalOpenEventBytes: Data?
    public var openEventIdentity: String?
    public var canonicalStageEventBytes: Data?
    public var stageEventIdentity: String?
    public var state: TransitionShotPreparationState
}
```

A qualified captured shot is stronger evidence than mere proximity. Before any manual or explicitly confirmed AutoShot ordinary append, `TransitionShotPreflight` applies the same uncertainty rule to the shot-origin fix. If its uncertainty disk is definitely inside the ordered next Tee's `35.0 m` shot radius—or intersects that radius while a completion/departure/arrival latch is active—the result is `.resolutionRequired`; this may open the previous-hole confirmation without prior dwell or a Green-entry latch. It still does **not** switch holes or assign the shot: Confirm/Manual assigns it to the ordered next hole and Cancel assigns it to the previous hole. `.ordinaryCurrentHole` is legal only for a valid fix definitely outside the shot radius with no unresolved episode/latch, or for an inaccurate fix whose center is also farther than `candidateTeeShotRadiusM + maximumHorizontalAccuracyM = 47.0 m` with no latch. An inaccurate but finite fix centered within that `47.0 m` guard band, or any inaccurate finite fix while a transition latch is active, is `.manualOwnershipRequired`; it follows the same preparation/open/stage saga with `detectorVersion="manual-shot-ownership-v1"`, null qualified-detector distances/accuracy and no invented detector booleans, so the existing score-confirmation Cancel is the sole “仍算上一洞” decision. A completely missing coordinate cannot construct `UnownedShotDraft` and rejects capture without an event/slot mutation, offering “等待定位” and the independent `确认成绩` action. Thus a player hitting from the next Tee before detector dwell can never silently write that shot to the previous hole, while a previous-hole recovery shot near that Tee remains recoverable through Cancel.

`previousHole` and `verifiedNextHole` are Track A `scoreSlot` values resolved only from the current `roundPolicy.orderedHoleSequence` cursor; map/label lookup follows the same row's `holeSubjectRef/displayHole` and never increments a physical hole number. `scopeId` is deterministically frozen from `(roundIncarnationId,orderedHoleCursor,previousScoreSlot,candidateNextScoreSlot-or-final)`；GPS samples、device ID and resolution UUID never enter it, so two offline devices detecting the same transition conflict in one scope while different transitions keep distinct audit identities without becoming parallel active confirmations. `HoleScoreCoordinator` first requires no actionable resolution anywhere in the incarnation, freezes the detector evidence and default suggestion into one Track A exact `resolution_opened` event through `ResolutionOpenedWireFactory`, then calls `appendLocalResolutionOpenIfVacantAtomically`; once appended, every surface renders that canonical payload instead of recomputing a different suggestion from later GPS.

`HoleTransitionCheckpointStore` durably exact-keys `{partition,policyHash,orderedHoleCursor,checkpointGeneration,lastAcceptedObservedAt,greenEntryObserved,completionApproachObserved,departedCurrentHole,maximumCertainForwardProgressM,maximumCertainTeeReductionM,adjacentFairwayRisk,backtrackGeneration}` through D14a's fsync-file/atomic-rename/fsync-directory primitive. It stores no raw path、coordinate history、speed samples、monotonic sequence、candidate resolution ID or score suggestion. Monotonic ordering is boot-local evidence only. Startup requires the active `(roundId,roundIncarnationId)` partition、same ordered cursor and exact LRP `policyHash`; corruption/hash mismatch disables only automatic detection and exposes the manual action. Restart increments `checkpointGeneration`, retains the completion/departure latches but deliberately resets consecutive fixes、arrival and dwell to zero and requires three fresh fixes. A checkpoint older than `180.0 s` starts a fresh detector generation without replaying old arrival evidence. A canonical `resolution_opened` always wins over the checkpoint, so a crash after open never emits a second episode.

The Hole Root also has an explicit `完成本洞/确认成绩` action. It uses the same ordered-hole cursor and same deterministic scope—not a separate manual-score state machine—and opens `.nextHole` or `.finalHole` with Track A's exact manual evidence: `detectorVersion="manual-transition-v1"`, the exact LRP `policyHash`, both distances and maximum accuracy null, every detector boolean false, fix count/span/dwell/forward progress `0`, and a durable player-action evidence ref. It does not require map、GPS or Guidance and never switches holes before the resulting ResolutionCommit. Automatic、shot-triggered and manual opens racing on the same device are serialized by open-if-vacant: one exact event wins and each loser reloads/presents that existing canonical episode instead of creating a local conflict. Only different-device offline opens in the same deterministic scope are retained as an explicit conflict.

`manual-shot-ownership-v1` uses the same exact null/false/zero evidence shape but carries the durable captured-action/preflight evidence refs and is legal only when an unowned preparation already exists for the same active shot ID. It cannot be called as a generic “finish hole” shortcut. Both manual detector versions are enumerated in generated validation and never confused with the automatic policy version.

If a shot is captured while an episode is unresolved, `ShotCaptureSession` uses the **current** active preallocated `shotId` to build `resolution_shot_staged(resolutionId,shotId,captureOrdinal,location,lie,provenance,evidenceRefs)` caused by the open event, then calls `appendResolutionStageAndReserveNextAtomically`. Only that transaction may claim the ID, append the operational event and rotate the slot. No `shot_recorded` exists yet, so score/statistics/calibration cannot double count it. Watch immediately exports these operational bytes in a signed `PeerLedgerBundle`; iPhone import preserves Watch origin and adds them as peer-provisional outbox items without inventing a server ACK. This is the sole Watch→iPhone takeover path; copying the journal or constructing a phone episode is forbidden.

For the first-shot-before-open race, `TransitionShotPreparationJournal` persists an exact `TransitionShotPreparation{partition,preparationId,sourceActionId,shotId,capturedAt,unownedDraft,policyHash,orderedHoleCursor,scopeId,resolutionId,canonicalOpenEventBytes,openEventIdentity,canonicalStageEventBytes,stageEventIdentity,state}` before any ordinary append or shot-slot mutation. `unownedDraft` is D14b's exact `UnownedShotDraft` and cannot carry a hole. States are exact `prepared|open_bound|stage_prepared|staged|terminal|blocked_by_other_scope`; nullable episode/event/byte fields must be present as JSON null until bound, and any populated bytes are re-decoded、hash-checked and reused exactly. Recovery performs one prepared saga:

1. reverify the same LRP cursor/policy and current active `shotId`; a mismatch remains visible and fail-closed;
2. call `appendLocalResolutionOpenIfVacantAtomically` with stable prepared open bytes, or if detector/manual already won the same scope, atomically replace the losing prepared-open tuple with the winner's exact canonical bytes/identity and bind it rather than minting another resolution;
3. durably store exact stage bytes caused by that canonical open, then call `appendResolutionStageAndReserveNextAtomically`;
4. mark terminal only after the ledger returns the idempotently advanced slot.

If a different-scope actionable episode blocks opening, the preparation stays `blocked_by_other_scope` and ordinary append remains forbidden until that flow terminalizes. Strong-kill tests stop before/after preparation replacement、open append、open binding、stage preparation、stage append、slot rotation and journal terminal marking. At every restart the same shot becomes exactly one staged operation or remains visibly blocked；it never becomes an ordinary previous-hole shot and never rotates twice.

At the terminal cursor, no next-hole episode or tentative next-hole ownership exists. After completion is armed, certain departure by `18.0 m` plus stationary dwell `>= 12.0 s`, or `90.0 s` elapsed since that qualified departure, may create canonical `.finalHole`; explicit Finish uses the same scope immediately. A cart pass alone before completion/departure cannot. The reducer and server cannot enter `finished` while that episode is unresolved；a `round_finished` event is legal only as the last child of the target `resolution_closed` inside one accepted `ResolutionCommit`.

- [ ] **Step 4: Build honest default suggestions and quick/manual semantics**

`FirstShotLandingClassifier` is the sole Par 4/5 prefill owner. It reads the canonical effective-shot sequence for the previous `scoreSlot`, selects the **last effective Tee shot** after D14a Tee-last-wins, and uses only the next causally/order-confirmed effective full shot's start-position as the Tee shot's landing evidence. A displayed trajectory、GPS after the fact、Guidance prediction、current player position or the Tee shot's own start lie is never landing evidence. Par 3 returns `.notApplicable` without geometry lookup.

For Par 4/5, classification requires the same-hole verified `guidance.playable-regions` authority and verified map route/hash. The next-shot horizontal-accuracy disk plus registration residual must lie strictly inside exactly one current-hole `lieKind=fairway` region to return `.hit`. Otherwise it must have one unambiguous projection onto the current hole route；using the increasing Tee→Green tangent `t` and landing offset `d`, `cross=t.east*d.north-t.north*d.east` is left when strictly positive and right when strictly negative. The complete uncertainty disk must stay on that side after accuracy/residual inflation. Boundary contact、disk overlap with fairway or multiple regions、route vertex/tangent ambiguity、near-zero cross value、off-route projection gap、a region/subject belonging to an adjacent hole/fairway、missing next-shot origin、retracted next shot、cross-device causal/order ambiguity or absent playable-region authority returns `.unknown`, never a list-order or nearest-fairway guess.

The classifier returns only `hit|miss_left|miss_right|unknown|not_applicable` to `DefaultHoleScoreSuggestion`/score presentation. It appends no event and never rewrites either shot's `startLie`. Quick writes `fairway_set` only for hit/left/right or Par 3 N/A；unknown stays absent, while Manual may ask the player for the final Fairway value. Tests mutate region order、accuracy radius、route tangent、subject and shot ordering to prove the result is deterministic and fail-closed.

The suggestion counts non-retracted effective full shots only:

- the installed LRP Par is required for Quick suggestion. The base is `effectiveFullShots + 2`, but the final suggested total is `max(holePar,effectiveFullShots + 2)`；the system never treats missing shot observations as magical under-Par play;
- when `effectiveFullShots == 0` or `effectiveFullShots + 2 < holePar`, the Par floor is visibly low-confidence with reason `incomplete_shot_evidence_par_floor`; this is a score default, not fabricated missing `shot_recorded` facts. If verified Par is unavailable, Quick is unavailable and Manual is required;
- verified Green entry otherwise uses the two-putt estimate with reason `green_departure_default`;
- departure without verified Green entry otherwise uses the same two-putt estimate with reason `unobserved_putts_two_putt_estimate`; absence of Green entry is not evidence that the ball was holed;
- when completion was armed only by the frozen approach evidence and Green entry is false, the UI derives advisory copy `possible_chip_in` from that canonical episode evidence and may show “如果切进，请手动改为 0 推”；the advisory is not a suggestion field and changes no suggested value、Quick fact、score minimum or canonical evidence;
- v1 permits a zero-putt result only when the player explicitly chooses `putts=0` in Manual confirmation；a future sensor-backed holed-out default requires a separately versioned evidence rule and cannot be inferred from visiting or not visiting the Green;
- an explicit `manual-transition-v1` with unavailable geometry uses the same formula. If the Par floor applies, `reasonCode=incomplete_shot_evidence_par_floor` and the UI derives the secondary manual-transition explanation from the frozen detector version；otherwise `manual_transition_two_putt_estimate` is primary. It never claims Green entry evidence;
- penalties default to zero because they cannot be sensed;
- Par 3 fairway is `not_applicable`;
- Par 4/5 fairway is `hit|miss_left|miss_right` only from verified first-shot landing classification; otherwise unknown.

Quick “确认” atomically adopts every available suggested fact and opens no additional steps: it prepares exact Track A `hole_score_set`、`putts_set`、`penalties_set` and, when available, `fairway_set`; it never converts `possible_chip_in` into zero putts. Par 3 N/A is available and written, verified Par 4/5 fairway is written, genuinely unknown Par 4/5 fairway remains unknown and is not silently invented. Manual confirmation walks exact total score → putts → Par 4/5 fairway → penalties and writes the complete chosen set；selecting zero putts is an explicit player decision. Validation prevents totals below the chosen effective-shot/putt/penalty minimum.

`TransitionStageOwnershipClassifier` is a conservative presentation/default helper over the target episode's canonical staged rows；it does not append an event and never changes Track A dispositions by itself. Rows are sorted by `(captureOrdinal,stagedEventIdentity)`. It may return `verified_next` only when the first still-distinct staged origin is definitely inside the ordered next Tee launch region with verified `lie=tee`, its full uncertainty disk does not overlap previous/adjacent-hole playable or Tee ownership, no earlier ambiguous recovery row exists, and each later row has unambiguous causal order and forward continuation on the verified next-hole route. Multiple ordered Tee-origin rows at that same verified next-Tee station are **not** a Mulligan question when they share one origin device/epoch and have no intervening previous-hole recovery or cross-device ordering ambiguity: every row is safely `verified_next`, Quick remains legal, and after assignment D14a's Tee-last-wins reducer retracts/supersedes the earlier attempts so only the last effective shot and its Club Prompt survive. Missing geometry、boundary/accuracy overlap、cross-device order ambiguity、backtracking、a prior rough/bunker/fringe recovery origin near the next Tee or any unresolved D14a station identity ambiguity returns `manual_required`. It never infers `previous_hole`; that ownership always comes from explicit Cancel or Manual choice.

Quick is available with zero staged rows or only when **every** target-owned staged row is `verified_next`; it then maps each to Track A `assigned_next`. Cancel remains the deliberate whole-episode recovery action: it maps every target-owned staged row to `assigned_previous`, writes no score facts and does not advance the active-play cursor. If there is more than one target stage or any row is `manual_required`, Manual inserts one ownership step before score submission and requires an explicit previous/next choice for every target stage；no row is preselected and the final control remains disabled until the exact sorted roster is complete. Thus “上一洞在下一洞 Tee 附近救球，随后才真正开球” can become `assigned_previous` then `assigned_next` in one ResolutionCommit. Manual still completes the previous-hole score and therefore advances the active cursor after the sealed commit even when one or more staged shots were assigned previous.

The choices are local decision input only and compile directly into Track A `stagedShotDispositions`; there is no new ownership event or parallel wire type. A stage with `provenance=autoshot_observed` becomes final `autoshot_confirmed` at whichever explicitly chosen destination, while a manual stage remains `manual`. Every target stage appears once, every assigned stage has exactly one matching final shot, and previous/next assignments may coexist. Same-device ordered next-Tee attempts are first assigned next so ownership is honest, then the already frozen D14a Tee-last-wins canonicalizer causally retracts every superseded attempt before any Club Prompt becomes visible；statistics/calibration expose only the final effective Tee shot. Because Track A's frozen `decisionHash` includes the complete sorted `stagedShotDispositions` and ordered final-event identities, changing one target choice necessarily changes `decisionHash` and `resolutionCommitId`; a retry with old IDs and new ownership fails. An unfinished form、Back、timeout or crash writes neither dispositions nor final facts and reopens the canonical rows unselected；after `ResolutionCommitRequest` preparation, restart/takeover reuses the exact body and never replays UI choices. Same-scope loser stages remain governed by `ResolutionConflictMergeSelection` and cannot consume a target-stage choice; different-scope queued episodes remain outside the request.

- [ ] **Step 5: Prepare stable `ResolutionCommit` bytes before any final-fact append**

```swift
public enum TargetStageOwnershipAssessment: String, Codable, Sendable {
    case verifiedNext = "verified_next"
    case manualRequired = "manual_required"
}

public enum TargetStagePlayerChoice: String, Codable, Sendable {
    case previousHole = "previous_hole"
    case nextHole = "next_hole"
}

public struct TargetStageOwnershipSelection: Codable, Equatable, Sendable {
    public let stagedEventIdentity: String
    public let choice: TargetStagePlayerChoice
}

public enum LoserStagePlayerChoice: Codable, Equatable, Sendable {
    case keepPrevious
    case keepNext
    case discard(reasonCode: String)
}

public struct ResolutionConflictMergeSelection: Codable, Equatable, Sendable {
    public let stagedEventIdentity: String
    public let choice: LoserStagePlayerChoice
}

public enum HoleScoreDecision: Codable, Equatable, Sendable {
    case acceptDefault(suggestionId: String)
    case manual(
        score: Int,
        putts: Int,
        fairway: HoleFairwayValue,
        penalties: Int,
        targetStageOwnership: [TargetStageOwnershipSelection],
        conflictMerge: [ResolutionConflictMergeSelection]
    )
    case cancel
}

public final class HoleScoreTransaction {
    public func prepare(
        resolutionId: String,
        roundId: String,
        roundIncarnationId: String,
        decision: HoleScoreDecision,
        journal: PendingShotOwnershipJournal,
        projection: DomainRoundProjection,
        builder: DomainEventBuilder,
        occurredAt: String
    ) throws -> ResolutionCommitRequest {
        let episode = try journal.requireCanonicalEpisode(
            resolutionId: resolutionId,
            roundId: roundId,
            roundIncarnationId: roundIncarnationId
        )
        let request = try HoleScoreResolutionRequestFactory.make(
            episode: episode,
            decision: decision,
            projection: projection,
            builder: builder,
            occurredAt: occurredAt
        )
        try journal.verifyPreparedRequest(request, for: resolutionId)
        return request
    }

    public func appendLocally(
        _ request: ResolutionCommitRequest,
        ledger: DomainLedgerStore,
        sourceDeviceId: String,
        sourceCredentialId: String,
        takeoverGeneration: Int
    ) throws -> ResolutionCommitOutboxRecord {
        let body = try CanonicalJSON.data(request)
        return try ledger.prepareResolutionCommit(
            request: request,
            canonicalRequestBody: body,
            sourceDeviceId: sourceDeviceId,
            sourceCredentialId: sourceCredentialId,
            takeoverGeneration: takeoverGeneration
        )
    }

    public func recoverPrepared(
        resolutionId: String,
        roundId: String,
        roundIncarnationId: String,
        journal: PendingShotOwnershipJournal,
        ledger: DomainLedgerStore
    ) throws -> ResolutionCommitOutboxRecord {
        try journal.requireCanonicalEpisode(
            resolutionId: resolutionId,
            roundId: roundId,
            roundIncarnationId: roundIncarnationId
        )
        return try ledger.requireResolutionCommit(
            resolutionId: resolutionId,
            roundId: roundId,
            roundIncarnationId: roundIncarnationId
        )
    }
}
```

`TargetStageOwnershipSelection` and `ResolutionConflictMergeSelection` are local decision inputs, not second wire contracts or durable facts. The factory accepts both only for `.manual`, requires each roster sorted-unique by staged identity and rejects any overlap. Target choices must cover exactly every target stage when the classifier requires Manual ownership；they cannot name loser/equivalent/foreign stages and derive only `assigned_previous|assigned_next`. Conflict choices may name only unresolved loser stages, derive assigned dispositions plus `decision.confirmedLoserStageEventIdentities` from `keepPrevious|keepNext`, and derive `explicitly_discarded` only from `.discard(reasonCode:)`. The completed selections become durable only inside the atomically prepared canonical `ResolutionCommitRequest`; an abandoned or partially completed UI draft cannot mutate claims or serve as ownership/discard evidence. `.acceptDefault` and `.cancel` construct the exact Track A decision with an empty confirmed-loser roster and no caller-supplied target selection.

`HoleScoreResolutionRequestFactory` builds the exact Track A `ResolutionCommitRequest`; it does not define a second request、transaction-ref、decision or staged-disposition wire type. It assigns stable final event IDs, creates the exact `ResolutionCommitTransactionRef`, computes Track A's decision hash/commit ID, includes the open and every staged event identity as required causes, and emits one linear final chain. `requiredCauseEventIdentities`、`supersededResolutionIds` and `stagedShotDispositions` use Track A's canonical sorted-unique rules. For each assigned stage, the resolved per-stage disposition first determines the exact destination score slot (`assigned_next → verifiedNextHole`, `assigned_previous → previousHole`)；only then may the factory construct a `ManualShotDraft(hole:destination,latitude:...,longitude:...,horizontalAccuracyM:...,lie:...)` and pass it to the shared `shot_recorded` builder. No pre-commit type or cache may construct or persist that hole-bearing draft. In the normal one-head case, Quick builds previous-hole score facts only after independently recomputing that every target stage is `verified_next`, assigns all of them next, appends the matching `shot_recorded` facts, then closes the target. Manual builds the score facts and uses the exact completed per-stage selection, allowing previous and next assignments in the same request, before closing. Cancel builds no score facts, assigns every target-owned stage to `previousHole`, then closes. Final-hole Quick/Manual has no next-owned stage roster, builds score facts, closes, then appends `round_finished` directly caused by that close. A same-scope conflict must first satisfy the stricter merge rules below；the ordinary Quick/Cancel shortcuts cannot guess what a loser-owned observation means.

A concurrent same-scope conflict includes every exact loser ID and one causal `resolution_closed(disposition=superseded)` event per loser. Every target and loser staged event appears exactly once in the same request's `stagedShotDispositions`, with its real `owningResolutionId`. Track A's sealed conflict rules apply unchanged:

- a loser observation proven exact-equivalent by Track A's byte/evidence-equivalence predicate may be `coalesced` into a target/winner stage that resolves without cycles to one assigned disposition；mere GPS proximity、matching club or similar time is never enough;
- an ambiguous or physically distinct loser observation is never silently coalesced、assigned or discarded. The factory remains blocked and prepares no commit/outbox bytes until the conflict-merge UI records an explicit choice for that exact staged identity;
- “保留此杆” is legal only through `decision.disposition=manually_confirmed`; the loser stage identity must appear in sorted-unique `decision.confirmedLoserStageEventIdentities`, receive `assigned_previous|assigned_next`, and name exactly one final `shot_recorded` identity;
- “删除此记录” may produce `explicitly_discarded` only from a durable explicit player choice and a non-empty player-confirmed `reasonCode`; absence、dismissal、timeout、Quick accept or Cancel is not discard evidence;
- `accepted_default` and `cancelled` always carry an empty `confirmedLoserStageEventIdentities` roster. They may coalesce only already-proven exact-equivalent observations and otherwise leave the conflict unresolved;
- every assigned disposition and final `shot_recorded` forms Track A's bidirectional bijection by stage identity、`shotId`、destination hole、provenance and final event identity. The sorted confirmed-loser roster is part of `decisionHash`, so changing one keep choice changes both the hash and `resolutionCommitId`;
- a retained loser is one ordinary confirmed physical shot and therefore enters canonical statistics and club calibration exactly once. A loser episode itself still creates no independent score/putt/penalty/fairway facts and no target-style close；its only episode fact is the required causal `resolution_closed(disposition=superseded)`;
- every target+loser claim transitions to `.commitConsumed` with its real owner/disposition evidence. Missing/duplicate dispositions、an unconfirmed assigned loser、a retained loser without one matching final shot、an unreferenced final shot、silent discard or any pre-commit fault rolls back all claims、score/shot facts、heads、receipts and finish state.

Different-scope queued episodes are never smuggled into this request；they are reconciled one at a time through their own exact ResolutionCommit after the current actionable flow terminalizes. The factory round-trips its result through Track A's strict decoder and golden fixture before returning it.

Track A `DomainLedgerStore.prepareResolutionCommit(...)` is the sole local append boundary and returns its exact durable `ResolutionCommitOutboxRecord`: in one state-file transaction it validates every prerequisite/shot claim, appends all final events as one provisional bundle, updates projection, and stores the unchanged canonical request body/hash/prerequisite/final roster. It does **not** place those final events in the ordinary per-event transport queue. Restart reuses the exact body; conflicting retry fails closed. Track A sync uploads/ACKs missing operational prerequisites first, then posts those preserved bytes to `/resolutions/{id}/commit`; the whole response roster applies atomically. A server 409 retains the losing local branch as a visible conflict rather than deleting facts or silently switching holes.

Club Prompts remain queued by staged-shot order and become visible only after the local commit exists; server conflict pauses them until the ownership conflict is resolved.

- [ ] **Step 6: Build highest-priority Watch/iOS confirmation, peer takeover and deep editing**

`WatchHoleScoreConfirmView` is the highest-priority overlay and haptics once per canonical episode revision. It shows the previous hole, frozen suggested score/putts/penalties/fairway summary and actions “确认”/“手动”/“取消”. Quick confirm does not open detail questions. While visible, Club Prompt and instruments pause.

Before enabling Quick, `WatchHoleScoreCoordinator` independently recomputes the exact target-stage ownership assessment from canonical rows and verified authority. If every row is `verified_next`, “确认” stays one tap；same-device ordered Tee attempts remain in this path and D14a leaves only the last effective shot. If any row is `manual_required`, Quick is replaced by “核对击球并记分”, while “取消” remains the explicit whole-roster previous-hole action. `WatchManualHoleScoreFlow` preserves the requested score → putts → Par 4/5 fairway → penalties order, then presents one compact “击球归属” row per staged shot only when multiple/ambiguous ownership requires it. Each row shows capture order、localized start lie、origin-device marker and map-relative distance when verified, with two unselected actions “上一洞”/“下一洞”；no ball flight or default is invented. The final submit is disabled until every required row has one choice. iPhone renders the same shared model with more map space, not another ownership algorithm.

When the selected scope has concurrent heads, the same overlay replaces Quick/Cancel with one primary action “核对记录（N）”; neither dismissal nor a timeout chooses a loser disposition. `WatchManualHoleScoreFlow` and `ReviewEditHoleView` render the identical conflict-merge model in canonical `(owningResolutionId,captureOrdinal,stagedEventIdentity)` order. Each row shows source device、captured time、recorded lie and distance between recorded origins when available；it never invents ball flight. Track A-proven exact-equivalent rows are read-only as “重复记录，已合并”. Every remaining ambiguous loser row must receive exactly one explicit choice: “保留到上一洞”, “保留到下一洞”, or destructive “删除此记录” followed by a second confirmation that supplies the player-confirmed reason. “稍后” and Back retain the unresolved conflict without preparing bytes. The final “确认合并并记分” control stays disabled until one target head is selected and every ambiguous loser has a choice；any keep choice forces the `.manual` decision even when the entered score equals the frozen suggestion. The coordinator passes only the resulting sorted `ResolutionConflictMergeSelection` list to the factory. A restart before final confirmation safely loses only the unfinished form choices and reopens the same canonical conflict；a restart after confirmation reloads the exact prepared request body, never reconstructs choices from UI state.

`HoleScoreCoordinator`/the shared interaction arbiter derives exactly one `actionableResolutionId` per round incarnation. It prefers the unresolved scope matching the current ordered-hole cursor; otherwise it selects the lowest queued `(orderedHoleCursor,scopeId,resolutionId)` conflict for explicit reconciliation. Same-scope multiple heads require a durable takeover/target selection and expose only that target's controls；all other heads are read-only evidence until the target commit closes/supersedes them. A different-scope queued row never presents a second sheet、haptic or mutable score form. Watch and iPhone render the same selected ID, and a surface without the current takeover generation is read-only.

`WatchResolutionPeerTransfer` uses the Track A `PeerLedgerBundle` factory and exports every new ordinary/prerequisite operational event plus any exact local `state=prepared|submitted` `ResolutionCommitOutboxRecord` as Track A `PreparedResolutionCommitTransfer`. The wire type keeps its sole legal `state="prepared"` value: local `submitted` is only a transport-attempt state and is deliberately normalized away, while the preserved request body/hash、`ResolutionCommitTransactionRef`、prerequisite roster、final identity/hash roster、source credential and takeover generation remain byte-identical. Accepted or conflicted records are never transfer payloads. `WatchEventBridge` calls Track A's paired-credential signature verifier and one-transaction import API; takeover selects the same `resolutionId/openEventIdentity/staged shot IDs`, never reconstructs an episode or request. Final provisional bytes remain inside the exact prepared request body and become local commit-final projection only through that verified import. If Watch posted the commit and lost the response, iPhone imports the normalized transfer, reposts those exact bytes and validates the server's cached idempotent success. Exactly one surface may present mutable controls at a time using the durable monotonic takeover generation；same-generation exact bundle retry is idempotent, a different bundle or late UI action fails closed.

Both iOS and Watch expose scorecard routes for arbitrary-hole correction, but an unresolved episode owns its `previousHole` score decision. Editing that same score slot while the episode is open routes into the episode's manual flow (or requires an explicit Cancel/terminal resolution first); it may not append an ordinary competing score fact that quick confirm would overwrite or reject on base revision. Other completed holes may still receive ordinary causal superseding score/putt/fairway/penalty events at any time. After the episode's ResolutionCommit is locally prepared/terminal, its hole may also use the normal historical edit path. These edits never change `activePlayHole`, episode ownership or another hole's Club Prompt. Replay/restart and statistics use the superseding canonical facts.

- [ ] **Step 7: Run complete transition/reducer/atomic-server suites**

Run:

```bash
uv run python tools/contracts/generate_contracts.py
uv run python -m unittest tests.test_contract_codegen -v
swift test --filter GuidanceContractTests
npm --prefix web_v2 test -- --run src/contracts/generated.test.ts
swift test --filter 'HoleTransitionTimelineTests|HoleScoreTransactionTests|FirstShotLandingClassifierTests|TransitionStageOwnershipClassifierTests|ActivePlayCursorProjectorTests|ResolutionCommitTests|PeerLedgerBundleTests|WatchHoleScoreFlowTests|HoleScoreDeepEditTests'
swift test --filter 'DomainRoundReducerTests|DomainLedgerStoreTests|ManualShotProducerTests|ClubPromptRecoveryTests|WatchEventBridgeTests'
uv run python -m unittest tests.test_resolution_commit_v2 tests.test_active_play_cursor tests.test_active_play_cursor_source_boundaries tests.test_round_reducer_v2 -v
```

Expected: PASS for exact cross-language policy hash/threshold parity, chip-in/never-entered-Green completion without inferred zero putts, Green +2, no-Green +2 with advisory-only `possible_chip_in`, explicit-manual-only zero putts, zero/partial shot evidence using a visible verified-Par floor rather than impossible under-Par defaults, missing Par forcing Manual, score-only manual transition with null geometry, Par 3 N/A, strict Par 4/5 first-landing classified/unknown, cart/adjacent/backtracking, first-next-Tee-shot detector race, every preparation/open/stage/rotation kill point, multiple tentative shots, same-device next-Tee attempts remaining Quick-eligible with D14a Tee-last-wins, previous-hole recovery plus true next-Tee shot receiving explicit mixed ownership, target-choice decision-hash drift, one locally actionable episode per incarnation, different-scope read-only conflict queuing, same-scope concurrent remote conflict, exact-equivalent loser coalescing, default/cancel empty confirmed-loser roster, ambiguous-loser commit blocking, explicit discard evidence, manual retention of each distinct physical loser shot exactly once, decision-hash/final-shot bijection, no loser-owned score facts and normal statistics/calibration for retained final shots, deterministic active cursor across Quick/Manual/Cancel/final-hole/deep-edit/restart/takeover/conflict, custom/shotgun order, checkpoint restart, Watch→iPhone prepared/submitted exact-body takeover including lost-response cached success, one server winner, no partial commit and arbitrary Watch/iOS edits.

- [ ] **Step 8: Commit S70 score/ownership flow**

```bash
git add \
  contracts/canonical/hole_transition_policy_v1.schema.json \
  contracts/canonical/fixtures/hole_transition_policy_golden.json \
  contracts/canonical/fixtures/active_play_cursor_timelines.json \
  contracts/canonical/live_round_package_v2.schema.json \
  contracts/canonical/canonical_object_registry.json \
  tools/contracts/generate_contracts.py \
  ai_caddie/contracts/generated.py \
  ai_caddie/rounds/resolution_commit.py \
  ai_caddie/rounds/ledger_repo.py \
  ai_caddie/rounds/active_play_cursor.py \
  ai_caddie/rounds/reducer_v2.py \
  tests/resolution_commit_fixtures.py \
  tests/test_resolution_commit_v2.py \
  tests/test_active_play_cursor.py \
  tests/test_active_play_cursor_source_boundaries.py \
  tests/test_round_reducer_v2.py \
  tests/test_contract_codegen.py \
  mobile/ios/AICaddieDomain/GeneratedContracts.swift \
  mobile/ios/AICaddieDomain/ResolutionCommit.swift \
  mobile/ios/AICaddieDomain/DomainRoundProjection.swift \
  mobile/ios/AICaddieDomain/DomainRoundReducer.swift \
  mobile/ios/AICaddieDomain/Scoring/HoleTransitionPolicy.swift \
  mobile/ios/AICaddieDomain/Scoring/HoleTransitionEvidence.swift \
  mobile/ios/AICaddieDomain/Scoring/ResolutionEpisode.swift \
  mobile/ios/AICaddieDomain/Scoring/ProvisionalHoleState.swift \
  mobile/ios/AICaddieDomain/Scoring/ActivePlayCursorProjector.swift \
  mobile/ios/AICaddieDomain/Scoring/ResolutionOpenedWireFactory.swift \
  mobile/ios/AICaddieDomain/Scoring/ResolutionShotStagedWireFactory.swift \
  mobile/ios/AICaddieDomain/Scoring/HoleTransitionDetector.swift \
  mobile/ios/AICaddieDomain/Scoring/HoleTransitionCheckpointStore.swift \
  mobile/ios/AICaddieDomain/Scoring/TransitionShotPreflight.swift \
  mobile/ios/AICaddieDomain/Scoring/TransitionShotPreparationJournal.swift \
  mobile/ios/AICaddieDomain/Scoring/DefaultHoleScoreSuggestion.swift \
  mobile/ios/AICaddieDomain/Scoring/FirstShotLandingClassifier.swift \
  mobile/ios/AICaddieDomain/Scoring/TransitionStageOwnershipClassifier.swift \
  mobile/ios/AICaddieDomain/Scoring/PendingShotOwnershipJournal.swift \
  mobile/ios/AICaddieDomain/Scoring/HoleScoreTransaction.swift \
  mobile/ios/AICaddieDomain/Scoring/HoleScoreResolutionRequestFactory.swift \
  mobile/ios/AICaddieDomain/Scoring/HoleScoreCoordinator.swift \
  mobile/ios/AICaddieDomain/ShotCapture/ShotCaptureSession.swift \
  mobile/ios/AICaddieDomain/ShotCapture/ManualShotProducer.swift \
  mobile/ios/AICaddieDomain/DomainLedgerStore.swift \
  mobile/ios/AICaddieDomainTests/DomainLedgerStoreTests.swift \
  mobile/ios/AICaddieDomainTests/HoleTransitionTimelineTests.swift \
  mobile/ios/AICaddieDomainTests/HoleScoreTransactionTests.swift \
  mobile/ios/AICaddieDomainTests/FirstShotLandingClassifierTests.swift \
  mobile/ios/AICaddieDomainTests/ActivePlayCursorProjectorTests.swift \
  mobile/ios/AICaddieDomainTests/TransitionStageOwnershipClassifierTests.swift \
  mobile/ios/AICaddieDomainTests/Fixtures/active_play_cursor_timelines.json \
  mobile/ios/AICaddieDomainTests/ManualShotProducerTests.swift \
  mobile/ios/AICaddieDomainTests/GuidanceContractTests.swift \
  mobile/ios/AICaddieDomainTests/ResolutionCommitTests.swift \
  mobile/ios/AICaddieWatch/Services/WatchHoleScoreCoordinator.swift \
  mobile/ios/AICaddieWatch/Services/WatchResolutionPeerTransfer.swift \
  mobile/ios/AICaddieWatch/Views/Scoring/WatchHoleScoreConfirmView.swift \
  mobile/ios/AICaddieWatch/Views/Scoring/WatchManualHoleScoreFlow.swift \
  mobile/ios/AICaddieWatch/Views/Scoring/WatchScorecardEditView.swift \
  mobile/ios/AICaddieWatch/Views/WatchRoundContainerView.swift \
  mobile/ios/AICaddie/Views/CurrentHoleView.swift \
  mobile/ios/AICaddie/Views/ReviewEditHoleView.swift \
  mobile/ios/AICaddieWatchTests/WatchHoleScoreFlowTests.swift \
  mobile/ios/AICaddieTests/HoleScoreDeepEditTests.swift \
  web_v2/src/contracts/generated.ts \
  web_v2/src/contracts/generated.test.ts
git commit -m "feat: add atomic cross-device S70 hole resolution"
```

## Task D15: Add AutoShot last with candidate fallback and evidence-gated automatic recording

**Depends on:** completed D14b manual score/ownership milestone and D15 Step 0's exact closure of Tracker D12a/D12b/D13a/E05/E06/T030/T031. Tracker D13b is conditional only: it reopens to Owner if platform evidence leaves Health saving as a real product choice or makes it technically unavoidable. AutoShot is not part of the first production milestone.

**Product law:** raw detection alone is not a shot fact. A candidate may be journaled while another overlay is active. During an unresolved D14b episode, an evidence-qualified observation with a verified or explicit player-selected start lie may become a canonical **operational** `resolution_shot_staged` with a reserved `shotId`, but still no `shot_recorded`; the player's D14b Quick/Manual/Cancel decision is the explicit ownership confirmation that converts it inside the atomic `ResolutionCommit`. Outside an episode, Candidate mode and any uncertain Automatic-mode observation still require explicit “算一杆” confirmation, including a lie choice when verification is absent. Only a signed-evidence-approved high-confidence Automatic observation with non-null verified lie、both ownership fields null、no unresolved episode owning the impact scope、an unreserved active shot ID and an exact `.ordinaryCurrentHole` preflight may atomically append `shot_recorded` without that extra confirmation. Score confirmation always has priority and AutoShot never auto-resolves an episode or guesses previous/next-hole ownership.

**Files:**
- Modify: `contracts/canonical/authority.json`
- Regenerate: `contracts/canonical/round_event_v2.schema.json`
- Modify: `ai_caddie/rounds/projection_contract.py`
- Regenerate: `contracts/canonical/round_projection_v2.schema.json`
- Create: `contracts/canonical/fixtures/round_trace_autoshot_automatic.json`
- Regenerate: `ai_caddie/contracts/generated.py`
- Regenerate: `mobile/ios/AICaddieDomain/GeneratedContracts.swift`
- Regenerate: `web_v2/src/contracts/generated.ts`
- Modify: `tests/test_contract_codegen.py`
- Modify: `tests/test_round_projection_contract.py`
- Modify: `tests/test_round_conformance_v2.py`
- Modify: `tests/test_round_reducer_v2.py`
- Modify: `web_v2/src/contracts/generated.test.ts`
- Modify: `web_v2/src/contracts/projectionDecoder.test.ts`
- Create: `web_v2/src/contracts/fixtures/round_trace_autoshot_automatic.json`
- Create: `ops/validate_autoshot_evidence.py`
- Create: `ops/run_watch_autoshot_evidence.sh`
- Create: `ops/build_autoshot_evidence_closure.py`
- Create: `tests/test_autoshot_evidence_gate.py`
- Create: `tests/test_autoshot_evidence_closure.py`
- Create: `mobile/ios/evidence/autoshot_evidence_plan.json`
- Create after real-device run: `mobile/ios/evidence/autoshot_evidence_closure.envelope.json`
- Create: `mobile/ios/evidence/autoshot_device_profiles.envelope.json`
- Create: `mobile/ios/evidence/autoshot_trust_store.json`
- Create: `mobile/ios/AICaddieDomain/ShotCapture/AutoShotEvidence.swift`
- Create: `mobile/ios/AICaddieDomain/ShotCapture/AutoShotControl.swift`
- Create: `mobile/ios/AICaddieDomain/ShotCapture/AutoShotCandidate.swift`
- Create: `mobile/ios/AICaddieDomain/ShotCapture/AutoShotDecisionOutbox.swift`
- Create: `mobile/ios/AICaddieWatch/Services/WatchMotionShotProducer.swift`
- Create: `mobile/ios/AICaddieWatch/Services/WatchAutoShotEvidenceRecorder.swift`
- Create: `mobile/ios/AICaddieWatch/Services/WatchAutoShotCoordinator.swift`
- Create: `mobile/ios/AICaddieWatch/Views/ShotCapture/WatchAutoShotCandidateView.swift`
- Create: `mobile/ios/AICaddieWatch/Views/ShotCapture/WatchAutoShotLiePickerView.swift`
- Modify: `mobile/ios/AICaddieWatch/Views/WatchRoundContainerView.swift`
- Modify: `mobile/ios/AICaddieDomain/ShotCapture/ShotCaptureSession.swift`
- Modify: `mobile/ios/AICaddieDomain/ShotCapture/ManualShotProducer.swift`
- Modify: `mobile/ios/AICaddieDomain/ShotCapture/ShotObservationJournal.swift`
- Modify: `mobile/ios/AICaddieDomain/Scoring/PendingShotOwnershipJournal.swift`
- Modify: `ai_caddie/rounds/ledger_models.py`
- Modify: `ai_caddie/rounds/ledger_repo.py`
- Modify: `ai_caddie/rounds/reducer_v2.py`
- Modify: `server_v2/round_ledger_api.py`
- Modify: `tests/test_round_event_ingest_v2.py`
- Modify: `tests/test_resolution_commit_v2.py`
- Modify: `mobile/ios/AICaddieDomain/DomainRoundEvent.swift`
- Modify: `mobile/ios/AICaddieDomain/DomainRoundProjection.swift`
- Modify: `mobile/ios/AICaddieDomain/DomainRoundReducer.swift`
- Modify: `mobile/ios/AICaddieDomain/DomainLedgerStore.swift`
- Modify: `mobile/ios/AICaddieDomain/RoundPayloadValidator.swift`
- Modify: `mobile/ios/AICaddieDomainTests/DomainLedgerStoreTests.swift`
- Modify: `mobile/ios/AICaddieDomainTests/DomainRoundReducerTests.swift`
- Modify: `mobile/ios/AICaddieDomainTests/RoundProjectionContractTests.swift`
- Create: `mobile/ios/AICaddieDomainTests/Fixtures/round_trace_autoshot_automatic.json`
- Modify: `mobile/ios/AICaddieDomainTests/RoundPayloadValidatorTests.swift`
- Modify: `mobile/ios/AICaddieDomainTests/ResolutionCommitTests.swift`
- Create: `mobile/ios/AICaddieDomainTests/AutoShotEvidenceTests.swift`
- Create: `mobile/ios/AICaddieDomainTests/AutoShotControlTests.swift`
- Create: `mobile/ios/AICaddieDomainTests/AutoShotCandidateTests.swift`
- Create: `mobile/ios/AICaddieDomainTests/AutoShotAutomaticPromotionTests.swift`
- Create: `mobile/ios/AICaddieWatchTests/WatchMotionShotProducerTests.swift`
- Create: `mobile/ios/AICaddieWatchTests/WatchAutoShotEvidenceHarnessTests.swift`
- Create: `mobile/ios/AICaddieWatchTests/WatchAutoShotCandidateFlowTests.swift`
- Create: `mobile/ios/AICaddieWatchTests/WatchAutoShotLiePickerTests.swift`
- Create: `mobile/ios/AICaddieWatchTests/WatchAutoShotAutomaticFlowTests.swift`
- Modify: `mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift`
- Create conditionally after Step 8 evidence approval: `mobile/ios/AICaddieWatch/AICaddieWatch.entitlements`
- Modify conditionally after Step 8 evidence approval: `mobile/ios/AICaddieWatch/Info.plist`
- Modify conditionally after Step 8 evidence approval: `mobile/ios/project.yml`

- [ ] **Step 0: Execute and sign the Tracker-qualified real-device evidence closure**

`autoshot_evidence_plan.json` is an exact, checked-in matrix rather than a prose promise. It binds `planVersion,buildCommit,imageDigest,deviceModel,osBuild,sampleRateHz,profileHash,wristSide,clubClass,startLie,roundScenario,lifecycleScenario,durationSeconds,rawPersistencePolicy,uploadPolicy,expectedArtifacts`. It must cover supported 41/46 mm hardware profiles、Tee/fairway/rough/bunker/fringe full shots、Green/putting negatives、walking/cart false-positive negatives、AOD/wrist-down/background/foreground、notification/call interruption、score/Club-Prompt preemption、strong kill/restart、location and Motion permission denial、Workout denied/started/preempted by another Workout/recovered、network absent and one continuous five-hour Motion+GPS run. Simulator-only rows cannot close a device profile.

`WatchAutoShotEvidenceRecorder` writes only bounded local aggregate counters、`MotionFeatureSummary`、labeled decision timestamps、battery/thermal samples and lifecycle transitions under an explicit Beta evidence session. It never stores raw high-frequency samples for the full round and has no network client. Any optional short labeled window is memory-only by default, requires separate test-session opt-in, is erased after local feature extraction and is absent from the production profile. `run_watch_autoshot_evidence.sh` uses an explicitly named physical Watch destination and build identity, runs the native harness, records Energy Log/signposts and copies artifacts only to the developer-selected local output directory；it contains no upload command、cloud URL or telemetry credential.

The exact execution is:

```bash
bash ops/run_watch_autoshot_evidence.sh \
  --plan mobile/ios/evidence/autoshot_evidence_plan.json \
  --device-profile "$AUTOSHOT_DEVICE_PROFILE" \
  --destination "$AUTOSHOT_WATCH_DESTINATION" \
  --duration-hours 5 \
  --output "$AUTOSHOT_LOCAL_EVIDENCE_DIR"
python3 ops/build_autoshot_evidence_closure.py \
  --plan mobile/ios/evidence/autoshot_evidence_plan.json \
  --artifacts "$AUTOSHOT_LOCAL_EVIDENCE_DIR" \
  --output mobile/ios/evidence/autoshot_evidence_closure.envelope.json
python3 ops/validate_autoshot_evidence.py \
  --closure mobile/ios/evidence/autoshot_evidence_closure.envelope.json \
  --trust-store mobile/ios/evidence/autoshot_trust_store.json \
  --requested-mode candidate
```

The signed closure envelope has exact root keys `{schema,closureId,planHash,buildIdentity,deviceProfile,privacyClosure,platformClosure,lifecycleResults,accuracyResults,batteryResults,artifactHashes,disposition,reasonCodes,signedAt,keyId,signature}` and strict nested keys. `privacyClosure` records `independentOptIn=true,defaultUpload=false,wholeRoundRawPersistence=false,compressedWindowUploadNecessary=false|true,withdrawalAndDeletionVerified=true,d12bDisposition`; `platformClosure` records whether Workout is required、whether it runs without Health save、whether `CLBackgroundActivitySession` is sufficient、whether Health write was requested、and permission-denial behavior. Lifecycle/accuracy/battery rows name every matrix case and exact local artifact hash；missing、duplicate、wrong-build or simulator substitutions fail.

Closure routing is deterministic:

- if compressed upload is not proven necessary, `d12bDisposition=closed_local_only` and `disposition=candidate_evidence_eligible|automatic_evidence_eligible`; this is the normal legal closure and D15 remains completely local;
- if upload is proven necessary, `disposition=owner_reopen_required` and execution stops at Tracker D12b before any research-upload code or consent UI is added;
- if Workout can run without Health save and denial leaves map/score/manual-shot intact, the closure may proceed with `healthSave=false`; if evidence leaves both optional Health save and no-save as real product choices, or saving is unavoidable, `owner_reopen_required` routes exactly Tracker D13b；Plan 4 never silently chooses or writes Health;
- a missing five-hour run、AOD/background/preemption recovery failure、permission denial breaking core play、unbounded raw persistence or unsupported device yields `blocked_platform`, leaving AutoShot Shadow/Disabled while the D14 manual path remains production-eligible.

`test_autoshot_evidence_closure.py` and `WatchAutoShotEvidenceHarnessTests` reject a forged disposition、missing matrix case、upload despite `closed_local_only`、Health write without the conditional Owner decision、raw retention、wrong build/profile and an artifact hash mismatch. Step 1 may consume only a verified `candidate_evidence_eligible|automatic_evidence_eligible` closure for the exact runtime profile.

- [ ] **Step 1: Write failing signed-evidence, privacy and lifecycle gates**

Evidence tests first require Step 0's signed closure ID/plan hash/build/profile and `closed_local_only` or an already answered conditional Owner decision. They then require exact signed device profile identity `deviceModel,osBuild,sampleRateHz,profileHash`, labeled-shot/round/player counts, false positives per 18-hole equivalent, false-negative rate, wrong-hole/duplicate/ownership-bypass counts, p95 detection-to-durable latency, five-hour incremental battery drain, automatic-undo rate, threshold set and evidence refs. Unknown profile, signature/key failure, expired evidence, runtime mismatch or threshold/range failure blocks every mode above shadow.

Control tests require a signature-verified monotonic generation with exact `shadow|candidate|automatic|disabled` mode and the approved evidence-envelope hash. Same-generation collision, rollback, stale cached allow, evidence/control hash disagreement or later downgrade/disable fails closed. A device may apply and durably retain a local **downward-only** safety override `automatic → candidate → disabled`; only a newer valid signed control/evidence pair may clear it, and no local metric may self-promote a mode.

Lifecycle tests require:

- detected/rejected/superseded candidates write zero canonical events/statistics/calibration;
- one explicit confirmation writes exactly one event using the active preallocated shot ID and `autoshot_confirmed` provenance;
- one Automatic-eligible ordinary observation writes exactly one event using the active preallocated shot ID and `autoshot_automatic` provenance, never presents “算一杆”, and queues Club Prompt only after the ledger transaction succeeds;
- Green/putting observations never create a candidate or automatic full-shot event；automatic append requires one impact-time verified `tee|fairway|rough|bunker|fringe|other` start lie, while an unavailable/ambiguous lie falls back to Candidate rather than guessing;
- a Candidate with a verified start lie remains one-tap “算一杆”; an unknown-lie Candidate writes no canonical event or stage when tapped and first enters the exact six-choice lie picker;
- only an explicit `tee|fairway|rough|bunker|fringe|other` picker choice may resolve an unknown Candidate, is durable across restart and is bound into the outbox/event bytes；dismissal/back never defaults to `other`;
- Automatic rejects a null verified lie even if a stale player-selected lie exists, and mutation/replay tests reject changing `verifiedStartLie`、`resolvedStartLie` or `lieSource` under the same candidate/outbox identity;
- raw high-frequency Motion samples are reduced in memory to `MotionFeatureSummary`, never persisted or uploaded by default;
- journal preparation before ledger、ledger commit before journal terminal mark and ledger/outbox before ACK crashes all recover exactly once; there is no pre-ledger standalone claim state;
- manual shot versus active AutoShot claim has deterministic exclusion/conflict behavior;
- prior-round/incarnation candidate/outbox entries never appear in the current partition;
- an episode-free candidate freezes impact-time `scoreSlot/orderedHoleCursor/holeSubjectRef`; confirming it after the UI has advanced never uses the then-current hole;
- an episode-free ordinary confirmation is accepted only when `resolutionEpisodeId == nil` and `ownershipHint == nil`, no unresolved episode owns the candidate's impact scope, and the active `shotId` is not `.resolutionReserved`;
- D15 Beta admits at most one episode-free pending candidate per active partition because that candidate owns the still-active preallocated shot slot；a second impact before decision is retained only as a local aggregate blocked-candidate metric and cannot mint another candidate、claim or shot event;
- Automatic high-confidence ordinary appends rotate the slot immediately and therefore may record later distinct impacts without waiting for a candidate decision；D14a Tee last-wins and near-station reconciliation still determine which effective shots survive, canceling any prompt/actual-club child that belongs to a superseded Tee attempt;
- either non-null ownership field, an owning unresolved episode or a reserved shot ID makes the ordinary confirmation API fail closed and permits only the `resolution_shot_staged` saga;
- score overlay preempts candidate UI and visible-time timers;
- an episode-free pending candidate reaches Hole Root as exactly one Watch overlay with “算一杆”/“误报” actions, one haptic per presentation revision and no guessed club;
- Crown/back/“稍后” and visible-time expiry write no candidate decision or canonical event, persist a collapsed `待确认一杆` affordance, and never haptic again until the player explicitly reopens it;
- visible-time accrues only while the candidate summary is top priority、Watch is active/visible and the display is awake；lie picker/submitting、score confirmation、older Club Prompt、wrist-down、background and restart pause it exactly;
- 41/46 mm snapshots and accessibility tests cover pending、collapsed、confirming、rejected、score-preempted and Club-Prompt-preempted states;
- candidate detected during one D14b episode keeps `resolutionEpisodeId`/impact location and, only after the signed evidence threshold **and a resolved start lie**, emits one operational `resolution_shot_staged`; it does not become a score/statistics shot or choose previous/next hole yet;
- an episode-attached unknown-lie Candidate disables Quick until the highest-priority score flow either marks it “误报” or obtains the same explicit lie choice and stages it；there is no second competing AutoShot overlay;
- D14b Quick may map only an all-`verified_next` staged roster to next, Manual may map this staged AutoShot previous or next per row, and Cancel maps the target roster to previous inside the same `ResolutionCommit`; this score-resolution action is the explicit confirmation and final provenance is `autoshot_confirmed`;
- terminal history is bounded per partition while every pending entry is preserved.

Add exact lie regressions `testVerifiedLieCandidateConfirmsInOneTap`, `testUnknownLieConfirmOpensPickerAndWritesNoOutboxStageOrShot`, `testExplicitLieSelectionBindsOutboxAndCanonicalBytesAcrossRestart`, `testBackDismissAndCrashNeverDefaultUnknownLieToOther`, `testAutomaticRequiresVerifiedLieAndRejectsPlayerSelectedSubstitute`, `testCandidateIdentityRejectsVerifiedLieMutation`, `testEpisodeUnknownLieBlocksQuickUntilSelectedOrRejected`, and `testLiePickerHasAllAndOnlySixTapOptionsAt41And46Millimeters`.

- [ ] **Step 2: Verify evidence before constructing policy**

```swift
public struct VerifiedAutoShotRuntimePolicy: Sendable {
    public let mode: AutoShotDetectionMode
    public let profileIdentityHash: String
    public let controlGeneration: UInt64
    public let thresholds: AutoShotThresholds
}
```

There is no Boolean `approvedForCandidateBeta`、`approvedForAutomatic` or `killSwitchEnabled` initializer. The production factory verifies Step 0's closure envelope, the signed profile evidence against the trust store, exact runtime device/OS/sample/profile identity, latest signed control and any persisted downward-only override. Shadow mode may collect aggregate local counters but cannot present confirmation or write ledger. Candidate mode may present only after its evidence gate passes. Automatic mode first evaluates the stricter promotion gate for each observation；eligible ordinary observations may enter Step 6's atomic path, while below-threshold confidence、unknown lie/location、pending-slot or ownership ambiguity falls back to the same Candidate surface without changing the signed mode. Unsupported/expired policy and any invariant breach fail closed, never to automatic.

- [ ] **Step 3: Use the partitioned candidate journal**

D14a's `ShotObservationJournal` stores exact:

```swift
public enum CandidateJournalDecision: String, Codable, Sendable {
    case pending
    case confirmed
    case automaticRecorded
    case rejectedFalsePositive
    case superseded
    case roundInactive
    case conflict
}

public enum CandidatePresentationDisposition: String, Codable, Sendable {
    case notPresented
    case queued
    case visible
    case collapsed
}

public enum CandidateConfirmationStep: String, Codable, Sendable {
    case summary
    case liePicker = "lie_picker"
    case submitting
}

public struct MotionFeatureSummary: Codable, Equatable, Sendable {
    public let peakRotationRate: Double
    public let peakAcceleration: Double
    public let durationMilliseconds: Double
}

public struct ImpactLocationFix: Codable, Equatable, Sendable {
    public let monotonicSeconds: Double
    public let latitude: Double
    public let longitude: Double
    public let horizontalAccuracyM: Double
}

public struct MotionImpactObservation: Codable, Equatable, Sendable {
    public let candidateId: String
    public let impactMonotonicSeconds: Double
    public let detectedAt: String
    public let featureSummary: MotionFeatureSummary
    public let locationFixHistory: [ImpactLocationFix]
}

public struct CandidateJournalEntry: Codable, Equatable, Sendable {
    public let partition: ShotJournalPartition
    public let candidateId: String
    public let shotId: String
    public let observation: MotionImpactObservation
    public let impactScoreSlot: Int
    public let impactOrderedHoleCursor: Int
    public let impactHoleSubjectRef: String
    public let verifiedStartLie: ShotStationLie?
    public let resolutionEpisodeId: String?
    public var ownershipHint: ProvisionalShotOwnershipHint?
    public var playerSelectedStartLie: ShotStationLie?
    public var presentationDisposition: CandidatePresentationDisposition
    public var confirmationStep: CandidateConfirmationStep
    public var visibleSecondsRemaining: Double
    public var presentationRevision: UInt64
    public var haptickedRevision: UInt64?
    public var decision: CandidateJournalDecision
    public var decidedAt: String?
}
```

Every `appendCandidate/pendingCandidate/decision/decideCandidate` call requires the active partition. Observation creation first proves there is no other episode-free pending candidate in that partition, reads and freezes the current active preallocated `shotId`, then resolves and freezes `impactScoreSlot/impactOrderedHoleCursor/impactHoleSubjectRef/verifiedStartLie` from the verified LRP/map classifier at impact time；all five values are immutable candidate-identity inputs and must agree on replay, and the later active slot/current-hole cursor/lie classification is never substituted. Optional fields are exact JSON keys with explicit null. Candidate/fallback observations initialize `playerSelectedStartLie=null` and exact UI state `queued,summary,10.0,revision=1,haptickedRevision=null`; an Automatic-eligible observation requires non-null `verifiedStartLie`, initializes `notPresented,summary,0.0,revision=0,haptickedRevision=null` and may become `automaticRecorded` only after Step 6's ledger success. UI-only disposition/step/timer/haptic changes are durable journal replacements but are never canonical round facts. A later impact while a candidate is pending increments only the signed-evidence aggregate `blockedByPendingCandidateCount`; it cannot allocate/reuse the active shot ID or silently replace the pending candidate. Startup never reads a global “last pending”.

For Candidate confirmation, a non-null `verifiedStartLie` requires `playerSelectedStartLie == nil` and resolves directly with `lieSource=verified`. When `verifiedStartLie == nil`, the first “算一杆” changes only `confirmationStep=lie_picker`; it does not set `decision`、prepare an outbox、stage or mutate the ledger. Tapping one exact `ShotStationLie` persists `playerSelectedStartLie`, then resolves with `lieSource=player_selected` and enters `submitting`. Back/restart returns to the durable pending picker/summary state, and there is no code path from nil to implicit `other`. A same-candidate mutation of the verified lie, a player-selected value when verified is already non-null, Green/water, or a resolved lie inconsistent with its source makes the journal entry corrupt/conflicted rather than silently repairing it.

The candidate journal and `DomainLedgerStore` are two durable files, so D15 does not pretend they share one transaction. For an episode-attached candidate, `stageForResolutionIfEligible` is a prepared saga only after start lie resolution: (1) read the current active shot slot, preallocate stable event ID and persist exact `CandidateStagePreparation{partition,candidateId,resolutionId,shotId,verifiedStartLie,playerSelectedStartLie,resolvedStartLie,lieSource,eventId,canonicalStageEventBytes,state=prepared}` in `ShotObservationJournal`, with every optional key explicitly present; (2) decode/revalidate those exact bytes and call D14b's `appendResolutionStageAndReserveNextAtomically`; (3) mark the preparation appended/terminal. A crash before step 2 leaves only a retryable preparation; a crash after ledger commit before step 3 retries the same bytes and receives idempotent success without another slot rotation. If another producer consumed the slot before step 2, the ledger changes nothing and the preparation becomes visible conflict/superseded—never a replacement event with a new ID. An episode-attached entry with unknown lie remains local and blocks Quick；the score flow embeds the same “算一杆/误报” plus lie picker, then stages or rejects before commit preparation. The eventual ResolutionCommit disposition remains the authority for previous/next ownership. A candidate is eligible for the separate ordinary explicit-confirmation path only when `resolutionEpisodeId == nil` **and** `ownershipHint == nil`; either field being non-null forces this stage saga and forbids ordinary `shot_recorded`. Episode-free candidates remain pending and noncanonical until that explicit confirmation writes `shot_recorded.hole=impactScoreSlot`.

- [ ] **Step 4: Persist a stable candidate-confirmed or automatic decision before ledger mutation**

`AutoShotCanonicalDecisionKind` is exact `confirmed_candidate|automatic`; `AutoShotLieSource` is exact `verified|player_selected`. `AutoShotDecisionOutbox` exact-keys `partition,candidateId,decisionKind,impactScoreSlot,impactOrderedHoleCursor,impactHoleSubjectRef,shotId,slotClaimOwner,verifiedStartLie,playerSelectedStartLie,resolvedStartLie,lieSource,resolutionEpisodeId,ownershipHint,transactionId,eventId,canonicalEventBytes,disposition`. Its strict custom `Codable` implementation requires every key and calls `encodeNil(forKey:)` for absent lie/ownership fields；synthesized `encodeIfPresent` omission is forbidden. An ordinary record therefore carries absent `verifiedStartLie` or `playerSelectedStartLie` and both ownership fields as explicit JSON null so migration/restart can prove the exact negative condition rather than silently dropping it. Candidate confirmation and Automatic share one flow:

1. require active partition、pending observation、`resolutionEpisodeId == nil` and `ownershipHint == nil`; `confirmed_candidate` additionally requires a durable player tap and, when needed, a durable explicit picker choice under Candidate/Automatic fallback, while `automatic` requires the exact current `VerifiedAutoShotRuntimePolicy.mode == automatic` and per-observation Step 6 eligibility;
2. resolve lie without guessing: verified Candidate uses non-null `verifiedStartLie` with `playerSelectedStartLie=null`; unknown-lie Candidate requires non-null explicit `playerSelectedStartLie`; Automatic requires non-null `verifiedStartLie` and forbids a player-selected substitute. Freeze `resolvedStartLie/lieSource` and reject every inconsistent combination before bytes;
3. resolve the frozen impact cursor through the verified LRP sequence and prove no nonterminal resolution episode owns that transition scope；if one exists, fail closed and route only to `stageForResolutionIfEligible`;
4. resolve the impact-time location through D14a's monotonic fix resolver;
5. run D14b `TransitionShotPreflight` before constructing ordinary bytes. `.resolutionRequired` and `.manualOwnershipRequired` both persist the shared `TransitionShotPreparation` with the same exact lie binding and execute open→stage with this candidate's same `shotId`；only `.ordinaryCurrentHole` continues;
6. read the active shot slot, require its `shotId` matches the observation and has no durable `.resolutionReserved`/`.commitConsumed` claim, then build the event through Track A's shared `ManualShotProducer.recordAutoShotDecision(...)` entry point using the frozen impact score slot、`resolvedStartLie` and exact decision kind, never a parallel event body；the builder maps only `confirmed_candidate → autoshot_confirmed` and `automatic → autoshot_automatic`;
7. durably persist the exact outbox tuple/bytes before ledger mutation;
8. call `appendAutoShotDecisionAndReserveNextAtomically(...)`, which in one ledger transaction rechecks decision-kind policy/evidence、the exact lie-source matrix、both null ownership fields、the absence of an owning unresolved episode、the non-resolution-owned active slot、a still-ordinary preflight result and exact frozen score-slot/subject binding, creates or idempotently matches the ordinary permanent claim, appends the event/outbox/projection row, completes the slot and reserves the next UUID;
9. mark candidate/outbox terminal only after ledger success.

Restart reuses exact IDs/bytes. There is no standalone claim state and no claim release path: a crash before the ledger transaction has no claim, while a crash after it is recovered by exact idempotent retry. An active slot paired with a different observation/outbox or a changed lie tuple fails hard without mutating either. A stale legacy manual event cannot silently steal a valid claim. Tests inject a fault before/after lie selection、transition preparation/open/stage、ordinary decision preparation、ledger commit、journal terminal marking and ACK for both decision kinds. Any observation whose shot origin itself qualifies the ordered-next-Tee transition must therefore stage under one canonical episode even if detector dwell/open races it；it can never fall through to an ordinary previous-hole event.

D15 explicitly supersedes Track A Task 13a's temporary **provenance-only** blanket guard while preserving every transaction/ancestry/claim guard. `shot_recorded` remains registry class `ordinary_or_resolution_commit`. Python `validate_event_payload(...)` and Swift `RoundPayloadValidator` therefore allow exact provenance `autoshot_confirmed|autoshot_automatic` with `transactionRef == nil` at the stateless schema layer; `RoundEventTransportClass.classify`/old-storage migration classify such an event as `.ordinaryEvent`, and classify it as `.resolutionCommitFinal` only when the exact transaction ref is present. Local generic `DomainLedgerStore.append(_:)` still rejects producer-built AutoShot provenance, so local creation must use the atomic API above；verified peer import may consume the resulting ordinary row through the shared batch boundary.

This is also an explicit reviewed extension of Plan 1's strict projection contract, not merely an event-schema enum edit. `ai_caddie/rounds/projection_contract.py` remains the sole schema source owner and expands `shots[].provenance` exactly from `manual|autoshot_confirmed|imported` to `manual|autoshot_confirmed|autoshot_automatic|imported`; regeneration updates `round_projection_v2.schema.json` and the Python/Swift/TypeScript validators. `round_trace_autoshot_automatic.json` and its native/Web byte-identical copies prove one episode-free ordinary automatic event reduces to a strict `RoundProjectionV2` shot with the same provenance and survives encode/decode/hash conformance. Tests still reject `autoshot_candidate`、`autoshot_observed` or any unknown projection provenance. Episode-attached observations remain `autoshot_observed` operational stages and, because D14b's score action explicitly confirms ownership, their final committed shot remains `autoshot_confirmed`；`autoshot_automatic` is never legal as a shortcut around a ResolutionCommit.

The new root trace is already matched by Plan 1's `contracts/canonical/**/*.json` source pattern, and Plan 1's single generator already byte-copies every `round_trace_*.json` into Swift/Web fixture roots. D15 therefore does not create another copier or generated group. It modifies the one existing `canonical-contracts` group only by appending the two newly discovered copy outputs below；the notation is plan-only, so implementation merges the array values into the real `outputs` array and never writes an `appendOutputs` key:

```json
{
  "name": "canonical-contracts",
  "appendOutputs": [
    "mobile/ios/AICaddieDomainTests/Fixtures/round_trace_autoshot_automatic.json",
    "web_v2/src/contracts/fixtures/round_trace_autoshot_automatic.json"
  ]
}
```

`tests/test_contract_codegen.py` must prove there is still exactly one `canonical-contracts` group, neither copy has a second owner, source/output sets contain no duplicates or overlap, `generate_all()` returns both copies byte-identical to the root trace, and the complete final generated output key set equals the group's generator-owned outputs. A root trace diff without these copies, either copy diff without its root source, or a hand-written copy is a failure.

The stateful Swift atomic producer decides local legality from both durable observation/outbox proof and ledger state: it rejects a decision-kind/provenance mismatch、a mutated or impossible verified/player-selected/resolved lie tuple、Automatic without a verified lie、unverified automatic policy、non-null ownership fields、an owning unresolved episode、a `.resolutionReserved|.commitConsumed` shot、resolution-owned ancestry or a same-batch stage. The Python/server ingest boundary cannot see private candidate-journal fields, so it independently revalidates every wire-observable invariant under the round/claim/scope locks: exact allowed non-Green start lie in event bytes、provenance enum、transaction class、reserved/consumed shot claims、resolution-owned cause/ancestry and same-batch staged IDs. Python `_requires_resolution_commit_in_session(...)` no longer returns true solely because provenance is `autoshot_confirmed|autoshot_automatic`; it still returns true for any `transactionRef`、commit-only kind、reserved shot or resolution-owned descendant. The ordinary `/events` endpoint therefore accepts only an otherwise-valid unreserved event, while the commit endpoint remains the sole path for staged AutoShot. Source-boundary and server tests prove removing the blanket check does not create a generic local or remote bypass.

- [ ] **Step 5: Build the concrete Watch candidate confirmation and respect score ownership**

`WatchAutoShotCoordinator` reads only the active journal partition and feeds the shared `WatchRoundContainerView` interaction arbiter. D15 deliberately has one mutable fallback-candidate surface: **Watch only**, because the candidate depends on Watch motion evidence and a Watch-local active shot slot. iPhone receives the canonical shot after explicit or automatic append and can use ordinary history editing, but it does not mirror、take over or decide a noncanonical pending candidate in this version. This explicit boundary avoids a second private peer wire/shot-slot truth；a later iPhone takeover requires its own reviewed contract.

An episode-free candidate becomes visible only from Hole Root as `WatchAutoShotCandidateView`, never as another permanent swipe page. Exact copy and actions are:

```text
检测到一杆
2号洞 · 发球台
[算一杆]  [误报]
稍后
```

```swift
struct WatchAutoShotCandidatePresentation: Equatable {
    let candidateId: String
    let holeLabel: String
    let verifiedLieLabel: String?
    let confirmationStep: CandidateConfirmationStep
    let isSubmitting: Bool
}

struct WatchAutoShotCandidateView: View {
    let presentation: WatchAutoShotCandidatePresentation
    let confirm: () -> Void
    let reject: () -> Void
    let deferDecision: () -> Void

    var body: some View {
        VStack(spacing: 6) {
            Text("检测到一杆").font(.headline)
            Text([presentation.holeLabel, presentation.verifiedLieLabel]
                .compactMap { $0 }.joined(separator: " · "))
                .font(.caption)
            HStack {
                Button("算一杆", action: confirm)
                    .disabled(presentation.isSubmitting)
                Button("误报", action: reject)
                    .disabled(presentation.isSubmitting)
            }
            Button("稍后", action: deferDecision)
                .buttonStyle(.plain)
                .disabled(presentation.isSubmitting)
        }
        .accessibilityElement(children: .contain)
    }
}
```

Unknown lie routes to one additional, non-defaulting screen rather than writing `lie=other`:

```swift
struct WatchAutoShotLiePickerView: View {
    let choose: (ShotStationLie) -> Void
    let back: () -> Void
    let isSubmitting: Bool

    private let options: [(ShotStationLie, String)] = [
        (.tee, "发球台"),
        (.fairway, "球道"),
        (.rough, "长草"),
        (.bunker, "沙坑"),
        (.fringe, "果岭边"),
        (.other, "其他"),
    ]

    var body: some View {
        ScrollView {
            VStack(spacing: 6) {
                Text("这杆从哪里打？").font(.headline)
                LazyVGrid(
                    columns: [GridItem(.flexible()), GridItem(.flexible())],
                    spacing: 6
                ) {
                    ForEach(Array(options.enumerated()), id: \.offset) { pair in
                        Button(pair.element.1) { choose(pair.element.0) }
                            .disabled(isSubmitting)
                    }
                }
                Button("返回", action: back)
                    .buttonStyle(.plain)
                    .disabled(isSubmitting)
            }
        }
        .accessibilityElement(children: .contain)
    }
}
```

The second Candidate line substitutes the frozen player-facing hole label and localized verified start lie；if lie classification is unavailable it shows only the hole label rather than raw IDs. The view never guesses or preselects a club. With verified lie, “算一杆” invokes Step 4 immediately and disables repeat taps while durable preparation is in flight. With unknown lie, it durably changes only to `lie_picker`; one of the six explicit taps becomes the confirmation and starts Step 4, while “返回” restores the still-pending summary with the same remaining visible budget. Entering the picker persists and pauses that budget, so it cannot expire while the player is choosing；restart restores the picker without a second haptic. There is no Green/water option and “其他” is a real player tap, never a fallback. After canonical ledger success the coordinator queues the normal Club Prompt for the same shot ID. “误报” durably sets `rejectedFalsePositive` and writes zero canonical event. “稍后”、Crown/back dismissal and expiry of the exact `10.0 s` summary visible-time budget set only `presentationDisposition=collapsed`; they do **not** confirm、reject、supersede or mutate a shot slot. Hole Root then shows one compact `待确认一杆` affordance; tapping it increments `presentationRevision`, restores the remaining budget to `10.0 s` only after an explicit reopen and permits exactly one new haptic for that revision.

Priority is exact: D14b score confirmation/manual-score step → an older canonical Club Prompt → AutoShot candidate → D14a recovery card → Caddie/Map instruments. `WatchAutoShotCoordinator` reuses D14a's already tested `ClubPromptVisibleCountdown` clock semantics with a candidate-specific durable snapshot；it does not implement a second wall-clock timer. The timer accrues only while this candidate is the arbiter's top visible overlay、`confirmationStep=summary`、scene phase is active、display is awake and wrist state is visible. Lie picker/submitting、every preemption、wrist-down、background or process exit first persists the remaining budget and pauses it. Becoming top-level emits one `.notification` haptic only when `haptickedRevision != presentationRevision`, then persists equality before playing the haptic so a crash cannot repeat it. Restart restores queued/visible/collapsed state、confirmation step and remaining time; it never turns timeout/dismiss into a decision.

While a D14b episode is unresolved, Watch may persist/stage impact candidates but score confirmation remains the only visible overlay. A resolved-lie candidate stages normally. An unknown-lie candidate appears inside that score flow as one blocking “检测到一杆” row with “算一杆”/“误报”；“算一杆” opens the same six-choice picker and only the selected lie permits staging, while “误报” terminalizes the local candidate with zero stage. Quick stays unavailable until the row is resolved, so the score commit cannot strand an unowned unknown-lie observation. The atomic resolution then creates each canonical shot with the explicitly resolved previous/next hole and same reserved shot ID；no second AutoShot prompt appears. Club Prompt is queued only after that commit and uses the same shot ID. If the player instead records a manual shot for the same observation before staging, the AutoShot candidate is superseded; if already staged, the resolution commit may choose only one source for that shot ID and must not create another shot fact. The episode-free Candidate/fallback path has at most one pending overlay by contract；the blocked-candidate metric is visible in rollout evidence. Automatic-eligible observations do not use this overlay or visible timer and proceed only through Step 6.

- [ ] **Step 6: Promote proven observations to S70-like automatic recording**

Automatic is a reviewed promotion, not an alias for Candidate. The validator freezes two evidence gates per exact device/OS/profile identity:

- Candidate gate: at least `300` labeled full-shot observations over `10` completed 18-hole-equivalent rounds, false positives `<= 0.50/round`, false-negative rate `<= 0.25`, p95 detection latency `<= 3000 ms`, five-hour incremental battery drain `<= 15.0` percentage points and zero wrong-hole、duplicate-canonical-shot or resolution-ownership-bypass findings;
- owner/internal Automatic canary gate: at least `1500` labeled full-shot observations over `50` completed 18-hole-equivalent rounds, false positives `<= 0.05/round`, false-negative rate `<= 0.12`, p95 detection-to-durable-append latency `<= 2000 ms`, five-hour incremental battery drain `<= 12.0` percentage points and the same exact-zero integrity findings;
- wider Automatic rollout requires a later signed generation backed by at least `1000` canary automatic decisions over `30` completed rounds, player correction/undo rate `<= 0.02`, false positives `<= 0.03/round`, no regression in the canary latency/battery gates and exact-zero integrity findings. The cohort/profile/evidence hashes are part of that generation；owner-canary evidence cannot silently authorize another hardware/OS profile.

`ops/validate_autoshot_evidence.py` recomputes those metrics from signed aggregate evidence and refuses an `automatic` control whose referenced envelope does not meet the target cohort gate. The numbers are rollout policy, not claims about evidence already collected；until a qualifying signed envelope exists, production stays Candidate/Shadow. Any threshold change requires a new reviewed authority/evidence generation, never an app constant edit hidden behind the same identity.

For each observation under verified Automatic mode, `WatchAutoShotCoordinator` evaluates one closed decision tree:

1. Green/putting、unresolved lie/location、below-Candidate confidence or an unsupported profile produces no canonical shot；eligible uncertainty falls back to Candidate and the rest stays shadow-only;
2. any D14b episode、next-Tee/manual-ownership preflight or reserved ancestry uses the existing prepared open/stage saga and waits for score ownership；it never ordinary-appends;
3. only verified allowed start lie + Automatic threshold + exact active slot + null ownership + `.ordinaryCurrentHole` enters Step 4 with `decisionKind=automatic` and provenance `autoshot_automatic`;
4. after the atomic ledger transaction and journal terminal mark, Watch emits the normal Club Prompt for that canonical shot ID. Choosing a club or Skip writes only `actual_club_set`; Cancel dismisses only the prompt. None of those actions retracts or conditions the already recorded shot/location;
5. multiple Tee impacts and near-station impacts are ordinary canonical observations handled by D14a's frozen Tee-last-wins/near-station reducer. A superseded Tee attempt loses its pending Club Prompt and is excluded from statistics/calibration；only the final effective Tee shot remains.

The current-hole recent-shot surface labels the provenance as localized “自动记录” and exposes “误报，撤销此杆”. Before a score episode owns the hole, that action calls D14a's canonical retraction path and writes one causal `shot_retracted`—never a destructive delete、slot reuse or private journal toggle；the canonical projection removes the shot and its actual-club contribution from statistics/calibration. If a score episode or completed score would become inconsistent, the action routes into D14b's existing resolution/deep-edit flow and cannot silently rewrite score facts. Candidate “误报” remains journal-only because no shot exists yet.

Rollback is downward-only and exact. One wrong-hole append、duplicate canonical shot、resolution-bypass or double slot rotation immediately persists local `disabled` and blocks further detection writes. After at least `100` automatic decisions in the rolling five-round device window, automatic correction rate `> 0.03`, false positives `> 0.10/round`, p95 durable latency `> 3000 ms`, incremental battery drain `> 15.0` points or two AutoShot recovery crashes downgrades locally to Candidate and queues aggregate evidence for the next signed control. A later signed downgrade always wins；recovery to Automatic requires a newer signed evidence/control generation and never occurs from local counters alone.

Add exact tests `testAutomaticEligibleOrdinaryShotAppendsWithoutCandidateUIThenQueuesClubPrompt`, `testClubPromptSkipOrCancelNeverRetractsAutomaticShot`, `testGreenUnknownLieAndBelowThresholdNeverAutomaticAppend`, `testNextTeeEpisodeAndReservedOwnershipAlwaysStageOrFallback`, `testAutomaticTeeLastWinsCancelsSupersededPromptAndKeepsFinalShot`, `testRecentShotUndoUsesCanonicalRetractionAndRecomputesStats`, `testScoreOwnedUndoRoutesToResolutionOrDeepEdit`, `testAutomaticCrashRecoveryIsExactlyOnce`, `testIntegrityViolationDisablesAndMetricRegressionDowngradesOnly`, and `testNoLocalCounterCanPromoteCandidateToAutomatic`.

- [ ] **Step 7: Run evidence, crash, privacy and canonical suites**

Run:

```bash
uv run python -m unittest tests.test_autoshot_evidence_gate tests.test_autoshot_evidence_closure tests.test_club_calibration -v
uv run python tools/contracts/generate_contracts.py
uv run python -m unittest tests.test_contract_codegen tests.test_round_projection_contract -v
uv run python -m unittest tests.test_round_event_ingest_v2 tests.test_resolution_commit_v2 tests.test_round_conformance_v2 tests.test_round_reducer_v2 -v
swift test --filter 'AutoShotEvidenceTests|AutoShotControlTests|AutoShotCandidateTests|AutoShotAutomaticPromotionTests|WatchMotionShotProducerTests|WatchAutoShotCandidateFlowTests|WatchAutoShotLiePickerTests|WatchAutoShotAutomaticFlowTests|WatchDesignSnapshotTests|ManualShotProducerTests|HoleScoreTransactionTests|HoleTransitionTimelineTests|RoundPayloadValidatorTests|DomainLedgerStoreTests|ResolutionCommitTests|ClubPromptRecoveryTests'
npm --prefix web_v2 test -- --run src/contracts/generated.test.ts src/contracts/projectionDecoder.test.ts
```

Expected: PASS; unsupported devices stay shadow/disabled, Candidate confirmation and Automatic ordinary append are each exactly once with distinct provenance, verified-lie Candidate is one tap, unknown-lie Candidate writes nothing until one explicit six-choice selection, picker restart/mutation/41/46 mm accessibility is deterministic and `other` is never a default, a next-Tee shot cannot race into the previous hole, either ownership field/reserved ancestry forces staging, D14b per-stage ownership wins, Green/putting and uncertain lies never auto-append, Club Prompt Cancel/Skip never retracts the shot, Tee last-wins cancels superseded prompts, canonical recent-shot undo recomputes statistics, rollback is downward-only, Watch candidate haptic/timer/dismiss/restart and priority states are deterministic, prior rounds never replay and unconfirmed candidates never enter calibration.

- [ ] **Step 8: Add entitlements only after evidence approval**

Only after the selected device profile evidence is approved, create `AICaddieWatch.entitlements` and modify the two existing metadata files with the minimum Motion/Workout capability and truthful permission strings. Before approval the entitlement file must remain absent, the existing files must remain byte-unchanged, and none of the three may be staged. Health saving remains absent unless separately approved. Run the native Watch suite and write exact build/evidence metadata.

- [ ] **Step 9: Commit AutoShot last**

```bash
git add \
  contracts/canonical/authority.json \
  contracts/canonical/round_event_v2.schema.json \
  ai_caddie/rounds/projection_contract.py \
  contracts/canonical/round_projection_v2.schema.json \
  contracts/canonical/fixtures/round_trace_autoshot_automatic.json \
  ai_caddie/contracts/generated.py \
  mobile/ios/AICaddieDomain/GeneratedContracts.swift \
  web_v2/src/contracts/generated.ts \
  tests/test_contract_codegen.py \
  tests/test_round_projection_contract.py \
  tests/test_round_conformance_v2.py \
  tests/test_round_reducer_v2.py \
  web_v2/src/contracts/generated.test.ts \
  web_v2/src/contracts/projectionDecoder.test.ts \
  web_v2/src/contracts/fixtures/round_trace_autoshot_automatic.json \
  ops/validate_autoshot_evidence.py \
  ops/run_watch_autoshot_evidence.sh \
  ops/build_autoshot_evidence_closure.py \
  tests/test_autoshot_evidence_gate.py \
  tests/test_autoshot_evidence_closure.py \
  mobile/ios/evidence/autoshot_evidence_plan.json \
  mobile/ios/evidence/autoshot_evidence_closure.envelope.json \
  mobile/ios/evidence/autoshot_device_profiles.envelope.json \
  mobile/ios/evidence/autoshot_trust_store.json \
  ai_caddie/rounds/ledger_models.py \
  ai_caddie/rounds/ledger_repo.py \
  ai_caddie/rounds/reducer_v2.py \
  server_v2/round_ledger_api.py \
  tests/test_round_event_ingest_v2.py \
  tests/test_resolution_commit_v2.py \
  mobile/ios/AICaddieDomain/ShotCapture/AutoShotEvidence.swift \
  mobile/ios/AICaddieDomain/ShotCapture/AutoShotControl.swift \
  mobile/ios/AICaddieDomain/ShotCapture/AutoShotCandidate.swift \
  mobile/ios/AICaddieDomain/ShotCapture/AutoShotDecisionOutbox.swift \
  mobile/ios/AICaddieDomain/ShotCapture/ShotCaptureSession.swift \
  mobile/ios/AICaddieDomain/ShotCapture/ManualShotProducer.swift \
  mobile/ios/AICaddieDomain/ShotCapture/ShotObservationJournal.swift \
  mobile/ios/AICaddieDomain/Scoring/PendingShotOwnershipJournal.swift \
  mobile/ios/AICaddieDomain/DomainRoundEvent.swift \
  mobile/ios/AICaddieDomain/DomainRoundProjection.swift \
  mobile/ios/AICaddieDomain/DomainRoundReducer.swift \
  mobile/ios/AICaddieDomain/DomainLedgerStore.swift \
  mobile/ios/AICaddieDomain/RoundPayloadValidator.swift \
  mobile/ios/AICaddieDomainTests/DomainLedgerStoreTests.swift \
  mobile/ios/AICaddieDomainTests/DomainRoundReducerTests.swift \
  mobile/ios/AICaddieDomainTests/RoundProjectionContractTests.swift \
  mobile/ios/AICaddieDomainTests/Fixtures/round_trace_autoshot_automatic.json \
  mobile/ios/AICaddieDomainTests/RoundPayloadValidatorTests.swift \
  mobile/ios/AICaddieDomainTests/ResolutionCommitTests.swift \
  mobile/ios/AICaddieDomainTests/AutoShotEvidenceTests.swift \
  mobile/ios/AICaddieDomainTests/AutoShotControlTests.swift \
  mobile/ios/AICaddieDomainTests/AutoShotCandidateTests.swift \
  mobile/ios/AICaddieDomainTests/AutoShotAutomaticPromotionTests.swift \
  mobile/ios/AICaddieWatch/Services/WatchMotionShotProducer.swift \
  mobile/ios/AICaddieWatch/Services/WatchAutoShotEvidenceRecorder.swift \
  mobile/ios/AICaddieWatch/Services/WatchAutoShotCoordinator.swift \
  mobile/ios/AICaddieWatch/Views/ShotCapture/WatchAutoShotCandidateView.swift \
  mobile/ios/AICaddieWatch/Views/ShotCapture/WatchAutoShotLiePickerView.swift \
  mobile/ios/AICaddieWatch/Views/WatchRoundContainerView.swift \
  mobile/ios/AICaddieWatchTests/WatchMotionShotProducerTests.swift \
  mobile/ios/AICaddieWatchTests/WatchAutoShotEvidenceHarnessTests.swift \
  mobile/ios/AICaddieWatchTests/WatchAutoShotCandidateFlowTests.swift \
  mobile/ios/AICaddieWatchTests/WatchAutoShotLiePickerTests.swift \
  mobile/ios/AICaddieWatchTests/WatchAutoShotAutomaticFlowTests.swift \
  mobile/ios/AICaddieWatchTests/WatchDesignSnapshotTests.swift
# Run this exact additional staging command only when Step 8 approved and changed the files:
git add mobile/ios/AICaddieWatch/AICaddieWatch.entitlements mobile/ios/AICaddieWatch/Info.plist mobile/ios/project.yml
git commit -m "feat: add evidence-gated automatic shot capture"
```

## Cross-track execution order and production gates

```text
Track A canonical contracts + ledger/outbox
  D02 final Guidance wire
    → D02a generated/source-boundary ownership
    → D02b pure role-aware static asset verification
    → D02c exact current-device pin + latest signed control

  D06 canonical sample admission
    → D07 2D dispersion
    → D07a durable lie-conditioned club/recovery models

  D08 deterministic planning primitives
    → D08a full-plan + optional server-audit contracts
    → D08b local/offline route-aware engine + LRP policy + device-local manual-request action
    → D08c real elevation provider + durable trust
    → D09 one Apple Guidance state model per process

  D14 manual shot
    → D14a canonical station reconciliation + Club Prompt
    → D14b score confirmation + scope-local evidence + one actionable flow per incarnation
    → D15 AutoShot last, after its Tracker-qualified Step 0 closure

Track B course authority
  signed static bundle + exact ACK/current-device pin/control → D02c/D08b
  map.geometry + map.transform + map.image                  → D10a/D12
  orderedHoles + LiveRoundPackageV2                         → D08b/D14b

Track D package extension
  pinned ShotRecoveryPolicy/v1 in the exact LRP             → D14a return-path reconciliation
  pinned HoleTransitionPolicy/v1 in exact roundPolicy       → D14b detector/checkpoint/preflight

Plan 3 research candidates → Plan 2 quality gate → signed promoted products
  playsLike.model + playsLike.elevation → D03/D08c
  hazardGuidance evidence-backed set    → D04/D08b
  greenSurface macro component          → D05/D12a
  guidance.playable-regions (optional)  → stochastic planner gate

Experience order
  D09 → D10 iOS root/detail → D10a exact map mechanics
      → D11 single-root Watch → D12 interactive instruments → D12a flag/PinPointer
      → D14b highest-priority score flow
  D13 Web stays governance/read-only
```

Allowed before all gates close:

- D00 backend quarantine and D01 facts-only zero states.
- Pure golden/math/topology/viewport tests that claim no runtime availability.
- UI unavailable/accepted-empty states and manual score/manual shot paths.
- Shadow-only AutoShot evaluation with zero canonical/statistics/calibration writes.

Forbidden before the corresponding gate:

- recommendation, aim line or dispersion without eligible live input and verified local authority;
- online audit token as an offline map/Caddie prerequisite;
- any probability、any `expectedStrokes` output、AVG on Hole Root/Web、AVG outside a fully gated stochastic full-Caddie combination, wind/air-density or fabricated default club;
- adjusted PlaysLike replacing raw front/middle/back, appearing without verified elevation/model authority, or surviving moving/off/tournament/unavailable as a stale number;
- fixed decorative ellipse, aim-centered landing ellipse, selected-actual-club fallback or raw internal IDs in UI;
- a manual-mode root with no “获取球童建议” path, a CTA that writes/proxies `actual_club_set`, a surface-owned mode store/action, a cross-process shared actor/store/request ID/result cache, or peer transfer of device-local manual request/result bytes;
- scalar map `pixelsPerMeter`, independent base-image/overlay zoom, missing ball/pin markers or cross-hole asset swaps;
- Driver ring outside Tee-shot context;
- five-page or three-page horizontal Watch product shell, a six-icon permanent root dock, or a long-press-only instrument entry without an explicit E01 reopen record;
- calling macro Green preview “Garmin Green Contours”, synthesizing putt contours or reading legacy `greenSlope`;
- automatic hole switching, finishing before final-hole score resolution, more than one actionable unresolved `ResolutionEpisode` in one round incarnation, parallel different-scope confirmation UI, or collapsing offline conflicts by arrival order；
- Candidate-mode `shot_recorded` before an explicit “算一杆”/lie choice or the owning D14b score-resolution decision；Automatic-mode `shot_recorded` without verified signed device evidence/control **and** non-null verified lie、exact location/slot、null ownership、no owning episode and `.ordinaryCurrentHole` preflight. An operational `resolution_shot_staged` may exist before ownership confirmation, but it is never a score/statistics/calibration shot fact.

Plan 1 owns `0003_round_ledger_v2`、`0004_round_merge_control` and `0005_round_resolution_commit`; Plan 2 then owns the single linear chain `0006_course_identity_layout` through `0011_device_course_authority`; Plan 3 owns no migration. Plan 4 owns exactly `0012_player_guidance_model` for D07a's immutable learned-model rows with `down_revision="0011_device_course_authority"`. All remaining Track D state reuses Track A's account-scoped durable stores. No task may renumber/edit `0003`–`0011` or add another Track D migration without a separately reviewed plan starting at `0013`.


## Plan-wide verification commands

Backend focused:

```bash
AI_CADDIE_DATA_MODE=fixture uv run python -m unittest \
  tests.test_track_d_safety_gates \
  tests.test_guidance_contract \
  tests.test_track_d_registry_merge \
  tests.test_contract_codegen \
  tests.test_guidance_source_boundaries \
  tests.test_guidance_capability_adapter \
  tests.test_guidance_map_asset_roles \
  tests.test_guidance_effective_control \
  tests.test_canonical_contract_ids \
  tests.test_guidance_playslike \
  tests.test_hazard_guidance \
  tests.test_green_surface_binding \
  tests.test_club_calibration \
  tests.test_club_dispersion \
  tests.test_caddie_guidance \
  tests.test_caddie_plan_contract \
  tests.test_live_current_position \
  tests.test_route_projection \
  tests.test_guidance_engine_bundle \
  tests.test_guidance_playable_regions \
  tests.test_stochastic_caddie_planner \
  tests.test_route_utility_planner \
  tests.test_guidance_first_leg_consistency \
  tests.test_guidance_elevation_provider \
  tests.test_guidance_manifest_trust \
  tests.test_shot_station_statistics \
  tests.test_autoshot_evidence_gate \
  tests.test_autoshot_evidence_closure \
  tests.test_active_play_cursor \
  tests.test_active_play_cursor_source_boundaries \
  tests.test_round_event_ingest_v2 \
  tests.test_resolution_commit_v2 \
  tests.test_round_projection_contract \
  tests.test_round_conformance_v2 \
  tests.test_round_reducer_v2 \
  tests.test_elevation \
  tests.test_course_prep_green_distances \
  tests.test_course_prep_hazard_geometry \
  tests.test_geometry_evidence \
  tests.test_decision_layer \
  tests.test_server_v2_caddie \
  tests.test_mobile_contracts \
  tests.test_round_ingest \
  tests.test_server_v2_mobile \
  tests.test_manual_club_bag \
  tests.test_effective_club_ladder -v
```

Expected: all listed modules PASS under fixture mode.

Backend full:

```bash
AI_CADDIE_DATA_MODE=fixture uv run python -m unittest discover -s tests -v
```

Expected: full Python suite PASS.

Web:

```bash
cd web_v2
npm test -- --run
npm run lint
npm run build
npm run test:e2e
```

Expected: Vitest, ESLint, TypeScript/Vite and Playwright all exit 0.

Shared Swift and native:

```bash
swift test
xcodegen generate --spec mobile/ios/project.yml --project-root .
xcodebuild test -project mobile/ios/AICaddieNative.xcodeproj -scheme AICaddie \
  -destination "platform=iOS Simulator,name=iPhone 16,OS=latest"
xcodebuild test -project mobile/ios/AICaddieNative.xcodeproj -scheme AICaddieWatch \
  -destination "platform=watchOS Simulator,name=Apple Watch Series 10 (46mm),OS=latest"
xcodebuild test -project mobile/ios/AICaddieNative.xcodeproj -scheme AICaddieUITests \
  -destination "platform=iOS Simulator,name=iPhone 16 Pro,OS=latest" \
  -only-testing:AICaddieUITests/RealFlowUITests/testOfflineFinalHoleFinishRelaunchDeepEditAndSyncNeverSplitsCommit
python3 ops/write_native_build_evidence.py
```

Expected: Swift package tests PASS; iOS、Watch and the Plan 2-owned production-installer final-hole UI E2E all report `** TEST SUCCEEDED **`; the full Watch scheme includes Plan 2's `WatchCourseColdStartUITests`, so Track D app-root changes cannot regress standalone install/start. The UI test still enters only through `UITestInstalledCourseFixtureLoader` with the signed primary `ios-v1` nine-hole fixture and real LRP/static-authority verification；Plan 4 adds no second loader or test seed. Native evidence index records the exact build environment.

## First production milestone boundary

The first production milestone is complete only when the following chain works without AutoShot:

```text
promoted real CourseSnapshot installed
→ exact current-device pin + local signed static authority
→ Watch/iOS facts-only single Hole Root and aligned ball/pin map
→ offline verified current-shot Guidance when eligible
→ manual mode exposes ready/requesting/retry/unavailable/available Caddie states on both roots；Watch completes the request with Phone absent and neither device syncs live request/result bytes
→ manual shot + Tee last-wins/“打厚了” reconciliation + Club Prompt
→ previous-hole quick/manual score confirmation
→ versioned conservative transition detector/checkpoint with cart、adjacent-fairway、backtrack and compact Green→Tee boundaries
→ ordered tentative shots use Quick only for an all-verified-next roster, Manual for explicit mixed previous/next ownership, and Cancel for whole-roster previous-hole recovery
→ next-Tee first shot may race detector/restart but can only become an unowned staged shot, never an ordinary previous-hole shot
→ final-hole score confirmation before finish
→ canonical active-play cursor advances only from sealed Quick/Manual ResolutionCommit, stays on Cancel, and ignores historical edits
→ strong-kill/restart recovery with one actionable unresolved confirmation per round incarnation; different-scope offline branches queue as read-only conflict/audit evidence and same-scope branches remain visible without parallel controls
→ offline finish and canonical sync
→ arbitrary-hole Watch/iOS deep correction without changing active hole
→ deterministic calibration/statistics recompute
```

Task D15 begins only after D14b completes this milestone and D15 Step 0 closes Tracker D12a/D12b/D13a/E05/E06/T030/T031 for the exact device profile；a conditional D12b/D13b Owner reopen must also be answered if and only if the closure emits `owner_reopen_required`. AutoShot failure、`closed_local_only` operation or lack of supported devices cannot regress the manual path.

## Execution handoff

Plan execution should use `superpowers:subagent-driven-development` task by task, with Track A/B/C gate checks repeated before every dependent task. Use `superpowers:verification-before-completion` before claiming any task, milestone or rollout complete.
