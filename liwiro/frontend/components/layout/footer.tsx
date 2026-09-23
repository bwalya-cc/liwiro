// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import Link from "next/link"
import Image from "next/image"
import type { ReactNode } from "react"

type FooterLinkProps = {
  href: string
  children: ReactNode
}

export function Footer() {
  return (
    <footer className="mt-16 border-t border-slate-200/70 bg-[rgba(247,250,255,0.78)] py-12 md:py-14">
      <div className="app-frame">
        <div className="app-card grid grid-cols-1 gap-10 p-7 md:grid-cols-3 md:p-9 lg:p-10">
          <div>
            <p className="app-section-label">Quick Links</p>
            <h3 className="mb-3 mt-3 text-lg font-semibold text-slate-950">Move around the workspace</h3>
            <ul className="space-y-2">
              <FooterLink href="/service-builder">Service Builder</FooterLink>
              <FooterLink href="/services">Services</FooterLink>
              <FooterLink href="/vdb-portal">VDB Console</FooterLink>
              <FooterLink href="/settings">Settings</FooterLink>
            </ul>
          </div>
          <div>
            <p className="app-section-label">Resources</p>
            <h3 className="mb-3 mt-3 text-lg font-semibold text-slate-950">Platform references</h3>
            <ul className="space-y-2">
              <li className="text-slate-600">Versa endpoints (.versa)</li>
              <li className="text-slate-600">LAPIS config import</li>
            </ul>
          </div>
          <div>
            <p className="app-section-label">About</p>
            <div className="mb-4 mt-2 flex items-center space-x-2">
              <Image src="/liwiro-rabbit-blue.svg" alt="Liwiro rabbit logo" width={24} height={24} />
              <span className="text-xl font-bold text-slate-950">Liwiro</span>
            </div>
            <p className="text-slate-600">
              Build, run, and inspect LAPIS-backed services with one consistent workspace.
            </p>
            <p className="mt-3 text-slate-500">&copy; {new Date().getFullYear()} Liwiro. Released under the MIT License.</p>
          </div>
        </div>
        <div className="mb-2 mt-7 text-center">
          <p className="text-sm text-slate-700">
            Open source project by{" "}
            <a
              href="https://www.zulan.io"
              target="_blank"
              rel="noreferrer"
              className="font-semibold text-orange-600 transition-colors hover:text-orange-500 hover:underline"
            >
              Zulan
            </a>
            . Coded in India and Zambia.
          </p>
          <p className="mt-1.5 text-sm text-slate-600">
            Full project details and articles:
            {" "}
            <a
              href="https://www.zulan.io/folio/verun"
              target="_blank"
              rel="noreferrer"
              className="font-medium text-orange-600 transition-colors hover:text-orange-500 hover:underline"
            >
              zulan.io/folio/verun
            </a>
          </p>
        </div>
      </div>
    </footer>
  )
}

function FooterLink({ href, children }: FooterLinkProps) {
  return (
    <li>
      <Link href={href} className="text-slate-600 transition-colors hover:text-primary">
        {children}
      </Link>
    </li>
  )
}
