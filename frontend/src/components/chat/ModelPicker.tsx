import { useEffect, useRef, useState } from "react"
import { Check, ChevronDown, Cpu, Sparkles } from "lucide-react"
import { useAssistantStore, type ModelChoice } from "@/store/assistantStore"

/** The four pickable models, fastest → smartest. The real model names (Haiku/Sonnet/
 *  Opus/Fable) are deliberately hidden behind friendly labels + a plain-English hint. */
const MODELS: { key: Exclude<ModelChoice, "auto">; label: string; hint: string }[] = [
  { key: "fast", label: "Fast", hint: "Quickest and lowest cost — simple, everyday tasks" },
  { key: "smart", label: "Smart", hint: "Balanced speed and skill — the everyday default" },
  { key: "expert", label: "Expert", hint: "Deeper thinking for tricky or important jobs" },
  { key: "genius", label: "Genius", hint: "Most thorough (slower, higher cost) — hardest, high-stakes work" },
]

/**
 * Ally's model picker (Claude-Code-style). Two modes:
 *  - Auto: the automatic model ladder decides per task (the model list is shown but disabled).
 *  - Manual: pick one model for the whole conversation.
 * The choice lives in assistantStore and is sent with each chat/mission frame. The safety
 * verify gate always stays on the top model regardless of the pick.
 */
export default function ModelPicker() {
  const choice = useAssistantStore((s) => s.modelChoice)
  const setChoice = useAssistantStore((s) => s.setModelChoice)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  // Remember the last manual pick so toggling Auto → Manual restores it (default: Smart).
  const lastManual = useRef<Exclude<ModelChoice, "auto">>("smart")
  if (choice !== "auto") lastManual.current = choice

  const manual = choice !== "auto"
  const current = manual ? MODELS.find((m) => m.key === choice) : null

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", onDown)
    return () => document.removeEventListener("mousedown", onDown)
  }, [open])

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        title="Choose which model Ally uses"
        className="flex items-center gap-1.5 rounded-full border border-border bg-background px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-accent"
      >
        {manual ? <Cpu size={13} className="text-primary" /> : <Sparkles size={13} className="text-primary" />}
        <span>{manual ? current?.label : "Auto"}</span>
        <ChevronDown size={13} className="text-muted-foreground" />
      </button>

      {open && (
        <div className="absolute bottom-full left-0 z-50 mb-1.5 w-72 rounded-xl border border-border bg-card p-2 shadow-xl">
          {/* Auto / Manual toggle */}
          <div className="mb-2 flex gap-1 rounded-lg bg-muted p-1">
            <button
              onClick={() => setChoice("auto")}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors ${
                !manual ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Sparkles size={13} /> Auto
            </button>
            <button
              onClick={() => setChoice(lastManual.current)}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors ${
                manual ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Cpu size={13} /> Manual
            </button>
          </div>

          {!manual && (
            <p className="px-2 pb-1.5 text-xs text-muted-foreground">
              Ally chooses the best model for each task.
            </p>
          )}

          {/* The four models — selectable in Manual, dimmed/disabled in Auto. */}
          <div className={manual ? "" : "pointer-events-none opacity-50"}>
            {MODELS.map((m) => {
              const active = manual && choice === m.key
              return (
                <button
                  key={m.key}
                  onClick={() => setChoice(m.key)}
                  disabled={!manual}
                  className={`flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left transition-colors ${
                    active ? "bg-accent" : "hover:bg-accent/60"
                  }`}
                >
                  <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center">
                    {active && <Check size={14} className="text-primary" />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium text-foreground">{m.label}</span>
                    <span className="block text-xs text-muted-foreground">{m.hint}</span>
                  </span>
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
