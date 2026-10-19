import { useEffect, useRef, useState } from "react"
import { Check, Copy, RotateCcw } from "lucide-react"

export function MessageActions({ content, isBot, onRegenerate }: {
  content: string
  isBot: boolean
  onRegenerate?: () => void
}) {
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState("")
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current) }, [])

  async function handleCopy() {
    setCopyError("")
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      if (timer.current) clearTimeout(timer.current)
      timer.current = setTimeout(() => setCopied(false), 1800)
    } catch {
      setCopied(false)
      setCopyError("Couldn't copy. Select the message text to copy it.")
    }
  }

  return (
    <div className="message-actions">
      <button type="button" aria-label={copied ? "Message copied" : "Copy message"} title={copied ? "Copied" : "Copy message"} onClick={handleCopy} className="message-action">
        {copied ? <Check size={15} aria-hidden="true" /> : <Copy size={15} aria-hidden="true" />}
      </button>
      {isBot && onRegenerate && (
        <button type="button" aria-label="Regenerate response" title="Regenerate response" onClick={onRegenerate} className="message-action">
          <RotateCcw size={15} aria-hidden="true" />
        </button>
      )}
      <span className={copyError ? "message-action-error" : "sr-only"} role="status">{copyError || (copied ? "Message copied." : "")}</span>
    </div>
  )
}
