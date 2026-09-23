// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import verun.vdb.VDB;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

public class VersaInstanceValue {
    private final VersaClassValue klass;
    private final Map<String, Object> fields = new LinkedHashMap<>();

    public VersaInstanceValue(VersaClassValue klass) {
        this.klass = klass;
    }

    public VersaClassValue getKlass() {
        return klass;
    }

    public boolean hasField(String name) {
        return fields.containsKey(name);
    }

    public Object getField(String name) {
        return fields.get(name);
    }

    public void setField(String name, Object value) {
        if (name == null) {
            fields.put(null, value);
            return;
        }
        if (!name.startsWith("__")) {
            Map<String, Object> patch = new LinkedHashMap<>();
            patch.put(name, value);
            klass.validatePatchOrThrow(patch);
        }
        fields.put(name, value);
    }

    public Map<String, Object> toDocumentMap() {
        Map<String, Object> out = new LinkedHashMap<>();
        for (Map.Entry<String, Object> e : fields.entrySet()) {
            String key = e.getKey();
            if (key == null || key.startsWith("__")) {
                continue;
            }
            Object value = e.getValue();
            if (value instanceof VersaInstanceValue) {
                out.put(key, ((VersaInstanceValue) value).toDocumentMap());
            } else {
                out.put(key, value);
            }
        }
        return out;
    }

    public Object save() {
        klass.runInstanceHook(this, "before_save", Collections.emptyList());
        String collection = klass.requireBoundCollection();
        Map<String, Object> doc = toDocumentMap();
        klass.runValidationOrThrow(doc, false);
        String id = fieldId();
        if (id != null && !id.isEmpty()) {
            Map<String, Object> query = new LinkedHashMap<>();
            query.put("_id", Collections.singletonMap("$eq", id));
            VDB.update(collection, query, doc);
            klass.runInstanceHook(this, "after_save", Collections.emptyList());
            return this;
        }
        Map<String, Object> inserted = VDB.insert(collection, doc);
        if (inserted != null) {
            for (Map.Entry<String, Object> e : inserted.entrySet()) {
                setField(e.getKey(), e.getValue());
            }
        }
        klass.runInstanceHook(this, "after_save", Collections.emptyList());
        return this;
    }

    public VersaInstanceValue update(Map<String, Object> patch) {
        klass.runInstanceHook(this, "before_update", Collections.singletonList(patch));
        klass.validatePatchOrThrow(patch);
        if (patch != null) {
            for (Map.Entry<String, Object> e : patch.entrySet()) {
                setField(e.getKey(), e.getValue());
            }
        }
        save();
        klass.runInstanceHook(this, "after_update", Collections.singletonList(patch));
        return this;
    }

    public boolean delete() {
        klass.runInstanceHook(this, "before_delete", Collections.emptyList());
        String collection = klass.requireBoundCollection();
        String id = fieldId();
        if (id != null && !id.isEmpty()) {
            VDB.delete(collection, id);
            klass.runInstanceHook(this, "after_delete", Collections.emptyList());
            return true;
        }
        int count = klass.deleteMany(toDocumentMap());
        if (count > 0) {
            klass.runInstanceHook(this, "after_delete", Collections.emptyList());
        }
        return count > 0;
    }

    public VersaInstanceValue reload() {
        String id = fieldId();
        if (id == null || id.isEmpty()) {
            return this;
        }
        VersaInstanceValue fresh = klass.findOne(Collections.singletonMap("_id", Collections.singletonMap("$eq", id)));
        if (fresh == null) {
            return this;
        }
        fields.clear();
        fields.putAll(fresh.fields);
        return this;
    }

    public Object propsFromSchema() {
        klass.applySchemaDefaults(this);
        return this;
    }

    public VersaInstanceValue assign(Map<String, Object> values) {
        if (values != null) {
            for (Map.Entry<String, Object> e : values.entrySet()) {
                setField(e.getKey(), e.getValue());
            }
        }
        return this;
    }

    public Object get(String name, Object fallback) {
        if (hasField(name)) {
            return getField(name);
        }
        return fallback;
    }

    public VersaInstanceValue set(String name, Object value) {
        setField(name, value);
        return this;
    }

    public boolean isPersisted() {
        String id = fieldId();
        return id != null && !id.isEmpty();
    }

    public String id() {
        return fieldId();
    }

    public VersaInstanceValue cloneInstance() {
        VersaInstanceValue cloned = new VersaInstanceValue(klass);
        cloned.assign(new LinkedHashMap<>(fields));
        return cloned;
    }

    public Map<String, Object> validate() {
        return klass.validateDocument(toDocumentMap(), false);
    }

    public String className() {
        return klass.getName();
    }

    private String fieldId() {
        Object id = fields.get("_id");
        return id == null ? null : String.valueOf(id);
    }

    @Override
    public String toString() {
        return "<" + klass.getName() + " " + ValueFormatter.toDisplayString(toDocumentMap()) + ">";
    }
}
