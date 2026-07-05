import { apiClient } from "./client"

export interface RecipeVariable {
  name: string
  required: boolean
  default: string
}

/** A Recipe = a goal-oriented mission skill promoted into the one-click gallery. */
export interface Recipe {
  slug: string
  title: string
  summary: string
  icon: string
  os_family: string // 'linux' | 'windows' | 'any'
  budget: number
  variables: RecipeVariable[]
  goal_template: string
}

/** List recipes, optionally OS-gated against a target server's os_type. */
export async function listRecipes(os?: string | null): Promise<Recipe[]> {
  const { data } = await apiClient.get<Recipe[]>("/api/recipes", {
    params: os ? { os } : undefined,
  })
  return data
}

/**
 * Fill a recipe's variables into its goal_template, producing the chat message that
 * starts the mission. Runs entirely client-side (like RunPlaybookModal's access-card
 * fill) — nothing round-trips the backend until it's sent as a normal chat message.
 *
 * Values are resolved in the recipe's declared order so a later variable's default may
 * reference an earlier one (e.g. `title` defaults to `{{domain}}`). A blank optional
 * with no default is dropped from the sentence rather than left as an empty `''`.
 */
export function composeRecipeMessage(recipe: Recipe, values: Record<string, string>): string {
  const resolved: Record<string, string> = {}
  const fillRefs = (tpl: string): string =>
    tpl.replace(/\{\{(\w+)\}\}/g, (_m, k: string) => resolved[k] ?? "")
  for (const v of recipe.variables) {
    let val = (values[v.name] ?? "").trim()
    if (!val && v.default) val = fillRefs(v.default).trim()
    resolved[v.name] = val
  }
  return fillRefs(recipe.goal_template).replace(/\s+/g, " ").trim()
}

/** Required variables the user left blank — block submit until empty. */
export function missingRequired(recipe: Recipe, values: Record<string, string>): string[] {
  return recipe.variables
    .filter((v) => v.required && !(values[v.name] ?? "").trim())
    .map((v) => v.name)
}
