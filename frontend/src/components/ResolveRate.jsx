// Displays the SWE-bench resolve rate measured offline by scripts/grade_swebench.py
// and served read-only at GET /resolve-rate. Renders NOTHING until a real grading
// exists (the endpoint 404s), so the UI never shows a fabricated score.

import { useEffect, useState } from 'react'
import { get } from '../api'

export default function ResolveRate() {
  const [data, setData] = useState(null)

  useEffect(() => {
    let alive = true
    get('/resolve-rate', { auth: false })
      .then((d) => alive && setData(d))
      .catch(() => {}) // 404 = not graded yet -> render nothing
    return () => {
      alive = false
    }
  }, [])

  if (!data || !Array.isArray(data.systems) || data.systems.length === 0) return null

  return (
    <div className="resolve">
      <span className="stage-label">Resolve rate · official SWE-bench harness</span>
      <div className="resolve-grid">
        {data.systems.map((s) => (
          <div
            className={`resolve-card${s.name === 'chairman' ? ' winner' : ''}`}
            key={s.name}
          >
            <span className="resolve-num">
              {s.resolved}/{s.total}
            </span>
            <span className="resolve-name">{s.label || s.name}</span>
          </div>
        ))}
      </div>
      <p className="resolve-note">
        {data.dataset} · graded by the official harness in Docker · honest, not
        self-scored.
      </p>
    </div>
  )
}
