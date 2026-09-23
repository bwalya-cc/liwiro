// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import verun.runtime.ast.ComprehensionClause;
import verun.runtime.ast.ListComprehensionNode;
import verun.runtime.ast.DictionaryComprehensionNode;
import verun.runtime.ast.Node;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class CollectionEvaluator {
    public static Object evaluateListComprehension(ListComprehensionNode node, Evaluator parent) {
        List<Object> result = new ArrayList<>();
        // Use public getters to access clauses and expression
        evaluateClauses(node.getClauses(), 0, new HashMap<>(parent.getEnvironment()), result, node.getExpression(),
                parent);
        return result;
    }

public static Object evaluateDictComprehension(DictionaryComprehensionNode node, Evaluator parent) {
    Map<Object, Object> result = new java.util.LinkedHashMap<>();
    for (Object item : iterableValues(parent.evaluate(node.iterable), "Dictionary comprehension")) {
        Map<String, Object> newEnv = new HashMap<>(parent.getEnvironment());
        newEnv.put(node.iterator, item);

        if (node.condition != null) {
            Object condition = parent.evaluateInContext(node.condition, newEnv);
            if (!ArithmeticEvaluator.isTruthy(condition)) continue;
        }

        Object key = parent.evaluateInContext(node.keyExpr, newEnv);
        Object value = parent.evaluateInContext(node.valueExpr, newEnv);
        result.put(key, value);
    }
    return result;
}

    private static void evaluateClauses(List<ComprehensionClause> clauses, int index,
            Map<String, Object> env, List<Object> result,
            Node expression, Evaluator parent) {
        if (index >= clauses.size()) {
            result.add(parent.evaluateInContext(expression, env));
            return;
        }

        ComprehensionClause clause = clauses.get(index);
        Object iterObj = parent.evaluateInContext(clause.iterable, env);
        if (iterObj instanceof List || iterObj instanceof java.util.Set
                || iterObj instanceof java.util.Map || iterObj instanceof String) {
            for (Object item : iterableValues(iterObj, "List comprehension")) {
                Map<String, Object> newEnv = new HashMap<>(env);
                newEnv.put(clause.iterator, item);
                if (clause.condition != null) {
                    Object cond = parent.evaluateInContext(clause.condition, newEnv);
                    if (!ArithmeticEvaluator.isTruthy(cond)) {
                        continue;
                    }
                }
                evaluateClauses(clauses, index + 1, newEnv, result, expression, parent);
            }
        } else {
            throw new EvaluationException("List comprehension iterable must be a list, set, map, or string");
        }
    }

    private static List<?> iterableValues(Object value, String label) {
        if (value instanceof List<?>) return (List<?>) value;
        if (value instanceof java.util.Set<?>) return new ArrayList<>((java.util.Set<?>) value);
        if (value instanceof java.util.Map<?, ?>) return new ArrayList<>(((java.util.Map<?, ?>) value).keySet());
        if (value instanceof String) {
            List<String> characters = new ArrayList<>();
            String text = (String) value;
            for (int i = 0; i < text.length(); i++) characters.add(text.substring(i, i + 1));
            return characters;
        }
        throw new EvaluationException(label + " iterable must be a list, set, map, or string");
    }
}
