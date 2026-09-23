// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import verun.runtime.ast.*;
import verun.runtime.Logger;
import verun.runtime.lexer.Lexer;
import verun.runtime.lexer.Token;
import verun.runtime.lexer.TokenType;
import verun.runtime.modules.CustomModuleRegistry;
import verun.runtime.modules.Email;
import verun.runtime.modules.Filer;
import verun.runtime.modules.HTTP;
import verun.runtime.modules.JsonXml;
import verun.runtime.modules.TimeDate;
import verun.runtime.modules.Crypto;
import verun.runtime.modules.Jwt;
import verun.runtime.modules.RandomModule;
import verun.runtime.parser.Parser;
import verun.vdb.VDB;


import java.util.*;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.function.Function;
import java.util.function.Supplier;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class Evaluator {
    private static final int DEFAULT_VDB_SCRIPT_RECURSION_LIMIT = 8;
    private static final ThreadLocal<Deque<String>> VDB_SCRIPT_EXECUTION_CHAIN = ThreadLocal.withInitial(ArrayDeque::new);
    private EvaluationContext context;
    private Map<String, Object> environment;
    private boolean insideLoop;
    private boolean loggingEnabled;
    private int callDepth = 0;
    private static final Scanner inputScanner = new Scanner(System.in);
    private static final Set<String> CORE_MODULES = new HashSet<>(Arrays.asList(
            "vdb", "http", "email", "json_xml", "filer", "crypto", "jwt", "time", "datetime", "random"));
    private static final List<String> VDB_EXPORTS = Arrays.asList(
            "create", "auth", "config", "set", "collection", "insert", "find", "update", "delete",
            "list_collections", "list_databases", "drop", "create_index", "drop_index", "list_indexes", "rebuild_indexes",
            "index_advisor_status", "index_advisor_apply", "index_advisor_policy", "index_advisor_remove_auto_indexes",
            "define", "use", "tumi", "save_script", "load_script",
            "delete_script", "execute_script", "aggregate", "begin_transaction", "commit_transaction",
            "abort_transaction", "list_scripts", "list_domains", "schedule_job", "list_jobs", "cancel_job", "model");
    private static final Pattern IMPORT_LINE_PATTERN = Pattern.compile(
            "^\\s*([A-Za-z_][A-Za-z0-9_]*)\\s+import\\s+(\\*|\\{[^;]*\\})\\s*;\\s*$");
    private static final Pattern NAMESPACE_IMPORT_LINE_PATTERN = Pattern.compile(
            "^\\s*import\\s+([A-Za-z_][A-Za-z0-9_]*)\\s*;\\s*$");
    private Logger logger;
    private Evaluator outerEvaluator;

    public Evaluator(boolean loggingEnabled, List<Token> tokens, String sourceText) {
        this.loggingEnabled = loggingEnabled;
        this.logger = new Logger();
        this.context = new EvaluationContext(tokens, sourceText);
        this.environment = new HashMap<>();
        this.insideLoop = false;
        this.outerEvaluator = null;
        loadBuiltins(sourceText);
    }

    public Evaluator(List<Token> tokens, String sourceText) {
        this(false, tokens, sourceText);
    }

    public Evaluator(boolean loggingEnabled) {
        this.loggingEnabled = loggingEnabled;
        this.logger = new Logger();
        this.context = new EvaluationContext();
        this.environment = new HashMap<>();
        this.insideLoop = false;
        this.outerEvaluator = null;
        loadBuiltins(null);
    }

    public Evaluator(Map<String, Object> env) {
        this.environment = env;
        this.insideLoop = false;
        this.loggingEnabled = false;
        this.outerEvaluator = null;
        loadBuiltins(null);
    }

    public Evaluator(EvaluationContext context) {
        this.context = context;
        this.loggingEnabled = false;
        this.environment = context.getEnvironment(); // Use environment from context
        this.insideLoop = false;
        this.outerEvaluator = null;
        loadBuiltins(context != null ? context.sourceText : null);
    }

    public Evaluator(EvaluationContext context, Evaluator outerEvaluator) {
        this.context = context;
        this.outerEvaluator = outerEvaluator;
        this.loggingEnabled = false;
        this.environment = context.getEnvironment(); // Use environment from context
        this.insideLoop = false;
        loadBuiltins(context != null ? context.sourceText : null);
    }

    public EvaluationContext getCurrentContext() {
        return context;
    }

    public Map<String, Object> getEnvironment() {
        return environment;
    }

    public static final class VDBScriptDependencyException extends EvaluationException {
        public VDBScriptDependencyException(String type, String message) {
            super(type, message);
        }
    }

    public static int currentVdbScriptRecursionLimit() {
        return resolvePositiveInt(
                System.getProperty("vi.vdb.script.maxDepth"),
                System.getProperty("vi.vdb.script.max-depth"),
                System.getenv("VI_VDB_SCRIPT_MAX_DEPTH"),
                DEFAULT_VDB_SCRIPT_RECURSION_LIMIT);
    }

    public static <T> T executeVdbScript(String scriptName, Supplier<T> action) {
        String normalized = normalizeVdbScriptName(scriptName);
        Deque<String> chain = VDB_SCRIPT_EXECUTION_CHAIN.get();
        List<String> attemptedChain = new ArrayList<>(chain);
        attemptedChain.add(normalized);

        if (chain.contains(normalized)) {
            throw new VDBScriptDependencyException(
                    "DependencyCycleError",
                    "Circular VDB script dependency detected: " + String.join(" -> ", attemptedChain));
        }

        int maxDepth = currentVdbScriptRecursionLimit();
        if (attemptedChain.size() > maxDepth) {
            throw new VDBScriptDependencyException(
                    "DependencyDepthError",
                    "VDB script recursion limit exceeded at depth " + attemptedChain.size()
                            + " (max " + maxDepth + "): " + String.join(" -> ", attemptedChain));
        }

        chain.addLast(normalized);
        try {
            return action.get();
        } finally {
            if (!chain.isEmpty() && normalized.equals(chain.peekLast())) {
                chain.removeLast();
            } else {
                chain.removeLastOccurrence(normalized);
            }
            if (chain.isEmpty()) {
                VDB_SCRIPT_EXECUTION_CHAIN.remove();
            }
        }
    }

    private static String normalizeVdbScriptName(String scriptName) {
        String normalized = String.valueOf(scriptName == null ? "" : scriptName).trim();
        return normalized.isEmpty() ? "<unnamed_vdb_script>" : normalized;
    }

    private static int resolvePositiveInt(String primary, String secondary, String tertiary, int fallback) {
        for (String candidate : Arrays.asList(primary, secondary, tertiary)) {
            if (candidate == null) {
                continue;
            }
            String normalized = candidate.trim();
            if (normalized.isEmpty()) {
                continue;
            }
            try {
                int parsed = Integer.parseInt(normalized);
                if (parsed > 0) {
                    return parsed;
                }
            } catch (NumberFormatException ignored) {
                // Ignore invalid overrides and keep searching for a valid positive value.
            }
        }
        return fallback;
    }

    public static String readInputLine() {
        synchronized (inputScanner) {
            try {
                if (inputScanner.hasNextLine()) {
                    return inputScanner.nextLine();
                }
            } catch (Exception ignored) {
                return "";
            }
            return "";
        }
    }

    public static Scanner sharedInputScanner() {
        return inputScanner;
    }

    private boolean isUnsetBinding(String name) {
        if (name == null || name.trim().isEmpty()) {
            return true;
        }
        String normalized = name.trim();
        if (!hasBinding(normalized)) {
            return true;
        }
        Object value = environment.containsKey(normalized) ? environment.get(normalized) : null;
        if (!environment.containsKey(normalized) && outerEvaluator != null) {
            return outerEvaluator.isUnsetBinding(normalized);
        }
        if (value instanceof MutableValue) {
            value = ((MutableValue) value).value;
        }
        return value instanceof UnsetValue;
    }

    private void loadBuiltins(String sourceText) {
        environment.put("null", null);
        environment.put("env", new LinkedHashMap<>(System.getenv()));

        environment.put("print", new BuiltinFunction(args -> {
            if (args.isEmpty()) {
                throw new RuntimeException("print requires at least one argument");
            }
            for (Object arg : args) {
                System.out.print(ValueFormatter.toDisplayString(arg));
            }
            System.out.println();
            return null;
        }));

        environment.put("input", new BuiltinFunction(args -> {
            if (!args.isEmpty()) {
                System.out.print(ValueFormatter.toDisplayString(args.get(0)));
            }
            return readInputLine();
        }));

        environment.put("exit", new BuiltinFunction(args -> {
            if (args.size() > 1) {
                throw new RuntimeException("exit expects zero or one argument");
            }
            int exitCode = args.isEmpty() ? 0 : castToInt(args.get(0));
            throw new ExitException(exitCode);
        }));

        environment.put("AsFloat", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("AsFloat expects one argument");
            }
            return (float) castToFloat(args.get(0));
        }));

        environment.put("int", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("int expects one argument");
            }
            return castToInt(args.get(0));
        }));

        environment.put("float", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("float expects one argument");
            }
            return castToFloat(args.get(0));
        }));

        environment.put("str", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("str expects one argument");
            }
            return ValueFormatter.toDisplayString(args.get(0));
        }));

        environment.put("bool", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("bool expects one argument");
            }
            return castToBool(args.get(0));
        }));

        environment.put("range", new BuiltinFunction(args -> {
            if (args.size() < 1 || args.size() > 3) {
                throw new RuntimeException("range expects one, two, or three arguments");
            }
            int start = 0;
            int end;
            int step;
            if (args.size() == 1) {
                end = castToInt(args.get(0));
                step = 1;
            } else {
                start = castToInt(args.get(0));
                end = castToInt(args.get(1));
                if (args.size() == 3) {
                    step = castToInt(args.get(2));
                    if (step == 0) {
                        throw new RuntimeException("range step cannot be zero");
                    }
                } else {
                    step = start <= end ? 1 : -1;
                }
            }
            List<Integer> result = new ArrayList<>();
            if (step > 0) {
                for (long i = start; i < end; i += step) {
                    result.add((int) i);
                }
            } else {
                for (long i = start; i > end; i += step) {
                    result.add((int) i);
                }
            }
            return result;
        }));

        environment.put("leng", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("leng expects one argument");
            }
            Object target = args.get(0);
            if (target instanceof List) {
                return ((List<?>) target).size();
            } else if (target instanceof String) {
                return ((String) target).length();
            } else if (target instanceof Map) {
                return ((Map<?, ?>) target).size();
            } else if (target instanceof java.util.Set) {
                return ((java.util.Set<?>) target).size();
            }
            throw new RuntimeException("Unsupported type for leng");
        }));
        // Keep the historical `leng` spelling while exposing the conventional
        // general-purpose `len` builtin for new Versa programs.
        environment.put("len", environment.get("leng"));

        environment.put("join", new BuiltinFunction(args -> {
            if (args.size() != 2) {
                throw new RuntimeException("join expects two arguments");
            }
            String separator = args.get(0).toString();
            List<?> values = iterableValues(args.get(1), "join");
            return String.join(separator, values.stream().map(ValueFormatter::toDisplayString).toArray(String[]::new));
        }));
        environment.put("set", new BuiltinFunction(args -> {
            java.util.LinkedHashSet<Object> out = new java.util.LinkedHashSet<>();
            if (args.isEmpty()) {
                return out;
            }
            Object first = args.get(0);
            if (first instanceof java.util.Set<?>) {
                out.addAll((java.util.Set<?>) first);
                return out;
            }
            if (first instanceof List<?>) {
                out.addAll((List<?>) first);
                return out;
            }
            out.addAll(args);
            return out;
        }));

        environment.put("map", new BuiltinFunction(args -> {
            if (args.size() != 2) {
                throw new RuntimeException("map expects two arguments");
            }
            if (!(args.get(0) instanceof Callable)) {
                throw new RuntimeException("map expects a callable mapper");
            }
            Callable lambda = (Callable) args.get(0);
            List<Object> result = new ArrayList<>();
            for (Object item : iterableValues(args.get(1), "map")) {
                result.add(lambda.call(Collections.singletonList(item)));
            }
            return result;
        }));

        environment.put("filter", new BuiltinFunction(args -> {
            if (args.size() != 2) {
                throw new RuntimeException("filter expects two arguments");
            }
            if (!(args.get(0) instanceof Callable)) {
                throw new RuntimeException("filter expects a callable predicate");
            }
            Callable predicate = (Callable) args.get(0);
            List<Object> result = new ArrayList<>();
            for (Object item : iterableValues(args.get(1), "filter")) {
                if (castToBool(predicate.call(Collections.singletonList(item)))) {
                    result.add(item);
                }
            }
            return result;
        }));

        environment.put("any", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("any expects one iterable");
            }
            for (Object item : iterableValues(args.get(0), "any")) {
                if (isTruthy(item)) return true;
            }
            return false;
        }));

        environment.put("all", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("all expects one iterable");
            }
            for (Object item : iterableValues(args.get(0), "all")) {
                if (!isTruthy(item)) return false;
            }
            return true;
        }));

        environment.put("sum", new BuiltinFunction(args -> {
            if (args.size() < 1 || args.size() > 2) {
                throw new RuntimeException("sum expects an iterable and an optional initial value");
            }
            List<?> values = iterableValues(args.get(0), "sum");
            Object initial = args.size() == 2 ? args.get(1) : 0;
            if (!(initial instanceof Number)) {
                throw new RuntimeException("sum initial value must be numeric");
            }
            boolean integral = initial instanceof Integer;
            double total = ((Number) initial).doubleValue();
            for (Object item : values) {
                if (!(item instanceof Number)) {
                    throw new RuntimeException("sum expects an iterable of numbers");
                }
                integral &= item instanceof Integer;
                total += ((Number) item).doubleValue();
            }
            if (integral && total >= Integer.MIN_VALUE && total <= Integer.MAX_VALUE && total == Math.rint(total)) {
                return (int) total;
            }
            return total;
        }));

        environment.put("reduce", new BuiltinFunction(args -> {
            if (args.size() < 2 || args.size() > 3) {
                throw new RuntimeException("reduce expects a callable, an iterable, and an optional initial value");
            }
            if (!(args.get(0) instanceof Callable)) {
                throw new RuntimeException("reduce expects a callable reducer");
            }
            Callable reducer = (Callable) args.get(0);
            List<?> values = iterableValues(args.get(1), "reduce");
            if (values.isEmpty() && args.size() < 3) {
                throw new RuntimeException("reduce of empty iterable requires an initial value");
            }
            int index = 0;
            Object accumulator;
            if (args.size() == 3) {
                accumulator = args.get(2);
            } else {
                accumulator = values.get(index++);
            }
            for (; index < values.size(); index++) {
                accumulator = reducer.call(Arrays.asList(accumulator, values.get(index)));
            }
            return accumulator;
        }));

        environment.put("json", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("json expects one argument");
            }
            Object value = args.get(0);
            if (value instanceof String) {
                return JsonXml.parseJson((String) value);
            }
            if (isJsonValue(value)) {
                return value;
            }
            throw new RuntimeException("json expects a JSON string or json value");
        }));
        environment.put("xml", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("xml expects one argument");
            }
            Object value = args.get(0);
            if (value instanceof String) {
                return JsonXml.parseXml((String) value);
            }
            if (isXmlValue(value)) {
                return value;
            }
            throw new RuntimeException("xml expects an XML string or xml value");
        }));
        loadOptionalModules(sourceText);
        environment.put("type", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("type expects one argument");
            }
            return valueType(args.get(0));
        }));
        environment.put("is_type", new BuiltinFunction(args -> {
            if (args.size() != 2) {
                throw new RuntimeException("is_type expects value and type name");
            }
            return isType(args.get(0), String.valueOf(args.get(1)));
        }));
        environment.put("unset", UnsetValue.INSTANCE);
    }

    private void loadOptionalModules(String sourceText) {
        Set<String> importedModules = sourceText == null ? new HashSet<>(CORE_MODULES) : parseTopLevelImports(sourceText);
        if (importedModules.contains("vdb")) {
            environment.put("vdb", new VDBNative());
        }
        if (importedModules.contains("http")) {
            environment.put("http", buildHttpModule());
        }
        if (importedModules.contains("email")) {
            environment.put("email", buildEmailModule());
        }
        if (importedModules.contains("json_xml")) {
            environment.put("json_xml", buildJsonXmlModule());
        }
        if (importedModules.contains("filer")) {
            environment.put("filer", buildFilerModule());
        }
        if (importedModules.contains("crypto")) {
            environment.put("crypto", buildCryptoModule());
        }
        if (importedModules.contains("jwt")) {
            environment.put("jwt", buildJwtModule());
        }
        if (importedModules.contains("time")) {
            environment.put("time", buildTimeModule());
        }
        if (importedModules.contains("datetime")) {
            environment.put("datetime", buildDatetimeModule());
        }
        if (importedModules.contains("random")) {
            environment.put("random", buildRandomModule());
        }
        for (String moduleName : importedModules) {
            if (CORE_MODULES.contains(moduleName)) {
                continue;
            }
            environment.put(moduleName, loadCustomModule(moduleName));
        }
        if (sourceText != null && !sourceText.isEmpty()) {
            applyModuleImports(sourceText);
        }
    }

    private Set<String> allAvailableModuleNames() {
        Set<String> modules = new HashSet<>(CORE_MODULES);
        modules.addAll(CustomModuleRegistry.listModuleNames());
        return modules;
    }

    private Set<String> parseTopLevelImports(String sourceText) {
        Set<String> imported = new HashSet<>();
        if (sourceText == null || sourceText.isEmpty()) {
            return imported;
        }
        String[] lines = sourceText.split("\\R", -1);
        boolean seenCode = false;
        for (int i = 0; i < lines.length; i++) {
            String raw = lines[i];
            String trimmed = raw == null ? "" : raw.trim();
            if (trimmed.isEmpty() || trimmed.startsWith("//") || trimmed.startsWith("#")) {
                continue;
            }
            Matcher matcher = IMPORT_LINE_PATTERN.matcher(raw);
            if (matcher.find()) {
                String module = matcher.group(1).toLowerCase(Locale.ROOT);
                if (allAvailableModuleNames().contains(module)) {
                    if (seenCode) {
                        throw new EvaluationException(
                                "ImportError",
                                "Module imports must appear at the top of the file/script: " + module,
                                i + 1,
                                Math.max(1, raw.indexOf(module) + 1),
                                raw);
                    }
                    imported.add(module);
                    continue;
                }
            }
            Matcher namespaceMatcher = NAMESPACE_IMPORT_LINE_PATTERN.matcher(raw);
            if (namespaceMatcher.find()) {
                String module = namespaceMatcher.group(1).toLowerCase(Locale.ROOT);
                if (allAvailableModuleNames().contains(module)) {
                    if (seenCode) {
                        throw new EvaluationException(
                                "ImportError",
                                "Module imports must appear at the top of the file/script: " + module,
                                i + 1,
                                Math.max(1, raw.indexOf(module) + 1),
                                raw);
                    }
                    imported.add(module);
                    continue;
                }
            }
            seenCode = true;
        }
        return imported;
    }

    private void applyModuleImports(String sourceText) {
        String[] lines = sourceText.split("\\R", -1);
        for (String raw : lines) {
            String trimmed = raw == null ? "" : raw.trim();
            if (trimmed.isEmpty() || trimmed.startsWith("//") || trimmed.startsWith("#")) {
                continue;
            }
            Matcher matcher = IMPORT_LINE_PATTERN.matcher(raw);
            if (!matcher.find()) {
                continue;
            }
            String moduleName = matcher.group(1);
            String spec = matcher.group(2).trim();
            if (!allAvailableModuleNames().contains(moduleName.toLowerCase(Locale.ROOT))) {
                continue;
            }
            Object moduleValue = environment.get(moduleName);
            Map<String, Object> module = asExportMap(moduleName, moduleValue);
            if (module == null || module.isEmpty()) {
                continue;
            }
            if ("*".equals(spec)) {
                for (Map.Entry<String, Object> e : module.entrySet()) {
                    String exportName = e.getKey();
                    // Keep module namespace binding intact for patterns like:
                    // random import *; random.randint(...)
                    if (moduleName.equals(exportName)) {
                        continue;
                    }
                    environment.put(exportName, e.getValue());
                }
                continue;
            }
            if (!spec.startsWith("{") || !spec.endsWith("}")) {
                continue;
            }
            String body = spec.substring(1, spec.length() - 1).trim();
            if (body.isEmpty()) {
                continue;
            }
            for (String part : body.split(",")) {
                String name = part == null ? "" : part.trim();
                if (name.isEmpty()) {
                    continue;
                }
                if (!module.containsKey(name)) {
                    throw new RuntimeException("Module '" + moduleName + "' does not export '" + name + "'");
                }
                environment.put(name, module.get(name));
            }
        }
    }

    private Map<String, Object> asExportMap(String moduleName, Object moduleValue) {
        if (moduleValue instanceof Map<?, ?>) {
            @SuppressWarnings("unchecked")
            Map<String, Object> cast = (Map<String, Object>) moduleValue;
            return cast;
        }
        if ("vdb".equals(moduleName) && moduleValue instanceof VDBNative) {
            Map<String, Object> exports = new HashMap<>();
            for (String name : VDB_EXPORTS) {
                exports.put(name, new BuiltinFunction(args -> {
                    Object resolved = resolveModuleMember(moduleValue, name);
                    if (!(resolved instanceof Callable)) {
                        return resolved;
                    }
                    return ((Callable) resolved).call(args);
                }));
            }
            return exports;
        }
        return null;
    }

    private Map<String, Object> loadCustomModule(String moduleName) {
        String normalizedName = String.valueOf(moduleName).toLowerCase(Locale.ROOT);
        if (CustomModuleRegistry.isLoading(normalizedName)) {
            throw new RuntimeException("Circular custom module import: " + normalizedName + " (" + CustomModuleRegistry.currentLoadChain() + ")");
        }
        String currentDomain = resolveCurrentModuleDomain();
        CustomModuleRegistry.CustomModule module = CustomModuleRegistry.resolveModule(normalizedName, currentDomain);
        if (module == null) {
            if (!CustomModuleRegistry.isKnownCustomModule(normalizedName)) {
                throw new RuntimeException("Unknown module: " + normalizedName);
            }
            if (currentDomain.isEmpty()) {
                throw new RuntimeException("Domain-scoped module '" + normalizedName + "' requires an active domain context");
            }
            throw new RuntimeException("Module '" + normalizedName + "' is not assigned to domain '" + currentDomain + "'");
        }
        if (module.source == null || module.source.trim().isEmpty()) {
            return new LinkedHashMap<>();
        }

        CustomModuleRegistry.pushLoading(normalizedName);
        try {
            Lexer lexer = new Lexer(module.source);
            List<Token> tokens = lexer.tokenize();
            Parser parser = new Parser(tokens, module.source);
            Node ast = parser.parse();
            Evaluator nested = new Evaluator(this.loggingEnabled, tokens, module.source);
            nested.outerEvaluator = this;
            Set<String> initialKeys = new HashSet<>(nested.environment.keySet());
            Object outerService = get("service");
            Object outerAuth = get("auth");
            Object outerParams = get("params");
            nested.environment.put("service", outerService);
            nested.environment.put("auth", outerAuth);
            nested.environment.put("params", outerParams);
            nested.environment.put("module_config", mergeModuleConfig(module.name, module.configDefaults));
            nested.environment.put("module_meta", buildModuleMeta(module));
            initialKeys.add("service");
            initialKeys.add("auth");
            initialKeys.add("params");
            initialKeys.add("module_config");
            initialKeys.add("module_meta");
            nested.evaluate(ast);

            Map<String, Object> exports = new LinkedHashMap<>();
            for (Map.Entry<String, Object> entry : nested.environment.entrySet()) {
                String key = entry.getKey();
                if (initialKeys.contains(key) || key == null || key.startsWith("__")) {
                    continue;
                }
                Object value = entry.getValue();
                if (value instanceof MutableValue) {
                    exports.put(key, ((MutableValue) value).value);
                } else if (value instanceof ConstantValue) {
                    exports.put(key, ((ConstantValue) value).value);
                } else {
                    exports.put(key, value);
                }
            }
            return exports;
        } finally {
            CustomModuleRegistry.popLoading(normalizedName);
        }
    }

    private Map<String, Object> buildModuleMeta(CustomModuleRegistry.CustomModule module) {
        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("name", module.name);
        meta.put("title", module.title);
        meta.put("description", module.description);
        meta.put("scope", module.scope);
        meta.put("assignedDomains", new ArrayList<>(module.assignedDomains));
        meta.put("ownerDomains", new ArrayList<>(module.ownerDomains));
        return meta;
    }

    private Map<String, Object> mergeModuleConfig(String moduleName, Map<String, Object> defaults) {
        Map<String, Object> merged = new LinkedHashMap<>();
        if (defaults != null) {
            merged.putAll(defaults);
        }
        Object serviceObject = get("service");
        if (!(serviceObject instanceof Map<?, ?>)) {
            return merged;
        }
        Object rawModules = ((Map<?, ?>) serviceObject).get("modules");
        if (!(rawModules instanceof List<?>)) {
            return merged;
        }
        for (Object item : (List<?>) rawModules) {
            if (!(item instanceof Map<?, ?>)) {
                continue;
            }
            String itemName = String.valueOf(((Map<?, ?>) item).get("name") == null ? "" : ((Map<?, ?>) item).get("name")).trim().toLowerCase(Locale.ROOT);
            if (!moduleName.equals(itemName)) {
                continue;
            }
            Object rawConfig = ((Map<?, ?>) item).get("config");
            if (rawConfig instanceof Map<?, ?>) {
                for (Map.Entry<?, ?> entry : ((Map<?, ?>) rawConfig).entrySet()) {
                    merged.put(String.valueOf(entry.getKey()), entry.getValue());
                }
            }
            break;
        }
        return merged;
    }

    private String resolveCurrentModuleDomain() {
        String configured = System.getProperty("liwiro.versa.module.domain");
        if (configured == null || configured.trim().isEmpty()) {
            configured = System.getenv("LIWIRO_VI_MODULE_DOMAIN");
        }
        if (configured != null && !configured.trim().isEmpty()) {
            return configured.trim().toLowerCase(Locale.ROOT);
        }
        try {
            String vdbDomain = String.valueOf(VDB.getCurrentDomain() == null ? "" : VDB.getCurrentDomain()).trim();
            if (!vdbDomain.isEmpty()) {
                return vdbDomain.toLowerCase(Locale.ROOT);
            }
        } catch (Throwable ignored) {
        }
        return "";
    }

    private Object resolveModuleMember(Object moduleValue, String member) {
        String tempName = "__vi_module_import_tmp";
        Object previous = environment.put(tempName, moduleValue);
        try {
            return MemberAccessEvaluator.evaluateMemberAccess(
                    new MemberAccessNode(new IdentifierNode(tempName, 1, 1), member),
                    this);
        } finally {
            if (previous == null) {
                environment.remove(tempName);
            } else {
                environment.put(tempName, previous);
            }
        }
    }

    public Object evaluate(Node node) {
        try {
            if (node instanceof IntegerNode) {
                return ((IntegerNode) node).value;
            }

            else if (node instanceof BooleanNode) {
                return ((BooleanNode) node).value;
            }

            else if (node instanceof FloatNode) {
                return ((FloatNode) node).value;
            }

            else if (node instanceof NumberNode) {
                double value = ((NumberNode) node).value;
                return value % 1 == 0 ? (int) value : value;
            }

            else if (node instanceof ClassDeclarationNode) {
                return evaluateClassDeclaration((ClassDeclarationNode) node);
            }

            else if (node instanceof EnumDeclarationNode) {
                return evaluateEnumDeclaration((EnumDeclarationNode) node);
            }

            else if (node instanceof StringNode) {
                return ((StringNode) node).value;
            }

            else if (node instanceof IdentifierNode) {
                IdentifierNode idNode = (IdentifierNode) node;
                String name = idNode.name;
                if (environment.containsKey(name)) {
                    Object value = environment.get(name);
                    if (value instanceof MutableValue) {
                        return ((MutableValue) value).value;
                    }
                    if (value instanceof ConstantValue) {
                        return ((ConstantValue) value).value;
                    }
                    return value;
                }
                if (outerEvaluator != null) {
                    return outerEvaluator.get(name);
                }
                throw withLocation("Undefined variable: " + name, idNode.line, idNode.column);
            }

            else if (node instanceof TryCatchNode) {
                TryCatchNode tryNode = (TryCatchNode) node;
                Object result = null;
                RuntimeException pending = null;
                boolean trySucceeded = false;

                try {
                    try {
                        result = evaluate(tryNode.tryBlock);
                        trySucceeded = true;
                    } catch (ControlFlowSignal signal) {
                        throw signal;
                    } catch (RuntimeException e) {
                        if (tryNode.catchBlock != null) {
                            if (tryNode.errorVar != null && !tryNode.errorVar.isEmpty()) {
                                environment.put(tryNode.errorVar, ExceptionObject.from(e));
                            }
                            try {
                                result = evaluate(tryNode.catchBlock);
                            } catch (ControlFlowSignal signal) {
                                throw signal;
                            } catch (RuntimeException catchEx) {
                                pending = catchEx;
                            }
                        } else {
                            pending = e;
                        }
                    }

                    if (pending == null && trySucceeded && tryNode.elseBlock != null) {
                        result = evaluate(tryNode.elseBlock);
                    }
                } finally {
                    if (tryNode.completeBlock != null) {
                        evaluate(tryNode.completeBlock);
                    }
                }

                if (pending != null) {
                    throw pending;
                }
                return result;
            }

            else if (node instanceof ThrowStatementNode) {
                ThrowStatementNode throwNode = (ThrowStatementNode) node;
                Object value = evaluate(throwNode.expression);
                int throwLine = throwNode.getLine();
                int throwColumn = throwNode.getColumn();
                String throwSource = getSourceLine(throwLine);
                if (value instanceof ExceptionObject) {
                    ExceptionObject exObj = (ExceptionObject) value;
                    int line = exObj.line > 0 ? exObj.line : throwLine;
                    int column = exObj.column > 0 ? exObj.column : throwColumn;
                    String source = exObj.source_line != null && !exObj.source_line.isEmpty()
                            ? exObj.source_line
                            : throwSource;
                    throw new EvaluationException(exObj.type, exObj.message, line, column, source);
                }
                throw new EvaluationException(
                        "ThrownError",
                        ValueFormatter.toDisplayString(value),
                        throwLine,
                        throwColumn,
                        throwSource);
            }

            else if (node instanceof BinaryOperationNode) {
                BinaryOperationNode binOp = (BinaryOperationNode) node;
                if (binOp.operator.equals("=")) {
                    Object right = evaluate(binOp.right);
                    if (binOp.left instanceof IdentifierNode) {
                        String varName = ((IdentifierNode) binOp.left).name;
                        Object current = environment.get(varName);
                        if (current instanceof ConstantValue) {
                            throw new RuntimeException("Cannot assign to constant '" + varName + "'");
                        }
                        if (current instanceof MutableValue) {
                            MutableValue mutable = (MutableValue) current;
                            assertTypeCompatibility(right, mutable.declaredType, "Type mismatch for '" + varName + "'");
                            mutable.value = right;
                        } else {
                            environment.put(varName, new MutableValue(right));
                        }
                        return right;
                    } else if (binOp.left instanceof MemberAccessNode) {
                        MemberAccessNode memberAccess = (MemberAccessNode) binOp.left;
                        Object object = evaluate(memberAccess.object);
                        String member = memberAccess.member;

                        if (object instanceof Map) {
                            ((Map<String, Object>) object).put(member, right);
                        } else if (object instanceof VersaInstanceValue) {
                            ((VersaInstanceValue) object).setField(member, right);
                        } else if (object instanceof VersaClassValue) {
                            ((VersaClassValue) object).setStaticField(member, right);
                        } else {
                            throw new RuntimeException("Cannot assign to member of non-object");
                        }
                        return right;
                    } else if (binOp.left instanceof IndexAccessNode) {
                        IndexAccessNode indexAccess = (IndexAccessNode) binOp.left;
                        Object target = evaluate(indexAccess.getTarget());
                        if (indexAccess.isSlice()) {
                            assignSliceValue(target, indexAccess.getIndex(), indexAccess.getEndIndex(), indexAccess.getStep(), right);
                            return right;
                        }
                        Object index = resolveIndexKey(indexAccess, target);
                        if (target instanceof List<?>) {
                            if (!(index instanceof Number)) {
                                throw new RuntimeException("List index must be a number");
                            }
                            int idx = ((Number) index).intValue();
                            @SuppressWarnings("unchecked")
                            List<Object> list = (List<Object>) target;
                            if (idx < 0 || idx >= list.size()) {
                                throw new RuntimeException("Index " + idx + " out of bounds for length " + list.size());
                            }
                            list.set(idx, right);
                            return right;
                        }
                        if (target instanceof Map<?, ?>) {
                            @SuppressWarnings("unchecked")
                            Map<Object, Object> map = (Map<Object, Object>) target;
                            map.put(resolveMapKey(map, index), right);
                            return right;
                        }
                        throw new RuntimeException("Invalid indexed assignment target");
                    } else {
                        throw new RuntimeException("Invalid left-hand side in assignment");
                    }
                } else {
                    if ("&&".equals(binOp.operator)) {
                        Object left = evaluate(binOp.left);
                        if (!(left instanceof Boolean)) {
                            throw new RuntimeException("Operator '&&' requires boolean operands");
                        }
                        if (!((Boolean) left)) {
                            return false;
                        }
                        Object right = evaluate(binOp.right);
                        if (!(right instanceof Boolean)) {
                            throw new RuntimeException("Operator '&&' requires boolean operands");
                        }
                        return (Boolean) right;
                    }
                    if ("||".equals(binOp.operator)) {
                        Object left = evaluate(binOp.left);
                        if (!(left instanceof Boolean)) {
                            throw new RuntimeException("Operator '||' requires boolean operands");
                        }
                        if (((Boolean) left)) {
                            return true;
                        }
                        Object right = evaluate(binOp.right);
                        if (!(right instanceof Boolean)) {
                            throw new RuntimeException("Operator '||' requires boolean operands");
                        }
                        return (Boolean) right;
                    }
                    if ("??".equals(binOp.operator)) {
                        Object left = evaluate(binOp.left);
                        if (left != null) {
                            return left;
                        }
                        return evaluate(binOp.right);
                    }
                    Object left = evaluate(binOp.left);
                    Object right = evaluate(binOp.right);
                    try {
                        return ArithmeticEvaluator.applyOperator(binOp.operator, left, right);
                    } catch (RuntimeException ee) {
                        throw withLocation(ee.getMessage(), binOp.line, binOp.column);
                    }
                }
            }

            else if (node instanceof UnaryOperationNode) {
                UnaryOperationNode unaryOp = (UnaryOperationNode) node;
                Object operand = evaluate(unaryOp.operand);
                try {
                    return ArithmeticEvaluator.applyUnaryOperator(unaryOp.operator, operand, unaryOp.isPostfix,
                            unaryOp.operand, environment);
                } catch (RuntimeException ee) {
                    throw withLocation(ee.getMessage(), unaryOp.line, unaryOp.column);
                }
            }

            else if (node instanceof VariableDeclarationNode) {
                VariableDeclarationNode varDecl = (VariableDeclarationNode) node;
                String declared = normalizeTypeName(varDecl.type);
                Object value = varDecl.initializer != null ? evaluate(varDecl.initializer) : UnsetValue.typed(declared);
                assertTypeCompatibility(value, varDecl.type, "Type mismatch for '" + varDecl.name + "'");
                environment.put(varDecl.name, new MutableValue(value, declared));
                return null;
            }

            else if (node instanceof ConstantDeclarationNode) {
                ConstantDeclarationNode constDecl = (ConstantDeclarationNode) node;
                Object value = constDecl.value != null ? evaluate(constDecl.value) : null;
                assertTypeCompatibility(value, constDecl.type, "Type mismatch for '" + constDecl.name + "'");
                environment.put(constDecl.name, new ConstantValue(value));
                return null;
            }

            else if (node instanceof BlockNode) {
                BlockNode block = (BlockNode) node;
                Object result = null;
                for (Node statement : block.statements) {
                    result = evaluate(statement);
                }
                return result;
            }

            else if (node instanceof IfStatementNode) {
                IfStatementNode ifStmt = (IfStatementNode) node;
                if (isTruthy(evaluate(ifStmt.condition))) {
                    return evaluate(ifStmt.thenBranch);
                }
                for (ElseIfClauseNode altClause : ifStmt.altClauses) {
                    if (isTruthy(evaluate(altClause.condition))) {
                        return evaluate(altClause.body);
                    }
                }
                if (ifStmt.elseBranch != null) {
                    return evaluate(ifStmt.elseBranch);
                }
                return null;
            }

            else if (node instanceof MatchStatementNode) {
                MatchStatementNode matchStmt = (MatchStatementNode) node;
                Object value = evaluate(matchStmt.expression);
                for (MatchCaseNode caseNode : matchStmt.cases) {
                    if (value.equals(evaluate(caseNode.pattern))) {
                        return evaluate(caseNode.body);
                    }
                }
                if (matchStmt.defaultCase != null) {
                    return evaluate(matchStmt.defaultCase);
                }
                return null;
            }

            else if (node instanceof FunctionDeclarationNode) {
                return evaluateFunctionDeclaration((FunctionDeclarationNode) node);
            }

            else if (node instanceof ReturnStatementNode) {
                ReturnStatementNode returnStmt = (ReturnStatementNode) node;
                Object value = returnStmt.expression != null ? evaluate(returnStmt.expression) : null;
                throw new ReturnException(value);
            }

            else if (node instanceof WhileLoopNode) {
                WhileLoopNode whileLoop = (WhileLoopNode) node;
                Object result = null;
                boolean previousInsideLoop = insideLoop;
                insideLoop = true;
                try {
                    while (isTruthy(evaluate(whileLoop.condition))) {
                        try {
                            result = evaluate(whileLoop.body);
                        } catch (BreakException be) {
                            break;
                        } catch (ContinueException ce) {
                            continue;
                        }
                    }
                } finally {
                    insideLoop = previousInsideLoop;
                }
                return result;
            }

            else if (node instanceof ForLoopNode) {
                ForLoopNode forLoopNode = (ForLoopNode) node;
                boolean previousInsideLoop = insideLoop;
                insideLoop = true;
                try {
                    evaluate(forLoopNode.initializer);
                    while (true) {
                        if (forLoopNode.condition != null) {
                            Object condResult = evaluate(forLoopNode.condition);
                            if (!(condResult instanceof Boolean) || !((Boolean) condResult)) {
                                break;
                            }
                        }
                        try {
                            evaluate(forLoopNode.body);
                        } catch (BreakException be) {
                            break;
                        } catch (ContinueException ce) {
                            // Continue still runs the increment expression.
                        }
                        if (forLoopNode.increment != null) {
                            evaluate(forLoopNode.increment);
                        }
                    }
                } finally {
                    insideLoop = previousInsideLoop;
                }
                return null;
            }

            else if (node instanceof ForEachLoopNode) {
                ForEachLoopNode forEachLoop = (ForEachLoopNode) node;
                Object collection = evaluate(forEachLoop.iterable);
                if (!(collection instanceof List) && !(collection instanceof java.util.Set)
                        && !(collection instanceof java.util.Map) && !(collection instanceof String)) {
                    throw new RuntimeException("For-each loop requires a list, set, map, or string");
                }
                Iterable<?> iterable;
                if (collection instanceof List) {
                    iterable = (List<?>) collection;
                } else if (collection instanceof java.util.Set) {
                    iterable = (java.util.Set<?>) collection;
                } else if (collection instanceof java.util.Map) {
                    // Map iteration follows the language's collection convention:
                    // iterate keys in the map's insertion order when available.
                    iterable = ((java.util.Map<?, ?>) collection).keySet();
                } else {
                    List<String> characters = new ArrayList<>();
                    String text = (String) collection;
                    for (int i = 0; i < text.length(); i++) {
                        characters.add(text.substring(i, i + 1));
                    }
                    iterable = characters;
                }
                boolean previousInsideLoop = insideLoop;
                insideLoop = true;
                try { for (Object item : iterable) {
                    if (forEachLoop.variable instanceof VariableDeclarationNode) {
                        VariableDeclarationNode varDecl = (VariableDeclarationNode) forEachLoop.variable;
                        assertTypeCompatibility(item, varDecl.type, "Type mismatch for '" + varDecl.name + "'");
                        environment.put(varDecl.name, new MutableValue(item, normalizeTypeName(varDecl.type)));
                    } else if (forEachLoop.variable instanceof IdentifierNode) {
                        String varName = ((IdentifierNode) forEachLoop.variable).name;
                        Object current = environment.get(varName);
                        if (current instanceof ConstantValue) {
                            throw new RuntimeException("Cannot assign to constant '" + varName + "'");
                        }
                        if (current instanceof MutableValue) {
                            MutableValue mutable = (MutableValue) current;
                            assertTypeCompatibility(item, mutable.declaredType, "Type mismatch for '" + varName + "'");
                            mutable.value = item;
                        } else {
                            environment.put(varName, new MutableValue(item));
                        }
                    }
                    try {
                        evaluate(forEachLoop.body);
                    } catch (BreakException be) {
                        break;
                    } catch (ContinueException ce) {
                        continue;
                    }
                } } finally { insideLoop = previousInsideLoop; }
                return null;
            }

            else if (node instanceof NoOpNode) {
                return null;
            }

            else if (node instanceof ContinueStatementNode) {
                if (!insideLoop) {
                    throw new RuntimeException("Continue statement not within a loop context");
                }
                throw new ContinueException();
            }

            else if (node instanceof BreakStatementNode) {
                if (!insideLoop) {
                    throw new RuntimeException("Break statement not within a loop context");
                }
                throw new BreakException();
            }

            else if (node instanceof ExpressionStatementNode) {
                return evaluate(((ExpressionStatementNode) node).expression);
            }

            else if (node instanceof ListExpressionNode) {
                ListExpressionNode listExpr = (ListExpressionNode) node;
                if (listExpr.iterator != null && listExpr.iterable != null) {
                    ArrayList<ComprehensionClause> clauses = new ArrayList<>();
                    clauses.add(new ComprehensionClause(
                            listExpr.iterator,
                            listExpr.iterable,
                            listExpr.condition));
                    return evaluateListComprehension(new ListComprehensionNode(
                            listExpr.expression,
                            clauses));
                } else {
                    if (listExpr.elements.size() == 1 && listExpr.elements.get(0) instanceof RangeListNode) {
                        return evaluate(listExpr.elements.get(0));
                    }
                    List<Object> elements = new ArrayList<>();
                    for (Node elem : listExpr.elements) {
                        elements.add(evaluate(elem));
                    }
                    return elements;
                }
            }

            else if (node instanceof DictionaryComprehensionNode) {
                return evaluateDictComprehension((DictionaryComprehensionNode) node);
            }

            else if (node instanceof ListComprehensionNode) {
                return evaluateListComprehension((ListComprehensionNode) node);
            }

            else if (node instanceof RangeListNode) {
                RangeListNode rangeNode = (RangeListNode) node;
                int start = toWholeInt(evaluate(rangeNode.getStart()), "Range start must be an integer");
                int end = toWholeInt(evaluate(rangeNode.getEnd()), "Range end must be an integer");
                List<Integer> range = new ArrayList<>();
                if (start <= end) {
                    for (int i = start; i <= end; i++) {
                        range.add(i);
                    }
                } else {
                    for (int i = start; i >= end; i--) {
                        range.add(i);
                    }
                }
                return range;
            }

            else if (node instanceof FormattedStringNode) {
                FormattedStringNode formattedString = (FormattedStringNode) node;
                StringBuilder result = new StringBuilder();
                for (Node part : formattedString.getParts()) {
                    if (part instanceof StringLiteralNode) {
                        result.append(((StringLiteralNode) part).getValue());
                    } else {
                        result.append(ValueFormatter.toDisplayString(evaluate(part)));
                    }
                }
                return result.toString();
            }

            else if (node instanceof TupleExpressionNode) {
                TupleExpressionNode tuple = (TupleExpressionNode) node;
                List<Object> elements = new ArrayList<>();
                for (Node element : tuple.elements) {
                    elements.add(evaluate(element));
                }
                return elements;
            }

            else if (node instanceof ObjectLiteralNode) {
                ObjectLiteralNode objectLiteral = (ObjectLiteralNode) node;
                Map<String, Object> obj = new LinkedHashMap<>();
                for (Map.Entry<String, Node> entry : objectLiteral.properties.entrySet()) {
                    obj.put(entry.getKey(), evaluate(entry.getValue()));
                }
                return obj;
            }

            else if (node instanceof MemberAccessNode) {
                return MemberAccessEvaluator.evaluateMemberAccess((MemberAccessNode) node, this);
            }
            else if (node instanceof CallExpressionNode) {
                CallExpressionNode callNode = (CallExpressionNode) node;
                try {
                    if (callNode.getCallee() instanceof IdentifierNode
                            && "is_unset".equals(((IdentifierNode) callNode.getCallee()).name)) {
                        if (callNode.getArguments().size() != 1) {
                            throw new RuntimeException("is_unset expects exactly one identifier");
                        }
                        Node target = callNode.getArguments().get(0);
                        if (!(target instanceof IdentifierNode)) {
                            throw new RuntimeException("is_unset expects a bare identifier");
                        }
                        return isUnsetBinding(((IdentifierNode) target).name);
                    }
                    Object callee = evaluate(callNode.getCallee());
                    List<Object> arguments = new ArrayList<>();
                    for (Node arg : callNode.getArguments()) {
                        arguments.add(evaluate(arg));
                    }
                    if (!(callee instanceof Callable)) {
                        throw new RuntimeException("Attempt to call non-function value: " + ValueFormatter.toDisplayString(callee));
                    }
                    return ((Callable) callee).call(arguments);
                } catch (ControlFlowSignal signal) {
                    throw signal;
                } catch (RuntimeException ex) {
                    if (hasLocationInfo(ex)) {
                        throw ex;
                    }
                    throw attachLocation(ex, callNode.getLine(), callNode.getColumn());
                }
            }
            else if (node instanceof LambdaExpressionNode) {
                LambdaExpressionNode lambda = (LambdaExpressionNode) node;
                return new LambdaFunction(lambda.parameters, lambda.body, this);
            }

            else if (node instanceof NewInstanceNode) {
                NewInstanceNode newNode = (NewInstanceNode) node;
                Object classObj = get(newNode.className);
                if (!(classObj instanceof Callable)) {
                    throw new RuntimeException("Unknown class: " + newNode.className);
                }
                List<Object> args = new ArrayList<>();
                for (Node arg : newNode.arguments) {
                    args.add(evaluate(arg));
                }
                return ((Callable) classObj).call(args);
            }

            else if (node instanceof IndexAccessNode) {
                IndexAccessNode indexNode = (IndexAccessNode) node;
                try {
                    Object target = evaluate(indexNode.getTarget());
                    if (indexNode.isSlice()) {
                        return sliceValue(target, indexNode.getIndex(), indexNode.getEndIndex(), indexNode.getStep());
                    }
                    Object index = resolveIndexKey(indexNode, target);
                    if (target instanceof List) {
                        if (!(index instanceof Number)) {
                            throw new RuntimeException("List index must be a number");
                        }
                        int idx = ((Number) index).intValue();
                        List<?> list = (List<?>) target;
                        if (idx < 0 || idx >= list.size()) {
                            throw new RuntimeException("Index " + idx + " out of bounds for length " + list.size());
                        }
                        return list.get(idx);
                    } else if (target instanceof Map) {
                        Map<?, ?> map = (Map<?, ?>) target;
                        Object key = resolveMapKey(map, index);
                        return map.get(key);
                    } else if (target instanceof EntryValue) {
                        EntryValue entry = (EntryValue) target;
                        if (java.util.Objects.equals(index, entry.key()) || java.util.Objects.equals(index, "value")
                                || java.util.Objects.equals(index, "v")) {
                            return entry.value();
                        }
                        if (java.util.Objects.equals(index, "key") || java.util.Objects.equals(index, "k")) {
                            return entry.key();
                        }
                        return null;
                    }
                    throw new RuntimeException("Cannot index object of type: " + target.getClass().getSimpleName());
                } catch (ControlFlowSignal signal) {
                    throw signal;
                } catch (RuntimeException ex) {
                    throw attachLocation(ex, indexNode.getLine(), indexNode.getColumn());
                }
            }
            else if (node instanceof ConditionalExpressionNode) {
                ConditionalExpressionNode condExpr = (ConditionalExpressionNode) node;
                Object conditionResult = evaluate(condExpr.condition);
                if (isTruthy(conditionResult)) {
                    return evaluate(condExpr.trueBranch);
                } else {
                    return evaluate(condExpr.falseBranch);
                }
            }

            else {
                throw new RuntimeException("Unknown node type: " + node.getClass().getSimpleName());
            }
        } catch (ControlFlowSignal e) {
            throw e;
        } catch (RuntimeException e) {
            if (!hasLocationInfo(e)) {
                int[] loc = tryExtractNodeLocation(node);
                if (loc[0] > 0 && loc[1] > 0) {
                    e = attachLocation(e, loc[0], loc[1]);
                }
            }
            if (this.loggingEnabled) {
                logger.logError("Runtime error", e);
            }
            throw e;
        } finally {
            if (node instanceof WhileLoopNode || node instanceof ForLoopNode) {
                insideLoop = false;
            }
        }
    }
    private Object evaluateFunctionDeclaration(FunctionDeclarationNode node) {
        Map<String, Object> closure = new HashMap<>(this.environment);
        UserFunction function = new UserFunction(
                node.parameters,
                closure,
                node.body,
                context != null ? context.tokens : null,
                context != null ? context.sourceText : null);
        // Bind function to its own closure for recursion.
        closure.put(node.name, function);
        environment.put(node.name, function);
        return null;
    }

    private Object evaluateClassDeclaration(ClassDeclarationNode node) {
        VersaClassValue parentClass = null;
        if (node.parent != null) {
            Object parentValue = evaluate(node.parent);
            if (parentValue instanceof VersaClassValue) {
                parentClass = (VersaClassValue) parentValue;
            } else {
                throw new RuntimeException("Parent is not a class: " + ValueFormatter.toDisplayString(parentValue));
            }
        }
        Object vdbBinding = null;
        if (node.vdbBinding != null) {
            vdbBinding = evaluate(node.vdbBinding);
        }
        VersaClassValue clazz = new VersaClassValue(node.className, node.constructorParameters, parentClass, vdbBinding);
        environment.put(node.className, clazz);

        if (node.body instanceof BlockNode) {
            BlockNode body = (BlockNode) node.body;
            for (Node member : body.statements) {
                if (member instanceof FunctionDeclarationNode) {
                    FunctionDeclarationNode fn = (FunctionDeclarationNode) member;
                    Map<String, Object> closure = new HashMap<>(this.environment);
                    UserFunction function = new UserFunction(
                            fn.parameters,
                            closure,
                            fn.body,
                            context != null ? context.tokens : null,
                            context != null ? context.sourceText : null);
                    closure.put(fn.name, function);
                    clazz.addMethod(fn.name, function, fn.isStatic);
                    continue;
                }
                if (member instanceof ExpressionStatementNode) {
                    evaluate(((ExpressionStatementNode) member).expression);
                    continue;
                }
            }
        }
        return null;
    }

    private Object evaluateEnumDeclaration(EnumDeclarationNode node) {
        VersaEnumValue enumValue = new VersaEnumValue(node.enumName);
        environment.put(node.enumName, enumValue);
        for (EnumMemberNode member : node.members) {
            Object value = member.value != null ? evaluate(member.value) : member.ordinal;
            enumValue.addMember(member.name, value, member.ordinal);
        }
        return enumValue;
    }

    public static boolean isTruthy(Object value) {
        if (value == null) {
            return false;
        }
        if (value instanceof Boolean) {
            return (Boolean) value;
        }
        return true;
    }

    private static List<?> iterableValues(Object value, String functionName) {
        if (value instanceof List<?>) {
            return (List<?>) value;
        }
        if (value instanceof java.util.Set<?>) {
            return new ArrayList<>((java.util.Set<?>) value);
        }
        if (value instanceof java.util.Map<?, ?>) {
            return new ArrayList<>(((java.util.Map<?, ?>) value).keySet());
        }
        if (value instanceof String) {
            List<String> characters = new ArrayList<>();
            String text = (String) value;
            for (int i = 0; i < text.length(); i++) {
                characters.add(text.substring(i, i + 1));
            }
            return characters;
        }
        throw new RuntimeException(functionName + " expects a list, set, map, or string");
    }

    private Object evaluateListComprehension(ListComprehensionNode node) {
        List<Object> result = new ArrayList<>();
        List<ComprehensionClause> clauses = node.getClauses();
        evaluateClauses(clauses, 0, new HashMap<>(environment), result, node.getExpression());
        return result;
    }

    private Object evaluateDictComprehension(DictionaryComprehensionNode node) {
        Map<Object, Object> result = new java.util.LinkedHashMap<>();
        Object iterable = evaluate(node.iterable);

        Iterable<?> values;
        if (iterable instanceof List<?>) {
            values = (List<?>) iterable;
        } else if (iterable instanceof java.util.Set<?>) {
            values = (java.util.Set<?>) iterable;
        } else if (iterable instanceof String) {
            List<String> characters = new ArrayList<>();
            String text = (String) iterable;
            for (int i = 0; i < text.length(); i++) {
                characters.add(text.substring(i, i + 1));
            }
            values = characters;
        } else if (iterable instanceof java.util.Map<?, ?>) {
            values = ((java.util.Map<?, ?>) iterable).keySet();
        } else {
            throw new RuntimeException("Dictionary comprehension iterable must be a list, set, map, or string");
        }

        for (Object item : values) {
            Map<String, Object> newEnv = new HashMap<>(environment);
            newEnv.put(node.iterator, item);

            if (node.condition != null) {
                Object condition = evaluateInContext(node.condition, newEnv);
                if (!isTruthy(condition)) continue;
            }

            Object key = evaluateInContext(node.keyExpr, newEnv);
            Object value = evaluateInContext(node.valueExpr, newEnv);
            result.put(key, value);
        }
        return result;
    }

    private void evaluateClauses(List<ComprehensionClause> clauses, int index,
            Map<String, Object> env, List<Object> result,
            Node expression) {
        if (index >= clauses.size()) {
            result.add(evaluateInContext(expression, env));
            return;
        }

        ComprehensionClause clause = clauses.get(index);
        Object iterObj = evaluateInContext(clause.iterable, env);
        if (iterObj instanceof List) {
            for (Object item : (List<?>) iterObj) {
                Map<String, Object> newEnv = new HashMap<>(env);
                newEnv.put(clause.iterator, item);
                
                if (clause.condition != null) {
                    Object cond = evaluateInContext(clause.condition, newEnv);
                    if (!isTruthy(cond)) {
                        continue;
                    }
                }
                
                evaluateClauses(clauses, index + 1, newEnv, result, expression);
            }
        } else if (iterObj instanceof java.util.Set) {
            for (Object item : (java.util.Set<?>) iterObj) {
                Map<String, Object> newEnv = new HashMap<>(env);
                newEnv.put(clause.iterator, item);

                if (clause.condition != null) {
                    Object cond = evaluateInContext(clause.condition, newEnv);
                    if (!isTruthy(cond)) {
                        continue;
                    }
                }

                evaluateClauses(clauses, index + 1, newEnv, result, expression);
            }
        } else if (iterObj instanceof String) {
            String s = (String) iterObj;
            for (int i = 0; i < s.length(); i++) {
                Map<String, Object> newEnv = new HashMap<>(env);
                newEnv.put(clause.iterator, s.substring(i, i + 1));
                
                if (clause.condition != null) {
                    Object cond = evaluateInContext(clause.condition, newEnv);
                    if (!isTruthy(cond)) {
                        continue;
                    }
                }
                
                evaluateClauses(clauses, index + 1, newEnv, result, expression);
            }
        } else if (iterObj instanceof java.util.Map) {
            for (Object item : ((java.util.Map<?, ?>) iterObj).keySet()) {
                Map<String, Object> newEnv = new HashMap<>(env);
                newEnv.put(clause.iterator, item);

                if (clause.condition != null) {
                    Object cond = evaluateInContext(clause.condition, newEnv);
                    if (!isTruthy(cond)) {
                        continue;
                    }
                }

                evaluateClauses(clauses, index + 1, newEnv, result, expression);
            }
        } else {
            throw new RuntimeException("List comprehension iterable must be a list, set, map, or string");
        }
    }

    public Object evaluateInContext(Node node, Map<String, Object> context) {
        Evaluator evaluator = new Evaluator(new EvaluationContext(context));
        return evaluator.evaluate(node);
    }

    public boolean isInsideLoop() {
        return insideLoop;
    }

    public Object get(String name) {
        if (environment.containsKey(name)) {
            Object value = environment.get(name);
            if (value instanceof MutableValue) {
                return ((MutableValue) value).value;
            }
            if (value instanceof ConstantValue) {
                return ((ConstantValue) value).value;
            }
            return value;
        }
        return null;
    }

    public boolean hasBinding(String name) {
        if (environment.containsKey(name)) {
            return true;
        }
        return outerEvaluator != null && outerEvaluator.hasBinding(name);
    }

    private String valueType(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof UnsetValue) {
            String declared = ((UnsetValue) value).getDeclaredType();
            if (declared == null || declared.isEmpty()) {
                return "unset";
            }
            return displayTypeName(declared) + "<unset>";
        }
        if (value instanceof MutableValue) {
            return valueType(((MutableValue) value).value);
        }
        if (value instanceof Integer) {
            return "int";
        }
        if (value instanceof Number) {
            return "float";
        }
        if (value instanceof String) {
            String text = ((String) value).trim();
            if (isJsonText(text)) {
                return "json";
            }
            if (isXmlText(text)) {
                return "xml";
            }
            return "string";
        }
        if (value instanceof Boolean) {
            return "bool";
        }
        if (value instanceof List) {
            return "list";
        }
        if (value instanceof java.util.Set) {
            return "set";
        }
        if (value instanceof EntryValue) {
            return "Entry";
        }
        if (value instanceof Map) {
            String markerType = TimeDate.versaType(value);
            if (markerType != null && !markerType.isEmpty()) {
                return markerType;
            }
            if (isXmlObject(value)) {
                return "xml";
            }
            return "object";
        }
        if (value instanceof VersaEnumMemberValue) {
            return "enum_value";
        }
        if (value instanceof VersaEnumValue) {
            return "enum";
        }
        if (value instanceof VersaInstanceValue) {
            return "object";
        }
        if (value instanceof VersaClassValue) {
            return "class";
        }
        if (value instanceof Callable) {
            return "function";
        }
        return value.getClass().getSimpleName();
    }

    private boolean isType(Object value, String rawExpected) {
        String expected = normalizeTypeName(rawExpected);
        switch (expected) {
            case "any":
                return true;
            case "unset":
                return value instanceof UnsetValue;
            case "null":
                return value == null;
            case "bool":
                return value instanceof Boolean;
            case "int":
                return value instanceof Integer;
            case "float":
                return value instanceof Number && !(value instanceof Integer);
            case "number":
                return value instanceof Number;
            case "string":
                return value instanceof String;
            case "list":
                return value instanceof List;
            case "set":
                return value instanceof java.util.Set;
            case "entry":
                return value instanceof EntryValue;
            case "object":
                return (value instanceof VersaInstanceValue)
                        || (value instanceof Map && !isXmlObject(value) && TimeDate.versaType(value) == null);
            case "enum":
            case "enumeration":
                return value instanceof VersaEnumValue;
            case "enum_value":
            case "enum_member":
                return value instanceof VersaEnumMemberValue;
            case "class":
                return value instanceof VersaClassValue;
            case "function":
                return value instanceof Callable;
            case "json":
                return isJsonValue(value);
            case "xml":
                return isXmlValue(value);
            case "datetime":
            case "date":
            case "time":
            case "timedelta":
            case "timezone":
            case "time_struct":
                return expected.equals(TimeDate.versaType(value));
            default:
                return expected.equals(valueType(value));
        }
    }

    public void assertTypeCompatibility(Object value, String declaredType, String prefix) {
        if (declaredType == null || String.valueOf(declaredType).trim().isEmpty()) {
            return;
        }
        if (value instanceof UnsetValue) {
            return;
        }
        String normalized = normalizeTypeName(declaredType);
        if (normalized.isEmpty() || "any".equals(normalized)) {
            return;
        }
        if (!isType(value, normalized)) {
            String actual = valueType(value);
            String messagePrefix = (prefix == null || prefix.isEmpty()) ? "Type mismatch" : prefix;
            throw new RuntimeException(
                    messagePrefix + ": expected " + normalized + ", got " + actual);
        }
    }

    private String normalizeTypeName(String rawExpected) {
        String expected = String.valueOf(rawExpected == null ? "" : rawExpected).trim().toLowerCase(Locale.ROOT);
        if (expected.isEmpty()) {
            return "";
        }
        switch (expected) {
            case "integer":
                return "int";
            case "double":
                return "float";
            case "boolean":
                return "bool";
            case "str":
                return "string";
            case "array":
                return "list";
            case "dtf":
            case "datetimeformat":
                return "string";
            case "map":
            case "dict":
                return "object";
            case "time_struct":
            case "timestruct":
                return "time_struct";
            case "nil":
            case "none":
                return "null";
            default:
                return expected;
        }
    }

    private String displayTypeName(String normalized) {
        switch (normalized) {
            case "string":
                return "str";
            case "object":
                return "dict";
            default:
                return normalized;
        }
    }

    private int toWholeInt(Object value, String errorMessage) {
        if (value instanceof Integer) {
            return (Integer) value;
        }
        if (value instanceof Number) {
            double numeric = ((Number) value).doubleValue();
            if (Math.floor(numeric) != numeric) {
                throw new RuntimeException(errorMessage);
            }
            return (int) numeric;
        }
        throw new RuntimeException(errorMessage);
    }

    private boolean isJsonValue(Object value) {
        return isJsonValue(value, Collections.newSetFromMap(new IdentityHashMap<>()), true);
    }

    private boolean isJsonValue(Object value, Set<Object> visited, boolean topLevel) {
        if (value == null || value instanceof Number || value instanceof Boolean) {
            return true;
        }
        if (value instanceof String) {
            if (!topLevel) {
                return true;
            }
            return isJsonText(((String) value).trim());
        }
        if (value instanceof MutableValue) {
            return isJsonValue(((MutableValue) value).value, visited, topLevel);
        }
        if (value instanceof List<?>) {
            if (visited.contains(value)) {
                return true;
            }
            visited.add(value);
            for (Object item : (List<?>) value) {
                if (!isJsonValue(item, visited, false)) {
                    return false;
                }
            }
            return true;
        }
        if (value instanceof Map<?, ?>) {
            if (visited.contains(value)) {
                return true;
            }
            visited.add(value);
            for (Map.Entry<?, ?> entry : ((Map<?, ?>) value).entrySet()) {
                if (entry.getKey() == null) {
                    return false;
                }
                if (!isJsonValue(entry.getValue(), visited, false)) {
                    return false;
                }
            }
            return true;
        }
        return false;
    }

    private boolean isXmlValue(Object value) {
        if (value instanceof MutableValue) {
            return isXmlValue(((MutableValue) value).value);
        }
        if (value instanceof String) {
            return isXmlText(((String) value).trim());
        }
        return isXmlObject(value);
    }

    private boolean isXmlObject(Object value) {
        if (!(value instanceof Map<?, ?>)) {
            return false;
        }
        Map<?, ?> map = (Map<?, ?>) value;
        Object root = map.get("root");
        if (!(root instanceof Map<?, ?>)) {
            return false;
        }
        Map<?, ?> rootMap = (Map<?, ?>) root;
        return rootMap.containsKey("name")
                && rootMap.containsKey("attributes")
                && rootMap.containsKey("children")
                && rootMap.containsKey("text");
    }

    private boolean isJsonText(String text) {
        if (text.isEmpty()) {
            return false;
        }
        char first = text.charAt(0);
        boolean objectOrArray = first == '{' || first == '[';
        if (!objectOrArray) {
            return false;
        }
        try {
            JsonXml.parseJson(text);
            return true;
        } catch (RuntimeException e) {
            return false;
        }
    }

    private boolean isXmlText(String text) {
        if (text.isEmpty() || !text.startsWith("<") || !text.endsWith(">")) {
            return false;
        }
        try {
            JsonXml.parseXml(text);
            return true;
        } catch (RuntimeException e) {
            return false;
        }
    }

    private Map<String, Object> buildTimeModule() {
        Map<String, Object> time = new HashMap<>();
        time.put("time", new BuiltinFunction(args -> TimeDate.time()));
        time.put("time_ns", new BuiltinFunction(args -> TimeDate.timeNs()));
        time.put("perf_counter", new BuiltinFunction(args -> TimeDate.perfCounter()));
        time.put("monotonic", new BuiltinFunction(args -> TimeDate.monotonic()));
        time.put("process_time", new BuiltinFunction(args -> TimeDate.processTime()));
        time.put("sleep", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("time.sleep expects seconds");
            }
            return TimeDate.sleep(args.get(0));
        }));
        time.put("localtime", new BuiltinFunction(args -> TimeDate.localtime(args.isEmpty() ? null : args.get(0))));
        time.put("gmtime", new BuiltinFunction(args -> TimeDate.gmtime(args.isEmpty() ? null : args.get(0))));
        time.put("strftime", new BuiltinFunction(args -> {
            if (args.isEmpty()) {
                throw new RuntimeException("time.strftime expects format and time struct");
            }
            String format = String.valueOf(args.get(0));
            Object struct = args.size() > 1 ? args.get(1) : TimeDate.localtime(null);
            return TimeDate.strftime(format, struct);
        }));
        time.put("ctime", new BuiltinFunction(args -> {
            Object ts = args.size() > 0 ? args.get(0) : null;
            Object format = args.size() > 1 ? args.get(1) : null;
            Object custom = args.size() > 2 ? args.get(2) : null;
            return TimeDate.ctime(ts, format, custom);
        }));
        return time;
    }

    private Map<String, Object> buildDatetimeModule() {
        Map<String, Object> datetime = new HashMap<>();
        datetime.put("now", new BuiltinFunction(args -> TimeDate.datetimeNow()));
        datetime.put("fromtimestamp", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("datetime.fromtimestamp expects timestamp");
            }
            return TimeDate.datetimeFromTimestamp(args.get(0));
        }));

        Map<String, Object> date = new HashMap<>();
        date.put("today", new BuiltinFunction(args -> TimeDate.dateToday()));
        date.put("fromtimestamp", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("datetime.date.fromtimestamp expects timestamp");
            }
            return TimeDate.dateFromTimestamp(args.get(0));
        }));

        Map<String, Object> timeSub = new HashMap<>();
        timeSub.put("from_components", new BuiltinFunction(TimeDate::timeFromComponents));

        datetime.put("date", date);
        datetime.put("time", timeSub);
        datetime.put("timedelta", new BuiltinFunction(args -> TimeDate.timedeltaFrom(args.isEmpty() ? null : args.get(0))));
        datetime.put("timezone", new BuiltinFunction(args -> TimeDate.timezoneFrom(args.isEmpty() ? null : args.get(0))));
        return datetime;
    }

    private Map<String, Object> buildHttpModule() {
        Map<String, Object> http = new HashMap<>();
        http.put("request", new BuiltinFunction(args -> {
            if (args.size() < 2) {
                throw new RuntimeException("http.request expects method and url");
            }
            String method = String.valueOf(args.get(0));
            String url = String.valueOf(args.get(1));
            Map<String, Object> options = args.size() > 2 && args.get(2) instanceof Map
                    ? (Map<String, Object>) args.get(2)
                    : Collections.emptyMap();
            return HTTP.requestSync(method, url, options);
        }));
        http.put("get", new BuiltinFunction(args -> {
            if (args.isEmpty()) {
                throw new RuntimeException("http.get expects url");
            }
            String url = String.valueOf(args.get(0));
            Map<String, Object> options = args.size() > 1 && args.get(1) instanceof Map
                    ? (Map<String, Object>) args.get(1)
                    : Collections.emptyMap();
            return HTTP.getSync(url, options);
        }));
        http.put("post", new BuiltinFunction(args -> {
            if (args.isEmpty()) {
                throw new RuntimeException("http.post expects url");
            }
            String url = String.valueOf(args.get(0));
            Map<String, Object> options = args.size() > 1 && args.get(1) instanceof Map
                    ? (Map<String, Object>) args.get(1)
                    : Collections.emptyMap();
            return HTTP.postSync(url, options);
        }));
        http.put("put", new BuiltinFunction(args -> {
            if (args.isEmpty()) {
                throw new RuntimeException("http.put expects url");
            }
            String url = String.valueOf(args.get(0));
            Map<String, Object> options = args.size() > 1 && args.get(1) instanceof Map
                    ? (Map<String, Object>) args.get(1)
                    : Collections.emptyMap();
            return HTTP.putSync(url, options);
        }));
        http.put("patch", new BuiltinFunction(args -> {
            if (args.isEmpty()) {
                throw new RuntimeException("http.patch expects url");
            }
            String url = String.valueOf(args.get(0));
            Map<String, Object> options = args.size() > 1 && args.get(1) instanceof Map
                    ? (Map<String, Object>) args.get(1)
                    : Collections.emptyMap();
            return HTTP.patchSync(url, options);
        }));
        http.put("delete", new BuiltinFunction(args -> {
            if (args.isEmpty()) {
                throw new RuntimeException("http.delete expects url");
            }
            String url = String.valueOf(args.get(0));
            Map<String, Object> options = args.size() > 1 && args.get(1) instanceof Map
                    ? (Map<String, Object>) args.get(1)
                    : Collections.emptyMap();
            return HTTP.deleteSync(url, options);
        }));
        return http;
    }

    private Map<String, Object> buildJsonXmlModule() {
        Map<String, Object> module = new HashMap<>();
        module.put("parse_json", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("json_xml.parse_json expects one argument");
            }
            return JsonXml.parseJson(String.valueOf(args.get(0)));
        }));
        module.put("json_to_obj", module.get("parse_json"));
        module.put("obj_to_json", new BuiltinFunction(args -> {
            if (args.isEmpty()) {
                throw new RuntimeException("json_xml.obj_to_json expects at least one argument");
            }
            boolean pretty = args.size() > 1 && castToBool(args.get(1));
            return JsonXml.objToJson(args.get(0), pretty);
        }));
        module.put("to_json", module.get("obj_to_json"));
        module.put("read_json", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("json_xml.read_json expects file path");
            }
            return JsonXml.readJson(String.valueOf(args.get(0)));
        }));
        module.put("write_json", new BuiltinFunction(args -> {
            if (args.size() < 2) {
                throw new RuntimeException("json_xml.write_json expects file path and value");
            }
            boolean pretty = args.size() > 2 && castToBool(args.get(2));
            return JsonXml.writeJson(String.valueOf(args.get(0)), args.get(1), pretty);
        }));
        module.put("parse_xml", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("json_xml.parse_xml expects one argument");
            }
            return JsonXml.parseXml(String.valueOf(args.get(0)));
        }));
        module.put("read_xml", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("json_xml.read_xml expects file path");
            }
            return JsonXml.readXml(String.valueOf(args.get(0)));
        }));
        module.put("write_xml", new BuiltinFunction(args -> {
            if (args.size() != 2) {
                throw new RuntimeException("json_xml.write_xml expects file path and xml string");
            }
            return JsonXml.writeXml(String.valueOf(args.get(0)), String.valueOf(args.get(1)));
        }));
        module.put("json_to_xml", new BuiltinFunction(args -> {
            if (args.isEmpty()) {
                throw new RuntimeException("json_xml.json_to_xml expects at least one argument");
            }
            String root = args.size() > 1 ? String.valueOf(args.get(1)) : "root";
            return JsonXml.jsonToXml(args.get(0), root);
        }));
        module.put("obj_to_xml", new BuiltinFunction(args -> {
            if (args.isEmpty()) {
                throw new RuntimeException("json_xml.obj_to_xml expects at least one argument");
            }
            String root = args.size() > 1 ? String.valueOf(args.get(1)) : "root";
            return JsonXml.objToXml(args.get(0), root);
        }));
        module.put("xml_to_json", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("json_xml.xml_to_json expects one argument");
            }
            return JsonXml.xmlToJson(String.valueOf(args.get(0)));
        }));
        module.put("xml_to_obj", module.get("xml_to_json"));
        module.put("read_text", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("json_xml.read_text expects file path");
            }
            return JsonXml.readText(String.valueOf(args.get(0)));
        }));
        module.put("write_text", new BuiltinFunction(args -> {
            if (args.size() != 2) {
                throw new RuntimeException("json_xml.write_text expects file path and text");
            }
            return JsonXml.writeText(String.valueOf(args.get(0)), String.valueOf(args.get(1)));
        }));
        return module;
    }

    private Map<String, Object> buildFilerModule() {
        Map<String, Object> filer = new HashMap<>();
        filer.put("join", new BuiltinFunction(args -> Filer.join(args.toArray())));
        filer.put("ensure_dir", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("filer.ensure_dir expects path");
            }
            return Filer.ensureDir(String.valueOf(args.get(0)));
        }));
        filer.put("exists", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("filer.exists expects path");
            }
            return Filer.exists(String.valueOf(args.get(0)));
        }));
        filer.put("write_text", new BuiltinFunction(args -> {
            if (args.size() != 2) {
                throw new RuntimeException("filer.write_text expects file path and text");
            }
            return Filer.writeText(String.valueOf(args.get(0)), String.valueOf(args.get(1)));
        }));
        filer.put("read_text", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("filer.read_text expects file path");
            }
            return Filer.readText(String.valueOf(args.get(0)));
        }));
        filer.put("read_bytes_base64", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("filer.read_bytes_base64 expects file path");
            }
            return Filer.readBytesBase64(String.valueOf(args.get(0)));
        }));
        filer.put("write_json", new BuiltinFunction(args -> {
            if (args.size() < 2) {
                throw new RuntimeException("filer.write_json expects file path and value");
            }
            boolean pretty = args.size() > 2 && castToBool(args.get(2));
            return Filer.writeJson(String.valueOf(args.get(0)), args.get(1), pretty);
        }));
        filer.put("read_json", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("filer.read_json expects file path");
            }
            return Filer.readJson(String.valueOf(args.get(0)));
        }));
        filer.put("write_xml", new BuiltinFunction(args -> {
            if (args.size() != 2) {
                throw new RuntimeException("filer.write_xml expects file path and xml string");
            }
            return Filer.writeXml(String.valueOf(args.get(0)), String.valueOf(args.get(1)));
        }));
        filer.put("read_xml", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("filer.read_xml expects file path");
            }
            return Filer.readXml(String.valueOf(args.get(0)));
        }));
        filer.put("write_csv", new BuiltinFunction(args -> {
            if (args.size() != 2 || !(args.get(1) instanceof List<?>)) {
                throw new RuntimeException("filer.write_csv expects file path and rows list");
            }
            return Filer.writeCsv(String.valueOf(args.get(0)), (List<?>) args.get(1));
        }));
        filer.put("read_csv", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("filer.read_csv expects file path");
            }
            return Filer.readCsv(String.valueOf(args.get(0)));
        }));
        filer.put("read_csv_records", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("filer.read_csv_records expects file path");
            }
            return Filer.readCsvRecords(String.valueOf(args.get(0)));
        }));
        return filer;
    }

    private Map<String, Object> buildEmailModule() {
        Map<String, Object> email = new HashMap<>();
        email.put("send", new BuiltinFunction(args -> {
            if (args.isEmpty()) {
                throw new RuntimeException("email.send expects options map");
            }
            if (!(args.get(0) instanceof Map)) {
                throw new RuntimeException("email.send expects a map argument");
            }
            return Email.sendSync((Map<String, Object>) args.get(0));
        }));
        return email;
    }

    private Map<String, Object> buildCryptoModule() {
        Map<String, Object> crypto = new HashMap<>();
        crypto.put("sha256", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("crypto.sha256 expects one argument");
            }
            return Crypto.sha256(String.valueOf(args.get(0)));
        }));
        crypto.put("sha512", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("crypto.sha512 expects one argument");
            }
            return Crypto.sha512(String.valueOf(args.get(0)));
        }));
        crypto.put("hmac_sha256", new BuiltinFunction(args -> {
            if (args.size() != 2) {
                throw new RuntimeException("crypto.hmac_sha256 expects secret and message");
            }
            return Crypto.hmacSha256(String.valueOf(args.get(0)), String.valueOf(args.get(1)));
        }));
        crypto.put("hmac_sha512", new BuiltinFunction(args -> {
            if (args.size() != 2) {
                throw new RuntimeException("crypto.hmac_sha512 expects secret and message");
            }
            return Crypto.hmacSha512(String.valueOf(args.get(0)), String.valueOf(args.get(1)));
        }));
        crypto.put("base64_encode", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("crypto.base64_encode expects one argument");
            }
            return Crypto.base64Encode(String.valueOf(args.get(0)));
        }));
        crypto.put("base64_decode", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("crypto.base64_decode expects one argument");
            }
            return Crypto.base64Decode(String.valueOf(args.get(0)));
        }));
        crypto.put("base64url_encode", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("crypto.base64url_encode expects one argument");
            }
            return Crypto.base64UrlEncode(String.valueOf(args.get(0)));
        }));
        crypto.put("base64url_decode", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("crypto.base64url_decode expects one argument");
            }
            return Crypto.base64UrlDecode(String.valueOf(args.get(0)));
        }));
        crypto.put("random_hex", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("crypto.random_hex expects byte length");
            }
            return Crypto.randomHex(castToInt(args.get(0)));
        }));
        crypto.put("random_bytes", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("crypto.random_bytes expects byte length");
            }
            return Crypto.randomBytes(castToInt(args.get(0)));
        }));
        crypto.put("uuid", new BuiltinFunction(args -> Crypto.uuid()));
        crypto.put("pbkdf2", new BuiltinFunction(args -> {
            if (args.size() < 2) {
                throw new RuntimeException("crypto.pbkdf2 expects password and salt");
            }
            int iterations = args.size() > 2 ? castToInt(args.get(2)) : 100000;
            int keyLength = args.size() > 3 ? castToInt(args.get(3)) : 32;
            String algorithm = args.size() > 4 ? String.valueOf(args.get(4)) : "HmacSHA256";
            return Crypto.pbkdf2(String.valueOf(args.get(0)), String.valueOf(args.get(1)), iterations, keyLength, algorithm);
        }));
        crypto.put("aes_gcm_encrypt", new BuiltinFunction(args -> {
            if (args.size() < 2) {
                throw new RuntimeException("crypto.aes_gcm_encrypt expects plaintext and key");
            }
            String iv = args.size() > 2 ? String.valueOf(args.get(2)) : null;
            return Crypto.aesGcmEncrypt(String.valueOf(args.get(0)), String.valueOf(args.get(1)), iv);
        }));
        crypto.put("aes_gcm_decrypt", new BuiltinFunction(args -> {
            if (args.size() < 3) {
                throw new RuntimeException("crypto.aes_gcm_decrypt expects ciphertext, key, and iv");
            }
            return Crypto.aesGcmDecrypt(String.valueOf(args.get(0)), String.valueOf(args.get(1)), String.valueOf(args.get(2)));
        }));
        return crypto;
    }

    private Map<String, Object> buildJwtModule() {
        Map<String, Object> jwtModule = new HashMap<>();
        jwtModule.put("sign", new BuiltinFunction(args -> {
            if (args.size() < 2) {
                throw new RuntimeException("jwt.sign expects payload and secret");
            }
            if (!(args.get(0) instanceof Map)) {
                throw new RuntimeException("jwt.sign expects payload as an object");
            }
            Map<String, Object> options = args.size() > 2 && args.get(2) instanceof Map
                    ? (Map<String, Object>) args.get(2)
                    : Collections.emptyMap();
            return Jwt.sign((Map<String, Object>) args.get(0), String.valueOf(args.get(1)), options);
        }));
        jwtModule.put("verify", new BuiltinFunction(args -> {
            if (args.size() < 2) {
                throw new RuntimeException("jwt.verify expects token and secret");
            }
            Map<String, Object> options = args.size() > 2 && args.get(2) instanceof Map
                    ? (Map<String, Object>) args.get(2)
                    : Collections.emptyMap();
            return Jwt.verify(String.valueOf(args.get(0)), String.valueOf(args.get(1)), options);
        }));
        jwtModule.put("decode", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("jwt.decode expects one token argument");
            }
            return Jwt.decode(String.valueOf(args.get(0)));
        }));
        return jwtModule;
    }

    private Map<String, Object> buildRandomModule() {
        Map<String, Object> random = new HashMap<>();
        random.put("seed", new BuiltinFunction(args -> {
            Object seed = args.isEmpty() ? null : args.get(0);
            RandomModule.seed(seed);
            return null;
        }));
        random.put("random", new BuiltinFunction(args -> RandomModule.random()));
        random.put("randint", new BuiltinFunction(args -> {
            if (args.size() != 2) {
                throw new RuntimeException("random.randint expects min and max");
            }
            return RandomModule.randint(castToInt(args.get(0)), castToInt(args.get(1)));
        }));
        random.put("randints", new BuiltinFunction(args -> {
            if (args.size() != 3) {
                throw new RuntimeException("random.randints expects min, max, and count");
            }
            return RandomModule.randints(castToInt(args.get(0)), castToInt(args.get(1)), castToInt(args.get(2)));
        }));
        random.put("randrange", new BuiltinFunction(args -> {
            if (args.isEmpty() || args.size() > 3) {
                throw new RuntimeException("random.randrange expects start, stop, and optional step");
            }
            Integer start;
            Integer stop;
            Integer step = null;
            if (args.size() == 1) {
                start = 0;
                stop = castToInt(args.get(0));
            } else {
                start = castToInt(args.get(0));
                stop = castToInt(args.get(1));
                if (args.size() == 3) {
                    step = castToInt(args.get(2));
                }
            }
            return RandomModule.randrange(start, stop, step);
        }));
        random.put("uniform", new BuiltinFunction(args -> {
            if (args.size() != 2) {
                throw new RuntimeException("random.uniform expects min and max");
            }
            return RandomModule.uniform(castToFloat(args.get(0)), castToFloat(args.get(1)));
        }));
        random.put("choice", new BuiltinFunction(args -> {
            if (args.size() != 1 || !(args.get(0) instanceof List<?>)) {
                throw new RuntimeException("random.choice expects one list argument");
            }
            return RandomModule.choice((List<?>) args.get(0));
        }));
        random.put("choices", new BuiltinFunction(args -> {
            if (args.size() < 1 || args.size() > 2 || !(args.get(0) instanceof List<?>)) {
                throw new RuntimeException("random.choices expects list and optional count");
            }
            int count = args.size() > 1 ? castToInt(args.get(1)) : 1;
            return RandomModule.choices((List<?>) args.get(0), count);
        }));
        random.put("shuffle", new BuiltinFunction(args -> {
            if (args.size() != 1 || !(args.get(0) instanceof List<?>)) {
                throw new RuntimeException("random.shuffle expects one list argument");
            }
            RandomModule.shuffle((List<Object>) args.get(0));
            return args.get(0);
        }));
        random.put("sample", new BuiltinFunction(args -> {
            if (args.size() != 2 || !(args.get(0) instanceof List<?>)) {
                throw new RuntimeException("random.sample expects list and count");
            }
            return RandomModule.sample((List<?>) args.get(0), castToInt(args.get(1)));
        }));
        random.put("boolean", new BuiltinFunction(args -> RandomModule.booleanValue()));
        random.put("chance", new BuiltinFunction(args -> {
            if (args.size() != 1) {
                throw new RuntimeException("random.chance expects probability between 0 and 1");
            }
            return RandomModule.chance(castToFloat(args.get(0)));
        }));
        return random;
    }

    private int castToInt(Object value) {
        if (value == null) {
            throw new RuntimeException("Cannot cast null to int");
        }
        if (value instanceof Boolean) {
            return ((Boolean) value) ? 1 : 0;
        }
        if (value instanceof Number) {
            return ((Number) value).intValue();
        }
        String text = String.valueOf(value).trim();
        if (text.isEmpty()) {
            throw new RuntimeException("Cannot cast empty string to int");
        }
        if ("true".equalsIgnoreCase(text)) {
            return 1;
        }
        if ("false".equalsIgnoreCase(text)) {
            return 0;
        }
        return (int) Double.parseDouble(text);
    }

    private double castToFloat(Object value) {
        if (value == null) {
            throw new RuntimeException("Cannot cast null to float");
        }
        if (value instanceof Boolean) {
            return ((Boolean) value) ? 1.0d : 0.0d;
        }
        if (value instanceof Number) {
            return ((Number) value).doubleValue();
        }
        String text = String.valueOf(value).trim();
        if (text.isEmpty()) {
            throw new RuntimeException("Cannot cast empty string to float");
        }
        if ("true".equalsIgnoreCase(text)) {
            return 1.0d;
        }
        if ("false".equalsIgnoreCase(text)) {
            return 0.0d;
        }
        return Double.parseDouble(text);
    }

    private boolean castToBool(Object value) {
        if (value == null) {
            return false;
        }
        if (value instanceof Boolean) {
            return (Boolean) value;
        }
        if (value instanceof Number) {
            return ((Number) value).doubleValue() != 0.0d;
        }
        String text = String.valueOf(value).trim();
        if (text.isEmpty()) {
            return false;
        }
        if ("false".equalsIgnoreCase(text) || "0".equals(text) || "null".equalsIgnoreCase(text)) {
            return false;
        }
        return true;
    }

    private Object resolveIndexKey(IndexAccessNode indexNode, Object target) {
        if ((target instanceof Map<?, ?> || target instanceof EntryValue)
                && indexNode.getIndex() instanceof IdentifierNode) {
            String identifier = ((IdentifierNode) indexNode.getIndex()).name;
            if (!hasBinding(identifier)) {
                return identifier;
            }
        }
        return evaluate(indexNode.getIndex());
    }

    private Object resolveMapKey(Map<?, ?> map, Object requestedKey) {
        if (map.containsKey(requestedKey)) {
            return requestedKey;
        }
        String stringKey = String.valueOf(requestedKey);
        if (map.containsKey(stringKey)) {
            return stringKey;
        }
        return requestedKey;
    }

    private Object sliceValue(Object target, Node startNode, Node endNode, Node stepNode) {
        Integer start = evaluateSliceBound(startNode);
        Integer end = evaluateSliceBound(endNode);
        Integer step = evaluateSliceBound(stepNode);
        int stride = step == null ? 1 : step;
        if (stride == 0) {
            throw new RuntimeException("Slice step cannot be zero");
        }

        if (target instanceof List<?>) {
            List<?> list = (List<?>) target;
            return selectSliceValues(list, start, end, stride);
        }

        if (target instanceof String) {
            String value = (String) target;
            StringBuilder result = new StringBuilder();
            for (Integer index : sliceIndexes(value.length(), start, end, stride)) {
                result.append(value.charAt(index));
            }
            return result.toString();
        }

        throw new RuntimeException("Slicing is supported for lists, tuples, and strings");
    }

    /**
     * Replace a list slice in-place.  Versa strings are immutable, so string
     * slice assignment is deliberately rejected with an actionable error.
     * The right-hand side is copied before mutation so assigning a list to a
     * slice of itself behaves predictably (for example, values[1:2] = values).
     */
    private void assignSliceValue(Object target, Node startNode, Node endNode, Node stepNode, Object replacement) {
        if (!(target instanceof List<?>)) {
            if (target instanceof String) {
                throw new RuntimeException("Cannot assign to a string slice; strings are immutable");
            }
            throw new RuntimeException("Slice assignment is supported for lists only");
        }
        if (!(replacement instanceof List<?>)) {
            throw new RuntimeException("Slice assignment requires a list value");
        }

        @SuppressWarnings("unchecked")
        List<Object> list = (List<Object>) target;
        Integer start = evaluateSliceBound(startNode);
        Integer end = evaluateSliceBound(endNode);
        Integer step = evaluateSliceBound(stepNode);
        int stride = step == null ? 1 : step;
        if (stride == 0) {
            throw new RuntimeException("Slice step cannot be zero");
        }
        List<Object> copiedReplacement = new ArrayList<>((List<?>) replacement);
        List<Integer> indexes = sliceIndexes(list.size(), start, end, stride);
        if (stride == 1) {
            int from = indexes.isEmpty() ? normalizeSliceIndex(start, list.size(), 0) : indexes.get(0);
            int to = indexes.isEmpty() ? from : indexes.get(indexes.size() - 1) + 1;
            list.subList(from, to).clear();
            list.addAll(from, copiedReplacement);
            return;
        }
        if (copiedReplacement.size() != indexes.size()) {
            throw new RuntimeException("Extended slice assignment requires a replacement list of length " + indexes.size());
        }
        for (int i = 0; i < indexes.size(); i++) {
            list.set(indexes.get(i), copiedReplacement.get(i));
        }
    }

    private Integer evaluateSliceBound(Node boundNode) {
        if (boundNode == null) {
            return null;
        }
        Object value = evaluate(boundNode);
        if (!(value instanceof Number)) {
            throw new RuntimeException("Slice bounds must be numbers");
        }
        return ((Number) value).intValue();
    }

    private int normalizeSliceIndex(Integer value, int size, int defaultValue) {
        int index = value == null ? defaultValue : value;
        if (index < 0) {
            index += size;
        }
        if (index < 0) {
            return 0;
        }
        if (index > size) {
            return size;
        }
        return index;
    }

    private List<Object> selectSliceValues(List<?> source, Integer start, Integer end, int step) {
        List<Object> values = new ArrayList<>();
        for (Integer index : sliceIndexes(source.size(), start, end, step)) {
            values.add(source.get(index));
        }
        return values;
    }

    /** Return Python-compatible half-open slice indexes, including negative steps. */
    private List<Integer> sliceIndexes(int size, Integer start, Integer end, int step) {
        List<Integer> indexes = new ArrayList<>();
        if (step > 0) {
            int from = start == null ? 0 : start;
            int to = end == null ? size : end;
            from = clampSliceBound(from, size, false);
            to = clampSliceBound(to, size, false);
            for (int index = from; index < to; index += step) {
                indexes.add(index);
                if (index > Integer.MAX_VALUE - step) break;
            }
        } else {
            int from = start == null ? size - 1 : start;
            int to = end == null ? -1 : end;
            from = clampSliceBound(from, size, true);
            to = clampSliceBound(to, size, true);
            for (int index = from; index > to; index += step) {
                indexes.add(index);
                if (index < Integer.MIN_VALUE - step) break;
            }
        }
        return indexes;
    }

    private int clampSliceBound(int value, int size, boolean reverse) {
        int normalized = value < 0 ? value + size : value;
        if (reverse) {
            if (normalized < -1) return -1;
            if (normalized >= size) return size - 1;
            return normalized;
        }
        if (normalized < 0) return 0;
        if (normalized > size) return size;
        return normalized;
    }

    public static class BreakException extends ControlFlowSignal {
        public BreakException() {
            super();
        }
    }

    public static class ContinueException extends ControlFlowSignal {
        public ContinueException() {
            super();
        }
    }

    private RuntimeException attachLocation(RuntimeException ex, int line, int column) {
        if (line <= 0 || column <= 0) {
            return ex;
        }
        if (ex instanceof EvaluationException) {
            EvaluationException ee = (EvaluationException) ex;
            if (ee.getLine() > 0 && ee.getColumn() > 0) {
                return ee;
            }
            return new EvaluationException(
                    ee.getType(),
                    ee.getMessage(),
                    line,
                    column,
                    getSourceLine(line),
                    ee);
        }
        return withLocation(ex.getMessage(), line, column, ex);
    }

    private RuntimeException withLocation(String message, int line, int column) {
        if (line > 0 && column > 0) {
            return new EvaluationException(
                    inferErrorType(message),
                    message,
                    line,
                    column,
                    getSourceLine(line));
        }
        return new EvaluationException(inferErrorType(message), message);
    }

    private RuntimeException withLocation(String message, int line, int column, Throwable cause) {
        if (line > 0 && column > 0) {
            return new EvaluationException(
                    inferErrorType(message),
                    message,
                    line,
                    column,
                    getSourceLine(line),
                    cause);
        }
        return new EvaluationException(inferErrorType(message), message, -1, -1, null, cause);
    }

    private boolean hasLocationInfo(RuntimeException ex) {
        if (ex instanceof VDBScriptDependencyException) {
            return true;
        }
        if (ex instanceof EvaluationException) {
            EvaluationException ee = (EvaluationException) ex;
            return ee.getLine() > 0;
        }
        String message = ex.getMessage();
        if (message == null) {
            return false;
        }
        String m = message.toLowerCase(Locale.ROOT);
        return m.contains(" at line ") || m.contains("line ") && m.contains("column");
    }

    private int[] tryExtractNodeLocation(Node node) {
        if (node == null) {
            return new int[] { -1, -1 };
        }
        try {
            Field lineField = node.getClass().getDeclaredField("line");
            lineField.setAccessible(true);
            Object lineObj = lineField.get(node);
            Field columnField = node.getClass().getDeclaredField("column");
            columnField.setAccessible(true);
            Object colObj = columnField.get(node);
            int line = lineObj instanceof Number ? ((Number) lineObj).intValue() : -1;
            int col = colObj instanceof Number ? ((Number) colObj).intValue() : -1;
            return new int[] { line, col };
        } catch (Exception ignored) {
        }
        try {
            Method getLine = node.getClass().getMethod("getLine");
            Method getColumn = node.getClass().getMethod("getColumn");
            Object lineObj = getLine.invoke(node);
            Object colObj = getColumn.invoke(node);
            int line = lineObj instanceof Number ? ((Number) lineObj).intValue() : -1;
            int col = colObj instanceof Number ? ((Number) colObj).intValue() : -1;
            return new int[] { line, col };
        } catch (Exception ignored) {
        }
        return new int[] { -1, -1 };
    }

    private String getSourceLine(int line) {
        if (context == null || context.sourceLines == null || line < 1 || line > context.sourceLines.length) {
            return null;
        }
        return context.sourceLines[line - 1];
    }

    private String inferErrorType(String message) {
        String msg = String.valueOf(message == null ? "" : message).toLowerCase(Locale.ROOT);
        if (msg.contains("division by zero")) {
            return "DivisionByZeroError";
        }
        if (msg.contains("modulo by zero")) {
            return "ModuloByZeroError";
        }
        if (msg.contains("undefined variable")) {
            return "NameError";
        }
        if (msg.contains("index") && (msg.contains("bounds") || msg.contains("out of"))) {
            return "IndexError";
        }
        if (msg.contains("cannot cast") || msg.contains("expects")) {
            return "TypeError";
        }
        if (msg.contains("invalid xml")) {
            return "XmlParseError";
        }
        if (msg.contains("invalid json")) {
            return "JsonParseError";
        }
        if (msg.contains("permission denied")) {
            return VdbExceptionTypes.PERMISSION;
        }
        if (msg.contains("not authenticated")) {
            return VdbExceptionTypes.NOT_AUTHENTICATED;
        }
        if (msg.contains("vdb.auth") || msg.contains("wrong password") || msg.contains("unknown vdb user")
                || msg.contains("no vdb users configured") || msg.contains("authentication")) {
            return VdbExceptionTypes.AUTH;
        }
        return "RuntimeError";
    }
}
