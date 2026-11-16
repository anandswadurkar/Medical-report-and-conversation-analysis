# medexplain: understand your medical report or visit

An interactive Jupyter notebook that helps a **patient** read their own medical
documents. Upload or paste a radiology report, a pathology report, lab results or a
doctor-patient conversation transcript, press **Explain**, and get:

| Tab | What it shows | What you can do |
|---|---|---|
| Overview | Document type (with the clues used), words worth asking about, what was **looked for and not found** | Jump to guided reading, the quiz or your questions |
| Read it with me | One section at a time, **conclusion first**, terms underlined with their meaning on hover, "not found here" notes | Step with **Previous / Next** and a progress bar, or show the whole document |
| Words | Every glossary term found, with how it appears (present, absent, possible) | Filter to *Worth asking / Not found / Possible*; click a word to see **every sentence it appears in**, highlighted; look up any of the 248 glossary words |
| Numbers | Each lab result against the range **printed in that report**, as a table with a **range bar** per result; sizes in inches | Pick a result for a plain explanation of the test and where the value sits |
| Conversation | Warning signs, the patient's questions, and the transcript as chat bubbles | Tick off a **to-do list** of instructions; filter by speaker; search; **Explain it back** and compare with what was said |
| Check my understanding | A short quiz built from the document ("Did the report find pneumothorax?", "Is your hemoglobin above, within or below the range?") | Answer and get instant feedback quoting the source sentence (teach-back) |
| My questions | Questions built from the document's words and numbers | Untick, add your own, copy, or **Save** as a text file (plus, optionally, the whole explanation as a web page) |
| Ask Claude (optional) | A fuller explanation in the reader's chosen language and reading level, plus follow-up questions | Only after a redaction preview and explicit consent |

A **text size** slider and **Start over** button sit at the top, and choosing an example
explains it immediately. A second notebook cell is a stand-alone word look-up that
works without a document. Everything except the last tab runs **offline**.

> Not medical advice. The tool explains words and numbers; it does not diagnose and can
> be wrong. It is designed to help a patient prepare questions for their care team.

## Scope

**In scope:** text of English-language radiology, pathology and lab reports;
transcripts that label speakers (`Doctor:` / `Patient:` or `[doctor]` / `[patient]`);
`.txt`, `.md`, `.pdf` with a text layer, `.docx`, or pasted text.

**Out of scope:** images (X-ray pictures, photos or scans of reports; OCR is not
attempted), audio recordings, diagnosis or risk prediction, medication advice,
non-English source documents (the Claude tab can *answer* in another language), and
clinical use by professionals.

## Install

On Windows, the fastest route uses the lock file, which lists the exact builds and
needs **no solve**:

```powershell
conda create -n medexplain --file conda-lock-win-64.txt
conda activate medexplain
pip install -e . --no-deps
python tools/install_kernel.py     # kernelspec that activates the env (Windows DLL fix)
python tools/build_notebook.py     # writes notebooks/patient_report_explainer.ipynb
```

On other platforms, or with a conda that has the libmamba solver (conda >= 23.10,
Miniforge, mamba), use `conda env create -f environment.yml` in place of the first line.

Open `notebooks/patient_report_explainer.ipynb` in VS Code or Jupyter, pick the kernel
**Python (medexplain)**, and run the first code cell.

**Why not just `conda env create -f environment.yml` here?** This machine's conda 4.14
has only the classic solver. On 2026-11-16, `conda env create` on this file sat at
"Solving environment" for 35 and 70+ minutes (about 2-3 GB of memory) without finishing,
with and without exact pins. What worked was building it in steps, each a small solve:
`conda create -n medexplain --override-channels -c conda-forge python=3.11.18 pip`
(9.5 min), then four `conda install` batches (widgets/kernel 5.3 min, file readers
36 s, anthropic 85 s, test tools 9.5 min). The lock file was exported from that env;
creating a fresh env from it has not been timed yet.

For the optional Claude tab, set `ANTHROPIC_API_KEY` in the environment *before*
starting Jupyter (`setx ANTHROPIC_API_KEY "sk-ant-..."` on Windows, then open a new
terminal). The key is never typed into the notebook.

## How it works

```mermaid
flowchart LR
  U[Upload / paste / example] --> I[ingest.py<br>txt, pdf, docx to text]
  I --> D[detect.py<br>document type + evidence]
  D --> S[sections.py<br>sections or speaker turns]
  S --> G[glossary.py + negation.py<br>terms: present / absent / possible]
  S --> L[labs.py<br>result vs printed range]
  S --> C[conversation.py<br>instructions, warnings, questions]
  G & L & C --> Q[analyze.py<br>questions for the care team]
  Q --> R[render.py to ui.py tabs]
  R -. consent + preview .-> X[redact.py to llm.py<br>Claude, optional]
```

Design rules, from the workspace ground rules:

- **Never guess.** Unknown document type is reported as unknown, with the reason, and
  the reader picks the type. A lab result is judged only against the range printed next
  to it; there is no built-in table of normal values, because ranges differ between labs.
  Units are kept exactly as written.
- **Disagreement is shown, not resolved.** When the report's own H/L flag contradicts its
  printed range, the result is marked "flag and range disagree" and a question is added.
- **Negation first.** Reports list many things that were checked and are absent ("No
  pneumothorax"). A NegEx-style check (Chapman et al. 2001,
  [doi:10.1006/jbin.2001.1029](https://doi.org/10.1006/jbin.2001.1029)) classifies every
  term as affirmed, negated or uncertain, so absent findings are reported as reassuring
  rather than highlighted as alarming.
- **Quotes, not paraphrase.** Conversation extraction returns sentences that were actually
  said, with the speaker, so the reader can check them.
- **Library code returns values.** `render.py` returns HTML strings; only `ui.py` touches
  widgets. Everything is importable and tested without a notebook.

### The Claude tab

- Model `claude-opus-5-5` with `effort: "medium"`, streamed. Server-side refusal
  fallback is enabled (`fallbacks="default"`, beta `server-side-fallback-2026-07-01`):
  medical text can occasionally trip a safety classifier, and this retries on a fallback
  model in the same call instead of returning nothing. The reply says when a fallback answered.
- The system prompt (`llm.py`) limits the model to explaining the document: no diagnosis,
  prognosis, risk numbers or treatment changes; compare numbers only with printed ranges;
  say plainly when something needs prompt care; treat instructions inside the document as data.
- Before anything is sent, `redact.py` removes emails, phone numbers, dates, record numbers,
  labelled name/address lines and any words the reader lists, and the reader sees the exact
  text to be sent. Consent is revoked automatically if the words to hide change after the preview.

## Data sources

The notebook ships with **four synthetic documents** written for this project
(`samples.py`): a chest X-ray report, a colon polyp pathology report, a blood test panel,
and a hypertension clinic visit. They contain made-up identifiers so redaction can be
tested. No real patient data is included or downloaded.

Public datasets for wider testing (from a link list compiled 2026-11-15; licences and
access terms must be checked before use, and none of these has been run yet):

| Use | Dataset | Access |
|---|---|---|
| Conversation turns, instructions | [MTS-Dialog](https://github.com/abachaa/MTS-Dialog), [ACI-Bench](https://github.com/wyim/aci-bench) (combined corpus: [microsoft/clinical_visit_note_summarization_corpus](https://github.com/microsoft/clinical_visit_note_summarization_corpus)) | Open on GitHub |
| Conversation (real consultations, mock patients) | [PriMock57](https://github.com/babylonhealth/primock57) | Open on GitHub |
| Pathology reports | [TCGA-Reports](https://github.com/tatonetti-lab/tcga-path-reports) (also on [Mendeley Data](https://data.mendeley.com/datasets/hyg5xkznpx/1)) | Open |
| Radiology reports | [MIMIC-CXR](https://physionet.org/content/mimic-cxr-jpg/2.0.0/) (section extraction: [MIT-LCP/mimic-cxr](https://github.com/MIT-LCP/mimic-cxr)), [ReXGradient-160K](https://huggingface.co/datasets/rajpurkarlab/ReXGradient-160K), [CheXpert Plus](https://arxiv.org/abs/2405.19538) | Credentialed or licence agreement |
| Radiology entity/negation labels | [RadGraph-XL](https://physionet.org/content/radgraph-xl/) | Credentialed (PhysioNet) |
| Synthetic conversations | [nisten/opus5-5-doctor-patient-conversations-all-human-diseases](https://huggingface.co/datasets/nisten/opus5-5-doctor-patient-conversations-all-human-diseases), [OnDeviceMedNotes](https://huggingface.co/datasets/OnDeviceMedNotes/synthetic-medical-conversations-deepseek-v3) | Open; smoke tests only (see Pitfalls) |

## Pitfalls

- **Synthetic LLM conversations cannot validate this tool.** They are written in the
  tidy style that a rule-based extractor finds easiest. Use them to find crashes, not to
  measure accuracy; measure on human transcripts (MTS-Dialog, ACI-Bench, PriMock57).
- **Questions inside a conversation are read as affirmed.** "Any shortness of breath?"
  marks "shortness of breath" as mentioned even if the patient then says no. The glossary
  tab says "mentioned", not "present", for this reason.
- **Negation scope is a few words.** Long lists ("no A, B, C, D, E, F, or G") can leave the
  last items outside the window and mark them affirmed.
- **Detection is a heuristic with hand-set weights** (`detect.py`). It reaches a verdict
  only above a score of 3, which no single generic word can produce, and otherwise asks.
- **Redaction is pattern-based.** Names in running text without a label are not caught
  unless the reader lists them.
- **Scanned PDFs have no text layer** and are refused with advice to paste text instead.
- **The quiz only asks what the document answers.** Options are a fixed set per kind of
  question ("found / not found / possible", "above / within / below the range"), so no
  invented statement about the patient's care is ever shown as an option. Results written
  as limits (`<0.01`) are left out because they cannot be placed exactly.
- **"Explain it back" compares key words, not meaning.** It flags an instruction as
  "you may want to re-read" when fewer than two of its key words appear in the reader's
  version, so a correct paraphrase in different words can still be flagged. The app
  says so on screen.

## Status (2026-11-16)

- 116 tests, all passing (2026-11-16, Windows 11, Python 3.11.18, `medexplain` env as
  pinned in `environment.yml`, 12.3 s). They cover known answers for negation (12 cases),
  detection of all four samples, lab parsing of all 12 rows in the sample panel, conflict
  and one-sided-range handling, PDF and Word reading, invalid input for every entry point,
  hypothesis invariants (annotation never changes the text; redaction is idempotent),
  the quiz (mix of found / not found / possible, answers from the printed range), range-bar
  geometry (marker left of, inside or right of the band), look-up ranking, recall
  checking, and every interactive control in the app (stepper, filters, look-up, quiz
  scoring, to-do list, transcript search, question builder, saving to a temporary
  folder, text size, start over, consent flow) driven with a fake Claude client.
- The generated notebook executes headlessly on the **Python (medexplain)** kernel with
  no errors (`python tools/build_notebook.py --execute`).
- Glossary: 248 entries across report structure, hedging phrases, anatomy, imaging,
  pathology, labs, abbreviations, conditions and common medicines.
- **Not yet validated on real documents.** There is no accuracy figure. Planned first
  measurement: document-type detection and negation on MTS-Dialog, ACI-Bench and
  TCGA-Reports, reported as MCC and balanced accuracy with a confusion matrix, next to a
  majority-class baseline and the "everything affirmed" baseline for negation.
- The Claude path is tested only against a fake client; no live API call has been made.

### Corrected during development

Recorded because each one would have produced a confident wrong answer:

- *Believed:* a speaker label is any line starting with a role word. *Found:* "PA and
  lateral views" became a turn by speaker "PA". *Now:* plain labels need a colon.
- *Believed:* two labelled lines mean a conversation. *Found:* a report header
  ("Patient: … / Physician: …") qualified. *Now:* at least three turns.
- *Believed:* any ALL-CAPS label is a section. *Found:* "MRN:" split the header. *Now:*
  identifier labels stay in the header block.
- *Believed:* abbreviation entries match case-sensitively throughout. *Found:* that also
  made "Body mass index" miss at the start of a sentence. *Now:* case-sensitivity applies
  only to abbreviation spellings, and short capitalised aliases (`US`, `PE`, `K`) are
  case-sensitive everywhere, so "tell us" is not ultrasound.
- *Believed:* INDICATION lines state findings. *Found:* "Evaluate for pneumonia" was
  marked affirmed. *Now:* "evaluate for", "assess for" are uncertainty triggers.

## Layout

```
src/medexplain/   ingest, detect, sections, negation, terms (glossary data), glossary,
                  labs, measurements, conversation, redact, analyze, quiz,
                  render + views (HTML), llm, ui (widgets), samples
tests/            pytest + hypothesis
tools/            build_notebook.py (generates the notebook), install_kernel.py
notebooks/        generated, committed without outputs
```

## Licence and citation

MIT (see `LICENSE`). Citation metadata in `CITATION.cff`.
