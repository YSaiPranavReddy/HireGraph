"""
agents/resume_screener.py — Resume Screener Agent

Called once per resume via LangGraph's Send() API (parallel fan-out).
Each invocation receives a single resume dict and returns one CandidateProfile
dict that is merged into state["candidate_profiles"] via the operator.add reducer.

Input (via Send payload):
    {
        "file_name": str,
        "raw_text": str,
        "job_description": str,   # passed through for context
    }

Output (partial state update):
    {
        "candidate_profiles": [<one profile dict>],
        "errors": [],
    }
"""

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from datetime import datetime
import json
import os
import re
from dotenv import load_dotenv
from utils.rate_limiter import safe_invoke

load_dotenv()

# Injected dynamically so ongoing "Present" roles are calculated correctly
TODAY_LABEL = datetime.now().strftime("%B %Y")   # e.g. "May 2026"


def get_llm():
    return ChatGroq(
        model="llama-3.1-8b-instant",   # parallel fan-out — 8B is sufficient and faster
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0.1,
        model_kwargs={"response_format": {"type": "json_object"}}
    )




def _clean_llm_json(raw: str) -> str:
    """
    Sanitise LLM output before passing to json.loads().
    Handles the three most common LLM JSON failures:

    1. Python literals  — None / True / False → null / true / false
    2. Trailing commas  — [x,] or {k:v,} → [x] or {k:v}
    3. Truncated output — JSON cut at token limit: try to recover the
       largest valid prefix by closing any unclosed braces/brackets.
    """
    # 1 — Python literals
    raw = re.sub(r'\bNone\b',  'null',  raw)
    raw = re.sub(r'\bTrue\b',  'true',  raw)
    raw = re.sub(r'\bFalse\b', 'false', raw)

    # 2 — Trailing commas before ] or }
    raw = re.sub(r',\s*([}\]])', r'\1', raw)

    # 3 — Truncated output: try as-is first, then attempt recovery
    try:
        json.loads(raw)   # quick validity check — don't store, just test
        return raw
    except json.JSONDecodeError:
        pass

    # Find the outermost opening brace and try to close the structure
    start = raw.find('{')
    if start == -1:
        return raw   # nothing to recover — let the caller handle the error

    fragment = raw[start:]
    depth_brace  = 0
    depth_bracket = 0
    last_good_pos = start

    for i, ch in enumerate(fragment):
        if ch == '{':
            depth_brace += 1
        elif ch == '}':
            depth_brace -= 1
            if depth_brace == 0 and depth_bracket == 0:
                last_good_pos = start + i + 1
                break
        elif ch == '[':
            depth_bracket += 1
        elif ch == ']':
            depth_bracket -= 1

    # If we found a balanced closing brace use that slice;
    # otherwise close however many levels are still open
    if depth_brace == 0:
        recovered = fragment[:last_good_pos - start]
    else:
        # Strip trailing partial value (up to last comma or colon)
        trimmed = fragment.rstrip()
        trimmed = re.sub(r'[,:\s]+$', '', trimmed)
        trimmed = re.sub(r',\s*([}\]])', r'\1', trimmed)
        recovered = trimmed + (']' * depth_bracket) + ('}' * depth_brace)

    return recovered


SYSTEM_PROMPT = f"""You are an expert resume parser. Extract structured candidate information from the resume text provided.

Always respond with ONLY valid JSON, no explanation, no markdown, no backticks.

{{
  "name": "candidate full name or 'Unknown' if not found",
  "email": "email address or empty string",
  "phone": "phone number or empty string",
  "skills": ["skill1", "skill2", "skill3"],
  "skill_categories": {{
    "languages": [],
    "frameworks": [],
    "concepts": [],
    "tools": []
  }},
  "demonstrated_skills": {{
    "evidence": [
      {{
        "skill": "FAISS",
        "project": "CodeRAG",
        "is_production": false
      }}
    ]
  }},
  "skill_depth": {{
    "frameworks": {{}},
    "concepts": {{}}
  }},
  "experience_years": 0.0,
  "education": "highest degree and field, e.g. B.Tech in Computer Science",
  "education_level": "high_school | associate | bachelor | master | phd | other",
  "previous_roles": ["Job Title at Company (Year-Year)", "..."],
  "projects": [
    {{
      "name": "project name",
      "tech_stack": ["FastAPI", "FAISS", "LangChain"],
      "description": "one sentence on what it does",
      "is_production": false
    }}
  ],
  "summary": "2-3 sentence professional summary inferred from the resume"
}}

Rules:
- skills: extract ALL technical skills, tools, frameworks, and languages mentioned anywhere
- skill_categories: bin each skill from the flat skills list into subcategories
- demonstrated_skills.evidence: for EVERY skill that appears in at least one project's tech_stack,
  add an entry with the skill name, which project it appeared in, and whether that project is production.
  This is PROVEN skill evidence — the candidate didn't just list it, they built something with it.
  If the same skill appears in multiple projects, add one entry per project.
- skill_depth: count how many projects demonstrate each framework and concept.
  Example: {{"frameworks": {{"FastAPI": 2, "LangChain": 1}}, "concepts": {{"RAG": 1, "LLMs": 2}}}}
  Only include skills that appear at least once in a project tech_stack.
- experience_years: total years of ALL hands-on experience as a decimal number, including:
    * Full-time employment
    * Internships (paid or unpaid)
    * Research positions and AI/ML research roles
    * Part-time or contract work
    * Significant freelance projects with clients
  For ongoing roles that say "Present" or "Current", calculate duration up to today: {TODAY_LABEL}.
  If a role spans less than a year, express as a decimal (e.g. 3 months = 0.25, 6 months = 0.5).
  Sum all non-overlapping roles for the total.
- previous_roles: include internships, research roles, and part-time positions — not just full-time jobs
- projects: extract from Projects section; set is_production=true if deployed, live, or in production use
- education_level: map the highest degree to the enum value
- If a field cannot be determined, use an empty string or empty list
- Do NOT invent information not present in the resume
"""


def resume_screener_agent(state: dict) -> dict:
    """
    Processes a single resume. Called via LangGraph Send() with a payload dict.

    The Send() payload is merged into the node's input, so state will contain:
      - file_name: str
      - raw_text: str
      - job_description: str (for context, not used in extraction)
    """
    file_name = state.get("file_name", "unknown.pdf")
    raw_text  = state.get("raw_text", "")

    print(f"[Resume Screener] Processing: {file_name}")

    # Handle empty/error PDFs
    if not raw_text or raw_text.startswith("ERROR"):
        print(f"[Resume Screener] Empty or unreadable PDF: {file_name}")
        return {
            "candidate_profiles": [{
                "name": "Unknown",
                "email": "",
                "phone": "",
                "skills": [],
                "experience_years": 0.0,
                "experience_months": 0,
                "education": "",
                "previous_roles": [],
                "summary": "",
                "raw_text": raw_text,
                "file_name": file_name,
            }],
            "errors": [f"Resume Screener: Could not read {file_name}"]
        }

    llm = get_llm()

    # 10k chars ≈ 2500 tokens — well within 8b-instant's 128k context window.
    # Keeps the experience/projects section intact even for long resumes.
    MAX_CHARS = 10_000
    truncated_text = raw_text[:MAX_CHARS]
    if len(raw_text) > MAX_CHARS:
        truncated_text += "\n[... resume truncated for processing ...]"

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Parse this resume:\n\n{truncated_text}")
    ]

    try:
        response = safe_invoke(llm, messages)
        raw = response.content.strip()

        # Strip markdown code fences if model adds them despite instructions
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        # ── JSON sanitisation ────────────────────────────────────────────────
        # LLMs produce three common invalid-JSON patterns:
        #   1. Python literals:  None / True / False  →  null / true / false
        #   2. Trailing commas:  [...,]  {…,}         →  [...] {}
        #   3. Truncated output: JSON cut at token limit — extract what's valid
        raw = _clean_llm_json(raw)

        parsed = json.loads(raw)

        # Single source of truth: trust experience_years from model, derive months in Python
        exp_years  = float(parsed.get("experience_years", 0.0))
        exp_months = round(exp_years * 12)

        # Sanity warning: model returned 0 exp but roles exist — likely a parsing issue
        if exp_years == 0.0 and parsed.get("previous_roles"):
            print(f"  [WARN] 0 exp returned but roles found: {parsed['previous_roles']}")

        profile = {
            "name":                parsed.get("name", "Unknown"),
            "email":               parsed.get("email", ""),
            "phone":               parsed.get("phone", ""),
            "skills":              parsed.get("skills", []),
            "skill_categories":    parsed.get("skill_categories", {"languages": [], "frameworks": [], "concepts": [], "tools": []}),
            "demonstrated_skills": parsed.get("demonstrated_skills", {"evidence": []}),
            "skill_depth":         parsed.get("skill_depth", {}),
            "experience_years":    exp_years,
            "experience_months":   exp_months,
            "education":           parsed.get("education", ""),
            "education_level":     parsed.get("education_level", "other"),
            "previous_roles":      parsed.get("previous_roles", []),
            "projects":            parsed.get("projects", []),
            "summary":             parsed.get("summary", ""),
            "raw_text":         raw_text,
            "file_name":        file_name,
        }

        # Human-friendly experience label
        if exp_months == 0:
            exp_label = "No listed exp"
        elif exp_months < 12:
            exp_label = f"{exp_months}m exp"
        else:
            exp_label = f"{exp_years:.1f}y exp"

        print(f"[Resume Screener] {profile['name']} | "
              f"{len(profile['skills'])} skills | {exp_label}")

        return {
            "candidate_profiles": [profile],
            "errors": []
        }

    except json.JSONDecodeError as e:
        print(f"[Resume Screener] JSON parse error for {file_name}: {e}")
        return {
            "candidate_profiles": [{
                "name": "Parse Error",
                "email": "", "phone": "",
                "skills": [],
                "experience_years": 0.0, "experience_months": 0,
                "education": "", "previous_roles": [], "summary": "",
                "raw_text": raw_text, "file_name": file_name,
            }],
            "errors": [f"Resume Screener JSON error ({file_name}): {str(e)}"]
        }

    except Exception as e:
        print(f"[Resume Screener] Error for {file_name}: {e}")
        return {
            "candidate_profiles": [{
                "name": "Error",
                "email": "", "phone": "",
                "skills": [],
                "experience_years": 0.0, "experience_months": 0,
                "education": "", "previous_roles": [], "summary": "",
                "raw_text": raw_text, "file_name": file_name,
            }],
            "errors": [f"Resume Screener error ({file_name}): {str(e)}"]
        }
