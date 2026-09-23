// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import java.util.Locale;

public final class VDBLogSettings {
    private static volatile boolean runtimeLogsEnabled = false;

    private VDBLogSettings() {
    }

    public static boolean isRuntimeLogsEnabled() {
        return runtimeLogsEnabled;
    }

    public static void setRuntimeLogsEnabled(boolean enabled) {
        runtimeLogsEnabled = enabled;
    }

    public static boolean isConsoleLogsEnabled() {
        return readBoolEnv("VDB_CONSOLE_LOGS", true);
    }

    public static boolean isHttpTrafficLogsEnabled() {
        return readBoolEnv("VDB_HTTP_TRAFFIC_LOGS", false);
    }

    public static boolean isFileLogsEnabled() {
        return readBoolEnv("VDB_FILE_LOGS", true);
    }

    private static boolean readBoolEnv(String key, boolean defaultValue) {
        String value = System.getenv(key);
        if (value == null) {
            return defaultValue;
        }
        String normalized = value.trim().toLowerCase(Locale.ROOT);
        if (normalized.isEmpty()) {
            return defaultValue;
        }
        return "1".equals(normalized)
                || "true".equals(normalized)
                || "yes".equals(normalized)
                || "on".equals(normalized);
    }
}
