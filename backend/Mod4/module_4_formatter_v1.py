"""
Module 4: Frontend API  |  FastAPI  |  Port 8080
=================================================
Reads mod3_output.json, formats it, and serves it via REST API.

Run:
    pip install fastapi uvicorn
    python module_4_formatter_v1.py

Endpoints:
    GET  /                        health check
    GET  /results                 full formatted output (all trials)
    GET  /results/summary         patient + summary stats only
    GET  /results/trials          ranked trial cards only
    GET  /results/trials/{nct_id} single trial card by NCT ID
    GET  /results/eligible        only Eligible trials
    GET  /results/refresh         reload mod3_output.json and reformat
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ============================================================================
# PATHS & CONFIG
# ============================================================================

MOD3_OUTPUT_PATH: Path = Path(
    r"D:\C&C\COHERENCE-26_Compile-and-Cry\backend\Mod3\mod3_output.json"
)
OUTPUT_PATH: Path = Path(
    r"D:\C&C\COHERENCE-26_Compile-and-Cry\backend\Mod4\mod4_frontend_output.json"
)

HOST: str = "0.0.0.0"
PORT: int = 8080

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("Mod4")

# ============================================================================
# CONSTANTS
# ============================================================================

FEATURE_LABELS: Dict[str, str] = {
    "age_in_range":            "Age within trial range",
    "age_diff_norm":           "Age distance from range boundary",
    "hba1c_match":             "HbA1c level compatibility",
    "fasting_glucose_match":   "Fasting glucose compatibility",
    "bmi_match":               "BMI compatibility",
    "egfr_match":              "Kidney function (eGFR) compatibility",
    "creatinine_match":        "Creatinine level compatibility",
    "has_required_condition":  "Has required diagnosis",
    "has_excluded_condition":  "Has excluded condition",
    "has_excluded_medication": "Has excluded medication",
    "missing_critical_labs":   "Missing critical lab values",
    "inclusion_coverage":      "Inclusion criteria coverage",
    "exclusion_safe_rate":     "Safety from exclusion criteria",
    "total_inclusions":        "Number of inclusion criteria",
    "total_exclusions":        "Number of exclusion criteria",
    "parse_confidence":        "Trial data parse confidence",
}

BADGE_CONFIG: Dict[str, Dict[str, str]] = {
    "Eligible":        {"color": "#16a34a", "bg": "#dcfce7", "icon": "✓"},
    "Likely Eligible": {"color": "#ca8a04", "bg": "#fef9c3", "icon": "~"},
    "Ineligible":      {"color": "#dc2626", "bg": "#fee2e2", "icon": "✗"},
}


def _score_band(score: float) -> str:
    if score >= 80: return "Excellent Match"
    if score >= 65: return "Good Match"
    if score >= 45: return "Partial Match"
    if score >= 25: return "Weak Match"
    return "Poor Match"


# ============================================================================
# FORMATTER
# ============================================================================

class Mod4Formatter:

    def format_trial(
        self,
        trial:        Dict[str, Any],
        rank:         int,
        patient_meta: Dict[str, Any],
    ) -> Dict[str, Any]:

        score         = float(trial.get("final_score", 0))
        xgb_score     = float(trial.get("xgboost_score", 0))
        confidence    = float(trial.get("confidence", 0))
        rule_passed   = bool(trial.get("rule_passed", False))
        rule_failures = trial.get("rule_failures", [])
        elabel        = trial.get("eligibility_label", "Ineligible")
        shap_values   = trial.get("shap_values", {})
        shap_pos      = trial.get("shap_top_positive", [])
        shap_neg      = trial.get("shap_top_negative", [])
        badge         = BADGE_CONFIG.get(elabel, BADGE_CONFIG["Ineligible"])

        return {
            "rank":    rank,
            "nct_id":  trial.get("nct_id", ""),
            "title":   trial.get("trial_title", ""),

            "eligibility": {
                "label":                elabel,
                "score":                round(score, 1),
                "score_pct":            f"{round(score, 1)}%",
                "band":                 _score_band(score),
                "badge_color":          badge["color"],
                "badge_bg":             badge["bg"],
                "badge_icon":           badge["icon"],
                "rule_passed":          rule_passed,
                "confidence":           round(confidence * 100, 1),
                "confidence_pct":       f"{round(confidence * 100, 1)}%",
                "xgboost_probability":  round(xgb_score * 100, 1),
            },

            "why_matched":     self._format_why_matched(shap_pos),
            "why_not_matched": self._format_why_not_matched(shap_neg, rule_failures),

            "hard_disqualifiers": [
                {
                    "reason":   r,
                    "severity": "hard",
                    "action":   "Patient does not meet this mandatory criterion",
                }
                for r in rule_failures
            ],

            "explanation_cards": self._build_explanation_cards(shap_values),
            "match_breakdown":   self._build_match_breakdown(
                                     trial.get("feature_vector", {})),
            "recommendation":    self._build_recommendation(
                                     elabel, score, rule_failures, shap_neg),
        }

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _format_why_matched(shap_pos: List[Dict]) -> List[Dict]:
        out = []
        for item in shap_pos:
            feat  = item.get("feature", "")
            val   = float(item.get("shap_value", 0.0))
            label = FEATURE_LABELS.get(feat, feat.replace("_", " ").title())
            out.append({
                "factor":      label,
                "impact":      round(abs(val) * 100, 2),
                "impact_pct":  f"+{round(abs(val) * 100, 2)}%",
                "description": f"{label} is a positive factor for this trial match.",
            })
        return out

    @staticmethod
    def _format_why_not_matched(
        shap_neg:      List[Dict],
        rule_failures: List[str],
    ) -> List[Dict]:
        out = []
        for item in shap_neg:
            feat  = item.get("feature", "")
            val   = float(item.get("shap_value", 0.0))
            label = FEATURE_LABELS.get(feat, feat.replace("_", " ").title())
            out.append({
                "factor":      label,
                "impact":      round(abs(val) * 100, 2),
                "impact_pct":  f"-{round(abs(val) * 100, 2)}%",
                "description": f"{label} is reducing the match score for this trial.",
                "type":        "soft",
            })
        for r in rule_failures:
            out.append({
                "factor":      "Hard Disqualifier",
                "impact":      100.0,
                "impact_pct":  "-100%",
                "description": r,
                "type":        "hard",
            })
        return out

    @staticmethod
    def _build_explanation_cards(shap_values: Dict[str, float]) -> List[Dict]:
        ranked = sorted(
            shap_values.items(),
            key=lambda x: abs(float(x[1])),
            reverse=True,
        )[:5]
        cards = []
        for feat, val in ranked:
            fval      = float(val)
            label     = FEATURE_LABELS.get(feat, feat.replace("_", " ").title())
            direction = "positive" if fval >= 0 else "negative"
            cards.append({
                "feature":        feat,
                "label":          label,
                "shap_value":     round(fval, 4),
                "impact_pct":     round(abs(fval) * 100, 2),
                "direction":      direction,
                "direction_icon": "↑" if direction == "positive" else "↓",
                "color":          "#16a34a" if direction == "positive" else "#dc2626",
                "description": (
                    f"{label} increases match likelihood."
                    if direction == "positive"
                    else f"{label} decreases match likelihood."
                ),
            })
        return cards

    @staticmethod
    def _build_match_breakdown(fv: Dict[str, float]) -> Dict[str, Any]:
        def pct(v: Optional[float]) -> Optional[float]:
            return None if v is None else round(float(v) * 100, 1)

        return {
            "demographics": {
                "age_in_range":  bool(round(fv.get("age_in_range", 0))),
                "age_score_pct": pct(fv.get("age_in_range")),
            },
            "lab_compatibility": {
                "HbA1c":           pct(fv.get("hba1c_match")),
                "Fasting_Glucose": pct(fv.get("fasting_glucose_match")),
                "BMI":             pct(fv.get("bmi_match")),
                "eGFR":            pct(fv.get("egfr_match")),
                "Creatinine":      pct(fv.get("creatinine_match")),
            },
            "criteria_coverage": {
                "inclusion_coverage_pct":  pct(fv.get("inclusion_coverage")),
                "exclusion_safe_rate_pct": pct(fv.get("exclusion_safe_rate")),
                "missing_critical_labs":   int(fv.get("missing_critical_labs", 0)),
            },
            "conditions": {
                "has_required_condition":  bool(round(fv.get("has_required_condition", 0))),
                "has_excluded_condition":  bool(round(fv.get("has_excluded_condition", 0))),
                "has_excluded_medication": bool(round(fv.get("has_excluded_medication", 0))),
            },
        }

    @staticmethod
    def _build_recommendation(
        label:         str,
        score:         float,
        rule_failures: List[str],
        shap_neg:      List[Dict],
    ) -> Dict[str, Any]:
        if label == "Eligible":
            action, priority = "Proceed with eligibility screening", "High"
            details = (
                "This patient shows strong compatibility with the trial criteria. "
                "Recommend contacting the trial coordinator for formal screening."
            )
        elif label == "Likely Eligible":
            action, priority = "Review borderline criteria before screening", "Medium"
            details = (
                "Patient partially meets trial criteria. "
                "Review the flagged factors below before proceeding."
            )
        else:
            action, priority = "Trial not recommended at this time", "Low"
            details = (
                "Patient does not meet one or more mandatory criteria. "
                "Re-evaluate if clinical status changes."
            )

        issues = [{"issue": r, "type": "hard_fail"} for r in rule_failures]
        for item in shap_neg[:3]:
            feat   = item.get("feature", "")
            lbl    = FEATURE_LABELS.get(feat, feat.replace("_", " ").title())
            issues.append({"issue": f"{lbl} is suboptimal", "type": "soft_fail"})

        return {
            "action":            action,
            "details":           details,
            "priority":          priority,
            "issues_to_address": issues,
        }


# ============================================================================
# PIPELINE HELPERS
# ============================================================================

def _format_patient_summary(data: Dict[str, Any]) -> Dict[str, Any]:
    labs = data.get("labs_used", {})
    return {
        "patient_id":          data.get("patient_id", ""),
        "age":                 data.get("age"),
        "gender":              data.get("gender"),
        "conditions_inferred": data.get("conditions_inferred", []),
        "labs": {
            "HbA1c":           labs.get("HbA1c"),
            "Fasting_Glucose": labs.get("Fasting_Glucose"),
            "BMI":             labs.get("BMI"),
            "eGFR":            labs.get("eGFR"),
            "Creatinine":      labs.get("Creatinine"),
        },
    }


def _format_summary_stats(ranked: List[Dict]) -> Dict[str, Any]:
    scores  = [float(t.get("final_score", 0)) for t in ranked]
    return {
        "total_trials_evaluated": len(ranked),
        "eligible_count":         sum(1 for t in ranked if t.get("eligibility_label") == "Eligible"),
        "likely_eligible_count":  sum(1 for t in ranked if t.get("eligibility_label") == "Likely Eligible"),
        "ineligible_count":       sum(1 for t in ranked if t.get("eligibility_label") == "Ineligible"),
        "top_score":              round(max(scores), 1) if scores else 0,
        "average_score":          round(sum(scores) / len(scores), 1) if scores else 0,
        "score_distribution": {
            "excellent_80_plus": sum(1 for s in scores if s >= 80),
            "good_65_79":        sum(1 for s in scores if 65 <= s < 80),
            "partial_45_64":     sum(1 for s in scores if 45 <= s < 65),
            "weak_25_44":        sum(1 for s in scores if 25 <= s < 45),
            "poor_below_25":     sum(1 for s in scores if s < 25),
        },
    }


def _build_payload(mod3_data: Dict[str, Any]) -> Dict[str, Any]:
    ranked_trials    = mod3_data.get("ranked_trials", [])
    formatter        = Mod4Formatter()
    patient_meta     = _format_patient_summary(mod3_data)
    formatted_trials = [
        formatter.format_trial(trial, rank=i + 1, patient_meta=patient_meta)
        for i, trial in enumerate(ranked_trials)
    ]
    return {
        "generated_at":   datetime.now().isoformat(),
        "schema_version": "1.0",
        "mod3_source":    str(MOD3_OUTPUT_PATH),
        "patient":        patient_meta,
        "summary":        _format_summary_stats(ranked_trials),
        "trials":         formatted_trials,
    }


def _load_and_format() -> Dict[str, Any]:
    """Read mod3_output.json, format, save to disk, return payload."""
    if not MOD3_OUTPUT_PATH.exists():
        raise FileNotFoundError(str(MOD3_OUTPUT_PATH))

    with open(MOD3_OUTPUT_PATH, encoding="utf-8") as f:
        mod3_data = json.load(f)

    if not mod3_data.get("ranked_trials"):
        raise ValueError("No ranked_trials found in mod3_output.json.")

    payload = _build_payload(mod3_data)

    # Also persist to disk
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    log.info(f"Saved → {OUTPUT_PATH}  ({os.path.getsize(OUTPUT_PATH):,} bytes)")

    return payload


# ============================================================================
# STARTUP — load once into memory
# ============================================================================

_cache: Dict[str, Any] = {}

def _get_payload() -> Dict[str, Any]:
    """Return cached payload; raise 503 if not loaded yet."""
    if not _cache:
        raise HTTPException(
            status_code=503,
            detail="Data not loaded yet. Call GET /results/refresh first.",
        )
    return _cache


# ============================================================================
# FASTAPI APP  (lifespan replaces deprecated on_event)
# ============================================================================

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── startup ──────────────────────────────────────────────────────
    global _cache
    try:
        _cache = _load_and_format()
        log.info(f"Startup load complete — {len(_cache.get('trials', []))} trials ready")
    except Exception as e:
        log.error(f"Startup load failed: {e}. Use GET /results/refresh to retry.")
    yield
    # ── shutdown (nothing to clean up) ───────────────────────────────

app = FastAPI(
    title="Clinical Trial Matcher — Mod4 API",
    description="Serves frontend-ready trial matching results from Mod3 output.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow all origins so any frontend (React, Vue, etc.) can call freely
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ============================================================================
# ROUTES
# ============================================================================

@app.get("/", tags=["Health"])
def health():
    """Health check — confirms server is running."""
    return {
        "status":    "ok",
        "service":   "Mod4 Clinical Trial Matcher API",
        "port":      PORT,
        "loaded":    bool(_cache),
        "trials":    len(_cache.get("trials", [])) if _cache else 0,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/results", tags=["Results"])
def get_all_results():
    """
    Full formatted payload: patient + summary + all ranked trial cards.
    This is the primary endpoint for the frontend dashboard.
    """
    return JSONResponse(content=_get_payload())


@app.get("/results/summary", tags=["Results"])
def get_summary():
    """Patient info + aggregated stats only (no trial cards)."""
    payload = _get_payload()
    return JSONResponse(content={
        "generated_at": payload["generated_at"],
        "patient":      payload["patient"],
        "summary":      payload["summary"],
    })


@app.get("/results/trials", tags=["Results"])
def get_trials(
    label:    Optional[str] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
):
    """
    All ranked trial cards.

    Optional query params:
      ?label=Eligible               filter by eligibility_label
      ?min_score=60                 filter by minimum final_score
      ?max_score=90                 filter by maximum final_score

    Example: GET /results/trials?label=Eligible&min_score=70
    """
    trials = _get_payload().get("trials", [])

    if label:
        trials = [t for t in trials
                  if t["eligibility"]["label"].lower() == label.lower()]
    if min_score is not None:
        trials = [t for t in trials if t["eligibility"]["score"] >= min_score]
    if max_score is not None:
        trials = [t for t in trials if t["eligibility"]["score"] <= max_score]

    return JSONResponse(content={
        "count":  len(trials),
        "trials": trials,
    })


@app.get("/results/trials/{nct_id:path}", tags=["Results"])
def get_trial_by_id(nct_id: str):
    """Single trial card by NCT ID (URL-encoded slashes supported)."""
    trials = _get_payload().get("trials", [])
    match  = next((t for t in trials if t["nct_id"] == nct_id), None)
    if not match:
        raise HTTPException(
            status_code=404,
            detail=f"Trial '{nct_id}' not found.",
        )
    return JSONResponse(content=match)


@app.get("/results/eligible", tags=["Results"])
def get_eligible_trials():
    """Shortcut — returns only Eligible trials sorted by score."""
    trials = _get_payload().get("trials", [])
    eligible = [
        t for t in trials
        if t["eligibility"]["label"] == "Eligible"
    ]
    return JSONResponse(content={
        "count":  len(eligible),
        "trials": eligible,
    })


@app.get("/results/refresh", tags=["Admin"])
def refresh():
    """
    Reload mod3_output.json from disk and reformat.
    Call this after running mod3_matcher.py with new data.
    """
    global _cache
    try:
        _cache = _load_and_format()
        return {
            "status":  "refreshed",
            "trials":  len(_cache.get("trials", [])),
            "loaded_at": datetime.now().isoformat(),
        }
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"mod3_output.json not found at {MOD3_OUTPUT_PATH}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    log.info(f"Starting Mod4 API on http://{HOST}:{PORT}")
    log.info(f"Docs available at http://127.0.0.1:{PORT}/docs")
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="info",
    )