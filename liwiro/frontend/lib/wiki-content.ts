import { userManual } from "./user-manual"

export type WikiPage = {
  slug: string
  title: string
  summary: string
  category: string
  audience: string
  readTime: string
  whenToUse: string
  highlights: string[]
  gettingStarted?: boolean
  startOrder?: number
  related?: string[]
  order: number
  content: string
  tags: string[]
  subsystem: string
}

function titleCase(value: string) {
  return String(value || "")
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((token) => token.slice(0, 1).toUpperCase() + token.slice(1))
    .join(" ")
}

const gettingStartedOrder = [
  "getting-started", "authentication", "service-builder", "service-manager",
]

const legacySlugMap: Record<string, string> = {
  "platform-foundations": "getting-started",
  "auth-and-access": "authentication",
  "service-builder-manual": "service-builder",
  "service-manager-manual": "service-manager",
  "security-and-auth": "authentication",
}

export const wikiPages: WikiPage[] = userManual.map((doc) => {
  const startOrder = gettingStartedOrder.indexOf(doc.slug)
  const content = doc.content
  return {
    slug: doc.slug,
    title: doc.title,
    summary: doc.summary,
    category: doc.category || titleCase(doc.subsystem),
    audience: doc.audience,
    readTime: `${Math.max(6, Math.ceil(content.split(/\s+/).filter(Boolean).length / 180))} min`,
    whenToUse: doc.summary,
    highlights: [],
    gettingStarted: startOrder >= 0,
    startOrder: startOrder >= 0 ? startOrder + 1 : undefined,
    related: doc.related || [],
    order: doc.order,
    content,
    tags: doc.tags || [],
    subsystem: doc.subsystem,
  }
})

export const wikiGettingStartedPages = wikiPages.filter((page) => page.gettingStarted)

export const wikiCategories = Object.values(
  wikiPages.reduce<Record<string, { title: string; pages: WikiPage[] }>>((accumulator, page) => {
    if (!accumulator[page.category]) {
      accumulator[page.category] = { title: page.category, pages: [] }
    }
    accumulator[page.category].pages.push(page)
    accumulator[page.category].pages.sort((left, right) => left.order - right.order)
    return accumulator
  }, {}),
).sort((left, right) => left.title.localeCompare(right.title))

export function getWikiPageBySlug(slug: string) {
  const resolvedSlug = legacySlugMap[String(slug || "").trim()] || String(slug || "").trim()
  return wikiPages.find((page) => page.slug === resolvedSlug) || null
}
