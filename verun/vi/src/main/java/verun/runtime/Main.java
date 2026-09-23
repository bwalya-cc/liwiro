// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

// File: ./vi/src/main/java/verun/runtime/Main.java
package verun.runtime;

import verun.runtime.lexer.Lexer;
import verun.runtime.lexer.Token;
import verun.runtime.parser.Parser;
import verun.runtime.evaluator.Evaluator;
import verun.runtime.evaluator.EvaluationException;
import verun.runtime.evaluator.ExitException;
import verun.runtime.ast.Node;
import verun.runtime.Logger;
import verun.runtime.modules.CustomModuleRegistry;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Scanner;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class Main {
    public static boolean LOGGING_ENABLED = false;
    public static boolean LOG_ALL = false;
    public static boolean MSG_ONLY = false;
    public static boolean PARSE_ONLY = false;
    private static final String SCRIPT_EXTENSION = ".versa";
    private static final Pattern LOCAL_IMPORT_LINE_PATTERN = Pattern.compile(
            "^\\s*(<[^>]+>|\"[^\"]+\"|'[^']+'|[A-Za-z_][A-Za-z0-9_./-]*)\\s+import\\s+(\\*|\\{[^;]*\\})\\s*;\\s*$");
    private static final Pattern IDENTIFIER_PATTERN = Pattern.compile("\\b(let|const|func|class|enum)\\s+([A-Za-z_][A-Za-z0-9_]*)\\b");
    private static final Set<String> CORE_MODULES = new HashSet<>(Arrays.asList(
            "vdb", "http", "email", "json_xml", "filer", "crypto", "jwt", "time", "datetime", "random"));

    public static void main(String[] args) {
        List<String> argsList = new ArrayList<>(Arrays.asList(args));
        LOGGING_ENABLED = argsList.contains("--log");
        LOG_ALL = argsList.contains("--all");
        MSG_ONLY = argsList.contains("--msg-only");
        PARSE_ONLY = argsList.contains("--parse-only");
        argsList.remove("--log");
        argsList.remove("--all");
        argsList.remove("--msg-only");
        argsList.remove("--parse-only");

        if (!argsList.isEmpty()) {
            int exitCode = 0;
            String filePath = argsList.get(0);
            if (!filePath.endsWith(SCRIPT_EXTENSION)) {
                System.err.println("Only VI files with extension " + SCRIPT_EXTENSION + " are supported.");
                System.exit(1);
                return;
            }
            if (LOGGING_ENABLED) {
                Logger.initialize(filePath, LOG_ALL);
            }
            String source = null;
            try {
                Path scriptPath = Paths.get(filePath);
                source = new String(Files.readAllBytes(scriptPath));
                source = preprocessLocalImports(source, scriptPath.toAbsolutePath().normalize());
                Lexer lexer = new Lexer(source);
                List<Token> tokens = lexer.tokenize();
                Parser parser = new Parser(tokens, source);
                Node ast = parser.parse();
                if (PARSE_ONLY) {
                    if (LOGGING_ENABLED && LOG_ALL) {
                        Logger.logSuccess("Script parsed successfully: " + filePath);
                    }
                    return;
                }
                Evaluator evaluator = new Evaluator(LOGGING_ENABLED, tokens, source);

                evaluator.evaluate(ast);
                if (LOGGING_ENABLED && LOG_ALL) {
                    Logger.logSuccess("Script executed successfully: " + filePath);
                }
            } catch (ExitException e) {
                exitCode = e.getExitCode();
            } catch (RuntimeException e) {
                outputError("Script error", e, source);
                exitCode = 1;
            } catch (IOException e) {
                outputError("Error reading file: " + filePath, e, null);
                exitCode = 1;
            }
            if (exitCode != 0) {
                System.exit(exitCode);
            }
        } else {
            runREPL();
        }
    }

    private static String preprocessLocalImports(String source, Path scriptPath) throws IOException {
        if (source == null) {
            return null;
        }
        Path normalized = scriptPath == null ? null : scriptPath.toAbsolutePath().normalize();
        if (normalized == null) {
            return source;
        }
        Map<Path, String> cache = new HashMap<>();
        Set<Path> stack = new HashSet<>();
        cache.put(normalized, source);
        return expandLocalImports(source, normalized, stack, cache);
    }

    private static String expandLocalImports(String source, Path currentFile, Set<Path> stack, Map<Path, String> cache)
            throws IOException {
        Path normalizedCurrent = currentFile.toAbsolutePath().normalize();
        if (stack.contains(normalizedCurrent)) {
            throw new RuntimeException("Circular local import detected: " + normalizedCurrent);
        }
        stack.add(normalizedCurrent);
        try {
            StringBuilder out = new StringBuilder();
            String[] lines = source.split("\\R", -1);
            for (String rawLine : lines) {
                String trimmed = rawLine == null ? "" : rawLine.trim();
                if (trimmed.isEmpty() || trimmed.startsWith("//") || trimmed.startsWith("#")) {
                    out.append(rawLine).append("\n");
                    continue;
                }
                Matcher m = LOCAL_IMPORT_LINE_PATTERN.matcher(rawLine);
                if (!m.matches()) {
                    out.append(rawLine).append("\n");
                    continue;
                }
                String rawTarget = m.group(1);
                String importSpec = m.group(2);
                String target = normalizeImportTarget(rawTarget);
                if (isOptionalModuleImportTarget(target)) {
                    out.append(rawLine).append("\n");
                    continue;
                }

                Path resolvedImport = resolveLocalImportPath(normalizedCurrent.getParent(), target);
                String importedSource = cache.get(resolvedImport);
                if (importedSource == null) {
                    importedSource = Files.readString(resolvedImport);
                    cache.put(resolvedImport, importedSource);
                }
                String expandedImportedSource = expandLocalImports(importedSource, resolvedImport, stack, cache);
                validateNamedImportsIfPresent(importSpec, expandedImportedSource, resolvedImport);
                String selectedImportedSource = selectImportedSource(importSpec, expandedImportedSource);

                out.append("# begin local import: ").append(target)
                        .append(" (from ").append(resolvedImport.getFileName()).append(")\n");
                out.append(selectedImportedSource);
                if (!selectedImportedSource.endsWith("\n")) {
                    out.append("\n");
                }
                out.append("# end local import: ").append(target).append("\n");
            }
            return out.toString();
        } finally {
            stack.remove(normalizedCurrent);
        }
    }

    private static boolean isOptionalModuleImportTarget(String target) {
        String normalized = String.valueOf(target).toLowerCase(Locale.ROOT);
        return CORE_MODULES.contains(normalized) || CustomModuleRegistry.isKnownCustomModule(normalized);
    }

    private static String normalizeImportTarget(String rawTarget) {
        String target = rawTarget == null ? "" : rawTarget.trim();
        if (target.startsWith("<") && target.endsWith(">") && target.length() > 2) {
            target = target.substring(1, target.length() - 1).trim();
        } else if ((target.startsWith("\"") && target.endsWith("\"")) || (target.startsWith("'") && target.endsWith("'"))) {
            target = target.substring(1, target.length() - 1);
        }
        return target;
    }

    private static Path resolveLocalImportPath(Path baseDir, String target) {
        List<Path> candidates = new ArrayList<>();
        Path targetPath = Paths.get(target);
        if (targetPath.isAbsolute()) {
            candidates.add(targetPath);
        } else {
            Path root = baseDir == null ? Paths.get(".") : baseDir;
            candidates.add(root.resolve(target));
            Path cwd = Paths.get("").toAbsolutePath().normalize();
            if (!cwd.equals(root.toAbsolutePath().normalize())) {
                candidates.add(cwd.resolve(target));
            }
        }
        List<Path> expandedCandidates = new ArrayList<>();
        for (Path candidate : candidates) {
            expandedCandidates.add(candidate);
            String filename = candidate.getFileName() == null ? "" : candidate.getFileName().toString().toLowerCase(Locale.ROOT);
            if (!filename.endsWith(SCRIPT_EXTENSION)) {
                expandedCandidates.add(Paths.get(candidate.toString() + SCRIPT_EXTENSION));
            }
        }
        for (Path candidate : expandedCandidates) {
            Path normalized = candidate.toAbsolutePath().normalize();
            if (Files.exists(normalized) && Files.isRegularFile(normalized)) {
                return normalized;
            }
        }
        throw new RuntimeException("Local import file not found: " + target);
    }

    private static void validateNamedImportsIfPresent(String importSpec, String importedSource, Path resolvedImport) {
        if (importSpec == null) {
            return;
        }
        String spec = importSpec.trim();
        if (!spec.startsWith("{") || !spec.endsWith("}")) {
            return;
        }
        String body = spec.substring(1, spec.length() - 1).trim();
        if (body.isEmpty()) {
            return;
        }
        Set<String> available = collectDeclaredNames(importedSource);
        for (String piece : body.split(",")) {
            String name = piece == null ? "" : piece.trim();
            if (name.isEmpty()) {
                continue;
            }
            if (!available.contains(name)) {
                throw new RuntimeException("Named import '" + name + "' was not found in " + resolvedImport.getFileName());
            }
        }
    }

    private static String selectImportedSource(String importSpec, String expandedImportedSource) {
        if (expandedImportedSource == null || expandedImportedSource.isEmpty()) {
            return expandedImportedSource;
        }
        if (importSpec == null) {
            return expandedImportedSource;
        }
        String spec = importSpec.trim();
        if ("*".equals(spec)) {
            return expandedImportedSource;
        }
        if (!spec.startsWith("{") || !spec.endsWith("}")) {
            return expandedImportedSource;
        }
        String body = spec.substring(1, spec.length() - 1).trim();
        if (body.isEmpty()) {
            return "";
        }
        Set<String> requested = new HashSet<>();
        for (String piece : body.split(",")) {
            String name = piece == null ? "" : piece.trim();
            if (!name.isEmpty()) {
                requested.add(name);
            }
        }
        if (requested.isEmpty()) {
            return "";
        }
        return extractNamedDeclarations(expandedImportedSource, requested);
    }

    private static String extractNamedDeclarations(String source, Set<String> requested) {
        String[] lines = source.split("\\R", -1);
        StringBuilder out = new StringBuilder();
        int i = 0;
        while (i < lines.length) {
            String line = lines[i];
            String trimmed = line == null ? "" : line.trim();
            Matcher matcher = IDENTIFIER_PATTERN.matcher(line == null ? "" : line);
            if (!trimmed.startsWith("//") && !trimmed.startsWith("#") && matcher.find()) {
                String name = matcher.group(2);
                if (requested.contains(name)) {
                    int braceDepth = countChar(line, '{') - countChar(line, '}');
                    out.append(line).append("\n");
                    i++;
                    while (i < lines.length && braceDepth > 0) {
                        String next = lines[i];
                        out.append(next).append("\n");
                        braceDepth += countChar(next, '{');
                        braceDepth -= countChar(next, '}');
                        i++;
                    }
                    continue;
                }
            }
            i++;
        }
        return out.toString();
    }

    private static int countChar(String text, char needle) {
        if (text == null || text.isEmpty()) {
            return 0;
        }
        int count = 0;
        for (int i = 0; i < text.length(); i++) {
            if (text.charAt(i) == needle) {
                count++;
            }
        }
        return count;
    }

    private static Set<String> collectDeclaredNames(String source) {
        if (source == null || source.isEmpty()) {
            return Collections.emptySet();
        }
        Set<String> names = new HashSet<>();
        String[] lines = source.split("\\R", -1);
        for (String line : lines) {
            String trimmed = line == null ? "" : line.trim();
            if (trimmed.startsWith("//") || trimmed.startsWith("#")) {
                continue;
            }
            Matcher matcher = IDENTIFIER_PATTERN.matcher(line);
            while (matcher.find()) {
                names.add(matcher.group(2));
            }
        }
        return names;
    }

    private static void runSource(String source, String scriptName, Evaluator evaluator) {
        Lexer lexer = new Lexer(source);
        List<verun.runtime.lexer.Token> tokens = lexer.tokenize();
        Parser parser = new Parser(tokens, source);
        Node ast = parser.parse();

        try {
            evaluator.evaluate(ast);
            if (LOGGING_ENABLED && LOG_ALL) {
                Logger.logSuccess("Script executed successfully: " + scriptName);
            }
        } catch (ExitException e) {
            throw e;
        } catch (Exception e) {
            outputError("Runtime error (line 1)", e, source);
        }
    }

    private static void outputError(String message, Exception e, String source) {
        String detail = e.getMessage() == null ? e.toString() : e.getMessage();
        String type = e instanceof EvaluationException ? ((EvaluationException) e).getType() : null;
        int[] location = e instanceof EvaluationException
                ? new int[] { ((EvaluationException) e).getLine(), ((EvaluationException) e).getColumn() }
                : extractLineAndColumn(detail);
        boolean hasInlineLine = location[0] > 0;
        String lineHint = hasInlineLine ? ("line " + location[0] + ", column " + location[1]) : extractLineHint(detail);
        String prefix = lineHint.isEmpty() ? message : (message + " (" + lineHint + ")");
        if (type != null && !type.isBlank()) {
            prefix = prefix + " [" + type + "]";
        }
        if (MSG_ONLY) {
            System.err.println(prefix + ": " + detail);
        } else {
            System.err.println(prefix + ": " + detail);
            if (!(e instanceof EvaluationException) && !hasInlineLine) {
                e.printStackTrace();
            }
        }

        if (hasInlineLine && source != null && !source.isEmpty()) {
            printSourcePointer(source, location[0], location[1]);
        }

        if (LOGGING_ENABLED) {
            Logger.logError(message, e);
        }
    }

    private static String extractLineHint(String detail) {
        if (detail == null || detail.isEmpty()) {
            return "";
        }
        Pattern[] patterns = new Pattern[] {
                Pattern.compile("line\\s+(\\d+)\\s*,\\s*column\\s*(\\d+)", Pattern.CASE_INSENSITIVE),
                Pattern.compile("line\\s+(\\d+):(\\d+)", Pattern.CASE_INSENSITIVE),
                Pattern.compile("line\\s+(\\d+)", Pattern.CASE_INSENSITIVE)
        };
        for (Pattern p : patterns) {
            Matcher m = p.matcher(detail);
            if (m.find()) {
                if (m.groupCount() >= 2) {
                    return "line " + m.group(1) + ", column " + m.group(2);
                }
                return "line " + m.group(1);
            }
        }
        return "";
    }

    private static int[] extractLineAndColumn(String detail) {
        if (detail == null || detail.isEmpty()) {
            return new int[] { -1, -1 };
        }
        Pattern[] patterns = new Pattern[] {
                Pattern.compile("line\\s+(\\d+)\\s*,\\s*column\\s*(\\d+)", Pattern.CASE_INSENSITIVE),
                Pattern.compile("line\\s+(\\d+):(\\d+)", Pattern.CASE_INSENSITIVE),
                Pattern.compile("line\\s+(\\d+)", Pattern.CASE_INSENSITIVE)
        };
        for (Pattern p : patterns) {
            Matcher m = p.matcher(detail);
            if (m.find()) {
                int line = Integer.parseInt(m.group(1));
                int col = m.groupCount() >= 2 ? Integer.parseInt(m.group(2)) : 1;
                return new int[] { line, Math.max(col, 1) };
            }
        }
        return new int[] { -1, -1 };
    }

    private static void printSourcePointer(String source, int line, int column) {
        String[] lines = source.split("\\R", -1);
        if (line < 1 || line > lines.length) {
            return;
        }
        String errorLine = lines[line - 1];
        int safeColumn = Math.max(1, Math.min(column, errorLine.length() + 1));
        String lineNum = String.valueOf(line);
        String gutter = " ".repeat(lineNum.length());
        String pointerPadding = " ".repeat(safeColumn - 1);

        System.err.println("--> line " + line + ", column " + safeColumn);
        System.err.println(lineNum + " | " + errorLine);
        System.err.println(gutter + " | " + pointerPadding + "^");
    }

    private static void runREPL() {
        Scanner scanner = Evaluator.sharedInputScanner();
        System.out.println("VI REPL. Type 'exit' to quit.");
        Evaluator replEvaluator = new Evaluator(LOGGING_ENABLED);
        StringBuilder buffer = new StringBuilder();
        while (true) {
            System.out.print(buffer.length() == 0 ? "> " : "... ");
            if (!scanner.hasNextLine()) {
                if (buffer.length() > 0) {
                    try {
                        runSource(normalizeReplSource(buffer.toString()), "REPL", replEvaluator);
                    } catch (ExitException e) {
                        System.exit(e.getExitCode());
                    } catch (Exception e) {
                        outputError("REPL error", e, normalizeReplSource(buffer.toString()));
                    }
                }
                break;
            }
            String line;
            try {
                line = scanner.nextLine();
            } catch (NoSuchElementException eof) {
                if (buffer.length() > 0) {
                    try {
                        runSource(normalizeReplSource(buffer.toString()), "REPL", replEvaluator);
                    } catch (ExitException e) {
                        System.exit(e.getExitCode());
                    } catch (Exception e) {
                        outputError("REPL error", e, normalizeReplSource(buffer.toString()));
                    }
                }
                break;
            }
            String trimmed = line.trim();
            if (buffer.length() == 0 && trimmed.equalsIgnoreCase("exit"))
                break;
            if (buffer.length() > 0 && trimmed.equalsIgnoreCase("exit")) {
                try {
                    runSource(normalizeReplSource(buffer.toString()), "REPL", replEvaluator);
                } catch (ExitException e) {
                    System.exit(e.getExitCode());
                } catch (Exception e) {
                    outputError("REPL error", e, normalizeReplSource(buffer.toString()));
                }
                break;
            }
            if (buffer.length() == 0 && trimmed.isEmpty()) {
                continue;
            }
            buffer.append(line).append("\n");
            if (!isCompleteReplChunk(buffer.toString())) {
                continue;
            }
            try {
                runSource(normalizeReplSource(buffer.toString()), "REPL", replEvaluator);
            } catch (ExitException e) {
                System.exit(e.getExitCode());
            } catch (Exception e) {
                outputError("REPL error", e, normalizeReplSource(buffer.toString()));
            }
            buffer.setLength(0);
        }
    }

    private static boolean isCompleteReplChunk(String source) {
        int braceDepth = 0;
        int bracketDepth = 0;
        int parenthesisDepth = 0;
        boolean inSingle = false;
        boolean inDouble = false;
        boolean escaping = false;
        for (int i = 0; i < source.length(); i++) {
            char ch = source.charAt(i);
            if (escaping) {
                escaping = false;
                continue;
            }
            if (ch == '\\') {
                escaping = true;
                continue;
            }
            if (!inDouble && ch == '\'') {
                inSingle = !inSingle;
                continue;
            }
            if (!inSingle && ch == '"') {
                inDouble = !inDouble;
                continue;
            }
            if (inSingle || inDouble) {
                continue;
            }
            if (ch == '{') {
                braceDepth++;
            } else if (ch == '}') {
                braceDepth--;
            } else if (ch == '[') {
                bracketDepth++;
            } else if (ch == ']') {
                bracketDepth--;
            } else if (ch == '(') {
                parenthesisDepth++;
            } else if (ch == ')') {
                parenthesisDepth--;
            }
        }
        String trimmed = source.trim();
        if (trimmed.isEmpty()) {
            return false;
        }
        if (braceDepth > 0 || bracketDepth > 0 || parenthesisDepth > 0) {
            return false;
        }
        if (braceDepth < 0 || bracketDepth < 0 || parenthesisDepth < 0) {
            return true;
        }
        String candidate = normalizeReplSource(source);
        try {
            Lexer lexer = new Lexer(candidate);
            List<Token> tokens = lexer.tokenize();
            Parser parser = new Parser(tokens, candidate);
            parser.parse();
            return true;
        } catch (RuntimeException ex) {
            return !looksLikeIncompleteReplChunk(ex);
        }
    }

    private static String normalizeReplSource(String source) {
        String raw = source == null ? "" : source;
        int end = raw.length();
        while (end > 0 && Character.isWhitespace(raw.charAt(end - 1))) {
            end--;
        }
        if (end <= 0) {
            return raw;
        }
        String trimmed = raw.substring(0, end);
        char lastChar = trimmed.charAt(trimmed.length() - 1);
        if (lastChar == ';' || lastChar == '}') {
            return raw;
        }
        return raw.substring(0, end) + ";" + raw.substring(end);
    }

    private static boolean looksLikeIncompleteReplChunk(RuntimeException ex) {
        String message = String.valueOf(ex == null ? "" : ex.getMessage()).toLowerCase(Locale.ROOT);
        if (message.isEmpty()) {
            return false;
        }
        return message.contains("unexpected end of input")
                || message.contains("expected ')' after")
                || message.contains("expected ']' after")
                || message.contains("expected '}' after")
                || message.contains("expected '{' after")
                || message.contains("unbalanced parentheses");
    }
}
