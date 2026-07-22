import { useState } from "react"
import { Check, Copy, RotateCcw, ThumbsDown, ThumbsUp } from "lucide-react"

const ICON_BTN =
  "flex h-6 w-6 items-center justify-center rounded-md text-muted hover:bg-brand-soft hover:text-brand transition-colors"

export function MessageActions({
  content,
  isBot,
  onRegenerate,
}: {
  content: string
  isBot: boolean
  onRegenerate?: () => void
}) {
  const [copied, setCopied] = useState(false)
  // Thumbs are local-only UI state this pass -- not persisted server-side.
  // Adding a real feedback endpoint is a cheap, optional follow-up (one
  // column + one endpoint), deliberately not built now.
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null)

  function handleCopy() {
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <div className="flex items-center gap-1 opacity-0 transition-opacity duration-[120ms] group-hover:opacity-100">
      <button type="button" aria-label="Copy" onClick={handleCopy} className={ICON_BTN}>
        {copied ? <Check size={14} className="text-success" /> : <Copy size={14} />}
      </button>
      {isBot && onRegenerate && (
        <button type="button" aria-label="Regenerate" onClick={onRegenerate} className={ICON_BTN}>
          <RotateCcw size={14} />
        </button>
      )}
      {isBot && (
        <>
          <button
            type="button"
            aria-label="Good response"
            onClick={() => setFeedback((f) => (f === "up" ? null : "up"))}
            className={`${ICON_BTN} ${feedback === "up" ? "text-success" : ""}`}
          >
            <ThumbsUp size={14} />
          </button>
          <button
            type="button"
            aria-label="Bad response"
            onClick={() => setFeedback((f) => (f === "down" ? null : "down"))}
            className={`${ICON_BTN} ${feedback === "down" ? "text-danger" : ""}`}
          >
            <ThumbsDown size={14} />
          </button>
        </>
      )}
    </div>
  )
}
