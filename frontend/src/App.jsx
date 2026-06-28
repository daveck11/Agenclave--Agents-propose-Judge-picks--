import { useEffect, useState } from 'react'
import './App.css'
import TriageView from './TriageView'
import Stage2View from './Stage2View'

const TABS = [
  { id: 'triage', label: 'Stage 1 · Triage' },
  { id: 'stage2', label: 'Stage 2 · Best-of-N' },
]

function useApiHealth() {
  const [ok, setOk] = useState(null)
  useEffect(() => {
    let alive = true
    const ping = async () => {
      try {
        const r = await fetch('/health')
        const j = await r.json()
        if (alive) setOk(j.status === 'ok' && j.models_loaded)
      } catch {
        if (alive) setOk(false)
      }
    }
    ping()
    const t = setInterval(ping, 5000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])
  return ok
}

export default function App() {
  const [tab, setTab] = useState('triage')
  // Shared issue text so a bug entered on one tab stays on the other.
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const health = useApiHealth()

  const issue = { title, body, setTitle, setBody }

  return (
    <div className="page">
      <div className="shell">
        <header className="hero">
          <div className="hero-top">
            <div className="brand">
              <span className="logo">◆</span>
              <span className="wordmark">Agenclave</span>
            </div>
            <span className={`status ${health === null ? 'pending' : health ? 'up' : 'down'}`}>
              <span className="dot" />
              {health === null ? 'connecting' : health ? 'API live' : 'API offline'}
            </span>
          </div>
          <p className="tagline">Issue triage and best-of-N agent code fixes.</p>
          <nav className="tabs">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                className={`tab${t.id === tab ? ' active' : ''}`}
                onClick={() => setTab(t.id)}
              >
                <span className="tab-label">{t.label}</span>
              </button>
            ))}
          </nav>
        </header>

        <main className="card">
          {/* Both stay mounted; hidden tab keeps its inputs and results. */}
          <div style={{ display: tab === 'triage' ? 'block' : 'none' }}>
            <TriageView issue={issue} />
          </div>
          <div style={{ display: tab === 'stage2' ? 'block' : 'none' }}>
            <Stage2View issue={issue} />
          </div>
        </main>

        <footer className="foot">Agenclave · MIT licensed</footer>
      </div>
    </div>
  )
}
