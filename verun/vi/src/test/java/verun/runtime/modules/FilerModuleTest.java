// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.modules;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;

import static org.junit.jupiter.api.Assertions.assertEquals;

public class FilerModuleTest {
    @TempDir
    Path tempDir;

    @Test
    void readsBinaryFilesAsBase64() throws Exception {
        byte[] payload = new byte[] {0x00, 0x01, 0x02, 0x03, 0x3f, 0x40, (byte) 0xfe, (byte) 0xff};
        Path file = tempDir.resolve("media.bin");
        Files.write(file, payload);

        String encoded = Filer.readBytesBase64(file.toString());

        assertEquals(Base64.getEncoder().encodeToString(payload), encoded);
    }
}
