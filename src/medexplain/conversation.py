"""Pull the things a patient needs to remember out of a visit transcript.

Rule-based and deliberately literal: every item it returns is a sentence that was
actually said, quoted with its speaker, so the reader can check it against the
transcript. It does not paraphrase or fill gaps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .sections import CLINICIAN, PATIENT, Turn

# A period followed by a digit is a decimal point ("2.5 mg"), not a sentence end.
_SENTENCE = re.compile(r"(?:[^.!?\n]|\.(?=\d))+(?:[.!?]+|$)", re.MULTILINE)

_INSTRUCTION = re.compile(
    r"\b(take|start(?:ing)?|stop(?:ping)?|continue|increase|decrease|cut back|avoid|"
    r"schedule|book|come back|follow[ -]?up|return|check (?:your|it)|keep (?:a|track)|"
    r"we(?:'ll| will| are going to|'re going to) (?:order|check|send|refer|do|get|start|repeat|draw|set up)|"
    r"i(?:'d| would| will|'ll|'m going to| am going to) (?:like to )?(?:order|prescribe|refer|recommend|send|start|increase|change|put you on)|"
    r"make sure|try to|you should|you need to|i want you to|i recommend|recommend(?:ed)?|"
    r"times a day|twice a day|once a day|every (?:day|morning|night|\d+ hours)|at bedtime|"
    r"\d+(?:\.\d+)?\s?(?:mg|mcg|units?|ml|tablets?|pills?|puffs?))\b",
    re.IGNORECASE,
)
_WARNING = re.compile(
    r"\b(if (?:you|it|the|your|there)\b.*\b(?:call|come in|go to|seek|let (?:us|me) know|get worse|worse)|"
    r"call (?:us|me|the office|911|your doctor)|go (?:straight )?to the (?:er|emergency|ed|hospital)|"
    r"emergency|right away|immediately|warning sign)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Quote:
    speaker: str
    role: str
    text: str


@dataclass(frozen=True)
class VisitSummary:
    instructions: list[Quote] = field(default_factory=list)
    warning_signs: list[Quote] = field(default_factory=list)
    patient_questions: list[Quote] = field(default_factory=list)
    turn_counts: dict[str, int] = field(default_factory=dict)


def sentences(text: str) -> list[str]:
    """Split a turn into sentences.

    >>> sentences("Take one daily. Call me if it gets worse!")
    ['Take one daily.', 'Call me if it gets worse!']
    """
    return [piece.strip() for piece in _SENTENCE.findall(text) if piece.strip()]


def summarize_visit(turns: list[Turn]) -> VisitSummary:
    """Collect clinician instructions, warning signs and the patient's own questions."""
    instructions: list[Quote] = []
    warnings: list[Quote] = []
    questions: list[Quote] = []
    counts: dict[str, int] = {}
    for turn in turns:
        counts[turn.role] = counts.get(turn.role, 0) + 1
        for sentence in sentences(turn.text):
            quote = Quote(turn.speaker, turn.role, sentence)
            if turn.role == CLINICIAN:
                # A warning sign is also an instruction; list it once, under warnings,
                # because that is the list a patient most needs to find quickly.
                if _WARNING.search(sentence):
                    warnings.append(quote)
                elif _INSTRUCTION.search(sentence) and not sentence.endswith("?"):
                    instructions.append(quote)
            elif turn.role == PATIENT and sentence.endswith("?"):
                questions.append(quote)
    return VisitSummary(instructions, warnings, questions, counts)


# ---------------------------------------------------------------------------
# "Explain it back": compare what the reader remembers with what was said
# ---------------------------------------------------------------------------

# Words that carry no instruction-specific meaning. Kept short and explicit so the
# check stays predictable.
_STOPWORDS = frozenset(
    """about after also back been come could days does doing don't each every from have here into just keep like
    look make might more most much need next only other over please really should some start still sure take
    than that their them then there these they this those time very want week weeks well were what when where
    which while will with would your you'll you're going also okay good right""".split()
)
_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


def key_words(sentence: str) -> set[str]:
    """Content words of a sentence: numbers and words of four or more letters, minus stopwords.

    >>> sorted(key_words("I'd like to start you on lisinopril 10 mg once a day."))
    ['10', 'lisinopril', 'once']
    """
    words = _WORD.findall(sentence.lower())
    return {word for word in words if (word.isdigit() or len(word) >= 4) and word not in _STOPWORDS}


@dataclass(frozen=True)
class RecallItem:
    quote: Quote
    remembered: bool
    shared_words: tuple[str, ...]


def recall_check(recollection: str, quotes: list[Quote]) -> list[RecallItem]:
    """Mark each quoted instruction as remembered when the reader's own words share
    at least two of its key words (or its only key word).

    This is a prompt to re-read, not a grade: different wording can mean the same
    thing, so the app says "you may want to check" rather than "wrong".
    """
    mine = key_words(recollection)
    items = []
    for quote in quotes:
        keys = key_words(quote.text)
        shared = tuple(sorted(keys & mine))
        needed = min(2, len(keys)) if keys else 1
        items.append(RecallItem(quote, len(shared) >= needed, shared))
    return items
