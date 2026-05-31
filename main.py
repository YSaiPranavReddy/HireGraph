"""
main.py — HireGraph FastAPI Backend

Endpoints:
  GET  /health          → liveness check
  POST /run/text        → run pipeline with raw JD text + uploaded PDF resumes
  POST /run/json        → run pipeline with pre-extracted JSON (for testing)
  GET  /models          → returns current LLM routing info

Run with:
  conda activate hiregraph
  uvicorn main:app --reload --port 8000
"""

import asyncio
import json
import os
import sys
import tempfile
import threading
import traceback
from typing import List, Optional

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from dotenv import load_dotenv
import httpx

load_dotenv()

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(__file__))

from graph.pipeline import run_pipeline
from utils.pdf_reader import extract_text_from_pdf
from utils.helpers import summarise_pipeline_result

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="HireGraph API",
    description="AI-powered multi-agent hiring pipeline",
    version="1.0.0",
)

frontend_url = os.getenv("FRONTEND_URL", os.getenv("FRONTEND_API_URL", ""))

origins = [
    "http://localhost:5173",   # Vite React dev server
    "http://localhost:4173",   # Vite preview
    "http://localhost:3000",   # fallback
]

if frontend_url:
    origins.append(frontend_url.rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Clerk JWT verification
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)

async def verify_clerk_token(
    credentials: HTTPAuthorizationCredentials = Security(_bearer)
):
    """
    Verify Clerk JWT on protected endpoints.
    - Extracts 'iss' from the unverified token to find the JWKS URL.
    - Fetches Clerk's public JWKS.
    - Returns the decoded payload.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = credentials.credentials
    try:
        from jose import jwt, jwk
        import httpx

        # 1. Decode without verification to get kid and iss
        unverified_header = jwt.get_unverified_header(token)
        unverified_claims = jwt.get_unverified_claims(token)
        
        kid = unverified_header.get("kid")
        iss = unverified_claims.get("iss")
        
        if not iss:
            raise HTTPException(status_code=401, detail="Token missing 'iss' claim")

        jwks_url = f"{iss.rstrip('/')}/.well-known/jwks.json"

        # 2. Fetch JWKS from the issuer
        async with httpx.AsyncClient() as client:
            resp = await client.get(jwks_url, timeout=5)
            resp.raise_for_status()
            jwks = resp.json()

        # 3. Find matching key
        key_data = next(
            (k for k in jwks.get("keys", []) if k.get("kid") == kid),
            None
        )
        if not key_data:
            raise HTTPException(status_code=401, detail="JWT key not found in JWKS")

        # 4. Verify token
        public_key = jwk.construct(key_data)
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        return payload

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class RunJsonRequest(BaseModel):
    """For programmatic testing — pass pre-extracted text directly."""
    job_description: str
    resumes: List[dict]   # [{"file_name": str, "raw_text": str}]


class HealthResponse(BaseModel):
    status: str
    version: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["Meta"])
def health():
    """Liveness check — returns 200 if the server is up."""
    return {"status": "ok", "version": "1.0.0"}


@app.get("/models", tags=["Meta"])
def model_info():
    """Returns the LLM routing configuration."""
    return {
        "jd_parser":         "groq/llama-3.1-8b-instant",
        "resume_screener":   "groq/llama-3.1-8b-instant",
        "ranker":            "groq/llama-3.3-70b-versatile",
        "bias_checker":      "groq/llama-3.3-70b-versatile",
        "outreach_drafter":  "groq/llama-3.3-70b-versatile",
    }


@app.post("/parse-jd", tags=["Utils"])
async def parse_jd_pdf(
    jd_pdf: UploadFile = File(..., description="JD as a PDF file"),
    _user = Depends(verify_clerk_token),
):
    """Extract raw text from a JD PDF file without running the pipeline."""
    if not jd_pdf.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Must be a PDF file")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        content = await jd_pdf.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        extracted_text = extract_text_from_pdf(tmp_path)
        return {"extracted_text": extracted_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF extraction failed: {str(e)}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@app.post("/run/text", tags=["Pipeline"])
async def run_from_uploads(
    resumes: List[UploadFile] = File(..., description="Resume PDFs"),
    jd_text:   Optional[str]       = Form(None, description="Raw JD text (use this OR jd_pdf)"),
    jd_pdf:    Optional[UploadFile] = File(None, description="JD as a PDF (use this OR jd_text)"),
    team_data: Optional[str]       = Form(None, description="Existing team CSV/JSON (optional — enables team gap scoring)"),
    _user = Depends(verify_clerk_token),
):
    """
    Main pipeline endpoint. Accepts resumes (PDFs) plus EITHER:
    - jd_text: raw job description string (paste mode)
    - jd_pdf:  JD uploaded as a PDF file (pdf mode)
    Returns the full pipeline result as JSON.
    """
    # ── Resolve JD text ─────────────────────────────────────────────────────
    resolved_jd = ""

    if jd_pdf and jd_pdf.filename:
        if not jd_pdf.filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail="jd_pdf must be a PDF file")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await jd_pdf.read())
            jd_tmp_path = tmp.name
        try:
            resolved_jd = extract_text_from_pdf(jd_tmp_path)
        finally:
            try: os.unlink(jd_tmp_path)
            except Exception: pass
    elif jd_text and jd_text.strip():
        resolved_jd = jd_text.strip()

    if not resolved_jd:
        raise HTTPException(
            status_code=400,
            detail="Provide either jd_text (paste) or jd_pdf (upload) — both are empty."
        )

    if not resumes:
        raise HTTPException(status_code=400, detail="At least one resume PDF is required")

    # Extract text from each uploaded PDF
    resume_texts = []
    tmp_paths = []

    try:
        for upload in resumes:
            if not upload.filename.endswith(".pdf"):
                raise HTTPException(
                    status_code=400,
                    detail=f"File '{upload.filename}' is not a PDF"
                )

            # Write to temp file so PyMuPDF can read it
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                content = await upload.read()
                tmp.write(content)
                tmp_paths.append(tmp.name)

            raw_text = extract_text_from_pdf(tmp_paths[-1])
            resume_texts.append({
                "file_name": upload.filename,
                "raw_text":  raw_text,
            })

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF processing error: {str(e)}")
    finally:
        # Clean up temp files
        for path in tmp_paths:
            try:
                os.unlink(path)
            except Exception:
                pass

    # Run pipeline
    try:
        result = run_pipeline(
            job_description=resolved_jd,
            resume_texts=resume_texts,
            team_data=team_data or "",
        )
        return result

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


# ---------------------------------------------------------------------------
# Node metadata for SSE event labels
# ---------------------------------------------------------------------------

_NODE_META = {
    "jd_parser_node":          {"label": "JD Parser",          "icon": "🔍"},
    "resume_screener_node":    {"label": "Resume Screener",    "icon": "📄"},
    "bias_checker_node":       {"label": "Bias Checker",       "icon": "⚖️"},
    "team_gap_analyzer_node":  {"label": "Team Gap Analyzer",  "icon": "👥"},
    "ranker_node":             {"label": "Ranker",             "icon": "🏆"},
    "critique_node":           {"label": "Critique",           "icon": "🧠"},
    "outreach_drafter_node":   {"label": "Outreach Drafter",   "icon": "✉️"},
}

# Fields that use operator.add (list-reducer) in HireGraphState
_LIST_REDUCERS = {"candidate_profiles", "errors"}


def _node_summary(node: str, delta: dict, acc: dict) -> str:
    """Return a short human-readable summary string for the completed node."""
    if node == "jd_parser_node":
        jd = delta.get("jd_parsed", {})
        return f"Role: {jd.get('role_title','?')} | Skills: {len(jd.get('required_skills',[]))}"
    if node == "resume_screener_node":
        profiles = acc.get("candidate_profiles", [])
        return f"{len(profiles)} resume(s) screened so far"
    if node == "bias_checker_node":
        risk = delta.get("bias_report", {}).get("overall_risk", "unknown")
        return f"Bias risk: {risk.upper()}"
    if node == "team_gap_analyzer_node":
        tga = delta.get("team_gap_analysis", {})
        gaps = tga.get("gap_skills", [])
        return f"Gaps found: {', '.join(gaps[:3]) or 'none'}"
    if node == "ranker_node":
        ranked = delta.get("ranked_candidates", [])
        top = ranked[0].get("name", "?") if ranked else "?"
        return f"#{1} {top} leads | {len(ranked)} candidates scored"
    if node == "critique_node":
        cr = delta.get("critique_result", {})
        approved = cr.get("approved", True)
        flags = len(cr.get("flags", []))
        return f"{'✅ Approved' if approved else '🔄 Retry requested'} | {flags} flag(s)"
    if node == "outreach_drafter_node":
        emails = delta.get("outreach_emails", [])
        rejs   = delta.get("rejection_emails", [])
        return f"{len(emails)} invite(s), {len(rejs)} rejection(s) drafted"
    return ""


@app.post("/run/stream", tags=["Pipeline"])
async def run_stream(
    resumes:   List[UploadFile]  = File(...),
    jd_text:   Optional[str]     = Form(None),
    jd_pdf:    Optional[UploadFile] = File(None),
    team_data: Optional[str]     = Form(None),
    _user = Depends(verify_clerk_token),
):
    """
    Streaming pipeline — same inputs as /run/text.
    Returns Server-Sent Events: one 'agent_update' per completed node,
    then a final 'pipeline_complete' event carrying the full result JSON.
    """
    # ── Resolve JD ──────────────────────────────────────────────────────────
    resolved_jd = ""
    if jd_pdf and jd_pdf.filename:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await jd_pdf.read())
            jd_tmp = tmp.name
        try:
            resolved_jd = extract_text_from_pdf(jd_tmp)
        finally:
            try: os.unlink(jd_tmp)
            except Exception: pass
    elif jd_text and jd_text.strip():
        resolved_jd = jd_text.strip()

    if not resolved_jd:
        raise HTTPException(status_code=400, detail="Provide jd_text or jd_pdf.")

    # ── Extract resume texts ─────────────────────────────────────────────────
    resume_texts = []
    tmp_paths: List[str] = []
    try:
        for upload in resumes:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(await upload.read())
                tmp_paths.append(tmp.name)
            resume_texts.append({
                "file_name": upload.filename,
                "raw_text":  extract_text_from_pdf(tmp_paths[-1]),
            })
    finally:
        for p in tmp_paths:
            try: os.unlink(p)
            except Exception: pass

    # ── Build initial state ──────────────────────────────────────────────────
    initial_state = {
        "job_description":     resolved_jd,
        "resume_texts":        resume_texts,
        "team_data":           team_data or "",
        "jd_parsed":           {},
        "candidate_profiles":  [],
        "ranked_candidates":   [],
        "team_gap_analysis":   {},
        "bias_report":         {},
        "outreach_emails":     [],
        "rejection_emails":    [],
        "critique_result":     {},
        "critique_feedback":   "",
        "critique_retry_count": 0,
        "errors":              [],
        "current_step":        "start",
    }

    async def generate():
        from graph.pipeline import build_pipeline
        pipeline_inst = build_pipeline()

        loop  = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        acc: dict = {}   # accumulated result (handles list reducers manually)

        def _put(item):
            asyncio.run_coroutine_threadsafe(queue.put(item), loop)

        def pipeline_thread():
            try:
                for chunk in pipeline_inst.stream(initial_state):
                    _put(("chunk", chunk))
                _put(("done", None))
            except Exception as exc:
                _put(("error", str(exc)))

        threading.Thread(target=pipeline_thread, daemon=True).start()

        while True:
            try:
                kind, data = await asyncio.wait_for(queue.get(), timeout=360.0)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"   # SSE comment — prevents proxy timeout
                continue

            if kind == "error":
                payload = json.dumps({"message": data})
                yield f"event: error\ndata: {payload}\n\n"
                break

            if kind == "done":
                payload = json.dumps(acc)
                yield f"event: pipeline_complete\ndata: {payload}\n\n"
                break

            # ── chunk: one completed node ────────────────────────────────────
            node_name  = list(data.keys())[0]
            state_delta = data[node_name]

            # Accumulate result (respect list-reducer fields)
            if isinstance(state_delta, dict):
                for k, v in state_delta.items():
                    if k in _LIST_REDUCERS and isinstance(v, list):
                        acc.setdefault(k, []).extend(v)
                    else:
                        acc[k] = v

            meta    = _NODE_META.get(node_name, {"label": node_name, "icon": "⚙️"})
            summary = _node_summary(node_name, state_delta, acc)

            payload = json.dumps({
                "node":    node_name,
                "label":   meta["label"],
                "icon":    meta["icon"],
                "summary": summary,
            })
            yield f"event: agent_update\ndata: {payload}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )


@app.post("/parse-jd", tags=["Utilities"])
async def parse_jd_pdf(
    jd_pdf: UploadFile = File(..., description="JD as a PDF"),
    _user = Depends(verify_clerk_token),
):
    """
    Extract raw text from a JD PDF without running the full pipeline.
    Use this to preview the extracted JD text before submitting.
    """
    if not jd_pdf.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await jd_pdf.read())
        tmp_path = tmp.name

    try:
        text = extract_text_from_pdf(tmp_path)
        if text.startswith("ERROR") or not text.strip():
            return {
                "file_name":      jd_pdf.filename,
                "extracted_text": "",
                "char_count":     0,
                "warning":        "Could not extract text from this PDF — it may be scanned or image-based. Please paste the JD text manually.",
            }
        return {"file_name": jd_pdf.filename, "extracted_text": text, "char_count": len(text)}
    finally:
        try: os.unlink(tmp_path)
        except Exception: pass


@app.post("/run/json", tags=["Pipeline"])
def run_from_json(payload: RunJsonRequest):
    """
    Testing endpoint — accepts pre-extracted resume text as JSON.
    Useful for testing without PDFs.
    """
    if not payload.job_description.strip():
        raise HTTPException(status_code=400, detail="job_description cannot be empty")

    if not payload.resumes:
        raise HTTPException(status_code=400, detail="At least one resume is required")

    try:
        result = run_pipeline(
            job_description=payload.job_description,
            resume_texts=payload.resumes,
        )
        return result

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


@app.post("/run/summary", tags=["Pipeline"])
async def run_summary(
    jd_text: str = Form(...),
    resumes: List[UploadFile] = File(...),
):
    """
    Same as /run/text but returns only the compact summary (faster response).
    """
    # Reuse the full endpoint logic
    full_result = await run_from_uploads(jd_text=jd_text, resumes=resumes)
    return summarise_pipeline_result(full_result)
