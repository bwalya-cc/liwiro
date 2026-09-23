// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

import java.util.List;

public class CallExpressionNode extends Node {
    private final Node callee;
    private final List<Node> arguments;
    private final int line;
    private final int column;
    
    public CallExpressionNode(Node callee, List<Node> arguments) {
        this(callee, arguments, -1, -1);
    }

    public CallExpressionNode(Node callee, List<Node> arguments, int line, int column) {
        this.callee = callee;
        this.arguments = arguments;
        this.line = line;
        this.column = column;
    }
    
    public Node getCallee() {
        return callee;
    }
    
    public List<Node> getArguments() {
        return arguments;
    }

    public int getLine() {
        return line;
    }

    public int getColumn() {
        return column;
    }
    
    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitCallExpression(this);
    }
}
