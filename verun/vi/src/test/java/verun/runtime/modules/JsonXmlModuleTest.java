// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.modules;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

class JsonXmlModuleTest {
    @TempDir
    Path tempDir;

    @Test
    void parseJsonPreservesWholeNumbers() {
        Map<?, ?> parsed = assertInstanceOf(Map.class, JsonXml.parseJson(
                "{\"count\":1,\"ratio\":1.5,\"nested\":{\"whole\":2},\"items\":[3,3.75,3000000000]}"));

        assertInstanceOf(Integer.class, parsed.get("count"));
        assertInstanceOf(Double.class, parsed.get("ratio"));
        Map<?, ?> nested = assertInstanceOf(Map.class, parsed.get("nested"));
        assertInstanceOf(Integer.class, nested.get("whole"));
        List<?> items = assertInstanceOf(List.class, parsed.get("items"));
        assertInstanceOf(Integer.class, items.get(0));
        assertInstanceOf(Double.class, items.get(1));
        assertInstanceOf(Long.class, items.get(2));
    }

    @Test
    void readWriteJsonPreservesNumericTypes() {
        Path file = tempDir.resolve("payload.json");
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("count", 7);
        payload.put("ratio", 7.5);
        payload.put("nested", Map.of("whole", 9));
        payload.put("items", List.of(1, 2.5, 3000000000L));

        JsonXml.writeJson(file.toString(), payload, true);
        Map<?, ?> reloaded = assertInstanceOf(Map.class, JsonXml.readJson(file.toString()));

        assertInstanceOf(Integer.class, reloaded.get("count"));
        assertInstanceOf(Double.class, reloaded.get("ratio"));
        Map<?, ?> nested = assertInstanceOf(Map.class, reloaded.get("nested"));
        assertInstanceOf(Integer.class, nested.get("whole"));
        List<?> items = assertInstanceOf(List.class, reloaded.get("items"));
        assertInstanceOf(Integer.class, items.get(0));
        assertInstanceOf(Double.class, items.get(1));
        assertInstanceOf(Long.class, items.get(2));
    }

    @Test
    void xmlToJsonReturnsPlainJsonLikeObjects() {
        Map<?, ?> parsed = assertInstanceOf(Map.class, JsonXml.xmlToJson(
                "<root><app>liwiro</app><features><item>vi</item><item>vdb</item></features><ok>true</ok><count>1</count></root>"));

        assertEquals("liwiro", parsed.get("app"));
        assertEquals(List.of("vi", "vdb"), parsed.get("features"));
        assertEquals(true, parsed.get("ok"));
        assertEquals(1, parsed.get("count"));
        assertInstanceOf(Integer.class, parsed.get("count"));
    }

    @Test
    void jsonToXmlAcceptsJsonTextAndXmlToObjRoundTrips() {
        String xml = JsonXml.jsonToXml("{\"app\":\"liwiro\",\"count\":2,\"ok\":true}", "root");
        Map<?, ?> roundTrip = assertInstanceOf(Map.class, JsonXml.xmlToObj(xml));

        assertEquals("liwiro", roundTrip.get("app"));
        assertEquals(2, roundTrip.get("count"));
        assertEquals(true, roundTrip.get("ok"));
        assertInstanceOf(Integer.class, roundTrip.get("count"));
    }
}
