import { useEffect, useState } from 'react'
import { Routes, Route, Link } from 'react-router-dom'
import './App.css'
import Nav from './components/Nav'
import AuthMenu from './components/AuthMenu'
import ProtectedRoute from './components/ProtectedRoute'
import TriagePage from './pages/TriagePage'
import CodeFixPage from './pages/CodeFixPage'
import WorkspacePage from './pages/WorkspacePage'
import AboutPage from './pages/AboutPage'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'

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
  const health = useApiHealth()

  return (
    <div className="page">
      <div className="shell">
        <header className="hero">
          <div className="hero-top">
            <Link to="/" className="brand">
              <span className="logo">◆</span>
              <span className="wordmark">Agenclave</span>
            </Link>
            <div className="hero-right">
              <span
                className={`status ${
                  health === null ? 'pending' : health ? 'up' : 'down'
                }`}
              >
                <span className="dot" />
                {health === null ? 'connecting' : health ? 'API live' : 'API offline'}
              </span>
              <AuthMenu />
            </div>
          </div>
          <p className="tagline">Issue triage and best-of-N agent code fixes.</p>
          <Nav />
        </header>

        <main className="card">
          <Routes>
            <Route path="/" element={<TriagePage />} />
            <Route path="/code-fix" element={<CodeFixPage />} />
            <Route
              path="/workspace"
              element={
                <ProtectedRoute>
                  <WorkspacePage />
                </ProtectedRoute>
              }
            />
            <Route path="/about" element={<AboutPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route
              path="*"
              element={
                <div className="empty-state">
                  <div className="empty-icon">◇</div>
                  <p>Page not found.</p>
                  <Link to="/" className="btn-secondary">
                    Back to Triage
                  </Link>
                </div>
              }
            />
          </Routes>
        </main>

        <footer className="foot">Agenclave · MIT licensed</footer>
      </div>
    </div>
  )
}
