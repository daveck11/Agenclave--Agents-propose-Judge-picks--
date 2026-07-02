import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { get, del } from '../api'
import { useIssue } from '../context/IssueContext'
import IssueCard from '../components/IssueCard'
import RunCard from '../components/RunCard'

export default function WorkspacePage() {
  const navigate = useNavigate()
  const { setIssue } = useIssue()

  const [issues, setIssues] = useState([])
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    setLoading(true)
    Promise.all([
      get('/issues').catch(() => []),
      get('/runs').catch(() => []),
    ])
      .then(([is, rs]) => {
        if (!alive) return
        setIssues(Array.isArray(is) ? is : [])
        setRuns(Array.isArray(rs) ? rs : [])
      })
      .catch((err) => {
        if (alive) setError(err.message || 'Could not load your workspace.')
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [])

  function sendIssueToCodeFix(issue) {
    setIssue({
      title: issue.title,
      body: issue.body,
      triage: {
        label: issue.label,
        confidence: issue.confidence,
        severity: issue.severity,
        top_tokens: issue.top_tokens,
        recommendations: issue.recommendations,
      },
    })
    navigate('/code-fix')
  }

  async function deleteIssue(id) {
    await del(`/issues/${id}`)
    setIssues((list) => list.filter((i) => i.id !== id))
  }

  return (
    <>
      <p className="subtitle">Your saved issues and best-of-N runs.</p>

      {error && <div className="error">{error}</div>}

      {loading ? (
        <div className="route-loading">Loading your workspace…</div>
      ) : (
        <>
          <section className="ws-section">
            <h2 className="ws-heading">Saved issues</h2>
            {issues.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">◇</div>
                <p>No saved issues yet - triage one to get started.</p>
              </div>
            ) : (
              <div className="saved-list">
                {issues.map((issue) => (
                  <IssueCard
                    key={issue.id}
                    issue={issue}
                    onSend={sendIssueToCodeFix}
                    onDelete={deleteIssue}
                  />
                ))}
              </div>
            )}
          </section>

          <section className="ws-section">
            <h2 className="ws-heading">Saved runs</h2>
            {runs.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">◇</div>
                <p>No saved runs yet - dispatch a fix from the Code-fix page.</p>
              </div>
            ) : (
              <div className="saved-list">
                {runs.map((run) => (
                  <RunCard key={run.run_id || run.id} run={run} />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </>
  )
}
