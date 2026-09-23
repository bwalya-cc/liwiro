"use client"

import { BarChart3, Filter, Plus, RefreshCw, Sparkles, TableProperties } from "lucide-react"
import { useRouter, useSearchParams } from "next/navigation"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"

import AnanseChartView from "@/components/verse/ananse-chart-view"
import { WorkspaceLayout } from "@/components/ide/workspace-layout"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { authHeaders } from "@/lib/auth"
import { activatePendingVerseAction, consumePendingVerseAction } from "@/lib/verse-actions"

function emptyFilter() {
  return { column: "", op: "eq", value: "" }
}

const NONE_VALUE = "__none__"

function datasetLabel(dataset) {
  return String(dataset?.title || "Dataset")
}

export default function AnanseWorkbenchPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const backend = process.env.NEXT_PUBLIC_LIWIRO_BACKEND || "http://127.0.0.1:5000"

  const [loading, setLoading] = useState(true)
  const [datasets, setDatasets] = useState([])
  const [selectedDatasetId, setSelectedDatasetId] = useState("")
  const [selectedDataset, setSelectedDataset] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [busy, setBusy] = useState(false)
  const [filters, setFilters] = useState([emptyFilter()])
  const [controlState, setControlState] = useState({
    preset: "",
    chartType: "",
    dimension: "",
    metric: "",
    secondaryMetric: "",
    compareBy: "",
    aggregation: "sum",
    limit: 12,
  })

  const analysisInputs = useRef({ filters, controlState })
  analysisInputs.current = { filters, controlState }

  const availableColumns = useMemo(() => (Array.isArray(selectedDataset?.columns) ? selectedDataset.columns : []), [selectedDataset?.columns])
  const dimensionOptions = useMemo(
    () => availableColumns.filter((column) => ["string", "boolean", "datetime"].includes(String(column?.type || ""))).map((column) => column.key),
    [availableColumns]
  )
  const metricOptions = useMemo(
    () => availableColumns.filter((column) => String(column?.type || "") === "number").map((column) => column.key),
    [availableColumns]
  )
  const filterColumn = useCallback((filter) => (
    availableColumns.find((column) => column.key === filter?.column) || null
  ), [availableColumns])
  const filterOperators = useCallback((filter) => {
    const type = String(filterColumn(filter)?.type || "")
    if (type === "number") return ["eq", "gte", "lte"]
    if (type === "boolean") return ["eq"]
    return ["eq", "contains"]
  }, [filterColumn])
  const chartOptions = useMemo(
    () => Array.isArray(analysis?.controls?.chartTypes) && analysis.controls.chartTypes.length ? analysis.controls.chartTypes : ["table", "metric-list"],
    [analysis?.controls?.chartTypes]
  )
  const presetOptions = useMemo(
    () => Array.isArray(analysis?.controls?.presets) ? analysis.controls.presets : [],
    [analysis?.controls?.presets]
  )
  const analysisSummary = analysis?.dataset?.analysisSummary || selectedDataset?.summary || {}
  const qualityColumns = Array.isArray(analysisSummary?.quality?.columnQuality) ? analysisSummary.quality.columnQuality : []

  const loadDatasets = useCallback(async () => {
    const res = await fetch(`${backend}/platform/verse/datasets`, { headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data?.error || "Failed to load Ananse datasets")
    const items = Array.isArray(data?.datasets) ? data.datasets : []
    setDatasets(items)
    return items
  }, [backend])

  const loadDataset = useCallback(async (datasetId) => {
    if (!datasetId) {
      setSelectedDataset(null)
      setAnalysis(null)
      return null
    }
    const res = await fetch(`${backend}/platform/verse/datasets/${encodeURIComponent(datasetId)}`, { headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data?.error || "Failed to load dataset")
    setSelectedDataset(data?.dataset || null)
    return data?.dataset || null
  }, [backend])

  const analyzeDataset = useCallback(async (datasetId, overrides = {}) => {
    if (!datasetId) return null
    setBusy(true)
    const { filters, controlState } = analysisInputs.current
    try {
      const nextFilters = (overrides.filters || filters).filter((item) => {
        if (!item?.column || item?.value === undefined || item?.value === null) return false
        return String(item.value).trim() !== ""
      })
      const payload = {
        preset: overrides.preset ?? controlState.preset,
        chartType: overrides.chartType ?? controlState.chartType,
        dimension: overrides.dimension ?? controlState.dimension,
        metric: overrides.metric ?? controlState.metric,
        secondaryMetric: overrides.secondaryMetric ?? controlState.secondaryMetric,
        compareBy: overrides.compareBy ?? controlState.compareBy,
        aggregation: overrides.aggregation ?? controlState.aggregation,
        limit: Number(overrides.limit ?? controlState.limit ?? 12) || 12,
        filters: nextFilters,
      }
      const res = await fetch(`${backend}/platform/verse/datasets/${encodeURIComponent(datasetId)}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(payload),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || "Failed to analyze dataset")
      const nextAnalysis = data?.analysis || null
      setAnalysis(nextAnalysis)
      const selected = nextAnalysis?.controls?.selected || {}
      setControlState({
        preset: String(selected.preset || ""),
        chartType: String(selected.chartType || ""),
        dimension: String(selected.dimension || ""),
        metric: String(selected.metric || ""),
        secondaryMetric: String(selected.secondaryMetric || ""),
        compareBy: String(selected.compareBy || ""),
        aggregation: String(selected.aggregation || "sum"),
        limit: Number(selected.limit || 12) || 12,
      })
      setFilters(Array.isArray(selected.filters) && selected.filters.length ? selected.filters : [emptyFilter()])
      return nextAnalysis
    } finally {
      setBusy(false)
    }
  }, [backend])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const items = await loadDatasets()
        if (cancelled) return
        const fromQuery = String(searchParams.get("dataset") || "").trim()
        const nextId = fromQuery || String((items[0] || {}).id || (items[0] || {}).datasetId || "")
        if (nextId) {
          setSelectedDatasetId(nextId)
        }
      } catch (error) {
        if (!cancelled) toast.error(error?.message || "Failed to load Ananse workbench")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [loadDatasets, searchParams])

  useEffect(() => {
    if (!selectedDatasetId) return
    let cancelled = false
    loadDataset(selectedDatasetId)
      .then((dataset) => {
        if (cancelled || !dataset) return
        return analyzeDataset(selectedDatasetId, { preset: "", chartType: "", dimension: "", metric: "", secondaryMetric: "", compareBy: "", filters: [] })
      })
      .catch((error) => {
        if (!cancelled) toast.error(error?.message || "Failed to load the selected dataset")
      })
    return () => {
      cancelled = true
    }
  }, [analyzeDataset, loadDataset, selectedDatasetId])

  useEffect(() => {
    const handleVerseContextRequest = (event) => {
      const respond = event?.detail?.respond
      if (typeof respond !== "function") return
      respond({
        pageKind: "ananse-workbench",
        screen: "ananse workbench",
        pathname: "/ananse-workbench",
        selectedDatasetId,
        selection: { kind: "dataset", id: selectedDatasetId },
        datasetTitle: selectedDataset?.title || "",
        analysisTitle: analysis?.title || "",
        chartType: analysis?.chart?.chartType || controlState.chartType || "",
      })
    }

    const handleVerseApply = (event) => {
      const artifact = event?.detail?.artifact
      const respond = event?.detail?.respond
      if (artifact?.kind !== "ananse-analysis" || typeof respond !== "function") return
      try {
        const nextDatasetId = String(artifact?.datasetId || artifact?.analysis?.datasetId || "").trim()
        if (nextDatasetId) {
          setSelectedDatasetId(nextDatasetId)
          router.replace(`/ananse-workbench?dataset=${encodeURIComponent(nextDatasetId)}`)
        }
        if (artifact?.analysis && typeof artifact.analysis === "object") {
          setAnalysis(artifact.analysis)
        }
        respond({ ok: true, message: "Opened the analysis in Ananse." })
      } catch (error) {
        respond({ ok: false, message: error?.message || "Failed to open the Ananse analysis." })
      }
    }

    const handleVerseExecute = (event) => {
      const artifact = event?.detail?.artifact
      const respond = event?.detail?.respond
      if (artifact?.kind !== "ananse-analysis" || typeof respond !== "function") return
      const nextDatasetId = String(artifact?.datasetId || artifact?.analysis?.datasetId || selectedDatasetId || "").trim()
      if (!nextDatasetId) {
        respond({ ok: false, message: "No dataset was attached to refresh." })
        return
      }
      analyzeDataset(nextDatasetId, {})
        .then(() => respond({ ok: true, message: "Refreshed the Ananse analysis." }))
        .catch((error) => respond({ ok: false, message: error?.message || "Failed to refresh the analysis." }))
    }

    window.addEventListener("liwiro:verse-assistant-request-context", handleVerseContextRequest)
    window.addEventListener("liwiro:verse-assistant-apply", handleVerseApply)
    window.addEventListener("liwiro:verse-assistant-execute", handleVerseExecute)

    const pendingAction = consumePendingVerseAction("/ananse-workbench")
    if (pendingAction?.artifact) {
      activatePendingVerseAction({
        pathname: "/ananse-workbench",
        pendingAction,
        onResult: (payload) => {
          if (payload?.ok) toast.success(payload.message || "Verse action completed.")
          else toast.error(payload?.message || "Verse action failed.")
        },
      })
    }

    return () => {
      window.removeEventListener("liwiro:verse-assistant-request-context", handleVerseContextRequest)
      window.removeEventListener("liwiro:verse-assistant-apply", handleVerseApply)
      window.removeEventListener("liwiro:verse-assistant-execute", handleVerseExecute)
    }
  }, [analysis?.chart?.chartType, analysis?.title, analyzeDataset, controlState.chartType, router, selectedDataset?.title, selectedDatasetId])

  const refreshCurrentAnalysis = async () => {
    if (!selectedDatasetId) return
    try {
      await loadDatasets()
      await loadDataset(selectedDatasetId)
      await analyzeDataset(selectedDatasetId, {})
      toast.success("Refreshed the analysis.")
    } catch (error) {
      toast.error(error?.message || "Failed to refresh the analysis")
    }
  }

  useEffect(() => {
    if (!selectedDatasetId) return
    let active = true
    let running = false
    const timer = setInterval(async () => {
      if (!active || running || document.hidden) return
      running = true
      try {
        await loadDatasets()
        if (active) await loadDataset(selectedDatasetId)
        if (active) await analyzeDataset(selectedDatasetId)
      } catch (error) {
        if (active) toast.error(error?.message || "Could not refresh platform data")
      } finally { running = false }
    }, 30000)
    return () => { active = false; clearInterval(timer) }
  }, [selectedDatasetId, loadDatasets, loadDataset, analyzeDataset])

  const systemPanel = (
    <div className="space-y-5">
      <Card>
        <CardHeader><CardTitle>Live platform intelligence</CardTitle></CardHeader>
        <CardContent className="space-y-3 text-sm text-slate-300">
          <p>Ananse collects your platform actions, service status, request volume, errors and response times automatically.</p>
          <p>Charts refresh every 30 seconds. Ananse uses these observations in conversations and proactive reviews.</p>
          <p className="text-xs text-slate-400">Service traffic appears as requests arrive. Access follows your service permissions.</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Datasets</CardTitle>
          <p className="text-sm text-slate-400">Live sources available to your account.</p>
        </CardHeader>
        <CardContent className="space-y-3">
          {datasets.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-white/10 px-4 py-8 text-center text-sm text-slate-400">
              Waiting for platform observations. Use services and platform actions to populate these views.
            </div>
          ) : (
            datasets.map((dataset) => {
              const active = String(dataset?.id || dataset?.datasetId || "") === selectedDatasetId
              return (
                <button
                  key={String(dataset?.id || dataset?.datasetId || "")}
                  type="button"
                  onClick={() => {
                    const nextId = String(dataset?.id || dataset?.datasetId || "")
                    setSelectedDatasetId(nextId)
                    router.replace(`/ananse-workbench?dataset=${encodeURIComponent(nextId)}`)
                  }}
                  className={`w-full rounded-2xl border px-4 py-3 text-left transition ${active ? "border-cyan-300/40 bg-cyan-400/10" : "border-white/10 bg-white/[0.03] hover:bg-white/[0.06]"}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-white">{datasetLabel(dataset)}</p>
                      <p className="mt-1 text-xs text-slate-400">
                        {dataset?.rowCount || 0} rows • {dataset?.columnCount || 0} columns
                      </p>
                    </div>
                    <Badge variant="secondary">{dataset?.source?.sourceType || "dataset"}</Badge>
                  </div>
                </button>
              )
            })
          )}
        </CardContent>
      </Card>
    </div>
  )

  const editorPanel = (
    <div className="space-y-5">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <div>
            <CardTitle>{analysis?.title || selectedDataset?.title || "Ananse workbench"}</CardTitle>
            <p className="text-sm text-slate-400">
              {analysis?.description || "Switch visualization methods, adjust dimensions and metrics, and compare the same dataset in multiple ways."}
            </p>
          </div>
          <Button type="button" variant="outline" onClick={refreshCurrentAnalysis} disabled={busy || !selectedDatasetId}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {selectedDataset ? (
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="secondary">{selectedDataset?.rowCount || 0} rows</Badge>
              <Badge variant="secondary">{selectedDataset?.columnCount || 0} columns</Badge>
              {selectedDataset?.source?.format ? <Badge variant="secondary">{selectedDataset.source.format}</Badge> : null}
              {selectedDataset?.source?.archivedName ? <Badge variant="outline">{selectedDataset.source.archivedName}</Badge> : null}
            </div>
          ) : null}

          <div className="grid gap-4 xl:grid-cols-7">
            <div className="grid gap-2">
              <Label>Guided view</Label>
              <Select
                value={controlState.preset || NONE_VALUE}
                onValueChange={(value) => {
                  const presetId = value === NONE_VALUE ? "" : value
                  const preset = presetOptions.find((item) => item.id === presetId)
                  setControlState((current) => ({
                    ...current,
                    preset: presetId,
                    chartType: preset?.chartType || current.chartType,
                  }))
                }}
              >
                <SelectTrigger><SelectValue placeholder="Choose a preset" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE_VALUE}>Manual</SelectItem>
                  {presetOptions.map((item) => (
                    <SelectItem key={item.id} value={item.id}>{item.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>Chart</Label>
              <Select value={controlState.chartType || NONE_VALUE} onValueChange={(value) => setControlState((current) => ({ ...current, chartType: value === NONE_VALUE ? "" : value }))}>
                <SelectTrigger><SelectValue placeholder="Chart type" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE_VALUE}>Auto</SelectItem>
                  {chartOptions.map((item) => (
                    <SelectItem key={item} value={item}>{String(item).replace(/-/g, " ")}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>Dimension</Label>
              <Select value={controlState.dimension || NONE_VALUE} onValueChange={(value) => setControlState((current) => ({ ...current, dimension: value === NONE_VALUE ? "" : value }))}>
                <SelectTrigger><SelectValue placeholder="Dimension" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE_VALUE}>None</SelectItem>
                  {dimensionOptions.map((item) => (
                    <SelectItem key={item} value={item}>{item}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>Metric</Label>
              <Select value={controlState.metric || NONE_VALUE} onValueChange={(value) => setControlState((current) => ({ ...current, metric: value === NONE_VALUE ? "" : value }))}>
                <SelectTrigger><SelectValue placeholder="Metric" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE_VALUE}>None</SelectItem>
                  {metricOptions.map((item) => (
                    <SelectItem key={item} value={item}>{item}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>Compare by</Label>
              <Select value={controlState.compareBy || NONE_VALUE} onValueChange={(value) => setControlState((current) => ({ ...current, compareBy: value === NONE_VALUE ? "" : value }))}>
                <SelectTrigger><SelectValue placeholder="Series split" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE_VALUE}>None</SelectItem>
                  {dimensionOptions.filter((item) => item !== controlState.dimension).map((item) => (
                    <SelectItem key={item} value={item}>{item}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>Aggregation</Label>
              <Select value={controlState.aggregation || "sum"} onValueChange={(value) => setControlState((current) => ({ ...current, aggregation: value }))}>
                <SelectTrigger><SelectValue placeholder="Aggregation" /></SelectTrigger>
                <SelectContent>
                  {["sum", "avg", "count", "min", "max"].map((item) => (
                    <SelectItem key={item} value={item}>{item}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>Limit</Label>
              <Input type="number" min={3} max={50} value={String(controlState.limit || 12)} onChange={(event) => setControlState((current) => ({ ...current, limit: Number(event.target.value || 12) || 12 }))} />
            </div>
          </div>

          <div className="space-y-3 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-white">Filters</p>
                <p className="text-xs text-slate-400">Apply equality, text, or numeric range filters before charting.</p>
              </div>
              <Button type="button" variant="ghost" size="sm" onClick={() => setFilters((current) => [...current, emptyFilter()])}>
                <Plus className="mr-2 h-4 w-4" />
                Add filter
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={() => setFilters([emptyFilter()])} disabled={!filters.some((item) => item.column || String(item.value ?? "").trim())}>
                Clear filters
              </Button>
            </div>
            {filters.map((filter, index) => (
              <div key={`filter-${index}`} className="grid gap-3 md:grid-cols-[1.1fr_0.8fr_1.2fr_auto]">
                <Select value={filter.column || NONE_VALUE} onValueChange={(value) => setFilters((current) => current.map((item, itemIndex) => {
                  if (itemIndex !== index) return item
                  const column = value === NONE_VALUE ? "" : value
                  const type = String(availableColumns.find((candidate) => candidate.key === column)?.type || "")
                  const allowed = type === "number" ? ["eq", "gte", "lte"] : (type === "boolean" ? ["eq"] : ["eq", "contains"])
                  return { ...item, column, op: allowed.includes(item.op) ? item.op : "eq", value: type === "boolean" ? "" : item.value }
                }))}>
                  <SelectTrigger><SelectValue placeholder="Column" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE_VALUE}>None</SelectItem>
                    {availableColumns.map((column) => (
                      <SelectItem key={column.key} value={column.key}>{column.key}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={filter.op || "eq"} onValueChange={(value) => setFilters((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, op: value } : item))}>
                  <SelectTrigger><SelectValue placeholder="Operator" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="eq">equals</SelectItem>
                    {filterOperators(filter).includes("contains") ? <SelectItem value="contains">contains</SelectItem> : null}
                    {filterOperators(filter).includes("gte") ? <SelectItem value="gte">≥</SelectItem> : null}
                    {filterOperators(filter).includes("lte") ? <SelectItem value="lte">≤</SelectItem> : null}
                  </SelectContent>
                </Select>
                {String(filterColumn(filter)?.type || "") === "boolean" ? (
                  <Select value={String(filter.value ?? "")} onValueChange={(value) => setFilters((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, value } : item))}>
                    <SelectTrigger><SelectValue placeholder="Value" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="true">true</SelectItem>
                      <SelectItem value="false">false</SelectItem>
                    </SelectContent>
                  </Select>
                ) : (
                  <Input
                    type={String(filterColumn(filter)?.type || "") === "number" ? "number" : "text"}
                    value={filter.value ?? ""}
                    onChange={(event) => setFilters((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, value: event.target.value } : item))}
                    placeholder="Value"
                  />
                )}
                <Button type="button" variant="ghost" size="icon" onClick={() => setFilters((current) => current.length <= 1 ? [emptyFilter()] : current.filter((_, itemIndex) => itemIndex !== index))}>
                  <Filter className="h-4 w-4" />
                </Button>
              </div>
            ))}
            <Button type="button" onClick={() => analyzeDataset(selectedDatasetId, { filters, preset: controlState.preset })} disabled={busy || !selectedDatasetId}>
              <BarChart3 className="mr-2 h-4 w-4" />
              {busy ? "Updating…" : "Apply analysis view"}
            </Button>
          </div>

          {analysis ? (
            <div className="space-y-4">
              <div className="grid gap-4 lg:grid-cols-3 xl:grid-cols-6">
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                  <p className="app-stat-label">Rows</p>
                  <p className="mt-2 text-2xl font-semibold text-white">{analysisSummary?.metrics?.rows ?? selectedDataset?.rowCount ?? 0}</p>
                  <p className="mt-1 text-sm text-slate-400">Rows in the current analysis view</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                  <p className="app-stat-label">Missing Rate</p>
                  <p className="mt-2 text-2xl font-semibold text-white">
                    {analysisSummary?.metrics?.missingRate !== undefined ? `${Math.round(Number(analysisSummary.metrics.missingRate || 0) * 100)}%` : "—"}
                  </p>
                  <p className="mt-1 text-sm text-slate-400">Cells without usable values</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                  <p className="app-stat-label">Time Series</p>
                  <p className="mt-2 text-2xl font-semibold text-white">{analysisSummary?.hasTimeSeries ? "Detected" : "Not detected"}</p>
                  <p className="mt-1 text-sm text-slate-400">Trend and anomaly chart readiness</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                  <p className="app-stat-label">Confidence</p>
                  <p className="mt-2 text-2xl font-semibold text-white">{analysis?.confidence || analysis?.chart?.confidence || "Medium"}</p>
                  <p className="mt-1 text-sm text-slate-400">{analysis?.intent ? `${analysis.intent} analysis` : "Analyst confidence signal"}</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                  <p className="app-stat-label">Duplicate Rows</p>
                  <p className="mt-2 text-2xl font-semibold text-white">{analysisSummary?.metrics?.duplicateRows ?? "—"}</p>
                  <p className="mt-1 text-sm text-slate-400">Exact repeated records</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                  <p className="app-stat-label">Complete Rows</p>
                  <p className="mt-2 text-2xl font-semibold text-white">{analysisSummary?.metrics?.completeRows ?? "—"}</p>
                  <p className="mt-1 text-sm text-slate-400">Rows with no missing values</p>
                </div>
              </div>

              {qualityColumns.length ? (
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-white">Data quality profile</p>
                      <p className="mt-1 text-sm text-slate-400">Columns with the most missing values are shown first.</p>
                    </div>
                    <Badge variant="outline">{Math.round(Number(analysisSummary?.metrics?.missingRate || 0) * 100)}% missing cells</Badge>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {qualityColumns.slice(0, 6).map((column) => (
                      <Badge key={column.key} variant="secondary" className="font-normal">
                        {column.key}: {Math.round(Number(column.missingRate || 0) * 100)}% missing • {column.distinctCount} distinct
                      </Badge>
                    ))}
                  </div>
                </div>
              ) : null}

              <AnanseChartView chart={analysis?.chart || {}} metrics={analysis?.metrics || []} tablePreview={analysis?.tablePreview || []} />

              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(18rem,0.8fr)]">
                <div className="overflow-hidden rounded-2xl border border-white/10">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        {(analysis?.chart?.tableColumns?.length ? analysis.chart.tableColumns : Object.keys((analysis?.tablePreview || [])[0] || {})).map((column) => (
                          <TableHead key={column}>{column}</TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(analysis?.tablePreview || []).slice(0, 12).map((row, rowIndex) => (
                        <TableRow key={`preview-${rowIndex}`}>
                          {Object.keys(row || {}).map((column) => (
                            <TableCell key={`${rowIndex}-${column}`}>{String(row?.[column] ?? "—")}</TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                <div className="space-y-3">
                  {(analysis?.insightNotes || []).length ? (
                    <div className="rounded-2xl border border-cyan-300/10 bg-cyan-400/[0.05] p-4">
                      <div className="flex items-center gap-2">
                        <Sparkles className="h-4 w-4 text-cyan-200" />
                        <p className="text-sm font-semibold text-white">Analyst context</p>
                      </div>
                      <div className="mt-3 space-y-2">
                        {(analysis?.insightNotes || []).slice(0, 3).map((item, index) => (
                          <p key={`insight-${index}`} className="text-sm text-slate-200">{item}</p>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  {(analysis?.findings || []).map((item, index) => (
                    <div key={`${item?.title || "finding"}-${index}`} className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                      <p className="text-sm font-semibold text-white">{item?.title || "Finding"}</p>
                      <p className="mt-1 text-sm leading-6 text-slate-300">{item?.description || ""}</p>
                    </div>
                  ))}
                  {(analysis?.detectedPatterns || []).length ? (
                    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                      <p className="text-sm font-semibold text-white">Detected patterns</p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {(analysis?.detectedPatterns || []).map((item, index) => (
                          <Badge key={`pattern-${index}`} variant="outline" className="border-white/10 text-slate-300">
                            {`${item?.label || item?.type || "pattern"}: ${item?.value ?? "—"}`}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  {(analysis?.uncertaintyNotes || []).length ? (
                    <div className="rounded-2xl border border-amber-300/10 bg-amber-400/[0.05] p-4">
                      <p className="text-sm font-semibold text-white">Uncertainty notes</p>
                      <div className="mt-2 space-y-2">
                        {(analysis?.uncertaintyNotes || []).map((item, index) => (
                          <p key={`uncertainty-${index}`} className="text-sm text-slate-200">{item}</p>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-white/10 px-4 py-12 text-center text-sm text-slate-400">
              {loading ? "Loading platform intelligence…" : "Platform observations will appear here as services and users perform actions."}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )

  return (
    <WorkspaceLayout
      eyebrow="Agent Workbench"
      title="Ananse Analytics"
      description="Explore service health and platform activity collected automatically from Liwiro."
      systemTitle="Data Sources"
      systemDescription="Live, permission-filtered platform and service observations."
      editorTitle="Analysis"
      editorDescription="Switch visualization styles, adjust dimensions and metrics, and inspect findings without leaving Liwiro."
      topActions={
        <Button type="button" variant="outline" onClick={refreshCurrentAnalysis} disabled={busy || !selectedDatasetId}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh Analysis
        </Button>
      }
      systemPanel={systemPanel}
      editorPanel={editorPanel}
    />
  )
}
