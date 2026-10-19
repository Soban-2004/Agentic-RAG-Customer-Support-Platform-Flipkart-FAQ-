import { useState, type FormEvent } from "react"
import { Link, useNavigate } from "react-router-dom"
import { ArrowRight, Eye, EyeOff, LoaderCircle } from "lucide-react"
import { useAuth } from "../hooks/useAuth"
import { ApiError } from "../api/client"
import { AuthLayout } from "./AuthLayout"
export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const signup = mode === "signup"
  const { login, register } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  async function handleSubmit(event: FormEvent) {
    event.preventDefault(); setError(null); setSubmitting(true)
    try { await (signup ? register : login)(username, password); navigate("/", { replace: true }) }
    catch (err) { setError(err instanceof ApiError ? err.message : "We couldn't connect. Please try again.") }
    finally { setSubmitting(false) }
  }
  return <AuthLayout><form className="auth-form" onSubmit={handleSubmit}><span className="form-brand-mark" aria-hidden="true"><span /></span><h2>{signup ? "Your space for support." : "Good to see you."}</h2><p className="auth-intro">{signup ? "Create an account to keep your conversations together." : "Sign in to pick up where you left off."}</p><div className="form-field"><label htmlFor="username">Username</label><input id="username" name="username" placeholder="Your username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} minLength={signup ? 3 : undefined} maxLength={32} pattern={signup ? "[a-zA-Z0-9_-]+" : undefined} aria-describedby={signup ? "username-hint" : undefined} required />{signup && <p id="username-hint" className="field-hint">3–32 characters. Letters, numbers, underscores, or hyphens.</p>}</div><div className="form-field"><label htmlFor="password">Password</label><div className="password-field"><input id="password" name="password" type={showPassword ? "text" : "password"} placeholder={signup ? "At least 8 characters" : "Your password"} autoComplete={signup ? "new-password" : "current-password"} value={password} onChange={(event) => setPassword(event.target.value)} minLength={signup ? 8 : undefined} maxLength={128} required /><button type="button" aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} onClick={() => setShowPassword(!showPassword)}>{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button></div></div>{error && <p className="form-error" role="alert">{error}</p>}<button className="primary-button auth-submit" disabled={submitting} type="submit"><span>{submitting ? (signup ? "Creating account…" : "Signing in…") : (signup ? "Create account" : "Sign in")}</span>{submitting ? <LoaderCircle className="loading-spin" size={18} /> : <ArrowRight size={18} />}</button><p className="auth-alternative">{signup ? "Already have an account?" : "New to Aster?"} <Link to={signup ? "/login" : "/signup"}>{signup ? "Sign in" : "Create an account"}</Link></p><div className="auth-divider"><span />or explore first<span /></div><Link to="/demo" className="secondary-button">Try the demo <ArrowRight size={16} /></Link><p className="auth-fineprint">No account needed. Demo conversations aren't saved.</p></form></AuthLayout>
}
