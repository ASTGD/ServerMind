import { useParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { CircleCheck, CircleAlert, CircleDashed, Loader2, ExternalLink } from "lucide-react"
import { getPublicStatus, type PublicStatus } from "@/api/statusPages"
import { LogoMark } from "@/components/brand/Logo"

/**
 * The PUBLIC status page — rendered for strangers, outside the authenticated app.
 *
 * It shows only what the API sends, which is an allowlist by design: a display name,
 * up/down, uptime numbers and a daily bar. No URLs, no server names, no error text.
 */
function tone(status: PublicStatus["status"]) {
  if (status === "up")
    return { text: "text-emerald-700 dark:text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/30" }
  if (status === "down")
    return { text: "text-red-700 dark:text-red-400", bg: "bg-red-500/10", border: "border-red-500/30" }
  return { text: "text-muted-foreground", bg: "bg-muted", border: "border-border" }
}

function StatusIcon({ status, size = 18 }: { status: PublicStatus["status"]; size?: number }) {
  if (status === "up") return <CircleCheck size={size} className="shrink-0 text-emerald-600 dark:text-emerald-400" />
  if (status === "down") return <CircleAlert size={size} className="shrink-0 text-red-600 dark:text-red-400" />
  return <CircleDashed size={size} className="shrink-0 text-muted-foreground" />
}

/** The 30-day bar. A day with no data is a gap, not an outage. */
function HistoryBar({ history }: { history: { date: string; status: string }[] }) {
  return (
    <div className="flex items-end gap-[2px]" aria-hidden="true">
      {history.map((d) => (
        <span
          key={d.date}
          title={`${d.date}: ${d.status === "none" ? "no data" : d.status}`}
          className={`h-6 w-[6px] rounded-sm ${
            d.status === "up"
              ? "bg-emerald-500/70"
              : d.status === "down"
                ? "bg-red-500/80"
                : "bg-muted"
          }`}
        />
      ))}
    </div>
  )
}

export default function PublicStatusPage() {
  const { slug = "" } = useParams()
  const { data, isLoading, isError } = useQuery({
    queryKey: ["public-status", slug],
    queryFn: () => getPublicStatus(slug),
    refetchInterval: 60_000,
    retry: false,
  })

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-6">
        <div className="text-center">
          <h1 className="text-h2 text-foreground">No status page here</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            This address does not have a published status page.
          </p>
        </div>
      </div>
    )
  }

  const t = tone(data.status)
  const brand = data.branding
  // The owner's colour, when set, tints the headings a client sees.
  const brandColor = brand?.primary_color || undefined

  return (
    <div className="min-h-screen bg-background px-4 py-10 sm:px-6">
      <div className="mx-auto w-full max-w-2xl">
        <header className="mb-6">
          {(brand?.logo_url || brand?.company_name) && (
            <div className="mb-3 flex items-center gap-2">
              {brand.logo_url && (
                <img src={brand.logo_url} alt="" className="h-7 w-auto max-w-[160px] object-contain"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = "none" }} />
              )}
              {brand.company_name && (
                <span className="text-sm font-semibold" style={{ color: brandColor }}>
                  {brand.company_name}
                </span>
              )}
            </div>
          )}
          <h1 className="text-h1 text-foreground">{data.title}</h1>
          {data.description && (
            <p className="mt-1 text-sm text-muted-foreground">{data.description}</p>
          )}
        </header>

        {/* The headline a visitor came for. */}
        <div className={`mb-6 flex items-center gap-3 rounded-xl border px-4 py-3.5 ${t.bg} ${t.border}`}>
          <StatusIcon status={data.status} size={20} />
          <span className={`text-[15px] font-medium ${t.text}`}>{data.message}</span>
        </div>

        {data.items.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
            Nothing is being reported on this page yet.
          </div>
        ) : (
          <ul className="space-y-2">
            {data.items.map((item) => (
              <li key={item.name} className="rounded-xl border border-border bg-card p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="flex items-center gap-2">
                    <StatusIcon status={item.status} />
                    <span className="text-sm font-medium">{item.name}</span>
                  </span>
                  <span className={`text-xs font-medium ${tone(item.status).text}`}>
                    {item.status === "up" ? "Operational" : item.status === "down" ? "Down" : "Checking"}
                  </span>
                </div>
                <div className="mt-3">
                  <HistoryBar history={item.history} />
                  <div className="mt-1.5 flex items-center justify-between text-[11px] text-muted-foreground">
                    <span>{data.history_days} days ago</span>
                    <span>{item.uptime_window}% uptime</span>
                    <span>today</span>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}

        <footer className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
          <span className="text-[11px] text-muted-foreground">
            Updated {new Date(data.checked_at).toLocaleString()}
          </span>
          <span className="flex items-center gap-3">
            {(data.support_url || brand?.support_url) && (
              <a
                href={data.support_url || brand?.support_url || "#"}
                className="inline-flex items-center gap-1 text-[11px] text-muted-foreground underline hover:text-foreground"
              >
                Get help <ExternalLink size={10} />
              </a>
            )}
            {brand?.footer_text && (
              <span className="text-[11px] text-muted-foreground">{brand.footer_text}</span>
            )}
            {/* White-label: the owner can remove our credit entirely. */}
            {brand?.show_credit !== false && (
              <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                Monitored by <LogoMark size={13} /> {brand?.app_name || "ServerAlly"}
              </span>
            )}
          </span>
        </footer>
      </div>
    </div>
  )
}
