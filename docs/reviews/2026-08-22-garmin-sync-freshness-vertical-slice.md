# Garmin Sync Freshness Vertical Slice

日期：2026-08-22  
范围：Garmin CN 拉取结果、同步状态、iOS/Web 可见反馈

## 结论

Homeserver 的 cron 当前每小时成功运行，`aicaddie-sync:latest` 也存在并能完成拉取。只读上游探针用现有同步凭据请求了 Garmin CN 的三个分页变体，均返回 `totalRows=485`。用户确认所说的 Half Moon Bay 两场已经正确同步并可用：

- `17603881`，`2026-08-14T17:59:40Z`，Half Moon Bay Golf Links ~ Ocean；18 洞 scorecard 完整，18 洞均有击球记录。
- `17601656`，`2026-08-13T22:11:27Z`，Half Moon Bay Golf Links ~ Old；18 洞 scorecard 完整，18 洞均有击球记录。

因此当前没有确认到 Garmin 同步主链路的故障。freshness 字段是可观测性补强，用来区分“请求成功”和“实际返回了新球局”，不是对这两场球的修复。后续仍应验收历史页、round detail、shot map 和 iOS Results 的端到端可见性；若出现新球局在 Garmin Connect 可见但本地不见，再针对账号区域和接口来源调查。

## 实现

同步结果现在记录以下非敏感观测字段：

- `remoteRoundCount`
- `remoteLatestRoundId`
- `remoteLatestRoundAt`
- `newRoundCount`

它们写入 `data/sync/garmin_cn_status.json`，通过 `/api/v2/sync/status` 暴露给 owner。iOS 与 Web 在 `newRoundCount == 0` 时显示“同步完成，但暂无新球局”，避免把“请求成功”误报成“有新数据”。旧状态没有这些字段时保持原有兼容行为。

## 验证

- Homeserver Python：`tests.test_pipeline` + `tests.test_server_v2_sync_status`，26/26 通过。
- Homeserver Web：`src/components/SyncStatusPanel.test.tsx`，15/15 通过。
- 未运行 native build：Homeserver 为 Linux，没有 `xcodebuild`/`swiftc`；iOS 只完成 Codable 兼容性静态核对。
- 未修改生产容器、volume、cron 或 Garmin 凭据。

## 未闭环项

1. 对这两场已同步球局做 history/round detail/shotmap/iOS Results 端到端验收，确认 UI 可见性与本地落盘一致。
2. 以后出现新球局时，利用 `remoteLatestRound*` 与 `newRoundCount` 判断是上游未返回、同步未落盘，还是客户端展示/缓存问题。
3. 只有在 Garmin Connect 可见而 CN summary 不可见时，才继续调查 global/CN endpoint、会话来源和账号区域。
