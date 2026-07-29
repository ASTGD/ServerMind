import { Link, NavLink } from "react-router-dom"
import { ArrowLeft } from "lucide-react"
import type { Server } from "@/types"
import { categoryForServer } from "@/lib/assetCategories"
import { menuFor, type MenuItem } from "@/lib/assetMenu"
import { cn } from "@/lib/utils"

/**
 * The asset's own menu.
 *
 * Deliberately NOT a second full-height sidebar glued to the app navigation — that reads as
 * one wide two-tone rail and leaves you unsure which level you are on. This is a card that
 * lives *inside* the page: indented, its own rounded surface, starting below the page header
 * and ending where its content ends. Secondary by shape, not by colour alone.
 */

const GROUP_LABEL: Record<MenuItem["group"], string> = {
  manage: "",
  operate: "Operate",
  account: "",
}

function statusText(server: Server) {
  switch (server.status) {
    case "online": return "Online"
    case "offline": return "Offline"
    case "auth_failed": return "Sign-in failing"
    case "host_changed": return "Identity changed"
    default: return "Not checked yet"
  }
}

function statusDot(server: Server) {
  if (server.status === "online") return "bg-emerald-500"
  if (server.status === "offline") return "bg-red-500"
  if (server.status === "auth_failed" || server.status === "host_changed") return "bg-red-500"
  return "bg-muted-foreground/40"
}

export default function AssetSidebar({ server }: { server: Server }) {
  const items = menuFor(server)
  const cat = categoryForServer(server)

  // Only render a group heading where there is a group above it to separate from.
  const groups: MenuItem["group"][] = ["manage", "operate", "account"]

  return (
    <aside className="w-full shrink-0 md:w-56">
      <div className="rounded-xl border border-border bg-card p-3">
        <Link
          to="/servers"
          className="mb-3 flex items-center gap-1.5 text-[12px] text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft size={13} /> All assets
        </Link>

        <p className="truncate text-[15px] font-medium text-foreground" title={server.name}>
          {server.name}
        </p>
        <p className="mt-0.5 flex items-center gap-1.5 text-[11.5px] text-muted-foreground">
          <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", statusDot(server))} />
          {statusText(server)} · {cat.label}
        </p>

        <nav className="mt-3 border-t border-border pt-2">
          {groups.map((group) => {
            const inGroup = items.filter((i) => i.group === group)
            if (!inGroup.length) return null
            return (
              <div key={group} className="mb-1 last:mb-0">
                {GROUP_LABEL[group] && (
                  <p className="mb-1 mt-2 px-2 text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground/70">
                    {GROUP_LABEL[group]}
                  </p>
                )}
                {inGroup.map((item) => (
                  <NavLink
                    key={item.path}
                    to={item.path ? `/servers/${server.id}/${item.path}` : `/servers/${server.id}`}
                    end={item.path === ""}
                    className={({ isActive }) => cn(
                      "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-[13px] transition-colors",
                      isActive
                        ? "bg-primary/10 font-medium text-primary"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    <item.icon size={14} className="shrink-0" />
                    <span className="truncate">{item.label}</span>
                  </NavLink>
                ))}
              </div>
            )
          })}
        </nav>

        {/* Facts, not links — what am I looking at, without a click. */}
        <dl className="mt-3 space-y-1 border-t border-border pt-2.5 text-[11.5px]">
          <Fact label="Address" value={`${server.host}:${server.port}`} />
          {server.os_type && (
            <Fact label="OS" value={server.os_version ? `${server.os_type} ${server.os_version}` : server.os_type} />
          )}
          {server.panel_type && <Fact label="Panel" value={server.panel_type} />}
          {server.arch && <Fact label="Arch" value={server.arch} />}
        </dl>
      </div>
    </aside>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="truncate text-right text-foreground" title={value}>{value}</dd>
    </div>
  )
}
