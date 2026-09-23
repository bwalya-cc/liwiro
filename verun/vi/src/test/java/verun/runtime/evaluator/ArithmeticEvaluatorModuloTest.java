// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import org.junit.jupiter.api.Test;
import verun.runtime.ast.Node;
import verun.runtime.lexer.Lexer;
import verun.runtime.lexer.Token;
import verun.runtime.parser.Parser;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

class ArithmeticEvaluatorModuloTest {
    @Test
    void integerModuloReturnsIntegerValue() {
        Object result = evaluate("7 % 3;\n");

        assertInstanceOf(Integer.class, result);
        assertEquals(1, result);
    }

    @Test
    void floatModuloStillReturnsFloatingPointValue() {
        Object result = evaluate("7.5 % 3;\n");

        assertInstanceOf(Double.class, result);
        assertEquals(1.5d, (Double) result);
    }

    private Object evaluate(String script) {
        Lexer lexer = new Lexer(script);
        List<Token> tokens = lexer.tokenize();
        Parser parser = new Parser(tokens, script);
        Node ast = parser.parse();
        Evaluator evaluator = new Evaluator(false, tokens, script);
        return evaluator.evaluate(ast);
    }
}
