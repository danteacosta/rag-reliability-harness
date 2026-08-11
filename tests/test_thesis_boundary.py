from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_product_layer_does_not_import_asd_or_emit_thesis_labels() -> None:
    forbidden_imports = ("agent_smell_degradation_harness", "feature_plane", "label_plane", "replay.runner")
    forbidden_labels = ("oracle_passed", "semantic_label", '"variant"', '"mutation"')
    for directory in (ROOT / "product", ROOT / "product_memory"):
        for path in directory.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert not any(token in source for token in forbidden_imports), path
            assert not any(token in source for token in forbidden_labels), path


def test_product_docs_state_thesis_isolation() -> None:
    docs = (ROOT / "docs" / "product" / "README.md").read_text(encoding="utf-8")
    assert "not exported into the thesis label plane" in docs
    assert "synthetic" in docs
