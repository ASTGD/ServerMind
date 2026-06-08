import { useState } from "react"
import Editor from "@monaco-editor/react"
import { Terminal, Monitor } from "lucide-react"

interface Props {
  scriptBash: string | null
  scriptPowershell: string | null
  defaultTab?: "bash" | "powershell"
  height?: string
}

export default function ScriptPreview({
  scriptBash,
  scriptPowershell,
  defaultTab,
  height = "420px",
}: Props) {
  const hasBash = !!scriptBash
  const hasPs = !!scriptPowershell
  const initialTab: "bash" | "powershell" =
    defaultTab ?? (hasBash ? "bash" : "powershell")
  const [tab, setTab] = useState<"bash" | "powershell">(initialTab)

  const content = tab === "bash" ? scriptBash ?? "" : scriptPowershell ?? ""
  const language = tab === "bash" ? "shell" : "powershell"

  return (
    <div className="rounded-xl border border-border overflow-hidden">
      {/* Tab bar */}
      {hasBash && hasPs && (
        <div className="flex border-b border-border bg-muted/40">
          <button
            onClick={() => setTab("bash")}
            className={`flex items-center gap-1.5 px-4 py-2 text-xs font-medium transition-colors ${
              tab === "bash"
                ? "text-foreground border-b-2 border-primary bg-background"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Terminal className="h-3 w-3" />
            Bash
          </button>
          <button
            onClick={() => setTab("powershell")}
            className={`flex items-center gap-1.5 px-4 py-2 text-xs font-medium transition-colors ${
              tab === "powershell"
                ? "text-foreground border-b-2 border-primary bg-background"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Monitor className="h-3 w-3" />
            PowerShell
          </button>
        </div>
      )}
      {!hasBash && !hasPs && (
        <div className="px-4 py-2 text-xs text-muted-foreground bg-muted/40 border-b border-border">
          No script available
        </div>
      )}

      <Editor
        height={height}
        language={language}
        value={content}
        theme="vs-dark"
        options={{
          readOnly: true,
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          fontSize: 13,
          lineNumbers: "on",
          folding: true,
          wordWrap: "off",
          padding: { top: 12, bottom: 12 },
          scrollbar: { alwaysConsumeMouseWheel: false },
        }}
      />
    </div>
  )
}
