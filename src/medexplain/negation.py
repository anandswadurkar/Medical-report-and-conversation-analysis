"""Decide whether a mention is affirmed, negated or uncertain.

A lightweight version of NegEx (Chapman et al., 2001, *J Biomed Inform* 34:301-310,
doi:10.1006/jbin.2001.1029): a term is negated when a trigger phrase appears within a
few tokens before it (or just after it) in the same clause. Clauses end at sentence
punctuation and at words such as "but" and "however", so in "no fracture, but a small
effusion" the "no" does not reach "effusion".

Why this matters for patients: radiology reports list many things that were *looked
for and not found* ("No pneumothorax."). Highlighting "pneumothorax" as a concern
without its negation would frighten a reader for no reason.
"""

from __future__ import annotations

import re
from enum import StrEnum


class Assertion(StrEnum):
    AFFIRMED = "affirmed"
    NEGATED = "negated"
    UNCERTAIN = "uncertain"


# Window sizes follow NegEx's original 5-6 token scope, which Chapman et al. chose as
# the span over which negation phrases reliably applied in discharge summaries.
PRE_WINDOW_TOKENS = 6
POST_WINDOW_TOKENS = 5

PRE_NEGATION = (
    "no",
    "not",
    "without",
    "negative for",
    "no evidence of",
    "no signs of",
    "no sign of",
    "free of",
    "absence of",
    "absent",
    "denies",
    "denied",
    "ruled out",
    "rules out",
    "resolution of",
    "resolved",
    "never had",
    "none",
)
PRE_UNCERTAIN = (
    "possible",
    "possibly",
    "probable",
    "probably",
    "may",
    "might",
    "could",
    "suspicious for",
    "suspected",
    "concern for",
    "concerning for",
    "questionable",
    "question of",
    "suggestive of",
    "suggests",
    "likely",
    "cannot exclude",
    "rule out",
    "r/o",
    "versus",
    "vs",
    "differential includes",
    "worried about",
    # Requests in an INDICATION line ("evaluate for pneumonia") name what was being
    # looked for, not what was found.
    "evaluate for",
    "evaluation for",
    "assess for",
    "to exclude",
)
POST_NEGATION = (
    "not seen",
    "not identified",
    "not present",
    "not detected",
    "not visualized",
    "is absent",
    "are absent",
    "was absent",
    "has resolved",
    "have resolved",
    "was ruled out",
    "is ruled out",
    "was excluded",
)
POST_UNCERTAIN = (
    "cannot be excluded",
    "cannot be ruled out",
    "can not be excluded",
    "not excluded",
    "not ruled out",
    "is suspected",
    "is possible",
    "is likely",
    "is not excluded",
    "versus",
    "vs",
)
CLAUSE_TERMINATORS = (
    "but",
    "however",
    "although",
    "though",
    "except",
    "aside from",
    "apart from",
    "which",
    "whereas",
    "yet",
)

_TOKEN = re.compile(r"[A-Za-z0-9/'\-]+")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?;])\s+|\n\s*\n|\n(?=\s*[-*•\d]+[.)]?\s)|\n(?=\s*[A-Z][A-Z /&()-]{2,40}:)")


def sentence_bounds(text: str, position: int) -> tuple[int, int]:
    """Return ``(start, end)`` of the sentence containing character ``position``.

    >>> text = "No pneumothorax. Small effusion."
    >>> sentence_bounds(text, 20)
    (17, 32)
    """
    if not 0 <= position <= len(text):
        raise ValueError(f"position {position} outside text of length {len(text)}")
    start, end = 0, len(text)
    for match in _SENTENCE_BREAK.finditer(text):
        if match.end() <= position:
            start = match.end()
        elif match.start() >= position:
            end = match.start()
            break
    return start, end


def _tokens(fragment: str) -> list[str]:
    return [token.lower() for token in _TOKEN.findall(fragment)]


def _last_trigger_distance(tokens: list[str], triggers: tuple[str, ...]) -> int | None:
    """Distance (in tokens) from the end of ``tokens`` to the nearest trigger, or None."""
    best: int | None = None
    for trigger in triggers:
        trigger_tokens = trigger.split()
        width = len(trigger_tokens)
        for index in range(len(tokens) - width, -1, -1):
            if tokens[index : index + width] == trigger_tokens:
                distance = len(tokens) - (index + width)
                if best is None or distance < best:
                    best = distance
                break
    return best


def _first_trigger_distance(tokens: list[str], triggers: tuple[str, ...]) -> int | None:
    best: int | None = None
    for trigger in triggers:
        trigger_tokens = trigger.split()
        width = len(trigger_tokens)
        for index in range(0, len(tokens) - width + 1):
            if tokens[index : index + width] == trigger_tokens:
                if best is None or index < best:
                    best = index
                break
    return best


def _clip_at_terminator(tokens: list[str], keep_tail: bool) -> list[str]:
    """Cut a token list at the last (pre-window) or first (post-window) clause terminator."""
    positions = [i for i, token in enumerate(tokens) if token in CLAUSE_TERMINATORS]
    if not positions:
        return tokens
    if keep_tail:
        return tokens[positions[-1] + 1 :]
    return tokens[: positions[0]]


def classify_mention(text: str, start: int, end: int) -> Assertion:
    """Classify the mention ``text[start:end]`` as affirmed, negated or uncertain.

    When a negation and an uncertainty trigger both apply, the one nearer the term
    wins, so "no suspicious mass" is negated and "not excluded" after a term is
    uncertain.

    >>> classify_mention("No pneumothorax.", 3, 15).value
    'negated'
    >>> s = "Malignancy cannot be excluded."
    >>> classify_mention(s, 0, 10).value
    'uncertain'
    >>> s = "No fracture, but there is a small effusion."
    >>> classify_mention(s, s.index("effusion"), s.index("effusion") + 8).value
    'affirmed'
    """
    if not 0 <= start < end <= len(text):
        raise ValueError(f"invalid span ({start}, {end}) for text of length {len(text)}")
    sentence_start, sentence_end = sentence_bounds(text, start)
    before = _clip_at_terminator(_tokens(text[sentence_start:start]), keep_tail=True)[-PRE_WINDOW_TOKENS:]
    after_all = _clip_at_terminator(_tokens(text[end:sentence_end]), keep_tail=False)
    after = after_all[:POST_WINDOW_TOKENS]

    # Post-term phrases are checked first because "cannot be excluded" contains the
    # token sequence of a weaker pre-trigger and is more specific.
    post_uncertain = _first_trigger_distance(after, POST_UNCERTAIN)
    post_negated = _first_trigger_distance(after, POST_NEGATION)
    if post_uncertain is not None and (post_negated is None or post_uncertain <= post_negated):
        return Assertion.UNCERTAIN
    if post_negated is not None:
        return Assertion.NEGATED

    pre_negated = _last_trigger_distance(before, PRE_NEGATION)
    pre_uncertain = _last_trigger_distance(before, PRE_UNCERTAIN)
    if pre_negated is None and pre_uncertain is None:
        return Assertion.AFFIRMED
    if pre_uncertain is None:
        return Assertion.NEGATED
    if pre_negated is None:
        return Assertion.UNCERTAIN
    return Assertion.NEGATED if pre_negated <= pre_uncertain else Assertion.UNCERTAIN
