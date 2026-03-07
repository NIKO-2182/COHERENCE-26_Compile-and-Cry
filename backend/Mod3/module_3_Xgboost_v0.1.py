"""
Module 3: Patient Matching with Rule-Based Pre-Filter & XGBoost + SHAP
=======================================================================

Reads directly from Mod2 output:
    MOD2_OUTPUT_PATH  →  mod2_output.json
                         (contains patient_snapshot + parsed_trials)

Saves final ranked matches to:
    OUTPUT_PATH       →  mod3_output.json

Flow:
  Mod2 JSON → Patient Features + Parsed Trials
            → Rule Pre-Filter  (hard rejection)
            → Feature Engineering (16-dim vector)
            → XGBoost Score  (or heuristic fallback)
            → SHAP Explanations
            → Ranked Output JSON
"""

import json
import logging
import math
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False

logger = logging.getLogger("Module3")


# ============================================================================
# ★  FILE PATHS  ★
# ============================================================================

MOD2_OUTPUT_PATH: Path = Path(
    r"D:\C&C\COHERENCE-26_Compile-and-Cry\backend\Mod2\mod2_output.json"
)

# XGBoost model (optional – falls back to heuristic if not found)
XGBOOST_MODEL_PATH: Optional[str] = None   # e.g. "models/trial_matcher.json"

OUTPUT_PATH: Path = Path(
    r"D:\C&C\COHERENCE-26_Compile-and-Cry\backend\Mod3\mod3_output.json"
)


# ============================================================================
# CONSTANTS
# ============================================================================

FEATURE_NAMES = [
    "age_diff",
    "hba1c_match",
    "fasting_glucose_match",
    "bmi_match",
    "egfr_match",
    "creatinine_match",
    "has_required_condition",
    "has_excluded_condition",
    "has_excluded_medication",
    "missing_lab_count",
    "missing_critical_labs",
    "condition_similarity",
    "medication_similarity",
    "inclusion_criteria_coverage",
    "exclusion_criteria_coverage",
    "geographic_distance",
]

# Lab name aliases: maps extractor keys → internal keys
LAB_ALIASES: Dict[str, str] = {
    # HbA1c
    "Glycosylated Hemoglobin (HbA1c)": "HbA1c",
    "HbA1c": "HbA1c",
    # Fasting glucose
    "Glucose - Fasting": "Fasting_Glucose",
    "Fasting Glucose": "Fasting_Glucose",
    "Fasting_Glucose": "Fasting_Glucose",
    # Creatinine
    "Creatinine": "Creatinine",
    # eGFR — rarely present in basic panels; derive from creatinine if absent
    "eGFR": "eGFR",
    # BMI — not a direct lab but sometimes included
    "BMI": "BMI",
    # Extras useful for scoring
    "SGPT (Alanine Transaminase)": "SGPT",
    "Cholesterol - Total": "Total_Cholesterol",
    "Cholesterol - HDL": "HDL",
    "Cholesterol - LDL": "LDL",
    "Triglycerides": "Triglycerides",
    "Vitamin D (25-OH)": "Vitamin_D",
    "Thyroid Stimulating Hormone -": "TSH",
}


# ============================================================================
# LOGGING
# ============================================================================

def _setup_logging(level: int = logging.INFO) -> None:
    if logger.handlers:
        return
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(ch)
    logger.setLevel(level)


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class FeatureVector:
    patient_id: str
    nct_id: str
    features: Dict[str, float]

    def to_array(self) -> np.ndarray:
        return np.array([self.features.get(n, 0.0) for n in FEATURE_NAMES],
                        dtype=np.float32)


@dataclass
class XGBoostPrediction:
    patient_id: str
    nct_id: str
    eligibility_score: float
    prediction_confidence: float
    shap_values: Dict[str, float] = field(default_factory=dict)
    top_positive_features: List[Tuple[str, float]] = field(default_factory=list)
    top_negative_features: List[Tuple[str, float]] = field(default_factory=list)


@dataclass
class RankedTrialMatch:
    patient_id: str
    nct_id: str
    trial_title: str
    rule_prefilter_passed: bool
    rule_prefilter_reason: str
    base_match_score: float
    xgboost_score: float
    final_score: float
    distance_km: Optional[float] = None
    geographic_penalty: float = 1.0
    rule_based_failures: List[str] = field(default_factory=list)
    shap_explanations: Dict[str, float] = field(default_factory=dict)
    top_factors: List[str] = field(default_factory=list)
    confidence: float = 0.8
    ranked_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        return {
            "patient_id": self.patient_id,
            "nct_id": self.nct_id,
            "trial_title": self.trial_title,
            "rule_prefilter_passed": self.rule_prefilter_passed,
            "rule_prefilter_reason": self.rule_prefilter_reason,
            "base_match_score": round(self.base_match_score, 2),
            "xgboost_score": round(self.xgboost_score, 3),
            "final_score": round(self.final_score, 2),
            "distance_km": self.distance_km,
            "geographic_penalty": round(self.geographic_penalty, 3),
            "rule_based_failures": self.rule_based_failures,
            "shap_explanations": {k: round(v, 4)
                                  for k, v in self.shap_explanations.items()},
            "top_factors": self.top_factors,
            "confidence": round(self.confidence, 2),
            "ranked_at": self.ranked_at,
        }


# ============================================================================
# MOD2 → MOD3 DATA ADAPTER
# ============================================================================

class Mod2Adapter:
    """
    Converts Mod2 JSON output into the patient_features dict and
    trials list that Mod3 components expect.
    """

    # ------------------------------------------------------------------
    # Patient features
    # ------------------------------------------------------------------

    @staticmethod
    def extract_patient_features(mod2_data: Dict) -> Dict[str, Any]:
        """
        Build a patient_features dict from:
          mod2_data["patient_snapshot"]   – demographics
          mod2_data["source_files"]["patient_report"]  – full lab JSON path
        """
        snap = mod2_data.get("patient_snapshot", {})

        features: Dict[str, Any] = {
            "patient_id":  snap.get("patient_id", "UNKNOWN"),
            "age":         snap.get("age"),
            "gender":      snap.get("gender"),
            "conditions":  [],    # populated below
            "medications": [],    # not present in basic lab report
            "labs":        {},
        }

        # Try to load the full patient lab JSON for actual lab values
        report_path = Path(
            mod2_data.get("source_files", {}).get("patient_report", "")
        )
        if report_path.exists():
            try:
                with open(report_path, encoding="utf-8") as f:
                    full_report = json.load(f)
                Mod2Adapter._populate_labs(features, full_report.get("labs", {}))
                Mod2Adapter._infer_conditions(features)
            except Exception as e:
                logger.warning(f"Could not load full patient report: {e}")
        else:
            logger.warning(
                f"Full patient report not found at {report_path}. "
                "Lab values will be missing."
            )

        return features

    @staticmethod
    def _populate_labs(features: Dict, raw_labs: Dict) -> None:
        """Map raw extractor lab keys to internal names."""
        labs: Dict[str, float] = {}
        for raw_key, lab_data in raw_labs.items():
            internal_key = LAB_ALIASES.get(raw_key)
            if internal_key is None:
                continue
            try:
                val = float(lab_data.get("value", ""))
                labs[internal_key] = val
            except (ValueError, TypeError):
                pass

        # Flatten into features dict (top-level keys for quick access)
        features["labs"] = labs
        for k, v in labs.items():
            features[k] = v

        # Derived: eGFR from CKD-EPI if missing (approximate, needs age+gender)
        if "eGFR" not in features and "Creatinine" in features:
            features["eGFR"] = Mod2Adapter._estimate_egfr(
                features["Creatinine"],
                features.get("age"),
                features.get("gender"),
            )

    @staticmethod
    def _estimate_egfr(creatinine: float,
                       age: Optional[int],
                       gender: Optional[str]) -> Optional[float]:
        """Rough CKD-EPI eGFR estimate (not for clinical use)."""
        if creatinine is None or age is None:
            return None
        try:
            cr = float(creatinine)
            a  = float(age)
            kappa = 0.7 if (gender or "").lower() == "female" else 0.9
            alpha = -0.241 if (gender or "").lower() == "female" else -0.302
            sex_factor = 1.012 if (gender or "").lower() == "female" else 1.0
            ratio = cr / kappa
            if ratio < 1:
                egfr = 142 * (ratio ** alpha) * (0.9938 ** a) * sex_factor
            else:
                egfr = 142 * (ratio ** -1.200) * (0.9938 ** a) * sex_factor
            return round(egfr, 1)
        except Exception:
            return None

    @staticmethod
    def _infer_conditions(features: Dict) -> None:
        """
        Infer likely conditions from lab values so the rule-based
        pre-filter has something to work with.
        """
        conditions = []
        labs = features.get("labs", {})

        hba1c   = labs.get("HbA1c")
        glucose = labs.get("Fasting_Glucose")

        if (hba1c and hba1c >= 6.5) or (glucose and glucose >= 126):
            conditions.append("Type 2 Diabetes")
            conditions.append("Diabetes Mellitus")

        if hba1c and 5.7 <= hba1c < 6.5:
            conditions.append("Pre-diabetes")

        features["conditions"] = conditions

    # ------------------------------------------------------------------
    # Trials
    # ------------------------------------------------------------------

    @staticmethod
    def extract_trials(mod2_data: Dict) -> List[Dict]:
        """
        Return the parsed_trials list from Mod2, already in the format
        Mod3 expects (nct_id, title, inclusions, exclusions).
        """
        return mod2_data.get("parsed_trials", [])


# ============================================================================
# RULE-BASED PRE-FILTER
# ============================================================================

class RuleBasedPreFilter:

    def check_patient_trial(
        self,
        patient: Dict[str, Any],
        trial: Dict[str, Any],
    ) -> Tuple[bool, List[str], float]:
        """Returns (passed, failed_criteria, confidence)."""
        failed: List[str] = []
        confidence = 1.0

        # ── Age ────────────────────────────────────────────────────────
        age      = patient.get("age")
        age_crit = self._get_inclusion_value(trial, "age")
        if age is not None and age_crit:
            if not self._in_range(age, age_crit):
                failed.append(f"Age {age} outside range {age_crit}")

        # ── Excluded conditions ────────────────────────────────────────
        for exc in trial.get("exclusions", []):
            fn  = exc.get("field_name", "")
            val = exc.get("value", "")
            if not isinstance(val, str):
                continue
            patient_conds = [c.lower() for c in patient.get("conditions", [])]
            if any(val.lower() in c for c in patient_conds):
                failed.append(f"Has excluded condition: {val}")
                return False, failed, 0.0   # hard stop

        # ── Excluded medications ───────────────────────────────────────
        for exc in trial.get("exclusions", []):
            fn  = exc.get("field_name", "")
            val = exc.get("value", "")
            if "insulin" not in fn.lower() and "medication" not in fn.lower():
                continue
            if not isinstance(val, str):
                continue
            patient_meds = [m.lower() for m in patient.get("medications", [])]
            if any(val.lower() in m for m in patient_meds):
                failed.append(f"Has excluded medication: {val}")
                return False, failed, 0.0

        # ── Required diagnosis ─────────────────────────────────────────
        req_diag = self._get_inclusion_value(trial, "required_diagnosis")
        if req_diag:
            patient_conds = [c.lower() for c in patient.get("conditions", [])]
            req_str = req_diag if isinstance(req_diag, str) else str(req_diag)
            if not any(req_str.lower() in c for c in patient_conds):
                failed.append(f"Missing required diagnosis: {req_diag}")
                confidence = 0.7

        # ── Critical labs ──────────────────────────────────────────────
        for lab in ("HbA1c", "eGFR", "Fasting_Glucose"):
            if patient.get(lab) is None:
                confidence -= 0.05

        confidence = max(0.0, confidence)
        return len(failed) == 0, failed, confidence

    # helpers
    @staticmethod
    def _get_inclusion_value(trial: Dict, field: str) -> Any:
        for inc in trial.get("inclusions", []):
            if inc.get("field_name") == field:
                return inc.get("value")
        return None

    @staticmethod
    def _in_range(value: float, criterion: Any) -> bool:
        if not isinstance(criterion, dict):
            return True
        mn = criterion.get("min")
        mx = criterion.get("max")
        if mn is not None and value < mn:
            return False
        if mx is not None and value > mx:
            return False
        return True


# ============================================================================
# FEATURE ENGINEERING
# ============================================================================

class FeatureEngineer:

    def create_feature_vector(
        self,
        patient: Dict[str, Any],
        trial: Dict[str, Any],
        patient_loc: Optional[Tuple[float, float]] = None,
        trial_loc: Optional[Tuple[float, float]] = None,
    ) -> FeatureVector:

        f: Dict[str, float] = {}

        # Age diff
        age      = patient.get("age")
        age_min  = self._crit_val(trial, "age", "min")
        f["age_diff"] = float(age - age_min) if age and age_min else 0.0

        # Lab matches
        for lab, feat_name in (
            ("HbA1c",          "hba1c_match"),
            ("Fasting_Glucose", "fasting_glucose_match"),
            ("BMI",            "bmi_match"),
            ("eGFR",           "egfr_match"),
            ("Creatinine",     "creatinine_match"),
        ):
            pat_val  = patient.get(lab)
            crit_val = self._lab_criterion(trial, lab)
            if pat_val is None or crit_val is None:
                f[feat_name] = 0.5
            else:
                f[feat_name] = self._score_range(pat_val, crit_val)

        # Condition / medication flags
        f["has_required_condition"]  = self._has_required_condition(patient, trial)
        f["has_excluded_condition"]  = self._has_excluded_condition(patient, trial)
        f["has_excluded_medication"] = self._has_excluded_medication(patient, trial)

        # Missing data
        all_labs      = ("HbA1c","Fasting_Glucose","BMI","eGFR","Creatinine")
        critical_labs = ("HbA1c","eGFR","Fasting_Glucose")
        f["missing_lab_count"]    = float(sum(patient.get(l) is None for l in all_labs))
        f["missing_critical_labs"]= float(sum(patient.get(l) is None for l in critical_labs))

        # Similarity
        f["condition_similarity"]  = self._jaccard(
            patient.get("conditions", []),
            self._trial_conditions(trial),
        )
        f["medication_similarity"] = self._jaccard(
            patient.get("medications", []),
            self._trial_medications(trial),
        )

        # Coverage
        f["inclusion_criteria_coverage"] = self._inclusion_coverage(patient, trial)
        f["exclusion_criteria_coverage"] = self._exclusion_coverage(patient, trial)

        # Geographic distance
        dist = 0.0
        if patient_loc and trial_loc and None not in trial_loc:
            dist = self._haversine(*patient_loc, *trial_loc)
        f["geographic_distance"] = dist

        return FeatureVector(
            patient_id=str(patient.get("patient_id", "?")),
            nct_id=str(trial.get("nct_id", "?")),
            features=f,
        )

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _crit_val(trial: Dict, field: str, key: str) -> Optional[float]:
        for inc in trial.get("inclusions", []):
            if inc.get("field_name") == field:
                v = inc.get("value", {})
                if isinstance(v, dict):
                    return v.get(key)
        return None

    @staticmethod
    def _lab_criterion(trial: Dict, lab: str) -> Optional[Dict]:
        for inc in trial.get("inclusions", []):
            if inc.get("field_name") == lab:
                return inc.get("value")
        return None

    @staticmethod
    def _score_range(value: float, criterion: Any) -> float:
        if not isinstance(criterion, dict):
            return 0.5
        mn = criterion.get("min")
        mx = criterion.get("max")
        if mn and value < mn:
            return max(0.0, 1.0 - (mn - value) / mn * 0.5)
        if mx and value > mx:
            return max(0.0, 1.0 - (value - mx) / mx * 0.5)
        return 1.0

    @staticmethod
    def _has_required_condition(patient: Dict, trial: Dict) -> float:
        for inc in trial.get("inclusions", []):
            if "diagnosis" in inc.get("field_name", "").lower():
                req = inc.get("value", "")
                if not isinstance(req, str):
                    req = str(req)
                conds = [c.lower() for c in patient.get("conditions", [])]
                return 1.0 if any(req.lower() in c for c in conds) else 0.0
        return 0.5

    @staticmethod
    def _has_excluded_condition(patient: Dict, trial: Dict) -> float:
        for exc in trial.get("exclusions", []):
            fn  = exc.get("field_name", "")
            val = exc.get("value", "")
            if "condition" not in fn.lower():
                continue
            if not isinstance(val, str):
                continue
            conds = [c.lower() for c in patient.get("conditions", [])]
            if any(val.lower() in c for c in conds):
                return 0.0
        return 1.0

    @staticmethod
    def _has_excluded_medication(patient: Dict, trial: Dict) -> float:
        for exc in trial.get("exclusions", []):
            fn  = exc.get("field_name", "")
            val = exc.get("value", "")
            if not any(k in fn.lower() for k in ("insulin","medication","treatment")):
                continue
            if not isinstance(val, str):
                continue
            meds = [m.lower() for m in patient.get("medications", [])]
            if any(val.lower() in m for m in meds):
                return 0.0
        return 1.0

    @staticmethod
    def _jaccard(list1: List[str], list2: List[str]) -> float:
        if not list1 and not list2:
            return 1.0
        if not list1 or not list2:
            return 0.0
        s1 = {s.lower() for s in list1}
        s2 = {s.lower() for s in list2}
        return len(s1 & s2) / len(s1 | s2)

    @staticmethod
    def _trial_conditions(trial: Dict) -> List[str]:
        out = []
        for inc in trial.get("inclusions", []):
            fn = inc.get("field_name", "")
            if "condition" in fn or "diagnosis" in fn:
                v = inc.get("value", "")
                out.append(v if isinstance(v, str) else str(v))
        return out

    @staticmethod
    def _trial_medications(trial: Dict) -> List[str]:
        out = []
        for inc in trial.get("inclusions", []):
            fn = inc.get("field_name", "")
            if "medication" in fn or "treatment" in fn:
                v = inc.get("value", "")
                out.append(v if isinstance(v, str) else str(v))
        return out

    @staticmethod
    def _inclusion_coverage(patient: Dict, trial: Dict) -> float:
        incs = trial.get("inclusions", [])
        if not incs:
            return 1.0
        met = sum(1 for inc in incs if patient.get(inc.get("field_name")) is not None)
        return met / len(incs)

    @staticmethod
    def _exclusion_coverage(patient: Dict, trial: Dict) -> float:
        excs = trial.get("exclusions", [])
        if not excs:
            return 1.0
        safe = sum(
            1 for exc in excs
            if not patient.get(exc.get("field_name"))
        )
        return safe / len(excs)

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371.0
        φ1, φ2 = math.radians(lat1), math.radians(lat2)
        dφ = math.radians(lat2 - lat1)
        dλ = math.radians(lon2 - lon1)
        a  = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
        return R * 2 * math.asin(math.sqrt(a))


# ============================================================================
# XGBOOST INFERENCE
# ============================================================================

class XGBoostInference:

    def __init__(self, model_path: Optional[str] = None):
        self.model    = None
        self.explainer = None

        if model_path and XGBOOST_AVAILABLE:
            try:
                self.model = xgb.Booster()
                self.model.load_model(model_path)
                logger.info(f"XGBoost model loaded from {model_path}")
                if SHAP_AVAILABLE:
                    self.explainer = shap.TreeExplainer(self.model)
            except Exception as e:
                logger.warning(f"Could not load XGBoost model: {e}")
        else:
            mode = "heuristic fallback" if not XGBOOST_AVAILABLE else "no model path"
            logger.info(f"XGBoost running in {mode} mode")

    def predict(self, fv: FeatureVector) -> XGBoostPrediction:
        if self.model is None:
            return self._heuristic(fv)

        try:
            X       = fv.to_array().reshape(1, -1)
            dmat    = xgb.DMatrix(X, feature_names=FEATURE_NAMES)
            score   = float(self.model.predict(dmat)[0])
            shap_d  = self._shap(dmat) if self.explainer else {}
            pos, neg = self._top_features(shap_d)
            return XGBoostPrediction(
                patient_id=fv.patient_id, nct_id=fv.nct_id,
                eligibility_score=min(1.0, max(0.0, score)),
                prediction_confidence=0.9,
                shap_values=shap_d,
                top_positive_features=pos,
                top_negative_features=neg,
            )
        except Exception as e:
            logger.error(f"XGBoost predict error: {e}")
            return self._heuristic(fv)

    def _heuristic(self, fv: FeatureVector) -> XGBoostPrediction:
        f = fv.features
        base = np.mean([
            f.get("hba1c_match",          0.5),
            f.get("fasting_glucose_match", 0.5),
            f.get("bmi_match",             0.5),
            f.get("egfr_match",            0.5),
            f.get("has_required_condition",0.5),
        ])
        base *= (1.0 - f.get("has_excluded_condition",  0.0) * 0.5)
        base *= (1.0 - f.get("has_excluded_medication", 0.0) * 0.5)
        base  = max(0.0, base - f.get("missing_critical_labs", 0) * 0.05)

        # Lightweight SHAP proxy: contribution = feature * weight
        weights = {
            "hba1c_match": 0.25, "fasting_glucose_match": 0.20,
            "egfr_match": 0.15,  "has_required_condition": 0.15,
            "has_excluded_condition": -0.10, "has_excluded_medication": -0.10,
            "missing_critical_labs": -0.05,
        }
        shap_d = {k: round(f.get(k, 0.0) * w, 4) for k, w in weights.items()}
        pos, neg = self._top_features(shap_d)

        return XGBoostPrediction(
            patient_id=fv.patient_id, nct_id=fv.nct_id,
            eligibility_score=float(min(1.0, max(0.0, base))),
            prediction_confidence=0.6,
            shap_values=shap_d,
            top_positive_features=pos,
            top_negative_features=neg,
        )

    def _shap(self, dmat: "xgb.DMatrix") -> Dict[str, float]:
        try:
            vals = self.explainer.shap_values(dmat)
            return {FEATURE_NAMES[i]: float(vals[0][i]) for i in range(len(FEATURE_NAMES))}
        except Exception:
            return {}

    @staticmethod
    def _top_features(shap_d: Dict[str, float], n: int = 3):
        ranked = sorted(shap_d.items(), key=lambda x: abs(x[1]), reverse=True)
        pos = [(k, v) for k, v in ranked[:n] if v > 0]
        neg = [(k, v) for k, v in ranked[:n] if v < 0]
        return pos, neg


# ============================================================================
# RANKING AGGREGATOR
# ============================================================================

class RankingAggregator:

    def __init__(self, model_path: Optional[str] = None):
        self.prefilter  = RuleBasedPreFilter()
        self.engineer   = FeatureEngineer()
        self.xgb_model  = XGBoostInference(model_path)

    def rank_trials(
        self,
        patient: Dict[str, Any],
        trials: List[Dict[str, Any]],
        patient_loc: Optional[Tuple[float, float]] = None,
        top_n: int = 10,
    ) -> List[RankedTrialMatch]:

        pid = str(patient.get("patient_id", "?"))
        logger.info(f"Ranking {len(trials)} trials for patient {pid}")
        matches: List[RankedTrialMatch] = []

        for trial in trials:
            try:
                # 1. Pre-filter
                passed, failures, conf = self.prefilter.check_patient_trial(patient, trial)

                # 2. Feature vector
                trial_loc = None  # trials from Mod2 don't carry GPS; extend here if needed
                fv  = self.engineer.create_feature_vector(patient, trial, patient_loc, trial_loc)

                # 3. XGBoost / heuristic
                pred = self.xgb_model.predict(fv)

                # 4. Combine scores
                base  = float(np.mean(list(fv.features.values())[:10])) * 100
                xgb100 = pred.eligibility_score * 100
                final  = (base * 0.6 + xgb100 * 0.4) if passed else xgb100 * 0.5

                # 5. Geo penalty
                dist = fv.features.get("geographic_distance", 0.0)
                geo  = max(0.5, 1.0 - max(0.0, dist - 100) / 1000) if dist > 100 else 1.0
                final *= geo

                # 6. Format top factors
                top_factors = (
                    [f"✓ {k} (+{v:.3f})" for k, v in pred.top_positive_features[:3]] +
                    [f"✗ {k} ({v:.3f})"  for k, v in pred.top_negative_features[:2]]
                )

                matches.append(RankedTrialMatch(
                    patient_id=pid,
                    nct_id=trial.get("nct_id", "?"),
                    trial_title=trial.get("title", ""),
                    rule_prefilter_passed=passed,
                    rule_prefilter_reason="Passed rule check" if passed else "Failed hard criteria",
                    base_match_score=base,
                    xgboost_score=pred.eligibility_score,
                    final_score=final,
                    distance_km=dist if dist > 0 else None,
                    geographic_penalty=geo,
                    rule_based_failures=failures,
                    shap_explanations=pred.shap_values,
                    top_factors=top_factors,
                    confidence=pred.prediction_confidence,
                ))

            except Exception as e:
                logger.error(f"Error scoring {trial.get('nct_id', '?')}: {e}")

        matches.sort(key=lambda m: m.final_score, reverse=True)
        logger.info(f"✓ Top score: {matches[0].final_score:.1f}" if matches else "No matches")
        return matches[:top_n]


# ============================================================================
# SAVE OUTPUT
# ============================================================================

def save_mod3_output(
    ranked: List[RankedTrialMatch],
    patient: Dict,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at":  datetime.now().isoformat(),
        "mod2_source":   str(MOD2_OUTPUT_PATH),
        "patient_id":    patient.get("patient_id"),
        "age":           patient.get("age"),
        "gender":        patient.get("gender"),
        "conditions":    patient.get("conditions", []),
        "labs_used":     {k: v for k, v in patient.items()
                         if k in ("HbA1c","Fasting_Glucose","BMI","eGFR","Creatinine")},
        "top_n_results": len(ranked),
        "ranked_trials": [m.to_dict() for m in ranked],
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    logger.info(f"✓ Mod3 output saved → {output_path}")


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    _setup_logging()

    print("\n" + "=" * 70)
    print("MODULE 3  |  Patient–Trial Matching  (XGBoost + SHAP)")
    print("=" * 70)

    # ── 1. Load Mod2 output ─────────────────────────────────────────────
    print(f"\n[1/4] Loading Mod2 output …\n      {MOD2_OUTPUT_PATH}")
    if not MOD2_OUTPUT_PATH.exists():
        raise FileNotFoundError(
            f"Mod2 output not found at {MOD2_OUTPUT_PATH}. "
            "Run mod2_criteria_parser.py first."
        )
    with open(MOD2_OUTPUT_PATH, encoding="utf-8") as f:
        mod2_data = json.load(f)

    # ── 2. Adapt to Mod3 format ─────────────────────────────────────────
    print("\n[2/4] Extracting patient features and trials …")
    patient_features = Mod2Adapter.extract_patient_features(mod2_data)
    trials           = Mod2Adapter.extract_trials(mod2_data)

    print(f"      Patient : {patient_features['patient_id']}  "
          f"| Age {patient_features.get('age', '?')}  "
          f"| {patient_features.get('gender', '?')}")
    print(f"      Labs    : {list(patient_features.get('labs', {}).keys())}")
    print(f"      Conditions inferred: {patient_features.get('conditions', [])}")
    print(f"      Trials  : {len(trials)}")

    # ── 3. Rank ─────────────────────────────────────────────────────────
    print(f"\n[3/4] Ranking trials …")
    aggregator = RankingAggregator(model_path=XGBOOST_MODEL_PATH)
    ranked     = aggregator.rank_trials(patient_features, trials, top_n=10)

    # ── 4. Save ─────────────────────────────────────────────────────────
    print(f"\n[4/4] Saving output …\n      {OUTPUT_PATH}")
    save_mod3_output(ranked, patient_features, OUTPUT_PATH)

    # ── Print results ───────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print(f"  TOP {len(ranked)} MATCHED TRIALS")
    print("─" * 70)
    for i, m in enumerate(ranked, 1):
        status = "✓" if m.rule_prefilter_passed else "✗"
        print(f"\n  {i:2d}. [{status}] {m.nct_id}")
        print(f"       {m.trial_title[:65]}")
        print(f"       Base={m.base_match_score:.1f}  XGB={m.xgboost_score:.3f}  "
              f"Final={m.final_score:.1f}  conf={m.confidence:.0%}")
        if m.rule_based_failures:
            for fail in m.rule_based_failures:
                print(f"       ⚠  {fail}")
        if m.top_factors:
            for tf in m.top_factors[:3]:
                print(f"       {tf}")
        if m.shap_explanations:
            top_shap = sorted(m.shap_explanations.items(),
                              key=lambda x: abs(x[1]), reverse=True)[:3]
            shap_str = "  |  ".join(f"{k}: {v:+.3f}" for k, v in top_shap)
            print(f"       SHAP → {shap_str}")

    print("\n" + "─" * 70)
    print(f"  Output saved: {OUTPUT_PATH}")
    print("─" * 70 + "\n")