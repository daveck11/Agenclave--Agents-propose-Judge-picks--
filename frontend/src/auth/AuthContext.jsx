import { createContext, useContext, useEffect, useState } from 'react'
import { post, get, getToken, setToken } from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  // On mount, hydrate the user from an existing token (logout on 401/expired).
  useEffect(() => {
    let alive = true
    const token = getToken()
    if (!token) {
      setLoading(false)
      return
    }
    get('/auth/me', { auth: true })
      .then((me) => {
        if (alive) setUser(me)
      })
      .catch(() => {
        setToken(null)
        if (alive) setUser(null)
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [])

  async function authenticate(path, email, password) {
    const data = await post(path, { email, password }, { auth: false })
    setToken(data.access_token)
    setUser(data.user)
    return data.user
  }

  const login = (email, password) => authenticate('/auth/login', email, password)
  const register = (email, password) =>
    authenticate('/auth/register', email, password)

  function logout() {
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
