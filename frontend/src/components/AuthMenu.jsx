import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export default function AuthMenu() {
  const { user, logout, loading } = useAuth()
  const navigate = useNavigate()

  if (loading) return <span className="auth-menu muted-light">…</span>

  if (user) {
    return (
      <div className="auth-menu">
        <span className="auth-email" title={user.email}>
          {user.email}
        </span>
        <button
          type="button"
          className="auth-link-btn"
          onClick={() => {
            logout()
            navigate('/')
          }}
        >
          Logout
        </button>
      </div>
    )
  }

  return (
    <div className="auth-menu">
      <Link to="/login" className="auth-link-btn">
        Login
      </Link>
      <Link to="/register" className="auth-link-btn primary">
        Register
      </Link>
    </div>
  )
}
