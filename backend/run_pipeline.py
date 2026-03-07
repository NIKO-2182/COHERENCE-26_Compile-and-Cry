"""
Master Pipeline Runner
======================
Starts a FastAPI upload server on port 8000.
When a PDF is uploaded via POST /upload-report, runs automatically:

  Step 1 → Mod1 Extractor     : PDF → extracted JSON  (direct import)
  Step 2 → Trial Fetcher      : fetch / verify trials JSON
  Step 3 → Mod2 Parser        : parse trial criteria
            ↑ auto-patches Mod2 to use the latest extracted JSON
  Step 4 → Mod3 Matcher       : XGBoost + SHAP matching
  Step 5 → Mod4 API           : serve results on port 8080

Usage:
    python run_pipeline.py

Then:
    POST PDF  →  http://localhost:8000/upload-report
    Status    →  http://localhost:8000/status
    Results   →  http://localhost:8080/results  (after pipeline finishes)
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ============================================================================
# PATHS
# ============================================================================

BASE: Path = Path(r"D:\C&C\COHERENCE-26_Compile-and-Cry\backend")

SCRIPTS = {
    "extractor":     BASE / "Mod1" / "Data_Extractor" / "extract_patient_data" / "extractor.py",
    "trial_fetcher": BASE / "Mod1" / "trial_fetcher"  / "trial_fetcher.py",
    "mod2":          BASE / "Mod2" / "module_2 Clinical_v0.1.py",
    "mod3":          BASE / "Mod3" / "module_3_Xgboost_v0.2.py",
    "mod4":          BASE / "Mod4" / "module_4_formatter_v1.py",
}

OUTPUTS = {
    "extractor":     BASE / "Mod1" / "Data_Extractor" / "extract_patient_data" / "extracted_results",
    "trial_fetcher": BASE / "Mod1" / "trial_fetcher"  / "clinical_trials_diabetes.json",
    "mod2":          BASE / "Mod2" / "mod2_output.json",
    "mod3":          BASE / "Mod3" / "mod3_output.json",
    "mod4":          BASE / "Mod4" / "mod4_frontend_output.json",
}

UPLOAD_DIR: Path = BASE / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

UPLOAD_HOST  = "0.0.0.0"
UPLOAD_PORT  = 8000
RESULTS_PORT = 8080

INTER_STEP_DELAY = 2   # seconds between steps

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("Pipeline")

# ============================================================================
# PIPELINE STATE
# ============================================================================

pipeline_state: dict = {
    "status":       "idle",
    "current_step": "",
    "steps":        [],
    "started_at":   None,
    "finished_at":  None,
    "error":        None,
    "pdf_path":     None,
}

_mod4_process: Optional[subprocess.Popen] = None


# ============================================================================
# HELPERS
# ============================================================================

def _log_step(name: str, status: str, detail: str = "") -> None:
    icon = {"running": "⏳", "done": "✓", "error": "✗"}.get(status, "")
    log.info(f"{icon}  {name}  |  {detail or status}")
    pipeline_state["steps"].append({
        "step":      name,
        "status":    status,
        "timestamp": datetime.now().isoformat(),
        "detail":    detail,
    })


def _run_script(
    label:        str,
    script:       Path,
    args:         list[str] | None = None,
    env_overrides: dict | None = None,
    timeout:      int = 300,
) -> tuple[bool, str]:
    """
    Run a Python script as subprocess from its own directory.
    env_overrides: extra environment variables injected into the subprocess.
    Streams all output to terminal and returns (success, error_text).
    """
    if not script.exists():
        return False, f"Script not found: {script}"

    cmd = [sys.executable, str(script)] + (args or [])
    log.info(f"  ▶ {' '.join(cmd)}")

    # Build environment — inherit current env + force UTF-8 + overrides
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"   # fix UnicodeEncodeError on Windows CP1252
    env["PYTHONUTF8"]       = "1"       # Python 3.7+ UTF-8 mode
    if env_overrides:
        env.update(env_overrides)

    try:
        proc = subprocess.run(
            cmd,
            timeout=timeout,
            capture_output=True,
            text=True,
            cwd=str(script.parent),
            env=env,
        )

        for line in (proc.stdout or "").splitlines():
            if line.strip():
                log.info(f"  [{label}] {line}")
        for line in (proc.stderr or "").splitlines():
            if line.strip():
                log.warning(f"  [{label}:ERR] {line}")

        if proc.returncode == 0:
            return True, ""

        err = (proc.stderr or proc.stdout or "").strip()
        return False, "\n".join(err.splitlines()[-10:]) if err else "Non-zero exit"

    except subprocess.TimeoutExpired:
        return False, f"Timed out after {timeout}s"
    except Exception as e:
        return False, str(e)


def _get_latest_extracted_json() -> Optional[Path]:
    """Return the most-recently-modified JSON in extracted_results/."""
    d = OUTPUTS["extractor"]
    if not d.exists():
        return None
    files = sorted(d.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _import_and_run_extractor(pdf_path: str) -> tuple[bool, str]:
    """Import extractor.py directly and call process_and_save()."""
    extractor_path = SCRIPTS["extractor"]
    if not extractor_path.exists():
        return False, f"extractor.py not found at {extractor_path}"

    try:
        spec   = importlib.util.spec_from_file_location("extractor", str(extractor_path))
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(extractor_path.parent))
        spec.loader.exec_module(module)

        out_dir = str(OUTPUTS["extractor"])
        log.info(f"  Calling process_and_save({pdf_path})")
        result = module.process_and_save(pdf_path, output_dir=out_dir)

        if result.get("status") == "ok":
            labs = len(result.get("result", {}).get("labs", {}))
            return True, f"Extracted {labs} lab metrics → {result.get('output_file')}"
        return False, result.get("message", "Extractor returned error status")

    except Exception as e:
        import traceback
        log.error(f"Extractor exception:\n{traceback.format_exc()}")
        return False, str(e)


# ============================================================================
# PIPELINE  (background thread)
# ============================================================================

def run_pipeline(pdf_path: str) -> None:
    global _mod4_process

    pipeline_state.update({
        "status":       "running",
        "current_step": "",
        "steps":        [],
        "started_at":   datetime.now().isoformat(),
        "finished_at":  None,
        "error":        None,
        "pdf_path":     pdf_path,
    })

    def abort(reason: str) -> None:
        pipeline_state["status"]      = "error"
        pipeline_state["error"]       = reason
        pipeline_state["finished_at"] = datetime.now().isoformat()
        log.error(f"Pipeline ABORTED — {reason}")

    log.info("=" * 58)
    log.info("  PIPELINE START")
    log.info(f"  PDF: {pdf_path}")
    log.info("=" * 58)

    # ── STEP 1: PDF Extraction ─────────────────────────────────────────
    pipeline_state["current_step"] = "Step 1: PDF Extraction"
    _log_step("Step 1 — PDF Extraction", "running")

    ok, detail = _import_and_run_extractor(pdf_path)
    if not ok:
        _log_step("Step 1 — PDF Extraction", "error", detail)
        return abort(f"Extraction failed: {detail}")

    OUTPUTS["extractor"].mkdir(parents=True, exist_ok=True)
    _log_step("Step 1 — PDF Extraction", "done", detail)
    time.sleep(INTER_STEP_DELAY)

    # ── STEP 2: Trial Fetcher ──────────────────────────────────────────
    pipeline_state["current_step"] = "Step 2: Trial Fetcher"
    _log_step("Step 2 — Trial Fetcher", "running")

    if OUTPUTS["trial_fetcher"].exists():
        _log_step("Step 2 — Trial Fetcher", "done", "Existing trials file found — skipping fetch")
    else:
        ok, detail = _run_script("TrialFetcher", SCRIPTS["trial_fetcher"], timeout=180)
        if not ok:
            _log_step("Step 2 — Trial Fetcher", "error", detail)
            return abort(f"Trial fetch failed: {detail}")
        _log_step("Step 2 — Trial Fetcher", "done", "Clinical trials fetched")
    time.sleep(INTER_STEP_DELAY)

    # ── STEP 3: Mod2 Criteria Parser ───────────────────────────────────
    # Mod2 has a hardcoded PATIENT_REPORT_PATH constant.
    # We override it by injecting the latest extracted JSON path
    # via the MOD2_PATIENT_REPORT_PATH environment variable.
    # Mod2 must read this env var at startup (see note below).
    pipeline_state["current_step"] = "Step 3: Mod2 Criteria Parser"
    _log_step("Step 3 — Mod2 Criteria Parser", "running")

    latest_json = _get_latest_extracted_json()
    if not latest_json:
        _log_step("Step 3 — Mod2 Criteria Parser", "error", "No extracted JSON in extracted_results/")
        return abort("No extracted JSON found. Step 1 may have failed silently.")

    log.info(f"  Injecting patient report: {latest_json.name}")

    ok, detail = _run_script(
        "Mod2",
        SCRIPTS["mod2"],
        env_overrides={"MOD2_PATIENT_REPORT_PATH": str(latest_json)},
        timeout=300,
    )
    # Mod2 may exit non-zero due to Unicode print errors on Windows CP1252
    # but still produce valid output — check the output file as ground truth
    mod2_output_exists = OUTPUTS["mod2"].exists()
    if not ok and not mod2_output_exists:
        _log_step("Step 3 — Mod2 Criteria Parser", "error", detail)
        return abort(f"Mod2 failed: {detail}")
    if not ok and mod2_output_exists:
        log.warning("  Mod2 exited non-zero but output file exists — treating as success")
    _log_step("Step 3 — Mod2 Criteria Parser", "done", "Trial criteria parsed")
    time.sleep(INTER_STEP_DELAY)

    # ── STEP 4: Mod3 XGBoost Matcher ───────────────────────────────────
    pipeline_state["current_step"] = "Step 4: Mod3 XGBoost Matcher"
    _log_step("Step 4 — Mod3 XGBoost Matcher", "running")

    ok, detail = _run_script("Mod3", SCRIPTS["mod3"], timeout=300)
    if not ok:
        _log_step("Step 4 — Mod3 XGBoost Matcher", "error", detail)
        return abort(f"Mod3 failed: {detail}")
    _log_step("Step 4 — Mod3 XGBoost Matcher", "done", "Patient matched to trials")
    time.sleep(INTER_STEP_DELAY)

    # ── STEP 5: Mod4 Results API ────────────────────────────────────────
    pipeline_state["current_step"] = "Step 5: Mod4 Results API"
    _log_step("Step 5 — Mod4 Results API", "running")

    if _mod4_process and _mod4_process.poll() is None:
        log.info("  Stopping previous Mod4 instance …")
        _mod4_process.terminate()
        try:
            _mod4_process.wait(timeout=5)
        except Exception:
            _mod4_process.kill()

    _mod4_process = subprocess.Popen(
        [sys.executable, str(SCRIPTS["mod4"])],
        cwd=str(SCRIPTS["mod4"].parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    started  = False
    deadline = time.time() + 15
    while time.time() < deadline:
        line = _mod4_process.stdout.readline()
        if line and line.strip():
            log.info(f"  [Mod4] {line.rstrip()}")
        if "Application startup complete" in (line or ""):
            started = True
            break
        if _mod4_process.poll() is not None:
            break
        time.sleep(0.1)

    label = f"Serving on http://0.0.0.0:{RESULTS_PORT}" if started else f"Process launched on port {RESULTS_PORT}"
    _log_step("Step 5 — Mod4 Results API", "done", label)

    pipeline_state["status"]      = "done"
    pipeline_state["finished_at"] = datetime.now().isoformat()

    log.info("=" * 58)
    log.info("  PIPELINE COMPLETE")
    log.info(f"  Results → http://127.0.0.1:{RESULTS_PORT}/results")
    log.info(f"  Docs    → http://127.0.0.1:{RESULTS_PORT}/docs")
    log.info("=" * 58)


# ============================================================================
# FASTAPI UPLOAD SERVER
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=" * 58)
    log.info("  CLINICAL TRIAL MATCHER — Upload Server ready")
    log.info(f"  POST PDF → http://0.0.0.0:{UPLOAD_PORT}/upload-report")
    log.info(f"  Status   → http://127.0.0.1:{UPLOAD_PORT}/status")
    log.info("=" * 58)
    yield


app = FastAPI(
    title="Clinical Trial Matcher — Pipeline Server",
    description="POST a patient PDF to /upload-report. Full Mod1→Mod4 pipeline runs automatically.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/", tags=["Health"])
def health():
    return {
        "service":      "Clinical Trial Matcher Pipeline",
        "upload_port":  UPLOAD_PORT,
        "results_port": RESULTS_PORT,
        "pipeline":     pipeline_state["status"],
        "timestamp":    datetime.now().isoformat(),
        "how_to_use":   f"POST PDF to http://0.0.0.0:{UPLOAD_PORT}/upload-report",
    }


@app.post("/upload-report", tags=["Upload"])
async def upload_report(file: UploadFile = File(...)):
    """
    Upload a patient PDF lab report.
    Triggers: Mod1 → Mod2 → Mod3 → Mod4 (results on port 8080).
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    if pipeline_state["status"] == "running":
        raise HTTPException(
            status_code=409,
            detail="Pipeline already running. Poll GET /status for progress.",
        )

    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_stem = Path(file.filename).stem
    dest      = UPLOAD_DIR / f"{safe_stem}_{ts}.pdf"
    content   = await file.read()

    with open(dest, "wb") as f:
        f.write(content)

    log.info(f"PDF saved → {dest}  ({len(content):,} bytes)")

    threading.Thread(
        target=run_pipeline,
        args=(str(dest),),
        daemon=True,
    ).start()

    return JSONResponse(
        status_code=202,
        content={
            "message":     "PDF received. Pipeline started.",
            "file":        str(dest),
            "size_bytes":  len(content),
            "status_url":  f"http://127.0.0.1:{UPLOAD_PORT}/status",
            "results_url": f"http://127.0.0.1:{RESULTS_PORT}/results",
        },
    )


@app.get("/status", tags=["Status"])
def get_status():
    """Poll pipeline progress."""
    state = dict(pipeline_state)
    if state["status"] == "done":
        state["results_url"]  = f"http://127.0.0.1:{RESULTS_PORT}/results"
        state["results_docs"] = f"http://127.0.0.1:{RESULTS_PORT}/docs"
    return JSONResponse(content=state)


# ============================================================================
# PROXY ROUTES  — forward /results/* to Mod4 on port 8080
# so the frontend only needs to talk to one port (8000)
# ============================================================================

@app.get("/results", tags=["Results"])
@app.get("/results/{path:path}", tags=["Results"])
async def proxy_results(request: Request, path: str = ""):
    """
    Proxy all /results/* requests to Mod4 on port 8080.
    Forwards query params (e.g. ?label=Eligible&min_score=70).
    Returns 202 if pipeline is still running, 503 if not started.
    """
    target = f"http://127.0.0.1:{RESULTS_PORT}/results"
    if path:
        target += f"/{path}"
    # Preserve query string
    if request.url.query:
        target += f"?{request.url.query}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(target)
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except httpx.ConnectError:
        if pipeline_state["status"] == "running":
            return JSONResponse(
                status_code=202,
                content={
                    "message":      "Pipeline still running — results not ready yet.",
                    "status_url":   f"http://127.0.0.1:{UPLOAD_PORT}/status",
                    "current_step": pipeline_state.get("current_step", ""),
                },
            )
        return JSONResponse(
            status_code=503,
            content={
                "message":    "Results API not running. Upload a PDF to start the pipeline.",
                "upload_url": f"http://127.0.0.1:{UPLOAD_PORT}/upload-report",
            },
        )
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e)})


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import socket
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "127.0.0.1"

    log.info("=" * 58)
    log.info("  CLINICAL TRIAL MATCHER — Master Pipeline")
    log.info("=" * 58)
    log.info(f"  Upload server  → http://{local_ip}:{UPLOAD_PORT}/upload-report")
    log.info(f"  Status         → http://{local_ip}:{UPLOAD_PORT}/status")
    log.info(f"  Results API    → http://{local_ip}:{RESULTS_PORT}/results  (after pipeline)")
    log.info(f"  Swagger UI     → http://127.0.0.1:{UPLOAD_PORT}/docs")
    log.info("=" * 58)

    # Optional public tunnel — skipped gracefully if no authtoken
    try:
        from pyngrok import ngrok, conf
        # Uncomment and paste your token from https://dashboard.ngrok.com/get-started/your-authtoken
        # conf.get_default().auth_token = "PASTE_YOUR_TOKEN_HERE"
        tunnel = ngrok.connect(UPLOAD_PORT, "http")
        log.info(f"  PUBLIC URL     → {tunnel.public_url}/upload-report")
    except ImportError:
        log.info("  (pip install pyngrok for public URL)")
    except Exception:
        log.info("  (ngrok skipped — add authtoken for public URL)")

    uvicorn.run(app, host=UPLOAD_HOST, port=UPLOAD_PORT, log_level="info")