"""Built-in examples for trying the notebook.

All four are SYNTHETIC. They were written for this project, describe no real person,
and contain made-up identifiers so that the redaction step has something to remove.
Their style follows public examples: MIMIC-CXR-style radiology sections, TCGA-style
pathology sections and MTS-Dialog-style ("Doctor:" / "Patient:") transcripts.
"""

from __future__ import annotations

from dataclasses import dataclass

from .detect import DocType


@dataclass(frozen=True)
class Sample:
    key: str
    title: str
    doc_type: DocType
    text: str


CHEST_XRAY = Sample(
    "chest_xray",
    "Chest X-ray report (synthetic)",
    DocType.RADIOLOGY,
    """\
Patient Name: Alex Sample
MRN: 00987654
Date of exam: 03/14/2026

EXAMINATION: Chest radiographs, PA and lateral views.

INDICATION: 58-year-old with cough for 3 weeks. Evaluate for pneumonia.

COMPARISON: Chest radiograph from 09/02/2024.

FINDINGS:
The cardiomediastinal silhouette is within normal limits. There is patchy opacity in
the right lower lobe, which may represent pneumonia. Small right pleural effusion.
No pneumothorax. A 6 mm nodule is seen in the left upper lobe, not present on the
prior study. Mild degenerative changes of the thoracic spine.

IMPRESSION:
1. Right lower lobe opacity, likely pneumonia in the appropriate clinical setting.
2. Small right pleural effusion.
3. New 6 mm left upper lobe nodule. Malignancy cannot be excluded.

RECOMMENDATION: Follow-up chest CT in 3 months to reassess the nodule after treatment.

Electronically signed by: Dr. Robin Example
""",
)

COLON_PATHOLOGY = Sample(
    "colon_pathology",
    "Colon polyp pathology report (synthetic)",
    DocType.PATHOLOGY,
    """\
Patient Name: Jordan Sample
Accession: S26-004512
Collected: 02/10/2026

SPECIMEN: Colon, sigmoid, polyp, biopsy.

GROSS DESCRIPTION:
Received in formalin labeled with the patient's name is a single tan polypoid
fragment of tissue measuring 0.8 x 0.5 x 0.4 cm. Entirely submitted in one cassette.

MICROSCOPIC DESCRIPTION:
Sections show a tubular adenoma with low-grade dysplasia. No high-grade dysplasia
is identified. No invasive carcinoma is seen. The margins are free of adenoma.

FINAL DIAGNOSIS:
Sigmoid colon polyp, biopsy: Tubular adenoma. Negative for high-grade dysplasia and
malignancy.

COMMENT: Surveillance colonoscopy interval per gastroenterology guidelines.
""",
)

BLOOD_TESTS = Sample(
    "blood_tests",
    "Blood test results (synthetic)",
    DocType.LAB,
    """\
Patient Name: Sam Sample        DOB: 01/22/1971
Collected: 04/02/2026 08:15

COMPLETE BLOOD COUNT (CBC)
Test                 Result   Units       Reference Range   Flag
WBC                  7.2      x10^3/uL    4.0-11.0
Hemoglobin           10.9     g/dL        12.0-15.5         L
Hematocrit           33.1     %           36.0-46.0         L
MCV                  76       fL          80-100            L
Platelets            250      x10^3/uL    150-400

BASIC METABOLIC PANEL (BMP)
Sodium               139      mmol/L      136-145
Potassium            4.1      mmol/L      3.5-5.1
Glucose              132      mg/dL       70-99             H
Creatinine           0.9      mg/dL       0.6-1.1
eGFR                 >60      mL/min/1.73m2   >60

LIPID PANEL
LDL Cholesterol      162      mg/dL       <100              H
HDL Cholesterol      48       mg/dL       >40
""",
)

CLINIC_VISIT = Sample(
    "clinic_visit",
    "Doctor-patient conversation (synthetic)",
    DocType.CONVERSATION,
    """\
Doctor: Good morning. What brings you in today?
Patient: I've been getting headaches in the morning, and the pharmacy machine said my blood pressure was high.
Doctor: How high was it?
Patient: It said 152 over 96.
Doctor: Today it's 148 over 94 here as well. Any chest pain, shortness of breath, or vision changes?
Patient: No, nothing like that. Just the headaches.
Doctor: Okay. With two high readings, this looks like hypertension, which means high blood pressure.
Patient: Is that serious? Do I have to take pills forever?
Doctor: It's very common and treatable. I'd like to start you on lisinopril 10 mg once a day, in the morning.
Doctor: I also want you to cut back on salt and try to walk for 30 minutes most days.
Doctor: We'll check your kidney function and potassium with a blood test in two weeks.
Patient: Are there side effects I should watch for?
Doctor: Some people get a dry cough. If you notice swelling of your lips, tongue, or face, stop the medicine and go to the emergency room right away.
Doctor: Please keep a log of your home blood pressure readings and come back in four weeks.
Patient: Okay, thank you.
""",
)

SAMPLES: dict[str, Sample] = {sample.key: sample for sample in (CHEST_XRAY, COLON_PATHOLOGY, BLOOD_TESTS, CLINIC_VISIT)}
