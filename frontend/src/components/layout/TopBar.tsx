import Breadcrumbs from "./Breadcrumbs"
import NotificationBell from "./NotificationBell"
import UserMenu from "./UserMenu"

export default function TopBar() {
  return (
    <header className="relative flex h-14 items-center justify-between gap-4 border-b border-border bg-gradient-to-r from-indigo-100 via-card to-violet-100 px-6 dark:from-indigo-950/40 dark:via-card dark:to-violet-950/40">
      <Breadcrumbs />
      <div className="flex shrink-0 items-center gap-1.5">
        <NotificationBell />
        <div className="mx-1 h-6 w-px bg-border" />
        <UserMenu />
      </div>
      {/* Brand accent — a thin gradient hairline along the bottom edge. */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-indigo-500/60 via-violet-500/40 to-fuchsia-500/60" />
    </header>
  )
}
