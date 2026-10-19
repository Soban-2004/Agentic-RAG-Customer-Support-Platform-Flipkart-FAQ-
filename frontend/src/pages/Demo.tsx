import { useCallback, useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { AnimatePresence, motion, useReducedMotion } from "framer-motion"
import { ArrowDown, PanelLeftOpen, PanelLeftClose, Plus, ArrowUpRight } from "lucide-react"
import type { ChatMessage, ImageAttachment } from "../api/client"
import { EASE_UI } from "../lib/motion"
import { useChatSocket } from "../hooks/useChatSocket"
import { MessageBubble } from "../components/MessageBubble"
import { TypingIndicator } from "../components/TypingIndicator"
import { ChatInput } from "../components/ChatInput"
import { StarterPrompts } from "../components/StarterPrompts"
import { Brand } from "../components/Brand"
import { ThemeSwitch } from "../components/ThemeSwitch"

const SCROLL_BOTTOM_THRESHOLD_PX = 80
function localMessage(role: "user" | "assistant", content: string): ChatMessage {
  return { id: crypto.randomUUID(), role, content, created_at: new Date().toISOString() }
}

export function Demo() {
  const reducedMotion = useReducedMotion()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [freshMessageIds, setFreshMessageIds] = useState<Set<string>>(new Set())
  const [stepsByMessageId, setStepsByMessageId] = useState<Record<string, string[]>>({})
  const [sidebarOpen, setSidebarOpen] = useState(() => window.matchMedia("(min-width: 768px)").matches)
  const [sendError, setSendError] = useState<string | null>(null)
  const [resetting, setResetting] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const asideRef = useRef<HTMLElement>(null)
  const atBottomRef = useRef(true)
  const [showScrollBtn, setShowScrollBtn] = useState(false)

  const handleDone = useCallback((content: string, steps: string[]) => {
    const message = localMessage("assistant", content)
    setMessages((previous) => [...previous, message])
    setStepsByMessageId((previous) => ({ ...previous, [message.id]: steps }))
    setFreshMessageIds((previous) => new Set(previous).add(message.id))
  }, [])
  const { connected, connectionState, streaming, pending, statusLabel, error, send, reconnect } = useChatSocket("/ws/demo", handleDone)

  useEffect(() => {
    if (connectionState !== "connecting") setResetting(false)
  }, [connectionState])

  useEffect(() => {
    if (!sidebarOpen || !window.matchMedia("(max-width: 767px)").matches) return
    const previous = document.activeElement as HTMLElement | null
    asideRef.current?.querySelector<HTMLButtonElement>("button")?.focus()
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") setSidebarOpen(false)
      if (event.key !== "Tab") return
      const elements = asideRef.current?.querySelectorAll<HTMLElement>("button, a[href]")
      if (!elements?.length) return
      const first = elements[0]
      const last = elements[elements.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    document.addEventListener("keydown", handleKey)
    return () => { document.removeEventListener("keydown", handleKey); previous?.focus() }
  }, [sidebarOpen])

  function scrollToBottom(smooth: boolean) {
    const element = scrollRef.current
    if (!element) return
    element.scrollTo({ top: element.scrollHeight, behavior: smooth && !reducedMotion ? "smooth" : "auto" })
    atBottomRef.current = true
    setShowScrollBtn(false)
  }
  function handleScroll() {
    const element = scrollRef.current
    if (!element) return
    const nearBottom = element.scrollHeight - element.scrollTop - element.clientHeight < SCROLL_BOTTOM_THRESHOLD_PX
    atBottomRef.current = nearBottom
    setShowScrollBtn(!nearBottom)
  }
  useEffect(() => {
    if (atBottomRef.current) scrollToBottom(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, pending, statusLabel])

  function handleSend(content: string, image?: ImageAttachment) {
    if (streaming || resetting) return false
    if (!connected || !send(content, { image })) { setSendError("Your message could not be sent. Reconnect and try again."); return false }
    setSendError(null)
    atBottomRef.current = true
    setShowScrollBtn(false)
    setMessages((previous) => [...previous, localMessage("user", content || "Photo attached")])
    return true
  }
  function newConversation() {
    if (streaming) return
    setMessages([])
    setFreshMessageIds(new Set())
    setStepsByMessageId({})
    setSendError(null)
    setResetting(true)
    reconnect()
    if (window.innerWidth < 768) setSidebarOpen(false)
  }
  const showStarters = messages.length === 0 && !pending && !statusLabel
  const sendDisabled = streaming || !connected || resetting

  return (
    <div className="app-frame">
      <div className="app-shell">
        {sidebarOpen && <>
          <button className="sidebar-backdrop" type="button" onClick={() => setSidebarOpen(false)} aria-label="Close navigation" tabIndex={-1} />
          <aside className="sidebar" ref={asideRef} aria-label="Demo navigation">
            <div className="sidebar-content">
              <div className="sidebar-top"><Brand /><button className="sidebar-close" type="button" onClick={() => setSidebarOpen(false)} aria-label="Close sidebar"><PanelLeftClose size={18} /></button></div>
              <button className="sidebar-new" type="button" onClick={newConversation} disabled={streaming || resetting}><Plus size={17} /> New conversation</button>
              <div className="sidebar-history"><p className="history-label">A little clarity, on demand</p><div className="demo-note"><span className="demo-note-marker" /><p>A question is all it takes.</p><span>Explore order tracking, returns, payments, and more. This demo keeps your conversation only while the page is open.</span></div></div>
              <div className="sidebar-footer"><ThemeSwitch /><div className="sidebar-account"><span>Here to try things out?</span><Link to="/login">Log in <ArrowUpRight size={14} /></Link></div></div>
            </div>
          </aside>
        </>}
        <main className="chat-main">
          <header className="chat-header">
            {!sidebarOpen && <button className="sidebar-close" type="button" onClick={() => setSidebarOpen(true)} aria-label="Open sidebar" aria-expanded={sidebarOpen}><PanelLeftOpen size={18} /></button>}
            <div className="chat-title"><Brand compact /></div>
            <span className="demo-badge">Demo · chats aren’t saved</span>
            <div className="connection-status" data-state={connectionState} role="status"><span className="connection-dot" />{connectionState === "ready" ? "Ready" : connectionState === "connecting" ? "Connecting" : "Offline"}</div>
            <ThemeSwitch />
            <Link to="/signup" className="header-cta">Save your chats <ArrowUpRight size={14} /></Link>
          </header>
          <div ref={scrollRef} onScroll={handleScroll} className="chat-scroll">
            <AnimatePresence mode="wait">
              <motion.div initial={reducedMotion ? false : { opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} exit={reducedMotion ? { opacity: 0 } : { opacity: 0, x: -8 }} transition={{ duration: reducedMotion ? 0 : 0.25, ease: EASE_UI }} className="conversation">
                {showStarters ? <StarterPrompts onPick={handleSend} disabled={sendDisabled} /> : <>
                  {messages.map((message) => <MessageBubble key={message.id} role={message.role} content={message.content} createdAt={message.created_at} userIdentifier="guest" isFresh={freshMessageIds.has(message.id)} steps={stepsByMessageId[message.id]} />)}
                  <AnimatePresence>
                    {pending ? <MessageBubble key="pending" role="assistant" content={pending} isStreaming userIdentifier="guest" /> : streaming && statusLabel ? <TypingIndicator key="status" label={statusLabel} /> : null}
                  </AnimatePresence>
                </>}
              </motion.div>
            </AnimatePresence>
            <AnimatePresence>
              {showScrollBtn && <motion.button type="button" onClick={() => scrollToBottom(true)} initial={reducedMotion ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 8 }} className="scroll-latest" aria-label="Scroll to latest"><ArrowDown size={16} /></motion.button>}
            </AnimatePresence>
          </div>
          {(sendError || error || connectionState === "offline") && <div className="chat-error" role="alert">{sendError || error || "You're offline. Reconnect to continue."}{connectionState === "offline" && <button type="button" onClick={() => { setSendError(null); reconnect() }}>Reconnect</button>}</div>}
          <ChatInput disabled={sendDisabled} showChips={messages.length > 0} onSend={handleSend} />
        </main>
      </div>
    </div>
  )
}
