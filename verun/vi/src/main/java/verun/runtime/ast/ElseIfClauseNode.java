// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class ElseIfClauseNode extends Node {
    public final Node condition;
    public final Node body;

    public ElseIfClauseNode(Node condition, Node body) {
        this.condition = condition;
        this.body = body;
    }

    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitElseIfClause(this);
    }
}