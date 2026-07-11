import { useState } from "react"
import { Navigate } from "react-router-dom"
import { FlaskConical, Terminal, ListChecks } from "lucide-react"
import Inspector from "@/components/dev/Inspector"
import EvalRunner from "@/components/dev/EvalRunner"
import { useAuthStore } from "@/store/authStore"

type Tab = "inspector" | "evals"

const TABS: { key: Tab; label: string; Icon: typeof Terminal }[] = [
  { key: "inspector", label: "Prompt Inspector", Icon: Terminal },
  { key: "evals", label: "Evals", Icon: ListChecks },
]

/** The Dev Door (docs/EVAL-DRIVEN-DEV.md) — admin-only. The page guards on is_admin;
 * every /api/dev endpoint 403s a non-admin regardless. */
export default function Dev() {
  const isAdmin = useAuthStore((s) => s.user?.is_admin)
  const [tab, setTab] = useState<Tab>("inspector")

  if (isAdmin === false) return <Navigate to="/dashboard" replace />

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex items-center gap-2">
        <FlaskConical size={22} className="text-primary" />
        <h1 className="text-xl font-semibold text-foreground">Dev Door</h1>
        <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">admin</span>
      </div>

      <div className="flex gap-1 border-b border-border">
        {TABS.map(({ key, label, Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`-mb-px flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
              tab === key
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Icon size={16} />
            {label}
          </button>
        ))}
      </div>

      {tab === "inspector" ? <Inspector /> : <EvalRunner />}
    </div>
  )
}
