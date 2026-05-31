"""
agents/bias_checker.py — Bias Checker Agent  (uses Google Gemini 1.5 Flash)

Audits the parsed job description for biased language, exclusionary criteria,
and demographic signals that could unfairly filter candidates.

Runs in Group 1 PARALLEL with resume_screener (only needs jd_parsed).

Reads:  state["jd_parsed"]   — structured JD dict from jd_parser
Writes: state["bias_report"] — {overall_risk, signals, recommendations}
"""

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
import json
import os
from dotenv import load_dotenv
from utils.rate_limiter import safe_invoke

load_dotenv()


def get_llm():
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0.2,
    )


SYSTEM_PROMPT = """You are a Responsible AI auditor specializing in hiring bias detection.

Analyze a parsed job description for language or criteria that could introduce:
- **Gender bias**: gendered language ("rockstar", "ninja", "aggressive"), male-coded traits
- **Age bias**: graduation year requirements, "recent graduate only", "digital native", overqualification concerns
- **Degree elitism**: requiring prestigious university, "Ivy League preferred", unnecessary degree requirements
- **Socioeconomic bias**: unpaid internship references, networking requirements, expensive certification barriers
- **Accessibility bias**: physical requirements not related to job function
- **Geographic bias**: "must be local" without genuine reason

For each signal found, provide a concrete rewrite suggestion.

Respond with ONLY valid JSON — no markdown, no backticks, no explanation:
{
  "overall_risk": "low" | "medium" | "high",
  "risk_summary": "1-2 sentence executive summary of bias risk",
  "signals": [
    {
      "field": "which JD field contains this",
      "text": "the exact biased text or criterion",
      "bias_type": "gender_coded | age_proxy | degree_elitism | socioeconomic | accessibility | geographic",
      "severity": "low | medium | high",
      "suggestion": "recommended inclusive rewrite"
    }
  ],
  "recommendations": [
    "Actionable recommendation 1",
    "Actionable recommendation 2"
  ],
  "positive_observations": [
    "Any inclusive language or practices already present"
  ]
}

If no bias is detected, return overall_risk: "low" with an empty signals array.
"""


def bias_checker_agent(state: dict) -> dict:
    """
    Reads: state["jd_parsed"]
    Writes: state["bias_report"]
    """
    print("🔎 [Bias Checker] Starting JD audit...")

    jd_parsed = state.get("jd_parsed", {})

    if not jd_parsed:
        print("⚠️  [Bias Checker] No parsed JD to audit.")
        return {
            "bias_report": {
                "overall_risk": "unknown",
                "risk_summary": "JD was not available for bias analysis.",
                "signals": [],
                "recommendations": ["Ensure JD is parsed before running bias check."],
                "positive_observations": []
            },
            "errors": state.get("errors", []) + ["Bias Checker: No parsed JD found"],
            "current_step": "bias_checker_failed"
        }

    llm = get_llm()

    prompt_content = f"""Audit this parsed job description for bias:

{json.dumps(jd_parsed, indent=2)}

Also consider the overall framing: does the language skew toward any demographic?"""

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt_content)
    ]

    try:
        response = safe_invoke(llm, messages)
        raw = response.content.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        bias_report = json.loads(raw)

        risk = bias_report.get("overall_risk", "unknown")
        signal_count = len(bias_report.get("signals", []))

        risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(risk, "⚪")
        print(f"✅ [Bias Checker] Risk: {risk_emoji} {risk.upper()} | "
              f"Signals found: {signal_count}")

        return {
            "bias_report": bias_report,
            "current_step": "bias_checker_done"
        }

    except json.JSONDecodeError as e:
        print(f"❌ [Bias Checker] JSON parse error: {e}")
        return {
            "bias_report": {
                "overall_risk": "unknown",
                "risk_summary": "Bias analysis failed due to a parsing error.",
                "signals": [],
                "recommendations": [],
                "positive_observations": []
            },
            "errors": state.get("errors", []) + [f"Bias Checker JSON error: {str(e)}"],
            "current_step": "bias_checker_failed"
        }
    except Exception as e:
        print(f"❌ [Bias Checker] Error: {e}")
        return {
            "bias_report": {
                "overall_risk": "unknown",
                "risk_summary": f"Bias analysis failed: {str(e)}",
                "signals": [],
                "recommendations": [],
                "positive_observations": []
            },
            "errors": state.get("errors", []) + [f"Bias Checker error: {str(e)}"],
            "current_step": "bias_checker_failed"
        }
