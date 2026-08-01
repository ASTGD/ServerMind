import { useQuery } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"
import { getSiteFacts } from "@/api/sites"

/**
 * The facts you need to work on a site: where its files are, who owns them, which PHP
 * version, how much disk it uses.
 *
 * These are the details someone copies out — into an SFTP client, a `cd`, a chown. So they
 * are shown as selectable monospace text rather than prose, and read LIVE from the server
 * on every visit. A stored path shown for a site that has since moved is worse than no
 * path at all, because someone will act on it.
 *
 * A fact the server could not answer is shown as unknown, never as a plausible default: a
 * static site genuinely has no PHP version, and inventing "8.1" would send someone looking
 * for a config file that does not exist.
 */

function sizeLabel(kb: number): string {
  if (kb >= 1024 * 1024) return `${(kb / 1024 / 1024).toFixed(1)} GB`
  if (kb >= 1024) return `${(kb / 1024).toFixed(1)} MB`
  return `${kb} KB`
}

function Row({ label, value, mono = true }: {
  label: string
  value: string | null | undefined
  mono?: boolean
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-t border-border px-4 py-2.5 first:border-t-0">
      <span className="shrink-0 text-small text-muted-foreground">{label}</span>
      {value ? (
        <span
          className={`min-w-0 truncate text-right text-small text-foreground ${
            mono ? "font-mono" : ""}`}
          title={value}
        >
          {value}
        </span>
      ) : (
        <span className="text-small text-muted-foreground/60">not known</span>
      )}
    </div>
  )
}

export default function SiteInformation({ siteId, sshServer }: {
  siteId: string
  /** Only a Linux server over SSH can be looked at; anything else has nothing to report. */
  sshServer: boolean
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["site-facts", siteId],
    queryFn: () => getSiteFacts(siteId),
    enabled: sshServer,
    // Cheap to re-read and always changing underneath us.
    staleTime: 30_000,
  })

  if (!sshServer) return null

  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="flex items-center gap-2 px-4 py-3">
        <p className="text-sm font-medium text-foreground">Information</p>
        {isLoading && <Loader2 size={12} className="animate-spin text-muted-foreground" />}
      </div>

      {data && !data.reachable ? (
        <p className="border-t border-border px-4 py-3 text-small text-muted-foreground">
          We could not reach the server to look. Check it is online, then reload.
        </p>
      ) : (
        <div className="border-t border-border">
          <Row label="System user" value={data?.system_user} />
          <Row label="Server path" value={data?.server_path} />
          <Row label="Public path" value={data?.public_path} />
          <Row label="PHP version" value={data?.php_version} mono={false} />
          <Row
            label="Size on disk"
            value={data?.size_kb != null ? sizeLabel(data.size_kb) : null}
            mono={false}
          />
        </div>
      )}
    </div>
  )
}
