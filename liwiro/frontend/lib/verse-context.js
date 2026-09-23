"use client"

function trimText(value, limit = 240) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim()
  if (!text) return ""
  if (text.length <= limit) return text
  return `${text.slice(0, Math.max(limit - 3, 0)).trimEnd()}...`
}

function normalizeRecord(item, limit = 8) {
  if (!item || typeof item !== "object" || Array.isArray(item)) return null
  const next = {}
  for (const [key, value] of Object.entries(item).slice(0, limit)) {
    const keyText = trimText(key, 80)
    if (!keyText) continue
    if (typeof value === "boolean" || typeof value === "number") {
      next[keyText] = value
      continue
    }
    const text = trimText(value, 180)
    if (text) next[keyText] = text
  }
  return Object.keys(next).length > 0 ? next : null
}

function normalizeRecordList(items, limit = 8) {
  if (!Array.isArray(items)) return []
  return items.map((item) => normalizeRecord(item)).filter(Boolean).slice(0, limit)
}

function normalizeMetrics(metrics = {}) {
  if (!metrics || typeof metrics !== "object" || Array.isArray(metrics)) return {}
  const next = {}
  for (const [key, value] of Object.entries(metrics).slice(0, 12)) {
    const keyText = trimText(key, 80)
    if (!keyText) continue
    if (typeof value === "boolean" || typeof value === "number") {
      next[keyText] = value
      continue
    }
    const text = trimText(value, 120)
    if (text) next[keyText] = text
  }
  return next
}

function normalizeFocus(raw = {}, fallback = {}) {
  const source = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : fallback
  const next = {
    kind: trimText(source?.kind, 80),
    label: trimText(source?.label, 160),
    identifier: trimText(source?.identifier || source?.id, 160),
    contentSummary: trimText(source?.contentSummary || fallback?.contentSummary, 240),
    contentPreview: trimText(source?.contentPreview || fallback?.contentPreview, 900),
    path: trimText(source?.path || fallback?.path, 180),
  }
  return Object.fromEntries(Object.entries(next).filter(([, value]) => value !== ""))
}

function buildLegacySummary(raw = {}) {
  const parts = [
    raw?.pageSummary,
    raw?.serviceName ? `Service draft: ${raw.serviceName}` : "",
    raw?.activeTab ? `Active tab: ${raw.activeTab}` : "",
    raw?.editorMode ? `Editor mode: ${raw.editorMode}` : "",
    raw?.mode ? `Mode: ${raw.mode}` : "",
    raw?.sourceDir ? `Source dir: ${raw.sourceDir}` : "",
    raw?.workspaceEnvPath ? `Workspace env: ${raw.workspaceEnvPath}` : "",
    raw?.activeDomain ? `Domain: ${raw.activeDomain}` : "",
    raw?.activeDb ? `Database: ${raw.activeDb}` : "",
    raw?.datasetTitle ? `Dataset: ${raw.datasetTitle}` : "",
    raw?.analysisTitle ? `Analysis: ${raw.analysisTitle}` : "",
    raw?.chartType ? `Chart: ${raw.chartType}` : "",
    raw?.vdbStatus ? `VDB: ${raw.vdbStatus}` : "",
    raw?.viStatus ? `VI: ${raw.viStatus}` : "",
  ]
  return trimText(parts.filter(Boolean).join(" | "), 900)
}

function normalizeSelection(raw = {}) {
  const next = {
    kind: trimText(raw?.selection?.kind || raw?.focus?.kind, 80),
    id: trimText(raw?.selection?.id || raw?.selectedServiceId || raw?.selectedDatasetId || raw?.selectedFile, 160),
    name: trimText(raw?.selection?.name || raw?.selectedServiceName || raw?.datasetTitle, 160),
    targetPath: trimText(raw?.selection?.targetPath || raw?.filePath, 180),
  }
  return Object.fromEntries(Object.entries(next).filter(([, value]) => value !== ""))
}

function normalizeEntity(raw = {}) {
  const source = raw?.entity || raw?.selectedService || null
  if (!source || typeof source !== "object" || Array.isArray(source)) return {}
  const next = {
    kind: trimText(source?.kind || "entity", 80),
    id: trimText(source?.id || source?.processId, 160),
    name: trimText(source?.name || source?.apiName || source?.title, 160),
    status: trimText(source?.status, 80),
    path: trimText(source?.path || source?.basePath, 180),
  }
  return Object.fromEntries(Object.entries(next).filter(([, value]) => value !== ""))
}

function normalizeAvailableActions(raw = {}) {
  if (!Array.isArray(raw?.availableActions)) return []
  return raw.availableActions
    .map((item) => normalizeRecord(item, 6))
    .filter(Boolean)
    .slice(0, 8)
}

export function normalizeVerseContext(rawContext = {}, fallback = {}) {
  const raw = rawContext && typeof rawContext === "object" && !Array.isArray(rawContext) ? rawContext : {}
  const pathname = trimText(raw?.pathname || fallback?.pathname || "/", 160) || "/"
  const screen = trimText(raw?.screen || fallback?.screen || pathname, 160) || pathname
  const pageKind = trimText(raw?.pageKind || fallback?.pageKind, 80)
  const focus = normalizeFocus(raw?.focus, {
    kind: fallback?.focusKind,
    label: raw?.selectedServiceName || raw?.serviceName || raw?.datasetTitle || raw?.selectedFile || raw?.filePath || raw?.activeDb || pathname,
    contentSummary: raw?.selectedServiceName || raw?.serviceName || raw?.analysisTitle || raw?.datasetTitle || raw?.selectedFile || raw?.filePath || "",
    contentPreview: raw?.rawConfigText || raw?.fileContent || raw?.queryText || "",
    path: raw?.filePath || "",
  })
  const selection = normalizeSelection(raw)
  const entity = normalizeEntity(raw)
  const metrics = normalizeMetrics(raw?.metrics)
  const availableActions = normalizeAvailableActions(raw)
  const records = normalizeRecordList(raw?.records?.length ? raw.records : (raw?.services?.length ? raw.services : raw?.serviceRoster))
  const pageSummary = buildLegacySummary(raw)

  return {
    pathname,
    screen,
    ...(pageKind ? { pageKind } : {}),
    ...(Object.keys(focus).length > 0 ? { focus } : {}),
    ...(Object.keys(selection).length > 0 ? { selection } : {}),
    ...(Object.keys(entity).length > 0 ? { entity } : {}),
    ...(Object.keys(metrics).length > 0 ? { metrics } : {}),
    ...(availableActions.length > 0 ? { availableActions } : {}),
    ...(pageSummary ? { pageSummary } : {}),
    ...(records.length > 0 ? { records } : {}),
  }
}
