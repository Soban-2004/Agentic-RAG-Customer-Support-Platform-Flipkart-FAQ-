import { motion } from "framer-motion"
import { LogOut, Monitor, Moon, PanelLeftClose, Plus, Sun, Trash2 } from "lucide-react"
import type { ThreadSummary } from "../api/client"
import { useAuth } from "../hooks/useAuth"
import { useTheme, type Theme } from "../hooks/useTheme"
import { EASE_UI } from "../lib/motion"

const SIDEBAR_WIDTH = 260

const THEME_OPTIONS: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
]

function ThemeSwitch() {
  const { theme, setTheme } = useTheme()
  return (
    <div className="flex items-center gap-1 rounded-lg bg-muted-surface p-1">
      {THEME_OPTIONS.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          type="button"
          onClick={() => setTheme(value)}
          aria-label={`${label} theme`}
          title={`${label} theme`}
          className={`flex h-7 w-7 items-center justify-center rounded-md transition-colors ${
            theme === value ? "bg-surface text-brand elevate-sm" : "text-muted hover:text-ink"
          }`}
        >
          <Icon size={14} />
        </button>
      ))}
    </div>
  )
}

export function Sidebar({
  threads,
  activeThreadId,
  open,
  onSelect,
  onNewChat,
  onDelete,
  onToggle,
}: {
  threads: ThreadSummary[]
  activeThreadId: string | null
  open: boolean
  onSelect: (id: string) => void
  onNewChat: () => void
  onDelete: (id: string) => void
  onToggle: () => void
}) {
  const { user, logout } = useAuth()

  function handleDelete(e: React.MouseEvent, id: string, title: string | null) {
    e.stopPropagation()
    if (window.confirm(`Delete "${title || "New chat"}"? This can't be undone.`)) {
      onDelete(id)
    }
  }

  return (
    <motion.aside
      className="flex h-full shrink-0 flex-col overflow-hidden border-r border-border bg-surface"
      initial={false}
      animate={{ width: open ? SIDEBAR_WIDTH : 0 }}
      transition={{ duration: 0.25, ease: EASE_UI }}
    >
      <div style={{ width: SIDEBAR_WIDTH }} className="flex h-full flex-col">
        <div className="flex items-center gap-2 p-3">
          <button
            type="button"
            onClick={onNewChat}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-border py-2 text-sm font-medium text-ink transition-colors hover:bg-brand-soft hover:text-brand"
          >
            <Plus size={15} /> New chat
          </button>
          <button
            type="button"
            onClick={onToggle}
            aria-label="Close sidebar"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-hover hover:text-ink"
          >
            <PanelLeftClose size={17} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-2">
          {threads.map((t) => (
            <div
              key={t.id}
              onClick={() => onSelect(t.id)}
              className={`group flex cursor-pointer items-center justify-between rounded-lg px-3 py-2 text-left text-sm mb-1 transition-colors ${
                t.id === activeThreadId ? "bg-brand-soft text-brand" : "text-ink/80 hover:bg-hover"
              }`}
            >
              <span className="truncate">{t.title || "New chat"}</span>
              <button
                type="button"
                onClick={(e) => handleDelete(e, t.id, t.title)}
                aria-label="Delete chat"
                className="ml-2 shrink-0 rounded p-1 text-muted opacity-0 transition-opacity hover:bg-hover hover:text-danger group-hover:opacity-100"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
          {threads.length === 0 && <p className="px-3 py-2 text-sm text-muted">No chats yet</p>}
        </div>

        <div className="flex items-center justify-between gap-2 border-t border-border p-3">
          <ThemeSwitch />
          <button
            type="button"
            onClick={() => logout()}
            className="flex shrink-0 items-center gap-1.5 rounded-lg bg-muted-surface px-2.5 py-1.5 text-xs font-medium text-ink/70 transition-colors hover:bg-danger-soft hover:text-danger"
          >
            <LogOut size={13} /> Log out
          </button>
        </div>
        <div className="border-t border-border px-3 py-2 text-xs text-muted">{user?.identifier}</div>
      </div>
    </motion.aside>
  )
}
