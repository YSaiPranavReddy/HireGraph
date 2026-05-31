import { useState } from 'react'
import './ResultPanels.css'

function EmailCard({ email }) {
  const [copied, setCopied] = useState(false)

  function copy() {
    navigator.clipboard.writeText(email.body || '')
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="email-card card">
      <div className="email-header">
        <div className="email-meta">
          <span className="email-to">To: <strong>{email.to || email.candidate_name}</strong></span>
          {email.subject && <span className="email-subject">📌 {email.subject}</span>}
        </div>
        <button className={`btn btn-sm ${copied ? 'btn-outline' : 'btn-primary'}`} onClick={copy}>
          {copied ? '✓ Copied' : 'Copy'}
        </button>
      </div>
      <div className="divider" style={{ margin: '12px 0' }} />
      <p className="email-body">{email.body}</p>
    </div>
  )
}

export default function OutreachPanel({ data }) {
  const emails = data?.outreach_emails || []
  if (!emails.length) return <div className="panel-empty">No outreach emails generated.</div>

  return (
    <div className="panel">
      <div className="panel-header">
        <h3 className="panel-title">✉️ Outreach Emails</h3>
        <span className="badge badge-purple">{emails.length} emails</span>
      </div>
      <p className="panel-summary">
        Personalized emails for each top candidate — not templates, written specifically for each person's background.
      </p>
      <div className="email-list">
        {emails.map((e, i) => <EmailCard key={i} email={e} />)}
      </div>
    </div>
  )
}
