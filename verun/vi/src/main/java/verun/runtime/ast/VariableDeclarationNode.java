// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class VariableDeclarationNode extends Node {
    public final String name;
    public final String type;
    public final Node initializer;

    public VariableDeclarationNode(String name, Node initializer) {
        this(name, null, initializer);
    }

    public VariableDeclarationNode(String name, String type, Node initializer) {
        this.name = name;
        this.type = type;
        this.initializer = initializer;
    }
    
    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitVariableDeclaration(this);
    }
}
