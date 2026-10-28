# Versioned map backfill

Deploying and restarting the API starts the first pass automatically. The API scans installed
mesh files, queues missing current-style topo PNGs and current-matte Garmin WebPs, and resumes
the journal on subsequent restarts. A style/matte/source version change queues the affected
units again. Recent rounds take precedence over downloaded/offline courses, then other courses;
within each tier, locally cached JPEGs precede images that require a download.

The existing `AI_CADDIE_TOPO_RENDER_PROCESSES` pool must be enabled (the production entrypoint
already enables it). Backfill never falls back to CPU rendering in an API thread. It submits
one unit at a time, at lower priority than nearby preparation, sharing the existing cold-render
slots. Garmin work only downloads/mattes; projection registration stays on demand. Network
JPEG downloads start at most once every two seconds, using cached release metadata without
refreshing it. An active round, selected installation or tee request pauses the whole pass;
topo/package/Garmin HTTP activity also pauses it until ten seconds after the last request ends.
Already running child-process renders finish; foreground requests can use the other render slot.
Topo backfill and foreground requests share the same per-path singleflight: overlapping requests
for one hole reuse its render. A broken pool, a submission RuntimeError or cancellation outside
shutdown consumes one of that unit's three consecutive interruption attempts. Before reaching
the limit, the unit moves to the end of its priority tier, waits five seconds and uses a fresh
pool on retry; other units in the same tier run first. At the limit it becomes a durable failure
with a reason such as `render interrupted 3x: BrokenProcessPool`. A 180-second timeout fails
the unit immediately, with no automatic retry. Shutdown cancellations preserve the interruption
count and stop the pass. Success, terminal failure and force scans reset the count.
Discarding uses the existing nonblocking pool shutdown: queued futures are cancelled, while
already-running child tasks are not forcibly terminated.

`AI_CADDIE_DATA_MODE=fixture`, `AI_CADDIE_FIXTURE_MODE=1` and `AI_CADDIE_TEST_MODE=1` disable
automatic startup. Tests explicitly exercising the writer use a temporary
`AI_CADDIE_RENDER_BACKFILL_STATE`. Production keeps `data/render-backfill.json`, under the
existing persistent-volume `data/` link. A separate adjacent `.lock` file uses `flock` to reject
a second writer even when the journal is atomically replaced. Do not remove that lock file
while a writer is running. During container overlap the background worker retries the lease every
30 seconds for up to ten minutes; if the old container releases it, the new one resumes that
journal. After the limit it stops this attempt, clears queued scan/force flags and exposes
`writerState=blocked` and `lastError` in status. The admin POST can trigger another attempt.
The compact snapshot is checkpointed every 25 units or ten seconds and when the pass exits.
Beside it, `render-backfill.json.events.jsonl` appends and fsyncs each submission intent before
calling the pool and each outcome afterward. Keep both files on the persistent volume. Startup
replays uncheckpointed events; a submitted-but-unfinished unit consumes one interruption and
fails without submission if that reaches three. Completed events are not counted again. Snapshot
sequence numbers prevent replaying already-checkpointed events; checkpointing compacts the log.

Read progress from `GET /api/v2/admin/render-backfill` using the usual admin credentials.
It returns `total`, `done`, `pending`, `failed`, versions, the last persisted timestamp, and at
most 50 failed units with separate topo/Garmin reasons. Add `?detail=1` only when full per-hole
details are needed. Garmin errors distinguish download failures (including an HTTP status such
as 403 for a rejected signed link) from matte failures. Cached JPEGs are verified before use;
corrupt files are removed and downloaded again. Backfill uses `allow_fetch=False` and does not
refresh release metadata: after a signed URL expires with 403, open the course in the foreground
to refresh its release, then force backfill again. Signed URLs and their query strings are never
included in these diagnostics. For read-only offline inspection in the service runtime:

```bash
python ops/render_backfill.py --status
```

To rescan and retry failed units, send an authenticated
`POST /api/v2/admin/render-backfill?force=true`. It returns 202 immediately and starts (or
signals) the sole background worker, including after a previous pass has finished.
If a pass is already running, POST force only sets a flag: the current pass finishes before
the force rescan starts. It does not interrupt a render or immediately retry an earlier unit. With
`force=false`, existing failed units remain failed. The CLI has no enqueue, force or wait mode;
all writes belong to the API process. Both HTTP methods use the existing admin gate: under
the production profile a missing credential returns 401 when the admin token is configured.

Rendering failures and interruptions have terminal conditions, preserved across API restarts.
Journaled `done` units are trusted until a version
change or force scan; every boot does not revalidate their files. The regular foreground cache
path repairs missing/corrupt images on demand. For about 10,114 installed holes, the previous
two-worker estimate was roughly 3.4 hours and 1.9 GB. This pass deliberately uses at most one
worker at a time: allow roughly seven idle hours for topo plus Garmin/download time, and longer
while foreground activity pauses it. These are planning estimates, not a measured completion SLA.
