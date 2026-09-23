// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.parser;

import verun.runtime.lexer.Token;
import verun.runtime.lexer.TokenType;

public class UtilityParser {

    public static Token lookahead(ParserContext ctx, int steps) {
        int pos = ctx.position + steps;
        if (pos >= ctx.tokens.size()) return null;
        return ctx.tokens.get(pos);
    }
    
    public static boolean lookaheadIs(ParserContext ctx, int steps, TokenType expectedType) {
        Token token = lookahead(ctx, steps);
        return token != null && token.type == expectedType;
    }

    public static boolean check(ParserContext ctx, TokenType type) {
        if (ctx.isAtEnd())
            return false;
        return ctx.tokens.get(ctx.position).type == type;
    }

    public static boolean check(ParserContext ctx, TokenType type, String value) {
        if (ctx.isAtEnd())
            return false;
        Token token = ctx.tokens.get(ctx.position);
        if (TokenType.isKeyword(value)) {
            return token.type == TokenType.getKeyword(value) && token.value.equals(value);
        }
        if (TokenType.getOperator(value) != null) {
            return token.type == TokenType.getOperator(value) && token.value.equals(value);
        }
        if (TokenType.isPunctuation(value)) {
            return token.type == TokenType.getPunctuation(value) && token.value.equals(value);
        }
        return token.type == type && token.value.equals(value);
    }

    public static Token consume(ParserContext ctx, TokenType type, String value, String errorMessage) {
        if (check(ctx, type, value)) {
            return ctx.advance();
        }

        Token foundToken = ctx.peek();
        throw error(foundToken, ctx.sourceLines, errorMessage);
    }

    public static boolean match(ParserContext ctx, TokenType type, String value) {
        if (ctx.isAtEnd())
            return false;
        Token token = ctx.tokens.get(ctx.position);
        if (token.type == type && token.value.equals(value)) {
            ctx.position++;
            return true;
        }
        return false;
    }

    public static boolean match(ParserContext ctx, TokenType type) {
        if (check(ctx, type)) {
            ctx.position++;
            return true;
        }
        return false;
    }

    public static Token consume(ParserContext ctx, TokenType type, String message) {
        if (check(ctx, type)) {
            return ctx.tokens.get(ctx.position++);
        } else {
            throw error(ctx.peek(), ctx.sourceLines, message);
        }
    }

    public static RuntimeException error(Token token, String[] sourceLines, String message) {
        int lineNo = token != null ? token.line : -1;
        int colNo = token != null ? token.column : -1;
        if ((lineNo <= 0 || colNo <= 0) && sourceLines != null && sourceLines.length > 0) {
            lineNo = sourceLines.length;
            colNo = sourceLines[sourceLines.length - 1].length() + 1;
        }
        if (lineNo <= 0 || sourceLines == null || lineNo > sourceLines.length) {
            if (lineNo > 0 && colNo > 0) {
                return new RuntimeException(message + " at line " + lineNo + ", column " + colNo);
            }
            return new RuntimeException(message);
        }
        String line = sourceLines[lineNo - 1];
        int safeCol = Math.max(1, colNo);
        String pointer = repeatSpaces(safeCol - 1) + "^";
        return new RuntimeException("Error at line " + lineNo + ":" + safeCol + "\n"
            + line + "\n" + pointer + "\n" + message);
    }

    public static String repeat(String str, int times) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < times; i++) {
            sb.append(str);
        }
        return sb.toString();
    }

    public static String repeatString(String str, int times) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < times; i++) {
            sb.append(str);
        }
        return sb.toString();
    }

    public static String repeatSpaces(int count) {
        StringBuilder sb = new StringBuilder(count);
        for (int i = 0; i < count; i++) {
            sb.append(" ");
        }
        return sb.toString();
    }
}
