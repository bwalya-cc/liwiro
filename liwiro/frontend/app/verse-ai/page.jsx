"use client"

import { BellRing, Bot, ChevronDown, ChevronUp, EyeOff, Trash, Wand2 } from "lucide-react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"

import VerseMessageCard from "@/components/verse/verse-message-card"
import VerseAgentProfilePanel from "@/components/verse/verse-agent-profile-panel"
import VerseTypingIndicator from "@/components/verse/verse-typing-indicator"
import VerseUsageMeter from "@/components/verse/verse-usage-meter"
import { useDocumentVisible } from "@/hooks/use-document-visible"
import { authHeaders } from "@/lib/auth"
import { computeJitteredDelayMs, createFailureCircuit } from "@/lib/request-circuit"
import { fetchVerseBootstrap } from "@/lib/verse-bootstrap"
import { normalizeVerseContext } from "@/lib/verse-context"
import { dispatchVersePageAction, executeVerseServerAction, isVerseServerActionArtifact, storeCarriedVerseThread, storePendingVerseAction, targetPathForVerseArtifact } from "@/lib/verse-actions"
import { fetchVerseNotifications, ignoreVerseIssue, markVerseNotificationsRead } from "@/lib/verse-notifications"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { OperationStatusPanel } from "@/components/ui/operation-status-panel"
import { useOperationStatus } from "@/lib/operation-status"
import { isFeatureEnabled, usePlatformFeatureFlags } from "@/lib/platform-flags"

const LAST_THREAD_KEY = "liwiro:verse:last-thread-id"
const VERSE_NOTIFICATION_POLL_INTERVAL_MS = 30_000

const titleOf = (thread) => String(thread?.title || "Hello, Chat")
const looksLikeVersaCodingRequest = (content = "", pathname = "/verse-ai") => {
  const text = String(content || "").trim().toLowerCase()
  if (!text) return pathname === "/vi-portal"
  if (pathname === "/vi-portal") return true
  return /\b(versa|script|cli|terminal|code|coding|program|game|module|debug|fix)\b/i.test(text)
}
const collaborationLabel = (content = "", pathname = "/verse-ai") =>
  looksLikeVersaCodingRequest(content, pathname)
    ? "Collaborating…"
    : "Collaborating…"
const sendingLabel = (content = "", name = "", pathname = "/verse-ai") => {
  const normalizedName = String(name || "").trim()
  if (!normalizedName) return collaborationLabel(content, pathname)
  return looksLikeVersaCodingRequest(content, pathname)
    ? `${normalizedName} is working…`
    : `${normalizedName} is replying…`
}
const addressedAgentName = (content = "", agents = []) => {
  const text = String(content || "")
  for (const agent of Array.isArray(agents) ? agents : []) {
    const displayName = String(agent?.displayName || "").trim()
    const baseName = String(agent?.name || "").trim()
    for (const candidate of [displayName, baseName]) {
      if (!candidate) continue
      const escaped = candidate.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
      if (new RegExp(`(^|\\s)@${escaped}(?=\\s|$)`, "i").test(text)) {
        return displayName || baseName || ""
      }
    }
  }
  return ""
}

const resolveUsername = (value) => String(
  value?.username
  || value?.user?.username
  || value?.account?.username
  || value?.profile?.username
  || value?.data?.username
  || "",
).trim()

const buildDraftThread = ({ providerName = "" } = {}) => ({
  id: "",
  title: "Hello, Chat",
  summary: "",
  providerName,
  threadOrigin: "user",
  messages: [],
  metadata: { draft: true },
})

export default function VersePage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const backend = process.env.NEXT_PUBLIC_LIWIRO_BACKEND || "http://127.0.0.1:5000"
  const [collaborationLevel, setCollaborationLevel] = useState("very collaborative")
  const [me, setMe] = useState(null)
  const [health, setHealth] = useState(null)
  const [agents, setAgents] = useState([])
  const [threads, setThreads] = useState([])
  const [notifications, setNotifications] = useState([])
  const [deletingThreadId, setDeletingThreadId] = useState("")
  const [unreadNotifications, setUnreadNotifications] = useState(0)
  const [activeThreadId, setActiveThreadId] = useState("")
  const [activeThread, setActiveThread] = useState(null)
  const [composer, setComposer] = useState("")
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [creating, setCreating] = useState(false)
  const [controlsOpen, setControlsOpen] = useState(false)
  const [showAgentProfiles, setShowAgentProfiles] = useState(false)
  const [selectedProfileAgentId, setSelectedProfileAgentId] = useState("")
  const [selectedProvider, setSelectedProvider] = useState("")
  const [sendStatus, setSendStatus] = useState("")
  const [actionState, setActionState] = useState({ messageId: "", mode: "" })
  const {
    status: verseOperationStatus,
    startOperation,
    succeedOperation,
    failOperation,
  } = useOperationStatus({ autoHideSuccessMs: 1600 })
  const composerRef = useRef(null)
  const messagesRef = useRef(null)
  const notificationsCircuitRef = useRef(createFailureCircuit({
    failureThreshold: 3,
    baseDelayMs: VERSE_NOTIFICATION_POLL_INTERVAL_MS,
    maxDelayMs: VERSE_NOTIFICATION_POLL_INTERVAL_MS * 6,
  }))
  const notificationPollInFlightRef = useRef(false)
  const { featureFlags } = usePlatformFeatureFlags(backend)
  const documentVisible = useDocumentVisible()
  const showVerseProgress = isFeatureEnabled(featureFlags, "unifiedOperationStatus", true)
    && isFeatureEnabled(featureFlags, "verseActionProgressMessages", true)

  const defaultAgent = agents[0] || null
  const activeAgent = useMemo(() => agents.find((agent) => agent.id === String(activeThread?.activeAgentId || "")) || defaultAgent || null, [activeThread?.activeAgentId, agents, defaultAgent])
  const providerOptions = useMemo(() => (Array.isArray(health?.providers) ? health.providers : []), [health?.providers])
  const provider = useMemo(() => providerOptions.find((item) => item.id === selectedProvider) || null, [providerOptions, selectedProvider])
  const requestedThreadId = String(searchParams?.get("threadId") || "").trim()
  const actionMessage = useMemo(() => (Array.isArray(activeThread?.messages) ? activeThread.messages : []).find((item) => String(item?.id || "") === String(actionState.messageId || "")) || null, [activeThread?.messages, actionState.messageId])
  const isProactiveThread = String(activeThread?.threadOrigin || activeThread?.metadata?.threadOrigin || "").trim() === "proactive"
  const activeIssueKey = String(activeThread?.issueKey || activeThread?.metadata?.issueKey || "").trim()
  const activeProactiveAgentId = String(activeThread?.proactiveAgentId || activeThread?.metadata?.proactiveAgentId || "").trim()
  const activeProactiveAgent = useMemo(() => agents.find((agent) => agent.id === activeProactiveAgentId) || null, [activeProactiveAgentId, agents])
  const viewerUsername = useMemo(() => resolveUsername(me) || String(activeThread?.ownerUsername || "").trim(), [activeThread?.ownerUsername, me])
  const versePageContext = useMemo(() => normalizeVerseContext({
    pathname: "/verse-ai",
    screen: "/verse-ai",
    pageKind: "verse-portal",
    pageSummary: "The user is working in the main Verse portal with saved threads and proactive notifications.",
  }), [])

  const loadThreads = useCallback(async () => {
    const res = await fetch(`${backend}/platform/verse/threads`, { headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data?.error || "Failed to load Verse threads")
    const nextThreads = Array.isArray(data?.threads) ? data.threads : []
    setThreads(nextThreads)
    return nextThreads
  }, [backend])

  const loadThread = useCallback(async (threadId) => {
    if (!threadId) return setActiveThread(null)
    const res = await fetch(`${backend}/platform/verse/threads/${encodeURIComponent(threadId)}`, { headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data?.error || "Failed to load Verse thread")
    setActiveThread(data?.thread || null)
    return data?.thread || null
  }, [backend])

  const loadThreadSafe = useCallback(async (threadId, { updateState = true } = {}) => {
    const normalizedThreadId = String(threadId || "").trim()
    if (!normalizedThreadId) {
      if (updateState) setActiveThread(null)
      return null
    }
    const res = await fetch(`${backend}/platform/verse/threads/${encodeURIComponent(normalizedThreadId)}`, { headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (res.status === 404) {
      if (updateState) setActiveThread(null)
      return null
    }
    if (!res.ok) throw new Error(data?.error || "Failed to load Verse thread")
    if (updateState) setActiveThread(data?.thread || null)
    return data?.thread || null
  }, [backend])

  const loadNotifications = useCallback(async ({ runScheduler = false, force = false } = {}) => {
    const payload = await fetchVerseNotifications({ backend, runScheduler, force })
    const items = Array.isArray(payload?.items) ? payload.items : []
    setNotifications(items)
    setUnreadNotifications(Number(payload?.unreadCount || 0))
    return payload || {}
  }, [backend])

  const openNotificationThread = useCallback(async (notification, { markRead = true } = {}) => {
    const threadId = String(notification?.threadId || "").trim()
    if (!threadId) return
    try {
      if (markRead) {
        const readPayload = await markVerseNotificationsRead({ backend, threadId })
        setUnreadNotifications(Number(readPayload?.unreadCount || 0))
      }
      setActiveThreadId(threadId)
      await Promise.all([
        loadNotifications({ runScheduler: false }),
        loadThread(threadId),
        loadThreads(),
      ])
    } catch (error) {
      toast.error(error?.message || "Failed to open the proactive Verse thread")
    }
  }, [backend, loadNotifications, loadThread, loadThreads])

  const showNotificationToasts = useCallback((items = []) => {
    for (const item of Array.isArray(items) ? items : []) {
      const title = String(item?.title || item?.agentDisplayName || "Verse proactive update").trim() || "Verse proactive update"
      const description = String(item?.body || "").trim()
      toast(title, {
        description,
        action: {
          label: "Open",
          onClick: () => { openNotificationThread(item).catch(() => {}) },
        },
      })
    }
  }, [openNotificationThread])

  const markNotificationPollingHealthy = useCallback(() => {
    return notificationsCircuitRef.current.succeed()
  }, [])

  const markNotificationPollingFailure = useCallback((error, { pause = false, retryAfterMs = 0, reason = "", detail = "" } = {}) => {
    return notificationsCircuitRef.current.fail(error, { pause, retryAfterMs, reason, detail })
  }, [])

  const bootstrap = useCallback(async () => {
    if (showVerseProgress) {
      startOperation({
        title: "Loading Verse Chat",
        detail: "Refreshing agents, threads, provider health, and proactive notifications.",
      })
    }
    setLoading(true)
    try {
      const [bootstrapData, threadList] = await Promise.all([
        fetchVerseBootstrap(backend, { ttlMs: 5000 }),
        loadThreads(),
      ])
      setMe(bootstrapData?.me || null)
      setHealth(bootstrapData || null)
      setAgents(Array.isArray(bootstrapData?.agents) ? bootstrapData.agents : [])
      const nextLevel = String(bootstrapData?.settings?.collaborationLevel || "").trim()
      if (nextLevel) setCollaborationLevel(nextLevel)
      let notificationsPayload = {}
      try {
        notificationsPayload = await loadNotifications()
      } catch (error) {
        markNotificationPollingFailure(error)
      }
      if (notificationsPayload?.degraded || notificationsPayload?.schedulerDeferred) {
        markNotificationPollingFailure(null, {
          pause: Boolean(notificationsPayload?.degraded),
          retryAfterMs: Number(notificationsPayload?.retryAfterMs || 0),
          reason: String(notificationsPayload?.reason || "").trim(),
        })
      } else {
        markNotificationPollingHealthy()
      }
      if (Array.isArray(notificationsPayload?.emitted) && notificationsPayload.emitted.length > 0) {
        showNotificationToasts(notificationsPayload.emitted)
      }
      const refreshedThreads = Array.isArray(notificationsPayload?.emitted) && notificationsPayload.emitted.length > 0
        ? await loadThreads()
        : threadList
      const storedThreadId = typeof window !== "undefined" ? String(window.localStorage.getItem(LAST_THREAD_KEY) || "").trim() : ""
      const candidateIds = [
        requestedThreadId,
        storedThreadId,
        String((refreshedThreads[0] || {}).id || notificationsPayload?.emitted?.[0]?.threadId || ""),
      ].filter(Boolean)
      let resolvedThread = null
      for (const candidateId of candidateIds) {
        resolvedThread = await loadThreadSafe(candidateId, { updateState: false })
        if (resolvedThread) break
        if (candidateId === storedThreadId && typeof window !== "undefined") {
          window.localStorage.removeItem(LAST_THREAD_KEY)
        }
      }
      if (resolvedThread?.id) {
        setActiveThreadId(String(resolvedThread.id || ""))
        setActiveThread(resolvedThread)
      } else {
        setActiveThreadId("")
        setActiveThread(null)
      }
      if (showVerseProgress) {
        succeedOperation({
          title: "Verse Chat ready",
          detail: "Threads and provider state are loaded.",
        })
      }
    } catch (error) {
      if (showVerseProgress) {
        failOperation({
          title: "Verse Chat failed to load",
          detail: error?.message || "Failed to load Verse Chat",
        })
      }
      toast.error(error?.message || "Failed to load Verse Chat")
    } finally {
      setLoading(false)
    }
  }, [backend, failOperation, loadNotifications, loadThreadSafe, loadThreads, markNotificationPollingFailure, markNotificationPollingHealthy, requestedThreadId, showNotificationToasts, showVerseProgress, startOperation, succeedOperation])

  useEffect(() => { bootstrap() }, [bootstrap])
  useEffect(() => {
    if (!activeThreadId) return undefined
    loadThreadSafe(activeThreadId).then((thread) => {
      if (!thread && typeof window !== "undefined" && String(window.localStorage.getItem(LAST_THREAD_KEY) || "").trim() === activeThreadId) {
        window.localStorage.removeItem(LAST_THREAD_KEY)
      }
    }).catch((error) => toast.error(error?.message || "Failed to load Verse thread"))
    if (typeof window !== "undefined") window.localStorage.setItem(LAST_THREAD_KEY, activeThreadId)
    return undefined
  }, [activeThreadId, loadThreadSafe])
  useEffect(() => {
    if (!documentVisible) return undefined
    let cancelled = false
    let timerId = 0

    const scheduleNextPoll = (delay = VERSE_NOTIFICATION_POLL_INTERVAL_MS) => {
      window.clearTimeout(timerId)
      if (cancelled) return
      timerId = window.setTimeout(() => {
        void runPoll()
      }, Math.max(0, Number(delay) || 0))
    }

    const runPoll = async () => {
      if (cancelled || notificationPollInFlightRef.current) return
      notificationPollInFlightRef.current = true
      let nextDelay = VERSE_NOTIFICATION_POLL_INTERVAL_MS
      try {
        const payload = await loadNotifications()
        if (cancelled) return
        if (Array.isArray(payload?.emitted) && payload.emitted.length > 0) {
          showNotificationToasts(payload.emitted)
          await loadThreads()
          if (activeThreadId && payload.emitted.some((item) => String(item?.threadId || "") === activeThreadId)) {
            await loadThread(activeThreadId)
          }
        }
        if (payload?.degraded || payload?.schedulerDeferred) {
          const failureState = markNotificationPollingFailure(null, {
            pause: Boolean(payload?.degraded),
            retryAfterMs: Number(payload?.retryAfterMs || 0),
            reason: String(payload?.reason || "").trim(),
          })
          nextDelay = Math.max(failureState.retryAfterMs, VERSE_NOTIFICATION_POLL_INTERVAL_MS)
        } else {
          markNotificationPollingHealthy()
        }
      } catch (error) {
        if (cancelled) return
        const failureState = markNotificationPollingFailure(error)
        nextDelay = failureState.paused
          ? Math.max(failureState.retryAfterMs, VERSE_NOTIFICATION_POLL_INTERVAL_MS)
          : computeJitteredDelayMs(failureState.retryAfterMs || VERSE_NOTIFICATION_POLL_INTERVAL_MS)
      } finally {
        notificationPollInFlightRef.current = false
        if (!cancelled) {
          scheduleNextPoll(nextDelay)
        }
      }
    }

    void runPoll()
    return () => {
      cancelled = true
      window.clearTimeout(timerId)
    }
  }, [activeThreadId, documentVisible, loadNotifications, loadThread, loadThreads, markNotificationPollingFailure, markNotificationPollingHealthy, showNotificationToasts])
  useEffect(() => {
    const currentProvider = String(activeThread?.providerName || health?.defaultProvider || providerOptions.find((item) => item.default)?.id || "").trim()
    if (currentProvider) setSelectedProvider((value) => value || currentProvider)
  }, [activeThread?.providerName, health?.defaultProvider, providerOptions])
  useEffect(() => {
    if (!messagesRef.current) return
    messagesRef.current.scrollTop = messagesRef.current.scrollHeight
  }, [activeThread?.messages?.length, activeThread?.synthesis?.content, sending])

  const createPersistentThread = useCallback(async () => {
    setCreating(true)
    try {
      const res = await fetch(`${backend}/platform/verse/threads`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ provider: selectedProvider, collaborationLevel, threadScope: "portal" }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || "Failed to create Verse thread")
      const thread = data?.thread || null
      if (thread) {
        setThreads((current) => [thread, ...current.filter((item) => item.id !== thread.id)])
        setActiveThreadId(String(thread.id || ""))
        setActiveThread(thread)
      }
      return thread
    } finally {
      setCreating(false)
    }
  }, [backend, collaborationLevel, selectedProvider])

  const createThread = useCallback(() => {
    const providerName = String(selectedProvider || health?.defaultProvider || providerOptions.find((item) => item.default)?.id || "").trim()
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(LAST_THREAD_KEY)
    }
    setActiveThreadId("")
    setActiveThread(buildDraftThread({ providerName }))
    setComposer("")
    setShowAgentProfiles(false)
    requestAnimationFrame(() => composerRef.current?.focus())
  }, [health?.defaultProvider, providerOptions, selectedProvider])

  const ensureThread = useCallback(async () => {
    if (activeThreadId) {
      const existing = await loadThreadSafe(activeThreadId, { updateState: false })
      if (existing?.id) {
        if (!activeThread || String(activeThread?.id || "") !== String(existing.id || "")) {
          setActiveThread(existing)
        }
        return String(existing.id || "")
      }
      setActiveThreadId("")
      setActiveThread(null)
      if (typeof window !== "undefined" && String(window.localStorage.getItem(LAST_THREAD_KEY) || "").trim() === activeThreadId) {
        window.localStorage.removeItem(LAST_THREAD_KEY)
      }
    }
    return String((await createPersistentThread())?.id || "")
  }, [activeThread, activeThreadId, createPersistentThread, loadThreadSafe])

  const carryThreadToPath = useCallback((targetPath, threadId) => {
    const normalizedTargetPath = String(targetPath || "").trim()
    const normalizedThreadId = String(threadId || activeThreadId || activeThread?.id || "").trim()
    if (!normalizedTargetPath || !normalizedThreadId) return
    storeCarriedVerseThread({
      pathname: normalizedTargetPath,
      targetPath: normalizedTargetPath,
      threadId: normalizedThreadId,
      sourcePathname: "/verse-ai",
      sourceSurface: "portal",
      carriedAt: new Date().toISOString(),
    })
  }, [activeThread?.id, activeThreadId])

  const deleteThread = useCallback(async (threadId) => {
    if (!threadId) return
    if (typeof window !== "undefined" && !window.confirm("Delete this chat? This cannot be undone.")) return
    setDeletingThreadId(threadId)
    try {
      const res = await fetch(`${backend}/platform/verse/threads/${encodeURIComponent(threadId)}`, {
        method: "DELETE",
        headers: authHeaders(),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || "Failed to delete Verse chat")
      const remainingThreads = threads.filter((item) => String(item?.id || "") !== threadId)
      setThreads(remainingThreads)
      if (threadId === activeThreadId) {
        const nextId = String((remainingThreads[0] || {}).id || "")
        setActiveThread(threadId === String(activeThread?.id || "") ? null : activeThread)
        setActiveThreadId(nextId)
        if (!nextId && typeof window !== "undefined") {
          window.localStorage.removeItem(LAST_THREAD_KEY)
        }
      }
      loadThreads().catch(() => {})
      loadNotifications({ runScheduler: false }).catch(() => {})
    } catch (error) {
      toast.error(error?.message || "Failed to delete the chat")
    } finally {
      setDeletingThreadId((current) => (current === threadId ? "" : current))
    }
  }, [activeThread, activeThreadId, backend, loadNotifications, loadThreads, threads])

  const handleThreadKeyDown = useCallback((event, threadId) => {
    if (event.key !== "Enter" && event.key !== " ") return
    event.preventDefault()
    setActiveThreadId(threadId)
  }, [])

  const markActiveThreadRead = useCallback(async () => {
    if (!activeThreadId) return
    const payload = await markVerseNotificationsRead({ backend, threadId: activeThreadId })
    setUnreadNotifications(Number(payload?.unreadCount || 0))
    await Promise.all([
      loadNotifications({ runScheduler: false }),
      loadThread(activeThreadId),
      loadThreads(),
    ])
  }, [activeThreadId, backend, loadNotifications, loadThread, loadThreads])

  const ignoreActiveThreadIssue = useCallback(async () => {
    if (!activeIssueKey) return
    const payload = await ignoreVerseIssue({
      backend,
      issueKey: activeIssueKey,
      agentId: activeProactiveAgentId,
      threadId: activeThreadId,
    })
    setUnreadNotifications(Number(payload?.unreadCount || 0))
    await Promise.all([
      loadNotifications({ runScheduler: false }),
      activeThreadId ? loadThread(activeThreadId) : Promise.resolve(),
      loadThreads(),
    ])
  }, [activeIssueKey, activeProactiveAgentId, activeThreadId, backend, loadNotifications, loadThread, loadThreads])

  const sendMessage = useCallback(async () => {
    const content = composer.trim()
    if (!content) return
    const respondingAgentName = addressedAgentName(content, agents)
    setSendStatus(sendingLabel(content, respondingAgentName, "/verse-ai"))
    if (showVerseProgress) {
      startOperation({
        title: "Sending Verse message",
        detail: sendingLabel(content, respondingAgentName, "/verse-ai"),
      })
    }
    setSending(true)
    try {
      const threadId = await ensureThread()
      const optimistic = { id: `optimistic-${Date.now()}`, role: "user", content, createdAt: new Date().toISOString(), userDisplayName: viewerUsername || "" }
      setActiveThread((current) => {
        const baseThread = current || buildDraftThread({ providerName: selectedProvider })
        return {
          ...baseThread,
          messages: [...(Array.isArray(baseThread.messages) ? baseThread.messages : []), optimistic],
        }
      })
      const res = await fetch(`${backend}/platform/verse/threads/${encodeURIComponent(threadId)}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ content, provider: selectedProvider, collaborationLevel, context: versePageContext }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || "Failed to send Verse message")
      setComposer("")
      setActiveThread(data?.thread || null)
      if (!activeThreadId) {
        setActiveThreadId(threadId)
      }
      await Promise.all([
        loadThreads(),
        loadNotifications({ runScheduler: false }),
      ])
      if (showVerseProgress) {
        succeedOperation({
          title: "Verse reply received",
          detail: "The thread has been updated with the latest response.",
        })
      }
    } catch (error) {
      if (activeThreadId) loadThreadSafe(activeThreadId).catch(() => {})
      if (showVerseProgress) {
        failOperation({
          title: "Failed to send Verse message",
          detail: error?.message || "Failed to send Verse message",
        })
      }
      toast.error(error?.message || "Failed to send Verse message")
    } finally {
      setSending(false)
      setSendStatus("")
    }
  }, [activeThreadId, agents, backend, collaborationLevel, composer, ensureThread, failOperation, loadNotifications, loadThreadSafe, loadThreads, selectedProvider, showVerseProgress, startOperation, succeedOperation, versePageContext, viewerUsername])

  const onComposerKeyDown = useCallback((event) => {
    if (event.key !== "Enter" || event.shiftKey) return
    event.preventDefault()
    if (sending || !composer.trim() || !provider?.configured) return
    sendMessage()
  }, [composer, provider?.configured, sendMessage, sending])

  const mentionAgent = useCallback((agent, seed = "") => {
    const displayName = String(agent?.displayName || agent?.name || "").trim()
    if (!displayName) return
    const nextSeed = String(seed || "").trim()
    setComposer((current) => `@${displayName} ${nextSeed || String(current || "").trimStart()}`.trimStart())
    requestAnimationFrame(() => composerRef.current?.focus())
  }, [])

  const synthesize = useCallback(async () => {
    if (!activeThreadId) return
    const res = await fetch(`${backend}/platform/verse/threads/${encodeURIComponent(activeThreadId)}/synthesis`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ provider: selectedProvider, context: versePageContext }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) return toast.error(data?.error || "Failed to synthesize Verse thread")
    setActiveThread(data?.thread || null)
    await loadThreads()
  }, [activeThreadId, backend, loadThreads, selectedProvider, versePageContext])

  const handleArtifactApply = useCallback(async (message) => {
    const artifact = message?.artifact
    if (!artifact) return
    const targetPath = String(targetPathForVerseArtifact(artifact) || "").trim()
    setActionState({ messageId: String(message?.id || ""), mode: "apply" })
    if (showVerseProgress) {
      startOperation({
        title: "Opening Verse action",
        detail: "Preparing the target page or artifact.",
      })
    }
    try {
      carryThreadToPath(targetPath, activeThreadId)
      storePendingVerseAction({ targetPath, mode: "apply", artifact, threadId: String(activeThreadId || activeThread?.id || ""), sourcePathname: "/verse-ai", sourceSurface: "portal" })
      if (targetPath) return router.push(targetPath)
      const result = await dispatchVersePageAction("liwiro:verse-assistant-apply", { pathname: "/verse-ai", artifact, action: "apply" })
      if (!result?.ok) throw new Error(result?.message || "Verse could not open this action.")
      if (showVerseProgress) {
        succeedOperation({
          title: "Verse action opened",
          detail: result.message || "The prepared action is ready.",
        })
      }
      toast.success(result.message || "Verse opened the prepared action.")
    } catch (error) {
      if (showVerseProgress) {
        failOperation({
          title: "Verse action failed",
          detail: error?.message || "Verse could not open this action.",
        })
      }
      toast.error(error?.message || "Verse could not open this action.")
    } finally {
      setActionState({ messageId: "", mode: "" })
    }
  }, [activeThread?.id, activeThreadId, carryThreadToPath, failOperation, router, showVerseProgress, startOperation, succeedOperation])

  const handleArtifactExecute = useCallback(async (message) => {
    const artifact = message?.artifact
    if (!artifact) return
    const targetPath = String(targetPathForVerseArtifact(artifact) || "").trim()
    setActionState({ messageId: String(message?.id || ""), mode: "execute" })
    if (showVerseProgress) {
      startOperation({
        title: "Running Verse action",
        detail: "Executing the prepared action.",
      })
    }
    try {
      if (isVerseServerActionArtifact(artifact)) {
        const result = await executeVerseServerAction({ backend, artifact, context: { pathname: "/verse-ai" } })
        if (!result?.ok) throw new Error(result?.message || "Verse could not run this action.")
        if (showVerseProgress) {
          succeedOperation({
            title: "Verse action completed",
            detail: result.message || "The server action completed.",
          })
        }
        toast.success(result.message || "Verse completed the action.")
        return
      }
      carryThreadToPath(targetPath, activeThreadId)
      storePendingVerseAction({ targetPath, mode: "execute", artifact, threadId: String(activeThreadId || activeThread?.id || ""), sourcePathname: "/verse-ai", sourceSurface: "portal" })
      if (targetPath) return router.push(targetPath)
      const result = await dispatchVersePageAction("liwiro:verse-assistant-execute", { pathname: "/verse-ai", artifact, action: "execute" })
      if (!result?.ok) throw new Error(result?.message || "Verse could not run this action.")
      if (showVerseProgress) {
        succeedOperation({
          title: "Verse action completed",
          detail: result.message || "The action completed successfully.",
        })
      }
      toast.success(result.message || "Verse completed the action.")
    } catch (error) {
      if (showVerseProgress) {
        failOperation({
          title: "Verse action failed",
          detail: error?.message || "Verse could not run this action.",
        })
      }
      toast.error(error?.message || "Verse could not run this action.")
    } finally {
      setActionState({ messageId: "", mode: "" })
    }
  }, [activeThread?.id, activeThreadId, backend, carryThreadToPath, failOperation, router, showVerseProgress, startOperation, succeedOperation])

  const handleArtifactSaveExecute = useCallback(async (message) => {
    const artifact = message?.artifact
    if (!artifact) return
    const targetPath = String(targetPathForVerseArtifact(artifact) || "").trim()
    setActionState({ messageId: String(message?.id || ""), mode: "save-execute" })
    if (showVerseProgress) {
      startOperation({
        title: "Saving and running Verse action",
        detail: "Applying the prepared file and executing it.",
      })
    }
    try {
      carryThreadToPath(targetPath, activeThreadId)
      storePendingVerseAction({ targetPath, mode: "save-execute", artifact, threadId: String(activeThreadId || activeThread?.id || ""), sourcePathname: "/verse-ai", sourceSurface: "portal" })
      if (targetPath) return router.push(targetPath)
      const result = await dispatchVersePageAction("liwiro:verse-assistant-execute", {
        pathname: "/verse-ai",
        artifact,
        action: "save-execute",
      })
      if (!result?.ok) throw new Error(result?.message || "Verse could not save and run this action.")
      if (showVerseProgress) {
        succeedOperation({
          title: "Verse action completed",
          detail: result.message || "The action was saved and executed.",
        })
      }
      toast.success(result.message || "Verse saved and ran the action.")
      await Promise.all([
        loadThreads(),
        loadNotifications({ runScheduler: false }),
      ])
    } catch (error) {
      if (showVerseProgress) {
        failOperation({
          title: "Verse action failed",
          detail: error?.message || "Verse could not save and run this action.",
        })
      }
      toast.error(error?.message || "Verse could not save and run this action.")
    } finally {
      setActionState({ messageId: "", mode: "" })
    }
  }, [activeThread?.id, activeThreadId, carryThreadToPath, failOperation, loadNotifications, loadThreads, router, showVerseProgress, startOperation, succeedOperation])

  const actionLabel = actionState.mode
    ? (() => {
        const actionAgentName = String(actionMessage?.agentDisplayName || activeAgent?.displayName || "").trim()
        return actionAgentName ? `${actionAgentName} is working…` : "Collaborating…"
      })()
    : ""

  return (
    <>
      <div className="min-h-[calc(100vh-7rem)] bg-[radial-gradient(circle_at_top_left,rgba(20,184,166,0.12),transparent_34%),radial-gradient(circle_at_top_right,rgba(249,115,22,0.12),transparent_30%),linear-gradient(180deg,#08111c_0%,#0d1724_40%,#0b1420_100%)] px-4 py-5 md:px-6">
        <div className="mx-auto max-w-[1600px] space-y-4">
          {showVerseProgress && verseOperationStatus?.visible ? (
            <OperationStatusPanel status={verseOperationStatus} />
          ) : null}
          <Card className="border-white/10 bg-white/[0.05]">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-white">Verse settings</CardTitle>
                  <p className="mt-1 text-sm text-slate-400">Manage collaboration and specialist cadence from Settings → Verse.</p>
                </div>
                <Link href="/settings#verse">
                  <Button size="sm" variant="secondary">Open Verse settings</Button>
                </Link>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-slate-300">
                Manage collaboration levels, proactive outreach, and specialist details alongside platform policies under Settings → Verse. Collapse the controls below to give the chat more room.
              </p>
            </CardContent>
          </Card>

          <Card className="overflow-hidden border-white/10 bg-[#08111c]/88 shadow-[0_30px_90px_rgba(0,0,0,0.38)]">
            <div className="grid min-h-[82vh] xl:h-[min(76vh,52rem)] xl:min-h-0 xl:grid-cols-[minmax(0,1fr)_minmax(0,3fr)]">
              <aside className="border-b border-white/10 bg-black/10 xl:flex xl:min-h-0 xl:flex-col xl:border-b-0 xl:border-r xl:border-white/10">
                <div className="border-b border-white/10 px-5 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-xl font-semibold text-white">Verse Chat</p>
                      <p className="mt-1 text-sm text-slate-400">Saved threads and provider status.</p>
                    </div>
                    <Button onClick={createThread} disabled={creating}>{creating ? "Creating…" : "New Chat"}</Button>
                  </div>
                  <div className="mt-3 rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-slate-300">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Status</p>
                    <p className="mt-1 font-semibold text-white">{health?.configured ? "Ready" : "Not configured"}</p>
                  </div>
                </div>
                <div className="px-4 py-4 xl:min-h-0 xl:flex-1 xl:overflow-y-auto xl:overscroll-contain">
                  <div className="mb-5">
                    <div className="flex items-center justify-between gap-3 px-1">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Inbox</p>
                      <Badge variant="secondary" className="rounded-full bg-white/10 text-white">
                        {unreadNotifications}
                      </Badge>
                    </div>
                    <div className="mt-3 space-y-2">
                      {notifications.length === 0 ? (
                        <div className="rounded-2xl border border-dashed border-white/10 px-4 py-5 text-sm text-slate-400">
                          No proactive pings yet.
                        </div>
                      ) : notifications.map((notification) => {
                        const threadId = String(notification.threadId || "")
                        const active = threadId && threadId === activeThreadId
                        return (
                          <button
                            key={notification.notificationId || `${threadId}-${notification.createdAt}`}
                            type="button"
                            onClick={() => openNotificationThread(notification).catch(() => {})}
                            className={`w-full rounded-2xl border px-4 py-3 text-left ${active ? "border-teal-400/35 bg-teal-400/10" : "border-white/10 bg-white/5 hover:bg-white/[0.08]"}`}
                          >
                            <div className="flex items-center justify-between gap-3">
                              <p className="font-semibold text-white">{notification.title || notification.threadTitle || "Proactive thread"}</p>
                              <Badge variant="secondary" className="rounded-full bg-white/10 text-white">
                                {notification.status === "reminded" ? "Reminder" : notification.unread ? "Unread" : "Read"}
                              </Badge>
                            </div>
                            <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-400">{notification.agentDisplayName || notification.agentId || "Verse"}</p>
                            <p className="mt-2 text-xs text-slate-400">{notification.body || "Open the proactive thread for details."}</p>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                  <p className="px-1 text-[11px] uppercase tracking-[0.18em] text-slate-400">Threads</p>
                  <div className="mt-3 space-y-2">
                    {threads.length === 0 ? <div className="rounded-2xl border border-dashed border-white/10 px-4 py-5 text-sm text-slate-400">No saved chats yet.</div> : threads.map((thread) => {
                      const threadId = String(thread.id || "")
                      const active = threadId === activeThreadId
                      const threadClass = active
                        ? "border-teal-400/35 bg-teal-400/10"
                        : "border-white/10 bg-white/5 hover:bg-white/[0.08]"
                      return (
                        <div
                          key={threadId}
                          role="button"
                          tabIndex={0}
                          onClick={() => setActiveThreadId(threadId)}
                          onKeyDown={(event) => handleThreadKeyDown(event, threadId)}
                          className={`w-full rounded-2xl border px-4 py-3 text-left ${threadClass}`}
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex items-center gap-2">
                              <p className="font-semibold text-white">{titleOf(thread)}</p>
                              {String(thread.threadOrigin || "").trim() === "proactive" ? <Badge variant="secondary" className="rounded-full bg-white/10 text-white">Agent-started</Badge> : null}
                            </div>
                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation()
                                deleteThread(threadId)
                              }}
                              disabled={deletingThreadId === threadId}
                              aria-label="Delete chat"
                              className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-white/10 bg-black/40 text-white transition hover:border-rose-300 hover:text-rose-300 disabled:cursor-wait disabled:opacity-40"
                            >
                              <Trash className="h-4 w-4" />
                            </button>
                          </div>
                          <p className="mt-1 text-xs text-slate-400">{thread.summary || "No summary yet"}</p>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </aside>

              <section className="flex min-h-0 flex-col">
                <div className="border-b border-white/10 px-5 py-4">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                    <div className="min-w-0">
                      <p className="truncate text-xl font-semibold text-white">{titleOf(activeThread)}</p>
                      <p className="mt-1 text-sm text-slate-400">{activeThread?.summary || "Start a conversation or pick a saved thread."}</p>
                      {isProactiveThread ? (
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          <Badge variant="secondary" className="rounded-full bg-white/10 text-white">Agent-started</Badge>
                          <Badge variant="secondary" className="rounded-full bg-white/10 text-white">{activeProactiveAgent?.displayName || activeProactiveAgentId || "Verse"}</Badge>
                          <Badge variant="secondary" className="rounded-full bg-white/10 text-white">
                            {String(activeThread?.notificationState || "").trim() === "reminded" ? "Reminder" : String(activeThread?.notificationState || "").trim() === "ignored" ? "Ignored" : "Proactive"}
                          </Badge>
                        </div>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-2">
                      {isProactiveThread ? (
                        <>
                          <Button size="sm" variant="secondary" onClick={() => markActiveThreadRead().catch((error) => toast.error(error?.message || "Failed to mark the thread as read"))}>
                            <BellRing className="mr-2 h-4 w-4" />Mark Read
                          </Button>
                          <Button size="sm" variant="secondary" onClick={() => ignoreActiveThreadIssue().catch((error) => toast.error(error?.message || "Failed to ignore the matter"))}>
                            <EyeOff className="mr-2 h-4 w-4" />Ignore Matter
                          </Button>
                        </>
                      ) : null}
                      <Button size="sm" variant="secondary" onClick={synthesize} disabled={!activeThreadId}><Wand2 className="mr-2 h-4 w-4" />Refresh</Button>
                    </div>
                  </div>
                </div>

                <div ref={messagesRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-5">
                  {loading ? <div className="rounded-2xl border border-dashed border-white/10 px-4 py-8 text-center text-sm text-slate-400">Loading Verse Chat…</div> : Array.isArray(activeThread?.messages) && activeThread.messages.length > 0 ? (
                    <>
                      {activeThread.messages.map((message) => (
                          <VerseMessageCard
                            key={message.id || `${message.role}-${message.createdAt}`}
                            message={message}
                            onApplyArtifact={handleArtifactApply}
                            onExecuteArtifact={handleArtifactExecute}
                            onSaveExecuteArtifact={handleArtifactSaveExecute}
                            applyBusy={actionState.messageId === String(message?.id || "") && actionState.mode === "apply"}
                            executeBusy={actionState.messageId === String(message?.id || "") && actionState.mode === "execute"}
                            saveExecuteBusy={actionState.messageId === String(message?.id || "") && actionState.mode === "save-execute"}
                            userDisplayName={viewerUsername}
                          />
                      ))}
                      {actionState.mode ? <VerseTypingIndicator label={actionLabel} /> : sending ? <VerseTypingIndicator label={sendStatus || "Collaborating…"} /> : null}
                    </>
                  ) : <div className="rounded-[1.6rem] border border-dashed border-white/10 bg-white/[0.04] px-5 py-8 text-center text-sm text-slate-400">Start a thread and your chat history will stay here.</div>}
                </div>

                <div className="border-t border-white/10 bg-black/10 px-5 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Chat controls</p>
                    <Button variant="secondary" size="sm" onClick={() => setControlsOpen((value) => !value)}>
                      {controlsOpen ? (
                        <>
                          <ChevronDown className="mr-2 h-4 w-4" />
                          Hide controls
                        </>
                      ) : (
                        <>
                          <ChevronUp className="mr-2 h-4 w-4" />
                          Show controls
                        </>
                      )}
                    </Button>
                  </div>
                  {controlsOpen ? (
                    <div className="mt-3 space-y-4">
                      <div>
                        <p className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Providers</p>
                        {providerOptions.length === 0 ? (
                          <p className="mt-2 text-xs text-slate-500">No providers available yet.</p>
                        ) : (
                          <div className="mt-2 flex flex-wrap gap-2">
                            {providerOptions.map((item) => (
                              <Button
                                key={item.id}
                                size="sm"
                                variant={selectedProvider === item.id ? "default" : "outline"}
                                className="rounded-full"
                                onClick={() => setSelectedProvider(item.id)}
                                disabled={!item.configured}
                              >
                                {item.label || item.id}
                              </Button>
                            ))}
                          </div>
                        )}
                        <p className="mt-2 text-xs text-slate-400">
                          {provider?.configured
                            ? "Provider is ready. Select another provider to switch."
                            : provider?.probe?.error || health?.probe?.error || "Configure a provider before sending messages."
                          }
                        </p>
                      </div>
                      <div>
                        <p className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Specialists</p>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {agents.map((agent) => (
                            <div key={agent.id} className="flex items-center gap-2">
                              <Button
                                size="sm"
                                variant="secondary"
                                className="rounded-full"
                                onClick={() => mentionAgent(agent)}
                              >
                                @{agent.displayName || agent.name}
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                className="rounded-full"
                                onClick={() => {
                                  setSelectedProfileAgentId(agent.id)
                                  setShowAgentProfiles(true)
                                }}
                              >
                                View abilities
                              </Button>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className="flex items-center justify-between gap-3">
                        <VerseUsageMeter
                          messages={Array.isArray(activeThread?.messages) ? activeThread.messages : []}
                          selectedProviderOption={provider}
                          selectedProvider={selectedProvider}
                          scopeLabel="Current thread"
                        />
                        <p className="text-xs text-slate-400">{provider?.configured ? "Usage shared for the active provider." : "Usage pending until a provider responds."}</p>
                      </div>
                    </div>
                  ) : (
                    <p className="mt-3 text-xs text-slate-500">Controls are hidden. Expand to continue the conversation.</p>
                  )}
                </div>
                <div className="border-t border-white/5 bg-black/[0.25] px-5 py-4">
                  <Textarea
                    ref={composerRef}
                    value={composer}
                    onChange={(event) => setComposer(event.target.value)}
                    onKeyDown={onComposerKeyDown}
                    placeholder="Work with verse agents to build, debug, validate, document, or route work."
                    className="min-h-[6rem] rounded-[1.3rem]"
                  />
                  <div className="mt-3 flex justify-end">
                    <Button
                      size="icon"
                      variant="secondary"
                      className="h-10 w-10 rounded-full"
                      onClick={sendMessage}
                      disabled={sending || !composer.trim() || !provider?.configured}
                      aria-label="Send message"
                    >
                      <Bot className="h-5 w-5" />
                    </Button>
                  </div>
                </div>
              </section>
            </div>
          </Card>
        </div>
      </div>

      {showAgentProfiles ? (
        <VerseAgentProfilePanel
          agents={agents}
          initialAgentId={selectedProfileAgentId}
          onClose={() => {
            setShowAgentProfiles(false)
            setSelectedProfileAgentId("")
          }}
        />
      ) : null}
    </>
  )
}
