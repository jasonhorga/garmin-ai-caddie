# Garmin Sync Recovery: 2026-09-25

## Incident

The production API was switched to source revision
`d7f699712f7ac6cba41d97c420c405e090625caf`, but the matching
`aicaddie-sync:<revision>` image was not built. The active homeserver cron is
`37 * * * * /home/jason/aicaddie-sync.sh`; it correctly refused to use a stale
or moving `latest` image.

- Last successful sync before repair: `2026-09-24T19:39:28Z`.
- Failures for the previous API revision began at `20:37Z`.
- Failures for the active `d7f69971...` revision began at `2026-09-25T00:37Z`.
- Actual log: `/home/jason/aicaddie-sync.log`.
- The repository `ops/auto_sync.sh` and `~/garmin-auto-sync.log` are not the
  active production paths on this homeserver.

## Recovery Evidence

1. Capacity check passed with at least `80 GiB` free before the build.
2. From the revision-bearing homeserver checkout, ran:

   ```bash
   bash ops/build_sync_image.sh
   ```

   Result: `aicaddie-sync:d7f699712f7ac6cba41d97c420c405e090625caf`.

   Image digest:
   `sha256:82aa569d5f2a4fee5e6077461acf3d2375b6f0b1c12bce8ed58d146708a3ad8a`.

   The image label and active API container label both equal the full revision
   above.

3. Ran the active cron wrapper immediately:

   ```bash
   bash /home/jason/aicaddie-sync.sh
   ```

   The run completed with `sync ok`. The pipeline reported `498` summaries,
   `498` scorecards, `498` shot files, `new_round_count: 1`, and
   `remote_latest_round_id: 17711803`.

4. Authenticated production history checks returned round `17711803` first:
   `北京天竺黑骑士球员俱乐部`, `2026-09-25T07:58:12+08:00`, 18 holes, score 94.
   The service index and health endpoint remained HTTP 200.

## Prevention Changes

- `ops/complete_homeserver_api_deploy.sh` is the mandatory post-switch gate:
  it health-checks the API on the production port, invokes the immutable sync
  image builder, and fails the deployment if the matching tag is absent.
- The homeserver has a pinned operational copy under
  `/home/jason/garmin-ai-caddie-data/operations/deploy-tools/`, with
  `SOURCE_REVISION=c6f32dc1` recorded beside the scripts.
- `ops/build_sync_image.sh` resolves the production host port and refuses to
  guess when multiple release containers are running.
- `ops/homeserver_sync.sh` is the canonical production cron entrypoint. It
  checks API/sync revision equality before touching the private volume, writes
  `sync ok` and `done` on success, and sends deduplicated syslog/desktop/
  optional webhook alerts for missing, mismatched, or failed syncs.
- The installed `/home/jason/aicaddie-sync.sh` was atomically replaced with
  that wrapper. The prior file and pre-change crontab are retained under
  `/home/jason/garmin-ai-caddie-data/operations/sync-wrapper-backup-20260925/`.

No API container, Caddy route, named volume, or unrelated homeserver resource
was removed or restarted during recovery.
