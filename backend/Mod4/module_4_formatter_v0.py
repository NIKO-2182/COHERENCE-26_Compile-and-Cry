"""
Module 4: Frontend-Ready JSON Formatter
========================================
Input  : D:\C&C\COHERENCE-26_Compile-and-Cry\backend\Mod3\mod3_output.json
Output : D:\C&C\COHERENCE-26_Compile-and-Cry\backend\Mod4\mod4_frontend_output.json

What this module does:
  - Strips internal fields (feature_vector, raw shap_values dict)
  - Converts scores to human-readable percentages and labels
  - Formats SHAP into ordered explanation cards
  - Adds match_summary, eligibility_badge, why_matched / why_not_matched
  - Produces a clean, flat, frontend-consumable JSON structure
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ============================================================================
# PATHS
# ============================================================================

MOD3_OUTPUT_PATH: Path = Path(
    r"D:\C&C\COHERENCE-26_Compile-and-Cry\backend\Mod3\mod3_output.json"
)
OUTPUT_PATH: Path = Path(
    r"D:\C&C\COHERENCE-26_Compile-and-Cry\backend\Mod4\mod4_frontend_output.json"
)

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

# Human-readable labels for each feature name used in SHAP
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

# Badge colours for frontend
BADGE_CONFIG: Dict[str, Dict[str, str]] = {
    "Eligible":        {"color": "#16a34a", "bg": "#dcfce7", "icon": "✓"},
    "Likely Eligible": {"color": "#ca8a04", "bg": "#fef9c3", "icon": "~"},
    "Ineligible":      {"color": "#dc2626", "bg": "#fee2e2", "icon": "✗"},
}

# Score band labels
def _score_band(score: float) -> str:
    if score >= 80:
        return "Excellent Match"
    if score >= 65:
        return "Good Match"
    if score >= 45:
        return "Partial Match"
    if score >= 25:
        return "Weak Match"
    return "Poor Match"


# ============================================================================
# FORMATTER CORE
# ============================================================================

class Mod4Formatter:
    """Converts a single mod3 ranked_trial dict into a frontend card dict."""

    def format_trial(
        self,
        trial: Dict[str, Any],
        rank:  int,
        patient_meta: Dict[str, Any],
    ) -> Dict[str, Any]:

        score          = float(trial.get("final_score", 0))
        xgb_score      = float(trial.get("xgboost_score", 0))
        confidence     = float(trial.get("confidence", 0))
        rule_passed    = bool(trial.get("rule_passed", False))
        rule_failures  = trial.get("rule_failures", [])
        elabel         = trial.get("eligibility_label", "Ineligible")
        shap_values    = trial.get("shap_values", {})
        shap_pos       = trial.get("shap_top_positive", [])
        shap_neg       = trial.get("shap_top_negative", [])

        badge = BADGE_CONFIG.get(elabel, BADGE_CONFIG["Ineligible"])

        return {
            # ── Identity ───────────────────────────────────────────────
            "rank":       rank,
            "nct_id":     trial.get("nct_id", ""),
            "title":      trial.get("trial_title", ""),

            # ── Eligibility summary ────────────────────────────────────
            "eligibility": {
                "label":       elabel,
                "score":       round(score, 1),
                "score_pct":   f"{round(score, 1)}%",
                "band":        _score_band(score),
                "badge_color": badge["color"],
                "badge_bg":    badge["bg"],
                "badge_icon":  badge["icon"],
                "rule_passed": rule_passed,
                "confidence":  round(confidence * 100, 1),
                "confidence_pct": f"{round(confidence * 100, 1)}%",
                "xgboost_probability": round(xgb_score * 100, 1),
            },

            # ── Why matched / not matched ──────────────────────────────
            "why_matched": self._format_why_matched(shap_pos),
            "why_not_matched": self._format_why_not_matched(
                shap_neg, rule_failures
            ),

            # ── Rule failures (hard stops) ─────────────────────────────
            "hard_disqualifiers": [
                {
                    "reason": r,
                    "severity": "hard",
                    "action":   "Patient does not meet this mandatory criterion",
                }
                for r in rule_failures
            ],

            # ── SHAP explanation cards (top 5 by |shap|) ───────────────
            "explanation_cards": self._build_explanation_cards(shap_values),

            # ── Match breakdown (feature groups) ──────────────────────
            "match_breakdown": self._build_match_breakdown(
                trial.get("feature_vector", {})
            ),

            # ── Recommendation ─────────────────────────────────────────
            "recommendation": self._build_recommendation(
                elabel, score, rule_failures, shap_neg
            ),
        }

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _format_why_matched(shap_pos: List[Dict]) -> List[Dict]:
        out = []
        for item in shap_pos:
            feat  = item.get("feature", "")
            val   = item.get("shap_value", 0.0)
            label = FEATURE_LABELS.get(feat, feat.replace("_", " ").title())
            out.append({
                "factor":      label,
                "impact":      round(abs(float(val)) * 100, 2),
                "impact_pct":  f"+{round(abs(float(val)) * 100, 2)}%",
                "description": f"{label} is a positive factor for this trial match.",
            })
        return out

    @staticmethod
    def _format_why_not_matched(
        shap_neg: List[Dict],
        rule_failures: List[str],
    ) -> List[Dict]:
        out = []
        # SHAP negative factors
        for item in shap_neg:
            feat  = item.get("feature", "")
            val   = item.get("shap_value", 0.0)
            label = FEATURE_LABELS.get(feat, feat.replace("_", " ").title())
            out.append({
                "factor":      label,
                "impact":      round(abs(float(val)) * 100, 2),
                "impact_pct":  f"-{round(abs(float(val)) * 100, 2)}%",
                "description": f"{label} is reducing the match score for this trial.",
                "type":        "soft",
            })
        # Hard rule failures
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
        """Top 5 features by absolute SHAP value as explanation cards."""
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
        """Group features into Lab / Demographic / Criteria sections."""

        def pct(v: Optional[float]) -> Optional[float]:
            if v is None:
                return None
            return round(float(v) * 100, 1)

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
            action  = "Proceed with eligibility screening"
            details = (
                "This patient shows strong compatibility with the trial criteria. "
                "Recommend contacting the trial coordinator for formal screening."
            )
            priority = "High"
        elif label == "Likely Eligible":
            action  = "Review borderline criteria before screening"
            details = (
                "Patient partially meets trial criteria. "
                "Review the flagged factors below before proceeding."
            )
            priority = "Medium"
        else:
            action  = "Trial not recommended at this time"
            details = (
                "Patient does not meet one or more mandatory criteria. "
                "Re-evaluate if clinical status changes."
            )
            priority = "Low"

        # List specific issues to address
        issues = []
        for r in rule_failures:
            issues.append({"issue": r, "type": "hard_fail"})
        for item in shap_neg[:3]:
            feat  = item.get("feature", "")
            label_ = FEATURE_LABELS.get(feat, feat.replace("_", " ").title())
            issues.append({"issue": f"{label_} is suboptimal", "type": "soft_fail"})

        return {
            "action":   action,
            "details":  details,
            "priority": priority,
            "issues_to_address": issues,
        }


# ============================================================================
# PATIENT SUMMARY FORMATTER
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
    total    = len(ranked)
    eligible = sum(1 for t in ranked if t.get("eligibility_label") == "Eligible")
    likely   = sum(1 for t in ranked if t.get("eligibility_label") == "Likely Eligible")
    inelig   = sum(1 for t in ranked if t.get("eligibility_label") == "Ineligible")
    scores   = [float(t.get("final_score", 0)) for t in ranked]

    return {
        "total_trials_evaluated": total,
        "eligible_count":         eligible,
        "likely_eligible_count":  likely,
        "ineligible_count":       inelig,
        "top_score":              round(max(scores), 1) if scores else 0,
        "average_score":          round(sum(scores) / len(scores), 1) if scores else 0,
        "score_distribution": {
            "excellent_80_plus":   sum(1 for s in scores if s >= 80),
            "good_65_79":          sum(1 for s in scores if 65 <= s < 80),
            "partial_45_64":       sum(1 for s in scores if 45 <= s < 65),
            "weak_25_44":          sum(1 for s in scores if 25 <= s < 45),
            "poor_below_25":       sum(1 for s in scores if s < 25),
        },
    }


# ============================================================================
# SAVE OUTPUT
# ============================================================================

def save_output(payload: Dict[str, Any], path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log.error(f"Cannot create output directory '{path.parent}': {e}")
        raise

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        log.info(f"Output saved → {path}  ({os.path.getsize(path):,} bytes)")
    except Exception as e:
        log.error(f"Failed to write output: {e}")
        traceback.print_exc()
        raise


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":

    if not MOD3_OUTPUT_PATH.exists():
        raise FileNotFoundError(
            f"\nMod3 output not found:\n  {MOD3_OUTPUT_PATH}\n"
            "Run mod3_matcher.py first.\n"
        )

    log.info(f"Loading Mod3 output from {MOD3_OUTPUT_PATH}")
    with open(MOD3_OUTPUT_PATH, encoding="utf-8") as f:
        mod3_data = json.load(f)

    ranked_trials = mod3_data.get("ranked_trials", [])
    if not ranked_trials:
        raise ValueError("No ranked_trials found in mod3_output.json.")

    log.info(f"Formatting {len(ranked_trials)} trials …")

    formatter     = Mod4Formatter()
    patient_meta  = _format_patient_summary(mod3_data)

    formatted_trials = [
        formatter.format_trial(trial, rank=i + 1, patient_meta=patient_meta)
        for i, trial in enumerate(ranked_trials)
    ]

    payload = {
        "generated_at":   datetime.now().isoformat(),
        "schema_version": "1.0",
        "mod3_source":    str(MOD3_OUTPUT_PATH),

        # Patient card for frontend header
        "patient":        patient_meta,

        # Aggregated stats for dashboard widgets
        "summary":        _format_summary_stats(ranked_trials),

        # Full ranked trial cards — ready for frontend list rendering
        "trials":         formatted_trials,
    }

    save_output(payload, OUTPUT_PATH)
    log.info("Module 4 complete.")