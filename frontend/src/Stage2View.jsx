import { useState } from 'react'

const EST_COST = '~$0.07'

const EXAMPLES = [
  {
    name: 'Bug (passes gate)',
    title: 'TypeError: RST.__init__() got an unexpected keyword argument header_rows',
    body:
      'Writing a table in RST format with header_rows raises TypeError: ' +
      'RST.__init__() got an unexpected keyword argument "header_rows". The RST ' +
      'writer should accept and forward header_rows to its FixedWidth parent. ' +
      'This worked before and is a regression.',
  },
  {
    name: 'Feature (filtered)',
    title: 'Add CSV export to the reports page',
    body:
      'It would be great if we could export the generated reports to CSV so we ' +
      'can open them in Excel. A simple "Export to CSV" button would do.',
  },
]

function Diff({ patch }) {
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

export default function Stage2View({ issue }) {
  const { title, body, setTitle, setBody } = issue
  const [live, setLive] = useState(false)
  const [status, setStatus] = useState('idle')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  function loadExample(ex) {
    setTitle(ex.title)
    setBody(ex.body)
    setResult(null)
    setError('')
  }

  async function run() {
    setError('')
    setResult(null)
    setStatus('running')
    try {
      const res = await fetch('/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, body, live }),
      })
      if (!res.ok) {
        let detail = ''
        try {
          detail = (await res.json()).detail || ''
        } catch {
          /* ignore */
        }
        setError(`Run failed (${res.status}). ${detail}`.trim())
        setStatus('idle')
        return
      }
      setResult(await res.json())
      setStatus('done')
    } catch {
      setError('Could not reach the API.')
      setStatus('idle')
    }
  }

  const running = status === 'running'
  const canRun = (title.trim() || body.trim()) && !running

  const r = result
  const gatePassed = r?.gate?.passed
  const decision = r?.decision || {}
  const ranking = decision.ranking || []
  const winner = decision.selected_agent
  const candidates = r
    ? [...(r.candidates || [])].sort((a, b) => {
        const ia = ranking.indexOf(a.agent)
        const ib = ranking.indexOf(b.agent)
        return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
      })
    : []

  return (
    <>
      <p className="subtitle">
        Stage 1 triages the issue and gates Stage 2. Only a bug is sent to the
        agents.
      </p>

      <div className="examples">
        <span className="examples-label">Examples:</span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex.name}
            type="button"
            className="example-btn"
            onClick={() => loadExample(ex)}
          >
            {ex.name}
          </button>
        ))}
      </div>

      <label htmlFor="s2title">Issue title</label>
      <input
        id="s2title"
        type="text"
        placeholder="Short summary of the issue"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <label htmlFor="s2body">Issue body</label>
      <textarea
        id="s2body"
        rows={5}
        placeholder="Describe the issue"
        value={body}
        onChange={(e) => setBody(e.target.value)}
      />

      <div className="run-bar">
        <label className={`switch${live ? ' on' : ''}`}>
          <input
            type="checkbox"
            checked={live}
            onChange={(e) => setLive(e.target.checked)}
          />
          <span className="track">
            <span className="knob" />
          </span>
          <span className="switch-text">
            {live ? (
              <>
                Live run, spends <strong>{EST_COST}</strong>
              </>
            ) : (
              <>Dry run, no API calls</>
            )}
          </span>
        </label>
        <button type="button" className="submit" onClick={run} disabled={!canRun}>
          {running ? (live ? 'Dispatching' : 'Running') : 'Run pipeline'}
        </button>
      </div>

      {running && live && (
        <div className="s2-status pulse">
          Running. Dispatching to the agents and the judge, about a minute.
        </div>
      )}

      {error && <div className="error">{error}</div>}

      {r && (
        <section className="result">
          <div className="stage-label">Stage 1 triage</div>
          <div className="result-row">
            <div className="metric">
              <span className="metric-label">Label</span>
              <span className="metric-value">{r.triage.label}</span>
              <span className="metric-conf">confidence {pct(r.triage.confidence)}</span>
            </div>
            <div className="metric">
              <span className="metric-label">Top tokens</span>
              <div className="chips" style={{ marginTop: 4 }}>
                {(r.triage.top_tokens || []).slice(0, 5).map((t, i) => (
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
              <div className="gate-title">
                {gatePassed ? 'Gate open' : 'Gate closed'}
              </div>
              <div className="gate-reason">{r.gate.reason}</div>
            </div>
          </div>

          {!gatePassed && (
            <div className="cost-note">
              Harness skipped. <strong>$0.00</strong> spent. Only bugs reach the
              best-of-N stage.
            </div>
          )}

          {gatePassed && !r.ran_live && (
            <div className="cost-note">
              Gate passed. Dry run, projected{' '}
              <strong>${r.cost.projection_usd.toFixed(4)}</strong> for {r.cost.calls}{' '}
              calls. Turn on Live and run again to dispatch.
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
                <span className="spent-pill">
                  spent ${r.cost.spent_usd.toFixed(4)}
                </span>
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
                Chairman decision ({r.config.chairman_model})
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

              {r.resolve_rate_note && (
                <div className="honesty">{r.resolve_rate_note}</div>
              )}
            </>
          )}
        </section>
      )}
    </>
  )
}
