import { useEffect, useRef, useState } from "react"
import { Outlet, useLocation } from "react-router-dom"
import Sidebar from "./Sidebar"
import TopBar from "./TopBar"
import VerifyBanner from "./VerifyBanner"
import AssistantDrawer from "./AssistantDrawer"
import TerminalWorkspace from "@/components/terminal/TerminalWorkspace"
import { useAssistantStore } from "@/store/assistantStore"
import { useTerminalStore } from "@/store/terminalStore"

/** Root application shell — sidebar + topbar + page outlet + the global AI assistant
 *  and terminal workspace (both live here so they persist across all navigation). */
export default function Layout() {
  const assistantOpen = useAssistantStore((s) => s.open)
  const toggleAssistant = useAssistantStore((s) => s.toggle)
  const closeAssistant = useAssistantStore((s) => s.close)
  const terminalOpen = useTerminalStore((s) => s.open)
  const toggleTerminal = useTerminalStore((s) => s.toggle)
  const minimizeTerminal = useTerminalStore((s) => s.minimize)
  const location = useLocation()
  // Mobile navigation drawer (the sidebar is off-canvas below lg).
  const [navOpen, setNavOpen] = useState(false)

  // ⌘K toggles Ally; ⌘` toggles the terminal window.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        toggleAssistant()
      } else if ((e.metaKey || e.ctrlKey) && e.key === "`") {
        e.preventDefault()
        toggleTerminal()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [toggleAssistant, toggleTerminal])

  // One tool window at a time: opening Ally tucks the terminal to its dock, and opening
  // the terminal tucks Ally to its dock. Both stay alive underneath.
  useEffect(() => {
    if (assistantOpen) minimizeTerminal()
  }, [assistantOpen, minimizeTerminal])
  useEffect(() => {
    if (terminalOpen) closeAssistant()
  }, [terminalOpen, closeAssistant])

  // Navigating to another page minimizes BOTH tool windows to their docks — the Ally
  // conversation, any running mission, and every SSH session stay alive, so re-opening
  // from the sidebar restores everything.
  const didMount = useRef(false)
  useEffect(() => {
    if (!didMount.current) { didMount.current = true; return }
    closeAssistant()
    minimizeTerminal()
    setNavOpen(false)
  }, [location.pathname, closeAssistant, minimizeTerminal])

  return (
    <div className="flex h-full bg-background">
      <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <TopBar onMenuClick={() => setNavOpen(true)} />
        <VerifyBanner />
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
      <AssistantDrawer />
      <TerminalWorkspace />
    </div>
  )
}
