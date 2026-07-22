# RAG Reliability Harness

Offline-first RAG reliability loop: detect corpus drift → re-ingest → eval (golden + traffic sample) → gate → alert with ownership — no API keys required.

![eval-gate](https://github.com/danteacosta/rag-reliability-harness/actions/workflows/eval.yml/badge.svg)

## Flow

```mermaid
flowchart LR
  A[detect drift] --> B[reingest]
  B --> C[retrieve + generate]
  C --> D[eval gate]
  D -->|fail| E[alert + owners]
  D -->|pass| F[healthy status]
```

Closed loop: fingerprint the corpus, rebuild the index when it drifts, score golden + online traffic sample (latency p50/p95), fail the gate on regression, and emit an alert with owning surface (`ingest` / `retrieval` / `generate` / `infra`).

## Before / after (synthetic, reproducible)

Injected regressions on a public FastAPI-style fixture corpus (no company data). Reproduce with `make simulate`.

| Failure mode | Blind path (before) | Full gate (after) |
|---|---|---|
| stale-context | 0% catch | 100% catch |
| ambiguous-ranking | 0% catch | 100% catch |
| unsupported-answer | 0% catch | 100% catch |

## 3 failure modes this harness catches

### 1. stale-context

**Example:** Index still has `mutable/v1` (`default_request_timeout_seconds = 30`) while gold expects `v2` (`60`). Answers look fluent but cite a stale truth; corpus fingerprint no longer matches.

**Caught by:** `tests/test_simulate.py::test_stale_context_sim_caught` and `make simulate` (`run_stale_scenario` → `drift_ok=False` → gate fail).

### 2. ambiguous-ranking

**Example:** Question about the HTTP *request* timeout competes with connection-pool / idle-deadline distractors. If ranking flips, MRR and precision slip even when the right chunk is somewhere in the top-k.

**Caught by:** `tests/test_simulate.py::test_ambiguous_ranking_sim_caught` and `make simulate` (`run_ambiguous_scenario` reverses hit order → gate fail).

### 3. unsupported-answer

**Example:** “What is the list price of Acme Cloud Enterprise?” — not in the corpus. Gold expects `INSUFFICIENT_CONTEXT`. A generator that always answers invents unsupported text.

**Caught by:** `tests/test_simulate.py::test_unsupported_always_answer_caught` and `make simulate` (`force_answer=True` → `refusal_accuracy` drop → gate fail).

## CI

![eval-gate](https://github.com/danteacosta/rag-reliability-harness/actions/workflows/eval.yml/badge.svg)

GitHub Actions runs the offline suite on every push and pull request: `pytest` → ingest → eval → gates → **closed loop**. No secrets.

## Acceptance criteria (ATDD)

Done is defined by caller-visible acceptance tests:

**Gate (`tests/test_acceptance.py`)**
1. Happy-path offline gate passes (`drift_ok`, no API keys)
2. Stale-context injection fails the gate
3. Ambiguous-ranking injection fails the gate
4. Unsupported always-answer injection fails the gate
5. Full suite + CI workflow require no secrets

**Closed loop (`tests/test_loop_acceptance.py`)**
1. Stale index triggers re-ingest and healthy gate
2. Gate failure writes alert JSON with owners
3. Healthy loop writes status without requiring a webhook
4. Failure reasons map to ingest/retrieval/generate/infra
5. Eval reports latency p50/p95

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make all
```

Useful targets: `make test`, `make ingest`, `make eval`, `make gate`, `make simulate`, `make loop`.

## Attribution & optional adapters

- FastAPI-style docs under `data/corpus/fastapi/` are original paraphrases — see [`data/ATTRIBUTION.md`](data/ATTRIBUTION.md).
- **Optional pgvector:** `docker compose up -d`, set `DATABASE_URL` / `PGVECTOR_DSN` (see `.env.example`). Adapter raises `NotConfiguredError` without a DSN; CI uses the in-memory store.
- **Optional Langfuse:** set `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY`. Without keys the tracer no-ops and records local spans only.
- **Optional alert webhook:** set `ALERT_WEBHOOK_URL` for `make loop`. On gate failure the loop always writes `loop/last_alert.json` with owners; webhook POST is best-effort.
