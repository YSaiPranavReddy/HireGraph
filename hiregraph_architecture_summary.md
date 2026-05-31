# HireGraph — Architecture & Progress Summary

## What HireGraph Does

HireGraph is an AI hiring assistant that automates the entire screening pipeline for HR teams:

1. HR uploads a Job Description (text or PDF) + candidate resumes (PDFs)
2. 6 AI agents work in parallel/sequence to screen, rank, audit, and draft outreach
3. HR gets a ranked shortlist, bias report, AI critique, and personalized emails — in one click

---

## System Architecture

```
┌─────────────────────────────────────────────────┐
│  Browser  (React + Vite — coming tonight)        │
│  Clerk Auth → Protected Dashboard → Results UI   │
└────────────────────┬────────────────────────────┘
                     │ HTTP + Clerk JWT Bearer token
                     ▼
┌─────────────────────────────────────────────────┐
│  FastAPI  (port 8000)                            │
│  POST /run/text   — run full pipeline            │
│  POST /parse-jd   — extract text from JD PDF    │
│  GET  /health     — health check                 │
│  [Clerk JWT middleware — verifies auth]          │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  LangGraph Pipeline                              │
│                                                  │
│  START                                           │
│    │                                             │
│    ▼                                             │
│  JD Parser (Groq 8B)                            │
│    │                                             │
│    ├──► Resume Screener ×N  ──┐  (parallel)     │
│    └──► Bias Checker          │  (parallel)     │
│                               │ barrier          │
│                               ▼                  │
│                         Ranker (Groq 70B)        │
│                               │                  │
│                               ▼                  │
│                     Critique (Gemini 2.5 Flash)  │
│                       │             │            │
│                  approved        not approved    │
│                  OR max retries  AND retries < 2 │
│                       │             │            │
│                       │    ◄────────┘ (loop)     │
│                       ▼                          │
│              Outreach Drafter (Groq 70B)         │
│                       │                          │
│                      END                         │
└─────────────────────────────────────────────────┘
```

---

## LLM Routing Strategy

| Agent | Model | Why |
|-------|-------|-----|
| JD Parser | `groq/llama-3.1-8b-instant` | Fast structured JSON extraction, doesn't need large reasoning capacity |
| Resume Screener ×N | `groq/llama-3.1-8b-instant` | Runs in parallel — 8B uses a separate TPM quota pool from 70B |
| Bias Checker | `groq/llama-3.3-70b-versatile` | Nuanced language analysis needs larger model |
| Ranker | `groq/llama-3.3-70b-versatile` | Multi-criteria scoring requires strong reasoning |
| **Critique** | **`gemini-2.5-flash`** (+ 3 fallbacks) | **Different model family** — Groq 70B judging its own output = confirmation bias |
| Outreach Drafter | `groq/llama-3.3-70b-versatile` | High-quality personalized writing |

---

## Critique Agent — Self-Correcting Loop

The critique agent is the key architectural differentiator:

```
Ranker (Groq 70B) → Critique (Gemini) → approved? → Outreach
                          │
                     not approved
                     + retry < 2
                          │
                          ▼
                     Ranker gets critique_feedback injected into prompt
                     "Alice scored 95 but is missing Docker and Kubernetes.
                      Re-score with at least -15 penalty for missing required skills."
                          │
                          ▼
                     Critique reviews again → approved? → Outreach
```

**Why Gemini for critique?** If the same Groq 70B model that ranked the candidates also critiques them, it tends to approve its own output (self-confirmation bias). Using a different model family (Google Gemini vs Meta Llama) gives a genuine second opinion.

**Fallback chain** (if Gemini quota is exhausted):
```
gemini-2.5-flash → gemini-3.5-flash → gemini-3.1-flash-lite → gemini-2.5-flash-lite → fail safe (auto-approve)
```
No Groq fallback — same-model self-review is worse than no critique.

---

## Rate Limiting Strategy

`utils/rate_limiter.py` → `safe_invoke(llm, messages)` wraps every agent call:

```
429 hit?
  → parse Groq/Gemini's suggested retry delay from error message
  → wait = max(suggested_delay, exponential_backoff)
    Attempt 1: ~5s  |  Attempt 2: ~10s  |  Attempt 3: ~20s
    Attempt 4: ~40s  |  Attempt 5: ~80s  |  Give up → re-raise
  → Non-quota errors re-raised immediately (bugs stay visible)
```

---

## Key Design Decisions Made

| Decision | Rationale |
|----------|-----------|
| `Send()` fan-out instead of sequential loop | Resume screening is I/O bound (LLM API calls) — parallel = N× faster |
| `operator.add` reducer on `candidate_profiles` | LangGraph needs explicit merge strategy for parallel branch outputs |
| Separate 8B / 70B models | 8B runs in parallel without consuming 70B's TPM quota |
| `experience_months` derived in Python, not LLM | LLMs return inconsistent correlated fields; single source of truth avoids bugs |
| Dynamic `TODAY_LABEL` in screener prompt | Hardcoded "May 2025" made all "Present" role calculations wrong |
| Critique fails safe on error | A broken critique should never block the pipeline — auto-approve and log |
| No Express middleware | FastAPI JWT middleware is sufficient; no BFF needed for this use case |

---

## File Map

```
HireGraph/
├── agents/
│   ├── jd_parser.py          Groq 8B — extracts JD structure
│   ├── resume_screener.py    Groq 8B — parallel per resume
│   ├── ranker.py             Groq 70B — scores + ranks candidates
│   ├── bias_checker.py       Groq 70B — JD language audit
│   ├── critique.py           Gemini — judges ranking, loops back if wrong
│   └── outreach_drafter.py   Groq 70B — personalized emails
│
├── graph/
│   ├── state.py              TypedDict schema (all agents share this)
│   └── pipeline.py           LangGraph graph: nodes, edges, critique loop
│
├── utils/
│   ├── rate_limiter.py       safe_invoke() — retry on 429
│   ├── helpers.py            Shared formatting utilities
│   └── pdf_reader.py         PyMuPDF text extraction
│
├── main.py                   FastAPI — /run/text, /parse-jd, /health
├── ui/app.py                 Streamlit UI (being replaced by React)
├── smoke_test.py             End-to-end pipeline test
├── .env                      API keys (gitignored)
└── .env.example              Template for new devs
```

---

## What's Done vs Pending

### ✅ Fully Complete (19 tasks)
- All 6 AI agents
- LangGraph pipeline with parallel fan-out + critique loop
- FastAPI backend (run pipeline, parse JD PDFs)
- Streamlit UI (2-mode JD input, 4 results tabs)
- Rate limiter with exponential backoff
- Experience parsing fix (internships, dynamic dates, months)
- Smoke test passing end-to-end

### ⬜ Pending (tonight)
- React + Vite frontend (T-16 to T-25)
- FastAPI CORS + Clerk JWT middleware (T-26, T-27)

### ⬜ Pending (after frontend)
- 3 sample resume PDFs (T-28)
- README.md (T-29)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite |
| Auth | Clerk (`@clerk/clerk-react`) |
| Routing | React Router v6 |
| HTTP Client | Axios |
| Backend | FastAPI + Uvicorn |
| Orchestration | LangGraph |
| LLM (extraction) | Groq llama-3.1-8b-instant |
| LLM (reasoning) | Groq llama-3.3-70b-versatile |
| LLM (critique) | Google Gemini 2.5 Flash |
| PDF parsing | PyMuPDF (fitz) |
| Environment | Conda `hiregraph` |
| Ports | 8000 (FastAPI) · 5173 (React) |
