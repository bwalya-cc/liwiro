// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { Menu, X, LogOut, ChevronDown } from "lucide-react"
import Image from "next/image"
import { usePathname, useRouter } from "next/navigation"
import type { ReactNode } from "react"
import { setAuthToken, authHeaders } from "@/lib/auth"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

type NavLinkProps = {
  href: string
  children: ReactNode
  isActive?: boolean
}

type MobileNavLinkProps = {
  href: string
  onClick: () => void
  children: ReactNode
  isActive?: boolean
}

export function Header() {
  const [isMenuOpen, setIsMenuOpen] = useState(false)
  const pathname = usePathname()
  const router = useRouter()
  const isLoginPage = pathname === "/login"

  useEffect(() => {
    setIsMenuOpen(false)
  }, [pathname])

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
    <header className="sticky top-0 z-50 border-b border-slate-200/80 bg-[rgba(247,250,255,0.92)] text-slate-900 shadow-[0_10px_34px_rgba(15,23,42,0.06)] backdrop-blur-xl transition-all duration-300">
      <div className="app-frame">
        <div className="flex h-[5.1rem] items-center justify-between gap-5">
          <Link href="/" className="flex items-center space-x-3 rounded-full px-2 py-1.5 transition-colors hover:bg-white/75">
            <Image src="/liwiro-rabbit-blue.svg" alt="Liwiro rabbit logo" width={24} height={24} />
            <div className="min-w-0">
              <span className="block text-xl font-bold tracking-tight text-slate-950 transition-colors">Liwiro</span>
              <span className="hidden text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500 md:block">
                API Workspace
              </span>
            </div>
          </Link>

          <nav className="hidden items-center gap-1.5 rounded-full border border-slate-200/[0.85] bg-white/90 p-1.5 shadow-[0_10px_24px_rgba(15,23,42,0.05)] backdrop-blur-sm md:flex">
            <NavLink href="/" isActive={pathname === "/"}>Home</NavLink>
            <NavLink href="/service-builder" isActive={pathname === "/service-builder"}>Service Builder</NavLink>
            <NavLink href="/services" isActive={pathname === "/services"}>Services</NavLink>
            <VerunNavMenu pathname={pathname || ""} />
            <NavLink href="/settings" isActive={pathname === "/settings"}>Settings</NavLink>
          </nav>

          <div className="hidden items-center gap-2 md:flex">
            {!isLoginPage && (
              <button
                type="button"
                onClick={handleLogout}
                className="inline-flex items-center gap-1 rounded-full border border-slate-200/[0.85] bg-white/90 px-4 py-2.5 text-sm font-medium text-slate-700 shadow-[0_10px_24px_rgba(15,23,42,0.05)] transition-all duration-200 hover:bg-slate-50 hover:shadow-[0_14px_28px_rgba(15,23,42,0.08)]"
              >
                <LogOut className="h-4 w-4" /> Logout
              </button>
            )}
          </div>

          <button
            className="rounded-full border border-slate-200/[0.85] bg-white/90 p-2.5 text-slate-700 shadow-[0_10px_24px_rgba(15,23,42,0.05)] transition-all duration-200 hover:bg-slate-50 hover:shadow-[0_14px_28px_rgba(15,23,42,0.08)] focus:outline-none md:hidden"
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            aria-label={isMenuOpen ? "Close navigation menu" : "Open navigation menu"}
            aria-expanded={isMenuOpen}
          >
            {isMenuOpen ? <X className="h-6 w-6 transition-transform hover:rotate-90" /> : <Menu className="h-6 w-6 transition-transform hover:scale-110" />}
          </button>
        </div>
      </div>

      {isMenuOpen && (
        <div className="border-t border-slate-200/80 bg-[rgba(247,250,255,0.96)] md:hidden">
          <div className="app-frame pb-4 pt-3">
            <nav className="flex flex-col space-y-2 rounded-[1.4rem] border border-slate-200/[0.85] bg-white/[0.94] p-3 shadow-[0_16px_34px_rgba(15,23,42,0.06)]">
            <MobileNavLink href="/" isActive={pathname === "/"} onClick={() => setIsMenuOpen(false)}>
              Home
            </MobileNavLink>
            <MobileNavLink href="/service-builder" isActive={pathname === "/service-builder"} onClick={() => setIsMenuOpen(false)}>
              Service Builder
            </MobileNavLink>
            <MobileNavLink href="/services" isActive={pathname === "/services"} onClick={() => setIsMenuOpen(false)}>
              Services
            </MobileNavLink>
            <div className="rounded-xl px-3 py-2.5">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Verun</p>
              <div className="mt-2 flex flex-col gap-2">
                <MobileNavLink href="/vdb-portal" isActive={pathname === "/vdb-portal"} onClick={() => setIsMenuOpen(false)}>
                  VDB Console
                </MobileNavLink>
                <MobileNavLink href="/vi-portal" isActive={pathname === "/vi-portal"} onClick={() => setIsMenuOpen(false)}>
                  Versa Console
                </MobileNavLink>
              </div>
            </div>
            <MobileNavLink href="/settings" isActive={pathname === "/settings"} onClick={() => setIsMenuOpen(false)}>
              Settings
            </MobileNavLink>
            {!isLoginPage && (
              <button
                type="button"
                onClick={handleLogout}
                className="rounded-xl px-3 py-2.5 text-left text-base font-medium text-slate-700 hover:bg-slate-100"
              >
                Logout
              </button>
            )}
          </nav>
        </div>
        </div>
      )}
    </header>
  )
}

function VerunNavMenu({ pathname }: { pathname: string }) {
  const isActive = pathname === "/vdb-portal" || pathname === "/vi-portal"

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={`inline-flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200 ${
          isActive
            ? "bg-primary text-primary-foreground shadow-[0_12px_24px_rgba(15,118,110,0.22)]"
            : "text-slate-700 hover:bg-slate-100 hover:text-slate-900"
        }`}
      >
        Verun <ChevronDown className="h-4 w-4" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="center" className="w-48 rounded-xl border-slate-200/90 bg-white/[0.96] p-1.5 shadow-[0_16px_32px_rgba(15,23,42,0.08)]">
        <DropdownMenuItem asChild className="rounded-lg">
          <Link href="/vdb-portal">VDB Console</Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild className="rounded-lg">
          <Link href="/vi-portal">Versa Console</Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function NavLink({ href, children, isActive = false }: NavLinkProps) {
  return (
    <Link
      href={href}
      className={`rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200 ${
        isActive ? "bg-primary text-primary-foreground shadow-[0_12px_24px_rgba(15,118,110,0.22)]" : "text-slate-700 hover:bg-slate-100 hover:text-slate-900"
      }`}
    >
      {children}
    </Link>
  )
}

function MobileNavLink({ href, onClick, children, isActive = false }: MobileNavLinkProps) {
  return (
    <Link
      href={href}
      className={`rounded-md px-3 py-2 text-base font-medium transition-all duration-200 hover:shadow-sm ${
        isActive
          ? "bg-primary text-primary-foreground"
          : "text-slate-700 hover:bg-slate-100"
      }`}
      onClick={onClick}
    >
      {children}
    </Link>
  )
}
