"""
extractor.py

Generalised OCR + feature extraction for clinical lab reports (PDFs or images).

Usage:
    python extractor.py /path/to/report.pdf [--json] [--save]

Requirements (recommended):
    pip install pytesseract pillow pdf2image regex PyMuPDF
    - On Windows, install Tesseract OCR and add to PATH.

The script returns a JSON-like dict with extracted fields (age, gender, labs, locations,
raw_text, parse_confidence). It's built to dynamically parse all metrics using bounding boxes.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    from PIL import Image
except Exception:
    Image = None  # type: ignore

try:
    import pytesseract
except Exception:
    pytesseract = None  # type: ignore

try:
    import fitz
except Exception:
    fitz = None  # type: ignore

# ─────────────────────────────────────────────
# Directory where JSON outputs are persisted
# ─────────────────────────────────────────────
OUTPUT_DIR = Path(os.getenv("LAB_OUTPUT_DIR", "extracted_results"))


def ocr_from_image(image: "Image.Image") -> str:
    if pytesseract is None:
        return ""
    try:
        return pytesseract.image_to_string(image)
    except Exception:
        return ""


def ocr_file(path: str) -> str:
    """Extract raw string text for demographics parsing."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    lower = path.lower()
    text_parts: List[str] = []
    if lower.endswith(".pdf") and fitz:
        try:
            doc = fitz.open(path)
            for page in doc:
                text = page.get_text()
                if text.strip():
                    text_parts.append(text)
            if text_parts:
                doc.close()
                return "\n".join(text_parts)
            for page in doc:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                mode = "RGBA" if pix.alpha else "RGB"
                if Image:
                    img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                    text_parts.append(ocr_from_image(img))
            doc.close()
        except Exception:
            pass
    elif Image and pytesseract:
        try:
            img = Image.open(path)
            text_parts.append(ocr_from_image(img))
        except Exception:
            pass
    return "\n".join(text_parts)


def parse_demographics(text: str) -> Dict:
    t = text.lower()

    patient_id = None
    m = re.search(r"(?:lab no\.?|lab no|lab\s+no|patient\s+id)[:\s]*([a-z0-9_\-]+)", t)
    if m:
        patient_id = m.group(1).strip().upper()

    age = None
    m = re.search(r"\bage\s*[:\-]?\s*(\d{1,3})\s*(?:years|yrs)?\b", t)
    if m:
        try:
            val = int(m.group(1))
            if 0 <= val <= 120:
                age = val
        except Exception:
            pass
    if age is None:
        m = re.search(r"(\d{1,3})\s*(?:years|yrs)\b", t)
        if m:
            try:
                val = int(m.group(1))
                if 0 <= val <= 120:
                    age = val
            except Exception:
                pass

    gender = None
    m = re.search(r"gender\s*[:\-]?\s*(male|female|m|f)\b", t)
    if m:
        g = m.group(1).strip()
        gender = "Male" if g.lower().startswith("m") else "Female"
    if gender is None:
        if re.search(r"\bMale\b", text):
            gender = "Male"
        elif re.search(r"\bFemale\b", text):
            gender = "Female"

    reported = None
    m = re.search(
        r"(?:reported|report released on|date of collection)\s*[:\-]?\s*([0-9/\-]+)", t
    )
    if m:
        reported = m.group(1).strip()

    return {
        "patient_id": patient_id,
        "age":        age,
        "gender":     gender,
        "reported":   reported,
    }


def is_float(s: str) -> bool:
    try:
        float(s)
        return True
    except Exception:
        return False


def is_recognized_value(s: str) -> bool:
    if is_float(s):
        return True
    if s.lower() in ["nil", "negative", "positive", "positive(+)"]:
        return True
    if re.match(r"^\d+-\d+$", s):
        return True
    return False


def is_unit(s: str) -> bool:
    s = s.lower()
    if s in ["%", "ratio", "pg", "fl", "f l", "mili/cu.mm", "10^3/ul"]:
        return True
    if "/" in s:
        return True
    if s in ["u/l", "u/ml", "uiu/ml"]:
        return True
    return False


def is_range(s: str, s_next: Optional[str] = None) -> bool:
    if re.search(r"^\d+\.?\d*-\d+\.?\d*$", s):
        return True
    if s in ["<", "<=", ">", ">="] and s_next and is_float(s_next):
        return True
    if s.startswith("<") or s.startswith(">"):
        return is_float(s[1:]) or is_float(s[2:])
    if s_next == "-" and is_float(s):
        return True
    return False


def get_lines_from_path(path: str) -> List[List[str]]:
    all_lines: List[List[str]] = []
    if path.lower().endswith(".pdf") and fitz:
        try:
            doc = fitz.open(path)
            for page in doc:
                words = page.get_text("words")
                lines: list = []
                for w in words:
                    y_c = (w[1] + w[3]) / 2.0
                    added = False
                    for ln in lines:
                        if abs(ln["y"] - y_c) < 5:
                            ln["words"].append(w)
                            added = True
                            break
                    if not added:
                        lines.append({"y": y_c, "words": [w]})
                lines.sort(key=lambda ln: ln["y"])
                for ln in lines:
                    ln["words"].sort(key=lambda ww: ww[0])
                    all_lines.append([ww[4] for ww in ln["words"]])
            doc.close()
        except Exception:
            pass
    elif Image and pytesseract:
        try:
            img = Image.open(path)
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            words = [
                (
                    data["left"][i],
                    data["top"][i],
                    data["left"][i] + data["width"][i],
                    data["top"][i] + data["height"][i],
                    data["text"][i].strip(),
                )
                for i in range(len(data["text"]))
                if int(data["conf"][i]) > 10 and data["text"][i].strip()
            ]
            lines2: list = []
            for w in words:
                y_c = (w[1] + w[3]) / 2.0
                added = False
                for ln in lines2:
                    if abs(ln["y"] - y_c) < 10:
                        ln["words"].append(w)
                        added = True
                        break
                if not added:
                    lines2.append({"y": y_c, "words": [w]})
            lines2.sort(key=lambda ln: ln["y"])
            for ln in lines2:
                ln["words"].sort(key=lambda ww: ww[0])
                all_lines.append([ww[4] for ww in ln["words"]])
        except Exception:
            pass
    return all_lines


def extract_metrics_from_lines(lines: List[List[str]]) -> Dict[str, Dict]:
    labs: Dict[str, Dict] = {}
    for tokens in lines:
        for idx, token in enumerate(tokens):
            if is_recognized_value(token):
                if idx == 0:
                    continue
                name   = " ".join(tokens[0:idx]).strip()
                name_l = name.lower()

                # Exclude likely non-test lines
                if any(name_l.startswith(s) for s in
                       ["page", "date", "age", "result", "males", "females"]):
                    continue
                if len(name) < 2 or name[0].isdigit():
                    continue
                if len(name.split()) > 6:
                    continue
                if "level of" in name_l or "goal" in name_l or "meal" in name_l:
                    continue

                value     = token
                unit      = None
                has_unit  = False
                has_range = False

                if idx + 1 < len(tokens):
                    if is_unit(tokens[idx + 1]):
                        has_unit = True
                        unit     = tokens[idx + 1]

                    check_idx = idx + 2 if has_unit else idx + 1
                    if check_idx < len(tokens):
                        nt = tokens[check_idx]
                        nn = tokens[check_idx + 1] if check_idx + 1 < len(tokens) else None
                        if is_range(nt, nn):
                            has_range = True

                # Save first match per test name
                if (has_unit or has_range) and name not in labs:
                    labs[name] = {
                        "value":    value,
                        "unit":     unit if unit else "",
                        "raw_line": " ".join(tokens),
                    }
                break   # stop after first value match per line
    return labs


def process_file(path: str) -> Dict:
    """Full pipeline: OCR → demographics → lab metrics."""
    text   = ocr_file(path)
    result = parse_demographics(text)

    lines = get_lines_from_path(path)
    labs  = extract_metrics_from_lines(lines)

    result["labs"]             = labs
    result["source_file"]      = os.path.abspath(path)
    result["raw_text_snippet"] = text[:600]
    result["parse_confidence"] = 1.0 if labs else 0.0
    return result


# ─────────────────────────────────────────────────────────────────────────────
# process_and_save  —  called by run_pipeline.py
# ─────────────────────────────────────────────────────────────────────────────
def process_and_save(pdf_path: str, output_dir: Optional[str] = None) -> Dict:
    """
    Run the full extraction pipeline and save result as JSON.

    Returns:
        {
            "result":      <extraction dict>,
            "output_file": <absolute path to saved JSON>,
            "status":      "ok" | "error",
            "message":     <human-readable summary>
        }
    """
    out_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = process_file(pdf_path)
    except Exception as exc:
        return {
            "result":      {},
            "output_file": None,
            "status":      "error",
            "message":     str(exc),
        }

    pid      = result.get("patient_id") or "UNKNOWN"
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem     = Path(pdf_path).stem
    filename = f"{stem}_{pid}_{ts}.json"
    out_path = out_dir / filename

    result["_saved_at"] = datetime.now().isoformat()

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)

    return {
        "result":      result,
        "output_file": str(out_path.resolve()),
        "status":      "ok",
        "message": (
            f"Extracted {len(result.get('labs', {}))} lab metrics. "
            f"Saved → {out_path}"
        ),
    }


def _format_report(result: Dict) -> str:
    output = []
    output.append("\n" + "=" * 70)
    output.append("CLINICAL LAB REPORT EXTRACTION SUMMARY")
    output.append("=" * 70 + "\n")

    output.append("📋 PATIENT INFORMATION")
    output.append("-" * 70)
    output.append(f"  Patient ID:    {result.get('patient_id', 'N/A')}")
    output.append(f"  Age:           {result.get('age', 'N/A')} years")
    output.append(f"  Gender:        {result.get('gender', 'N/A')}")
    output.append(f"  Report Date:   {result.get('reported', 'N/A')}")
    output.append("")

    labs = result.get("labs", {})
    if labs:
        output.append("🧪 LABORATORY RESULTS")
        output.append("-" * 70)
        for key, lab_data in labs.items():
            val  = lab_data.get("value", "N/A")
            unit = lab_data.get("unit", "")
            output.append(f"  {key:25s} | {val:8s} | {unit}")
        output.append(f"\n  Total Metrics Found: {len(labs)}")
    else:
        output.append("🧪 LABORATORY RESULTS: No labs extracted")

    output.append("")
    conf = result.get("parse_confidence", 0)
    output.append("📊 EXTRACTION QUALITY")
    output.append("-" * 70)
    output.append(f"  Confidence:    {conf * 100:.0f}%")
    output.append("=" * 70 + "\n")
    return "\n".join(output)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extractor.py /path/to/report.pdf [--json] [--save]")
        sys.exit(1)

    path        = sys.argv[1]
    json_output = "--json" in sys.argv
    auto_save   = "--save" in sys.argv

    try:
        if auto_save:
            outcome = process_and_save(path)
            print(json.dumps(outcome, indent=2, ensure_ascii=False))
        else:
            out = process_file(path)
            if json_output:
                print(json.dumps(out, indent=2, ensure_ascii=False))
            else:
                print(_format_report(out))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(2)