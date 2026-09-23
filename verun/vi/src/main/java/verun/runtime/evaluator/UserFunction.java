// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import verun.runtime.ast.Node;
import verun.runtime.ast.ParameterNode;
import verun.runtime.lexer.Token;
import java.util.List;
import java.util.Map;
import java.util.HashMap;

public class UserFunction implements Callable {
    private final List<ParameterNode> parameters;
    private final Map<String, Object> environment;
    private final Node body;
    private final List<Token> sourceTokens;
    private final String sourceText;

    public UserFunction(List<ParameterNode> parameters, Map<String, Object> environment, Node body) {
        this(parameters, environment, body, null, null);
    }

    public UserFunction(List<ParameterNode> parameters, Map<String, Object> environment, Node body,
            List<Token> sourceTokens, String sourceText) {
        this.parameters = parameters;
        this.environment = environment;
        this.body = body;
        this.sourceTokens = sourceTokens;
        this.sourceText = sourceText;
    }

    @Override
    public Object call(List<Object> args) {
        return callWithBindings(args, null);
    }

    public Object callWithBindings(List<Object> args, Map<String, Object> extraBindings) {
        // Use a per-call scope so recursive/nested calls do not overwrite shared closure values.
        Map<String, Object> callEnv = new HashMap<>(environment);
        if (extraBindings != null && !extraBindings.isEmpty()) {
            callEnv.putAll(extraBindings);
        }
        EvaluationContext callContext;
        if (sourceTokens != null && sourceText != null) {
            callContext = new EvaluationContext(sourceTokens, sourceText);
            callContext.getEnvironment().putAll(callEnv);
        } else {
            callContext = new EvaluationContext(callEnv);
        }
        Evaluator evaluator = new Evaluator(callContext);

        // Bind arguments and defaults to parameters.
        for (int i = 0; i < parameters.size(); i++) {
            ParameterNode parameter = parameters.get(i);
            String paramName = parameter.name;
            Object value;
            if (i < args.size()) {
                value = args.get(i);
            } else if (parameter.defaultValue != null) {
                value = evaluator.evaluate(parameter.defaultValue);
            } else {
                value = null;
            }
            evaluator.assertTypeCompatibility(value, parameter.type, "Type mismatch for parameter '" + paramName + "'");
            evaluator.getEnvironment().put(paramName, new MutableValue(value, parameter.type));
        }

        try {
            return evaluator.evaluate(body);
        } catch (ReturnException ret) {
            return ret.value;
        }
    }

    public List<ParameterNode> getParameters() {
        return parameters;
    }

    public Map<String, Object> getEnvironment() {
        return environment;
    }

    public Node getBody() {
        return body;
    }
}
