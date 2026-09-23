// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import org.junit.jupiter.api.Test;
import verun.runtime.ast.Node;
import verun.runtime.lexer.Lexer;
import verun.runtime.lexer.Token;
import verun.runtime.parser.Parser;

import java.util.List;
import java.util.Arrays;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class EvaluatorControlFlowAndIndexingTest {
    @Test
    void constBindingsAreImmutable() {
        RuntimeException error = assertThrows(RuntimeException.class, () -> evaluate(
                "const answer = 42;\n"
                        + "answer = 7;\n"));
        assertTrue(error.getMessage().contains("Cannot assign to constant"));
    }

    @Test
    void breakAndContinueWorkWithOptionalFinalSemicolons() {
        Object result = evaluate(
                "let values = [];\n"
                        + "for (let i = 0; i < 6; i = i + 1) {\n"
                        + "  if (i == 1) { continue; }\n"
                        + "  if (i == 4) { break; }\n"
                        + "  values.add(i)\n"
                        + "}\n"
                        + "values;");
        assertEquals(List.of(0, 2, 3), result);
    }

    @Test
    void breakAndContinueWorkInForEachLoops() {
        Object result = evaluate(
                "let values = [1, 2, 3, 4, 5];\n"
                        + "let seen = [];\n"
                        + "for (let value in values) {\n"
                        + "  if (value == 2) { continue; }\n"
                        + "  if (value == 5) { break; }\n"
                        + "  seen.add(value);\n"
                        + "}\n"
                        + "seen;\n");
        assertEquals(List.of(1, 3, 4), result);
    }

    @Test
    void sliceReturnsSubListInsteadOfSingleElement() {
        Object ranged = evaluate(
                "let values = [10, 20, 30];\n"
                        + "values[1:3];\n");
        Object openEnded = evaluate(
                "let values = [10, 20, 30];\n"
                        + "values[1:];\n");

        assertEquals(List.of(20, 30), ranged);
        assertEquals(List.of(20, 30), openEnded);
    }

    @Test
    void sliceAssignmentReplacesAndResizesLists() {
        Object result = evaluate(
                "let values = [1, 2, 3, 4];\n"
                        + "values[1:3] = [20, 30, 31];\n"
                        + "values[0:1] = [];\n"
                        + "values[-1:] = [99, 100];\n"
                        + "values;\n");

        assertEquals(List.of(20, 30, 31, 99, 100), result);
    }

    @Test
    void sliceAssignmentCopiesSelfReferentialReplacementBeforeMutation() {
        Object result = evaluate(
                "let values = [1, 2, 3];\n"
                        + "values[1:2] = values;\n"
                        + "values;\n");

        assertEquals(List.of(1, 1, 2, 3, 3), result);
    }

    @Test
    void sliceAssignmentRejectsImmutableStringsAndNonLists() {
        RuntimeException stringError = assertThrows(RuntimeException.class, () -> evaluate(
                "let value = \"abc\";\nvalue[1:2] = [\"x\"];\n"));
        assertTrue(stringError.getMessage().contains("strings are immutable"));

        RuntimeException scalarError = assertThrows(RuntimeException.class, () -> evaluate(
                "let value = [1, 2];\nvalue[:] = 3;\n"));
        assertTrue(scalarError.getMessage().contains("requires a list"));
    }

    @Test
    void steppedSlicesSupportForwardAndReverseTraversal() {
        Object result = evaluate(
                "let values = [0, 1, 2, 3, 4, 5];\n"
                        + "let forward = values[::2];\n"
                        + "let reverse = values[5:0:-2];\n"
                        + "let text = \"abcdef\"[1:6:2];\n"
                        + "[forward, reverse, text];\n");

        assertEquals(List.of(List.of(0, 2, 4), List.of(5, 3, 1), "bdf"), result);
    }

    @Test
    void steppedSliceAssignmentRequiresMatchingReplacementLength() {
        Object result = evaluate(
                "let values = [0, 1, 2, 3, 4, 5];\n"
                        + "values[::2] = [10, 20, 40];\n"
                        + "values;\n");
        assertEquals(List.of(10, 1, 20, 3, 40, 5), result);

        RuntimeException error = assertThrows(RuntimeException.class, () -> evaluate(
                "let values = [0, 1, 2, 3];\nvalues[::2] = [9];\n"));
        assertTrue(error.getMessage().contains("replacement list of length 2"));
    }

    @Test
    void bareReturnExitsFunctionWithNull() {
        Object result = evaluate(
                "func stop_early(flag) {\n"
                        + "  if (flag) { return; }\n"
                        + "  return 42;\n"
                        + "}\n"
                        + "[stop_early(true), stop_early(false)];\n");

        assertEquals(Arrays.asList(null, 42), result);
    }

    @Test
    void dictionaryComprehensionsAcceptStringsAndSetsAndRejectScalars() {
        Object result = evaluate(
                "let from_text = {x: x for x in \"ab\"};\n"
                        + "let from_set = {x: x * 2 for x in set([1, 2])};\n"
                        + "[from_text.a, from_text.b, from_set[1], from_set[2]];\n");

        assertEquals(Arrays.asList("a", "b", 2, 4), result);

        RuntimeException error = assertThrows(RuntimeException.class, () -> evaluate(
                "let invalid = {x: x for x in 42};\n"));
        assertTrue(error.getMessage().contains("must be a list, set, map, or string"));
    }

    @Test
    void mapsCanBeIteratedAndUsedAsComprehensionInputs() {
        Object result = evaluate(
                "let source = {first: 10, second: 20};\n"
                        + "let keys = [];\n"
                        + "for (let key in source) { keys.add(key); }\n"
                        + "let copied = {key: source[key] * 2 for key in source};\n"
                        + "[keys, copied.first, copied.second];\n");

        assertEquals(Arrays.asList(Arrays.asList("first", "second"), 20, 40), result);
    }

    @Test
    void objectBracketAccessSupportsQuotedBareAndDynamicKeys() {
        Object result = evaluate(
                "let record = {name: \"Ada\", \"city\": \"Lusaka\", 'role': \"admin\"};\n"
                        + "let lookup = \"city\";\n"
                        + "[record.name, record[\"name\"], record[lookup], record[role], record[\"role\"]];\n");

        assertEquals(List.of("Ada", "Ada", "Lusaka", "admin", "admin"), result);
    }

    @Test
    void returnInsideTryDoesNotLeakIntoCatch() {
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

    @Test
    void exitBuiltinStopsExecutionWithRequestedCode() {
        ExitException exit = assertThrows(
                ExitException.class,
                () -> evaluate(
                        "exit(7);\n"
                                + "print(\"after exit\");\n"));

        assertEquals(7, exit.getExitCode());
    }

    @Test
    void missingVdbAuthRaisesNamedException() {
        RuntimeException error = assertThrows(
                RuntimeException.class,
                () -> evaluate(
                        "vdb import *;\n"
                                + "vdb.list_collections();\n"));

        EvaluationException evaluation = assertInstanceOf(EvaluationException.class, error);
        assertEquals("VDBNotAuthenticatedException", evaluation.getType());
    }

    @Test
    void exitBuiltinDefaultsToZeroWhenNoCodeProvided() {
        ExitException exit = assertThrows(
                ExitException.class,
                () -> evaluate("exit();\n"));

        assertEquals(0, exit.getExitCode());
    }

    @Test
    void isUnsetReportsMissingAndDeclaredUnsetBindings() {
        Object result = evaluate(
                "let missing = is_unset(notDeclaredYet);\n"
                        + "let value;\n"
                        + "let declared = is_unset(value);\n"
                        + "value = 7;\n"
                        + "[missing, declared, is_unset(value)];\n");

        assertEquals(List.of(true, true, false), result);
    }

    @Test
    void exceptionObjectsExposeVdbExceptionMetadata() {
        Object result = evaluate(
                "vdb import *;\n"
                        + "try {\n"
                        + "    vdb.list_collections();\n"
                        + "} catch (e) {\n"
                        + "    [e.type, e.base_type, e.type_alias, e.type_code];\n"
                        + "}\n");

        assertEquals(
                List.of("VDBNotAuthenticatedException", "VDBException", "VDBException.NotAuthenticated", "NotAuthenticated"),
                result);
    }

    @Test
    void rethrownNestedCatchKeepsOriginalInnerFailureLine() {
        Object result = evaluate(
                "func nested() {\n"
                        + "    try {\n"
                        + "        try {\n"
                        + "            let values = [1];\n"
                        + "            values[4];\n"
                        + "        } catch (inner) {\n"
                        + "            throw inner;\n"
                        + "        }\n"
                        + "    } catch (outer) {\n"
                        + "        [outer.line, outer.source_line];\n"
                        + "    }\n"
                        + "}\n"
                        + "\n"
                        + "nested();\n");

        List<?> details = assertInstanceOf(List.class, result);
        assertEquals(5, details.get(0));
        assertTrue(String.valueOf(details.get(1)).trim().equals("values[4];"));
    }

    @Test
    void outerCatchSeesFailureLineCreatedInsideInnerCatchBlock() {
        Object result = evaluate(
                "func nested() {\n"
                        + "    try {\n"
                        + "        try {\n"
                        + "            let values = [1];\n"
                        + "            values[4];\n"
                        + "        } catch (inner) {\n"
                        + "            missing_again;\n"
                        + "        }\n"
                        + "    } catch (outer) {\n"
                        + "        [outer.line, outer.source_line];\n"
                        + "    }\n"
                        + "}\n"
                        + "\n"
                        + "nested();\n");

        List<?> details = assertInstanceOf(List.class, result);
        assertEquals(7, details.get(0));
        assertTrue(String.valueOf(details.get(1)).trim().equals("missing_again;"));
    }

    @Test
    void thrownStringCapturesThrowSite() {
        Object result = evaluate(
                "try {\n"
                        + "    throw \"Inner failure\";\n"
                        + "} catch (e) {\n"
                        + "    [e.type, e.line, e.column, e.source_line];\n"
                        + "}\n");

        List<?> details = assertInstanceOf(List.class, result);
        assertEquals("ThrownError", details.get(0));
        assertEquals(2, details.get(1));
        assertEquals(5, details.get(2));
        assertTrue(String.valueOf(details.get(3)).trim().equals("throw \"Inner failure\";"));
    }

    @Test
    void rethrowPreservesOriginalThrowSite() {
        Object result = evaluate(
                "try {\n"
                        + "    try {\n"
                        + "        throw \"Inner failure\";\n"
                        + "    } catch (e) {\n"
                        + "        throw e;\n"
                        + "    }\n"
                        + "} catch (e) {\n"
                        + "    [e.type, e.line, e.column, e.source_line];\n"
                        + "}\n");

        List<?> details = assertInstanceOf(List.class, result);
        assertEquals("ThrownError", details.get(0));
        assertEquals(3, details.get(1));
        assertEquals(9, details.get(2));
        assertTrue(String.valueOf(details.get(3)).trim().equals("throw \"Inner failure\";"));
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
