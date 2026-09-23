// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

"use client"

import { useEffect, useMemo, useState, useCallback, useRef } from "react"
import { useParams, useRouter } from "next/navigation"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { CopyIconButton } from "@/components/ui/copy-icon-button"
import { JsonTextarea } from "@/components/ui/json-textarea"
import { Textarea } from "@/components/ui/textarea"
import { Input } from "@/components/ui/input"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import SharedModuleConfig from "@/app/service-builder/components/SharedModuleConfig"
import ModuleConfig from "@/app/service-builder/components/ModuleConfig"
import PasswordInput from "@/components/ui/password-input"
import { authHeaders } from "@/lib/auth"
import { fetchAuthedJson } from "@/lib/authed-json-cache"
import { parseJsonLikeObject, parseJsonLikeText } from "@/lib/json-editor"
import { generateCollectionNameFromModelName } from "@/lib/model-naming"
import { generateLiwiroKey } from "@/lib/service-keys"
import {
  applyMediaStorageEnvPreset,
  buildMediaStorageScriptTemplate,
  envObjectToText,
  MEDIA_STORAGE_ENV_PRESETS,
  MEDIA_STORAGE_SCRIPT_PRESETS,
  parseEnvText,
  summarizeMediaCapabilities,
} from "@/lib/media-storage-presets"
import { resolveServiceLinks } from "@/lib/service-links"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { ChevronDown, ChevronRight, Loader2, Plus, RefreshCw, Trash2 } from "lucide-react"
import { toast } from "sonner"

const PANEL_GROUPS = [
  {
    title: "Service",
    items: [
      { id: "overview", label: "Overview", hint: "Runtime, links, status, controls" },
      { id: "env", label: "Environment", hint: "service.env keys and media presets" },
      { id: "notes", label: "Developer Notes", hint: "Docs-facing notes" },
      { id: "keys", label: "Setup & Docs Keys", hint: "Bootstrap and documentation secrets" },
    ],
  },
  {
    title: "Auth",
    items: [
      { id: "auth", label: "Auth Config", hint: "JWT and auth-service wiring" },
      { id: "testing", label: "Route Testing", hint: "Protected route auth and responses" },
    ],
  },
  {
    title: "Structure",
    items: [
      { id: "models", label: "Models", hint: "Structured collection schema editor" },
      { id: "endpoints", label: "Endpoints", hint: "Routes, VQL, and Versas" },
      { id: "modules", label: "VI Modules", hint: "Attach shared Versa modules to this service" },
      { id: "config", label: "Raw LAPIS Config", hint: "Full JSON editor" },
    ],
  },
]

const PANEL_EDITOR_MODES = {
  overview: ["structured", "text"],
  env: ["structured", "text"],
  notes: ["structured", "text"],
  keys: ["structured", "text"],
  auth: ["structured", "text"],
  testing: ["structured", "text"],
  models: ["structured", "text"],
  endpoints: ["structured", "text"],
  modules: ["structured", "text"],
  config: ["structured", "text"],
}

const normalizeOperationType = (value) => {
  const token = String(value || "").trim().toLowerCase().replaceAll("-", "_")
  const aliases = {
    crud: "crud",
    resource: "crud",
    rest: "crud",
    custom: "custom",
    query: "custom",
    vql: "custom",
    script: "script",
    versa: "script",
    code: "script",
  }
  return aliases[token] || token
}

const normalizeCrudOperation = (value) => {
  const token = String(value || "").trim().toLowerCase().replaceAll("-", "_")
  const aliases = {
    create: "create",
    create_one: "create",
    create_many: "create",
    post: "create",
    insert: "create",
    read: "read",
    read_one: "read",
    read_many: "read",
    get: "read",
    get_one: "read",
    get_many: "read",
    list: "read",
    fetch: "read",
    fetch_one: "read",
    fetch_many: "read",
    query: "read",
    update: "update",
    update_one: "update",
    update_many: "update",
    put: "update",
    patch: "update",
    edit: "update",
    delete: "delete",
    delete_one: "delete",
    delete_many: "delete",
    remove: "delete",
    remove_one: "delete",
    remove_many: "delete",
  }
  return aliases[token] || token
}

const PANEL_GROUP_DEFAULTS = {
  Service: true,
  Auth: true,
  Structure: true,
}

const PANEL_ITEMS = PANEL_GROUPS.flatMap((group) => group.items)

function makePairId() {
  return `pair_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

function toFieldDrafts(fieldsObj) {
  const entries = Object.entries(fieldsObj || {})
  return entries.map(([fieldId, field]) => {
    const source = field || {}
    return {
      id: String(source.id || fieldId),
      name: String(source.name || ""),
      type: String(source.type || "string"),
      required: Boolean(source.required),
      unique: Boolean(source.unique),
      relationModel: String(source.relationModel || source.ref || ""),
      relationType: String(source.relationType || ""),
      rawField: source,
    }
  })
}

function objectToPairs(obj) {
  const entries = Object.entries(obj || {})
  if (entries.length === 0) return [{ id: makePairId(), key: "", value: "" }]
  return entries.map(([key, value]) => ({
    id: makePairId(),
    key: String(key || ""),
    value: value == null ? "" : (typeof value === "string" ? value : JSON.stringify(value)),
  }))
}

function toEndpointDraftEntries(endpointsObj) {
  return Object.entries(endpointsObj || {}).map(([id, ep]) => ({
    id,
    enabled: ep?.enabled !== false,
    ...(ep || {}),
    path: String(ep?.path || "").trim() || "/",
    queryPairs: objectToPairs((ep || {}).exampleParams?.query || {}),
    bodyPairs: objectToPairs((ep || {}).exampleParams?.body || {}),
    exampleBearer: String(
      (ep || {}).exampleParams?.headers?.Authorization
      || (ep || {}).exampleParams?.headers?.authorization
      || "",
    ).replace(/^Bearer\s+/i, ""),
  }))
}

function toModelDraftEntries(modelsObj) {
  return Object.entries(modelsObj || {}).map(([id, model]) => ({
    id,
    ...(model || {}),
    fieldsDrafts: toFieldDrafts((model || {}).fields || {}),
  }))
}

function normalizeServiceModules(modules) {
  const normalized = []
  const seen = new Set()

  ;(Array.isArray(modules) ? modules : []).forEach((item) => {
    if (!item || typeof item !== "object") return
    const name = String(item.name || "").trim().toLowerCase()
    if (!name || seen.has(name)) return
    seen.add(name)
    normalized.push({
      name,
      config: item.config && typeof item.config === "object" && !Array.isArray(item.config) ? item.config : {},
    })
  })

  return normalized
}

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

export default function ServiceDetailPage() {
  const params = useParams()
  const router = useRouter()
  const processId = useMemo(() => String(params?.id || ""), [params])
  const backend = process.env.NEXT_PUBLIC_LIWIRO_BACKEND || "http://127.0.0.1:5000"

  const [service, setService] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [configText, setConfigText] = useState("")
  const [serviceEnvText, setServiceEnvText] = useState("")
  const [developerNotes, setDeveloperNotes] = useState("")
  const [error, setError] = useState("")
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [setupApiKey, setSetupApiKey] = useState("")
  const [documentationKey, setDocumentationKey] = useState("")
  const [docsKeyConfigured, setDocsKeyConfigured] = useState(false)
  const [endpointDrafts, setEndpointDrafts] = useState([])
  const [modelDrafts, setModelDrafts] = useState([])
  const [sharedModuleDrafts, setSharedModuleDrafts] = useState({})
  const [moduleDrafts, setModuleDrafts] = useState([])
  const [availableModules, setAvailableModules] = useState([])
  const [availableModuleDomains, setAvailableModuleDomains] = useState([])
  const [modulesLoading, setModulesLoading] = useState(false)
  const [collapsedModels, setCollapsedModels] = useState({})
  const [collapsedEndpoints, setCollapsedEndpoints] = useState({})
  const [collapsedCustomVql, setCollapsedCustomVql] = useState({})
  const [authDraft, setAuthDraft] = useState({})
  const [authDependencyService, setAuthDependencyService] = useState(null)
  const [authBootstrapCreds, setAuthBootstrapCreds] = useState({ username: "", email: "", password: "", role: "SUPER_ADMIN" })
  const [authProfileChoice, setAuthProfileChoice] = useState("")
  const [routeDrafts, setRouteDrafts] = useState({})
  const [authToken, setAuthToken] = useState("")
  const [setupRunning, setSetupRunning] = useState(false)
  const [authenticating, setAuthenticating] = useState(false)
  const [downloadingAuthKeys, setDownloadingAuthKeys] = useState(false)
  const [lapisFullHeight, setLapisFullHeight] = useState(false)
  const [canManageServices, setCanManageServices] = useState(false)
  const [deleteDataWithService, setDeleteDataWithService] = useState(true)
  const [activePanel, setActivePanel] = useState("overview")
  const [editorMode, setEditorMode] = useState("structured")
  const [panelDirection, setPanelDirection] = useState("vertical")
  const [textEditorValue, setTextEditorValue] = useState("")
  const [textEditorError, setTextEditorError] = useState("")
  const [textEditorSyncKey, setTextEditorSyncKey] = useState(0)
  const [collapsedGroups, setCollapsedGroups] = useState(PANEL_GROUP_DEFAULTS)
  const responseTextareaRefs = useRef({})
  const suppressNextAuthTokenSyncRef = useRef(false)
  const endpointConfigsRef = useRef([])
  const links = resolveServiceLinks(service, "http://127.0.0.1")
  const docsEnabled = service?.lapis_config?.metadata?.documentation?.enabled !== false
  const serviceRoot = links?.root || ""
  const basePath = String(service?.lapis_config?.metadata?.basePath || "").trim()

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return
    const mediaQuery = window.matchMedia("(min-width: 1024px)")
    const syncDirection = () => {
      setPanelDirection(mediaQuery.matches ? "horizontal" : "vertical")
    }
    syncDirection()
    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", syncDirection)
      return () => mediaQuery.removeEventListener("change", syncDirection)
    }
    mediaQuery.addListener(syncDirection)
    return () => mediaQuery.removeListener(syncDirection)
  }, [])

  const joinRoute = (base, route) => {
    const basePart = String(base || "").trim()
    const routePart = String(route || "").trim()
    const normalizedBase = basePart ? (basePart.startsWith("/") ? basePart : `/${basePart}`) : ""
    const normalizedRoute = routePart ? (routePart.startsWith("/") ? routePart : `/${routePart}`) : ""
    const normalizedBaseNoSlash = normalizedBase.replace(/\/+$/, "")
    const merged = normalizedBaseNoSlash
      && normalizedRoute
      && (normalizedRoute === normalizedBaseNoSlash || normalizedRoute.startsWith(`${normalizedBaseNoSlash}/`))
      ? normalizedRoute
      : `${normalizedBaseNoSlash}${normalizedRoute}`
    return merged === "" ? "/" : merged
  }

  const endpointConfigs = useMemo(() => {
    const endpoints = service?.lapis_config?.endpoints || {}
    const docsEndpoints = Object.entries(endpoints).map(([id, endpoint]) => ({
      id,
      enabled: endpoint?.enabled !== false,
      method: String(endpoint?.method || "GET").toUpperCase(),
      path: joinRoute(basePath, endpoint?.path || ""),
      operationType: normalizeOperationType(endpoint?.operationType || "unknown"),
      requiresAuth: Boolean(endpoint?.requiresAuth),
      exampleParams: endpoint?.exampleParams || {},
      developerNotes: endpoint?.developerNotes || "",
    }))
    const authCfg = service?.lapis_config?.auth || {}
    const customCfg = authCfg?.customEndpoints || {}
    if (Boolean(authCfg?.isAuthService) && Boolean(customCfg?.enabled)) {
      const registerPath = joinRoute(basePath, customCfg?.register || "/auth/register")
      const hasRegister = docsEndpoints.some(
        (route) => route.method === "POST" && String(route.path || "").trim() === String(registerPath || "").trim(),
      )
      if (!hasRegister) {
        docsEndpoints.push({
          id: "ep_auth_register_auto",
          enabled: true,
          method: "POST",
          path: registerPath,
          operationType: "script",
          requiresAuth: true,
          developerNotes: "Register route (super-admin bearer token required).",
          exampleParams: {
            query: {},
            body: {
              username: "kalumbi.banda",
              email: "kalumbi.banda@zmail.com",
              password: "AfricaPatriotic#2026",
              role: "ADMIN",
              rbac: { scopes: ["ADMIN", "USER_MANAGE", "USER_READ", "USER_WRITE"] },
            },
            headers: { Authorization: "Bearer <super-admin-token>" },
          },
        })
      }
    }
    return docsEndpoints
  }, [service, basePath])

  const authIsAuthService = Boolean(service?.lapis_config?.auth?.isAuthService)
  const authEnabled = Boolean(service?.lapis_config?.auth?.enabled)
  const hasProtectedRoutes = endpointConfigs.some((route) => Boolean(route?.requiresAuth))
  const authDependencyName = String(service?.lapis_config?.auth?.authServiceName || "").trim()
  const authCustomEndpointsEnabled = Boolean(service?.lapis_config?.auth?.customEndpoints?.enabled)
  const authResetPageMode = authDraft?.passwordResetPage?.submissionMode === "custom_page"
    ? "custom_page"
    : (authDraft?.passwordResetPage?.enabled === false ? "custom_page" : "auto_form")
  const signInRoute = joinRoute(
    basePath,
    authCustomEndpointsEnabled
      ? (service?.lapis_config?.auth?.customEndpoints?.signIn || "/auth/signin")
      : "/auth/signin",
  )

  useEffect(() => {
    endpointConfigsRef.current = endpointConfigs
  }, [endpointConfigs])
  const dependencyBasePath = String(authDependencyService?.lapis_config?.metadata?.basePath || "").trim()
  const dependencySignInRoute = joinRoute(
    dependencyBasePath,
    authDependencyService?.lapis_config?.auth?.customEndpoints?.enabled
      ? (authDependencyService?.lapis_config?.auth?.customEndpoints?.signIn || "/auth/signin")
      : "/auth/signin",
  )
  const signOutRoute = joinRoute(
    basePath,
    authCustomEndpointsEnabled
      ? (service?.lapis_config?.auth?.customEndpoints?.signOut || "/auth/signout")
      : "/auth/signout",
  )
  const dependencySignOutRoute = joinRoute(
    dependencyBasePath,
    authDependencyService?.lapis_config?.auth?.customEndpoints?.enabled
      ? (authDependencyService?.lapis_config?.auth?.customEndpoints?.signOut || "/auth/signout")
      : "/auth/signout",
  )
  const authTargetRoot = authIsAuthService ? serviceRoot : (authDependencyService?.port ? `http://127.0.0.1:${authDependencyService.port}` : "")
  const authTargetSignInRoute = authIsAuthService ? signInRoute : dependencySignInRoute
  const authTargetSignOutRoute = authIsAuthService ? signOutRoute : dependencySignOutRoute
  const authProfileOptions = useMemo(() => {
    const srcService = authIsAuthService ? service : authDependencyService
    const lapis = srcService?.lapis_config || {}
    const authCfg = lapis?.auth || {}
    const metadata = lapis?.metadata || {}
    const seedCollections = metadata?.seedData?.collections || {}
    const authUsersSeed = Array.isArray(seedCollections?.auth_users) ? seedCollections.auth_users : []
    const options = []
    const pushOption = (candidate) => {
      if (!candidate || typeof candidate !== "object") return
      const username = String(candidate.username || "").trim()
      if (!username) return
      if (options.some((item) => item.username.toLowerCase() === username.toLowerCase())) return
      options.push({
        username,
        email: String(candidate.email || "").trim(),
        password: String(candidate.password || "").trim(),
        role: String(candidate.role || "USER").trim() || "USER",
      })
    }
    pushOption(authCfg?.defaultSuperAdmin || {})
    authUsersSeed.forEach(pushOption)
    return options
  }, [authDependencyService, authIsAuthService, service])

  const activePanelMeta = useMemo(() => (
    PANEL_ITEMS.find((item) => item.id === activePanel) || PANEL_ITEMS[0]
  ), [activePanel])
  const activePanelGroup = useMemo(() => (
    PANEL_GROUPS.find((group) => group.items.some((item) => item.id === activePanel)) || PANEL_GROUPS[0]
  ), [activePanel])
  const availableEditorModes = PANEL_EDITOR_MODES[activePanel] || ["structured"]
  const isTextEditorMode = editorMode === "text" && availableEditorModes.includes("text")
  const hasTextEditorMode = availableEditorModes.includes("text")
  const hasStructuredEditorMode = availableEditorModes.includes("structured")
  const modelCount = modelDrafts.length
  const endpointCount = endpointDrafts.length || endpointConfigs.length
  const sharedModuleCount = Object.keys(sharedModuleDrafts || {}).length
  const moduleCount = moduleDrafts.length
  const protectedRouteCount = endpointConfigs.filter((route) => route.requiresAuth).length
  const notesPreview = String(developerNotes || "").trim()
  const notesSummary = notesPreview ? `${notesPreview.slice(0, 120)}${notesPreview.length > 120 ? "..." : ""}` : "No developer notes yet."
  const endpointMethodSummary = Array.from(new Set(endpointConfigs.map((route) => route.method))).join(" • ") || "No routes"
  const mediaCapabilities = useMemo(() => (
    service?.mediaCapabilities && typeof service.mediaCapabilities === "object"
      ? service.mediaCapabilities
      : summarizeMediaCapabilities(service?.lapis_config || {})
  ), [service])
  const mediaProviders = useMemo(() => (
    Array.isArray(mediaCapabilities?.providers) ? mediaCapabilities.providers : []
  ), [mediaCapabilities])
  const mediaDefaultProviderLabel = useMemo(() => {
    const match = mediaProviders.find((provider) => provider.id === mediaCapabilities?.defaultProvider)
    return match?.label || String(mediaCapabilities?.defaultProvider || "").trim() || "Not configured"
  }, [mediaCapabilities, mediaProviders])
  const modulesCatalog = useMemo(() => {
    const merged = [...(Array.isArray(availableModules) ? availableModules : [])]
    const seen = new Set(merged.map((module) => String(module?.name || "").trim().toLowerCase()).filter(Boolean))
    Object.entries(normalizeSharedModules(sharedModuleDrafts)).forEach(([name, module]) => {
      const normalizedName = String(name || "").trim().toLowerCase()
      if (!normalizedName || seen.has(normalizedName)) return
      seen.add(normalizedName)
      merged.push({
        name: normalizedName,
        title: module.title || normalizedName,
        description: module.description || "",
        scope: module.scope || "domain",
        assigned_domains: module.serviceDomain ? [module.serviceDomain] : [],
        owner_domains: module.serviceDomain ? [module.serviceDomain] : [],
        service_domain: module.serviceDomain || "",
        config_schema: module.configSchema || {},
        config_defaults: module.configDefaults || {},
      })
    })
    return merged
  }, [availableModules, sharedModuleDrafts])

  const endpointRequestTextAreaClass = "min-h-[132px] font-mono text-xs leading-5"
  const endpointResponseTextAreaClass = "h-auto min-h-full box-border w-full max-w-full resize-none overflow-hidden border-0 bg-transparent px-[10px] py-[10px] font-mono text-xs leading-5 text-sky-100 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0 whitespace-pre-wrap break-all"
  const endpointScriptTextAreaClass = "min-h-[320px] border-white/10 bg-[#0b3451] font-mono text-xs leading-5 text-slate-50"
  const editorCardClass = "service-management-editor-card"
  const editorTextAreaClass = "border-white/[0.12] bg-[#0a2d47] text-slate-50 placeholder:text-sky-100/[0.35] focus-visible:ring-sky-300 focus-visible:ring-offset-[#08243a]"
  const managementShellClass = "service-management-shell"
  const sidebarCardClass = "service-management-sidebar-card"
  const sidebarSoftCardClass = "service-management-sidebar-soft-card"

  const updateRouteDraft = (routeId, key, value) => {
    setRouteDrafts((prev) => ({
      ...prev,
      [routeId]: {
        ...(prev[routeId] || {}),
        [key]: value,
      },
    }))
  }

  const setResponseTextareaRef = useCallback((routeId, node) => {
    if (node) {
      responseTextareaRefs.current[routeId] = node
      return
    }
    delete responseTextareaRefs.current[routeId]
  }, [])

  const syncResponseTextareaHeight = useCallback((routeId) => {
    const textarea = responseTextareaRefs.current[routeId]
    if (!textarea) return
    const container = textarea.parentElement
    textarea.style.height = "0px"
    const targetHeight = Math.max(textarea.scrollHeight, container?.clientHeight || 0, 220)
    textarea.style.height = `${targetHeight}px`
  }, [])

  const parseJsonOrEmptyObject = (rawText, label) => {
    const text = String(rawText || "").trim()
    if (!text) return {}
    try {
      return parseJsonLikeObject(text, label)
    } catch (err) {
      throw new Error(err?.message || `Invalid ${label} JSON`)
    }
  }

  const parseJsonTextForDisplay = (rawText, fallback = {}) => {
    const text = String(rawText || "").trim()
    if (!text) return fallback
    try {
      return parseJsonLikeText(text)
    } catch {
      return text
    }
  }

  const normalizeTestingWorkspace = useCallback((testingState = {}, options = {}) => {
    const source = testingState && typeof testingState === "object" ? testingState : {}
    const authSource = source.auth && typeof source.auth === "object" ? source.auth : {}
    const profileSource = authSource.profile && typeof authSource.profile === "object" ? authSource.profile : {}
    const routesSource = source.routes && typeof source.routes === "object" && !Array.isArray(source.routes)
      ? source.routes
      : {}
    const routeEntries = Array.isArray(options.routeEntries) ? options.routeEntries : endpointConfigsRef.current
    const fallbackProfile = options.defaultProfile && typeof options.defaultProfile === "object"
      ? options.defaultProfile
      : {}
    const fallbackRoutes = options.fallbackRoutes && typeof options.fallbackRoutes === "object"
      ? options.fallbackRoutes
      : {}
    const fallbackToken = String(options.defaultToken ?? "")
    const fallbackProfileChoice = String(options.defaultProfileChoice ?? "")
    const authHas = (key) => Object.prototype.hasOwnProperty.call(authSource, key)
    const profileHas = (key) => Object.prototype.hasOwnProperty.call(profileSource, key)

    return {
      auth: {
        profileChoice: authHas("profileChoice")
          ? String(authSource.profileChoice ?? "")
          : String(fallbackProfileChoice || ""),
        token: authHas("token")
          ? String(authSource.token ?? "")
          : String(fallbackToken || ""),
        profile: {
          username: profileHas("username")
            ? String(profileSource.username ?? "")
            : String(fallbackProfile.username || ""),
          email: profileHas("email")
            ? String(profileSource.email ?? "")
            : String(fallbackProfile.email || ""),
          password: profileHas("password")
            ? String(profileSource.password ?? "")
            : String(fallbackProfile.password || ""),
          role: profileHas("role")
            ? String(profileSource.role ?? "")
            : String(fallbackProfile.role || "SUPER_ADMIN"),
        },
      },
      routes: Object.fromEntries(routeEntries.map((route) => {
        const routeSource = routesSource[route.id] && typeof routesSource[route.id] === "object"
          ? routesSource[route.id]
          : {}
        const fallbackDraft = fallbackRoutes[route.id] && typeof fallbackRoutes[route.id] === "object"
          ? fallbackRoutes[route.id]
          : {}
        const ex = route.exampleParams || {}
        const exAuth = ex?.headers?.Authorization || ex?.headers?.authorization || ""
        const exBearer = typeof exAuth === "string" && exAuth.startsWith("Bearer ") ? exAuth.slice(7) : ""
        const routeQuery = routeSource.query && typeof routeSource.query === "object" ? routeSource.query : (ex.query || {})
        const routeBody = routeSource.body && typeof routeSource.body === "object" ? routeSource.body : (ex.body || {})

        return [route.id, {
          queryText: typeof routeSource.queryText === "string"
            ? routeSource.queryText
            : (typeof fallbackDraft.queryText === "string" ? fallbackDraft.queryText : JSON.stringify(routeQuery, null, 2)),
          bodyText: typeof routeSource.bodyText === "string"
            ? routeSource.bodyText
            : (typeof fallbackDraft.bodyText === "string" ? fallbackDraft.bodyText : JSON.stringify(routeBody, null, 2)),
          bearerToken: typeof routeSource.bearerToken === "string"
            ? routeSource.bearerToken
            : (typeof fallbackDraft.bearerToken === "string"
              ? fallbackDraft.bearerToken
              : (route.requiresAuth ? (String(routeSource.responseToken || fallbackToken || exBearer || "")) : "")),
          responseText: typeof routeSource.responseText === "string"
            ? routeSource.responseText
            : String(fallbackDraft.responseText || "Run the route to see response."),
          responseToken: typeof routeSource.responseToken === "string"
            ? routeSource.responseToken
            : String(fallbackDraft.responseToken || ""),
          running: false,
        }]
      })),
    }
  }, [])

  const buildManagerState = useCallback((testingState = null) => ({
    testing: normalizeTestingWorkspace(
      testingState || {
        auth: {
          profileChoice: authProfileChoice,
          token: authToken,
          profile: authBootstrapCreds,
        },
        routes: routeDrafts,
      },
      {
        defaultProfileChoice: authProfileChoice,
        defaultToken: authToken,
        defaultProfile: authBootstrapCreds,
        fallbackRoutes: routeDrafts,
      },
    ),
  }), [authBootstrapCreds, authProfileChoice, authToken, normalizeTestingWorkspace, routeDrafts])

  const toFieldObject = (fieldDrafts) => {
    const next = {}
    ;(fieldDrafts || []).forEach((field) => {
      const fieldId = String(field?.id || "").trim()
      if (!fieldId) return
      const raw = { ...(field?.rawField || {}) }
      raw.id = fieldId
      raw.name = String(field?.name || "")
      raw.type = String(field?.type || "string")
      raw.required = Boolean(field?.required)
      raw.unique = Boolean(field?.unique)
      const relationModel = String(field?.relationModel || "").trim()
      const relationType = String(field?.relationType || "").trim()
      if (relationModel) {
        raw.relationModel = relationModel
        raw.ref = relationModel
      } else {
        delete raw.relationModel
      }
      if (relationType) {
        raw.relationType = relationType
      } else {
        delete raw.relationType
      }
      next[fieldId] = raw
    })
    return next
  }

  const parseValue = (rawValue) => {
    const text = String(rawValue ?? "").trim()
    if (!text) return ""
    if (text === "true") return true
    if (text === "false") return false
    if (text === "null") return null
    if (/^-?\d+(\.\d+)?$/.test(text)) return Number(text)
    if (
      (text.startsWith("{") && text.endsWith("}")) ||
      (text.startsWith("[") && text.endsWith("]")) ||
      (text.startsWith('"') && text.endsWith('"')) ||
      (text.startsWith("'") && text.endsWith("'"))
    ) {
      try {
        return parseJsonLikeText(text)
      } catch {
        return text
      }
    }
    return text
  }

  const pairsToObject = (pairs) => {
    const next = {}
    ;(pairs || []).forEach((pair) => {
      const key = String(pair?.key || "").trim()
      if (!key) return
      next[key] = parseValue(pair?.value)
    })
    return next
  }

  const modelDraftsToConfig = (drafts = []) => {
    const next = {}
    drafts.forEach((model) => {
      next[model.id] = {
        name: model.name || "",
        collection: model.collection || "",
        fields: toFieldObject(model.fieldsDrafts || []),
      }
    })
    return next
  }

  const confirmModelDependencyImpact = (nextConfig) => {
    const currentModels = service?.lapis_config?.models || {}
    const nextModels = nextConfig?.models || {}
    const endpoints = service?.lapis_config?.endpoints || {}
    const impacts = []
    Object.entries(currentModels).forEach(([id, model]) => {
      const oldName = String(model?.name || id).trim()
      const nextName = String(nextModels?.[id]?.name || "").trim()
      const linkedEndpoints = Object.entries(endpoints)
        .filter(([, endpoint]) => String(endpoint?.linkedModel || "").trim() === oldName)
        .map(([endpointId]) => endpointId)
      if (!linkedEndpoints.length) return
      if (!nextName) impacts.push(`Removing '${oldName}' leaves ${linkedEndpoints.join(", ")} without its linked model.`)
      else if (nextName !== oldName) impacts.push(`Renaming '${oldName}' breaks linked endpoint(s): ${linkedEndpoints.join(", ")}.`)
      else if (JSON.stringify(model?.fields || {}) !== JSON.stringify(nextModels?.[id]?.fields || {})) {
        impacts.push(`Changing '${oldName}' fields changes the data contract for ${linkedEndpoints.join(", ")}.`)
      }
    })
    if (!impacts.length || typeof window === "undefined") return true
    return window.confirm(`This service change has effects:\n\n${impacts.join("\n")}\n\nContinue and restart the service?`)
  }

  const endpointDraftsToConfig = (drafts = []) => {
    const next = {}
    drafts.forEach((ep) => {
      const bearer = String(ep.exampleBearer || "").trim()
      next[ep.id] = {
        ...ep,
        exampleParams: {
          query: pairsToObject(ep.queryPairs || []),
          body: pairsToObject(ep.bodyPairs || []),
          headers: bearer ? { Authorization: `Bearer ${bearer}` } : {},
        },
      }
      delete next[ep.id].id
      delete next[ep.id].queryPairs
      delete next[ep.id].bodyPairs
      delete next[ep.id].exampleBearer
    })
    return next
  }

  const getTextEditorMeta = (panelId) => {
    switch (panelId) {
      case "overview":
        return {
          title: "Service Metadata JSON",
          description: "Edit the service metadata, base path, documentation settings, and overview fields as raw JSON.",
          language: "json",
          saveLabel: "Save Metadata + Restart",
          placeholder: '{"basePath":"/api/service","documentation":{"enabled":true,"key":"liwiroservicepass0!"}}',
        }
      case "env":
        return {
          title: "Service Environment",
          description: "Edit service.env values as KEY=value lines. Scripts read them via service.env.MY_KEY.",
          language: "text",
          saveLabel: "Save Environment + Restart",
          placeholder: "CLOUDINARY_CLOUD_NAME=replace-with-cloud-name\nCLOUDINARY_API_KEY=replace-with-api-key",
        }
      case "notes":
        return {
          title: "Developer Notes",
          description: "Plain text notes shown inside generated service docs.",
          language: "text",
          saveLabel: "Save Notes + Restart",
          placeholder: "Write developer notes for this service.",
        }
      case "keys":
        return {
          title: "Service Keys JSON",
          description: "Edit setup and documentation keys as raw JSON.",
          language: "json",
          saveLabel: "Save Keys + Restart",
          placeholder: '{"setupApiKey":"liwiroservicepass0!","documentation":{"key":"liwiroservicepass0!"}}',
        }
      case "auth":
        return {
          title: "Auth Config JSON",
          description: "Edit authentication wiring directly as JSON.",
          language: "json",
          saveLabel: "Save Auth JSON + Restart",
          placeholder: '{"enabled":true,"isAuthService":false}',
        }
      case "models":
        return {
          title: "Models JSON",
          description: "Raw model schema editing for fast bulk updates.",
          language: "json",
          saveLabel: "Save Models JSON + Restart",
          placeholder: '{"users":{"name":"Users","collection":"users","fields":{}}}',
        }
      case "endpoints":
        return {
          title: "Endpoints JSON",
          description: "Edit route JSON directly. `versaScript` stays plain text inside the JSON object.",
          language: "json",
          saveLabel: "Save Endpoints JSON + Restart",
          placeholder: '{"listUsers":{"method":"GET","path":"/users","operationType":"crud"}}',
        }
      case "modules":
        return {
          title: "VI Modules JSON",
          description: "Edit shared module definitions and attached service modules together as a JSON object.",
          language: "json",
          saveLabel: "Save Modules JSON + Restart",
          placeholder: '{"sharedModules":{"helpers":{"title":"Helpers","source":"func hello(name) {\\n  return \\"hello \\" + name;\\n}"}},"modules":[{"name":"mediacloud","config":{"defaultProvider":"cloudinary"}}]}',
        }
      case "testing":
        return {
          title: "Testing Workspace JSON",
          description: "Edit local route test inputs, bearer tokens, and captured responses as JSON.",
          language: "json",
          saveLabel: "Save Testing JSON",
          placeholder: '{"auth":{"token":""},"routes":{"listUsers":{"query":{},"body":{},"bearerToken":"","responseText":""}}}',
        }
      case "config":
        return {
          title: "Raw LAPIS Config",
          description: "Full-service JSON editor for advanced changes.",
          language: "json",
          saveLabel: "Save Raw Config + Restart",
          placeholder: '{"metadata":{},"auth":{},"models":{},"endpoints":{}}',
        }
      default:
        return {
          title: "Text Editor",
          description: "Direct text editing.",
          language: "text",
          saveLabel: "Save + Restart",
          placeholder: "",
        }
    }
  }

  const buildTextEditorValue = (panelId) => {
    switch (panelId) {
      case "overview":
        return JSON.stringify(service?.lapis_config?.metadata || {}, null, 2)
      case "env":
        return serviceEnvText || envObjectToText((service?.lapis_config?.metadata || {}).env || {})
      case "notes":
        return developerNotes || ""
      case "keys":
        return JSON.stringify({
          setupApiKey,
          documentation: {
            key: documentationKey,
          },
        }, null, 2)
      case "auth":
        return JSON.stringify(authDraft || {}, null, 2)
      case "models":
        return JSON.stringify(modelDraftsToConfig(modelDrafts), null, 2)
      case "endpoints":
        return JSON.stringify(endpointDraftsToConfig(endpointDrafts), null, 2)
      case "modules":
        return JSON.stringify({
          sharedModules: normalizeSharedModules(sharedModuleDrafts),
          modules: normalizeServiceModules(moduleDrafts),
        }, null, 2)
      case "testing": {
        const testingState = buildManagerState().testing
        return JSON.stringify({
          auth: testingState.auth,
          routes: Object.fromEntries(endpointConfigs.map((route) => [
            route.id,
            {
              query: parseJsonTextForDisplay(testingState.routes[route.id]?.queryText || "{}", {}),
              body: parseJsonTextForDisplay(testingState.routes[route.id]?.bodyText || "{}", {}),
              bearerToken: testingState.routes[route.id]?.bearerToken || "",
              responseText: testingState.routes[route.id]?.responseText || "",
              responseToken: testingState.routes[route.id]?.responseToken || "",
            },
          ])),
        }, null, 2)
      }
      case "config":
        return configText || JSON.stringify(service?.lapis_config || {}, null, 2)
      default:
        return ""
    }
  }

  const hydrateServiceState = useCallback((data) => {
    const nextConfig = data?.lapis_config || {}
    const endpointEntries = toEndpointDraftEntries(nextConfig?.endpoints || {})
    const modelEntries = toModelDraftEntries(nextConfig?.models || {})
    const defaultSuperAdmin = nextConfig?.auth?.defaultSuperAdmin || {}
    const defaultTestingProfile = {
      username: String(defaultSuperAdmin?.username || ""),
      email: String(defaultSuperAdmin?.email || ""),
      password: String(defaultSuperAdmin?.password || ""),
      role: String(defaultSuperAdmin?.role || "SUPER_ADMIN"),
    }
    const nextTestingState = normalizeTestingWorkspace(data?.managerState?.testing || {}, {
      routeEntries: endpointEntries,
      defaultProfileChoice: defaultTestingProfile.username,
      defaultToken: "",
      defaultProfile: defaultTestingProfile,
      fallbackRoutes: {},
    })
    const hasStoredTestingRoutes = Boolean(
      data?.managerState?.testing?.routes
      && typeof data.managerState.testing.routes === "object"
      && !Array.isArray(data.managerState.testing.routes),
    )

    setService(data)
    setConfigText(JSON.stringify(nextConfig || {}, null, 2))
    setServiceEnvText(envObjectToText(nextConfig?.metadata?.env || {}))
    setDeveloperNotes(nextConfig?.metadata?.developerNotes || "")
    setSetupApiKey(nextConfig?.metadata?.setupApiKey || "")
    setDocumentationKey(String(nextConfig?.metadata?.documentation?.key || ""))
    setDocsKeyConfigured(Boolean(data?.docsKeyConfigured))
    setAuthDraft({ ...(nextConfig?.auth || {}) })
    if (hasStoredTestingRoutes) {
      suppressNextAuthTokenSyncRef.current = true
    }
    setAuthBootstrapCreds(nextTestingState.auth.profile)
    setAuthProfileChoice(nextTestingState.auth.profileChoice)
    setAuthToken(nextTestingState.auth.token)
    setRouteDrafts(nextTestingState.routes)
    setEndpointDrafts(endpointEntries)
    setCollapsedEndpoints(Object.fromEntries(endpointEntries.map((ep) => [ep.id, true])))
    setCollapsedCustomVql(Object.fromEntries(endpointEntries.map((ep) => [ep.id, false])))
    setModelDrafts(modelEntries)
    setSharedModuleDrafts(normalizeSharedModules(nextConfig?.sharedModules || {}))
    setModuleDrafts(normalizeServiceModules(nextConfig?.modules || []))
    setCollapsedModels(Object.fromEntries(modelEntries.map((model) => [model.id, true])))
    setTextEditorError("")
    setTextEditorSyncKey((prev) => prev + 1)
  }, [normalizeTestingWorkspace])

  const loadModulesCatalog = useCallback(async () => {
    setModulesLoading(true)
    try {
      const data = await fetchAuthedJson(`${backend}/platform/vi/modules/catalog`, { ttlMs: 10000 })
      setAvailableModules(Array.isArray(data?.modules) ? data.modules : [])
      setAvailableModuleDomains(Array.isArray(data?.available_domains) ? data.available_domains : [])
      return Array.isArray(data?.modules) ? data.modules : []
    } catch (err) {
      if (err?.status === 401) {
        router.replace("/login")
        return []
      }
      toast.error(err?.message || "Failed to load VI modules")
      return []
    } finally {
      setModulesLoading(false)
    }
  }, [backend, router])

  const runRoute = async (route) => {
    if (route?.enabled === false) {
      updateRouteDraft(route.id, "responseText", "Endpoint is disabled in the current service configuration.")
      toast.error("This endpoint is disabled in the current service configuration.")
      return
    }
    if (!serviceRoot) {
      toast.error("Service root URL unavailable. Start the service first.")
      return
    }

    const draft = routeDrafts[route.id] || {}
    updateRouteDraft(route.id, "running", true)
    updateRouteDraft(route.id, "responseToken", "")
    updateRouteDraft(route.id, "responseText", "Running...")
    try {
      const queryObj = parseJsonOrEmptyObject(draft.queryText || "{}", "query")
      const bodyObj = parseJsonOrEmptyObject(draft.bodyText || "{}", "body")

      const bearer = String(draft.bearerToken || "").trim()
      const response = await fetch(`${backend}/services/${processId}/test-route`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          endpointId: route.id,
          query: queryObj,
          body: bodyObj,
          bearerToken: bearer,
        }),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(result?.error || "Route test failed")
      const routeStatus = Number(result?.status || 0)
      const routeBody = result?.body
      const rendered = typeof routeBody === "string" ? routeBody : JSON.stringify(routeBody ?? {}, null, 2)
      if (routeStatus >= 200 && routeStatus < 300 && routeBody && typeof routeBody === "object") {
          const rawToken = routeBody?.token ?? routeBody?.access_token ?? routeBody?.accessToken ?? routeBody?.jwt ?? ""
          let token = typeof rawToken === "string" ? rawToken.trim() : ""
          if (token.toLowerCase().startsWith("bearer ")) {
            token = token.slice(7).trim()
          }
          if (token) {
            updateRouteDraft(route.id, "responseToken", token)
            setAuthToken(token)
          }
      }
      updateRouteDraft(route.id, "responseText", `HTTP ${routeStatus || "?"}\n${rendered}`)
    } catch (err) {
      updateRouteDraft(route.id, "responseText", `Error: ${err?.message || "Request failed"}`)
    } finally {
      updateRouteDraft(route.id, "running", false)
    }
  }

  const populateRouteDefaults = (route) => {
    const ex = route?.exampleParams || {}
    const exAuth = ex?.headers?.Authorization || ex?.headers?.authorization || ""
    const exBearer = typeof exAuth === "string" && exAuth.startsWith("Bearer ") ? exAuth.slice(7) : ""
    setRouteDrafts((prev) => ({
      ...prev,
      [route.id]: {
        ...(prev[route.id] || {}),
        queryText: JSON.stringify(ex.query || {}, null, 2),
        bodyText: JSON.stringify(ex.body || {}, null, 2),
        bearerToken: route.requiresAuth ? (authToken || exBearer || "") : "",
      },
    }))
  }

  const runResetSuperAdmin = async () => {
    if (!serviceRoot) {
      toast.error("Service root URL unavailable. Start the service first.")
      return
    }
    if (!setupApiKey) {
      toast.error("Setup API key is required")
      return
    }
    setSetupRunning(true)
    try {
      const endpointUrl = new URL("liwiro/setup/reset-super-admin", serviceRoot).toString()
      const response = await fetch(endpointUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Liwiro-Setup-Key": setupApiKey,
        },
        body: JSON.stringify({
          username: authBootstrapCreds.username,
          email: authBootstrapCreds.email,
          password: authBootstrapCreds.password,
          role: authBootstrapCreds.role || "SUPER_ADMIN",
        }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.error || "Super admin reset failed")
      toast.success(data?.message || data?.status || "Super admin reset completed")
    } catch (err) {
      toast.error(err?.message || "Super admin reset failed")
    } finally {
      setSetupRunning(false)
    }
  }

  const runAuthenticate = async () => {
    if (!authTargetRoot) {
      toast.error(authIsAuthService ? "Service root URL unavailable. Start the service first." : "Authentication service is unavailable or not running.")
      return
    }
    const username = String(authBootstrapCreds.username || "").trim()
    const password = String(authBootstrapCreds.password || "").trim()
    if (!username || !password) {
      toast.error("Username and password are required for authentication")
      return
    }
    setAuthenticating(true)
    try {
      const endpointUrl = new URL(
        authTargetSignInRoute.startsWith("/") ? authTargetSignInRoute.slice(1) : authTargetSignInRoute,
        authTargetRoot,
      ).toString()
      const response = await fetch(endpointUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.error || "Authentication failed")
      if (data?.authenticated === false) {
        throw new Error(data?.reason || data?.error || "Authentication failed")
      }
      const rawToken = data?.token ?? data?.access_token ?? data?.accessToken ?? data?.jwt ?? ""
      let token = typeof rawToken === "string" ? rawToken.trim() : ""
      if (token.toLowerCase().startsWith("bearer ")) {
        token = token.slice(7).trim()
      }
      if (!token) throw new Error("Authentication succeeded but no token was returned")
      setAuthToken(token)
      toast.success("Authenticated. Bearer token captured and applied to protected routes.")
    } catch (err) {
      toast.error(err?.message || "Authentication failed")
    } finally {
      setAuthenticating(false)
    }
  }

  const runSignOut = async () => {
    if (!authTargetRoot) {
      toast.error(authIsAuthService ? "Service root URL unavailable. Start the service first." : "Authentication service is unavailable or not running.")
      return
    }
    const bearer = String(authToken || "").trim()
    if (!bearer) {
      toast.error("No bearer token found. Authenticate first.")
      return
    }
    try {
      const endpointUrl = new URL(
        authTargetSignOutRoute.startsWith("/") ? authTargetSignOutRoute.slice(1) : authTargetSignOutRoute,
        authTargetRoot,
      ).toString()
      const response = await fetch(endpointUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${bearer}`,
        },
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.error || data?.message || "Sign out failed")
      setAuthToken("")
      toast.success(data?.message || "Signed out. Bearer token cleared.")
    } catch (err) {
      toast.error(err?.message || "Sign out failed")
    }
  }

  const downloadAuthKeys = async () => {
    const targetProcessId = String(service?.processId || processId || "")
    if (!targetProcessId) {
      toast.error("Service identifier unavailable.")
      return
    }
    setDownloadingAuthKeys(true)
    try {
      const response = await fetch(`${backend}/services/${targetProcessId}/auth-keys`, {
        headers: authHeaders(),
      })
      if (response.status === 401) {
        router.replace("/login")
        return
      }
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data?.error || "Failed to download auth keys")
      }
      const files = Array.isArray(data?.files) ? data.files : []
      if (!files.length) {
        throw new Error("No authentication key material is available for this service")
      }

      files.forEach((file, index) => {
        const content = String(file?.content || "")
        const filename = String(file?.filename || `auth-material-${index + 1}.txt`)
        const blob = new Blob([content], { type: "text/plain;charset=utf-8" })
        const url = window.URL.createObjectURL(blob)
        const link = document.createElement("a")
        link.href = url
        link.download = filename
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        window.URL.revokeObjectURL(url)
      })

      toast.success(
        data?.caution
          ? `Downloaded auth material. ${data.caution}`
          : "Downloaded auth material.",
      )
    } catch (err) {
      toast.error(err?.message || "Failed to download auth keys")
    } finally {
      setDownloadingAuthKeys(false)
    }
  }

  const fetchService = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const response = await fetch(`${backend}/services/${processId}`, {
        headers: authHeaders(),
      })
      if (response.status === 401) {
        router.replace("/login")
        return
      }
      const data = await response.json()
      if (!response.ok) {
        throw new Error(data.error || "Failed to load service")
      }
      hydrateServiceState(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [backend, processId, router, hydrateServiceState])

  useEffect(() => {
    if (processId) fetchService()
  }, [processId, fetchService])

  useEffect(() => {
    loadModulesCatalog()
  }, [loadModulesCatalog])

  useEffect(() => {
    if (activePanel !== "testing") return
    const frame = window.requestAnimationFrame(() => {
      endpointConfigs.forEach((route) => syncResponseTextareaHeight(route.id))
    })
    return () => window.cancelAnimationFrame(frame)
  }, [activePanel, endpointConfigs, routeDrafts, syncResponseTextareaHeight])

  useEffect(() => {
    if (activePanel !== "testing") return
    const handleResize = () => {
      endpointConfigs.forEach((route) => syncResponseTextareaHeight(route.id))
    }
    window.addEventListener("resize", handleResize)
    return () => window.removeEventListener("resize", handleResize)
  }, [activePanel, endpointConfigs, syncResponseTextareaHeight])

  useEffect(() => {
    const loadPageDefaults = async () => {
      const [meRes, settingsRes] = await Promise.allSettled([
        fetchAuthedJson(`${backend}/auth/me`, { ttlMs: 2500 }),
        fetchAuthedJson(`${backend}/platform/settings`, { ttlMs: 2500 }),
      ])

      if (meRes.status === "fulfilled") {
        const me = meRes.value || {}
        const perms = Array.isArray(me?.permissions) ? me.permissions : []
        setCanManageServices(perms.includes("MANAGE_SERVICES"))
      } else {
        setCanManageServices(false)
      }

      if (settingsRes.status === "fulfilled") {
        const settings = settingsRes.value || {}
        setDeleteDataWithService(Boolean(settings?.deleteDataWithServiceByDefault))
      }
    }
    loadPageDefaults()
  }, [backend])

  useEffect(() => {
    const loadAuthDependency = async () => {
      if (!hasProtectedRoutes || authIsAuthService || !authDependencyName) {
        setAuthDependencyService(null)
        return
      }
      try {
        const servicesUrl = new URL(`${backend}/services`)
        servicesUrl.searchParams.set("refresh", "0")
        const data = await fetchAuthedJson(servicesUrl.toString(), { ttlMs: 2500 })
        const found = (Array.isArray(data) ? data : []).find(
          (item) => String(item?.apiName || "").trim().toLowerCase() === authDependencyName.toLowerCase(),
        )
        setAuthDependencyService(found || null)
        if (found) {
          const depDefault = (((found || {}).lapis_config || {}).auth || {}).defaultSuperAdmin || {}
          const depUsername = String(depDefault?.username || "").trim()
          const depEmail = String(depDefault?.email || "").trim()
          const depPassword = String(depDefault?.password || "").trim()
          if (depUsername || depEmail || depPassword) {
            setAuthBootstrapCreds((prev) => {
              const curUsername = String(prev?.username || "").trim()
              const curEmail = String(prev?.email || "").trim()
              const curPassword = String(prev?.password || "").trim()
              const curRole = String(prev?.role || "SUPER_ADMIN").trim() || "SUPER_ADMIN"
              return {
                username: curUsername || depUsername,
                email: curEmail || depEmail,
                password: curPassword || depPassword,
                role: curRole || String(depDefault?.role || "SUPER_ADMIN"),
              }
            })
          }
        }
      } catch {
        setAuthDependencyService(null)
      }
    }
    loadAuthDependency()
  }, [backend, hasProtectedRoutes, authIsAuthService, authDependencyName])

  useEffect(() => {
    if (!authProfileOptions.length) {
      setAuthProfileChoice("")
      return
    }
    if (!authProfileChoice || !authProfileOptions.some((p) => p.username === authProfileChoice)) {
      const first = authProfileOptions[0]
      setAuthProfileChoice(first.username)
      setAuthBootstrapCreds((prev) => ({
        ...prev,
        username: first.username || prev.username,
        email: first.email || prev.email,
        password: first.password || prev.password,
        role: first.role || prev.role || "USER",
      }))
    }
  }, [authProfileChoice, authProfileOptions])

  useEffect(() => {
    if (!endpointConfigs.length) {
      setRouteDrafts({})
      return
    }
    setRouteDrafts((prev) => {
      const next = {}
      endpointConfigs.forEach((route) => {
        const previous = prev[route.id] || {}
        const ex = route.exampleParams || {}
        const exAuth = ex?.headers?.Authorization || ex?.headers?.authorization || ""
        const exBearer = typeof exAuth === "string" && exAuth.startsWith("Bearer ") ? exAuth.slice(7) : ""
        next[route.id] = {
          queryText: previous.queryText ?? JSON.stringify(ex.query || {}, null, 2),
          bodyText: previous.bodyText ?? JSON.stringify(ex.body || {}, null, 2),
          bearerToken: previous.bearerToken ?? (route.requiresAuth ? (authToken || exBearer || "") : ""),
          responseText: previous.responseText ?? "Run the route to see response.",
          responseToken: previous.responseToken ?? "",
          running: false,
        }
      })
      return next
    })
  }, [endpointConfigs, authToken])

  useEffect(() => {
    if (suppressNextAuthTokenSyncRef.current) {
      suppressNextAuthTokenSyncRef.current = false
      return
    }
    setRouteDrafts((prev) => {
      const next = { ...prev }
      endpointConfigs.forEach((route) => {
        if (!route.requiresAuth) return
        next[route.id] = {
          ...(next[route.id] || {}),
          bearerToken: authToken || "",
        }
      })
      return next
    })
  }, [authToken, endpointConfigs])

  useEffect(() => {
    setEndpointDrafts((prev) => prev.map((ep) => (
      ep?.requiresAuth ? { ...ep, exampleBearer: authToken || "" } : ep
    )))
  }, [authToken])

  const callAction = async (action) => {
    try {
      const response = await fetch(`${backend}/services/${processId}/${action}`, {
        method: "POST",
        headers: authHeaders(),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || `${action} failed`)
      toast.success(data.message || `Service ${action} complete`)
      if (action === "start" && data?.process_id && String(data.process_id) !== processId) {
        router.replace(`/services/${data.process_id}`)
        return
      }
      await fetchService()
    } catch (err) {
      toast.error(err.message)
    }
  }

  const handleDelete = async () => {
    try {
      const deleteUrl = new URL(`${backend}/services/${processId}/delete`)
      if (deleteDataWithService) {
        deleteUrl.searchParams.set("deleteData", "true")
      }
      const response = await fetch(deleteUrl.toString(), {
        method: "DELETE",
        headers: authHeaders(),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || "Delete failed")
      toast.success(data.message || "Service deleted")
      router.replace("/services")
    } catch (err) {
      toast.error(err.message)
    }
  }

  const toggleDocs = async (enabled) => {
    if (!service?.lapis_config) return
    setSaving(true)
    setError("")
    try {
      const nextConfig = JSON.parse(JSON.stringify(service.lapis_config))
      nextConfig.metadata = nextConfig.metadata || {}
      nextConfig.metadata.documentation = {
        ...(nextConfig.metadata.documentation || {}),
        enabled: !!enabled,
      }

      const response = await fetch(`${backend}/services/${processId}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({ lapis_config: nextConfig, restart: true }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || "Failed to update docs setting")
      hydrateServiceState(data)
      const newProcessId = String(data?.processId || "")
      if (newProcessId && newProcessId !== processId) {
        router.replace(`/services/${newProcessId}`)
      }
      toast.success(`Service documentation ${enabled ? "enabled" : "disabled"}`)
    } catch (err) {
      setError(err.message)
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

  const saveDeveloperNotes = async () => {
    if (!service?.lapis_config) return
    setSaving(true)
    setError("")
    try {
      const nextConfig = JSON.parse(JSON.stringify(service.lapis_config))
      nextConfig.metadata = nextConfig.metadata || {}
      nextConfig.metadata.developerNotes = developerNotes
      const response = await fetch(`${backend}/services/${processId}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({ lapis_config: nextConfig, restart: true }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || "Failed to save developer notes")
      hydrateServiceState(data)
      const newProcessId = String(data?.processId || "")
      if (newProcessId && newProcessId !== processId) {
        router.replace(`/services/${newProcessId}`)
      }
      toast.success("Developer notes updated")
    } catch (err) {
      setError(err.message)
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

  const saveServiceEnvironment = async () => {
    if (!service?.lapis_config) return
    setSaving(true)
    setError("")
    try {
      const nextConfig = JSON.parse(JSON.stringify(service.lapis_config))
      nextConfig.metadata = nextConfig.metadata || {}
      nextConfig.metadata.env = parseEnvText(serviceEnvText)
      const response = await fetch(`${backend}/services/${processId}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({ lapis_config: nextConfig, restart: true }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || "Failed to save service environment")
      hydrateServiceState(data)
      toast.success("Service environment updated")
    } catch (err) {
      setError(err.message)
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

  const saveDocumentationKey = async () => {
    if (!service?.lapis_config) return
    const key = String(documentationKey || "").trim()
    if (!key) {
      toast.error("Documentation key is required")
      return
    }
    setSaving(true)
    setError("")
    try {
      const nextConfig = JSON.parse(JSON.stringify(service.lapis_config))
      nextConfig.metadata = nextConfig.metadata || {}
      nextConfig.metadata.documentation = {
        ...(nextConfig.metadata.documentation || {}),
        enabled: nextConfig.metadata.documentation?.enabled !== false,
      }
      const response = await fetch(`${backend}/services/${processId}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          lapis_config: nextConfig,
          restart: true,
          service_documentation_key: key,
        }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || "Failed to save documentation key")
      hydrateServiceState(data)
      toast.success("Documentation key updated")
    } catch (err) {
      setError(err.message)
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

  const generateSetupApiKey = () => {
    setSetupApiKey(generateLiwiroKey("liwiro_setup_"))
  }

  const generateDocumentationKey = () => {
    setDocumentationKey(generateLiwiroKey("liwiro_docs_"))
  }

  const saveTestingWorkspace = async (testingState = null, successMessage = "Testing workspace saved", showErrorToast = true) => {
    if (!service) return
    setSaving(true)
    setError("")
    setTextEditorError("")
    try {
      const response = await fetch(`${backend}/services/${processId}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          manager_state: buildManagerState(testingState),
          restart: false,
        }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || "Failed to save testing workspace")
      hydrateServiceState(data)
      const newProcessId = String(data?.processId || "")
      if (newProcessId && newProcessId !== processId) {
        router.replace(`/services/${newProcessId}`)
      }
      toast.success(successMessage)
    } catch (err) {
      setError(err.message)
      if (showErrorToast) {
        toast.error(err.message)
      }
      throw err
    } finally {
      setSaving(false)
    }
  }

  const updateEndpointDraft = (id, key, value) => {
    setEndpointDrafts((prev) => prev.map((item) => (item.id === id ? { ...item, [key]: value } : item)))
  }

  const updateModelDraft = (id, key, value) => {
    setModelDrafts((prev) => prev.map((item) => {
      if (item.id !== id) return item
      if (key !== "name") {
        return { ...item, [key]: value }
      }

      const currentCollection = String(item.collection || "").trim()
      const previousAutoCollection = generateCollectionNameFromModelName(item.name || "")
      const nextAutoCollection = generateCollectionNameFromModelName(value)
      const shouldAutoUpdateCollection = !currentCollection || currentCollection === previousAutoCollection

      return {
        ...item,
        name: value,
        ...(shouldAutoUpdateCollection ? { collection: nextAutoCollection } : {}),
      }
    }))
  }

  const addModelDraft = () => {
    const id = `model_${Date.now()}`
    setModelDrafts((prev) => [...prev, { id, name: "", collection: "", fieldsDrafts: [] }])
    setCollapsedModels((prev) => ({ ...prev, [id]: false }))
  }

  const removeModelDraft = (id) => {
    setModelDrafts((prev) => prev.filter((item) => item.id !== id))
    setCollapsedModels((prev) => {
      const next = { ...prev }
      delete next[id]
      return next
    })
  }

  const addModelFieldDraft = (modelId) => {
    const newFieldId = `field_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
    setModelDrafts((prev) => prev.map((item) => {
      if (item.id !== modelId) return item
      return {
        ...item,
        fieldsDrafts: [
          ...(item.fieldsDrafts || []),
          {
            id: newFieldId,
            name: "",
            type: "string",
            required: false,
            unique: false,
            relationModel: "",
            relationType: "",
            rawField: {},
          },
        ],
      }
    }))
  }

  const updateModelFieldDraft = (modelId, fieldId, key, value) => {
    setModelDrafts((prev) => prev.map((item) => {
      if (item.id !== modelId) return item
      return {
        ...item,
        fieldsDrafts: (item.fieldsDrafts || []).map((field) => (
          field.id === fieldId ? { ...field, [key]: value } : field
        )),
      }
    }))
  }

  const removeModelFieldDraft = (modelId, fieldId) => {
    setModelDrafts((prev) => prev.map((item) => {
      if (item.id !== modelId) return item
      return {
        ...item,
        fieldsDrafts: (item.fieldsDrafts || []).filter((field) => field.id !== fieldId),
      }
    }))
  }

  const addEndpointParamPair = (endpointId, type) => {
    const newPair = { id: `pair_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`, key: "", value: "" }
    setEndpointDrafts((prev) => prev.map((ep) => {
      if (ep.id !== endpointId) return ep
      const key = type === "body" ? "bodyPairs" : "queryPairs"
      return { ...ep, [key]: [...(ep[key] || []), newPair] }
    }))
  }

  const updateEndpointParamPair = (endpointId, type, pairId, key, value) => {
    setEndpointDrafts((prev) => prev.map((ep) => {
      if (ep.id !== endpointId) return ep
      const pairsKey = type === "body" ? "bodyPairs" : "queryPairs"
      return {
        ...ep,
        [pairsKey]: (ep[pairsKey] || []).map((pair) => (pair.id === pairId ? { ...pair, [key]: value } : pair)),
      }
    }))
  }

  const removeEndpointParamPair = (endpointId, type, pairId) => {
    setEndpointDrafts((prev) => prev.map((ep) => {
      if (ep.id !== endpointId) return ep
      const pairsKey = type === "body" ? "bodyPairs" : "queryPairs"
      return { ...ep, [pairsKey]: (ep[pairsKey] || []).filter((pair) => pair.id !== pairId) }
    }))
  }

  const applyServiceEnvPreset = (presetId) => {
    const nextEnv = applyMediaStorageEnvPreset(parseEnvText(serviceEnvText), presetId)
    setServiceEnvText(envObjectToText(nextEnv))
  }

  const applyEndpointScriptPreset = (endpointId, presetId) => {
    setEndpointDrafts((prev) => prev.map((ep) => {
      if (ep.id !== endpointId) return ep
      return {
        ...ep,
        operationType: "script",
        versaScript: buildMediaStorageScriptTemplate(presetId, ep.path || "/upload"),
      }
    }))
  }

  const attachModuleToService = useCallback(async (moduleName) => {
    const normalizedName = String(moduleName || "").trim().toLowerCase()
    if (!normalizedName) return false

    let created = false
    setModuleDrafts((prev) => {
      const existing = Array.isArray(prev) ? prev : []
      if (existing.some((item) => String(item?.name || "").trim().toLowerCase() === normalizedName)) {
        return prev
      }
      created = true
      return [...existing, { name: normalizedName, config: {} }]
    })

    const serviceDomain = String(service?.lapis_config?.metadata?.apiName || service?.apiName || "").trim().toLowerCase()
    if (Object.prototype.hasOwnProperty.call(sharedModuleDrafts || {}, normalizedName)) {
      return created
    }
    if (!serviceDomain) {
      return created
    }

    try {
      const response = await fetch(`${backend}/platform/vi/modules/${encodeURIComponent(normalizedName)}/domains`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ domain: serviceDomain }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data?.error || "Failed to assign service domain to module")
      }
      setAvailableModules((prev) =>
        prev.map((item) => (String(item?.name || "").trim() === normalizedName ? data?.module || item : item)),
      )
    } catch (error) {
      toast.error(error?.message || "Failed to sync module domain assignment")
    }

    return created
  }, [backend, service, sharedModuleDrafts])

  const saveStructuredConfig = async () => {
    if (!service?.lapis_config) return
    setSaving(true)
    setError("")
    try {
      ;(endpointDrafts || []).forEach((endpoint) => {
        if (normalizeOperationType(endpoint?.operationType) !== "custom") return
        const text = String(endpoint?.vqlQuery || "").trim()
        if (!text) throw new Error(`Custom VQL endpoint '${endpoint?.id || "endpoint"}' requires a readable VDB command.`)
        if (/^[{[]/.test(text)) throw new Error(`Custom VQL endpoint '${endpoint?.id || "endpoint"}' cannot use a JSON command object.`)
      })
      const nextConfig = JSON.parse(JSON.stringify(service.lapis_config))
      nextConfig.metadata = nextConfig.metadata || {}
      nextConfig.metadata.env = parseEnvText(serviceEnvText)
      nextConfig.metadata.setupApiKey = setupApiKey
      nextConfig.metadata.developerNotes = developerNotes
      nextConfig.metadata.documentation = {
        ...(nextConfig.metadata.documentation || {}),
        enabled: nextConfig.metadata.documentation?.enabled !== false,
        ...(String(documentationKey || "").trim() ? { key: String(documentationKey || "").trim() } : {}),
      }
      nextConfig.auth = { ...(nextConfig.auth || {}), ...(authDraft || {}) }
      nextConfig.models = modelDraftsToConfig(modelDrafts)
      nextConfig.endpoints = endpointDraftsToConfig(endpointDrafts)
      nextConfig.sharedModules = normalizeSharedModules(sharedModuleDrafts)
      nextConfig.modules = normalizeServiceModules(moduleDrafts)
      if (!confirmModelDependencyImpact(nextConfig)) {
        setSaving(false)
        return
      }

      const response = await fetch(`${backend}/services/${processId}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          lapis_config: nextConfig,
          manager_state: buildManagerState(),
          restart: true,
          acknowledgeImpact: true,
          ...(String(documentationKey || "").trim() ? { service_documentation_key: String(documentationKey || "").trim() } : {}),
        }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || "Failed to save structured config")
      hydrateServiceState(data)
      const newProcessId = String(data?.processId || "")
      if (newProcessId && newProcessId !== processId) {
        router.replace(`/services/${newProcessId}`)
      }
      toast.success("Service configuration saved from structured editor")
    } catch (err) {
      setError(err.message)
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

  const togglePanelGroup = (groupTitle) => {
    setCollapsedGroups((prev) => ({
      ...prev,
      [groupTitle]: !prev[groupTitle],
    }))
  }

  const selectPanel = (panelId, groupTitle) => {
    setActivePanel(panelId)
    if (groupTitle) {
      setCollapsedGroups((prev) => ({
        ...prev,
        [groupTitle]: false,
      }))
    }
    const nextModes = PANEL_EDITOR_MODES[panelId] || ["structured"]
    const nextMode = nextModes.includes(editorMode) ? editorMode : nextModes[0]
    setEditorMode(nextMode)
    if (nextMode === "text") {
      setTextEditorValue(buildTextEditorValue(panelId))
      setTextEditorError("")
    }
  }

  const switchEditorMode = (nextMode) => {
    if (!availableEditorModes.includes(nextMode)) return
    setEditorMode(nextMode)
    if (nextMode === "text") {
      setTextEditorValue(buildTextEditorValue(activePanel))
      setTextEditorError("")
    }
  }

  useEffect(() => {
    if (!isTextEditorMode) return
    setTextEditorValue(buildTextEditorValue(activePanel))
    setTextEditorError("")
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePanel, isTextEditorMode, textEditorSyncKey])

  const saveTextEditor = async () => {
    if (!service?.lapis_config) return

    const meta = getTextEditorMeta(activePanel)
    setSaving(true)
    setError("")
    setTextEditorError("")

    try {
      let nextConfig = JSON.parse(JSON.stringify(service.lapis_config))
      let successMessage = `${meta.title} updated`
      let serviceDocumentationKey = ""

      if (activePanel === "overview") {
        nextConfig.metadata = parseJsonOrEmptyObject(textEditorValue, "service metadata")
        serviceDocumentationKey = String(nextConfig?.metadata?.documentation?.key || "").trim()
        successMessage = "Service metadata updated"
      } else if (activePanel === "env") {
        nextConfig.metadata = nextConfig.metadata || {}
        nextConfig.metadata.env = parseEnvText(textEditorValue)
        successMessage = "Service environment updated"
      } else if (activePanel === "notes") {
        nextConfig.metadata = nextConfig.metadata || {}
        nextConfig.metadata.developerNotes = textEditorValue
        successMessage = "Developer notes updated"
      } else if (activePanel === "keys") {
        const parsed = parseJsonOrEmptyObject(textEditorValue, "keys")
        const nextSetupApiKey = String(parsed.setupApiKey ?? parsed.metadata?.setupApiKey ?? "").trim()
        const nextDocumentationKey = String(
          parsed.documentationKey
          ?? parsed.documentation?.key
          ?? parsed.metadata?.documentation?.key
          ?? "",
        ).trim()
        if (!nextSetupApiKey && !nextDocumentationKey) {
          throw new Error("Keys JSON must include `setupApiKey` or `documentation.key`.")
        }
        nextConfig.metadata = nextConfig.metadata || {}
        if (nextSetupApiKey) nextConfig.metadata.setupApiKey = nextSetupApiKey
        nextConfig.metadata.documentation = {
          ...(nextConfig.metadata.documentation || {}),
          enabled: nextConfig.metadata.documentation?.enabled !== false,
          ...(nextDocumentationKey ? { key: nextDocumentationKey } : {}),
        }
        serviceDocumentationKey = nextDocumentationKey
        successMessage = "Service keys updated"
      } else if (activePanel === "auth") {
        nextConfig.auth = parseJsonOrEmptyObject(textEditorValue, "auth config")
        successMessage = "Authentication config updated"
      } else if (activePanel === "models") {
        nextConfig.models = parseJsonOrEmptyObject(textEditorValue, "models config")
        successMessage = "Models updated from raw editor"
      } else if (activePanel === "endpoints") {
        nextConfig.endpoints = parseJsonOrEmptyObject(textEditorValue, "endpoints config")
        successMessage = "Endpoints updated from raw editor"
      } else if (activePanel === "modules") {
        const parsed = parseJsonLikeText(textEditorValue)
        if (Array.isArray(parsed)) {
          nextConfig.modules = normalizeServiceModules(parsed)
          successMessage = "VI modules updated from raw editor"
        } else if (parsed && typeof parsed === "object") {
          nextConfig.sharedModules = normalizeSharedModules(parsed.sharedModules || {})
          nextConfig.modules = normalizeServiceModules(parsed.modules || [])
          successMessage = "VI modules updated from raw editor"
        } else {
          throw new Error("Modules JSON must be an array or an object containing `sharedModules` and `modules`.")
        }
      } else if (activePanel === "testing") {
        const parsed = parseJsonOrEmptyObject(textEditorValue, "testing workspace")
        const normalizedTesting = normalizeTestingWorkspace(parsed, {
          defaultProfileChoice: authProfileChoice,
          defaultToken: authToken,
          defaultProfile: authBootstrapCreds,
          fallbackRoutes: routeDrafts,
        })
        await saveTestingWorkspace(normalizedTesting, "Testing workspace updated", false)
        return
      } else if (activePanel === "config") {
        const parsedConfig = parseJsonLikeText(textEditorValue)
        if (!parsedConfig || typeof parsedConfig !== "object" || Array.isArray(parsedConfig)) {
          throw new Error("LAPIS config must be a JSON object")
        }
        nextConfig = parsedConfig
        serviceDocumentationKey = String(parsedConfig?.metadata?.documentation?.key || "").trim()
        successMessage = "Raw LAPIS configuration updated"
      } else {
        throw new Error("This panel does not support raw text saving.")
      }

      if (!confirmModelDependencyImpact(nextConfig)) {
        setSaving(false)
        return
      }

      const response = await fetch(`${backend}/services/${processId}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          lapis_config: nextConfig,
          restart: true,
          acknowledgeImpact: true,
          ...(serviceDocumentationKey ? { service_documentation_key: serviceDocumentationKey } : {}),
        }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || `Failed to save ${meta.title.toLowerCase()}`)
      hydrateServiceState(data)
      const newProcessId = String(data?.processId || "")
      if (newProcessId && newProcessId !== processId) {
        router.replace(`/services/${newProcessId}`)
      }
      toast.success(successMessage)
    } catch (err) {
      const message = err?.message || `Failed to save ${meta.title.toLowerCase()}`
      setError(message)
      setTextEditorError(message)
      toast.error(message)
    } finally {
      setSaving(false)
    }
  }

  const renderOverviewWorkspaceCard = () => (
    <Card className={`${editorCardClass} flex min-h-full flex-col`}>
      <CardHeader className="p-6 pb-4 md:p-7 md:pb-5">
        <CardTitle className="text-xl text-white">Overview Workspace</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-5 p-6 pt-0 md:p-7 md:pt-0">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-2xl border border-white/[0.08] bg-[#102c49] p-5">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-300">Service Base Path</p>
            <p className="mt-2 text-lg font-semibold text-white">{basePath || "/"}</p>
            <p className="mt-2 text-sm leading-6 text-slate-300">Requests resolve relative to this service root.</p>
          </div>
          <div className="rounded-2xl border border-white/[0.08] bg-[#102c49] p-5">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-300">Documentation Access</p>
            <p className="mt-2 text-lg font-semibold text-white">{docsEnabled ? "Enabled" : "Disabled"}</p>
            <p className="mt-2 text-sm leading-6 text-slate-300">
              Docs key is {docsKeyConfigured ? "configured" : "not configured"}.
            </p>
          </div>
          <div className="rounded-2xl border border-white/[0.08] bg-[#102c49] p-5">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-300">Authentication</p>
            <p className="mt-2 text-lg font-semibold text-white">{authEnabled ? "Enabled" : "Disabled"}</p>
            <p className="mt-2 text-sm leading-6 text-slate-300">
              {authIsAuthService ? "This service issues auth tokens." : `Dependency: ${authDependencyName || "not configured"}`}
            </p>
          </div>
          <div className="rounded-2xl border border-white/[0.08] bg-[#102c49] p-5">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-300">Structure</p>
            <p className="mt-2 text-lg font-semibold text-white">{modelCount} models / {endpointCount} endpoints</p>
            <p className="mt-2 text-sm leading-6 text-slate-300">{protectedRouteCount} protected routes in the current config.</p>
          </div>
        </div>

        {mediaProviders.length > 0 && (
          <div className="rounded-[1.6rem] border border-white/[0.08] bg-[#102c49] p-6">
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-300">Media Integrations</p>
                <p className="mt-3 text-lg font-semibold text-white">
                  {mediaProviders.map((provider) => provider.label).join(" • ")}
                </p>
                <p className="mt-2 text-sm leading-7 text-slate-300">
                  Assets persist in <code className="text-sky-300">{mediaCapabilities.assetCollection || "media_assets"}</code> and the current default provider is {mediaDefaultProviderLabel}.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {mediaProviders.map((provider) => (
                  <Badge
                    key={provider.id}
                    className={provider.ready
                      ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-200"
                      : "border-amber-400/30 bg-amber-500/10 text-amber-200"}
                  >
                    {provider.label}
                    {provider.default ? " default" : ""}
                  </Badge>
                ))}
              </div>
            </div>
            <p className="mt-4 text-xs leading-6 text-slate-300">
              Route testing stays JSON-based here. Use {` `}
              {(mediaCapabilities.inputModes || []).map((mode, index) => (
                <span key={mode}>
                  <code className="text-sky-300">{mode}</code>
                  {index < (mediaCapabilities.inputModes || []).length - 1 ? ", " : ""}
                </span>
              ))}
              {` `}body fields instead of multipart uploads.
            </p>
          </div>
        )}

        <div className="rounded-[1.6rem] border border-white/[0.08] bg-[#0f2741] p-6">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-300">Next Edits</p>
          <p className="mt-3 text-sm leading-7 text-slate-300">
            The left workspace panel carries runtime status, service controls, and live links. Use the actions below to jump directly into the editor section you need.
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <Button variant="outline" className="h-10 border-white/10 bg-[#12304d] px-4 text-slate-100 hover:bg-[#193d60]" onClick={() => selectPanel("env", "Service")}>
              Service Environment
            </Button>
            <Button variant="outline" className="h-10 border-white/10 bg-[#12304d] px-4 text-slate-100 hover:bg-[#193d60]" onClick={() => selectPanel("notes", "Service")}>
              Developer Notes
            </Button>
            <Button variant="outline" className="h-10 border-white/10 bg-[#12304d] px-4 text-slate-100 hover:bg-[#193d60]" onClick={() => selectPanel("keys", "Service")}>
              Setup & Docs Keys
            </Button>
            <Button variant="outline" className="h-10 border-white/10 bg-[#12304d] px-4 text-slate-100 hover:bg-[#193d60]" onClick={() => selectPanel("auth", "Auth")}>
              Auth Config
            </Button>
            <Button variant="outline" className="h-10 border-white/10 bg-[#12304d] px-4 text-slate-100 hover:bg-[#193d60]" onClick={() => selectPanel("modules", "Structure")}>
              VI Modules
            </Button>
            <Button variant="outline" className="h-10 border-white/10 bg-[#12304d] px-4 text-slate-100 hover:bg-[#193d60]" onClick={() => selectPanel("config", "Structure")}>
              Raw LAPIS Config
            </Button>
          </div>
        </div>

        <div className="mt-auto flex flex-wrap gap-3 pt-1">
          <Button className="h-11 bg-sky-400 px-5 text-slate-950 hover:bg-sky-300" onClick={fetchService}>
            Reload from Service
          </Button>
          <Button variant="outline" className="h-11 border-white/10 bg-[#12304d] px-5 text-slate-100 hover:bg-[#193d60]" onClick={() => selectPanel("testing", "Auth")}>
            Open Route Testing
          </Button>
        </div>
      </CardContent>
    </Card>
  )

  const renderEnvironmentWorkspaceCard = () => (
    <Card className={`${editorCardClass} flex min-h-full flex-col`}>
      <CardHeader className="p-6 pb-4 md:p-7 md:pb-5">
        <CardTitle className="text-xl text-white">Service Environment</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-5 p-6 pt-0 md:p-7 md:pt-0">
        <div className="rounded-2xl border border-white/[0.08] bg-[#102c49] p-5">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-300">service.env</p>
          <p className="mt-3 text-sm leading-7 text-slate-300">
            Script routes receive these values under <code className="text-sky-300">service.env.MY_KEY</code>. Use the preset buttons to scaffold media provider placeholders, then replace them with real credentials before testing.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {MEDIA_STORAGE_ENV_PRESETS.map((preset) => (
              <button
                key={preset.id}
                type="button"
                className="rounded border border-sky-300/25 bg-sky-500/10 px-2.5 py-1 text-xs font-medium text-sky-100 transition hover:bg-sky-500/20"
                onClick={() => applyServiceEnvPreset(preset.id)}
                title={preset.description}
                disabled={!canManageServices}
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>
        {mediaProviders.length > 0 && (
          <div className="grid gap-3 md:grid-cols-2">
            {mediaProviders.map((provider) => (
              <div key={provider.id} className="rounded-2xl border border-white/[0.08] bg-[#102c49] p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-semibold text-white">{provider.label}</p>
                  <Badge className={provider.ready
                    ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-200"
                    : "border-amber-400/30 bg-amber-500/10 text-amber-200"}
                  >
                    {provider.ready ? "Ready" : "Needs values"}
                  </Badge>
                  {provider.default ? (
                    <Badge className="border-sky-400/30 bg-sky-500/10 text-sky-100">Default</Badge>
                  ) : null}
                </div>
                <p className="mt-3 text-xs leading-6 text-slate-300">
                  Routes: {(provider.routes || []).map((route) => `${route.method} ${route.path}`).join(" • ") || "No provider routes detected"}
                </p>
                <p className="mt-2 text-xs leading-6 text-slate-300">
                  Env keys: {(provider.envKeys || []).join(", ") || "No media keys found"}
                </p>
              </div>
            ))}
          </div>
        )}
        <Textarea
          value={serviceEnvText}
          onChange={(e) => setServiceEnvText(e.target.value)}
          className={`min-h-[260px] font-mono text-sm ${editorTextAreaClass}`}
          placeholder={"CLOUDINARY_CLOUD_NAME=replace-with-cloud-name\nCLOUDINARY_API_KEY=replace-with-api-key"}
        />
        <div className="flex flex-wrap gap-2">
          <Button className="h-10 bg-sky-500 text-slate-950 hover:bg-sky-400" onClick={saveServiceEnvironment} disabled={saving || !canManageServices}>
            Save Environment and Restart
          </Button>
        </div>
      </CardContent>
    </Card>
  )

  if (loading) {
    return <div className="mx-auto w-full max-w-6xl px-4 py-10 text-slate-300 md:px-6">Loading service...</div>
  }

  if (error && !service) {
    return <div className="mx-auto w-full max-w-6xl px-4 py-10 text-amber-300 md:px-6">{error}</div>
  }

  return (
    <div
      data-service-management-layout="two-panel"
      className="flex h-full min-h-0 w-full overflow-hidden"
    >
      <div className="flex h-full min-h-0 w-full flex-col">
        <div className={managementShellClass}>
          <ResizablePanelGroup direction={panelDirection} className="h-full min-h-0">
            <ResizablePanel
              className="min-h-0"
              defaultSize={panelDirection === "horizontal" ? 28 : 34}
              minSize={panelDirection === "horizontal" ? 22 : 24}
              maxSize={panelDirection === "horizontal" ? 38 : 60}
            >
              <aside className="service-management-sidebar">
                <div className="flex h-full min-h-0 flex-col">
                  <div className="border-b border-white/10 px-5 py-5 md:px-6 md:py-6">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-sky-300">Service Summary</p>
                  <h1 className="mt-2 text-2xl font-bold tracking-tight text-white">{service.apiName}</h1>
                  <p className="mt-1 text-sm text-slate-300">
                    Process {service.processId} • {service.status === "RUNNING" ? "Running" : "Stopped"}
                  </p>
                </div>
                <Link href="/services" className="rounded-full border border-white/10 bg-[#12304d] px-3 py-1.5 text-xs font-semibold text-slate-100 transition hover:border-sky-400 hover:bg-[#193d60]">
                  Back
                </Link>
              </div>
              <div className={`${sidebarCardClass} mt-4 px-4 py-4`}>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge className={service.status === "RUNNING" ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-200" : "border-amber-400/30 bg-amber-500/10 text-amber-200"}>
                    {service.status === "RUNNING" ? "Running" : "Not Running"}
                  </Badge>
                  {links.productionMode ? (
                    <Badge className="border-rose-400/30 bg-rose-500/10 text-rose-200">
                      Production Mode
                    </Badge>
                  ) : null}
                  <span className="text-xs font-medium text-slate-300">Port {service.port || "_"}</span>
                  <span className="text-xs font-medium text-slate-300">{docsEnabled ? "Docs enabled" : "Docs disabled"}</span>
                  {mediaProviders.map((provider) => (
                    <Badge
                      key={provider.id}
                      className={provider.ready
                        ? "border-sky-400/30 bg-sky-500/10 text-sky-100"
                        : "border-amber-400/30 bg-amber-500/10 text-amber-200"}
                    >
                      {provider.label}
                    </Badge>
                  ))}
                </div>
                <div className="mt-4 grid gap-2 text-sm text-slate-100">
                  {links.runtime ? (
                    <a className="rounded-xl border border-sky-400/30 bg-sky-400/10 px-3 py-2 font-medium text-sky-100 transition hover:border-sky-300 hover:bg-sky-400/20" target="_blank" rel="noreferrer" href={links.runtime}>Runtime</a>
                  ) : (
                    <span className="rounded-xl border border-dashed border-white/10 px-3 py-2 text-slate-400">Runtime unavailable</span>
                  )}
                  {links.root ? (
                    <a className="rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 font-medium text-slate-100 transition hover:border-sky-400 hover:bg-white/[0.08]" target="_blank" rel="noreferrer" href={links.root}>Service Root</a>
                  ) : null}
                  {links.liwiroDocs ? (
                    <a className="rounded-xl border border-sky-400/30 bg-sky-400/10 px-3 py-2 font-medium text-sky-100 transition hover:border-sky-300 hover:bg-sky-400/20" target="_blank" rel="noreferrer" href={links.liwiroDocs}>Service Docs</a>
                  ) : (
                    <span className="rounded-xl border border-dashed border-white/10 px-3 py-2 text-slate-400">
                      {links.docsEnabled === false ? "Docs disabled" : "Service docs unavailable"}
                    </span>
                  )}
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2">
                  <Button variant="outline" className="h-9 border-white/10 bg-[#12304d] text-slate-100 hover:bg-[#193d60]" onClick={() => callAction("start")} disabled={!canManageServices}>Start</Button>
                  <Button variant="outline" className="h-9 border-white/10 bg-[#12304d] text-slate-100 hover:bg-[#193d60]" onClick={() => callAction("stop")} disabled={!canManageServices}>Stop</Button>
                  <Button variant="outline" className="h-9 border-white/10 bg-[#12304d] text-slate-100 hover:bg-[#193d60]" onClick={() => toggleDocs(!docsEnabled)} disabled={saving || !canManageServices}>
                    {docsEnabled ? "Disable Docs" : "Enable Docs"}
                  </Button>
                  <Button variant="outline" className="h-9 border-rose-400/30 bg-rose-500/10 text-rose-200 hover:bg-rose-500/20" onClick={() => setDeleteOpen(true)} disabled={!canManageServices}>Delete</Button>
                </div>
              </div>
                  </div>

                  <div className="flex-1 overflow-y-auto overscroll-contain px-4 py-4 md:px-5 md:py-5">
              <div className="mb-6 space-y-4 px-1">
                <div className={`${sidebarCardClass} p-4`}>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-300">Workspace Status</p>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <span className="rounded-full border border-sky-400/30 bg-sky-400/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-sky-100">
                      {activePanelGroup.title}
                    </span>
                    <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-100">
                      {isTextEditorMode ? "Text Mode" : "Structured Mode"}
                    </span>
                  </div>
                  <div className="mt-3">
                    <p className="text-sm font-bold text-white">{activePanelMeta.label}</p>
                    <p className="mt-0.5 text-xs text-slate-300">{activePanelMeta.hint}</p>
                  </div>
                </div>

                <div className={`${sidebarCardClass} p-4`}>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-300">Service Overview</p>
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    <div className={`${sidebarSoftCardClass} p-3`}>
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Models</p>
                      <p className="mt-1 text-lg font-bold text-white">{modelCount}</p>
                    </div>
                    <div className={`${sidebarSoftCardClass} p-3`}>
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Endpoints</p>
                      <p className="mt-1 text-lg font-bold text-white">{endpointCount}</p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                {PANEL_GROUPS.map((group) => (
                  <div key={group.title} className={`${sidebarCardClass} overflow-hidden`}>
                    <button
                      type="button"
                      onClick={() => togglePanelGroup(group.title)}
                      className="flex w-full items-start justify-between gap-3 px-4 py-4 text-left"
                    >
                      <div className="min-w-0">
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-300">{group.title}</p>
                        <p className="mt-1 text-sm font-semibold text-white">
                          {group.title === "Service" && `${service.status === "RUNNING" ? "Running" : "Stopped"} • ${docsEnabled ? "docs on" : "docs off"} • port ${service.port || "_"}`}
                          {group.title === "Auth" && `${authEnabled ? "Auth on" : "Auth off"} • ${protectedRouteCount} protected routes • ${authToken ? "token captured" : "no token"}`}
                          {group.title === "Structure" && `${modelCount} models • ${endpointCount} endpoints • ${moduleCount} modules`}
                        </p>
                        <p className="mt-1 text-xs text-slate-300">
                          {group.title === "Service" && notesSummary}
                          {group.title === "Auth" && (authIsAuthService ? "This service issues auth tokens." : `Dependency: ${authDependencyName || "not configured"}`)}
                          {group.title === "Structure" && (endpointConfigs[0] ? `${endpointConfigs[0].method} ${endpointConfigs[0].path}${endpointConfigs.length > 1 ? ` and ${endpointConfigs.length - 1} more routes` : ""} • ${moduleCount} module${moduleCount === 1 ? "" : "s"}` : `No models or endpoints configured yet. ${moduleCount} module${moduleCount === 1 ? "" : "s"} attached.`)}
                        </p>
                      </div>
                      {collapsedGroups[group.title] ? <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-slate-300" /> : <ChevronDown className="mt-1 h-4 w-4 shrink-0 text-slate-300" />}
                    </button>
                    {!collapsedGroups[group.title] && (
                      <div className="space-y-4 border-t border-white/10 px-4 py-4">
                        {group.title === "Service" && (
                          <>
                            <div className="grid gap-3 text-sm text-slate-100">
                              <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
                                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-300">Overview</p>
                                <p className="mt-2 text-sm text-slate-100">Base path: <span className="font-semibold">{basePath || "/"}</span></p>
                                <p className="mt-1 text-sm text-slate-100">Docs key: <span className="font-semibold">{docsKeyConfigured ? "configured" : "not configured"}</span></p>
                                <p className="mt-1 text-sm text-slate-100">Setup key: <span className="font-semibold">{setupApiKey ? "configured" : "not configured"}</span></p>
                              </div>
                              {mediaProviders.length > 0 && (
                                <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
                                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-300">Media</p>
                                  <p className="mt-2 text-sm text-slate-100">{mediaProviders.map((provider) => provider.label).join(" • ")}</p>
                                  <p className="mt-1 text-sm text-slate-100">Default: <span className="font-semibold">{mediaDefaultProviderLabel}</span></p>
                                  <p className="mt-1 text-xs text-slate-300">Assets: {mediaCapabilities.assetCollection || "media_assets"}</p>
                                </div>
                              )}
                              <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
                                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-300">Notes</p>
                                <p className="mt-2 text-sm text-slate-100">{notesSummary}</p>
                              </div>
                            </div>
                            <div className="flex flex-wrap gap-2">
                              {group.items.map((item) => (
                                <button
                                  key={item.id}
                                  type="button"
                                  onClick={() => selectPanel(item.id, group.title)}
                                  className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                                    activePanel === item.id
                                      ? "border-sky-300 bg-sky-400/[0.15] text-white"
                                      : "border-white/10 bg-[#0f2740] text-slate-100 hover:border-sky-400 hover:bg-[#17395a]"
                                  }`}
                                >
                                  {item.label}
                                </button>
                              ))}
                            </div>
                          </>
                        )}

                        {group.title === "Auth" && (
                          <>
                            <div className="grid gap-3 text-sm text-slate-100">
                              <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
                                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-300">Security</p>
                                <p className="mt-2">Auth enabled: <span className="font-semibold">{authEnabled ? "Yes" : "No"}</span></p>
                                <p className="mt-1">Auth service: <span className="font-semibold">{authIsAuthService ? "This service" : (authDependencyName || "Not configured")}</span></p>
                                <p className="mt-1">Protected routes: <span className="font-semibold">{protectedRouteCount}</span></p>
                              </div>
                              <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
                                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-300">Runtime Auth</p>
                                <p className="mt-2 break-all text-xs font-medium text-slate-200">{authTargetSignInRoute || "No signin route"}</p>
                                <p className="mt-1 break-all text-xs font-medium text-slate-200">{authTargetSignOutRoute || "No signout route"}</p>
                                <p className="mt-2 text-sm">Token: <span className="font-semibold">{authToken ? "Captured" : "Not captured"}</span></p>
                              </div>
                            </div>
                            <div className="flex flex-wrap gap-2">
                              {group.items.map((item) => (
                                <button
                                  key={item.id}
                                  type="button"
                                  onClick={() => selectPanel(item.id, group.title)}
                                  className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                                    activePanel === item.id
                                      ? "border-sky-300 bg-sky-400/[0.15] text-white"
                                      : "border-white/10 bg-[#0f2740] text-slate-100 hover:border-sky-400 hover:bg-[#17395a]"
                                  }`}
                                >
                                  {item.label}
                                </button>
                              ))}
                            </div>
                          </>
                        )}

                        {group.title === "Structure" && (
                          <>
                            <div className="grid gap-3 text-sm text-slate-100">
                              <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
                                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-300">Models</p>
                                <p className="mt-2">{modelCount} configured models</p>
                                <p className="mt-1 text-xs text-slate-300">
                                  {modelDrafts.slice(0, 4).map((model) => model.name || model.id).join(" • ") || "No models yet"}
                                </p>
                              </div>
                              <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
                                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-300">Endpoints</p>
                                <p className="mt-2">{endpointCount} routes, {protectedRouteCount} protected</p>
                                <p className="mt-1 text-xs text-slate-300">
                                  {endpointConfigs.slice(0, 4).map((route) => `${route.method} ${route.path}`).join(" • ") || "No endpoints yet"}
                                </p>
                              </div>
                              <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
                                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-300">VI Modules</p>
                                <p className="mt-2">{sharedModuleCount} shared, {moduleCount} attached</p>
                                <p className="mt-1 text-xs text-slate-300">
                                  {[
                                    ...Object.keys(sharedModuleDrafts || {}).slice(0, 2),
                                    ...moduleDrafts.slice(0, 2).map((module) => module.name || "").filter(Boolean),
                                  ].join(" • ") || "No modules yet"}
                                </p>
                              </div>
                            </div>
                            <div className="flex flex-wrap gap-2">
                              {group.items.map((item) => (
                                <button
                                  key={item.id}
                                  type="button"
                                  onClick={() => selectPanel(item.id, group.title)}
                                  className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                                    activePanel === item.id
                                      ? "border-sky-300 bg-sky-400/[0.15] text-white"
                                      : "border-white/10 bg-[#0f2740] text-slate-100 hover:border-sky-400 hover:bg-[#17395a]"
                                  }`}
                                >
                                  {item.label}
                                </button>
                              ))}
                            </div>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
                  </div>
                </div>
              </aside>
            </ResizablePanel>

            <ResizableHandle withHandle className="bg-slate-200/[0.85] dark:bg-slate-800/80" />

            <ResizablePanel className="min-h-0" defaultSize={panelDirection === "horizontal" ? 72 : 66} minSize={40}>
        <section className="service-management-editor">
          <div className="flex h-full min-w-0 flex-col">
            <div className="service-management-editor-toolbar px-6 py-6 md:px-8">
              <div className="flex flex-col gap-4">
                <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase tracking-[0.22em] text-sky-300">
                      Editor Workspace • {activePanelGroup.title}
                    </p>
                    <h2 className="mt-2 text-3xl font-bold tracking-tight text-white">{activePanelMeta.label}</h2>
                    <p className="mt-1 max-w-2xl text-sm text-slate-300">{activePanelMeta.hint}</p>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <span className="rounded-full border border-white/10 bg-[#102845] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-sky-100">
                        {service.apiName}
                      </span>
                      <span className="rounded-full border border-white/10 bg-[#12304d] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-sky-200/[0.85]">
                        {service.status === "RUNNING" ? "Running" : "Stopped"}
                      </span>
                      <span className="rounded-full border border-white/10 bg-[#12304d] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-sky-200/[0.85]">
                        {isTextEditorMode ? "Text Mode" : "Structured Mode"}
                      </span>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {hasStructuredEditorMode && (
                      <button
                        type="button"
                        onClick={() => switchEditorMode("structured")}
                        className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${
                          !isTextEditorMode
                            ? "border-sky-300 bg-sky-400/[0.15] text-white"
                            : "border-white/10 bg-[#12304d] text-sky-200 hover:border-sky-500 hover:bg-[#193d60]"
                        }`}
                      >
                        Structured Mode
                      </button>
                    )}
                    {hasTextEditorMode && (
                      <button
                        type="button"
                        onClick={() => switchEditorMode("text")}
                        className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${
                          isTextEditorMode
                            ? "border-sky-300 bg-sky-400/[0.15] text-white"
                            : "border-white/10 bg-[#12304d] text-sky-200 hover:border-sky-500 hover:bg-[#193d60]"
                        }`}
                      >
                        Text Mode
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-hidden px-6 py-6 md:px-8 md:py-8">
                <div className="h-full min-h-0 overflow-y-auto overscroll-contain pr-1">
                  <div className="flex min-h-full flex-col">
                <div className="mb-5 grid gap-4 xl:grid-cols-[minmax(16rem,0.72fr)_minmax(0,1.28fr)]">
                  <div className={`${editorCardClass} p-5`}>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-300/80">Service Overview</p>
                    <div className="mt-4 grid grid-cols-2 gap-3">
                      <div className="rounded-[1.05rem] border border-white/10 bg-[#12304d] p-4">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-sky-300/80">Models</p>
                        <p className="mt-2 text-2xl font-bold text-white">{modelCount}</p>
                      </div>
                      <div className="rounded-[1.05rem] border border-white/10 bg-[#12304d] p-4">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-sky-300/80">Endpoints</p>
                        <p className="mt-2 text-2xl font-bold text-white">{endpointCount}</p>
                      </div>
                      <div className="rounded-[1.05rem] border border-white/10 bg-[#12304d] p-4">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-sky-300/80">Modules</p>
                        <p className="mt-2 text-2xl font-bold text-white">{moduleCount}</p>
                      </div>
                    </div>
                    <p className="mt-4 text-sm text-slate-300">
                      Base path <span className="font-semibold text-white">{basePath || "/"}</span> with {protectedRouteCount} protected route{protectedRouteCount === 1 ? "" : "s"} and {moduleCount} attached module{moduleCount === 1 ? "" : "s"}.
                    </p>
                  </div>

                  <div className={`${editorCardClass} p-5`}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-300/80">Quick Reference</p>
                        <p className="mt-2 text-lg font-semibold text-white">Jump across service manager features</p>
                      </div>
                      <span className="rounded-full border border-white/10 bg-[#12304d] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-sky-200">
                        {activePanelMeta.label}
                      </span>
                    </div>
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      {PANEL_GROUPS.map((group) => (
                        <div key={`quick-${group.title}`} className="rounded-[1.05rem] border border-white/10 bg-[#12304d] p-4">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-sky-300/80">{group.title}</p>
                          <div className="mt-3 flex flex-wrap gap-2">
                            {group.items.map((item) => (
                              <button
                                key={`quick-${group.title}-${item.id}`}
                                type="button"
                                onClick={() => selectPanel(item.id, group.title)}
                                className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                                  activePanel === item.id
                                    ? "border-sky-300 bg-sky-400/[0.15] text-white"
                                    : "border-white/10 bg-[#0f2740] text-sky-100 hover:border-sky-400 hover:bg-[#17395a]"
                                }`}
                              >
                                {item.label}
                              </button>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                {isTextEditorMode ? (
                <Card className={`${editorCardClass} flex min-h-full flex-col`}>
                  <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
                    <div>
                      <CardTitle className="text-xl text-white">{getTextEditorMeta(activePanel).title}</CardTitle>
                      <p className="mt-2 text-sm text-slate-300">{getTextEditorMeta(activePanel).description}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button variant="outline" className="h-9 border-white/10 bg-[#12304d] text-sky-100 hover:bg-[#193d60]" onClick={() => setTextEditorValue(buildTextEditorValue(activePanel))}>
                        Reset
                      </Button>
                      <Button variant="outline" className="h-9 border-white/10 bg-[#12304d] text-sky-100 hover:bg-[#193d60]" onClick={() => setLapisFullHeight((prev) => !prev)}>
                        {lapisFullHeight ? "Normal Height" : "Full Height"}
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent className="flex min-h-0 flex-1 flex-col">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <span className="rounded-full border border-white/10 bg-[#12304d] px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-sky-200">
                        {getTextEditorMeta(activePanel).language}
                      </span>
                      <span className="text-xs text-slate-400">Direct editing mode</span>
                    </div>
                    <Textarea
                      value={textEditorValue}
                      onChange={(e) => setTextEditorValue(e.target.value)}
                      className={`${lapisFullHeight ? "min-h-[72vh]" : "min-h-[58vh]"} flex-1 ${editorTextAreaClass} font-mono text-sm leading-6`}
                      placeholder={getTextEditorMeta(activePanel).placeholder}
                    />
                    {(textEditorError || error) && (
                      <p className="mt-3 text-sm text-amber-300">{textEditorError || error}</p>
                    )}
                    <div className="mt-4 flex flex-wrap gap-2">
                      <Button onClick={saveTextEditor} className="h-10 bg-sky-500 text-slate-950 hover:bg-sky-400" disabled={saving || !canManageServices}>
                        {saving ? "Saving..." : getTextEditorMeta(activePanel).saveLabel}
                      </Button>
                      <Button variant="outline" className="h-10 border-white/10 bg-[#12304d] text-sky-100 hover:bg-[#193d60]" onClick={fetchService}>
                        Reload from Service
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-6">

      {activePanel === "overview" && renderOverviewWorkspaceCard()}

      {activePanel === "env" && renderEnvironmentWorkspaceCard()}

      {activePanel === "notes" && (
      <Card className={`${editorCardClass} flex min-h-full flex-col`}>
        <CardHeader>
          <CardTitle className="text-xl text-white">Developer Notes</CardTitle>
        </CardHeader>
        <CardContent>
          <Textarea
            value={developerNotes}
            onChange={(e) => setDeveloperNotes(e.target.value)}
            className={`min-h-[130px] ${editorTextAreaClass}`}
            placeholder="Notes shown inside Service Docs."
          />
          <div className="mt-4 flex flex-wrap gap-2">
            <Button className="h-10 bg-sky-500 text-slate-950 hover:bg-sky-400" onClick={saveDeveloperNotes} disabled={saving || !canManageServices}>
              Save Notes and Restart
            </Button>
          </div>
        </CardContent>
      </Card>
      )}

      {activePanel === "keys" && (
      <Card className={`${editorCardClass} flex min-h-full flex-col`}>
        <CardHeader>
          <CardTitle className="text-xl text-white">Service Setup Keys</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-4 md:grid-cols-[220px_1fr] md:items-center">
            <p className="text-sm font-semibold text-sky-200">`metadata.setupApiKey`</p>
            <PasswordInput
              value={setupApiKey}
              onChange={(e) => setSetupApiKey(e.target.value)}
              placeholder="Set setup API key used by /liwiro/setup routes"
              className={`h-10 ${editorTextAreaClass}`}
              actions={[
                {
                  key: "generate-setup-api-key",
                  label: "Generate setup API key",
                  onClick: generateSetupApiKey,
                  icon: <RefreshCw className="h-4 w-4" />,
                },
              ]}
            />
          </div>
          <div className="grid gap-4 md:grid-cols-[220px_1fr] md:items-center">
            <p className="text-sm font-semibold text-sky-200">
              `metadata.documentation.key`
              <span className="ml-2 text-xs text-slate-400">
                ({docsKeyConfigured ? "configured" : "not configured"})
              </span>
            </p>
            <div className="space-y-2">
              <PasswordInput
                value={documentationKey}
                onChange={(e) => setDocumentationKey(e.target.value)}
                placeholder="Service documentation key"
                className={`h-10 font-mono text-xs ${editorTextAreaClass}`}
                actions={[
                  {
                    key: "generate-documentation-key",
                    label: "Generate documentation key",
                    onClick: generateDocumentationKey,
                    icon: <RefreshCw className="h-4 w-4" />,
                  },
                ]}
              />
              <p className="text-xs text-slate-300">
                Per-service key. LAPIS examples default to <code className="text-sky-300">liwiroservicepass0!</code>, and you can rotate each service key independently here.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 pt-2">
            <Button className="h-10 bg-sky-500 text-slate-950 hover:bg-sky-400" onClick={saveStructuredConfig} disabled={saving || !canManageServices}>
              Save Setup Key + Restart
            </Button>
            <Button variant="outline" className="h-10 border-white/10 bg-[#12304d] text-sky-100 hover:bg-[#193d60]" onClick={saveDocumentationKey} disabled={saving || !canManageServices}>
              Save Documentation Key + Restart
            </Button>
          </div>
        </CardContent>
      </Card>
      )}

      {activePanel === "auth" && (
      <Card className={`${editorCardClass} flex min-h-full flex-col`}>
        <CardHeader>
          <CardTitle className="text-xl text-white">Authentication Configuration</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-4 md:grid-cols-2">
            <label className="flex items-center gap-2 rounded-xl border border-white/[0.08] bg-[#102c49] px-4 py-2.5 text-sm text-sky-100">
              <input
                type="checkbox"
                className="accent-sky-500"
                checked={Boolean(authDraft.enabled)}
                onChange={(e) => setAuthDraft((prev) => ({ ...prev, enabled: e.target.checked }))}
              />
              Authentication Enabled
            </label>
            <label className="flex items-center gap-2 rounded-xl border border-white/[0.08] bg-[#102c49] px-4 py-2.5 text-sm text-sky-100">
              <input
                type="checkbox"
                className="accent-sky-500"
                checked={Boolean(authDraft.isAuthService)}
                onChange={(e) => setAuthDraft((prev) => ({ ...prev, isAuthService: e.target.checked }))}
              />
              This Service Is Auth Service
            </label>
            <label className="flex items-center gap-2 rounded-xl border border-white/[0.08] bg-[#102c49] px-4 py-2.5 text-sm text-sky-100">
              <input
                type="checkbox"
                className="accent-sky-500"
                checked={Boolean(authDraft.useAsymmetricJWT)}
                onChange={(e) => setAuthDraft((prev) => ({ ...prev, useAsymmetricJWT: e.target.checked }))}
              />
              Use JWT Verification
            </label>
            <select
              className={`h-11 rounded-xl border-white/10 bg-[#091522] px-4 text-sm text-sky-100 ${editorTextAreaClass}`}
              value={authDraft.keyManagement || "auto"}
              onChange={(e) => setAuthDraft((prev) => ({ ...prev, keyManagement: e.target.value }))}
            >
              <option value="auto">Auto Key Management</option>
              <option value="manual">Manual Key Management</option>
            </select>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Input
              value={authDraft.authModel || ""}
              onChange={(e) => setAuthDraft((prev) => ({ ...prev, authModel: e.target.value }))}
              className={`h-11 ${editorTextAreaClass}`}
              placeholder="Auth model name"
            />
            <Input
              value={authDraft.authServiceName || ""}
              onChange={(e) => setAuthDraft((prev) => ({ ...prev, authServiceName: e.target.value }))}
              className={`h-11 ${editorTextAreaClass}`}
              placeholder="Dependency auth service name"
            />
            <Textarea
              value={authDraft.publicKey || ""}
              onChange={(e) => setAuthDraft((prev) => ({ ...prev, publicKey: e.target.value }))}
              className={`min-h-[120px] font-mono text-sm ${editorTextAreaClass}`}
              placeholder="Public key"
            />
            <Textarea
              value={authDraft.authServicePublicKey || ""}
              onChange={(e) => setAuthDraft((prev) => ({ ...prev, authServicePublicKey: e.target.value }))}
              className={`min-h-[120px] font-mono text-sm ${editorTextAreaClass}`}
              placeholder="Auth service public key for JWT verification"
            />
          </div>
          {authIsAuthService ? (
            <div className="rounded-2xl border border-amber-400/25 bg-amber-500/10 p-5">
              <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                <div className="space-y-2">
                  <p className="text-sm font-semibold text-amber-100">Authentication Material Export</p>
                  <p className="text-xs leading-6 text-amber-50/90">
                    Caution: downloaded private keys or shared secrets can issue valid bearer tokens for this service. Export only over trusted operator sessions and store the files outside version control.
                  </p>
                </div>
                <Button
                  variant="outline"
                  className="h-10 border-amber-300/40 bg-[#5b3a10] text-amber-100 hover:bg-[#724914]"
                  onClick={downloadAuthKeys}
                  disabled={downloadingAuthKeys || !canManageServices}
                >
                  {downloadingAuthKeys ? "Downloading..." : "Download Auth Keys"}
                </Button>
              </div>
            </div>
          ) : null}
          <div className="rounded-2xl border border-white/[0.08] bg-[#102c49] p-5">
            <div className="mb-4 space-y-2">
              <p className="text-sm font-semibold text-white">Password Reset Submission</p>
              <p className="text-xs text-slate-300">
                Choose whether forgot-password emails open the generated reset form or a custom submission page where Liwiro appends the token.
              </p>
            </div>
            <div className="space-y-4">
              <select
                className={`h-11 rounded-xl border-white/10 bg-[#0d2138] px-4 text-sm text-sky-100 ${editorTextAreaClass}`}
                value={authResetPageMode}
                onChange={(e) => {
                  const nextMode = e.target.value === "custom_page" ? "custom_page" : "auto_form"
                  setAuthDraft((prev) => ({
                    ...prev,
                    passwordResetPage: {
                      ...(prev.passwordResetPage || {}),
                      submissionMode: nextMode,
                      enabled: nextMode === "auto_form",
                    },
                  }))
                }}
              >
                <option value="auto_form">Auto-generated reset form</option>
                <option value="custom_page">Custom submission page link</option>
              </select>
            {authResetPageMode === "custom_page" ? (
              <div className="space-y-2">
                <Input
                  value={authDraft.passwordResetPage?.customPageBaseUrl || ""}
                  onChange={(e) => setAuthDraft((prev) => ({
                    ...prev,
                    passwordResetPage: {
                      ...(prev.passwordResetPage || {}),
                      customPageBaseUrl: e.target.value,
                    },
                  }))}
                  className={`h-11 ${editorTextAreaClass}`}
                  placeholder="https://app.example.com/reset-password"
                />
                <p className="text-xs text-slate-300">
                  The email link uses this base and appends the token as `?token=...` or `&token=...`.
                </p>
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2">
                <Input
                  value={authDraft.passwordResetPage?.title || ""}
                  onChange={(e) => setAuthDraft((prev) => ({
                    ...prev,
                    passwordResetPage: {
                      ...(prev.passwordResetPage || {}),
                      title: e.target.value,
                    },
                  }))}
                  className={`h-11 ${editorTextAreaClass}`}
                  placeholder="Page title"
                />
                <Input
                  value={authDraft.passwordResetPage?.submitLabel || ""}
                  onChange={(e) => setAuthDraft((prev) => ({
                    ...prev,
                    passwordResetPage: {
                      ...(prev.passwordResetPage || {}),
                      submitLabel: e.target.value,
                    },
                  }))}
                  className={`h-11 ${editorTextAreaClass}`}
                  placeholder="Submit button label"
                />
                <Textarea
                  value={authDraft.passwordResetPage?.description || ""}
                  onChange={(e) => setAuthDraft((prev) => ({
                    ...prev,
                    passwordResetPage: {
                      ...(prev.passwordResetPage || {}),
                      description: e.target.value,
                    },
                  }))}
                  className={`min-h-[110px] text-sm md:col-span-2 ${editorTextAreaClass}`}
                  placeholder="Page description"
                />
                <Input
                  value={authDraft.passwordResetPage?.loadingMessage || ""}
                  onChange={(e) => setAuthDraft((prev) => ({
                    ...prev,
                    passwordResetPage: {
                      ...(prev.passwordResetPage || {}),
                      loadingMessage: e.target.value,
                    },
                  }))}
                  className={`h-11 ${editorTextAreaClass}`}
                  placeholder="Loading message"
                />
                <Input
                  value={authDraft.passwordResetPage?.successMessage || ""}
                  onChange={(e) => setAuthDraft((prev) => ({
                    ...prev,
                    passwordResetPage: {
                      ...(prev.passwordResetPage || {}),
                      successMessage: e.target.value,
                    },
                  }))}
                  className={`h-11 ${editorTextAreaClass}`}
                  placeholder="Success message"
                />
                <Input
                  value={authDraft.passwordResetPage?.failureMessage || ""}
                  onChange={(e) => setAuthDraft((prev) => ({
                    ...prev,
                    passwordResetPage: {
                      ...(prev.passwordResetPage || {}),
                      failureMessage: e.target.value,
                    },
                  }))}
                  className={`h-11 md:col-span-2 ${editorTextAreaClass}`}
                  placeholder="Failure message"
                />
              </div>
            )}
            </div>
          </div>
          <div className="flex pt-2">
            <Button className="h-10 bg-sky-500 text-slate-950 hover:bg-sky-400" onClick={saveStructuredConfig} disabled={saving || !canManageServices}>
              Save Auth Config + Restart
            </Button>
          </div>
        </CardContent>
      </Card>
      )}

      {activePanel === "models" && (
      <Card className={`${editorCardClass} flex min-h-full flex-col`}>
        <CardHeader>
          <CardTitle className="text-xl text-white">Models Editor</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {(modelDrafts || []).length === 0 ? (
            <p className="text-sm text-slate-300">No models found.</p>
          ) : (
            <div className="space-y-4">
              {modelDrafts.map((model) => (
                <div key={model.id} className="rounded-2xl border border-white/[0.08] bg-[#102c49] p-5">
                  <div className="mb-4 flex items-center justify-between gap-3">
                    <button
                      type="button"
                      className="inline-flex items-center gap-2 text-sm font-bold text-white transition hover:text-sky-300"
                      onClick={() => setCollapsedModels((prev) => ({ ...prev, [model.id]: !prev[model.id] }))}
                    >
                      {collapsedModels[model.id] ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                      <span>{model.name || model.id}</span>
                    </button>
                    <Button variant="outline" className="h-9 w-9 p-0 border-rose-300/25 bg-[#2a1730] text-rose-200 hover:bg-[#3a1d40]" onClick={() => removeModelDraft(model.id)} disabled={!canManageServices}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                  {!collapsedModels[model.id] && (
                    <div className="space-y-5">
                      <div className="grid gap-4 md:grid-cols-2">
                        <Input value={model.name || ""} onChange={(e) => updateModelDraft(model.id, "name", e.target.value)} placeholder="Model Name" className={`h-10 ${editorTextAreaClass}`} />
                        <Input value={model.collection || ""} onChange={(e) => updateModelDraft(model.id, "collection", e.target.value)} placeholder="Collection Name" className={`h-10 ${editorTextAreaClass}`} />
                      </div>
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <p className="text-xs font-semibold uppercase tracking-wider text-sky-300/80">Fields</p>
                          <Button variant="outline" className="h-8 border-white/10 bg-[#12304d] text-sky-100 hover:bg-[#193d60]" onClick={() => addModelFieldDraft(model.id)} disabled={!canManageServices}>
                            <Plus className="mr-1 h-3.5 w-3.5" /> Add Field
                          </Button>
                        </div>
                        {(model.fieldsDrafts || []).length === 0 ? (
                          <p className="text-xs text-slate-400">No fields yet.</p>
                        ) : (
                          (model.fieldsDrafts || []).map((field) => (
                            <div key={field.id} className="rounded-xl border border-white/[0.08] bg-[#102c49] p-4">
                              <div className="grid gap-4 md:grid-cols-3">
                                <Input value={field.id || ""} onChange={(e) => updateModelFieldDraft(model.id, field.id, "id", e.target.value)} placeholder="Field ID" className={`h-10 ${editorTextAreaClass} font-mono`} />
                                <Input value={field.name || ""} onChange={(e) => updateModelFieldDraft(model.id, field.id, "name", e.target.value)} placeholder="Field Name" className={`h-10 ${editorTextAreaClass}`} />
                                <select
                                  className={`h-10 rounded-md border border-white/10 bg-[#091522] px-3 text-sm text-sky-100 ${editorTextAreaClass}`}
                                  value={field.type || "string"}
                                  onChange={(e) => updateModelFieldDraft(model.id, field.id, "type", e.target.value)}
                                >
                                  <option value="string">string</option>
                                  <option value="number">number</option>
                                  <option value="boolean">boolean</option>
                                  <option value="date">date</option>
                                  <option value="object">object</option>
                                </select>
                              </div>
                              <div className="mt-4 grid gap-4 md:grid-cols-3 md:items-center">
                                <label className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-[#102c49] px-3 py-2 text-xs text-sky-100">
                                  <input
                                    type="checkbox"
                                    className="accent-sky-500"
                                    checked={Boolean(field.required)}
                                    onChange={(e) => updateModelFieldDraft(model.id, field.id, "required", e.target.checked)}
                                  />
                                  Required
                                </label>
                                <Input value={field.relationModel || ""} onChange={(e) => updateModelFieldDraft(model.id, field.id, "relationModel", e.target.value)} placeholder="Relationship target model (optional)" className={`h-10 ${editorTextAreaClass}`} />
                                <div className="flex items-center gap-2">
                                  <select
                                    className={`h-10 w-full rounded-md border border-white/10 bg-[#091522] px-3 text-sm text-sky-100 ${editorTextAreaClass}`}
                                    value={field.relationType || ""}
                                    onChange={(e) => updateModelFieldDraft(model.id, field.id, "relationType", e.target.value)}
                                  >
                                    <option value="">No relationship type</option>
                                    <option value="one-to-one">one-to-one</option>
                                    <option value="one-to-many">one-to-many</option>
                                    <option value="many-to-one">many-to-one</option>
                                    <option value="many-to-many">many-to-many</option>
                                  </select>
                                  <Button variant="outline" className="h-10 w-10 p-0 border-rose-300/25 bg-[#2a1730] text-rose-200 hover:bg-[#3a1d40]" onClick={() => removeModelFieldDraft(model.id, field.id)} disabled={!canManageServices}>
                                    <Trash2 className="h-4 w-4" />
                                  </Button>
                                </div>
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
              <div className="flex flex-wrap gap-2 pt-2">
                <Button variant="outline" className="h-10 border-white/10 bg-[#12304d] text-sky-100 hover:bg-[#193d60]" onClick={addModelDraft} disabled={!canManageServices}>
                  Add Model
                </Button>
                <Button className="h-10 bg-sky-500 text-slate-950 hover:bg-sky-400" onClick={saveStructuredConfig} disabled={saving || !canManageServices}>
                  Save Models + Restart
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
      )}

      {activePanel === "endpoints" && (
      <Card className={`${editorCardClass} flex min-h-full flex-col`}>
        <CardHeader>
          <CardTitle className="text-xl text-white">Structured Endpoint Editor</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {(endpointDrafts || []).length === 0 ? (
            <p className="text-sm text-slate-300">No endpoints found.</p>
          ) : (
            <div className="space-y-4">
              {endpointDrafts.map((ep) => (
                <div key={ep.id} className="rounded-2xl border border-white/[0.08] bg-[#102c49] p-5">
                  <div className="mb-4 flex items-center justify-between gap-3">
                    <button
                      type="button"
                      className="inline-flex items-center gap-2 text-sm font-bold text-white transition hover:text-sky-300"
                      onClick={() => setCollapsedEndpoints((prev) => ({ ...prev, [ep.id]: !prev[ep.id] }))}
                    >
                      {collapsedEndpoints[ep.id] ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                      <span>{`${ep.method || "GET"} ${ep.path || ep.id}`}</span>
                    </button>
                  </div>
                  {!collapsedEndpoints[ep.id] && (
                    <div className="space-y-5">
                      <div className="grid gap-4 md:grid-cols-4">
                        <select
                          className={`h-11 rounded-xl border-white/10 bg-[#091522] px-4 text-sm text-sky-100 ${editorTextAreaClass}`}
                          value={ep.method || "GET"}
                          onChange={(e) => updateEndpointDraft(ep.id, "method", e.target.value)}
                        >
                          <option value="GET">GET</option>
                          <option value="POST">POST</option>
                          <option value="PUT">PUT</option>
                          <option value="DELETE">DELETE</option>
                        </select>
                        <Input value={ep.path || ""} onChange={(e) => updateEndpointDraft(ep.id, "path", e.target.value)} placeholder="Path" className={`h-11 ${editorTextAreaClass}`} />
                        <select
                          className={`h-11 rounded-xl border-white/10 bg-[#091522] px-4 text-sm text-sky-100 ${editorTextAreaClass}`}
                          value={normalizeOperationType(ep.operationType || "crud")}
                          onChange={(e) => updateEndpointDraft(ep.id, "operationType", normalizeOperationType(e.target.value))}
                        >
                          <option value="crud">crud</option>
                          <option value="custom">custom</option>
                          <option value="script">script</option>
                        </select>
                        <Input value={ep.linkedModel || ""} onChange={(e) => updateEndpointDraft(ep.id, "linkedModel", e.target.value)} placeholder="Linked Model (for CRUD)" className={`h-11 ${editorTextAreaClass}`} />
                      </div>
                      <div className="grid gap-4 md:grid-cols-4">
                        <select
                          className={`h-11 rounded-xl border-white/10 bg-[#091522] px-4 text-sm text-sky-100 ${editorTextAreaClass}`}
                          value={normalizeCrudOperation(ep.crudOperation || "read")}
                          onChange={(e) => updateEndpointDraft(ep.id, "crudOperation", normalizeCrudOperation(e.target.value))}
                        >
                          <option value="create">create</option>
                          <option value="read">read</option>
                          <option value="update">update</option>
                          <option value="delete">delete</option>
                        </select>
                        <label className="flex items-center gap-2 rounded-xl border border-white/[0.08] bg-[#102c49] px-4 py-2 text-sm text-sky-100">
                          <input
                            type="checkbox"
                            className="accent-sky-500"
                            checked={Boolean(ep.requiresAuth)}
                            onChange={(e) => updateEndpointDraft(ep.id, "requiresAuth", e.target.checked)}
                          />
                          Requires Auth
                        </label>
                        <label className="flex items-center gap-2 rounded-xl border border-white/[0.08] bg-[#102c49] px-4 py-2 text-sm text-sky-100">
                          <input
                            type="checkbox"
                            className="accent-sky-500"
                            checked={ep.enabled !== false}
                            onChange={(e) => updateEndpointDraft(ep.id, "enabled", e.target.checked)}
                          />
                          Enabled
                        </label>
                        <Input value={ep.vqlQuery || ""} onChange={(e) => updateEndpointDraft(ep.id, "vqlQuery", e.target.value)} placeholder="Custom VQL summary" className={`h-11 ${editorTextAreaClass}`} />
                      </div>
                      {normalizeOperationType(ep.operationType) === "custom" && (
                        <div className="rounded-xl border border-white/[0.08] bg-[#102c49] p-4">
                          <button
                            type="button"
                            className="inline-flex items-center gap-2 text-sm font-semibold text-white transition hover:text-sky-300"
                            onClick={() => setCollapsedCustomVql((prev) => ({ ...prev, [ep.id]: !prev[ep.id] }))}
                          >
                            {collapsedCustomVql[ep.id] ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                            <span>Custom VQL Query</span>
                          </button>
                          {!collapsedCustomVql[ep.id] && (
                            <JsonTextarea
                              value={ep.vqlQuery || ""}
                              onChange={(e) => updateEndpointDraft(ep.id, "vqlQuery", e.target.value)}
                              className={`mt-4 ${endpointScriptTextAreaClass}`}
                              placeholder='read collection collection where field="value" limit 100'
                            />
                          )}
                        </div>
                      )}
                      {normalizeOperationType(ep.operationType) === "script" && (
                        <div className="rounded-xl border border-white/[0.08] bg-[#102c49] p-4">
                          <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-sky-300/80">Versa (.versa)</p>
                          <div className="mb-3 flex flex-wrap gap-2">
                            {MEDIA_STORAGE_SCRIPT_PRESETS.map((preset) => (
                              <button
                                key={preset.id}
                                type="button"
                                className="rounded border border-sky-300/25 bg-sky-500/10 px-2.5 py-1 text-xs font-medium text-sky-100 transition hover:bg-sky-500/20"
                                onClick={() => applyEndpointScriptPreset(ep.id, preset.id)}
                                title={preset.description}
                                disabled={!canManageServices}
                              >
                                {preset.label}
                              </button>
                            ))}
                          </div>
                          <Textarea
                            value={ep.versaScript || ""}
                            onChange={(e) => updateEndpointDraft(ep.id, "versaScript", e.target.value)}
                            className={endpointScriptTextAreaClass}
                            placeholder="json_xml import *;\nvdb import *;\n...\nreturn {ok: true};"
                          />
                        </div>
                      )}
                      <Textarea
                        value={ep.developerNotes || ""}
                        onChange={(e) => updateEndpointDraft(ep.id, "developerNotes", e.target.value)}
                        className={`min-h-[88px] ${editorTextAreaClass}`}
                        placeholder="Developer notes"
                      />
                      <div className="rounded-xl border border-white/[0.08] bg-[#102c49] p-4">
                        <p className="mb-4 text-xs font-semibold uppercase tracking-wider text-sky-300/80">Example Query Params</p>
                        <div className="space-y-3">
                          {(ep.queryPairs || []).map((pair) => (
                            <div key={pair.id} className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
                              <Input value={pair.key || ""} onChange={(e) => updateEndpointParamPair(ep.id, "query", pair.id, "key", e.target.value)} placeholder="Param key" className={`h-10 ${editorTextAreaClass}`} />
                              <Input value={pair.value || ""} onChange={(e) => updateEndpointParamPair(ep.id, "query", pair.id, "value", e.target.value)} placeholder="Param value" className={`h-10 ${editorTextAreaClass}`} />
                              <Button variant="outline" className="h-10 w-10 p-0 border-rose-300/25 bg-[#2a1730] text-rose-200 hover:bg-[#3a1d40]" onClick={() => removeEndpointParamPair(ep.id, "query", pair.id)} disabled={!canManageServices}>
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          ))}
                          <Button variant="outline" className="h-9 border-white/10 bg-[#12304d] text-sky-100 hover:bg-[#193d60]" onClick={() => addEndpointParamPair(ep.id, "query")} disabled={!canManageServices}>
                            <Plus className="mr-1 h-3.5 w-3.5" /> Add Query Param
                          </Button>
                        </div>
                      </div>
                      <div className="rounded-xl border border-white/[0.08] bg-[#102c49] p-4">
                        <p className="mb-4 text-xs font-semibold uppercase tracking-wider text-sky-300/80">Example Body Params</p>
                        <div className="space-y-3">
                          {(ep.bodyPairs || []).map((pair) => (
                            <div key={pair.id} className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
                              <Input value={pair.key || ""} onChange={(e) => updateEndpointParamPair(ep.id, "body", pair.id, "key", e.target.value)} placeholder="Body key" className={`h-10 ${editorTextAreaClass}`} />
                              <Input value={pair.value || ""} onChange={(e) => updateEndpointParamPair(ep.id, "body", pair.id, "value", e.target.value)} placeholder='Body value (supports JSON like {"x":1})' className={`h-10 ${editorTextAreaClass}`} />
                              <Button variant="outline" className="h-10 w-10 p-0 border-rose-300/25 bg-[#2a1730] text-rose-200 hover:bg-[#3a1d40]" onClick={() => removeEndpointParamPair(ep.id, "body", pair.id)} disabled={!canManageServices}>
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          ))}
                          <Button variant="outline" className="h-9 border-white/10 bg-[#12304d] text-sky-100 hover:bg-[#193d60]" onClick={() => addEndpointParamPair(ep.id, "body")} disabled={!canManageServices}>
                            <Plus className="mr-1 h-3.5 w-3.5" /> Add Body Param
                          </Button>
                        </div>
                      </div>
                      <Input
                        value={ep.exampleBearer || ""}
                        onChange={(e) => updateEndpointDraft(ep.id, "exampleBearer", e.target.value)}
                        className={`h-11 font-mono text-xs ${editorTextAreaClass}`}
                        placeholder="Example bearer token (without Bearer prefix)"
                      />
                    </div>
                  )}
                </div>
              ))}
              <div className="flex pt-2">
                <Button className="h-10 bg-sky-500 text-slate-950 hover:bg-sky-400" onClick={saveStructuredConfig} disabled={saving || !canManageServices}>
                  Save Endpoint Changes + Restart
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
      )}

      {activePanel === "modules" && (
      <Card className={`${editorCardClass} flex min-h-full flex-col`}>
        <CardHeader>
          <CardTitle className="text-xl text-white">Service VI Modules</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <SharedModuleConfig
            config={{ sharedModules: sharedModuleDrafts }}
            serviceDomain={String(service?.lapis_config?.metadata?.apiName || service?.apiName || "").trim().toLowerCase()}
            updateConfig={(_, __, ___, value) => setSharedModuleDrafts(normalizeSharedModules(value))}
          />
          <ModuleConfig
            config={{ modules: moduleDrafts }}
            availableModules={modulesCatalog}
            availableDomains={availableModuleDomains}
            loading={modulesLoading}
            refreshCatalog={loadModulesCatalog}
            onAttachModule={attachModuleToService}
            updateConfig={(_, __, ___, value) => setModuleDrafts(Array.isArray(value) ? value : [])}
          />
          <div className="flex pt-2">
            <Button className="h-10 bg-sky-500 text-slate-950 hover:bg-sky-400" onClick={saveStructuredConfig} disabled={saving || !canManageServices}>
              Save Modules + Restart
            </Button>
          </div>
        </CardContent>
      </Card>
      )}

      {activePanel === "testing" && (
      <Card className={`${editorCardClass} flex min-h-full flex-col`}>
        <CardHeader>
          <CardTitle className="text-xl text-white">Configured Routes & Auth Testing</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-4">
            {hasProtectedRoutes && (
              <div className="rounded-2xl border border-white/[0.08] bg-[#102c49] p-5">
                <p className="mb-2 text-sm font-bold text-sky-100">
                  {authIsAuthService ? "Auth Service Setup" : "Protected Route Authentication"}
                </p>
                <p className="mb-4 text-xs text-slate-300">
                  {authIsAuthService
                    ? "Use the reset super admin route to enforce the configured credentials, then authenticate and auto-fill Bearer tokens for protected routes."
                    : "Authenticate against the selected auth service. Bearer token is auto-filled into all protected routes and updates when you re-authenticate."}
                </p>
                {!authIsAuthService && (
                  <p className="mb-4 text-xs text-slate-300">
                    Selected auth service: <code className="text-sky-400">{authDependencyName || "Not configured"}</code>
                    {authDependencyService?.status ? ` (${authDependencyService.status})` : ""}
                  </p>
                )}
                {authProfileOptions.length > 0 && (
                  <div className="mb-4 space-y-2">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-sky-300/80">Authenticate Profile</p>
                    <select
                      value={authProfileChoice}
                      onChange={(e) => {
                        const selected = authProfileOptions.find((item) => item.username === e.target.value)
                        setAuthProfileChoice(e.target.value)
                        if (!selected) return
                        setAuthBootstrapCreds((prev) => ({
                          ...prev,
                          username: selected.username || prev.username,
                          email: selected.email || prev.email,
                          password: selected.password || prev.password,
                          role: selected.role || prev.role || "USER",
                        }))
                      }}
                      className={`h-11 w-full rounded-xl border-white/10 bg-[#091522] px-4 text-sm text-sky-100 ${editorTextAreaClass}`}
                    >
                      {authProfileOptions.map((profile) => (
                        <option key={profile.username} value={profile.username}>
                          {profile.username} ({profile.role || "USER"})
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                <div className="grid gap-4 md:grid-cols-2">
                  <Input
                    value={authBootstrapCreds.username}
                    onChange={(e) => setAuthBootstrapCreds((prev) => ({ ...prev, username: e.target.value }))}
                    className={`h-11 ${editorTextAreaClass}`}
                    placeholder="Super admin username"
                  />
                  <Input
                    value={authBootstrapCreds.email}
                    onChange={(e) => setAuthBootstrapCreds((prev) => ({ ...prev, email: e.target.value }))}
                    className={`h-11 ${editorTextAreaClass}`}
                    placeholder="Super admin email"
                  />
                  <PasswordInput
                    value={authBootstrapCreds.password}
                    onChange={(e) => setAuthBootstrapCreds((prev) => ({ ...prev, password: e.target.value }))}
                    className={`h-11 ${editorTextAreaClass}`}
                    placeholder="Super admin password"
                  />
                  <Input
                    value={authBootstrapCreds.role}
                    onChange={(e) => setAuthBootstrapCreds((prev) => ({ ...prev, role: e.target.value }))}
                    className={`h-11 ${editorTextAreaClass}`}
                    placeholder="Role"
                  />
                </div>
                <div className="mt-4 grid gap-4 md:grid-cols-[1fr_auto_auto] md:items-center">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-sky-300/80">Authenticate Route</p>
                    <p className="mt-1 text-xs font-mono text-slate-300">
                      <code>{authTargetSignInRoute}</code>
                      {!authEnabled ? " (auth disabled)" : ""}
                    </p>
                    <p className="mt-1 text-xs font-mono text-slate-300">
                      <code>{authTargetSignOutRoute}</code> (signout)
                    </p>
                  </div>
                  {authIsAuthService ? (
                    <Button variant="outline" className="h-10 border-white/10 bg-[#12304d] text-sky-100 hover:bg-[#193d60]" onClick={runResetSuperAdmin} disabled={setupRunning || !canManageServices}>
                      {setupRunning ? (
                        <span className="inline-flex items-center gap-2">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          <span>Resetting...</span>
                        </span>
                      ) : (
                        "Reset Super Admin"
                      )}
                    </Button>
                  ) : (
                    <div />
                  )}
                  <Button className="h-10 bg-sky-500 text-slate-950 hover:bg-sky-400" onClick={runAuthenticate} disabled={authenticating}>
                    {authenticating ? (
                      <span className="inline-flex items-center gap-2">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        <span>Authenticating...</span>
                      </span>
                    ) : (
                      "Authenticate"
                    )}
                  </Button>
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <Button variant="outline" className="h-10 border-rose-300/25 bg-[#2a1730] text-rose-200 hover:bg-[#3a1d40]" onClick={runSignOut} disabled={!authToken}>
                    Sign Out
                  </Button>
                  <div className="flex-1">
                    <Input
                      value={authToken}
                      onChange={(e) => setAuthToken(e.target.value)}
                      placeholder="Captured Bearer token (auto-applied to protected routes)"
                      className={`h-11 font-mono text-xs ${editorTextAreaClass}`}
                    />
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button className="h-10 bg-sky-500 text-slate-950 hover:bg-sky-400" onClick={() => saveTestingWorkspace()} disabled={saving || !canManageServices}>
                    {saving ? "Saving..." : "Save Testing Workspace"}
                  </Button>
                </div>
              </div>
            )}

            {mediaProviders.length > 0 && (
              <div className="rounded-2xl border border-sky-400/20 bg-[#102c49] p-5">
                <p className="mb-2 text-sm font-bold text-sky-100">Media Route Testing</p>
                <p className="text-xs leading-6 text-slate-300">
                  These provider routes are implemented in Versa scripts and are exercised here with JSON request bodies. Use {` `}
                  {(mediaCapabilities.inputModes || []).map((mode, index) => (
                    <span key={mode}>
                      <code className="text-sky-300">{mode}</code>
                      {index < (mediaCapabilities.inputModes || []).length - 1 ? ", " : ""}
                    </span>
                  ))}
                  {` `}instead of multipart uploads, then replace placeholder `service.env` values before trying live uploads.
                </p>
              </div>
            )}

            {endpointConfigs.length === 0 ? (
              <p className="text-sm text-slate-300">No routes configured.</p>
            ) : (
              endpointConfigs.map((route) => (
                <div key={route.id} className="min-w-0 rounded-2xl border border-white/[0.08] bg-[#102c49] p-5">
                  <div className="mb-3 flex flex-wrap items-center gap-2">
                    <span className="font-bold text-white">{route.method}</span>
                    <span className="font-mono text-xs text-sky-200">{route.path}</span>
                    <span className="text-xs text-sky-300/80">({route.operationType})</span>
                    {route.enabled === false && (
                      <Badge variant="outline" className="border-amber-300/30 bg-amber-500/10 text-amber-200">
                        disabled
                      </Badge>
                    )}
                    {route.requiresAuth && (
                      <Badge variant="outline" className="border-sky-500/30 bg-sky-500/5 text-sky-400">
                        requiresAuth
                      </Badge>
                    )}
                  </div>
                  {route.developerNotes && (
                    <p className="mb-4 text-xs text-slate-300">{route.developerNotes}</p>
                  )}
                  <div className="doc-grid grid items-stretch gap-4 xl:auto-rows-fr xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                    <div className="min-w-0 h-full rounded-xl border border-white/[0.08] bg-[#102c49] p-4">
                      <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-sky-300/80">Request</p>
                      <div className="space-y-4">
                        <JsonTextarea
                          value={routeDrafts[route.id]?.queryText || "{}"}
                          onChange={(e) => updateRouteDraft(route.id, "queryText", e.target.value)}
                          className={endpointRequestTextAreaClass + " " + editorTextAreaClass}
                          placeholder='{"_id":"u_1001"}'
                        />
                        <JsonTextarea
                          value={routeDrafts[route.id]?.bodyText || "{}"}
                          onChange={(e) => updateRouteDraft(route.id, "bodyText", e.target.value)}
                          className={endpointRequestTextAreaClass + " " + editorTextAreaClass}
                          placeholder='{"name":"Alex"}'
                        />
                        <div className="space-y-1.5">
                          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-300">
                            {route.requiresAuth ? "Bearer token" : "Bearer token (optional)"}
                          </p>
                          <Input
                            value={routeDrafts[route.id]?.bearerToken || ""}
                            onChange={(e) => updateRouteDraft(route.id, "bearerToken", e.target.value)}
                            placeholder={route.requiresAuth ? "Bearer token required for this route" : "Bearer token"}
                            className={`h-10 font-mono text-xs ${editorTextAreaClass}`}
                          />
                        </div>
                        <div className="flex items-center gap-2 pt-1">
                          <Button variant="outline" className="h-9 border-white/10 bg-[#12304d] text-sky-100 hover:bg-[#193d60]" onClick={() => populateRouteDefaults(route)}>
                            Defaults
                          </Button>
                          <Button className="h-9 flex-1 bg-sky-500 text-slate-950 hover:bg-sky-400" onClick={() => runRoute(route)} disabled={route.enabled === false || Boolean(routeDrafts[route.id]?.running)}>
                            {routeDrafts[route.id]?.running ? "Running..." : "Try Route"}
                          </Button>
                        </div>
                      </div>
                    </div>
                    <div className="response-box min-w-0 overflow-hidden rounded-xl border border-white/[0.08] bg-[#0d2138]">
                        <div className="flex h-full min-w-0 flex-col overflow-hidden rounded-xl bg-[#0d2138]">
                          <div className="flex items-center justify-between gap-2 border-b border-white/[0.08] px-3 pb-3 pt-3">
                          <p className="text-[10px] font-semibold uppercase tracking-wider text-sky-300/80">Response</p>
                            <CopyIconButton
                              text={String(routeDrafts[route.id]?.responseText || "")}
                              label="Copy route response"
                              successMessage="Response copied"
                              errorMessage="Failed to copy response"
                              className="h-7 w-7 border-white/10 bg-[#12304d] text-sky-200 hover:bg-[#193d60] hover:text-white"
                            />
                          </div>
                          {routeDrafts[route.id]?.responseToken ? (
                            <div className="mb-2 px-3 pt-3">
                              <div className="relative">
                                <Input
                                  value={routeDrafts[route.id]?.responseToken || ""}
                                  readOnly
                                  className={`h-8 pr-10 font-mono text-[10px] text-sky-300 ${editorTextAreaClass}`}
                                />
                                <CopyIconButton
                                  text={String(routeDrafts[route.id]?.responseToken || "")}
                                  label="Copy bearer token"
                                  successMessage="Bearer token copied"
                                  errorMessage="Failed to copy bearer token"
                                  className="absolute right-1.5 top-1/2 h-5 w-5 -translate-y-1/2 border-white/10 bg-[#12304d] text-sky-100 hover:bg-[#193d60] hover:text-white"
                                />
                              </div>
                            </div>
                          ) : null}
                        <div className="flex min-h-[220px] min-w-0 flex-1 overflow-hidden px-1 pb-1 pt-2">
                          <Textarea
                            ref={(node) => setResponseTextareaRef(route.id, node)}
                            value={routeDrafts[route.id]?.responseText || ""}
                            readOnly
                            rows={1}
                            className={endpointResponseTextAreaClass}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>
      )}

      {activePanel === "config" && (
      <Card className={`${editorCardClass} flex min-h-full flex-col`}>
        <CardHeader>
          <CardTitle className="text-xl text-white">Global Configuration Manager</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-white/[0.08] bg-[#102c49] p-5">
              <p className="text-xs font-semibold uppercase tracking-wider text-sky-300/80">Service & Security</p>
              <div className="mt-4 space-y-2">
                <p className="text-sm text-sky-100">Base path: <span className="font-bold">{basePath || "/"}</span></p>
                <p className="text-sm text-sky-100">Docs: <span className="font-bold">{docsEnabled ? "Enabled" : "Disabled"}</span></p>
                <p className="text-sm text-sky-100">Auth: <span className="font-bold">{authEnabled ? "Enabled" : "Disabled"}</span></p>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button variant="outline" className="h-8 border-white/10 bg-[#12304d] text-sky-100 hover:bg-[#193d60]" onClick={() => selectPanel("overview")}>Overview</Button>
                <Button variant="outline" className="h-8 border-white/10 bg-[#12304d] text-sky-100 hover:bg-[#193d60]" onClick={() => selectPanel("keys")}>Keys</Button>
                <Button variant="outline" className="h-8 border-white/10 bg-[#12304d] text-sky-100 hover:bg-[#193d60]" onClick={() => selectPanel("auth")}>Auth</Button>
              </div>
            </div>

            <div className="rounded-2xl border border-white/[0.08] bg-[#102c49] p-5">
              <p className="text-xs font-semibold uppercase tracking-wider text-sky-300/80">Models & Routes</p>
              <div className="mt-4 space-y-2">
                <p className="text-sm text-sky-100">Models: <span className="font-bold">{modelCount}</span></p>
                <p className="text-sm text-sky-100">Endpoints: <span className="font-bold">{endpointCount}</span></p>
                <p className="text-sm text-sky-100">Modules: <span className="font-bold">{moduleCount}</span></p>
                <p className="text-sm text-sky-100">Protected routes: <span className="font-bold">{protectedRouteCount}</span></p>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button variant="outline" className="h-8 border-white/10 bg-[#12304d] text-sky-100 hover:bg-[#193d60]" onClick={() => selectPanel("models")}>Models</Button>
                <Button variant="outline" className="h-8 border-white/10 bg-[#12304d] text-sky-100 hover:bg-[#193d60]" onClick={() => selectPanel("endpoints")}>Endpoints</Button>
                <Button variant="outline" className="h-8 border-white/10 bg-[#12304d] text-sky-100 hover:bg-[#193d60]" onClick={() => selectPanel("modules")}>VI Modules</Button>
                <Button variant="outline" className="h-8 border-white/10 bg-[#12304d] text-sky-100 hover:bg-[#193d60]" onClick={() => selectPanel("testing")}>Testing</Button>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-white/[0.08] bg-[#102c49] p-5">
            <p className="text-sm text-slate-300">
              Use structured mode to manage the service by section, or switch to text mode for the full LAPIS JSON. Structured changes require a restart to apply.
            </p>
            <div className="mt-5 flex flex-wrap gap-3">
              <Button className="h-10 bg-sky-500 text-slate-950 hover:bg-sky-400" onClick={saveStructuredConfig} disabled={saving || !canManageServices}>
                {saving ? "Saving..." : "Save Structured Changes + Restart"}
              </Button>
              <Button variant="outline" className="h-10 border-white/10 bg-[#12304d] text-sky-100 hover:bg-[#193d60]" onClick={fetchService}>
                Reload from Service
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
      )}
                    </div>
                  )}
                  </div>
                </div>
            </div>
          </div>
        </section>
            </ResizablePanel>
          </ResizablePanelGroup>
        </div>
      </div>

      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this service?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete <span className="font-semibold">{service?.apiName}</span>, stop its process,
              {deleteDataWithService ? " and remove its service data." : " and keep its service data."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
