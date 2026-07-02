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
  const assistantOpen = useAssistantStore((s) => s.open)
  const toggleAssistant = useAssistantStore((s) => s.toggle)
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

  return (
    <div className="flex h-full bg-background">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
        <VerifyBanner />
        <main
          className={`flex-1 overflow-auto p-6 transition-[padding] duration-300 ${
            assistantOpen ? "md:pr-[28rem]" : ""
          }`}
        >
          <Outlet />
        </main>
      </div>
      <AssistantDrawer />
      <TerminalWorkspace />
    </div>
  )
}
