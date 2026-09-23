// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

import verun.runtime.evaluator.Evaluator;

public class ContinueStatementNode extends Node {
    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitContinueStatement(this);
    }
    
    public void validate(Evaluator evaluator) {
        // Check if the continue statement is within a loop context
        if (!evaluator.isInsideLoop()) {
            throw new RuntimeException("Continue statement not within a loop context.");
        }
    }
} 