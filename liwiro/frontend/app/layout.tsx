// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import { AppShell } from "@/components/layout/app-shell"
import { UiPreferencesProvider } from "@/components/providers/ui-preferences-provider"
import { Toaster } from "@/components/ui/sonner"
import type { ReactNode } from "react"
import "@xterm/xterm/css/xterm.css"
import "./globals.css"

export const metadata = {
  title: "Liwiro Developer Console",
  description: "IDE-style control panel for Liwiro services, VDB, and platform operations.",
  icons: {
    icon: [
      { url: "/favicon.ico", type: "image/x-icon" },
      { url: "/liwiro-rabbit-blue.svg", type: "image/svg+xml" },
    ],
    apple: "/liwiro-rabbit-blue.svg",
  },
}

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className="min-h-screen bg-background text-foreground antialiased">
        <UiPreferencesProvider>
          <AppShell>{children}</AppShell>
          <Toaster richColors position="top-right" />
        </UiPreferencesProvider>
      </body>
    </html>
  )
}
