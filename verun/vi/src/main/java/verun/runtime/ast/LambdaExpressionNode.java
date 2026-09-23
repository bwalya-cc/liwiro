// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

import java.util.List;

public class LambdaExpressionNode extends Node {
    public final List<ParameterNode> parameters;
    public final Node body;

    public LambdaExpressionNode(List<ParameterNode> parameters, Node body) {
        this.parameters = parameters;
        this.body = body;
    }

    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitLambdaExpression(this);
    }
}