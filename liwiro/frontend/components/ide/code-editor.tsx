"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { AlertCircle, CheckCircle2 } from "lucide-react"

import { CopyIconButton } from "@/components/ui/copy-icon-button"
import { validateJsonText } from "@/lib/json-editor"
import { cn } from "@/lib/utils"

type CodeEditorProps = {
  value: string
  onChange?: (value: string) => void
  language?: string
  placeholder?: string
  minHeight?: string
  readOnly?: boolean
  error?: string
  status?: string
  validateJson?: boolean
  className?: string
}

export function IDECodeEditor({
  value,
  onChange,
  language = "json",
  placeholder,
  minHeight = "24rem",
  readOnly = false,
  error,
  status,
  validateJson = false,
  className,
}: CodeEditorProps) {
  const gutterRef = useRef<HTMLDivElement | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const validationTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastValidityRef = useRef<boolean | null>(null)
  const [validationState, setValidationState] = useState<"idle" | "valid" | "invalid">("idle")
  const [validationMessage, setValidationMessage] = useState("")
  const lineNumbers = useMemo(() => {
    const count = Math.max(1, String(value || "").split("\n").length)
    return Array.from({ length: count }, (_, index) => index + 1)
  }, [value])

  const clearValidationTimers = useCallback(() => {
    if (validationTimerRef.current) {
      clearTimeout(validationTimerRef.current)
      validationTimerRef.current = null
    }
    if (successTimerRef.current) {
      clearTimeout(successTimerRef.current)
      successTimerRef.current = null
    }
  }, [])

  const applyJsonValidation = useCallback(
    (textValue: string, allowFlash = true) => {
      if (!validateJson) return
      const validation = validateJsonText(textValue)
      if (!String(textValue || "").trim()) {
        lastValidityRef.current = true
        setValidationState("idle")
        setValidationMessage("")
        return
      }
      if (!validation.valid) {
        lastValidityRef.current = false
        setValidationState("invalid")
        setValidationMessage(validation.message)
        return
      }

      if (!readOnly && validation.formatted && validation.formatted !== textValue) {
        onChange?.(validation.formatted)
      }
      const shouldFlash = allowFlash && lastValidityRef.current === false
      lastValidityRef.current = true
      setValidationState(shouldFlash ? "valid" : "idle")
      setValidationMessage("")
      if (shouldFlash) {
        successTimerRef.current = setTimeout(() => setValidationState("idle"), 1200)
      }
    },
    [onChange, readOnly, validateJson],
  )

  useEffect(() => {
    if (!validateJson) return
    clearValidationTimers()
    validationTimerRef.current = setTimeout(() => {
      applyJsonValidation(String(value || ""))
    }, 700)
    return clearValidationTimers
  }, [applyJsonValidation, clearValidationTimers, validateJson, value])

  const validation = validateJson
    ? {
        valid: validationState !== "invalid",
        message: validationMessage,
      }
    : { valid: true, message: "" }
  const effectiveError = error || (!validation.valid ? validation.message : "")

  const handleScroll = () => {
    if (!textareaRef.current || !gutterRef.current) return
    gutterRef.current.scrollTop = textareaRef.current.scrollTop
  }

  return (
    <div
      className={cn(
        "ide-code-editor",
        validationState === "invalid" && "border-rose-300/45 shadow-[0_0_0_1px_rgba(253,164,175,0.24)]",
        validationState === "valid" && "border-emerald-300/35 shadow-[0_0_0_1px_rgba(110,231,183,0.18)]",
        className,
      )}
    >
      <div className="ide-code-editor-toolbar">
        <div className="flex items-center gap-3">
          <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-300">
            {language}
          </span>
          {status ? <span className="text-xs text-slate-400">{status}</span> : null}
        </div>
        <div className="flex items-center gap-2">
          {validateJson ? (
            <div className={cn("flex items-center gap-2 text-xs", validation.valid ? "text-emerald-300" : "text-amber-300")}>
              {validation.valid ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
              <span>{validation.valid ? "Valid JSON" : "Invalid JSON"}</span>
            </div>
          ) : null}
          <CopyIconButton
            text={value}
            label={`Copy ${language} content`}
            successMessage="Copied to clipboard"
            errorMessage="Failed to copy content"
          />
        </div>
      </div>
      <div className="ide-code-editor-body" style={{ minHeight }}>
        <div ref={gutterRef} className="ide-code-editor-gutter" aria-hidden="true">
          {lineNumbers.map((lineNumber) => (
            <div key={lineNumber}>{lineNumber}</div>
          ))}
        </div>
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => onChange?.(event.target.value)}
          onBlur={(event) => {
            clearValidationTimers()
            applyJsonValidation(event.target.value)
          }}
          onScroll={handleScroll}
          readOnly={readOnly}
          placeholder={placeholder}
          spellCheck={false}
          className="ide-code-editor-input"
        />
      </div>
      {effectiveError ? <p className="ide-code-editor-error">{effectiveError}</p> : null}
    </div>
  )
}
