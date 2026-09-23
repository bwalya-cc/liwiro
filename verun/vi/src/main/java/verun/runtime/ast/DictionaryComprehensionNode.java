// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class DictionaryComprehensionNode extends Node {
    public final Node keyExpr;
    public final Node valueExpr;
    public final String iterator;
    public final Node iterable;
    public final Node condition;

    public DictionaryComprehensionNode(
        Node keyExpr,
        Node valueExpr, 
        String iterator,
        Node iterable,
        Node condition
    ) {
        this.keyExpr = keyExpr;
        this.valueExpr = valueExpr;
        this.iterator = iterator;
        this.iterable = iterable;
        this.condition = condition;
    }

    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitDictionaryComprehension(this);
    }
}