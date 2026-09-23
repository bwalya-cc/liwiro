// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
package verun.vdb;

import org.junit.jupiter.api.Test;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class VDBLineEditorTest {
    @Test
    void commandHistoryIsLoadedFromThePreviousSession() throws Exception {
        Path historyPath = Files.createTempFile("vdb-command-history-", ".txt");
        try {
            Files.writeString(historyPath, "read domains;\n");
            System.setProperty("vdb.command.history", historyPath.toString());
            try (VDBLineEditor editor = new VDBLineEditor()) {
                Field historyField = VDBLineEditor.class.getDeclaredField("history");
                historyField.setAccessible(true);
                @SuppressWarnings("unchecked")
                List<String> history = (List<String>) historyField.get(editor);
                assertTrue(history.contains("read domains;"));
            }
        } finally {
            System.clearProperty("vdb.command.history");
            Files.deleteIfExists(historyPath);
        }
    }

    @Test
    void historyNavigationUsesTheTypedPrefix() {
        List<String> entries = List.of("read domains;", "create domain auth;", "read databases;", "read users;");
        assertEquals(List.of(0, 2, 3), VDBLineEditor.matchingHistory(entries, "read "));
        assertEquals(List.of(1), VDBLineEditor.matchingHistory(entries, "cre"));
        assertEquals(List.of(1), VDBLineEditor.matchingHistory(entries, "create d"));
        assertEquals(List.of(0, 1, 2, 3), VDBLineEditor.matchingHistory(entries, ""));
    }

    @Test
    void commandHistoryIsWrittenForTheNextSession() throws Exception {
        Path historyPath = Files.createTempFile("vdb-command-history-write-", ".txt");
        try {
            Files.deleteIfExists(historyPath);
            System.setProperty("vdb.command.history", historyPath.toString());
            try (VDBLineEditor editor = new VDBLineEditor()) {
                Field historyField = VDBLineEditor.class.getDeclaredField("history");
                historyField.setAccessible(true);
                @SuppressWarnings("unchecked")
                List<String> history = (List<String>) historyField.get(editor);
                history.add("read users;");
                Method save = VDBLineEditor.class.getDeclaredMethod("saveHistory");
                save.setAccessible(true);
                save.invoke(editor);
            }
            assertEquals("read users;\n", Files.readString(historyPath));
        } finally {
            System.clearProperty("vdb.command.history");
            Files.deleteIfExists(historyPath);
        }
    }
}
