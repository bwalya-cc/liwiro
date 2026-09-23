// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import verun.runtime.ast.CallExpressionNode;
import verun.runtime.ast.Node;
import verun.runtime.ast.BlockNode;
import verun.runtime.ast.IndexAccessNode;
import verun.runtime.ast.IdentifierNode;
import verun.runtime.ast.ReturnStatementNode;
import java.util.ArrayList;
import java.util.List;

public class FunctionEvaluator {
    public interface CallableValue {
        Object call(EvaluationContext context, List<Object> args);
    }

    public static class Lambda implements CallableValue {
        private final List<String> parameters;
        private final Node body;
        private final EvaluationContext closure;

        // Constructor that takes parameters, body, and closure
        public Lambda(List<String> params, Node body, EvaluationContext closure) {
            this.parameters = params;
            this.body = body;
            this.closure = closure;
        }

        // Overloaded constructor that creates a new closure context
        public Lambda(List<String> params, Node body) {
            this(params, body, new EvaluationContext());
        }

        @Override
        public Object call(EvaluationContext context, List<Object> args) {
            EvaluationContext lambdaContext = new EvaluationContext(this.closure);
            
            // Bind arguments to parameters
            for (int i = 0; i < parameters.size(); i++) {
                String paramName = parameters.get(i);
                Object argValue = i < args.size() ? args.get(i) : null;
                lambdaContext.declare(paramName, argValue);
            }
            
            return new Evaluator(lambdaContext).evaluate(body);
        }

        public Object apply(List<Object> args) {
            return call(new EvaluationContext(), args); // Use default context if none provided
        }
    }

    public static Object callFunction(CallExpressionNode node, Evaluator evaluator) {
        Object callee = evaluator.evaluate(node.getCallee());
        List<Object> args = new ArrayList<>();
        
        for (Node arg : node.getArguments()) {
            args.add(evaluator.evaluate(arg));
        }
        
        if (callee instanceof CallableValue) {
            return ((CallableValue) callee).call(evaluator.getCurrentContext(), args);
        }
        
        throw new EvaluationException("Attempt to call non-function value [in FunctionEvaluator]: " + callee);
    }
}