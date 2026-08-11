import { useEffect, useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { AlertTriangle, FileCode2, Loader2, ShieldCheck } from "lucide-react"
import { getWpConfig, saveWpConfig } from "@/api/sites"
import { Button } from "@/components/ui"

/**
 * Editing wp-config.php — Ploi's WordPress → Configuration.
 *
 * The file every WordPress owner is told to edit and never does, because getting it wrong
 * takes the site down completely: it is PHP, loaded before anything else, and a missing
 * semicolon produces a blank page with no message anywhere they would look.
 *
 * The reassurance is stated before the box, because somebody who knows the change is checked
 * and reversible makes it carefully once, instead of not at all.
 *
 * The real values are shown, not masked: this is where the file is EDITED, and saving a mask
 * back would write the mask into the file. The count of secret lines is shown instead, so
 * nobody is surprised by what is in front of them.
 */
export default function WpConfigEditor({ siteId }: { siteId: string }) {
  const [text, setText] = useState<string | null>(null)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ["wp-config", siteId],
    queryFn: () => getWpConfig(siteId),
  })

  useEffect(() => { if (data && text === null) setText(data.content) }, [data, text])

  const save = useMutation({
    mutationFn: () => saveWpConfig(siteId, text ?? ""),
    onSuccess: (r) => setNote({ ok: true, text: r.message }),
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setNote({ ok: false, text: e.response?.data?.detail ?? "That could not be saved." }),
  })

  const dirty = data != null && text != null && text !== data.content

  return (
    <details className="rounded-xl border border-border bg-card">
      <summary className="flex cursor-pointer items-center gap-2 px-4 py-3 text-sm
                          font-medium text-foreground">
        <FileCode2 size={15} className="text-muted-foreground" />
        Configuration file
      </summary>

      <div className="space-y-3 border-t border-border p-4">
        <p className="text-small text-muted-foreground">
          WordPress reads its settings from this file before anything else. It is checked for
          syntax errors before it is saved, a copy is kept, and if the site stops loading the
          old one is put straight back.
        </p>

        {isLoading && (
          <p className="flex items-center gap-2 text-small text-muted-foreground">
            <Loader2 size={13} className="animate-spin" /> Reading the file…
          </p>
        )}
        {error != null && (
          <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2
                        text-small text-destructive">
            That file could not be read.
          </p>
        )}

        {data && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-caption text-muted-foreground">{data.path}</span>
              {data.secrets > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2
                                 py-0.5 text-caption text-muted-foreground">
                  <ShieldCheck size={11} />
                  {data.secrets} line{data.secrets === 1 ? "" : "s"} hold a password or a key
                </span>
              )}
            </div>

            {data.warnings.map((w) => (
              <p key={w} className="flex items-start gap-1.5 rounded-lg border-l-2
                                    border-amber-500 bg-amber-500/5 px-3 py-2 text-caption
                                    text-amber-800 dark:text-amber-300">
                <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                {w}
              </p>
            ))}

            <textarea
              value={text ?? ""}
              onChange={(e) => { setText(e.target.value); setNote(null) }}
              rows={18}
              spellCheck={false}
              className="w-full rounded-lg border border-border bg-background px-3 py-2
                         font-mono text-caption leading-relaxed text-foreground"
            />

            <div className="flex items-center gap-3">
              <Button size="sm" disabled={!dirty || save.isPending}
                      onClick={() => save.mutate()}>
                {save.isPending && <Loader2 size={13} className="animate-spin" />}
                Save
              </Button>
              {dirty && !save.isPending && (
                <button type="button" onClick={() => { setText(data.content); setNote(null) }}
                        className="text-caption text-muted-foreground hover:text-foreground">
                  Undo my changes
                </button>
              )}
            </div>
          </>
        )}

        {note && (
          <p className={`rounded-lg border-l-2 px-3 py-2 text-small ${
            note.ok
              ? "border-emerald-500 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400"
              : "border-destructive bg-destructive/5 text-destructive"}`}>
            {note.text}
          </p>
        )}
      </div>
    </details>
  )
}
