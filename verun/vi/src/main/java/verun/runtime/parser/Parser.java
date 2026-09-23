// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.parser;

import verun.runtime.ast.Node;
import java.util.List;

public class Parser {
    private final ParserContext ctx;
    
    public Parser(List<verun.runtime.lexer.Token> tokens, String sourceText) {
        this.ctx = new ParserContext(tokens, sourceText);
    }
    
    public Node parse() {
        return StatementParser.parseProgram(ctx.tokens, ctx.sourceText, ctx.sourceLines);
    }
    
    // Expose parseExpressionOnly() for external callers.
    public Node parseExpressionOnly() {
        return ExpressionParser.parseExpressionOnly(ctx);
    }
}