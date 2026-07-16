import { useState } from "react"
import { Navigate } from "react-router-dom"
import { FlaskConical, Terminal, ListChecks, Activity as ActivityIcon, Scale, Users, Receipt, LayoutDashboard } from "lucide-react"
import Inspector from "@/components/dev/Inspector"
import EvalRunner from "@/components/dev/EvalRunner"
import Activity from "@/components/dev/Activity"
import ProviderAb from "@/components/dev/ProviderAb"
import AdminOverview from "@/components/dev/AdminOverview"
import AdminUsers from "@/components/dev/AdminUsers"
import AdminEntitlements from "@/components/dev/AdminEntitlements"
import { useAuthStore } from "@/store/authStore"

type Tab = "overview" | "users" | "entitlements" | "inspector" | "evals" | "activity" | "cost-ab"

const TABS: { key: Tab; label: string; Icon: typeof Terminal }[] = [
  // Operator console (SAAS-LAUNCH-PLAN §5) — support/ops, never billing.
  { key: "overview", label: "Overview", Icon: LayoutDashboard },
  { key: "users", label: "Users", Icon: Users },
  { key: "entitlements", label: "Billing events", Icon: Receipt },
  // Ally engineering (EVAL-DRIVEN-DEV).
  { key: "inspector", label: "Prompt Inspector", Icon: Terminal },
  { key: "evals", label: "Evals", Icon: ListChecks },
  { key: "activity", label: "Activity", Icon: ActivityIcon },
  { key: "cost-ab", label: "Cost A/B", Icon: Scale },
]

/** The Dev Door (docs/EVAL-DRIVEN-DEV.md) — admin-only. The page guards on is_admin;
 * every /api/dev endpoint 403s a non-admin regardless. */
export default function Dev() {
  const isAdmin = useAuthStore((s) => s.user?.is_admin)
  const [tab, setTab] = useState<Tab>("overview")

  if (isAdmin === false) return <Navigate to="/dashboard" replace />

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex items-center gap-2">
        <FlaskConical size={22} className="text-primary" />
        <h1 className="text-xl font-semibold text-foreground">Dev Door</h1>
        <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">admin</span>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-border">
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

      {tab === "overview" && <AdminOverview />}
      {tab === "users" && <AdminUsers />}
      {tab === "entitlements" && <AdminEntitlements />}
      {tab === "inspector" && <Inspector />}
      {tab === "evals" && <EvalRunner />}
      {tab === "activity" && <Activity />}
      {tab === "cost-ab" && <ProviderAb />}
    </div>
  )
}
