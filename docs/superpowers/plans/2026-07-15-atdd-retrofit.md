# ATDD Plan — RAG Reliability Harness (retrofit)

**Date:** 2026-07-15  
**Skill:** flagrare-atdd-plan (applied after Superpowers implementation — process correction)  
**Status:** Acceptance tests define done; implementation already exists and must satisfy them.

## Scope

Formalize caller-visible done criteria for the offline RAG reliability harness: happy-path CI gate, three failure-mode catches, and zero-secret local/CI path. No new product features beyond making acceptance tests explicit and executable.

## Codebase Findings

- Entry points: `python -m ingest`, `python -m eval`, `python -m gates`, `python -m eval.simulate_regressions`, `make all`
- Core modules: `ingest/pipeline.py`, `retrieval/generate.py`, `eval/runner.py`, `eval/simulate_regressions.py`, `gates/run.py`
- Golden set: `data/golden/set.jsonl` (40 items); corpus: `data/corpus/fastapi` + `data/corpus/mutable/{v1,v2}`
- Existing unit/integration tests (~40) cover internals; sims already catch the three failure modes
- Prior process used Superpowers TDD tasks, not Flagrare ATDD-first planning
- Makefile currently calls bare `python` (can miss venv deps like PyYAML)

## Acceptance Tests

These are the done criteria. Each must pass without API keys.

### AT1 — Happy-path gate is green offline

Given the public FastAPI-style corpus with mutable **v2** ingested into `.index`,  
when a caller runs eval then the quality gate,  
then the gate **passes**, metrics include `drift_ok=true`, and no cloud LLM/embedding API is required.

### AT2 — Stale-context regressions fail the gate

Given an index built from mutable **v1** while the expected corpus fingerprint is **v2**,  
when the caller runs the stale-context simulation / gate check,  
then the gate **fails** (regression caught; blind/no-gate path does not catch it).

### AT3 — Ambiguous-ranking regressions fail the gate

Given a sabotaged ranking that demotes relevant chunks for ambiguous queries,  
when the caller runs the ambiguous-ranking simulation / gate check,  
then the gate **fails**.

### AT4 — Unsupported-answer regressions fail the gate

Given a generator forced to always answer (never refuse) on out-of-corpus questions,  
when the caller runs the unsupported-answer simulation / gate check,  
then the gate **fails** because refusal quality regresses.

### AT5 — Clone-to-green without secrets

Given a fresh install of package extras `[dev]` only,  
when the caller runs the full offline suite (`pytest` + ingest v2 + eval + gate),  
then all steps succeed with exit code 0 and the workflow does not reference required secrets.

## Implementation Plan

1. Encode AT1–AT5 as `tests/test_acceptance.py` (public behavior via module CLIs / public APIs).
2. Point Makefile at `.venv/bin/python` when present so AT5/`make all` is reliable.
3. Link acceptance tests from README (short “Acceptance criteria” pointer).
4. Keep existing unit tests; do not re-litigate internals already covered.

## Structural Decisions

- **Strategy pattern (light):** `VectorStore` protocol + in-memory default — swap pgvector later without changing eval/gate callers.
- **No other patterns warranted** for acceptance layer — thin integration tests over existing `simulate_*` / `check_gate` APIs are enough.

## Risks / Open Questions

- Blind “before” catch rate is definitionally 0% (`check_gate_blind`); disclose in README if interviewers dig in.
- `recall@k` implementation uses a capped denominator; renaming/documenting is optional polish, not AT-blocking.
- GitHub badge placeholder until remote exists — AT5 is local/CI definition; badge is packaging.
