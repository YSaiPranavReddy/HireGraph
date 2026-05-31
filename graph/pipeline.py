"""
graph/pipeline.py — HireGraph LangGraph Pipeline

Architecture (with critique loop):

    START
      -> jd_parser_node               (sequential)
      -> [fan_out_router]             (conditional edge, returns Send() list)
          |-- resume_screener_node x N  (parallel, Groq 8B, one per resume)
          |-- bias_checker_node         (parallel, Groq 70B, reads jd_parsed)
      -> [implicit barrier — all parallel branches must finish]
      -> ranker_node                  (sequential, Groq 70B)
      -> critique_node                (sequential, Gemini 2.0 Flash — different model)
          |-- approved OR retries >= 2  -> outreach_drafter_node
          |-- not approved              -> ranker_node  (retry with feedback, max 2x)
      -> outreach_drafter_node        (sequential, Groq 70B)
      -> END

Key LangGraph concepts used:
  - fan_out_router: CONDITIONAL EDGE returning List[Send] for parallel dispatch
  - critique_router: CONDITIONAL EDGE returning node name for the loop back-edge
  - Annotated + operator.add on candidate_profiles merges parallel fan-in outputs
  - critique_retry_count acts as the circuit breaker (max 2 retries)
"""

import os
from typing import List
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from graph.state import HireGraphState
from agents.jd_parser import jd_parser_agent
from agents.resume_screener import resume_screener_agent
from agents.bias_checker import bias_checker_agent
from agents.team_gap_analyzer import team_gap_analyzer_agent
from agents.ranker import ranker_agent
from agents.critique import critique_agent, MAX_RETRIES
from agents.outreach_drafter import outreach_drafter_agent

load_dotenv()

# LangSmith: map LANGSMITH_API_KEY -> LANGCHAIN_API_KEY if not already set
if os.getenv("LANGSMITH_API_KEY") and not os.getenv("LANGCHAIN_API_KEY"):
    os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY")


# ---------------------------------------------------------------------------
# Node wrappers
# ---------------------------------------------------------------------------

def jd_parser_node(state: HireGraphState) -> dict:
    return jd_parser_agent(state)


def resume_screener_node(state: dict) -> dict:
    """Called once per resume via Send() — receives a flat payload dict."""
    return resume_screener_agent(state)


def bias_checker_node(state: dict) -> dict:
    return bias_checker_agent(state)


def team_gap_analyzer_node(state: dict) -> dict:
    return team_gap_analyzer_agent(state)


def ranker_node(state: HireGraphState) -> dict:
    return ranker_agent(state)


def critique_node(state: HireGraphState) -> dict:
    return critique_agent(state)


def outreach_drafter_node(state: HireGraphState) -> dict:
    return outreach_drafter_agent(state)


# ---------------------------------------------------------------------------
# Fan-out conditional edge router  (NOT a node — returns List[Send])
# ---------------------------------------------------------------------------

def fan_out_router(state: HireGraphState) -> List[Send]:
    """
    Called as a conditional edge after jd_parser_node.
    Returns a list of Send objects — LangGraph runs them all in parallel.
    Each Send carries its own isolated state dict.
    """
    resume_texts = state.get("resume_texts", [])
    jd_parsed    = state.get("jd_parsed", {})
    job_desc     = state.get("job_description", "")
    team_data    = state.get("team_data", "")

    print(f"[Fan-Out] Dispatching {len(resume_texts)} resume screener(s) + bias checker + team gap analyzer")

    sends = []

    # One Send per resume -> parallel resume_screener_node calls
    for resume in resume_texts:
        sends.append(
            Send("resume_screener_node", {
                "file_name":       resume.get("file_name", "unknown.pdf"),
                "raw_text":        resume.get("raw_text", ""),
                "job_description": job_desc,
                "jd_parsed":       jd_parsed,
            })
        )

    # Bias checker
    sends.append(
        Send("bias_checker_node", {
            "jd_parsed":       jd_parsed,
            "job_description": job_desc,
        })
    )

    # Team gap analyzer (fast-paths to empty dict if team_data is absent)
    sends.append(
        Send("team_gap_analyzer_node", {
            "team_data":  team_data,
            "jd_parsed":  jd_parsed,
        })
    )

    return sends


# ---------------------------------------------------------------------------
# Critique loop router  (conditional edge — decides retry or proceed)
# ---------------------------------------------------------------------------

def critique_router(state: HireGraphState) -> str:
    """
    Called as a conditional edge after critique_node.
    Returns the name of the next node to execute.

    Logic:
      - approved=True  OR  retry_count >= MAX_RETRIES  -> proceed to outreach
      - approved=False AND retry_count <  MAX_RETRIES  -> loop back to ranker
    """
    critique   = state.get("critique_result", {})
    retry_count = state.get("critique_retry_count", 0)

    approved = critique.get("approved", True)

    if approved or retry_count >= MAX_RETRIES:
        if not approved:
            print(f"[Critique Router] Max retries ({MAX_RETRIES}) reached — proceeding despite issues")
        else:
            print(f"[Critique Router] Approved after {retry_count} attempt(s) — proceeding to Outreach")
        return "outreach_drafter_node"
    else:
        print(f"[Critique Router] Retry {retry_count}/{MAX_RETRIES} — sending back to Ranker")
        return "ranker_node"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_pipeline():
    """Build and compile the HireGraph LangGraph pipeline."""
    graph = StateGraph(HireGraphState)

    # Register nodes
    graph.add_node("jd_parser_node",          jd_parser_node)
    graph.add_node("resume_screener_node",     resume_screener_node)
    graph.add_node("bias_checker_node",        bias_checker_node)
    graph.add_node("team_gap_analyzer_node",   team_gap_analyzer_node)
    graph.add_node("ranker_node",              ranker_node)
    graph.add_node("critique_node",            critique_node)
    graph.add_node("outreach_drafter_node",    outreach_drafter_node)

    # START -> jd_parser
    graph.add_edge(START, "jd_parser_node")

    # jd_parser -> fan_out_router (conditional edge returning Send list)
    graph.add_conditional_edges(
        "jd_parser_node",
        fan_out_router,
        ["resume_screener_node", "bias_checker_node", "team_gap_analyzer_node"]
    )

    # Parallel branches -> ranker (LangGraph barrier: waits for ALL branches)
    graph.add_edge("resume_screener_node",   "ranker_node")
    graph.add_edge("bias_checker_node",      "ranker_node")
    graph.add_edge("team_gap_analyzer_node", "ranker_node")

    # ranker -> critique (always)
    graph.add_edge("ranker_node", "critique_node")

    # critique -> critique_router (loop or proceed)
    graph.add_conditional_edges(
        "critique_node",
        critique_router,
        {
            "outreach_drafter_node": "outreach_drafter_node",
            "ranker_node":           "ranker_node",
        }
    )

    # outreach -> END
    graph.add_edge("outreach_drafter_node", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# High-level runner
# ---------------------------------------------------------------------------

def run_pipeline(job_description: str, resume_texts: List[dict], team_data: str = "") -> dict:
    """
    Entry point for FastAPI and Streamlit.

    Args:
        job_description: raw JD text string
        resume_texts:    list of {"file_name": str, "raw_text": str}

    Returns:
        Final HireGraphState dict with all outputs populated.
    """
    pipeline = build_pipeline()

    initial_state: HireGraphState = {
        "job_description":    job_description,
        "resume_texts":       resume_texts,
        "team_data":          team_data,
        "jd_parsed":          {},
        "candidate_profiles": [],
        "ranked_candidates":  [],
        "team_gap_analysis":  {},
        "bias_report":          {},
        "outreach_emails":      [],
        "rejection_emails":     [],
        "critique_result":    {},
        "critique_feedback":  "",
        "critique_retry_count": 0,
        "errors":             [],
        "current_step":       "start",
    }

    print("\n" + "="*60)
    print("[HireGraph] Pipeline Starting")
    print("="*60)
    print(f"  JD length : {len(job_description)} chars")
    print(f"  Resumes   : {len(resume_texts)}")
    print("="*60 + "\n")

    result = pipeline.invoke(initial_state)

    critique    = result.get("critique_result", {})
    retry_count = result.get("critique_retry_count", 0)

    print("\n" + "="*60)
    print("[DONE] Pipeline Complete")
    print("="*60)
    print(f"  Candidates screened : {len(result.get('candidate_profiles', []))}")
    print(f"  Candidates ranked   : {len(result.get('ranked_candidates', []))}")
    print(f"  Critique            : {'APPROVED' if critique.get('approved', True) else 'FLAGGED'} "
          f"after {retry_count} attempt(s), {len(critique.get('flags', []))} flag(s)")
    print(f"  Bias risk           : {result.get('bias_report', {}).get('overall_risk', 'unknown')}")
    print(f"  Outreach emails     : {len(result.get('outreach_emails', []))}")
    print(f"  Rejection letters   : {len(result.get('rejection_emails', []))}")

    if result.get("errors"):
        print(f"  [WARN] {len(result['errors'])} error(s):")
        for err in result["errors"]:
            print(f"    - {err}")
    print("="*60 + "\n")

    return result
