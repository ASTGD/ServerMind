import { cn } from "@/lib/utils"
import { Sparkles, AlertTriangle, CheckCircle2, XCircle, Server as ServerIcon, ArrowRight, Layers, Loader2 } from "lucide-react"
import ScriptCard from "./ScriptCard"
import MissionCard, { type MissionOffer } from "./MissionCard"
import MissionProgress, { type MissionState } from "./MissionProgress"
import { HighlightServerNames, type MentionServer } from "./serverMentions"
import Markdown from "./Markdown"
import ArtifactPanel, { type Artifact } from "./ArtifactPanel"
import ServerTag from "./ServerTag"
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

/** Which resource a message is about — rendered as a stable-colored server chip so the
 *  user can tell, at a glance, what each line concerns (like avatars in a group chat). */
export interface MsgServer {
  serverId?: string | null
  serverName?: string | null
}

export type ChatMessageData =
  | ({ id: string; role: "user"; content: string } & MsgServer)
  | { id: string; role: "assistant"; kind: "thinking" }
  | ({ id: string; role: "assistant"; kind: "clarification"; message: string; askServers?: { id: string; name: string }[]; options?: string[] } & MsgServer)
  | { id: string; role: "assistant"; kind: "output"; content: string; done?: boolean }
  | { id: string; role: "assistant"; kind: "artifact"; artifact: Artifact }
  | ({ id: string; role: "assistant"; kind: "complete"; explanation: string; status: string; suggestions: string[] } & MsgServer)
  | ({ id: string; role: "assistant"; kind: "answer"; content: string; suggestions: string[]; handoff?: Handoff | null; batch?: BatchSpec | null; script?: GenerateScriptResult | null } & MsgServer)
  | { id: string; role: "assistant"; kind: "blocked"; reason: string }
  | { id: string; role: "assistant"; kind: "quota"; message: string }
  | { id: string; role: "assistant"; kind: "mission_offer"; offer: MissionOffer }
  | { id: string; role: "assistant"; kind: "mission"; mission: MissionState }
  | { id: string; role: "assistant"; kind: "error"; message: string }
  // Context marker — shown when the ONE continuous Ally conversation switches target
  // ("Now talking to TestServer3"). Never sent to the AI, never persisted.
  | { id: string; role: "system"; kind: "divider"; label: string }

interface Props {
  message: ChatMessageData
  onSuggestion?: (text: string) => void
  onHandoff?: (handoff: Handoff) => void
  onBatch?: (batch: BatchSpec) => void
  onStartMission?: (offer: MissionOffer) => void
  /** Stop THIS card's mission (several may run at once — routed by mission id). */
  onStopMission?: (mission: MissionState) => void
  /** Approve THIS card's paused step (in-card approval). */
  onApproveMission?: (mission: MissionState) => void
  /** Known servers — their names render as clickable chips in text bubbles. */
  servers?: MentionServer[]
  onServerClick?: (id: string) => void
  /** A candidate server chip under a clarification was picked (Ally asked "which one?"). */
  onPickServer?: (id: string) => void
}

/** Small pill button used for follow-up suggestions and tappable answer options. */
function Chips({ items, onPick }: { items: string[]; onPick?: (t: string) => void }) {
  if (!items.length) return null
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((s, i) => (
        <button
          key={i}
          onClick={() => onPick?.(s)}
          className="rounded-full border border-border bg-background px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
        >
          {s}
        </button>
      ))}
    </div>
  )
}

/**
 * One line in the conversation, styled like a document (Claude / ChatGPT) rather than
 * chat bubbles: Ally's replies are plain flowing text under a small "Ally" header; the
 * user's messages are a soft right-aligned block; results are a quiet status line, not a
 * big colored box. Structured work (mission cards, command output) keeps its own card.
 */
export default function ChatMessage({ message, onSuggestion, onHandoff, onBatch, onStartMission, onStopMission, onApproveMission, servers, onServerClick, onPickServer }: Props) {
  const names = servers ?? []
  /** Plain text with server names chipped — for USER messages (users don't write markdown). */
  const withNames = (text: string) =>
    names.length ? (
      <HighlightServerNames text={text} servers={names} onServerClick={onServerClick} />
    ) : (
      text
    )
  /** Ally's prose → rich, readable markdown (headings, bold, lists…) with server chips
   *  preserved. Color is inherited so a status line keeps its tint. */
  const allyText = (text: string) => <Markdown text={text} servers={names} onServerClick={onServerClick} />

  // Target-switch divider — a centered label, no avatar, no bubble.
  if (message.role === "system" && message.kind === "divider") {
    return (
      <div className="flex items-center gap-3 py-1" role="separator">
        <div className="h-px flex-1 bg-border" />
        <span className="shrink-0 text-[11px] font-medium text-muted-foreground">{message.label}</span>
        <div className="h-px flex-1 bg-border" />
      </div>
    )
  }

  // ── USER — a soft, understated block on the right (not a bright bubble) ──────────
  if (message.role === "user") {
    return (
      <div className="flex flex-col items-end gap-1">
        {message.serverName && <ServerTag name={message.serverName} />}
        <div className="max-w-[82%] whitespace-pre-wrap rounded-2xl rounded-tr-sm border border-border bg-muted px-3.5 py-2 text-[15px] leading-relaxed text-foreground">
          {withNames(message.content)}
        </div>
      </div>
    )
  }

  // ── ASSISTANT — structured work stands alone (its own card, no "Ally" header) ────
  if (message.kind === "mission_offer") {
    return <MissionCard offer={message.offer} onStart={(o) => onStartMission?.(o)} />
  }
  if (message.kind === "mission") {
    return (
      <MissionProgress
        mission={message.mission}
        onStop={() => onStopMission?.(message.mission)}
        onApprove={() => onApproveMission?.(message.mission)}
        onOption={(text) => onSuggestion?.(text)}
      />
    )
  }
  if (message.kind === "output") {
    // The live command run — Ally's actual work. Shown in the Workspace (routed there),
    // streaming while it runs and kept as a finished record (done) afterwards.
    const done = message.done
    return (
      <div className="overflow-hidden rounded-lg border border-border">
        <div className="flex items-center gap-2 border-b border-border bg-muted/50 px-3 py-1.5 text-xs font-medium text-muted-foreground">
          {done ? (
            <CheckCircle2 size={13} className="text-emerald-500" />
          ) : (
            <Loader2 size={13} className="animate-spin text-primary" />
          )}
          <span>{done ? "Command output" : "Running on the server…"}</span>
        </div>
        <pre className="max-h-72 overflow-y-auto whitespace-pre-wrap break-all bg-[#0d0d0d] p-3 font-mono text-xs text-green-400">
          {message.content || (done ? "(no output)" : "…")}
        </pre>
      </div>
    )
  }
  // A table or chart Ally chose to show — rendered as a Workspace panel (Track B Phase 2).
  if (message.kind === "artifact") {
    return <ArtifactPanel artifact={message.artifact} />
  }
  // Ally is thinking — a quiet transient line (replaced by the real reply).
  if (message.kind === "thinking") {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span className="flex gap-0.5">
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.3s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.15s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground" />
        </span>
        Thinking…
      </div>
    )
  }

  // ── ASSISTANT conversation — document style: an "Ally" header + flowing text ─────
  const allyHeader = (
    <div className="flex items-center gap-2">
      <div className="flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-md bg-gradient-to-br from-indigo-500 to-violet-500 text-white">
        <Sparkles size={13} />
      </div>
      <span className="text-[13px] font-medium text-foreground">Ally</span>
      {"serverName" in message && message.serverName && <ServerTag name={message.serverName} />}
    </div>
  )

  let body: React.ReactNode = null

  if (message.kind === "answer") {
    body = (
      <div className="space-y-2.5">
        {allyText(message.content)}
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
        <Chips items={message.suggestions} onPick={onSuggestion} />
      </div>
    )
  } else if (message.kind === "complete") {
    const Icon = message.status === "success" ? CheckCircle2 : message.status === "failed" ? XCircle : AlertTriangle
    const tone =
      message.status === "success"
        ? "text-green-600 dark:text-green-400"
        : message.status === "failed"
          ? "text-destructive"
          : "text-amber-600 dark:text-amber-400"
    body = (
      <div className="space-y-2.5">
        <div className="flex items-start gap-2">
          <Icon size={17} className={cn("mt-0.5 shrink-0", tone)} />
          <div className="min-w-0 flex-1">{allyText(message.explanation)}</div>
        </div>
        <Chips items={message.suggestions} onPick={onSuggestion} />
      </div>
    )
  } else if (message.kind === "clarification") {
    body = (
      <div className="space-y-2.5">
        {allyText(message.message)}
        {/* Ally asked "which server?" — one click picks it (sets focus + retries). */}
        {message.askServers && message.askServers.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {message.askServers.map((s) => (
              <button
                key={s.id}
                onClick={() => onPickServer?.(s.id)}
                className="transition-transform hover:scale-[1.03]"
                title={`Continue on ${s.name}`}
              >
                <ServerTag name={s.name} />
              </button>
            ))}
          </div>
        )}
        {/* Track C: tappable answer options — clicking sends that text as the reply. */}
        {message.options && message.options.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {message.options.map((o, i) => (
              <button
                key={i}
                onClick={() => onSuggestion?.(o)}
                className="rounded-full border border-primary/40 bg-primary/5 px-3 py-1 text-xs text-foreground transition-colors hover:border-primary hover:bg-primary/10"
              >
                {o}
              </button>
            ))}
          </div>
        )}
      </div>
    )
  } else if (message.kind === "blocked") {
    body = (
      <div className="flex items-start gap-2 border-l-2 border-destructive bg-destructive/5 py-1.5 pl-3 text-sm text-destructive">
        <AlertTriangle size={15} className="mt-0.5 shrink-0" />
        <div>
          <p className="font-medium">Command blocked</p>
          <p className="text-xs opacity-80">{message.reason}</p>
        </div>
      </div>
    )
  } else if (message.kind === "quota") {
    body = (
      <div className="flex items-start gap-2 border-l-2 border-amber-500 bg-amber-500/5 py-1.5 pl-3 text-sm text-amber-700 dark:text-amber-400">
        <AlertTriangle size={15} className="mt-0.5 shrink-0" />
        <div>
          <p className="font-medium">Out of Ally actions</p>
          <p className="text-xs opacity-90">{message.message}</p>
        </div>
      </div>
    )
  } else if (message.kind === "error") {
    body = (
      <div className="border-l-2 border-destructive bg-destructive/5 py-1.5 pl-3 text-sm text-destructive">
        {message.message}
      </div>
    )
  }

  return (
    <div className="space-y-2.5">
      {allyHeader}
      {body}
    </div>
  )
}
