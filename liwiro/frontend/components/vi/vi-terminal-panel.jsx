"use client"

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react"
import { FitAddon } from "@xterm/addon-fit"
import { Terminal } from "@xterm/xterm"
import { Eraser } from "lucide-react"
import { CopyIconButton } from "@/components/ui/copy-icon-button"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useDocumentVisible } from "@/hooks/use-document-visible"
import { authHeaders } from "@/lib/auth"
import { computeJitteredDelayMs, createFailureCircuit } from "@/lib/request-circuit"
import { toast } from "sonner"

const PRIMARY_PROMPT = "> "
const CONTINUATION_PROMPT = "... "
const UTILITY_COMMANDS = new Set(["help", "clear", "status", "pwd", "ls", "la", "ll", "tree", "files", "dirs", "cat", "open", "run", "source-dir", "reset", "exit"])
const PATH_COMPLETION_COMMANDS = new Set([":cat", ":open", ":run", ":ls", ":la", ":ll", ":tree", ":dirs"])
const FILE_PATH_COMPLETION_COMMANDS = new Set([":cat", ":open", ":run"])
const TRANSCRIPT_FLUSH_INTERVAL_MS = 64
const LISTING_CACHE_TTL_MS = 1200
const TERMINAL_ACTIVE_POLL_INTERVAL_MS = 250
const TERMINAL_IDLE_POLL_INTERVAL_MS = 900
const TERMINAL_RETRY_BASE_MS = 2_000
const TERMINAL_RETRY_MAX_MS = 30_000

function joinTranscript(parts) {
  return parts
    .map((part) => String(part || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").replace(/^\n+|\n+$/g, ""))
    .filter(Boolean)
    .join("\n")
}

function formatTerminalEvent(label, detail = "") {
  const timestamp = new Intl.DateTimeFormat([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date())
  const entries = [`[${timestamp}] ${String(label || "").trim()}`]
  const normalizedDetail = String(detail || "").replace(/\r\n/g, "\n").trim()
  if (normalizedDetail) {
    entries.push(normalizedDetail)
  }
  return entries.join("\n")
}

function terminalTranscriptBlock(text) {
  return String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n")
}

function parsePromptFromOutput(text, fallback = PRIMARY_PROMPT) {
  const sample = String(text || "")
  if (sample.endsWith(CONTINUATION_PROMPT)) return CONTINUATION_PROMPT
  if (sample.endsWith(PRIMARY_PROMPT)) return PRIMARY_PROMPT
  return fallback
}

function resolveInlineInputPrefix(transcript, fallback = PRIMARY_PROMPT) {
  const normalized = terminalTranscriptBlock(transcript)
  const prompt = promptValue(fallback)
  if (!normalized) return prompt
  const lines = normalized.split("\n")
  const lastLine = String(lines[lines.length - 1] || "")
  if (!lastLine) return prompt
  if (lastLine.endsWith(CONTINUATION_PROMPT)) return CONTINUATION_PROMPT
  if (lastLine.endsWith(PRIMARY_PROMPT)) return PRIMARY_PROMPT
  return lastLine
}

function promptValue(value, fallback = PRIMARY_PROMPT) {
  return value === undefined || value === null ? fallback : String(value)
}

function normalizePortalPath(value) {
  const raw = String(value || "").trim().replace(/\\/g, "/")
  if (!raw || raw === ".") return ""
  const withoutDotPrefix = raw.replace(/^\.\/+/, "").replace(/\/+$/, "")
  const parts = withoutDotPrefix.split("/").filter(Boolean)
  if (parts.some((part) => part === "." || part === "..")) {
    throw new Error("Path must stay within the VI source directory")
  }
  return parts.join("/")
}

function normalizeUtilityCommandInput(value) {
  const trimmed = String(value || "").trim()
  if (!trimmed) return ""
  if (trimmed.startsWith(":")) return trimmed
  const match = /^([A-Za-z][\w-]*)(?:\s+(.*))?$/.exec(trimmed)
  if (!match) return ""
  const command = String(match[1] || "").toLowerCase()
  if (!UTILITY_COMMANDS.has(command)) return ""
  const args = String(match[2] || "").trim()
  return `:${command}${args ? ` ${args}` : ""}`
}

function formatListTimestamp(value) {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "-"
  return new Intl.DateTimeFormat([], {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date)
}

function formatListSize(value) {
  if (value === null || value === undefined || value === "") return "-"
  const size = Number(value)
  if (!Number.isFinite(size) || size < 0) return "-"
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function longestCommonPrefix(values) {
  if (!Array.isArray(values) || values.length === 0) return ""
  let prefix = String(values[0] || "")
  for (let index = 1; index < values.length; index += 1) {
    const candidate = String(values[index] || "")
    while (prefix && !candidate.startsWith(prefix)) {
      prefix = prefix.slice(0, -1)
    }
    if (!prefix) return ""
  }
  return prefix
}

export const VITerminalPanel = forwardRef(function VITerminalPanel(
  { backend, sourceDir = "", activeFilePath = "", onSessionChange, onOpenFile, autoConnect = true },
  ref,
) {
  const cardRef = useRef(null)
  const containerRef = useRef(null)
  const terminalRef = useRef(null)
  const fitAddonRef = useRef(null)
  const resizeObserverRef = useRef(null)
  const reconnectTimerRef = useRef(null)
  const pollTimerRef = useRef(null)
  const pollInFlightRef = useRef(false)
  const recoveryInFlightRef = useRef(false)
  const lastSeqRef = useRef(0)
  const lastResizeRef = useRef({ cols: 120, rows: 32 })
  const transcriptFlushTimerRef = useRef(null)
  const currentPromptRef = useRef(PRIMARY_PROMPT)
  const localInputBufferRef = useRef("")
  const localCursorIndexRef = useRef(0)
  const utilityModeRef = useRef(false)
  const historyRef = useRef([])
  const historyIndexRef = useRef(-1)
  const historyDraftRef = useRef("")
  const mountedRef = useRef(false)
  const closedByUserRef = useRef(false)
  const completionVersionRef = useRef(0)
  const hasTranscriptRef = useRef(false)
  const transcriptTextRef = useRef("")
  const pendingTranscriptRef = useRef([])
  const filesCacheRef = useRef({ data: null, promise: null, expiresAt: 0 })
  const directoriesCacheRef = useRef(new Map())
  const reconnectCircuitRef = useRef(createFailureCircuit({
    failureThreshold: 4,
    baseDelayMs: TERMINAL_RETRY_BASE_MS,
    maxDelayMs: TERMINAL_RETRY_MAX_MS,
  }))
  const [connected, setConnected] = useState(false)
  const [active, setActive] = useState(false)
  const [hasTranscript, setHasTranscript] = useState(false)
  const [completionState, setCompletionState] = useState(null)
  const [connectionHealth, setConnectionHealth] = useState({
    degraded: false,
    paused: false,
    retryAfterMs: 0,
    reason: "",
    detail: "",
  })
  const [sessionInfo, setSessionInfo] = useState({
    sessionKey: "",
    cols: 120,
    rows: 32,
    prompt: PRIMARY_PROMPT,
    mode: "repl",
    cwd: "",
  })
  const documentVisible = useDocumentVisible()

  const updateHasTranscript = (value) => {
    const next = Boolean(value)
    if (hasTranscriptRef.current === next) return
    hasTranscriptRef.current = next
    setHasTranscript(next)
  }

  const flushTranscript = () => {
    if (transcriptFlushTimerRef.current) {
      clearTimeout(transcriptFlushTimerRef.current)
      transcriptFlushTimerRef.current = null
    }
    if (!pendingTranscriptRef.current.length) {
      return transcriptTextRef.current
    }
    transcriptTextRef.current += pendingTranscriptRef.current.join("")
    pendingTranscriptRef.current = []
    updateHasTranscript(transcriptTextRef.current.trim())
    return transcriptTextRef.current
  }

  const scheduleTranscriptFlush = () => {
    if (transcriptFlushTimerRef.current) return
    transcriptFlushTimerRef.current = setTimeout(() => {
      transcriptFlushTimerRef.current = null
      flushTranscript()
    }, TRANSCRIPT_FLUSH_INTERVAL_MS)
  }

  const setTranscript = (value) => {
    if (transcriptFlushTimerRef.current) {
      clearTimeout(transcriptFlushTimerRef.current)
      transcriptFlushTimerRef.current = null
    }
    pendingTranscriptRef.current = []
    transcriptTextRef.current = String(value || "")
    updateHasTranscript(transcriptTextRef.current.trim())
  }

  const appendTranscript = (value) => {
    const next = terminalTranscriptBlock(value)
    if (!next) return
    pendingTranscriptRef.current.push(next)
    if (!hasTranscriptRef.current && next.trim()) {
      updateHasTranscript(true)
    }
    scheduleTranscriptFlush()
  }

  const currentTranscriptText = () => flushTranscript()

  const invalidateListingCaches = () => {
    filesCacheRef.current = { data: null, promise: null, expiresAt: 0 }
    directoriesCacheRef.current.clear()
  }

  const writeToTerminal = (value, { record = true } = {}) => {
    const next = String(value || "")
    if (!next) return
    terminalRef.current?.write(next)
    if (record) {
      appendTranscript(next)
    }
    currentPromptRef.current = parsePromptFromOutput(next, currentPromptRef.current)
  }

  const writeEvent = (label, detail = "") => {
    writeToTerminal(`\r\n${formatTerminalEvent(label, detail)}\r\n`)
  }

  const dismissCompletionPopup = () => {
    completionVersionRef.current += 1
    setCompletionState(null)
  }

  const clearTerminalViewport = ({ preservePrompt = true } = {}) => {
    dismissCompletionPopup()
    terminalRef.current?.reset()
    setTranscript("")
    if (preservePrompt) {
      writeToTerminal(promptValue(currentPromptRef.current))
      if (localInputBufferRef.current) {
        rewriteLocalInput(localInputBufferRef.current)
      }
    }
  }

  const rewriteLocalInput = (buffer) => {
    const terminal = terminalRef.current
    if (!terminal) return
    const normalizedBuffer = String(buffer || "")
    const lines = normalizedBuffer.split("\n")
    if (normalizedBuffer.includes("\n")) {
      localCursorIndexRef.current = normalizedBuffer.length
    }
    const lineCount = Math.max(1, lines.length)
    let clearSequence = "\x1b[2K\r"
    for (let index = 1; index < lineCount; index += 1) {
      clearSequence += "\x1b[1A\x1b[2K\r"
    }
    terminal.write(clearSequence)
    const transcript = currentTranscriptText()
    const inlinePrefix = resolveInlineInputPrefix(transcript, currentPromptRef.current)
    const continuationPrompt = inlinePrefix ? CONTINUATION_PROMPT : ""
    const rendered = lines.map((line, index) => `${index === 0 ? inlinePrefix : continuationPrompt}${line}`).join("\r\n")
    terminal.write(rendered)
    if (!normalizedBuffer.includes("\n")) {
      const cursorIndex = Math.max(0, Math.min(localCursorIndexRef.current, normalizedBuffer.length))
      const trailingLength = normalizedBuffer.length - cursorIndex
      if (trailingLength > 0) {
        terminal.write(`\x1b[${trailingLength}D`)
      }
    }
  }

  const fitTerminal = () => {
    const fitAddon = fitAddonRef.current
    const terminal = terminalRef.current
    if (!fitAddon || !terminal) return
    fitAddon.fit()
    const cols = terminal.cols || 120
    const rows = terminal.rows || 32
    lastResizeRef.current = { cols, rows }
    setSessionInfo((prev) => ({ ...prev, cols, rows }))
    if (connected) {
      void resizeTerminal(cols, rows)
    }
  }

  const syncSession = (payload) => {
    const next = {
      sessionKey: String(payload?.sessionKey || payload?.session_key || ""),
      cols: Number(payload?.cols || terminalRef.current?.cols || 120),
      rows: Number(payload?.rows || terminalRef.current?.rows || 32),
      prompt:
        payload && Object.prototype.hasOwnProperty.call(payload, "prompt")
          ? String(payload?.prompt ?? "")
          : promptValue(currentPromptRef.current),
      active: Boolean(payload?.active),
      mode: String(payload?.mode || "repl"),
      cwd: String(payload?.cwd || payload?.sourceDir || sourceDir || ""),
    }
    currentPromptRef.current = next.prompt
    setSessionInfo((prev) => ({ ...prev, ...next }))
    setActive(next.active)
    onSessionChange?.({
      active: next.active,
      prompt: next.prompt,
      cols: next.cols,
      rows: next.rows,
      sessionKey: next.sessionKey,
      mode: next.mode,
    })
  }

  const publishInactiveSession = () => {
    dismissCompletionPopup()
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    const next = {
      active: false,
      prompt: promptValue(currentPromptRef.current),
      cols: terminalRef.current?.cols || sessionInfo.cols || 120,
      rows: terminalRef.current?.rows || sessionInfo.rows || 32,
      sessionKey: sessionInfo.sessionKey || "",
      mode: sessionInfo.mode || "repl",
    }
    setConnected(false)
    setActive(false)
    onSessionChange?.(next)
  }

  const stopPolling = () => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
  }

  const markTerminalHealthy = () => {
    const next = reconnectCircuitRef.current.succeed()
    setConnectionHealth({
      degraded: next.degraded,
      paused: next.paused,
      retryAfterMs: next.retryAfterMs,
      reason: next.reason,
      detail: "",
    })
    return next
  }

  const markTerminalFailure = (error, { pause = false, retryAfterMs = 0, reason = "", detail = "" } = {}) => {
    const next = reconnectCircuitRef.current.fail(error, { pause, retryAfterMs, reason, detail })
    setConnectionHealth({
      degraded: true,
      paused: next.paused,
      retryAfterMs: next.retryAfterMs,
      reason: next.reason || next.lastError,
      detail: next.paused
        ? "Paused to protect system stability."
        : String(detail || next.reason || next.lastError || "VI terminal reconnect slowed after errors.").trim(),
    })
    return next
  }

  const nextTerminalPollDelay = (payload = null, chunks = []) => {
    if (!documentVisible) {
      return TERMINAL_IDLE_POLL_INTERVAL_MS
    }
    if (Array.isArray(chunks) && chunks.length > 0) {
      return TERMINAL_ACTIVE_POLL_INTERVAL_MS
    }
    if (String(payload?.mode || sessionInfo.mode || "").trim().toLowerCase() === "file") {
      return TERMINAL_ACTIVE_POLL_INTERVAL_MS
    }
    return TERMINAL_IDLE_POLL_INTERVAL_MS
  }

  const ensureTerminalInView = () => {
    if (typeof window === "undefined") return
    const card = cardRef.current
    if (!card) return
    const rect = card.getBoundingClientRect()
    const topInset = 96
    const bottomInset = 24
    let delta = 0
    if (rect.top < topInset) {
      delta = rect.top - topInset
    } else if (rect.bottom > window.innerHeight - bottomInset) {
      delta = rect.bottom - window.innerHeight + bottomInset
    }
    if (delta) {
      window.scrollBy({ top: delta, behavior: "smooth" })
    }
  }

  const openSession = async ({ reset = false } = {}) => {
    const terminal = terminalRef.current
    const cols = terminal?.cols || sessionInfo.cols || 120
    const rows = terminal?.rows || sessionInfo.rows || 32
    const res = await fetch(`${backend}/platform/vi/terminal/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ cols, rows, reset }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      throw new Error(data?.error || "Failed to start VI terminal")
    }
    syncSession(data)
    return data
  }

  const schedulePoll = (delay = TERMINAL_IDLE_POLL_INTERVAL_MS) => {
    if (!mountedRef.current || closedByUserRef.current || !documentVisible || pollTimerRef.current) return
    pollTimerRef.current = setTimeout(() => {
      pollTimerRef.current = null
      void pollTerminal()
    }, Math.max(0, Number(delay) || 0))
  }

  const scheduleSessionRecovery = (delay = TERMINAL_RETRY_BASE_MS) => {
    if (!mountedRef.current || closedByUserRef.current || !documentVisible || reconnectTimerRef.current) return
    reconnectTimerRef.current = setTimeout(async () => {
      reconnectTimerRef.current = null
      try {
        const recovered = await recoverTerminalSession({ scheduleImmediatePoll: false })
        if (recovered) {
          markTerminalHealthy()
          setConnected(true)
          schedulePoll(0)
          return
        }
        const failureState = markTerminalFailure(new Error("VI terminal session is unavailable"), {
          detail: "VI terminal reconnect slowed after errors.",
        })
        if (!failureState.paused && !closedByUserRef.current && mountedRef.current && documentVisible) {
          scheduleSessionRecovery(computeJitteredDelayMs(failureState.retryAfterMs || TERMINAL_RETRY_BASE_MS))
        }
      } catch (error) {
        const failureState = markTerminalFailure(error, {
          detail: "VI terminal reconnect slowed after errors.",
        })
        if (!failureState.paused && !closedByUserRef.current && mountedRef.current && documentVisible) {
          scheduleSessionRecovery(computeJitteredDelayMs(failureState.retryAfterMs || TERMINAL_RETRY_BASE_MS))
        }
      }
    }, Math.max(0, Number(delay) || 0))
  }

  const recoverTerminalSession = async ({ scheduleImmediatePoll = true } = {}) => {
    if (!mountedRef.current || closedByUserRef.current || recoveryInFlightRef.current) return false
    recoveryInFlightRef.current = true
    try {
      const data = await openSession({ reset: false })
      const recovered = Boolean(data?.active)
      if (recovered) {
        markTerminalHealthy()
        setConnected(true)
        if (scheduleImmediatePoll) {
          schedulePoll(0)
        }
      }
      return recovered
    } catch {
      return false
    } finally {
      recoveryInFlightRef.current = false
    }
  }

  const pollTerminal = async () => {
    if (pollInFlightRef.current || closedByUserRef.current || !documentVisible) return
    const reconnectSnapshot = reconnectCircuitRef.current.snapshot()
    if (reconnectSnapshot.paused) return
    pollInFlightRef.current = true
    let shouldContinue = false
    let retryMode = ""
    let nextDelay = TERMINAL_IDLE_POLL_INTERVAL_MS
    try {
      const res = await fetch(`${backend}/platform/vi/terminal/poll?lastSeq=${encodeURIComponent(String(lastSeqRef.current || 0))}`, {
        headers: authHeaders(),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(data?.error || "Failed to poll VI terminal")
      }

      setConnected(true)
      syncSession(data)

      if (data?.reset) {
        terminalRef.current?.reset()
        setTranscript("")
      }

      const chunks = Array.isArray(data?.chunks) ? data.chunks : []
      chunks.forEach((chunk) => {
        writeToTerminal(String(chunk?.data || ""))
      })

      const nextLastSeq = Number(data?.lastSeq)
      if (Number.isFinite(nextLastSeq) && nextLastSeq >= 0) {
        lastSeqRef.current = nextLastSeq
      } else if (chunks.length) {
        const trailingSeq = Number(chunks[chunks.length - 1]?.seq)
        if (Number.isFinite(trailingSeq) && trailingSeq >= 0) {
          lastSeqRef.current = trailingSeq
        }
      }

      if (data?.reset && !chunks.length && !hasTranscriptRef.current && String(data?.prompt || "")) {
        writeToTerminal(promptValue(data?.prompt))
      }

      shouldContinue = Boolean(data?.active)
      if (!shouldContinue) {
        const recovered = !closedByUserRef.current && mountedRef.current
          ? await recoverTerminalSession({ scheduleImmediatePoll: false })
          : false
        if (recovered) {
          shouldContinue = true
          nextDelay = TERMINAL_ACTIVE_POLL_INTERVAL_MS
        } else {
          publishInactiveSession()
          const failureState = markTerminalFailure(new Error(String(data?.reason || "VI terminal session is inactive").trim() || "VI terminal session is inactive"), {
            pause: Boolean(data?.degraded),
            retryAfterMs: Number(data?.retryAfterMs || 0),
            reason: String(data?.reason || "").trim(),
            detail: "VI terminal reconnect slowed after errors.",
          })
          if (!failureState.paused && !closedByUserRef.current && mountedRef.current) {
            retryMode = "recover"
            nextDelay = failureState.retryAfterMs > 0
              ? failureState.retryAfterMs
              : computeJitteredDelayMs(TERMINAL_RETRY_BASE_MS)
          }
        }
      } else {
        markTerminalHealthy()
        nextDelay = nextTerminalPollDelay(data, chunks)
      }
    } catch (error) {
      if (!closedByUserRef.current && mountedRef.current) {
        setConnected(false)
        const failureState = markTerminalFailure(error, {
          detail: "VI terminal polling slowed after errors.",
        })
        if (!failureState.paused) {
          retryMode = "poll"
          nextDelay = computeJitteredDelayMs(failureState.retryAfterMs || TERMINAL_RETRY_BASE_MS)
        }
      }
    } finally {
      pollInFlightRef.current = false
      if (shouldContinue) {
        schedulePoll(nextDelay)
      } else if (retryMode === "recover") {
        scheduleSessionRecovery(nextDelay)
      } else if (retryMode === "poll") {
        schedulePoll(nextDelay)
      }
    }
  }

  const postTerminalAction = async (path, payload = {}) => {
    const res = await fetch(`${backend}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      throw new Error(data?.error || "VI terminal request failed")
    }
    syncSession(data)
    return data
  }

  const resizeTerminal = async (cols, rows) => {
    if (!connected) return
    const normalizedCols = Number(cols) || terminalRef.current?.cols || 120
    const normalizedRows = Number(rows) || terminalRef.current?.rows || 32
    if (normalizedCols < 1 || normalizedRows < 1) return
    try {
      await postTerminalAction("/platform/vi/terminal/resize", {
        cols: normalizedCols,
        rows: normalizedRows,
      })
    } catch {
      // Ignore resize sync failures; polling will resync the session shape.
    }
  }

  const connectSocket = async ({ reset = false } = {}) => {
    dismissCompletionPopup()
    closedByUserRef.current = false
    stopPolling()
    reconnectCircuitRef.current.reset()
    setConnectionHealth({
      degraded: false,
      paused: false,
      retryAfterMs: 0,
      reason: "",
      detail: "",
    })
    await openSession({ reset })
    terminalRef.current?.reset()
    setTranscript("")
    lastSeqRef.current = 0
    setConnected(true)
    fitTerminal()
    await pollTerminal()
  }

  const reconnectTerminal = async ({ reset = false } = {}) => {
    try {
      await connectSocket({ reset })
      markTerminalHealthy()
    } catch (error) {
      const failureState = markTerminalFailure(error, {
        detail: "VI terminal reconnect slowed after errors.",
      })
      if (!failureState.paused && documentVisible) {
        scheduleSessionRecovery(computeJitteredDelayMs(failureState.retryAfterMs || TERMINAL_RETRY_BASE_MS))
      }
      throw error
    }
  }

  const closeSocket = ({ skipReconnect = true } = {}) => {
    if (skipReconnect) {
      closedByUserRef.current = true
    }
    stopPolling()
  }

  const printPrompt = () => {
    writeToTerminal(promptValue(currentPromptRef.current))
  }

  const clearLocalInput = () => {
    dismissCompletionPopup()
    localInputBufferRef.current = ""
    localCursorIndexRef.current = 0
    utilityModeRef.current = false
    historyIndexRef.current = -1
    historyDraftRef.current = ""
  }

  const submitInput = async (source) => {
    if (!connected || connectionHealth.paused) {
      reconnectCircuitRef.current.reset()
      setConnectionHealth({
        degraded: false,
        paused: false,
        retryAfterMs: 0,
        reason: "",
        detail: "",
      })
      const recovered = await recoverTerminalSession({ scheduleImmediatePoll: false })
      if (!recovered) {
        toast.error("VI terminal is offline")
        return
      }
    }
    try {
      await postTerminalAction("/platform/vi/terminal/input", { data: source })
      schedulePoll(0)
    } catch (error) {
      const recovered = await recoverTerminalSession({ scheduleImmediatePoll: false })
      if (recovered) {
        markTerminalHealthy()
        schedulePoll(0)
        return
      }
      writeToTerminal(`\r\nError: ${error?.message || "Failed to send input to VI terminal"}\r\n`)
      publishInactiveSession()
      const failureState = markTerminalFailure(error, {
        detail: "VI terminal reconnect slowed after errors.",
      })
      if (!failureState.paused) {
        scheduleSessionRecovery(0)
      }
    }
  }

  const replaceInputWithHistory = (nextValue) => {
    dismissCompletionPopup()
    localInputBufferRef.current = nextValue
    localCursorIndexRef.current = String(nextValue || "").length
    rewriteLocalInput(nextValue)
  }

  const moveCursor = (delta) => {
    const currentValue = localInputBufferRef.current
    if (currentValue.includes("\n")) return
    const nextIndex = Math.max(0, Math.min(currentValue.length, localCursorIndexRef.current + delta))
    if (nextIndex === localCursorIndexRef.current) return
    dismissCompletionPopup()
    localCursorIndexRef.current = nextIndex
    rewriteLocalInput(currentValue)
  }

  const moveCursorToBoundary = (position) => {
    const currentValue = localInputBufferRef.current
    if (currentValue.includes("\n")) return
    const nextIndex = position === "start" ? 0 : currentValue.length
    if (nextIndex === localCursorIndexRef.current) return
    dismissCompletionPopup()
    localCursorIndexRef.current = nextIndex
    rewriteLocalInput(currentValue)
  }

  const handleHistory = (direction) => {
    const currentValue = localInputBufferRef.current
    if (currentValue.includes("\n")) return
    if (!historyRef.current.length) return
    if (direction < 0) {
      if (historyIndexRef.current < 0) {
        historyDraftRef.current = currentValue
      }
      const nextIndex = historyIndexRef.current < 0 ? historyRef.current.length - 1 : Math.max(0, historyIndexRef.current - 1)
      historyIndexRef.current = nextIndex
      replaceInputWithHistory(historyRef.current[nextIndex] || "")
      return
    }
    if (historyIndexRef.current < 0) return
    const nextIndex = historyIndexRef.current + 1
    if (nextIndex >= historyRef.current.length) {
      historyIndexRef.current = -1
      replaceInputWithHistory(historyDraftRef.current)
      return
    }
    historyIndexRef.current = nextIndex
    replaceInputWithHistory(historyRef.current[nextIndex] || "")
  }

  const backspaceInput = () => {
    const currentValue = localInputBufferRef.current
    const cursorIndex = Math.max(0, Math.min(localCursorIndexRef.current, currentValue.length))
    if (!currentValue || cursorIndex <= 0) return
    dismissCompletionPopup()
    localInputBufferRef.current = currentValue.slice(0, cursorIndex - 1) + currentValue.slice(cursorIndex)
    localCursorIndexRef.current = cursorIndex - 1
    rewriteLocalInput(localInputBufferRef.current)
  }

  const deleteInputForward = () => {
    const currentValue = localInputBufferRef.current
    const cursorIndex = Math.max(0, Math.min(localCursorIndexRef.current, currentValue.length))
    if (!currentValue || cursorIndex >= currentValue.length) return
    dismissCompletionPopup()
    localInputBufferRef.current = currentValue.slice(0, cursorIndex) + currentValue.slice(cursorIndex + 1)
    rewriteLocalInput(localInputBufferRef.current)
  }

  const deletePreviousWord = () => {
    const currentValue = localInputBufferRef.current
    let cursorIndex = Math.max(0, Math.min(localCursorIndexRef.current, currentValue.length))
    if (cursorIndex === 0) return
    const end = cursorIndex
    while (cursorIndex > 0 && /\s/.test(currentValue[cursorIndex - 1])) cursorIndex -= 1
    while (cursorIndex > 0 && !/\s/.test(currentValue[cursorIndex - 1])) cursorIndex -= 1
    localInputBufferRef.current = currentValue.slice(0, cursorIndex) + currentValue.slice(end)
    localCursorIndexRef.current = cursorIndex
    rewriteLocalInput(localInputBufferRef.current)
  }

  const killInputToEnd = () => {
    const currentValue = localInputBufferRef.current
    const cursorIndex = Math.max(0, Math.min(localCursorIndexRef.current, currentValue.length))
    if (cursorIndex >= currentValue.length) return
    localInputBufferRef.current = currentValue.slice(0, cursorIndex)
    rewriteLocalInput(localInputBufferRef.current)
  }

  const killInputToStart = () => {
    const currentValue = localInputBufferRef.current
    const cursorIndex = Math.max(0, Math.min(localCursorIndexRef.current, currentValue.length))
    if (cursorIndex === 0) return
    localInputBufferRef.current = currentValue.slice(cursorIndex)
    localCursorIndexRef.current = 0
    rewriteLocalInput(localInputBufferRef.current)
  }

  const appendInput = (text) => {
    if (!text) return
    dismissCompletionPopup()
    const currentValue = localInputBufferRef.current
    const cursorIndex = Math.max(0, Math.min(localCursorIndexRef.current, currentValue.length))
    localInputBufferRef.current = currentValue.slice(0, cursorIndex) + text + currentValue.slice(cursorIndex)
    localCursorIndexRef.current = cursorIndex + text.length
    rewriteLocalInput(localInputBufferRef.current)
  }

  const insertMultilineNewline = () => {
    dismissCompletionPopup()
    const currentValue = localInputBufferRef.current
    const cursorIndex = Math.max(0, Math.min(localCursorIndexRef.current, currentValue.length))
    localInputBufferRef.current = currentValue.slice(0, cursorIndex) + "\n" + currentValue.slice(cursorIndex)
    localCursorIndexRef.current = cursorIndex + 1
    rewriteLocalInput(localInputBufferRef.current)
  }

  const cancelInput = () => {
    if (!localInputBufferRef.current) {
      if (connected) {
        writeToTerminal("^C\r\n")
        void postTerminalAction("/platform/vi/terminal/signal", { signal: "SIGINT" })
          .then(() => {
            schedulePoll(0)
          })
          .catch((error) => {
            writeToTerminal(`\r\nError: ${error?.message || "Failed to interrupt VI terminal"}\r\n`)
            printPrompt()
          })
      }
      return
    }
    writeToTerminal("^C\r\n")
    clearLocalInput()
    printPrompt()
  }

  const recordSubmittedInput = (source) => {
    const prompt = promptValue(currentPromptRef.current)
    const continuationPrompt = prompt ? CONTINUATION_PROMPT : ""
    const rendered = String(source || "")
      .replace(/\r\n/g, "\n")
      .replace(/\n+$/g, "")
      .split("\n")
      .map((line, index) => `${index === 0 ? prompt : continuationPrompt}${line}`)
      .join("\n")
    if (rendered.trim()) {
      appendTranscript(`${rendered}\n`)
    }
  }

  const renderHelp = () => {
    writeToTerminal(
      [
        "\r\nVI Terminal utilities",
        ":help",
        ":clear",
        ":status",
        ":pwd",
        ":ls [path]",
        ":la [path]",
        ":ll [path]",
        ":tree [path]",
        ":files",
        ":dirs [path]",
        ":cat [relative-path]",
        ":open <relative-path>",
        ":run [relative-path]",
        ":source-dir",
        ":reset",
        ":exit",
        "",
        "You can also omit the leading colon for these utility commands.",
        "",
        "Tab completes file and folder paths for utility commands.",
        "",
      ].join("\r\n"),
    )
  }

  const fetchPortalFiles = async ({ force = false } = {}) => {
    const cache = filesCacheRef.current
    const now = Date.now()
    if (!force && cache.data && cache.expiresAt > now) {
      return cache.data
    }
    if (!force && cache.promise) {
      return cache.promise
    }
    const request = fetch(`${backend}/platform/vi/files`, { headers: authHeaders() })
      .then((res) =>
        res
          .json()
          .catch(() => ({}))
          .then((data) => ({ res, data })),
      )
      .then((data) => {
        if (!data?.res?.ok) {
          throw new Error(data?.data?.error || "Failed to load VI files")
        }
        const nextFiles = Array.isArray(data?.data?.files) ? data.data.files : []
        filesCacheRef.current = {
          data: nextFiles,
          promise: null,
          expiresAt: Date.now() + LISTING_CACHE_TTL_MS,
        }
        return nextFiles
      })
      .catch((error) => {
        filesCacheRef.current = { data: null, promise: null, expiresAt: 0 }
        throw error
      })
    filesCacheRef.current = { data: cache.data, promise: request, expiresAt: cache.expiresAt }
    return request
  }

  const fetchPortalDirectories = async (pathValue = "", { force = false } = {}) => {
    const cacheKey = String(pathValue || "")
    const cacheEntry = directoriesCacheRef.current.get(cacheKey)
    const now = Date.now()
    if (!force && cacheEntry?.data && cacheEntry.expiresAt > now) {
      return cacheEntry.data
    }
    if (!force && cacheEntry?.promise) {
      return cacheEntry.promise
    }
    const query = pathValue ? `?path=${encodeURIComponent(pathValue)}` : ""
    const request = fetch(`${backend}/platform/vi/directories${query}`, { headers: authHeaders() })
      .then((res) =>
        res
          .json()
          .catch(() => ({}))
          .then((data) => ({ res, data })),
      )
      .then((data) => {
        if (!data?.res?.ok) {
          throw new Error(data?.data?.error || "Failed to browse directories")
        }
        const nextData = data?.data || {}
        directoriesCacheRef.current.set(cacheKey, {
          data: nextData,
          promise: null,
          expiresAt: Date.now() + LISTING_CACHE_TTL_MS,
        })
        return nextData
      })
      .catch((error) => {
        directoriesCacheRef.current.delete(cacheKey)
        throw error
      })
    directoriesCacheRef.current.set(cacheKey, {
      data: cacheEntry?.data || null,
      promise: request,
      expiresAt: cacheEntry?.expiresAt || 0,
    })
    return request
  }

  const normalizeFileLookup = (value) => String(value || "").trim().replace(/\\/g, "/").replace(/^\.\//, "")

  const terminalSourceDir = () => String(sourceDir || sessionInfo.cwd || "").trim().replace(/\\/g, "/").replace(/\/+$/, "")

  const resolveListingTarget = (pathValue = "") => {
    const root = terminalSourceDir()
    const raw = String(pathValue || "").trim().replace(/\\/g, "/")
    if (!raw || raw === ".") {
      return {
        absolutePath: root,
        displayPath: root || ".",
        relativePath: "",
      }
    }

    if (raw.startsWith("/")) {
      const absolutePath = raw.replace(/\/+$/, "")
      if (root && absolutePath !== root && !absolutePath.startsWith(`${root}/`)) {
        throw new Error("Path must stay within the VI source directory")
      }
      return {
        absolutePath,
        displayPath: absolutePath,
        relativePath: root && absolutePath.startsWith(root)
          ? normalizePortalPath(absolutePath.slice(root.length))
          : "",
      }
    }

    if (!root) {
      throw new Error("VI source directory is not available")
    }

    const relativePath = normalizePortalPath(raw)
    return {
      absolutePath: relativePath ? `${root}/${relativePath}` : root,
      displayPath: relativePath ? `${root}/${relativePath}` : root,
      relativePath,
    }
  }

  const resolveFilePath = async (pathValue, { preferActive = false } = {}) => {
    const normalized = normalizeFileLookup(pathValue)
    const activePath = normalizeFileLookup(activeFilePath)
    if (!normalized) {
      if (preferActive && activePath) return activePath
      throw new Error("A VI file path is required")
    }

    const baseName = normalized.split("/").pop()
    if (activePath && (activePath === normalized || activePath.endsWith(`/${normalized}`) || activePath.split("/").pop() === baseName)) {
      return activePath
    }

    const files = await fetchPortalFiles()
    const exactMatch = files.find((file) => normalizeFileLookup(file?.path) === normalized)
    if (exactMatch?.path) return exactMatch.path

    const suffixMatches = files.filter((file) => normalizeFileLookup(file?.path).endsWith(`/${normalized}`))
    if (suffixMatches.length === 1) return suffixMatches[0].path
    if (suffixMatches.length > 1) {
      throw new Error(`Multiple VI files match "${normalized}"`)
    }

    const nameMatches = files.filter((file) => normalizeFileLookup(file?.path).split("/").pop() === baseName)
    if (nameMatches.length === 1) return nameMatches[0].path
    if (nameMatches.length > 1) {
      throw new Error(`Multiple VI files match "${normalized}"`)
    }

    throw new Error(`VI file not found: ${normalized}`)
  }

  const ensureConnected = async () => {
    if (connected) return
    await reconnectTerminal()
  }

  const listFiles = async () => {
    const files = await fetchPortalFiles()
    if (!files.length) {
      writeToTerminal("\r\nNo VI files in the current source directory.\r\n")
      return
    }
    writeToTerminal(`\r\nFiles in ${sourceDir || "source directory"}\r\n`)
    files.forEach((file) => {
      writeToTerminal(`- ${file?.path || file?.name || "unknown"}\r\n`)
    })
  }

  const loadImmediateEntries = async (
    pathValue = "",
    { includeFiles = true, includeDirectories = true, includeHidden = true, force = false } = {},
  ) => {
    const target = resolveListingTarget(pathValue)
    const [directoryData, files] = await Promise.all([
      fetchPortalDirectories(target.absolutePath, { force }),
      includeFiles ? fetchPortalFiles({ force }) : Promise.resolve([]),
    ])

    const directories = includeDirectories
      ? (Array.isArray(directoryData?.directories) ? directoryData.directories : []).map((directory) => ({
          type: "dir",
          name: String(directory?.name || "").trim(),
          displayName: `${String(directory?.name || "").trim()}/`,
          size: null,
          modifiedAt: null,
        }))
      : []

    const immediateFiles = includeFiles
      ? files
          .filter((file) => {
            const filePath = normalizeFileLookup(file?.path)
            if (!filePath) return false
            const lastSlash = filePath.lastIndexOf("/")
            const parentPath = lastSlash >= 0 ? filePath.slice(0, lastSlash) : ""
            return parentPath === target.relativePath
          })
          .map((file) => ({
            type: "file",
            name: String(file?.name || "").trim() || normalizeFileLookup(file?.path).split("/").pop() || "unknown",
            displayName: String(file?.name || "").trim() || normalizeFileLookup(file?.path).split("/").pop() || "unknown",
            size: file?.size,
            modifiedAt: file?.modifiedAt,
          }))
      : []

    const entries = [...directories, ...immediateFiles]
      .filter((entry) => entry.name)
      .filter((entry) => includeHidden || !entry.name.startsWith("."))
      .sort((left, right) => {
        if (left.type !== right.type) return left.type === "dir" ? -1 : 1
        return left.name.localeCompare(right.name)
      })

    return { target, directoryData, entries }
  }

  const listDirectories = async (pathValue = "") => {
    const target = resolveListingTarget(pathValue)
    const data = await fetchPortalDirectories(target.absolutePath)
    const directories = Array.isArray(data?.directories) ? data.directories : []
    const currentPath = String(data?.path || target.displayPath || sourceDir || "")
    writeToTerminal(`\r\nDirectories under ${currentPath || "."}\r\n`)
    if (!directories.length) {
      writeToTerminal("(none)\r\n")
      return
    }
    directories.forEach((directory) => {
      writeToTerminal(`- ${directory?.path || directory?.name || "unknown"}\r\n`)
    })
  }

  const listSourceEntries = async (pathValue = "", { includeHidden = false, longFormat = false } = {}) => {
    const { target, directoryData, entries } = await loadImmediateEntries(pathValue, {
      includeFiles: true,
      includeDirectories: true,
      includeHidden,
    })
    writeToTerminal(`\r\nListing ${directoryData?.path || target.displayPath || "."}\r\n`)
    if (!entries.length) {
      writeToTerminal("(empty)\r\n")
      return
    }

    entries.forEach((entry) => {
      if (!longFormat) {
        writeToTerminal(`${entry.displayName}\r\n`)
        return
      }
      const typeLabel = entry.type === "dir" ? "dir " : "file"
      const sizeLabel = String(formatListSize(entry.size)).padStart(8)
      const modifiedLabel = formatListTimestamp(entry.modifiedAt).padEnd(16)
      writeToTerminal(`${typeLabel} ${sizeLabel} ${modifiedLabel} ${entry.displayName}\r\n`)
    })
  }

  const renderTree = async (pathValue = "", { includeHidden = false } = {}) => {
    const rootState = await loadImmediateEntries(pathValue, {
      includeFiles: true,
      includeDirectories: true,
      includeHidden,
    })
    const rootLabel = rootState.directoryData?.path || rootState.target.displayPath || "."
    writeToTerminal(`\r\n${rootLabel}\r\n`)

    if (!rootState.entries.length) {
      writeToTerminal("(empty)\r\n")
      return
    }

    const walkTree = async (relativePath, prefix = "") => {
      const { entries } = await loadImmediateEntries(relativePath, {
        includeFiles: true,
        includeDirectories: true,
        includeHidden,
      })

      for (let index = 0; index < entries.length; index += 1) {
        const entry = entries[index]
        const isLast = index === entries.length - 1
        const connector = isLast ? "`-- " : "|-- "
        writeToTerminal(`${prefix}${connector}${entry.displayName}\r\n`)
        if (entry.type !== "dir") continue
        const nextRelativePath = relativePath ? `${relativePath}/${entry.name}` : entry.name
        const nextPrefix = `${prefix}${isLast ? "    " : "|   "}`
        await walkTree(nextRelativePath, nextPrefix)
      }
    }

    await walkTree(rootState.target.relativePath)
  }

  const parsePathCompletionContext = (buffer) => {
    const rawBuffer = String(buffer || "")
    const match = /^(?::)?(\S+)(\s+)(.*)$/.exec(rawBuffer)
    if (!match) return null
    const normalizedCommand = `:${String(match[1] || "").replace(/^:/, "").toLowerCase()}`
    if (!PATH_COMPLETION_COMMANDS.has(normalizedCommand)) return null

    const spacing = match[2]
    const rawArg = String(match[3] || "").replace(/\\/g, "/")
    if (/\s/.test(rawArg)) return null

    const hasTrailingSlash = rawArg.endsWith("/")
    const lastSlashIndex = hasTrailingSlash ? rawArg.length - 1 : rawArg.lastIndexOf("/")
    const directoryPart = lastSlashIndex >= 0 ? rawArg.slice(0, lastSlashIndex) : ""
    const fragment = hasTrailingSlash ? "" : rawArg.slice(lastSlashIndex + 1)
    return {
      command: normalizedCommand,
      renderCommand: rawBuffer.startsWith(":") ? normalizedCommand : normalizedCommand.slice(1),
      spacing,
      rawArg,
      directoryPart,
      fragment,
      basePath: directoryPart ? `${directoryPart.replace(/\/+$/, "")}/` : "",
      includeFiles: FILE_PATH_COMPLETION_COMMANDS.has(normalizedCommand),
      includeDirectories: true,
    }
  }

  const applyCompletionValue = (context, entry) => {
    const completedPath = `${context.basePath}${entry.name}${entry.type === "dir" ? "/" : ""}${entry.type === "file" ? " " : ""}`
    const nextBuffer = `${context.renderCommand}${context.spacing}${completedPath}`
    dismissCompletionPopup()
    localInputBufferRef.current = nextBuffer
    localCursorIndexRef.current = nextBuffer.length
    rewriteLocalInput(nextBuffer)
  }

  const showCompletionPopup = (context, directoryPath, entries) => {
    setCompletionState({
      command: context.renderCommand,
      path: directoryPath || ".",
      items: entries.slice(0, 12).map((entry) => ({
        label: entry.displayName,
        type: entry.type,
      })),
      extraCount: Math.max(0, entries.length - 12),
    })
  }

  const triggerPathCompletion = async () => {
    const bufferSnapshot = localInputBufferRef.current
    const context = parsePathCompletionContext(bufferSnapshot)
    if (!context) return false

    const requestVersion = completionVersionRef.current + 1
    completionVersionRef.current = requestVersion
    setCompletionState(null)

    try {
      const completionOptions = {
        includeFiles: context.includeFiles,
        includeDirectories: context.includeDirectories,
        includeHidden: context.fragment.startsWith("."),
      }
      let { directoryData, entries } = await loadImmediateEntries(context.directoryPart, completionOptions)

      if (completionVersionRef.current !== requestVersion || localInputBufferRef.current !== bufferSnapshot) {
        return true
      }

      let matches = entries.filter((entry) => entry.name.startsWith(context.fragment))
      if (!matches.length) {
        ;({ directoryData, entries } = await loadImmediateEntries(context.directoryPart, {
          ...completionOptions,
          force: true,
        }))
        if (completionVersionRef.current !== requestVersion || localInputBufferRef.current !== bufferSnapshot) {
          return true
        }
        matches = entries.filter((entry) => entry.name.startsWith(context.fragment))
      }
      if (!matches.length) {
        return true
      }

      if (matches.length === 1) {
        applyCompletionValue(context, matches[0])
        return true
      }

      const candidateNames = matches.map((entry) => `${entry.name}${entry.type === "dir" ? "/" : ""}`)
      const sharedPrefix = longestCommonPrefix(candidateNames)
      if (sharedPrefix && sharedPrefix.length > context.fragment.length) {
        const nextBuffer = `${context.renderCommand}${context.spacing}${context.basePath}${sharedPrefix}`
        dismissCompletionPopup()
        localInputBufferRef.current = nextBuffer
        localCursorIndexRef.current = nextBuffer.length
        rewriteLocalInput(nextBuffer)
      }

      showCompletionPopup(context, directoryData?.path, matches)
      return true
    } catch {
      return true
    }
  }

  const runFile = async (pathValue) => {
    const resolvedPath = await resolveFilePath(pathValue, { preferActive: true })
    await ensureConnected()
    writeEvent("run file", resolvedPath)
    const data = await postTerminalAction("/platform/vi/terminal/run", { path: resolvedPath })
    schedulePoll(0)
    ensureTerminalInView()
    return data
  }

  const runSource = async ({ path, source }) => {
    const logicalPath = normalizeFileLookup(path) || normalizeFileLookup(activeFilePath) || "scratch/unsaved.versa"
    await ensureConnected()
    writeEvent("run", logicalPath)
    const data = await postTerminalAction("/platform/vi/terminal/run", {
      path: logicalPath,
      source: String(source ?? ""),
    })
    schedulePoll(0)
    ensureTerminalInView()
    return data
  }

  const showFileContents = async (pathValue) => {
    const resolvedPath = await resolveFilePath(pathValue, { preferActive: true })
    const res = await fetch(`${backend}/platform/vi/files/${encodeURIComponent(resolvedPath)}`, { headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      throw new Error(data?.error || "Failed to read VI file")
    }
    writeToTerminal(`\r\n# ${resolvedPath}\r\n${String(data?.content || "")}\r\n`)
  }

  const showStatus = async () => {
    const res = await fetch(`${backend}/platform/vi/terminal/session`, { headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      throw new Error(data?.error || "Failed to load VI terminal status")
    }
    const promptLabel = data?.prompt === "" ? "(raw input)" : promptValue(data?.prompt)
    writeToTerminal(
      [
        "",
        `Session: ${data?.sessionKey || "-"}`,
        `Active: ${data?.active ? "yes" : "no"}`,
        `Mode: ${data?.mode || "repl"}`,
        `Prompt: ${promptLabel}`,
        `Size: ${data?.cols || 120}x${data?.rows || 32}`,
        `Cwd: ${data?.cwd || sourceDir || "-"}`,
        `Source dir: ${data?.sourceDir || sourceDir || "-"}`,
        "",
      ].join("\r\n"),
    )
  }

  const executeUtility = async (rawCommand) => {
    const trimmed = String(rawCommand || "").trim()
    const [command, ...rest] = trimmed.split(/\s+/)
    const joinedArg = rest.join(" ").trim()

    try {
      switch (command) {
        case ":help":
          renderHelp()
          printPrompt()
          return
        case ":clear":
          clearTerminalViewport({ preservePrompt: true })
          return
        case ":status":
          await showStatus()
          printPrompt()
          return
        case ":pwd":
          writeToTerminal(`\r\n${sessionInfo.cwd || sourceDir || "-"}\r\n`)
          printPrompt()
          return
        case ":ls":
          await listSourceEntries(joinedArg)
          printPrompt()
          return
        case ":la":
          await listSourceEntries(joinedArg, { includeHidden: true })
          printPrompt()
          return
        case ":ll":
          await listSourceEntries(joinedArg, { includeHidden: true, longFormat: true })
          printPrompt()
          return
        case ":tree":
          await renderTree(joinedArg)
          printPrompt()
          return
        case ":files":
          await listFiles()
          printPrompt()
          return
        case ":dirs":
          await listDirectories(joinedArg)
          printPrompt()
          return
        case ":cat":
          await showFileContents(joinedArg)
          printPrompt()
          return
        case ":open":
          if (!joinedArg) throw new Error("Usage: :open <relative-path>")
          {
            const resolvedPath = await resolveFilePath(joinedArg)
            await onOpenFile?.(resolvedPath)
            writeEvent("opened in editor", resolvedPath)
          }
          printPrompt()
          return
        case ":run":
          await runFile(joinedArg)
          return
        case ":source-dir":
          writeToTerminal(`\r\n${sourceDir || "-"}\r\n`)
          printPrompt()
          return
        case ":reset":
          writeEvent("terminal reset", sessionInfo.sessionKey || "current session")
          await reconnectTerminal({ reset: true })
          return
        case ":exit":
          closedByUserRef.current = true
          await fetch(`${backend}/platform/vi/terminal/session`, {
            method: "DELETE",
            headers: authHeaders(),
          })
          closeSocket()
          setConnected(false)
          publishInactiveSession()
          writeToTerminal("\r\n[VI terminal closed]\r\n")
          return
        default:
          writeToTerminal(`\r\nUnrecognized utility command: ${trimmed || command}\r\nType :help to view the supported terminal commands.\r\n`)
          printPrompt()
      }
    } catch (error) {
      writeToTerminal(`\r\nError: ${error?.message || "Utility command failed"}\r\n`)
      printPrompt()
    }
  }

  useEffect(() => {
    invalidateListingCaches()
  }, [sourceDir])

  useEffect(() => {
    if (!mountedRef.current) return
    if (!documentVisible) {
      stopPolling()
      return
    }
    if (closedByUserRef.current) return
    const shouldResume = Boolean(connected || active || sessionInfo.sessionKey)
    if (!shouldResume) return
    if (connectionHealth.paused) {
      reconnectCircuitRef.current.reset()
      setConnectionHealth({
        degraded: false,
        paused: false,
        retryAfterMs: 0,
        reason: "",
        detail: "",
      })
    }
    if (active) {
      schedulePoll(0)
    } else {
      scheduleSessionRecovery(0)
    }
  // Scheduling callbacks are stable refs managed by the terminal controller.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, connected, connectionHealth.paused, documentVisible, sessionInfo.sessionKey])

  useImperativeHandle(ref, () => ({
    writeEvent,
    writeText(text) {
      writeToTerminal(text)
    },
    async runFile(path) {
      return runFile(path)
    },
    async runSource(options) {
      return runSource(options || {})
    },
    focus() {
      ensureTerminalInView()
      terminalRef.current?.focus()
    },
    clear() {
      clearTerminalViewport({ preservePrompt: true })
    },
    invalidateListings() {
      invalidateListingCaches()
    },
  }))

  useEffect(() => {
    mountedRef.current = true
    const terminal = new Terminal({
      cursorBlink: true,
      convertEol: true,
      fontFamily: '"JetBrains Mono", "Fira Code", monospace',
      fontSize: 13,
      letterSpacing: 0.2,
      lineHeight: 1.35,
      scrollback: 5000,
      theme: {
        background: "#020617",
        foreground: "#d1fae5",
        cursor: "#34d399",
        selectionBackground: "rgba(52, 211, 153, 0.3)",
        black: "#020617",
        red: "#fb7185",
        green: "#34d399",
        yellow: "#fbbf24",
        blue: "#38bdf8",
        magenta: "#f472b6",
        cyan: "#22d3ee",
        white: "#e2e8f0",
        brightBlack: "#334155",
        brightRed: "#fda4af",
        brightGreen: "#6ee7b7",
        brightYellow: "#fcd34d",
        brightBlue: "#7dd3fc",
        brightMagenta: "#f9a8d4",
        brightCyan: "#67e8f9",
        brightWhite: "#f8fafc",
      },
    })
    const fitAddon = new FitAddon()
    terminal.loadAddon(fitAddon)
    terminal.open(containerRef.current)
    terminalRef.current = terminal
    fitAddonRef.current = fitAddon
    fitTerminal()

    const dataDisposable = terminal.onData((data) => {
      if (data === "\u000c") {
        clearTerminalViewport({ preservePrompt: true })
        return
      }
      if (data === "\u0003") {
        cancelInput()
        return
      }
      if (data === "\u0001") { // Ctrl-A
        moveCursorToBoundary("start")
        return
      }
      if (data === "\u0005") { // Ctrl-E
        moveCursorToBoundary("end")
        return
      }
      if (data === "\u000b") { // Ctrl-K
        killInputToEnd()
        return
      }
      if (data === "\u0015") { // Ctrl-U
        killInputToStart()
        return
      }
      if (data === "\u0017") { // Ctrl-W
        deletePreviousWord()
        return
      }
      if (data === "\u0010") { // Ctrl-P
        handleHistory(-1)
        return
      }
      if (data === "\u000e") { // Ctrl-N
        handleHistory(1)
        return
      }
      if (data === "\u0004") { // Ctrl-D: delete forward, like readline
        deleteInputForward()
        return
      }
      if (data === "\u001b[D" || data === "\u001bOD") {
        moveCursor(-1)
        return
      }
      if (data === "\u001b[C" || data === "\u001bOC") {
        moveCursor(1)
        return
      }
      if (data === "\u001b[H" || data === "\u001bOH") {
        moveCursorToBoundary("start")
        return
      }
      if (data === "\u001b[F" || data === "\u001bOF") {
        moveCursorToBoundary("end")
        return
      }
      if (data === "\u001b[3~") {
        deleteInputForward()
        return
      }
      if (data === "\u007f") {
        backspaceInput()
        return
      }
      if (data === "\u001b[A" || data === "\u001bOA") {
        handleHistory(-1)
        return
      }
      if (data === "\u001b[B" || data === "\u001bOB") {
        handleHistory(1)
        return
      }
      if (data === "\t") {
        if (parsePathCompletionContext(localInputBufferRef.current)) {
          triggerPathCompletion()
          return
        }
        appendInput("\t")
        return
      }
      if (data === "\r") {
        const source = localInputBufferRef.current
        const utilityCommand = currentPromptRef.current === PRIMARY_PROMPT ? normalizeUtilityCommandInput(source) : ""
        const wasUtility = utilityModeRef.current || Boolean(utilityCommand)
        if (source.trim()) {
          recordSubmittedInput(source)
        }
        writeToTerminal("\r\n", { record: false })
        clearLocalInput()
        if (wasUtility) {
          executeUtility(utilityCommand || source)
          return
        }
        if (!source.trim()) {
          void submitInput("")
          return
        }
        if (historyRef.current[historyRef.current.length - 1] !== source) {
          historyRef.current = [...historyRef.current, source]
        }
        void submitInput(source)
        return
      }
      if (data === ":" && !localInputBufferRef.current && currentPromptRef.current === PRIMARY_PROMPT) {
        utilityModeRef.current = true
        appendInput(":")
        return
      }
      appendInput(data)
    })

    terminal.attachCustomKeyEventHandler((event) => {
      if (event.type === "keydown" && event.key === "Enter" && (event.ctrlKey || event.metaKey || event.shiftKey)) {
        event.preventDefault()
        insertMultilineNewline()
        return false
      }
      if (event.type === "keydown" && event.key === "ArrowUp") {
        event.preventDefault()
        handleHistory(-1)
        return false
      }
      if (event.type === "keydown" && event.key === "ArrowLeft") {
        event.preventDefault()
        moveCursor(-1)
        return false
      }
      if (event.type === "keydown" && event.key === "ArrowRight") {
        event.preventDefault()
        moveCursor(1)
        return false
      }
      if (event.type === "keydown" && event.key === "ArrowDown") {
        event.preventDefault()
        handleHistory(1)
        return false
      }
      if (event.type === "keydown" && event.key === "Home") {
        event.preventDefault()
        moveCursorToBoundary("start")
        return false
      }
      if (event.type === "keydown" && event.key === "End") {
        event.preventDefault()
        moveCursorToBoundary("end")
        return false
      }
      if (event.type === "keydown" && event.key === "Delete") {
        event.preventDefault()
        deleteInputForward()
        return false
      }
      if (event.type === "keydown" && event.ctrlKey && event.key.toLowerCase() === "c") {
        if (terminalRef.current?.hasSelection?.()) {
          return true
        }
        event.preventDefault()
        cancelInput()
        return false
      }
      if (event.type === "keydown" && event.key === "Tab") {
        if (parsePathCompletionContext(localInputBufferRef.current)) {
          event.preventDefault()
          triggerPathCompletion()
          return false
        }
        return true
      }
      if (event.type === "keydown" && event.ctrlKey && event.key.toLowerCase() === "l") {
        event.preventDefault()
        clearTerminalViewport({ preservePrompt: true })
        return false
      }
      return true
    })

    const terminalContainer = containerRef.current
    const handleTerminalFocus = () => {
      ensureTerminalInView()
    }
    const handleTerminalPointerDown = () => {
      ensureTerminalInView()
      terminal.focus()
    }
    terminalContainer?.addEventListener("focusin", handleTerminalFocus)
    terminalContainer?.addEventListener("mousedown", handleTerminalPointerDown)

    resizeObserverRef.current = new ResizeObserver(() => {
      fitTerminal()
    })
    resizeObserverRef.current.observe(containerRef.current)

    if (autoConnect) {
      reconnectTerminal().catch((error) => {
        writeToTerminal(`Error: ${error?.message || "Failed to connect VI terminal"}\r\n`)
        toast.error(error?.message || "Failed to connect VI terminal")
      })
    } else {
      publishInactiveSession()
    }

    return () => {
      mountedRef.current = false
      clearTimeout(reconnectTimerRef.current)
      if (transcriptFlushTimerRef.current) {
        clearTimeout(transcriptFlushTimerRef.current)
        transcriptFlushTimerRef.current = null
      }
      resizeObserverRef.current?.disconnect()
      terminalContainer?.removeEventListener("focusin", handleTerminalFocus)
      terminalContainer?.removeEventListener("mousedown", handleTerminalPointerDown)
      dataDisposable.dispose()
      closeSocket()
      terminal.dispose()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoConnect])

  return (
    <Card ref={cardRef} className="overflow-hidden rounded-[1.5rem] border border-slate-900/90 bg-slate-950 text-slate-100 shadow-[0_24px_60px_rgba(2,6,23,0.34)]">
      <CardHeader className="border-b border-slate-800/90 bg-slate-950/[0.98] py-4">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-xl text-slate-50">Versa Terminal</CardTitle>
          <div className="flex items-center gap-2">
            <div className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${
              connectionHealth.paused
                ? "border border-amber-400/20 bg-amber-400/10 text-amber-100"
                : active
                  ? "border border-emerald-400/20 bg-emerald-400/10 text-emerald-200"
                  : "border border-white/10 bg-white/5 text-slate-300"
            }`}>
              {connectionHealth.paused ? "Reconnect Paused" : active ? "Terminal Live" : "Terminal Idle"}
            </div>
            <Button type="button" variant="outline" size="sm" className="h-8 border-slate-700 bg-slate-900/95 text-slate-100 hover:bg-slate-800 hover:text-white" onClick={() => reconnectTerminal().catch((error) => toast.error(error?.message || "Failed to reconnect VI terminal"))}>
              {active ? "Refresh" : "Reconnect"}
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-0">
        {connectionHealth.degraded ? (
          <div className="border-b border-amber-400/20 bg-amber-400/10 px-5 py-3 text-sm text-amber-100">
            <p className="font-semibold">
              {connectionHealth.paused ? "Automatic terminal reconnect paused" : "Automatic terminal reconnect slowed"}
            </p>
            <p className="mt-1 text-xs text-amber-50/80">
              {connectionHealth.detail || connectionHealth.reason || "VI terminal polling slowed after repeated failures."}
            </p>
          </div>
        ) : null}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-slate-800/90 bg-slate-950/95 px-5 py-3 text-xs text-slate-400">
          <span>Mode: {sessionInfo.mode || "repl"}</span>
          <span>Prompt: {sessionInfo.prompt === "" ? "(raw input)" : promptValue(sessionInfo.prompt)}</span>
          <span>Size: {sessionInfo.cols}x{sessionInfo.rows}</span>
          <span>Source: {sourceDir || "-"}</span>
        </div>
        <div className="bg-slate-950/90 p-4">
          <div className="relative">
            <div className="absolute right-3 top-3 z-10 flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="icon"
                aria-label="Clear VI terminal viewport"
                title="Clear VI terminal viewport"
                onClick={() => clearTerminalViewport({ preservePrompt: true })}
                disabled={!hasTranscript}
                className="h-8 w-8 rounded-lg border-slate-700 bg-slate-900/95 text-slate-100 shadow-sm backdrop-blur hover:bg-slate-800 hover:text-white"
              >
                <Eraser className="h-3.5 w-3.5" />
              </Button>
              <CopyIconButton
                getText={currentTranscriptText}
                label="Copy VI terminal transcript"
                successMessage="VI terminal transcript copied"
                errorMessage="Failed to copy VI terminal transcript"
                disabled={!hasTranscript}
                className="border-slate-700 bg-slate-900/95 text-slate-100 backdrop-blur hover:bg-slate-800 hover:text-white"
              />
            </div>
            <div ref={containerRef} className="h-[44rem] w-full overflow-hidden rounded-[1.2rem] border border-slate-800/80 bg-slate-950 px-3 py-2" />
            {completionState ? (
              <div className="pointer-events-none absolute inset-x-4 bottom-4 z-10">
                <div className="rounded-2xl border border-emerald-400/20 bg-slate-900/95 px-4 py-3 shadow-[0_18px_40px_rgba(2,6,23,0.5)] backdrop-blur">
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-200/90">
                    {completionState.command} matches in {completionState.path}
                  </div>
                  <div className="flex flex-wrap gap-2 font-mono text-xs text-slate-100">
                    {completionState.items.map((item) => (
                      <span
                        key={`${item.type}:${item.label}`}
                        className={`rounded-full border px-2 py-1 ${
                          item.type === "dir"
                            ? "border-sky-400/25 bg-sky-400/10 text-sky-100"
                            : "border-slate-700 bg-slate-800/90 text-slate-100"
                        }`}
                      >
                        {item.label}
                      </span>
                    ))}
                  </div>
                  <div className="mt-2 text-[11px] text-slate-400">
                    {completionState.extraCount > 0 ? `+${completionState.extraCount} more. ` : ""}
                    Type more, then press Tab again.
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </CardContent>
    </Card>
  )
})
