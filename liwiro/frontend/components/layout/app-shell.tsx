"use client"

import Image from "next/image"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { AlertTriangle, LogOut, Menu, ShieldCheck, X } from "lucide-react"
import { useEffect, useMemo, useState, type ReactNode } from "react"

import { AuthGate } from "@/components/auth/auth-gate"
import { findWorkspaceNavItem, isNavItemActive, workspaceNavigation, type WorkspaceNavItem } from "@/components/ide/navigation-config"
import { Button } from "@/components/ui/button"
import VerseAssistantDock from "@/components/verse/verse-assistant-dock"
import { fetchAuthedJson } from "@/lib/authed-json-cache"
import { authHeaders, getAuthRuntimeState, setAuthRuntimeState, setAuthToken } from "@/lib/auth"
import { cn } from "@/lib/utils"

type AppShellProps = {
  children: ReactNode
}

const FULLSCREEN_PUBLIC_ROUTES = new Set(["/login", "/setup"])

function isAuthOptionalRoute(pathname: string) {
  return pathname === "/license"
    || pathname === "/credits"
    || pathname === "/license-types"
    || pathname === "/wiki"
    || pathname.startsWith("/wiki/")
}

function normalizePathname(pathname?: string) {
  if (!pathname) return "/"
  if (pathname.length > 1 && pathname.endsWith("/")) {
    return pathname.slice(0, -1)
  }
  return pathname
}

function describeRoute(pathname: string) {
  const active = findWorkspaceNavItem(pathname)
  if (pathname.startsWith("/services/")) {
    return {
      section: "Services",
      title: "Service Manager",
      description: "Structured and raw editing for a generated service instance.",
    }
  }
  if (pathname === "/login") {
    return {
      section: "Access",
      title: "Login",
      description: "Authenticate into the Liwiro control plane.",
    }
  }
  if (pathname === "/setup") {
    return {
      section: "Access",
      title: "Setup",
      description: "Bootstrap the initial Liwiro admin and VDB runtime connection.",
    }
  }
  if (pathname === "/ai-setup") {
    return {
      section: "Agents",
      title: "AI Setup",
      description: "Configure shared AI providers, models, and credentials.",
    }
  }
  if (active) {
    return {
      section: active.section.title,
      title: active.item.title,
      description: active.item.description,
    }
  }
  return {
    section: "Workspace",
    title: "Liwiro",
    description: "Developer control panel.",
  }
}

function SidebarNavButton({
  item,
  pathname,
  expanded,
  closeMobile,
}: {
  item: WorkspaceNavItem
  pathname: string
  expanded: boolean
  closeMobile?: () => void
}) {
  const active = isNavItemActive(item, pathname)
  const Icon = item.icon

  return (
    <Link
      href={item.href}
      onClick={closeMobile}
      className={cn(
        "ide-nav-link",
        expanded ? "ide-nav-link-expanded" : "ide-nav-link-collapsed",
        active && "ide-nav-link-active",
      )}
      aria-label={item.title}
    >
      <span className="ide-nav-icon-wrap">
        <Icon className="h-4 w-4" />
      </span>
      {expanded ? (
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold">{item.title}</span>
          <span className="block truncate text-xs text-slate-400">{item.description}</span>
        </span>
      ) : null}
    </Link>
  )
}

function SidebarContents({
  pathname,
  expanded,
  onCloseMobile,
}: {
  pathname: string
  expanded: boolean
  onCloseMobile?: () => void
}) {
  return (
    <div className="ide-sidebar-shell">
      <div className="ide-sidebar-brand">
        <Link href="/" onClick={onCloseMobile} className="ide-brand-lockup">
          <span className="ide-brand-glyph">
            <Image src="/liwiro-rabbit-blue.svg" alt="Liwiro rabbit logo" width={28} height={28} className="h-7 w-7 object-contain" />
          </span>
          {expanded ? (
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold text-white">Liwiro</span>
              <span className="block truncate text-[11px] uppercase tracking-[0.2em] text-sky-300/70">
                Developer Console
              </span>
            </span>
          ) : null}
        </Link>
      </div>

      <div className="ide-sidebar-scroll">
        {workspaceNavigation.map((section) => (
          <div key={section.title} className="ide-nav-section">
            {expanded ? <p className="ide-nav-section-label">{section.title}</p> : null}
            <div className="space-y-1.5">
              {section.items.map((item) => (
                <SidebarNavButton
                  key={item.href}
                  item={item}
                  pathname={pathname}
                  expanded={expanded}
                  closeMobile={onCloseMobile}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="ide-sidebar-footer">
        <div className={cn("ide-status-card", !expanded && "ide-status-card-collapsed")}>
          <ShieldCheck className="h-4 w-4 text-sky-300" />
          {expanded ? (
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Workspace</p>
              <p className="truncate text-sm text-slate-100">Structured + raw control surfaces</p>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function WorkspaceTopbar({
  pathname,
  onOpenMobileMenu,
  requiresAuth,
}: {
  pathname: string
  onOpenMobileMenu: () => void
  requiresAuth: boolean
}) {
  const router = useRouter()
  const route = useMemo(() => describeRoute(pathname), [pathname])

  const handleLogout = async () => {
    const backend = process.env.NEXT_PUBLIC_LIWIRO_BACKEND || "http://127.0.0.1:5000"
    try {
      await fetch(`${backend}/auth/logout`, {
        method: "POST",
        headers: authHeaders(),
      })
    } finally {
      setAuthToken("")
      router.replace("/login")
    }
  }

  return (
    <header className="ide-topbar">
      <div className="flex min-w-0 items-start gap-3">
        <button type="button" className="ide-mobile-menu" onClick={onOpenMobileMenu} aria-label="Open navigation">
          <Menu className="h-5 w-5" />
        </button>
        <Link href="/" className="ide-topbar-brand" aria-label="Open Liwiro dashboard">
          <span className="ide-brand-glyph">
            <Image src="/liwiro-rabbit-blue.svg" alt="Liwiro rabbit logo" width={24} height={24} className="h-6 w-6 object-contain" />
          </span>
          <span className="hidden min-w-0 lg:block">
            <span className="block truncate text-sm font-semibold text-white">Liwiro</span>
            <span className="block truncate text-[11px] uppercase tracking-[0.18em] text-sky-300/70">Control Plane</span>
          </span>
        </Link>
        <div className="min-w-0">
          <p className="ide-topbar-kicker">{route.section}</p>
          <h2 className="truncate text-lg font-semibold text-white">{route.title}</h2>
          <p className="truncate text-sm text-slate-400">{route.description}</p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {requiresAuth ? (
          <Button variant="outline" className="ide-topbar-button" onClick={handleLogout}>
            <LogOut className="h-4 w-4" />
            Logout
          </Button>
        ) : (
          <Link href="/login">
            <Button variant="outline" className="ide-topbar-button">
              Login
            </Button>
          </Link>
        )}
      </div>
    </header>
  )
}

export function AppShell({ children }: AppShellProps) {
  const pathname = normalizePathname(usePathname() || "/")
  const backend = process.env.NEXT_PUBLIC_LIWIRO_BACKEND || "http://127.0.0.1:5000"
  const [mobileOpen, setMobileOpen] = useState(false)
  const [hoverExpanded, setHoverExpanded] = useState(false)
  const [runtimeState, setRuntimeState] = useState(() => getAuthRuntimeState())

  const hideShell = FULLSCREEN_PUBLIC_ROUTES.has(pathname)
  const requiresAuth = !isAuthOptionalRoute(pathname)
  const desktopExpanded = hoverExpanded

  useEffect(() => {
    if (!requiresAuth || hideShell) {
      setRuntimeState(null)
      return
    }

    let cancelled = false
    const cachedState = getAuthRuntimeState()
    if (cachedState) {
      setRuntimeState(cachedState)
    }

    fetchAuthedJson(`${backend}/auth/me`, { ttlMs: 5000 })
      .then((payload) => {
        const nextState = {
          vdbRuntimeReady: payload?.vdbRuntimeReady !== false,
          vdbRuntimeError: payload?.vdbRuntimeError || "",
          aiConfigured: payload?.aiConfig?.configured !== false,
          aiDefaultProvider: payload?.aiConfig?.defaultProvider || "",
          canManageAi: Boolean(payload?.aiConfig?.canManage),
        }
        setAuthRuntimeState(nextState)
        if (!cancelled) {
          setRuntimeState({
            ...nextState,
            updatedAt: Date.now(),
          })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRuntimeState(cachedState || null)
        }
      })

    return () => {
      cancelled = true
    }
  }, [backend, hideShell, pathname, requiresAuth])

  useEffect(() => {
    const handleAiConfigUpdated = (event: Event) => {
      const detail = (event as CustomEvent)?.detail || {}
      const aiState = {
        aiConfigured: detail?.configured !== false,
        aiDefaultProvider: String(detail?.defaultProvider || ""),
        canManageAi: Boolean(detail?.canManage),
        updatedAt: Date.now(),
      }
      setAuthRuntimeState({ ...(getAuthRuntimeState() || {}), ...aiState })
      setRuntimeState((current: any) => ({ ...(current || {}), ...aiState }))
    }
    window.addEventListener("liwiro:ai-config-updated", handleAiConfigUpdated)
    return () => window.removeEventListener("liwiro:ai-config-updated", handleAiConfigUpdated)
  }, [])

  if (hideShell) {
    return <main className="min-h-screen">{children}</main>
  }

  return (
    <div className="ide-app-shell">
      <aside
        className={cn("ide-sidebar-desktop", desktopExpanded ? "ide-sidebar-desktop-expanded" : "ide-sidebar-desktop-collapsed")}
        onMouseEnter={() => setHoverExpanded(true)}
        onMouseLeave={() => setHoverExpanded(false)}
      >
        <SidebarContents pathname={pathname} expanded={desktopExpanded} />
      </aside>

      {mobileOpen ? (
        <div className="ide-mobile-overlay">
          <div className="ide-mobile-backdrop" onClick={() => setMobileOpen(false)} />
          <aside className="ide-sidebar-mobile">
            <div className="flex justify-end p-3">
              <button type="button" className="ide-mobile-close" onClick={() => setMobileOpen(false)} aria-label="Close navigation">
                <X className="h-5 w-5" />
              </button>
            </div>
            <SidebarContents pathname={pathname} expanded onCloseMobile={() => setMobileOpen(false)} />
          </aside>
        </div>
      ) : null}

      <div className="ide-app-main">
        <WorkspaceTopbar pathname={pathname} onOpenMobileMenu={() => setMobileOpen(true)} requiresAuth={requiresAuth} />
        {requiresAuth && runtimeState?.vdbRuntimeReady === false ? (
          <div className="px-4 pt-4 md:px-6">
            <div className="flex flex-col gap-3 rounded-[1.2rem] border border-amber-400/25 bg-amber-400/[0.08] px-4 py-3 text-amber-100 md:flex-row md:items-start md:justify-between">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-200" />
                <div className="min-w-0">
                  <p className="text-sm font-semibold">VDB runtime is degraded</p>
                  <p className="mt-1 text-sm text-amber-100/90">
                    {runtimeState?.vdbRuntimeError || "The workspace is running without a ready VDB runtime."}
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Link href="/login">
                  <Button variant="outline" className="h-9 border-amber-200/30 bg-amber-50/10 text-amber-50 hover:bg-amber-50/20">
                    Repair Runtime
                  </Button>
                </Link>
                <Link href="/settings">
                  <Button variant="outline" className="h-9 border-white/10 bg-white/[0.04] text-white hover:bg-white/[0.08]">
                    Open Settings
                  </Button>
                </Link>
              </div>
            </div>
          </div>
        ) : null}
        {requiresAuth && pathname !== "/ai-setup" && runtimeState?.aiConfigured === false ? (
          <div className="px-4 pt-4 md:px-6">
            <div className="flex flex-col gap-3 rounded-[1.2rem] border border-sky-400/25 bg-sky-400/[0.08] px-4 py-3 text-sky-100 md:flex-row md:items-start md:justify-between">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-sky-200" />
                <div className="min-w-0">
                  <p className="text-sm font-semibold">AI provider setup required</p>
                  <p className="mt-1 text-sm text-sky-100/90">
                    {runtimeState?.canManageAi
                      ? "Add an API key for the default provider to enable Verse AI features."
                      : "AI credentials have not been configured. Ask a super admin to complete AI setup."}
                  </p>
                </div>
              </div>
              <Link href="/ai-setup">
                <Button variant="outline" className="h-9 border-sky-200/30 bg-sky-50/10 text-sky-50 hover:bg-sky-50/20">
                  {runtimeState?.canManageAi ? "Configure AI" : "View AI Status"}
                </Button>
              </Link>
            </div>
          </div>
        ) : null}
        <main className="ide-app-content">{requiresAuth ? <AuthGate>{children}</AuthGate> : children}</main>
      </div>
      {requiresAuth ? <VerseAssistantDock pathname={pathname} /> : null}
    </div>
  )
}
