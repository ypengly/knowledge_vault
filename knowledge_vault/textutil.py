"""Tokenising, light stemming, query-term coverage, and highlighting."""
from __future__ import annotations

import html
import re

STOP = set("""a an and are as at be but by can could did do does for from had has have how i if in into is it its
me my of on or our so than that the their them then there these they this to us was we were what when where which
who whom why will with would you your about say said tell find show give""".split())
_WORD = re.compile(r"\w+", re.UNICODE)


def stem(w: str) -> str:
    w = w.lower()
    for suf in ("ingly", "edly", "ing", "ed", "ly", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def tokens(text: str, keep_stop: bool = False) -> list[str]:
    out = [t.lower() for t in _WORD.findall(text)]
    return out if keep_stop else [t for t in out if t not in STOP and len(t) > 1]


def stems(text: str) -> list[str]:
    return [stem(t) for t in tokens(text)]


def coverage(query: str, text: str) -> float:
    """Fraction of distinct query content-stems that appear in text (0..1)."""
    q = set(stems(query))
    if not q:
        return 0.0
    return len(q & set(stems(text))) / len(q)


def highlight_html(text: str, query: str, limit: int | None = None) -> str:
    """HTML-escape text and wrap words that match query stems in <mark>."""
    if limit and len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + " …"
    q = set(stems(query))
    esc = html.escape(text)

    def repl(m: re.Match) -> str:
        w = m.group(0)
        return f"<mark>{w}</mark>" if stem(w) in q and w.lower() not in STOP else w

    return _WORD.sub(repl, esc).replace("\n", "<br>")


def best_snippet(text: str, query: str, width: int = 420) -> str:
    """Window of text around the densest cluster of query terms."""
    if len(text) <= width:
        return text
    q = set(stems(query))
    best, best_pos = -1, 0
    for m in _WORD.finditer(text):
        if stem(m.group(0)) in q:
            win = text[m.start(): m.start() + width]
            score = sum(1 for w in _WORD.findall(win) if stem(w) in q)
            if score > best:
                best, best_pos = score, m.start()
    start = max(0, best_pos - 60)
    snippet = text[start: start + width]
    return ("… " if start else "") + snippet.strip() + (" …" if start + width < len(text) else "")
