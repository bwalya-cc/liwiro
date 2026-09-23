// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertFalse;

class VdbNumericTypePreservationTest {
    @BeforeAll
    static void bootstrapVdb() {
        VdbTestSupport.ensureBootstrappedSuperAdmin();
    }

    @Test
    void vqlCreateAndUpdatePreserveWholeNumbersInStoredDocuments() throws Exception {
        User superAdmin = VdbTestSupport.ensureBootstrappedSuperAdmin();
        String domain = uniqueName("numeric_domain");
        String collection = uniqueName("numeric_docs");

        VDB.setCurrentUser(superAdmin);
        VDB.defineDomain(domain, "main", true);
        VDB.createCollection(collection);

        VQLProcessor processor = new VQLProcessor(superAdmin, domain);
        processor.executeCommand("{\"action\":\"insert\",\"collection\":\"" + collection
                + "\",\"document\":{\"count\":1,\"ratio\":1.5,\"visits\":1,\"large\":9007199254740991,\"obsolete\":true,\"nested\":{\"whole\":2},\"items\":[3,3.75]}}");

        Map<String, Object> created = readOnlyStoredDocument(domain, collection);
        assertInstanceOf(Integer.class, created.get("count"));
        assertInstanceOf(Double.class, created.get("ratio"));
        Map<?, ?> createdNested = assertInstanceOf(Map.class, created.get("nested"));
        assertInstanceOf(Integer.class, createdNested.get("whole"));
        List<?> createdItems = assertInstanceOf(List.class, created.get("items"));
        assertInstanceOf(Integer.class, createdItems.get(0));
        assertInstanceOf(Double.class, createdItems.get(1));

        String id = String.valueOf(created.get("_id"));
        processor.executeCommand("{\"action\":\"update\",\"collection\":\"" + collection
                + "\",\"where\":{\"_id\":\"" + id
                + "\"},\"set\":{\"count\":7,\"ratio\":2.25,\"nested\":{\"whole\":8},\"items\":[9,9.5]},\"inc\":{\"visits\":2,\"large\":2},\"unset\":{\"obsolete\":true}}");

        Map<String, Object> updated = readOnlyStoredDocument(domain, collection);
        assertEquals(id, updated.get("_id"));
        Number visits = assertInstanceOf(Number.class, updated.get("visits"));
        assertEquals(3, visits.intValue());
        assertEquals(9007199254740993L, assertInstanceOf(Long.class, updated.get("large")));
        assertFalse(updated.containsKey("obsolete"));
        assertInstanceOf(Integer.class, updated.get("count"));
        assertInstanceOf(Double.class, updated.get("ratio"));
        Map<?, ?> updatedNested = assertInstanceOf(Map.class, updated.get("nested"));
        assertInstanceOf(Integer.class, updatedNested.get("whole"));
        List<?> updatedItems = assertInstanceOf(List.class, updated.get("items"));
        assertInstanceOf(Integer.class, updatedItems.get(0));
        assertInstanceOf(Double.class, updatedItems.get(1));
    }

    private static Map<String, Object> readOnlyStoredDocument(String domain, String collection) throws IOException {
        Path dataPath = DirectoryUtil.getCollectionDataPath(domain, "main", collection);
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(dataPath, "*" + BsonStorage.DOCUMENT_EXTENSION)) {
            for (Path path : stream) {
                return BsonStorage.readMap(path);
            }
        }
        throw new IOException("No BSON document found for " + domain + "/" + collection);
    }

    private static String uniqueName(String prefix) {
        return prefix + "_" + UUID.randomUUID().toString().replace("-", "");
    }
}
