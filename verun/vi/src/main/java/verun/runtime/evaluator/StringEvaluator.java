// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

import java.util.Arrays;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class StringEvaluator {
    public static Object handleStringOperation(Object left, String operator, Object right) {
        if ("+".equals(operator)) {
            return left.toString() + right.toString();
        }
        throw new EvaluationException("Unsupported string operator: " + operator);
    }

    public static Object callMethod(String method, String str, List<Object> args) {
        switch (method) {
            case "split":
                if (args.isEmpty()) {
                    String trimmed = str.replaceFirst("(?U)^\\s+", "")
                            .replaceFirst("(?U)\\s+$", "");
                    return trimmed.isEmpty() ? new ArrayList<>() : Arrays.asList(trimmed.split("\\s+"));
                }
                return Arrays.asList(str.split(args.get(0).toString()));
            case "splitlines":
                return Arrays.asList(str.split("\\R"));
            case "toUpper":
            case "upper":
                return str.toUpperCase(Locale.ROOT);
            case "toLower":
            case "lower":
                return str.toLowerCase(Locale.ROOT);
            case "casefold":
                return str.toLowerCase(Locale.ROOT);
            case "capitalize":
            case "capitalise":
                if (str.isEmpty()) {
                    return str;
                }
                return str.substring(0, 1).toUpperCase(Locale.ROOT) + str.substring(1).toLowerCase(Locale.ROOT);
            case "title":
                if (str.isEmpty()) {
                    return str;
                }
                String[] parts = str.split("\\s+");
                StringBuilder titled = new StringBuilder();
                for (int i = 0; i < parts.length; i++) {
                    String p = parts[i];
                    if (!p.isEmpty()) {
                        p = p.substring(0, 1).toUpperCase(Locale.ROOT) + p.substring(1).toLowerCase(Locale.ROOT);
                    }
                    if (i > 0) {
                        titled.append(" ");
                    }
                    titled.append(p);
                }
                return titled.toString();
            case "trim":
            case "strip":
                return str.replaceFirst("(?U)^\\s+", "")
                        .replaceFirst("(?U)\\s+$", "");
            case "lstrip":
                return str.replaceFirst("(?U)^\\s+", "");
            case "rstrip":
                return str.replaceFirst("(?U)\\s+$", "");
            case "join":
                if (args.isEmpty()) {
                    throw new EvaluationException("join expects an iterable argument");
                }
                Object iterable = args.get(0);
                if (iterable instanceof List<?> || iterable instanceof java.util.Set<?> || iterable instanceof java.util.Map<?, ?>) {
                    List<String> joinParts = new ArrayList<>();
                    Iterable<?> values = iterable instanceof List<?> ? (List<?>) iterable
                            : iterable instanceof java.util.Set<?> ? (java.util.Set<?>) iterable
                            : ((java.util.Map<?, ?>) iterable).keySet();
                    for (Object item : values) {
                        joinParts.add(String.valueOf(item));
                    }
                    return String.join(str, joinParts);
                }
                if (iterable instanceof String) {
                    String source = (String) iterable;
                    StringBuilder joined = new StringBuilder();
                    boolean first = true;
                    for (int offset = 0; offset < source.length();) {
                        int codePoint = source.codePointAt(offset);
                        if (!first) {
                            joined.append(str);
                        }
                        joined.appendCodePoint(codePoint);
                        first = false;
                        offset += Character.charCount(codePoint);
                    }
                    return joined.toString();
                }
                throw new EvaluationException("join expects a list, set, map, or string argument");
            case "contains":
                if (args.isEmpty()) {
                    throw new EvaluationException("contains expects one argument");
                }
                return str.contains(String.valueOf(args.get(0)));
            case "startswith":
            case "starts_with":
                if (args.isEmpty()) {
                    throw new EvaluationException("startswith expects one argument");
                }
                return str.startsWith(String.valueOf(args.get(0)));
            case "endswith":
            case "ends_with":
                if (args.isEmpty()) {
                    throw new EvaluationException("endswith expects one argument");
                }
                return str.endsWith(String.valueOf(args.get(0)));
            case "replace":
                if (args.size() < 2) {
                    throw new EvaluationException("replace expects old and new");
                }
                return str.replace(String.valueOf(args.get(0)), String.valueOf(args.get(1)));
            case "count":
                if (args.isEmpty()) {
                    throw new EvaluationException("count expects one argument");
                }
                String needle = String.valueOf(args.get(0));
                if (needle.isEmpty()) {
                    return str.length() + 1;
                }
                int count = 0;
                int at = 0;
                while (true) {
                    int idx = str.indexOf(needle, at);
                    if (idx < 0) {
                        break;
                    }
                    count++;
                    at = idx + needle.length();
                }
                return count;
            case "find":
                if (args.isEmpty()) {
                    throw new EvaluationException("find expects one argument");
                }
                return str.indexOf(String.valueOf(args.get(0)));
            case "index":
                if (args.isEmpty()) {
                    throw new EvaluationException("index expects one argument");
                }
                int index = str.indexOf(String.valueOf(args.get(0)));
                if (index < 0) {
                    throw new EvaluationException("substring not found");
                }
                return index;
            case "isalpha":
                return !str.isEmpty() && str.chars().allMatch(Character::isLetter);
            case "isdigit":
                return !str.isEmpty() && str.chars().allMatch(Character::isDigit);
            case "isalnum":
                return !str.isEmpty() && str.chars().allMatch(Character::isLetterOrDigit);
            case "isspace":
                return !str.isEmpty() && str.chars().allMatch(Character::isWhitespace);
            case "islower":
                return !str.isEmpty()
                        && str.chars().anyMatch(Character::isLetter)
                        && str.equals(str.toLowerCase(Locale.ROOT));
            case "isupper":
                return !str.isEmpty()
                        && str.chars().anyMatch(Character::isLetter)
                        && str.equals(str.toUpperCase(Locale.ROOT));
            case "message": // Added handling for message property
                return str;
            default:
                throw new EvaluationException("Unknown string method: " + method);
        }
    }
}
