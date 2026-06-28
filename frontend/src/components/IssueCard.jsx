import { useState } from 'react'

function pct(x) {
  return typeof x === 'number' ? `${(x * 100).toFixed(1)}%` : '-'
}

function fmtDate(s) {
  if (!s) return ''
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString()
}

// A saved issue in the Workspace. Click the header to expand the body/tokens;
// "Send to code-fix" hands it off and "Delete" removes it.
export default function IssueCard({ issue, onSend, onDelete }) {
  const [open, setOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)

  async function handleDelete(e) {
    e.stopPropagation()
    if (!onDelete) return
    setDeleting(true)
    try {
      await onDelete(issue.id)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className={`saved-card${open ? ' open' : ''}`}>
      <button
        type="button"
        className="saved-head"
        onClick={() => setOpen((o) => !o)}
      >
        <div className="saved-head-main">
          <span className="saved-title">{issue.title || '(untitled)'}</span>
          <span className="saved-sub">
            {issue.label && <span className="chip-sm">{issue.label}</span>}
            {issue.confidence != null && (
              <span className="muted">conf {pct(issue.confidence)}</span>
            )}
            {issue.severity != null && (
              <span className={`sev-tag sev-${issue.severity}`}>
                {issue.severity}
              </span>
            )}
          </span>
        </div>
        <span className="saved-date">{fmtDate(issue.created_at)}</span>
      </button>

      {open && (
        <div className="saved-body">
          {issue.body && <p className="saved-text">{issue.body}</p>}

          {Array.isArray(issue.top_tokens) && issue.top_tokens.length > 0 && (
            <div className="chips">
              {issue.top_tokens.map((t, i) => (
                <span className="chip" key={`${t}-${i}`}>
                  {typeof t === 'string' ? t : JSON.stringify(t)}
                </span>
              ))}
            </div>
          )}

          <div className="saved-actions">
            {onSend && (
              <button
                type="button"
                className="btn-secondary"
                onClick={(e) => {
                  e.stopPropagation()
                  onSend(issue)
                }}
              >
                Send to code-fix →
              </button>
            )}
            {onDelete && (
              <button
                type="button"
                className="btn-danger"
                onClick={handleDelete}
                disabled={deleting}
              >
                {deleting ? 'Deleting…' : 'Delete'}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
