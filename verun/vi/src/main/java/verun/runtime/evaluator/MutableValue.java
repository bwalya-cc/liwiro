// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

public class MutableValue {
    public Object value;
    public final String declaredType;

    public MutableValue(Object value) {
        this(value, null);
    }

    public MutableValue(Object value, String declaredType) {
        this.value = value;
        this.declaredType = declaredType;
    }
}
