"use client"

import { useCallback, useMemo } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"

import { MarkdownDocument, extractMarkdownHeadings } from "@/components/ide/markdown-document"
import { WorkspaceLayout } from "@/components/ide/workspace-layout"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { getWikiPageBySlug, wikiPages } from "@/lib/wiki-content"

export default function WikiDetailPage() {
  const params = useParams()
  const slug = String(params?.slug || "")
  const page = getWikiPageBySlug(slug)

  const scrollToAnchor = useCallback((id) => {
    const target = document.getElementById(String(id || ""))
    if (!target) return
    target.scrollIntoView({ behavior: "smooth", block: "start" })
    window.history.replaceState(null, "", `#${id}`)
  }, [])

  const tableOfContents = useMemo(() => {
    if (!page) return []
    return extractMarkdownHeadings(page.content, 1, 3, page.slug)
  }, [page])

  const relatedPages = useMemo(() => {
    if (!page) return []
    return (page.related || [])
      .map((entry) => getWikiPageBySlug(entry))
      .filter(Boolean)
  }, [page])

  const pageIndex = useMemo(() => wikiPages.findIndex((entry) => entry.slug === page?.slug), [page])
  const previousPage = pageIndex > 0 ? wikiPages[pageIndex - 1] : null
  const nextPage = pageIndex >= 0 && pageIndex < wikiPages.length - 1 ? wikiPages[pageIndex + 1] : null

  if (!page) {
    return (
      <WorkspaceLayout
        eyebrow="Documentation / Wiki"
        title="Page Not Found"
        description="The requested wiki page does not exist."
        systemTitle="Next Step"
        systemDescription="Return to the manual catalog."
        editorTitle="Manual"
        editorDescription="Open the manual to browse available guides."
        systemPanel={
          <Card>
            <CardHeader>
              <CardTitle>Open the catalog</CardTitle>
            </CardHeader>
            <CardContent>
              <Link href="/wiki" className="inline-flex rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-100 hover:bg-white/10">
                Back to Wiki
              </Link>
            </CardContent>
          </Card>
        }
        editorPanel={
          <Card>
            <CardHeader>
              <CardTitle>No page at this slug</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-slate-300">
              <p>Open the manual to choose a guide.</p>
            </CardContent>
          </Card>
        }
      />
    )
  }

  return (
    <WorkspaceLayout
      eyebrow={`Documentation / ${page.category}`}
      title={page.title}
      description={page.summary}
      topActions={
        <div className="flex flex-wrap gap-2">
          <Link href="/wiki" className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-medium text-slate-100 hover:bg-white/10">
            Knowledge Home
          </Link>
          <Link href="/login" className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-medium text-slate-100 hover:bg-white/10">
            Open Access Console
          </Link>
        </div>
      }
      systemTitle="Page Guide"
      systemDescription="This panel tells you when to use the page, what it covers, and where to go next."
      editorTitle="Guide"
      editorDescription="Read the guide and use the contents list to jump between sections."
      systemPanel={
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Page Info</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-slate-300">
              <p><span className="font-semibold text-white">Category:</span> {page.category}</p>
              <p><span className="font-semibold text-white">Audience:</span> {page.audience}</p>
              <p><span className="font-semibold text-white">Reading time:</span> {page.readTime}</p>
              <p><span className="font-semibold text-white">Subsystem:</span> {page.subsystem}</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Use This Page When</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-slate-300">
              <p>{page.whenToUse}</p>
              <div className="space-y-1">
                {page.highlights.map((item) => (
                  <p key={`${page.slug}-${item}`}>- {item}</p>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Table of Contents</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {tableOfContents.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => scrollToAnchor(item.id)}
                  className="block w-full rounded-lg px-3 py-2 text-left text-sm text-slate-300 hover:bg-white/5 hover:text-white"
                >
                  <span className="block">{item.text}</span>
                </button>
              ))}
            </CardContent>
          </Card>

          {page.tags?.length ? (
            <Card>
              <CardHeader>
                <CardTitle>Tags</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                {page.tags.map((tag) => (
                  <span key={`${page.slug}-${tag}`} className="rounded-full border border-sky-400/20 bg-sky-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-sky-200">
                    {tag}
                  </span>
                ))}
              </CardContent>
            </Card>
          ) : null}

          {relatedPages.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>Related Pages</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {relatedPages.map((related) => (
                  <Link
                    key={related.slug}
                    href={`/wiki/${related.slug}`}
                    className="block rounded-xl border border-white/10 bg-white/5 px-4 py-3 hover:bg-white/10"
                  >
                    <p className="font-semibold text-white">{related.title}</p>
                    <p className="mt-1 text-sm text-slate-400">{related.summary}</p>
                  </Link>
                ))}
              </CardContent>
            </Card>
          ) : null}
        </div>
      }
      editorPanel={
        <div className="space-y-5">
          <article id={page.slug} className="markdown-article">
            <div className="mb-6 flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-sky-400/20 bg-sky-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-sky-200">
                {page.category}
              </span>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-300">
                {page.readTime}
              </span>
            </div>
            <div className="mb-6 rounded-[1.15rem] border border-white/10 bg-white/5 px-4 py-4 text-sm text-slate-300">
              <p className="font-semibold text-white">Plain-language summary</p>
              <p className="mt-2">{page.whenToUse}</p>
            </div>
            <MarkdownDocument content={page.content} idPrefix={page.slug} />
          </article>

          <Card>
            <CardHeader>
              <CardTitle>Continue Reading</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-3">
              {previousPage ? (
                <Link href={`/wiki/${previousPage.slug}`} className="rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-100 hover:bg-white/10">
                  Previous: {previousPage.title}
                </Link>
              ) : null}
              {nextPage ? (
                <Link href={`/wiki/${nextPage.slug}`} className="rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-100 hover:bg-white/10">
                  Next: {nextPage.title}
                </Link>
              ) : null}
              <Link href="/wiki" className="rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-100 hover:bg-white/10">
                Back to Knowledge Home
              </Link>
            </CardContent>
          </Card>
        </div>
      }
    />
  )
}
