import { useState } from 'react'
import { post } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useIssue } from '../context/IssueContext'
import RunResult from '../components/RunResult'

const EST_COST = '~$0.07'

const EXAMPLES = [
  {
    name: 'Bug (passes gate)',
    title: 'App crashes on startup with NullPointerException after upgrade',
    body:
      'Since updating to version 2.3 the application crashes immediately on launch ' +
      'with a NullPointerException. The stack trace points to ConfigLoader.init(). ' +
      'Rolling back to 2.2 fixes it. Happens on every machine we tried - a clear regression.',
  },
  {
    name: 'Feature (filtered)',
    title: 'Add CSV export to the reports page',
    body:
      'It would be great if we could export the generated reports to CSV so we ' +
      'can open them in Excel. A simple "Export to CSV" button would do.',
  },
]

export default function CodeFixPage() {
  const { user } = useAuth()
  const { current, patchIssue } = useIssue()

  // Prefill from the handed-off issue; the fields stay editable.
  const title = current.title
  const body = current.body
  const setTitle = (v) => patchIssue({ title: v })
  const setBody = (v) => patchIssue({ body: v })

  const [live, setLive] = useState(false)
  const [status, setStatus] = useState('idle')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  function loadExample(ex) {
    patchIssue({ title: ex.title, body: ex.body })
    setResult(null)
    setError('')
  }

  async function run() {
    setError('')
    setResult(null)
    setStatus('running')
    try {
      // When logged in the backend saves the run automatically and returns a
      // run_id; we surface that as a "saved" badge.
      const data = await post('/runs', { title, body, live }, { auth: Boolean(user) })
      setResult(data)
      setStatus('done')
    } catch (err) {
      setError(err.message || 'Could not reach the API.')
      setStatus('idle')
    }
  }

  const running = status === 'running'
  const canRun = (title.trim() || body.trim()) && !running
  const savedRun = Boolean(user && result && result.run_id)

  return (
    <>
      <p className="subtitle">
        Stage 1 triages the issue and gates Stage 2. Only a bug is dispatched to
        the best-of-N agents.
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

      {!user && (
        <div className="cost-note" style={{ marginTop: 14 }}>
          <strong>Log in</strong> to automatically save runs to your Workspace.
        </div>
      )}

      {savedRun && (
        <div className="save-badge" style={{ marginTop: 14 }}>
          Saved to your Workspace ✓
        </div>
      )}

      {error && <div className="error">{error}</div>}

      <RunResult result={result} />
    </>
  )
}
