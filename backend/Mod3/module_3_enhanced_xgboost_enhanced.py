"""
Module 3 Enhanced: Patient Matching with Rule-Based Pre-Filter & XGBoost Integration
====================================================================================

Enhanced features:
1. Rule-based pre-filter (fast rejection for hard criteria)
2. Feature vector generation for XGBoost
3. XGBoost model inference
4. SHAP explanations
5. Ranking & output aggregation

Flow:
  Patient + Trial → Rule Pre-Filter (fast) → Pass/Fail
                 → Feature Engineering → Vector
                 → XGBoost Score → SHAP Explanations
                 → Ranking & Output
"""

import logging
import numpy as np
import json
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import math
from pathlib import Path

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

logger = logging.getLogger('Module3Enhanced')


# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================

class PreFilterResult(Enum):
    """Result of rule-based pre-filter"""
    PASSED = "Passed"
    FAILED = "Failed"
    CONDITIONAL = "Conditional"  # Passed but low confidence


# Hard criteria thresholds
HARD_CRITERIA_RULES = {
    "age": {"weight": 1.0, "strict": True},              # Must be within range
    "exclusion_conditions": {"weight": 1.0, "strict": True},  # Cannot have
    "exclusion_medications": {"weight": 1.0, "strict": True}, # Cannot have
    "required_diagnosis": {"weight": 0.8, "strict": False},   # Should have
}

# Feature importance constants
FEATURE_NAMES = [
    "age_diff",                    # Patient age - criterion min age
    "hba1c_match",                 # HbA1c within range (0-1)
    "glucose_match",               # Fasting glucose within range
    "bmi_match",                   # BMI within range
    "egfr_match",                  # eGFR within range
    "creatinine_match",            # Creatinine within range
    "has_required_condition",      # Has required diagnosis (0-1)
    "has_excluded_condition",      # Has excluded condition (0-1, inverted)
    "has_excluded_medication",     # Has excluded medication (0-1, inverted)
    "missing_lab_count",           # Number of missing labs
    "missing_critical_labs",       # Missing critical labs (HbA1c, eGFR)
    "condition_similarity",        # Condition overlap (0-1)
    "medication_similarity",       # Medication overlap (0-1)
    "inclusion_criteria_coverage", # % of inclusions met
    "exclusion_criteria_coverage", # % of exclusions met
    "geographic_distance",         # Haversine distance (km)
]


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class PreFilterResult:
    """Result of rule-based pre-filter"""
    passed: bool
    reason: str
    failed_criteria: List[str] = field(default_factory=list)
    confidence: float = 1.0  # 1.0 = certain, 0.5 = borderline


@dataclass
class FeatureVector:
    """Feature vector for XGBoost"""
    patient_id: str
    nct_id: str
    features: Dict[str, float]  # {feature_name: value}
    feature_array: np.ndarray = None  # Dense array for XGBoost
    
    def to_array(self) -> np.ndarray:
        """Convert features dict to ordered numpy array"""
        if self.feature_array is not None:
            return self.feature_array
        
        return np.array([
            self.features.get(fname, 0.0)
            for fname in FEATURE_NAMES
        ])


@dataclass
class XGBoostPrediction:
    """XGBoost model prediction"""
    patient_id: str
    nct_id: str
    eligibility_score: float  # 0-1
    prediction_confidence: float  # 0-1
    feature_importance: Dict[str, float] = field(default_factory=dict)
    shap_values: Dict[str, float] = field(default_factory=dict)
    top_positive_features: List[Tuple[str, float]] = field(default_factory=list)
    top_negative_features: List[Tuple[str, float]] = field(default_factory=list)


@dataclass
class RankedTrialMatch:
    """Trial match with all information for ranking"""
    patient_id: str
    nct_id: str
    trial_title: str
    
    # Scores from different stages
    rule_prefilter_passed: bool
    rule_prefilter_reason: str
    
    # Base matching score (0-100)
    base_match_score: float
    
    # XGBoost score (0-1)
    xgboost_score: float
    
    # Final score (combination)
    final_score: float  # 0-100
    
    # Geographic penalty
    distance_km: Optional[float] = None
    geographic_penalty: float = 1.0  # 1.0 = no penalty
    
    # Explanations
    rule_based_failures: List[str] = field(default_factory=list)
    shap_explanations: Dict[str, float] = field(default_factory=dict)
    top_factors: List[str] = field(default_factory=list)
    
    # Recommendations
    recommendations: List[str] = field(default_factory=list)
    
    # Metadata
    ranked_at: str = field(default_factory=lambda: datetime.now().isoformat())
    confidence: float = 0.8
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
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
            "shap_explanations": {k: round(v, 3) for k, v in self.shap_explanations.items()},
            "top_factors": self.top_factors,
            "recommendations": self.recommendations,
            "confidence": round(self.confidence, 2)
        }


# ============================================================================
# RULE-BASED PRE-FILTER
# ============================================================================

class RuleBasedPreFilter:
    """Fast rejection filter using hard criteria"""
    
    def __init__(self):
        """Initialize pre-filter"""
        logger.info("RuleBasedPreFilter initialized")
    
    def check_patient_trial(
        self,
        patient_features: Dict[str, Any],
        trial_criteria: Dict[str, Any]
    ) -> Tuple[bool, List[str], float]:
        """
        Quick check: does patient pass hard criteria?
        
        Returns:
            (passed: bool, failed_criteria: List[str], confidence: float)
        """
        failed = []
        confidence = 1.0
        
        # Rule 1: Age must be within range
        age = patient_features.get("age")
        incl_age = self._get_inclusion_value(trial_criteria, "age")
        
        if age is not None and incl_age:
            if not self._check_numeric_range(age, incl_age):
                failed.append(f"Age {age} outside range {incl_age}")
                confidence = 0.9
        
        # Rule 2: Cannot have excluded conditions
        excluded_conditions = self._get_exclusion_values(trial_criteria, "conditions")
        patient_conditions = patient_features.get("conditions", [])
        
        for exc_cond in excluded_conditions:
            if any(exc_cond.lower() in cond.lower() for cond in patient_conditions):
                failed.append(f"Has excluded condition: {exc_cond}")
                return False, failed, 0.0  # Hard stop
        
        # Rule 3: Cannot have excluded medications
        excluded_meds = self._get_exclusion_values(trial_criteria, "medications")
        patient_meds = patient_features.get("medications", [])
        
        for exc_med in excluded_meds:
            if any(exc_med.lower() in med.lower() for med in patient_meds):
                failed.append(f"Has excluded medication: {exc_med}")
                return False, failed, 0.0  # Hard stop
        
        # Rule 4: Required diagnosis
        required_diagnosis = self._get_inclusion_value(trial_criteria, "required_diagnosis")
        if required_diagnosis:
            has_diagnosis = any(
                req.lower() in cond.lower()
                for cond in patient_conditions
                for req in ([required_diagnosis] if isinstance(required_diagnosis, str) else required_diagnosis)
            )
            if not has_diagnosis:
                failed.append(f"Missing required diagnosis: {required_diagnosis}")
                confidence = 0.7  # Borderline
        
        # Rule 5: Check critical labs availability
        critical_labs = ["HbA1c", "eGFR", "Fasting_Glucose"]
        missing_critical = sum(
            1 for lab in critical_labs
            if patient_features.get(lab) is None
        )
        
        if missing_critical > 0:
            confidence *= (1.0 - 0.1 * missing_critical)  # Reduce confidence
        
        passed = len(failed) == 0
        
        return passed, failed, confidence
    
    @staticmethod
    def _get_inclusion_value(trial_criteria: Dict, field_name: str) -> Any:
        """Get inclusion criterion value for field"""
        for inc in trial_criteria.get("inclusions", []):
            if inc.get("field_name") == field_name:
                return inc.get("value")
        return None
    
    @staticmethod
    def _get_exclusion_values(trial_criteria: Dict, field_name: str) -> List[Any]:
        """Get all exclusion values for field"""
        values = []
        for exc in trial_criteria.get("exclusions", []):
            if exc.get("field_name") == field_name:
                val = exc.get("value")
                if isinstance(val, list):
                    values.extend(val)
                else:
                    values.append(val)
        return values
    
    @staticmethod
    def _check_numeric_range(value: float, criterion: Dict) -> bool:
        """Check if value is within criterion range"""
        if not isinstance(criterion, dict):
            return True
        
        min_val = criterion.get("min")
        max_val = criterion.get("max")
        
        if min_val is not None and value < min_val:
            return False
        if max_val is not None and value > max_val:
            return False
        
        return True


# ============================================================================
# FEATURE ENGINEERING
# ============================================================================

class FeatureEngineer:
    """Generate feature vectors for XGBoost"""
    
    def __init__(self):
        """Initialize feature engineer"""
        logger.info("FeatureEngineer initialized")
    
    def create_feature_vector(
        self,
        patient_features: Dict[str, Any],
        trial_criteria: Dict[str, Any],
        patient_location: Optional[Tuple[float, float]] = None,
        trial_location: Optional[Tuple[float, float]] = None
    ) -> FeatureVector:
        """
        Create feature vector from patient and trial data
        
        Args:
            patient_features: Patient data dict
            trial_criteria: Trial criteria dict
            patient_location: (lat, lon) tuple
            trial_location: (lat, lon) tuple
        
        Returns:
            FeatureVector with all features
        """
        patient_id = patient_features.get("patient_id", "unknown")
        nct_id = trial_criteria.get("nct_id", "unknown")
        
        features = {}
        
        # 1. Age difference from criterion minimum
        age = patient_features.get("age")
        age_min = self._get_criterion_value(trial_criteria, "age", "min")
        features["age_diff"] = (age - age_min) if age and age_min else 0.0
        
        # 2. Lab match scores (normalized 0-1)
        lab_matches = self._compute_lab_matches(patient_features, trial_criteria)
        features.update(lab_matches)
        
        # 3. Condition match
        features["has_required_condition"] = self._check_required_condition(
            patient_features, trial_criteria
        )
        
        # 4. Exclusion checks (inverted: 1.0 = good, 0.0 = bad)
        features["has_excluded_condition"] = self._check_excluded_condition(
            patient_features, trial_criteria
        )
        features["has_excluded_medication"] = self._check_excluded_medication(
            patient_features, trial_criteria
        )
        
        # 5. Missing data flags
        missing_count, missing_critical = self._count_missing_labs(patient_features)
        features["missing_lab_count"] = float(missing_count)
        features["missing_critical_labs"] = float(missing_critical)
        
        # 6. Similarity scores
        features["condition_similarity"] = self._compute_similarity(
            patient_features.get("conditions", []),
            self._get_criterion_conditions(trial_criteria)
        )
        features["medication_similarity"] = self._compute_similarity(
            patient_features.get("medications", []),
            self._get_criterion_medications(trial_criteria)
        )
        
        # 7. Criteria coverage
        features["inclusion_criteria_coverage"] = self._compute_inclusion_coverage(
            patient_features, trial_criteria
        )
        features["exclusion_criteria_coverage"] = self._compute_exclusion_coverage(
            patient_features, trial_criteria
        )
        
        # 8. Geographic distance
        geographic_distance = 0.0
        if patient_location and trial_location:
            geographic_distance = self._haversine_distance(
                patient_location[0], patient_location[1],
                trial_location[0], trial_location[1]
            )
        features["geographic_distance"] = geographic_distance
        
        return FeatureVector(
            patient_id=patient_id,
            nct_id=nct_id,
            features=features
        )
    
    def _get_criterion_value(
        self,
        trial_criteria: Dict,
        field_name: str,
        key: str = "value"
    ) -> Optional[float]:
        """Get criterion value for field"""
        for inc in trial_criteria.get("inclusions", []):
            if inc.get("field_name") == field_name:
                value = inc.get("value", {})
                if isinstance(value, dict):
                    return value.get(key)
                return value
        return None
    
    def _compute_lab_matches(
        self,
        patient_features: Dict,
        trial_criteria: Dict
    ) -> Dict[str, float]:
        """Compute match scores for lab values (0-1)"""
        matches = {}
        
        labs = ["HbA1c", "Fasting_Glucose", "BMI", "eGFR", "Creatinine"]
        
        for lab in labs:
            patient_value = patient_features.get(lab)
            criterion = self._get_lab_criterion(trial_criteria, lab)
            
            if patient_value is None or criterion is None:
                matches[f"{lab.lower()}_match"] = 0.5  # Unknown
            else:
                matches[f"{lab.lower()}_match"] = self._score_numeric_match(
                    patient_value, criterion
                )
        
        return matches
    
    @staticmethod
    def _get_lab_criterion(trial_criteria: Dict, lab_name: str) -> Optional[Dict]:
        """Get criterion dict for lab"""
        for inc in trial_criteria.get("inclusions", []):
            if inc.get("field_name") == lab_name:
                return inc.get("value")
        return None
    
    @staticmethod
    def _score_numeric_match(patient_value: float, criterion: Dict) -> float:
        """Score how well patient value matches criterion (0-1)"""
        if not isinstance(criterion, dict):
            return 0.5
        
        min_val = criterion.get("min")
        max_val = criterion.get("max")
        
        # Check if in range
        if min_val and patient_value < min_val:
            distance = min_val - patient_value
            return max(0.0, 1.0 - (distance / min_val) * 0.5)
        
        if max_val and patient_value > max_val:
            distance = patient_value - max_val
            return max(0.0, 1.0 - (distance / max_val) * 0.5)
        
        return 1.0  # Perfect match
    
    @staticmethod
    def _check_required_condition(patient_features: Dict, trial_criteria: Dict) -> float:
        """Check if patient has required condition (0-1)"""
        for inc in trial_criteria.get("inclusions", []):
            if "diagnosis" in inc.get("field_name", "").lower():
                required = inc.get("value")
                patient_conds = patient_features.get("conditions", [])
                
                has_it = any(
                    req.lower() in cond.lower()
                    for cond in patient_conds
                    for req in ([required] if isinstance(required, str) else [required])
                )
                
                return 1.0 if has_it else 0.0
        
        return 0.5  # Not specified
    
    @staticmethod
    def _check_excluded_condition(patient_features: Dict, trial_criteria: Dict) -> float:
        """Check if patient has excluded condition (inverted: 1.0 = good)"""
        for exc in trial_criteria.get("exclusions", []):
            if "condition" in exc.get("field_name", "").lower():
                excluded = exc.get("value")
                patient_conds = patient_features.get("conditions", [])
                
                has_it = any(
                    exc.lower() in cond.lower()
                    for cond in patient_conds
                    for exc in ([excluded] if isinstance(excluded, str) else excluded)
                )
                
                return 0.0 if has_it else 1.0  # Inverted
        
        return 1.0  # Not specified (good)
    
    @staticmethod
    def _check_excluded_medication(patient_features: Dict, trial_criteria: Dict) -> float:
        """Check if patient has excluded medication (inverted)"""
        for exc in trial_criteria.get("exclusions", []):
            if "medication" in exc.get("field_name", "").lower() or \
               "treatment" in exc.get("field_name", "").lower() or \
               "insulin" in exc.get("field_name", "").lower():
                
                excluded = exc.get("value")
                patient_meds = patient_features.get("medications", [])
                
                has_it = any(
                    e.lower() in med.lower()
                    for med in patient_meds
                    for e in ([excluded] if isinstance(excluded, str) else excluded)
                )
                
                return 0.0 if has_it else 1.0  # Inverted
        
        return 1.0  # Not specified (good)
    
    @staticmethod
    def _count_missing_labs(patient_features: Dict) -> Tuple[int, int]:
        """Count missing labs"""
        critical = ["HbA1c", "eGFR", "Fasting_Glucose"]
        all_labs = ["HbA1c", "Fasting_Glucose", "BMI", "eGFR", "Creatinine", 
                   "PostPrandial_Glucose", "BP_Systolic", "BP_Diastolic"]
        
        missing_all = sum(1 for lab in all_labs if patient_features.get(lab) is None)
        missing_critical = sum(1 for lab in critical if patient_features.get(lab) is None)
        
        return missing_all, missing_critical
    
    @staticmethod
    def _compute_similarity(list1: List[str], list2: List[str]) -> float:
        """Compute Jaccard similarity between two lists"""
        if not list1 and not list2:
            return 1.0
        if not list1 or not list2:
            return 0.0
        
        set1 = {s.lower() for s in list1}
        set2 = {s.lower() for s in list2}
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0
    
    @staticmethod
    def _get_criterion_conditions(trial_criteria: Dict) -> List[str]:
        """Get required conditions from trial"""
        conditions = []
        for inc in trial_criteria.get("inclusions", []):
            if "condition" in inc.get("field_name", "").lower() or \
               "diagnosis" in inc.get("field_name", "").lower():
                val = inc.get("value", "")
                if isinstance(val, list):
                    conditions.extend(val)
                else:
                    conditions.append(val)
        return conditions
    
    @staticmethod
    def _get_criterion_medications(trial_criteria: Dict) -> List[str]:
        """Get required medications from trial"""
        meds = []
        for inc in trial_criteria.get("inclusions", []):
            if "medication" in inc.get("field_name", "").lower() or \
               "treatment" in inc.get("field_name", "").lower():
                val = inc.get("value", "")
                if isinstance(val, list):
                    meds.extend(val)
                else:
                    meds.append(val)
        return meds
    
    @staticmethod
    def _compute_inclusion_coverage(patient_features: Dict, trial_criteria: Dict) -> float:
        """Compute % of inclusion criteria met"""
        inclusions = trial_criteria.get("inclusions", [])
        if not inclusions:
            return 1.0
        
        met = 0
        for inc in inclusions:
            field = inc.get("field_name")
            if patient_features.get(field) is not None:
                met += 1
        
        return met / len(inclusions)
    
    @staticmethod
    def _compute_exclusion_coverage(patient_features: Dict, trial_criteria: Dict) -> float:
        """Compute % of exclusions NOT present (good)"""
        exclusions = trial_criteria.get("exclusions", [])
        if not exclusions:
            return 1.0
        
        met = 0
        for exc in exclusions:
            field = exc.get("field_name")
            # For exclusions, "met" means it's NOT present
            if patient_features.get(field) is None or patient_features.get(field) == []:
                met += 1
        
        return met / len(exclusions)
    
    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate haversine distance between two points (km)"""
        R = 6371  # Earth radius in km
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat / 2) ** 2 + \
            math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
        
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c


# ============================================================================
# XGBOOST INTEGRATION
# ============================================================================

class XGBoostInference:
    """XGBoost model inference and SHAP explanations"""
    
    def __init__(self, model_path: Optional[str] = None):
        """
        Initialize XGBoost inference
        
        Args:
            model_path: Path to trained XGBoost model
        """
        self.model = None
        self.explainer = None
        
        if model_path and XGBOOST_AVAILABLE:
            try:
                self.model = xgb.Booster()
                self.model.load_model(model_path)
                logger.info(f"Loaded XGBoost model from {model_path}")
            except Exception as e:
                logger.warning(f"Could not load XGBoost model: {e}")
        elif XGBOOST_AVAILABLE:
            logger.info("XGBoost available but no model path provided")
        else:
            logger.warning("XGBoost not installed. Install with: pip install xgboost shap")
    
    def predict(self, feature_vector: FeatureVector) -> XGBoostPrediction:
        """
        Predict eligibility score for patient-trial pair
        
        Args:
            feature_vector: Feature vector from FeatureEngineer
        
        Returns:
            XGBoostPrediction with score and explanations
        """
        if self.model is None:
            # Fallback: simple heuristic if model not available
            return self._fallback_prediction(feature_vector)
        
        try:
            # Convert features to DMatrix
            X = feature_vector.to_array().reshape(1, -1)
            dmatrix = xgb.DMatrix(X, feature_names=FEATURE_NAMES)
            
            # Get prediction
            score = self.model.predict(dmatrix)[0]
            
            # Get SHAP values if available
            shap_values = {}
            if SHAP_AVAILABLE:
                shap_values = self._get_shap_explanations(dmatrix, score)
            
            # Get feature importance
            feature_importance = self._get_feature_importance()
            
            # Identify top positive/negative features
            top_positive, top_negative = self._get_top_features(shap_values)
            
            return XGBoostPrediction(
                patient_id=feature_vector.patient_id,
                nct_id=feature_vector.nct_id,
                eligibility_score=float(score),
                prediction_confidence=0.9,
                feature_importance=feature_importance,
                shap_values=shap_values,
                top_positive_features=top_positive,
                top_negative_features=top_negative
            )
        
        except Exception as e:
            logger.error(f"XGBoost prediction error: {e}")
            return self._fallback_prediction(feature_vector)
    
    def _fallback_prediction(self, feature_vector: FeatureVector) -> XGBoostPrediction:
        """Fallback heuristic when model not available"""
        features = feature_vector.features
        
        # Simple heuristic: average of key positive features
        positive_features = [
            features.get("hba1c_match", 0.5),
            features.get("glucose_match", 0.5),
            features.get("bmi_match", 0.5),
            features.get("egfr_match", 0.5),
            features.get("has_required_condition", 0.5),
        ]
        
        # Adjust for exclusions
        score = np.mean(positive_features)
        score *= (1.0 - features.get("has_excluded_condition", 0.0) * 0.5)
        score *= (1.0 - features.get("has_excluded_medication", 0.0) * 0.5)
        
        # Penalty for missing data
        missing_penalty = features.get("missing_critical_labs", 0) * 0.05
        score = max(0.0, score - missing_penalty)
        
        return XGBoostPrediction(
            patient_id=feature_vector.patient_id,
            nct_id=feature_vector.nct_id,
            eligibility_score=float(min(1.0, max(0.0, score))),
            prediction_confidence=0.6,  # Lower confidence for heuristic
            feature_importance={},
            shap_values={}
        )
    
    def _get_shap_explanations(self, dmatrix: 'xgb.DMatrix', score: float) -> Dict[str, float]:
        """Get SHAP value explanations"""
        if not SHAP_AVAILABLE:
            return {}
        
        try:
            explainer = shap.TreeExplainer(self.model)
            shap_values = explainer.shap_values(dmatrix)
            
            # Convert to dict {feature_name: shap_value}
            return {
                FEATURE_NAMES[i]: float(shap_values[0][i])
                for i in range(len(FEATURE_NAMES))
            }
        except Exception as e:
            logger.debug(f"SHAP explanation error: {e}")
            return {}
    
    def _get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance from model"""
        if self.model is None:
            return {}
        
        try:
            importance = self.model.get_score()
            return {name: float(importance.get(name, 0)) for name in FEATURE_NAMES}
        except:
            return {}
    
    @staticmethod
    def _get_top_features(shap_values: Dict[str, float], top_n: int = 3) -> Tuple[List, List]:
        """Get top positive and negative SHAP features"""
        if not shap_values:
            return [], []
        
        sorted_features = sorted(shap_values.items(), key=lambda x: abs(x[1]), reverse=True)
        
        top_positive = [(f, v) for f, v in sorted_features[:top_n] if v > 0]
        top_negative = [(f, v) for f, v in sorted_features[:top_n] if v < 0]
        
        return top_positive, top_negative


# ============================================================================
# RANKING & AGGREGATION
# ============================================================================

class RankingAggregator:
    """Rank and aggregate trial matches for a patient"""
    
    def __init__(self):
        """Initialize aggregator"""
        self.prefilter = RuleBasedPreFilter()
        self.feature_engineer = FeatureEngineer()
        self.xgboost = XGBoostInference()
        logger.info("RankingAggregator initialized")
    
    def score_all_trials(
        self,
        patient_features: Dict[str, Any],
        trials: List[Dict[str, Any]],
        patient_location: Optional[Tuple[float, float]] = None,
        model_path: Optional[str] = None,
        top_n: int = 10
    ) -> List[RankedTrialMatch]:
        """
        Score patient against all trials and return ranked list
        
        Args:
            patient_features: Patient data
            trials: List of trial criteria dicts
            patient_location: (lat, lon) for geographic distance
            model_path: XGBoost model path
            top_n: Return top N matches
        
        Returns:
            List of RankedTrialMatch sorted by final score
        """
        patient_id = patient_features.get("patient_id", "unknown")
        logger.info(f"Scoring patient {patient_id} against {len(trials)} trials")
        
        matches = []
        
        for trial in trials:
            try:
                # Step 1: Rule-based pre-filter
                passed, failures, confidence = self.prefilter.check_patient_trial(
                    patient_features, trial
                )
                
                # Step 2: Feature engineering
                trial_location = (trial.get("location", {}).get("lat"),
                                trial.get("location", {}).get("lon"))
                
                feature_vector = self.feature_engineer.create_feature_vector(
                    patient_features, trial,
                    patient_location, trial_location
                )
                
                # Step 3: XGBoost prediction
                xgb_pred = self.xgboost.predict(feature_vector)
                
                # Step 4: Combine scores
                base_score = sum(list(feature_vector.features.values())[:10]) / 10 * 100
                xgb_score_100 = xgb_pred.eligibility_score * 100
                
                # Final score: 60% rule-based, 40% XGBoost
                final_score = (base_score * 0.6 + xgb_score_100 * 0.4) if passed else xgb_score_100 * 0.5
                
                # Geographic penalty
                geo_penalty = 1.0
                distance_km = feature_vector.features.get("geographic_distance", 0)
                if distance_km > 100:
                    geo_penalty = max(0.5, 1.0 - (distance_km - 100) / 1000)
                
                final_score *= geo_penalty
                
                # Create ranked match
                match = RankedTrialMatch(
                    patient_id=patient_id,
                    nct_id=trial.get("nct_id", "unknown"),
                    trial_title=trial.get("title", ""),
                    rule_prefilter_passed=passed,
                    rule_prefilter_reason="Passed rule check" if passed else "Failed hard criteria",
                    base_match_score=base_score,
                    xgboost_score=xgb_pred.eligibility_score,
                    final_score=final_score,
                    distance_km=distance_km if distance_km > 0 else None,
                    geographic_penalty=geo_penalty,
                    rule_based_failures=failures,
                    shap_explanations=xgb_pred.shap_values,
                    top_factors=self._format_top_factors(xgb_pred),
                    confidence=xgb_pred.prediction_confidence
                )
                
                matches.append(match)
            
            except Exception as e:
                logger.error(f"Error scoring trial {trial.get('nct_id')}: {e}")
                continue
        
        # Sort by final score (descending)
        matches.sort(key=lambda x: x.final_score, reverse=True)
        
        top_score = matches[0].final_score if matches else 0
        logger.info(f"✓ Scored {len(matches)} trials. Top match: {top_score:.1f}")
        
        return matches[:top_n]
    
    @staticmethod
    def _format_top_factors(xgb_pred: XGBoostPrediction) -> List[str]:
        """Format top factors for display"""
        factors = []
        
        for feature, shap_val in xgb_pred.top_positive_features[:3]:
            factors.append(f"✓ {feature} (+{shap_val:.3f})")
        
        for feature, shap_val in xgb_pred.top_negative_features[:2]:
            factors.append(f"✗ {feature} ({shap_val:.3f})")
        
        return factors


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("\n" + "="*80)
    print("MODULE 3 ENHANCED: RULE-BASED PRE-FILTER + XGBOOST + RANKING")
    print("="*80)
    
    # Sample patient
    patient = {
        "patient_id": "synth_DUMMYG010",
        "age": 35,
        "gender": "Male",
        "location": {"lat": 28.6139, "lon": 77.209},
        "conditions": ["Type 2 Diabetes"],
        "medications": ["Metformin"],
        "labs": {
            "HbA1c": 8.2,
            "Fasting_Glucose": 140.0,
            "BMI": 28.5,
            "eGFR": 85,
            "Creatinine": 0.9
        }
    }
    
    # Sample trials
    trials = [
        {
            "nct_id": "NCT03042325",
            "title": "Safety and Efficacy of Alogliptin",
            "location": {"lat": 28.7041, "lon": 77.1025},
            "inclusions": [
                {"field_name": "age", "value": {"min": 18, "max": 75}},
                {"field_name": "HbA1c", "value": {"min": 7.0, "max": 10.0}},
                {"field_name": "BMI", "value": {"min": 27}}
            ],
            "exclusions": [
                {"field_name": "prior_insulin", "value": "insulin"},
                {"field_name": "eGFR", "value": {"min": 45}}
            ]
        },
        {
            "nct_id": "NCT03720886",
            "title": "Type 2 Diabetes Management Study",
            "location": {"lat": 28.5244, "lon": 77.1855},
            "inclusions": [
                {"field_name": "age", "value": {"min": 20, "max": 70}},
                {"field_name": "HbA1c", "value": {"min": 6.5, "max": 11.0}},
                {"field_name": "Fasting_Glucose", "value": {"min": 100}}
            ],
            "exclusions": [
                {"field_name": "eGFR", "value": {"min": 30}}
            ]
        }
    ]
    
    # Step 1: Rule-based pre-filter
    print("\nStep 1: Rule-Based Pre-Filter")
    print("-" * 80)
    prefilter = RuleBasedPreFilter()
    
    for trial in trials:
        passed, failures, conf = prefilter.check_patient_trial(patient, trial)
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{trial['nct_id']}: {status} (confidence: {conf:.2f})")
        if failures:
            for f in failures:
                print(f"  - {f}")
    
    # Step 2: Feature engineering
    print("\nStep 2: Feature Engineering")
    print("-" * 80)
    engineer = FeatureEngineer()
    
    for trial in trials[:1]:  # Show first trial
        fv = engineer.create_feature_vector(patient, trial)
        print(f"{trial['nct_id']} features:")
        for fname, fval in list(fv.features.items())[:8]:
            print(f"  {fname}: {fval:.3f}")
    
    # Step 3: XGBoost (fallback heuristic if model not available)
    print("\nStep 3: XGBoost Inference (Fallback Heuristic)")
    print("-" * 80)
    xgb_inf = XGBoostInference()
    
    for trial in trials[:1]:
        fv = engineer.create_feature_vector(patient, trial)
        pred = xgb_inf.predict(fv)
        print(f"{trial['nct_id']} XGBoost score: {pred.eligibility_score:.3f}")
    
    # Step 4: Ranking
    print("\nStep 4: Final Ranking & Aggregation")
    print("-" * 80)
    aggregator = RankingAggregator()
    ranked = aggregator.score_all_trials(
        patient, trials,
        patient_location=(28.6139, 77.209),
        top_n=10
    )
    
    for i, match in enumerate(ranked, 1):
        print(f"\n{i}. {match.nct_id}")
        print(f"   Title: {match.trial_title}")
        print(f"   Rule-Based: {'✓ Passed' if match.rule_prefilter_passed else '✗ Failed'}")
        print(f"   Base Score: {match.base_match_score:.1f}/100")
        print(f"   XGBoost Score: {match.xgboost_score:.3f}")
        print(f"   Final Score: {match.final_score:.1f}/100")
        print(f"   Confidence: {match.confidence:.2%}")
        
        if match.distance_km:
            print(f"   Distance: {match.distance_km:.0f} km (penalty: {match.geographic_penalty:.2f})")
        
        if match.rule_based_failures:
            print(f"   Failures:")
            for f in match.rule_based_failures:
                print(f"     • {f}")
        
        if match.top_factors:
            print(f"   Top Factors:")
            for tf in match.top_factors[:3]:
                print(f"     {tf}")
    
    print("\n" + "="*80)
    print("✓ MODULE 3 ENHANCED TESTING COMPLETE")
    print("="*80 + "\n")
