"use client"

import { createContext, useContext, useEffect, useMemo, useState, type Dispatch, type ReactNode, type SetStateAction } from "react"

const SIDEBAR_STORAGE_KEY = "liwiro:ui:sidebar-pinned"

type UiPreferencesContextValue = {
  hydrated: boolean
  sidebarPinned: boolean
  setSidebarPinned: Dispatch<SetStateAction<boolean>>
}

const UiPreferencesContext = createContext<UiPreferencesContextValue | null>(null)

function readStoredBoolean(key: string, fallback: boolean) {
  if (typeof window === "undefined") return fallback
  const raw = window.localStorage.getItem(key)
  if (raw == null) return fallback
  return raw === "true"
}

export function UiPreferencesProvider({ children }: { children: ReactNode }) {
  const [hydrated, setHydrated] = useState(false)
  const [sidebarPinned, setSidebarPinned] = useState(false)

  useEffect(() => {
    setSidebarPinned(readStoredBoolean(SIDEBAR_STORAGE_KEY, false))
    setHydrated(true)
  }, [])

  useEffect(() => {
    if (!hydrated) return
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(sidebarPinned))
  }, [hydrated, sidebarPinned])

  const value = useMemo<UiPreferencesContextValue>(() => ({
    hydrated,
    sidebarPinned,
    setSidebarPinned,
  }), [hydrated, sidebarPinned])

  return <UiPreferencesContext.Provider value={value}>{children}</UiPreferencesContext.Provider>
}

export function useUiPreferences() {
  const value = useContext(UiPreferencesContext)
  if (!value) {
    throw new Error("useUiPreferences must be used inside UiPreferencesProvider")
  }
  return value
}
