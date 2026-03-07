from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import tempfile
import os
import json
from datetime import datetime
from pathlib import Path
from extract_patient_data.extractor import process_file

app = FastAPI()

# Create results directory
RESULTS_DIR = Path(__file__).parent / "extracted_results"
RESULTS_DIR.mkdir(exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/upload-report")
async def upload_report(file: UploadFile = File(None), report: UploadFile = File(None)):
    """Receive PDF from frontend, extract data, and save to JSON"""
    try:
        # Accept file with either field name
        uploaded_file = file or report
        
        if not uploaded_file:
            return {"success": False, "error": "No file provided"}
        
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            contents = await uploaded_file.read()
            tmp.write(contents)
            tmp_path = tmp.name
        
        # Extract data
        result = process_file(tmp_path)
        os.remove(tmp_path)
        
        # Save extracted data to JSON file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = uploaded_file.filename.replace(".pdf", "").replace(" ", "_")
        json_filename = f"{filename}_{timestamp}.json"
        json_path = RESULTS_DIR / json_filename
        
        with open(json_path, "w") as f:
            json.dump(result, f, indent=2)
        
        return {
            "success": True, 
            "data": result,
            "saved_file": json_filename,
            "saved_path": str(json_path)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/analyze")
async def analyze(file: UploadFile = File(None), report: UploadFile = File(None)):
    """Receive PDF from frontend, extract data, and save to JSON"""
    try:
        uploaded_file = file or report
        if not uploaded_file:
            return {"success": False, "error": "No file provided"}
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            contents = await uploaded_file.read()
            tmp.write(contents)
            tmp_path = tmp.name
        
        result = process_file(tmp_path)
        os.remove(tmp_path)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = uploaded_file.filename.replace(".pdf", "").replace(" ", "_")
        json_filename = f"{filename}_{timestamp}.json"
        json_path = RESULTS_DIR / json_filename
        
        with open(json_path, "w") as f:
            json.dump(result, f, indent=2)
        
        return {
            "success": True, 
            "data": result,
            "saved_file": json_filename,
            "saved_path": str(json_path)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="192.168.137.226", port=8000)
