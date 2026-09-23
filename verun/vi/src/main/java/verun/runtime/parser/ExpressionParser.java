// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.parser;

import verun.runtime.ast.*;
import verun.runtime.lexer.Lexer;
import verun.runtime.lexer.Token;
import verun.runtime.lexer.TokenType;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class ExpressionParser {
    private final ParserContext parserContext;

    public ExpressionParser(ParserContext parserContext) {
        this.parserContext = parserContext;
    }

    public static Node parseExpression(ParserContext ctx) {
        return parseAssignment(ctx);
    }

    private static Node parseAssignment(ParserContext ctx) {
        Node left = parseTernary(ctx);

        if (UtilityParser.match(ctx, TokenType.EQUAL) ||
                UtilityParser.match(ctx, TokenType.PLUS_EQUAL) ||
                UtilityParser.match(ctx, TokenType.MINUS_EQUAL) ||
                UtilityParser.match(ctx, TokenType.STAR_EQUAL) ||
                UtilityParser.match(ctx, TokenType.SLASH_EQUAL) ||
                UtilityParser.match(ctx, TokenType.PERCENT_EQUAL)) {

            Token operator = ctx.previous();
            Node right = parseAssignment(ctx);

            if (operator.type == TokenType.EQUAL && right instanceof LambdaExpressionNode) {
                return new BinaryOperationNode(left, "=", right, operator.line, operator.column);
            }

            if (operator.type != TokenType.EQUAL) {
                String baseOp = operator.value.replace("=", "");
                Node binaryOp = new BinaryOperationNode(left, baseOp, right, operator.line, operator.column);
                return new BinaryOperationNode(left, "=", binaryOp, operator.line, operator.column);
            }

            return new BinaryOperationNode(left, "=", right, operator.line, operator.column);
        }
        return left;
    }

    private static Node parseTernary(ParserContext ctx) {
        Node condition = parseNullCoalescing(ctx);

        // Check for if-else expression syntax: expr if condition else expr
        // Guard with rollback so list/dict comprehension filters ("if ...") do not fail here.
        int savedPos = ctx.position;
        if (UtilityParser.match(ctx, TokenType.IF)) {
            Node trueBranch = parseEquality(ctx);
            if (UtilityParser.match(ctx, TokenType.ELSE, "else")) {
                Node falseBranch = parseTernary(ctx);
                return new ConditionalExpressionNode(condition, trueBranch, falseBranch);
            }
            ctx.position = savedPos;
        }

        // Check for traditional ternary operator: condition ? true_expr : false_expr
        if (UtilityParser.match(ctx, TokenType.QUESTION_MARK, "?")) {
            Node trueBranch = parseTernary(ctx);
            UtilityParser.consume(ctx, TokenType.COLON, ":", "Expected ':' after true branch in ternary operator");
            Node falseBranch = parseTernary(ctx);
            return new ConditionalExpressionNode(condition, trueBranch, falseBranch);
        }
        
        return condition;
    }

    private static Node parseNullCoalescing(ParserContext ctx) {
        Node left = parseLogicalOr(ctx);
        while (UtilityParser.match(ctx, TokenType.QUESTION_QUESTION, "??")) {
            Token op = ctx.previous();
            String operator = op.value;
            Node right = parseLogicalOr(ctx);
            left = new BinaryOperationNode(left, operator, right, op.line, op.column);
        }
        return left;
    }

    private static Node parseLogicalOr(ParserContext ctx) {
        Node left = parseLogicalAnd(ctx);
        while (UtilityParser.match(ctx, TokenType.PIPE_PIPE, "||")) {
            Token op = ctx.previous();
            String operator = op.value;
            Node right = parseLogicalAnd(ctx);
            left = new BinaryOperationNode(left, operator, right, op.line, op.column);
        }
        return left;
    }

    private static Node parseLogicalAnd(ParserContext ctx) {
        Node left = parseBitwiseOr(ctx);
        while (UtilityParser.match(ctx, TokenType.AMPERSAND_AMPERSAND, "&&")) {
            Token op = ctx.previous();
            String operator = op.value;
            Node right = parseBitwiseOr(ctx);
            left = new BinaryOperationNode(left, operator, right, op.line, op.column);
        }
        return left;
    }

    private static Node parseBitwiseOr(ParserContext ctx) {
        Node left = parseBitwiseXor(ctx);
        while (UtilityParser.match(ctx, TokenType.PIPE, "|")) {
            Token op = ctx.previous();
            String operator = op.value;
            Node right = parseBitwiseXor(ctx);
            left = new BinaryOperationNode(left, operator, right, op.line, op.column);
        }
        return left;
    }

    private static Node parseBitwiseXor(ParserContext ctx) {
        Node left = parseBitwiseAnd(ctx);
        while (UtilityParser.match(ctx, TokenType.CARET_CARET, "^^")) {
            Token op = ctx.previous();
            String operator = op.value;
            Node right = parseBitwiseAnd(ctx);
            left = new BinaryOperationNode(left, operator, right, op.line, op.column);
        }
        return left;
    }

    private static Node parseBitwiseAnd(ParserContext ctx) {
        Node left = parseEquality(ctx);
        while (UtilityParser.match(ctx, TokenType.AMPERSAND, "&")) {
            Token op = ctx.previous();
            String operator = op.value;
            Node right = parseEquality(ctx);
            left = new BinaryOperationNode(left, operator, right, op.line, op.column);
        }
        return left;
    }

    private static Node parseEquality(ParserContext ctx) {
        Node left = parseComparison(ctx);
        while (UtilityParser.match(ctx, TokenType.EQUAL_EQUAL, "==") ||
                UtilityParser.match(ctx, TokenType.EXCLAMATION_EQUAL, "!=")) {
            Token op = ctx.previous();
            String operator = op.value;
            Node right = parseComparison(ctx);
            left = new BinaryOperationNode(left, operator, right, op.line, op.column);
        }
        return left;
    }

    private static Node parseComparison(ParserContext ctx) {
        Node left = parseShift(ctx);
        while (UtilityParser.match(ctx, TokenType.LESS_THAN, "<") ||
                UtilityParser.match(ctx, TokenType.GREATER_THAN, ">") ||
                UtilityParser.match(ctx, TokenType.LESS_THAN_EQUAL, "<=") ||
                UtilityParser.match(ctx, TokenType.GREATER_THAN_EQUAL, ">=")) {
            Token op = ctx.previous();
            String operator = op.value;
            Node right = parseShift(ctx);
            left = new BinaryOperationNode(left, operator, right, op.line, op.column);
        }
        return left;
    }

    private static Node parseShift(ParserContext ctx) {
        Node left = parseRange(ctx);
        while (UtilityParser.match(ctx, TokenType.SHIFT_LEFT, "<<") ||
                UtilityParser.match(ctx, TokenType.SHIFT_RIGHT, ">>")) {
            Token op = ctx.previous();
            String operator = op.value;
            Node right = parseRange(ctx);
            left = new BinaryOperationNode(left, operator, right, op.line, op.column);
        }
        return left;
    }

    private static Node parseRange(ParserContext ctx) {
        Node left = parseTerm(ctx);
        while (UtilityParser.match(ctx, TokenType.RANGE, "..")) {
            Node right = parseTerm(ctx);
            left = new RangeListNode(left, right);
        }
        return left;
    }

    private static Node parseTerm(ParserContext ctx) {
        Node left = parseFactor(ctx);
        while (UtilityParser.match(ctx, TokenType.PLUS, "+") || UtilityParser.match(ctx, TokenType.MINUS, "-")) {
            Token op = ctx.previous();
            String operator = op.value;
            Node right = parseFactor(ctx);
            left = new BinaryOperationNode(left, operator, right, op.line, op.column);
        }
        return left;
    }

    private static Node parseFactor(ParserContext ctx) {
        Node left = parsePower(ctx);
        while (UtilityParser.match(ctx, TokenType.STAR, "*") ||
                UtilityParser.match(ctx, TokenType.SLASH, "/") ||
                UtilityParser.match(ctx, TokenType.FLOOR_DIV, "//") ||
                UtilityParser.match(ctx, TokenType.PERCENT, "%")) {
            Token op = ctx.previous();
            String operator = op.value;
            Node right = parsePower(ctx);
            left = new BinaryOperationNode(left, operator, right, op.line, op.column);
        }
        return left;
    }

    private static Node parsePower(ParserContext ctx) {
        Node left = parseUnary(ctx);
        while (UtilityParser.match(ctx, TokenType.STAR_STAR, "**") ||
                UtilityParser.match(ctx, TokenType.CARET, "^")) {
            Token op = ctx.previous();
            String operator = op.value;
            Node right = parseUnary(ctx);
            left = new BinaryOperationNode(left, operator, right, op.line, op.column);
        }
        return left;
    }

    private static Node parseUnary(ParserContext ctx) {
        if (UtilityParser.match(ctx, TokenType.MINUS, "-")
                || UtilityParser.match(ctx, TokenType.EXCLAMATION, "!")
                || UtilityParser.match(ctx, TokenType.TILDE, "~")) {
            Token op = ctx.previous();
            String operator = op.value;
            Node operand = parseUnary(ctx);
            return new UnaryOperationNode(operator, operand, false, op.line, op.column);
        }
        Node node = parsePrimary(ctx);
        return parsePostfix(ctx, node);
    }

    private static Node parsePostfix(ParserContext ctx, Node node) {
        while (true) {
            if (UtilityParser.match(ctx, TokenType.LEFT_SQUARE_BRACKET, "[")) {
                Token bracket = ctx.previous();
                Node startIndex = null;
                Node endIndex = null;

                if (!UtilityParser.check(ctx, TokenType.COLON, ":") && !UtilityParser.check(ctx, TokenType.RIGHT_SQUARE_BRACKET, "]")) {
                    startIndex = parseExpression(ctx);
                }

                if (UtilityParser.match(ctx, TokenType.COLON, ":")) {
                    Node step = null;
                    if (!UtilityParser.check(ctx, TokenType.RIGHT_SQUARE_BRACKET, "]")
                            && !UtilityParser.check(ctx, TokenType.COLON, ":")) {
                        endIndex = parseExpression(ctx);
                    }
                    if (UtilityParser.match(ctx, TokenType.COLON, ":")) {
                        if (!UtilityParser.check(ctx, TokenType.RIGHT_SQUARE_BRACKET, "]")) {
                            step = parseExpression(ctx);
                        }
                    }
                    UtilityParser.consume(ctx, TokenType.RIGHT_SQUARE_BRACKET, "]", "Expected ']' after slice");
                    node = new IndexAccessNode(node, startIndex, endIndex, step, bracket.line, bracket.column);
                } else {
                    if (startIndex == null) {
                        throw parserError(ctx.peek(), "Expected index expression before ']'");
                    }
                    UtilityParser.consume(ctx, TokenType.RIGHT_SQUARE_BRACKET, "]", "Expected ']' after index");
                    node = new IndexAccessNode(node, startIndex, bracket.line, bracket.column);
                }
            } else if (UtilityParser.match(ctx, TokenType.DOT)) {
                String member = UtilityParser.consume(ctx, TokenType.IDENTIFIER,
                        "Expected member name after '.'").value;
                node = new MemberAccessNode(node, member);
            } else if (UtilityParser.match(ctx, TokenType.LEFT_PAREN, "(")) {
                Token openParen = ctx.previous();
                List<Node> arguments = new ArrayList<>();
                if (!UtilityParser.check(ctx, TokenType.RIGHT_PAREN)) {
                    do {
                        arguments.add(parseExpression(ctx));
                    } while (UtilityParser.match(ctx, TokenType.COMMA));
                }
                UtilityParser.consume(ctx, TokenType.RIGHT_PAREN, ")", "Expected ')' after arguments");
                node = new CallExpressionNode(node, arguments, openParen.line, openParen.column);
            } else if (checkPostfixOperator(ctx)) {
                Token op = ctx.advance();
                String operator = op.value;
                node = new UnaryOperationNode(operator, node, true, op.line, op.column);
            } else {
                break;
            }
        }
        return node;
    }

    private static boolean checkPostfixOperator(ParserContext ctx) {
        if (ctx.position >= ctx.tokens.size())
            return false;
        TokenType type = ctx.tokens.get(ctx.position).type;
        return type == TokenType.PLUS_PLUS || type == TokenType.MINUS_MINUS;
    }

    // In ExpressionParser.java
    public static Node parseLiteralOrIdentifier(ParserContext ctx) {
        Token token = ctx.peek();
        if (token.type == TokenType.EOF) {
            throw parserError(token, "Unexpected end of input in expression");
        }
        if (token.type == TokenType.SEMICOLON || token.type == TokenType.RIGHT_BRACE) {
            // These tokens signal the end of an expression
            throw parserError(token, "Unexpected token in expression: " + token.value);
        }
        if (token.type == TokenType.NUMBER) {
            String numStr = token.value;
            ctx.position++;
            if (numStr.contains(".")) {
                return new FloatNode(Double.parseDouble(numStr));
            } else {
                return new IntegerNode(Integer.parseInt(numStr));
            }
        } else if (token.type == TokenType.STRING) {
            ctx.position++;
            return new StringNode(token.value);
        } else if (token.type == TokenType.FORMATTED_STRING) {
            ctx.position++;
            return new FormattedStringNode(parseFormattedParts(ctx, token.value, token.line, token.column));
        } else if (token.type == TokenType.TRUE) {
            ctx.position++;
            return new BooleanNode(true);
        } else if (token.type == TokenType.FALSE) {
            ctx.position++;
            return new BooleanNode(false);
        } else if (token.type == TokenType.NULL) {
            ctx.position++;
            return new IdentifierNode("null", token.line, token.column);
        } else if (token.type == TokenType.IDENTIFIER) {
            ctx.position++;
            return new IdentifierNode(token.value, token.line, token.column);
        } else if (TokenType.isKeyword(token.value)) {
            ctx.position++;
            return new IdentifierNode(token.value, token.line, token.column);
        } else {
            throw parserError(token, "Expected literal or identifier, found: " + token.value);
        }
    }
    
    private static Node parsePrimary(ParserContext ctx) {
        // Check for lambda expression first, before consuming any tokens
        if (isLambdaExpression(ctx)) {
            return new ExpressionParser(ctx).parseLambdaExpression(ctx);
        } else if (UtilityParser.match(ctx, TokenType.FUNC, "func")) {
            return parseAnonymousFunctionExpression(ctx);
        } else if (UtilityParser.match(ctx, TokenType.LEFT_PAREN, "(")) {
            // Check if this is a tuple (comma-separated expressions)
            List<Node> elements = new ArrayList<>();
            boolean isTuple = false;
            
            // Look ahead to see if there are commas
            int tempPos = ctx.position;
            int parenCount = 1;
            boolean foundComma = false;
            
            while (tempPos < ctx.tokens.size() && parenCount > 0) {
                Token token = ctx.tokens.get(tempPos);
                if (token.type == TokenType.LEFT_PAREN) {
                    parenCount++;
                } else if (token.type == TokenType.RIGHT_PAREN) {
                    parenCount--;
                } else if (token.type == TokenType.COMMA && parenCount == 1) {
                    foundComma = true;
                    break;
                }
                tempPos++;
            }
            
            if (foundComma) {
                // This is a tuple - parse comma-separated expressions
                if (!UtilityParser.check(ctx, TokenType.RIGHT_PAREN, ")")) {
                    do {
                        elements.add(parseExpression(ctx));
                    } while (UtilityParser.match(ctx, TokenType.COMMA, ","));
                }
                UtilityParser.consume(ctx, TokenType.RIGHT_PAREN, ")", "Expected ')' after tuple elements");
                return new TupleExpressionNode(elements);
            } else {
                // Just a grouping expression
                Node expr = parseExpression(ctx);
                UtilityParser.consume(ctx, TokenType.RIGHT_PAREN, ")", "Expected ')' after expression");
                return expr;
            }
        } else if (UtilityParser.check(ctx, TokenType.LEFT_SQUARE_BRACKET)) {
            List<Node> elements = new ArrayList<>();
            ctx.position++; // Consume '['
            
            // Look ahead to see if this is a list comprehension
            boolean isListComprehension = false;
            int tempPos = ctx.position;
            while (tempPos < ctx.tokens.size() && ctx.tokens.get(tempPos).type != TokenType.RIGHT_SQUARE_BRACKET) {
                if (ctx.tokens.get(tempPos).type == TokenType.FOR) {
                    isListComprehension = true;
                    break;
                }
                tempPos++;
            }
            
            if (isListComprehension) {
                // List comprehension: [expression for iterator in iterable (for iterator in iterable)* (if condition)?]
                Node expression = parseExpression(ctx);
                
                // Parse multiple comprehension clauses
                ArrayList<ComprehensionClause> clauses = new ArrayList<>();
                
                while (UtilityParser.match(ctx, TokenType.FOR, "for")) {
                    String iterator = UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected iterator variable").value;
                    UtilityParser.consume(ctx, TokenType.IN, "in", "Expected 'in' after iterator");
                    Node iterable = parseExpression(ctx);
                    
                    // Check for condition
                    Node condition = null;
                    if (UtilityParser.match(ctx, TokenType.IF, "if")) {
                        condition = parseEquality(ctx);
                    }
                    
                    clauses.add(new ComprehensionClause(iterator, iterable, condition));
                }
                
                UtilityParser.consume(ctx, TokenType.RIGHT_SQUARE_BRACKET, "]", "Expected ']' to close list comprehension");
                return new ListComprehensionNode(expression, clauses);
            } else {
                if (!UtilityParser.check(ctx, TokenType.RIGHT_SQUARE_BRACKET, "]")) {
                    do {
                        elements.add(parseExpression(ctx));
                    } while (UtilityParser.match(ctx, TokenType.COMMA, ","));
                }
                UtilityParser.consume(ctx, TokenType.RIGHT_SQUARE_BRACKET, "]", "Expected ']'");
                return new ListExpressionNode(elements);
            }
        } else if (isLambdaExpression(ctx)) {
            return new ExpressionParser(ctx).parseLambdaExpression(ctx);
        } else if (UtilityParser.check(ctx, TokenType.LEFT_BRACE)) {
            return parseDictComprehensionOrObject(ctx);
        } else if (UtilityParser.check(ctx, TokenType.NEW)) {
            ctx.position++; // Consume 'new'
            String className = UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected class name after 'new'").value;
            UtilityParser.consume(ctx, TokenType.LEFT_PAREN, "(", "Expected '(' after class name");
            List<Node> arguments = new ArrayList<>();
            if (!UtilityParser.check(ctx, TokenType.RIGHT_PAREN, ")")) {
                do {
                    arguments.add(parseExpression(ctx));
                } while (UtilityParser.match(ctx, TokenType.COMMA, ","));
            }
            UtilityParser.consume(ctx, TokenType.RIGHT_PAREN, ")", "Expected ')' after arguments");
            return new NewInstanceNode(className, arguments);
        } else {
            return parseLiteralOrIdentifier(ctx);
        }
    }

    private Node parseLambdaExpression(ParserContext ctx) {
        List<ParameterNode> parameters = new ArrayList<>();
        if (UtilityParser.check(ctx, TokenType.LEFT_PAREN)) {
            UtilityParser.consume(ctx, TokenType.LEFT_PAREN, "(", "Expected '(' before lambda parameters");
            while (!UtilityParser.check(ctx, TokenType.RIGHT_PAREN)) {
                if (!parameters.isEmpty()) {
                    UtilityParser.consume(ctx, TokenType.COMMA, ",", "Expected ',' between parameters");
                }
                Token paramToken = ctx.peek();
                if (paramToken.type != TokenType.IDENTIFIER) {
                    throw parserError(paramToken, "Expected parameter name, found: " + paramToken.value);
                }
                parameters.add(new ParameterNode(paramToken.value));
                ctx.position++;
            }
            UtilityParser.consume(ctx, TokenType.RIGHT_PAREN, ")", "Expected ')' after lambda parameters");
        } else {
            Token paramToken = ctx.peek();
            if (paramToken.type != TokenType.IDENTIFIER) {
                throw parserError(paramToken, "Expected parameter name, found: " + paramToken.value);
            }
            parameters.add(new ParameterNode(paramToken.value));
            ctx.position++;
        }
        UtilityParser.consume(ctx, TokenType.DOUBLE_ARROW, "=>", "Expected '=>' after lambda parameters");
        Node body = StatementParser.parseBlockOrExpression(ctx);
        return new LambdaExpressionNode(parameters, body);
    }

    private static List<Node> parseFormattedParts(ParserContext ctx, String formattedStr, int baseLine, int baseColumn) {
        List<Node> parts = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        int formattedLine = baseLine > 0 ? baseLine : 1;
        int formattedColumn = baseColumn > 0 ? baseColumn : 1;
        for (int i = 0; i < formattedStr.length(); i++) {
            char c = formattedStr.charAt(i);

            // Handle common escape sequences inside formatted string literal sections.
            if (c == '\\' && i + 1 < formattedStr.length()) {
                char next = formattedStr.charAt(i + 1);
                switch (next) {
                    case 'n':
                        current.append('\n');
                        i++;
                        continue;
                    case 't':
                        current.append('\t');
                        i++;
                        continue;
                    case 'r':
                        current.append('\r');
                        i++;
                        continue;
                    case '\\':
                        current.append('\\');
                        i++;
                        continue;
                    case '`':
                        current.append('`');
                        i++;
                        continue;
                    default:
                        // Keep unknown escapes as-is.
                        current.append(c);
                        continue;
                }
            }

            // Check for ${...} syntax
            if (c == '$' && i + 1 < formattedStr.length() && formattedStr.charAt(i + 1) == '{') {
                if (current.length() > 0) {
                    parts.add(new StringNode(current.toString()));
                    current.setLength(0);
                }
                i += 2; // Skip ${
                int exprStartIndex = i;

                // Parse expression within braces
                StringBuilder exprBuilder = new StringBuilder();
                int braceCount = 1;
                while (i < formattedStr.length() && braceCount > 0) {
                    c = formattedStr.charAt(i);
                    if (c == '{')
                        braceCount++;
                    else if (c == '}')
                        braceCount--;
                    if (braceCount > 0) {
                        exprBuilder.append(c);
                        i++;
                    }
                }

                String expr = exprBuilder.toString();
                Lexer exprLexer = new Lexer(expr);
                List<Token> exprTokens = remapFormattedExprTokenLocations(
                        exprLexer.tokenize(),
                        formattedLine,
                        formattedColumn + exprStartIndex + 1);
                Parser exprParser = new Parser(exprTokens, expr);
                Node exprNode = exprParser.parseExpressionOnly();
                parts.add(exprNode);
            }
            // Check for {...} syntax
            else if (c == '{') {
                if (current.length() > 0) {
                    parts.add(new StringNode(current.toString()));
                    current.setLength(0);
                }
                i++; // Skip {
                int exprStartIndex = i;

                // Parse expression within braces
                StringBuilder exprBuilder = new StringBuilder();
                int braceCount = 1;
                while (i < formattedStr.length() && braceCount > 0) {
                    c = formattedStr.charAt(i);
                    if (c == '{')
                        braceCount++;
                    else if (c == '}')
                        braceCount--;
                    if (braceCount > 0) {
                        exprBuilder.append(c);
                        i++;
                    }
                }

                String expr = exprBuilder.toString();
                Lexer exprLexer = new Lexer(expr);
                List<Token> exprTokens = remapFormattedExprTokenLocations(
                        exprLexer.tokenize(),
                        formattedLine,
                        formattedColumn + exprStartIndex + 1);
                Parser exprParser = new Parser(exprTokens, expr);
                Node exprNode = exprParser.parseExpressionOnly();
                parts.add(exprNode);
            } else {
                current.append(c);
            }
        }
        if (current.length() > 0) {
            parts.add(new StringNode(current.toString()));
        }
        return parts;
    }

    private static List<Token> remapFormattedExprTokenLocations(List<Token> tokens, int baseLine, int baseColumn) {
        if (tokens == null || tokens.isEmpty()) {
            return tokens;
        }
        List<Token> remapped = new ArrayList<>(tokens.size());
        for (Token token : tokens) {
            if (token == null) {
                continue;
            }
            int relLine = Math.max(1, token.line);
            int relCol = Math.max(1, token.column);
            int line = baseLine + (relLine - 1);
            int column = (relLine == 1) ? (baseColumn + relCol - 1) : relCol;
            remapped.add(new Token(token.type, token.value, line, column, token.lineText));
        }
        return remapped;
    }

    private static boolean isLambdaExpression(ParserContext ctx) {
        int savedPos = ctx.position;
        try {
            // Simple check: look for pattern (IDENTIFIER) => or (IDENTIFIER, IDENTIFIER, ...) =>
            if (!UtilityParser.check(ctx, TokenType.LEFT_PAREN)) {
                return false;
            }
            
            // Look ahead to see if we have the pattern we want
            int tempPos = ctx.position + 1; // Skip the (
            boolean foundClosingParen = false;
            boolean foundArrow = false;
            
            // Look for closing parenthesis
            while (tempPos < ctx.tokens.size()) {
                Token token = ctx.tokens.get(tempPos);
                if (token.type == TokenType.RIGHT_PAREN) {
                    foundClosingParen = true;
                    tempPos++;
                    break;
                } else if (token.type == TokenType.IDENTIFIER || 
                          token.type == TokenType.COMMA) {
                    tempPos++;
                } else {
                    // Found something unexpected
                    return false;
                }
            }
            
            // Check for =>
            if (foundClosingParen && tempPos < ctx.tokens.size() && 
                ctx.tokens.get(tempPos).type == TokenType.DOUBLE_ARROW) {
                foundArrow = true;
            }
            
            return foundClosingParen && foundArrow;
        } catch (Exception e) {
            return false;
        } finally {
            ctx.position = savedPos;
        }
    }

    private static Node parseDictComprehensionOrObject(ParserContext ctx) {
        UtilityParser.consume(ctx, TokenType.LEFT_BRACE, "{", "Expected '{'");

        if (isDictComprehension(ctx)) {
            return parseDictComprehension(ctx);
        }

        return parseObjectLiteral(ctx);
    }

    private static boolean isDictComprehension(ParserContext ctx) {
        // Find a top-level `for` after the first key/value colon. The old
        // bounded lookahead misclassified valid expressions such as
        // `source[key] * 2` when the iterator appeared more than five tokens
        // after the colon.
        int tempPos = ctx.position;
        int nesting = 0;
        boolean sawColon = false;
        while (tempPos < ctx.tokens.size()) {
            TokenType type = ctx.tokens.get(tempPos).type;
            if (type == TokenType.LEFT_PAREN || type == TokenType.LEFT_SQUARE_BRACKET
                    || type == TokenType.LEFT_BRACE) {
                nesting++;
            } else if (type == TokenType.RIGHT_PAREN || type == TokenType.RIGHT_SQUARE_BRACKET
                    || type == TokenType.RIGHT_BRACE) {
                if (nesting == 0) {
                    return false;
                }
                nesting--;
            } else if (nesting == 0 && type == TokenType.COLON) {
                sawColon = true;
            } else if (nesting == 0 && sawColon && type == TokenType.FOR) {
                return true;
            }
            tempPos++;
        }
        return false;
    }

    private static Node parseDictComprehension(ParserContext ctx) {
        Node keyExpr = parseExpression(ctx);
        UtilityParser.consume(ctx, TokenType.COLON, ":", "Expected ':' in dictionary comprehension");
        Node valueExpr = parseExpression(ctx);
        UtilityParser.consume(ctx, TokenType.FOR, "for", "Expected 'for' in comprehension");
        String iterator = UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected iterator variable").value;
        UtilityParser.consume(ctx, TokenType.IN, "in", "Expected 'in' after iterator");
        Node iterable = parseExpression(ctx);
        Node condition = null;
        if (UtilityParser.match(ctx, TokenType.IF, "if")) {
            condition = parseExpression(ctx);
        }
        UtilityParser.consume(ctx, TokenType.RIGHT_BRACE, "}", "Expected '}' to close dictionary comprehension");
        return new DictionaryComprehensionNode(keyExpr, valueExpr, iterator, iterable, condition);
    }

    private static Node parseObjectLiteral(ParserContext ctx) {
        Map<String, Node> properties = new HashMap<>();
        // Opening brace already consumed by parseDictComprehensionOrObject
        while (!UtilityParser.check(ctx, TokenType.RIGHT_BRACE, "}")) {
            String key = parseObjectKey(ctx);
            UtilityParser.consume(ctx, TokenType.COLON, ":", "Expected ':' after property name");
            Node value = parseExpression(ctx);
            properties.put(key, value);
            if (!UtilityParser.check(ctx, TokenType.RIGHT_BRACE, "}")) {
                UtilityParser.consume(ctx, TokenType.COMMA, ",", "Expected ',' after property");
            }
        }
        UtilityParser.consume(ctx, TokenType.RIGHT_BRACE, "}", "Expected '}' after object literal");
        return new ObjectLiteralNode(properties);
    }

    private static String parseObjectKey(ParserContext ctx) {
        if (UtilityParser.check(ctx, TokenType.STRING)) {
            return UtilityParser.consume(ctx, TokenType.STRING, "Expected string key").value;
        }
        return UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected identifier key").value;
    }

    private static Node parseAnonymousFunctionExpression(ParserContext ctx) {
        UtilityParser.consume(ctx, TokenType.LEFT_PAREN, "(", "Expected '(' after 'func'");
        List<ParameterNode> parameters = parseParameters(ctx);
        UtilityParser.consume(ctx, TokenType.RIGHT_PAREN, ")", "Expected ')' after function parameters");

        // Optional return type annotation
        if (UtilityParser.match(ctx, TokenType.ARROW, "->")) {
            UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected return type");
        }

        Node body;
        if (UtilityParser.match(ctx, TokenType.DOUBLE_ARROW, "=>")) {
            body = parseExpression(ctx);
        } else {
            body = StatementParser.parseBlock(ctx);
        }
        return new LambdaExpressionNode(parameters, body);
    }

    public static List<ParameterNode> parseParameters(ParserContext ctx) {
        List<ParameterNode> params = new ArrayList<>();
        if (!UtilityParser.check(ctx, TokenType.RIGHT_PAREN, ")")) {
            do {
                String name = UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected parameter name").value;
                String type = null;
                Node defaultValue = null;
                
                // Parse optional type annotation
                if (UtilityParser.match(ctx, TokenType.COLON, ":")) {
                    type = UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected parameter type").value;
                }
                
                // Parse optional default value
                if (UtilityParser.match(ctx, TokenType.EQUAL, "=")) {
                    defaultValue = parseExpression(ctx);
                }
                
                params.add(new ParameterNode(name, type, defaultValue));
            } while (UtilityParser.match(ctx, TokenType.COMMA, ","));
        }
        return params;
    }

    public static Node parseExpressionOnly(ParserContext ctx) {
        return parseExpression(ctx);
    }

    private static RuntimeException parserError(Token token, String message) {
        int line = token != null ? token.line : -1;
        int column = token != null ? token.column : -1;
        if (line > 0 && column > 0) {
            return new RuntimeException(message + " at line " + line + ", column " + column);
        }
        if (line > 0) {
            return new RuntimeException(message + " at line " + line + ", column 1");
        }
        return new RuntimeException(message);
    }

    private boolean match() {
        if (parserContext.isAtEnd())
            return false;
        if (parserContext.peek().type == TokenType.FUNC) {
            parserContext.position++;
            return true;
        }
        return false;
    }

}
