// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import com.google.gson.JsonObject;
import com.google.gson.JsonElement;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;

public class CommandValidator {
    private static final Set<String> SUPPORTED_ACTIONS = Collections.unmodifiableSet(new LinkedHashSet<>(Arrays.asList(
            "define", "use", "list", "find", "read", "insert", "create", "update", "delete", "drop",
            "aggregate", "create_collection", "drop_collection", "drop_domain", "drop_db",
            "create_index", "drop_index", "list_indexes", "rebuild_indexes", "model_get", "model_delete",
            "script_create", "script_read", "script_execute", "script_delete", "script_list",
            "transaction_begin", "transaction_commit", "transaction_abort", "domain_status",
            "domain_suspend", "domain_resume", "tumi", "help", "context", "whoami", "echo", "export"
    )));

    private static final Set<String> LEGACY_OPERATION_KEYS = Collections.unmodifiableSet(new LinkedHashSet<>(Arrays.asList(
            "tumi", "read", "create", "update", "delete", "list", "drop", "define", "use", "transaction",
            "script", "index", "find", "insert", "aggregate", "create_collection",
            "drop_collection", "drop_domain", "drop_db", "create_index", "drop_index", "list_indexes",
            "rebuild_indexes", "model_get", "model_delete", "script_create", "script_read", "script_execute",
            "script_delete", "script_list", "transaction_begin", "transaction_commit", "transaction_abort",
            "domain_status", "domain_suspend", "domain_resume", "help", "context", "whoami", "echo", "export"
    )));

    static Set<String> supportedActions() {
        return SUPPORTED_ACTIONS;
    }

    public static void validateCommandStructure(JsonObject command) throws IllegalArgumentException {
        if (command.entrySet().isEmpty()) {
            throw new IllegalArgumentException("Empty command");
        }
        
        if (command.has("commands")) {
            if (command.entrySet().size() != 1) {
                throw new IllegalArgumentException("Batch command may contain only the commands array");
            }
            if (!command.get("commands").isJsonArray() || command.getAsJsonArray("commands").size() == 0) {
                throw new IllegalArgumentException("commands must be a non-empty array");
            }
            for (JsonElement item : command.getAsJsonArray("commands")) {
                if (!item.isJsonObject()) throw new IllegalArgumentException("Each batch command must be an object");
                if (item.getAsJsonObject().has("commands")) {
                    throw new IllegalArgumentException("Batch entries must be flat actions");
                }
                validateCommandStructure(item.getAsJsonObject());
            }
            return;
        }
        if (!command.has("action")) {
            throw new IllegalArgumentException("A parsed VDB action is required; nested command envelopes are not supported");
        }
        JsonElement actionElement = command.get("action");
        if (actionElement == null || !actionElement.isJsonPrimitive()
                || !actionElement.getAsJsonPrimitive().isString()
                || actionElement.getAsString().trim().isEmpty()) {
            throw new IllegalArgumentException("action must be a non-empty string");
        }
        for (String nestedKey : LEGACY_OPERATION_KEYS) {
            if (command.has(nestedKey)) {
                throw new IllegalArgumentException(
                        "A parsed VDB action cannot include nested operation key '" + nestedKey + "'");
            }
        }
        String operation = actionElement.getAsString().trim().toLowerCase(Locale.ROOT);
        {
            if (!SUPPORTED_ACTIONS.contains(operation)) {
                throw new IllegalArgumentException("Unsupported action: " + operation);
            }
            if ("help".equals(operation)) {
                validateOptionalString(command, "topic");
                validateOptionalString(command, "section");
                validateOptionalPositiveInteger(command, "page");
                validateOptionalPositiveInteger(command, "page_size");
                validateOptionalPositiveInteger(command, "pageSize");
            }
            if (operation.matches("domain_status|domain_suspend|domain_resume")
                    && ((!command.has("domain") || !command.get("domain").isJsonPrimitive())
                    && (!command.has("name") || !command.get("name").isJsonPrimitive()))) {
                throw new IllegalArgumentException("Action " + operation + " requires domain or name");
            }
            if ("domain_status".equals(operation) && command.has("operation")
                    && (!command.get("operation").isJsonPrimitive()
                    || !command.get("operation").getAsString().matches("(?i)get|status|suspend|resume|activate"))) {
                throw new IllegalArgumentException("Action domain_status operation must be get, status, suspend, resume, or activate");
            }
            if (operation.matches("find|read|insert|update|delete|drop|aggregate|create_collection|drop_collection|create_index|drop_index|list_indexes|rebuild_indexes") &&
                    (!command.has("collection") || !command.get("collection").isJsonPrimitive())) {
                throw new IllegalArgumentException("Action " + operation + " requires collection");
            }
            if (operation.matches("create_index|drop_index") &&
                    (!command.has("field") || !command.get("field").isJsonPrimitive()
                            || command.get("field").getAsString().trim().isEmpty())) {
                throw new IllegalArgumentException("Action " + operation + " requires field");
            }
            if (operation.matches("insert|create")
                    && (!command.has("document") || !command.get("document").isJsonObject())) {
                throw new IllegalArgumentException("Action " + operation + " requires document object");
            }
            if ("update".equals(operation)) {
                boolean hasOperator = false;
                for (String field : new String[]{"set", "inc", "unset"}) {
                    if (command.has(field)) {
                        if (!command.get(field).isJsonObject()) {
                            throw new IllegalArgumentException("Action update field " + field + " must be an object");
                        }
                        hasOperator = true;
                    }
                }
                if (!hasOperator) {
                    throw new IllegalArgumentException("Action update requires set, inc, or unset object");
                }
            }
            if ("list".equals(operation)) {
                if (!command.has("resource") || !command.get("resource").isJsonPrimitive()) {
                    throw new IllegalArgumentException("Action " + operation + " requires resource");
                }
            }
            if (operation.matches("define|use") && !command.has("name") && !command.has("domain") && !command.has("db")) {
                throw new IllegalArgumentException("Action " + operation + " requires name, domain, or db");
            }
            if (operation.matches("model_get|model_delete") && (!command.has("model") || !command.get("model").isJsonPrimitive())) {
                throw new IllegalArgumentException("Action " + operation + " requires model");
            }
            if (operation.matches("script_create|script_read|script_execute|script_delete") && (!command.has("name") || !command.get("name").isJsonPrimitive())) {
                throw new IllegalArgumentException("Action " + operation + " requires name");
            }
            if (operation.matches("transaction_begin|transaction_commit|transaction_abort")) {
                return;
            }
            if ("tumi".equals(operation) && (!command.has("operation") || !command.get("operation").isJsonPrimitive())) {
                throw new IllegalArgumentException("Action tumi requires operation");
            }
            return;
        }
    }

    private static void validateOptionalString(JsonObject command, String field) {
        if (command.has(field) && (!command.get(field).isJsonPrimitive()
                || !command.getAsJsonPrimitive(field).isString())) {
            throw new IllegalArgumentException("Action help field " + field + " must be a string");
        }
    }

    private static void validateOptionalPositiveInteger(JsonObject command, String field) {
        if (!command.has(field)) {
            return;
        }
        JsonElement value = command.get(field);
        if (!value.isJsonPrimitive() || !value.getAsJsonPrimitive().isNumber()) {
            throw new IllegalArgumentException("Action help field " + field + " must be a positive integer");
        }
        try {
            java.math.BigDecimal number = value.getAsBigDecimal().stripTrailingZeros();
            if (number.scale() > 0 || number.signum() <= 0 || number.compareTo(java.math.BigDecimal.valueOf(Integer.MAX_VALUE)) > 0) {
                throw new IllegalArgumentException("Action help field " + field + " must be a positive integer");
            }
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("Action help field " + field + " must be a positive integer");
        }
    }
}
