import { motion, useReducedMotion } from "framer-motion"
import { BotAvatar } from "./Avatar"

export function TypingIndicator({ label }: { label: string }) {
  const reducedMotion = useReducedMotion()
  return (
    <motion.div className="typing-indicator" initial={reducedMotion ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: reducedMotion ? 0 : 0.2 }} role="status">
      <BotAvatar />
      <div className="typing-content">
        <span className="thinking-dots" aria-hidden="true"><i /><i /><i /></span>
        <span>{label || "Preparing your response…"}</span>
      </div>
    </motion.div>
  )
}
