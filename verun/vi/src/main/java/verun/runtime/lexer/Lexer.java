// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.lexer;

import java.util.*;

// Lexer class responsible for tokenizing the source code
public class Lexer {

    private final String source;
    private int position = 0;
    private int line = 1;
    private int column = 1;
    private boolean insideString = false; // Track if we're inside a string literal

    public Lexer(String source) {
        this.source = source;
    }

    public List<Token> tokenize() {
        List<Token> tokens = new ArrayList<>();
        while (position < source.length()) {
            char current = peek();

            if (Character.isWhitespace(current)) {
                consumeWhitespace();
            } else if (current == '#') {
                readComment();
            } else if (current == '`' && peekAhead(1) == '`' && peekAhead(2) == '`') {
                readMultiLineComment();
            } else if (current == '`') {
                tokens.add(
                        new Token(TokenType.FORMATTED_STRING, readFormattedString(), line, column, getCurrentLine()));
                column += 2; // Account for opening/closing backticks
            } else if (current == '"' || current == '\'') {
                int startColumn = column;
                String value = readString(current);
                tokens.add(new Token(TokenType.STRING, value, line, startColumn, getCurrentLine()));
            } else if (current == '.' && position + 1 < source.length() && source.charAt(position + 1) == '.') {
                // Handle range operator ..
                tokens.add(new Token(TokenType.RANGE, "..", line, column, getCurrentLine()));
                advance(); // Skip first .
                advance(); // Skip second .
                column += 2;
            } else if (current == ':') {
                // ':' is punctuation (including the two-colon spelling used
                // for an omitted slice bound), never an operator. Handle it
                // before the broad operator scanner so `::` becomes two
                // ordinary COLON tokens.
                tokens.add(new Token(TokenType.COLON, ":", line, column, getCurrentLine()));
                advance();
            } else if (isOperator(current)) {
                String operator = readOperator();
                TokenType operatorType = TokenType.getOperator(operator);
                tokens.add(new Token(operatorType, operator, line, column, getCurrentLine()));
                column += operator.length();
            } else if (isPunctuation(current)) {
                String punct = String.valueOf(current);
                tokens.add(new Token(TokenType.getPunctuation(punct), punct, line, column, getCurrentLine()));
                advance();
            } else if (Character.isLetter(current) || current == '_' || current == '$') {
                String id = readIdentifier();
                TokenType type = TokenType.getKeyword(id);
                tokens.add(new Token(type != TokenType.IDENTIFIER ? type : TokenType.IDENTIFIER,
                        id, line, column - id.length(), getCurrentLine()));
            } else if (Character.isDigit(current)) {
                String number = readNumber();
                tokens.add(new Token(TokenType.NUMBER, number, line, column - number.length(), getCurrentLine()));
            } else {
                throw new RuntimeException(
                        "Unexpected character: " + current + " at line " + line + ", column " + column);
            }
        }
        return tokens;
    }

    private void readComment() {
        while (position < source.length() && peek() != '\n') {
            advance();
        }
    }

    // In Lexer.java
    private String readString(char quoteType) {
        advance(); // Skip opening quote
        StringBuilder value = new StringBuilder();

        while (position < source.length() && peek() != quoteType) {
            char current = peek();
            if (current == '\\') {
                advance();
                current = peek();
                if (current == '.' || current == ',' || current == ';') {
                    value.append(current);
                } else {
                    switch (current) {
                        case 'n':
                            value.append('\n');
                            break;
                        case 't':
                            value.append('\t');
                            break;
                        case '"':
                            value.append('"');
                            break;
                        case '\'':
                            value.append('\'');
                            break;
                        case '\\':
                            value.append('\\');
                            break;
                        default:
                            value.append('\\').append(current);
                            break;
                    }
                }
            } else {
                value.append(current);
            }
            advance();
        }

        if (position >= source.length()) {
            throw new RuntimeException("Unterminated string at line " + line);
        }

        advance(); // Skip closing quote
        return value.toString();
    }

    // Rest of the helper methods (advance, peek, readNumber, etc.) remain unchanged
    // [Keep all other existing methods exactly as they were in your original code]

    private void advance() {
        if (peek() == '\n') {
            line++;
            column = 1;
        } else {
            column++;
        }
        position++;
    }

    private char peek() {
        return source.charAt(position);
    }

    private void consumeWhitespace() {
        while (position < source.length() && Character.isWhitespace(peek())) {
            advance();
        }
    }

    private void readMultiLineComment() {
        // Consume opening triple backticks
        advance();
        advance();
        advance();

        while (position + 2 < source.length()) {
            if (peek() == '`' && peekAhead(1) == '`' && peekAhead(2) == '`') {
                // Consume closing triple backticks
                advance();
                advance();
                advance();
                return;
            }
            advance();
        }
        throw new RuntimeException("Unterminated multi-line comment");
    }

    private String getCurrentLine() {
        int start = position;
        while (start > 0 && source.charAt(start - 1) != '\n') {
            start--;
        }
        int end = position;
        while (end < source.length() && source.charAt(end) != '\n') {
            end++;
        }
        return source.substring(start, end);
    }

    private String readFormattedString() {
        advance(); // Skip opening backtick
        StringBuilder value = new StringBuilder();
        while (position < source.length() && peek() != '`') {
            char current = peek();
            if (current == '{') {
                value.append(current);
                advance();
                int braceCount = 1;
                while (position < source.length() && braceCount > 0) {
                    current = peek();
                    if (current == '{')
                        braceCount++;
                    else if (current == '}')
                        braceCount--;
                    value.append(current);
                    advance();
                }
                if (braceCount > 0) {
                    throw new RuntimeException("Unterminated interpolation in formatted string at line " + line);
                }
            } else {
                value.append(current);
                advance();
            }
        }
        if (position >= source.length()) {
            throw new RuntimeException("Unterminated formatted string at line " + line);
        }
        advance(); // Skip closing backtick
        return value.toString();
    }

    // Reads a comment from the source code
    private void readComment(List<Token> tokens) {
        int startColumn = column;
        advance(); // Skip '#'
        StringBuilder comment = new StringBuilder();
        while (position < source.length() && peek() != '\n') {
            comment.append(peek());
            advance();
        }
        tokens.add(new Token(TokenType.COMMENT, comment.toString(), line, startColumn, getCurrentLine()));
    }

    // Reads a single-line comment from the source code
    private String readOperator() {
        StringBuilder operator = new StringBuilder();
        while (position < source.length() && isOperator(peek())) {
            char current = peek();

            // Handle double-character operators first
            if (position + 1 < source.length()) {
                char next = source.charAt(position + 1);

                // Handle range operator ..
                if (current == '.' && next == '.') {
                    operator.append("..");
                    advance();
                    advance();
                    return operator.toString();
                }

                // Handle => for lambdas
                if (current == '=' && next == '>') {
                    operator.append(current).append(next);
                    advance();
                    advance();
                    return operator.toString();
                }

                // Handle // floor-division operator.
                if (current == '/' && next == '/') {
                    operator.append(current).append(next);
                    advance();
                    advance();
                    return operator.toString();
                }

                // Handle -> for arrows
                if (current == '-' && next == '>') {
                    operator.append(current).append(next);
                    advance();
                    advance();
                    return operator.toString();
                }
            }

            // Handle single-character operators
            operator.append(current);
            advance();
        }
        return operator.toString();
    }

    private boolean isOperator(char c) {
        return "+-*/%&|^~<>!?=:".indexOf(c) != -1;
    }

    private boolean isPunctuation(char c) {
        return "(){}[],;:.@\"".indexOf(c) != -1;
    }

    private String readIdentifier() {
        int start = position;
        while (position < source.length() &&
                (Character.isLetterOrDigit(peek()) || peek() == '_' || peek() == '$')) {
            advance();
        }
        return source.substring(start, position);
    }

    private String readNumber() {
        int start = position;
        boolean isFloat = false;
        while (position < source.length() &&
                (Character.isDigit(peek()) || 
                 (peek() == '.' && !isFloat && peekAhead(1) != '.'))) {  // Don't consume . if it's part of ..
            if (peek() == '.') {
                isFloat = true;
            }
            advance();
        }
        return source.substring(start, position);
    }

    private char peekAhead(int steps) {
        if (position + steps >= source.length())
            return '\0';
        return source.charAt(position + steps);
    }

    private char peekNext() {
        return peekAhead(1); // Reuse existing logic
    }
}
