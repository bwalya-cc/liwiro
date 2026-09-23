// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class ForEachLoopNode extends Node {
    public final Node variable;
    public final Node iterable;
    public final Node body;
    
    public ForEachLoopNode(Node variable, Node iterable, Node body) {
        this.variable = variable;
        this.iterable = iterable;
        this.body = body;
    }
    
    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitForEachLoop(this);
    }
}