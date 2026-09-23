// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

import java.util.ArrayList;

public class ListComprehensionNode extends Node {
    protected final Node expression; // the expression to evaluate
    private final ArrayList<ComprehensionClause> clauses; // one or more for-clauses
    private final String iterator;
    private final Node iterable;
    private final Node condition;

    public ListComprehensionNode(Node expression, ArrayList<ComprehensionClause> clauses) {
        this.expression = expression;
        this.clauses = clauses;
        this.iterator = null;
        this.iterable = null;
        this.condition = null;
    }

    public ListComprehensionNode(Node expression, String iterator, Node iterable, Node condition) {
        this.expression = expression;
        this.iterator = iterator;
        this.iterable = iterable;
        this.condition = condition;
        this.clauses = null;
    }

    public Node getExpression() {
        return expression;
    }

    public ArrayList<ComprehensionClause> getClauses() {
        return clauses;
    }

    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitListComprehension(this);
    }
}