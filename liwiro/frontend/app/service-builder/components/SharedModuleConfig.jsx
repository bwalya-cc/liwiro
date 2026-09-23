// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

"use client"

import { useEffect, useMemo, useState } from "react"
import { Plus, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { JsonTextarea } from "@/components/ui/json-textarea"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { parseJsonLikeObject } from "@/lib/json-editor"

function normalizeSharedModules(sharedModules) {
  const source = sharedModules && typeof sharedModules === "object" && !Array.isArray(sharedModules)
    ? sharedModules
    : {}
  const out = {}
  Object.entries(source).forEach(([rawName, rawEntry]) => {
    const name = String(rawName || "").trim().toLowerCase()
    if (!name || !rawEntry || typeof rawEntry !== "object" || Array.isArray(rawEntry)) return
    out[name] = {
      title: String(rawEntry.title || name),
      description: String(rawEntry.description || ""),
      source: String(rawEntry.source || ""),
      scope: String(rawEntry.scope || "domain") === "global" ? "global" : "domain",
      serviceDomain: String(rawEntry.serviceDomain || rawEntry.service_domain || ""),
      configSchema: rawEntry.configSchema && typeof rawEntry.configSchema === "object" && !Array.isArray(rawEntry.configSchema)
        ? rawEntry.configSchema
        : rawEntry.config_schema && typeof rawEntry.config_schema === "object" && !Array.isArray(rawEntry.config_schema)
        ? rawEntry.config_schema
        : {},
      configDefaults: rawEntry.configDefaults && typeof rawEntry.configDefaults === "object" && !Array.isArray(rawEntry.configDefaults)
        ? rawEntry.configDefaults
        : rawEntry.config_defaults && typeof rawEntry.config_defaults === "object" && !Array.isArray(rawEntry.config_defaults)
        ? rawEntry.config_defaults
        : {},
    }
  })
  return out
}

export default function SharedModuleConfig({ config, updateConfig, serviceDomain = "" }) {
  const sharedModules = useMemo(() => normalizeSharedModules(config?.sharedModules || {}), [config?.sharedModules])
  const [newModuleName, setNewModuleName] = useState("")
  const [jsonErrors, setJsonErrors] = useState({})

  useEffect(() => {
    setJsonErrors((prev) => {
      const next = {}
      Object.keys(sharedModules).forEach((name) => {
        if (prev[name]) next[name] = prev[name]
      })
      return next
    })
  }, [sharedModules])

  const setSharedModules = (nextSharedModules) => {
    updateConfig("sharedModules", null, null, nextSharedModules)
  }

  const addSharedModule = () => {
    const name = String(newModuleName || "").trim().toLowerCase()
    if (!name) return
    if (!/^[a-z_][a-z0-9_]*$/.test(name)) return
    if (sharedModules[name]) return
    setSharedModules({
      ...sharedModules,
      [name]: {
        title: name,
        description: "",
        source: "",
        scope: "domain",
        serviceDomain: String(serviceDomain || "").trim().toLowerCase(),
        configSchema: {},
        configDefaults: {},
      },
    })
    setNewModuleName("")
  }

  const updateSharedModule = (moduleName, key, value) => {
    setSharedModules({
      ...sharedModules,
      [moduleName]: {
        ...(sharedModules[moduleName] || {}),
        [key]: value,
      },
    })
  }

  const updateJsonField = (moduleName, key, value) => {
    try {
      const parsed = value.trim() ? parseJsonLikeObject(value, `${moduleName} ${key}`) : {}
      setJsonErrors((prev) => ({ ...prev, [moduleName]: "" }))
      updateSharedModule(moduleName, key, parsed)
    } catch (error) {
      setJsonErrors((prev) => ({ ...prev, [moduleName]: error?.message || "Invalid JSON object" }))
    }
  }

  const removeSharedModule = (moduleName) => {
    const next = { ...sharedModules }
    delete next[moduleName]
    setSharedModules(next)
  }

  return (
    <div className="app-card p-6">
      <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Shared Versa Modules</h2>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
            Define reusable modules once, publish them into VDB, then import them from multiple routes and services without duplicating Versa source.
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900/40">
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
          <Input
            value={newModuleName}
            onChange={(e) => setNewModuleName(e.target.value.toLowerCase())}
            placeholder="shared_module_name"
          />
          <Button onClick={addSharedModule} disabled={!newModuleName.trim()}>
            <Plus className="h-4 w-4" /> Add Shared Module
          </Button>
        </div>
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-300">
          Shared modules are stored centrally in VDB and can also be attached below for per-service `module_config` overrides.
        </p>
      </div>

      <div className="mt-5 space-y-4">
        {Object.keys(sharedModules).length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-300 p-5 text-sm text-slate-600 dark:border-slate-700 dark:text-slate-300">
            No shared modules defined yet. Add one above to publish reusable Versa code alongside this service config.
          </div>
        ) : (
          Object.entries(sharedModules).map(([moduleName, module]) => (
            <div key={moduleName} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-950/40">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <p className="text-base font-semibold text-slate-900 dark:text-slate-100">{moduleName}</p>
                  <p className="mt-1 text-xs uppercase tracking-[0.16em] text-sky-600 dark:text-sky-300">
                    {module.scope || "domain"} scope
                  </p>
                </div>
                <Button variant="outline" className="h-9" onClick={() => removeSharedModule(moduleName)}>
                  <Trash2 className="h-4 w-4" /> Remove
                </Button>
              </div>

              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label>Display Title</Label>
                  <Input
                    value={module.title || ""}
                    onChange={(e) => updateSharedModule(moduleName, "title", e.target.value)}
                    placeholder="My Shared Module"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Scope</Label>
                  <select
                    className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm dark:border-slate-700 dark:bg-slate-950"
                    value={module.scope || "domain"}
                    onChange={(e) => updateSharedModule(moduleName, "scope", e.target.value === "global" ? "global" : "domain")}
                  >
                    <option value="domain">domain</option>
                    <option value="global">global</option>
                  </select>
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label>Description</Label>
                  <Input
                    value={module.description || ""}
                    onChange={(e) => updateSharedModule(moduleName, "description", e.target.value)}
                    placeholder="Reusable Versa helpers for..."
                  />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label>Service Domain</Label>
                  <Input
                    value={module.serviceDomain || String(serviceDomain || "").trim().toLowerCase()}
                    onChange={(e) => updateSharedModule(moduleName, "serviceDomain", e.target.value.toLowerCase())}
                    placeholder={String(serviceDomain || "service-domain").trim().toLowerCase()}
                  />
                </div>
              </div>

              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                <div className="space-y-2">
                  <Label>Config Schema JSON</Label>
                  <JsonTextarea
                    value={JSON.stringify(module.configSchema || {}, null, 2)}
                    onChange={(e) => updateJsonField(moduleName, "configSchema", e.target.value)}
                    className={`min-h-[140px] font-mono text-sm ${jsonErrors[moduleName] ? "border-amber-500" : ""}`}
                    placeholder='{"apiKey":{"type":"string"}}'
                  />
                </div>
                <div className="space-y-2">
                  <Label>Default Config JSON</Label>
                  <JsonTextarea
                    value={JSON.stringify(module.configDefaults || {}, null, 2)}
                    onChange={(e) => updateJsonField(moduleName, "configDefaults", e.target.value)}
                    className={`min-h-[140px] font-mono text-sm ${jsonErrors[moduleName] ? "border-amber-500" : ""}`}
                    placeholder='{"defaultProvider":"cloudinary"}'
                  />
                </div>
              </div>

              {jsonErrors[moduleName] ? (
                <p className="mt-2 text-sm text-amber-700 dark:text-amber-300">{jsonErrors[moduleName]}</p>
              ) : null}

              <div className="mt-4 space-y-2">
                <Label>Module Source (.versa)</Label>
                <Textarea
                  value={module.source || ""}
                  onChange={(e) => updateSharedModule(moduleName, "source", e.target.value)}
                  className="min-h-[18rem] font-mono text-sm leading-6"
                  placeholder={"func hello(name) {\n  return \"hello \" + name;\n}"}
                />
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
