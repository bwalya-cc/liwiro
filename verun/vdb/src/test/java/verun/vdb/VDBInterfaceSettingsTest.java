// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Path;

import org.junit.jupiter.api.Test;

class VDBInterfaceSettingsTest {
    @Test
    void supportsUnixSocketReturnsFalseOnWindows() {
        String original = System.getProperty("os.name");
        try {
            System.setProperty("os.name", "Windows 11");
            assertEquals("windows", VDBInterfaceSettings.hostPlatform());
            assertFalse(VDBInterfaceSettings.supportsUnixSocket());
            assertFalse(VDBInterfaceSettings.isUnixSocketEnabled());
            assertTrue(VDBInterfaceSettings.supportsNamedPipe());
            assertTrue(VDBInterfaceSettings.isNamedPipeEnabled());
            assertEquals("\\\\.\\pipe\\verun_vdb", VDBInterfaceSettings.getNamedPipePath());
        } finally {
            restoreSystemProperty("os.name", original);
        }
    }

    @Test
    void supportsUnixSocketReturnsTrueOnLinux() {
        String original = System.getProperty("os.name");
        try {
            System.setProperty("os.name", "Linux");
            assertEquals("linux", VDBInterfaceSettings.hostPlatform());
            assertTrue(VDBInterfaceSettings.supportsUnixSocket());
        } finally {
            restoreSystemProperty("os.name", original);
        }
    }

    @Test
    void platformCachePathLivesUnderRepoTmpDirectory() {
        Path cachePath = VDBInterfaceSettings.resolvePlatformCachePath();
        String normalized = cachePath.toString().replace('\\', '/');
        assertTrue(normalized.endsWith("/tmp/platform-runtime.json"));
    }

    @Test
    void normalizeNamedPipePathRemovesDuplicatePrefixAndControlCharacters() {
        assertEquals(
                "\\\\.\\pipe\\verun_vdb",
                VDBInterfaceSettings.normalizeNamedPipePath("\\\\.\\pipe\\.\\pipe\u000berun_vdb")
        );
    }

    private void restoreSystemProperty(String key, String value) {
        if (value == null) {
            System.clearProperty(key);
            return;
        }
        System.setProperty(key, value);
    }
}
