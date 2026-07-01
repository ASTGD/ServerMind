import { useMemo, useState } from "react"
import { useParams } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { formatDistanceToNow } from "date-fns"
import {
  Shield,
  ShieldAlert,
  ShieldCheck,
  AlertOctagon,
  AlertTriangle,
  AlertCircle,
  Info,
  CheckCircle2,
  HelpCircle,
  Loader2,
  RefreshCw,
  Play,
  Copy,
  Check,
  ChevronDown,
  ChevronRight,
  Clock,
  XCircle,
} from "lucide-react"
import {
  listSecurityScans,
  runSecurityScan,
  type SecurityScan,
  type Finding,
  type Severity,
} from "@/api/security"

// ── Severity / grade visual config ──────────────────────────────────────────

const SEVERITY_META: Record<
  Severity,
  { label: string; text: string; bg: string; border: string; Icon: typeof AlertTriangle }
> = {
  critical: { label: "Critical", text: "text-red-400", bg: "bg-red-500/10", border: "border-red-500/30", Icon: AlertOctagon },
  high: { label: "High", text: "text-orange-400", bg: "bg-orange-500/10", border: "border-orange-500/30", Icon: AlertTriangle },
  medium: { label: "Medium", text: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/30", Icon: AlertCircle },
  low: { label: "Low", text: "text-blue-400", bg: "bg-blue-500/10", border: "border-blue-500/30", Icon: Info },
  info: { label: "Info", text: "text-slate-400", bg: "bg-slate-500/10", border: "border-slate-500/20", Icon: Info },
  unknown: { label: "Unknown", text: "text-slate-400", bg: "bg-slate-500/10", border: "border-slate-500/20", Icon: HelpCircle },
  pass: { label: "Pass", text: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/20", Icon: CheckCircle2 },
}

function gradeColor(grade: string): string {
  switch (grade) {
    case "A": return "text-emerald-400"
    case "B": return "text-lime-400"
    case "C": return "text-amber-400"
    case "D": return "text-orange-400"
    default: return "text-red-400"
  }
}

function scoreRingColor(grade: string): string {
  switch (grade) {
    case "A": return "#34d399"
    case "B": return "#a3e635"
    case "C": return "#fbbf24"
    case "D": return "#fb923c"
    default: return "#f87171"
  }
}

// ── Small pieces ─────────────────────────────────────────────────────────────

function SeverityBadge({ severity }: { severity: Severity }) {
  const m = SEVERITY_META[severity]
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${m.text} ${m.bg} ${m.border} border`}>
      <m.Icon className="h-3 w-3" />
      {m.label}
    </span>
  )
}

function ScoreRing({ score, grade }: { score: number; grade: string }) {
  const r = 52
  const circ = 2 * Math.PI * r
  const dash = (score / 100) * circ
  return (
    <div className="relative h-32 w-32 shrink-0">
      <svg className="h-32 w-32 -rotate-90" viewBox="0 0 120 120">
        <circle cx="60" cy="60" r={r} fill="none" stroke="currentColor" strokeWidth="9" className="text-muted/40" />
        <circle
          cx="60" cy="60" r={r} fill="none"
          stroke={scoreRingColor(grade)}
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circ}`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-3xl font-bold ${gradeColor(grade)}`}>{score}</span>
        <span className="text-xs text-muted-foreground">/ 100</span>
      </div>
    </div>
  )
}

function CountChip({ severity, count }: { severity: Severity; count: number }) {
  const m = SEVERITY_META[severity]
  return (
    <div className={`flex items-center gap-2 rounded-lg border ${m.border} ${m.bg} px-3 py-2`}>
      <m.Icon className={`h-4 w-4 ${m.text}`} />
      <span className={`text-lg font-semibold ${m.text}`}>{count}</span>
      <span className="text-xs text-muted-foreground">{m.label}</span>
    </div>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() => {
        void navigator.clipboard.writeText(text)
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1500)
      }}
      className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors shrink-0"
      title="Copy command"
    >
      {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
      {copied ? "Copied" : "Copy"}
    </button>
  )
}

function FindingCard({ finding }: { finding: Finding }) {
  const m = SEVERITY_META[finding.severity]
  return (
    <div className={`rounded-xl border ${m.border} bg-card p-4`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5 min-w-0">
          <m.Icon className={`h-5 w-5 ${m.text} shrink-0 mt-0.5`} />
          <div className="min-w-0">
            <h4 className="text-sm font-medium text-foreground">{finding.title}</h4>
            <p className="text-xs text-muted-foreground mt-0.5">{finding.description}</p>
          </div>
        </div>
        <SeverityBadge severity={finding.severity} />
      </div>

      {finding.detail && (
        <div className="mt-3 rounded-lg bg-muted/40 px-3 py-2">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground/60 mb-0.5">Observed</p>
          <p className="text-xs font-mono text-foreground/90 break-words">{finding.detail}</p>
        </div>
      )}

      {finding.recommendation && (
        <p className="mt-3 text-xs text-muted-foreground">
          <span className="font-medium text-foreground/80">Recommendation: </span>
          {finding.recommendation}
        </p>
      )}

      {finding.fix_command && (
        <div className="mt-3">
          <div className="flex items-center justify-between mb-1">
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground/60">
              Suggested fix · review before running
            </p>
            <CopyButton text={finding.fix_command} />
          </div>
          <pre className="rounded-lg bg-background border border-border px-3 py-2 text-xs font-mono text-foreground/90 overflow-x-auto whitespace-pre-wrap break-words">
            {finding.fix_command}
          </pre>
        </div>
      )}
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function Security() {
  const { id: serverId } = useParams<{ id: string }>()
  const qc = useQueryClient()

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showHistory, setShowHistory] = useState(false)

  const { data: scans = [], isLoading } = useQuery({
    queryKey: ["security-scans", serverId],
    queryFn: () => listSecurityScans(serverId!),
    enabled: !!serverId,
  })

  const runMut = useMutation({
    mutationFn: () => runSecurityScan(serverId!),
    onSuccess: (scan) => {
      setSelectedId(scan.id)
      qc.invalidateQueries({ queryKey: ["security-scans", serverId] })
    },
  })

  const selected: SecurityScan | undefined = useMemo(() => {
    if (!scans.length) return undefined
    return scans.find((s) => s.id === selectedId) ?? scans[0]
  }, [scans, selectedId])

  const grouped = useMemo(() => {
    const issues: Finding[] = []
    const informational: Finding[] = []
    const passing: Finding[] = []
    for (const f of selected?.findings ?? []) {
      if (f.severity === "pass") passing.push(f)
      else if (f.severity === "info" || f.severity === "unknown") informational.push(f)
      else issues.push(f)
    }
    return { issues, informational, passing }
  }, [selected])

  const scanning = runMut.isPending

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-foreground flex items-center gap-2">
            <Shield className="h-6 w-6 text-primary" />
            Security Audit
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Read-only checks for SSH, firewall, updates, accounts, and hardening.
          </p>
        </div>
        <button
          onClick={() => runMut.mutate()}
          disabled={scanning}
          className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60 transition-colors shrink-0"
        >
          {scanning ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          {scanning ? "Scanning…" : scans.length ? "Re-scan" : "Run Scan"}
        </button>
      </div>

      {/* Run error */}
      {runMut.isError && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {(runMut.error as Error).message}
        </div>
      )}

      {/* Loading initial */}
      {isLoading && (
        <div className="flex items-center gap-2 py-12 text-muted-foreground text-sm">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading scans…
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !scans.length && !scanning && (
        <div className="flex flex-col items-center justify-center py-16 text-center rounded-xl border border-dashed border-border">
          <ShieldAlert className="h-10 w-10 text-muted-foreground/30 mb-3" />
          <p className="text-sm text-foreground font-medium">No security scans yet</p>
          <p className="text-xs text-muted-foreground/70 mt-1 max-w-sm">
            Run an audit to check this server's SSH config, firewall, pending updates,
            account hygiene, file permissions, and more.
          </p>
          <button
            onClick={() => runMut.mutate()}
            className="mt-4 flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <Play className="h-4 w-4" />
            Run first scan
          </button>
        </div>
      )}

      {/* Scanning placeholder (first scan) */}
      {scanning && !scans.length && (
        <div className="flex flex-col items-center justify-center py-16 text-center rounded-xl border border-border bg-card">
          <Loader2 className="h-8 w-8 text-primary animate-spin mb-3" />
          <p className="text-sm text-foreground">Running security checks…</p>
          <p className="text-xs text-muted-foreground/70 mt-1">This can take 10–30 seconds.</p>
        </div>
      )}

      {/* Failed scan banner */}
      {selected && selected.status === "failed" && (
        <div className="flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <XCircle className="h-5 w-5 shrink-0" />
          <div>
            <p className="font-medium">Scan failed</p>
            <p className="text-xs text-red-400/80">{selected.error ?? "Unknown error"}</p>
          </div>
        </div>
      )}

      {/* Results */}
      {selected && selected.status === "completed" && (
        <>
          {/* Score hero */}
          <div className="rounded-xl border border-border bg-card p-6">
            <div className="flex flex-col sm:flex-row items-center gap-6">
              <ScoreRing score={selected.score} grade={selected.grade} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  {selected.score >= 75 ? (
                    <ShieldCheck className="h-5 w-5 text-emerald-400" />
                  ) : (
                    <ShieldAlert className="h-5 w-5 text-orange-400" />
                  )}
                  <span className={`text-lg font-semibold ${gradeColor(selected.grade)}`}>
                    Grade {selected.grade}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1.5">
                  <Clock className="h-3 w-3" />
                  Scanned {formatDistanceToNow(new Date(selected.created_at), { addSuffix: true })}
                  {selected.duration_ms != null && ` · ${(selected.duration_ms / 1000).toFixed(1)}s`}
                </p>

                {/* Count chips */}
                <div className="mt-4 flex flex-wrap gap-2">
                  {selected.counts.critical > 0 && <CountChip severity="critical" count={selected.counts.critical} />}
                  {selected.counts.high > 0 && <CountChip severity="high" count={selected.counts.high} />}
                  {selected.counts.medium > 0 && <CountChip severity="medium" count={selected.counts.medium} />}
                  {selected.counts.low > 0 && <CountChip severity="low" count={selected.counts.low} />}
                  <CountChip severity="pass" count={selected.counts.pass} />
                </div>
              </div>
            </div>
          </div>

          {/* 2-column: Issues (left) + Passing (right) */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
            {/* Left column — issues + informational */}
            <div className="space-y-3">
              {grouped.issues.length > 0 ? (
                <>
                  <h2 className="text-sm font-semibold text-foreground">
                    Issues ({grouped.issues.length + grouped.informational.length})
                  </h2>
                  {grouped.issues.map((f) => (
                    <FindingCard key={f.id} finding={f} />
                  ))}
                  {grouped.informational.map((f) => (
                    <FindingCard key={f.id} finding={f} />
                  ))}
                </>
              ) : (
                <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-emerald-500/20 bg-emerald-500/5 py-12 text-center">
                  <ShieldCheck className="h-8 w-8 text-emerald-400/60 mb-2" />
                  <p className="text-sm font-medium text-emerald-400">No issues found</p>
                  <p className="text-xs text-muted-foreground mt-1">This server passed all checks.</p>
                </div>
              )}
            </div>

            {/* Right column — passing checks */}
            <div className="space-y-3">
              {grouped.passing.length > 0 && (
                <>
                  <h2 className="text-sm font-semibold text-emerald-400 flex items-center gap-1.5">
                    <CheckCircle2 className="h-4 w-4" />
                    Passing ({grouped.passing.length})
                  </h2>
                  <div className="space-y-1.5">
                    {grouped.passing.map((f) => (
                      <div
                        key={f.id}
                        className="flex items-start gap-2.5 rounded-lg border border-emerald-500/15 bg-emerald-500/5 px-3 py-2.5"
                      >
                        <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
                        <div className="min-w-0">
                          <p className="text-sm text-foreground">{f.title}</p>
                          {f.detail && (
                            <p className="text-xs text-muted-foreground mt-0.5 break-words">{f.detail}</p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Scan history */}
          {scans.length > 1 && (
            <div>
              <button
                onClick={() => setShowHistory((v) => !v)}
                className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                {showHistory ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                Scan history ({scans.length})
              </button>
              {showHistory && (
                <div className="mt-3 space-y-1.5">
                  {scans.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => setSelectedId(s.id)}
                      className={`flex items-center justify-between w-full rounded-lg border px-3 py-2 text-left transition-colors ${
                        s.id === selected.id
                          ? "border-primary/40 bg-primary/5"
                          : "border-border hover:bg-muted/40"
                      }`}
                    >
                      <span className="flex items-center gap-2">
                        <span className={`text-sm font-semibold ${gradeColor(s.grade)}`}>
                          {s.status === "failed" ? "—" : s.score}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {formatDistanceToNow(new Date(s.created_at), { addSuffix: true })}
                        </span>
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {s.status === "failed"
                          ? "failed"
                          : `${s.counts.critical}C · ${s.counts.high}H · ${s.counts.medium}M`}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
