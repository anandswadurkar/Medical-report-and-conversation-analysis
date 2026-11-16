"""Tests for the interactive features: quiz, look-up, range bars, recall, and the app's controls."""

from __future__ import annotations

import re

import pytest

from medexplain import analyze_document
from medexplain.conversation import Quote, key_words, recall_check
from medexplain.detect import DocType
from medexplain.glossary import find_terms, lookup, mention_context
from medexplain.labs import parse_lab_line
from medexplain.quiz import FOUND, NOT_FOUND, POSSIBLE, CheckQuestion, build_check_questions
from medexplain.samples import SAMPLES
from medexplain.views import (
    check_feedback_html,
    highlight,
    range_bar_svg,
    section_step_html,
    text_size_css,
    transcript_html,
)


# --- quiz -----------------------------------------------------------------------
def test_quiz_on_xray_mixes_ruled_out_possible_and_present() -> None:
    questions = build_check_questions(analyze_document(SAMPLES["chest_xray"].text))
    answers = {q.answer for q in questions}
    assert {FOUND, NOT_FOUND, POSSIBLE} <= answers
    by_prompt = {q.prompt: q for q in questions}
    assert by_prompt["Did the report find pneumothorax?"].answer == NOT_FOUND
    # The explanation quotes the source sentence.
    assert "No pneumothorax" in by_prompt["Did the report find pneumothorax?"].explanation


def test_quiz_on_labs_uses_printed_range() -> None:
    questions = build_check_questions(analyze_document(SAMPLES["blood_tests"].text))
    hemoglobin = next(q for q in questions if "Hemoglobin" in q.prompt)
    assert hemoglobin.answer == "Below the printed range"
    assert "12.0-15.5" in hemoglobin.explanation


def test_quiz_never_exceeds_limit_and_keeps_a_mix() -> None:
    text = SAMPLES["chest_xray"].text + "\nHemoglobin 10.9 g/dL 12.0-15.5 L\nGlucose 132 mg/dL 70-99 H\n"
    questions = build_check_questions(analyze_document(text, DocType.RADIOLOGY), max_questions=4)
    assert len(questions) == 4
    assert any("range printed" in q.prompt for q in questions) and any(
        q.prompt.startswith("Did the report") for q in questions
    )


def test_quiz_skips_less_than_values() -> None:
    analysis = analyze_document("LAB RESULTS\nTroponin <0.01 ng/mL 0.00-0.04\nReference range shown.", DocType.LAB)
    assert build_check_questions(analysis) == []


def test_quiz_rejects_bad_limit_and_bad_question() -> None:
    with pytest.raises(ValueError):
        build_check_questions(analyze_document(SAMPLES["chest_xray"].text), max_questions=0)
    with pytest.raises(ValueError):
        CheckQuestion("q", ("a", "b"), "c", "e")


def test_feedback_wording() -> None:
    question = CheckQuestion("Did it?", ("yes", "no"), "no", "Because.")
    assert "Right" in check_feedback_html(question, "no")
    assert "Not quite" in check_feedback_html(question, "yes") and "<b>no</b>" in check_feedback_html(question, "yes")
    assert check_feedback_html(question, None) == ""


# --- look-up and context --------------------------------------------------------
def test_lookup_ranks_exact_then_prefix_then_substring() -> None:
    assert lookup("nodule")[0].term == "nodule"
    assert lookup("hemo")[0].term == "hemoglobin"
    assert [t.term for t in lookup("   ")] == []
    assert lookup("zzzz") == []


def test_lookup_respects_document_type() -> None:
    assert lookup("ER", DocType.PATHOLOGY)[0].definition.startswith("Estrogen")
    assert lookup("ER", DocType.CONVERSATION)[0].definition == "Emergency room."


def test_mention_context_trims_long_sentences() -> None:
    text = "Word " * 100 + "pneumothorax " + "word " * 100 + "."
    hit = find_terms(text, DocType.RADIOLOGY)[0]
    before, match, after = mention_context(text, hit, max_chars=80)
    assert match == "pneumothorax" and before.startswith("…") and after.endswith("…")
    assert len(before) + len(after) < 120


# --- range bar ------------------------------------------------------------------
def _marker_x(svg: str) -> float:
    return float(re.search(r'<circle cx="([\d.]+)"', svg).group(1))


def _band(svg: str) -> tuple[float, float]:
    match = re.findall(r'<rect x="([\d.]+)" y="9" width="([\d.]+)"', svg)[1]
    start, width = float(match[0]), float(match[1])
    return start, start + width


@pytest.mark.parametrize(
    ("line", "where"),
    [
        ("Glucose 132 mg/dL 70-99 H", "right"),
        ("Hemoglobin 10.9 g/dL 12.0-15.5 L", "left"),
        ("Sodium 139 mmol/L 136-145", "inside"),
    ],
)
def test_range_bar_places_marker_relative_to_band(line: str, where: str) -> None:
    svg = range_bar_svg(parse_lab_line(line))
    marker, (low, high) = _marker_x(svg), _band(svg)
    assert {"right": marker > high, "left": marker < low, "inside": low <= marker <= high}[where]
    assert "aria-label" in svg and "<title>" in svg


def test_range_bar_for_one_sided_range_runs_to_the_edge() -> None:
    svg = range_bar_svg(parse_lab_line("LDL Cholesterol 162 mg/dL <100 H"))
    low, _ = _band(svg)
    assert low == pytest.approx(6.0)  # band starts at the axis start
    assert _marker_x(svg) > _band(svg)[1]


# --- views ----------------------------------------------------------------------
def test_section_step_rejects_out_of_range_index() -> None:
    sections = analyze_document(SAMPLES["chest_xray"].text).sections
    with pytest.raises(ValueError):
        section_step_html(sections[0], len(sections), len(sections), DocType.RADIOLOGY)


def test_highlight_never_touches_tag_attributes() -> None:
    result = highlight('<span title="dry cough">dry cough</span>', "cough")
    assert result == '<span title="dry cough">dry <mark>cough</mark></span>'


def test_transcript_filter_and_search() -> None:
    turns = analyze_document(SAMPLES["clinic_visit"].text).turns
    patient_only = transcript_html(turns, DocType.CONVERSATION, ("patient",))
    assert "bubble clinician" not in patient_only and "bubble patient" in patient_only
    searched = transcript_html(turns, DocType.CONVERSATION, None, "cough")
    assert "Showing 1 of" in searched and "<mark>cough</mark>" in searched


@pytest.mark.parametrize("bad", [50, 300])
def test_text_size_bounds(bad: int) -> None:
    with pytest.raises(ValueError):
        text_size_css(bad)


# --- recall ---------------------------------------------------------------------
def test_key_words_drop_stopwords_and_short_words() -> None:
    assert key_words("Please come back in four weeks.") == {"four"}


def test_recall_check_marks_what_was_covered() -> None:
    quotes = [
        Quote("Doctor", "clinician", "I'd like to start you on lisinopril 10 mg once a day."),
        Quote("Doctor", "clinician", "We'll check your kidney function and potassium with a blood test in two weeks."),
    ]
    items = recall_check("take lisinopril 10 mg every morning", quotes)
    assert [item.remembered for item in items] == [True, False]
    assert items[0].shared_words == ("10", "lisinopril")


# --- the app --------------------------------------------------------------------
@pytest.fixture
def xray_app():
    pytest.importorskip("ipywidgets")
    from medexplain.ui import SOURCE_SAMPLE, ExplainerApp

    app = ExplainerApp()
    app.sources.selected_index = SOURCE_SAMPLE
    app.sample.value = "chest_xray"  # choosing an example explains it straight away
    assert app.analysis is not None
    return app


def test_guided_reading_steps_through_sections(xray_app) -> None:
    app = xray_app
    total = len(app.analysis.sections)
    assert "Part 1 of" in app.step_view.value and "Impression" in app.step_view.value
    assert app.prev_button.disabled and not app.next_button.disabled
    for _ in range(total + 2):  # clicking past the end stays on the last part
        app.next_button.click()
    assert f"Part {total} of {total}" in app.step_view.value and app.next_button.disabled
    app.show_full.value = True
    assert "Full text" in app.step_view.value


def test_word_filter_and_detail(xray_app) -> None:
    app = xray_app
    app.word_filter.value = "negated"
    labels = [label for label, _ in app.word_list.options]
    assert labels == ["pneumothorax  ✓ not found"]
    assert "<mark>pneumothorax</mark>" in app.word_detail.value
    app.word_filter.value = "concern"
    assert [label for label, _ in app.word_list.options] == ["malignant  ⚠ ask"]


def test_lookup_box(xray_app) -> None:
    app = xray_app
    app.lookup_box.value = "atelectasis"
    assert "not fully inflated" in app.lookup_result.value
    app.lookup_box.value = "qwertyuiop"
    assert "not in the built-in glossary" in app.lookup_result.value


def test_quiz_interaction_scores_answers(xray_app) -> None:
    app = xray_app
    (radio, feedback), question = app._check_widgets[0], app._check_questions[0]
    radio.value = question.answer
    assert "Right" in feedback.value and "1 of 1 right" in app.check_score.value
    wrong = next(option for option in question.options if option != question.answer)
    app._check_widgets[1][0].value = wrong if app._check_questions[1].answer != wrong else question.options[0]
    assert "of 2 right" in app.check_score.value
    app.check_reset.click()
    assert all(r.value is None for r, _ in app._check_widgets)


def test_question_builder_and_save(xray_app, tmp_path) -> None:
    app = xray_app
    first_check, first_text = app._question_rows[0]
    first_check.value = False
    assert first_text not in app.final_questions.value
    app.own_question.value = "Can I keep exercising"
    app.add_question.click()
    assert "Can I keep exercising?" in app.final_questions.value
    app.save_folder.value = str(tmp_path)
    app.save_report_too.value = True
    app.save_button.click()
    saved = sorted(p.name for p in tmp_path.iterdir())
    assert len(saved) == 2 and saved[0].startswith("my_explanation_") and saved[1].startswith("my_questions_")
    text = next(tmp_path.glob("my_questions_*.txt")).read_text(encoding="utf-8")
    assert "Can I keep exercising?" in text and "\r\r" not in text


def test_save_to_missing_folder_reports_error(xray_app, tmp_path) -> None:
    app = xray_app
    app.save_folder.value = str(tmp_path / "does-not-exist")
    app.save_button.click()
    assert "does not exist" in app.save_status.value


def test_conversation_tools() -> None:
    pytest.importorskip("ipywidgets")
    from medexplain.ui import SOURCE_SAMPLE, ExplainerApp

    app = ExplainerApp()
    app.sources.selected_index = SOURCE_SAMPLE
    app.sample.value = "clinic_visit"
    assert len(app._todo_checks) == 4 and "0 of 4 done" in app.todo_status.value
    app._todo_checks[0].value = True
    assert "1 of 4 done" in app.todo_status.value
    app.speaker_filter.value = "clinician"
    assert "bubble patient" not in app.transcript.value
    app.transcript_search.value = "salt"
    assert "<mark>salt</mark>" in app.transcript.value
    app.recall_text.value = "Take lisinopril 10 mg each morning and cut down salt, walk 30 minutes"
    app.recall_button.click()
    assert "You covered" in app.recall_result.value and "re-read" in app.recall_result.value


def test_numbers_tab_picks_first_out_of_range_result() -> None:
    pytest.importorskip("ipywidgets")
    from medexplain.ui import SOURCE_SAMPLE, ExplainerApp

    app = ExplainerApp()
    app.sources.selected_index = SOURCE_SAMPLE
    app.sample.value = "blood_tests"
    assert "Hemoglobin" in app.lab_detail.value and "lower than the range" in app.lab_detail.value
    assert "red blood cells" in app.lab_detail.value  # meaning pulled from the glossary
    assert app.lab_table.value.count("<svg") == 12


def test_text_size_and_start_over(xray_app) -> None:
    app = xray_app
    app.text_size.value = 150
    assert "font-size: 150%" in app.size_style.value
    app.start_over.click()
    assert app.analysis is None and app.results.layout.display == "none"
