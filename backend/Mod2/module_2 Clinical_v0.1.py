"""
Module 2: Clinical Trial Criteria Parsing with GLiNER + Regex Fallback
=========================================================================

Automatically loads:
  - Patient lab report  : PATIENT_REPORT_PATH
  - Clinical trials     : CLINICAL_TRIALS_PATH

Runs parsing pipeline and saves structured output to OUTPUT_PATH.
"""

import re
import json
import logging
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path

try:
    from gliner import GLiNER
    GLINER_AVAILABLE = True
except ImportError:
    GLINER_AVAILABLE = False


# ============================================================================
# ★  FILE PATHS  ★  — update these if files move
# ============================================================================

PATIENT_REPORT_PATH: Path = Path(
    r"D:\C&C\COHERENCE-26_Compile-and-Cry\backend\Mod1\Data_Extractor"
    r"\extracted_results\niharreport_20260307_032622.json"
)

CLINICAL_TRIALS_PATH: Path = Path(
    r"D:\C&C\COHERENCE-26_Compile-and-Cry\backend\Mod1\trial_fetcher"
    r"\clinical_trials_diabetes.json"
)

# Where Mod2 writes its output (sits next to this script by default)
OUTPUT_PATH: Path = Path(__file__).parent / "mod2_output.json"


# ============================================================================
# LOGGING
# ============================================================================

class ColorFormatter(logging.Formatter):
    COLORS = {
        'DEBUG':    '\033[36m',
        'INFO':     '\033[92m',
        'WARNING':  '\033[93m',
        'ERROR':    '\033[91m',
        'CRITICAL': '\033[95m',
        'RESET':    '\033[0m',
    }

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        record.levelname = f"{color}{record.levelname}{self.COLORS['RESET']}"
        return super().format(record)


def setup_logging(log_file: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger('Module2Parser')
    logger.setLevel(level)
    if logger.handlers:
        return logger  # avoid duplicate handlers on re-import

    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(ColorFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(ch)

    if log_file:
        fh = logging.FileHandler(log_file)
        fh.setLevel(level)
        fh.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        logger.addHandler(fh)

    return logger


logger = setup_logging(log_file='module2_parser.log')


# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

ENTITY_TYPES = [
    "Age range minimum and maximum in years",
    "HbA1c value or range as percentage",
    "Fasting glucose level or range in mg/dL",
    "Post-prandial glucose level in mg/dL",
    "BMI value or threshold in kg/m²",
    "eGFR value or threshold in mL/min/1.73m²",
    "Serum creatinine level in mg/dL",
    "Required diagnosis: Type 2 Diabetes Mellitus",
    "Diabetes duration in months or years",
    "Prior or excluded treatment: insulin",
    "Exclusion: severe renal impairment or CKD",
    "Exclusion: active cardiovascular disease",
    "Exclusion: history of severe hypoglycemia",
    "Exclusion: pregnancy or nursing",
    "Blood pressure measurement threshold",
]

REGEX_PATTERNS = {
    "age": {
        "pattern": r"(?:age|aged|patients?|subjects?|participants?)\s*(?:of|between|from|>=?|<=?)?\s*(\d{1,3})\s*(?:to|-|until|and|through|–)?\s*(\d{1,3})?\s*(?:years?|yrs?|yo)?",
        "category": "Demographic", "field": "age", "unit": "years", "priority": 95,
    },
    "hba1c": {
        "pattern": r"(?:HbA1c|A1c|hemoglobin\s*A1c|glycated\s*hemoglobin)\s*(?:of|between|from|>=?|<=?|–|-)?\s*(\d+\.?\d*)\s*(?:%|and|to|–|-|through)?\s*(\d+\.?\d*)?\s*%?",
        "category": "Lab", "field": "HbA1c", "unit": "%", "priority": 90,
    },
    "fasting_glucose": {
        "pattern": r"(?:fasting\s+)?(?:plasma\s+)?glucose\s*(?:levels?|values?)?(?:between|from|of|>=?|<=?|–|-)?\s*(\d+\.?\d*)\s*(?:mg/dL|and|to|–|-)\s*(\d+\.?\d*)?\s*(?:mg/dL)?",
        "category": "Lab", "field": "Fasting_Glucose", "unit": "mg/dL", "priority": 85,
    },
    "postprandial_glucose": {
        "pattern": r"(?:post[−-]?prandial|postprandial|2\s*h(?:our)?|two\s*hour)\s*glucose\s*(?:levels?|values?)?(?:between|from|of|>=?|<=?|–|-)?\s*(\d+\.?\d*)\s*(?:mg/dL|and|to|–|-)\s*(\d+\.?\d*)?\s*(?:mg/dL)?",
        "category": "Lab", "field": "Postprandial_Glucose", "unit": "mg/dL", "priority": 80,
    },
    "bmi": {
        "pattern": r"BMI\s*(?:>=?|<=?|of|between|from|–|-)?\s*(\d+\.?\d*)\s*(?:kg/m²|kg/m2|and|to|–|-|through)?\s*(\d+\.?\d*)?\s*(?:kg/m²|kg/m2)?",
        "category": "Lab", "field": "BMI", "unit": "kg/m²", "priority": 85,
    },
    "egfr": {
        "pattern": r"(?:eGFR|estimated\s+glomerular\s+filtration\s+rate|GFR)\s*(?:>=?|<=?|of|between|from|–|-)?\s*(\d+\.?\d*)\s*(?:mL/min/1\.73m²|mL/min|and|to|–|-|through)?\s*(\d+\.?\d*)?\s*(?:mL/min/1\.73m²|mL/min)?",
        "category": "Lab", "field": "eGFR", "unit": "mL/min/1.73m²", "priority": 90,
    },
    "creatinine": {
        "pattern": r"(?:serum\s+)?creatinine\s*(?:levels?|values?)?(?:>=?|<=?|of|between|from|–|-)?\s*(\d+\.?\d*)\s*(?:mg/dL|µmol/L|μmol/L|and|to|–|-|through)?\s*(\d+\.?\d*)?\s*(?:mg/dL|µmol/L|μmol/L)?",
        "category": "Lab", "field": "Creatinine", "unit": "mg/dL", "priority": 80,
    },
    "diabetes_duration": {
        "pattern": r"(?:diagnosed|duration|history)\s+(?:of|with)?\s+(?:type\s+2\s+)?diabetes\s+(?:for|>=?|>|<=?|<|–|-)?\s+(\d+)\s+(?:months?|years?)",
        "category": "Duration", "field": "diabetes_duration", "unit": "months", "priority": 75,
    },
    "blood_pressure": {
        "pattern": r"(?:blood\s+pressure|BP|systolic)\s*(?:>=?|<=?|of|between|from|–|-)?\s*(\d+)\s*(?:/|and|diastolic|mmHg|–|-)?\s*(\d+)?\s*(?:mmHg)?",
        "category": "Lab", "field": "BP", "unit": "mmHg", "priority": 75,
    },
}

NEGATION_KEYWORDS = {
    "no", "not", "without", "exclude", "excluding", "exclusion",
    "negative", "history negative", "absence of", "free from",
    "prior", "history of", "previous", "uncontrolled", "avoid",
    "contraindication", "contraindicated",
}


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ParsedCriterion:
    category: str
    field_name: str
    value: Any
    unit: Optional[str] = None
    negated: bool = False
    confidence: float = 0.9
    source: str = "regex"
    source_text: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class StructuredTrialCriteria:
    nct_id: str
    title: str
    inclusions: List[Dict]
    exclusions: List[Dict]
    parse_confidence: float
    parsed_at: str
    total_entities: int
    source_mix: str
    extraction_summary: Dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "nct_id": self.nct_id,
            "title": self.title,
            "inclusions": self.inclusions,
            "exclusions": self.exclusions,
            "parse_confidence": round(self.parse_confidence, 3),
            "parsed_at": self.parsed_at,
            "total_entities": self.total_entities,
            "source_mix": self.source_mix,
            "extraction_summary": self.extraction_summary,
            "warnings": self.warnings,
        }


# ============================================================================
# PARSER
# ============================================================================

class TrialCriteriaParser:

    def __init__(
        self,
        use_gliner: bool = True,
        gliner_model: str = "Ihor/gliner-biomed-small-v1.0",
        log_level: int = logging.INFO,
        cache_results: bool = False,
    ):
        self.use_gliner = use_gliner and GLINER_AVAILABLE
        self.gliner_model = None
        self.cache_results = cache_results
        self.cache_dir = Path("parsed_trials_cache") if cache_results else None

        if self.cache_dir:
            self.cache_dir.mkdir(exist_ok=True)

        logger.setLevel(log_level)

        if not GLINER_AVAILABLE and use_gliner:
            logger.warning("GLiNER not installed. pip install gliner")

        if self.use_gliner:
            try:
                logger.info(f"Loading GLiNER model: {gliner_model}")
                self.gliner_model = GLiNER.from_pretrained(gliner_model)
                logger.info("✓ GLiNER loaded")
            except Exception as e:
                logger.warning(f"GLiNER load failed: {e}. Falling back to regex.")
                self.use_gliner = False

    # ── public API ─────────────────────────────────────────────────────────

    def parse_trial(
        self,
        trial: Dict[str, Any],
        threshold: float = 0.5,
        use_cache: bool = True,
    ) -> StructuredTrialCriteria:
        nct_id   = trial.get("nct_id", "UNKNOWN")
        title    = trial.get("title", "")
        raw_incl = trial.get("inclusion_criteria", "")
        raw_excl = trial.get("exclusion_criteria", "")

        # Cache check
        if use_cache and self.cache_dir:
            cached = self.cache_dir / f"{nct_id}.json"
            if cached.exists():
                try:
                    with open(cached) as f:
                        return StructuredTrialCriteria(**json.load(f))
                except Exception:
                    pass

        logger.info(f"Parsing {nct_id}: {title[:60]}")

        regex_incl, regex_excl = self._extract_regex(raw_incl, raw_excl)
        gl_incl, gl_excl       = (self._extract_gliner(raw_incl, raw_excl, threshold)
                                   if self.use_gliner else ([], []))

        inclusions = self._merge_criteria(regex_incl, gl_incl)
        exclusions = self._merge_criteria(regex_excl, gl_excl)

        has_regex  = bool(regex_incl or regex_excl)
        has_gliner = bool(gl_incl or gl_excl)
        source_mix = ("hybrid" if has_regex and has_gliner
                      else "gliner_only" if has_gliner else "regex_only")

        all_crit  = inclusions + exclusions
        confs     = [c.get("confidence", 0.9) for c in all_crit]
        avg_conf  = sum(confs) / len(confs) if confs else 0.0
        summary   = self._compute_extraction_summary(inclusions, exclusions)

        result = StructuredTrialCriteria(
            nct_id=nct_id,
            title=title,
            inclusions=inclusions,
            exclusions=exclusions,
            parse_confidence=avg_conf,
            parsed_at=datetime.now().isoformat(),
            total_entities=len(all_crit),
            source_mix=source_mix,
            extraction_summary=summary,
        )

        if use_cache and self.cache_dir:
            try:
                with open(self.cache_dir / f"{nct_id}.json", "w") as f:
                    json.dump(result.to_dict(), f, indent=2)
            except Exception:
                pass

        logger.info(f"  ✓ {nct_id}: {len(all_crit)} entities | {source_mix} | conf={avg_conf:.2%}")
        return result

    def batch_parse_trials(
        self,
        trials: List[Dict],
        threshold: float = 0.5,
        show_progress: bool = True,
    ) -> List[StructuredTrialCriteria]:
        results, errors = [], []
        logger.info(f"Batch: {len(trials)} trials")

        for i, trial in enumerate(trials):
            try:
                results.append(self.parse_trial(trial, threshold=threshold))
            except Exception as e:
                nct_id = trial.get("nct_id", f"Trial_{i}")
                errors.append(f"{nct_id}: {e}")
                logger.error(f"Error parsing {nct_id}: {e}")

            if show_progress and (i + 1) % 10 == 0:
                logger.info(f"  Progress: {i+1}/{len(trials)}")

        logger.info(f"✓ Batch done: {len(results)} ok, {len(errors)} failed")
        if errors:
            logger.warning(f"First errors: {errors[:5]}")
        return results

    # ── private helpers ────────────────────────────────────────────────────

    def _extract_regex(self, raw_incl: str, raw_excl: str) -> Tuple[List[Dict], List[Dict]]:
        inclusions, exclusions = [], []
        sorted_patterns = sorted(
            REGEX_PATTERNS.items(),
            key=lambda x: x[1].get("priority", 50),
            reverse=True,
        )
        for name, info in sorted_patterns:
            try:
                for m in re.finditer(info["pattern"], raw_incl, re.IGNORECASE):
                    v = self._extract_numeric_value(m, name)
                    if v is not None:
                        inclusions.append({
                            "category": info["category"], "field_name": info["field"],
                            "value": v, "unit": info.get("unit"), "negated": False,
                            "confidence": 0.85, "source": "regex",
                            "source_text": m.group(0)[:100],
                        })
                for m in re.finditer(info["pattern"], raw_excl, re.IGNORECASE):
                    v = self._extract_numeric_value(m, name)
                    if v is not None:
                        exclusions.append({
                            "category": info["category"], "field_name": info["field"],
                            "value": v, "unit": info.get("unit"), "negated": True,
                            "confidence": 0.85, "source": "regex",
                            "source_text": m.group(0)[:100],
                        })
            except Exception as e:
                logger.warning(f"Regex error [{name}]: {e}")
        return inclusions, exclusions

    def _extract_gliner(self, raw_incl: str, raw_excl: str, threshold: float) -> Tuple[List[Dict], List[Dict]]:
        if not self.gliner_model:
            return [], []
        inclusions, exclusions = [], []
        try:
            combined  = f"Inclusion Criteria:\n{raw_incl}\n\nExclusion Criteria:\n{raw_excl}"
            entities  = self.gliner_model.predict_entities(
                combined, ENTITY_TYPES, threshold=threshold, flat_ner=True, multi_label=False
            )
            incl_end  = combined.find("Exclusion Criteria:")
            for ent in entities:
                is_excl  = ent.get("start", 0) > incl_end if incl_end > 0 else False
                criterion = self._parse_entity_to_criterion(
                    ent.get("text", ""), ent.get("label", ""), ent.get("score", 0.0), is_excl
                )
                if criterion:
                    (exclusions if is_excl else inclusions).append(criterion)
        except Exception as e:
            logger.error(f"GLiNER error: {e}")
        return inclusions, exclusions

    @staticmethod
    def _extract_numeric_value(match: re.Match, pattern_name: str) -> Any:
        try:
            g1 = match.group(1) if match.lastindex and match.lastindex >= 1 else None
            g2 = match.group(2) if match.lastindex and match.lastindex >= 2 else None

            if pattern_name == "age":
                if not g1: return None
                res = {"min": int(g1)}
                if g2: res["max"] = int(g2)
                return res

            if pattern_name in ("hba1c", "fasting_glucose", "postprandial_glucose",
                                 "bmi", "egfr", "creatinine"):
                if not g1: return None
                res = {"min": float(g1)}
                if g2: res["max"] = float(g2)
                return res

            if pattern_name == "diabetes_duration":
                return {"duration": int(g1), "unit": "months"} if g1 else None

            if pattern_name == "blood_pressure":
                if not g1: return None
                res = {"systolic": int(g1)}
                if g2: res["diastolic"] = int(g2)
                return res

        except (ValueError, AttributeError, IndexError) as e:
            logger.debug(f"Numeric extract error [{pattern_name}]: {e}")
        return None

    @staticmethod
    def _parse_entity_to_criterion(text: str, label: str, score: float, is_excl: bool) -> Optional[Dict]:
        label_l = label.lower()
        value, unit = None, None
        try:
            nums = re.findall(r"\d+\.?\d*", text)
            if "age" in label_l:
                value = {"min": int(nums[0]), **({"max": int(nums[1])} if len(nums) >= 2 else {})}
                unit = "years"
            elif "hba1c" in label_l:
                value = {"min": float(nums[0]), **({"max": float(nums[1])} if len(nums) >= 2 else {})}
                unit = "%"
            elif "glucose" in label_l:
                value = {"min": float(nums[0]), **({"max": float(nums[1])} if len(nums) >= 2 else {})}
                unit = "mg/dL"
            elif "bmi" in label_l:
                value = {"min": float(nums[0]), **({"max": float(nums[1])} if len(nums) >= 2 else {})}
                unit = "kg/m²"
            elif "egfr" in label_l or "creatinine" in label_l:
                value = float(nums[0]) if nums else None
                unit  = "mL/min/1.73m²" if "egfr" in label_l else "mg/dL"
            else:
                value = text

            if value is None:
                return None

            category = ("Demographic" if "age" in label_l
                        else "Duration" if "duration" in label_l
                        else "Lab" if any(x in label_l for x in
                                         ["hba1c","glucose","bmi","egfr","creatinine","blood pressure"])
                        else "Condition")

            return {
                "category": category, "field_name": label_l.replace(" ", "_"),
                "value": value, "unit": unit, "negated": is_excl,
                "confidence": score, "source": "gliner", "source_text": text[:100],
            }
        except Exception as e:
            logger.debug(f"Entity parse error: {e}")
            return None

    @staticmethod
    def _merge_criteria(regex_crit: List[Dict], gliner_crit: List[Dict]) -> List[Dict]:
        merged = {c["field_name"]: c for c in regex_crit}
        for c in gliner_crit:
            if c["field_name"] not in merged or c.get("confidence", 0) > 0.7:
                merged[c["field_name"]] = c
        return list(merged.values())

    @staticmethod
    def _compute_extraction_summary(inclusions: List[Dict], exclusions: List[Dict]) -> Dict:
        all_crit = inclusions + exclusions
        cats: Dict[str, int] = {}
        for c in all_crit:
            cat = c.get("category", "Unknown")
            cats[cat] = cats.get(cat, 0) + 1
        confs = [c.get("confidence", 0.5) for c in all_crit]
        return {
            "total_inclusions": len(inclusions),
            "total_exclusions": len(exclusions),
            "fields_by_category": cats,
            "confidence_stats": (
                {"min": min(confs), "max": max(confs), "avg": sum(confs) / len(confs)}
                if confs else {}
            ),
        }


# ============================================================================
# I/O HELPERS
# ============================================================================

def load_patient_report(path: Path) -> Dict:
    """Load extracted patient lab JSON produced by Mod1 extractor."""
    if not path.exists():
        raise FileNotFoundError(f"Patient report not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    logger.info(f"✓ Patient report loaded  → {path.name}")
    return data


def load_clinical_trials(path: Path) -> List[Dict]:
    """
    Load clinical trials JSON from Mod1 trial_fetcher.
    Accepts either a list of trial dicts OR a dict with a 'trials' key.
    """
    if not path.exists():
        raise FileNotFoundError(f"Clinical trials file not found: {path}")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    trials = raw if isinstance(raw, list) else raw.get("trials", list(raw.values()))
    logger.info(f"✓ Clinical trials loaded → {path.name}  ({len(trials)} trials)")
    return trials


def save_mod2_output(
    parsed_trials: List[StructuredTrialCriteria],
    patient: Dict,
    output_path: Path,
) -> None:
    """Save Mod2 output: parsed trials + patient snapshot + metadata."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(),
        "source_files": {
            "patient_report":   str(PATIENT_REPORT_PATH),
            "clinical_trials":  str(CLINICAL_TRIALS_PATH),
        },
        "patient_snapshot": {
            "patient_id": patient.get("patient_id"),
            "age":        patient.get("age"),
            "gender":     patient.get("gender"),
            "reported":   patient.get("reported"),
            "lab_count":  len(patient.get("labs", {})),
        },
        "parsed_trials_count": len(parsed_trials),
        "parsed_trials":       [t.to_dict() for t in parsed_trials],
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    logger.info(f"✓ Mod2 output saved → {output_path}  ({len(parsed_trials)} trials)")


def convert_to_module3_format(structured: StructuredTrialCriteria) -> Dict:
    """Slim format ready for Mod3 patient-matching."""
    return {
        "nct_id":           structured.nct_id,
        "title":            structured.title,
        "inclusions":       structured.inclusions,
        "exclusions":       structured.exclusions,
        "parse_confidence": structured.parse_confidence,
        "parsed_at":        structured.parsed_at,
        "total_entities":   structured.total_entities,
        "extraction_summary": structured.extraction_summary,
    }


# ============================================================================
# ENTRY POINT  — runs automatically when script is called directly
# ============================================================================

if __name__ == "__main__":

    print("\n" + "=" * 70)
    print("MODULE 2  |  Clinical Trial Criteria Parser")
    print("=" * 70)

    # ── 1. Load inputs ──────────────────────────────────────────────────────
    print(f"\n[1/4] Loading patient report …\n      {PATIENT_REPORT_PATH}")
    patient_data = load_patient_report(PATIENT_REPORT_PATH)

    print(f"\n[2/4] Loading clinical trials …\n      {CLINICAL_TRIALS_PATH}")
    trials = load_clinical_trials(CLINICAL_TRIALS_PATH)

    # ── 2. Parse trials ─────────────────────────────────────────────────────
    print(f"\n[3/4] Parsing {len(trials)} trial(s) …")
    parser = TrialCriteriaParser(use_gliner=True, log_level=logging.INFO)
    parsed = parser.batch_parse_trials(trials, threshold=0.5)

    # ── 3. Save output ──────────────────────────────────────────────────────
    print(f"\n[4/4] Saving output …\n      {OUTPUT_PATH}")
    save_mod2_output(parsed, patient_data, OUTPUT_PATH)

    # ── 4. Quick summary ────────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print(f"  Patient  : {patient_data.get('patient_id', 'N/A')}  "
          f"| Age {patient_data.get('age', '?')}  "
          f"| {patient_data.get('gender', '?')}")
    print(f"  Trials   : {len(parsed)} parsed successfully")
    total_entities = sum(t.total_entities for t in parsed)
    print(f"  Entities : {total_entities} total criteria extracted")
    print(f"  Output   : {OUTPUT_PATH}")
    print("─" * 70 + "\n")

    # ── 5. Module 3 format preview (first trial) ────────────────────────────
    if parsed:
        m3 = convert_to_module3_format(parsed[0])
        print(f"Module 3 preview — {m3['nct_id']} ({m3['total_entities']} entities)")
        print(f"  Inclusions ({len(m3['inclusions'])}):")
        for inc in m3["inclusions"]:
            print(f"    • {inc['field_name']:30s} {str(inc['value']):20s} {inc.get('unit','')}")
        print(f"  Exclusions ({len(m3['exclusions'])}):")
        for exc in m3["exclusions"]:
            print(f"    • {exc['field_name']:30s} {str(exc['value']):20s} {exc.get('unit','')}")

    print("\n✓ Module 2 complete.\n")