"""Run-level semantic lint integration without changing gate decisions."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from observability.semantic_lint import Finding, lint_session


def lint_run_events(run_id: str, events: Iterable[Mapping[str, Any]]) -> list[Finding]:
    """Lint a closed-loop event snapshot as a product session.

    The source reference is the run identity itself; individual event
    payloads are inspected for secret-like fields. Findings are observational
    and must not alter the RAG gate decision.
    """
    return lint_session(
        {
            "session_id_hash": run_id,
            "source_refs": [{"kind": "run", "identifier": run_id}],
            "events": [dict(event) for event in events],
        }
    )
