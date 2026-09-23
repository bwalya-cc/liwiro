// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime;

import verun.runtime.lexer.Lexer;
import verun.runtime.lexer.Token;
import verun.runtime.parser.Parser;
import verun.runtime.parser.ParserContext;
import verun.runtime.ast.Node;
import java.util.List;

public class DebugLetParsing {
    public static void main(String[] args) {
        String source = "let x = 5;";
        System.out.println("Source: " + source);
        
        Lexer lexer = new Lexer(source);
        List<Token> tokens = lexer.tokenize();
        
        System.out.println("Tokens:");
        for (int i = 0; i < tokens.size(); i++) {
            Token token = tokens.get(i);
            System.out.println("  [" + i + "] " + token.type + " : '" + token.value + "'");
        }
        
        ParserContext ctx = new ParserContext(tokens, source);
        System.out.println("Initial position: " + ctx.position);
        System.out.println("Current token: " + ctx.peek().type);
        
        // Try to match LET token
        boolean matched = verun.runtime.parser.UtilityParser.match(ctx, verun.runtime.lexer.TokenType.LET);
        System.out.println("LET matched: " + matched);
        System.out.println("Position after match: " + ctx.position);
        if (matched) {
            System.out.println("Next token: " + ctx.peek().type);
        }
    }
}