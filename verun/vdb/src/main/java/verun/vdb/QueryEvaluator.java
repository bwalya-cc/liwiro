// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import java.util.*;
import java.util.stream.Collectors;

public class QueryEvaluator {
    /** Evaluate the native typed Versa predicate without a Mongo-style query object. */
    public static boolean matches(Map<String, Object> doc, VDBCommand.Expression predicate) {
        return predicate == null || VDBCommand.truthy(predicate.evaluate(doc, Collections.emptyMap()));
    }

    public static boolean matches(Map<String, Object> doc, Map<String, Object> query) {
        for (Map.Entry<String, Object> entry : query.entrySet()) {
            String key = entry.getKey();
            Object condition = entry.getValue();

            if (key.startsWith("$")) {
                if (!evaluateLogicalOperator(doc, key, condition)) {
                    return false;
                }
            } else {
                if (!evaluateField(doc, key, condition)) {
                    return false;
                }
            }
        }
        return true;
    }

    private static boolean evaluateLogicalOperator(Map<String, Object> doc, String operator, Object conditions) {
        switch (operator) {
            case "$and":
                for (Map<String, Object> cond : (List<Map<String, Object>>) conditions) {
                    if (!matches(doc, cond)) {
                        return false;
                    }
                }
                return true;
            case "$or":
                for (Map<String, Object> cond : (List<Map<String, Object>>) conditions) {
                    if (matches(doc, cond)) {
                        return true;
                    }
                }
                return false;
            default:
                throw new RuntimeException("Unsupported operator: " + operator);
        }
    }

    private static boolean evaluateField(Map<String, Object> doc, String field, Object condition) {
        Object value = getNestedField(doc, field);
        
        if (condition instanceof Map) {
            return evaluateOperators(value, (Map<String, Object>) condition);
        } else {
            return Objects.equals(value, condition);
        }
    }

    public static Object getNestedField(Map<String, Object> doc, String field) {
        String[] parts = field.split("\\.");
        Object current = doc;
        for (String part : parts) {
            if (current instanceof Map) {
                current = ((Map<?, ?>) current).get(part);
            } else {
                return null;
            }
        }
        return current;
    }

    private static boolean evaluateOperators(Object value, Map<String, Object> operators) {
        for (Map.Entry<String, Object> entry : operators.entrySet()) {
            String operator = entry.getKey();
            Object operand = entry.getValue();
            if (!evaluateOperator(value, operator, operand)) {
                return false;
            }
        }
        return true;
    }

    private static boolean evaluateOperator(Object value, String operator, Object operand) {
        switch (operator) {
            case "$eq":
                return Objects.equals(value, operand);
            case "$gt":
                return compare(value, operand) > 0;
            case "$lt":
                return compare(value, operand) < 0;
            case "$gte":
                return compare(value, operand) >= 0;
            case "$lte":
                return compare(value, operand) <= 0;
            case "$exists":
                boolean exists = operand instanceof Boolean ? (Boolean) operand : false;
                return (value != null) == exists;
            default:
                throw new RuntimeException("Unsupported operator: " + operator);
        }
    }

    private static int compare(Object a, Object b) {
        if (a instanceof Number && b instanceof Number) {
            double aValue = ((Number) a).doubleValue();
            double bValue = ((Number) b).doubleValue();
            return Double.compare(aValue, bValue);
        }
        if (a instanceof Comparable && b instanceof Comparable) {
            return ((Comparable) a).compareTo(b);
        }
        throw new RuntimeException("Cannot compare " + a + " and " + b);
    }
}
