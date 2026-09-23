"use client"

import Image from "next/image"
import Link from "next/link"
import { Loader2, ServerCog, ShieldCheck, SquareTerminal } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { usePathname, useRouter } from "next/navigation"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import PasswordInput from "@/components/ui/password-input"
import { VdbTransportStatusIndicator } from "@/components/vdb/vdb-transport-status-indicator"
import { markAuthVerified, setAuthRuntimeState, setAuthToken } from "@/lib/auth"
import { useVdbConnectionStatus } from "@/lib/vdb-connection-status"
import { normalizeVdbNamedPipePath, normalizeVdbTransportMode, vdbTransportOptions, vdbTransportTargetConfig } from "@/lib/vdb-transport"

export function AuthConsole() {
  const pathname = usePathname()
  const router = useRouter()
  const backend = process.env.NEXT_PUBLIC_LIWIRO_BACKEND || "http://127.0.0.1:5000"

  const [backendReachable, setBackendReachable] = useState(true)
  const [vdbUsersExist, setVdbUsersExist] = useState(false)
  const [vdbUsernames, setVdbUsernames] = useState([])
  const [hasFrontendCreds, setHasFrontendCreds] = useState(false)
  const [workspaceConfigured, setWorkspaceConfigured] = useState(false)
  const [statusResolved, setStatusResolved] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [forceSetupMode, setForceSetupMode] = useState(false)
  const [vdbDefaults, setVdbDefaults] = useState({
    supportsNamedPipe: false,
    defaultVdbTransport: "unixsocket",
    defaultVdbServerUrl: "http://127.0.0.1:1957",
    defaultVdbUnixSocketPath: "/tmp/vdb.sock",
    defaultVdbNamedPipePath: normalizeVdbNamedPipePath("\\\\.\\pipe\\verun_vdb"),
  })

  const [form, setForm] = useState({
    username: "",
    password: "",
    vdb_transport: "unixsocket",
    vdb_server_url: "http://127.0.0.1:1957",
    vdb_unix_socket_path: "/tmp/vdb.sock",
    vdb_named_pipe_path: normalizeVdbNamedPipePath("\\\\.\\pipe\\verun_vdb"),
    vdb_app_username: "Liwiro",
    vdb_app_password: "",
  })

  useEffect(() => {
    const loadStatus = async () => {
      try {
        const response = await fetch(`${backend}/auth/status`)
        if (!response.ok) throw new Error("Backend status failed")

        const data = await response.json()
        setBackendReachable(true)
        setWorkspaceConfigured(Boolean(data.configured))
        setHasFrontendCreds(Boolean(data.hasFrontendCreds))
        setVdbUsersExist(Boolean(data.vdbUsersExist))
        setVdbUsernames(Array.isArray(data.vdbUsernames) ? data.vdbUsernames : [])
        const supportsNamedPipe = Boolean(data.supportsNamedPipe)
        const defaultVdbTransport = normalizeVdbTransportMode(
          data.vdbTransport || data.defaultVdbTransport || "unixsocket",
          supportsNamedPipe,
        )
        const nextDefaults = {
          supportsNamedPipe,
          defaultVdbTransport,
          defaultVdbServerUrl: String(data.defaultVdbServerUrl || "http://127.0.0.1:1957"),
          defaultVdbUnixSocketPath: String(data.defaultVdbUnixSocketPath || "/tmp/vdb.sock"),
          defaultVdbNamedPipePath: normalizeVdbNamedPipePath(data.defaultVdbNamedPipePath || "\\\\.\\pipe\\verun_vdb"),
        }
        setVdbDefaults(nextDefaults)
        setForm((prev) => ({
          ...prev,
          vdb_transport: defaultVdbTransport,
          vdb_server_url: String(data.vdbServerUrl || nextDefaults.defaultVdbServerUrl || prev.vdb_server_url),
          vdb_unix_socket_path: String(data.vdbUnixSocketPath || nextDefaults.defaultVdbUnixSocketPath || prev.vdb_unix_socket_path),
          vdb_named_pipe_path: normalizeVdbNamedPipePath(
            data.vdbNamedPipePath || nextDefaults.defaultVdbNamedPipePath || prev.vdb_named_pipe_path
          ),
        }))
      } catch {
        setBackendReachable(false)
        setWorkspaceConfigured(false)
        setHasFrontendCreds(false)
        setVdbUsersExist(false)
        setVdbUsernames([])
        setError(`Cannot reach backend at ${backend}. Run liwiro/scripts/start_all.sh and refresh.`)
      } finally {
        setStatusResolved(true)
      }
    }

    loadStatus()
  }, [backend])

  const accessModePending = !statusResolved && backendReachable
  const setupMode = statusResolved ? forceSetupMode || !workspaceConfigured : false
  // Runtime repair belongs in Settings. Keep VDB fields on the first-run
  // setup form only; never turn the login screen into a second repair flow.
  const showVdbConfig = setupMode
  const vdbTargetField = vdbTransportTargetConfig({
    transport: form.vdb_transport,
    serverUrl: form.vdb_server_url,
    socketPath: form.vdb_unix_socket_path,
    namedPipePath: form.vdb_named_pipe_path,
    defaultServerUrl: vdbDefaults.defaultVdbServerUrl,
    defaultSocketPath: vdbDefaults.defaultVdbUnixSocketPath,
    defaultNamedPipePath: vdbDefaults.defaultVdbNamedPipePath,
    supportsNamedPipe: vdbDefaults.supportsNamedPipe,
  })
  const selectedVdbStatus = useVdbConnectionStatus({
    backend,
    transport: form.vdb_transport,
    serverUrl: form.vdb_transport === "unixsocket" ? "" : form.vdb_server_url,
    socketPath: form.vdb_transport === "unixsocket" ? form.vdb_unix_socket_path : "",
    namedPipePath: form.vdb_transport === "namedpipe" ? form.vdb_named_pipe_path : "",
    supportsNamedPipe: vdbDefaults.supportsNamedPipe,
    enabled: backendReachable && statusResolved && showVdbConfig,
    attemptAutostart: form.vdb_transport === "http",
  })

  useEffect(() => {
    if (!statusResolved || !backendReachable) return

    const targetPath = setupMode ? "/setup" : "/login"
    if (pathname !== targetPath) {
      router.replace(targetPath)
    }
  }, [backendReachable, pathname, router, setupMode, statusResolved])

  const statusCards = useMemo(() => [
    {
      label: "Backend",
      value: statusResolved ? (backendReachable ? "Reachable" : "Unavailable") : "Checking",
      note: backend,
      icon: ServerCog,
    },
    {
      label: "Workspace Auth",
      value: statusResolved ? (workspaceConfigured ? "Configured" : "Pending") : "Checking",
      note: accessModePending
        ? "Resolving access flow"
        : (setupMode ? "Bootstrap in progress" : "Ready for sign in"),
      icon: ShieldCheck,
    },
    {
      label: "VDB Users",
      value: statusResolved ? (vdbUsersExist ? "Detected" : "Missing") : "Checking",
      note: statusResolved
        ? (vdbUsernames.length > 0 ? vdbUsernames.join(", ") : "No usernames reported")
        : "Inspecting runtime state",
      icon: SquareTerminal,
    },
  ], [accessModePending, backend, backendReachable, setupMode, statusResolved, vdbUsernames, vdbUsersExist, workspaceConfigured])

  const onChange = (field, value) => {
    setForm((prev) => ({
      ...prev,
      [field]: field === "vdb_named_pipe_path" ? normalizeVdbNamedPipePath(value) : value,
    }))
  }

  const onSubmit = async (event) => {
    event.preventDefault()
    setLoading(true)
    setError("")
    setNotice("")

    try {
      if (!backendReachable) {
        throw new Error(`Backend is unreachable at ${backend}. Start it first.`)
      }

      const payload = {
        username: form.username,
        password: form.password,
      }

      if (setupMode) {
        payload.liwiro_super_admin_username = form.username
        payload.liwiro_super_admin_password = form.password
        payload.vdb_transport = form.vdb_transport
        payload.vdb_server_url = form.vdb_server_url
        payload.vdb_unix_socket_path = form.vdb_unix_socket_path
        payload.vdb_named_pipe_path = form.vdb_named_pipe_path
        payload.vdb_app_username = form.vdb_app_username
        payload.vdb_app_password = form.vdb_app_password
      }

      const response = await fetch(`${backend}/auth/signin`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || "Sign in failed")

      setAuthToken(data.token)
      markAuthVerified(data.token)
      setAuthRuntimeState({
        vdbRuntimeReady: data.vdbRuntimeReady !== false,
        vdbRuntimeError: data.vdbRuntimeError || "",
      })
      setNotice(
        data.vdbRuntimeReady === false
          ? "Signed in with degraded runtime access. Open Settings → Repair VDB runtime connection to enter the VDB username and password."
          : ""
      )
      router.replace(data.vdbRuntimeReady === false ? "/settings" : "/")
    } catch (err) {
      const message = err?.message || "Sign in failed"
      if (message.includes("Failed to fetch")) {
        setError(`Failed to connect to backend (${backend}). Check backend server and CORS config.`)
      } else {
        if (message.includes("Liwiro application user") || message.includes("No VDB super admin was detected in VDB")) {
          setForceSetupMode(true)
        }
        setError(message)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-console-shell">
      <div className="auth-console-grid">
        <section className="auth-console-panel px-6 py-7 md:px-8 md:py-8">
          <div className="mb-6 inline-flex items-center gap-4 rounded-[1.5rem] border border-sky-400/20 bg-sky-400/[0.08] px-4 py-4 shadow-[0_18px_36px_rgba(14,165,233,0.12)]">
            <span className="inline-flex h-16 w-16 items-center justify-center overflow-hidden rounded-[1.35rem]">
              <Image
                src="/liwiro-rabbit-blue.svg"
                alt="Kalulu, the Liwiro rabbit logo"
                width={44}
                height={44}
                className="h-11 w-11 object-contain"
              />
            </span>
            <div className="min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-sky-300/80">Kalulu</p>
              <p className="mt-1 text-lg font-semibold text-white">Liwiro Access Console</p>
              <p className="mt-1 text-sm text-slate-400">The console selects setup or sign-in automatically from the current workspace state.</p>
            </div>
          </div>
          <p className="workspace-eyebrow">{accessModePending ? "Access Check" : (setupMode ? "First-Time Setup" : "Workspace Access")}</p>
          <h1 className="workspace-title">{accessModePending ? "Checking workspace access" : (setupMode ? "Bootstrap the Liwiro control plane" : "Sign in to Liwiro")}</h1>
          <p className="workspace-copy">
            {accessModePending
              ? "Liwiro is checking whether this workspace already has operator credentials so it can open the correct access flow."
              : (setupMode
                  ? "Create the initial admin account, connect Liwiro to VDB, and initialize the runtime foundations in one guided flow."
                  : "Authenticate into the developer control panel and continue managing services, databases, and runtime modules.")}
          </p>

          <div className="mt-6 grid gap-3">
            {statusCards.map((card) => {
              const Icon = card.icon
              return (
                <div key={card.label} className="auth-step-card">
                  <div className="flex items-center gap-3">
                    <span className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-sky-400/10 text-sky-200">
                      <Icon className="h-4 w-4" />
                    </span>
                    <div className="min-w-0">
                      <p className="app-stat-label">{card.label}</p>
                      <p className="mt-1 truncate text-lg font-semibold text-white">{card.value}</p>
                      <p className="truncate text-sm text-slate-400">{card.note}</p>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          <div className="mt-6 space-y-3">
            <div className="auth-step-card">
              <p className="app-stat-label">Flow</p>
              <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-slate-300">
                {accessModePending ? (
                  <li>Resolve whether Liwiro should open setup or sign-in.</li>
                ) : setupMode ? (
                  <>
                    <li>Create the Liwiro admin identity.</li>
                    <li>Configure the VDB connection used by runtime services.</li>
                    <li>Sign in and continue to service initialization.</li>
                  </>
                ) : (
                  <>
                    <li>Validate your Liwiro operator credentials.</li>
                    <li>Reuse the saved runtime connection when it is healthy.</li>
                    <li>Enter the workspace and continue managing services.</li>
                  </>
                )}
              </ol>
            </div>

            <div className="flex flex-wrap gap-2">
              {setupMode ? (
                <>
                  <Link href="/wiki/getting-started">
                    <Button variant="outline">Getting Started</Button>
                  </Link>
                  <Link href="/wiki/platform-setup">
                    <Button variant="outline">Setup Guide</Button>
                  </Link>
                </>
              ) : (
                <Link href="/wiki">
                  <Button variant="outline">Open Manual</Button>
                </Link>
              )}
              <Link href="/license">
                <Button variant="outline">View License</Button>
              </Link>
            </div>
          </div>
        </section>

        <section className="auth-console-panel px-6 py-7 md:px-8 md:py-8">
          <div className="border-b border-white/10 pb-5">
            <p className="app-section-label">{accessModePending ? "Access Console" : (setupMode ? "Setup Console" : "Login Console")}</p>
            <h2 className="mt-2 text-2xl font-semibold text-white">
              {accessModePending ? "Resolving workspace mode" : (setupMode ? "Admin + runtime bootstrap" : "Operator authentication")}
            </h2>
            <p className="mt-2 text-sm leading-7 text-slate-400">
              {accessModePending
                ? "Checking for existing Liwiro operator credentials before showing the correct form."
                : (setupMode
                    ? "Use the generated admin credentials as the platform super admin. Liwiro will also initialize the VDB runtime connection from this form."
                    : "Use your Liwiro credentials. If runtime VDB authentication needs repair, enter the VDB credentials in Settings after signing in.")}
            </p>
          </div>

          {accessModePending ? (
            <div className="flex min-h-[20rem] items-center justify-center pt-6">
              <div className="text-center">
                <Loader2 className="mx-auto h-8 w-8 animate-spin text-sky-200" />
                <p className="mt-4 text-sm font-medium text-white">Checking workspace access</p>
                <p className="mt-1 text-sm text-slate-400">Loading stored credential state from the backend.</p>
              </div>
            </div>
          ) : (
            <form className="space-y-6 pt-6" onSubmit={onSubmit}>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="username">{setupMode ? "Admin Username" : "Username"}</Label>
                  <Input
                    id="username"
                    value={form.username}
                    onChange={(event) => onChange("username", event.target.value)}
                    autoComplete="username"
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password">{setupMode ? "Admin Password" : "Password"}</Label>
                  <PasswordInput
                    id="password"
                    value={form.password}
                    onChange={(event) => onChange("password", event.target.value)}
                    autoComplete={setupMode ? "new-password" : "current-password"}
                    required
                  />
                </div>
              </div>

              {showVdbConfig && (
                <div className="space-y-4 rounded-[1.35rem] border border-white/10 bg-white/5 p-4">
                  <div>
                    <p className="text-sm font-semibold text-white">
                      Initial VDB Runtime Configuration
                    </p>
                    <p className="mt-1 text-sm text-slate-400">
                      These credentials allow Liwiro to initialize its application user and runtime database context.
                    </p>
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <div className="flex items-center justify-between gap-3">
                        <Label htmlFor="vdb_transport">VDB Transport</Label>
                        <VdbTransportStatusIndicator status={selectedVdbStatus} />
                      </div>
                      <select
                        id="vdb_transport"
                        className="flex h-12 w-full rounded-xl border border-white/10 bg-[rgba(8,18,31,0.86)] px-4 py-3 text-sm text-slate-100"
                        value={form.vdb_transport}
                        onChange={(event) => onChange("vdb_transport", event.target.value)}
                      >
                        {vdbTransportOptions({ supportsNamedPipe: vdbDefaults.supportsNamedPipe }).map((option) => (
                          <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor={vdbTargetField.key}>{vdbTargetField.label}</Label>
                      <Input
                        id={vdbTargetField.key}
                        value={vdbTargetField.value}
                        onChange={(event) => onChange(vdbTargetField.key, event.target.value)}
                        placeholder={vdbTargetField.placeholder}
                        required={setupMode}
                      />
                    </div>
                  </div>

                  {selectedVdbStatus?.status === "starting" ? (
                    <p className="inline-flex items-center gap-2 text-sm text-slate-300">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span>{form.vdb_transport === "http" ? "Starting HTTP server..." : form.vdb_transport === "namedpipe" ? "Checking named-pipe interface..." : "Checking Unix-socket interface..."}</span>
                    </p>
                  ) : null}

                  {selectedVdbStatus?.detail && selectedVdbStatus?.status !== "starting" ? (
                    <div
                      className={`rounded-[1rem] border px-3 py-2 text-sm ${
                        selectedVdbStatus?.status === "available"
                          ? "border-emerald-400/20 bg-emerald-400/[0.08] text-emerald-100"
                          : selectedVdbStatus?.status === "paused"
                            ? "border-amber-400/20 bg-amber-400/[0.08] text-amber-100"
                          : selectedVdbStatus?.status === "unsupported"
                            ? "border-amber-400/20 bg-amber-400/[0.08] text-amber-100"
                            : "border-white/10 bg-white/[0.04] text-slate-300"
                      }`}
                    >
                      {selectedVdbStatus.detail}
                    </div>
                  ) : null}

                  {selectedVdbStatus?.paused && typeof selectedVdbStatus?.retry === "function" ? (
                    <Button type="button" variant="outline" className="h-10 rounded-xl border-white/10 bg-white/[0.04]" onClick={selectedVdbStatus.retry}>
                      Retry transport check
                    </Button>
                  ) : null}

                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="vdb_app_username">VDB App/Admin Username</Label>
                      <Input
                        id="vdb_app_username"
                        value={form.vdb_app_username}
                        onChange={(event) => onChange("vdb_app_username", event.target.value)}
                        required={setupMode}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="vdb_app_password">VDB App/Admin Password</Label>
                      <PasswordInput
                        id="vdb_app_password"
                        value={form.vdb_app_password}
                        onChange={(event) => onChange("vdb_app_password", event.target.value)}
                        autoComplete="current-password"
                        required={setupMode}
                      />
                    </div>
                  </div>
                </div>
              )}

              {error ? (
                <div className="rounded-[1.15rem] border border-amber-400/20 bg-amber-400/[0.08] px-4 py-3 text-sm text-amber-100">
                  {error}
                </div>
              ) : null}

              {notice ? (
                <div className="rounded-[1.15rem] border border-sky-400/20 bg-sky-400/[0.08] px-4 py-3 text-sm text-sky-100">
                  {notice}
                </div>
              ) : null}

              <div className="flex flex-wrap gap-3 pt-2">
                <Button type="submit" className="min-w-[14rem]" disabled={loading}>
                  {loading ? (
                    <span className="inline-flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span>{setupMode ? "Bootstrapping..." : "Signing in..."}</span>
                    </span>
                  ) : (
                    <span>{setupMode ? "Create Admin and Sign In" : "Sign In"}</span>
                  )}
                </Button>
              </div>
            </form>
          )}
        </section>
      </div>
    </div>
  )
}
