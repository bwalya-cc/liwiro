// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import verun.runtime.ast.MemberAccessNode;
import verun.vdb.Collection;
import verun.vdb.ScriptDocument;
import verun.vdb.VDB;

import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.function.Supplier;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MemberAccessEvaluator {
    private static final Pattern AFFECTED_COUNT_PATTERN = Pattern.compile("(\\d+)");
    private static final Pattern JSON_ERROR_PATTERN = Pattern.compile("\"error\"\\s*:\\s*\"([^\"]+)\"");

    public static Object evaluateMemberAccess(MemberAccessNode node, Evaluator evaluator) {
        Object object = evaluator.evaluate(node.object);
        String member = node.member;

        if (object instanceof VDBNative || object == VDB.class) {
            if (!"auth".equals(member) && !"config".equals(member) && VDB.getCurrentUser() == null) {
                throw new EvaluationException(
                        VdbExceptionTypes.NOT_AUTHENTICATED,
                        "Not authenticated: call vdb.auth({user: ..., pass: ...}) first");
            }
            if ("create".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("create_collection", null, () -> {
                    if (args.isEmpty()) {
                        throw new RuntimeException("vdb.create expects at least a collection name");
                    }
                    String collectionName = String.valueOf(args.get(0));
                    if (args.size() >= 2 && args.get(1) != null) {
                        Object rawClass = args.get(1);
                        if (rawClass instanceof VersaClassValue) {
                            VersaClassValue versaClass = (VersaClassValue) rawClass;
                            VDB.createCollection(collectionName, versaClass.callSchemaMap());
                            return "Collection created: " + collectionName;
                        }
                        if (rawClass instanceof Class<?>) {
                            return VDB.create(collectionName, (Class<?>) rawClass);
                        }
                        throw new RuntimeException("vdb.create second argument must be a class reference");
                    }
                    VDB.createCollection(collectionName);
                    return "Collection created: " + collectionName;
                }));
            } else if ("auth".equals(member)) {
                return new BuiltinFunction(args -> {
                    if (args.isEmpty() || !(args.get(0) instanceof Map<?, ?>)) {
                        throw new EvaluationException(
                                VdbExceptionTypes.AUTH,
                                "vdb.auth expects an object like {user: \"name\", pass: \"password\"}");
                    }
                    Map<String, String> auth = coerceStringMap((Map<?, ?>) args.get(0));
                    String result = VDB.auth(auth);
                    String error = extractVdbError(result);
                    if (error != null) {
                        throw new EvaluationException(VdbExceptionTypes.inferFromMessage(error), error);
                    }
                    return vdbSuccess("auth", null, "Authentication successful", result, null);
                });
            } else if ("config".equals(member)) {
                return new BuiltinFunction(args -> {
                    if (args.isEmpty()) {
                        Map<String, Object> cfg = new HashMap<>();
                        cfg.put("logs", VDB.isRuntimeLogsEnabled());
                        cfg.put("logging", VDB.isRuntimeLogsEnabled());
                        return vdbSuccess("config", null, "Current configuration", cfg, null);
                    }
                    Object first = args.get(0);
                    if (!(first instanceof Map<?, ?>)) {
                        return vdbError("config", null, "Invalid config payload", "vdb.config expects an object like {logging: true}", null);
                    }
                    Map<?, ?> cfg = (Map<?, ?>) first;
                    Object value = cfg.containsKey("logging") ? cfg.get("logging") : cfg.get("logs");
                    if (value != null) {
                        boolean enabled;
                        if (value instanceof Boolean) {
                            enabled = (Boolean) value;
                        } else {
                            enabled = value != null && Boolean.parseBoolean(String.valueOf(value));
                        }
                        VDB.setRuntimeLogsEnabled(enabled);
                    }
                    Map<String, Object> out = new HashMap<>();
                    out.put("logs", VDB.isRuntimeLogsEnabled());
                    out.put("logging", VDB.isRuntimeLogsEnabled());
                    return vdbSuccess("config", null, "Configuration updated", out, null);
                });
            } else if ("set".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("set_context", null, () -> {
                    Map<String, Object> data = (Map<String, Object>) args.get(0);
                    if (data.containsKey("domain")) {
                        String domain = data.get("domain").toString();
                        if (!verun.vdb.VDB.domainExists(domain)) {
                            VDB.defineDomain(domain, "main", false);
                        }
                        VDB.useDomain(domain);
                    }
                    if (data.containsKey("database")) {
                        String db = data.get("database").toString();
                        if (!VDB.listDatabases().contains(db)) {
                            try {
                                VDB.createDatabase(db);
                            } catch (RuntimeException ignored) {
                                // Ignore if DB already exists due stale directory cache/race.
                            }
                        }
                        VDB.useDatabase(db);
                    } else if (data.containsKey("db")) {
                        String db = data.get("db").toString();
                        if (!VDB.listDatabases().contains(db)) {
                            try {
                                VDB.createDatabase(db);
                            } catch (RuntimeException ignored) {
                                // Ignore if DB already exists due stale directory cache/race.
                            }
                        }
                        VDB.useDatabase(db);
                    }
                    Map<String, Object> context = new LinkedHashMap<>();
                    context.put("domain", VDB.getCurrentDomain());
                    context.put("database", VDB.getCurrentDB());
                    return context;
                }));
            } else if ("collection".equals(member)) {
                return new BuiltinFunction(args -> {
                    String collectionName = args.get(0).toString();
                    if (!VDB.collectionExists(VDB.getCurrentDomain(), VDB.getCurrentDB(), collectionName)) {
                        VDB.createCollection(collectionName);
                    }
                    return new Collection(collectionName);
                });
            } else if ("insert".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("insert", args.get(0).toString(), () -> {
                    String collectionName = args.get(0).toString();
                    Map<String, Object> document = (Map<String, Object>) args.get(1);
                    return VDB.insert(collectionName, document);
                }));
            } else if ("find".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("find", args.get(0).toString(), () -> {
                    String collectionName = args.get(0).toString();
                    Map<String, Object> query = (Map<String, Object>) args.get(1);
                    int limit = (Integer) args.get(2);
                    return VDB.find(collectionName, query, limit);
                }));
            } else if ("update".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("update", args.get(0).toString(), () -> {
                    String collectionName = args.get(0).toString();
                    Map<String, Object> query = (Map<String, Object>) args.get(1);
                    Map<String, Object> update = (Map<String, Object>) args.get(2);
                    return VDB.update(collectionName, query, update);
                }));
            } else if ("delete".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("delete", args.get(0).toString(), () -> {
                    String collectionName = args.get(0).toString();
                    Map<String, Object> query = (Map<String, Object>) args.get(1);
                    return VDB.delete(collectionName, query);
                }));
            } else if ("list_collections".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("list_collections", null, VDB::listCollections));
            } else if ("list_databases".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("list_databases", null, VDB::listDatabases));
            } else if ("drop".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("drop_collection", args.get(0).toString(), () -> {
                    String collectionName = args.get(0).toString();
                    VDB.drop(collectionName);
                    return "Dropped collection " + collectionName;
                }));
            } else if ("define".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("define", null, () -> {
                    Map<String, Object> define = (Map<String, Object>) args.get(0);
                    String domain = define.containsKey("domain") ? define.get("domain").toString() : null;
                    String db = define.containsKey("db")
                            ? define.get("db").toString()
                            : (define.containsKey("database") ? define.get("database").toString() : "main");
                    if (domain != null) {
                        VDB.defineDomain(domain, db, false);
                    } else if (db != null) {
                        VDB.createDatabase(db);
                    }
                    Map<String, Object> context = new LinkedHashMap<>();
                    context.put("domain", VDB.getCurrentDomain());
                    context.put("database", VDB.getCurrentDB());
                    return context;
                }));
            } else if ("use".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("use", null, () -> {
                    Map<String, Object> use = (Map<String, Object>) args.get(0);
                    if (use.containsKey("domain")) {
                        String domain = use.get("domain").toString();
                        if (!verun.vdb.VDB.domainExists(domain)) {
                            VDB.defineDomain(domain, "main", false);
                        }
                        VDB.useDomain(domain);
                    }
                    if (use.containsKey("db")) {
                        String db = use.get("db").toString();
                        if (!VDB.listDatabases().contains(db)) {
                            try {
                                VDB.createDatabase(db);
                            } catch (RuntimeException ignored) {
                                // Ignore if DB already exists due stale directory cache/race.
                            }
                        }
                        VDB.useDatabase(db);
                    } else if (use.containsKey("database")) {
                        String db = use.get("database").toString();
                        if (!VDB.listDatabases().contains(db)) {
                            try {
                                VDB.createDatabase(db);
                            } catch (RuntimeException ignored) {
                                // Ignore if DB already exists due stale directory cache/race.
                            }
                        }
                        VDB.useDatabase(db);
                    }
                    Map<String, Object> context = new LinkedHashMap<>();
                    context.put("domain", VDB.getCurrentDomain());
                    context.put("database", VDB.getCurrentDB());
                    return context;
                }));
            } else if ("tumi".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("tumi", null, () -> {
                    Map<String, Object> tumiCmd = (Map<String, Object>) args.get(0);
                    return VDB.tumi(tumiCmd);
                }));
            } else if ("save_script".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("save_script", null, () -> {
                    String name = args.get(0).toString();
                    String service = args.get(1).toString();
                    String code = args.get(2).toString();
                    return VDB.saveScript(name, service, code);
                }));
            } else if ("load_script".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("load_script", null, () -> {
                    String name = args.get(0).toString();
                    ScriptDocument script = VDB.loadScript(name);
                    Map<String, Object> response = new LinkedHashMap<>();
                    response.put("name", script.name);
                    response.put("service", script.serviceName);
                    response.put("code", script.code);
                    response.put("language", script.language);
                    response.put("extension", script.extension);
                    return response;
                }));
            } else if ("delete_script".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("delete_script", null, () -> {
                    String name = args.get(0).toString();
                    return VDB.deleteScript(name);
                }));
            } else if ("execute_script".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("execute_script", null, () -> {
                    String name = args.get(0).toString();
                    Map<String, Object> params = args.size() > 1 && args.get(1) instanceof Map
                            ? (Map<String, Object>) args.get(1)
                            : Collections.emptyMap();
                    return Evaluator.executeVdbScript(name, () -> {
                        ScriptDocument script = VDB.loadScript(name);

                        // Execute stored Versa in current evaluator context.
                        if (script.code != null && !script.code.trim().isEmpty()) {
                            verun.runtime.lexer.Lexer lexer = new verun.runtime.lexer.Lexer(script.code);
                            List<verun.runtime.lexer.Token> tokens = lexer.tokenize();
                            verun.runtime.parser.Parser parser = new verun.runtime.parser.Parser(tokens, script.code);
                            verun.runtime.ast.Node ast = parser.parse();
                            Evaluator nested = new Evaluator(false, tokens, script.code);
                            for (Map.Entry<String, Object> entry : evaluator.getEnvironment().entrySet()) {
                                String key = entry.getKey();
                                if (("vdb".equals(key) || "http".equals(key) || "email".equals(key) || "json_xml".equals(key)
                                        || "filer".equals(key)
                                        || "crypto".equals(key) || "jwt".equals(key) || "time".equals(key)
                                        || "datetime".equals(key) || "random".equals(key))
                                        && !nested.getEnvironment().containsKey(key)) {
                                    continue;
                                }
                                nested.getEnvironment().put(key, entry.getValue());
                            }
                            nested.getEnvironment().put("params", params);
                            Object value = nested.evaluate(ast);
                            Map<String, Object> result = new LinkedHashMap<>();
                            result.put("result", value);
                            if (params.containsKey("collection")) {
                                String collection = params.get("collection").toString();
                                result.put("collection_data", VDB.find(collection, Collections.emptyMap(), Integer.MAX_VALUE));
                            }
                            return result;
                        }
                        return VDB.executeScript(name, params);
                    });
                }));
            } else if ("aggregate".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("aggregate", args.get(0).toString(), () -> {
                    String collectionName = args.get(0).toString();
                    List<Map<String, Object>> pipeline = (List<Map<String, Object>>) args.get(1);
                    return VDB.aggregate(collectionName, pipeline);
                }));
            } else if ("create_index".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("create_index", args.get(0).toString(), () -> {
                    String collectionName = args.get(0).toString();
                    String field = String.valueOf(args.get(1));
                    boolean unique = args.size() > 2 && args.get(2) instanceof Boolean && (Boolean) args.get(2);
                    return VDB.createIndex(collectionName, field, unique);
                }));
            } else if ("drop_index".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("drop_index", args.get(0).toString(), () -> {
                    String collectionName = args.get(0).toString();
                    String field = String.valueOf(args.get(1));
                    return VDB.dropIndex(collectionName, field);
                }));
            } else if ("list_indexes".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("list_indexes", args.get(0).toString(), () -> {
                    String collectionName = args.get(0).toString();
                    return VDB.listIndexes(collectionName);
                }));
            } else if ("rebuild_indexes".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("rebuild_indexes", args.get(0).toString(), () -> {
                    String collectionName = args.get(0).toString();
                    return VDB.rebuildIndexes(collectionName);
                }));
            } else if ("index_advisor_status".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("index_advisor_status", null,
                        () -> verun.vdb.IndexAdvisor.advisorStatus(VDB.getCurrentDomain(), VDB.getCurrentDB())));
            } else if ("index_advisor_apply".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("index_advisor_apply", null, () -> {
                    int limit = args.isEmpty() ? Integer.MAX_VALUE : ((Number) args.get(0)).intValue();
                    Map<String, Object> result = new LinkedHashMap<>();
                    result.put("created", verun.vdb.IndexAdvisor.applyRecommendations(
                            VDB.getCurrentDomain(),
                            VDB.getCurrentDB(),
                            limit));
                    result.put("status", verun.vdb.IndexAdvisor.advisorStatus(VDB.getCurrentDomain(), VDB.getCurrentDB()));
                    return result;
                }));
            } else if ("index_advisor_policy".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("index_advisor_policy", null, () -> {
                    if (args.isEmpty()) {
                        return verun.vdb.IndexAdvisor.advisorStatus(VDB.getCurrentDomain(), VDB.getCurrentDB()).get("policy");
                    }
                    return verun.vdb.IndexAdvisor.setPolicy(String.valueOf(args.get(0)));
                }));
            } else if ("index_advisor_remove_auto_indexes".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("index_advisor_remove_auto_indexes", null, () -> {
                    Map<String, Object> result = new LinkedHashMap<>();
                    result.put("removed", verun.vdb.IndexAdvisor.removeAdvisorIndexes(
                            VDB.getCurrentDomain(),
                            VDB.getCurrentDB()));
                    return result;
                }));
            } else if ("begin_transaction".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("begin_transaction", null, () -> {
                    VDB.beginTransaction();
                    return "Transaction started";
                }));
            } else if ("commit_transaction".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("commit_transaction", null, () -> {
                    VDB.commitTransaction();
                    return "Transaction committed";
                }));
            } else if ("abort_transaction".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("abort_transaction", null, () -> {
                    VDB.abortTransaction();
                    return "Transaction aborted";
                }));
            } else if ("list_scripts".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("list_scripts", null, VDB::listScripts));
            } else if ("list_domains".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("list_domains", null, verun.vdb.DirectoryUtil::getDomains));
            } else if ("schedule_job".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("schedule_job", null, () -> {
                    if (args.isEmpty() || !(args.get(0) instanceof Map<?, ?>)) {
                        throw new RuntimeException("vdb.schedule_job expects an object payload");
                    }
                    Map<String, Object> cfg = (Map<String, Object>) args.get(0);
                    String name = String.valueOf(cfg.get("name"));
                    String script = String.valueOf(cfg.get("script"));
                    long now = System.currentTimeMillis();
                    long startAt = cfg.containsKey("start_at")
                            ? parseTimeMillis(cfg.get("start_at"), now)
                            : now;
                    long everySeconds = cfg.containsKey("every_seconds")
                            ? Math.max(1L, ((Number) cfg.get("every_seconds")).longValue())
                            : 60L;
                    Map<String, Object> params = cfg.containsKey("params") && cfg.get("params") instanceof Map
                            ? (Map<String, Object>) cfg.get("params")
                            : Collections.emptyMap();
                    return VDBScriptJobs.scheduleJob(name, script, startAt, everySeconds, params, evaluator);
                }));
            } else if ("list_jobs".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("list_jobs", null, VDBScriptJobs::listJobs));
            } else if ("cancel_job".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("cancel_job", null, () -> {
                    String name = args.isEmpty() ? "" : String.valueOf(args.get(0));
                    return VDBScriptJobs.cancelJob(name);
                }));
            } else if ("model".equals(member)) {
                Map<String, Object> model = new HashMap<>();
                model.put("register", new BuiltinFunction(args -> {
                    Class<?> modelClass = (Class<?>) args.get(0);
                    String collectionName = args.get(1).toString();
                    verun.vdb.ModelRegistry.register(modelClass, collectionName);
                    return null;
                }));
                return model;
            }
        }

        if (object instanceof Collection) {
            Collection collection = (Collection) object;
            if ("insert".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("insert", collection.getName(), () -> {
                    Map<String, Object> document = (Map<String, Object>) args.get(0);
                    return VDB.insert(collection.getName(), document);
                }));
            } else if ("find".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("find", collection.getName(), () -> {
                    Map<String, Object> query = (Map<String, Object>) args.get(0);
                    int limit = args.size() > 1 ? ((Number) args.get(1)).intValue() : Integer.MAX_VALUE;
                    return collection.find(query, limit);
                }));
            } else if ("delete".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("delete", collection.getName(), () -> {
                    Map<String, Object> query = (Map<String, Object>) args.get(0);
                    return collection.delete(query);
                }));
            } else if ("update".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("update", collection.getName(), () -> {
                    Map<String, Object> query = (Map<String, Object>) args.get(0);
                    Map<String, Object> update = (Map<String, Object>) args.get(1);
                    return VDB.update(collection.getName(), query, update);
                }));
            } else if ("create_index".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("create_index", collection.getName(), () -> {
                    String field = String.valueOf(args.get(0));
                    boolean unique = args.size() > 1 && args.get(1) instanceof Boolean && (Boolean) args.get(1);
                    return VDB.createIndex(collection.getName(), field, unique);
                }));
            } else if ("drop_index".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("drop_index", collection.getName(), () -> {
                    String field = String.valueOf(args.get(0));
                    return VDB.dropIndex(collection.getName(), field);
                }));
            } else if ("list_indexes".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("list_indexes", collection.getName(),
                        () -> VDB.listIndexes(collection.getName())));
            } else if ("rebuild_indexes".equals(member)) {
                return new BuiltinFunction(args -> runVdbOperation("rebuild_indexes", collection.getName(),
                        () -> VDB.rebuildIndexes(collection.getName())));
            }
        }

        if (object instanceof String) {
            String str = (String) object;
            return new BuiltinFunction(args -> {
                return StringEvaluator.callMethod(member, str, args);
            });
        }

        if (object instanceof VersaClassValue) {
            VersaClassValue clazz = (VersaClassValue) object;
            if ("name".equals(member) || "class_name".equals(member)) {
                return clazz.getName();
            }
            if ("collection".equals(member) || "collection_name".equals(member)) {
                return clazz.resolveCollectionName();
            }
            if ("binding_info".equals(member) || "meta".equals(member)) {
                return new BuiltinFunction(args -> clazz.bindingInfo());
            }
            if ("schema".equals(member)) {
                return new BuiltinFunction(args -> clazz.callSchemaMap());
            }
            if ("new".equals(member) || "build".equals(member) || "construct".equals(member)) {
                return new BuiltinFunction(args -> clazz.newInstance(args));
            }
            if ("find".equals(member)) {
                return new BuiltinFunction(args -> {
                    Map<String, Object> query = args.isEmpty() || !(args.get(0) instanceof Map<?, ?>)
                            ? Collections.emptyMap()
                            : (Map<String, Object>) args.get(0);
                    return clazz.findOne(query);
                });
            }
            if ("find_by_id".equals(member)) {
                return new BuiltinFunction(args -> args.isEmpty() ? null : clazz.findById(args.get(0)));
            }
            if ("find_many".equals(member) || "all".equals(member)) {
                return new BuiltinFunction(args -> {
                    Map<String, Object> query = Collections.emptyMap();
                    int limit = 100;
                    if (!"all".equals(member)) {
                        if (!args.isEmpty() && args.get(0) instanceof Map<?, ?>) {
                            query = (Map<String, Object>) args.get(0);
                        }
                        if (args.size() > 1 && args.get(1) instanceof Number) {
                            limit = ((Number) args.get(1)).intValue();
                        }
                    } else {
                        if (!args.isEmpty() && args.get(0) instanceof Number) {
                            limit = ((Number) args.get(0)).intValue();
                        }
                    }
                    return clazz.findMany(query, limit);
                });
            }
            if ("count".equals(member)) {
                return new BuiltinFunction(args -> {
                    Map<String, Object> query = args.isEmpty() || !(args.get(0) instanceof Map<?, ?>)
                            ? Collections.emptyMap()
                            : (Map<String, Object>) args.get(0);
                    return clazz.count(query);
                });
            }
            if ("exists".equals(member)) {
                return new BuiltinFunction(args -> {
                    Map<String, Object> query = args.isEmpty() || !(args.get(0) instanceof Map<?, ?>)
                            ? Collections.emptyMap()
                            : (Map<String, Object>) args.get(0);
                    return clazz.exists(query);
                });
            }
            if ("delete_many".equals(member)) {
                return new BuiltinFunction(args -> {
                    Map<String, Object> query = args.isEmpty() || !(args.get(0) instanceof Map<?, ?>)
                            ? Collections.emptyMap()
                            : (Map<String, Object>) args.get(0);
                    return clazz.deleteMany(query);
                });
            }
            if ("delete_by_id".equals(member)) {
                return new BuiltinFunction(args -> args.isEmpty() ? false : clazz.deleteById(args.get(0)));
            }
            if ("update_many".equals(member)) {
                return new BuiltinFunction(args -> {
                    Map<String, Object> query = args.isEmpty() || !(args.get(0) instanceof Map<?, ?>)
                            ? Collections.emptyMap()
                            : (Map<String, Object>) args.get(0);
                    Map<String, Object> patch = args.size() > 1 && args.get(1) instanceof Map<?, ?>
                            ? (Map<String, Object>) args.get(1)
                            : Collections.emptyMap();
                    return clazz.updateMany(query, patch);
                });
            }
            if ("create".equals(member)) {
                return new BuiltinFunction(args -> {
                    VersaInstanceValue instance = clazz.newInstance(Collections.emptyList());
                    if (!args.isEmpty() && args.get(0) instanceof Map<?, ?>) {
                        Map<String, Object> data = (Map<String, Object>) args.get(0);
                        for (Map.Entry<String, Object> e : data.entrySet()) {
                            instance.setField(e.getKey(), e.getValue());
                        }
                    }
                    instance.save();
                    return instance;
                });
            }
            if ("from_object".equals(member)) {
                return new BuiltinFunction(args -> {
                    Map<String, Object> data = args.isEmpty() || !(args.get(0) instanceof Map<?, ?>)
                            ? Collections.emptyMap()
                            : (Map<String, Object>) args.get(0);
                    boolean persist = args.size() > 1 && args.get(1) instanceof Boolean && (Boolean) args.get(1);
                    return clazz.fromObject(data, persist);
                });
            }
            if ("first_or_create".equals(member)) {
                return new BuiltinFunction(args -> {
                    Map<String, Object> query = args.isEmpty() || !(args.get(0) instanceof Map<?, ?>)
                            ? Collections.emptyMap()
                            : (Map<String, Object>) args.get(0);
                    Map<String, Object> defaults = args.size() > 1 && args.get(1) instanceof Map<?, ?>
                            ? (Map<String, Object>) args.get(1)
                            : Collections.emptyMap();
                    return clazz.firstOrCreate(query, defaults);
                });
            }
            if ("upsert".equals(member)) {
                return new BuiltinFunction(args -> {
                    Map<String, Object> query = args.isEmpty() || !(args.get(0) instanceof Map<?, ?>)
                            ? Collections.emptyMap()
                            : (Map<String, Object>) args.get(0);
                    Map<String, Object> patch = args.size() > 1 && args.get(1) instanceof Map<?, ?>
                            ? (Map<String, Object>) args.get(1)
                            : Collections.emptyMap();
                    return clazz.upsert(query, patch);
                });
            }
            if ("schema_defaults".equals(member)) {
                return new BuiltinFunction(args -> clazz.callSchemaMap());
            }

            UserFunction staticMethod = clazz.getStaticMethod(member);
            if (staticMethod != null) {
                return new BuiltinFunction(args -> clazz.invokeStaticMethod(staticMethod, args));
            }
            Object staticField = clazz.getStaticField(member);
            if (staticField != null) {
                return staticField;
            }
        }

        if (object instanceof VersaInstanceValue) {
            VersaInstanceValue instance = (VersaInstanceValue) object;
            VersaClassValue clazz = instance.getKlass();
            if ("save".equals(member)) {
                return new BuiltinFunction(args -> instance.save());
            }
            if ("update".equals(member)) {
                return new BuiltinFunction(args -> {
                    Map<String, Object> patch = args.isEmpty() || !(args.get(0) instanceof Map<?, ?>)
                            ? Collections.emptyMap()
                            : (Map<String, Object>) args.get(0);
                    return instance.update(patch);
                });
            }
            if ("delete".equals(member)) {
                return new BuiltinFunction(args -> instance.delete());
            }
            if ("reload".equals(member)) {
                return new BuiltinFunction(args -> instance.reload());
            }
            if ("refresh".equals(member)) {
                return new BuiltinFunction(args -> instance.reload());
            }
            if ("to_object".equals(member)) {
                return new BuiltinFunction(args -> instance.toDocumentMap());
            }
            if ("assign".equals(member)) {
                return new BuiltinFunction(args -> {
                    Map<String, Object> patch = args.isEmpty() || !(args.get(0) instanceof Map<?, ?>)
                            ? Collections.emptyMap()
                            : (Map<String, Object>) args.get(0);
                    return instance.assign(patch);
                });
            }
            if ("set".equals(member)) {
                return new BuiltinFunction(args -> {
                    if (args.size() < 2) {
                        throw new RuntimeException("instance.set expects key and value");
                    }
                    return instance.set(String.valueOf(args.get(0)), args.get(1));
                });
            }
            if ("get".equals(member)) {
                return new BuiltinFunction(args -> {
                    if (args.isEmpty()) {
                        throw new RuntimeException("instance.get expects key");
                    }
                    Object fallback = args.size() > 1 ? args.get(1) : null;
                    return instance.get(String.valueOf(args.get(0)), fallback);
                });
            }
            if ("clone".equals(member)) {
                return new BuiltinFunction(args -> instance.cloneInstance());
            }
            if ("validate".equals(member)) {
                return new BuiltinFunction(args -> instance.validate());
            }
            if ("props_from_schema".equals(member)) {
                return new BuiltinFunction(args -> instance.propsFromSchema());
            }
            if ("class_name".equals(member)) {
                return instance.className();
            }
            if ("id".equals(member)) {
                return instance.id();
            }
            if ("is_persisted".equals(member)) {
                return instance.isPersisted();
            }
            Object field = instance.getField(member);
            if (field != null || instance.hasField(member)) {
                return field;
            }
            UserFunction method = clazz.getInstanceMethod(member);
            if (method != null) {
                return new BuiltinFunction(args -> clazz.invokeInstanceMethod(instance, method, member, args));
            }
        }

        if (object instanceof VersaEnumValue) {
            VersaEnumValue enumValue = (VersaEnumValue) object;
            if ("name".equals(member) || "enum_name".equals(member)) {
                return enumValue.getName();
            }
            if ("members".equals(member)) {
                return new BuiltinFunction(args -> new ArrayList<>(enumValue.members()));
            }
            if ("names".equals(member)) {
                return new BuiltinFunction(args -> enumValue.names());
            }
            if ("values".equals(member) || "raw_values".equals(member)) {
                return new BuiltinFunction(args -> enumValue.values());
            }
            if ("members_map".equals(member) || "as_map".equals(member)) {
                return new BuiltinFunction(args -> enumValue.asMap());
            }
            if (enumValue.hasMember(member)) {
                return enumValue.getMember(member);
            }
            throw new RuntimeException("Enum member not found: " + enumValue.getName() + "." + member);
        }

        if (object instanceof VersaEnumMemberValue) {
            VersaEnumMemberValue enumMember = (VersaEnumMemberValue) object;
            if ("name".equals(member)) {
                return enumMember.getName();
            }
            if ("enum".equals(member)) {
                return enumMember.getOwner();
            }
            if ("enum_name".equals(member) || "owner_name".equals(member)) {
                return enumMember.getEnumName();
            }
            if ("value".equals(member) || "raw_value".equals(member)) {
                return enumMember.getValue();
            }
            if ("ordinal".equals(member) || "index".equals(member)) {
                return enumMember.getOrdinal();
            }
            throw new RuntimeException("Enum member field not found: " + enumMember + "." + member);
        }

        if (object instanceof Map) {
            Map<Object, Object> map = (Map<Object, Object>) object;
            String markerType = verun.runtime.modules.TimeDate.versaType(map);
            if ("timezone".equals(markerType)) {
                if ("human".equals(member) || "human_readable".equals(member)) {
                    return new BuiltinFunction(args -> verun.runtime.modules.TimeDate.timezoneHumanReadable(map));
                }
                if ("isoformat".equals(member)) {
                    return new BuiltinFunction(args -> verun.runtime.modules.TimeDate.timezoneIsoformat(map));
                }
            }
            if ("keys".equals(member)) {
                return new BuiltinFunction(args -> new java.util.ArrayList<>(map.keySet()));
            } else if ("values".equals(member)) {
                return new BuiltinFunction(args -> new java.util.ArrayList<>(map.values()));
            } else if ("items".equals(member)) {
                return new BuiltinFunction(args -> {
                    List<Object> entries = new ArrayList<>();
                    for (Map.Entry<Object, Object> e : map.entrySet()) {
                        entries.add(new EntryValue(e.getKey(), e.getValue()));
                    }
                    return entries;
                });
            } else if ("update".equals(member)) {
                return new BuiltinFunction(args -> {
                    if (!args.isEmpty() && args.get(0) instanceof Map) {
                        map.putAll((Map<?, ?>) args.get(0));
                    }
                    return null;
                });
            } else if ("pop".equals(member)) {
                return new BuiltinFunction(args -> args.isEmpty() ? null : map.remove(args.get(0)));
            } else if ("clear".equals(member)) {
                return new BuiltinFunction(args -> {
                    map.clear();
                    return null;
                });
            }
            return map.get(member);
        } else if (object instanceof EntryValue) {
            EntryValue entry = (EntryValue) object;
            if ("key".equals(member)) {
                return new BuiltinFunction(args -> entry.key());
            }
            if ("value".equals(member)) {
                return new BuiltinFunction(args -> entry.value());
            }
            Object keyObj = entry.key();
            if (member.equals(String.valueOf(keyObj))) {
                return entry.value();
            }
            if ("k".equals(member)) {
                return entry.key();
            }
            if ("v".equals(member)) {
                return entry.value();
            }
            throw new RuntimeException("Member not found: " + member);
        } else if (object instanceof Set<?>) {
            @SuppressWarnings("unchecked")
            Set<Object> set = (Set<Object>) object;
            if ("add".equals(member)) {
                return new BuiltinFunction(args -> {
                    if (args.isEmpty()) {
                        throw new RuntimeException("set.add expects one value");
                    }
                    return set.add(args.get(0));
                });
            }
            if ("remove".equals(member)) {
                return new BuiltinFunction(args -> {
                    if (args.isEmpty()) {
                        throw new RuntimeException("set.remove expects one value");
                    }
                    return set.remove(args.get(0));
                });
            }
            if ("discard".equals(member)) {
                return new BuiltinFunction(args -> {
                    if (args.isEmpty()) {
                        return false;
                    }
                    return set.remove(args.get(0));
                });
            }
            if ("contains".equals(member) || "has".equals(member)) {
                return new BuiltinFunction(args -> !args.isEmpty() && set.contains(args.get(0)));
            }
            if ("clear".equals(member)) {
                return new BuiltinFunction(args -> {
                    set.clear();
                    return null;
                });
            }
            if ("size".equals(member) || "len".equals(member)) {
                return new BuiltinFunction(args -> set.size());
            }
            if ("to_list".equals(member) || "values".equals(member)) {
                return new BuiltinFunction(args -> new ArrayList<>(set));
            }
            if ("copy".equals(member)) {
                return new BuiltinFunction(args -> new LinkedHashSet<>(set));
            }
            if ("update".equals(member) || "union_update".equals(member)) {
                return new BuiltinFunction(args -> {
                    if (!args.isEmpty()) {
                        for (Object arg : args) {
                            set.addAll(asSet(arg));
                        }
                    }
                    return null;
                });
            }
            if ("union".equals(member)) {
                return new BuiltinFunction(args -> {
                    LinkedHashSet<Object> out = new LinkedHashSet<>(set);
                    for (Object arg : args) {
                        out.addAll(asSet(arg));
                    }
                    return out;
                });
            }
            if ("intersection".equals(member)) {
                return new BuiltinFunction(args -> {
                    LinkedHashSet<Object> out = new LinkedHashSet<>(set);
                    for (Object arg : args) {
                        out.retainAll(asSet(arg));
                    }
                    return out;
                });
            }
            if ("difference".equals(member)) {
                return new BuiltinFunction(args -> {
                    LinkedHashSet<Object> out = new LinkedHashSet<>(set);
                    for (Object arg : args) {
                        out.removeAll(asSet(arg));
                    }
                    return out;
                });
            }
            if ("symmetric_difference".equals(member)) {
                return new BuiltinFunction(args -> {
                    LinkedHashSet<Object> out = new LinkedHashSet<>(set);
                    for (Object arg : args) {
                        Set<Object> other = asSet(arg);
                        LinkedHashSet<Object> next = new LinkedHashSet<>(out);
                        next.addAll(other);
                        Set<Object> common = new HashSet<>(out);
                        common.retainAll(other);
                        next.removeAll(common);
                        out = next;
                    }
                    return out;
                });
            }
            if ("is_subset".equals(member) || "issubset".equals(member)) {
                return new BuiltinFunction(args -> {
                    if (args.isEmpty()) {
                        throw new RuntimeException("set.is_subset expects one iterable");
                    }
                    return asSet(args.get(0)).containsAll(set);
                });
            }
            if ("is_superset".equals(member) || "issuperset".equals(member)) {
                return new BuiltinFunction(args -> {
                    if (args.isEmpty()) {
                        throw new RuntimeException("set.is_superset expects one iterable");
                    }
                    return set.containsAll(asSet(args.get(0)));
                });
            }
            if ("equals".equals(member)) {
                return new BuiltinFunction(args -> !args.isEmpty() && set.equals(asSet(args.get(0))));
            }
            if ("pop".equals(member)) {
                return new BuiltinFunction(args -> {
                    if (set.isEmpty()) {
                        return null;
                    }
                    Object first = set.iterator().next();
                    set.remove(first);
                    return first;
                });
            }
            throw new RuntimeException("Member not found: " + member);
        } else {
            try {
                Field field = object.getClass().getDeclaredField(member);
                field.setAccessible(true);
                return field.get(object);
            } catch (Exception e) {
                if (member.equals("add") || member.equals("remove") || member.equals("remove_all")
                        || member.equals("all_indexes") || member.equals("clear") ||
                        member.equals("sort") || member.equals("reverse") || member.equals("insert") ||
                        member.equals("pop") || member.equals("index") || member.equals("count") ||
                        member.equals("size") || member.equals("get") || member.equals("join") ||
                        member.equals("contains") || member.equals("swap")) {
                    if (!(object instanceof List<?>)) {
                        throw new RuntimeException("Member not found: " + member);
                    }
                    List<Object> list = (List<Object>) object;
                    if (member.equals("add")) {
                        return new BuiltinFunction(args -> {
                            list.add(args.get(0));
                            return null;
                        });
                    } else if (member.equals("remove")) {
                        return new BuiltinFunction(args -> {
                            return list.remove(args.get(0));
                        });
                    } else if (member.equals("remove_all")) {
                        return new BuiltinFunction(args -> {
                            if (args.isEmpty()) {
                                throw new RuntimeException("remove_all expects one argument");
                            }
                            Object target = args.get(0);
                            int removed = 0;
                            for (int i = list.size() - 1; i >= 0; i--) {
                                if (java.util.Objects.equals(list.get(i), target)) {
                                    list.remove(i);
                                    removed++;
                                }
                            }
                            return removed;
                        });
                    } else if (member.equals("clear")) {
                        return new BuiltinFunction(args -> {
                            list.clear();
                            return null;
                        });
                    } else if (member.equals("sort")) {
                        return new BuiltinFunction(args -> {
                            list.sort(null);
                            return null;
                        });
                    } else if (member.equals("reverse")) {
                        return new BuiltinFunction(args -> {
                            Collections.reverse(list);
                            return null;
                        });
                    } else if (member.equals("insert")) {
                        return new BuiltinFunction(args -> {
                            if (args.size() < 2) {
                                throw new RuntimeException("insert expects value and index");
                            }
                            Object value = args.get(0);
                            int index = ((Number) args.get(1)).intValue();
                            list.add(index, value);
                            return null;
                        });
                    } else if (member.equals("pop")) {
                        return new BuiltinFunction(args -> {
                            if (args.isEmpty()) {
                                return list.remove(list.size() - 1);
                            } else {
                                int idx = ((Number) args.get(0)).intValue();
                                return list.remove(idx);
                            }
                        });
                    } else if (member.equals("index")) {
                        return new BuiltinFunction(args -> {
                            return list.indexOf(args.get(0));
                        });
                    } else if (member.equals("all_indexes")) {
                        return new BuiltinFunction(args -> {
                            if (args.isEmpty()) {
                                throw new RuntimeException("all_indexes expects one argument");
                            }
                            List<Integer> indexes = new ArrayList<>();
                            Object target = args.get(0);
                            for (int i = 0; i < list.size(); i++) {
                                if (java.util.Objects.equals(list.get(i), target)) {
                                    indexes.add(i);
                                }
                            }
                            return indexes;
                        });
                    } else if (member.equals("count")) {
                        return new BuiltinFunction(args -> {
                            return (int) list.stream().filter(obj -> obj.equals(args.get(0))).count();
                        });
                    } else if (member.equals("contains")) {
                        return new BuiltinFunction(args -> {
                            return list.contains(args.get(0));
                        });
                    } else if (member.equals("size")) {
                        return new BuiltinFunction(args -> list.size());
                    } else if (member.equals("get")) {
                        return new BuiltinFunction(args -> list.get(((Number) args.get(0)).intValue()));
                    } else if (member.equals("join")) {
                        return new BuiltinFunction(args -> {
                            String separator = args.isEmpty() ? "," : String.valueOf(args.get(0));
                            StringBuilder builder = new StringBuilder();
                            for (int i = 0; i < list.size(); i++) {
                                if (i > 0) {
                                    builder.append(separator);
                                }
                                builder.append(ValueFormatter.toDisplayString(list.get(i)));
                            }
                            return builder.toString();
                        });
                    } else if (member.equals("swap")) {
                        return new BuiltinFunction(args -> {
                            if (args.size() < 2) {
                                throw new RuntimeException("swap expects two indexes");
                            }
                            int i = ((Number) args.get(0)).intValue();
                            int j = ((Number) args.get(1)).intValue();
                            if (i < 0 || i >= list.size() || j < 0 || j >= list.size()) {
                                throw new RuntimeException("swap index out of bounds");
                            }
                            Object tmp = list.get(i);
                            list.set(i, list.get(j));
                            list.set(j, tmp);
                            return null;
                        });
                    }
                }
                throw new RuntimeException("Member not found: " + member);
            }
        }
    }

    private static Map<String, Object> getSchemaFromClass(Class<?> clazz) {
        try {
            return (Map<String, Object>) clazz.getField("schema").get(null);
        } catch (Exception e) {
            throw new RuntimeException("Failed to get schema from class: " + e.getMessage(), e);
        }
    }

    private static Object runVdbOperation(String operation, String collection, Supplier<Object> action) {
        try {
            Object raw = action.get();
            return normalizeVdbResponse(operation, collection, raw);
        } catch (Evaluator.VDBScriptDependencyException e) {
            throw e;
        } catch (Exception e) {
            return vdbError(operation, collection, "VDB operation failed", e.getMessage(), null);
        }
    }

    private static Map<String, String> coerceStringMap(Map<?, ?> raw) {
        Map<String, String> out = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : raw.entrySet()) {
            out.put(String.valueOf(entry.getKey()), entry.getValue() == null ? null : String.valueOf(entry.getValue()));
        }
        return out;
    }

    private static String extractVdbError(String result) {
        if (result == null || result.isBlank()) {
            return null;
        }
        Matcher matcher = JSON_ERROR_PATTERN.matcher(result);
        if (matcher.find()) {
            return matcher.group(1);
        }
        return null;
    }

    private static Object normalizeVdbResponse(String operation, String collection, Object raw) {
        Map<String, Object> extraMeta = new LinkedHashMap<>();
        if (raw instanceof String && ("update".equals(operation) || "delete".equals(operation))) {
            int affected = parseAffectedCount((String) raw);
            extraMeta.put("affected_count", affected);
            if (affected == 0) {
                return vdbResponse(false, "not_found", operation, collection,
                        "No matching documents found", null, String.valueOf(raw), extraMeta);
            }
            return vdbSuccess(operation, collection, "Operation completed", raw, extraMeta);
        }
        if (raw instanceof Boolean) {
            boolean ok = (Boolean) raw;
            if (!ok) {
                return vdbResponse(false, "not_found", operation, collection,
                        "Requested resource not found", raw, null, extraMeta);
            }
            return vdbSuccess(operation, collection, "Operation completed", raw, extraMeta);
        }
        if (raw instanceof List<?>) {
            extraMeta.put("count", ((List<?>) raw).size());
            return vdbSuccess(operation, collection, "Operation completed", raw, extraMeta);
        }
        return vdbSuccess(operation, collection, "Operation completed", raw, extraMeta);
    }

    private static int parseAffectedCount(String text) {
        Matcher matcher = AFFECTED_COUNT_PATTERN.matcher(String.valueOf(text));
        if (matcher.find()) {
            return Integer.parseInt(matcher.group(1));
        }
        return 0;
    }

    private static Map<String, Object> vdbSuccess(String operation, String collection, String message, Object data,
            Map<String, Object> extraMeta) {
        return vdbResponse(true, "success", operation, collection, message, data, null, extraMeta);
    }

    private static Map<String, Object> vdbError(String operation, String collection, String message, String error,
            Map<String, Object> extraMeta) {
        return vdbResponse(false, "error", operation, collection, message, null, error, extraMeta);
    }

    private static Map<String, Object> vdbResponse(boolean ok, String status, String operation, String collection,
            String message, Object data, String error, Map<String, Object> extraMeta) {
        Map<String, Object> response = new LinkedHashMap<>();
        String errorType = ok ? null : inferVdbErrorType(operation, status, message, error);
        response.put("ok", ok);
        response.put("status", status);
        response.put("operation", operation);
        response.put("message", message);
        response.put("data", toVersaValue(data));
        response.put("error", error);
        response.put("error_type", errorType);
        response.put("exception_type", errorType);

        Map<String, Object> context = new LinkedHashMap<>();
        context.put("domain", VDB.getCurrentDomain());
        context.put("database", VDB.getCurrentDB());
        if (collection != null && !collection.isEmpty()) {
            context.put("collection", collection);
        }
        context.put("timestamp", System.currentTimeMillis());
        if (extraMeta != null && !extraMeta.isEmpty()) {
            context.putAll(extraMeta);
        }
        response.put("context", context);
        return response;
    }

    private static String inferVdbErrorType(String operation, String status, String message, String error) {
        String text = String.valueOf(error != null ? error : message).toLowerCase(Locale.ROOT);
        if (text.contains("not authenticated")) {
            return VdbExceptionTypes.NOT_AUTHENTICATED;
        }
        if ("auth".equals(operation) || text.contains("authentication") || text.contains("wrong password")
                || text.contains("unknown vdb user") || text.contains("no vdb users configured")) {
            return VdbExceptionTypes.AUTH;
        }
        if ("not_found".equals(status) || text.contains("not found") || text.contains("does not exist")) {
            return VdbExceptionTypes.NOT_FOUND;
        }
        if (text.contains("permission denied")) {
            return VdbExceptionTypes.PERMISSION;
        }
        if (text.contains("invalid") || text.contains("expects")) {
            return VdbExceptionTypes.VALIDATION;
        }
        return VdbExceptionTypes.OPERATION;
    }

    private static long parseTimeMillis(Object raw, long defaultValue) {
        if (raw == null) {
            return defaultValue;
        }
        if (raw instanceof Number) {
            long value = ((Number) raw).longValue();
            if (value < 1_000_000_000_000L) {
                return value * 1000L;
            }
            return value;
        }
        String text = String.valueOf(raw).trim();
        if (text.isEmpty()) {
            return defaultValue;
        }
        try {
            long value = Long.parseLong(text);
            if (value < 1_000_000_000_000L) {
                return value * 1000L;
            }
            return value;
        } catch (NumberFormatException ignored) {
            return defaultValue;
        }
    }

    private static Object toVersaValue(Object value) {
        if (value instanceof Map<?, ?>) {
            Map<String, Object> converted = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : ((Map<?, ?>) value).entrySet()) {
                converted.put(String.valueOf(entry.getKey()), toVersaValue(entry.getValue()));
            }
            return converted;
        }
        if (value instanceof List<?>) {
            List<Object> converted = new ArrayList<>();
            for (Object item : (List<?>) value) {
                converted.add(toVersaValue(item));
            }
            return converted;
        }
        return value;
    }

    private static Set<Object> asSet(Object value) {
        LinkedHashSet<Object> out = new LinkedHashSet<>();
        if (value == null) {
            return out;
        }
        if (value instanceof Set<?>) {
            out.addAll((Set<?>) value);
            return out;
        }
        if (value instanceof List<?>) {
            out.addAll((List<?>) value);
            return out;
        }
        out.add(value);
        return out;
    }
}
