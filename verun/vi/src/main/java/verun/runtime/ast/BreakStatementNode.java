// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class BreakStatementNode extends Node {
    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitBreakStatement(this);
    }
} 