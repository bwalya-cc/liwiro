// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import { RefreshCw, Copy, Download } from "lucide-react"
import { Button } from "@/components/ui/button"
import { CopyIconButton } from "@/components/ui/copy-icon-button"
import { summarizeMediaCapabilities } from "@/lib/media-storage-presets"
import { toast } from "sonner"

export default function PreviewConfig({ config, setActiveTab }) {
  const mediaCapabilities = summarizeMediaCapabilities(config)
  const mediaProviders = mediaCapabilities.providers || []
  const attachedModules = Array.isArray(config?.modules) ? config.modules : []
  const enhancedConfig = {
    ...config,
    endpoints: Object.fromEntries(
      Object.entries(config.endpoints).map(([id, ep]) => [
        id, 
        {
          ...ep,
          parameters: ep.parameters?.map(p => ({
            name: p.name,
            in: p.in,
            type: p.type,
            required: p.required
          }))
        }
      ])
    )
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(config, null, 2))
      toast.success("Configuration copied to clipboard")
    } catch (err) {
      toast.error("Failed to copy configuration")
    }
  }

  const handleDownload = () => {
    const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${config.metadata.apiName}-lapis-config.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div className="app-card p-6">
      <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Configuration Preview</h2>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            className="border-slate-300 bg-white text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
            onClick={() => setActiveTab("config")}
          >
            <RefreshCw className="h-4 w-4 mr-1" /> Refresh
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="border-slate-300 bg-white text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
            onClick={handleCopy}
          >
            <Copy className="h-4 w-4 mr-1" /> Copy
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="border-slate-300 bg-white text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
            onClick={handleDownload}
          >
            <Download className="h-4 w-4 mr-1" /> Download
          </Button>
        </div>
      </div>
      {mediaCapabilities.enabled && (
        <div className="mb-5 grid gap-4 md:grid-cols-3">
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900/50">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-600 dark:text-sky-300">Media Providers</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {mediaProviders.map((provider) => (
                <span
                  key={provider.id}
                  className={`rounded-full border px-2.5 py-1 text-xs font-medium ${
                    provider.ready
                      ? "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-700/50 dark:bg-emerald-950/40 dark:text-emerald-200"
                      : "border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-700/50 dark:bg-amber-950/40 dark:text-amber-200"
                  }`}
                >
                  {provider.label}
                  {provider.default ? " • default" : ""}
                </span>
              ))}
            </div>
            <p className="mt-3 text-xs text-slate-500 dark:text-slate-300">
              Provider summaries are inferred from `metadata.env` and script-backed upload routes.
            </p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900/50">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-600 dark:text-sky-300">Storage Model</p>
            <p className="mt-3 text-lg font-semibold text-slate-900 dark:text-slate-100">{mediaCapabilities.assetCollection || "media_assets"}</p>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
              Asset collection
            </p>
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-300">
              {mediaCapabilities.serviceEnvKeys.length} service.env keys configured in this LAPIS draft.
            </p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900/50">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-600 dark:text-sky-300">Testing Inputs</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {(mediaCapabilities.inputModes || []).map((mode) => (
                <code key={mode} className="rounded bg-slate-200 px-2 py-1 text-[11px] text-slate-800 dark:bg-slate-800 dark:text-slate-100">
                  {mode}
                </code>
              ))}
            </div>
            <p className="mt-3 text-xs text-slate-500 dark:text-slate-300">
              Media routes are tested with JSON bodies. Use `sourceUrl`, `dataUri`, `dataBase64`, or `textBody` instead of multipart uploads.
            </p>
          </div>
        </div>
      )}
      {attachedModules.length > 0 && (
        <div className="mb-5 rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900/50">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-600 dark:text-sky-300">Attached VI Modules</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {attachedModules.map((module) => (
              <span
                key={String(module?.name || "")}
                className="rounded-full border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-700 dark:border-slate-700 dark:text-slate-200"
              >
                {String(module?.name || "")}
              </span>
            ))}
          </div>
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-300">
            Service-level module config overrides are stored in the top-level `modules` array and exposed to Versa at runtime through `module_config`.
          </p>
        </div>
      )}
      <div className="relative">
        <CopyIconButton
          text={JSON.stringify(enhancedConfig, null, 2)}
          label="Copy configuration preview"
          successMessage="Configuration copied to clipboard"
          errorMessage="Failed to copy configuration"
          className="absolute right-3 top-3 border-white/10 bg-slate-900/90 text-slate-100 hover:bg-slate-800 hover:text-white"
        />
        <pre className="max-h-[640px] overflow-auto rounded-lg border border-slate-800 bg-slate-950 p-4 text-slate-100 shadow-inner dark:border-slate-700 dark:bg-black dark:text-slate-100">
          {JSON.stringify(enhancedConfig, null, 2)}
        </pre>
      </div>
    </div>
  )
}
