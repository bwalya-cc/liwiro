"use client"

import { useEffect, useRef, useState } from "react"
import { Check, Copy } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

/** @param {{text?: string, getText?: () => string, label?: string, successMessage?: string, errorMessage?: string, disabled?: boolean, className?: string}} props */
export function CopyIconButton({
  text = "",
  getText,
  label = "Copy text",
  successMessage = "Copied to clipboard",
  errorMessage = "Failed to copy text",
  disabled = false,
  className,
}) {
  const resolveText = () => {
    if (typeof getText === "function") {
      const next = getText()
      return typeof next === "string" ? next : String(next ?? "")
    }
    return typeof text === "string" ? text : String(text ?? "")
  }
  const normalizedText = resolveText()
  const [copied, setCopied] = useState(false)
  const resetTimerRef = useRef(null)

  useEffect(() => {
    return () => {
      if (resetTimerRef.current) {
        clearTimeout(resetTimerRef.current)
      }
    }
  }, [])

  const handleCopy = async (event) => {
    event?.stopPropagation?.()
    const currentText = resolveText()
    if (disabled || !currentText.trim()) return
    try {
      await navigator.clipboard.writeText(currentText)
      setCopied(true)
      toast.success(successMessage)
      if (resetTimerRef.current) {
        clearTimeout(resetTimerRef.current)
      }
      resetTimerRef.current = setTimeout(() => {
        setCopied(false)
      }, 1400)
    } catch {
      toast.error(errorMessage)
    }
  }

  return (
    <Button
      type="button"
      variant="outline"
      size="icon"
      aria-label={label}
      title={label}
      onClick={handleCopy}
      disabled={disabled || (!getText && !normalizedText.trim())}
      className={cn(
        "h-8 w-8 rounded-lg border-slate-300/80 bg-white/90 text-slate-700 shadow-sm backdrop-blur hover:bg-slate-100 hover:text-slate-900 dark:border-white/10 dark:bg-slate-950/80 dark:text-slate-100 dark:hover:bg-slate-900",
        className,
      )}
    >
      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
    </Button>
  )
}
