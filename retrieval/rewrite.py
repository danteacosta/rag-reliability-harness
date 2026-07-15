from __future__ import annotations

import re

SYNONYMS: dict[str, str] = {
    "deps": "dependencies",
    "auth": "authentication",
    "mw": "middleware",
    "cfg": "config",
    "db": "database",
    "req": "request",
    "resp": "response",
}


def rewrite(query: str) -> str:
    """Expand common abbreviations and aliases in the query."""
    result = query
    for alias, expansion in SYNONYMS.items():
        pattern = rf"\b{re.escape(alias)}\b"
        result = re.sub(pattern, expansion, result, flags=re.IGNORECASE)
    return result
