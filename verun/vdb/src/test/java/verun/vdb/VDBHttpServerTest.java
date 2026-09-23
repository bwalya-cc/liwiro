package verun.vdb;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import java.util.Map;
import java.lang.reflect.Method;

class VDBHttpServerTest {

    @Test
    void resolvePortUsesSystemPropertyWhenPresent() {
        String original = System.getProperty("vdb.http.port");
        try {
            System.setProperty("vdb.http.port", "20457");
            assertEquals(20457, VDBHttpServer.resolvePort());
        } finally {
            restoreProperty(original);
        }
    }

    @Test
    void resolvePortFallsBackToDefaultWhenPropertyIsInvalid() {
        String original = System.getProperty("vdb.http.port");
        try {
            System.setProperty("vdb.http.port", "not-a-port");
            assertEquals(1957, VDBHttpServer.resolvePort());
        } finally {
            restoreProperty(original);
        }
    }

    @Test
    void dispatcherExposesHealthAndLicense() {
        VDBRequestDispatcher dispatcher = new VDBRequestDispatcher();

        VDBTransportResponse health = dispatcher.dispatch(new VDBTransportRequest("GET", "/health", "", null, "", "test"));
        VDBTransportResponse license = dispatcher.dispatch(new VDBTransportRequest("GET", "/license", "", null, "", "test"));

        assertEquals(200, health.getStatusCode());
        assertTrue(health.getBody().contains("\"status\":\"ok\""));

        assertEquals(200, license.getStatusCode());
        assertTrue(license.getBody().contains("\"license\":\"MIT\""));
    }

    @Test
    void rootExamplesUseReadableVdbCommands() {
        VDBRequestDispatcher dispatcher = new VDBRequestDispatcher();
        VDBTransportResponse response = dispatcher.dispatch(new VDBTransportRequest(
                "GET", "/", "", Map.of(), "", "127.0.0.1"));
        assertEquals(200, response.getStatusCode());
        assertTrue(response.getBody().contains("echo \\\"Hello\\\""));
        assertTrue(!response.getBody().contains("{\\\"action\\\""));
        com.google.gson.JsonObject root = com.google.gson.JsonParser.parseString(response.getBody()).getAsJsonObject();
        assertTrue(root.get("help").getAsString().contains("page_size is limited to 1..5"));
    }

    @Test
    void helpEndpointAcceptsFlatActionEnvelope() {
        User user = VdbTestSupport.ensureBootstrappedSuperAdmin();
        SessionManager sessions = new SessionManager();
        String sessionId = sessions.createSession(user);
        VDBRequestDispatcher dispatcher = new VDBRequestDispatcher(sessions);
        VDBTransportResponse response = dispatcher.dispatch(new VDBTransportRequest(
                "POST", "/help", "", Map.of("X-Session-Id", sessionId),
                "{\"action\":\"help\",\"topic\":\"General\"}", "127.0.0.1"));

        assertEquals(200, response.getStatusCode());
        assertTrue(response.getBody().contains("\"topic\""));
    }

    @Test
    void helpEndpointPaginatesGetQueries() {
        User user = VdbTestSupport.ensureBootstrappedSuperAdmin();
        SessionManager sessions = new SessionManager();
        String sessionId = sessions.createSession(user);
        VDBRequestDispatcher dispatcher = new VDBRequestDispatcher(sessions);
        VDBTransportResponse response = dispatcher.dispatch(new VDBTransportRequest(
                "GET", "/help", "topic=Domains&page=2&page_size=2",
                Map.of("X-Session-Id", sessionId), "", "127.0.0.1"));

        assertEquals(200, response.getStatusCode());
        com.google.gson.JsonObject body = com.google.gson.JsonParser.parseString(response.getBody()).getAsJsonObject();
        assertEquals("section", body.get("mode").getAsString());
        assertEquals(2, body.get("page").getAsInt());
        assertEquals(2, body.getAsJsonArray("commands").size());
        assertTrue(body.getAsJsonObject("navigation").has("next"));
    }

    @Test
    void helpEndpointAcceptsPagingInPostBody() {
        User user = VdbTestSupport.ensureBootstrappedSuperAdmin();
        SessionManager sessions = new SessionManager();
        String sessionId = sessions.createSession(user);
        VDBRequestDispatcher dispatcher = new VDBRequestDispatcher(sessions);
        VDBTransportResponse response = dispatcher.dispatch(new VDBTransportRequest(
                "POST", "/help", "", Map.of("X-Session-Id", sessionId),
                "{\"action\":\"help\",\"topic\":\"Documents\",\"page\":2,\"page_size\":2}",
                "127.0.0.1"));

        assertEquals(200, response.getStatusCode());
        com.google.gson.JsonObject body = com.google.gson.JsonParser.parseString(response.getBody()).getAsJsonObject();
        assertEquals("Documents", body.get("topic").getAsString());
        assertEquals(2, body.get("page").getAsInt());
        assertEquals(2, body.getAsJsonArray("commands").size());
    }

    @Test
    void helpEndpointRejectsUnboundedPageSize() {
        User user = VdbTestSupport.ensureBootstrappedSuperAdmin();
        SessionManager sessions = new SessionManager();
        String sessionId = sessions.createSession(user);
        VDBRequestDispatcher dispatcher = new VDBRequestDispatcher(sessions);
        VDBTransportResponse response = dispatcher.dispatch(new VDBTransportRequest(
                "GET", "/help", "topic=Documents&page_size=100",
                Map.of("X-Session-Id", sessionId), "", "127.0.0.1"));

        assertEquals(400, response.getStatusCode());
        assertTrue(response.getBody().contains("between 1 and 5"));
    }

    @Test
    void helpEndpointRejectsUnsupportedMethods() {
        VDBRequestDispatcher dispatcher = new VDBRequestDispatcher();
        VDBTransportResponse response = dispatcher.dispatch(new VDBTransportRequest(
                "DELETE", "/help", "", Map.of(), "", "127.0.0.1"));
        assertEquals(405, response.getStatusCode());
    }

    @Test
    void helpEndpointRejectsNonStringTopicWithoutServerError() {
        User user = VdbTestSupport.ensureBootstrappedSuperAdmin();
        SessionManager sessions = new SessionManager();
        String sessionId = sessions.createSession(user);
        VDBRequestDispatcher dispatcher = new VDBRequestDispatcher(sessions);
        VDBTransportResponse response = dispatcher.dispatch(new VDBTransportRequest(
                "POST", "/help", "", Map.of("X-Session-Id", sessionId),
                "{\"action\":\"help\",\"topic\":{}}", "127.0.0.1"));
        assertEquals(400, response.getStatusCode());
    }

    @Test
    void helpEndpointRejectsMalformedTopicEncoding() {
        VDBRequestDispatcher dispatcher = new VDBRequestDispatcher();
        VDBTransportResponse response = dispatcher.dispatch(new VDBTransportRequest(
                "GET", "/help/%ZZ", "", Map.of(), "", "127.0.0.1"));
        assertEquals(400, response.getStatusCode());
    }

    @Test
    void vqlPermissionErrorsMapToForbiddenStatus() throws Exception {
        VDBRequestDispatcher dispatcher = new VDBRequestDispatcher();
        Method responseStatus = VDBRequestDispatcher.class.getDeclaredMethod("responseStatus", String.class);
        responseStatus.setAccessible(true);
        assertEquals(403, responseStatus.invoke(dispatcher,
                "{\"status\":\"error\",\"message\":\"Permission denied for collection\"}"));
    }

    private void restoreProperty(String original) {
        if (original == null) {
            System.clearProperty("vdb.http.port");
        } else {
            System.setProperty("vdb.http.port", original);
        }
    }
}
