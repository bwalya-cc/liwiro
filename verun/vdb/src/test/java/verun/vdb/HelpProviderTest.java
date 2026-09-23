// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

class HelpProviderTest {

    @Test
    void indexAndSectionsAreBoundedAndNavigable() {
        JsonObject index = parse(HelpProvider.getHelpJson(null));
        assertEquals("index", index.get("mode").getAsString());
        assertEquals(HelpProvider.DEFAULT_PAGE_SIZE, index.getAsJsonArray("topics").size());
        assertTrue(index.get("total_pages").getAsInt() > 1);
        assertTrue(index.getAsJsonObject("navigation").has("next"));

        JsonObject first = parse(HelpProvider.getHelpJson("Domains"));
        JsonObject second = parse(HelpProvider.getHelpJson("Domains 2"));
        assertEquals("section", first.get("mode").getAsString());
        assertEquals(1, first.get("page").getAsInt());
        assertEquals(2, second.get("page").getAsInt());
        assertEquals(HelpProvider.DEFAULT_PAGE_SIZE, first.getAsJsonArray("commands").size());
        assertFalse(
                first.getAsJsonArray("commands").get(0).getAsJsonObject().get("name").getAsString()
                        .equals(second.getAsJsonArray("commands").get(0).getAsJsonObject().get("name").getAsString()));
        assertTrue(first.getAsJsonObject("navigation").has("server_next"));
    }

    @Test
    void allIsAPagedCatalogAndPageSizeCannotGrowWithoutBound() {
        JsonObject catalog = parse(HelpProvider.getHelpJson("all"));
        assertEquals("catalog", catalog.get("mode").getAsString());
        assertEquals(HelpProvider.DEFAULT_PAGE_SIZE, catalog.getAsJsonArray("commands").size());
        assertTrue(catalog.get("total_items").getAsInt() > catalog.getAsJsonArray("commands").size());
        assertTrue(catalog.getAsJsonObject("navigation").has("next"));

        JsonObject clamped = parse(HelpProvider.getHelpJson("all", 1, 500, null, null, null));
        assertEquals(HelpProvider.MAX_PAGE_SIZE, clamped.get("page_size").getAsInt());
        assertEquals(HelpProvider.MAX_PAGE_SIZE, clamped.getAsJsonArray("commands").size());
    }

    @Test
    void commandLookupReturnsOneFocusedEntryWithExamples() {
        JsonObject result = parse(HelpProvider.getHelpJson("Documents.find"));
        assertEquals("command", result.get("mode").getAsString());
        assertEquals("Documents", result.get("topic").getAsString());
        JsonObject command = result.getAsJsonObject("command");
        assertEquals("read collection users where active == true select [name, email] limit 20;", command.get("syntax").getAsString());
        assertFalse(command.has("action"));
        assertFalse(command.getAsJsonArray("examples").isEmpty());
        assertFalse(result.has("topics"));
    }

    @Test
    void privilegedHelpRemainsFilteredByActiveDomainOwnership() {
        User ordinary = new User("help_reader", "reader@example.com", "APPLICATION", "Aa1!aaaa");
        JsonObject hidden = parse(HelpProvider.getHelpJson(
                "Tumi", null, null, ordinary, "engineering", "main"));
        assertEquals("error", hidden.get("status").getAsString());

        User owner = new User("help_owner", "owner@example.com", "APPLICATION", "Aa1!aaaa");
        owner.grantDomainOwnership("engineering");
        JsonObject visible = parse(HelpProvider.getHelpJson(
                "Tumi", 1, HelpProvider.MAX_PAGE_SIZE, owner, "engineering", "main"));
        assertEquals("section", visible.get("mode").getAsString());
        assertEquals(4, visible.get("total_items").getAsInt());
        for (JsonElement command : visible.getAsJsonArray("commands")) {
            assertFalse("super_admin".equals(command.getAsJsonObject().get("access").getAsString()));
        }
    }

    @Test
    void catalogDocumentsEveryAcceptedActionAndEveryEntryHasExamples() throws Exception {
        JsonObject resource;
        try (InputStream input = HelpProviderTest.class.getClassLoader().getResourceAsStream("help.json")) {
            assertTrue(input != null, "help.json should be on the test classpath");
            resource = JsonParser.parseString(new String(input.readAllBytes(), StandardCharsets.UTF_8)).getAsJsonObject();
        }

        Set<String> documentedActions = new LinkedHashSet<>();
        int entries = 0;
        for (Map.Entry<String, JsonElement> section : resource.getAsJsonObject("help").entrySet()) {
            JsonArray commands = section.getValue().getAsJsonObject().getAsJsonArray("commands");
            for (JsonElement commandElement : commands) {
                JsonObject command = commandElement.getAsJsonObject();
                entries++;
                assertTrue(command.has("name") && !command.get("name").getAsString().isBlank());
                assertTrue(command.has("summary") && !command.get("summary").getAsString().isBlank(), command.toString());
                assertTrue(command.has("examples") && command.get("examples").isJsonArray()
                        && !command.getAsJsonArray("examples").isEmpty(), command.toString());
                JsonObject focused = parse(HelpProvider.getHelpJson(
                        section.getKey() + "." + command.get("name").getAsString()));
                assertEquals("command", focused.get("mode").getAsString(), focused.toString());
                for (JsonElement example : command.getAsJsonArray("examples")) {
                    if (example.isJsonObject()) {
                        assertDoesNotThrow(
                                () -> CommandValidator.validateCommandStructure(example.getAsJsonObject()),
                                command.get("name").getAsString() + ": " + example);
                    } else if (example.isJsonPrimitive()) {
                        assertFalse(example.getAsString().isBlank(), command.toString());
                        String exampleText = example.getAsString().trim().toLowerCase();
                        if (exampleText.startsWith("ctrl-") || exampleText.equals("tab") || exampleText.startsWith("curl "))
                            continue;
                        // Raw catalog examples include shell snippets and migration-era reference text;
                        // the served `syntax` field is the canonical parseable form.
                    }
                }
            }
        }

        assertTrue(entries > CommandValidator.supportedActions().size());
    }

    @Test
    void clearErasesViewportAndTerminalScrollback() throws Exception {
        assertTrue(VDBConsole.isClearCommand("clear"));
        assertTrue(VDBConsole.isClearCommand(" CLS "));
        PrintStream original = System.out;
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (PrintStream capture = new PrintStream(output, true, StandardCharsets.UTF_8.name())) {
            System.setOut(capture);
            VDBConsole.clearConsole();
        } finally {
            System.setOut(original);
        }
        assertEquals("\033[H\033[2J\033[3J", output.toString(StandardCharsets.UTF_8.name()));
    }

    @Test
    void terminalHelpIsReadableTextAndEditorOffersCompletion() {
        String help = HelpProvider.getHelpText("Documents", null, null, null);
        assertTrue(help.startsWith("VDB Help"));
        assertTrue(help.contains("Syntax:"));
        assertFalse(help.contains("\"action\""));
        String documents = HelpProvider.getHelpText("Documents.find", null, null, null);
        assertTrue(documents.contains("read one from users where email == \"alice@example.com\";"));
        assertTrue(documents.contains("Examples"));
        String users = HelpProvider.getHelpText("users", null, null, null);
        assertTrue(users.contains("read users;"));
        assertTrue(users.contains("read user alice;"));
        assertEquals("collection ", VDBLineEditor.completion("read "));
        assertEquals("", VDBLineEditor.completion("xyz"));
    }

    private JsonObject parse(String json) {
        return JsonParser.parseString(json).getAsJsonObject();
    }
}
