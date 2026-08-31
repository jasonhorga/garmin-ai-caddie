# Garmin AI Caddie Cleanup - 2026-08-31

This is the allow-list and result record for the cleanup performed after the
owner confirmed that TestFlight build 46 is visible. Only the two exact
temporary output paths below are in scope.

## Allow-list

| Path | Owner | Evidence | Action |
| --- | --- | --- | --- |
| `/home/ubuntu/claude-web-data/repo/garmin-ai-caddie/.codex-tmp/native-33294247633-real-screenshots` | Codex / this project | Completed Native run 33294247633; artifact copies exist on GitHub; no local process uses the path | Delete local disposable copy |
| `/home/jason/codex-runs/garmin-caddie-surface-rerun-20260829` | Codex / this project | 303 MB; owner `jason`; contains only PNG/TXT/log output, no Git metadata, source files, lock/PID/socket, or active process | Archive under project `archives/`, verify checksum, then delete scratch |

The remote scratch archive is retained at
`/home/jason/garmin-ai-caddie-data/archives/garmin-caddie-surface-rerun-20260829.tar.zst`
with a sibling SHA-256 file. It is generated evidence, not source code.

## Explicitly protected

No other local or remote path was deleted. This includes all Git worktrees and
snapshots, the active API/database/web containers, the stopped rollback API
container/image, the `aicaddie-sync` images, named volumes, shared BuildKit
cache, Codex/Claude/Gemini sessions, other projects, and root-level files in
`/home/jason`.

## Result

- Local screenshot scratch is absent. The local repository's `.codex-tmp`
  footprint changed from 98 MB to 82 MB; no tracked files changed.
- The remote scratch source is absent. Its archive is 116,403,183 bytes,
  contains 318 entries, passes `zstd -t`, and has SHA-256
  `a61f8962dc4fa8a8feaf3934636bec61d6930dc144988dc69d37a646c57b33b3`.
- The archive checksum is also stored beside it as
  `/home/jason/garmin-ai-caddie-data/archives/garmin-caddie-surface-rerun-20260829.tar.zst.sha256`.
- The API health probe remained `status=ok` at revision
  `1af378b811cd25edae12285c5745aef1b57d7faf`; the API, database, and web
  containers remained healthy/running.
- No Docker resource was changed. During the operation an unrelated
  `movieclaw` container was running a root-owned pytest process; Docker volume
  usage increased independently, so that process and volume were left alone.
