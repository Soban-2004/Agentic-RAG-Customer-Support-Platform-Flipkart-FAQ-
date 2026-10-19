import type { ReactNode } from "react"
import { Link } from "react-router-dom"
import { ArrowUpRight, MessageCircle, Package, RotateCcw } from "lucide-react"
import { Brand, Aperture } from "./Brand"
import { ThemeSwitch } from "./ThemeSwitch"
export function AuthLayout({ children }: { children: ReactNode }) {
  return <main className="auth-page"><header className="auth-header"><Link to="/demo" aria-label="Aster demo"><Brand compact /></Link><ThemeSwitch /></header><div className="auth-layout"><section className="auth-story"><Aperture className="auth-aperture" /><h1>A little help.<br />A lot of clarity.</h1><p>A thoughtful space for your orders, refunds,<br className="desktop-break" /> and everything you need to figure out.</p><div className="auth-topics"><span><Package size={16} /> Orders</span><span><RotateCcw size={16} /> Refunds</span><span><MessageCircle size={16} /> Answers</span></div><Link className="auth-demo-link" to="/demo">Take a look around <ArrowUpRight size={17} /></Link></section><section className="auth-form-panel">{children}</section></div><footer className="auth-footer"><span>Made for the questions that come after checkout.</span><span>Flipkart support assistant</span></footer></main>
}
