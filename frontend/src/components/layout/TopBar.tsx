import Breadcrumbs from "./Breadcrumbs"
import NotificationBell from "./NotificationBell"
import UserMenu from "./UserMenu"

export default function TopBar() {
  return (
    <header className="flex h-14 items-center justify-between gap-4 border-b border-border bg-card px-6">
      <Breadcrumbs />
      <div className="flex shrink-0 items-center gap-1.5">
        <NotificationBell />
        <div className="mx-1 h-6 w-px bg-border" />
        <UserMenu />
      </div>
    </header>
  )
}
