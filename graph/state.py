"""
graph/state.py — HireGraph shared pipeline state

All agent nodes read from and write to this TypedDict.

Key LangGraph compatibility rules applied here:
  1. No @dataclass objects in state — LangGraph serializes state as JSON,
     so all values must be plain Python primitives / dicts / lists.
  2. List fields that are written by PARALLEL nodes (candidate_profiles)
     use Annotated + operator.add so LangGraph merges partial results
     from each Send() branch instead of overwriting.
"""

import operator
from typing import TypedDict, List, Optional, Annotated


# ── Candidate profile schema (plain dict shape documented here) ──────────────
# {
#   "name": str,
#   "email": str,
#   "phone": str,
#   "skills": List[str],
#   "experience_years": float,
#   "education": str,
#   "previous_roles": List[str],
#   "raw_text": str,
#   "file_name": str,
# }

# ── Ranked candidate schema (plain dict shape documented here) ───────────────
# {
#   "rank": int,
#   "name": str,
#   "score": float,               # 0.0 – 100.0
#   "skills_match": str,          # "high" | "medium" | "low"
#   "experience_match": str,      # "above" | "meets" | "below"
#   "reasoning": str,
#   "file_name": str,
# }

# ── Bias signal schema (plain dict shape documented here) ────────────────────
# {
#   "field": str,          # e.g. "education_requirement"
#   "text": str,           # the offending text
#   "bias_type": str,      # e.g. "degree_elitism", "age_proxy", "gender_coded"
#   "suggestion": str,     # recommended rewording
# }

# ── Outreach email schema (plain dict shape documented here) ─────────────────
# {
#   "candidate_name": str,
#   "file_name": str,
#   "subject": str,
#   "body": str,
# }

# ── Rejection letter schema (plain dict shape documented here) ────────────────
# {
#   "candidate_name": str,
#   "file_name": str,
#   "subject": str,
#   "body": str,
#   "missing_skills": List[str],
#   "score": float,
# }


class HireGraphState(TypedDict):
    # ── Inputs ────────────────────────────────────────────────────────────────
    job_description: str
    resume_texts:    List[dict]          # [{"file_name": str, "raw_text": str}]
    team_data:       str                 # optional CSV/JSON of existing team (empty = no team context)

    # ── JD Parser output ──────────────────────────────────────────────────────
    jd_parsed: dict                   # {role_title, required_skills, ...}

    # ── Resume Screener output (parallel fan-in — uses reducer) ───────────────
    # Annotated + operator.add means each parallel Send() branch appends
    # its single profile dict to this list rather than overwriting it.
    candidate_profiles: Annotated[List[dict], operator.add]

    # ── Ranker output ─────────────────────────────────────────────────────────
    ranked_candidates: List[dict]     # sorted list of ranked candidate dicts

    # ── Critique Agent output (Gemini) ────────────────────────────────────────
    # critique_result:      Gemini's review of the ranking
    # critique_feedback:    natural-language feedback passed back to Ranker on retry
    # critique_retry_count: circuit breaker — max 2 re-rank loops
    critique_result: dict
    critique_feedback: str
    critique_retry_count: int

    # ── Team Gap Analyzer output ──────────────────────────────────────────────
    team_gap_analysis: dict           # {team_size, skill_coverage, saturated_skills, gap_skills, analysis_summary}

    # ── Bias Checker output ───────────────────────────────────────────────────
    bias_report: dict                 # {overall_risk, signals, recommendations}

    # ── Outreach Drafter output ───────────────────────────────────────────────
    outreach_emails:  List[dict]       # personalized invite emails (top N)
    rejection_emails: List[dict]       # kind rejection letters (bottom candidates)

    # ── Pipeline metadata ────────────────────────────────────────────────────
    errors: Annotated[List[str], operator.add]   # also merged across parallel branches
    current_step: str