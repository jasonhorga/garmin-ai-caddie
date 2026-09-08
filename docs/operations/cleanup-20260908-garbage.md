# Garmin AI Caddie Cleanup - 2026-09-08

This is the exact allow-list for the 2026-09-08 cleanup. It covers only
generated local scratch and expired, source-only review snapshots. It does not
authorize Docker, database, user-data, credential, deployment, active tunnel,
or rollback-resource changes.

## Allow-list

| Path | Owner / reason | Evidence before deletion |
| --- | --- | --- |
| `/home/ubuntu/claude-web-data/repo/garmin-ai-caddie/.codex-tmp/native-33648860821` | Codex / completed native evidence scratch | Generated screenshots/logs from an old run; not referenced by the current state ledger; no active process cwd or open handle; GitHub/native artifacts are the durable evidence. |
| `/home/ubuntu/claude-web-data/repo/garmin-ai-caddie/.codex-tmp/backend-authfix-20260906` | Codex / empty stale staging directory | No retained files and no active handle. |
| `/home/ubuntu/claude-web-data/repo/garmin-ai-caddie/.codex-tmp/public-ingress-20260907` | Codex / temporary local Caddy and cloudflared config | Superseded by the homeserver Quick Tunnel; no local service uses it and no credential bytes are present. |
| `*/__pycache__` under the canonical checkout | Python runtime cache | 7.1 MiB generated cache; no local Python process is running against the checkout. |
| `/home/ubuntu/claude-web-data/repo/garmin-ai-caddie/node_modules/.vite-temp` | Vite runtime cache | 4 KiB generated cache; dependencies and lockfiles remain. |
| `/home/jason/codex-runs/garmin-ai-caddie-map1-20260901` | Expired read-only MAP1 snapshot | 2026-08-31 snapshot, no open handle, no Git metadata, canonical source and reports retained. |
| `/home/jason/codex-runs/garmin-ai-caddie-map1-20260901-final` | Expired read-only MAP1 snapshot | 2026-08-31 snapshot, no open handle, no Git metadata, canonical source and reports retained. |
| `/home/jason/codex-runs/garmin-ai-caddie-map1-20260901-rerun` | Expired read-only MAP1 snapshot | 2026-08-31 snapshot, no open handle, no Git metadata, canonical source and reports retained. |
| `/home/jason/codex-runs/garmin-ai-caddie-map1-check-20260901` | Expired read-only MAP1 check snapshot | 2026-08-31 snapshot, no open handle, no Git metadata, canonical source and reports retained. |
| `/home/jason/codex-runs/garmin-ai-caddie-rel-20260901` | Expired read-only release snapshot | 2026-08-31 snapshot, no open handle, no Git metadata, release records retained. |
| `/home/jason/codex-runs/garmin-ai-caddie-zoom-20260901` | Expired read-only zoom snapshot | 2026-08-31 snapshot, no open handle, no Git metadata, MAP1 code and evidence retained. |
| `/home/jason/codex-runs/garmin-ai-caddie-syncfix-20260906` | Expired Codex source snapshot | `SESSION_MANIFEST.txt` expired 2026-09-07 12:20 UTC; resources `none`; no open handle. |

## Protected

- Canonical checkout, Git metadata, branch refs, and committed evidence.
- `.garmin_tokens`, `data`, `downloads`, `logs`, `output`, and all user data.
- `node_modules` except the exact `.vite-temp` cache listed above.
- Current Build 53 backend/API container, database/web containers, named
  volumes, rollback container/image, and Quick Tunnel session
  `codex-aicaddie-quicktunnel-http2-20260907`.
- Homeserver deployment records, private-volume backups, imports, archives,
  cleanup manifests, current source snapshot
  `garmin-ai-caddie-backend-f363872f-20260908`, MAP1 snapshot
  `garmin-ai-caddie-map1-20260902` (expires 2026-09-09), and the
  `phone-regression-20260908` snapshot.
- Other projects, active Codex/Claude sessions, and any path not listed above.

## Execution requirements

Before deletion, record exact byte counts, check open handles, and verify every
target is still an exact allow-listed path. Delete only those paths. Record
post-delete existence checks, service health, and before/after disk capacity in
the persistent homeserver cleanup manifest.

## Result

- At `2026-09-08T14:31:50Z`, the local targets were moved with `gio trash`.
  The moved working-tree bytes were 137,245,181 for the old Native scratch,
  temporary ingress directories, and Vite cache, plus 6,586,049 of Python
  bytecode caches. All listed local paths are absent; no tracked source changed.
- At `2026-09-08T14:32:39Z`, the seven remote snapshots were moved with
  `gio trash`: 319,044,908 bytes total across seven exact paths. All seven
  paths are absent and every protected snapshot remains present. The remote
  `SESSION_MANIFEST.txt` for `syncfix` had already expired on 2026-09-07.
- This cleanup intentionally used the OS trash rather than irreversible
  deletion. The local trash footprint is about 149 MiB; the homeserver trash
  retains the moved snapshots for recovery. No broad purge was run.
- Homeserver API health remained `status=ok` at revision
  `f363872f3af631edf0bcae5f9ab3e2c9fe28e0bb`; the current API, database, web
  containers, and Quick Tunnel session remained up. Homeserver free space was
  96 GiB after the operation.
- Raw command records are stored beside this file as `precheck.txt`,
  `execute.txt`, and `local-execute.txt`.
