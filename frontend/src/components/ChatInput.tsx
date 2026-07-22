import { useEffect, useRef, useState, type KeyboardEvent } from "react"
import { motion } from "framer-motion"
import { ArrowUp } from "lucide-react"
import { EASE_UI } from "../lib/motion"

const MAX_LINES = 6
const LINE_HEIGHT_PX = 22

const IDLE_PLACEHOLDERS = [
  "Ask about an order, refund, or Flipkart policy...",
  "What's the status of order FK1001?",
  "What's Flipkart's return policy?",
  "I want to talk to a human agent...",
]

const CHIPS = [
  { label: "Track order", message: "What's the status of my order?" },
  { label: "Return item", message: "How do I return an item?" },
  { label: "Payment issue", message: "I'm having a problem with a payment." },
  { label: "Refund status", message: "What's the status of my refund?" },
]

export function ChatInput({
  disabled,
  showChips = false,
  onSend,
}: {
  disabled: boolean
  showChips?: boolean
  onSend: (content: string) => void
}) {
  const [value, setValue] = useState("")
  const [placeholderIdx, setPlaceholderIdx] = useState(0)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (value || disabled) return
    const id = setInterval(() => setPlaceholderIdx((i) => (i + 1) % IDLE_PLACEHOLDERS.length), 3200)
    return () => clearInterval(id)
  }, [value, disabled])

  function autosize() {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "auto"
    const max = LINE_HEIGHT_PX * MAX_LINES
    const next = Math.min(el.scrollHeight, max)
    el.style.height = `${next}px`
    el.style.overflowY = el.scrollHeight > max ? "auto" : "hidden"
  }

  function submit() {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue("")
    requestAnimationFrame(autosize)
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const hasContent = value.trim().length > 0

  return (
    <div className="border-t border-border bg-surface p-3">
      {showChips && !value && (
        <div className="mb-2 flex flex-wrap gap-2">
          {CHIPS.map((chip) => (
            <motion.button
              key={chip.label}
              type="button"
              whileTap={{ scale: 0.95 }}
              onClick={() => onSend(chip.message)}
              disabled={disabled}
              className="rounded-full border border-brand/30 bg-brand-soft px-3 py-1 text-xs font-medium text-brand transition-colors hover:bg-brand hover:text-white disabled:opacity-40"
            >
              {chip.label}
            </motion.button>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2">
        <textarea
          ref={textareaRef}
          className="flex-1 resize-none rounded-xl border border-border bg-bg px-3 py-2 text-[15px] text-ink outline-none transition-[border-color,box-shadow] duration-150 ease-[var(--ease-ui)] focus:border-brand focus:shadow-[0_0_0_3px_var(--brand-ring)]"
          rows={1}
          placeholder={IDLE_PLACEHOLDERS[placeholderIdx]}
          value={value}
          onChange={(e) => {
            setValue(e.target.value)
            autosize()
          }}
          onKeyDown={handleKeyDown}
        />
        <motion.button
          type="button"
          onClick={submit}
          disabled={disabled || !hasContent}
          whileTap={{ scale: 0.95 }}
          animate={{ scale: hasContent && !disabled ? 1 : 0.96 }}
          transition={{ duration: 0.15, ease: EASE_UI }}
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-colors duration-150 disabled:cursor-not-allowed ${
            hasContent && !disabled ? "bg-brand text-white" : "bg-muted-surface text-muted"
          }`}
        >
          <ArrowUp size={18} strokeWidth={2.5} />
        </motion.button>
      </div>
    </div>
  )
}
