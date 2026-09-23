// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

public class VDBTransportRequest {
    private final String method;
    private final String path;
    private final String rawQuery;
    private final Map<String, String> headers;
    private final String body;
    private final String remoteAddress;

    public VDBTransportRequest(
            String method,
            String path,
            String rawQuery,
            Map<String, String> headers,
            String body,
            String remoteAddress) {
        this.method = method == null ? "GET" : method.trim().toUpperCase();
        this.path = path == null || path.trim().isEmpty() ? "/" : path.trim();
        this.rawQuery = rawQuery == null ? "" : rawQuery;
        this.headers = headers == null ? Collections.emptyMap() : Collections.unmodifiableMap(new LinkedHashMap<>(headers));
        this.body = body == null ? "" : body;
        this.remoteAddress = remoteAddress == null ? "" : remoteAddress;
    }

    public String getMethod() {
        return method;
    }

    public String getPath() {
        return path;
    }

    public String getRawQuery() {
        return rawQuery;
    }

    public Map<String, String> getHeaders() {
        return headers;
    }

    public String getBody() {
        return body;
    }

    public String getRemoteAddress() {
        return remoteAddress;
    }

    public String getHeader(String name) {
        if (name == null || name.isEmpty() || headers.isEmpty()) {
            return null;
        }
        for (Map.Entry<String, String> entry : headers.entrySet()) {
            if (name.equalsIgnoreCase(entry.getKey())) {
                return entry.getValue();
            }
        }
        return null;
    }
}
