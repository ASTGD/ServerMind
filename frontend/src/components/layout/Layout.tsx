import { useEffect, useRef } from "react"
import { Outlet, useNavigate, useLocation } from "react-router-dom"
import Sidebar from "./Sidebar"
import TopBar from "./TopBar"
import VerifyBanner from "./VerifyBanner"
import AssistantDrawer from "./AssistantDrawer"
import TerminalWorkspace from "@/components/terminal/TerminalWorkspace"
import { useAssistantStore } from "@/store/assistantStore"

/** Root application shell — sidebar + topbar + page outlet + the global AI assistant
 *  and terminal workspace (both live here so they persist across all navigation). */
export default function Layout() {
  const toggleAssistant = useAssistantStore((s) => s.toggle)
  const closeAssistant = useAssistantStore((s) => s.close)
  const navigate = useNavigate()
  const location = useLocation()
  const pathRef = useRef(location.pathname)
  pathRef.current = location.pathname

  // ⌘K summons Ally; ⌘` opens the terminal workspace (toggles back if already there).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        toggleAssistant()
      } else if ((e.metaKey || e.ctrlKey) && e.key === "`") {
        e.preventDefault()
        if (pathRef.current === "/terminal") navigate(-1)
        else navigate("/terminal")
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [toggleAssistant, navigate])

  // Navigating to another page MINIMIZES the Ally window back to its dock icon — the
  // conversation + any running mission stay alive, so re-opening restores everything.
  const didMount = useRef(false)
  useEffect(() => {
    if (!didMount.current) { didMount.current = true; return }
    closeAssistant()
  }, [location.pathname, closeAssistant])

  return (
    <div className="flex h-full bg-background">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
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
