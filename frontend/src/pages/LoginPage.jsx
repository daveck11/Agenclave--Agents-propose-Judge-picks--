import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(email, password)
      // Always land on Triage (the start of the flow), not a deep link.
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.message || 'Login failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-form-wrap">
      <h2 className="auth-title">Log in</h2>
      <p className="subtitle">Welcome back. Log in to access your workspace.</p>

      <form onSubmit={submit}>
        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />

        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <button
          type="submit"
          className="submit"
          disabled={busy || !email || !password}
        >
          {busy ? 'Logging in…' : 'Log in'}
        </button>
      </form>

      {error && <div className="error">{error}</div>}

      <p className="auth-switch">
        No account? <Link to="/register">Register</Link>
      </p>
    </div>
  )
}
