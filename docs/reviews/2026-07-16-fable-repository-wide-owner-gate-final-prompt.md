# 纯 Fable 最终对抗任务：全仓 Owner 决策门、权威与实现漂移

你是独立产品治理与工程审查者。请使用 `claude-fable-5`、max effort，对 Codex 的全仓 Owner-gate 合并稿做一次敌对审查。

## 运行边界

- 只读；不得修改文件。
- 只允许 Read / Grep。
- 不得调用 Agent / Task / Web / Bash / Write / Edit。
- 不得使用其它模型，不得 fallback。
- 不要因为 Codex、旧 Fable 或文件标题声称“已定”就接受；必须核对 Owner 来源、产品合理性与真实代码。
- 先判断设计/范围是否合理，再判断复用与实现漂移，最后判断是否真的需要 Owner。

## 必须完整阅读

1. `docs/reviews/2026-07-16-repository-wide-owner-gate-authority-and-drift-audit.md`
2. `docs/reviews/2026-07-15-watch-decision-and-task-tracker.md`
3. `docs/reviews/2026-07-16-codex-watch-owner-decision-queue-reclassification.md`
4. `docs/reviews/2026-07-16-claude-fable-watch-owner-decision-queue-final-adversarial-review.md`
5. `docs/reviews/2026-07-16-claude-fable-d02-virtual-caddie-adversarial-review.md`
6. `docs/superpowers/specs/2026-06-13-multiplayer-foundation-design.md`
7. `docs/superpowers/specs/2026-06-28-member-onboarding-apple-design.md`
8. `docs/superpowers/specs/2026-06-28-garmin-self-bind-phaseB-design.md`
9. `docs/product/2026-06-29-product-manual.md`
10. `docs/reviews/2026-07-11-full-repository-review.md`
11. `docs/reviews/2026-07-11-codex-claude-cross-review.md`
12. `docs/reviews/2026-07-14-claude-fable-only-product-design-adversarial-review.md`
13. `docs/superpowers/specs/2026-06-11-w4-requirements.md`
14. `docs/superpowers/specs/2026-07-02-unified-tri-surface-spec.md`
15. `docs/superpowers/plans/2026-07-08-watch-full-consensus.md`

然后用 Grep/Read 抽核合并稿 §4 列出的全部源码行，不要只信行号摘要。

## 必须攻击的问题

1. 常设 Owner 队列是否真的只剩 `D02 CURRENT → D04 QUEUED`？扫描上述文档与相关源码后，有没有遗漏的当前产品价值取舍。
2. D12b 是否必须留在条件回流注册表；E07、D13b、E08/E09 的路由是否准确。
3. Watch 的空白“练习记分”（默认 18 个 Par 4）应当只是 D04 前的 placeholder，还是已经构成一个必须现在问 Owner 的正式并行产品模式。
4. 2026-06-13 是否已经明确决定“每人只看自己、owner 管理页不看成员分析”；旧 Fable 的 family visibility 三档是否属于无效重开。
5. 成员 Garmin self-bind 是否已有 Owner-goal-directed Phase B 方向，因此剩余是工程完成；还是全仓 release review 足以把它重新升级为当前 Owner 范围题。
6. Apple 首次登录自动注册是否已在“owner 控制分发”前提下批准；若公开分发，invite/allowlist 是工程安全前置还是新的 Owner 偏好题。
7. L20（至多一个前台 active，旧局可 suspended/finishedPendingSync 保留）是否可由 L16 唯一推出；是否偷偷做了产品取舍。
8. L21（所有用户可见距离为码，内部米制）是否确由用户原话锁定。
9. D02 旧 Fable review §2.3 的三个“Owner 边界”是否应重分类为实施分批/E04/D04，而非三个新问题。
10. 合并稿 §4 的十余项代码漂移是否分类正确；有没有一项实际上需要 Owner 决定，或遗漏同等级漂移。
11. 新增的 authority correction 是否错误覆盖了仍有效的 Owner 决定，或仍有会误导实施者的高风险旧文档未加 guard。
12. D09b 删除“已有手机/Web admin 代录通道”理由后，out-of-scope 结论是否仍站得住。

## 输出格式

请输出一份完整中文报告，至少包括：

1. **最终裁决**：ACCEPT / MODIFY / REJECT Codex 的“无新增常设 Owner 门”结论。
2. **Owner 队列表**：每个当前、queued、条件回流项；如新增，必须给出精确问题与为什么现有决定不能推出答案。
3. **非 Watch 三项裁决**：family visibility、Garmin self-bind、Apple auto-registration。
4. **L20/L21 与 D02 §2.3 裁决**。
5. **代码漂移逐项抽核**：至少标出 CONFIRMED / MODIFY / REJECT。
6. **文档权威审计**：哪些 guard 正确，哪些还需修。
7. **可直接写回的更正清单**。
8. **明确下一步**：现在唯一应该向 Owner 问什么；不得夹带下一题。

不要写泛泛建议。每个异议必须给文件与行号或明确来源；没有新问题时，也要说明你攻击过哪些最强反例后为何仍没有。

