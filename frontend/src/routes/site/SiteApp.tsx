import { useState } from "react"
import { useOutletContext } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Loader2 } from "lucide-react"
import { getSiteApp, runSiteAppAction, type SiteDetail } from "@/api/sites"
import { EmptyState } from "@/components/ui"
import WordPressPanel from "@/components/sites/WordPressPanel"
import EnvEditor from "@/components/sites/EnvEditor"
import LaravelPanel from "@/components/sites/LaravelPanel"
import PhpPanel from "@/components/sites/PhpPanel"

/**
 * The screen for whatever runs on this site.
 *
 * A dispatcher, not a screen: the backend's registry answers which application is here and
 * reads its state, and each application gets its own panel. That split is the whole design —
 * WordPress is an inventory of plugins and users, Laravel is the condition of a deployment,
 * PHP is a handful of limits. One screen trying to serve all three would serve none of them.
 * Adding Nextcloud is a registry entry, a service, and one more line below.
 *
 * Read fresh on every visit. Plugin versions, migrations and administrator accounts all
 * change without us, and a cached answer to "is anything wrong here" is worth nothing.
 */
export default function SiteAppPage() {
  const { site } = useOutletContext<{ site: SiteDetail }>()
  const qc = useQueryClient()
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["site-app", site.id],
    queryFn: () => getSiteApp(site.id),
  })

  const run = useMutation({
    mutationFn: ({ action, target }: { action: string; target?: string }) =>
      runSiteAppAction(site.id, action, target ?? ""),
    onMutate: ({ action, target }) => {
      setNote(null)
      setBusy(target || action)
    },
    // Held busy until the re-read finishes. Clearing it the moment the command returns
    // leaves "Done." sitting above the OLD numbers for as long as the SSH round trip takes,
    // which reads as a failure.
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["site-app", site.id] })
      setBusy(null)
      setNote({ ok: true, text: "Done." })
    },
    // The tool's own message names the actual problem — a plugin that does not exist, a
    // migration that failed, a database it cannot reach — better than anything written here.
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      setBusy(null)
      setNote({ ok: false, text: e.response?.data?.detail ?? "That did not work." })
    },
  })

  if (isLoading) {
    return (
      <div className="flex justify-center py-16 text-muted-foreground">
        <Loader2 size={20} className="animate-spin" />
      </div>
    )
  }

  if (!data?.app) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Nothing to manage here"
        description="This site does not run an application we have tools for."
      />
    )
  }

  if (!data.ok) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title={`${data.label} could not be read`}
        description={data.reason ?? "We could not look at this site."}
      />
    )
  }

  const act = (action: string, target?: string) => run.mutate({ action, target })

  if (data.app === "wordpress") {
    return <WordPressPanel data={data} domain={site.domain} onAct={act} busy={busy} note={note} />
  }
  if (data.app === "laravel") {
    return (
      <div className="space-y-4">
        <LaravelPanel data={data} onAct={act} busy={busy} />
        <EnvEditor siteId={site.id} />
        {note && (
          <p className={`rounded-lg border-l-2 px-3 py-2 text-small ${
            note.ok
              ? "border-emerald-500 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400"
              : "border-destructive bg-destructive/5 text-destructive"}`}>
            {note.text}
          </p>
        )}
      </div>
    )
  }
  if (data.app === "php") return <PhpPanel data={data} />

  return (
    <EmptyState
      icon={AlertTriangle}
      title={`${data.label} has no screen yet`}
      description="We know what runs here, but there is nothing to show for it so far."
    />
  )
}
