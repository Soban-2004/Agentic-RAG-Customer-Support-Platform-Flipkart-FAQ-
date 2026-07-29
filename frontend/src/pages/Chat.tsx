import { useCallback, useEffect, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { AnimatePresence, motion } from "framer-motion"
import { ArrowDown, PanelLeftOpen } from "lucide-react"
import { api, type ChatMessage, type ThreadSummary } from "../api/client"
import { EASE_UI } from "../lib/motion"
import { useAuth } from "../hooks/useAuth"
import { useChatSocket } from "../hooks/useChatSocket"
import { Sidebar } from "../components/Sidebar"
import { MessageBubble } from "../components/MessageBubble"
import { TypingIndicator } from "../components/TypingIndicator"
import { ChatInput } from "../components/ChatInput"
import { StarterPrompts } from "../components/StarterPrompts"

const TITLE_MAX_LEN = 40
const SCROLL_BOTTOM_THRESHOLD_PX = 80

function localMessage(role: "user" | "assistant", content: string): ChatMessage {
  return { id: crypto.randomUUID(), role, content, created_at: new Date().toISOString() }
}

export function Chat() {
  const { threadId } = useParams<{ threadId?: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()

  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loadingThread, setLoadingThread] = useState(false)
  const [pendingFirst, setPendingFirst] = useState<string | null>(null)
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)

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
    api.listThreads().then(setThreads).catch(() => {})
  }, [])

  useEffect(() => {
    refreshThreads()
  }, [refreshThreads])

  useEffect(() => {
    atBottomRef.current = true
    setShowScrollBtn(false)
    if (!threadId) {
      setMessages([])
      return
    }
    if (skipThreadLoadRef.current) {
      skipThreadLoadRef.current = false
      return
    }
    setLoadingThread(true)
    api
      .getThread(threadId)
      .then((t) => setMessages(t.messages))
      .catch(() => setMessages([]))
      .finally(() => setLoadingThread(false))
  }, [threadId])

  const handleDone = useCallback(
    (content: string, steps: string[]) => {
      if (regeneratingId) {
        const id = regeneratingId
        setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, content } : m)))
        setStepsByMessageId((s) => ({ ...s, [id]: steps }))
        setFreshMessageIds((f) => new Set(f).add(id))
        setRegeneratingId(null)
      } else {
        const msg = localMessage("assistant", content)
        setMessages((prev) => [...prev, msg])
        setStepsByMessageId((s) => ({ ...s, [msg.id]: steps }))
        setFreshMessageIds((f) => new Set(f).add(msg.id))
      }
      refreshThreads()
    },
    [refreshThreads, regeneratingId],
  )

  const { connected, streaming, pending, statusLabel, send } = useChatSocket(threadId ?? null, handleDone)

  function scrollToBottom(smooth: boolean) {
    const el = scrollRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" })
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
    if (connected && pendingFirst) {
      send(pendingFirst)
      setPendingFirst(null)
    }
  }, [connected, pendingFirst, send])

  async function handleSend(content: string) {
    // A user sending a message is always an intent to see the reply -- jump
    // to bottom even if they'd scrolled up to reread earlier context.
    atBottomRef.current = true
    setShowScrollBtn(false)
    setMessages((prev) => [...prev, localMessage("user", content)])

    if (!threadId) {
      const thread = await api.createThread(content.slice(0, TITLE_MAX_LEN))
      setPendingFirst(content)
      skipThreadLoadRef.current = true
      refreshThreads()
      navigate(`/chat/${thread.id}`, { replace: true })
      return
    }
    send(content)
  }

  async function handleRegenerate(assistantMessageId: string) {
    if (streaming || !threadId) return
    const idx = messages.findIndex((m) => m.id === assistantMessageId)
    const priorUser = [...messages.slice(0, idx)].reverse().find((m) => m.role === "user")
    if (!priorUser) return
    atBottomRef.current = true
    setShowScrollBtn(false)
    await api.regeneratePrep(threadId).catch(() => {})
    setRegeneratingId(assistantMessageId)
    send(priorUser.content)
  }

  async function handleDeleteThread(id: string) {
    await api.deleteThread(id)
    setThreads((prev) => prev.filter((t) => t.id !== id))
    if (id === threadId) navigate("/")
  }

  const showStarters = !loadingThread && messages.length === 0 && !pending && !statusLabel

  return (
    <div className="h-full bg-bg p-3 sm:p-4 lg:p-5">
      <div className="flex h-full overflow-hidden rounded-2xl elevate-md">
        <Sidebar
          threads={threads}
          activeThreadId={threadId ?? null}
          open={sidebarOpen}
          onSelect={(id) => navigate(`/chat/${id}`)}
          onNewChat={() => navigate("/")}
          onDelete={handleDeleteThread}
          onToggle={() => setSidebarOpen((o) => !o)}
        />
        <main className="relative flex flex-1 flex-col overflow-hidden bg-bg">
          <header className="absolute inset-x-0 top-0 z-10 flex items-center gap-2 border-b border-border bg-surface/70 px-4 py-3 backdrop-blur-md">
            {!sidebarOpen && (
              <button
                type="button"
                onClick={() => setSidebarOpen(true)}
                aria-label="Open sidebar"
                className="mr-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-bg hover:text-ink"
              >
                <PanelLeftOpen size={17} />
              </button>
            )}
            <span className="font-heading text-lg">🛍️</span>
            <span className="font-heading font-semibold text-ink">Flipkart Support</span>
            <span
              className={`ml-auto h-2 w-2 rounded-full transition-colors ${
                connected ? "bg-success" : "bg-muted"
              }`}
              title={connected ? "Connected" : "Connecting..."}
            />
          </header>

        <div ref={scrollRef} onScroll={handleScroll} className="relative flex-1 overflow-y-auto px-4 pb-4 pt-16">
          <AnimatePresence mode="wait">
            <motion.div
              key={threadId ?? "new"}
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.25, ease: EASE_UI }}
              className="flex h-full flex-col gap-4"
            >
              {showStarters ? (
                <StarterPrompts onPick={handleSend} />
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
                      onRegenerate={m.role === "assistant" ? () => handleRegenerate(m.id) : undefined}
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
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 8 }}
                className="fixed bottom-24 right-8 flex h-9 w-9 items-center justify-center rounded-full bg-surface text-brand elevate-md"
                aria-label="Scroll to latest"
              >
                <ArrowDown size={16} />
              </motion.button>
            )}
          </AnimatePresence>
        </div>

          <ChatInput disabled={streaming} showChips={messages.length > 0} onSend={handleSend} />
        </main>
      </div>
    </div>
  )
}
