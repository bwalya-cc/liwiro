// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

final class VdbExceptionTypes {
    static final String BASE = "VDBException";
    static final String AUTH = "VDBAuthenticationException";
    static final String NOT_AUTHENTICATED = "VDBNotAuthenticatedException";
    static final String PERMISSION = "VDBPermissionException";
    static final String VALIDATION = "VDBValidationException";
    static final String NOT_FOUND = "VDBNotFoundException";
    static final String OPERATION = "VDBOperationException";

    private VdbExceptionTypes() {
    }

    static String normalizeType(String rawType) {
        String type = String.valueOf(rawType == null ? "" : rawType).trim();
        if (type.isEmpty()) {
            return "RuntimeError";
        }
        switch (type) {
            case "VDBAuthenticationError":
                return AUTH;
            case "VDBPermissionError":
                return PERMISSION;
            case "VDBValidationError":
                return VALIDATION;
            case "VDBNotFoundError":
                return NOT_FOUND;
            case "VDBOperationError":
                return OPERATION;
            default:
                return type;
        }
    }

    static String aliasFor(String rawType) {
        String type = normalizeType(rawType);
        if (AUTH.equals(type)) {
            return BASE + ".AuthError";
        }
        if (NOT_AUTHENTICATED.equals(type)) {
            return BASE + ".NotAuthenticated";
        }
        if (PERMISSION.equals(type)) {
            return BASE + ".PermissionError";
        }
        if (VALIDATION.equals(type)) {
            return BASE + ".ValidationError";
        }
        if (NOT_FOUND.equals(type)) {
            return BASE + ".NotFound";
        }
        if (OPERATION.equals(type)) {
            return BASE + ".OperationError";
        }
        return type.startsWith("VDB") ? BASE + ".Error" : "";
    }

    static String codeFor(String rawType) {
        String alias = aliasFor(rawType);
        int dotIndex = alias.lastIndexOf('.');
        if (dotIndex >= 0 && dotIndex + 1 < alias.length()) {
            return alias.substring(dotIndex + 1);
        }
        return "";
    }

    static String baseFor(String rawType) {
        String type = normalizeType(rawType);
        return type.startsWith("VDB") ? BASE : "";
    }

    static Map<String, Object> metadataFor(String rawType) {
        Map<String, Object> out = new LinkedHashMap<>();
        String type = normalizeType(rawType);
        String base = baseFor(type);
        String alias = aliasFor(type);
        String code = codeFor(type);
        out.put("type", type);
        out.put("base_type", base);
        out.put("baseType", base);
        out.put("type_alias", alias);
        out.put("typeAlias", alias);
        out.put("type_code", code);
        out.put("typeCode", code);
        return out;
    }

    static String inferFromMessage(String message) {
        String msg = String.valueOf(message == null ? "" : message).toLowerCase(Locale.ROOT);
        if (msg.contains("permission denied")) {
            return PERMISSION;
        }
        if (msg.contains("not authenticated")) {
            return NOT_AUTHENTICATED;
        }
        if (msg.contains("vdb.auth") || msg.contains("authentication") || msg.contains("wrong password")
                || msg.contains("unknown vdb user") || msg.contains("no vdb users configured")) {
            return AUTH;
        }
        return OPERATION;
    }
}
