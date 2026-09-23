// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

import java.util.List;

public class NewInstanceNode extends Node {
    public final String className;
    public final List<Node> arguments;

    public NewInstanceNode(String className, List<Node> arguments) {
        this.className = className;
        this.arguments = arguments;
    }
    
    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitNewInstance(this);
    }
}