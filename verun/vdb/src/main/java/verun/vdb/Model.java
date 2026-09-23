// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import java.util.Map;

public abstract class Model {
    public String _id;
    public String collectionName;

    public Model() {
        this.collectionName = this.getClass().getSimpleName().toLowerCase() + "s";
    }

    public abstract Map<String, Object> toDocument();

    public abstract void fromDocument(Map<String, Object> doc);

    public void create() {
        Map<String, Object> doc = toDocument();
        VDB.insert(collectionName, doc);
        _id = (String) doc.get("_id");
    }

    public void save() {
        if (_id == null) {
            create();
        } else {
            update();
        }
    }

    public void update() {
        Map<String, Object> doc = toDocument();
        VDB.update(collectionName, _id, doc);
    }

    public void delete() {
        VDB.delete(collectionName, _id);
    }

    public static <T extends Model> T findById(Class<T> clazz, String id) {
        String collectionName = clazz.getSimpleName().toLowerCase() + "s";
        Map<String, Object> doc = VDB.findById(collectionName, id);
        if (doc == null) return null;
        
        try {
            T instance = clazz.getDeclaredConstructor().newInstance();
            instance.fromDocument(doc);
            return instance;
        } catch (Exception e) {
            throw new RuntimeException("Error creating instance of " + clazz.getName());
        }
    }

    public Map<String, Object> getSchema() {
        return schemaDefinition;
    }

    public void setSchema(Map<String, Object> schema) {
        this.schemaDefinition = schema;
    }

    protected Map<String, Object> schemaDefinition;
}