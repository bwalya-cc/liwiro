// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import verun.runtime.modules.JsonXml;

import java.util.List;
import java.util.Map;
import java.util.StringJoiner;

public final class ValueFormatter {
    private ValueFormatter() {
    }

    public static String toDisplayString(Object value) {
        if (value instanceof MutableValue) {
            return toDisplayString(((MutableValue) value).value);
        }
        if (value == null) {
            return "null";
        }
        if (value instanceof String) {
            return (String) value;
        }
        if (value instanceof EntryValue) {
            EntryValue entry = (EntryValue) value;
            return toDisplayString(entry.key()) + ":" + toDisplayString(entry.value());
        }
        if (value instanceof VersaEnumMemberValue || value instanceof VersaEnumValue) {
            return value.toString();
        }
        if (value instanceof Map.Entry) {
            Map.Entry<?, ?> entry = (Map.Entry<?, ?>) value;
            return toDisplayString(entry.getKey()) + ":" + toDisplayString(entry.getValue());
        }
        if (value instanceof java.util.Set) {
            StringJoiner joiner = new StringJoiner(", ", "{", "}");
            for (Object item : (java.util.Set<?>) value) {
                joiner.add(toDisplayString(item));
            }
            return joiner.toString();
        }
        if (value instanceof Map) {
            if (looksLikeXmlObject((Map<?, ?>) value)) {
                try {
                    return JsonXml.objToXml(value, "root");
                } catch (RuntimeException ignored) {
                    // Fall through to object formatting if XML reconstruction fails.
                }
            }
            StringJoiner joiner = new StringJoiner(", ", "{", "}");
            for (Map.Entry<?, ?> entry : ((Map<?, ?>) value).entrySet()) {
                joiner.add(toDisplayString(entry.getKey()) + ":" + toDisplayString(entry.getValue()));
            }
            return joiner.toString();
        }
        if (value instanceof List) {
            StringJoiner joiner = new StringJoiner(", ", "[", "]");
            for (Object item : (List<?>) value) {
                joiner.add(toDisplayString(item));
            }
            return joiner.toString();
        }
        return String.valueOf(value);
    }

    private static boolean looksLikeXmlObject(Map<?, ?> map) {
        Object root = map.get("root");
        if (!(root instanceof Map<?, ?>)) {
            return false;
        }
        Map<?, ?> rootMap = (Map<?, ?>) root;
        return rootMap.containsKey("name")
                && rootMap.containsKey("attributes")
                && rootMap.containsKey("children")
                && rootMap.containsKey("text");
    }
}
