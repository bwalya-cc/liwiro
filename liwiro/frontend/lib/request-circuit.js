"use client"

const DEFAULT_FAILURE_THRESHOLD = 3
const DEFAULT_BASE_DELAY_MS = 2_000
const DEFAULT_MAX_DELAY_MS = 60_000
const DEFAULT_JITTER_RATIO = 0.15

function normalizeDelayMs(value, fallback = 0) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed < 0) return Math.max(0, Number(fallback) || 0)
  return Math.round(parsed)
}

export function computeBackoffDelayMs(
  failureCount,
  {
    baseDelayMs = DEFAULT_BASE_DELAY_MS,
    maxDelayMs = DEFAULT_MAX_DELAY_MS,
    overrideDelayMs = 0,
  } = {},
) {
  const explicitDelay = normalizeDelayMs(overrideDelayMs, 0)
  if (explicitDelay > 0) {
    return explicitDelay
  }
  const normalizedFailures = Math.max(1, Number(failureCount) || 1)
  const computed = normalizeDelayMs(baseDelayMs, DEFAULT_BASE_DELAY_MS) * (2 ** Math.max(0, normalizedFailures - 1))
  return Math.min(normalizeDelayMs(maxDelayMs, DEFAULT_MAX_DELAY_MS), computed)
}

export function computeJitteredDelayMs(delayMs, jitterRatio = DEFAULT_JITTER_RATIO) {
  const normalizedDelay = normalizeDelayMs(delayMs, 0)
  if (normalizedDelay <= 0) return 0
  const normalizedRatio = Math.max(0, Math.min(0.5, Number(jitterRatio) || 0))
  if (normalizedRatio <= 0) return normalizedDelay
  const spread = Math.round(normalizedDelay * normalizedRatio)
  if (spread <= 0) return normalizedDelay
  const offset = Math.round((Math.random() * 2 - 1) * spread)
  return Math.max(0, normalizedDelay + offset)
}

export function parseRetryAfterMs(payload = null, headers = null) {
  const payloadDelay = normalizeDelayMs(payload?.retryAfterMs, 0)
  if (payloadDelay > 0) return payloadDelay
  const headerValue = typeof headers?.get === "function" ? headers.get("Retry-After") : ""
  const normalizedHeader = String(headerValue || "").trim()
  if (!normalizedHeader) return 0
  const asSeconds = Number(normalizedHeader)
  if (Number.isFinite(asSeconds) && asSeconds > 0) {
    return Math.round(asSeconds * 1000)
  }
  const asDate = Date.parse(normalizedHeader)
  if (!Number.isNaN(asDate)) {
    return Math.max(0, asDate - Date.now())
  }
  return 0
}

export function createFailureCircuit({
  failureThreshold = DEFAULT_FAILURE_THRESHOLD,
  baseDelayMs = DEFAULT_BASE_DELAY_MS,
  maxDelayMs = DEFAULT_MAX_DELAY_MS,
} = {}) {
  const normalizedThreshold = Math.max(1, Number(failureThreshold) || DEFAULT_FAILURE_THRESHOLD)
  const normalizedBaseDelay = normalizeDelayMs(baseDelayMs, DEFAULT_BASE_DELAY_MS)
  const normalizedMaxDelay = Math.max(normalizedBaseDelay, normalizeDelayMs(maxDelayMs, DEFAULT_MAX_DELAY_MS))

  let state = {
    failureCount: 0,
    degraded: false,
    paused: false,
    retryAfterMs: 0,
    reason: "",
    lastError: "",
    updatedAt: 0,
  }

  const snapshot = () => ({ ...state })

  return {
    snapshot,
    reset(overrides = {}) {
      state = {
        failureCount: 0,
        degraded: false,
        paused: false,
        retryAfterMs: 0,
        reason: "",
        lastError: "",
        updatedAt: Date.now(),
        ...(overrides && typeof overrides === "object" ? overrides : {}),
      }
      return snapshot()
    },
    succeed(overrides = {}) {
      return this.reset(overrides)
    },
    fail(error, { pause = false, reason = "", retryAfterMs = 0, detail = "" } = {}) {
      const nextFailureCount = Math.max(1, Number(state.failureCount || 0) + 1)
      const nextDelay = computeBackoffDelayMs(nextFailureCount, {
        baseDelayMs: normalizedBaseDelay,
        maxDelayMs: normalizedMaxDelay,
        overrideDelayMs: retryAfterMs,
      })
      const lastError = String(error?.message || error || reason || detail || "").trim()
      state = {
        failureCount: nextFailureCount,
        degraded: true,
        paused: Boolean(pause || nextFailureCount >= normalizedThreshold),
        retryAfterMs: nextDelay,
        reason: String(reason || detail || lastError || "").trim(),
        lastError,
        updatedAt: Date.now(),
      }
      return snapshot()
    },
  }
}
