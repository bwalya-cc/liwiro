// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import { Input } from "@/components/ui/input"
import PasswordInput from "@/components/ui/password-input"
import { Label } from "@/components/ui/label"
import { JsonTextarea } from "@/components/ui/json-textarea"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { parseJsonLikeObject } from "@/lib/json-editor"
import { generateLiwiroKey } from "@/lib/service-keys"
import {
  applyMediaStorageEnvPreset,
  envObjectToText,
  MEDIA_STORAGE_ENV_PRESETS,
  parseEnvText,
} from "@/lib/media-storage-presets"
import { useEffect, useState } from "react"
import { ChevronDown, RefreshCw } from "lucide-react"


export default function MetadataConfig({ config, updateConfig }) {
  const [seedCollectionsText, setSeedCollectionsText] = useState(
    JSON.stringify(config.metadata.seedData?.collections || {}, null, 2)
  )
  const [envText, setEnvText] = useState(envObjectToText(config.metadata.env || {}))
  const [isEnvOpen, setIsEnvOpen] = useState(false)
  const [isSetupConfigOpen, setIsSetupConfigOpen] = useState(false)

  useEffect(() => {
    setSeedCollectionsText(JSON.stringify(config.metadata.seedData?.collections || {}, null, 2))
  }, [config.metadata.seedData?.collections])
  useEffect(() => {
    setEnvText(envObjectToText(config.metadata.env || {}))
  }, [config.metadata.env])

  const updateSeedCollections = (value) => {
    setSeedCollectionsText(value)
    try {
      const parsed = value.trim() ? parseJsonLikeObject(value, "Seed collections") : {}
      updateConfig("metadata", null, "seedData", {
        ...config.metadata.seedData,
        collections: parsed && typeof parsed === "object" ? parsed : {},
      })
    } catch {
      updateConfig("metadata", null, "seedData", {
        ...config.metadata.seedData,
        collections: config.metadata.seedData?.collections || {},
      })
    }
  }

  const updateServiceEnv = (value) => {
    setEnvText(value)
    updateConfig("metadata", null, "env", parseEnvText(value))
  }

  const applyEnvPreset = (presetId) => {
    const nextEnv = applyMediaStorageEnvPreset(config.metadata.env || {}, presetId)
    setEnvText(envObjectToText(nextEnv))
    updateConfig("metadata", null, "env", nextEnv)
    setIsEnvOpen(true)
  }

  const generateSetupApiKey = () => {
    updateConfig("metadata", null, "setupApiKey", generateLiwiroKey("liwiro_setup_"))
  }

  const generateDocumentationKey = () => {
    updateConfig("metadata", null, "documentation", {
      ...(config.metadata.documentation || {}),
      key: generateLiwiroKey("liwiro_docs_"),
    })
  }

  return (
    <div className="app-card p-6">
      <h2 className="mb-5 text-xl font-semibold text-slate-900 dark:text-slate-100">API Metadata</h2>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label>API Name</Label>
          <Input
            placeholder="My API Service"
            value={config.metadata.apiName}
            onChange={(e) => updateConfig("metadata", null, "apiName", e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label>Base Path</Label>
          <Input
            placeholder="/api/v1"
            value={config.metadata.basePath}
            onChange={(e) => updateConfig("metadata", null, "basePath", e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label>API Version</Label>
          <Input
            placeholder="1.0.0"
            value={config.metadata.version}
            onChange={(e) => updateConfig("metadata", null, "version", e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label>Service Database</Label>
          <Input
            placeholder="main"
            value={config.metadata.database || "main"}
            onChange={(e) => updateConfig("metadata", null, "database", e.target.value)}
          />
        </div>
        <div className="space-y-2 md:col-span-2">
          <Label>Developer Notes</Label>
          <Textarea
            placeholder="Notes for operators/developers shown in service docs."
            value={config.metadata.developerNotes || ""}
            onChange={(e) => updateConfig("metadata", null, "developerNotes", e.target.value)}
            className="min-h-[92px]"
          />
        </div>
        <div className="space-y-2 md:col-span-2">
          <Collapsible open={isSetupConfigOpen} onOpenChange={setIsSetupConfigOpen}>
            <div className="rounded-md border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-900/50">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <Label className="text-sm">Setup Config</Label>
                  <p className="text-xs text-slate-500 dark:text-slate-300">
                    Toggle setup keys, docs access, and seeding fields for `/liwiro/setup` and `/liwiro/docs`.
                  </p>
                </div>
                <CollapsibleTrigger asChild>
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 rounded border px-2 py-1 text-xs text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
                  >
                    {isSetupConfigOpen ? "Hide Setup Config" : "Show Setup Config"}
                    <ChevronDown className={`h-3.5 w-3.5 transition-transform ${isSetupConfigOpen ? "rotate-180" : ""}`} />
                  </button>
                </CollapsibleTrigger>
              </div>
              <CollapsibleContent className="pt-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label>Setup API Key</Label>
                    <PasswordInput
                      placeholder="Shared key for setup endpoints"
                      value={config.metadata.setupApiKey || ""}
                      onChange={(e) => updateConfig("metadata", null, "setupApiKey", e.target.value)}
                      actions={[
                        {
                          key: "generate-setup-key",
                          label: "Generate setup API key",
                          onClick: generateSetupApiKey,
                          icon: <RefreshCw className="h-4 w-4" />,
                        },
                      ]}
                    />
                    <p className="text-xs text-slate-500 dark:text-slate-300">
                      Used by `/liwiro/setup/reset-super-admin` and `/liwiro/setup/seed-db`.
                    </p>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label>Seed Service Database</Label>
                      <Switch
                        checked={config.metadata.seedData?.enabled || false}
                        onCheckedChange={(checked) =>
                          updateConfig("metadata", null, "seedData", { ...config.metadata.seedData, enabled: checked })
                        }
                      />
                    </div>
                    <p className="text-xs text-slate-500 dark:text-slate-300">
                      Enables `POST /liwiro/setup/seed-db`.
                    </p>
                  </div>
                  {config.metadata.seedData?.enabled && (
                    <div className="space-y-2 md:col-span-2">
                      <Label>Seed Collections JSON</Label>
                      <JsonTextarea
                        value={seedCollectionsText}
                        onChange={(e) => updateSeedCollections(e.target.value)}
                        className="min-h-[140px] font-mono text-sm"
                        placeholder='{"users":[{"username":"demo"}]}'
                      />
                      <p className="text-xs text-slate-500 dark:text-slate-300">
                        Use model name or collection name as keys; values must be arrays of documents.
                      </p>
                    </div>
                  )}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label>Service Documentation</Label>
                      <Switch
                        checked={config.metadata.documentation?.enabled !== false}
                        onCheckedChange={(checked) =>
                          updateConfig("metadata", null, "documentation", {
                            ...(config.metadata.documentation || {}),
                            enabled: checked,
                          })
                        }
                      />
                    </div>
                    <p className="text-xs text-slate-500 dark:text-slate-300">
                      When disabled, `/liwiro/docs` is unavailable for this service.
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label>Documentation Key</Label>
                    <PasswordInput
                      placeholder="Service-specific key for /liwiro/docs"
                      value={config.metadata.documentation?.key || ""}
                      onChange={(e) =>
                        updateConfig("metadata", null, "documentation", {
                          ...(config.metadata.documentation || {}),
                          key: e.target.value,
                        })
                      }
                      actions={[
                        {
                          key: "generate-documentation-key",
                          label: "Generate documentation key",
                          onClick: generateDocumentationKey,
                          icon: <RefreshCw className="h-4 w-4" />,
                        },
                      ]}
                    />
                    <p className="text-xs text-slate-500 dark:text-slate-300">
                      Set this during creation. It protects docs for this service only.
                    </p>
                  </div>
                </div>
              </CollapsibleContent>
            </div>
          </Collapsible>
        </div>
        <div className="space-y-2 md:col-span-2">
          <Collapsible open={isEnvOpen} onOpenChange={setIsEnvOpen}>
            <div className="rounded-md border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-900/50">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <Label className="text-sm">Service Environment (.env)</Label>
                  <p className="text-xs text-slate-500 dark:text-slate-300">
                    Scripts can read these values via `service.env.MY_KEY`.
                  </p>
                </div>
                <CollapsibleTrigger asChild>
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 rounded border px-2 py-1 text-xs text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
                  >
                    {isEnvOpen ? "Hide" : "Edit"}
                    <ChevronDown className={`h-3.5 w-3.5 transition-transform ${isEnvOpen ? "rotate-180" : ""}`} />
                  </button>
                </CollapsibleTrigger>
              </div>
              <CollapsibleContent className="pt-3">
                <div className="mb-3 flex flex-wrap gap-2">
                  {MEDIA_STORAGE_ENV_PRESETS.map((preset) => (
                    <button
                      key={preset.id}
                      type="button"
                      className="rounded border border-sky-300/25 bg-sky-500/10 px-2.5 py-1 text-xs font-medium text-sky-700 transition hover:bg-sky-500/20 dark:text-sky-200"
                      onClick={() => applyEnvPreset(preset.id)}
                      title={preset.description}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
                <Textarea
                  value={envText}
                  onChange={(e) => updateServiceEnv(e.target.value)}
                  className="min-h-[150px] font-mono text-sm"
                  placeholder={"EMAIL_SMTP_HOST=smtp.gmail.com\nEMAIL_SMTP_PORT=587\nEMAIL_SMTP_STARTTLS=true"}
                />
                <p className="mt-2 text-xs text-slate-500 dark:text-slate-300">
                  Format: one `KEY=value` per line. Values are auto-typed for booleans and numbers.
                </p>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-300">
                  Media preset buttons insert placeholder values only. Replace them with real provider credentials before testing.
                </p>
              </CollapsibleContent>
            </div>
          </Collapsible>
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>Rate Limiting</Label>
            <Switch
              checked={config.metadata.rateLimiting.enabled}
              onCheckedChange={(checked) => updateConfig("metadata", null, "rateLimiting", {
                ...config.metadata.rateLimiting,
                enabled: checked,
              })}
            />
          </div>
          {config.metadata.rateLimiting.enabled && (
            <div className="flex gap-2 mt-2">
              <Input
                type="number"
                value={config.metadata.rateLimiting.limit}
                onChange={(e) => updateConfig("metadata", null, "rateLimiting", {
                  ...config.metadata.rateLimiting,
                  limit: parseInt(e.target.value),
                })}
              />
              <Select
                value={config.metadata.rateLimiting.timeframe}
                onValueChange={(value) => updateConfig("metadata", null, "rateLimiting", {
                  ...config.metadata.rateLimiting,
                  timeframe: value,
                })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="second">Per Second</SelectItem>
                  <SelectItem value="minute">Per Minute</SelectItem>
                  <SelectItem value="hour">Per Hour</SelectItem>
                  <SelectItem value="day">Per Day</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
