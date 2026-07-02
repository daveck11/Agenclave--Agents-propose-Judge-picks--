// Shared rendering of a /runs response: Stage-1 triage summary, the gate,
// cost notes, the parallel agent grid with diffs, and the chairman decision.
// Extracted from the original Stage2View so both Stage2View and CodeFixPage
// render runs identically.

export function Diff({ patch }) {
  if (!patch || !patch.trim()) {
    return <div className="diff-empty">No patch produced.</div>
  }
  const lines = patch.replace(/\n$/, '').split('\n')
  return (
    <pre className="diff">
      {lines.map((line, i) => {
        let cls = 'd-ctx'
        if (line.startsWith('+++') || line.startsWith('---')) cls = 'd-file'
        else if (line.startsWith('@@')) cls = 'd-hunk'
        else if (line.startsWith('diff ') || line.startsWith('index ')) cls = 'd-meta'
        else if (line.startsWith('+')) cls = 'd-add'
        else if (line.startsWith('-')) cls = 'd-del'
        return (
          <span className={`d-line ${cls}`} key={i}>
            {line || ' '}
          </span>
        )
      })}
    </pre>
  )
}

function pct(x) {
  return typeof x === 'number' ? `${(x * 100).toFixed(1)}%` : '-'
}

// Trust-scored routing panel: which models were picked for this task, and why.
// Reads the read-only `routing` block the API attaches when the gate passes.
function Routing({ routing }) {
  const considered = routing.considered || []
  const selected = new Set(routing.selected || [])
  const noHistory = considered.length > 0 && considered.every((c) => !c.total)

  return (
    <div className="routing">
      <div className="stage-label">Trust-scored routing (top-{routing.k})</div>
      <p className="routing-reason">{routing.reason}</p>
      <div className="routing-table">
        <div className="routing-row routing-head">
          <span>model</span>
          <span>reliability</span>
          <span>sample</span>
          <span></span>
        </div>
        {considered.map((c) => {
          const picked = selected.has(c.model)
          return (
            <div
              className={`routing-row${picked ? ' routed' : ''}`}
              key={c.model}
            >
              <span className="routing-model">{c.model}</span>
              <span className="routing-num">
                {pct(c.estimate)} <span className="routing-n">(n={c.total})</span>
              </span>
              <span className="routing-num">
                {typeof c.sample === 'number' ? c.sample.toFixed(3) : '-'}
              </span>
              <span>
                {picked && <span className="badge-win">routed</span>}
              </span>
            </div>
          )
        })}
      </div>
      {noHistory && (
        <div className="honesty">
          No verified history yet — routing is <strong>exploring</strong>. The web
          demo judges with the Chairman and does not verify patches, so it does not
          update trust. Reliability is learned only from in-loop verification runs.
        </div>
      )}
    </div>
  )
}

export default function RunResult({ result }) {
  const r = result
  if (!r) return null

  const gatePassed = r?.gate?.passed
  const decision = r?.decision || {}
  const ranking = decision.ranking || []
  const winner = decision.selected_agent
  const candidates = [...(r.candidates || [])].sort((a, b) => {
    const ia = ranking.indexOf(a.agent)
    const ib = ranking.indexOf(b.agent)
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
  })

  return (
    <section className="result">
      <div className="stage-label">Stage 1 triage</div>
      <div className="result-row">
        <div className="metric">
          <span className="metric-label">Label</span>
          <span className="metric-value">{r.triage?.label}</span>
          <span className="metric-conf">confidence {pct(r.triage?.confidence)}</span>
        </div>
        <div className="metric">
          <span className="metric-label">Top tokens</span>
          <div className="chips" style={{ marginTop: 4 }}>
            {(r.triage?.top_tokens || []).slice(0, 5).map((t, i) => (
              <span className="chip" key={`${t}-${i}`}>
                {t}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className={`gate ${gatePassed ? 'open' : 'closed'}`}>
        <span className="gate-icon">{gatePassed ? '→' : '⛔'}</span>
        <div>
          <div className="gate-title">{gatePassed ? 'Gate open' : 'Gate closed'}</div>
          <div className="gate-reason">{r.gate?.reason}</div>
        </div>
      </div>

      {!gatePassed && (
        <div className="cost-note">
          Harness skipped. <strong>$0.00</strong> spent. Only bugs reach the
          best-of-N stage.
        </div>
      )}

      {gatePassed && r.routing && (
        <Routing routing={r.routing} />
      )}

      {gatePassed && !r.ran_live && r.cost && (
        <div className="cost-note">
          Gate passed. Dry run, projected{' '}
          <strong>${(r.cost.projection_usd ?? 0).toFixed(4)}</strong> for{' '}
          {r.cost.calls} calls. Turn on Live and run again to dispatch.
        </div>
      )}

      {r.ran_live && (
        <>
          <div className="flow">
            <span className="flow-node">bug</span>
            <span className="flow-arrow">→</span>
            <span className="flow-node">{candidates.length} agents</span>
            <span className="flow-arrow">→</span>
            <span className="flow-node accent">chairman: {winner}</span>
            {r.cost && (
              <span className="spent-pill">
                spent ${(r.cost.spent_usd ?? 0).toFixed(4)}
              </span>
            )}
          </div>

          <div className="stage-label">
            Stage 2 candidates ({candidates.length} agents, parallel)
          </div>
          <div className="agent-grid">
            {candidates.map((c) => {
              const rank = ranking.indexOf(c.agent)
              const isWinner = c.agent === winner
              return (
                <div
                  key={c.agent}
                  className={`agent-card${isWinner ? ' winner' : ''}`}
                >
                  <div className="agent-head">
                    <span className="agent-model">{c.agent}</span>
                    <span className="agent-tags">
                      {rank >= 0 && <span className="rank-pill">#{rank + 1}</span>}
                      {isWinner && <span className="badge-win">selected</span>}
                      {!c.ok && <span className="badge-err">failed</span>}
                    </span>
                  </div>
                  {c.error && <div className="cand-error">{c.error}</div>}
                  <Diff patch={c.patch} />
                </div>
              )
            })}
          </div>

          <div className="stage-label">
            Chairman decision ({r.config?.chairman_model})
          </div>
          <div className="chairman-pick">
            <div className="pick-head">
              Selected <code>{winner}</code>
              {decision.synthesized && (
                <span className="synth-pill">synthesised</span>
              )}
            </div>
            {ranking.length > 0 && (
              <div className="rank-row">
                ranking:{' '}
                {ranking.map((m, i) => (
                  <span key={m}>
                    {i > 0 && <span className="rank-sep"> ▸ </span>}
                    <span className={m === winner ? 'rank-win' : ''}>{m}</span>
                  </span>
                ))}
              </div>
            )}
            <p className="pick-rationale">{decision.rationale}</p>
          </div>

          {r.resolve_rate_note && <div className="honesty">{r.resolve_rate_note}</div>}
        </>
      )}
    </section>
  )
}
