import { useState } from "react"
import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Bell, Loader2, X } from "lucide-react"
import {
  getDeployNotifications, removeDeployNotification, setDeployNotification,
} from "@/api/sites"
import { Button } from "@/components/ui"

/**
 * Be told when this site deploys — Ploi's per-site Notifications.
 *
 * A subscription, not a second notification system: it points at a channel the customer
 * already made and verified, and the sending goes through the one implementation of "talk
 * to Slack" that everything else uses.
 *
 * Ploi's other half — a pair of raw webhook URLs POSTed per site — is deliberately not here.
 * We already have signed, retried, delivery-logged webhooks, so deploy became two events in
 * that catalogue (`deploy.started`, `deploy.finished`) rather than an unsigned second path
 * nobody could audit. That lives in Settings → Integrations, where every other event is.
 */
export default function DeployNotifications({ siteId }: { siteId: string }) {
  const qc = useQueryClient()
  const [channelId, setChannelId] = useState("")
  const [events, setEvents] = useState<string[]>(["completed", "failed"])
  const [error, setError] = useState<string | null>(null)

  const data = useQuery({
    queryKey: ["deploy-notifications", siteId],
    queryFn: () => getDeployNotifications(siteId),
  })

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["deploy-notifications", siteId] })

  const save = useMutation({
    mutationFn: () => setDeployNotification(siteId, channelId, events),
    onSuccess: () => { setError(null); setChannelId(""); invalidate() },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setError(e.response?.data?.detail ?? "That could not be saved."),
  })

  const drop = useMutation({
    mutationFn: (ruleId: string) => removeDeployNotification(siteId, ruleId),
    onSuccess: invalidate,
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setError(e.response?.data?.detail ?? "That could not be removed."),
  })

  const toggle = (value: string) =>
    setEvents((cur) =>
      cur.includes(value) ? cur.filter((e) => e !== value) : [...cur, value])

  const d = data.data
  const channels = d?.channels ?? []
  const rules = d?.rules ?? []

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2">
        <Bell size={15} className="text-muted-foreground" />
        <h3 className="text-h3 text-foreground">Deploy notifications</h3>
      </div>
      <p className="mt-1 text-small text-muted-foreground">
        Be told when this site deploys, without watching the screen.
      </p>

      {rules.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {rules.map((r) => (
            <div key={r.id}
                 className="flex items-start justify-between gap-3 rounded-lg border
                            border-border bg-muted/30 px-3 py-2">
              <div className="min-w-0">
                <p className="text-small text-foreground">
                  {r.channel
                    ? <>{r.channel.label}{" "}
                        <span className="text-caption text-muted-foreground">
                          ({r.channel.kind})
                        </span></>
                    // SET NULL rather than CASCADE, so the rule outlives its channel and
                    // can be repaired instead of vanishing silently.
                    : <span className="text-amber-700 dark:text-amber-400">
                        The channel this used was deleted — it sends nothing until you pick
                        another.
                      </span>}
                </p>
                <p className="mt-0.5 text-caption text-muted-foreground">{r.summary}</p>
                {r.last_error && (
                  <p className="mt-1 flex items-start gap-1 text-caption
                                text-red-600 dark:text-red-400">
                    <AlertTriangle size={11} className="mt-0.5 shrink-0" />
                    Last attempt failed: {r.last_error}
                  </p>
                )}
              </div>
              <button
                onClick={() => drop.mutate(r.id)}
                disabled={drop.isPending}
                title="Remove"
                className="shrink-0 rounded p-1 text-muted-foreground hover:bg-card
                           hover:text-foreground"
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      {data.isLoading ? (
        <p className="mt-3 text-small text-muted-foreground">Checking…</p>
      ) : channels.length === 0 ? (
        // Absent reasons are worse than stated ones — without this the form is simply
        // missing and nobody knows whether the feature exists.
        <p className="mt-3 rounded-lg border-l-2 border-border bg-muted/30 px-3 py-2
                      text-small text-muted-foreground">
          You have no notification channels yet. Add one in{" "}
          <Link to="/settings" className="underline hover:text-foreground">Settings</Link>
          {" "}— Slack, email, Telegram or SMS — then it can be picked here.
        </p>
      ) : (
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap gap-3">
            {(d?.events ?? []).map((e) => (
              <label key={e.value} className="flex items-center gap-1.5 text-small
                                              text-foreground">
                <input type="checkbox" checked={events.includes(e.value)}
                       onChange={() => toggle(e.value)} />
                {e.label}
              </label>
            ))}
          </div>

          <div className="flex flex-wrap items-end gap-2">
            <label className="block min-w-[14rem] flex-1">
              <span className="text-caption text-muted-foreground">Send it to</span>
              <select
                value={channelId}
                onChange={(ev) => setChannelId(ev.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background
                           px-3 py-2 text-small text-foreground"
              >
                <option value="">Choose a channel…</option>
                {channels.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label} ({c.kind}){c.verified_at ? "" : " — not tested yet"}
                  </option>
                ))}
              </select>
            </label>
            <Button size="sm" disabled={save.isPending || !channelId || !events.length}
                    onClick={() => { setError(null); save.mutate() }}>
              {save.isPending && <Loader2 size={14} className="animate-spin" />}
              Add
            </Button>
          </div>

          <p className="text-caption text-muted-foreground">
            A message names the site, the branch and — when one fails — the step it stopped
            on. Being told can never break a deploy: if the channel is down we record that
            here rather than failing the deploy over it.
          </p>
        </div>
      )}

      {error && (
        <p className="mt-2 rounded-lg border-l-2 border-destructive bg-destructive/5
                      px-3 py-2 text-small text-destructive">{error}</p>
      )}
    </div>
  )
}
