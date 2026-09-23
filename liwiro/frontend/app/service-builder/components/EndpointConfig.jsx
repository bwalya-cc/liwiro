// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { JsonTextarea } from "@/components/ui/json-textarea";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { parseJsonLikeObject } from "@/lib/json-editor";
import { buildMediaStorageScriptTemplate, MEDIA_STORAGE_SCRIPT_PRESETS } from "@/lib/media-storage-presets";
import { useEffect, useState } from "react";

const CRUD_METHODS = { create: "POST", read: "GET", update: "PUT", delete: "DELETE" };
const DEFAULT_BEARER_TOKEN = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.demo.signature";

function getPrimaryModel(models, endpoint) {
  const entries = Object.values(models || {});
  const linkedModel = String(endpoint?.linkedModel || "").trim();
  if (linkedModel) {
    const match = entries.find((model) => String(model?.name || "").trim() === linkedModel);
    if (match) return match;
  }
  return entries[0] || null;
}

function buildCustomVqlStarter(models, endpoint) {
  const model = getPrimaryModel(models, endpoint);
  const collectionName = String(model?.collection || model?.name || "collection_name").trim() || "collection_name";
  return `read collection ${JSON.stringify(collectionName)} limit 25`;
}

function buildScriptStarter(endpoint) {
  const routePath = String(endpoint?.path || "/").trim() || "/";
  return [
    "let p = params;",
    "{",
    "  ok: true,",
    `  route: "${routePath}",`,
    "  query: p.query ?? {},",
    "  body: p.body ?? {}",
    "}",
  ].join("\n");
}

function normalizeExampleParams(endpoint, requiresAuth = Boolean(endpoint?.requiresAuth)) {
  const exampleParams = endpoint?.exampleParams && typeof endpoint.exampleParams === "object" && !Array.isArray(endpoint.exampleParams)
    ? { ...endpoint.exampleParams }
    : {};
  const headers = exampleParams.headers && typeof exampleParams.headers === "object" && !Array.isArray(exampleParams.headers)
    ? { ...exampleParams.headers }
    : {};
  delete headers.authorization;
  if (requiresAuth) {
    if (!String(headers.Authorization || "").trim()) {
      headers.Authorization = DEFAULT_BEARER_TOKEN;
    }
  } else {
    delete headers.Authorization;
  }
  return {
    ...exampleParams,
    headers,
  };
}

export default function EndpointConfig({
  config,
  addEndpoint,
  removeEndpoint,
  updateConfig,
  models,
  availableModules = [],
  attachedModules = [],
  versaEndpointErrors = {},
}) {
  const [vqlErrors, setVqlErrors] = useState({});
  const [exampleErrors, setExampleErrors] = useState({});
  const [exampleDrafts, setExampleDrafts] = useState({});
  const [moduleHelpOpen, setModuleHelpOpen] = useState({});

  useEffect(() => {
    const next = {};
    Object.entries(config.endpoints || {}).forEach(([endpointId, endpoint]) => {
      next[endpointId] = JSON.stringify(endpoint.exampleParams || {}, null, 2);
    });
    setExampleDrafts(next);
  }, [config.endpoints]);

  const handleVqlChange = (endpointId, value) => {
    try {
      const command = String(value || "").trim()
      if (command.startsWith("{") || command.startsWith("[")) throw new Error("Use readable VDB syntax, such as read collection orders")
      setVqlErrors((prev) => ({ ...prev, [endpointId]: null }));
    } catch (error) {
      setVqlErrors((prev) => ({ ...prev, [endpointId]: error?.message || "Invalid readable command" }));
    }
    updateConfig("endpoints", endpointId, "vqlQuery", value);
  };

  const handleCrudOperationChange = (endpointId, value) => {
    updateConfig("endpoints", endpointId, "crudOperation", value);
    updateConfig("endpoints", endpointId, "method", CRUD_METHODS[value] || "GET");
  };

  const handleExampleParamsChange = (endpointId, value) => {
    setExampleDrafts((prev) => ({ ...prev, [endpointId]: value }))
    try {
      const parsed = value.trim() ? parseJsonLikeObject(value, "Example params") : {}
      setExampleErrors((prev) => ({ ...prev, [endpointId]: null }))
      updateConfig("endpoints", endpointId, "exampleParams", parsed && typeof parsed === "object" ? parsed : {})
    } catch (error) {
      setExampleErrors((prev) => ({ ...prev, [endpointId]: error?.message || "Invalid JSON object" }))
    }
  }

  const handleRequiresAuthChange = (endpointId, checked) => {
    const endpoint = config.endpoints?.[endpointId] || {};
    updateConfig("endpoints", endpointId, "requiresAuth", checked);
    updateConfig("endpoints", endpointId, "exampleParams", normalizeExampleParams(endpoint, checked));
  };

  const handleOperationTypeChange = (endpointId, value) => {
    const endpoint = config.endpoints?.[endpointId] || {};
    updateConfig("endpoints", endpointId, "operationType", value);
    updateConfig("endpoints", endpointId, "exampleParams", normalizeExampleParams(endpoint, Boolean(endpoint?.requiresAuth)));

    if (value === "crud") {
      const nextCrudOperation = String(endpoint?.crudOperation || "read").trim().toLowerCase() || "read";
      updateConfig("endpoints", endpointId, "crudOperation", nextCrudOperation);
      updateConfig("endpoints", endpointId, "method", CRUD_METHODS[nextCrudOperation] || "GET");
      if (!String(endpoint?.linkedModel || "").trim()) {
        const fallbackModel = getPrimaryModel(models, endpoint);
        const fallbackName = String(fallbackModel?.name || "").trim();
        if (fallbackName) {
          updateConfig("endpoints", endpointId, "linkedModel", fallbackName);
        }
      }
    }

    if (value === "custom" && !String(endpoint?.vqlQuery || "").trim()) {
      updateConfig("endpoints", endpointId, "vqlQuery", buildCustomVqlStarter(models, endpoint));
    }

    if (value === "script" && !String(endpoint?.versaScript || "").trim()) {
      updateConfig("endpoints", endpointId, "versaScript", buildScriptStarter(endpoint));
    }
  };

  const handleLinkedModelChange = (endpointId, value) => {
    const endpoint = config.endpoints?.[endpointId] || {};
    updateConfig("endpoints", endpointId, "linkedModel", value);
    if (String(endpoint?.operationType || "").trim().toLowerCase() === "custom" && !String(endpoint?.vqlQuery || "").trim()) {
      updateConfig(
        "endpoints",
        endpointId,
        "vqlQuery",
        buildCustomVqlStarter(models, { ...endpoint, linkedModel: value }),
      );
    }
  };

  const applyScriptPreset = (endpointId, presetId) => {
    const endpoint = config.endpoints?.[endpointId] || {};
    updateConfig(
      "endpoints",
      endpointId,
      "versaScript",
      buildMediaStorageScriptTemplate(presetId, endpoint?.path || "/upload"),
    );
  };

  return (
    <div className="app-card p-6">
      <div className="mb-5 flex items-center justify-between">
        <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Endpoints</h2>
        <Button onClick={addEndpoint} size="sm" className="brand-solid h-9">
          <Plus className="h-4 w-4 mr-1" /> Add Endpoint
        </Button>
      </div>

      {Object.keys(config.endpoints).length === 0 ? (
        <div className="rounded-lg border border-dashed py-8 text-center dark:border-slate-700">
          <p className="text-slate-500 dark:text-slate-300">No endpoints defined</p>
        </div>
      ) : (
        <div className="space-y-6">
          {Object.entries(config.endpoints).map(([endpointId, endpoint]) => {
            const versaEndpointError = String(versaEndpointErrors?.[endpointId] || "").trim();
            return (
              <div
                key={endpointId}
                className={`mb-4 rounded-lg border p-4 ${versaEndpointError ? "border-red-400 bg-red-50/40 dark:border-red-500/60 dark:bg-red-950/20" : "border-slate-200 dark:border-slate-700"}`}
              >
                <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                  <h3 className="font-medium text-slate-900 dark:text-slate-100">Endpoint Configuration</h3>
                  <div className="flex items-center gap-4">
                    <div className="flex items-center">
                      <Label className="mr-2">Enabled</Label>
                      <Switch
                        checked={endpoint.enabled !== false}
                        onCheckedChange={(checked) => updateConfig("endpoints", endpointId, "enabled", checked)}
                      />
                    </div>
                    <div className="flex items-center">
                      <Label className="mr-2">Require Auth</Label>
                      <Switch
                        checked={endpoint.requiresAuth || false}
                        onCheckedChange={(checked) => handleRequiresAuthChange(endpointId, checked)}
                      />
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => removeEndpoint(endpointId)}
                      className="h-8 text-destructive hover:text-destructive/80"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                <div className="mb-4 grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label>HTTP Method</Label>
                    <Select
                      value={endpoint.method}
                      onValueChange={(value) => updateConfig("endpoints", endpointId, "method", value)}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Method" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="GET">GET</SelectItem>
                        <SelectItem value="POST">POST</SelectItem>
                        <SelectItem value="PUT">PUT</SelectItem>
                        <SelectItem value="DELETE">DELETE</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Path</Label>
                    <Input
                      value={endpoint.path || ""}
                      onChange={(e) => updateConfig("endpoints", endpointId, "path", e.target.value)}
                    />
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label>Operation Type</Label>
                    <Select
                      value={endpoint.operationType}
                      onValueChange={(value) => handleOperationTypeChange(endpointId, value)}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Operation Type" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="crud">CRUD Operation</SelectItem>
                        <SelectItem value="custom">Custom VQL</SelectItem>
                        <SelectItem value="script">Versa (.versa)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Developer Notes</Label>
                    <Textarea
                      value={endpoint.developerNotes || ""}
                      onChange={(e) => updateConfig("endpoints", endpointId, "developerNotes", e.target.value)}
                      className="min-h-[84px]"
                      placeholder="Notes displayed in service documentation for this route."
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Example Params JSON</Label>
                    <JsonTextarea
                      value={exampleDrafts[endpointId] ?? JSON.stringify(endpoint.exampleParams || {}, null, 2)}
                      onChange={(e) => handleExampleParamsChange(endpointId, e.target.value)}
                      className={`min-h-[120px] font-mono text-sm ${exampleErrors[endpointId] ? "border-amber-500" : ""}`}
                      placeholder='{"query":{"id":"u1"},"body":{"name":"John"},"headers":{"Authorization":"Bearer token"}}'
                    />
                    {exampleErrors[endpointId] && (
                      <p className="mt-1 text-sm text-amber-700 dark:text-amber-300">{exampleErrors[endpointId]}</p>
                    )}
                  </div>

                  {endpoint.operationType === "crud" && (
                    <>
                      <div className="space-y-2">
                        <Label>Linked Model</Label>
                        <Select
                          value={endpoint.linkedModel}
                          onValueChange={(value) => handleLinkedModelChange(endpointId, value)}
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Select a model" />
                          </SelectTrigger>
                          <SelectContent>
                            {Object.entries(config.models).map(([modelId, model]) => (
                              <SelectItem key={modelId} value={model.name}>
                                {model.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="space-y-2">
                        <Label>CRUD Operation</Label>
                        <Select
                          value={endpoint.crudOperation}
                          onValueChange={(value) => handleCrudOperationChange(endpointId, value)}
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Operation" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="create">Create</SelectItem>
                            <SelectItem value="read">Read</SelectItem>
                            <SelectItem value="update">Update</SelectItem>
                            <SelectItem value="delete">Delete</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="rounded-md border border-primary/25 bg-primary/10 p-3 dark:border-primary/30 dark:bg-primary/20">
                        <p className="text-xs text-primary dark:text-primary-foreground">
                          Use <span className="font-semibold">Example Params JSON</span> to drive docs testing payloads. Parameter dropdowns are intentionally removed.
                        </p>
                      </div>
                    </>
                  )}

                  {endpoint.operationType === "custom" && (
                    <div className="space-y-2">
                      <Label>Custom VQL Query</Label>
                      <JsonTextarea
                        value={endpoint.vqlQuery || ""}
                        onChange={(e) => handleVqlChange(endpointId, e.target.value)}
                        className={`h-32 font-mono ${vqlErrors[endpointId] ? "border-amber-500" : ""}`}
                        placeholder='read collection collection_name limit 25'
                      />
                      <p className="text-xs text-slate-500 dark:text-slate-300">
                        Write a readable command. Query-string values and request-body fields can supply runtime values.
                      </p>
                      {vqlErrors[endpointId] && (
                        <p className="mt-1 text-sm text-amber-700 dark:text-amber-300">{vqlErrors[endpointId]}</p>
                      )}
                    </div>
                  )}

                  {endpoint.operationType === "script" && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between gap-3">
                        <Label>Versa (.versa)</Label>
                        <div className="relative">
                          <button
                            type="button"
                            onClick={() => setModuleHelpOpen((prev) => ({ ...prev, [endpointId]: !prev[endpointId] }))}
                            className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-sky-300/40 bg-sky-500/10 text-xs font-semibold text-sky-700 transition hover:bg-sky-500/20 dark:border-sky-400/30 dark:text-sky-200"
                            title="What modules are"
                          >
                            m
                          </button>
                          {moduleHelpOpen[endpointId] && (
                            <div className="absolute right-0 top-9 z-10 w-80 rounded-xl border border-slate-200 bg-white p-3 text-left shadow-xl dark:border-slate-700 dark:bg-slate-950">
                              <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">VI modules</p>
                              <p className="mt-2 text-xs leading-6 text-slate-600 dark:text-slate-300">
                                Modules are reusable Versa imports managed in the VI portal. Attach them in the service builder, then import them in scripts with the same syntax as core modules.
                              </p>
                              <div className="mt-3 flex flex-wrap gap-2">
                                {(attachedModules.length ? attachedModules : availableModules).map((module) => (
                                  <span
                                    key={String(module?.name || "")}
                                    className="rounded-full border border-slate-200 px-2.5 py-1 text-[11px] font-medium text-slate-700 dark:border-slate-700 dark:text-slate-200"
                                  >
                                    {String(module?.name || "")}
                                  </span>
                                ))}
                                {!(attachedModules.length || availableModules.length) && (
                                  <span className="text-[11px] text-slate-500 dark:text-slate-300">
                                    No modules attached yet. Add one in the VI Modules section.
                                  </span>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {MEDIA_STORAGE_SCRIPT_PRESETS.map((preset) => (
                          <button
                            key={preset.id}
                            type="button"
                            className="rounded border border-sky-300/25 bg-sky-500/10 px-2.5 py-1 text-xs font-medium text-sky-700 transition hover:bg-sky-500/20 dark:text-sky-200"
                            onClick={() => applyScriptPreset(endpointId, preset.id)}
                            title={preset.description}
                          >
                            {preset.label}
                          </button>
                        ))}
                      </div>
                      <Textarea
                        value={endpoint.versaScript || ""}
                        onChange={(e) => updateConfig("endpoints", endpointId, "versaScript", e.target.value)}
                        className={`h-32 font-mono ${versaEndpointError ? "border-red-500 focus-visible:ring-red-500/50" : ""}`}
                        placeholder={"let p = params;\n{\n  ok: true,\n  query: p.query ?? {},\n  body: p.body ?? {}\n}"}
                      />
                      {versaEndpointError && (
                        <p className="text-sm text-red-700 dark:text-red-300">
                          {versaEndpointError}
                        </p>
                      )}
                      <p className="text-xs text-slate-500 dark:text-slate-300">
                        Scripts receive merged request params plus `query`, `body`, `service`, and auth context helpers at runtime.
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-300">
                        Media presets scaffold Cloudinary upload routes using service.env placeholders.
                      </p>
                    </div>
                  )}
                </div>

              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
