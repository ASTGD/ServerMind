import { create } from "zustand"
import { persist } from "zustand/middleware"
import type { User } from "@/types"

interface AuthState {
  user: User | null
  token: string | null
  refreshToken: string | null
  /** Set the full session after login/register. Omit refreshToken to keep the current one. */
  setAuth: (user: User, token: string, refreshToken?: string | null) => void
  /** Swap in freshly-rotated tokens after a silent refresh (keeps the current user). */
  setTokens: (token: string, refreshToken: string) => void
  clearAuth: () => void
}

/** Persisted authentication state. */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      refreshToken: null,
      setAuth: (user, token, refreshToken) =>
        set((s) => ({
          user,
          token,
          refreshToken: refreshToken !== undefined ? refreshToken : s.refreshToken,
        })),
      setTokens: (token, refreshToken) => set({ token, refreshToken }),
      clearAuth: () => set({ user: null, token: null, refreshToken: null }),
    }),
    { name: "sm-auth" },
  ),
)
