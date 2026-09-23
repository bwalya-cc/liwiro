import {
  BookText,
  ChartColumnBig,
  DatabaseZap,
  Hammer,
  Home,
  KeyRound,
  Sparkles,
  Scale,
  ServerCog,
  Settings2,
  SquareTerminal,
  Users,
  type LucideIcon,
} from "lucide-react"

export type WorkspaceNavItem = {
  title: string
  href: string
  description: string
  icon: LucideIcon
  isPublic?: boolean
  matches?: (pathname: string) => boolean
}

export type WorkspaceNavSection = {
  title: string
  items: WorkspaceNavItem[]
}

export const workspaceNavigation: WorkspaceNavSection[] = [
  {
    title: "Home",
    items: [
      {
        title: "Home",
        href: "/",
        description: "System dashboard and quick actions.",
        icon: Home,
      },
    ],
  },
  {
    title: "Services",
    items: [
      {
        title: "Service Builder",
        href: "/service-builder",
        description: "Compose LAPIS services and API contracts.",
        icon: Hammer,
      },
      {
        title: "Service Manager",
        href: "/services",
        description: "Operate generated services and open editors.",
        icon: ServerCog,
        matches: (pathname) => pathname === "/services" || pathname.startsWith("/services/"),
      },
    ],
  },
  {
    title: "Agents",
    items: [
      {
        title: "Verse Chat",
        href: "/verse-ai",
        description: "Multi-agent chat with specialist agents.",
        icon: Sparkles,
      },
      {
        title: "AI Setup",
        href: "/ai-setup",
        description: "Configure AI providers, models, and API keys.",
        icon: KeyRound,
      },
      {
        title: "Ananse Analytics",
        href: "/ananse-workbench",
        description: "Full-screen analytics and data visualization workbench.",
        icon: ChartColumnBig,
      },
    ],
  },
  {
    title: "VERUN",
    items: [
      {
        title: "VDB Console",
        href: "/vdb-portal",
        description: "Database console and query runner.",
        icon: DatabaseZap,
      },
      {
        title: "Versa Console",
        href: "/vi-portal",
        description: "Versa source workspace and REPL console.",
        icon: SquareTerminal,
      },
    ],
  },
  {
    title: "System",
    items: [
      {
        title: "Settings",
        href: "/settings",
        description: "Platform preferences, users, and runtime defaults.",
        icon: Settings2,
      },
      {
        title: "License",
        href: "/license",
        description: "Open-source license, attribution, and notice text.",
        icon: Scale,
        isPublic: true,
      },
      {
        title: "Credits",
        href: "/credits",
        description: "Acknowledgements for guidance, support, and contribution.",
        icon: Users,
        isPublic: true,
      },
    ],
  },
  {
    title: "Documentation",
    items: [
      {
        title: "Wiki",
        href: "/wiki",
        description: "Platform documentation and configuration reference.",
        icon: BookText,
        isPublic: true,
        matches: (pathname) => pathname === "/wiki" || pathname.startsWith("/wiki/"),
      },
    ],
  },
]

function normalizePathname(pathname?: string) {
  if (!pathname) return "/"
  if (pathname.length > 1 && pathname.endsWith("/")) {
    return pathname.slice(0, -1)
  }
  return pathname
}

export function findWorkspaceNavItem(pathname?: string) {
  const normalized = normalizePathname(pathname)
  for (const section of workspaceNavigation) {
    for (const item of section.items) {
      if (typeof item.matches === "function" && item.matches(normalized)) {
        return { section, item }
      }
      if (item.href === normalized) {
        return { section, item }
      }
    }
  }
  return null
}

export function isNavItemActive(item: WorkspaceNavItem, pathname?: string) {
  const normalized = normalizePathname(pathname)
  if (typeof item.matches === "function") {
    return item.matches(normalized)
  }
  return item.href === normalized
}
