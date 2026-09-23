// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

"use client"

import { useEffect, useState } from "react"
import { usePathname, useRouter } from "next/navigation"
import { authHeaders, getAuthToken, hasFreshAuthVerification, markAuthVerified, setAuthToken } from "@/lib/auth"

function isPublicRoute(pathname) {
  return pathname === "/login"
    || pathname === "/setup"
    || pathname === "/license"
    || pathname === "/license-types"
    || pathname === "/wiki"
    || pathname.startsWith("/wiki/")
}

export function AuthGate({ children }) {
  const pathname = usePathname()
  const router = useRouter()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let cancelled = false
    const normalizedPath = pathname?.endsWith("/") && pathname.length > 1 ? pathname.slice(0, -1) : pathname
    if (isPublicRoute(normalizedPath || "/")) {
      setReady(true)
      return () => {
        cancelled = true
      }
    }

    const backend = process.env.NEXT_PUBLIC_LIWIRO_BACKEND || "http://127.0.0.1:5000"

    const verify = async () => {
      const token = getAuthToken()
      if (!token) {
        router.replace("/login")
        return
      }

      if (hasFreshAuthVerification(token)) {
        if (!cancelled) {
          setReady(true)
        }
        return
      }

      setReady(false)

      try {
        const controller = new AbortController()
        const timeoutId = window.setTimeout(() => controller.abort(), 4000)
        const response = await fetch(`${backend}/auth/me`, {
          headers: authHeaders(),
          signal: controller.signal,
        }).finally(() => {
          window.clearTimeout(timeoutId)
        })

        if (!response.ok) {
          setAuthToken("")
          router.replace("/login")
          return
        }
        if (!cancelled) {
          markAuthVerified(token)
          setReady(true)
        }
      } catch {
        setAuthToken("")
        router.replace("/login")
      }
    }

    verify()

    return () => {
      cancelled = true
    }
  }, [pathname, router])

  if (!ready) {
    return (
      <div className="app-frame flex min-h-[calc(100dvh-5.1rem)] items-center justify-center py-10 md:py-14">
        <div className="app-card w-full max-w-sm p-9 text-center md:p-11">
          <div className="mx-auto h-10 w-10 animate-spin rounded-full border-2 border-slate-300 border-t-primary" />
          <p className="mt-4 text-sm font-medium text-slate-200">Checking authentication</p>
          <p className="mt-1.5 text-xs text-slate-400">Loading your workspace...</p>
        </div>
      </div>
    )
  }

  return children
}
