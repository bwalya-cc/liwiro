// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import verun.runtime.ast.ParameterNode;
import verun.vdb.Collection;
import verun.vdb.VDB;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

public class VersaClassValue implements Callable {
    private final String name;
    private final List<ParameterNode> constructorParameters;
    private final VersaClassValue parent;
    private final Map<String, UserFunction> instanceMethods = new LinkedHashMap<>();
    private final Map<String, UserFunction> staticMethods = new LinkedHashMap<>();
    private final Map<String, Object> staticFields = new LinkedHashMap<>();
    private final Object vdbBinding;

    public VersaClassValue(String name, List<ParameterNode> constructorParameters, VersaClassValue parent, Object vdbBinding) {
        this.name = name;
        this.constructorParameters = constructorParameters == null ? Collections.emptyList() : constructorParameters;
        this.parent = parent;
        this.vdbBinding = vdbBinding;
    }

    public String getName() {
        return name;
    }

    public VersaClassValue getParent() {
        return parent;
    }

    public Object getVdbBinding() {
        return vdbBinding;
    }

    public void addMethod(String name, UserFunction method, boolean isStatic) {
        if (isStatic) {
            staticMethods.put(name, method);
        } else {
            instanceMethods.put(name, method);
        }
    }

    public UserFunction getInstanceMethod(String methodName) {
        if (instanceMethods.containsKey(methodName)) {
            return instanceMethods.get(methodName);
        }
        return parent != null ? parent.getInstanceMethod(methodName) : null;
    }

    public UserFunction getStaticMethod(String methodName) {
        if (staticMethods.containsKey(methodName)) {
            return staticMethods.get(methodName);
        }
        return parent != null ? parent.getStaticMethod(methodName) : null;
    }

    public Object getStaticField(String fieldName) {
        if (staticFields.containsKey(fieldName)) {
            return staticFields.get(fieldName);
        }
        return parent != null ? parent.getStaticField(fieldName) : null;
    }

    public void setStaticField(String fieldName, Object value) {
        staticFields.put(fieldName, value);
    }

    @Override
    public Object call(List<Object> args) {
        return newInstance(args);
    }

    public VersaInstanceValue newInstance(List<Object> args) {
        VersaInstanceValue instance = new VersaInstanceValue(this);
        Map<String, Object> ctorLocals = bindConstructorFields(instance, args);
        applySchemaDefaults(instance);
        UserFunction init = getInstanceMethod("init");
        if (init != null) {
            invokeInstanceMethod(instance, init, "init", args, ctorLocals);
        }
        return instance;
    }

    private Map<String, Object> bindConstructorFields(VersaInstanceValue instance, List<Object> args) {
        Map<String, Object> defaultsEvaluatorEnv = new LinkedHashMap<>();
        defaultsEvaluatorEnv.put("this", instance);
        defaultsEvaluatorEnv.put(name, instance);
        Evaluator defaultsEvaluator = new Evaluator(new EvaluationContext(defaultsEvaluatorEnv));
        Map<String, Object> ctorLocals = new LinkedHashMap<>();
        for (int i = 0; i < constructorParameters.size(); i++) {
            ParameterNode param = constructorParameters.get(i);
            Object value;
            if (i < args.size()) {
                value = args.get(i);
            } else if (param.defaultValue != null) {
                value = defaultsEvaluator.evaluate(param.defaultValue);
            } else {
                value = null;
            }
            instance.setField(param.name, value);
            ctorLocals.put(param.name, value);
        }
        return ctorLocals;
    }

    public Object invokeInstanceMethod(VersaInstanceValue instance, UserFunction method, String methodName, List<Object> args) {
        return invokeInstanceMethod(instance, method, methodName, args, null);
    }

    public Object invokeInstanceMethod(VersaInstanceValue instance, UserFunction method, String methodName, List<Object> args,
            Map<String, Object> additionalBindings) {
        Map<String, Object> extras = new LinkedHashMap<>();
        extras.put("this", instance);
        addInheritanceAliases(extras, instance);
        extras.put("__class__", this);
        if (additionalBindings != null && !additionalBindings.isEmpty()) {
            extras.putAll(additionalBindings);
        }
        return method.callWithBindings(args, extras);
    }

    public Object invokeStaticMethod(UserFunction method, List<Object> args) {
        Map<String, Object> extras = new LinkedHashMap<>();
        addClassAliases(extras);
        extras.put("__class__", this);
        return method.callWithBindings(args, extras);
    }

    private void addInheritanceAliases(Map<String, Object> env, VersaInstanceValue instance) {
        VersaClassValue cursor = this;
        while (cursor != null) {
            env.put(cursor.getName(), instance);
            cursor = cursor.getParent();
        }
    }

    private void addClassAliases(Map<String, Object> env) {
        VersaClassValue cursor = this;
        while (cursor != null) {
            env.put(cursor.getName(), this);
            cursor = cursor.getParent();
        }
    }

    public Map<String, Object> callSchemaMap() {
        UserFunction schema = getStaticMethod("schema");
        if (schema != null) {
            Object value = invokeStaticMethod(schema, Collections.emptyList());
            if (value instanceof Map<?, ?>) {
                @SuppressWarnings("unchecked")
                Map<String, Object> out = (Map<String, Object>) value;
                return out;
            }
            return Collections.emptyMap();
        }
        UserFunction instanceSchema = getInstanceMethod("schema");
        if (instanceSchema != null) {
            VersaInstanceValue temp = new VersaInstanceValue(this);
            Object value = invokeInstanceMethod(temp, instanceSchema, "schema", Collections.emptyList());
            if (value instanceof Map<?, ?>) {
                @SuppressWarnings("unchecked")
                Map<String, Object> out = (Map<String, Object>) value;
                return out;
            }
        }
        return Collections.emptyMap();
    }

    public void applySchemaDefaults(VersaInstanceValue instance) {
        Map<String, Object> schema = callSchemaMap();
        if (schema == null || schema.isEmpty()) {
            return;
        }
        for (Map.Entry<String, Object> entry : schema.entrySet()) {
            String field = entry.getKey();
            if (instance.hasField(field)) {
                continue;
            }
            if (entry.getValue() instanceof Map<?, ?>) {
                Object defaultValue = ((Map<?, ?>) entry.getValue()).get("default");
                if (defaultValue != null) {
                    instance.setField(field, defaultValue);
                } else {
                    instance.setField(field, null);
                }
            }
        }
    }

    public Map<String, Object> validateDocument(Map<String, Object> doc, boolean partial) {
        Map<String, Object> schema = callSchemaMap();
        Map<String, Object> result = new LinkedHashMap<>();
        List<Object> errors = new ArrayList<>();
        if (schema != null && !schema.isEmpty()) {
            for (Map.Entry<String, Object> entry : schema.entrySet()) {
                String field = entry.getKey();
                if (!(entry.getValue() instanceof Map<?, ?>)) {
                    continue;
                }
                Map<?, ?> fieldSchema = (Map<?, ?>) entry.getValue();
                boolean required = truthy(fieldSchema.get("required"));
                Object value = doc.get(field);
                boolean present = doc.containsKey(field);
                if (!partial && required && !present) {
                    errors.add("Missing required field: " + field);
                    continue;
                }
                if (!present) {
                    continue;
                }
                Object typeObj = fieldSchema.get("type");
                if (typeObj != null) {
                    String expected = normalizeSchemaType(String.valueOf(typeObj));
                    if (!expected.isEmpty() && !matchesSchemaType(value, expected)) {
                        errors.add("Invalid type for '" + field + "': expected " + expected + ", got " + typeOf(value));
                    }
                }
            }
        }
        result.put("ok", errors.isEmpty());
        result.put("errors", errors);
        result.put("schema", schema == null ? Collections.emptyMap() : schema);
        return result;
    }

    public String resolveCollectionName() {
        if (vdbBinding instanceof Collection) {
            return ((Collection) vdbBinding).getName();
        }
        if (vdbBinding instanceof String) {
            return String.valueOf(vdbBinding);
        }
        if (vdbBinding instanceof Map<?, ?>) {
            Object nameObj = ((Map<?, ?>) vdbBinding).get("name");
            if (nameObj != null) {
                return String.valueOf(nameObj);
            }
        }
        return null;
    }

    public VersaInstanceValue fromDocument(Map<String, Object> doc) {
        VersaInstanceValue instance = new VersaInstanceValue(this);
        applySchemaDefaults(instance);
        if (doc != null) {
            for (Map.Entry<String, Object> e : doc.entrySet()) {
                instance.setField(e.getKey(), e.getValue());
            }
        }
        return instance;
    }

    public VersaInstanceValue fromObject(Map<String, Object> data, boolean persist) {
        VersaInstanceValue instance = newInstance(Collections.emptyList());
        if (data != null) {
            instance.assign(data);
        }
        if (persist) {
            instance.save();
        }
        return instance;
    }

    public List<VersaInstanceValue> findMany(Map<String, Object> query, int limit) {
        String collection = requireBoundCollection();
        List<Map<String, Object>> docs = VDB.find(collection, query == null ? Collections.emptyMap() : query, limit <= 0 ? 100 : limit);
        List<VersaInstanceValue> out = new ArrayList<>();
        for (Map<String, Object> doc : docs) {
            out.add(fromDocument(doc));
        }
        return out;
    }

    public VersaInstanceValue findOne(Map<String, Object> query) {
        List<VersaInstanceValue> found = findMany(query, 1);
        return found.isEmpty() ? null : found.get(0);
    }

    public VersaInstanceValue findById(Object id) {
        if (id == null) {
            return null;
        }
        Map<String, Object> query = new LinkedHashMap<>();
        query.put("_id", Collections.singletonMap("$eq", String.valueOf(id)));
        return findOne(query);
    }

    public int count(Map<String, Object> query) {
        return findMany(query, Integer.MAX_VALUE).size();
    }

    public boolean exists(Map<String, Object> query) {
        return findOne(query) != null;
    }

    public int updateMany(Map<String, Object> query, Map<String, Object> patch) {
        String collection = requireBoundCollection();
        validatePatchOrThrow(patch);
        String result = VDB.update(collection,
                query == null ? Collections.emptyMap() : query,
                patch == null ? Collections.emptyMap() : patch);
        return parseAffectedCount(result);
    }

    public VersaInstanceValue firstOrCreate(Map<String, Object> query, Map<String, Object> defaults) {
        VersaInstanceValue existing = findOne(query);
        if (existing != null) {
            return existing;
        }
        Map<String, Object> data = new LinkedHashMap<>();
        if (defaults != null) {
            data.putAll(defaults);
        }
        if (query != null) {
            mergeSimpleEqFieldsIntoData(query, data);
        }
        return fromObject(data, true);
    }

    public VersaInstanceValue upsert(Map<String, Object> query, Map<String, Object> patch) {
        VersaInstanceValue existing = findOne(query);
        if (existing != null) {
            existing.update(patch == null ? Collections.emptyMap() : patch);
            return existing;
        }
        Map<String, Object> data = new LinkedHashMap<>();
        if (query != null) {
            mergeSimpleEqFieldsIntoData(query, data);
        }
        if (patch != null) {
            data.putAll(patch);
        }
        return fromObject(data, true);
    }

    public int deleteMany(Map<String, Object> query) {
        String collection = requireBoundCollection();
        String result = VDB.delete(collection, query == null ? Collections.emptyMap() : query);
        return parseAffectedCount(result);
    }

    public boolean deleteById(Object id) {
        VersaInstanceValue found = findById(id);
        return found != null && found.delete();
    }

    public String requireBoundCollection() {
        String name = resolveCollectionName();
        if (name == null || name.trim().isEmpty()) {
            throw new RuntimeException("Class '" + this.name + "' is not bound to a VDB collection");
        }
        if (!VDB.collectionExists(VDB.getCurrentDomain(), VDB.getCurrentDB(), name)) {
            VDB.createCollection(name);
        }
        return name;
    }

    public Map<String, Object> bindingInfo() {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("class", name);
        out.put("collection", resolveCollectionName());
        out.put("bound", resolveCollectionName() != null);
        out.put("schema", callSchemaMap());
        return out;
    }

    public void runValidationOrThrow(Map<String, Object> doc, boolean partial) {
        Map<String, Object> validation = validateDocument(doc, partial);
        Object ok = validation.get("ok");
        if (!(ok instanceof Boolean) || !((Boolean) ok)) {
            throw new RuntimeException("Schema validation failed: " + validation.get("errors"));
        }
    }

    public Object runInstanceHook(VersaInstanceValue instance, String hookName, List<Object> args) {
        UserFunction hook = getInstanceMethod(hookName);
        if (hook == null) {
            return null;
        }
        return invokeInstanceMethod(instance, hook, hookName, args == null ? Collections.emptyList() : args);
    }

    public void validatePatchOrThrow(Map<String, Object> patch) {
        if (patch == null) {
            return;
        }
        runValidationOrThrow(patch, true);
    }

    private int parseAffectedCount(String text) {
        if (text == null) {
            return 0;
        }
        String digits = text.replaceAll("\\D+", " ").trim();
        if (digits.isEmpty()) {
            return 0;
        }
        String[] parts = digits.split("\\s+");
        return Integer.parseInt(parts[0]);
    }

    private void mergeSimpleEqFieldsIntoData(Map<String, Object> query, Map<String, Object> data) {
        for (Map.Entry<String, Object> e : query.entrySet()) {
            Object value = e.getValue();
            if (value instanceof Map<?, ?>) {
                Map<?, ?> map = (Map<?, ?>) value;
                if (map.containsKey("$eq")) {
                    data.put(e.getKey(), map.get("$eq"));
                }
            } else {
                data.put(e.getKey(), value);
            }
        }
    }

    private String normalizeSchemaType(String raw) {
        String t = raw == null ? "" : raw.trim().toLowerCase(Locale.ROOT);
        if ("string".equals(t) || "str".equals(t)) return "string";
        if ("bool".equals(t) || "boolean".equals(t)) return "bool";
        if ("int".equals(t) || "integer".equals(t)) return "int";
        if ("float".equals(t) || "double".equals(t) || "number".equals(t)) return "number";
        if ("object".equals(t) || "map".equals(t)) return "object";
        if ("list".equals(t) || "array".equals(t)) return "list";
        if ("null".equals(t)) return "null";
        return t;
    }

    private boolean matchesSchemaType(Object value, String expected) {
        if ("any".equals(expected) || expected.isEmpty()) return true;
        if (value == null) return true;
        if ("null".equals(expected)) return value == null;
        if ("string".equals(expected)) return value instanceof String;
        if ("bool".equals(expected)) return value instanceof Boolean;
        if ("int".equals(expected)) return value instanceof Integer;
        if ("number".equals(expected)) return value instanceof Number;
        if ("list".equals(expected)) return value instanceof List<?>;
        if ("object".equals(expected)) return value instanceof Map<?, ?> || value instanceof VersaInstanceValue;
        if ("class".equals(expected)) return value instanceof VersaClassValue;
        return true;
    }

    private String typeOf(Object value) {
        if (value == null) return "null";
        if (value instanceof Integer) return "int";
        if (value instanceof Number) return "number";
        if (value instanceof String) return "string";
        if (value instanceof Boolean) return "bool";
        if (value instanceof List<?>) return "list";
        if (value instanceof Map<?, ?>) return "object";
        if (value instanceof VersaInstanceValue) return "object";
        if (value instanceof VersaClassValue) return "class";
        return value.getClass().getSimpleName();
    }

    private boolean truthy(Object value) {
        if (value == null) return false;
        if (value instanceof Boolean) return (Boolean) value;
        if (value instanceof Number) return ((Number) value).doubleValue() != 0.0d;
        return !Objects.toString(value, "").trim().isEmpty();
    }

    @Override
    public String toString() {
        return "<class " + name + ">";
    }
}
