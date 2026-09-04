# Course Data Platform、Deep Mine 与三端统一设计

**日期：** 2026-07-18

**状态：** 主线权威设计候选，等待 Owner 书面复核

**范围：** 新球场发现与获取、Garmin-derived 数据研究、不可变课程快照、Web/iOS/Apple Watch 统一契约、离线安装与安全降级

## 摘要

- 风退出 v1 live guidance；`PlaysLike` 只使用核实高差。
- 新球场通过统一 Course Service 按需搜索、获取、构建和安装；Watch 不直接解析 Garmin raw。
- 所有原始资产进入不可变 CAS，Deep Mine 对冻结 corpus 提供“零静默丢失”的字节级闭包，而不虚称理解未来全部私有语义。
- 研究资产必须经过逐洞、逐 capability quality gate，才能晋升到不可变 `CourseSnapshot`。
- Web/iOS/Watch 共享 CourseSnapshot、RoundEvent、LiveFacts、Guidance 和 Capability contract；只允许呈现和平台生命周期不同。
- Watch 安装完整 9/18 洞包后可无手机、无网络完成整轮。
- Garmin-derived 操作先过逐项 rights matrix；被允许的个人数据默认每账户私有，协议保留未来 rights-cleared 中央目录能力。
- 第一生产里程碑是“真实新球场 → 完整快照 → Watch 离线整轮 → iOS 深改 → 确定性统计”，不是先穷尽神秘字段或 AutoShot。

## 1. 权威边界

本文件把过去分散在地图解析、Watch、iOS、Web、球童和数据研究中的结论合并成一套产品与工程架构。它不重写已经锁定的球局交互细节，而是规定这些交互所依赖的数据、契约、安装和跨端一致性如何成立。

以下 Owner 决定继续有效：

- 直接对标 Garmin S70 可观察的任务流、信息层级、状态切换和恢复行为，不逐像素复制，也不声称掌握 Garmin 私有算法。
- Watch 可独立搜索球场、选择 CourseLayout/Tee、下载真实球场包、开局并脱离 iPhone 完成整轮。
- v1 不显示成功率或伪精确概率；未经真实自校准，不显示虚构的 `AVG. STROKES`。
- v1 不接入风或空气密度；`PlaysLike` 只使用已核实的高差。
- 不做推杆级果岭等高线；果岭宏观坡向在完成独立 source/component/transform/consumer 验证后可以作为独立能力晋升，当前实现不自动视为已通过。
- iOS 负责深度修改；Web 维持备战、治理和只读复盘边界；Watch 完成场上核心闭环。
- AutoShot 研究可以并行，但不得阻塞手动记分、手动记一杆、恢复、离线结束与同步的最小可靠闭环。

开发协作中的 Telegram Owner Decision Pager 是独立基础设施，不属于本文件定义的高尔夫产品能力。

## 2. 为什么需要重做整体边界

当前仓库已经具备搜索、Garmin release、prodgeometry、Draco、DSKIMG、高差、topo、LRP、iOS 离线事件、Watch 同步等大量局部能力，但缺少一条统一供应链：

1. 当前 corpus 只覆盖有限球场，不能支持未来临时遇到的新球场。
2. 历史解析器会主动过滤或静默丢失未知字段、非 `POSITION` Draco 属性、富 geometry branch 和 DSKIMG 未处理区间。
3. 研究产物、静态球场数据、动态球局事实和球童推断之间边界不清。
4. Web、iOS、Watch 和后端维护了相互漂移的 DTO、事件和降级语义。
5. 静态资源仍常按 mutable `gid/hole/style` 命名，更新后可能错误复用旧资产。
6. Watch 的真实离线安装仍偏向当前洞和下一洞，不能证明无手机完成整轮。
7. 风已经违反 Owner 决定进入 LRP、决策引擎和部分 UI，说明文档与产品契约缺少执行门。

因此，本轮目标不是再增加一个解析器或页面，而是建立：

```text
上游发现与原始证据
→ 可重放的研究解析
→ 逐能力质量晋升
→ 不可变 CourseSnapshot
→ 三端统一安装和球局契约
→ 整轮冻结、离线运行、确定性同步
```

## 3. 已选择的总体方案

### 3.1 被否决的路线

#### 设备直接访问 Garmin 并解析

否决。它会把 Garmin 凭证、签名 URL、ZIP key、protobuf/Draco/DSKIMG 漂移、授权责任和质量检验复制到 Watch、iOS 和 Web。Watch 电量、存储和冷启动也无法承担服务端研究流水线。

#### 只写死为单机脚本和 mutable 文件目录

否决。它接近当前状态，无法可靠更新、回滚、重放历史 raw、处理多 worker、冻结 active round 或证明三端安装的是同一版本。

#### 后端唯一状态、全部客户端做薄壳

否决。它不能满足 Watch 独立冷启动和离线整轮，网络中断会破坏记分和恢复。

### 3.2 正式选择

建立三条并行但通过明确晋升门连接的轨道：

```text
Course Acquisition Service
  搜索、身份解析、原始获取、构建、发布、安装

Research / Deep Mine Lab
  无损 inventory、Unknown Registry、差分、假设验证

Canonical Runtime
  CourseSnapshot、RoundEvent、LiveFacts、Guidance、三端投影
```

Course Service 的协议、snapshot 格式和安装协议从第一天同时支持两种部署：

- 每账户或个人 homeserver 私有构建；
- 权利明确后的中央 catalog/CDN。

账户私有只是隔离方式，不构成缓存、解密、派生、长期保留或分发授权。每个 provider/source 必须先通过逐操作 rights matrix；`unknown` 或 `denied` 的操作 fail closed。只有明确允许的个人使用/研究操作才能在账户私有模式执行，并且绝不跨账户复用 Garmin-derived raw 或派生资产。未来 rights-cleared 共享只改变 grant/publish policy，不重写客户端。

## 4. 不可违反的架构不变量

1. 上游 provider ID 不是产品内部 CourseLayout 或 CourseSnapshot 身份。
2. 所有原始响应体按字节 SHA-256 保存，原件不可改写。
3. 所有解析输出必须能追溯到 raw hash、decoder build 和参数。
4. 未理解的数据可以长期存在，但不能静默消失；必须进入 Unknown Registry 或明确 opaque 状态。
5. Research artifact 永远不能被客户端直接消费；只有通过逐能力 quality gate 的规范化输出才能进入 CourseSnapshot。
6. `CourseSnapshot` 不可变、内容寻址；active round 始终 pin 精确 snapshot。
7. 三端共享事实和状态机语义，平台差异只存在于传感器、运输、后台生命周期和呈现。
8. 推荐杆、推荐目标和推荐路线永远不等于实际击球事实。
9. 传输 ACK/cursor 不是业务事件，不能污染 RoundEvent ledger。
10. 缺数据时诚实降级；不得生成假 par、假洞数、假 geometry、假等高线或假球童建议。
11. v1 Guidance 的输入中不存在风或空气密度。
12. 已安装球场和 active round 不因 homeserver、手机或云暂时不可达而停止工作。

## 5. 核心身份和数据对象

### 5.1 `ProviderCourseRef`

描述一次上游身份，例如：

```text
provider = garmin
providerEnvironment/catalogNamespace
region
providerCourseId = gid
```

唯一键至少是 `provider + providerEnvironment/catalogNamespace + region + providerCourseId`；不能假定 gid 跨 Garmin region/catalog 全局唯一。它只用于获取与 provenance，不作为产品球场身份。

### 5.2 `VenueIdentity`

表示现实世界中的球场场地。候选聚类可使用名称、经纬度、地址、电话、网站和 sibling 关系，但弱匹配不能自动发布。人工确认和合并历史必须保留。

### 5.3 `CourseLayout`

表示玩家实际打的有序洞组：

- 单个 18 洞 provider record；
- 单个 9 洞 provider record；
- 两个九洞 segment 组成 18 洞，例如 `A → C`。

`SegmentIdentity` 表示 Venue 内稳定的逻辑九洞或十八洞段；`ProviderSegmentBinding` 才把它绑定到某个 `ProviderCourseRef` 的完整或局部 hole roster。一个 provider 18 洞 record 在 release 证明确有连续、唯一的 18 个 physical holes 后，可以提供完整 18 洞 binding，也可以把 front/back 物理九洞分别绑定成两个可选 `SegmentIdentity`，供单九或有序两九 layout 使用；不能仅凭显示名称或数组前后各九自动假定现实分段。

`CourseLayoutIdentity` 是稳定的产品身份，由 VenueIdentity、Owner/可信目录确认的 `SegmentIdentity` 顺序和逻辑 hole identities 组成，不直接把 Garmin gid、release 或 local-hole 编进稳定 ID。

`LayoutRevision` 是不可变版本，通过逐洞 `ProviderBinding` 显式绑定某一组 `ProviderCourseRef + SourceRevision + provider/local-hole` 到 `SegmentIdentity + logical-hole`，并记录人工确认、迁移和 supersession。`layoutRevisionId` 由 §5.11 Typed ID Registry 对这份有序 provider mapping 生成；CourseSnapshot 总是引用精确 revision。

`TeeSelection` 是 layout revision 级对象，不等同于单个 provider tee ID。对于 `A → C` 等多 segment 组合，它显式保存每个 segment/local-hole 使用的 provider tee、normalized tee family、颜色/名称和 rating/slope provenance；`teeSelectionId` 由 §5.11 的 TeeSelection domain 对这份有序映射生成。

规则：

- 一个 Garmin `gid` 可能有 9 洞或 18 洞，不能写死。
- 搜索结果标注的洞数只作候选提示，release 实际洞序用于验证。
- 不能只根据 `A/B/C` 名称自动组合两个九洞。
- 九洞顺序会改变 logical layout identity，必须由可信 metadata 或用户明确选择；provider release 变化只产生新的 LayoutRevision，不自动创建新现实球场。
- Venue/segment/layout 的 merge、unmerge 和 alias 都是可逆的 append-only identity resolution records。误合并后不改写旧 stable ID 或历史 snapshot；发布更高 generation 的 supersession/alias，把未来选择指向纠正后的 identities，active/历史 round 继续引用原 revision 并可审计。
- 同一个 physical hole 在不同 layout 中可以有不同 `absolute/displayHole`，但静态资产主键始终绑定 provider/source/local-hole；display hole 永不进入物理资产 identity。
- 两个九洞的 tee 名称相同也不能自动视为同一 tee；rating/slope 合并必须使用已验证规则和来源，缺失时退化为 gross-only，不猜测 18 洞值。
- Canonical tee 保留 provider tee index、name、gender、slope、rating 和 source provenance；颜色只是 UI normalization，不能作为 provider tee identity。切换 `TeeSelection` 必须改变 tee origin、洞长、路线、障碍/果岭距离、Watch 地图依赖和全部 tee-dependent 派生缓存键。
- v1 round/install profile 只支持精确 9 或 18 洞。27/36 洞 venue 先暴露多个可选 9 洞 segment，用户选择单九或有序两九；更多 segment 属于未来范围，不能生成 Watch 无法完整安装的 layout。

### 5.4 `SourceObservation`、`SourceRevision` 与 `SourceHead`

`SourceObservation` 表示一次 endpoint/asset 获取结果，无论成功、部分、拒绝或失败都不可变归档。其 `outcome` 使用：`complete | transient_partial | rights_blocked | not_found | withdrawn_evidence | malformed | budget_exhausted`，并携带 HTTP/transport 证据；partial/denied observation 不是 Course revision。

`SourceRevision` 只表示由一组 `complete` observations 证明的、内部一致且可构建的 provider course record 版本。它冻结 provider release/date identifiers、完整 hole set、asset locators、raw hashes 和 coherence proof；lifecycle 仅使用 `candidate | accepted | quarantined | superseded`。

`SourceHead` 是 account + 完整 ProviderCourseRef + source branch scoped、单调前进的 channel，指向最后 accepted SourceRevision，并带 generation、observedAt、etag/release ordering、compare-and-swap token 和独立 `availabilityOverlay: available | temporarily_unavailable | rights_blocked | withdrawn`。availability 变化不改写或伪造 SourceRevision。

规则：

- `/releases` 与 `/date` 只可在能证明 gid、release/date lineage、hole set 和 asset revision 一致时合并；否则分别归档，不能构造 hybrid revision。
- `2xx` 但 body/roster/asset 不完整和 `204` 产生 `transient_partial` observation；timeout、`429` 和 `5xx` 同样产生可退避的 transient observation，并保留最后 accepted head。
- `401/403` 在一次受控凭证刷新后仍失败时产生 `rights_blocked` observation 并收紧 SourceHead overlay，不得伪装成 withdrawn，也不得从其他账户缓存补齐。
- 单次 `404/410` 只产生 `not_found` observation，不足以撤销 current head。只有 latest/release inventory 的独立重复观察共同证明目标已撤回时，才发布更高 generation 的 `availabilityOverlay=withdrawn`；最后 accepted SourceRevision 仍保留供历史审计/受 policy 允许的 pinned round 使用。
- 历史 `/date` 响应只建立显式 historical revision。它即使完整，也不得默认成为 current `SourceHead`；必须由 current release lineage 或人工 promotion 单独确认。
- 迟到缓存、旧 HTTP 响应或旧 manifest 可以进入 raw archive，但不能让 SourceHead generation 回退。
- partial、rights、withdrawn evidence 或 schema failure 更新 observation/overlay；只有完整 coherent candidate 才能进入 SourceRevision lifecycle，且不能覆盖最后 accepted revision。
- builder 的所有洞必须来自同一个 coherent SourceRevision，或来自 manifest 中显式声明、逐项验证的 composite revision；不能逐洞随意取“最新”。

### 5.5 `SourceManifest`

记录一次完整 source discovery：

- provider refs、release/date endpoint、观察时间；
- semantic locator（稳定 path 与影响内容选择的 allowlisted query），与 auth/signature/expiry query 分离；后者只作 secret class 短期 resolver state，不进 receipt；
- redirect chain、逐跳状态和 final semantic locator；任何签名 final URL 只保存脱敏结构/hash，不保存 credential query；
- HTTP status、media type、etag、last-modified，以及显式 header allowlist；`Authorization`、`Cookie`、`Set-Cookie`、CSRF 和 provider-specific credential headers 永不进入 receipt；
- raw body hash、父子关系、授权类别；
- expected/obtained/missing assets；
- schema fingerprint 和 parser selection result。

### 5.6 `CourseSnapshotContent`

纯静态、不可变、内容寻址，包含 layout revision、scorecard、tee、anchors、normalized geometry、hazards、elevation、可选 green surface、语义层资产和逐洞 capability/quality。平台 renderer/style 产物不进入 semantic snapshot hash。

`snapshotId` 由 §5.11 的 CourseSnapshotContent domain 对 canonical content manifest 生成。内容 manifest 不包含 owner、账户 grant、channel 名或可变 entitlement 状态。

### 5.7 `SnapshotGrant` 与 `CourseReleaseChannel`

`SnapshotGrant` 把 account/entitlement、合法来源、允许的设备 profile、安装/使用期限和撤销政策绑定到 snapshot content。`CourseReleaseChannel` 是账户或 rights-cleared catalog 的单调指针，引用 snapshot、install manifests、SafetyPolicy 和 generation。

授权改变只更新 grant/channel/policy，不改变内容 hash；相同 bytes 是否能物理去重由存储加密和 entitlement policy 决定，绝不能因为相同 SHA-256 自动授予跨账户读取。

Grant 和 channel 都必须签名，并声明 audience（account/device class）、issuedAt/expiresAt、keyId、rightsPolicyVersion 和 channel generation。客户端为每个 channel 持久化最高已接受 generation；签名仍合法但 generation 较低的旧 grant/manifest 一律拒绝，防止重放。

Grant 时间判断不能直接相信可手调的 Watch/iPhone wall clock。服务端下发 signed `TrustedTimeToken(serverTime, tokenGeneration, maxOfflineAge, offlineNotAfter)`；设备在 Keychain/受保护存储保存 token、lastEffectiveTime 和 boot/monotonic anchor。同一连续时钟区间使用 `serverTime + monotonicElapsed`，且 effective time 永不回退；重启后只接受未倒退、未超过 policy maxForwardSkew 的 wall-clock continuation，否则标记 `time_untrusted` 并要求刷新。大幅快进不能永久污染 signed anchor，取得更高 generation token 后按新可信时间恢复。首次无可信 token、token 超 maxOfflineAge 或重装后 anchor 丢失时，时间受限 grant 对**新安装/新开局** fail closed；已开始 round 仍只按签名的 `activeRoundContinuation` 处理。

### 5.8 `CourseInstallManifest`

从同一 CourseSnapshotContent 生成不同设备 profile：

- Watch：完整 9/18 洞、受控尺寸、离线优先；
- iOS：完整静态包和丰富交互资产；
- Web：同一 normalized snapshot identity，可按需安装高清呈现资产。

三个 manifest 的显示资产可以不同，但事实、洞序、capability、source identity 和 snapshot ID 必须一致。

Renderer/style-only 更新产生新的 installManifestId/channel generation，不改变 snapshotId。若显示资产烘焙了可交互 hazard、target 或其他语义，它必须声明 semantic layer dependencies；依赖改变时必须引用新 snapshot 或通过兼容性 gate，不能借“样式更新”静默换事实。

Manifest identity 和签名避免自引用：`manifestPayload` 不包含 `installManifestId` 或 signature；`payloadBytes = CanonicalJSON(manifestPayload)`；`idDigest = SHA-256(ASCII("course-install-manifest/v1\0") || payloadBytes)`；`installManifestId = lowercaseHex(idDigest)`。`protectedHeaderBytes = CanonicalJSON({type, version, keyId, algorithm})`，signature 覆盖 `ASCII("course-install-signature/v1\0") || protectedHeaderBytes || idDigest || payloadBytes`。Wire envelope 固定为 `protectedB64u + installManifestId + payloadB64u + signatureB64u`。客户端先由 trust store 验证 `keyId → allowed algorithm/type/version`，再对收到的 protected header 和 payload **原始 bytes**验 ID/签名后解析，并拒绝 parse 后重新 canonicalize 与原 bytes 不一致的对象；不得由 Swift/Python/TypeScript 各自重序列化后再决定身份，也不得接受未签名的 keyId/algorithm substitution。

wire envelope 与 `manifestPayload` 合起来至少包含：

- `installManifestId/profileId/snapshotId/layoutRevisionId/teeSelection compatibility`；
- 精确 ordered hole roster（9 或 18）及 absolute-hole → logical-hole → provider/local-hole/sourceRevision binding；
- versioned asset groups，每组声明 `required | optional`、capability、hole/layer subject、media type、hash、size、ordinal 和 dependencies；
- total required/optional bytes、minimum free-space、staging overhead 和 supported resume protocol；
- canonical commit marker、minimum client/schema、signature/grant/channel generation。

缺任一 required hole/asset group 时 manifest 不能进入 installed；optional group 缺失只按 capability contract 降级。

### 5.9 `LiveRoundPackage`

只保存本轮动态准备信息，并与以下不可变 `RoundSemanticBinding` 一起开始球局：

```text
snapshotId
courseLayoutIdentityId
layoutRevisionId
teeSelectionId
liveRoundPackageId
```

Watch/iOS/Web profile 的 install manifest 本来就不同，因此 `installManifestId` 不属于跨设备唯一的 round semantic identity。每台参与设备另持久化 `DeviceRoundInstallBinding(deviceId, profileId, installManifestId, snapshotId, verifiedAt)`；它必须证明本机 manifest 与 RoundSemanticBinding 的 snapshot/layout/tee compatibility 一致，但不会让另一设备被迫使用相同 profile。

LRP 本身包含：

- player/bag snapshot；
- round policy 和版本化 `GuidanceEngineBundle`；
- client/schema minimums；
- 可选个性化设置。

静态球场文件路径、provider 签名 URL、weather requirement 不得散落进 LRP。

LRP 是 round-scoped immutable config，不包含任何设备专属 ACK、cursor、ledger position 或 outbox 状态。每台消费设备单独取得 vector `DeviceSyncBootstrap`：

```text
roundId
consumerDeviceId / consumerEpoch
mergeControlGeneration / mergeResolutionId
streams[]:
  streamSubject:
    round_incarnation: roundIncarnationId
    merge_control: mergeControlId
  ledgerPartitionId / ledgerEpoch / streamId
  lastAckedLedgerPosition / replayCursor / checkpointHash
mergedCheckpointHash
```

未合并球局只有一个 round-incarnation stream；合并球局拥有 merge-control stream 加全部 active source incarnation streams。每个 cursor/ACK 只对自己的 `ledgerPartitionId` 有意义，`mergedCheckpointHash` 是 merge resolution + canonical source vector + reducerVersion 的 hash，不是伪造的全局序号。ledger compaction 或 cursor namespace 变化只替换对应 stream 的 `ledgerEpoch/streamId/ledgerPartitionId`，旧 cursor fail closed 并重新 bootstrap。更换设备、重装、stream compaction 或 cursor 前进不改变 LRP identity。

`GuidanceEngineBundle` 只包含 engine/version、玩家校准、输入特征版本和离线计算资源，不预塞缺少 input revision 的推荐输出。已经安装 snapshot 的设备即使没有服务端预制 LRP，也必须能本地生成最小 immutable basic-round config；缺 bag/calibration/policy 时只阻止 Guidance，不阻止 gross score 开局。

`liveRoundPackageId` 由 §5.11 的 LiveRoundPackage domain 对 canonical round config 生成。v1 开始球局后不允许替换或在同一 round adopt 新 player/bag/policy/engine bundle；配置变化只用于下一局，若必须立即采用则结束/新建 round。未来若支持同局更新，必须先冻结 append-only `round_config_adopted`、base config revision、并发冲突、pin 和 Guidance invalidation contract；初始 RoundSemanticBinding 永不改写。

### 5.10 `LiveFacts` 与 `Guidance`

`LiveFacts` 分成两层：高频 `EphemeralObservation`（原始 GPS sample、短时精度/运动窗口）和经过 reducer/promotion 的 durable facts（active play hole、成绩、击球位置、实际杆、旗位选择、人工修正）。Guidance 可以读取新鲜 observation，但审计、同步和统计只依赖已声明保留策略的 durable facts；不能把每个 GPS sample 永久冒充业务事件。

`Guidance` 是基于 `factsVersion + snapshotId + model/calibration version` 的可失效推断：推荐杆、目标、路线和理由。它必须包含有效期、门控状态、缺席原因和证据引用。

`baseEntityRevision` 不是裸整数，而是 typed `EntityRevisionToken(scopeId, reducerVersion, canonicalOrdinal, entityProjectionHash, contributingEventSetHash, provisionalFlag)`。canonicalOrdinal 只在同一 canonical entity stream 内单调；离线 projection 产生 `provisionalFlag=true` token，不能因为两端都显示“revision 6”就视为同一 base。

Revision equivalence 先解析显式 causation/contributing event identities，再比较 `scopeId + reducerVersion + entityProjectionHash + contributingEventSetHash`；`canonicalOrdinal/provisionalFlag` 只描述来源，不参与语义等价。因此离线先写 A、再基于 provisional A 写 correction B 时，服务器接受 A 后可把 B 的 base 映射到等价 canonical token，不产生假冲突。若 content/event-set hash 不同才保留并产生 conflict projection。`roundFactsVersion` 是 `snapshotId + reducerVersion + canonical single/vector ledger checkpoint + canonical durable projection` 的 hash。UI 或 producer 必须声明使用的是 round scope 还是 entity scope，不能用模糊递增整数跨设备比较。

每个 Guidance candidate 至少包含：

```text
guidanceId
candidateHash
inputHash
roundFactsVersion / entityRevisions
producer
engineBuild
executionLocation
selectionPolicyVersion
validUntil
invalidationReasons[]
output + rationale + evidenceRefs[]
```

本地和云端对同一 inputHash 可以产生不同 candidate，但不能用“最后到达”决定真相。`candidateHash` 按 §5.11 的 GuidanceCandidate registry 计算。版本化 GuidanceSelectionPolicy 先按 engine compatibility、capability、校准和有效期做 eligibility gate，再为合格候选产生完整 rank tuple（policy-defined engine rank、execution rank、calibration specificity、capability completeness、producer/build rank），最后以 candidateHash lexicographic order 作稳定终极 tie-break；arrival time 永不进入比较。任何 input revision 改变、SafetyPolicy 收紧或必需 fact 过期都会使旧 candidate 失效。对同一 candidate set 的所有到达排列，三端必须选择同一 candidate 或同一 unavailable reason。

### 5.11 Canonical Encoding 与 Typed ID Registry

所有内容寻址 ID、binding hash、eventHash、checkpointHash 和 signature input 共享 machine-readable `CanonicalObjectRegistry`，不能各模块口头约定“hash 一下 JSON”。每个 object kind 固定：domain tag、schema/canonicalization version、included/excluded fields、字段顺序无关规则、单位、null/unset、ID 编码和 golden bytes。

`CanonicalJSON v1` 采用 RFC 8785 JCS，并增加以下输入约束：

- UTF-8；key 唯一；key 和进入 canonical semantic object 的 string 必须是 Unicode NFC，否则 validation reject。provider 原始 spelling 另在 raw/provenance 保留。
- 禁止 NaN/Infinity 和 negative zero；JSON integer 只能在 JavaScript safe-integer 范围。需要 uint64/更大精确值的 ledger position、size 或 counter 使用无符号十进制 string，禁止 `+`、前导零和空字符串。
- 时间固定为 UTC `YYYY-MM-DDTHH:mm:ss.SSSZ`；UUID 使用 lowercase canonical text；binary 使用无 padding base64url；enum 大小写和 SI 单位由 schema 固定。
- absent、显式 null 和 registry 定义的 unset sentinel 是三种不同语义；canonicalizer 不补语言默认值，也不丢未知已签名字段。

Typed ID 的统一公式为 `lowercaseHex(SHA-256(ASCII(domainTag + "\0") || canonicalBytes))`。Registry 至少覆盖 `CourseLayoutIdentity/SegmentIdentity/LayoutRevision/TeeSelection/SourceObservation/SourceRevision/SourceManifest/BuildSecurityDomain/CourseSnapshotContent/CourseInstallManifest/InstallSecurityDomain/SnapshotGrant/CourseReleaseChannel/SafetyPolicy/PurgeDirective/TrustedTimeToken/LiveRoundPackage/RoundSemanticBinding/MergeControlId/LedgerPartitionId/EventIdentity/EntityRevisionToken/RoundEvent/RoundFactsVersion/GuidanceInput/GuidanceCandidate/MergedCheckpoint`；不同 domain 的相同 bytes 绝不能得到可互换的业务 ID。CourseInstallManifest 使用 §5.8 的额外 signature envelope。Python/Swift/TypeScript 必须从同一 registry/codegen 和 golden byte fixtures 生成/验证，禁止手写第二套 canonicalizer。

`SnapshotGrant`、`CourseReleaseChannel`、`SafetyPolicy`、`PurgeDirective` 和 `TrustedTimeToken` 统一使用 `SignedControlEnvelope`：protected canonical header 固定 `type/schemaVersion/keyId/algorithm`，payload 以对应 registry/domain 的原始 canonical bytes 传输，signature 覆盖 `type-specific signature domain + protectedHeaderBytes + typed payload digest + payloadBytes`。客户端先校验 trust-store 中 key/type/algorithm 绑定，再验原始 bytes、audience/subject 和 monotonic generation；未签名 header 替换、低 generation 重放或跨 type 复用签名一律拒绝。CourseInstallManifest 遵循同一 protected-header 原则，并使用 §5.8 的 manifest-specific ID/signature domain。

## 6. 新球场发现与获取状态机

```text
SEARCH
→ CANDIDATE_RESOLUTION
→ LAYOUT_CONFIRMATION
→ CATALOG_CHECK
   ├ accepted snapshot exists → REMOTE_READY
   └ absent/stale → BUILD_QUEUED
       → SOURCE_DISCOVERY
       → RAW_ARCHIVED
       → PARSING
       → QUALITY_GATE
           ├ pass at minimum capability → SNAPSHOT_BUILD → SNAPSHOT_PUBLISHED
           └ fail/quarantine → DEGRADED_OR_UNAVAILABLE
→ INSTALL_PROFILE_BUILD
→ PROFILE_READY
→ DOWNLOADING
→ VERIFYING
→ ATOMIC_INSTALL
→ INSTALLED
→ LIVE_PACKAGE_PREPARED
→ first durable play event → STARTED_PINNED
→ ACTIVE_OFFLINE
→ Lifecycle=finished + Replication=dirty/syncing
→ Replication=clean + durable checkpoint
→ release device operational pin
```

最后三步只是两轴 round state 与 pin 生命周期的组合投影，不定义 `FINISHED_PENDING_SYNC → SYNCED` 这种 canonical 单轴状态。

### 6.1 搜索结果语义

搜索结果必须显式返回：

- `ready`：请求 account/grant 下既存在可接受 snapshot，也存在兼容当前设备 profile 的已签名 install manifest；
- `buildable`：上游身份足够，但需首次构建；
- `metadata_only`：只保证已经通过 gate 的身份/metadata；scorecard 或 distance 是否可用分别报告，不能由状态名推断；
- `ambiguous_layout`：九洞组合或候选场地需确认；
- `unavailable`：无法取得满足最低 gate 的合法数据。

Watch 选择球场前必须知道是否需要联网构建，不得在开球后才发现包不存在。

响应不能把 semantic snapshot readiness 与 requested-profile readiness 压成一个模糊布尔值；至少并列返回 `snapshotState`、`requestedProfileState`、`profileId/minClient` 和各自 build job。snapshot 已存在但 Watch profile 尚未生成时，不得返回顶层 `ready`。

这些状态对请求 account/grant scoped：物理 CAS 或其他账户已有 snapshot 不等于当前账户 `ready`。返回值同时声明 `catalogScope/accountId/grantState/sourceHeadGeneration/buildJobId`；权限未知时不能用共享缓存存在性泄漏资产或绕过私有构建。

`CATALOG_CHECK`、`ready/building`、build polling 和错误详情都按 `BuildSecurityDomain` 授权后投影。A 账户的私有 snapshot 或 running job 对 B 账户必须表现为“不存在”，B 不能看到 job ID/进度、等待 A 的 single-flight，或读取 A 的 raw/derived；只有 rights matrix 明确 `crossAccountShare=allowed` 且双方 grant 指向同一 rights-cleared shared catalog domain 时，才能合流。

### 6.2 Garmin adapter 的 source discovery 顺序

1. 搜索目录并保存完整原始响应。
2. 查询 `/course-layouts/{gid}/releases/`，解析 release inventory。
3. 查询目标比赛日期或当前日期的 `/date/{timestamp}`，处理 withdrawn/latest 和历史回退。
4. 枚举 release/date 中所有资产 locator，而不是只保留生产选择结果。
5. 获取 prodgeometry、已观察到的 geometry branches、coursedata/DSKIMG 和必要 metadata。
6. 官方 raster 仅作内部配准或质检；未经权利确认，不进入可分发 snapshot。

签名 URL 只在 resolver 内短暂使用，客户端永远不接触 Garmin token、ZIP key 或签名 query。

### 6.3 首次使用的物理边界

- 一个从未安装的新球场需要 Course Service 或 homeserver 在线完成发现、解析、质检和构建。
- iPhone 不是必需前置；Watch 可直连我们的 Course Service 搜索和下载。
- 安装完成并产生第一条持久打球事件后，整轮不再需要 Course Service。
- Course Service 不可达时，已安装包和 unfinished round 继续工作；从未安装的新球场明确不可用，不生成占位 18×Par 4 球局。

## 7. Immutable Raw CAS 与 provenance

### 7.1 存储模型

```text
raw/sha256/ab/<hash>
receipt/<receipt-id>
derived/sha256/ab/<hash>
snapshot/sha256/ab/<snapshot-id>
```

- `raw` 保存字节完全一致的 HTTP body、ZIP、PB、DRC、WebP、IMG。
- `receipt` 保存观察时间、semantic locator、allowlisted headers、authorization class 和父引用。
- 解密后的 archive members、Lossless IR、normalized geometry 和 render output 属于 `derived`，必须记录 `parentRefs[] + transform graph + parser/decryptor/build hashes`。跨源配准、融合和 render 通常是多父 DAG，不能压成一个 `parentRawHash`。
- player-specific overlay、事件日志和静态课程资产分区，避免每轮复制课程数据。

HTTP root domain 定义为：去除 transfer framing 后、应用 `Content-Encoding` 解压前的 entity-body octets。Acquisition adapter 应禁用透明解压并保存该 encoded entity；解压结果进入新的 derived ByteDomain。若某客户端库只能提供自动解压后的 body，receipt 必须标记 `transportDecoded=true`，该样本不能宣称 wire/entity byte closure。

### 7.2 并发与发布

- CAS 先写 tempfile、fsync，再按 hash 原子 publish。
- 每个请求先计算 `BuildSecurityDomain`：`account/grant-or-entitlement/storage-key-domain/rightsPolicyVersion`；明确允许共享时才替换为签名的 `sharedCatalogId + sharedGrantFamily + rightsPolicyVersion`。domain ID 不能由调用方任意指定。
- `SemanticBuildKey = BuildSecurityDomain + layoutRevision + source-head-generations + source-revision-hashes + parser-set + semantic-builder versions`，只决定 CourseSnapshotContent。
- `InstallProfileBuildKey = BuildSecurityDomain + snapshotId + profileId + renderer/style/toolchain versions`，只决定 CourseInstallManifest/显示资产。renderer-only 改动不得重跑 semantic promotion 或产生新 snapshotId。
- 构建使用数据库 lease/advisory lock 或任务队列 single-flight；进程内 `_HOLE_LOCKS` 不能作为生产并发正确性。
- job row、single-flight、negative cache、parser/build status、raw/derived lookup cache 和 publish staging 均继承同一 security domain；content hash 相同不允许绕过 domain。跨域只允许复用明确 rights-cleared 的非敏感公共 metadata，且仍需逐请求授权。
- build lease 固定启动时的 grant/rightsPolicy/channel generation，但不能把它当永久授权。raw fetch、decrypt/derive、snapshot/profile publish、asset serve 和 device install commit 每个产生副作用的边界都必须在事务内重验当前 rights/grant generation；policy 收紧、grant revoke 或账户删除后，旧 worker 只能把已产生证据标记 quarantined/retention-pending，不能 CAS 前移 channel、发布 ready 或继续 serve/install。
- snapshot channel 指针通过事务或 compare-and-swap 前移。

### 7.3 权利与 entitlement

- raw receipts、private derived records、SnapshotGrant 和 CourseReleaseChannel 携带 `owner/account/entitlement/provenance`；CourseSnapshotContent 不携带可变授权状态。
- 私有模式禁止跨账户 dedupe 到用户可读取的共同命名空间；物理层内部去重也必须经过 entitlement guard。
- 未经明确权利，不跨账户发布 Garmin-derived bytes 或可逆派生资产。
- 未来中央 catalog 只接收 rights-cleared 或明确允许共享的 snapshot profile。

每个 provider/source/asset class 都维护版本化 rights matrix：

```text
operation: discover | fetch | cache | decrypt | derive | render | retain | export | distribute | crossAccountShare
decision: allowed | denied | unknown
scope: account | device | purpose | region | timeWindow
evidenceRef
policyVersion
```

`private` 不是 decision。若 `cache` 未确认，响应不能进入持久 raw CAS；若 `decrypt/derive` 未确认，Research Lab 不运行对应转换；若 `render/distribute` 未确认，派生层不进入安装 manifest。rights policy 收紧时走独立 policy/grant 失效和合法删除流程，不能用技术可达性替代授权判断。

### 7.4 安全、隐私与保留

- Garmin Cookie、OAuth token、CSRF、签名 query 和 ZIP key 属于 secret，不进入 raw CAS、receipt、Unknown Registry、日志或客户端 manifest。
- 私有 raw/derived 数据静态加密，并通过账户/服务身份 ACL 与访问审计读取。
- 私有 snapshot/install asset 的 Course Service delivery URL、CDN key、ETag/range/redirect 和 browser HTTP cache 都必须绑定授权后的 opaque Build/InstallSecurityDomain，不能只暴露 content hash。服务端在处理 `If-None-Match`、Range 或 redirect **之前**授权；private response 使用 `Cache-Control: private, no-store`，离线复用只进入应用管理且 account-scoped 的 CacheStorage/local CAS。只有 rights-cleared shared domain 可使用公开 content-hash URL 与 `public, immutable` CDN cache。
- HTTP body 若混入玩家身份或个人数据，必须在 receipt 标记 data class，限制 retention，并支持按账户删除；不能因为内容寻址而失去删除能力。
- 调试和 coverage 报告只引用 hash/range，默认不内嵌原始敏感字节。
- parser 在资源预算、archive bomb、路径穿越和恶意/畸形输入上 fail closed；研究资产不能写出 CAS/staging 根目录。

## 8. Deep Mine：可证明的“挖到底”

### 8.1 可承诺与不可承诺

可以承诺：

> 对指定 corpus Merkle root 和 decoder set，所有原始字节、容器条目、字段 occurrence、Draco 属性和 DSKIMG 区间都被解析、原样 opaque-preserved、标记 padding/malformed/budget_exhausted，或进入 Unknown Registry；不存在未登记的静默丢失，结果可重跑复现。

不能承诺：

> 未取得的地区、历史、实验、订阅和运行时资产，未来格式，以及仅凭有限样本无法证明的 Garmin 私有业务语义已经全部理解。

### 8.2 研究流水线

```text
Immutable Raw CAS
→ Container / Byte Walker
→ Node Ledger
   ├ Lossless IR
   ├ Semantic Projector
   ├ Unknown Registry
   └ Fingerprint / Diff / Coverage
```

每个 node 必须包含：

- `byteDomainId`、parent node、offset、length、raw hash；
- decoder 与版本；
- occurrence index；
- status：`decoded | opaque_preserved | padding | malformed | budget_exhausted`；
- semantic hypothesis 与 confidence，若存在；
- consumer/projector consumed IDs。

每个 raw artifact 建立独立 root `ByteDomain`。压缩成员、解密明文、解码后的子 buffer 和图片像素面是新的 ByteDomain，记录 parent transform/hash，但不能把不同 domain 的 offset 混算。

字节闭包 verifier 只检查同一 ByteDomain 的直接 accounting children：它们必须以 `decoded/opaque/padding/malformed/budget_exhausted` 精确、无重叠地分区 `[0, domain_size)`。更深层语义 node 可以嵌套或引用同一 slice，但不参与父 domain 的再次分区。每个 domain 独立出具 closure proof，最后由 parent-transform graph 汇总。

Parser registry 使用 `provider + sourceType + magic/mediaType + schemaFamily + versionRange` 选择唯一权威 decoder。每个 decoder 声明输入预算、支持版本、IR schema、build hash 和已验证 fixtures。未知版本或预算耗尽时 fail closed 并保存 raw/剩余 range，不能“尽力解析”后进入产品 gate。

### 8.3 格式 inventory 最低要求

#### Archive/container

保存 central/local entries、重复路径、CRC、压缩/加密方式、extra fields、未引用数据和解压成员 hash。研究 inventory 必须列出 `prodgeometry`、`geometryrendertest`、`latestr50cooks` 等全部观察到的 branch；生产选择策略属于后续 projector。

“富图/富 geometry”只是本项目对信息量较高候选资产的内部研究标签，不是已经确认的 Garmin 产品等级。branch 名称、文件体积或字段数量都不能单独证明其业务用途。

#### JSON

使用 duplicate-key aware token/occurrence model，保留顺序、原始数字和 null；不能由普通 dictionary 覆盖重复键。

#### Protobuf

共享 wire walker 支持 wire 0–5、groups、packed candidate、边界和溢出检查。每个 tag occurrence 保存 raw range。已知 schema projector 不能删除未知字段。

#### Draco

按 attribute index 枚举 semantic、unique ID、component count、data type、normalized/quantization、values 和范围。研究层的 `POSITION` 不做三位小数舍入；所有 attributes 必须输出或登记失败。

#### Texture/image

记录真实格式、尺寸、帧、alpha、ICC/EXIF/XMP、bit depth、像素/通道统计。法线图、mask 或 height 只能作为假设，必须通过 UV/渲染或跨样本证据确认。

#### DSKIMG

从真实 header/FAT 枚举全部 subfile 和 block chain，不写死 block size、第二 FAT 项或仅取 GMP。TRE/RGN/LBL/DEM 和未知 section 分别建立 range map；parse abort 后剩余字节必须登记。

### 8.4 Unknown Registry

每项未知必须有稳定 ID、范围和证据链，例如：

- `pb:date_layout/f12/wire2`
- `archive:geometryrendertest/...`
- `drc:CliffUV2/attr_uid_3`
- `img:GMP/DEM/section_0xNN`
- `behavior:AdjGreen`

字段包括首次/最后出现、样本覆盖、raw hash/range、形态和值域、共现、状态、假设、反证、下一最小证据、是否需要抓包。

未知允许存在；不在 registry 中的未知不允许存在。

### 8.5 Fingerprint 与探索止损

每个 artifact 产生：

- content fingerprint；
- structural fingerprint；
- distribution fingerprint。

新字段、文件、attribute、section、wire type、cardinality 改变和字段消失自动生成 diff/unknown。

Coverage 不能压成一个百分比，至少并列报告：acquisition、byte accounting、syntactic decode、semantic confirmed/hypothesis/unknown、corpus strata、structural fingerprints、golden regression、consumer consumed/unconsumed nodes 和 malformed/budget errors。`opaque_preserved` 可以计入字节已分类，但绝不能计入语义已理解。

新语料按地区、版本、9/18 洞、山地/平地、海滨/内陆、稀有 DRC 层和 DSKIMG cluster 分层扩展。连续三批约 25 场的新语料均无新 structural fingerprint，且高优先 unknown 已确认、转抓包或显式延期，才结束本轮结构探索。这个停止条件是有限 corpus 结论，不是 Garmin 全宇宙证明。

### 8.6 什么时候要求 Owner 抓包

只有以下情况才创建证据任务：

- 原始响应体或资产本地不存在；
- 必须把 UI 行为与网络请求建立时间关联；
- 缺特定地区、历史或实验 branch；
- 数据只在用户正常可用的特定运行状态生成。

已有 raw 但解析器不会、主动过滤 branch 或语义难猜时，不得把工作甩给 Owner。

抓包任务必须绑定 Unknown ID，声明唯一问题、正负对照、设备/版本/locale、gid/hole、时间窗口、完整未截断 body、hash、脱敏规则和自动验证标准。只研究用户正常、合法可访问的数据，不提供绕过授权的流程。

这些是开发协作中的 evidence tasks，进入工程队列，并可由独立 Telegram Decision Pager 提醒 Owner；它们不进入高尔夫 App 的 Web/iOS/Watch 产品 Inbox，也不在打球过程中提醒。

## 9. Semantic Projector 与逐能力 Quality Gate

Gate 不是一个总布尔值。每个洞、每项 capability 独立晋升：

| Capability | 最低晋升证据 |
|---|---|
| `core.identity` | layout 洞序唯一、absolute/local mapping 完整、venue/provider provenance 一致 |
| `scorecard` | par、handicap、tee 定义范围和跨源一致性通过 |
| `distance` | tee/green anchors、单位、坐标和长度可信 |
| `map` | mesh 可解、无 NaN/越界、比例/方向/镜像验证、projection 可逆 |
| `hazardGuidance` | hazard 语义、路线和 landing window 配准通过更高门槛 |
| `playsLike` | elevation source、坐标轴、单位和高差交叉验证通过 |
| `greenSurface` | 独立 source hash、正确 green component 选择、decoder/calibration、方位 transform、baseGeometryHash 和跨源配准/消费通过 |
| `caddieGuidance` | 只消费已经晋升的事实和玩家校准；缺数据时有明确门控 |

一个 layout 能开始基础球局的最低门是：所选全部洞的 `core.identity` 和洞序完整，并能持久记录 gross score。若 scorecard/par 未通过 gate，只允许明确标注的 gross-only 模式；不得为了显示相对 par 而填充假 par。地图、hazard、plays-like、green surface 和 caddie 可以逐洞缺失，不阻塞这个基础闭环。

Par、tee、rating 和 slope 的 snapshot authority 只能来自带 SourceRevision/provenance 的课程 metadata、release 或明确审核的 course reference。玩家历史 scorecard 是观测/交叉检查，不是课程静态权威；按颜色名、tee set 顺序或 `_blue_tee` 类启发式猜选不得进入 snapshot builder。多源冲突无法消解时阻断 `scorecard` capability，退化为 gross-only。

距离、高程和坐标的 canonical contract 使用 SI：米、度、UTC/RFC3339。`baseHorizontalDistance_m` 是 current/ball coordinate 到显式 targetRef 的水平 geodesic/local-tangent 距离，不是三维 slant distance；若需要 slant distance 必须作为另一个命名事实，v1 PlaysLike 不消费它。`elevationDelta_m = targetElevation_m - currentBallElevation_m`，正值表示上坡、负值表示下坡。`playsLikeAdjustment_m > 0` 表示有效距离增加，且 `playsLikeDistance_m = baseHorizontalDistance_m + playsLikeAdjustment_m`；后二者是带 engine/input version 的推断。UI 只在呈现边界换算码，禁止把米高差直接加到码距离或在各端重复实现换算公式。

### 9.1 防止“内部自洽但整体错误”

DSKIMG 或 geometry 内部闭环不能证明地面真值。发布前还需要：

- requested ProviderCourseRef、SourceRevision、requested local hole 与资产内部 gid/hole/revision/locator coherence 全部一致；“文件存在/HTTP 200”不是 gate；
- 已知 tee、green、hole order 或可信外部 anchor 的交叉验证；
- 方向、hole swap、镜像、坐标轴、单位和尺度的显式 fail-closed 检查；单位/轴必须来自 decoder contract 或校准证据，不能按数值范围猜；
- 多洞连续性和邻洞位置检查；
- 随机真实课程的人工地图叠加或现场证据；
- decoder/version 变化后的 golden regression。

质量不足时 capability 不晋升；gross score 只要 `core.identity` 通过即可继续，distance 只有 `distance=accepted` 时才继续；不把未知 anchor、长度或 geometry 画成可信距离/地图。

每洞 promotion report 必须保存完整 binding chain：

```text
CourseLayoutIdentity
→ LayoutRevision absolute/local mapping
→ SourceRevision release roster
→ hole.json GlobalId/HoleNumber
→ exact raw hashes
→ derived layer hashes
→ asset hashes
→ SnapshotCapability
```

Gate 必须有 duplicate hole、hole swap、neighbor green 误绑、mixed release、missing roster member 和跨 gid 污染的负例 fixture。任何链条断裂或一对多歧义都 fail closed。

Elevation/PlaysLike promotion 还需要 versioned axis/unit attestation、校准 anchors、允许的 anchor 最大距离、残差/outlier 阈值和样本覆盖；阈值由 quality policy version 冻结并写进 report，不能藏在 decoder 常量。人工 overlay approval 必须绑定 raw hash、decoder/projection/quality versions、reviewer 和截图/证据 hash；数据重解后旧人工批准自动失效。

### 9.2 分层 Capability contract

不能用一个 descriptor 同时表达“课程有没有数据”“这台设备装没装”“此刻 GPS 新不新”。三端共享四层模型：

#### `SnapshotCapability`

随 CourseSnapshot 冻结，粒度为 layout/hole/layer：

```text
capabilityId
subjectRef: typed ID for layout | hole | layer
dataState: present | absent | intentionally_opaque
qualityState: accepted | degraded | blocked
reasonCodes[]
evidenceRefs[]
qualityVersion
sourceLayerIds[]
requiredAssetRefs[]
optionalAssetRefs[]
```

#### `DeviceInstallCapability`

随设备和 install manifest 变化，粒度为 device/profile/asset group：

```text
capabilityId
subjectRef: typed ID for device | profile | assetGroup
materializationState: absent | staging_downloading | verifying | installed
healthState: unknown | verified | corrupt | quarantined
currencyState: current | superseded
intentState: none | uninstall_pending
rightsState: allowed | expired | revoked | purge_pending
installSecurityDomainId
installedManifestId
recordGeneration
installedAssetRefs[]
missingRequiredAssetRefs[]
missingOptionalAssetRefs[]
reasonCodes[]
```

#### `RuntimeCapability`

随 round/facts 变化，粒度为 round/hole/capability：

```text
capabilityId
subjectRef: typed ID for round | hole | liveFact
availability: available | degraded | blocked
factsVersion
observedAt
maxAgeMs
expiresAt
accuracyValue
accuracyUnit: meters | degrees | percent
chosenExecution: local | peer | cloud | unavailable
requirements[]
reasonCodes[]
```

#### `EffectiveCapability`

由前三层、SnapshotGrant/rights 状态、signed monotonic `SafetyPolicy` 和 `PurgeDirective` 纯投影得到，供 UI 和 Guidance 消费，并声明 action queue policy 与无环 fallback DAG。Action queue policy 使用 `immediate | durable_offline | requires_online | forbidden`，不塞进静态安装状态。Fallback graph 必须终止于显式安全节点，例如 `score_only`、`distance_only` 或 `hide_guidance`。

所有 overlay 只能取交集/减能力；dominant reason 的稳定优先级为 `purge/legal → rights/grant → safety → install integrity/materialization → runtime freshness → snapshot quality`，同时保留全部 contributing reasonCodes。Purge/rights 不能被 Safety 或本地 pin 重新启用，SafetyPolicy 不能修改 snapshot facts、增加未经 gate 的能力或让 policyVersion 回退。UI 不能自行把 `SnapshotCapability accepted` 推断成“现在可用”；GPS、旗位、网络、本地资产、grant trusted-time 和 purge 状态必须经过统一 Effective projection。三端用完整 truth-table fixtures 验证 install 五轴、grant/purge/safety 组合和 dominant reason 一致。

### 9.3 地图源融合与 topo 生成策略

产品不直接把某个 Garmin 原始包当成“地图文件”交给三端，而是从多个 source 生成带 provenance 的 normalized layers：

- 已验证的 prodgeometry 作为当前基础洞形、surface 和 hazard geometry 的主要候选。
- DSKIMG 的 RGN/DEM、coursedata 和其他 provider assets 作为独立候选、粗粒度降级或交叉验证来源；不能因为内部坐标闭环就自动覆盖基础 geometry。
- `geometryrendertest`、`latestr50cooks` 和其他富 branch 先进入 Research inventory；只有证明语义、坐标和质量优于现有层后，才以新的 layer version 晋升。
- topo/contour 是从已晋升 elevation layer 派生的自有渲染结果，不把 Garmin DSKIMG、官方 raster 或未知纹理原样冒充产品等高线。
- green surface 与 hole base 使用独立 source/decoder/calibration provenance，并通过显式 transform 和 `baseGeometryHash` 绑定；未配准时宁可缺席。

同一 capability 有多个候选 source 时，builder 根据版本化 promotion policy 选择；选择结果、被拒候选和理由都进入 quality report。更新 source 不得在相同 snapshot ID 下静默换图。

## 10. CourseSnapshot 构建与资产

canonical manifest 至少冻结：

- venue、layout、absolute-hole 映射；
- source/raw/derived hashes；
- parser、decoder、projection、semantic builder versions；
- metadata、tees、par、anchors、hazards、elevation、green surface；
- 每洞 capability 和 quality report hash；
- normalized semantic asset hashes、media type 和 schema；
- source content hashes 和不可变 provenance refs；
- schema version 和 canonicalization version。

`snapshotId` 证明 semantic content 身份，不证明发布者身份；每个安装 manifest 还必须由 Course Service 的可轮换 signing key 签名，并声明 renderer/style versions、key ID、签名算法、签发时间和撤销 channel。客户端必须先验证签名，再验证逐资产 hash。

对象 key 必须由内容 hash 形成。当前 `gid/hole/style` topo ETag、Watch `gid_hole` 覆盖式图片和 mutable `output/gid*_h*` 不能作为正式 snapshot identity。

基础 geometry 与 green surface 可以是 manifest 内独立组件，但不能成为客户端可随意并行更新的顶层包。`CourseSnapshot` 必须一次冻结它们的兼容组合，防止跨版本错位。

## 11. 三端原子安装和离线整轮

### 11.1 通用 installer 状态机

Installer 不是一个把所有含义塞在一起的 enum，而是五条正交轴：

```text
Materialization: absent → staging/downloading → verifying → installed
Health: unknown | verified | corrupt | quarantined
Currency: current | superseded
Intent: none | uninstall_pending
Rights: allowed | expired | revoked | purge_pending
```

- `InstallRecord` 持久化上述五轴、profile manifest、staging、verification 和单调 `recordGeneration`。`superseded` 或 `uninstall_pending` 不会把 materialization 偷偷改成 absent；只要仍是 installed，其 required assets 仍是 root。
- `PinRecord` 持久化 round/LRP/snapshot/install binding 与 operational/audit ref type。
- `UninstallRequest` 持久化用户意图，在 pin 释放后完成；不能因为 app 重启丢失或提前删除。
- 每台设备从 signed grant 派生不可由客户端伪造的 `InstallSecurityDomain(accountId, grantId/entitlementId, storageKeyDomain, rightsPolicyVersion, deviceProfile)`。InstallRecord、PinRecord、staging path、resume bitmap、installed index、本地 CAS ref 和 Web Cache/IndexedDB namespace 全部以该 domain 分区；登出/切账户不能看到或激活另一 domain 的 ready/staging/install 状态。只有 `crossAccountShare=allowed` 的 shared grant 才能显式使用共享只读 asset domain，账户专属 install/grant index 仍分开。
- 所有资产先写 `<installSecurityDomain>/<installManifestId>.partial` 或等价 staging namespace，不能仅用 content hash 跨账户寻址可读状态。
- 逐项验证签名、hash、大小、media type 和最低 schema/client version。
- 只有 commit marker/事务索引成功后才算 installed。
- 崩溃、断网和部分下载保留可验证 staging 并支持断点续传。
- 旧 snapshot 与新 snapshot 可并存；active/unfinished round pin 的 snapshot 不可被 GC。
- 更新先把新 manifest 完整安装，再以 CAS 提升 channel/install generation；旧 record 只变 `Currency=superseded`，在显式原子 uninstall/deactivation 前继续 materialized/root，可供 pinned round 或回滚使用。
- repair 从 corrupt/quarantined record 建独立 staging，验证后原子恢复 `Materialization=installed, Health=verified`；repair 失败保留旧记录和诊断，不能把 corrupt 标成 ready。
- uninstall 先 CAS `Intent=uninstall_pending`。若 pin=0，同一事务移除 installed index/required roots 并设 `Materialization=absent`，之后 bytes 才可异步 GC；若 pin>0 则保持 installed/root 等待。start 与 uninstall 对同一 `recordGeneration` 竞争：start 先成功则 pin 阻止卸载，uninstall 先成功则新 start fail closed。
- 新 start 只允许 `Materialization=installed + Health=verified + Currency=current + Intent=none + Rights=allowed`，或由更高 generation rollback channel 明确把旧 record 重新设为 current。active pinned round 的 continuation 另按 grant/policy，不重新经过“新 start”门。

传输单元携带 `snapshotId/installManifestId/assetHash/assetGroup/ordinal/offset/length/totalLength`。接收端允许 duplicate 和 out-of-order chunk，但只按 hash/range bitmap 记进度；resume 请求声明已验证 ranges，发送端不能相信单纯文件长度。最终 commit ACK 只在全部 required assets、roster、签名和 installed-index 事务成功后返回。

开始球局必须执行一个本地原子事务：

```text
verified_current_allowed_unpinned + recordGeneration
→ verify manifest + assets
→ verify local manifest compatibility with RoundSemanticBinding
→ persist local DeviceRoundInstallBinding
→ create/reuse round incarnation from roundIntent
→ increment snapshot/install-manifest pin
→ append idempotent durable round_started event when this is the initiating intent
→ active_pinned
```

同一 intent 从 iOS 中继到 Watch 时携带相同 `roundId/roundIntentId/roundIncarnationId/RoundSemanticBinding`，但各自事务 pin 自己的 compatible install manifest。任一步失败都回滚本机 round activation 和 pin，不产生“球局存在但包可删”或“永久幽灵 pin”。只有 Lifecycle 为 finished/discarded、Replication 为 clean、vector checkpoint 已持久化且无本地恢复需求时，才能释放**设备 operational pin**。更新不能替换 pinned binding；普通卸载在 pin 大于零时失败；安全撤销可以禁用能力，但不能在仍需恢复球局时先删除事件或必要静态包。

SnapshotGrant 到期默认禁止新安装和新开局。active round 是否可继续由 grant 中显式、已签名的 `activeRoundContinuation` 决定；字段缺失或 rights policy 不允许时 fail closed，并按 SafetyPolicy/PurgeDirective 退化或删除，不能由客户端自行“宽限”。

### 11.2 Watch

- 安装完整 9/18 洞 Watch profile，不以“当前+下一洞”作为正确性基础。
- iPhone `transferFile` 可作为镜像加速，但 Watch 可直接 HTTPS 下载。
- Watch app 内置 Course Service signing trust root；轮换 key 必须由已信任 root/rotation chain 签名，设备同时持久化最高 channel/policy generation，防止旧合法包重放。
- Watch 需要独立 app auth bootstrap 和 token refresh，使用 Watch-native device/app flow 与 Keychain scoped token；手机下发可作首次配对加速，但短期 phone token 不能成为永久前置。Garmin 上游凭证永不进入 Watch。
- 离线时可开已安装球场、记分、记录事实、纠错、结束并进入 `finishedPendingSync`。

### 11.3 iOS

- 后台下载和原子目录切换；包管理、删除和固定球场遵守 pin/GC 规则。
- 可中继 Watch 安装包，但每个 `transferFile` 必须附带上述 manifest/chunk metadata；手机不得用文件名或发送顺序代替 identity。
- 承担深度编辑、媒体和证据采集，不成为 Watch 独立开局前置。

### 11.4 Web

- 使用同一 manifest，在 versioned Cache Storage namespace 中 staging 资产；逐项 hash 验证后，最后一次 IndexedDB 事务写 installed index/commit marker。旧 cache namespace 在新 index commit 前保持可用。
- Web 可按需安装高清 profile，但不能发明另一套 layout、capability 或 guidance 语义。
- Web 不作为场上实时事实 producer；继续承担备战、治理和复盘。

## 12. RoundEventEnvelope 与 deterministic reducer

三端直接产生同一个业务 envelope，不再让 `WatchInputEvent` 成为第二套事实模型：

```text
eventId
originDeviceId
originEpoch
clientSequence
ownerAccountId
subjectPlayerId
actorId
roundId
streamSubject: round_incarnation(roundIncarnationId) | merge_control(mergeControlId)
roundIntentId
snapshotId
roundSemanticBindingHash
occurredAt
kind
entityRef
payload
causationId
baseEntityRevision
schemaVersion
```

`streamSubject` 是 generated discriminated union，不能同时出现两个 ID，也不能用空 roundIncarnationId 冒充 control stream。普通 play/fact event 使用 `round_incarnation`；`round_merge_resolution` 使用 `merge_control`。`roundIntentId/snapshotId/roundSemanticBindingHash` 是否 required 由 EventKind Registry 固定：play/start 事件必须有，merge-control event 按其 payload 引用 source RoundSemanticBindings，不伪造单一 source binding。

Envelope 中 `baseEntityRevision` 与 `schemaVersion` 是独立字段，不能复用一个含糊 slot。`eventHash` 按 §5.11 的 `RoundEvent` registry 对**完整 immutable envelope**计算，包含 identity fields、streamSubject、kind、entityRef、payload、baseEntityRevision、causationId、occurredAt、snapshot/binding refs 和 schemaVersion；只排除 receipt、ledgerPosition、ACK/retry 等服务端运输 metadata。Python/Swift/TypeScript 以相同 fixtures 验证 byte-identical hash。

### 12.1 传输和业务分离

- 幂等键至少包含 `ownerAccountId/streamSubject/originDeviceId/originEpoch/eventId`。
- 手机转发 Watch 事件时保留 origin，不重新冒充 phone event。
- ACK、cursor、`ledgerPosition`（旧 adapter 名 `serverSequence`）、retry/dead-letter 属于传输 metadata。
- 未知 event kind 不能导致整批 422 或重放全失败；mixed-client migration 必须有逐事件 accept/reject 和 dead-letter。
- 同一 origin 的 `clientSequence` 用于检测缺口和重复；跨设备不能仅按客户端时间戳排序。服务器接收顺序用于传输追踪，业务纠错通过 `entityRef + baseEntityRevision + causationId` 表达，reducer 使用已版本化的确定性优先规则处理并发。
- 业务幂等以单个 event identity 为准。batch idempotency key 只能缓存一次完整、原子提交的响应；崩溃后部分写入的重试必须逐事件补齐，不能把整个 batch 判为 duplicate。
- event identity → eventHash/terminal receipt/dead-letter tombstone 索引独立于 LedgerPartition/ledgerEpoch，至少保留到该 round/event retention 或 privacy purge 完成。compaction 只改变 replay partition/checkpoint，不能清空 dedupe：旧 outbox 重传 pre-compaction accepted/opaque/rejected event 时返回原终态/compacted receipt，不分配新 ledgerPosition、不重复 reducer side effect。
- ACK 描述消费进度而不是事件来源，必须按 `(ownerAccountId, ledgerPartitionId, consumerDeviceId, consumerEpoch)` 对 `ledgerPosition` 单调 compare-and-set；旧客户端或并发写入不能让 ACK/cursor 回退。生产 ACK store 使用事务存储，不能用整份 JSON 文件覆盖。
- 除首个 `round_started` 建立 branch binding 外，所有 round-incarnation known/opaque event 在 accept 前都必须通过 common binding guard：`ownerAccountId/roundId/roundIntentId/roundIncarnationId/snapshotId/roundSemanticBindingHash` 与冻结 branch 完全一致。mismatch 返回 permanent `round_binding_mismatch` 并进入 visible dead-letter；未知 kind 只有在 common envelope/auth/binding 合法后才可 `accepted_opaque`。

### 12.2 Canonical order 与本地 provisional order

- 每次设备事件流重建或本地数据重置产生新的 `originEpoch`；`originEpoch + clientSequence` 在一个 origin 内严格单调。
- 设备离线时只拥有 `LocalProjectionOrder`，由本设备 origin sequence、已缓存远端 checkpoint 和稳定 event ID 构成；UI 必须把未同步冲突视为 provisional。
- `LedgerPartitionId` 由 `ownerAccountId + canonical streamSubject + ledgerEpoch + streamId` 规范生成。服务端逐事件接收后在该 partition 内分配不可回退的 `ledgerPosition`，形成 canonical transport order；重放返回相同 position。旧 contract 的 `serverSequence` 只允许由 migration adapter 单向映射为同值 `ledgerPosition`，新 envelope/receipt 不能同时出现两个名字。
- 不同 LedgerPartition 的 position 不可比较，也不能用一个账户全局整数暗示业务先后。compaction 创建更高 `ledgerEpoch` 的新 partition/checkpoint；旧 partition cursor 返回 `bootstrap_required`，不得猜测位置映射。
- 单一或 merged round 的 reducer 输入使用 versioned `ProjectionOrder`：先满足 causation/baseEntityRevision dependencies，再保持每个 partition 的 ledgerPosition；跨 partition 无因果关系的事件只用 merge resolution source ordinal + stable event identity 作确定性遍历。若两个操作的业务结果会因为这个 fallback 顺序而改变，reducer 必须产生 conflict projection，不能把遍历顺序冒充胜负规则。
- 业务结果不能依赖“谁的手机时钟更早”。普通事实尽量设计为按 entity 可合并；修正显式指向目标 entity/event 和 `baseEntityRevision`。
- 两个并发、不可自动合并的修正都保留，并产生 conflict projection；版本化 reducer policy 只处理有明确规则的 tie，不能静默丢弃 losing event。
- 客户端同步 canonical checkpoint 后重新投影；若 provisional 结果改变，展示可解释的 reconciliation，而不是在本地继续维持第二真相。

### 12.3 投影

- `RoundProjection` 只能由 pure reducer 从 snapshot + ordered events 生成。
- UI 不直接写 projection 或静态 snapshot。
- iOS/Watch 共享 Swift Domain target；后端 Python reducer作云端权威；Web 读取投影。
- Python reducer 与共享 Swift reducer 使用同一批 golden event traces 验证：离线顺序、重复、部分 ACK、纠错、崩溃恢复、混合客户端和 finish/suspend。
- Web runtime 只消费后端 projection，不成为第二个可写 reducer。TypeScript 运行 generated schema/decoder 和 projection-view conformance：对同一 golden trace 的已知 expected projection 验证反序列化、缺席原因和展示映射，不自行决定业务冲突。

### 12.4 Round identities 与 start binding

- `roundId`：首次 start intent 时客户端生成的全局稳定逻辑球局 UUID；离线可创建，成功汇合后不重写。
- `roundIntentId`：一次 start command 的幂等 ID，绑定 `roundId + RoundSemanticBindingHash`。Watch/iOS 中继同一次 start 必须复用它。
- `roundIncarnationId`：该 intent 建立的不可变 start branch ID；同一 intent 的 Watch/iOS relay 共享它。独立离线 start intent 产生新 incarnation；app 重装、本地流重建或同步 cursor 重置**不改变** incarnation，只提升对应 device 的 `originEpoch/consumerEpoch`。

`round_started` event 必须携带 RoundSemanticBindingHash，并记录 initiating device 的 `DeviceRoundInstallBinding` 作为安装证据；后续设备加入只需证明自己的 compatible binding，不改写 round event。相同 roundIntentId 但 semantic binding 不同是 permanent conflict，不能当 duplicate。不同设备独立创建的不同 roundId/intent 在同步时保留为独立 provisional rounds，进入 start conflict 流程。

### 12.5 Normative event registry 与 per-event receipt

Track A 必须产出 machine-readable EventKind Registry；每个 kind 固定：entity key、payload schema/units、operation、baseEntityRevision、merge/conflict/unset、retention 和 minimum client version。核心类别至少包括：

| Event kind/class | Entity 与 operation | 关键规则 |
|---|---|---|
| `round_started` | round / append-once | 固定 RoundSemanticBinding；initiating DeviceRoundInstallBinding 只作设备安装证据 |
| `round_suspended`, `round_resumed`, `round_finished`, `round_discarded` | round lifecycle / append transition | discard 是 durable event，不删除 ledger |
| `hole_score_set`, `putts_set`, `penalties_set`, `fairway_set` | hole fact / set-supersede | typed integer/enum，要求 baseEntityRevision |
| `shot_recorded` | shot / append | 稳定 shot entity ID、位置、lie、时间和 provenance |
| `shot_fact_corrected` | shot field / supersede | 指向 target shot/entity revision，不改写原 event |
| `shot_retracted` | shot / retract | 保留原事件和理由，统计投影排除 |
| `actual_club_set` | shot club / set-supersede | actual 与推荐严格分离 |
| `resolution_*` | resolution episode / append transition | 同一 scope 至多一个 active episode |
| `round_merge_resolution` | round merge control / append-supersede | 引用全部 source round/incarnation/checkpoint，不移动或改写原 event |

每个上传 event 都返回独立 receipt：

```text
eventIdentity
eventHash
status: accepted | duplicate_hash_match | accepted_opaque | rejected_permanent | deferred
ledgerPartitionId
ledgerEpoch
streamId
ledgerPosition
currentEntityRevision
reasonCode
```

- 相同 event identity、相同完整 `eventHash` 才是 duplicate。
- 相同 identity、不同 `eventHash` 返回 permanent `identity_envelope_mismatch`，不得覆盖；即使 payload 相同但 kind/entityRef/baseEntityRevision/binding 不同也不是 duplicate。
- 相同 batch idempotency key、不同 request body hash 返回冲突，不能复用旧响应。
- `accepted_opaque` 原样进入 ledger 但不改变当前 projection，待兼容 reducer 可重放。
- `deferred` 可重试且不前移该事件的 durable ACK；`rejected_permanent` 进入可见 dead-letter。
- set/supersede payload 必须区分 `unset`（未提供/不改变）、显式 `null`（若该字段 registry 允许清除）和具体值；各 kind 不得靠语言默认值猜语义。
- `baseEntityRevision` 必须是完整 EntityRevisionToken；相同 ordinal 但 projection/contributing-event hash 不同按并发冲突处理，不能只比较数字；provisional/canonical token 在 causal event set 与 projection hash 等价时允许确定性映射。

Producer outbox 的规范状态转换为：

| Receipt | 本地原子动作 | 是否继续自动重试 |
|---|---|---|
| `accepted` / `duplicate_hash_match` / `accepted_opaque` | 先持久化 receipt、eventHash、LedgerPartitionId/position，再从 transport outbox 删除；业务 event 仍留在本地 ledger | 否 |
| `deferred` | 保留原 outbox item、attempt/backoff/reason；不得前移 outbound completion | 是 |
| `rejected_permanent` | 原 event + receipt 原子移入 visible dead-letter，随后从 retry queue 删除 | 否，等待人工/版本化修复 |
| response 缺该 event receipt / transport uncertain | 保留原 outbox item；以同 event identity/hash 重试 | 是 |

Inbound replay ACK 与 outbound receipt 完全独立：不能因为上传成功就 ACK 尚未持久化/投影的远端 stream，也不能因为 replay ACK 前进就删除未取得终态 receipt 的本地 event。

### 12.6 正交的球局与同步状态

业务生命周期和复制状态是两条轴：

```text
Lifecycle: draft → ready → active ↔ suspended → finished | discarded
Replication: clean ↔ dirty → syncing → clean | conflict | deadLetter
```

`finishedPendingSync` 只是 `Lifecycle=finished + Replication=dirty/syncing` 的 UI 投影，不是 canonical 单轴状态。active/suspended 可以是 clean 或 dirty；finished 后 iOS 深度修正会保持 Lifecycle=finished、重新进入 Replication=dirty，服务端接受后再次 clean 并重算统计。

- `discarded` 只能由显式 durable event 进入；不本地删除 ledger，也不清 pending queue。
- 服务端 canonical projection 中每个 player 至多一个 active round，但离线设备可能各自产生不同 `roundIncarnationId` 的 provisional start。
- 在线 start 通过事务取得 active lease；离线 start 创建 provisional incarnation，并先 pin 本地 snapshot/LRP binding。
- 同一 roundId/roundIntentId 在 Watch/iOS 间中继时可以安全汇合；不同 intent 同步时若与已有 active/unfinished round 冲突，服务器保留全部事件并产生 `RoundStartConflict`。
- 冲突由 iOS 恢复流程选择继续一个、合并可证明属于同一局的事件，或显式 suspend/discard；任何未选择分支保持 durable。
- v1 普通 merge 的硬门是所有 source `RoundSemanticBindingHash` 完全相同；不同 snapshot、layout revision/洞序、teeSelection 或 LRP 的分支不能合并，只能选择、suspend/discard 并保留各自 ledger。未来若支持跨 binding 合并，必须先定义显式逐洞/逐事件 remap contract 和证据，不能把一种洞序/距离/Guidance 语义套到另一分支。不同设备 profile/installManifestId 不阻止 merge，只要各自 DeviceRoundInstallBinding 都兼容同一个 semantic binding。
- 合并只能追加 `RoundMergeResolution`：声明 canonical round、ordered source `roundId/roundIncarnationId` membership、决策时各 source partition/checkpoint、选择/冲突 policy 和 actor/evidence。checkpoint 是决策证据与 bootstrap 下界，不是冻结 cutoff；membership 默认 `live_until_superseded`，因此合并后迟到的 Watch event、离线深改或 correction 一旦进入任一 source ledger，会自动推进 source vector 和 `mergedCheckpointHash` 并重新投影。
- `MergedRoundStream` 是 merge-control partition + source incarnation partitions 的虚拟 vector stream，不复制事件、不制造全局 sequence。source compaction 时只替换该 vector member；consumer 遇到新 partition/mergeControlGeneration 必须重新取得 DeviceSyncBootstrap。unmerge/改选 source 通过更高 revision 的 resolution 提升 mergeControlGeneration 并发布新 membership；旧 source ledgers、event identities 和历史 vector checkpoints 永不重写。
- merge 生效后，source branches 的原 lifecycle events 保留，但 control projection 赋予其 `mergeRole=source_member`；只有 canonical aggregate 持有 player-facing active lease/active slot。unmerge 后按 superseding resolution 恢复各 branch 的可见 lifecycle/conflict 状态，不靠改写旧 finish/start event。
- 开始新局、finish、discard 或解决冲突不能清空旧 round 的未同步队列。
- 包过期只阻止新开局，不终止已开始的 round。
- 单个交互纠错/确认使用独立 `ResolutionEpisode`。在线事务可保证同一 scope 至多一个 canonical active episode；离线设备可以各自产生 provisional episode。同步发现并发 active 时全部保留并产生 conflict projection，直到显式 resolution 选择/supersede，不能按到达顺序静默关闭其中一个。

## 13. 更新、回滚、撤销与 GC

### 13.1 普通更新

构建新 snapshot，并原子更新 `current` channel。未开球用户可安装新版本；active round 继续旧版本，结束后提示更新。

### 13.2 回滚

回滚不让 channel generation 倒退，而是发布一个**更高 generation**、重新指向旧 snapshot/install manifests 的 signed channel record。内容寻址对象不修改。客户端未开始的新局使用回滚目标；已开始的局继续 pin。

### 13.3 安全撤销

P0 撤销通过独立于 CourseSnapshotContent 的 signed、monotonic `SafetyPolicy` 发布。它包含 `policyVersion/channelGeneration/issuedAt/keyId/reason/effectiveRules`；客户端只接受签名有效且版本前进的 policy。Policy 只能减能力或禁止新动作，不修改静态事实、洞序和历史事件。

SafetyPolicy 可分别表达：

- `denyNewInstall`；
- `denyNewRound`；
- `disableMap`；
- `disableGuidance`。

若发现错洞、镜像或危险 guidance，即使 active round 不切换 snapshot，也可以在下次联网后以更高 policyVersion 收紧能力并退化为安全 facts。完全离线设备不可能即时获知撤销，这个物理边界必须公开。Policy 缓存和 snapshot pin 分开，防止把“冻结静态事实”误解成“永不接受安全降级”。

删除不是 SafetyPolicy 的副作用，而是独立 signed `PurgeDirective`，带 rights/privacy basis、scope、deadline 和 generation。优先级为：

1. Owner 隐私删除或明确法律强制 purge；
2. rights grant 失效和禁止继续保留；
3. safety capability reduction；
4. ordinary operational pin/GC。

Safety 问题优先禁用能力、保留恢复所需事实。rights/privacy 指令若要求删除，可以覆盖 operational pin，但必须先尽可能保护独立的玩家事件日志、明确退化为 score-only、记录审计和告知无法恢复的资产；不能用 active pin 无限延迟合法删除。

执行 PurgeDirective 必须是可恢复事务：先持久化 directive generation、阻止新安装/开局，并把受影响的 `InstallRecord.Rights` 原子转为 `purge_pending`、更新 EffectiveCapability 和 score-only 恢复投影；随后其目标 refs 才进入 GC subtract overlay。字节删除完成后写 audit completion、设 `Materialization=absent/Rights=revoked` 并移除失效 installed index。任何崩溃点都不能留下“仍可 start/显示 ready，但 required bytes 已删”的假安装。

Purge 完成度必须分开记录 `server_erased | device_pending | device_acknowledged`，并逐 device/account domain 审计。长期离线或已失联设备在物理上收不到新 directive，不能因 deadline 到达就宣称其本地 bytes 已删除；它下次联网时必须在解锁 course/start/sync 之前先处理最高 purge generation 并回 ACK。需要限定长期离线保留的 rights profile 必须使用 signed `offlineNotAfter/maxOfflineAge` 和可到期的 device content-key lease；没有这类预先边界时，只能报告 device_pending，不能虚构远程擦除能力。

### 13.4 GC

- active/unfinished round、用户固定球场和尚未完成同步的 snapshot 不可删除。
- 只要 `InstallRecord.Materialization=installed`，其 manifest 声明的**全部 required assets**——包括 required presentation/display——都是本地 root，不受 `Currency=superseded` 或 `Intent=uninstall_pending` 单独影响；否则 UI 会显示“已安装”却在离线缺文件。低磁盘只能删除 optional assets，或通过一个原子事务降级到新的较小 manifest / 完成 uninstall，再释放旧 required roots。
- operational pin 释放只允许 round-specific 临时/optional display cache 被 GC；它不自动释放 installed manifest 的 required assets。
- canonical round/event archive 对 `snapshotId + semantic manifest + immutable provenance refs` 保留 audit reference；只要球局仍在 retention 内，就不能因设备 pin 释放而全局删除其可重放语义。
- 大体积 CAS asset 只有在所有 install/operational/audit/rights retention 引用释放后才进入回收；rights/privacy PurgeDirective 另按 §13.3 处理。
- player event log 与课程资产分开；安装失败或 GC 不得影响已记录杆数。

GC root set 必须显式包含：所有 current/rollback-retained channels、SnapshotGrants、installed manifest 的 required assets、active/suspended/dirty finished rounds、user pins、audit/legal holds、staging transaction 和 running build lease。`PurgeDirective` 本身的签名元数据/审计记录是 root，但其目标对象是 mark 前应用的 deny/subtract overlay，绝不能因为“pending directive”反而把待删 bytes 加成正 root。Mark/sweep 使用 `gcGeneration` 或 lease snapshot；installer/build publish 在 mark 与 sweep 之间产生的新引用不能被旧 sweep 删除。

Staging 有独立 TTL 和 `stagingOwnerId/InstallSecurityDomain`；过期、无 build lease 的 staging 可清理。低磁盘 LRU 只清未 pin、可重下的 optional assets（包括 optional display），并在同一事务更新 `InstallRecord.missingOptionalAssetRefs`；不能清任何 required asset 或 event outbox。CAS 定期 scrub hash/size/ref integrity，corrupt object 进入 quarantine 并触发重建，不把坏对象继续共享。

账户删除按 privacy PurgeDirective 覆盖普通 round/audit retention root：删除或不可逆去标识 grants、private receipts、player overlays、round/event ledgers、merge-control memberships、media/evidence、ACK/bootstrap/outbox/dead-letter、device/origin identifiers 和专属 encryption keys，并解除它们对 CourseSnapshot 的个人引用。active/dirty/merged 状态不构成无限延期理由；仅有明确 legal hold basis 的最小记录可进入隔离、限权 hold，而不能继续出现在普通产品/统计路径。共享物理课程 CAS 只能在无其他合法引用时删除。使用 per-account envelope encryption 时允许 crypto-erase，但只保留不含个人信息、不可反推球局内容的删除审计证明。

## 14. 风与 weather 漂移的确定性修正

当前代码已经违反范围：

- `mobile/contracts/live_round_package.schema.json` 强制 `weatherSnapshot`；
- `ai_caddie/caddie/mobile_live.py` 获取并注入天气；
- `ai_caddie/caddie/decision.py` 的 `_wind_adjustment_m` 用经验系数修正 carry；
- Web/Watch 部分文案和测试仍把 wind 当 readiness 或 plays-like 输入。

正式 contract：

- 从 LRP required fields、Guidance input、Watch readiness、Caddie UI 和 carry calculation 移除风。
- `PlaysLike v1 = verified elevation adjustment`。
- 天气若未来作为赛后历史背景保存，使用独立、可选的 observation，不进入 live guidance，也不影响包可用性。
- 未来加入风必须先完成来源、空间/时间精度、TTL、离线、续航和现场校准证据，再显式重开 Owner 决策。

迁移必须双版本：旧 Swift/v1 LRP decoder 仍要求 `weatherSnapshot` 时，服务端只为该 schema 返回明确 `unavailable/neutral` 的兼容字段，所有 reducer/Guidance 忽略它；v2 LRP contract 完全移除字段。覆盖率证明旧客户端退出后，才删除 v1 serializer。不能直接停止下发导致旧客户端整包 decode 失败，也不能让兼容占位重新进入决策。

## 15. 三端职责和禁止的再次分叉

| 层 | 正式职责 | 明确禁止 |
|---|---|---|
| Watch | 独立选场/安装/开局、GPS、记分、场上事实、浅纠错、离线整轮 | 自己解析 provider raw；依赖手机才能开局；维护第二套 event 语义 |
| iOS | 独立打球、深编辑、包管理/中继、媒体和证据采集 | 把 Watch event 改写为 phone origin；成为 Watch 静态数据唯一来源 |
| Web | 备战、治理、研究、复盘、只读球局呈现 | 浏览器实时 GPS 记分；发明独立 round/layout/guidance 模型 |
| Backend | Course Service、contract registry、reducer、权限、构建、同步 | 保存 surface navigation state；用 mutable gid path 作为版本身份 |
| Research Lab | 无损解析、unknown、差分、证据与 promotion candidate | 直接发布到客户端；用假设字段驱动球童 |

平台可以改变布局、字体、Crown/触摸/haptic 和后台生命周期，但不能改变同一事实的含义、可用性、缺席原因和恢复状态机。

## 16. 当前代码复用、修改后复用与淘汰

### 16.1 可直接复用的受限基础原语

没有现成 feature module、cache/store 或 installer 可以原样成为新 authority。唯一可直接复用的是经过边界/畸形输入测试的、无状态低层 primitive，例如 `inspect_courseview_release.py` 的 varint decode；即使复用，也必须放进新 parser package 和 occurrence-preserving tests，不能连带继承旧 release 选择/发布行为。

### 16.2 需要重构后复用

- `ai_caddie/core/data.py` 的 `HoleRef` 正确区分 display/physical hole 的概念，但正式 key 必须扩展 provider namespace、SourceRevision 和 typed logical identity；同目录 tempfile + `os.replace` 也要补 file/directory fsync、schema/hash 和事务边界。
- `ai_caddie/courses/prep_cache.py`：可复用 fingerprint/LRU/single-flight 算法，但 key 必须加入 Build/InstallSecurityDomain、source/snapshot/tee/profile/generator；只能作非权威派生响应缓存，不能承担 readiness 或跨 worker build lock。
- `ai_caddie/connectors/snapshot.py`：dependency manifest、状态和 provenance 结构可作 schema 参考；必须迁移到 typed IDs、CanonicalObjectRegistry 和新 CourseSnapshot store，旧 connector snapshot 不可作为 authority。
- `course_search.py`：只保留 transport/race guard 和候选呈现模式；provider namespace、account/grant scope、auth、弱匹配和状态语义由新 adapter 重建。
- `inspect_courseview_release.py`：保留低层 wire walker；完整 adapter 必须校验 response course ID、release/version、唯一连续洞序、男女 par/handicap、provider tee index/name/gender/slope/rating，未知字段或 partial response 诊断后 fail closed。上游 locator 只留在服务器 resolver。
- `geometry_sync.py`、`batch_prodgeometry_course.py` 和 Node decoder/key 工具：只复用下载/解密/Draco transport primitive 与 fixtures；cache/live/date fallback、mutable gid/hole output、best-effort readiness 和发布流程必须替换为 SourceRevision + Raw CAS + BuildSecurityDomain + quality gate。
- `geometry_evidence.py`：路线、hazard、landing-window 数学可作为 promotion candidate；当前“文件存在即 ready”和缺 provenance 的结果不能直接晋升。
- `course_prep.py`：只保留可证明的几何/距离计算 primitive；固定 blue tee、无 tee 参数 cache、静态 authority 混用和 current `greenSlope` 路径必须替换。
- `topo_render.py`：保留自渲算法和 progressive fallback 方向；输入 identity、ETag、URL、依赖 manifest、rights gate 和 output hash 全部重做。
- iOS `WatchEventBridge.transferFile`：只保留平台 transport 能力；manifest identity、chunk/range resume、逐项 verify、commit ACK 和 installer transaction 全部重做。
- 当前手写 protobuf parser：迁移到共享 occurrence-preserving wire walker。
- prodgeometry decoder：枚举全部 Draco attributes，研究层不舍入。
- DSKIMG decoder：从真实 FAT/subfile/section inventory 重做。
- `mobile_live.py`：保留 LRP/事件服务骨架，去除静态路径、weather required 和隐含 snapshot。
- iOS `OfflineStore`：只复用 append-only/outbox/恢复思路；当前仅按 eventId 去重、业务 ledger 写 `sync_marker/hole=0`，持久化 identity 和 schema 必须迁移。
- Watch `WatchRoundStore`、`WatchSyncClient`：只复用本地 durable queue 方向；当前 finish/new-round/config-missing 清队列语义必须替换。
- 后端 event ingest/replay/ACK：只保留 API 轮廓；旧 `serverSequence` 仅作单向 migration adapter，正式 LedgerPartition/ledgerPosition、逐事件幂等、partial batch recovery 和 monotonic transactional ACK 必须重做。
- iOS/Watch DTO 与 mapper：迁移到共享 Swift Domain target 和 generated contracts；直接 Watch mapper 与 phone bridge 的数字/club 验证必须统一。
- `greenSlope`：当前整块 `Green.drc` 平面拟合和跨端未消费状态先 quarantine；完成 component 选择、source hash、方位 transform、baseGeometryHash 和 Python/Swift consumer tests 后才 promotion。

### 16.3 不可原样继续

- mutable `data/courseview/<gid>_releases.pb` 和 `output/gid*_h*` 作为正式版本存储。
- `fetch_courseview.py/parse_courseview.py` 的“文件存在即最新”、固定偏移、异常吞噬和 best-effort 产物；只允许留在 `tools/` 作取证、fixture 和回归 oracle。
- 按颜色/数组顺序猜 provider tee、捏造 generic tee，或 `course_prep` 固定选择 blue tee。
- 玩家历史 par 覆盖 provider/course authority，或缓存缺失时把洞数伪装成 `[1...9]`。
- topo 的 `gid/hole/style` cache key。
- history 领域当前 `snapshotId` 名称冒充 CourseSnapshot；应重命名其 Garmin/history 语义。
- Watch `gid_hole` 图片覆盖式缓存和“只推当前+下一洞”正确性模型。
- 进程内 `_HOLE_LOCKS` 作为多 worker single-flight。
- `WatchInputEvent → LiveRoundEvent` 双业务模型。
- `weatherSnapshot` required 和 `_wind_adjustment_m` 生产路径。
- Web 浏览器高精度 GPS 的实时逐杆记分路径。
- Web 仅存 React state 却称“离线包”，以及“发到手机/手表”按钮实际只执行 `window.print()` 的误导性产品声明。
- 服务端固定返回 `live-<gid>` suggested round ID；同一 layout 连续开两局必须生成不同 roundId，且旧 package/event 不能串局。
- 任何 `18 × Par 4` 假球场 fallback，除非明确隔离为测试 fixture。

## 17. 失败语义与诚实降级

| 失败 | 产品行为 |
|---|---|
| 搜索无结果 | 要求补地点或从地图候选选择；不接受弱模糊匹配 |
| layout ambiguous | 在安装前确认有序九洞组合；不自动猜 |
| unknown schema | raw quarantine；旧 accepted snapshot 继续，否则只发布通过 gate 的基础能力 |
| geometry 缺失 | 只发布各自独立通过 gate 的 scorecard 或 distance；anchors 未验证时 distance 同样 unavailable，地图/hazard/guidance 明确 unavailable |
| 部分下载或崩溃 | staging + hash verify + resume；无 commit marker 不算 installed |
| Course Service 不可达 | 已安装场和 active round 正常；新场不可构建 |
| Watch/iOS 混合版本 | 逐事件兼容、reject/dead-letter；不能整批失败或无限重试 |
| 错洞/镜像发现 | 禁用 map/guidance、发布 tombstone；保留安全记分事实 |
| event sync 失败 | 保留本地 durable queue，进入 finishedPendingSync；不清除 round |

## 18. 验证与证据矩阵

### 18.1 Acquisition

- 搜索结果、provider refs、VenueIdentity 和 CourseLayout 可追溯。
- 单 gid 9 洞、单 gid 18 洞、18 洞 front/back 作为单九、两个九洞不同顺序、误 merge 后 unmerge/alias 均有 fixtures；历史 snapshot identity 不被改写。
- release latest/withdrawn/date fallback、`204/404/403/429/5xx/timeout/partial` 的 SourceObservation/SourceHead overlay 矩阵和 source manifest diff 有回归测试；partial/denied observation 不会伪造 SourceRevision，historical `/date` 不会自动前移 current head。
- Provider adapter 验证 response course ID、release/version、洞号唯一连续、男女 par/handicap、provider tee index/name/gender/slope/rating；unknown/partial 输入 fail closed 并保留诊断。
- SourceManifest fixture 证明 semantic/auth query 分离、redirect chain 可审计，secret headers/query 不进入 receipt。
- A 账户私有 build 时，B 看不到 `ready/building/jobId`、不等待 A single-flight、不能命中 A raw/derived/cache；只有签名的 shared domain + `crossAccountShare=allowed` fixture 才可合流。
- A 下载 private asset 后，B 的普通 GET、`If-None-Match`、Range、redirect 和 proxy/browser-cache 请求都不能得到 A 的 hit/304/bytes/存在性差异；rights-cleared shared domain 才允许 public immutable cache 命中。
- 在 search/fetch/decrypt/derive/publish/serve/install-commit 每个阶段并发 revoke rights 或删除账户，旧 job 都不能前移 channel/暴露 ready/继续安装；允许保留的证据按新 policy quarantine，其余进入 purge。
- snapshot 已 ready 但 requested Watch profile 尚未构建时，顶层状态不是 `ready`；semantic/profile 两个 build key、job 和 channel generation 分开验证，style-only 构建不改变 snapshotId。

### 18.2 Deep Mine

- byte accounting 100% 分类；opaque 与 semantic decode 分开报告。
- protobuf unknown occurrence、JSON duplicate key、ZIP duplicate path、全部 Draco attributes 和 DSKIMG parse abort 有合成 fixtures。
- Lossless IR 对目标格式可重组或精确引用原始 byte slice。
- 新 structural fingerprint 自动进入 Unknown Registry。

### 18.3 Quality

- projection roundtrip、mirror/axis/unit/scale、NaN/outlier、hole order 和跨源 anchor tests。
- golden real-course overlays 覆盖版本、地区和稀有层。
- 每项 promoted capability 可输出 evidenceRef 和 quality report hash。
- 切换 provider tee 后，tee origin、洞长、路线、hazard/green distance、Watch map dependency 和所有 tee-dependent cache key 都改变；颜色同名不能合并不同 provider tee。
- 新 provider release/content hash 后，旧 topo URL/ETag 不命中；相同 semantic input hash + renderer/style 产生稳定输出，style-only 更新不改变 snapshotId。
- 水平 base distance、上坡/下坡/零高差和 target/ball elevation 符号有 golden fixtures；正 adjustment 增加 plays-like，负 adjustment 减少，任何端都不把 slant distance 或米值直接当码相加。

### 18.4 Install/offline

- Watch/iOS/Web 对同一 snapshot manifest 验证相同 identity。
- manifest self-ID/signature golden bytes 在 Python/Swift/TypeScript 完全一致；客户端对收到的 canonical bytes 验证，不靠重序列化碰巧相同。
- SnapshotGrant/CourseReleaseChannel/SafetyPolicy/PurgeDirective/TrustedTimeToken 的 SignedControlEnvelope 也有跨语言 golden bytes、keyId/algorithm substitution、跨 type signature 和低 generation replay 负例。
- 中断下载、duplicate/out-of-order chunk、range resume、磁盘不足、坏 hash、旧客户端和 commit-ACK 重试测试；ACK 只能在 required roster/assets 与 installed index 同一事务成功后返回。
- installer 五轴 truth table 覆盖 superseded 仍 rooted、uninstall_pending+pin、repair corrupt、rollback 重新 current、start-vs-uninstall CAS 和 complete-uninstall；任何组合的 ready/start/GC/reasonCode 三端一致。
- Watch **零本地缓存、iPhone 不可达**时，在真机完成 native auth/refresh → search → account-scoped build poll → direct download → verify → atomic install → start；随后关闭网络完成 9/18 洞。
- 同一设备/浏览器 A 账户已有 ready/install/staging 后切换到 B，B 看不到、不能 resume/activate A 的记录或解密其 private assets；只有 explicit shared asset domain 可物理复用，grant/install index 仍分别授权。
- trusted time 覆盖 wall-clock 回拨、异常快进、长期离线、重启、重装后 Keychain anchor 保留/丢失和更高 generation token 恢复；任何情况都不能复活过期 grant，且 activeRoundContinuation 与新 start 门分开验证。
- Watch 通过 iPhone relay 与 direct HTTPS 得到相同 manifest/assets；重复、乱序、切换 transport 和中途恢复不产生双安装或错误 commit。
- 同一 roundIntent 从 iOS relay 到 Watch 时两端使用不同 profile/installManifestId，但相同 RoundSemanticBinding/roundIncarnationId；任一端 manifest 与 snapshot/layout/tee 不兼容都只回滚该端 activation/pin。
- Web 在每个 Cache Storage/IndexedDB commit 边界强杀：重启后只能看到完整旧版本或完整新版本，不能出现 installed index 指向缺失 cache namespace。
- installer publish、uninstall、low-disk LRU、mark/sweep 和 PurgeDirective 并发 race 有 deterministic tests；mark 开始后新 commit 的 generation/lease 不被旧 sweep 删除，required display asset 在 installed 状态下始终存在。
- PurgeDirective 在“record 转 purge_pending、subtract roots、删除 bytes、移除 installed index、audit complete”每个边界强杀恢复，任何时刻都不暴露 installed + missing-required 的组合。
- Watch 安装完整 9/18 洞后关闭手机和网络，完成开局、18 洞记分、结束和重启恢复。
- iOS 在飞行模式从 installed registry 列场、开局、记分、强杀恢复、结束并保留待同步事件；开局路径不发网络请求。
- Web 被浏览器外部 eviction、quota clear 或单 namespace 丢失后，启动 scrub 必须把 Health/InstallRecord 标为 corrupt/absent 并阻止显示 installed/start；不能让 IndexedDB index 单独冒充完整包。
- indefinitely offline device 的 Purge 状态保持 device_pending；重连后在任何 start/unlock 前完成 purge 并 ACK。active/dirty/merged round 的账户删除覆盖 ledger、merge、media、sync/device refs，只留下非个人删除证明或显式 legal hold。

### 18.5 Runtime conformance

- 同一 golden event trace 在 Python/Swift reducer 得到相同 projection；TypeScript 对该 expected projection 做 generated decode、reason-code 和 view mapping conformance，不实现第三个业务 reducer。
- 重复、乱序、部分 ACK、纠错冲突、suspend/resume 和 mixed-client fixtures；未知 kind 返回 `accepted_opaque`、可保存/转发/重放，旧 Swift enum decoder 不崩溃。
- generated `streamSubject` 对 round-incarnation 与 merge-control event 做跨语言 encode/hash/replay/compaction；双 ID、空 ID 或 control event 塞入 round partition 一律拒绝。
- 模拟 batch 在第 N 个事件后崩溃并用相同 request key 重试，验证剩余事件补齐且已写事件不重复。
- 相同 event identity/相同 hash 返回 duplicate；相同 identity/不同 hash、相同 batch key/不同 body 都返回显式冲突且不覆盖 ledger。
- 四类终态/非终态 receipt 按表驱动 outbox：终态成功先持久化 receipt 再删除 transport item，deferred/缺 receipt 保留重试，permanent reject 原子进入 visible dead-letter；任一边界强杀不丢 event。
- set/supersede 的 absent、`unset`、允许的显式 `null` 和具体值跨语言一致，不被 Swift optional 或 JSON default 混淆。
- 两个离线 branch 拥有相同 canonicalOrdinal/显示 revision number、但 entityProjectionHash 或 contributingEventSetHash 不同，必须产生 conflict；不得发生 ABA 式错误 supersede。
- 同一离线 batch/乱序上传中先有 A、再有基于 provisional A 的 correction B；服务端拓扑接受 A 后把 B 映射到等价 canonical base，不因 provisionalFlag/ordinal 不同制造假冲突。
- 并发 ACK、future/gapped/regressing ACK、旧 ledger cursor、origin epoch 重置、ledger compaction 和 replay checkpoint 验证单调性；旧 epoch/cursor fail closed 并重新 bootstrap，不能回退或覆盖其他设备状态。
- compaction 后重传旧 accepted、accepted_opaque 和 rejected_permanent event，跨 epoch dedupe/tombstone 返回原终态或 compacted receipt，不产生新 position/投影副作用。
- 两台完全离线设备分别 start 的不同 round incarnation 同步后产生可恢复冲突；`RoundMergeResolution` 引用源 incarnation/checkpoint，merge/unmerge 不改写任一源 event。
- source 分支只要 snapshot、layout order（如 A→C/C→A）、teeSelection 或 LRP 任一不同，v1 merge 就 fail closed 并保留两条 ledger；不同 device profile manifest 但相同 RoundSemanticBinding 可以 merge。
- merge 后迟到 source event、iOS 离线深改、单一 source compaction 和 unmerge/supersede 分别推进正确 vector/mergeControlGeneration；旧单 cursor 收到 `bootstrap_required`，所有消费者从新 DeviceSyncBootstrap 恢复且 projection 一致。
- start 时 LRP/snapshot/layout/tee semantic binding 任一 ID/hash 不匹配，或本机 install manifest 与该 binding 不兼容，都原子失败，不产生本机 activation 或 pin。
- post-start known/opaque event 逐一篡改 owner/round/intent/incarnation/snapshot/RoundSemanticBindingHash 均返回 permanent `round_binding_mismatch`；合法未知 kind 才能 accepted_opaque。
- 离线并发 `ResolutionEpisode` 都保留为 provisional/conflict，显式 resolution 前不按到达顺序丢弃。
- SafetyPolicy generation 前进、回滚重放、capability reduction 和 PurgeDirective overlay 三端一致；旧合法 policy 不能重新启用能力。
- 米/码、角度、坐标、时间、finite number 和 canonical hash fixtures 在 Python/Swift/TypeScript 一致；专门覆盖 Watch 高差米值不得直接加到码数。
- 推荐与 actual club/shot 永远分离。
- Guidance 在风缺席、geometry degraded、GPS stale 和 capability blocked 时有一致结果。
- 同一 inputHash 的 local/cloud candidate set 以全部到达排列输入三端，GuidanceSelectionPolicy 都选择相同 candidateHash；完全并列时稳定 hash tie-break，不读取 arrival time。

## 19. 分阶段实施程序

本文件是 program architecture，不应生成一个巨型 implementation plan。实施必须拆成四份可独立验收的子计划。

### Phase 0：Authority 与漂移止血

在四条 track 扩展前先完成一个短门：

1. 将本文件、Watch 决策账本和 canonical contracts 声明为新实现的权威输入。
2. 禁止新增 weather/wind 消费者，并为 `weatherSnapshot` required、`_wind_adjustment_m` 和相关 UI 建立删除迁移。
3. 冻结 mutable gid/hole cache、第二套 Watch event 和“当前+下一洞即离线正确”的继续扩张。
4. 区分 history Garmin snapshot ID 与新的 CourseSnapshot ID，避免迁移期命名冲突。
5. 建立跨端 contract drift CI，确保新字段在 Python/Swift/TypeScript 中同时出现或显式 unsupported。
6. 修复 batch crash/retry 的整批 duplicate、ACK 回退和并发整文件覆盖；在这个门通过前，不把当前事件服务称为可靠同步基础。
7. 删除业务 ledger 中的 `sync_marker/hole=0`，统一 event identity 去重键，并修复 Watch direct mapper 与 phone bridge 对无效 payload 的不同处理。
8. 在迁移测试成立前禁止 `confirmFinish`、开始新局或缺 config 路径清除 pending events；旧 queue 必须可归属到原 round 并恢复。
9. 审计并暂时封闭所有未认证或跨账户共享的 topo、geometry、tee 和 course-prep 路径；只有 rights matrix 明确允许公开的 metadata 才可继续公共缓存/路由。
10. 修复 Watch 将 `elevationDeltaM` 直接加到码数的单位漂移；所有跨端 fixture 先以 SI 校验，再验证显示单位。
11. 合并 Watch 当前 `WatchSyncClient.currentState`、`WatchRoundModel.round` 及各自 pending queue 的双状态/双队列；先迁移为共享 Swift Domain ledger/outbox，再扩展 standalone 与 companion 行为，禁止只共享 DTO 却继续各写一份真相。
12. 删除固定 `live-<gid>` suggested round ID 和锁定该字符串的测试；相同 layout 连续 start 必须产生不同 roundId，重复同一 roundIntent 才幂等汇合。
13. 将 current `greenSlope` 输出和未消费 DTO 显式 quarantine；在 component/source/transform/baseGeometryHash/跨端 consumer 证据齐全前，三端统一报告 capability unavailable。

### Track A：Canonical contracts 与最小可靠球局

1. 冻结 CourseSnapshot/LRP/RoundEvent/LiveFacts/Guidance/Capability schema。
2. 建 contract registry、generated models 和 golden event traces。
3. 收敛 WatchInputEvent 双模型、finish/suspend、ACK/dead-letter。
4. 完成手动记分、手动一杆、恢复、离线结束、同步和 iOS 深编辑。

### Track B：Course Acquisition 与 Snapshot 安装

1. Provider search/identity/layout resolution。
2. Raw CAS、SourceManifest、parser registry 和 build queue。
3. Quality gate、snapshot builder 和 content-addressed assets。
4. Watch/iOS/Web installer、完整整轮包、pin/update/rollback/GC。

### Track C：Deep Mine Research Lab

1. Node Ledger、Lossless IR、Unknown Registry。
2. protobuf/JSON/archive/Draco/texture/DSKIMG 全 inventory。
3. corpus fingerprint、coverage、止损与 capture request generator。
4. 经过证据和 quality gate 的 capability promotion。

### Track D：体验与高级能力晋升

1. S70 行为对标的 Hole Root/Map Detail/Caddie layers。
2. verified elevation PlaysLike、hazard guidance 和宏观 green surface。
3. 玩家球杆校准、二维 dispersion 和 caddie chain。
4. AutoShot producer 在 canonical ledger 和手动恢复成立后接入。

依赖关系：

```text
Track A contracts ─────────────┐
                              ├─► Watch 最小可靠整轮
Track B snapshot/install ─────┘

Track C Deep Mine ──► promoted capabilities ──► Track D

Track C 不阻塞 A/B 的基础距离、地图和记分交付
```

## 20. 第一生产里程碑

第一里程碑不是“解析所有神秘字段”，也不是 AutoShot，而是：

```text
搜索一个真实球场
→ 构建并原子安装完整 CourseSnapshot
→ Watch 无手机开局
→ 手动成绩与手动一杆
→ 强杀恢复
→ 离线完成整轮
→ iOS/服务器同步
→ iOS 深度修改
→ 统计确定性重算
```

同时，Deep Mine 对同一原始包产生 byte closure、Unknown Registry 和可重放 evidence，但未知高级资产不阻塞该里程碑。

## 21. Program 级验收条件

只有同时满足以下条件，才能宣称这次“地图与三端统一”主线完成：

1. 当前 corpus 的 raw 和解析 coverage 可复现，所有未知显式登记。
2. 任一新球场可经过 search → acquire → gate → snapshot → install，失败也有明确状态。
3. Active round pin 精确 snapshot，更新、回滚和 GC 不会改变其静态事实。
4. Watch 安装完整整轮包后可离线完成整轮并可靠恢复。
5. Python/Swift reducer 对 golden event traces 的 projection 一致；TypeScript generated decoder/view 对同一 expected projection 一致。
6. Web/iOS/Watch 对 capability availability、缺席原因和降级显示一致。
7. Garmin token、ZIP key、签名 URL 和私有 raw 不进入客户端或跨账户共享路径。
8. 风从 v1 Guidance、LRP required、Watch readiness 和 carry calculation 完全退出。
9. 富 geometry、DSKIMG DEM/contour、green surface 等高级能力只有通过独立证据门才进入产品。
10. 现有用户数据、未同步事件和 dirty worktree 在迁移期间不被覆盖或静默丢失。

## 22. 当前无需 Owner 再决定的事项

- 风是否进入 v1：不进入，确定性修正现有漂移。
- Watch 是否依赖 iPhone：不依赖，iPhone 只作可选加速与深编辑。
- Deep Mine 是否阻塞主路径：不阻塞，能力逐项晋升。
- Provider raw 是否由 Watch 直接解析：不解析。
- 当前是否跨账户共享 Garmin-derived 资产：不共享；协议保留未来中央模式。
- 缺高级 geometry 是否阻塞基础球局：不阻塞，但必须诚实降级。
- 三端是否可维护三套业务事实：不可；必须共享 canonical contracts 和 conformance traces。

若未来要把中央共享目录正式商业化、重新加入实时风、加入推杆级果岭等高线，或公开分发 Garmin-derived 可逆资产，必须基于权利和证据重新提交 Owner 决策。

## 23. 权威与证据索引

- [Watch 决策与任务账本](../../reviews/2026-07-15-watch-decision-and-task-tracker.md)
- [全仓 Owner gate、权威与实现漂移审计](../../reviews/2026-07-16-repository-wide-owner-gate-authority-and-drift-audit.md)
- [S70 Virtual Caddie 与地图机制证据](../../reviews/2026-07-16-s70-virtual-caddie-and-map-mechanisms-evidence.md)
- [三端统一既有 Owner 来源规格](2026-07-02-unified-tri-surface-spec.md)
- [Garmin Course Data Reference](2026-07-02-garmin-course-data-reference.md)
- [Garmin 数据到功能的历史路线图](2026-07-03-garmin-data-to-features.md)

后四份文件保留历史证据和已批准来源，但若与本文件、Watch 决策账本或全仓权威审计冲突，以后者为准。
