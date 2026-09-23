"use client"

import { fetchAuthedJson, invalidateAuthedJsonCache } from "@/lib/authed-json-cache"

function verseBootstrapUrl(backend = "") {
  const baseUrl = String(backend || "http://127.0.0.1:5000").trim() || "http://127.0.0.1:5000"
  return `${baseUrl}/platform/verse/bootstrap`
}

export function fetchVerseBootstrap(backend, { ttlMs = 5000 } = {}) {
  return fetchAuthedJson(verseBootstrapUrl(backend), { ttlMs })
}

export function invalidateVerseBootstrap(backend) {
  invalidateAuthedJsonCache(verseBootstrapUrl(backend))
}
