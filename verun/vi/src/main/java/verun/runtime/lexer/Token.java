// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.lexer;

public class Token {
    public final TokenType type;
    public final String value;
    public final int line;
    public final int column;
    public final String lineText; // full text of the source line

    public Token(TokenType type, String value, int line, int column, String lineText) {
        this.type = type;
        this.value = value;
        this.line = line;
        this.column = column;
        this.lineText = lineText;
    }

    @Override
    public String toString() {
        return type + " \"" + value + "\" (line " + line + ", column " + column + ")";
    }
}