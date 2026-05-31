import { useState } from 'react'
import './ResultPanels.css'

function RejectionCard({ letter }) {
  const [copied, setCopied] = useState(false)
  const [expanded, setExpanded] = useState(false)

  function copy() {
    navigator.clipboard.writeText(letter.body || '')
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="email-card card rejection-card">
      <div className="email-header">
        <div className="email-meta">
          <span className="email-to">
            To: <strong>{letter.candidate_name}</strong>
          </span>
          {letter.subject && (
            <span className="email-subject">📌 {letter.subject}</span>
          )}
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {typeof letter.score === 'number' && (
            <span className="badge badge-dim">Score: {letter.score}/100</span>
          )}
          <button
            className={`btn btn-sm ${copied ? 'btn-outline' : 'btn-secondary'}`}
            onClick={copy}
          >
            {copied ? '✓ Copied' : 'Copy'}
          </button>
        </div>
      </div>

      {/* Missing skills chips */}
      {letter.missing_skills?.length > 0 && (
        <div className="missing-chips" style={{ margin: '10px 0 6px' }}>
          <span className="chip-label" style={{ fontSize: '11px', opacity: 0.6, marginRight: '6px' }}>
            Missing:
          </span>
          {letter.missing_skills.map((s, i) => (
            <span key={i} className="chip chip-missing">{s}</span>
          ))}
        </div>
      )}

      <div className="divider" style={{ margin: '10px 0' }} />

      {/* Body — collapsible after 4 lines */}
      <div
        className={`email-body rejection-body ${expanded ? 'expanded' : 'collapsed'}`}
        style={{ cursor: 'pointer' }}
        onClick={() => setExpanded(e => !e)}
      >
        {letter.body}
      </div>
      <button
        className="btn btn-ghost btn-sm"
        style={{ marginTop: '6px', fontSize: '12px' }}
        onClick={() => setExpanded(e => !e)}
      >
        {expanded ? '▲ Show less' : '▼ Read full letter'}
      </button>
    </div>
  )
}

export default function RejectionPanel({ data }) {
  const letters = data?.rejection_emails || []

  if (!letters.length) {
    return (
      <div className="panel-empty">
        No rejection letters generated.
        {data?.ranked_candidates?.length <= 3
          ? ' All candidates received invite emails.'
          : ''}
      </div>
    )
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <h3 className="panel-title">📩 Rejection Letters</h3>
        <span className="badge badge-orange">{letters.length} letters</span>
      </div>
      <p className="panel-summary">
        Kind, specific rejections — not templates. Each letter names the candidate's
        actual strengths, the exact skill gaps for this role, and concrete steps to
        close them. No "we'll keep your resume on file."
      </p>
      <div className="email-list">
        {letters.map((l, i) => (
          <RejectionCard key={i} letter={l} />
        ))}
      </div>
    </div>
  )
}
