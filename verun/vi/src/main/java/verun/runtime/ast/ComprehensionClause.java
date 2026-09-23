// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.ast;

public class ComprehensionClause {
    public final String iterator;
    public final Node iterable;
    public final Node condition;

    public ComprehensionClause(String iterator, Node iterable, Node condition) {
        this.iterator = iterator;
        this.iterable = iterable;
        this.condition = condition;
    }
}