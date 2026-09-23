"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useDocumentVisible } from "@/hooks/use-document-visible"
import { computeJitteredDelayMs, createFailureCircuit } from "@/lib/request-circuit"
import { normalizeVdbNamedPipePath, normalizeVdbTransportMode } from "@/lib/vdb-transport"

const PROBE_RESPONSE_CACHE_TTL_MS = 2000
const probeInflightRequests = new Map()
const probeResponseCache = new Map()

const DEFAULT_STATE = {
  transport: "unixsocket",
  available: false,
  status: "checking",
  target: "",
  detail: "Checking VDB transport availability",
  loading: true,
  localTarget: false,
  autostartAttempted: false,
  autostartDeferred: false,
  degraded: false,
  paused: false,
  retryAfterMs: 0,
  reason: "",
}

async function fetchProbePayload(requestUrl) {
  const normalizedUrl = String(requestUrl || "").trim()
  if (!normalizedUrl) {
    throw new Error("A VDB probe request URL is required")
  }
  const now = Date.now()
  const cached = probeResponseCache.get(normalizedUrl)
  if (cached && now - cached.at < PROBE_RESPONSE_CACHE_TTL_MS) {
    return cached.payload
  }
  if (probeInflightRequests.has(normalizedUrl)) {
    return probeInflightRequests.get(normalizedUrl)
  }

  const promise = fetch(normalizedUrl, { cache: "no-store" })
    .then(async (response) => {
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        const error = new Error(payload?.error || "Failed to probe VDB connection")
        error.status = response.status
        throw error
      }
      probeResponseCache.set(normalizedUrl, { at: Date.now(), payload })
      return payload
    })
    .finally(() => {
      probeInflightRequests.delete(normalizedUrl)
    })

  probeInflightRequests.set(normalizedUrl, promise)
  return promise
}

export function useVdbConnectionStatus({
  backend,
  transport,
  serverUrl,
  socketPath,
  namedPipePath,
  supportsNamedPipe = false,
  enabled = true,
  pollIntervalMs = 10000,
  attemptAutostart = false,
}) {
  const [state, setState] = useState(DEFAULT_STATE)
  const [retryTick, setRetryTick] = useState(0)
  const lastAutostartRef = useRef({ key: "", at: 0 })
  const lastTargetRef = useRef("")
  const circuitRef = useRef(createFailureCircuit())
  const documentVisible = useDocumentVisible()

  const retry = useCallback(() => {
    lastAutostartRef.current = { key: "", at: 0 }
    circuitRef.current.reset()
    setRetryTick((current) => current + 1)
  }, [])

  useEffect(() => {
    const nextTransport = normalizeVdbTransportMode(transport, supportsNamedPipe)
    const targetValue = nextTransport === "http"
      ? String(serverUrl || "")
      : nextTransport === "namedpipe"
        ? normalizeVdbNamedPipePath(namedPipePath || "")
        : String(socketPath || "")
    const targetKey = `${nextTransport}|${targetValue}`

    if (!enabled || !backend) {
      setState((prev) => ({
        ...prev,
        transport: nextTransport,
        loading: false,
        status: "idle",
        detail: "",
        localTarget: false,
        autostartAttempted: false,
        autostartDeferred: false,
        degraded: false,
        paused: false,
        retryAfterMs: 0,
        reason: "",
      }))
      return undefined
    }

    if (!documentVisible) {
      return undefined
    }

    let cancelled = false
    let timerId = 0
    const shouldTryLocalAutostart = Boolean(attemptAutostart && nextTransport === "http")
    const circuit = circuitRef.current

    if (lastTargetRef.current !== targetKey) {
      lastTargetRef.current = targetKey
      circuit.reset()
      setState({
        transport: nextTransport,
        available: false,
        status: "checking",
        target: targetValue,
        detail: "Checking VDB transport availability",
        loading: true,
        localTarget: nextTransport !== "http",
        autostartAttempted: false,
        autostartDeferred: false,
        degraded: false,
        paused: false,
        retryAfterMs: 0,
        reason: "",
      })
    }

    const runProbe = async () => {
      let nextDelayMs = pollIntervalMs
      try {
        const fetchStatus = async (attemptAutostart = false) => {
          const url = new URL(`${backend}/auth/vdb-connection-status`)
          url.searchParams.set("vdb_transport", nextTransport)
          if (serverUrl) {
            url.searchParams.set("vdb_server_url", serverUrl)
          }
          if (socketPath) {
            url.searchParams.set("vdb_unix_socket_path", socketPath)
          }
          if (namedPipePath) {
            url.searchParams.set("vdb_named_pipe_path", normalizeVdbNamedPipePath(namedPipePath))
          }
          if (attemptAutostart) {
            url.searchParams.set("attempt_autostart", "1")
          }
          return fetchProbePayload(url.toString())
        }

        const applyPayload = (payload) => {
          const normalizedReason = String(payload?.reason || payload?.detail || "").trim()
          setState({
            transport: String(payload?.transport || nextTransport),
            available: Boolean(payload?.available),
            status: payload?.status || (payload?.available ? "available" : "unavailable"),
            target: String(payload?.target || ""),
            detail: String(payload?.detail || ""),
            loading: false,
            localTarget: Boolean(payload?.localTarget),
            autostartAttempted: Boolean(payload?.autostartAttempted),
            autostartDeferred: Boolean(payload?.autostartDeferred),
            degraded: Boolean(payload?.degraded),
            paused: Boolean(payload?.status === "paused" || (payload?.degraded && Number(payload?.retryAfterMs || 0) > 0)),
            retryAfterMs: Math.max(0, Number(payload?.retryAfterMs || 0)),
            reason: normalizedReason,
          })
        }

        const payload = await fetchStatus(false)
        if (cancelled) return

        const autostartKey = `${nextTransport}|${serverUrl || ""}|${socketPath || ""}|${namedPipePath || ""}`
        const canAttemptAutostart = Boolean(
          shouldTryLocalAutostart &&
          !payload?.available &&
          payload?.localTarget
        )

        if (canAttemptAutostart) {
          const now = Date.now()
          const recentlyAttempted = (
            lastAutostartRef.current.key === autostartKey &&
            now - lastAutostartRef.current.at < 15000
          )
          if (!recentlyAttempted) {
            lastAutostartRef.current = { key: autostartKey, at: now }
            setState({
              transport: nextTransport,
              available: false,
              status: "starting",
              target: String(payload?.target || targetValue || ""),
              detail: "Starting HTTP server...",
              loading: true,
              localTarget: Boolean(payload?.localTarget),
              autostartAttempted: true,
            })
            const startedPayload = await fetchStatus(true)
            if (cancelled) return
            applyPayload(startedPayload)
            if (startedPayload?.degraded || startedPayload?.autostartDeferred || startedPayload?.status === "paused") {
              const failureState = circuit.fail(null, {
                pause: true,
                reason: String(startedPayload?.reason || startedPayload?.detail || "VDB transport is paused").trim(),
                retryAfterMs: Number(startedPayload?.retryAfterMs || 0),
                detail: "Paused to protect system stability.",
              })
              nextDelayMs = Math.max(failureState.retryAfterMs, pollIntervalMs)
              setState((current) => ({
                ...current,
                status: "paused",
                degraded: true,
                paused: true,
                retryAfterMs: failureState.retryAfterMs,
                reason: String(startedPayload?.reason || startedPayload?.detail || "").trim(),
                detail: String(startedPayload?.detail || "Paused to protect system stability.").trim(),
              }))
            } else {
              circuit.succeed()
              nextDelayMs = pollIntervalMs
            }
          } else {
            applyPayload(payload)
            if (payload?.degraded || payload?.autostartDeferred || payload?.status === "paused") {
              const failureState = circuit.fail(null, {
                pause: true,
                reason: String(payload?.reason || payload?.detail || "VDB transport is paused").trim(),
                retryAfterMs: Number(payload?.retryAfterMs || 0),
                detail: "Paused to protect system stability.",
              })
              nextDelayMs = Math.max(failureState.retryAfterMs, pollIntervalMs)
              setState((current) => ({
                ...current,
                status: "paused",
                degraded: true,
                paused: true,
                retryAfterMs: failureState.retryAfterMs,
                reason: String(payload?.reason || payload?.detail || "").trim(),
                detail: String(payload?.detail || "Paused to protect system stability.").trim(),
              }))
            } else {
              circuit.succeed()
              nextDelayMs = pollIntervalMs
            }
          }
        } else {
          applyPayload(payload)
          if (payload?.degraded || payload?.autostartDeferred || payload?.status === "paused") {
            const failureState = circuit.fail(null, {
              pause: true,
              reason: String(payload?.reason || payload?.detail || "VDB transport is paused").trim(),
              retryAfterMs: Number(payload?.retryAfterMs || 0),
              detail: "Paused to protect system stability.",
            })
            nextDelayMs = Math.max(failureState.retryAfterMs, pollIntervalMs)
            setState((current) => ({
              ...current,
              status: "paused",
              degraded: true,
              paused: true,
              retryAfterMs: failureState.retryAfterMs,
              reason: String(payload?.reason || payload?.detail || "").trim(),
              detail: String(payload?.detail || "Paused to protect system stability.").trim(),
            }))
          } else {
            circuit.succeed()
            nextDelayMs = pollIntervalMs
          }
        }
      } catch (error) {
        if (cancelled) return
        const failureState = circuit.fail(error, {
          reason: error?.message || "VDB transport probe failed",
          detail: "VDB transport probe failed.",
          retryAfterMs: pollIntervalMs,
        })
        nextDelayMs = failureState.paused
          ? Math.max(failureState.retryAfterMs, pollIntervalMs)
          : computeJitteredDelayMs(failureState.retryAfterMs || pollIntervalMs)
        setState({
          transport: nextTransport,
          available: false,
          status: failureState.paused ? "paused" : "unavailable",
          target: targetValue,
          detail: failureState.paused
            ? "Paused to protect system stability."
            : nextTransport === "http"
              ? "HTTP server unavailable"
              : nextTransport === "namedpipe"
                ? "Named pipe unavailable"
                : "Unix socket unavailable",
          loading: false,
          localTarget: nextTransport !== "http" || !serverUrl,
          autostartAttempted: false,
          autostartDeferred: false,
          degraded: true,
          paused: failureState.paused,
          retryAfterMs: failureState.retryAfterMs,
          reason: failureState.reason || failureState.lastError,
        })
      } finally {
        if (!cancelled) {
          timerId = window.setTimeout(runProbe, nextDelayMs)
        }
      }
    }

    runProbe()
    return () => {
      cancelled = true
      window.clearTimeout(timerId)
    }
  }, [attemptAutostart, backend, documentVisible, enabled, namedPipePath, pollIntervalMs, retryTick, serverUrl, socketPath, supportsNamedPipe, transport])

  return useMemo(() => ({ ...state, retry }), [retry, state])
}
