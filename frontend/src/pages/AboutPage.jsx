// Why Agenclave exists. This page frames the project as an honest, open-source
// learning reproduction of Blackbox AI's "Chairman LLM" pattern — full credit to
// their team — so the intent is unmistakable on first visit.

import ResolveRate from '../components/ResolveRate'

// TODO(David): point this at the public repo before sharing.
const REPO_URL = 'https://github.com/davidnkpa/agenclave'

const CONCEPT_MAP = [
  {
    bb: 'Chairman LLM scores every candidate on correctness, performance, risk and complexity',
    ag: 'A Chairman judge LLM ranks each agent patch on correctness / risk / complexity, then selects or synthesises the best',
  },
  {
    bb: 'Dispatch one task to Blackbox + Claude Code + Codex in parallel',
    ag: 'asyncio fan-out to Claude / OpenAI / Blackbox behind one Agent interface',
  },
  {
    bb: 'Ranked #1 on Princeton’s SWE-bench',
    ag: 'Runs on real SWE-bench Lite instances and emits SWE-bench-format predictions',
  },
  {
    bb: 'All models, all agents under one endpoint',
    ag: 'Provider-agnostic — switch vendors with a single config value',
  },
]

export default function AboutPage() {
  return (
    <>
      <p className="subtitle">
        Agenclave is a small, <strong>honest open-source reproduction</strong> of Blackbox AI&rsquo;s
        &ldquo;Chairman LLM&rdquo; pattern, built by a CS student to deeply understand how
        dispatch-many-agents / judge-the-best architectures actually work. Full credit for the idea
        belongs to the Blackbox team.
      </p>

      <div className="flow about-flow">
        <span className="flow-node">issue in</span>
        <span className="flow-arrow">&rarr;</span>
        <span className="flow-node">Stage 1: triage &amp; gate</span>
        <span className="flow-arrow">&rarr;</span>
        <span className="flow-node">fan out to N agents</span>
        <span className="flow-arrow">&rarr;</span>
        <span className="flow-node accent">Chairman picks / synthesises</span>
      </div>

      <span className="stage-label">How it maps to Blackbox</span>
      <div className="cmp">
        <div className="cmp-row cmp-head">
          <div>Blackbox AI</div>
          <div>Agenclave (this project)</div>
        </div>
        {CONCEPT_MAP.map((row, i) => (
          <div className="cmp-row" key={i}>
            <div className="cmp-bb">{row.bb}</div>
            <div className="cmp-ag">{row.ag}</div>
          </div>
        ))}
      </div>

      <ResolveRate />

      <span className="stage-label">Built honestly</span>
      <div className="honesty">
        This is a portfolio project, not a product. It reports what <strong>didn&rsquo;t</strong> work
        as readily as what did: transformer embeddings (MiniLM) actually <strong>lost</strong> to a
        plain TF-IDF classifier, so the simpler model ships and the result is documented. A severity
        head and a <code>performance</code> class were deliberately cut for lack of a cleanly-licensed
        gold dataset. Stage-2 resolve rates are reported as measured by the official SWE-bench harness
        &mdash; <strong>no self-graded or fabricated scores</strong>. MIT licensed; happy to make the
        repo private on request.
      </div>

      <div className="result-cta">
        <a className="btn-secondary" href={REPO_URL} target="_blank" rel="noreferrer">
          View the code on GitHub &rarr;
        </a>
      </div>
    </>
  )
}
