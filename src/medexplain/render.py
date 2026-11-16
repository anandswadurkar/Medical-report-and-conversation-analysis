"""Turn an ``Analysis`` into HTML for the notebook.

Pure functions returning strings: no display calls here, so the same output can be
tested, shown in a widget, or saved to a file.

Colours are from the Okabe-Ito colour-blind-safe palette, and every status is also
written out in words or with a symbol, so nothing depends on colour alone.
Backgrounds are semi-transparent so the output reads in both light and dark themes.
"""

from __future__ import annotations

import html

from .analyze import Analysis
from .detect import DocType
from .glossary import TermHit, find_terms, unique_terms
from .labs import LabStatus
from .negation import Assertion
from .sections import CLINICIAN, FAMILY, PATIENT

CSS = """
<style>
.mx { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; line-height: 1.55; color: inherit; max-width: 980px; }
.mx h3 { margin: 0.9em 0 0.35em; font-size: 1.15em; }
.mx h4 { margin: 0.8em 0 0.25em; font-size: 1.0em; }
.mx .doc { white-space: pre-wrap; font-family: ui-monospace, Consolas, monospace; font-size: 0.92em;
           padding: 10px 12px; border-radius: 6px; background: rgba(127,127,127,0.08); }
.mx .card { border: 1px solid rgba(127,127,127,0.35); border-radius: 8px; padding: 10px 14px; margin: 10px 0; }
.mx .card.first { border-left: 5px solid #0072B2; }
.mx .guide { opacity: 0.8; font-style: italic; margin-bottom: 4px; }
.mx .notice { border-radius: 8px; padding: 10px 14px; margin: 10px 0; border-left: 5px solid #E69F00;
              background: rgba(230,159,0,0.12); }
.mx .calm { border-left-color: #009E73; background: rgba(0,158,115,0.10); }
.mx .info { border-left-color: #56B4E9; background: rgba(86,180,233,0.10); }
.mx .t { border-bottom: 1px solid #0072B2; cursor: help; }
.mx .t-concern { background: rgba(230,159,0,0.28); border-bottom: 2px solid #E69F00; }
.mx .t-uncertain { border-bottom: 2px dashed #56B4E9; }
.mx .t-negated { border-bottom: 2px dotted #009E73; }
.mx .tag { font-size: 0.78em; padding: 1px 6px; border-radius: 10px; margin-left: 3px; white-space: nowrap;
           border: 1px solid rgba(127,127,127,0.5); }
.mx table { border-collapse: collapse; margin: 6px 0; width: 100%; }
.mx th, .mx td { text-align: left; padding: 5px 8px; border-bottom: 1px solid rgba(127,127,127,0.3); vertical-align: top; }
.mx th { font-weight: 600; }
.mx .bubble { border-radius: 12px; padding: 7px 12px; margin: 6px 0; max-width: 78%; }
.mx .bubble.clinician { background: rgba(0,114,178,0.13); margin-right: auto; }
.mx .bubble.patient { background: rgba(0,158,115,0.13); margin-left: auto; }
.mx .bubble.family, .mx .bubble.other { background: rgba(127,127,127,0.13); margin-left: auto; }
.mx .who { font-size: 0.8em; font-weight: 600; opacity: 0.8; }
.mx .legend span { margin-right: 12px; }
.mx .small { font-size: 0.88em; opacity: 0.85; }
.mx mark { background: rgba(240,228,66,0.55); color: inherit; padding: 0 2px; border-radius: 3px; }
.mx .right { border-left: 5px solid #009E73; background: rgba(0,158,115,0.10); border-radius: 6px; padding: 6px 10px; }
.mx .wrong { border-left: 5px solid #D55E00; background: rgba(213,94,0,0.10); border-radius: 6px; padding: 6px 10px; }
.mx .step { font-size: 0.85em; letter-spacing: 0.03em; text-transform: uppercase; opacity: 0.75; }
.mx svg.bar text { fill: currentColor; font-size: 11px; }
.mx .bigterm { font-size: 1.25em; font-weight: 600; }
</style>
"""

DISCLAIMER = (
    "This tool explains words and numbers in your document. It does not diagnose, "
    "and it can miss things or get them wrong. Your care team knows your full history: "
    "use this to prepare questions for them, not to replace them."
)

_STATUS_WORDS = {
    Assertion.AFFIRMED: "mentioned",
    Assertion.NEGATED: "mentioned as NOT present",
    Assertion.UNCERTAIN: "mentioned as a possibility",
}

_LAB_SYMBOL = {
    LabStatus.BELOW: "↓ below range",
    LabStatus.ABOVE: "↑ above range",
    LabStatus.WITHIN: "✓ within range",
    LabStatus.NO_RANGE: "? no range printed",
    LabStatus.UNCLEAR: "? cannot tell",
    LabStatus.CONFLICT: "! flag and range disagree",
}


def _e(text: str) -> str:
    return html.escape(text, quote=True)


def _plural(count: int, noun: str) -> str:
    """Return "1 size" or "2 sizes".

    >>> _plural(1, "size"), _plural(2, "size")
    ('1 size', '2 sizes')
    """
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def wrap(body: str) -> str:
    return f'{CSS}<div class="mx">{body}</div>'


def _term_class(hit: TermHit) -> str:
    if hit.assertion is Assertion.NEGATED:
        return "t t-negated"
    if hit.term.concern:
        return "t t-concern"
    if hit.assertion is Assertion.UNCERTAIN:
        return "t t-uncertain"
    return "t"


def annotate(text: str, hits: list[TermHit]) -> str:
    """Escape ``text`` and wrap each glossary hit in a span with its meaning as a tooltip.

    Stripping the tags from the result gives back ``html.escape(text)`` exactly;
    the tests check this.
    """
    pieces = []
    cursor = 0
    for hit in sorted(hits, key=lambda h: h.start):
        if hit.start < cursor:
            continue
        pieces.append(_e(text[cursor : hit.start]))
        tooltip = f"{hit.term.term}: {hit.term.definition} ({_STATUS_WORDS[hit.assertion]})"
        pieces.append(f'<span class="{_term_class(hit)}" title="{_e(tooltip)}">{_e(text[hit.start : hit.end])}</span>')
        cursor = hit.end
    pieces.append(_e(text[cursor:]))
    return "".join(pieces)


LEGEND = (
    '<div class="legend small">Hover over an underlined word for its meaning. '
    '<span><span class="t">word</span> explained</span>'
    '<span><span class="t t-concern">word</span> worth asking about</span>'
    '<span><span class="t t-uncertain">word</span> a possibility</span>'
    '<span><span class="t t-negated">word</span> looked for and NOT found</span></div>'
)


def overview_html(analysis: Analysis) -> str:
    detection = analysis.detection
    parts = ["<h3>What this looks like</h3>"]
    if analysis.doc_type is DocType.UNKNOWN:
        parts.append(
            '<div class="notice info">I could not tell what kind of document this is '
            f"({_e(detection.reason)}). Choose the type in the drop-down above and press "
            "<b>Explain</b> again for better results.</div>"
        )
    else:
        chosen_by = "you chose" if analysis.doc_type is not detection.doc_type else "detected"
        clues = "; ".join(detection.evidence.get(analysis.doc_type, [])) or "chosen by you"
        parts.append(
            f"<p><b>{_e(analysis.doc_type.label)}</b> <span class='small'>({chosen_by}; clues: {_e(clues)})</span></p>"
        )

    concerns = analysis.concerns
    if concerns:
        words = sorted({hit.matched_text.lower() for hit in concerns})
        parts.append(
            '<div class="notice"><b>Some words here are worth talking through with your care team:</b> '
            f"{_e(', '.join(words))}. Seeing one of these words does not by itself tell you how serious "
            "anything is; the context, the wording and your history all matter. "
            "If you have not already discussed this document with your care team, consider contacting them. "
            "If you feel unwell, do not wait for an appointment.</div>"
        )
    ruled_out = sorted({hit.matched_text.lower() for hit in analysis.ruled_out})
    if ruled_out:
        parts.append(
            '<div class="notice calm"><b>Looked for and not found:</b> '
            f"{_e(', '.join(ruled_out))}. Reports often list things that were checked and are absent; "
            "these are usually reassuring.</div>"
        )

    counts = []
    if analysis.sections:
        counts.append(_plural(len(analysis.sections), "section"))
    if analysis.turns:
        counts.append(_plural(len(analysis.turns), "speaker turn"))
    counts.append(_plural(len(unique_terms(analysis.term_hits)), "term") + " explained")
    if analysis.labs:
        out_of_range = sum(1 for lab in analysis.labs if lab.status in (LabStatus.BELOW, LabStatus.ABOVE))
        counts.append(_plural(len(analysis.labs), "lab result") + f" ({out_of_range} outside the printed range)")
    if analysis.measurements:
        counts.append(_plural(len(analysis.measurements), "size"))
    parts.append(f"<p class='small'>Found: {_e(', '.join(counts))}.</p>")
    parts.append(f'<div class="notice info small">{_e(DISCLAIMER)}</div>')
    return wrap("".join(parts))


def walkthrough_html(analysis: Analysis) -> str:
    """The document section by section, conclusions first, with terms explained inline."""
    parts = [LEGEND]
    if analysis.sections:
        parts.append(
            "<p class='small'>Sections are shown with the summary first. The original order is under <b>Full text</b>.</p>"
        )
        for index, section in enumerate(analysis.sections):
            first = " first" if index == 0 and section.guide.endswith("Start here.") else ""
            hits = find_terms(section.body, analysis.doc_type)
            guide = f'<div class="guide">{_e(section.guide)}</div>' if section.guide else ""
            parts.append(
                f'<div class="card{first}"><h4>{_e(section.name.title())}</h4>{guide}<div class="doc">{annotate(section.body, hits)}</div></div>'
            )
    elif analysis.turns:
        parts.append(
            "<p class='small'>This is a conversation; see the <b>Conversation</b> tab for the turn-by-turn view.</p>"
        )
    parts.append(f"<h4>Full text</h4><div class='doc'>{annotate(analysis.text, analysis.term_hits)}</div>")
    return wrap("".join(parts))


def glossary_html(analysis: Analysis) -> str:
    grouped = unique_terms(analysis.term_hits)
    if not grouped:
        return wrap("<p>No terms from the built-in glossary were found.</p>")
    rows = []
    for term, hits in grouped:
        statuses = sorted({_STATUS_WORDS[hit.assertion] for hit in hits})
        as_written = sorted({hit.matched_text for hit in hits})
        flag = " ⚠" if term.concern and any(hit.is_concern for hit in hits) else ""
        rows.append(
            f"<tr><td><b>{_e(term.term)}</b>{flag}<div class='small'>as written: {_e(', '.join(as_written))}</div></td>"
            f"<td>{_e(term.definition)}</td><td>{_e('; '.join(statuses))}</td><td class='small'>{_e(term.category)}</td></tr>"
        )
    return wrap(
        f"<p class='small'>{len(grouped)} terms. Meanings are general, not specific to you. Learn more at "
        "<a href='https://medlineplus.gov/' target='_blank' rel='noopener'>MedlinePlus</a> (U.S. National Library of Medicine).</p>"
        "<table><tr><th>Word</th><th>What it usually means</th><th>How it appears here</th><th>Type</th></tr>"
        + "".join(rows)
        + "</table>"
    )


def numbers_html(analysis: Analysis) -> str:
    parts = []
    if analysis.labs:
        rows = []
        for lab in analysis.labs:
            range_text = lab.range_text or "not printed"
            flag = f" <span class='tag'>report flag: {_e(lab.report_flag)}</span>" if lab.report_flag else ""
            rows.append(
                f"<tr><td><b>{_e(lab.name)}</b></td><td>{_e(lab.value_text)} {_e(lab.unit)}</td>"
                f"<td>{_e(range_text)}</td><td>{_e(_LAB_SYMBOL[lab.status])}{flag}</td></tr>"
            )
        parts.append(
            "<h3>Lab results</h3><p class='small'>Each result is compared only with the range printed in your report. "
            "Ranges differ between labs, and a result slightly outside the range is common and often not a problem.</p>"
            "<table><tr><th>Test</th><th>Your result</th><th>Printed range</th><th>Compared with the range</th></tr>"
            + "".join(rows)
            + "</table>"
        )
        conflicts = [lab for lab in analysis.labs if lab.status is LabStatus.CONFLICT]
        if conflicts:
            parts.append(
                "<div class='notice'>For "
                + _e(", ".join(lab.name for lab in conflicts))
                + ", the report's own flag does not agree with its printed range. That can be a reading error on my side, "
                "or a different range used by the lab. Ask your care team which applies.</div>"
            )
    if analysis.measurements:
        items = "".join(f"<li>{_e(m.plain)}</li>" for m in analysis.measurements)
        parts.append(
            f"<h3>Sizes</h3><p class='small'>Metric sizes converted to inches (1 inch = 25.4 mm).</p><ul>{items}</ul>"
        )
    if not parts:
        parts.append("<p>No lab results or sizes were found.</p>")
    return wrap("".join(parts))


def conversation_html(analysis: Analysis) -> str:
    if not analysis.turns:
        return wrap(
            "<p>No speaker turns were found. Transcripts are recognised when lines start with a label such as "
            "<code>Doctor:</code> and <code>Patient:</code>, or <code>[doctor]</code> and <code>[patient]</code>.</p>"
        )
    visit = analysis.visit
    parts = []
    if visit is not None:

        def _list(title: str, quotes, empty: str) -> str:
            if not quotes:
                return f"<h4>{title}</h4><p class='small'>{empty}</p>"
            items = "".join(f"<li>{_e(q.text)} <span class='small'>({_e(q.speaker)})</span></li>" for q in quotes)
            return f"<h4>{title}</h4><ul>{items}</ul>"

        parts.append(
            "<h3>What to remember</h3><p class='small'>Sentences quoted word for word from the transcript.</p>"
        )
        parts.append(
            _list(
                "⚠ When to get help",
                visit.warning_signs,
                "No warning signs were mentioned. Consider asking which symptoms should make you call.",
            )
        )
        parts.append(_list("What you were asked to do", visit.instructions, "No instructions were found."))
        parts.append(_list("Questions you asked", visit.patient_questions, "No questions from the patient were found."))
    bubbles = []
    for turn in analysis.turns:
        role = turn.role if turn.role in (CLINICIAN, PATIENT, FAMILY) else "other"
        hits = find_terms(turn.text, analysis.doc_type)
        bubbles.append(
            f'<div class="bubble {role}"><div class="who">{_e(turn.speaker)}</div>{annotate(turn.text, hits)}</div>'
        )
    parts.append("<h3>The conversation</h3>" + LEGEND + "".join(bubbles))
    return wrap("".join(parts))


def questions_html(analysis: Analysis) -> str:
    items = "".join(f"<li>{_e(question)}</li>" for question in analysis.questions)
    return wrap(
        "<h3>Questions you could ask your care team</h3>"
        "<p class='small'>Built from the words and numbers in your document. Edit them, add your own, "
        "and bring the list to your next appointment or portal message.</p>"
        f"<ol>{items}</ol>"
    )


def questions_text(analysis: Analysis) -> str:
    """The questions as plain text, for copying into a portal message."""
    return "\n".join(f"{number}. {question}" for number, question in enumerate(analysis.questions, start=1))


def full_report_html(analysis: Analysis) -> str:
    """Everything on one page, for the no-widgets path and for saving."""
    return "".join(
        (
            overview_html(analysis),
            walkthrough_html(analysis),
            glossary_html(analysis),
            numbers_html(analysis),
            conversation_html(analysis) if analysis.turns else "",
            questions_html(analysis),
        )
    )
