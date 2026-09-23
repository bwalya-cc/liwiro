// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial
package verun.vdb;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.PosixFilePermission;
import java.util.EnumSet;
import java.util.ArrayList;
import java.util.List;

/** Small readline-style editor used by the interactive VDB console. */
final class VDBLineEditor implements AutoCloseable {
    static final String HELP_PREVIOUS = "\u0001VDB_HELP_PREVIOUS";
    static final String HELP_NEXT = "\u0001VDB_HELP_NEXT";
    private static final String GREY = "\u001B[90m";
    private static final String RESET = "\u001B[0m";
    private static final int MAX_PERSISTED_HISTORY = 1000;
    private static final String[] COMPLETIONS = {
            "help ", "context;", "whoami;", "read domains;", "read databases;", "read collections;",
            "read collection ", "read users;", "read roles;", "create domain ", "create database ",
            "create collection ", "create in ", "update collection ", "delete from ", "drop collection ",
            "create index ", "read indexes on ", "rebuild indexes on ", "begin transaction;",
            "commit transaction;", "rollback transaction;", "transaction {", "create user ", "create role ",
            "grant ", "revoke ", "run script ", "read scripts;", "clear;", "license;", "exit;"
    };
    private final List<String> history = new ArrayList<>();
    private int historyIndex = -1;
    private String historyDraft = "";
    private List<Integer> historyMatches = List.of();
    private final boolean raw;
    private String savedStty;
    private final BufferedReader fallbackReader = new BufferedReader(new InputStreamReader(System.in));
    private boolean pageNavigation;

    VDBLineEditor() {
        loadHistory();
        raw = System.console() != null && enableRawMode();
    }

    void setPageNavigation(boolean enabled) { pageNavigation = enabled; }

    String readLine(String prompt) throws IOException {
        if (!raw) {
            System.out.print(prompt);
            System.out.flush();
            return fallbackReader.readLine();
        }
        System.out.print(prompt);
        System.out.flush();
        StringBuilder value = new StringBuilder();
        int cursor = 0;
        historyIndex = -1;
        historyDraft = "";
        historyMatches = List.of();
        while (true) {
            int first = System.in.read();
            if (first < 0 || first == 4) { // Ctrl-D
                if (value.length() == 0) return null;
                continue;
            }
            if (first == 3) { // Ctrl-C
                System.out.print("^C\r\n");
                return "";
            }
            if (first == 12) { // Ctrl-L
                clearScreen();
                redraw(prompt, value, cursor);
                continue;
            }
            if (first == 1) { cursor = 0; redraw(prompt, value, cursor); continue; } // Ctrl-A
            if (first == 5) { cursor = value.length(); redraw(prompt, value, cursor); continue; } // Ctrl-E
            if (first == 11) { value.delete(cursor, value.length()); redraw(prompt, value, cursor); continue; } // Ctrl-K
            if (first == 21) { value.delete(0, cursor); cursor = 0; redraw(prompt, value, cursor); continue; } // Ctrl-U
            if (first == 23) { // Ctrl-W
                int end = cursor;
                while (cursor > 0 && Character.isWhitespace(value.charAt(cursor - 1))) cursor--;
                while (cursor > 0 && !Character.isWhitespace(value.charAt(cursor - 1))) cursor--;
                value.delete(cursor, end);
                redraw(prompt, value, cursor);
                continue;
            }
            if (first == 9) { // Tab accepts the visible command completion.
                String suggestion = completion(value.toString());
                if (!suggestion.isEmpty()) { value.append(suggestion); cursor = value.length(); }
                else value.insert(cursor++, '\t');
                redraw(prompt, value, cursor);
                continue;
            }
            if (first == 10) { // Ctrl-J: multiline input
                value.insert(cursor++, '\n');
                redraw(prompt, value, cursor);
                continue;
            }
            if (first == 13) {
                System.out.print("\r\n");
                String result = value.toString();
                if (!result.trim().isEmpty() && (history.isEmpty() || !history.get(history.size() - 1).equals(result))) {
                    history.add(result);
                    if (history.size() > MAX_PERSISTED_HISTORY) {
                        history.remove(0);
                    }
                    saveHistory();
                }
                return result;
            }
            if (first == 127 || first == 8) {
                if (cursor > 0) { value.deleteCharAt(--cursor); redraw(prompt, value, cursor); }
                continue;
            }
            if (first == 27) {
                int second = System.in.read();
                if (second == '[' || second == 'O') {
                    int third = System.in.read();
                    if (third == 'A') { moveHistory(value, -1); cursor = value.length(); }
                    else if (third == 'B') { moveHistory(value, 1); cursor = value.length(); }
                    else if (third == 'C' && cursor < value.length()) cursor++;
                    else if (third == 'C' && cursor == value.length() && pageNavigation && value.length() == 0) { System.out.print("\r\n"); return HELP_NEXT; }
                    else if (third == 'C' && cursor == value.length()) { String suggestion = completion(value.toString()); if (!suggestion.isEmpty()) { value.append(suggestion); cursor = value.length(); } }
                    else if (third == 'D' && cursor > 0) cursor--;
                    else if (third == 'D' && cursor == 0 && pageNavigation && value.length() == 0) { System.out.print("\r\n"); return HELP_PREVIOUS; }
                    else if (third == 'H') cursor = 0;
                    else if (third == 'F') cursor = value.length();
                    else if (third == '3') { if (System.in.read() == '~' && cursor < value.length()) value.deleteCharAt(cursor); }
                    redraw(prompt, value, cursor);
                }
                continue;
            }
            if (first == 16) { // Ctrl-P
                moveHistory(value, -1); cursor = value.length(); redraw(prompt, value, cursor); continue;
            }
            if (first == 14) { // Ctrl-N
                moveHistory(value, 1); cursor = value.length(); redraw(prompt, value, cursor);
                continue;
            }
            if (first >= 32) {
                value.insert(cursor++, (char) first);
                redraw(prompt, value, cursor);
            }
        }
    }

    private void replaceHistory(StringBuilder value, int index) {
        value.setLength(0);
        if (index >= 0 && index < history.size()) value.append(history.get(index));
    }

    /** Move through the newest-to-oldest history entries matching the typed prefix. */
    private void moveHistory(StringBuilder value, int direction) {
        if (historyIndex < 0 && direction > 0) return;
        if (historyIndex < 0) {
            historyDraft = value.toString();
            historyMatches = matchingHistory(history, historyDraft);
            if (historyMatches.isEmpty()) return;
            historyIndex = historyMatches.size() - 1;
        } else {
            int next = historyIndex + direction;
            if (next < 0) next = 0;
            if (next >= historyMatches.size()) {
                historyIndex = -1;
                value.setLength(0);
                value.append(historyDraft);
                return;
            }
            historyIndex = next;
        }
        replaceHistory(value, historyMatches.get(historyIndex));
    }

    static List<Integer> matchingHistory(List<String> entries, String prefix) {
        String wanted = prefix == null ? "" : prefix;
        List<Integer> matches = new ArrayList<>();
        for (int i = 0; i < entries.size(); i++) {
            if (entries.get(i).startsWith(wanted)) matches.add(i);
        }
        return matches;
    }

    private static Path historyPath() {
        String configured = System.getProperty("vdb.command.history");
        if (configured == null || configured.isBlank()) configured = System.getenv("VDB_COMMAND_HISTORY_FILE");
        if (configured != null && !configured.isBlank()) return Path.of(configured).toAbsolutePath().normalize();
        return DirectoryUtil.SYS_DIR.resolve("command_history.txt");
    }

    private void loadHistory() {
        Path path = historyPath();
        try {
            if (!Files.isRegularFile(path)) return;
            for (String line : Files.readAllLines(path, StandardCharsets.UTF_8)) {
                if (!line.isBlank() && (history.isEmpty() || !history.get(history.size() - 1).equals(line))) history.add(line);
            }
            if (history.size() > MAX_PERSISTED_HISTORY) history.subList(0, history.size() - MAX_PERSISTED_HISTORY).clear();
        } catch (Exception ignored) {
            // History is convenience state; a damaged/unreadable file must not
            // prevent the VDB console from starting.
        }
    }

    private void saveHistory() {
        Path path = historyPath();
        try {
            Files.createDirectories(path.getParent());
            Files.write(path, history, StandardCharsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE);
            try {
                Files.setPosixFilePermissions(path, EnumSet.of(PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_WRITE));
            } catch (UnsupportedOperationException ignored) {
                // Windows and other non-POSIX filesystems use their native ACLs.
            }
        } catch (Exception ignored) {
            // Keep command execution independent from optional history storage.
        }
    }

    private static void redraw(String prompt, StringBuilder value, int cursor) {
        String[] lines = value.toString().split("\\n", -1);
        String suggestion = lines.length == 1 && cursor == value.length() ? completion(value.toString()) : "";
        StringBuilder out = new StringBuilder("\r\033[2K").append(prompt).append(lines[0]);
        if (!suggestion.isEmpty()) out.append(GREY).append(suggestion).append(RESET);
        for (int i = 1; i < lines.length; i++) out.append("\r\n\033[2K... ").append(lines[i]);
        out.append("\r");
        int column = visibleLength(prompt) + (cursor <= lines[0].length() ? cursor : lines[0].length());
        out.append("\033[").append(Math.max(0, column)).append('C');
        System.out.print(out);
        System.out.flush();
    }

    static String completion(String input) {
        if (input == null || input.isEmpty()) return "help ";
        String lower = input.toLowerCase();
        if ("read ".equals(lower)) return "collection ";
        for (String candidate : COMPLETIONS) {
            if (candidate.startsWith(lower) && candidate.length() > input.length()) return candidate.substring(input.length());
        }
        return "";
    }

    private static int visibleLength(String value) {
        return value.replaceAll("\\033\\[[;\\d]*m", "").length();
    }

    private static void clearScreen() { VDBConsole.clearConsole(); }

    private boolean enableRawMode() {
        try {
            Process get = new ProcessBuilder("sh", "-c", "stty -g < /dev/tty").redirectErrorStream(true).start();
            savedStty = new String(get.getInputStream().readAllBytes()).trim();
            get.waitFor();
            // Keep carriage-return (Enter) distinct from LF (Ctrl-J), which we
            // use for an explicit multiline insertion. Without -icrnl most
            // terminals translate Enter into LF and every command appears to
            // hang at the continuation prompt.
            Process set = new ProcessBuilder("sh", "-c", "stty -icanon -echo -icrnl min 1 < /dev/tty").inheritIO().start();
            return set.waitFor() == 0 && !savedStty.isEmpty();
        } catch (Exception ignored) { return false; }
    }

    @Override public void close() {
        if (raw && savedStty != null) {
            try { new ProcessBuilder("sh", "-c", "stty " + savedStty + " < /dev/tty").inheritIO().start().waitFor(); }
            catch (Exception ignored) { }
            System.out.println();
        }
    }
}
