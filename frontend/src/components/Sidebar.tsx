import { useEffect, useRef } from "react"
import { LogOut, PanelLeftClose, Plus, Trash2, MessageSquare } from "lucide-react"
import type { ThreadSummary } from "../api/client"
import { useAuth } from "../hooks/useAuth"
import { Brand } from "./Brand"
import { ThemeSwitch } from "./ThemeSwitch"

export function Sidebar({ threads, activeThreadId, open, onSelect, onNewChat, onDelete, onToggle }: {
  threads: ThreadSummary[]
  activeThreadId: string | null
  open: boolean
  onSelect: (id: string) => void
  onNewChat: () => void
  onDelete: (id: string) => void
  onToggle: () => void
}) {
  const { user, logout } = useAuth()
  const asideRef = useRef<HTMLElement>(null)
  useEffect(() => {
    if (!open || !window.matchMedia("(max-width: 767px)").matches) return
    const previous = document.activeElement as HTMLElement | null
    asideRef.current?.querySelector<HTMLButtonElement>("button")?.focus()
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") onToggle()
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
  }, [open, onToggle])
  if (!open) return null
  return (
    <>
      <button className="sidebar-backdrop" type="button" onClick={onToggle} aria-label="Close navigation" tabIndex={-1} />
      <aside className="sidebar" ref={asideRef} aria-label="Conversation navigation">
        <div className="sidebar-content">
          <div className="sidebar-top"><Brand /><button className="sidebar-close" type="button" onClick={onToggle} aria-label="Close sidebar"><PanelLeftClose size={18} /></button></div>
          <button className="sidebar-new" type="button" onClick={onNewChat}><Plus size={17} /> New conversation</button>
          <nav className="sidebar-history" aria-label="Chat history">
            <p className="history-label">Your conversations</p>
            {threads.map((thread) => (
              <div key={thread.id} className={`thread-row ${thread.id === activeThreadId ? "is-active" : ""}`}>
                <button className="thread-title" type="button" onClick={() => onSelect(thread.id)} aria-current={thread.id === activeThreadId ? "page" : undefined}><MessageSquare size={15} /><span>{thread.title || "New conversation"}</span></button>
                <button className="thread-delete" type="button" aria-label={`Delete ${thread.title || "conversation"}`} onClick={() => { if (window.confirm(`Delete "${thread.title || "New conversation"}"? This can't be undone.`)) onDelete(thread.id) }}><Trash2 size={14} /></button>
              </div>
            ))}
            {threads.length === 0 && <p className="sidebar-empty">Your saved conversations will appear here.</p>}
          </nav>
          <div className="sidebar-footer"><ThemeSwitch /><div className="sidebar-account"><span title={user?.identifier}>{user?.identifier}</span><button type="button" onClick={() => logout()} aria-label="Log out"><LogOut size={16} /></button></div></div>
        </div>
      </aside>
    </>
  )
}
