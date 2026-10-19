import { Package, RotateCcw, ReceiptText, Headphones, ArrowUpRight } from "lucide-react"
import { Aperture } from "./Brand"
const STARTERS = [
  { label: "Follow an order", detail: "Try example order FK1001", icon: Package, message: "What's the status of order FK1001?" },
  { label: "Check a refund", detail: "Try example refund RF2001", icon: RotateCcw, message: "What's the status of refund RF2001?" },
  { label: "Understand returns", detail: "Explore Flipkart's return policy", icon: ReceiptText, message: "What is Flipkart's return policy?" },
  { label: "Talk to someone", detail: "Try a support escalation", icon: Headphones, message: "I want to talk to a human agent about my order FK1004, it arrived damaged." },
]
export function StarterPrompts({ onPick, disabled = false }: { onPick: (message: string) => void; disabled?: boolean }) {
  return <section className="welcome"><Aperture /><h1>Let's clear<br />things up.</h1><p className="welcome-description">Orders, refunds, and the questions in between.<br className="desktop-break" /> A little help, right where you need it.</p><div className="starter-grid">{STARTERS.map(({ label, detail, icon: Icon, message }) => <button className="starter-action" key={label} type="button" disabled={disabled} onClick={() => onPick(message)} onPointerMove={(event) => { const rect = event.currentTarget.getBoundingClientRect(); event.currentTarget.style.setProperty("--pointer-x", `${event.clientX - rect.left}px`); event.currentTarget.style.setProperty("--pointer-y", `${event.clientY - rect.top}px`); }}><span className="starter-icon"><Icon size={20} strokeWidth={1.65} /></span><span className="starter-copy"><strong>{label}</strong><span>{detail}</span></span><ArrowUpRight className="starter-arrow" size={17} /></button>)}</div><p className="welcome-note">Example IDs use demonstration data.</p></section>
}
