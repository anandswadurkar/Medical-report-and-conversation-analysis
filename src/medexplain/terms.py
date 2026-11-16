"""Curated plain-language glossary.

Each entry is written for a reader with no medical training, at roughly a
6th-to-8th-grade reading level. Definitions were written for this project and
checked against MedlinePlus (https://medlineplus.gov/), the U.S. National Library
of Medicine's consumer health resource, and RadiologyInfo.org
(https://www.radiologyinfo.org/). They describe what a word *usually* means; they
never say what it means for a particular patient.

Fields
------
term
    Canonical spelling shown to the reader.
definition
    Plain-language meaning.
category
    One of ``CATEGORIES``.
aliases
    Other spellings matched in the text.
case_sensitive
    True for short abbreviations, where matching ``"ER"`` case-insensitively would
    also hit ordinary words.
concern
    True when an affirmed mention is something a care team usually discusses with
    the patient directly (cancer words, clots, bleeding, collapsed lung). It drives
    the "talk to your care team" notice, never a diagnosis.
doc_types
    When non-empty, the entry applies only to these document types. Used for
    abbreviations whose meaning depends on context (``ER`` is "estrogen receptor"
    in pathology and "emergency room" elsewhere).
"""

from __future__ import annotations

from dataclasses import dataclass, field

CATEGORIES = (
    "report structure",
    "hedging phrase",
    "anatomy and direction",
    "imaging finding",
    "imaging test",
    "pathology",
    "lab test",
    "abbreviation",
    "condition",
    "medication",
)


@dataclass(frozen=True)
class Term:
    term: str
    definition: str
    category: str
    aliases: tuple[str, ...] = ()
    case_sensitive: bool = False
    concern: bool = False
    doc_types: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f"unknown category {self.category!r} for term {self.term!r}")
        if not self.definition.strip():
            raise ValueError(f"term {self.term!r} has an empty definition")


def _t(term: str, definition: str, category: str, *aliases: str, cs: bool = False, concern: bool = False, only: tuple[str, ...] = ()) -> Term:
    return Term(term, definition, category, tuple(aliases), cs, concern, only)


# Single-letter aliases keep the 248 table rows short enough to scan.
S, H, A, I, M, P, L, B, C, D = (  # noqa: E741
    "report structure",
    "hedging phrase",
    "anatomy and direction",
    "imaging finding",
    "imaging test",
    "pathology",
    "lab test",
    "abbreviation",
    "condition",
    "medication",
)

GLOSSARY: tuple[Term, ...] = (
    # --- report structure -------------------------------------------------------
    _t("impression", "The radiologist's summary and conclusion. It is usually the most important part of an imaging report, so many people read it first.", S, "conclusion"),
    _t("findings", "The detailed list of what was seen, organ by organ or area by area.", S),
    _t("indication", "Why the test was ordered, for example a symptom such as cough or pain.", S, "clinical history", "clinical indication", "reason for exam"),
    _t("comparison", "Earlier scans the radiologist looked at to see whether anything has changed.", S),
    _t("technique", "How the test was done, such as which views were taken or whether contrast dye was used.", S),
    _t("addendum", "A note added after the report was first finished, often with a correction or extra information.", S),
    _t("gross description", "What the specimen looked like to the naked eye (size, color, weight) before it was examined under a microscope.", S),
    _t("microscopic description", "What the pathologist saw when looking at thin slices of the tissue under a microscope.", S),
    _t("final diagnosis", "The pathologist's conclusion about what the tissue shows. In a pathology report this is the main result.", S),
    _t("specimen", "The piece of tissue or fluid that was sent to the lab.", S),
    _t("reference range", "The range of results seen in most healthy people, as used by the lab that ran your test. Ranges differ between labs.", S, "ref range", "normal range"),
    # --- hedging phrases ----------------------------------------------------------
    _t("unremarkable", "Normal; nothing worth pointing out.", H),
    _t("within normal limits", "Normal for this test.", H, "WNL"),
    _t("no acute", "Nothing new or urgent was seen. Older or long-standing findings may still be described.", H),
    _t("suspicious for", "The doctor is raising a possibility that needs to be checked. It is not a final diagnosis.", H),
    _t("consistent with", "The findings match a particular explanation.", H, "compatible with"),
    _t("cannot be excluded", "The test cannot rule this possibility out. Your doctor may want another test to be sure.", H, "cannot be ruled out", "not excluded"),
    _t("clinical correlation", "The writer is asking your doctor to compare this result with your symptoms, exam and other tests before drawing conclusions.", H, "correlate clinically", "clinical correlation is recommended"),
    _t("incidental", "Found by chance, not related to the reason the test was ordered.", H, "incidentally"),
    _t("likely", "Probable, but not certain.", H, "most likely", "probable"),
    _t("nonspecific", "Could have several different causes; the finding alone does not point to one.", H, "non-specific"),
    _t("stable", "Unchanged compared with an earlier test. This is usually reassuring.", H),
    _t("interval", "Over the time since the previous test (for example, 'interval improvement' means it got better since last time).", H),
    # --- anatomy and direction ----------------------------------------------------
    _t("bilateral", "On both sides of the body.", A),
    _t("unilateral", "On one side of the body only.", A),
    _t("anterior", "Toward the front of the body.", A),
    _t("posterior", "Toward the back of the body.", A),
    _t("lateral", "Toward the side, away from the middle of the body. In a chest X-ray, a 'lateral view' is a picture taken from the side.", A),
    _t("medial", "Toward the middle of the body.", A),
    _t("proximal", "Closer to the center of the body or to where a limb attaches.", A),
    _t("distal", "Farther from the center of the body or from where a limb attaches.", A),
    _t("superior", "Above, or toward the head.", A),
    _t("inferior", "Below, or toward the feet.", A),
    _t("hilar", "Near the hilum, the area where the airways and blood vessels enter each lung.", A, "hilum", "hila"),
    _t("mediastinum", "The space in the middle of the chest between the lungs. It holds the heart, large blood vessels, windpipe and lymph nodes.", A, "mediastinal"),
    _t("costophrenic angle", "The bottom corner of each lung on a chest X-ray, where fluid tends to collect first.", A, "costophrenic angles"),
    _t("parenchyma", "The main working tissue of an organ (for example, lung parenchyma).", A, "parenchymal"),
    _t("cardiomediastinal silhouette", "The outline of the heart and the middle of the chest on an X-ray.", A),
    _t("pleura", "The thin lining around the lungs and inside the chest wall.", A, "pleural"),
    _t("lobe", "A section of an organ. The right lung has three lobes and the left lung has two.", A, "lobes"),
    # --- imaging findings -------------------------------------------------------
    _t("opacity", "An area that looks whiter or denser than expected on an X-ray or CT. Fluid, infection, scarring and other causes can all do this.", I, "opacities", "opacification"),
    _t("consolidation", "Part of the lung is filled with fluid or other material instead of air. Pneumonia is a common cause.", I),
    _t("atelectasis", "Part of the lung is not fully inflated. Small areas are common, for example after surgery or with shallow breathing.", I, "atelectatic", "subsegmental atelectasis"),
    _t("pleural effusion", "Extra fluid between the lung and the chest wall.", I, "effusion", "effusions", "pleural effusions"),
    _t("pneumothorax", "Air has leaked into the space between the lung and the chest wall, which can make the lung collapse.", I, concern=True),
    _t("cardiomegaly", "The heart looks larger than usual on the image.", I, "enlarged heart"),
    _t("nodule", "A small, round spot. Most nodules are harmless, but some need a follow-up scan to check that they do not grow.", I, "nodules", "nodular"),
    _t("mass", "A lump or growth, usually larger than a nodule. A mass needs further checking to find out what it is.", I, "masses", concern=True),
    _t("lesion", "A general word for any abnormal area. It does not, by itself, mean cancer.", I, "lesions"),
    _t("edema", "Swelling caused by extra fluid in the tissue.", I, "oedema", "edematous"),
    _t("infiltrate", "An area of the lung filled with something other than air, such as fluid or cells.", I, "infiltrates"),
    _t("lymphadenopathy", "Enlarged lymph nodes. Infection and inflammation are common causes; sometimes follow-up is needed.", I),
    _t("calcification", "A small deposit of calcium. Many calcifications are harmless signs of old, healed processes.", I, "calcified", "calcifications"),
    _t("granuloma", "A small cluster of immune cells, often from an old infection. A calcified granuloma is usually harmless.", I, "granulomas"),
    _t("degenerative changes", "Wear-and-tear changes that come with age, often in joints or the spine.", I, "degenerative change", "degenerative"),
    _t("osteophyte", "A bone spur, a small bony growth that often comes with arthritis.", I, "osteophytes"),
    _t("fracture", "A broken bone.", I, "fractures"),
    _t("stenosis", "Narrowing of a passage, such as a blood vessel or the spinal canal.", I),
    _t("hernia", "Part of an organ or tissue pushing through a weak spot in the muscle or tissue around it.", I),
    _t("cyst", "A sac filled with fluid. Simple cysts are usually harmless.", I, "cysts", "cystic"),
    _t("emphysema", "Damage to the tiny air sacs in the lungs, which makes breathing out harder. Smoking is the most common cause.", I),
    _t("fibrosis", "Scarring of tissue.", I, "fibrotic"),
    _t("bronchiectasis", "Airways that have become widened and scarred, which makes it harder to clear mucus.", I),
    _t("hepatomegaly", "An enlarged liver.", I),
    _t("splenomegaly", "An enlarged spleen.", I),
    _t("hepatic steatosis", "Fatty liver: extra fat stored in the liver.", I, "steatosis", "fatty liver"),
    _t("cholelithiasis", "Gallstones.", I, "gallstones"),
    _t("nephrolithiasis", "Kidney stones.", I, "kidney stones", "renal calculi"),
    _t("hydronephrosis", "Swelling of a kidney because urine is not draining properly.", I),
    _t("diverticulosis", "Small pouches in the wall of the colon. Very common with age and often causes no symptoms.", I),
    _t("diverticulitis", "Inflamed or infected pouches in the wall of the colon.", I),
    _t("pulmonary embolism", "A blood clot in the arteries of the lungs. It needs prompt treatment.", I, "pulmonary emboli", "PE", concern=True),
    _t("thrombus", "A blood clot inside a blood vessel.", I, "thrombosis", "clot", concern=True),
    _t("deep vein thrombosis", "A blood clot in a deep vein, usually in the leg.", I, "DVT", concern=True),
    _t("aneurysm", "A bulge in the wall of a blood vessel.", I, concern=True),
    _t("hemorrhage", "Bleeding.", I, "haemorrhage", "hematoma", concern=True),
    _t("infarct", "An area of tissue damaged because its blood supply was blocked (for example, a stroke in the brain).", I, "infarction", concern=True),
    _t("ischemia", "Not enough blood flow reaching a part of the body.", I, "ischemic", concern=True),
    _t("BI-RADS", "A 0 to 6 scale used for breast imaging: 0 means more images are needed, 1 and 2 are negative or benign, 3 is probably benign with short-term follow-up, 4 and 5 call for a biopsy, and 6 is a known cancer.", I, cs=True),
    _t("Lung-RADS", "A scale used for lung-cancer screening CT scans that says how concerning a lung nodule looks and when to re-scan.", I, cs=True),
    # --- imaging tests ------------------------------------------------------------
    _t("CT", "Computed tomography: a scan that combines many X-rays into cross-section pictures of the body.", M, "CT scan", "computed tomography", "CAT scan", cs=True),
    _t("MRI", "Magnetic resonance imaging: a scan that uses a strong magnet and radio waves, not X-rays, to make detailed pictures.", M, "magnetic resonance imaging", cs=True),
    _t("X-ray", "A quick picture that uses a small amount of radiation. Bones look white and air looks dark.", M, "radiograph", "radiographs", "x-ray", "xray"),
    _t("ultrasound", "An imaging test that uses sound waves, with no radiation.", M, "sonogram", "US", "sonography"),
    _t("PET", "Positron emission tomography: a scan that shows how active different tissues are, using a small amount of a radioactive tracer.", M, "PET scan", "PET/CT", cs=True),
    _t("contrast", "A dye given for some scans so that blood vessels and organs show up more clearly.", M, "contrast agent", "IV contrast", "with contrast"),
    _t("PA and lateral", "Two chest X-ray pictures: one taken from back to front (PA) and one from the side (lateral).", M, "PA and lateral views", "PA/lateral"),
    _t("Hounsfield units", "The scale that measures how dense something looks on a CT scan. Water is 0, air is about -1000 and bone is several hundred or more.", M, "HU"),
    # --- pathology ----------------------------------------------------------------
    _t("biopsy", "A small sample of tissue taken out so it can be looked at under a microscope.", P, "biopsies"),
    _t("excision", "Surgery that removes a whole lump or area of tissue.", P, "excised", "excisional"),
    _t("resection", "Surgery that removes part or all of an organ or tissue.", P, "resected"),
    _t("margin", "The edge of the tissue that was removed. 'Negative' or 'clear' margins mean no abnormal cells were seen at the edge, which suggests the area was fully removed.", P, "margins"),
    _t("benign", "Not cancer.", P),
    _t("malignant", "Cancer: cells that can grow into nearby tissue or spread to other parts of the body.", P, "malignancy", concern=True),
    _t("carcinoma", "A type of cancer that starts in the cells lining organs or skin.", P, "carcinomas", concern=True),
    _t("adenocarcinoma", "A cancer that starts in gland cells, such as in the colon, lung, breast or prostate.", P, concern=True),
    _t("squamous cell carcinoma", "A cancer that starts in flat cells, such as those in the skin or the lining of the airways.", P, concern=True),
    _t("metastasis", "Cancer that has spread from where it started to another part of the body.", P, "metastatic", "metastases", concern=True),
    _t("neoplasm", "A growth of new tissue, also called a tumor. It can be benign (not cancer) or malignant (cancer).", P, "neoplastic", "tumor", "tumour", concern=True),
    _t("in situ", "Abnormal cells that have stayed in the layer where they started and have not grown into deeper tissue.", P),
    _t("invasive", "Abnormal cells have grown beyond the layer where they started into the tissue around it.", P, concern=True),
    _t("dysplasia", "Cells that look abnormal under the microscope but are not cancer. Some types can turn into cancer over time, so follow-up is common.", P, "dysplastic"),
    _t("high-grade dysplasia", "Cells that look very abnormal and are more likely to become cancer if left alone. Usually treated or removed.", P, concern=True),
    _t("atypia", "Cells that look somewhat unusual. It is not cancer, but the doctor may want to check further.", P, "atypical"),
    _t("hyperplasia", "More cells than usual, but cells that look normal. Usually not cancer.", P, "hyperplastic"),
    _t("metaplasia", "One kind of normal cell has been replaced by another kind, often in response to irritation.", P),
    _t("necrosis", "Dead tissue.", P, "necrotic"),
    _t("inflammation", "The body's response to injury or infection, with swelling and immune cells.", P, "inflamed", "inflammatory"),
    _t("chronic", "Long-lasting or slowly developing.", P),
    _t("acute", "Sudden or recent.", P),
    _t("grade", "How abnormal the cells look under the microscope. A lower grade usually means slower-growing.", P, "histologic grade", only=("pathology",)),
    _t("stage", "How large a cancer is and how far it has spread. Staging helps choose treatment.", P, "TNM", "staging", "pathologic stage", only=("pathology",)),
    _t("lymphovascular invasion", "Cancer cells were seen inside small blood or lymph vessels.", P, "LVI", concern=True),
    _t("perineural invasion", "Cancer cells were seen along a nerve.", P, concern=True),
    _t("immunohistochemistry", "A lab stain that uses antibodies to show which proteins the cells make. It helps identify the type of cells.", P, "IHC", "immunostain", "immunostains"),
    _t("H&E", "The standard pink-and-purple stain used to look at tissue under a microscope.", P, "hematoxylin and eosin", cs=True),
    _t("ER", "Estrogen receptor: a protein on some breast cancer cells. 'ER-positive' cancers can often be treated with hormone medicines.", P, "estrogen receptor", cs=True, only=("pathology",)),
    _t("PR", "Progesterone receptor: a hormone receptor tested in breast cancer, read together with ER.", P, "progesterone receptor", cs=True, only=("pathology",)),
    _t("HER2", "A protein that some cancers make too much of. It decides whether certain targeted medicines can help.", P, "HER-2", cs=True),
    _t("Ki-67", "A marker of how many cells are dividing. A higher percentage means faster growth.", P, "Ki67", cs=True),
    _t("Gleason score", "A score for prostate cancer based on how the cells look. A higher score means a more aggressive cancer.", P, "Gleason"),
    _t("polyp", "A small growth on the lining of an organ such as the colon. Many are harmless; some types can turn into cancer over years, which is why they are removed.", P, "polyps", "polypoid"),
    _t("tubular adenoma", "The most common kind of colon polyp. It is not cancer, but it is precancerous, so removing it lowers cancer risk.", P, "tubular adenomas"),
    _t("adenoma", "A non-cancerous growth that starts in gland tissue.", P, "adenomas", "adenomatous"),
    _t("fibroadenoma", "A common non-cancerous breast lump.", P),
    _t("frozen section", "A quick microscope check done during surgery to help the surgeon decide what to do next.", P),
    _t("lymph node", "Small bean-shaped glands that are part of the immune system. They are checked to see whether cancer has spread.", P, "lymph nodes", "nodal"),
    # --- lab tests ----------------------------------------------------------------
    _t("CBC", "Complete blood count: counts the red cells, white cells and platelets in your blood.", L, "complete blood count", cs=True),
    _t("WBC", "White blood cells, which fight infection.", L, "white blood cell count", "white blood cells", "leukocytes", cs=True),
    _t("RBC", "Red blood cells, which carry oxygen.", L, "red blood cell count", "red blood cells", cs=True),
    _t("hemoglobin", "The protein in red blood cells that carries oxygen. A low level is called anemia.", L, "Hgb", "HGB", "Hb", "haemoglobin"),
    _t("hematocrit", "The share of your blood made up of red blood cells.", L, "Hct", "HCT"),
    _t("platelets", "Small blood cells that help blood clot.", L, "platelet count", "PLT", "Plt"),
    _t("MCV", "Mean corpuscular volume: the average size of your red blood cells. Small cells can point to low iron.", L, "mean corpuscular volume", cs=True),
    _t("BMP", "Basic metabolic panel: a group of blood tests for salts, kidney function and sugar.", L, "basic metabolic panel", cs=True),
    _t("CMP", "Comprehensive metabolic panel: the basic panel plus liver tests and proteins.", L, "comprehensive metabolic panel", cs=True),
    _t("sodium", "A salt in the blood that helps control fluid balance.", L, "Na"),
    _t("potassium", "A salt in the blood that the heart and muscles need to work properly.", L, "K"),
    _t("chloride", "A salt in the blood that works with sodium to balance fluids.", L, "Cl"),
    _t("bicarbonate", "Shows the acid balance of the blood.", L, "CO2", "HCO3", "total CO2"),
    _t("glucose", "Blood sugar.", L, "blood sugar", "fasting glucose"),
    _t("BUN", "Blood urea nitrogen: a waste product cleared by the kidneys.", L, "blood urea nitrogen", "urea", cs=True),
    _t("creatinine", "A waste product from muscles that the kidneys clear. It is used to check kidney function.", L, "Cr", "Creat"),
    _t("eGFR", "Estimated glomerular filtration rate: an estimate of how well the kidneys filter blood. Higher is better.", L, "GFR", cs=True),
    _t("calcium", "A mineral needed for bones, muscles and nerves.", L, "Ca"),
    _t("albumin", "The main protein in blood, made by the liver.", L),
    _t("ALT", "A liver enzyme. High levels can mean the liver is irritated.", L, "alanine aminotransferase", "SGPT", cs=True),
    _t("AST", "An enzyme found in the liver and muscles. High levels can mean liver or muscle irritation.", L, "aspartate aminotransferase", "SGOT", cs=True),
    _t("ALP", "Alkaline phosphatase: an enzyme from the liver and bones.", L, "alkaline phosphatase", "Alk Phos", cs=True),
    _t("bilirubin", "A yellow substance made when old red blood cells break down. High levels can cause yellow skin (jaundice).", L, "total bilirubin", "T. bili"),
    _t("HbA1c", "Your average blood sugar over the past 2 to 3 months. It is used to diagnose and track diabetes.", L, "A1c", "hemoglobin A1c", "HgbA1c", cs=True),
    _t("TSH", "Thyroid-stimulating hormone: the main screening test for thyroid problems.", L, "thyroid stimulating hormone", cs=True),
    _t("LDL", "'Bad' cholesterol. Lower is generally better for the heart.", L, "LDL cholesterol", "LDL-C", cs=True),
    _t("HDL", "'Good' cholesterol. Higher is generally better for the heart.", L, "HDL cholesterol", "HDL-C", cs=True),
    _t("triglycerides", "A type of fat in the blood.", L, "TG"),
    _t("total cholesterol", "The total amount of cholesterol in the blood.", L, "cholesterol"),
    _t("CRP", "C-reactive protein: rises when there is inflammation somewhere in the body.", L, "C-reactive protein", cs=True),
    _t("ESR", "Erythrocyte sedimentation rate ('sed rate'): another general sign of inflammation.", L, "sed rate", cs=True),
    _t("INR", "A measure of how long blood takes to clot. Used to monitor blood thinners such as warfarin.", L, cs=True),
    _t("troponin", "A heart protein. A high level can mean heart muscle damage, such as from a heart attack.", L, "hs-troponin", "troponin I", "troponin T"),
    _t("ferritin", "A measure of the iron stored in your body.", L),
    _t("critical value", "A result far enough outside the usual range that the lab contacts the care team right away.", L, "critical result", "panic value", concern=True),
    # --- abbreviations ------------------------------------------------------------
    _t("hx", "History (your past health problems).", B, "Hx", "HX"),
    _t("dx", "Diagnosis.", B, "Dx", "DX"),
    _t("tx", "Treatment.", B, "Tx"),
    _t("rx", "Prescription.", B, "Rx", "RX"),
    _t("sx", "Symptoms.", B, "Sx"),
    _t("f/u", "Follow-up.", B, "F/U", "follow up", "follow-up"),
    _t("prn", "As needed.", B, "PRN", "p.r.n.", "as needed"),
    _t("bid", "Twice a day.", B, "BID", "b.i.d.", "twice a day", "twice daily"),
    _t("tid", "Three times a day.", B, "TID", "t.i.d.", "three times a day"),
    _t("qid", "Four times a day.", B, "QID", "q.i.d."),
    _t("qd", "Once a day.", B, "QD", "q.d.", "once daily", "once a day"),
    _t("qhs", "At bedtime.", B, "QHS", "q.h.s."),
    _t("po", "By mouth.", B, "PO", "p.o."),
    _t("NPO", "Nothing by mouth: do not eat or drink.", B, cs=True),
    _t("SOB", "Shortness of breath.", B, "shortness of breath", cs=True),
    _t("c/o", "Complains of.", B, "C/O"),
    _t("r/o", "Rule out: something the doctor wants to check for and exclude.", B, "R/O", "rule out"),
    _t("s/p", "Status post: after a past procedure or event (for example 's/p appendectomy' means after having the appendix removed).", B, "S/P", "status post"),
    _t("BP", "Blood pressure.", B, "blood pressure", cs=True),
    _t("HR", "Heart rate (pulse).", B, "heart rate", cs=True),
    _t("RR", "Respiratory rate: breaths per minute.", B, "respiratory rate", cs=True),
    _t("SpO2", "Oxygen saturation: how much oxygen your blood is carrying, measured with a finger clip.", B, "O2 sat", "oxygen saturation", "pulse ox", cs=True),
    _t("BMI", "Body mass index: weight compared with height.", B, "body mass index", cs=True),
    _t("ED", "Emergency department.", B, "emergency department", "emergency room", cs=True, only=("conversation", "radiology", "lab", "unknown")),
    _t("ER", "Emergency room.", B, cs=True, only=("conversation", "radiology", "lab", "unknown")),
    _t("PCP", "Primary care provider: your main doctor or nurse practitioner.", B, "primary care provider", "primary care physician", cs=True),
    _t("NSAID", "A group of pain relievers that also reduce inflammation, such as ibuprofen and naproxen.", B, "NSAIDs", cs=True),
    _t("ECG", "Electrocardiogram: a test that records the heart's electrical activity.", B, "EKG", "electrocardiogram", cs=True),
    _t("differential diagnosis", "The list of possible explanations the doctor is considering.", B, "differential", "ddx", "DDx"),
    _t("idiopathic", "Of unknown cause.", B),
    _t("prognosis", "The likely course or outcome of a condition.", B),
    _t("remission", "Signs and symptoms of a disease have lessened or disappeared.", B),
    # --- conditions ---------------------------------------------------------------
    _t("hypertension", "High blood pressure.", C, "HTN", "high blood pressure"),
    _t("hypotension", "Low blood pressure.", C),
    _t("diabetes", "A condition in which blood sugar runs too high.", C, "diabetes mellitus", "DM", "T2DM", "type 2 diabetes"),
    _t("hyperlipidemia", "High levels of fats such as cholesterol in the blood.", C, "dyslipidemia", "HLD", "high cholesterol"),
    _t("anemia", "Too few red blood cells or too little hemoglobin, which can cause tiredness.", C, "anaemia", "anemic"),
    _t("coronary artery disease", "Narrowing of the blood vessels that supply the heart.", C, "CAD"),
    _t("heart failure", "The heart does not pump as well as it should. It does not mean the heart has stopped.", C, "CHF", "congestive heart failure"),
    _t("atrial fibrillation", "An irregular, often fast heartbeat.", C, "AFib", "a-fib", "AF"),
    _t("COPD", "Chronic obstructive pulmonary disease: long-term lung disease, such as emphysema, that makes breathing harder.", C, "chronic obstructive pulmonary disease", cs=True),
    _t("asthma", "A condition in which the airways narrow and swell, causing wheezing and shortness of breath.", C),
    _t("pneumonia", "An infection of the lungs.", C),
    _t("GERD", "Gastroesophageal reflux disease: stomach acid flowing back up into the food pipe, causing heartburn.", C, "acid reflux", "reflux", cs=True),
    _t("UTI", "Urinary tract infection.", C, "urinary tract infection", cs=True),
    _t("URI", "Upper respiratory infection, such as a cold.", C, "upper respiratory infection", cs=True),
    _t("hypothyroidism", "An underactive thyroid gland.", C),
    _t("hyperthyroidism", "An overactive thyroid gland.", C),
    _t("chronic kidney disease", "Long-term loss of kidney function.", C, "CKD"),
    _t("osteoarthritis", "Wear-and-tear arthritis of the joints.", C, "OA"),
    _t("migraine", "A type of headache, often with sensitivity to light or nausea.", C, "migraines"),
    # --- medications --------------------------------------------------------------
    _t("lisinopril", "A blood pressure medicine (ACE inhibitor), also used for heart failure and to protect the kidneys.", D),
    _t("losartan", "A blood pressure medicine (ARB).", D),
    _t("amlodipine", "A blood pressure medicine (calcium channel blocker).", D),
    _t("metoprolol", "A beta blocker used for blood pressure, heart rhythm and heart failure.", D),
    _t("hydrochlorothiazide", "A 'water pill' (diuretic) used for blood pressure.", D, "HCTZ"),
    _t("furosemide", "A strong 'water pill' (diuretic) that removes extra fluid.", D, "Lasix"),
    _t("metformin", "A first-choice medicine for type 2 diabetes.", D),
    _t("insulin", "A hormone, given as a medicine, that lowers blood sugar.", D),
    _t("atorvastatin", "A statin: lowers cholesterol.", D, "Lipitor"),
    _t("simvastatin", "A statin: lowers cholesterol.", D),
    _t("rosuvastatin", "A statin: lowers cholesterol.", D),
    _t("statin", "A group of medicines that lower cholesterol.", D, "statins"),
    _t("aspirin", "A pain reliever that also makes blood less likely to clot.", D, "ASA"),
    _t("warfarin", "A blood thinner. It needs regular INR blood tests.", D, "Coumadin"),
    _t("apixaban", "A blood thinner.", D, "Eliquis"),
    _t("acetaminophen", "A pain and fever reliever (Tylenol). Taking more than the label says can harm the liver.", D, "Tylenol", "paracetamol"),
    _t("ibuprofen", "A pain reliever that also reduces inflammation (an NSAID), such as Advil or Motrin.", D, "Advil", "Motrin"),
    _t("naproxen", "A pain reliever that also reduces inflammation (an NSAID), such as Aleve.", D, "Aleve"),
    _t("amoxicillin", "An antibiotic.", D),
    _t("azithromycin", "An antibiotic.", D, "Z-pak", "Zithromax"),
    _t("doxycycline", "An antibiotic.", D),
    _t("cephalexin", "An antibiotic.", D, "Keflex"),
    _t("nitrofurantoin", "An antibiotic used for bladder infections.", D, "Macrobid"),
    _t("prednisone", "A steroid medicine that calms inflammation.", D),
    _t("omeprazole", "Lowers stomach acid (a proton pump inhibitor).", D, "Prilosec"),
    _t("pantoprazole", "Lowers stomach acid (a proton pump inhibitor).", D, "Protonix"),
    _t("albuterol", "A rescue inhaler that quickly opens the airways.", D, "ventolin", "proair"),
    _t("levothyroxine", "Thyroid hormone replacement for an underactive thyroid.", D, "Synthroid"),
    _t("sertraline", "An antidepressant (SSRI), also used for anxiety.", D, "Zoloft"),
    _t("gabapentin", "A medicine for nerve pain and seizures.", D),
    _t("cetirizine", "An allergy medicine (antihistamine).", D, "Zyrtec"),
    _t("loratadine", "An allergy medicine (antihistamine).", D, "Claritin"),
    _t("fluticasone", "A steroid nasal spray or inhaler that calms inflammation.", D, "Flonase", "Flovent"),
    _t("montelukast", "A daily tablet for asthma and allergies.", D, "Singulair"),
    _t("ondansetron", "An anti-nausea medicine.", D, "Zofran"),
)
