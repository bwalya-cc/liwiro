// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

import java.util.List;
import java.util.ArrayList;

public class ListExpressionNode extends Node {
    public final List<Node> elements;
    public final String iterator;
    public final Node iterable;
    public final Node condition;
    public final Node expression;

    // Constructor for a literal list.
    public ListExpressionNode(List<Node> elements) {
        this.elements = elements;
        this.iterator = null;
        this.iterable = null;
        this.condition = null;
        this.expression = null;
    }

    // Constructor for a list comprehension.
    public ListExpressionNode(Node expression, String iterator, Node iterable) {
        this.elements = new ArrayList<>();
        this.expression = expression;
        this.iterator = iterator;
        this.iterable = iterable;
        this.condition = null;
    }
    
    // Constructor for list comprehension with condition
    public ListExpressionNode(Node expression, String iterator, Node iterable, Node condition) {
        this.elements = new ArrayList<>();
        this.expression = expression;
        this.iterator = iterator;
        this.iterable = iterable;
        this.condition = condition;
    }

    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitListExpression(this);
    }
}