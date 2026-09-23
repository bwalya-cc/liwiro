"use client"

import { Loader2 } from "lucide-react"

export function VdbTransportStatusIndicator({ status, className = "", showText = true }) {
  const normalized = status?.status === "starting"
    ? "starting"
    : status?.status === "paused" || status?.paused
      ? "paused"
    : status?.status === "available"
      ? "available"
      : status?.status === "unsupported"
        ? "unsupported"
      : status?.status === "unavailable"
        ? "unavailable"
        : "checking"

  const dotClassName = normalized === "available"
    ? "bg-emerald-500 shadow-[0_0_0_4px_rgba(16,185,129,0.16)]"
    : normalized === "paused"
      ? "bg-amber-400 shadow-[0_0_0_4px_rgba(251,191,36,0.18)]"
    : normalized === "unavailable"
      ? "bg-rose-500 shadow-[0_0_0_4px_rgba(244,63,94,0.14)]"
      : normalized === "unsupported"
        ? "bg-orange-400 shadow-[0_0_0_4px_rgba(251,146,60,0.14)]"
        : "bg-amber-400 shadow-[0_0_0_4px_rgba(251,191,36,0.14)]"

  const label = normalized === "available"
    ? "Available"
    : normalized === "paused"
      ? "Paused"
    : normalized === "unavailable"
      ? "Unavailable"
      : normalized === "unsupported"
        ? (status?.detail || "Unsupported")
      : normalized === "starting"
        ? "Starting"
        : "Checking"

  return (
    <span
      className={`inline-flex max-w-full items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-xs font-medium text-slate-200 ${className}`.trim()}
      title={status?.detail || label}
    >
      {normalized === "starting" ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : (
        <span className={`h-2.5 w-2.5 rounded-full ${dotClassName}`} />
      )}
      {showText ? <span className="min-w-0 break-words">{label}</span> : null}
    </span>
  )
}
