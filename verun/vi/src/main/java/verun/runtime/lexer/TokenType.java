// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.lexer;

import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.HashSet;
import java.util.Arrays;

public enum TokenType {

    // ===== BRACKETS =====
    LEFT_PAREN("("),
    RIGHT_PAREN(")"),
    LEFT_SQUARE_BRACKET("["),
    RIGHT_SQUARE_BRACKET("]"),
    LEFT_BRACE("{"),
    RIGHT_BRACE("}"),

    // ===== PUNCTUATION =====
    COMMA(","),
    DOT("."),
    SEMICOLON(";"),
    COLON(":"),
    AT_SYMBOL("@"),
    UNDERSCORE("_"),
    SINGLE_QUOTE("'"),
    DOUBLE_QUOTE("\""),
    BACKTICK("`"),

    // ===== OPERATORS =====
    PLUS("+"),
    MINUS("-"),
    MINUS_MINUS("--"),
    PLUS_PLUS("++"),
    PLUS_EQUAL("+="),
    MINUS_EQUAL("-="),
    STAR_EQUAL("*="),
    SLASH_EQUAL("/="),
    PERCENT_EQUAL("%="),
    STAR_STAR("**"),
    STAR("*"),
    SLASH("/"),
    FLOOR_DIV("//"),
    PERCENT("%"),
    AMPERSAND("&"),
    PIPE("|"),
    CARET("^"),
    CARET_CARET("^^"),
    TILDE("~"),
    AMPERSAND_AMPERSAND("&&"),
    PIPE_PIPE("||"),
    QUESTION_QUESTION("??"),
    SHIFT_LEFT("<<"),
    SHIFT_RIGHT(">>"),
    EQUAL("="),
    EQUAL_EQUAL("=="),
    EXCLAMATION("!"),
    EXCLAMATION_EQUAL("!="),
    LESS_THAN("<"),
    GREATER_THAN(">"),
    LESS_THAN_EQUAL("<="),
    GREATER_THAN_EQUAL(">="),
    ARROW("->"),
    BIND_ARROW("<->"),
    DOUBLE_ARROW("=>"), // For lambdas
    QUESTION_MARK("?"), // For ternary operators
    RANGE(".."),
    STRING_INTERPOLATION("${"), // For string interpolation

    // ===== LITERALS & IDENTIFIERS =====
    NUMBER(null),
    STRING(null),
    FORMATTED_STRING(null),
    IDENTIFIER(null),
    COMMENT(null),
    EOF(null),
    MULTILINE_COMMENT(null),

    // ===== KEYWORDS =====
    FUNC("func"),
    LET("let"),
    VAR("var"),
    CONST("const"),
    RETURN("return"),
    IF("if"),
    ALT("alt"),
    FOR("for"),
    WHILE("while"),
    MATCH("match"),
    CASE("case"),
    IMPORT("import"),
    CLASS("class"),
    ENUM("enum"),
    EXTENDS("extends")   ,
    OVERRIDE("override"),
    STATIC("static"),
    NEW("new"), 
    IN("in"),
    BREAK("break"),
    CONTINUE("continue"),


    // Exception Handling
    TRY("try"),
    CATCH("catch"),
    ELSE("else"),
    COMPLETE("complete"),
    THROW("throw"),

    // Boolean and null literals
    TRUE("true"),
    FALSE("false"),
    NULL("null"),

    ;

    private final String symbol;
    private static final Map<String, TokenType> keywords = new HashMap<>();
    private static final Map<String, TokenType> operators = new HashMap<>();

    TokenType(String symbol) {
        this.symbol = symbol;
    }

    static {
        
        // Register all keywords.
        keywords.put("func", FUNC);
        keywords.put("let", LET);
        keywords.put("var", VAR);
        keywords.put("const", CONST);
        keywords.put("return", RETURN);
        keywords.put("if", IF);
        keywords.put("else", ELSE);
        keywords.put("alt", ALT);
        keywords.put("for", FOR);
        keywords.put("while", WHILE);
        keywords.put("match", MATCH);
        keywords.put("case", CASE);
        keywords.put("import", IMPORT);
        keywords.put("class", CLASS);
        keywords.put("enum", ENUM);
        keywords.put("extends", EXTENDS);
        keywords.put("override", OVERRIDE);
        keywords.put("static", STATIC);
        keywords.put("new", NEW);
        keywords.put("in", IN);
        keywords.put("try", TRY);
        keywords.put("catch", CATCH);
        keywords.put("throw", THROW);
        keywords.put("complete", COMPLETE);
        keywords.put("break", BREAK);
        keywords.put("continue", CONTINUE);
        keywords.put("true", TRUE);
        keywords.put("false", FALSE);
        keywords.put("null", NULL);

        // Register all operators.
        operators.put("+", PLUS);
        operators.put("-", MINUS);
        operators.put("--", MINUS_MINUS);
        operators.put("++", PLUS_PLUS);
        operators.put("+=", PLUS_EQUAL);
        operators.put("-=", MINUS_EQUAL);
        operators.put("*=", STAR_EQUAL);
        operators.put("/=", SLASH_EQUAL);
        operators.put("%=", PERCENT_EQUAL);
        operators.put("**", STAR_STAR);
        operators.put("*", STAR);
        operators.put("/", SLASH);
        operators.put("//", FLOOR_DIV);
        operators.put("%", PERCENT);
        operators.put("&", AMPERSAND);
        operators.put("|", PIPE);
        operators.put("^", CARET);
        operators.put("^^", CARET_CARET);
        operators.put("~", TILDE);
        operators.put("&&", AMPERSAND_AMPERSAND);
        operators.put("||", PIPE_PIPE);
        operators.put("??", QUESTION_QUESTION);
        operators.put("<<", SHIFT_LEFT);
        operators.put(">>", SHIFT_RIGHT);
        operators.put("=", EQUAL);
        operators.put("==", EQUAL_EQUAL);
        operators.put("!", EXCLAMATION);
        operators.put("!=", EXCLAMATION_EQUAL);
        operators.put("<", LESS_THAN);
        operators.put(">", GREATER_THAN);
        operators.put("<=", LESS_THAN_EQUAL);
        operators.put(">=", GREATER_THAN_EQUAL);
        operators.put("->", ARROW);
        operators.put("<->", BIND_ARROW);
        operators.put("=>", DOUBLE_ARROW);
        operators.put("?", QUESTION_MARK);
        operators.put(":", COLON);
        operators.put("..", RANGE);

    }

    public static TokenType getKeyword(String keyword) {
        return keywords.getOrDefault(keyword, IDENTIFIER);
    }

    public static boolean isKeyword(String value) {
        return keywords.containsKey(value);
    }

    private boolean isOperator(char c) {
        return operators.containsKey(String.valueOf(c));
    }

    public static boolean isAssignmentOperator(String value) {
        return
            value.equals("=") ||
            value.equals("+=") ||
            value.equals("-=") ||
            value.equals("*=") ||
            value.equals("/=") ||
            value.equals("%=");
    }

    private static final Set<TokenType> punctuationTypes = new HashSet<>(Arrays.asList(
        LEFT_PAREN, RIGHT_PAREN, 
        LEFT_BRACE, RIGHT_BRACE,
        LEFT_SQUARE_BRACKET, RIGHT_SQUARE_BRACKET,
        COMMA, DOT, SEMICOLON, COLON, AT_SYMBOL, UNDERSCORE
    ));

    public static TokenType getPunctuation(String value) {
        switch(value) {
            case "(": return LEFT_PAREN;
            case ")": return RIGHT_PAREN;
            case "{": return LEFT_BRACE;
            case "}": return RIGHT_BRACE;
            case "[": return LEFT_SQUARE_BRACKET;
            case "]": return RIGHT_SQUARE_BRACKET;
            case ",": return COMMA;
            case ".": return DOT;
            case ";": return SEMICOLON;
            case ":": return COLON;
            case "@": return AT_SYMBOL;
            case "_": return UNDERSCORE;
            default: return null;
        }
    }

    public static boolean isPunctuation(String value) {
        return getPunctuation(value) != null;
    }

    public static TokenType getOperator(String operator) {
        return operators.get(operator);
    }

    public String getSymbol() {
        return symbol;
    }
}
