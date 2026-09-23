// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  Check,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Eraser,
  FileCode2,
  FolderOpen,
  PencilLine,
  Play,
  Plus,
  RefreshCw,
  Save,
  SquareTerminal,
  Trash2,
  X,
} from "lucide-react"
import { toast } from "sonner"

import { authHeaders } from "@/lib/auth"
import { fetchAuthedJson } from "@/lib/authed-json-cache"
import { parseJsonLikeObject } from "@/lib/json-editor"
import { applyMediaStorageEnvPreset, envObjectToText, MEDIA_STORAGE_ENV_PRESETS, parseEnvText } from "@/lib/media-storage-presets"
import { activatePendingVerseAction, consumePendingVerseAction } from "@/lib/verse-actions"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { JsonTextarea } from "@/components/ui/json-textarea"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { VITerminalPanel } from "@/components/vi/vi-terminal-panel"
import { OperationStatusPanel } from "@/components/ui/operation-status-panel"
import { useOperationStatus } from "@/lib/operation-status"
import { isFeatureEnabled, usePlatformFeatureFlags } from "@/lib/platform-flags"

const DEFAULT_FILE_PATH = "scratch/playground.versa"
const VI_PORTAL_EDITOR_STATE_KEY = "liwiro:vi-portal:editor-state"

function createBlankEditorState() {
  return {
    originalPath: "",
    path: "",
    content: "",
  }
}

function loadSavedEditorState() {
  if (typeof window === "undefined") return null
  try {
    const raw = window.localStorage.getItem(VI_PORTAL_EDITOR_STATE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== "object") return null
    return {
      selectedFile: String(parsed.selectedFile || "").trim(),
      expandedWorkspaceFolders: parsed.expandedWorkspaceFolders && typeof parsed.expandedWorkspaceFolders === "object"
        ? parsed.expandedWorkspaceFolders
        : {},
      editor: {
        originalPath: String(parsed.editor?.originalPath || "").trim(),
        path: String(parsed.editor?.path || "").trim(),
        content: String(parsed.editor?.content || ""),
      },
    }
  } catch {
    return null
  }
}

function saveEditorState({ selectedFile = "", expandedWorkspaceFolders = {}, editor = createBlankEditorState() } = {}) {
  if (typeof window === "undefined") return
  window.localStorage.setItem(
    VI_PORTAL_EDITOR_STATE_KEY,
    JSON.stringify({
      selectedFile: String(selectedFile || "").trim(),
      expandedWorkspaceFolders: expandedWorkspaceFolders && typeof expandedWorkspaceFolders === "object" ? expandedWorkspaceFolders : {},
      editor: {
        originalPath: String(editor?.originalPath || "").trim(),
        path: String(editor?.path || "").trim(),
        content: String(editor?.content || ""),
      },
    }),
  )
}

function workspaceAncestorFolders(pathValue) {
  const parts = String(pathValue || "")
    .replace(/\\/g, "/")
    .split("/")
    .filter(Boolean)
  const folderPaths = []
  for (let index = 0; index < parts.length - 1; index += 1) {
    folderPaths.push(parts.slice(0, index + 1).join("/"))
  }
  return folderPaths
}

function createWorkspaceNode(name = "", path = "") {
  return {
    name,
    path,
    folders: new Map(),
    files: [],
  }
}

function finalizeWorkspaceNode(node) {
  return {
    name: node.name,
    path: node.path,
    files: [...node.files].sort((left, right) => String(left?.name || left?.path || "").localeCompare(String(right?.name || right?.path || ""))),
    folders: [...node.folders.values()]
      .map((child) => finalizeWorkspaceNode(child))
      .sort((left, right) => left.name.localeCompare(right.name)),
  }
}

function buildWorkspaceTree(files) {
  const root = createWorkspaceNode("", "")
  const fileMetaByPath = new Map()
  ;(Array.isArray(files) ? files : []).forEach((file) => {
    const normalizedPath = String(file?.path || "")
      .replace(/\\/g, "/")
      .replace(/^\.\/+/, "")
      .replace(/\/+$/, "")
    if (!normalizedPath) return
    const parts = normalizedPath.split("/").filter(Boolean)
    if (!parts.length) return

    let cursor = root
    let folderPath = ""
    for (let index = 0; index < parts.length - 1; index += 1) {
      const part = parts[index]
      folderPath = folderPath ? `${folderPath}/${part}` : part
      if (!cursor.folders.has(part)) {
        cursor.folders.set(part, createWorkspaceNode(part, folderPath))
      }
      cursor = cursor.folders.get(part)
    }

    const normalizedFile = {
      ...file,
      name: String(file?.name || parts[parts.length - 1] || normalizedPath),
      path: normalizedPath,
    }
    cursor.files.push(normalizedFile)
    fileMetaByPath.set(normalizedPath, normalizedFile)
  })
  return {
    tree: finalizeWorkspaceNode(root),
    fileMetaByPath,
  }
}

function consoleLinesFromPayload(payload, emptyFallback = "") {
  const entries = []
  const seen = new Set()

  function push(value, prefix = "") {
    const normalized = String(value || "").replace(/\r\n/g, "\n").trim()
    if (!normalized) return
    const next = prefix ? `${prefix}${normalized}` : normalized
    if (seen.has(next)) return
    seen.add(next)
    entries.push(next)
  }

  push(payload?.output)
  push(payload?.stdout)
  push(payload?.stderr)

  const errorText = String(payload?.error || "").trim()
  if (errorText && !seen.has(errorText)) {
    push(errorText, "Error: ")
  }

  if (!entries.length && emptyFallback) {
    entries.push(emptyFallback)
  }

  return entries
}

function formatConsoleEvent(label, detail = "") {
  const timestamp = new Intl.DateTimeFormat([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date())
  const entries = [`[${timestamp}] ${String(label || "").trim()}`]
  const normalizedDetail = String(detail || "").replace(/\r\n/g, "\n").trim()
  if (normalizedDetail) {
    entries.push(normalizedDetail)
  }
  return entries.join("\n")
}

export default function VIPortalPage() {
  const backend = process.env.NEXT_PUBLIC_LIWIRO_BACKEND || "http://127.0.0.1:5000"
  const terminalPanelRef = useRef(null)
  const pendingVerseActionRef = useRef(null)
  const fetchFilesRef = useRef(null)
  const {
    status: portalOperationStatus,
    startOperation,
    succeedOperation,
    failOperation,
  } = useOperationStatus({ autoHideSuccessMs: 1800 })
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [editorStateHydrated, setEditorStateHydrated] = useState(false)
  const [connection, setConnection] = useState({
    verun_root: "",
    vi_jar_path: "",
    vi_jar_exists: false,
    source_dir: "",
    files_count: 0,
    terminal_active: false,
    terminal_prompt: "> ",
  })
  const [files, setFiles] = useState([])
  const [selectedFile, setSelectedFile] = useState("")
  const [expandedWorkspaceFolders, setExpandedWorkspaceFolders] = useState({})
  const [editor, setEditor] = useState({
    originalPath: "",
    path: "",
    content: "",
  })
  const [sourceDirDraft, setSourceDirDraft] = useState("")
  const [editingSourceDir, setEditingSourceDir] = useState(false)
  const [workspaceCollapsed, setWorkspaceCollapsed] = useState(true)
  const [deleteFileDialogOpen, setDeleteFileDialogOpen] = useState(false)
  const [deleteFileTargetPath, setDeleteFileTargetPath] = useState("")
  const [directoryPickerOpen, setDirectoryPickerOpen] = useState(false)
  const [directoryBrowser, setDirectoryBrowser] = useState({
    path: "",
    parent: "",
    directories: [],
    roots: [],
    source_dir: "",
  })
  const [directoryBrowserLoading, setDirectoryBrowserLoading] = useState(false)
  const [directoryBrowserError, setDirectoryBrowserError] = useState("")
  const [replActive, setReplActive] = useState(false)
  const [workspaceEnvText, setWorkspaceEnvText] = useState("")
  const [workspaceEnvPath, setWorkspaceEnvPath] = useState("")
  const [workspaceEnvLoading, setWorkspaceEnvLoading] = useState(false)
  const [modulesLoading, setModulesLoading] = useState(false)
  const [modules, setModules] = useState([])
  const [moduleDomains, setModuleDomains] = useState([])
  const [moduleReservedNames, setModuleReservedNames] = useState([])
  const [moduleIsSuperAdmin, setModuleIsSuperAdmin] = useState(false)
  const [selectedModuleName, setSelectedModuleName] = useState("")
  const [moduleEditor, setModuleEditor] = useState({
    originalName: "",
    name: "",
    title: "",
    description: "",
    scope: "domain",
    assigned_domains: [],
    config_schema: "{}",
    config_defaults: "{}",
    source: "",
  })
  const { featureFlags } = usePlatformFeatureFlags(backend)
  const showPortalProgress = isFeatureEnabled(featureFlags, "unifiedOperationStatus", true)
    && isFeatureEnabled(featureFlags, "viProgressMessages", true)

  const workspaceIndex = useMemo(() => buildWorkspaceTree(files), [files])
  const workspaceTree = workspaceIndex.tree
  const selectedFileMeta = useMemo(
    () => workspaceIndex.fileMetaByPath.get(String(selectedFile || "").trim()) || null,
    [selectedFile, workspaceIndex],
  )
  const deleteFileTargetName = useMemo(() => {
    const normalizedPath = String(deleteFileTargetPath || "").trim()
    if (!normalizedPath) return ""
    const matched = workspaceIndex.fileMetaByPath.get(normalizedPath)
    return String(matched?.name || normalizedPath.split("/").pop() || normalizedPath).trim()
  }, [deleteFileTargetPath, workspaceIndex])

  const expandWorkspaceAncestors = useCallback((pathValue) => {
    const folders = workspaceAncestorFolders(pathValue)
    if (!folders.length) return
    setExpandedWorkspaceFolders((prev) => {
      const next = { ...prev }
      folders.forEach((folderPath) => {
        next[folderPath] = true
      })
      return next
    })
  }, [])

  useEffect(() => {
    const handleVerseContextRequest = (event) => {
      const respond = event?.detail?.respond
      if (typeof respond !== "function") return
      const focusLabel = String(editor.path || selectedFile || "Current VI draft").trim() || "Current VI draft"
      const focusPreview = String(editor.content || "").trim()
      const normalizedPreview = focusPreview.length > 1200 ? `${focusPreview.slice(0, 1200)}...` : focusPreview
      respond({
        pageKind: "vi-portal",
        screen: "vi portal",
        pathname: "/vi-portal",
        sourceDir: connection.source_dir,
        selectedFile,
        filePath: editor.path,
        fileContent: editor.content,
        workspaceEnvPath,
        focus: {
          kind: "vi-script",
          label: focusLabel,
          identifier: String(editor.path || "").trim(),
          contentSummary: focusLabel,
          contentPreview: normalizedPreview,
        },
        relevanceHints: {
          focusPreferred: true,
          activeEditor: true,
        },
      })
    }

    const handleVerseApply = (event) => {
      const artifact = event?.detail?.artifact
      const respond = event?.detail?.respond
      if (artifact?.kind !== "vi-script" || typeof respond !== "function") return
      try {
        const nextPath = String(artifact?.path || editor.path || DEFAULT_FILE_PATH).trim() || DEFAULT_FILE_PATH
        const nextContent = String(artifact?.versaSource || "").trim()
        if (!nextContent) {
          respond({ ok: false, message: "Verse did not return any Versa source to load." })
          return
        }
        setSelectedFile("")
        setEditor({
          originalPath: "",
          path: nextPath,
          content: nextContent,
        })
        expandWorkspaceAncestors(nextPath)
        respond({ ok: true, message: `Loaded Versa source into the VI editor at ${nextPath}.` })
      } catch (error) {
        respond({ ok: false, message: error?.message || "Failed to load the Versa source into VI." })
      }
    }

    const handleVerseExecute = (event) => {
      const artifact = event?.detail?.artifact
      const respond = event?.detail?.respond
      const action = String(event?.detail?.action || "execute").trim().toLowerCase()
      if (artifact?.kind !== "vi-script" || typeof respond !== "function") return
      const nextPath = String(artifact?.path || editor.path || DEFAULT_FILE_PATH).trim() || DEFAULT_FILE_PATH
      const nextContent = String(artifact?.versaSource || "").trim()
      if (!nextContent) {
        respond({ ok: false, message: "Verse did not return any Versa source to run." })
        return
      }
      try {
        setSelectedFile("")
        setEditor({
          originalPath: "",
          path: nextPath,
          content: nextContent,
        })
        expandWorkspaceAncestors(nextPath)
        Promise.resolve(
          action === "save-execute"
            ? (async () => {
                const validationResponse = await fetch(`${backend}/platform/vi/validate`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json", ...authHeaders() },
                  body: JSON.stringify({ path: nextPath, source: nextContent }),
                })
                const validationPayload = await validationResponse.json().catch(() => ({}))
                if (!validationResponse.ok || validationPayload?.ok === false) {
                  const issue = Array.isArray(validationPayload?.issues)
                    ? validationPayload.issues.find(Boolean)
                    : validationPayload?.error
                  throw new Error(issue || "Versa validation failed; the draft was not written.")
                }
                const createResponse = await fetch(`${backend}/platform/vi/files`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json", ...authHeaders() },
                  body: JSON.stringify({ path: nextPath, content: nextContent }),
                })
                let savePayload = await createResponse.json().catch(() => ({}))
                if (createResponse.status === 409) {
                  const updateResponse = await fetch(`${backend}/platform/vi/files/${encodeURIComponent(nextPath)}`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json", ...authHeaders() },
                    body: JSON.stringify({ path: nextPath, content: nextContent }),
                  })
                  savePayload = await updateResponse.json().catch(() => ({}))
                  if (!updateResponse.ok) {
                    throw new Error(savePayload?.error || "Failed to save the Versa draft")
                  }
                } else if (!createResponse.ok) {
                  throw new Error(savePayload?.error || "Failed to save the Versa draft")
                }
                const savedPath = String(savePayload?.path || nextPath).trim() || nextPath
                const nextFiles = await fetchFilesRef.current?.()
                setSelectedFile(savedPath)
                setEditor({
                  originalPath: savedPath,
                  path: savedPath,
                  content: String(savePayload?.content || nextContent),
                })
                expandWorkspaceAncestors(savedPath)
                if (Array.isArray(nextFiles)) {
                  setConnection((prev) => ({ ...prev, files_count: nextFiles.length }))
                }
                if (terminalPanelRef.current?.runFile) {
                  await terminalPanelRef.current.runFile(savedPath)
                  return { savedPath }
                }
                const runResponse = await fetch(`${backend}/platform/vi/files/${encodeURIComponent(savedPath)}/run`, {
                  method: "POST",
                  headers: authHeaders(),
                })
                const runPayload = await runResponse.json().catch(() => ({}))
                if (!runResponse.ok) {
                  throw new Error(runPayload?.error || "Failed to run the saved Versa draft")
                }
                return { savedPath }
              })()
            : terminalPanelRef.current?.runSource
            ? terminalPanelRef.current.runSource({ path: nextPath, source: nextContent })
            : fetch(`${backend}/platform/vi/terminal/run`, {
                method: "POST",
                headers: { "Content-Type": "application/json", ...authHeaders() },
                body: JSON.stringify({ path: nextPath, source: nextContent }),
              }).then(async (res) => {
                const data = await res.json().catch(() => ({}))
                if (!res.ok) throw new Error(data?.error || "Failed to run the Versa draft")
                return data
              })
        )
          .then(() => {
            respond({
              ok: true,
              message: action === "save-execute"
                ? `Saved and started ${nextPath} in the VI terminal.`
                : `Loaded and started ${nextPath} in the VI terminal.`,
            })
          })
          .catch((error) => {
            respond({
              ok: false,
              message: error?.message || (action === "save-execute" ? "Failed to save and run the Versa draft." : "Failed to run the Versa draft."),
            })
          })
      } catch (error) {
        respond({
          ok: false,
          message: error?.message || (action === "save-execute" ? "Failed to save and execute the Versa draft." : "Failed to execute the Versa draft."),
        })
      }
    }

    window.addEventListener("liwiro:verse-assistant-request-context", handleVerseContextRequest)
    window.addEventListener("liwiro:verse-assistant-apply", handleVerseApply)
    window.addEventListener("liwiro:verse-assistant-execute", handleVerseExecute)
    const pendingAction = consumePendingVerseAction("/vi-portal")
    if (pendingAction?.artifact) {
      pendingVerseActionRef.current = pendingAction
      activatePendingVerseAction({
        pathname: "/vi-portal",
        pendingAction,
        onResult: (payload) => {
          pendingVerseActionRef.current = null
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
  }, [backend, connection.source_dir, editor.content, editor.path, expandWorkspaceAncestors, selectedFile, workspaceEnvPath])

  const fetchConnection = useCallback(async () => {
    try {
      const data = await fetchAuthedJson(`${backend}/platform/vi/connection`)
      const next = {
        verun_root: String(data?.verun_root || ""),
        vi_jar_path: String(data?.vi_jar_path || data?.versa_jar_path || ""),
        vi_jar_exists: Boolean(data?.vi_jar_exists ?? data?.versa_jar_exists),
        source_dir: String(data?.source_dir || ""),
        files_count: Number(data?.files_count || 0),
        terminal_active: Boolean(data?.terminal_active ?? data?.repl_active),
        terminal_prompt: String(data?.terminal_prompt || data?.repl_prompt || "> "),
      }
      setConnection(next)
      setSourceDirDraft(next.source_dir)
      setReplActive(next.terminal_active)
      return next
    } catch (error) {
      if (Number(error?.status || 0) === 401) {
        window.location.href = "/login"
        return null
      }
      throw error
    }
  }, [backend])

  const fetchFiles = useCallback(async () => {
    const res = await fetch(`${backend}/platform/vi/files`, { headers: authHeaders() })
    if (res.status === 401) {
      window.location.href = "/login"
      return []
    }
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data?.error || "Failed to load VI files")
    }
    const data = await res.json()
    const nextFiles = Array.isArray(data?.files) ? data.files : []
    setFiles(nextFiles)
    terminalPanelRef.current?.invalidateListings?.()
    return nextFiles
  }, [backend])

  const fetchWorkspaceEnv = useCallback(async () => {
    setWorkspaceEnvLoading(true)
    try {
      const res = await fetch(`${backend}/platform/vi/workspace-env`, { headers: authHeaders() })
      if (res.status === 401) {
        window.location.href = "/login"
        return ""
      }
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || "Failed to load workspace .env")
      const nextText = String(data?.content || "")
      setWorkspaceEnvText(nextText)
      setWorkspaceEnvPath(String(data?.path || ""))
      return nextText
    } catch (error) {
      toast.error(error?.message || "Failed to load workspace .env")
      return ""
    } finally {
      setWorkspaceEnvLoading(false)
    }
  }, [backend])

  const loadFile = useCallback(async (path) => {
    const res = await fetch(`${backend}/platform/vi/files/${encodeURIComponent(path)}`, { headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data?.error || "Failed to load file")
    const resolvedPath = String(data?.path || path)
    expandWorkspaceAncestors(resolvedPath)
    setSelectedFile(resolvedPath)
    setEditor({
      originalPath: resolvedPath,
      path: resolvedPath,
      content: String(data?.content || ""),
    })
    return data
  }, [backend, expandWorkspaceAncestors])

  const startNewFile = useCallback(() => {
    setSelectedFile("")
    setEditor(createBlankEditorState())
  }, [])

  const startNewModule = useCallback(() => {
    setSelectedModuleName("")
    setModuleEditor({
      originalName: "",
      name: "",
      title: "",
      description: "",
      scope: "domain",
      assigned_domains: [],
      config_schema: "{}",
      config_defaults: "{}",
      source: "",
    })
  }, [])

  const fetchModules = useCallback(async () => {
    setModulesLoading(true)
    try {
      const res = await fetch(`${backend}/platform/vi/modules/catalog`, { headers: authHeaders() })
      if (res.status === 401) {
        window.location.href = "/login"
        return []
      }
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || "Failed to load VI modules")
      const nextModules = Array.isArray(data?.modules) ? data.modules : []
      setModules(nextModules)
      setModuleDomains(Array.isArray(data?.available_domains) ? data.available_domains : [])
      setModuleReservedNames(Array.isArray(data?.reserved_names) ? data.reserved_names : [])
      setModuleIsSuperAdmin(Boolean(data?.is_super_admin))
      return nextModules
    } catch (error) {
      toast.error(error?.message || "Failed to load VI modules")
      return []
    } finally {
      setModulesLoading(false)
    }
  }, [backend])

  const loadModule = useCallback(async (moduleName) => {
    const name = String(moduleName || "").trim()
    if (!name) return null
    const res = await fetch(`${backend}/platform/vi/modules/${encodeURIComponent(name)}`, { headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data?.error || "Failed to load VI module")
    const loadedModule = data?.module || {}
    setSelectedModuleName(String(loadedModule?.name || name))
    setModuleEditor({
      originalName: String(loadedModule?.name || name),
      name: String(loadedModule?.name || name),
      title: String(loadedModule?.title || loadedModule?.name || name),
      description: String(loadedModule?.description || ""),
      scope: String(loadedModule?.scope || "domain"),
      assigned_domains: Array.isArray(loadedModule?.assigned_domains) ? loadedModule.assigned_domains : [],
      config_schema: JSON.stringify(loadedModule?.config_schema || {}, null, 2),
      config_defaults: JSON.stringify(loadedModule?.config_defaults || {}, null, 2),
      source: String(loadedModule?.source || ""),
    })
    return loadedModule
  }, [backend])

  const appendConsole = useCallback((text) => {
    const next = String(text || "").replace(/\r\n/g, "\n").replace(/^\n+|\n+$/g, "")
    if (!next) return
    terminalPanelRef.current?.writeText(`${next}\r\n`)
  }, [])

  const reportFileLoadError = useCallback((path, error) => {
    const normalizedPath = String(path || "file").trim() || "file"
    const message = String(error?.message || "Failed to load file").trim()
    appendConsole(formatConsoleEvent("warning", `Could not load ${normalizedPath}: ${message}`))
    toast.error(message)
  }, [appendConsole])

  const safeLoadFile = useCallback(async (path) => {
    try {
      return await loadFile(path)
    } catch (error) {
      reportFileLoadError(path, error)
      return null
    }
  }, [loadFile, reportFileLoadError])

  const clearEditor = useCallback(() => {
    setSelectedFile("")
    setEditor(createBlankEditorState())
  }, [])

  const toggleWorkspaceFolder = useCallback((folderPath) => {
    const normalizedPath = String(folderPath || "").trim()
    if (!normalizedPath) return
    setExpandedWorkspaceFolders((prev) => ({
      ...prev,
      [normalizedPath]: !prev[normalizedPath],
    }))
  }, [])

  const loadPortal = useCallback(async () => {
    if (showPortalProgress) {
      startOperation({
        title: "Loading VI portal",
        detail: "Refreshing workspace files, modules, and runtime connection state.",
      })
    }
    setLoading(true)
    try {
      const shouldPreserveVerseDraft = String(pendingVerseActionRef.current?.artifact?.kind || "").trim() === "vi-script"
      const [, nextFiles] = await Promise.all([fetchConnection(), fetchFiles(), fetchModules(), fetchWorkspaceEnv()])
      if (shouldPreserveVerseDraft) {
        pendingVerseActionRef.current = null
      } else {
        const savedState = loadSavedEditorState()
        if (savedState) {
          const nextEditor = savedState.editor && typeof savedState.editor === "object"
            ? {
                originalPath: String(savedState.editor.originalPath || "").trim(),
                path: String(savedState.editor.path || "").trim(),
                content: String(savedState.editor.content || ""),
              }
            : createBlankEditorState()
          const savedSelectedFile = String(savedState.selectedFile || "").trim()
          const savedFolders = savedState.expandedWorkspaceFolders && typeof savedState.expandedWorkspaceFolders === "object"
            ? savedState.expandedWorkspaceFolders
            : {}
          setExpandedWorkspaceFolders(savedFolders)
          setSelectedFile(savedSelectedFile && nextFiles.some((item) => String(item?.path || "").trim() === savedSelectedFile) ? savedSelectedFile : "")
          setEditor(nextEditor)
        } else {
          startNewFile()
        }
      }
      startNewModule()
      if (showPortalProgress) {
        succeedOperation({
          title: "VI portal ready",
          detail: "The workspace, modules, and editor state are loaded.",
        })
      }
    } catch (error) {
      if (showPortalProgress) {
        failOperation({
          title: "VI portal failed to load",
          detail: error?.message || "Failed to load VI portal",
        })
      }
      toast.error(error?.message || "Failed to load VI portal")
    } finally {
      setEditorStateHydrated(true)
      setLoading(false)
    }
  }, [failOperation, fetchConnection, fetchFiles, fetchModules, fetchWorkspaceEnv, showPortalProgress, startNewFile, startNewModule, startOperation, succeedOperation])

  useEffect(() => {
    loadPortal()
  }, [loadPortal])

  useEffect(() => {
    fetchFilesRef.current = fetchFiles
  }, [fetchFiles])

  useEffect(() => {
    if (!editorStateHydrated) return
    saveEditorState({ selectedFile, expandedWorkspaceFolders, editor })
  }, [editor, editorStateHydrated, expandedWorkspaceFolders, selectedFile])

  const syncEditorAfterFileRefresh = useCallback(async (nextFiles) => {
    if (!Array.isArray(nextFiles) || nextFiles.length === 0) {
      startNewFile()
      return
    }
    if (editor.originalPath) {
      const match = nextFiles.find((item) => String(item?.path || "") === editor.originalPath)
      if (match) {
        try {
          await loadFile(match.path)
          return
        } catch (error) {
          reportFileLoadError(match.path, error)
          startNewFile()
          return
        }
      }
    }
    setSelectedFile("")
    setEditor((current) => {
      if (String(current?.content || "").trim() || String(current?.path || "").trim()) {
        return {
          ...current,
          originalPath: "",
        }
      }
      return createBlankEditorState()
    })
  }, [editor.originalPath, loadFile, reportFileLoadError, startNewFile])

  const refreshAll = useCallback(async () => {
    if (showPortalProgress) {
      startOperation({
        title: "Refreshing VI portal",
        detail: "Reloading files, modules, and runtime state.",
      })
    }
    setBusy(true)
    try {
      const [, nextFiles, nextModules] = await Promise.all([fetchConnection(), fetchFiles(), fetchModules(), fetchWorkspaceEnv()])
      await syncEditorAfterFileRefresh(nextFiles)
      if (selectedModuleName) {
        const match = nextModules.find((item) => String(item?.name || "") === selectedModuleName)
        if (match) {
          await loadModule(selectedModuleName)
        } else {
          startNewModule()
        }
      } else {
        startNewModule()
      }
      toast.success("VI portal refreshed")
      if (showPortalProgress) {
        succeedOperation({
          title: "VI portal refreshed",
          detail: "The latest workspace state is now loaded.",
        })
      }
    } catch (error) {
      if (showPortalProgress) {
        failOperation({
          title: "VI portal refresh failed",
          detail: error?.message || "Failed to refresh VI portal",
        })
      }
      toast.error(error?.message || "Failed to refresh VI portal")
    } finally {
      setBusy(false)
    }
  }, [failOperation, fetchConnection, fetchFiles, fetchModules, fetchWorkspaceEnv, loadModule, selectedModuleName, showPortalProgress, startNewModule, startOperation, succeedOperation, syncEditorAfterFileRefresh])

  const browseDirectories = useCallback(async (pathValue = "") => {
    setDirectoryBrowserLoading(true)
    setDirectoryBrowserError("")
    setBusy(true)
    try {
      const query = String(pathValue || "").trim() ? `?path=${encodeURIComponent(String(pathValue || "").trim())}` : ""
      const res = await fetch(`${backend}/platform/vi/directories${query}`, {
        headers: authHeaders(),
      })
      const data = await res.json().catch(() => ({}))
      if (res.status === 401) {
        window.location.href = "/login"
        return null
      }
      if (!res.ok) throw new Error(data?.error || "Failed to browse directories")
      setDirectoryBrowser({
        path: String(data?.path || ""),
        parent: String(data?.parent || ""),
        directories: Array.isArray(data?.directories) ? data.directories : [],
        roots: Array.isArray(data?.roots) ? data.roots : [],
        source_dir: String(data?.source_dir || ""),
      })
      return data
    } catch (error) {
      setDirectoryBrowserError(error?.message || "Failed to browse directories")
      throw error
    } finally {
      setDirectoryBrowserLoading(false)
      setBusy(false)
    }
  }, [backend])

  const openDirectoryPicker = useCallback(async () => {
    setDirectoryPickerOpen(true)
    try {
      await browseDirectories(connection.source_dir || sourceDirDraft || "")
    } catch (error) {
      toast.error(error?.message || "Failed to browse directories")
    }
  }, [browseDirectories, connection.source_dir, sourceDirDraft])

  const persistSourceDirectory = useCallback(async (nextPath) => {
    const normalizedPath = String(nextPath || "").trim()
    if (!normalizedPath) {
      toast.error("Source directory is required")
      return false
    }

    if (showPortalProgress) {
      startOperation({
        title: "Updating VI source directory",
        detail: "Applying the new workspace root and reloading files.",
      })
    }
    setBusy(true)
    try {
      const res = await fetch(`${backend}/platform/vi/connection`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ source_dir: normalizedPath }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || "Failed to update source directory")
      setConnection((prev) => ({
        ...prev,
        source_dir: String(data?.source_dir || normalizedPath),
        files_count: Number(data?.files_count || 0),
      }))
      setSourceDirDraft(String(data?.source_dir || normalizedPath))
      setEditingSourceDir(false)
      setDirectoryPickerOpen(false)
      await fetchWorkspaceEnv()
      const nextFiles = await fetchFiles()
      await syncEditorAfterFileRefresh(nextFiles)
      appendConsole(formatConsoleEvent("source directory updated", String(data?.source_dir || normalizedPath)))
      if (showPortalProgress) {
        succeedOperation({
          title: "VI source directory updated",
          detail: String(data?.source_dir || normalizedPath),
        })
      }
      toast.success("VI source directory updated")
      return true
    } catch (error) {
      if (showPortalProgress) {
        failOperation({
          title: "Failed to update VI source directory",
          detail: error?.message || "Failed to update source directory",
        })
      }
      toast.error(error?.message || "Failed to update source directory")
      return false
    } finally {
      setBusy(false)
    }
  }, [appendConsole, backend, failOperation, fetchFiles, fetchWorkspaceEnv, showPortalProgress, startOperation, succeedOperation, syncEditorAfterFileRefresh])

  const saveWorkspaceEnv = useCallback(async () => {
    if (showPortalProgress) {
      startOperation({
        title: "Saving workspace environment",
        detail: "Writing the VI workspace .env file.",
      })
    }
    setBusy(true)
    try {
      const res = await fetch(`${backend}/platform/vi/workspace-env`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ content: workspaceEnvText }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || "Failed to save workspace .env")
      setWorkspaceEnvText(String(data?.content || ""))
      setWorkspaceEnvPath(String(data?.path || ""))
      appendConsole(formatConsoleEvent("workspace env saved", String(data?.path || "")))
      if (showPortalProgress) {
        succeedOperation({
          title: "Workspace environment saved",
          detail: String(data?.path || "Workspace .env updated"),
        })
      }
      toast.success("Workspace .env saved")
    } catch (error) {
      if (showPortalProgress) {
        failOperation({
          title: "Failed to save workspace environment",
          detail: error?.message || "Failed to save workspace .env",
        })
      }
      toast.error(error?.message || "Failed to save workspace .env")
    } finally {
      setBusy(false)
    }
  }, [appendConsole, backend, failOperation, showPortalProgress, startOperation, succeedOperation, workspaceEnvText])

  const applyWorkspaceEnvPreset = useCallback((presetId) => {
    const nextEnv = applyMediaStorageEnvPreset(parseEnvText(workspaceEnvText), presetId)
    setWorkspaceEnvText(envObjectToText(nextEnv))
  }, [workspaceEnvText])

  const saveSourceDirectory = useCallback(async () => {
    await persistSourceDirectory(sourceDirDraft)
  }, [persistSourceDirectory, sourceDirDraft])

  const persistFile = useCallback(async ({ showToast = true } = {}) => {
    const path = String(editor.path || "").trim()
    if (!path) {
      toast.error("File path is required")
      return null
    }

    const isVersaFile = path.toLowerCase().endsWith(".versa")
    if (showPortalProgress) {
      startOperation({
        title: editor.originalPath ? "Saving VI file" : "Creating VI file",
        detail: path,
      })
    }
    setBusy(true)
    try {
      if (isVersaFile) {
        const validationResponse = await fetch(`${backend}/platform/vi/validate`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({ path, source: editor.content }),
        })
        const validationPayload = await validationResponse.json().catch(() => ({}))
        if (!validationResponse.ok || validationPayload?.ok === false) {
          const issue = Array.isArray(validationPayload?.issues)
            ? validationPayload.issues.find(Boolean)
            : validationPayload?.error
          throw new Error(issue || "Versa validation failed; the file was not written.")
        }
      }
      const isExistingFile = Boolean(editor.originalPath)
      const method = editor.originalPath ? "PUT" : "POST"
      const route = editor.originalPath
        ? `${backend}/platform/vi/files/${encodeURIComponent(editor.originalPath)}`
        : `${backend}/platform/vi/files`
      const res = await fetch(route, {
        method,
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ path, content: editor.content }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || "Failed to save file")
      const nextFiles = await fetchFiles()
      const resolvedPath = String(data?.path || path)
      expandWorkspaceAncestors(resolvedPath)
      setSelectedFile(resolvedPath)
      setEditor({
        originalPath: resolvedPath,
        path: resolvedPath,
        content: String(data?.content || editor.content),
      })
      setConnection((prev) => ({ ...prev, files_count: nextFiles.length }))
      appendConsole(formatConsoleEvent(isExistingFile ? "file saved" : "file created", resolvedPath))
      if (showPortalProgress) {
        succeedOperation({
          title: isExistingFile ? "VI file saved" : "VI file created",
          detail: resolvedPath,
        })
      }
      if (showToast) {
        toast.success(isExistingFile ? "File updated" : "File created")
      }
      return {
        created: !isExistingFile,
        path: String(data?.path || path),
      }
    } catch (error) {
      if (showPortalProgress) {
        failOperation({
          title: "Failed to save VI file",
          detail: error?.message || "Failed to save file",
        })
      }
      toast.error(error?.message || "Failed to save file")
      return null
    } finally {
      setBusy(false)
    }
  }, [appendConsole, backend, editor, expandWorkspaceAncestors, failOperation, fetchFiles, showPortalProgress, startOperation, succeedOperation])

  const saveFile = useCallback(async () => {
    await persistFile()
  }, [persistFile])

  const toggleModuleDomain = useCallback((domainName) => {
    const normalized = String(domainName || "").trim().toLowerCase()
    if (!normalized) return
    setModuleEditor((prev) => {
      const current = Array.isArray(prev.assigned_domains) ? prev.assigned_domains : []
      const next = current.includes(normalized)
        ? current.filter((item) => item !== normalized)
        : [...current, normalized]
      return { ...prev, assigned_domains: next }
    })
  }, [])

  const saveModule = useCallback(async () => {
    const name = String(moduleEditor.name || "").trim().toLowerCase()
    if (!name) {
      toast.error("Module name is required")
      return
    }
    try {
      const configSchema = moduleEditor.config_schema.trim() ? parseJsonLikeObject(moduleEditor.config_schema, "Config schema") : {}
      const configDefaults = moduleEditor.config_defaults.trim() ? parseJsonLikeObject(moduleEditor.config_defaults, "Config defaults") : {}
      const payload = {
        name,
        title: String(moduleEditor.title || name).trim(),
        description: String(moduleEditor.description || "").trim(),
        scope: moduleEditor.scope === "global" ? "global" : "domain",
        assigned_domains: Array.isArray(moduleEditor.assigned_domains) ? moduleEditor.assigned_domains : [],
        config_schema: configSchema,
        config_defaults: configDefaults,
        source: String(moduleEditor.source || ""),
      }
      if (showPortalProgress) {
        startOperation({
          title: moduleEditor.originalName ? "Saving VI module" : "Creating VI module",
          detail: name,
        })
      }
      const route = moduleEditor.originalName
        ? `${backend}/platform/vi/modules/${encodeURIComponent(moduleEditor.originalName)}`
        : `${backend}/platform/vi/modules`
      const method = moduleEditor.originalName ? "PUT" : "POST"
      setBusy(true)
      const res = await fetch(route, {
        method,
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(payload),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || "Failed to save VI module")
      await fetchModules()
      await loadModule(String(data?.module?.name || name))
      if (showPortalProgress) {
        succeedOperation({
          title: moduleEditor.originalName ? "VI module saved" : "VI module created",
          detail: String(data?.module?.name || name),
        })
      }
      toast.success(moduleEditor.originalName ? "VI module updated" : "VI module created")
    } catch (error) {
      if (showPortalProgress) {
        failOperation({
          title: "Failed to save VI module",
          detail: error?.message || "Failed to save VI module",
        })
      }
      toast.error(error?.message || "Failed to save VI module")
    } finally {
      setBusy(false)
    }
  }, [backend, failOperation, fetchModules, loadModule, moduleEditor, showPortalProgress, startOperation, succeedOperation])

  const deleteModule = useCallback(async () => {
    if (!moduleEditor.originalName) {
      toast.error("Select a saved module first")
      return
    }
    if (showPortalProgress) {
      startOperation({
        title: "Deleting VI module",
        detail: moduleEditor.originalName,
      })
    }
    setBusy(true)
    try {
      const res = await fetch(`${backend}/platform/vi/modules/${encodeURIComponent(moduleEditor.originalName)}`, {
        method: "DELETE",
        headers: authHeaders(),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || "Failed to delete VI module")
      await fetchModules()
      setSelectedModuleName("")
      startNewModule()
      if (showPortalProgress) {
        succeedOperation({
          title: "VI module deleted",
          detail: moduleEditor.originalName,
        })
      }
      toast.success("VI module deleted")
    } catch (error) {
      if (showPortalProgress) {
        failOperation({
          title: "Failed to delete VI module",
          detail: error?.message || "Failed to delete VI module",
        })
      }
      toast.error(error?.message || "Failed to delete VI module")
    } finally {
      setBusy(false)
    }
  }, [backend, failOperation, fetchModules, moduleEditor.originalName, showPortalProgress, startNewModule, startOperation, succeedOperation])

  const openModuleHarness = useCallback(() => {
    const moduleName = String(moduleEditor.name || moduleEditor.originalName || "").trim().toLowerCase()
    if (!moduleName) {
      toast.error("Choose a module first")
      return
    }
    setSelectedFile("")
    setEditor({
      originalPath: "",
      path: `scratch/${moduleName}-harness.versa`,
      content: [
        `import ${moduleName};`,
        `print("Loaded module: ${moduleName}");`,
        "# Call exported functions below.",
        "# Example:",
        `# print(${moduleName}.status());`,
      ].join("\n"),
    })
    appendConsole(formatConsoleEvent("module harness loaded", `scratch/${moduleName}-harness.versa`))
    toast.success("Harness starter loaded into the file editor")
  }, [appendConsole, moduleEditor.name, moduleEditor.originalName])

  const requestDeleteFile = useCallback((pathValue = "") => {
    const normalizedPath = String(pathValue || "").trim()
    if (!normalizedPath) {
      toast.error("Choose a saved file first")
      return
    }
    setDeleteFileTargetPath(normalizedPath)
    setDeleteFileDialogOpen(true)
  }, [])

  const deleteFile = useCallback(async () => {
    const targetPath = String(deleteFileTargetPath || "").trim()
    if (!targetPath) {
      toast.error("Choose a saved file first")
      return
    }
    if (showPortalProgress) {
      startOperation({
        title: "Deleting VI file",
        detail: targetPath,
      })
    }
    setBusy(true)
    try {
      const res = await fetch(`${backend}/platform/vi/files/${encodeURIComponent(targetPath)}`, {
        method: "DELETE",
        headers: authHeaders(),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || "Failed to delete file")
      const nextFiles = await fetchFiles()
      setConnection((prev) => ({ ...prev, files_count: nextFiles.length }))
      await syncEditorAfterFileRefresh(nextFiles)
      appendConsole(formatConsoleEvent("file deleted", targetPath))
      setDeleteFileDialogOpen(false)
      setDeleteFileTargetPath("")
      if (showPortalProgress) {
        succeedOperation({
          title: "VI file deleted",
          detail: targetPath,
        })
      }
      toast.success("File deleted")
    } catch (error) {
      if (showPortalProgress) {
        failOperation({
          title: "Failed to delete VI file",
          detail: error?.message || "Failed to delete file",
        })
      }
      toast.error(error?.message || "Failed to delete file")
    } finally {
      setBusy(false)
    }
  }, [appendConsole, backend, deleteFileTargetPath, failOperation, fetchFiles, showPortalProgress, startOperation, succeedOperation, syncEditorAfterFileRefresh])

  const runFilePath = useCallback(async (filePath, { showToast = true } = {}) => {
    const normalizedPath = String(filePath || "").trim()
    if (!normalizedPath) {
      toast.error("Save the file first before running it")
      return false
    }
    if (showPortalProgress) {
      startOperation({
        title: "Running VI file",
        detail: normalizedPath,
      })
    }
    setBusy(true)
    try {
      if (terminalPanelRef.current?.runFile) {
        await terminalPanelRef.current.runFile(normalizedPath)
        if (showPortalProgress) {
          succeedOperation({
            title: "VI file started",
            detail: normalizedPath,
          })
        }
        if (showToast) {
          toast.success("VI file started in terminal")
        }
        return true
      }

      appendConsole(formatConsoleEvent("run file", normalizedPath))
      const res = await fetch(`${backend}/platform/vi/files/${encodeURIComponent(normalizedPath)}/run`, {
        method: "POST",
        headers: authHeaders(),
      })
      const data = await res.json().catch(() => ({}))
      consoleLinesFromPayload(data, "(file completed with no output)").forEach(appendConsole)
      if (!res.ok) {
        toast.error(data?.error || "Failed to run VI file")
        if (showPortalProgress) {
          failOperation({
            title: "Failed to run VI file",
            detail: data?.error || "Failed to run VI file",
          })
        }
        return false
      }
      if (showPortalProgress) {
        succeedOperation({
          title: "VI file executed",
          detail: normalizedPath,
        })
      }
      if (showToast) {
        toast.success("VI file executed")
      }
      return true
    } catch (error) {
      if (showPortalProgress) {
        failOperation({
          title: "Failed to run VI file",
          detail: error?.message || "Failed to run VI file",
        })
      }
      toast.error(error?.message || "Failed to run VI file")
      return false
    } finally {
      setBusy(false)
    }
  }, [appendConsole, backend, failOperation, showPortalProgress, startOperation, succeedOperation])

  const runFile = useCallback(async () => {
    await runFilePath(editor.originalPath)
  }, [editor.originalPath, runFilePath])

  const runEphemeralFile = useCallback(async () => {
    const logicalPath = String(editor.path || editor.originalPath || DEFAULT_FILE_PATH).trim() || DEFAULT_FILE_PATH
    if (showPortalProgress) {
      startOperation({
        title: "Running editor buffer",
        detail: logicalPath,
      })
    }
    setBusy(true)
    try {
      if (terminalPanelRef.current?.runSource) {
        await terminalPanelRef.current.runSource({
          path: logicalPath,
          source: editor.content,
        })
        if (showPortalProgress) {
          succeedOperation({
            title: "Editor buffer started",
            detail: logicalPath,
          })
        }
        toast.success("Current editor buffer started in terminal")
        return true
      }

      appendConsole(formatConsoleEvent("run", logicalPath))
      const res = await fetch(`${backend}/platform/vi/terminal/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          path: logicalPath,
          source: editor.content,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(data?.error || "Failed to run editor buffer")
      }
      if (showPortalProgress) {
        succeedOperation({
          title: "Editor buffer started",
          detail: logicalPath,
        })
      }
      toast.success("Current editor buffer started in terminal")
      return true
    } catch (error) {
      if (showPortalProgress) {
        failOperation({
          title: "Failed to run editor buffer",
          detail: error?.message || "Failed to run editor buffer",
        })
      }
      toast.error(error?.message || "Failed to run editor buffer")
      return false
    } finally {
      setBusy(false)
    }
  }, [appendConsole, backend, editor.content, editor.originalPath, editor.path, failOperation, showPortalProgress, startOperation, succeedOperation])

  const saveAndRunFile = useCallback(async () => {
    const saved = await persistFile({ showToast: false })
    if (!saved?.path) return
    const ok = await runFilePath(saved.path, { showToast: false })
    if (ok) {
      toast.success(saved.created ? "File created and started in terminal" : "File saved and started in terminal")
    }
  }, [persistFile, runFilePath])

  const renderWorkspaceFolder = useCallback((folderNode, depth = 0) => {
    const folderPath = String(folderNode?.path || "")
    const isExpanded = Boolean(expandedWorkspaceFolders[folderPath])
    return (
      <div key={folderPath || `folder-${depth}`} className="space-y-1">
        <button
          type="button"
          onClick={() => toggleWorkspaceFolder(folderPath)}
          className="flex w-full items-center gap-2 rounded-xl border border-slate-200/80 bg-white/[0.84] px-3 py-2 text-left transition hover:border-slate-300 hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:hover:border-sky-400/20 dark:hover:bg-white/10"
          style={{ paddingLeft: `${0.85 + depth * 0.85}rem` }}
        >
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 shrink-0 text-slate-500 dark:text-slate-300" />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0 text-slate-500 dark:text-slate-300" />
          )}
          <FolderOpen className="h-4 w-4 shrink-0 text-primary" />
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{folderNode?.name || "folder"}</p>
            <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">{folderNode?.files?.length || 0} file(s)</p>
          </div>
        </button>

        {isExpanded ? (
          <div className="space-y-1">
            {folderNode?.folders?.map((childNode) => renderWorkspaceFolder(childNode, depth + 1))}
            {folderNode?.files?.map((file) => {
              const active = String(file?.path || "") === selectedFile
              return (
                <div
                  key={String(file?.path || file?.name)}
                  className={`flex w-full items-center gap-2 rounded-xl border px-3 py-2 transition ${
                    active
                      ? "border-primary/40 bg-primary/[0.08] shadow-[0_16px_30px_rgba(15,118,110,0.12)] dark:border-sky-400/30 dark:bg-sky-400/10 dark:shadow-[0_16px_30px_rgba(56,189,248,0.12)]"
                      : "border-slate-200/80 bg-white/[0.76] hover:border-slate-300 hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:hover:border-sky-400/20 dark:hover:bg-white/10"
                  }`}
                  style={{ paddingLeft: `${1.75 + depth * 0.85}rem` }}
                >
                  <button
                    type="button"
                    onClick={() => safeLoadFile(file.path)}
                    className="flex min-w-0 flex-1 items-center gap-2 text-left"
                  >
                    <FileCode2 className="h-4 w-4 shrink-0 text-slate-500 dark:text-slate-300" />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-slate-900 dark:text-slate-100" title={file?.path || file?.name}>
                        {file?.name || file?.path}
                      </p>
                      <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">{file?.modifiedAt || "-"}</p>
                    </div>
                  </button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="ml-auto h-8 w-8 shrink-0 rounded-full text-slate-500 hover:text-rose-500 dark:text-slate-300 dark:hover:text-rose-300"
                    onClick={() => requestDeleteFile(file.path)}
                    aria-label={`Delete ${file?.name || file?.path}`}
                    title={`Delete ${file?.name || file?.path}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              )
            })}
          </div>
        ) : null}
      </div>
    )
  }, [expandedWorkspaceFolders, requestDeleteFile, safeLoadFile, selectedFile, toggleWorkspaceFolder])

  if (loading) {
    return <div className="app-page py-8 text-sm text-slate-300">Loading VI portal...</div>
  }

  return (
    <div className="w-full app-stack">
      <section className="app-hero">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="app-eyebrow">Versa Console</p>
            <h1 className="app-title mt-4">Work with local Versa source files and a PTY-backed Versa terminal</h1>
            <p className="app-copy mt-3">
              The source editor and VI terminal share the same workspace row, while the source directory stays editable from the file rail.
            </p>
          </div>
          <Button variant="outline" className="h-11 rounded-xl" onClick={refreshAll} disabled={busy || loading}>
            <RefreshCw className="h-4 w-4" /> Refresh Portal
          </Button>
        </div>
      </section>

      {showPortalProgress && portalOperationStatus?.visible ? (
        <OperationStatusPanel status={portalOperationStatus} />
      ) : null}

      <div className="app-card-soft p-4 md:p-5">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <PortalStat
            label="Source Folder"
            value={connection.source_dir || "-"}
            icon={<FolderOpen className="h-5 w-5 text-primary" />}
            wrapValue
          />
          <PortalStat
            label="Local Files"
            value={String(connection.files_count || files.length || 0)}
            icon={<FileCode2 className="h-5 w-5 text-primary" />}
          />
          <PortalStat
            label="Versa Terminal"
            value={replActive ? "Live" : "Idle"}
            icon={<SquareTerminal className="h-5 w-5 text-primary" />}
          />
          <PortalStat
            label="Runtime Jar"
            value={connection.vi_jar_exists ? "Ready" : "Missing"}
            icon={<Play className="h-5 w-5 text-primary" />}
          />
          <PortalStat
            label="VI Modules"
            value={modulesLoading ? "Loading..." : String(modules.length || 0)}
            icon={<FileCode2 className="h-5 w-5 text-primary" />}
            caption="Scope-aware module manager"
            href="#vi-modules"
          />
        </div>
      </div>

      <div className="space-y-6">
        <Card className="overflow-hidden rounded-xl border-slate-200 shadow-sm">
          <div className="flex items-start gap-3 px-4 py-3 md:px-5">
            <Button
              variant="outline"
              className="mt-0.5 h-9 w-9 shrink-0 px-0"
              onClick={() => setWorkspaceCollapsed((prev) => !prev)}
              aria-expanded={!workspaceCollapsed}
              aria-label={workspaceCollapsed ? "Expand source workspace" : "Collapse source workspace"}
              title={workspaceCollapsed ? "Expand source workspace" : "Collapse source workspace"}
            >
              {workspaceCollapsed ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
            </Button>
            <div className="min-w-0 flex-1">
              <button
                type="button"
                onClick={() => {
                  if (!workspaceCollapsed) {
                    setEditingSourceDir(true)
                  }
                }}
                className={`block w-full rounded-lg border border-transparent px-3 py-2 text-left transition ${
                  workspaceCollapsed
                    ? "bg-slate-50/80 dark:bg-slate-950/40"
                    : "bg-slate-50/80 hover:border-slate-300 hover:bg-slate-100/80 dark:bg-slate-950/40 dark:hover:border-slate-700 dark:hover:bg-slate-900/70"
                }`}
                title={workspaceCollapsed ? connection.source_dir || "-" : "Click to edit source directory"}
              >
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Source Folder</p>
                <p className="mt-1 break-all text-sm font-medium text-slate-900 dark:text-slate-100">{connection.source_dir || "-"}</p>
              </button>
            </div>
            {!workspaceCollapsed ? (
              <div className="hidden items-center gap-2 md:flex">
                <div className="rounded-lg border border-slate-200/80 bg-slate-50 px-3 py-2 text-right dark:border-slate-800 dark:bg-slate-950/50">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Files</p>
                  <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{files.length}</p>
                </div>
                <Button variant="outline" className="h-9" onClick={startNewFile}>
                  <Plus className="h-4 w-4" /> New
                </Button>
              </div>
            ) : null}
          </div>

          {!workspaceCollapsed ? (
            <CardContent className="border-t border-slate-200/80 bg-slate-50/60 px-4 py-4 dark:border-slate-800 dark:bg-slate-950/20 md:px-5">
              <div className="grid gap-4 xl:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
                <div className="rounded-[1.15rem] border border-slate-200/90 bg-white p-3 dark:border-slate-800 dark:bg-slate-950/40">
                  <div className="flex items-center justify-between gap-3">
                    <Label>Workspace Controls</Label>
                    {!editingSourceDir ? (
                      <Button variant="ghost" size="sm" className="h-8 px-2 text-slate-600 dark:text-slate-300" onClick={() => setEditingSourceDir(true)}>
                        <PencilLine className="h-4 w-4" /> Edit
                      </Button>
                    ) : null}
                  </div>

                  {editingSourceDir ? (
                    <div className="mt-3 space-y-3">
                      <div className="flex flex-col gap-2">
                        <Input
                          value={sourceDirDraft}
                          onChange={(e) => setSourceDirDraft(e.target.value)}
                          placeholder="Absolute path or project-relative folder"
                        />
                        <Button variant="outline" className="h-10 justify-start" onClick={openDirectoryPicker} disabled={busy}>
                          <FolderOpen className="h-4 w-4" /> Select Folder
                        </Button>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button className="brand-solid h-9" onClick={saveSourceDirectory} disabled={busy}>
                          <Check className="h-4 w-4" /> Use Directory
                        </Button>
                        <Button
                          variant="outline"
                          className="h-9"
                          onClick={() => {
                            setSourceDirDraft(connection.source_dir || "")
                            setEditingSourceDir(false)
                          }}
                          disabled={busy}
                        >
                          <X className="h-4 w-4" /> Cancel
                        </Button>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        Type a path directly or browse server folders. Relative paths are resolved from the Liwiro project root, and missing folders are created on save.
                      </p>
                    </div>
                  ) : (
                    <div className="mt-3 space-y-3">
                      <div className="rounded-xl border border-slate-200/80 bg-slate-50 px-3 py-3 dark:border-slate-800 dark:bg-slate-900/60">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Active File</p>
                        <p
                          className="mt-2 truncate text-xs font-medium text-slate-700 dark:text-slate-200"
                          title={selectedFileMeta?.path || editor.path || "Draft file"}
                        >
                          {selectedFileMeta?.name || selectedFileMeta?.path?.split("/").pop() || editor.path?.split("/").pop() || "Draft"}
                        </p>
                      </div>
                      <p className="text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                        Expand this panel when you need file browsing or want to change the workspace folder. Collapse it to give more vertical room to the editor and terminal.
                      </p>
                    </div>
                  )}

                  <div className="mt-4 space-y-3 rounded-xl border border-slate-200/80 bg-slate-50 px-3 py-3 dark:border-slate-800 dark:bg-slate-900/60">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Workspace .env</p>
                        <p className="mt-1 text-xs text-slate-500 dark:text-slate-300">
                          VI terminal sessions, saved runs, and direct runs load this file into `env.*`.
                        </p>
                      </div>
                      <Button variant="outline" className="h-8 px-2 text-xs" onClick={fetchWorkspaceEnv} disabled={busy || workspaceEnvLoading}>
                        <RefreshCw className="h-3.5 w-3.5" /> Reload
                      </Button>
                    </div>
                    <p className="break-all font-mono text-[11px] text-slate-500 dark:text-slate-400">{workspaceEnvPath || `${connection.source_dir || "."}/.env`}</p>
                    <div className="flex flex-wrap gap-2">
                      {MEDIA_STORAGE_ENV_PRESETS.map((preset) => (
                        <Button
                          key={preset.id}
                          type="button"
                          variant="outline"
                          className="h-8 px-2 text-xs"
                          onClick={() => applyWorkspaceEnvPreset(preset.id)}
                          disabled={busy}
                        >
                          {preset.label}
                        </Button>
                      ))}
                    </div>
                    <Textarea
                      value={workspaceEnvText}
                      onChange={(e) => setWorkspaceEnvText(e.target.value)}
                      className="min-h-[12rem] font-mono text-sm leading-6"
                      placeholder={"API_KEY=replace-me\nMEDIA_DEFAULT_PROVIDER=cloudinary"}
                    />
                    <div className="flex flex-wrap gap-2">
                      <Button className="brand-solid h-9" onClick={saveWorkspaceEnv} disabled={busy}>
                        <Save className="h-4 w-4" /> Save .env
                      </Button>
                    </div>
                  </div>
                </div>

                <div className="rounded-[1.15rem] border border-slate-200/90 bg-white p-3 dark:border-slate-800 dark:bg-slate-950/40">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">Workspace Files</p>
                      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Browse local Versa files by folder and load one directly into the editor.</p>
                    </div>
                    <div className="rounded-lg border border-slate-200/80 bg-slate-50 px-3 py-2 text-right dark:border-slate-800 dark:bg-slate-900/60 md:hidden">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Files</p>
                      <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{files.length}</p>
                    </div>
                  </div>

                  {loading ? (
                    <p className="mt-4 text-sm text-slate-600 dark:text-slate-300">Loading files...</p>
                  ) : files.length === 0 ? (
                    <p className="mt-4 text-sm text-slate-600 dark:text-slate-300">No local VI files yet. Create the first one from the editor.</p>
                  ) : (
                    <div className="mt-4 space-y-3">
                      {workspaceTree.folders.length ? (
                        <div className="space-y-2">
                          {workspaceTree.folders.map((folderNode) => renderWorkspaceFolder(folderNode))}
                        </div>
                      ) : null}

                      {workspaceTree.files.length ? (
                        <div className="space-y-2">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Workspace Root</p>
                          {workspaceTree.files.map((file) => {
                            const active = String(file?.path || "") === selectedFile
                            return (
                              <div
                                key={String(file?.path || file?.name)}
                                className={`flex w-full items-center gap-2 rounded-xl border px-3 py-2 transition ${
                                  active
                                    ? "border-primary/40 bg-primary/[0.08] shadow-[0_16px_30px_rgba(15,118,110,0.12)] dark:border-sky-400/30 dark:bg-sky-400/10 dark:shadow-[0_16px_30px_rgba(56,189,248,0.12)]"
                                    : "border-slate-200/80 bg-white/[0.76] hover:border-slate-300 hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:hover:border-sky-400/20 dark:hover:bg-white/10"
                                }`}
                              >
                                <button
                                  type="button"
                                  onClick={() => safeLoadFile(file.path)}
                                  className="flex min-w-0 flex-1 items-center gap-2 text-left"
                                >
                                  <FileCode2 className="h-4 w-4 shrink-0 text-slate-500 dark:text-slate-300" />
                                  <div className="min-w-0">
                                    <p className="truncate text-sm font-medium text-slate-900 dark:text-slate-100" title={file?.path || file?.name}>
                                      {file?.name || file?.path}
                                    </p>
                                    <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">{file?.modifiedAt || "-"}</p>
                                  </div>
                                </button>
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon"
                                  className="ml-auto h-8 w-8 shrink-0 rounded-full text-slate-500 hover:text-rose-500 dark:text-slate-300 dark:hover:text-rose-300"
                                  onClick={() => requestDeleteFile(file.path)}
                                  aria-label={`Delete ${file?.name || file?.path}`}
                                  title={`Delete ${file?.name || file?.path}`}
                                >
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </div>
                            )
                          })}
                        </div>
                      ) : null}
                    </div>
                  )}
                </div>
              </div>
            </CardContent>
          ) : null}
        </Card>

        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.08fr)_minmax(24rem,1fr)] xl:items-start">

        <Card className="rounded-xl border-slate-200 shadow-sm">
          <CardHeader className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="text-xl text-slate-900 dark:text-slate-100">VI Editor</CardTitle>
              <Button
                variant="outline"
                className="h-10 w-10 px-0"
                onClick={clearEditor}
                disabled={busy || (!editor.path && !editor.content && !editor.originalPath && !selectedFile)}
                aria-label="Clear editor"
                title="Clear editor"
              >
                <Eraser className="h-4 w-4" />
              </Button>
            </div>
            <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_16rem]">
              <div>
                <Label htmlFor="file-path">File Path</Label>
                <Input id="file-path" value={editor.path} onChange={(e) => setEditor((prev) => ({ ...prev, path: e.target.value }))} />
              </div>
              <div>
                <Label>Selected File</Label>
                <p className="mt-2 break-words text-sm text-slate-600 dark:text-slate-300" title={selectedFileMeta?.path || "Draft file"}>
                  {selectedFileMeta?.path || "Draft file"}
                </p>
              </div>
            </div>
          </CardHeader>

          <CardContent className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="file-content">Source</Label>
              <Textarea id="file-content" className="min-h-[44rem] font-mono text-sm leading-6" value={editor.content} onChange={(e) => setEditor((prev) => ({ ...prev, content: e.target.value }))} />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button onClick={saveFile} disabled={busy}>
                <Save className="h-4 w-4" /> {editor.originalPath ? "Save Changes" : "Create File"}
              </Button>
              <Button variant="outline" onClick={saveAndRunFile} disabled={busy}>
                <Play className="h-4 w-4" /> Save & Run
              </Button>
              <Button variant="outline" onClick={runEphemeralFile} disabled={busy}>
                <Play className="h-4 w-4" /> Run
              </Button>
              <Button variant="outline" onClick={runFile} disabled={busy || !editor.originalPath}>
                <Play className="h-4 w-4" /> Run Saved File
              </Button>
              <Button variant="outline" onClick={() => requestDeleteFile(editor.originalPath)} disabled={busy || !editor.originalPath}>
                <Trash2 className="h-4 w-4" /> Delete File
              </Button>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Save & Run writes the current editor buffer first, including path changes. Run executes the current editor buffer without saving it. Run Saved File executes the last saved path without changing the file. The broom clears the editor, clears the path, and removes the current file selection.
            </p>
          </CardContent>
        </Card>

        <VITerminalPanel
          ref={terminalPanelRef}
          backend={backend}
          sourceDir={connection.source_dir}
          activeFilePath={editor.originalPath}
          onOpenFile={safeLoadFile}
          autoConnect={false}
          onSessionChange={({ active }) => {
            setReplActive(Boolean(active))
          }}
        />
        </div>
      </div>

      <Dialog
        open={deleteFileDialogOpen}
        onOpenChange={(open) => {
          setDeleteFileDialogOpen(open)
          if (!open) {
            setDeleteFileTargetPath("")
          }
        }}
      >
        <DialogContent className="border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
          <DialogHeader>
            <DialogTitle>Delete workspace file?</DialogTitle>
            <DialogDescription>
              {deleteFileTargetName
                ? `This will permanently remove ${deleteFileTargetName} from the workspace.`
                : "This will permanently remove the selected file from the workspace."}
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-xl border border-slate-200/80 bg-slate-50 px-3 py-2 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-300">
            {deleteFileTargetPath || "No file selected"}
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setDeleteFileDialogOpen(false)
                setDeleteFileTargetPath("")
              }}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button type="button" variant="destructive" onClick={deleteFile} disabled={busy || !deleteFileTargetPath}>
              {busy ? "Deleting..." : "Delete file"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Card id="vi-modules" className="scroll-mt-24 rounded-xl border-slate-200 shadow-sm">
        <CardHeader className="space-y-3">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <CardTitle className="text-xl text-slate-900 dark:text-slate-100">VI Modules Portal</CardTitle>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                Manage reusable Versa modules once, then import them in portal files, generated services, and VDB-backed scripts with the same syntax as core modules.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" className="h-9" onClick={fetchModules} disabled={busy || modulesLoading}>
                <RefreshCw className="h-4 w-4" /> Refresh Modules
              </Button>
              <Button variant="outline" className="h-9" onClick={startNewModule} disabled={busy}>
                <Plus className="h-4 w-4" /> New Module
              </Button>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 text-xs text-slate-500 dark:text-slate-300">
            <span>Reserved names: {moduleReservedNames.join(", ") || "-"}</span>
            <span>Visible domains: {moduleDomains.join(", ") || "all visible domains"}</span>
            <span>{moduleIsSuperAdmin ? "Super admin scope controls enabled" : "Global scope promotion requires super admin"}</span>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid gap-5 xl:grid-cols-[18rem_minmax(0,1fr)]">
            <div className="space-y-3 xl:max-h-[34rem] xl:overflow-y-auto xl:pr-1">
              {modulesLoading ? (
                <p className="text-sm text-slate-600 dark:text-slate-300">Loading modules...</p>
              ) : modules.length === 0 ? (
                <p className="rounded-xl border border-dashed border-slate-300 p-4 text-sm text-slate-600 dark:border-slate-700 dark:text-slate-300">
                  No visible modules yet. Create one here or promote one to global as super admin.
                </p>
              ) : (
                modules.map((module) => {
                  const active = String(module?.name || "") === selectedModuleName
                  return (
                    <button
                      key={String(module?.name || "")}
                      type="button"
                      onClick={() => loadModule(String(module?.name || ""))}
                      className={`w-full rounded-[1.15rem] border px-4 py-3 text-left transition ${
                        active
                          ? "border-primary/40 bg-primary/[0.08] shadow-[0_16px_30px_rgba(15,118,110,0.12)] dark:border-sky-400/30 dark:bg-sky-400/10"
                          : "border-slate-200/90 bg-white/[0.84] hover:border-slate-300 hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:hover:border-sky-400/20 dark:hover:bg-white/10"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100" title={module?.name || ""}>
                          {module?.title || module?.name}
                        </p>
                        <span className="rounded-full border border-slate-200/90 px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:border-white/10 dark:text-slate-400">
                          {module?.scope || "domain"}
                        </span>
                      </div>
                      <p className="mt-2 text-xs leading-relaxed text-slate-600 dark:text-slate-300">
                        {module?.description || "Reusable Versa module"}
                      </p>
                    </button>
                  )
                })
              )}
            </div>

            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-2">
                  <Label>Module Name</Label>
                  <Input
                    value={moduleEditor.name}
                    onChange={(e) => setModuleEditor((prev) => ({ ...prev, name: e.target.value.toLowerCase() }))}
                    placeholder="my_module"
                    disabled={Boolean(moduleEditor.originalName)}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Display Title</Label>
                  <Input
                    value={moduleEditor.title}
                    onChange={(e) => setModuleEditor((prev) => ({ ...prev, title: e.target.value }))}
                    placeholder="My Module"
                  />
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-[14rem_minmax(0,1fr)]">
                <div className="space-y-2">
                  <Label>Scope</Label>
                  <select
                    className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm dark:border-slate-700 dark:bg-slate-950"
                    value={moduleEditor.scope}
                    onChange={(e) => setModuleEditor((prev) => ({ ...prev, scope: e.target.value }))}
                    disabled={!moduleIsSuperAdmin}
                  >
                    <option value="domain">domain</option>
                    <option value="global">global</option>
                  </select>
                </div>
                <div className="space-y-2">
                  <Label>Description</Label>
                  <Input
                    value={moduleEditor.description}
                    onChange={(e) => setModuleEditor((prev) => ({ ...prev, description: e.target.value }))}
                    placeholder="Reusable Versa helpers for..."
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label>Assigned Domains</Label>
                <div className="flex flex-wrap gap-2">
                  {moduleDomains.map((domain) => {
                    const selected = (moduleEditor.assigned_domains || []).includes(domain)
                    return (
                      <button
                        key={domain}
                        type="button"
                        onClick={() => toggleModuleDomain(domain)}
                        disabled={moduleEditor.scope === "global"}
                        className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                          selected
                            ? "border-emerald-400 bg-emerald-50 text-emerald-700 dark:border-emerald-500/50 dark:bg-emerald-950/40 dark:text-emerald-200"
                            : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"
                        }`}
                      >
                        {domain}
                      </button>
                    )
                  })}
                  {moduleDomains.length === 0 && (
                    <span className="text-xs text-slate-500 dark:text-slate-300">Connect to VDB in the portal to expose owned domains, or create a global module as super admin.</span>
                  )}
                </div>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <div className="space-y-2">
                  <Label>Config Schema JSON</Label>
                  <JsonTextarea
                    value={moduleEditor.config_schema}
                    onChange={(e) => setModuleEditor((prev) => ({ ...prev, config_schema: e.target.value }))}
                    className="min-h-[140px] font-mono text-sm"
                    placeholder='{"defaultProvider":{"type":"string"}}'
                  />
                </div>
                <div className="space-y-2">
                  <Label>Default Config JSON</Label>
                  <JsonTextarea
                    value={moduleEditor.config_defaults}
                    onChange={(e) => setModuleEditor((prev) => ({ ...prev, config_defaults: e.target.value }))}
                    className="min-h-[140px] font-mono text-sm"
                    placeholder='{"defaultProvider":"cloudinary"}'
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label>Module Source (.versa)</Label>
                <Textarea
                  value={moduleEditor.source}
                  onChange={(e) => setModuleEditor((prev) => ({ ...prev, source: e.target.value }))}
                  className="min-h-[22rem] font-mono text-sm leading-6"
                  placeholder={"func hello(name) {\n  return \"hello \" + name;\n}"}
                />
              </div>

              <div className="flex flex-wrap gap-2">
                <Button onClick={saveModule} disabled={busy}>
                  <Save className="h-4 w-4" /> {moduleEditor.originalName ? "Save Module" : "Create Module"}
                </Button>
                <Button variant="outline" onClick={openModuleHarness} disabled={!moduleEditor.name && !moduleEditor.originalName}>
                  <Play className="h-4 w-4" /> Load in VI Editor
                </Button>
                <Button variant="outline" onClick={deleteModule} disabled={busy || !moduleEditor.originalName}>
                  <Trash2 className="h-4 w-4" /> Delete
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Dialog
        open={directoryPickerOpen}
        onOpenChange={(open) => {
          setDirectoryPickerOpen(open)
          if (!open) {
            setDirectoryBrowserError("")
          }
        }}
      >
        <DialogContent className="max-w-3xl border-slate-200 bg-white p-0 dark:border-slate-800 dark:bg-slate-950">
          <div className="border-b border-slate-200/80 p-6 dark:border-slate-800">
            <DialogHeader>
              <DialogTitle>Select Source Folder</DialogTitle>
              <DialogDescription>
                Browse server-side folders and choose where the VI portal stores source files.
              </DialogDescription>
            </DialogHeader>

            {directoryBrowser.roots.length ? (
              <div className="mt-4 flex flex-wrap gap-2">
                {directoryBrowser.roots.map((root) => (
                  <Button
                    key={String(root?.path || root?.label)}
                    type="button"
                    variant={directoryBrowser.path === root?.path ? "default" : "outline"}
                    className="h-9"
                    onClick={() => browseDirectories(root?.path || "")}
                    disabled={directoryBrowserLoading || busy}
                  >
                    {root?.label || "Root"}
                  </Button>
                ))}
              </div>
            ) : null}
          </div>

          <div className="space-y-4 p-6">
            <div className="rounded-[1.15rem] border border-slate-200/80 bg-slate-50/80 p-4 dark:border-slate-800 dark:bg-slate-950/60">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Current Folder</p>
              <p className="mt-3 break-all font-mono text-sm text-slate-800 dark:text-slate-100">
                {directoryBrowser.path || connection.source_dir || "-"}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  className="h-9"
                  onClick={() => browseDirectories(directoryBrowser.parent)}
                  disabled={!directoryBrowser.parent || directoryBrowserLoading || busy}
                >
                  Up One Level
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="h-9"
                  onClick={() => browseDirectories(connection.source_dir || "")}
                  disabled={directoryBrowserLoading || busy}
                >
                  Configured Folder
                </Button>
              </div>
            </div>

            {directoryBrowserError ? <p className="text-sm text-rose-500">{directoryBrowserError}</p> : null}

            <div className="max-h-[24rem] overflow-y-auto rounded-[1.15rem] border border-slate-200/80 dark:border-slate-800">
              {directoryBrowserLoading ? (
                <p className="p-4 text-sm text-slate-600 dark:text-slate-300">Loading folders...</p>
              ) : directoryBrowser.directories.length === 0 ? (
                <p className="p-4 text-sm text-slate-600 dark:text-slate-300">No subfolders inside this directory.</p>
              ) : (
                <div className="divide-y divide-slate-200/80 dark:divide-slate-800">
                  {directoryBrowser.directories.map((directory) => (
                    <button
                      key={String(directory?.path || directory?.name)}
                      type="button"
                      onClick={() => browseDirectories(directory?.path || "")}
                      className="flex w-full items-start gap-3 px-4 py-3 text-left transition hover:bg-slate-50 dark:hover:bg-slate-900/70"
                    >
                      <FolderOpen className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{directory?.name || directory?.path}</p>
                        <p className="mt-1 break-all text-xs text-slate-500 dark:text-slate-400">{directory?.path}</p>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <DialogFooter className="border-t border-slate-200/80 px-6 py-4 dark:border-slate-800">
            <Button type="button" variant="outline" onClick={() => setDirectoryPickerOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button
              type="button"
              className="brand-solid"
              onClick={() => persistSourceDirectory(directoryBrowser.path || connection.source_dir || sourceDirDraft)}
              disabled={directoryBrowserLoading || busy || !(directoryBrowser.path || connection.source_dir || sourceDirDraft)}
            >
              <Check className="h-4 w-4" /> Use This Folder
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function PortalStat({ label, value, icon, wrapValue = false, href = "", caption = "" }) {
  const className = `min-w-0 rounded-[1.15rem] border border-slate-200/[0.85] bg-white/[0.92] p-5 dark:border-white/10 dark:bg-white/5${
    href ? " block transition hover:border-primary/40 hover:bg-primary/[0.06]" : ""
  }`

  const content = (
    <>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="app-stat-label">{label}</p>
          <p
            className={`mt-2 font-semibold text-slate-950 dark:text-slate-100 ${wrapValue ? "break-all text-sm leading-6" : "text-lg"}`}
            title={value}
          >
            {value}
          </p>
          {caption ? <p className="mt-2 text-xs font-medium text-slate-500 dark:text-slate-400">{caption}</p> : null}
        </div>
        <span className="shrink-0">{icon}</span>
      </div>
    </>
  )

  if (href) {
    return (
      <a href={href} className={className}>
        {content}
      </a>
    )
  }

  return (
    <div className={className}>
      {content}
    </div>
  )
}
