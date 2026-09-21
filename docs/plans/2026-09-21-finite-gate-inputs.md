# Finite numeric evidence at the RAG gate

## Observed defect and contract

The gate converts inputs with `float` and compares them directly. IEEE NaN is
neither less than a floor nor greater than a slip limit, so it can produce an
approval without a valid measurement. Positive infinity can also satisfy a
floor. Numeric strings and booleans are silently coerced; malformed strings
raise an exception instead of returning an auditable gate decision.

Given a configured floor or maximum slip, when a required current metric,
baseline metric, or threshold is not a finite JSON number, the gate must block
with a stable reason identifying its source and metric. Its decision must be
serializable as strict JSON. Existing finite inputs, missing-value reason codes,
drift behavior, and the deliberately blind simulation control remain unchanged.
The CLI must print GATE FAIL and exit 1 for these invalid numerical inputs.

## Design and verification

Validate each numerical operand at the existing gate boundary before arithmetic.
Use a small helper for finite-number conversion and a reason constructor; no new
provider, policy abstraction, dependencies, or statistical estimator is needed.
Reject booleans and numeric strings rather than silently inventing measurements.
Keep invalid values out of numerical evidence fields; reasons identify the bad
source. A negative maximum slip is also invalid configuration. Floors may be
any finite number so the generic gate can evaluate non-ratio metrics.

Tests exercise the public decision, compatibility wrapper and file-based CLI,
including NaN, infinity, malformed values, huge integers, missing values and
valid boundary values. First reproduce failures, then implement, run the full
suite, and run offline ingest/evaluation/gate/loop and synthetic regressions.

This is a prospective integrity fix to the independent sister artifact. It does
not modify historical metrics or establish evidence for thesis H1/H2. Metrics
not selected by a configured rule are outside this validation contract.

## Verification observed

- Before implementation: 38 new failing cases, including a CLI `GATE PASS` on
  NaN. A separate overflow regression failed strict JSON serialization.
- After implementation: 79 gate cases passed; full suite 186 passed, 1 skipped
  (optional live pgvector test without a local DSN).
- `PYTHON=/private/tmp/rag-quality-venv/bin/python make all simulate`: offline
  ingest, evaluation, healthy gate, closed loop, and all three injected-regression
  scenarios passed. `compileall` and `git diff --check` passed.
- No configured linter or type-checker exists. Reviewed responsibilities,
  dependency boundaries, error handling and public-behavior tests; no provider
  calls, secrets, historical result rewrites or new architecture were introduced.

Review also identified malformed rule sections silently disabling comparisons,
and nonfinite drift evidence leaking into decisions. Regression tests reproduced
21 boundary failures and four non-string rule-name crashes before extending the
fix. Rules now require mappings with nonempty string names, and drift policy
requires a boolean. Explicit empty mappings and omitted rules remain valid.
Invalid drift values block without copying them into numeric evidence.
