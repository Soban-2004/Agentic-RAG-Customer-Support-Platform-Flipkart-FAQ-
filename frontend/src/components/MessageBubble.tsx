import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { motion, useAnimation } from "framer-motion"
import { Check, Circle } from "lucide-react"
import { BotAvatar, UserAvatar } from "./Avatar"
import { MessageActions } from "./MessageActions"
import { EASE_UI } from "../lib/motion"

function formatTime(iso?: string) {
  if (!iso) return ""
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
  } catch {
    return ""
  }
}

// Structured answers (payment modes, return steps) render as icon rows, not
// literal markdown bullets -- ul/ol become plain wrappers, li becomes a
// ListRow that reads list "kind" + a running index off context so ordered
// lists get numbered badges and unordered lists get dot icons.
type ListKind = "ordered" | "unordered"
const ListContext = createContext<{ kind: ListKind; counter: { current: number } }>({
  kind: "unordered",
  counter: { current: 0 },
})

const listVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.05 } },
}
const rowVariants = {
  hidden: { opacity: 0, y: 6 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.2, ease: EASE_UI } },
}

function ListRow({ children }: { children?: ReactNode }) {
  const { kind, counter } = useContext(ListContext)
  const index = counter.current++
  return (
    <motion.div variants={rowVariants} className="flex items-start gap-2 py-0.5">
      <motion.span
        className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-soft font-mono text-[10px] font-medium text-brand"
        initial={{ scale: 0.9 }}
        animate={{ scale: [0.9, 1.05, 1] }}
        transition={{ duration: 0.25, delay: 0.05 }}
      >
        {kind === "ordered" ? index + 1 : <Circle size={7} fill="currentColor" strokeWidth={0} />}
      </motion.span>
      <span className="text-[15px] leading-relaxed">{children}</span>
    </motion.div>
  )
}

// isFresh gates whether the row-stagger plays at all (only for a message
// that just streamed in live this session -- see Chat.tsx's freshMessageIds)
// so revisiting/switching threads never replays it. `controls` lets a click
// jump straight to rest state (cosmetic "skip") without restarting anything.
function makeMarkdownComponents(isFresh: boolean, controls: ReturnType<typeof useAnimation>) {
  function ListWrapper({ kind, children }: { kind: ListKind; children?: ReactNode }) {
    const counter = { current: 0 }
    return (
      <ListContext.Provider value={{ kind, counter }}>
        <motion.div
          className="my-2 flex flex-col gap-0.5"
          variants={listVariants}
          initial={isFresh ? "hidden" : false}
          animate={controls}
        >
          {children}
        </motion.div>
      </ListContext.Provider>
    )
  }
  return {
    ul: ({ children }: { children?: ReactNode }) => <ListWrapper kind="unordered">{children}</ListWrapper>,
    ol: ({ children }: { children?: ReactNode }) => <ListWrapper kind="ordered">{children}</ListWrapper>,
    li: ({ children }: { children?: ReactNode }) => <ListRow>{children}</ListRow>,
  }
}

export function MessageBubble({
  role,
  content,
  createdAt,
  userIdentifier,
  isStreaming = false,
  isFresh = false,
  steps,
  onRegenerate,
}: {
  role: "user" | "assistant"
  content: string
  createdAt?: string
  userIdentifier?: string
  isStreaming?: boolean
  isFresh?: boolean
  steps?: string[]
  onRegenerate?: () => void
}) {
  const isUser = role === "user"
  const controls = useAnimation()
  const [skipped, setSkipped] = useState(false)

  useEffect(() => {
    if (isFresh) controls.start("visible")
    else controls.set("visible")
    // Only ever meant to run once per mount -- isFresh doesn't change after
    // a message is created (see freshMessageIds in Chat.tsx).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleSkip() {
    if (!isFresh || skipped) return
    controls.set("visible") // jump instantly, cancels any in-flight stagger
    setSkipped(true)
  }

  const components = useMemo(() => makeMarkdownComponents(isFresh, controls), [isFresh, controls])

  return (
    <motion.div
      className={`group flex items-end gap-2.5 ${isUser ? "flex-row-reverse" : ""}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: [0, 0, 0.2, 1] }}
    >
      {isUser ? <UserAvatar identifier={userIdentifier ?? "?"} /> : <BotAvatar />}
      <div className={`flex flex-col ${isUser ? "items-end" : "items-start"} max-w-[75ch]`}>
        <div
          onClick={!isUser ? handleSkip : undefined}
          className={
            isUser
              ? "rounded-2xl rounded-br-sm bg-brand px-4 py-2.5 text-[15px] leading-relaxed text-white elevate-sm"
              : "rounded-r-2xl rounded-l-sm border-l-[3px] border-brand bg-surface px-4 py-2.5 elevate-sm transition-shadow hover:elevate-md"
          }
        >
          {isUser ? (
            <span className="whitespace-pre-wrap">{content}</span>
          ) : (
            <div className="prose prose-sm max-w-none prose-p:my-2 prose-headings:font-heading text-ink">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
                {content}
              </ReactMarkdown>
              {isStreaming && <span className="stream-cursor h-[1em] align-text-bottom" />}
            </div>
          )}
        </div>
        {!isUser && !isStreaming && steps && steps.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 px-1">
            {[...new Set(steps)].map((step) => (
              <span key={step} className="flex items-center gap-1 text-[11px] text-muted">
                <Check size={11} className="text-success" />
                {step}
              </span>
            ))}
          </div>
        )}
        <div className="mt-1 flex items-center gap-2 px-1">
          {createdAt && (
            <span className="font-mono text-[11px] uppercase tracking-wide text-muted">
              {formatTime(createdAt)}
            </span>
          )}
          {!isStreaming && <MessageActions content={content} isBot={!isUser} onRegenerate={onRegenerate} />}
        </div>
      </div>
    </motion.div>
  )
}
