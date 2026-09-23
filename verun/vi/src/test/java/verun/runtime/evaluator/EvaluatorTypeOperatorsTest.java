// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import org.junit.jupiter.api.Test;
import verun.runtime.modules.JsonXml;

import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class EvaluatorTypeOperatorsTest {
    @SuppressWarnings("unchecked")
    @Test
    void typeReportsJsonAndXmlAndCoreTypes() {
        Evaluator evaluator = new Evaluator(false);
        BuiltinFunction typeFn = (BuiltinFunction) evaluator.get("type");

        assertEquals("int", typeFn.call(List.of(42)));
        assertEquals("float", typeFn.call(List.of(1.5)));
        assertEquals("bool", typeFn.call(List.of(true)));
        assertEquals("string", typeFn.call(List.of("hello")));
        assertEquals("null", typeFn.call(Collections.singletonList(null)));
        assertEquals("list", typeFn.call(List.of(Arrays.asList(1, 2))));
        assertEquals("json", typeFn.call(List.of("{\"a\":1}")));
        assertEquals("xml", typeFn.call(List.of("<root><a>1</a></root>")));

        Map<String, Object> objectValue = new LinkedHashMap<>();
        objectValue.put("name", "Ava");
        assertEquals("object", typeFn.call(List.of(objectValue)));

        Object xmlObject = JsonXml.parseXml("<person><name>Ava</name></person>");
        assertEquals("xml", typeFn.call(List.of(xmlObject)));
    }

    @Test
    void isTypeSupportsAliasesAndStructuredChecks() {
        Evaluator evaluator = new Evaluator(false);
        BuiltinFunction isTypeFn = (BuiltinFunction) evaluator.get("is_type");

        assertTrue((Boolean) isTypeFn.call(List.of(42, "int")));
        assertTrue((Boolean) isTypeFn.call(List.of(42, "number")));
        assertTrue((Boolean) isTypeFn.call(List.of(42, "integer")));
        assertTrue((Boolean) isTypeFn.call(List.of(2.5, "float")));
        assertTrue((Boolean) isTypeFn.call(List.of(true, "boolean")));
        assertTrue((Boolean) isTypeFn.call(List.of("hello", "str")));
        assertTrue((Boolean) isTypeFn.call(List.of(Arrays.asList(1, 2), "array")));
        assertTrue((Boolean) isTypeFn.call(Arrays.asList(null, "none")));

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("ok", true);
        payload.put("count", 3);
        payload.put("name", "Ava");
        assertTrue((Boolean) isTypeFn.call(List.of(payload, "json")));
        assertTrue((Boolean) isTypeFn.call(List.of("{\"ok\":true}", "json")));
        assertTrue((Boolean) isTypeFn.call(List.of("<root/>", "xml")));
        assertTrue((Boolean) isTypeFn.call(List.of(JsonXml.parseXml("<root/>"), "xml")));

        assertFalse((Boolean) isTypeFn.call(List.of("plain text", "json")));
        assertFalse((Boolean) isTypeFn.call(List.of(payload, "xml")));
    }
}
