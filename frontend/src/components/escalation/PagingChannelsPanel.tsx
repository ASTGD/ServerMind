import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MessageSquare, Smartphone, Loader2, Check, Trash2, ShieldCheck } from "lucide-react"
import {
  listProviders, setProvider, deleteProvider, testProvider, type PagingProvider,
} from "@/api/escalation"
import { Button } from "@/components/ui"

const input =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
const label = "mb-1 block text-xs font-medium text-muted-foreground"

function useProviderActions() {
  const qc = useQueryClient()
  const invalidate = () => qc.invalidateQueries({ queryKey: ["paging-providers"] })
  return {
    save: useMutation({ mutationFn: (v: Parameters<typeof setProvider>) => setProvider(...v), onSuccess: invalidate }),
    remove: useMutation({ mutationFn: deleteProvider, onSuccess: invalidate }),
    test: useMutation({ mutationFn: (v: Parameters<typeof testProvider>) => testProvider(...v) }),
  }
}

function detail(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === "string" ? d : fallback
}

function TwilioCard({ state }: { state: PagingProvider }) {
  const { save, remove, test } = useProviderActions()
  const [form, setForm] = useState({ account_sid: "", auth_token: "", from_number: "" })
  const [limit, setLimit] = useState(state.monthly_limit ?? 100)
  const [testTo, setTestTo] = useState("")
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const used = state.sent_this_month
  const cap = state.monthly_limit ?? 0
  const nearCap = cap > 0 && used / cap >= 0.9

  return (
    <div className="rounded-lg border border-border p-3">
      <div className="mb-2 flex items-center gap-2">
        <Smartphone size={14} className="text-primary" />
        <span className="text-[13px] font-medium">Text messages (Twilio)</span>
        {state.configured && (
          <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
            state.verified
              ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
              : "bg-amber-500/15 text-amber-700 dark:text-amber-300"}`}>
            {state.verified ? "Tested" : "Not tested yet"}
          </span>
        )}
      </div>
      <p className="mb-3 text-[11.5px] text-muted-foreground">
        A text is the one alert that reliably wakes someone. Texts cost money on every
        message, so ServerAlly keeps a monthly limit you set.
      </p>

      {state.configured ? (
        <>
          <div className="mb-3 rounded-lg bg-muted/60 px-3 py-2">
            <p className="text-[11.5px] text-muted-foreground">
              <span className={nearCap ? "font-semibold text-amber-700 dark:text-amber-400" : ""}>
                {used} of {cap}
              </span>{" "}
              texts used this month. Resets on the 1st.
            </p>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <div>
              <label className={label}>Monthly limit</label>
              <input type="number" min={0} max={10000} className={input} value={limit}
                onChange={(e) => setLimit(Math.max(0, Number(e.target.value) || 0))} />
            </div>
            <div>
              <label className={label}>Send a test to</label>
              <div className="flex gap-1.5">
                <input className={input} placeholder="+8801712345678" value={testTo}
                  onChange={(e) => setTestTo(e.target.value)} />
                <Button size="sm" variant="outline" disabled={!testTo.trim() || test.isPending}
                  onClick={() => {
                    setMsg(null)
                    test.mutate(["twilio", testTo.trim()], {
                      onSuccess: () => setMsg({ ok: true, text: `Test text sent to ${testTo}.` }),
                      onError: (e) => setMsg({ ok: false, text: detail(e, "Could not send the text.") }),
                    })
                  }}>
                  {test.isPending ? <Loader2 size={13} className="animate-spin" /> : "Test"}
                </Button>
              </div>
            </div>
          </div>
          <div className="mt-3 flex justify-between">
            <Button size="sm" variant="ghost"
              onClick={() => remove.mutate("twilio")}>
              <Trash2 size={13} /> Remove
            </Button>
            <Button size="sm" disabled={save.isPending}
              onClick={() => save.mutate(["twilio", { monthly_limit: limit }] as Parameters<typeof setProvider>)}>
              Save limit
            </Button>
          </div>
        </>
      ) : (
        <>
          <div className="grid gap-2 sm:grid-cols-3">
            <div>
              <label className={label}>Account SID</label>
              <input className={`${input} font-mono text-xs`} placeholder="AC…"
                value={form.account_sid}
                onChange={(e) => setForm({ ...form, account_sid: e.target.value })} />
            </div>
            <div>
              <label className={label}>Auth Token</label>
              <input className={`${input} font-mono text-xs`} type="password" placeholder="••••••"
                value={form.auth_token}
                onChange={(e) => setForm({ ...form, auth_token: e.target.value })} />
            </div>
            <div>
              <label className={label}>Your Twilio number</label>
              <input className={input} placeholder="+15550001111"
                value={form.from_number}
                onChange={(e) => setForm({ ...form, from_number: e.target.value })} />
            </div>
          </div>
          <div className="mt-2 flex items-center justify-between gap-2">
            <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
              <ShieldCheck size={11} /> Stored encrypted; never shown again.
            </span>
            <Button size="sm" disabled={save.isPending ||
              !(form.account_sid && form.auth_token && form.from_number)}
              onClick={() => {
                setMsg(null)
                save.mutate(["twilio", { ...form, monthly_limit: limit }] as Parameters<typeof setProvider>, {
                  onError: (e) => setMsg({ ok: false, text: detail(e, "Could not save.") }),
                })
              }}>
              {save.isPending ? <><Loader2 size={13} className="animate-spin" /> Saving…</> : "Save"}
            </Button>
          </div>
        </>
      )}

      {msg && (
        <p className={`mt-2 rounded-lg px-3 py-2 text-xs ${msg.ok
          ? "border border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
          : "border border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400"}`}>
          {msg.ok && <Check size={12} className="mr-1 inline" />}{msg.text}
        </p>
      )}
    </div>
  )
}

function TelegramCard({ state }: { state: PagingProvider }) {
  const { save, remove, test } = useProviderActions()
  const [botToken, setBotToken] = useState("")
  const [testTo, setTestTo] = useState("")
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  return (
    <div className="rounded-lg border border-border p-3">
      <div className="mb-2 flex items-center gap-2">
        <MessageSquare size={14} className="text-primary" />
        <span className="text-[13px] font-medium">Telegram</span>
        {state.configured && (
          <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
            state.verified
              ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
              : "bg-amber-500/15 text-amber-700 dark:text-amber-300"}`}>
            {state.verified ? "Tested" : "Not tested yet"}
          </span>
        )}
      </div>
      <p className="mb-3 text-[11.5px] text-muted-foreground">
        Free, and it pushes to your phone. Create a bot with @BotFather, send it a message,
        then paste its token here.
      </p>

      {state.configured ? (
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <label className={label}>Send a test to chat ID</label>
            <input className={input} placeholder="123456789" value={testTo}
              onChange={(e) => setTestTo(e.target.value)} />
          </div>
          <Button size="sm" variant="outline" disabled={!testTo.trim() || test.isPending}
            onClick={() => {
              setMsg(null)
              test.mutate(["telegram", testTo.trim()], {
                onSuccess: () => setMsg({ ok: true, text: "Test message sent." }),
                onError: (e) => setMsg({ ok: false, text: detail(e, "Could not send.") }),
              })
            }}>
            {test.isPending ? <Loader2 size={13} className="animate-spin" /> : "Test"}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => remove.mutate("telegram")}>
            <Trash2 size={13} />
          </Button>
        </div>
      ) : (
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <label className={label}>Bot token</label>
            <input className={`${input} font-mono text-xs`} type="password"
              placeholder="123456:ABC-DEF…" value={botToken}
              onChange={(e) => setBotToken(e.target.value)} />
          </div>
          <Button size="sm" disabled={!botToken.trim() || save.isPending}
            onClick={() => {
              setMsg(null)
              save.mutate(["telegram", { bot_token: botToken.trim() }] as Parameters<typeof setProvider>, {
                onError: (e) => setMsg({ ok: false, text: detail(e, "Could not save.") }),
              })
            }}>
            {save.isPending ? <Loader2 size={13} className="animate-spin" /> : "Save"}
          </Button>
        </div>
      )}

      {msg && (
        <p className={`mt-2 rounded-lg px-3 py-2 text-xs ${msg.ok
          ? "border border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
          : "border border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400"}`}>
          {msg.ok && <Check size={12} className="mr-1 inline" />}{msg.text}
        </p>
      )}
    </div>
  )
}

/** Where pages can be sent. Email, Slack and webhooks need no setup; these two do. */
export default function PagingChannelsPanel() {
  const { data: providers = [] } = useQuery({
    queryKey: ["paging-providers"], queryFn: listProviders,
  })
  const twilio = providers.find((p) => p.provider === "twilio")
  const telegram = providers.find((p) => p.provider === "telegram")

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-1 flex items-center gap-2">
        <Smartphone size={15} className="text-primary" />
        <h3 className="text-sm font-semibold">Ways to reach you</h3>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Email, Slack and webhooks work with no setup. Texts and Telegram need an account of
        your own — connect one here and your on-call policy can use it.
      </p>
      <div className="space-y-2">
        {twilio && <TwilioCard state={twilio} />}
        {telegram && <TelegramCard state={telegram} />}
      </div>
    </div>
  )
}
