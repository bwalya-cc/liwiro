// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

"use client"

import { useEffect, useRef, useState } from "react"
import { Check, AlertCircle } from "lucide-react"
import { validateJsonText } from "@/lib/json-editor"

export function CodeEditor({
  value,
  onChange,
  language,
  placeholder = "Enter code here...",
  height = "200px",
  validate = false,
}) {
  const [isValid, setIsValid] = useState(true)
  const [errorMessage, setErrorMessage] = useState("")
  const [validationState, setValidationState] = useState("idle")
  const lastValidityRef = useRef(null)
  const successTimerRef = useRef(null)

  useEffect(() => {
    if (!(validate && language === "json")) return
    window.clearTimeout(successTimerRef.current)
    const timer = window.setTimeout(() => {
      const validation = validateJsonText(value)
      if (!String(value || "").trim()) {
        lastValidityRef.current = true
        setIsValid(true)
        setErrorMessage("")
        setValidationState("idle")
        return
      }
      if (!validation.valid) {
        lastValidityRef.current = false
        setIsValid(false)
        setErrorMessage(validation.message)
        setValidationState("invalid")
        return
      }
      if (validation.formatted && validation.formatted !== value) {
        onChange(validation.formatted)
        return
      }
      const shouldFlash = lastValidityRef.current === false
      lastValidityRef.current = true
      setIsValid(true)
      setErrorMessage("")
      setValidationState(shouldFlash ? "valid" : "idle")
      if (shouldFlash) {
        successTimerRef.current = window.setTimeout(() => setValidationState("idle"), 1200)
      }
    }, 700)

    return () => {
      window.clearTimeout(timer)
      window.clearTimeout(successTimerRef.current)
    }
  }, [value, validate, language, onChange])

  return (
    <div className="relative">
      <div className="mb-1 flex items-center justify-between">
        <div className="font-mono text-xs text-slate-500 dark:text-slate-400">{language.toUpperCase()}</div>
        {validate && (
          <div className="flex items-center">
            {isValid ? (
              <div className="flex items-center text-xs text-green-600 dark:text-green-400">
                <Check className="h-3 w-3 mr-1" />
                Valid
              </div>
            ) : (
              <div className="flex items-center text-xs text-red-500 dark:text-red-400">
                <AlertCircle className="h-3 w-3 mr-1" />
                Invalid
              </div>
            )}
          </div>
        )}
      </div>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={`w-full rounded-md border p-3 font-mono text-sm text-slate-900 dark:text-slate-100 ${
          validationState === "invalid"
            ? "border-red-300 bg-red-50 dark:border-red-500/50 dark:bg-red-950/30"
            : validationState === "valid"
            ? "border-emerald-300 bg-emerald-50 dark:border-emerald-500/50 dark:bg-emerald-950/20"
            : "border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-950"
        } focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent`}
        style={{
          height,
          resize: "vertical",
          tabSize: 2,
        }}
      />
      {!isValid && errorMessage && <div className="mt-1 text-xs text-red-500 dark:text-red-400">{errorMessage}</div>}
    </div>
  )
}
