import { useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import Editor from "@monaco-editor/react"
import { AlertTriangle, Eye, EyeOff, KeyRound, Loader2 } from "lucide-react"

import { getSiteEnv, saveSiteEnv } from "@/api/sites"
import { Button } from "@/components/ui"
import { useThemeStore } from "@/store/themeStore"

/**
 * A Laravel site's settings file.
 *
 * **Nothing is fetched until it is asked for.** Every value in this file is a credential,
 * so opening the page should not pull them into a browser that nobody asked to see them
 * in. The button is the consent.
 *
 * The values are then shown masked, because the common reason to open this is to check one
 * setting — the environment, the URL, whether debug is on — and none of those require the
 * database password to be on screen while somebody is sharing it. Editing reveals
 * everything, which is unavoidable: you cannot edit what you cannot read.
 */
export default function EnvEditor({ siteId }: { siteId: string }) {
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const [reveal, setReveal] = useState(false)
  const [draft, setDraft] = useState("")
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)

  const theme = useThemeStore((s) => s.theme)
  const dark = theme === "dark"
    || (theme === "system"
        && typeof window !== "undefined"
        && window.matchMedia?.("(prefers-color-scheme: dark)").matches)

  const q = useQuery({
    queryKey: ["site-env", siteId],
    queryFn: () => getSiteEnv(siteId),
    enabled: open,
    // Credentials do not belong in a cache that outlives the reason they were fetched.
    gcTime: 0,
    staleTime: 0,
  })

  const save = useMutation({
    mutationFn: () => saveSiteEnv(siteId, draft),
    onSuccess: (r) => { setNote({ ok: true, text: r.message }); setEditing(false); q.refetch() },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setNote({ ok: false, text: e.response?.data?.detail ?? "Those settings could not be saved." }),
  })

  const data = q.data

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2">
        <KeyRound size={15} className="text-muted-foreground" />
        <h3 className="text-h3 text-foreground">Environment settings</h3>
      </div>
      <p className="mt-1 text-small text-muted-foreground">
        The <span className="font-mono">.env</span> file — the database connection, the
        application URL, mail settings and every key this application holds. Changing it is
        how you point the site at a different database or turn debug off.
      </p>

      {!open ? (
        <div className="mt-3">
          <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
            Open the settings file
          </Button>
          <p className="mt-2 text-caption text-muted-foreground">
            Nothing is loaded until you ask — this file holds passwords.
          </p>
        </div>
      ) : q.isLoading ? (
        <div className="mt-4 flex items-center gap-2 text-small text-muted-foreground">
          <Loader2 size={14} className="animate-spin" /> Reading it from the server…
        </div>
      ) : q.isError ? (
        <p className="mt-3 rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2
                      text-small text-destructive">
          That file could not be read.
        </p>
      ) : data ? (
        <div className="mt-4 space-y-3">
          {data.warning && (
            <div className="rounded-lg border-l-2 border-destructive bg-destructive/10 px-3 py-2.5">
              <p className="flex items-center gap-1.5 text-small font-semibold text-destructive">
                <AlertTriangle size={14} /> This file is public
              </p>
              <p className="mt-1 text-caption text-foreground">{data.warning}</p>
            </div>
          )}

          <p className="text-caption text-muted-foreground">
            <span className="font-mono">{data.path}</span> · {data.bytes} bytes ·{" "}
            owned by {data.owner} · mode {data.mode}
            {data.config_cached && (
              <> · <span className="text-foreground">configuration is cached</span>, so
              saving rebuilds it — without that, an edit here would change nothing</>
            )}
          </p>

          {!editing ? (
            <>
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-small">
                  <tbody>
                    {data.settings.map((s) => (
                      <tr key={s.key} className="border-b border-border last:border-0">
                        <td className="whitespace-nowrap px-3 py-1.5 font-mono text-caption
                                       text-muted-foreground">
                          {s.key}
                          {s.critical && (
                            <span className="ml-1.5 rounded bg-amber-500/10 px-1 text-[10px]
                                             font-medium text-amber-700 dark:text-amber-400">
                              do not change
                            </span>
                          )}
                        </td>
                        <td className="w-full px-3 py-1.5 font-mono text-caption text-foreground">
                          {s.secret && !reveal
                            ? <span className="text-muted-foreground">••••••••</span>
                            : (s.value || <span className="text-muted-foreground">empty</span>)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="ghost" onClick={() => setReveal((v) => !v)}>
                  {reveal ? <EyeOff size={14} /> : <Eye size={14} />}
                  {reveal ? "Hide values" : "Show values"}
                </Button>
                <Button size="sm" variant="outline"
                        onClick={() => { setDraft(data.content); setEditing(true); setNote(null) }}>
                  Edit
                </Button>
                <Button size="sm" variant="ghost" onClick={() => { setOpen(false); setReveal(false) }}>
                  Close
                </Button>
              </div>
            </>
          ) : (
            <>
              <div className="rounded-lg border-l-2 border-amber-500 bg-amber-500/5 px-3 py-2">
                <p className="text-caption text-muted-foreground">
                  The current file is kept. If the site stops working with your changes — or
                  if Laravel cannot read them — the old one goes back automatically and
                  nothing is left changed.
                </p>
              </div>
              <div className="overflow-hidden rounded-lg border border-border">
                <Editor
                  height="420px"
                  defaultLanguage="ini"
                  theme={dark ? "vs-dark" : "light"}
                  value={draft}
                  onChange={(v) => setDraft(v ?? "")}
                  options={{ minimap: { enabled: false }, fontSize: 13, wordWrap: "on" }}
                />
              </div>
              <div className="flex gap-2">
                <Button size="sm" onClick={() => save.mutate()}
                        disabled={save.isPending || !draft.trim()}>
                  {save.isPending && <Loader2 size={14} className="animate-spin" />}
                  Save settings
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
                  Cancel
                </Button>
              </div>
            </>
          )}

          {note && (
            <p className={`rounded-lg border-l-2 px-3 py-2 text-small ${
              note.ok
                ? "border-emerald-500 bg-emerald-500/5 text-foreground"
                : "border-destructive bg-destructive/5 text-destructive"}`}>
              {note.text}
            </p>
          )}
        </div>
      ) : null}
    </div>
  )
}
