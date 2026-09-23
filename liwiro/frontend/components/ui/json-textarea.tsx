// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

"use client"

import * as React from "react"

import { Textarea } from "@/components/ui/textarea"
import { validateJsonText } from "@/lib/json-editor"
import { cn } from "@/lib/utils"

type JsonTextareaProps = React.ComponentProps<typeof Textarea> & {
  validationDelay?: number
  successFlashMs?: number
}

export const JsonTextarea = React.forwardRef<HTMLTextAreaElement, JsonTextareaProps>(
  (
    {
      className,
      value,
      onChange,
      onBlur,
      validationDelay = 700,
      successFlashMs = 1200,
      spellCheck = false,
      ...props
    },
    ref,
  ) => {
    const [status, setStatus] = React.useState<"idle" | "valid" | "invalid">("idle")
    const lastValidityRef = React.useRef<boolean | null>(null)
    const validationTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null)
    const successTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null)

    const clearTimers = React.useCallback(() => {
      if (validationTimerRef.current) {
        clearTimeout(validationTimerRef.current)
        validationTimerRef.current = null
      }
      if (successTimerRef.current) {
        clearTimeout(successTimerRef.current)
        successTimerRef.current = null
      }
    }, [])

    const emitFormattedValue = React.useCallback(
      (nextValue: string) => {
        if (!onChange) return
        const syntheticEvent = {
          target: { value: nextValue },
          currentTarget: { value: nextValue },
        } as React.ChangeEvent<HTMLTextAreaElement>
        onChange(syntheticEvent)
      },
      [onChange],
    )

    const applyValidation = React.useCallback(
      (textValue: string, allowFlash = true) => {
        const validation = validateJsonText(String(textValue || ""))
        if (!String(textValue || "").trim()) {
          lastValidityRef.current = true
          setStatus("idle")
          return
        }
        if (!validation.valid) {
          lastValidityRef.current = false
          setStatus("invalid")
          return
        }

        const currentValue = String(textValue || "")
        if (validation.formatted && validation.formatted !== currentValue) {
          emitFormattedValue(validation.formatted)
        }

        const shouldFlash = allowFlash && lastValidityRef.current === false
        lastValidityRef.current = true
        setStatus(shouldFlash ? "valid" : "idle")
        if (shouldFlash) {
          successTimerRef.current = setTimeout(() => setStatus("idle"), successFlashMs)
        }
      },
      [emitFormattedValue, successFlashMs],
    )

    React.useEffect(() => {
      clearTimers()
      validationTimerRef.current = setTimeout(() => {
        applyValidation(String(value || ""))
      }, validationDelay)
      return clearTimers
    }, [applyValidation, clearTimers, validationDelay, value])

    return (
      <Textarea
        ref={ref}
        value={value}
        onChange={onChange}
        onBlur={(event) => {
          clearTimers()
          applyValidation(event.target.value)
          onBlur?.(event)
        }}
        spellCheck={spellCheck}
        className={cn(
          status === "invalid" && "border-rose-300/75 bg-rose-500/[0.08] focus-visible:ring-rose-200/80",
          status === "valid" && "border-emerald-300/70 bg-emerald-500/[0.05] focus-visible:ring-emerald-200/80",
          className,
        )}
        {...props}
      />
    )
  },
)

JsonTextarea.displayName = "JsonTextarea"
