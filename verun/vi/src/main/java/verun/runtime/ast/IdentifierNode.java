// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class IdentifierNode extends Node {
    public final String name;
    public final int line;
    public final int column;
    
    public IdentifierNode(String name) {
        this(name, -1, -1);
    }

    public IdentifierNode(String name, int line, int column) {
        this.name = name;
        this.line = line;
        this.column = column;
    }
    
    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitIdentifier(this);
    }
}
