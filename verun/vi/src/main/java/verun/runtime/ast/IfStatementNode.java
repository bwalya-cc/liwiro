// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

import java.util.List;

public class IfStatementNode extends Node {
    public final Node condition;
    public final Node thenBranch;
    public final List<ElseIfClauseNode> altClauses; // Changed from elseIfs
    public final Node elseBranch;

    public IfStatementNode(
        Node condition, 
        Node thenBranch, 
        List<ElseIfClauseNode> altClauses, 
        Node elseBranch
    ) {
        this.condition = condition;
        this.thenBranch = thenBranch;
        this.altClauses = altClauses;
        this.elseBranch = elseBranch;
    }

    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitIfStatement(this);
    }
}