"""Product-facing gate and report adapters for the RAG harness.

The product layer intentionally owns no RAG domain model.  It consumes the
neutral contracts from :mod:`agent_reliability_protocol` and keeps RAG
payloads namespaced behind a small adapter boundary.
"""

from product.gate import decide_product_gate
from product.report import ProductGateReport

__all__ = ["ProductGateReport", "decide_product_gate"]
