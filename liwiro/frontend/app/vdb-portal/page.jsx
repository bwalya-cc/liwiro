// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

"use client"

import { vdbCommandText } from "@/lib/vdb-commands"
import { useEffect, useMemo, useState, useCallback, useRef } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { JsonTextarea } from "@/components/ui/json-textarea"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { CopyIconButton } from "@/components/ui/copy-icon-button"
import { VdbTransportStatusIndicator } from "@/components/vdb/vdb-transport-status-indicator"
import VdbRbacAdmin from "@/components/vdb/vdb-rbac-admin"
import PasswordInput from "@/components/ui/password-input"
import { OperationStatusPanel } from "@/components/ui/operation-status-panel"
import { authHeaders } from "@/lib/auth"
import { fetchAuthedJson } from "@/lib/authed-json-cache"
import { activatePendingVerseAction, consumePendingVerseAction } from "@/lib/verse-actions"
import { useOperationStatus } from "@/lib/operation-status"
import { isFeatureEnabled, usePlatformFeatureFlags } from "@/lib/platform-flags"
import { useVdbConnectionStatus } from "@/lib/vdb-connection-status"
import { normalizeVdbNamedPipePath, normalizeVdbTransportMode, vdbTransportLabel, vdbTransportOptions, vdbTransportTargetConfig } from "@/lib/vdb-transport"
import { toast } from "sonner"

const FAMILY_OPTIONS = ["general", "help", "list", "define", "use", "drop", "domain", "model", "crud", "script", "transaction", "export", "tumi"]
const LIST_OPTIONS = ["domains", "all_domains", "domains_and_owners", "dbs", "collections", "models", "scripts"]
const TUMI_LIST_OPTIONS = ["users", "roles", "permissions", "domains", "domains_and_owners", "owned_domains"]
const TRANSACTION_ACTIONS = ["begin", "commit", "abort"]
const GENERAL_ACTIONS = ["whoami", "context", "echo"]
const DEFINE_USE_DROP_ACTIONS = {
  define: ["domain", "db", "domain_db"],
  use: ["domain", "db", "domain_db"],
  drop: ["domain", "db", "collection"],
}
const DOMAIN_ACTIONS = ["status", "suspend", "resume"]
const MODEL_ACTIONS = ["get", "delete"]
const CRUD_ACTIONS = ["create", "read", "update", "delete"]
const SCRIPT_ACTIONS = ["create", "read", "execute", "delete"]
const TUMI_ACTIONS = ["list", "create", "delete", "read", "grant", "revoke", "transfer"]
const FALLBACK_PERMISSIONS = ["READ", "WRITE", "DATA_ACCESS", "DATA_EXPORT", "SCRIPT_READ", "SCRIPT_WRITE"]
const HELP_FALLBACK_TOPICS = ["commands", "domains", "dbs", "collections", "scripts", "users", "roles", "permissions"]

const defaultBuilder = {
  family: "general",
  action: "whoami",
  listType: "domains",
  helpTopic: "commands",
  echoMessage: "hello",
  domain: "",
  db: "",
  collection: "",
  modelCollection: "",
  scriptName: "",
  scriptService: "utils",
  scriptCode: "print('Hello from script');",
  scriptParamsText: "{}",
  createSchemaText: "{}",
  createDataText: "{}",
  readQueryText: "{}",
  readArgsText: "{}",
  writeQueryText: "{}",
  writeDataText: "{}",
  exportDomains: [],
  exportPackage: "",
  exportOutDir: "",
  tumiAction: "list",
  tumiListType: "users",
  tumiUsername: "",
  tumiRole: "",
  tumiDomain: "",
  tumiDb: "",
  tumiCollection: "",
  tumiPermissions: ["READ"],
  tumiEmail: "",
  tumiPassword: "",
}

function asArray(value) {
  return Array.isArray(value) ? value : []
}

function responseHeight(text, base = 320, max = 960) {
  const lines = String(text || "").split("\n")
  const estimatedRows = lines.reduce((total, line) => total + Math.max(1, Math.ceil(line.length / 88)), 0)
  return Math.max(base, Math.min(max, estimatedRows * 20 + 40))
}

function parseResponseJson(text) {
  try {
    return JSON.parse(String(text || ""))
  } catch {
    return null
  }
}

export default function VdbPortalPage() {
  const runQueryRef = useRef(null)
  const backend = process.env.NEXT_PUBLIC_LIWIRO_BACKEND || "http://127.0.0.1:5000"
  const {
    status: portalOperationStatus,
    startOperation,
    succeedOperation,
    failOperation,
  } = useOperationStatus({ autoHideSuccessMs: 1800 })
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [isSuperAdmin, setIsSuperAdmin] = useState(false)
  const [mode, setMode] = useState("app")
  const [connection, setConnection] = useState({
    vdb_transport: "unixsocket",
    vdb_server_url: "",
    vdb_unix_socket_path: "",
    vdb_named_pipe_path: "",
    vdb_app_username: "",
    vdb_super_admin_username: "",
    has_saved_vdb_app_password: false,
    has_saved_vdb_super_admin_password: false,
    can_use_app_mode: true,
    can_use_super_admin_mode: false,
    liwiro_domain: "",
    liwiro_db: "",
    supportsNamedPipe: false,
    defaultVdbTransport: "unixsocket",
    defaultVdbServerUrl: "http://127.0.0.1:1957",
    defaultVdbUnixSocketPath: "/tmp/vdb.sock",
    defaultVdbNamedPipePath: normalizeVdbNamedPipePath("\\\\.\\pipe\\verun_vdb"),
    defaultVdbExportOutDir: "/tmp/vdb-exports",
  })
  const [credentials, setCredentials] = useState({
    username: "",
    password: "",
    vdb_transport: "unixsocket",
    vdb_server_url: "",
    vdb_unix_socket_path: "",
    vdb_named_pipe_path: "",
  })
  const [saveSuperAdminCredentials, setSaveSuperAdminCredentials] = useState(false)
  const [portalToken, setPortalToken] = useState("")
  const [sessionInfo, setSessionInfo] = useState({})
  const [autoConnectedAppMode, setAutoConnectedAppMode] = useState(false)

  const [queryText, setQueryText] = useState("read domains")
  const [lastResponse, setLastResponse] = useState("No query executed yet.")
  const [builder, setBuilder] = useState(defaultBuilder)
  const [commandOptions, setCommandOptions] = useState({
    domains: [],
    dbs: [],
    collections: [],
    models: [],
    scripts: [],
    users: [],
    roles: [],
    permissions: [],
    helpTopics: HELP_FALLBACK_TOPICS,
  })
  const { featureFlags } = usePlatformFeatureFlags(backend)
  const showPortalProgress = isFeatureEnabled(featureFlags, "unifiedOperationStatus", true)
    && isFeatureEnabled(featureFlags, "vdbProgressMessages", true)

  const canQuery = Boolean(portalToken)
  const savedVdbStatus = useVdbConnectionStatus({
    backend,
    transport: connection.vdb_transport,
    serverUrl: connection.vdb_server_url,
    socketPath: connection.vdb_unix_socket_path,
    namedPipePath: connection.vdb_named_pipe_path,
    supportsNamedPipe: connection.supportsNamedPipe,
    enabled: !loading,
  })
  const selectedVdbStatus = useVdbConnectionStatus({
    backend,
    transport: credentials.vdb_transport,
    serverUrl: credentials.vdb_server_url || connection.vdb_server_url,
    socketPath: credentials.vdb_unix_socket_path || connection.vdb_unix_socket_path,
    namedPipePath: credentials.vdb_named_pipe_path || connection.vdb_named_pipe_path,
    supportsNamedPipe: connection.supportsNamedPipe,
    enabled: !loading,
    attemptAutostart: credentials.vdb_transport === "http",
  })
  const selectedTargetField = vdbTransportTargetConfig({
    transport: credentials.vdb_transport,
    serverUrl: credentials.vdb_server_url || connection.vdb_server_url,
    socketPath: credentials.vdb_unix_socket_path || connection.vdb_unix_socket_path,
    namedPipePath: credentials.vdb_named_pipe_path || connection.vdb_named_pipe_path,
    defaultServerUrl: connection.defaultVdbServerUrl,
    defaultSocketPath: connection.defaultVdbUnixSocketPath,
    defaultNamedPipePath: normalizeVdbNamedPipePath(connection.defaultVdbNamedPipePath),
    supportsNamedPipe: connection.supportsNamedPipe,
  })

  const knownPermissions = useMemo(() => {
    const merged = [...asArray(commandOptions.permissions), ...FALLBACK_PERMISSIONS]
    return [...new Set(merged.map((p) => String(p || "").trim()).filter(Boolean))]
  }, [commandOptions.permissions])

  const knownHelpTopics = useMemo(() => {
    const merged = [...asArray(commandOptions.helpTopics), ...HELP_FALLBACK_TOPICS]
    return [...new Set(merged.map((p) => String(p || "").trim()).filter(Boolean))]
  }, [commandOptions.helpTopics])

  useEffect(() => {
    const handleVerseContextRequest = (event) => {
      const respond = event?.detail?.respond
      if (typeof respond !== "function") return
      const queryPreview = String(queryText || "").trim()
      const normalizedPreview = queryPreview.length > 1200 ? `${queryPreview.slice(0, 1200)}...` : queryPreview
      const activeDomain = String(sessionInfo?.context?.domain || "")
      const activeDb = String(sessionInfo?.context?.db || "")
      respond({
        pageKind: "vdb-portal",
        screen: "vdb portal",
        pathname: "/vdb-portal",
        mode,
        queryText,
        activeDomain,
        activeDb,
        focus: {
          kind: "vdb-query",
          label: activeDomain || activeDb ? `Active query in ${activeDomain || "default"}/${activeDb || "default"}` : "Active VDB query",
          identifier: [activeDomain, activeDb].filter(Boolean).join("/"),
          contentSummary: activeDomain || activeDb ? `Current query targets ${activeDomain || "default"} ${activeDb || ""}`.trim() : "Current VDB query editor contents",
          contentPreview: normalizedPreview,
        },
        relevanceHints: {
          focusPreferred: true,
          activeQuery: true,
        },
      })
    }

    const handleVerseApply = (event) => {
      const artifact = event?.detail?.artifact
      const respond = event?.detail?.respond
      if (artifact?.kind !== "vdb-query" || typeof respond !== "function") return
      try {
        const query = artifact?.vdbQuery
        if (!query || typeof query !== "string") {
          respond({ ok: false, message: "Verse did not return a valid VDB command." })
          return
        }
        setQueryText(vdbCommandText(query))
        respond({ ok: true, message: "Loaded the VDB query into the query console." })
      } catch (error) {
        respond({ ok: false, message: error?.message || "Failed to load the VDB query." })
      }
    }

    const handleVerseExecute = (event) => {
      const artifact = event?.detail?.artifact
      const respond = event?.detail?.respond
      if (artifact?.kind !== "vdb-query" || typeof respond !== "function") return
      const query = artifact?.vdbQuery
      if (!query || typeof query !== "string") {
        respond({ ok: false, message: "Verse did not return a valid VDB command." })
        return
      }
      try {
        setQueryText(vdbCommandText(query))
        Promise.resolve(runQueryRef.current?.(query))
          .then(() => {
            respond({ ok: true, message: "Loaded and ran the VDB query." })
          })
          .catch((error) => {
            respond({ ok: false, message: error?.message || "Failed to run the VDB query." })
          })
      } catch (error) {
        respond({ ok: false, message: error?.message || "Failed to execute the VDB query." })
      }
    }

    window.addEventListener("liwiro:verse-assistant-request-context", handleVerseContextRequest)
    window.addEventListener("liwiro:verse-assistant-apply", handleVerseApply)
    window.addEventListener("liwiro:verse-assistant-execute", handleVerseExecute)
    const pendingAction = consumePendingVerseAction("/vdb-portal")
    if (pendingAction?.artifact) {
      activatePendingVerseAction({
        pathname: "/vdb-portal",
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
  }, [mode, queryText, sessionInfo?.context?.db, sessionInfo?.context?.domain])

  const fetchConnectionInfo = useCallback(async () => {
    const data = await fetchAuthedJson(`${backend}/platform/vdb/connection`)
    const next = {
      vdb_transport: normalizeVdbTransportMode(data?.vdb_transport || data?.defaultVdbTransport || "unixsocket", Boolean(data?.supportsNamedPipe)),
      vdb_server_url: String(data?.vdb_server_url || ""),
      vdb_unix_socket_path: String(data?.vdb_unix_socket_path || ""),
      vdb_named_pipe_path: normalizeVdbNamedPipePath(data?.vdb_named_pipe_path || ""),
      vdb_app_username: String(data?.vdb_app_username || ""),
      vdb_super_admin_username: String(data?.vdb_super_admin_username || ""),
      has_saved_vdb_app_password: Boolean(data?.has_saved_vdb_app_password),
      has_saved_vdb_super_admin_password: Boolean(data?.has_saved_vdb_super_admin_password),
      can_use_app_mode: Boolean(data?.can_use_app_mode ?? true),
      can_use_super_admin_mode: Boolean(data?.can_use_super_admin_mode),
      liwiro_domain: String(data?.liwiro_domain || ""),
      liwiro_db: String(data?.liwiro_db || ""),
      supportsNamedPipe: Boolean(data?.supportsNamedPipe),
      defaultVdbTransport: normalizeVdbTransportMode(data?.defaultVdbTransport || "unixsocket", Boolean(data?.supportsNamedPipe)),
      defaultVdbServerUrl: String(data?.defaultVdbServerUrl || "http://127.0.0.1:1957"),
      defaultVdbUnixSocketPath: String(data?.defaultVdbUnixSocketPath || "/tmp/vdb.sock"),
      defaultVdbNamedPipePath: normalizeVdbNamedPipePath(data?.defaultVdbNamedPipePath || "\\\\.\\pipe\\verun_vdb"),
      defaultVdbExportOutDir: String(data?.defaultVdbExportOutDir || "/tmp/vdb-exports"),
    }
    setConnection(next)
    setCredentials((prev) => ({
      ...prev,
      username: mode === "app" ? (prev.username || next.vdb_app_username) : prev.username,
      vdb_transport: prev.vdb_transport || next.vdb_transport,
      vdb_server_url: prev.vdb_server_url || next.vdb_server_url,
      vdb_unix_socket_path: prev.vdb_unix_socket_path || next.vdb_unix_socket_path,
      vdb_named_pipe_path: normalizeVdbNamedPipePath(prev.vdb_named_pipe_path || next.vdb_named_pipe_path),
    }))
  }, [backend, mode])

  const fetchCommandOptions = useCallback(async () => {
    if (!portalToken) return
    try {
      const res = await fetch(`${backend}/platform/vdb/options`, {
        headers: { ...authHeaders(), "X-VDB-Portal-Token": portalToken },
      })
      if (!res.ok) return
      const data = await res.json().catch(() => ({}))
      setCommandOptions({
        domains: asArray(data?.domains).map((v) => String(v || "").trim()).filter(Boolean),
        dbs: asArray(data?.dbs).map((v) => String(v || "").trim()).filter(Boolean),
        collections: asArray(data?.collections).map((v) => String(v || "").trim()).filter(Boolean),
        models: asArray(data?.models).map((v) => String(v || "").trim()).filter(Boolean),
        scripts: asArray(data?.scripts).map((v) => String(v || "").trim()).filter(Boolean),
        users: asArray(data?.users).map((v) => String(v || "").trim()).filter(Boolean),
        roles: asArray(data?.roles).map((v) => String(v || "").trim()).filter(Boolean),
        permissions: asArray(data?.permissions).map((v) => String(v || "").trim()).filter(Boolean),
        helpTopics: asArray(data?.helpTopics).map((v) => String(v || "").trim()).filter(Boolean),
      })
    } catch {
      // Keep UI responsive even if options endpoint is unavailable.
    }
  }, [backend, portalToken])

  const fetchSessionSnapshot = useCallback(async (tokenOverride = portalToken) => {
    const activeToken = String(tokenOverride || "").trim()
    if (!activeToken) return
    try {
      const headers = { ...authHeaders(), "X-VDB-Portal-Token": activeToken }
      const [whoamiRes, contextRes] = await Promise.all([
        fetch(`${backend}/platform/vdb/whoami`, { headers }),
        fetch(`${backend}/platform/vdb/context`, { headers }),
      ])
      const whoami = whoamiRes.ok ? await whoamiRes.json().catch(() => ({})) : null
      const context = contextRes.ok ? await contextRes.json().catch(() => ({})) : null
      setSessionInfo((prev) => ({
        ...prev,
        ...(whoami ? { whoami } : {}),
        ...(context ? { context } : {}),
      }))
    } catch {
      // Keep the session usable even if the snapshot refresh fails.
    }
  }, [backend, portalToken])

  useEffect(() => {
    const load = async () => {
      if (showPortalProgress) {
        startOperation({
          title: "Loading VDB portal",
          detail: "Refreshing session info, connection details, and command options.",
        })
      }
      setLoading(true)
      try {
        const me = await fetchAuthedJson(`${backend}/auth/me`, { ttlMs: 2500 })
        setIsSuperAdmin(Boolean(me?.is_super_admin))
        await fetchConnectionInfo()
        if (showPortalProgress) {
          succeedOperation({
            title: "VDB portal ready",
            detail: "Connection details and session controls are loaded.",
          })
        }
      } catch (err) {
        if (err?.status === 401) {
          window.location.href = "/login"
          return
        }
        if (showPortalProgress) {
          failOperation({
            title: "VDB portal failed to load",
            detail: err?.message || "Failed to load VDB portal",
          })
        }
        toast.error(err?.message || "Failed to load VDB portal")
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [backend, failOperation, fetchConnectionInfo, showPortalProgress, startOperation, succeedOperation])

  useEffect(() => {
    if (!connection.can_use_super_admin_mode && mode === "super_admin") {
      setMode("app")
    }
  }, [mode, connection.can_use_super_admin_mode])

  useEffect(() => {
    setCredentials((prev) => ({
      ...prev,
      username: mode === "super_admin" ? "" : (connection.vdb_app_username || ""),
      password: "",
      vdb_transport: connection.vdb_transport || connection.defaultVdbTransport || "unixsocket",
    }))
  }, [mode, connection.vdb_app_username, connection.vdb_super_admin_username, connection.vdb_transport, connection.defaultVdbTransport])

  const connectSession = useCallback(async ({ silent = false } = {}) => {
    if (showPortalProgress && !silent) {
      startOperation({
        title: "Connecting to VDB",
        detail: "Authenticating the portal session and loading the current workspace context.",
      })
    }
    setBusy(true)
    try {
      const payload = {
        mode,
        vdb_transport: credentials.vdb_transport || connection.vdb_transport,
        username: mode === "super_admin" ? credentials.username : "",
        password: mode === "super_admin" ? credentials.password : "",
        vdb_server_url: credentials.vdb_server_url || connection.vdb_server_url,
        vdb_unix_socket_path: credentials.vdb_unix_socket_path || connection.vdb_unix_socket_path,
        vdb_named_pipe_path: credentials.vdb_named_pipe_path || connection.vdb_named_pipe_path,
        save_credentials: mode === "super_admin" ? saveSuperAdminCredentials : false,
      }
      const res = await fetch(`${backend}/platform/vdb/session`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(payload),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || "Failed to create VDB portal session")
      const nextPortalToken = String(data?.portalToken || "")
      setPortalToken(nextPortalToken)
      setSessionInfo(data || {})
      fetchSessionSnapshot(nextPortalToken)
      setLastResponse(JSON.stringify(data, null, 2))
      if (showPortalProgress && !silent) {
        succeedOperation({
          title: "VDB session connected",
          detail: `Connected as ${String(data?.username || "session").trim() || "session"}.`,
        })
      }
      if (!silent) toast.success("Connected to VDB portal session")
    } catch (err) {
      if (showPortalProgress && !silent) {
        failOperation({
          title: "Failed to connect to VDB",
          detail: err?.message || "Failed to connect",
        })
      }
      if (!silent) toast.error(err?.message || "Failed to connect")
    } finally {
      setBusy(false)
    }
  }, [backend, showPortalProgress, startOperation, succeedOperation, failOperation, mode, credentials.username, credentials.password, credentials.vdb_transport, credentials.vdb_server_url, credentials.vdb_unix_socket_path, credentials.vdb_named_pipe_path, connection.vdb_transport, connection.vdb_server_url, connection.vdb_unix_socket_path, connection.vdb_named_pipe_path, saveSuperAdminCredentials, fetchSessionSnapshot])

  useEffect(() => {
    if (loading || busy || autoConnectedAppMode || portalToken) return
    if (mode !== "app") return
    if (!connection.can_use_app_mode || !connection.has_saved_vdb_app_password) return
    setAutoConnectedAppMode(true)
    connectSession({ silent: true })
  }, [loading, busy, autoConnectedAppMode, portalToken, mode, connection, connectSession])

  useEffect(() => {
    fetchCommandOptions()
  }, [fetchCommandOptions])

  useEffect(() => {
    fetchSessionSnapshot()
  }, [fetchSessionSnapshot])

  useEffect(() => {
    setBuilder((prev) => {
      const next = { ...prev }
      if (!next.domain && connection.liwiro_domain) next.domain = connection.liwiro_domain
      if (!next.db && connection.liwiro_db) next.db = connection.liwiro_db
      if (!next.collection && commandOptions.collections[0]) next.collection = commandOptions.collections[0]
      if (!next.modelCollection && commandOptions.models[0]) next.modelCollection = commandOptions.models[0]
      if (!next.modelCollection && commandOptions.collections[0]) next.modelCollection = commandOptions.collections[0]
      if (!next.scriptName && commandOptions.scripts[0]) next.scriptName = commandOptions.scripts[0]
      if (!next.tumiUsername && commandOptions.users[0]) next.tumiUsername = commandOptions.users[0]
      if (!next.tumiRole && commandOptions.roles[0]) next.tumiRole = commandOptions.roles[0]
      if (!next.helpTopic && knownHelpTopics[0]) next.helpTopic = knownHelpTopics[0]
      if (!next.exportOutDir && connection.defaultVdbExportOutDir) next.exportOutDir = connection.defaultVdbExportOutDir
      return next
    })
  }, [connection.liwiro_domain, connection.liwiro_db, connection.defaultVdbExportOutDir, commandOptions, knownHelpTopics])

  const parsedLastResponse = useMemo(() => parseResponseJson(lastResponse), [lastResponse])
  const latestExport = useMemo(() => {
    const data = parsedLastResponse && typeof parsedLastResponse?.data === "object" ? parsedLastResponse.data : null
    const zipFile = String(data?.zip_file || "").trim()
    const outDir = String(data?.out_dir || "").trim()
    if (!zipFile && !outDir) return null
    return {
      zipFile,
      outDir,
      exportedDomains: asArray(data?.exported_domains).map((value) => String(value || "").trim()).filter(Boolean),
      skippedDomains: data?.skipped_domains && typeof data.skipped_domains === "object"
        ? Object.entries(data.skipped_domains).map(([domain, reason]) => ({
          domain: String(domain || "").trim(),
          reason: String(reason || "").trim(),
        }))
        : [],
    }
  }, [parsedLastResponse])

  const disconnectSession = async () => {
    if (!portalToken) return
    if (showPortalProgress) {
      startOperation({
        title: "Closing VDB session",
        detail: "Clearing the current portal token and session snapshot.",
      })
    }
    setBusy(true)
    try {
      await fetch(`${backend}/platform/vdb/session`, {
        method: "DELETE",
        headers: { ...authHeaders(), "X-VDB-Portal-Token": portalToken },
      })
    } finally {
      setPortalToken("")
      setSessionInfo({})
      setCommandOptions({
        domains: [], dbs: [], collections: [], models: [], scripts: [], users: [], roles: [], permissions: [], helpTopics: HELP_FALLBACK_TOPICS,
      })
      setBusy(false)
      if (showPortalProgress) {
        succeedOperation({
          title: "VDB session closed",
          detail: "The portal session has been cleared.",
        })
      }
      toast.success("VDB portal session closed")
    }
  }

  const parseJson = (text, fallbackLiteral) => {
    const source = String(text || "").trim()
    try {
      return JSON.parse(source || fallbackLiteral)
    } catch {
      throw new Error("VDB query fragments must be strict JSON")
    }
  }

  const hasEntries = (value) => {
    return value && typeof value === "object" && Object.keys(value).length > 0
  }

  const runQuery = async (queryOverride = null) => {
    if (!portalToken) {
      toast.error("Connect a VDB portal session first")
      return
    }

    let query = queryOverride
    if (query) {
      try {
        query = vdbCommandText(query)
      } catch (err) {
        toast.error(err?.message || "Invalid VDB query")
        return
      }
    }
    if (!query) {
      try {
        query = vdbCommandText(queryText)
      } catch (err) {
        toast.error(err?.message || "Invalid VDB query syntax")
        return
      }
    }

    if (showPortalProgress) {
      startOperation({
        title: "Running VDB query",
        detail: "Sending the command and waiting for the database response.",
      })
    }
    setBusy(true)
    try {
      const res = await fetch(`${backend}/platform/vdb/query`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
          "X-VDB-Portal-Token": portalToken,
        },
        body: JSON.stringify({ query }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || "VDB query failed")
      setLastResponse(JSON.stringify(data, null, 2))
      fetchCommandOptions()
      fetchSessionSnapshot()
      if (showPortalProgress) {
        succeedOperation({
          title: "VDB query completed",
          detail: "The latest response is now loaded in the console.",
        })
      }
      toast.success("Query executed")
    } catch (err) {
      if (showPortalProgress) {
        failOperation({
          title: "VDB query failed",
          detail: err?.message || "VDB query failed",
        })
      }
      toast.error(err?.message || "VDB query failed")
    } finally {
      setBusy(false)
    }
  }
  runQueryRef.current = runQuery

  const buildQueryFromBuilder = useCallback(() => {
    const f = builder.family
    if (f === "general") {
      if (builder.action === "whoami") return { action: "whoami" }
      if (builder.action === "context") return { action: "context" }
      return { action: "echo", value: builder.echoMessage || "hello" }
    }
    if (f === "help") return { action: "help", topic: builder.helpTopic || "commands" }
    if (f === "list") return { action: "list", resource: builder.listType || "domains" }

    if (f === "define") {
      if (builder.action === "domain") return { action: "define", resource: "domain", name: builder.domain }
      if (builder.action === "db") return { action: "define", resource: "db", name: builder.db }
      return { action: "define", resource: "db", domain: builder.domain, name: builder.db }
    }

    if (f === "use") {
      if (builder.action === "domain") return { action: "use", domain: builder.domain }
      if (builder.action === "db") return { action: "use", db: builder.db }
      return { action: "use", domain: builder.domain, db: builder.db }
    }

    if (f === "drop") {
      if (builder.action === "domain") return { action: "drop_domain", domain: builder.domain }
      if (builder.action === "db") return { action: "drop_db", db: builder.db }
      return { action: "drop_collection", collection: builder.collection }
    }

    if (f === "domain") {
      const domain = builder.domain
      if (builder.action === "suspend") return { action: "domain_suspend", domain }
      if (builder.action === "resume") return { action: "domain_resume", domain }
      return { action: "domain_status", domain, operation: "status" }
    }

    if (f === "model") {
      if (builder.action === "get") return { action: "model_get", model: builder.modelCollection }
      return { action: "model_delete", model: builder.modelCollection }
    }

    if (f === "crud") {
      if (builder.action === "create") {
        const collectionName = builder.collection || "collection"
        const payload = { [collectionName]: {} }
        const schema = parseJson(builder.createSchemaText, "{}")
        if (hasEntries(schema)) {
          payload[collectionName].schema = schema
        }
        const data = parseJson(builder.createDataText, "{}")
        if (hasEntries(data)) {
          payload[collectionName].data = data
        }
        return { action: "create_collection", collection: collectionName, ...payload[collectionName] }
      }
      if (builder.action === "read") return { action: "find", collection: builder.collection, where: parseJson(builder.readQueryText, "{}"), ...parseJson(builder.readArgsText, "{}") }
      if (builder.action === "update") return { action: "update", collection: builder.collection || "collection", where: parseJson(builder.writeQueryText, "{}"), data: parseJson(builder.writeDataText, "{}") }
      return { action: "delete", collection: builder.collection || "collection", where: parseJson(builder.writeQueryText, "{}") }
    }

    if (f === "script") {
      if (builder.action === "create") return { action: "script_create", name: builder.scriptName, service: builder.scriptService, code: builder.scriptCode }
      if (builder.action === "read") return { action: "script_read", name: builder.scriptName }
      if (builder.action === "execute") return { action: "script_execute", name: builder.scriptName, params: parseJson(builder.scriptParamsText, "{}") }
      return { action: "script_delete", name: builder.scriptName }
    }

    if (f === "transaction") return { action: `transaction_${builder.action || "begin"}` }

    if (f === "export") {
      const selectedDomains = asArray(builder.exportDomains).filter(Boolean)
      return {
        action: "export",
        domains: selectedDomains.length ? selectedDomains : "*",
        package: builder.exportPackage || undefined,
        out_dir: builder.exportOutDir || undefined,
      }
    }

    if (f === "tumi") {
      const action = builder.tumiAction
      if (action === "list") return { action: "tumi", operation: "list", resource: builder.tumiListType || "users" }
      if (action === "transfer") return { action: "tumi", operation: "transfer", username: builder.tumiUsername, domain: builder.tumiDomain }
      if (action === "create") {
        return { action: "tumi", operation: "create", username: builder.tumiUsername, email: builder.tumiEmail, password: builder.tumiPassword, role: builder.tumiRole || "APPLICATION" }
      }
      if (action === "delete") return { action: "tumi", operation: "delete", username: builder.tumiUsername }
      if (action === "read") return { action: "tumi", operation: "read", role: builder.tumiRole || "" }

      const out = { username: builder.tumiUsername }
      if (builder.tumiRole) out.role = builder.tumiRole
      if (builder.tumiDomain) out.domain = builder.tumiDomain
      if (builder.tumiDb) out.db = builder.tumiDb
      if (builder.tumiCollection) out.collection = builder.tumiCollection
      if (asArray(builder.tumiPermissions).length) out.permissions = asArray(builder.tumiPermissions)
      return { action: "tumi", operation: action, ...out }
    }

    return { action: "whoami" }
  }, [builder])

  const applyBuiltQuery = () => {
    if (builder.family === "export" && !String(builder.exportOutDir || "").trim()) {
      toast.error("Export location is required")
      return null
    }
    try {
      const query = buildQueryFromBuilder()
      setQueryText(vdbCommandText(query))
      return query
    } catch (err) {
      toast.error(err?.message || "Invalid VDB query syntax")
      return null
    }
  }

  const runBuiltQuery = () => {
    const query = applyBuiltQuery()
    if (!query) return
    runQuery(query)
  }

  const toggleExportDomain = (domain) => {
    setBuilder((prev) => {
      const current = new Set(asArray(prev.exportDomains))
      if (current.has(domain)) current.delete(domain)
      else current.add(domain)
      return { ...prev, exportDomains: Array.from(current) }
    })
  }

  const togglePermission = (perm) => {
    setBuilder((prev) => {
      const current = new Set(asArray(prev.tumiPermissions))
      if (current.has(perm)) current.delete(perm)
      else current.add(perm)
      return { ...prev, tumiPermissions: Array.from(current) }
    })
  }

  const actionOptions = useMemo(() => {
    if (builder.family === "general") return GENERAL_ACTIONS
    if (builder.family === "define") return DEFINE_USE_DROP_ACTIONS.define
    if (builder.family === "use") return DEFINE_USE_DROP_ACTIONS.use
    if (builder.family === "drop") return DEFINE_USE_DROP_ACTIONS.drop
    if (builder.family === "domain") return DOMAIN_ACTIONS
    if (builder.family === "model") return MODEL_ACTIONS
    if (builder.family === "crud") return CRUD_ACTIONS
    if (builder.family === "script") return SCRIPT_ACTIONS
    if (builder.family === "transaction") return TRANSACTION_ACTIONS
    return []
  }, [builder.family])

  useEffect(() => {
    if (builder.family === "tumi" || builder.family === "help" || builder.family === "list" || builder.family === "export") return
    if (!actionOptions.includes(builder.action)) {
      setBuilder((prev) => ({ ...prev, action: actionOptions[0] || "whoami" }))
    }
  }, [actionOptions, builder.family, builder.action])

  if (loading) {
    return <div className="app-page py-8 text-sm text-slate-300">Loading VDB portal...</div>
  }

  return (
    <div className="w-full app-stack">
      <section className="app-hero">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="app-eyebrow">VDB Console</p>
            <h1 className="app-title mt-4">Query VDB from a guided studio</h1>
            <p className="app-copy mt-3">Open an app or super-admin session, build commands visually, and keep the command console available beside it.</p>
          </div>
          {portalToken && (
            <div className="rounded-full border border-slate-200/90 bg-white/[0.84] px-4 py-2 text-sm font-medium text-slate-700 dark:border-slate-800 dark:bg-slate-950/[0.72] dark:text-slate-200">
              Connected as {sessionInfo?.username || credentials.username || "session"}
            </div>
          )}
        </div>
      </section>

      {showPortalProgress && portalOperationStatus?.visible ? (
        <OperationStatusPanel status={portalOperationStatus} />
      ) : null}

      <div className="app-rail-layout">
        <aside className="app-rail">
          <Card className="rounded-xl border-slate-200 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <CardHeader>
          <CardTitle className="text-xl text-slate-900 dark:text-slate-100">VDB Console Session</CardTitle>
        </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3">
            <div className="min-w-0 rounded-lg border border-slate-200/80 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-950/50">
              <Label>Transport</Label>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <p className="break-words text-sm font-medium text-slate-700 dark:text-slate-300">{vdbTransportLabel(connection.vdb_transport, connection.supportsNamedPipe)}</p>
                <VdbTransportStatusIndicator status={savedVdbStatus} className="border-slate-200 bg-white text-slate-700 dark:border-slate-800 dark:bg-slate-950/70 dark:text-slate-200" />
              </div>
            </div>
            <div className="min-w-0 rounded-lg border border-slate-200/80 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-950/50">
              <Label>VDB Server</Label>
              <p className="mt-1 break-all text-sm font-medium text-slate-700 dark:text-slate-300">{connection.vdb_server_url || "-"}</p>
            </div>
            <div className="min-w-0 rounded-lg border border-slate-200/80 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-950/50">
              <Label>{connection.vdb_transport === "namedpipe" ? "Named Pipe" : "Socket Path"}</Label>
              <p className="mt-1 break-all text-sm font-medium text-slate-700 dark:text-slate-300">{connection.vdb_transport === "namedpipe" ? (connection.vdb_named_pipe_path || "-") : (connection.vdb_unix_socket_path || "-")}</p>
            </div>
            <div className="min-w-0 rounded-lg border border-slate-200/80 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-950/50">
              <Label>App User</Label>
              <p className="mt-1 break-words text-sm font-medium text-slate-700 dark:text-slate-300">{connection.vdb_app_username || "-"}</p>
            </div>
            <div className="min-w-0 rounded-lg border border-slate-200/80 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-950/50">
              <Label>Liwiro Domain</Label>
              <p className="mt-1 break-words text-sm font-medium text-slate-700 dark:text-slate-300">{connection.liwiro_domain || "-"}</p>
            </div>
            <div className="min-w-0 rounded-lg border border-slate-200/80 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-950/50">
              <Label>Liwiro DB</Label>
              <p className="mt-1 break-words text-sm font-medium text-slate-700 dark:text-slate-300">{connection.liwiro_db || "-"}</p>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <label className="flex items-center gap-2 rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700">
              <input type="radio" name="vdb-mode" checked={mode === "app"} onChange={() => setMode("app")} />
              Sign in as configured app user
            </label>
            {connection.can_use_super_admin_mode && (
              <label className="flex items-center gap-2 rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700">
                <input type="radio" name="vdb-mode" checked={mode === "super_admin"} onChange={() => setMode("super_admin")} />
                Sign in as VDB super admin
              </label>
            )}
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <div className="flex items-center justify-between gap-3">
                <Label>Transport</Label>
                <VdbTransportStatusIndicator status={selectedVdbStatus} className="border-slate-200 bg-white text-slate-700 dark:border-slate-800 dark:bg-slate-950/70 dark:text-slate-200" />
              </div>
              <select
                className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm dark:border-slate-700 dark:bg-slate-950"
                value={credentials.vdb_transport}
                onChange={(e) => setCredentials((p) => ({ ...p, vdb_transport: e.target.value }))}
              >
                {vdbTransportOptions({ supportsNamedPipe: connection.supportsNamedPipe }).map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </div>
            <div>
              <Label>{selectedTargetField.label}</Label>
              <Input
                value={selectedTargetField.value}
                onChange={(e) => setCredentials((p) => ({ ...p, [selectedTargetField.key]: e.target.value }))}
                placeholder={selectedTargetField.placeholder}
              />
            </div>
          </div>

          {selectedVdbStatus?.detail ? (
            <p className="text-xs text-slate-500 dark:text-slate-400">{selectedVdbStatus.detail}</p>
          ) : null}

          {selectedVdbStatus?.paused && typeof selectedVdbStatus?.retry === "function" ? (
            <div>
              <Button type="button" size="sm" variant="outline" onClick={selectedVdbStatus.retry}>
                Retry transport check
              </Button>
            </div>
          ) : null}

          {mode === "super_admin" ? (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              <div><Label>Super Admin Username</Label><Input value={credentials.username} onChange={(e) => setCredentials((p) => ({ ...p, username: e.target.value }))} placeholder={connection.vdb_super_admin_username || "super-admin username"} /></div>
              <div><Label>Super Admin Password</Label><PasswordInput value={credentials.password} onChange={(e) => setCredentials((p) => ({ ...p, password: e.target.value }))} placeholder={connection.has_saved_vdb_super_admin_password ? "Leave empty to use saved password" : "super-admin password"} /></div>
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              <div><Label>App Username</Label><Input value={connection.vdb_app_username || "-"} readOnly /></div>
              <div><Label>App Password</Label><Input value={connection.has_saved_vdb_app_password ? "Saved in Liwiro auth store" : "Not saved"} readOnly /></div>
            </div>
          )}

          {mode === "super_admin" && isSuperAdmin && (
            <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
              <input type="checkbox" checked={saveSuperAdminCredentials} onChange={(e) => setSaveSuperAdminCredentials(Boolean(e.target.checked))} />
              Save super admin credentials
            </label>
          )}

          <div className="flex flex-wrap gap-2">
            <Button className="brand-solid h-9" onClick={() => connectSession()} disabled={busy}>{busy ? "Connecting..." : "Connect Session"}</Button>
            <Button variant="outline" className="h-9" onClick={disconnectSession} disabled={busy || !canQuery}>Disconnect Session</Button>
            <Button variant="outline" className="h-9" onClick={fetchConnectionInfo} disabled={busy}>Refresh Connection</Button>
            <Button variant="outline" className="h-9" onClick={fetchCommandOptions} disabled={busy || !canQuery}>Refresh Options</Button>
          </div>
          {portalToken && <p className="text-xs text-slate-500 dark:text-slate-300">Active session: <code>{sessionInfo?.mode || mode}</code> as <code>{sessionInfo?.username || credentials.username}</code></p>}
        </CardContent>
          </Card>
        </aside>

        <div className="app-main-column">
      <Card className="rounded-xl border-slate-200 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <CardHeader>
          <CardTitle className="text-xl text-slate-900 dark:text-slate-100">VDB Command Studio</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-lg border border-sky-300/20 bg-sky-500/[0.06] px-3 py-2 text-sm text-slate-600 dark:text-slate-300">
            Context-aware choices come from the active VDB session. <code>use</code> only offers domains and databases visible to you; commands that create resources still allow a new name.
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            <div>
              <Label>Command Family</Label>
              <select className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm dark:border-slate-700 dark:bg-slate-950" value={builder.family} onChange={(e) => setBuilder((p) => ({ ...p, family: e.target.value }))}>
                {FAMILY_OPTIONS.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
              </select>
            </div>

            {actionOptions.length > 0 && (
              <div>
                <Label>Action</Label>
                <select className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm dark:border-slate-700 dark:bg-slate-950" value={builder.action} onChange={(e) => setBuilder((p) => ({ ...p, action: e.target.value }))}>
                  {actionOptions.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                </select>
              </div>
            )}

            {builder.family === "list" && (
              <div>
                <Label>List Type</Label>
                <select className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm dark:border-slate-700 dark:bg-slate-950" value={builder.listType} onChange={(e) => setBuilder((p) => ({ ...p, listType: e.target.value }))}>
                  {LIST_OPTIONS.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                </select>
              </div>
            )}

            {builder.family === "help" && (
              <div>
                <Label>Help Topic</Label>
                <select className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm dark:border-slate-700 dark:bg-slate-950" value={builder.helpTopic} onChange={(e) => setBuilder((p) => ({ ...p, helpTopic: e.target.value }))}>
                  {knownHelpTopics.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                </select>
              </div>
            )}

            {builder.family === "tumi" && (
              <div>
                <Label>Tumi Action</Label>
                <select className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm dark:border-slate-700 dark:bg-slate-950" value={builder.tumiAction} onChange={(e) => setBuilder((p) => ({ ...p, tumiAction: e.target.value }))}>
                  {TUMI_ACTIONS.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                </select>
              </div>
            )}

            {builder.family === "tumi" && builder.tumiAction === "list" && (
              <div>
                <Label>Tumi List Type</Label>
                <select className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm dark:border-slate-700 dark:bg-slate-950" value={builder.tumiListType} onChange={(e) => setBuilder((p) => ({ ...p, tumiListType: e.target.value }))}>
                  {TUMI_LIST_OPTIONS.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                </select>
              </div>
            )}
          </div>

          <div className="grid gap-3 md:grid-cols-4">
            {builder.family === "general" && builder.action === "echo" && (
              <div><Label>Echo Message</Label><Input value={builder.echoMessage} onChange={(e) => setBuilder((p) => ({ ...p, echoMessage: e.target.value }))} /></div>
            )}

            {(builder.family === "define" || builder.family === "use" || builder.family === "drop" || builder.family === "domain" || builder.family === "tumi") && (
              <>
                <div>
                  <Label>Domain</Label>
                  {builder.family === "use" ? (
                    <select className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm dark:border-slate-700 dark:bg-slate-950" value={builder.domain} onChange={(e) => setBuilder((p) => ({ ...p, domain: e.target.value }))}>
                      <option value="">Select accessible domain</option>
                      {asArray(commandOptions.domains).map((domain) => <option key={domain} value={domain}>{domain}</option>)}
                    </select>
                  ) : <Input list="vdb-domains" value={builder.domain} onChange={(e) => setBuilder((p) => ({ ...p, domain: e.target.value }))} placeholder="Select or type domain" />}
                </div>
                <div>
                  <Label>DB</Label>
                  {builder.family === "use" ? (
                    <select className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm dark:border-slate-700 dark:bg-slate-950" value={builder.db} onChange={(e) => setBuilder((p) => ({ ...p, db: e.target.value }))}>
                      <option value="">Select accessible database</option>
                      {asArray(commandOptions.dbs).map((db) => <option key={db} value={db}>{db}</option>)}
                    </select>
                  ) : <Input list="vdb-dbs" value={builder.db} onChange={(e) => setBuilder((p) => ({ ...p, db: e.target.value }))} placeholder="Select or type db" />}
                </div>
              </>
            )}

            {(builder.family === "drop" || builder.family === "crud" || builder.family === "tumi") && (
              <div>
                <Label>Collection</Label>
                <Input list="vdb-collections" value={builder.collection} onChange={(e) => setBuilder((p) => ({ ...p, collection: e.target.value }))} placeholder="Select collection" />
              </div>
            )}

            {builder.family === "model" && (
              <div>
                <Label>Model Collection</Label>
                <Input list="vdb-models" value={builder.modelCollection} onChange={(e) => setBuilder((p) => ({ ...p, modelCollection: e.target.value }))} placeholder="Select model" />
              </div>
            )}

            {builder.family === "script" && (
              <>
                <div>
                  <Label>Script Name</Label>
                  <Input list="vdb-scripts" value={builder.scriptName} onChange={(e) => setBuilder((p) => ({ ...p, scriptName: e.target.value }))} placeholder="Select or type script" />
                </div>
                <div><Label>Service</Label><Input value={builder.scriptService} onChange={(e) => setBuilder((p) => ({ ...p, scriptService: e.target.value }))} placeholder="utils" /></div>
              </>
            )}

            {builder.family === "tumi" && builder.tumiAction !== "list" && (
              <>
                <div>
                  <Label>Username</Label>
                  <Input list="vdb-users" value={builder.tumiUsername} onChange={(e) => setBuilder((p) => ({ ...p, tumiUsername: e.target.value }))} placeholder="Select user" />
                </div>
                {(builder.tumiAction === "create" || builder.tumiAction === "read" || builder.tumiAction === "grant" || builder.tumiAction === "revoke") && (
                  <div>
                    <Label>Role</Label>
                    <Input list="vdb-roles" value={builder.tumiRole} onChange={(e) => setBuilder((p) => ({ ...p, tumiRole: e.target.value }))} placeholder="Select role" />
                  </div>
                )}
                {(builder.tumiAction === "transfer" || builder.tumiAction === "grant" || builder.tumiAction === "revoke") && (
                  <div>
                    <Label>Tumi Domain</Label>
                    <Input list="vdb-domains" value={builder.tumiDomain} onChange={(e) => setBuilder((p) => ({ ...p, tumiDomain: e.target.value }))} placeholder="Select domain" />
                  </div>
                )}
                {(builder.tumiAction === "grant" || builder.tumiAction === "revoke") && (
                  <div>
                    <Label>Tumi DB</Label>
                    <Input list="vdb-dbs" value={builder.tumiDb} onChange={(e) => setBuilder((p) => ({ ...p, tumiDb: e.target.value }))} placeholder="Select db" />
                  </div>
                )}
                {(builder.tumiAction === "grant" || builder.tumiAction === "revoke") && (
                  <div>
                    <Label>Tumi Collection</Label>
                    <Input list="vdb-collections" value={builder.tumiCollection} onChange={(e) => setBuilder((p) => ({ ...p, tumiCollection: e.target.value }))} placeholder="Select collection" />
                  </div>
                )}
              </>
            )}
          </div>

          {builder.family === "export" && (
            <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-950/40">
              <p className="text-sm font-medium text-slate-800 dark:text-slate-100">Export Targets</p>
              <div className="flex flex-wrap gap-3">
                <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
                  <input
                    type="checkbox"
                    checked={asArray(builder.exportDomains).length === 0}
                    onChange={(e) => setBuilder((p) => ({ ...p, exportDomains: e.target.checked ? [] : asArray(commandOptions.domains) }))}
                  />
                  All visible domains
                </label>
              </div>
              {asArray(commandOptions.domains).length > 0 && (
                <div className="grid gap-2 md:grid-cols-3">
                  {commandOptions.domains.map((domain) => (
                    <label key={domain} className="flex items-center gap-2 rounded border border-slate-200 px-2 py-1.5 text-sm dark:border-slate-700">
                      <input type="checkbox" checked={asArray(builder.exportDomains).includes(domain)} onChange={() => toggleExportDomain(domain)} />
                      {domain}
                    </label>
                  ))}
                </div>
              )}
              <div className="grid gap-3 md:grid-cols-2">
                <div>
                  <Label>Export Location</Label>
                  <Input
                    value={builder.exportOutDir}
                    onChange={(e) => setBuilder((p) => ({ ...p, exportOutDir: e.target.value }))}
                    placeholder={connection.defaultVdbExportOutDir || "/tmp/vdb-exports"}
                  />
                </div>
                <div>
                  <Label>Package Name (optional)</Label>
                  <Input value={builder.exportPackage} onChange={(e) => setBuilder((p) => ({ ...p, exportPackage: e.target.value }))} placeholder="authcore-backup" />
                </div>
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-300">
                Export location is required and is sent to VDB as <code>out_dir</code>. VDB creates the destination directory when possible and writes only the final zip there.
              </p>
            </div>
          )}

          {(builder.family === "tumi" && (builder.tumiAction === "grant" || builder.tumiAction === "revoke")) && (
            <div className="space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-950/40">
              <p className="text-sm font-medium text-slate-800 dark:text-slate-100">Permissions</p>
              <div className="grid gap-2 md:grid-cols-3">
                {knownPermissions.map((perm) => (
                  <label key={perm} className="flex items-center gap-2 rounded border border-slate-200 px-2 py-1.5 text-sm dark:border-slate-700">
                    <input type="checkbox" checked={asArray(builder.tumiPermissions).includes(perm)} onChange={() => togglePermission(perm)} />
                    {perm}
                  </label>
                ))}
              </div>
            </div>
          )}

          {(builder.family === "crud" || builder.family === "script" || (builder.family === "tumi" && builder.tumiAction === "create")) && (
            <div className="grid gap-3 md:grid-cols-2">
              {builder.family === "crud" && builder.action === "create" && (
                <div className="space-y-3">
                  <div>
                    <Label>Collection Schema (optional)</Label>
                    <JsonTextarea
                      value={builder.createSchemaText}
                      onChange={(e) => setBuilder((p) => ({ ...p, createSchemaText: e.target.value }))}
                      className="min-h-[160px] font-mono text-xs"
                      placeholder='{"id":{"type":"string","required":true},"active":{"type":"bool","default":true}}'
                    />
                  </div>
                  <div>
                    <Label>Initial Document (optional)</Label>
                    <JsonTextarea
                      value={builder.createDataText}
                      onChange={(e) => setBuilder((p) => ({ ...p, createDataText: e.target.value }))}
                      className="min-h-[160px] font-mono text-xs"
                      placeholder='{"name":"Alex","age":30}'
                    />
                  </div>
                </div>
              )}
              {builder.family === "crud" && builder.action === "read" && <><JsonTextarea value={builder.readQueryText} onChange={(e) => setBuilder((p) => ({ ...p, readQueryText: e.target.value }))} className="min-h-[180px] font-mono text-xs" placeholder='{"status":{"$eq":"active"}}' /><JsonTextarea value={builder.readArgsText} onChange={(e) => setBuilder((p) => ({ ...p, readArgsText: e.target.value }))} className="min-h-[180px] font-mono text-xs" placeholder='{"limit":25}' /></>}
              {builder.family === "crud" && (builder.action === "update" || builder.action === "delete") && <><JsonTextarea value={builder.writeQueryText} onChange={(e) => setBuilder((p) => ({ ...p, writeQueryText: e.target.value }))} className="min-h-[180px] font-mono text-xs" placeholder='{"_id":{"$eq":"u1"}}' />{builder.action === "update" && <JsonTextarea value={builder.writeDataText} onChange={(e) => setBuilder((p) => ({ ...p, writeDataText: e.target.value }))} className="min-h-[180px] font-mono text-xs" placeholder='{"active":false}' />}</>}
              {builder.family === "script" && builder.action === "create" && <Textarea value={builder.scriptCode} onChange={(e) => setBuilder((p) => ({ ...p, scriptCode: e.target.value }))} className="min-h-[220px] border-sky-800 bg-sky-950 font-mono text-xs text-sky-100" placeholder="print('hello')" />}
              {builder.family === "script" && builder.action === "execute" && <JsonTextarea value={builder.scriptParamsText} onChange={(e) => setBuilder((p) => ({ ...p, scriptParamsText: e.target.value }))} className="min-h-[180px] font-mono text-xs" placeholder='{"collection":"users"}' />}
              {builder.family === "tumi" && builder.tumiAction === "create" && <><Input value={builder.tumiEmail} onChange={(e) => setBuilder((p) => ({ ...p, tumiEmail: e.target.value }))} placeholder="email" /><PasswordInput value={builder.tumiPassword} onChange={(e) => setBuilder((p) => ({ ...p, tumiPassword: e.target.value }))} placeholder="password" /></>}
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            <Button variant="outline" className="h-9" onClick={applyBuiltQuery}>Apply to Query Editor</Button>
            <Button className="brand-solid h-9" onClick={runBuiltQuery} disabled={!canQuery || busy}>Run Built Query</Button>
          </div>

          <datalist id="vdb-domains">{asArray(commandOptions.domains).map((d) => <option key={d} value={d} />)}</datalist>
          <datalist id="vdb-dbs">{asArray(commandOptions.dbs).map((d) => <option key={d} value={d} />)}</datalist>
          <datalist id="vdb-collections">{asArray(commandOptions.collections).map((d) => <option key={d} value={d} />)}</datalist>
          <datalist id="vdb-models">{asArray(commandOptions.models).map((d) => <option key={d} value={d} />)}</datalist>
          <datalist id="vdb-scripts">{asArray(commandOptions.scripts).map((d) => <option key={d} value={d} />)}</datalist>
          <datalist id="vdb-users">{asArray(commandOptions.users).map((d) => <option key={d} value={d} />)}</datalist>
          <datalist id="vdb-roles">{asArray(commandOptions.roles).map((d) => <option key={d} value={d} />)}</datalist>
        </CardContent>
      </Card>

      <div className="grid gap-5 2xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card className="rounded-xl border-slate-200 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <CardHeader>
            <CardTitle className="text-xl text-slate-900 dark:text-slate-100">VDB Query Console</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <JsonTextarea value={queryText} onChange={(e) => setQueryText(e.target.value)} className="min-h-[420px] font-mono text-xs" placeholder="read domains" />
            <div className="flex gap-2">
              <Button className="brand-solid h-9" onClick={() => runQuery(null)} disabled={!canQuery || busy}>Run Query</Button>
              <Button variant="outline" className="h-9" onClick={() => setQueryText("read domains")}>Reset Query</Button>
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-xl border-slate-200 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0">
            <CardTitle className="text-xl text-slate-900 dark:text-slate-100">VDB Output Console</CardTitle>
            <CopyIconButton
              text={lastResponse}
              label="Copy VDB output"
              successMessage="VDB output copied"
              errorMessage="Failed to copy VDB output"
              className="border-white/10 bg-[#12304d] text-sky-100 hover:bg-[#193d60] hover:text-white"
            />
          </CardHeader>
          <CardContent>
            {latestExport && (
              <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50/80 p-4 text-sm text-emerald-950 dark:border-emerald-900/70 dark:bg-emerald-950/30 dark:text-emerald-100">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold">Latest Export</p>
                    <p className="mt-1 break-all">ZIP: <code>{latestExport.zipFile || "-"}</code></p>
                    <p className="mt-1 break-all">Out Dir: <code>{latestExport.outDir || "-"}</code></p>
                  </div>
                  <div className="flex gap-2">
                    {latestExport.zipFile ? (
                      <CopyIconButton
                        text={latestExport.zipFile}
                        label="Copy export zip path"
                        successMessage="Export zip path copied"
                        errorMessage="Failed to copy export zip path"
                        className="border-emerald-300 bg-white text-emerald-800 hover:bg-emerald-100 hover:text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-100 dark:hover:bg-emerald-900/70"
                      />
                    ) : null}
                    {latestExport.outDir ? (
                      <CopyIconButton
                        text={latestExport.outDir}
                        label="Copy export directory"
                        successMessage="Export directory copied"
                        errorMessage="Failed to copy export directory"
                        className="border-emerald-300 bg-white text-emerald-800 hover:bg-emerald-100 hover:text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-100 dark:hover:bg-emerald-900/70"
                      />
                    ) : null}
                  </div>
                </div>
                {latestExport.exportedDomains.length > 0 ? (
                  <p className="mt-3">Exported: {latestExport.exportedDomains.join(", ")}</p>
                ) : null}
                {latestExport.skippedDomains.length > 0 ? (
                  <p className="mt-2">Skipped: {latestExport.skippedDomains.map((item) => `${item.domain} (${item.reason})`).join(", ")}</p>
                ) : null}
              </div>
            )}
            <div className="min-w-0 overflow-hidden rounded-xl bg-sky-950 px-2 py-2">
              <Textarea
                value={lastResponse}
                readOnly
                style={{ height: `${responseHeight(lastResponse, 420, 1080)}px` }}
                className="min-h-[420px] resize-y overflow-x-hidden border-0 bg-transparent px-4 py-3 font-mono text-xs leading-5 text-sky-100 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
              />
            </div>
          </CardContent>
        </Card>
      </div>

      <VdbRbacAdmin backend={backend} portalToken={portalToken} title="VDB RBAC / TUMI" />
        </div>
      </div>
    </div>
  )
}
