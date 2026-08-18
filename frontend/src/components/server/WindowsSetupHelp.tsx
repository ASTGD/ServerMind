import { useQuery } from "@tanstack/react-query"
import { Check, Copy, Terminal } from "lucide-react"
import { useState } from "react"

import { getWindowsSetup } from "@/api/servers"

/**
 * The one step nobody can do for the customer.
 *
 * A Linux server needs nothing done to it — SSH is already listening. Windows is not like
 * that, and this form used to say nothing at all: it filled in port 5985 and hoped. When it
 * failed the customer got a library exception and no idea what to do.
 *
 * Remote management cannot be turned on remotely when nothing is on yet — that is the shape
 * of the problem, not a gap. So the honest fix is to hand over the exact command, correct
 * for a cloud VM, scoped to our own address, ready to copy.
 */
export function WindowsSetupHelp({ port }: { port: number }) {
  const [copied, setCopied] = useState(false)
  const { data } = useQuery({
    queryKey: ["windows-setup", port],
    queryFn: () => getWindowsSetup(port),
    staleTime: 60 * 60 * 1000,
  })

  if (!data) return null

  async function copy() {
    if (!data) return
    await navigator.clipboard.writeText(data.command)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="rounded-lg border border-border bg-muted/40 p-3">
      <div className="mb-2 flex items-center gap-2">
        <Terminal className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium text-foreground">
          First, run this once on the Windows server
        </span>
      </div>

      <p className="mb-2 text-xs text-muted-foreground">{data.note}</p>

      <div className="relative">
        <pre className="overflow-x-auto rounded-md border border-border bg-background p-2.5 pr-10 text-[11px] leading-relaxed text-foreground">
          <code>{data.command}</code>
        </pre>
        <button
          type="button"
          onClick={copy}
          title="Copy"
          className="absolute right-1.5 top-1.5 rounded-md border border-border bg-card p-1.5 text-muted-foreground hover:text-foreground"
        >
          {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
        </button>
      </div>

      {data.scoped ? (
        <p className="mt-2 text-xs text-muted-foreground">
          This lets in <span className="font-mono text-foreground">{data.address}</span> — ServerAlly
          — and nobody else.
        </p>
      ) : (
        // Never silently print "Any": that would be us telling somebody to publish their
        // Windows login to the internet.
        <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">{data.unscoped_warning}</p>
      )}

      <details className="mt-2">
        <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
          Not using the built-in Administrator account?
        </summary>
        <pre className="mt-1.5 overflow-x-auto rounded-md border border-border bg-background p-2.5 text-[11px] leading-relaxed text-muted-foreground">
          <code>{data.other_admin_note}</code>
        </pre>
      </details>
    </div>
  )
}
