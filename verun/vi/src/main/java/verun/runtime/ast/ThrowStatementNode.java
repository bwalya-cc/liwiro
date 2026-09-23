// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class ThrowStatementNode extends Node {
    public final Node expression;
    public final int line;
    public final int column;

    public ThrowStatementNode(Node expression) {
        this(expression, -1, -1);
    }

    public ThrowStatementNode(Node expression, int line, int column) {
        this.expression = expression;
        this.line = line;
        this.column = column;
    }

    public int getLine() {
        return line;
    }

    public int getColumn() {
        return column;
    }

    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitThrowStatement(this);
    }
}
