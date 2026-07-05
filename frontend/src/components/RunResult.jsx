// Shared rendering of a /runs response: triage summary, the gate, routing,
// cost notes, the parallel agent grid with diffs, and the chairman decision.

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

// Display a model id as just the model name in caps:
// blackbox:blackboxai/openai/gpt-5.4 -> GPT-5.4
function modelName(id) {
  if (!id) return ''
  return String(id).replace(/^blackbox:/, '').split('/').pop().toUpperCase()
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
              <span className="routing-model">{modelName(c.model)}</span>
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
          No verified history yet - routing is <strong>exploring</strong>. The web
          demo judges with the Chairman and does not verify patches, so it does not
          update trust. Reliability is learned only from in-loop verification runs.
        </div>
      )}
    </div>
  )
}

// Verification panel: for a practice-bug (fixture) run the backend actually
// applies each patch and runs the tests. This shows who passed - and, when the
// Chairman's read-the-patch pick differs from what the tests prove, calls it out.
function Verification({ verification, verifiedWinner, chairmanWinner, fixture }) {
  const vlist = verification || []
  const tierOf = (agent) => (vlist.find((v) => v.agent === agent) || {}).tier
  const verifiedPassed = tierOf(verifiedWinner) === 'trusted'
  const judgePassed = tierOf(chairmanWinner) === 'trusted'
  const differ = verifiedWinner && chairmanWinner && verifiedWinner !== chairmanWinner

  let callout = null
  if (differ && verifiedPassed && !judgePassed) {
    // Hero case: the judge's pick fails the tests; verification catches it.
    callout = (
      <>
        The Chairman picked <code>{modelName(chairmanWinner)}</code> by reading the
        patches - but its patch <strong>fails the tests</strong>. Verification selected{' '}
        <code>{modelName(verifiedWinner)}</code>, which passes. Verification, not the
        judge, decides.
      </>
    )
  } else if (differ && verifiedPassed && judgePassed) {
    // Tie-break case: the judge's pick also passed; trust breaks the tie.
    callout = (
      <>
        The Chairman's pick and the verified winner both pass the tests - so
        verification breaks the tie by track record and takes the more-trusted,{' '}
        <code>{modelName(verifiedWinner)}</code> (the Chairman, reading only,
        preferred <code>{modelName(chairmanWinner)}</code>).
      </>
    )
  }

  return (
    <div className="verify">
      <div className="stage-label">
        Verification - ran the tests{fixture?.module ? ` (${fixture.module})` : ''}
      </div>
      <p className="verify-note">
        Each candidate patch was applied in a sandbox and its tests were run.
      </p>
      {callout && <div className="verify-callout">{callout}</div>}
    </div>
  )
}

export default function RunResult({ result }) {
  const r = result
  if (!r) return null

  const gatePassed = r?.gate?.passed
  const decision = r?.decision || {}
  const ranking = decision.ranking || []
  const chairmanPick = decision.selected_agent
  // A fixture run has real verification, so VERIFICATION (not the judge) decides
  // the final winner; a plain run has no tests, so the Chairman's pick stands.
  const isFixture = Boolean(r.verification)
  const verifyOrder = (r.verification || []).map((v) => v.agent)
  const winner = isFixture ? r.verified_winner : chairmanPick
  const order = isFixture && verifyOrder.length ? verifyOrder : ranking
  const candidates = [...(r.candidates || [])].sort((a, b) => {
    const ia = order.indexOf(a.agent)
    const ib = order.indexOf(b.agent)
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
            <span className="flow-node accent">
              {isFixture ? 'verified' : 'chairman'}: {modelName(winner)}
            </span>
            {r.cost && (
              <span className="spent-pill">
                spent ${(r.cost.spent_usd ?? 0).toFixed(4)}
              </span>
            )}
          </div>

          {r.verification && (
            <Verification
              verification={r.verification}
              verifiedWinner={r.verified_winner}
              chairmanWinner={chairmanPick}
              fixture={r.fixture}
            />
          )}

          <div className="stage-label">
            Stage 2 candidates ({candidates.length} agents, parallel)
          </div>
          <div className="agent-grid">
            {candidates.map((c) => {
              const rank = order.indexOf(c.agent)
              const isWinner = c.agent === winner
              return (
                <div
                  key={c.agent}
                  className={`agent-card${isWinner ? ' winner' : ''}`}
                >
                  <div className="agent-head">
                    <span className="agent-model">{modelName(c.agent)}</span>
                    <span className="agent-tags">
                      {rank >= 0 && <span className="rank-pill">#{rank + 1}</span>}
                      {isWinner && (
                        <span className="badge-win">{isFixture ? 'verified' : 'selected'}</span>
                      )}
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
            {isFixture ? 'Chairman read (patch-only)' : 'Chairman decision'} (
            {modelName(r.config?.chairman_model)})
          </div>
          <div className="chairman-pick">
            <div className="pick-head">
              {isFixture ? 'Preferred by reading' : 'Selected'}{' '}
              <code>{modelName(chairmanPick)}</code>
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
                    <span className={m === chairmanPick ? 'rank-win' : ''}>
                      {modelName(m)}
                    </span>
                  </span>
                ))}
              </div>
            )}
            <p className="pick-rationale">{decision.rationale}</p>
          </div>
        </>
      )}
    </section>
  )
}
