// Thin fetch wrapper around the Agenclave API.
//
// All calls go same-origin (the Vite dev proxy forwards /auth, /issues, /runs,
// /triage, /health to the FastAPI service). Requests send/expect JSON and, when
// a token is present, an `Authorization: Bearer <token>` header. Errors are
// normalised to `{ status, message }` so callers can render a single string.

const TOKEN_KEY = 'agenclave_token'

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* ignore storage failures (private mode, etc.) */
  }
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.message = message
  }
}

/**
 * Core request helper.
 * @param {string} path     API path, e.g. "/triage"
 * @param {object} options
 * @param {string} [options.method="GET"]
 * @param {object} [options.body]   JSON-serialisable request body
 * @param {boolean} [options.auth]  attach bearer token; defaults to true when a
 *                                  token exists, false otherwise
 */
export async function apiFetch(path, { method = 'GET', body, auth } = {}) {
  const token = getToken()
  const wantAuth = auth === undefined ? Boolean(token) : auth

  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (wantAuth && token) headers['Authorization'] = `Bearer ${token}`

  let res
  try {
    res = await fetch(path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'Could not reach the API.')
  }

  if (res.status === 204) return null

  let data = null
  const text = await res.text()
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }

  if (!res.ok) {
    let message
    if (data && typeof data === 'object' && data.detail) {
      // FastAPI errors put the human message under `detail`; it can be a string
      // or a list of validation objects.
      message = Array.isArray(data.detail)
        ? data.detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
        : String(data.detail)
    } else if (typeof data === 'string' && data) {
      message = data
    } else {
      message = `Request failed (${res.status}).`
    }
    throw new ApiError(res.status, message)
  }

  return data
}

export const get = (path, opts) => apiFetch(path, { ...opts, method: 'GET' })
export const post = (path, body, opts) =>
  apiFetch(path, { ...opts, method: 'POST', body })
export const del = (path, opts) => apiFetch(path, { ...opts, method: 'DELETE' })
