import { Info } from "lucide-react"
import type { SiteApp } from "@/api/sites"

/**
 * What PHP this site actually runs under.
 *
 * The smallest section, and read-only on purpose. There is no framework here to administer,
 * so the one thing worth showing is the set of limits that decide whether the site works —
 * because they are set per POOL, and the server's PHP page reports the server default. When
 * somebody is looking at this screen it is usually because an upload failed or a page ran
 * out of memory, and those numbers are the answer.
 *
 * No buttons: changing a pool limit changes it for every site sharing that pool, which
 * belongs to the server's screen, not to one site's page.
 */
export default function PhpPanel({ data }: { data: SiteApp }) {
  const settings = data.settings ?? []
  const extensions = data.extensions ?? []
  // Worth surfacing rather than leaving for someone to spot: the shell's PHP is not
  // necessarily the site's, and when they differ that IS the answer to "it works when I run
  // it by hand".
  const differs = !!data.cli_version && !!data.version
    && data.cli_version.split(".").slice(0, 2).join(".")
       !== data.version.split(".").slice(0, 2).join(".")

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border bg-card px-4 py-3">
        <p className="text-sm font-medium text-foreground">PHP {data.version}</p>
        <p className="mt-0.5 text-small text-muted-foreground">
          What this site's own pages actually run under
          {data.sapi && <> ({data.sapi})</>}. Read by asking the site itself, not the
          command line.
        </p>
        {differs && (
          <p className="mt-2 rounded-lg border-l-2 border-amber-500 bg-amber-500/5 px-3 py-2 text-small text-foreground">
            The command line on this server uses PHP {data.cli_version}, which is a different
            version from the one serving this site. A script that works when you run it by
            hand can still fail as a web page.
          </p>
        )}
      </div>

      <div className="rounded-xl border border-border bg-card">
        <div className="border-b border-border px-4 py-3">
          <p className="text-sm font-medium text-foreground">Limits</p>
          <p className="mt-0.5 text-caption text-muted-foreground">
            These are the settings behind most "it just stops" problems.
          </p>
        </div>
        {settings.map((s) => (
          <div key={s.name}
               className="flex items-baseline justify-between gap-4 border-t border-border px-4 py-2.5 first:border-t-0">
            <div className="min-w-0">
              <p className="text-small text-foreground">{s.label}</p>
              <p className="text-caption font-mono text-muted-foreground">{s.name}</p>
            </div>
            <span className="shrink-0 font-mono text-small text-foreground">{s.value}</span>
          </div>
        ))}
      </div>

      {extensions.length > 0 && (
        <div className="rounded-xl border border-border bg-card">
          <div className="flex items-center gap-2 border-b border-border px-4 py-3">
            <Info size={14} className="text-muted-foreground" />
            <p className="text-sm font-medium text-foreground">
              Extensions <span className="text-muted-foreground">({extensions.length})</span>
            </p>
            <p className="text-caption text-muted-foreground">
              What this site can do. An application asking for a missing one will not start.
            </p>
          </div>
          <div className="flex flex-wrap gap-1.5 px-4 py-3">
            {extensions.map((e) => (
              <span key={e}
                    className="rounded bg-muted px-1.5 py-0.5 font-mono text-caption text-muted-foreground">
                {e}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
