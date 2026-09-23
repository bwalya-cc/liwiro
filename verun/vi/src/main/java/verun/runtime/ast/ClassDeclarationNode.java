// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

import java.util.List;

public class ClassDeclarationNode extends Node {
    public final String className;
    public final List<ParameterNode> constructorParameters;
    public final Node parent;
    public final Node vdbBinding;
    public final Node body;

    public ClassDeclarationNode(String className, List<ParameterNode> constructorParameters, Node parent, Node vdbBinding, Node body) {
        this.className = className;
        this.constructorParameters = constructorParameters;
        this.parent = parent;
        this.vdbBinding = vdbBinding;
        this.body = body;
    }

    public ClassDeclarationNode(String className, Node parent, Node body) {
        this(className, null, parent, null, body);
    }

    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitClassDeclaration(this);
    }
}
