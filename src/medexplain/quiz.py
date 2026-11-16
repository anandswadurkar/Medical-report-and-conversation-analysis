"""'Check my understanding' questions built from the document.

This is the teach-back idea from health-literacy practice: asking people to confirm
what they understood catches misunderstandings early (AHRQ Health Literacy Universal
Precautions Toolkit, Tool 5 "Use the Teach-Back Method",
https://www.ahrq.gov/health-literacy/improve/precautions/tool5.html).

Every question is answerable from the document alone, and every explanation quotes the
sentence the answer comes from. No question needs invented wrong answers about the
patient's care: the options are the same fixed set for every question of a kind, so
nothing false about the patient is ever shown as an option.
"""

from __future__ import annotations

from dataclasses import dataclass

from .analyze import Analysis
from .glossary import TermHit, mention_context
from .labs import LabStatus
from .negation import Assertion

FOUND = "Yes, it was found"
NOT_FOUND = "No, it was looked for and not found"
POSSIBLE = "It is described as a possibility"
FINDING_OPTIONS = (FOUND, NOT_FOUND, POSSIBLE)
_FINDING_ANSWER = {Assertion.AFFIRMED: FOUND, Assertion.NEGATED: NOT_FOUND, Assertion.UNCERTAIN: POSSIBLE}

ABOVE = "Above the printed range"
WITHIN = "Within the printed range"
BELOW = "Below the printed range"
LAB_OPTIONS = (ABOVE, WITHIN, BELOW)
_LAB_ANSWER = {LabStatus.ABOVE: ABOVE, LabStatus.WITHIN: WITHIN, LabStatus.BELOW: BELOW}

# Categories whose mentions describe a finding (not anatomy or report structure).
_FINDING_CATEGORIES = ("imaging finding", "pathology", "condition")
# Pathology words that describe a process, not a finding to ask about.
_SKIP_TERMS = {
    "chronic",
    "acute",
    "grade",
    "stage",
    "biopsy",
    "excision",
    "resection",
    "specimen",
    "margin",
    "lymph node",
    "frozen section",
    "immunohistochemistry",
    "H&E",
}


@dataclass(frozen=True)
class CheckQuestion:
    prompt: str
    options: tuple[str, ...]
    answer: str
    explanation: str

    def __post_init__(self) -> None:
        if self.answer not in self.options:
            raise ValueError(f"answer {self.answer!r} is not one of the options {self.options}")


def _quote(text: str, hit: TermHit) -> str:
    before, match, after = mention_context(text, hit)
    return f"“{(before + match + after).strip()}”"


def _finding_question(text: str, hit: TermHit) -> CheckQuestion:
    word = hit.matched_text if hit.matched_text.isupper() else hit.matched_text.lower()
    answer = _FINDING_ANSWER[hit.assertion]
    meaning = hit.term.definition.rstrip(".")
    return CheckQuestion(
        prompt=f"Did the report find {word}?",
        options=FINDING_OPTIONS,
        answer=answer,
        explanation=f"The report says {_quote(text, hit)}. ({hit.term.term}: {meaning}.)",
    )


def build_check_questions(analysis: Analysis, max_questions: int = 6) -> list[CheckQuestion]:
    """Return up to ``max_questions`` questions, findings first, then lab results.

    Findings are chosen so that the set includes, where the document allows, one that
    was ruled out, one that is possible and one that is present. That mix is what
    tests whether "no pneumothorax" was read correctly.

    Raises
    ------
    ValueError
        If ``max_questions`` is not positive.
    """
    if max_questions < 1:
        raise ValueError(f"max_questions must be at least 1, got {max_questions}")
    candidates: dict[Assertion, list[TermHit]] = {assertion: [] for assertion in Assertion}
    seen: set[str] = set()
    for hit in analysis.term_hits:
        if hit.term.category not in _FINDING_CATEGORIES or hit.term.term in _SKIP_TERMS or hit.term.term in seen:
            continue
        seen.add(hit.term.term)
        candidates[hit.assertion].append(hit)

    # Interleave negated, uncertain, affirmed so that a short quiz still has a mix.
    findings: list[TermHit] = []
    order = (Assertion.NEGATED, Assertion.UNCERTAIN, Assertion.AFFIRMED)
    while any(candidates[a] for a in order):
        for assertion in order:
            if candidates[assertion]:
                findings.append(candidates[assertion].pop(0))

    finding_questions = [_finding_question(analysis.text, hit) for hit in findings]
    labs = [lab for lab in analysis.labs if lab.status in _LAB_ANSWER and lab.comparator == ""]
    # Out-of-range results first: those are the ones worth being sure about.
    labs.sort(key=lambda lab: lab.status is LabStatus.WITHIN)
    lab_questions = []
    for lab in labs:
        unit = f" {lab.unit}" if lab.unit else ""
        lab_questions.append(
            CheckQuestion(
                prompt=f"Your {lab.name} is {lab.value_text}{unit}. Compared with the range printed on the report, is it…",
                options=LAB_OPTIONS,
                answer=_LAB_ANSWER[lab.status],
                explanation=f"The printed range is {lab.range_text}{unit}, and {lab.value_text} is {lab.status.value}. A result outside the range is a reason to ask, not necessarily a problem.",
            )
        )

    # Keep a mix when both kinds exist: reserve about a third of the slots for labs,
    # then let either kind fill slots the other cannot use.
    reserved_for_labs = min(len(lab_questions), max(1, max_questions // 3)) if finding_questions else len(lab_questions)
    keep_findings = min(len(finding_questions), max_questions - min(reserved_for_labs, max_questions))
    keep_labs = min(len(lab_questions), max_questions - keep_findings)
    return finding_questions[:keep_findings] + lab_questions[:keep_labs]
