// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;

class CommandValidatorTest {

    @Test
    void rejectsUnsupportedOperations() {
        JsonObject cmd = new JsonObject();
        cmd.addProperty("nuke", "all");
        assertThrows(IllegalArgumentException.class, () -> CommandValidator.validateCommandStructure(cmd));
    }

    @Test
    void rejectsTopLevelQueryOperators() {
        JsonObject cmd = new JsonObject();
        cmd.addProperty("read", "users");
        JsonObject query = new JsonObject();
        query.addProperty("$or", "invalid");
        cmd.add("query", query);
        assertThrows(IllegalArgumentException.class, () -> CommandValidator.validateCommandStructure(cmd));
    }

    @Test
    void rejectsLegacyNestedReadQuery() {
        JsonObject cmd = new JsonObject();
        cmd.addProperty("read", "users");
        JsonObject query = new JsonObject();
        query.addProperty("username", "alice");
        cmd.add("query", query);
        assertThrows(IllegalArgumentException.class, () -> CommandValidator.validateCommandStructure(cmd));
    }

    @Test
    void rejectsLegacyUtilityEnvelopeWithoutAction() {
        JsonObject cmd = new JsonObject();
        cmd.addProperty("echo", "hello");
        assertThrows(IllegalArgumentException.class, () -> CommandValidator.validateCommandStructure(cmd));
    }

    @Test
    void rejectsLegacyNestedKeyAlongsideFlatAction() {
        JsonObject cmd = new JsonObject();
        cmd.addProperty("action", "find");
        cmd.addProperty("collection", "users");
        cmd.add("read", new JsonObject());
        assertThrows(IllegalArgumentException.class, () -> CommandValidator.validateCommandStructure(cmd));
    }

    @Test
    void rejectsLifecycleAndModernActionsWhenNested() {
        for (String nested : new String[]{"domain_status", "domain_suspend", "domain_resume", "aggregate", "create_collection", "script_execute"}) {
            JsonObject cmd = new JsonObject();
            cmd.addProperty("action", "echo");
            cmd.add(nested, new JsonObject());
            assertThrows(IllegalArgumentException.class, () -> CommandValidator.validateCommandStructure(cmd), nested);
        }
    }

    @Test
    void acceptsFlatBatchAndRejectsMixedBatchEnvelope() {
        JsonObject batch = new JsonObject();
        com.google.gson.JsonArray commands = new com.google.gson.JsonArray();
        JsonObject echo = new JsonObject();
        echo.addProperty("action", "echo");
        echo.addProperty("value", "ok");
        commands.add(echo);
        batch.add("commands", commands);
        assertDoesNotThrow(() -> CommandValidator.validateCommandStructure(batch));
        batch.addProperty("action", "echo");
        assertThrows(IllegalArgumentException.class, () -> CommandValidator.validateCommandStructure(batch));

        JsonObject nestedBatch = new JsonObject();
        com.google.gson.JsonArray nestedCommands = new com.google.gson.JsonArray();
        JsonObject childBatch = new JsonObject();
        childBatch.add("commands", commands);
        nestedCommands.add(childBatch);
        nestedBatch.add("commands", nestedCommands);
        assertThrows(IllegalArgumentException.class, () -> CommandValidator.validateCommandStructure(nestedBatch));
    }

    @Test
    void rejectsNonStringAction() {
        JsonObject cmd = new JsonObject();
        JsonObject action = new JsonObject();
        action.addProperty("name", "echo");
        cmd.add("action", action);
        assertThrows(IllegalArgumentException.class, () -> CommandValidator.validateCommandStructure(cmd));
    }

    @Test
    void acceptsConciseIndexAction() {
        JsonObject cmd = new JsonObject();
        cmd.addProperty("action", "create_index");
        cmd.addProperty("collection", "users");
        cmd.addProperty("field", "email");
        cmd.addProperty("unique", true);
        assertDoesNotThrow(() -> CommandValidator.validateCommandStructure(cmd));
    }

    @Test
    void acceptsCaseInsensitiveActionNamesForCanonicalDispatch() {
        JsonObject cmd = new JsonObject();
        cmd.addProperty("action", "  FIND ");
        cmd.addProperty("collection", "users");
        assertDoesNotThrow(() -> CommandValidator.validateCommandStructure(cmd));
    }

    @Test
    void acceptsContextActionsWithDirectDomainOrDatabaseFields() {
        JsonObject useDomain = new JsonObject();
        useDomain.addProperty("action", "use");
        useDomain.addProperty("domain", "analytics");
        assertDoesNotThrow(() -> CommandValidator.validateCommandStructure(useDomain));

        JsonObject useDatabase = new JsonObject();
        useDatabase.addProperty("action", "use");
        useDatabase.addProperty("db", "warehouse");
        assertDoesNotThrow(() -> CommandValidator.validateCommandStructure(useDatabase));
    }

    @Test
    void rejectsIndexActionWithoutField() {
        JsonObject cmd = new JsonObject();
        cmd.addProperty("action", "drop_index");
        cmd.addProperty("collection", "users");
        assertThrows(IllegalArgumentException.class, () -> CommandValidator.validateCommandStructure(cmd));
    }

    @Test
    void rejectsMutatingActionsWithoutPayloads() {
        JsonObject insert = new JsonObject();
        insert.addProperty("action", "insert");
        insert.addProperty("collection", "users");
        assertThrows(IllegalArgumentException.class, () -> CommandValidator.validateCommandStructure(insert));

        JsonObject update = new JsonObject();
        update.addProperty("action", "update");
        update.addProperty("collection", "users");
        assertThrows(IllegalArgumentException.class, () -> CommandValidator.validateCommandStructure(update));

        JsonObject incrementOnly = new JsonObject();
        incrementOnly.addProperty("action", "update");
        incrementOnly.addProperty("collection", "users");
        JsonObject inc = new JsonObject();
        inc.addProperty("logins", 1);
        incrementOnly.add("inc", inc);
        assertDoesNotThrow(() -> CommandValidator.validateCommandStructure(incrementOnly));
    }

    @Test
    void validatesHelpPagingFields() {
        JsonObject valid = new JsonObject();
        valid.addProperty("action", "help");
        valid.addProperty("topic", "Documents");
        valid.addProperty("page", 2);
        valid.addProperty("page_size", 3);
        assertDoesNotThrow(() -> CommandValidator.validateCommandStructure(valid));

        JsonObject zeroPage = valid.deepCopy();
        zeroPage.addProperty("page", 0);
        assertThrows(IllegalArgumentException.class, () -> CommandValidator.validateCommandStructure(zeroPage));

        JsonObject objectTopic = valid.deepCopy();
        objectTopic.add("topic", new JsonObject());
        assertThrows(IllegalArgumentException.class, () -> CommandValidator.validateCommandStructure(objectTopic));
    }
}
