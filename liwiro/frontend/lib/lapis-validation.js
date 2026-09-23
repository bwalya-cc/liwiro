"use client"

import { authHeaders } from "@/lib/auth"

export function mapVersaIssuesByEndpoint(issues = []) {
  return Object.fromEntries(
    (Array.isArray(issues) ? issues : [])
      .map((item) => {
        const endpointId = String(item?.endpointId || "").trim()
        const error = String(item?.error || item?.message || "").trim()
        return endpointId && error ? [endpointId, error] : null
      })
      .filter(Boolean)
  )
}

function normalizeLapisValidationPayload(payload = {}, fallbackError = "") {
  return {
    ok: Boolean(payload?.ok),
    error: String(payload?.error || fallbackError || "").trim(),
    versaIssues: Array.isArray(payload?.versaIssues) ? payload.versaIssues : [],
    issues: Array.isArray(payload?.issues) ? payload.issues : [],
    normalized: payload?.normalized && typeof payload.normalized === "object" ? payload.normalized : null,
    dryRun: payload?.dryRun && typeof payload.dryRun === "object" ? payload.dryRun : null,
    validationState: payload?.validationState && typeof payload.validationState === "object" ? payload.validationState : {},
    featureFlags: payload?.featureFlags && typeof payload.featureFlags === "object" ? payload.featureFlags : {},
    repairAttempts: Array.isArray(payload?.repairAttempts) ? payload.repairAttempts : [],
    appliedFixes: Array.isArray(payload?.appliedFixes) ? payload.appliedFixes : [],
    attemptCount: Number(payload?.attemptCount || 0),
    repaired: Boolean(payload?.repaired),
    repairable: Boolean(payload?.repairable),
    finalStatus: String(payload?.finalStatus || "").trim(),
    progressMessage: String(payload?.progressMessage || "").trim(),
  }
}

export async function validateLapisConfigRemote(backend, config, validationState = {}) {
  const baseUrl = String(backend || "").trim()
  if (!baseUrl) {
    return normalizeLapisValidationPayload({ ok: false, error: "Liwiro backend is not configured." })
  }
  const response = await fetch(`${baseUrl}/platform/lapis/validate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({ config, validationState }),
  })
  const payload = await response.json().catch(() => ({}))
  return normalizeLapisValidationPayload(payload, response.ok ? "" : "Failed to validate LAPIS config.")
}

export async function repairLapisConfigRemote(backend, config, { maxAttempts = 6 } = {}) {
  const baseUrl = String(backend || "").trim()
  if (!baseUrl) {
    return normalizeLapisValidationPayload({ ok: false, error: "Liwiro backend is not configured.", finalStatus: "failed" })
  }
  const response = await fetch(`${baseUrl}/platform/lapis/repair`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({ config, maxAttempts }),
  })
  const payload = await response.json().catch(() => ({}))
  return normalizeLapisValidationPayload(payload, response.ok ? "" : "Failed to repair LAPIS config.")
}
