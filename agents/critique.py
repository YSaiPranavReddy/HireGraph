"""
agents/critique.py — Critique Agent  (uses Google Gemini 2.5 Flash)

Acts as an independent judge reviewing the Ranker's output.
Uses a DIFFERENT model family (Gemini) than the Ranker (Groq/Llama) to
eliminate self-confirmation bias — the same model tends to approve its own work.

Role in the pipeline loop:
    Ranker (Groq 70B) → Critique (Gemini 2.5 Flash)
                               │
               approved OR retries >= 2 → Outreach
               not approved AND retries < 2 → Ranker (with feedback)

Key design decisions:
  1. Per-candidate feedback structure — critique returns individual verdicts
     (justified / too_high / too_low) per candidate, not one feedback blob.
     Ranker retry re-scores only candidates with non-justified verdicts.
     Candidates marked "justified" keep their existing score — untouched.

  2. No score caps — dealbreaker flags reduce role_relevance and zero out
     the missing skill in skills_match. The total score drops naturally
     based on the candidate's overall profile. Two candidates with the
     same dealbreaker flag can score very differently — this is correct.

  3. Semantic reasoning — equivalent project evidence satisfies dealbreakers.
     Missing framework name ≠ missing skill if the concept is demonstrated.

Reads:  state["ranked_candidates"], state["candidate_profiles"], state["jd_parsed"]
        state["critique_retry_count"]

Writes: state["critique_result"]      — {approved, flags, per_candidate_feedback, attempt}
        state["critique_feedback"]    — summary string for pipeline compatibility
        state["critique_retry_count"] — incremented by 1
"""

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from utils.rate_limiter import safe_invoke, is_rate_limit_error
import json
import os
from dotenv import load_dotenv

load_dotenv()

MAX_RETRIES = 2


CRITIQUE_MODEL_CHAIN = [
    (
        "gemini-2.5-flash",
        lambda: ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0.1,
        ),
    ),
    (
        "gemini-2.0-flash",
        lambda: ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0.1,
        ),
    ),
    (
        "gemini-1.5-flash",
        lambda: ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0.1,
        ),
    ),
    (
        "gemini-1.5-flash-8b",
        lambda: ChatGoogleGenerativeAI(
            model="gemini-1.5-flash-8b",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0.1,
        ),
    ),
]


def invoke_with_fallback(messages: list) -> tuple:
    """
    Try each Gemini model in order. Returns (response, model_name_used).
    No Groq fallback — same model as ranker judging its own output defeats
    the purpose of cross-model critique.
    """
    last_exc = None
    for model_name, get_model in CRITIQUE_MODEL_CHAIN:
        try:
            llm = get_model()
            response = safe_invoke(llm, messages)
            return response, model_name
        except Exception as exc:
            if is_rate_limit_error(exc):
                print(f"  [Critique Fallback] {model_name} quota exhausted -> trying next...")
                last_exc = exc
                continue
            raise
    raise last_exc


SYSTEM_PROMPT = """You are an independent hiring expert auditing AI-generated candidate scores.
You receive candidate profiles WITH project evidence and the scores the Ranker assigned.

Your job: for EACH candidate INDEPENDENTLY, decide if their score is:
  "justified"  — score matches the evidence, no change needed
  "too_high"   — score is inflated relative to the evidence
  "too_low"    — score is deflated, evidence was missed or under-weighted

You will receive:
1. Parsed JD — required_skills, dealbreaker_skills, seniority_level, skill_categories
2. Candidate profiles — skills, demonstrated_skills.evidence, projects (with descriptions)
3. Current ranking — scores, matched_skills, missing_skills, dealbreaker_flags, reasoning

============================================================
HOW TO AUDIT EACH CANDIDATE
============================================================

For EACH candidate, work through these checks independently:

CHECK 1 — Dealbreaker skills:
  For each skill in dealbreaker_skills:
  a) Check demonstrated_skills.evidence — any entry for this CONCEPT
  b) Check projects[].description — does any description imply this concept?
  c) Check skills[] — is it listed?

  SEMANTIC — reason about concepts, not framework names:
  - Project implementing the CONCEPT = satisfied (even without exact framework name)
  - Different tool solving the same problem = satisfied
  - Listed in skills but zero project evidence = NOT satisfied

  If candidate has NO project evidence of the concept anywhere:
    → The ranker should have added it to dealbreaker_flags
    → role_relevance should be 8-10 pts lower than a candidate without this gap
    → skills_match should be zero for that skill
    → If score looks too high given this gap → verdict "too_high"

  If candidate HAS project evidence (even without exact framework name):
    → Dealbreaker IS satisfied. Do NOT flag it.
    → Do not penalize for missing exact framework name.

CHECK 2 — Score vs evidence quality:
  Count proven skills (in demonstrated_skills.evidence) vs listed-only vs absent.

  Most required skills proven in projects → expect 75-95
  Mix of proven + listed-only → expect 55-75
  Mostly listed-only or absent → expect 30-55
  Missing dealbreaker concept entirely → expect lower end based on overall profile

  If score is significantly above or below what evidence supports:
    → verdict "too_high" or "too_low" with specific evidence cited

CHECK 3 — Under-scoring (equally important as over-scoring):
  If candidate has strong project evidence for most required skills but
  scored below 70 — they may be under-scored.
  Check demonstrated_skills.evidence carefully before accepting a low score.
  → verdict "too_low" with the specific evidence that was missed

============================================================
CRITICAL RULES
============================================================
1. NEVER batch candidates. One verdict per candidate, independently.
   Never write "all candidates" or "X, Y, Z all have the same issue."

2. "justified" = correct score, no change suggested.

3. Only flag issues backed by specific evidence.
   Name the project. Name the skill. Be precise.

4. Research + engineering = stronger candidate, not weaker.
   Never penalize research depth when engineering evidence also exists.
   Only flag if candidate has EXCLUSIVELY non-relevant skills with zero
   engineering evidence for what the JD requires.

5. No score caps exist in this system. Do NOT suggest hard caps like
   "must be ≤ 45". Instead describe what dimensions should reflect:
   "role_relevance should be 8-10 pts lower" or
   "skills_match should be zero for LangGraph since no project evidence exists."

6. On attempt 2+: only flag HIGH severity. Approve minor issues.

============================================================
RESPONSE FORMAT — one entry per candidate, no exceptions
============================================================
Respond with ONLY valid JSON, no markdown, no backticks.
per_candidate_feedback MUST contain one entry for EVERY candidate.
Candidate names must match EXACTLY as they appear in the ranking.

{
  "approved": true or false,
  "attempt": 1,
  "per_candidate_feedback": {
    "Exact Candidate Name": {
      "verdict": "justified",
      "current_score": 87.5,
      "suggested_score": 87.5,
      "feedback": null
    },
    "Another Candidate Name": {
      "verdict": "too_high",
      "current_score": 78.5,
      "suggested_score": 62.0,
      "feedback": "demonstrated_skills.evidence has zero entries for LangGraph or agentic concept. dealbreaker_flags should include this. role_relevance should be reduced 8-10 pts for the missing core skill. skills_match should be zero for that skill."
    },
    "Under-scored Candidate": {
      "verdict": "too_low",
      "current_score": 60.0,
      "suggested_score": 78.0,
      "feedback": "CodeRAG project description says 'Built a Retrieval-Augmented Generation (RAG) code assistant' — this satisfies the RAG dealbreaker. Score should reflect this evidence. Increase skills_match and role_relevance accordingly."
    }
  },
  "flags": [
    {
      "candidate": "exact name",
      "issue": "specific issue with project evidence cited",
      "severity": "low | medium | high",
      "expected_score_range": "approximate range e.g. 55-65"
    }
  ]
}

Rules:
- approved: true ONLY if ALL candidates have verdict "justified"
- approved: false if ANY candidate has "too_high" or "too_low"
- feedback: null when verdict is "justified"
- suggested_score equals current_score when verdict is "justified"
- Do NOT use fixed caps in feedback — describe dimension adjustments instead
"""


def critique_agent(state: dict) -> dict:
    """
    Reviews ranked_candidates against candidate_profiles and jd_parsed.
    Returns per-candidate verdicts so ranker retry is surgical.
    """
    ranked      = state.get("ranked_candidates", [])
    profiles    = state.get("candidate_profiles", [])
    jd_parsed   = state.get("jd_parsed", {})
    retry_count = state.get("critique_retry_count", 0)

    attempt = retry_count + 1
    print(f"[Critique] Starting review (attempt {attempt}/{MAX_RETRIES})...")

    if not ranked:
        print("[Critique] No ranked candidates to review — skipping.")
        return {
            "critique_result": {
                "approved": True,
                "attempt": attempt,
                "flags": [],
                "per_candidate_feedback": {},
                "feedback": "No candidates to review."
            },
            "critique_feedback":    "",
            "critique_retry_count": attempt,
            "current_step":         "critique_skipped"
        }

    # ── Build slim profiles ──────────────────────────────────────────────────
    # Include demonstrated_skills + projects WITH descriptions so Gemini
    # can reason about concepts from project text, not just tech_stack keywords.
    slim_profiles = []
    for p in profiles:
        slim_profiles.append({
            "name":                p.get("name"),
            "skills":              p.get("skills", []),
            "demonstrated_skills": p.get("demonstrated_skills", {"evidence": []}),
            "skill_depth":         p.get("skill_depth", {}),
            "experience_years":    p.get("experience_years"),
            "education":           p.get("education"),
            "previous_roles":      p.get("previous_roles", []),
            "projects": [
                {
                    "name":          proj.get("name"),
                    "tech_stack":    proj.get("tech_stack", []),
                    "description":   proj.get("description", "")[:150],  # concept evidence
                    "is_production": proj.get("is_production", False),
                }
                for proj in p.get("projects", [])
            ],
            "file_name": p.get("file_name"),
        })

    # ── Build slim ranking ───────────────────────────────────────────────────
    slim_ranking = [
        {
            "rank":              c.get("rank"),
            "name":              c.get("name"),
            "score":             c.get("score"),
            "skills_match":      c.get("skills_match"),
            "experience_fit":    c.get("experience_fit"),
            "role_relevance":    c.get("role_relevance"),
            "matched_skills":    c.get("matched_skills", []),
            "missing_skills":    c.get("missing_skills", []),
            "dealbreaker_flags": c.get("dealbreaker_flags", []),
            "reasoning":         c.get("reasoning", ""),
        }
        for c in ranked
    ]

    candidate_names = [c.get("name") for c in ranked]

    prompt = f"""Attempt {attempt} of {MAX_RETRIES}.

JOB DESCRIPTION (parsed):
{json.dumps(jd_parsed, indent=2)}

CANDIDATE PROFILES (with project evidence and descriptions):
{json.dumps(slim_profiles, indent=2)}

CURRENT RANKING:
{json.dumps(slim_ranking, indent=2)}

Audit each candidate INDEPENDENTLY.
You MUST return a verdict for ALL {len(ranked)} candidates: {json.dumps(candidate_names)}

For each candidate: cross-check their demonstrated_skills.evidence AND
project descriptions against their score. Is it justified, too high, or too low?"""

    if retry_count >= 1:
        prompt += f"""

Attempt {attempt}: Ranker has already incorporated previous feedback.
Only flag HIGH severity issues — major score contradictions or clear
evidence mismatches. Approve minor issues."""

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt)
    ]

    try:
        response, model_used = invoke_with_fallback(messages)
        print(f"  [Critique] Model: {model_used}")
        raw = response.content.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        critique = json.loads(raw)
        critique["attempt"] = attempt

        approved      = critique.get("approved", True)
        flags         = critique.get("flags", [])
        per_candidate = critique.get("per_candidate_feedback", {})

        # Build summary feedback string for logging + pipeline compatibility
        feedback_parts = []
        for name, vdata in per_candidate.items():
            verdict = vdata.get("verdict", "justified")
            if verdict in ("too_high", "too_low"):
                fb = vdata.get("feedback")
                if fb and fb != "null":
                    feedback_parts.append(f"{name}: {fb}")

        feedback_summary = " | ".join(feedback_parts) if feedback_parts else "No corrections needed."

        high_flags   = [f for f in flags if f.get("severity") == "high"]
        medium_flags = [f for f in flags if f.get("severity") == "medium"]

        status = "APPROVED" if approved else "NEEDS REVISION"
        print(f"[Critique] {status} | Model: {model_used} | "
              f"Flags: {len(high_flags)} high, {len(medium_flags)} medium, "
              f"{len(flags) - len(high_flags) - len(medium_flags)} low")

        # Log per-candidate verdicts
        for name, vdata in per_candidate.items():
            verdict = vdata.get("verdict", "justified")
            curr    = vdata.get("current_score", "?")
            sugg    = vdata.get("suggested_score", curr)
            icon    = "✅" if verdict == "justified" else ("⬇️ " if verdict == "too_high" else "⬆️ ")
            change  = f"({curr} → {sugg})" if verdict != "justified" else f"({curr} ✓)"
            print(f"  {icon} {name}: {verdict} {change}")

        if not approved:
            print(f"[Critique] Feedback: {feedback_summary[:150]}...")

        critique["per_candidate_feedback"] = per_candidate
        critique["feedback"] = feedback_summary

        return {
            "critique_result":      critique,
            "critique_feedback":    feedback_summary if not approved else "",
            "critique_retry_count": attempt,
            "current_step":         "critique_approved" if approved else "critique_retry"
        }

    except json.JSONDecodeError as e:
        print(f"[Critique] JSON parse error: {e} — approving to avoid blocking pipeline")
        return {
            "critique_result": {
                "approved": True,
                "attempt":  attempt,
                "flags":    [],
                "per_candidate_feedback": {},
                "feedback": f"Critique parse error — skipped: {str(e)}"
            },
            "critique_feedback":    "",
            "critique_retry_count": attempt,
            "current_step":         "critique_parse_error"
        }

    except Exception as e:
        print(f"[Critique] All models exhausted — failing safe (auto-approve)")
        print(f"  Details: {str(e)[:120]}")
        return {
            "critique_result": {
                "approved": True,
                "attempt":  attempt,
                "flags":    [],
                "per_candidate_feedback": {},
                "feedback": f"Critique error — skipped: {str(e)}"
            },
            "critique_feedback":    "",
            "critique_retry_count": attempt,
            "current_step":         "critique_error"
        }