# AI Provider And Fact-Bound Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Anthropic-only review code with a provider abstraction and generate review reports only from structured facts.

**Architecture:** Keep `ai_caddie/llm.py` as the report prompt boundary, add provider implementations under `ai_caddie/llm_providers.py`, and store generated reports as versioned fact-bound records. Tests use a static provider by default.

**Tech Stack:** Python 3.12, dataclasses, requests-compatible provider layer, unittest.

---

## Files

Create:

- `ai_caddie/llm_providers.py`
- `ai_caddie/reports.py`
- `tests/test_llm_providers.py`
- `tests/test_fact_bound_reports.py`

Modify:

- `ai_caddie/llm.py`
- `ai_review.py`
- `ai_caddie_analyze.py`
- `server_v2/models.py`
- `server_v2/main.py`

## Task 1: Provider Interfaces

- [ ] Write tests in `tests/test_llm_providers.py` for:
  - static provider returns configured reply
  - missing NIM key raises a secret-free error
  - provider selection rejects unsupported names
  - secret-like input is redacted from exception text
- [ ] Create `ai_caddie/llm_providers.py` with:

```python
@dataclass(frozen=True)
class LLMMessage:
    role: Literal["system", "user", "assistant"]
    content: str

class TextProvider(Protocol):
    model: str
    def chat(self, messages: Iterable[LLMMessage], max_tokens: int | None = None) -> str: ...
```

- [ ] Implement:
  - `StaticProvider`
  - `NvidiaNimProvider`
  - `AnthropicProvider`
  - `build_text_provider(settings=None)`
- [ ] Keep Gemini CLI OAuth as a named unsupported provider that returns a clear internal-only error until deliberately implemented.
- [ ] Run:

```bash
uv run python -m unittest tests.test_llm_providers -v
```

- [ ] Commit:

```bash
git add ai_caddie/llm_providers.py tests/test_llm_providers.py
git commit -m "feat: add llm provider abstraction"
```

## Task 2: Fact-Bound Report Builder

- [ ] Create `tests/test_fact_bound_reports.py` asserting:
  - generated report includes `factsUsed`
  - generated report includes `missingData`
  - report stores provider/model metadata
  - prompt excludes cookie/csrf/token/secret strings
- [ ] Create `ai_caddie/reports.py` with:
  - `build_round_report_facts(history_stats, round_id)`
  - `generate_report(facts, provider)`
  - `redact_private_text(text)`
- [ ] The report object must include:

```python
{
  "schema": "ai-caddie-review-report-v1",
  "kind": "round|trend",
  "provider": "...",
  "model": "...",
  "factsUsed": [...],
  "missingData": [...],
  "narrative": "...",
  "confidence": "low|medium|high"
}
```

- [ ] Run:

```bash
uv run python -m unittest tests.test_fact_bound_reports -v
```

- [ ] Commit:

```bash
git add ai_caddie/reports.py tests/test_fact_bound_reports.py
git commit -m "feat: add fact-bound report builder"
```

## Task 3: Replace Anthropic-Only Entry Points

- [ ] Modify `ai_caddie/llm.py` so `maybe_call_anthropic()` becomes a compatibility wrapper around `maybe_call_llm()`.
- [ ] Modify `ai_review.py` to use `build_text_provider()`.
- [ ] Modify `ai_caddie_analyze.py` help text from Anthropic-specific wording to configured provider wording.
- [ ] Add tests or adjust existing tests to assert old Anthropic compatibility still returns `(None, error)` when no provider key is present.
- [ ] Run:

```bash
uv run python -m unittest tests.test_llm_providers tests.test_fact_bound_reports -v
```

- [ ] Commit:

```bash
git add ai_caddie/llm.py ai_review.py ai_caddie_analyze.py tests
git commit -m "feat: route ai review through providers"
```

## Task 4: API Surface

- [ ] Add `GET /api/v2/reports/round/{round_id}` returning existing/stub generated reports.
- [ ] Add `POST /api/v2/reports/round/{round_id}/generate` using configured provider.
- [ ] In tests, patch provider to `StaticProvider`.
- [ ] Ensure no endpoint response contains secret terms.
- [ ] Run:

```bash
uv run python -m unittest discover -s tests -v
```

- [ ] Commit:

```bash
git add server_v2 ai_caddie tests
git commit -m "feat: expose fact-bound review reports"
```

## Task 5: Verification

- [ ] Run full backend tests.
- [ ] Run `py_compile` on `ai_caddie/llm_providers.py`, `ai_caddie/reports.py`, `ai_caddie/llm.py`.
- [ ] Do not call live providers unless `AI_CADDIE_LIVE_LLM_TEST=1`.
