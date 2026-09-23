// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class IndexAccessNode extends Node {
    private final Node target;
    private final Node index;
    private final Node endIndex;
    private final Node step;
    private final boolean slice;
    private final int line;
    private final int column;

    public IndexAccessNode(Node target, Node index) {
        this(target, index, null, false, -1, -1);
    }

    public IndexAccessNode(Node target, Node index, int line, int column) {
        this(target, index, null, false, line, column);
    }

    public IndexAccessNode(Node target, Node index, Node endIndex, int line, int column) {
        this(target, index, endIndex, null, line, column);
    }

    public IndexAccessNode(Node target, Node index, Node endIndex, Node step, int line, int column) {
        this(target, index, endIndex, step, true, line, column);
    }

    public IndexAccessNode(Node target, Node index, Node endIndex, boolean slice, int line, int column) {
        this(target, index, endIndex, null, slice, line, column);
    }

    private IndexAccessNode(Node target, Node index, Node endIndex, Node step, boolean slice, int line, int column) {
        this.target = target;
        this.index = index;
        this.endIndex = endIndex;
        this.step = step;
        this.slice = slice;
        this.line = line;
        this.column = column;
    }

    public Node getTarget() {
        return target;
    }

    public Node getIndex() {
        return index;
    }

    public Node getEndIndex() {
        return endIndex;
    }

    public Node getStep() {
        return step;
    }

    public boolean isSlice() {
        return slice;
    }

    public int getLine() {
        return line;
    }

    public int getColumn() {
        return column;
    }

    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitIndexAccessNode(this);
    }
}
