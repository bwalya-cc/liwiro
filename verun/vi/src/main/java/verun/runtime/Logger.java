// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

 // File: ./vi/src/main/java/verun/runtime/Logger.java

package verun.runtime;

import java.io.IOException;
import java.io.PrintWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.UUID;
import java.text.SimpleDateFormat;
import java.util.Date;

public class Logger {
    private static PrintWriter logWriter;
    private static boolean logAll = false;
    private static Path logsDir;
    private static Path viLogsDir;

    public static void initialize(String scriptName, boolean logAll) {
        Logger.logAll = logAll;
        logsDir = resolveLogsDir();
        viLogsDir = logsDir.resolve("vi");

        try {
            // Create logs directory if it doesn't exist
            if (!Files.exists(logsDir)) {
                Files.createDirectories(logsDir);
            }

            // Create vi subdirectory if it doesn't exist
            if (!Files.exists(viLogsDir)) {
                Files.createDirectories(viLogsDir);
            }

            // Create sessions.log file if it doesn't exist
            Path sessionsLog = logsDir.resolve("sessions.log");
            if (!Files.exists(sessionsLog)) {
                Files.createFile(sessionsLog);
            }

            // Initialize session log
            try (PrintWriter sessionWriter = new PrintWriter(
                    Files.newBufferedWriter(sessionsLog, StandardOpenOption.APPEND))) {
                sessionWriter.println(String.join(",",
                        java.time.LocalDateTime.now().format(java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")),
                        UUID.randomUUID().toString(),
                        "VI",
                        "START"));
            }

            // Initialize main log
            String safeScriptName = scriptName.replaceAll("[^a-zA-Z0-9]", "_");
            String timestamp = new SimpleDateFormat("yyyyMMdd_HHmmss").format(new Date());
            String logFileName = String.format("script_%s_%s.log", safeScriptName, timestamp);
            Path logFile = viLogsDir.resolve(logFileName);

            logWriter = new PrintWriter(Files.newBufferedWriter(logFile, StandardOpenOption.CREATE));
            Runtime.getRuntime().addShutdownHook(new Thread(Logger::close));
        } catch (IOException e) {
            System.err.println("Failed to initialize logger: " + e.getMessage());
            // Fallback: Log to standard error
            logWriter = new PrintWriter(System.err);
        }
    }

    private static Path resolveLogsDir() {
        Path cwd = Paths.get("").toAbsolutePath().normalize();
        Path logsFromCwd = cwd.resolve("logs");
        if (Files.isDirectory(logsFromCwd)) {
            return logsFromCwd;
        }

        Path verunFromCwd = cwd.resolve("verun");
        if (Files.isDirectory(verunFromCwd)) {
            return verunFromCwd.resolve("logs");
        }

        if (cwd.getFileName() != null && "vi".equals(cwd.getFileName().toString())) {
            Path parent = cwd.getParent();
            if (parent != null && parent.getFileName() != null && "verun".equals(parent.getFileName().toString())) {
                return parent.resolve("logs");
            }
        }

        return cwd.resolve("logs");
    }

    public static void logError(String message, Throwable e) {
        if (logWriter != null) {
            logWriter.println("[" + new Date() + "] ERROR: " + message);
            e.printStackTrace(logWriter);
            logWriter.flush();
        }
    }

    public static void logSuccess(String message) {
        if (logWriter != null && logAll) {
            logWriter.println("[" + new Date() + "] SUCCESS: " + message);
            logWriter.flush();
        }
    }

    public static void close() {
        if (logWriter != null) {
            logWriter.close();
        }
    }
}
