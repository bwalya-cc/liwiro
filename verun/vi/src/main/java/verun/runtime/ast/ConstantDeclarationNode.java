// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class ConstantDeclarationNode extends Node {
    public final String name;
    public final String type;
    public final Node value;
    
    public ConstantDeclarationNode(String name, Node value) {
        this(name, null, value);
    }

    public ConstantDeclarationNode(String name, String type, Node value) {
        this.name = name;
        this.type = type;
        this.value = value;
    }
    
    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitConstantDeclaration(this);
    }
}
