# 纯 Fable 对抗任务：Watch Owner 决策队列终审

你是独立的产品治理与 Apple Watch 高尔夫产品对抗审查者。不要顺从 Codex，也不要因为当前实现省事而降产品目标。

## 用户真实目标

把所有真正需要 Product Owner 本人判断的问题都搞清楚，并且之后一次只问一个；用户回答后必须先写回决策账本，不能边聊边丢问题。

用户明确要求判断顺序：

1. 先判断整个产品设计是否合理、是否最优，尤其是否真正接近 Garmin Approach S70 的腕上体验。
2. 再判断现有工程哪些可直接复用、哪些修改后可复用、哪些必须淘汰。
3. 最后才给具体修改和实现建议。

不得把技术阈值、证据缺口、实现难度或模型可以决定的问题转嫁给 Owner。

## 必须完整阅读的核心文件

1. `docs/reviews/2026-07-15-watch-decision-and-task-tracker.md`
2. `docs/reviews/2026-07-16-codex-watch-owner-decision-queue-reclassification.md`
3. `docs/reviews/2026-07-15-codex-fable-watch-full-experience-reassessment.md`
4. `docs/reviews/2026-07-15-claude-fable-watch-full-experience-final-adversarial-review.md`
5. `docs/reviews/2026-07-15-s70-verified-evidence-pack.md`
6. `docs/reviews/2026-07-16-s70-virtual-caddie-driver-arc-evidence.md`
7. `docs/superpowers/specs/2026-05-25-ai-caddie-master-product-spec.md`
8. `docs/superpowers/specs/2026-06-09-web-product-redesign-design.md`
9. `docs/superpowers/specs/2026-06-13-multiplayer-foundation-design.md`
10. `docs/superpowers/specs/2026-07-02-unified-tri-surface-spec.md`
11. `docs/superpowers/specs/2026-07-05-auto-swing-detection.md`
12. `docs/superpowers/specs/2026-07-07-review-edit-ui-design.md`
13. `docs/superpowers/specs/2026-07-08-watch-full-consensus.md`
14. `docs/superpowers/specs/2026-07-10-watch-control-spec.md`
15. `docs/superpowers/specs/2026-07-10-watch-design-system.md`

可用 Read/Grep 继续核对与分类直接相关的源码或文档。不得修改任何文件。

## 必须独立裁决的范围

### A. D03–D13

逐项分类为且只能为下列之一：

- `OWNER_REQUIRED`
- `OWNER_REOPEN`（已有 Owner 决定，现申请改变）
- `ALREADY_DECIDED`
- `ENGINEERING_OR_MODEL_DECIDABLE`
- `EVIDENCE_FIRST`
- `DUPLICATE_OR_INVALID`

若一项混合了两个问题，必须拆开再分别分类。若选项是假中立、违反既有 invariant、隐私底线或产品边界，必须删除，不得让 Owner 在无效选项中选择。

### B. L01–L17 与 D01–D02

检查是否有已经锁定却被后续文本静默推翻的语义；尤其检查 D02 的 C′、D04 Watch 独立范围、D07 净杆、D10 编辑边界。

### C. E01–E10

不要默认“证据完成后就一定要问 Owner”。逐项判断：

- 证据后是否真的会形成价值取舍；
- 还是证据/平台约束会直接推出答案；
- 是否与 D 项重复；
- 是否遗漏新的前置证据。

### D. 是否漏了真实 Owner 决策

扫描完整账本和关键规格，找出未登记但确实改变产品承诺的 Owner 问题。不要把普通 backlog、阈值或实现方案算成 Owner 问题。

## 必须重点攻击的争议

1. D03 是否只是工程治理，而不是 Owner 三选一。
2. D04 必须诚实写成“是否授权降低此前批准的 Watch 冷启动独立范围”；产品最优与最短交付不能混为一谈。
3. D07 是否已被 2026-06-09 用户逐屏确认的“v1 gross、Stableford/净杆后续”决定。
4. D08 是否只是三条事实链独立的重复结论。
5. D09 的传感器归属与同组手填总分是否被错误捆绑；多人总分是否属于当前产品边界或 S70 核心体验。
6. D10 必须尊重“iOS 深编辑、Web 只读”的 Owner 定稿，不能擅自写成 iPhone/Web 都深编辑。
7. D11 是否已由个人产品边界与本 build 排除 tournament surface 决定；正式合规扩张是否应证据先行。
8. D12 的隐私底线是否已经唯一推出“默认不上传、独立 opt-in”；是否只剩证据后的研究数据捐赠计划。
9. D13 是否必须先证明 Workout/后台/Health 保存的真实平台组合，才能形成 Owner 问题。
10. Codex 暂定“D02 后只剩 D04”是否过度删除了真实产品取舍。

## 输出要求

直接输出一份可保存的中文 Markdown 审查，不要写前言闲聊。必须包含：

1. `执行结论`：当前真正 Owner 队列究竟有几项，按顺序列出。
2. `逐项裁决表`：D03–D13 每项分类、理由、关键证据、是否改写。
3. `E01–E10 审计表`：每项是证据后 Owner、证据直接决定、重复，还是无效。
4. `对 Codex 的异议`：明确 ACCEPT / MODIFY / REJECT，不能只说大体同意。
5. `准确的 Owner 问题`：每个真实问题只给 2–3 个互斥、诚实选项，说明产品最优推荐与工程代价。
6. `可直接写回账本的决定`：无需 Owner 的项目给出精确状态与一句话语义。
7. `遗漏检查`：是否还有账本外的真实 Owner 决策。
8. `最终下一步`：保持 D02 为唯一 CURRENT；不得提前询问 D04。

所有事实必须标注仓库路径和行号。若证据不足，写 `EVIDENCE_FIRST`，不得用模型记忆补洞。

