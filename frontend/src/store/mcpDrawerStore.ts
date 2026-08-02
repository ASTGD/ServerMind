import { create } from "zustand"

/** The top-bar MCP Activity drawer — a floating panel that slides down from the top bar to
 *  show what a connected AI is doing live, and slides back up when collapsed.
 *
 *  Opened by hand only. It used to slide down on its own whenever a new burst of activity
 *  started, so it reappeared over the page every few minutes and covered the right-hand
 *  side of whatever was being read. The top-bar badge is the notification; this is the
 *  detail, and asking for the detail is the reader's decision. */
interface McpDrawerState {
  open: boolean
  setOpen: (v: boolean) => void
  toggle: () => void
  /** Slide it back up. */
  collapse: () => void
}

export const useMcpDrawerStore = create<McpDrawerState>((set) => ({
  open: false,
  setOpen: (v) => set({ open: v }),
  toggle: () => set((s) => ({ open: !s.open })),
  collapse: () => set({ open: false }),
}))
