package verun.vdb;

import com.google.gson.*;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class VDBCommandLanguageTest {
    @Test void readableCommandsCoverAdministrativeAndDataOperations() {
        assertEquals(VDBCommand.Kind.READ_USERS, VDBCommandLanguage.parseBatch("read users;").commands.get(0).kind);
        assertEquals(VDBCommand.Kind.CREATE_USER, VDBCommandLanguage.parseBatch("create user bob = { password: \"a; b\", role: application };").commands.get(0).kind);
        VDBCommand read = VDBCommandLanguage.parseBatch("read collection orders where status == \"open\" limit 10;").commands.get(0);
        assertTrue((Boolean) read.predicate.evaluate(Map.of("status", "open"), Map.of()));
        assertEquals(10, read.limit);
        assertEquals(2, VDBCommandLanguage.parseBatch("update collection orders where id == 1 { status = \"closed\"; amount = 20; };").commands.get(0).updates.size());
        assertEquals(VDBCommand.Kind.CREATE_DOCUMENT, VDBCommandLanguage.parseBatch("create in orders = { id: 1, amount: 20 };").commands.get(0).kind);
        assertEquals(VDBCommand.Kind.RUN_SCRIPT, VDBCommandLanguage.parseBatch("run script nightly with { value: \"a;b\" };").commands.get(0).kind);
        assertEquals(2, VDBCommandLanguage.parseBatch("context; read collections;").commands.size());
    }
    @Test void rejectsJsonCommandsAndIncompleteStatements() {
        for (String source : new String[]{"{\"action\":\"whoami\"}", "[]", "read collection", "read orders where name", "echo \"unclosed", "read orders nope 1", "insert users data { name: \"A\" };", "update users set active = true;"})
            assertThrows(IllegalArgumentException.class, () -> VDBCommandLanguage.parse(source), source);
    }
    @Test void preservesMemberAccessDotsInsideRawScriptBlocks() {
        VDBCommand command = VDBCommandLanguage.parseBatch(
                "create script AuthCoreService_ep_signup for AuthCoreService = { "
                        + "let username = str(params.username ?? \"\").trim(); "
                        + "let createdAt = datetime.now().isoformat(); "
                        + "return {username: username, createdAt: createdAt}; "
                        + "};"
        ).commands.get(0);

        assertEquals(VDBCommand.Kind.CREATE_SCRIPT, command.kind);
        assertTrue(command.options.get("code").toString().contains("datetime.now().isoformat()"));
    }
    @Test void transportExecutesReadableCommandsAndRejectsJson() {
        User admin = VdbTestSupport.ensureBootstrappedSuperAdmin();
        SessionManager sessions = new SessionManager();
        String sessionId = sessions.createSession(admin);
        VDBRequestDispatcher dispatcher = new VDBRequestDispatcher(sessions);
        String collection = "readable_" + UUID.randomUUID().toString().replace("-", "");
        for (String command : new String[]{"create collection " + collection + ";", "create in " + collection + " = { name: \"Ada\", amount: 12 };", "update collection " + collection + " where name == \"Ada\" { amount = 21; };", "read collection " + collection + ";"}) {
            VDBTransportResponse response = dispatcher.dispatch(new VDBTransportRequest("POST", "/vdb", "", Map.of("X-Session-Id", sessionId), command, "127.0.0.1"));
            assertEquals(200, response.getStatusCode(), response.getBody());
            if (command.startsWith("read")) assertTrue(response.getBody().contains("21"), response.getBody());
        }
        String role = "READER_" + UUID.randomUUID().toString().replace("-", "").substring(0, 10).toUpperCase();
        VDBTransportResponse createdRole = dispatcher.dispatch(new VDBTransportRequest(
                "POST", "/vdb", "", Map.of("X-Session-Id", sessionId),
                "create role " + role + " = { permissions: [\"DATA_ACCESS\"], scope: \"default.main\" };", "127.0.0.1"));
        assertEquals(200, createdRole.getStatusCode(), createdRole.getBody());
        assertTrue(createdRole.getBody().contains("Role created"), createdRole.getBody());
        VDBTransportResponse deletedRole = dispatcher.dispatch(new VDBTransportRequest(
                "POST", "/vdb", "", Map.of("X-Session-Id", sessionId), "delete role " + role + ";", "127.0.0.1"));
        assertTrue(deletedRole.getBody().contains("Role deleted"), deletedRole.getBody());
        VDBTransportResponse rejected = dispatcher.dispatch(new VDBTransportRequest("POST", "/vdb", "", Map.of("X-Session-Id", sessionId), "{\"action\":\"whoami\"}", "127.0.0.1"));
        assertEquals(400, rejected.getStatusCode());
    }
}
