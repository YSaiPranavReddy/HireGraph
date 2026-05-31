"""
smoke_test.py — End-to-end pipeline smoke test (T-10)

Uses inline fake JD + 2 fake resume strings (no PDFs needed).
Makes real LLM calls to Groq + Gemini.
Run with: conda run -n hiregraph python smoke_test.py
"""

import json
from graph.pipeline import run_pipeline

# ── Sample Job Description ────────────────────────────────────────────────────
SAMPLE_JD = """
Job Title: Senior Backend Engineer

We are looking for a Senior Backend Engineer to join our fintech platform team.

Required Skills:
- Python (5+ years)
- FastAPI or Django REST Framework
- PostgreSQL, Redis
- Docker, Kubernetes
- REST API design and microservices architecture

Nice to Have:
- Experience with LangChain or LLM integrations
- AWS or GCP cloud experience
- Apache Kafka or message queue systems

Experience: Minimum 4 years of professional software development experience.

Responsibilities:
- Design and build scalable backend microservices
- Optimize database queries and caching strategies
- Lead code reviews and mentor junior engineers
- Collaborate with product and frontend teams

Education: Bachelor's degree in Computer Science or equivalent practical experience.

Industry: Fintech / Payments
"""

# ── Sample Resumes (inline text, simulating PDF extraction) ──────────────────
RESUME_ALICE = """
Alice Chen
alice.chen@email.com | +1-555-0101 | LinkedIn: /in/alicechen

SUMMARY
Senior software engineer with 6 years building high-throughput backend systems
in Python. Strong background in fintech and payment platforms.

SKILLS
Python, FastAPI, PostgreSQL, Redis, Docker, Kubernetes, AWS, REST APIs,
Microservices, SQLAlchemy, Celery, RabbitMQ, Git, CI/CD, pytest

EXPERIENCE
Senior Backend Engineer — PayFlow Inc (2021–Present)
- Built FastAPI microservices handling 50k requests/day
- Reduced PostgreSQL query latency by 40% through indexing and caching
- Led a team of 4 engineers on payment reconciliation system

Backend Engineer — FinStack Ltd (2019–2021)
- Developed Django REST APIs for banking dashboard
- Integrated Redis caching, reducing API response time by 60%

EDUCATION
B.Tech in Computer Science — IIT Delhi (2019)
"""

RESUME_BOB = """
Bob Malik
bob.malik@email.com | +91-9876543210

ABOUT ME
Full stack developer with 2 years experience. Comfortable with Python and 
JavaScript. Looking to grow into backend engineering.

SKILLS
Python, Flask, MySQL, JavaScript, React, HTML/CSS, Git, Linux basics

EXPERIENCE
Junior Developer — StartupXYZ (2022–2024)
- Built internal Flask APIs for admin dashboard
- Maintained MySQL database schemas
- Fixed bugs and wrote unit tests

Intern — TechCorp (2021)
- Assisted senior developers with frontend tasks

EDUCATION
B.Sc Computer Science — Delhi University (2022)
"""

# ── Run the pipeline ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    resume_texts = [
        {"file_name": "alice_chen.pdf",  "raw_text": RESUME_ALICE},
        {"file_name": "bob_malik.pdf",   "raw_text": RESUME_BOB},
    ]

    result = run_pipeline(
        job_description=SAMPLE_JD,
        resume_texts=resume_texts,
    )

    # ── Pretty print results ──────────────────────────────────────────────────
    print("\n" + "="*60)
    print("📋 PARSED JD")
    print("="*60)
    print(json.dumps(result.get("jd_parsed", {}), indent=2))

    print("\n" + "="*60)
    print("👥 CANDIDATE PROFILES")
    print("="*60)
    for p in result.get("candidate_profiles", []):
        print(f"\n  {p['name']} ({p['file_name']})")
        print(f"  Skills     : {', '.join(p['skills'][:6])}{'...' if len(p['skills']) > 6 else ''}")
        print(f"  Experience : {p['experience_years']} years")
        print(f"  Education  : {p['education']}")

    print("\n" + "="*60)
    print("🏆 RANKED CANDIDATES")
    print("="*60)
    for c in result.get("ranked_candidates", []):
        print(f"\n  #{c['rank']} {c['name']} — Score: {c['score']}/100")
        print(f"  Skills match: {c.get('skills_match', '?')}/40  |  "
              f"Exp fit: {c.get('experience_fit', '?')}/30  |  "
              f"Edu: {c.get('education_fit', '?')}/15  |  "
              f"Role: {c.get('role_relevance', '?')}/15")
        print(f"  Matched: {c.get('matched_skills', [])}")
        print(f"  Missing: {c.get('missing_skills', [])}")
        print(f"  💬 {c.get('reasoning', '')}")

    print("\n" + "="*60)
    print("🔎 BIAS REPORT")
    print("="*60)
    bias = result.get("bias_report", {})
    risk = bias.get("overall_risk", "unknown")
    risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(risk, "⚪")
    print(f"  Overall Risk: {risk_emoji} {risk.upper()}")
    print(f"  Summary: {bias.get('risk_summary', '')}")
    signals = bias.get("signals", [])
    if signals:
        print(f"\n  Signals ({len(signals)}):")
        for s in signals:
            print(f"    [{s.get('severity','?').upper()}] {s.get('bias_type','?')} — {s.get('text','')}")
            print(f"    → {s.get('suggestion','')}")
    else:
        print("  No bias signals detected.")
    recs = bias.get("recommendations", [])
    if recs:
        print(f"\n  Recommendations:")
        for r in recs:
            print(f"    • {r}")

    print("\n" + "="*60)
    print("✉️  OUTREACH EMAILS")
    print("="*60)
    for email in result.get("outreach_emails", []):
        print(f"\n  To: {email['candidate_name']}")
        print(f"  Subject: {email['subject']}")
        print(f"  Body:\n")
        for line in email['body'].split('\\n'):
            print(f"    {line}")

    if result.get("errors"):
        print("\n" + "="*60)
        print("⚠️  PIPELINE ERRORS")
        print("="*60)
        for err in result["errors"]:
            print(f"  - {err}")

    print("\n✅ Smoke test complete.\n")
