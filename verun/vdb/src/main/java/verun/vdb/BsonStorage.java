// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import com.google.gson.Gson;
import org.bson.BSONObject;
import org.bson.BasicBSONDecoder;
import org.bson.BasicBSONEncoder;
import org.bson.BasicBSONObject;
import org.bson.types.BasicBSONList;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class BsonStorage {
    static final String DOCUMENT_EXTENSION = ".bson";
    static final String LOG_EXTENSION = ".bsonlog";
    private static final Gson GSON = new Gson();
    private static final String ROOT_VALUE_KEY = "_value";

    private BsonStorage() {
    }

    static void writeDocument(Path path, Map<String, Object> document) throws IOException {
        writeValue(path, document);
    }

    static Map<String, Object> readDocument(Path path) throws IOException {
        return readMap(path);
    }

    static void writeValue(Path path, Object value) throws IOException {
        Files.createDirectories(path.getParent());
        Path tempPath = path.resolveSibling(path.getFileName().toString() + ".tmp");
        Files.write(tempPath, encodeValue(value));
        Files.move(tempPath, path, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
    }

    static Object readValue(Path path) throws IOException {
        return decodeValue(Files.readAllBytes(path));
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> readMap(Path path) throws IOException {
        Object value = readValue(path);
        if (value instanceof Map<?, ?>) {
            return new LinkedHashMap<>((Map<String, Object>) value);
        }
        return new LinkedHashMap<>();
    }

    @SuppressWarnings("unchecked")
    static List<Object> readList(Path path) throws IOException {
        Object value = readValue(path);
        if (value instanceof List<?>) {
            return new ArrayList<>((List<Object>) value);
        }
        return new ArrayList<>();
    }

    static void appendLogEntry(Path path, Map<String, Object> entry) throws IOException {
        Files.createDirectories(path.getParent());
        Files.write(path, encodeValue(entry), StandardOpenOption.CREATE, StandardOpenOption.APPEND);
    }

    static List<Map<String, Object>> readLogEntries(Path path) throws IOException {
        if (path == null || !Files.exists(path)) {
            return Collections.emptyList();
        }
        byte[] bytes = Files.readAllBytes(path);
        List<Map<String, Object>> out = new ArrayList<>();
        int offset = 0;
        while (offset + 4 <= bytes.length) {
            int length = ByteBuffer.wrap(bytes, offset, 4).order(ByteOrder.LITTLE_ENDIAN).getInt();
            if (length <= 0 || offset + length > bytes.length) {
                break;
            }
            byte[] slice = new byte[length];
            System.arraycopy(bytes, offset, slice, 0, length);
            Object value = decodeValue(slice);
            if (value instanceof Map<?, ?>) {
                @SuppressWarnings("unchecked")
                Map<String, Object> map = new LinkedHashMap<>((Map<String, Object>) value);
                out.add(map);
            }
            offset += length;
        }
        return out;
    }

    static boolean isBsonDocument(Path path) {
        String filename = path == null || path.getFileName() == null ? "" : path.getFileName().toString();
        return filename.endsWith(DOCUMENT_EXTENSION);
    }

    static boolean isBsonLog(Path path) {
        String filename = path == null || path.getFileName() == null ? "" : path.getFileName().toString();
        return filename.endsWith(LOG_EXTENSION);
    }

    static String toJson(Object value) {
        return GSON.toJson(value);
    }

    private static byte[] encodeValue(Object value) {
        BasicBSONObject root = new BasicBSONObject();
        root.put(ROOT_VALUE_KEY, toBsonValue(value));
        BSONObject bsonObject = root;
        return new BasicBSONEncoder().encode(bsonObject);
    }

    private static Object decodeValue(byte[] bytes) {
        Object decoded = new BasicBSONDecoder().readObject(bytes);
        if (decoded instanceof BSONObject) {
            Object raw = ((BSONObject) decoded).get(ROOT_VALUE_KEY);
            if (raw != null || ((BSONObject) decoded).containsField(ROOT_VALUE_KEY)) {
                return fromBsonValue(raw);
            }
            return fromBsonValue(decoded);
        }
        return new LinkedHashMap<>();
    }

    private static Object toBsonValue(Object value) {
        if (value instanceof Map<?, ?>) {
            BasicBSONObject out = new BasicBSONObject();
            for (Map.Entry<?, ?> entry : ((Map<?, ?>) value).entrySet()) {
                out.put(String.valueOf(entry.getKey()), toBsonValue(entry.getValue()));
            }
            return out;
        }
        if (value instanceof List<?>) {
            BasicBSONList out = new BasicBSONList();
            for (Object item : (List<?>) value) {
                out.add(toBsonValue(item));
            }
            return out;
        }
        if (value instanceof Number || value instanceof Boolean || value instanceof String || value == null) {
            return value;
        }
        return String.valueOf(value);
    }

    private static Object fromBsonValue(Object value) {
        if (value instanceof BasicBSONList) {
            List<Object> out = new ArrayList<>();
            for (Object item : (BasicBSONList) value) {
                out.add(fromBsonValue(item));
            }
            return out;
        }
        if (value instanceof BSONObject) {
            Map<String, Object> out = new LinkedHashMap<>();
            for (String key : ((BSONObject) value).keySet()) {
                out.put(key, fromBsonValue(((BSONObject) value).get(key)));
            }
            return out;
        }
        return value;
    }
}
