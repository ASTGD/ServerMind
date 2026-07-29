import { Link, useOutletContext } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { formatDistanceToNow } from "date-fns"
import { GitBranch, Loader2, Rocket, Undo2 } from "lucide-react"
import { deployNow, listDeployTargets, rollback } from "@/api/deployments"
import { Button, EmptyState } from "@/components/ui"
import { cn } from "@/lib/utils"
import type { Server } from "@/types"

/**
 * Getting code onto this server.
 *
 * A per-server view of the deploy targets, not a second deploy implementation — creating
 * and editing a target still happens on the full Deployments page, because that is where
 * the build commands, shared paths and webhook secret live. What belongs here is the pair
 * of things you want while looking at one server: what is currently released, and the two
 * buttons that change it.
 */
export default function ServerDeployments() {
  const { server } = useOutletContext<{ server: Server }>()
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ["deploy-targets"], queryFn: listDeployTargets,
  })
  const mine = (data?.targets ?? []).filter((t) => t.server_id === server.id)

  const deploy = useMutation({
    mutationFn: (id: string) => deployNow(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["deploy-targets"] }),
  })
  const back = useMutation({
    mutationFn: (id: string) => rollback(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["deploy-targets"] }),
  })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="flex items-center gap-2 text-[17px] font-medium text-foreground">
            <Rocket size={16} className="text-primary" /> Deployments
          </h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Each deploy builds in a new folder and switches one link, so a failed build never
            reaches the live site.
          </p>
        </div>
        <Link to="/deployments">
          <Button size="sm" variant="outline">Manage targets</Button>
        </Link>
      </div>

      {isLoading ? (
        <div className="h-24 animate-pulse rounded-xl border border-border bg-card" />
      ) : mine.length === 0 ? (
        <EmptyState
          icon={Rocket}
          title="Nothing deploys here yet"
          description="Add a deploy target to pull code from Git onto this server and release it safely."
          className="py-14"
          action={<Link to="/deployments"><Button size="sm">Add a target</Button></Link>}
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          {mine.map((t) => (
            <div key={t.id} className="flex flex-wrap items-center gap-3 border-t border-border px-3 py-3 first:border-t-0">
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-2 text-[14px] font-medium text-foreground">
                  {t.name}
                  {t.auto_deploy && (
                    <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
                      push to deploy
                    </span>
                  )}
                </p>
                <p className="truncate text-[11.5px] text-muted-foreground">
                  <GitBranch size={10} className="mr-1 inline" />
                  {t.repo} · {t.branch} → {t.path}
                </p>
                <p className="mt-0.5 text-[11.5px] text-muted-foreground">
                  {t.current_release
                    ? <>Live release <span className="text-foreground">{t.current_release}</span></>
                    : "Never deployed"}
                  {t.last_status && (
                    <span className={cn(
                      "ml-2 font-medium",
                      t.last_status === "success" ? "text-emerald-600 dark:text-emerald-400"
                        : t.last_status === "failed" ? "text-red-600 dark:text-red-400"
                          : "text-muted-foreground",
                    )}>
                      {t.last_status}
                    </span>
                  )}
                  {t.last_deployed_at && (() => {
                    try {
                      return ` · ${formatDistanceToNow(new Date(t.last_deployed_at), { addSuffix: true })}`
                    } catch { return "" }
                  })()}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                <Button size="sm" variant="outline"
                  disabled={deploy.isPending && deploy.variables === t.id}
                  onClick={() => deploy.mutate(t.id)}>
                  {deploy.isPending && deploy.variables === t.id
                    ? <Loader2 size={13} className="animate-spin" />
                    : <Rocket size={13} />}
                  Deploy now
                </Button>
                <Button size="sm" variant="ghost"
                  disabled={back.isPending && back.variables === t.id}
                  onClick={() => back.mutate(t.id)}>
                  {back.isPending && back.variables === t.id
                    ? <Loader2 size={13} className="animate-spin" />
                    : <Undo2 size={13} />}
                  Roll back
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
