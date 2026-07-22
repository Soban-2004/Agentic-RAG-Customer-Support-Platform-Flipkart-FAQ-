import { useState, type FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "../hooks/useAuth"
import { ApiError } from "../api/client"

export function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(username, password)
      navigate("/", { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex h-full items-center justify-center bg-bg p-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-2xl bg-surface p-8 elevate-md"
      >
        <h1 className="mb-1 text-center font-heading text-xl font-semibold text-ink">
          🛍️ Flipkart Support
        </h1>
        <p className="mb-6 text-center text-sm text-muted">Sign in to continue</p>

        <label className="mb-1 block text-sm font-medium text-ink" htmlFor="username">
          Username
        </label>
        <input
          id="username"
          className="mb-4 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-ink outline-none transition-[border-color,box-shadow] duration-150 ease-[var(--ease-ui)] focus:border-brand focus:shadow-[0_0_0_3px_var(--brand-ring)]"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
          required
        />

        <label className="mb-1 block text-sm font-medium text-ink" htmlFor="password">
          Password
        </label>
        <input
          id="password"
          type="password"
          className="mb-4 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-ink outline-none transition-[border-color,box-shadow] duration-150 ease-[var(--ease-ui)] focus:border-brand focus:shadow-[0_0_0_3px_var(--brand-ring)]"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />

        {error && <p className="mb-4 text-sm text-danger">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-brand py-2 text-sm font-medium text-white transition-colors hover:bg-brand-hover disabled:opacity-50"
        >
          {submitting ? "Signing in..." : "Sign in"}
        </button>

        <p className="mt-4 text-center text-xs text-muted">
          No self-serve signup -- ask an admin to provision your account.
        </p>
      </form>
    </div>
  )
}
