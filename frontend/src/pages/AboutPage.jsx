// About page: what Agenclave is and how it relates to BlackBox.

const REPO_URL = 'https://github.com/daveck11/BlackBox-Agenclave'

const CONCEPT_MAP = [
  {
    bb: 'The Chairman shows why the winning solution won, but each pick is made fresh: no memory of which model actually verifies on which kind of work',
    ag: 'Routes to the trusted subset and shows which models and why (Thompson-sampled from per-model reliability, with the evidence)',
  },
  {
    bb: 'The judge rates candidate patches by reading them',
    ag: 'Verifies each patch by running the tests, then ranks by what actually passes',
  },
  {
    bb: 'Optimised for generation (reported #1 on SWE-bench Verified in 2025)',
    ag: 'Optimised for trust: which output to trust for this task, proven',
  },
  {
    bb: 'One endpoint for all models and agents',
    ag: 'Sits on top of that endpoint (runs its agents through BlackBox) and adds the trust layer',
  },
]

export default function AboutPage() {
  return (
    <>
      <p className="subtitle">
        BLACKBOXAI Agenclave is a <strong>verification-backed trust layer for multi-agent coding</strong>. As AI
        agents outpace human review, the bottleneck stops being generating code and becomes trusting
        it. Agenclave answers one question with evidence: <strong>which of N agent outputs do I
        trust?</strong>
      </p>

      <div className="flow about-flow">
        <span className="flow-node">issue in</span>
        <span className="flow-arrow">&rarr;</span>
        <span className="flow-node">triage &amp; gate</span>
        <span className="flow-arrow">&rarr;</span>
        <span className="flow-node">route to trusted models</span>
        <span className="flow-arrow">&rarr;</span>
        <span className="flow-node">verify each patch</span>
        <span className="flow-arrow">&rarr;</span>
        <span className="flow-node accent">rank by what passes</span>
      </div>

      <span className="stage-label">How it relates to BlackBox</span>
      <div className="cmp">
        <div className="cmp-row cmp-head">
          <div>BlackBox AI</div>
          <div>BLACKBOXAI Agenclave (this project)</div>
        </div>
        {CONCEPT_MAP.map((row, i) => (
          <div className="cmp-row" key={i}>
            <div className="cmp-bb">{row.bb}</div>
            <div className="cmp-ag">{row.ag}</div>
          </div>
        ))}
      </div>

      <span className="stage-label">Built honestly</span>
      <div className="honesty">
        Trust is earned from <strong>real verification</strong>, never a benchmark shortcut. Per-model
        reliability is learned only from in-loop test runs and is kept strictly separate from any
        held-out grader. It also reports what did not work: transformer embeddings (MiniLM) lost to a
        plain TF-IDF classifier, so the simpler model ships. No self-graded or fabricated scores.
      </div>

      <div className="result-cta">
        <a className="btn-secondary" href={REPO_URL} target="_blank" rel="noreferrer">
          View the code on GitHub &rarr;
        </a>
      </div>
    </>
  )
}
