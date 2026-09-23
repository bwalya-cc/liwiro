// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime;

import verun.runtime.lexer.Lexer;
import verun.runtime.lexer.Token;
import java.util.List;

public class DebugWithTrace {
    public static void main(String[] args) {
        String source = "1..5";
        System.out.println("Source: " + source);
        
        // Test the range detection logic directly
        System.out.println("Testing range detection:");
        for (int i = 0; i < source.length(); i++) {
            char c = source.charAt(i);
            System.out.println("Position " + i + ": '" + c + "' isOperator: " + isOperator(c));
            if (c == '.' && i + 1 < source.length() && source.charAt(i + 1) == '.') {
                System.out.println("  Found range operator .. at position " + i);
            }
        }
        
        Lexer lexer = new Lexer(source);
        List<Token> tokens = lexer.tokenize();
        
        System.out.println("\nTokens:");
        for (Token token : tokens) {
            System.out.println("  " + token.type + " : '" + token.value + "'");
        }
    }
    
    private static boolean isOperator(char c) {
        return "+-*/%&|^~<>!?=:".indexOf(c) != -1;
    }
}