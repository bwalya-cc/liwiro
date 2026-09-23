// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.modules;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class Filer {
    private Filer() {
    }

    public static String join(Object... parts) {
        if (parts == null || parts.length == 0) {
            return "";
        }
        Path path = Path.of(String.valueOf(parts[0]));
        for (int i = 1; i < parts.length; i++) {
            path = path.resolve(String.valueOf(parts[i]));
        }
        return path.toString();
    }

    public static String ensureDir(String path) {
        try {
            Files.createDirectories(Path.of(path));
            return path;
        } catch (IOException e) {
            throw new RuntimeException("Failed to create directory: " + path + " (" + e.getMessage() + ")");
        }
    }

    public static boolean exists(String path) {
        return Files.exists(Path.of(path));
    }

    public static String writeText(String filePath, String value) {
        return JsonXml.writeText(filePath, value);
    }

    public static String readText(String filePath) {
        return JsonXml.readText(filePath);
    }

    public static String readBytesBase64(String filePath) {
        try {
            return Base64.getEncoder().encodeToString(Files.readAllBytes(Path.of(filePath)));
        } catch (IOException e) {
            throw new RuntimeException("Failed to read binary file: " + filePath + " (" + e.getMessage() + ")");
        }
    }

    public static String writeJson(String filePath, Object value, boolean pretty) {
        return JsonXml.writeJson(filePath, value, pretty);
    }

    public static Object readJson(String filePath) {
        return JsonXml.readJson(filePath);
    }

    public static String writeXml(String filePath, String xml) {
        return JsonXml.writeXml(filePath, xml);
    }

    public static Map<String, Object> readXml(String filePath) {
        return JsonXml.readXml(filePath);
    }

    public static String writeCsv(String filePath, List<?> rows) {
        List<String> lines = new ArrayList<>();
        if (rows != null) {
            for (Object row : rows) {
                lines.add(serializeCsvRow(row));
            }
        }
        return writeText(filePath, String.join("\n", lines));
    }

    public static List<Object> readCsv(String filePath) {
        String text = readText(filePath);
        List<Object> rows = new ArrayList<>();
        if (text == null || text.isEmpty()) {
            return rows;
        }
        String[] lines = text.split("\\R");
        for (String line : lines) {
            rows.add(parseCsvLine(line));
        }
        return rows;
    }

    public static Map<String, Object> readCsvRecords(String filePath) {
        List<Object> rows = readCsv(filePath);
        Map<String, Object> out = new LinkedHashMap<>();
        List<Object> headers = new ArrayList<>();
        List<Object> records = new ArrayList<>();
        if (!rows.isEmpty() && rows.get(0) instanceof List<?>) {
            headers.addAll((List<?>) rows.get(0));
            for (int i = 1; i < rows.size(); i++) {
                Object rowObj = rows.get(i);
                if (!(rowObj instanceof List<?>)) {
                    continue;
                }
                List<?> row = (List<?>) rowObj;
                Map<String, Object> rec = new LinkedHashMap<>();
                for (int j = 0; j < headers.size(); j++) {
                    Object key = headers.get(j);
                    Object value = j < row.size() ? row.get(j) : "";
                    rec.put(String.valueOf(key), value);
                }
                records.add(rec);
            }
        }
        out.put("headers", headers);
        out.put("rows", rows);
        out.put("records", records);
        return out;
    }

    private static String serializeCsvRow(Object row) {
        if (row instanceof List<?>) {
            List<String> cols = new ArrayList<>();
            for (Object col : (List<?>) row) {
                cols.add(escapeCsv(String.valueOf(col == null ? "" : col)));
            }
            return String.join(",", cols);
        }
        if (row instanceof Map<?, ?>) {
            List<String> cols = new ArrayList<>();
            for (Object value : ((Map<?, ?>) row).values()) {
                cols.add(escapeCsv(String.valueOf(value == null ? "" : value)));
            }
            return String.join(",", cols);
        }
        return escapeCsv(String.valueOf(row == null ? "" : row));
    }

    private static String escapeCsv(String value) {
        boolean quote = value.contains(",") || value.contains("\"") || value.contains("\n") || value.contains("\r");
        String escaped = value.replace("\"", "\"\"");
        return quote ? ("\"" + escaped + "\"") : escaped;
    }

    private static List<Object> parseCsvLine(String line) {
        List<Object> out = new ArrayList<>();
        if (line == null) {
            return out;
        }
        StringBuilder current = new StringBuilder();
        boolean inQuotes = false;
        for (int i = 0; i < line.length(); i++) {
            char ch = line.charAt(i);
            if (ch == '"') {
                if (inQuotes && i + 1 < line.length() && line.charAt(i + 1) == '"') {
                    current.append('"');
                    i++;
                } else {
                    inQuotes = !inQuotes;
                }
            } else if (ch == ',' && !inQuotes) {
                out.add(current.toString());
                current.setLength(0);
            } else {
                current.append(ch);
            }
        }
        out.add(current.toString());
        return out;
    }
}
