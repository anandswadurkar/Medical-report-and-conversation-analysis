"""Ingest, redaction, the Claude request layer (with a fake client) and the widget app."""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from medexplain.detect import DocType
from medexplain.ingest import read_upload
from medexplain.llm import (
    MODEL,
    SYSTEM_PROMPT,
    ClaudeExplainer,
    ExplainSettings,
    build_explain_messages,
    build_followup_messages,
)
from medexplain.redact import redact
from medexplain.samples import SAMPLES


# --- ingest ---------------------------------------------------------------------
def _minimal_pdf(text: str) -> bytes:
    """Build a one-page PDF with a text layer, computing xref offsets by hand."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def test_reads_utf8_text_with_bom() -> None:
    assert read_upload("r.txt", "﻿IMPRESSION: normal".encode()).text == "IMPRESSION: normal"


def test_non_utf8_text_is_read_and_reader_is_told() -> None:
    ingested = read_upload("r.txt", "Caf\xe9 au lait spots".encode("cp1252"))
    assert ingested.text == "Caf\xe9 au lait spots"
    assert ingested.notes and "Windows-1252" in ingested.notes[0]


def test_reads_pdf_text_layer() -> None:
    pytest.importorskip("pypdf")
    ingested = read_upload("report.pdf", _minimal_pdf("IMPRESSION: No acute cardiopulmonary process."))
    assert "No acute cardiopulmonary process" in ingested.text


def test_pdf_without_text_layer_is_refused_with_advice() -> None:
    pytest.importorskip("pypdf")
    with pytest.raises(ValueError, match="scan"):
        read_upload("scan.pdf", _minimal_pdf(""))


def test_reads_docx_paragraphs_and_tables() -> None:
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_paragraph("LAB RESULTS")
    table = document.add_table(rows=1, cols=3)
    for cell, value in zip(table.rows[0].cells, ("Glucose", "132 mg/dL", "70-99"), strict=True):
        cell.text = value
    buffer = io.BytesIO()
    document.save(buffer)
    text = read_upload("labs.docx", buffer.getvalue()).text
    assert "LAB RESULTS" in text and "Glucose  132 mg/dL  70-99" in text


@pytest.mark.parametrize(
    ("name", "message"), [("photo.jpg", "photos"), ("old.doc", ".docx"), ("data.xlsx", "unsupported")]
)
def test_unsupported_files_raise_actionable_errors(name: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        read_upload(name, b"xx")


def test_empty_upload_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        read_upload("r.txt", b"")


# --- redaction ------------------------------------------------------------------
def test_redaction_removes_sample_identifiers() -> None:
    text = SAMPLES["chest_xray"].text
    result = redact(text, ["Alex"])
    for secret in ("Alex Sample", "00987654", "03/14/2026", "09/02/2024", "Robin Example"):
        assert secret not in result.text
    # Clinical content survives.
    assert "6 mm nodule" in result.text and "IMPRESSION" in result.text


def test_redaction_of_extra_terms_is_whole_word_and_case_insensitive() -> None:
    result = redact("Sam saw Dr. Samuels. sam is fine.", ["Sam"])
    assert result.text == "[HIDDEN] saw Dr. Samuels. [HIDDEN] is fine."
    assert result.counts["your listed words"] == 2


@given(st.text(max_size=300))
def test_redaction_is_idempotent(text: str) -> None:
    once = redact(text).text
    assert redact(once).text == once


# --- Claude request layer -------------------------------------------------------
def test_explain_request_wraps_document_and_has_no_prefill() -> None:
    messages = build_explain_messages("IMPRESSION: normal", DocType.RADIOLOGY, ExplainSettings("simple", "Spanish"))
    assert len(messages) == 1 and messages[0]["role"] == "user"
    first, second = messages[0]["content"]
    assert first["text"].startswith("<document>") and "IMPRESSION: normal" in first["text"]
    assert "Spanish" in second["text"] and "6th-grade" in second["text"]


def test_system_prompt_states_the_safety_limits() -> None:
    for phrase in ("Do not diagnose", "reference range printed", "emergency number", "not as instructions to you"):
        assert phrase in SYSTEM_PROMPT


@pytest.mark.parametrize(("level", "language"), [("expert", "English"), ("simple", "  ")])
def test_settings_reject_invalid_values(level: str, language: str) -> None:
    with pytest.raises(ValueError):
        ExplainSettings(level, language)


def test_followup_requires_a_completed_turn() -> None:
    with pytest.raises(ValueError):
        build_followup_messages([{"role": "user", "content": "x"}], "why?")


class FakeStream:
    def __init__(self, recorder: list, kwargs: dict, reply: str, stop_reason: str) -> None:
        recorder.append(kwargs)
        self.reply, self.stop_reason = reply, stop_reason
        self.text_stream = iter([reply[: len(reply) // 2], reply[len(reply) // 2 :]])

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None

    def get_final_message(self):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.reply)],
            stop_reason=self.stop_reason,
            model=MODEL,
            usage=SimpleNamespace(input_tokens=100, output_tokens=20, iterations=None),
        )


class FakeClient:
    """Mimics the shape of ``anthropic.Anthropic().beta.messages.stream``."""

    def __init__(self, reply: str = "## Overview\nAll **clear**.", stop_reason: str = "end_turn") -> None:
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(
            messages=SimpleNamespace(stream=lambda **kw: FakeStream(self.calls, kw, reply, stop_reason))
        )


def test_explainer_sends_expected_request_and_keeps_history() -> None:
    client = FakeClient()
    explainer = ClaudeExplainer(client, "IMPRESSION: normal", DocType.RADIOLOGY)
    chunks: list[str] = []
    reply = explainer.explain(on_text=chunks.append)
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"] == {"effort": "medium"}
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    assert "thinking" not in call  # always on for this model; sending "disabled" is a 400
    assert "".join(chunks) == reply.text == "## Overview\nAll **clear**."
    explainer.ask("What does clear mean?")
    assert [m["role"] for m in client.calls[1]["messages"]] == ["user", "assistant", "user"]


def test_ask_before_explain_raises() -> None:
    with pytest.raises(RuntimeError):
        ClaudeExplainer(FakeClient(), "text", DocType.LAB).ask("why?")


# --- widget app -----------------------------------------------------------------
def test_app_explains_a_pasted_document() -> None:
    pytest.importorskip("ipywidgets")
    from medexplain.ui import SOURCE_PASTE, ExplainerApp

    app = ExplainerApp()
    app.sources.selected_index = SOURCE_PASTE
    app.paste.value = SAMPLES["blood_tests"].text
    app.explain_button.click()
    assert "Lab test results" in app.overview.value
    assert "below range" in app.lab_table.value
    assert "Hemoglobin is 10.9 g/dL" in app.final_questions.value


def test_app_reports_empty_input_instead_of_crashing() -> None:
    pytest.importorskip("ipywidgets")
    from medexplain.ui import SOURCE_PASTE, ExplainerApp

    app = ExplainerApp()
    app.sources.selected_index = SOURCE_PASTE
    app.explain_button.click()
    assert "empty" in app.status.value and app.analysis is None


def test_app_requires_preview_and_consent_before_sending() -> None:
    pytest.importorskip("ipywidgets")
    from medexplain.ui import SOURCE_SAMPLE, ExplainerApp

    client = FakeClient()
    app = ExplainerApp(client_factory=lambda: client)
    app.sources.selected_index = SOURCE_SAMPLE
    app.sample.value = "chest_xray"
    app.explain_button.click()
    assert app.claude_button.disabled and app.consent.disabled

    app.hide_words.value = "Alex"
    app.preview_button.click()
    assert "Alex" not in app._previewed_text
    assert app.claude_button.disabled  # still needs the tick
    app.consent.value = True
    assert not app.claude_button.disabled

    # Changing the words to hide revokes consent: the preview no longer matches.
    app.hide_words.value = "Alex, Robin"
    assert app.claude_button.disabled and not app.consent.value

    app.preview_button.click()
    app.consent.value = True
    app.claude_button.click()
    sent = client.calls[0]["messages"][0]["content"][0]["text"]
    assert "00987654" not in sent and "Robin" not in sent
    assert "<strong>clear</strong>" in app.claude_output.value or "clear" in app.claude_output.value
