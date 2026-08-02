import { useState } from "react"
import { Link, useOutletContext } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Flag, Globe, Loader2, RefreshCw, Search, ShieldAlert, ShieldCheck,
} from "lucide-react"
import { getServerRole } from "@/api/servers"
import { listServerSites, scanServerSites, APP_LABEL, type Site } from "@/api/sites"
import { listRecipes } from "@/api/recipes"
import RunRecipeModal from "@/components/recipes/RunRecipeModal"
import AddSiteForm from "@/components/sites/AddSiteForm"
import { Button } from "@/components/ui"
import { installerOptionsFor } from "@/lib/assetMenu"
import { siteDetail, siteState, siteStatusLabel, siteTone } from "@/lib/siteStatus"
import { cn } from "@/lib/utils"
import type { Server } from "@/types"

/**
 * The sites on one server — and the place to put a new one there.
 *
 * This is the section an owner opens first, because a server exists to serve something.
 * It answers three questions per site in one line: is it up, is its certificate valid, and
 * what is it running.
 *
 * Creating a site hands the job to Ally rather than templating a vhost ourselves. A
 * competitor can fill in a stored template because they built the machine and know its
 * exact state; we are looking at a real server that may have anything on it, so the right
 * move is to look first and then decide — which is what the runbook does.
 */
export default function ServerSites() {
  const { server } = useOutletContext<{ server: Server }>()
  const qc = useQueryClient()
  //: The Ally route, which takes over the card while it runs.
  const [creating, setCreating] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ["server-sites", server.id],
    queryFn: () => listServerSites(server.id),
  })

  const scan = useMutation({
    mutationFn: () => scanServerSites(server.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["server-sites", server.id] })
      qc.invalidateQueries({ queryKey: ["sites"] })
    },
  })

  // Which runbook applies is the server's decision, not ours: a panel server and a plain
  // server answer "host a website" with different procedures.
  const { data: recipes = [] } = useQuery({
    queryKey: ["recipes", server.id],
    queryFn: () => listRecipes(null, server.id),
  })
  const siteRecipe = recipes.find((r) => r.slug.includes("host-website"))

  // The two deterministic installers. Fetched by slug so the button knows whether the
  // installer exists on this deployment before offering it.

  // The same question Start here asks, from the same cached query. A site created before
  // it is answered either fails at the installer or answers it silently — see the two
  // branches below.
  const { data: role } = useQuery({
    queryKey: ["server-role", server.id],
    queryFn: () => getServerRole(server.id),
    enabled: server.connection_type === "ssh",
  })
  const undecided = !!role?.applies && role.role === "undecided" && role.can_choose
  // Not "undecided" — "cannot serve anything yet". A machine somebody put nginx on can
  // host a site perfectly well, whether or not they have answered the bigger question.
  const notReadyYet = undecided && role?.found != null
    && (role.found.web_servers ?? []).length === 0

  const doors = installerOptionsFor(server)
  const sites = data?.sites ?? []
  // An empty server has nothing to look at, so it opens straight into the form.
  // The New site card is always on the page, the way the list is. It used to be behind a
  // button, which put a click in front of the one thing this section exists to do.
  const showForm = !creating
  // The server cannot be looked at, so everything below is the last thing we saw rather
  // than the current truth. Without saying so the page showed four sites from a server
  // that had been wiped, each with a confident reason for being down.
  const stale = data?.stale_because ?? null
  // Same split as the fleet page: a setup that never finished is not an outage.
  const unfinished = sites.filter((s) => siteState(s) === "failed").length
  const unpointed = sites.filter((s) => siteState(s) === "unpointed").length
  const down = sites.filter(
    (s) => !["failed", "unpointed"].includes(siteState(s))
      && s.uptime?.status === "down").length

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="flex items-center gap-2 text-[17px] font-medium text-foreground">
            <Globe size={16} className="text-primary" /> Sites
          </h2>
          {/* What this server can serve WITH, before what it serves. Built only from data
              already loaded — reading the real stack (nginx, PHP version, database) needs a
              live SSH probe, and this is the page you open most, so it does not pay for one.
              Installed does that job, one click away. */}
          <p className="mt-0.5 text-sm text-muted-foreground">
            {[
              server.os_version ? `${server.os_type} ${server.os_version}` : server.os_type,
              server.panel_type,
            ].filter(Boolean).join(" · ")}
            {(server.os_type || server.panel_type) && " — "}
            {sites.length === 0
              ? "nothing hosted here yet"
              : `${sites.length} site${sites.length === 1 ? "" : "s"}`}
            {down > 0 && !stale && (
              <span className="ml-1 font-medium text-red-600 dark:text-red-400">
                · {down} down
              </span>
            )}
            {unfinished > 0 && !stale && (
              <span className="ml-1 font-medium text-red-600 dark:text-red-400">
                · {unfinished} unfinished
              </span>
            )}
            {unpointed > 0 && !stale && (
              <span className="ml-1">· {unpointed} not pointed here yet</span>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={scan.isPending}
            onClick={() => scan.mutate()}>
            {scan.isPending
              ? <Loader2 size={13} className="animate-spin" />
              : <RefreshCw size={13} />}
            Look for sites
          </Button>
        </div>
      </div>

      {scan.data && (
        <p className="rounded-lg bg-muted/50 px-3 py-2 text-[12.5px] text-foreground">
          Found {scan.data.found} site{scan.data.found === 1 ? "" : "s"}
          {scan.data.added > 0 && `, ${scan.data.added} new`}.
        </p>
      )}

      {stale && sites.length > 0 && (
        <p className="rounded-lg border-l-2 border-amber-500 bg-amber-500/5 px-3 py-2 text-small text-foreground">
          {stale === "host_changed"
            ? "This server's identity changed, so we cannot look at it. "
            : stale === "auth_failed"
              ? "We cannot sign in to this server at the moment. "
              : "This server is not answering. "}
          What is listed below is the last thing we saw — it may no longer be true.
        </p>
      )}

      {/* A server that has not answered the Start-here question, and has no web server on
          it, cannot host anything yet. Offering the domain form here invites somebody into
          a dead end: they type a domain, press Create, wait, and the installer tells them
          to go and set the server up. Say that first instead, and keep the one button that
          IS useful — a server added with websites already on it needs finding, not setting
          up, and that scan is what makes it answer the question by itself. */}
      {showForm && notReadyYet && (
        <section className="grid overflow-hidden rounded-xl border border-border bg-card sm:grid-cols-[minmax(0,280px)_minmax(0,1fr)]">
          <div className="p-5 sm:pr-6">
            <h3 className="text-sm font-medium text-foreground">New site</h3>
            <p className="mt-1 text-caption text-muted-foreground">
              Nothing can be hosted here yet.
            </p>
          </div>
          <div className="p-5 sm:pl-0">
            <div className="flex items-start gap-3 rounded-lg border border-border p-3">
              <Flag size={15} className="mt-0.5 shrink-0 text-primary" />
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground">
                  Choose how this server runs first
                </p>
                <p className="mt-0.5 text-small text-muted-foreground">
                  This server has no web server on it, so a site created now would have
                  nothing to serve it. Start here decides whether ServerAlly sets it up, or
                  a control panel does.
                </p>
                <Link to={`/servers/${server.id}`} className="mt-2 inline-block">
                  <Button size="sm"><Flag size={13} /> Start here</Button>
                </Link>
              </div>
            </div>
            {sites.length === 0 && !scan.data && (
              <p className="mt-3 text-caption text-muted-foreground">
                Already have websites on this server?{" "}
                <button type="button" onClick={() => scan.mutate()}
                  className="inline-flex items-center gap-1 font-medium text-foreground underline-offset-2 hover:underline">
                  <Search size={11} /> Look for them
                </button>{" "}
                — ServerAlly reads the web server's own configuration and lists what is there.
              </p>
            )}
          </div>
        </section>
      )}

      {showForm && !notReadyYet && (
        <>
          {/* It CAN host — somebody installed a web server themselves. Creating a site is
              allowed, and it is also the answer to the Start-here question, so it says so
              rather than deciding quietly on the customer's behalf. */}
          {undecided && (
            <p className="rounded-lg border-l-2 border-primary bg-primary/5 px-3 py-2 text-small text-foreground">
              Adding a site here makes <span className="font-medium">ServerAlly the control
              panel</span> for this server. If you meant to install cPanel or CyberPanel on
              it instead,{" "}
              <Link to={`/servers/${server.id}`} className="font-medium underline underline-offset-2">
                choose that first
              </Link>{" "}
              — afterwards it needs the server rebuilt.
            </p>
          )}
          <AddSiteForm
            serverId={server.id}
            // A panel owns its own sites, so nothing can be written behind its back.
            panelOnly={!doors.direct}
            onAsk={doors.ally && siteRecipe ? () => setCreating(true) : undefined}
            // Only worth offering when there is nothing listed — that is the moment someone
            // has connected a server whose sites we have not looked for yet.
            showFind={sites.length === 0 && !scan.data}
            onFind={() => scan.mutate()}
          />
        </>
      )}

      {creating && siteRecipe && (
        <div className="rounded-xl border border-border bg-card p-3">
          <p className="mb-3 text-[12.5px] text-muted-foreground">
            Ally will look at this server first and use the right method for it — a control
            panel is driven through the panel, a plain server gets its web server configured
            directly.
          </p>
          <RunRecipeModal recipe={siteRecipe} onClose={() => setCreating(false)} />
        </div>
      )}

      {/* This page is the sites on this server and the way to add one — nothing else. The
          list used to be hidden whenever the form was showing, which was fine while the
          form was something a button revealed; now that the card is always here, that
          hid every site on the server. */}
      {!isLoading && sites.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          {sites.map((s) => <SiteRow key={s.id} site={s} serverId={server.id} />)}
        </div>
      )}

      {isLoading && (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-14 animate-pulse border-t border-border first:border-t-0" />
          ))}
        </div>
      )}
    </div>
  )
}

/** Up/down comes from the uptime monitor, which checks from outside — where a visitor is. */
function ToneDot({ site }: { site: Site }) {
  const tone = siteTone(site)
  return (
    <span title={siteStatusLabel(site)} className={cn(
      "size-2 shrink-0 rounded-full",
      tone === "bad" ? "bg-red-500"
        : tone === "good" ? "bg-emerald-500"
          : "bg-muted-foreground/40",
    )} />
  )
}

/** The certificate a visitor actually receives, not the one named in the config. */
function CertChip({ site }: { site: Site }) {
  const days = site.uptime?.cert_days_left
  const state = site.uptime?.cert_state
  if (state === "expired") {
    return (
      <span className="flex items-center gap-1 rounded-full bg-red-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-red-700 dark:text-red-300">
        <ShieldAlert size={9} /> Certificate expired
      </span>
    )
  }
  if (typeof days === "number" && days <= 14) {
    return (
      <span className="flex items-center gap-1 rounded-full bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:text-amber-300">
        <ShieldAlert size={9} /> HTTPS expires in {days}d
      </span>
    )
  }
  if (typeof days === "number") {
    return (
      <span className="flex items-center gap-1 text-[10.5px] text-muted-foreground">
        <ShieldCheck size={9} /> {days}d
      </span>
    )
  }
  if (site.has_ssl) {
    return (
      <span className="flex items-center gap-1 text-[10.5px] text-muted-foreground"
        title="The server is configured for HTTPS. Add an uptime monitor to track expiry.">
        <ShieldCheck size={9} /> HTTPS set up
      </span>
    )
  }
  return null
}

function SiteRow({ site, serverId }: { site: Site; serverId: string }) {
  const state = siteState(site)
  const detail = siteDetail(site)
  const tone = siteTone(site)
  const to = `/servers/${serverId}/sites/${site.id}`

  return (
    <div className={cn(
      "group flex items-center gap-4 border-t border-border px-4 py-3 first:border-t-0",
      "transition-colors hover:bg-accent/50",
      state === "absent" && "opacity-60",
    )}>
      <ToneDot site={site} />

      {/* What it is. The domain leads, because that is what somebody is looking for. */}
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2">
          <Link to={to}
            className="truncate text-[14px] font-medium text-foreground hover:underline">
            {site.domain}
          </Link>
          <CertChip site={site} />
        </p>
        <p className="truncate text-caption text-muted-foreground">
          {APP_LABEL[site.app_type] ?? site.app_type}
          {site.app_version ? ` ${site.app_version}` : ""}
          {site.doc_root ? ` · ${site.doc_root}` : ""}
        </p>
      </div>

      {/* Where it stands. Its own column, so a healthy row says "Up" rather than saying
          nothing — silence read equally as fine, never checked, and no idea. */}
      <div className="hidden w-[260px] shrink-0 text-right sm:block">
        <p className={cn("text-small font-medium",
          tone === "bad" ? "text-red-600 dark:text-red-400"
            : tone === "good" ? "text-emerald-600 dark:text-emerald-400"
              : "text-muted-foreground")}>
          {siteStatusLabel(site)}
        </p>
        {/* Wrapped rather than truncated: the reason a setup failed is the most useful
            sentence on the row, and "no web server is running on this …" is not it. */}
        {detail && (
          <p className="line-clamp-2 text-caption text-muted-foreground" title={detail}>
            {detail}
          </p>
        )}
      </div>

      {/* Somewhere to go. The whole row used to be a link with nothing saying so. */}
      <Link to={to}
        className={cn(
          "shrink-0 rounded-lg border border-border px-2.5 py-1 text-caption font-medium",
          "text-muted-foreground transition-colors",
          "hover:border-primary/40 hover:bg-primary/5 hover:text-foreground",
        )}>
        View
      </Link>
    </div>
  )
}

