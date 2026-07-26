import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Palette, Loader2, Check, Lock } from "lucide-react"
import { getBranding, updateBranding, type Branding } from "@/api/branding"
import { Button } from "@/components/ui"
import { useFeature } from "@/components/plan/FeatureLock"

const input =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
const label = "mb-1 block text-xs font-medium text-muted-foreground"

/**
 * White-label settings. These apply to what an agency's CLIENTS see — public status pages
 * and client reports — never to the app itself.
 */
export default function BrandingPanel() {
  const qc = useQueryClient()
  // Only removing OUR name is a paid switch; the rest of the branding stays open on every
  // plan, so a Pro customer can still brand their status page.
  const whiteLabel = useFeature("white_label")
  const { data } = useQuery({ queryKey: ["branding"], queryFn: getBranding })
  const [form, setForm] = useState<Partial<Branding>>({})
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (data) setForm(data)
  }, [data])

  const save = useMutation({
    mutationFn: () => updateBranding(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["branding"] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setError(typeof d === "string" ? d : "Could not save branding.")
    },
  })

  const color = form.primary_color || "#4f46e5"

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-1 flex items-center gap-2">
        <Palette size={15} className="text-primary" />
        <h3 className="text-sm font-semibold">Your branding</h3>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Used on anything your clients see — status pages and client reports. Your own view of
        ServerAlly does not change.
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={label}>Company name</label>
          <input className={input} placeholder="Acme Web Studio"
            value={form.company_name ?? ""}
            onChange={(e) => setForm({ ...form, company_name: e.target.value })} />
        </div>
        <div>
          <label className={label}>Brand colour</label>
          <div className="flex items-center gap-2">
            <input type="color" className="h-9 w-12 cursor-pointer rounded border border-border bg-background"
              value={color}
              onChange={(e) => setForm({ ...form, primary_color: e.target.value })} />
            <input className={`${input} font-mono text-xs`} placeholder="#4f46e5"
              value={form.primary_color ?? ""}
              onChange={(e) => setForm({ ...form, primary_color: e.target.value })} />
          </div>
        </div>
        <div className="sm:col-span-2">
          <label className={label}>Logo address <span className="text-muted-foreground/70">(optional)</span></label>
          <input className={`${input} font-mono text-xs`} placeholder="https://acme.com/logo.png"
            value={form.logo_url ?? ""}
            onChange={(e) => setForm({ ...form, logo_url: e.target.value })} />
        </div>
        <div>
          <label className={label}>Support link</label>
          <input className={`${input} font-mono text-xs`} placeholder="https://acme.com/support"
            value={form.support_url ?? ""}
            onChange={(e) => setForm({ ...form, support_url: e.target.value })} />
        </div>
        <div>
          <label className={label}>Support email</label>
          <input className={input} type="email" placeholder="help@acme.com"
            value={form.support_email ?? ""}
            onChange={(e) => setForm({ ...form, support_email: e.target.value })} />
        </div>
        <div className="sm:col-span-2">
          <label className={label}>Footer note <span className="text-muted-foreground/70">(optional)</span></label>
          <input className={input} placeholder="© Acme Web Studio — managed hosting"
            value={form.footer_text ?? ""}
            onChange={(e) => setForm({ ...form, footer_text: e.target.value })} />
        </div>
      </div>

      <label className={`mt-3 flex items-start gap-2.5 rounded-lg border border-border p-3 ${
        whiteLabel.allowed ? "cursor-pointer" : "cursor-not-allowed opacity-60"}`}>
        <input type="checkbox" className="mt-0.5"
          disabled={!whiteLabel.allowed}
          checked={!!form.hide_serverally_branding}
          onChange={(e) => setForm({ ...form, hide_serverally_branding: e.target.checked })} />
        <span>
          <span className="flex flex-wrap items-center gap-1.5 text-[13px] font-medium">
            Remove “Monitored by ServerAlly”
            {!whiteLabel.allowed && (
              <span className="flex items-center gap-1 rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
                <Lock size={9} /> {whiteLabel.requiredPlan}
              </span>
            )}
          </span>
          <span className="block text-[11.5px] text-muted-foreground">
            {whiteLabel.allowed
              ? "Your clients see only your brand on status pages and reports."
              : `Included in ${whiteLabel.requiredPlan}. Everything else here works on your plan.`}
          </span>
        </span>
      </label>

      {/* A live preview, so the effect is obvious before anything is published. */}
      <div className="mt-3 rounded-lg border border-border bg-background p-3">
        <p className={label}>Your clients will see</p>
        <div className="flex items-center gap-2">
          {form.logo_url ? (
            <img src={form.logo_url} alt="" className="h-6 w-auto max-w-[120px] object-contain"
              onError={(e) => { (e.target as HTMLImageElement).style.display = "none" }} />
          ) : null}
          <span className="text-sm font-semibold" style={{ color }}>
            {form.company_name || "Your company"}
          </span>
        </div>
        <p className="mt-1.5 text-[11px] text-muted-foreground">
          {form.footer_text || " "}
          {!form.hide_serverally_branding && (
            <span className="ml-2 opacity-70">· Monitored by ServerAlly</span>
          )}
        </p>
      </div>

      {error && (
        <p className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      <div className="mt-3 flex justify-end">
        <Button size="sm" disabled={save.isPending} onClick={() => { setError(null); save.mutate() }}>
          {save.isPending ? <><Loader2 size={14} className="animate-spin" /> Saving…</>
            : saved ? <><Check size={14} /> Saved</> : "Save branding"}
        </Button>
      </div>
    </div>
  )
}
