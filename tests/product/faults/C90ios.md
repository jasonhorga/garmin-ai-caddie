# C90 iOS r6 故障清单

本轮每条新增验收行为测试都有一个独立 native mutant。项目台在 native CI 对每个
patch 单独 apply 并运行 manifest 中的 target；本机没有 Swift/Xcode，只做 patch
可应用性与 Python fault-runner 检查。

| promise | mutant | 测试 / 红断言 |
|---|---|---|
| B1 | 01、02、03 | `testQuarantineBlockedFinishKeepsRoundBackgroundWorkAlive`、`testQuarantineBlockedWatchFinishKeepsRoundBackgroundWorkAlive`、`testDiscardFailureKeepsRoundBackgroundWorkAlive`：held round request 被取消或 round ownership 被清除 |
| B2 | 04 | `testDiscardLeavesAnotherPrepCourseDownloadRunning`：另一个球场 prep held request 的 stop count 变为 1 |
| B5 | 05 | `testFinishKeepsWholeCourseDownloadRunning`：Save & End 后本局 held whole-course request 被取消 |
| B4 | 06 | `testAStoppedModelSendsNoFurtherRequest`：install/status 在 stop 后到达 `URLProtocol.startLoading`，违反 inverted expectation |
| B3 | 07 | `testCancelledRequestSamplesTimingBeforeTransportCheck`：取消发生在 gate 后仍必须采到一次 monotonic start |
| B3 | 08 | `testClientTimingStorePersistsOffCallerQueue`：写盘 observer 在调用队列执行 |

顺手项：`C90RequestGate` 的 release-before-wait race、`.canceling` 等待条件、discard
重复 geometry 取消已在 r5 修复；本轮保留并由既有 B4 teardown 测试覆盖。
