// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class ReturnStatementNode extends Node {
    public final Node expression;
    
    public ReturnStatementNode(Node expression) {
        this.expression = expression;
    }
    
    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitReturnStatement(this);
    }
}