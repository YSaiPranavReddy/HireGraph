import { useState } from 'react'
import './ResultPanels.css'

const VERDICT_META = {
  justified: { label: 'Justified',  icon: '✅', badge: 'badge-green'  },
  too_high:  { label: 'Too High',   icon: '⬇️',  badge: 'badge-red'    },
  too_low:   { label: 'Too Low',    icon: '⬆️',  badge: 'badge-yellow' },
}

export default function CritiquePanel({ data }) {
  const critique       = data?.critique_result || {}
  const flags          = critique.flags || []
  const perCandidate   = critique.per_candidate_feedback || {}
  const approved       = critique.approved !== false
  const retries        = data?.critique_retry_count || 0
  const hasCandidates  = Object.keys(perCandidate).length > 0

  const high   = flags.filter(f => f.severity === 'high')
  const medium = flags.filter(f => f.severity === 'medium')
  const low    = flags.filter(f => f.severity === 'low')

  return (
    <div className="panel">
      <div className="panel-header">
        <h3 className="panel-title">🧠 Critique Agent</h3>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span className={`badge ${approved ? 'badge-green' : 'badge-red'}`}>
            {approved ? '✓ Approved' : '✗ Flagged'}
          </span>
          <span className="badge badge-purple">
            {retries} retry{retries !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      <p className="panel-summary">
        Gemini independently audited the Groq ranking for scoring consistency and logical contradictions.
        {approved
          ? ' The ranking was approved as accurate.'
          : ' Issues were found and feedback was sent to the Ranker.'}
      </p>

      {/* ── Per-candidate verdicts (new format) ── */}
      {hasCandidates && (
        <div className="panel-section">
          <h4 className="section-heading">Per-Candidate Verdicts</h4>
          <div className="verdict-list">
            {Object.entries(perCandidate).map(([name, vdata]) => (
              <VerdictCard key={name} name={name} vdata={vdata} />
            ))}
          </div>
        </div>
      )}

      {/* ── Legacy flags (still shown if present) ── */}
      {!hasCandidates && flags.length === 0 && (
        <div className="critique-clean">
          <span style={{ fontSize: 40 }}>✓</span>
          <p>No flags raised — ranking is consistent with evidence.</p>
        </div>
      )}

      {[
        { list: high,   label: 'High Severity',   badge: 'badge-red'    },
        { list: medium, label: 'Medium Severity',  badge: 'badge-yellow' },
        { list: low,    label: 'Low Severity',     badge: 'badge-blue'   },
      ].filter(g => g.list.length > 0).map(({ list, label, badge }) => (
        <div key={label} className="panel-section">
          <h4 className="section-heading">
            <span className={`badge ${badge}`}>{label}</span>
          </h4>
          {list.map((f, i) => (
            <div key={i} className="flag-card">
              <div className="flag-candidate">{f.candidate}</div>
              <p className="flag-issue">{f.issue}</p>
              {f.expected_score_range && (
                <p className="flag-suggestion">→ Expected: {f.expected_score_range}</p>
              )}
            </div>
          ))}
        </div>
      ))}

      {/* Feedback sent to ranker */}
      {critique.feedback && !approved && (
        <div className="panel-section">
          <h4 className="section-heading">Feedback sent to Ranker</h4>
          <div className="feedback-box">{critique.feedback}</div>
        </div>
      )}
    </div>
  )
}

function VerdictCard({ name, vdata }) {
  const [expanded, setExpanded] = useState(false)
  const verdict = vdata.verdict || 'justified'
  const meta    = VERDICT_META[verdict] || VERDICT_META.justified
  const curr    = vdata.current_score
  const sugg    = vdata.suggested_score
  const changed = verdict !== 'justified' && sugg !== curr

  return (
    <div className={`verdict-card verdict-${verdict}`}>
      <div className="verdict-row">
        <span className="verdict-name">{name}</span>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
          {changed && (
            <span className="verdict-score-change">
              {curr} → {sugg}
            </span>
          )}
          {!changed && curr != null && (
            <span className="badge-dim">{curr}</span>
          )}
          <span className={`badge ${meta.badge}`} style={{ fontSize: 11 }}>
            {meta.icon} {meta.label}
          </span>
        </div>
      </div>
      {vdata.feedback && vdata.feedback !== 'null' && (
        <>
          <p
            className={`verdict-feedback ${expanded ? 'expanded' : 'collapsed'}`}
            onClick={() => setExpanded(s => !s)}
          >
            {vdata.feedback}
          </p>
          <button className="btn-ghost" onClick={() => setExpanded(s => !s)}>
            {expanded ? 'Show less ▲' : 'Show more ▼'}
          </button>
        </>
      )}
    </div>
  )
}
