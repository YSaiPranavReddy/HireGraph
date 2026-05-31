"""
ui/app.py — HireGraph Streamlit Frontend

Calls the FastAPI backend at localhost:8000.
Run with: streamlit run ui/app.py

Sections:
  1. Sidebar   — config + model info
  2. Upload    — JD text + resume PDFs
  3. Pipeline  — run button + live progress
  4. Results   — ranked candidates with score breakdown
  5. Bias      — audit report with color-coded signals
  6. Outreach  — email drafts with copy buttons
"""

import sys
import os
import json
import time
import requests
import streamlit as st
from pathlib import Path

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="HireGraph — AI Hiring Assistant",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

BACKEND_URL = "http://localhost:8000"

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------

st.markdown("""
<style>
    /* Main background */
    .stApp { background-color: #0f1117; }

    /* Score badge */
    .score-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 700;
        font-size: 1.1rem;
    }
    .score-high   { background: #1a3a2a; color: #4ade80; border: 1px solid #4ade80; }
    .score-medium { background: #3a2a0a; color: #fbbf24; border: 1px solid #fbbf24; }
    .score-low    { background: #3a1a1a; color: #f87171; border: 1px solid #f87171; }

    /* Rank card */
    .rank-card {
        background: #1a1d27;
        border: 1px solid #2d3147;
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        margin-bottom: 1rem;
    }

    /* Bias signal row */
    .signal-row {
        background: #1e1a10;
        border-left: 4px solid #fbbf24;
        border-radius: 6px;
        padding: 0.7rem 1rem;
        margin-bottom: 0.5rem;
    }
    .signal-high   { border-left-color: #f87171; background: #1e1212; }
    .signal-medium { border-left-color: #fbbf24; background: #1e1a10; }
    .signal-low    { border-left-color: #4ade80; background: #121e14; }

    /* Email card */
    .email-card {
        background: #131720;
        border: 1px solid #2d3147;
        border-radius: 10px;
        padding: 1.2rem 1.5rem;
        font-family: 'Courier New', monospace;
        white-space: pre-wrap;
        font-size: 0.88rem;
        line-height: 1.6;
    }

    /* Divider */
    hr { border-color: #2d3147; }

    /* Metric delta override */
    [data-testid="stMetricDelta"] { font-size: 0.8rem; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def score_color_class(score: float) -> str:
    if score >= 70: return "score-high"
    if score >= 40: return "score-medium"
    return "score-low"


def signal_class(severity: str) -> str:
    return f"signal-{severity.lower()}" if severity.lower() in ("high","medium","low") else "signal-medium"


def risk_emoji(risk: str) -> str:
    return {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(risk.lower(), "⚪")


def check_backend() -> bool:
    try:
        r = requests.get(f"{BACKEND_URL}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/artificial-intelligence.png", width=64)
    st.title("HireGraph")
    st.caption("AI-Powered Multi-Agent Hiring Assistant")
    st.divider()

    # Backend status
    if check_backend():
        st.success("Backend connected ✓", icon="🟢")
    else:
        st.error("Backend offline — start with:\n`uvicorn main:app --reload`", icon="🔴")

    st.divider()

    # Model routing info
    st.markdown("**Model Routing**")
    st.markdown("""
| Agent | Model |
|---|---|
| JD Parser | `8b-instant` |
| Resume Screener | `8b-instant` |
| Ranker | `70b-versatile` |
| Bias Checker | `70b-versatile` |
| Outreach | `70b-versatile` |
""")

    st.divider()
    top_n = st.slider("Outreach emails for top N", 1, 5, 3)
    st.caption("Only top-N ranked candidates get outreach emails drafted.")


# ---------------------------------------------------------------------------
# Title
# ---------------------------------------------------------------------------

st.markdown("# 🧠 HireGraph")
st.markdown("### AI-Powered Multi-Agent Hiring Pipeline")
st.markdown("Upload a job description and resumes — the pipeline screens, ranks, audits for bias, and drafts outreach emails automatically.")
st.divider()


# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------

if "result" not in st.session_state:
    st.session_state.result = None
if "running" not in st.session_state:
    st.session_state.running = False
if "jd_extracted" not in st.session_state:
    st.session_state.jd_extracted = ""   # text extracted from JD PDF
if "jd_pdf_name" not in st.session_state:
    st.session_state.jd_pdf_name = ""


# ---------------------------------------------------------------------------
# SECTION 1: Job Description — two-mode input
# ---------------------------------------------------------------------------

st.markdown("## 📋 Step 1 — Job Description")

jd_mode = st.radio(
    "How will you provide the JD?",
    options=["Paste Text", "Upload PDF"],
    horizontal=True,
    key="jd_mode",
)

jd_text  = ""   # final resolved text passed to the pipeline
jd_ready = False

if jd_mode == "Paste Text":
    jd_col, tip_col = st.columns([3, 1])
    with jd_col:
        jd_text = st.text_area(
            "Paste your job description here",
            height=220,
            placeholder="Job Title: Senior Backend Engineer\n\nRequired Skills:\n- Python (5+ years)\n- FastAPI or Django REST Framework...",
            key="jd_input",
        )
    with tip_col:
        st.markdown("""
**Tips for best results:**
- Include required skills
- Specify min experience
- List responsibilities
- Mention education req.

The JD Parser extracts all criteria automatically.
""")
    jd_ready = bool(jd_text.strip())

else:  # Upload PDF mode
    jd_pdf_col, jd_prev_col = st.columns([1, 1])

    with jd_pdf_col:
        jd_pdf_file = st.file_uploader(
            "Upload Job Description PDF",
            type=["pdf"],
            key="jd_pdf_upload",
            help="Upload the company JD as a PDF — text will be extracted automatically.",
        )

        if jd_pdf_file:
            # Only re-extract if a new file is uploaded
            if jd_pdf_file.name != st.session_state.jd_pdf_name:
                with st.spinner("Extracting text from JD PDF..."):
                    try:
                        resp = requests.post(
                            f"{BACKEND_URL}/parse-jd",
                            files=[("jd_pdf", (jd_pdf_file.name, jd_pdf_file.getvalue(), "application/pdf"))],
                            timeout=30,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            st.session_state.jd_extracted = data["extracted_text"]
                            st.session_state.jd_pdf_name  = jd_pdf_file.name
                            st.success(f"✅ Extracted {data['char_count']:,} characters from **{jd_pdf_file.name}**")
                        else:
                            st.error(f"Extraction failed: {resp.text}")
                    except Exception as e:
                        st.error(f"Could not reach backend: {e}")
            else:
                st.success(f"✅ Using extracted text from **{st.session_state.jd_pdf_name}**")

    with jd_prev_col:
        if st.session_state.jd_extracted:
            st.markdown("**Extracted JD preview** (editable)")
            # Let user tweak extracted text before running
            st.session_state.jd_extracted = st.text_area(
                "Extracted JD text",
                value=st.session_state.jd_extracted,
                height=220,
                key="jd_extracted_edit",
                label_visibility="collapsed",
            )
        else:
            st.info("Upload a JD PDF on the left — the extracted text will appear here for review.")

    jd_text  = st.session_state.jd_extracted
    jd_ready = bool(jd_text.strip())
    # Store the original file object for sending to backend
    # We'll detect mode in the run section via jd_mode

st.markdown("## 📄 Step 2 — Resume PDFs")
uploaded_files = st.file_uploader(
    "Upload one or more candidate resumes (PDF)",
    type=["pdf"],
    accept_multiple_files=True,
    key="resume_upload",
)

if uploaded_files:
    st.success(f"{len(uploaded_files)} resume(s) uploaded: {', '.join(f.name for f in uploaded_files)}")




# ---------------------------------------------------------------------------
# SECTION 2: Run
# ---------------------------------------------------------------------------

st.divider()
st.markdown("## ⚡ Step 3 — Run Pipeline")

col_run, col_reset = st.columns([1, 5])

with col_run:
    run_clicked = st.button(
        "🚀 Run HireGraph",
        type="primary",
        disabled=st.session_state.running or not jd_ready or not uploaded_files,
        use_container_width=True,
    )

with col_reset:
    if st.session_state.result and st.button("🔄 Reset", use_container_width=False):
        st.session_state.result = None
        st.session_state.jd_extracted = ""
        st.session_state.jd_pdf_name  = ""
        st.rerun()

if not jd_ready:
    st.caption("⬆️ Add a job description (paste or upload PDF) to enable the Run button.")
elif not uploaded_files:
    st.caption("⬆️ Upload at least one resume PDF to enable the Run button.")

if run_clicked:
    if not check_backend():
        st.error("Backend is not running. Start it with: `uvicorn main:app --reload --port 8000`")
    else:
        st.session_state.running = True
        st.session_state.result = None

        # Progress display
        progress_bar = st.progress(0)
        status_text  = st.empty()
        agent_log    = st.empty()

        stages = [
            (15, "🔍 JD Parser — extracting skills & criteria..."),
            (35, "📄 Resume Screener — parallel extraction running..."),
            (50, "🔎 Bias Checker — auditing JD for bias signals..."),
            (70, "🏆 Ranker — scoring & ranking candidates..."),
            (90, "✉️ Outreach Drafter — writing personalized emails..."),
            (100, "✅ Pipeline complete!"),
        ]

        try:
            # Build multipart payload
            files_payload = [
                ("resumes", (f.name, f.getvalue(), "application/pdf"))
                for f in uploaded_files
            ]

            # JD: send as text field (works for both modes —
            # PDF mode already extracted text into jd_text via /parse-jd)
            data_payload = {"jd_text": jd_text}

            # Animate progress while waiting for response
            with st.spinner("Running pipeline..."):
                for pct, msg in stages[:-1]:
                    progress_bar.progress(pct)
                    status_text.markdown(f"**{msg}**")
                    time.sleep(0.4)

                response = requests.post(
                    f"{BACKEND_URL}/run/text",
                    data=data_payload,
                    files=files_payload,
                    timeout=300,
                )

            progress_bar.progress(100)
            status_text.markdown("**✅ Pipeline complete!**")

            if response.status_code == 200:
                st.session_state.result = response.json()
            else:
                st.error(f"Backend error {response.status_code}: {response.text}")

        except requests.exceptions.ConnectionError:
            st.error("Could not connect to backend. Is it running?")
        except requests.exceptions.Timeout:
            st.error("Pipeline timed out (>5 min). Try fewer resumes.")
        except Exception as e:
            st.error(f"Unexpected error: {e}")
        finally:
            st.session_state.running = False
            time.sleep(1)
            progress_bar.empty()
            status_text.empty()

        if st.session_state.result:
            st.rerun()


# ---------------------------------------------------------------------------
# SECTION 3: Results (only shown after pipeline runs)
# ---------------------------------------------------------------------------

if st.session_state.result:
    result = st.session_state.result

    # Summary metrics row
    st.divider()
    st.markdown("## 📊 Pipeline Results")

    ranked     = result.get("ranked_candidates", [])
    profiles   = result.get("candidate_profiles", [])
    bias       = result.get("bias_report", {})
    emails     = result.get("outreach_emails", [])
    errors     = result.get("errors", [])

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Candidates Screened",  len(profiles))
    m2.metric("Ranked",               len(ranked))
    m3.metric("Top Score",            f"{ranked[0]['score']:.1f}/100" if ranked else "—")
    m4.metric("Bias Risk",            bias.get("overall_risk","—").upper())
    m5.metric("Emails Drafted",       len(emails))

    if errors:
        with st.expander(f"⚠️ {len(errors)} pipeline warning(s)"):
            for e in errors:
                st.caption(e)

    # ── Tab layout ──────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "🏆 Ranked Candidates",
        "🔎 Bias Report",
        "✉️ Outreach Emails",
        "📋 Raw JD Parse",
    ])

    # ── TAB 1: Ranked Candidates ────────────────────────────────────────────
    with tab1:
        if not ranked:
            st.warning("No ranked candidates. Check pipeline errors above.")
        else:
            st.markdown(f"**{len(ranked)} candidate(s) ranked** — sorted by composite score (100 = perfect match)")
            st.divider()

            for c in ranked:
                score      = c.get("score", 0)
                css_class  = score_color_class(score)
                name       = c.get("name", "Unknown")
                rank       = c.get("rank", "?")
                reasoning  = c.get("reasoning", "")
                matched    = c.get("matched_skills", [])
                missing    = c.get("missing_skills", [])
                s_skills   = c.get("skills_match", 0)
                s_exp      = c.get("experience_fit", 0)
                s_edu      = c.get("education_fit", 0)
                s_role     = c.get("role_relevance", 0)

                with st.container():
                    # Header row
                    h_col, s_col = st.columns([4, 1])
                    with h_col:
                        st.markdown(f"### #{rank} &nbsp; {name}")
                    with s_col:
                        st.markdown(
                            f'<div class="score-badge {css_class}">{score:.1f} / 100</div>',
                            unsafe_allow_html=True,
                        )

                    # Score breakdown bar chart
                    score_data = {
                        "Skills (40)":      s_skills,
                        "Experience (30)":  s_exp,
                        "Education (15)":   s_edu,
                        "Role Fit (15)":    s_role,
                    }
                    st.bar_chart(score_data, height=120)

                    # Skills
                    det_col1, det_col2 = st.columns(2)
                    with det_col1:
                        if matched:
                            st.markdown("**✅ Matched skills**")
                            st.markdown(" ".join(f"`{s}`" for s in matched))
                    with det_col2:
                        if missing:
                            st.markdown("**❌ Missing skills**")
                            st.markdown(" ".join(f"`{s}`" for s in missing))

                    # Reasoning
                    if reasoning:
                        st.info(f"**Ranker reasoning:** {reasoning}")

                    st.divider()

    # ── TAB 2: Bias Report ──────────────────────────────────────────────────
    with tab2:
        risk      = bias.get("overall_risk", "unknown")
        summary   = bias.get("risk_summary", "")
        signals   = bias.get("signals", [])
        recs      = bias.get("recommendations", [])
        positives = bias.get("positive_observations", [])

        # Overall badge
        risk_col, _ = st.columns([1, 3])
        with risk_col:
            st.markdown(
                f"<h2 style='text-align:center'>{risk_emoji(risk)} {risk.upper()}</h2>",
                unsafe_allow_html=True,
            )

        if summary:
            st.markdown(f"> {summary}")

        st.divider()

        if signals:
            st.markdown(f"### Bias Signals Detected ({len(signals)})")
            for sig in signals:
                sev      = sig.get("severity", "medium")
                btype    = sig.get("bias_type", "").replace("_", " ").title()
                text     = sig.get("text", "")
                suggest  = sig.get("suggestion", "")
                field    = sig.get("field", "")

                badge = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(sev, "⚪")
                st.markdown(
                    f"""<div class="signal-row {signal_class(sev)}">
                        <strong>{badge} {btype}</strong> &nbsp;·&nbsp; <em>{field}</em><br/>
                        <span style="color:#ccc">"{text}"</span><br/>
                        <span style="color:#6ee7b7">→ {suggest}</span>
                    </div>""",
                    unsafe_allow_html=True,
                )
        else:
            st.success("No bias signals detected in this job description.")

        if recs:
            st.divider()
            st.markdown("### Recommendations")
            for r in recs:
                st.markdown(f"• {r}")

        if positives:
            st.divider()
            st.markdown("### Positive Observations")
            for p in positives:
                st.markdown(f"✅ {p}")

    # ── TAB 3: Outreach Emails ──────────────────────────────────────────────
    with tab3:
        if not emails:
            st.warning("No outreach emails were drafted. Check pipeline errors.")
        else:
            st.markdown(f"**{len(emails)} personalized outreach email(s) drafted**")
            st.divider()

            for email in emails:
                cname   = email.get("candidate_name", "Candidate")
                subject = email.get("subject", "")
                body    = email.get("body", "")

                with st.expander(f"✉️ {cname} — {subject}", expanded=True):
                    st.markdown(f"**Subject:** `{subject}`")
                    st.markdown("**Body:**")
                    st.markdown(
                        f'<div class="email-card">{body}</div>',
                        unsafe_allow_html=True,
                    )
                    # Copy button (copies to clipboard via JS)
                    full_text = f"Subject: {subject}\n\n{body}"
                    st.code(full_text, language=None)
                    st.caption("Use the copy icon on the code block above to copy the email.")

    # ── TAB 4: Raw JD Parse ─────────────────────────────────────────────────
    with tab4:
        jd_parsed = result.get("jd_parsed", {})
        if jd_parsed:
            st.markdown(f"**Role:** {jd_parsed.get('role_title','—')}")
            st.markdown(f"**Industry:** {jd_parsed.get('industry','—')}")
            st.markdown(f"**Min Experience:** {jd_parsed.get('min_experience_years','—')} years")
            st.markdown(f"**Education:** {jd_parsed.get('education_requirement','—')}")

            col_req, col_nice = st.columns(2)
            with col_req:
                st.markdown("**Required Skills**")
                for s in jd_parsed.get("required_skills", []):
                    st.markdown(f"- `{s}`")
            with col_nice:
                st.markdown("**Nice-to-Have**")
                for s in jd_parsed.get("nice_to_have_skills", []):
                    st.markdown(f"- `{s}`")

            st.markdown("**Responsibilities**")
            for r in jd_parsed.get("responsibilities", []):
                st.markdown(f"- {r}")

            st.divider()
            with st.expander("Raw JSON"):
                st.json(jd_parsed)
        else:
            st.warning("JD was not parsed. Check pipeline errors.")
