"""Split page text into overlapping word windows that never cross page boundaries."""
from __future__ import annotations

import re

_TOK = re.compile(r"\S+")


def chunk_text(text: str, size: int = 180, overlap: int = 30) -> list[str]:
    if size <= 0:
        raise ValueError("size must be positive")
    overlap = max(0, min(overlap, size - 1))
    spans = [m.span() for m in _TOK.finditer(text)]
    if not spans:
        return []
    if len(spans) <= size:
        return [text[spans[0][0]: spans[-1][1]]]
    out, step, i = [], size - overlap, 0
    while i < len(spans):
        j = min(i + size, len(spans))
        out.append(text[spans[i][0]: spans[j - 1][1]])
        if j == len(spans):
            break
        i += step
    return out
