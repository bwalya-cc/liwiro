// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class StringLiteralNode extends Node {
    private final String rawValue;

    public StringLiteralNode(String rawValue) {
        this.rawValue = rawValue;
    }

    public String getValue() {
        return rawValue.substring(1, rawValue.length() - 1)
            .replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace("\\\"", "\"")
            .replace("\\\\", "\\");
    }

    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitStringLiteral(this);
    }
}