// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

"use client"

import { useCallback, useEffect, useState } from "react"
import { AlertTriangle, CheckCircle2, KeyRound, Loader2, PlugZap, ShieldCheck, Trash2 } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import PasswordInput from "@/components/ui/password-input"
import { authHeaders } from "@/lib/auth"
import { invalidateAuthedJsonCache } from "@/lib/authed-json-cache"
import { invalidateVerseBootstrap } from "@/lib/verse-bootstrap"

const PROVIDER_COPY = {
  openai: { description: "OpenAI Responses API", keyPlaceholder: "sk-…" },
  google: { description: "Google Gemini API", keyPlaceholder: "AIza…" },
  anthropic: { description: "Anthropic Messages API", keyPlaceholder: "sk-ant-…" },
}

function buildDraft(payload) {
  return {
    defaultProvider: String(payload?.defaultProvider || "openai"),
    providers: Object.fromEntries((payload?.providers || []).map((provider) => [provider.id, {
      ...provider,
      apiKey: "",
      removeApiKey: false,
    }])),
  }
}

export default function AiSetupPage() {
  const backend = process.env.NEXT_PUBLIC_LIWIRO_BACKEND || "http://127.0.0.1:5000"
  const [config, setConfig] = useState(null)
  const [draft, setDraft] = useState({ defaultProvider: "openai", providers: {} })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testingProvider, setTestingProvider] = useState("")
  const [testResults, setTestResults] = useState({})

  const loadConfig = useCallback(async () => {
    setLoading(true)
    try {
      const response = await fetch(`${backend}/platform/ai/config`, { headers: authHeaders() })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.error || "Failed to load AI configuration")
      setConfig(payload)
      setDraft(buildDraft(payload))
    } catch (error) {
      toast.error(error?.message || "Failed to load AI configuration")
    } finally {
      setLoading(false)
    }
  }, [backend])

  useEffect(() => { loadConfig() }, [loadConfig])

  const updateProvider = (providerId, patch) => {
    setTestResults((current) => ({ ...current, [providerId]: null }))
    setDraft((current) => ({
      ...current,
      providers: {
        ...current.providers,
        [providerId]: { ...(current.providers[providerId] || {}), ...patch },
      },
    }))
  }

  const saveConfig = async () => {
    if (!config?.canManage) return
    setSaving(true)
    try {
      const providers = Object.fromEntries(Object.entries(draft.providers).map(([providerId, provider]) => {
        const payload = { model: String(provider?.model || "").trim() }
        if (provider?.removeApiKey) payload.removeApiKey = true
        else if (String(provider?.apiKey || "").trim()) payload.apiKey = String(provider.apiKey).trim()
        return [providerId, payload]
      }))
      const response = await fetch(`${backend}/platform/ai/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ defaultProvider: draft.defaultProvider, providers }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.error || "Failed to save AI configuration")
      setConfig(payload)
      setDraft(buildDraft(payload))
      setTestResults({})
      invalidateAuthedJsonCache(`${backend}/auth/me`)
      invalidateVerseBootstrap(backend)
      window.dispatchEvent(new CustomEvent("liwiro:ai-config-updated", { detail: payload }))
      toast.success("AI configuration saved. Checking provider connections…")
      await Promise.all((payload.providers || []).filter((provider) => provider.configured).map((provider) => testConnection(provider.id, { model: provider.model })))
    } catch (error) {
      toast.error(error?.message || "Failed to save AI configuration")
    } finally {
      setSaving(false)
    }
  }

  const testConnection = async (providerId, saved = null) => {
    setTestingProvider(providerId)
    setTestResults((current) => ({ ...current, [providerId]: null }))
    try {
      const response = await fetch(`${backend}/platform/ai/config/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ provider: providerId, model: saved?.model || draft.providers[providerId]?.model, ...(!saved && draft.providers[providerId]?.apiKey ? { apiKey: draft.providers[providerId].apiKey } : {}) }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload?.error || "Connection test failed")
      setTestResults((current) => ({ ...current, [providerId]: { ok: true, message: `Verified with ${payload.model || "the configured model"}.` } }))
      toast.success(`${draft.providers[providerId]?.label || providerId} connection verified`)
    } catch (error) {
      setTestResults((current) => ({ ...current, [providerId]: { ok: false, message: error?.message || "Connection test failed" } }))
    } finally {
      setTestingProvider("")
    }
  }

  if (loading) {
    return <div className="app-page flex min-h-[45vh] items-center justify-center text-sm text-slate-300"><Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading AI configuration…</div>
  }

  if (!config) {
    return <div className="app-page py-8 text-sm text-slate-300">AI configuration could not be loaded.</div>
  }

  const providers = Object.values(draft.providers)

  return (
    <div className="app-page space-y-6 py-6">
      <section className="app-hero">
        <div>
          <p className="app-eyebrow">Agents</p>
          <h1 className="app-title">AI Setup</h1>
          <p className="app-subtitle">Choose the default Verse provider and manage its shared model and API credentials.</p>
        </div>
        <div className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${config.configured ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200" : "border-amber-400/30 bg-amber-400/10 text-amber-100"}`}>
          {testResults[config.defaultProvider]?.ok ? "Connection verified" : config.configured ? "Key saved" : "Setup required"}
        </div>
      </section>

      {!config.canManage ? (
        <div className="flex items-start gap-3 rounded-xl border border-amber-400/25 bg-amber-400/[0.08] p-4 text-amber-100">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <div><p className="font-semibold">Super admin access required</p><p className="mt-1 text-sm text-amber-100/80">Ask a Liwiro super admin to configure or test the shared AI credentials.</p></div>
        </div>
      ) : null}

      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><KeyRound className="h-5 w-5" /> Default provider</CardTitle></CardHeader>
        <CardContent>
          <Label htmlFor="default-ai-provider">Provider used for new Verse conversations</Label>
          <select
            id="default-ai-provider"
            value={draft.defaultProvider}
            disabled={!config.canManage || saving}
            onChange={(event) => setDraft((current) => ({ ...current, defaultProvider: event.target.value }))}
            className="mt-2 h-10 w-full max-w-md rounded-md border border-input bg-background px-3 text-sm text-foreground"
          >
            {providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.label}</option>)}
          </select>
        </CardContent>
      </Card>

      <div className="grid gap-5 xl:grid-cols-3">
        {providers.map((provider) => {
          const result = testResults[provider.id]
          const effectiveConfigured = provider.removeApiKey ? false : provider.configured || Boolean(String(provider.apiKey || "").trim())
          return (
            <Card key={provider.id} className={draft.defaultProvider === provider.id ? "border-sky-400/35" : ""}>
              <CardHeader>
                <div className="flex items-start justify-between gap-3">
                  <div><CardTitle>{provider.label}</CardTitle><p className="mt-1 text-sm text-slate-400">{PROVIDER_COPY[provider.id]?.description}</p></div>
                  {effectiveConfigured ? <CheckCircle2 className="h-5 w-5 text-emerald-300" /> : <AlertTriangle className="h-5 w-5 text-amber-300" />}
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div><Label htmlFor={`${provider.id}-model`}>Model</Label><Input id={`${provider.id}-model`} className="mt-2" value={provider.model || ""} disabled={!config.canManage || saving} onChange={(event) => updateProvider(provider.id, { model: event.target.value })} /></div>
                <div>
                  <Label htmlFor={`${provider.id}-key`}>{provider.configured ? "Replace API key" : "API key"}</Label>
                  <PasswordInput id={`${provider.id}-key`} className="mt-2" autoComplete="new-password" placeholder={PROVIDER_COPY[provider.id]?.keyPlaceholder || "Enter API key"} value={provider.apiKey || ""} disabled={!config.canManage || saving || provider.removeApiKey} onChange={(event) => updateProvider(provider.id, { apiKey: event.target.value, removeApiKey: false })} />
                  <p className="mt-2 text-xs text-slate-400">{provider.configured ? "A key is saved. Its value is never returned to the browser." : "No key is currently saved."}</p>
                </div>
                {provider.configured && config.canManage ? (
                  <Button type="button" variant={provider.removeApiKey ? "outline" : "ghost"} className="w-full" disabled={saving} onClick={() => updateProvider(provider.id, { removeApiKey: !provider.removeApiKey, apiKey: "" })}>
                    <Trash2 className="mr-2 h-4 w-4" /> {provider.removeApiKey ? "Keep saved key" : "Remove saved key on save"}
                  </Button>
                ) : null}
                <Button type="button" variant="outline" className="w-full" disabled={!config.canManage || !effectiveConfigured || saving || testingProvider === provider.id || provider.removeApiKey} onClick={() => testConnection(provider.id)}>
                  {testingProvider === provider.id ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <PlugZap className="mr-2 h-4 w-4" />} Test connection
                </Button>
                {result ? <p className={`text-sm ${result.ok ? "text-emerald-300" : "text-rose-300"}`}>{result.message}</p> : null}
              </CardContent>
            </Card>
          )
        })}
      </div>

      {config.canManage ? (
        <div className="flex flex-col gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3"><ShieldCheck className="mt-0.5 h-5 w-5 text-sky-300" /><div><p className="text-sm font-semibold text-white">Credentials are stored on this Liwiro server</p><p className="mt-1 text-xs text-slate-400">Saving checks each configured provider with a real generation request. You can also test a key before saving it.</p></div></div>
          <Button onClick={saveConfig} disabled={saving}>{saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}Save AI Configuration</Button>
        </div>
      ) : null}
    </div>
  )
}
