"use client"

import { useEffect, useMemo, useState } from "react"

import { authHeaders } from "@/lib/auth"

export const DEFAULT_PLATFORM_FEATURE_FLAGS = {
  lapisRecursiveAutoFix: true,
  lapisSafeSchemaAutoFix: true,
  unifiedOperationStatus: true,
  transientSuccessFeedback: true,
  serviceBatchProgressMessages: true,
  viProgressMessages: true,
  vdbProgressMessages: true,
  verseActionProgressMessages: true,
  settingsProgressMessages: true,
}

let featureFlagsPromise = null
let featureFlagsCache = null

export async function fetchPlatformFeatureFlags(backend) {
  const baseUrl = String(backend || "").trim()
  if (!baseUrl) {
    return {
      featureFlags: { ...DEFAULT_PLATFORM_FEATURE_FLAGS },
      featureFlagDefinitions: [],
    }
  }
  if (featureFlagsCache) {
    return featureFlagsCache
  }
  if (featureFlagsPromise) {
    return featureFlagsPromise
  }
  featureFlagsPromise = fetch(`${baseUrl}/platform/feature-flags`, { headers: authHeaders() })
    .then(async (response) => {
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload?.error || "Failed to load platform feature flags")
      }
      const next = {
        featureFlags: {
          ...DEFAULT_PLATFORM_FEATURE_FLAGS,
          ...(payload?.featureFlags && typeof payload.featureFlags === "object" ? payload.featureFlags : {}),
        },
        featureFlagDefinitions: Array.isArray(payload?.featureFlagDefinitions) ? payload.featureFlagDefinitions : [],
      }
      featureFlagsCache = next
      return next
    })
    .catch(() => ({
      featureFlags: { ...DEFAULT_PLATFORM_FEATURE_FLAGS },
      featureFlagDefinitions: [],
    }))
    .finally(() => {
      featureFlagsPromise = null
    })
  return featureFlagsPromise
}

export function usePlatformFeatureFlags(backend, { enabled = true } = {}) {
  const [state, setState] = useState({
    loading: Boolean(enabled),
    featureFlags: { ...DEFAULT_PLATFORM_FEATURE_FLAGS },
    featureFlagDefinitions: [],
    error: "",
  })

  useEffect(() => {
    if (!enabled) {
      setState((current) => ({
        ...current,
        loading: false,
        featureFlags: { ...DEFAULT_PLATFORM_FEATURE_FLAGS, ...(current.featureFlags || {}) },
      }))
      return
    }
    let active = true
    setState((current) => ({ ...current, loading: true, error: "" }))
    fetchPlatformFeatureFlags(backend)
      .then((next) => {
        if (!active) return
        setState({
          loading: false,
          featureFlags: next.featureFlags,
          featureFlagDefinitions: next.featureFlagDefinitions,
          error: "",
        })
      })
      .catch((error) => {
        if (!active) return
        setState((current) => ({
          ...current,
          loading: false,
          error: String(error?.message || "Failed to load platform feature flags"),
          featureFlags: { ...DEFAULT_PLATFORM_FEATURE_FLAGS, ...(current.featureFlags || {}) },
        }))
      })
    return () => {
      active = false
    }
  }, [backend, enabled])

  return useMemo(
    () => ({
      loading: state.loading,
      error: state.error,
      featureFlags: state.featureFlags,
      featureFlagDefinitions: state.featureFlagDefinitions,
    }),
    [state]
  )
}

export function isFeatureEnabled(featureFlags, key, fallback = false) {
  if (!featureFlags || typeof featureFlags !== "object") return Boolean(fallback)
  if (!Object.prototype.hasOwnProperty.call(featureFlags, key)) return Boolean(fallback)
  return Boolean(featureFlags[key])
}
