// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class NamedArgumentNode extends Node {
    public final Node key;
    public final Node value;
    
    public NamedArgumentNode(Node key, Node value) {
        this.key = key;
        this.value = value;
    }
    
    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitNamedArgument(this);
    }
}