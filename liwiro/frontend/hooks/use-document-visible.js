// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

"use client"

import { useEffect, useState } from "react"

export function useDocumentVisible() {
  const [documentVisible, setDocumentVisible] = useState(() => {
    if (typeof document === "undefined") return true
    return document.visibilityState !== "hidden"
  })

  useEffect(() => {
    if (typeof document === "undefined") return undefined
    const handleVisibilityChange = () => {
      setDocumentVisible(document.visibilityState !== "hidden")
    }
    document.addEventListener("visibilitychange", handleVisibilityChange)
    handleVisibilityChange()
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange)
    }
  }, [])

  return documentVisible
}
