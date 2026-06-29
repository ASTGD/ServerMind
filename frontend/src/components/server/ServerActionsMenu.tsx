import { useState, useRef, useEffect } from "react"
import { MoreHorizontal, RefreshCw, Search, Pencil, KeyRound, Trash2, Loader2 } from "lucide-react"

interface Props {
  onTest: () => void
  onDetect: () => void
  onEdit: () => void
  onCredentials: () => void
  onDelete: () => void
  testPending?: boolean
  detectPending?: boolean
}

/** Overflow "⋯" menu for occasional server actions — keeps them out of the main row. */
export default function ServerActionsMenu({
  onTest,
  onDetect,
  onEdit,
  onCredentials,
  onDelete,
  testPending,
  detectPending,
}: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", onClick)
    return () => document.removeEventListener("mousedown", onClick)
  }, [])

  const item = "flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-foreground hover:bg-accent"
  function run(fn: () => void) {
    fn()
    setOpen(false)
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="More actions"
        className="flex items-center rounded-md border border-border px-2.5 py-1.5 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
      >
        <MoreHorizontal size={16} />
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 w-52 overflow-hidden rounded-lg border border-border bg-card py-1 shadow-lg">
          <button className={item} onClick={() => run(onTest)}>
            {testPending ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            Test connection
          </button>
          <button className={item} onClick={() => run(onDetect)}>
            {detectPending ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
            Detect OS
          </button>
          <button className={item} onClick={() => run(onEdit)}>
            <Pencil size={14} /> Edit server
          </button>
          <button className={item} onClick={() => run(onCredentials)}>
            <KeyRound size={14} /> Update credentials
          </button>
          <div className="my-1 border-t border-border" />
          <button className={`${item} text-destructive`} onClick={() => run(onDelete)}>
            <Trash2 size={14} /> Delete server
          </button>
        </div>
      )}
    </div>
  )
}
