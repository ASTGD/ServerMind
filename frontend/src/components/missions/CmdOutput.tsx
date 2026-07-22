import { cn } from "@/lib/utils"

/**
 * The dark terminal block a mission step expands into — the (already-redacted)
 * command plus its output tail. Shared by the live mission card, the in-card
 * approval box, and the mission-detail transcript so they stay identical.
 * Deliberately always-dark (terminal surface, like xterm) in both themes.
 */
export default function CmdOutput({
  cmd,
  output,
  className,
}: {
  cmd?: string
  output?: string
  className?: string
}) {
  if (!cmd && !output) return null
  return (
    <div className={cn("space-y-1", className)}>
      {cmd && (
        <pre className="overflow-x-auto rounded-md bg-[#0d0d0d] px-2.5 py-1.5 font-mono text-xs text-zinc-300">
          $ {cmd}
        </pre>
      )}
      {output && (
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-md bg-[#0d0d0d] px-2.5 py-1.5 font-mono text-xs text-zinc-400">
          {output}
        </pre>
      )}
    </div>
  )
}
