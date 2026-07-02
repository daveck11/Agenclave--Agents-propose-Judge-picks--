import { useState } from 'react'

function fmtDate(s) {
  if (!s) return ''
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString()
}

// A saved Stage-2 run in the Workspace. Defensive about field shape since the
// stored RunOut nests triage/gate/decision/cost which may be partial.
export default function RunCard({ run, onDelete }) {
  const [open, setOpen] = useState(false)

  // A persisted run (GET /runs) nests the payload under `result`; a fresh
  // POST /runs response is already flat. Unwrap either shape.
  const data = run.result || run
  const triage = data.triage || {}
  const gate = data.gate || {}
  const decision = data.decision || {}
  const cost = data.cost || {}
  const winner = decision.selected_agent
  const candidates = data.candidates || []
  const ranLive = run.ran_live ?? data.ran_live
  const title = run.title || data.title || '(untitled run)'

  return (
    <div className={`saved-card${open ? ' open' : ''}`}>
      <button
        type="button"
        className="saved-head"
        onClick={() => setOpen((o) => !o)}
      >
        <div className="saved-head-main">
          <span className="saved-title">{title}</span>
          <span className="saved-sub">
            {triage.label && <span className="chip-sm">{triage.label}</span>}
            <span className={`gate-tag ${gate.passed ? 'open' : 'closed'}`}>
              {gate.passed ? 'gate open' : 'gate closed'}
            </span>
            {ranLive ? (
              <span className="live-tag">live</span>
            ) : (
              <span className="muted">dry</span>
            )}
            {winner && <span className="muted">→ {winner}</span>}
          </span>
        </div>
        <span className="saved-date">{fmtDate(run.created_at)}</span>
      </button>

      {open && (
        <div className="saved-body">
          {gate.reason && <p className="saved-text mono-sm">{gate.reason}</p>}

          {ranLive && winner && (
            <div className="flow">
              <span className="flow-node">bug</span>
              <span className="flow-arrow">→</span>
              <span className="flow-node">{candidates.length} agents</span>
              <span className="flow-arrow">→</span>
              <span className="flow-node accent">chairman: {winner}</span>
            </div>
          )}

          {decision.rationale && (
            <div className="chairman-pick" style={{ marginTop: 14 }}>
              <div className="pick-head">
                Selected <code>{winner}</code>
              </div>
              <p className="pick-rationale">{decision.rationale}</p>
            </div>
          )}

          {typeof cost.spent_usd === 'number' && (
            <div className="cost-note" style={{ marginTop: 12 }}>
              Spent <strong>${cost.spent_usd.toFixed(4)}</strong>
              {typeof cost.calls === 'number' && <> · {cost.calls} calls</>}
            </div>
          )}

          {onDelete && (
            <div className="saved-actions">
              <button
                type="button"
                className="btn-danger"
                onClick={() => onDelete(run.id)}
              >
                Delete run
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
