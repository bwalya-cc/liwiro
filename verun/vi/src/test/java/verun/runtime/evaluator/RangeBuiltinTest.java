// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;
import verun.runtime.ast.Node;
import verun.runtime.lexer.Lexer;
import verun.runtime.lexer.Token;
import verun.runtime.parser.Parser;

class RangeBuiltinTest {
    @Test
    void supportsExplicitPositiveAndNegativeSteps() {
        assertEquals(List.of(1, 3, 5), evaluate("range(1, 7, 2);"));
        assertEquals(List.of(7, 4, 1), evaluate("range(7, 0, -3);"));
    }

    @Test
    void rejectsZeroStep() {
        assertThrows(RuntimeException.class, () -> evaluate("range(1, 3, 0);"));
    }

    private Object evaluate(String source) {
        List<Token> tokens = new Lexer(source).tokenize();
        Node ast = new Parser(tokens, source).parse();
        return new Evaluator(false, tokens, source).evaluate(ast);
    }
}
