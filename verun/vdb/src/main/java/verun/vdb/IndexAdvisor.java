// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.reflect.TypeToken;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Scanner;

public final class IndexAdvisor {
    private static final Gson GSON = new GsonBuilder().disableHtmlEscaping().create();
    private static final int DEFAULT_MIN_QUERIES = 8;
    private static final double DEFAULT_MIN_SCAN_RATIO = 0.70d;

    private IndexAdvisor() {
    }

    public static synchronized void recordFind(
            String domain,
            String db,
            String collection,
            Map<String, Object> query,
            int totalDocs,
            int scannedDocs,
            List<String> indexedFieldsUsed,
            long elapsedNanos) {
        if (query == null || query.isEmpty() || collection == null || collection.isEmpty()) {
            return;
        }
        Policy policy = loadPolicy();
        if ("off".equals(policy.mode)) {
            return;
        }

        List<String> eqFields = extractEqFields(query);
        if (eqFields.isEmpty()) {
            return;
        }

        int safeTotal = Math.max(totalDocs, 1);
        double scanRatio = Math.min(1.0d, Math.max(0.0d, scannedDocs / (double) safeTotal));
        Map<String, Object> stats = readStructuredMap(DirectoryUtil.INDEX_ADVISOR_STATS);
        Map<String, Object> indexDefs = readCollectionIndexDefs(domain, db, collection);
        long now = System.currentTimeMillis();

        for (String field : eqFields) {
            String key = statKey(domain, db, collection, field);
            Map<String, Object> rec = asMap(stats.get(key));
            if (rec.isEmpty()) {
                rec = new LinkedHashMap<>();
                rec.put("domain", domain);
                rec.put("db", db);
                rec.put("collection", collection);
                rec.put("field", field);
                rec.put("eq_queries", 0.0d);
                rec.put("indexed_hits", 0.0d);
                rec.put("full_scan_hits", 0.0d);
                rec.put("avg_scan_ratio", 0.0d);
                rec.put("avg_elapsed_ms", 0.0d);
                rec.put("created_at", now);
            }

            double count = asDouble(rec.get("eq_queries"), 0.0d) + 1.0d;
            double avgRatio = asDouble(rec.get("avg_scan_ratio"), 0.0d);
            avgRatio = ((avgRatio * (count - 1.0d)) + scanRatio) / count;

            double elapsedMs = elapsedNanos / 1_000_000.0d;
            double avgElapsed = asDouble(rec.get("avg_elapsed_ms"), 0.0d);
            avgElapsed = ((avgElapsed * (count - 1.0d)) + elapsedMs) / count;

            boolean usedIndex = indexedFieldsUsed != null && indexedFieldsUsed.contains(field);
            boolean hasIndex = indexDefs.containsKey(field);

            rec.put("eq_queries", count);
            rec.put("avg_scan_ratio", avgRatio);
            rec.put("avg_elapsed_ms", avgElapsed);
            rec.put("last_elapsed_ms", elapsedMs);
            rec.put("last_scan_ratio", scanRatio);
            rec.put("indexed_hits", asDouble(rec.get("indexed_hits"), 0.0d) + (usedIndex ? 1.0d : 0.0d));
            rec.put("full_scan_hits", asDouble(rec.get("full_scan_hits"), 0.0d) + (scanRatio >= 0.99d ? 1.0d : 0.0d));
            rec.put("index_exists", hasIndex);
            rec.put("recommended", shouldRecommend(hasIndex, count, avgRatio, policy));
            rec.put("last_seen", now);

            stats.put(key, rec);
        }

        stats.put("updated_at", now);
        writeStructuredMap(DirectoryUtil.INDEX_ADVISOR_STATS, stats);
        appendQueryLog(domain, db, collection, eqFields, safeTotal, scannedDocs, scanRatio, indexedFieldsUsed, elapsedNanos, now);
    }

    public static synchronized List<Map<String, Object>> recommendations(String domain, String db) {
        Map<String, Object> stats = readStructuredMap(DirectoryUtil.INDEX_ADVISOR_STATS);
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map.Entry<String, Object> e : stats.entrySet()) {
            if ("updated_at".equals(e.getKey())) {
                continue;
            }
            Map<String, Object> rec = asMap(e.getValue());
            if (rec.isEmpty()) {
                continue;
            }
            if (!domain.equals(String.valueOf(rec.get("domain")))) {
                continue;
            }
            if (!db.equals(String.valueOf(rec.get("db")))) {
                continue;
            }
            if (!asBool(rec.get("recommended"), false)) {
                continue;
            }
            out.add(new LinkedHashMap<>(rec));
        }
        return out;
    }

    public static synchronized Map<String, Object> startupAdvisor(String channel, boolean interactive) {
        String domain = VDB.getCurrentDomain();
        String db = VDB.getCurrentDB();
        Policy policy = loadPolicy();
        List<Map<String, Object>> recs = recommendations(domain, db);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("channel", channel);
        out.put("mode", policy.mode);
        out.put("domain", domain);
        out.put("db", db);
        out.put("recommendations", recs);

        if (recs.isEmpty()) {
            return out;
        }

        VDB.logRuntime("index_advisor", "Found " + recs.size() + " index recommendation(s) for " + domain + "/" + db);

        if ("auto".equals(policy.mode)) {
            int created = applyRecommendations(domain, db, Integer.MAX_VALUE);
            out.put("created", created);
            VDB.logRuntime("index_advisor", "Auto-created " + created + " indexes");
            return out;
        }

        if ("off".equals(policy.mode)) {
            return out;
        }

        if (!interactive) {
            out.put("hint", "Set advisor policy to auto/manual/off via vdb.index_advisor_policy(mode)");
            return out;
        }

        printRecommendations(recs);
        System.out.println("Index advisor options:");
        System.out.println("  [k] keep manual (do nothing)");
        System.out.println("  [a] auto-create recommendations now and set mode=auto");
        System.out.println("  [m] set mode=manual");
        System.out.println("  [o] set mode=off");
        System.out.println("  [r] remove advisor-created indexes and set mode=manual");
        System.out.print("Choose [k/a/m/o/r]: ");
        String choice = "k";
        try {
            Scanner scanner = new Scanner(System.in);
            if (scanner.hasNextLine()) {
                choice = String.valueOf(scanner.nextLine()).trim().toLowerCase(Locale.ROOT);
            }
        } catch (Exception ignored) {
            choice = "k";
        }

        switch (choice) {
            case "a":
                policy.mode = "auto";
                savePolicy(policy);
                out.put("created", applyRecommendations(domain, db, Integer.MAX_VALUE));
                break;
            case "m":
                policy.mode = "manual";
                savePolicy(policy);
                break;
            case "o":
                policy.mode = "off";
                savePolicy(policy);
                break;
            case "r":
                out.put("removed", removeAdvisorIndexes(domain, db));
                policy.mode = "manual";
                savePolicy(policy);
                break;
            case "k":
            default:
                break;
        }
        out.put("mode", loadPolicy().mode);
        return out;
    }

    public static synchronized int applyRecommendations(String domain, String db, int limit) {
        int created = 0;
        List<Map<String, Object>> recs = recommendations(domain, db);
        String prevDomain = VDB.getCurrentDomain();
        String prevDb = VDB.getCurrentDB();
        switchContext(domain, db);
        for (Map<String, Object> rec : recs) {
            if (created >= limit) {
                break;
            }
            String collection = String.valueOf(rec.get("collection"));
            String field = String.valueOf(rec.get("field"));
            if (collection.isEmpty() || field.isEmpty()) {
                continue;
            }
            try {
                VDB.createIndex(collection, field, false, "advisor",
                        "auto-created from query advisor (eq_queries=" + asInt(rec.get("eq_queries"), 0) + ")");
                created++;
            } catch (Exception ignored) {
            }
        }
        switchContext(prevDomain, prevDb);
        return created;
    }

    public static synchronized int removeAdvisorIndexes(String domain, String db) {
        int removed = 0;
        String prevDomain = VDB.getCurrentDomain();
        String prevDb = VDB.getCurrentDB();
        switchContext(domain, db);
        for (String collection : DirectoryUtil.getCollections(domain, db)) {
            Map<String, Object> defs = readCollectionIndexDefs(domain, db, collection);
            List<String> toDrop = new ArrayList<>();
            for (Map.Entry<String, Object> e : defs.entrySet()) {
                Map<String, Object> cfg = asMap(e.getValue());
                if ("advisor".equals(String.valueOf(cfg.get("created_by")))) {
                    toDrop.add(e.getKey());
                }
            }
            for (String field : toDrop) {
                try {
                    VDB.dropIndex(collection, field);
                    removed++;
                } catch (Exception ignored) {
                }
            }
        }
        switchContext(prevDomain, prevDb);
        return removed;
    }

    public static synchronized Map<String, Object> advisorStatus(String domain, String db) {
        Map<String, Object> out = new LinkedHashMap<>();
        Policy policy = loadPolicy();
        out.put("policy", policy.toMap());
        out.put("stats", statsFor(domain, db));
        out.put("recommendations", recommendations(domain, db));
        return out;
    }

    private static List<Map<String, Object>> statsFor(String domain, String db) {
        Map<String, Object> stats = readStructuredMap(DirectoryUtil.INDEX_ADVISOR_STATS);
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map.Entry<String, Object> e : stats.entrySet()) {
            if ("updated_at".equals(e.getKey())) {
                continue;
            }
            Map<String, Object> rec = asMap(e.getValue());
            if (rec.isEmpty()) {
                continue;
            }
            if (!domain.equals(String.valueOf(rec.get("domain")))) {
                continue;
            }
            if (!db.equals(String.valueOf(rec.get("db")))) {
                continue;
            }
            out.add(new LinkedHashMap<>(rec));
        }
        return out;
    }

    public static synchronized Map<String, Object> setPolicy(String mode) {
        Policy policy = loadPolicy();
        String clean = String.valueOf(mode == null ? "" : mode).trim().toLowerCase(Locale.ROOT);
        if (!"auto".equals(clean) && !"manual".equals(clean) && !"off".equals(clean)) {
            throw new RuntimeException("index advisor mode must be auto, manual, or off");
        }
        policy.mode = clean;
        policy.updatedAt = System.currentTimeMillis();
        savePolicy(policy);
        return policy.toMap();
    }

    private static boolean shouldRecommend(boolean hasIndex, double queries, double avgScanRatio, Policy policy) {
        if (hasIndex) {
            return false;
        }
        if (queries < policy.minQueries) {
            return false;
        }
        return avgScanRatio >= policy.minScanRatio;
    }

    private static List<String> extractEqFields(Map<String, Object> query) {
        List<String> fields = new ArrayList<>();
        for (Map.Entry<String, Object> e : query.entrySet()) {
            String key = e.getKey();
            if (key == null || key.isEmpty() || key.startsWith("$")) {
                continue;
            }
            Object value = e.getValue();
            if (value instanceof Map<?, ?> || value instanceof List<?>) {
                continue;
            }
            fields.add(key);
        }
        return fields;
    }

    private static void appendQueryLog(
            String domain,
            String db,
            String collection,
            List<String> eqFields,
            int totalDocs,
            int scannedDocs,
            double scanRatio,
            List<String> indexedFieldsUsed,
            long elapsedNanos,
            long ts) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("ts", ts);
        row.put("domain", domain);
        row.put("db", db);
        row.put("collection", collection);
        row.put("eq_fields", eqFields);
        row.put("total_docs", totalDocs);
        row.put("scanned_docs", scannedDocs);
        row.put("scan_ratio", scanRatio);
        row.put("indexed_fields_used", indexedFieldsUsed == null ? Collections.emptyList() : indexedFieldsUsed);
        row.put("elapsed_ms", elapsedNanos / 1_000_000.0d);
        try {
            Files.createDirectories(DirectoryUtil.INDEX_ADVISOR_DIR);
            BsonStorage.appendLogEntry(DirectoryUtil.INDEX_ADVISOR_QUERY_LOG, row);
        } catch (IOException ignored) {
        }
    }

    private static Map<String, Object> readCollectionIndexDefs(String domain, String db, String collection) {
        Path path = DirectoryUtil.getCollectionIndexDefinitionsPath(domain, db, collection);
        return readStructuredMap(path);
    }

    private static Map<String, Object> readStructuredMap(Path path) {
        if (path == null || !Files.exists(path)) {
            return new LinkedHashMap<>();
        }
        try {
            Map<String, Object> parsed = BsonStorage.readMap(path);
            if (parsed == null) {
                return new LinkedHashMap<>();
            }
            return new LinkedHashMap<>(parsed);
        } catch (Exception e) {
            return new LinkedHashMap<>();
        }
    }

    private static void writeStructuredMap(Path path, Map<String, Object> map) {
        try {
            Files.createDirectories(path.getParent());
            BsonStorage.writeValue(path, map);
        } catch (IOException ignored) {
        }
    }

    private static Map<String, Object> asMap(Object value) {
        if (!(value instanceof Map<?, ?>)) {
            return new LinkedHashMap<>();
        }
        Map<String, Object> out = new LinkedHashMap<>();
        for (Map.Entry<?, ?> e : ((Map<?, ?>) value).entrySet()) {
            out.put(String.valueOf(e.getKey()), e.getValue());
        }
        return out;
    }

    private static double asDouble(Object value, double fallback) {
        if (value instanceof Number) {
            return ((Number) value).doubleValue();
        }
        try {
            return Double.parseDouble(String.valueOf(value));
        } catch (Exception e) {
            return fallback;
        }
    }

    private static int asInt(Object value, int fallback) {
        if (value instanceof Number) {
            return ((Number) value).intValue();
        }
        try {
            return Integer.parseInt(String.valueOf(value));
        } catch (Exception e) {
            return fallback;
        }
    }

    private static long asLong(Object value, long fallback) {
        if (value instanceof Number) {
            return ((Number) value).longValue();
        }
        try {
            return Long.parseLong(String.valueOf(value));
        } catch (Exception e) {
            return fallback;
        }
    }

    private static boolean asBool(Object value, boolean fallback) {
        if (value instanceof Boolean) {
            return (Boolean) value;
        }
        if (value == null) {
            return fallback;
        }
        return Boolean.parseBoolean(String.valueOf(value));
    }

    private static String statKey(String domain, String db, String collection, String field) {
        return domain + "/" + db + "/" + collection + "/" + field;
    }

    private static void switchContext(String domain, String db) {
        if (domain == null || domain.isEmpty() || db == null || db.isEmpty()) {
            return;
        }
        try {
            VDB.setDomain(domain);
            VDB.useDatabase(db);
        } catch (Exception ignored) {
        }
    }

    private static void printRecommendations(List<Map<String, Object>> recs) {
        System.out.println("Index advisor recommendations:");
        for (Map<String, Object> rec : recs) {
            System.out.println("  - " + rec.get("collection") + "." + rec.get("field")
                    + " (eq_queries=" + asInt(rec.get("eq_queries"), 0)
                    + ", avg_scan_ratio=" + String.format(Locale.ROOT, "%.2f", asDouble(rec.get("avg_scan_ratio"), 1.0d))
                    + ")");
        }
    }

    private static Policy loadPolicy() {
        Map<String, Object> raw = readStructuredMap(DirectoryUtil.INDEX_ADVISOR_POLICY);
        Policy p = new Policy();
        p.mode = String.valueOf(raw.getOrDefault("mode", "manual")).toLowerCase(Locale.ROOT);
        if (!"auto".equals(p.mode) && !"manual".equals(p.mode) && !"off".equals(p.mode)) {
            p.mode = "manual";
        }
        p.minQueries = asInt(raw.get("min_queries"), DEFAULT_MIN_QUERIES);
        p.minScanRatio = asDouble(raw.get("min_scan_ratio"), DEFAULT_MIN_SCAN_RATIO);
        p.updatedAt = asLong(raw.get("updated_at"), 0L);
        return p;
    }

    private static void savePolicy(Policy p) {
        p.updatedAt = System.currentTimeMillis();
        writeStructuredMap(DirectoryUtil.INDEX_ADVISOR_POLICY, p.toMap());
    }

    private static final class Policy {
        String mode = "manual";
        int minQueries = DEFAULT_MIN_QUERIES;
        double minScanRatio = DEFAULT_MIN_SCAN_RATIO;
        long updatedAt = 0L;

        Map<String, Object> toMap() {
            Map<String, Object> out = new LinkedHashMap<>();
            out.put("mode", mode);
            out.put("min_queries", minQueries);
            out.put("min_scan_ratio", minScanRatio);
            out.put("updated_at", updatedAt);
            return out;
        }
    }
}
