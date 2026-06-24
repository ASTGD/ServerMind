import { Outlet } from "react-router-dom"
import Sidebar from "./Sidebar"
import TopBar from "./TopBar"
import VerifyBanner from "./VerifyBanner"

/** Root application shell — sidebar + topbar + page outlet. */
export default function Layout() {
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
    </div>
  )
}
