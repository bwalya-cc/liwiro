// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

export const AUTH_TOKEN_KEY = "liwiro_auth_token"
export const AUTH_VERIFICATION_KEY = "liwiro_auth_verification"
export const AUTH_RUNTIME_STATE_KEY = "liwiro_auth_runtime_state"
export const AUTH_VERIFICATION_TTL_MS = 60_000

export function getAuthToken() {
  if (typeof window === "undefined") return ""
  return window.localStorage.getItem(AUTH_TOKEN_KEY) || ""
}

export function setAuthToken(token) {
  if (typeof window === "undefined") return
  if (!token) {
    window.localStorage.removeItem(AUTH_TOKEN_KEY)
    window.sessionStorage.removeItem(AUTH_VERIFICATION_KEY)
    window.sessionStorage.removeItem(AUTH_RUNTIME_STATE_KEY)
    return
  }
  window.localStorage.setItem(AUTH_TOKEN_KEY, token)
  window.sessionStorage.removeItem(AUTH_VERIFICATION_KEY)
}

/** @param {Record<string, any>|null} payload */
export function setAuthRuntimeState(payload = null) {
  if (typeof window === "undefined") return
  if (!payload || typeof payload !== "object") {
    window.sessionStorage.removeItem(AUTH_RUNTIME_STATE_KEY)
    return
  }
  window.sessionStorage.setItem(
    AUTH_RUNTIME_STATE_KEY,
    JSON.stringify({
      vdbRuntimeReady: payload?.vdbRuntimeReady !== false,
      vdbRuntimeError: String(payload?.vdbRuntimeError || "").trim(),
      aiConfigured: payload?.aiConfigured !== false,
      aiDefaultProvider: String(payload?.aiDefaultProvider || "").trim(),
      canManageAi: Boolean(payload?.canManageAi),
      updatedAt: Date.now(),
    }),
  )
}

export function getAuthRuntimeState() {
  if (typeof window === "undefined") return null
  try {
    const raw = window.sessionStorage.getItem(AUTH_RUNTIME_STATE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return {
      vdbRuntimeReady: parsed?.vdbRuntimeReady !== false,
      vdbRuntimeError: String(parsed?.vdbRuntimeError || "").trim(),
      aiConfigured: parsed?.aiConfigured !== false,
      aiDefaultProvider: String(parsed?.aiDefaultProvider || "").trim(),
      canManageAi: Boolean(parsed?.canManageAi),
      updatedAt: Number(parsed?.updatedAt || 0),
    }
  } catch {
    return null
  }
}

export function authHeaders(extra = {}) {
  const token = getAuthToken()
  const headers = { ...extra }
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

export function markAuthVerified(token = getAuthToken()) {
  if (typeof window === "undefined") return
  const normalizedToken = String(token || "").trim()
  if (!normalizedToken) return
  window.sessionStorage.setItem(
    AUTH_VERIFICATION_KEY,
    JSON.stringify({
      token: normalizedToken,
      verifiedAt: Date.now(),
    }),
  )
}

export function hasFreshAuthVerification(token = getAuthToken(), maxAgeMs = AUTH_VERIFICATION_TTL_MS) {
  if (typeof window === "undefined") return false
  const normalizedToken = String(token || "").trim()
  if (!normalizedToken) return false
  try {
    const raw = window.sessionStorage.getItem(AUTH_VERIFICATION_KEY)
    if (!raw) return false
    const parsed = JSON.parse(raw)
    const verifiedToken = String(parsed?.token || "").trim()
    const verifiedAt = Number(parsed?.verifiedAt || 0)
    if (!verifiedToken || verifiedToken !== normalizedToken) return false
    if (!Number.isFinite(verifiedAt) || verifiedAt <= 0) return false
    return Date.now() - verifiedAt <= Math.max(0, Number(maxAgeMs) || 0)
  } catch {
    return false
  }
}
