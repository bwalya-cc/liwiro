// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

import java.util.List;

public class FormattedStringNode extends Node {
    private final List<Node> parts;

    public FormattedStringNode(List<Node> parts) {
        this.parts = parts;
    }

    public List<Node> getParts() {
        return parts;
    }

    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitFormattedString(this);
    }
}