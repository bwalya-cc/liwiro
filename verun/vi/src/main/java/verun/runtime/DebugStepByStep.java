// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime;

import verun.runtime.lexer.Lexer;
import verun.runtime.lexer.Token;
import java.util.List;

public class DebugStepByStep {
    public static void main(String[] args) {
        String source = "1..5";
        System.out.println("Source: " + source);
        
        Lexer lexer = new Lexer(source);
        List<Token> tokens = lexer.tokenize();
        
        System.out.println("Tokens:");
        for (Token token : tokens) {
            System.out.println("  " + token.type + " : '" + token.value + "'");
        }
    }
}