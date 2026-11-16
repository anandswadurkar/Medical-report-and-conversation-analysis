"""Known-answer, invalid-input and invariant tests for the offline analysis."""

from __future__ import annotations

import html
import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from medexplain import analyze_document
from medexplain.detect import DocType, detect_document_type
from medexplain.glossary import find_terms
from medexplain.labs import LabStatus, extract_lab_results, parse_lab_line
from medexplain.measurements import find_measurements
from medexplain.negation import Assertion, classify_mention
from medexplain.render import annotate
from medexplain.samples import SAMPLES
from medexplain.sections import split_sections, split_turns
from medexplain.terms import CATEGORIES, GLOSSARY


def _status(sentence: str, word: str) -> str:
    start = sentence.lower().index(word.lower())
    return classify_mention(sentence, start, start + len(word)).value


# --- negation -------------------------------------------------------------------
@pytest.mark.parametrize(
    ("sentence", "word", "expected"),
    [
        ("No pneumothorax.", "pneumothorax", "negated"),
        ("There is a small left pleural effusion.", "pleural effusion", "affirmed"),
        ("No pneumothorax or pleural effusion.", "pleural effusion", "negated"),
        ("No fracture, but there is a small effusion.", "effusion", "affirmed"),
        ("Malignancy cannot be excluded.", "Malignancy", "uncertain"),
        ("Findings are suspicious for malignancy.", "malignancy", "uncertain"),
        ("No evidence of pulmonary embolism.", "pulmonary embolism", "negated"),
        ("A pneumothorax is not seen.", "pneumothorax", "negated"),
        ("No suspicious mass.", "mass", "negated"),
        ("Evaluate for pneumonia.", "pneumonia", "uncertain"),
        # Negation does not cross a sentence boundary.
        ("No fracture. Large mass in the liver.", "mass", "affirmed"),
        ("Negative for high-grade dysplasia and malignancy.", "malignancy", "negated"),
    ],
)
def test_negation_known_answers(sentence: str, word: str, expected: str) -> None:
    assert _status(sentence, word) == expected


def test_negation_rejects_bad_span() -> None:
    with pytest.raises(ValueError):
        classify_mention("short", 3, 99)


# --- glossary -------------------------------------------------------------------
def test_glossary_entries_are_well_formed() -> None:
    valid_types = {t.value for t in DocType}
    for term in GLOSSARY:
        assert term.category in CATEGORIES
        assert term.definition.strip()
        assert set(term.doc_types) <= valid_types, term.term


def test_glossary_has_no_duplicate_spellings_within_a_doc_type() -> None:
    for doc_type in DocType:
        seen: dict[str, str] = {}
        for term in GLOSSARY:
            if term.doc_types and doc_type.value not in term.doc_types:
                continue
            for spelling in (term.term, *term.aliases):
                key = spelling if term.case_sensitive else spelling.lower()
                assert key not in seen or seen[key] == term.term, (
                    f"{spelling!r} defined twice for {doc_type.value}: {seen.get(key)} / {term.term}"
                )
                seen[key] = term.term


def test_terms_do_not_match_inside_words() -> None:
    hits = find_terms("She enjoyed the massage and the cystoscopy.")
    assert [hit.term.term for hit in hits] == []


def test_longest_match_wins() -> None:
    hits = find_terms("Body mass index is 24. Small pleural effusion.")
    assert [hit.term.term for hit in hits] == ["BMI", "pleural effusion"]


def test_short_capitalised_abbreviations_are_case_sensitive() -> None:
    # "us" in a conversation is not ultrasound; "US" in a report is.
    assert find_terms("Can you tell us more?") == []
    assert [hit.term.term for hit in find_terms("Renal US shows no hydronephrosis.")] == [
        "ultrasound",
        "hydronephrosis",
    ]


def test_context_dependent_abbreviation() -> None:
    pathology = find_terms("ER positive, PR positive.", DocType.PATHOLOGY)
    elsewhere = find_terms("She went to the ER last night.", DocType.CONVERSATION)
    assert pathology[0].term.definition.startswith("Estrogen receptor")
    assert elsewhere[0].term.definition == "Emergency room."


@settings(max_examples=150, deadline=None)
@given(st.text(alphabet=st.sampled_from(list("abc <>&\"'.\nNo pneumothorax mass effusion")), max_size=200))
def test_annotation_round_trips_to_escaped_text(text: str) -> None:
    # Invariant: annotation only adds tags; it never drops or reorders characters.
    annotated = annotate(text, find_terms(text))
    assert re.sub(r"<[^>]+>", "", annotated) == html.escape(text, quote=True)


# --- detection ------------------------------------------------------------------
@pytest.mark.parametrize("sample", list(SAMPLES.values()), ids=lambda s: s.key)
def test_samples_are_detected_as_their_type(sample) -> None:
    assert detect_document_type(sample.text).doc_type is sample.doc_type


def test_detection_returns_unknown_without_cues() -> None:
    detection = detect_document_type("Dear Sam, thanks for coming in. See you soon.")
    assert detection.doc_type is DocType.UNKNOWN
    assert "no document type" in detection.reason


def test_report_header_with_two_labels_is_not_a_conversation() -> None:
    text = "Patient: Jane Roe\nPhysician: Dr. A\nIMPRESSION: Normal chest radiograph.\nFINDINGS: Clear lungs."
    assert detect_document_type(text).doc_type is DocType.RADIOLOGY


def test_detection_rejects_empty_text() -> None:
    with pytest.raises(ValueError):
        detect_document_type("   \n ")


# --- sections and turns ---------------------------------------------------------
def test_sections_put_identifier_lines_in_header() -> None:
    names = [section.name for section in split_sections(SAMPLES["chest_xray"].text)]
    assert names[0] == "Header" and "MRN" not in names
    assert {"FINDINGS", "IMPRESSION", "RECOMMENDATION"} <= set(names)


def test_title_case_lab_line_is_not_a_section() -> None:
    assert split_sections("Hemoglobin: 10.2 g/dL\nGlucose: 99 mg/dL") == []


def test_turns_in_both_transcript_styles() -> None:
    mts = split_turns("Doctor: Hi.\nPatient: Hello.\nDoctor: Any pain?")
    aci = split_turns("[doctor] hi there\n[patient] hello\n[doctor] any pain")
    assert [t.role for t in mts] == [t.role for t in aci] == ["clinician", "patient", "clinician"]


def test_pa_and_lateral_is_not_a_speaker() -> None:
    assert split_turns("PA and lateral views of the chest.") == []


# --- labs -----------------------------------------------------------------------
def test_lab_rows_from_sample_are_complete_and_correct() -> None:
    labs = {lab.name: lab for lab in extract_lab_results(SAMPLES["blood_tests"].text, DocType.LAB)}
    assert len(labs) == 12
    assert labs["Hemoglobin"].status is LabStatus.BELOW
    assert labs["Glucose"].status is LabStatus.ABOVE
    assert labs["Sodium"].status is LabStatus.WITHIN
    assert labs["LDL Cholesterol"].range_high == 100 and labs["LDL Cholesterol"].status is LabStatus.ABOVE
    assert labs["eGFR"].comparator == ">" and labs["eGFR"].status is LabStatus.WITHIN
    # Units are kept as written, never converted.
    assert labs["WBC"].unit == "x10^3/uL"


def test_flag_that_contradicts_range_is_reported_not_resolved() -> None:
    result = parse_lab_line("Potassium 4.2 mmol/L 3.5-5.1 H")
    assert result is not None and result.status is LabStatus.CONFLICT


def test_lab_without_range_is_not_judged() -> None:
    result = parse_lab_line("TSH 2.1 mIU/L")
    assert result is not None and result.status is LabStatus.NO_RANGE


def test_less_than_value_is_only_judged_when_unambiguous() -> None:
    assert parse_lab_line("Troponin <0.01 ng/mL 0.00-0.04").status is LabStatus.UNCLEAR
    assert parse_lab_line("Ferritin <5 ng/mL 15-150").status is LabStatus.BELOW


def test_non_results_are_ignored() -> None:
    for line in ("Collected: 04/02/2026 08:15", "Age 54", "A 6 mm nodule", "INDICATION: 58-year-old with cough"):
        assert parse_lab_line(line) is None, line


def test_reversed_range_raises() -> None:
    with pytest.raises(ValueError):
        parse_lab_line("Sodium 140 mmol/L 145-136")


# --- measurements ---------------------------------------------------------------
def test_measurement_conversion_is_exact() -> None:
    (size,) = find_measurements("A 25.4 mm cyst.")
    assert size.dimensions_mm == (25.4,)
    assert size.plain.startswith("about 1.0 inches")


def test_bare_numbers_are_not_sizes() -> None:
    assert find_measurements("Follow up in 3 months. Glucose 132.") == []


# --- whole pipeline -------------------------------------------------------------
def test_pathology_sample_rules_out_cancer_words() -> None:
    analysis = analyze_document(SAMPLES["colon_pathology"].text)
    assert analysis.concerns == []
    assert {"carcinoma", "malignancy", "high-grade dysplasia"} <= {
        hit.matched_text.lower() for hit in analysis.ruled_out
    }


def test_chest_xray_flags_possible_malignancy_but_not_negated_pneumothorax() -> None:
    analysis = analyze_document(SAMPLES["chest_xray"].text)
    concerns = {hit.term.term: hit.assertion for hit in analysis.concerns}
    assert concerns == {"malignant": Assertion.UNCERTAIN}


def test_visit_summary_quotes_warning_and_instructions() -> None:
    analysis = analyze_document(SAMPLES["clinic_visit"].text)
    assert analysis.visit is not None
    assert any("emergency room" in quote.text for quote in analysis.visit.warning_signs)
    assert any("lisinopril 10 mg" in quote.text for quote in analysis.visit.instructions)
    assert len(analysis.visit.patient_questions) == 3


def test_reader_override_of_document_type() -> None:
    analysis = analyze_document("Some notes about the visit with no clear structure at all.", DocType.CONVERSATION)
    assert analysis.detection.doc_type is DocType.UNKNOWN and analysis.doc_type is DocType.CONVERSATION


def test_crlf_text_gives_same_result_as_lf() -> None:
    text = SAMPLES["chest_xray"].text
    a, b = analyze_document(text), analyze_document(text.replace("\n", "\r\n"))
    assert [(h.term.term, h.start) for h in a.term_hits] == [(h.term.term, h.start) for h in b.term_hits]


@pytest.mark.parametrize("text", ["", "   ", "too short"])
def test_analyze_rejects_empty_or_tiny_input(text: str) -> None:
    with pytest.raises(ValueError):
        analyze_document(text)
