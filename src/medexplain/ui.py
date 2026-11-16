"""The interactive notebook app (ipywidgets).

This is the thin I/O layer: it reads the reader's input, calls the pure functions in
``analyze``, ``render``, ``views``, ``quiz``, ``redact`` and ``llm``, and puts their
output into widgets. It holds no analysis logic of its own. Saving files happens only
here, and only when the reader presses a Save button.
"""

from __future__ import annotations

import datetime as _dt
import html
import time
from collections.abc import Callable
from pathlib import Path

import ipywidgets as W

from .analyze import Analysis, analyze_document
from .conversation import recall_check
from .detect import DocType
from .glossary import TermHit, all_spellings, lookup, unique_terms
from .ingest import SUPPORTED_EXTENSIONS, read_upload
from .llm import MODEL, READING_LEVELS, ClaudeExplainer, ClaudeReply, ExplainSettings
from .negation import Assertion
from .quiz import build_check_questions
from .redact import redact
from .render import CSS, full_report_html, glossary_html, overview_html, walkthrough_html, wrap
from .samples import SAMPLES
from .sections import CLINICIAN, FAMILY, PATIENT
from .terms import Term
from .views import (
    check_feedback_html,
    lab_detail_html,
    lab_table_html,
    lookup_html,
    section_step_html,
    term_detail_html,
    text_size_css,
    transcript_html,
)

SOURCE_UPLOAD, SOURCE_PASTE, SOURCE_SAMPLE = 0, 1, 2
TAB_OVERVIEW, TAB_GUIDED, TAB_WORDS, TAB_NUMBERS, TAB_CONVERSATION, TAB_CHECK, TAB_QUESTIONS, TAB_CLAUDE = range(8)
RESULT_TITLES = (
    "Overview",
    "Read it with me",
    "Words",
    "Numbers",
    "Conversation",
    "Check my understanding",
    "My questions",
    "Ask Claude (optional)",
)
WORD_FILTERS = (("All", "all"), ("Worth asking", "concern"), ("Not found", "negated"), ("Possible", "uncertain"))
SPEAKER_FILTERS = (("Everyone", "everyone"), ("Clinician", "clinician"), ("Patient & family", "patient"))
# ipywidgets treats a value of None as "nothing selected", so filters use string keys.
SPEAKER_ROLES: dict[str, tuple[str, ...] | None] = {
    "everyone": None,
    "clinician": (CLINICIAN,),
    "patient": (PATIENT, FAMILY),
}


def default_save_dir() -> Path:
    """Where Save writes by default: the user's Downloads folder, else their home."""
    downloads = Path.home() / "Downloads"
    return downloads if downloads.is_dir() else Path.home()


def _markdown_to_html(text: str) -> str:
    """Render the model's Markdown. Raw HTML in the reply is escaped first."""
    escaped = html.escape(text, quote=False)
    try:
        import markdown
    except ImportError:
        return f"<div class='doc'>{escaped}</div>"
    return markdown.markdown(escaped, extensions=["sane_lists"])


def _default_client_factory():
    import anthropic

    # Credentials come from ANTHROPIC_API_KEY or an `ant auth login` profile.
    return anthropic.Anthropic()


def _describe_api_error(error: Exception) -> str:
    """Turn an SDK exception into a sentence a patient can act on."""
    try:
        import anthropic
    except ImportError:
        return "The 'anthropic' package is not installed in this environment."
    if isinstance(error, anthropic.AuthenticationError):
        return "Claude could not be reached because no valid API key was found. Set ANTHROPIC_API_KEY (see the README), then restart the kernel."
    if isinstance(error, anthropic.PermissionDeniedError):
        return "The API key does not have permission to use this model."
    if isinstance(error, anthropic.RateLimitError):
        return "Too many requests right now. Wait a minute and try again."
    if isinstance(error, anthropic.APIStatusError):
        return f"The Claude API returned an error ({error.status_code}). Try again later."
    if isinstance(error, anthropic.APIConnectionError):
        return "Could not connect to the Claude API. Check your internet connection."
    return f"Something went wrong talking to Claude: {type(error).__name__}: {error}"


def _word_status(hits: list[TermHit]) -> str:
    """Summarise how a term appears, for the word filter and list labels."""
    if any(hit.is_concern for hit in hits):
        return "concern"
    if all(hit.assertion is Assertion.NEGATED for hit in hits):
        return "negated"
    if any(hit.assertion is Assertion.UNCERTAIN for hit in hits):
        return "uncertain"
    return "all"


_STATUS_LABEL = {"concern": "⚠ ask", "negated": "✓ not found", "uncertain": "? possible", "all": ""}


def _row(checkbox: W.Checkbox, text: str) -> W.HBox:
    """A checkbox with a wrapping label (a Checkbox's own description truncates long text)."""
    label = W.HTML(wrap(html.escape(text)), layout=W.Layout(width="auto"))
    return W.HBox([checkbox, label], layout=W.Layout(align_items="center"))


class ExplainerApp:
    """Upload or paste a document, explore it offline, optionally ask Claude."""

    def __init__(self, client_factory: Callable[[], object] | None = None, save_dir: Path | None = None) -> None:
        self.client_factory = client_factory or _default_client_factory
        self.analysis: Analysis | None = None
        self.explainer: ClaudeExplainer | None = None
        self._previewed_text: str | None = None
        self._transcript_html = ""
        self._words: list[tuple[Term, list[TermHit]]] = []
        self._step = 0
        self._custom_questions: list[str] = []
        self._question_rows: list[tuple[W.Checkbox, str]] = []
        self._todo_checks: list[W.Checkbox] = []
        self._check_widgets: list[tuple[W.RadioButtons, W.HTML]] = []
        self._check_questions: list = []

        self._build_header()
        self._build_input()
        self._build_overview()
        self._build_guided()
        self._build_words()
        self._build_numbers()
        self._build_conversation()
        self._build_check()
        self._build_questions(save_dir or default_save_dir())
        self._build_claude()

        self.results = W.Tab(
            children=[
                self.overview_panel,
                self.guided_panel,
                self.words_panel,
                self.numbers_panel,
                self.conversation_panel,
                self.check_panel,
                self.questions_panel,
                self.claude_panel,
            ]
        )
        for index, title in enumerate(RESULT_TITLES):
            self.results.set_title(index, title)
        self.results.layout.display = "none"

        self.widget = W.VBox(
            [
                self.size_style,
                self.header,
                W.HBox([self.text_size, self.start_over]),
                self.sources,
                W.HBox([self.doc_type, self.explain_button]),
                self.status,
                self.results,
            ]
        )

    # ================================================================== building
    def _build_header(self) -> None:
        self.size_style = W.HTML(text_size_css(100))
        self.header = W.HTML(
            CSS + "<div class='mx'><h3>Understand your medical report or visit</h3>"
            "<p class='small'>1. Upload, paste or pick an example. 2. Press <b>Explain</b>. "
            "3. Explore the tabs, check your understanding, and take your questions to your care team.</p></div>"
        )
        self.text_size = W.IntSlider(
            value=100, min=80, max=200, step=10, description="Text size %", style={"description_width": "initial"}
        )
        self.text_size.observe(
            lambda change: setattr(self.size_style, "value", text_size_css(change["new"])), names="value"
        )
        self.start_over = W.Button(description="Start over", icon="undo")
        self.start_over.on_click(self._on_start_over)

    def _build_input(self) -> None:
        self.upload = W.FileUpload(accept=",".join(SUPPORTED_EXTENSIONS), multiple=False, description="Choose file")
        self.paste = W.Textarea(
            placeholder="Paste the text of your report or visit transcript here.",
            layout=W.Layout(width="100%", height="200px"),
        )
        self.sample = W.Dropdown(
            options=[("Pick an example", "")] + [(sample.title, key) for key, sample in SAMPLES.items()],
            layout=W.Layout(width="420px"),
        )
        self.sources = W.Tab(
            children=[
                W.VBox(
                    [
                        W.HTML(f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}. The file stays on this computer."),
                        self.upload,
                    ]
                ),
                W.VBox([self.paste]),
                W.VBox([W.HTML("Made-up examples, for trying the tool."), self.sample]),
            ]
        )
        for index, title in enumerate(("Upload a file", "Paste text", "Try an example")):
            self.sources.set_title(index, title)
        self.sources.selected_index = SOURCE_PASTE
        self.doc_type = W.Dropdown(
            options=[("Detect automatically", None)] + [(t.label, t) for t in DocType if t is not DocType.UNKNOWN],
            description="Document type",
            style={"description_width": "initial"},
        )
        self.explain_button = W.Button(description="Explain", button_style="primary", icon="search")
        self.explain_button.on_click(self._on_explain)
        # Choosing an example runs it straight away: one less step for a first try.
        self.sample.observe(lambda change: self._on_explain() if change["new"] else None, names="value")
        self.status = W.HTML()

    def _build_overview(self) -> None:
        self.overview = W.HTML()
        self.go_guided = W.Button(description="Read it with me", icon="book", button_style="info")
        self.go_check = W.Button(description="Check my understanding", icon="check")
        self.go_questions = W.Button(description="My questions", icon="list")
        self.go_guided.on_click(lambda _: setattr(self.results, "selected_index", TAB_GUIDED))
        self.go_check.on_click(lambda _: setattr(self.results, "selected_index", TAB_CHECK))
        self.go_questions.on_click(lambda _: setattr(self.results, "selected_index", TAB_QUESTIONS))
        self.overview_panel = W.VBox([self.overview, W.HBox([self.go_guided, self.go_check, self.go_questions])])

    def _build_guided(self) -> None:
        self.step_progress = W.IntProgress(value=0, min=0, max=1, layout=W.Layout(width="300px"))
        self.step_label = W.HTML()
        self.step_view = W.HTML()
        self.prev_button = W.Button(description="Previous", icon="arrow-left")
        self.next_button = W.Button(description="Next", icon="arrow-right", button_style="info")
        self.show_full = W.ToggleButton(description="Show the whole document", icon="file-text")
        self.prev_button.on_click(lambda _: self._go_step(self._step - 1))
        self.next_button.on_click(lambda _: self._go_step(self._step + 1))
        self.show_full.observe(lambda _: self._render_step(), names="value")
        self.guided_panel = W.VBox(
            [
                W.HBox([self.prev_button, self.next_button, self.step_progress, self.step_label]),
                self.show_full,
                self.step_view,
            ]
        )

    def _build_words(self) -> None:
        self.word_filter = W.ToggleButtons(options=list(WORD_FILTERS), value="all", style={"button_width": "auto"})
        self.word_list = W.Select(options=[], rows=14, layout=W.Layout(width="280px"))
        self.word_detail = W.HTML(layout=W.Layout(flex="1 1 auto", min_width="0"))
        self.word_filter.observe(lambda _: self._refresh_word_list(), names="value")
        self.word_list.observe(self._on_word_selected, names="value")
        self.lookup_box = W.Combobox(
            placeholder="Type any medical word, e.g. 'atelectasis' or 'bid'",
            options=all_spellings(),
            ensure_option=False,
            layout=W.Layout(width="420px"),
        )
        self.lookup_result = W.HTML()
        self.lookup_box.observe(self._on_lookup, names="value")
        self.glossary_table = W.HTML()
        table = W.Accordion(children=[self.glossary_table])
        table.set_title(0, "All words as one table")
        table.selected_index = None
        self.words_panel = W.VBox(
            [
                W.HTML(wrap("<p class='small'>Pick a word to see what it means and every sentence it appears in.</p>")),
                self.word_filter,
                W.HBox([self.word_list, self.word_detail]),
                W.HTML(wrap("<h4>Look up any word</h4>")),
                self.lookup_box,
                self.lookup_result,
                table,
            ]
        )

    def _build_numbers(self) -> None:
        self.lab_table = W.HTML()
        self.lab_picker = W.Dropdown(
            options=[], description="Explain", style={"description_width": "initial"}, layout=W.Layout(width="420px")
        )
        self.lab_detail = W.HTML()
        self.sizes = W.HTML()
        self.lab_picker.observe(self._on_lab_selected, names="value")
        self.numbers_panel = W.VBox([self.lab_table, self.lab_picker, self.lab_detail, self.sizes])

    def _build_conversation(self) -> None:
        self.visit_summary = W.HTML()
        self.todo_box = W.VBox()
        self.todo_status = W.HTML()
        self.speaker_filter = W.ToggleButtons(
            options=list(SPEAKER_FILTERS), value="everyone", style={"button_width": "auto"}
        )
        self.transcript_search = W.Text(
            placeholder="Search the conversation, e.g. 'pressure'", layout=W.Layout(width="360px")
        )
        self.transcript = W.HTML()
        self.speaker_filter.observe(lambda _: self._render_transcript(), names="value")
        self.transcript_search.observe(lambda _: self._render_transcript(), names="value")
        self.recall_text = W.Textarea(
            placeholder="Without looking: what were you asked to do? Write it in your own words.",
            layout=W.Layout(width="100%", height="110px"),
        )
        self.recall_button = W.Button(description="Compare with what was said", icon="exchange")
        self.recall_result = W.HTML()
        self.recall_button.on_click(self._on_recall)
        recall = W.Accordion(children=[W.VBox([self.recall_text, self.recall_button, self.recall_result])])
        recall.set_title(0, "Explain it back (optional practice)")
        recall.selected_index = None
        self.conversation_panel = W.VBox(
            [
                self.visit_summary,
                W.HTML(wrap("<h4>My to-do list</h4><p class='small'>Tick things off as you do them.</p>")),
                self.todo_box,
                self.todo_status,
                recall,
                W.HTML(wrap("<h3>The conversation</h3>")),
                W.HBox([self.speaker_filter, self.transcript_search]),
                self.transcript,
            ]
        )

    def _build_check(self) -> None:
        self.check_intro = W.HTML()
        self.check_box = W.VBox()
        self.check_score = W.HTML()
        self.check_reset = W.Button(description="Try again", icon="refresh")
        self.check_reset.on_click(lambda _: self._render_check())
        self.check_panel = W.VBox([self.check_intro, self.check_box, self.check_score, self.check_reset])

    def _build_questions(self, save_dir: Path) -> None:
        self.question_box = W.VBox()
        self.own_question = W.Text(placeholder="Add your own question", layout=W.Layout(width="520px"))
        self.add_question = W.Button(description="Add", icon="plus")
        self.add_question.on_click(self._on_add_question)
        self.final_questions = W.Textarea(layout=W.Layout(width="100%", height="170px"), description="My list:")
        self.save_folder = W.Text(
            value=str(save_dir),
            description="Save to folder",
            style={"description_width": "initial"},
            layout=W.Layout(width="520px"),
        )
        self.save_report_too = W.Checkbox(
            value=False, description="Also save the full explanation as a web page", indent=False
        )
        self.save_button = W.Button(description="Save", icon="save", button_style="success")
        self.save_status = W.HTML()
        self.save_button.on_click(self._on_save)
        self.questions_panel = W.VBox(
            [
                W.HTML(
                    wrap(
                        "<h3>Questions to ask your care team</h3><p class='small'>Untick any you don't need, add your own, then copy "
                        "the list or save it. Bring it to your appointment or paste it into a portal message.</p>"
                    )
                ),
                self.question_box,
                W.HBox([self.own_question, self.add_question]),
                self.final_questions,
                self.save_folder,
                self.save_report_too,
                self.save_button,
                self.save_status,
            ]
        )

    def _build_claude(self) -> None:
        self.hide_words = W.Text(
            placeholder="e.g. your name, your doctor's name, your town",
            description="Words to hide",
            style={"description_width": "initial"},
            layout=W.Layout(width="600px"),
        )
        self.preview_button = W.Button(description="Preview what would be sent", icon="eye")
        self.preview = W.HTML()
        self.consent = W.Checkbox(
            value=False,
            description="I checked the preview and agree to send this text to Anthropic's API.",
            indent=False,
            layout=W.Layout(width="auto"),
            disabled=True,
        )
        self.reading_level = W.Dropdown(
            options=list(READING_LEVELS),
            value="standard",
            description="Reading level",
            style={"description_width": "initial"},
        )
        self.language = W.Text(value="English", description="Answer in", style={"description_width": "initial"})
        self.claude_button = W.Button(
            description="Explain with Claude", button_style="info", icon="comment", disabled=True
        )
        self.claude_output = W.HTML()
        self.followup = W.Text(
            placeholder="Ask a follow-up question about this document", layout=W.Layout(width="600px"), disabled=True
        )
        self.ask_button = W.Button(description="Ask", icon="question", disabled=True)
        self.preview_button.on_click(self._on_preview)
        self.consent.observe(self._on_consent, names="value")
        self.hide_words.observe(self._invalidate_preview, names="value")
        self.claude_button.on_click(self._on_claude)
        self.ask_button.on_click(self._on_ask)
        intro = W.HTML(
            wrap(
                "<div class='notice info'><b>Optional.</b> Everything in the other tabs ran on this computer. "
                f"This tab can send your document to Claude ({html.escape(MODEL)}, run by Anthropic) for a fuller explanation "
                "in your own words and language, and answer follow-up questions.<br><br>"
                "<b>Before sending:</b> dates, phone numbers, emails, record numbers and labelled name or address lines are "
                "hidden automatically, plus any words you list below. This is not perfect: names inside sentences can slip "
                "through, so read the preview. Only send what you are comfortable sharing. Requires an Anthropic API key "
                "(see the README).</div>"
            )
        )
        self.claude_panel = W.VBox(
            [
                intro,
                self.hide_words,
                self.preview_button,
                self.preview,
                self.consent,
                W.HBox([self.reading_level, self.language]),
                self.claude_button,
                self.claude_output,
                W.HBox([self.followup, self.ask_button]),
            ]
        )

    # ================================================================== input
    def _set_status(self, message: str, kind: str = "info") -> None:
        css = {"info": "notice info", "error": "notice", "ok": "notice calm"}[kind]
        self.status.value = wrap(f"<div class='{css}'>{html.escape(message)}</div>") if message else ""

    def read_input(self) -> tuple[str, list[str]]:
        """Return the text to analyze and any notes about how it was read."""
        source = self.sources.selected_index
        if source == SOURCE_UPLOAD:
            if not self.upload.value:
                raise ValueError("No file chosen yet. Use 'Choose file', or switch to 'Paste text'.")
            item = self.upload.value[0]
            ingested = read_upload(item["name"], bytes(item["content"]))
            return ingested.text, list(ingested.notes)
        if source == SOURCE_SAMPLE:
            if not self.sample.value:
                raise ValueError("Pick an example from the list first.")
            return SAMPLES[self.sample.value].text, ["This is a made-up example, not a real patient."]
        if not self.paste.value.strip():
            raise ValueError("The text box is empty. Paste your document text first.")
        return self.paste.value, []

    def _on_explain(self, _button=None) -> None:
        try:
            text, notes = self.read_input()
            analysis = analyze_document(text, self.doc_type.value)
        except ValueError as error:
            self._set_status(str(error), "error")
            return
        self.analysis = analysis
        self.overview.value = overview_html(analysis)
        self._load_guided()
        self._load_words()
        self._load_numbers()
        self._load_conversation()
        self._render_check()
        self._load_questions()
        self._reset_claude()
        self.results.layout.display = None
        self.results.selected_index = TAB_OVERVIEW
        self._set_status(" ".join(["Done. Explore the tabs below."] + notes), "ok")

    def _on_start_over(self, _button=None) -> None:
        self.analysis = None
        self.paste.value = ""
        self.sample.value = ""
        self.results.layout.display = "none"
        self._reset_claude()
        self._set_status("")

    # ================================================================== guided reading
    def _load_guided(self) -> None:
        assert self.analysis is not None
        self._step = 0
        has_steps = bool(self.analysis.sections)
        self.show_full.value = not has_steps
        self.show_full.disabled = not has_steps
        self._render_step()

    def _go_step(self, index: int) -> None:
        if self.analysis is None or not self.analysis.sections:
            return
        self._step = max(0, min(index, len(self.analysis.sections) - 1))
        self.show_full.value = False
        self._render_step()

    def _render_step(self) -> None:
        if self.analysis is None:
            return
        sections = self.analysis.sections
        if self.show_full.value or not sections:
            note = (
                ""
                if sections
                else wrap("<p class='small'>This document has no labelled sections, so it is shown whole.</p>")
            )
            self.step_view.value = note + walkthrough_html(self.analysis)
            self.prev_button.disabled = self.next_button.disabled = True
            self.step_progress.max, self.step_progress.value = 1, 1
            self.step_label.value = ""
            return
        total = len(sections)
        self.step_view.value = section_step_html(sections[self._step], self._step, total, self.analysis.doc_type)
        self.prev_button.disabled = self._step == 0
        self.next_button.disabled = self._step == total - 1
        self.step_progress.max, self.step_progress.value = total, self._step + 1
        self.step_label.value = f"&nbsp;{self._step + 1} / {total}"

    # ================================================================== words
    def _load_words(self) -> None:
        assert self.analysis is not None
        self._words = unique_terms(self.analysis.term_hits)
        self.glossary_table.value = glossary_html(self.analysis)
        self.word_filter.value = "all"
        self._refresh_word_list()
        self.lookup_box.options = all_spellings(self.analysis.doc_type)
        self.lookup_box.value = ""
        self.lookup_result.value = ""

    def _refresh_word_list(self) -> None:
        wanted = self.word_filter.value
        options = []
        for index, (term, hits) in enumerate(self._words):
            status = _word_status(hits)
            if wanted != "all" and status != wanted:
                continue
            label = f"{term.term}  {_STATUS_LABEL[status]}".rstrip()
            options.append((label, index))
        self.word_list.options = options
        if options:
            self.word_list.value = options[0][1]
            self._on_word_selected({"new": options[0][1]})
        else:
            self.word_detail.value = wrap("<p class='small'>No words of this kind in your document.</p>")

    def _on_word_selected(self, change) -> None:
        index = change["new"]
        if self.analysis is None or index is None or index >= len(self._words):
            return
        term, hits = self._words[index]
        self.word_detail.value = term_detail_html(term, hits, self.analysis.text)

    def _on_lookup(self, change) -> None:
        doc_type = self.analysis.doc_type if self.analysis else DocType.UNKNOWN
        query = change["new"] or ""
        self.lookup_result.value = lookup_html(query, lookup(query, doc_type))

    # ================================================================== numbers
    def _load_numbers(self) -> None:
        assert self.analysis is not None
        labs = self.analysis.labs
        self.lab_table.value = wrap("<h3>Lab results</h3>") + lab_table_html(labs)
        self.lab_picker.options = [
            (f"{lab.name}: {lab.value_text} {lab.unit}".strip(), index) for index, lab in enumerate(labs)
        ]
        self.lab_picker.layout.display = None if labs else "none"
        if labs:
            out_of_range = next(
                (i for i, lab in enumerate(labs) if lab.status.name in ("BELOW", "ABOVE", "CONFLICT")), 0
            )
            self.lab_picker.value = out_of_range
            self._on_lab_selected({"new": out_of_range})
        else:
            self.lab_detail.value = ""
        if self.analysis.measurements:
            items = "".join(f"<li>{html.escape(m.plain)}</li>" for m in self.analysis.measurements)
            self.sizes.value = wrap(
                f"<h3>Sizes</h3><p class='small'>Metric sizes converted to inches (1 inch = 25.4 mm).</p><ul>{items}</ul>"
            )
        else:
            self.sizes.value = ""

    def _on_lab_selected(self, change) -> None:
        index = change["new"]
        if self.analysis is None or index is None or index >= len(self.analysis.labs):
            return
        lab = self.analysis.labs[index]
        meaning = next(
            (term for term in lookup(lab.name, self.analysis.doc_type, limit=3) if term.category == "lab test"), None
        )
        self.lab_detail.value = lab_detail_html(lab, meaning)

    # ================================================================== conversation
    def _load_conversation(self) -> None:
        assert self.analysis is not None
        visit = self.analysis.visit
        self._todo_checks = []
        self.recall_text.value = ""
        self.recall_result.value = ""
        if visit is None:
            self.visit_summary.value = wrap(
                "<p>No speaker turns were found. Transcripts are recognised when lines start with a label such as "
                "<code>Doctor:</code> and <code>Patient:</code>, or <code>[doctor]</code> and <code>[patient]</code>.</p>"
            )
            self.todo_box.children = []
            self.todo_status.value = ""
            self.transcript.value = ""
            return

        def _list(title: str, quotes, empty: str) -> str:
            if not quotes:
                return f"<h4>{title}</h4><p class='small'>{empty}</p>"
            items = "".join(
                f"<li>{html.escape(q.text)} <span class='small'>({html.escape(q.speaker)})</span></li>" for q in quotes
            )
            return f"<h4>{title}</h4><ul>{items}</ul>"

        warning_class = "notice" if visit.warning_signs else "notice info"
        self.visit_summary.value = wrap(
            "<h3>What to remember</h3><p class='small'>Sentences quoted word for word from the transcript.</p>"
            f"<div class='{warning_class}'>"
            + _list(
                "⚠ When to get help",
                visit.warning_signs,
                "No warning signs were mentioned. Consider asking which symptoms should make you call.",
            )
            + "</div>"
            + _list("Questions you asked", visit.patient_questions, "No questions from the patient were found.")
        )
        rows = []
        for quote in visit.instructions:
            check = W.Checkbox(value=False, indent=False, layout=W.Layout(width="28px"))
            check.observe(lambda _: self._update_todo_status(), names="value")
            self._todo_checks.append(check)
            rows.append(_row(check, quote.text))
        self.todo_box.children = rows or [
            W.HTML(wrap("<p class='small'>No instructions were found in this conversation.</p>"))
        ]
        self._update_todo_status()
        self.speaker_filter.value = "everyone"
        self.transcript_search.value = ""
        self._render_transcript()

    def _update_todo_status(self) -> None:
        if not self._todo_checks:
            self.todo_status.value = ""
            return
        done = sum(check.value for check in self._todo_checks)
        total = len(self._todo_checks)
        message = "All done." if done == total else f"{done} of {total} done."
        self.todo_status.value = wrap(f"<p class='small'>{message}</p>")

    def _render_transcript(self) -> None:
        if self.analysis is None or not self.analysis.turns:
            self.transcript.value = ""
            return
        self.transcript.value = transcript_html(
            self.analysis.turns,
            self.analysis.doc_type,
            SPEAKER_ROLES[self.speaker_filter.value],
            self.transcript_search.value,
        )

    def _on_recall(self, _button=None) -> None:
        if self.analysis is None or self.analysis.visit is None:
            return
        quotes = self.analysis.visit.instructions + self.analysis.visit.warning_signs
        if not self.recall_text.value.strip():
            self.recall_result.value = wrap("<p class='small'>Write what you remember first.</p>")
            return
        items = recall_check(self.recall_text.value, quotes)
        rows = []
        for item in items:
            if item.remembered:
                rows.append(f"<li>✓ {html.escape(item.quote.text)}</li>")
            else:
                rows.append(f"<li><b>You may want to re-read:</b> {html.escape(item.quote.text)}</li>")
        remembered = sum(item.remembered for item in items)
        self.recall_result.value = wrap(
            f"<p>You covered {remembered} of {len(items)} things that were said. Different words can mean the same thing, "
            f"so treat this as a reminder, not a score.</p><ul>{''.join(rows)}</ul>"
        )

    # ================================================================== check my understanding
    def _render_check(self) -> None:
        if self.analysis is None:
            return
        questions = build_check_questions(self.analysis)
        self._check_questions = questions
        self._check_widgets = []
        if not questions:
            self.check_intro.value = wrap(
                "<p>There is nothing to quiz on in this document: it has no findings or lab results from the glossary. "
                "For a conversation, try <b>Explain it back</b> in the Conversation tab.</p>"
            )
            self.check_box.children = []
            self.check_score.value = ""
            self.check_reset.layout.display = "none"
            return
        self.check_intro.value = wrap(
            "<h3>Check my understanding</h3><p class='small'>A few questions answered from your document. "
            "Getting one wrong is useful: it shows exactly which part to read again or ask about.</p>"
        )
        blocks = []
        for number, question in enumerate(questions, start=1):
            radio = W.RadioButtons(options=list(question.options), value=None, layout=W.Layout(width="auto"))
            feedback = W.HTML()
            radio.observe(lambda change, q=question, f=feedback: self._on_answer(q, f, change["new"]), names="value")
            self._check_widgets.append((radio, feedback))
            blocks.append(W.VBox([W.HTML(wrap(f"<b>{number}. {html.escape(question.prompt)}</b>")), radio, feedback]))
        self.check_box.children = blocks
        self.check_reset.layout.display = None
        self._update_score()

    def _on_answer(self, question, feedback: W.HTML, chosen: str | None) -> None:
        feedback.value = check_feedback_html(question, chosen)
        self._update_score()

    def _update_score(self) -> None:
        answered = [
            (radio.value, q)
            for (radio, _), q in zip(self._check_widgets, self._check_questions, strict=True)
            if radio.value is not None
        ]
        if not answered:
            self.check_score.value = wrap(f"<p class='small'>0 of {len(self._check_widgets)} answered.</p>")
            return
        right = sum(chosen == q.answer for chosen, q in answered)
        self.check_score.value = wrap(
            f"<p><b>{right} of {len(answered)} right</b> ({len(answered)} of {len(self._check_widgets)} answered).</p>"
        )

    # ================================================================== questions
    def _load_questions(self) -> None:
        assert self.analysis is not None
        self._custom_questions = []
        self._rebuild_question_rows([(text, True) for text in self.analysis.questions])

    def _rebuild_question_rows(self, items: list[tuple[str, bool]]) -> None:
        self._question_rows = []
        rows = []
        for text, keep in items:
            check = W.Checkbox(value=keep, indent=False, layout=W.Layout(width="28px"))
            check.observe(lambda _: self._update_final_questions(), names="value")
            self._question_rows.append((check, text))
            rows.append(_row(check, text))
        self.question_box.children = rows
        self._update_final_questions()

    def _on_add_question(self, _button=None) -> None:
        text = self.own_question.value.strip()
        if not text:
            return
        if not text.endswith("?"):
            text += "?"
        current = [(t, check.value) for check, t in self._question_rows]
        self._rebuild_question_rows(current + [(text, True)])
        self.own_question.value = ""

    def selected_questions(self) -> list[str]:
        return [text for check, text in self._question_rows if check.value]

    def _update_final_questions(self) -> None:
        self.final_questions.value = "\n".join(f"{n}. {q}" for n, q in enumerate(self.selected_questions(), start=1))

    def _on_save(self, _button=None) -> None:
        if self.analysis is None:
            return
        folder = Path(self.save_folder.value.strip()).expanduser()
        if not folder.is_dir():
            self.save_status.value = wrap(
                f"<div class='notice'>The folder {html.escape(str(folder))} does not exist.</div>"
            )
            return
        stamp = _dt.datetime.now().strftime("%Y-%m-%d_%H%M")
        written = []
        questions_path = folder / f"my_questions_{stamp}.txt"
        # newline="" so Windows does not double the line endings (ground rules, section 9).
        with open(questions_path, "w", encoding="utf-8", newline="") as handle:
            handle.write("Questions for my care team\n\n" + self.final_questions.value + "\n")
        written.append(questions_path)
        if self.save_report_too.value:
            report_path = folder / f"my_explanation_{stamp}.html"
            with open(report_path, "w", encoding="utf-8", newline="") as handle:
                handle.write(
                    "<!doctype html><meta charset='utf-8'><title>My explanation</title>"
                    + full_report_html(self.analysis)
                )
            written.append(report_path)
        names = "".join(f"<li><code>{html.escape(str(path))}</code></li>" for path in written)
        self.save_status.value = wrap(
            f"<div class='notice calm'>Saved:<ul>{names}</ul>These files contain your health information; keep them somewhere private.</div>"
        )

    # ================================================================== Claude
    def _reset_claude(self) -> None:
        self.explainer = None
        self.claude_output.value = ""
        self.followup.disabled = True
        self.ask_button.disabled = True
        self._invalidate_preview()

    def _invalidate_preview(self, _change=None) -> None:
        # Consent applies to the exact text that was previewed; any change revokes it.
        self._previewed_text = None
        self.preview.value = ""
        self.consent.value = False
        self.consent.disabled = True
        self.claude_button.disabled = True

    def _on_preview(self, _button=None) -> None:
        if self.analysis is None:
            self._set_status("Press Explain first.", "error")
            return
        extra = [word for word in self.hide_words.value.split(",") if word.strip()]
        redaction = redact(self.analysis.text, extra)
        self._previewed_text = redaction.text
        summary = ", ".join(f"{count} {name}" for name, count in sorted(redaction.counts.items())) or "nothing matched"
        self.preview.value = wrap(
            f"<p class='small'>Hidden: {html.escape(summary)}. This is exactly what would be sent:</p>"
            f"<div class='doc' style='max-height:320px;overflow:auto'>{html.escape(redaction.text)}</div>"
        )
        self.consent.disabled = False
        self.consent.value = False

    def _on_consent(self, change) -> None:
        self.claude_button.disabled = not (change["new"] and self._previewed_text is not None)

    def _stream_into_output(self, prefix_html: str) -> Callable[[str], None]:
        buffer: list[str] = []
        last_update = [0.0]

        def on_text(chunk: str) -> None:
            buffer.append(chunk)
            now = time.monotonic()
            # Re-render at most a few times a second; each update is a message to the front end.
            if now - last_update[0] > 0.25:
                last_update[0] = now
                self.claude_output.value = prefix_html + wrap(f"<div class='doc'>{html.escape(''.join(buffer))}</div>")

        return on_text

    def _show_reply(self, prefix_html: str, reply: ClaudeReply) -> str:
        notes = []
        if reply.refused:
            notes.append("Claude declined to answer this request. Try rephrasing, or ask your care team.")
        if reply.truncated:
            notes.append("The answer was cut off because it reached the length limit.")
        if reply.served_by_fallback:
            notes.append(f"Answered by the fallback model {reply.model}.")
        note_html = "".join(f"<div class='notice small'>{html.escape(note)}</div>" for note in notes)
        footer = (
            f"<p class='small'>Model: {html.escape(reply.model)} · {reply.input_tokens} input / {reply.output_tokens} output tokens. "
            "AI can make mistakes; check anything important with your care team.</p>"
        )
        block = wrap(_markdown_to_html(reply.text) + note_html + footer)
        self.claude_output.value = prefix_html + block
        return prefix_html + block

    def _on_claude(self, _button=None) -> None:
        if self.analysis is None or self._previewed_text is None or not self.consent.value:
            self._set_status("Preview the text and tick the consent box first.", "error")
            return
        try:
            settings = ExplainSettings(self.reading_level.value, self.language.value)
            client = self.client_factory()
        except Exception as error:  # surfaced to the reader, never swallowed
            self.claude_output.value = wrap(f"<div class='notice'>{html.escape(_describe_api_error(error))}</div>")
            return
        self.explainer = ClaudeExplainer(client, self._previewed_text, self.analysis.doc_type, settings)
        self.claude_button.disabled = True
        self.claude_output.value = wrap("<p class='small'>Asking Claude…</p>")
        try:
            reply = self.explainer.explain(on_text=self._stream_into_output(""))
        except Exception as error:
            self.claude_output.value = wrap(f"<div class='notice'>{html.escape(_describe_api_error(error))}</div>")
            self.claude_button.disabled = False
            return
        self._transcript_html = self._show_reply("", reply)
        self.claude_button.disabled = False
        self.followup.disabled = reply.refused
        self.ask_button.disabled = reply.refused

    def _on_ask(self, _widget=None) -> None:
        if self.explainer is None or not self.followup.value.strip():
            return
        question = self.followup.value.strip()
        self.followup.value = ""
        prefix = self._transcript_html + wrap(
            f"<div class='bubble patient'><div class='who'>You</div>{html.escape(question)}</div>"
        )
        self.ask_button.disabled = True
        try:
            reply = self.explainer.ask(question, on_text=self._stream_into_output(prefix))
        except Exception as error:
            self.claude_output.value = prefix + wrap(
                f"<div class='notice'>{html.escape(_describe_api_error(error))}</div>"
            )
            self.ask_button.disabled = False
            return
        self._transcript_html = self._show_reply(prefix, reply)
        self.ask_button.disabled = False


def launch(client_factory: Callable[[], object] | None = None) -> ExplainerApp:
    """Build the app and display it in the current notebook cell."""
    from IPython.display import display

    app = ExplainerApp(client_factory)
    display(app.widget)
    return app


def word_lookup() -> W.VBox:
    """A stand-alone 'look up any medical word' box, usable without a document."""
    from IPython.display import display

    box = W.Combobox(
        placeholder="Type a medical word, e.g. 'nodule', 'HbA1c', 'prn'",
        options=all_spellings(),
        ensure_option=False,
        layout=W.Layout(width="420px"),
    )
    result = W.HTML()
    box.observe(
        lambda change: setattr(result, "value", lookup_html(change["new"] or "", lookup(change["new"] or ""))),
        names="value",
    )
    widget = W.VBox([W.HTML(CSS), box, result])
    display(widget)
    return widget
