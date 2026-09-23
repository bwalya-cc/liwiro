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

import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

class VDBVersaClassCollectionTest {

    @Test
    void createAcceptsVersaClassSchemaReference() {
        String collection = "junit_versa_schema_" + UUID.randomUUID().toString().replace("-", "");
        prepareAuthenticatedVdbContext();
        try {
            Object value = evaluate(
                    "class AuditEntry {\n"
                            + "    schema() {\n"
                            + "        return {\n"
                            + "            id: {type: \"string\", required: true},\n"
                            + "            severity: {type: \"string\", default: \"info\"}\n"
                            + "        };\n"
                            + "    }\n"
                            + "}\n"
                            + "vdb.create(\"" + collection + "\", AuditEntry);\n");

            Map<?, ?> response = assertInstanceOf(Map.class, value);
            assertEquals(Boolean.TRUE, response.get("ok"));
            assertEquals("create_collection", response.get("operation"));
        } finally {
            VDB.drop(collection);
        }
    }

    private static Object evaluate(String source) {
        String script = "vdb import *;\n" + source;
        Lexer lexer = new Lexer(script);
        List<Token> tokens = lexer.tokenize();
        Parser parser = new Parser(tokens, script);
        Node ast = parser.parse();
        Evaluator evaluator = new Evaluator(false, tokens, script);
        return evaluator.evaluate(ast);
    }

    private static void prepareAuthenticatedVdbContext() {
        User user = new User("junit_versa_schema", "junit-versa-schema@example.com", "SUPER_ADMIN", "GuardPass0!");
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
