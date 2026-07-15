# RAG Reliability Harness — Design Spec

**Date:** 2026-07-15  
**Status:** Approved (user)  
**Goal:** Weekend portfolio repo that proves RAG *evaluation process* skill — README in ~40s, real CI gate, small golden set, three named failure modes.

---

## 1. Problem & success criteria

Hiring managers skim README, not architecture depth. Success means:

1. Clone → `make eval` (or equivalent) passes without API keys.
2. GitHub Actions badge stays green on every push (offline-first).
3. README shows: flow diagram → before/after table → 3 failure modes → CI badge.
4. Three CV terms are demonstrated with concrete examples + regression tests:
   - `stale-context`
   - `ambiguous-ranking`
   - `unsupported-answer`
5. Scope stays weekend-sized: small and polished, not large and fragile.

---

## 2. Decisions locked

| Decision | Choice | Rationale |
|----------|--------|-----------|
| CI mode | Offline-first | Green badge without secrets; clone works for reviewers |
| Corpus | Mix: FastAPI-style public docs + mutable in-repo docs | Real content + controllable drift demos |
| Architecture | Portfolio slim (Option 1) | Default in-process store; pgvector optional locally |
| Generate path (CI) | Extractive / template, no LLM | Deterministic groundedness checks |
| LLM-as-judge / Langfuse | Optional adapters only | Not required for CI |

---

## 3. Architecture

```text
ingest → retrieve → generate → eval gate
   │         │          │           │
 chunk +   rewrite   extractive   metrics vs
 embed     + cache   answer       golden set
                                  fail on regress
```

### Modules

| Path | Responsibility |
|------|----------------|
| `ingest/` | Load markdown corpus, chunk, embed, upsert into vector store; write corpus fingerprint |
| `retrieval/` | LangChain-compatible retriever, lightweight query rewrite, in-memory semantic cache |
| `eval/` | Metrics: precision@k, recall@k, MRR, groundedness, drift; regression simulation script |
| `gates/` | CLI compares run metrics to `thresholds.yaml` + baseline; non-zero exit on regression |
| `observability/` | No-op tracer default; optional Langfuse adapter behind env flag |
| `data/corpus/fastapi/` | Small public-style technical docs (attributed) |
| `data/corpus/mutable/` | Versioned docs (`v1` / `v2`) for stale-context |
| `data/golden/` | ~40 Q/A items in JSONL |
| `.github/workflows/eval.yml` | Install → ingest fixtures → eval → gate |

### Vector store strategy

- **Default (CI + local quick path):** in-process Chroma (or FAISS) via a `VectorStore` protocol.
- **Optional:** pgvector adapter + `docker-compose.yml` for local demo; **not** used in CI.
- **CI embeddings (locked):** character n-gram hashed bag-of-features (e.g. hashing trick over 3–5 grams into a fixed dim). Similarity is cosine over those vectors so **lexical overlap drives ranking** — enough for meaningful precision@k / MRR and the ambiguous-ranking demo without downloading models. Optional `sentence-transformers` path exists for local demos only; CI never uses it.
- **Default `k`:** 5 for all retrieval metrics and the generate top-k context window.

### Query rewrite & cache

- **Rewrite:** deterministic synonym / alias map for FastAPI terms (e.g. `deps` → `dependencies`); no LLM.
- **Semantic cache:** optional in-memory exact/near-exact query→chunk-ids cache. Not load-bearing for the three failure modes; may be a no-op stub if timeboxed.

### Generation (offline)

- Build answer by selecting / concatenating top retrieved chunk spans that match the question (extractive).
- **Refusal string (locked):** `INSUFFICIENT_CONTEXT` when max retrieval score < threshold or when no chunk passes the relevance cutoff.
- For `unsupported-answer` items: gold expects that refusal (or equivalent abstention), not a fabricated answer.

### Mutable corpus versioning (happy path)

- Default ingest / CI indexes **mutable `v2`** (current truth).
- Stale-context simulation forces an index built from **mutable `v1`** while golden still targets `v2`.

---

## 4. Data model

### Chunk

```json
{
  "id": "fastapi.routing.01",
  "doc_id": "fastapi/routing",
  "text": "...",
  "metadata": { "source": "fastapi/routing.md", "version": "1.0" }
}
```

### Golden item (`data/golden/set.jsonl`)

```json
{
  "id": "q001",
  "question": "...",
  "answer": "...",
  "relevant_chunk_ids": ["fastapi.routing.01"],
  "failure_mode": "none"
}
```

`failure_mode` ∈ `none` | `stale-context` | `ambiguous-ranking` | `unsupported-answer`.

### Corpus fingerprint

Hash of sorted `(doc_id, content_hash)` pairs written at ingest time. Drift metric fails when the active index fingerprint does not match the expected corpus version for the eval run (e.g. mutable `v1` vs `v2`).

---

## 5. Failure modes & tests

### stale-context

- **Example:** mutable doc changes default timeout `30s` → `60s`.
- **Golden:** expects `60s` (or chunk IDs from `v2`).
- **Capture:** drift fingerprint mismatch and/or recall@k against `v2` gold when index still on `v1`.
- **Regression sim:** force index on `v1` while gold targets `v2`; gate must fail; catch rate reported in README.

### ambiguous-ranking

- **Example:** two chunks share overlapping terms; only one answers the question.
- **Golden:** exact `relevant_chunk_ids` for the correct chunk.
- **Capture:** precision@k / MRR drop when ranking prefers the distractor.
- **Regression sim:** swap ranking scores / disable rewrite; gate fails.

### unsupported-answer

- **Example:** question outside corpus (e.g. unrelated product pricing).
- **Golden:** empty `relevant_chunk_ids`, expected abstention.
- **Capture:** groundedness / refusal accuracy — fabricated extractive answer fails.
- **Regression sim:** force always-answer mode; gate fails.

---

## 6. Metrics & gating

| Metric | Definition (offline) |
|--------|----------------------|
| precision@k | \|retrieved ∩ relevant\| / k (per query, then mean) |
| recall@k | \|retrieved ∩ relevant\| / \|relevant\| |
| MRR | mean reciprocal rank of first relevant chunk |
| groundedness | answer tokens/claims supported by retrieved context (lexical containment + refusal handling) |
| refusal_accuracy | for items with empty `relevant_chunk_ids` (or `failure_mode=unsupported-answer`): 1 iff answer is `INSUFFICIENT_CONTEXT` |
| drift | corpus fingerprint match boolean (aggregated as pass rate / catch in sim) |

### Metric cohort rules (locked)

- **Retrieval metrics (precision@k, recall@k, MRR):** computed **only** on golden items where `relevant_chunk_ids` is non-empty. Items with empty relevant IDs are **excluded** from those means (avoids divide-by-zero and false precision drag).
- **Groundedness:** computed on all answered (non-refusal) items; refusals count as grounded.
- **refusal_accuracy:** computed only on the unsupported / empty-relevant cohort.
- **drift:** corpus-level, not per-query; evaluated in the stale-context simulation and as a gate check that the active index fingerprint matches the expected fingerprint for the run profile (`happy` → v2, `stale_sim` → intentionally mismatched).

**Gate inputs:**

- `eval/thresholds.yaml` — absolute floors (e.g. recall@5 ≥ 0.75, refusal_accuracy ≥ 0.90).
- `eval/baselines/ci.json` — committed baseline from a known-good run.
- Fail if any metric below threshold **or** delta vs baseline worse than allowed slip (e.g. −0.05).

**Before/after README numbers:** produced by `eval/simulate_regressions.py` injecting the three failure modes; synthetic but reproducible from the public fixture corpus (no company data).

---

## 7. README requirements (order fixed)

1. Simple flow diagram: ingest → retrieve → generate → eval gate.
2. Before/after table (synthetic, reproducible).
3. Section “3 failure modes this harness catches” with concrete example + regression test each.
4. Real CI badge (GitHub Actions eval suite on push).

Plus: quickstart, attribution for FastAPI-style docs, optional pgvector/Langfuse notes.

Bonus: `LINKEDIN_DRAFT.md` — “why eval matters more than RAG” linking this repo.

---

## 8. Tech stack

- Python 3.11+
- `pyproject.toml` packaging
- LangChain (thin retriever integration)
- Chroma (default) + optional pgvector
- pytest for unit/integration tests
- GitHub Actions for CI gate
- Make (or `uv run`) for DX: `make ingest`, `make eval`, `make gate`

---

## 9. Out of scope

- HTTP API / UI / auth
- LLM generate required in CI
- Mandatory Ragas LLM-as-judge (optional hook only)
- Large datasets, continuous scraping
- Multi-tenant / production deploy

---

## 10. Delivery checklist

- [ ] Package layout + offline ingest/retrieve/generate
- [ ] Golden set ~40 items covering the three failure modes
- [ ] Eval suite + thresholds + baseline
- [ ] CI workflow green without secrets
- [ ] Optional pgvector compose + Langfuse stub
- [ ] README (40s narrative) + LinkedIn draft
- [ ] `simulate_regressions.py` for before/after table numbers
