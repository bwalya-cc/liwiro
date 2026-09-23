// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

import java.util.List;

public class MatchStatementNode extends Node {
    public final Node expression;
    public final List<MatchCaseNode> cases;
    public final Node defaultCase;
    
    public MatchStatementNode(Node expression, List<MatchCaseNode> cases, Node defaultCase) {
        this.expression = expression;
        this.cases = cases;
        this.defaultCase = defaultCase;
    }
    
    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitMatchStatement(this);
    }
}