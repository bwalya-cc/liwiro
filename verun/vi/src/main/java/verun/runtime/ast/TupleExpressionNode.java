// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

import java.util.List;

public class TupleExpressionNode extends Node {
    public final List<Node> elements;
    
    public TupleExpressionNode(List<Node> elements) {
        this.elements = elements;
    }

    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitTupleExpression(this);
    }
}