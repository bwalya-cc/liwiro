// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime;

import verun.runtime.lexer.Lexer;
import verun.runtime.lexer.Token;
import java.util.List;

public class DebugSimple {
    public static void main(String[] args) {
        String[] tests = {"\"hello\"", "print(\"test\")"};
        
        for (String source : tests) {
            System.out.println("\n=== Testing: " + source + " ===");
            Lexer lexer = new Lexer(source);
            List<Token> tokens = lexer.tokenize();
            
            System.out.println("Tokens:");
            for (int i = 0; i < tokens.size(); i++) {
                Token token = tokens.get(i);
                System.out.println("  [" + i + "] " + token.type + " : '" + token.value + "'");
            }
            
            System.out.println("Token count: " + tokens.size());
        }
    }
}