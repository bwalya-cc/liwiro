// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class TryCatchNode extends Node {
    public final Node tryBlock;
    public final String errorVar;
    public final Node catchBlock;
    public final Node elseBlock;
    public final Node completeBlock;

    public TryCatchNode(Node tryBlock, String errorVar, Node catchBlock, Node elseBlock, Node completeBlock) {
        this.tryBlock = tryBlock;
        this.errorVar = errorVar;
        this.catchBlock = catchBlock;
        this.elseBlock = elseBlock;
        this.completeBlock = completeBlock;
    }

    @Override
    public <T> T accept(AstVisitor<T> visitor) {
        return visitor.visitTryCatch(this);
    }
}