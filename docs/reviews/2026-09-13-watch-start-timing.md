# Watch Startup Timing Evidence (2026-09-13)

## Scope

- Workflow: `Watch Runtime Visual Check`, run `34747551313`
- Measurement commit: `ed879184d164060046509ec209887a053f38ecd7`
- API revision: `17ad4e66871126730c9fca9246fee884af309b2f`
- API origin: `https://right-exhibits-colleges-dated.trycloudflare.com`
- Device: Apple Watch Series 9 (45mm) watchOS simulator on GitHub `macos-15`
- Start timestamp: after course search and tee selection, immediately before
  `startCourseImmediately`; this is the product start action boundary, not the
  time spent searching for a course.

## Measured milestones

| Milestone | Elapsed from Start (ms) | Interpretation |
|---|---:|---|
| `local_round_shell` | 63 | 18-hole provisional round exists locally |
| `first_hole_facts` | 1,369 | first-hole distance/facts available |
| `first_hole_map` | 1,375 | first drawable map state; coverage was `partial` |
| `first_hole_caddie` | 1,376 | caddie state became available; this capture reported `options=0`, so it is not proof that a full multi-option list was ready |
| `complete_course` | 85,245 | all 18 precise course states returned |

The timing marker SHA-256 is
`b0e6d831c5edddbed09f2aaa0cf9bac2fbddc665aaf98f373d1b23bac39481c2`.
The uploaded `watch-runtime-evidence` artifact is ID `10315165738`, digest
`sha256:3d9644c9ac86461970b08371f9ea21c05c2f62074cb865ef7021cb4f69e65a37`.

## Limitations

This is one simulator run over a public Quick Tunnel, not a physical Watch
measurement and not a p50/p95. It is useful for ordering the stages and showing
the current full-course tail, but it must not be presented as S70-equivalent
hardware timing. The prior attempt (`34746814418`) ended after the provisional
shell because the harness treated the first marker line as terminal; it is
excluded from the timing result.

The public S70 material reviewed for this slice contains no reproducible,
stage-by-stage startup seconds. A fair comparison still requires a physical
S70 and physical Watch/iPhone, GPS already locked, the same course, and a
shared ready event (hole 1 facts + usable map). At least 20 repetitions are
needed before reporting p95.
