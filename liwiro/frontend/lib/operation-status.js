"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"

function normalizeStatus(payload = {}) {
  return {
    state: String(payload?.state || "idle").trim() || "idle",
    title: String(payload?.title || "").trim(),
    label: String(payload?.label || "").trim(),
    detail: String(payload?.detail || "").trim(),
    current: String(payload?.current || "").trim(),
    presentation: String(payload?.presentation || "inline").trim() || "inline",
    total: Number(payload?.total || 0),
    completed: Number(payload?.completed || 0),
    succeeded: Number(payload?.succeeded || 0),
    failed: Number(payload?.failed || 0),
    progress: Number(payload?.progress || 0),
    visible: payload?.visible !== false,
  }
}

export function useOperationStatus({ autoHideSuccessMs = 1800 } = {}) {
  const hideTimerRef = useRef(null)
  const [status, setStatus] = useState(null)

  const clearHideTimer = useCallback(() => {
    if (hideTimerRef.current) {
      clearTimeout(hideTimerRef.current)
      hideTimerRef.current = null
    }
  }, [])

  const clearStatus = useCallback(() => {
    clearHideTimer()
    setStatus(null)
  }, [clearHideTimer])

  const setOperationStatus = useCallback((payload = {}) => {
    clearHideTimer()
    setStatus(normalizeStatus(payload))
  }, [clearHideTimer])

  const startOperation = useCallback((payload = {}) => {
    setOperationStatus({ state: "running", visible: true, ...payload })
  }, [setOperationStatus])

  const updateOperation = useCallback((patch = {}) => {
    clearHideTimer()
    setStatus((current) => normalizeStatus({ ...(current || {}), ...patch, visible: true }))
  }, [clearHideTimer])

  const succeedOperation = useCallback((payload = {}) => {
    clearHideTimer()
    setStatus((current) => normalizeStatus({ ...(current || {}), state: "success", visible: true, ...payload }))
    hideTimerRef.current = setTimeout(() => {
      setStatus(null)
      hideTimerRef.current = null
    }, Math.max(300, Number(payload?.autoHideMs || autoHideSuccessMs) || autoHideSuccessMs))
  }, [autoHideSuccessMs, clearHideTimer])

  const failOperation = useCallback((payload = {}) => {
    clearHideTimer()
    setStatus((current) => normalizeStatus({ ...(current || {}), state: "error", visible: true, ...payload }))
  }, [clearHideTimer])

  useEffect(() => () => clearHideTimer(), [clearHideTimer])

  return useMemo(() => ({
    status,
    setOperationStatus,
    startOperation,
    updateOperation,
    succeedOperation,
    failOperation,
    clearStatus,
  }), [clearStatus, failOperation, setOperationStatus, startOperation, status, succeedOperation, updateOperation])
}
