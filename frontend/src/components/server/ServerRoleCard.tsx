import { useState } from "react"
import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Globe, LayoutPanelTop, TriangleAlert } from "lucide-react"
import { getServerRole } from "@/api/servers"
import ServerSetupPanel from "@/components/server/ServerSetupPanel"
import { Button } from "@/components/ui"
import type { Server } from "@/types"

/**
 * What ServerAlly is to this server — and, while the machine is still clean, the one
 * moment that is a choice.
 *
 * Two products meet here. On one path ServerAlly IS the control panel: we install the web
 * server, write the vhosts, own the certificates. On the other a real panel owns the
 * machine and we are the thing watching it. Everything else follows from that — the menu,
 * what Ally will do, who renews the certificate.
 *
 * It used to be answered by accident. A fresh server became ours the moment somebody
 * pressed Set up, which is a decision nobody was offered, and an expensive one to get
 * wrong: setup installs nginx, PHP and a database, and a control panel wants a clean
 * machine, so the way back is rebuilding the server.
 */
export default function ServerRoleCard({ server }: { server: Server }) {
  const [going, setGoing] = useState<"serverally" | "panel" | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["server-role", server.id],
    queryFn: () => getServerRole(server.id),
    // A setup finishing, or a panel being detected, changes the answer.
    staleTime: 10_000,
  })

  if (isLoading) {
    return <div className="h-24 animate-pulse rounded-lg border border-border bg-card" />
  }
  if (!data?.applies) return null

  // A decided server never reaches this page — its Overview is gone from the menu and
  // /servers/:id sends it to Sites. So there is no "already decided" card to render here;
  // if the choice is made, this component is not on screen.
  if (data.role !== "undecided") return null

  // A setup the customer already asked for is running. Showing the two doors again would
  // ask them to choose something they have chosen, while the work is under way.
  if (!data.can_choose) return <ServerSetupPanel server={server} />

  // ── The fork ───────────────────────────────────────────────────────────────

  if (going === "serverally") {
    return (
      <>
        <button type="button" onClick={() => setGoing(null)}
          className="text-caption text-muted-foreground underline-offset-2 hover:text-foreground hover:underline">
          ← Back to the two options
        </button>
        <ServerSetupPanel server={server} />
      </>
    )
  }

  return (
    <section className="overflow-hidden rounded-xl border border-border bg-card">
      <header className="border-b border-border px-5 py-4">
        <h3 className="text-sm font-medium text-foreground">
          How should this server be run?
        </h3>
        <p className="mt-0.5 text-caption text-muted-foreground">
          This is a clean server, so both are still open. Pick one and ServerAlly follows
          it from here.
        </p>
      </header>

      <div className="grid gap-3 p-5 sm:grid-cols-2">
        <Door
          icon={Globe}
          title="Set up with ServerAlly"
          blurb="We install the web server, PHP and a database, and ServerAlly becomes the
                 control panel — websites, certificates, redirects and deployments all live
                 in here."
          note="Best if you just want websites running and do not want to learn a panel."
          onPick={() => setGoing("serverally")}
          cta="Set it up"
        />
        <Door
          icon={LayoutPanelTop}
          title="Install a control panel"
          blurb="CyberPanel, cPanel, Plesk and others. That panel then owns the websites and
                 the certificates, and ServerAlly watches over it — monitoring, backups,
                 security scans and Ally."
          note="Best if you already know a panel, or your customers need its own logins."
          onPick={() => setGoing("panel")}
          cta="Choose a panel"
          picked={going === "panel"}
        >
          {going === "panel" && (
            <div className="mt-3 space-y-1.5 border-t border-border pt-3">
              {data.panels.length === 0 && (
                <p className="text-caption text-muted-foreground">
                  No control-panel installers are available on this ServerAlly.
                </p>
              )}
              {data.panels.map((p) => (
                <Link key={p.id} to={`/playbooks/${p.id}`}
                  className="block rounded-lg border border-border px-3 py-2 hover:border-primary/50 hover:bg-accent">
                  <p className="text-sm font-medium text-foreground">{p.title}</p>
                  {p.description && (
                    <p className="line-clamp-2 text-caption text-muted-foreground">
                      {p.description}
                    </p>
                  )}
                </Link>
              ))}
            </div>
          )}
        </Door>
      </div>

      {/* The asymmetry, said out loud. A customer cannot know it, and finds out at the
          worst possible moment — when they have a working server and want the other one. */}
      <footer className="flex items-start gap-2.5 border-t border-border bg-amber-500/5 px-5 py-3">
        <TriangleAlert size={14} className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" />
        <p className="text-caption text-muted-foreground">
          <span className="font-medium text-foreground">This is close to a one-way door.</span>{" "}
          A control panel needs a clean machine, so once this server has been set up by
          ServerAlly — or has websites on it — installing a panel means rebuilding the
          server from scratch. Going the other way is easier but still not free.
        </p>
      </footer>
    </section>
  )
}

function Door({ icon: Icon, title, blurb, note, onPick, cta, picked, children }: {
  icon: typeof Globe
  title: string
  blurb: string
  note: string
  onPick: () => void
  cta: string
  picked?: boolean
  children?: React.ReactNode
}) {
  return (
    <div className={`rounded-lg border p-4 transition-colors ${
      picked ? "border-primary/60 bg-primary/[0.03]" : "border-border"}`}>
      <Icon size={18} className="text-primary" />
      <p className="mt-2 text-sm font-medium text-foreground">{title}</p>
      <p className="mt-1 text-caption text-muted-foreground">{blurb}</p>
      <p className="mt-2 text-caption text-muted-foreground/80">{note}</p>
      <Button size="sm" variant="outline" className="mt-3" onClick={onPick}>{cta}</Button>
      {children}
    </div>
  )
}