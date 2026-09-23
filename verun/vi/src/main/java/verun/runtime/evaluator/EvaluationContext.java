// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import verun.runtime.lexer.Token;
import verun.runtime.lexer.TokenType;
import java.util.List;
import java.util.HashMap;
import java.util.Map;

public class EvaluationContext {
    public final List<Token> tokens;
    public int position;
    public final String sourceText;
    public final String[] sourceLines;
    public boolean isInsideFunction = false;
    public int parenthesisCount = 0;
    
    // Environment to store variables
    private Map<String, Object> environment;
    private Map<String, Object> args = new HashMap<>();

    // Existing constructor
    public EvaluationContext(List<Token> tokens, String sourceText) {
        this.tokens = tokens;
        this.sourceText = sourceText;
        this.sourceLines = sourceText.split("\n");
        this.position = 0;
        this.parenthesisCount = 0;
        this.isInsideFunction = false;
        this.environment = new HashMap<>();
    }

    // Constructor that takes a Map<String, Object>
    public EvaluationContext(Map<String, Object> environment) {
        this.tokens = null;
        this.sourceText = null;
        this.sourceLines = null;
        this.position = 0;
        this.parenthesisCount = 0;
        this.isInsideFunction = false;
        this.environment = new HashMap<>(environment);
    }

    // Constructor that takes another EvaluationContext
    public EvaluationContext(EvaluationContext other) {
        this.tokens = other.tokens;
        this.sourceText = other.sourceText;
        this.sourceLines = other.sourceLines;
        this.position = other.position;
        this.parenthesisCount = other.parenthesisCount;
        this.isInsideFunction = other.isInsideFunction;
        this.environment = new HashMap<>(other.environment);
    }

    // Default constructor
    public EvaluationContext() {
        this.tokens = null;
        this.sourceText = null;
        this.sourceLines = null;
        this.position = 0;
        this.parenthesisCount = 0;
        this.isInsideFunction = false;
        this.environment = new HashMap<>();
    }

    // Method to declare variables in the environment
    public void declare(String name, Object value) {
        environment.put(name, value);
    }

    // Method to get variables from the environment
    public Object get(String name) {
        return environment.get(name);
    }

    public Map<String, Object> getEnvironment() {
        return environment;
    }

    public boolean isAtEnd() {
        return position >= tokens.size();
    }
    
    public Token peek() {
        return tokens.get(position);
    }
    
    public Token previous() {
        return tokens.get(position - 1);
    }
    
    public Token advance() {
        if (position < tokens.size()) {
            return tokens.get(position++);
        }
        return null;
    }

    public String getCurrentLine() {
        if (position == 0) return "";
        int currentLine = tokens.get(position - 1).line;
        return sourceLines[currentLine - 1];
    }

    public void setArgs(Map<String, Object> args) {
        this.args = args;
    }

    public Map<String, Object> getArgs() {
        return args;
    }
}