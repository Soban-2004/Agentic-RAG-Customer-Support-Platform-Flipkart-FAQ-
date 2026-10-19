import { useCallback, useEffect, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { AnimatePresence, motion, useReducedMotion } from "framer-motion"
import { ArrowDown, PanelLeftOpen } from "lucide-react"
import { api, type ChatMessage, type ImageAttachment, type ThreadSummary } from "../api/client"
import { EASE_UI } from "../lib/motion"
import { useAuth } from "../hooks/useAuth"
import { useChatSocket, type CompletionMetadata } from "../hooks/useChatSocket"
import { Sidebar } from "../components/Sidebar"
import { MessageBubble } from "../components/MessageBubble"
import { TypingIndicator } from "../components/TypingIndicator"
import { ChatInput } from "../components/ChatInput"
import { StarterPrompts } from "../components/StarterPrompts"
import { Brand } from "../components/Brand"
import { ThemeSwitch } from "../components/ThemeSwitch"

const TITLE_MAX_LEN = 40
const SCROLL_BOTTOM_THRESHOLD_PX = 80

function localMessage(role: "user" | "assistant", content: string): ChatMessage {
  return { id: crypto.randomUUID(), role, content, created_at: new Date().toISOString() }
}

export function Chat() {
  const { threadId } = useParams<{ threadId?: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const reducedMotion = useReducedMotion()

  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loadingThread, setLoadingThread] = useState(false)
  const [pendingFirst, setPendingFirst] = useState<{ threadId: string; content: string; image?: ImageAttachment } | null>(null)
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(() => window.matchMedia("(min-width: 768px)").matches)
  const [error, setError] = useState<string | null>(null)
  const [creatingThread, setCreatingThread] = useState(false)
  const toggleSidebar = useCallback(() => setSidebarOpen((open) => !open), [])

  // Client-only, session-only bookkeeping -- never sent to/from the backend.
  // freshMessageIds gates the structured-content row-stagger animation (only
  // plays for a message that just streamed in live, never on thread revisit
  // or reload). stepsByMessageId is the tool-call "steps trail" accumulated
  // from this-turn's status frames (see useChatSocket) -- deliberately kept
  // as a parallel map rather than a field on ChatMessage, since the backend
  // never persists status frames and a reload/revisit will always show none.
  const [freshMessageIds, setFreshMessageIds] = useState<Set<string>>(new Set())
  const [stepsByMessageId, setStepsByMessageId] = useState<Record<string, string[]>>({})

  const scrollRef = useRef<HTMLDivElement>(null)
  const atBottomRef = useRef(true)
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  // Set right before navigating to a just-created thread (see handleSend) --
  // the server has zero messages for it yet (the first message is still
  // queued as pendingFirst, waiting on the WS to connect), so the thread-load
  // effect below must skip its fetch that one time or it clobbers the
  // optimistic user bubble already in `messages` with an empty result.
  const skipThreadLoadRef = useRef(false)

  const refreshThreads = useCallback(() => {
    api.listThreads().then(setThreads).catch(() => setError("Your conversation history could not be loaded. Please try again."))
  }, [])

  useEffect(() => {
    refreshThreads()
  }, [refreshThreads])

  useEffect(() => {
    let active = true
    setError(null)
    setRegeneratingId(null)
    setPendingFirst((first) => first?.threadId === threadId ? first : null)
    atBottomRef.current = true
    setShowScrollBtn(false)
    if (!threadId) {
      setMessages([])
      setLoadingThread(false)
      setPendingFirst(null)
      return
    }
    if (skipThreadLoadRef.current) {
      skipThreadLoadRef.current = false
      return
    }
    setLoadingThread(true)
    api
      .getThread(threadId)
      .then((t) => { if (active) setMessages(t.messages) })
      .catch(() => { if (active) { setMessages([]); setError("This conversation could not be loaded. Please try again.") } })
      .finally(() => { if (active) setLoadingThread(false) })
    return () => { active = false }
  }, [threadId])

  const handleDone = useCallback(
    (content: string, steps: string[], metadata?: CompletionMetadata) => {
      if (metadata?.reload_history && threadId) {
        api.getThread(threadId).then((thread) => setMessages(thread.messages)).catch(() => setError("Reload the conversation to recover its latest answer."))
        setRegeneratingId(null)
        refreshThreads()
        return
      }
      if (regeneratingId) {
        const id = regeneratingId
        setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, content, id: metadata?.assistant_message_id ?? m.id } : m)))
        setStepsByMessageId((s) => ({ ...s, [id]: steps }))
        setFreshMessageIds((f) => new Set(f).add(id))
        setRegeneratingId(null)
      } else {
        const msg = { ...localMessage("assistant", content), ...(metadata?.assistant_message_id ? { id: metadata.assistant_message_id } : {}) }
        setMessages((prev) => prev.some((item) => item.id === msg.id) ? prev : [...prev, msg])
        setStepsByMessageId((s) => ({ ...s, [msg.id]: steps }))
        setFreshMessageIds((f) => new Set(f).add(msg.id))
      }
      refreshThreads()
    },
    [refreshThreads, regeneratingId, threadId],
  )

  const { connected, connectionState, streaming, pending, statusLabel, error: socketError, send, reconnect } = useChatSocket(
    threadId ? `/ws/chat/${threadId}` : null,
    handleDone,
  )

  useEffect(() => {
    if (socketError || !connected) setRegeneratingId(null)
  }, [socketError, connected])

  function scrollToBottom(smooth: boolean) {
    const el = scrollRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: smooth && !reducedMotion ? "smooth" : "auto" })
    atBottomRef.current = true
    setShowScrollBtn(false)
  }

  function handleScroll() {
    const el = scrollRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_BOTTOM_THRESHOLD_PX
    atBottomRef.current = nearBottom
    setShowScrollBtn(!nearBottom)
  }

  useEffect(() => {
    if (atBottomRef.current) scrollToBottom(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, pending, statusLabel])

  useEffect(() => {
    if (!loadingThread) scrollToBottom(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadingThread])

  // A brand-new thread's WS connection isn't open yet the instant we
  // navigate to it -- queue the first message and fire it once connected.
  useEffect(() => {
    if (connected && pendingFirst && pendingFirst.threadId === threadId) {
      if (send(pendingFirst.content, { image: pendingFirst.image })) setPendingFirst(null)
    }
  }, [connected, pendingFirst, send, threadId])

  async function handleSend(content: string, image?: ImageAttachment) {
    if (streaming || loadingThread || creatingThread || pendingFirst) return false
    if (threadId && !connected) { setError("You're offline. Reconnect before sending your message."); return false }
    setError(null)
    // A user sending a message is always an intent to see the reply -- jump
    // to bottom even if they'd scrolled up to reread earlier context.
    atBottomRef.current = true
    setShowScrollBtn(false)
    if (!threadId) {
      setCreatingThread(true)
      try {
        const thread = await api.createThread(content.slice(0, TITLE_MAX_LEN) || "Photo question")
        setMessages([localMessage("user", content || "Photo attached")])
        setPendingFirst({ threadId: thread.id, content, image })
        skipThreadLoadRef.current = true
        refreshThreads()
        navigate(`/chat/${thread.id}`, { replace: true })
        return true
      } catch {
        setError("Your conversation could not be created. Please try sending your message again.")
        return false
      } finally { setCreatingThread(false) }
    }
    if (send(content, { image })) {
      setMessages((prev) => [...prev, localMessage("user", content || "Photo attached")])
      return true
    }
    setError("Your message could not be sent. Please reconnect and try again.")
    return false
  }

  async function handleRegenerate(assistantMessageId: string) {
    if (streaming || !threadId || !connected) return
    const idx = messages.findIndex((m) => m.id === assistantMessageId)
    const priorUser = [...messages.slice(0, idx)].reverse().find((m) => m.role === "user")
    if (!priorUser) return
    atBottomRef.current = true
    setShowScrollBtn(false)
    try {
      setRegeneratingId(assistantMessageId)
      if (!send(priorUser.content, { regenerate_message_id: assistantMessageId })) { setRegeneratingId(null); setError("Your reply could not be regenerated. Please reconnect and try again.") }
    } catch { setError("Your reply could not be regenerated. Please try again.") }
  }

  async function handleDeleteThread(id: string) {
    try {
      await api.deleteThread(id)
      setThreads((prev) => prev.filter((t) => t.id !== id))
      if (id === threadId) navigate("/")
    } catch { setError("This conversation could not be deleted. Please try again.") }
  }

  const showStarters = !loadingThread && messages.length === 0 && !pending && !statusLabel
  const sendDisabled = streaming || loadingThread || creatingThread || !!pendingFirst || (!!threadId && !connected)

  return (
    <div className="app-frame">
      <div className="app-shell">
        <Sidebar
          threads={threads}
          activeThreadId={threadId ?? null}
          open={sidebarOpen}
          onSelect={(id) => { navigate(`/chat/${id}`); if (window.innerWidth < 768) setSidebarOpen(false) }}
          onNewChat={() => { navigate("/"); if (window.innerWidth < 768) setSidebarOpen(false) }}
          onDelete={handleDeleteThread}
          onToggle={toggleSidebar}
        />
        <main className="chat-main">
          <header className="chat-header">
            {!sidebarOpen && (
              <button
                type="button"
                onClick={() => setSidebarOpen(true)}
                aria-label="Open sidebar"
                aria-expanded={sidebarOpen}
                className="sidebar-close"
              >
                <PanelLeftOpen size={17} />
              </button>
            )}
            <div className="chat-title"><Brand compact /></div>
            <div className="connection-status" data-state={connectionState} role="status"><span className="connection-dot" />{connectionState === "ready" ? "Ready" : connectionState === "connecting" ? "Connecting" : "Offline"}</div>
            <ThemeSwitch />
          </header>

        <div ref={scrollRef} onScroll={handleScroll} className="chat-scroll">
          <AnimatePresence mode="wait">
            <motion.div
              key={threadId ?? "new"}
              initial={reducedMotion ? false : { opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={reducedMotion ? { opacity: 0 } : { opacity: 0, x: -8 }}
              transition={{ duration: reducedMotion ? 0 : 0.25, ease: EASE_UI }}
              className="conversation"
            >
              {showStarters ? (
                <StarterPrompts onPick={handleSend} disabled={sendDisabled} />
              ) : loadingThread ? (
                <div className="flex animate-pulse flex-col gap-4">
                  <div className="h-12 w-2/3 self-end rounded-2xl bg-muted-surface" />
                  <div className="h-16 w-3/4 rounded-2xl bg-muted-surface" />
                  <div className="h-10 w-1/2 self-end rounded-2xl bg-muted-surface" />
                </div>
              ) : (
                <>
                  {messages.map((m) => (
                    <MessageBubble
                      key={m.id}
                      role={m.role}
                      content={m.content}
                      createdAt={m.created_at}
                      userIdentifier={user?.identifier}
                      isFresh={freshMessageIds.has(m.id)}
                      steps={stepsByMessageId[m.id]}
                      onRegenerate={m.role === "assistant" && !sendDisabled ? () => handleRegenerate(m.id) : undefined}
                    />
                  ))}
                  <AnimatePresence>
                    {pending ? (
                      <MessageBubble
                        key="pending"
                        role="assistant"
                        content={pending}
                        isStreaming
                        userIdentifier={user?.identifier}
                      />
                    ) : streaming && statusLabel ? (
                      <TypingIndicator key="status" label={statusLabel} />
                    ) : null}
                  </AnimatePresence>
                </>
              )}
            </motion.div>
          </AnimatePresence>

          <AnimatePresence>
            {showScrollBtn && (
              <motion.button
                type="button"
                onClick={() => scrollToBottom(true)}
                initial={reducedMotion ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 8 }}
                className="scroll-latest"
                aria-label="Scroll to latest"
              >
                <ArrowDown size={16} />
              </motion.button>
            )}
          </AnimatePresence>
        </div>

          {(error || socketError || connectionState === "offline") && <div className="chat-error" role="alert">{error || socketError || "You're offline. Reconnect to continue."}{connectionState === "offline" && <button type="button" onClick={reconnect}>Reconnect</button>}</div>}
          <ChatInput disabled={sendDisabled} showChips={messages.length > 0} onSend={handleSend} />
        </main>
      </div>
    </div>
  )
}
