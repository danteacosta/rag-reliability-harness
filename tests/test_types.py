from rag_harness.types import GoldenItem


def test_golden_item_from_dict():
    item = GoldenItem.from_dict({
        "id": "q001",
        "question": "What is the default timeout?",
        "answer": "60s",
        "relevant_chunk_ids": ["mutable.config.01"],
        "failure_mode": "stale-context",
    })
    assert item.id == "q001"
    assert item.failure_mode == "stale-context"
    assert item.relevant_chunk_ids == ["mutable.config.01"]
