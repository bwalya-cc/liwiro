// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import java.util.*;

/** Typed intermediate representation for the native VDB Versa command language. */
public final class VDBCommand {
    public enum Kind {
        CONTEXT, WHOAMI, ECHO, HELP, CLEAR, LICENSE, EXIT,
        READ_DOMAINS, READ_ALL_DOMAINS, READ_DOMAINS_WITH_OWNERS,
        READ_DATABASES, READ_COLLECTIONS, READ_MODELS, READ_SCRIPTS,
        READ_USERS, READ_ROLES, READ_PERMISSIONS, READ_OWNED_DOMAINS,
        READ_COLLECTION, READ_ONE, COUNT,
        CREATE_DOMAIN, CREATE_DATABASE, CREATE_COLLECTION, CREATE_DOCUMENT,
        CREATE_USER, CREATE_ROLE, CREATE_INDEX, CREATE_SCRIPT,
        UPDATE_COLLECTION, UPDATE_USER, UPDATE_ROLE,
        DELETE_DOCUMENT, DELETE_USER, DELETE_ROLE, DELETE_SCRIPT,
        DROP_DOMAIN, DROP_DATABASE, DROP_COLLECTION, DROP_INDEX, DROP_MODEL,
        USE_DOMAIN, USE_DATABASE, USE_PATH,
        DESCRIBE_COLLECTION, STATUS_DOMAIN, SUSPEND_DOMAIN, RESUME_DOMAIN,
        GRANT_PERMISSION, REVOKE_PERMISSION, GRANT_ROLE, REVOKE_ROLE,
        GRANT_OWNERSHIP, TRANSFER_DOMAIN,
        READ_INDEXES, REBUILD_INDEXES, REBUILD_INDEX,
        RUN_SCRIPT, EXPORT, BEGIN_TRANSACTION, COMMIT_TRANSACTION,
        ROLLBACK_TRANSACTION, TRANSACTION_BLOCK, AGGREGATE
    }

    public interface Expression {
        Object evaluate(Map<String, Object> document, Map<String, Object> bindings);
    }

    public static final class Literal implements Expression {
        public final Object value;
        public Literal(Object value) { this.value = value; }
        @Override public Object evaluate(Map<String, Object> document, Map<String, Object> bindings) { return value; }
    }

    public static final class Field implements Expression {
        public final String path;
        public Field(String path) { this.path = Objects.requireNonNull(path); }
        @Override public Object evaluate(Map<String, Object> document, Map<String, Object> bindings) {
            if (bindings != null && bindings.containsKey(path)) return bindings.get(path);
            return QueryEvaluator.getNestedField(document, path);
        }
    }

    public static final class Unary implements Expression {
        public final String operator;
        public final Expression operand;
        public Unary(String operator, Expression operand) { this.operator = operator; this.operand = operand; }
        @Override public Object evaluate(Map<String, Object> document, Map<String, Object> bindings) {
            Object value = operand.evaluate(document, bindings);
            if ("!".equals(operator)) return !truthy(value);
            if ("-".equals(operator) && value instanceof Number) return -((Number) value).doubleValue();
            throw new IllegalArgumentException("Unsupported unary operator: " + operator);
        }
    }

    public static final class Binary implements Expression {
        public final String operator;
        public final Expression left;
        public final Expression right;
        public Binary(String operator, Expression left, Expression right) {
            this.operator = operator; this.left = left; this.right = right;
        }
        @Override public Object evaluate(Map<String, Object> document, Map<String, Object> bindings) {
            Object a = left.evaluate(document, bindings);
            if ("&&".equals(operator) && !truthy(a)) return false;
            if ("||".equals(operator) && truthy(a)) return true;
            Object b = right.evaluate(document, bindings);
            switch (operator) {
                case "&&": return truthy(b);
                case "||": return truthy(b);
                case "==": return valuesEqual(a, b);
                case "!=": return !valuesEqual(a, b);
                case ">": return compare(a, b) > 0;
                case "<": return compare(a, b) < 0;
                case ">=": return compare(a, b) >= 0;
                case "<=": return compare(a, b) <= 0;
                case "in": return contains(b, a);
                case "!in": return !contains(b, a);
                case "??": return a == null ? b : a;
                case "+":
                    if (a instanceof Number && b instanceof Number) return numeric(a, b, '+');
                    return String.valueOf(a) + String.valueOf(b);
                case "-": return numeric(a, b, '-');
                case "*": return numeric(a, b, '*');
                case "/": return numeric(a, b, '/');
                default: throw new IllegalArgumentException("Unsupported binary operator: " + operator);
            }
        }
    }

    public static final class Range implements Expression {
        public final Expression start;
        public final Expression end;
        public Range(Expression start, Expression end) { this.start = start; this.end = end; }
        @Override public Object evaluate(Map<String, Object> document, Map<String, Object> bindings) {
            return new RangeValue(start.evaluate(document, bindings), end.evaluate(document, bindings));
        }
    }

    public static final class Call implements Expression {
        public final String name;
        public final List<Expression> arguments;
        public Call(String name, List<Expression> arguments) { this.name = name; this.arguments = arguments; }
        @Override public Object evaluate(Map<String, Object> document, Map<String, Object> bindings) {
            if ("exists".equals(name) && arguments.size() == 1 && arguments.get(0) instanceof Field)
                return hasNestedField(document, ((Field) arguments.get(0)).path);
            if ("now".equals(name) && arguments.isEmpty()) return System.currentTimeMillis();
            throw new IllegalArgumentException("Function is not available in this VDB expression: " + name);
        }
    }

    public static final class RangeValue {
        public final Object start;
        public final Object end;
        RangeValue(Object start, Object end) { this.start = start; this.end = end; }
    }

    public static final class Order {
        public final String field;
        public final boolean ascending;
        public Order(String field, boolean ascending) { this.field = field; this.ascending = ascending; }
    }

    public static final class Update {
        public enum Operation { SET, INCREMENT, DECREMENT, UNSET }
        public final String field;
        public final Operation operation;
        public final Expression value;
        public Update(String field, Operation operation, Expression value) {
            this.field = field; this.operation = operation; this.value = value;
        }
    }

    public static final class SchemaField {
        public final String name;
        public final String type;
        public final boolean nullable;
        public final Object defaultValue;
        public final Set<String> annotations;
        public final Map<String, SchemaField> fields;
        public SchemaField(String name, String type, boolean nullable, Object defaultValue,
                           Set<String> annotations, Map<String, SchemaField> fields) {
            this.name = name; this.type = type; this.nullable = nullable; this.defaultValue = defaultValue;
            this.annotations = Collections.unmodifiableSet(new LinkedHashSet<>(annotations));
            this.fields = Collections.unmodifiableMap(new LinkedHashMap<>(fields));
        }
    }

    public final Kind kind;
    public final String target;
    public final Object value;
    public final Expression predicate;
    public final List<String> selection;
    public final List<Order> order;
    public final List<Update> updates;
    public final Map<String, Object> options;
    public final List<VDBCommand> statements;
    public final int offset;
    public final int limit;
    public final boolean all;

    public VDBCommand(Kind kind, String target, Object value, Expression predicate,
                      List<String> selection, List<Order> order, List<Update> updates,
                      Map<String, Object> options, List<VDBCommand> statements,
                      int offset, int limit, boolean all) {
        this.kind = Objects.requireNonNull(kind); this.target = target; this.value = value;
        this.predicate = predicate;
        this.selection = immutable(selection); this.order = immutable(order); this.updates = immutable(updates);
        this.options = Collections.unmodifiableMap(new LinkedHashMap<>(options));
        this.statements = immutable(statements); this.offset = offset; this.limit = limit; this.all = all;
    }

    private static <T> List<T> immutable(List<T> source) {
        return Collections.unmodifiableList(new ArrayList<>(source));
    }

    public static final class Batch {
        public final List<VDBCommand> commands;
        public Batch(List<VDBCommand> commands) { this.commands = immutable(commands); }
    }

    static boolean truthy(Object value) {
        return value instanceof Boolean ? (Boolean) value : value != null && (!(value instanceof Number) || ((Number) value).doubleValue() != 0);
    }
    private static boolean valuesEqual(Object a, Object b) {
        if (a instanceof Number && b instanceof Number) return Double.compare(((Number) a).doubleValue(), ((Number) b).doubleValue()) == 0;
        return Objects.equals(a, b);
    }
    @SuppressWarnings({"unchecked", "rawtypes"})
    private static int compare(Object a, Object b) {
        if (a == null || b == null) throw new IllegalArgumentException("Cannot order null values");
        if (a instanceof Number && b instanceof Number) return Double.compare(((Number) a).doubleValue(), ((Number) b).doubleValue());
        if (a instanceof Comparable && a.getClass().isInstance(b)) return ((Comparable) a).compareTo(b);
        return String.valueOf(a).compareTo(String.valueOf(b));
    }
    private static boolean contains(Object container, Object item) {
        if (container instanceof RangeValue) {
            RangeValue range = (RangeValue) container;
            return compare(item, range.start) >= 0 && compare(item, range.end) <= 0;
        }
        if (container instanceof java.util.Collection<?>) return ((java.util.Collection<?>) container).stream().anyMatch(value -> valuesEqual(value, item));
        if (container instanceof String) return ((String) container).contains(String.valueOf(item));
        return false;
    }
    private static Object numeric(Object a, Object b, char operation) {
        if (!(a instanceof Number) || !(b instanceof Number)) throw new IllegalArgumentException("Numeric operator requires numbers");
        double result;
        switch (operation) {
            case '+': result = ((Number) a).doubleValue() + ((Number) b).doubleValue(); break;
            case '-': result = ((Number) a).doubleValue() - ((Number) b).doubleValue(); break;
            case '*': result = ((Number) a).doubleValue() * ((Number) b).doubleValue(); break;
            default: result = ((Number) a).doubleValue() / ((Number) b).doubleValue();
        }
        if (a instanceof Integer && b instanceof Integer && operation != '/') return (int) result;
        if (a instanceof Long && b instanceof Number && operation != '/') return (long) result;
        return result;
    }
    @SuppressWarnings("unchecked")
    static boolean hasNestedField(Map<String, Object> document, String field) {
        Object current = document;
        for (String part : field.split("\\.")) {
            if (!(current instanceof Map) || !((Map<String, Object>) current).containsKey(part)) return false;
            current = ((Map<String, Object>) current).get(part);
        }
        return true;
    }
}
