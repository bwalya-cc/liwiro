"use client"

import { authHeaders } from "@/lib/auth"

const PENDING_ACTION_STORAGE_KEY = "liwiro:verse-pending-action"
const PENDING_ASSISTANT_SEED_STORAGE_KEY = "liwiro:verse-pending-assistant-seed"
const CARRIED_THREAD_STORAGE_KEY = "liwiro:verse-carried-thread"

export function targetPathForVerseArtifact(artifact) {
  const kind = String(artifact?.kind || "").trim()
  if (kind === "ananse-analysis") return "/ananse-workbench"
  if (kind === "service-builder-lapis") return "/service-builder"
  if (kind === "service-manager-action") return "/services"
  if (kind === "vi-script") return "/vi-portal"
  if (kind === "vdb-query") return "/vdb-portal"
  if (kind === "page-navigation") return String(artifact?.targetPage || "").trim()
  return ""
}

export function isVerseServerActionArtifact(artifact) {
  const executionMode = String(artifact?.executionMode || "").trim().toLowerCase()
  if (executionMode) return executionMode === "server"
  return String(artifact?.kind || "").trim() === "service-manager-action"
}

export function storePendingVerseAction(payload) {
  if (typeof window === "undefined") return
  try {
    window.sessionStorage.setItem(PENDING_ACTION_STORAGE_KEY, JSON.stringify(payload || {}))
  } catch {
    // Ignore storage failures and fall back to in-page behavior only.
  }
}

export function consumePendingVerseAction(expectedPathname = "") {
  if (typeof window === "undefined") return null
  try {
    const raw = window.sessionStorage.getItem(PENDING_ACTION_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== "object") return null
    const targetPath = String(parsed.targetPath || "").trim()
    const expected = String(expectedPathname || "").trim()
    if (expected && targetPath && expected !== targetPath) {
      return null
    }
    window.sessionStorage.removeItem(PENDING_ACTION_STORAGE_KEY)
    return parsed
  } catch {
    return null
  }
}

export function storeCarriedVerseThread(payload) {
  if (typeof window === "undefined") return
  try {
    window.sessionStorage.setItem(CARRIED_THREAD_STORAGE_KEY, JSON.stringify(payload || {}))
  } catch {
    // Ignore storage failures and fall back to page-local thread resolution.
  }
}

export function consumeCarriedVerseThread(expectedPathname = "") {
  if (typeof window === "undefined") return null
  try {
    const raw = window.sessionStorage.getItem(CARRIED_THREAD_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== "object") return null
    const targetPath = String(parsed.pathname || parsed.targetPath || "").trim()
    const expected = String(expectedPathname || "").trim()
    if (expected && targetPath && expected !== targetPath) {
      return null
    }
    window.sessionStorage.removeItem(CARRIED_THREAD_STORAGE_KEY)
    return parsed
  } catch {
    return null
  }
}

export function storePendingVerseAssistantSeed(payload) {
  if (typeof window === "undefined") return
  try {
    window.sessionStorage.setItem(PENDING_ASSISTANT_SEED_STORAGE_KEY, JSON.stringify(payload || {}))
  } catch {
    // Ignore storage failures and rely on the in-memory event only.
  }
}

export function consumePendingVerseAssistantSeed(expectedPathname = "") {
  if (typeof window === "undefined") return null
  try {
    const raw = window.sessionStorage.getItem(PENDING_ASSISTANT_SEED_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== "object") return null
    const targetPath = String(parsed.pathname || "").trim()
    const expected = String(expectedPathname || "").trim()
    if (expected && targetPath && expected !== targetPath) {
      return null
    }
    window.sessionStorage.removeItem(PENDING_ASSISTANT_SEED_STORAGE_KEY)
    return parsed
  } catch {
    return null
  }
}

export function dispatchVersePageAction(eventName, { pathname = "/", artifact = null, action = "apply" } = {}, timeoutMs = 1000) {
  return new Promise((resolve) => {
    if (typeof window === "undefined") {
      resolve({ ok: false, message: "This action requires a browser page." })
      return
    }
    let settled = false
    const finish = (payload = {}) => {
      if (settled) return
      settled = true
      resolve(payload && typeof payload === "object" ? payload : {})
    }
    const timer = window.setTimeout(
      () => finish({ ok: false, message: "This page did not expose the requested Verse action." }),
      timeoutMs
    )
    window.dispatchEvent(
      new CustomEvent(eventName, {
        detail: {
          pathname,
          artifact,
          action,
          respond: (payload) => {
            window.clearTimeout(timer)
            finish(payload)
          },
        },
      })
    )
  })
}

export function dispatchVerseAssistantSeed({ pathname = "/", message = null, open = true } = {}) {
  if (typeof window === "undefined") return
  window.dispatchEvent(
    new CustomEvent("liwiro:verse-assistant-seed", {
      detail: {
        pathname,
        open,
        message,
      },
    })
  )
}

export function activatePendingVerseAction({ pathname = "/", pendingAction = null, onResult } = {}) {
  if (typeof window === "undefined" || !pendingAction?.artifact) return false
  const artifact = pendingAction.artifact
  const respond = (payload = {}) => {
    if (typeof onResult === "function") {
      onResult(payload && typeof payload === "object" ? payload : {})
    }
  }
  if (String(artifact?.kind || "").trim() === "page-navigation") {
    const carriedThreadId = String(pendingAction?.threadId || "").trim()
    if (carriedThreadId) {
      storeCarriedVerseThread({
        pathname,
        targetPath: pathname,
        threadId: carriedThreadId,
        sourcePathname: String(pendingAction?.sourcePathname || "").trim(),
        sourceSurface: String(pendingAction?.sourceSurface || "").trim(),
        carriedAt: new Date().toISOString(),
      })
    }
    const followUp = artifact?.followUp && typeof artifact.followUp === "object" ? artifact.followUp : {}
    const followUpArtifact = followUp?.artifact && typeof followUp.artifact === "object" ? followUp.artifact : null
    const followUpMessage = String(followUp?.message || "").trim() || "You are in the right workspace now. Should I continue?"
    const seedPayload = {
      pathname,
      open: true,
      message: {
        id: `verse-seed-${Date.now()}`,
        role: "agent",
        content: followUpMessage,
        agentId: String(followUp?.agentId || ""),
        agentName: String(followUp?.agentName || ""),
        agentTitle: String(followUp?.agentTitle || ""),
        agentDisplayName: String(followUp?.agentDisplayName || followUp?.agentName || "Verse Chat"),
        styleToken: String(followUp?.styleToken || "slate"),
        artifact: followUpArtifact,
        visualization: null,
        inspectDetails: {
          manualLinks: Array.isArray(followUp?.manualLinks) ? followUp.manualLinks : [],
        },
        retrievalTrace: [],
        confidence: "High",
      },
    }
    storePendingVerseAssistantSeed(seedPayload)
    dispatchVerseAssistantSeed(seedPayload)
    respond({
      ok: true,
      message: `Opened ${String(artifact?.destination?.label || "the requested workspace").trim() || "the requested workspace"} and queued the next step.`,
    })
    return true
  }
  window.setTimeout(() => {
    window.dispatchEvent(
      new CustomEvent(
        pendingAction?.mode === "apply" ? "liwiro:verse-assistant-apply" : "liwiro:verse-assistant-execute",
        {
          detail: {
            pathname,
            artifact,
            action: pendingAction.mode || "apply",
            respond,
          },
        }
      )
    )
  }, 0)
  return true
}

export async function executeVerseServerAction({ backend, artifact, context = {} } = {}) {
  const baseUrl = String(backend || "").trim()
  if (!baseUrl) {
    return { ok: false, message: "Verse action execution is not configured." }
  }
  const response = await fetch(`${baseUrl}/platform/verse/actions/execute`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({
      artifact,
      context,
    }),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    return {
      ok: false,
      message: payload?.error || payload?.message || "Verse could not run the requested action.",
      payload,
    }
  }
  return {
    ok: Boolean(payload?.ok ?? true),
    message: payload?.message || "Verse completed the requested action.",
    payload,
  }
}
