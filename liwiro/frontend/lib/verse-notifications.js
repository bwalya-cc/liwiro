"use client"

import { authHeaders } from "@/lib/auth"
import { invalidateAuthedJsonCache } from "@/lib/authed-json-cache"

const notificationRequests = new Map()

export async function fetchVerseNotifications({ backend, runScheduler = true, force = false } = {}) {
  const baseUrl = String(backend || "").trim()
  const params = new URLSearchParams()
  if (!runScheduler) params.set("run", "0")
  if (force) params.set("force", "1")
  const requestUrl = `${baseUrl}/platform/verse/notifications${params.size ? `?${params.toString()}` : ""}`
  const requestKey = `notifications:${requestUrl}`
  if (notificationRequests.has(requestKey)) {
    return notificationRequests.get(requestKey)
  }
  const promise = fetch(requestUrl, {
    headers: authHeaders(),
  })
    .then(async (response) => {
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload?.error || "Failed to load Verse notifications")
      }
      return payload || {}
    })
    .finally(() => {
      notificationRequests.delete(requestKey)
    })
  notificationRequests.set(requestKey, promise)
  return promise
}

export async function markVerseNotificationsRead({ backend, notificationId = "", threadId = "" } = {}) {
  const baseUrl = String(backend || "").trim()
  const response = await fetch(`${baseUrl}/platform/verse/notifications/read`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      notificationId,
      threadId,
    }),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload?.error || "Failed to mark Verse notifications as read")
  }
  invalidateAuthedJsonCache(`${baseUrl}/platform/verse/notifications`)
  return payload || {}
}

export async function ignoreVerseIssue({ backend, issueKey = "", agentId = "", threadId = "" } = {}) {
  const baseUrl = String(backend || "").trim()
  const response = await fetch(`${baseUrl}/platform/verse/issues/ignore`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      issueKey,
      agentId,
      threadId,
    }),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload?.error || "Failed to ignore the proactive Verse issue")
  }
  invalidateAuthedJsonCache(`${baseUrl}/platform/verse/notifications`)
  return payload || {}
}
