// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import verun.runtime.ast.ElseIfClauseNode;
import verun.runtime.ast.IfStatementNode;
import verun.runtime.ast.WhileLoopNode;

public class ControlFlowEvaluator {
    
    public static Object evaluateIf(IfStatementNode node, Evaluator evaluator) {
        // Evaluate main condition
        Object conditionResult = evaluator.evaluate(node.condition);
        if (conditionResult != null && !conditionResult.equals(false)) {
            return evaluator.evaluate(node.thenBranch);
        }
        
        // Check 'alt' clauses
        for (ElseIfClauseNode altClause : node.altClauses) {
            Object altConditionResult = evaluator.evaluate(altClause.condition);
            if (altConditionResult != null && !altConditionResult.equals(false)) {
                return evaluator.evaluate(altClause.body);
            }
        }
        // Handle 'else' clause
        if (node.elseBranch != null) {
            return evaluator.evaluate(node.elseBranch);
        }
        
        return null;
    }

    public static Object evaluateWhile(WhileLoopNode node, Evaluator evaluator) {
        Object result = null;
        while (Evaluator.isTruthy(evaluator.evaluate(node.condition))) {
            try {
                result = evaluator.evaluate(node.body);
            } catch (Evaluator.BreakException be) {
                break;
            } catch (Evaluator.ContinueException ce) {
                continue;
            }
        }
        return result;
    }
    
    public static Object evaluateForLoop(verun.runtime.ast.ForLoopNode node, Evaluator evaluator) {
        Object result = null;
        evaluator.evaluate(node.initializer);
        while (true) {
            if (node.condition != null) {
                if (!Evaluator.isTruthy(evaluator.evaluate(node.condition))) {
                    break;
                }
            }
            result = evaluator.evaluate(node.body);
            if (node.increment != null) {
                evaluator.evaluate(node.increment);
            }
        }
        return result;
    }
}