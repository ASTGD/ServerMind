import { useState, useRef, type KeyboardEvent } from "react"
import { Send, Loader2, Server as ServerIcon } from "lucide-react"
import { useTranslation } from "react-i18next"
import { findMentionQuery, matchServers, type MentionServer, type MentionQuery } from "./serverMentions"

interface Props {
  onSend: (message: string) => void
  disabled?: boolean
  loading?: boolean
  /** Enables @-mentions: type "@" to pick a server name from this list (exact name
   *  inserted — typos can't happen). Typing a name WITHOUT "@" behaves as before. */
  servers?: MentionServer[]
}

export default function ChatInput({ onSend, disabled, loading, servers }: Props) {
  const { t } = useTranslation()
  const [value, setValue] = useState("")
  const [mention, setMention] = useState<MentionQuery | null>(null)
  const [mentionIndex, setMentionIndex] = useState(0)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const matches = mention && servers?.length ? matchServers(servers, mention.query) : []
  const popupOpen = matches.length > 0

  function refreshMention(text: string, caret: number) {
    const q = servers?.length ? findMentionQuery(text, caret) : null
    setMention(q)
    if (!q || q.query !== mention?.query) setMentionIndex(0)
  }

  function handleSend() {
    const trimmed = value.trim()
    if (!trimmed || disabled || loading) return
    onSend(trimmed)
    setValue("")
    setMention(null)
    // Reset height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto"
    }
  }

  /** Replace the "@query" being typed with the picked server's exact name. */
  function pick(server: MentionServer) {
    if (!mention) return
    const caret = textareaRef.current?.selectionStart ?? value.length
    const next = value.slice(0, mention.at) + server.name + " " + value.slice(caret)
    const newCaret = mention.at + server.name.length + 1
    setValue(next)
    setMention(null)
    requestAnimationFrame(() => {
      const el = textareaRef.current
      if (el) {
        el.focus()
        el.setSelectionRange(newCaret, newCaret)
      }
    })
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (popupOpen) {
      if (e.key === "ArrowDown") {
        e.preventDefault()
        setMentionIndex((i) => (i + 1) % matches.length)
        return
      }
      if (e.key === "ArrowUp") {
        e.preventDefault()
        setMentionIndex((i) => (i - 1 + matches.length) % matches.length)
        return
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault()
        pick(matches[Math.min(mentionIndex, matches.length - 1)])
        return
      }
      if (e.key === "Escape") {
        e.preventDefault()
        setMention(null)
        return
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleInput() {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }

  return (
    <div className="relative flex items-end gap-2 rounded-xl border border-border bg-card p-2">
      {/* @-mention popup — pick a server, its exact name is inserted as text. */}
      {popupOpen && (
        <div className="absolute bottom-full left-0 z-20 mb-1.5 w-64 overflow-hidden rounded-lg border border-border bg-card py-1 shadow-xl">
          {matches.map((s, i) => (
            <button
              key={s.id}
              type="button"
              // mousedown, not click — click fires after the textarea loses focus.
              onMouseDown={(e) => {
                e.preventDefault()
                pick(s)
              }}
              onMouseEnter={() => setMentionIndex(i)}
              className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm ${
                i === mentionIndex ? "bg-accent text-accent-foreground" : "text-foreground"
              }`}
            >
              <ServerIcon size={13} className="shrink-0 text-muted-foreground" />
              <span className="truncate">{s.name}</span>
            </button>
          ))}
        </div>
      )}

      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        onChange={(e) => {
          setValue(e.target.value)
          refreshMention(e.target.value, e.target.selectionStart ?? e.target.value.length)
        }}
        onKeyDown={handleKeyDown}
        onKeyUp={(e) => refreshMention(e.currentTarget.value, e.currentTarget.selectionStart ?? e.currentTarget.value.length)}
        onClick={(e) => refreshMention(e.currentTarget.value, e.currentTarget.selectionStart ?? e.currentTarget.value.length)}
        onBlur={() => setMention(null)}
        onInput={handleInput}
        placeholder={t("chat.placeholder")}
        disabled={disabled || loading}
        className="flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none disabled:opacity-50"
      />
      <button
        onClick={handleSend}
        disabled={!value.trim() || disabled || loading}
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-opacity"
      >
        {loading ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
      </button>
    </div>
  )
}
