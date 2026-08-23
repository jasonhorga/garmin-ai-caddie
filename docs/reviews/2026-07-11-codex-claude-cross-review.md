# Codex × Claude Code Fable Max 全仓交叉审查

> 审查日期：2026-07-11 UTC
> 代码基线：本地 `integration/v2` @ `a0c0fca`
> 远端对照：`origin/integration/v2` @ `b5e17d3`，本地落后 46 个提交
> Codex 主报告：[2026-07-11-full-repository-review.md](2026-07-11-full-repository-review.md)
> Claude 原始独立报告：[2026-07-11-claude-fable-max-independent-review.md](2026-07-11-claude-fable-max-independent-review.md)
> 结论：两轮独立审查均判定当前版本 **NOT READY**；Claude 对主要 blocker 提供了独立佐证，并额外暴露了若干真实问题，但它不能替代 Codex 主报告。

---

## 1. 最终结论

这次让 Claude Code 重做一遍是有价值的。它没有推翻第一轮审查，反而在最重要的方向上形成了高一致性：

1. Release IPA 携带全局管理员令牌。
2. iPhone、Watch、Web 都存在记分生命周期丢数据路径。
3. Render、备份、GitHub Actions 和 CI 门禁不足以支撑扩大试用。
4. 中文 AI 叙述的事实绑定并不可靠。
5. 跨端契约缺乏真正的前向兼容策略。

Claude 还带来了 8 类值得处理的新增或扩展发现。其中：

- 5 类经本轮动态或完整数据流核验后直接确认；
- 2 类问题成立，但 Claude 对影响范围表述过宽；
- 1 类属于现有 AI 事实绑定问题的放大器，而不是独立的越权漏洞。

综合判断仍然是：

- 暂停扩大 TestFlight 和外部家庭成员。
- 立即处理真实 IPA 中的管理员令牌。
- 第一优先级仍是“一杆都不能丢”和“结束球局不能删除记录”。
- Claude 新发现中的 `addShot` 丢字段、9+9 差值污染、事件枚举版本阻塞和开放注册资源滥用，应进入第一批整改。
- Claude 报告不应单独作为发布依据，因为它没有获得任何动态测试权限，并漏掉了 Codex 已确定性复现的多项高风险问题。

---

## 2. Claude Code 实际执行情况

### 2.1 请求配置

调用的是本机 Claude Code 2.1.207，启动参数为：

```text
claude --print --model fable --effort max
```

同时采用严格只读约束：

- safe mode；
- permission mode 为 `dontAsk`；
- 禁止 Edit/Write、Git mutation 和外部写操作；
- 禁止读取 Codex 主报告与历史 review；
- 禁止读取或打印真实 token、cookie 和私有数据。

主会话 ID：

```text
3b5153c3-c15e-40a1-8c6d-2648ea2ad53d
```

会话从 14:01:57 运行到 14:41:41，约 39 分 45 秒。Claude 使用了 8 个主领域子代理，AI/几何代理又拆出 2 个二级代理。CLI 使用估算约为 165 美元。

### 2.2 模型透明度

这不是一份“纯 Fable”报告。

虽然 CLI 确实以 `--model fable --effort max` 启动，但 Claude Code 自动进行了模型 fallback：

- 主会话日志有 94 条 `claude-fable-5` assistant 记录；
- 有 177 条 `claude-opus-4-8` assistant 记录；
- 两段最终长篇综合输出均由 `claude-opus-4-8` 生成；
- 部分子调用还记录了 `claude-opus-4-8[1m]` 变体。

因此准确描述是：**Fable Max 配置启动、Fable 与 Opus 混合执行、最终综合由 fallback Opus 完成。**

### 2.3 独立性核验

主会话工具调用中没有打开以下文件：

- `docs/reviews/2026-07-11-full-repository-review.md`
- `docs/CODE_REVIEW_FINDINGS.md`

仅有的相关路径出现，是在 Git diff 命令中作为明确排除项，或在子代理提示中作为禁读规则。

Claude 没有修改仓库、Git、GitHub、部署、TestFlight 或凭据状态。

### 2.4 动态验证限制

Claude 的 Python、npm 和测试执行均被 `dontAsk` 权限拒绝。因此 Claude 报告里的问题证据主要是：

- static-inference；
- test-evidence，即阅读测试源码；
- 跨文件数据流核验。

Claude 没有权利声称“测试全绿”，它也明确没有这样声称。

Codex 随后对 Claude 新发现进行了动态补充验证，并运行了 43 个相关既有测试：

```text
Ran 43 tests in 11.466s
OK
```

这些测试全部通过，但恰好说明现有测试没有覆盖新发现的真实边界，而不是说明问题不存在。

---

## 3. 两轮审查的高一致性结论

| 领域 | Codex 结论 | Claude 结论 | 交叉判断 |
|---|---|---|---|
| Release IPA 管理员令牌 | 真实 artifact 外部实测，P0 | 静态全链路确认，唯一 P0 | 已确认安全事故，立即轮换和撤销 |
| iOS sync marker 竞态 | 确定性代码路径与测试分析，P0 | P1-1 | 同一根因，仅严重度标尺不同 |
| Watch 无配置结束清空 pending | P0 | P1-2 | 完全一致 |
| iPhone “结束本场”实际 discard | P0 | P1-3 | 完全一致 |
| Web 记分仅 React 内存 | P1 | P1-4 | 完全一致 |
| Render 不跑 Alembic | P1 | P2-a | 完全一致，严重度不同 |
| snapshot 包含成员 Garmin cookie | 实测，P0 | P2-b | 完全一致，Codex 有动态归档证据 |
| mutable GitHub Action 标签 | P1 | P1-8 | 完全一致 |
| Watch 米/码混用 | P1 | P2-l | 完全一致 |
| 中文 fact binding 失效 | 动态复现，P1 | 最终上调 P1-9 | 完全一致 |
| 契约/schema 漂移 | 多项 P2 | P2-k | 高度一致 |
| CI/测试假绿 | 多项 P1/P2/P3 | P2-e/m 与测试清单 | 高度一致 |
| 备份无调度、同卷、无恢复演练 | P1/P2 | P2-o | 完全一致 |
| 非原子文件存储 | P0/P2 多项动态复现 | P2-f 与补充清单 | 根因一致，Codex 证据更强 |

严重度数字不能直接比较。Codex 把“已确认永久数据丢失”和“核心主流程阻断”也列为 P0；Claude 只把当前可外部取得的全局凭据泄漏列为 P0。因此 `8 P0 vs 1 P0` 主要是分级规则差异，不是事实分歧。

---

## 4. Claude 新发现的二次核验

### XR-01 — P1：`addShot` 的初始 `club/lie` 被服务端静默丢弃

**结论：确认。**

数据流：

1. iOS `RoundCorrectionOp.add` 编码 `club` 和 `lie`：
   [RoundCorrection.swift](../../mobile/ios/AICaddie/Models/RoundCorrection.swift)，第 23–72、87–89 行。
2. 服务端 `RoundCorrectionRequest` 没有这两个字段，且 Pydantic 默认忽略 extra：
   [models.py](../../server_v2/models.py)，第 474–486 行。
3. 路由只把 `body.model_dump()` 交给存储层：
   [main.py](../../server_v2/main.py)，第 530–547 行。
4. shot map 读侧却期待事件中存在 `club/lie`：
   [round_shot_map.py](../../ai_caddie/rounds/round_shot_map.py)，第 124–150 行。

最小复现：

```text
club_preserved = False
lie_preserved  = False
```

影响范围需准确表述：

- 只影响“新增一杆时填写的初始球杆和球位”；
- `editField club/lie` 使用 `field/value`，不受此缺字段影响；
- 落点、顺序和原始 Garmin 数据仍在；
- POST 返回成功后 refetch 会用空值覆盖 iOS 乐观 UI。

测试缺口：

- `tests/test_corrections_api_ops.py` 明明发送了 `club/lie`，却没有断言它们被保存；
- shot map 测试直接注入带字段的 correction dict，绕过 Pydantic 边界；
- 缺 POST → 持久化 → refetch 的端到端测试。

远端 46 个提交后的模型仍缺这两个字段。

### XR-02 — P1：同日 9+9 合并污染通用 differential，但 handicap estimate 已有保护

**结论：问题确认，Claude 的“所有差值统计”表述过宽。**

根因：

- 九洞原始局读取 `teeBoxRating/teeBoxSlope`：
  [history.py](../../ai_caddie/history/history.py)，第 282–283 行。
- `merge_same_day_halves` 以 `{**front}` 为基底，合并后没有清空或重算 rating/slope：
  同文件第 342–395 行。
- 通用 `_round_differential` 没有 18 洞 rating 合理性检查：
  [history_stats.py](../../ai_caddie/history/history_stats.py)，第 248–254 行。

实际影响：

- summary 的 average/best/recent differential；
- difficulty-adjusted 聚合；
- 年、季、月时间序列；
- course recent form；
- improvement 和部分报告事实；
- rating/slope 数据质量覆盖。

不受影响或已有缓解：

- `_round_differential_or_par` 对 rating < 50 回退 score-par；
- `handicapEstimate` 和 `handicapTrend` 使用该安全入口。

示例：

```text
18-hole score       = 91
18-hole par         = 72
retained rating     = 35.2
generic differential = 55.8   # 错
handicap input        = 19.0   # 已回退，正确
```

现有测试只锁住 handicap fallback，没有走真实 9+9 merge → summary/course/report 链路。

### XR-03 — P1：`geometry_evidence` 与真实几何产物 schema 断裂

**结论：确认。**

读侧只识别：

```text
polygon | points | path
```

位置：

- [geometry_evidence.py](../../ai_caddie/geometry/geometry_evidence.py)，第 165–171、276–297、489–491、544–546、608–635 行。

真实写侧却产生：

- hazard：`centroid`、`bbox`、`tee_distances`，无 polygon：
  [export_prodgeometry_hazards.py](../../ai_caddie/geometry/export_prodgeometry_hazards.py)，第 96–142 行。
- mesh：`positions` 和 `faces`，无 polygon：
  [decode_courseview_geometry.js](../../ai_caddie/geometry/decode_courseview_geometry.js)，第 108–148、207–219 行。

使用 canonical writer 形状的最小复现结果：

```text
surface = unknown
missingData = surface_match
```

受影响：

- `classify_shot_surface`；
- 手工球局从几何推导 GIR/fairway；
- geometry map API 的 hazard/surface features；
- caddie route evidence 的 avoid zones、intersection 和 clearance。

不受影响：

- 主线复盘分析中直接使用 triangle mesh 的路径；
- course prep/topo/watch 中直接使用 `positions/faces` 的路径。

这是生产数据形状与测试 fixture 形状不一致的问题。现有几何测试全部合成了真实管线从不产出的 polygon。

### XR-04 — 条件 P1 / 默认 P2：媒体保留 EXIF GPS，并可能原样发送给视觉模型

**结论：确认。**

链路：

1. iOS 读取并 base64 编码原始媒体字节，没有重编码或剥离元数据：
   [MediaCaptureView.swift](../../mobile/ios/AICaddie/Views/MediaCaptureView.swift)，第 97–153 行。
2. 后端原样解码、原样写盘：
   [media.py](../../ai_caddie/core/media.py)，第 149–183 行。
3. vision 读取前 1 MB 原始字节并构造成 `LLMMediaPart`：
   [vision_context.py](../../ai_caddie/llm/vision_context.py)，第 29、144–164 行。
4. NVIDIA/Gemini 外部 provider 路径会把这些原始字节发出。

最小复现：

```text
stored_identical          = True
provider_bytes_identical  = True
exif_marker_present       = True
```

缓解条件：

- 需要已认证玩家；
- 文件按玩家隔离；
- 单个照片 12 MB、视频 80 MB；
- vision 只发送前 1 MB；
- `privacyState=redacted` 不发送；
- 默认 static provider 不产生外部网络传输。

但默认 `private_local` 并不阻止外发。开启外部多模态 provider 时，这是精确位置隐私问题；未开启时仍是 at-rest 元数据保留问题。

### XR-05 — P1：Swift 封闭枚举导致真实跨版本 head-of-line blocking

**结论：确认。**

封闭枚举：

- [LiveRoundEvent.swift](../../mobile/ios/AICaddie/Models/LiveRoundEvent.swift)，第 3–13 行；
- [WatchEventBridge.swift](../../mobile/ios/AICaddie/Services/WatchEventBridge.swift)，第 4–10 行；
- [WatchSyncClient.swift](../../mobile/ios/AICaddieWatch/Services/WatchSyncClient.swift)，第 6–12 行。

远端已经实际新增 `.fairway`，但没有通用 unknown fallback，因此风险不是理论上的。

三种版本组合：

1. **新 Watch → 旧手机**：旧手机解码失败，Watch 事件重新入队并持续重试。
2. **新客户端 → 旧服务端**：一个未知 kind 使整个 batch 在 Pydantic Literal 校验阶段 422。
3. **旧 iOS → 新服务端 replay**：一个未知 kind 使整个 replay page 解码失败；调用方 `try?` 后直接返回，cursor 不推进，后续所有事件被该条未知事件永久挡住。

动态服务端复现：

```text
batch_rejected   = True
first_error_type = literal_error
loc              = ('events', 0, 'kind')
```

范围修正：

- iOS 本地 JSONL 是逐行解码，未知行会被跳过，不会摧毁整份日志；
- Watch 队列是整个数组一次性解码，版本降级时可能整队列不可读；
- 新 Watch → 旧手机场景首先表现为事件滞留，不是立即删除。

需要的修复不是仅补 `.fairway`，而是协议级 unknown case、逐项 accept/reject、replay 跳过未知事件和明确的服务端先行发布纪律。

### XR-06 — P2：未隔离的自由文本可以注入 report/caddie narrative

**结论：部分确认，属于同租户叙述完整性问题，不是跨租户越权。**

可控文本来源包括：

- 手工 course name；
- manual notes；
- vision `evidenceText`。

这些文本只经过 secret/path redaction，没有被标记为“不可信数据”，随后被 JSON 序列化进 report 或 caddie explanation prompt。

本地 capture provider 验证：

```text
caddie_prompt_contains_injection = True
report_prompt_contains_injection = True
```

结合中文 fact binding 漏洞，注入后的中文虚构建议仍可能得到：

```text
factBinding.state = bound
unsupportedClaimCount = 0
```

范围和缓解：

- 路由需要认证并按玩家隔离；
- note evidence 截断为 180 字、最多三条；
- report 中 vision finding 必须 manual-confirmed；
- 没有 provider tool execution；
- 确定性的球杆/路线选择在 LLM 解释前已经完成；
- 主要影响是调用者自己的 narrative，而不是读取其他用户数据。

因此建议把它作为现有 P1-AI-01 的放大器和独立 P2 trust-boundary 问题，而不是新的 P0/P1 越权漏洞。

### XR-07 — P1：开放 Apple 自助注册、无配额与无界重活线程形成资源耗尽链

**结论：确认，受部署配置影响。**

入口：

- 任何 audience 正确、签名有效的首次 Apple subject 都会自动加入 owner family；
- 没有邀请、审批、成员 allowlist 或家庭人数上限：
  [auth_api.py](../../server_v2/auth_api.py)，第 107–165 行。

可滥用资源：

- 每次媒体上传生成新 UUID 文件，无累计空间 quota；
- 同一媒体可以重复 analyze，重复调用 vision provider；
- report generate 每次都可调用 provider 并写新记录；
- caddie explanation 默认开启，可重复调用 provider；
- 无应用层 rate limit、用户配额或费用预算。

直接线程放大链：

1. 成员提交自己的手工球局；
2. ingest 使全局 stats cache 失效；
3. 每个请求都创建新的 daemon thread：
   [main.py](../../server_v2/main.py)，第 471–497 行。
4. 每个线程可能下载/解码几何、渲染 topo 并重建三组 stats cache：
   同文件第 746–777 行。
5. 冷 build 在 cache lock 外执行，多个线程可以重复计算。

最小模拟：

```text
requests = 25
thread_starts = 25
thread_name = prepare-recent-ingest
```

缓解条件：

- 需要有效 Apple 身份，不是匿名注册；
- Apple auth 未配置时返回 503；
- 默认 static LLM 不产生外部账单；
- 单文件大小有上限；
- Garmin sync 和同洞 geometry 有锁，但不能限制 ingest 创建线程。

在扩大 TestFlight 前，应加入邀请/审批、家庭上限、rate limit、媒体累计 quota、LLM 调用预算，以及 single-flight/有界线程池。

### XR-08 — P2 契约语义 / 当前低影响：`greenSlope.directionDeg` 不是所声明的 topo bearing

**结论：数学和命名问题确认；当前用户影响被 Claude 说重了。**

[elevation.py](../../ai_caddie/geometry/elevation.py) 第 113–141 行中：

- 地面坐标是 `(gx, gy)=(-x, z)`，即未旋转的 east/north 局部帧；
- `atan2(-b, -a)` 产生从 east 轴逆时针的数学角；
- docstring 却称其为 hole/topo frame 的 bearing。

而 [hole_render.py](../../ai_caddie/geometry/hole_render.py) 第 65–98 行会把球洞旋转到 tee → green 轴，因此不能直接把这个值画在 topo 图上，也不能直接当 compass bearing。

范围修正：

- 当前 HEAD 的 Web/iOS/Watch 没有实际消费该方向字段；
- 因此这是潜伏的契约语义陷阱，不是当前已展示的错误箭头；
- 远端已加入一层 screen-space 转换，但转换失败时仍可能保留原始地面帧值，应在远端合并前继续验证。

现有 `test_elevation.py` 只证明数值符合当前数学约定，没有证明该约定符合字段名和客户端坐标系。

---

## 5. Claude 报告中需要纠正或收窄的表述

### 5.1 “stats cache 严谨且分玩家”不完整

Claude 报告把 stats cache 列为无跨玩家污染的强项。主键和基础球局指纹确实按 player 分区，但成员辅助证据仍错误检查 owner 根路径。

Codex 已动态复现：

- 修改成员 annotation 后；
- 第二次调用仍直接命中旧 cache；
- build 次数保持 1。

因此更准确的说法是：**主 cache key 分玩家，但 annotation/weather/report/audit 的成员失效逻辑有缺口。**

对应 Codex 主报告 P1-BE-04。

### 5.2 “unsupported claim 会走 deterministic fallback”不成立

Claude 强项部分写到报告发现 unsupported claim 后会降 confidence 并走确定性兜底。

实际代码只会：

- 设置 `factBinding.state=needs_review`；
- 将 confidence 降为 low；
- 仍原样返回并持久化 provider narrative。

最小复现：

```text
state               = needs_review
confidence          = low
narrative_unchanged = True
provider            = original provider
```

因此 Codex 主报告要求“检测到 unsupported claim 后 fail closed、替换为 deterministic narrative”仍然成立。

### 5.3 “9+9 污染所有差值”需收窄

通用 differential、趋势、课程和报告数据会被污染，但 handicap estimate/trend 已有 rating < 50 的回退保护。

### 5.4 “green slope 已产生用户可见错误”需收窄

HEAD 当前没有消费方向字段。问题是未来客户端和远端新代码的坐标契约陷阱，而不是当前 HEAD 已显示错误箭头。

### 5.5 Claude 的测试限制不能覆盖 Codex 的动态证据

Claude 无法运行测试不代表测试失败，也不能推翻 Codex 已完成的：

- IPA artifact 实测；
- snapshot secret 泄漏复现；
- fresh SQLite health 假绿复现；
- ingest/correction/ACK/atomic write 并发复现；
- stats cache 失效复现；
- Python/Web 构建和依赖审计。

---

## 6. Codex 找到、Claude 最终综合未充分覆盖的高风险问题

Claude 的最终报告很长，但仍遗漏或弱化了多个 Codex 已确认问题。最重要的包括：

1. **长期玩家/admin bearer 驻留 URL**，进入历史、日志和截图。
2. **iPhone 在 replay 前 ACK 全局序列**，可永久漏掉 Watch/Web 事件。
3. **round ingest、correction、ACK、player registry 的并发事务缺失**。
4. **通用 atomic write 同进程双线程使用相同临时文件名**。
5. **Garmin detail 失败被吞掉但 connector 仍发布 ready**。
6. **completed 球局和 `_no_data` shot 永久不刷新**。
7. **成员辅助 evidence 不使 stats cache 失效**。
8. **备份遗漏 SQLite/PostgreSQL 身份、ACL、session 和 owner 状态**。
9. **fresh Fly/Render 部署缺 Apple audience/identity seed，Release 无法登录**。
10. **Web Apple 登录、自助 Garmin bind、球包跨玩家状态和 session logout 契约问题**。
11. **WatchConnectivity 快照乱序、quick input 非 write-ahead 和手机 replay/投影顺序问题**。
12. **默认分支无 push CI、无 branch protection、无 protected environment**。

这也是为什么 Claude 独立报告应作为增量审查，而不是取代 Codex 主报告。

---

## 7. 合并后的整改优先级

### 7.1 0–72 小时

1. 轮换 `AI_CADDIE_ADMIN_TOKEN`。
2. 删除受影响 IPA artifacts，停止受影响 TestFlight build 继续分发。
3. 从 Info.plist、Fastlane 和 workflow 完全移除 admin token。
4. 修复 iOS sync marker 竞态、ACK/replay 顺序和真正的“保存并结束”。
5. 修复 Watch no-config finish 清空 pending。
6. Web 进行中球局持久化到 localStorage/IndexedDB。
7. 暂时关闭开放自助注册，或立即加 allowlist/invite。
8. 所有 secret-bearing Actions 固定完整 commit SHA。

### 7.2 第一周

1. 给 `RoundCorrectionRequest` 增加 `club/lie`，并加完整 round-trip 测试。
2. 9+9 merge 清空/重算 rating/slope；通用 differential 也加合理性守卫。
3. 枚举引入 unknown fallback，服务端改逐事件 accept/reject。
4. 让 `geometry_evidence` 消费 canonical `positions/faces`，不要让测试继续使用虚构 polygon schema。
5. 图片上传时重编码并剥离 EXIF；发送 provider 前再做一次元数据剥离。
6. Render 使用正式 entrypoint、Alembic 和持久数据库。
7. 修复 snapshot secret-free 与完整身份数据库备份。

### 7.3 第二至四周

1. 文件型核心写入迁入数据库事务，或统一跨进程锁和 crash-safe 原子提交。
2. 注册改成邀请/审批制，增加家庭人数上限。
3. 加 rate limit、媒体累计空间 quota、LLM 每用户预算和告警。
4. daemon thread 改为有界 executor + single-flight + 去抖。
5. 自由文本明确标记为 untrusted data；LLM 输出改结构化 claim + fact ID。
6. 修复 stats cache 的成员辅助证据指纹。
7. 统一 Web/iOS/Watch/Backend/JSON Schema 的版本协商与契约测试。

---

## 8. 新增验收测试清单

- `addShot` POST 后 stored correction 和 refetched shot map 均保留 `club/lie`。
- 真实两个九洞输入经过 merge 后，所有 differential consumer 都得到合理值。
- 用 canonical writer 的 `positions/faces` 和 `centroid/bbox` fixture 测 geometry evidence。
- 上传含 GPS EXIF 的 JPEG 后，落盘和 provider payload 都不含 GPS/设备元数据。
- 旧 iOS 解码含未来 kind 的 replay 时跳过未知项并继续推进 cursor。
- 新 Watch 向旧手机发送未来 kind 时得到带 eventId/reason 的明确拒绝。
- 混合 batch 中未知事件被逐项拒绝，已知事件仍能提交。
- 未受邀请的 Apple subject 不能自动加入 family。
- 同一成员的 rate、媒体空间和 LLM 预算达到上限后稳定返回 429/配额错误。
- 100 个并发 ingest 只产生一个对应玩家的 prepare job。
- unsupported narrative 必须被 deterministic narrative 替换，而不是仅降 confidence。
- 中文、英文、数值和实体级 fabricated claim 都会 fail closed。

---

## 9. 最终建议

两轮审查共同说明：项目的核心价值和工程基础都已经存在，但当前最大的风险不是“功能少”，而是安全凭据、记分耐久、跨端版本和运维门禁还没有形成硬不变量。

建议继续以 Codex 主报告作为完整问题目录，以本报告作为 Claude 独立验证和新增问题补充。发布决策必须同时满足两份报告的 P0/P1 验收条件。

最合理的工程顺序仍然是：

```text
安全事故处置
→ 一杆不丢
→ 结束球局可恢复
→ 身份/注册/资源治理
→ 事务与契约
→ 统计与几何正确性
→ AI 叙述
→ Watch 视觉打磨
```
