import type { ImageAttachment } from "../api/client"
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react"
import { ArrowUp, ImagePlus, X } from "lucide-react"

const CHIPS = [
  { label: "Track order", message: "What's the status of my order?" },
  { label: "Return item", message: "How do I return an item?" },
  { label: "Payment issue", message: "I'm having a problem with a payment." },
  { label: "Refund status", message: "What's the status of my refund?" },
]

export function ChatInput({ disabled, showChips = false, onSend }: {
  disabled: boolean
  showChips?: boolean
  onSend: (content: string, image?: ImageAttachment) => void | boolean | Promise<void | boolean>
}) {
  const [value, setValue] = useState("")
  const [attachment, setAttachment] = useState<ImageAttachment | undefined>()
  const [attachmentName, setAttachmentName] = useState("")
  const [attachmentError, setAttachmentError] = useState("")
  const [readingImage, setReadingImage] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  async function attach(file?: File) {
    setAttachmentError("")
    if (!file) return
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type) || file.size > 4 * 1024 * 1024) {
      setAttachmentError("Choose a JPEG, PNG, or WebP under 4 MiB.")
      return
    }
    setReadingImage(true)
    try {
      const data = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result).split(",")[1])
        reader.onerror = () => reject(new Error("read failed"))
        reader.readAsDataURL(file)
      })
      setAttachment({ data, mime_type: file.type as ImageAttachment["mime_type"] })
      setAttachmentName(file.name)
    } catch { setAttachmentError("The photo couldn't be read. Please try another file.") }
    finally { setReadingImage(false) }
  }
  const submittingRef = useRef(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const hintId = useId()

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    const styles = getComputedStyle(el)
    const lineHeight = parseFloat(styles.lineHeight) || 24
    const padding = parseFloat(styles.paddingTop) + parseFloat(styles.paddingBottom)
    const max = lineHeight * 6 + padding
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, max)}px`
    el.style.overflowY = el.scrollHeight > max ? "auto" : "hidden"
  }, [value])

  async function submit() {
    const trimmed = value.trim()
    if ((!trimmed && !attachment) || disabled || readingImage || submittingRef.current) return
    submittingRef.current = true
    const snapshot = value
    try {
      const accepted = await onSend(trimmed, attachment)
      if (accepted !== false) {
        setValue((current) => current === snapshot ? "" : current)
        setAttachment(undefined)
        setAttachmentName("")
      }
    } finally {
      submittingRef.current = false
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <div className="composer">
      {showChips && !value && (
        <div className="composer-chips" aria-label="Suggested questions">
          {CHIPS.map((chip) => (
            <button key={chip.label} type="button" className="composer-chip" disabled={disabled} onClick={() => onSend(chip.message)}>{chip.label}</button>
          ))}
        </div>
      )}
      {attachment && <div className="attachment-status"><span>{attachmentName}</span><button type="button" aria-label="Remove attached photo" onClick={() => setAttachment(undefined)}><X size={15} /></button></div>}
      {attachmentError && <p className="attachment-error" role="alert">{attachmentError}</p>}
      <div className="composer-inner">
        <input ref={fileRef} id="chat-photo" name="chat-photo" type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(event) => { void attach(event.target.files?.[0]); event.target.value = "" }} />
        <button className="composer-attach" type="button" aria-label="Attach a product photo" disabled={disabled || readingImage} onClick={() => fileRef.current?.click()}><ImagePlus size={19} /></button>
        <textarea ref={textareaRef} id="chat-message" name="message" className="composer-field" rows={1} aria-label="Your message" aria-describedby={hintId}
          placeholder="Ask about an order, refund, or policy…" value={value} disabled={disabled}
          onChange={(event) => setValue(event.target.value)} onKeyDown={handleKeyDown} />
        <button type="button" className="composer-send" aria-label="Send message" onClick={submit} disabled={disabled || readingImage || (!value.trim() && !attachment)}>
          <ArrowUp size={20} strokeWidth={2} aria-hidden="true" />
        </button>
      </div>
      <p className="composer-footnote" id={hintId}>Enter to send · Shift + Enter for a new line</p>
    </div>
  )
}
