import { useState, useRef, type KeyboardEvent } from "react"
import { Send, Loader2 } from "lucide-react"
import { useTranslation } from "react-i18next"

interface Props {
  onSend: (message: string) => void
  disabled?: boolean
  loading?: boolean
}

export default function ChatInput({ onSend, disabled, loading }: Props) {
  const { t } = useTranslation()
  const [value, setValue] = useState("")
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  function handleSend() {
    const trimmed = value.trim()
    if (!trimmed || disabled || loading) return
    onSend(trimmed)
    setValue("")
    // Reset height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto"
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
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
    <div className="flex items-end gap-2 rounded-xl border border-border bg-card p-2">
      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
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
