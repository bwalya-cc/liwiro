// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

import java.util.List;

public class EnumDeclarationNode extends Node {
    public final String enumName;
    public final List<EnumMemberNode> members;

    public EnumDeclarationNode(String enumName, List<EnumMemberNode> members) {
        this.enumName = enumName;
        this.members = members;
    }

    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitEnumDeclaration(this);
    }
}
