"""Split a report into sections and a transcript into speaker turns."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .detect import _SPEAKER_LINE

# What each common section is for, in plain words. Keys are lower-case header names.
SECTION_GUIDE: dict[str, str] = {
    "impression": "The summary and conclusion. Start here.",
    "conclusion": "The summary and conclusion. Start here.",
    "final diagnosis": "The pathologist's conclusion. Start here.",
    "diagnosis": "The main conclusion. Start here.",
    "assessment": "The clinician's summary of what is going on.",
    "assessment and plan": "The clinician's summary and what happens next.",
    "plan": "What happens next: tests, treatment and follow-up.",
    "recommendation": "What the writer suggests should happen next.",
    "recommendations": "What the writer suggests should happen next.",
    "findings": "The detailed list of what was seen.",
    "results": "The detailed results.",
    "indication": "Why the test was ordered.",
    "clinical history": "Why the test was ordered.",
    "clinical indication": "Why the test was ordered.",
    "history": "Background on your health that the writer was given.",
    "reason for exam": "Why the test was ordered.",
    "comparison": "Earlier tests used to check for change.",
    "technique": "How the test was done.",
    "procedure": "What was done.",
    "exam": "Which test was done.",
    "examination": "Which test was done.",
    "specimen": "What tissue was sent to the lab.",
    "specimens": "What tissue was sent to the lab.",
    "specimen submitted": "What tissue was sent to the lab.",
    "gross description": "What the tissue looked like to the naked eye.",
    "gross": "What the tissue looked like to the naked eye.",
    "microscopic description": "What was seen under the microscope.",
    "microscopic": "What was seen under the microscope.",
    "comment": "Extra notes from the writer, often explaining the diagnosis.",
    "comments": "Extra notes from the writer, often explaining the diagnosis.",
    "note": "Extra notes from the writer.",
    "addendum": "Information added after the report was first finished.",
    "chief complaint": "The main reason for the visit, in the patient's words.",
    "medications": "Medicines you take.",
    "allergies": "Allergies on record.",
}

# Sections a reader should see first, in this order.
PRIORITY = (
    "impression",
    "conclusion",
    "final diagnosis",
    "diagnosis",
    "assessment and plan",
    "assessment",
    "recommendation",
    "recommendations",
    "plan",
)

_HEADER = re.compile(r"^[ \t]*(?P<name>[A-Za-z][A-Za-z /&()-]{1,40}?)[ \t]*:[ \t]*(?P<rest>.*)$")


@dataclass(frozen=True)
class Section:
    name: str
    body: str
    start: int  # character offset of the header line in the original text
    guide: str  # plain-language purpose, "" when the header is not a known one

    @property
    def key(self) -> str:
        return self.name.lower()


# ALL-CAPS labels that introduce an identifier, not a section ("MRN: 00987654").
_IDENTIFIER_LABELS = {
    "MRN",
    "DOB",
    "ID",
    "SSN",
    "FIN",
    "CSN",
    "ACC",
    "ACCESSION",
    "AGE",
    "SEX",
    "DATE",
    "TIME",
    "PHONE",
    "FAX",
    "NAME",
    "PATIENT",
    "PATIENT NAME",
    "ROOM",
    "BED",
}


def _is_header(name: str) -> bool:
    """Accept ALL-CAPS headers of any name, and Title-case headers only if known.

    "Hemoglobin: 10.2" is Title-case but not a section, so free-form Title-case names
    are rejected. Identifier labels such as "MRN" stay in the header block.
    """
    stripped = name.strip()
    if stripped.upper() in _IDENTIFIER_LABELS:
        return False
    if stripped.lower() in SECTION_GUIDE:
        return True
    letters = [char for char in stripped if char.isalpha()]
    return len(letters) >= 3 and all(char.isupper() for char in letters)


def split_sections(text: str) -> list[Section]:
    """Split a report into its labelled sections.

    Text before the first header becomes a section named "Header". Returns an
    empty list when no header is found; the caller then shows the text as a whole.

    >>> [s.name for s in split_sections("EXAM: CXR\\nFINDINGS: clear\\nIMPRESSION: normal")]
    ['EXAM', 'FINDINGS', 'IMPRESSION']
    """
    lines = text.splitlines(keepends=True)
    offsets = []
    position = 0
    for line in lines:
        offsets.append(position)
        position += len(line)

    headers: list[tuple[int, str, int, str]] = []  # (line index, name, offset, inline text)
    for index, line in enumerate(lines):
        match = _HEADER.match(line.rstrip("\r\n"))
        if match and _is_header(match.group("name")):
            headers.append((index, match.group("name").strip(), offsets[index], match.group("rest")))
    if not headers:
        return []

    sections: list[Section] = []
    first_line = headers[0][0]
    preamble = "".join(lines[:first_line]).strip()
    if preamble:
        sections.append(Section("Header", preamble, 0, "Details about the test and the patient."))
    for number, (line_index, name, offset, inline) in enumerate(headers):
        next_line = headers[number + 1][0] if number + 1 < len(headers) else len(lines)
        body = "\n".join(part for part in (inline.strip(), "".join(lines[line_index + 1 : next_line]).strip()) if part)
        sections.append(Section(name, body, offset, SECTION_GUIDE.get(name.lower(), "")))
    return sections


def reading_order(sections: list[Section]) -> list[Section]:
    """Put the conclusion-type sections first, keep the rest in document order."""
    first = [section for key in PRIORITY for section in sections if section.key == key]
    rest = [section for section in sections if section not in first]
    return first + rest


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

CLINICIAN = "clinician"
PATIENT = "patient"
FAMILY = "family"
OTHER = "other"

_ROLE_WORDS = {
    CLINICIAN: ("doctor", "dr", "physician", "clinician", "nurse", "provider", "guest_clinician"),
    PATIENT: ("patient", "pt"),
    FAMILY: ("guest_family", "family", "caregiver", "mother", "father", "parent", "spouse"),
}


@dataclass(frozen=True)
class Turn:
    speaker: str  # label as written, e.g. "Doctor", "[patient]"
    role: str  # one of CLINICIAN, PATIENT, FAMILY, OTHER
    text: str
    start: int


def speaker_role(label: str) -> str:
    """Map a speaker label to a role.

    >>> speaker_role("Dr. Patel"), speaker_role("[patient]"), speaker_role("Speaker 2")
    ('clinician', 'patient', 'other')
    """
    cleaned = label.strip().strip("[]").lower().rstrip(".")
    first_word = cleaned.split()[0].rstrip(".") if cleaned else ""
    for role, words in _ROLE_WORDS.items():
        if cleaned in words or first_word in words:
            return role
    return OTHER


def split_turns(text: str) -> list[Turn]:
    """Split a transcript into speaker turns. Unlabelled lines continue the last turn.

    >>> [(t.role, t.text) for t in split_turns("Doctor: How are you?\\nPatient: Tired.\\nVery tired.")]
    [('clinician', 'How are you?'), ('patient', 'Tired.\\nVery tired.')]
    """
    turns: list[Turn] = []
    matches = list(_SPEAKER_LINE.finditer(text))
    for index, match in enumerate(matches):
        label = (match.group("bracket") or match.group("plain")).strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        turns.append(Turn(label, speaker_role(label), body, match.start()))
    return turns
