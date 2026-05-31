"""
utils/helpers.py — Shared utility functions for HireGraph

No LLM dependencies. Used by FastAPI backend and Streamlit UI.
"""

import json
import re
from typing import List, Optional


def top_n_candidates(ranked_candidates: List[dict], n: int = 3) -> List[dict]:
    """Return the top-N ranked candidates (already sorted by score desc)."""
    return ranked_candidates[:n]


def safe_json_parse(text: str) -> Optional[dict]:
    """
    Attempt to parse a JSON string, stripping markdown fences if present.
    Returns None on failure instead of raising.
    """
    if not text:
        return None
    raw = text.strip()
    # Strip ```json ... ``` or ``` ... ```
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


def risk_color(overall_risk: str) -> str:
    """Map bias risk level to a Streamlit color string."""
    return {
        "low":     "green",
        "medium":  "orange",
        "high":    "red",
    }.get(overall_risk.lower(), "gray")


def risk_badge(overall_risk: str) -> str:
    """Return an emoji badge for bias risk level."""
    return {
        "low":    "🟢 LOW",
        "medium": "🟡 MEDIUM",
        "high":   "🔴 HIGH",
    }.get(overall_risk.lower(), "⚪ UNKNOWN")


def score_bar(score: float, max_score: float = 100.0) -> str:
    """Return a simple ASCII progress bar for a score."""
    filled = int((score / max_score) * 20)
    return "[" + "█" * filled + "░" * (20 - filled) + f"] {score:.1f}/{max_score:.0f}"


def format_skill_list(skills: List[str], limit: int = 8) -> str:
    """Format a skill list as a comma-separated string, truncating if needed."""
    if not skills:
        return "—"
    shown = skills[:limit]
    suffix = f" +{len(skills) - limit} more" if len(skills) > limit else ""
    return ", ".join(shown) + suffix


def summarise_pipeline_result(result: dict) -> dict:
    """
    Extract a compact summary dict from a full pipeline result.
    Used for API responses where the full state is too verbose.
    """
    ranked = result.get("ranked_candidates", [])
    bias   = result.get("bias_report", {})
    emails = result.get("outreach_emails", [])

    return {
        "total_candidates":  len(result.get("candidate_profiles", [])),
        "total_ranked":      len(ranked),
        "top_candidate":     ranked[0].get("name") if ranked else None,
        "top_score":         ranked[0].get("score") if ranked else None,
        "bias_risk":         bias.get("overall_risk", "unknown"),
        "bias_signal_count": len(bias.get("signals", [])),
        "emails_drafted":    len(emails),
        "errors":            result.get("errors", []),
    }
