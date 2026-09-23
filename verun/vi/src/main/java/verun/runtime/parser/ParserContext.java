// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.parser;

import verun.runtime.lexer.Token;
import verun.runtime.lexer.TokenType;
import java.util.List;

public class ParserContext {
    public final List<Token> tokens;
    public int position;
    public final String sourceText;
    public final String[] sourceLines;
    public boolean isInsideFunction = false;
    public int parenthesisCount = 0;
    
    public ParserContext(List<Token> tokens, String sourceText) {
        this.tokens = tokens;
        this.sourceText = sourceText;
        this.sourceLines = sourceText.split("\n");
        this.position = 0;
        this.parenthesisCount = 0;
    }
    
    public boolean isAtEnd() {
        return position >= tokens.size();
    }
    
    public Token peek() {
        if (isAtEnd()) {
            // Return EOF token when at end of stream
            return new Token(TokenType.EOF, "", -1, -1, "");
        }
        return tokens.get(position);
    }
    
    public Token previous() {
        return tokens.get(position - 1);
    }
    
    public Token advance() {
        if (position < tokens.size()) {
            return tokens.get(position++);
        }
        return null;
    }

    // Added check method
    public boolean check(TokenType type) {
        if (isAtEnd()) {
            return false;
        }
        return peek().type == type;
    }

    public String getCurrentLine() {
        if (position == 0) return "";
        int currentLine = tokens.get(position - 1).line;
        return sourceLines[currentLine - 1];
    }
}