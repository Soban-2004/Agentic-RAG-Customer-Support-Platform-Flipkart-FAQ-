import { useCallback, useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { AnimatePresence, motion } from "framer-motion"
import { ArrowDown } from "lucide-react"
import type { ChatMessage } from "../api/client"
import { EASE_UI } from "../lib/motion"
import { useChatSocket } from "../hooks/useChatSocket"
import { MessageBubble } from "../components/MessageBubble"
import { TypingIndicator } from "../components/TypingIndicator"
import { ChatInput } from "../components/ChatInput"
import { StarterPrompts } from "../components/StarterPrompts"

const SCROLL_BOTTOM_THRESHOLD_PX = 80

function localMessage(role: "user" | "assistant", content: string): ChatMessage {
  return { id: crypto.randomUUID(), role, content, created_at: new Date().toISOString() }
}

/** No-login, nothing-saved version of Chat.tsx -- talks to /ws/demo
 * (src/api/demo_ws.py) instead of an authenticated per-thread socket, so a
 * recruiter/evaluator can try the system in a few seconds with zero signup
 * friction. Deliberately simpler than Chat.tsx: no sidebar/thread list
 * (there's nothing to list -- the backend never writes this conversation
 * anywhere), no regenerate (that endpoint is Postgres-thread-backed), and
 * history is plain component state that a reload discards -- matching the
 * backend's in-memory-only session (build_ephemeral_memory). */
export function Demo() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [freshMessageIds, setFreshMessageIds] = useState<Set<string>>(new Set())
  const [stepsByMessageId, setStepsByMessageId] = useState<Record<string, string[]>>({})

  const scrollRef = useRef<HTMLDivElement>(null)
  const atBottomRef = useRef(true)
  const [showScrollBtn, setShowScrollBtn] = useState(false)

  const handleDone = useCallback((content: string, steps: string[]) => {
    const msg = localMessage("assistant", content)
    setMessages((prev) => [...prev, msg])
    setStepsByMessageId((s) => ({ ...s, [msg.id]: steps }))
    setFreshMessageIds((f) => new Set(f).add(msg.id))
  }, [])

  // Fixed path, connects once on mount -- unlike Chat.tsx there's no
  // per-thread identity to key the socket on.
  const { connected, streaming, pending, statusLabel, send } = useChatSocket("/ws/demo", handleDone)

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

  function handleSend(content: string) {
    atBottomRef.current = true
    setShowScrollBtn(false)
    setMessages((prev) => [...prev, localMessage("user", content)])
    send(content)
  }

  const showStarters = messages.length === 0 && !pending && !statusLabel

  return (
    <div className="h-full bg-bg p-3 sm:p-4 lg:p-5">
      <div className="flex h-full overflow-hidden rounded-2xl elevate-md">
        <main className="relative flex flex-1 flex-col overflow-hidden bg-bg">
          <header className="absolute inset-x-0 top-0 z-10 flex items-center gap-2 border-b border-border bg-surface/70 px-4 py-3 backdrop-blur-md">
            <span className="font-heading text-lg">🛍️</span>
            <span className="font-heading font-semibold text-ink">Flipkart Support</span>
            <span className="ml-1 rounded-full bg-brand-soft px-2 py-0.5 text-xs font-medium text-brand">
              Demo -- nothing is saved
            </span>
            <span
              className={`h-2 w-2 rounded-full transition-colors ${connected ? "bg-success" : "bg-muted"}`}
              title={connected ? "Connected" : "Connecting..."}
            />
            <Link to="/signup" className="ml-auto text-sm font-medium text-brand hover:text-brand-hover">
              Sign up to save your chats
            </Link>
          </header>

          <div ref={scrollRef} onScroll={handleScroll} className="relative flex-1 overflow-y-auto px-4 pb-4 pt-16">
            <AnimatePresence mode="wait">
              <motion.div
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -8 }}
                transition={{ duration: 0.25, ease: EASE_UI }}
                className="flex h-full flex-col gap-4"
              >
                {showStarters ? (
                  <StarterPrompts onPick={handleSend} />
                ) : (
                  <>
                    {messages.map((m) => (
                      <MessageBubble
                        key={m.id}
                        role={m.role}
                        content={m.content}
                        createdAt={m.created_at}
                        userIdentifier="guest"
                        isFresh={freshMessageIds.has(m.id)}
                        steps={stepsByMessageId[m.id]}
                      />
                    ))}
                    <AnimatePresence>
                      {pending ? (
                        <MessageBubble
                          key="pending"
                          role="assistant"
                          content={pending}
                          isStreaming
                          userIdentifier="guest"
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
