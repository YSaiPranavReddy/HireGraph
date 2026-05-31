# HireGraph — Task Plan
> Status: `[ ]` not started · `[~]` in progress · `[x]` done

---

## Phase 0 — Infrastructure ✅

- [x] **T-00** · Scaffold directory & stub files
- [x] **T-01** · `requirements.txt` — all deps installed in `hiregraph` conda env
- [x] **T-02** · `.env` + `.env.example` — GROQ_API_KEY, GOOGLE_API_KEY, LANGSMITH_API_KEY

---

## Phase 1 — State Layer ✅

- [x] **T-03** · `graph/state.py` — plain dicts, Annotated reducers for fan-in, critique fields added

---

## Phase 2 — Agents ✅

- [x] **T-04** · `agents/jd_parser.py` — Groq llama-3.1-8b-instant; selective dealbreaker schema; skill_categories
- [x] **T-05** · `agents/resume_screener.py` — Groq llama-3.1-8b-instant; demonstrated_skills + skill_depth extraction; _clean_llm_json() JSON repair
- [x] **T-06** · `agents/ranker.py` — per-candidate scoring; Python sort + rank; structured-flag retry; Python-enforced dealbreaker cap
- [x] **T-07** · `agents/bias_checker.py` — Groq llama-3.3-70b-versatile
- [x] **T-08** · `agents/outreach_drafter.py` — Groq llama-3.3-70b-versatile

---

## Phase 3 — LangGraph Pipeline ✅

- [x] **T-09** · `graph/pipeline.py` — fan_out_router + Send() + barrier + critique loop + compile
- [x] **T-10** · Smoke test — full end-to-end run, all 6 agents, zero errors

---

## Phase 4 — Bonus Enhancements ✅

- [x] **T-B1** · `utils/rate_limiter.py` — exponential backoff retry on 429, parses Groq/Gemini retry-after header
- [x] **T-B2** · `agents/resume_screener.py` — experience fix: internships counted, dynamic TODAY_LABEL, months derived in Python
- [x] **T-B3** · `agents/critique.py` — Gemini critique judge (4-model fallback chain); per-candidate flag logic; NEVER BATCH FLAG rule; semantic dealbreaker check
- [x] **T-B4** · `graph/pipeline.py` — critique loop wired: ranker → critique → router → outreach OR retry ranker (max 2 retries)
- [x] **T-B5** · `graph/state.py` — critique_result, critique_feedback, critique_retry_count fields

---

## Phase 5 — Backend API ✅

- [x] **T-11** · `utils/helpers.py` — shared utilities (JSON cleaning, score viz, bias formatting)
- [x] **T-12** · `main.py` — FastAPI: POST /run/text, POST /parse-jd, GET /health; Clerk JWT middleware; CORS; graceful PDF parse error handling

---

## Phase 6 — Streamlit UI ✅ (superseded by Phase 7)

- [x] **T-13** · `ui/app.py` — two-mode JD input (text/PDF), resume upload, 4 results tabs

---

## Phase 7 — React + Clerk Frontend ✅

- [x] **T-16** · Scaffold Vite + React in `frontend/`
- [x] **T-17** · Install deps (`@clerk/clerk-react`, `react-router-dom`, `axios`)
- [x] **T-18** · `main.jsx` — ClerkProvider + BrowserRouter setup
- [x] **T-19** · `App.jsx` — Routes + ProtectedRoute component
- [x] **T-20** · Landing page — Hero, feature cards, how-it-works, CTA
- [x] **T-21** · Auth pages — Clerk SignIn/SignUp components
- [x] **T-22** · Dashboard shell + Navbar
- [x] **T-23** · Dashboard JD input + Resume upload panels
- [x] **T-24** · Dashboard results tabs (Ranked / Bias / Critique / Outreach) — dealbreaker badges, project chips
- [x] **T-25** · `api/pipeline.js` — axios wrapper with Clerk token injection
- [x] **T-26** · FastAPI CORS — `http://localhost:5173` allowed
- [x] **T-27** · FastAPI Clerk JWT middleware — Bearer token verified on protected endpoints

---

## Phase 9 — Wow Factor Features ⬜

- [ ] **T-30** · `agents/team_gap_analyzer.py` — takes existing team CSV/JSON, identifies skill gaps, passes gap analysis to Ranker so candidates are scored on *unique value added to team* not just JD keyword match
  - New state field: `team_gap_analysis: dict`
  - Ranker prompt augmented: "team already has 4 Python devs — Go/Rust candidates get diversity bonus"
  - UI: optional team CSV upload on Dashboard
  - Pipeline: runs parallel with Bias Checker in fan-out

- [ ] **T-31** · `agents/outreach_drafter.py` (second pass) — Rejection Letters
  - Top N candidates → personalized invite emails (existing)
  - Bottom candidates → kind, specific rejection: exact missing skills + resources to close gaps
  - New state field: `rejection_emails: List[dict]`
  - Dashboard: 5th tab — 📩 Rejection Letters

- [ ] **T-32** · Real-time SSE Pipeline UI
  - FastAPI: `GET /run/stream` endpoint using `StreamingResponse` + LangGraph `.stream()`
  - Each agent emits SSE event when it starts/finishes
  - React: `EventSource` API, pipeline diagram lights up node by node
  - Upload flow: POST files → get `job_id` → stream events via SSE

---

## Phase 8 — Polish & Docs ⬜

- [ ] **T-28** · Sample resumes — 3 synthetic PDFs in `data/sample_resumes/`
- [ ] **T-29** · `README.md` — architecture overview, quickstart, env vars, screenshots

---

## Phase 10 — Deployment ⬜

- [ ] **T-33** · Backend deployment — FastAPI on Render (free tier)
  - `Dockerfile` or `render.yaml` in project root
  - Environment variables: `GROQ_API_KEY`, `GOOGLE_API_KEY`, `CLERK_SECRET_KEY`, `FRONTEND_API_URL`
  - Health check: `GET /health` → Render auto-restart on failure

- [ ] **T-34** · Frontend deployment — React on Vercel
  - `VITE_CLERK_PUBLISHABLE_KEY` + `VITE_API_BASE_URL` env vars in Vercel dashboard
  - `vercel.json` SPA fallback for React Router

- [ ] **T-35** · Clerk production instance
  - Switch from dev keys to production keys in both Vercel and Render
  - Add deployed frontend domain to Clerk allowed origins

- [ ] **T-36** · CORS hardening for production
  - `main.py` — replace `localhost` origins with deployed Vercel URL
  - Keep `localhost` only in `.env.example` dev config

- [ ] **T-37** · Production smoke test
  - End-to-end run on live URLs with real resumes
  - Confirm Clerk auth, file uploads, full pipeline, and results render correctly


## Current Status

| Task | Description | Status |
|------|-------------|--------|
| T-00 | Scaffold | ✅ Done |
| T-01 | requirements.txt | ✅ Done |
| T-02 | .env / .env.example | ✅ Done |
| T-03 | graph/state.py | ✅ Done |
| T-04 | agents/jd_parser.py | ✅ Done |
| T-05 | agents/resume_screener.py | ✅ Done |
| T-06 | agents/ranker.py | ✅ Done |
| T-07 | agents/bias_checker.py | ✅ Done |
| T-08 | agents/outreach_drafter.py | ✅ Done |
| T-09 | graph/pipeline.py | ✅ Done |
| T-10 | Smoke test | ✅ Done |
| T-B1 | utils/rate_limiter.py | ✅ Done |
| T-B2 | Experience parsing fix | ✅ Done |
| T-B3 | agents/critique.py | ✅ Done |
| T-B4 | Pipeline critique loop | ✅ Done |
| T-B5 | State critique fields | ✅ Done |
| T-11 | utils/helpers.py | ✅ Done |
| T-12 | main.py (FastAPI + Clerk JWT) | ✅ Done |
| T-13 | ui/app.py (Streamlit) | ✅ Done |
| T-16 | Frontend scaffold (Vite + React) | ✅ Done |
| T-17 | npm deps | ✅ Done |
| T-18 | main.jsx (ClerkProvider) | ✅ Done |
| T-19 | App.jsx + routes + ProtectedRoute | ✅ Done |
| T-20 | Landing page | ✅ Done |
| T-21 | Auth pages (Clerk) | ✅ Done |
| T-22 | Dashboard shell + Navbar | ✅ Done |
| T-23 | JD input + Resume upload | ✅ Done |
| T-24 | Results tabs (Ranked/Bias/Critique/Outreach) | ✅ Done |
| T-25 | api/pipeline.js (Clerk token injection) | ✅ Done |
| T-26 | FastAPI CORS update | ✅ Done |
| T-27 | FastAPI JWT middleware | ✅ Done |
| T-28 | Sample resumes | ⬜ Phase 8 |
| T-29 | README.md | ⬜ Phase 8 |
| T-30 | Team Gap Analyzer agent | ⬜ Phase 9 |
| T-31 | Rejection Letters (outreach 2nd pass) | ⬜ Phase 9 |
| T-32 | Real-time SSE Pipeline UI | ⬜ Phase 9 |
| T-33 | Backend deployment (Render) | ⬜ Phase 10 |
| T-34 | Frontend deployment (Vercel) | ⬜ Phase 10 |
| T-35 | Clerk production instance | ⬜ Phase 10 |
| T-36 | CORS update for production | ⬜ Phase 10 |
| T-37 | Smoke test production | ⬜ Phase 10 |
