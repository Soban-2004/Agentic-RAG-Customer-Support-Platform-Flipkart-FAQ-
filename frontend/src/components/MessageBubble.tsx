import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { motion, useReducedMotion } from "framer-motion"
import { BotAvatar, UserAvatar } from "./Avatar"
import { MessageActions } from "./MessageActions"

function formatTime(iso?: string) {
  if (!iso) return ""
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
}

export function MessageBubble({ role, content, createdAt, userIdentifier, isStreaming = false, isFresh = false, steps, onRegenerate }: {
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
  const reducedMotion = useReducedMotion()
  const time = formatTime(createdAt)

  return (
    <motion.div className={`message-row ${isUser ? "user" : "assistant"}`}
      initial={isFresh && !reducedMotion ? { opacity: 0, y: 8 } : false}
      animate={{ opacity: 1, y: 0 }} transition={{ duration: reducedMotion ? 0 : 0.2, ease: [0, 0, 0.2, 1] }}>
      {isUser ? <UserAvatar identifier={userIdentifier ?? "?"} /> : <BotAvatar />}
      <div className="message-body" style={{ minWidth: 0 }}>
        <div className="message-content">
          {isUser ? <span className="message-user-text">{content}</span> : (
            <div className="message-markdown" style={{ minWidth: 0 }}>
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
                table: ({ children }) => <div className="message-table-scroll" tabIndex={0} role="region" aria-label="Response table" style={{ overflowX: "auto" }}><table>{children}</table></div>,
                pre: ({ children }) => <pre className="message-code" tabIndex={0} style={{ overflowX: "auto" }}>{children}</pre>,
              }}>{content}</ReactMarkdown>
              {isStreaming && <span className="stream-cursor" aria-hidden="true" />}
            </div>
          )}
        </div>
        {!isUser && !isStreaming && steps && steps.length > 0 && (
          <details className="message-steps">
            <summary>Response details</summary>
            <ul>{[...new Set(steps)].map((step) => <li key={step}>{step}</li>)}</ul>
          </details>
        )}
        <div className="message-meta">
          <span className="message-author">{isUser ? "You" : "Aster"}</span>
          {time && <time dateTime={createdAt}>{time}</time>}
          {!isStreaming && <MessageActions content={content} isBot={!isUser} onRegenerate={onRegenerate} />}
        </div>
      </div>
    </motion.div>
  )
}
