"use client"

import { authHeaders } from "@/lib/auth"

const inflightRequests = new Map()
const responseCache = new Map()

export async function fetchAuthedJson(url, { ttlMs = 0, cacheKey = "" } = {}) {
  const targetUrl = String(url || "").trim()
  const key = String(cacheKey || targetUrl).trim()
  if (!targetUrl || !key) {
    throw new Error("A request URL is required")
  }

  const now = Date.now()
  if (ttlMs > 0) {
    const cached = responseCache.get(key)
    if (cached && now - cached.at < ttlMs) {
      return cached.payload
    }
  }

  if (inflightRequests.has(key)) {
    return inflightRequests.get(key)
  }

  const promise = fetch(targetUrl, { headers: authHeaders() })
    .then(async (response) => {
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        const error = new Error(payload?.error || `Request failed with status ${response.status}`)
        error.status = response.status
        error.payload = payload
        throw error
      }
      if (ttlMs > 0) {
        responseCache.set(key, { at: Date.now(), payload })
      }
      return payload
    })
    .finally(() => {
      inflightRequests.delete(key)
    })

  inflightRequests.set(key, promise)
  return promise
}

export function invalidateAuthedJsonCache(prefix = "") {
  const normalizedPrefix = String(prefix || "").trim()
  if (!normalizedPrefix) {
    responseCache.clear()
    inflightRequests.clear()
    return
  }
  for (const key of [...responseCache.keys()]) {
    if (key.startsWith(normalizedPrefix)) {
      responseCache.delete(key)
    }
  }
  for (const key of [...inflightRequests.keys()]) {
    if (key.startsWith(normalizedPrefix)) {
      inflightRequests.delete(key)
    }
  }
}
