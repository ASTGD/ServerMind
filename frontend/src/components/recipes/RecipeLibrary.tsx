import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Sparkles, GitBranch, Globe, Rocket, ShieldCheck, HardDriveDownload, Lock, MoveRight } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { listRecipes, type Recipe } from "@/api/recipes"
import RunRecipeModal from "./RunRecipeModal"

/** Map a recipe's icon hint to a lucide icon (falls back to a generic sparkle). */
const ICONS: Record<string, LucideIcon> = {
  wordpress: Globe,
  github: GitBranch,
  harden: ShieldCheck,
  shield: ShieldCheck,
  backup: HardDriveDownload,
  ssl: Lock,
  migrate: MoveRight,
}
function iconFor(name: string): LucideIcon {
  return ICONS[name?.toLowerCase()] ?? Rocket
}

function RecipeCard({ recipe, onPick }: { recipe: Recipe; onPick: () => void }) {
  const Icon = iconFor(recipe.icon)
  return (
    <button
      onClick={onPick}
      className="group flex h-full flex-col rounded-xl border border-border bg-card p-4 text-left transition hover:border-primary/50 hover:shadow-sm"
    >
      <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
        <Icon size={18} />
      </div>
      <h3 className="text-sm font-semibold text-foreground">{recipe.title}</h3>
      <p className="mt-1 line-clamp-3 flex-1 text-xs text-muted-foreground">{recipe.summary}</p>
      <span className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-primary opacity-0 transition group-hover:opacity-100">
        <Sparkles size={12} /> Set up
      </span>
    </button>
  )
}

/** The one-click Recipes gallery — sits at the top of the Missions page. */
export default function RecipeLibrary() {
  const { data: recipes = [], isLoading } = useQuery({ queryKey: ["recipes"], queryFn: () => listRecipes() })
  const [active, setActive] = useState<Recipe | null>(null)

  if (isLoading || recipes.length === 0) return null

  return (
    <section className="mb-8">
      <div className="mb-3 flex items-center gap-2">
        <Sparkles size={18} className="text-primary" />
        <h2 className="text-lg font-semibold text-foreground">Recipes</h2>
        <span className="text-xs text-muted-foreground">— one-click jobs Ally runs for you</span>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {recipes.map((r) => (
          <RecipeCard key={r.slug} recipe={r} onPick={() => setActive(r)} />
        ))}
      </div>
      {active && <RunRecipeModal recipe={active} onClose={() => setActive(null)} />}
    </section>
  )
}
