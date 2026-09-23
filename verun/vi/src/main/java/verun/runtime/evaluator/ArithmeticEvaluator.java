// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import verun.runtime.modules.TimeDate;

import java.util.Map;

import verun.runtime.ast.IdentifierNode;
import verun.runtime.ast.Node;

public class ArithmeticEvaluator {
    public static Object applyOperator(String operator, Object left, Object right) {
        Object datetimeAware = TimeDate.tryApplyOperator(operator, left, right);
        if (datetimeAware != null) {
            return datetimeAware;
        }
        switch (operator) {
            case "+":
                if (left instanceof String || right instanceof String) {
                    return ValueFormatter.toDisplayString(left) + ValueFormatter.toDisplayString(right);
                }
                return numericBinary(operator, left, right, (a, b) -> a + b, (a, b) -> a + b);
            case "-":
                return numericBinary(operator, left, right, (a, b) -> a - b, (a, b) -> a - b);
            case "*":
                if (left instanceof String || right instanceof String) {
                    return stringMultiply(left, right);
                }
                return numericBinary(operator, left, right, (a, b) -> a * b, (a, b) -> a * b);
            case "/":
                ensureNumbers(operator, left, right);
                if (((Number) right).doubleValue() == 0.0d) {
                    throw new EvaluationException("Division by zero");
                }
                return ((Number) left).doubleValue() / ((Number) right).doubleValue();
            case "//":
                ensureNumbers(operator, left, right);
                if (((Number) right).doubleValue() == 0.0d) {
                    throw new EvaluationException("Division by zero");
                }
                double floor = Math.floor(((Number) left).doubleValue() / ((Number) right).doubleValue());
                if (floor < Integer.MIN_VALUE || floor > Integer.MAX_VALUE) {
                    throw new EvaluationException("Floor division result is out of int range");
                }
                return (int) floor;
            case "%":
                ensureNumbers(operator, left, right);
                if (left instanceof Integer && right instanceof Integer) {
                    int divisor = (Integer) right;
                    if (divisor == 0) {
                        throw new EvaluationException("Modulo by zero");
                    }
                    return ((Integer) left) % divisor;
                }
                if (((Number) right).doubleValue() == 0.0d) {
                    throw new EvaluationException("Modulo by zero");
                }
                return ((Number) left).doubleValue() % ((Number) right).doubleValue();
            case "**":
                return numericBinary(operator, left, right, (a, b) -> Math.pow(a, b), (a, b) -> Math.pow(a, b));
            case "^":
                return numericBinary(operator, left, right, (a, b) -> Math.pow(a, b), (a, b) -> Math.pow(a, b));
            case "^^":
                ensureIntegers(operator, left, right);
                return ((Integer) left) ^ ((Integer) right);
            case "&":
                ensureIntegers(operator, left, right);
                return ((Integer) left) & ((Integer) right);
            case "|":
                ensureIntegers(operator, left, right);
                return ((Integer) left) | ((Integer) right);
            case "<<":
                ensureIntegers(operator, left, right);
                return ((Integer) left) << ((Integer) right);
            case ">>":
                ensureIntegers(operator, left, right);
                return ((Integer) left) >> ((Integer) right);
            case "==":
                return equalsNullable(left, right);
            case "!=":
                return !equalsNullable(left, right);
            case "<":
                return comparable(operator, left, right, -1);
            case ">":
                return comparable(operator, left, right, 1);
            case "<=":
                return comparable(operator, left, right, -2);
            case ">=":
                return comparable(operator, left, right, 2);
            default:
                throw new EvaluationException("Unsupported operator: " + operator);
        }
    }

    public static Object applyUnaryOperator(String operator, Object operand, boolean isPostfix, Node operandNode,
            Map<String, Object> environment) {
        switch (operator) {
            case "++":
            case "--":
                return handleIncrementDecrement(operator, operand, isPostfix, operandNode, environment);
            case "!":
                if (!(operand instanceof Boolean)) {
                    throw new EvaluationException("Logical NOT requires a boolean operand");
                }
                return !((Boolean) operand);
            case "-":
                if (operand instanceof Integer) {
                    return -((Integer) operand);
                }
                if (operand instanceof Number) {
                    return -((Number) operand).doubleValue();
                }
                throw new EvaluationException("Unary '-' requires a numeric operand");
            case "+":
                if (operand instanceof Number) {
                    return operand;
                }
                throw new EvaluationException("Unary '+' requires a numeric operand");
            case "~":
                if (operand instanceof Integer) {
                    return ~((Integer) operand);
                }
                throw new EvaluationException("Bitwise NOT requires an integer operand");
            default:
                throw new EvaluationException("Unsupported unary operator: " + operator);
        }
    }

    private static Object handleIncrementDecrement(String operator, Object operand, boolean isPostfix, Node operandNode,
            Map<String, Object> environment) {
        Object actualOperand = operand;
        String varName = null;

        if (operandNode instanceof IdentifierNode) {
            varName = ((IdentifierNode) operandNode).name;
            actualOperand = environment.get(varName);
        }

        if (!(actualOperand instanceof MutableValue)) {
            throw new EvaluationException(operator + " requires a mutable variable");
        }
        Object raw = ((MutableValue) actualOperand).value;
        if (!(raw instanceof Integer)) {
            throw new EvaluationException(operator + " requires an integer variable");
        }
        MutableValue mutable = (MutableValue) actualOperand;
        int value = (Integer) raw;
        int next = operator.equals("++") ? value + 1 : value - 1;
        mutable.value = next;
        return isPostfix ? value : next;
    }

    public static boolean isTruthy(Object object) {
        if (object == null) {
            return false;
        }
        if (object instanceof Boolean) {
            return (Boolean) object;
        }
        return true;
    }

    private static Object numericBinary(
            String operator,
            Object left,
            Object right,
            DoubleBinaryOp doubleOp,
            DoubleBinaryOp intOpAsDouble) {
        ensureNumbers(operator, left, right);
        if (left instanceof Integer && right instanceof Integer) {
            double result = intOpAsDouble.apply(((Integer) left).doubleValue(), ((Integer) right).doubleValue());
            if (Math.floor(result) == result && result >= Integer.MIN_VALUE && result <= Integer.MAX_VALUE) {
                return (int) result;
            }
            return result;
        }
        return doubleOp.apply(((Number) left).doubleValue(), ((Number) right).doubleValue());
    }

    private static Object comparable(String operator, Object left, Object right, int mode) {
        if (left instanceof Number && right instanceof Number) {
            double l = ((Number) left).doubleValue();
            double r = ((Number) right).doubleValue();
            if (mode == -1) return l < r;
            if (mode == 1) return l > r;
            if (mode == -2) return l <= r;
            return l >= r;
        }
        if (left instanceof String && right instanceof String) {
            int cmp = ((String) left).compareTo((String) right);
            if (mode == -1) return cmp < 0;
            if (mode == 1) return cmp > 0;
            if (mode == -2) return cmp <= 0;
            return cmp >= 0;
        }
        throw new EvaluationException("Operator '" + operator + "' requires both operands to be numbers or strings");
    }

    private static boolean equalsNullable(Object left, Object right) {
        if (left == null && right == null) {
            return true;
        }
        if (left == null || right == null) {
            return false;
        }
        if (left instanceof Number && right instanceof Number) {
            return Double.compare(((Number) left).doubleValue(), ((Number) right).doubleValue()) == 0;
        }
        return left.equals(right);
    }

    private static void ensureNumbers(String operator, Object left, Object right) {
        if (!(left instanceof Number) || !(right instanceof Number)) {
            throw new EvaluationException(
                    "Operator '" + operator + "' requires numeric operands, got " + typeOf(left) + " and " + typeOf(right));
        }
    }

    private static void ensureIntegers(String operator, Object left, Object right) {
        if (!(left instanceof Integer) || !(right instanceof Integer)) {
            throw new EvaluationException(
                    "Operator '" + operator + "' requires integer operands, got " + typeOf(left) + " and " + typeOf(right));
        }
    }

    private static Object stringMultiply(Object left, Object right) {
        if (left instanceof String && isWholeNumber(right)) {
            return repeat((String) left, asWholeNumber(right));
        }
        if (right instanceof String && isWholeNumber(left)) {
            return repeat((String) right, asWholeNumber(left));
        }
        throw new EvaluationException(
                "Operator '*' supports string repetition only with a whole-number operand, got "
                        + typeOf(left) + " and " + typeOf(right));
    }

    private static boolean isWholeNumber(Object value) {
        if (!(value instanceof Number)) {
            return false;
        }
        if (value instanceof Integer) {
            return true;
        }
        double asDouble = ((Number) value).doubleValue();
        return Double.isFinite(asDouble) && Math.floor(asDouble) == asDouble;
    }

    private static int asWholeNumber(Object value) {
        if (!isWholeNumber(value)) {
            throw new EvaluationException("Expected a whole-number value, got " + typeOf(value));
        }
        double asDouble = ((Number) value).doubleValue();
        if (asDouble < Integer.MIN_VALUE || asDouble > Integer.MAX_VALUE) {
            throw new EvaluationException("Whole number is out of int range: " + ValueFormatter.toDisplayString(value));
        }
        return (int) asDouble;
    }

    private static String repeat(String source, int count) {
        if (count <= 0 || source.isEmpty()) {
            return "";
        }
        StringBuilder builder = new StringBuilder(source.length() * count);
        for (int i = 0; i < count; i++) {
            builder.append(source);
        }
        return builder.toString();
    }

    private static String typeOf(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof Integer) {
            return "int";
        }
        if (value instanceof Number) {
            return "float";
        }
        if (value instanceof String) {
            return "string";
        }
        if (value instanceof Boolean) {
            return "bool";
        }
        if (value instanceof java.util.Map) {
            return "object";
        }
        if (value instanceof java.util.List) {
            return "list";
        }
        return value.getClass().getSimpleName();
    }

    @FunctionalInterface
    private interface DoubleBinaryOp {
        double apply(double a, double b);
    }
}
