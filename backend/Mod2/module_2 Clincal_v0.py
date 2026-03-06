"""
Module 2: Clinical Trial Criteria Parsing with GLiNER + Regex Fallback
=========================================================================

Enhanced Version with:
- Better logging and debugging
- Improved error handling
- More robust regex patterns
- Confidence scoring improvements
- Batch processing with progress tracking
- Caching support

Input: Trial dict from Module 1 with raw criteria text
Output: Structured JSON with categorized inclusions/exclusions
"""

import re
import json
import logging
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
import warnings

try:
    from gliner import GLiNER
    GLINER_AVAILABLE = True
except ImportError:
    GLINER_AVAILABLE = False

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

class ColorFormatter(logging.Formatter):
    """Add colors to console logs for better readability"""
    
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[92m',       # Green
        'WARNING': '\033[93m',    # Yellow
        'ERROR': '\033[91m',      # Red
        'CRITICAL': '\033[95m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        record.levelname = f"{log_color}{record.levelname}{self.COLORS['RESET']}"
        return super().format(record)

def setup_logging(log_file: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    """Configure logging with both console and file output"""
    logger = logging.getLogger('Module2Parser')
    logger.setLevel(level)
    
    # Console handler with colors
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_formatter = ColorFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger

logger = setup_logging(log_file='module2_parser.log')


# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

# Entity types for GLiNER (natural language descriptions)
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

# Enhanced regex patterns with better matching
REGEX_PATTERNS = {
    "age": {
        "pattern": r"(?:age|aged|patients?|subjects?|participants?)\s*(?:of|between|from|>=?|<=?)?\s*(\d{1,3})\s*(?:to|-|until|and|through|–)?\s*(\d{1,3})?\s*(?:years?|yrs?|yo)?",
        "category": "Demographic",
        "field": "age",
        "unit": "years",
        "priority": 95  # Higher priority = try first
    },
    "hba1c": {
        "pattern": r"(?:HbA1c|A1c|hemoglobin\s*A1c|glycated\s*hemoglobin)\s*(?:of|between|from|>=?|<=?|–|-)\s*(\d+\.?\d*)\s*(?:%|and|to|–|-|through)?\s*(\d+\.?\d*)?\s*%?",
        "category": "Lab",
        "field": "HbA1c",
        "unit": "%",
        "priority": 90
    },
    "fasting_glucose": {
        "pattern": r"(?:fasting\s+)?(?:plasma\s+)?glucose\s*(?:levels?|values?)?(?:between|from|of|>=?|<=?|–|-)\s*(\d+\.?\d*)\s*(?:mg/dL|and|to|–|-)\s*(\d+\.?\d*)?\s*(?:mg/dL)?",
        "category": "Lab",
        "field": "Fasting_Glucose",
        "unit": "mg/dL",
        "priority": 85
    },
    "postprandial_glucose": {
        "pattern": r"(?:post[−-]?prandial|postprandial|2\s*h(?:our)?|two\s*hour)\s*glucose\s*(?:levels?|values?)?(?:between|from|of|>=?|<=?|–|-)\s*(\d+\.?\d*)\s*(?:mg/dL|and|to|–|-)\s*(\d+\.?\d*)?\s*(?:mg/dL)?",
        "category": "Lab",
        "field": "Postprandial_Glucose",
        "unit": "mg/dL",
        "priority": 80
    },
    "bmi": {
        "pattern": r"BMI\s*(?:>=?|<=?|of|between|from|–|-)\s*(\d+\.?\d*)\s*(?:kg/m²|kg/m2|and|to|–|-|through)?\s*(\d+\.?\d*)?\s*(?:kg/m²|kg/m2)?",
        "category": "Lab",
        "field": "BMI",
        "unit": "kg/m²",
        "priority": 85
    },
    "egfr": {
        "pattern": r"(?:eGFR|estimated\s+glomerular\s+filtration\s+rate|GFR)\s*(?:>=?|<=?|of|between|from|–|-)\s*(\d+\.?\d*)\s*(?:mL/min/1\.73m²|mL/min|and|to|–|–|-|through)?\s*(\d+\.?\d*)?\s*(?:mL/min/1\.73m²|mL/min)?",
        "category": "Lab",
        "field": "eGFR",
        "unit": "mL/min/1.73m²",
        "priority": 90
    },
    "creatinine": {
        "pattern": r"(?:serum\s+)?creatinine\s*(?:levels?|values?)?(?:>=?|<=?|of|between|from|–|-)\s*(\d+\.?\d*)\s*(?:mg/dL|µmol/L|μmol/L|and|to|–|-|through)?\s*(\d+\.?\d*)?\s*(?:mg/dL|µmol/L|μmol/L)?",
        "category": "Lab",
        "field": "Creatinine",
        "unit": "mg/dL",
        "priority": 80
    },
    "diabetes_duration": {
        "pattern": r"(?:diagnosed|duration|history)\s+(?:of|with)?\s+(?:type\s+2\s+)?diabetes\s+(?:for|>=?|>|<=?|<|–|-)\s+(\d+)\s+(?:months?|years?)",
        "category": "Duration",
        "field": "diabetes_duration",
        "unit": "months",
        "priority": 75
    },
    "blood_pressure": {
        "pattern": r"(?:blood\s+pressure|BP|systolic)\s*(?:>=?|<=?|of|between|from|–|-)\s*(\d+)\s*(?:/|and|diastolic|mmHg|–|-)\s*(\d+)?\s*(?:mmHg)?",
        "category": "Lab",
        "field": "BP",
        "unit": "mmHg",
        "priority": 75
    }
}

# Negation keywords indicating exclusion
NEGATION_KEYWORDS = {
    "no", "not", "without", "exclude", "excluding", "exclusion",
    "negative", "history negative", "absence of", "free from",
    "prior", "history of", "previous", "uncontrolled", "avoid",
    "contraindication", "contraindicated"
}


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ParsedCriterion:
    """Single parsed criterion (inclusion or exclusion)."""
    category: str
    field_name: str
    value: Any
    unit: Optional[str] = None
    negated: bool = False
    confidence: float = 0.9
    source: str = "regex"
    source_text: str = ""
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


@dataclass
class StructuredTrialCriteria:
    """Complete parsed trial criteria output."""
    nct_id: str
    title: str
    inclusions: List[Dict]
    exclusions: List[Dict]
    parse_confidence: float
    parsed_at: str
    total_entities: int
    source_mix: str
    extraction_summary: Dict = field(default_factory=dict)  # Stats per field
    warnings: List[str] = field(default_factory=list)  # Any warnings during parsing
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
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
            "warnings": self.warnings
        }


# ============================================================================
# MAIN PARSER CLASS
# ============================================================================

class TrialCriteriaParser:
    """
    Enhanced parser for clinical trial criteria using GLiNER + regex.
    
    Features:
    - Regex extraction with 8 patterns
    - GLiNER NER integration (optional)
    - Intelligent merging
    - Comprehensive logging
    - Error handling & recovery
    - Batch processing with progress
    """
    
    def __init__(
        self,
        use_gliner: bool = True,
        gliner_model: str = "Ihor/gliner-biomed-small-v1.0",
        log_level: int = logging.INFO,
        cache_results: bool = False
    ):
        """
        Initialize parser.
        
        Args:
            use_gliner: Whether to use GLiNER
            gliner_model: GLiNER model checkpoint
            log_level: Logging level
            cache_results: Cache parsed results to file
        """
        self.use_gliner = use_gliner and GLINER_AVAILABLE
        self.gliner_model = None
        self.cache_results = cache_results
        self.cache_dir = Path("parsed_trials_cache") if cache_results else None
        
        if self.cache_dir:
            self.cache_dir.mkdir(exist_ok=True)
        
        logger.setLevel(log_level)
        
        if not GLINER_AVAILABLE and use_gliner:
            logger.warning("GLiNER not installed. Install with: pip install gliner")
        
        if self.use_gliner:
            try:
                logger.info(f"Loading GLiNER model: {gliner_model}")
                self.gliner_model = GLiNER.from_pretrained(gliner_model)
                logger.info("✓ GLiNER loaded successfully")
            except Exception as e:
                logger.warning(f"Failed to load GLiNER: {e}. Using regex fallback.")
                self.use_gliner = False
    
    def parse_trial(
        self,
        trial: Dict[str, Any],
        threshold: float = 0.5,
        use_cache: bool = True
    ) -> StructuredTrialCriteria:
        """
        Parse a single trial's inclusion/exclusion criteria.
        
        Args:
            trial: Trial dict with nct_id, title, inclusion_criteria, exclusion_criteria
            threshold: GLiNER confidence threshold (0.3-0.7)
            use_cache: Use cached result if available
            
        Returns:
            StructuredTrialCriteria with parsed criteria
        """
        nct_id = trial.get("nct_id", "UNKNOWN")
        title = trial.get("title", "")
        raw_incl = trial.get("inclusion_criteria", "")
        raw_excl = trial.get("exclusion_criteria", "")
        
        # Check cache
        if use_cache and self.cache_dir:
            cached_file = self.cache_dir / f"{nct_id}.json"
            if cached_file.exists():
                logger.debug(f"Loading cached result for {nct_id}")
                try:
                    with open(cached_file) as f:
                        data = json.load(f)
                    return StructuredTrialCriteria(**data)
                except Exception as e:
                    logger.warning(f"Failed to load cache: {e}")
        
        logger.info(f"Parsing trial {nct_id}: {title[:60]}")
        
        # Stage 1: Regex extraction
        regex_inclusions, regex_exclusions = self._extract_regex(raw_incl, raw_excl)
        logger.debug(f"  Regex: {len(regex_inclusions)} inclusions, {len(regex_exclusions)} exclusions")
        
        # Stage 2: GLiNER extraction
        gliner_inclusions, gliner_exclusions = [], []
        if self.use_gliner:
            gliner_inclusions, gliner_exclusions = self._extract_gliner(
                raw_incl, raw_excl, threshold
            )
            logger.debug(f"  GLiNER: {len(gliner_inclusions)} inclusions, {len(gliner_exclusions)} exclusions")
        
        # Stage 3: Merge
        inclusions = self._merge_criteria(regex_inclusions, gliner_inclusions, "inclusion")
        exclusions = self._merge_criteria(regex_exclusions, gliner_exclusions, "exclusion")
        
        # Determine source mix
        has_regex = bool(regex_inclusions or regex_exclusions)
        has_gliner = bool(gliner_inclusions or gliner_exclusions)
        
        if has_regex and has_gliner:
            source_mix = "hybrid"
        elif has_gliner:
            source_mix = "gliner_only"
        else:
            source_mix = "regex_only"
        
        # Compute statistics
        all_criteria = inclusions + exclusions
        confidences = [c.get("confidence", 0.9) for c in all_criteria]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        # Extract summary
        extraction_summary = self._compute_extraction_summary(inclusions, exclusions)
        
        result = StructuredTrialCriteria(
            nct_id=nct_id,
            title=title,
            inclusions=inclusions,
            exclusions=exclusions,
            parse_confidence=avg_confidence,
            parsed_at=datetime.now().isoformat(),
            total_entities=len(all_criteria),
            source_mix=source_mix,
            extraction_summary=extraction_summary
        )
        
        # Cache result
        if use_cache and self.cache_dir:
            try:
                with open(self.cache_dir / f"{nct_id}.json", "w") as f:
                    json.dump(result.to_dict(), f, indent=2)
            except Exception as e:
                logger.warning(f"Failed to cache result: {e}")
        
        logger.info(f"✓ {nct_id}: {len(all_criteria)} entities, {avg_confidence:.2%} confidence, {source_mix}")
        
        return result
    
    def _extract_regex(self, raw_incl: str, raw_excl: str) -> Tuple[List[Dict], List[Dict]]:
        """Extract criteria using regex patterns (sorted by priority)"""
        inclusions = []
        exclusions = []
        
        # Sort patterns by priority (high first)
        sorted_patterns = sorted(
            REGEX_PATTERNS.items(),
            key=lambda x: x[1].get("priority", 50),
            reverse=True
        )
        
        for pattern_name, pattern_info in sorted_patterns:
            pattern = pattern_info["pattern"]
            category = pattern_info["category"]
            field = pattern_info["field"]
            unit = pattern_info.get("unit")
            
            try:
                # Search in inclusions
                for match in re.finditer(pattern, raw_incl, re.IGNORECASE):
                    value = self._extract_numeric_value(match, pattern_name)
                    if value is not None:
                        inclusions.append({
                            "category": category,
                            "field_name": field,
                            "value": value,
                            "unit": unit,
                            "negated": False,
                            "confidence": 0.85,
                            "source": "regex",
                            "source_text": match.group(0)[:100]
                        })
                
                # Search in exclusions
                for match in re.finditer(pattern, raw_excl, re.IGNORECASE):
                    value = self._extract_numeric_value(match, pattern_name)
                    if value is not None:
                        exclusions.append({
                            "category": category,
                            "field_name": field,
                            "value": value,
                            "unit": unit,
                            "negated": True,
                            "confidence": 0.85,
                            "source": "regex",
                            "source_text": match.group(0)[:100]
                        })
            
            except Exception as e:
                logger.warning(f"Error extracting {pattern_name}: {e}")
                continue
        
        return inclusions, exclusions
    
    def _extract_gliner(self, raw_incl: str, raw_excl: str, threshold: float) -> Tuple[List[Dict], List[Dict]]:
        """Extract criteria using GLiNER NER"""
        if not self.gliner_model:
            return [], []
        
        inclusions = []
        exclusions = []
        
        try:
            combined_text = f"Inclusion Criteria:\n{raw_incl}\n\nExclusion Criteria:\n{raw_excl}"
            
            # Run GLiNER prediction
            entities = self.gliner_model.predict_entities(
                combined_text,
                ENTITY_TYPES,
                threshold=threshold,
                flat_ner=True,
                multi_label=False
            )
            
            # Determine inclusion vs exclusion
            incl_end = combined_text.find("Exclusion Criteria:")
            
            for entity in entities:
                start = entity.get("start", 0)
                text = entity.get("text", "").strip()
                label = entity.get("label", "")
                score = entity.get("score", 0.0)
                
                is_exclusion = start > incl_end if incl_end > 0 else "Exclusion" in label
                
                criterion = self._parse_entity_to_criterion(text, label, score, is_exclusion)
                
                if criterion:
                    target_list = exclusions if is_exclusion else inclusions
                    target_list.append(criterion)
        
        except Exception as e:
            logger.error(f"GLiNER extraction error: {e}")
        
        return inclusions, exclusions
    
    @staticmethod
    def _extract_numeric_value(match: re.Match, pattern_name: str) -> Any:
        """Extract numeric value from regex match groups with error handling"""
        try:
            if pattern_name == "age":
                min_val = int(match.group(1)) if match.group(1) else None
                max_val = int(match.group(2)) if match.lastindex >= 2 and match.group(2) else None
                if min_val is None:
                    return None
                return {"min": min_val, **({"max": max_val} if max_val else {})}
            
            elif pattern_name in ["hba1c", "fasting_glucose", "postprandial_glucose", "bmi", "egfr", "creatinine"]:
                min_val = float(match.group(1)) if match.group(1) else None
                max_val = float(match.group(2)) if match.lastindex >= 2 and match.group(2) else None
                if min_val is None:
                    return None
                return {"min": min_val, **({"max": max_val} if max_val else {})}
            
            elif pattern_name == "diabetes_duration":
                val = match.group(1) if match.group(1) else None
                if not val:
                    return None
                return {"duration": int(val), "unit": "months"}
            
            elif pattern_name == "blood_pressure":
                systolic = int(match.group(1)) if match.group(1) else None
                diastolic = int(match.group(2)) if match.lastindex >= 2 and match.group(2) else None
                if systolic is None:
                    return None
                return {"systolic": systolic, **({"diastolic": diastolic} if diastolic else {})}
            
            return None
        except (IndexError, ValueError, AttributeError) as e:
            logger.debug(f"Error extracting numeric value from {pattern_name}: {e}")
            return None
    
    @staticmethod
    def _parse_entity_to_criterion(text: str, label: str, score: float, is_exclusion: bool) -> Optional[Dict]:
        """Convert GLiNER entity to criterion dict"""
        value = None
        unit = None
        
        try:
            if "age" in label.lower():
                numbers = re.findall(r"\d+", text)
                if numbers:
                    value = {"min": int(numbers[0])}
                    if len(numbers) >= 2:
                        value["max"] = int(numbers[1])
                    unit = "years"
            
            elif "hba1c" in label.lower():
                numbers = re.findall(r"\d+\.?\d*", text)
                if numbers:
                    value = {"min": float(numbers[0])}
                    if len(numbers) >= 2:
                        value["max"] = float(numbers[1])
                    unit = "%"
            
            elif "glucose" in label.lower():
                numbers = re.findall(r"\d+\.?\d*", text)
                if numbers:
                    value = {"min": float(numbers[0])}
                    if len(numbers) >= 2:
                        value["max"] = float(numbers[1])
                    unit = "mg/dL"
            
            elif "bmi" in label.lower():
                numbers = re.findall(r"\d+\.?\d*", text)
                if numbers:
                    value = {"min": float(numbers[0])}
                    if len(numbers) >= 2:
                        value["max"] = float(numbers[1])
                    unit = "kg/m²"
            
            elif "egfr" in label.lower() or "creatinine" in label.lower():
                numbers = re.findall(r"\d+\.?\d*", text)
                if numbers:
                    value = float(numbers[0])
                    unit = "mL/min/1.73m²" if "egfr" in label.lower() else "mg/dL"
            
            elif "diabetes" in label.lower():
                value = text
            
            else:
                value = text
            
            if value is None:
                return None
            
            # Determine category
            category = "Lab" if any(x in label.lower() for x in ["hba1c", "glucose", "bmi", "egfr", "creatinine", "blood pressure"]) else "Condition"
            if "age" in label.lower():
                category = "Demographic"
            elif "duration" in label.lower():
                category = "Duration"
            
            return {
                "category": category,
                "field_name": label.lower().replace(" ", "_"),
                "value": value,
                "unit": unit,
                "negated": is_exclusion,
                "confidence": score,
                "source": "gliner",
                "source_text": text[:100]
            }
        
        except Exception as e:
            logger.debug(f"Error parsing entity: {e}")
            return None
    
    @staticmethod
    def _merge_criteria(
        regex_crit: List[Dict],
        gliner_crit: List[Dict],
        source_type: str = "inclusion"
    ) -> List[Dict]:
        """Intelligently merge regex and GLiNER criteria"""
        merged = {}
        
        # Add regex criteria (baseline)
        for crit in regex_crit:
            field = crit.get("field_name", "unknown")
            merged[field] = crit
        
        # Overlay with GLiNER (higher priority if confidence > 0.7)
        for crit in gliner_crit:
            field = crit.get("field_name", "unknown")
            gliner_conf = crit.get("confidence", 0.0)
            
            if field not in merged or gliner_conf > 0.7:
                merged[field] = crit
        
        return list(merged.values())
    
    @staticmethod
    def _compute_extraction_summary(inclusions: List[Dict], exclusions: List[Dict]) -> Dict:
        """Compute extraction statistics"""
        summary = {
            "total_inclusions": len(inclusions),
            "total_exclusions": len(exclusions),
            "fields_by_category": {},
            "confidence_stats": {}
        }
        
        all_criteria = inclusions + exclusions
        
        # Group by category
        for crit in all_criteria:
            cat = crit.get("category", "Unknown")
            summary["fields_by_category"][cat] = summary["fields_by_category"].get(cat, 0) + 1
        
        # Confidence stats
        if all_criteria:
            confidences = [c.get("confidence", 0.5) for c in all_criteria]
            summary["confidence_stats"] = {
                "min": min(confidences),
                "max": max(confidences),
                "avg": sum(confidences) / len(confidences)
            }
        
        return summary
    
    def batch_parse_trials(
        self,
        trials: List[Dict],
        threshold: float = 0.5,
        show_progress: bool = True
    ) -> List[StructuredTrialCriteria]:
        """Parse multiple trials with progress tracking"""
        results = []
        errors = []
        
        logger.info(f"Starting batch processing: {len(trials)} trials")
        
        for i, trial in enumerate(trials):
            try:
                structured = self.parse_trial(trial, threshold=threshold)
                results.append(structured)
            
            except Exception as e:
                nct_id = trial.get("nct_id", f"Trial_{i}")
                error_msg = f"{nct_id}: {str(e)}"
                errors.append(error_msg)
                logger.error(f"Error parsing trial: {error_msg}")
            
            # Progress update
            if show_progress and (i + 1) % 10 == 0:
                logger.info(f"Progress: {i + 1}/{len(trials)} trials parsed")
        
        # Summary
        logger.info(f"✓ Batch complete: {len(results)} successful, {len(errors)} failed")
        
        if errors:
            logger.warning(f"Errors: {errors[:5]}")  # Show first 5 errors
        
        return results


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def convert_to_module3_format(structured: StructuredTrialCriteria) -> Dict:
    """Convert Module 2 output to Module 3 input format"""
    return {
        "nct_id": structured.nct_id,
        "title": structured.title,
        "inclusions": structured.inclusions,
        "exclusions": structured.exclusions,
        "parse_confidence": structured.parse_confidence,
        "parsed_at": structured.parsed_at,
        "total_entities": structured.total_entities,
        "extraction_summary": structured.extraction_summary,
    }


def save_parsed_trials(trials: List[StructuredTrialCriteria], output_file: str) -> None:
    """Save parsed trials to JSON file"""
    data = [t.to_dict() for t in trials]
    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Saved {len(data)} trials to {output_file}")


def load_parsed_trials(input_file: str) -> List[StructuredTrialCriteria]:
    """Load parsed trials from JSON file"""
    with open(input_file) as f:
        data = json.load(f)
    
    trials = [StructuredTrialCriteria(**d) for d in data]
    logger.info(f"Loaded {len(data)} trials from {input_file}")
    return trials


# ============================================================================
# EXAMPLE USAGE & TESTING
# ============================================================================

if __name__ == "__main__":
    
    sample_trial = {
        "nct_id": "NCT03042325",
        "title": "Safety and Efficacy of Alogliptin in Indian Participants With Type 2 Diabetes",
        "inclusion_criteria": """
            - Adults aged 18 to 75 years
            - Diagnosed with Type 2 Diabetes Mellitus for at least 6 months
            - HbA1c between 7.0% and 10.0% at screening
            - BMI ≥ 27 kg/m²
            - Fasting glucose 110-270 mg/dL
            - eGFR ≥ 45 mL/min/1.73m²
        """,
        "exclusion_criteria": """
            - Prior use of insulin for diabetes
            - eGFR < 45 mL/min/1.73m²
            - Serum creatinine > 1.5 mg/dL
            - Active cardiovascular disease
            - History of severe hypoglycemia in past 12 months
            - Pregnancy or nursing
        """
    }
    
    print("\n" + "="*80)
    print("MODULE 2: ENHANCED TRIAL CRITERIA PARSER - TEST")
    print("="*80)
    
    # Initialize parser (regex-only if GLiNER not available)
    parser = TrialCriteriaParser(use_gliner=True, log_level=logging.INFO)
    
    # Parse trial
    print(f"\nParsing: {sample_trial['title']}")
    structured = parser.parse_trial(sample_trial, threshold=0.5)
    
    # Display results
    print(f"\n✓ Parsing Complete!")
    print(f"  Source mix: {structured.source_mix}")
    print(f"  Total entities: {structured.total_entities}")
    print(f"  Avg confidence: {structured.parse_confidence:.3f}")
    
    print(f"\nInclusions ({len(structured.inclusions)}):")
    for inc in structured.inclusions:
        print(f"  • {inc['field_name']}: {inc['value']} {inc.get('unit', '')}")
    
    print(f"\nExclusions ({len(structured.exclusions)}):")
    for exc in structured.exclusions:
        print(f"  • {exc['field_name']}: {exc['value']} {exc.get('unit', '')}")
    
    # Extraction summary
    print(f"\nExtraction Summary:")
    for cat, count in structured.extraction_summary.get("fields_by_category", {}).items():
        print(f"  {cat}: {count} fields")
    
    # Convert for Module 3
    m3_input = convert_to_module3_format(structured)
    print(f"\n✓ Converted to Module 3 format")
    
    # Save example
    output_file = "module2_enhanced_example.json"
    with open(output_file, "w") as f:
        json.dump(structured.to_dict(), f, indent=2)
    
    print(f"✓ Example output saved to: {output_file}")
    print("\n" + "="*80 + "\n")


# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

# Entity types for GLiNER (natural language descriptions)
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

# Regex patterns for fallback (robust extraction)
REGEX_PATTERNS = {
    "age": {
        "pattern": r"(?:age|aged|patients?|subjects?|participants?)\s*(?:of|between|from)?\s*(\d{1,3})\s*(?:to|-|until|and|through)?\s*(\d{1,3})?\s*(?:years?|yrs?)",
        "category": "Demographic",
        "field": "age"
    },
    "hba1c": {
        "pattern": r"(?:HbA1c|A1c|hemoglobin\s*A1c)\s*(?:between|from|≥|>|≤|<)?\s*(\d+\.?\d*)\s*(?:%|and|to|-|through)?\s*(\d+\.?\d*)?\s*%?",
        "category": "Lab",
        "field": "HbA1c",
        "unit": "%"
    },
    "fasting_glucose": {
        "pattern": r"(?:fasting\s*)?glucose\s*(?:between|from|≥|>|≤|<)?\s*(\d+\.?\d*)\s*(?:mg/dL|and|to|–|-)\s*(\d+\.?\d*)?\s*(?:mg/dL)?",
        "category": "Lab",
        "field": "Fasting_Glucose",
        "unit": "mg/dL"
    },
    "bmi": {
        "pattern": r"BMI\s*(?:≥|>|≤|<|of|between)?\s*(\d+\.?\d*)\s*(?:kg/m²|kg/m2|and|to|-|–)?\s*(\d+\.?\d*)?\s*(?:kg/m²|kg/m2)?",
        "category": "Lab",
        "field": "BMI",
        "unit": "kg/m²"
    },
    "egfr": {
        "pattern": r"(?:eGFR|estimated\s*glomerular\s*filtration\s*rate)\s*(?:≥|>|≤|<)?\s*(\d+\.?\d*)\s*(?:mL/min/1.73m²|mL/min)?",
        "category": "Lab",
        "field": "eGFR",
        "unit": "mL/min/1.73m²"
    },
    "creatinine": {
        "pattern": r"(?:serum\s*)?creatinine\s*(?:≥|>|≤|<)?\s*(\d+\.?\d*)\s*(?:mg/dL)?",
        "category": "Lab",
        "field": "Creatinine",
        "unit": "mg/dL"
    },
    "diabetes_duration": {
        "pattern": r"(?:diagnosed|duration|history|diabetes)\s*(?:of|with)?\s*(?:type\s*2\s*)?diabetes\s*(?:for|≥|>)?\s*(\d+)\s*(?:months?|years?)",
        "category": "Duration",
        "field": "diabetes_duration",
        "unit": "months"
    },
    "blood_pressure": {
        "pattern": r"(?:blood\s*pressure|BP|systolic)\s*(?:≥|>|≤|<)?\s*(\d+)\s*(?:/|\s*and\s*)?(\d+)?\s*(?:mmHg)?",
        "category": "Lab",
        "field": "BP",
        "unit": "mmHg"
    }
}

# Negation keywords that indicate exclusion
NEGATION_KEYWORDS = [
    "no", "not", "without", "exclude", "excluding", "exclusion",
    "negative", "history negative", "absence of", "free from",
    "prior", "history of", "previous", "uncontrolled"
]


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ParsedCriterion:
    """Single parsed criterion (inclusion or exclusion)."""
    category: str  # "Demographic", "Lab", "Condition", "Duration", "Treatment"
    field_name: str  # e.g., "age", "HbA1c", "prior_insulin"
    value: Any  # scalar, dict (min/max), or list
    unit: Optional[str] = None
    negated: bool = False  # True if excluded/negative
    confidence: float = 0.9  # confidence score (regex=0.9, GLiNER varies)
    source: str = "regex"  # "regex" or "gliner"
    source_text: str = ""  # original span


@dataclass
class StructuredTrialCriteria:
    """Complete parsed trial criteria output."""
    nct_id: str
    title: str
    inclusions: List[Dict]
    exclusions: List[Dict]
    parse_confidence: float  # average confidence
    parsed_at: str
    total_entities: int
    source_mix: str  # "regex_only", "gliner_only", "hybrid"


# ============================================================================
# MAIN PARSER CLASS
# ============================================================================

class TrialCriteriaParser:
    """
    Parse clinical trial criteria using GLiNER + regex fallback.
    
    Two-stage approach:
    1. Regex patterns (high precision, limited recall)
    2. GLiNER NER (good coverage, zero-shot)
    3. Merge results intelligently
    """
    
    def __init__(self, use_gliner: bool = True, gliner_model: str = "Ihor/gliner-biomed-small-v1.0"):
        """
        Initialize parser.
        
        Args:
            use_gliner: Whether to use GLiNER (requires installation)
            gliner_model: GLiNER model checkpoint
        """
        self.use_gliner = use_gliner and GLINER_AVAILABLE
        self.gliner_model = None
        
        if self.use_gliner:
            try:
                logger.info(f"Loading GLiNER: {gliner_model}")
                self.gliner_model = GLiNER.from_pretrained(gliner_model)
                logger.info("✓ GLiNER loaded successfully")
            except Exception as e:
                logger.warning(f"Failed to load GLiNER: {e}. Using regex fallback.")
                self.use_gliner = False
    
    def parse_trial(self, trial: Dict[str, Any], threshold: float = 0.5) -> StructuredTrialCriteria:
        """
        Parse a single trial's inclusion/exclusion criteria.
        
        Args:
            trial: Trial dict from Module 1 with keys:
                - nct_id: str
                - title: str
                - inclusion_criteria: str (raw text)
                - exclusion_criteria: str (raw text)
            threshold: GLiNER confidence threshold (0.3-0.7)
            
        Returns:
            StructuredTrialCriteria with parsed criteria
        """
        nct_id = trial.get("nct_id", "UNKNOWN")
        title = trial.get("title", "")
        raw_incl = trial.get("inclusion_criteria", "")
        raw_excl = trial.get("exclusion_criteria", "")
        
        logger.info(f"Parsing trial {nct_id}: {title[:60]}...")
        
        # Stage 1: Regex extraction (always run)
        regex_inclusions, regex_exclusions = self._extract_regex(raw_incl, raw_excl)
        
        # Stage 2: GLiNER extraction (if available)
        gliner_inclusions, gliner_exclusions = [], []
        if self.use_gliner:
            gliner_inclusions, gliner_exclusions = self._extract_gliner(
                raw_incl, raw_excl, threshold
            )
        
        # Stage 3: Merge intelligently
        inclusions = self._merge_criteria(regex_inclusions, gliner_inclusions, source_type="inclusion")
        exclusions = self._merge_criteria(regex_exclusions, gliner_exclusions, source_type="exclusion")
        
        # Determine source mix
        has_regex = bool(regex_inclusions or regex_exclusions)
        has_gliner = bool(gliner_inclusions or gliner_exclusions)
        
        if has_regex and has_gliner:
            source_mix = "hybrid"
        elif has_gliner:
            source_mix = "gliner_only"
        else:
            source_mix = "regex_only"
        
        # Compute average confidence
        all_criteria = inclusions + exclusions
        confidences = [c.get("confidence", 0.9) for c in all_criteria]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        return StructuredTrialCriteria(
            nct_id=nct_id,
            title=title,
            inclusions=inclusions,
            exclusions=exclusions,
            parse_confidence=avg_confidence,
            parsed_at=datetime.now().isoformat(),
            total_entities=len(all_criteria),
            source_mix=source_mix
        )
    
    def _extract_regex(self, raw_incl: str, raw_excl: str) -> Tuple[List[Dict], List[Dict]]:
        """
        Extract criteria using regex patterns.
        
        Returns:
            (inclusions_list, exclusions_list) as dicts
        """
        inclusions = []
        exclusions = []
        
        # Process each pattern
        for pattern_name, pattern_info in REGEX_PATTERNS.items():
            pattern = pattern_info["pattern"]
            category = pattern_info["category"]
            field = pattern_info["field"]
            unit = pattern_info.get("unit")
            
            # Search in inclusions
            for match in re.finditer(pattern, raw_incl, re.IGNORECASE):
                value = self._extract_numeric_value(match, pattern_name)
                if value:
                    inclusions.append({
                        "category": category,
                        "field_name": field,
                        "value": value,
                        "unit": unit,
                        "negated": False,
                        "confidence": 0.85,  # Regex confidence
                        "source": "regex",
                        "source_text": match.group(0)
                    })
            
            # Search in exclusions
            for match in re.finditer(pattern, raw_excl, re.IGNORECASE):
                value = self._extract_numeric_value(match, pattern_name)
                if value:
                    exclusions.append({
                        "category": category,
                        "field_name": field,
                        "value": value,
                        "unit": unit,
                        "negated": True,
                        "confidence": 0.85,
                        "source": "regex",
                        "source_text": match.group(0)
                    })
        
        return inclusions, exclusions
    
    def _extract_gliner(self, raw_incl: str, raw_excl: str, threshold: float) -> Tuple[List[Dict], List[Dict]]:
        """
        Extract criteria using GLiNER NER.
        
        Returns:
            (inclusions_list, exclusions_list) as dicts
        """
        if not self.gliner_model:
            return [], []
        
        inclusions = []
        exclusions = []
        
        # Combine texts for context
        combined_text = f"Inclusion Criteria:\n{raw_incl}\n\nExclusion Criteria:\n{raw_excl}"
        
        try:
            # Run GLiNER prediction
            entities = self.gliner_model.predict_entities(
                combined_text,
                ENTITY_TYPES,
                threshold=threshold,
                flat_ner=True,
                multi_label=False
            )
            
            # Determine if each entity is inclusion or exclusion based on position
            incl_end = combined_text.find("Exclusion Criteria:")
            
            for entity in entities:
                start = entity.get("start", 0)
                text = entity.get("text", "").strip()
                label = entity.get("label", "")
                score = entity.get("score", 0.0)
                
                # Determine inclusion vs exclusion
                is_exclusion = start > incl_end if incl_end > 0 else "Exclusion" in label.lower()
                
                # Parse entity into criterion
                criterion = self._parse_entity_to_criterion(text, label, score, is_exclusion)
                
                if criterion:
                    target_list = exclusions if is_exclusion else inclusions
                    target_list.append(criterion)
            
            logger.info(f"GLiNER found: {len(inclusions)} inclusions, {len(exclusions)} exclusions")
        
        except Exception as e:
            logger.error(f"GLiNER extraction error: {e}")
        
        return inclusions, exclusions
    
    @staticmethod
    def _extract_numeric_value(match: re.Match, pattern_name: str) -> Any:
        """Extract numeric value from regex match groups."""
        try:
            if pattern_name == "age":
                min_val = int(match.group(1)) if match.group(1) else None
                max_val = int(match.group(2)) if match.lastindex >= 2 and match.group(2) else None
                if min_val is None:
                    return None
                return {"min": min_val, **({"max": max_val} if max_val else {})}
            
            elif pattern_name in ["hba1c", "fasting_glucose", "bmi", "egfr", "creatinine"]:
                min_val = float(match.group(1)) if match.group(1) else None
                max_val = float(match.group(2)) if match.lastindex >= 2 and match.group(2) else None
                if min_val is None:
                    return None
                return {"min": min_val, **({"max": max_val} if max_val else {})}
            
            elif pattern_name == "diabetes_duration":
                val = match.group(1) if match.group(1) else None
                if not val:
                    return None
                return {"duration": int(val), "unit": "months"}
            
            elif pattern_name == "blood_pressure":
                systolic = int(match.group(1)) if match.group(1) else None
                diastolic = int(match.group(2)) if match.lastindex >= 2 and match.group(2) else None
                if systolic is None:
                    return None
                return {"systolic": systolic, **({"diastolic": diastolic} if diastolic else {})}
            
            return None
        except (IndexError, ValueError, AttributeError) as e:
            logger.warning(f"Error extracting numeric value from {pattern_name}: {e}")
            return None
    
    @staticmethod
    def _parse_entity_to_criterion(text: str, label: str, score: float, is_exclusion: bool) -> Optional[Dict]:
        """Convert GLiNER entity to criterion dict."""
        # Try to extract numeric value from entity text
        value = None
        unit = None
        
        # Match specific entity types to criteria
        if "age" in label.lower():
            numbers = re.findall(r"\d+", text)
            if numbers:
                if len(numbers) >= 2:
                    value = {"min": int(numbers[0]), "max": int(numbers[1])}
                else:
                    value = {"min": int(numbers[0])}
                unit = "years"
        
        elif "hba1c" in label.lower():
            numbers = re.findall(r"\d+\.?\d*", text)
            if numbers:
                if len(numbers) >= 2:
                    value = {"min": float(numbers[0]), "max": float(numbers[1])}
                else:
                    value = {"min": float(numbers[0])}
                unit = "%"
        
        elif "glucose" in label.lower():
            numbers = re.findall(r"\d+\.?\d*", text)
            if numbers:
                if len(numbers) >= 2:
                    value = {"min": float(numbers[0]), "max": float(numbers[1])}
                else:
                    value = {"min": float(numbers[0])}
                unit = "mg/dL"
        
        elif "bmi" in label.lower():
            numbers = re.findall(r"\d+\.?\d*", text)
            if numbers:
                value = {"min": float(numbers[0])}
                if len(numbers) >= 2:
                    value["max"] = float(numbers[1])
                unit = "kg/m²"
        
        elif "egfr" in label.lower() or "creatinine" in label.lower():
            numbers = re.findall(r"\d+\.?\d*", text)
            if numbers:
                value = float(numbers[0])
                unit = "mL/min/1.73m²" if "egfr" in label.lower() else "mg/dL"
        
        elif "diabetes" in label.lower():
            value = text
        
        else:
            value = text  # fallback: use original text
        
        if value is None:
            return None
        
        # Determine category
        category = "Lab" if any(x in label.lower() for x in ["hba1c", "glucose", "bmi", "egfr", "creatinine", "blood pressure"]) else "Condition"
        if "age" in label.lower():
            category = "Demographic"
        elif "duration" in label.lower():
            category = "Duration"
        
        return {
            "category": category,
            "field_name": label.lower().replace(" ", "_"),
            "value": value,
            "unit": unit,
            "negated": is_exclusion,
            "confidence": score,
            "source": "gliner",
            "source_text": text
        }
    
    @staticmethod
    def _merge_criteria(
        regex_crit: List[Dict],
        gliner_crit: List[Dict],
        source_type: str = "inclusion"
    ) -> List[Dict]:
        """
        Intelligently merge regex and GLiNER criteria.
        
        Strategy:
        - Prefer GLiNER for semantic understanding (confidence > 0.7)
        - Use regex for high-precision numeric extraction
        - Avoid duplicates
        """
        merged = {}  # field_name -> criterion dict
        
        # Add regex criteria (baseline)
        for crit in regex_crit:
            field = crit.get("field_name", "unknown")
            merged[field] = crit
        
        # Overlay with GLiNER (higher priority if confidence > 0.7)
        for crit in gliner_crit:
            field = crit.get("field_name", "unknown")
            gliner_conf = crit.get("confidence", 0.0)
            
            if field not in merged or gliner_conf > 0.7:
                merged[field] = crit
        
        # Convert back to list
        return list(merged.values())
    
    def batch_parse_trials(self, trials: List[Dict]) -> List[StructuredTrialCriteria]:
        """Parse multiple trials efficiently."""
        results = []
        
        for i, trial in enumerate(trials):
            try:
                structured = self.parse_trial(trial)
                results.append(structured)
                
                if (i + 1) % 10 == 0:
                    logger.info(f"Parsed {i + 1}/{len(trials)} trials")
            
            except Exception as e:
                logger.error(f"Error parsing trial {trial.get('nct_id')}: {e}")
                continue
        
        logger.info(f"✓ Successfully parsed {len(results)}/{len(trials)} trials")
        return results


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def convert_to_module3_format(structured: StructuredTrialCriteria) -> Dict:
    """
    Convert Module 2 output to Module 3 input format.
    
    Module 3 needs structured criteria for patient matching.
    """
    return {
        "nct_id": structured.nct_id,
        "title": structured.title,
        "inclusions": structured.inclusions,
        "exclusions": structured.exclusions,
        "parse_confidence": structured.parse_confidence,
        "parsed_at": structured.parsed_at,
        "total_entities": structured.total_entities,
    }


# ============================================================================
# EXAMPLE USAGE & TESTING
# ============================================================================

if __name__ == "__main__":
    
    # Example trial from Module 1
    sample_trial = {
        "nct_id": "NCT03042325",
        "title": "Safety and Efficacy of Alogliptin in Indian Participants With Type 2 Diabetes",
        "inclusion_criteria": """
            - Adults aged 18 to 75 years
            - Diagnosed with Type 2 Diabetes Mellitus for at least 6 months
            - HbA1c between 7.0% and 10.0% at screening
            - BMI ≥ 27 kg/m²
            - Fasting glucose 110-270 mg/dL
            - eGFR ≥ 45 mL/min/1.73m²
        """,
        "exclusion_criteria": """
            - Prior use of insulin for diabetes
            - eGFR < 45 mL/min/1.73m²
            - Serum creatinine > 1.5 mg/dL
            - Active cardiovascular disease
            - History of severe hypoglycemia in past 12 months
            - Pregnancy or nursing
        """
    }
    
    print("\n" + "="*70)
    print("MODULE 2: TRIAL CRITERIA PARSER - TEST")
    print("="*70)
    
    # Initialize parser (regex-only if GLiNER not available)
    parser = TrialCriteriaParser(use_gliner=True)
    
    # Parse trial
    print(f"\nParsing trial: {sample_trial['nct_id']}")
    print(f"Title: {sample_trial['title']}")
    
    structured = parser.parse_trial(sample_trial, threshold=0.5)
    
    # Display results
    print(f"\n✓ Parse Complete!")
    print(f"  Source mix: {structured.source_mix}")
    print(f"  Total entities: {structured.total_entities}")
    print(f"  Avg confidence: {structured.parse_confidence:.3f}")
    
    print(f"\nInclusions ({len(structured.inclusions)}):")
    for inc in structured.inclusions:
        print(f"  • {inc['field_name']}: {inc['value']} {inc.get('unit', '')}")
    
    print(f"\nExclusions ({len(structured.exclusions)}):")
    for exc in structured.exclusions:
        print(f"  • {exc['field_name']}: {exc['value']} {exc.get('unit', '')}")
    
    # Convert to Module 3 format
    print(f"\nConverting to Module 3 format...")
    m3_input = convert_to_module3_format(structured)
    print(f"✓ Ready for Module 3 (Patient Feature Extraction)")
    
    # Save example output
    output_file = "module2_parsed_trial_example.json"
    with open(output_file, "w") as f:
        # Convert to JSON-serializable format
        output = {
            "nct_id": m3_input["nct_id"],
            "title": m3_input["title"],
            "inclusions": m3_input["inclusions"],
            "exclusions": m3_input["exclusions"],
            "parse_confidence": round(m3_input["parse_confidence"], 3),
            "parsed_at": m3_input["parsed_at"],
        }
        json.dump(output, f, indent=2)
    
    print(f"\n✓ Example output saved to: {output_file}")
