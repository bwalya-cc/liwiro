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

class TryCatchControlFlowRegressionTest {
    @Test
    void returnInsideTryDoesNotFallIntoCatch() {
        Object result = evaluate(
                "func delete_flow() {\n"
                        + "    try {\n"
                        + "        return {status: \"returned\"};\n"
                        + "    } catch (e) {\n"
                        + "        return {status: e.type};\n"
                        + "    }\n"
                        + "}\n"
                        + "\n"
                        + "delete_flow().status;\n");

        assertEquals("returned", result);
    }

    @Test
    void nestedTryElseReturnDoesNotLeakIntoOuterCatch() {
        Object result = evaluate(
                "func delete_flow() {\n"
                        + "    try {\n"
                        + "        try {\n"
                        + "            let ok = true;\n"
                        + "        } catch (e) {\n"
                        + "            return {status: \"inner-catch\"};\n"
                        + "        } else {\n"
                        + "            return {status: \"inner-else\"};\n"
                        + "        }\n"
                        + "    } catch (e) {\n"
                        + "        return {status: e.message};\n"
                        + "    }\n"
                        + "}\n"
                        + "\n"
                        + "delete_flow().status;\n");

        assertEquals("inner-else", result);
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
