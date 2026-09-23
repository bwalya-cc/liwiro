// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import org.junit.jupiter.api.Test;
import verun.runtime.ast.Node;
import verun.runtime.lexer.Lexer;
import verun.runtime.lexer.Token;
import verun.runtime.parser.Parser;
import verun.vdb.User;
import verun.vdb.VDB;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertThrows;

public class VDBScriptDependencyLimitTest {

    @SuppressWarnings("unchecked")
    @Test
    void vdbScriptChainRunsWithinConfiguredDepthLimit() {
        String previousLimit = System.getProperty("vi.vdb.script.maxDepth");
        System.setProperty("vi.vdb.script.maxDepth", "4");
        List<String> names = persistLinearChain("junit_vdb_depth_ok_" + UUID.randomUUID().toString().replace("-", ""), 4);
        try {
            Object value = evaluate("vdb.execute_script(\"" + names.get(0) + "\", {});");
            Map<String, Object> response = assertInstanceOf(Map.class, value);
            assertEquals(Boolean.TRUE, response.get("ok"));
            Map<String, Object> data = assertInstanceOf(Map.class, response.get("data"));
            assertTrue(data.containsKey("result"));
        } finally {
            restoreLimit(previousLimit);
            deleteScripts(names);
        }
    }

    @Test
    void vdbScriptChainThrowsWhenDepthLimitIsExceeded() {
        String previousLimit = System.getProperty("vi.vdb.script.maxDepth");
        System.setProperty("vi.vdb.script.maxDepth", "4");
        List<String> names = persistLinearChain("junit_vdb_depth_limit_" + UUID.randomUUID().toString().replace("-", ""), 5);
        try {
            Evaluator.VDBScriptDependencyException error = assertThrows(
                    Evaluator.VDBScriptDependencyException.class,
                    () -> evaluate("vdb.execute_script(\"" + names.get(0) + "\", {});"));
            assertEquals("DependencyDepthError", error.getType());
            assertTrue(error.getMessage().contains("max 4"), error.getMessage());
            assertTrue(error.getMessage().contains(names.get(0)), error.getMessage());
            assertTrue(error.getMessage().contains(names.get(4)), error.getMessage());
        } finally {
            restoreLimit(previousLimit);
            deleteScripts(names);
        }
    }

    @Test
    void vdbScriptCycleThrowsBeforeUnboundedRecursion() {
        String previousLimit = System.getProperty("vi.vdb.script.maxDepth");
        System.setProperty("vi.vdb.script.maxDepth", "8");
        String prefix = "junit_vdb_cycle_" + UUID.randomUUID().toString().replace("-", "");
        List<String> names = List.of(prefix + "_a", prefix + "_b");
        try {
            VDB.saveScript(names.get(0), "tests", "vdb import *;\nvdb.execute_script(\"" + names.get(1) + "\", {});");
            VDB.saveScript(names.get(1), "tests", "vdb import *;\nvdb.execute_script(\"" + names.get(0) + "\", {});");

            Evaluator.VDBScriptDependencyException error = assertThrows(
                    Evaluator.VDBScriptDependencyException.class,
                    () -> evaluate("vdb.execute_script(\"" + names.get(0) + "\", {});"));
            assertEquals("DependencyCycleError", error.getType());
            assertTrue(error.getMessage().contains(names.get(0)), error.getMessage());
            assertTrue(error.getMessage().contains(names.get(1)), error.getMessage());
        } finally {
            restoreLimit(previousLimit);
            deleteScripts(names);
        }
    }

    private static Object evaluate(String source) {
        prepareAuthenticatedVdbContext();
        String script = "vdb import *;\n" + source;
        Lexer lexer = new Lexer(script);
        List<Token> tokens = lexer.tokenize();
        Parser parser = new Parser(tokens, script);
        Node ast = parser.parse();
        Evaluator evaluator = new Evaluator(false, tokens, script);
        return evaluator.evaluate(ast);
    }

    private static List<String> persistLinearChain(String prefix, int depth) {
        List<String> names = new ArrayList<>();
        for (int level = 1; level <= depth; level += 1) {
            names.add(prefix + "_" + level);
        }

        for (int index = names.size() - 1; index >= 0; index -= 1) {
            String name = names.get(index);
            String code = "vdb import *;\n\"" + name + "_done\";";
            if (index < names.size() - 1) {
                code = "vdb import *;\nvdb.execute_script(\"" + names.get(index + 1) + "\", {});";
            }
            VDB.saveScript(name, "tests", code);
        }
        return names;
    }

    private static void deleteScripts(List<String> names) {
        for (String name : names) {
            try {
                VDB.deleteScript(name);
            } catch (Exception ignored) {
                // Best-effort cleanup for test-created script fixtures.
            }
        }
    }

    private static void restoreLimit(String previousLimit) {
        if (previousLimit == null) {
            System.clearProperty("vi.vdb.script.maxDepth");
            return;
        }
        System.setProperty("vi.vdb.script.maxDepth", previousLimit);
    }

    private static void prepareAuthenticatedVdbContext() {
        User user = new User("junit_vdb_guard", "junit-vdb-guard@example.com", "SUPER_ADMIN", "GuardPass0!");
        VDB.setCurrentUser(user);
        try {
            VDB.defineDomain("default", "main", true);
        } catch (Exception ignored) {
            VDB.setDomain("default");
            if (!VDB.listDatabases().contains("main")) {
                VDB.createDatabase("main");
            }
            VDB.useDatabase("main");
        }
    }
}
