import { useCallback, useEffect, useRef, useState } from "react"

type ServerFrame =
  | { type: "token"; delta: string }
  | { type: "status"; label: string }
  | { type: "done"; content: string }

/** One WS connection per open thread. Protocol (see src/api/chat_ws.py):
 * client sends {content}, server streams {type:"status",label} frames while
 * working (guardrail scan, tool lookups -- most real answers never stream a
 * token at all, so these are the only progress signal), {type:"token",delta}
 * frames when it does, then exactly one {type:"done",content} frame carrying
 * the authoritative final text (post output-guardrail-scan -- may differ
 * from the concatenated deltas, e.g. PII redaction).
 *
 * Status labels seen during a turn are also accumulated (client-side only --
 * the backend never persists them) and handed to `onDone` as a "steps
 * trail", e.g. ["Searching Flipkart's policies...", "Finalizing response..."]
 * -- purely a this-session UI nicety, gone on reload/thread-revisit. */
export function useChatSocket(
  threadId: string | null,
  onDone: (content: string, steps: string[]) => void,
) {
  const wsRef = useRef<WebSocket | null>(null)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone
  const stepsRef = useRef<string[]>([])

  const [connected, setConnected] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [pending, setPending] = useState("")
  const [statusLabel, setStatusLabel] = useState<string | null>(null)

  useEffect(() => {
    if (!threadId) return
    const protocol = window.location.protocol === "https:" ? "wss" : "ws"
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/chat/${threadId}`)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onmessage = (event) => {
      const frame = JSON.parse(event.data) as ServerFrame
      if (frame.type === "status") {
        stepsRef.current.push(frame.label)
        setStatusLabel(frame.label)
      } else if (frame.type === "token") {
        setStatusLabel(null)
        setPending((prev) => prev + frame.delta)
      } else if (frame.type === "done") {
        const steps = stepsRef.current
        stepsRef.current = []
        setStreaming(false)
        setPending("")
        setStatusLabel(null)
        onDoneRef.current(frame.content, steps)
      }
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [threadId])

  const send = useCallback((content: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    stepsRef.current = []
    setStreaming(true)
    setPending("")
    setStatusLabel(null)
    wsRef.current.send(JSON.stringify({ content }))
  }, [])

  return { connected, streaming, pending, statusLabel, send }
}
