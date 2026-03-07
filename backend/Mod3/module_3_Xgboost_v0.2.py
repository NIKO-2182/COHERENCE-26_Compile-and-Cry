"""
Module 3: Patient-Trial Matching | XGBoost + SHAP -> JSON
==========================================================
Input  : D:\C&C\COHERENCE-26_Compile-and-Cry\backend\Mod2\mod2_output.json
Output : D:\C&C\COHERENCE-26_Compile-and-Cry\backend\Mod3\mod3_output.json

Pipeline:
  Mod2 JSON -> Mod2Adapter -> RuleBasedPreFilter -> FeatureEngineer
            -> XGBoostTrainer -> SHAPExplainer -> RankingAggregator
            -> save mod3_output.json
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import xgboost as xgb
import shap


# ============================================================================
# PATHS
# ============================================================================

MOD2_OUTPUT_PATH: Path = Path(
    r"D:\C&C\COHERENCE-26_Compile-and-Cry\backend\Mod2\mod2_output.json"
)
OUTPUT_PATH: Path = Path(
    r"D:\C&C\COHERENCE-26_Compile-and-Cry\backend\Mod3\mod3_output.json"
)


# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("Mod3")


# ============================================================================
# JSON SERIALIZER  (handles numpy types so json.dump never crashes)
# ============================================================================

class SafeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
            return None
        return super().default(obj)


# ============================================================================
# CONSTANTS
# ============================================================================

FEATURE_NAMES: List[str] = [
    "age_in_range",
    "age_diff_norm",
    "hba1c_match",
    "fasting_glucose_match",
    "bmi_match",
    "egfr_match",
    "creatinine_match",
    "has_required_condition",
    "has_excluded_condition",
    "has_excluded_medication",
    "missing_critical_labs",
    "inclusion_coverage",
    "exclusion_safe_rate",
    "total_inclusions",
    "total_exclusions",
    "parse_confidence",
]

LAB_ALIASES: Dict[str, str] = {
    "Glycosylated Hemoglobin (HbA1c)": "HbA1c",
    "HbA1c":                            "HbA1c",
    "Glucose - Fasting":                "Fasting_Glucose",
    "Fasting Glucose":                  "Fasting_Glucose",
    "Fasting_Glucose":                  "Fasting_Glucose",
    "Creatinine":                       "Creatinine",
    "eGFR":                             "eGFR",
    "BMI":                              "BMI",
    "SGPT (Alanine Transaminase)":      "SGPT",
    "Cholesterol - Total":              "Total_Cholesterol",
    "Cholesterol - HDL":                "HDL",
    "Cholesterol - LDL":                "LDL",
    "Triglycerides":                    "Triglycerides",
    "Vitamin D (25-OH)":                "Vitamin_D",
    "Thyroid Stimulating Hormone -":    "TSH",
}

CRITICAL_LABS: Tuple[str, ...] = ("HbA1c", "Fasting_Glucose", "eGFR", "Creatinine")


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class FeatureVector:
    nct_id:   str
    features: Dict[str, float]

    def to_array(self) -> np.ndarray:
        return np.array(
            [float(self.features.get(n, 0.0)) for n in FEATURE_NAMES],
            dtype=np.float32,
        )


@dataclass
class RankedTrialMatch:
    patient_id:        str
    nct_id:            str
    trial_title:       str
    rule_passed:       bool
    rule_failures:     List[str]
    feature_vector:    Dict[str, float]
    xgboost_score:     float
    final_score:       float
    shap_values:       Dict[str, float]
    shap_top_positive: List[Dict]
    shap_top_negative: List[Dict]
    eligibility_label: str
    confidence:        float
    ranked_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        return {
            "patient_id":        self.patient_id,
            "nct_id":            self.nct_id,
            "trial_title":       self.trial_title,
            "eligibility_label": self.eligibility_label,
            "final_score":       round(float(self.final_score), 2),
            "xgboost_score":     round(float(self.xgboost_score), 4),
            "confidence":        round(float(self.confidence), 4),
            "rule_passed":       bool(self.rule_passed),
            "rule_failures":     self.rule_failures,
            "shap_values":       {
                k: round(float(v), 4)
                for k, v in self.shap_values.items()
            },
            "shap_top_positive": self.shap_top_positive,
            "shap_top_negative": self.shap_top_negative,
            "feature_vector":    {
                k: round(float(v), 4)
                for k, v in self.feature_vector.items()
            },
            "ranked_at":         self.ranked_at,
        }


# ============================================================================
# MOD2 ADAPTER
# ============================================================================

class Mod2Adapter:
    """Reads mod2_output.json and returns (patient_features dict, trials list)."""

    @staticmethod
    def load(path: Path) -> Tuple[Dict[str, Any], List[Dict]]:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        patient = Mod2Adapter._build_patient(data)
        trials  = data.get("parsed_trials", [])
        log.info(f"Patient: {patient['patient_id']}  |  Trials loaded: {len(trials)}")
        return patient, trials

    @staticmethod
    def _build_patient(data: Dict) -> Dict[str, Any]:
        snap = data.get("patient_snapshot", {})
        p: Dict[str, Any] = {
            "patient_id":  snap.get("patient_id", "UNKNOWN"),
            "age":         snap.get("age"),
            "gender":      snap.get("gender"),
            "conditions":  [],
            "medications": [],
            "labs":        {},
        }

        # Load full lab report for actual lab values
        report_path_str = data.get("source_files", {}).get("patient_report", "")
        report_path = Path(report_path_str) if report_path_str else Path("")
        if report_path.exists():
            try:
                with open(report_path, encoding="utf-8") as f:
                    report = json.load(f)
                Mod2Adapter._map_labs(p, report.get("labs", {}))
                log.info(f"Labs mapped: {list(p['labs'].keys())}")
            except Exception as e:
                log.warning(f"Could not read patient report: {e}")
        else:
            log.warning(f"Patient report not found at '{report_path}' — labs will be empty.")

        # Derive eGFR from Creatinine via CKD-EPI if not in report
        if not p.get("eGFR") and p.get("Creatinine"):
            egfr = Mod2Adapter._ckd_epi(
                p["Creatinine"], p.get("age"), p.get("gender")
            )
            if egfr is not None:
                p["eGFR"]         = egfr
                p["labs"]["eGFR"] = egfr
                log.info(f"eGFR derived via CKD-EPI: {egfr}")

        p["conditions"] = Mod2Adapter._infer_conditions(p)
        log.info(f"Conditions inferred: {p['conditions']}")
        return p

    @staticmethod
    def _map_labs(p: Dict, raw_labs: Dict) -> None:
        for raw_key, lab_data in raw_labs.items():
            internal = LAB_ALIASES.get(raw_key)
            if not internal:
                continue
            try:
                val = float(lab_data.get("value", ""))
                p["labs"][internal] = val
                p[internal]         = val
            except (ValueError, TypeError):
                pass

    @staticmethod
    def _ckd_epi(
        cr: float,
        age: Optional[int],
        gender: Optional[str],
    ) -> Optional[float]:
        if cr is None or age is None:
            return None
        try:
            female = (gender or "").lower() == "female"
            kappa  = 0.7 if female else 0.9
            alpha  = -0.241 if female else -0.302
            sex_f  = 1.012 if female else 1.0
            ratio  = float(cr) / kappa
            base   = (ratio ** alpha) if ratio < 1.0 else (ratio ** -1.200)
            return round(142.0 * base * (0.9938 ** float(age)) * sex_f, 1)
        except Exception:
            return None

    @staticmethod
    def _infer_conditions(p: Dict) -> List[str]:
        conds = []
        hba1c = p.get("HbA1c")
        gluc  = p.get("Fasting_Glucose")
        if (hba1c is not None and hba1c >= 6.5) or \
           (gluc  is not None and gluc  >= 126):
            conds += ["Type 2 Diabetes", "Diabetes Mellitus"]
        elif hba1c is not None and 5.7 <= hba1c < 6.5:
            conds.append("Pre-diabetes")
        return conds


# ============================================================================
# RULE-BASED PRE-FILTER
# ============================================================================

class RuleBasedPreFilter:
    """Hard accept/reject before XGBoost scoring."""

    def check(
        self,
        patient: Dict[str, Any],
        trial:   Dict[str, Any],
    ) -> Tuple[bool, List[str]]:
        """Returns (passed: bool, failures: List[str])."""
        failures: List[str] = []

        # 1. Age range
        age      = patient.get("age")
        age_crit = self._incl_val(trial, "age")
        if age is not None and isinstance(age_crit, dict):
            mn = age_crit.get("min")
            mx = age_crit.get("max")
            if mn is not None and age < mn:
                failures.append(f"Age {age} < minimum required {mn}")
            if mx is not None and age > mx:
                failures.append(f"Age {age} > maximum allowed {mx}")

        # 2. Hard exclusions — conditions
        pat_conds = [c.lower() for c in patient.get("conditions", [])]
        pat_meds  = [m.lower() for m in patient.get("medications", [])]

        for exc in trial.get("exclusions", []):
            val = exc.get("value", "")
            if not isinstance(val, str) or not val.strip():
                continue
            fn = exc.get("field_name", "").lower()
            vl = val.lower()

            # Condition exclusion
            if any(vl in c for c in pat_conds):
                failures.append(f"Patient has excluded condition: {val}")
                return False, failures  # hard stop

            # Medication exclusion
            if any(k in fn for k in ("insulin", "medication", "treatment")):
                if any(vl in m for m in pat_meds):
                    failures.append(f"Patient has excluded medication: {val}")
                    return False, failures  # hard stop

        return len(failures) == 0, failures

    @staticmethod
    def _incl_val(trial: Dict, field: str) -> Any:
        for inc in trial.get("inclusions", []):
            if inc.get("field_name") == field:
                return inc.get("value")
        return None


# ============================================================================
# FEATURE ENGINEERING
# ============================================================================

class FeatureEngineer:
    """Builds a 16-dimensional feature vector for each patient-trial pair."""

    def build(
        self,
        patient: Dict[str, Any],
        trial:   Dict[str, Any],
    ) -> FeatureVector:
        f: Dict[str, float] = {}

        # Age features
        age      = patient.get("age")
        age_crit = self._incl_val(trial, "age")
        if age is not None and isinstance(age_crit, dict):
            mn  = float(age_crit.get("min") or 0)
            mx  = float(age_crit.get("max") or 120)
            f["age_in_range"]  = 1.0 if mn <= age <= mx else 0.0
            dist = max(0.0, mn - age) + max(0.0, age - mx)
            f["age_diff_norm"] = dist / max(1.0, mx - mn)
        else:
            f["age_in_range"]  = 0.5
            f["age_diff_norm"] = 0.0

        # Lab range scores
        lab_map = [
            ("HbA1c",           "hba1c_match"),
            ("Fasting_Glucose",  "fasting_glucose_match"),
            ("BMI",             "bmi_match"),
            ("eGFR",            "egfr_match"),
            ("Creatinine",      "creatinine_match"),
        ]
        for lab, feat_key in lab_map:
            f[feat_key] = self._range_score(
                patient.get(lab),
                self._lab_crit(trial, lab),
            )

        # Condition / medication exclusion flags
        f["has_required_condition"]  = self._required_condition(patient, trial)
        f["has_excluded_condition"]  = self._excluded_condition(patient, trial)
        f["has_excluded_medication"] = self._excluded_medication(patient, trial)

        # Missing critical labs (0-4)
        f["missing_critical_labs"] = float(
            sum(1 for lab in CRITICAL_LABS if patient.get(lab) is None)
        )

        # Inclusion / exclusion coverage
        incs = trial.get("inclusions", [])
        excs = trial.get("exclusions", [])

        f["inclusion_coverage"] = (
            sum(1 for inc in incs
                if patient.get(inc.get("field_name")) is not None)
            / max(1, len(incs))
        )
        f["exclusion_safe_rate"] = (
            sum(1 for exc in excs
                if not patient.get(exc.get("field_name")))
            / max(1, len(excs))
        )

        # Trial complexity proxies
        f["total_inclusions"] = float(len(incs))
        f["total_exclusions"] = float(len(excs))
        f["parse_confidence"] = float(trial.get("parse_confidence") or 0.5)

        return FeatureVector(nct_id=trial.get("nct_id", "?"), features=f)

    # ── static helpers ─────────────────────────────────────────────────

    @staticmethod
    def _incl_val(trial: Dict, field: str) -> Any:
        for inc in trial.get("inclusions", []):
            if inc.get("field_name") == field:
                return inc.get("value")
        return None

    @staticmethod
    def _lab_crit(trial: Dict, lab: str) -> Optional[Dict]:
        for inc in trial.get("inclusions", []):
            if inc.get("field_name") == lab:
                v = inc.get("value")
                return v if isinstance(v, dict) else None
        return None

    @staticmethod
    def _range_score(val: Optional[float], crit: Optional[Dict]) -> float:
        if val is None or crit is None:
            return 0.5
        mn = crit.get("min")
        mx = crit.get("max")
        if mn is not None and val < mn:
            return max(0.0, 1.0 - (mn - val) / max(abs(mn), 1e-6))
        if mx is not None and val > mx:
            return max(0.0, 1.0 - (val - mx) / max(abs(mx), 1e-6))
        return 1.0

    @staticmethod
    def _required_condition(patient: Dict, trial: Dict) -> float:
        for inc in trial.get("inclusions", []):
            if "diagnosis" in inc.get("field_name", "").lower():
                req   = str(inc.get("value", "")).lower()
                conds = [c.lower() for c in patient.get("conditions", [])]
                return 1.0 if any(req in c for c in conds) else 0.0
        return 0.5  # not specified → neutral

    @staticmethod
    def _excluded_condition(patient: Dict, trial: Dict) -> float:
        for exc in trial.get("exclusions", []):
            if "condition" not in exc.get("field_name", "").lower():
                continue
            val = str(exc.get("value", "")).lower()
            if any(val in c.lower() for c in patient.get("conditions", [])):
                return 1.0  # patient HAS this excluded condition (bad)
        return 0.0

    @staticmethod
    def _excluded_medication(patient: Dict, trial: Dict) -> float:
        for exc in trial.get("exclusions", []):
            fn = exc.get("field_name", "").lower()
            if not any(k in fn for k in ("insulin", "medication", "treatment")):
                continue
            val = str(exc.get("value", "")).lower()
            if any(val in m.lower() for m in patient.get("medications", [])):
                return 1.0
        return 0.0


# ============================================================================
# XGBOOST TRAINER
# ============================================================================

class XGBoostTrainer:
    """
    Self-supervised XGBoost training on the current patient's trial batch.
    Soft label = 0.8 * rule_passed + 0.2 * inclusion_coverage  (in [0, 1])
    """

    PARAMS: Dict = {
        "objective":        "reg:squarederror",
        "eval_metric":      "rmse",
        "max_depth":        4,
        "eta":              0.1,
        "subsample":        0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 1,
        "seed":             42,
        "verbosity":        0,
    }
    NUM_ROUNDS: int = 100

    def train(
        self,
        fvs:    List[FeatureVector],
        labels: List[float],
    ) -> Tuple[xgb.Booster, xgb.DMatrix]:
        X      = np.stack([fv.to_array() for fv in fvs])          # (N, 16)
        y      = np.array(labels, dtype=np.float32)                # (N,)
        dtrain = xgb.DMatrix(X, label=y, feature_names=FEATURE_NAMES)
        booster = xgb.train(
            self.PARAMS,
            dtrain,
            num_boost_round=self.NUM_ROUNDS,
            verbose_eval=False,
        )
        log.info(f"XGBoost trained — {len(fvs)} trials, {self.NUM_ROUNDS} rounds")
        return booster, dtrain

    @staticmethod
    def predict(booster: xgb.Booster, fvs: List[FeatureVector]) -> np.ndarray:
        X    = np.stack([fv.to_array() for fv in fvs])
        dmat = xgb.DMatrix(X, feature_names=FEATURE_NAMES)
        raw  = booster.predict(dmat)
        return np.clip(raw, 0.0, 1.0).astype(float)


# ============================================================================
# SHAP EXPLAINER
# ============================================================================

class SHAPExplainer:
    """Wraps shap.TreeExplainer and produces per-trial SHAP dicts."""

    def __init__(self, booster: xgb.Booster):
        self.explainer = shap.TreeExplainer(booster)

    def explain(self, fvs: List[FeatureVector]) -> List[Dict[str, float]]:
        X  = np.stack([fv.to_array() for fv in fvs])
        sv = self.explainer.shap_values(
            xgb.DMatrix(X, feature_names=FEATURE_NAMES)
        )                                                   # (N, 16)
        result = []
        for row in sv:
            result.append({
                FEATURE_NAMES[i]: float(row[i])
                for i in range(len(FEATURE_NAMES))
            })
        return result

    @staticmethod
    def top_factors(
        shap_d: Dict[str, float],
        n: int = 5,
    ) -> Tuple[List[Dict], List[Dict]]:
        ranked = sorted(shap_d.items(), key=lambda x: abs(x[1]), reverse=True)
        pos = [
            {"feature": k, "shap_value": round(float(v), 4), "direction": "positive"}
            for k, v in ranked if v > 0
        ][:n]
        neg = [
            {"feature": k, "shap_value": round(float(v), 4), "direction": "negative"}
            for k, v in ranked if v < 0
        ][:n]
        return pos, neg


# ============================================================================
# RANKING AGGREGATOR
# ============================================================================

class RankingAggregator:
    """Orchestrates the full Mod3 pipeline."""

    def __init__(self):
        self.pre_filter = RuleBasedPreFilter()
        self.engineer   = FeatureEngineer()
        self.trainer    = XGBoostTrainer()

    def run(
        self,
        patient: Dict[str, Any],
        trials:  List[Dict[str, Any]],
        top_n:   int = 10,
    ) -> List[RankedTrialMatch]:

        pid = str(patient.get("patient_id", "?"))
        log.info(f"Running pipeline for patient '{pid}' against {len(trials)} trials")

        # ── Step 1: Rule filter + feature vectors ──────────────────────
        rule_results: List[Tuple[bool, List[str]]] = []
        fvs:          List[FeatureVector]           = []
        soft_labels:  List[float]                   = []

        for trial in trials:
            passed, failures = self.pre_filter.check(patient, trial)
            fv               = self.engineer.build(patient, trial)
            rule_results.append((passed, failures))
            fvs.append(fv)

            # Soft label: rule signal + coverage signal
            cov   = fv.features.get("inclusion_coverage", 0.5)
            label = 0.8 * float(passed) + 0.2 * float(cov)
            soft_labels.append(label)

        # ── Step 2: Train XGBoost ───────────────────────────────────────
        booster, _ = self.trainer.train(fvs, soft_labels)
        scores     = XGBoostTrainer.predict(booster, fvs)   # np.ndarray (N,)

        # ── Step 3: SHAP explanations ───────────────────────────────────
        log.info("Computing SHAP values …")
        shap_exp  = SHAPExplainer(booster)
        shap_list = shap_exp.explain(fvs)

        # ── Step 4: Assemble RankedTrialMatch objects ───────────────────
        matches: List[RankedTrialMatch] = []

        for i, trial in enumerate(trials):
            passed, failures = rule_results[i]
            xgb_score        = float(scores[i])
            shap_d           = shap_list[i]

            # Final score — penalise hard-rule failures heavily
            final = xgb_score * 100.0
            if not passed:
                final *= 0.40

            # Eligibility label
            if final >= 65 and passed:
                elabel = "Eligible"
            elif final >= 40:
                elabel = "Likely Eligible"
            else:
                elabel = "Ineligible"

            shap_pos, shap_neg = SHAPExplainer.top_factors(shap_d)

            matches.append(RankedTrialMatch(
                patient_id        = pid,
                nct_id            = str(trial.get("nct_id", "?")),
                trial_title       = str(trial.get("title", "")),
                rule_passed       = bool(passed),
                rule_failures     = list(failures),
                feature_vector    = dict(fvs[i].features),
                xgboost_score     = xgb_score,
                final_score       = round(final, 2),
                shap_values       = shap_d,
                shap_top_positive = shap_pos,
                shap_top_negative = shap_neg,
                eligibility_label = elabel,
                confidence        = float(trial.get("parse_confidence") or 0.5),
            ))

        matches.sort(key=lambda m: m.final_score, reverse=True)
        if matches:
            log.info(
                f"Top match → {matches[0].nct_id} | "
                f"score={matches[0].final_score:.1f} | "
                f"label={matches[0].eligibility_label}"
            )
        return matches[:top_n]


# ============================================================================
# OUTPUT WRITER
# ============================================================================

def save_output(
    ranked:  List[RankedTrialMatch],
    patient: Dict[str, Any],
    path:    Path,
) -> None:
    """Serialise results to JSON with full error reporting."""

    # Ensure output directory exists
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log.error(f"Cannot create output directory '{path.parent}': {e}")
        raise

    payload = {
        "generated_at":        datetime.now().isoformat(),
        "mod2_source":         str(MOD2_OUTPUT_PATH),
        "patient_id":          patient.get("patient_id"),
        "age":                 patient.get("age"),
        "gender":              patient.get("gender"),
        "conditions_inferred": patient.get("conditions", []),
        "labs_used": {
            k: patient[k]
            for k in ("HbA1c", "Fasting_Glucose", "BMI", "eGFR", "Creatinine")
            if k in patient
        },
        "total_trials_scored": len(ranked),
        "ranked_trials":       [m.to_dict() for m in ranked],
    }

    # Write with SafeEncoder to handle any residual numpy types
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False, cls=SafeEncoder)
        log.info(f"Output saved → {path}  ({os.path.getsize(path):,} bytes)")
    except Exception as e:
        log.error(f"Failed to write output file: {e}")
        traceback.print_exc()
        raise


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":

    # Validate input
    if not MOD2_OUTPUT_PATH.exists():
        raise FileNotFoundError(
            f"\nMod2 output not found:\n  {MOD2_OUTPUT_PATH}\n"
            "Run mod2_criteria_parser.py first.\n"
        )

    # Load
    patient, trials = Mod2Adapter.load(MOD2_OUTPUT_PATH)

    if not trials:
        raise ValueError("No parsed_trials found in mod2_output.json.")

    # Run pipeline
    aggregator = RankingAggregator()
    ranked     = aggregator.run(patient, trials, top_n=len(trials))

    # Save
    save_output(ranked, patient, OUTPUT_PATH)
    log.info("Module 3 complete.")