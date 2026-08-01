import { useOutletContext } from "react-router-dom"
import { Loader2 } from "lucide-react"
import { APP_LABEL, type SiteDetail } from "@/api/sites"
import SiteInstaller from "@/components/sites/SiteInstaller"
import SiteHttps from "@/components/sites/SiteHttps"
import { canInstallOnto, wasCreatedHere } from "@/lib/siteInstall"

/**
 * What this site is, and the one thing it most likely still needs.
 *
 * An empty site needs something installed; a live one usually needs HTTPS. Both are here
 * rather than behind a menu item, because on the day you arrive they are the reason you
 * came. Everything else about the site has its own tab.
 */
export default function SiteOverview() {
  const { site } = useOutletContext<{ site: SiteDetail }>()

  const installing = site.status === "installing"
  const canInstall = canInstallOnto(site)
  const ours = wasCreatedHere(site)

  return (
    <div className="space-y-4">
      {installing && (
        <p className="flex items-center gap-2 rounded-lg border-l-2 border-primary bg-primary/5 px-3 py-2 text-small text-foreground">
          <Loader2 size={13} className="animate-spin text-primary" />
          Setting this up now. It runs on the server — you can leave this page.
        </p>
      )}

      {site.status === "failed" && site.install_error && (
        <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2 text-small text-destructive">
          {site.install_error}
        </p>
      )}

      {/* Only on an empty site ServerAlly made. On one that was already on the server this
          would be offering to replace somebody's live website — and the server refuses that
          anyway, so the button would be a promise we cannot keep. */}
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

      {!installing && site.server.connection_type === "ssh" && !site.server.panel_type && (
        <SiteHttps siteId={site.id} domain={site.domain} hasSsl={site.has_ssl} />
      )}
    </div>
  )
}
