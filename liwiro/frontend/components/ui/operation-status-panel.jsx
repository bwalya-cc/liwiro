"use client"

import { AlertTriangle, CheckCircle2, LoaderCircle, Sparkles } from "lucide-react"

import { Progress } from "@/components/ui/progress"

const STATE_STYLES = {
  running: {
    icon: LoaderCircle,
    iconClassName: "animate-spin text-sky-500 dark:text-sky-300",
    borderClassName: "border-sky-200/80 bg-sky-50/85 dark:border-sky-500/30 dark:bg-sky-950/25",
    labelClassName: "text-sky-900 dark:text-sky-100",
    detailClassName: "text-sky-700 dark:text-sky-200/90",
  },
  success: {
    icon: CheckCircle2,
    iconClassName: "text-emerald-500 dark:text-emerald-300",
    borderClassName: "border-emerald-200/80 bg-emerald-50/85 dark:border-emerald-500/30 dark:bg-emerald-950/25",
    labelClassName: "text-emerald-900 dark:text-emerald-100",
    detailClassName: "text-emerald-700 dark:text-emerald-200/90",
  },
  error: {
    icon: AlertTriangle,
    iconClassName: "text-amber-500 dark:text-amber-300",
    borderClassName: "border-amber-200/80 bg-amber-50/85 dark:border-amber-500/30 dark:bg-amber-950/25",
    labelClassName: "text-amber-900 dark:text-amber-100",
    detailClassName: "text-amber-700 dark:text-amber-200/90",
  },
  idle: {
    icon: Sparkles,
    iconClassName: "text-slate-500 dark:text-slate-300",
    borderClassName: "border-slate-200/80 bg-white/85 dark:border-slate-700/70 dark:bg-slate-950/40",
    labelClassName: "text-slate-900 dark:text-slate-100",
    detailClassName: "text-slate-600 dark:text-slate-300",
  },
}

export function OperationStatusPanel({ status, className = "" }) {
  if (!status?.visible) return null

  const state = String(status?.state || "idle").trim().toLowerCase()
  const styles = STATE_STYLES[state] || STATE_STYLES.idle
  const Icon = styles.icon
  const total = Number(status?.total || 0)
  const completed = Math.max(0, Number(status?.completed || 0))
  const explicitProgress = Number(status?.progress || 0)
  const progressValue = total > 0 ? Math.min(100, Math.max(0, (completed / total) * 100)) : Math.min(100, Math.max(0, explicitProgress))

  return (
    <div className={`rounded-[1.1rem] border px-4 py-3 shadow-sm ${styles.borderClassName} ${className}`.trim()}>
      <div className="flex items-start gap-3">
        <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${styles.iconClassName}`.trim()} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <p className={`text-sm font-semibold ${styles.labelClassName}`.trim()}>{status?.title || status?.label || "Working"}</p>
              {status?.label && status?.title && status?.label !== status?.title ? (
                <p className={`text-xs ${styles.detailClassName}`.trim()}>{status.label}</p>
              ) : null}
            </div>
            {(status?.current || total > 0) ? (
              <p className={`shrink-0 text-xs ${styles.detailClassName}`.trim()}>
                {status?.current
                  ? status.current
                  : `${completed}/${total}`}
              </p>
            ) : null}
          </div>
          {status?.detail ? <p className={`mt-1 text-xs ${styles.detailClassName}`.trim()}>{status.detail}</p> : null}
          {total > 0 || explicitProgress > 0 ? (
            <div className="mt-3 space-y-1.5">
              <Progress value={progressValue} className="h-2.5" />
              <div className={`flex items-center justify-between text-[11px] ${styles.detailClassName}`.trim()}>
                <span>{total > 0 ? `${completed}/${total} complete` : `${Math.round(progressValue)}% complete`}</span>
                <span>{Number(status?.succeeded || 0)} success, {Number(status?.failed || 0)} failed</span>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

