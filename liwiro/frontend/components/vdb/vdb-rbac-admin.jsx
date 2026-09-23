// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import PasswordInput from "@/components/ui/password-input"
import { authHeaders } from "@/lib/auth"
import { vdbCommandText } from "@/lib/vdb-commands"
import { toast } from "sonner"

function asArray(value) {
  return Array.isArray(value) ? value : []
}

function uniqueUpper(items) {
  return [...new Set(asArray(items).map((item) => String(item || "").trim().toUpperCase()).filter(Boolean))]
}

function parsePermissionsCsv(value) {
  return uniqueUpper(String(value || "").split(","))
}

function prettyJson(value) {
  return JSON.stringify(value || {}, null, 2)
}

export default function VdbRbacAdmin({ backend, portalToken = "", title = "VDB RBAC Admin" }) {
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [overview, setOverview] = useState({ users: [], roles: {}, permissions: [], domains: [], user_permissions: [] })
  const [selectedUser, setSelectedUser] = useState("")
  const [newUser, setNewUser] = useState({
    username: "",
    email: "",
    password: "",
    role: "APPLICATION",
  })
  const [roleForm, setRoleForm] = useState({
    name: "",
    permissions: "",
    scopeDomain: "",
    scopeDb: "",
  })
  const [accessForm, setAccessForm] = useState({
    username: "",
    role: "",
    domain: "",
    db: "main",
    collection: "",
    permissions: "READ",
  })

  const customRoles = useMemo(() => asArray(overview?.roles?.custom_roles), [overview])
  const systemRoles = useMemo(() => asArray(overview?.roles?.system_roles), [overview])
  const roleNames = useMemo(
    () => [...new Set([...systemRoles, ...customRoles].map((role) => String(role?.name || "").trim()).filter(Boolean))],
    [customRoles, systemRoles]
  )
  const selectedUserRecord = useMemo(
    () => asArray(overview.user_permissions).find((row) => row.username === selectedUser) || null,
    [overview.user_permissions, selectedUser]
  )
  const knownPermissions = useMemo(() => uniqueUpper(overview.permissions), [overview.permissions])
  const domainNames = useMemo(
    () => [...new Set(asArray(overview.domains).map((row) => String(row?.domain || "").trim()).filter(Boolean))],
    [overview.domains]
  )
  const editingCustomRole = useMemo(
    () => customRoles.find((role) => String(role?.name || "").trim() === String(roleForm.name || "").trim()) || null,
    [customRoles, roleForm.name]
  )
  const editingSystemRole = useMemo(
    () => systemRoles.find((role) => String(role?.name || "").trim() === String(roleForm.name || "").trim()) || null,
    [systemRoles, roleForm.name]
  )

  const requestHeaders = useCallback(() => {
    const headers = { ...authHeaders() }
    if (portalToken) headers["X-VDB-Portal-Token"] = portalToken
    return headers
  }, [portalToken])

  const loadOverview = useCallback(async ({ silent = false } = {}) => {
    setLoading(true)
    try {
      const res = await fetch(`${backend}/platform/vdb/rbac/overview`, {
        headers: requestHeaders(),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || "Failed to load VDB RBAC overview")
      setOverview({
        users: asArray(data?.users),
        roles: data?.roles && typeof data.roles === "object" ? data.roles : {},
        permissions: asArray(data?.permissions),
        domains: asArray(data?.domains),
        user_permissions: asArray(data?.user_permissions),
      })
      const users = asArray(data?.users).map((item) => String(item || "").trim()).filter(Boolean)
      setSelectedUser((prev) => (prev && users.includes(prev) ? prev : (users[0] || "")))
      setAccessForm((prev) => ({
        ...prev,
        username: prev.username || users[0] || "",
        domain: prev.domain || (asArray(data?.domains).map((item) => String(item?.domain || "").trim()).find(Boolean) || ""),
      }))
      if (!silent) toast.success("VDB RBAC refreshed")
    } catch (error) {
      if (!silent) toast.error(error?.message || "Failed to load VDB RBAC overview")
    } finally {
      setLoading(false)
    }
  }, [backend, requestHeaders])

  useEffect(() => {
    loadOverview({ silent: true })
  }, [loadOverview])

  const runCommand = useCallback(async (command, successMessage) => {
    setBusy(true)
    try {
      const res = await fetch(`${backend}/platform/vdb/rbac/command`, {
        method: "POST",
        headers: { "Content-Type": "text/plain; charset=utf-8", ...requestHeaders() },
        body: vdbCommandText(command),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || "VDB RBAC command failed")
      toast.success(successMessage || data?.data?.message || "VDB RBAC command completed")
      await loadOverview({ silent: true })
      return data
    } catch (error) {
      toast.error(error?.message || "VDB RBAC command failed")
      return null
    } finally {
      setBusy(false)
    }
  }, [backend, loadOverview, requestHeaders])

  const createUser = async () => {
    const username = String(newUser.username || "").trim()
    const email = String(newUser.email || "").trim()
    const password = String(newUser.password || "").trim()
    const role = String(newUser.role || "APPLICATION").trim().toUpperCase()
    if (!username || !email || !password) {
      toast.error("Username, email, and password are required")
      return
    }
    const result = await runCommand({ action: "tumi", operation: "create", username, email, password, role }, `Created VDB user ${username}`)
    if (result) {
      setNewUser({ username: "", email: "", password: "", role: "APPLICATION" })
      setSelectedUser(username)
      setAccessForm((prev) => ({ ...prev, username }))
    }
  }

  const loadRoleIntoForm = (name) => {
    const roleName = String(name || "").trim()
    if (!roleName) return
    const role = customRoles.find((item) => String(item?.name || "").trim() === roleName)
      || systemRoles.find((item) => String(item?.name || "").trim() === roleName)
    setRoleForm({
      name: roleName,
      permissions: asArray(role?.permissions).join(", "),
      scopeDomain: String(role?.scope?.domain || ""),
      scopeDb: String(role?.scope?.db || ""),
    })
  }

  const saveRole = async () => {
    const name = String(roleForm.name || "").trim()
    if (!name) {
      toast.error("Role name is required")
      return
    }
    if (editingSystemRole) {
      toast.error("System roles cannot be modified here")
      return
    }
    const permissions = parsePermissionsCsv(roleForm.permissions)
    const rolePayload = { name, permissions }
    if (String(roleForm.scopeDomain || "").trim() || String(roleForm.scopeDb || "").trim()) {
      rolePayload.scope = {}
      if (String(roleForm.scopeDomain || "").trim()) rolePayload.scope.domain = String(roleForm.scopeDomain || "").trim().toLowerCase()
      if (String(roleForm.scopeDb || "").trim()) rolePayload.scope.db = String(roleForm.scopeDb || "").trim().toLowerCase()
    }
    const action = editingCustomRole ? "update" : "create"
    await runCommand(
      action === "create"
        ? { action: "tumi", operation: "create", role: rolePayload }
        : { action: "tumi", operation: "update", role: rolePayload },
      `${action === "create" ? "Created" : "Updated"} role ${name}`
    )
  }

  const deleteRole = async () => {
    const name = String(roleForm.name || "").trim()
    if (!name) {
      toast.error("Choose a custom role to delete")
      return
    }
    if (!editingCustomRole) {
      toast.error("Only custom roles can be deleted")
      return
    }
    const result = await runCommand({ action: "tumi", operation: "delete", role: name }, `Deleted role ${name}`)
    if (result) {
      setRoleForm({ name: "", permissions: "", scopeDomain: "", scopeDb: "" })
    }
  }

  const applyGrantOrRevoke = async (verb) => {
    const username = String(accessForm.username || selectedUser || "").trim()
    if (!username) {
      toast.error("Choose a user first")
      return
    }
    const payload = { username }
    const chosenRole = String(accessForm.role || "").trim()
    if (chosenRole) {
      payload.role = chosenRole
    } else {
      const domain = String(accessForm.domain || "").trim()
      if (!domain) {
        toast.error("Domain is required when granting or revoking permissions")
        return
      }
      payload.domain = domain
      const db = String(accessForm.db || "").trim()
      if (db) payload.db = db
      const collection = String(accessForm.collection || "").trim()
      if (collection) payload.collection = collection
      payload.permissions = parsePermissionsCsv(accessForm.permissions)
    }
    await runCommand({ action: "tumi", operation: verb, ...payload }, `${verb === "grant" ? "Updated" : "Revoked"} access for ${username}`)
  }

  const transferDomain = async () => {
    const username = String(accessForm.username || selectedUser || "").trim()
    const domain = String(accessForm.domain || "").trim()
    if (!username || !domain) {
      toast.error("Username and domain are required for transfer")
      return
    }
    await runCommand({ action: "tumi", operation: "transfer", username, domain }, `Transferred domain ${domain} to ${username}`)
  }

  const deleteUser = async () => {
    const username = String(selectedUser || "").trim()
    if (!username) {
      toast.error("Choose a user first")
      return
    }
    const result = await runCommand({ action: "tumi", operation: "delete", username }, `Deleted VDB user ${username}`)
    if (result) {
      setSelectedUser("")
      setAccessForm((prev) => ({ ...prev, username: "" }))
    }
  }

  return (
    <Card className="rounded-xl border-slate-200 shadow-sm dark:border-slate-700 dark:bg-slate-900">
      <CardHeader className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <CardTitle className="text-xl text-slate-900 dark:text-slate-100">{title}</CardTitle>
        <Button variant="outline" className="h-9" onClick={() => loadOverview()} disabled={busy || loading}>
          {loading ? "Loading..." : "Refresh RBAC"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
            <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">Create VDB User</p>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <div>
                <Label>Username</Label>
                <Input value={newUser.username} onChange={(e) => setNewUser((prev) => ({ ...prev, username: e.target.value }))} placeholder="user" />
              </div>
              <div>
                <Label>Email</Label>
                <Input value={newUser.email} onChange={(e) => setNewUser((prev) => ({ ...prev, email: e.target.value }))} placeholder="user@example.com" />
              </div>
              <div>
                <Label>Password</Label>
                <PasswordInput value={newUser.password} onChange={(e) => setNewUser((prev) => ({ ...prev, password: e.target.value }))} placeholder="Password" />
              </div>
              <div>
                <Label>Role</Label>
                <select className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm dark:border-slate-700 dark:bg-slate-950" value={newUser.role} onChange={(e) => setNewUser((prev) => ({ ...prev, role: e.target.value }))}>
                  <option value="APPLICATION">APPLICATION</option>
                  <option value="ADMIN">ADMIN</option>
                </select>
              </div>
            </div>
            <div className="mt-3 flex gap-2">
              <Button className="brand-solid h-9" onClick={createUser} disabled={busy}>Create User</Button>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
            <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">Create / Update Role</p>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <div>
                <Label>Role Name</Label>
                <Input list="vdb-rbac-roles" value={roleForm.name} onChange={(e) => setRoleForm((prev) => ({ ...prev, name: e.target.value }))} placeholder="DOMAIN_EDITOR" />
              </div>
              <div>
                <Label>Known Roles</Label>
                <select className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm dark:border-slate-700 dark:bg-slate-950" value="" onChange={(e) => loadRoleIntoForm(e.target.value)}>
                  <option value="">Load role...</option>
                  {roleNames.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
              </div>
              <div>
                <Label>Permissions</Label>
                <Input value={roleForm.permissions} onChange={(e) => setRoleForm((prev) => ({ ...prev, permissions: e.target.value }))} placeholder="READ, WRITE, DATA_EXPORT" />
              </div>
              <div>
                <Label>Scope Domain</Label>
                <Input value={roleForm.scopeDomain} onChange={(e) => setRoleForm((prev) => ({ ...prev, scopeDomain: e.target.value }))} placeholder="Optional domain" />
              </div>
              <div>
                <Label>Scope DB</Label>
                <Input value={roleForm.scopeDb} onChange={(e) => setRoleForm((prev) => ({ ...prev, scopeDb: e.target.value }))} placeholder="Optional db" />
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button className="brand-solid h-9" onClick={saveRole} disabled={busy || Boolean(editingSystemRole)}>
                {editingCustomRole ? "Update Role" : "Create Role"}
              </Button>
              <Button variant="outline" className="h-9 border-destructive/40 text-destructive hover:bg-destructive/10 dark:border-destructive/40 dark:text-destructive dark:hover:bg-destructive/20" onClick={deleteRole} disabled={busy || !editingCustomRole}>
                Delete Role
              </Button>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
          <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">Grant / Revoke / Transfer</p>
          <div className="mt-3 grid gap-3 lg:grid-cols-3">
            <div>
              <Label>User</Label>
              <Input list="vdb-rbac-users" value={accessForm.username} onChange={(e) => setAccessForm((prev) => ({ ...prev, username: e.target.value }))} placeholder="alice" />
            </div>
            <div>
              <Label>Role Grant / Revoke</Label>
              <Input list="vdb-rbac-roles" value={accessForm.role} onChange={(e) => setAccessForm((prev) => ({ ...prev, role: e.target.value }))} placeholder="Optional role name" />
            </div>
            <div>
              <Label>Domain</Label>
              <Input list="vdb-rbac-domains" value={accessForm.domain} onChange={(e) => setAccessForm((prev) => ({ ...prev, domain: e.target.value }))} placeholder="default" />
            </div>
            <div>
              <Label>DB</Label>
              <Input value={accessForm.db} onChange={(e) => setAccessForm((prev) => ({ ...prev, db: e.target.value }))} placeholder="main" />
            </div>
            <div>
              <Label>Collection</Label>
              <Input value={accessForm.collection} onChange={(e) => setAccessForm((prev) => ({ ...prev, collection: e.target.value }))} placeholder="Optional collection" />
            </div>
            <div>
              <Label>Permissions</Label>
              <Input value={accessForm.permissions} onChange={(e) => setAccessForm((prev) => ({ ...prev, permissions: e.target.value }))} placeholder="READ, WRITE" />
            </div>
          </div>
          {knownPermissions.length ? (
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-300">Known permissions: {knownPermissions.join(", ")}</p>
          ) : null}
          <div className="mt-3 flex flex-wrap gap-2">
            <Button className="brand-solid h-9" onClick={() => applyGrantOrRevoke("grant")} disabled={busy}>Grant</Button>
            <Button variant="outline" className="h-9" onClick={() => applyGrantOrRevoke("revoke")} disabled={busy}>Revoke</Button>
            <Button variant="outline" className="h-9" onClick={transferDomain} disabled={busy}>Transfer Domain</Button>
            <Button variant="outline" className="h-9 border-destructive/40 text-destructive hover:bg-destructive/10 dark:border-destructive/40 dark:text-destructive dark:hover:bg-destructive/20" onClick={deleteUser} disabled={busy || !selectedUser}>
              Delete Selected User
            </Button>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
            <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">All User Permissions</p>
            <div className="mt-3 space-y-3">
              {asArray(overview.user_permissions).length === 0 ? (
                <p className="text-sm text-slate-500 dark:text-slate-300">No VDB user permission data available.</p>
              ) : asArray(overview.user_permissions).map((row) => (
                <button
                  key={row.username}
                  type="button"
                  onClick={() => {
                    setSelectedUser(row.username)
                    setAccessForm((prev) => ({ ...prev, username: row.username }))
                  }}
                  className={`w-full rounded-lg border p-3 text-left transition ${
                    selectedUser === row.username
                      ? "border-green-300 bg-green-50 text-green-900 dark:border-green-700 dark:bg-green-900/20 dark:text-green-200"
                      : "border-slate-200 bg-white hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:hover:bg-slate-800"
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-semibold">{row.username}</p>
                    <p className="text-xs text-slate-500 dark:text-slate-300">{asArray(row.owned_domains).join(", ") || "no owned domains"}</p>
                  </div>
                  <pre className="mt-2 overflow-auto whitespace-pre-wrap break-words rounded-md bg-slate-950/95 p-3 text-xs text-slate-100">{prettyJson({
                    db_permissions: row.db_permissions,
                    collection_permissions: row.collection_permissions,
                  })}</pre>
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
            <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">Selected User</p>
            {selectedUserRecord ? (
              <div className="mt-3 space-y-3">
                <p className="text-sm font-medium text-slate-800 dark:text-slate-200">{selectedUserRecord.username}</p>
                <p className="text-xs text-slate-500 dark:text-slate-300">Owned domains: {asArray(selectedUserRecord.owned_domains).join(", ") || "none"}</p>
                <pre className="overflow-auto whitespace-pre-wrap break-words rounded-md bg-slate-950/95 p-3 text-xs text-slate-100">{prettyJson(selectedUserRecord)}</pre>
              </div>
            ) : (
              <p className="mt-3 text-sm text-slate-500 dark:text-slate-300">Choose a user to inspect a single permission view.</p>
            )}
            <div className="mt-6">
              <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">Domains</p>
              <pre className="mt-3 overflow-auto whitespace-pre-wrap break-words rounded-md bg-slate-950/95 p-3 text-xs text-slate-100">{prettyJson(overview.domains)}</pre>
            </div>
          </div>
        </div>

        <datalist id="vdb-rbac-users">{asArray(overview.users).map((user) => <option key={user} value={user} />)}</datalist>
        <datalist id="vdb-rbac-roles">{roleNames.map((role) => <option key={role} value={role} />)}</datalist>
        <datalist id="vdb-rbac-domains">{domainNames.map((domain) => <option key={domain} value={domain} />)}</datalist>
      </CardContent>
    </Card>
  )
}
