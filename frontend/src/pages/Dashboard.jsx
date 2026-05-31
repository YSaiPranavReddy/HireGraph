import { useState, useRef } from 'react'
import { useUser, useAuth } from '@clerk/clerk-react'
import Navbar from '../components/Navbar'
import { parseJdPdf, streamPipeline } from '../api/pipeline'
import RankedList      from '../components/dashboard/RankedList'
import BiasPanel       from '../components/dashboard/BiasPanel'
import CritiquePanel   from '../components/dashboard/CritiquePanel'
import OutreachPanel   from '../components/dashboard/OutreachPanel'
import RejectionPanel  from '../components/dashboard/RejectionPanel'
import PipelineDiagram from '../components/dashboard/PipelineDiagram'
import './Dashboard.css'

const TABS = [
  { id: 'ranked',   label: '🏆 Ranked' },
  { id: 'bias',     label: '⚖️ Bias Report' },
  { id: 'critique', label: '🧠 Critique' },
  { id: 'outreach',   label: '✉️ Outreach' },
  { id: 'rejections', label: '📩 Rejections' },
]

export default function Dashboard() {
  const { user } = useUser()
  const { getToken } = useAuth()

  // ── Input state ─────────────────────────────────
  const [jdMode, setJdMode]         = useState('text')   // 'text' | 'pdf'
  const [jdText, setJdText]         = useState('')
  const [jdFile, setJdFile]         = useState(null)
  const [jdExtracted, setJdExtracted] = useState('')
  const [jdExtracting, setJdExtracting] = useState(false)
  const [resumeFiles, setResumeFiles] = useState([])
  const [teamData, setTeamData]       = useState('')
  const [showTeamInput, setShowTeamInput] = useState(false)

  // ── Pipeline state ──────────────────────────────────
  const [running, setRunning]         = useState(false)
  const [result, setResult]           = useState(null)
  const [error, setError]             = useState(null)
  const [activeTab, setActiveTab]     = useState('ranked')
  const [streamEvents, setStreamEvents] = useState([])   // live SSE events

  const resumeInputRef = useRef()

  // ── CSV export ──────────────────────────────────
  function exportCSV() {
    const candidates = result?.ranked_candidates || []
    const profiles   = result?.candidate_profiles || []

    // Build email lookup keyed by file_name
    const emailByFile = {}
    profiles.forEach(p => { emailByFile[p.file_name] = p.email || '' })

    // Header + rows (already sorted by score desc from the backend)
    const rows = [['Rank', 'Name', 'Email', 'Score', 'Matched Skills', 'Dealbreaker Flags']]
    candidates.forEach(c => {
      rows.push([
        c.rank,
        c.name,
        emailByFile[c.file_name] || '',
        c.score,
        (c.matched_skills || []).join('; '),
        (c.dealbreaker_flags || []).join('; '),
      ])
    })

    const csv = rows
      .map(row => row.map(v => `"${String(v ?? '').replace(/"/g, '""')}"`).join(','))
      .join('\n')

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = 'hiregraph_results.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  // ── JD PDF extraction ───────────────────────────
  async function handleJdPdf(file) {
    setJdFile(file)
    setJdExtracting(true)
    setJdExtracted('')
    try {
      const token = await getToken()
      const text = await parseJdPdf(file, token)
      if (!text) {
        setJdExtracted('Could not extract text — this PDF may be scanned or image-based. Paste the JD text manually above.')
      } else {
        setJdExtracted(text)
      }
    } catch (e) {
      console.error('JD extract error:', e)
      setJdExtracted('Failed to extract — paste text manually.')
    } finally {
      setJdExtracting(false)
    }
  }

  // ── Run pipeline (streaming) ───────────────────────────
  async function handleRun() {
    const jd = jdMode === 'text' ? jdText : jdExtracted
    if (!jd || !jd.trim())   return setError('Please provide a Job Description.')
    if (!resumeFiles.length) return setError('Please upload at least one resume.')

    setRunning(true)
    setError(null)
    setResult(null)
    setStreamEvents([])

    try {
      const token = await getToken()
      await streamPipeline(jd, resumeFiles, token, teamData, (type, data) => {
        if (type === 'agent_update') {
          setStreamEvents(prev => {
            // De-duplicate by node (critique/ranker may fire multiple times)
            const filtered = prev.filter(e => e.node !== data.node)
            return [...filtered, data]
          })
        }
        if (type === 'pipeline_complete') {
          setResult(data)
          setActiveTab('ranked')
          setRunning(false)
        }
        if (type === 'error') {
          setError(data.message || 'Pipeline error.')
          setRunning(false)
        }
      })
    } catch (e) {
      setError(e.message || 'Pipeline failed.')
      setRunning(false)
    }
  }

  return (
    <div className="dashboard">
      <Navbar />

      <div className="dashboard-body">

        {/* ── Welcome bar ─────────────────────── */}
        <div className="welcome-bar">
          <div>
            <h1 className="welcome-title">
              Welcome back, <span className="gradient-text">{user?.firstName || 'HR'}</span> 👋
            </h1>
            <p className="welcome-sub">Upload a JD and resumes to run the pipeline</p>
          </div>
          <div className="welcome-status">
            <span className="status-dot" />
            <span className="status-text">Pipeline ready</span>
          </div>
        </div>

        {/* ── Main layout ─────────────────────── */}
        <div className="dash-layout">

          {/* ── Left: Inputs ─────────────────── */}
          <div className="inputs-panel card">

            {/* JD input mode toggle */}
            <div className="input-section">
              <label className="form-label">Job Description</label>
              <div className="tabs" style={{ marginBottom: 16 }}>
                <button
                  className={`tab-btn ${jdMode === 'text' ? 'active' : ''}`}
                  onClick={() => setJdMode('text')}
                >📝 Paste Text</button>
                <button
                  className={`tab-btn ${jdMode === 'pdf' ? 'active' : ''}`}
                  onClick={() => setJdMode('pdf')}
                >📄 Upload PDF</button>
              </div>

              {jdMode === 'text' ? (
                <textarea
                  rows={10}
                  placeholder="Paste the full job description here..."
                  value={jdText}
                  onChange={e => setJdText(e.target.value)}
                />
              ) : (
                <div className="pdf-drop-zone"
                  onClick={() => document.getElementById('jd-pdf-input').click()}
                  onDragOver={e => e.preventDefault()}
                  onDrop={e => { e.preventDefault(); handleJdPdf(e.dataTransfer.files[0]) }}
                >
                  <input
                    id="jd-pdf-input" type="file" accept=".pdf"
                    style={{ display: 'none' }}
                    onChange={e => handleJdPdf(e.target.files[0])}
                  />
                  {jdFile ? (
                    <div className="pdf-loaded">
                      <span className="pdf-icon">📄</span>
                      <span className="pdf-name">{jdFile.name}</span>
                      {jdExtracting && <span className="extracting">Extracting...</span>}
                    </div>
                  ) : (
                    <div className="pdf-placeholder">
                      <span className="pdf-icon-lg">📂</span>
                      <span>Click or drag a JD PDF here</span>
                    </div>
                  )}
                </div>
              )}

              {jdMode === 'pdf' && jdExtracted && (
                <div className="jd-preview">
                  <label className="form-label" style={{ marginTop: 12 }}>Extracted Text (editable)</label>
                  <textarea
                    rows={8}
                    value={jdExtracted}
                    onChange={e => setJdExtracted(e.target.value)}
                  />
                </div>
              )}
            </div>

            <div className="divider" />

            {/* Resume upload */}
            <div className="input-section">
              <label className="form-label">Candidate Resumes</label>
              <div
                className="pdf-drop-zone resume-drop"
                onClick={() => resumeInputRef.current.click()}
                onDragOver={e => e.preventDefault()}
                onDrop={e => {
                  e.preventDefault()
                  const files = Array.from(e.dataTransfer.files).filter(f => f.name.endsWith('.pdf'))
                  setResumeFiles(prev => [...prev, ...files])
                }}
              >
                <input
                  ref={resumeInputRef} type="file" accept=".pdf" multiple
                  style={{ display: 'none' }}
                  onChange={e => setResumeFiles(prev => [...prev, ...Array.from(e.target.files)])}
                />
                <span className="pdf-icon-lg">📋</span>
                <span>Click or drag resume PDFs here</span>
                <span className="drop-hint">Multiple files supported</span>
              </div>

              {resumeFiles.length > 0 && (
                <div className="resume-list">
                  {resumeFiles.map((f, i) => (
                    <div key={i} className="resume-chip">
                      <span>📄 {f.name}</span>
                      <button onClick={() => setResumeFiles(prev => prev.filter((_, j) => j !== i))}>✕</button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="divider" />

            {/* Optional team data — collapsible */}
            <div className="input-section">
              <button
                className="btn btn-ghost"
                style={{ fontSize: '13px', padding: '4px 0', display: 'flex', alignItems: 'center', gap: '6px' }}
                onClick={() => setShowTeamInput(s => !s)}
              >
                <span>{showTeamInput ? '▼' : '▶'}</span>
                <span>👥 Add existing team data <span style={{ opacity: 0.5, fontWeight: 400 }}>(optional — enables team gap scoring)</span></span>
              </button>
              {showTeamInput && (
                <div style={{ marginTop: '10px' }}>
                  <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '8px', lineHeight: 1.6 }}>
                    Paste your team roster as CSV or JSON. Candidates will be scored on <strong>unique value they add</strong> vs. skills your team already has.
                  </p>
                  <textarea
                    rows={5}
                    placeholder={'name,role,skills\nAlice,ML Engineer,"Python, PyTorch, LangChain"\nBob,Backend Dev,"Python, FastAPI, PostgreSQL"'}
                    value={teamData}
                    onChange={e => setTeamData(e.target.value)}
                    style={{ fontFamily: 'monospace', fontSize: '12px' }}
                  />
                  {teamData.trim() && (
                    <span style={{ fontSize: '11px', color: 'var(--success)', marginTop: '4px', display: 'block' }}>
                      ✓ Team data will be included in this run
                    </span>
                  )}
                </div>
              )}
            </div>

            {error && <div className="error-box">{error}</div>}

            <button
              className="btn btn-primary run-btn"
              onClick={handleRun}
              disabled={running}
            >
              {running
                ? <><span className="spinner-sm" /> Running pipeline...</>
                : '⚡ Run HireGraph'}
            </button>

            {running && (
              <div className="running-hint">
                This takes 1–3 minutes depending on Groq / Gemini API speed
              </div>
            )}
          </div>

          {/* ── Right: Results ────────────────── */}
          <div className="results-panel">
            {!result && !running && (
              <div className="results-empty card">
                <div className="empty-icon">⚡</div>
                <h3>Results appear here</h3>
                <p>Upload a JD and resumes, then click Run HireGraph</p>
              </div>
            )}

            {(running || streamEvents.length > 0) && (
              <div className="results-loading card">
                <p className="loading-text" style={{ marginBottom: '16px' }}>
                  {running ? 'Pipeline running — agents lighting up as they complete...' : '✅ Pipeline complete'}
                </p>
                <PipelineDiagram events={streamEvents} />
              </div>
            )}

            {result && (
              <div className="results-content">
                {/* Tabs */}
                <div className="tabs result-tabs">
                  {TABS.map(t => (
                    <button
                      key={t.id}
                      className={`tab-btn ${activeTab === t.id ? 'active' : ''}`}
                      onClick={() => setActiveTab(t.id)}
                    >{t.label}</button>
                  ))}
                </div>

                {/* Tab panels */}
                <div className="tab-content">
                  {activeTab === 'ranked'     && <RankedList    data={result} />}
                  {activeTab === 'bias'       && <BiasPanel     data={result} />}
                  {activeTab === 'critique'   && <CritiquePanel data={result} />}
                  {activeTab === 'outreach'   && <OutreachPanel  data={result} />}
                  {activeTab === 'rejections' && <RejectionPanel data={result} />}
                </div>

                {/* Export button */}
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '24px', paddingTop: '16px', borderTop: '1px solid var(--border)' }}>
                  <button
                    id="export-results-btn"
                    className="btn btn-outline"
                    onClick={exportCSV}
                    style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px' }}
                  >
                    <span>⬇️</span>
                    <span>Export Results (CSV)</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
