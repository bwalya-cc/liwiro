// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class RangeListNode extends Node {
    private final Node start;
    private final Node end;

    public RangeListNode(Node start, Node end) {
        this.start = start;
        this.end = end;
    }

    public Node getStart() {
        return start;
    }

    public Node getEnd() {
        return end;
    }

    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitRangeList(this);
    }
}