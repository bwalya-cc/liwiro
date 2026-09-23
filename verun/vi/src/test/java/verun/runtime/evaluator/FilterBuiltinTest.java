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

class FilterBuiltinTest {
    @Test
    void filtersListWithPredicate() {
        assertEquals(List.of(2, 4), evaluate("filter((value) => value % 2 == 0, [1, 2, 3, 4]);"));
    }

    @Test
    void mapAndFilterAcceptAllLanguageIterables() {
        assertEquals(List.of("A", "B"), evaluate("map((value) => value.toUpper(), \"ab\");"));
        assertEquals(List.of("first"), evaluate("filter((value) => value == \"first\", {first: 1, second: 2});"));
    }

    @Test
    void rejectsNonCallablePredicate() {
        assertThrows(RuntimeException.class, () -> evaluate("filter(1, [1, 2]);"));
    }

    private Object evaluate(String source) {
        List<Token> tokens = new Lexer(source).tokenize();
        Node ast = new Parser(tokens, source).parse();
        return new Evaluator(false, tokens, source).evaluate(ast);
    }
}
