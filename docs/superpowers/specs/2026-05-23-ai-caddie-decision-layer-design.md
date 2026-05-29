# AI Caddie Decision Layer v1 Design

## Goal

Add a decision-centered layer to the existing AI Caddie app. The first version
focuses on tee-shot planning and post-hole decision judgment. It should turn the
current geometry, route, shot, and club facts into a verifiable caddie decision:
what to do, what to avoid, why, and how the actual shot compared.

## Product Principle

The core product object is a decision, not a dashboard, round, or report.

A useful caddie recommendation must be falsifiable after the round. It should
define the planned option, target carry, recommended club set, unacceptable
risks, acceptable uncertainty, supporting evidence, and confidence. After actual
shot data exists, the system should classify the result as:

- `strategy`: the player chose a materially different or riskier plan and was
  punished by a known risk.
- `execution`: the player followed the selected plan but missed into a known
  risk or poor surface.
- `info_gap`: the system lacks enough data to judge.
- `variance`: the result is not clearly explained by a strategy or execution
  failure.

## Scope

In scope:

- Add `DecisionPlan` JSON for tee-shot planning.
- Add `DecisionOutcome` JSON for post-hole judgment.
- Attach both objects to `build_hole_analysis()`.
- Surface decision summaries in round analysis.
- Show a compact decision card in the Web MVP.
- Cover the new decision rules with synthetic unit tests that do not depend on
  private Garmin data.

Out of scope:

- Full every-shot strategy.
- Live GPS on-course workflow.
- Long-term model mutation or persisted learning.
- LLM-first strategy selection.
- Broad UI redesign of the whole Web app.

## Data Flow

Existing flow:

```text
Garmin/manual hole
+ prodgeometry
+ club profiles
=> hole analysis
=> SVG/GeoJSON/route candidates
```

New flow:

```text
hole analysis
+ candidate routes
+ club profiles
+ data quality
=> DecisionPlan

DecisionPlan
+ actual first shot
+ feature/risk classification
=> DecisionOutcome
```

The LLM wording layer can consume these objects later, but the decision engine
must be deterministic and testable without an API key.

## Interfaces

Create `ai_caddie/decision.py`.

Public functions:

- `build_decision_plan(analysis: dict[str, Any]) -> dict[str, Any]`
- `judge_decision_outcome(plan: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]`

`DecisionPlan` schema:

- `schema`: `ai-caddie-decision-plan-v1`
- `phase`: `tee_shot`
- `context`: round, course, hole, global/local hole, tee box
- `options`: safe/stock/attack options derived from candidate routes
- `selectedOptionId`
- `selectedOption`
- `forbiddenZones`
- `acceptableMiss`
- `evidence`
- `confidence`

`DecisionOutcome` schema:

- `schema`: `ai-caddie-decision-outcome-v1`
- `phase`: `tee_shot`
- `plannedOptionId`
- `actualOptionId`
- `executionMatch`
- `result`
- `failureType`
- `modelUpdateSuggestion`

## Selection Rules

Route mapping:

- `conservative_layup` -> `safe`
- `stock_line` -> `stock`
- `aggressive_line` -> `attack`

Selected option:

- Prefer `stock` when its risk score is within one point of the safest option.
- Otherwise choose the lowest-risk option.
- If no route candidates exist, return no selected option and low confidence.

Club recommendation:

- Use club profiles whose median distance is within a useful range of the
  option carry.
- Exclude unknown clubs and putter from tee-shot recommendations.
- Fall back to the route label or first recorded club when profiles are absent.

Confidence:

- Start from `analysis.dataQuality.confidence`.
- Degrade when geometry, route candidates, or club samples are missing.
- Return explicit confidence reasons.

## Web UX

Add a compact decision card above the existing overlay:

- Main caddie instruction: selected option label, carry, and clubs.
- Avoid list from forbidden zones.
- Evidence list, capped to three items.
- Confidence and reasons.
- Outcome judgment when actual shot data exists.

Keep current overlay, shots table, and candidate route table. The purpose is to
introduce the decision layer without replacing the current diagnostic views.

## Testing

Add synthetic tests under `tests/test_decision_layer.py`.

Required tests:

- Stock is selected when it is almost as safe as the safe option.
- Safe is selected when stock is materially riskier.
- Club recommendations prefer matching median-distance clubs.
- Outcome is `execution` when the selected plan is followed but the first shot
  finishes in or near a known risk.
- Outcome is `strategy` when the player takes a non-selected riskier option and
  is punished by a known risk.
- Outcome is `info_gap` when there is no usable first shot.

Run:

```bash
uv run python -m unittest tests.test_decision_layer -v
uv run python -m unittest discover -s tests -v
uv run python -m py_compile ai_caddie/decision.py ai_caddie/analysis.py ai_caddie_web.py
```
