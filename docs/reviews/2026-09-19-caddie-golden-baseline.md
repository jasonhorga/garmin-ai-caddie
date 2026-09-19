# Caddie Golden Replay Baseline

日期：2026-09-19 UTC  
范围：`DIRECT-CADDIE-VALIDATION`，算法改动尚未发布

12 条回归场景固化在
[`tests/fixtures/caddie_golden_cases.json`](../..//tests/fixtures/caddie_golden_cases.json)，由
[`tests/replay_caddie_goldens.py`](../..//tests/replay_caddie_goldens.py) 重放。远程执行使用
homeserver 的 API 镜像 `/app/.venv`，没有在控制机安装依赖或启动新服务。

## Evidence

- Replay test：`tests.test_caddie_golden_replay`，1/1 passed。
- Fixture SHA-256：`72e557128b79dcbf4a280e863c42edefc028c5be21f628de1156c79a248790dd`。
- Baseline output：`/home/jason/garmin-ai-caddie-data/operations/direct-caddie-validation-20260919/caddie-golden-baseline-20260919.json`。
- Baseline output SHA-256：`070e67386609951c08d57a521d01599e821ea33775cf0bf6bf9adf3b0fecf90b`。
- 执行命令：
  `docker run --rm --volumes-from aicaddie-release-7ef3fcc8-candidate-20260917 ... tests/replay_caddie_goldens.py`。

## Current Findings

基线不是通过标准，而是后续实现前的可比快照。按 fixture 的目标检查，失败项为：

- `01_normal_par4`：无障碍正常四杆洞的 selected 首杆为 `3W`，没有自然选择最长可行的 Driver。
- `04_short_par4_green_bunker`：短四杆洞 selected 首杆为 `3H`，没有保持首杆/替代方案的清晰语义。
- `08_cold_start`：无历史数据仍产生三杆序列，超过冷启动最多两杆的约束。
- `10_no_driver_or_unstable_driver`：Driver 只有 5 个样本但仍可能成为序列首杆，缺少不稳定球杆降级理由。

同时，当前回放中 `driverNonTee=0`，多段水区间保留为两个带有不同
`intervalIndex` 的区间；这两项不能替代真实球场回放，后续仍要覆盖第二杆重新投影、复合九洞外呼计数和真实几何。

下一阶段先实施网络 P0，完成后再把 fixture 的目标检查升级为阻断式 Caddie P0 回归。
