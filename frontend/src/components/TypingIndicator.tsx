import { motion } from "framer-motion"
import { BotAvatar } from "./Avatar"
import { EASE_UI } from "../lib/motion"

export function TypingIndicator({ label }: { label: string }) {
  return (
    <motion.div
      className="flex items-end gap-2.5"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2, ease: EASE_UI }}
    >
      <BotAvatar />
      <div className="flex items-center gap-3 rounded-r-2xl rounded-l-sm border-l-[3px] border-brand bg-surface px-4 py-2.5 elevate-sm">
        <span className="h-1.5 w-10 overflow-hidden rounded-full bg-brand-soft">
          <span className="pulse-bar block h-full w-full rounded-full" />
        </span>
        <span className="shimmer-text text-sm font-medium">{label}</span>
      </div>
    </motion.div>
  )
}
