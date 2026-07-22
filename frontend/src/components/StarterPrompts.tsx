import { motion } from "framer-motion"
import { EASE_UI } from "../lib/motion"

// Same four example prompts the old Chainlit @cl.set_starters used --
// purely client-side/static, no backend involvement, shown only on an empty
// new thread so a first-time visitor can see RAG/tool-calling/memory in
// action without having to think of a question themselves.
const STARTERS = [
  { label: "📦 Track my order", message: "What's the status of order FK1001?" },
  { label: "💸 Check a refund", message: "What's the status of refund RF2001?" },
  { label: "📋 Return policy", message: "What is Flipkart's return policy?" },
  {
    label: "🎫 Talk to a human",
    message: "I want to talk to a human agent about my order FK1004, it arrived damaged.",
  },
]

export function StarterPrompts({ onPick }: { onPick: (message: string) => void }) {
  return (
    <motion.div
      className="flex h-full flex-col items-center justify-center gap-6 px-4 text-center"
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3, ease: EASE_UI }}
    >
      <div>
        <h1 className="font-heading text-2xl font-semibold text-ink">
          🛍️ Flipkart Customer Chatbot
        </h1>
        <p className="mt-2 text-muted">Ask about an order, a refund, or how something works.</p>
      </div>
      <div className="grid w-full max-w-xl grid-cols-1 gap-3 sm:grid-cols-2">
        {STARTERS.map((s) => (
          <button
            key={s.label}
            type="button"
            onClick={() => onPick(s.message)}
            className="rounded-xl border border-border bg-surface p-3 text-left text-sm elevate-sm transition-all hover:-translate-y-0.5 hover:border-brand/40 hover:elevate-md"
          >
            <div className="font-medium text-ink">{s.label}</div>
            <div className="mt-0.5 text-muted">{s.message}</div>
          </button>
        ))}
      </div>
    </motion.div>
  )
}
