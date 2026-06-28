import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios"
import { useAuthStore } from "@/store/authStore"

const baseURL = import.meta.env.VITE_API_URL || ""

export const apiClient = axios.create({
  // Empty string → relative URLs, proxied by Vite to the backend.
  // Works from any host (localhost, LAN IP) without rebuilding.
  baseURL,
  timeout: 30_000,
})

apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ── Silent token refresh on 401 ────────────────────────────────────────────────
// When the access token expires, transparently exchange the refresh token for a
// fresh pair and retry the request ONCE. We only log the user out if the refresh
// itself fails (refresh token dead) or there is no refresh token. Concurrent 401s
// share a single in-flight refresh so the refresh endpoint never fires more than
// once at a time.
let refreshPromise: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const { refreshToken, setTokens, clearAuth } = useAuthStore.getState()
  if (!refreshToken) {
    clearAuth()
    return null
  }
  try {
    // Bare axios (no interceptors) so a 401 on the refresh call can't recurse.
    const { data } = await axios.post(`${baseURL}/api/auth/refresh`, {
      refresh_token: refreshToken,
    })
    setTokens(data.access_token, data.refresh_token)
    return data.access_token as string
  } catch {
    clearAuth() // refresh token is dead — this is a genuine logout
    return null
  }
}

// Never try to refresh on the auth endpoints themselves.
const AUTH_PATHS = ["/api/auth/login", "/api/auth/register", "/api/auth/refresh"]

apiClient.interceptors.response.use(
  (res) => res,
  async (err: AxiosError) => {
    const original = err.config as
      | (InternalAxiosRequestConfig & { _retried?: boolean })
      | undefined
    const is401 = err.response?.status === 401
    const isAuthCall = !!original && AUTH_PATHS.some((p) => (original.url ?? "").includes(p))

    if (!is401 || !original || isAuthCall) {
      return Promise.reject(err)
    }

    // Already retried once with a fresh token and still 401 → give up.
    if (original._retried) {
      useAuthStore.getState().clearAuth()
      return Promise.reject(err)
    }

    // No refresh token (e.g. a session predating this feature) → clean logout.
    if (!useAuthStore.getState().refreshToken) {
      useAuthStore.getState().clearAuth()
      return Promise.reject(err)
    }

    // Refresh once (shared across concurrent 401s), then replay the request.
    original._retried = true
    if (!refreshPromise) {
      refreshPromise = refreshAccessToken().finally(() => {
        refreshPromise = null
      })
    }
    const newToken = await refreshPromise
    if (newToken) {
      return apiClient(original) // request interceptor re-attaches the new token
    }
    return Promise.reject(err) // refresh failed; clearAuth already ran
  },
)
