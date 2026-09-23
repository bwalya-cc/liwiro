// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;
import verun.runtime.ast.Node;
import verun.runtime.lexer.Lexer;
import verun.runtime.lexer.Token;
import verun.runtime.parser.Parser;

class CoreBuiltinAliasTest {
    @Test
    void lenIsTheConventionalAliasForHistoricalLengBuiltin() {
        String source = "let values = [1, 2, 3]; len(values);";
        List<Token> tokens = new Lexer(source).tokenize();
        Node program = new Parser(tokens, source).parse();
        Object result = new Evaluator(false, tokens, source).evaluate(program);
        assertEquals(3, result);
    }
}
