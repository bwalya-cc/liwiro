// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.evaluator;

public final class UnsetValue {
    public static final UnsetValue INSTANCE = new UnsetValue(null);
    private final String declaredType;

    private UnsetValue(String declaredType) {
        this.declaredType = declaredType;
    }

    public static UnsetValue typed(String declaredType) {
        if (declaredType == null || declaredType.trim().isEmpty()) {
            return INSTANCE;
        }
        return new UnsetValue(declaredType.trim());
    }

    public String getDeclaredType() {
        return declaredType;
    }

    @Override
    public String toString() {
        return "unset";
    }
}
