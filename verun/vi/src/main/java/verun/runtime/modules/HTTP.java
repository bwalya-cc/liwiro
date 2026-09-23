// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.modules;

import java.io.UnsupportedEncodingException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;

public class HTTP {
    private static final HttpClient client = HttpClient.newBuilder()
            .followRedirects(HttpClient.Redirect.NORMAL)
            .build();

    public static CompletableFuture<Map<String, Object>> request(String method, String url, Map<String, Object> options) {
        RequestConfig cfg = buildConfig(method, url, options);
        HttpRequest request = buildRequest(cfg);
        return client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .thenApply(resp -> toResponseMap(cfg, resp));
    }

    public static Map<String, Object> requestSync(String method, String url, Map<String, Object> options) {
        try {
            return request(method, url, options).join();
        } catch (Exception e) {
            throw new RuntimeException("HTTP request failed: " + rootMessage(e));
        }
    }

    public static Map<String, Object> getSync(String url, Map<String, Object> options) {
        return requestSync("GET", url, options);
    }

    public static Map<String, Object> postSync(String url, Map<String, Object> options) {
        return requestSync("POST", url, options);
    }

    public static Map<String, Object> putSync(String url, Map<String, Object> options) {
        return requestSync("PUT", url, options);
    }

    public static Map<String, Object> patchSync(String url, Map<String, Object> options) {
        return requestSync("PATCH", url, options);
    }

    public static Map<String, Object> deleteSync(String url, Map<String, Object> options) {
        return requestSync("DELETE", url, options);
    }

    private static HttpRequest buildRequest(RequestConfig cfg) {
        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(cfg.url))
                .timeout(Duration.ofSeconds(cfg.timeoutSeconds));

        for (Map.Entry<String, String> header : cfg.headers.entrySet()) {
            builder.header(header.getKey(), header.getValue());
        }

        String method = cfg.method;
        String body = cfg.body;
        if ("GET".equals(method) || "HEAD".equals(method)) {
            if ("HEAD".equals(method)) {
                builder.method("HEAD", HttpRequest.BodyPublishers.noBody());
            } else {
                builder.GET();
            }
            return builder.build();
        }
        if (body == null) {
            if (cfg.bodyBytes == null) {
                builder.method(method, HttpRequest.BodyPublishers.noBody());
            } else {
                builder.method(method, HttpRequest.BodyPublishers.ofByteArray(cfg.bodyBytes));
            }
        } else {
            builder.method(method, HttpRequest.BodyPublishers.ofString(body));
        }
        return builder.build();
    }

    private static RequestConfig buildConfig(String method, String url, Map<String, Object> options) {
        String normalizedMethod = String.valueOf(method == null ? "GET" : method).trim().toUpperCase();
        if (normalizedMethod.isEmpty()) {
            normalizedMethod = "GET";
        }
        String inputUrl = String.valueOf(url == null ? "" : url).trim();
        if (inputUrl.isEmpty()) {
            throw new RuntimeException("HTTP url is required");
        }
        Map<String, Object> opts = options == null ? Collections.emptyMap() : options;

        Map<String, String> headers = new LinkedHashMap<>();
        Object rawHeaders = opts.get("headers");
        if (rawHeaders instanceof Map<?, ?>) {
            for (Map.Entry<?, ?> entry : ((Map<?, ?>) rawHeaders).entrySet()) {
                if (entry.getKey() == null || entry.getValue() == null) {
                    continue;
                }
                headers.put(String.valueOf(entry.getKey()), String.valueOf(entry.getValue()));
            }
        }
        Map<String, Object> queryMap = toStringObjectMap(opts.get("query"));
        applyAuth(opts, headers, queryMap);

        String finalUrl = withQueryString(inputUrl, queryMap);
        String body = null;
        byte[] bodyBytes = null;
        Map<String, Object> form = toStringObjectMap(opts.get("form"));
        if (!form.isEmpty()) {
            body = toFormUrlEncoded(form);
            if (!headers.containsKey("Content-Type")) {
                headers.put("Content-Type", "application/x-www-form-urlencoded");
            }
        } else {
            bodyBytes = decodeBase64Body(opts.get("bodyBytesBase64"));
            if (bodyBytes == null) {
                body = stringifyBody(opts.get("body"));
            } else if (!headers.containsKey("Content-Type")) {
                headers.put("Content-Type", "application/octet-stream");
            }
        }
        if (body != null && !headers.containsKey("Content-Type")) {
            headers.put("Content-Type", "application/json");
        }

        int timeoutSeconds = 20;
        Object timeoutRaw = opts.get("timeoutSeconds");
        if (timeoutRaw instanceof Number) {
            timeoutSeconds = Math.max(1, ((Number) timeoutRaw).intValue());
        } else if (timeoutRaw != null) {
            timeoutSeconds = Math.max(1, Integer.parseInt(String.valueOf(timeoutRaw)));
        }

        return new RequestConfig(normalizedMethod, finalUrl, headers, body, bodyBytes, timeoutSeconds);
    }

    private static void applyAuth(Map<String, Object> opts, Map<String, String> headers, Map<String, Object> queryMap) {
        putAuthorizationIfAbsent(headers, asNonBlank(opts.get("authHeader")));

        String bearer = asNonBlank(opts.get("authBearer"));
        if (bearer == null) {
            bearer = asNonBlank(opts.get("authToken"));
        }
        if (bearer != null) {
            putAuthorizationIfAbsent(headers, "Bearer " + bearer);
        }

        applyBasicAuth(opts.get("authBasic"), headers);
        applyOAuth2Auth(opts.get("authOAuth2"), headers);
        applyApiKeyAuth(opts.get("authApiKey"), headers, queryMap);
        applyDigestAuth(opts.get("authDigest"), headers);
        applyGenericAuth(opts.get("auth"), headers, queryMap);
    }

    private static void applyGenericAuth(Object rawAuth, Map<String, String> headers, Map<String, Object> queryMap) {
        if (rawAuth == null) {
            return;
        }
        if (rawAuth instanceof String) {
            putAuthorizationIfAbsent(headers, asNonBlank(rawAuth));
            return;
        }
        Map<String, Object> auth = toStringObjectMap(rawAuth);
        String type = String.valueOf(auth.getOrDefault("type", "")).trim().toLowerCase();
        switch (type) {
            case "bearer":
                String token = asNonBlank(auth.get("token"));
                if (token != null) {
                    putAuthorizationIfAbsent(headers, "Bearer " + token);
                }
                return;
            case "basic":
                applyBasicAuth(auth, headers);
                return;
            case "oauth2":
                applyOAuth2Auth(auth, headers);
                return;
            case "apikey":
            case "api_key":
                applyApiKeyAuth(auth, headers, queryMap);
                return;
            case "digest":
                applyDigestAuth(auth, headers);
                return;
            case "header":
            case "custom":
                String value = asNonBlank(auth.get("value"));
                if (value != null) {
                    putAuthorizationIfAbsent(headers, value);
                }
                return;
            default:
                String fallback = asNonBlank(auth.get("value"));
                if (fallback != null) {
                    putAuthorizationIfAbsent(headers, fallback);
                }
        }
    }

    private static void applyBasicAuth(Object raw, Map<String, String> headers) {
        Map<String, Object> auth = toStringObjectMap(raw);
        if (auth.isEmpty()) {
            return;
        }
        String username = asNonBlank(auth.get("username"));
        String password = asNonBlank(auth.get("password"));
        if (username == null || password == null) {
            return;
        }
        String encoded = Base64.getEncoder()
                .encodeToString((username + ":" + password).getBytes(StandardCharsets.UTF_8));
        putAuthorizationIfAbsent(headers, "Basic " + encoded);
    }

    private static void applyOAuth2Auth(Object raw, Map<String, String> headers) {
        Map<String, Object> auth = toStringObjectMap(raw);
        if (auth.isEmpty()) {
            return;
        }
        String token = asNonBlank(auth.get("accessToken"));
        if (token == null) {
            token = asNonBlank(auth.get("token"));
        }
        if (token == null) {
            return;
        }
        String tokenType = asNonBlank(auth.get("tokenType"));
        if (tokenType == null) {
            tokenType = "Bearer";
        }
        putAuthorizationIfAbsent(headers, tokenType + " " + token);
    }

    private static void applyApiKeyAuth(Object raw, Map<String, String> headers, Map<String, Object> queryMap) {
        Map<String, Object> auth = toStringObjectMap(raw);
        if (auth.isEmpty()) {
            return;
        }
        String value = asNonBlank(auth.get("value"));
        if (value == null) {
            value = asNonBlank(auth.get("apiKey"));
        }
        if (value == null) {
            return;
        }
        String name = asNonBlank(auth.get("name"));
        if (name == null) {
            name = "X-API-Key";
        }
        String prefix = asNonBlank(auth.get("prefix"));
        String in = String.valueOf(auth.getOrDefault("in", "header")).trim().toLowerCase();
        String finalValue = prefix == null ? value : (prefix + value);

        if ("query".equals(in)) {
            queryMap.put(name, finalValue);
        } else {
            headers.putIfAbsent(name, finalValue);
        }
    }

    private static void applyDigestAuth(Object raw, Map<String, String> headers) {
        if (raw == null) {
            return;
        }
        if (raw instanceof String) {
            String value = asNonBlank(raw);
            if (value != null) {
                putAuthorizationIfAbsent(headers, value.startsWith("Digest ") ? value : "Digest " + value);
            }
            return;
        }
        Map<String, Object> auth = toStringObjectMap(raw);
        String value = asNonBlank(auth.get("value"));
        if (value != null) {
            putAuthorizationIfAbsent(headers, value.startsWith("Digest ") ? value : "Digest " + value);
        }
    }

    private static void putAuthorizationIfAbsent(Map<String, String> headers, String authHeader) {
        if (authHeader == null || authHeader.isEmpty()) {
            return;
        }
        if (!headers.containsKey("Authorization")) {
            headers.put("Authorization", authHeader);
        }
    }

    private static String asNonBlank(Object value) {
        if (value == null) {
            return null;
        }
        String text = String.valueOf(value).trim();
        return text.isEmpty() ? null : text;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> toStringObjectMap(Object value) {
        if (!(value instanceof Map<?, ?>)) {
            return new LinkedHashMap<>();
        }
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : ((Map<?, ?>) value).entrySet()) {
            if (entry.getKey() == null) {
                continue;
            }
            result.put(String.valueOf(entry.getKey()), entry.getValue());
        }
        return result;
    }

    private static Map<String, Object> toResponseMap(RequestConfig cfg, HttpResponse<String> response) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("ok", response.statusCode() >= 200 && response.statusCode() < 300);
        out.put("status", response.statusCode());
        out.put("method", cfg.method);
        out.put("url", cfg.url);
        out.put("body", response.body());

        Map<String, Object> headers = new LinkedHashMap<>();
        response.headers().map().forEach((k, v) -> {
            if (v == null || v.isEmpty()) {
                headers.put(k, "");
                return;
            }
            if (v.size() == 1) {
                headers.put(k, v.get(0));
            } else {
                headers.put(k, v);
            }
        });
        out.put("headers", headers);
        return out;
    }

    private static String stringifyBody(Object body) {
        if (body == null) {
            return null;
        }
        if (body instanceof String) {
            return (String) body;
        }
        if (body instanceof Number || body instanceof Boolean) {
            return String.valueOf(body);
        }
        if (body instanceof Map<?, ?> || body instanceof List<?>) {
            return toJson(body);
        }
        return String.valueOf(body);
    }

    private static byte[] decodeBase64Body(Object rawValue) {
        if (rawValue == null) {
            return null;
        }
        String text = String.valueOf(rawValue).trim();
        if (text.isEmpty()) {
            return null;
        }
        try {
            return Base64.getDecoder().decode(text);
        } catch (Exception e) {
            throw new RuntimeException("HTTP bodyBytesBase64 must be valid base64");
        }
    }

    private static String toFormUrlEncoded(Map<String, Object> formValues) {
        if (formValues == null || formValues.isEmpty()) {
            return "";
        }
        StringBuilder encoded = new StringBuilder();
        for (Map.Entry<String, Object> entry : formValues.entrySet()) {
            if (entry.getKey() == null || entry.getValue() == null) {
                continue;
            }
            if (encoded.length() > 0) {
                encoded.append("&");
            }
            encoded.append(urlEncode(String.valueOf(entry.getKey())));
            encoded.append("=");
            encoded.append(urlEncode(formValueToString(entry.getValue())));
        }
        return encoded.toString();
    }

    private static String formValueToString(Object value) {
        if (value == null) {
            return "";
        }
        if (value instanceof Map<?, ?> || value instanceof List<?>) {
            return toJson(value);
        }
        return String.valueOf(value);
    }

    private static String withQueryString(String url, Map<String, Object> queryValues) {
        if (queryValues == null || queryValues.isEmpty()) {
            return url;
        }
        StringBuilder query = new StringBuilder();
        for (Map.Entry<String, Object> entry : queryValues.entrySet()) {
            if (entry.getKey() == null || entry.getValue() == null) {
                continue;
            }
            if (query.length() > 0) {
                query.append("&");
            }
            query.append(urlEncode(String.valueOf(entry.getKey())));
            query.append("=");
            query.append(urlEncode(String.valueOf(entry.getValue())));
        }
        if (query.length() == 0) {
            return url;
        }
        String delimiter = url.contains("?") ? "&" : "?";
        return url + delimiter + query;
    }

    private static String urlEncode(String value) {
        try {
            return URLEncoder.encode(value, StandardCharsets.UTF_8.toString());
        } catch (UnsupportedEncodingException e) {
            throw new RuntimeException("Failed to encode URL value");
        }
    }

    private static String rootMessage(Throwable throwable) {
        Throwable cursor = throwable;
        while (cursor.getCause() != null) {
            cursor = cursor.getCause();
        }
        return cursor.getMessage() == null ? cursor.toString() : cursor.getMessage();
    }

    @SuppressWarnings("unchecked")
    private static String toJson(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof String) {
            return "\"" + escapeJson((String) value) + "\"";
        }
        if (value instanceof Number || value instanceof Boolean) {
            return String.valueOf(value);
        }
        if (value instanceof Map<?, ?>) {
            StringBuilder builder = new StringBuilder();
            builder.append("{");
            boolean first = true;
            for (Map.Entry<?, ?> entry : ((Map<?, ?>) value).entrySet()) {
                if (!first) {
                    builder.append(",");
                }
                first = false;
                builder.append("\"").append(escapeJson(String.valueOf(entry.getKey()))).append("\":");
                builder.append(toJson(entry.getValue()));
            }
            builder.append("}");
            return builder.toString();
        }
        if (value instanceof List<?>) {
            StringBuilder builder = new StringBuilder();
            builder.append("[");
            boolean first = true;
            for (Object item : (List<Object>) value) {
                if (!first) {
                    builder.append(",");
                }
                first = false;
                builder.append(toJson(item));
            }
            builder.append("]");
            return builder.toString();
        }
        return "\"" + escapeJson(String.valueOf(value)) + "\"";
    }

    private static String escapeJson(String text) {
        String escaped = text.replace("\\", "\\\\");
        escaped = escaped.replace("\"", "\\\"");
        escaped = escaped.replace("\n", "\\n");
        escaped = escaped.replace("\r", "\\r");
        return escaped.replace("\t", "\\t");
    }

    private static class RequestConfig {
        final String method;
        final String url;
        final Map<String, String> headers;
        final String body;
        final byte[] bodyBytes;
        final int timeoutSeconds;

        RequestConfig(String method, String url, Map<String, String> headers, String body, byte[] bodyBytes, int timeoutSeconds) {
            this.method = method;
            this.url = url;
            this.headers = headers;
            this.body = body;
            this.bodyBytes = bodyBytes;
            this.timeoutSeconds = timeoutSeconds;
        }
    }
}
