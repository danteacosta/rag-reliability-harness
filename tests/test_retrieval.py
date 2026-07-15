from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from retrieval.retriever import build_test_retriever
from retrieval.rewrite import rewrite


def test_rewrite_expands_deps_alias():
    assert "dependencies" in rewrite("how do deps work?")


def test_harness_retriever_returns_langchain_documents():
    r = build_test_retriever()
    assert isinstance(r, BaseRetriever)
    docs = r.invoke("timeout")
    assert isinstance(docs[0], Document)
