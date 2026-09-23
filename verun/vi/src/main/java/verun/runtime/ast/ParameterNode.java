// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class ParameterNode extends Node {
    public final String name;
    public final String type;
    public final Node defaultValue;
    
    public ParameterNode(String name, String type, Node defaultValue) {
        this.name = name;
        this.type = type;
        this.defaultValue = defaultValue;
    }
    
    public ParameterNode(String name) {
        this(name, null, null);
    }
    
    public ParameterNode(String name, String type) {
        this(name, type, null);
    }
    
    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitParameter(this);
    }
}