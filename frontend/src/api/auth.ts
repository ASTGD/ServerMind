import { apiClient } from "./client"
import { useAuthStore } from "@/store/authStore"
import type { User } from "@/types"

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user: User
}

export interface RegisterBody {
  email: string
  password: string
  name?: string
  preferred_language?: string
}

export interface LoginBody {
  email: string
  password: string
}

/** Register a new account. */
export async function register(body: RegisterBody): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>("/api/auth/register", body)
  return data
}

/** Login with email + password. */
export async function login(body: LoginBody): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>("/api/auth/login", body)
  return data
}

/** Get the authenticated user profile. */
export async function getMe(): Promise<User> {
  const { data } = await apiClient.get<User>("/api/auth/me")
  return data
}

/** Update preferred language. */
export async function updateLanguage(language: string): Promise<User> {
  const { data } = await apiClient.put<User>("/api/auth/language", { language })
  return data
}

export interface ProfileUpdateBody {
  name?: string | null
  avatar_url?: string | null
  preferred_language?: string
}

/** Update the authenticated user's profile (name, avatar, language). */
export async function updateProfile(body: ProfileUpdateBody): Promise<User> {
  const { data } = await apiClient.put<User>("/api/auth/me", body)
  return data
}

/** Change the account password (requires the current one). */
export async function changePassword(
  current_password: string,
  new_password: string,
): Promise<void> {
  await apiClient.put("/api/auth/password", { current_password, new_password })
}

/** Mint a short-lived, single-use WebSocket auth ticket. */
export async function getWsTicket(): Promise<{ ticket: string; expires_in: number }> {
  const { data } = await apiClient.post<{ ticket: string; expires_in: number }>("/api/auth/ws-ticket")
  return data
}

/**
 * Build the auth query for a WebSocket URL. Prefers a single-use ticket (keeps
 * the JWT out of the URL / proxy logs); falls back to the access token if the
 * ticket endpoint is unavailable (e.g. Redis down).
 */
export async function wsAuthQuery(): Promise<string> {
  try {
    const { ticket } = await getWsTicket()
    return `ticket=${encodeURIComponent(ticket)}`
  } catch {
    const token = useAuthStore.getState().token
    return `token=${encodeURIComponent(token ?? "")}`
  }
}

/** Logout — clears tokens on client side. */
export async function logout(): Promise<void> {
  await apiClient.post("/api/auth/logout").catch(() => {})
}
