# C90 iOS r7 故障清单

本轮每条新增验收行为测试都有一个独立 native mutant。项目台在 native CI 对每个
patch 单独 apply 并运行 manifest 中的 target；本机没有 Swift/Xcode，只做 patch
可应用性与 Python fault-runner 检查。

| promise | mutant | 测试 / 红断言 |
|---|---|---|
| B1 | 01、02、03 | `testSealFailureKeepsRoundBackgroundWorkAlive`、`testQuarantineBlockedWatchFinishKeepsRoundBackgroundWorkAlive`、`testDiscardFailureKeepsRoundBackgroundWorkAlive`：seal/clear/discard 失败时 round-owned task/round ownership 被清除 |
| B1 | 09 | `testQuarantineBlockedFinishKeepsRoundBackgroundWorkAlive`：测试先写入 scoring quarantine，再调用 `finishActiveRound()`；mutant 在 `do {` 首行取消 round work，随后 quarantine guard 返回失败，故 held round ownership 断言 `offlineCourseDownloadRoundIdForTesting == package.roundId` 红 |
| B2 | 04 | `testDiscardLeavesAnotherPrepCourseDownloadRunning`：discard 后另一球场 prep 行保持下载中、active job 不清，并在释放 503 后发起下一次请求 |
| B5 | 05 | `testFinishKeepsWholeCourseDownloadRunning`：Save & End 后本局 whole-course 下载继续并最终落盘模板 |
| B4 | 06 | `testAStoppedModelSendsNoFurtherRequest`：SyncClient 删除 transport 前 cancellation check 后，stop 后 gate 放行仍会到达 transport，违反 inverted expectation |
| B3 | 07 | `testCancelledRequestSamplesTimingBeforeTransportCheck`：取消发生在 gate 后仍必须采到一次 monotonic start |
| B3 | 08 | `testClientTimingStorePersistsOffCallerQueue`：写盘 observer 在调用队列执行 |

顺手项：`C90RequestGate` 的 release-before-wait race、`.canceling` 等待条件、discard
重复 geometry 取消已在 r5 修复；本轮保留并由既有 B4 teardown 测试覆盖。
