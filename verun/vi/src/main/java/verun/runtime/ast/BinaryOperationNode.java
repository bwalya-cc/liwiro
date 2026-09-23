// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class BinaryOperationNode extends Node {
    public final Node left;
    public final String operator;
    public final Node right;
    public final int line;
    public final int column;
    
    public BinaryOperationNode(Node left, String operator, Node right) {
        this(left, operator, right, -1, -1);
    }

    public BinaryOperationNode(Node left, String operator, Node right, int line, int column) {
        this.left = left;
        this.operator = operator;
        this.right = right;
        this.line = line;
        this.column = column;
    }

    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitBinaryOperation(this);
    }
}
