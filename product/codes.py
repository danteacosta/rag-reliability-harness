"""Stable process exit codes for the product surface.

ARP deliberately keeps its neutral ``exit_code`` pass/fail compatibility
property. The product CLI has a richer operational vocabulary and maps it
without mutating the shared decision object.
"""

from __future__ import annotations

from typing import Any

PRODUCT_EXIT_APPROVE = 0
PRODUCT_EXIT_WARN = 10
PRODUCT_EXIT_BLOCK = 20
PRODUCT_EXIT_CONTRACT = 30


def product_exit_code(decision: Any) -> int:
    value = getattr(decision, "decision", None)
    if value == "approve":
        return PRODUCT_EXIT_APPROVE
    if value in {"warn", "request_clarification"}:
        return PRODUCT_EXIT_WARN
    if value == "block":
        return PRODUCT_EXIT_BLOCK
    raise ValueError(f"unsupported product decision: {value!r}")
