// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

"use client"

import { useState, useEffect, useRef, useCallback, useMemo } from "react"
import { Play, Square, Trash2, AlertTriangle, Plus, Upload, X, RefreshCw, CheckCircle2, SlidersHorizontal, Pencil } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Progress } from "@/components/ui/progress"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { authHeaders } from "@/lib/auth"
import { fetchAuthedJson } from "@/lib/authed-json-cache"
import { validateLapisConfigRemote } from "@/lib/lapis-validation"
import { resolveServiceLinks } from "@/lib/service-links"
import { LapisUploadError } from "@/components/lapis/lapis-upload-error"
import { OperationStatusPanel } from "@/components/ui/operation-status-panel"
import { TransientSuccessDialog } from "@/components/ui/transient-success-dialog"
import { useOperationStatus } from "@/lib/operation-status"
import { isFeatureEnabled, usePlatformFeatureFlags } from "@/lib/platform-flags"
import {
  BUILDER_EDIT_REQUEST_KEY,
  BUILDER_EDIT_RESULT_KEY,
  SERVICES_UPLOADED_BATCH_STORAGE_KEY,
  readSessionJson,
  writeSessionJson,
} from "@/lib/uploaded-batch-storage"
import { activatePendingVerseAction, consumePendingVerseAction, executeVerseServerAction } from "@/lib/verse-actions"
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
import { toast } from "sonner"
import { Label } from "@/components/ui/label"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

export default function ServicesPage() {
  const router = useRouter()
  const baseConfig = {
    metadata: {
      apiName: "",
      basePath: "/api/v1",
      version: "1.0.0",
      database: "main",
      developerNotes: "",
      setupApiKey: "liwiroservicepass0!",
      documentation: { enabled: true, key: "liwiroservicepass0!" },
      seedData: { enabled: false, collections: {} },
      rateLimiting: { enabled: false, limit: 100, timeframe: "minute" },
    },
    auth: {
      enabled: false,
      useAsymmetricJWT: false,
      autoGenerateKeys: true,
      privateKey: "",
      publicKey: "",
      authModel: "",
      isAuthService: false,
      authServiceName: "",
      keyManagement: "auto",
      defaultSuperAdmin: { enabled: false, username: "superadmin", email: "superadmin@liwiro.local", password: "", role: "SUPER_ADMIN" },
      customEndpoints: { enabled: false, signIn: "/signin", signOut: "/signout", signUp: "/signup", register: "/register", forgotPassword: "/forgot-password", resetPassword: "/reset-password" },
      passwordResetPage: {
        enabled: true,
        submissionMode: "auto_form",
        customPageBaseUrl: "",
        title: "",
        description: "",
        submitLabel: "",
        loadingMessage: "",
        successMessage: "",
        failureMessage: "",
      },
    },
    models: {},
    endpoints: {},
  }

  const normalizeConfig = (incoming) => {
    const merged = {
      ...baseConfig,
      ...(incoming || {}),
      metadata: { ...baseConfig.metadata, ...((incoming || {}).metadata || {}) },
      auth: { ...baseConfig.auth, ...((incoming || {}).auth || {}) },
      models: { ...((incoming || {}).models || {}) },
      endpoints: { ...((incoming || {}).endpoints || {}) },
    }

    merged.metadata.documentation = {
      ...baseConfig.metadata.documentation,
      ...((merged.metadata || {}).documentation || {}),
    }
    merged.metadata.seedData = {
      ...baseConfig.metadata.seedData,
      ...((merged.metadata || {}).seedData || {}),
      collections: ((merged.metadata || {}).seedData || {}).collections || {},
    }
    merged.auth.defaultSuperAdmin = {
      ...baseConfig.auth.defaultSuperAdmin,
      ...((merged.auth || {}).defaultSuperAdmin || {}),
    }
    merged.auth.passwordResetPage = {
      ...baseConfig.auth.passwordResetPage,
      ...((merged.auth || {}).passwordResetPage || {}),
    }
    merged.auth.customEndpoints = {
      ...baseConfig.auth.customEndpoints,
      ...((merged.auth || {}).customEndpoints || {}),
    }

    return merged
  }

  const sanitizeForSubmit = (incomingConfig) => ({
    ...incomingConfig,
    metadata: {
      ...baseConfig.metadata,
      ...(incomingConfig.metadata || {}),
      documentation: {
        ...baseConfig.metadata.documentation,
        ...((incomingConfig.metadata || {}).documentation || {}),
      },
      seedData: {
        ...baseConfig.metadata.seedData,
        ...((incomingConfig.metadata || {}).seedData || {}),
        collections: (((incomingConfig.metadata || {}).seedData || {}).collections) || {},
      },
    },
    auth: {
      ...baseConfig.auth,
      ...(incomingConfig.auth || {}),
      defaultSuperAdmin: {
        ...baseConfig.auth.defaultSuperAdmin,
        ...((incomingConfig.auth || {}).defaultSuperAdmin || {}),
      },
      passwordResetPage: {
        ...baseConfig.auth.passwordResetPage,
        ...((incomingConfig.auth || {}).passwordResetPage || {}),
      },
      customEndpoints: {
        ...baseConfig.auth.customEndpoints,
        ...((incomingConfig.auth || {}).customEndpoints || {}),
      },
    },
  })

  const configHasVersaScriptEndpoints = (candidateConfig = {}) => Object.values(candidateConfig?.endpoints || {}).some(
    (endpoint) => String(endpoint?.operationType || "").trim().toLowerCase() === "script" && String(endpoint?.versaScript || "").trim()
  )

  const validateConfigWithBackend = async (candidateConfig) => {
    const normalizedCandidate = sanitizeForSubmit(normalizeConfig(candidateConfig))
    const result = await validateLapisConfigRemote(LIWIRO_BACKEND, normalizedCandidate)
    return {
      ...result,
      normalized: result?.normalized && typeof result.normalized === "object" ? normalizeConfig(result.normalized) : normalizedCandidate,
    }
  }

  const bestLapisIssueMessage = useCallback((result, fallback = "") => {
    const issueMessage = (Array.isArray(result?.issues) ? result.issues : [])
      .map((item) => String(item?.message || item?.error || "").trim())
      .find(Boolean)
    return String(result?.error || issueMessage || fallback || "").trim()
  }, [])

  const createItemId = () => {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID()
    }
    return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  }

  const [services, setServices] = useState([])
  const [canManageServices, setCanManageServices] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [serviceToDelete, setServiceToDelete] = useState(null)
  const [deleteAllDialogOpen, setDeleteAllDialogOpen] = useState(false)
  const [deleteSelectedDialogOpen, setDeleteSelectedDialogOpen] = useState(false)
  const [deletingServiceIds, setDeletingServiceIds] = useState([])
  const [deletingAll, setDeletingAll] = useState(false)
  const [deletingSelected, setDeletingSelected] = useState(false)
  const [loading, setLoading] = useState(true)
  const [bulkAction, setBulkAction] = useState(null)
  const [selectedServiceIds, setSelectedServiceIds] = useState([])
  const [alsoDeleteData, setAlsoDeleteData] = useState(true)
  const [startServicesAfterGeneration, setStartServicesAfterGeneration] = useState(true)
  const [retryFailedBatchOps, setRetryFailedBatchOps] = useState(true)
  const [batchConfigs, setBatchConfigs] = useState([])
  const [batchGenerating, setBatchGenerating] = useState(false)
  const [authSelectionDialogOpen, setAuthSelectionDialogOpen] = useState(false)
  const [authSelectionOptions, setAuthSelectionOptions] = useState([])
  const [authSelectionChoice, setAuthSelectionChoice] = useState("")
  const [authSelectionApplyAll, setAuthSelectionApplyAll] = useState(true)
  const [authSelectionResolver, setAuthSelectionResolver] = useState(null)
  const [batchProgress, setBatchProgress] = useState(null)
  const {
    status: uploadOperationStatus,
    startOperation: startUploadOperation,
    updateOperation: updateUploadOperation,
    succeedOperation: succeedUploadOperation,
    failOperation: failUploadOperation,
    clearStatus: clearUploadOperation,
  } = useOperationStatus({ autoHideSuccessMs: 2200 })
  const fileInputRef = useRef(null)
  const progressHideTimerRef = useRef(null)
  const [batchStorageReady, setBatchStorageReady] = useState(false)

  const LIWIRO_BACKEND = process.env.NEXT_PUBLIC_LIWIRO_BACKEND || "http://127.0.0.1:5000"
  const LIWIRO_HOST = process.env.NEXT_PUBLIC_LIWIRO_HOST || "http://127.0.0.1"
  const { featureFlags } = usePlatformFeatureFlags(LIWIRO_BACKEND)
  const uploadProgressEnabled = isFeatureEnabled(featureFlags, "unifiedOperationStatus", true)
    && isFeatureEnabled(featureFlags, "serviceBatchProgressMessages", true)
  const uploadSuccessModalEnabled = isFeatureEnabled(featureFlags, "transientSuccessFeedback", true)
  const prepareConfigForBatchWorkflow = useCallback(async (candidateConfig) => {
    const normalizedCandidate = sanitizeForSubmit(normalizeConfig(candidateConfig))
    const result = await validateLapisConfigRemote(LIWIRO_BACKEND, normalizedCandidate)
    return {
      ...result,
      normalized: result?.normalized && typeof result.normalized === "object" ? normalizeConfig(result.normalized) : normalizedCandidate,
    }
  // normalizeConfig/sanitizeForSubmit are stable module helpers.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [LIWIRO_BACKEND])

  const applyServiceList = useCallback((nextServices) => {
    setServices(nextServices)
    setSelectedServiceIds((prev) => prev.filter((id) => nextServices.some((svc) => String(svc.processId) === String(id))))
  }, [])

  const loadPermissions = useCallback(async () => {
    try {
      const [meRes, settingsRes] = await Promise.allSettled([
        fetchAuthedJson(`${LIWIRO_BACKEND}/auth/me`, { ttlMs: 2500 }),
        fetchAuthedJson(`${LIWIRO_BACKEND}/platform/settings`, { ttlMs: 2500 }),
      ])
      if (meRes.status === "rejected" && Number(meRes.reason?.status || 0) === 401) {
        window.location.href = "/login"
        return
      }
      if (settingsRes.status === "rejected" && Number(settingsRes.reason?.status || 0) === 401) {
        window.location.href = "/login"
        return
      }
      if (meRes.status === "fulfilled") {
        const perms = Array.isArray(meRes.value?.permissions) ? meRes.value.permissions : []
        setCanManageServices(perms.includes("MANAGE_SERVICES"))
      }
      if (settingsRes.status === "fulfilled") {
        const settings = settingsRes.value || {}
        setAlsoDeleteData(Boolean(settings?.deleteDataWithServiceByDefault))
        setStartServicesAfterGeneration(Boolean(settings?.startServicesAfterGenerationByDefault))
        setRetryFailedBatchOps(Boolean(settings?.retryFailedBatchOpsByDefault))
      }
    } catch {
      setCanManageServices(false)
    }
  }, [LIWIRO_BACKEND])

  const fetchServices = useCallback(async ({ refreshRuntime = true, showLoading = true } = {}) => {
    if (showLoading) {
      setLoading(true)
    }
    try {
      const url = new URL(`${LIWIRO_BACKEND}/services`)
      url.searchParams.set("summary", "1")
      url.searchParams.set("refresh", refreshRuntime ? "1" : "0")
      const response = await fetch(url.toString(), {
        headers: authHeaders(),
      })
      if (response.status === 401) {
        window.location.href = "/login"
        return null
      }
      const data = await response.json()
      const nextServices = Array.isArray(data) ? data : []
      applyServiceList(nextServices)
      return nextServices
    } catch (error) {
      console.error("Error fetching services:", error)
      toast.error("Failed to load services")
      return null
    } finally {
      if (showLoading) {
        setLoading(false)
      }
    }
  }, [LIWIRO_BACKEND, applyServiceList])

  useEffect(() => {
    loadPermissions()
    let cancelled = false

    const hydrateServices = async () => {
      const initialServices = await fetchServices({ refreshRuntime: false, showLoading: true })
      if (cancelled || initialServices === null) return
      void fetchServices({ refreshRuntime: true, showLoading: false })
    }

    hydrateServices()

    return () => {
      cancelled = true
    }
  }, [loadPermissions, fetchServices])

  useEffect(() => {
    if (typeof window === "undefined") return
    try {
      const storedBatch = readSessionJson(SERVICES_UPLOADED_BATCH_STORAGE_KEY)
      if (Array.isArray(storedBatch)) {
        setBatchConfigs(storedBatch)
      }
      const parsedResult = readSessionJson(BUILDER_EDIT_RESULT_KEY)
      if (parsedResult && (!parsedResult?.source || parsedResult?.source === "services-uploaded-list")) {
        if (parsedResult?.saved) toast.success("Uploaded service config updated")
        if (parsedResult?.cancelled) toast.message("Uploaded service edit cancelled")
        window.sessionStorage.removeItem(BUILDER_EDIT_RESULT_KEY)
      }
    } catch {
      // Ignore malformed state in session storage.
    } finally {
      setBatchStorageReady(true)
    }
  }, [])

  useEffect(() => {
    if (typeof window === "undefined") return
    if (!batchStorageReady) return
    writeSessionJson(SERVICES_UPLOADED_BATCH_STORAGE_KEY, batchConfigs)
  }, [batchConfigs, batchStorageReady])

  useEffect(() => {
    if (typeof window === "undefined") return

    const resolveVerseService = (artifact) => {
      const serviceAction = artifact?.serviceAction && typeof artifact.serviceAction === "object" ? artifact.serviceAction : {}
      const processId = String(serviceAction?.processId || "").trim()
      const serviceName = String(serviceAction?.serviceName || "").trim().toLowerCase()
      return services.find((service) => {
        const nextProcessId = String(service?.processId || "").trim()
        const nextApiName = String(service?.apiName || "").trim().toLowerCase()
        if (processId && nextProcessId === processId) return true
        if (serviceName && nextApiName === serviceName) return true
        return false
      }) || null
    }

    const handleVerseContextRequest = (event) => {
      const respond = event?.detail?.respond
      if (typeof respond !== "function") return
      const selectedSet = new Set(selectedServiceIds.map((id) => String(id)))
      const selectedServices = services.filter((service) => selectedSet.has(String(service?.processId || "")))
      const primarySelected = selectedServices[0] || null
      const selectedLabel = String(primarySelected?.apiName || primarySelected?.processId || "Current service selection").trim() || "Current service selection"
      respond({
        pageKind: "service-manager",
        screen: "service manager",
        pathname: "/services",
        selectedServiceId: primarySelected?.processId || "",
        selectedServiceName: primarySelected?.apiName || "",
        services: services.slice(0, 50).map((service) => ({
          processId: String(service?.processId || ""),
          apiName: String(service?.apiName || ""),
          status: String(service?.status || ""),
          basePath: String(service?.basePath || ""),
          port: service?.port ?? null,
          docsEnabled: service?.docsEnabled !== false,
        })),
        selectedService: primarySelected
          ? {
              processId: String(primarySelected.processId || ""),
              apiName: String(primarySelected.apiName || ""),
              status: String(primarySelected.status || ""),
            }
          : null,
        focus: {
          kind: "service-manager-action",
          label: selectedLabel,
          identifier: String(primarySelected?.processId || "").trim(),
          contentSummary: primarySelected
            ? `${selectedLabel} is currently ${String(primarySelected?.status || "unknown").trim() || "unknown"}`
            : "Current service selection in Service Manager",
          contentPreview: primarySelected ? JSON.stringify({
            processId: String(primarySelected.processId || ""),
            apiName: String(primarySelected.apiName || ""),
            status: String(primarySelected.status || ""),
            basePath: String(primarySelected.basePath || ""),
            port: primarySelected.port ?? null,
          }, null, 2) : "",
        },
        relevanceHints: {
          focusPreferred: Boolean(primarySelected),
          selectedServiceCount: selectedServices.length,
        },
        serviceRoster: services.slice(0, 20).map((service) => ({
          processId: String(service?.processId || ""),
          apiName: String(service?.apiName || ""),
          status: String(service?.status || ""),
        })),
      })
    }

    const handleVerseApply = (event) => {
      const artifact = event?.detail?.artifact
      const respond = event?.detail?.respond
      if (artifact?.kind !== "service-manager-action" || typeof respond !== "function") return
      const resolvedService = resolveVerseService(artifact)
      if (!resolvedService) {
        respond({ ok: false, message: "That service is not visible in the Service Manager right now." })
        return
      }
      setSelectedServiceIds([String(resolvedService.processId || "")])
      respond({ ok: true, message: `Focused ${resolvedService.apiName || resolvedService.processId} in Service Manager.` })
    }

    const handleVerseExecute = (event) => {
      const artifact = event?.detail?.artifact
      const respond = event?.detail?.respond
      if (artifact?.kind !== "service-manager-action" || typeof respond !== "function") return
      executeVerseServerAction({
        backend: LIWIRO_BACKEND,
        artifact,
        context: { pathname: "/services", pageKind: "service-manager" },
      })
        .then(async (result) => {
          if (!result?.ok) {
            respond({ ok: false, message: result?.message || "Verse could not complete the service action." })
            return
          }
          await fetchServices({ refreshRuntime: true, showLoading: false })
          const nextProcessId = String(result?.payload?.service?.processId || artifact?.serviceAction?.processId || "").trim()
          if (nextProcessId) {
            setSelectedServiceIds([nextProcessId])
          }
          respond({ ok: true, message: result?.message || "Verse completed the service action." })
        })
        .catch((error) => {
          respond({ ok: false, message: error?.message || "Verse could not complete the service action." })
        })
    }

    window.addEventListener("liwiro:verse-assistant-request-context", handleVerseContextRequest)
    window.addEventListener("liwiro:verse-assistant-apply", handleVerseApply)
    window.addEventListener("liwiro:verse-assistant-execute", handleVerseExecute)

    const pendingAction = consumePendingVerseAction("/services")
    if (pendingAction?.artifact) {
      activatePendingVerseAction({
        pathname: "/services",
        pendingAction,
        onResult: (payload) => {
          if (payload?.ok) toast.success(payload.message || "Verse action completed.")
          else toast.error(payload?.message || "Verse action failed.")
        },
      })
    }

    return () => {
      window.removeEventListener("liwiro:verse-assistant-request-context", handleVerseContextRequest)
      window.removeEventListener("liwiro:verse-assistant-apply", handleVerseApply)
      window.removeEventListener("liwiro:verse-assistant-execute", handleVerseExecute)
    }
  }, [LIWIRO_BACKEND, fetchServices, selectedServiceIds, services])

  useEffect(() => () => {
    if (progressHideTimerRef.current) {
      clearTimeout(progressHideTimerRef.current)
    }
  }, [])

  const deleteServiceUrl = (processId) => {
    const url = new URL(`${LIWIRO_BACKEND}/services/${processId}/delete`)
    if (alsoDeleteData) {
      url.searchParams.set("deleteData", "true")
    }
    return url.toString()
  }

  const beginBatchProgress = (kind, total) => {
    if (progressHideTimerRef.current) {
      clearTimeout(progressHideTimerRef.current)
      progressHideTimerRef.current = null
    }
    setBatchProgress({
      kind,
      total,
      completed: 0,
      succeeded: 0,
      failed: 0,
      current: "",
      done: false,
    })
  }

  const updateBatchProgress = (patch) => {
    setBatchProgress((prev) => (prev ? { ...prev, ...patch } : prev))
  }

  const finishBatchProgress = () => {
    setBatchProgress((prev) => (prev ? { ...prev, done: true, current: "" } : prev))
    if (progressHideTimerRef.current) {
      clearTimeout(progressHideTimerRef.current)
    }
    progressHideTimerRef.current = setTimeout(() => {
      setBatchProgress(null)
      progressHideTimerRef.current = null
    }, 900)
  }

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

  const runServiceActionWithRetry = async (service, action, retries = (retryFailedBatchOps ? 1 : 0)) => {
    let attempt = 0
    let lastError = null
    while (attempt <= retries) {
      try {
        const response = await fetch(`${LIWIRO_BACKEND}/services/${service.processId}/${action}`, {
          method: "POST",
          headers: authHeaders(),
        })
        const data = await response.json().catch(() => ({}))
        if (!response.ok) {
          throw new Error(data.error || data.message || `Failed to ${action} ${service.apiName || service.processId}`)
        }
        return { ok: true, data }
      } catch (error) {
        lastError = error
        if (attempt < retries) await sleep(300)
      }
      attempt += 1
    }
    return { ok: false, error: lastError || new Error(`Failed to ${action} ${service.apiName || service.processId}`) }
  }

  const deleteOneServiceWithRetry = async (service, retries = (retryFailedBatchOps ? 1 : 0)) => {
    let attempt = 0
    let lastError = null
    while (attempt <= retries) {
      try {
        const response = await fetch(deleteServiceUrl(service.processId), {
          method: "DELETE",
          headers: authHeaders(),
        })
        const data = await response.json().catch(() => ({}))
        if (!response.ok) {
          throw new Error(data.error || data.message || `Failed to delete ${service.apiName}`)
        }
        return { ok: true, data }
      } catch (error) {
        lastError = error
        if (attempt < retries) await sleep(300)
      }
      attempt += 1
    }
    return { ok: false, error: lastError || new Error(`Failed to delete ${service.apiName}`) }
  }

  const toggleSelectService = (processId, checked) => {
    const id = String(processId)
    setSelectedServiceIds((prev) => {
      const set = new Set(prev.map(String))
      if (checked) set.add(id)
      else set.delete(id)
      return Array.from(set)
    })
  }

  const toggleSelectAllServices = (checked) => {
    if (!checked) {
      setSelectedServiceIds([])
      return
    }
    setSelectedServiceIds(sortedServices.map((svc) => String(svc.processId)))
  }

  const handleStartService = async (id) => {
    try {
      const response = await fetch(`${LIWIRO_BACKEND}/services/${id}/start`, {
        method: "POST",
        headers: authHeaders(),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || "Failed to start service")
      toast.success(data.message || "Service started")
      fetchServices()
    } catch (error) {
      console.error("Error starting service:", error)
      toast.error(error?.message || "Error starting service")
    }
  }

  const handleStopService = async (id) => {
    try {
      const response = await fetch(`${LIWIRO_BACKEND}/services/${id}/stop`, {
        method: "POST",
        headers: authHeaders(),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || "Failed to stop service")
      toast.success(data.message || "Service stopped")
      fetchServices()
    } catch (error) {
      console.error("Error stopping service:", error)
      toast.error(error?.message || "Error stopping service")
    }
  }

  const handleBulkServiceAction = async (action) => {
    const targetStatus = action === "start" ? "NOT_RUNNING" : "RUNNING"
    const targetServices = services.filter((service) => service.status === targetStatus)
    if (targetServices.length === 0) {
      toast.message(action === "start" ? "All services are already running" : "All services are already stopped")
      return
    }

    setBulkAction(action)
    beginBatchProgress(`${action}-all`, targetServices.length)
    try {
      let succeeded = 0
      let failed = 0
      for (let index = 0; index < targetServices.length; index += 1) {
        const service = targetServices[index]
        updateBatchProgress({ current: service.apiName || String(service.processId) })
        const result = await runServiceActionWithRetry(service, action)
        if (result.ok) {
          succeeded += 1
        } else {
          failed += 1
        }
        updateBatchProgress({
          completed: index + 1,
          succeeded,
          failed,
        })
      }

      if (succeeded > 0) {
        toast.success(`${action === "start" ? "Started" : "Stopped"} ${succeeded} service${succeeded > 1 ? "s" : ""}`)
      }
      if (failed > 0) {
        toast.error(`${failed} service${failed > 1 ? "s" : ""} failed to ${action}`)
      }
      fetchServices()
    } catch (error) {
      console.error(`Error during ${action}-all:`, error)
      toast.error(error?.message || `Error trying to ${action} all services`)
    } finally {
      finishBatchProgress()
      setBulkAction(null)
    }
  }

  const handleSelectedServiceAction = async (action) => {
    if (selectedServiceIds.length === 0) {
      toast.message(`No services selected to ${action}`)
      return
    }
    const selectedSet = new Set(selectedServiceIds.map(String))
    const targetServices = services.filter((service) => selectedSet.has(String(service.processId)))
    setBulkAction(`${action}-selected`)
    beginBatchProgress(`${action}-selected`, targetServices.length)
    try {
      let succeeded = 0
      let failed = 0
      for (let index = 0; index < targetServices.length; index += 1) {
        const service = targetServices[index]
        updateBatchProgress({ current: service.apiName || String(service.processId) })
        const result = await runServiceActionWithRetry(service, action)
        if (result.ok) {
          succeeded += 1
        } else {
          failed += 1
        }
        updateBatchProgress({
          completed: index + 1,
          succeeded,
          failed,
        })
      }
      if (succeeded > 0) toast.success(`${action === "start" ? "Started" : "Stopped"} ${succeeded} selected service${succeeded > 1 ? "s" : ""}`)
      if (failed > 0) toast.error(`${failed} selected service${failed > 1 ? "s" : ""} failed to ${action}`)
      fetchServices()
    } catch (error) {
      toast.error(error?.message || `Failed to ${action} selected services`)
    } finally {
      finishBatchProgress()
      setBulkAction(null)
    }
  }

  const normalizeBatchError = (rawMessage) => {
    const message = String(rawMessage || "").trim()
    if (!message) return "Failed to generate service"
    const authDependencyText = "Auth-dependent service cannot be created before an authentication service is running."
    if (message.includes(authDependencyText)) {
      return "This LAPIS config depends on an authentication service. Create and start an auth service first, then retry."
    }
    return message
  }

  const generateServiceFromConfig = async (rawConfig) => {
    const normalizedConfig = normalizeConfig(rawConfig)
    let payload = sanitizeForSubmit(normalizedConfig)
    const validation = await prepareConfigForBatchWorkflow(normalizedConfig)
    if (!validation?.ok) {
      throw new Error(bestLapisIssueMessage(validation, "LAPIS validation is invalid. Service generation is blocked until it is fixed."))
    }
    payload = sanitizeForSubmit(normalizeConfig(validation?.normalized || normalizedConfig))
    const serviceName = String(payload?.metadata?.apiName || "").trim()
    if (!serviceName) {
      throw new Error("Service name is required")
    }

    const response = await fetch(`${LIWIRO_BACKEND}/generate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
      },
      body: JSON.stringify(payload),
    })
    if (response.status === 401) {
      window.location.href = "/login"
      return
    }
    const text = await response.text()
    let data = {}
    try {
      data = text ? JSON.parse(text) : {}
    } catch {
      data = {}
    }
    if (!response.ok) {
      throw new Error(normalizeBatchError(data?.error || data?.message || text || "Failed to generate service"))
    }
    return data
  }

  const chooseAuthServiceWithPrompt = async (authServices) => {
    if (!Array.isArray(authServices) || authServices.length === 0) return null
    if (authServices.length === 1) {
      return { selected: authServices[0], applyAll: true }
    }
    const defaultChoice = String(authServices[0]?.apiName || "")
    return new Promise((resolve) => {
      setAuthSelectionOptions(authServices)
      setAuthSelectionChoice(defaultChoice)
      setAuthSelectionApplyAll(true)
      setAuthSelectionResolver(() => resolve)
      setAuthSelectionDialogOpen(true)
    })
  }

  const resolveAuthSelectionDialog = (result) => {
    if (typeof authSelectionResolver === "function") {
      authSelectionResolver(result)
    }
    setAuthSelectionResolver(null)
    setAuthSelectionDialogOpen(false)
  }

  const handleLapisUpload = async (event) => {
    const files = Array.from(event.target.files || [])
    if (files.length === 0) return

    const loaded = []
    let readyCount = 0
    let repairedCount = 0
    let manualFixCount = 0
    let invalidCount = 0

    if (uploadProgressEnabled) {
      startUploadOperation({
        title: "Uploading LAPIS batch",
        label: `Preparing ${files.length} file${files.length === 1 ? "" : "s"}`,
        detail: "Reading and validating each file.",
        total: files.length,
        completed: 0,
        succeeded: 0,
        failed: 0,
      })
    }

    for (let index = 0; index < files.length; index += 1) {
      const file = files[index]
      try {
        if (uploadProgressEnabled) {
          updateUploadOperation({ current: file.name, detail: `Processing ${file.name}` })
        }
        const text = await file.text()
        const parsed = JSON.parse(text)
        const normalized = normalizeConfig(parsed)
        const apiName = String(normalized?.metadata?.apiName || "").trim() || file.name
        const validation = await prepareConfigForBatchWorkflow(normalized)
        const queuedConfig = normalizeConfig(validation?.normalized || normalized)
        const ready = Boolean(validation?.ok || validation?.finalStatus === "ready")
        const status = ready ? "ready" : (String(validation?.finalStatus || "").trim() || "needs-manual-fix")
        const error = ready ? "" : bestLapisIssueMessage(validation, "LAPIS validation is invalid.")
        loaded.push({
          id: createItemId(),
          fileName: file.name,
          apiName,
          config: queuedConfig,
          status,
          error,
          issues: Array.isArray(validation?.issues) ? validation.issues : [],
          appliedFixes: Array.isArray(validation?.appliedFixes) ? validation.appliedFixes : [],
          repairAttempts: Array.isArray(validation?.repairAttempts) ? validation.repairAttempts : [],
          attemptCount: Number(validation?.attemptCount || 0),
          progressMessage: String(validation?.progressMessage || "").trim(),
          repaired: Boolean(validation?.repaired),
        })
        if (ready) {
          readyCount += 1
          if (validation?.repaired) repairedCount += 1
        } else if (queuedConfig) {
          manualFixCount += 1
        } else {
          invalidCount += 1
        }
      } catch (error) {
        const message = String(error?.message || "").trim()
        loaded.push({
          id: createItemId(),
          fileName: file.name,
          apiName: file.name,
          config: null,
          status: "invalid",
          error: message && !/unexpected token|json/i.test(message) ? message : "Invalid JSON",
        })
        invalidCount += 1
      } finally {
        if (uploadProgressEnabled) {
          updateUploadOperation({
            completed: index + 1,
            succeeded: readyCount,
            failed: manualFixCount + invalidCount,
            current: file.name,
          })
        }
      }
    }

    setBatchConfigs((prev) => [...prev, ...loaded])

    if (readyCount > 0) {
      toast.success(
        repairedCount > 0
          ? `${readyCount} LAPIS file${readyCount > 1 ? "s" : ""} ready, ${repairedCount} auto-repaired`
          : `${readyCount} LAPIS file${readyCount > 1 ? "s" : ""} queued`,
      )
    }
    if (manualFixCount > 0) {
      toast.error(`${manualFixCount} LAPIS file${manualFixCount > 1 ? "s still need" : " still needs"} manual fixes`)
    }
    if (invalidCount > 0) {
      toast.error(`${invalidCount} invalid file${invalidCount > 1 ? "s" : ""} skipped`)
    }
    if (uploadProgressEnabled) {
      if (readyCount > 0) {
        succeedUploadOperation({
          title: "LAPIS batch ready",
          detail:
            `${readyCount} file${readyCount === 1 ? "" : "s"} are ready for generation.`,
          presentation: uploadSuccessModalEnabled ? "modal" : "inline",
          total: files.length,
          completed: files.length,
          succeeded: readyCount,
          failed: manualFixCount + invalidCount,
        })
      } else {
        failUploadOperation({
          title: "LAPIS batch needs attention",
          detail: "No uploaded files reached ready state. Review the reported errors and retry.",
          total: files.length,
          completed: files.length,
          succeeded: 0,
          failed: manualFixCount + invalidCount,
        })
      }
    }
    event.target.value = ""
  }

  const runBatchGenerate = async () => {
    const readyItems = batchConfigs.filter((item) => item.status === "ready" && item.config)
    if (readyItems.length === 0) {
      toast.error("No valid LAPIS files ready for generation")
      return
    }

    setBatchGenerating(true)
    beginBatchProgress("generate", readyItems.length)
    setBatchConfigs((prev) => prev.map((item) => (
      item.status === "ready" ? { ...item, status: "pending", error: "" } : item
    )))

    let successCount = 0
    let failCount = 0
    let singleGeneratedProcessId = ""
    const servicesResponse = await fetch(`${LIWIRO_BACKEND}/services`, { headers: authHeaders() }).catch(() => null)
    const existingServices = servicesResponse?.ok ? await servicesResponse.json().catch(() => []) : []
    const existingNames = new Set(
      (Array.isArray(existingServices) ? existingServices : []).map((svc) => String(svc?.apiName || "").trim().toLowerCase()).filter(Boolean),
    )
    const availableServices = Array.isArray(existingServices) ? [...existingServices] : []
    const availableAuthServices = availableServices.filter(
      (svc) => Boolean(svc?.lapis_config?.auth?.isAuthService),
    )
    let sharedAuthChoice = null

    for (let index = 0; index < readyItems.length; index += 1) {
      const item = readyItems[index]
      updateBatchProgress({ current: item.apiName || item.fileName || "LAPIS config" })
      setBatchConfigs((prev) => prev.map((entry) => (
        entry.id === item.id ? { ...entry, status: "running", error: "" } : entry
      )))
      try {
        const clonedConfig = JSON.parse(JSON.stringify(item.config || {}))
        const serviceName = String(clonedConfig?.metadata?.apiName || "").trim()
        if (!serviceName) {
          throw new Error("Service name is required")
        }
        if (existingNames.has(serviceName.toLowerCase())) {
          throw new Error(`Error: Service name '${serviceName}' already exists. Use a unique name.`)
        }

        const authCfg = clonedConfig?.auth || {}
        const hasProtectedRoutes = Object.values(clonedConfig?.endpoints || {}).some((ep) => Boolean(ep?.requiresAuth))
        const explicitAuthConsumer = Boolean(authCfg?.enabled) && Boolean(authCfg?.useAsymmetricJWT) && !Boolean(authCfg?.isAuthService)
        const needsExternalAuth = (hasProtectedRoutes && !Boolean(authCfg?.isAuthService)) || explicitAuthConsumer
        if (needsExternalAuth) {
          clonedConfig.auth = {
            ...(clonedConfig.auth || {}),
            enabled: true,
            useAsymmetricJWT: true,
            keyManagement: String(clonedConfig?.auth?.keyManagement || "").trim() || "auto",
          }
          if (availableAuthServices.length === 0) {
            throw new Error("No authentication service exists. Create an authentication service first.")
          }
          const configuredName = String(clonedConfig?.auth?.authServiceName || "").trim()
          if (configuredName) {
            const selectedByName = availableAuthServices.find(
              (svc) => String(svc?.apiName || "").trim().toLowerCase() === configuredName.toLowerCase(),
            )
            if (!selectedByName) {
              throw new Error(`Configured authentication service '${configuredName}' was not found. Select a valid authentication service.`)
            }
            clonedConfig.auth = {
              ...(clonedConfig.auth || {}),
              authServiceName: String(selectedByName.apiName || ""),
            }
            const selectedAuthCfg = selectedByName?.lapis_config?.auth || {}
            const selectedPublicKey = String(selectedAuthCfg?.publicKey || selectedAuthCfg?.authServicePublicKey || "").trim()
            if (selectedPublicKey && !String(clonedConfig?.auth?.authServicePublicKey || "").trim()) {
              clonedConfig.auth.authServicePublicKey = selectedPublicKey
            }
          } else if (!sharedAuthChoice) {
            const selected = await chooseAuthServiceWithPrompt(availableAuthServices)
            if (!selected?.selected?.apiName) {
              throw new Error("Authentication service selection is required for this LAPIS config.")
            }
            if (selected.applyAll) {
              sharedAuthChoice = selected.selected
            }
            clonedConfig.auth = {
              ...(clonedConfig.auth || {}),
              authServiceName: String(selected.selected.apiName),
            }
            const selectedAuthCfg = selected.selected?.lapis_config?.auth || {}
            const selectedPublicKey = String(selectedAuthCfg?.publicKey || selectedAuthCfg?.authServicePublicKey || "").trim()
            if (selectedPublicKey && !String(clonedConfig?.auth?.authServicePublicKey || "").trim()) {
              clonedConfig.auth.authServicePublicKey = selectedPublicKey
            }
          } else {
            clonedConfig.auth = {
              ...(clonedConfig.auth || {}),
              authServiceName: String(sharedAuthChoice.apiName || ""),
            }
            const selectedAuthCfg = sharedAuthChoice?.lapis_config?.auth || {}
            const selectedPublicKey = String(selectedAuthCfg?.publicKey || selectedAuthCfg?.authServicePublicKey || "").trim()
            if (selectedPublicKey && !String(clonedConfig?.auth?.authServicePublicKey || "").trim()) {
              clonedConfig.auth.authServicePublicKey = selectedPublicKey
            }
          }
        }

        const generated = await generateServiceFromConfig(clonedConfig)
        const generatedProcessId = String(generated?.process_id || generated?.processId || "").trim()
        if (!singleGeneratedProcessId && generatedProcessId) {
          singleGeneratedProcessId = generatedProcessId
        }
        let finalStatus = "RUNNING"
        if (!startServicesAfterGeneration && generatedProcessId) {
          const stopResult = await runServiceActionWithRetry({ processId: generatedProcessId, apiName: serviceName }, "stop")
          if (stopResult.ok) {
            finalStatus = "NOT_RUNNING"
          } else {
            throw new Error(`Generated ${serviceName}, but failed to stop it automatically`)
          }
        }
        availableServices.push({
          apiName: serviceName,
          lapis_config: clonedConfig,
          status: finalStatus,
        })
        if (Boolean(clonedConfig?.auth?.isAuthService)) {
          availableAuthServices.push({
            apiName: serviceName,
            lapis_config: clonedConfig,
            status: finalStatus,
          })
        }
        existingNames.add(serviceName.toLowerCase())
        successCount += 1
        updateBatchProgress({ completed: index + 1, succeeded: successCount, failed: failCount })
        setBatchConfigs((prev) => prev.map((entry) => (
          entry.id === item.id ? { ...entry, status: "success", error: "" } : entry
        )))
      } catch (error) {
        failCount += 1
        updateBatchProgress({ completed: index + 1, succeeded: successCount, failed: failCount })
        const normalizedError = normalizeBatchError(error?.message)
        setBatchConfigs((prev) => prev.map((entry) => (
          entry.id === item.id ? { ...entry, status: "failed", error: normalizedError } : entry
        )))
      }
    }

    setBatchGenerating(false)
    finishBatchProgress()
    if (successCount > 0) {
      toast.success(
        startServicesAfterGeneration
          ? `Generated and started ${successCount} service${successCount > 1 ? "s" : ""}`
          : `Generated ${successCount} service${successCount > 1 ? "s" : ""} (left stopped)`,
      )
    }
    if (failCount > 0) {
      toast.error(`${failCount} service${failCount > 1 ? "s" : ""} failed`)
    }
    if (readyItems.length === 1 && successCount === 1 && singleGeneratedProcessId) {
      router.push(`/services/${encodeURIComponent(singleGeneratedProcessId)}`)
      return
    }
    fetchServices()
    setBatchConfigs([])
  }

  const removeBatchConfig = (id) => {
    setBatchConfigs((prev) => prev.filter((item) => item.id !== id))
  }

  const clearBatchConfigs = () => {
    setBatchConfigs([])
  }

  const startBatchItemEdit = (item) => {
    if (!item?.config) return
    try {
      if (typeof window !== "undefined") {
        writeSessionJson(SERVICES_UPLOADED_BATCH_STORAGE_KEY, batchConfigs)
        writeSessionJson(BUILDER_EDIT_REQUEST_KEY, {
          source: "services-uploaded-list",
          storageKey: SERVICES_UPLOADED_BATCH_STORAGE_KEY,
          itemId: String(item.id),
          returnPath: "/services",
        })
      }
      router.push("/service-builder?mode=edit-uploaded")
    } catch {
      toast.error("Failed to open structured service editor")
    }
  }

  const confirmDelete = (service) => {
    setServiceToDelete(service)
    setDeleteDialogOpen(true)
  }

  const handleDeleteService = async () => {
    if (!serviceToDelete) return
    const targetId = String(serviceToDelete.processId)
    const previousServices = services
    setDeletingServiceIds((prev) => Array.from(new Set([...prev.map(String), targetId])))
    setServices((prev) => prev.filter((service) => String(service.processId) !== targetId))
    setSelectedServiceIds((prev) => prev.filter((id) => String(id) !== targetId))
    setDeleteDialogOpen(false)
    try {
      const response = await fetch(deleteServiceUrl(serviceToDelete.processId), {
        method: "DELETE",
        headers: authHeaders(),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || "Failed to delete service")
      toast.success(data.message || "Service deleted")
    } catch (error) {
      setServices(previousServices)
      console.error("Error deleting service:", error)
      toast.error(error?.message || "Error deleting service")
    } finally {
      setDeletingServiceIds((prev) => prev.filter((id) => String(id) !== targetId))
      setServiceToDelete(null)
      fetchServices()
    }
  }

  const handleDeleteAllServices = async () => {
    if (services.length === 0) {
      toast.message("No services to delete")
      return
    }
    const targetServices = [...services]
    const targetIds = targetServices.map((service) => String(service.processId))
    setDeletingAll(true)
    beginBatchProgress("delete-all", targetServices.length)
    setDeletingServiceIds((prev) => Array.from(new Set([...prev.map(String), ...targetIds])))
    setSelectedServiceIds([])
    try {
      let succeeded = 0
      let failed = 0
      const failedServices = []

      for (let index = 0; index < targetServices.length; index += 1) {
        const service = targetServices[index]
        updateBatchProgress({ current: service.apiName || String(service.processId) })
        const result = await deleteOneServiceWithRetry(service)
        if (result.ok) {
          succeeded += 1
          setServices((prev) => prev.filter((item) => String(item.processId) !== String(service.processId)))
        } else {
          failed += 1
          failedServices.push(service)
        }
        updateBatchProgress({ completed: index + 1, succeeded, failed })
      }

      if (succeeded > 0) {
        toast.success(`Deleted ${succeeded} service${succeeded > 1 ? "s" : ""}`)
      }
      if (failed > 0) {
        toast.error(`${failed} service${failed > 1 ? "s" : ""} failed to delete`)
        setServices((prev) => {
          const known = new Set(prev.map((svc) => String(svc.processId)))
          const additions = failedServices.filter((svc) => !known.has(String(svc.processId)))
          return [...prev, ...additions]
        })
      }
      setDeleteAllDialogOpen(false)
    } catch (error) {
      setServices(targetServices)
      toast.error(error?.message || "Failed to delete all services")
    } finally {
      finishBatchProgress()
      setDeletingServiceIds((prev) => prev.filter((id) => !targetIds.includes(String(id))))
      fetchServices()
      setDeletingAll(false)
    }
  }

  const handleDeleteSelectedServices = async () => {
    if (selectedServiceIds.length === 0) {
      toast.message("No services selected to delete")
      return
    }
    const targetIdSet = new Set(selectedServiceIds.map(String))
    const selectedServices = services.filter((service) => targetIdSet.has(String(service.processId)))
    const previousServices = services
    setDeletingServiceIds((prev) => Array.from(new Set([...prev.map(String), ...Array.from(targetIdSet)])))
    setDeleteSelectedDialogOpen(false)
    setSelectedServiceIds([])
    setDeletingSelected(true)
    beginBatchProgress("delete-selected", selectedServices.length)
    try {
      let succeeded = 0
      let failed = 0
      const failedServices = []
      for (let index = 0; index < selectedServices.length; index += 1) {
        const service = selectedServices[index]
        updateBatchProgress({ current: service.apiName || String(service.processId) })
        const result = await deleteOneServiceWithRetry(service)
        if (result.ok) {
          succeeded += 1
          setServices((prev) => prev.filter((item) => String(item.processId) !== String(service.processId)))
        } else {
          failed += 1
          failedServices.push(service)
        }
        updateBatchProgress({ completed: index + 1, succeeded, failed })
      }
      if (succeeded > 0) toast.success(`Deleted ${succeeded} selected service${succeeded > 1 ? "s" : ""}`)
      if (failed > 0) {
        toast.error(`${failed} selected service${failed > 1 ? "s" : ""} failed to delete`)
        setServices((prev) => {
          const known = new Set(prev.map((svc) => String(svc.processId)))
          const additions = failedServices.filter((svc) => !known.has(String(svc.processId)))
          return [...prev, ...additions]
        })
      }
    } catch (error) {
      setServices(previousServices)
      toast.error(error?.message || "Failed to delete selected services")
    } finally {
      finishBatchProgress()
      setDeletingServiceIds((prev) => prev.filter((id) => !targetIdSet.has(String(id))))
      fetchServices()
      setDeletingSelected(false)
    }
  }

  const formatDate = (dateString) => {
    if (!dateString) return "-"
    return new Date(dateString).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    })
  }

  const sortedServices = useMemo(() => {
    const getStatusRank = (service) => (service?.status === "RUNNING" ? 0 : 1)
    const getPortRank = (service) => {
      const port = Number(service?.port)
      return Number.isFinite(port) && port > 0 ? port : Number.POSITIVE_INFINITY
    }

    return [...services].sort((left, right) => {
      const statusRank = getStatusRank(left) - getStatusRank(right)
      if (statusRank !== 0) return statusRank

      const portRank = getPortRank(left) - getPortRank(right)
      if (portRank !== 0) return portRank

      const leftName = String(left?.apiName || "")
      const rightName = String(right?.apiName || "")
      const nameRank = leftName.localeCompare(rightName, undefined, { sensitivity: "base" })
      if (nameRank !== 0) return nameRank

      return String(left?.processId || "").localeCompare(String(right?.processId || ""), undefined, { numeric: true, sensitivity: "base" })
    })
  }, [services])

  const runningServices = services.filter((service) => service.status === "RUNNING").length
  const stoppedServices = services.length - runningServices
  const readyBatchCount = batchConfigs.filter((item) => item.status === "ready").length
  const allSelected = services.length > 0 && selectedServiceIds.length === services.length
  const someSelected = selectedServiceIds.length > 0 && !allSelected

  return (
    <div className="w-full app-stack">
      <section className="app-hero">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="app-eyebrow">Service Runtime</p>
            <h1 className="app-title mt-4">Operate generated services from one live control surface</h1>
            <p className="app-copy mt-3">Start, stop, inspect, batch-generate, and open service docs without leaving the management view.</p>
          </div>
          <Link href="/service-builder">
            <Button className="brand-solid h-11 px-5" disabled={!canManageServices}>
              <Plus className="mr-1 h-4 w-4" /> Create New Service
            </Button>
          </Link>
        </div>
      </section>

      <section className="space-y-4 py-2 md:py-3">
        <div className="grid gap-4 md:grid-cols-3">
          <div className="app-stat-card p-5">
            <div>
              <p className="app-stat-label">Total Services</p>
              <p className="mt-2 text-2xl font-semibold tracking-tight text-white">{services.length}</p>
            </div>
          </div>
          <div className="app-stat-card p-5">
            <div>
              <p className="app-stat-label">Running</p>
              <p className="mt-2 text-2xl font-semibold tracking-tight text-emerald-300">{runningServices}</p>
            </div>
          </div>
          <div className="app-stat-card p-5">
            <div>
              <p className="app-stat-label">Stopped</p>
              <p className="mt-2 text-2xl font-semibold tracking-tight text-amber-300">{stoppedServices}</p>
            </div>
          </div>
        </div>

        {uploadProgressEnabled && uploadOperationStatus?.visible ? (
          <OperationStatusPanel status={uploadOperationStatus} />
        ) : null}

        {batchProgress && (
          <div className={`app-card-soft p-4 ${batchProgress.done && batchProgress.failed === 0 ? "border border-green-400/35" : ""}`}>
            <div className="mb-2 flex items-center justify-between gap-3">
              <p className="text-sm font-medium text-slate-100">
                {{
                  "delete-all": "Deleting all services",
                  "delete-selected": "Deleting selected services",
                  "start-all": "Starting all eligible services",
                  "start-selected": "Starting selected services",
                  "stop-all": "Stopping all eligible services",
                  "stop-selected": "Stopping selected services",
                  generate: "Generating services from LAPIS files",
                }[batchProgress.kind] || "Processing batch operation"}
              </p>
              {batchProgress.done && batchProgress.failed === 0 ? (
                <div className="flex items-center gap-2 text-green-300">
                  <CheckCircle2 className="h-5 w-5 animate-bounce" />
                  <span className="text-sm font-semibold">Completed</span>
                </div>
              ) : (
                <span className="text-xs text-slate-400">
                  {batchProgress.completed}/{batchProgress.total}
                </span>
              )}
            </div>
            <Progress value={batchProgress.total > 0 ? (batchProgress.completed / batchProgress.total) * 100 : 0} className="h-2.5" />
            <div className="mt-2 flex items-center justify-between text-xs text-slate-300">
              <span>{batchProgress.current ? `Current: ${batchProgress.current}` : "Finalizing..."}</span>
              <span>{batchProgress.succeeded} success, {batchProgress.failed} failed</span>
            </div>
          </div>
        )}

        <div className="app-card-soft p-5">
          <p className="app-section-label">Access</p>
          <p className="mt-2 text-lg font-semibold text-slate-50">
            {canManageServices ? "Manage Services enabled" : "Read-only access"}
          </p>
          <p className="mt-2 text-sm text-slate-300">
            {canManageServices ? "Bulk actions and service controls are available." : "Ask an admin for MANAGE_SERVICES to start, stop, or delete services."}
          </p>
        </div>
      </section>

      <Card className="rounded-xl border-white/10 bg-[rgba(9,18,29,0.9)] shadow-sm">
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <div>
            <CardTitle className="text-xl text-slate-50">Services</CardTitle>
            <p className="mt-1 text-xs text-slate-400">
              {loading ? "Refreshing list..." : `${services.length} service${services.length === 1 ? "" : "s"} loaded`}
            </p>
            {deletingServiceIds.length > 0 && (
              <p className="mt-1 text-xs text-amber-300">
                Deleting {deletingServiceIds.length} service{deletingServiceIds.length === 1 ? "" : "s"}...
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="h-8" disabled={!canManageServices}>
                  <SlidersHorizontal className="mr-1 h-4 w-4" /> Options
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-72">
                <DropdownMenuLabel>Batch Options</DropdownMenuLabel>
                <DropdownMenuCheckboxItem
                  checked={alsoDeleteData}
                  onCheckedChange={(checked) => setAlsoDeleteData(Boolean(checked))}
                >
                  Delete data with service
                </DropdownMenuCheckboxItem>
                <DropdownMenuCheckboxItem
                  checked={startServicesAfterGeneration}
                  onCheckedChange={(checked) => setStartServicesAfterGeneration(Boolean(checked))}
                >
                  Start services after generation
                </DropdownMenuCheckboxItem>
                <DropdownMenuCheckboxItem
                  checked={retryFailedBatchOps}
                  onCheckedChange={(checked) => setRetryFailedBatchOps(Boolean(checked))}
                >
                  Retry failed batch requests once
                </DropdownMenuCheckboxItem>
                <DropdownMenuSeparator />
                <div className="px-2 py-1.5 text-xs text-slate-300">
                  Applies to batch generate, start/stop, and delete operations.
                </div>
              </DropdownMenuContent>
            </DropdownMenu>
            <Button variant="outline" size="sm" className="h-8" onClick={fetchServices} disabled={loading}>
              <RefreshCw className={`mr-1 h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Refresh
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-8 border-destructive/40 text-destructive hover:bg-destructive/10 dark:border-destructive/40 dark:text-destructive dark:hover:bg-destructive/20"
              onClick={() => setDeleteSelectedDialogOpen(true)}
              disabled={loading || deletingServiceIds.length > 0 || selectedServiceIds.length === 0 || !canManageServices}
            >
              <Trash2 className="mr-1 h-4 w-4" /> Delete Selected
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-8"
              onClick={() => handleSelectedServiceAction("start")}
              disabled={loading || bulkAction !== null || selectedServiceIds.length === 0 || !canManageServices}
            >
              <Play className="mr-1 h-4 w-4" /> Start Selected
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-8"
              onClick={() => handleSelectedServiceAction("stop")}
              disabled={loading || bulkAction !== null || selectedServiceIds.length === 0 || !canManageServices}
            >
              <Square className="mr-1 h-4 w-4" /> Stop Selected
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-8"
              onClick={() => handleBulkServiceAction("start")}
              disabled={loading || bulkAction !== null || !canManageServices}
            >
              <Play className="mr-1 h-4 w-4" /> Start All
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-8"
              onClick={() => handleBulkServiceAction("stop")}
              disabled={loading || bulkAction !== null || !canManageServices}
            >
              <Square className="mr-1 h-4 w-4" /> Stop All
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {canManageServices && (
            <div className="mb-5 rounded-[1.15rem] border border-white/10 bg-[rgba(14,24,37,0.72)] p-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-50">Create Multiple Services</p>
                  <p className="text-xs text-slate-300">
                    Select multiple LAPIS files, then generate services in one batch.
                    {batchConfigs.length > 0 ? ` ${readyBatchCount} ready of ${batchConfigs.length}.` : ""}
                  </p>
                </div>
                <div className="flex gap-2">
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept=".json,.lapis"
                    onChange={handleLapisUpload}
                    className="hidden"
                  />
                  <Button variant="outline" size="sm" className="h-8" onClick={() => fileInputRef.current?.click()} disabled={batchGenerating}>
                    <Upload className="mr-1 h-4 w-4" /> Select LAPIS Files
                  </Button>
                  <Button size="sm" className="brand-solid h-8" onClick={runBatchGenerate} disabled={batchGenerating || batchConfigs.filter((item) => item.status === "ready").length === 0}>
                    {batchGenerating ? "Generating..." : (startServicesAfterGeneration ? "Generate + Start All" : "Generate (Keep Stopped)")}
                  </Button>
                  <Button variant="outline" size="sm" className="h-8" onClick={clearBatchConfigs} disabled={batchGenerating || batchConfigs.length === 0}>
                    Clear List
                  </Button>
                </div>
              </div>
              {batchConfigs.length > 0 && (
                <div className="mt-3 space-y-2">
                  {batchConfigs.map((item) => (
                    <div
                      key={item.id}
                      className={`rounded-md border px-3 py-2 text-sm ${item.status !== "ready" ? "border-amber-400/60 bg-amber-500/10" : "border-orange-300/70 bg-orange-400/15 shadow-[0_0_18px_rgba(251,146,60,0.16)]"}`}
                    >
                      <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                        <span className="font-medium text-slate-50">{item.apiName}</span>
                        <div className="flex items-center gap-2">
                          <span className={`text-xs uppercase tracking-wide ${item.status === "ready" ? "font-semibold text-orange-200" : "text-slate-300"}`}>{item.status}</span>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-6 w-6 p-0"
                            onClick={() => startBatchItemEdit(item)}
                            disabled={batchGenerating || item.status === "running" || !item.config}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-6 w-6 p-0"
                            onClick={() => removeBatchConfig(item.id)}
                            disabled={batchGenerating}
                          >
                            <X className="h-3 w-3" />
                          </Button>
                        </div>
                      </div>
                      <p className="text-xs text-slate-300">{item.fileName}</p>
                      {item.progressMessage ? <p className="mt-1 text-xs text-slate-300">{item.progressMessage}</p> : null}
                      {item.repaired ? (
                        <p className="mt-1 text-xs text-emerald-300">
                          Auto-repaired with {Array.isArray(item.appliedFixes) ? item.appliedFixes.length : 0} deterministic fix{Array.isArray(item.appliedFixes) && item.appliedFixes.length === 1 ? "" : "es"}.
                        </p>
                      ) : null}
                      {item.error ? <LapisUploadError error={item.error} className="text-amber-300 dark:text-amber-300" /> : null}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {loading ? (
            <p className="py-8 text-sm text-slate-300">Loading services...</p>
          ) : services.length === 0 ? (
            <div className="py-10 text-center">
              <AlertTriangle className="mx-auto mb-4 h-12 w-12 text-slate-400" />
              <h3 className="text-lg font-medium text-slate-50">No services found</h3>
              <p className="mt-2 text-slate-300">Create your first service in Service Builder.</p>
              <Link href="/service-builder">
                <Button className="brand-solid mt-5">Create Service</Button>
              </Link>
            </div>
          ) : (
            <div className="app-table-shell overflow-x-auto">
              <Table className="[&_tbody_td]:text-slate-100 [&_tbody_tr]:border-white/10 [&_tbody_tr:hover]:bg-white/[0.04] [&_thead_th]:text-slate-300">
                <TableHeader>
                  <TableRow className="border-white/10 bg-white/[0.04]">
                    <TableHead className="w-[4%]">
                      <input
                        type="checkbox"
                        checked={allSelected}
                        ref={(el) => {
                          if (el) el.indeterminate = someSelected
                        }}
                        onChange={(e) => toggleSelectAllServices(e.target.checked)}
                        disabled={!canManageServices || services.length === 0}
                        aria-label="Select all services"
                      />
                    </TableHead>
                    <TableHead className="w-[26%] text-slate-300">Name</TableHead>
                    <TableHead className="w-[12%] text-slate-300">Status</TableHead>
                    <TableHead className="w-[10%] text-slate-300">Port</TableHead>
                    <TableHead className="w-[16%] text-slate-300">Runtime</TableHead>
                    <TableHead className="w-[18%] text-slate-300">Docs</TableHead>
                    <TableHead className="w-[12%] text-slate-300">Governance</TableHead>
                    <TableHead className="w-[10%] text-slate-300">Created</TableHead>
                    <TableHead className="w-[18%] text-slate-300">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sortedServices.map((service) => {
                    const links = resolveServiceLinks(service, LIWIRO_HOST)
                    const checked = selectedServiceIds.includes(String(service.processId))
                    const mediaCapabilities = service?.mediaCapabilities && typeof service.mediaCapabilities === "object"
                      ? service.mediaCapabilities
                      : {}
                    const mediaProviders = Array.isArray(mediaCapabilities.providers) ? mediaCapabilities.providers : []
                    return (
                    <TableRow key={service._id || service.processId} className="border-white/10 hover:bg-white/[0.04]">
                      <TableCell>
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) => toggleSelectService(service.processId, e.target.checked)}
                          disabled={!canManageServices}
                          aria-label={`Select ${service.apiName}`}
                        />
                      </TableCell>
                      <TableCell className="font-medium text-slate-50">
                        <Link href={`/services/${service.processId}`} className="text-sky-300 hover:text-sky-200 hover:underline">
                          {service.apiName}
                        </Link>
                        {mediaProviders.length > 0 && (
                          <>
                            <div className="mt-2 flex flex-wrap gap-1.5">
                              {mediaProviders.map((provider) => (
                                <Badge
                                  key={provider.id}
                                  variant="outline"
                                  className={provider.ready
                                    ? "border-emerald-300/40 bg-emerald-500/10 text-emerald-200"
                                    : "border-amber-300/40 bg-amber-500/10 text-amber-200"}
                                >
                                  {provider.label}
                                  {provider.default ? " default" : ""}
                                </Badge>
                              ))}
                            </div>
                            <p className="mt-2 text-xs text-slate-400">
                              Assets: {mediaCapabilities.assetCollection || "media_assets"} • JSON inputs: {(mediaCapabilities.inputModes || []).join(", ") || "configured in service docs"}
                            </p>
                          </>
                        )}
                      </TableCell>
                      <TableCell>
                        {service.status === "RUNNING" ? (
                          <Badge className="bg-green-100 text-green-800 hover:bg-green-100 dark:bg-green-900/40 dark:text-green-300">
                            Running
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-50 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                            Not Running
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-slate-200">{service.status === "RUNNING" && service.port ? service.port : "_"}</TableCell>
                      <TableCell className="whitespace-nowrap">
                        {links.runtime ? (
                          <a
                            href={links.runtime}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex rounded-md border border-sky-400/30 bg-sky-400/10 px-2.5 py-1 text-xs font-medium text-sky-100 hover:bg-sky-400/20"
                          >
                            Runtime (/liwiro)
                          </a>
                        ) : (
                          <span className="text-slate-400">Unavailable</span>
                        )}
                        {links.root && (
                          <a
                            href={links.root}
                            target="_blank"
                            rel="noreferrer"
                            className="ml-2 inline-flex rounded-md border border-white/10 bg-white/[0.03] px-2.5 py-1 text-xs font-medium text-slate-100 hover:bg-white/[0.08]"
                          >
                            Root
                          </a>
                        )}
                      </TableCell>
                      <TableCell className="whitespace-nowrap">
                        {links.liwiroDocs ? (
                          <a
                            href={links.liwiroDocs}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex rounded-md border border-sky-400/30 bg-sky-400/10 px-2.5 py-1 text-xs font-medium text-sky-100 hover:bg-sky-400/20"
                          >
                            Service Docs
                          </a>
                        ) : (
                          <span className="text-slate-400">
                            {links.docsEnabled === false ? "Disabled" : "Unavailable"}
                          </span>
                        )}
                      </TableCell>
                      <TableCell>
                        {service?.governance?.status === "ready" ? (
                          <Badge className="border border-orange-300/70 bg-orange-400/20 text-orange-100 hover:bg-orange-400/25">
                            Ready {service.governance.score}%
                          </Badge>
                        ) : (
                          <div className="space-y-1">
                            <Badge variant="outline" className="border-amber-300/50 text-amber-200">
                              {service?.governance?.score ?? 0}% coverage
                            </Badge>
                            <p className="max-w-44 text-xs text-amber-200/80">
                              {service?.governance?.issues?.[0]?.message || "Review service controls."}
                            </p>
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-slate-200">{formatDate(service.createdAt)}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Link href={`/services/${service.processId}`}>
                            <Button variant="outline" size="sm" className="h-8 w-8 p-0">
                              <Pencil className="h-4 w-4" />
                            </Button>
                          </Link>
                          {service.status === "RUNNING" ? (
                            <Button variant="outline" size="sm" className="h-8" onClick={() => handleStopService(service.processId)} disabled={!canManageServices}>
                              <Square className="mr-1 h-4 w-4" /> Stop
                            </Button>
                          ) : (
                            <Button variant="outline" size="sm" className="h-8" onClick={() => handleStartService(service.processId)} disabled={!canManageServices}>
                              <Play className="mr-1 h-4 w-4" /> Start
                            </Button>
                          )}
                          <Button
                            variant="outline"
                            size="sm"
                              onClick={() => confirmDelete(service)}
                            className="h-8 w-8 border-destructive/40 p-0 text-destructive hover:bg-destructive/10 hover:text-destructive dark:border-destructive/40 dark:hover:bg-destructive/20"
                            disabled={!canManageServices || deletingAll || deletingSelected || deletingServiceIds.includes(String(service.processId))}
                          >
                            {deletingServiceIds.includes(String(service.processId)) ? (
                              <RefreshCw className="h-4 w-4 animate-spin" />
                            ) : (
                              <Trash2 className="h-4 w-4" />
                            )}
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete the service <span className="font-semibold">{serviceToDelete?.apiName}</span>{alsoDeleteData ? " and its data" : ""}. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={serviceToDelete ? deletingServiceIds.includes(String(serviceToDelete.processId)) : false}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteService}
              disabled={serviceToDelete ? deletingServiceIds.includes(String(serviceToDelete.processId)) : false}
            >
              {serviceToDelete && deletingServiceIds.includes(String(serviceToDelete.processId)) ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={deleteAllDialogOpen} onOpenChange={setDeleteAllDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete all services?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete all listed services{alsoDeleteData ? " and their data" : ""}. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deletingAll}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteAllServices} disabled={deletingAll}>
              {deletingAll ? "Deleting..." : "Delete All"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={deleteSelectedDialogOpen} onOpenChange={setDeleteSelectedDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete selected services?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete {selectedServiceIds.length} selected service{selectedServiceIds.length === 1 ? "" : "s"}{alsoDeleteData ? " and their data" : ""}. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deletingSelected}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteSelectedServices} disabled={deletingSelected}>
              {deletingSelected ? "Deleting..." : "Delete Selected"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={authSelectionDialogOpen}
        onOpenChange={(open) => {
          setAuthSelectionDialogOpen(open)
          if (!open && authSelectionResolver) {
            resolveAuthSelectionDialog(null)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Select Authentication Service</AlertDialogTitle>
            <AlertDialogDescription>
              Multiple authentication services are available. Choose one for this service.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-3">
            <Label htmlFor="auth-service-select">Authentication service</Label>
            <select
              id="auth-service-select"
              className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm dark:border-slate-700 dark:bg-slate-950"
              value={authSelectionChoice}
              onChange={(e) => setAuthSelectionChoice(e.target.value)}
            >
              {authSelectionOptions.map((svc) => (
                <option key={svc.processId || svc.apiName} value={String(svc.apiName || "")}>
                  {svc.apiName}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={authSelectionApplyAll}
                onChange={(e) => setAuthSelectionApplyAll(e.target.checked)}
              />
              Use this choice for all remaining services
            </label>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => resolveAuthSelectionDialog(null)}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                const selected = authSelectionOptions.find((svc) => String(svc.apiName || "") === authSelectionChoice)
                resolveAuthSelectionDialog({ selected, applyAll: authSelectionApplyAll })
              }}
            >
              Continue
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <TransientSuccessDialog
        status={uploadOperationStatus}
        onOpenChange={(open) => {
          if (!open && uploadOperationStatus?.presentation === "modal") {
            clearUploadOperation()
          }
        }}
      />
    </div>
  )
}
