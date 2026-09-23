// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class UnaryOperationNode extends Node {
    public final String operator;
    public final Node operand;
    public final boolean isPostfix;
    public final int line;
    public final int column;

    public UnaryOperationNode(String operator, Node operand, boolean isPostfix) {
        this(operator, operand, isPostfix, -1, -1);
    }

    public UnaryOperationNode(String operator, Node operand, boolean isPostfix, int line, int column) {
        this.operator = operator;
        this.operand = operand;
        this.isPostfix = isPostfix;
        this.line = line;
        this.column = column;
    }
    
    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitUnaryOperation(this);
    }
}
