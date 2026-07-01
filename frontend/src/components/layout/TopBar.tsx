import Breadcrumbs from "./Breadcrumbs"
import NotificationBell from "./NotificationBell"
import UserMenu from "./UserMenu"

export default function TopBar() {
  return (
    <header className="dark relative flex h-14 items-center justify-between gap-4 border-b border-white/5 bg-gradient-to-r from-indigo-950 to-violet-950 px-6">
      <Breadcrumbs />
      <div className="flex shrink-0 items-center gap-1.5">
        <NotificationBell />
        <div className="mx-1 h-6 w-px bg-white/10" />
        <UserMenu />
      </div>
      {/* Brand accent — a thin gradient hairline along the bottom edge. */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-indigo-500 via-violet-500 to-fuchsia-500 opacity-80" />
    </header>
  )
}
