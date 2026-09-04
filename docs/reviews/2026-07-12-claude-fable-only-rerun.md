# garmin-ai-caddie 全仓工程审查(Fable 独立重跑)

> **状态:INCOMPLETE（Fable 额度中断）** — 会话未完成全仓审查，不得把本文件当作正式发现报告或发布判断依据。

## 0. 运行元数据

- 日期:2026-07-12
- 审查者:Claude Fable 5(模型 ID `claude-fable-5`),单会话、未使用任何子代理/Task/其他模型
- 审查对象:工作区 `/home/ubuntu/claude-web-data/repo/garmin-ai-caddie`,分支 `integration/v2`,HEAD = `a0c0fca8f07b888722561f28b2a10cdf45f84d33`
- 工作区脏状态(未纳入审查的未提交内容,仅记录存在):`M docs/CODE_REVIEW_FINDINGS.md`、未跟踪 `.mockups/watch-shot-tracking.html`、`docs/reviews/`、两份 2026-07-10 watch 规格文档
- 模式:只读;唯一写入 = 本报告文件;不提交、不推送
- 代码规模:`ai_caddie/` 69 个 py 文件约 31,992 行;`tests/` 148 个 py 文件约 37,053 行;`web_v2/src` 115 个 TS/TSX 约 32,642 行;`mobile/` 112 个 Swift 约 21,748 行;另有 `server_v2/`、`ops/`、`tools/`、`migrations/`

## 1. 独立性声明与排除项

- 本次审查**未读取**任何既有审查产物:`docs/CODE_REVIEW_FINDINGS.md`、`docs/reviews/**`(除写入本文件)、`docs/superpowers/reviews/**`,以及任何以历史代码审查为主要内容的文件。
- 局限披露:会话启动时上下文中带有跨会话记忆索引(项目历史摘要)。该索引不含旧审查的具体发现条目;本报告所有发现均以本会话实际读取的代码/配置为证据,不引用记忆内容作为证据。
- 所有结论标注置信级别:**CONFIRMED**(代码路径已完整读通)/ **HIGH-CONFIDENCE**(证据充分但个别环节未动态验证)/ **NEEDS-DYNAMIC-VERIFICATION**(需要运行时验证)。

## 2. 严重级别定义

| 级别 | 定义 |
|---|---|
| P0 | 生产路径上必然或高概率触发:数据丢失/损坏、越权访问、服务不可用、资金/账号安全 |
| P1 | 明确的正确性或安全缺陷,用户可见,但需特定条件触发或影响面有限 |
| P2 | 边界条件、鲁棒性、性能、可观测性缺陷;或将来高概率变成 P1 的结构性问题 |
| P3 | 风格、文档、小型可维护性改进 |

## 3. 执行摘要

本次确实以 `claude-fable-5`、`max` effort 和禁用 refusal fallback 的方式重新启动了独立审查。会话在完成仓库盘点并开始检查部署、会话、玩家与 Apple 登录链路后，触发 Fable 5 七天额度上限并以 HTTP 429 结束。由于尚未覆盖 Web、iOS、Watch、Garmin、统计、几何、AI、测试和完整运维链路，本次运行**不能给出新的全仓结论**。

终止提示为：`You've reached your Fable 5 limit. Run /usage-credits to continue or switch models with /model.` 本次按要求没有切换模型，因此保留未完成状态。

## 4. 优点

额度中断前未形成达到证据标准的完整优点清单。

## 5. 发现总表

额度中断前未形成可发布的完整发现条目。会话中的探索笔记不能替代逐项 source-to-sink 核验，因此这里不抄录半成品判断。

## 6. P0/P1 及重要 P2 详细证据

未完成。

## 7. 跨端契约分析

未完成。

## 8. 测试缺口矩阵

未完成。

## 9. 发布门槛

未完成；继续以 2026-07-11 的完整审查和交叉核验文档作为当前依据。

## 10. 30/60/90 天建议

未完成。

## 11. 实际覆盖清单

### 已检查或开始检查

- 仓库顶层结构、当前 HEAD、工作区脏状态和各端代码规模
- `README.md`、`Dockerfile`、`docker-compose.yml`、`.env.example`
- `ops/start_api.sh`
- `server_v2/main.py`（部分）
- `server_v2/session.py`
- `server_v2/players_api.py`
- `server_v2/auth_api.py`
- `server_v2/apple_auth.py`
- `ai_caddie/rounds/players.py`

### 未完成

- Python 后端其余 API、存储、并发、备份恢复
- Garmin 导入、geometry/maps、统计/差点和 AI caddie/provider 边界
- Web 全部生产链路
- iOS 全部生产链路
- Apple Watch 与 WatchConnectivity 全部生产链路
- 跨端契约和 schema evolution
- 安全、隐私、供应链、CI/CD、观测、限流和资源耗尽的完整核验
- 测试质量、false-green、端到端缺口、死代码和重复
- Release readiness 与整改路线

## 12. 中断记录与模型来源（运行控制器补记）

- Claude Code 版本：`2.1.207`
- 会话 ID：`55ce3a46-c905-4979-84db-f95b196378c3`
- 启动模型：`claude-fable-5`
- effort：`max`
- refusal fallback：通过 `CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK=1` 禁用
- 退出：HTTP 429 / Fable 5 usage limit
- 本次模型用量记录仅包含 `claude-fable-5`：18 input、13,513 output、620,008 cache-read、91,081 cache-creation tokens
- 总运行时间：234,287 ms；Claude CLI 报告成本：USD 3.117458
- fallback/Opus：会话事件中未出现 `model_refusal_fallback`，最终 `modelUsage` 不含 Opus
- CLI 返回的额度重置时间：2026-07-13 05:00 UTC

> 本节由外层运行控制器在 Claude Code 进程退出后根据 stream-json 和会话 JSONL 补记；不属于 Fable 的审查结论。
