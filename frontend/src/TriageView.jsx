import { useState } from 'react'

const EXAMPLES = [
  {
    name: 'Crash bug',
    title: 'App crashes on startup after upgrading to v2.3',
    body:
      'Since updating to version 2.3 the application crashes immediately on launch ' +
      'with a NullPointerException. Stack trace points to ConfigLoader.init(). ' +
      'Rolling back to 2.2 fixes it. Happens on every machine we tried.',
  },
  {
    name: 'Feature request',
    title: 'Add CSV export to the reports page',
    body:
      'It would be great if we could export the generated reports to CSV so we can ' +
      'open them in Excel. Right now the only option is a PDF, which is hard to ' +
      'process further. A simple "Export to CSV" button would do.',
  },
  {
    name: 'Documentation',
    title: 'README install steps are out of date',
    body:
      'The setup instructions reference a pip command that no longer works. The ' +
      'docs should be updated to match the new Makefile targets.',
  },
]

function pct(x) {
  if (typeof x !== 'number') return '-'
  return `${(x * 100).toFixed(1)}%`
}

export default function TriageView({ issue }) {
  const { title, body, setTitle, setBody } = issue
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  function loadExample(ex) {
    setTitle(ex.title)
    setBody(ex.body)
    setResult(null)
    setError('')
  }

  async function triage(e) {
    e.preventDefault()
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const res = await fetch('/triage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, body }),
      })
      if (res.status === 503) {
        setError('Models not trained. Train the classifier and restart the API.')
        return
      }
      if (!res.ok) {
        setError(`Request failed (${res.status}).`)
        return
      }
      setResult(await res.json())
    } catch {
      setError('Could not reach the API.')
    } finally {
      setLoading(false)
    }
  }

  const canSubmit = (title.trim() || body.trim()) && !loading

  return (
    <>
      <p className="subtitle">Classify an issue by type.</p>

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

      <form onSubmit={triage}>
        <label htmlFor="title">Title</label>
        <input
          id="title"
          type="text"
          placeholder="Short summary of the issue"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />

        <label htmlFor="body">Body</label>
        <textarea
          id="body"
          rows={7}
          placeholder="Describe the issue"
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />

        <button type="submit" className="submit" disabled={!canSubmit}>
          {loading ? 'Triaging' : 'Triage'}
        </button>
      </form>

      {error && <div className="error">{error}</div>}

      {result && (
        <section className="result">
          <div className="result-row">
            <div className="metric">
              <span className="metric-label">Label</span>
              <span className="metric-value">{result.label}</span>
              <span className="metric-conf">confidence {pct(result.confidence)}</span>
            </div>
            {result.severity != null && (
              <div className="metric">
                <span className="metric-label">Severity</span>
                <span className={`metric-value sev-${result.severity}`}>
                  {result.severity}
                </span>
                <span className="metric-conf">
                  confidence {pct(result.severity_confidence)}
                </span>
              </div>
            )}
          </div>

          {Array.isArray(result.top_tokens) && result.top_tokens.length > 0 && (
            <div className="tokens">
              <span className="tokens-label">Top tokens</span>
              <div className="chips">
                {result.top_tokens.map((tok, i) => (
                  <span className="chip" key={`${tok}-${i}`}>
                    {typeof tok === 'string' ? tok : JSON.stringify(tok)}
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
    </>
  )
}
