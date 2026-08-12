import { useState } from "react"
import { useOutletContext } from "react-router-dom"
import { Loader2, RefreshCw, Sparkles } from "lucide-react"
import { APP_LABEL, type SiteDetail } from "@/api/sites"
import PromoteToLive from "@/components/sites/PromoteToLive"
import SiteCode from "@/components/sites/SiteCode"
import SiteInstaller from "@/components/sites/SiteInstaller"
import SiteHttps from "@/components/sites/SiteHttps"
import SiteInformation from "@/components/sites/SiteInformation"
import { Button } from "@/components/ui"
import { canInstallOnto, wasCreatedHere } from "@/lib/siteInstall"

/**
 * The site's home: what is on it, how code gets onto it, and what it still needs.
 *
 * It used to be three boxes of which two were warnings, and on a site that already ran
 * something the whole page was one sentence saying what could NOT be done — a dead page on
 * the first screen anyone opens. The two things a site exists for, getting code onto it and
 * choosing what runs on it, were both somewhere else.
 *
 * So both are here now. Deploying is always offered, because deploying a new version of an
 * app that is already installed is the ordinary case. Installing is offered too, but on an
 * occupied site it is honestly named: it starts the site over, and it says so before
 * anything is pressed rather than failing at the server with a guard message.
 */
export default function SiteOverview() {
  const { site } = useOutletContext<{ site: SiteDetail }>()
  const [replacing, setReplacing] = useState(false)

  const installing = site.status === "installing"
  const canInstall = canInstallOnto(site)
  const ours = wasCreatedHere(site)
  const manageable = site.server.connection_type === "ssh" && !site.server.panel_type
  // Only a site we built. One we merely found could be laid out any way, with content
  // nobody has a copy of — the server refuses it too, so offering it would be a promise we
  // cannot keep, aimed at exactly the sites where being wrong costs the most.
  const canReplace = manageable && ours && !canInstall && !installing

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

      {/* First, on a staging copy only: the reason that copy exists. Renders nothing at all
          on an ordinary site, so it costs the other screens nothing. */}
      {!installing && <PromoteToLive site={site} />}

      {/* An empty site: the plain chooser, no warnings, nothing to lose. */}
      {canInstall && (
        <SiteInstaller
          siteId={site.id}
          serverId={site.server.id}
          panelOnly={!!site.server.panel_type}
        />
      )}

      {/* What is running, and the way to change it. Not a dead end any more. */}
      {!installing && !canInstall && (
        replacing ? (
          <div className="space-y-2">
            <SiteInstaller
              siteId={site.id}
              serverId={site.server.id}
              panelOnly={!!site.server.panel_type}
              replacing
              domain={site.domain}
            />
            <button type="button" onClick={() => setReplacing(false)}
              className="text-caption text-muted-foreground underline-offset-2 hover:text-foreground hover:underline">
              Leave it as it is
            </button>
          </div>
        ) : (
          <section className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-border bg-card p-4">
            <div className="min-w-0">
              <p className="text-sm font-medium text-foreground">
                {ours
                  ? `${APP_LABEL[site.app_type] ?? site.app_type} is installed here`
                  : "This site was already on the server"}
                {site.app_version ? ` · ${site.app_version}` : ""}
              </p>
              <p className="mt-0.5 text-small text-muted-foreground">
                {ours
                  ? "Update it by deploying, or start the site over with something else."
                  : "ServerAlly found it rather than building it, so it is watched and managed "
                    + "from here but never replaced — we do not know how it was put together. "
                    + "Ask Ally if you need to change what it runs."}
              </p>
            </div>
            {canReplace ? (
              <Button variant="outline" size="sm" onClick={() => setReplacing(true)}>
                <RefreshCw size={13} /> Start over
              </Button>
            ) : !ours ? (
              <span className="inline-flex items-center gap-1.5 text-caption text-muted-foreground">
                <Sparkles size={13} className="text-primary" /> Ask Ally
              </span>
            ) : null}
          </section>
        )
      )}

      {/* Always, installed or not: a new version of what is already here is the normal
          reason anyone opens a site. */}
      {!installing && <SiteCode site={site} />}

      {!installing && manageable && (
        <SiteHttps siteId={site.id} domain={site.domain} hasSsl={site.has_ssl} />
      )}

      <SiteInformation
        siteId={site.id}
        sshServer={site.server.connection_type === "ssh"}
      />
    </div>
  )
}
