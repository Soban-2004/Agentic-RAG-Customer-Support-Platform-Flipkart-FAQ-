import type { ImageAttachment } from "../api/client"
import { useCallback, useEffect, useRef, useState } from "react"

export type CompletionMetadata = { assistant_message_id?: string; client_message_id?: string; reload_history?: boolean }

type Outgoing = { content: string; client_message_id: string; regenerate_message_id?: string; image?: ImageAttachment }

type ServerFrame =
  | { type: "token"; delta: string }
  | { type: "status"; label: string }
  | ({ type: "done"; content: string } & CompletionMetadata)
  | { type: "error"; code: string; message: string; client_message_id?: string }

export function useChatSocket(path: string | null, onDone: (content: string, steps: string[], metadata?: CompletionMetadata) => void) {
  const wsRef = useRef<WebSocket | null>(null)
  const pendingFrame = useRef<{ path: string; frame: Outgoing } | null>(null)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone
  const stepsRef = useRef<string[]>([])
  const streamingRef = useRef(false)
  const [generation, setGeneration] = useState(0)
  const [connectionState, setConnectionState] = useState<"ready" | "connecting" | "offline">(path ? "connecting" : "ready")
  const [streaming, setStreaming] = useState(false)
  const [pending, setPending] = useState("")
  const [statusLabel, setStatusLabel] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setStreaming(false)
    streamingRef.current = false
    setPending("")
    setStatusLabel(null)
    setError(null)
    stepsRef.current = []
    if (!path) {
      setConnectionState("ready")
      return
    }
    if (pendingFrame.current?.path !== path) pendingFrame.current = null
    setConnectionState("connecting")
    const protocol = window.location.protocol === "https:" ? "wss" : "ws"
    const basePath = import.meta.env.BASE_URL.replace(/\/$/, "")
    const ws = new WebSocket(`${protocol}://${window.location.host}${basePath}${path}`)
    wsRef.current = ws
    ws.onopen = () => {
      if (!active) return
      setConnectionState("ready")
      if (pendingFrame.current?.path === path) {
        ws.send(JSON.stringify(pendingFrame.current.frame))
        streamingRef.current = true
        setStreaming(true)
        setStatusLabel("Recovering your message?")
      }
    }
    ws.onclose = (event) => {
      if (!active) return
      setConnectionState("offline")
      if (event.code === 1008) {
        pendingFrame.current = null
        setError("Your session ended or this request isn't permitted. Please sign in again.")
      } else if (event.code === 1013) {
        setError("Support is busy or temporarily unavailable. Please reconnect shortly.")
      }
      if (streamingRef.current && event.code !== 1008 && event.code !== 1013) setError("The connection was interrupted before the reply finished. Reconnect to continue.")
      streamingRef.current = false
      setStreaming(false)
      setPending("")
      setStatusLabel(null)
    }
    ws.onerror = () => { if (active) setConnectionState("offline") }
    ws.onmessage = (event) => {
      if (!active) return
      let frame: ServerFrame
      try { frame = JSON.parse(event.data) as ServerFrame } catch { return }
      if (frame.type === "error") {
        pendingFrame.current = null
        streamingRef.current = false
        setStreaming(false)
        setPending("")
        setStatusLabel(null)
        setError(frame.message)
      } else if (frame.type === "status") {
        stepsRef.current.push(frame.label)
        setStatusLabel(frame.label)
      } else if (frame.type === "token") {
        setStatusLabel(null)
        setPending((prev) => prev + frame.delta)
      } else if (frame.type === "done") {
        const steps = stepsRef.current
        stepsRef.current = []
        streamingRef.current = false
        setStreaming(false)
        setPending("")
        setStatusLabel(null)
        pendingFrame.current = null
        onDoneRef.current(frame.content, steps, frame)
      }
    }
    return () => {
      active = false
      ws.close()
      if (wsRef.current === ws) wsRef.current = null
    }
  }, [path, generation])

  const send = useCallback((content: string, options?: { regenerate_message_id?: string; image?: ImageAttachment }) => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN || streamingRef.current) return false
    if (!path) return false
    const frame: Outgoing = { content, client_message_id: crypto.randomUUID(), ...options }
    try { ws.send(JSON.stringify(frame)); pendingFrame.current = { path, frame } } catch {
      setError("Your message could not be sent. Reconnect and try again.")
      return false
    }
    stepsRef.current = []
    streamingRef.current = true
    setStreaming(true)
    setPending("")
    setStatusLabel("Working on your question…")
    setError(null)
    return true
  }, [path])
  const reconnect = useCallback(() => setGeneration((value) => value + 1), [])
  return { connected: connectionState === "ready" && !!path, connectionState, streaming, pending, statusLabel, error, send, reconnect }
}
