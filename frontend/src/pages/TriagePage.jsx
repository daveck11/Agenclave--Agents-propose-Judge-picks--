import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { post } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useIssue } from '../context/IssueContext'
import RecommendationList from '../components/RecommendationList'
import FixturePicker from '../components/FixturePicker'

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
  return typeof x === 'number' ? `${(x * 100).toFixed(1)}%` : '-'
}

export default function TriagePage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const { current, patchIssue, setIssue, clearIssue } = useIssue()

  const title = current.title
  const body = current.body
  const setTitle = (v) => patchIssue({ title: v })
  const setBody = (v) => patchIssue({ body: v })

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(current.triage || null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  function loadExample(ex) {
    patchIssue({ title: ex.title, body: ex.body, triage: null, fixtureId: null })
    setResult(null)
    setError('')
    setSaved(false)
  }

  function loadFixture(f) {
    patchIssue({ title: f.title, body: f.body, triage: null, fixtureId: f.id })
    setResult(null)
    setError('')
    setSaved(false)
  }

  function clearAll() {
    clearIssue()
    setResult(null)
    setError('')
    setSaved(false)
  }

  async function triage(e) {
    e.preventDefault()
    setLoading(true)
    setError('')
    setResult(null)
    setSaved(false)
    try {
      const data = await post('/triage', { title, body }, { auth: false })
      setResult(data)
      patchIssue({ triage: data })
    } catch (err) {
      if (err.status === 503) {
        setError('Models not trained. Train the classifier and restart the API.')
      } else {
        setError(err.message || 'Could not reach the API.')
      }
    } finally {
      setLoading(false)
    }
  }

  function sendToCodeFix() {
    setIssue({ title, body, triage: result, fixtureId: current.fixtureId })
    navigate('/code-fix')
  }

  async function saveIssue() {
    if (!result) return
    setSaving(true)
    setError('')
    try {
      await post('/issues', {
        title,
        body,
        label: result.label,
        confidence: result.confidence,
        severity: result.severity,
        top_tokens: result.top_tokens,
        recommendations: result.recommendations,
      })
      setSaved(true)
    } catch (err) {
      setError(err.message || 'Could not save the issue.')
    } finally {
      setSaving(false)
    }
  }

  const canSubmit = (title.trim() || body.trim()) && !loading

  return (
    <>
      <div className="subtitle-row">
        <p className="subtitle">
          Classify an issue by type and get next-step recommendations.
        </p>
        <button
          type="button"
          className="clear-btn"
          onClick={clearAll}
          title="Clear title and body"
        >
          <span className="clear-icon">⟳</span> Clear
        </button>
      </div>

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

      <FixturePicker onLoad={loadFixture} />

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

          <RecommendationList recommendations={result.recommendations} />

          <div className="result-cta">
            {result.can_proceed_to_stage2 && (
              <button type="button" className="submit" onClick={sendToCodeFix}>
                Send to the code-fix agents →
              </button>
            )}
            {user && (
              <button
                type="button"
                className="btn-secondary"
                onClick={saveIssue}
                disabled={saving || saved}
              >
                {saved ? 'Saved ✓' : saving ? 'Saving…' : 'Save issue'}
              </button>
            )}
          </div>
        </section>
      )}
    </>
  )
}
