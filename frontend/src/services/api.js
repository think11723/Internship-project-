import axios from 'axios'

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

// Request interceptor — pass-through. Hook left in place so future
// auth headers / request IDs can be added here.
api.interceptors.request.use(
  (config) => config,
  (error) => Promise.reject(error)
)

// Response interceptor — normalize every error into a single,
// user-readable message. The backend already returns
// { status, message, error_code, request_id } but we keep the
// normalization here so the UI never has to read axios internals.
api.interceptors.response.use(
  (response) => response,
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
export { toUserMessage, REQUEST_TIMEOUT_MS }

