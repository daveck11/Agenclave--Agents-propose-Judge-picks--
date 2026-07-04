import { useEffect, useState } from 'react'
import { get } from '../api'

// A dropdown of curated practice bugs ("fixtures"). Loading one prefills the
// issue so it flows through Stage 1 (triage) and Stage 2 (code-fix) - a stand-in
// for connecting a real codebase, used for the demo. Renders nothing if the API
// has no fixtures (keeps the page clean when the feature is unavailable).
export default function FixturePicker({ onLoad }) {
  const [fixtures, setFixtures] = useState([])

  useEffect(() => {
    let alive = true
    get('/fixtures', { auth: false })
      .then((fx) => alive && setFixtures(Array.isArray(fx) ? fx : []))
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  if (fixtures.length === 0) return null

  function handleChange(e) {
    const id = e.target.value
    const f = fixtures.find((x) => x.id === id)
    if (f) onLoad(f)
    e.target.value = '' // reset so the same fixture can be re-picked
  }

  return (
    <div className="fixture-picker">
      <label htmlFor="fixture-select" className="fixture-label">
        Load a practice bug
      </label>
      <select id="fixture-select" defaultValue="" onChange={handleChange}>
        <option value="" disabled>
          Choose a fixture…
        </option>
        {fixtures.map((f) => (
          <option key={f.id} value={f.id}>
            {f.title}
          </option>
        ))}
      </select>
      <span className="fixture-hint">
        A self-contained bug + its tests, a stand-in for a real codebase.
      </span>
    </div>
  )
}
