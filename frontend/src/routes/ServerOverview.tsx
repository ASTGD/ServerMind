import { useOutletContext } from "react-router-dom"
import ServerMetrics from "@/components/server/ServerMetrics"
import InstalledWidget from "@/components/server/widgets/InstalledWidget"
import SecurityWidget from "@/components/server/widgets/SecurityWidget"
import BackupsWidget from "@/components/server/widgets/BackupsWidget"
import SchedulerWidget from "@/components/server/widgets/SchedulerWidget"
import RecentActivityWidget from "@/components/server/widgets/RecentActivityWidget"
import MemoryWidget from "@/components/server/widgets/MemoryWidget"
import type { Server } from "@/types"

/** The default tab of the server hub — a read-only dashboard of widgets. The server is
 * provided by the ServerDetail shell via the router outlet context. */
export default function ServerOverview() {
  const { server } = useOutletContext<{ server: Server }>()

  // A Windows (RDP) / WinRM asset has no command channel to auto-detect OS, but it IS
  // Windows by definition — show that instead of a bare "—".
  const isWindows = server.connection_type === "rdp" || server.connection_type === "winrm"
  const osValue = server.os_type
    ? `${server.os_type}${server.os_version ? ` ${server.os_version}` : ""}`
    : isWindows ? "Windows" : "—"

  const info: { label: string; value: string }[] = [
    { label: "OS", value: osValue },
    { label: "Architecture", value: server.arch ?? "—" },
    { label: "Shell", value: server.shell },
    { label: "Connection", value: server.connection_type.toUpperCase() },
    { label: "Host", value: server.host },
    { label: "Port", value: String(server.port) },
    { label: "Username", value: server.username },
    { label: "Auth", value: server.auth_type },
  ]

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="mb-3 text-sm font-medium text-foreground">Server info</h3>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm sm:grid-cols-4">
            {info.map((f) => (
              <div key={f.label}>
                <dt className="text-xs text-muted-foreground">{f.label}</dt>
                <dd className="truncate font-mono capitalize text-foreground">{f.value}</dd>
              </div>
            ))}
          </dl>
        </div>

        <InstalledWidget serverId={server.id} />
        <RecentActivityWidget serverId={server.id} />

        {server.notes && (
          <div className="rounded-lg border border-border bg-card p-4">
            <h3 className="mb-2 text-sm font-medium text-foreground">Notes</h3>
            <p className="whitespace-pre-wrap text-sm text-muted-foreground">{server.notes}</p>
          </div>
        )}

        {server.tags && server.tags.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {server.tags.map((tag) => (
              <span
                key={tag}
                className="rounded-full border border-border px-3 py-0.5 text-xs text-muted-foreground"
              >
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-4">
        <ServerMetrics serverId={server.id} />
        <SecurityWidget serverId={server.id} />
        <BackupsWidget serverId={server.id} />
        <SchedulerWidget serverId={server.id} />
        <MemoryWidget serverId={server.id} />
      </div>
    </div>
  )
}
