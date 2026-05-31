"""
agents/outreach_drafter.py — Outreach Drafter Agent  (uses Groq llama-3.3-70b-versatile)

Two outputs from one agent:
  1. outreach_emails  — personalized invite emails for the top-N ranked candidates
  2. rejection_emails — kind, specific rejection letters for bottom candidates
     Each rejection names the exact missing skills and suggests concrete next steps.
     No generic "we'll keep your resume on file."

Runs SEQUENTIALLY after the Ranker (needs ranked_candidates).

Reads:  state["ranked_candidates"]  — sorted list
        state["jd_parsed"]          — for role/company context
Writes: state["outreach_emails"]    — [{candidate_name, file_name, subject, body}]
        state["rejection_emails"]   — [{candidate_name, file_name, subject, body, missing_skills, score}]
"""

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
import json
import os
from dotenv import load_dotenv
from utils.rate_limiter import safe_invoke

load_dotenv()

TOP_N = 3   # Draft invite emails for top N; everyone else gets a rejection letter


def get_llm():
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0.4,
    )


# ---------------------------------------------------------------------------
# Invite email prompt (unchanged from original)
# ---------------------------------------------------------------------------
INVITE_PROMPT = """You are a senior technical recruiter writing personalized outreach emails.

Write a short, warm, professional email to invite a candidate for an initial conversation.

Guidelines:
- Subject line: compelling, specific, under 10 words
- Opening: address them by first name, reference 1-2 of THEIR specific skills
- Body: briefly explain the role and why THEY specifically are a strong fit
- CTA: invite for a 30-minute call, no pressure
- Tone: human, enthusiastic but not salesy, respectful of their time
- Length: 120-180 words total (body only, not subject)
- Do NOT use generic phrases like "We came across your profile" or "We'd love to connect"
- Do NOT invent company name — use "[Company]" as placeholder

Respond with ONLY valid JSON — no markdown, no backticks, no explanation:
{
  "candidate_name": "full name",
  "file_name": "filename.pdf",
  "subject": "Subject line here",
  "body": "Full email body here (use \\n for line breaks)"
}
"""


# ---------------------------------------------------------------------------
# Rejection letter prompt — kind, specific, actionable
# ---------------------------------------------------------------------------
REJECTION_PROMPT = """You are a senior technical recruiter writing a thoughtful rejection letter.

The candidate applied for a role but is not moving forward. Write a rejection email that:
- Is warm, respectful, and genuinely encouraging
- Names their ACTUAL strengths (reference their real skills and projects)
- Is honest about the specific gap (missing skills or experience) — but NOT harsh
- Suggests 1-2 CONCRETE resources or steps to close the gap (courses, projects, docs)
- Leaves the door open for future roles
- Does NOT say "we'll keep your resume on file" — that's a lie and candidates hate it
- Does NOT use generic phrases like "after careful consideration"
- Length: 130-180 words (body only, not subject)
- Use "[Company]" as placeholder — do NOT invent a company name

Respond with ONLY valid JSON — no markdown, no backticks, no explanation:
{
  "candidate_name": "full name",
  "file_name": "filename.pdf",
  "subject": "Subject line here",
  "body": "Full email body here (use \\n for line breaks)"
}
"""


def _strip_fences(raw: str) -> str:
    """Remove markdown code fences if the model adds them."""
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _draft_invite(llm, candidate: dict, role_title: str, responsibilities: list) -> dict:
    """Draft a personalized invite email for a top-N candidate."""
    name = candidate.get("name", "Candidate")
    first_name = name.split()[0] if name not in ("Unknown", "") else "there"

    prompt = f"""Write a personalized outreach email for this candidate.

ROLE: {role_title}
ROLE RESPONSIBILITIES (context): {json.dumps(responsibilities)}

CANDIDATE:
- Name: {name}
- Score: {candidate.get('score', 0)}/100
- Their strongest matched skills: {json.dumps(candidate.get('matched_skills', [])[:3])}
- Why they ranked well: {candidate.get('reasoning', '')}

Address them as "{first_name}". Reference their skills naturally in the email."""

    messages = [SystemMessage(content=INVITE_PROMPT), HumanMessage(content=prompt)]
    response = safe_invoke(llm, messages)
    result = json.loads(_strip_fences(response.content.strip()))
    result["file_name"] = candidate.get("file_name", "")
    result["candidate_name"] = name
    return result


def _draft_rejection(llm, candidate: dict, role_title: str, jd_required_skills: list) -> dict:
    """Draft a kind, specific rejection letter for a bottom candidate."""
    name = candidate.get("name", "Candidate")
    first_name = name.split()[0] if name not in ("Unknown", "") else "there"
    missing = candidate.get("missing_skills", [])
    matched = candidate.get("matched_skills", [])

    prompt = f"""Write a kind rejection email for this candidate who is not moving forward.

ROLE: {role_title}

CANDIDATE:
- Name: {name}
- Score: {candidate.get('score', 0)}/100
- Their genuine strengths (skills they do have): {json.dumps(matched[:4])}
- What they're missing for this specific role: {json.dumps(missing)}
- Dealbreaker flags (if any): {json.dumps(candidate.get('dealbreaker_flags', []))}
- Ranker reasoning: {candidate.get('reasoning', '')}

Address them as "{first_name}".
Be specific: name the missing skills by name.
Suggest 1-2 concrete resources (courses, docs, project ideas) to close the gap.
Do NOT be generic. This email should feel personal and useful, not boilerplate."""

    messages = [SystemMessage(content=REJECTION_PROMPT), HumanMessage(content=prompt)]
    response = safe_invoke(llm, messages)
    result = json.loads(_strip_fences(response.content.strip()))
    result["file_name"] = candidate.get("file_name", "")
    result["candidate_name"] = name
    result["missing_skills"] = missing
    result["score"] = candidate.get("score", 0)
    return result


def outreach_drafter_agent(state: dict) -> dict:
    """
    Reads:  state["ranked_candidates"], state["jd_parsed"]
    Writes: state["outreach_emails"], state["rejection_emails"]
    """
    print("✉️  [Outreach Drafter] Starting...")

    ranked    = state.get("ranked_candidates", [])
    jd_parsed = state.get("jd_parsed", {})

    if not ranked:
        print("⚠️  [Outreach Drafter] No ranked candidates.")
        return {
            "outreach_emails":  [],
            "rejection_emails": [],
            "errors": state.get("errors", []) + ["Outreach Drafter: No ranked candidates found"],
            "current_step": "outreach_drafter_failed",
        }

    llm              = get_llm()
    role_title       = jd_parsed.get("role_title", "the open role")
    responsibilities = jd_parsed.get("responsibilities", [])[:3]
    required_skills  = jd_parsed.get("required_skills", [])

    top_candidates    = ranked[:TOP_N]
    bottom_candidates = ranked[TOP_N:]   # everyone who didn't make the invite cut

    outreach_emails  = []
    rejection_emails = []
    errors           = []

    # ── Invite emails (top N) ─────────────────────────────────────────────────
    for candidate in top_candidates:
        name = candidate.get("name", "Candidate")
        print(f"   ✍️  Invite email → #{candidate.get('rank', '?')} {name}")
        try:
            email = _draft_invite(llm, candidate, role_title, responsibilities)
            outreach_emails.append(email)
            print(f"   ✅ Invite drafted for {name}")
        except (json.JSONDecodeError, Exception) as e:
            print(f"   ❌ Invite error for {name}: {e}")
            errors.append(f"Outreach Drafter invite error ({name}): {str(e)}")

    # ── Rejection letters (everyone else) ────────────────────────────────────
    for candidate in bottom_candidates:
        name = candidate.get("name", "Candidate")
        print(f"   ✍️  Rejection letter → #{candidate.get('rank', '?')} {name}")
        try:
            letter = _draft_rejection(llm, candidate, role_title, required_skills)
            rejection_emails.append(letter)
            print(f"   ✅ Rejection drafted for {name}")
        except (json.JSONDecodeError, Exception) as e:
            print(f"   ❌ Rejection error for {name}: {e}")
            errors.append(f"Outreach Drafter rejection error ({name}): {str(e)}")

    print(
        f"✅ [Outreach Drafter] "
        f"{len(outreach_emails)} invite(s) | {len(rejection_emails)} rejection(s)"
    )

    return {
        "outreach_emails":  outreach_emails,
        "rejection_emails": rejection_emails,
        "errors": state.get("errors", []) + errors,
        "current_step": "outreach_drafter_done",
    }
