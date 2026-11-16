"""Generate notebooks/patient_report_explainer.ipynb.

    conda activate medexplain
    python tools/build_notebook.py            # write the notebook (no outputs)
    python tools/build_notebook.py --execute  # also run it headlessly as a check

The notebook is build output. Edit this script, not the .ipynb, so the notebook
never drifts from the package (workspace CLAUDE.md, section 4).
"""

from __future__ import annotations

import argparse
import copy
from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "patient_report_explainer.ipynb"
KERNEL = {"name": "medexplain", "display_name": "Python (medexplain)", "language": "python"}

INTRO = """\
# Understand your medical report or visit

This notebook helps you read **your own** medical documents:

| You can upload | What you get |
|---|---|
| An imaging report (X-ray, CT, MRI, ultrasound) | The summary first, every term explained, what was *ruled out* |
| A pathology (biopsy) report | The diagnosis in plain words, cancer words checked for "no" / "negative for" |
| Lab results | Each number compared with the range printed on *your* report |
| A visit transcript ("Doctor: … / Patient: …") | Your instructions, warning signs and questions pulled out word for word |

Every tab ends in the same place: **a list of questions to bring to your care team.**

> **This is not medical advice.** It explains words and numbers; it does not diagnose,
> and it can miss things or get them wrong. If you feel unwell, contact your care team or
> your local emergency number. Do not wait for a tool.

**Privacy.** Everything runs on this computer. The optional *Ask Claude* tab sends text
to Anthropic only after you preview exactly what will be sent and tick a consent box.
"""

HOW_TO = """\
## How to use it

1. Run the cell below (**Shift+Enter**). If asked for a kernel, choose **Python (medexplain)**.
2. Choose **Upload a file** (.txt, .pdf with selectable text, .docx), **Paste text**, or
   **Try an example** (an example opens straight away).
3. Press **Explain**, then explore:

| Tab | Try this |
|---|---|
| Overview | See what kind of document it is, what is worth asking about, and what was **ruled out** |
| Read it with me | Step through the report one part at a time with **Next** / **Previous**, summary first |
| Words | Filter to *Worth asking*, *Not found* or *Possible*; click a word to see every sentence it is in. Look up any word in the box below |
| Numbers | See where each lab result sits against the range printed on your report; pick one for a plain explanation |
| Conversation | Tick off your to-do list, filter by speaker, search the transcript, and practise **Explain it back** |
| Check my understanding | Answer a few quick questions built from your document and get instant feedback |
| My questions | Untick, add your own, then copy or **Save** the list for your appointment |

Use the **Text size** slider at the top if the print is small.

Tip: patient portals usually let you copy report text. Photos and scanned PDFs cannot be read; paste the text instead.
"""

LOOKUP = """\
## Just want to look up a word?

Type any medical word or abbreviation (for example *atelectasis*, *HbA1c* or *prn*).
This works without a document.
"""

LOOKUP_CODE = """\
from medexplain.ui import word_lookup

word_lookup();
"""

SETUP = """\
# Make the package importable even if it was not pip-installed yet.
import sys
from pathlib import Path

try:
    import medexplain
except ImportError:
    sys.path.insert(0, str(Path.cwd().parent / "src"))
    import medexplain

from medexplain.ui import launch

app = launch()
"""

NO_WIDGETS = """\
## Without the interactive widgets

If the buttons above do not appear (some viewers cannot show widgets), put your text
between the triple quotes below and run the cell. You get the same explanation as one page.
"""

NO_WIDGETS_CODE = """\
from IPython.display import HTML, display

from medexplain import analyze_document
from medexplain.render import full_report_html
from medexplain.samples import SAMPLES

my_text = \"\"\"
\"\"\"

text = my_text if my_text.strip() else SAMPLES["chest_xray"].text  # falls back to a made-up example
display(HTML(full_report_html(analyze_document(text))))
"""

CLAUDE_SETUP = """\
## Optional: turning on *Ask Claude*

The *Ask Claude* tab uses Anthropic's API and needs an API key from
[console.anthropic.com](https://console.anthropic.com/). Set it **before** starting
Jupyter, so the key is never typed into the notebook:

```
setx ANTHROPIC_API_KEY "sk-ant-..."      (Windows; open a new terminal afterwards)
export ANTHROPIC_API_KEY="sk-ant-..."    (macOS / Linux)
```

What is sent: the redacted document text shown in the preview, your reading-level and
language choices, and any follow-up questions you type. Nothing else from this notebook.
"""

LIMITS = """\
## What this tool can and cannot do

- **It reads words, not images.** It never looks at X-ray or scan pictures.
- **Ranges come from your report.** A result is called high or low only against the
  range printed next to it; with no printed range it says so instead of guessing.
- **"No …" is understood, mostly.** Phrases such as "no pneumothorax" or "negative for
  malignancy" are recognised as *ruled out*. Unusual wording can still fool it.
- **The glossary is general.** A word's usual meaning is not necessarily what it means
  for you. Your care team knows your history.
- **Redaction is a safety net, not a guarantee.** Read the preview before sending.

The examples are made up. The project README lists public datasets of reports and
conversations for anyone who wants to test the tool more widely.
"""


def build() -> nbformat.NotebookNode:
    notebook = new_notebook()
    notebook.metadata["kernelspec"] = KERNEL
    notebook.metadata["language_info"] = {"name": "python"}
    notebook.cells = [
        new_markdown_cell(INTRO),
        new_markdown_cell(HOW_TO),
        new_code_cell(SETUP),
        new_markdown_cell(LOOKUP),
        new_code_cell(LOOKUP_CODE),
        new_markdown_cell(NO_WIDGETS),
        new_code_cell(NO_WIDGETS_CODE),
        new_markdown_cell(CLAUDE_SETUP),
        new_markdown_cell(LIMITS),
    ]
    return notebook


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run the notebook headlessly to check it works")
    parser.add_argument("--kernel", default=KERNEL["name"], help="kernel to execute with (default: %(default)s)")
    arguments = parser.parse_args()

    notebook = build()
    NOTEBOOK.parent.mkdir(parents=True, exist_ok=True)
    if arguments.execute:
        from nbclient import NotebookClient

        # Execute a copy so the saved notebook stays output-free (ground rules, section 4).
        executed = nbformat.from_dict(copy.deepcopy(notebook))
        NotebookClient(
            executed, timeout=120, kernel_name=arguments.kernel, resources={"metadata": {"path": str(NOTEBOOK.parent)}}
        ).execute()
        errors = [
            output
            for cell in executed.cells
            if cell.cell_type == "code"
            for output in cell.outputs
            if output.output_type == "error"
        ]
        if errors:
            raise SystemExit(f"notebook raised: {errors[0]['ename']}: {errors[0]['evalue']}")
        print(f"executed {sum(c.cell_type == 'code' for c in executed.cells)} code cells without errors")
    # newline="" so Windows does not rewrite the JSON's line endings.
    with open(NOTEBOOK, "w", encoding="utf-8", newline="") as handle:
        nbformat.write(notebook, handle)
    print(f"wrote {NOTEBOOK.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
