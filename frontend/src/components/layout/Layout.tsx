import { useEffect } from "react"
import { Outlet } from "react-router-dom"
import Sidebar from "./Sidebar"
import TopBar from "./TopBar"
import VerifyBanner from "./VerifyBanner"
import AssistantDrawer from "./AssistantDrawer"
import TerminalDock from "@/components/terminal/TerminalDock"
import { useAssistantStore } from "@/store/assistantStore"
import { useTerminalStore } from "@/store/terminalStore"

/** Root application shell — sidebar + topbar + page outlet + the global AI assistant
 *  and terminal dock (both live here so they persist across all navigation). */
export default function Layout() {
  const assistantOpen = useAssistantStore((s) => s.open)
  const toggleAssistant = useAssistantStore((s) => s.toggle)
  const toggleDock = useTerminalStore((s) => s.toggleDock)

  // ⌘K summons Ally; ⌘` toggles the terminal dock — from anywhere.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        toggleAssistant()
      } else if ((e.metaKey || e.ctrlKey) && e.key === "`") {
        e.preventDefault()
        toggleDock()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [toggleAssistant, toggleDock])

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
      <TerminalDock />
    </div>
  )
}
