# Codex Owner Decision Pager 设计

**日期：** 2026-07-18

**状态：** Owner 已批准设计，等待书面规格复核

**范围：** homeserver 上 Codex 开发协作的外部通知与决策恢复；不属于高尔夫产品功能

## 1. 背景

Owner 通过 Secure ShellFish 连接 homeserver，并在长期存在的 `shellfish-*` tmux 会话中与 Codex 协作。长时间 review、研究或开发过程中，Codex 可能遇到必须由 Owner 作出的产品选择、授权或范围决定。若 Codex 只在当前终端提问并停止，Owner 不在 ShellFish 前台时无法及时获知，工作可能无谓停滞数小时。

本设计建立一个独立的工程协作通知通道：Codex 在真正需要 Owner 决策时，通过 Telegram Bot 主动提醒；简单问题可直接在 Telegram 选择答案，需要讨论时返回原 ShellFish/tmux 会话细聊。

该系统不得进入 Web、iOS、Apple Watch 高尔夫产品契约，也不得把打球过程中的产品提醒与开发协作提醒混为一谈。

## 2. 已锁定目标

1. Codex 只有在无法安全继续依赖分支、且问题确实需要 Owner 权限或价值判断时才发出通知。
2. Telegram 中支持结构化直接回答、确认推荐方案、稍后提醒和请求细聊。
3. 决策及其回答持久化；Codex、tmux、SSH 或 homeserver 服务重启不得丢失。
4. 对 managed background Codex job，结构化答案可以触发受控续跑。
5. 对普通交互式 Codex TUI，不向未知状态的 pane 盲目注入按键；需要细聊时由 Owner 回到原会话。
6. 429、503、模型 cooldown、普通测试失败和可由工程证据解决的问题不得上交 Owner；系统应自动重试或继续研究。
7. Bot 不是远程 Shell，不接受任意命令执行。

## 3. 非目标

- 不替代 Telegram、ShellFish、tmux 或 Codex 自身的完整聊天 UI。
- 不将自然语言 Telegram 消息直接拼接为 Shell 命令。
- 不保证任意已经运行中的交互式 TUI 都能被外部安全唤醒。
- 不发送源代码、凭证、Cookie、授权 Header、完整日志或其他敏感信息到 Telegram。
- 不把所有 Codex turn complete、测试完成或普通状态更新都变成手机 Push。
- 第一版不依赖 experimental `app-server`、`remote-control` 或未稳定的内部协议。

## 4. 方案比较与裁决

### 4.1 PushDeer 单向提醒

优点是接入简单、只需发送 HTTP 请求。缺点是没有结构化回答、确认、snooze 和待决列表。它可作为未来备用通道，但不作为第一版主通道。

### 4.2 Telegram Bot + tmux `send-keys`

Telegram 交互能力足够，但直接向现有 pane 执行 `tmux send-keys` 无法可靠判断 Codex 是否正在等待输入、是否处于 Shell、工具执行或其他界面。错误注入可能成为命令执行或污染错误会话，因此否决。

### 4.3 Telegram Bot + 持久队列 + managed Codex runner

这是批准方案。Telegram 负责通知和结构化回答；SQLite 保存决策状态；managed runner 对自己启动并记录 session ID 的后台 Codex job 使用稳定的会话续接能力。普通 TUI 保持人工返回，不做危险注入。

## 5. 总体架构

```text
Codex / Review Job
      │ owner-pager ask
      ▼
Decision Store (SQLite + append-only events)
      │
      ├──► Telegram Bot Notifier ──► Owner 手机
      │                                  │
      │                    answer / snooze / discuss
      │                                  │
      ◄───────────────────────────────────┘
      │
      ├── answered managed job ──► Managed Runner ──► codex exec resume
      │
      └── discussion requested ──► ShellFish/tmux handoff instructions
```

组件边界：

- `owner-pager`：创建、查询、回答、snooze、解决决策的本地 CLI/API。
- `decision-store`：持久化当前状态与不可变事件历史。
- `telegram-worker`：使用 long polling 接收按钮回调；无需开放公网 webhook 端口。
- `notifier`：发送新问题、提醒、确认和错误消息。
- `managed-codex-runner`：只管理由它启动的非交互任务，并保存 Codex session ID、工作目录和安全恢复上下文。
- `handoff-renderer`：生成项目路径、tmux session、attach 命令和问题摘要；不自动发送按键。

## 6. 决策触发规则

### 6.1 允许触发

- 两种或更多合法产品方向会产生不同用户承诺，现有 Owner 决定无法推出唯一答案。
- 需要新的外部授权、付费、发布、数据抓取或其他显著状态改变。
- 发现现有实现与 Owner 锁定范围冲突，而修正方向会实质改变已批范围。
- 继续执行会不可逆地丢失数据、覆盖工作或扩大权限。

### 6.2 禁止触发

- 429、503、cooldown 或临时网络故障：自动定时重试。
- 测试失败、解析器错误、未知字段或技术难题：先穷尽安全研究。
- 已有 Owner 决定、权威规格或数据能唯一推出答案。
- 可以采取保守、可逆、范围内的工程默认继续工作。
- 仅仅希望 Owner 看状态、给予鼓励或确认无意义的实现细节。

### 6.3 继续工作规则

创建决策后，只暂停依赖该答案的分支。所有无依赖调查、测试、文档整理和其他计划项继续进行。只有整个目标都依赖该决策时，managed job 才进入 `waiting_owner`。

## 7. 决策数据模型

`Decision` 至少包含：

- `decision_id`：稳定、可读 ID。
- `revision`：问题或选项变化时递增，防止回答旧问题。
- `job_id`、`codex_session_id`、`cwd`、`tmux_session`：恢复与 handoff 上下文。
- `title`、`question`、`rationale`：脱敏摘要。
- `options[]`：稳定 option ID、短标签、说明。
- `recommended_option_id` 与推荐理由。
- `status`：`open | snoozed | answered | discussion_requested | resolved | cancelled | expired`。
- `blocking_scope`：暂停哪个计划项或 job。
- `created_at`、`remind_at`、`answered_at`、`resolved_at`。
- `decision_hash`：关键问题和选项的 canonical hash。

`DecisionEvent` 只追加，记录创建、发送、发送失败、提醒、点击、回答、请求细聊、恢复、解决和取消。当前状态可以由事件投影得到；SQLite 中可同时保存物化状态以便查询。

Telegram callback 只携带短 token，例如 `d:<id>:<rev>:<action>`；服务端重新读取完整记录并验证 Owner `chat_id`、revision、状态和允许动作。

## 8. Telegram 交互

典型消息：

```text
需要你决定 · MAP-001

问题：新球场快照在未取得明确分发权前，是否默认账户私有？
影响：阻塞 Course Service 发布策略；解析研究继续进行。
推荐：账户私有，接口保留未来中央目录能力。
```

按钮按问题动态生成：

- `按推荐方案`
- 一个或多个显式选项，例如 `A 私有`、`B 中央共享`
- `需要细聊`
- `30 分钟后提醒`
- `今天晚些时候`

Bot 命令第一版只需要：

- `/pending`：列出未解决问题。
- `/decision <id>`：重新显示一项。
- `/snooze <id>`：延后提醒。
- `/help`：说明 Bot 只处理 Owner 决策，不执行 Shell。

自然语言回复不会自动成为命令或答案。若 Owner 希望补充理由，Bot 可保存为 `owner_note`，但需显式引用 decision ID；自由文本仍不得进入 Shell。

## 9. 回答后的恢复语义

### 9.1 Managed background job

runner 创建 Codex job 时保存 session ID。收到有效结构化回答后：

1. 将回答写成不可变 `DecisionEvent`。
2. 生成只包含 decision ID、选择、Owner note 与原问题 hash 的恢复 prompt。
3. 对对应非交互 session 使用稳定的 `codex exec resume <session-id> -` 路径继续工作，恢复 prompt 从标准输入传入，避免出现在进程参数中。
4. 对同一 `decision_id + revision` 使用 single-flight 锁，避免重复点击启动两次。
5. 新 job 必须重新读取工作树状态和计划，不假设暂停期间文件未变化。

### 9.2 普通交互式 TUI

回答仍会被持久保存，但第一版不向活跃 pane 注入字符。Bot 回复：

- 已记录的答案；
- tmux session 名；
- `tmux attach-session -t <session>` 命令；
- 若该会话已结束，则提供 `codex resume <session-id>` 提示。

Owner 返回会话后，Codex 读取 pending answered decision 并继续。未来只有在官方、稳定的受控消息接口能够识别 thread/turn 并防止并发时，才评估自动唤醒交互式 TUI。

## 10. 通知、重试与去重

- 新决策立即发送一次。
- 发送失败采用指数退避并加入抖动；Telegram `retry_after` 必须被遵守。
- 首次未回答提醒默认为 30 分钟，第二次为 2 小时，此后最多每日一次。
- Owner 点击 snooze 后，在指定时间前不再提醒。
- `answered`、`discussion_requested`、`resolved`、`cancelled` 立即取消未来提醒。
- 去重键为 `decision_id + revision + notification_kind + cadence_slot`。
- 多个非紧急问题合并摘要；系统仍维持一次只推进一个 `current` Owner 产品问题的治理规则。

## 11. 安全与秘密管理

- Telegram Bot Token 和允许的 Owner chat ID 保存在 systemd credentials，或退化为 Owner 专属、权限 `0600` 的配置文件。
- Token 不进入仓库、聊天、环境诊断、进程参数、URL query、日志或异常正文。
- Bot 启动时拒绝 world/group-readable 的 secret 文件。
- 只接受单一 allowlisted private chat；群聊、转发消息和其他用户一律拒绝。
- callback 必须匹配有效 decision、revision 和状态；过期按钮返回“问题已更新”，不能修改新版本。
- Bot 无 Shell tool、无通用 subprocess 接口、无任意路径写权限。
- Telegram 内容只包含脱敏问题；敏感证据留在 homeserver，并以短引用定位。
- Token 泄露时通过 BotFather `/token` 生成新 Token，撤销旧 Token，并重启 worker。

## 12. Codex 集成

Codex 官方用户级配置支持外部 `notify` 程序，稳定 CLI 也支持保存和恢复 session。设计使用以下边界：

- `~/.codex/config.toml` 的用户级 `notify` 可用于普通 turn/approval 的本地事件入口，但不得把所有 turn complete 直接推送到 Telegram。
- `owner-pager ask` 是语义明确的 Owner 决策入口；Codex 在创建阻塞问题时显式调用。
- 全局或用户级 Codex 指令要求：需要 Owner 决策时必须创建 pager item；技术性失败不创建。
- managed runner 使用稳定的非交互执行/恢复能力。
- experimental app-server、remote-control 和 debug send-message 不作为第一版正确性依赖。

## 13. 故障处理

- Telegram 不可达：决策保留为 `open`，worker 重试；不丢失问题。
- Bot Token 无效：停止发送并在本地 health 状态中记录；不得无限触发 Telegram 请求。
- Bot worker 崩溃：systemd 自动重启；SQLite 恢复未发送和未完成任务。
- homeserver 重启：服务恢复后扫描到期提醒和 `waiting_owner` job。
- 重复 callback：按 decision revision 和事件幂等键只记录一次。
- resume 失败：job 保持 `answered_resume_failed`，给 Owner 发送一次说明与 ShellFish handoff，不把答案改回未回答。
- 工作树在暂停期间变化：resume 前重新核对 dirty state；冲突时进入细聊而非覆盖。

## 14. 验证计划

### 单元测试

- 决策状态转换、revision、过期按钮和幂等。
- chat ID allowlist、callback 解析和 secret 文件权限。
- 通知去重、snooze、退避和 Telegram `retry_after`。
- managed resume prompt 不包含敏感字段。

### 集成测试

- 使用独立测试 Bot 验证发送、按钮、long polling 和重启恢复。
- SQLite 写入后强杀 worker，验证重启不丢失。
- 同一按钮快速点击多次，只启动一个 resume。
- 模拟 Telegram 401、429、5xx、超时和断网。
- 模拟 Codex resume 失败、session 不存在和 dirty worktree 变化。

### 人工验收

1. 创建一个无风险测试决策。
2. 手机收到 Telegram Push。
3. 点击推荐选项，Bot 显示已记录。
4. managed test job 自动继续并产生完成通知。
5. 创建第二个测试决策，点击“需要细聊”。
6. Bot 返回正确 tmux session 和 attach 命令，且没有向 pane 自动输入。

## 15. 分阶段交付

### Phase 1：通知与持久决策

- Telegram Bot、SQLite、systemd worker。
- 创建问题、按钮回答、snooze、pending 列表和 ShellFish handoff。
- 不自动续跑 Codex。

### Phase 2：Managed Codex Runner

- 为长 review、研究和开发任务建立受控 job wrapper。
- 保存 session ID，结构化回答后使用稳定 resume。
- single-flight、工作树重检、失败降级到细聊。

### Phase 3：Codex 工作流接入

- 用户级指令或可复用 skill 规定触发条件。
- 可选接入 Codex 外部 notifier 作为本地事件源。
- 统计误报、漏报、等待时长和提醒噪音，调整 cadence。

PushDeer 只有在 Telegram 实测存在明显漏送或 Owner 明确要求冗余时才作为备用 adapter 加入。

## 16. Owner 已批准的协作系统决定

- Telegram 为主通道。
- 简单问题允许直接回答。
- 复杂问题允许回到 ShellFish/tmux 细聊。
- 不把 Telegram Bot 做成远程 Shell。
- 不向活跃 TUI 盲目注入文本。
- managed 长任务可在结构化回答后自动恢复。

## 17. 实施前所需 Owner 操作

Owner 需要通过 Telegram 官方 `@BotFather` 创建 Bot，并在 homeserver 终端安全写入 Token。Token 不得粘贴到 Codex 对话。实现阶段还需由 Owner 首次打开新 Bot 并发送 `/start`，系统才能读取并锁定正确的私聊 chat ID。
