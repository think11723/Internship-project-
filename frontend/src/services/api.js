import axios from 'axios'
import { decodeDeep } from '../utils/htmlEntities'

// Use empty string to leverage Vite proxy for /api requests
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

// 30 s request timeout — long enough for the OpenRouter cover-letter
// call (~25 s in the worst case) with a small safety margin, short
// enough to fail fast on a stuck connection.
const REQUEST_TIMEOUT_MS = 30_000

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: REQUEST_TIMEOUT_MS,
})

// Key under which this browser's opaque user id is persisted.
const USER_ID_STORAGE_KEY = 'fundflow:uid'

/**
 * Return this browser's user id, minting one on first use.
 *
 * INTERIM — this is an isolation key, not a credential. It is generated
 * client-side and the backend does not verify it, so it separates users'
 * data but proves nothing about who is calling.
 *
 * TODO(firebase): replace the body of this function with
 * `await getAuth().currentUser?.getIdToken()` and switch the header
 * below to `Authorization: Bearer <token>`. The backend already prefers
 * that header (see backend/app/core/auth.py), so no other frontend file
 * needs to change.
 *
 * Falls back to an in-memory id when localStorage is unavailable
 * (private browsing, storage disabled) so requests still succeed —
 * isolation then lasts only for the page session.
 */
let inMemoryUserId = null

function getUserId() {
  try {
    const existing = localStorage.getItem(USER_ID_STORAGE_KEY)
    if (existing) return existing
    const minted = generateUserId()
    localStorage.setItem(USER_ID_STORAGE_KEY, minted)
    return minted
  } catch {
    // Storage unavailable — keep one id for the lifetime of the page.
    if (!inMemoryUserId) inMemoryUserId = generateUserId()
    return inMemoryUserId
  }
}

/**
 * Generate an id matching the backend's accepted charset:
 * ^[A-Za-z0-9_-]{1,128}$ (see backend/app/core/auth.py). Note this
 * excludes dots and slashes because the id is used as a directory name
 * server-side.
 */
function generateUserId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID().replace(/-/g, '')
  }
  // Fallback for older browsers / non-secure contexts.
  return `u${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`
}

// Request interceptor — attach the caller's identity to every request.
// This is the single place identity enters the API layer; no call-site
// needs to know about it.
api.interceptors.request.use(
  (config) => {
    config.headers = config.headers || {}
    config.headers['X-User-Id'] = getUserId()
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor — decode HTML entities, then normalize every error
// into a single, user-readable message. The backend already returns
// { status, message, error_code, request_id } but we keep the
// normalization here so the UI never has to read axios internals.
api.interceptors.response.use(
  (response) => {
    // Company copy is scraped from press releases and careers pages, so it
    // arrives HTML-encoded (`Anthropic&rsquo;s`, `Series&nbsp;B`). React
    // renders text nodes literally and never decodes entities, so we decode
    // here — the single point where backend data enters the app. Every
    // service imports this instance, so no component or service should
    // decode again (a second pass would over-decode intentionally
    // double-encoded text). See utils/htmlEntities.js.
    response.data = decodeDeep(response.data)
    return response
  },
  (error) => {
    const userMessage = toUserMessage(error)
    // Surface the original axios error for the console; the UI uses
    // error.message which we've now set to the user-friendly text.
    error.userMessage = userMessage
    if (typeof console !== 'undefined') {
      console.error('API error:', error.message, '→', userMessage)
    }
    return Promise.reject(error)
  }
)

/**
 * Map every axios error to a short, plain-English string the UI can
 * display verbatim. No jargon, no stack traces, no internal codes.
 */
function toUserMessage(error) {
  // The backend sends a clean {message, status, request_id} envelope;
  // prefer the server's wording when present.
  const serverMessage = error?.response?.data?.message
  if (serverMessage && typeof serverMessage === 'string') {
    return serverMessage
  }

  // No response from server (network / CORS / DNS / offline).
  if (!error?.response) {
    if (error?.code === 'ECONNABORTED' || /timeout/i.test(error?.message || '')) {
      return 'The request took too long. Please try again.'
    }
    return 'Unable to reach the AI service. Please check your connection and try again.'
  }

  // 5xx — server-side problem.
  if (error.response.status >= 500) {
    return 'Something went wrong on our end. Please try again in a moment.'
  }

  // 4xx — caller-side problem. Generic but readable.
  if (error.response.status === 404) {
    return 'We couldn’t find what you were looking for.'
  }
  if (error.response.status === 401 || error.response.status === 403) {
    return 'You don’t have access to this resource.'
  }

  return 'We couldn’t complete that request. Please try again.'
}

export default api
export { toUserMessage, REQUEST_TIMEOUT_MS, getUserId, USER_ID_STORAGE_KEY }

