// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import verun.runtime.ast.Node;
import verun.runtime.ast.ParameterNode;
import java.util.List;
import java.util.ArrayList;
import java.util.Map;
import java.util.HashMap;

public class LambdaFunction implements Callable {
    private final List<ParameterNode> parameters;
    private final Node body;
    private final Evaluator evaluator;
    private final Map<String, Object> capturedEnvironment;
    
    public LambdaFunction(List<ParameterNode> parameters, Node body, Evaluator evaluator) {
        this.parameters = parameters;
        this.body = body;
        this.evaluator = evaluator;
        // Capture the current environment for closure
        this.capturedEnvironment = new HashMap<>(evaluator.getEnvironment());
    }
    
    @Override
    public Object call(List<Object> arguments) {
        // Save the current environment
        Map<String, Object> savedEnvironment = new HashMap<>(evaluator.getEnvironment());
        
        try {
            // Clear and restore captured environment
            evaluator.getEnvironment().clear();
            evaluator.getEnvironment().putAll(capturedEnvironment);
            
            // Bind parameters to arguments
            for (int i = 0; i < parameters.size() && i < arguments.size(); i++) {
                String paramName = parameters.get(i).name;
                evaluator.getEnvironment().put(paramName, arguments.get(i));
            }
            
            // Evaluate the lambda body
            try {
                return evaluator.evaluate(body);
            } catch (ReturnException ret) {
                return ret.value;
            }
        } finally {
            // Restore the original environment
            evaluator.getEnvironment().clear();
            evaluator.getEnvironment().putAll(savedEnvironment);
        }
    }
}
