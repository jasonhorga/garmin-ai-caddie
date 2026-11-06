# Manual GIR evidence audit

Run the read-only command on an offline copy of the runtime root, using the shared
Python runtime. The copy needs `data/players/*/{scorecards,shots}/*.json`; legacy
`data/{scorecards,shots}/*.json` is also inventoried. Geometry and credentials are
not needed. Redirect stdout to a private report outside the copied root:

```sh
AI_CADDIE_DATA_MODE=fixture <shared-python> ops/audit_manual_gir.py \
  --root <offline-copy> > <private-report.json>
```

There is no apply mode. The report includes every manual hole, existing GIR and
tee values, overlapping reason counts and source SHA256 digests. An unreadable
source or an empty inventory gives a nonzero exit status; inspect `errors` before
using the totals. Missing shots are explicitly counted. Non-manual cards are
excluded from hole counts.

`storedGirWithAimOnlyCandidate` finds existing GIR with no entered or safely
countable putts, a score above regulation, and only an aim at the regulation
stroke. `storedGirWithAmbiguousIndex` also covers existing GIR with missing
penalties, missing positions or extra positions. These are candidates for review,
not proof that the stored value is wrong. Play dates do not prove ingestion dates;
the inventory intentionally includes all dates. Decide whether to retain or clear
existing values after inspecting the private inventory. This command never does
either, and the backfill still preserves existing GIR.

`oneMissingPosition`, `missingPenaltiesKey`, `nonzeroPenalties`,
`positionCountMismatch` and `unknownLieBeforeFirstPutt` cover the known ambiguity
classes. The last flag means the prefix before the first recognized green putt
contains an unknown/green lie or an off-green putter, so the putt tail is not
reliably countable.

`penaltyTeeRecoveryUnproven` and `extraGreenTailRecoveryUnproven` count potential
tee-result recoveries. Stored shots have ordinal positions and a hole-level
penalty total, without a reliable per-stroke penalty or extra-tap attribution.
Green suffix positions may be real putts. These records therefore stay unknown;
do not deduplicate positions or infer penalty timing from their order. Explicitly
entered tee results remain preserved.
