# Retrieval metric contract v2

Observed: five of twenty relevant IDs yields recall@5=1 under the legacy capped denominator; repeated IDs yield recall/nDCG above1. This is a measurement migration, not a retrieval improvement.

Acceptance / BDD:
- Given five unique relevant hits of twenty, recall@5 is0.25.
- Given duplicate retrieved IDs, only the first occurrence earns credit; duplicates consume their original rank positions. Relevant IDs represent a set. Recall, precision and binary nDCG stay within[0,1].
- Given a new evaluation, its metric contract is serialized and retained when extracting a baseline.
- Given baseline comparisons across different contracts, the gate blocks with an explicit reason. Two unversioned legacy artifacts remain compatible.
- Historical baseline bytes remain unchanged; a separate v2 CI baseline is qualified by a deterministic fresh evaluation, not by relabeling scientific results.

Design: localized pure metric functions, runner metadata, baseline extraction and gate compatibility check. No design pattern needed. Duplicate rank slots are not removed (which could improve later ranks). MRR already uses the first original rank. Empty relevance and nonpositive k remain0. Product-memory metrics are out of scope. Existing policy thresholds remain operational thresholds, not validated scientific cutoffs.

Verification: focused metric invariants and gate mismatch tests first; full suite, deterministic ingest/eval/gate/loop, static compilation, independent SOLID/clean-code review and exact-head CI before merge. No model/provider calls.
