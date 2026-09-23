// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.common;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.JsonPrimitive;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class JsonValueConverter {
    private static final Gson DEFAULT_GSON = new Gson();

    private JsonValueConverter() {
    }

    public static Object fromJson(String json) {
        return fromJsonElement(JsonParser.parseString(String.valueOf(json == null ? "null" : json)));
    }

    public static Object fromJsonElement(JsonElement element) {
        if (element == null || element.isJsonNull()) {
            return null;
        }
        if (element.isJsonObject()) {
            Map<String, Object> out = new LinkedHashMap<>();
            for (Map.Entry<String, JsonElement> entry : element.getAsJsonObject().entrySet()) {
                out.put(entry.getKey(), fromJsonElement(entry.getValue()));
            }
            return out;
        }
        if (element.isJsonArray()) {
            List<Object> out = new ArrayList<>();
            for (JsonElement item : element.getAsJsonArray()) {
                out.add(fromJsonElement(item));
            }
            return out;
        }
        if (element.isJsonPrimitive()) {
            return fromPrimitive(element.getAsJsonPrimitive());
        }
        return null;
    }

    @SuppressWarnings("unchecked")
    public static Map<String, Object> toObjectMap(JsonObject object) {
        Object value = fromJsonElement(object);
        if (value instanceof Map<?, ?>) {
            return new LinkedHashMap<>((Map<String, Object>) value);
        }
        return new LinkedHashMap<>();
    }

    @SuppressWarnings("unchecked")
    public static List<Object> toObjectList(JsonArray array) {
        Object value = fromJsonElement(array);
        if (value instanceof List<?>) {
            return new ArrayList<>((List<Object>) value);
        }
        return new ArrayList<>();
    }

    public static Object convertViaJson(Object value) {
        return convertViaJson(DEFAULT_GSON, value);
    }

    public static Object convertViaJson(Gson gson, Object value) {
        Gson effective = gson == null ? DEFAULT_GSON : gson;
        return fromJsonElement(effective.toJsonTree(value));
    }

    public static Object coerceStringScalar(String raw) {
        String text = raw == null ? "" : raw.trim();
        if (text.isEmpty()) {
            return "";
        }
        if ("true".equalsIgnoreCase(text)) {
            return true;
        }
        if ("false".equalsIgnoreCase(text)) {
            return false;
        }
        if ("null".equalsIgnoreCase(text)) {
            return null;
        }
        if (looksLikeNumber(text)) {
            return normalizeNumber(text);
        }
        return text;
    }

    public static Number normalizeNumber(String raw) {
        String text = raw == null ? "0" : raw.trim();
        if (text.indexOf('.') >= 0 || text.indexOf('e') >= 0 || text.indexOf('E') >= 0) {
            return Double.valueOf(text);
        }
        try {
            return Integer.valueOf(text);
        } catch (NumberFormatException ignored) {
        }
        try {
            return Long.valueOf(text);
        } catch (NumberFormatException ignored) {
        }
        return Double.valueOf(text);
    }

    private static Object fromPrimitive(JsonPrimitive primitive) {
        if (primitive.isBoolean()) {
            return primitive.getAsBoolean();
        }
        if (primitive.isString()) {
            return primitive.getAsString();
        }
        if (primitive.isNumber()) {
            return normalizeNumber(primitive.getAsString());
        }
        return primitive.getAsString();
    }

    private static boolean looksLikeNumber(String text) {
        return text.matches("-?(0|[1-9]\\d*)(\\.\\d+)?([eE][+-]?\\d+)?");
    }
}
