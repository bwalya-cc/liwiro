// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.modules;

import java.nio.file.*;
import java.io.*;

public class File {
    private Path path;

    public File(String filePath) {
        this.path = Paths.get(filePath);
    }

    public void write(String content) throws IOException {
        Files.write(path, content.getBytes());
    }

    public String read() throws IOException {
        return new String(Files.readAllBytes(path));
    }

    public void close() {
        // No specific close operation needed for basic file handling
    }

    public void delete() throws IOException {
        Files.delete(path);
    }
}