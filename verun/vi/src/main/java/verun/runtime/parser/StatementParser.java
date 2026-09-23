// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.parser;

import verun.runtime.ast.*;
import verun.runtime.lexer.Token;
import verun.runtime.lexer.TokenType;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class StatementParser {

    public static Node parseProgram(List<Token> tokens, String sourceText, String[] sourceLines) {
        ParserContext ctx = new ParserContext(tokens, sourceText);
        List<Node> statements = new ArrayList<>();
        while (!ctx.isAtEnd()) {
            if (UtilityParser.check(ctx, TokenType.COMMENT) || UtilityParser.check(ctx, TokenType.MULTILINE_COMMENT)) {
                ctx.position++;
                continue;
            }
            statements.add(parseStatement(ctx));
        }
        return new BlockNode(statements);
    }

    public static Node parseStatement(ParserContext ctx) {
        while (UtilityParser.match(ctx, TokenType.COMMENT) || UtilityParser.match(ctx, TokenType.SEMICOLON, ";")) {
            // Skip stray semicolons and comments.
        }
        if (ctx.isAtEnd()) {
            return new NoOpNode();
        }
        if (UtilityParser.check(ctx, TokenType.CLASS, "class")) {
            UtilityParser.match(ctx, TokenType.CLASS, "class");
            return parseClassDeclaration(ctx);
        }
        if (UtilityParser.check(ctx, TokenType.ENUM, "enum")) {
            UtilityParser.match(ctx, TokenType.ENUM, "enum");
            return parseEnumDeclaration(ctx);
        }
        if (UtilityParser.match(ctx, TokenType.TRY, "try")) {
            return parseTryStatement(ctx);
        }
        if (UtilityParser.match(ctx, TokenType.THROW, "throw")) {
            return parseThrowStatement(ctx);
        }
        if (UtilityParser.check(ctx, TokenType.IMPORT, "import")) {
            ctx.position++;
            UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected module name after 'import'");
            UtilityParser.consume(ctx, TokenType.SEMICOLON, ";", "Expected ';' after import statement");
            return new NoOpNode();
        }
        if (UtilityParser.check(ctx, TokenType.IDENTIFIER)) {
            int savedPos = ctx.position;
            if (UtilityParser.match(ctx, TokenType.IDENTIFIER)
                    && UtilityParser.match(ctx, TokenType.IMPORT, "import")) {
                if (UtilityParser.check(ctx, TokenType.STAR, "*")) {
                    ctx.position++;
                } else if (UtilityParser.check(ctx, TokenType.LEFT_BRACE, "{")) {
                    ctx.position++;
                    while (!UtilityParser.check(ctx, TokenType.RIGHT_BRACE, "}") && !ctx.isAtEnd()) {
                        if (UtilityParser.check(ctx, TokenType.IDENTIFIER)) {
                            ctx.position++;
                        } else if (UtilityParser.check(ctx, TokenType.COMMA, ",")) {
                            ctx.position++;
                        } else {
                            throw parserError(ctx.peek(), "Expected identifier list in import");
                        }
                    }
                    UtilityParser.consume(ctx, TokenType.RIGHT_BRACE, "}", "Expected '}' in import list");
                }
                while (!UtilityParser.check(ctx, TokenType.SEMICOLON, ";") && !ctx.isAtEnd()) {
                    ctx.position++;
                }
                UtilityParser.consume(ctx, TokenType.SEMICOLON, ";", "Expected ';' after import statement");
                return new NoOpNode();
            }
            ctx.position = savedPos;
        }
        if (UtilityParser.match(ctx, TokenType.IF, "if")) {
            return parseIfStatement(ctx);
        } else if (UtilityParser.match(ctx, TokenType.FOR, "for")) {
            return parseForLoop(ctx);
        }

        else if (UtilityParser.match(ctx, TokenType.WHILE, "while")) {
            return parseWhileLoop(ctx);
        }

        else if (UtilityParser.match(ctx, TokenType.MATCH, "match")) {
            return parseMatchStatement(ctx);
        }

        else if (UtilityParser.match(ctx, TokenType.FUNC, "func")) {
            return parseFunctionDeclaration(ctx, false);
        }

        else if (UtilityParser.match(ctx, TokenType.RETURN, "return")) {
            return parseReturnStatement(ctx);
        }

        else if (UtilityParser.match(ctx, TokenType.BREAK, "break")) {
            UtilityParser.match(ctx, TokenType.SEMICOLON, ";");
            return new BreakStatementNode();
        }

        else if (UtilityParser.match(ctx, TokenType.CONTINUE, "continue")) {
            UtilityParser.match(ctx, TokenType.SEMICOLON, ";");
            return new ContinueStatementNode();
        }

        else if (UtilityParser.match(ctx, TokenType.CONST, "const")) {
            return parseConstantDeclaration(ctx);
        }

        if (UtilityParser.match(ctx, TokenType.LET) || UtilityParser.match(ctx, TokenType.VAR)) {
            return parseVariableDeclaration(ctx); // No extra parameters
        }

        return parseExpressionStatement(ctx);
    }

    public static Node parseBlockOrExpression(ParserContext ctx) {
        if (UtilityParser.check(ctx, TokenType.LEFT_BRACE, "{")) {
            return parseBlock(ctx);
        }
        return ExpressionParser.parseExpression(ctx);
    }

    private static Node parseTryStatement(ParserContext ctx) {
        Node tryBlock = parseBlock(ctx);

        String errorVar = null;
        Node catchBlock = null;
        if (UtilityParser.match(ctx, TokenType.CATCH, "catch")) {
            UtilityParser.consume(ctx, TokenType.LEFT_PAREN, "(", "Expected '(' after catch");
            errorVar = UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected error variable").value;
            UtilityParser.consume(ctx, TokenType.RIGHT_PAREN, ")", "Expected ')'");
            catchBlock = parseBlock(ctx);
        }

        Node elseBlock = null;
        if (UtilityParser.match(ctx, TokenType.ELSE, "else")) {
            elseBlock = parseBlock(ctx);
        }

        Node completeBlock = null;
        if (UtilityParser.match(ctx, TokenType.COMPLETE, "complete")) {
            completeBlock = parseBlock(ctx);
        }

        return new TryCatchNode(tryBlock, errorVar, catchBlock, elseBlock, completeBlock);
    }

    private static Node parseTryCatch(ParserContext ctx) {
        UtilityParser.consume(ctx, TokenType.TRY, "try", "Expected 'try'");
        Node tryBlock = parseBlock(ctx);

        String errorVar = null;
        Node catchBlock = null;
        if (UtilityParser.match(ctx, TokenType.CATCH, "catch")) {
            UtilityParser.consume(ctx, TokenType.LEFT_PAREN, "(", "Expected '(' after catch");
            errorVar = UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected error variable").value;
            UtilityParser.consume(ctx, TokenType.RIGHT_PAREN, ")", "Expected ')'");
            catchBlock = parseBlock(ctx);
        }

        Node elseBlock = null;
        if (UtilityParser.match(ctx, TokenType.ELSE, "else")) {
            elseBlock = parseBlock(ctx);
        }

        Node completeBlock = null;
        if (UtilityParser.match(ctx, TokenType.COMPLETE, "complete")) {
            completeBlock = parseBlock(ctx);
        }

        return new TryCatchNode(tryBlock, errorVar, catchBlock, elseBlock, completeBlock);
    }

    private static Node parseThrowStatement(ParserContext ctx) {
        verun.runtime.lexer.Token throwToken = ctx.previous();
        Node expression = ExpressionParser.parseExpression(ctx);
        UtilityParser.consume(ctx, TokenType.SEMICOLON, ";", "Expected ';' after throw");
        return new ThrowStatementNode(
                expression,
                throwToken == null ? -1 : throwToken.line,
                throwToken == null ? -1 : throwToken.column);
    }

    private static Node parseClassDeclaration(ParserContext ctx) {
        String className = UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected class name after 'class'").value;
        List<ParameterNode> constructorParameters = new ArrayList<>();
        if (UtilityParser.match(ctx, TokenType.LEFT_PAREN, "(")) {
            constructorParameters = ExpressionParser.parseParameters(ctx);
            UtilityParser.consume(ctx, TokenType.RIGHT_PAREN, ")", "Expected ')' after class parameters");
        }
        Node parent = null;
        if (UtilityParser.match(ctx, TokenType.EXTENDS, "extends")) {
            parent = new IdentifierNode(
                    UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected parent class name").value);
        }
        Node vdbBinding = null;
        if (UtilityParser.match(ctx, TokenType.BIND_ARROW, "<->")) {
            vdbBinding = ExpressionParser.parseExpression(ctx);
        } else if (UtilityParser.check(ctx, TokenType.LESS_THAN, "<")
                && UtilityParser.lookahead(ctx, 1) != null && UtilityParser.lookahead(ctx, 1).type == TokenType.ARROW) {
            ctx.position += 2; // consume < and ->
            vdbBinding = ExpressionParser.parseExpression(ctx);
        }
        Node body = parseClassBody(ctx);
        if (UtilityParser.check(ctx, TokenType.SEMICOLON, ";")) {
            UtilityParser.match(ctx, TokenType.SEMICOLON, ";");
        }
        return new ClassDeclarationNode(className, constructorParameters, parent, vdbBinding, body);
    }

    private static Node parseEnumDeclaration(ParserContext ctx) {
        String enumName = UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected enum name after 'enum'").value;
        UtilityParser.consume(ctx, TokenType.LEFT_BRACE, "{", "Expected '{' to start enum body");

        List<EnumMemberNode> members = new ArrayList<>();
        int ordinal = 0;
        while (!UtilityParser.check(ctx, TokenType.RIGHT_BRACE, "}")) {
            while (UtilityParser.match(ctx, TokenType.COMMENT)
                    || UtilityParser.match(ctx, TokenType.SEMICOLON, ";")
                    || UtilityParser.match(ctx, TokenType.COMMA, ",")) {
                // Skip separators and comments inside enum bodies.
            }
            if (UtilityParser.check(ctx, TokenType.RIGHT_BRACE, "}")) {
                break;
            }
            String memberName = UtilityParser.consume(
                    ctx,
                    TokenType.IDENTIFIER,
                    "Expected enum member name in enum '" + enumName + "'").value;
            Node value = null;
            if (UtilityParser.match(ctx, TokenType.EQUAL, "=")) {
                value = ExpressionParser.parseExpression(ctx);
            }
            members.add(new EnumMemberNode(memberName, value, ordinal));
            ordinal++;
            UtilityParser.match(ctx, TokenType.COMMA, ",");
            UtilityParser.match(ctx, TokenType.SEMICOLON, ";");
        }

        UtilityParser.consume(ctx, TokenType.RIGHT_BRACE, "}", "Expected '}' to end enum body");
        if (UtilityParser.check(ctx, TokenType.SEMICOLON, ";")) {
            UtilityParser.match(ctx, TokenType.SEMICOLON, ";");
        }
        return new EnumDeclarationNode(enumName, members);
    }

    private static Node parseClassBody(ParserContext ctx) {
        UtilityParser.consume(ctx, TokenType.LEFT_BRACE, "{", "Expected '{' to start class body");
        List<Node> members = new ArrayList<>();
        while (!UtilityParser.check(ctx, TokenType.RIGHT_BRACE, "}")) {
            members.add(parseMemberDeclaration(ctx));
        }
        UtilityParser.consume(ctx, TokenType.RIGHT_BRACE, "}", "Expected '}' to end class body");
        return new BlockNode(members);
    }

    private static Node parseMemberDeclaration(ParserContext ctx) {
        while (UtilityParser.match(ctx, TokenType.SEMICOLON, ";")) {
        }
        while (UtilityParser.check(ctx, TokenType.COMMENT)) {
            ctx.position++;
        }
        while (ctx.position < ctx.tokens.size() &&
                ((ctx.tokens.get(ctx.position).type == TokenType.AT_SYMBOL
                        && ctx.tokens.get(ctx.position).value.equals("@"))
                        || (ctx.tokens.get(ctx.position).type == TokenType.OVERRIDE
                                && ctx.tokens.get(ctx.position).value.equals("override")))) {
            ctx.position++;
        }
        boolean isStatic = UtilityParser.match(ctx, TokenType.STATIC, "static");
        Node member;
        if (UtilityParser.check(ctx, TokenType.IDENTIFIER) && UtilityParser.lookahead(ctx, 1) != null &&
                UtilityParser.lookahead(ctx, 1).type == TokenType.LEFT_PAREN
                && UtilityParser.lookahead(ctx, 1).value.equals("(")) {
            member = parseImplicitFunctionDeclaration(ctx, isStatic);
        }

        else if (UtilityParser.match(ctx, TokenType.FUNC, "func")) {
            member = parseFunctionDeclaration(ctx, isStatic);
        } else {
            member = parseExpressionStatement(ctx);
        }
        if (UtilityParser.check(ctx, TokenType.SEMICOLON, ";")) {
            UtilityParser.match(ctx, TokenType.SEMICOLON, ";");
        }
        return member;
    }

    private static Node parseImplicitFunctionDeclaration(ParserContext ctx, boolean isStatic) {
        String name = UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected function name").value;
        UtilityParser.consume(ctx, TokenType.LEFT_PAREN, "(", "Expected '(' after function name");
        List<ParameterNode> parameters = ExpressionParser.parseParameters(ctx);
        UtilityParser.consume(ctx, TokenType.RIGHT_PAREN, ")", "Expected ')' after parameters");
        String returnType = null;
        if (UtilityParser.match(ctx, TokenType.ARROW, "->")) {
            returnType = UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected return type").value;
        }
        Node body = parseBlock(ctx);
        return new FunctionDeclarationNode(name, parameters, returnType, body, isStatic);
    }

    private static Node parseFunctionDeclaration(ParserContext ctx, boolean isStatic) {
        // Track function entry
        boolean previousFunctionState = ctx.isInsideFunction;
        ctx.isInsideFunction = true;

        try {
            String name = UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected function name").value;
            UtilityParser.consume(ctx, TokenType.LEFT_PAREN, "(", "Expected '(' after function name");
            List<ParameterNode> parameters = ExpressionParser.parseParameters(ctx);
            UtilityParser.consume(ctx, TokenType.RIGHT_PAREN, ")", "Expected ')' after parameters");

            String returnType = null;
            if (UtilityParser.match(ctx, TokenType.ARROW, "->")) {
                returnType = UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected return type").value;
            }

            Node body;
            if (UtilityParser.match(ctx, TokenType.DOUBLE_ARROW, "=>")) {
                body = ExpressionParser.parseExpression(ctx);
                UtilityParser.consume(ctx, TokenType.SEMICOLON, ";", "Expected ';' after arrow function");
            } else {
                body = parseBlock(ctx);
            }
            return new FunctionDeclarationNode(name, parameters, returnType, body, isStatic);
        } finally {
            // Restore previous context state
            ctx.isInsideFunction = previousFunctionState;
        }
    }

    private static Node parseReturnStatement(ParserContext ctx) {
        if (UtilityParser.match(ctx, TokenType.SEMICOLON, ";")) {
            return new ReturnStatementNode(null);
        }
        Node expr = ExpressionParser.parseExpression(ctx);
        // Ensure parentheses are balanced
        if (ctx.parenthesisCount != 0) {
            throw parserError(ctx.peek(), "Unbalanced parentheses in return statement");
        }
        UtilityParser.consume(ctx, TokenType.SEMICOLON, ";", "Expected ';' after return");
        return new ReturnStatementNode(expr);
    }

    public static Node parseIfStatement(ParserContext ctx) {
        // 'if' token already consumed by parseStatement's match, so start with '('
        UtilityParser.consume(ctx, TokenType.LEFT_PAREN, "(", "Expected '(' after 'if'");
        Node condition = ExpressionParser.parseExpression(ctx);
        UtilityParser.consume(ctx, TokenType.RIGHT_PAREN, ")", "Expected ')' after condition");
        Node thenBranch = parseBlock(ctx);

        List<ElseIfClauseNode> altClauses = new ArrayList<>();
        while (UtilityParser.match(ctx, TokenType.ALT, "alt")) {
            UtilityParser.consume(ctx, TokenType.LEFT_PAREN, "(", "Expected '(' after 'alt'");
            Node altCondition = ExpressionParser.parseExpression(ctx);
            UtilityParser.consume(ctx, TokenType.RIGHT_PAREN, ")", "Expected ')' after alt condition");
            Node altBody = parseBlock(ctx);
            altClauses.add(new ElseIfClauseNode(altCondition, altBody));
        }

        Node elseBranch = null;
        if (UtilityParser.match(ctx, TokenType.ELSE, "else")) {
            // Accept the conventional `else if (...)` spelling in addition to
            // Versa's concise `alt (...)` form.
            if (UtilityParser.match(ctx, TokenType.IF, "if")) {
                elseBranch = parseIfStatement(ctx);
            } else {
                elseBranch = parseBlock(ctx);
            }
        }

        return new IfStatementNode(condition, thenBranch, altClauses, elseBranch);
    }

    public static Node parseBlock(ParserContext ctx) {
        if (UtilityParser.match(ctx, TokenType.LEFT_BRACE, "{")) {
            List<Node> statements = new ArrayList<>();
            while (!UtilityParser.check(ctx, TokenType.RIGHT_BRACE, "}") && !ctx.isAtEnd()) {
                statements.add(parseStatement(ctx));
            }
            UtilityParser.consume(ctx, TokenType.RIGHT_BRACE, "}", "Expected '}' after block");
            return new BlockNode(statements);
        }
        return parseStatement(ctx);
    }

    private static Node parseBlockOrStatement(ParserContext ctx) {
        if (UtilityParser.check(ctx, TokenType.LEFT_BRACE, "{")) {
            return parseBlock(ctx);
        } else {
            return parseStatement(ctx);
        }
    }

    private static Node parseMatchStatement(ParserContext ctx) {
        UtilityParser.consume(ctx, TokenType.LEFT_PAREN, "(", "Expected '(' after match");
        Node expression = ExpressionParser.parseExpression(ctx);
        UtilityParser.consume(ctx, TokenType.RIGHT_PAREN, ")", "Expected ')' after match expression");
        UtilityParser.consume(ctx, TokenType.LEFT_BRACE, "{", "Expected '{' to start match block");
        List<MatchCaseNode> cases = new ArrayList<>();
        while (!UtilityParser.check(ctx, TokenType.RIGHT_BRACE, "}")) {
            UtilityParser.consume(ctx, TokenType.CASE, "case", "Expected 'case' in match block");
            Node pattern = ExpressionParser.parseExpression(ctx);
            UtilityParser.consume(ctx, TokenType.COLON, ":", "Expected ':' after match case pattern");
            Node body = parseBlock(ctx);
            cases.add(new MatchCaseNode(pattern, body));
        }
        Node defaultCase = null;
        if (UtilityParser.match(ctx, TokenType.UNDERSCORE, "_")) {
            UtilityParser.consume(ctx, TokenType.COLON, ":", "Expected ':' after default case");
            defaultCase = parseBlock(ctx);
        }
        UtilityParser.consume(ctx, TokenType.RIGHT_BRACE, "}", "Expected '}' to close match block");
        return new MatchStatementNode(expression, cases, defaultCase);
    }

    private static Node parseForLoop(ParserContext ctx) {
        // Check if this is a Python-style for loop without parentheses
        if (UtilityParser.check(ctx, TokenType.IDENTIFIER) && 
            (UtilityParser.lookaheadIs(ctx, 1, TokenType.IN) || UtilityParser.lookaheadIs(ctx, 1, TokenType.COLON))) {
            // Python-style: for variable in expression:
            String varName = ctx.peek().value;
            ctx.position++; // consume variable name
            
            if (UtilityParser.match(ctx, TokenType.IN, "in") || UtilityParser.match(ctx, TokenType.COLON, ":")) {
                Node iterable = ExpressionParser.parseExpression(ctx);
                Node body = parseBlock(ctx);
                Node initializer = new IdentifierNode(varName);
                return new ForEachLoopNode(initializer, iterable, body);
            }
        }
        
        // Traditional C-style for loop
        UtilityParser.consume(ctx, TokenType.LEFT_PAREN, "(", "Expected '(' after 'for'");
        Node initializer = parseOptionalForInitializer(ctx);
        if (isForEachLoop(ctx, initializer)) {
            return parseForEachLoop(ctx, initializer);
        } else {
            return parseTraditionalForLoop(ctx, initializer);
        }
    }

    private static boolean isForEachLoop(ParserContext ctx, Node initializer) {
        return (initializer instanceof VariableDeclarationNode || initializer instanceof IdentifierNode)
                && (UtilityParser.check(ctx, TokenType.IN, "in") || UtilityParser.check(ctx, TokenType.COLON, ":"));
    }

    private static Node parseForEachLoop(ParserContext ctx, Node initializer) {
        String varName;

        if (initializer instanceof VariableDeclarationNode) {
            varName = ((VariableDeclarationNode) initializer).name;
        } else if (initializer instanceof IdentifierNode) {
            varName = ((IdentifierNode) initializer).name;
        } else {
            throw parserError(ctx.peek(), "Invalid loop variable: expected VariableDeclarationNode or IdentifierNode");
        }

        if (UtilityParser.match(ctx, TokenType.IN, "in") || UtilityParser.match(ctx, TokenType.COLON, ":")) {
            Node iterable = ExpressionParser.parseExpression(ctx);
            UtilityParser.consume(ctx, TokenType.RIGHT_PAREN, ")", "Expected ')'");
            Node body = parseBlock(ctx);
            return new ForEachLoopNode(initializer, iterable, body);
        } else {
            throw parserError(ctx.peek(), "Expected 'in' or ':' in for-each loop");
        }
    }

    // In StatementParser.java, modify parseTraditionalForLoop
    private static Node parseTraditionalForLoop(ParserContext ctx, Node initializer) {
        UtilityParser.consume(ctx, TokenType.SEMICOLON, ";", "Expected ';' after initializer");
        Node condition = ExpressionParser.parseExpression(ctx);
        UtilityParser.consume(ctx, TokenType.SEMICOLON, ";", "Expected ';' after condition");
        Node increment = ExpressionParser.parseExpression(ctx);
        UtilityParser.consume(ctx, TokenType.RIGHT_PAREN, ")", "Expected ')'");
        Node body = parseBlock(ctx);
        return new ForLoopNode(initializer, condition, increment, body);
    }

    private static Node parseOptionalForInitializer(ParserContext ctx) {
        if (UtilityParser.check(ctx, TokenType.SEMICOLON, ";"))
            return null;
        // Fix: Add UtilityParser prefix to lookahead()
        if (UtilityParser.check(ctx, TokenType.IDENTIFIER) && UtilityParser.lookahead(ctx, 1) != null &&
                (UtilityParser.lookahead(ctx, 1).type == TokenType.IN
                        || UtilityParser.lookahead(ctx, 1).type == TokenType.COLON)) {
            return new IdentifierNode(
                    UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected loop variable name").value);
        }
        if (UtilityParser.match(ctx, TokenType.LET, "let") || UtilityParser.match(ctx, TokenType.VAR, "var")) {
            return parseForLoopVariableDeclaration(ctx);
        } else {
            return ExpressionParser.parseExpression(ctx);
        }
    }

    private static Node parseForLoopVariableDeclaration(ParserContext ctx) {
        String name = UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected variable name").value;
        String type = null;
        if (UtilityParser.match(ctx, TokenType.COLON, ":")) {
            type = UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected type annotation").value;
        }
        Node initializer = null;
        if (UtilityParser.match(ctx, TokenType.EQUAL, "=")) {
            initializer = ExpressionParser.parseExpression(ctx);
        }
        return new VariableDeclarationNode(name, type, initializer);
    }

    public static Node parseVariableDeclaration(ParserContext ctx) {
        String name = UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected variable name").value;
        String type = null;
        if (UtilityParser.match(ctx, TokenType.COLON)) {
            type = UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected type annotation").value;
        }

        Node initializer = null;
        if (UtilityParser.match(ctx, TokenType.EQUAL)) {
            initializer = ExpressionParser.parseExpression(ctx);
        }
        UtilityParser.consume(ctx, TokenType.SEMICOLON, ";", "Expected ';' after variable declaration");
        return new VariableDeclarationNode(name, type, initializer);
    }

    private static Node parseExpressionStatement(ParserContext ctx) {
        Node expr = ExpressionParser.parseExpression(ctx);
        // Semicolons remain supported, but a final expression or an expression
        // immediately before a closing block may use conventional ASI-style
        // termination (useful for short scripts and generated handlers).
        if (!UtilityParser.match(ctx, TokenType.SEMICOLON, ";")
                && !ctx.isAtEnd()
                && !UtilityParser.check(ctx, TokenType.RIGHT_BRACE, "}")) {
            throw parserError(ctx.peek(), "Expected ';' after expression");
        }
        return new ExpressionStatementNode(expr);
    }

    private static Node parseConstantDeclaration(ParserContext ctx) {
        String name = UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected constant name").value;
        String type = null;
        if (UtilityParser.match(ctx, TokenType.COLON, ":")) {
            type = UtilityParser.consume(ctx, TokenType.IDENTIFIER, "Expected type annotation").value;
        }
        UtilityParser.consume(ctx, TokenType.EQUAL, "=", "Expected '=' in constant declaration");
        Node initializer = ExpressionParser.parseExpression(ctx);
        UtilityParser.consume(ctx, TokenType.SEMICOLON, ";", "Expected ';' after constant declaration");
        return new ConstantDeclarationNode(name, type, initializer);
    }

    public static Node parseWhileLoop(ParserContext ctx) {
        UtilityParser.consume(ctx, TokenType.LEFT_PAREN, "(", "Expected '(' after while");
        Node condition = ExpressionParser.parseExpression(ctx);
        UtilityParser.consume(ctx, TokenType.RIGHT_PAREN, ")", "Expected ')' after while condition");
        Node body = parseBlock(ctx);
        return new WhileLoopNode(condition, body);
    }

    private static Node parseWhileStatement(ParserContext ctx) {
        UtilityParser.consume(ctx, TokenType.WHILE, "while");
        Node condition = ExpressionParser.parseExpression(ctx);
        Node body = parseBlockOrStatement(ctx);
        return new WhileLoopNode(condition, body);
    }

    public static Node parseExpressionOnly(ParserContext ctx) {
        return ExpressionParser.parseExpression(ctx);
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
}
