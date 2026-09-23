// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

"use client"

import { useEffect, useState, useCallback, useMemo } from "react"
import Link from "next/link"
import { authHeaders } from "@/lib/auth"
import { fetchAuthedJson, invalidateAuthedJsonCache } from "@/lib/authed-json-cache"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import VdbRbacAdmin from "@/components/vdb/vdb-rbac-admin"
import { VdbTransportStatusIndicator } from "@/components/vdb/vdb-transport-status-indicator"
import PasswordInput from "@/components/ui/password-input"
import { OperationStatusPanel } from "@/components/ui/operation-status-panel"
import { toast } from "sonner"
import { useOperationStatus } from "@/lib/operation-status"
import { useVdbConnectionStatus } from "@/lib/vdb-connection-status"
import { normalizeVdbNamedPipePath, vdbTransportLabel, vdbTransportTargetConfig } from "@/lib/vdb-transport"
import { fetchVerseBootstrap, invalidateVerseBootstrap } from "@/lib/verse-bootstrap"

const CREATE_ROLE_OPTIONS = [
  {
    value: "viewer",
    label: "Viewer",
    description: "Can view services and inspect runtime status.",
  },
  {
    value: "service_manager",
    label: "Service Manager",
    description: "Can view and operate services (start/stop/delete/generate).",
  },
  {
    value: "admin",
    label: "Admin",
    description: "Platform admin (non-super-admin). Gets full service access.",
  },
]

const PLATFORM_PERMISSION_OPTIONS = [
  {
    value: "VIEW_SERVICES",
    label: "View Services",
    description: "Read service list and details.",
  },
  {
    value: "MANAGE_SERVICES",
    label: "Manage Services",
    description: "Generate/start/stop/delete services.",
  },
]

const createPermissionDraftId = () => {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

const createPermissionDraft = (permission = {}) => ({
  draftId: createPermissionDraftId(),
  effect: String(permission?.effect || "ALLOW").trim().toUpperCase() === "DENY" ? "DENY" : "ALLOW",
  type: String(permission?.type || "SERVICE_ALL").trim().toUpperCase() || "SERVICE_ALL",
  service: String(permission?.service || ""),
  endpoint: String(permission?.endpoint || ""),
  model: String(permission?.model || ""),
  targetService: String(permission?.targetService || ""),
})

const sanitizePermissionDrafts = (drafts) => {
  if (!Array.isArray(drafts)) return []
  return drafts.map((permission) => {
    const nextPermission = {
      effect: String(permission?.effect || "ALLOW").trim().toUpperCase() === "DENY" ? "DENY" : "ALLOW",
      type: String(permission?.type || "SERVICE_ALL").trim().toUpperCase() || "SERVICE_ALL",
    }
    for (const key of ["service", "endpoint", "model", "targetService"]) {
      const value = String(permission?.[key] || "").trim()
      if (value) {
        nextPermission[key] = value
      }
    }
  return nextPermission
})
}

const VERSE_LEVELS = ["collaborative", "very collaborative", "absolutely synergetic"]
const PROACTIVITY_LEVELS = [1, 2, 3, 4, 5, 6]
const formatLevel = (value = "") => String(value || "").split(/\s+/).map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ")

const buildVerseAgentSettings = (agents = [], explicit = {}) =>
  Object.fromEntries(
    (Array.isArray(agents) ? agents : []).map((agent) => {
      const raw = explicit?.[agent.id] || {}
      return [
        agent.id,
        {
          proactivityEnabled: Boolean(raw?.proactivityEnabled ?? true),
          proactivityLevel: Number(raw?.proactivityLevel || 2),
        },
      ]
    }),
  )

export default function SettingsPage() {
  const backend = process.env.NEXT_PUBLIC_LIWIRO_BACKEND || "http://127.0.0.1:5000"
  const [canManageSettings, setCanManageSettings] = useState(false)
  const [canManageUsers, setCanManageUsers] = useState(false)
  const [isSuperAdmin, setIsSuperAdmin] = useState(false)
  const [settings, setSettings] = useState({
    productionMode: false,
    startServicesOnStartup: false,
    autoRefreshServiceStatus: true,
    deleteDataWithServiceByDefault: true,
    startServicesAfterGenerationByDefault: true,
    retryFailedBatchOpsByDefault: true,
    featureFlags: {},
  })
  const [featureFlagDefinitions, setFeatureFlagDefinitions] = useState([])
  const {
    status: settingsOperationStatus,
    startOperation,
    succeedOperation,
    failOperation,
  } = useOperationStatus({ autoHideSuccessMs: 1800 })
  const [vdbConnection, setVdbConnection] = useState({
    vdb_transport: "unixsocket",
    vdb_server_url: "",
    vdb_unix_socket_path: "",
    vdb_named_pipe_path: "",
    vdb_app_username: "",
    vdb_app_password: "",
    liwiro_domain: "",
    liwiro_db: "",
    supportsNamedPipe: false,
    defaultVdbServerUrl: "http://127.0.0.1:1957",
    defaultVdbUnixSocketPath: "/tmp/vdb.sock",
    defaultVdbNamedPipePath: normalizeVdbNamedPipePath("\\\\.\\pipe\\verun_vdb"),
  })
  const [statusSnapshot, setStatusSnapshot] = useState({
    configured: false,
    hasFrontendCreds: false,
    vdbUsersExist: false,
  })
  const [users, setUsers] = useState([])
  const [services, setServices] = useState([])
  const [verseHealth, setVerseHealth] = useState(null)
  const [verseSettingsState, setVerseSettingsState] = useState(null)
  const [verseAgents, setVerseAgents] = useState([])
  const [verseAgentSettings, setVerseAgentSettings] = useState({})
  const [verseLoading, setVerseLoading] = useState(false)
  const [verseBusy, setVerseBusy] = useState(false)
  const [vdbSaving, setVdbSaving] = useState(false)
  const verseControlsDisabled = !canManageSettings || verseBusy || verseLoading
  const [permissionDrafts, setPermissionDrafts] = useState({})
  const [serviceAccessDrafts, setServiceAccessDrafts] = useState({})
  const [createUserOpen, setCreateUserOpen] = useState(false)
  const [newUser, setNewUser] = useState({
    username: "",
    password: "",
    role: "viewer",
    permissions: ["VIEW_SERVICES"],
    service_access: "*",
  })
  const vdbStatus = useVdbConnectionStatus({
    backend,
    transport: vdbConnection.vdb_transport,
    serverUrl: vdbConnection.vdb_server_url,
    socketPath: vdbConnection.vdb_unix_socket_path,
    namedPipePath: vdbConnection.vdb_named_pipe_path,
    supportsNamedPipe: vdbConnection.supportsNamedPipe,
    enabled: canManageSettings,
  })
  const vdbTargetField = vdbTransportTargetConfig({
    transport: vdbConnection.vdb_transport,
    serverUrl: vdbConnection.vdb_server_url,
    socketPath: vdbConnection.vdb_unix_socket_path,
    namedPipePath: vdbConnection.vdb_named_pipe_path,
    defaultServerUrl: vdbConnection.defaultVdbServerUrl,
    defaultSocketPath: vdbConnection.defaultVdbUnixSocketPath,
    defaultNamedPipePath: vdbConnection.defaultVdbNamedPipePath,
    supportsNamedPipe: vdbConnection.supportsNamedPipe,
  })
  const verseCollaborationLevel = useMemo(
    () => String(verseSettingsState?.collaborationLevel || verseHealth?.settings?.collaborationLevel || "very collaborative").trim() || "very collaborative",
    [verseHealth, verseSettingsState]
  )
  const verseProactiveEnabled = useMemo(
    () => Boolean(verseSettingsState?.proactiveModeEnabled ?? verseHealth?.settings?.proactiveModeEnabled ?? false),
    [verseHealth, verseSettingsState]
  )
  const showSettingsProgress = useMemo(() => {
    const flags = settings?.featureFlags && typeof settings.featureFlags === "object" ? settings.featureFlags : {}
    const unified = !Object.prototype.hasOwnProperty.call(flags, "unifiedOperationStatus") || Boolean(flags.unifiedOperationStatus)
    const settingsFlag = !Object.prototype.hasOwnProperty.call(flags, "settingsProgressMessages") || Boolean(flags.settingsProgressMessages)
    return unified && settingsFlag
  }, [settings?.featureFlags])
  const groupedFeatureFlags = useMemo(() => {
    const groups = new Map()
    for (const definition of Array.isArray(featureFlagDefinitions) ? featureFlagDefinitions : []) {
      const groupId = String(definition?.group || "general").trim() || "general"
      if (!groups.has(groupId)) groups.set(groupId, [])
      groups.get(groupId).push(definition)
    }
    return [...groups.entries()]
  }, [featureFlagDefinitions])

  const isManagedSuperAdminUser = useCallback(
    (username) => users.some((user) => user.username === username && Boolean(user.is_super_admin)),
    [users]
  )

  const loadVerseData = useCallback(async () => {
    if (showSettingsProgress) {
      startOperation({
        title: "Loading Verse settings",
        detail: "Refreshing collaboration, proactive mode, and specialist controls.",
      })
    }
    setVerseLoading(true)
    try {
      const bootstrapData = await fetchVerseBootstrap(backend, { ttlMs: 5000 })
      const agentList = Array.isArray(bootstrapData?.agents) ? bootstrapData.agents : []
      const explicitAgentSettings = bootstrapData?.settings || {}
      setVerseHealth(bootstrapData || null)
      setVerseSettingsState(bootstrapData?.settings || null)
      setVerseAgents(agentList)
      setVerseAgentSettings(buildVerseAgentSettings(agentList, explicitAgentSettings?.agents || explicitAgentSettings?.agentSettings || {}))
      if (showSettingsProgress) {
        succeedOperation({
          title: "Verse settings loaded",
          detail: "Verse controls are ready.",
        })
      }
    } catch (error) {
      if (showSettingsProgress) {
        failOperation({
          title: "Verse settings failed to load",
          detail: error?.message || "Failed to load Verse settings",
        })
      }
      toast.error(error?.message || "Failed to load Verse settings")
    } finally {
      setVerseLoading(false)
    }
  }, [backend, failOperation, showSettingsProgress, startOperation, succeedOperation])

  const persistVerseSettings = useCallback(async ({ collaboration, proactiveEnabled, nextAgents } = {}) => {
    const agentsPayload = nextAgents || verseAgentSettings
    if (showSettingsProgress) {
      startOperation({
        title: "Saving Verse settings",
        detail: "Applying collaboration and proactive configuration.",
      })
    }
    setVerseBusy(true)
    try {
      const payload = {
        collaborationLevel: collaboration ?? verseCollaborationLevel,
        proactiveModeEnabled: proactiveEnabled ?? verseProactiveEnabled,
        agents: agentsPayload,
      }
      const res = await fetch(`${backend}/platform/verse/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(payload),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || "Failed to update Verse settings")
      const nextSettings = data?.settings || payload
      setVerseSettingsState(nextSettings)
      setVerseHealth((current) => ({ ...(current || {}), settings: nextSettings, prerequisites: data?.prerequisites || current?.prerequisites || null }))
      setVerseAgentSettings(agentsPayload)
      invalidateVerseBootstrap(backend)
      invalidateAuthedJsonCache(`${backend}/platform/verse/agents`)
      invalidateAuthedJsonCache(`${backend}/platform/verse/settings`)
      if (showSettingsProgress) {
        succeedOperation({
          title: "Verse settings saved",
          detail: "The new Verse configuration is now active.",
        })
      }
      toast.success("Verse settings updated")
      return nextSettings
    } catch (error) {
      if (showSettingsProgress) {
        failOperation({
          title: "Verse settings failed to save",
          detail: error?.message || "Failed to update Verse settings",
        })
      }
      toast.error(error?.message || "Failed to update Verse settings")
      throw error
    } finally {
      setVerseBusy(false)
    }
  }, [backend, failOperation, showSettingsProgress, startOperation, succeedOperation, verseAgentSettings, verseCollaborationLevel, verseProactiveEnabled])

  const handleVerseCollaboration = useCallback((level) => {
    if (verseBusy || verseLoading) return
    persistVerseSettings({ collaboration: level }).catch(() => {})
  }, [persistVerseSettings, verseBusy, verseLoading])

  const toggleVerseProactive = useCallback((checked) => {
    if (verseBusy || verseLoading) return
    persistVerseSettings({ proactiveEnabled: Boolean(checked) }).catch(() => {})
  }, [persistVerseSettings, verseBusy, verseLoading])

  const updateVerseAgentProactivity = useCallback((agentId, patch = {}) => {
    if (verseBusy || verseLoading) return
    const current = verseAgentSettings[agentId] || { proactivityEnabled: true, proactivityLevel: 2 }
    const nextAgents = {
      ...verseAgentSettings,
      [agentId]: {
        proactivityEnabled: Boolean(patch?.proactivityEnabled ?? current.proactivityEnabled),
        proactivityLevel: Number(patch?.proactivityLevel ?? current.proactivityLevel ?? 2),
      },
    }
    persistVerseSettings({ nextAgents }).catch(() => {})
  }, [persistVerseSettings, verseAgentSettings, verseBusy, verseLoading])

  const load = useCallback(async () => {
    if (showSettingsProgress) {
      startOperation({
        title: "Loading platform settings",
        detail: "Refreshing platform defaults, feature flags, users, and runtime state.",
      })
    }
    try {
      const meRes = await fetch(`${backend}/auth/me`, { headers: authHeaders() })
      if (meRes.status === 401) {
        window.location.href = "/login"
        return
      }
      if (!meRes.ok) {
        throw new Error("Failed to load current user")
      }
      const me = await meRes.json()
      const manageSettings = Boolean(me?.is_super_admin)
      const manageUsers = Boolean(me?.is_super_admin)
      setIsSuperAdmin(Boolean(me?.is_super_admin))
      setCanManageSettings(manageSettings)
      setCanManageUsers(manageUsers)

      const servicesUrl = new URL(`${backend}/services`)
      servicesUrl.searchParams.set("summary", "1")
      servicesUrl.searchParams.set("refresh", "0")

      const requests = {}
      if (manageSettings) {
        requests.settings = fetch(`${backend}/platform/settings`, { headers: authHeaders() })
        requests.vdbConnection = fetch(`${backend}/platform/vdb/connection`, { headers: authHeaders() })
        requests.authStatus = fetch(`${backend}/auth/status`, { headers: authHeaders() })
      }
      if (manageUsers) {
        requests.users = fetch(`${backend}/platform/users`, { headers: authHeaders() })
        requests.services = fetch(servicesUrl.toString(), { headers: authHeaders() })
      }

      const requestEntries = Object.entries(requests)
      const settled = await Promise.allSettled(requestEntries.map(([, promise]) => promise))
      const results = Object.fromEntries(requestEntries.map(([key], index) => [key, settled[index]]))

      const settingsRes = results.settings
      if (settingsRes?.status === "fulfilled" && settingsRes.value.ok) {
        const data = await settingsRes.value.json()
        setSettings({
          productionMode: Boolean(data.productionMode),
          startServicesOnStartup: Boolean(data.startServicesOnStartup),
          autoRefreshServiceStatus: Boolean(data.autoRefreshServiceStatus),
          deleteDataWithServiceByDefault: Boolean(data.deleteDataWithServiceByDefault),
          startServicesAfterGenerationByDefault: Boolean(data.startServicesAfterGenerationByDefault),
          retryFailedBatchOpsByDefault: Boolean(data.retryFailedBatchOpsByDefault),
          featureFlags: data?.featureFlags && typeof data.featureFlags === "object" ? data.featureFlags : {},
        })
        setFeatureFlagDefinitions(Array.isArray(data?.featureFlagDefinitions) ? data.featureFlagDefinitions : [])
      }

      const connRes = results.vdbConnection
      if (connRes?.status === "fulfilled" && connRes.value.ok) {
        const conn = await connRes.value.json()
        setVdbConnection({
          vdb_transport: String(conn?.vdb_transport || "unixsocket"),
          vdb_server_url: String(conn?.vdb_server_url || ""),
          vdb_unix_socket_path: String(conn?.vdb_unix_socket_path || ""),
          vdb_named_pipe_path: normalizeVdbNamedPipePath(conn?.vdb_named_pipe_path || ""),
          vdb_app_username: String(conn?.vdb_app_username || ""),
          vdb_app_password: "",
          liwiro_domain: String(conn?.liwiro_domain || ""),
          liwiro_db: String(conn?.liwiro_db || ""),
          supportsNamedPipe: Boolean(conn?.supportsNamedPipe),
          defaultVdbServerUrl: String(conn?.defaultVdbServerUrl || "http://127.0.0.1:1957"),
          defaultVdbUnixSocketPath: String(conn?.defaultVdbUnixSocketPath || "/tmp/vdb.sock"),
          defaultVdbNamedPipePath: normalizeVdbNamedPipePath(conn?.defaultVdbNamedPipePath || "\\\\.\\pipe\\verun_vdb"),
        })
      }

      const statusRes = results.authStatus
      if (statusRes?.status === "fulfilled" && statusRes.value.ok) {
        const statusData = await statusRes.value.json()
        setStatusSnapshot({
          configured: Boolean(statusData?.configured),
          hasFrontendCreds: Boolean(statusData?.hasFrontendCreds),
          vdbUsersExist: Boolean(statusData?.vdbUsersExist),
        })
      }

      const usersRes = results.users
      if (usersRes?.status === "fulfilled" && usersRes.value.ok) {
        const data = await usersRes.value.json()
        const normalized = Array.isArray(data) ? data : []
        setUsers(normalized)
        const nextDrafts = {}
        const nextServiceDrafts = {}
        normalized.forEach((user) => {
          nextDrafts[user.username] = Array.isArray(user.permissions)
            ? user.permissions.map((permission) => createPermissionDraft(permission))
            : []
          nextServiceDrafts[user.username] = Array.isArray(user.service_access) ? user.service_access.join(", ") : "*"
        })
        setPermissionDrafts(nextDrafts)
        setServiceAccessDrafts(nextServiceDrafts)
      }

      const serviceRes = results.services
      if (serviceRes?.status === "fulfilled" && serviceRes.value.ok) {
        const serviceRows = await serviceRes.value.json()
        setServices(Array.isArray(serviceRows) ? serviceRows : [])
      }
      if (manageSettings) {
        await loadVerseData()
      }
      if (showSettingsProgress) {
        succeedOperation({
          title: "Platform settings loaded",
          detail: "Admin controls are ready.",
        })
      }
    } catch (error) {
      if (showSettingsProgress) {
        failOperation({
          title: "Platform settings failed to load",
          detail: error?.message || "Failed to load platform settings",
        })
      }
      toast.error("Failed to load platform settings")
    }
  }, [backend, failOperation, loadVerseData, showSettingsProgress, startOperation, succeedOperation])

  useEffect(() => {
    load()
  }, [load])

  const saveSettings = async () => {
    if (showSettingsProgress) {
      startOperation({
        title: "Saving platform settings",
        detail: "Persisting runtime defaults and feature flags.",
      })
    }
    try {
      const res = await fetch(`${backend}/platform/settings`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify(settings),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || "Failed to save settings")
      toast.success("Settings updated")
      setSettings({
        productionMode: Boolean(data.productionMode),
        startServicesOnStartup: Boolean(data.startServicesOnStartup),
        autoRefreshServiceStatus: Boolean(data.autoRefreshServiceStatus),
        deleteDataWithServiceByDefault: Boolean(data.deleteDataWithServiceByDefault),
        startServicesAfterGenerationByDefault: Boolean(data.startServicesAfterGenerationByDefault),
        retryFailedBatchOpsByDefault: Boolean(data.retryFailedBatchOpsByDefault),
        featureFlags: data?.featureFlags && typeof data.featureFlags === "object" ? data.featureFlags : {},
      })
      setFeatureFlagDefinitions(Array.isArray(data?.featureFlagDefinitions) ? data.featureFlagDefinitions : [])
      if (showSettingsProgress) {
        succeedOperation({
          title: "Platform settings saved",
          detail: "Runtime defaults and feature flags were updated.",
        })
      }
    } catch (error) {
      if (showSettingsProgress) {
        failOperation({
          title: "Platform settings failed to save",
          detail: error?.message || "Failed to save settings",
        })
      }
      toast.error(error?.message || "Failed to save settings")
    }
  }

  const saveVdbConnection = async () => {
    if (!canManageSettings) return
    setVdbSaving(true)
    try {
      const res = await fetch(`${backend}/platform/vdb/connection`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(vdbConnection),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        if (data?.revertedTransport) {
          setVdbConnection((current) => ({
            ...current,
            vdb_transport: String(data.revertedTransport),
            vdb_app_password: "",
          }))
        }
        throw new Error(data.error || "Failed to save VDB runtime settings")
      }
      setVdbConnection((current) => ({ ...current, ...data, vdb_app_password: "" }))
      toast.success(data.vdbRuntimeReady === false ? "VDB settings saved; runtime still needs attention" : "VDB runtime settings saved")
      await load()
    } catch (error) {
      toast.error(error?.message || "Failed to save VDB runtime settings")
    } finally {
      setVdbSaving(false)
    }
  }

  const createUser = async () => {
    if (showSettingsProgress) {
      startOperation({
        title: "Creating user",
        detail: "Saving the new platform account.",
      })
    }
    try {
      const username = String(newUser.username || "").trim()
      const password = String(newUser.password || "").trim()
      if (!username || !password) {
        throw new Error("Username and password are required")
      }
      const service_access = String(newUser.service_access || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean)
      const res = await fetch(`${backend}/platform/users`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          username,
          password,
          role: newUser.role,
          service_access,
          permissions: Array.isArray(newUser.permissions) ? newUser.permissions : [],
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || "Failed to create user")
      toast.success(`User ${data.username} created`)
      setNewUser({
        username: "",
        password: "",
        role: "viewer",
        permissions: ["VIEW_SERVICES"],
        service_access: "*",
      })
      setCreateUserOpen(false)
      if (showSettingsProgress) {
        succeedOperation({
          title: "User created",
          detail: `The account '${data.username}' is ready.`,
        })
      }
      load()
    } catch (error) {
      if (showSettingsProgress) {
        failOperation({
          title: "Failed to create user",
          detail: error?.message || "Failed to create user",
        })
      }
      toast.error(error?.message || "Failed to create user")
    }
  }

  const updateUserRole = async (username, role) => {
    if (showSettingsProgress) {
      startOperation({
        title: "Updating role",
        detail: `Applying the new role for ${username}.`,
      })
    }
    try {
      const res = await fetch(`${backend}/platform/users/${encodeURIComponent(username)}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({ role }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || "Failed to update role")
      if (showSettingsProgress) {
        succeedOperation({
          title: "Role updated",
          detail: `Updated ${data.username}.`,
        })
      }
      toast.success(`Updated ${data.username}`)
      load()
    } catch (error) {
      if (showSettingsProgress) {
        failOperation({
          title: "Failed to update role",
          detail: error?.message || "Failed to update role",
        })
      }
      toast.error(error?.message || "Failed to update role")
    }
  }

  const updateUserServiceAccess = async (username, serviceAccessRaw) => {
    if (showSettingsProgress) {
      startOperation({
        title: "Updating service access",
        detail: `Saving service access for ${username}.`,
      })
    }
    try {
      const service_access = String(serviceAccessRaw || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean)
      const res = await fetch(`${backend}/platform/users/${encodeURIComponent(username)}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({ service_access }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || "Failed to update service access")
      if (showSettingsProgress) {
        succeedOperation({
          title: "Service access updated",
          detail: `Updated ${data.username}.`,
        })
      }
      toast.success(`Updated ${data.username} service access`)
      load()
    } catch (error) {
      if (showSettingsProgress) {
        failOperation({
          title: "Failed to update service access",
          detail: error?.message || "Failed to update service access",
        })
      }
      toast.error(error?.message || "Failed to update service access")
    }
  }

  const deleteUser = async (username) => {
    if (showSettingsProgress) {
      startOperation({
        title: "Deleting user",
        detail: `Removing ${username} from the platform.`,
      })
    }
    try {
      const res = await fetch(`${backend}/platform/users/${encodeURIComponent(username)}`, {
        method: "DELETE",
        headers: authHeaders(),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || "Failed to delete user")
      if (showSettingsProgress) {
        succeedOperation({
          title: "User deleted",
          detail: data.message || `Removed ${username}.`,
        })
      }
      toast.success(data.message || "User deleted")
      load()
    } catch (error) {
      if (showSettingsProgress) {
        failOperation({
          title: "Failed to delete user",
          detail: error?.message || "Failed to delete user",
        })
      }
      toast.error(error?.message || "Failed to delete user")
    }
  }

  const updateUserPermissions = async (username, permissions) => {
    if (isManagedSuperAdminUser(username)) {
      return
    }
    if (!hasUserPermissionChanges(username)) {
      return
    }
    if (showSettingsProgress) {
      startOperation({
        title: "Updating permissions",
        detail: `Saving platform permissions for ${username}.`,
      })
    }
    try {
      const res = await fetch(`${backend}/platform/users/${encodeURIComponent(username)}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({ permissions: sanitizePermissionDrafts(permissions) }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || "Failed to update permissions")
      if (showSettingsProgress) {
        succeedOperation({
          title: "Permissions updated",
          detail: `Updated ${data.username}.`,
        })
      }
      toast.success(`Updated ${data.username} permissions`)
      load()
    } catch (error) {
      if (showSettingsProgress) {
        failOperation({
          title: "Failed to update permissions",
          detail: error?.message || "Failed to update permissions",
        })
      }
      toast.error(error?.message || "Failed to update permissions")
    }
  }

  const addPermissionDraft = (username, effect = "ALLOW") => {
    if (isManagedSuperAdminUser(username)) {
      return
    }
    setPermissionDrafts((prev) => ({
      ...prev,
      [username]: [...(prev[username] || []), createPermissionDraft({ effect })],
    }))
  }

  const updatePermissionDraft = (username, index, key, value) => {
    if (isManagedSuperAdminUser(username)) {
      return
    }
    setPermissionDrafts((prev) => ({
      ...prev,
      [username]: (prev[username] || []).map((item, idx) => (idx === index ? { ...item, [key]: value } : item)),
    }))
  }

  const removePermissionDraft = (username, index) => {
    if (isManagedSuperAdminUser(username)) {
      return
    }
    setPermissionDrafts((prev) => ({
      ...prev,
      [username]: (prev[username] || []).filter((_, idx) => idx !== index),
    }))
  }

  const hasUserPermissionChanges = (username) => {
    const baselinePermissions = sanitizePermissionDrafts(
      users.find((user) => user.username === username)?.permissions || []
    )
    const draftPermissions = sanitizePermissionDrafts(permissionDrafts[username] || [])
    return JSON.stringify(baselinePermissions) !== JSON.stringify(draftPermissions)
  }

  const selectNewUserRole = (roleValue) => {
    setNewUser((prev) => {
      let nextPermissions = Array.isArray(prev.permissions) ? [...prev.permissions] : []
      if (roleValue === "viewer") {
        nextPermissions = ["VIEW_SERVICES"]
      } else if (roleValue === "service_manager") {
        nextPermissions = Array.from(new Set(["VIEW_SERVICES", "MANAGE_SERVICES"]))
      } else if (roleValue === "admin") {
        nextPermissions = Array.from(new Set(["VIEW_SERVICES", "MANAGE_SERVICES"]))
      }
      return {
        ...prev,
        role: roleValue,
        permissions: nextPermissions,
        service_access: roleValue === "admin" ? "*" : prev.service_access || "*",
      }
    })
  }

  const toggleNewUserPermission = (permission) => {
    setNewUser((prev) => {
      const current = Array.isArray(prev.permissions) ? prev.permissions : []
      const exists = current.includes(permission)
      const next = exists ? current.filter((item) => item !== permission) : [...current, permission]
      return { ...prev, permissions: next }
    })
  }

  return (
    <div className="w-full app-stack">
      <section className="app-hero">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="app-eyebrow">Platform Settings</p>
            <h1 className="app-title mt-4">Manage runtime defaults, access, and platform policy</h1>
            <p className="app-copy mt-3">Configure Liwiro behavior, review the current VDB snapshot, and manage user roles from one admin surface.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href="/vdb-portal">
              <Button variant="outline" className="h-10">Open VDB Portal</Button>
            </Link>
            <Button variant="outline" className="h-10" onClick={load}>Refresh Snapshot</Button>
          </div>
        </div>
      </section>

      {showSettingsProgress && settingsOperationStatus?.visible ? (
        <OperationStatusPanel status={settingsOperationStatus} />
      ) : null}

      <div className="app-rail-layout">
        <aside className="app-rail">
          <div className="app-card-soft p-5">
            <p className="app-section-label">Access Mode</p>
            <p className="mt-2 text-lg font-semibold text-slate-950 dark:text-slate-50">
              {isSuperAdmin ? "Super Admin" : "Restricted"}
            </p>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
              {isSuperAdmin
                ? "Platform-level settings and RBAC changes are available."
                : "Only the super admin can edit platform settings and user management."}
            </p>
          </div>

          <div className="app-card-soft p-5">
            <p className="app-section-label">Runtime Snapshot</p>
            <div className="mt-3 grid gap-3">
              <div className="rounded-[1.1rem] border border-slate-200/80 bg-white/[0.84] p-4 dark:border-slate-800 dark:bg-slate-950/[0.68]">
                <p className="app-stat-label">Frontend Auth</p>
                <p className="mt-1 text-lg font-semibold text-slate-950 dark:text-slate-50">{statusSnapshot.hasFrontendCreds ? "Configured" : "Missing"}</p>
              </div>
              <div className="rounded-[1.1rem] border border-slate-200/80 bg-white/[0.84] p-4 dark:border-slate-800 dark:bg-slate-950/[0.68]">
                <p className="app-stat-label">VDB Users</p>
                <p className="mt-1 text-lg font-semibold text-slate-950 dark:text-slate-50">{statusSnapshot.vdbUsersExist ? "Detected" : "Not detected"}</p>
              </div>
              <div className="rounded-[1.1rem] border border-slate-200/80 bg-white/[0.84] p-4 dark:border-slate-800 dark:bg-slate-950/[0.68]">
                <p className="app-stat-label">Liwiro DB</p>
                <p className="mt-1 text-lg font-semibold text-slate-950 dark:text-slate-50">{vdbConnection.liwiro_db || "-"}</p>
              </div>
            </div>
          </div>
        </aside>

        <div className="app-main-column">
          <Card className="rounded-xl border-slate-200 shadow-sm dark:border-slate-700 dark:bg-slate-900">
            <CardHeader className="pb-3">
              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div>
                  <CardTitle className="text-xl text-slate-900 dark:text-slate-100">Verse settings</CardTitle>
                  <p className="text-sm text-slate-600 dark:text-slate-300">
                    Manage collaboration, proactive outreach, and specialist cadence alongside platform policies.
                  </p>
                </div>
                <p className="text-xs uppercase tracking-[0.18em] text-slate-400">
                  {verseLoading ? "Loading verse data…" : verseBusy ? "Saving..." : "Ready"}
                </p>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {!canManageSettings ? (
                <p className="text-xs text-amber-500">Super admin role required to edit Verse settings.</p>
              ) : null}
              <div className="rounded-2xl border border-slate-200/80 bg-white/[0.92] p-4 dark:border-slate-700 dark:bg-slate-950/60">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Collaboration</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {VERSE_LEVELS.map((level) => (
                      <Button
                        key={level}
                        size="sm"
                        variant={verseCollaborationLevel === level ? "default" : "outline"}
                        className="rounded-full"
                        onClick={() => handleVerseCollaboration(level)}
                        disabled={verseControlsDisabled}
                      >
                      {formatLevel(level)}
                    </Button>
                  ))}
                </div>
              </div>
              <div className="rounded-2xl border border-slate-200/80 bg-white/[0.92] p-4 dark:border-slate-700 dark:bg-slate-950/60">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Proactive outreach</p>
                    <p className="text-sm text-slate-700 dark:text-slate-300">{verseProactiveEnabled ? "Enabled" : "Disabled"}</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Each agent can run 1-6 proactive evaluations per day.</p>
                  </div>
                  <Switch
                    checked={verseProactiveEnabled}
                    onCheckedChange={toggleVerseProactive}
                    disabled={verseControlsDisabled}
                  />
                </div>
              </div>
              {verseAgents.length > 0 && (
                <div className="rounded-2xl border border-slate-200/80 bg-white/[0.92] p-4 dark:border-slate-700 dark:bg-slate-950/60">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Specialists</p>
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    {verseAgents.map((agent) => {
                      const agentConfig = verseAgentSettings[agent.id] || { proactivityEnabled: true, proactivityLevel: 2 }
                      return (
                        <div key={agent.id} className="rounded-2xl border border-slate-200/90 bg-white/[0.82] p-3 dark:border-slate-700 dark:bg-slate-900/60">
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <p className="font-semibold text-slate-900 dark:text-slate-100">{agent.displayName}</p>
                              <p className="text-xs uppercase tracking-[0.16em] text-slate-400">{agent.title}</p>
                            </div>
                            <Switch
                              checked={Boolean(agentConfig.proactivityEnabled)}
                              disabled={!verseProactiveEnabled || verseControlsDisabled}
                              onCheckedChange={(checked) => updateVerseAgentProactivity(agent.id, { proactivityEnabled: checked })}
                            />
                          </div>
                          <div className="mt-3 flex flex-wrap gap-2">
                            {PROACTIVITY_LEVELS.map((level) => (
                              <Button
                                key={`${agent.id}-${level}`}
                                size="sm"
                                variant={agentConfig.proactivityLevel === level ? "default" : "outline"}
                                className="rounded-full"
                                disabled={!verseProactiveEnabled || verseControlsDisabled || !agentConfig.proactivityEnabled}
                                onClick={() => updateVerseAgentProactivity(agent.id, { proactivityLevel: level })}
                              >
                                {level}
                              </Button>
                            ))}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
          <Card className="rounded-xl border-slate-200 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <CardHeader>
          <CardTitle className="text-xl text-slate-900 dark:text-slate-100">Liwiro Settings {isSuperAdmin ? "(Super Admin)" : ""}</CardTitle>
        </CardHeader>
        <CardContent>
          {!canManageSettings ? (
            <p className="text-sm text-amber-700 dark:text-amber-300">Only the super admin can manage platform settings and RBAC.</p>
          ) : (
            <div className="space-y-4">
              <div className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm font-medium leading-6 text-slate-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
                Super admin mode enabled. Platform-level settings and permission policies are editable.
              </div>
              <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Platform Runtime Snapshot</p>
                <div className="mt-2 grid gap-2 text-xs text-slate-600 dark:text-slate-300 md:grid-cols-2">
                  <p>Production mode: <span className="font-semibold">{settings.productionMode ? "Enabled" : "Disabled"}</span></p>
                  <p>Frontend auth configured: <span className="font-semibold">{statusSnapshot.hasFrontendCreds ? "Yes" : "No"}</span></p>
                  <p>VDB users detected: <span className="font-semibold">{statusSnapshot.vdbUsersExist ? "Yes" : "No"}</span></p>
                  <p className="flex items-center gap-2">
                    <span>VDB transport: <code>{String(vdbConnection.vdb_transport || "").toLowerCase()}</code></span>
                    <VdbTransportStatusIndicator status={vdbStatus} className="border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-950/70 dark:text-slate-200" />
                  </p>
                  <p>VDB server: <code>{vdbConnection.vdb_server_url || "-"}</code></p>
                  <p>{vdbTransportLabel(vdbConnection.vdb_transport, vdbConnection.supportsNamedPipe)} target: <code>{vdbTargetField.value || vdbTargetField.placeholder || "-"}</code></p>
                  <p>VDB app user: <code>{vdbConnection.vdb_app_username || "-"}</code></p>
                  <p>Liwiro domain: <code>{vdbConnection.liwiro_domain || "-"}</code></p>
                  <p>Liwiro db: <code>{vdbConnection.liwiro_db || "-"}</code></p>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Link href="/vdb-portal">
                    <Button variant="outline" className="h-8">Open VDB Portal</Button>
                  </Link>
                  <Link href="/vi-portal">
                    <Button variant="outline" className="h-8">Open VI Portal</Button>
                  </Link>
                  <Button variant="outline" className="h-8" onClick={load}>Refresh Snapshot</Button>
                </div>
              </div>
              <div className="rounded-lg border border-sky-200 bg-sky-50/70 p-4 dark:border-sky-900/70 dark:bg-sky-950/20">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Repair VDB runtime connection</p>
                    <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">Enter the VDB username and password here. Runtime repair is managed from Settings; the login page only authenticates your Liwiro account.</p>
                  </div>
                  <VdbTransportStatusIndicator status={vdbStatus} className="border-slate-200 bg-white text-slate-700 dark:border-slate-800 dark:bg-slate-950/70 dark:text-slate-200" />
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <div><Label htmlFor="settings-vdb-username">VDB Username</Label><Input id="settings-vdb-username" className="mt-1" value={vdbConnection.vdb_app_username} onChange={(event) => setVdbConnection((current) => ({ ...current, vdb_app_username: event.target.value }))} disabled={vdbSaving} /></div>
                  <div><Label htmlFor="settings-vdb-password">VDB Password</Label><PasswordInput id="settings-vdb-password" className="mt-1" value={vdbConnection.vdb_app_password} onChange={(event) => setVdbConnection((current) => ({ ...current, vdb_app_password: event.target.value }))} placeholder="Leave blank to keep the saved password" autoComplete="new-password" disabled={vdbSaving} /></div>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <Button type="button" variant="outline" className="h-9" onClick={saveVdbConnection} disabled={vdbSaving || !canManageSettings}>{vdbSaving ? "Saving…" : "Save and repair VDB runtime"}</Button>
                  <span className="text-xs text-slate-600 dark:text-slate-400">Saved passwords are never displayed.</span>
                </div>
              </div>
              <div className="flex items-center justify-between rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                <div>
                  <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Production mode</p>
                  <p className="text-xs text-slate-500 dark:text-slate-300">
                    Disable generated-service `/liwiro/*` routes, service docs, and public docs endpoints such as `/docs` and `/openapi*` across the platform.
                  </p>
                </div>
                <Switch
                  checked={settings.productionMode}
                  onCheckedChange={(checked) => setSettings((prev) => ({ ...prev, productionMode: checked }))}
                />
              </div>
              <div className="flex items-center justify-between rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                <div>
                  <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Start services on Liwiro startup</p>
                  <p className="text-xs text-slate-500 dark:text-slate-300">Automatically re-launch stopped services when backend boots.</p>
                </div>
                <Switch
                  checked={settings.startServicesOnStartup}
                  onCheckedChange={(checked) => setSettings((prev) => ({ ...prev, startServicesOnStartup: checked }))}
                />
              </div>
              <div className="flex items-center justify-between rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                <div>
                  <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Auto refresh service status</p>
                  <p className="text-xs text-slate-500 dark:text-slate-300">Reconcile running/not-running state when listing services.</p>
                </div>
                <Switch
                  checked={settings.autoRefreshServiceStatus}
                  onCheckedChange={(checked) => setSettings((prev) => ({ ...prev, autoRefreshServiceStatus: checked }))}
                />
              </div>
              <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Service List Option Defaults</p>
                <p className="mb-3 text-xs text-slate-500 dark:text-slate-300">Defaults applied in Services list batch actions.</p>
                <div className="space-y-3">
                  <div className="flex items-center justify-between rounded-md border border-slate-200 p-2 dark:border-slate-700">
                    <p className="text-xs text-slate-700 dark:text-slate-200">Delete data with service</p>
                    <Switch
                      checked={settings.deleteDataWithServiceByDefault}
                      onCheckedChange={(checked) => setSettings((prev) => ({ ...prev, deleteDataWithServiceByDefault: checked }))}
                    />
                  </div>
                  <div className="flex items-center justify-between rounded-md border border-slate-200 p-2 dark:border-slate-700">
                    <p className="text-xs text-slate-700 dark:text-slate-200">Start services after generation</p>
                    <Switch
                      checked={settings.startServicesAfterGenerationByDefault}
                      onCheckedChange={(checked) => setSettings((prev) => ({ ...prev, startServicesAfterGenerationByDefault: checked }))}
                    />
                  </div>
                  <div className="flex items-center justify-between rounded-md border border-slate-200 p-2 dark:border-slate-700">
                    <p className="text-xs text-slate-700 dark:text-slate-200">Retry failed batch ops once</p>
                    <Switch
                      checked={settings.retryFailedBatchOpsByDefault}
                      onCheckedChange={(checked) => setSettings((prev) => ({ ...prev, retryFailedBatchOpsByDefault: checked }))}
                    />
                  </div>
                </div>
              </div>
              {groupedFeatureFlags.length > 0 ? (
                <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                  <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Feature Flags</p>
                  <p className="mb-3 text-xs text-slate-500 dark:text-slate-300">
                    Central rollout switches for LAPIS repair, progress messaging, Verse actions, and portal behavior.
                  </p>
                  <div className="space-y-4">
                    {groupedFeatureFlags.map(([groupId, definitions]) => (
                      <div key={groupId} className="rounded-md border border-slate-200/80 p-3 dark:border-slate-700/80">
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{groupId}</p>
                        <div className="mt-3 space-y-3">
                          {definitions.map((definition) => {
                            const flagId = String(definition?.id || "").trim()
                            const flagEnabled = Boolean(settings?.featureFlags?.[flagId])
                            return (
                              <div key={flagId} className="flex items-start justify-between gap-4 rounded-md border border-slate-200/80 px-3 py-2 dark:border-slate-700/70">
                                <div>
                                  <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{definition?.title || flagId}</p>
                                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-300">{definition?.description || "No description available."}</p>
                                  {definition?.envKey ? (
                                    <p className="mt-1 text-[11px] text-slate-400">Env override: {definition.envKey}</p>
                                  ) : null}
                                </div>
                                <Switch
                                  checked={flagEnabled}
                                  onCheckedChange={(checked) => setSettings((prev) => ({
                                    ...prev,
                                    featureFlags: {
                                      ...(prev?.featureFlags || {}),
                                      [flagId]: Boolean(checked),
                                    },
                                  }))}
                                />
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
              <Button className="brand-solid h-10" onClick={saveSettings}>Save Settings</Button>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="rounded-xl border-slate-200 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <CardHeader>
          <CardTitle className="text-xl text-slate-900 dark:text-slate-100">User Accounts & Roles</CardTitle>
        </CardHeader>
        <CardContent>
          {!canManageUsers ? (
            <p className="text-sm text-amber-700 dark:text-amber-300">User management requires super admin role.</p>
          ) : (
            <div className="space-y-5">
              <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                  <div>
                    <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">Create User</p>
                    <p className="text-xs text-slate-500 dark:text-slate-300">
                      Guided setup: choose a role, click permissions, then create the account.
                    </p>
                  </div>
                  <Button variant="outline" className="h-9" onClick={() => setCreateUserOpen((prev) => !prev)}>
                    {createUserOpen ? "Hide Form" : "New User"}
                  </Button>
                </div>

                {createUserOpen && (
                  <div className="mt-4 space-y-5 border-t border-slate-200 pt-4 dark:border-slate-700">
                    <div className="grid gap-4 md:grid-cols-2">
                      <div className="space-y-2">
                        <Label htmlFor="new-user-username">Username</Label>
                        <Input
                          id="new-user-username"
                          placeholder="Username"
                          value={newUser.username}
                          onChange={(e) => setNewUser((prev) => ({ ...prev, username: e.target.value }))}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="new-user-password">Password</Label>
                        <PasswordInput
                          id="new-user-password"
                          placeholder="Password"
                          value={newUser.password}
                          onChange={(e) => setNewUser((prev) => ({ ...prev, password: e.target.value }))}
                        />
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label>Role</Label>
                      <div className="grid gap-2 md:grid-cols-3">
                        {CREATE_ROLE_OPTIONS.map((option) => {
                          const selected = newUser.role === option.value
                          return (
                            <button
                              key={option.value}
                              type="button"
                              onClick={() => selectNewUserRole(option.value)}
                              className={`rounded-lg border p-3 text-left transition ${
                                selected
                                  ? "border-green-300 bg-green-50 text-green-900 dark:border-green-700 dark:bg-green-900/20 dark:text-green-200"
                                  : "border-slate-200 bg-white hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800"
                              }`}
                            >
                              <p className="text-sm font-semibold">{option.label}</p>
                              <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">{option.description}</p>
                            </button>
                          )
                        })}
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label>Platform Permissions</Label>
                      <p className="text-xs text-slate-500 dark:text-slate-300">
                        Click to toggle. Selected permissions are highlighted in green.
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {PLATFORM_PERMISSION_OPTIONS.map((option) => {
                          const selected = (newUser.permissions || []).includes(option.value)
                          return (
                            <button
                              key={option.value}
                              type="button"
                              onClick={() => toggleNewUserPermission(option.value)}
                              className={`rounded-full border px-3 py-2 text-left text-xs transition ${
                                selected
                                  ? "border-green-300 bg-green-100 text-green-800 dark:border-green-700 dark:bg-green-900/30 dark:text-green-200"
                                  : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
                              }`}
                              title={option.description}
                            >
                              {option.label}
                            </button>
                          )
                        })}
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="new-user-service-access">Service Access</Label>
                      <Input
                        id="new-user-service-access"
                        placeholder="* or comma list (e.g. AuthService, OrdersService)"
                        value={newUser.service_access}
                        disabled={newUser.role === "admin"}
                        onChange={(e) => setNewUser((prev) => ({ ...prev, service_access: e.target.value }))}
                      />
                      <p className="text-xs text-slate-500 dark:text-slate-300">
                        {newUser.role === "admin"
                          ? "Admin role uses wildcard service access (*) automatically."
                          : "Use * for all services or a comma-separated list of service names/process IDs."}
                      </p>
                    </div>

                    <div className="flex justify-end">
                      <Button
                        className="brand-solid h-10"
                        onClick={createUser}
                        disabled={!String(newUser.username || "").trim() || !String(newUser.password || "").trim()}
                      >
                        Create User
                      </Button>
                    </div>
                  </div>
                )}
              </div>

              <div className="space-y-2">
                {users.map((user) => {
                  const permissionEditingLocked = Boolean(user.is_super_admin)
                  const permissionSaveDirty = hasUserPermissionChanges(user.username)

                  return (
                  <div key={user.username} className="flex flex-col gap-3 rounded-lg border border-slate-200 p-3 dark:border-slate-700 md:flex-row md:items-center md:justify-between">
                    <div>
                      <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-slate-900 dark:text-slate-100">
                        <span>{user.username}</span>
                        {user.is_super_admin ? (
                          <span className="inline-flex shrink-0 whitespace-nowrap rounded bg-primary/[0.15] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-primary dark:bg-primary/30 dark:text-primary-foreground">
                            super admin
                          </span>
                        ) : null}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-300">Created: {user.created_at || "-"}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Label className="text-xs">Role</Label>
                      <select
                        className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm dark:border-slate-700 dark:bg-slate-950"
                        value={user.role || "viewer"}
                        disabled={permissionEditingLocked}
                        onChange={(e) => updateUserRole(user.username, e.target.value)}
                      >
                        <option value="viewer">viewer</option>
                        <option value="service_manager">service_manager</option>
                        <option value="admin">admin</option>
                      </select>
                      <Input
                        className="h-9 w-[280px]"
                        value={serviceAccessDrafts[user.username] ?? (Array.isArray(user.service_access) ? user.service_access.join(", ") : "*")}
                        disabled={permissionEditingLocked}
                        onChange={(e) => setServiceAccessDrafts((prev) => ({ ...prev, [user.username]: e.target.value }))}
                        onBlur={(e) => updateUserServiceAccess(user.username, e.target.value)}
                        placeholder="Service access: * or api names"
                      />
                      <Button variant="outline" className="h-9 border-destructive/40 text-destructive hover:bg-destructive/10 dark:border-destructive/40 dark:text-destructive dark:hover:bg-destructive/20" onClick={() => deleteUser(user.username)} disabled={permissionEditingLocked}>
                        Delete
                      </Button>
                    </div>
                    <div className="w-full rounded-md border border-slate-200 p-3 dark:border-slate-700 md:col-span-2">
                      <div className="mb-2 flex items-center justify-between">
                        <p className="text-xs font-semibold text-slate-700 dark:text-slate-200">Fine-grained Permissions</p>
                        {permissionEditingLocked ? (
                          <span className="inline-flex shrink-0 whitespace-nowrap rounded-full border border-amber-300/60 bg-amber-100/90 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-amber-950 dark:border-amber-300/60 dark:bg-amber-100/90 dark:text-amber-950">
                            Deactivated for super admin
                          </span>
                        ) : (
                          <div className="flex gap-2">
                            <Button variant="outline" className="h-7 text-xs" onClick={() => addPermissionDraft(user.username, "ALLOW")}>
                              + Add Permission
                            </Button>
                            <Button
                              variant="outline"
                              className="h-7 border-destructive/40 text-xs text-destructive hover:bg-destructive/10 dark:border-destructive/40 dark:text-destructive dark:hover:bg-destructive/20"
                              onClick={() => addPermissionDraft(user.username, "DENY")}
                            >
                              Remove Permission
                            </Button>
                            <Button
                              className="brand-solid h-7 px-3 text-xs"
                              onClick={() => updateUserPermissions(user.username, permissionDrafts[user.username] || [])}
                              disabled={!permissionSaveDirty}
                            >
                              Save Permissions
                            </Button>
                          </div>
                        )}
                      </div>
                      {permissionEditingLocked ? (
                        <p className="mb-3 rounded-md border border-amber-300/55 bg-amber-50/90 px-3 py-2 text-xs leading-6 text-amber-900 dark:border-amber-500/35 dark:bg-amber-500/10 dark:text-amber-200">
                          Add/remove permission controls are deactivated for the super admin account. Super admin access is managed at the platform level.
                        </p>
                      ) : null}
                      {!permissionEditingLocked && (permissionDrafts[user.username] || []).length > 0 ? (
                        <p className="mb-3 text-xs text-slate-500 dark:text-slate-300">
                          `Add Permission` creates an explicit allow rule. `Remove Permission` creates a deny rule that can carve out access even from wildcard (`*`) service access.
                        </p>
                      ) : null}
                      <div className="space-y-2">
                        {(permissionDrafts[user.username] || []).length === 0 ? (
                          <p className="text-xs text-slate-500 dark:text-slate-300">
                            {permissionEditingLocked
                              ? "No editable fine-grained permission rules are shown for the super admin account."
                              : "No explicit permission rules defined. Add permission rules to grant access or remove permission rules to block access on specific services, endpoints, or models."}
                          </p>
                        ) : (
                          (permissionDrafts[user.username] || []).map((permission, idx) => (
                            <div key={permission.draftId || `${user.username}-${idx}`} className="grid gap-2 rounded border border-slate-200 p-2 dark:border-slate-700 md:grid-cols-6">
                              <div className="space-y-2">
                                <span
                                  className={`inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] ${
                                    permission.effect === "DENY"
                                      ? "border border-rose-300/60 bg-rose-100/90 text-rose-950 dark:border-rose-300/60 dark:bg-rose-100/90 dark:text-rose-950"
                                      : "border border-emerald-300/60 bg-emerald-100/90 text-emerald-950 dark:border-emerald-300/60 dark:bg-emerald-100/90 dark:text-emerald-950"
                                  }`}
                                >
                                  {permission.effect === "DENY" ? "Remove access" : "Grant access"}
                                </span>
                                <select
                                  className="h-8 w-full rounded-md border border-slate-300 bg-white px-2 text-xs dark:border-slate-700 dark:bg-slate-950"
                                  value={permission.type || "SERVICE_ALL"}
                                  onChange={(e) => updatePermissionDraft(user.username, idx, "type", e.target.value)}
                                  disabled={permissionEditingLocked}
                                >
                                  <option value="SERVICE_ALL">service all</option>
                                  <option value="SERVICE_ENDPOINT">service endpoint</option>
                                  <option value="SERVICE_MODEL">service model</option>
                                  <option value="CROSS_SERVICE">other service</option>
                                </select>
                              </div>
                              <select
                                className="h-8 rounded-md border border-slate-300 bg-white px-2 text-xs dark:border-slate-700 dark:bg-slate-950"
                                value={permission.service || ""}
                                onChange={(e) => updatePermissionDraft(user.username, idx, "service", e.target.value)}
                                disabled={permissionEditingLocked}
                              >
                                <option value="">select service</option>
                                {services.map((service) => <option key={`svc-${service.processId}`} value={service.apiName}>{service.apiName}</option>)}
                              </select>
                              {permission.type === "SERVICE_ENDPOINT" ? (
                                <Input
                                  className="h-8 text-xs"
                                  value={permission.endpoint || ""}
                                  onChange={(e) => updatePermissionDraft(user.username, idx, "endpoint", e.target.value)}
                                  placeholder="endpoint path"
                                  disabled={permissionEditingLocked}
                                />
                              ) : (
                                <Input className="h-8 text-xs" value="" placeholder="endpoint n/a" disabled />
                              )}
                              {permission.type === "SERVICE_MODEL" ? (
                                <Input
                                  className="h-8 text-xs"
                                  value={permission.model || ""}
                                  onChange={(e) => updatePermissionDraft(user.username, idx, "model", e.target.value)}
                                  placeholder="model name"
                                  disabled={permissionEditingLocked}
                                />
                              ) : (
                                <Input className="h-8 text-xs" value="" placeholder="model n/a" disabled />
                              )}
                              {permission.type === "CROSS_SERVICE" ? (
                                <select
                                  className="h-8 rounded-md border border-slate-300 bg-white px-2 text-xs dark:border-slate-700 dark:bg-slate-950"
                                  value={permission.targetService || ""}
                                  onChange={(e) => updatePermissionDraft(user.username, idx, "targetService", e.target.value)}
                                  disabled={permissionEditingLocked}
                                >
                                  <option value="">target service</option>
                                  {services.map((service) => <option key={`target-${service.processId}`} value={service.apiName}>{service.apiName}</option>)}
                                </select>
                              ) : (
                                <Input className="h-8 text-xs" value="" placeholder="target n/a" disabled />
                              )}
                              {permissionEditingLocked ? (
                                <div className="inline-flex h-8 items-center justify-center rounded-md border border-slate-200 bg-slate-50 px-2 text-[11px] font-medium uppercase tracking-[0.16em] text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
                                  Locked
                                </div>
                              ) : (
                                <Button
                                  variant="outline"
                                  className="h-8 border-destructive/40 text-xs text-destructive dark:border-destructive/40 dark:text-destructive"
                                  onClick={() => removePermissionDraft(user.username, idx)}
                                >
                                  Delete Rule
                                </Button>
                              )}
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  </div>
                  )
                })}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {canManageUsers ? <VdbRbacAdmin backend={backend} title="VDB Users / RBAC" /> : null}
        </div>
      </div>
    </div>
  )
}
