"""Hide common personal identifiers before text leaves the computer.

This is a convenience, not a guarantee. It removes patterns that are easy to
recognise (emails, phone numbers, dates, record numbers, labelled name and address
lines, and any words the reader lists) and leaves everything else, including names
that appear in running text without a label. The notebook shows the redacted text
before anything is sent so the reader can check it.

Patterns follow the HIPAA Safe Harbor identifier list (45 CFR 164.514(b)(2)) where a
regular expression can reasonably catch them.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

_LABELLED_LINE = re.compile(
    r"(?im)^(?P<label>[ \t]*(?:patient(?:'s)? name|patient name|name|full name|address|home address|street|"
    r"guardian|emergency contact|insurance(?: id| number)?|member id|policy(?: number)?|ssn|social security(?: number)?|"
    r"referring physician|ordering physician|attending|signed by|electronically signed by|dictated by)[ \t]*[:#][ \t]*)(?P<value>\S.*)$"
)
_RECORD_NUMBER = re.compile(
    r"(?i)\b(?P<label>mrn|medical record(?: number| no\.?| #)?|acc(?:ession)?(?: number| no\.?| #)?|account(?: number| no\.?| #)?|"
    r"encounter(?: id| #)?|visit(?: id| #)?|case(?: number| no\.?| #)|patient id|id)\s*[:#]?\s*(?P<value>[A-Z0-9][A-Z0-9\-]{3,})\b"
)
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("url", re.compile(r"\bhttps?://\S+")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("phone", re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)")),
    ("date", re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")),
    ("date", re.compile(r"\b\d{4}-\d{2}-\d{2}\b")),
    (
        "date",
        re.compile(
            r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b",
            re.IGNORECASE,
        ),
    ),
    ("zip code", re.compile(r"\b\d{5}(?:-\d{4})\b")),
)


@dataclass(frozen=True)
class Redaction:
    text: str
    counts: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def redact(text: str, extra_terms: list[str] | tuple[str, ...] = ()) -> Redaction:
    """Replace identifiers in ``text`` with bracketed placeholders.

    ``extra_terms`` are words to hide wherever they appear (case-insensitive), for
    example the reader's own name or their doctor's name.

    >>> r = redact("Name: Jane Roe\\nMRN: 00123456\\nSeen 03/14/2026. Call 315-555-0100.")
    >>> print(r.text)
    Name: [NAME]
    MRN: [ID]
    Seen [DATE]. Call [PHONE].
    """
    counts: Counter[str] = Counter()

    def _labelled(match: re.Match[str]) -> str:
        counts["labelled detail"] += 1
        label = match.group("label")
        placeholder = (
            "[NAME]"
            if "name" in label.lower()
            or "by" in label.lower()
            or "physician" in label.lower()
            or "attending" in label.lower()
            else "[REDACTED]"
        )
        return f"{label}{placeholder}"

    result = _LABELLED_LINE.sub(_labelled, text)

    def _record(match: re.Match[str]) -> str:
        # Require a digit, so "ID: unknown" or a word after "case" is left alone.
        if not re.search(r"\d", match.group("value")):
            return match.group(0)
        counts["record number"] += 1
        return match.group(0)[: match.start("value") - match.start()] + "[ID]"

    result = _RECORD_NUMBER.sub(_record, result)

    for name, pattern in _PATTERNS:
        placeholder = f"[{name.upper()}]"

        def _replace(match: re.Match[str], name: str = name, placeholder: str = placeholder) -> str:
            counts[name] += 1
            return placeholder

        result = pattern.sub(_replace, result)

    for term in extra_terms:
        cleaned = term.strip()
        if len(cleaned) < 2:
            continue
        pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(cleaned) + r"(?![A-Za-z0-9])", re.IGNORECASE)
        result, replaced = pattern.subn("[HIDDEN]", result)
        if replaced:
            counts["your listed words"] += replaced

    return Redaction(result, dict(counts))
