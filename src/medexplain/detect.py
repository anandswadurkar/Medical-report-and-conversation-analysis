"""Guess what kind of document was uploaded, and show the evidence.

The detector counts cues (section headers, speaker labels, lab rows with reference
ranges) for each document type. It returns ``UNKNOWN`` rather than a best guess when
no type has enough cues or when two types tie, and the notebook then asks the reader
to choose. It is a heuristic and has not been validated on real reports yet; see the
README "Status" section.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class DocType(StrEnum):
    RADIOLOGY = "radiology"
    PATHOLOGY = "pathology"
    LAB = "lab"
    CONVERSATION = "conversation"
    UNKNOWN = "unknown"

    @property
    def label(self) -> str:
        return {
            "radiology": "Imaging (radiology) report",
            "pathology": "Pathology (tissue) report",
            "lab": "Lab test results",
            "conversation": "Doctor-patient conversation",
            "unknown": "Not sure",
        }[self.value]


# Each cue is (regex, weight, human-readable evidence). Weights are counts of
# independent signals: a section header that only one report type uses is worth 2,
# a word that also appears elsewhere is worth 1.
_FLAGS = re.IGNORECASE | re.MULTILINE
_CUES: dict[DocType, tuple[tuple[re.Pattern[str], int, str], ...]] = {
    DocType.RADIOLOGY: (
        (re.compile(r"^\s*impression\s*:", _FLAGS), 2, "has an IMPRESSION section"),
        (re.compile(r"^\s*findings\s*:", _FLAGS), 1, "has a FINDINGS section"),
        (re.compile(r"^\s*(technique|comparison)\s*:", _FLAGS), 2, "has a TECHNIQUE or COMPARISON section"),
        (
            re.compile(
                r"\b(radiograph|x-ray|ct|mri|ultrasound|sonograph\w*|mammogra\w+|pa and lateral|contrast)\b",
                re.IGNORECASE,
            ),
            1,
            "names an imaging test",
        ),
        (re.compile(r"\b(BI-RADS|Lung-RADS|LI-RADS|TI-RADS|PI-RADS)\b"), 2, "uses a RADS imaging score"),
    ),
    DocType.PATHOLOGY: (
        (
            re.compile(r"^\s*(gross description|microscopic description|gross|microscopic)\s*:", _FLAGS),
            2,
            "has GROSS or MICROSCOPIC sections",
        ),
        (re.compile(r"^\s*(final )?diagnosis\s*:", _FLAGS), 1, "has a DIAGNOSIS section"),
        (re.compile(r"^\s*specimens?( submitted)?\s*:", _FLAGS), 2, "lists a SPECIMEN"),
        (
            re.compile(
                r"\b(received in formalin|formalin|cassettes?|H&E|immunohistochemi\w+|margins?)\b", re.IGNORECASE
            ),
            1,
            "uses tissue-processing words",
        ),
        (re.compile(r"\b(biopsy|excision|resection)\b", re.IGNORECASE), 1, "mentions a biopsy or resection"),
    ),
    DocType.LAB: (
        (re.compile(r"\b(reference range|ref range|normal range)\b", re.IGNORECASE), 2, "has a reference-range column"),
        (
            re.compile(r"\b(CBC|CMP|BMP|lipid panel|metabolic panel|complete blood count)\b", re.IGNORECASE),
            1,
            "names a lab panel",
        ),
        (
            re.compile(r"\b(mg/dL|g/dL|mmol/L|mEq/L|U/L|IU/L|x10\^?\d+/[uµ]L|K/[uµ]L|fL|pg|ng/mL|mIU/L)\b"),
            1,
            "uses lab units",
        ),
    ),
    DocType.CONVERSATION: (),  # scored from speaker turns, see detect_document_type
}

# Two transcript styles: "Doctor: text" (MTS-Dialog) and "[doctor] text" (ACI-Bench).
# The plain style requires a colon, otherwise "PA and lateral views" would be a turn.
_SPEAKER_NAMES = r"doctor|dr\.?(?: [A-Z][a-z]+)?|patient|pt\.?|physician|clinician|nurse|provider|speaker ?\d+|guest_family|guest_clinician|family|caregiver|mother|father|parent|spouse"
_SPEAKER_LINE = re.compile(
    rf"^[ \t]*(?:\[(?P<bracket>{_SPEAKER_NAMES})\][ \t]*:?|(?P<plain>{_SPEAKER_NAMES})[ \t]*:)[ \t]*",
    re.IGNORECASE | re.MULTILINE,
)
_LAB_ROW = re.compile(r"\d+(?:\.\d+)?\s*(?:-|–|to)\s*\d+(?:\.\d+)?")

# A document needs at least this score for its top type to be accepted. Three is the
# smallest score that cannot come from a single generic word, because the strongest
# single cue is worth 2.
MIN_SCORE = 3


@dataclass(frozen=True)
class Detection:
    doc_type: DocType
    scores: dict[DocType, int]
    evidence: dict[DocType, list[str]]
    reason: str


def speaker_labels(text: str) -> list[str]:
    """Return the speaker label of every line that starts with one, lower-cased.

    >>> speaker_labels("Doctor: hi\\nPatient: hello\\n[doctor] ok")
    ['doctor', 'patient', 'doctor']
    """
    labels = []
    for match in _SPEAKER_LINE.finditer(text):
        label = match.group("bracket") or match.group("plain")
        labels.append(label.strip().lower().rstrip("."))
    return labels


def detect_document_type(text: str) -> Detection:
    """Score ``text`` against each document type.

    Raises
    ------
    ValueError
        If ``text`` is empty or only whitespace.
    """
    if not text or not text.strip():
        raise ValueError("the document is empty; nothing to analyze")

    scores: dict[DocType, int] = {doc_type: 0 for doc_type in DocType if doc_type is not DocType.UNKNOWN}
    evidence: dict[DocType, list[str]] = {doc_type: [] for doc_type in scores}

    for doc_type, cues in _CUES.items():
        for pattern, weight, description in cues:
            if pattern.search(text):
                scores[doc_type] += weight
                evidence[doc_type].append(description)

    lab_rows = sum(1 for line in text.splitlines() if _LAB_ROW.search(line) and re.search(r"[A-Za-z]{2,}", line))
    if lab_rows >= 3:
        scores[DocType.LAB] += 2
        evidence[DocType.LAB].append(f"{lab_rows} lines look like results with a range")

    labels = speaker_labels(text)
    distinct = set(labels)
    # Three turns, not two: a report header such as "Patient: ... / Physician: ..."
    # produces two labelled lines without being a conversation.
    if len(labels) >= 3 and len(distinct) >= 2:
        # Turn-taking between two or more speakers is the defining feature of a
        # conversation, so it alone is enough to clear MIN_SCORE.
        scores[DocType.CONVERSATION] += MIN_SCORE + min(len(labels) // 4, 3)
        evidence[DocType.CONVERSATION].append(
            f"{len(labels)} speaker turns by {len(distinct)} speakers ({', '.join(sorted(distinct))})"
        )

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    (best, best_score), (_, second_score) = ranked[0], ranked[1]
    if best_score < MIN_SCORE:
        return Detection(
            DocType.UNKNOWN,
            scores,
            evidence,
            f"no document type reached a score of {MIN_SCORE} (best was {best.value} with {best_score})",
        )
    if best_score == second_score:
        tied = [doc_type.value for doc_type, score in ranked if score == best_score]
        return Detection(DocType.UNKNOWN, scores, evidence, f"tie between {', '.join(tied)} at score {best_score}")
    return Detection(best, scores, evidence, f"{best.value} scored {best_score}; next best scored {second_score}")
