"use client"

export function normalizeVdbNamedPipePath(value) {
  let text = String(value || "").trim()
  if (!text) {
    text = "\\\\.\\pipe\\verun_vdb"
  }
  text = text.replaceAll("/", "\\")
  text = text.replaceAll("\u000b", "\\v")
  text = Array.from(text).filter((char) => {
    const code = char.charCodeAt(0)
    return code >= 32 && code !== 127
  }).join("")
  for (;;) {
    const lower = text.toLowerCase()
    let matched = ""
    for (const prefix of ["\\\\.\\pipe\\\\", "\\\\.\\pipe\\", "\\.\\pipe\\", ".\\pipe\\", "pipe\\"]) {
      if (lower.startsWith(prefix.toLowerCase())) {
        matched = prefix
        break
      }
    }
    if (!matched) {
      break
    }
    text = text.slice(matched.length)
  }
  text = text.replace(/^\\+/, "").trim()
  if (!text) {
    text = "verun_vdb"
  }
  return `\\\\.\\pipe\\${text}`
}

export function normalizeVdbTransportMode(value, supportsNamedPipe = false) {
  const text = String(value || "").trim().toLowerCase().replace("-", "_")
  if (text === "http") {
    return "http"
  }
  if (["namedpipe", "named_pipe", "pipe", "ipc", "af_pipe"].includes(text)) {
    return supportsNamedPipe ? "namedpipe" : "unixsocket"
  }
  if (["unixsocket", "unix_socket", "unix", "socket", "uds"].includes(text)) {
    return supportsNamedPipe ? "namedpipe" : "unixsocket"
  }
  return "unixsocket"
}

export function vdbTransportOptions({ supportsNamedPipe = false } = {}) {
  const options = []
  if (!supportsNamedPipe) {
    options.push({ value: "unixsocket", label: "IPC (Unix Socket)" })
  } else {
    options.push({ value: "namedpipe", label: "IPC (Named Pipe)" })
  }
  options.push({ value: "http", label: "HTTP Server" })
  return options
}

export function vdbTransportLabel(transport, supportsNamedPipe = false) {
  const normalized = normalizeVdbTransportMode(transport, supportsNamedPipe)
  if (normalized === "http") {
    return "HTTP"
  }
  if (normalized === "namedpipe") {
    return "VDBNamedPipe"
  }
  return "VDBUnixSocket"
}

export function vdbTransportTargetConfig({
  transport,
  serverUrl,
  socketPath,
  namedPipePath,
  defaultServerUrl = "http://127.0.0.1:1957",
  defaultSocketPath = "/tmp/vdb.sock",
  defaultNamedPipePath = "\\\\.\\pipe\\verun_vdb",
  supportsNamedPipe: _supportsNamedPipe = false,
} = {}) {
  const normalized = normalizeVdbTransportMode(transport, _supportsNamedPipe)
  if (normalized === "http") {
    return {
      mode: normalized,
      key: "vdb_server_url",
      label: "VDB Server URL",
      value: String(serverUrl || ""),
      placeholder: defaultServerUrl,
    }
  }
  if (normalized === "namedpipe") {
    return {
      mode: normalized,
      key: "vdb_named_pipe_path",
      label: "VDB Named Pipe Path",
      value: normalizeVdbNamedPipePath(namedPipePath || defaultNamedPipePath),
      placeholder: normalizeVdbNamedPipePath(defaultNamedPipePath),
    }
  }
  return {
    mode: normalized,
    key: "vdb_unix_socket_path",
    label: "VDB Unix Socket Path",
    value: String(socketPath || ""),
    placeholder: defaultSocketPath,
  }
}
