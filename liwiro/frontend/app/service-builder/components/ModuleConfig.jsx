// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

"use client"

import { useEffect, useMemo, useState } from "react"
import { Plus, RefreshCw, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { JsonTextarea } from "@/components/ui/json-textarea"
import { Label } from "@/components/ui/label"
import { parseJsonLikeObject } from "@/lib/json-editor"

export default function ModuleConfig({
  config,
  availableModules = [],
  availableDomains = [],
  loading = false,
  refreshCatalog,
  onAttachModule,
  updateConfig,
}) {
  const attachedModules = useMemo(
    () => (Array.isArray(config?.modules) ? config.modules : []),
    [config?.modules],
  )
  const [selectedModuleName, setSelectedModuleName] = useState("")
  const [configDrafts, setConfigDrafts] = useState({})
  const [configErrors, setConfigErrors] = useState({})

  const attachedNames = useMemo(
    () => new Set(attachedModules.map((item) => String(item?.name || "").trim().toLowerCase()).filter(Boolean)),
    [attachedModules],
  )

  const selectableModules = useMemo(
    () => (availableModules || []).filter((module) => !attachedNames.has(String(module?.name || "").trim().toLowerCase())),
    [attachedNames, availableModules],
  )

  useEffect(() => {
    const nextDrafts = {}
    for (const item of attachedModules) {
      const name = String(item?.name || "").trim()
      if (!name) continue
      nextDrafts[name] = JSON.stringify(item?.config || {}, null, 2)
    }
    setConfigDrafts(nextDrafts)
    setConfigErrors((prev) => {
      const next = {}
      for (const item of attachedModules) {
        const name = String(item?.name || "").trim()
        if (!name) continue
        if (prev[name]) next[name] = prev[name]
      }
      return next
    })
  }, [attachedModules])

  const setModules = (nextModules) => {
    updateConfig("modules", null, "items", nextModules)
  }

  const removeModule = (moduleName) => {
    const target = String(moduleName || "").trim().toLowerCase()
    setModules(attachedModules.filter((item) => String(item?.name || "").trim().toLowerCase() !== target))
  }

  const updateModuleConfig = (moduleName, value) => {
    const key = String(moduleName || "").trim()
    setConfigDrafts((prev) => ({ ...prev, [key]: value }))
    try {
      const parsed = value.trim() ? parseJsonLikeObject(value, `${key} config`) : {}
      setConfigErrors((prev) => ({ ...prev, [key]: "" }))
      setModules(
        attachedModules.map((item) =>
          String(item?.name || "").trim() === key
            ? { ...item, config: parsed && typeof parsed === "object" ? parsed : {} }
            : item,
        ),
      )
    } catch (error) {
      setConfigErrors((prev) => ({ ...prev, [key]: error?.message || "Invalid JSON object" }))
    }
  }

  const handleAttach = async () => {
    const moduleName = String(selectedModuleName || "").trim()
    if (!moduleName) return
    const created = await onAttachModule(moduleName)
    if (created) {
      setSelectedModuleName("")
    }
  }

  return (
    <div className="app-card p-6">
      <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">VI Modules</h2>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
            Attach reusable custom modules from the VI Modules portal. Domain-scoped modules auto-add the current service domain when possible.
          </p>
        </div>
        <Button variant="outline" className="h-10" onClick={refreshCatalog} disabled={loading}>
          <RefreshCw className="h-4 w-4" /> Refresh Modules
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
        <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900/40">
          <div className="space-y-2">
            <Label>Add Existing Module</Label>
            <select
              className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm dark:border-slate-700 dark:bg-slate-950"
              value={selectedModuleName}
              onChange={(e) => setSelectedModuleName(e.target.value)}
              disabled={loading}
            >
              <option value="">{loading ? "Loading modules..." : "Select a module"}</option>
              {selectableModules.map((module) => (
                <option key={module.name} value={module.name}>
                  {module.title || module.name} ({module.scope})
                </option>
              ))}
            </select>
          </div>
          <Button onClick={handleAttach} disabled={!selectedModuleName || loading} className="w-full">
            <Plus className="h-4 w-4" /> Attach Module
          </Button>
          <p className="text-xs text-slate-500 dark:text-slate-300">
            Available domains: {availableDomains.length ? availableDomains.join(", ") : "All currently visible domains"}
          </p>
        </div>

        <div className="space-y-4">
          {attachedModules.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-300 p-5 text-sm text-slate-600 dark:border-slate-700 dark:text-slate-300">
              No VI modules attached yet. Create or manage shared modules in the VI portal, then attach them here.
            </div>
          ) : (
            attachedModules.map((item) => {
              const moduleName = String(item?.name || "").trim()
              const moduleMeta = availableModules.find((candidate) => String(candidate?.name || "").trim() === moduleName) || {}
              return (
                <div key={moduleName} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-950/40">
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div>
                      <p className="text-base font-semibold text-slate-900 dark:text-slate-100">
                        {moduleMeta?.title || moduleName}
                      </p>
                      <p className="mt-1 text-xs uppercase tracking-[0.16em] text-sky-600 dark:text-sky-300">
                        {moduleMeta?.scope || "domain"} scope
                      </p>
                      <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                        {moduleMeta?.description || "Reusable VI module."}
                      </p>
                      {Array.isArray(moduleMeta?.assigned_domains) && moduleMeta.assigned_domains.length > 0 ? (
                        <p className="mt-2 text-xs text-slate-500 dark:text-slate-300">
                          Domains: {moduleMeta.assigned_domains.join(", ")}
                        </p>
                      ) : null}
                    </div>
                    <Button variant="outline" className="h-9" onClick={() => removeModule(moduleName)}>
                      <Trash2 className="h-4 w-4" /> Remove
                    </Button>
                  </div>

                  <div className="mt-4 space-y-2">
                    <Label>Service Config Overrides JSON</Label>
                    <JsonTextarea
                      value={configDrafts[moduleName] ?? JSON.stringify(item?.config || {}, null, 2)}
                      onChange={(e) => updateModuleConfig(moduleName, e.target.value)}
                      className={`min-h-[120px] font-mono text-sm ${configErrors[moduleName] ? "border-amber-500" : ""}`}
                      placeholder='{"defaultProvider":"cloudinary"}'
                    />
                    {configErrors[moduleName] ? (
                      <p className="text-sm text-amber-700 dark:text-amber-300">{configErrors[moduleName]}</p>
                    ) : (
                      <p className="text-xs text-slate-500 dark:text-slate-300">
                        Overrides are exposed to the module runtime as `module_config`.
                      </p>
                    )}
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}
