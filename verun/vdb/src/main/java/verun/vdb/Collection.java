// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import java.util.*;
import java.nio.file.Path;
import java.nio.file.Files;
import java.io.IOException;
import java.util.stream.Collectors;

public class Collection {
    private final String name;
    private final String domain;
    private final String db;

    public Collection(String name) {
        this.name = name;
        this.domain = VDB.getCurrentDomain();
        this.db = VDB.getCurrentDB();
        validateContext();
    }

    public String getName() {
        return name;
    }

    private void validateContext() {
        if (domain == null || domain.isEmpty()) {
            throw new RuntimeException("No active domain context");
        }
        if (db == null || db.isEmpty()) {
            throw new RuntimeException("No active database context");
        }
    }

    public List<Map<String, Object>> find(Map<String, Object> query,
            Map<String, Boolean> projection,
            int limit) {
        if (!VDB.hasPermission("DATA_ACCESS")) {
            throw new RuntimeException("Read permission denied");
        }
        try {
            List<Map<String, Object>> filtered = VDB.find(name,
                    query == null ? Collections.emptyMap() : query,
                    limit);

            if (projection != null && !projection.isEmpty()) {
                return filtered.stream()
                        .map(doc -> applyProjection(doc, projection))
                        .collect(Collectors.toList());
            }

            return filtered;
        } catch (Exception e) {
            throw new RuntimeException("Query failed: " + e.getMessage(), e);
        }
    }

    public List<Map<String, Object>> find(Map<String, Object> query, int limit) {
        return find(query, Collections.emptyMap(), limit);
    }

    private Map<String, Object> applyProjection(Map<String, Object> doc, Map<String, Boolean> projection) {
        if (projection == null || projection.isEmpty())
            return doc;

        Map<String, Object> projected = new HashMap<>();
        projection.forEach((field, include) -> {
            if (Boolean.TRUE.equals(include) && doc.containsKey(field)) {
                projected.put(field, doc.get(field));
            }
        });
        return projected;
    }

    public int delete(Map<String, Object> query) {
        List<Map<String, Object>> docs = find(query, Integer.MAX_VALUE);
        int deletedCount = 0;
        for (Map<String, Object> doc : docs) {
            VDB.delete(this.name, (String) doc.get("_id"));
            deletedCount++;
        }
        return deletedCount;
    }

    private Object getNestedField(Map<String, Object> doc, String field) {
        return QueryEvaluator.getNestedField(doc, field);
    }
}
