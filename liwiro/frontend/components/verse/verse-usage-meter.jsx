"use client"

import { Info } from "lucide-react"
import { useMemo } from "react"

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"

function usageNumber(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function formatCount(value) {
  const numeric = usageNumber(value)
  return new Intl.NumberFormat().format(numeric == null ? 0 : Math.max(0, Math.round(numeric)))
}

function usageFromMessage(message) {
  if (message?.usage && typeof message.usage === "object") return message.usage
  if (message?.inspectDetails?.usage && typeof message.inspectDetails.usage === "object") {
    return message.inspectDetails.usage
  }
  return null
}

function matchesSelectedProvider(usage, fallbackProviderOption, fallbackProvider) {
  const selectedId = String(fallbackProviderOption?.id || fallbackProvider || "").trim().toLowerCase()
  if (!selectedId) return true
  const usageId = String(usage?.provider?.id || "").trim().toLowerCase()
  return usageId === selectedId
}

function summarizeUsage(messages, fallbackProviderOption, fallbackProvider, scopeLabel) {
  let totalInput = 0
  let totalOutput = 0
  let totalTokens = 0
  let hasInput = false
  let hasOutput = false
  let hasTotal = false
  let latestUsage = null
  let anyUsage = false
  const providerKeys = new Set()

  for (const message of Array.isArray(messages) ? messages : []) {
    const role = String(message?.role || "").trim().toLowerCase()
    if (role !== "agent" && role !== "assistant") continue
    const usage = usageFromMessage(message)
    if (!usage) continue
    if (!matchesSelectedProvider(usage, fallbackProviderOption, fallbackProvider)) continue
    anyUsage = true
    latestUsage = usage
    const providerId = String(usage?.provider?.id || "").trim()
    const providerModel = String(usage?.provider?.model || "").trim()
    if (providerId || providerModel) {
      providerKeys.add(`${providerId}:${providerModel}`)
    }
    const input = usageNumber(usage?.inputTokens)
    const output = usageNumber(usage?.outputTokens)
    const total = usageNumber(usage?.totalTokens)
    if (input != null) {
      totalInput += input
      hasInput = true
    }
    if (output != null) {
      totalOutput += output
      hasOutput = true
    }
    if (total != null) {
      totalTokens += total
      hasTotal = true
    } else if (input != null || output != null) {
      totalTokens += (input || 0) + (output || 0)
      hasTotal = true
    }
  }

  const percentUsed = usageNumber(latestUsage?.percentUsed)
  const providerLabel = String(
    latestUsage?.provider?.label || fallbackProviderOption?.label || fallbackProvider || "Provider"
  ).trim()
  const providerModel = String(latestUsage?.provider?.model || fallbackProviderOption?.model || "").trim()
  const limitLabel = String(latestUsage?.limitLabel || "").trim()
  const mixedProviders = providerKeys.size > 1

  let tone = "orange"
  let width = "100%"
  if (percentUsed != null) {
    width = `${Math.max(0, Math.min(100, percentUsed))}%`
    tone = percentUsed >= 80 ? "red" : percentUsed < 40 ? "green" : "blue"
  } else if (anyUsage) {
    tone = "blue"
  }

  const title = mixedProviders ? "Mixed providers" : providerLabel
  const hasTokenUsage = hasInput || hasOutput || hasTotal
  const subtitle = percentUsed != null
    ? `${Math.round(percentUsed)}%${limitLabel ? ` of ${limitLabel}` : ""}`
    : anyUsage
      ? hasTokenUsage
        ? `${formatCount(totalTokens)} tokens tracked`
        : "Usage tracked"
      : "Usage pending"

  return {
    anyUsage,
    hasInput,
    hasOutput,
    hasTotal,
    totalInput,
    totalOutput,
    totalTokens,
    percentUsed,
    providerLabel,
    providerModel,
    limitLabel,
    mixedProviders,
    tone,
    width,
    title,
    subtitle,
    scopeLabel,
  }
}

const TONE_STYLES = {
  green: {
    fill: "bg-emerald-400",
    badge: "border-emerald-400/25 bg-emerald-400/10 text-emerald-100",
  },
  blue: {
    fill: "bg-sky-400",
    badge: "border-sky-400/25 bg-sky-400/10 text-sky-100",
  },
  red: {
    fill: "bg-rose-400",
    badge: "border-rose-400/25 bg-rose-400/10 text-rose-100",
  },
  orange: {
    fill: "bg-amber-400",
    badge: "border-amber-400/25 bg-amber-400/10 text-amber-100",
  },
}

export default function VerseUsageMeter({
  messages = [],
  selectedProviderOption = null,
  selectedProvider = "",
  scopeLabel = "current conversation",
  className = "",
  tooltipAlign = "end",
}) {
  const summary = useMemo(
    () => summarizeUsage(messages, selectedProviderOption, selectedProvider, scopeLabel),
    [messages, scopeLabel, selectedProvider, selectedProviderOption]
  )
  const tone = TONE_STYLES[summary.tone] || TONE_STYLES.orange

  return (
    <div className={`flex min-w-0 items-center gap-3 ${className}`.trim()}>
      <TooltipProvider delayDuration={120}>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label={`Usage: ${summary.subtitle}`}
              className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border ${tone.badge}`}
            >
              <Info className="h-4 w-4" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="top" align={tooltipAlign} className="max-w-xs rounded-xl border-white/10 bg-[#08111c] px-3 py-3 text-xs text-slate-100">
            <div className="space-y-2">
              <div>
                <p className="font-semibold text-white">{summary.mixedProviders ? "Mixed providers" : summary.providerLabel}</p>
                <p className="text-slate-400">{summary.subtitle}</p>
                <p className="text-slate-400">{summary.scopeLabel}</p>
              </div>
              {summary.providerModel ? <p className="text-slate-300">Model: {summary.providerModel}</p> : null}
              {summary.mixedProviders ? (
                <p className="text-slate-300">This conversation includes assistant replies from more than one provider or model.</p>
              ) : null}
              {summary.hasInput ? <p className="text-slate-300">Input tokens: {formatCount(summary.totalInput)}</p> : null}
              {summary.hasOutput ? <p className="text-slate-300">Output tokens: {formatCount(summary.totalOutput)}</p> : null}
              {summary.hasTotal ? <p className="text-slate-300">Total tokens: {formatCount(summary.totalTokens)}</p> : null}
              {summary.percentUsed == null && !summary.anyUsage ? (
                <p className="text-slate-300">Usage data is not available yet for this conversation.</p>
              ) : null}
            </div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex min-w-0 items-center gap-2">
          <p className="truncate text-xs font-medium text-slate-200">
            {summary.mixedProviders ? "Mixed providers" : summary.providerLabel}
          </p>
          {summary.providerModel ? (
            <span className="truncate text-[11px] text-slate-400">{summary.providerModel}</span>
          ) : null}
        </div>
        <div className="overflow-hidden rounded-full bg-white/10">
          <div
            className={`h-2 rounded-full transition-all duration-300 ${tone.fill}`}
            style={{ width: summary.width }}
          />
        </div>
        <p className="mt-1 truncate text-[11px] text-slate-400">{summary.subtitle}</p>
      </div>
    </div>
  )
}
