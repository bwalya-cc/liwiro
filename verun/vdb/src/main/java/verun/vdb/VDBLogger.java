// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.UUID;

public class VDBLogger {
    private PrintWriter writer;
    private String sessionId;
    private final boolean consoleLogsEnabled;
    private final boolean fileLogsEnabled;
    private static final DateTimeFormatter dtf = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    public VDBLogger() throws IOException {
        this.sessionId = UUID.randomUUID().toString();
        this.consoleLogsEnabled = VDBLogSettings.isConsoleLogsEnabled();
        this.fileLogsEnabled = VDBLogSettings.isFileLogsEnabled();
        initializeSessionLog();
        this.writer = fileLogsEnabled
                ? new PrintWriter(new FileWriter(
                        DirectoryUtil.VDB_LOGS_DIR.resolve(sessionId + ".log").toString(), true), true)
                : null;
    }

    public VDBLogger(String sessionId) throws IOException {
        this.sessionId = sessionId;
        this.consoleLogsEnabled = VDBLogSettings.isConsoleLogsEnabled();
        this.fileLogsEnabled = VDBLogSettings.isFileLogsEnabled();
        Path logFile = DirectoryUtil.VDB_LOGS_DIR.resolve(sessionId + ".log");
        this.writer = fileLogsEnabled ? new PrintWriter(new FileWriter(logFile.toString(), true), true) : null;
        initializeSessionLog();

        // Add shutdown hook to ensure logs are flushed on exit
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            this.close();
        }));
    }

    private void initializeSessionLog() {
        if (!fileLogsEnabled) {
            return;
        }
        try (PrintWriter sessionWriter = new PrintWriter(new FileWriter(
                DirectoryUtil.SESSIONS_LOG.toString(), true))) {
            sessionWriter.println(String.join(",",
                LocalDateTime.now().format(dtf),
                sessionId,
                "VDB",
                "START"
            ));
        } catch (IOException e) {
            System.err.println("Failed to write to sessions.log: " + e.getMessage());
        }
    }

    public synchronized void log(String message) {
        if (!VDBLogSettings.isRuntimeLogsEnabled()) {
            return;
        }
        String timestamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
        String logMessage = String.format("%s - %s", timestamp, message);
        
        if (consoleLogsEnabled) {
            // Colorize based on message content
            if (message.contains("error") || message.contains("failed")) {
                System.err.println(ColorUtil.colorize(logMessage, ColorUtil.RED));
            } else if (message.contains("warning")) {
                System.err.println(ColorUtil.colorize(logMessage, ColorUtil.YELLOW));
            } else if (message.contains("success")) {
                System.out.println(ColorUtil.colorize(logMessage, ColorUtil.GREEN));
            } else {
                System.out.println(logMessage);
            }
        }

        if (writer != null) {
            writer.println(logMessage);
            writer.flush();
        }
    }

    public synchronized void close() {
        if (writer != null) {
            writer.flush();
            writer.close();
        }
    }
}
