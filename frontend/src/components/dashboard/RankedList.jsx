import './ResultPanels.css'

export default function RankedList({ data }) {
  const ranked = data?.ranked_candidates || []
  if (!ranked.length) return <div className="panel-empty">No ranked candidates.</div>

  return (
    <div className="panel">
      <div className="panel-header">
        <h3 className="panel-title">🏆 Ranked Candidates</h3>
        <span className="badge badge-purple">{ranked.length} candidates</span>
      </div>
      <div className="candidate-list">
        {ranked.map((c, i) => (
          <div key={i} className={`candidate-card card rank-${i + 1}`}>
            <div className="candidate-header">
              <div className="rank-badge">#{i + 1}</div>
              <div className="candidate-info">
                <span className="candidate-name">{c.name}</span>
                <span className="candidate-exp">{c.experience_years?.toFixed(1)}y exp</span>
              </div>
              <div className="score-circle" style={{ '--score': c.score }}>
                <span className="score-val">{c.score}</span>
                <span className="score-max">/100</span>
              </div>
            </div>

            {/* Dealbreaker flags */}
            {c.dealbreaker_flags?.length > 0 && (
              <div className="dealbreaker-row">
                {c.dealbreaker_flags.map((f, j) => (
                  <span key={j} className="badge badge-red">⚠️ {f}</span>
                ))}
              </div>
            )}

            {/* Score breakdown */}
            <div className="score-breakdown">
              {[
                { label: 'Skills',     val: c.skills_match,    max: 40 },
                { label: 'Experience', val: c.experience_fit,  max: 30 },
                { label: 'Education',  val: c.education_fit,   max: 15 },
                { label: 'Role Fit',   val: c.role_relevance,  max: 15 },
              ].map(({ label, val, max }) => (
                <div key={label} className="score-row">
                  <span className="score-label">{label}</span>
                  <div className="score-bar-track">
                    <div className="score-bar-fill" style={{ width: `${Math.min((val / max) * 100, 100)}%` }} />
                  </div>
                  <span className="score-frac">{val ?? '—'}/{max}</span>
                </div>
              ))}
            </div>

            {/* Skills */}
            {c.matched_skills?.length > 0 && (
              <div className="skills-row">
                {c.matched_skills.map((s, j) => (
                  <span key={j} className="skill-chip skill-match">{s}</span>
                ))}
                {c.missing_skills?.map((s, j) => (
                  <span key={j} className="skill-chip skill-miss">{s}</span>
                ))}
              </div>
            )}

            {/* Key Projects */}
            {c.key_projects?.length > 0 && (
              <div className="key-projects-row">
                <span className="key-projects-label">🔨 Projects:</span>
                {c.key_projects.map((p, j) => (
                  <span key={j} className="skill-chip skill-project">{p}</span>
                ))}
              </div>
            )}

            {/* Reasoning */}
            {c.reasoning && (
              <p className="candidate-reasoning">💬 {c.reasoning}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
