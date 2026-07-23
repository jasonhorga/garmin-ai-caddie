# Plan 1 Task 1 Authority Gate Verification

Date: 2026-07-23 UTC
Verified production HEAD: `71149b78e45f67dec00511ea10502647e06e8453`

## Bounded requirement and exclusions

Task 1 establishes the fail-closed authority boundary for the canonical
contract lane. It must pin authoritative/evidence inputs, validate the
authority manifest and protected paths, couple generated sources to an owned
output, preserve exact changed-path bytes, and execute the same policy in CI
for pull requests and manual runs.

The task does not define CanonicalJSON runtime semantics, typed IDs, registry
contents, event durability, or product behavior. Those remain in later Plan 1
tasks.

## Production evidence

The dedicated implementation and remediation history is:

- `41fca67` — initial canonical authority manifest, checker, CI gate, and tests;
- `3f6016e` — invalid-diff-range fail-closed behavior;
- `362f26c` — manifest, provenance, path, schema, and generated-group hardening;
- `a28ae70` — additional authority-policy and CI execution boundary coverage;
- `819f9f2` — closure of specification and quality review findings;
- `71149b7` — rename-out defense and deterministic CLI diagnostics.

At the verified HEAD:

- `.github/workflows/ci.yml` uses full-history checkout, an event-specific
  three-dot/two-dot/fallback range, `set -euo pipefail`,
  `git diff --no-renames --name-only -z`, and the authority CLI;
- `tools/contracts/check_authority.py` validates pinned bytes and Git objects,
  manifest structure, canonical-root containment, legacy-adapter fences,
  forbidden symbols, and generated source/output ownership;
- the CLI catches only `AuthorityViolation`, emits one deterministic diagnostic
  with exit code 1, and leaves unexpected exceptions visible;
- `tests/test_ci_workflow.py` executes the checked-in CI shell step against a
  real temporary Git repository. Its rename fixture proves normal rename
  detection reports only the destination while the checked-in `--no-renames`
  workflow still rejects moving a canonical source outside the protected
  pattern;
- `tests/test_contract_authority.py` covers NUL framing, escaped and malformed
  paths, source-commit/blob/SHA pins, duplicate and malformed JSON, schema refs,
  symlinks, UTF-8, adapter constraints, generated ownership, and exact CLI
  diagnostics.

The real-Git rename fixture and malformed-policy fixtures are mutation-backed
RED evidence: removing `--no-renames`, removing generated-source coupling, or
restoring broad CLI exception handling makes the corresponding focused test
fail.

## Independent reviews

- Requirement/specification re-review: `SPEC_PASS`; no open Critical or
  Important finding.
- Code-quality re-review at `71149b7`: `QUALITY_PASS`; no Critical, Important,
  or Minor finding.

The reviews specifically rechecked the CI range policy, `pipefail`, NUL
framing, actual-Git rename behavior, generated source/output coupling, and CLI
exception boundary.

## Homeserver verification

Verification ran on host `homeserver` in the detached, clean exact clone:

`/home/jason/codex-runs/garmin-ai-caddie-rootverify-71149b7-9d3c`

The clone resolved to `71149b78e45f67dec00511ea10502647e06e8453`, and
Git object `38903466c39a06e17ca03f94e7f90fd0f216cbec` required by the provenance
pin was present. The project Python environment supplied `pathspec 0.12.1`;
all code under test came from the exact clone.

Commands and results:

```text
git diff --no-renames --name-only -z HEAD^..HEAD |
  python tools/contracts/check_authority.py
  -> exit 0

python -m py_compile \
  tools/contracts/check_authority.py \
  tests/test_contract_authority.py \
  tests/test_ci_workflow.py
  -> exit 0

python -m unittest tests.test_contract_authority tests.test_ci_workflow -q
  -> Ran 92 tests in 1.932s; OK

git diff --check
  -> exit 0

git status --porcelain
  -> empty
```

## Verified file digests

| Artifact | SHA-256 |
|---|---|
| `.github/workflows/ci.yml` | `66783d948227f3b4fd81abe5348a4f2b37145b07b4a2f74117138a6c354636f0` |
| `contracts/canonical/authority.json` | `470bf2e94e3162ffcae95d4d8d3b525b0d8b5258de1ed648444707bd453935a6` |
| `tools/contracts/check_authority.py` | `a02b152f94ebd90eaf33d57a618311041a4058ce411391d5247a388c2f6d19f4` |
| `tests/test_contract_authority.py` | `4883e66f45d6c476a8dfaf916906d92bf93c221ad7d3dda600448c296d0fa702` |
| `tests/test_ci_workflow.py` | `cbeb5bc94aaf570bdcd1a6ad81e5f26cf362567912baf06a4276514823dd9ce0` |

## Gate result

Plan 1 Task 1 satisfies the Execution Index definition of `VERIFIED`. POP
returns to the canonical reliability foundation and selects Plan 1 Task 2.
