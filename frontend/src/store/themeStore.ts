import { create } from "zustand"
import { persist } from "zustand/middleware"

export type Theme = "light" | "dark" | "system"

const media = window.matchMedia("(prefers-color-scheme: dark)")

/** Toggle the `.dark` class on <html> for the chosen theme (tokens do the rest). */
function applyTheme(theme: Theme) {
  const dark = theme === "dark" || (theme === "system" && media.matches)
  document.documentElement.classList.toggle("dark", dark)
}

interface ThemeState {
  theme: Theme
  setTheme: (theme: Theme) => void
}

/** Persisted theme preference. Default "light" — the app's historical appearance. */
export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: "light",
      setTheme: (theme) => {
        applyTheme(theme)
        set({ theme })
      },
    }),
    { name: "sm-theme" },
  ),
)

// Apply once at module load (imported from main.tsx before first render, so no
// light-flash), and follow live OS changes while in "system" mode.
applyTheme(useThemeStore.getState().theme)
media.addEventListener("change", () => {
  if (useThemeStore.getState().theme === "system") applyTheme("system")
})
