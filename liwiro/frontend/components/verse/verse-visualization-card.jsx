"use client"

import Link from "next/link"
import { ArrowUpRight, BarChart3 } from "lucide-react"

import AnanseChartView from "@/components/verse/ananse-chart-view"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

function valueText(value) {
  if (value === null || value === undefined || value === "") return "—"
  return String(value)
}

export default function VerseVisualizationCard({ visualization }) {
  const chart = visualization?.chart || {}
  const findings = Array.isArray(visualization?.findings) ? visualization.findings : []
  const metrics = Array.isArray(visualization?.metrics) ? visualization.metrics : []
  const alternateChartTypes = Array.isArray(visualization?.alternateChartTypes) ? visualization.alternateChartTypes : []
  const dataset = visualization?.dataset && typeof visualization.dataset === "object" ? visualization.dataset : {}
  const datasetId = String(visualization?.datasetId || dataset?.id || dataset?.datasetId || "").trim()
  const tablePreview = Array.isArray(visualization?.tablePreview) ? visualization.tablePreview : []
  const uncertaintyNotes = Array.isArray(visualization?.uncertaintyNotes) ? visualization.uncertaintyNotes : []
  const intent = String(visualization?.intent || chart?.intent || "").trim()
  const confidence = String(visualization?.confidence || chart?.confidence || "").trim()

  if (!visualization || (!chart?.data?.length && !metrics.length && !tablePreview.length && !(visualization?.series || []).length)) {
    return null
  }

  return (
    <div className="mt-3 overflow-hidden rounded-[1.3rem] border border-white/10 bg-black/20">
      <div className="border-b border-white/10 px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white">{visualization?.title || "Analysis snapshot"}</p>
            {visualization?.description ? <p className="mt-1 text-xs text-slate-400">{visualization.description}</p> : null}
          </div>
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-2xl border border-white/10 bg-cyan-400/10 text-cyan-200">
            <BarChart3 className="h-4 w-4" />
          </span>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          {dataset?.rowCount ? <Badge variant="secondary">{dataset.rowCount} rows</Badge> : null}
          {dataset?.columnCount ? <Badge variant="secondary">{dataset.columnCount} columns</Badge> : null}
          {visualization?.type ? <Badge variant="secondary">{String(visualization.type).replace(/-/g, " ")}</Badge> : null}
          {intent ? <Badge variant="outline" className="border-white/10 bg-transparent text-slate-300">{intent}</Badge> : null}
          {confidence ? <Badge variant="outline" className="border-white/10 bg-transparent text-slate-300">{confidence} confidence</Badge> : null}
          {alternateChartTypes.slice(0, 4).map((item) => (
            <Badge key={item} variant="outline" className="border-white/10 bg-transparent text-slate-300">
              {String(item).replace(/-/g, " ")}
            </Badge>
          ))}
        </div>
      </div>

      <div className="space-y-4 px-4 py-4">
        <AnanseChartView chart={chart} metrics={metrics} tablePreview={tablePreview} compact />

        {metrics.length ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {metrics.slice(0, 4).map((item, index) => (
              <div key={`${item?.label || "metric"}-${index}`} className="rounded-2xl border border-white/10 bg-white/[0.04] px-3 py-3">
                <p className="text-[11px] uppercase tracking-[0.18em] text-slate-400">{item?.label || "Metric"}</p>
                <p className="mt-1 text-lg font-semibold text-white">{valueText(item?.value)}</p>
              </div>
            ))}
          </div>
        ) : null}

        {findings.length ? (
          <div className="space-y-2">
            {findings.slice(0, 3).map((item, index) => (
              <div key={`${item?.title || "finding"}-${index}`} className="rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-3">
                <p className="text-sm font-semibold text-white">{item?.title || "Finding"}</p>
                <p className="mt-1 text-xs leading-6 text-slate-300">{item?.description || ""}</p>
              </div>
            ))}
          </div>
        ) : null}

        {uncertaintyNotes.length ? (
          <div className="rounded-2xl border border-amber-300/10 bg-amber-400/[0.06] px-3 py-3">
            <p className="text-sm font-semibold text-amber-100">Uncertainty notes</p>
            <div className="mt-2 space-y-1">
              {uncertaintyNotes.slice(0, 2).map((item, index) => (
                <p key={`uncertainty-${index}`} className="text-xs text-amber-50/85">{item}</p>
              ))}
            </div>
          </div>
        ) : null}

        {datasetId ? (
          <div className="flex justify-end">
            <Link href={`/ananse-workbench?dataset=${encodeURIComponent(datasetId)}`}>
              <Button type="button" size="sm" variant="secondary" className="rounded-full">
                <ArrowUpRight className="mr-2 h-4 w-4" />
                Open in Ananse
              </Button>
            </Link>
          </div>
        ) : null}
      </div>
    </div>
  )
}
