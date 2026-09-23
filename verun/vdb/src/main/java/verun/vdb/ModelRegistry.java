// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import java.util.HashMap;
import java.util.Map;

public class ModelRegistry {
    public static final Map<String, Class<?>> registry = new HashMap<>();
    
    public static void register(Class<?> modelClass, String collectionName) {
        registry.put(collectionName, modelClass);
        VDB.createCollection(collectionName);
    }
    
    public static Class<?> getModel(String collectionName) {
        return registry.get(collectionName);
    }
}
