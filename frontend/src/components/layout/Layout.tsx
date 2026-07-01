import { useEffect } from "react"
import { Outlet } from "react-router-dom"
import Sidebar from "./Sidebar"
import TopBar from "./TopBar"
import VerifyBanner from "./VerifyBanner"
import AssistantDrawer from "./AssistantDrawer"
import { useAssistantStore } from "@/store/assistantStore"

/** Root application shell — sidebar + topbar + page outlet + the global AI assistant. */
export default function Layout() {
  const assistantOpen = useAssistantStore((s) => s.open)
  const toggle = useAssistantStore((s) => s.toggle)

  // ⌘K / Ctrl-K summons the assistant from anywhere.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        toggle()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [toggle])

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
    </div>
  )
}
