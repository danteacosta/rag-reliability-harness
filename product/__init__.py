"""Product-facing gate and report adapters for the RAG harness.

The product layer intentionally owns no RAG domain model.  It consumes the
neutral contracts from :mod:`agent_reliability_protocol` and keeps RAG
payloads namespaced behind a small adapter boundary.
"""

from product.gate import decide_product_gate
from product.report import ProductGateReport
from product.arp_adapter import ArpV2EventLog, build_arp_manifest, read_arp_events, read_arp_manifest

__all__ = ["ArpV2EventLog", "ProductGateReport", "build_arp_manifest", "decide_product_gate", "read_arp_events", "read_arp_manifest"]
