"use client"

import { BellRing, ChevronDown, ChevronUp, MessageSquarePlus, Minimize2, PanelRightOpen, Send, Sparkles } from "lucide-react"
import { useRouter } from "next/navigation"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"

import VerseMessageCard from "@/components/verse/verse-message-card"
import VerseAgentProfilePanel from "@/components/verse/verse-agent-profile-panel"
import VerseTypingIndicator from "@/components/verse/verse-typing-indicator"
import VerseUsageMeter from "@/components/verse/verse-usage-meter"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { useDocumentVisible } from "@/hooks/use-document-visible"
import { OperationStatusPanel } from "@/components/ui/operation-status-panel"
import { authHeaders } from "@/lib/auth"
import { computeJitteredDelayMs, createFailureCircuit } from "@/lib/request-circuit"
import { fetchVerseBootstrap } from "@/lib/verse-bootstrap"
import { normalizeVerseContext } from "@/lib/verse-context"
import { consumeCarriedVerseThread, consumePendingVerseAssistantSeed, dispatchVersePageAction, executeVerseServerAction, isVerseServerActionArtifact, storeCarriedVerseThread, storePendingVerseAction, targetPathForVerseArtifact } from "@/lib/verse-actions"
import { fetchVerseNotifications, markVerseNotificationsRead } from "@/lib/verse-notifications"
import { useOperationStatus } from "@/lib/operation-status"
import { isFeatureEnabled, usePlatformFeatureFlags } from "@/lib/platform-flags"

const looksLikeVersaCodingRequest = (content = "", pathname = "/") => {
  const text = String(content || "").trim().toLowerCase()
  if (!text) return pathname === "/vi-portal"
  if (pathname === "/vi-portal") return true
  return /\b(versa|script|cli|terminal|code|coding|program|game|module|debug|fix)\b/i.test(text)
}
const collaborationLabel = (content = "", pathname = "/") =>
  looksLikeVersaCodingRequest(content, pathname)
    ? "Collaborating…"
    : "Collaborating…"
const sendingLabel = (content = "", agentName = "", pathname = "/") => {
  const normalizedName = String(agentName || "").trim()
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

const buildDraftThread = ({ pathname = "/", providerName = "" } = {}) => ({
  id: "",
  title: "Hello, Chat",
  summary: "",
  sourcePathname: pathname,
  providerName: providerName,
  threadOrigin: "user",
  messages: [],
  metadata: { pathname, surface: "dock", draft: true },
})

const VERSE_NOTIFICATION_POLL_INTERVAL_MS = 30_000

export default function VerseAssistantDock({ pathname = "/" }) {
  const router = useRouter()
  const backend = process.env.NEXT_PUBLIC_LIWIRO_BACKEND || "http://127.0.0.1:5000"
  const composerRef = useRef(null)
  const messagesRef = useRef(null)
  const bootstrapPromiseRef = useRef(null)
  const carriedThreadRef = useRef(null)
  const notificationsCircuitRef = useRef(createFailureCircuit({
    failureThreshold: 3,
    baseDelayMs: VERSE_NOTIFICATION_POLL_INTERVAL_MS,
    maxDelayMs: VERSE_NOTIFICATION_POLL_INTERVAL_MS * 6,
  }))
  const notificationPollInFlightRef = useRef(false)
  const [open, setOpen] = useState(false)
  const [bootstrapped, setBootstrapped] = useState(false)
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [me, setMe] = useState(null)
  const [health, setHealth] = useState(null)
  const [agents, setAgents] = useState([])
  const [controlsOpen, setControlsOpen] = useState(false)
  const [showAgentProfiles, setShowAgentProfiles] = useState(false)
  const [selectedProfileAgentId, setSelectedProfileAgentId] = useState("")
  const [thread, setThread] = useState(null)
  const [composer, setComposer] = useState("")
  const [unreadNotifications, setUnreadNotifications] = useState(0)
  const [selectedProvider, setSelectedProvider] = useState("")
  const [sendStatus, setSendStatus] = useState("")
  const [actionState, setActionState] = useState({ messageId: "", mode: "" })
  const {
    status: verseOperationStatus,
    startOperation,
    succeedOperation,
    failOperation,
  } = useOperationStatus({ autoHideSuccessMs: 1500 })
  const { featureFlags } = usePlatformFeatureFlags(backend)
  const documentVisible = useDocumentVisible()
  const showVerseProgress = isFeatureEnabled(featureFlags, "unifiedOperationStatus", true)
    && isFeatureEnabled(featureFlags, "verseActionProgressMessages", true)

  const providerOptions = useMemo(() => (Array.isArray(health?.providers) ? health.providers : []), [health?.providers])
  const provider = useMemo(() => providerOptions.find((item) => item.id === selectedProvider) || null, [providerOptions, selectedProvider])
  const defaultAgent = agents[0] || null
  const collaborationLevel = useMemo(
    () => String(health?.settings?.collaborationLevel || "very collaborative").trim() || "very collaborative",
    [health?.settings?.collaborationLevel]
  )
  const messages = useMemo(() => (Array.isArray(thread?.messages) ? thread.messages : []), [thread?.messages])
  const actionMessage = useMemo(() => messages.find((message) => String(message?.id || "") === String(actionState.messageId || "")) || null, [messages, actionState.messageId])
  const viewerUsername = useMemo(() => resolveUsername(me) || String(thread?.ownerUsername || "").trim(), [me, thread?.ownerUsername])

  const loadThreadById = useCallback(async (threadId) => {
    const normalizedThreadId = String(threadId || "").trim()
    if (!normalizedThreadId) return null
    const res = await fetch(`${backend}/platform/verse/threads/${encodeURIComponent(normalizedThreadId)}`, { headers: authHeaders() })
    const data = await res.json().catch(() => ({}))
    if (res.status === 404) return null
    if (!res.ok) throw new Error(data?.error || "Failed to load Verse thread")
    setThread(data?.thread || null)
    return data?.thread || null
  }, [backend])

  const resolveThread = useCallback(async (healthPayload = null) => {
    const res = await fetch(`${backend}/platform/verse/threads/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        pathname,
        provider: selectedProvider || healthPayload?.defaultProvider || "",
        collaborationLevel,
        metadata: { pathname, surface: "dock" },
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data?.error || "Failed to restore page chat")
    setThread(data?.thread || null)
    return data?.thread || null
  }, [backend, collaborationLevel, pathname, selectedProvider])

  const createThread = useCallback(async (healthPayload = null) => {
    const providerName = String(selectedProvider || healthPayload?.defaultProvider || health?.defaultProvider || "").trim()
    const res = await fetch(`${backend}/platform/verse/threads`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        provider: providerName,
        collaborationLevel,
        threadScope: "dock",
        sourcePathname: pathname,
        metadata: { pathname, surface: "dock" },
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data?.error || "Failed to create a new Verse chat")
    setThread(data?.thread || null)
    setComposer("")
    setShowAgentProfiles(false)
    return data?.thread || null
  }, [backend, collaborationLevel, health?.defaultProvider, pathname, selectedProvider])

  const ensureThread = useCallback(async () => {
    if (thread?.id) return thread
    return createThread()
  }, [createThread, thread])

  const closeDock = useCallback(() => {
    setOpen(false)
    setShowAgentProfiles(false)
    setSelectedProfileAgentId("")
    setComposer((current) => {
      if (thread?.id) return current
      return ""
    })
    setThread((current) => {
      if (current?.id) return current
      return null
    })
  }, [thread?.id])

  const openDock = useCallback(() => {
    setOpen(true)
  }, [])

  const loadNotifications = useCallback(async ({ runScheduler = true, force = false } = {}) => {
    const payload = await fetchVerseNotifications({ backend, runScheduler, force })
    setUnreadNotifications(Number(payload?.unreadCount || 0))
    return payload || {}
  }, [backend])

  const openProactiveThread = useCallback(async (notification, { markRead = true } = {}) => {
    const threadId = String(notification?.threadId || "").trim()
    if (!threadId) return
    try {
      if (markRead) {
        const readPayload = await markVerseNotificationsRead({ backend, threadId })
        setUnreadNotifications(Number(readPayload?.unreadCount || 0))
      }
    } catch {
      // Keep navigation resilient even if the read marker fails.
    }
    if (typeof window !== "undefined") {
      window.localStorage.setItem("liwiro:verse:last-thread-id", threadId)
    }
    router.push(`/verse-ai?threadId=${encodeURIComponent(threadId)}`)
  }, [backend, router])

  const markNotificationPollingHealthy = useCallback(() => {
    return notificationsCircuitRef.current.succeed()
  }, [])

  const markNotificationPollingFailure = useCallback((error, { pause = false, retryAfterMs = 0, reason = "", detail = "" } = {}) => {
    return notificationsCircuitRef.current.fail(error, { pause, retryAfterMs, reason, detail })
  }, [])

  const showNotificationToasts = useCallback((items = []) => {
    for (const item of Array.isArray(items) ? items : []) {
      const title = String(item?.title || item?.agentDisplayName || "Verse proactive update").trim() || "Verse proactive update"
      toast(title, {
        description: String(item?.body || "").trim(),
        action: {
          label: "Open",
          onClick: () => { openProactiveThread(item).catch(() => {}) },
        },
      })
    }
  }, [openProactiveThread])

  const bootstrap = useCallback(async () => {
    if (bootstrapPromiseRef.current) {
      return bootstrapPromiseRef.current
    }
    const promise = (async () => {
      if (showVerseProgress) {
        startOperation({
          title: "Loading page chat",
          detail: "Refreshing the dock thread, agents, and provider state.",
        })
      }
      setLoading(true)
      try {
        const bootstrapData = await fetchVerseBootstrap(backend, { ttlMs: 5000 })
        setMe(bootstrapData?.me || null)
        setHealth(bootstrapData || null)
        setAgents(Array.isArray(bootstrapData?.agents) ? bootstrapData.agents : [])
        const defaultProvider = String(
          bootstrapData?.defaultProvider ||
          (Array.isArray(bootstrapData?.providers) ? bootstrapData.providers.find((item) => item.default)?.id : "")
        ).trim()
        if (defaultProvider) setSelectedProvider((current) => current || defaultProvider)
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
        const carried = carriedThreadRef.current
        if (carried?.threadId) {
          carriedThreadRef.current = null
          const carriedThread = await loadThreadById(carried.threadId)
          if (carriedThread) {
            setBootstrapped(true)
            if (showVerseProgress) {
              succeedOperation({
                title: "Page chat ready",
                detail: "Verse is ready for this page.",
              })
            }
            return carriedThread
          }
        }
        const resolvedThread = await resolveThread(bootstrapData)
        setBootstrapped(true)
        if (showVerseProgress) {
          succeedOperation({
            title: "Page chat ready",
            detail: "Verse is ready for this page.",
          })
        }
        return resolvedThread
      } catch (error) {
        if (showVerseProgress) {
          failOperation({
            title: "Page chat failed to load",
            detail: error?.message || "Failed to load Verse Chat",
          })
        }
        if (open) {
          toast.error(error?.message || "Failed to load Verse Chat")
        }
        throw error
      } finally {
        setLoading(false)
      }
    })()
    bootstrapPromiseRef.current = promise.finally(() => {
      bootstrapPromiseRef.current = null
    })
    return bootstrapPromiseRef.current
  }, [backend, failOperation, loadNotifications, loadThreadById, markNotificationPollingFailure, markNotificationPollingHealthy, open, resolveThread, showNotificationToasts, showVerseProgress, startOperation, succeedOperation])

  useEffect(() => {
    if (!open || pathname === "/verse-ai" || bootstrapped) return
    bootstrap().catch(() => {})
  }, [bootstrapped, bootstrap, open, pathname])
  useEffect(() => { if (open) requestAnimationFrame(() => composerRef.current?.focus()) }, [open])
  useEffect(() => {
    if (!messagesRef.current) return
    messagesRef.current.scrollTop = messagesRef.current.scrollHeight
  }, [messages.length, open])
  useEffect(() => {
    if (pathname === "/verse-ai") return
    setBootstrapped(false)
    setThread(null)
    notificationsCircuitRef.current.reset()
  }, [pathname])
  useEffect(() => {
    const carried = consumeCarriedVerseThread(pathname)
    if (carried?.threadId) {
      carriedThreadRef.current = carried
      setOpen(true)
    }
    const pendingSeed = consumePendingVerseAssistantSeed(pathname)
    if (pendingSeed?.message?.content) {
      setOpen(true)
    }
  }, [pathname])
  useEffect(() => {
    if (pathname === "/verse-ai" || !open || !bootstrapped) return undefined
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
  }, [bootstrapped, documentVisible, loadNotifications, markNotificationPollingFailure, markNotificationPollingHealthy, open, pathname, showNotificationToasts])
  useEffect(() => {
    const currentProvider = String(thread?.providerName || health?.defaultProvider || "").trim()
    if (currentProvider) setSelectedProvider((value) => value || currentProvider)
  }, [health?.defaultProvider, thread?.providerName])

  const handoffThread = useCallback((targetPath, sourceThreadId) => {
    const normalizedTargetPath = String(targetPath || "").trim()
    const normalizedThreadId = String(sourceThreadId || thread?.id || "").trim()
    if (!normalizedTargetPath || !normalizedThreadId || normalizedTargetPath === pathname) return
    storeCarriedVerseThread({
      pathname: normalizedTargetPath,
      targetPath: normalizedTargetPath,
      threadId: normalizedThreadId,
      sourcePathname: pathname,
      sourceSurface: "dock",
      carriedAt: new Date().toISOString(),
    })
  }, [pathname, thread?.id])

  const requestPageContext = useCallback(() => new Promise((resolve) => {
    if (typeof window === "undefined") return resolve({})
    let settled = false
    const finish = (payload = {}) => {
      if (settled) return
      settled = true
      resolve(
        normalizeVerseContext(payload && typeof payload === "object" ? payload : {}, {
          pathname,
          screen: pathname,
        })
      )
    }
    const timer = window.setTimeout(() => finish({}), 150)
    window.dispatchEvent(new CustomEvent("liwiro:verse-assistant-request-context", {
      detail: { pathname, respond: (payload) => { window.clearTimeout(timer); finish(payload) } },
    }))
  }), [pathname])

  const sendMessage = useCallback(async () => {
    const content = String(composer || "").trim()
    if (!content) return
    const respondingAgentName = addressedAgentName(content, agents)
    setSendStatus(sendingLabel(content, respondingAgentName, pathname))
    if (showVerseProgress) {
      startOperation({
        title: "Sending page chat message",
        detail: sendingLabel(content, respondingAgentName, pathname),
      })
    }
    setSending(true)
    try {
      const activeThread = await ensureThread()
      if (!activeThread?.id) throw new Error("Failed to create a new Verse chat")
      const pageContext = await requestPageContext()
      const optimistic = { id: `user-${Date.now()}`, role: "user", content, userDisplayName: viewerUsername || "" }
      setThread((current) => {
        const baseThread = current?.id ? current : activeThread
        if (!baseThread) return current
        return {
          ...baseThread,
          messages: [...(Array.isArray(baseThread.messages) ? baseThread.messages : []), optimistic],
        }
      })
      setComposer("")
      const res = await fetch(`${backend}/platform/verse/threads/${encodeURIComponent(activeThread.id)}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          content,
          provider: selectedProvider,
          collaborationLevel,
          context: { pathname, screen: String(pageContext?.screen || pathname), pageKind: String(pageContext?.pageKind || ""), ...pageContext },
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        const requestError = new Error(data?.error || "Failed to get Verse assistance")
        requestError.status = res.status
        throw requestError
      }
      setThread(data?.thread || null)
      if (showVerseProgress) {
        succeedOperation({
          title: "Verse reply received",
          detail: "The page chat has been updated.",
        })
      }
    } catch (error) {
      const recovered = Number(error?.status) === 404 && thread?.id ? await resolveThread() : null
      if (recovered) {
        const retryContext = await requestPageContext()
        const retryRes = await fetch(`${backend}/platform/verse/threads/${encodeURIComponent(recovered.id)}/messages`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({
            content,
            provider: selectedProvider,
            collaborationLevel,
            context: { pathname, screen: String(retryContext?.screen || pathname), pageKind: String(retryContext?.pageKind || ""), ...retryContext },
          }),
        })
        const retryData = await retryRes.json().catch(() => ({}))
        if (!retryRes.ok) {
          const retryError = new Error(retryData?.error || "Failed to get Verse assistance")
          retryError.status = retryRes.status
          throw retryError
        }
        setThread(retryData?.thread || null)
        setComposer("")
        if (showVerseProgress) {
          succeedOperation({
            title: "Verse reply received",
            detail: "The page chat recovered and updated successfully.",
          })
        }
        return
      }
      if (showVerseProgress) {
        failOperation({
          title: "Failed to get Verse assistance",
          detail: error?.message || "Failed to get Verse assistance",
        })
      }
      toast.error(error?.message || "Failed to get Verse assistance")
    } finally {
      setSending(false)
      setSendStatus("")
    }
  }, [agents, backend, collaborationLevel, composer, ensureThread, failOperation, pathname, requestPageContext, resolveThread, selectedProvider, showVerseProgress, startOperation, succeedOperation, thread?.id, viewerUsername])

  const handleComposerKeyDown = useCallback((event) => {
    if (event.key !== "Enter" || event.shiftKey) return
    event.preventDefault()
    if (sending || !String(composer || "").trim() || !provider?.configured) return
    sendMessage()
  }, [composer, provider?.configured, sendMessage, sending])

  const openInVerse = useCallback(() => {
    if (typeof window !== "undefined" && thread?.id) {
      window.localStorage.setItem("liwiro:verse:last-thread-id", thread.id)
    }
    router.push(thread?.id ? `/verse-ai?threadId=${encodeURIComponent(thread.id)}` : "/verse-ai")
  }, [router, thread?.id])

  const handleNewChat = useCallback(() => {
    const providerName = String(selectedProvider || health?.defaultProvider || "").trim()
    setThread(buildDraftThread({ pathname, providerName }))
    setComposer("")
    setShowAgentProfiles(false)
    setOpen(true)
    requestAnimationFrame(() => composerRef.current?.focus())
  }, [health?.defaultProvider, pathname, selectedProvider])

  const applyArtifact = useCallback((artifact) => dispatchVersePageAction("liwiro:verse-assistant-apply", { pathname, artifact, action: "apply" }), [pathname])

  const handleApplyArtifact = useCallback(async (message) => {
    const artifact = message?.artifact
    if (!artifact) return
    const targetPath = String(targetPathForVerseArtifact(artifact) || "").trim()
    setActionState({ messageId: String(message?.id || ""), mode: "apply" })
    try {
      if (String(artifact?.kind || "").trim() === "page-navigation" && targetPath && pathname !== targetPath) {
        handoffThread(targetPath, thread?.id)
        storePendingVerseAction({ targetPath, mode: "apply", artifact, threadId: String(thread?.id || ""), sourcePathname: pathname, sourceSurface: "dock" })
        return router.push(targetPath)
      }
      const result = await applyArtifact(artifact)
      if (result?.ok) return toast.success(result.message || "Applied Verse changes to the page.")
      if (targetPath && pathname !== targetPath) {
        handoffThread(targetPath, thread?.id)
        storePendingVerseAction({ targetPath, mode: "apply", artifact, threadId: String(thread?.id || ""), sourcePathname: pathname, sourceSurface: "dock" })
        return router.push(targetPath)
      }
      throw new Error(result?.message || "This page could not apply the Verse output.")
    } catch (error) {
      toast.error(error?.message || "This page could not apply the Verse output.")
    } finally {
      setActionState({ messageId: "", mode: "" })
    }
  }, [applyArtifact, handoffThread, pathname, router, thread?.id])

  const handleExecuteArtifact = useCallback(async (message) => {
    const artifact = message?.artifact
    if (!artifact) return
    const targetPath = String(targetPathForVerseArtifact(artifact) || "").trim()
    setActionState({ messageId: String(message?.id || ""), mode: "execute" })
    try {
      if (isVerseServerActionArtifact(artifact) && targetPath && targetPath !== pathname) {
        const result = await executeVerseServerAction({ backend, artifact, context: { pathname } })
        if (!result?.ok) throw new Error(result?.message || "Verse could not run the requested action.")
        return toast.success(result.message || "Verse completed the action.")
      }
      const result = await dispatchVersePageAction("liwiro:verse-assistant-execute", { pathname, artifact, action: "execute" }, 1000)
      if (result?.ok) return toast.success(result.message || "Verse completed the action.")
      if (targetPath && pathname !== targetPath) {
        handoffThread(targetPath, thread?.id)
        storePendingVerseAction({ targetPath, mode: "execute", artifact, threadId: String(thread?.id || ""), sourcePathname: pathname, sourceSurface: "dock" })
        return router.push(targetPath)
      }
      throw new Error(result?.message || "Verse could not run the requested action.")
    } catch (error) {
      toast.error(error?.message || "Verse could not run the requested action.")
    } finally {
      setActionState({ messageId: "", mode: "" })
    }
  }, [backend, handoffThread, pathname, router, thread?.id])

  const handleSaveExecuteArtifact = useCallback(async (message) => {
    const artifact = message?.artifact
    if (!artifact) return
    const targetPath = String(targetPathForVerseArtifact(artifact) || "").trim()
    setActionState({ messageId: String(message?.id || ""), mode: "save-execute" })
    try {
      if (targetPath && pathname !== targetPath) {
        handoffThread(targetPath, thread?.id)
        storePendingVerseAction({ targetPath, mode: "save-execute", artifact, threadId: String(thread?.id || ""), sourcePathname: pathname, sourceSurface: "dock" })
        return router.push(targetPath)
      }
      const result = await dispatchVersePageAction("liwiro:verse-assistant-execute", { pathname, artifact, action: "save-execute" }, 1000)
      if (result?.ok) return toast.success(result.message || "Verse saved and ran the action.")
      throw new Error(result?.message || "Verse could not save and run the requested action.")
    } catch (error) {
      toast.error(error?.message || "Verse could not save and run the requested action.")
    } finally {
      setActionState({ messageId: "", mode: "" })
    }
  }, [handoffThread, pathname, router, thread?.id])

  if (pathname === "/verse-ai") return null

  const shellClass = pathname === "/service-builder"
    ? "pointer-events-none fixed bottom-4 left-4 z-[70] max-w-[calc(100vw-1rem)] lg:left-6"
    : "pointer-events-none fixed bottom-4 right-4 z-[70] max-w-[calc(100vw-1rem)] lg:right-6"

  return (
    <div className={shellClass}>
      {open ? (
        <div className="pointer-events-auto flex h-[min(48rem,calc(100vh-6rem))] w-[25rem] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-[1.7rem] border border-white/10 bg-[#08111c]/95 shadow-[0_30px_90px_rgba(0,0,0,0.45)] backdrop-blur-xl">
          <div className="border-b border-white/10 px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-teal-300/80">Verse Chat</p>
              </div>
              <div className="flex items-center gap-2">
                <span className="truncate rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] text-slate-100">
                  {String(thread?.sourcePathname || pathname || "Page chat")}
                </span>
                {unreadNotifications > 0 ? (
                  <span className="rounded-full border border-white/10 bg-white/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-white">
                    {unreadNotifications}
                  </span>
                ) : null}
                <Button size="icon" variant="ghost" className="h-8 w-8 rounded-full" onClick={handleNewChat} aria-label="New chat">
                  <MessageSquarePlus className="h-4 w-4" />
                </Button>
                <Button size="icon" variant="ghost" className="h-8 w-8 rounded-full" onClick={openInVerse}><PanelRightOpen className="h-4 w-4" /></Button>
                <Button size="icon" variant="ghost" className="h-8 w-8 rounded-full" onClick={closeDock}><Minimize2 className="h-4 w-4" /></Button>
              </div>
            </div>
          </div>

          {showVerseProgress && verseOperationStatus?.visible ? (
            <div className="px-4 pt-3">
              <OperationStatusPanel status={verseOperationStatus} />
            </div>
          ) : null}

          {controlsOpen ? (
            <div className="flex min-h-0 flex-1 flex-col px-4 py-4">
              <div className="flex items-center justify-between gap-3">
                <p className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Chat controls</p>
                <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setControlsOpen((value) => !value)} aria-label="Hide controls">
                  <ChevronDown className="h-4 w-4" />
                </Button>
              </div>
              <div className="mt-3 flex min-h-0 flex-1 flex-col overflow-hidden rounded-[1.4rem] border border-white/10 bg-white/[0.03]">
                <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
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
                    <div className="mt-2 grid gap-2">
                      {agents.map((agent) => (
                        <div key={agent.id} className="flex overflow-hidden rounded-full border border-white/10 bg-white/[0.03]">
                          <button
                            type="button"
                            onClick={() => {
                              setComposer((current) => `@${agent.displayName || agent.name} ${String(current || "").trimStart()}`.trimStart())
                              requestAnimationFrame(() => composerRef.current?.focus())
                            }}
                            className="min-w-0 flex-1 px-3 py-2 text-left text-sm text-slate-100 transition hover:bg-white/[0.08]"
                          >
                            @{agent.displayName || agent.name}
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedProfileAgentId(agent.id)
                              setShowAgentProfiles(true)
                            }}
                            className="shrink-0 border-l border-white/10 px-3 py-2 text-sm text-slate-300 transition hover:bg-white/[0.08] hover:text-white"
                          >
                            View abilities
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="border-t border-white/10 px-4 py-3">
                  <VerseUsageMeter
                    messages={messages}
                    selectedProviderOption={provider}
                    selectedProvider={selectedProvider}
                    scopeLabel="Current chat widget thread"
                    className="w-full"
                    tooltipAlign="start"
                  />
                </div>
              </div>
            </div>
          ) : (
            <>
              <div ref={messagesRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
                {messages.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-white/10 px-4 py-6 text-sm text-slate-400">
                    Start a conversation and replies will appear here.
                  </div>
                ) : (
                  <>
                    {messages.map((message) => (
                      <VerseMessageCard
                        key={message.id || `${message.role}-${message.createdAt}`}
                        message={message}
                        onApplyArtifact={handleApplyArtifact}
                        onExecuteArtifact={handleExecuteArtifact}
                        onSaveExecuteArtifact={handleSaveExecuteArtifact}
                        applyBusy={actionState.messageId === String(message?.id || "") && actionState.mode === "apply"}
                        executeBusy={actionState.messageId === String(message?.id || "") && actionState.mode === "execute"}
                        saveExecuteBusy={actionState.messageId === String(message?.id || "") && actionState.mode === "save-execute"}
                        userDisplayName={viewerUsername}
                      />
                    ))}
                    {actionState.mode ? (
                      <VerseTypingIndicator label={String(actionMessage?.agentDisplayName || "").trim() ? `${String(actionMessage?.agentDisplayName || "").trim()} is working…` : "Collaborating…"} />
                    ) : sending ? (
                      <VerseTypingIndicator label={sendStatus || "Collaborating…"} />
                    ) : null}
                  </>
                )}
              </div>

              <div className="border-t border-white/10 px-4 py-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Chat controls</p>
                  <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setControlsOpen((value) => !value)} aria-label="Show controls">
                    <ChevronUp className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </>
          )}
          {!controlsOpen ? (
            <div className="border-t border-white/10 px-4 py-4">
              <div className="relative">
                <Textarea
                  ref={composerRef}
                  value={composer}
                  onChange={(event) => setComposer(event.target.value)}
                  onKeyDown={handleComposerKeyDown}
                  placeholder="Chat with verse agents"
                  className="min-h-[6rem] rounded-[1.1rem] pr-12"
                />
                <Button
                  size="icon"
                  variant="secondary"
                  className="absolute bottom-3 right-3"
                  onClick={sendMessage}
                  disabled={sending || !String(composer || "").trim() || !provider?.configured}
                  aria-label="Send message"
                >
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      ) : (
        <Button className="pointer-events-auto h-12 rounded-full px-4 shadow-[0_18px_40px_rgba(0,0,0,0.28)]" onClick={openDock}>
          {unreadNotifications > 0 ? <BellRing className="mr-2 h-4 w-4" /> : <Sparkles className="mr-2 h-4 w-4" />}
          Verse Chat
          {unreadNotifications > 0 ? (
            <span className="ml-2 rounded-full bg-black/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-white">
              {unreadNotifications}
            </span>
          ) : null}
        </Button>
      )}
      {showAgentProfiles ? (
        <VerseAgentProfilePanel
          agents={agents}
          compact
          initialAgentId={selectedProfileAgentId}
          onClose={() => {
            setShowAgentProfiles(false)
            setSelectedProfileAgentId("")
          }}
        />
      ) : null}
    </div>
  )
}
