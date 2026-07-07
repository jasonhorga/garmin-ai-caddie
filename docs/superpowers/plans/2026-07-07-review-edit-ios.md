# 复盘编辑界面 iOS 交互 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`).

**Goal:** 让 iOS 复盘满屏球道图能亲手加/改/拖/删每一杆(消费 #273 已上线的后端 op),做到干净、可靠、永不变砖。

**Architecture:** 现有 `RoundHoleShotMapScreen`(图 `RoundShotMapView` + 杆序列表 `shotListCard` + 横滑翻洞 `RoundShotMapPagerScreen`)上加一层**编辑态**。新增一个 `RoundEditModel`(`@Observable`)持有当前洞 shotmap 的可变副本 + 编辑开关,**乐观本地应用**每个操作(立刻画出来=「保存永远成功」手感)+ 后台 `SyncClient.postRoundCorrection` 落库 + 之后静默 refetch 对齐真值。手势层在满屏图上消歧:空白点=加杆、按住落点手柄=拖(带放大镜)、点落点/列表行=弹框改。

**Tech Stack:** SwiftUI(iOS 17,`@Observable`),Canvas 画杆,`ImageRenderer` 快照。后端 op 端点 `POST /api/v2/history/rounds/{ref}/corrections`。

## Global Constraints

- **iOS 只在 GitHub `native-mobile`(macOS `xcodebuild test` AICaddie+AICaddieWatch)编译验 + `DesignSnapshotTests`(ImageRenderer→`Documents/design-snapshots/*.png`→artifact)快照看**。**本地不编译**。所以本计划**整块实现→一个 PR→CI 编译+快照+契约→`gh run download` 看图迭代**,不是逐任务 CI-gate。
- **`tests/test_mobile_contracts.py`(在 backend CI `ci.yml` 里,grep iOS 源码断言控件)**:改控件要同步它。**iOS PR 必须同时看 `native-mobile` 和 `ci.yml(backend)` 两套检查**(memory 教训 #42)。
- **ImageRenderer 两坑**:① 不渲 `ScrollView` 内容(快照里滚动区空)→ 快照用不滚的 `VStack`/`Canvas`;② "填满容器的 `Path{}.fill()` 直接子视图"→ 返回 nil cgImage 渲不出 → 用 `Canvas` + 显式定尺。
- **真拖动手感要 TestFlight(用户已搁置)**——本计划只到 CI 编译+快照;手感验证 defer。
- **不造假**:缺球杆的杆,选杆器**默认高亮**按距离猜的那支但**不写死**,不点保持「未知」;推测不进球杆档案。
- **删除直接删,不问原因、不做撤销**(设计 §8)。**网页保持只读**,不动 web。
- 设计:`docs/superpowers/specs/2026-07-07-review-edit-ui-design.md`(funnel `/edit.html`)。

---

## File Structure

- **Modify** `mobile/ios/AICaddie/Models/RoundShotMap.swift` — `RoundShot` 加 `shotId`/`clubSource`/`lieSource`;`RoundHoleShotMap` 加 `manualPenalty`;`RoundShot.id` 用稳定 shotId。
- **Create** `mobile/ios/AICaddie/Models/RoundCorrection.swift` — 修改 op 载荷(`Encodable`,镜像后端 `RoundCorrectionRequest`)+ 构造 helper。
- **Modify** `mobile/ios/AICaddie/Services/SyncClient.swift` — 加 `postRoundCorrection`。
- **Create** `mobile/ios/AICaddie/Models/RoundEditModel.swift` — `@Observable` 编辑状态机 + 乐观本地应用 + 后台落库。
- **Create** `mobile/ios/AICaddie/Views/RoundShotEditComponents.swift` — 放大镜 loupe、改杆弹框(球杆/球位/删)、罚杆计数器、可重排列表行(表现型,快照可直渲)。
- **Modify** `mobile/ios/AICaddie/Views/RoundShotMapView.swift` — 编辑态 canvas(落点画拖动手柄)+ 手势层(空白点/按手柄拖/点杆)+ `RoundHoleShotMapScreen` 接编辑开关 + 锁横滑。
- **Modify** `mobile/ios/AICaddieTests/DesignSnapshotTests.swift` — 加编辑态快照(手柄、弹框、放大镜、罚杆条)。
- **Modify** `tests/test_mobile_contracts.py` — 断言新编辑控件在源码里。

---

## Task 1: 模型 — 稳定 shotId + provenance + 罚杆 + op 载荷

**Files:** Modify `Models/RoundShotMap.swift`;Create `Models/RoundCorrection.swift`

**Interfaces (Produces):**
- `RoundShot.shotId: String?`(解码后端 `"id"`)、`clubSource: String?`、`lieSource: String?`;`RoundShot.id: String { shotId ?? "o\(order ?? 0)" }`。
- `RoundHoleShotMap.manualPenalty: Int`(解码 `"manualPenalty"`,默认 0)。
- `RoundCorrectionOp: Encodable`(字段:`op:String`,可选 `shotId,hole:Int,field,value:AnyCodableValue,px:[Double],insertAfterShotId,order:[String],clientMutationId`);静态构造:`.delete(shotId)`、`.editClub(shotId,String)`、`.editLie(shotId,String)`、`.movePosition(shotId,px:[Double])`、`.addShot(px:[Double],club:String?,lie:String?,insertAfterShotId:String?)`、`.reorder([String])`、`.setPenalty(hole:Int,value:Int)`。`value` 用一个轻量 `AnyCodableValue` enum(`.string/.int/.doubles`)编码。

- [ ] **Step 1: RoundShot / RoundHoleShotMap 加字段**(改 `init(from:)` + memberwise init + CodingKeys)。`shotId` 解码 key `id`(后端每杆的稳定号,字符串如 `s:r1:201`);老的 `id: Int{order}` 换成 `public var id: String { shotId ?? "o\(order ?? 0)" }`(Identifiable 用它);`clubSource`/`lieSource` decodeIfPresent;`manualPenalty = (try? c.decodeIfPresent(Int.self, forKey:.manualPenalty)) ?? 0`。
- [ ] **Step 2: 新建 `RoundCorrection.swift`** —— `AnyCodableValue`(`enum{case string(String);case int(Int);case doubles([Double])}` + `encode`)+ `RoundCorrectionOp: Encodable`(只编码非 nil 字段,用 `encodeIfPresent`)+ 上述静态构造 + 每个带一个 `clientMutationId = UUID().uuidString`(幂等)。
- [ ] **Step 3: 快照/契约不涉及模型**(纯数据)—— 靠 CI 编译验;Step 提交。

```swift
// RoundCorrection.swift 关键形状
public enum AnyCodableValue: Encodable {
    case string(String), int(Int), doubles([Double])
    public func encode(to e: Encoder) throws {
        var c = e.singleValueContainer()
        switch self { case .string(let s): try c.encode(s); case .int(let i): try c.encode(i); case .doubles(let d): try c.encode(d) }
    }
}
public struct RoundCorrectionOp: Encodable {
    public let op: String
    public var shotId: String? = nil, field: String? = nil, insertAfterShotId: String? = nil, clientMutationId: String? = UUID().uuidString
    public var hole: Int? = nil
    public var value: AnyCodableValue? = nil
    public var px: [Double]? = nil
    public var order: [String]? = nil
    static func delete(_ id: String) -> Self { .init(op: "deleteShot", shotId: id) }
    static func editClub(_ id: String, _ v: String) -> Self { .init(op: "editField", shotId: id, field: "club", value: .string(v)) }
    static func editLie(_ id: String, _ v: String) -> Self { .init(op: "editField", shotId: id, field: "lie", value: .string(v)) }
    static func move(_ id: String, px: [Double]) -> Self { .init(op: "editField", shotId: id, field: "position", value: .doubles(px)) }
    static func add(px: [Double], club: String?, lie: String?, after: String?) -> Self { .init(op: "addShot", insertAfterShotId: after, value: nil, px: px) /* club/lie 见下:加 club/lie 字段 */ }
    static func reorder(_ ids: [String]) -> Self { .init(op: "reorderShot", order: ids) }
    static func setPenalty(hole: Int, _ v: Int) -> Self { .init(op: "setHolePenalty", hole: hole, value: .int(v)) }
}
```
> 注意:`addShot` 的 `club`/`lie` 后端读顶层字段(不是 `value`),给 `RoundCorrectionOp` 加 `club:String?`/`lie:String?` 两个可选顶层字段,`add(...)` 里填上。

**Commit:** `feat(复盘编辑iOS): 模型补稳定 shotId/provenance/罚杆 + 修改 op 载荷`

---

## Task 2: SyncClient.postRoundCorrection

**Files:** Modify `Services/SyncClient.swift`
**Interfaces:** `func postRoundCorrection(roundRef: String, _ op: RoundCorrectionOp) async throws`(POST 上述端点,201 即成功;非 2xx 抛 `SyncClientError`)。镜像已有 `fetchRoundShotMap` 的 URL/编码风格(`endpointURL`、`JSONEncoder`、鉴权 header)。

- [ ] **Step 1: 加方法**(照 `fetchRoundShotMap` 的样式:`endpointURL("/api/v2/history/rounds/\(encoded)/corrections")`,`httpMethod="POST"`,`httpBody = try JSONEncoder().encode(op)`,`Content-Type: application/json`,复用现有鉴权注入)。非 2xx → `throw SyncClientError...`(照现有错误类型)。
- [ ] **Step 2: 编译验(CI)+ 提交** `feat(复盘编辑iOS): SyncClient.postRoundCorrection`

---

## Task 3: RoundEditModel(编辑状态机 + 乐观本地应用)

**Files:** Create `Models/RoundEditModel.swift`
**Interfaces (Produces):** `@Observable final class RoundEditModel`:
- 状态:`var map: RoundHoleShotMap`(可变副本)、`var isEditing: Bool = false`、`var pendingError: String? = nil`、`var draggingShotId: String? = nil`。
- `init(map:, sync:, roundRef:)`。
- 方法(每个:**先本地改 `map.shots`/`manualPenalty`**,再 `Task { try? await sync.postRoundCorrection(...) }` 落库;失败设 `pendingError` 但**不回滚本地**(本地先落手感),下次 refetch 对齐):
  - `enterEdit()/exitEdit()`
  - `addShot(px:[Double], club:String?, lie:String?, afterShotId:String?)` — 本地在 `afterShotId` 之后插一个 `RoundShot(end:[px], club:club, lie:lie, order:…, synthetic:false, shotId: "local-\(UUID)")`;POST `.add(px:club:lie:after:)`;之后 `refetch()`(真 shotId 来自后端)。
  - `move(shotId:, px:[Double])` — 本地把该杆 `end = px`;POST `.move(shotId,px)`。
  - `editClub(shotId:, _:)`/`editLie(shotId:, _:)` — 本地覆盖 + 标 `clubSource/lieSource="manual"`;POST。
  - `delete(shotId:)` — 本地移除;POST `.delete`。**空洞不崩**(shots 可为空,图仍显示、可继续加)。
  - `reorder(_ ids:[String])` — 本地按 ids 重排 `shots`;POST `.reorder(ids)`。
  - `setPenalty(_ v:Int)` — 本地 `map.manualPenalty=v`;POST `.setPenalty(hole:map.hole,v)`。
  - `refetch()` — `map = try await sync.fetchRoundShotMap(...)`(静默对齐;失败保留本地)。

- [ ] **Step 1: 建类 + 全部方法**(乐观本地应用镜像后端语义:删=移除、改=覆盖、加=插序、重排=重排、罚杆=改数)。
- [ ] **Step 2: 编译验(CI)+ 提交** `feat(复盘编辑iOS): RoundEditModel 乐观本地应用 + 后台落库`

---

## Task 4: 手势层 + 编辑态 canvas(拖动手柄)

**Files:** Modify `Views/RoundShotMapView.swift`
**Interfaces:** `RoundShotMapView` 加 `editModel: RoundEditModel?`(nil=只读老行为)。编辑态:Canvas 在每个落点多画一个**拖动手柄**(小圆环);外层 `GeometryReader` 上挂手势,按落点像素↔视图坐标换算做**命中测试**消歧。

- [ ] **Step 1: 编辑态画手柄** — 编辑时,每个 `shot.end` 处画一个 14pt 直径的空心圆环(手柄),被 `draggingShotId` 选中的高亮。
- [ ] **Step 2: 手势消歧**(单指):`DragGesture(minimumDistance:0)`:
  - `.onChanged` 首帧:若起点落在某手柄命中半径(≈22pt)内 → 进入**拖模式**(`draggingShotId=该杆`),实时 `editModel.map` 里更新该杆 `end`(不发网络)+ 触发放大镜(Task 5);否则记为"可能是点击"。
  - `.onEnded`:若拖过阈值且在拖模式 → `editModel.move(shotId, px: 视图坐标→overlay像素)`;若几乎没动 → 视为**点击**:命中某落点 → 弹改杆框(Task 6);命中空白 → 弹加杆框(Task 6,起点=前一杆、px=点的位置)。
  - 换算:视图坐标 → overlay 像素 = `p / scale`(scale = 视图尺寸/overlay w,h,和现有 `draw` 里的 `sx,sy` 一致,反过来)。
- [ ] **Step 3: 快照** — `DesignSnapshotTests` 渲一张"编辑态带手柄"(seeded map + editModel.isEditing=true),名 `review-edit-handles`。
- [ ] **Step 4: 提交** `feat(复盘编辑iOS): 满屏编辑手势(空白加/按手柄拖/点杆改)+ 手柄`

---

## Task 5: 放大镜 loupe

**Files:** Create/extend `Views/RoundShotEditComponents.swift`
**Interfaces:** `MagnifierLoupe`:给定底图 `Image`(topo)、当前拖动点(视图坐标)、放大倍数,渲一个**圆形放大视图浮在手指上方**(offset -80pt),显示手指下方区域的放大 + 中心十字。

- [ ] **Step 1: 建 `MagnifierLoupe` 视图**(`Canvas` 或 `Image` + `.mask(Circle())` + scaleEffect + offset;定尺 100pt 圆;ImageRenderer 友好=不用 ScrollView)。
- [ ] **Step 2: 接进 Task 4 的拖模式**(`draggingShotId != nil` 时叠加显示,跟随手指)。
- [ ] **Step 3: 快照** `review-edit-magnifier`。**Step 4: 提交** `feat(复盘编辑iOS): 拖动放大镜 loupe`

---

## Task 6: 改杆弹框(球杆/球位/删)+ 加杆弹框

**Files:** extend `Views/RoundShotEditComponents.swift`
**Interfaces:** `ShotEditSheet`(改已有杆:球杆 picker + 球位 picker + 「删除本杆」)、`AddShotSheet`(加杆:球杆 picker **默认高亮**按距离猜的那支 + 球位 picker;确认=回调 `(club,lie)`)。球杆列表来自玩家球包(复用现有球包来源;缺则给常见杆),缺球杆默认高亮距离猜测那支但**不预选写死**(用户不动=nil)。

- [ ] **Step 1: `ShotEditSheet`** — `.sheet`;球杆 `Picker`(含「未知」项)、球位 `Picker`(球道/长草/沙坑/水/果岭/…用 `shotLieLabel` 现有映射)、`Button("删除本杆", role:.destructive)`;回调 `editModel.editClub/editLie/delete`。
- [ ] **Step 2: `AddShotSheet`** — 同上但含"推荐球杆"高亮(按 `distanceGuessClub(yards)`,yards 由 px 距离×ppm 估);确认回调 `editModel.addShot`。
- [ ] **Step 3: `distanceGuessClub`** 放 `RoundEditModel` 或工具:按玩家各杆距离分布选最近的一支(**只做默认高亮,不写库**)。
- [ ] **Step 4: 快照** `review-edit-sheet`(渲 ShotEditSheet 内容为独立视图)。**Step 5: 提交** `feat(复盘编辑iOS): 改杆/加杆弹框(球位/球杆+推荐高亮,直接删)`

---

## Task 7: 落点列表手动重排 + 罚杆计数器

**Files:** Modify `Views/RoundShotMapView.swift`(`shotListCard`)、extend components
**Interfaces:** 编辑态的 `shotListCard` 用 `List{...}.onMove` 支持拖动重排(→ `editModel.reorder(新顺序的 shotId 数组)`);每洞 `PenaltyStepper`(`罚杆 - N +`)→ `editModel.setPenalty`。

- [ ] **Step 1: 列表重排** — 编辑态 `ForEach(map.shots){...}.onMove{ from,to in 本地重排→收集 shotId 顺序→editModel.reorder }`。(注:重排列表要 `List`+`.onMove`,快照里 List 内容 ImageRenderer 可能不渲 → 重排 UI 的快照用一个静态表现型行堆;真交互 TestFlight 验。)
- [ ] **Step 2: `PenaltyStepper`** — `HStack{ "本洞罚杆" ; Button("-") ; Text(manualPenalty) ; Button("+") }` → `editModel.setPenalty`。定尺、非 ScrollView。
- [ ] **Step 3: 快照** `review-edit-penalty`。**Step 4: 提交** `feat(复盘编辑iOS): 落点列表重排 + 罚杆计数器`

---

## Task 8: 接进 RoundHoleShotMapScreen(编辑开关 + 锁横滑)

**Files:** Modify `Views/RoundShotMapView.swift`(`RoundHoleShotMapScreen`/`RoundShotMapPagerScreen`)
**Interfaces:** `RoundHoleShotMapScreen` 持一个 `RoundEditModel`;顶部「编辑/完成」切 `isEditing`;`isEditing` 时把 `RoundShotMapView(editModel:)` 接活 + 显示 PenaltyStepper + 列表切重排态;`RoundShotMapPagerScreen` 在 `isEditing` 时 `.disabled` 分页(锁横滑翻洞,设计 §1)。

- [ ] **Step 1: 接线** — screen 建 `@State editModel`;`load()` 后 `editModel.map = 拉到的 shotmap`;工具栏「编辑」按钮 toggle;编辑态渲 editModel-driven 视图。
- [ ] **Step 2: 锁横滑** — pager 在任一洞编辑态时禁分页(用一个 `@Binding editingLock`)。
- [ ] **Step 3: 快照** `review-edit-screen`(整屏编辑态)。**Step 4: 提交** `feat(复盘编辑iOS): 复盘屏接编辑开关 + 编辑时锁横滑翻洞`

---

## Task 9: 快照汇总 + mobile 契约

**Files:** Modify `AICaddieTests/DesignSnapshotTests.swift`、`tests/test_mobile_contracts.py`
- [ ] **Step 1: DesignSnapshotTests** 确保 Task 4–8 的 5 张快照(handles/magnifier/sheet/penalty/screen)都用 seeded `RoundHoleShotMap` 渲(不依赖网络;topo 底图用 `fallback`/纯色,ImageRenderer 不渲网络图)。
- [ ] **Step 2: test_mobile_contracts.py** 加一个 `RoundEditContractTests`:`_read_required_source(RoundShotMapView.swift)` 断言含 `"RoundEditModel"`、`"编辑"`、`ShotEditSheet`、`PenaltyStepper`、`postRoundCorrection`(读 SyncClient.swift);`RoundCorrection.swift` 含 `addShot`/`reorderShot`/`editField`。守 iOS 接线不被后续删。
- [ ] **Step 3: 提交** `test(复盘编辑iOS): 编辑态快照 + mobile 契约断言`

---

## 验证(整块 → 一个 PR → 两套 CI → 看图)

1. 全部实现 + 提交后开 PR 进 integration/v2。
2. 盯 **`native-mobile`**(编译 AICaddie+AICaddieWatch + 跑快照)**和 `ci.yml` backend**(`test_mobile_contracts`)**两套**。native-mobile Watch 模拟器偶发 flaky → `gh run rerun <id> --failed`。
3. `gh run download <runId> -n design-snapshots` 下载 `review-edit-*.png` **肉眼看**:手柄/放大镜/弹框/罚杆条/整屏编辑态是否贴 `/edit.html` 设计。丑就迭代。
4. 两套绿 + 快照 OK → 合并。**真拖动手感 defer 到 TestFlight(用户已搁置)。**

## Self-Review(对着设计核)

- §1 两模式/满屏图 → Task 8(编辑开关)+ Task 4(编辑态 canvas)✓;锁横滑 → Task 8 ✓。
- §2 手势(空白点加/按手柄拖/点杆改)→ Task 4 ✓。
- §3 加杆+自动连线 → Task 3 addShot(本地插序,Canvas 按序画线自动连)+ Task 6 加杆框 ✓;位置由点的像素 → Task 4 换算 ✓。
- §4 弹框选杆/球位+默认值 → Task 6 ✓。§5 拖动+放大镜 → Task 4+5 ✓。
- §6 列表+重排 → Task 7 ✓。§7 缺杆默认高亮不写死 → Task 6 Step 3 ✓(守不造假)。
- §8 直接删不问因不撤销 → Task 3 delete + Task 6 删除按钮 ✓(无 reason/无 undo)。
- §9 罚杆计数器 → Task 7 ✓;永不变砖 → Task 3 delete 允许空洞 + Task 4 空白加杆 ✓;网页只读 → 不动 web ✓;保存本地先落 → Task 3 乐观应用 ✓。
- **占位扫描**:各 Task 有关键 code + 明确接口;SwiftUI 细节(boilerplate)由实现时补,难点(手势消歧/放大镜/乐观应用/op 载荷)已给码。**类型一致**:`RoundCorrectionOp`/`RoundEditModel` 方法名跨 Task 一致;`shotId:String` 全程字符串。
- **iOS 现实**:逐任务无本地测试步(iOS 不本地编译)——每 Task 的"验证"= CI 编译 + 该组件的快照/契约;整体一个 PR 过两套 CI。这是刻意的,不是占位。
