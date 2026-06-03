
"""
agents/jd_parser.py — JD Parser Agent

Parses a raw job description into structured data that downstream agents
(Resume Screener, Ranker, Bias Checker) consume.

Reads:  state["job_description"]
Writes: state["jd_parsed"]
"""

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from graph.state import HireGraphState
import json
import os
from dotenv import load_dotenv
from utils.rate_limiter import safe_invoke

load_dotenv()


def get_llm():
    return ChatGroq(
        model="llama-3.1-8b-instant",   # extraction task — 8B is sufficient and faster
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0.1,
        model_kwargs={"response_format": {"type": "json_object"}}
    )


SYSTEM_PROMPT = """You are an expert HR analyst. Parse a job description into structured data.

Always respond with ONLY valid JSON, no explanation, no markdown, no backticks.

{
  "role_title": "exact job title",
  "required_skills": ["skill1", "skill2"],
  "nice_to_have_skills": ["skill1", "skill2"],
  "dealbreaker_skills": ["skill that is non-negotiable for this role"],
  "min_experience_years": 0,
  "max_experience_years": null,
  "responsibilities": ["responsibility1"],
  "education_requirement": "e.g. Bachelor's in CS or equivalent",
  "education_is_strict": false,
  "industry": "e.g. Fintech, Healthcare, SaaS",
  "seniority_level": "intern | junior | mid | senior | lead",
  "skill_categories": {
    "languages": ["Python", "Java"],
    "frameworks": ["FastAPI", "LangChain"],
    "concepts": ["RAG", "LLMs", "OOP"],
    "tools": ["Docker", "Git"]
  }
}

Rules:
- dealbreaker_skills: be SELECTIVE — only the 1-2 skills that are the absolute core of the role.
    A dealbreaker cap eliminates candidates entirely. Use this sparingly.

    Populate ONLY when ALL of these are true:
    * The skill defines the PRIMARY PURPOSE of the role (not just foundational or nice-to-have)
    * A candidate without this skill literally cannot do the core work of the role
    * The JD signals this skill cannot be learned on the job

    EXPLICIT signal: JD uses "must", "required", "essential", "mandatory"
    IMPLICIT signal: skill appears in BOTH the responsibilities AND foundational skills sections
                     AND the JD implies this is not a learning opportunity
    IMPLICIT signal: skill is in the role title itself

    DO NOT add a skill as a dealbreaker just because it appears in a required skills list.
    Required != dealbreaker. Most roles have 0-2 dealbreakers, rarely more than 3.
    Python is almost NEVER a dealbreaker — virtually every candidate applying for a Python
    AI role has Python. Save dealbreakers for the specific stack that defines the role.

    Group related skills into ONE dealbreaker concept rather than listing each separately.
    Example: instead of ["LangChain", "LangGraph", "RAG", "Python"] use
    ["LangChain/LangGraph or equivalent agentic framework experience"]

- skill_categories: re-categorize required_skills into subcategories for precision
  matching against resume skill_categories
- education_is_strict: true ONLY if JD explicitly says "degree required" with no
  "or equivalent" clause
- seniority_level: infer from title, experience requirement, and responsibility language
- max_experience_years: null unless JD explicitly states an upper limit
- Be precise. Only include what is explicitly stated or strongly implied.
"""


def jd_parser_agent(state: HireGraphState) -> dict:
    """
    Reads: state["job_description"]
    Writes: state["jd_parsed"]
    """
    print("🔍 [JD Parser] Starting...")

    jd_text = state.get("job_description", "")

    if not jd_text:
        return {
            "jd_parsed": {},
            "errors": state.get("errors", []) + ["JD Parser: No job description provided"],
            "current_step": "jd_parser_failed"
        }

    llm = get_llm()

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Parse this job description:\n\n{jd_text}")
    ]

    try:
        response = safe_invoke(llm, messages)
        raw = response.content.strip()

        # clean up if model wraps in backticks despite instructions
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        parsed = json.loads(raw)

        print(f"✅ [JD Parser] Role: {parsed.get('role_title')} | "
              f"Skills: {len(parsed.get('required_skills', []))} | "
              f"Seniority: {parsed.get('seniority_level', 'unknown')} | "
              f"Dealbreakers: {len(parsed.get('dealbreaker_skills', []))}")

        return {
            "jd_parsed": parsed,
            "current_step": "jd_parser_done"
        }

    except json.JSONDecodeError as e:
        print(f"❌ [JD Parser] JSON parse error: {e}")
        return {
            "jd_parsed": {},
            "errors": state.get("errors", []) + [f"JD Parser JSON error: {str(e)}"],
            "current_step": "jd_parser_failed"
        }
    except Exception as e:
        print(f"❌ [JD Parser] Error: {e}")
        return {
            "jd_parsed": {},
            "errors": state.get("errors", []) + [f"JD Parser error: {str(e)}"],
            "current_step": "jd_parser_failed"
        }