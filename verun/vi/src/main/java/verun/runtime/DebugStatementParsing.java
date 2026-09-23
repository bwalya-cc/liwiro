// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime;

import verun.runtime.lexer.Lexer;
import verun.runtime.lexer.Token;
import verun.runtime.parser.Parser;
import verun.runtime.parser.ParserContext;
import java.util.List;

public class DebugStatementParsing {
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
        System.out.println("Starting parseStatement...");
        System.out.println("Initial position: " + ctx.position);
        System.out.println("Current token: " + ctx.peek().type);
        
        // Simulate the parseStatement logic
        if (ctx.peek().type == verun.runtime.lexer.TokenType.LET) {
            System.out.println("Found LET token, calling parseVariableDeclaration");
            // This would call parseVariableDeclaration which expects to find the variable name next
            ctx.position++; // consume LET
            System.out.println("After consuming LET, position: " + ctx.position);
            System.out.println("Next token should be IDENTIFIER: " + ctx.peek().type);
        } else {
            System.out.println("Did not find LET token, this is the bug!");
        }
    }
}