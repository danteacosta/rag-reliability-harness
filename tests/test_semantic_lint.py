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
