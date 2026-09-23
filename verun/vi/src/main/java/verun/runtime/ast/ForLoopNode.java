// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class ForLoopNode extends Node {
    public final Node initializer;
    public final Node condition;
    public final Node increment;
    public final Node body;
    
    public ForLoopNode(Node initializer, Node condition, Node increment, Node body) {
        this.initializer = initializer;
        this.condition = condition;
        this.increment = increment;
        this.body = body;
    }
    
    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitForLoop(this);
    }
}