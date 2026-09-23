// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

import java.util.List;

public class BlockNode extends Node {
    public final List<Node> statements;
    
    public BlockNode(List<Node> statements) {
        this.statements = statements;
    }
    
    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitBlock(this);
    }
}