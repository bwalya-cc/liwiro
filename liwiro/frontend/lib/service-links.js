// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

const HTTP_PROTOCOL_RE = /^https?:\/\//i

function ensureHttpUrl(value) {
  const raw = String(value || "").trim()
  if (!raw) return null
  const candidate = HTTP_PROTOCOL_RE.test(raw) ? raw : `http://${raw}`
  try {
    const parsed = new URL(candidate)
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null
    return parsed
  } catch {
    return null
  }
}

export function resolveServiceLinks(service, fallbackHost = "http://127.0.0.1") {
  const runtimeFromApi = ensureHttpUrl(service?.runtimeUrl)
  const rootFromApi = ensureHttpUrl(service?.rootUrl)
  const fallbackHostUrl = ensureHttpUrl(fallbackHost)
  const port = Number(service?.port)
  const managementRoutesEnabled = service?.managementRoutesEnabled !== false

  let origin = runtimeFromApi ? runtimeFromApi.origin : null
  if (!origin && rootFromApi) {
    origin = rootFromApi.origin
  }
  if (!origin && fallbackHostUrl && Number.isFinite(port) && port > 0) {
    origin = `${fallbackHostUrl.protocol}//${fallbackHostUrl.hostname}:${port}`
  }

  const runtime = managementRoutesEnabled
    ? (ensureHttpUrl(service?.runtimeUrl)?.href || (origin ? `${origin}/liwiro` : null))
    : null
  const root = origin ? `${origin}/` : null
  const docsEnabled = service?.docsEnabled !== false
  const liwiroDocs = docsEnabled && managementRoutesEnabled
    ? (ensureHttpUrl(service?.liwiroDocsUrl)?.href || (origin ? `${origin}/liwiro/docs` : null))
    : null

  return {
    runtime,
    root,
    liwiroDocs,
    docsEnabled,
    managementRoutesEnabled,
    productionMode: Boolean(service?.productionMode),
  }
}
