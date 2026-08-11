import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Gauge, Loader2 } from "lucide-react"
import { getHttp3, setHttp3 } from "@/api/sites"
import { Button } from "@/components/ui"

/**
 * HTTP/3 for one site — Ploi's SSL → HTTP/3.
 *
 * **Most servers cannot do it, and that is the honest first thing to say.** nginx only
 * speaks HTTP/3 when it was built with the module, which arrived in 1.25 — and Ubuntu 24.04,
 * what our own setup installs, ships 1.24. A switch that writes a configuration nginx then
 * refuses would take down every site on the machine, so a server that cannot is told why
 * rather than given the switch.
 *
 * Deliberately quiet about the benefit: HTTP/3 is a small speed improvement on poor mobile
 * connections, not a fix for anything. Overselling it would get people to change a working
 * web server configuration for nothing.
 */
export default function Http3Toggle({ siteId }: { siteId: string }) {
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ["http3", siteId],
    queryFn: () => getHttp3(siteId),
  })

  const change = useMutation({
    mutationFn: (enabled: boolean) => setHttp3(siteId, enabled),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["http3", siteId] }),
  })

  if (isLoading || !data) return null

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-sm font-medium text-foreground">
            <Gauge size={15} className="text-muted-foreground" />
            HTTP/3
          </p>
          <p className="mt-1 text-small text-muted-foreground">
            A newer way for browsers to talk to this site. A little faster on poor mobile
            connections; nothing changes for anyone whose browser does not support it.
          </p>
          {data.why && (
            <p className="mt-2 text-caption text-amber-700 dark:text-amber-400">{data.why}</p>
          )}
          {!data.why && data.enabled && !data.udp_open && (
            // The failure where everything looks configured and no visitor can connect.
            <p className="mt-2 text-caption text-amber-700 dark:text-amber-400">
              HTTP/3 uses UDP port 443. If your provider has its own firewall in front of this
              server, open that port there too.
            </p>
          )}
        </div>

        {!data.why && (
          <Button
            size="sm"
            variant={data.enabled ? "outline" : "secondary"}
            disabled={change.isPending}
            onClick={() => change.mutate(!data.enabled)}
          >
            {change.isPending && <Loader2 size={13} className="animate-spin" />}
            {data.enabled ? "Turn off" : "Turn on"}
          </Button>
        )}
      </div>

      {change.isError && (
        <p className="mt-2 rounded-lg border-l-2 border-destructive bg-destructive/5 px-3
                      py-2 text-small text-destructive">
          {(change.error as { response?: { data?: { detail?: string } } })
            ?.response?.data?.detail ?? "That could not be changed."}
        </p>
      )}
      {change.isSuccess && !change.isPending && (
        <p className="mt-2 text-caption text-emerald-700 dark:text-emerald-400">
          {change.data.message}
        </p>
      )}
    </div>
  )
}
