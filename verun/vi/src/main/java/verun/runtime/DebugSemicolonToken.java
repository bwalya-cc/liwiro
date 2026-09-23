// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime;

import verun.runtime.lexer.Lexer;
import verun.runtime.lexer.Token;
import verun.runtime.lexer.TokenType;
import verun.runtime.parser.ParserContext;
import java.util.List;

public class DebugSemicolonToken {
    public static void main(String[] args) {
        String source = ";";
        Lexer lexer = new Lexer(source);
        List<Token> tokens = lexer.tokenize();
        
        System.out.println("Tokens for: " + source);
        for (Token token : tokens) {
            System.out.println("  " + token.type + " : '" + token.value + "'");
            System.out.println("  Type name: " + token.type.name());
            System.out.println("  Expected SEMICOLON value: " + TokenType.SEMICOLON.getSymbol());
        }
        
        // Test the match method directly
        ParserContext ctx = new ParserContext(tokens, source);
        System.out.println("\nTesting match methods:");
        System.out.println("Current token type: " + ctx.peek().type);
        System.out.println("TokenType.SEMICOLON.getSymbol(): " + TokenType.SEMICOLON.getSymbol());
        
        boolean match1 = verun.runtime.parser.UtilityParser.match(ctx, TokenType.SEMICOLON);
        System.out.println("match(SEMICOLON): " + match1);
        
        ctx.position = 0; // Reset position
        boolean match2 = verun.runtime.parser.UtilityParser.match(ctx, TokenType.SEMICOLON, ";");
        System.out.println("match(SEMICOLON, ';'): " + match2);
    }
}