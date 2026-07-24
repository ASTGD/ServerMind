import { create } from "zustand"

/** The top-bar MCP Activity drawer — a floating panel that slides down from the top bar to
 *  show what a connected AI is doing live, and slides back up when collapsed. */
interface McpDrawerState {
  open: boolean
  /** True once the user manually collapsed the drawer during the current run-burst, so it
   *  doesn't auto-reopen for every command; reset when activity goes idle again. */
  suppressed: boolean
  setOpen: (v: boolean) => void
  toggle: () => void
  /** Collapse (slide up) and suppress auto-open until the fleet goes idle again. */
  collapse: () => void
  setSuppressed: (v: boolean) => void
}

export const useMcpDrawerStore = create<McpDrawerState>((set) => ({
  open: false,
  suppressed: false,
  setOpen: (v) => set({ open: v }),
  toggle: () => set((s) => ({ open: !s.open, suppressed: s.open ? true : s.suppressed })),
  collapse: () => set({ open: false, suppressed: true }),
  setSuppressed: (v) => set({ suppressed: v }),
}))
