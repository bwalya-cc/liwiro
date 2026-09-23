// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime;

import verun.runtime.lexer.Lexer;
import verun.runtime.lexer.Token;
import java.util.List;

public class DebugCommaTokens {
    public static void main(String[] args) {
        String source = "let nums = [1, 2, 3, 4, 5];";
        Lexer lexer = new Lexer(source);
        List<Token> tokens = lexer.tokenize();
        
        System.out.println("Tokens for: " + source);
        for (Token token : tokens) {
            System.out.println("  " + token.type + " : '" + token.value + "' at line " + token.line + ", col " + token.column);
        }
    }
}