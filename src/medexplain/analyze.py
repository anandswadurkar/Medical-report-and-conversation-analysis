"""Run every offline step on one document and collect the results."""

from __future__ import annotations

from dataclasses import dataclass

from .conversation import VisitSummary, summarize_visit
from .detect import Detection, DocType, detect_document_type
from .glossary import TermHit, find_terms
from .labs import LabResult, LabStatus, extract_lab_results
from .measurements import Measurement, find_measurements, unique_measurements
from .negation import Assertion
from .sections import Section, Turn, reading_order, split_sections, split_turns

# Below this length there is not enough text to say anything useful.
MIN_CHARACTERS = 20


@dataclass(frozen=True)
class Analysis:
    text: str
    detection: Detection
    doc_type: DocType  # detection.doc_type unless the reader chose a type
    sections: list[Section]
    turns: list[Turn]
    visit: VisitSummary | None
    term_hits: list[TermHit]
    labs: list[LabResult]
    measurements: list[Measurement]
    questions: list[str]

    @property
    def concerns(self) -> list[TermHit]:
        return [hit for hit in self.term_hits if hit.is_concern]

    @property
    def ruled_out(self) -> list[TermHit]:
        return [
            hit
            for hit in self.term_hits
            if hit.assertion is Assertion.NEGATED and hit.term.category in ("imaging finding", "pathology", "condition")
        ]


def suggest_questions(analysis_parts: dict) -> list[str]:
    """Build questions to ask the care team from what was found.

    Every question quotes the document's own words, so it is specific to it.
    """
    doc_type: DocType = analysis_parts["doc_type"]
    hits: list[TermHit] = analysis_parts["term_hits"]
    labs: list[LabResult] = analysis_parts["labs"]
    sections: list[Section] = analysis_parts["sections"]
    visit: VisitSummary | None = analysis_parts["visit"]

    questions = ["What is the main takeaway from this for me?"]
    seen: set[str] = set()
    for hit in hits:
        if not hit.is_concern or hit.term.term in seen:
            continue
        seen.add(hit.term.term)
        # Keep abbreviations as written ("PE"); lower-case words that were only
        # capitalised because they started a sentence ("Malignancy").
        word = hit.matched_text if hit.term.case_sensitive or hit.matched_text.isupper() else hit.matched_text.lower()
        if hit.assertion is Assertion.UNCERTAIN:
            questions.append(
                f"The report raises the possibility of “{word}”. How likely is it in my case, and what would confirm or rule it out?"
            )
        else:
            questions.append(f"The report mentions “{word}”. What does this mean for me, and what are the next steps?")

    for lab in labs:
        if lab.status in (LabStatus.BELOW, LabStatus.ABOVE):
            direction = "below" if lab.status is LabStatus.BELOW else "above"
            unit = f" {lab.unit}" if lab.unit else ""
            questions.append(
                f"My {lab.name} is {lab.value_text}{unit}, {direction} the printed range ({lab.range_text}). What might cause this, and does it need any action?"
            )
        elif lab.status is LabStatus.CONFLICT:
            questions.append(
                f"For {lab.name}, the report's flag ({lab.report_flag}) does not match its printed range ({lab.range_text}). Which is right?"
            )

    for section in sections:
        if section.key in ("recommendation", "recommendations") and section.body:
            questions.append(
                f"The report recommends: “{section.body.splitlines()[0][:160]}”. Who will arrange this, and when?"
            )
        if section.key == "comparison":
            questions.append("Has anything changed compared with my earlier tests?")

    if doc_type is DocType.PATHOLOGY:
        questions.append("Do I need any further treatment or tests because of this result?")
    if doc_type is DocType.LAB:
        questions.append("Should any of these tests be repeated, and when?")
    if visit is not None:
        if visit.instructions:
            questions.append("Can we go over my instructions once more so I'm sure I have them right?")
        if not visit.warning_signs:
            questions.append("Which symptoms should make me call you or seek urgent care?")
    questions.append("Do I need a follow-up appointment or test, and who will schedule it?")
    return questions


def analyze_document(text: str, doc_type: DocType | None = None) -> Analysis:
    """Analyze ``text`` offline. Nothing leaves the computer.

    Parameters
    ----------
    text
        The document text.
    doc_type
        The document type chosen by the reader. ``None`` uses the detector's answer.

    Raises
    ------
    ValueError
        If the text is empty or shorter than ``MIN_CHARACTERS``.
    """
    if text is None or len(text.strip()) < MIN_CHARACTERS:
        raise ValueError(
            f"the document has fewer than {MIN_CHARACTERS} characters of text; there is nothing to analyze"
        )
    # Normalise Windows and old Mac line endings once, so every character offset
    # below refers to the same string.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    detection = detect_document_type(text)
    chosen = doc_type if doc_type is not None else detection.doc_type

    turns = split_turns(text) if chosen is DocType.CONVERSATION else []
    visit = summarize_visit(turns) if turns else None
    sections = reading_order(split_sections(text)) if chosen is not DocType.CONVERSATION else []
    term_hits = find_terms(text, chosen)
    labs = extract_lab_results(text, chosen)
    measurements = (
        unique_measurements(find_measurements(text))
        if chosen in (DocType.RADIOLOGY, DocType.PATHOLOGY, DocType.UNKNOWN)
        else []
    )

    parts = {"doc_type": chosen, "term_hits": term_hits, "labs": labs, "sections": sections, "visit": visit}
    return Analysis(
        text=text,
        detection=detection,
        doc_type=chosen,
        sections=sections,
        turns=turns,
        visit=visit,
        term_hits=term_hits,
        labs=labs,
        measurements=measurements,
        questions=suggest_questions(parts),
    )
