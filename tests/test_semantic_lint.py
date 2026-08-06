import pytest

from observability.semantic_lint import lint_session, validate_session


def test_lint_session_reports_missing_source_and_secret_like_fields():
    findings = lint_session({"session_id_hash": "s1", "events": [{"message": "x", "api_key": "secret"}]})
    codes = {item.code for item in findings}
    assert "missing_source_refs" in codes
    assert "secret_like_field" in codes


def test_validate_session_strict_raises():
    try:
        validate_session({"session_id_hash": "s1", "events": []}, strict=True)
    except ValueError as exc:
        assert "missing_source_refs" in str(exc)
    else:
        raise AssertionError("strict validation must reject unprovenanced sessions")


def test_semantic_lint_is_versioned_and_fail_closed_for_stale_or_unknown_workers():
    findings = lint_session(
        {"session_id_hash": "s1", "source_refs": [{"kind": "session", "identifier": "s1"}]},
        worker_status="stale",
    )
    assert findings[0].code == "semantic_lint_unavailable"
    assert findings[0].rule_version == "v1"
    with pytest.raises(ValueError, match="semantic_lint_unavailable"):
        validate_session(
            {"session_id_hash": "s1", "source_refs": [{"kind": "session", "identifier": "s1"}]},
            worker_status="unknown",
            strict=True,
        )


def test_semantic_lint_rule_order_is_deterministic():
    findings = lint_session(
        {"session_id_hash": "s1", "events": [{"api_token": "redacted"}]},
    )
    assert [finding.code for finding in findings] == ["missing_source_refs", "secret_like_field"]
