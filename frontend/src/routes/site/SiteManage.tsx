import { useState } from "react"
import { useOutletContext } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import Editor from "@monaco-editor/react"
import {
  AlertTriangle, FileCode2, Loader2, RotateCcw,
} from "lucide-react"
import { getSiteVhost, saveSiteVhost, type SiteDetail } from "@/api/sites"
import { Button, EmptyState } from "@/components/ui"
import { useThemeStore } from "@/store/themeStore"

/**
 * The tasks that do not belong to any one part of a site — Ploi's "Manage" screen.
 *
 * Built one item at a time, and an item that is not built is ABSENT rather than shown
 * greyed out: a permanently dead button is noise on every visit and implies the feature
 * exists and is merely switched off.
 *
 * Two of Ploi's ten are deliberately not coming. **System user** and **Tenants** are theirs
 * because they give every site its own Linux user; ours all run as the web server's user,
 * so those rows would describe a thing this product does not have. If per-site users are
 * ever added, they arrive together.
 */
export default function SiteManage() {
  const { site } = useOutletContext<{ site: SiteDetail }>()

  return (
    <div className="space-y-4">
      <VhostEditor site={site} />
    </div>
  )
}

/**
 * The web-server configuration, edited by hand — the escape hatch when nothing else on the
 * site fits.
 *
 * It is also the most dangerous edit in the product, so the page says what protects them
 * BEFORE they type: the old file is kept, the web server has to accept the new one, the
 * site has to still answer, and any failure puts the old file back. That is not reassurance
 * for its own sake — someone who knows the change is reversible will make it carefully once
 * instead of not at all.
 */
function VhostEditor({ site }: { site: SiteDetail }) {
  const qc = useQueryClient()
  // "system" is a real setting, so asking the store for the preference is not enough —
  // the editor would render light inside a dark app. Resolved the same way the app resolves
  // it, and re-read on every render so a toggle carries.
  const preference = useThemeStore((s) => s.theme)
  const dark = preference === "dark"
    || (preference === "system"
      && typeof window !== "undefined"
      && window.matchMedia("(prefers-color-scheme: dark)").matches)
  const [draft, setDraft] = useState<string | null>(null)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["site-vhost", site.id],
    queryFn: () => getSiteVhost(site.id),
  })

  const save = useMutation({
    mutationFn: () => saveSiteVhost(site.id, draft ?? ""),
    onSuccess: (r) => {
      setNote({ ok: true, text: r.message })
      setDraft(null)   // reload from the server, so what is shown is what is really there
      qc.invalidateQueries({ queryKey: ["site-vhost", site.id] })
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setNote({ ok: false, text: e.response?.data?.detail ?? "It could not be saved." }),
  })

  if (isLoading) {
    return <div className="h-64 animate-pulse rounded-xl border border-border bg-card" />
  }
  if (!data?.ok) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="The configuration cannot be edited here"
        description={data?.reason ?? "This site is not managed over SSH."}
      />
    )
  }

  const original = data.content ?? ""
  const value = draft ?? original
  const changed = value !== original

  return (
    <section className="overflow-hidden rounded-xl border border-border bg-card">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 py-4">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-sm font-medium text-foreground">
            <FileCode2 size={15} className="text-primary" /> Web server configuration
          </h3>
          <p className="mt-0.5 truncate font-mono text-caption text-muted-foreground"
             title={data.path}>
            {data.path}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {changed && (
            <Button variant="ghost" size="sm" onClick={() => { setDraft(null); setNote(null) }}>
              <RotateCcw size={13} /> Discard
            </Button>
          )}
          <Button size="sm" disabled={!changed || save.isPending}
                  onClick={() => { setNote(null); save.mutate() }}>
            {save.isPending
              ? <><Loader2 size={13} className="animate-spin" /> Saving…</>
              : "Save"}
          </Button>
        </div>
      </header>

      {/* Said before they type, not after it goes wrong. */}
      <p className="border-b border-border bg-muted/30 px-5 py-2.5 text-caption text-muted-foreground">
        Your current file is kept. The web server has to accept the new one and the site has
        to still answer — if either fails, the old file goes straight back and nothing on
        this server changes.
      </p>

      {note && (
        <p className={`border-b border-border px-5 py-2.5 text-small ${note.ok
          ? "bg-emerald-500/5 text-emerald-700 dark:text-emerald-400"
          : "bg-destructive/5 text-destructive"}`}>
          {note.text}
        </p>
      )}

      <Editor
        height="480px"
        defaultLanguage="ini"
        value={value}
        onChange={(v) => setDraft(v ?? "")}
        theme={dark ? "vs-dark" : "light"}
        options={{
          minimap: { enabled: false },
          fontSize: 13,
          scrollBeyondLastLine: false,
          tabSize: 4,
        }}
      />
    </section>
  )
}
