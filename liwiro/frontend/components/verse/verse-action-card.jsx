"use client"

import { ChevronDown, ChevronUp, FileCode2, Loader2, Play, Save, Wand2 } from "lucide-react"
import Link from "next/link"
import { useMemo, useState } from "react"

import { Button } from "@/components/ui/button"

function artifactDescription(artifact) {
  const kind = String(artifact?.kind || "").trim()
  if (kind === "ananse-analysis") {
    const title = String(artifact?.analysis?.title || artifact?.title || "").trim()
    return title ? `Prepared an Ananse analysis for ${title}.` : "Prepared an Ananse analysis you can open and refine."
  }
  if (kind === "service-builder-lapis") {
    const serviceName = String(artifact?.lapisConfig?.metadata?.apiName || "").trim()
    return serviceName ? `Prepared a service draft for ${serviceName}.` : "Prepared a service draft you can open or generate."
  }
  if (kind === "service-manager-action") {
    const action = String(artifact?.serviceAction?.action || "").trim()
    const serviceName = String(artifact?.serviceAction?.serviceName || artifact?.serviceAction?.processId || "").trim()
    if (action && serviceName) {
      return `Prepared a ${action} action for ${serviceName}.`
    }
    return "Prepared a Service Manager action you can open or run."
  }
  if (kind === "vi-script") {
    const path = String(artifact?.path || "").trim()
    return path ? `Prepared a Versa draft for ${path}.` : "Prepared a Versa draft you can load or run."
  }
  if (kind === "vdb-query") {
    return "Prepared a VDB command you can inspect, load or run."
  }
  if (kind === "page-navigation") {
    const destination = String(artifact?.destination?.label || artifact?.targetPage || "").trim()
    return destination
      ? `Prepared a location change so you can continue in ${destination}.`
      : "Prepared a location change into the right workspace."
  }
  return "Prepared the next action."
}

function statusLabel(artifact) {
  const status = String(artifact?.status || "").trim().toLowerCase()
  if (status === "validated" || status === "repaired") return "Prepared"
  if (status === "blocked") return "Blocked"
  return ""
}

function artifactFiles(artifact) {
  const kind = String(artifact?.kind || "").trim()
  if (kind === "vi-script" && String(artifact?.versaSource || "").trim()) {
    return [{ path: artifact.path || "scratch/verse-draft.versa", source: String(artifact.versaSource), language: "Versa" }]
  }
  if (kind === "service-builder-lapis") {
    const lapis = artifact?.lapisConfig && typeof artifact.lapisConfig === "object" ? artifact.lapisConfig : {}
    const scripts = Object.entries(lapis?.endpoints || {}).flatMap(([id, endpoint]) => (
      typeof endpoint?.versaScript === "string" && endpoint.versaScript.trim()
        ? [{ path: String(endpoint.path || id), source: endpoint.versaScript, language: "Versa", endpointId: id }]
        : []
    ))
    return [...scripts, { path: "service.lapis.json", source: JSON.stringify(lapis, null, 2), language: "LAPIS" }]
  }
  if (kind === "vdb-query" && String(artifact?.vdbQuery || "").trim()) {
    return [{ path: "query.vql", source: String(artifact.vdbQuery), language: "VDB command" }]
  }
  return []
}

export default function VerseActionCard({
  artifact,
  onApply,
  onExecute,
  onSaveExecute,
  applyBusy = false,
  executeBusy = false,
  saveExecuteBusy = false,
}) {
  const [showSource, setShowSource] = useState(false)
  const [selectedFile, setSelectedFile] = useState(0)
  const files = useMemo(() => artifactFiles(artifact), [artifact])
  if (!artifact || typeof artifact !== "object") return null
  const status = String(artifact?.status || "").trim().toLowerCase()
  const blocked = status === "blocked"
  const issues = Array.isArray(artifact?.validation?.issues) ? artifact.validation.issues : []
  const manualLinks = Array.isArray(artifact?.manualLinks) ? artifact.manualLinks : []
  const showIssues = blocked && issues.length > 0
  const applyLabel = String(artifact?.applyLabel || "").trim()
  const executeLabel = String(artifact?.executeLabel || "").trim()
  const saveExecuteLabel = String(artifact?.saveExecuteLabel || "").trim()
  const kind = String(artifact?.kind || "").trim()
  const suppressApplyForDirectRun = (kind === "vi-script" || kind === "vdb-query") && (executeLabel || saveExecuteLabel)
  const effectiveApplyLabel = suppressApplyForDirectRun ? "" : applyLabel
  const currentFile = files[selectedFile] || files[0]
  const validationDetails = Array.isArray(artifact?.validation?.details) ? artifact.validation.details : []
  const errorLines = new Set((validationDetails.find((detail) => (
    detail?.path === currentFile?.path || detail?.endpointId === currentFile?.endpointId
  ))?.errorLines || []).map(Number))

  return (
    <div className={`mt-3 min-w-0 overflow-hidden rounded-[1.2rem] border px-4 py-4 ${
      blocked
        ? "border-rose-400/15 bg-rose-500/[0.08]"
        : "border-white/10 bg-black/15"
    }`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-semibold text-white">{artifact?.title || "Ready to use"}</p>
            {statusLabel(artifact) ? (
              <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.16em] ${
                blocked ? "border-rose-400/20 bg-rose-500/10 text-rose-100" : "border-emerald-400/20 bg-emerald-500/10 text-emerald-100"
              }`}>
                {statusLabel(artifact)}
              </span>
            ) : null}
          </div>
          <p className="mt-1 break-words text-xs text-slate-400">{artifactDescription(artifact)}</p>
          {showIssues ? (
            <div className="mt-2 space-y-1 text-xs text-rose-100/90">
              {issues.slice(0, 2).map((issue, index) => (
                <p key={`${artifact?.kind || "artifact"}-issue-${index}`} className="break-words">• {issue}</p>
              ))}
            </div>
          ) : null}
          {files.length > 0 ? (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="mt-3 h-7 px-2 text-[11px] uppercase tracking-[0.14em] text-sky-100 hover:bg-sky-400/10"
              onClick={() => setShowSource((current) => !current)}
            >
              {showSource ? <ChevronUp className="mr-1.5 h-3.5 w-3.5" /> : <ChevronDown className="mr-1.5 h-3.5 w-3.5" />}
              <FileCode2 className="mr-1.5 h-3.5 w-3.5" />
              {showSource ? "Hide generated file" : "Show generated file"}
            </Button>
          ) : null}
          {manualLinks.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {manualLinks.slice(0, 3).map((link) => (
                <Link
                  key={`${link.href}-${link.title}`}
                  href={link.href}
                  className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] uppercase tracking-[0.16em] text-slate-200 hover:bg-white/10"
                >
                  {link.title}
                </Link>
              ))}
            </div>
          ) : null}
        </div>
      </div>
      {showSource && currentFile ? (
        <div className="mt-3 overflow-hidden rounded-xl border border-white/10 bg-slate-950/80">
          <div className="flex flex-wrap items-center gap-2 border-b border-white/10 px-3 py-2">
            {files.map((file, index) => (
              <button
                key={`${file.path}-${index}`}
                type="button"
                onClick={() => setSelectedFile(index)}
                className={`rounded-md px-2 py-1 text-xs ${files.indexOf(file) === selectedFile ? "bg-sky-400/15 text-sky-100" : "text-slate-400 hover:bg-white/5"}`}
              >
                {file.path}
              </button>
            ))}
            <span className="ml-auto text-[10px] uppercase tracking-[0.14em] text-slate-500">{currentFile.language}</span>
          </div>
          <div className="max-h-[32rem] overflow-auto py-2 font-mono text-xs leading-6">
            {currentFile.source.split("\n").map((line, index) => {
              const lineNumber = index + 1
              const hasError = errorLines.has(lineNumber)
              return (
                <div key={lineNumber} className={`grid grid-cols-[3.25rem_minmax(0,1fr)] px-3 ${hasError ? "bg-red-500/25 text-red-50 ring-1 ring-inset ring-red-400/50" : "text-slate-200"}`}>
                  <span className={`select-none pr-3 text-right ${hasError ? "text-red-200" : "text-slate-600"}`}>{lineNumber}</span>
                  <code className="whitespace-pre break-all">{line || " "}</code>
                </div>
              )
            })}
          </div>
          {errorLines.size > 0 ? <p className="border-t border-red-400/20 bg-red-500/10 px-3 py-2 text-xs text-red-100">Highlighted lines are reported by validation.</p> : null}
        </div>
      ) : null}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {effectiveApplyLabel ? (
          <Button type="button" size="sm" variant="secondary" className="h-8 rounded-full px-3" onClick={onApply} disabled={applyBusy || blocked}>
            {applyBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Wand2 className="mr-2 h-4 w-4" />}
            {effectiveApplyLabel}
          </Button>
        ) : null}
        {executeLabel ? (
          <Button type="button" size="sm" className="h-8 rounded-full px-3" onClick={onExecute} disabled={executeBusy || blocked}>
            {executeBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
            {executeLabel}
          </Button>
        ) : null}
        {saveExecuteLabel ? (
          <Button type="button" size="sm" variant="outline" className="h-8 rounded-full px-3" onClick={onSaveExecute} disabled={saveExecuteBusy || blocked}>
            {saveExecuteBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
            {saveExecuteLabel}
          </Button>
        ) : null}
      </div>
    </div>
  )
}
