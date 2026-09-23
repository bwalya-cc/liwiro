// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class ConditionalExpressionNode extends Node {
    public final Node condition;
    public final Node trueBranch;
    public final Node falseBranch;
    
    public ConditionalExpressionNode(Node condition, Node trueBranch, Node falseBranch) {
        this.condition = condition;
        this.trueBranch = trueBranch;
        this.falseBranch = falseBranch;
    }

    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitConditionalExpression(this);
    }
}