# COHERENCE-26 — Nextrial

> **Compile and Cry** | Automated patient-to-trial eligibility matching using OCR, biomedical NER, XGBoost, and SHAP explanations.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Modules](#modules)
  - [Module 1 — Data Extractor](#module-1--data-extractor)
  - [Module 2 — Trial Criteria Parser](#module-2--trial-criteria-parser)
  - [Module 3 — Patient-Trial Matcher](#module-3--patient-trial-matcher)
  - [Module 4 — Frontend API Formatter](#module-4--frontend-api-formatter)
- [Pipeline Orchestrator](#pipeline-orchestrator)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Usage](#usage)
- [Output Schema](#output-schema)
- [Compliance Notes](#compliance-notes)
- [Tech Stack](#tech-stack)

---

## Overview

COHERENCE-26 is a full-stack backend pipeline that takes a patient's clinical lab report (PDF), extracts lab values and demographics via OCR, fetches relevant clinical trials, parses eligibility criteria using biomedical NER, matches the patient to trials using a self-supervised XGBoost model with SHAP explanations, and serves the ranked results via a REST API ready for frontend consumption.

**Problem it solves:** Clinical trial matching is manual, slow, and error-prone. A clinician must read hundreds of trial eligibility criteria and compare them against a patient's labs by hand. COHERENCE-26 automates this end-to-end in seconds.

**Current focus:** Type 2 Diabetes trials (expandable to any condition).

---

## Architecture

```
PDF Upload (port 8000)
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│                    run_pipeline.py                          │
│              Pipeline Orchestrator (FastAPI)                │
└──────┬──────────┬──────────┬──────────┬────────────────────┘
       │          │          │          │
       ▼          ▼          ▼          ▼
   [MOD 1]    [MOD 2]    [MOD 3]    [MOD 4]
  Extractor   NER Parser  XGBoost   Formatter
   (OCR)      (GLiNER)    + SHAP    (FastAPI)
       │          │          │          │
       ▼          ▼          ▼          ▼
extracted_   mod2_output  mod3_output  mod4_frontend
results/     .json        .json        _output.json
.json                                  ↓
                                   port 8080
                                   /results/*
```

---

## Modules

### Module 1 — Data Extractor

**File:** `Mod1/Data_Extractor/extract_patient_data/extractor.py`  
**Input:** Patient PDF lab report  
**Output:** `extracted_results/<name>_<patient_id>_<timestamp>.json`

Extracts structured data from clinical PDF lab reports using a two-pass approach:

**Pass 1 — Text extraction:**
- PyMuPDF (`fitz`) for native PDF text layer extraction
- Tesseract OCR fallback for scanned/image PDFs
- Regex-based demographics parser (patient ID, age, gender, report date)

**Pass 2 — Lab metric extraction:**
- Bounding box word alignment groups tokens by Y-coordinate proximity
- Heuristic value/unit/range detection per line
- Filters out non-test lines (headers, dates, page numbers)
- Extracts up to 53+ lab metrics per report

**Key function called by pipeline:**
```python
process_and_save(pdf_path, output_dir) -> {
    "result": { patient_id, age, gender, labs: {...} },
    "output_file": "path/to/saved.json",
    "status": "ok" | "error"
}
```

**Sample output:**
```json
{
  "patient_id": "REPORT",
  "age": 19,
  "gender": "Male",
  "labs": {
    "Glycosylated Hemoglobin (HbA1c)": { "value": "6.0", "unit": "%" },
    "Glucose - Fasting": { "value": "101", "unit": "mg/dL" },
    "Creatinine": { "value": "0.79", "unit": "mg/dL" }
  },
  "parse_confidence": 1.0
}
```

---

### Module 2 — Trial Criteria Parser

**File:** `Mod2/module_2 Clinical_v0.1.py`  
**Input:** Patient JSON + `clinical_trials_diabetes.json` (50 trials from ClinicalTrials.gov)  
**Output:** `Mod2/mod2_output.json`  
**Env var:** `MOD2_PATIENT_REPORT_PATH` (injected by pipeline to point at latest extracted JSON)

Parses raw free-text eligibility criteria from each clinical trial into structured inclusion/exclusion criterion objects using a hybrid NER approach:

**Primary — GLiNER biomedical NER:**
- Model: `Ihor/gliner-biomed-small-v1.0`
- Zero-shot entity extraction on clinical text
- Extracts: age, HbA1c, fasting glucose, BMI, eGFR, creatinine, blood pressure, diabetes duration, diagnosis
- Confidence threshold: 0.7 (below this, regex result wins)

**Fallback — Regex NER:**
- Hand-crafted patterns for 9 clinical fields
- Handles numeric ranges, inequality expressions, and unit variations
- Runs on every trial regardless of GLiNER result

**Merge logic:** GLiNER wins if confidence > 0.7, otherwise regex. Produces a `source_mix` label: `gliner_only`, `regex_only`, or `hybrid`.

**Per-trial output schema:**
```json
{
  "nct_id": "NCT01234567",
  "title": "...",
  "inclusions": [
    {
      "field_name": "age",
      "value": { "min": 30, "max": 65 },
      "unit": "years",
      "confidence": 0.91,
      "source": "gliner"
    }
  ],
  "exclusions": [...],
  "parse_confidence": 0.74,
  "source_mix": "hybrid"
}
```

---

### Module 3 — Patient-Trial Matcher

**File:** `Mod3/module_3_Xgboost_v0.2.py`  
**Input:** `Mod2/mod2_output.json`  
**Output:** `Mod3/mod3_output.json`

Five-stage matching pipeline:

**Stage 1 — Mod2Adapter**
- Reads patient snapshot and lab values from mod2 output
- Maps raw lab names to internal aliases (e.g. `"Glycosylated Hemoglobin (HbA1c)"` → `"HbA1c"`)
- Derives eGFR via CKD-EPI formula if not directly reported
- Infers conditions from lab values (HbA1c ≥ 6.5 or glucose ≥ 126 → Type 2 Diabetes)

**Stage 2 — RuleBasedPreFilter**
- Hard rejection on age range violations
- Hard rejection if patient has excluded conditions or medications
- Produces `rule_passed: bool` and `rule_failures: [...]` per trial

**Stage 3 — FeatureEngineer**
Builds a 16-dimensional feature vector per patient-trial pair:

| Feature | Description |
|---|---|
| `age_in_range` | 1 if patient age within trial bounds |
| `age_diff_norm` | Normalised distance from age boundary |
| `hba1c_match` | 0–1 range compatibility score |
| `fasting_glucose_match` | 0–1 range compatibility score |
| `bmi_match` | 0–1 range compatibility score |
| `egfr_match` | 0–1 range compatibility score |
| `creatinine_match` | 0–1 range compatibility score |
| `has_required_condition` | 1 if patient has required diagnosis |
| `has_excluded_condition` | 1 if patient has excluded condition |
| `has_excluded_medication` | 1 if patient has excluded medication |
| `missing_critical_labs` | Count of missing HbA1c/glucose/eGFR/creatinine |
| `inclusion_coverage` | Fraction of inclusion fields present in patient |
| `exclusion_safe_rate` | Fraction of exclusions patient is safe from |
| `total_inclusions` | Trial complexity proxy |
| `total_exclusions` | Trial complexity proxy |
| `parse_confidence` | Mod2 parse confidence for this trial |

**Stage 4 — XGBoostTrainer**
- Self-supervised soft labels: `0.8 × rule_passed + 0.2 × inclusion_coverage`
- Trains fresh on each patient's trial batch (100 rounds)
- Parameters: `max_depth=4, eta=0.1, subsample=0.8`

**Stage 5 — SHAPExplainer + RankingAggregator**
- `shap.TreeExplainer` produces per-trial SHAP values for all 16 features
- `final_score = xgboost_score × 100` (× 0.40 penalty if rule failed)
- Labels: `Eligible` (≥65, rule passed) | `Likely Eligible` (≥40) | `Ineligible`

---

### Module 4 — Frontend API Formatter

**File:** `Mod4/module_4_formatter_v1.py`  
**Input:** `Mod3/mod3_output.json`  
**Output:** `Mod4/mod4_frontend_output.json` + live REST API on port 8080

Transforms raw Mod3 output into clean, frontend-consumable JSON cards:

- Strips internal fields (`feature_vector`, raw `shap_values` dict)
- Converts scores to human-readable percentages and band labels
- Builds SHAP explanation cards with direction icons (`↑`/`↓`) and colours
- Generates `why_matched` / `why_not_matched` lists
- Produces `match_breakdown` grouped by demographics / labs / criteria
- Writes `recommendation` with action, priority, and issues to address
- Adds eligibility badge config (colour, background, icon) for UI rendering
- Computes summary stats: eligible count, score distribution, top score

---

## Pipeline Orchestrator

**File:** `run_pipeline.py`  
**Port:** 8000

Single entry point that starts a FastAPI upload server and orchestrates all four modules sequentially in a background thread when a PDF is received.

**Step sequence:**

| Step | Action | Method |
|---|---|---|
| 1 | PDF Extraction | Direct Python import of `extractor.process_and_save()` |
| 2 | Trial Fetch | Subprocess (skipped if file already exists) |
| 3 | Criteria Parsing | Subprocess with `MOD2_PATIENT_REPORT_PATH` env injection |
| 4 | Patient Matching | Subprocess |
| 5 | Results API | `Popen` (stays running) |

**Resilience features:**
- Step 3 checks `mod2_output.json` existence as fallback if Mod2 exits non-zero (handles Windows CP1252 Unicode print errors)
- All subprocesses forced to UTF-8 via `PYTHONIOENCODING=utf-8`
- Mod4 is terminated and restarted on each new pipeline run
- `/results/*` routes on port 8000 proxy to Mod4 on port 8080 (single port for frontend)

---

## API Reference

### Upload Server — Port 8000

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `POST` | `/upload-report` | Upload patient PDF, triggers pipeline |
| `GET` | `/status` | Poll pipeline progress |
| `GET` | `/results` | Proxy → Mod4 full results |
| `GET` | `/results/summary` | Proxy → patient + summary stats |
| `GET` | `/results/trials` | Proxy → trial cards (filterable) |
| `GET` | `/results/trials/{nct_id}` | Proxy → single trial card |
| `GET` | `/results/eligible` | Proxy → Eligible trials only |

**Query params for `/results/trials`:**
```
?label=Eligible
?min_score=65
?max_score=90
?label=Likely Eligible&min_score=40
```

### Results API — Port 8080

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/results` | Full payload |
| `GET` | `/results/summary` | Patient card + stats |
| `GET` | `/results/trials` | All ranked trial cards |
| `GET` | `/results/trials/{nct_id}` | Single trial card |
| `GET` | `/results/eligible` | Eligible only |
| `GET` | `/results/refresh` | Hot-reload from disk |

**Swagger UI:** `http://127.0.0.1:8000/docs` and `http://127.0.0.1:8080/docs`

---

## Project Structure

```
backend/
├── run_pipeline.py                          ← Master orchestrator (start here)
│
├── Mod1/
│   ├── Data_Extractor/
│   │   └── extract_patient_data/
│   │       ├── extractor.py                 ← OCR + lab extraction
│   │       └── extracted_results/           ← Output JSONs
│   └── trial_fetcher/
│       ├── trial_fetcher.py                 ← ClinicalTrials.gov fetcher
│       └── clinical_trials_diabetes.json    ← 50 cached trials
│
├── Mod2/
│   ├── module_2 Clinical_v0.1.py            ← GLiNER + regex NER parser
│   └── mod2_output.json                     ← Parsed trial criteria
│
├── Mod3/
│   ├── module_3_Xgboost_v0.2.py             ← XGBoost + SHAP matcher
│   └── mod3_output.json                     ← Ranked trial matches
│
├── Mod4/
│   ├── module_4_formatter_v1.py             ← FastAPI results server
│   └── mod4_frontend_output.json            ← Frontend-ready JSON
│
└── uploads/                                 ← Temporary PDF storage
```

---

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/your-org/COHERENCE-26.git
cd COHERENCE-26/backend

# 2. Create conda environment
conda create -n CC python=3.11
conda activate CC

# 3. Install dependencies
pip install fastapi uvicorn httpx
pip install PyMuPDF pytesseract pillow
pip install xgboost shap numpy
pip install gliner
pip install pyngrok  # optional, for public URL

# 4. Install Tesseract OCR (Windows)
# Download from: https://github.com/UB-Mannheim/tesseract/wiki
# Add to PATH after installation
```

---

## Usage

```bash
# Start the full pipeline server
python run_pipeline.py
```

Server starts on `http://0.0.0.0:8000`. Then upload a PDF:

```bash
# Via curl
curl -X POST http://localhost:8000/upload-report \
     -F "file=@patient_report.pdf"

# Poll status
curl http://localhost:8000/status

# Get results when done
curl http://localhost:8000/results
curl http://localhost:8000/results/eligible
curl "http://localhost:8000/results/trials?label=Eligible&min_score=70"
```

**Expected pipeline duration:** ~60–120 seconds for 50 trials (dominated by GLiNER inference in Mod2).

---

## Output Schema

### `/results` — Full Payload

```json
{
  "generated_at": "2026-03-07T08:02:08.123456",
  "schema_version": "1.0",
  "patient": {
    "patient_id": "REPORT",
    "age": 19,
    "gender": "Male",
    "conditions_inferred": ["Pre-diabetes"],
    "labs": {
      "HbA1c": 6.0,
      "Fasting_Glucose": 101.0,
      "eGFR": 127.0,
      "Creatinine": 0.79
    }
  },
  "summary": {
    "total_trials_evaluated": 50,
    "eligible_count": 12,
    "likely_eligible_count": 18,
    "ineligible_count": 20,
    "top_score": 89.65,
    "average_score": 52.3,
    "score_distribution": {
      "excellent_80_plus": 5,
      "good_65_79": 7,
      "partial_45_64": 14,
      "weak_25_44": 16,
      "poor_below_25": 8
    }
  },
  "trials": [
    {
      "rank": 1,
      "nct_id": "CTRI/2009/091/000104",
      "title": "...",
      "eligibility": {
        "label": "Eligible",
        "score": 89.65,
        "score_pct": "89.65%",
        "band": "Excellent Match",
        "badge_color": "#16a34a",
        "badge_bg": "#dcfce7",
        "badge_icon": "✓",
        "rule_passed": true,
        "confidence_pct": "74.4%"
      },
      "why_matched": [
        {
          "factor": "Age within trial range",
          "impact_pct": "+10.22%",
          "description": "Age within trial range is a positive factor."
        }
      ],
      "why_not_matched": [],
      "explanation_cards": [
        {
          "label": "Age within trial range",
          "impact_pct": 10.22,
          "direction": "positive",
          "direction_icon": "↑",
          "color": "#16a34a"
        }
      ],
      "match_breakdown": {
        "demographics": { "age_in_range": true, "age_score_pct": 100.0 },
        "lab_compatibility": { "HbA1c": 50.0, "Fasting_Glucose": 50.0 },
        "criteria_coverage": { "inclusion_coverage_pct": 33.3 },
        "conditions": { "has_required_condition": false }
      },
      "recommendation": {
        "action": "Proceed with eligibility screening",
        "priority": "High",
        "issues_to_address": []
      }
    }
  ]
}
```

---

## Compliance Notes

> ⚠️ This project is a **research prototype**. It is not currently HIPAA or DPDPA compliant for production use with real patient data.

**Current gaps:**
- No encryption at rest (JSON and PDF files stored as plaintext)
- No HTTPS on internal ports (8000/8080)
- No API authentication
- No audit logging
- PHI accumulates in `uploads/` and `extracted_results/` indefinitely

**Before using with real patient data:**
1. Add API key authentication to all endpoints
2. Enable HTTPS via nginx/Caddy or uvicorn SSL certs
3. Implement de-identification in Mod1 (hash patient_id, strip raw_text_snippet)
4. Add auto-deletion of PDFs after extraction
5. Encrypt output JSONs at rest using Fernet symmetric encryption
6. Add access audit logging middleware
7. Sign a Business Associate Agreement with your infrastructure provider

---

## Tech Stack

| Layer | Technology |
|---|---|
| API framework | FastAPI + Uvicorn |
| PDF extraction | PyMuPDF (fitz) |
| OCR | Tesseract via pytesseract |
| Biomedical NER | GLiNER (`Ihor/gliner-biomed-small-v1.0`) |
| Regex NER | Python `re` module |
| ML model | XGBoost (`reg:squarederror`) |
| Explainability | SHAP (`TreeExplainer`) |
| Proxy/HTTP client | httpx |
| Public tunneling | pyngrok + ngrok |
| Data format | JSON throughout |
| Language | Python 3.11 |
| Environment | Miniconda (CC env) |
| OS | Windows 11 |
