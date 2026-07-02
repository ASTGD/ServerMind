import { cn } from "@/lib/utils"
import { Bot, User, AlertTriangle, CheckCircle2, XCircle, Server as ServerIcon, ArrowRight, Layers } from "lucide-react"
import ScriptCard from "./ScriptCard"
import type { GenerateScriptResult } from "@/types"

export interface Handoff {
  serverId: string
  serverName: string
  prompt: string
}

export interface BatchSpec {
  prompt: string
  targets: { serverId: string; serverName: string }[]
}

export type ChatMessageData =
  | { id: string; role: "user"; content: string }
  | { id: string; role: "assistant"; kind: "thinking" }
  | { id: string; role: "assistant"; kind: "clarification"; message: string }
  | { id: string; role: "assistant"; kind: "output"; content: string; done?: boolean }
  | { id: string; role: "assistant"; kind: "complete"; explanation: string; status: string; suggestions: string[] }
  | { id: string; role: "assistant"; kind: "answer"; content: string; suggestions: string[]; handoff?: Handoff | null; batch?: BatchSpec | null; script?: GenerateScriptResult | null }
  | { id: string; role: "assistant"; kind: "blocked"; reason: string }
  | { id: string; role: "assistant"; kind: "quota"; message: string }
  | { id: string; role: "assistant"; kind: "error"; message: string }

interface Props {
  message: ChatMessageData
  onSuggestion?: (text: string) => void
  onHandoff?: (handoff: Handoff) => void
  onBatch?: (batch: BatchSpec) => void
}

export default function ChatMessage({ message, onSuggestion, onHandoff, onBatch }: Props) {
  const isUser = message.role === "user"

  return (
    <div className={cn("flex gap-3", isUser && "flex-row-reverse")}>
      {/* Avatar */}
      <div className={cn(
        "flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
        isUser ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
      )}>
        {isUser ? <User size={13} /> : <Bot size={13} />}
      </div>

      {/* Bubble */}
      <div className={cn("max-w-[80%] space-y-1", isUser && "items-end")}>
        {message.role === "user" && (
          <div className="rounded-2xl rounded-tr-sm bg-primary px-3.5 py-2 text-sm text-primary-foreground">
            {message.content}
          </div>
        )}

        {message.role === "assistant" && message.kind === "thinking" && (
          <div className="flex items-center gap-2 rounded-2xl rounded-tl-sm bg-muted px-3.5 py-2 text-sm text-muted-foreground">
            <span className="flex gap-0.5">
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.3s]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.15s]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground" />
            </span>
            Thinking…
          </div>
        )}

        {message.role === "assistant" && message.kind === "clarification" && (
          <div className="rounded-2xl rounded-tl-sm bg-muted px-3.5 py-2 text-sm text-foreground">
            {message.message}
          </div>
        )}

        {message.role === "assistant" && message.kind === "output" && (
          <pre className="max-h-64 overflow-y-auto whitespace-pre-wrap break-all rounded-lg bg-[#0d0d0d] p-3 font-mono text-xs text-green-400">
            {message.content}
          </pre>
        )}

        {message.role === "assistant" && message.kind === "complete" && (
          <div className="space-y-2">
            <div className={cn(
              "flex items-start gap-2 rounded-2xl rounded-tl-sm px-3.5 py-2 text-sm",
              message.status === "success"
                ? "bg-green-500/10 text-green-700 dark:text-green-400"
                : message.status === "failed"
                  ? "bg-destructive/10 text-destructive"
                  : "bg-yellow-500/10 text-yellow-700 dark:text-yellow-400",
            )}>
              {message.status === "success"
                ? <CheckCircle2 size={14} className="mt-0.5 shrink-0" />
                : message.status === "failed"
                  ? <XCircle size={14} className="mt-0.5 shrink-0" />
                  : <AlertTriangle size={14} className="mt-0.5 shrink-0" />}
              <span>{message.explanation}</span>
            </div>
            {message.suggestions.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {message.suggestions.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => onSuggestion?.(s)}
                    className="rounded-full border border-border bg-background px-2.5 py-1 text-xs text-muted-foreground hover:border-primary/50 hover:text-foreground transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {message.role === "assistant" && message.kind === "answer" && (
          <div className="space-y-2">
            <div className="whitespace-pre-wrap rounded-2xl rounded-tl-sm bg-muted px-3.5 py-2 text-sm text-foreground">
              {message.content}
            </div>
            {message.script && <ScriptCard script={message.script} />}
            {message.handoff && (
              <button
                onClick={() => onHandoff?.(message.handoff!)}
                className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-indigo-500 to-violet-500 px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90"
              >
                <ServerIcon size={13} />
                Run on {message.handoff.serverName}
                <ArrowRight size={13} />
              </button>
            )}
            {message.batch && message.batch.targets.length > 0 && (
              <div className="rounded-xl border border-indigo-500/25 bg-indigo-500/5 p-3">
                <p className="mb-2 text-xs font-medium text-foreground">
                  Run on {message.batch.targets.length} servers
                </p>
                <div className="mb-2.5 flex flex-wrap gap-1">
                  {message.batch.targets.map((t) => (
                    <span
                      key={t.serverId}
                      className="rounded-full border border-border bg-background px-2 py-0.5 text-[11px] text-muted-foreground"
                    >
                      {t.serverName}
                    </span>
                  ))}
                </div>
                <button
                  onClick={() => onBatch?.(message.batch!)}
                  className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-indigo-500 to-violet-500 px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90"
                >
                  <Layers size={13} />
                  Run on all
                  <ArrowRight size={13} />
                </button>
              </div>
            )}
            {message.suggestions.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {message.suggestions.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => onSuggestion?.(s)}
                    className="rounded-full border border-border bg-background px-2.5 py-1 text-xs text-muted-foreground hover:border-primary/50 hover:text-foreground transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {message.role === "assistant" && message.kind === "blocked" && (
          <div className="flex items-start gap-2 rounded-2xl rounded-tl-sm bg-destructive/10 px-3.5 py-2 text-sm text-destructive">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            <div>
              <p className="font-medium">Command blocked</p>
              <p className="text-xs opacity-80">{message.reason}</p>
            </div>
          </div>
        )}

        {/* Out of Ally actions this month (the quota wall — docs/AI-METERING.md) */}
        {message.role === "assistant" && message.kind === "quota" && (
          <div className="flex items-start gap-2 rounded-2xl rounded-tl-sm border border-amber-500/25 bg-amber-500/10 px-3.5 py-2 text-sm text-amber-700 dark:text-amber-400">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            <div>
              <p className="font-medium">Out of Ally actions</p>
              <p className="text-xs opacity-90">{message.message}</p>
            </div>
          </div>
        )}

        {message.role === "assistant" && message.kind === "error" && (
          <div className="rounded-2xl rounded-tl-sm bg-destructive/10 px-3.5 py-2 text-sm text-destructive">
            {message.message}
          </div>
        )}
      </div>
    </div>
  )
}
