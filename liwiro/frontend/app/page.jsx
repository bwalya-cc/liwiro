"use client"

import Link from "next/link"
import { Activity, ArrowRight, BarChart3, Bot, DatabaseZap, Hammer, ServerCog, SquareTerminal } from "lucide-react"
import { useCallback, useEffect, useMemo, useState } from "react"

import { WorkspaceLayout } from "@/components/ide/workspace-layout"
import AnanseChartView from "@/components/verse/ananse-chart-view"
import VerseAgentProfilePanel from "@/components/verse/verse-agent-profile-panel"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { fetchAuthedJson } from "@/lib/authed-json-cache"
import { fetchVerseBootstrap } from "@/lib/verse-bootstrap"

export default function HomePage() {
  const backend = process.env.NEXT_PUBLIC_LIWIRO_BACKEND || "http://127.0.0.1:5000"
  const [loading, setLoading] = useState(true)
  const [services, setServices] = useState([])
  const [vdbConnection, setVdbConnection] = useState(null)
  const [viConnection, setViConnection] = useState(null)
  const [me, setMe] = useState(null)
  const [agents, setAgents] = useState([])
  const [agentsLoading, setAgentsLoading] = useState(false)
  const [agentsLoadError, setAgentsLoadError] = useState("")

  useEffect(() => {
    let cancelled = false

    const loadDashboard = async () => {
      setLoading(true)
      try {
        const servicesUrl = new URL(`${backend}/services`)
        servicesUrl.searchParams.set("summary", "1")
        servicesUrl.searchParams.set("refresh", "0")
        const [servicesRes, vdbRes, viRes, meRes] = await Promise.allSettled([
          fetchAuthedJson(servicesUrl.toString(), { ttlMs: 2500 }),
          fetchAuthedJson(`${backend}/platform/vdb/connection`, { ttlMs: 2500 }),
          fetchAuthedJson(`${backend}/platform/vi/connection`, { ttlMs: 2500 }),
          fetchAuthedJson(`${backend}/auth/me`, { ttlMs: 2500 }),
        ])

        if (cancelled) return

        if (servicesRes.status === "fulfilled") {
          setServices(Array.isArray(servicesRes.value) ? servicesRes.value : [])
        }

        if (vdbRes.status === "fulfilled") {
          setVdbConnection(vdbRes.value || {})
        }

        if (viRes.status === "fulfilled") {
          setViConnection(viRes.value || {})
        }

        if (meRes.status === "fulfilled") {
          setMe(meRes.value || null)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    loadDashboard()

    return () => {
      cancelled = true
    }
  }, [backend])

  const loadAgentProfiles = useCallback(async () => {
    if (agentsLoading || agents.length > 0) return
    setAgentsLoading(true)
    setAgentsLoadError("")
    try {
      const bootstrap = await fetchVerseBootstrap(backend, { ttlMs: 10000 })
      setAgents(Array.isArray(bootstrap?.agents) ? bootstrap.agents : [])
    } catch (error) {
      setAgentsLoadError(error?.message || "Failed to load Verse specialists")
    } finally {
      setAgentsLoading(false)
    }
  }, [agents.length, agentsLoading, backend])

  const runningServices = useMemo(
    () => services.filter((service) => service?.status === "RUNNING"),
    [services],
  )
  const stoppedServices = services.length - runningServices.length
  const recentServices = useMemo(
    () =>
      [...services]
        .sort((left, right) => new Date(right?.createdAt || 0).getTime() - new Date(left?.createdAt || 0).getTime())
        .slice(0, 5),
    [services],
  )
  const serviceStatusChart = useMemo(
    () => ({
      chartType: "donut",
      title: "Service status mix",
      description: "Running versus stopped services in the current control plane snapshot.",
      data: [
        { label: "Running", value: runningServices.length },
        { label: "Stopped", value: Math.max(stoppedServices, 0) },
      ],
      xKey: "label",
      valueKey: "value",
      confidence: "High",
      intent: "composition",
      status: "ready",
    }),
    [runningServices.length, stoppedServices]
  )
  const serviceTrendChart = useMemo(() => {
    const counts = new Map()
    for (const service of services) {
      const key = service?.createdAt ? new Date(service.createdAt).toLocaleDateString() : "Unknown"
      counts.set(key, (counts.get(key) || 0) + 1)
    }
    return {
      chartType: "bar",
      title: "Recent service creation",
      description: "How many services were added on each visible day.",
      data: Array.from(counts.entries()).map(([label, value]) => ({ label, value })),
      xKey: "label",
      yKeys: ["value"],
      valueKey: "value",
      confidence: "Medium",
      intent: "trend",
      status: "ready",
    }
  }, [services])
  const docsCoverageChart = useMemo(() => ({
    chartType: "bar",
    title: "Docs coverage",
    description: "Services with docs enabled versus disabled.",
    data: [
      { label: "Docs on", value: services.filter((item) => item?.docsEnabled !== false).length },
      { label: "Docs off", value: services.filter((item) => item?.docsEnabled === false).length },
    ],
    xKey: "label",
    yKeys: ["value"],
    valueKey: "value",
    confidence: "High",
    intent: "comparison",
    status: "ready",
  }), [services])

  useEffect(() => {
    const handleVerseContextRequest = (event) => {
      const respond = event?.detail?.respond
      if (typeof respond !== "function") return
      respond({
        pageKind: "dashboard",
        screen: "dashboard",
        pathname: "/",
        services: services.map((service) => ({
          apiName: String(service?.apiName || ""),
          processId: String(service?.processId || ""),
          status: String(service?.status || ""),
          basePath: String(service?.basePath || ""),
          port: service?.port ?? null,
          docsEnabled: service?.docsEnabled !== false,
        })),
        metrics: {
          runningServices: runningServices.length,
          stoppedServices,
          docsEnabled: services.filter((item) => item?.docsEnabled !== false).length,
        },
        vdbStatus: vdbConnection?.liwiro_db ? "Connected" : "Unknown",
        viStatus: viConnection?.repl_active ? "REPL live" : "Ready",
      })
    }
    window.addEventListener("liwiro:verse-assistant-request-context", handleVerseContextRequest)
    return () => {
      window.removeEventListener("liwiro:verse-assistant-request-context", handleVerseContextRequest)
    }
  }, [runningServices.length, services, stoppedServices, vdbConnection?.liwiro_db, viConnection?.repl_active])

  const systemSignals = [
    {
      label: "Active Services",
      value: loading ? "..." : String(runningServices.length),
      note: `${stoppedServices} stopped`,
      icon: ServerCog,
    },
    {
      label: "Database Status",
      value: vdbConnection?.liwiro_db ? "Connected" : "Unknown",
      note: vdbConnection?.liwiro_db || "No Liwiro DB reported",
      icon: DatabaseZap,
    },
    {
      label: "VI Runtime",
      value: viConnection?.repl_active ? "REPL live" : "Ready",
      note: viConnection?.source_dir || "Runtime info unavailable",
      icon: SquareTerminal,
    },
    {
      label: "Operator",
      value: me?.username || "Workspace user",
      note: me?.is_super_admin ? "Super admin" : "Platform session",
      icon: Activity,
    },
  ]

  const quickLinks = [
    {
      title: "Create a Service",
      description: "Open the builder and define metadata, auth, models, and endpoints.",
      href: "/service-builder",
      icon: Hammer,
    },
    {
      title: "Manage Runtime",
      description: "Inspect services, start or stop them, and jump into service editors.",
      href: "/services",
      icon: ServerCog,
    },
    {
      title: "Open VDB Console",
      description: "Run raw VDB queries or use the structured command studio.",
      href: "/vdb-portal",
      icon: DatabaseZap,
    },
    {
      title: "Read the Wiki",
      description: "Browse architecture, configuration reference, and API concepts.",
      href: "/wiki",
      icon: Bot,
    },
    {
      title: "Open Ananse",
      description: "Explore datasets, switch chart methods, and build richer visual analysis.",
      href: "/ananse-workbench",
      icon: BarChart3,
    },
  ]

  const systemPanel = (
    <>
      <div className="grid gap-3 sm:grid-cols-2">
        {systemSignals.map((signal) => {
          const Icon = signal.icon
          return (
            <div key={signal.label} className="rounded-[1.25rem] border border-white/10 bg-white/5 p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="app-stat-label">{signal.label}</p>
                  <p className="mt-2 break-words text-2xl font-semibold text-white">{signal.value}</p>
                  <p className="mt-1 break-all text-sm text-slate-400">{signal.note}</p>
                </div>
                <span className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-white/10 bg-sky-400/10 text-sky-200">
                  <Icon className="h-5 w-5" />
                </span>
              </div>
            </div>
          )
        })}
      </div>

      <div className="rounded-[1.25rem] border border-white/10 bg-white/5 p-4">
        <p className="workspace-panel-label">Recent Activity</p>
        <div className="mt-3 space-y-3">
          {recentServices.length === 0 ? (
            <p className="text-sm text-slate-400">No services have been generated yet.</p>
          ) : (
            recentServices.map((service) => (
              <Link
                key={String(service?.processId || service?.apiName)}
                href={`/services/${encodeURIComponent(service?.processId || "")}`}
                className="block rounded-xl border border-white/10 bg-[rgba(255,255,255,0.03)] px-3 py-3 text-sm text-slate-100 hover:bg-white/[0.08]"
              >
                <p className="font-semibold text-white">{service?.apiName || service?.processId}</p>
                <p className="mt-1 text-xs text-slate-400">
                  {service?.status === "RUNNING" ? "Running" : "Stopped"} • {service?.createdAt ? new Date(service.createdAt).toLocaleString() : "No timestamp"}
                </p>
              </Link>
            ))
          )}
        </div>
      </div>
    </>
  )

  const editorPanel = (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Runtime Overview</CardTitle>
          <p className="text-sm text-slate-400">
            A condensed operational snapshot across generated services and platform modules.
          </p>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-3 md:grid-cols-3">
            <DashboardMetric label="Running" value={String(runningServices.length)} note="Service processes online" />
            <DashboardMetric label="Stopped" value={String(stoppedServices)} note="Services awaiting start" />
            <DashboardMetric label="Docs" value={String(services.filter((item) => item?.docsEnabled !== false).length)} note="Service docs enabled" />
          </div>

          <div className="grid gap-4">
            <div className="rounded-[1.2rem] border border-white/10 bg-[rgba(255,255,255,0.04)] p-4">
              <div className="grid gap-4 xl:grid-cols-[minmax(16rem,0.8fr)_minmax(0,1.2fr)] xl:items-center">
                <div>
                  <p className="app-stat-label">Service Status Mix</p>
                  <p className="mt-1 text-sm text-slate-400">Running versus stopped services right now.</p>
                </div>
                <AnanseChartView chart={serviceStatusChart} compact />
              </div>
            </div>
            <div className="rounded-[1.2rem] border border-white/10 bg-[rgba(255,255,255,0.04)] p-4">
              <div className="grid gap-4 xl:grid-cols-[minmax(16rem,0.8fr)_minmax(0,1.2fr)] xl:items-center">
                <div>
                  <p className="app-stat-label">Docs Coverage</p>
                  <p className="mt-1 text-sm text-slate-400">How many services expose documentation today.</p>
                </div>
                <AnanseChartView chart={docsCoverageChart} compact />
              </div>
            </div>
            <div className="rounded-[1.2rem] border border-white/10 bg-[rgba(255,255,255,0.04)] p-4">
              <div className="grid gap-4 xl:grid-cols-[minmax(16rem,0.8fr)_minmax(0,1.2fr)] xl:items-center">
                <div>
                  <p className="app-stat-label">Recent Service Creation</p>
                  <p className="mt-1 text-sm text-slate-400">Creation volume across the visible time window.</p>
                </div>
                <AnanseChartView chart={serviceTrendChart} compact tablePreview={serviceTrendChart.data} />
              </div>
            </div>
          </div>

          <div className="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <div className="rounded-[1.2rem] border border-white/10 bg-[rgba(255,255,255,0.03)] p-4">
              <p className="app-stat-label">System Logs</p>
              <div className="mt-3 min-w-0 space-y-2 font-mono text-xs text-slate-300">
                <p className="break-all">{loading ? "[loading] refreshing dashboard state" : `[services] ${services.length} records loaded from backend`}</p>
                <p className="break-all">{vdbConnection?.liwiro_db ? `[vdb] connected to ${vdbConnection.liwiro_domain || "domain"}/${vdbConnection.liwiro_db}` : "[vdb] connection status unavailable"}</p>
                <p className="break-all">{viConnection?.source_dir ? `[vi] source dir ${viConnection.source_dir}` : "[vi] portal connection status unavailable"}</p>
                <p className="break-all">{me?.username ? `[auth] session active for ${me.username}` : "[auth] session context unavailable"}</p>
              </div>
            </div>

            <div className="space-y-3">
              <p className="app-stat-label">Service Queue</p>
              {services.length === 0 ? (
                <div className="rounded-[1.2rem] border border-dashed border-white/10 px-4 py-8 text-center text-sm text-slate-400">
                  No services yet. Start from Service Builder.
                </div>
              ) : (
                <div className="grid gap-3 lg:grid-cols-2">
                  {services.slice(0, 6).map((service) => (
                    <Link
                      key={String(service?.processId || service?.apiName)}
                      href={`/services/${encodeURIComponent(service?.processId || "")}`}
                      className="flex min-h-[6.5rem] items-center justify-between rounded-[1.15rem] border border-white/10 bg-[rgba(255,255,255,0.03)] px-4 py-3 text-sm hover:bg-white/[0.08]"
                    >
                      <div className="min-w-0">
                        <p className="truncate font-semibold text-white">{service?.apiName || service?.processId}</p>
                        <p className="mt-1 line-clamp-2 text-xs text-slate-400">
                          {service?.basePath || "/"} • {service?.port ? `port ${service.port}` : "no port assigned"}
                        </p>
                      </div>
                      <span className={`ml-3 shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${service?.status === "RUNNING" ? "bg-emerald-400/10 text-emerald-200" : "bg-amber-400/10 text-amber-200"}`}>
                        {service?.status === "RUNNING" ? "Running" : "Stopped"}
                      </span>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-5 xl:grid-cols-[minmax(18rem,0.75fr)_minmax(0,1.25fr)]">
        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>Quick Create</CardTitle>
              <p className="text-sm text-slate-400">Start a new service definition or open an existing runtime entry.</p>
            </CardHeader>
            <CardContent className="space-y-3">
              <Link href="/service-builder" className="block">
                <Button className="w-full justify-between">
                  Open Service Builder
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
              <Link href="/services" className="block pt-2">
                <Button variant="outline" className="w-full justify-between">
                  Open Service Manager
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Quick Access</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3">
              {quickLinks.map((link) => {
                const Icon = link.icon
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    className="block rounded-[1.2rem] border border-white/10 bg-[rgba(255,255,255,0.03)] p-4 transition hover:bg-white/[0.08]"
                  >
                    <div className="flex items-start gap-3">
                      <span className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-sky-400/10 text-sky-200">
                        <Icon className="h-4 w-4" />
                      </span>
                      <div>
                        <p className="font-semibold text-white">{link.title}</p>
                        <p className="mt-1 text-sm text-slate-400">{link.description}</p>
                      </div>
                    </div>
                  </Link>
                )
              })}
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Verse Specialists</CardTitle>
            <p className="text-sm text-slate-400">Load specialist profiles only when needed to keep dashboard startup lighter.</p>
          </CardHeader>
          <CardContent>
            {agents.length > 0 ? (
              <VerseAgentProfilePanel
                agents={agents}
                compact
                modal={false}
              />
            ) : (
              <div className="rounded-[1.2rem] border border-white/10 bg-[rgba(255,255,255,0.03)] p-4">
                <p className="text-sm text-slate-300">
                  Specialist metadata stays out of the initial dashboard boot path now.
                </p>
                {agentsLoadError ? (
                  <p className="mt-2 text-sm text-amber-300">{agentsLoadError}</p>
                ) : null}
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button onClick={loadAgentProfiles} disabled={agentsLoading}>
                    {agentsLoading ? "Loading specialists..." : "Load Specialist Profiles"}
                  </Button>
                  <Link href="/verse-ai">
                    <Button variant="outline">Open Verse AI</Button>
                  </Link>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )

  return (
    <WorkspaceLayout
      eyebrow="System Dashboard"
      title="Developer control plane"
      description="Monitor generated services, check platform runtime health, and jump directly into builder, runtime, database, and scripting workflows."
      systemTitle="Overview"
      systemDescription="Live summaries for services, database connectivity, and session context."
      editorTitle="Details"
      editorDescription="Operational widgets tuned for day-to-day platform work."
      topActions={
        <>
          <Link href="/service-builder">
            <Button>Create Service</Button>
          </Link>
          <Link href="/services">
            <Button variant="outline">Open Runtime</Button>
          </Link>
        </>
      }
      systemPanel={systemPanel}
      editorPanel={editorPanel}
    />
  )
}

function DashboardMetric({ label, value, note }) {
  return (
    <div className="rounded-[1.1rem] border border-white/10 bg-[rgba(255,255,255,0.03)] p-4">
      <p className="app-stat-label">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-white">{value}</p>
      <p className="mt-1 text-sm text-slate-400">{note}</p>
    </div>
  )
}
