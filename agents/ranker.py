"""
agents/ranker.py — Ranker Agent (Groq llama-3.3-70b-versatile)

Scores each candidate INDIVIDUALLY against the JD, then sorts in Python.

Why per-candidate scoring?
  When all candidates are scored together in one prompt, the LLM shortcuts —
  it compares candidates against each other instead of evaluating each one
  against the JD. This causes clustering, inconsistency, and bias toward
  whichever candidate appears first or has the longest skills list.

  Scoring one at a time forces the model to evaluate, not compare.
  Sorting is then pure Python — deterministic and consistent.

Reads:  state["candidate_profiles"]  — list of profile dicts
        state["jd_parsed"]           — structured JD dict
        state["critique_feedback"]   — correction from Critique (on retry)
        state["critique_retry_count"]
Writes: state["ranked_candidates"]   — sorted list of scored dicts
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
        temperature=0.1,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Single-candidate scoring prompt.
# The model scores ONE candidate. No comparisons, no rankings, just evaluation.
# ─────────────────────────────────────────────────────────────────────────────

SCORE_PROMPT = """You are a technical recruiter evaluating ONE candidate for a specific role.
Your job is to score this candidate against the job description provided.
Do not compare to other candidates. Evaluate this person on their own merits vs the JD.

Always respond with ONLY valid JSON, no markdown, no backticks.

============================================================
STEP 1 — DEALBREAKER CHECK
============================================================
For each skill in dealbreaker_skills, check the candidate's evidence in this order:

  a) projects[].tech_stack — did they BUILD something using this skill?
  b) projects[].description — does the description imply this concept was used?
  c) skills[] — is it at least listed?

SEMANTIC REASONING — do not keyword match:
  Reason about concepts, not keywords.

  - A project implementing the CONCEPT even without the exact framework name = satisfied
  - A different tool that solves the same problem = satisfied
  - Listing a skill without any project using it = half credit only
  - No mention anywhere = absent

  Apply this reasoning to whatever skills the JD requires.
  If you can see the CONCEPT being implemented in a project description,
  that satisfies the dealbreaker — even if the exact framework name is absent.

  Only set dealbreaker_flag = true when the candidate has:
  - No project demonstrating the concept (not just the framework name)
  - AND the skill is not in their skills list at all

If dealbreaker_flag = true for a skill:
  → Add to dealbreaker_flags: ["missing: <skill>"]
  → Score that skill as ZERO in skills_match (no partial credit)
  → In role_relevance: reduce by 8-10 pts — candidate cannot perform a core job function
  → Do NOT apply any score cap — let the dimensions score naturally
  → The final score reflects the gap proportionally based on overall profile strength
  → The dealbreaker_flags field is for UI transparency only — it does not cap the score

  Two candidates can both have dealbreaker_flags and score very differently:
  - Candidate missing dealbreaker AND most other skills → low skills_match + low role_relevance → 30-45
  - Candidate missing only the dealbreaker skill, strong elsewhere → decent skills_match + reduced role_relevance → 55-75
  This is correct and honest — do not flatten both to the same number.

============================================================
STEP 2 — SCORE THESE DIMENSIONS
============================================================

skills_match (40 pts max):
  For each required skill, find the strongest evidence:
  - Project tech_stack or description demonstrates the concept → full credit
    (production project → 2.5x, non-production → 2x vs listed-only)
  - Skill listed but no project evidence → half credit
  - Not found anywhere → zero, add to missing_skills
  - Dealbreaker skill absent → zero (per Step 1)
  Nice-to-have skills: up to +5 bonus (within 40 cap)

experience_fit (30 pts max):
  Intern/junior role:
    Project complexity and count = 70% of this score
    experience_years = 30% of this score
    Each deployed/production project = +3 bonus pts (max +9)
  Mid/senior/lead role:
    experience_years = 70%, project complexity = 30%

education_fit (15 pts max):
  If education_is_strict = false, strong project evidence substitutes for degree.
  Match education level to the seniority level of the role.

role_relevance (15 pts max):
  How directly do this candidate's projects and previous roles map to
  the JD's stated responsibilities?
  Directly relevant project > unrelated full-time job for intern/junior roles.
  If a dealbreaker skill is absent: reduce role_relevance by 8-10 pts.

============================================================
STEP 3 — SELF CHECK BEFORE RESPONDING
============================================================
  - Does your reasoning cite SPECIFIC projects as evidence?
    "strong candidate" is not reasoning. "Project X demonstrates skill Y" is.
  - Is your score consistent with the evidence you cited?
    Many missing required skills → score should be below 65.
    Strong project evidence for most required skills → score should be 75+.
  - If dealbreaker_flags is non-empty: confirm role_relevance was reduced by 8-10 pts.
    Do NOT apply a flat cap — the score must reflect the full profile.

============================================================
RESPONSE FORMAT
============================================================
{
  "name": "candidate full name",
  "file_name": "filename.pdf",
  "score": 82.5,
  "skills_match": 33,
  "experience_fit": 25,
  "education_fit": 13,
  "role_relevance": 12,
  "matched_skills": ["Python", "FastAPI", "RAG"],
  "missing_skills": ["LangGraph"],
  "dealbreaker_flags": [],
  "key_projects": ["NyayLens - Hybrid RAG + agentic orchestration"],
  "reasoning": "2-3 sentences citing specific project evidence for the score given."
}
"""


def _score_one(llm, profile: dict, jd_parsed: dict, feedback: str = "", team_gap: dict = None) -> dict:
    """
    Score a single candidate against the JD.
    Returns a scored dict or a fallback dict on error.
    """
    # Build a focused, token-efficient candidate summary
    candidate_summary = {
        "name":                profile.get("name", "Unknown"),
        "file_name":           profile.get("file_name", ""),
        "skills":              profile.get("skills", []),
        "demonstrated_skills": profile.get("demonstrated_skills", {"evidence": []}),
        "skill_depth":         profile.get("skill_depth", {}),
        "experience_years":    profile.get("experience_years", 0),
        "experience_months":   profile.get("experience_months", 0),
        "education":           profile.get("education", ""),
        "education_level":     profile.get("education_level", "other"),
        "previous_roles":      profile.get("previous_roles", []),
        "projects":            profile.get("projects", []),
        "summary":             profile.get("summary", ""),
    }

    jd_summary = {
        "role_title":          jd_parsed.get("role_title", ""),
        "required_skills":     jd_parsed.get("required_skills", []),
        "dealbreaker_skills":  jd_parsed.get("dealbreaker_skills", []),
        "nice_to_have_skills": jd_parsed.get("nice_to_have_skills", []),
        "seniority_level":     jd_parsed.get("seniority_level", ""),
        "education_is_strict": jd_parsed.get("education_is_strict", False),
        "skill_categories":    jd_parsed.get("skill_categories", {}),
        "responsibilities":    jd_parsed.get("responsibilities", []),
    }

    user_content = f"""JOB DESCRIPTION:
{json.dumps(jd_summary, indent=2)}

CANDIDATE TO SCORE:
{json.dumps(candidate_summary, indent=2)}

Score this candidate against the job description above."""

    # Inject team gap context when available — adjusts role_relevance
    if team_gap and team_gap.get("gap_skills"):
        saturated = team_gap.get("saturated_skills", [])
        gaps      = team_gap.get("gap_skills", [])
        summary   = team_gap.get("analysis_summary", "")
        user_content += f"""

TEAM CONTEXT — adjust role_relevance by ±5 pts:
  Team size: {team_gap.get('team_size', 0)} members
  Skills already well-covered (saturated): {json.dumps(saturated)}
  Skills the team is missing (gaps): {json.dumps(gaps)}
  Analysis: {summary}

  If this candidate brings skills from the GAPS list → +3 to +5 pts on role_relevance
  If this candidate's top skills are ALL in the SATURATED list → -3 to -5 pts on role_relevance
  If mixed → no adjustment"""

    # On critique retry — inject specific feedback for this candidate only
    if feedback:
        user_content += f"""

CORRECTION REQUIRED:
{feedback}

Adjust your score based on this feedback."""

    messages = [
        SystemMessage(content=SCORE_PROMPT),
        HumanMessage(content=user_content)
    ]

    try:
        response = safe_invoke(llm, messages)
        raw = response.content.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        result = json.loads(raw)

        # Transparency only — no score manipulation
        if result.get("dealbreaker_flags"):
            print(f"  [Ranker] ⚠️  {result.get('name')} has dealbreaker flags: {result['dealbreaker_flags']}")

        return result

    except (json.JSONDecodeError, Exception) as e:
        print(f"  [Ranker] ❌ Error scoring {profile.get('name', 'Unknown')}: {e}")
        return {
            "name":             profile.get("name", "Unknown"),
            "file_name":        profile.get("file_name", ""),
            "score":            0,
            "skills_match":     0,
            "experience_fit":   0,
            "education_fit":    0,
            "role_relevance":   0,
            "matched_skills":   [],
            "missing_skills":   [],
            "dealbreaker_flags": ["scoring_error"],
            "key_projects":     [],
            "reasoning":        f"Scoring error: {str(e)[:100]}",
        }


def ranker_agent(state: dict) -> dict:
    """
    Scores each candidate individually, then sorts by score in Python.

    On critique retry: re-scores only the candidates mentioned in the feedback,
    keeps other scores unchanged.
    """
    print("🏆 [Ranker] Starting...")

    profiles           = state.get("candidate_profiles", [])
    jd_parsed          = state.get("jd_parsed", {})
    team_gap_analysis  = state.get("team_gap_analysis", {}) or {}
    critique_feedback  = state.get("critique_feedback", "")
    critique_retry_num = state.get("critique_retry_count", 0)
    existing_ranked    = state.get("ranked_candidates", [])

    if team_gap_analysis.get("gap_skills"):
        print(f"  [Ranker] Team context active — gaps: {', '.join(team_gap_analysis['gap_skills'][:4])}")

    if not profiles:
        print("⚠️  [Ranker] No candidate profiles to rank.")
        return {
            "ranked_candidates": [],
            "errors": state.get("errors", []) + ["Ranker: No candidate profiles found"],
            "current_step": "ranker_failed"
        }

    if not jd_parsed:
        print("⚠️  [Ranker] No parsed JD available.")
        return {
            "ranked_candidates": [],
            "errors": state.get("errors", []) + ["Ranker: No parsed JD found"],
            "current_step": "ranker_failed"
        }

    llm = get_llm()

    # DEBUG — remove after fixing
    # for p in profiles:
    #     name     = p.get("name", "Unknown")
    #     evidence = p.get("demonstrated_skills", {}).get("evidence", [])
    #     projects = p.get("projects", [])
    #     print(f"\n{'='*50}")
    #     print(f"DEBUG: {name}")
    #     print(f"  demonstrated_skills.evidence ({len(evidence)} entries):")
    #     for e in evidence:
    #         print(f"    - {e.get('skill')} in {e.get('project')} (production={e.get('is_production')})")
    #     print(f"  projects ({len(projects)} entries):")
    #     for proj in projects:
    #         print(f"    - {proj.get('name')}: {proj.get('tech_stack')}")
    #         print(f"      desc: {proj.get('description', '')[:100]}")
    #     print(f"{'='*50}\n")


    # ── On retry: surgical re-scoring from per_candidate_feedback verdicts ──
    # critique now returns per_candidate_feedback[name] = {verdict, suggested_score, feedback}
    # verdict "justified"          → keep existing score, no LLM call
    # verdict "too_high"/"too_low" → re-score with that candidate's specific feedback only
    if critique_feedback and critique_retry_num > 0 and existing_ranked:
        print(f"[Ranker] Critique retry {critique_retry_num} — surgical re-scoring...")

        critique_result   = state.get("critique_result", {})
        per_candidate     = critique_result.get("per_candidate_feedback", {})
        scores_by_name    = {c["name"]: c for c in existing_ranked}

        needs_rescore = {
            name
            for name, vdata in per_candidate.items()
            if vdata.get("verdict") in ("too_high", "too_low")
        }

        print(f"[Ranker] Re-scoring {len(needs_rescore)} candidate(s): {needs_rescore or '(none)'}")

        for profile in profiles:
            name = profile.get("name", "")
            if name in needs_rescore:
                # Use this candidate's specific feedback, fall back to full feedback blob
                candidate_feedback = per_candidate.get(name, {}).get("feedback") or critique_feedback
                if candidate_feedback == "null":
                    candidate_feedback = critique_feedback

                print(f"  [Ranker] Re-scoring: {name}")
                result = _score_one(
                    llm, profile, jd_parsed,
                    feedback=candidate_feedback,
                    team_gap=team_gap_analysis,
                )
                scores_by_name[name] = result
            else:
                existing = scores_by_name.get(name, {})
                print(f"  [Ranker] Keeping score: {name} ({existing.get('score', '?')})")

        ranked = list(scores_by_name.values())

    # ── First pass: score all candidates individually ──
    else:
        ranked = []
        for profile in profiles:
            name = profile.get("name", "Unknown")
            print(f"  [Ranker] Scoring: {name}")
            result = _score_one(llm, profile, jd_parsed, team_gap=team_gap_analysis)
            ranked.append(result)

    # ── Sort by score in Python — not by LLM ──
    ranked.sort(key=lambda x: x.get("score", 0), reverse=True)
    for i, candidate in enumerate(ranked):
        candidate["rank"] = i + 1

    print(f"✅ [Ranker] Ranked {len(ranked)} candidates")
    for c in ranked:
        flags = " ⚠️ DEALBREAKER" if c.get("dealbreaker_flags") else ""
        print(f"   #{c['rank']} {c['name']} — {c['score']}/100{flags}")

    return {
        "ranked_candidates": ranked,
        "current_step": "ranker_done"
    }