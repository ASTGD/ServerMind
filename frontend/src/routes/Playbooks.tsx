import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Search, Loader2, BookOpen, Terminal, Monitor } from "lucide-react"
import { listPlaybooks, listCategories } from "@/api/playbooks"
import PlaybookCard from "@/components/playbooks/PlaybookCard"

type OsTab = "all" | "linux" | "windows"

const OS_TABS: { value: OsTab; label: string; icon: React.ReactNode }[] = [
  { value: "all", label: "All", icon: <BookOpen className="h-3.5 w-3.5" /> },
  { value: "linux", label: "Linux", icon: <Terminal className="h-3.5 w-3.5" /> },
  { value: "windows", label: "Windows", icon: <Monitor className="h-3.5 w-3.5" /> },
]

const CATEGORY_LABELS: Record<string, string> = {
  setup: "Setup",
  security: "Security",
  backup: "Backup",
  deployment: "Deployment",
  monitoring: "Monitoring",
  maintenance: "Maintenance",
}

export default function Playbooks() {
  const [osTab, setOsTab] = useState<OsTab>("all")
  const [category, setCategory] = useState<string | null>(null)
  const [search, setSearch] = useState("")

  const { data: categories = [] } = useQuery({
    queryKey: ["playbook-categories"],
    queryFn: listCategories,
  })

  const { data: playbooks = [], isLoading } = useQuery({
    queryKey: ["playbooks", osTab, category, search],
    queryFn: () =>
      listPlaybooks({
        os_family: osTab === "all" ? undefined : osTab,
        category: category ?? undefined,
        q: search || undefined,
      }),
    staleTime: 60_000,
  })

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Playbooks</h1>
        <p className="text-muted-foreground text-sm mt-1">
          One-click scripts for common server administration tasks
        </p>
      </div>

      {/* OS tabs + Search */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex rounded-lg border border-border overflow-hidden">
          {OS_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setOsTab(tab.value)}
              className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors ${
                osTab === tab.value
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-72">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search playbooks..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-lg border border-border bg-background text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
        </div>
      </div>

      {/* Category chips */}
      {categories.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setCategory(null)}
            className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
              category === null
                ? "bg-primary/10 text-primary border-primary/30 font-medium"
                : "text-muted-foreground border-border hover:border-primary/30 hover:text-foreground"
            }`}
          >
            All categories
          </button>
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setCategory(cat === category ? null : cat)}
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                category === cat
                  ? "bg-primary/10 text-primary border-primary/30 font-medium"
                  : "text-muted-foreground border-border hover:border-primary/30 hover:text-foreground"
              }`}
            >
              {CATEGORY_LABELS[cat] ?? cat}
            </button>
          ))}
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-24 text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin mr-2" />
          Loading playbooks...
        </div>
      )}

      {/* Empty state */}
      {!isLoading && playbooks.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <BookOpen className="h-10 w-10 text-muted-foreground/40 mb-3" />
          <p className="text-muted-foreground font-medium">No playbooks found</p>
          <p className="text-muted-foreground/60 text-sm mt-1">
            Try adjusting your filters or search query
          </p>
        </div>
      )}

      {/* Grid */}
      {!isLoading && playbooks.length > 0 && (
        <div>
          <p className="text-xs text-muted-foreground mb-4">
            {playbooks.length} playbook{playbooks.length !== 1 ? "s" : ""}
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {playbooks.map((pb) => (
              <PlaybookCard key={pb.id} playbook={pb} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
