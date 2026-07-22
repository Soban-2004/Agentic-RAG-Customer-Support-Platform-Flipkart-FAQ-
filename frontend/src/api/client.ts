// Thin fetch wrapper -- cookies (the httpOnly JWT session cookie) ride along
// automatically via `credentials: "include"` since the proxy (dev) / static
// serving (prod) keeps everything same-origin. See vite.config.ts.

export interface User {
  identifier: string
}

export interface ThreadSummary {
  id: string
  title: string | null
  created_at: string
}

export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  created_at: string
}

export interface ThreadDetail extends ThreadSummary {
  messages: ChatMessage[]
}

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      // no JSON body
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  login: (username: string, password: string) =>
    request<User>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  me: () => request<User>("/api/auth/me"),
  listThreads: () => request<ThreadSummary[]>("/api/threads"),
  createThread: (title: string) =>
    request<ThreadSummary>("/api/threads", {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  getThread: (id: string) => request<ThreadDetail>(`/api/threads/${id}`),
  deleteThread: (id: string) => request<void>(`/api/threads/${id}`, { method: "DELETE" }),
  regeneratePrep: (id: string) =>
    request<void>(`/api/threads/${id}/regenerate-prep`, { method: "POST" }),
}

export { ApiError }
