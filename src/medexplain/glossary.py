"""Find glossary terms in a document and classify each mention."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from .detect import DocType
from .negation import Assertion, classify_mention, sentence_bounds
from .terms import GLOSSARY, Term

# Letters/digits on either side mean the match is inside a longer word ("mass" in
# "massage"). Lookarounds are used instead of \b so that "b.i.d." and "f/u" match.
_LEFT = r"(?<![A-Za-z0-9])"
_RIGHT = r"(?![A-Za-z0-9])"


@dataclass(frozen=True)
class TermHit:
    term: Term
    start: int
    end: int
    matched_text: str
    assertion: Assertion

    @property
    def is_concern(self) -> bool:
        """True when a concern term is mentioned as present or possible."""
        return self.term.concern and self.assertion is not Assertion.NEGATED


def _alias_is_case_sensitive(term: Term, alias: str) -> bool:
    """Short spellings with capitals ("US", "Na", "PE") must match case exactly.

    Otherwise "US" (ultrasound) would match the word "us" in a conversation, and
    "K" (potassium) would match every stray "k".
    """
    has_capital = any(char.isupper() for char in alias)
    if term.case_sensitive:
        # The flag is for abbreviations ("SOB", "BI-RADS"); spelled-out aliases such as
        # "shortness of breath" must still match at the start of a sentence.
        return has_capital and " " not in alias
    return len(alias) <= 5 and has_capital


def _applies(term: Term, doc_type: DocType) -> bool:
    return not term.doc_types or doc_type.value in term.doc_types


@lru_cache(maxsize=8)
def _compiled(doc_type: DocType) -> tuple[tuple[re.Pattern[str], Term], ...]:
    """Return one compiled pattern per spelling, longest spellings first.

    Longest-first ordering plus the overlap check in ``find_terms`` makes
    "pleural effusion" win over "effusion" and "body mass index" over "mass".
    """
    spellings: list[tuple[str, Term]] = []
    for term in GLOSSARY:
        if not _applies(term, doc_type):
            continue
        for spelling in (term.term, *term.aliases):
            spellings.append((spelling, term))
    spellings.sort(key=lambda item: len(item[0]), reverse=True)
    compiled = []
    for spelling, term in spellings:
        flags = 0 if _alias_is_case_sensitive(term, spelling) else re.IGNORECASE
        # Allow any run of whitespace between words, so line-wrapped terms still match.
        body = r"\s+".join(re.escape(part) for part in spelling.split())
        compiled.append((re.compile(_LEFT + body + _RIGHT, flags), term))
    return tuple(compiled)


def find_terms(text: str, doc_type: DocType = DocType.UNKNOWN) -> list[TermHit]:
    """Return non-overlapping glossary mentions in ``text``, in reading order.

    >>> hits = find_terms("No pneumothorax. Small left pleural effusion.", DocType.RADIOLOGY)
    >>> [(h.term.term, h.assertion.value) for h in hits]
    [('pneumothorax', 'negated'), ('pleural effusion', 'affirmed')]
    """
    taken = [False] * len(text)
    hits: list[TermHit] = []
    for pattern, term in _compiled(doc_type):
        for match in pattern.finditer(text):
            start, end = match.span()
            if any(taken[start:end]):
                continue
            for index in range(start, end):
                taken[index] = True
            hits.append(TermHit(term, start, end, match.group(0), classify_mention(text, start, end)))
    hits.sort(key=lambda hit: hit.start)
    return hits


def unique_terms(hits: list[TermHit]) -> list[tuple[Term, list[TermHit]]]:
    """Group hits by term, keeping first-appearance order."""
    grouped: dict[str, tuple[Term, list[TermHit]]] = {}
    for hit in hits:
        key = f"{hit.term.term}|{hit.term.definition}"
        grouped.setdefault(key, (hit.term, []))[1].append(hit)
    return list(grouped.values())


def mention_context(text: str, hit: TermHit, max_chars: int = 220) -> tuple[str, str, str]:
    """Return ``(before, mention, after)`` for the sentence that contains ``hit``.

    Long sentences are trimmed to about ``max_chars`` around the mention, with an
    ellipsis, so the context stays readable.

    >>> text = "Lungs are clear. No pneumothorax is seen."
    >>> hit = find_terms(text, DocType.RADIOLOGY)[0]
    >>> mention_context(text, hit)
    ('No ', 'pneumothorax', ' is seen.')
    """
    start, end = sentence_bounds(text, hit.start)
    before, after = text[start : hit.start], text[hit.end : end]
    half = max(20, (max_chars - len(hit.matched_text)) // 2)
    if len(before) > half:
        before = "…" + before[-half:]
    if len(after) > half:
        after = after[:half] + "…"
    return before.lstrip(), text[hit.start : hit.end], after.rstrip()


def all_spellings(doc_type: DocType = DocType.UNKNOWN) -> list[str]:
    """Every glossary spelling that applies to ``doc_type``, sorted case-insensitively."""
    spellings = {spelling for term in GLOSSARY if _applies(term, doc_type) for spelling in (term.term, *term.aliases)}
    return sorted(spellings, key=str.lower)


def lookup(query: str, doc_type: DocType = DocType.UNKNOWN, limit: int = 5) -> list[Term]:
    """Find glossary entries for a word the reader types.

    Ranking: exact spelling, then spellings that start with the query, then spellings
    that contain it. Case is ignored. Returns an empty list for an empty query.

    >>> [t.term for t in lookup("effusion")]
    ['pleural effusion']
    >>> lookup("BID")[0].term
    'bid'
    """
    cleaned = " ".join(query.lower().split())
    if not cleaned:
        return []
    ranked: dict[int, list[Term]] = {0: [], 1: [], 2: []}
    seen: set[int] = set()
    for term in GLOSSARY:
        if not _applies(term, doc_type):
            continue
        spellings = [spelling.lower() for spelling in (term.term, *term.aliases)]
        if cleaned in spellings:
            rank = 0
        elif any(spelling.startswith(cleaned) for spelling in spellings):
            rank = 1
        elif len(cleaned) >= 3 and any(cleaned in spelling for spelling in spellings):
            rank = 2
        else:
            continue
        if id(term) not in seen:
            seen.add(id(term))
            ranked[rank].append(term)
    for rank_terms in ranked.values():
        # Within a rank: entries whose main name matches come before alias-only
        # matches ("Macrobid" for "bid"), then alphabetical, so ties are stable.
        rank_terms.sort(key=lambda term: (cleaned not in term.term.lower(), term.term.lower()))
    return (ranked[0] + ranked[1] + ranked[2])[:limit]
