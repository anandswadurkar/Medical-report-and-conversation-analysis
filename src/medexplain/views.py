"""HTML pieces for the interactive app: range bars, term cards, guided steps, transcript.

Pure functions returning HTML strings, like ``render``. Colours are Okabe-Ito and every
visual cue is repeated in words.
"""

from __future__ import annotations

import html
import re

from .detect import DocType
from .glossary import TermHit, find_terms, mention_context, unique_terms
from .labs import LabResult, LabStatus
from .negation import Assertion
from .quiz import CheckQuestion
from .render import _LAB_SYMBOL, _STATUS_WORDS, LEGEND, annotate, wrap
from .sections import CLINICIAN, FAMILY, PATIENT, Section, Turn
from .terms import Term

# Okabe-Ito colours: range band in bluish green, marker blue inside, vermillion outside.
_BAND = "#009E73"
_OUTSIDE = "#D55E00"
_INSIDE = "#0072B2"
_FINDING_CATEGORIES = ("imaging finding", "pathology", "condition")


def _e(text: str) -> str:
    return html.escape(text, quote=True)


def range_bar_svg(lab: LabResult, width: int = 240, height: int = 34) -> str:
    """A small horizontal bar: the printed range as a band, the result as a marker.

    Returns an empty string when the report printed no range. The SVG carries a
    ``<title>`` and ``aria-label`` with the same information in words.

    >>> from medexplain.labs import parse_lab_line
    >>> "<svg" in range_bar_svg(parse_lab_line("Glucose 132 mg/dL 70-99 H"))
    True
    >>> range_bar_svg(parse_lab_line("TSH 2.1 mIU/L"))
    ''
    """
    low, high, value = lab.range_low, lab.range_high, lab.value
    if low is None and high is None:
        return ""
    # Axis: the printed limits plus the value, padded by a quarter of their spread so
    # the marker never sits on the edge. A one-sided range's band runs to the axis end.
    points = [p for p in (low, high, value) if p is not None]
    span = (max(points) - min(points)) or abs(value) or 1.0
    axis_min, axis_max = min(points) - 0.25 * span, max(points) + 0.25 * span
    if min(points) >= 0 and axis_min < 0:
        axis_min = 0.0  # lab values here are non-negative; don't draw a negative axis

    def x(v: float) -> float:
        return 6 + (width - 12) * (v - axis_min) / (axis_max - axis_min)

    band_start = x(low) if low is not None else x(axis_min)
    band_end = x(high) if high is not None else x(axis_max)
    colour = _OUTSIDE if lab.status in (LabStatus.BELOW, LabStatus.ABOVE) else _INSIDE
    marker = x(value)
    label = f"{lab.name}: {lab.value_text} {lab.unit}".strip() + f"; printed range {lab.range_text}; {lab.status.value}"
    low_text = f"{low:g}" if low is not None else ""
    high_text = f"{high:g}" if high is not None else ""
    return (
        f'<svg class="bar" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{_e(label)}">'
        f"<title>{_e(label)}</title>"
        f'<rect x="6" y="9" width="{width - 12}" height="8" rx="4" fill="rgba(127,127,127,0.25)"/>'
        f'<rect x="{band_start:.1f}" y="9" width="{max(band_end - band_start, 1):.1f}" height="8" rx="4" fill="{_BAND}" fill-opacity="0.55"/>'
        f'<line x1="{marker:.1f}" x2="{marker:.1f}" y1="3" y2="23" stroke="{colour}" stroke-width="3"/>'
        f'<circle cx="{marker:.1f}" cy="13" r="4.5" fill="{colour}"/>'
        f'<text x="{band_start:.1f}" y="32" text-anchor="middle">{_e(low_text)}</text>'
        f'<text x="{band_end:.1f}" y="32" text-anchor="middle">{_e(high_text)}</text>'
        "</svg>"
    )


def lab_table_html(labs: list[LabResult]) -> str:
    """The lab table with a range bar per row."""
    if not labs:
        return wrap("<p>No lab results were found.</p>")
    rows = []
    for lab in labs:
        flag = f" <span class='tag'>report flag: {_e(lab.report_flag)}</span>" if lab.report_flag else ""
        bar = range_bar_svg(lab) or "<span class='small'>no range to compare with</span>"
        rows.append(
            f"<tr><td><b>{_e(lab.name)}</b></td><td>{_e(lab.value_text)} {_e(lab.unit)}</td>"
            f"<td>{_e(lab.range_text or 'not printed')}</td><td>{bar}</td><td>{_e(_LAB_SYMBOL[lab.status])}{flag}</td></tr>"
        )
    return wrap(
        "<p class='small'>Each result is compared only with the range printed in your report. Ranges differ between labs, "
        "and a result slightly outside the range is common and often not a problem.</p>"
        "<table><tr><th>Test</th><th>Your result</th><th>Printed range</th><th>Where it sits</th><th>Compared with the range</th></tr>"
        + "".join(rows)
        + "</table><p class='small'>Green band: the printed range. Dot: your result (blue inside the range, orange outside).</p>"
    )


def lab_detail_html(lab: LabResult, meaning: Term | None) -> str:
    """One lab result explained: what the test measures, the bar, and the line as written."""
    unit = f" {lab.unit}" if lab.unit else ""
    about = (
        f"<p>{_e(meaning.definition)}</p>"
        if meaning
        else "<p class='small'>This test is not in the built-in glossary.</p>"
    )
    if lab.status in (LabStatus.BELOW, LabStatus.ABOVE):
        direction = "lower" if lab.status is LabStatus.BELOW else "higher"
        reading = (
            f"Your result is {direction} than the range printed on this report ({_e(lab.range_text)}{_e(unit)}). "
            "Results slightly outside a range are common, and what matters depends on your health overall, "
            "so this is a good thing to ask about rather than a conclusion."
        )
    elif lab.status is LabStatus.WITHIN:
        reading = f"Your result is within the range printed on this report ({_e(lab.range_text)}{_e(unit)})."
    elif lab.status is LabStatus.CONFLICT:
        reading = (
            f"The report flags this result ({_e(lab.report_flag)}), but the value is not outside the printed range. "
            "The lab may use a different range than the one printed. Ask your care team which one applies."
        )
    elif lab.status is LabStatus.UNCLEAR:
        reading = (
            "The result is written as a limit (for example &lt;0.01), so it cannot be placed exactly against the range."
        )
    else:
        reading = "No range is printed next to this result, so it is not compared with anything here. Ask what range your lab uses."
    return wrap(
        f"<div class='card'><div class='bigterm'>{_e(lab.name)}: {_e(lab.value_text)}{_e(unit)}</div>"
        f"{about}{range_bar_svg(lab, width=360, height=38)}<p>{reading}</p>"
        f"<p class='small'>As written on line {lab.line_number}: <code>{_e(lab.line)}</code></p></div>"
    )


def term_detail_html(term: Term, hits: list[TermHit], text: str) -> str:
    """One glossary term: its meaning, and each sentence it appears in with the mention marked."""
    contexts = []
    for hit in hits:
        before, match, after = mention_context(text, hit)
        contexts.append(
            f"<li>{_e(before)}<mark>{_e(match)}</mark>{_e(after)} <span class='tag'>{_e(_STATUS_WORDS[hit.assertion])}</span></li>"
        )
    concern = ""
    if term.concern and any(hit.is_concern for hit in hits):
        concern = (
            "<div class='notice small'>This is a word your care team usually talks through with you directly. "
            "Its meaning here depends on the full context.</div>"
        )
    elif term.concern and hits:
        concern = "<div class='notice calm small'>Every mention of this word here says it was <b>not</b> found.</div>"
    aliases = f" · also written {_e(', '.join(term.aliases[:4]))}" if term.aliases else ""
    where = f"<h4>Where it appears ({len(hits)})</h4><ul>{''.join(contexts)}</ul>" if hits else ""
    return wrap(
        f"<div class='card'><div class='bigterm'>{_e(term.term)}</div><div class='small'>{_e(term.category)}{aliases}</div>"
        f"<p>{_e(term.definition)}</p>{concern}{where}</div>"
    )


def lookup_html(query: str, terms: list[Term]) -> str:
    """Results of the free look-up box."""
    if not query.strip():
        return ""
    if not terms:
        return wrap(
            f"<p class='small'>“{_e(query)}” is not in the built-in glossary. Try a shorter part of the word, or search "
            "<a href='https://medlineplus.gov/' target='_blank' rel='noopener'>MedlinePlus</a>.</p>"
        )
    return wrap(
        "".join(
            f"<div class='card'><b>{_e(term.term)}</b> <span class='small'>({_e(term.category)})</span><br>{_e(term.definition)}</div>"
            for term in terms
        )
    )


def section_step_html(section: Section, index: int, total: int, doc_type: DocType) -> str:
    """One step of the guided reading: the section, its purpose and the words in it."""
    if not 0 <= index < total:
        raise ValueError(f"step {index} is outside 0..{total - 1}")
    hits = find_terms(section.body, doc_type)
    explained = "".join(f"<li><b>{_e(term.term)}</b>: {_e(term.definition)}</li>" for term, _ in unique_terms(hits))
    ruled_out = sorted(
        {
            hit.matched_text.lower()
            for hit in hits
            if hit.assertion is Assertion.NEGATED and hit.term.category in _FINDING_CATEGORIES
        }
    )
    calm = (
        f"<div class='notice calm small'>Looked for and not found here: {_e(', '.join(ruled_out))}.</div>"
        if ruled_out
        else ""
    )
    guide = f"<div class='guide'>{_e(section.guide)}</div>" if section.guide else ""
    words = (
        f"<h4>Words in this part</h4><ul>{explained}</ul>"
        if explained
        else "<p class='small'>No glossary words in this part.</p>"
    )
    first = " first" if index == 0 else ""
    return wrap(
        f"<div class='step'>Part {index + 1} of {total}</div>"
        f"<div class='card{first}'><h3>{_e(section.name.title())}</h3>{guide}"
        f"<div class='doc'>{annotate(section.body, hits)}</div>{calm}{words}</div>"
    )


def highlight(escaped_html: str, query: str) -> str:
    """Wrap case-insensitive matches of ``query`` in ``<mark>``, outside tags only.

    >>> highlight('a <span title="pain">pain</span> b', "pain")
    'a <span title="pain"><mark>pain</mark></span> b'
    """
    if not query.strip():
        return escaped_html
    pattern = re.compile(re.escape(html.escape(query.strip(), quote=True)), re.IGNORECASE)
    pieces = re.split(r"(<[^>]+>)", escaped_html)
    return "".join(
        piece if piece.startswith("<") else pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", piece)
        for piece in pieces
    )


def transcript_html(
    turns: list[Turn], doc_type: DocType, roles: tuple[str, ...] | None = None, search: str = ""
) -> str:
    """The conversation as chat bubbles, optionally filtered by role and searched."""
    shown = [turn for turn in turns if roles is None or turn.role in roles]
    if search.strip():
        shown = [turn for turn in shown if search.strip().lower() in turn.text.lower()]
    if not shown:
        return wrap("<p class='small'>No turns match.</p>")
    bubbles = []
    for turn in shown:
        role = turn.role if turn.role in (CLINICIAN, PATIENT, FAMILY) else "other"
        body = highlight(annotate(turn.text, find_terms(turn.text, doc_type)), search)
        bubbles.append(f'<div class="bubble {role}"><div class="who">{_e(turn.speaker)}</div>{body}</div>')
    return wrap(LEGEND + f"<p class='small'>Showing {len(shown)} of {len(turns)} turns.</p>" + "".join(bubbles))


def check_feedback_html(question: CheckQuestion, chosen: str | None) -> str:
    """Feedback for one 'check my understanding' answer."""
    if chosen is None:
        return ""
    if chosen == question.answer:
        return wrap(f"<div class='right'>✓ Right. {_e(question.explanation)}</div>")
    return wrap(
        f"<div class='wrong'>✗ Not quite: the answer is <b>{_e(question.answer)}</b>. {_e(question.explanation)}</div>"
    )


def text_size_css(percent: int) -> str:
    """A style override that scales all app text, for readers who need larger print."""
    if not 70 <= percent <= 250:
        raise ValueError(f"text size must be between 70 and 250 percent, got {percent}")
    return f"<style>.mx {{ font-size: {percent}%; }}</style>"
