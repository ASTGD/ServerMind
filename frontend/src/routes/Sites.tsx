import { useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Globe, Search, Loader2, RefreshCw, CircleCheck, CircleAlert, CircleDashed,
  ShieldCheck, ShieldAlert, Server as ServerIcon, Sparkles, EyeOff, Plus,
  Mail, MailWarning,
} from "lucide-react"
import {
  listSites, scanServerSites, addSite, watchSites, APP_LABEL, type Site,
} from "@/api/sites"
import RunRecipeModal from "@/components/recipes/RunRecipeModal"
import { listRecipes } from "@/api/recipes"
import { listServers } from "@/api/servers"
import { checkMailNow, watchMail } from "@/api/mail"
import { Button, EmptyState } from "@/components/ui"
import { useAssistantStore } from "@/store/assistantStore"
import { siteLooksBroken, siteProblem, siteState } from "@/lib/siteStatus"
import { cn } from "@/lib/utils"

/** Up/down comes from the uptime monitor, which checks from outside — where a visitor is. */
function StatusDot({ site }: { site: Site }) {
  const status = site.uptime?.status
  if (!site.uptime)
    return (
      <span title="No uptime monitor for this site yet">
        <CircleDashed size={15} className="shrink-0 text-muted-foreground/60" />
      </span>
    )
  if (status === "up")
    return <CircleCheck size={15} className="shrink-0 text-emerald-600 dark:text-emerald-400" />
  if (status === "down")
    return <CircleAlert size={15} className="shrink-0 text-red-600 dark:text-red-400" />
  return <CircleDashed size={15} className="shrink-0 text-muted-foreground" />
}

/** The certificate a visitor actually receives, not the one named in the config. */
function CertChip({ site }: { site: Site }) {
  const days = site.uptime?.cert_days_left
  const state = site.uptime?.cert_state
  if (state === "expired")
    return (
      <span className="flex items-center gap-1 rounded-full bg-red-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-red-700 dark:text-red-300">
        <ShieldAlert size={9} /> Certificate expired
      </span>
    )
  if (typeof days === "number" && days <= 14)
    return (
      <span className="flex items-center gap-1 rounded-full bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:text-amber-300">
        <ShieldAlert size={9} /> HTTPS expires in {days}d
      </span>
    )
  if (typeof days === "number")
    return (
      <span className="flex items-center gap-1 text-[10.5px] text-muted-foreground">
        <ShieldCheck size={9} /> {days}d
      </span>
    )
  if (site.has_ssl)
    return (
      <span className="flex items-center gap-1 text-[10.5px] text-muted-foreground"
        title="The server is configured for HTTPS. Add an uptime monitor to track expiry.">
        <ShieldCheck size={9} /> HTTPS set up
      </span>
    )
  return null
}

/**
 * Whether this domain's email will actually arrive.
 *
 * Deliberately quiet when it is fine: an agency with fifty healthy domains should see
 * fifty calm rows, so only a real problem earns colour. "Not checked yet" is shown as
 * exactly that — never as a pass.
 */
function MailChip({ site, onClick }: { site: Site; onClick: () => void }) {
  const mail = site.mail
  if (!mail) return null
  if (!mail.checked)
    return (
      <span className="flex items-center gap-1 text-[10.5px] text-muted-foreground">
        <Loader2 size={9} className="animate-spin" /> Checking email…
      </span>
    )
  const base = "flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold"
  if (mail.verdict === "failing")
    return (
      <button onClick={onClick} className={cn(base, "bg-red-500/15 text-red-700 dark:text-red-300")}>
        <MailWarning size={9} /> Email failing
      </button>
    )
  if (mail.verdict === "at risk")
    return (
      <button onClick={onClick}
        className={cn(base, "bg-amber-500/15 text-amber-700 dark:text-amber-300")}>
        <MailWarning size={9} /> Email at risk
      </button>
    )
  return (
    <button onClick={onClick}
      className="flex items-center gap-1 text-[10.5px] text-muted-foreground hover:text-foreground">
      <Mail size={9} /> Email {mail.score}/100
    </button>
  )
}

const SEVERITY: Record<string, string> = {
  critical: "text-red-600 dark:text-red-400",
  warning: "text-amber-600 dark:text-amber-400",
  info: "text-muted-foreground",
}

/** What is wrong and what to do about it — the fix matters more than the finding. */
function MailFindings({ site, onClose }: { site: Site; onClose: () => void }) {
  const qc = useQueryClient()
  const mail = site.mail!
  const recheck = useMutation({
    mutationFn: () => checkMailNow(mail.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sites"] }),
  })
  return (
    <div className="mt-2 rounded-lg border border-border bg-muted/30 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-[12.5px] text-foreground">{mail.summary}</p>
        <div className="flex shrink-0 gap-1">
          <Button size="sm" variant="ghost" disabled={recheck.isPending}
            onClick={() => recheck.mutate()}>
            {recheck.isPending
              ? <Loader2 size={12} className="animate-spin" />
              : <RefreshCw size={12} />}
            Check again
          </Button>
          <Button size="sm" variant="ghost" onClick={onClose}>Close</Button>
        </div>
      </div>
      <ul className="mt-2 space-y-2">
        {mail.findings.map((f) => (
          <li key={f.key} className="text-[12px]">
            <p className={cn("font-medium", SEVERITY[f.severity] ?? "text-foreground")}>
              {f.title}
            </p>
            <p className="text-muted-foreground">{f.detail}</p>
            {f.fix && <p className="mt-0.5 text-foreground">→ {f.fix}</p>}
          </li>
        ))}
        {mail.findings.length === 0 && (
          <li className="text-[12px] text-muted-foreground">
            Nothing to fix — SPF, DKIM and DMARC are all in order.
          </li>
        )}
      </ul>
    </div>
  )
}

function SiteRow({ site }: { site: Site }) {
  const askAlly = useAssistantStore((s) => s.askAlly)
  const down = site.uptime?.status === "down"
  const state = siteState(site)
  const problem = siteProblem(site)
  const [showMail, setShowMail] = useState(false)

  return (
    <li className={cn(
      "rounded-xl border bg-card p-3",
      siteLooksBroken(site) ? "border-red-500/40 bg-red-500/[0.03]" : "border-border",
      state === "absent" && "opacity-60",
    )}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 gap-2.5">
          <span className="mt-0.5"><StatusDot site={site} /></span>
          <div className="min-w-0">
            <p className="flex flex-wrap items-center gap-2">
              <Link
                to={`/sites/${site.id}`}
                className="truncate text-[14px] font-medium text-foreground hover:underline"
              >
                {site.domain}
              </Link>
              <CertChip site={site} />
              <MailChip site={site} onClick={() => setShowMail((v) => !v)} />
              {state === "installing" && (
                <span className="flex items-center gap-1 rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                  <Loader2 size={9} className="animate-spin" /> Setting up…
                </span>
              )}
              {state === "failed" && (
                <span className="flex items-center gap-1 rounded-full bg-destructive/10 px-1.5 py-0.5 text-[10px] font-medium text-destructive">
                  <CircleAlert size={9} /> Setup failed
                </span>
              )}
              {state === "absent" && (
                <span className="flex items-center gap-1 rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                  <EyeOff size={9} /> No longer found
                </span>
              )}
            </p>
            <p className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[11.5px] text-muted-foreground">
              <span className="flex items-center gap-1">
                <ServerIcon size={10} /> {site.server_name ?? "—"}
              </span>
              <span>
                {APP_LABEL[site.app_type] ?? site.app_type}
                {site.app_version ? ` ${site.app_version}` : ""}
              </span>
              {site.aliases.length > 0 && <span>also {site.aliases.slice(0, 2).join(", ")}</span>}
              {problem && (
                <span className="text-red-600 dark:text-red-400">{problem}</span>
              )}
            </p>
          </div>
        </div>

        <Button
          size="sm" variant="ghost"
          onClick={() => askAlly(
            // Hand Ally the reason we already know, so it does not start by rediscovering
            // it — a failed install is a different job from a site that has gone down.
            state === "failed"
              ? `Setting up ${site.domain} on ${site.server_name} failed: ${problem}. Finish it.`
              : down
                ? `${site.domain} on ${site.server_name} is down — find out why and fix it`
                : `Check ${site.domain} on ${site.server_name} and tell me if anything needs attention`,
          )}
        >
          <Sparkles size={13} /> Ask Ally
        </Button>
      </div>

      {showMail && site.mail && (
        <MailFindings site={site} onClose={() => setShowMail(false)} />
      )}
    </li>
  )
}

/**
 * Sites — every site across the fleet, searchable by domain.
 *
 * Deliberately joins data we already collect (uptime, certificate expiry, what each site runs)
 * rather than introducing a new kind. Creating or configuring a site is a control panel's job;
 * knowing what is running and whether it is healthy is ours.
 */
export default function Sites() {
  const qc = useQueryClient()
  const [q, setQ] = useState("")
  const [serverId, setServerId] = useState("")
  const [includeGone, setIncludeGone] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ["sites", serverId, includeGone],
    queryFn: () => listSites({
      server_id: serverId || undefined,
      include_gone: includeGone || undefined,
    }),
  })
  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers })

  const scan = useMutation({
    mutationFn: scanServerSites,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sites"] }),
  })

  // Filtering client-side keeps typing instant on a fleet-sized list; the server-side `q` is
  // there for when a list outgrows one request.
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const all = data?.sites ?? []
    if (!needle) return all
    return all.filter((s) =>
      s.domain.toLowerCase().includes(needle)
      || s.aliases.some((a) => a.toLowerCase().includes(needle))
      || (s.server_name ?? "").toLowerCase().includes(needle))
  }, [data, q])

  const [adding, setAdding] = useState(false)
  const [newDomain, setNewDomain] = useState("")
  const [creating, setCreating] = useState(false)
  const [note, setNote] = useState("")

  // Which server, then which recipe. A plain server and a panel server answer "host a
  // website" with different runbooks, and the server decides — so it is chosen first
  // rather than hardcoding one and hoping it fits.
  const [createOn, setCreateOn] = useState("")
  const { data: recipes = [] } = useQuery({
    queryKey: ["recipes", createOn],
    queryFn: () => listRecipes(null, createOn || null),
    enabled: !!createOn,
  })
  const siteRecipe = recipes.find((r) => r.slug.includes("host-website"))

  const add = useMutation({
    mutationFn: () => addSite({ domain: newDomain, watch: true }),
    onSuccess: (r) => {
      setNote(r.message); setNewDomain(""); setAdding(false)
      qc.invalidateQueries({ queryKey: ["sites"] })
    },
  })
  const watchAll = useMutation({
    mutationFn: () => watchSites(),
    onSuccess: (r) => { setNote(r.message); qc.invalidateQueries({ queryKey: ["sites"] }) },
  })
  const checkMail = useMutation({
    mutationFn: () => watchMail(),
    onSuccess: (r) => { setNote(r.message); qc.invalidateQueries({ queryKey: ["sites"] }) },
  })

  const scannable = servers.filter((s) => s.connection_type === "ssh")
  const unwatched = (data?.sites ?? []).filter((s) => !s.uptime).length
  // Counted apart on purpose. A site that failed to install was never up, so folding it
  // into "down" both overstates an outage and hides a job that is waiting to be finished.
  const unfinished = shown.filter((s) => siteState(s) === "failed").length
  const down = shown.filter(
    (s) => siteState(s) !== "failed" && s.uptime?.status === "down").length
  const noMail = (data?.sites ?? []).filter((s) => !s.mail).length
  const badMail = shown.filter(
    (s) => s.mail?.verdict === "failing" || s.mail?.verdict === "at risk").length

  return (
    <div>
      <header className="mb-4">
        <h1 className="flex items-center gap-2 text-h1 text-foreground">
          <Globe className="h-5 w-5 text-primary" /> Sites
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Every site across your servers. Search by domain — you don’t need to know which
          server it’s on.
          {down > 0 && (
            <span className="ml-1 font-medium text-red-600 dark:text-red-400">
              {down} {down === 1 ? "site is" : "sites are"} down.
            </span>
          )}
          {unfinished > 0 && (
            <span className="ml-1 font-medium text-red-600 dark:text-red-400">
              {unfinished} {unfinished === 1 ? "setup" : "setups"} did not finish.
            </span>
          )}
          {badMail > 0 && (
            <span className="ml-1 font-medium text-amber-700 dark:text-amber-300">
              {badMail} {badMail === 1 ? "has" : "have"} an email problem.
            </span>
          )}
        </p>
      </header>

      {/* Two doors, on the page where someone looks for a site. "I already have one"
          is ours alone — no competitor can track a site on a host it did not build.
          "Create one" hands the job to Ally rather than templating a vhost ourselves. */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => { setAdding(!adding); setNote("") }}>
          <Plus size={13} />Add a site
        </Button>
        {scannable.length > 0 && (
          <Button size="sm" variant="outline"
            onClick={() => { setCreating(true); setCreateOn(scannable[0].id) }}>
            <Sparkles size={13} />Create a new site
          </Button>
        )}
        {noMail > 0 && (
          <Button size="sm" variant="ghost" disabled={checkMail.isPending}
            onClick={() => checkMail.mutate()}>
            {checkMail.isPending
              ? <Loader2 size={13} className="animate-spin" />
              : <Mail size={13} />}
            Check email for {noMail} domain{noMail === 1 ? "" : "s"}
          </Button>
        )}
        {unwatched > 0 && (
          <Button size="sm" variant="ghost" disabled={watchAll.isPending}
            onClick={() => watchAll.mutate()}>
            {watchAll.isPending
              ? <Loader2 size={13} className="animate-spin" />
              : <CircleCheck size={13} />}
            Watch {unwatched} unwatched site{unwatched === 1 ? "" : "s"}
          </Button>
        )}
      </div>

      {adding && (
        <div className="mb-3 rounded-xl border border-border bg-card p-3">
          <p className="text-[12.5px] text-muted-foreground">
            Any website you own — it does not have to be on a server we manage. We will
            check it every five minutes from outside and tell you if it stops loading.
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <input value={newDomain} onChange={(e) => setNewDomain(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && newDomain.trim()) add.mutate() }}
              placeholder="shop.example.com"
              className="min-w-[220px] flex-1 rounded-lg border border-border bg-background
                         px-3 py-2 text-sm outline-none focus:border-primary" />
            <Button size="sm" disabled={!newDomain.trim() || add.isPending}
              onClick={() => add.mutate()}>
              {add.isPending && <Loader2 size={13} className="animate-spin" />}Add
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setAdding(false)}>Cancel</Button>
          </div>
          {(add.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail && (
            <p className="mt-2 text-[12.5px] text-red-600 dark:text-red-400">
              {(add.error as { response?: { data?: { detail?: string } } }).response!.data!.detail}
            </p>
          )}
        </div>
      )}

      {note && (
        <p className="mb-3 rounded-lg bg-muted/50 px-3 py-2 text-[12.5px] text-foreground">
          {note}
        </p>
      )}

      {creating && (
        <div className="mb-3 rounded-xl border border-border bg-card p-3">
          <p className="text-[12.5px] text-muted-foreground">
            Which server should it go on? Ally will look at that server and use the right
            method for it.
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <select value={createOn} onChange={(e) => setCreateOn(e.target.value)}
              className="rounded-lg border border-border bg-background px-3 py-2 text-sm
                         outline-none focus:border-primary">
              {scannable.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <Button size="sm" variant="ghost" onClick={() => setCreating(false)}>Cancel</Button>
          </div>
          {siteRecipe && (
            <div className="mt-3 border-t border-border pt-3">
              <RunRecipeModal recipe={siteRecipe}
                onClose={() => setCreating(false)} />
            </div>
          )}
        </div>
      )}

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[200px] flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="acmeshop.com"
            className="w-full rounded-lg border border-border bg-background py-1.5 pl-8 pr-3 text-sm outline-none focus:border-primary"
          />
        </div>
        <select
          value={serverId} onChange={(e) => setServerId(e.target.value)}
          className="rounded-lg border border-border bg-background px-2 py-1.5 text-sm outline-none focus:border-primary"
        >
          <option value="">All servers</option>
          {servers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <label className="flex cursor-pointer items-center gap-1.5 text-[11.5px] text-muted-foreground">
          <input type="checkbox" checked={includeGone}
            onChange={(e) => setIncludeGone(e.target.checked)} />
          Show ones we no longer find
        </label>
      </div>

      {/* A server we have never looked at has no sites recorded — say that, rather than
          letting an empty list imply the fleet has no websites. */}
      {(data?.never_scanned.length ?? 0) > 0 && (
        <div className="mb-3 rounded-xl border border-dashed border-border bg-muted/30 p-3">
          <p className="text-[13px] font-medium text-foreground">
            {data!.never_scanned.length} server{data!.never_scanned.length === 1 ? "" : "s"} not
            looked at yet
          </p>
          <p className="mt-0.5 text-[11.5px] text-muted-foreground">
            We read the web server’s own config to find the sites. Nothing is changed.
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {data!.never_scanned.map((s) => (
              <Button key={s.id} size="sm" variant="outline"
                disabled={scan.isPending && scan.variables === s.id}
                onClick={() => scan.mutate(s.id)}>
                {scan.isPending && scan.variables === s.id
                  ? <Loader2 size={13} className="animate-spin" />
                  : <RefreshCw size={13} />}
                {s.name}
              </Button>
            ))}
          </div>
        </div>
      )}

      {isLoading ? (
        <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>
      ) : shown.length === 0 ? (
        <EmptyState
          icon={Globe}
          title={q ? `Nothing matches “${q}”` : "No sites found yet"}
          description={q
            ? "Try part of the domain, or the server's name."
            : "Scan a server and we'll list the websites it serves — read from the web server's own configuration."}
          action={!q && scannable.length > 0 ? (
            <Button size="sm" disabled={scan.isPending}
              onClick={() => scan.mutate(scannable[0].id)}>
              {scan.isPending ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              Scan {scannable[0].name}
            </Button>
          ) : undefined}
        />
      ) : (
        <>
          <ul className="space-y-2">
            {shown.map((site) => <SiteRow key={site.id} site={site} />)}
          </ul>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <p className="text-[11.5px] text-muted-foreground">
              {shown.length} site{shown.length === 1 ? "" : "s"} across{" "}
              {data?.servers_scanned ?? 0} scanned server
              {(data?.servers_scanned ?? 0) === 1 ? "" : "s"}
            </p>
            {serverId && (
              <Button size="sm" variant="outline" disabled={scan.isPending}
                onClick={() => scan.mutate(serverId)}>
                {scan.isPending ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
                Rescan this server
              </Button>
            )}
          </div>
          {scan.data?.note && (
            <p className="mt-2 text-[11.5px] text-amber-700 dark:text-amber-400">{scan.data.note}</p>
          )}
        </>
      )}
    </div>
  )
}
