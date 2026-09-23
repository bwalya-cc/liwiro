// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class EnumMemberNode extends Node {
    public final String name;
    public final Node value;
    public final int ordinal;

    public EnumMemberNode(String name, Node value, int ordinal) {
        this.name = name;
        this.value = value;
        this.ordinal = ordinal;
    }

    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitEnumMember(this);
    }
}
