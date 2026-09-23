// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

"use client"

import { useState, useEffect, useRef, useCallback, useMemo } from "react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { authHeaders } from "@/lib/auth"
import { AlertTriangle, ArrowLeft, Pencil, X } from "lucide-react"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"
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
import MetadataConfig from "./components/MetadataConfig"
import AuthConfig from "./components/AuthConfig"
import ModelConfig from "./components/ModelConfig"
import SharedModuleConfig from "./components/SharedModuleConfig"
import ModuleConfig from "./components/ModuleConfig"
import EndpointConfig from "./components/EndpointConfig"
import PreviewConfig from "./components/PreviewConfig"
import { IDECodeEditor } from "@/components/ide/code-editor"
import { ModeToggle } from "@/components/ide/mode-toggle"
import { LapisUploadError } from "@/components/lapis/lapis-upload-error"
import { fetchAuthedJson } from "@/lib/authed-json-cache"
import { parseJsonLikeText } from "@/lib/json-editor"
import { mapVersaIssuesByEndpoint, validateLapisConfigRemote } from "@/lib/lapis-validation"
import { OperationStatusPanel } from "@/components/ui/operation-status-panel"
import { TransientSuccessDialog } from "@/components/ui/transient-success-dialog"
import { useOperationStatus } from "@/lib/operation-status"
import { isFeatureEnabled, usePlatformFeatureFlags } from "@/lib/platform-flags"
import { activatePendingVerseAction, consumePendingVerseAction } from "@/lib/verse-actions"
import {
  BUILDER_EDIT_REQUEST_KEY,
  BUILDER_EDIT_RESULT_KEY,
  SERVICE_BUILDER_UPLOADED_BATCH_STORAGE_KEY,
  getBatchReturnPathForSource,
  getBatchStorageKeyForSource,
  readSessionJson,
  writeSessionJson,
} from "@/lib/uploaded-batch-storage"

export default function ServiceBuilderPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const LIWIRO_BACKEND = process.env.NEXT_PUBLIC_LIWIRO_BACKEND || "http://127.0.0.1:5000"
  const createId = () => {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID()
    }
    return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  }
  const isPlainObject = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value)
  const baseConfig = {
    metadata: {
      apiName: "",
      basePath: "/api/v1",
      version: "1.0.0",
      database: "main",
      developerNotes: "",
      setupApiKey: "liwiroservicepass0!",
      documentation: { enabled: true, key: "liwiroservicepass0!" },
      env: {},
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
    sharedModules: {},
    modules: [],
    endpoints: {},
  }

  const normalizeFieldDefinition = (field, fallbackId, depth = 0) => {
    const normalizedField = isPlainObject(field) ? { ...field } : {}
    const resolvedId = String(normalizedField.id || fallbackId || "").trim() || fallbackId || createId()
    const normalizedType = String(normalizedField.type || "string").trim() || "string"
    const embeddedFields = normalizedType === "object" && Array.isArray(normalizedField.embeddedFields)
      ? normalizedField.embeddedFields.map((embeddedField, index) =>
          normalizeFieldDefinition(embeddedField, `${resolvedId}-${index + 1}`, depth + 1),
        )
      : []

    return {
      ...normalizedField,
      id: resolvedId,
      name: String(normalizedField.name || ""),
      type: normalizedType,
      required: Boolean(normalizedField.required),
      unique: Boolean(normalizedField.unique),
      default: Boolean(normalizedField.default),
      defaultValue: normalizedField.defaultValue ?? "",
      objectTemplate: String(normalizedField.objectTemplate || ""),
      embeddedFields,
      depth: Number.isFinite(Number(normalizedField.depth)) ? Number(normalizedField.depth) : depth,
    }
  }

  const normalizeModelDefinitions = (models) => Object.fromEntries(
    Object.entries(isPlainObject(models) ? models : {}).map(([modelId, model]) => {
      const normalizedModel = isPlainObject(model) ? { ...model } : {}
      const normalizedFields = Object.fromEntries(
        Object.entries(isPlainObject(normalizedModel.fields) ? normalizedModel.fields : {}).map(([fieldId, field]) => [
          fieldId,
          normalizeFieldDefinition(field, fieldId, 0),
        ]),
      )

      return [
        modelId,
        {
          ...normalizedModel,
          name: String(normalizedModel.name || ""),
          collection: String(normalizedModel.collection || ""),
          fields: normalizedFields,
        },
      ]
    }),
  )

  const updateEmbeddedFieldPath = (fields, fieldPath, updater) => {
    const [rootFieldId, ...nestedFieldIds] = Array.isArray(fieldPath) ? fieldPath : []
    if (!rootFieldId) return null
    const rootField = fields?.[rootFieldId]
    if (!rootField) return null

    const applyUpdate = (fieldNode, remainingIds) => {
      if (!fieldNode || typeof fieldNode !== "object") return null
      const nextFieldNode = { ...fieldNode }
      if (remainingIds.length === 0) {
        return updater(nextFieldNode)
      }

      const [childId, ...nextRemainingIds] = remainingIds
      const embeddedFields = Array.isArray(fieldNode.embeddedFields) ? fieldNode.embeddedFields : []
      const childIndex = embeddedFields.findIndex((child) => child?.id === childId)
      if (childIndex < 0) return null

      const updatedChild = applyUpdate(embeddedFields[childIndex], nextRemainingIds)
      if (!updatedChild) return null

      const nextEmbeddedFields = [...embeddedFields]
      nextEmbeddedFields[childIndex] = updatedChild
      nextFieldNode.embeddedFields = nextEmbeddedFields
      return nextFieldNode
    }

    const nextRootField = applyUpdate(rootField, nestedFieldIds)
    if (!nextRootField) return null

    return {
      ...(fields || {}),
      [rootFieldId]: nextRootField,
    }
  }

  const [config, setConfig] = useState(baseConfig)
  const [submitError, setSubmitError] = useState("")
  const [batchConfigs, setBatchConfigs] = useState([])
  const [editingBatchId, setEditingBatchId] = useState("")
  const [editingOriginalConfig, setEditingOriginalConfig] = useState(null)
  const [externalBatchEditId, setExternalBatchEditId] = useState("")
  const [externalBatchEditMode, setExternalBatchEditMode] = useState(false)
  const [externalBatchReturnPath, setExternalBatchReturnPath] = useState("/services")
  const [externalBatchStorageKey, setExternalBatchStorageKey] = useState("")
  const [externalBatchSource, setExternalBatchSource] = useState("")
  const [builderBatchStorageReady, setBuilderBatchStorageReady] = useState(false)
  const [batchGenerating, setBatchGenerating] = useState(false)
  const [authSelectionDialogOpen, setAuthSelectionDialogOpen] = useState(false)
  const [authSelectionOptions, setAuthSelectionOptions] = useState([])
  const [authSelectionChoice, setAuthSelectionChoice] = useState("")
  const [authSelectionApplyAll, setAuthSelectionApplyAll] = useState(true)
  const [authSelectionResolver, setAuthSelectionResolver] = useState(null)
  const [startServicesAfterGeneration, setStartServicesAfterGeneration] = useState(true)
  const [availableModules, setAvailableModules] = useState([])
  const [availableModuleDomains, setAvailableModuleDomains] = useState([])
  const [modulesLoading, setModulesLoading] = useState(false)
  const [versaValidationState, setVersaValidationState] = useState({
    error: "",
    versaIssues: [],
    endpointErrors: {},
    pending: false,
  })
  const [validationControl, setValidationControl] = useState({
    attemptCount: 0,
    resetCount: 0,
    continueApproved: false,
    blocked: false,
    timedOut: false,
    thresholdReached: false,
    shouldAskForHelp: false,
  })
  const [validationDialogOpen, setValidationDialogOpen] = useState(false)
  const [validationResumeToken, setValidationResumeToken] = useState(0)
  const {
    status: uploadOperationStatus,
    startOperation: startUploadOperation,
    updateOperation: updateUploadOperation,
    succeedOperation: succeedUploadOperation,
    failOperation: failUploadOperation,
    clearStatus: clearUploadOperation,
  } = useOperationStatus({ autoHideSuccessMs: 2200 })

  const [activeTab, setActiveTab] = useState("config")
  const [editorMode, setEditorMode] = useState("structured")
  const [rawConfigText, setRawConfigText] = useState(JSON.stringify(baseConfig, null, 2))
  const [rawConfigError, setRawConfigError] = useState("")
  const [hasAuthModel, setHasAuthModel] = useState(false)
  const fileInputRef = useRef(null)
  const normalizeConfigRef = useRef((value) => value)
  const sanitizeForSubmitRef = useRef((value) => value)
  const configHasVersaScriptEndpointsRef = useRef(() => false)
  const generateServiceFromConfigRef = useRef(null)
  const versaValidationSignatureRef = useRef("")
  const validationControlRef = useRef(validationControl)
  const { featureFlags } = usePlatformFeatureFlags(LIWIRO_BACKEND)
  const uploadProgressEnabled = isFeatureEnabled(featureFlags, "unifiedOperationStatus", true)
    && isFeatureEnabled(featureFlags, "serviceBatchProgressMessages", true)
  const uploadSuccessModalEnabled = isFeatureEnabled(featureFlags, "transientSuccessFeedback", true)

  const sanitizeGenerateErrorMessage = (value, fallback = "Failed to generate service.") => {
    const message = String(value || "").trim() || fallback
    return message.replace(/^Error:\s*/i, "")
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

  const normalizeConfig = (incoming) => {
    const merged = {
      ...baseConfig,
      ...(incoming || {}),
      metadata: { ...baseConfig.metadata, ...((incoming || {}).metadata || {}) },
      auth: { ...baseConfig.auth, ...((incoming || {}).auth || {}) },
      models: normalizeModelDefinitions((incoming || {}).models),
      sharedModules: { ...(((incoming || {}).sharedModules && typeof (incoming || {}).sharedModules === "object" && !Array.isArray((incoming || {}).sharedModules)) ? (incoming || {}).sharedModules : {}) },
      modules: Array.isArray((incoming || {}).modules) ? (incoming || {}).modules : [],
      endpoints: { ...((incoming || {}).endpoints || {}) },
    }

    merged.endpoints = Object.fromEntries(
      Object.entries(merged.endpoints).map(([id, ep]) => [
        id,
        {
          ...ep,
          enabled: ep.enabled !== false,
          operationType: normalizeOperationType(ep.operationType || "crud"),
          crudOperation: normalizeCrudOperation(ep.crudOperation || "read"),
          versaScript: ep.versaScript || "",
          developerNotes: ep.developerNotes || "",
          exampleParams: isPlainObject(ep.exampleParams) ? ep.exampleParams : {},
        },
      ]),
    )

    merged.metadata.documentation = {
      ...baseConfig.metadata.documentation,
      ...((merged.metadata || {}).documentation || {}),
    }
    merged.metadata.seedData = {
      ...baseConfig.metadata.seedData,
      ...((merged.metadata || {}).seedData || {}),
      collections: ((merged.metadata || {}).seedData || {}).collections || {},
    }
    merged.metadata.env = {
      ...(baseConfig.metadata.env || {}),
      ...((merged.metadata || {}).env || {}),
    }
    merged.auth.defaultSuperAdmin = {
      ...baseConfig.auth.defaultSuperAdmin,
      ...((merged.auth || {}).defaultSuperAdmin || {}),
    }
    merged.auth.customEndpoints = {
      ...baseConfig.auth.customEndpoints,
      ...((merged.auth || {}).customEndpoints || {}),
    }
    merged.auth.passwordResetPage = {
      ...baseConfig.auth.passwordResetPage,
      ...((merged.auth || {}).passwordResetPage || {}),
    }
    merged.models = normalizeModelDefinitions(merged.models)

    return merged
  }

  const configHasVersaScriptEndpoints = (candidateConfig = config) => Object.values(candidateConfig?.endpoints || {}).some(
    (endpoint) => String(endpoint?.operationType || "").trim().toLowerCase() === "script" && String(endpoint?.versaScript || "").trim()
  )
  configHasVersaScriptEndpointsRef.current = configHasVersaScriptEndpoints

  useEffect(() => {
    validationControlRef.current = validationControl
  }, [validationControl])

  const validateConfigWithBackend = useCallback(async (candidateConfig) => {
    const normalize = normalizeConfigRef.current
    const sanitize = sanitizeForSubmitRef.current
    const normalizedCandidate = sanitize(normalize(candidateConfig))
    const result = await validateLapisConfigRemote(LIWIRO_BACKEND, normalizedCandidate, validationControlRef.current)
    return {
      ...result,
      endpointErrors: mapVersaIssuesByEndpoint(result?.versaIssues || []),
      normalized: result?.normalized && typeof result.normalized === "object" ? normalize(result.normalized) : normalizedCandidate,
    }
  }, [LIWIRO_BACKEND])

  const bestLapisIssueMessage = useCallback((result, fallback = "") => {
    const issueMessage = (Array.isArray(result?.issues) ? result.issues : [])
      .map((item) => String(item?.message || item?.error || "").trim())
      .find(Boolean)
    return String(result?.error || issueMessage || fallback || "").trim()
  }, [])

  const prepareConfigForUploadWorkflow = useCallback(async (candidateConfig) => {
    const normalize = normalizeConfigRef.current
    const sanitize = sanitizeForSubmitRef.current
    const normalizedCandidate = sanitize(normalize(candidateConfig))
    const result = await validateLapisConfigRemote(LIWIRO_BACKEND, normalizedCandidate, validationControlRef.current)

    return {
      ...result,
      endpointErrors: mapVersaIssuesByEndpoint(result?.versaIssues || result?.issues || []),
      normalized: result?.normalized && typeof result.normalized === "object" ? normalize(result.normalized) : normalizedCandidate,
    }
  }, [LIWIRO_BACKEND])
  normalizeConfigRef.current = normalizeConfig

  useEffect(() => {
    const authModelExists = Object.values(config.models).some(model => {
      const fieldNames = Object.values(model?.fields || {}).map(field => field.name?.toLowerCase() || '')
      return fieldNames.includes("username") && fieldNames.includes("email") && fieldNames.includes("password")
    })

    setHasAuthModel(authModelExists)

    if (authModelExists && !config.auth.authModel) {
      const authModel = Object.values(config.models).find(model =>
        Object.values(model?.fields || {}).some(field =>
          ["username", "email", "password"].includes(field.name?.toLowerCase())
        )
      )
      if (authModel) updateConfig("auth", null, "authModel", authModel.name)
    }
  // updateConfig is stable for this model-derived initialization effect.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.models, config.auth.authModel])

  useEffect(() => {
    const handleVerseContextRequest = (event) => {
      const respond = event?.detail?.respond
      if (typeof respond !== "function") return
      const serviceName = String(config?.metadata?.apiName || "").trim()
      const focusLabel = serviceName || "Current service draft"
      const rawPreview = String(rawConfigText || "").trim()
      const focusPreview = rawPreview.length > 1200 ? `${rawPreview.slice(0, 1200)}...` : rawPreview
      respond({
        pageKind: "service-builder",
        screen: "service builder",
        pathname: "/service-builder",
        editorMode,
        activeTab,
        serviceName,
        lapisConfig: config,
        rawConfigText,
        focus: {
          kind: "service-builder-lapis",
          label: focusLabel,
          identifier: serviceName,
          contentSummary: `Current ${activeTab} view for ${focusLabel}`,
          contentPreview: focusPreview,
        },
        relevanceHints: {
          focusPreferred: true,
          activeEditor: true,
          activeTab,
        },
      })
    }

    const handleVerseApply = (event) => {
      const artifact = event?.detail?.artifact
      const respond = event?.detail?.respond
      if (artifact?.kind !== "service-builder-lapis" || typeof respond !== "function") return
      try {
        const normalized = (normalizeConfigRef.current || ((value) => value))(artifact?.lapisConfig || {})
        const preferredMode = String(artifact?.modePreference || "structured").trim().toLowerCase() === "raw" ? "raw" : "structured"
        setConfig(normalized)
        setRawConfigText(JSON.stringify(normalized, null, 2))
        setEditorMode(preferredMode)
        setActiveTab("config")
        respond({
          ok: true,
          message: preferredMode === "raw" ? "Loaded the LAPIS config into raw mode." : "Loaded the LAPIS config into structured mode.",
        })
      } catch (error) {
        respond({ ok: false, message: error?.message || "Failed to apply the LAPIS config." })
      }
    }

    const handleVerseExecute = (event) => {
      const artifact = event?.detail?.artifact
      const respond = event?.detail?.respond
      if (artifact?.kind !== "service-builder-lapis" || typeof respond !== "function") return
      try {
        const normalized = (normalizeConfigRef.current || ((value) => value))(artifact?.lapisConfig || {})
        const preferredMode = String(artifact?.modePreference || "structured").trim().toLowerCase() === "raw" ? "raw" : "structured"
        setConfig(normalized)
        setRawConfigText(JSON.stringify(normalized, null, 2))
        setEditorMode(preferredMode)
        setActiveTab("config")
        Promise.resolve(generateServiceFromConfigRef.current?.(normalized))
          .then((generated) => {
            const serviceName = String(generated?.apiName || normalized?.metadata?.apiName || "service").trim() || "service"
            respond({ ok: true, message: `Generated ${serviceName} from the Verse draft.` })
          })
          .catch((error) => {
            const message = sanitizeGenerateErrorMessage(error?.message, "Failed to generate the Verse draft.")
            if (/already exists/i.test(message)) {
              setSubmitError(message)
              setActiveTab("config")
              respond({
                ok: true,
                message: `${message} The draft is loaded in Service Builder so you can rename it and generate again.`,
              })
              return
            }
            respond({ ok: false, message })
          })
      } catch (error) {
        respond({ ok: false, message: sanitizeGenerateErrorMessage(error?.message, "Failed to execute the Verse draft.") })
      }
    }

    window.addEventListener("liwiro:verse-assistant-request-context", handleVerseContextRequest)
    window.addEventListener("liwiro:verse-assistant-apply", handleVerseApply)
    window.addEventListener("liwiro:verse-assistant-execute", handleVerseExecute)
    const pendingAction = consumePendingVerseAction("/service-builder")
    if (pendingAction?.artifact) {
      activatePendingVerseAction({
        pathname: "/service-builder",
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
  }, [activeTab, config, editorMode, rawConfigText])

  useEffect(() => {
    const storedBatch = readSessionJson(SERVICE_BUILDER_UPLOADED_BATCH_STORAGE_KEY)
    if (Array.isArray(storedBatch)) {
      setBatchConfigs(storedBatch)
    }
    setBuilderBatchStorageReady(true)
  }, [])

  useEffect(() => {
    let cancelled = false

    const loadPlatformDefaults = async () => {
      try {
        const data = await fetchAuthedJson(`${LIWIRO_BACKEND}/platform/settings`, { ttlMs: 2500 })
        if (!cancelled) {
          setStartServicesAfterGeneration(Boolean(data?.startServicesAfterGenerationByDefault))
        }
      } catch {
        // Keep local defaults when platform settings are unavailable.
      }
    }

    loadPlatformDefaults()

    return () => {
      cancelled = true
    }
  }, [LIWIRO_BACKEND])

  const loadModulesCatalog = useCallback(async ({ silent = false } = {}) => {
    setModulesLoading(true)
    try {
      const data = await fetchAuthedJson(`${LIWIRO_BACKEND}/platform/vi/modules/catalog`, { ttlMs: 10000 })
      setAvailableModules(Array.isArray(data?.modules) ? data.modules : [])
      setAvailableModuleDomains(Array.isArray(data?.available_domains) ? data.available_domains : [])
      return true
    } catch (error) {
      if (error?.status === 401) {
        window.location.href = "/login"
        return false
      }
      if (!silent) {
        toast.error(error?.message || "Failed to load VI modules")
      }
      return false
    } finally {
      setModulesLoading(false)
    }
  }, [LIWIRO_BACKEND])

  useEffect(() => {
    loadModulesCatalog({ silent: true })
  }, [loadModulesCatalog])

  useEffect(() => {
    if (typeof window === "undefined") return
    if (searchParams.get("mode") !== "edit-uploaded") return
    try {
      const request = readSessionJson(BUILDER_EDIT_REQUEST_KEY)
      if (!request) {
        setSubmitError("No uploaded service edit context was found. Go back to Services and retry.")
        return
      }
      const source = String(request?.source || "services-uploaded-list")
      const storageKey = String(request?.storageKey || getBatchStorageKeyForSource(source))
      const returnPath = String(request?.returnPath || getBatchReturnPathForSource(source))
      const batchItems = readSessionJson(storageKey)
      if (!request?.itemId || !Array.isArray(batchItems)) {
        setSubmitError("Invalid uploaded service edit context. Go back to Services and retry.")
        return
      }
      const target = batchItems.find((item) => String(item?.id) === String(request.itemId))
      if (!target?.config) {
        setSubmitError("Selected uploaded service config is unavailable.")
        return
      }
      const normalized = normalizeConfig(target.config)
      setExternalBatchEditId(String(request.itemId))
      setExternalBatchEditMode(true)
      setExternalBatchReturnPath(returnPath)
      setExternalBatchStorageKey(storageKey)
      setExternalBatchSource(source)
      setConfig(normalized)
      setEditingOriginalConfig(normalized)
      setSubmitError("")
      setActiveTab("config")
      window.scrollTo({ top: 0, behavior: "smooth" })
    } catch {
      setSubmitError("Failed to load uploaded service edit context.")
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  useEffect(() => {
    if (typeof window === "undefined") return
    if (!builderBatchStorageReady || externalBatchEditMode) return
    writeSessionJson(SERVICE_BUILDER_UPLOADED_BATCH_STORAGE_KEY, batchConfigs)
  }, [batchConfigs, builderBatchStorageReady, externalBatchEditMode])

  const addModel = () => {
    const modelId = createId()
    setConfig(prev => ({
      ...prev,
      models: {
        ...prev.models,
        [modelId]: { name: "", collection: "", fields: {} }
      }
    }))
  }

  const addEndpoint = () => {
    const endpointId = createId()
    setConfig(prev => ({
      ...prev,
      endpoints: {
        ...prev.endpoints,
        [endpointId]: {
          enabled: true,
          method: "GET",
          path: "/",
          operationType: "crud",
          crudOperation: "read",
          developerNotes: "",
          exampleParams: {},
          linkedModel: "",
          defaultParameters: {
            data: { enabled: true, name: "data" },
            query: { enabled: true, name: "query", operator: "$eq" }
          }
        }
      }
    }))
  }

  const removeEndpoint = (endpointId) => {
    setConfig(prev => {
      const nextEndpoints = { ...(prev.endpoints || {}) }
      delete nextEndpoints[endpointId]
      return {
        ...prev,
        endpoints: nextEndpoints,
      }
    })
  }

  const removeModel = (modelId) => {
    setConfig(prev => {
      const nextModels = { ...(prev.models || {}) }
      delete nextModels[modelId]
      return {
        ...prev,
        models: nextModels,
      }
    })
  }

  const updateConfig = (section, id, field, value) => {
    setConfig(prev => {
      if (section === "metadata") {
        return {
          ...prev,
          metadata: {
            ...prev.metadata,
            [field]: value,
          },
        }
      }

      if (section === "models") {
        const currentModel = prev.models?.[id]
        if (!currentModel) return prev
        return {
          ...prev,
          models: {
            ...(prev.models || {}),
            [id]: {
              ...currentModel,
              [field]: value,
            },
          },
        }
      }

      if (section === "fields") {
        const [modelId, ...fieldPath] = id.split(':')
        const currentModel = prev.models?.[modelId]
        if (!currentModel) return prev

        const nextFields = updateEmbeddedFieldPath(currentModel.fields || {}, fieldPath, (currentField) => {
          if (field === "embeddedFields") {
            currentField.embeddedFields = Array.isArray(value) ? value : []
          } else {
            currentField[field] = value
            if (field === "type") {
              currentField.embeddedFields = value === "object"
                ? (Array.isArray(currentField.embeddedFields) ? currentField.embeddedFields : [])
                : []
            }
          }
          return currentField
        })

        if (!nextFields) return prev

        return {
          ...prev,
          models: {
            ...(prev.models || {}),
            [modelId]: {
              ...currentModel,
              fields: nextFields,
            },
          },
        }
      }

      if (section === "endpoints") {
        const currentEndpoint = prev.endpoints?.[id]
        if (!currentEndpoint) return prev
        return {
          ...prev,
          endpoints: {
            ...(prev.endpoints || {}),
            [id]: {
              ...currentEndpoint,
              [field]: value,
            },
          },
        }
      }

      if (section === "modules") {
        return {
          ...prev,
          modules: Array.isArray(value) ? value : [],
        }
      }

      if (section === "sharedModules") {
        return {
          ...prev,
          sharedModules: value && typeof value === "object" && !Array.isArray(value) ? value : {},
        }
      }

      if (section === "auth") {
        return {
          ...prev,
          auth: {
            ...prev.auth,
            [field]: typeof value === "object" ? { ...prev.auth?.[field], ...value } : value,
          },
        }
      }

      if (section === "defaultParameters") {
        const [endpointId, paramType, paramField] = id.split(':')
        const currentEndpoint = prev.endpoints?.[endpointId]
        if (!currentEndpoint) return prev
        const defaultParameters = currentEndpoint.defaultParameters && typeof currentEndpoint.defaultParameters === "object"
          ? currentEndpoint.defaultParameters
          : {}
        const currentParamType = defaultParameters[paramType] && typeof defaultParameters[paramType] === "object"
          ? defaultParameters[paramType]
          : {}
        return {
          ...prev,
          endpoints: {
            ...(prev.endpoints || {}),
            [endpointId]: {
              ...currentEndpoint,
              defaultParameters: {
                ...defaultParameters,
                [paramType]: {
                  ...currentParamType,
                  [paramField]: value,
                },
              },
            },
          },
        }
      }

      return prev
    })
  }

  const attachModuleToService = async (moduleName) => {
    const normalizedName = String(moduleName || "").trim().toLowerCase()
    if (!normalizedName) return false

    let created = false
    setConfig((prev) => {
      const existing = Array.isArray(prev.modules) ? prev.modules : []
      if (existing.some((item) => String(item?.name || "").trim().toLowerCase() === normalizedName)) {
        return prev
      }
      created = true
      return {
        ...prev,
        modules: [...existing, { name: normalizedName, config: {} }],
      }
    })

    const serviceDomain = String(config?.metadata?.apiName || "").trim().toLowerCase()
    if (!serviceDomain || (config?.sharedModules && Object.prototype.hasOwnProperty.call(config.sharedModules, normalizedName))) {
      return created
    }

    try {
      const response = await fetch(`${LIWIRO_BACKEND}/platform/vi/modules/${encodeURIComponent(normalizedName)}/domains`, {
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
      env: {
        ...(baseConfig.metadata.env || {}),
        ...((incomingConfig.metadata || {}).env || {}),
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
    models: normalizeModelDefinitions(incomingConfig.models),
    sharedModules: Object.fromEntries(
      Object.entries(
        incomingConfig.sharedModules && typeof incomingConfig.sharedModules === "object" && !Array.isArray(incomingConfig.sharedModules)
          ? incomingConfig.sharedModules
          : {},
      )
        .map(([rawName, rawModule]) => {
          const name = String(rawName || "").trim().toLowerCase()
          const moduleConfig = rawModule && typeof rawModule === "object" && !Array.isArray(rawModule) ? rawModule : {}
          return [
            name,
            {
              title: String(moduleConfig.title || name).trim() || name,
              description: String(moduleConfig.description || "").trim(),
              source: String(moduleConfig.source || ""),
              scope: String(moduleConfig.scope || "domain") === "global" ? "global" : "domain",
              serviceDomain: String(moduleConfig.serviceDomain || moduleConfig.service_domain || incomingConfig?.metadata?.apiName || "").trim().toLowerCase(),
              configSchema: moduleConfig.configSchema && typeof moduleConfig.configSchema === "object" && !Array.isArray(moduleConfig.configSchema)
                ? moduleConfig.configSchema
                : moduleConfig.config_schema && typeof moduleConfig.config_schema === "object" && !Array.isArray(moduleConfig.config_schema)
                ? moduleConfig.config_schema
                : {},
              configDefaults: moduleConfig.configDefaults && typeof moduleConfig.configDefaults === "object" && !Array.isArray(moduleConfig.configDefaults)
                ? moduleConfig.configDefaults
                : moduleConfig.config_defaults && typeof moduleConfig.config_defaults === "object" && !Array.isArray(moduleConfig.config_defaults)
                ? moduleConfig.config_defaults
                : {},
            },
          ]
        })
        .filter(([name, moduleConfig]) => name && String(moduleConfig.source || "").trim()),
    ),
    modules: Array.isArray(incomingConfig.modules)
      ? incomingConfig.modules
        .map((item) => ({
          name: String(item?.name || "").trim().toLowerCase(),
          config: item?.config && typeof item.config === "object" && !Array.isArray(item.config) ? item.config : {},
        }))
        .filter((item) => item.name)
      : [],
  })
  sanitizeForSubmitRef.current = sanitizeForSubmit

  const clearBuilderBatchQueue = () => {
    setBatchConfigs([])
    setEditingBatchId("")
    setEditingOriginalConfig(null)
    if (typeof window === "undefined") return
    window.sessionStorage.removeItem(SERVICE_BUILDER_UPLOADED_BATCH_STORAGE_KEY)
    window.sessionStorage.removeItem(BUILDER_EDIT_REQUEST_KEY)
    window.sessionStorage.removeItem(BUILDER_EDIT_RESULT_KEY)
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

  const applyGenerationStartPreference = async (processId, serviceName) => {
    const normalizedProcessId = String(processId || "").trim()
    if (startServicesAfterGeneration || !normalizedProcessId) {
      return "RUNNING"
    }

    const response = await fetch(`${LIWIRO_BACKEND}/services/${encodeURIComponent(normalizedProcessId)}/stop`, {
      method: "POST",
      headers: authHeaders(),
    })
    if (response.status === 401) {
      window.location.href = "/login"
      throw new Error("Authentication required")
    }
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(
        data?.error
          || data?.message
          || `Service '${serviceName}' was generated, but failed to stop automatically.`,
      )
    }
    return "NOT_RUNNING"
  }

  const resolveAuthSetupForPayload = async (payload, existingServices, sharedAuthSelection = null) => {
    const clonedPayload = JSON.parse(JSON.stringify(payload || {}))
    const endpointMap = clonedPayload?.endpoints || {}
    const hasProtectedRoutes = Object.values(endpointMap).some((ep) => Boolean(ep?.requiresAuth))
    const isAuthService = Boolean(clonedPayload?.auth?.isAuthService)
    const explicitAuthConsumer = Boolean(clonedPayload?.auth?.enabled) && Boolean(clonedPayload?.auth?.useAsymmetricJWT) && !isAuthService
    const needsExternalAuth = (hasProtectedRoutes && !isAuthService) || explicitAuthConsumer
    if (!needsExternalAuth) {
      return { payload: clonedPayload, selectedAuthService: sharedAuthSelection, applyForAll: true }
    }

    const authServices = (Array.isArray(existingServices) ? existingServices : []).filter(
      (svc) => Boolean(svc?.lapis_config?.auth?.isAuthService),
    )
    if (authServices.length === 0) {
      throw new Error("No authentication service exists. Create an authentication service before creating protected routes.")
    }

    clonedPayload.auth = {
      ...(clonedPayload.auth || {}),
      enabled: true,
      useAsymmetricJWT: true,
      keyManagement: String(clonedPayload?.auth?.keyManagement || "").trim() || "auto",
    }

    let selectedAuthService = sharedAuthSelection
    const configuredName = String(clonedPayload?.auth?.authServiceName || "").trim()
    if (configuredName) {
      selectedAuthService = authServices.find(
        (svc) => String(svc?.apiName || "").trim().toLowerCase() === configuredName.toLowerCase(),
      ) || null
      if (!selectedAuthService) {
        throw new Error(`Configured authentication service '${configuredName}' was not found. Select a valid authentication service.`)
      }
    } else if (selectedAuthService && selectedAuthService.apiName) {
      const serviceName = String(selectedAuthService.apiName || "").trim().toLowerCase()
      selectedAuthService = authServices.find((svc) => String(svc?.apiName || "").trim().toLowerCase() === serviceName) || null
    }

    let applyForAll = true
    if (!selectedAuthService) {
      const choice = await chooseAuthServiceWithPrompt(authServices)
      if (!choice?.selected?.apiName) {
        throw new Error("Authentication service selection is required for this service.")
      }
      selectedAuthService = choice.selected
      applyForAll = Boolean(choice.applyAll)
    }

    clonedPayload.auth.authServiceName = String(selectedAuthService.apiName || "")
    const selectedAuthCfg = selectedAuthService?.lapis_config?.auth || {}
    const selectedPublicKey = String(selectedAuthCfg?.publicKey || selectedAuthCfg?.authServicePublicKey || "").trim()
    if (selectedPublicKey && !String(clonedPayload?.auth?.authServicePublicKey || "").trim()) {
      clonedPayload.auth.authServicePublicKey = selectedPublicKey
    }

    return {
      payload: clonedPayload,
      selectedAuthService,
      applyForAll,
    }
  }

  const generateService = async () => {
    try {
      setSubmitError("")
      const validationError = getConfigValidationError(config)
      if (validationError) {
        throw new Error(validationError)
      }
      const serviceName = String(config?.metadata?.apiName || "").trim()
      const data = await generateServiceFromConfig(config)
      const finalStatus = await applyGenerationStartPreference(data?.process_id || data?.processId, serviceName)
      clearBuilderBatchQueue()
      toast.success(
        finalStatus === "NOT_RUNNING"
          ? `Service '${serviceName}' generated and left stopped`
          : (data.message || "Service generated successfully"),
      )
      const processId = String(data?.process_id || data?.processId || "").trim()
      if (processId) {
        router.replace(`/services/${encodeURIComponent(processId)}`)
        return
      }
      router.push("/services")
    } catch (error) {
      console.error("Error generating service:", error);
      const message = sanitizeGenerateErrorMessage(error?.message, "Error generating service")
      if (message.includes("RBAC authorization failed")) {
        setSubmitError(
          "Authorization failed while creating the service. Sign out, sign in again with super-admin credentials, and verify Liwiro Domain/DB in login setup."
        )
      } else if (message.includes("Authentication failed")) {
        setSubmitError(
          "Service startup authentication failed. Verify service auth settings/credentials and ensure backend DB connection credentials are valid."
        )
      } else {
        setSubmitError(message)
      }
      toast.error("Service generation failed")
    }
  };

  const generateServiceFromConfig = async (rawConfig) => {
    const normalizedConfig = normalizeConfig(rawConfig)
    const validationError = getConfigValidationError(normalizedConfig)
    if (validationError) {
      throw new Error(validationError)
    }
    let payload = sanitizeForSubmit(normalizedConfig)
    const validation = await prepareConfigForUploadWorkflow(normalizedConfig)
    if (!validation?.ok) {
      throw new Error(bestLapisIssueMessage(validation, "LAPIS validation is invalid. Service generation is blocked until it is fixed."))
    }
    payload = sanitizeForSubmit(normalizeConfig(validation?.normalized || normalizedConfig))
    const serviceName = String(payload?.metadata?.apiName || "").trim()
    if (!serviceName) {
      throw new Error("Service name is required")
    }

    const existingServicesUrl = new URL(`${LIWIRO_BACKEND}/services`)
    existingServicesUrl.searchParams.set("refresh", "0")
    const existingResponse = await fetch(existingServicesUrl.toString(), { headers: authHeaders() })
    let existingServices = []
    if (existingResponse.ok) {
      existingServices = await existingResponse.json()
      const hasCollision = Array.isArray(existingServices) && existingServices.some(
        (service) => String(service?.apiName || "").trim().toLowerCase() === serviceName.toLowerCase(),
      )
      if (hasCollision) {
        throw new Error(`Service name '${serviceName}' already exists. Use a unique name.`)
      }
    }
    const resolved = await resolveAuthSetupForPayload(payload, existingServices, null)
    payload = resolved.payload

    const response = await fetch(`${LIWIRO_BACKEND}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
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
      const backendError = data?.error || data?.message || text || "Failed to generate service"
      throw new Error(backendError)
    }
    return data
  }
  generateServiceFromConfigRef.current = generateServiceFromConfig

  const handleLapisUpload = async (event) => {
    const files = Array.from(event.target.files || [])
    if (files.length === 0) return
    const loaded = []
    let firstLoadedConfig = null
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
      const itemId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      try {
        if (uploadProgressEnabled) {
          updateUploadOperation({
            current: file.name,
            detail: `Processing ${file.name}`,
          })
        }
        const text = await file.text()
        const parsed = JSON.parse(text)
        const normalized = normalizeConfig(parsed)
        const apiName = String(normalized?.metadata?.apiName || "").trim() || file.name
        const validation = await prepareConfigForUploadWorkflow(normalized)
        const queuedConfig = normalizeConfig(validation?.normalized || normalized)
        const ready = Boolean(validation?.ok || validation?.finalStatus === "ready")
        const status = ready ? "ready" : (String(validation?.finalStatus || "").trim() || "needs-manual-fix")
        const error = ready ? "" : bestLapisIssueMessage(validation, "LAPIS validation is invalid.")
        const nextItem = {
          id: itemId,
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
        }
        loaded.push(nextItem)
        if (!firstLoadedConfig && queuedConfig) firstLoadedConfig = queuedConfig
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
          id: itemId,
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
    if (loaded.length === 1 && loaded[0]?.config) {
      setEditingBatchId(String(loaded[0].id))
      setEditingOriginalConfig(normalizeConfig(loaded[0].config))
    }
    if (firstLoadedConfig) {
      setConfig(firstLoadedConfig)
    }
    if (readyCount > 0) {
      toast.success(
        repairedCount > 0
          ? `${readyCount} LAPIS file${readyCount > 1 ? "s" : ""} ready, ${repairedCount} auto-repaired`
          : `${readyCount} LAPIS file${readyCount > 1 ? "s" : ""} loaded`,
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
          title: repairedCount > 0 ? "LAPIS batch repaired and ready" : "LAPIS batch ready",
          detail:
            repairedCount > 0
              ? `${readyCount} file${readyCount === 1 ? "" : "s"} are ready. ${repairedCount} received deterministic repairs.`
              : `${readyCount} file${readyCount === 1 ? "" : "s"} are ready for generation.`,
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
    const readyItems = batchConfigs
      .filter((item) => item.status === "ready" && item.config)
      .map((item) => {
        if (editingBatchId && String(item.id) === String(editingBatchId)) {
          return { ...item, config: sanitizeForSubmit(normalizeConfig(config)) }
        }
        return item
      })
    if (readyItems.length === 0) {
      toast.error("No valid LAPIS files ready for generation")
      return
    }

    setBatchGenerating(true)
    setBatchConfigs((prev) => prev.map((item) => (
      item.status === "ready" ? { ...item, status: "pending", error: "" } : item
    )))

    let successCount = 0
    let failCount = 0
    let singleGeneratedProcessId = ""
    const servicesUrl = new URL(`${LIWIRO_BACKEND}/services`)
    servicesUrl.searchParams.set("refresh", "0")
    const servicesResponse = await fetch(servicesUrl.toString(), { headers: authHeaders() }).catch(() => null)
    const existingServices = servicesResponse?.ok ? await servicesResponse.json().catch(() => []) : []
    const availableServices = Array.isArray(existingServices) ? [...existingServices] : []
    const existingNames = new Set(
      (Array.isArray(existingServices) ? existingServices : []).map((svc) => String(svc?.apiName || "").trim().toLowerCase()).filter(Boolean),
    )
    let sharedAuthSelection = null

    for (const item of readyItems) {
      setBatchConfigs((prev) => prev.map((entry) => (
        entry.id === item.id ? { ...entry, status: "running", error: "" } : entry
      )))
      try {
        let payload = sanitizeForSubmit(normalizeConfig(item.config || {}))
        const serviceName = String(payload?.metadata?.apiName || "").trim()
        if (!serviceName) {
          throw new Error("Service name is required")
        }
        if (existingNames.has(serviceName.toLowerCase())) {
          throw new Error(`Service name '${serviceName}' already exists. Use a unique name.`)
        }
        const resolved = await resolveAuthSetupForPayload(payload, availableServices, sharedAuthSelection)
        payload = resolved.payload
        if (resolved.selectedAuthService && resolved.applyForAll) {
          sharedAuthSelection = resolved.selectedAuthService
        } else if (!resolved.applyForAll) {
          sharedAuthSelection = null
        }
        const generated = await generateServiceFromConfig(payload)
        const generatedProcessId = String(generated?.process_id || generated?.processId || "").trim()
        if (!singleGeneratedProcessId && generatedProcessId) {
          singleGeneratedProcessId = generatedProcessId
        }
        const finalStatus = await applyGenerationStartPreference(generatedProcessId, serviceName)
        availableServices.push({
          apiName: serviceName,
          lapis_config: payload,
          status: finalStatus,
        })
        existingNames.add(serviceName.toLowerCase())
        successCount += 1
        setBatchConfigs((prev) => prev.map((entry) => (
          entry.id === item.id ? { ...entry, status: "success", error: "" } : entry
        )))
      } catch (error) {
        failCount += 1
        setBatchConfigs((prev) => prev.map((entry) => (
          entry.id === item.id ? { ...entry, status: "failed", error: error?.message || "Failed to generate" } : entry
        )))
      }
    }

    setBatchGenerating(false)
    if (successCount > 0) {
      clearBuilderBatchQueue()
      toast.success(`Generated ${successCount} service${successCount > 1 ? "s" : ""}`)
    }
    if (failCount > 0) {
      toast.error(`${failCount} service${failCount > 1 ? "s" : ""} failed`)
    }
    if (successCount === 1 && singleGeneratedProcessId) {
      router.replace(`/services/${encodeURIComponent(singleGeneratedProcessId)}`)
      return
    }
    if (successCount > 1) {
      router.replace("/services")
      return
    }
  }

  const removeBatchConfig = (id) => {
    setBatchConfigs((prev) => prev.filter((item) => item.id !== id))
    if (editingBatchId === id) {
      setEditingBatchId("")
      setEditingOriginalConfig(null)
    }
  }

  const isCurrentConfigValid = () => !getConfigValidationError(config)

  const startBatchItemEdit = (item) => {
    if (!item?.config) return
    if (editingBatchId && String(editingBatchId) !== String(item.id) && !commitCurrentBatchEdit()) {
      return
    }
    setEditingBatchId(String(item.id))
    setEditingOriginalConfig(normalizeConfig(item.config))
    setConfig(normalizeConfig(item.config))
    setSubmitError("")
    setActiveTab("config")
    if (typeof window !== "undefined") {
      window.scrollTo({ top: 0, behavior: "smooth" })
    }
  }

  const cancelBatchItemEdit = () => {
    if (editingOriginalConfig) {
      setConfig(normalizeConfig(editingOriginalConfig))
    }
    setEditingBatchId("")
    setEditingOriginalConfig(null)
  }

  const saveBatchItemChanges = async () => {
    if (!editingBatchId || !isCurrentConfigValid()) return
    try {
      let normalized = sanitizeForSubmit(normalizeConfig(config))
      const validation = await prepareConfigForUploadWorkflow(normalized)
      if (!validation?.ok) {
        throw new Error(bestLapisIssueMessage(validation, "LAPIS validation is invalid."))
      }
      normalized = sanitizeForSubmit(normalizeConfig(validation?.normalized || normalized))
      const apiName = String(normalized?.metadata?.apiName || "").trim()
      setBatchConfigs((prev) => prev.map((item) => (
        String(item.id) === String(editingBatchId)
          ? { ...item, config: normalized, apiName: apiName || item.apiName, status: "ready", error: "" }
          : item
      )))
      setEditingOriginalConfig(normalizeConfig(normalized))
      toast.success("Batch item saved")
    } catch (error) {
      toast.error(error?.message || "Failed to validate the uploaded service config")
    }
  }

  const finishBatchItemEdit = () => {
    setEditingBatchId("")
    setEditingOriginalConfig(null)
  }

  const cancelExternalBatchEdit = () => {
    if (typeof window !== "undefined") {
      writeSessionJson(BUILDER_EDIT_RESULT_KEY, {
        cancelled: true,
        itemId: externalBatchEditId,
        source: externalBatchSource || "services-uploaded-list",
        storageKey: externalBatchStorageKey || getBatchStorageKeyForSource(externalBatchSource),
      })
      window.sessionStorage.removeItem(BUILDER_EDIT_REQUEST_KEY)
    }
    router.push(externalBatchReturnPath || getBatchReturnPathForSource(externalBatchSource))
  }

  const saveExternalBatchEdit = async () => {
    if (!externalBatchEditId || !isCurrentConfigValid() || typeof window === "undefined") return
    try {
      let normalized = sanitizeForSubmit(normalizeConfig(config))
      const validation = await prepareConfigForUploadWorkflow(normalized)
      if (!validation?.ok) {
        throw new Error(bestLapisIssueMessage(validation, "LAPIS validation is invalid."))
      }
      normalized = sanitizeForSubmit(normalizeConfig(validation?.normalized || normalized))
      const apiName = String(normalized?.metadata?.apiName || "").trim()
      if (!apiName) {
        throw new Error("Service name is required")
      }
      const batchStorageKey = externalBatchStorageKey || getBatchStorageKeyForSource(externalBatchSource)
      const batchItems = readSessionJson(batchStorageKey) || []
      if (!Array.isArray(batchItems)) {
        throw new Error("Uploaded services list is not available")
      }
      const nextBatchItems = batchItems.map((item) => (
        String(item?.id) === String(externalBatchEditId)
          ? { ...item, config: normalized, apiName, status: "ready", error: "" }
          : item
      ))
      writeSessionJson(batchStorageKey, nextBatchItems)
      writeSessionJson(BUILDER_EDIT_RESULT_KEY, {
        saved: true,
        itemId: externalBatchEditId,
        source: externalBatchSource || "services-uploaded-list",
        storageKey: batchStorageKey,
      })
      window.sessionStorage.removeItem(BUILDER_EDIT_REQUEST_KEY)
      toast.success("Uploaded service config saved")
      router.push(externalBatchReturnPath || getBatchReturnPathForSource(externalBatchSource))
    } catch (error) {
      toast.error(error?.message || "Failed to save uploaded service config")
    }
  }

  const moduleCatalogOptions = useMemo(() => {
    const sharedDraftModules = config?.sharedModules && typeof config.sharedModules === "object" && !Array.isArray(config.sharedModules)
      ? config.sharedModules
      : {}
    const availableNames = new Set(
      (Array.isArray(availableModules) ? availableModules : [])
        .map((module) => String(module?.name || "").trim().toLowerCase())
        .filter(Boolean),
    )
    return [
      ...(Array.isArray(availableModules) ? availableModules : []),
      ...Object.entries(sharedDraftModules)
        .filter(([name]) => !availableNames.has(String(name || "").trim().toLowerCase()))
        .map(([name, module]) => ({
          name,
          title: module?.title || name,
          description: module?.description || "Shared module defined in this draft",
          scope: module?.scope || "domain",
          assigned_domains: [],
        })),
    ]
  }, [availableModules, config?.sharedModules])

  const modelCount = Object.keys(config.models || {}).length
  const endpointCount = Object.keys(config.endpoints || {}).length
  const protectedEndpointCount = Object.values(config.endpoints || {}).filter((ep) => Boolean(ep?.requiresAuth)).length
  const hasApiName = Boolean(String(config?.metadata?.apiName || "").trim())
  const readyBatchCount = useMemo(
    () => batchConfigs.filter((item) => item.status === "ready").length,
    [batchConfigs],
  )
  const generateButtonLabel = externalBatchEditMode
    ? "Save Uploaded Service"
    : (startServicesAfterGeneration ? "Generate Service" : "Generate Service (Keep Stopped)")
  const getComparableConfigSignature = (candidateConfig) => {
    try {
      const normalize = normalizeConfigRef.current || normalizeConfig
      const sanitize = sanitizeForSubmitRef.current || sanitizeForSubmit
      return JSON.stringify(sanitize(normalize(candidateConfig || {})))
    } catch {
      return ""
    }
  }
  const editSnapshotSignature = useMemo(
    () => (editingOriginalConfig ? getComparableConfigSignature(editingOriginalConfig) : ""),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [editingOriginalConfig],
  )
  const currentConfigSignature = useMemo(
    () => getComparableConfigSignature(config),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [config],
  )
  const batchEditDirty = useMemo(
    () => Boolean(editingBatchId) && Boolean(editingOriginalConfig) && currentConfigSignature !== editSnapshotSignature,
    [currentConfigSignature, editSnapshotSignature, editingBatchId, editingOriginalConfig],
  )

  const getConfigValidationError = (candidateConfig = config) => {
    const nextConfig = candidateConfig || {}
    if (candidateConfig === config && configHasVersaScriptEndpoints(nextConfig)) {
      if (versaValidationState.pending) {
        return "Versa syntax validation is still running."
      }
      if (validationControl.blocked) {
        if (validationControl.shouldAskForHelp) {
          return "Versa validation is blocked. Ask for help or grant permission to keep working."
        }
        return "Versa validation is paused until you allow it to continue or reset the validation count."
      }
      if (String(versaValidationState.error || "").trim()) {
        return String(versaValidationState.error || "").trim()
      }
    }
    const apiName = String(nextConfig?.metadata?.apiName || "").trim()
    const basePath = String(nextConfig?.metadata?.basePath || "").trim()
    const version = String(nextConfig?.metadata?.version || "").trim()
    if (!apiName || !basePath || !version) {
      return "Service metadata requires apiName, basePath, and version."
    }

    const modelNames = new Set()
    for (const model of Object.values(nextConfig?.models || {})) {
      const modelName = String(model?.name || "").trim()
      const collectionName = String(model?.collection || "").trim()
      if (!modelName || !collectionName) {
        return "Each model requires both a name and a collection."
      }
      modelNames.add(modelName)

      for (const field of Object.values(model?.fields || {})) {
        if (!String(field?.id || "").trim() || !String(field?.name || "").trim() || !String(field?.type || "").trim()) {
          return `Model '${modelName}' has a field missing id, name, or type.`
        }
      }
    }

    const moduleNames = new Set()
    for (const moduleEntry of Array.isArray(nextConfig?.modules) ? nextConfig.modules : []) {
      const moduleName = String(moduleEntry?.name || "").trim().toLowerCase()
      if (!moduleName) {
        return "Each attached VI module requires a name."
      }
      if (moduleNames.has(moduleName)) {
        return `Duplicate VI module '${moduleName}' in this service draft.`
      }
      if (moduleEntry?.config != null && (!moduleEntry.config || typeof moduleEntry.config !== "object" || Array.isArray(moduleEntry.config))) {
        return `VI module '${moduleName}' requires a JSON object config override.`
      }
      moduleNames.add(moduleName)
    }

    for (const [endpointId, endpoint] of Object.entries(nextConfig?.endpoints || {})) {
      const endpointLabel = String(endpoint?.path || endpointId || "").trim() || String(endpointId || "endpoint")
      const operationType = normalizeOperationType(endpoint?.operationType)
      if (!String(endpoint?.method || "").trim() || !String(endpoint?.path || "").trim() || !operationType) {
        return `Endpoint '${endpointLabel}' requires method, path, and operation type.`
      }
      if (operationType === "crud") {
        const crudOperation = normalizeCrudOperation(endpoint?.crudOperation)
        const linkedModel = String(endpoint?.linkedModel || "").trim()
        if (!crudOperation || !linkedModel) {
          return `CRUD endpoint '${endpointLabel}' requires both a linked model and CRUD operation.`
        }
        if (modelNames.size > 0 && !modelNames.has(linkedModel)) {
          return `CRUD endpoint '${endpointLabel}' references unknown model '${linkedModel}'.`
        }
      }
      if (operationType === "custom") {
        const queryText = String(endpoint?.vqlQuery || "").trim()
        if (!queryText) {
          return `Custom VQL endpoint '${endpointLabel}' requires a readable VDB command.`
        }
        if (/^[{[]/.test(queryText)) {
          return `Custom VQL endpoint '${endpointLabel}' cannot use a JSON command object.`
        }
      }
      if (operationType === "script" && !String(endpoint?.versaScript || "").trim()) {
        return `Versa endpoint '${endpointLabel}' requires script content.`
      }
    }

    return ""
  }

  const currentConfigValidationError = useMemo(
    () => getConfigValidationError(config),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      config,
      validationControl.blocked,
      validationControl.shouldAskForHelp,
      versaValidationState.error,
      versaValidationState.pending,
    ],
  )

  useEffect(() => {
    const normalize = normalizeConfigRef.current
    const sanitize = sanitizeForSubmitRef.current
    const hasVersaScripts = configHasVersaScriptEndpointsRef.current
    const normalizedCandidate = sanitize(normalize(config))
    if (!hasVersaScripts(normalizedCandidate)) {
      setVersaValidationState({ error: "", versaIssues: [], endpointErrors: {}, pending: false })
      setValidationControl({
        attemptCount: 0,
        resetCount: validationControl.resetCount,
        continueApproved: false,
        blocked: false,
        timedOut: false,
        thresholdReached: false,
        shouldAskForHelp: false,
      })
      versaValidationSignatureRef.current = ""
      return undefined
    }
    if (validationControl.blocked) {
      return undefined
    }

    let active = true
    setVersaValidationState((current) => ({ ...current, pending: true }))
    const timer = window.setTimeout(async () => {
      try {
        const result = await validateConfigWithBackend(normalizedCandidate)
        if (!active) return
        const nextValidationControl = {
          attemptCount: Number(result?.validationState?.attemptCount || 0),
          resetCount: Number(result?.validationState?.resetCount || 0),
          continueApproved: Boolean(result?.validationState?.continueApproved),
          blocked: Boolean(result?.validationState?.requiresPermission),
          timedOut: Boolean(result?.validationState?.timedOut),
          thresholdReached: Boolean(result?.validationState?.thresholdReached),
          shouldAskForHelp: Boolean(result?.validationState?.shouldAskForHelp),
        }
        const nextState = {
          error: String(result?.error || "").trim(),
          versaIssues: Array.isArray(result?.versaIssues) ? result.versaIssues : [],
          endpointErrors: result?.endpointErrors && typeof result.endpointErrors === "object" ? result.endpointErrors : {},
          pending: false,
        }
        setVersaValidationState(nextState)
        setValidationControl(nextValidationControl)
        if (nextValidationControl.blocked) {
          setValidationDialogOpen(true)
        }
        const signature = JSON.stringify(nextState.versaIssues.map((item) => [item?.endpointId, item?.error]))
        if (nextState.versaIssues.length > 0 && signature !== versaValidationSignatureRef.current) {
          toast.error("Versa syntax is wrong. Service generation is blocked until it is fixed.")
          versaValidationSignatureRef.current = signature
        }
        if (!nextState.versaIssues.length) {
          versaValidationSignatureRef.current = ""
        }
      } catch (error) {
        if (!active) return
        const message = String(error?.message || "Failed to validate Versa syntax.").trim()
        setVersaValidationState({ error: message, versaIssues: [], endpointErrors: {}, pending: false })
        setValidationControl((current) => ({
          ...current,
          blocked: true,
          timedOut: /timed out/i.test(message),
          thresholdReached: true,
        }))
        setValidationDialogOpen(true)
        if (versaValidationSignatureRef.current !== `transport:${message}`) {
          toast.error(message)
          versaValidationSignatureRef.current = `transport:${message}`
        }
      }
    }, 450)

    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [config, validateConfigWithBackend, validationControl.blocked, validationControl.resetCount, validationResumeToken])

  const commitCurrentBatchEdit = ({ silent = false } = {}) => {
    if (!editingBatchId) return true
    const validationError = getConfigValidationError(config)
    if (validationError) {
      if (!silent) {
        toast.error("Fix the current uploaded service config or cancel before switching to another queued service.")
      }
      return false
    }
    const normalized = sanitizeForSubmit(normalizeConfig(config))
    const apiName = String(normalized?.metadata?.apiName || "").trim()
    setBatchConfigs((prev) => prev.map((item) => (
      String(item.id) === String(editingBatchId)
        ? { ...item, config: normalized, apiName: apiName || item.apiName, status: "ready", error: "" }
        : item
    )))
    return true
  }

  const switchEditorMode = (nextMode) => {
    setEditorMode(nextMode)
    if (nextMode === "text") {
      setRawConfigText(JSON.stringify(config, null, 2))
      setRawConfigError("")
    }
  }

  const handleRawConfigChange = (value) => {
    setRawConfigText(value)
    try {
      const parsed = value.trim() ? parseJsonLikeText(value) : {}
      if (!isPlainObject(parsed)) {
        throw new Error("LAPIS config must be a JSON object")
      }
      setConfig(normalizeConfig(parsed))
      setRawConfigError("")
    } catch (error) {
      setRawConfigError(error?.message || "Invalid JSON")
    }
  }

  const continueValidationWork = () => {
    setValidationDialogOpen(false)
    setValidationControl((current) => ({
      ...current,
      blocked: false,
      continueApproved: true,
      shouldAskForHelp: false,
    }))
    setValidationResumeToken((current) => current + 1)
  }

  const resetValidationCount = () => {
    setValidationDialogOpen(false)
    setValidationControl((current) => ({
      ...current,
      attemptCount: 0,
      resetCount: Number(current.resetCount || 0) + 1,
      continueApproved: true,
      blocked: false,
      thresholdReached: false,
      shouldAskForHelp: false,
      timedOut: false,
    }))
    setValidationResumeToken((current) => current + 1)
  }

  const askForValidationHelp = () => {
    setValidationDialogOpen(false)
    setValidationControl((current) => ({
      ...current,
      blocked: true,
      continueApproved: false,
      shouldAskForHelp: true,
    }))
    setSubmitError("Versa validation is blocked. If you want me to keep coding, please allow a reset or help unblock the failing script.")
  }

  return (
    <div className="w-full app-stack">
      <section className="app-hero">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <Button
              type="button"
              variant="outline"
              className="mb-4 h-9"
              onClick={() => {
                if (typeof window !== "undefined" && window.history.length > 1) {
                  router.back()
                  return
                }
                router.push("/services")
              }}
            >
              <ArrowLeft className="mr-1 h-4 w-4" /> Back
            </Button>
            <p className="app-eyebrow">Service Builder</p>
            <h1 className="app-title mt-4">Compose LAPIS services in a guided studio</h1>
            <p className="app-copy mt-3">Define metadata, auth, models, and endpoints, then generate a runnable service without leaving the workspace.</p>
            <div className="mt-5 flex flex-wrap gap-2">
              <span className="rounded-full border border-slate-200/90 bg-white/[0.88] px-3 py-1 text-xs font-medium text-slate-700 dark:border-slate-800 dark:bg-slate-950/[0.72] dark:text-slate-200">
                {hasApiName ? `API: ${config.metadata.apiName}` : "API name not set"}
              </span>
              <span className="rounded-full border border-slate-200/90 bg-white/[0.88] px-3 py-1 text-xs font-medium text-slate-700 dark:border-slate-800 dark:bg-slate-950/[0.72] dark:text-slate-200">
                {modelCount} model{modelCount === 1 ? "" : "s"}
              </span>
              <span className="rounded-full border border-slate-200/90 bg-white/[0.88] px-3 py-1 text-xs font-medium text-slate-700 dark:border-slate-800 dark:bg-slate-950/[0.72] dark:text-slate-200">
                {endpointCount} endpoint{endpointCount === 1 ? "" : "s"}
              </span>
              <span className="rounded-full border border-slate-200/90 bg-white/[0.88] px-3 py-1 text-xs font-medium text-slate-700 dark:border-slate-800 dark:bg-slate-950/[0.72] dark:text-slate-200">
                {config.auth.enabled ? "Auth enabled" : "Auth disabled"}
                {protectedEndpointCount > 0 ? ` • ${protectedEndpointCount} protected` : ""}
              </span>
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button
              type="button"
              variant="outline"
              size="lg"
              className="h-11 rounded-xl px-5"
              onClick={() => setActiveTab("preview")}
            >
              Preview Config
            </Button>
            {externalBatchEditMode && (
              <Button
                type="button"
                variant="outline"
                size="lg"
                className="h-11 rounded-xl px-5"
                onClick={cancelExternalBatchEdit}
              >
                Cancel
              </Button>
            )}
            <Button
              onClick={externalBatchEditMode ? saveExternalBatchEdit : generateService}
              size="lg"
              className="brand-solid h-11 rounded-xl px-6 font-semibold shadow-lg shadow-primary/25"
              disabled={!isCurrentConfigValid()}
            >
              {generateButtonLabel}
            </Button>
          </div>
        </div>
      </section>

      <div className="space-y-6">
        {uploadProgressEnabled && uploadOperationStatus?.visible ? (
          <OperationStatusPanel status={uploadOperationStatus} />
        ) : null}
        <div className="grid gap-6 xl:grid-cols-3">
          <Card className="xl:col-span-2">
            <CardHeader>
              <CardTitle>Builder Snapshot</CardTitle>
              <p className="text-sm text-slate-400">
                Work from top to bottom: metadata, auth, models, endpoints, then preview the generated config before you save.
              </p>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-[1.15rem] border border-slate-200/80 bg-white/[0.84] p-4 dark:border-slate-800 dark:bg-slate-950/[0.68]">
                <p className="app-stat-label">Structure</p>
                <p className="mt-1 text-lg font-semibold text-slate-950 dark:text-slate-50">{modelCount} models • {endpointCount} endpoints</p>
              </div>
              <div className="rounded-[1.15rem] border border-slate-200/80 bg-white/[0.84] p-4 dark:border-slate-800 dark:bg-slate-950/[0.68]">
                <p className="app-stat-label">Security</p>
                <p className="mt-1 text-lg font-semibold text-slate-950 dark:text-slate-50">{config.auth.enabled ? "Auth configured" : "Public service"}</p>
              </div>
            </CardContent>
          </Card>

          {!externalBatchEditMode && (
            <Card>
              <CardHeader>
                <CardTitle>Import</CardTitle>
                <p className="text-sm text-slate-400">
                  Preload configuration from existing `.lapis` or `.json` files and continue editing here.
                </p>
              </CardHeader>
              <CardContent>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".json,.lapis"
                  onChange={handleLapisUpload}
                  className="hidden"
                />
                <Button
                  type="button"
                  variant="outline"
                  className="h-10 w-full"
                  onClick={() => fileInputRef.current?.click()}
                >
                  Choose File(s)
                </Button>
              </CardContent>
            </Card>
          )}
        </div>

        {!externalBatchEditMode && batchConfigs.length > 0 && (
          <div className="app-card-soft p-5">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="app-section-label">Batch</p>
                <h2 className="mt-2 text-lg font-semibold text-slate-950 dark:text-slate-50">Queued Services</h2>
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                  {readyBatchCount} ready of {batchConfigs.length} uploaded configuration{batchConfigs.length === 1 ? "" : "s"}.
                </p>
              </div>
              <Button
                type="button"
                onClick={runBatchGenerate}
                disabled={batchGenerating || readyBatchCount === 0}
                className="brand-solid h-10"
              >
                {batchGenerating ? "Generating..." : "Generate All Ready Services"}
              </Button>
            </div>
            <div className="mt-4 grid gap-2 xl:grid-cols-2">
              {batchConfigs.map((item) => (
                <div
                  key={item.id}
                  className={`rounded-[1.05rem] border px-3 py-3 text-sm ${item.status !== "ready" ? "border-amber-300 bg-amber-50/70 dark:border-amber-700/70 dark:bg-amber-950/20" : "border-slate-200/[0.85] bg-white/[0.86] dark:border-slate-800 dark:bg-slate-950/[0.68]"}`}
                >
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <span className="font-medium text-slate-900 dark:text-slate-100">{item.apiName}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-300">{item.status}</span>
                      <button
                        type="button"
                        aria-label={`Edit ${item.fileName}`}
                        className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-slate-300 text-slate-500 hover:bg-slate-100 hover:text-slate-800 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-900 dark:hover:text-slate-100"
                        onClick={() => startBatchItemEdit(item)}
                        disabled={batchGenerating || item.status === "running" || !item.config}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        aria-label={`Remove ${item.fileName}`}
                        className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-slate-300 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-900 dark:hover:text-slate-100"
                        onClick={() => removeBatchConfig(item.id)}
                        disabled={batchGenerating || item.status === "running"}
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                  <p className="text-xs text-slate-500 dark:text-slate-300">{item.fileName}</p>
                  {item.progressMessage ? (
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-300">{item.progressMessage}</p>
                  ) : null}
                  {item.repaired ? (
                    <p className="mt-1 text-xs text-emerald-700 dark:text-emerald-300">
                      Auto-repaired with {Array.isArray(item.appliedFixes) ? item.appliedFixes.length : 0} deterministic fix{Array.isArray(item.appliedFixes) && item.appliedFixes.length === 1 ? "" : "es"}.
                    </p>
                  ) : null}
                  {item.error ? <LapisUploadError error={item.error} /> : null}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="w-full">
      {editingBatchId && (
        <div className="fixed bottom-4 right-4 z-50 flex items-center gap-2 rounded-xl border border-slate-300 bg-white/95 p-3 shadow-xl backdrop-blur dark:border-slate-700 dark:bg-slate-900/95">
          <Button
            type="button"
            className="brand-solid h-9"
            onClick={batchEditDirty ? saveBatchItemChanges : finishBatchItemEdit}
            disabled={batchEditDirty && !isCurrentConfigValid()}
          >
            {batchEditDirty ? "Save Batch Changes" : "Done"}
          </Button>
          <Button
            type="button"
            variant="outline"
            className="h-9"
            onClick={cancelBatchItemEdit}
          >
            {batchEditDirty ? "Cancel" : "Close"}
          </Button>
        </div>
      )}
      <TransientSuccessDialog
        status={uploadOperationStatus}
        onOpenChange={(open) => {
          if (!open && uploadOperationStatus?.presentation === "modal") {
            clearUploadOperation()
          }
        }}
      />
      {externalBatchEditMode && (
        <div className="fixed bottom-4 right-4 z-50 flex items-center gap-2 rounded-xl border border-slate-300 bg-white/95 p-3 shadow-xl backdrop-blur dark:border-slate-700 dark:bg-slate-900/95">
          <Button
            type="button"
            className="brand-solid h-9"
            onClick={saveExternalBatchEdit}
            disabled={!isCurrentConfigValid()}
          >
            Save Uploaded Service
          </Button>
          <Button
            type="button"
            variant="outline"
            className="h-9"
            onClick={cancelExternalBatchEdit}
          >
            Cancel
          </Button>
        </div>
      )}

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="flex w-full justify-start gap-2">
          <TabsTrigger value="config">Configuration</TabsTrigger>
          <TabsTrigger value="preview">Preview</TabsTrigger>
        </TabsList>

        <TabsContent value="config" className="mt-6">
          <div className="mb-4 flex flex-col gap-3 rounded-[1.35rem] border border-white/10 bg-white/5 px-4 py-4 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="app-section-label">Editor Mode</p>
              <p className="mt-1 text-sm text-slate-300">
                Switch between guided forms and raw LAPIS JSON. Valid JSON changes update the same builder state used by structured mode.
              </p>
            </div>
            <ModeToggle value={editorMode} onChange={switchEditorMode} />
          </div>
          {editorMode === "structured" ? (
            <div className="grid gap-8">
              <MetadataConfig config={config} updateConfig={updateConfig} />
              <AuthConfig
                config={config}
                updateConfig={updateConfig}
                hasAuthModel={hasAuthModel}
              />
              <ModelConfig
                config={config}
                addModel={addModel}
                removeModel={removeModel}
                updateConfig={updateConfig}
              />
              <SharedModuleConfig
                config={config}
                updateConfig={updateConfig}
                serviceDomain={config?.metadata?.apiName}
              />
              <ModuleConfig
                config={config}
                availableModules={moduleCatalogOptions}
                availableDomains={availableModuleDomains}
                loading={modulesLoading}
                refreshCatalog={loadModulesCatalog}
                onAttachModule={attachModuleToService}
                updateConfig={updateConfig}
              />
              <EndpointConfig
                config={config}
                addEndpoint={addEndpoint}
                removeEndpoint={removeEndpoint}
                updateConfig={updateConfig}
                models={config.models}
                availableModules={availableModules}
                attachedModules={config.modules || []}
                versaEndpointErrors={versaValidationState.endpointErrors}
              />

              <div className="flex justify-end">
                {externalBatchEditMode && (
                  <Button
                    type="button"
                    variant="outline"
                    size="lg"
                    className="mr-3 h-12 rounded-xl px-8"
                    onClick={cancelExternalBatchEdit}
                  >
                    Cancel
                  </Button>
                )}
                <Button
                  onClick={externalBatchEditMode ? saveExternalBatchEdit : generateService}
                  size="lg"
                  className="brand-solid h-12 w-full rounded-xl px-8 font-semibold shadow-lg shadow-primary/25 md:w-auto"
                  disabled={!isCurrentConfigValid()}
                >
                  {generateButtonLabel}
                </Button>
              </div>
              {(submitError || currentConfigValidationError) && (
                <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{submitError || currentConfigValidationError}</span>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-5">
              <div className="rounded-[1.35rem] border border-white/10 bg-white/5 p-4">
                <p className="app-section-label">Raw LAPIS Editor</p>
                <p className="mt-2 text-sm text-slate-300">
                  Edit the full service definition as JSON. Valid edits sync back into the structured builder, preview, and generation flow immediately.
                </p>
              </div>
              <IDECodeEditor
                value={rawConfigText}
                onChange={handleRawConfigChange}
                language="json"
                validateJson
                error={rawConfigError}
                minHeight="34rem"
                status={hasApiName ? `Editing ${config.metadata.apiName}` : "Editing unsaved service"}
                placeholder='{"metadata":{},"auth":{},"models":{},"endpoints":{}}'
              />
              <div className="flex flex-wrap justify-end gap-3">
                <Button variant="outline" onClick={() => setRawConfigText(JSON.stringify(config, null, 2))}>
                  Reset from Builder State
                </Button>
                <Button
                  onClick={externalBatchEditMode ? saveExternalBatchEdit : generateService}
                  size="lg"
                  className="brand-solid"
                  disabled={Boolean(rawConfigError) || !isCurrentConfigValid()}
                >
                  {generateButtonLabel}
                </Button>
              </div>
              {(submitError || currentConfigValidationError) && (
                <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{submitError || currentConfigValidationError}</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </TabsContent>

        <TabsContent value="preview" className="mt-6">
          <PreviewConfig config={config} setActiveTab={setActiveTab} />
        </TabsContent>
      </Tabs>
      <AlertDialog
        open={validationDialogOpen}
        onOpenChange={setValidationDialogOpen}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Versa Validation Needs Permission</AlertDialogTitle>
            <AlertDialogDescription>
              {validationControl.shouldAskForHelp
                ? "Validation has hit the retry threshold. If you want me to keep working, I need your permission to reset the validation count or your help with the blocking script."
                : validationControl.timedOut
                ? "Versa validation timed out. I paused instead of looping. You can let me continue, reset the validation count, or stop here and help unblock it."
                : "Versa validation reached the current retry threshold. I paused instead of continuing in a dead end. You can let me continue, reset the validation count, or stop and help unblock it."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={askForValidationHelp}>Ask for Help</AlertDialogCancel>
            <Button type="button" variant="outline" onClick={resetValidationCount}>
              Reset Count
            </Button>
            <AlertDialogAction onClick={continueValidationWork}>Continue Coding</AlertDialogAction>
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
            <label htmlFor="auth-service-select" className="text-sm font-medium">
              Authentication service
            </label>
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
        </div>
      </div>
    </div>
  )
}
