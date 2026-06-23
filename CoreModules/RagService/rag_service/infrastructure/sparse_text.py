"""
Stable sparse vectors for Qdrant hybrid search (keyword signal).

Uses deterministic hashing + log(tf) weights so index and query use the same
mapping without a Rust/native BM25 dependency (portable across Python versions).
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

# Qdrant sparse index range; keep below 2^24 for compatibility
_DIM = 1 << 22


def normalize_text_for_sparse(text: str) -> str:
    return " ".join((text or "").split())


def _stable_index(token: str) -> int:
    h = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") % _DIM


def text_to_sparse_vector(text: str) -> tuple[list[int], list[float]]:
    """
    Map text to (indices, values) for Qdrant sparse vector storage.
    Empty input yields empty lists.
    """
    t = normalize_text_for_sparse(text).lower()
    tokens = _TOKEN_RE.findall(t)
    if not tokens:
        return [], []
    tf: Counter[str] = Counter(tokens)
    acc: dict[int, float] = {}
    for tok, c in tf.items():
        idx = _stable_index(tok)
        w = 1.0 + math.log(c)
        acc[idx] = acc.get(idx, 0.0) + w
    indices = sorted(acc.keys())
    values = [acc[i] for i in indices]
    return indices, values
