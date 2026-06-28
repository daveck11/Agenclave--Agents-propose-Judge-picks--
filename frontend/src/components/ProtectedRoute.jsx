import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

// Gate a route behind authentication. While the auth state is still hydrating
// we show nothing (avoids a redirect flash); once resolved, anonymous users are
// sent to /login with the attempted location so they can be returned after.
export default function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return <div className="route-loading">Loading…</div>
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />
  return children
}
