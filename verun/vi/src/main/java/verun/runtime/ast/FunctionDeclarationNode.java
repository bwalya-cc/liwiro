// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

import java.util.List;

public class FunctionDeclarationNode extends Node {
    public final String name;
    public final List<ParameterNode> parameters;
    public final String returnType;
    public final Node body;
    public final boolean isStatic;

    public FunctionDeclarationNode(String name, List<ParameterNode> parameters, String returnType, Node body,
                                   boolean isStatic) {
        this.name = name;
        this.parameters = parameters;
        this.returnType = returnType;
        this.body = body;
        this.isStatic = isStatic;
    }
    
    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitFunctionDeclaration(this);
    }
}