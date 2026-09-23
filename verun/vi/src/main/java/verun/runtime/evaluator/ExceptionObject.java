// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

public class ExceptionObject {
    public final String type;
    public final String base_type;
    public final String baseType;
    public final String type_alias;
    public final String typeAlias;
    public final String type_code;
    public final String typeCode;
    public final String message;
    public final int line;
    public final int column;
    public final String source_line;

    public ExceptionObject(String message) {
        this("RuntimeError", message, -1, -1, null);
    }

    public ExceptionObject(String type, String message, int line, int column, String sourceLine) {
        String normalizedType = VdbExceptionTypes.normalizeType(type == null || type.isBlank() ? "RuntimeError" : type);
        this.type = normalizedType;
        this.base_type = VdbExceptionTypes.baseFor(normalizedType);
        this.baseType = this.base_type;
        this.type_alias = VdbExceptionTypes.aliasFor(normalizedType);
        this.typeAlias = this.type_alias;
        this.type_code = VdbExceptionTypes.codeFor(normalizedType);
        this.typeCode = this.type_code;
        this.message = message == null ? "" : message;
        this.line = line;
        this.column = column;
        this.source_line = sourceLine == null ? "" : sourceLine;
    }

    public static ExceptionObject from(Throwable throwable) {
        if (throwable instanceof EvaluationException) {
            EvaluationException ee = (EvaluationException) throwable;
            return new ExceptionObject(ee.getType(), ee.getMessage(), ee.getLine(), ee.getColumn(), ee.getSourceLine());
        }
        String message = throwable == null ? "Unknown error" : (throwable.getMessage() == null ? throwable.toString() : throwable.getMessage());
        return new ExceptionObject("RuntimeError", message, -1, -1, null);
    }

    @Override
    public String toString() {
        String where = (line > 0 && column > 0) ? (" at line " + line + ", column " + column) : "";
        return type + ": " + message + where;
    }
}
