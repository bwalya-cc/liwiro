// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.google.gson.Gson;
import java.util.Map;
import org.junit.jupiter.api.Test;

class VQLProcessorScriptPermissionsTest {
    private static final Gson GSON = new Gson();

    @Test
    void deniesScriptCreateWithoutWritePermission() {
        User user = new User("app_create", "create@example.com", "APPLICATION", "Aa1!aaaa");
        VQLProcessor processor = new VQLProcessor(user, "default");

        String response = processor.executeCommand(
                "{\"action\":\"script_create\",\"name\":\"demo\",\"service\":\"svc\",\"code\":\"print(1);\"}");
        Map<String, Object> parsed = parse(response);

        assertEquals("error", parsed.get("status"));
        assertTrue(String.valueOf(parsed.get("message")).contains("Permission denied for creating scripts"));
    }

    @Test
    void deniesScriptReadWithoutReadPermission() {
        User user = new User("app_read", "read@example.com", "APPLICATION", "Aa1!aaaa");
        VQLProcessor processor = new VQLProcessor(user, "default");

        String response = processor.executeCommand("{\"action\":\"script_read\",\"name\":\"demo\"}");
        Map<String, Object> parsed = parse(response);

        assertEquals("error", parsed.get("status"));
        assertTrue(String.valueOf(parsed.get("message")).contains("Permission denied for reading scripts"));
    }

    @Test
    void allowsScriptReadWhenReadPermissionExists() {
        User user = new User("app_read_ok", "readok@example.com", "APPLICATION", "Aa1!aaaa");
        user.grantPermission("default", "main", "READ");
        VQLProcessor processor = new VQLProcessor(user, "default");

        String response = processor.executeCommand("{\"action\":\"script_read\",\"name\":\"demo\"}");
        Map<String, Object> parsed = parse(response);

        assertEquals("error", parsed.get("status"));
        assertTrue(String.valueOf(parsed.get("message")).contains("Script command failed: Script not found"));
    }

    private Map<String, Object> parse(String json) {
        return GSON.fromJson(json, Map.class);
    }
}
