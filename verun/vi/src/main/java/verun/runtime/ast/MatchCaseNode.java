// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class MatchCaseNode extends Node {
    public final Node pattern;
    public final Node body;
    
    public MatchCaseNode(Node pattern, Node body) {
        this.pattern = pattern;
        this.body = body;
    }
    
    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitMatchCase(this);
    }
}