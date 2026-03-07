"""
extractor.py

Generalised OCR + feature extraction for clinical lab reports (PDFs or images).

Usage:
    python extractor.py /path/to/report.pdf --json

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

def ocr_from_image(image: Image.Image) -> str:
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
        except:
            pass
    elif Image and pytesseract:
        try:
            img = Image.open(path)
            text_parts.append(ocr_from_image(img))
        except:
            pass
    return "\n".join(text_parts)

def parse_demographics(text: str) -> Dict:
    t = text.lower()
    
    patient_id = None
    m = re.search(r"(?:lab no\.?|lab no|lab\s+no|patient\s+id)[:\s]*([a-z0-9_\-]+)", t)
    if m: patient_id = m.group(1).strip().upper()

    age = None
    m = re.search(r"\bage\s*[:\-]?\s*(\d{1,3})\s*(?:years|yrs)?\b", t)
    if m:
        try:
            val = int(m.group(1))
            if 0 <= val <= 120: age = val
        except: pass
    if age is None:
        m = re.search(r"(\d{1,3})\s*(?:years|yrs)\b", t)
        if m:
            try:
                val = int(m.group(1))
                if 0 <= val <= 120: age = val
            except: pass

    gender = None
    m = re.search(r"gender\s*[:\-]?\s*(male|female|m|f)\b", t)
    if m:
        g = m.group(1).strip()
        gender = "Male" if g.lower().startswith("m") else "Female"
    if gender is None:
        if re.search(r"\bMale\b", text): gender = "Male"
        elif re.search(r"\bFemale\b", text): gender = "Female"

    reported = None
    m = re.search(r"(?:reported|report released on|date of collection)\s*[:\-]?\s*([0-9/\-]+)", t)
    if m: reported = m.group(1).strip()
    
    return {
        "patient_id": patient_id,
        "age": age,
        "gender": gender,
        "reported": reported,
    }

def is_float(s):
    try:
        float(s)
        return True
    except: return False

def is_recognized_value(s):
    if is_float(s): return True
    if s.lower() in ["nil", "negative", "positive", "positive(+)"]: return True
    if re.match(r"^\d+-\d+$", s): return True
    return False

def is_unit(s):
    s = s.lower()
    if s in ['%', 'ratio', 'pg', 'fl', 'f l', 'mili/cu.mm', '10^3/ul']: return True
    if '/' in s: return True
    if s in ['u/l', 'u/ml', 'uiu/ml']: return True
    return False

def is_range(s, s_next=None):
    if re.search(r"^\d+\.?\d*-\d+\.?\d*$", s): return True
    if s in ['<', '<=', '>', '>='] and s_next and is_float(s_next): return True
    if s.startswith('<') or s.startswith('>'): return is_float(s[1:]) or is_float(s[2:])
    if s_next == '-' and is_float(s): return True
    return False

def get_lines_from_path(path: str) -> List[List[str]]:
    all_lines = []
    if path.lower().endswith(".pdf") and fitz:
        try:
            doc = fitz.open(path)
            for page in doc:
                words = page.get_text("words")
                lines = []
                for w in words:
                    y_c = (w[1] + w[3]) / 2.0
                    added = False
                    for l in lines:
                        if abs(l['y'] - y_c) < 5:
                            l['words'].append(w)
                            added = True
                            break
                    if not added: lines.append({'y': y_c, 'words': [w]})
                lines.sort(key=lambda l: l['y'])
                for l in lines:
                    l['words'].sort(key=lambda w: w[0])
                    all_lines.append([w[4] for w in l['words']])
            doc.close()
        except: pass
    elif Image and pytesseract:
        try:
            img = Image.open(path)
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            words = [(data['left'][i], data['top'][i], data['left'][i]+data['width'][i], data['top'][i]+data['height'][i], data['text'][i].strip())
                     for i in range(len(data['text'])) if int(data['conf'][i]) > 10 and data['text'][i].strip()]
            lines = []
            for w in words:
                y_c = (w[1] + w[3]) / 2.0
                added = False
                for l in lines:
                    if abs(l['y'] - y_c) < 10:
                        l['words'].append(w)
                        added = True
                        break
                if not added: lines.append({'y': y_c, 'words': [w]})
            lines.sort(key=lambda l: l['y'])
            for l in lines:
                l['words'].sort(key=lambda w: w[0])
                all_lines.append([w[4] for w in l['words']])
        except: pass
    return all_lines

def extract_metrics_from_lines(lines: List[List[str]]) -> Dict[str, Dict]:
    labs = {}
    for tokens in lines:
        for idx, token in enumerate(tokens):
            if is_recognized_value(token):
                if idx == 0: continue
                name = " ".join(tokens[0:idx]).strip()
                name_l = name.lower()
                
                # Exclude likely non-tests
                if any(name_l.startswith(s) for s in ["page", "date", "age", "result", "males", "females"]): continue
                if len(name) < 2 or name[0].isdigit(): continue
                if len(name.split()) > 6: continue
                if "level of" in name_l or "goal" in name_l or "meal" in name_l: continue
                
                value = token
                unit = None
                has_unit, has_range = False, False
                
                if idx + 1 < len(tokens):
                    if is_unit(tokens[idx+1]):
                        has_unit = True
                        unit = tokens[idx+1]
                    
                    check_idx = idx + 2 if has_unit else idx + 1
                    if check_idx < len(tokens):
                        nt = tokens[check_idx]
                        nn = tokens[check_idx+1] if check_idx+1 < len(tokens) else None
                        if is_range(nt, nn): has_range = True
                
                # Save first match per test name
                if (has_unit or has_range) and name not in labs:
                    labs[name] = {"value": value, "unit": unit if unit else "", "raw_line": " ".join(tokens)}
                break # stop checking tokens in this line once we matched the first
    return labs

def process_file(path: str) -> Dict:
    text = ocr_file(path)
    result = parse_demographics(text)
    
    lines = get_lines_from_path(path)
    labs = extract_metrics_from_lines(lines)
    
    result["labs"] = labs
    result["source_file"] = os.path.abspath(path)
    result["raw_text_snippet"] = text[:600]
    result["parse_confidence"] = 1.0 if labs else 0.0
    return result

def _format_report(result: Dict) -> str:
    output = []
    output.append("\n" + "="*70)
    output.append("CLINICAL LAB REPORT EXTRACTION SUMMARY")
    output.append("="*70 + "\n")

    output.append("📋 PATIENT INFORMATION")
    output.append("-" * 70)
    output.append(f"  Patient ID:    {result.get('patient_id', 'N/A')}")
    output.append(f"  Age:           {result.get('age', 'N/A')} years")
    output.append(f"  Gender:        {result.get('gender', 'N/A')}")
    output.append(f"  Report Date:   {result.get('reported', 'N/A')}")
    output.append("")

    labs = result.get('labs', {})
    if labs:
        output.append("🧪 LABORATORY RESULTS")
        output.append("-" * 70)
        for key, lab_data in labs.items():
            val = lab_data.get('value', 'N/A')
            unit = lab_data.get('unit', '')
            output.append(f"  {key:25s} | {val:8s} | {unit}")
        output.append(f"\n  Total Metrics Found: {len(labs)}")
    else:
        output.append("🧪 LABORATORY RESULTS: No labs extracted")
    
    output.append("")
    conf = result.get('parse_confidence', 0)
    output.append("📊 EXTRACTION QUALITY")
    output.append("-" * 70)
    output.append(f"  Confidence:    {conf*100:.0f}%")
    output.append("="*70 + "\n")
    return "\n".join(output)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extractor.py /path/to/report.pdf [--json]")
        sys.exit(1)
    
    path = sys.argv[1]
    json_output = "--json" in sys.argv
    
    try:
        out = process_file(path)
        if json_output:
            print(json.dumps(out, indent=2))
        else:
            print(_format_report(out))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(2)
