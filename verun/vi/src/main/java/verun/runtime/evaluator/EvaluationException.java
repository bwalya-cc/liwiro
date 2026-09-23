// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

public class EvaluationException extends RuntimeException {
    private final String type;
    private final int line;
    private final int column;
    private final String sourceLine;

    public EvaluationException(String message) {
        this("RuntimeError", message, -1, -1, null, null);
    }

    public EvaluationException(String message, Throwable cause) {
        this("RuntimeError", message, -1, -1, null, cause);
    }

    public EvaluationException(String type, String message) {
        this(type, message, -1, -1, null, null);
    }

    public EvaluationException(String type, String message, int line, int column) {
        this(type, message, line, column, null, null);
    }

    public EvaluationException(String type, String message, int line, int column, Throwable cause) {
        this(type, message, line, column, null, cause);
    }

    public EvaluationException(String type, String message, int line, int column, String sourceLine) {
        this(type, message, line, column, sourceLine, null);
    }

    public EvaluationException(String type, String message, int line, int column, String sourceLine, Throwable cause) {
        super(message, cause);
        this.type = VdbExceptionTypes.normalizeType(type == null || type.isBlank() ? "RuntimeError" : type);
        this.line = line;
        this.column = column;
        this.sourceLine = sourceLine;
    }

    public String getType() {
        return type;
    }

    public int getLine() {
        return line;
    }

    public int getColumn() {
        return column;
    }

    public String getSourceLine() {
        return sourceLine;
    }
}
