# RAG Reliability Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a polished offline-first RAG reliability harness with golden-set eval, CI regression gate, and a README that sells the process in ~40 seconds.

**Architecture:** Thin Python package: hash n-gram embeddings → in-memory vector store → rewrite + retrieve → extractive generate → metrics + gate. Mutable corpus v2 is the happy path; regression sims inject stale / bad-rank / always-answer failures. Optional pgvector and Langfuse are stubs/adapters only.

**Tech Stack:** Python 3.11+, numpy, pyyaml, pytest, langchain-core (thin), GitHub Actions. No API keys in CI.

**Spec:** `docs/superpowers/specs/2026-07-15-rag-reliability-harness-design.md`

---

## File structure

| Path | Responsibility |
|------|----------------|
| `pyproject.toml` | Package metadata, deps, pytest entry |
| `Makefile` | `ingest`, `eval`, `gate`, `simulate`, `test` |
| `rag_harness/__init__.py` | Package version |
| `rag_harness/types.py` | `Chunk`, `GoldenItem`, `RetrievalHit` dataclasses |
| `rag_harness/embeddings/hash_embedder.py` | Char n-gram hashing trick (dim=256, n=3..5) |
| `rag_harness/store/memory.py` | In-memory cosine store (CI default; intentional stand-in for Chroma/FAISS — same `VectorStore` protocol) |
| `rag_harness/store/protocol.py` | `VectorStore` protocol |
| `rag_harness/store/pgvector.py` | Optional stub/adapter (raises unless configured) |
| `ingest/chunker.py` | Markdown → chunks with stable IDs |
| `ingest/pipeline.py` | Load corpus, embed, upsert, write fingerprint |
| `ingest/fingerprint.py` | Corpus fingerprint hash |
| `retrieval/rewrite.py` | Synonym map rewrite |
| `retrieval/cache.py` | Exact-query cache stub |
| `retrieval/retriever.py` | Top-k retrieve + scores; thin `langchain_core.retrievers.BaseRetriever` wrapper |
| `retrieval/generate.py` | Extractive answer / `INSUFFICIENT_CONTEXT` |
| `eval/metrics.py` | precision@k, recall@k, MRR, groundedness, refusal_accuracy, drift |
| `eval/runner.py` | Run golden set → metrics dict |
| `eval/simulate_regressions.py` | Inject 3 failure modes → before/after catch rates |
| `eval/thresholds.yaml` | Absolute floors + max slip |
| `eval/baselines/ci.json` | Committed happy-path baseline (filled after first green run) |
| `gates/run.py` | CLI: load metrics, compare thresholds/baseline, exit code |
| `observability/tracing.py` | No-op tracer + Langfuse stub |
| `data/corpus/fastapi/*.md` | ~8–10 attributed FastAPI-style docs |
| `data/corpus/mutable/v1/*.md` | Stale truths (e.g. timeout 30s) |
| `data/corpus/mutable/v2/*.md` | Current truths (timeout 60s) |
| `data/golden/set.jsonl` | ~40 golden items |
| `data/ATTRIBUTION.md` | Doc sources |
| `tests/…` | Unit + integration tests mirroring modules |
| `.github/workflows/eval.yml` | Offline CI: test → ingest → eval → gate |
| `docker-compose.yml` | Optional Postgres+pgvector (not used in CI) |
| `README.md` | 40s narrative (order locked in spec) |
| `LINKEDIN_DRAFT.md` | Bonus post draft |
| `.gitignore` | `.venv`, `__pycache__`, `.index/`, etc. |

**Locked constants (implement exactly):**

- `K = 5`
- `REFUSAL = "INSUFFICIENT_CONTEXT"`
- `REFUSAL_SCORE_THRESHOLD = 0.12` (cosine; tune only if tests demand, document change)
- Hash embedder: `DIM=256`, n-grams `range(3, 6)`
- Happy-path mutable version: `v2`
- Retrieval metrics cohort: non-empty `relevant_chunk_ids` only

---

### Task 1: Scaffold package + types

**Files:**
- Create: `pyproject.toml`, `Makefile`, `.gitignore`, `rag_harness/__init__.py`, `rag_harness/types.py`
- Test: `tests/test_types.py`

- [ ] **Step 1: Write failing test for GoldenItem parsing**

```python
# tests/test_types.py
from rag_harness.types import GoldenItem

def test_golden_item_from_dict():
    item = GoldenItem.from_dict({
        "id": "q001",
        "question": "What is the default timeout?",
        "answer": "60s",
        "relevant_chunk_ids": ["mutable.config.01"],
        "failure_mode": "stale-context",
    })
    assert item.id == "q001"
    assert item.failure_mode == "stale-context"
    assert item.relevant_chunk_ids == ["mutable.config.01"]
```

- [ ] **Step 2: Run test — expect fail (module missing)**

Run: `python -m pytest tests/test_types.py -v`  
Expected: FAIL / import error

- [ ] **Step 3: Implement scaffold**

`pyproject.toml` (minimal):

```toml
[project]
name = "rag-reliability-harness"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "numpy>=1.26",
  "pyyaml>=6.0",
  "langchain-core>=0.2",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]
pgvector = ["psycopg[binary]>=3.1"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["rag_harness*", "ingest*", "retrieval*", "eval*", "gates*", "observability*"]
```

Implement `GoldenItem`, `Chunk`, `RetrievalHit` dataclasses in `rag_harness/types.py` with `from_dict`.

- [ ] **Step 4: Run test — expect pass**

Run: `python -m pytest tests/test_types.py -v`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml Makefile .gitignore rag_harness tests/test_types.py
git commit -m "chore: scaffold package and core types"
```

---

### Task 2: Hash embedder + in-memory store

**Files:**
- Create: `rag_harness/embeddings/hash_embedder.py`, `rag_harness/store/protocol.py`, `rag_harness/store/memory.py`
- Test: `tests/test_embeddings.py`, `tests/test_store.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_embeddings.py
from rag_harness.embeddings.hash_embedder import HashEmbedder

def test_similar_text_ranks_higher_than_unrelated():
    emb = HashEmbedder(dim=256)
    q = emb.embed("default request timeout seconds")
    near = emb.embed("The default request timeout is 60 seconds.")
    far = emb.embed("OAuth2 password flow with JWT tokens")
    assert emb.cosine(q, near) > emb.cosine(q, far)

def test_embed_is_deterministic():
    emb = HashEmbedder(dim=256)
    assert (emb.embed("abc") == emb.embed("abc")).all()
```

```python
# tests/test_store.py
from rag_harness.embeddings.hash_embedder import HashEmbedder
from rag_harness.store.memory import InMemoryVectorStore
from rag_harness.types import Chunk

def test_topk_returns_lexical_match_first():
    emb = HashEmbedder()
    store = InMemoryVectorStore(emb)
    store.upsert([
        Chunk(id="a", doc_id="d1", text="OAuth2 password flow", metadata={}),
        Chunk(id="b", doc_id="d2", text="Default request timeout is 60 seconds", metadata={}),
    ])
    hits = store.similarity_search("request timeout", k=2)
    assert hits[0].chunk_id == "b"
```

- [ ] **Step 2: Run tests — expect fail**

Run: `python -m pytest tests/test_embeddings.py tests/test_store.py -v`

- [ ] **Step 3: Implement HashEmbedder + InMemoryVectorStore**

- Normalize text: lowercasing, collapse whitespace
- Hash each char n-gram `n in (3,4,5)` into `dim` bins; L2-normalize
- Store keeps vectors + chunk map; `similarity_search` returns ranked `RetrievalHit(chunk_id, score, text, metadata)`

- [ ] **Step 4: Run tests — expect pass**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add hash embedder and in-memory vector store"
```

---

### Task 3: Ingest pipeline + fingerprint

**Files:**
- Create: `ingest/chunker.py`, `ingest/fingerprint.py`, `ingest/pipeline.py`, `ingest/__main__.py`
- Test: `tests/test_ingest.py`
- Create fixture docs under `tests/fixtures/corpus/` (tiny) for unit tests

- [ ] **Step 1: Write failing test**

```python
def test_fingerprint_changes_when_doc_changes(tmp_path):
    # write doc A, ingest, fingerprint F1
    # change doc text, ingest, fingerprint F2
    assert F1 != F2

def test_chunk_ids_stable_across_runs(tmp_path):
    # same content → same chunk ids
```

- [ ] **Step 2: Run — expect fail**

- [ ] **Step 3: Implement**

- Chunker: split on `##` headings or ~400 char windows with 40 char overlap; IDs like `{doc_stem}.{idx:02d}`
- Pipeline args: `--corpus-root data/corpus --mutable-version v2 --index-dir .index`
- Default mutable path: include `fastapi/` + `mutable/{version}/`
- Write `.index/fingerprint.json` and persist store (numpy `.npz` + chunks json)

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: ingest pipeline with corpus fingerprint"
```

---

### Task 4: Retrieval, rewrite, generate

**Files:**
- Create: `retrieval/rewrite.py`, `retrieval/cache.py`, `retrieval/retriever.py`, `retrieval/generate.py`
- Test: `tests/test_retrieval.py`, `tests/test_generate.py`

- [ ] **Step 1: Failing tests**

```python
def test_rewrite_expands_deps_alias():
    assert "dependencies" in rewrite("how do deps work?")

def test_generate_refuses_when_scores_low():
    hits = [RetrievalHit(chunk_id="x", score=0.01, text="unrelated", metadata={})]
    assert generate_answer("pricing of Acme Cloud?", hits) == "INSUFFICIENT_CONTEXT"

def test_generate_extracts_from_top_hit():
    hits = [RetrievalHit(chunk_id="b", score=0.9, text="Default request timeout is 60 seconds.", metadata={})]
    ans = generate_answer("What is the default request timeout?", hits)
    assert "60" in ans
    assert ans != "INSUFFICIENT_CONTEXT"

def test_harness_retriever_returns_langchain_documents():
    from langchain_core.retrievers import BaseRetriever
    from langchain_core.documents import Document
    # build tiny store with one chunk, wrap in HarnessRetriever
    r = build_test_retriever()
    assert isinstance(r, BaseRetriever)
    docs = r.invoke("timeout")
    assert isinstance(docs[0], Document)
```

- [ ] **Step 2: Run — expect fail**

- [ ] **Step 3: Implement**

- Synonym map: `deps→dependencies`, `auth→authentication`, `mw→middleware`, etc.
- Cache: dict keyed by exact rewritten query string (stub OK)
- `generate_answer`: if `hits[0].score < 0.12` or no hits → `INSUFFICIENT_CONTEXT`; else return first 1–2 hit texts joined (extractive)
- `HarnessRetriever(BaseRetriever)`: `_get_relevant_documents` wraps rewrite + store search → `Document` list (portfolio signal; eval may call store directly)

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: retrieval rewrite and extractive generate"
```

---

### Task 5: Corpus + golden set (content)

**Files:**
- Create: `data/corpus/fastapi/*.md` (8–10 files), `data/corpus/mutable/v1/config.md`, `data/corpus/mutable/v2/config.md`, `data/golden/set.jsonl`, `data/ATTRIBUTION.md`

- [ ] **Step 1: Author FastAPI-style docs** (original paraphrases attributed to FastAPI public docs themes: routing, path params, dependencies, security/OAuth2, middleware, CORS, background tasks, settings)

- [ ] **Step 2: Author mutable docs**

`v1`: `default_request_timeout_seconds = 30`  
`v2`: `default_request_timeout_seconds = 60`  
Plus one distractor-friendly pair for ambiguous ranking (two chunks sharing “timeout” / “deadline” language; only one is request timeout).

- [ ] **Step 3: Author ~40 golden JSONL rows**

Target mix:
- ~28 `failure_mode=none` with non-empty `relevant_chunk_ids`
- ~4 `stale-context` (gold = v2 chunk ids / “60”)
- ~4 `ambiguous-ranking`
- ~4 `unsupported-answer` (empty `relevant_chunk_ids`, answer=`INSUFFICIENT_CONTEXT`)

- [ ] **Step 4: Smoke ingest**

Run: `python -m ingest --mutable-version v2`  
Expected: `.index/` created, fingerprint written

- [ ] **Step 5: Commit**

```bash
git commit -m "data: add FastAPI corpus, mutable versions, golden set"
```

---

### Task 6: Metrics + eval runner

**Files:**
- Create: `eval/metrics.py`, `eval/runner.py`, `eval/__main__.py`
- Test: `tests/test_metrics.py`

- [ ] **Step 1: Failing metric tests**

```python
def test_recall_at_k():
    assert recall_at_k(["a", "b"], ["b", "c", "d"], k=2) == 0.5

def test_precision_at_k():
    assert precision_at_k(["a", "x"], ["a", "b"], k=2) == 0.5

def test_mrr():
    assert mrr(["x", "a"], ["a"]) == 0.5

def test_retrieval_metrics_skip_empty_relevant():
    items = [
        {"relevant_chunk_ids": [], "retrieved": ["a"]},
        {"relevant_chunk_ids": ["a"], "retrieved": ["a", "b"]},
    ]
    m = aggregate_retrieval_metrics(items, k=2)
    # only second item contributes
    assert m["recall@2"] == 1.0

def test_refusal_accuracy():
    assert refusal_accuracy([
        {"relevant_chunk_ids": [], "answer": "INSUFFICIENT_CONTEXT"},
        {"relevant_chunk_ids": [], "answer": "something made up"},
    ]) == 0.5

def test_groundedness_refusal_is_grounded():
    assert groundedness("INSUFFICIENT_CONTEXT", contexts=["x"]) == 1.0

def test_groundedness_lexical_containment():
    # non-refusal: answer tokens must appear in joined contexts
    assert groundedness("timeout is 60 seconds", contexts=["Default request timeout is 60 seconds."]) == 1.0
    assert groundedness("timeout is 99 hours", contexts=["Default request timeout is 60 seconds."]) < 1.0

def test_drift_match():
    assert drift_ok(active_fp="abc", expected_fp="abc") is True
    assert drift_ok(active_fp="abc", expected_fp="xyz") is False
```

- [ ] **Step 2: Run — expect fail**

- [ ] **Step 3: Implement metrics + runner**

Runner: load golden → retrieve/generate per item → aggregate → write `eval/last_run.json` including:
- retrieval/generation metrics
- `fingerprint_active`: hash read from `.index/fingerprint.json` after ingest
- `fingerprint_expected`: **recompute at eval time** by hashing the on-disk corpus roots `data/corpus/fastapi` + `data/corpus/mutable/v2` (same algorithm as ingest) — do not commit a separate expected hash file
- `drift_ok`: `fingerprint_active == fingerprint_expected`

- [ ] **Step 4: Tests pass + one full eval smoke**

Run: `python -m eval`  
Expected: JSON metrics printed; recall@5 reasonably high on happy path

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: eval metrics and golden-set runner"
```

---

### Task 7: Gate + thresholds + baseline

**Files:**
- Create: `gates/run.py`, `gates/__main__.py`, `eval/thresholds.yaml`, `eval/baselines/ci.json`
- Test: `tests/test_gate.py`

- [ ] **Step 1: Failing gate tests**

```python
def test_gate_fails_below_threshold():
    assert check_gate({"recall@5": 0.1, "drift_ok": True}, thresholds, baseline)[0] is False

def test_gate_fails_on_baseline_slip():
    thresholds = {
        "require_drift_ok": True,
        "floors": {"recall@5": 0.50, "mrr": 0.40, "groundedness": 0.50, "refusal_accuracy": 0.50, "precision@5": 0.10},
        "max_slip": {"recall@5": 0.05, "mrr": 0.05, "groundedness": 0.05, "refusal_accuracy": 0.05},
    }
    baseline = {"recall@5": 0.90, "mrr": 0.80, "groundedness": 0.95, "refusal_accuracy": 1.0, "precision@5": 0.40}
    current = {**baseline, "recall@5": 0.80, "drift_ok": True}  # slip 0.10 > 0.05
    assert check_gate(current, thresholds, baseline)[0] is False

def test_gate_fails_when_drift_ok_false():
    happy_enough_metrics = {
        "recall@5": 0.90, "precision@5": 0.40, "mrr": 0.80,
        "groundedness": 0.95, "refusal_accuracy": 1.0, "drift_ok": False,
    }
    assert check_gate(happy_enough_metrics, thresholds, baseline)[0] is False
```

- [ ] **Step 2: Implement thresholds**

```yaml
# eval/thresholds.yaml
k: 5
require_drift_ok: true   # happy-path CI must have fingerprint match
floors:
  recall@5: 0.70
  precision@5: 0.20
  mrr: 0.55
  groundedness: 0.85
  refusal_accuracy: 0.90
max_slip:
  recall@5: 0.05
  mrr: 0.05
  groundedness: 0.05
  refusal_accuracy: 0.05
```

Gate logic: fail if `require_drift_ok` and `metrics["drift_ok"] is False`; else check floors + slip.
- [ ] **Step 3: Run happy-path eval; write real `eval/baselines/ci.json` from output**

- [ ] **Step 4: `python -m gates` exits 0 on happy path**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: CI quality gate with thresholds and baseline"
```

---

### Task 8: Failure-mode regression simulations

**Files:**
- Create: `eval/simulate_regressions.py`
- Test: `tests/test_simulate.py`

**Contracts (locked):**

- A **scenario** produces one metrics dict (same shape as `eval/last_run.json`).
- **Detector (after / full harness):** `caught = check_gate(metrics, thresholds, baseline)[0] is False`  
  (gate fails ⇒ regression caught). For stale, also assert `metrics["drift_ok"] is False` when index is v1 vs expected v2.
- **Blind path (before):** same metrics, but `check_gate_blind(metrics)` only checks nothing / always returns pass — i.e. `caught_before = False` by definition for injected failures.  
  Report `before_catch_rate = 0.0` and `after_catch_rate = 1.0` when the full gate fails on that scenario (boolean → rate over the single scenario, or mean over N seeds if looped). For README, three scenarios ⇒ three rows with 0% → 100% when detectors work.
- **Scenarios:**
  1. `stale-context`: ingest `mutable/v1` (+ fastapi); expected fingerprint still v2; run eval → `drift_ok=False` and/or recall drop → gate fails.
  2. `ambiguous-ranking`: after retrieve, reverse hit order before metrics → MRR/precision drop on ambiguous cohort → gate fails.
  3. `unsupported-answer`: `generate_answer(..., force_answer=True)` never refuses → `refusal_accuracy` drop → gate fails.

- [ ] **Step 1: Tests**

```python
def test_stale_context_sim_caught(tmp_path):
    metrics = run_stale_scenario(tmp_path)
    assert metrics["drift_ok"] is False
    ok, _ = check_gate(metrics, load_thresholds(), load_baseline())
    assert ok is False

def test_ambiguous_ranking_sim_caught(tmp_path):
    metrics = run_ambiguous_scenario(tmp_path)
    ok, _ = check_gate(metrics, load_thresholds(), load_baseline())
    assert ok is False

def test_unsupported_always_answer_caught(tmp_path):
    metrics = run_unsupported_scenario(tmp_path)
    assert metrics["refusal_accuracy"] < 0.9
    ok, _ = check_gate(metrics, load_thresholds(), load_baseline())
    assert ok is False

def test_simulate_report_shape():
    report = simulate_all()
    assert report["stale-context"]["before_catch_rate"] == 0.0
    assert report["stale-context"]["after_catch_rate"] == 1.0
```

- [ ] **Step 2: Implement `simulate_regressions.py` writing `eval/sim_report.json`**

- [ ] **Step 3: Tests pass**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: simulate three failure-mode regressions for README"
```

---

### Task 9: Observability stub + optional pgvector

**Files:**
- Create: `observability/tracing.py`, `rag_harness/store/pgvector.py`, `docker-compose.yml`, `.env.example`
- Test: `tests/test_tracing.py`

- [ ] **Step 1: No-op tracer records spans in list; Langfuse adapter no-ops without keys**

- [ ] **Step 2: pgvector module documents required env; `NotConfiguredError` if used without DSN**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: add Langfuse stub and optional pgvector adapter"
```

---

### Task 10: CI workflow + Makefile polish

**Files:**
- Create: `.github/workflows/eval.yml`
- Modify: `Makefile`

- [ ] **Step 1: Workflow**

```yaml
name: eval-gate
on:
  push:
  pull_request:
jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -e ".[dev]"
      - run: pytest -q
      - run: python -m ingest --mutable-version v2
      - run: python -m eval
      - run: python -m gates
```

- [ ] **Step 2: Makefile targets** `test`, `ingest`, `eval`, `gate`, `simulate`, `all`

- [ ] **Step 3: Run full local path green**

- [ ] **Step 4: Commit**

```bash
git commit -m "ci: add offline eval-gate GitHub Actions workflow"
```

---

### Task 11: README + LinkedIn draft

**Files:**
- Create: `README.md`, `LINKEDIN_DRAFT.md`

- [ ] **Step 1: README in locked order (spec §7 — do not reorder)**

1. Title + one-liner (badge may appear here as markdown image, but narrative order below is mandatory)
2. **Flow diagram** — ingest → retrieve → generate → eval gate
3. **Before/after table** from `simulate_regressions` numbers
4. **“3 failure modes this harness catches”** with example + test each
5. **CI badge** + short note that Actions runs the eval suite on every push (badge URL placeholder: `https://github.com/<user>/rag-reliability-harness/actions/workflows/eval.yml/badge.svg` until remote exists)
6. Quickstart (`make all`)
7. Attribution + optional pgvector/Langfuse

- [ ] **Step 2: LINKEDIN_DRAFT.md** — short post: why eval > another RAG demo; link repo

- [ ] **Step 3: Commit**

```bash
git commit -m "docs: README narrative and LinkedIn draft"
```

---

### Task 12: Final verification

- [ ] **Step 1: Fresh venv path**

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make all
```

Expected: tests pass, gate exit 0, simulate prints catch rates

- [ ] **Step 2: Confirm no secrets required**

- [ ] **Step 3: Fix any threshold/baseline drift; commit if needed**

```bash
git commit -m "fix: calibrate thresholds after full-suite run"
```

---

## Execution notes

- Prefer TDD order inside each task.
- Do not add Ragas LLM-judge or real Langfuse calls in CI.
- Optional `sentence-transformers` path from the spec is **dropped** for this weekend build (hash embedder only).
- If hash ranking is too weak for ambiguous cases, strengthen distractor wording in corpus (do not switch to API embeddings).
- After GitHub remote exists, update README badge URL to the real owner/repo.
