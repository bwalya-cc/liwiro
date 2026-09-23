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

class EvaluatorEnumTest {
    @Test
    void enumMembersExposeNamesOrdinalsAndDefaultValues() {
        Object result = evaluate(
                "enum Status { OPEN, CLOSED, FAILED };\n"
                        + "[type(Status), type(Status.OPEN), Status.name, Status.OPEN.name, Status.OPEN.ordinal, Status.CLOSED.value, Status.names(), Status.values()];\n");

        assertEquals(
                List.of("enum", "enum_value", "Status", "OPEN", 0, 1, List.of("OPEN", "CLOSED", "FAILED"), List.of(0, 1, 2)),
                result);
    }

    @Test
    void enumSupportsExplicitValuesEqualityAndDisplayString() {
        Object result = evaluate(
                "enum HttpStatus {\n"
                        + "    OK = 200,\n"
                        + "    NOT_FOUND = 404,\n"
                        + "    FALLBACK = \"fallback\"\n"
                        + "};\n"
                        + "[HttpStatus.OK.value, HttpStatus.NOT_FOUND.value, HttpStatus.OK == HttpStatus.OK, HttpStatus.OK != HttpStatus.NOT_FOUND, str(HttpStatus.OK), is_type(HttpStatus, \"enum\"), is_type(HttpStatus.OK, \"enum_member\")];\n");

        assertEquals(List.of(200, 404, true, true, "HttpStatus.OK", true, true), result);
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
