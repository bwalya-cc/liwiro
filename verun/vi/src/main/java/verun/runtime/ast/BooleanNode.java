// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class BooleanNode extends Node {
    public final boolean value;

    public BooleanNode(boolean value) {
        this.value = value;
    }

    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitBoolean(this);
    }
} 