// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import { useState } from "react"
import { Eye, EyeOff } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

export default function PasswordInput({ className = "", wrapperClassName = "", actions = [], ...props }) {
  const [visible, setVisible] = useState(false)
  const hasExtraActions = Array.isArray(actions) && actions.length > 0

  return (
    <div className={`relative w-full ${wrapperClassName}`.trim()}>
      <Input
        {...props}
        type={visible ? "text" : "password"}
        className={`${hasExtraActions ? "pr-20" : "pr-10"} ${className}`.trim()}
      />
      <div className="absolute right-1 top-1/2 flex -translate-y-1/2 items-center gap-1">
        {hasExtraActions ? actions.map((action, index) => (
          <Button
            key={action?.key || `${action?.label || "action"}-${index}`}
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0 text-slate-400 hover:bg-white/5 hover:text-white"
            onClick={action?.onClick}
            aria-label={action?.label || "Password action"}
            title={action?.label || "Password action"}
          >
            {action?.icon}
          </Button>
        )) : null}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-8 w-8 p-0 text-slate-400 hover:bg-white/5 hover:text-white"
          onClick={() => setVisible((prev) => !prev)}
          aria-label={visible ? "Hide password" : "Show password"}
        >
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </Button>
      </div>
    </div>
  )
}
