// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

const COMMON_MEDIA_ENV = {
  MEDIA_ASSET_COLLECTION: "media_assets",
  MEDIA_DEFAULT_PROVIDER: "cloudinary",
}

const CLOUDINARY_ENV = {
  ...COMMON_MEDIA_ENV,
  CLOUDINARY_CLOUD_NAME: "replace-with-cloudinary-cloud-name",
  CLOUDINARY_API_KEY: "replace-with-cloudinary-api-key",
  CLOUDINARY_API_SECRET: "replace-with-cloudinary-api-secret",
  CLOUDINARY_FOLDER: "liwiro-demo",
}

const MEDIA_PROVIDER_SUMMARY_SPECS = [
  {
    id: "cloudinary",
    label: "Cloudinary",
    envKeys: [
      "CLOUDINARY_CLOUD_NAME",
      "CLOUDINARY_API_KEY",
      "CLOUDINARY_API_SECRET",
      "CLOUDINARY_FOLDER",
    ],
    requiredEnvKeys: [
      "CLOUDINARY_CLOUD_NAME",
      "CLOUDINARY_API_KEY",
      "CLOUDINARY_API_SECRET",
    ],
    pathHints: ["/cloudinary"],
    scriptMarkers: ["api.cloudinary.com/v1_1/", "/auto/upload"],
    inputModes: ["sourceUrl", "dataUri", "dataBase64", "textBody"],
  },
]

export const MEDIA_STORAGE_ENV_PRESETS = [
  {
    id: "cloudinary",
    label: "Cloudinary",
    description: "Adds placeholder service.env values for direct Cloudinary uploads from Versa script routes.",
    env: CLOUDINARY_ENV,
  },
]

function cloudinaryScript(routePath) {
  const safeRoute = String(routePath || "/upload/cloudinary").trim() || "/upload/cloudinary"
  return [
    "let req = params;",
    "let body = req.body ?? {};",
    "let cloudName = str(service.env.CLOUDINARY_CLOUD_NAME ?? \"\").trim();",
    "let apiKey = str(service.env.CLOUDINARY_API_KEY ?? \"\").trim();",
    "let apiSecret = str(service.env.CLOUDINARY_API_SECRET ?? \"\").trim();",
    "let folder = str(body.folder ?? req.folder ?? service.env.CLOUDINARY_FOLDER ?? \"\").trim();",
    "let publicId = str(body.publicId ?? req.publicId ?? \"\").trim();",
    "let sourceUrl = str(body.sourceUrl ?? req.sourceUrl ?? \"\").trim();",
    "let dataUri = str(body.dataUri ?? req.dataUri ?? \"\").trim();",
    "let dataBase64 = str(body.dataBase64 ?? req.dataBase64 ?? \"\").trim();",
    "let textBody = str(body.textBody ?? req.textBody ?? \"\").trim();",
    "let mimeType = str(body.mimeType ?? req.mimeType ?? \"application/octet-stream\").trim();",
    "let fileValue = dataUri;",
    "if (fileValue == \"\" && dataBase64 != \"\") {",
    "  fileValue = \"data:\" + mimeType + \";base64,\" + dataBase64;",
    "}",
    "if (fileValue == \"\" && textBody != \"\") {",
    "  fileValue = \"data:text/plain;base64,\" + crypto.base64_encode(textBody);",
    "}",
    "if (fileValue == \"\") {",
    "  fileValue = sourceUrl;",
    "}",
    "if (cloudName == \"\" || apiKey == \"\" || apiSecret == \"\") {",
    "  return {ok: false, statusCode: 500, reason: \"Missing Cloudinary environment values\", error: \"Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET in metadata.env\"};",
    "}",
    "if (fileValue == \"\") {",
    "  return {ok: false, statusCode: 400, reason: \"Provide sourceUrl, dataUri, dataBase64, or textBody\"};",
    "}",
    "let form = {file: fileValue};",
    "if (folder != \"\") {",
    "  form.folder = folder;",
    "}",
    "if (publicId != \"\") {",
    "  form.public_id = publicId;",
    "}",
    "let uploadRes = http.post(\"https://api.cloudinary.com/v1_1/\" + cloudName + \"/auto/upload\", {",
    "  authBasic: {username: apiKey, password: apiSecret},",
    "  form: form,",
    "  timeoutSeconds: 90",
    "});",
    "let parsed = {};",
    "let bodyText = str(uploadRes.body ?? \"\").trim();",
    "if (bodyText != \"\") {",
    "  parsed = json_xml.parse_json(bodyText);",
    "}",
    "return {",
    "  ok: uploadRes.ok == true,",
    "  statusCode: uploadRes.status ?? 200,",
    "  provider: \"cloudinary\",",
    `  route: "${safeRoute}",`,
    "  upload: parsed,",
    "  raw: uploadRes",
    "};",
  ].join("\n")
}

export const MEDIA_STORAGE_SCRIPT_PRESETS = [
  {
    id: "cloudinary",
    label: "Cloudinary Upload",
    description: "Uploads a remote URL, data URI, base64 payload, or plain text into Cloudinary from a Versa route.",
  },
]

function dedupePreserveOrder(values) {
  const seen = new Set()
  const ordered = []
  for (const rawValue of values || []) {
    const value = String(rawValue || "").trim()
    if (!value || seen.has(value)) continue
    seen.add(value)
    ordered.push(value)
  }
  return ordered
}

function isPlaceholderEnvValue(value) {
  const text = String(value ?? "").trim().toLowerCase()
  if (!text) return true
  return (
    text.includes("replace-with")
    || text.includes("replace_me")
    || text.includes("replace-me")
    || text.includes("changeme")
    || text.includes("change-me")
    || (text.includes("<") && text.includes(">"))
  )
}

function normalizeProviderId(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/-/g, "_")
    .replace(/\s+/g, "_")
}

export function summarizeMediaCapabilities(lapisConfig) {
  const config = lapisConfig && typeof lapisConfig === "object" && !Array.isArray(lapisConfig)
    ? lapisConfig
    : {}
  const metadata = config.metadata && typeof config.metadata === "object" && !Array.isArray(config.metadata)
    ? config.metadata
    : {}
  const env = metadata.env && typeof metadata.env === "object" && !Array.isArray(metadata.env)
    ? metadata.env
    : {}
  const endpoints = config.endpoints && typeof config.endpoints === "object" && !Array.isArray(config.endpoints)
    ? config.endpoints
    : {}
  const defaultProvider = normalizeProviderId(env.MEDIA_DEFAULT_PROVIDER)
  const assetCollection = String(env.MEDIA_ASSET_COLLECTION || "media_assets").trim() || "media_assets"
  const providers = []
  const inputModes = []

  for (const spec of MEDIA_PROVIDER_SUMMARY_SPECS) {
    const routes = []
    for (const [endpointId, endpoint] of Object.entries(endpoints)) {
      const endpointConfig = endpoint && typeof endpoint === "object" ? endpoint : {}
      const path = String(endpointConfig.path || "").trim()
      const pathLower = path.toLowerCase()
      const scriptLower = String(endpointConfig.versaScript || "").trim().toLowerCase()
      const matchesPath = spec.pathHints.some((hint) => pathLower.includes(hint))
      const matchesScript = spec.scriptMarkers.some((marker) => scriptLower.includes(marker))
      if (!matchesPath && !matchesScript) continue
      routes.push({
        id: String(endpointId || "").trim(),
        method: String(endpointConfig.method || "GET").trim().toUpperCase() || "GET",
        path: path || "/",
      })
    }

    const envKeys = spec.envKeys.filter((key) => Object.prototype.hasOwnProperty.call(env, key))
    const ready = spec.requiredEnvKeys.every((key) => !isPlaceholderEnvValue(env[key]))
    const enabled = Boolean(routes.length || envKeys.length || defaultProvider === spec.id)
    if (!enabled) continue

    providers.push({
      id: spec.id,
      label: spec.label,
      ready,
      default: defaultProvider === spec.id,
      envKeys,
      routes,
      inputModes: [...spec.inputModes],
    })
    inputModes.push(...spec.inputModes)
  }

  return {
    enabled: providers.length > 0,
    assetCollection,
    defaultProvider,
    providers,
    serviceEnvKeys: Object.keys(env).map((key) => String(key).trim()).filter(Boolean).sort(),
    inputModes: dedupePreserveOrder(inputModes),
    jsonRequestOnly: providers.length > 0,
  }
}

export function envObjectToText(envObj) {
  if (!envObj || typeof envObj !== "object") return ""
  return Object.entries(envObj)
    .filter(([key]) => String(key || "").trim())
    .map(([key, value]) => `${String(key).toUpperCase()}=${String(value ?? "")}`)
    .join("\n")
}

export function parseEnvText(text) {
  const out = {}
  const lines = String(text || "").split("\n")
  for (const rawLine of lines) {
    const line = rawLine.trim()
    if (!line || line.startsWith("#")) continue
    const eqIndex = line.indexOf("=")
    if (eqIndex <= 0) continue
    const key = line.slice(0, eqIndex).trim().toUpperCase()
    if (!/^[A-Z_][A-Z0-9_]*$/.test(key)) continue
    let value = line.slice(eqIndex + 1).trim()
    if (
      (value.startsWith("\"") && value.endsWith("\"")) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1)
    }
    const lower = value.toLowerCase()
    if (lower === "true") {
      out[key] = true
    } else if (lower === "false") {
      out[key] = false
    } else if (/^-?\d+(\.\d+)?$/.test(value)) {
      out[key] = Number(value)
    } else {
      out[key] = value
    }
  }
  return out
}

export function getMediaStorageEnvPreset(presetId) {
  return MEDIA_STORAGE_ENV_PRESETS.find((preset) => preset.id === presetId) || null
}

export function applyMediaStorageEnvPreset(currentEnv, presetId) {
  const preset = getMediaStorageEnvPreset(presetId)
  if (!preset) return { ...(currentEnv || {}) }
  return {
    ...(currentEnv || {}),
    ...(preset.env || {}),
  }
}

export function buildMediaStorageScriptTemplate(presetId, routePath = "/upload") {
  if (presetId === "cloudinary") {
    return cloudinaryScript(routePath)
  }
  return [
    "let p = params;",
    "{",
    "  ok: true,",
    `  route: "${String(routePath || "/upload").trim() || "/upload"}",`,
    "  query: p.query ?? {},",
    "  body: p.body ?? {}",
    "}",
  ].join("\n")
}
