# Product reliability gate

The product surface is a CI adapter over the neutral ARP 2.0.5 manifest and
lifecycle contracts. It does not consume thesis labels or alter scientific
estimands.

## Contract

| Decision | Process code | SARIF level |
| --- | ---: | --- |
| approve | 0 | note |
| warn | 10 | warning |
| block | 20 | error |
| invalid ARP envelope | 30 | error |

Hard failures take precedence over soft warnings. Reason and evidence IDs are
stable so CI annotations can be reconciled across reruns. RAG metrics remain
under the `metrics`/`rag` namespaces and are operational diagnostics.

## Smoke demo

```bash
python -m product --demo-output runs/product-demo
```

The command produces `approve.json`, `warn.json`, and `block.json`, their SARIF
counterparts, and `summary.json`. The data is synthetic and only verifies the
adapter contract; it must never be included in thesis analysis.

## Live reports

```bash
python -m product \
  --manifest runs/<run_id>/manifest.json \
  --events runs/<run_id>/events.jsonl \
  --metrics runs/<run_id>/metrics.json \
  --format sarif \
  --output runs/<run_id>/report.sarif
```

Invalid manifests, malformed event streams, run-ID mismatches, and lifecycle
ordering failures return code 30.

## Candidate memory and semantic QA

Product memory is an append-only candidate stream, not a replacement for the RAG corpus store. Every candidate carries source references and confidence. It remains `candidate` until a reviewer explicitly accepts or rejects it; acceptance requires a reviewer identity. The post-run semantic linter reports missing provenance and secret-like fields as structured findings. These product artifacts are not exported into the thesis label plane.

Retrieval is selective and typed: `CandidateMemoryStore.retrieve()` considers only the latest `accepted` record for a candidate, optionally scopes by user and category, and uses bounded lexical matching. Raw transcripts are not embedded or added to the corpus vector store. The closed loop records semantic-lint findings in its status and lifecycle event stream without changing the gate decision.

Session handoff is an explicit ingress, not an implicit model write:

```bash
python -m product --ingest-handoff session.json \
  --user-id <hashed-user-id> --candidate-store data/candidates.jsonl
```

Candidates carry session provenance, a bounded retention window, payload limits,
append locking, and an audit record. Deletion appends a tombstone and never
silently removes the history needed to explain a previous retrieval. The
semantic-lint worker is versioned and fails closed when its ruleset is unknown
or stale.
