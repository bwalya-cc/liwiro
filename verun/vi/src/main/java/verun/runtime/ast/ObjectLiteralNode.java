// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

import java.util.Map;

public class ObjectLiteralNode extends Node {
    public final Map<String, Node> properties;

    public ObjectLiteralNode(Map<String, Node> properties) {
        this.properties = properties;
    }
    
    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitObjectLiteral(this);
    }
}