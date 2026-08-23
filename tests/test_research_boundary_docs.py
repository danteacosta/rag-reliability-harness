from pathlib import Path


def test_readme_keeps_rag_out_of_confirmatory_thesis_rows():
    text = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")
    assert "independent sister artifact" in text
    assert "MUST NOT be pooled" in text
    assert "B0–B3" in text
