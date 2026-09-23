"use client"

import { cn } from "@/lib/utils"

type ModeOption = {
  value: string
  label: string
}

type ModeToggleProps = {
  value: string
  onChange: (value: string) => void
  options?: ModeOption[]
  className?: string
}

const DEFAULT_OPTIONS = [
  { value: "structured", label: "Structured Mode" },
  { value: "text", label: "Text Mode" },
]

export function ModeToggle({ value, onChange, options = DEFAULT_OPTIONS, className }: ModeToggleProps) {
  return (
    <div className={cn("inline-flex items-center gap-1 rounded-2xl border border-white/10 bg-[#081521] p-1", className)}>
      {options.map((option) => {
        const active = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={cn(
              "rounded-xl px-3 py-2 text-sm font-semibold transition",
              active
                ? "bg-sky-400 text-slate-950 shadow-[0_10px_24px_rgba(56,189,248,0.28)]"
                : "text-slate-300 hover:bg-white/5 hover:text-white",
            )}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
