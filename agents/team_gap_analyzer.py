"""
agents/team_gap_analyzer.py — Team Gap Analyzer Agent  (Groq llama-3.3-70b-versatile)

Takes an optional existing team snapshot (CSV or JSON text) and the parsed JD.
Identifies which required skills are already well-covered by the team vs. which
are genuine gaps. Passes this analysis to the Ranker so candidates who fill gaps
score higher on role_relevance than candidates who duplicate existing skills.

If team_data is empty/absent → returns empty analysis immediately (no LLM call).

Runs PARALLEL with bias_checker and resume_screeners in the fan-out stage.

Reads:  state["team_data"]   — raw CSV/JSON string uploaded by recruiter (optional)
        state["jd_parsed"]   — for required_skills context
Writes: state["team_gap_analysis"] — structured gap analysis dict
"""

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
import json
import os
from dotenv import load_dotenv
from utils.rate_limiter import safe_invoke

load_dotenv()


EMPTY_ANALYSIS = {
    "team_size": 0,
    "skill_coverage": {},
    "saturated_skills": [],
    "gap_skills": [],
    "analysis_summary": "",
}


def get_llm():
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0.1,
    )


SYSTEM_PROMPT = """You are a talent strategy analyst. You will receive:
1. An existing engineering team snapshot (CSV or JSON — names, roles, skills)
2. A parsed job description with required_skills

Your job: analyze what skills the team already covers vs. what they're missing.

Always respond with ONLY valid JSON, no markdown, no backticks:
{
  "team_size": 4,
  "skill_coverage": {
    "Python": 4,
    "FastAPI": 2,
    "LangChain": 1,
    "React": 0
  },
  "saturated_skills": ["Python", "SQL"],
  "gap_skills": ["LangGraph", "RAG", "Vector DB"],
  "analysis_summary": "2-3 sentences. Name the specific skill gaps and why they matter for this hire."
}

Rules:
- saturated_skills: skills where 50%+ of the team already has coverage (low marginal value for new hire)
- gap_skills: required_skills from the JD that 0-1 team members have (high marginal value for new hire)
- skill_coverage: count of team members with each required skill (only include JD required_skills)
- analysis_summary: be specific — name the gaps, don't be generic
"""


def team_gap_analyzer_agent(state: dict) -> dict:
    """
    Reads:  state["team_data"], state["jd_parsed"]
    Writes: state["team_gap_analysis"]
    """
    team_data = state.get("team_data", "").strip()
    jd_parsed = state.get("jd_parsed", {})

    # Fast path — no team data provided, skip LLM entirely
    if not team_data:
        print("ℹ️  [Team Gap Analyzer] No team data provided — skipping.")
        return {"team_gap_analysis": EMPTY_ANALYSIS}

    print("🔍 [Team Gap Analyzer] Analyzing team skill coverage...")

    required_skills = jd_parsed.get("required_skills", [])
    role_title      = jd_parsed.get("role_title", "the role")

    prompt = f"""EXISTING TEAM DATA:
{team_data}

JOB DESCRIPTION (parsed):
- Role: {role_title}
- Required skills: {json.dumps(required_skills)}

Analyze the team's current skill coverage vs. what this new hire needs to bring."""

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]

    try:
        llm = get_llm()
        response = safe_invoke(llm, messages)
        raw = response.content.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        analysis = json.loads(raw)

        team_size       = analysis.get("team_size", 0)
        gap_count       = len(analysis.get("gap_skills", []))
        saturated_count = len(analysis.get("saturated_skills", []))

        print(
            f"✅ [Team Gap Analyzer] Team: {team_size} members | "
            f"Gaps: {gap_count} skills | Saturated: {saturated_count} skills"
        )
        if analysis.get("gap_skills"):
            print(f"   Key gaps: {', '.join(analysis['gap_skills'][:5])}")

        return {"team_gap_analysis": analysis}

    except (json.JSONDecodeError, Exception) as e:
        print(f"⚠️  [Team Gap Analyzer] Error: {e} — proceeding without team analysis")
        return {"team_gap_analysis": EMPTY_ANALYSIS}
