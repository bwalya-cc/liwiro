package verun.vdb;

import org.junit.jupiter.api.Test;
import java.util.Map;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;

class NativeVdbCommandLanguageTest {
    @Test void parsesTypedQueryClausesAndExpressions() {
        VDBCommand command = VDBCommandLanguage.parseBatch(
                "read collection products where price >= 100 && stock > 0 select [sku, price] order by price desc limit 20;")
                .commands.get(0);
        assertEquals(VDBCommand.Kind.READ_COLLECTION, command.kind);
        assertEquals(2, command.selection.size());
        assertEquals(20, command.limit);
        assertTrue((Boolean) command.predicate.evaluate(Map.of("price", 200, "stock", 2), Map.of()));
        assertFalse((Boolean) command.predicate.evaluate(Map.of("price", 20, "stock", 2), Map.of()));
    }

    @Test void parsesNativeCreateUpdateAndDeleteSafety() {
        VDBCommand create = VDBCommandLanguage.parseBatch("create in users = { name: \"Alice\", active: true };").commands.get(0);
        assertEquals(VDBCommand.Kind.CREATE_DOCUMENT, create.kind);
        VDBCommand update = VDBCommandLanguage.parseBatch("update collection users where active == true { logins += 1; unset temporary_code; }").commands.get(0);
        assertEquals(2, update.updates.size());
        assertThrows(IllegalArgumentException.class, () -> VDBCommandLanguage.parseBatch("delete from users;"));
        assertDoesNotThrow(() -> VDBCommandLanguage.parseBatch("delete from users all;"));
    }

    @Test void parsesDocumentedSchemaAndAdministrationForms() {
        VDBCommand schema = VDBCommandLanguage.parseBatch(
                "create collection products = { sku: string @required @unique, price: decimal @required, stock: int = 0 };")
                .commands.get(0);
        assertEquals(VDBCommand.Kind.CREATE_COLLECTION, schema.kind);
        assertEquals(3, ((Map<?, ?>) schema.value).size());
        VDBCommand one = VDBCommandLanguage.parseBatch(
                "read one from users where email == \"alice@example.com\";").commands.get(0);
        assertEquals(VDBCommand.Kind.READ_ONE, one.kind);
        VDBCommand aggregate = VDBCommandLanguage.parseBatch(
                "aggregate collection orders where status == \"paid\" by customer_id { orders: count(); revenue: sum(total); };")
                .commands.get(0);
        assertEquals(VDBCommand.Kind.AGGREGATE, aggregate.kind);
    }

    @Test void rejectsLegacyCommandAndQueryEnvelopes() {
        assertThrows(IllegalArgumentException.class, () -> VDBCommandLanguage.parseBatch("{\"action\":\"read\"}"));
        assertThrows(IllegalArgumentException.class, () -> VDBCommandLanguage.parseBatch("read collection users where {\"active\":true};"));
        assertThrows(IllegalArgumentException.class, () -> VDBCommandLanguage.parseBatch("update collection users set {\"active\":true};"));
        assertThrows(IllegalArgumentException.class, () -> VDBCommandLanguage.parseBatch("insert users data { name: \"Alice\" };"));
        assertThrows(IllegalArgumentException.class, () -> VDBCommandLanguage.parseBatch("update users set active = true;"));
    }
    @Test void nativeTransportExecutesCrudThroughTypedPath() {
        User admin = VdbTestSupport.ensureBootstrappedSuperAdmin();
        SessionManager sessions = new SessionManager();
        String session = sessions.createSession(admin);
        VDBRequestDispatcher dispatcher = new VDBRequestDispatcher(sessions);
        String collection = "native_" + UUID.randomUUID().toString().replace("-", "");
        assertEquals(200, dispatcher.dispatch(new VDBTransportRequest("POST", "/vdb", "", Map.of("X-Session-Id", session), "create collection " + collection + ";", "127.0.0.1")).getStatusCode());
        assertEquals(200, dispatcher.dispatch(new VDBTransportRequest("POST", "/vdb", "", Map.of("X-Session-Id", session), "create in " + collection + " = { score: 120, active: true };", "127.0.0.1")).getStatusCode());
        VDBTransportResponse read = dispatcher.dispatch(new VDBTransportRequest("POST", "/vdb", "", Map.of("X-Session-Id", session), "read collection " + collection + " where score >= 100 select [score] limit 20;", "127.0.0.1"));
        assertEquals(200, read.getStatusCode(), read.getBody());
        assertTrue(read.getBody().contains("120"), read.getBody());
    }

    @Test void readUsersUsesTheNativeUserResourceList() {
        User admin = VdbTestSupport.ensureBootstrappedSuperAdmin();
        SessionManager sessions = new SessionManager();
        String session = sessions.createSession(admin);
        VDBRequestDispatcher dispatcher = new VDBRequestDispatcher(sessions);
        VDBTransportResponse response = dispatcher.dispatch(new VDBTransportRequest(
                "POST", "/vdb", "", Map.of("X-Session-Id", session), "read users;", "127.0.0.1"));
        assertEquals(200, response.getStatusCode(), response.getBody());
        assertFalse(response.getBody().contains("Invalid list command"), response.getBody());
    }
}
