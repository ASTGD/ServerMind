import { Link, useParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import {
  ArrowLeft, CircleAlert, CircleCheck, CircleDashed, ExternalLink, Loader2,
  ShieldAlert, ShieldCheck,
} from "lucide-react"
import { getSite, APP_LABEL, type SiteDetail as SiteDetailData } from "@/api/sites"
import SiteInstaller from "@/components/sites/SiteInstaller"
import { canInstallOnto, wasCreatedHere } from "@/lib/siteInstall"

/**
 * One site.
 *
 * A site is added by its domain alone, which builds an empty site — so this is where the
 * second half happens: what actually runs on it. The installer belongs here rather than on
 * the Sites list because that is the question you ask about a site you already have, not a
 * question you answer before the site exists.
 *
 * Read fresh by id rather than picked out of the list, so the page works when it is opened
 * from a link or a bookmark.
 */
export default function SiteDetail() {
  const { siteId = "" } = useParams()

  const { data: site, isLoading } = useQuery({
    queryKey: ["site", siteId],
    queryFn: () => getSite(siteId),
    // While something is being installed the answer changes on its own, so the page keeps
    // up rather than making someone reload to find out whether it worked.
    refetchInterval: (q) => (q.state.data?.status === "installing" ? 5000 : false),
  })

  if (isLoading) {
    return (
      <div className="flex justify-center py-16 text-muted-foreground">
        <Loader2 size={20} className="animate-spin" />
      </div>
    )
  }
  if (!site) {
    return <p className="py-16 text-center text-small text-muted-foreground">No such site.</p>
  }

  const installing = site.status === "installing"
  const failed = site.status === "failed"
  const canInstall = canInstallOnto(site)
  const ours = wasCreatedHere(site)

  return (
    <div className="space-y-4">
      <div>
        <Link
          to={`/servers/${site.server.id}/sites`}
          className="inline-flex items-center gap-1 text-caption text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft size={12} /> All sites on {site.server.name}
        </Link>

        <div className="mt-1 flex flex-wrap items-center gap-2">
          <h2 className="text-h2 text-foreground">{site.domain}</h2>
          <a
            href={`http://${site.domain}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-caption text-muted-foreground hover:text-foreground"
          >
            <ExternalLink size={11} /> Open
          </a>
        </div>

        <p className="mt-0.5 flex flex-wrap items-center gap-2 text-small text-muted-foreground">
          <Status site={site} />
          <span>·</span>
          <span>{APP_LABEL[site.app_type] ?? site.app_type}
            {site.app_version ? ` ${site.app_version}` : ""}</span>
          {site.doc_root && <><span>·</span><span className="font-mono text-caption">{site.doc_root}</span></>}
        </p>
      </div>

      {installing && (
        <p className="flex items-center gap-2 rounded-lg border-l-2 border-primary bg-primary/5 px-3 py-2 text-small text-foreground">
          <Loader2 size={13} className="animate-spin text-primary" />
          Setting this up now. It runs on the server — you can leave this page.
        </p>
      )}

      {failed && site.install_error && (
        <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2 text-small text-destructive">
          {site.install_error}
        </p>
      )}

      {/* Only on an empty site ServerAlly made. On a site that was already on the server
          when we found it, this would be offering to replace someone's live website — and
          the server refuses that anyway, so the button would be a promise we cannot keep. */}
      {canInstall && (
        <SiteInstaller
          siteId={site.id}
          serverId={site.server.id}
          panelOnly={!!site.server.panel_type}
        />
      )}

      {!installing && !canInstall && (
        <div className="rounded-xl border border-border bg-card p-4">
          <p className="text-sm font-medium text-foreground">
            {ours
              ? `${APP_LABEL[site.app_type] ?? site.app_type} is installed here`
              : "This site was already on the server"}
          </p>
          <p className="mt-0.5 text-small text-muted-foreground">
            {ours
              ? "To put something else on this domain, remove the site first — replacing it in place would delete whatever is here now."
              : "ServerAlly found it rather than building it, so it is watched and managed from here but not replaced. Ask Ally if you need to change what it runs."}
          </p>
        </div>
      )}
    </div>
  )
}

function Status({ site }: { site: SiteDetailData }) {
  if (site.status === "installing") {
    return <span className="inline-flex items-center gap-1"><Loader2 size={12} className="animate-spin" /> Setting up</span>
  }
  if (site.status === "failed") {
    return <span className="inline-flex items-center gap-1 text-destructive"><CircleAlert size={12} /> Setup failed</span>
  }
  const up = site.uptime?.status
  if (up === "up") {
    return (
      <span className="inline-flex items-center gap-2">
        <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
          <CircleCheck size={12} /> Up
        </span>
        <Cert site={site} />
      </span>
    )
  }
  if (up === "down") {
    return (
      <span className="inline-flex items-center gap-1 text-red-600 dark:text-red-400">
        <CircleAlert size={12} /> Down{site.uptime?.error ? ` — ${site.uptime.error}` : ""}
      </span>
    )
  }
  return <span className="inline-flex items-center gap-1"><CircleDashed size={12} /> Not monitored</span>
}

function Cert({ site }: { site: SiteDetailData }) {
  const days = site.uptime?.cert_days_left
  if (site.uptime?.cert_state === "expired") {
    return <span className="inline-flex items-center gap-1 text-red-600 dark:text-red-400"><ShieldAlert size={11} /> Certificate expired</span>
  }
  if (typeof days === "number") {
    return <span className="inline-flex items-center gap-1"><ShieldCheck size={11} /> HTTPS {days}d</span>
  }
  return null
}
