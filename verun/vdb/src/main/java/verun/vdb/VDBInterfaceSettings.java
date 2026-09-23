// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

public final class VDBInterfaceSettings {
    private static final Gson GSON = new Gson();

    private VDBInterfaceSettings() {
    }

    public static String hostPlatform() {
        String detected = detectHostPlatform();
        String cached = readCachedPlatform();
        String resolved = cached == null || cached.isBlank() ? detected : cached.trim().toLowerCase();
        if (!resolved.equals(detected)) {
            resolved = detected;
        }
        writePlatformCache(resolved);
        return resolved;
    }

    private static String detectHostPlatform() {
        String osName = String.valueOf(System.getProperty("os.name", "")).trim().toLowerCase();
        if (osName.startsWith("win")) {
            return "windows";
        }
        if (osName.startsWith("mac")) {
            return "macos";
        }
        if (!osName.isEmpty()) {
            return osName;
        }
        return "linux";
    }

    private static String readCachedPlatform() {
        Path cachePath = resolvePlatformCachePath();
        try {
            if (!Files.exists(cachePath)) {
                return null;
            }
            String raw = Files.readString(cachePath, StandardCharsets.UTF_8);
            JsonObject payload = JsonParser.parseString(raw).getAsJsonObject();
            if (!payload.has("platform")) {
                return null;
            }
            String cached = String.valueOf(payload.get("platform").getAsString()).trim().toLowerCase();
            if ("windows".equals(cached) || "linux".equals(cached) || "macos".equals(cached)) {
                return cached;
            }
        } catch (Exception ignored) {
        }
        return null;
    }

    private static void writePlatformCache(String platform) {
        Path cachePath = resolvePlatformCachePath();
        try {
            Files.createDirectories(cachePath.getParent());
            JsonObject payload = new JsonObject();
            payload.addProperty("schema", 1);
            payload.addProperty("platform", platform);
            payload.addProperty("system", String.valueOf(System.getProperty("os.name", "")).trim());
            payload.addProperty("os_name", platform.startsWith("win") ? "nt" : "posix");
            payload.addProperty("detected_by", "java");
            payload.addProperty("cache_path", cachePath.toString());
            Files.writeString(cachePath, GSON.toJson(payload) + System.lineSeparator(), StandardCharsets.UTF_8);
        } catch (Exception ignored) {
        }
    }

    static Path resolvePlatformCachePath() {
        Path vdbRoot = DirectoryUtil.VDB_ROOT;
        Path verunRoot = vdbRoot.getParent();
        Path repoRoot = verunRoot == null ? Paths.get("").toAbsolutePath().normalize() : verunRoot.getParent();
        if (repoRoot == null) {
            repoRoot = Paths.get("").toAbsolutePath().normalize();
        }
        return repoRoot.resolve("tmp").resolve("platform-runtime.json").toAbsolutePath().normalize();
    }

    public static boolean supportsUnixSocket() {
        return !"windows".equals(hostPlatform());
    }

    public static boolean supportsNamedPipe() {
        return "windows".equals(hostPlatform());
    }

    public static boolean isNamedPipeEnabled() {
        if (!supportsNamedPipe()) {
            return false;
        }
        return readBool(
                "vdb.interface.namedpipe.enabled",
                "VDB_INTERFACE_NAMEDPIPE_ENABLED",
                "VDB_NAMED_PIPE_ENABLED",
                true);
    }

    public static String getNamedPipePath() {
        String configured = readString(
                "vdb.interface.namedpipe.path",
                "VDB_INTERFACE_NAMEDPIPE_PATH",
                "VDB_NAMED_PIPE_PATH");
        return normalizeNamedPipePath(configured);
    }

    public static String resolveDefaultNamedPipePath() {
        return "\\\\.\\pipe\\verun_vdb";
    }

    public static String normalizeNamedPipePath(String rawValue) {
        String value = String.valueOf(rawValue == null ? "" : rawValue).trim().replace('/', '\\');
        if (value.isEmpty()) {
            value = resolveDefaultNamedPipePath();
        }
        value = value.replace("\u000b", "\\v");
        StringBuilder sanitized = new StringBuilder();
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            if (ch >= 32 && ch != 127) {
                sanitized.append(ch);
            }
        }
        value = sanitized.toString();
        String[] prefixes = {"\\\\.\\pipe\\\\", "\\\\.\\pipe\\", "\\.\\pipe\\", ".\\pipe\\", "pipe\\"};
        while (true) {
            String lower = value.toLowerCase();
            boolean changed = false;
            for (String prefix : prefixes) {
                if (lower.startsWith(prefix.toLowerCase())) {
                    value = value.substring(prefix.length());
                    changed = true;
                    break;
                }
            }
            if (!changed) {
                break;
            }
        }
        while (value.startsWith("\\")) {
            value = value.substring(1);
        }
        value = value.trim();
        if (value.isEmpty()) {
            value = "verun_vdb";
        }
        return "\\\\.\\pipe\\" + value;
    }

    public static boolean isUnixSocketEnabled() {
        if (!supportsUnixSocket()) {
            return false;
        }
        return readBool(
                "vdb.interface.unixsocket.enabled",
                "VDB_INTERFACE_UNIXSOCKET_ENABLED",
                "VDB_UNIX_SOCKET_ENABLED",
                true);
    }

    public static String getUnixSocketPath() {
        String configured = readString(
                "vdb.interface.unixsocket.path",
                "VDB_INTERFACE_UNIXSOCKET_PATH",
                "VDB_UNIX_SOCKET_PATH");
        if (configured != null && !configured.trim().isEmpty()) {
            return configured.trim();
        }
        return resolveDefaultUnixSocketPath();
    }

    public static String resolveDefaultUnixSocketPath() {
        Path runDir = Paths.get("/run");
        if (Files.isDirectory(runDir) && Files.isWritable(runDir)) {
            return runDir.resolve("vdb.sock").toString();
        }
        return Paths.get(System.getProperty("java.io.tmpdir"), "vdb.sock").toString();
    }

    private static boolean readBool(String propertyKey, String envKey, String legacyEnvKey, boolean fallback) {
        String raw = readString(propertyKey, envKey, legacyEnvKey);
        if (raw == null) {
            return fallback;
        }
        String value = raw.trim().toLowerCase();
        if ("1".equals(value) || "true".equals(value) || "yes".equals(value) || "on".equals(value)) {
            return true;
        }
        if ("0".equals(value) || "false".equals(value) || "no".equals(value) || "off".equals(value)) {
            return false;
        }
        return fallback;
    }

    private static String readString(String propertyKey, String envKey, String legacyEnvKey) {
        String propertyValue = System.getProperty(propertyKey);
        if (propertyValue != null && !propertyValue.trim().isEmpty()) {
            return propertyValue;
        }
        String envValue = System.getenv(envKey);
        if (envValue != null && !envValue.trim().isEmpty()) {
            return envValue;
        }
        String legacyValue = System.getenv(legacyEnvKey);
        if (legacyValue != null && !legacyValue.trim().isEmpty()) {
            return legacyValue;
        }
        return null;
    }
}
