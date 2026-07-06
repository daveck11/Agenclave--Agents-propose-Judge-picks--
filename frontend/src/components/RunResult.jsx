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
// Verification panel: just notes that the tests were actually run. The winner
// and the reasoning are announced by the Chairman verdict below.
function Verification({ fixture }) {
  return (
    <div className="verify">
      <div className="stage-label">
        Verification - ran the tests{fixture?.module ? ` (${fixture.module})` : ''}
      </div>
      <p className="verify-note">
        Each candidate patch was applied in a sandbox and its tests were run.
      </p>
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

  // For a fixture run the Chairman verdict announces the verified winner and why
  // it won relative to the judge's read.
  const tierOf = (a) => ((r.verification || []).find((v) => v.agent === a) || {}).tier
  let verdictLine = null
  if (isFixture && winner) {
    const V = r.verification || []
    const wv = V.find((v) => v.agent === winner) || {}
    const wt = wv.total
      ? `passes all its tests (${wv.passed}/${wv.total})`
      : 'passes its tests'
    let why
    if (chairmanPick === winner) {
      why =
        "The Chairman's read agrees, and it holds the strongest verified track record, so it is the one to trust."
    } else if (tierOf(chairmanPick) !== 'trusted') {
      why = `The Chairman read-preferred ${modelName(chairmanPick)} on how the patch looks, but that patch fails the tests, so verification takes the candidate that actually works.`
    } else {
      why = `The Chairman read-preferred ${modelName(chairmanPick)}, and both patches pass, so verification breaks the tie by track record and takes the more-trusted of the two.`
    }
    // Note any other candidates that were ruled out on the tests (not the winner,
    // and not the judge's pick since that is already addressed above).
    const ruledOut = V.filter(
      (v) => v.tier !== 'trusted' && v.agent !== chairmanPick && v.agent !== winner
    ).map((v) => modelName(v.agent))
    const ruled = ruledOut.length
      ? ` ${ruledOut.join(', ')} ${ruledOut.length === 1 ? 'is' : 'are'} ruled out for not passing the tests.`
      : ''
    verdictLine = `${modelName(winner)} ${wt}. ${why}${ruled}`
  }

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

          {r.verification && <Verification fixture={r.fixture} />}

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
            Chairman verdict ({modelName(r.config?.chairman_model)})
          </div>
          <div className="chairman-pick">
            {isFixture && chairmanPick && (
              <div className="pick-sub">
                Chairman picked <code>{modelName(chairmanPick)}</code> by reading
              </div>
            )}
            <div className="pick-head">
              {isFixture ? 'Overall winner' : 'Selected'}{' '}
              <code>{modelName(isFixture ? winner : chairmanPick)}</code>
              {isFixture && <span className="badge-win">verified</span>}
              {decision.synthesized && (
                <span className="synth-pill">synthesised</span>
              )}
            </div>
            {isFixture && verdictLine && (
              <div className="verify-callout" style={{ marginTop: 8 }}>
                {verdictLine}
              </div>
            )}
            {!isFixture && ranking.length > 0 && (
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
            {!isFixture && <p className="pick-rationale">{decision.rationale}</p>}
          </div>
        </>
      )}
    </section>
  )
}
