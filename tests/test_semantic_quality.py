from observability.session_quality import lint_run_events


def test_lint_run_events_returns_structured_findings_for_secret_like_payloads():
    findings = lint_run_events(
        "run-1",
        [{"source_refs": [{"kind": "run", "identifier": "run-1"}], "api_token": "redacted"}],
    )
    assert [item.code for item in findings] == ["secret_like_field"]
