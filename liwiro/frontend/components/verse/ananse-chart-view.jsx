"use client"

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceDot,
  Scatter,
  ScatterChart,
  XAxis,
  YAxis,
} from "recharts"

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"

const CHART_COLORS = [
  "#22c55e",
  "#38bdf8",
  "#f59e0b",
  "#f97316",
  "#a78bfa",
]

function seriesKeysForChart(chart = {}) {
  const keys = Array.isArray(chart?.yKeys) ? chart.yKeys.filter(Boolean) : []
  if (keys.length) return keys
  if (chart?.valueKey) return [String(chart.valueKey)]
  return ["value"]
}

function chartConfig(chart = {}) {
  const keys = seriesKeysForChart(chart)
  const baseConfig = keys.reduce((config, key, index) => {
    config[key] = {
      label: String(key || "value").replace(/[_-]+/g, " "),
      color: CHART_COLORS[index % CHART_COLORS.length],
    }
    return config
  }, {})

  const chartType = String(chart?.chartType || chart?.type || "bar").trim().toLowerCase()
  if (!["pie", "donut"].includes(chartType)) {
    return baseConfig
  }

  const categoryKey = String(chart?.xKey || "label").trim() || "label"
  const categoryConfig = (Array.isArray(chart?.data) ? chart.data : []).reduce((config, item, index) => {
    const label = String(item?.[categoryKey] || "").trim()
    if (!label) return config
    config[label] = {
      label,
      color: CHART_COLORS[index % CHART_COLORS.length],
    }
    return config
  }, {})

  return { ...baseConfig, ...categoryConfig }
}

function formatAxisLabel(value) {
  if (value === null || value === undefined || value === "") return "—"
  return String(value)
}

function chartStatus(chart = {}) {
  const status = String(chart?.status || "").trim().toLowerCase()
  return status || "ready"
}

function chartFallbackReason(chart = {}) {
  return String(chart?.fallbackReason || "").trim()
}

function validateChart(chart = {}, metrics = [], tablePreview = []) {
  const chartType = String(chart?.chartType || chart?.type || "bar").trim().toLowerCase()
  const data = Array.isArray(chart?.data) ? chart.data : []
  if (chartStatus(chart) === "fallback") {
    return { ok: false, message: chartFallbackReason(chart) || "This chart fell back to a safer view." }
  }
  if (chartType === "metric-list") {
    return metrics.length ? { ok: true } : { ok: false, message: "No metric cards are available for this result yet." }
  }
  if (chartType === "table") {
    return (tablePreview.length || data.length) ? { ok: true } : { ok: false, message: "No table preview is available for this result yet." }
  }
  if (!data.length) {
    return { ok: false, message: "No chart data is available for this view yet." }
  }
  if (["line", "area", "anomaly-timeline"].includes(chartType) && (!chart?.xKey || !(chart?.yKeys || []).length)) {
    return { ok: false, message: "This trend view is missing an x-axis or metric series." }
  }
  if (chartType === "scatter" && (!chart?.xKey || !(chart?.yKeys || []).length)) {
    return { ok: false, message: "Scatter charts need both x and y numeric keys." }
  }
  if (["pie", "donut", "histogram"].includes(chartType) && !chart?.valueKey) {
    return { ok: false, message: "This chart is missing the value field required for rendering." }
  }
  return { ok: true }
}

function renderMetricList(chart = {}, metrics = []) {
  const metricItems = Array.isArray(metrics) ? metrics : []
  if (!metricItems.length) return null
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {metricItems.map((item, index) => (
        <div key={`${item?.label || "metric"}-${index}`} className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
          <p className="text-[11px] uppercase tracking-[0.18em] text-slate-400">{item?.label || "Metric"}</p>
          <p className="mt-2 text-2xl font-semibold text-white">{String(item?.value ?? "—")}</p>
        </div>
      ))}
    </div>
  )
}

function renderTable(chart = {}, rows = []) {
  const tableColumns = Array.isArray(chart?.tableColumns) && chart.tableColumns.length
    ? chart.tableColumns
    : Object.keys(rows?.[0] || {})
  if (!tableColumns.length) return null
  return (
    <div className="overflow-hidden rounded-2xl border border-white/10">
      <Table>
        <TableHeader>
          <TableRow>
            {tableColumns.map((column) => (
              <TableHead key={column}>{column}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {(Array.isArray(rows) ? rows : []).slice(0, 18).map((row, rowIndex) => (
            <TableRow key={`row-${rowIndex}`}>
              {tableColumns.map((column) => (
                <TableCell key={`${rowIndex}-${column}`}>{formatAxisLabel(row?.[column])}</TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

export default function AnanseChartView({ chart, metrics = [], tablePreview = [], compact = false }) {
  const chartType = String(chart?.chartType || chart?.type || "bar").trim().toLowerCase()
  const data = Array.isArray(chart?.data) ? chart.data : []
  const xKey = String(chart?.xKey || "label").trim() || "label"
  const yKeys = seriesKeysForChart(chart)
  const valueKey = String(chart?.valueKey || yKeys[0] || "value").trim() || "value"
  const seriesKey = String(chart?.seriesKey || "").trim()
  const validation = validateChart(chart, metrics, tablePreview)
  const fallbackRows = tablePreview.length ? tablePreview : data
  const chartClassName = compact ? "h-[18rem] w-full" : "h-[24rem] w-full"

  if (chartType === "metric-list") {
    return renderMetricList(chart, metrics)
  }

  if (chartType === "table") {
    return renderTable(chart, tablePreview.length ? tablePreview : data)
  }

  if (!validation.ok) {
    return (
      <div className="space-y-4">
        <div className="rounded-2xl border border-dashed border-white/10 px-4 py-6 text-center text-sm text-slate-300">
          <p>{validation.message}</p>
          {chartFallbackReason(chart) ? <p className="mt-2 text-xs text-slate-500">{chartFallbackReason(chart)}</p> : null}
        </div>
        {fallbackRows.length ? renderTable({ ...chart, chartType: "table" }, fallbackRows) : null}
      </div>
    )
  }

  const config = chartConfig(chart)

  if (chartType === "line" || chartType === "anomaly-timeline") {
    return (
      <ChartContainer config={config} className={chartClassName}>
        <LineChart data={data}>
          <CartesianGrid vertical={false} />
          <XAxis dataKey={xKey} tickLine={false} axisLine={false} minTickGap={24} />
          <YAxis tickLine={false} axisLine={false} />
          <ChartTooltip content={<ChartTooltipContent />} />
          <ChartLegend content={<ChartLegendContent />} />
          {yKeys.map((key) => (
            <Line key={key} type="monotone" dataKey={key} stroke={`var(--color-${key})`} strokeWidth={2.2} dot={compact ? false : { r: 2 }} />
          ))}
          {chartType === "anomaly-timeline" && Array.isArray(chart?.anomalyPoints)
            ? chart.anomalyPoints.map((point, index) => (
                <ReferenceDot
                  key={`anomaly-${index}`}
                  x={point?.x}
                  y={point?.y}
                  r={5}
                  fill="hsl(var(--chart-5))"
                  stroke="white"
                  strokeWidth={1.5}
                />
              ))
            : null}
        </LineChart>
      </ChartContainer>
    )
  }

  if (chartType === "area") {
    return (
      <ChartContainer config={config} className={chartClassName}>
        <AreaChart data={data}>
          <CartesianGrid vertical={false} />
          <XAxis dataKey={xKey} tickLine={false} axisLine={false} minTickGap={24} />
          <YAxis tickLine={false} axisLine={false} />
          <ChartTooltip content={<ChartTooltipContent />} />
          <ChartLegend content={<ChartLegendContent />} />
          {yKeys.map((key) => (
            <Area key={key} type="monotone" dataKey={key} stroke={`var(--color-${key})`} fill={`var(--color-${key})`} fillOpacity={0.24} />
          ))}
        </AreaChart>
      </ChartContainer>
    )
  }

  if (chartType === "scatter") {
    const yKey = yKeys[0] || valueKey
    return (
      <ChartContainer config={config} className={chartClassName}>
        <ScatterChart data={data}>
          <CartesianGrid />
          <XAxis dataKey={xKey} type="number" tickLine={false} axisLine={false} />
          <YAxis dataKey={yKey} type="number" tickLine={false} axisLine={false} />
          <ChartTooltip content={<ChartTooltipContent />} />
          <Scatter data={data} fill={`var(--color-${yKey})`} />
        </ScatterChart>
      </ChartContainer>
    )
  }

  if (chartType === "pie" || chartType === "donut") {
    return (
      <ChartContainer config={config} className={chartClassName}>
        <PieChart>
          <ChartTooltip content={<ChartTooltipContent nameKey={valueKey} />} />
          <ChartLegend content={<ChartLegendContent nameKey={xKey} />} />
          <Pie
            data={data}
            dataKey={valueKey}
            nameKey={xKey}
            innerRadius={chartType === "donut" ? 55 : 0}
            outerRadius={compact ? 72 : 88}
            paddingAngle={3}
          >
            {data.map((entry, index) => (
              <Cell key={`slice-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
            ))}
          </Pie>
        </PieChart>
      </ChartContainer>
    )
  }

  if (chartType === "histogram") {
    return (
      <ChartContainer config={config} className={chartClassName}>
        <BarChart data={data}>
          <CartesianGrid vertical={false} />
          <XAxis dataKey={xKey} tickLine={false} axisLine={false} minTickGap={compact ? 18 : 24} />
          <YAxis tickLine={false} axisLine={false} />
          <ChartTooltip content={<ChartTooltipContent />} />
          <Bar dataKey={valueKey} fill={`var(--color-${valueKey})`} radius={[8, 8, 0, 0]} />
        </BarChart>
      </ChartContainer>
    )
  }

  return (
    <ChartContainer config={config} className={chartClassName}>
      <BarChart data={data} layout={chartType === "leaderboard" ? "vertical" : "horizontal"}>
        <CartesianGrid vertical={chartType === "leaderboard"} horizontal={chartType !== "leaderboard"} />
        {chartType === "leaderboard" ? (
          <>
            <XAxis type="number" tickLine={false} axisLine={false} />
            <YAxis dataKey={xKey} type="category" tickLine={false} axisLine={false} width={120} />
          </>
        ) : (
          <>
            <XAxis dataKey={xKey} tickLine={false} axisLine={false} minTickGap={24} />
            <YAxis tickLine={false} axisLine={false} />
          </>
        )}
        <ChartTooltip content={<ChartTooltipContent />} />
        <ChartLegend content={<ChartLegendContent />} />
        {yKeys.map((key) => (
          <Bar
            key={key}
            dataKey={key}
            stackId={chart?.stacked ? "stack" : undefined}
            fill={`var(--color-${key})`}
            radius={chartType === "leaderboard" ? [0, 12, 12, 0] : [12, 12, 0, 0]}
          />
        ))}
      </BarChart>
    </ChartContainer>
  )
}
