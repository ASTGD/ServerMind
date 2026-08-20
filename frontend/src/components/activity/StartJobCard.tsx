import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { Play } from "lucide-react"
import { listBlueprints, startBlueprint } from "@/api/blueprints"
import { listServers } from "@/api/servers"
import { Button } from "@/components/ui"

/** Start a ready-made job from the app. The form is drawn from the blueprint's own
 * declared inputs, so a field can never be asked for here that the backend then ignores —
 * one source, the same rule the setup screen follows. */
export default function StartJobCard() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { data: blueprints = [] } = useQuery({ queryKey: ["blueprints"], queryFn: listBlueprints })
  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers })

  const bp = blueprints[0]
  // Only servers the blueprint can run on are offered — absent, not disabled.
  const eligible = servers.filter((s) => s.connection_type === "ssh" && !s.panel_type)

  const [serverId, setServerId] = useState("")
  const [values, setValues] = useState<Record<string, string>>({})
  const [error, setError] = useState("")

  const start = useMutation({
    mutationFn: () => startBlueprint(serverId, bp!.key, values),
    onSuccess: (run) => {
      qc.invalidateQueries({ queryKey: ["blueprint-runs"] })
      navigate(`/activity/${run.id}`)
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setError(e.response?.data?.detail ?? "Could not start."),
  })

  if (!bp) return null
  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <p className="text-[15px] font-medium">{bp.title}</p>
      <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">{bp.description}</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <select value={serverId} onChange={(e) => { setServerId(e.target.value); setError("") }}
          className="h-9 rounded-lg border border-border bg-background px-2.5 text-sm">
          <option value="">Which server…</option>
          {eligible.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        {bp.needs.map((n) =>
          n.choices.length ? (
            <select key={n.name} value={values[n.name] ?? ""}
              onChange={(e) => { setValues((v) => ({ ...v, [n.name]: e.target.value })); setError("") }}
              className="h-9 rounded-lg border border-border bg-background px-2.5 text-sm">
              <option value="">{n.label}…</option>
              {n.choices.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          ) : (
            <input key={n.name} value={values[n.name] ?? ""} placeholder={n.label}
              onChange={(e) => { setValues((v) => ({ ...v, [n.name]: e.target.value })); setError("") }}
              className="h-9 rounded-lg border border-border bg-background px-2.5 text-sm" />
          ))}
      </div>
      {error && <p className="mt-2 text-[13px] text-red-600 dark:text-red-400">{error}</p>}
      <div className="mt-3 flex items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">
          {bp.leaves_for_you[0] ?? ""}
        </p>
        <Button size="sm" onClick={() => start.mutate()}
          disabled={!serverId || start.isPending}>
          <Play size={13} className="mr-1.5" /> Start
        </Button>
      </div>
    </div>
  )
}
