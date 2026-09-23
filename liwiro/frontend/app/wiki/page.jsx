'use client'

import Link from "next/link"
import { useCallback, useMemo, useState } from "react"

import { WorkspaceLayout } from "@/components/ide/workspace-layout"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { wikiCategories, wikiGettingStartedPages } from "@/lib/wiki-content"

export default function WikiPage() {
  const [searchTerm, setSearchTerm] = useState("")
  const normalizedTerm = searchTerm.trim().toLowerCase()

  const pageMatches = useCallback((page) => {
    if (!normalizedTerm) {
      return true
    }
    const haystack = [page.title, page.summary, page.category, ...(page.highlights || []), ...((page.tags || []))].join(" ").toLowerCase()
    return haystack.includes(normalizedTerm)
  }, [normalizedTerm])

  const filteredGettingStartedPages = useMemo(() => wikiGettingStartedPages.filter(pageMatches), [pageMatches])
  const filteredCategories = useMemo(() => {
    return wikiCategories
      .map((category) => ({
        ...category,
        pages: category.pages.filter((page) => pageMatches(page)),
      }))
      .filter((category) => category.pages.length > 0)
  }, [pageMatches])

  const noMatches = !!normalizedTerm && filteredCategories.length === 0 && filteredGettingStartedPages.length === 0

  return (
    <WorkspaceLayout
      eyebrow="Documentation / Wiki"
      title="Liwiro Manual"
      description="Guides for building, running, and testing services."
      topActions={
        <div className="flex flex-wrap items-center gap-2">
          <label className="sr-only" htmlFor="wiki-search">
            Search manual
          </label>
          <input
            id="wiki-search"
            type="search"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="Search guides, commands, topics..."
            className="min-w-[220px] flex-1 rounded-full border border-white/15 bg-white/5 px-4 py-2 text-sm text-white placeholder:text-slate-400 focus:border-sky-300 focus:ring focus:ring-sky-300/40"
          />
          <Link href="/login" className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-medium text-slate-100 hover:bg-white/10">
            Open Access Console
          </Link>
        </div>
      }
      systemTitle="Getting Started"
      systemDescription="If you are new, read these pages in order. If not, jump straight to the subsystem catalog."
      editorTitle="Guides"
      editorDescription="Browse the public Liwiro manual."
      systemPanel={
        <div className="space-y-4">
          {filteredGettingStartedPages.map((page) => (
            <Link
              key={page.slug}
              href={`/wiki/${page.slug}`}
              className="block rounded-[1.15rem] border border-white/10 bg-white/5 p-4 hover:bg-white/[0.08]"
            >
              <p className="app-stat-label">{page.category}</p>
              <p className="mt-2 text-xs font-semibold uppercase tracking-[0.18em] text-sky-200">
                Step {page.startOrder || "?"}
              </p>
              <p className="mt-2 text-lg font-semibold text-white">{page.title}</p>
              <p className="mt-2 text-sm text-slate-400">{page.summary}</p>
              <p className="mt-3 text-sm text-slate-300">{page.whenToUse}</p>
              <div className="mt-3 space-y-1 text-sm text-slate-300">
                {page.highlights.slice(0, 2).map((item) => (
                  <p key={`${page.slug}-${item}`}>- {item}</p>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-xs text-sky-200">
                <span>{page.readTime}</span>
                <span>{page.audience}</span>
                <span>{page.subsystem}</span>
              </div>
            </Link>
          ))}

          <Card>
            <CardHeader>
              <CardTitle>How to use this manual</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-slate-300">
              <p>Use the left panel for the fastest onboarding path.</p>
              <p>Use the catalog when you already know the subsystem or artifact you need.</p>
              <p>Search by product terms like Versa, VDB, VQL, LAPIS, auth, or dry-run.</p>
              <p>All wiki pages are readable without signing in.</p>
            </CardContent>
          </Card>
        </div>
      }
      editorPanel={
        <div className="space-y-6">
          {noMatches ? (
            <p className="text-sm text-slate-400">No guides match your search. Try a different keyword.</p>
          ) : null}
          {filteredCategories.map((category) => (
            <section key={category.title} className="space-y-4">
              <div>
                <p className="app-stat-label">{category.title}</p>
                <h2 className="mt-2 text-2xl font-semibold text-white">{category.title}</h2>
              </div>
              <div className="grid gap-4 xl:grid-cols-2">
                {category.pages.map((page) => (
                  <Link
                    key={page.slug}
                    href={`/wiki/${page.slug}`}
                    className="block rounded-[1.2rem] border border-white/10 bg-white/5 p-5 hover:bg-white/[0.08]"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-full border border-sky-400/20 bg-sky-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-sky-200">
                        {page.readTime}
                      </span>
                      <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-300">
                        {page.audience}
                      </span>
                    </div>
                    <p className="mt-4 text-xl font-semibold text-white">{page.title}</p>
                    <p className="mt-2 text-sm leading-7 text-slate-400">{page.summary}</p>
                    <p className="mt-3 text-sm text-slate-300">{page.whenToUse}</p>
                    <div className="mt-3 space-y-1 text-sm text-slate-300">
                      {page.highlights.slice(0, 3).map((item) => (
                        <p key={`${page.slug}-${item}`}>- {item}</p>
                      ))}
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.16em] text-sky-200">
                      {(page.tags || []).slice(0, 3).map((tag) => (
                        <span key={`${page.slug}-${tag}`} className="rounded-full border border-sky-400/20 bg-sky-400/10 px-3 py-1">
                          {tag}
                        </span>
                      ))}
                    </div>
                    <p className="mt-4 text-sm font-medium text-sky-200">Open guide</p>
                  </Link>
                ))}
              </div>
            </section>
          ))}
        </div>
      }
    />
  )
}
