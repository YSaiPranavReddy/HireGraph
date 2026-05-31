import './ResultPanels.css'

const RISK_MAP = {
  low:    { color: 'badge-green',  icon: '🟢', label: 'Low Risk'    },
  medium: { color: 'badge-yellow', icon: '🟡', label: 'Medium Risk' },
  high:   { color: 'badge-red',    icon: '🔴', label: 'High Risk'   },
}

export default function BiasPanel({ data }) {
  const report = data?.bias_report || {}
  const risk   = (report.overall_risk || 'low').toLowerCase()
  const meta   = RISK_MAP[risk] || RISK_MAP.low
  const signals = report.signals || []
  const recs    = report.recommendations || []

  return (
    <div className="panel">
      <div className="panel-header">
        <h3 className="panel-title">⚖️ Bias Report</h3>
        <span className={`badge ${meta.color}`}>{meta.icon} {meta.label}</span>
      </div>

      {report.summary && (
        <p className="panel-summary">{report.summary}</p>
      )}

      {signals.length > 0 && (
        <div className="panel-section">
          <h4 className="section-heading">Signals Found ({signals.length})</h4>
          <div className="signal-list">
            {signals.map((s, i) => {
              const sev = (s.severity || 'low').toLowerCase()
              const badge = sev === 'high' ? 'badge-red' : sev === 'medium' ? 'badge-yellow' : 'badge-blue'
              return (
                <div key={i} className="signal-card">
                  <div className="signal-header">
                    <span className={`badge ${badge}`}>{sev.toUpperCase()}</span>
                    <span className="signal-type">{s.type?.replace(/_/g, ' ')}</span>
                  </div>
                  {s.text && <p className="signal-quote">"{s.text}"</p>}
                  {s.suggestion && <p className="signal-suggestion">→ {s.suggestion}</p>}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {recs.length > 0 && (
        <div className="panel-section">
          <h4 className="section-heading">Recommendations</h4>
          <ul className="rec-list">
            {recs.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      )}
    </div>
  )
}
