import { useState } from "react"
import { useOutletContext } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Check, Code2, Loader2, Plus } from "lucide-react"
import { getPhp, switchPhp, type PhpSite } from "@/api/php"
import { getPlaybook, listPlaybooks } from "@/api/playbooks"
import RunPlaybookModal from "@/components/playbooks/RunPlaybookModal"
import { Button, EmptyState } from "@/components/ui"
import { cn } from "@/lib/utils"
import type { Server } from "@/types"

/**
 * Which PHP each website runs on, and how to move one.
 *
 * Read fresh every time rather than cached: a stale version shown as current is worse than
 * showing nothing, because someone would move a site "to 8.3" it is already on, or believe
 * a site is safe on a version it no longer uses.
 *
 * The switch is the only dangerous thing here, so the UI says what will happen before it is
 * pressed — the server checks the site still works afterwards and puts the old version back
 * if it does not, which means a refusal is safe rather than alarming.
 */
export default function ServerPhp() {
  const { server } = useOutletContext<{ server: Server }>()
  const qc = useQueryClient()
  const [installing, setInstalling] = useState(false)
  const [pending, setPending] = useState<{ site: PhpSite; version: string } | null>(null)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["php", server.id],
    queryFn: () => getPhp(server.id),
  })

  const { data: playbooks = [] } = useQuery({ queryKey: ["playbooks"], queryFn: () => listPlaybooks() })
  const installer = playbooks.find((p) => p.slug === "php-version")
  const { data: installerFull } = useQuery({
    queryKey: ["playbook", "php-version"],
    queryFn: () => getPlaybook(installer!.id),
    enabled: installing && !!installer,
  })

  const move = useMutation({
    mutationFn: (v: { site: PhpSite; version: string }) => switchPhp(server.id, {
      config: v.site.config,
      // The vhost file is named after the domain, which is what the server needs to check
      // the site with a Host header.
      domain: v.site.name.replace(/\.conf$/, ""),
      version: v.version,
    }),
    onSuccess: (r) => {
      setNote({ ok: true, text: r.message })
      setPending(null)
      qc.invalidateQueries({ queryKey: ["php", server.id] })
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      // A 409 means the change was refused or undone — nothing is broken.
      setNote({ ok: false, text: e.response?.data?.detail ?? "The change could not be made." })
      setPending(null)
      qc.invalidateQueries({ queryKey: ["php", server.id] })
    },
  })

  const versions = data?.versions ?? []
  const running = new Set(data?.running ?? [])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="flex items-center gap-2 text-[17px] font-medium text-foreground">
            <Code2 size={16} className="text-primary" /> PHP
          </h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {versions.length === 0
              ? "No PHP found on this server."
              : `${versions.length} version${versions.length === 1 ? "" : "s"} installed`}
            {data?.cli_default && ` · command line uses ${data.cli_default}`}
          </p>
        </div>
        {installer && (
          <Button size="sm" onClick={() => setInstalling(true)}>
            <Plus size={13} /> Install a version
          </Button>
        )}
      </div>

      {data?.error && (
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[12.5px] text-foreground">
          {data.error}
        </p>
      )}

      {note && (
        <p className={cn(
          "rounded-lg px-3 py-2 text-[12.5px]",
          note.ok
            ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
            : "border border-amber-500/30 bg-amber-500/10 text-foreground",
        )}>
          {note.text}
        </p>
      )}

      {installing && installerFull && (
        <RunPlaybookModal
          playbook={installerFull}
          servers={[server]}
          onClose={() => {
            setInstalling(false)
            qc.invalidateQueries({ queryKey: ["php", server.id] })
          }}
        />
      )}

      {isLoading ? (
        <div className="h-24 animate-pulse rounded-xl border border-border bg-card" />
      ) : versions.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-3">
          <p className="mb-2 text-[12.5px] font-medium text-foreground">Installed</p>
          <div className="flex flex-wrap gap-2">
            {versions.map((v) => (
              <span key={v} className={cn(
                "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px]",
                running.has(v)
                  ? "bg-emerald-500/15 font-medium text-emerald-700 dark:text-emerald-300"
                  : "bg-muted text-muted-foreground",
              )}>
                PHP {v}
                {running.has(v) ? <Check size={11} /> : " · not running"}
              </span>
            ))}
          </div>
        </div>
      )}

      {!isLoading && (data?.sites.length ?? 0) === 0 ? (
        <EmptyState
          icon={Code2}
          // Three genuinely different situations, and "no PHP websites found" was the same
          // unhelpful sentence for all of them. The middle one is the common real case: a
          // box serving PHP through something other than PHP-FPM, where there is honestly
          // nothing for this page to manage.
          title={versions.length === 0
            ? "PHP is not installed here"
            : running.size === 0
              ? "This server does not use PHP-FPM"
              : "No PHP websites yet"}
          description={versions.length === 0
            ? "Install a version if you want to host PHP websites on this server."
            : running.size === 0
              ? `PHP ${versions.join(" and ")} is installed but no PHP-FPM service is `
                + "running, so its websites are served another way — a control panel or "
                + "OpenLiteSpeed manages its own PHP, and changing it there is the safe "
                + "place to do it."
              : "Websites on this server will appear here once one of them serves PHP, and "
                + "you can then change the version it uses."}
          className="py-12"
        />
      ) : !isLoading && (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <div className="border-b border-border px-3 py-2">
            <p className="text-[12.5px] font-medium text-foreground">Which version each site uses</p>
            <p className="mt-0.5 text-[11.5px] text-muted-foreground">
              Changing this is checked: if the site stops working on the new version it is put
              straight back on the one it had.
            </p>
          </div>
          {data!.sites.map((s) => (
            <div key={s.config} className="flex flex-wrap items-center gap-3 border-t border-border px-3 py-2.5 first:border-t-0">
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13.5px] font-medium text-foreground">{s.name}</p>
                <p className="truncate text-[11px] text-muted-foreground">{s.config}</p>
              </div>
              <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[11.5px] font-medium text-foreground">
                PHP {s.version ?? "?"}
              </span>
              <select
                value={s.version ?? ""}
                disabled={move.isPending}
                onChange={(e) => {
                  const v = e.target.value
                  if (v && v !== s.version) setPending({ site: s, version: v })
                }}
                className="shrink-0 rounded-lg border border-border bg-background px-2 py-1 text-[12.5px] outline-none focus:border-primary"
              >
                <option value={s.version ?? ""}>Change to…</option>
                {versions.filter((v) => v !== s.version && running.has(v)).map((v) => (
                  <option key={v} value={v}>PHP {v}</option>
                ))}
              </select>
            </div>
          ))}
        </div>
      )}

      {pending && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md rounded-xl border border-border bg-card p-5 shadow-xl">
            <h3 className="flex items-center gap-2 text-[16px] font-medium text-foreground">
              <AlertTriangle size={16} className="text-amber-500" />
              Move {pending.site.name} to PHP {pending.version}?
            </h3>
            <p className="mt-2 text-[12.5px] leading-relaxed text-muted-foreground">
              An application written for an older PHP can stop working on a newer one. We will
              change it, check the site still loads, and put it straight back on PHP{" "}
              {pending.site.version} if it does not — so this is safe to try.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <Button size="sm" variant="ghost" onClick={() => setPending(null)}>Cancel</Button>
              <Button size="sm" disabled={move.isPending} onClick={() => move.mutate(pending)}>
                {move.isPending && <Loader2 size={13} className="animate-spin" />}
                Change it
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
