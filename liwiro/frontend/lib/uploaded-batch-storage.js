export const SERVICES_UPLOADED_BATCH_STORAGE_KEY = "liwiro:services:uploaded-batch-configs"
export const SERVICE_BUILDER_UPLOADED_BATCH_STORAGE_KEY = "liwiro:service-builder:uploaded-batch-configs"
export const BUILDER_EDIT_REQUEST_KEY = "liwiro:service-builder:edit-uploaded-request"
export const BUILDER_EDIT_RESULT_KEY = "liwiro:service-builder:edit-uploaded-result"

export function getBatchStorageKeyForSource(source) {
  if (String(source || "").trim() === "service-builder-uploaded-list") {
    return SERVICE_BUILDER_UPLOADED_BATCH_STORAGE_KEY
  }
  return SERVICES_UPLOADED_BATCH_STORAGE_KEY
}

export function getBatchReturnPathForSource(source) {
  if (String(source || "").trim() === "service-builder-uploaded-list") {
    return "/service-builder"
  }
  return "/services"
}

export function readSessionJson(key) {
  if (typeof window === "undefined") return null
  try {
    const raw = window.sessionStorage.getItem(key)
    if (!raw) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function writeSessionJson(key, value) {
  if (typeof window === "undefined") return
  window.sessionStorage.setItem(key, JSON.stringify(value))
}
